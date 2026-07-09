from langchain_core.messages import HumanMessage, SystemMessage
import pytest

from app.capabilities.contract_review.prompts import build_prompt, parse_json_object
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
    content = messages[1].content
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
