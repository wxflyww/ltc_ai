from langchain_core.messages import HumanMessage, SystemMessage

from app.capabilities.contract_review.prompts import build_prompt, parse_json_object


def test_build_prompt_returns_system_and_human_messages():
    messages = build_prompt("a1a_party_extraction", full_text="合同正文")
    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], HumanMessage)
    assert "合同正文" in messages[1].content


def test_parse_json_object_accepts_plain_json():
    assert parse_json_object('{"x": 1}') == {"x": 1}


def test_parse_json_object_accepts_fenced_json():
    assert parse_json_object('```json\n{"x": 1}\n```') == {"x": 1}
