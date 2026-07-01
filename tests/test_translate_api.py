from unittest.mock import patch

from fastapi.testclient import TestClient

from app.capabilities.translate.schemas import TranslateData, TokenUsage
from app.main import create_app


def _client():
    return TestClient(create_app(register_middleware=False))


def test_translate_success_contract():
    fake = TranslateData(
        translated_text="Hello", source_lang="zh", model="qwen3.6-35b-a3b",
        token_usage=TokenUsage(prompt_tokens=5, completion_tokens=3, total_tokens=8),
    )
    with patch("app.capabilities.translate.router.translate", return_value=fake):
        c = _client()
        r = c.post("/api/v1/translate", json={"text": "你好", "target_lang": "en"})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["translated_text"] == "Hello"
    assert body["data"]["model"] == "qwen3.6-35b-a3b"
    assert "traceId" in body  # 字段存在
    assert "duration_seconds" in body  # 顶层


def test_translate_validation_error_returns_10001():
    c = _client()
    r = c.post("/api/v1/translate", json={"target_lang": "en"})  # 缺 text
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == 10001
    assert "traceId" in body
    assert "duration_seconds" in body


def test_translate_model_failure_returns_20001():
    from app.core.errors import ModelInvocationError
    with patch(
        "app.capabilities.translate.router.translate",
        side_effect=ModelInvocationError("exhausted"),
    ):
        c = _client()
        r = c.post("/api/v1/translate", json={"text": "你好", "target_lang": "en"})
    assert r.status_code == 500
    body = r.json()
    assert body["code"] == 20001
    assert body["data"] is None
    assert "traceId" in body
