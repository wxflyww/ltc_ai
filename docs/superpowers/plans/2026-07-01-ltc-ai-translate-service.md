# LTC AI能力服务（翻译）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个独立部署的 FastAPI AI 能力服务，首期提供 `/health` 与 `POST /api/v1/translate` 两个接口，内部用 LangChain 调用私有化 vLLM 大模型，含多环境配置、容器化、可观测性、统一错误处理。

**Architecture:** 薄分层 + 能力包式结构（方案 A）。四层：API 层（FastAPI Router + Pydantic）→ 能力层（capabilities/translate/）→ 模型适配层（models/llm.py，LangChain ChatModel 适配 vLLM OpenAI 兼容）→ 基础设施层（core/）。能力之间互不依赖，未来加 OCR 只需新增一个 capabilities 包。测试在模型层边界 mock，CI 不依赖 vLLM。

**Tech Stack:** Python 3.11、FastAPI、uvicorn、LangChain（langchain-core + langchain-openai）、tenacity、pydantic-settings、PyYAML、prometheus-fastapi-instrumentator、pytest、httpx（TestClient）、Docker。

## Global Constraints

- Python 3.11，基础镜像 `python:3.11-slim`。
- 统一响应格式：`{ code, message, data, traceId, duration_seconds }`，`code=0` 成功，非 0 错误。
- `duration_seconds` 放响应顶层、与 `traceId` 并列，3 位小数秒，成功/错误响应都带。
- 错误码分段：`0` 成功；`1xxxx` 客户端错误；`2xxxx` 服务端错误（`20001` 模型调用失败重试耗尽、`20002` 模型超时、`20003` 模型返回格式异常、`29999` 未捕获兜底、`10001` 参数校验失败、`10002` API Key 无效/缺失）。
- 重试：3 次（1 初始 + 2 重试），指数退避 1s→2s，±20% 抖动；仅对超时/5xx/429 重试；4xx 非 429 与格式异常不重试。不做内容降级，失败即报错 `20001`。
- 鉴权：API Key，从 `Authorization: Bearer <key>` 或 `X-API-Key` 头读取，与配置 `api_keys` 白名单比对。`/health` 与 `/metrics` 不鉴权。
- 配置加载优先级：环境变量 > `config-{env}.yaml` > `config.yaml`；`LTC_ENV` 选 dev/test/prod；密钥不入库走环境变量。
- traceId 优先级：请求头 `X-Trace-Id` 透传 > 自动生成 UUID。
- 结构化日志 JSON 格式，含 `traceId`/`endpoint`/`duration_seconds`/`llm_duration_seconds`。
- 测试在模型层边界 mock，CI 不依赖 vLLM 可用性。

---

## File Structure

| 文件 | 职责 | 创建/修改 |
|---|---|---|
| `pyproject.toml` | 依赖与项目元数据 | Create |
| `.env.example` | 环境变量占位样例 | Create |
| `.gitignore` | 追加 .env 等 | Modify |
| `config/config.yaml` | 默认配置基线 | Create |
| `config/config-dev.yaml` | dev 覆盖 | Create |
| `config/config-test.yaml` | test 覆盖 | Create |
| `config/config-prod.yaml` | prod 覆盖 | Create |
| `app/__init__.py` | 包标识（空） | Create |
| `app/core/__init__.py` | 包标识（空） | Create |
| `app/core/config.py` | 多环境配置加载 + Settings | Create |
| `app/core/response.py` | 统一响应包装模型 | Create |
| `app/core/errors.py` | 错误码常量 + 业务异常基类 | Create |
| `app/core/exception_handlers.py` | 异常→统一响应转换 | Create |
| `app/core/logging.py` | 结构化 JSON 日志 | Create |
| `app/core/middleware.py` | traceId + API Key + 耗时中间件 | Create |
| `app/models/__init__.py` | 包标识（空） | Create |
| `app/models/llm.py` | LangChain ChatModel 工厂 + 指标埋点 | Create |
| `app/capabilities/__init__.py` | 包标识（空） | Create |
| `app/capabilities/translate/__init__.py` | 包标识（空） | Create |
| `app/capabilities/translate/schemas.py` | 请求/响应 Pydantic 模型 | Create |
| `prompts/translate.yaml` | 翻译 prompt 模板 | Create |
| `app/capabilities/translate/prompts.py` | 加载 YAML 构造 PromptTemplate | Create |
| `app/capabilities/translate/service.py` | 翻译业务 + 重试 | Create |
| `app/capabilities/translate/router.py` | POST /api/v1/translate 路由 | Create |
| `app/main.py` | FastAPI 应用装配 | Create |
| `tests/__init__.py` | 包标识（空） | Create |
| `tests/conftest.py` | pytest fixture | Create |
| `tests/test_health.py` | 健康检查测试 | Create |
| `tests/test_config.py` | 配置加载测试 | Create |
| `tests/test_translate_service.py` | 重试/降级单测 | Create |
| `tests/test_translate_api.py` | 接口级测试 | Create |
| `Dockerfile` | 多阶段构建 | Create |
| `docker-compose.yml` | 基础 compose | Create |
| `docker-compose.test.yml` | test override | Create |
| `docker-compose.prod.yml` | prod override | Create |
| `README.md` | 项目说明 | Create |

任务依赖顺序：1（项目骨架+配置）→ 2（统一响应/错误码）→ 3（配置）→ 4（日志）→ 5（模型适配层）→ 6（翻译 schemas+prompt）→ 7（翻译 service+重试）→ 8（翻译 router）→ 9（中间件）→ 10（main 装配）→ 11（Docker+compose+README）。

---

### Task 1: 项目骨架与依赖

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Modify: `.gitignore`
- Create: `app/__init__.py`
- Create: `app/core/__init__.py`
- Create: `app/models/__init__.py`
- Create: `app/capabilities/__init__.py`
- Create: `app/capabilities/translate/__init__.py`
- Create: `tests/__init__.py`

**Interfaces:**
- Produces: `pyproject.toml`（依赖清单，后续任务安装用）、空包标识文件。

- [ ] **Step 1: 创建 pyproject.toml**

```toml
[project]
name = "ltc-ai"
version = "1.0.0"
description = "LTC AI能力/Agent服务 - AI中台能力层"
requires-python = ">=3.11,<3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "pydantic>=2.7.0",
    "pydantic-settings>=2.3.0",
    "langchain>=0.3.0",
    "langchain-core>=0.3.0",
    "langchain-openai>=0.2.0",
    "tenacity>=8.4.0",
    "pyyaml>=6.0",
    "prometheus-fastapi-instrumentator>=7.0.0",
    "python-json-logger>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.27.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"
```

- [ ] **Step 2: 创建 .env.example**

```bash
# 运行环境：dev / test / prod
LTC_ENV=dev

# 服务配置（覆盖 config-*.yaml）
# LTC__SERVER__PORT=8000
# LTC__SERVER__LOG_LEVEL=INFO

# vLLM OpenAI 兼容端点（生产必填）
# LTC__LLM__BASE_URL=http://vllm-prod.internal:8000/v1
# LTC__LLM__MODEL=qwen3.6-35b-a3b

# API Key 白名单（逗号分隔）
# LTC__AUTH__API_KEYS=changeme-key-1
```

- [ ] **Step 3: 更新 .gitignore（追加环境与缓存）**

读取现有 `.gitignore`，在末尾追加：

```gitignore

# 环境与密钥
.env
config/config-local-*.yaml

# Python
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.coverage
htmlcov/
```

- [ ] **Step 4: 创建空包标识文件**

`app/__init__.py`、`app/core/__init__.py`、`app/models/__init__.py`、`app/capabilities/__init__.py`、`app/capabilities/translate/__init__.py`、`tests/__init__.py` 均创建为空文件（内容为空字符串）。

- [ ] **Step 5: 安装依赖并验证**

Run: `.venv/Scripts/python -m pip install -e ".[dev]"`
Expected: 成功安装所有依赖，无报错。

- [ ] **Step 6: 验证导入**

Run: `.venv/Scripts/python -c "import fastapi, langchain_openai, tenacity, yaml; print('ok')"`
Expected: 输出 `ok`

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .env.example .gitignore app/ tests/
git commit -m "chore: 项目骨架与依赖"
```

---

### Task 2: 统一响应与错误码

**Files:**
- Create: `app/core/response.py`
- Create: `app/core/errors.py`
- Create: `tests/test_response_errors.py`

**Interfaces:**
- Produces: `ApiResponse`（统一响应模型）、`ErrorCode`（错误码常量）、`AppError`（业务异常基类，属性 `code`/`message`/`http_status`）。
- 后续任务 `exception_handlers.py` 依赖 `ApiResponse` 与 `AppError`；`middleware.py` 依赖 `AppError`。

- [ ] **Step 1: 写失败测试 `tests/test_response_errors.py`**

```python
from app.core.errors import ErrorCode, AppError, ValidationError, AuthError, ModelInvocationError, ModelTimeoutError, ModelFormatError
from app.core.response import ApiResponse


def test_api_response_success():
    resp = ApiResponse(data={"translated_text": "hi"}, trace_id="t1", duration_seconds=0.123)
    body = resp.to_dict()
    assert body["code"] == 0
    assert body["message"] == "ok"
    assert body["data"] == {"translated_text": "hi"}
    assert body["traceId"] == "t1"
    assert body["duration_seconds"] == 0.123


def test_api_response_error():
    resp = ApiResponse(code=ErrorCode.PARAM_INVALID, message="bad", data=None,
                       trace_id="t1", duration_seconds=0.1)
    body = resp.to_dict()
    assert body["code"] == 10001
    assert body["data"] is None


def test_app_error_carries_code_and_http_status():
    err = ValidationError("text is empty")
    assert err.code == ErrorCode.PARAM_INVALID
    assert err.http_status == 400
    assert "text is empty" in err.message


def test_error_code_segments():
    assert ErrorCode.SUCCESS == 0
    assert ErrorCode.AUTH_INVALID == 10002
    assert ErrorCode.MODEL_INVOCATION == 20001
    assert ErrorCode.MODEL_TIMEOUT == 20002
    assert ErrorCode.MODEL_FORMAT == 20003
    assert ErrorCode.UNKNOWN == 29999


def test_model_errors_distinct():
    assert ModelInvocationError("x").http_status == 500
    assert ModelTimeoutError("x").http_status == 504
    assert ModelFormatError("x").http_status == 500
```

- [ ] **Step 2: 运行测试验证失败**

Run: `.venv/Scripts/python -m pytest tests/test_response_errors.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.core.response'`）

- [ ] **Step 3: 创建 `app/core/errors.py`**

```python
"""统一错误码与业务异常基类。"""


class ErrorCode:
    SUCCESS = 0

    # 客户端错误 1xxxx
    PARAM_INVALID = 10001
    AUTH_INVALID = 10002

    # 服务端错误 2xxxx
    MODEL_INVOCATION = 20001  # 调用失败（重试耗尽）
    MODEL_TIMEOUT = 20002
    MODEL_FORMAT = 20003
    UNKNOWN = 29999


class AppError(Exception):
    """业务异常基类。异常处理器据此转成统一响应。"""

    code: int = ErrorCode.UNKNOWN
    http_status: int = 500

    def __init__(self, message: str = ""):
        self.message = message or self.__class__.__name__
        super().__init__(self.message)


class ValidationError(AppError):
    code = ErrorCode.PARAM_INVALID
    http_status = 400


class AuthError(AppError):
    code = ErrorCode.AUTH_INVALID
    http_status = 401


class ModelInvocationError(AppError):
    code = ErrorCode.MODEL_INVOCATION
    http_status = 500


class ModelTimeoutError(AppError):
    code = ErrorCode.MODEL_TIMEOUT
    http_status = 504


class ModelFormatError(AppError):
    code = ErrorCode.MODEL_FORMAT
    http_status = 500
```

- [ ] **Step 4: 创建 `app/core/response.py`**

```python
"""统一响应包装。"""
from typing import Any, Optional

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    """统一响应：{ code, message, data, traceId, duration_seconds }。"""

    code: int = 0
    message: str = "ok"
    data: Optional[Any] = None
    traceId: str = ""
    duration_seconds: float = Field(default=0.0)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "data": self.data,
            "traceId": self.traceId,
            "duration_seconds": round(self.duration_seconds, 3),
        }
```

- [ ] **Step 5: 运行测试验证通过**

Run: `.venv/Scripts/python -m pytest tests/test_response_errors.py -v`
Expected: PASS（6 个测试通过）

- [ ] **Step 6: Commit**

```bash
git add app/core/response.py app/core/errors.py tests/test_response_errors.py
git commit -m "feat(core): 统一响应格式与错误码"
```

---

### Task 3: 多环境配置加载

**Files:**
- Create: `config/config.yaml`
- Create: `config/config-dev.yaml`
- Create: `config/config-test.yaml`
- Create: `config/config-prod.yaml`
- Create: `app/core/config.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Produces: `Settings`（全局配置单例，`get_settings()` 工厂）；字段：`server.host/port/log_level`、`llm.base_url/model/temperature/timeout`、`auth.api_keys`、`app.env`。
- 后续 `models/llm.py`、`middleware.py`、`logging.py` 依赖 `get_settings()`。

- [ ] **Step 1: 写失败测试 `tests/test_config.py`**

```python
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
    assert settings.llm.timeout == 30
    # dev 覆盖
    assert settings.llm.base_url == "http://vllm-dev.internal:8000/v1"
    # env 标记
    assert settings.app.env == "dev"


def test_env_var_overrides_yaml(monkeypatch):
    monkeypatch.setenv("LTC_ENV", "dev")
    monkeypatch.setenv("LTC__SERVER__PORT", "9999")
    monkeypatch.setenv("LTC__AUTH__API_KEYS", '["k1","k2"]')
    _reset_settings()
    settings = get_settings()
    assert settings.server.port == 9999
    assert settings.auth.api_keys == ["k1", "k2"]


def test_prod_env_uses_prod_yaml(monkeypatch):
    monkeypatch.setenv("LTC_ENV", "prod")
    _reset_settings()
    settings = get_settings()
    assert settings.app.env == "prod"
    assert settings.llm.base_url == "http://vllm-prod.internal:8000/v1"
    assert settings.server.log_level == "WARNING"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `.venv/Scripts/python -m pytest tests/test_config.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 创建配置文件**

`config/config.yaml`：
```yaml
server:
  host: "0.0.0.0"
  port: 8000
  log_level: "INFO"
llm:
  base_url: ""
  model: "qwen3.6-35b-a3b"
  temperature: 0.3
  timeout: 30
auth:
  api_keys: []
```

`config/config-dev.yaml`：
```yaml
llm:
  base_url: "http://vllm-dev.internal:8000/v1"
```

`config/config-test.yaml`：
```yaml
llm:
  base_url: "http://vllm-test.internal:8000/v1"
```

`config/config-prod.yaml`：
```yaml
llm:
  base_url: "http://vllm-prod.internal:8000/v1"
  model: "qwen3.6-35b-a3b"
server:
  log_level: "WARNING"
```

- [ ] **Step 4: 创建 `app/core/config.py`**

```python
"""多环境配置加载。优先级：环境变量 > config-{env}.yaml > config.yaml。"""
import os
from pathlib import Path
from typing import List

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"

# 嵌套子模型
class ServerSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"


class LlmSettings(BaseModel):
    base_url: str = ""
    model: str = "qwen3.6-35b-a3b"
    temperature: float = 0.3
    timeout: int = 30


class AuthSettings(BaseModel):
    api_keys: List[str] = []


class AppMeta(BaseModel):
    env: str = "dev"


class Settings(BaseSettings):
    server: ServerSettings = ServerSettings()
    llm: LlmSettings = LlmSettings()
    auth: AuthSettings = AuthSettings()
    app: AppMeta = AppMeta()

    model_config = {"env_prefix": "LTC__", "env_nested_delimiter": "__"}


_settings: Settings | None = None


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_yaml(env: str) -> dict:
    data: dict = {}
    base = _CONFIG_DIR / "config.yaml"
    if base.exists():
        data = _deep_merge(data, yaml.safe_load(base.read_text(encoding="utf-8")) or {})
    env_file = _CONFIG_DIR / f"config-{env}.yaml"
    if env_file.exists():
        data = _deep_merge(data, yaml.safe_load(env_file.read_text(encoding="utf-8")) or {})
    return data


def get_settings() -> Settings:
    """获取全局配置单例。env 变量（LTC__ 前缀）覆盖 yaml。"""
    global _settings
    if _settings is not None:
        return _settings
    env = os.getenv("LTC_ENV", "dev")
    yaml_data = _load_yaml(env)
    yaml_data.setdefault("app", {})["env"] = env
    # 先用 yaml 构造，再用环境变量覆盖（pydantic-settings 自动从 env 读取 LTC__ 前缀）
    _settings = Settings(**yaml_data)
    return _settings


def _reset_settings() -> None:
    """测试用：重置单例。"""
    global _settings
    _settings = None
```

- [ ] **Step 5: 运行测试验证通过**

Run: `.venv/Scripts/python -m pytest tests/test_config.py -v`
Expected: PASS（3 个测试通过）

- [ ] **Step 6: Commit**

```bash
git add config/ app/core/config.py tests/test_config.py
git commit -m "feat(core): 多环境配置加载"
```

---

### Task 4: 结构化 JSON 日志

**Files:**
- Create: `app/core/logging.py`
- Create: `tests/test_logging.py`

**Interfaces:**
- Produces: `setup_logging(level)`（配置 JSON 日志）、`get_logger()`（带 traceId 上下文的 logger）、`bind_trace_id(trace_id)`/`clear_trace_id()`（上下文绑定）。
- 后续 `middleware.py`、`service.py`、`exception_handlers.py` 依赖。

- [ ] **Step 1: 写失败测试 `tests/test_logging.py`**

```python
import io
import json

from app.core.logging import setup_logging, get_logger, bind_trace_id, clear_trace_id


def test_log_json_contains_trace_id():
    stream = io.StringIO()
    setup_logging("INFO", stream)
    bind_trace_id("trace-abc")
    logger = get_logger()
    logger.info("hello", extra={"endpoint": "/api/v1/translate", "duration_seconds": 0.5})
    clear_trace_id()
    line = stream.getvalue().strip().splitlines()[-1]
    obj = json.loads(line)
    assert obj["message"] == "hello"
    assert obj["traceId"] == "trace-abc"
    assert obj["endpoint"] == "/api/v1/translate"
    assert obj["duration_seconds"] == 0.5
    assert "timestamp" in obj
    assert obj["level"] == "INFO"


def test_log_without_trace_id():
    stream = io.StringIO()
    setup_logging("INFO", stream)
    clear_trace_id()
    logger = get_logger()
    logger.info("no trace")
    obj = json.loads(stream.getvalue().strip())
    assert obj["traceId"] == ""
```

- [ ] **Step 2: 运行测试验证失败**

Run: `.venv/Scripts/python -m pytest tests/test_logging.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 创建 `app/core/logging.py`**

```python
"""结构化 JSON 日志，注入 traceId。"""
import logging
import sys
from contextvars import ContextVar

from pythonjsonlogger import jsonlogger

_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")

_FORMAT = "%(timestamp)s %(level)s %(name)s %(message)s %(traceId)s %(endpoint)s %(duration_seconds)s %(llm_duration_seconds)s"


class _ContextFilter(logging.Filter):
    """把 contextvar 注入到每条日志的 record。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.traceId = _trace_id_var.get()
        if not hasattr(record, "endpoint"):
            record.endpoint = ""
        if not hasattr(record, "duration_seconds"):
            record.duration_seconds = ""
        if not hasattr(record, "llm_duration_seconds"):
            record.llm_duration_seconds = ""
        return True


def setup_logging(level: str = "INFO", stream=None) -> None:
    """配置根 logger 输出 JSON。"""
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(jsonlogger.JsonFormatter(_FORMAT))
    handler.addFilter(_ContextFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())


def get_logger(name: str = "ltc_ai") -> logging.Logger:
    return logging.getLogger(name)


def bind_trace_id(trace_id: str) -> None:
    _trace_id_var.set(trace_id)


def clear_trace_id() -> None:
    _trace_id_var.set("")
```

- [ ] **Step 4: 运行测试验证通过**

Run: `.venv/Scripts/python -m pytest tests/test_logging.py -v`
Expected: PASS（2 个测试通过）

- [ ] **Step 5: Commit**

```bash
git add app/core/logging.py tests/test_logging.py
git commit -m "feat(core): 结构化JSON日志"
```

---

### Task 5: 模型适配层（LangChain ChatModel 工厂 + 指标埋点）

**Files:**
- Create: `app/models/llm.py`
- Create: `tests/test_llm_factory.py`

**Interfaces:**
- Consumes: `get_settings()`（Task 3）。
- Produces: `get_chat_model()` → `langchain_core.language_models.BaseChatModel`；`invoke_model(messages)` → 调用并返回 `(content: str, token_usage: dict)`，内部埋点 Prometheus 指标 `llm_calls_total`/`llm_call_duration_seconds`/`llm_tokens_total`。
- 后续 `translate/service.py` 依赖 `invoke_model`。

**说明：** 重试逻辑在 Task 7（service 层），本层只调用 + 抛原始错误 + 埋点。`invoke_model` 用 try/except 区分超时（→`ModelTimeoutError`）与其他错误（原样抛出，由 service 判定可重试性）。

- [ ] **Step 1: 写失败测试 `tests/test_llm_factory.py`**

```python
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
```

- [ ] **Step 2: 运行测试验证失败**

Run: `.venv/Scripts/python -m pytest tests/test_llm_factory.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 创建 `app/models/llm.py`**

```python
"""模型适配层：LangChain ChatModel 工厂 + 调用埋点。重试在 service 层。"""
import time

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from prometheus_client import Counter, Histogram

from app.core.config import get_settings
from app.core.errors import ModelTimeoutError
from app.core.logging import get_logger

logger = get_logger("llm")

llm_calls_total = Counter("llm_calls_total", "LLM calls", ["model", "status"])
llm_call_duration_seconds = Histogram("llm_call_duration_seconds", "LLM call latency", ["model"])
llm_tokens_total = Counter("llm_tokens_total", "LLM token usage", ["model", "type"])

_chat_model: BaseChatModel | None = None


def get_chat_model() -> BaseChatModel:
    """构造配置好的 LangChain ChatModel（vLLM OpenAI 兼容）。单例。"""
    global _chat_model
    if _chat_model is not None:
        return _chat_model
    s = get_settings().llm
    _chat_model = ChatOpenAI(
        model=s.model,
        base_url=s.base_url,
        temperature=s.temperature,
        timeout=s.timeout,
        api_key="dummy-not-used-by-vllm-but-required",
    )
    return _chat_model


def invoke_model(model: BaseChatModel, messages: list) -> tuple[str, dict]:
    """调用模型，返回 (content, token_usage)。超时转 ModelTimeoutError，其他错误原样抛出。"""
    model_name = getattr(model, "model_name", "") or getattr(model, "model", "unknown")
    start = time.perf_counter()
    try:
        resp = model.invoke(messages)
    except TimeoutError as e:
        llm_calls_total.labels(model=model_name, status="timeout").inc()
        raise ModelTimeoutError(str(e)) from e
    elapsed = time.perf_counter() - start
    llm_call_duration_seconds.labels(model=model_name).observe(elapsed)

    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    usage_meta = getattr(resp, "usage_metadata", None) or {}
    usage = {
        "prompt_tokens": int(usage_meta.get("prompt_tokens", 0)),
        "completion_tokens": int(usage_meta.get("completion_tokens", 0)),
        "total_tokens": int(usage_meta.get("total_tokens", 0)),
    }
    llm_tokens_total.labels(model=model_name, type="prompt").inc(usage["prompt_tokens"])
    llm_tokens_total.labels(model=model_name, type="completion").inc(usage["completion_tokens"])
    llm_calls_total.labels(model=model_name, status="success").inc()
    logger.debug("llm invoked", extra={"llm_duration_seconds": round(elapsed, 3)})
    return content, usage
```

- [ ] **Step 4: 运行测试验证通过**

Run: `.venv/Scripts/python -m pytest tests/test_llm_factory.py -v`
Expected: PASS（5 个测试通过）

- [ ] **Step 5: Commit**

```bash
git add app/models/llm.py tests/test_llm_factory.py
git commit -m "feat(models): LangChain ChatModel工厂与调用埋点"
```

---

### Task 6: 翻译 Schemas 与 Prompt 模板

**Files:**
- Create: `prompts/translate.yaml`
- Create: `app/capabilities/translate/schemas.py`
- Create: `app/capabilities/translate/prompts.py`
- Create: `tests/test_translate_prompts.py`

**Interfaces:**
- Produces: `TranslateRequest`（`text`/`target_lang`/`source_lang?`）、`TranslateData`（`translated_text`/`source_lang`/`model`/`token_usage`）、`build_translate_prompt(text, target_lang, source_lang)` → `list[BaseMessage]`。
- 后续 `service.py`、`router.py` 依赖。

- [ ] **Step 1: 写失败测试 `tests/test_translate_prompts.py`**

```python
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
```

- [ ] **Step 2: 运行测试验证失败**

Run: `.venv/Scripts/python -m pytest tests/test_translate_prompts.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 创建 `prompts/translate.yaml`**

```yaml
system: |
  You are a professional translator. Translate the user's text to the target language.
  Rules:
  - Output ONLY the translated text, no explanations.
  - Preserve the original meaning, tone, and formatting.
  - If the source language is auto, infer it from the input.
user: |
  Source language: {source_lang}
  Target language: {target_lang}
  Text: {text}
```

- [ ] **Step 4: 创建 `app/capabilities/translate/schemas.py`**

```python
"""翻译请求/响应 Pydantic 模型。"""
from typing import Optional

from pydantic import BaseModel, Field


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, description="源文本")
    target_lang: str = Field(..., min_length=1, description="目标语言代码")
    source_lang: Optional[str] = Field(default=None, description="源语言代码，不传则模型自识别")


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class TranslateData(BaseModel):
    translated_text: str
    source_lang: str
    model: str
    token_usage: TokenUsage
```

- [ ] **Step 5: 创建 `app/capabilities/translate/prompts.py`**

```python
"""加载 YAML prompt 模板并构造 LangChain 消息。"""
from pathlib import Path
from typing import Optional

import yaml
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

_PROMPT_FILE = Path(__file__).resolve().parents[3] / "prompts" / "translate.yaml"
_template: dict | None = None


def _load_template() -> dict:
    global _template
    if _template is None:
        _template = yaml.safe_load(_PROMPT_FILE.read_text(encoding="utf-8"))
    return _template


def build_translate_prompt(
    text: str, target_lang: str, source_lang: Optional[str]
) -> list[BaseMessage]:
    tpl = _load_template()
    src = source_lang or "auto"
    system = tpl["system"].strip()
    user = tpl["user"].format(text=text, target_lang=target_lang, source_lang=src)
    return [SystemMessage(content=system), HumanMessage(content=user)]
```

- [ ] **Step 6: 运行测试验证通过**

Run: `.venv/Scripts/python -m pytest tests/test_translate_prompts.py -v`
Expected: PASS（4 个测试通过）

- [ ] **Step 7: Commit**

```bash
git add prompts/translate.yaml app/capabilities/translate/schemas.py app/capabilities/translate/prompts.py tests/test_translate_prompts.py
git commit -m "feat(translate): 请求响应schema与prompt模板"
```

---

### Task 7: 翻译 Service（含重试/降级）

**Files:**
- Create: `app/capabilities/translate/service.py`
- Create: `tests/test_translate_service.py`

**Interfaces:**
- Consumes: `get_chat_model()`/`invoke_model()`（Task 5）、`build_translate_prompt`（Task 6）、`get_settings()`（Task 3）。
- Produces: `translate(request: TranslateRequest) -> TranslateData`。失败抛 `ModelInvocationError`/`ModelFormatError`。
- 后续 `router.py` 依赖 `translate`。

**重试规则（全局约束）：** 3 次（1 初始 + 2 重试），退避 1s→2s，±20% 抖动；仅重试超时/5xx/429。用 tenacity 实现，重试只在 service 层。为使测试快速，退避参数需可注入。

- [ ] **Step 1: 写失败测试 `tests/test_translate_service.py`**

```python
from unittest.mock import MagicMock, patch

import pytest

from app.core.errors import ModelFormatError, ModelInvocationError, ModelTimeoutError
from app.capabilities.translate.schemas import TranslateRequest
from app.capabilities.translate import service


def _ok_model(content="Hello", tokens=8):
    m = MagicMock()
    m.model_name = "qwen3.6-35b-a3b"
    m.invoke.return_value = MagicMock(content=content,
                                       usage_metadata={"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": tokens})
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
    # invoke 返回无法解析的内容 → ModelFormatError，不重试
    m.invoke.return_value = MagicMock(content="", usage_metadata=None)
    with patch("app.capabilities.translate.service.get_chat_model", return_value=m):
        with pytest.raises(ModelFormatError):
            service.translate(req, sleep_fn=lambda s: None)
    assert m.invoke.call_count == 1


def test_translate_retries_on_http_500(monkeypatch):
    """模拟 5xx：用 langchain_openai 的 APIStatusError 不易构造，
    改用一个带 status_code=500 属性的异常对象，由 service 的可重试判定识别。"""
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
```

- [ ] **Step 2: 运行测试验证失败**

Run: `.venv/Scripts/python -m pytest tests/test_translate_service.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 创建 `app/capabilities/translate/service.py`**

```python
"""翻译业务：组装 prompt、调模型、指数退避重试。重试只在 service 层。"""
import random
import time
from typing import Callable

from app.core.config import get_settings
from app.core.errors import ModelFormatError, ModelInvocationError
from app.core.logging import get_logger
from app.models.llm import get_chat_model, invoke_model
from app.capabilities.translate.prompts import build_translate_prompt
from app.capabilities.translate.schemas import TranslateData, TranslateRequest

logger = get_logger("translate")

MAX_ATTEMPTS = 3  # 1 初始 + 2 重试
BASE_BACKOFFS = [1.0, 2.0]  # 秒，第 1、2 次重试前


def _is_retryable(err: Exception) -> bool:
    """超时、5xx、429 可重试；其他（含 ModelFormatError）不可重试。"""
    if isinstance(err, (TimeoutError,)):
        return True
    status = getattr(err, "status_code", None)
    if status is not None and (status == 429 or 500 <= status < 600):
        return True
    return False


def _backoff_with_jitter(attempt: int) -> float:
    base = BASE_BACKOFFS[attempt]
    return base * random.uniform(0.8, 1.2)


def translate(
    request: TranslateRequest,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> TranslateData:
    """执行翻译。失败重试，重试耗尽抛 ModelInvocationError。"""
    messages = build_translate_prompt(
        text=request.text, target_lang=request.target_lang, source_lang=request.source_lang
    )
    model = get_chat_model()
    model_name = getattr(model, "model_name", "") or getattr(model, "model", "unknown")

    last_err: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            content, usage = invoke_model(model, messages)
        except Exception as err:  # noqa: BLE001
            last_err = err
            logger.warning("model call failed, retrying", extra={"attempt": attempt + 1})
            if _is_retryable(err) and attempt < MAX_ATTEMPTS - 1:
                sleep_fn(_backoff_with_jitter(attempt))
                continue
            # 不可重试，或重试耗尽
            if isinstance(err, ModelFormatError):
                raise
            raise ModelInvocationError(str(err)) from err
        # 成功路径
        if not content or not content.strip():
            raise ModelFormatError("model returned empty content")
        return TranslateData(
            translated_text=content.strip(),
            source_lang=request.source_lang or "auto",
            model=model_name,
            token_usage=usage,
        )
    # 理论不可达（循环内已 raise），兜底
    raise ModelInvocationError(str(last_err) if last_err else "unknown model failure")
```

注：`invoke_model`（Task 5）对超时已转 `ModelTimeoutError`，但 `_is_retryable` 同时接受 `TimeoutError` 以防 vLLM 客户端抛原生 `httpx.ReadTimeout` 等；`ModelTimeoutError` 继承 `AppError` 而非 `TimeoutError`，故需补判。

- [ ] **Step 4: 修正可重试判定以覆盖 ModelTimeoutError**

编辑 `app/capabilities/translate/service.py`，将 `_is_retryable` 改为：

```python
def _is_retryable(err: Exception) -> bool:
    """超时、5xx、429 可重试；其他（含 ModelFormatError）不可重试。"""
    # ModelTimeoutError 或任何 TimeoutError 子类
    if isinstance(err, (TimeoutError,)) or "Timeout" in type(err).__name__:
        return True
    status = getattr(err, "status_code", None)
    if status is not None and (status == 429 or 500 <= status < 600):
        return True
    return False
```

- [ ] **Step 5: 运行测试验证通过**

Run: `.venv/Scripts/python -m pytest tests/test_translate_service.py -v`
Expected: PASS（5 个测试通过）

- [ ] **Step 6: Commit**

```bash
git add app/capabilities/translate/service.py tests/test_translate_service.py
git commit -m "feat(translate): 翻译service与指数退避重试"
```

---

### Task 8: 翻译 Router

**Files:**
- Create: `app/capabilities/translate/router.py`
- Create: `tests/test_translate_api.py`

**Interfaces:**
- Consumes: `translate()`（Task 7）、`TranslateRequest`/`TranslateData`（Task 6）、`ApiResponse`（Task 2）。
- Produces: `router: APIRouter`，`POST /api/v1/translate`。
- 注意：本任务测试 mock `service.translate`，验证响应契约与字段。鉴权/中间件在 Task 9/10，本任务测试用 `app.override` 不挂中间件，单独验证 router 逻辑。

- [ ] **Step 1: 写失败测试 `tests/test_translate_api.py`**

```python
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.capabilities.translate.schemas import TranslateData, TokenUsage
from app.main import create_app


def _client():
    return TestClient(create_app(register_middleware=False))


def test_translate_success_contract():
    fake = TranslateData(translated_text="Hello", source_lang="zh",
                         model="qwen3.6-35b-a3b",
                         token_usage=TokenUsage(prompt_tokens=5, completion_tokens=3, total_tokens=8))
    with patch("app.capabilities.translate.router.translate", return_value=fake):
        c = _client()
        r = c.post("/api/v1/translate", json={"text": "你好", "target_lang": "en"})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["translated_text"] == "Hello"
    assert body["data"]["model"] == "qwen3.6-35b-a3b"
    assert body["traceId"]  # 非空
    assert "duration_seconds" in body  # 顶层


def test_translate_validation_error_returns_10001():
    c = _client()
    r = c.post("/api/v1/translate", json={"target_lang": "en"})  # 缺 text
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == 10001
    assert body["traceId"]
    assert "duration_seconds" in body


def test_translate_model_failure_returns_20001():
    from app.core.errors import ModelInvocationError
    with patch("app.capabilities.translate.router.translate",
               side_effect=ModelInvocationError("exhausted")):
        c = _client()
        r = c.post("/api/v1/translate", json={"text": "你好", "target_lang": "en"})
    assert r.status_code == 500
    body = r.json()
    assert body["code"] == 20001
    assert body["data"] is None
    assert body["traceId"]
```

- [ ] **Step 2: 运行测试验证失败**

Run: `.venv/Scripts/python -m pytest tests/test_translate_api.py -v`
Expected: FAIL（`app.main` 不存在）

- [ ] **Step 3: 创建 `app/capabilities/translate/router.py`**

```python
"""POST /api/v1/translate 路由。"""
from fastapi import APIRouter

from app.core.response import ApiResponse
from app.capabilities.translate.schemas import TranslateRequest
from app.capabilities.translate.service import translate

router = APIRouter(prefix="/api/v1", tags=["translate"])


@router.post("/translate")
def translate_endpoint(request: TranslateRequest) -> dict:
    data = translate(request)
    return ApiResponse(data=data).to_dict()
```

注：`traceId` 与 `duration_seconds` 由 Task 9 中间件注入到响应字典（FastAPI 返回 dict 时，响应体即该 dict）。中间件会在响应返回前补字段。Task 8 先用占位空串，Task 9 让测试通过。为避免 Task 8 卡住，先在 router 返回时填占位值：

```python
@router.post("/translate")
def translate_endpoint(request: TranslateRequest) -> dict:
    data = translate(request)
    body = ApiResponse(data=data).to_dict()
    body.setdefault("traceId", "")
    body.setdefault("duration_seconds", 0.0)
    return body
```

- [ ] **Step 4: 创建临时最小 `app/main.py`（Task 10 会扩展）**

```python
from fastapi import FastAPI

from app.capabilities.translate.router import router as translate_router


def create_app(register_middleware: bool = True) -> FastAPI:
    app = FastAPI(title="LTC AI能力服务", version="1.0.0")
    app.include_router(translate_router)
    if register_middleware:
        pass  # Task 9/10 接入
    return app


app = create_app()
```

- [ ] **Step 5: 运行测试验证通过**

Run: `.venv/Scripts/python -m pytest tests/test_translate_api.py -v`
Expected: PASS（3 个测试通过——此时 traceId/duration_seconds 为占位值，Task 9 接入后变真实值）

- [ ] **Step 6: Commit**

```bash
git add app/capabilities/translate/router.py app/main.py tests/test_translate_api.py
git commit -m "feat(translate): translate路由与最小应用"
```

---

### Task 9: 中间件（traceId + API Key + 耗时 + 异常处理）

**Files:**
- Create: `app/core/middleware.py`
- Create: `app/core/exception_handlers.py`
- Create: `tests/test_middleware.py`

**Interfaces:**
- Consumes: `get_settings()`、`bind_trace_id`/`clear_trace_id`、`ApiResponse`、`AppError`/`ErrorCode`。
- Produces: `TraceIdMiddleware`（生成/透传 traceId + 计时 + 注入响应 `traceId`/`duration_seconds`）、`AuthMiddleware`（API Key 校验，放行 `/health`、`/metrics`）、`register_exception_handlers(app)`（捕获 `AppError` 与兜底 `Exception`，输出统一错误响应）。
- 修改 `app/main.py` 接入。

- [ ] **Step 1: 写失败测试 `tests/test_middleware.py`**

```python
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.capabilities.translate.schemas import TranslateData, TokenUsage
from app.core.errors import AuthError, ModelInvocationError
from app.core.middleware import TraceIdMiddleware, AuthMiddleware, register_exception_handlers
from app.capabilities.translate.router import router as translate_router


def _build(auth_keys=None):
    app = FastAPI()
    app.add_middleware(TraceIdMiddleware)
    app.add_middleware(AuthMiddleware, allowed_keys=auth_keys or [])
    register_exception_handlers(app)
    app.include_router(translate_router)
    return TestClient(app)


def test_trace_id_passthrough_and_duration():
    fake = TranslateData(translated_text="Hi", source_lang="zh", model="m",
                         token_usage=TokenUsage())
    with patch("app.capabilities.translate.router.translate", return_value=fake):
        c = _build(auth_keys=["k1"])
        r = c.post("/api/v1/translate", json={"text": "x", "target_lang": "en"},
                   headers={"X-API-Key": "k1", "X-Trace-Id": "client-trace-1"})
    assert r.status_code == 200
    body = r.json()
    assert body["traceId"] == "client-trace-1"
    assert isinstance(body["duration_seconds"], (int, float))
    assert body["duration_seconds"] >= 0


def test_auth_missing_key_returns_10002():
    c = _build(auth_keys=["k1"])
    r = c.post("/api/v1/translate", json={"text": "x", "target_lang": "en"})
    assert r.status_code == 401
    assert r.json()["code"] == 10002


def test_auth_invalid_key_returns_10002():
    c = _build(auth_keys=["k1"])
    r = c.post("/api/v1/translate", json={"text": "x", "target_lang": "en"},
               headers={"X-API-Key": "wrong"})
    assert r.status_code == 401
    assert r.json()["code"] == 10002


def test_auth_bearer_header_accepted():
    fake = TranslateData(translated_text="Hi", source_lang="zh", model="m",
                         token_usage=TokenUsage())
    with patch("app.capabilities.translate.router.translate", return_value=fake):
        c = _build(auth_keys=["k1"])
        r = c.post("/api/v1/translate", json={"text": "x", "target_lang": "en"},
                   headers={"Authorization": "Bearer k1"})
    assert r.status_code == 200


def test_health_bypasses_auth():
    from app.main import create_app
    # /health 在 main.py 注册，这里直接测 auth 不挡 /health
    app = FastAPI()
    app.add_middleware(AuthMiddleware, allowed_keys=["k1"])

    @app.get("/health")
    def h():
        return {"status": "ok"}

    c = TestClient(app)
    r = c.get("/health")
    assert r.status_code == 200


def test_app_error_returned_as_unified_response():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom():
        raise ModelInvocationError("exhausted")

    c = TestClient(app)
    r = c.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["code"] == 20001
    assert body["data"] is None


def test_unhandled_exception_returns_29999():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/crash")
    def crash():
        raise RuntimeError("unexpected")

    c = TestClient(app)
    r = c.get("/crash")
    assert r.status_code == 500
    assert r.json()["code"] == 29999
```

- [ ] **Step 2: 运行测试验证失败**

Run: `.venv/Scripts/python -m pytest tests/test_middleware.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 创建 `app/core/exception_handlers.py`**

```python
"""全局异常 → 统一响应。"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.core.response import ApiResponse

logger = get_logger("errors")

# Pydantic/FastAPI 校验错误 → 10001
from fastapi.exceptions import RequestValidationError


def _json(resp: ApiResponse, status: int) -> JSONResponse:
    return JSONResponse(status_code=status, content=resp.to_dict())


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        resp = ApiResponse(code=ErrorCode.PARAM_INVALID, message="参数校验失败",
                           data=None, trace_id="", duration_seconds=0.0)
        return _json(resp, 422)

    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        logger.error("app error: %s", exc.message)
        resp = ApiResponse(code=exc.code, message=exc.message, data=None,
                           trace_id="", duration_seconds=0.0)
        return _json(resp, exc.http_status)

    @app.exception_handler(Exception)
    async def _unknown(request: Request, exc: Exception):
        logger.exception("unhandled exception")
        resp = ApiResponse(code=ErrorCode.UNKNOWN, message="内部错误", data=None,
                           trace_id="", duration_seconds=0.0)
        return _json(resp, 500)
```

注：`trace_id` 与 `duration_seconds` 由 `TraceIdMiddleware` 在响应后处理阶段注入（见下一步），异常处理器先填占位空值，中间件在 finalize 时覆盖。

- [ ] **Step 4: 创建 `app/core/middleware.py`**

```python
"""traceId 注入、API Key 校验、耗时记录中间件。"""
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.errors import AuthError
from app.core.logging import bind_trace_id, clear_trace_id, get_logger

logger = get_logger("middleware")

_AUTH_FREE_PATHS = {"/health", "/metrics"}


class TraceIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex
        bind_trace_id(trace_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            clear_trace_id()
        duration = time.perf_counter() - start
        # 注入 traceId / duration_seconds 到 JSON 响应体
        await _inject_trace_fields(response, trace_id, duration)
        logger.info("request done", extra={"endpoint": request.url.path,
                                           "duration_seconds": round(duration, 3)})
        return response


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_keys: list[str] | None = None):
        super().__init__(app)
        self.allowed_keys = set(allowed_keys or [])

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _AUTH_FREE_PATHS:
            return await call_next(request)
        token = request.headers.get("X-API-Key") or _extract_bearer(request)
        if not token or token not in self.allowed_keys:
            return _auth_error_response()
        return await call_next(request)


def _extract_bearer(request: Request) -> str | None:
    h = request.headers.get("Authorization", "")
    if h.lower().startswith("bearer "):
        return h[7:].strip()
    return None


def _auth_error_response() -> Response:
    from app.core.errors import ErrorCode
    from app.core.response import ApiResponse
    resp = ApiResponse(code=ErrorCode.AUTH_INVALID, message="API Key 无效或缺失",
                       data=None, trace_id="", duration_seconds=0.0)
    return Response(content=resp.model_dump_json(), media_type="application/json",
                    status_code=401)


async def _inject_trace_fields(response: Response, trace_id: str, duration: float) -> None:
    """对 JSON 响应体补 traceId / duration_seconds。"""
    body = b""
    async for chunk in response.body_iterator:
        body += chunk
    try:
        import json
        obj = json.loads(body)
        if isinstance(obj, dict):
            obj["traceId"] = trace_id
            obj["duration_seconds"] = round(duration, 3)
            new_body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            response.body = new_body
            response.headers["content-length"] = str(len(new_body))
    except Exception:  # noqa: BLE001
        # 非 JSON（如 /metrics 纯文本）不处理
        response.body = body
```

注：`AuthMiddleware` 直接返回 `Response`（不经过 `call_next`），故 `TraceIdMiddleware` 须在 `AuthMiddleware` 之前注册（外层），以包裹其响应。注册顺序见 Task 10。

- [ ] **Step 5: 更新 `app/main.py` 接入中间件**

```python
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.middleware import AuthMiddleware, TraceIdMiddleware
from app.core.exception_handlers import register_exception_handlers
from app.capabilities.translate.router import router as translate_router


def create_app(register_middleware: bool = True) -> FastAPI:
    settings = get_settings()
    setup_logging(settings.server.log_level)
    app = FastAPI(title="LTC AI能力服务", version="1.0.0")

    if register_middleware:
        app.add_middleware(AuthMiddleware, allowed_keys=settings.auth.api_keys)
        app.add_middleware(TraceIdMiddleware)

    register_exception_handlers(app)
    app.include_router(translate_router)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "1.0.0"}

    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
    return app


app = create_app()
```

- [ ] **Step 6: 运行全部测试验证通过**

Run: `.venv/Scripts/python -m pytest tests/ -v`
Expected: PASS（所有测试通过）。注意 Task 8 的 `test_translate_api.py` 用 `create_app(register_middleware=False)`，此时无 traceId 中间件，traceId 为占位 —— 该断言只要求非空，占位空串会失败。需修正 Task 8 测试期望。

修正 `tests/test_translate_api.py` 中 `test_translate_success_contract` 与 `test_translate_validation_error_returns_10001`、`test_translate_model_failure_returns_20001`：当 `register_middleware=False` 时 traceId 为占位空串。改为断言字段存在而非非空：

```python
    assert "traceId" in body
    assert "duration_seconds" in body
```

（即把 `assert body["traceId"]` 改为 `assert "traceId" in body`）

Run: `.venv/Scripts/python -m pytest tests/test_translate_api.py tests/test_middleware.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/core/middleware.py app/core/exception_handlers.py app/main.py tests/test_middleware.py tests/test_translate_api.py
git commit -m "feat(core): traceId/APIKey/耗时中间件与异常处理"
```

---

### Task 10: 健康检查测试与端到端冒烟

**Files:**
- Create: `tests/test_health.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Produces: 健康检查测试、conftest fixture（`reset_settings` autouse、`client` fixture）。

- [ ] **Step 1: 写 `tests/test_health.py`**

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_ok():
    c = TestClient(create_app())
    r = c.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == "1.0.0"


def test_health_does_not_require_auth():
    c = TestClient(create_app())  # 默认 register_middleware=True，但 /health 免鉴权
    r = c.get("/health")
    assert r.status_code == 200


def test_metrics_exposed():
    c = TestClient(create_app())
    r = c.get("/metrics")
    assert r.status_code == 200
    assert "http_requests_total" in r.text or "python_info" in r.text
```

- [ ] **Step 2: 写 `tests/conftest.py`**

```python
import os

import pytest

from app.core.config import _reset_settings


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch):
    monkeypatch.setenv("LTC_ENV", "dev")
    _reset_settings()
    yield
    _reset_settings()
```

- [ ] **Step 3: 运行全部测试**

Run: `.venv/Scripts/python -m pytest tests/ -v`
Expected: PASS（全部测试通过）

- [ ] **Step 4: 启动服务冒烟（手动）**

Run: `.venv/Scripts/python -m uvicorn app.main:app --port 8001`
然后在另一终端：
Run: `curl -s http://127.0.0.1:8001/health`
Expected: `{"status":"ok","version":"1.0.0"}`

Run: `curl -s -X POST http://127.0.0.1:8001/api/v1/translate -H "Content-Type: application/json" -d '{"text":"hello","target_lang":"zh"}'`
Expected: 返回 401（无 API Key，dev 环境 api_keys 为空 → 所有 key 无效）。

注：dev 环境 `api_keys=[]` 表示无任何合法 key。冒烟鉴权需临时设环境变量 `LTC__AUTH__API_KEYS='["test"]'` 后重启再测成功路径。此步为手动验证，不阻塞。

- [ ] **Step 5: Commit**

```bash
git add tests/test_health.py tests/conftest.py
git commit -m "test: 健康检查与端到端冒烟"
```

---

### Task 11: 容器化与文档

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `docker-compose.test.yml`
- Create: `docker-compose.prod.yml`
- Create: `README.md`

**Interfaces:**
- 产物：可构建镜像、可 compose 启动、README 含构建与启动说明。

- [ ] **Step 1: 创建 `Dockerfile`（多阶段）**

```dockerfile
# ---- builder ----
FROM python:3.11-slim AS builder
WORKDIR /build
COPY pyproject.toml ./
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir .

# ---- runtime ----
FROM python:3.11-slim AS runtime
RUN useradd -m -u 1000 appuser
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    LTC_ENV=dev
WORKDIR /app
COPY app/ ./app/
COPY prompts/ ./prompts/
COPY config/ ./config/
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8000/health'); sys.exit(0)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: 创建 `docker-compose.yml`（基础）**

```yaml
services:
  ltc-ai:
    build: .
    image: ltc-ai:latest
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./config:/app/config:ro
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 1G
    restart: unless-stopped
```

- [ ] **Step 3: 创建 `docker-compose.test.yml`（override）**

```yaml
services:
  ltc-ai:
    environment:
      LTC_ENV: test
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 512M
```

- [ ] **Step 4: 创建 `docker-compose.prod.yml`（override）**

```yaml
services:
  ltc-ai:
    environment:
      LTC_ENV: prod
    deploy:
      resources:
        limits:
          cpus: "4.0"
          memory: 2G
      replicas: 2
```

- [ ] **Step 5: 创建 `README.md`**

````markdown
# LTC AI 能力服务

LTC（Lead to Cash）系统的 AI 中台能力层。首期提供健康检查与文本翻译接口，内部用 LangChain 调用私有化 vLLM 大模型。

## 接口

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/health` | 否 | 存活探针 |
| GET | `/metrics` | 否 | Prometheus 指标 |
| POST | `/api/v1/translate` | 是 | 文本翻译 |

### 翻译示例

```bash
curl -X POST http://localhost:8000/api/v1/translate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-key>" \
  -d '{"text":"本合同自双方签字之日起生效","target_lang":"en"}'
```

## 本地开发

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
LTC_ENV=dev .venv/Scripts/python -m uvicorn app.main:app --reload
```

## 配置

加载优先级：环境变量 > `config-{LTC_ENV}.yaml` > `config.yaml`。
密钥通过环境变量注入（`LTC__AUTH__API_KEYS` 等），不入库。见 `.env.example`。

## 测试

```bash
.venv/Scripts/python -m pytest tests/ -v
```

## 容器部署

```bash
# 构建
docker compose build
# 生产
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
# 测试
docker compose -f docker-compose.yml -f docker-compose.test.yml up -d
```

## 架构

薄分层 + 能力包式结构：API 层 → 能力层（capabilities/）→ 模型适配层（models/）→ 基础设施层（core/）。详见 `docs/superpowers/specs/2026-07-01-ltc-ai-translate-service-design.md`。
````

- [ ] **Step 6: 验证镜像构建**

Run: `docker compose build`
Expected: 成功构建镜像，无报错。

- [ ] **Step 7: 验证容器启动与健康检查**

Run: `LTC__AUTH__API_KEYS='["smoke-key"]' docker compose up -d`
Run: `sleep 3 && docker compose exec ltc-ai python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"`
Expected: 输出 `{"status":"ok","version":"1.0.0"}`
Run: `docker compose down`

- [ ] **Step 8: Commit**

```bash
git add Dockerfile docker-compose*.yml README.md
git commit -m "build: 多阶段Dockerfile与compose及README"
```

---

## 自检（Self-Review）

**1. Spec 覆盖：**
- 第 0 节范围（翻译+健康检查）→ Task 6/7/8（翻译）+ Task 10（健康检查）✅
- 第 1 节四层架构 → Task 2/3/4（core）、Task 5（models）、Task 6/7/8（capabilities）✅
- 第 2 节目录结构 → File Structure 表全覆盖 ✅
- 第 3 节接口契约 → Task 8（translate 契约）、Task 9（traceId/duration_seconds/错误码）✅
- 第 4 节重试/降级 → Task 7（重试 3 次/退避/可重试判定/不重试格式异常）✅
- 第 4 节错误分层 → Task 9（exception_handlers 全码段）✅
- 第 5 节多环境配置 → Task 3 ✅
- 第 5 节容器化 → Task 11 ✅
- 第 5 节可观测性（日志+指标）→ Task 4（日志）、Task 5（埋点）、Task 9/10（/metrics）✅
- 第 5 节安全（API Key，/health//metrics 免鉴权）→ Task 9 ✅
- 第 6 节测试策略 → 全任务 TDD ✅

**2. 占位扫描：** 无 TBD/TODO。Task 8 占位值已在 Task 9 替换为真实值，Task 9 步骤 6 明确修正了 Task 8 断言。

**3. 类型一致性：** `translate(request: TranslateRequest) -> TranslateData` 在 Task 6（schema）、Task 7（service）、Task 8（router）一致；`get_chat_model()`/`invoke_model()` 在 Task 5 定义、Task 7 消费一致；`ApiResponse` 字段在 Task 2 定义、Task 8/9 消费一致；错误码常量在 Task 2 定义、Task 5/7/9 消费一致。

**4. 一处修正：** Task 8 步骤 6 与 Task 9 步骤 6 之间，`test_translate_api.py` 的 traceId 断言需随中间件接入而调整 —— 已在 Task 9 步骤 6 显式说明并给出修正代码。
