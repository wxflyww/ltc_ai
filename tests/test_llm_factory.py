from unittest.mock import MagicMock, patch

import pytest

from app.core.errors import ModelTimeoutError
from app.models import llm


def test_get_chat_model_returns_base_chat_model():
    with patch("app.models.llm.ChatOpenAI") as mock_cls:
        mock_cls.return_value = MagicMock(name="model")
        m = llm.get_chat_model()
        assert m is mock_cls.return_value
        kwargs = mock_cls.call_args.kwargs
        assert kwargs["model"]  # 来自配置
        assert kwargs["base_url"] == "http://vllm-dev.internal:8000/v1"


def test_invoke_model_returns_content_and_tokens():
    fake_ai = MagicMock()
    fake_ai.content = "Hello"
    fake_ai.usage_metadata = {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}
    fake_model = MagicMock()
    fake_model.invoke.return_value = fake_ai

    content, usage = llm.invoke_model(fake_model, [MagicMock()])
    assert content == "Hello"
    assert usage == {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}


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
