"""多环境配置加载。优先级：环境变量 > config-{env}.yaml > config.yaml > 默认。"""
import os
from pathlib import Path
from typing import List

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


class ServerSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"


class LlmSettings(BaseModel):
    base_url: str = ""
    model: str = "qwen3.6-35b-a3b"
    temperature: float = 0.1
    timeout: int = 30
    api_key: str = ""


class AuthSettings(BaseModel):
    api_keys: List[str] = []


class DebugSettings(BaseModel):
    llm_trace: bool = False
    llm_trace_max_chars: int = 2000
    llm_trace_prompts: List[str] = []
    llm_trace_write_html: bool = True
    llm_trace_output_dir: str = "tmp/llm-trace-audit"


class SigningPresetSettings(BaseModel):
    base_url: str = ""
    path: str = "/api/v1/signature-presets/by-entity-name"
    timeout: float = 3.0


class AppMeta(BaseModel):
    env: str = "dev"


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_yaml_data(env: str) -> dict:
    """合并 config.yaml 基线与 config-{env}.yaml 覆盖。"""
    data: dict = {}
    base = _CONFIG_DIR / "config.yaml"
    if base.exists():
        data = _deep_merge(data, yaml.safe_load(base.read_text(encoding="utf-8")) or {})
    env_file = _CONFIG_DIR / f"config-{env}.yaml"
    if env_file.exists():
        data = _deep_merge(data, yaml.safe_load(env_file.read_text(encoding="utf-8")) or {})
    return data


class YamlSettingsSource(PydanticBaseSettingsSource):
    """以 YAML 文件作为配置源（优先级低于环境变量）。"""

    def __init__(self, settings_cls):
        super().__init__(settings_cls)
        env = os.getenv("LTC_ENV", "dev")
        data = _load_yaml_data(env)
        data.setdefault("app", {})["env"] = env
        self._data = data

    def get_field_value(self, field, field_name):
        return self._data.get(field_name), field_name, False

    def __call__(self) -> dict:
        return {
            name: self._data[name]
            for name in self.settings_cls.model_fields
            if name in self._data
        }


class Settings(BaseSettings):
    model_config = {
        "env_prefix": "LTC__",
        "env_nested_delimiter": "__",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    server: ServerSettings = ServerSettings()
    llm: LlmSettings = LlmSettings()
    auth: AuthSettings = AuthSettings()
    debug: DebugSettings = DebugSettings()
    signing_preset: SigningPresetSettings = SigningPresetSettings()
    app: AppMeta = AppMeta()

    @classmethod
    def settings_customise_sources(
        cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings
    ):
        # 优先级（高→低）：init kwargs > 环境变量 > .env > yaml > 默认
        return (init_settings, env_settings, dotenv_settings,
                YamlSettingsSource(settings_cls), file_secret_settings)


_settings: Settings | None = None


def get_settings() -> Settings:
    """获取全局配置单例。"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def _reset_settings() -> None:
    """测试用：重置单例。"""
    global _settings
    _settings = None
