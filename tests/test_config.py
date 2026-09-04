import os

from app.core.config import get_settings, _reset_settings


def test_loads_default_then_env_override(tmp_path, monkeypatch):
    # 用临时 config 目录
    monkeypatch.setenv("LTC_ENV", "dev")
    _reset_settings()
    settings = get_settings()
    # 默认基线值
    assert settings.server.port == 8000
    assert settings.llm.temperature == 0.3
    # dev 覆盖
    assert settings.llm.base_url == "http://10.105.1.5:4000/v1"
    assert settings.llm.timeout == 3000
    # env 标记
    assert settings.app.env == "dev"


def test_env_var_overrides_yaml(monkeypatch):
    monkeypatch.setenv("LTC_ENV", "dev")
    monkeypatch.setenv("LTC__SERVER__PORT", "9999")
    monkeypatch.setenv("LTC__LLM__API_KEY", "env-llm-key")
    monkeypatch.setenv("LTC__AUTH__API_KEYS", '["k1","k2"]')
    _reset_settings()
    settings = get_settings()
    assert settings.server.port == 9999
    assert settings.llm.api_key == "env-llm-key"
    assert settings.auth.api_keys == ["k1", "k2"]


def test_debug_settings_from_env(monkeypatch):
    monkeypatch.setenv("LTC_ENV", "dev")
    monkeypatch.setenv("LTC__DEBUG__LLM_TRACE", "true")
    monkeypatch.setenv("LTC__DEBUG__LLM_TRACE_MAX_CHARS", "1234")
    monkeypatch.setenv("LTC__DEBUG__LLM_TRACE_PROMPTS", '["b4_attachment_content"]')
    monkeypatch.setenv("LTC__DEBUG__LLM_TRACE_WRITE_HTML", "false")
    monkeypatch.setenv("LTC__DEBUG__LLM_TRACE_OUTPUT_DIR", "tmp/custom-audit")
    _reset_settings()
    settings = get_settings()
    assert settings.debug.llm_trace is True
    assert settings.debug.llm_trace_max_chars == 1234
    assert settings.debug.llm_trace_prompts == ["b4_attachment_content"]
    assert settings.debug.llm_trace_write_html is False
    assert settings.debug.llm_trace_output_dir == "tmp/custom-audit"


def test_prod_env_uses_prod_yaml(monkeypatch):
    monkeypatch.setenv("LTC_ENV", "prod")
    _reset_settings()
    settings = get_settings()
    assert settings.app.env == "prod"
    assert settings.llm.base_url == "http://192.168.16.10:8080/v1"
    assert settings.server.log_level == "WARNING"
