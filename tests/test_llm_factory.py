from unittest.mock import MagicMock, patch

import pytest

from app.core.errors import ModelTimeoutError
from app.models import llm


def test_get_chat_model_returns_base_chat_model(monkeypatch):
    monkeypatch.setenv("LTC__LLM__API_KEY", "env-llm-key")
    with patch("app.models.llm.ChatOpenAI") as mock_cls:
        mock_cls.return_value = MagicMock(name="model")
        m = llm.get_chat_model()
        assert m is mock_cls.return_value
        kwargs = mock_cls.call_args.kwargs
        assert kwargs["model"]  # 来自配置
        assert kwargs["base_url"] == "http://192.168.16.10:8080/v1"
        assert kwargs["api_key"] == "env-llm-key"


def test_invoke_model_returns_content_and_tokens():
    fake_ai = MagicMock()
    fake_ai.content = "Hello"
    fake_ai.usage_metadata = {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}
    fake_model = MagicMock()
    fake_model.invoke.return_value = fake_ai

    content, usage = llm.invoke_model(fake_model, [MagicMock()])
    assert content == "Hello"
    assert usage == {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}


def test_invoke_model_passes_response_format_to_model():
    fake_ai = MagicMock()
    fake_ai.content = '{"ok": true}'
    fake_ai.usage_metadata = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
    fake_model = MagicMock()
    fake_model.invoke.return_value = fake_ai
    response_format = {"type": "json_schema", "json_schema": {"name": "ok_schema"}}

    content, usage = llm.invoke_model(fake_model, [MagicMock()], response_format=response_format)

    assert content == '{"ok": true}'
    assert usage["total_tokens"] == 2
    fake_model.invoke.assert_called_once()
    assert fake_model.invoke.call_args.kwargs["response_format"] == response_format


def test_invoke_model_missing_usage_defaults_zero():
    fake_ai = MagicMock()
    fake_ai.content = "Hello"
    fake_ai.usage_metadata = None
    fake_model = MagicMock()
    fake_model.invoke.return_value = fake_ai

    content, usage = llm.invoke_model(fake_model, [MagicMock()])
    assert content == "Hello"
    assert usage == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def test_invoke_model_timeout_raises_model_timeout_error():
    fake_model = MagicMock()
    fake_model.invoke.side_effect = TimeoutError("read timed out")
    with pytest.raises(ModelTimeoutError):
        llm.invoke_model(fake_model, [MagicMock()])


def test_invoke_model_other_error_reraises():
    fake_model = MagicMock()
    fake_model.invoke.side_effect = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        llm.invoke_model(fake_model, [MagicMock()])
