from unittest.mock import patch

from app.capabilities.contract_review.response_formats import RESPONSE_FORMATS
from app.capabilities.contract_review.schemas import AttachmentInput, ContractReviewRequest, SystemPreset
from app.capabilities.contract_review.service import (
    _log_llm_trace,
    _invoke_json_prompt,
    _parse_model_checks,
    _preprocess_request,
    _run_b1,
    _run_b4,
    review_contract,
    run_review_pipeline,
)
from app.core.config import _reset_settings
from app.core.errors import ModelFormatError, ModelInputTooLongError, ModelOutputTooLongError
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


def test_review_contract_exposes_pipeline_metrics():
    request = ContractReviewRequest(contract_md="# 合同", attachments=[])
    with patch("app.capabilities.contract_review.service.run_review_pipeline") as fake_pipeline:
        fake_pipeline.return_value = {
            "items": [
                {"id": "序号1", "name": "合同首页完整性", "result": "PASS", "block_level": "通过"},
            ],
            "metrics": [
                {
                    "id": "A-1a",
                    "name": "合同首页/签约方提取",
                    "duration_seconds": 0.12,
                    "token_usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
                }
            ],
        }
        data = review_contract(request, check_time="2026-07-07T10:00:00")

    assert data.metrics[0].id == "A-1a"
    assert data.metrics[0].token_usage.total_tokens == 12


def test_review_contract_does_not_call_real_llm_in_unit_test():
    request = ContractReviewRequest(contract_md="# 合同", attachments=[])
    with patch("app.capabilities.contract_review.service.invoke_model") as fake_invoke:
        with patch("app.capabilities.contract_review.service.run_review_pipeline", return_value=[]):
            review_contract(request, check_time="2026-07-07T10:00:00")
    fake_invoke.assert_not_called()


def test_review_contract_converts_context_length_error_to_blocking_check():
    request = ContractReviewRequest(contract_md="# 合同", attachments=[])
    with patch(
        "app.capabilities.contract_review.service.run_review_pipeline",
        side_effect=ModelInputTooLongError("B-1-附件一内容过长，超过模型单次处理长度限制，请拆分该部分内容或减少单次上传内容后重试"),
    ):
        data = review_contract(request, check_time="2026-07-21T10:00:00")

    assert data.overall_result == "BLOCK"
    assert len(data.checks) == 1
    assert data.checks[0].id == "模型上下文长度"
    assert data.checks[0].block_level == "硬阻断"
    assert "B-1-附件一内容过长" in (data.checks[0].reason or "")


def test_review_contract_converts_output_length_error_to_blocking_check():
    request = ContractReviewRequest(contract_md="# 合同", attachments=[])
    with patch(
        "app.capabilities.contract_review.service.run_review_pipeline",
        side_effect=ModelOutputTooLongError("B-4-附件一模型输出达到长度上限，结果被截断，请缩小检查范围或拆分内容后重试"),
    ):
        data = review_contract(request, check_time="2026-07-21T10:00:00")

    assert data.overall_result == "BLOCK"
    assert len(data.checks) == 1
    assert data.checks[0].id == "模型输出长度"
    assert data.checks[0].block_level == "硬阻断"
    assert "模型输出达到长度上限" in (data.checks[0].reason or "")


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
    assert "full_text_and_attachments" not in prepared


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


def test_run_review_pipeline_runs_b1_by_contract_and_each_attachment():
    request = ContractReviewRequest(
        contract_md="# 合同\n甲方：客户公司\n乙方：我方公司\n\n附件一\n内嵌附件内容",
        attachments=[AttachmentInput(index=2, filename="上传附件.md", text="上传附件内容")],
    )
    outputs = [
        '{"header":{"contract_name":"测试合同","project_name":null,"project_number":null,"contract_number":"HT-1","signing_location":"沈阳","signing_date":"2026年7月8日","parties":[{"role":"甲方","name":"客户公司"},{"role":"乙方","name":"我方公司"}]},"signature_parties":[{"role":"甲方","name":"客户公司"},{"role":"乙方","name":"我方公司"}],"sections":[]}',
        '{"signature":{"role":"乙方","name":"我方公司","legal_rep_name":"张三","signing_date":"2026年7月8日","bank_name":"招商银行","bank_account":"123456","account_holder":"我方公司","address":"地址","phone":"024-12345678","fax":"","website":"","postal_code":"110000"}}',
        '{"currency":"人民币","payment_method":"电汇","total_amount_numeric":"100","total_amount_uppercase":"壹佰元整","total_amount_match":true,"payment_stages":[]}',
        '{"copies":{"total_copies":2,"party_copies":[{"role":"甲方","copies":1},{"role":"乙方","copies":1}]},"attachments_declared":[{"index":1,"title":"附件一","content_embedded_in_contract":false},{"index":2,"title":"上传附件","content_embedded_in_contract":false}],"total_declared":2}',
        '{"checks":[]}',
        '{"checks":[]}',
        '{"checks":[]}',
        '{"checks":[]}',
        '{"checks":[]}',
    ]
    b1_prompts = []

    def fake_invoke(model, messages, response_format=None):
        content = messages[-1].content
        if "【当前检查范围】" in content:
            b1_prompts.append(content)
        return outputs.pop(0), {
            "prompt_tokens": 10,
            "completion_tokens": 1,
            "total_tokens": 11,
        }

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
                result = run_review_pipeline(request)

    assert len(b1_prompts) == 3
    assert "合同正文" in b1_prompts[0]
    assert "内嵌附件内容" not in b1_prompts[0]
    assert "附件一" in b1_prompts[1]
    assert "上传附件.md" in b1_prompts[2]
    b1_metric = next(metric for metric in result["metrics"] if metric.id == "B-1")
    assert [segment.id for segment in b1_metric.segments] == ["B-1-合同正文", "B-1-附件一", "B-1-上传附件.md"]
    assert b1_metric.token_usage.total_tokens == 33


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


def test_invoke_json_prompt_converts_context_length_error_with_label():
    def fake_invoke(model, messages, response_format=None):
        raise Exception(
            "Error code: 400 - You passed 16385 input tokens. "
            "However, the model's context length is only 16384 tokens."
        )

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            with pytest.raises(ModelFormatError) as exc:
                _invoke_json_prompt(
                    "b1_appellation",
                    validation_label="B-1-附件一",
                    parties=[],
                    scope_label="附件一",
                    segment_text="很长的附件",
                )

    assert "B-1-附件一内容过长" in str(exc.value)
    assert "超过模型单次处理长度限制" in str(exc.value)


def test_invoke_json_prompt_converts_tokens_limit_reached_error_with_label():
    def fake_invoke(model, messages, response_format=None):
        raise Exception('{"error":{"code":"tokens_limit_reached","message":"input too long"}}')

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            with pytest.raises(ModelFormatError) as exc:
                _invoke_json_prompt(
                    "b1_appellation",
                    validation_label="B-1-附件二",
                    parties=[],
                    scope_label="附件二",
                    segment_text="很长的附件",
                )

    assert "B-1-附件二内容过长" in str(exc.value)
    assert "超过模型单次处理长度限制" in str(exc.value)


def test_invoke_json_prompt_converts_length_finish_reason_error_with_label():
    def fake_invoke(model, messages, response_format=None):
        raise Exception(
            "openai.LengthFinishReasonError: Could not parse response content as the length limit was reached "
            "- CompletionUsage(completion_tokens=15496, prompt_tokens=888, total_tokens=16384)"
        )

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            with pytest.raises(ModelFormatError) as exc:
                _invoke_json_prompt(
                    "b1_appellation",
                    validation_label="B-1-附件三",
                    parties=[],
                    scope_label="附件三",
                    segment_text="很长的附件",
                )

    assert "B-1-附件三模型输出达到长度上限" in str(exc.value)
    assert "结果被截断" in str(exc.value)


def test_parse_model_checks_normalizes_block_level_wu_by_result():
    payload = {
        "checks": [
            {"result": "WARN", "block_level": "无", "reason": "称谓存在不一致"},
            {"result": "FAIL", "block_level": "无", "reason": "存在冲突"},
            {"result": "NA", "block_level": "无", "reason": "无附件"},
        ]
    }

    items = _parse_model_checks(payload, "B-1", "称谓一致性")

    assert [item.block_level for item in items] == ["提示", "硬阻断", "不适用"]


def test_parse_model_checks_normalizes_chinese_result_and_english_block_level():
    payload = {
        "checks": [
            {"result": "通过", "block_level": "pass", "reason": None},
        ]
    }

    items = _parse_model_checks(payload, "B-4", "附件内容一致性")

    assert items[0].result == "PASS"
    assert items[0].block_level == "通过"


def test_log_llm_trace_filters_by_prompt(monkeypatch, caplog):
    monkeypatch.setenv("LTC_ENV", "dev")
    monkeypatch.setenv("LTC__DEBUG__LLM_TRACE", "true")
    monkeypatch.setenv("LTC__DEBUG__LLM_TRACE_PROMPTS", '["b4_attachment_content"]')
    _reset_settings()

    caplog.clear()
    caplog.set_level("INFO", logger="contract_review")

    _log_llm_trace("invoke_json_prompt_response", prompt_name="b1_appellation", label="B-1")
    _log_llm_trace("invoke_json_prompt_response", prompt_name="b4_attachment_content", label="B-4")

    logs = [record.message for record in caplog.records if record.name == "contract_review"]
    assert logs.count("contract review llm trace") == 1


def test_invoke_json_prompt_logs_invoke_error_event(monkeypatch, caplog):
    monkeypatch.setenv("LTC_ENV", "dev")
    monkeypatch.setenv("LTC__DEBUG__LLM_TRACE", "true")
    _reset_settings()

    caplog.clear()
    caplog.set_level("INFO", logger="contract_review")

    def fake_invoke(model, messages, response_format=None):
        raise Exception(
            "openai.LengthFinishReasonError: Could not parse response content as the length limit was reached "
            "- CompletionUsage(completion_tokens=15496, prompt_tokens=888, total_tokens=16384)"
        )

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            with pytest.raises(ModelFormatError):
                _invoke_json_prompt(
                    "b4_attachment_content",
                    validation_label="B-4-附件一",
                    baseline={"header": {}, "signature": {}, "preset": None},
                    attachment_text="附件内容",
                )

    payloads = [record.__dict__.get("payload", {}) for record in caplog.records if record.name == "contract_review"]
    invoke_error = next(payload for payload in payloads if payload.get("event") == "invoke_json_prompt_invoke_error")
    assert invoke_error.get("length_issue") == "output"


def test_run_b1_retries_when_reason_is_too_generic():
    outputs = [
        '{"checks":[{"result":"WARN","block_level":"提示","reason":"称谓存在不一致"}]}',
        '{"checks":[{"result":"WARN","block_level":"提示","reason":"乙方称谓不一致：合同首部为“供应商（乙方）”，正文第3条使用“卖方”，请业务确认是否均指同一主体。"}]}',
    ]

    def fake_invoke(model, messages, response_format=None):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke) as mocked:
            items = _run_b1("合同正文", [], [], [])

    assert mocked.call_count == 2
    assert items[0].result == "WARN"
    assert "乙方称谓不一致" in items[0].reason
    assert "供应商（乙方）" in items[0].reason


def test_run_b1_adds_scope_prefix_and_segment_name():
    outputs = [
        '{"checks":[{"result":"WARN","block_level":"提示","reason":"乙方称谓不一致：合同首部为供应商（乙方），正文第3条使用卖方。"}]}',
    ]

    def fake_invoke(model, messages, response_format=None):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            items = _run_b1("合同正文", [], [], [])

    assert len(items) == 1
    assert items[0].name == "称谓一致性-合同正文"
    assert (items[0].reason or "").startswith("合同正文中：")


def test_run_b1_deduplicates_same_reason_items():
    outputs = [
        '{"checks":['
        '{"result":"WARN","block_level":"提示","reason":"乙方称谓不一致：合同首部为供应商（乙方），正文第3条使用卖方。"},'
        '{"result":"WARN","block_level":"提示","reason":"乙方称谓不一致：合同首部为供应商（乙方），正文第3条使用卖方。"}'
        ']}'
    ]

    def fake_invoke(model, messages, response_format=None):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            items = _run_b1("合同正文", [], [], [])

    assert len(items) == 1
    assert items[0].result == "WARN"


def test_run_b1_normalizes_legacy_scope_prefix_to_natural_language():
    outputs = [
        '{"checks":[{"result":"WARN","block_level":"\u63d0\u793a","reason":"\u3010\u8303\u56f4\u3011\u5408\u540c\u6b63\u6587\u3010\u4e3b\u4f53\u3011\u4e59\u65b9\u3010\u57fa\u51c6\u79f0\u8c13\u3011\u4f9b\u5e94\u5546\uff08\u4e59\u65b9\uff09\u3010\u53d1\u73b0\u79f0\u8c13\u3011\u5356\u65b9\u3010\u8bc1\u636e\u3011\u7b2c3\u6761\u4f7f\u7528\u5356\u65b9\u3002"}]}'
    ]

    def fake_invoke(model, messages, response_format=None):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            items = _run_b1("\u5408\u540c\u6b63\u6587", [], [], [])

    assert (items[0].reason or "").startswith("\u5408\u540c\u6b63\u6587\u4e2d\uff1a")
    assert "\u3010\u4e3b\u4f53\u3011" not in (items[0].reason or "")


def test_run_b1_filters_generic_document_nouns_as_noise():
    outputs = [
        '{"checks":[{"result":"WARN","block_level":"提示","reason":"合同正文中：乙方【基准称谓】乙方【发现称谓】本合同【证据】第10条出现本合同项下责任。"}]}'
    ]

    def fake_invoke(model, messages, response_format=None):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            items = _run_b1("合同正文", [], [], [])

    assert len(items) == 1
    assert items[0].result == "PASS"


def test_run_b1_reason_is_truncated_to_max_length():
    long_reason = "乙方称谓不一致：" + ("证据" * 200)
    outputs = [
        f'{{"checks":[{{"result":"WARN","block_level":"提示","reason":"{long_reason}"}}]}}'
    ]

    def fake_invoke(model, messages, response_format=None):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            items = _run_b1("合同正文", [], [], [])

    assert len(items) == 1
    assert items[0].result == "WARN"
    assert items[0].reason is not None
    assert len(items[0].reason) <= 160
    assert "…" in items[0].reason


def test_run_b1_converts_tagged_reason_to_natural_language_sentence():
    outputs = [
        '{"checks":[{"result":"WARN","block_level":"提示","reason":"【范围】合同正文【主体】乙方【基准称谓】东软集团股份有限公司【发现称谓】中国移动北京公司【证据】合同名称中出现中国移动北京公司与东软集团股份有限公司采购合同。"}]}'
    ]

    def fake_invoke(model, messages, response_format=None):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            items = _run_b1("合同正文", [], [], [])

    assert len(items) == 1
    assert items[0].reason is not None
    assert items[0].reason.startswith("合同正文中：")
    assert "【基准称谓】" not in items[0].reason
    assert "【发现称谓】" not in items[0].reason
    assert "【证据】" not in items[0].reason


def test_invoke_json_prompt_logs_metadata_output_length(monkeypatch, caplog):
    monkeypatch.setenv("LTC__DEBUG__LLM_TRACE", "true")
    _reset_settings()

    caplog.clear()
    caplog.set_level("INFO", logger="contract_review")

    def fake_invoke(model, messages, response_format=None):
        raise ModelOutputTooLongError("finish_reason=length")

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            with pytest.raises(ModelOutputTooLongError):
                _invoke_json_prompt(
                    "a1a_party_extraction",
                    validation_label="A-1a",
                    full_text="contract",
                )

    payloads = [record.__dict__.get("payload", {}) for record in caplog.records if record.name == "contract_review"]
    invoke_error = next(payload for payload in payloads if payload.get("event") == "invoke_json_prompt_invoke_error")
    assert invoke_error.get("length_issue") == "output"


def test_b1_response_schema_requires_structured_evidence_observation():
    properties = RESPONSE_FORMATS["b1_appellation"]["json_schema"]["schema"]["properties"]["checks"]["items"]["properties"]

    assert {"role", "baseline_appellation", "found_appellation", "evidence_quote", "evidence_type"} <= set(properties)


def test_run_b1_warns_when_attachment_uses_party_role_without_definition():
    outputs = [
        '{"checks":[]}',
        '{"checks":[{"result":"WARN","block_level":"提示","role":"乙方","baseline_appellation":"中国移动通信集团北京有限公司","found_appellation":null,"evidence_quote":"乙方应按约定提供价格清单。","evidence_type":"role_without_definition"}]}',
    ]

    def fake_invoke(model, messages, response_format=None):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            items = _run_b1(
                "合同正文",
                [{"title": "附件1", "text": "乙方应按约定提供价格清单。"}],
                [{"role": "乙方", "name": "中国移动通信集团北京有限公司", "aliases": []}],
            )

    attachment_item = next(item for item in items if item.name == "称谓一致性-附件1")
    assert attachment_item.result == "WARN"
    assert "未明确对应主体" in (attachment_item.reason or "")


def test_run_b1_generates_warn_from_verified_structured_observation():
    outputs = [
        '{"checks":[{"result":"WARN","block_level":"提示","role":"乙方","baseline_appellation":"供应商","found_appellation":"卖方","evidence_quote":"卖方应在十日内交付。","evidence_type":"party_appellation"}]}',
    ]

    def fake_invoke(model, messages, response_format=None):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            items = _run_b1(
                "卖方应在十日内交付。",
                [],
                [{"role": "乙方", "name": "供应商", "aliases": []}],
            )

    assert items[0].result == "WARN"
    assert "发现“卖方”" in (items[0].reason or "")
    assert "证据“卖方应在十日内交付。”" in (items[0].reason or "")



def test_run_b1_ignores_contract_name_observation():
    outputs = [
        '{"checks":[{"result":"WARN","block_level":"提示","role":"甲方","baseline_appellation":"中国移动通信集团北京有限公司","found_appellation":"中国移动北京公司","evidence_quote":"合同名称：中国移动北京公司2024年项目合同","evidence_type":"contract_or_project_name"}]}',
    ]

    def fake_invoke(model, messages, response_format=None):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            items = _run_b1(
                "合同名称：中国移动北京公司2024年项目合同",
                [],
                [{"role": "甲方", "name": "中国移动通信集团北京有限公司", "aliases": []}],
            )

    assert items[0].result == "PASS"


def test_run_b1_ignores_cross_scope_evidence():
    outputs = [
        '{"checks":[{"result":"WARN","block_level":"提示","role":"甲方","baseline_appellation":"中国移动通信集团北京有限公司","found_appellation":"中国移动北京公司","evidence_quote":"合同名称：中国移动北京公司2024年项目合同","evidence_type":"party_appellation"}]}',
    ]

    def fake_invoke(model, messages, response_format=None):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            items = _run_b1(
                "鉴于条款仅引用既有项目。",
                [],
                [{"role": "甲方", "name": "中国移动通信集团北京有限公司", "aliases": []}],
            )

    assert items[0].result == "PASS"


def test_run_b1_accepts_alias_declared_in_header_party():
    outputs = [
        '{"checks":[{"result":"WARN","block_level":"提示","role":"甲方","baseline_appellation":"中国移动通信集团北京有限公司","found_appellation":"北京移动","evidence_quote":"北京移动应在验收后付款。","evidence_type":"party_appellation"}]}',
    ]

    def fake_invoke(model, messages, response_format=None):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            items = _run_b1(
                "北京移动应在验收后付款。",
                [],
                [{"role": "甲方", "name": "中国移动通信集团北京有限公司", "aliases": ["北京移动"]}],
            )

    assert items[0].result == "PASS"


def test_b4_response_schema_keeps_reason_check_item():
    properties = RESPONSE_FORMATS["b4_attachment_content"]["json_schema"]["schema"]["properties"]["checks"]["items"]["properties"]

    assert "reason" in properties
    assert "evidence_type" not in properties


def test_b1_response_schema_supports_attachment_definition_evidence_types():
    evidence_type = RESPONSE_FORMATS["b1_appellation"]["json_schema"]["schema"]["properties"]["checks"]["items"]["properties"]["evidence_type"]

    assert {"party_definition", "role_without_definition"} <= set(evidence_type["enum"])


def test_run_b1_warns_when_attachment_party_definition_differs_from_contract():
    outputs = [
        '{"checks":[]}',
        '{"checks":[{"result":"WARN","block_level":"提示","role":"乙方","baseline_appellation":"中国移动通信集团北京有限公司","found_appellation":"中国移动北京公司","evidence_quote":"乙方：中国移动北京公司","evidence_type":"party_definition"}]}',
    ]

    def fake_invoke(model, messages, response_format=None):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            items = _run_b1(
                "合同正文",
                [{"title": "附件1", "text": "乙方：中国移动北京公司"}],
                [{"role": "乙方", "name": "中国移动通信集团北京有限公司", "aliases": []}],
            )

    attachment_item = next(item for item in items if item.name == "称谓一致性-附件1")
    assert attachment_item.result == "WARN"
    assert "发现“中国移动北京公司”" in (attachment_item.reason or "")


def test_run_b1_passes_when_attachment_party_definition_matches_declared_alias():
    outputs = [
        '{"checks":[]}',
        '{"checks":[{"result":"WARN","block_level":"提示","role":"乙方","baseline_appellation":"中国移动通信集团北京有限公司","found_appellation":"北京移动","evidence_quote":"乙方：北京移动","evidence_type":"party_definition"}]}',
    ]

    def fake_invoke(model, messages, response_format=None):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            items = _run_b1(
                "合同正文",
                [{"title": "附件1", "text": "乙方：北京移动"}],
                [{"role": "乙方", "name": "中国移动通信集团北京有限公司", "aliases": ["北京移动"]}],
            )

    attachment_item = next(item for item in items if item.name == "称谓一致性-附件1")
    assert attachment_item.result == "PASS"


def test_run_b1_legacy_pass_without_reason_keeps_reason_none():
    outputs = [
        '{"checks":[{"result":"PASS","block_level":"通过","reason":null}]}',
    ]

    def fake_invoke(model, messages, response_format=None):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            items = _run_b1("合同正文", [], [])

    assert items[0].result == "PASS"
    assert items[0].reason is None

def test_a3_and_b4_response_schemas_require_amount_evidence():
    a3_properties = RESPONSE_FORMATS["a3_amount_payment"]["json_schema"]["schema"]["properties"]
    b4_item_properties = RESPONSE_FORMATS["b4_attachment_content"]["json_schema"]["schema"]["properties"]["checks"]["items"]["properties"]

    assert "total_amount_evidence" in a3_properties
    assert {"check_type", "attachment_value", "attachment_evidence"} <= set(b4_item_properties)


def test_b4_amount_mismatch_uses_verified_contract_and_attachment_evidence():
    outputs = [
        '{"checks":[{"result":"FAIL","block_level":"提示","check_type":"total_amount","attachment_value":3286000,"attachment_evidence":"附件含税总价为3286000元。","reason":null}]}'
    ]

    def fake_invoke(model, messages, response_format=None):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            items = _run_b4(
                [{"title": "附件1", "text": "附件含税总价为3286000元。"}],
                {"amount_payment": {"total_amount_numeric": 3350130, "total_amount_evidence": "本合同最终含税总价为3350130元。"}},
            )

    item = items[0]
    assert item.result == "FAIL"
    assert item.block_level == "硬阻断"
    assert "合同正文总价“3350130”" in (item.reason or "")
    assert "正文证据“本合同最终含税总价为3350130元。”" in (item.reason or "")
    assert "附件证据“附件含税总价为3286000元。”" in (item.reason or "")


def test_b4_ignores_amount_mismatch_without_current_attachment_evidence():
    outputs = [
        '{"checks":[{"result":"FAIL","block_level":"硬阻断","check_type":"total_amount","attachment_value":3286000,"attachment_evidence":"其他附件含税总价为3286000元。","reason":null}]}'
    ]

    def fake_invoke(model, messages, response_format=None):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            items = _run_b4(
                [{"title": "附件1", "text": "附件含税总价为3286000元。"}],
                {"amount_payment": {"total_amount_numeric": 3350130, "total_amount_evidence": "本合同最终含税总价为3350130元。"}},
            )

    assert items[0].result == "PASS"


def test_b4_normalizes_pass_block_level_from_result():
    outputs = ['{"checks":[{"result":"PASS","block_level":"硬阻断","check_type":"other","attachment_value":null,"attachment_evidence":null,"reason":"附件内容一致"}]}']

    def fake_invoke(model, messages, response_format=None):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            items = _run_b4([{"title": "附件3", "text": "保密条款"}], {})

    assert items[0].result == "PASS"
    assert items[0].block_level == "通过"

def test_b4_ignores_unstructured_amount_claim_without_evidence():
    outputs = ['{"checks":[{"result":"FAIL","block_level":"硬阻断","reason":"附件含税总价与合同正文金额不一致"}]}']

    def fake_invoke(model, messages, response_format=None):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            items = _run_b4([{"title": "附件1", "text": "附件价格清单"}], {})

    assert items[0].result == "PASS"


def test_run_review_pipeline_uses_attachment_title_matching_for_unresolved_filename():
    request = ContractReviewRequest(
        contract_md="# 合同\n甲方：客户公司\n乙方：我方公司",
        attachments=[AttachmentInput(index=1, filename="附件1：价格明细表2.11.md", text="附件内容")],
    )
    prompts = []
    responses = {
        "a1a_party_extraction": {
            "header": {
                "contract_name": "测试合同",
                "project_name": None,
                "project_number": None,
                "contract_number": "HT-1",
                "signing_location": "沈阳",
                "signing_date": "2026年7月8日",
                "parties": [{"role": "甲方", "name": "客户公司"}, {"role": "乙方", "name": "我方公司"}],
            },
            "signature_parties": [],
            "sections": [],
        },
        "a3_amount_payment": {
            "currency": "人民币",
            "payment_method": "电汇",
            "total_amount_numeric": "100",
            "total_amount_uppercase": "壹佰元整",
            "total_amount_match": True,
            "payment_stages": [],
        },
        "a4_copies_attachments": {
            "copies": {"total_copies": 2, "party_copies": []},
            "attachments_declared": [
                {"index": 1, "title": "价格明细表", "content_embedded_in_contract": False, "section_heading_hint": None}
            ],
            "total_declared": 1,
        },
        "attachment_title_matching": {
            "decisions": [
                {
                    "uploaded_id": "uploaded-0",
                    "declared_id": "declared-0",
                    "judgement": "MATCH",
                    "reason": "文件名中的版本号不改变附件标题含义",
                }
            ]
        },
    }

    def fake_prompt(prompt_name, **kwargs):
        prompts.append((prompt_name, kwargs))
        return responses[prompt_name]

    with patch("app.capabilities.contract_review.service._invoke_json_prompt", side_effect=fake_prompt):
        with patch("app.capabilities.contract_review.service.identify_our_party", return_value=(None, None)):
            with patch("app.capabilities.contract_review.service._run_b1", return_value=[]):
                with patch("app.capabilities.contract_review.service._run_b4", return_value=[]):
                    result = run_review_pipeline(request)

    attachment_item = next(item for item in result.items if item.id == "附件检查-数量标题")
    assert attachment_item.result == "PASS"
    matching_call = next(kwargs for name, kwargs in prompts if name == "attachment_title_matching")
    assert "价格明细表" in matching_call["declared_attachments"]
    assert "价格明细表2.11" in matching_call["uploaded_attachments"]


def test_run_review_pipeline_keeps_warn_when_attachment_title_matching_is_uncertain():
    request = ContractReviewRequest(
        contract_md="# 合同\n甲方：客户公司\n乙方：我方公司",
        attachments=[AttachmentInput(index=1, filename="附件1：技术协议补充协议.md", text="附件内容")],
    )
    responses = {
        "a1a_party_extraction": {
            "header": {
                "contract_name": "测试合同",
                "project_name": None,
                "project_number": None,
                "contract_number": "HT-1",
                "signing_location": "沈阳",
                "signing_date": "2026年7月8日",
                "parties": [{"role": "甲方", "name": "客户公司"}, {"role": "乙方", "name": "我方公司"}],
            },
            "signature_parties": [],
            "sections": [],
        },
        "a3_amount_payment": {
            "currency": "人民币",
            "payment_method": "电汇",
            "total_amount_numeric": "100",
            "total_amount_uppercase": "壹佰元整",
            "total_amount_match": True,
            "payment_stages": [],
        },
        "a4_copies_attachments": {
            "copies": {"total_copies": 2, "party_copies": []},
            "attachments_declared": [
                {"index": 1, "title": "技术协议", "content_embedded_in_contract": False, "section_heading_hint": None}
            ],
            "total_declared": 1,
        },
        "attachment_title_matching": {
            "decisions": [
                {
                    "uploaded_id": "uploaded-0",
                    "declared_id": "declared-0",
                    "judgement": "UNCERTAIN",
                    "reason": "无法仅根据名称确认是否为补充协议",
                }
            ]
        },
    }

    def fake_prompt(prompt_name, **kwargs):
        return responses[prompt_name]

    with patch("app.capabilities.contract_review.service._invoke_json_prompt", side_effect=fake_prompt):
        with patch("app.capabilities.contract_review.service.identify_our_party", return_value=(None, None)):
            with patch("app.capabilities.contract_review.service._run_b1", return_value=[]):
                with patch("app.capabilities.contract_review.service._run_b4", return_value=[]):
                    result = run_review_pipeline(request)

    attachment_item = next(item for item in result.items if item.id == "附件检查-数量标题")
    assert attachment_item.result == "WARN"
    assert "业务确认" in (attachment_item.reason or "")

def test_run_review_pipeline_skips_attachment_title_matching_for_normalized_exact_title():
    request = ContractReviewRequest(
        contract_md="# 合同\n甲方：客户公司\n乙方：我方公司",
        attachments=[AttachmentInput(index=1, filename="附件1：价格明细表.md", text="附件内容")],
    )
    prompts = []
    responses = {
        "a1a_party_extraction": {
            "header": {
                "contract_name": "测试合同",
                "project_name": None,
                "project_number": None,
                "contract_number": "HT-1",
                "signing_location": "沈阳",
                "signing_date": "2026年7月8日",
                "parties": [{"role": "甲方", "name": "客户公司"}, {"role": "乙方", "name": "我方公司"}],
            },
            "signature_parties": [],
            "sections": [],
        },
        "a3_amount_payment": {
            "currency": "人民币",
            "payment_method": "电汇",
            "total_amount_numeric": "100",
            "total_amount_uppercase": "壹佰元整",
            "total_amount_match": True,
            "payment_stages": [],
        },
        "a4_copies_attachments": {
            "copies": {"total_copies": 2, "party_copies": []},
            "attachments_declared": [
                {"index": 1, "title": "价格明细表", "content_embedded_in_contract": False, "section_heading_hint": None}
            ],
            "total_declared": 1,
        },
    }

    def fake_prompt(prompt_name, **kwargs):
        prompts.append(prompt_name)
        return responses[prompt_name]

    with patch("app.capabilities.contract_review.service._invoke_json_prompt", side_effect=fake_prompt):
        with patch("app.capabilities.contract_review.service.identify_our_party", return_value=(None, None)):
            with patch("app.capabilities.contract_review.service._run_b1", return_value=[]):
                with patch("app.capabilities.contract_review.service._run_b4", return_value=[]):
                    result = run_review_pipeline(request)

    attachment_item = next(item for item in result.items if item.id == "附件检查-数量标题")
    assert attachment_item.result == "PASS"
    assert "attachment_title_matching" not in prompts
