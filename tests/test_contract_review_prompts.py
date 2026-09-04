from langchain_core.messages import HumanMessage, SystemMessage
import pytest

from app.capabilities.contract_review.prompts import build_prompt, parse_json_object
from app.capabilities.contract_review.response_formats import get_response_format
from app.core.errors import ModelFormatError


def test_build_prompt_returns_system_and_human_messages():
    messages = build_prompt("a1a_party_extraction", full_text="合同正文")
    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], HumanMessage)
    assert "合同正文" in messages[1].content


def test_a1a_prompt_requires_project_name():
    messages = build_prompt("a1a_party_extraction", full_text="合同正文")
    assert "project_name" in messages[1].content


def test_a1a_prompt_distinguishes_contract_number_and_project_number():
    messages = build_prompt("a1a_party_extraction", full_text="合同编号：\n项目编号：P-1")
    content = "\n".join(message.content for message in messages)
    assert "project_number" in content
    assert "项目编号不能填入contract_number" in content
    assert "合同编号”标签存在但后面为空" in content


def test_parse_json_object_accepts_plain_json():
    assert parse_json_object('{"x": 1}') == {"x": 1}


def test_parse_json_object_accepts_fenced_json():
    assert parse_json_object('```json\n{"x": 1}\n```') == {"x": 1}


def test_parse_json_object_extracts_json_from_explanatory_text():
    content = '好的，以下是JSON：\n{"x": 1, "nested": {"y": 2}}\n请查收。'
    assert parse_json_object(content) == {"x": 1, "nested": {"y": 2}}


def test_parse_json_object_removes_think_block_before_extracting_json():
    content = '<think>先分析合同结构</think>\n{"x": 1}'
    assert parse_json_object(content) == {"x": 1}


def test_parse_json_object_raises_for_text_without_json_object():
    with pytest.raises(ModelFormatError):
        parse_json_object("根据合同内容，未发现可提取信息。")

def test_a3_prompt_includes_total_amount_and_evidence_example():
    messages = build_prompt("a3_amount_payment", full_text="合同最终含税总价为100元。")
    content = messages[1].content

    assert '"total_amount_numeric": "100"' in content
    assert '"total_amount_evidence": "本合同最终含税总价为100元（大写：壹佰元整）。"' in content


def test_a3_prompt_and_schema_declare_amount_pairs():
    messages = build_prompt("a3_amount_payment", full_text="合同最终含税总价为100元。")
    content = messages[1].content

    assert '"amount_pairs"' in content
    assert "不含税" in content and "含税" in content

    schema = get_response_format("a3_amount_payment")["json_schema"]["schema"]
    properties = schema["properties"]
    assert "amount_pairs" in properties
    assert "amount_pairs" in schema["required"]
    assert "contract_overall_evidence" in properties
    assert "contract_overall_evidence" in schema["required"]
    assert "total_amount_match" in properties
    pair_properties = properties["amount_pairs"]["items"]["properties"]
    assert {"label", "amount_numeric", "amount_uppercase"} <= set(pair_properties)


def test_a3_prompt_forbids_derived_amounts_and_uppercase_generation():
    messages = build_prompt(
        "a3_amount_payment",
        full_text="总价10492500.00元，付款比例50%、40%、10%。",
    )
    content = "\n".join(message.content for message in messages)

    assert "只摘录合同原文明确出现的金额" in content
    assert "禁止根据总价、付款比例或其他金额计算" in content
    assert "禁止根据数字金额生成中文大写" in content
    assert "amount_numeric、amount_uppercase、amount_evidence 必须返回 null" in content


def test_a3_payment_stage_schema_declares_nullable_amount_evidence():
    schema = get_response_format("a3_amount_payment")["json_schema"]["schema"]
    properties = schema["properties"]
    stage_schema = properties["payment_stages"]["items"]
    stage_properties = stage_schema["properties"]

    assert "amount_evidence" in stage_properties
    assert stage_properties["amount_evidence"]["type"] == ["string", "null"]
    assert "amount_evidence" in stage_schema["required"]
    assert "total_amount_evidence" in properties
    assert "contract_overall_evidence" in properties
    assert "amount_pairs" in properties
    assert "total_amount_match" in properties


def test_a3_prompt_uses_bounded_evidence_and_no_table_row_recovery_rule():
    messages = build_prompt(
        "a3_amount_payment",
        full_text="| 2.1合同总金额为￥ | 4690000元 | （含6%增值税），人民币（大写） | 肆佰陆拾玖万元整。 |",
    )
    content = "\n".join(message.content for message in messages)

    assert "contract_overall_evidence" in content
    assert "有界片段" in content
    assert "一次自然换行" in content
    assert "谈判含税报价" in content
    assert "amount_evidence" in content
    assert "不得填写该字段" in content
    assert "不得根据中文大写反推数字金额" in content
    assert "单元格" not in content
    assert "同一表格行" not in content
    assert "禁止根据数字金额生成中文大写" in content


def test_attachment_title_matching_prompt_and_schema_use_three_state_decision():
    messages = build_prompt(
        "attachment_title_matching",
        declared_attachments='[{"id":"declared-0","title":"价格明细表"}]',
        uploaded_attachments='[{"id":"uploaded-0","filename":"价格明细表2.11.md"}]',
    )
    content = messages[1].content
    schema = get_response_format("attachment_title_matching")["json_schema"]["schema"]
    decision = schema["properties"]["decisions"]["items"]

    assert "UNCERTAIN" in content
    assert "价格明细表2.11.md" in content
    assert decision["properties"]["judgement"]["enum"] == ["MATCH", "MISMATCH", "UNCERTAIN"]
