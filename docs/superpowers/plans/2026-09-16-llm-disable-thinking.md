# 关闭模型思考模式（仅 contract_review 作用域）实施计划

> 对应 OpenSpec change：`llm-disable-thinking`。它是 `contract-review-mvp-prefill` 的**依赖**，**先做这一份**。
> 执行方式：测试驱动，先红后绿。本计划创建时**未修改任何业务代码**。

**目标：** 让 `POST /api/v1/contract-review` 的**全部模型调用**（`mode=review` 与后续 `mode=prefill` 共用 `_invoke_json_prompt`）在请求体携带 `chat_template_kwargs.enable_thinking=false`，消除思考文本污染。

**架构：** 只在 `app/capabilities/contract_review/service.py` **自己的调用点**做局部绑定（`model.bind(extra_body=...)`）。不经过 `app/models/llm.py`，不触碰 `two_stage/**` 与 `translate`。

**技术约束：** Python 3.11；LangChain `ChatOpenAI`；`chat_template_kwargs` **必须包在 `extra_body` 里**（直接当 invoke kwargs 会 `TypeError`，实测）；pytest。

**四条红线（逐条守住，Task 5 有可勾验命令）：**

1. `app/capabilities/contract_review/two_stage/**` 零改动 —— **不得新增该目录下的任何 git 变更条目**。
2. `app/models/llm.py` 零改动。
3. `app/capabilities/translate/**` 零改动。
4. `mode=review` 除"关思考"外，prompt / 响应模型 / `response_formats.py` / `checks.py` / `amounts.py` / 错误码 / 字段集合**全不动**。

---

## Task 1：写失败测试 —— 配置开关存在、且可被环境变量退回

**文件：** 修改 `tests/test_config.py`

### Step 1：在 `tests/test_config.py` 末尾追加

```python
def test_llm_disable_thinking_defaults_true(monkeypatch):
    monkeypatch.setenv("LTC_ENV", "dev")
    _reset_settings()
    settings = get_settings()
    assert settings.llm.disable_thinking is True


def test_llm_disable_thinking_env_override(monkeypatch):
    monkeypatch.setenv("LTC_ENV", "dev")
    monkeypatch.setenv("LTC__LLM__DISABLE_THINKING", "false")
    _reset_settings()
    settings = get_settings()
    assert settings.llm.disable_thinking is False
```

（`get_settings` / `_reset_settings` 该文件已导入，无需新增 import。）

### Step 2：运行，确认失败（RED）

```powershell
.venv\Scripts\python.exe -m pytest tests/test_config.py -k disable_thinking -v
```

预期：2 个用例失败，报 `AttributeError: 'LlmSettings' object has no attribute 'disable_thinking'`。

## Task 2：加配置字段（GREEN）

**文件：** 修改 `app/core/config.py`

### Step 1：在 `LlmSettings`（`config.py:19-24`）的 `api_key` 下一行插入一行

```python
    disable_thinking: bool = True
```

### Step 2：运行 Task 1 的测试，确认转绿

```powershell
.venv\Scripts\python.exe -m pytest tests/test_config.py -v
```

预期：全部通过。

> **为什么安全**：`LlmSettings` 是普通 `BaseModel`，外层 `Settings` 用 `extra="ignore"`（`config.py:98`）、`YamlSettingsSource` 只遍历 `model_fields`（`:85-89`）。`config.yaml` / `config-{env}.yaml` 都**不写**这个键 → 三套环境默认 `True`（关思考）。要退回某环境：`LTC__LLM__DISABLE_THINKING=false`，或在该环境 yaml 里加 `llm.disable_thinking: false`。
> `two_stage` 只读 `get_settings().llm.model`（`prepare_service.py:235`），`translate` 不读它 → 新字段对两者**无可见影响**。

## Task 3：写失败测试 —— 调用点确实绑定了关思考

**文件：** 新建 `tests/test_contract_review_thinking.py`

### Step 1：写入以下完整内容

```python
from langchain_openai import ChatOpenAI

from app.capabilities.contract_review import service as svc

_THINK_OFF = {"chat_template_kwargs": {"enable_thinking": False}}


def _fake_model() -> ChatOpenAI:
    return ChatOpenAI(model="qwen3.6-35b-a3b", base_url="http://127.0.0.1:1/v1", api_key="k")


def _settings_stub(disable_thinking: bool):
    llm = type("Llm", (), {"disable_thinking": disable_thinking})()
    return type("Settings", (), {"llm": llm})()


def test_model_for_json_prompt_binds_disable_thinking(monkeypatch):
    model = _fake_model()
    monkeypatch.setattr(svc, "get_chat_model", lambda: model)
    monkeypatch.setattr(svc, "get_settings", lambda: _settings_stub(True))

    bound = svc._model_for_json_prompt()

    assert bound is not model
    assert bound.kwargs.get("extra_body") == _THINK_OFF


def test_model_for_json_prompt_returns_plain_model_when_switch_off(monkeypatch):
    model = _fake_model()
    monkeypatch.setattr(svc, "get_chat_model", lambda: model)
    monkeypatch.setattr(svc, "get_settings", lambda: _settings_stub(False))

    assert svc._model_for_json_prompt() is model


def test_invoke_json_prompt_actually_sends_thinking_off(monkeypatch):
    """最强判据：走真实 _invoke_json_prompt，捕获真正交给 invoke_model 的模型对象。"""
    seen = {}

    def fake_invoke(model, messages, response_format=None):
        seen["model"] = model
        seen["response_format"] = response_format
        return ('{"header": {}, "signature_parties": [], "sections": []}', {})

    monkeypatch.setattr(svc, "invoke_model", fake_invoke)

    svc._invoke_json_prompt("a1a_party_extraction", full_text="合同正文")

    assert seen["model"].kwargs.get("extra_body") == _THINK_OFF
    assert seen["response_format"] is not None


def test_bound_model_keeps_model_name_for_metrics(monkeypatch):
    """bind 后仍能取到 model_name，Prometheus 指标标签不退化。"""
    model = _fake_model()
    monkeypatch.setattr(svc, "get_chat_model", lambda: model)
    monkeypatch.setattr(svc, "get_settings", lambda: _settings_stub(True))

    assert getattr(svc._model_for_json_prompt(), "model_name", "") == "qwen3.6-35b-a3b"
```

### Step 2：运行，确认失败（RED）

```powershell
.venv\Scripts\python.exe -m pytest tests/test_contract_review_thinking.py -v
```

预期：4 个用例全红，报 `AttributeError: module 'app.capabilities.contract_review.service' has no attribute '_model_for_json_prompt'`。

## Task 4：实现 `_model_for_json_prompt` 并接线（GREEN）

**文件：** 修改 `app/capabilities/contract_review/service.py`

### Step 1：在 `_invoke_json_prompt`（`service.py:284`）**上方**新增两段

```python
_THINKING_OFF_EXTRA_BODY = {"chat_template_kwargs": {"enable_thinking": False}}


def _model_for_json_prompt():
    """返回用于 JSON 抽取的模型；开关开启时绑定 enable_thinking=false。

    只在本能力自身的调用点绑定。model.bind 返回新对象、不污染 get_chat_model() 单例，
    故 two_stage 与 translate 的调用形态与取值均不受影响（已实测，见 change 任务 3.5）。
    """
    model = get_chat_model()
    if not get_settings().llm.disable_thinking:
        return model
    return model.bind(extra_body=dict(_THINKING_OFF_EXTRA_BODY))
```

（`get_settings` 已在 `service.py:36` 导入，无需新增 import。）

### Step 2：把 `_invoke_json_prompt` 里的这一行（`service.py:294`）

```python
    model = get_chat_model()
```

改为：

```python
    model = _model_for_json_prompt()
```

> **一处覆盖全部调用**：评审链路（A-1a / A-1b / A-3 / A-4 / B-1 / B-4 / 附件标题匹配）全部经过 `_invoke_json_prompt`；`:316` 首次调用与 `:357` 格式错重试**共用同一个 `model` 变量**，重试也带关思考。后续预填链路同样走这里。

### Step 3：运行，确认转绿

```powershell
.venv\Scripts\python.exe -m pytest tests/test_contract_review_thinking.py tests/test_config.py -v
```

预期：全部通过（4 + 5 个用例）。

## Task 5：全量回归 + 四条红线核验

### Step 1：跑全量测试

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```

预期：**全绿**。其中 `tests/two_stage/` 必须仍为 **467 passed / 0 failed**。
若有失败 —— **不得改测试期望凑绿**，回到 Task 4 查原因。

### Step 2：核验红线（第一条允许出现你**此前已在改**的两个文件，不得新增条目；后两条必须无输出）

```powershell
git status --short app/capabilities/contract_review/two_stage
git status --short app/models/llm.py
git status --short app/capabilities/translate
```

预期：
- 第 1 条只出现 `M extract_signature.py` / `?? extract_header_parties.py.bak`（你并行工作的既有改动，**原样保留**），无其他条目；
- 第 2、3 条**无任何输出**。

### Step 3：确认改动范围只落在这几个文件

```powershell
git status --short app config prompts
```

预期：只出现 `app/core/config.py`（1 行）与 `app/capabilities/contract_review/service.py`（新增函数 + 1 行替换）。

### Step 4：真实端点抽验（建议做，非自动测试）

用真实模型跑一次 `mode=review` 的 A-1a，确认输出 head 是 `{`、耗时与改前同量级。
本次实测基线（`c1.md`，`Qwen3.6-35B`）：关思考 **42.19s / 5,964 tokens**；不关 **48.19s / 5,970 tokens**，两次顶层键集合一致。
参考脚本：`tmp/_probe_review.py`（保留未删即可复用；`tmp/` 已被 `.gitignore` 覆盖）。

---

## 完成判据

1. `tests/` 全绿，`tests/two_stage/` 仍 467 passed。
2. `app/models/llm.py`、`app/capabilities/translate/`、`two_stage/` 三个目录**零新增 git 变更条目**。
3. 改动文件只有 `app/core/config.py`、`app/capabilities/contract_review/service.py` 与 2 个测试文件。
4. `openspec validate llm-disable-thinking --strict` 仍为 `is valid`。
