from app.capabilities.translate.schemas import TranslateRequest, TranslateData
from app.capabilities.translate.prompts import build_translate_prompt


def test_translate_request_required_fields():
    req = TranslateRequest(text="你好", target_lang="en")
    assert req.text == "你好"
    assert req.target_lang == "en"
    assert req.source_lang is None


def test_translate_data():
    d = TranslateData(translated_text="Hello", source_lang="zh", model="qwen3.6", token_usage={"total_tokens": 1})
    assert d.translated_text == "Hello"


def test_build_prompt_with_source_lang():
    msgs = build_translate_prompt("你好", "en", source_lang="zh")
    texts = [m.content for m in msgs]
    joined = " ".join(texts)
    assert "zh" in joined
    assert "en" in joined
    assert "你好" in joined


def test_build_prompt_without_source_lang():
    msgs = build_translate_prompt("你好", "en", source_lang=None)
    assert len(msgs) >= 1
