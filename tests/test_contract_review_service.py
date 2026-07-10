from unittest.mock import patch

from app.capabilities.contract_review.schemas import AttachmentInput, ContractReviewRequest, SystemPreset
from app.capabilities.contract_review.service import (
    _invoke_json_prompt,
    _preprocess_request,
    _run_b1,
    review_contract,
    run_review_pipeline,
)
from app.core.errors import ModelFormatError
import pytest


def test_review_contract_preserves_fail_and_warn_from_checks():
    request = ContractReviewRequest(contract_md="# 合同", attachments=[])
    with patch("app.capabilities.contract_review.service.run_review_pipeline") as fake_pipeline:
        fake_pipeline.return_value = [
            {"id": "序号2", "name": "签章页完整性", "result": "FAIL", "block_level": "硬阻断", "reason": "银行账号不一致"},
            {"id": "序号2", "name": "签章页完整性", "result": "WARN", "block_level": "提示", "reason": "传真缺失"},
        ]
        data = review_contract(request, check_time="2026-07-07T10:00:00")
    assert data.overall_result == "BLOCK"
    assert len(data.checks) == 2


def test_review_contract_does_not_call_real_llm_in_unit_test():
    request = ContractReviewRequest(contract_md="# 合同", attachments=[])
    with patch("app.capabilities.contract_review.service.invoke_model") as fake_invoke:
        with patch("app.capabilities.contract_review.service.run_review_pipeline", return_value=[]):
            review_contract(request, check_time="2026-07-07T10:00:00")
    fake_invoke.assert_not_called()


def test_review_contract_blocks_when_declared_attachments_missing():
    request = ContractReviewRequest(
        contract_md="# 合同\n正文声明附件共3份",
        attachments=[
            AttachmentInput(index=1, filename="附件一.xlsx", text="附件一"),
            AttachmentInput(index=2, filename="附件二.xlsx", text="附件二"),
        ],
    )
    with patch("app.capabilities.contract_review.service.run_review_pipeline") as fake_pipeline:
        fake_pipeline.return_value = [
            {"id": "附件检查-数量标题", "name": "附件数量/标题一致性", "result": "FAIL", "block_level": "硬阻断", "reason": "正文声明附件3份，实际仅获取到2份"}
        ]
        data = review_contract(request, check_time="2026-07-07T10:00:00")
    assert data.overall_result == "BLOCK"
    assert data.checks[0].reason == "正文声明附件3份，实际仅获取到2份"


def test_preprocess_request_splits_embedded_attachments_and_merges_uploaded():
    request = ContractReviewRequest(
        contract_md="# 合同\n\n正文内容\n\n附件一\n内嵌附件内容\n",
        attachments=[
            AttachmentInput(index=10, filename="上传附件.md", file_type="md", text="上传附件内容"),
        ],
    )

    prepared = _preprocess_request(request)

    assert "正文内容" in prepared["full_text"]
    assert "内嵌附件内容" not in prepared["full_text"]
    assert [item["filename"] for item in prepared["attachments"]] == ["附件一.md", "上传附件.md"]
    assert prepared["attachments"][0]["text"] == "附件一\n内嵌附件内容"
    assert prepared["attachments"][0]["source"] == "合同正文内嵌"
    assert "【附件】附件一.md" in prepared["full_text_and_attachments"]
    assert "【附件】上传附件.md" in prepared["full_text_and_attachments"]


def test_run_review_pipeline_uses_llm_adapter_and_preset_fetch():
    request = ContractReviewRequest(
        contract_md="# 合同\n甲方：客户公司\n乙方：我方公司\n附件共3份",
        attachments=[
            AttachmentInput(index=1, filename="附件一.xlsx", text="附件一"),
            AttachmentInput(index=2, filename="附件二.xlsx", text="附件二"),
        ],
    )
    outputs = [
        '{"header":{"contract_name":"测试合同","contract_number":"HT-1","signing_location":"沈阳","signing_date":"2026年7月8日","parties":[{"role":"甲方","name":"客户公司"},{"role":"乙方","name":"我方公司"}]},"signature_parties":[{"role":"甲方","name":"客户公司"},{"role":"乙方","name":"我方公司"}],"sections":[]}',
        '{"signature":{"role":"乙方","name":"我方公司","legal_rep_name":"张三","signing_date":"2026年7月8日","bank_name":"招商银行","bank_account":"123456","account_holder":"我方公司","address":"地址","phone":"024-12345678","fax":"","website":"","postal_code":"110000"}}',
        '{"currency":"人民币","payment_method":"电汇","total_amount_numeric":"100","total_amount_uppercase":"壹佰元整","total_amount_match":true,"payment_stages":[]}',
        '{"copies":{"total_copies":2,"party_copies":[{"role":"甲方","copies":1},{"role":"乙方","copies":1}]},"attachments_declared":[{"index":1,"title":"附件一","content_embedded_in_contract":false},{"index":2,"title":"附件二","content_embedded_in_contract":false},{"index":3,"title":"附件三","content_embedded_in_contract":false}],"total_declared":3}',
        '{"checks":[]}',
        '{"checks":[]}',
        '{"checks":[]}',
    ]

    def fake_invoke(model, messages, response_format=None):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            with patch("app.capabilities.contract_review.service.fetch_preset") as fake_fetch:
                fake_fetch.return_value = SystemPreset(
                    entity_name="我方公司",
                    legal_rep_name="张三",
                    legal_rep_id_number="",
                    authorized_reps=[],
                    bank_name="招商银行",
                    bank_account="123456",
                    account_holder="我方公司",
                    address="地址",
                    phone="024-12345678",
                    fax="",
                    website="",
                    postal_code="110000",
                )
                items = run_review_pipeline(request)

    assert fake_fetch.call_args.args == ("我方公司",)
    assert any(item.id == "附件检查-数量标题" and item.result == "FAIL" for item in items)


def test_run_review_pipeline_reports_candidate_when_preset_lookup_misses():
    request = ContractReviewRequest(contract_md="# 合同\n供应商（乙方）：东软集团股份有限公司", attachments=[])
    outputs = [
        '{"header":{"contract_name":"合同","project_name":"项目名称","contract_number":"HT-1","signing_location":"南宁","signing_date":"2026年7月9日","parties":[{"role":"甲方","name":"客户公司"},{"role":"乙方","name":"东软集团股份有限公司"}]},"signature_parties":[{"role":"甲方","name":"客户公司"},{"role":"乙方","name":"东软集团股份有限公司"}],"sections":[]}',
        '{"currency":"人民币","payment_method":"电汇","total_amount_numeric":"100","total_amount_uppercase":"壹佰元整","total_amount_match":true,"payment_stages":[]}',
        '{"copies":{"total_copies":2,"party_copies":[{"role":"甲方","copies":1},{"role":"乙方","copies":1}]},"attachments_declared":[],"total_declared":0}',
        '{"checks":[]}',
    ]

    def fake_invoke(model, messages, response_format=None):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            with patch("app.capabilities.contract_review.service.fetch_preset", return_value=None):
                items = run_review_pipeline(request)

    seq1_fail = next(item for item in items if item.id == "序号1" and item.result == "FAIL")
    assert "已提取我方候选主体：东软集团股份有限公司" in seq1_fail.reason
    assert "合同名称缺失" not in seq1_fail.reason


def test_run_review_pipeline_sends_embedded_and_uploaded_attachments_to_b4():
    request = ContractReviewRequest(
        contract_md="# 合同\n甲方：客户公司\n乙方：我方公司\n\n附件一\n内嵌附件内容",
        attachments=[
            AttachmentInput(index=2, filename="附件二.md", text="上传附件二"),
            AttachmentInput(index=3, filename="附件三.md", text="上传附件三"),
        ],
    )
    outputs = [
        '{"header":{"contract_name":"测试合同","project_name":null,"project_number":null,"contract_number":"HT-1","signing_location":"沈阳","signing_date":"2026年7月8日","parties":[{"role":"甲方","name":"客户公司"},{"role":"乙方","name":"我方公司"}]},"signature_parties":[{"role":"甲方","name":"客户公司"},{"role":"乙方","name":"我方公司"}],"sections":[]}',
        '{"signature":{"role":"乙方","name":"我方公司","legal_rep_name":"张三","signing_date":"2026年7月8日","bank_name":"招商银行","bank_account":"123456","account_holder":"我方公司","address":"地址","phone":"024-12345678","fax":"","website":"","postal_code":"110000"}}',
        '{"currency":"人民币","payment_method":"电汇","total_amount_numeric":"100","total_amount_uppercase":"壹佰元整","total_amount_match":true,"payment_stages":[]}',
        '{"copies":{"total_copies":2,"party_copies":[{"role":"甲方","copies":1},{"role":"乙方","copies":1}]},"attachments_declared":[{"index":1,"title":"附件一","content_embedded_in_contract":false},{"index":2,"title":"附件二","content_embedded_in_contract":false},{"index":3,"title":"附件三","content_embedded_in_contract":false}],"total_declared":3}',
        '{"checks":[]}',
        '{"checks":[]}',
        '{"checks":[]}',
        '{"checks":[]}',
    ]
    b4_texts = []

    def fake_invoke(model, messages, response_format=None):
        content = messages[-1].content
        if "【当前附件】" in content:
            b4_texts.append(content)
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            with patch("app.capabilities.contract_review.service.fetch_preset") as fake_fetch:
                fake_fetch.return_value = SystemPreset(
                    entity_name="我方公司",
                    legal_rep_name="张三",
                    legal_rep_id_number="",
                    authorized_reps=[],
                    bank_name="招商银行",
                    bank_account="123456",
                    account_holder="我方公司",
                    address="地址",
                    phone="024-12345678",
                    fax="",
                    website="",
                    postal_code="110000",
                )
                items = run_review_pipeline(request)

    assert len(b4_texts) == 3
    assert any("内嵌附件内容" in text for text in b4_texts)
    assert any("上传附件二" in text for text in b4_texts)
    assert any("上传附件三" in text for text in b4_texts)
    assert all(item.result != "FAIL" for item in items if item.id == "附件检查-数量标题")


def test_invoke_json_prompt_retries_once_when_model_returns_non_json():
    outputs = ["不是JSON", '{"ok": true}']

    def fake_invoke(model, messages, response_format=None):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke) as mocked:
            result = _invoke_json_prompt("a1a_party_extraction", full_text="合同正文")

    assert result == {"ok": True}
    assert mocked.call_count == 2


def test_invoke_json_prompt_passes_json_schema_response_format():
    captured_response_formats = []

    def fake_invoke(model, messages, response_format=None):
        captured_response_formats.append(response_format)
        return (
            '{"header":{"contract_name":null,"project_name":null,"contract_number":null,'
            '"signing_location":null,"signing_date":null,"parties":[]},'
            '"signature_parties":[],"sections":[]}',
            {"total_tokens": 1},
        )

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            result = _invoke_json_prompt("a1a_party_extraction", full_text="合同正文")

    assert result["header"]["parties"] == []
    assert captured_response_formats
    response_format = captured_response_formats[0]
    assert response_format["type"] == "json_schema"
    schema = response_format["json_schema"]["schema"]
    assert schema["required"] == ["header", "signature_parties", "sections"]
    assert schema["properties"]["header"]["required"] == [
        "contract_name",
        "project_name",
        "project_number",
        "contract_number",
        "signing_location",
        "signing_date",
        "parties",
    ]


def test_invoke_json_prompt_retries_when_required_schema_keys_missing():
    outputs = [
        '{"contract_name":"合同","parties":[]}',
        (
            '{"header":{"contract_name":"合同","project_name":null,"contract_number":null,'
            '"signing_location":null,"signing_date":null,"parties":[]},'
            '"signature_parties":[],"sections":[]}'
        ),
    ]

    def fake_invoke(model, messages, response_format=None):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke) as mocked:
            result = _invoke_json_prompt(
                "a1a_party_extraction",
                required_keys=["header", "signature_parties", "sections"],
                full_text="合同正文",
            )

    assert result["header"]["contract_name"] == "合同"
    assert mocked.call_count == 2


def test_invoke_json_prompt_keeps_prompt_name_for_json_parse_error_with_required_keys():
    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", return_value=("不是JSON", {"total_tokens": 1})):
            with pytest.raises(ModelFormatError) as exc:
                _invoke_json_prompt(
                    "a1a_party_extraction",
                    required_keys=["header", "signature_parties", "sections"],
                    validation_label="A-1a",
                    full_text="合同正文",
                )

    assert "a1a_party_extraction模型输出不是合法JSON" in str(exc.value)


def test_invoke_json_prompt_error_message_includes_prompt_name_after_retry_fails():
    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", return_value=("不是JSON", {"total_tokens": 1})):
            with pytest.raises(ModelFormatError) as exc:
                _invoke_json_prompt("a1a_party_extraction", full_text="合同正文")

    assert "a1a_party_extraction模型输出不是合法JSON" in str(exc.value)


def test_run_b1_retries_when_reason_is_too_generic():
    outputs = [
        '{"checks":[{"result":"WARN","block_level":"提示","reason":"称谓存在不一致"}]}',
        '{"checks":[{"result":"WARN","block_level":"提示","reason":"乙方称谓不一致：合同首部为“供应商（乙方）”，正文第3条使用“卖方”，请业务确认是否均指同一主体。"}]}',
    ]

    def fake_invoke(model, messages, response_format=None):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke) as mocked:
            items = _run_b1("合同正文")

    assert mocked.call_count == 2
    assert items[0].result == "WARN"
    assert "乙方称谓不一致" in items[0].reason
    assert "供应商（乙方）" in items[0].reason
