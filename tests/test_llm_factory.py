from unittest.mock import MagicMock, patch

import pytest

from app.core.errors import ModelOutputTooLongError, ModelTimeoutError
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
    """LangChain usage_metadata uses input_tokens/output_tokens keys."""
    fake_ai = MagicMock()
    fake_ai.content = "Hello"
    fake_ai.usage_metadata = {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8}
    fake_model = MagicMock()
    fake_model.invoke.return_value = fake_ai

    content, usage = llm.invoke_model(fake_model, [MagicMock()])
    assert content == "Hello"
    assert usage == {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}


def test_invoke_model_falls_back_to_legacy_token_keys():
    """Backward compat: some providers return prompt_tokens/completion_tokens."""
    fake_ai = MagicMock()
    fake_ai.content = "Hi"
    fake_ai.usage_metadata = {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9}
    fake_model = MagicMock()
    fake_model.invoke.return_value = fake_ai

    content, usage = llm.invoke_model(fake_model, [MagicMock()])
    assert usage == {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9}


def test_invoke_model_passes_response_format_to_model():
    fake_ai = MagicMock()
    fake_ai.content = '{"ok": true}'
    fake_ai.usage_metadata = {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}
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


def test_get_chat_model_disables_sdk_hidden_retries(monkeypatch):
    """max_retries=0：禁止 openai SDK 对读超时静默重试（否则 timeout×3）。"""
    monkeypatch.setenv("LTC__LLM__API_KEY", "env-llm-key")
    with patch("app.models.llm.ChatOpenAI") as mock_cls:
        mock_cls.return_value = MagicMock(name="model")
        llm.get_chat_model()
        assert mock_cls.call_args.kwargs["max_retries"] == 0


def _httpx_request():
    import httpx

    return httpx.Request("POST", "http://192.168.16.10:8080/v1/chat/completions")


def _api_timeout_error():
    from openai import APITimeoutError

    return APITimeoutError(request=_httpx_request())


def test_langchain_openai_timeout_error_capture_surface():
    """若环境的 langchain-openai 提供 OpenAITimeoutError，必须落在捕获面内。

    本地 venv（langchain-openai 1.3.3）没有这个类（超时直接抛 openai.APITimeoutError）；
    容器（1.6.2）有，且继承 openai.APITimeoutError，故 `except (TimeoutError, APITimeoutError)`
    能覆盖两条路径。
    """
    import importlib

    from openai import APITimeoutError

    module = importlib.import_module("langchain_openai.chat_models.base")
    cls = getattr(module, "OpenAITimeoutError", None)
    if cls is None:
        pytest.skip("当前 langchain-openai 无 OpenAITimeoutError（1.3.3 环境）")
    assert issubclass(cls, APITimeoutError)


def test_invoke_model_wrapped_timeout_raises_model_timeout_error():
    """langchain-openai 包装后的超时（APITimeoutError 子类）同样要转成 ModelTimeoutError。"""
    from openai import APITimeoutError

    class _WrappedTimeout(APITimeoutError):  # 模拟 langchain_openai.OpenAITimeoutError
        pass

    fake_model = MagicMock()
    fake_model.invoke.side_effect = _WrappedTimeout(
        request=_httpx_request()
    )
    with pytest.raises(ModelTimeoutError):
        llm.invoke_model(fake_model, [MagicMock()])


def test_invoke_model_api_timeout_raises_model_timeout_error():
    """SDK 读超时（非内置 TimeoutError）必须转成 ModelTimeoutError → 20002/504。"""
    fake_model = MagicMock()
    fake_model.invoke.side_effect = _api_timeout_error()
    with pytest.raises(ModelTimeoutError):
        llm.invoke_model(fake_model, [MagicMock()])


def test_invoke_model_other_error_reraises():
    fake_model = MagicMock()
    fake_model.invoke.side_effect = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        llm.invoke_model(fake_model, [MagicMock()])


def test_invoke_model_raises_output_length_error_when_finish_reason_is_length():
    fake_ai = MagicMock()
    fake_ai.content = '{"checks": []}'
    fake_ai.usage_metadata = {"input_tokens": 1, "output_tokens": 8, "total_tokens": 9}
    fake_ai.response_metadata = {"finish_reason": "length"}
    fake_model = MagicMock()
    fake_model.invoke.return_value = fake_ai

    with pytest.raises(ModelOutputTooLongError):
        llm.invoke_model(fake_model, [MagicMock()])
