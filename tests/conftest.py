import pytest

from app.core.config import _reset_settings
from app.models.llm import _reset_chat_model


@pytest.fixture(autouse=True)
def reset_singletons(monkeypatch):
    """每个测试前重置配置/模型单例，默认 dev 环境。"""
    monkeypatch.setenv("LTC_ENV", "dev")
    _reset_settings()
    _reset_chat_model()
    yield
    _reset_settings()
    _reset_chat_model()
