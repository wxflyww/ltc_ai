from unittest.mock import MagicMock, patch

import pytest

from app.core.errors import ModelFormatError, ModelInvocationError, ModelTimeoutError
from app.capabilities.translate.schemas import TranslateRequest
from app.capabilities.translate import service


def _ok_model(content="Hello", tokens=8):
    m = MagicMock()
    m.model_name = "qwen3.6-35b-a3b"
    m.invoke.return_value = MagicMock(
        content=content,
        usage_metadata={"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": tokens},
    )
    return m


def test_translate_success():
    req = TranslateRequest(text="你好", target_lang="en", source_lang="zh")
    with patch("app.capabilities.translate.service.get_chat_model", return_value=_ok_model("Hello")):
        data = service.translate(req, sleep_fn=lambda s: None)
    assert data.translated_text == "Hello"
    assert data.source_lang == "zh"
    assert data.model == "qwen3.6-35b-a3b"
    assert data.token_usage.total_tokens == 8


def test_translate_retries_on_timeout_then_succeeds():
    req = TranslateRequest(text="你好", target_lang="en")
    m = _ok_model("Hello")
    m.invoke.side_effect = [TimeoutError("t"), m.invoke.return_value]
    calls = {"n": 0}

    def fake_sleep(s):
        calls["n"] += 1

    with patch("app.capabilities.translate.service.get_chat_model", return_value=m):
        data = service.translate(req, sleep_fn=fake_sleep)
    assert data.translated_text == "Hello"
    assert m.invoke.call_count == 2  # 1 失败 + 1 成功
    assert calls["n"] == 1  # 重试间睡了一次


def test_translate_exhausts_retries_and_raises_invocation_error():
    req = TranslateRequest(text="你好", target_lang="en")
    m = MagicMock()
    m.model_name = "qwen3.6-35b-a3b"
    m.invoke.side_effect = TimeoutError("t")
    with patch("app.capabilities.translate.service.get_chat_model", return_value=m):
        with pytest.raises(ModelInvocationError):
            service.translate(req, sleep_fn=lambda s: None)
    assert m.invoke.call_count == 3  # 1 初始 + 2 重试


def test_translate_does_not_retry_on_format_error():
    req = TranslateRequest(text="你好", target_lang="en")
    m = MagicMock()
    m.model_name = "qwen3.6-35b-a3b"
    # invoke 返回空内容 → ModelFormatError，不重试
    m.invoke.return_value = MagicMock(content="", usage_metadata=None)
    with patch("app.capabilities.translate.service.get_chat_model", return_value=m):
        with pytest.raises(ModelFormatError):
            service.translate(req, sleep_fn=lambda s: None)
    assert m.invoke.call_count == 1


def test_translate_retries_on_http_500(monkeypatch):
    """模拟 5xx：用一个带 status_code=500 属性的异常对象，由 service 的可重试判定识别。"""
    req = TranslateRequest(text="你好", target_lang="en")

    class Fake500(Exception):
        status_code = 500

    class _Resp:
        content = "Hello"
        usage_metadata = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}

    m = MagicMock()
    m.model_name = "qwen3.6-35b-a3b"
    m.invoke.side_effect = [Fake500("server error"), _Resp()]
    with patch("app.capabilities.translate.service.get_chat_model", return_value=m):
        data = service.translate(req, sleep_fn=lambda s: None)
    assert data.translated_text == "Hello"
    assert m.invoke.call_count == 2
