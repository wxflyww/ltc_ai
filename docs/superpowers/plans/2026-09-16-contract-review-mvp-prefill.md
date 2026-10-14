# MVP 智能预填（D-02 / D-03）实施计划

> 对应 OpenSpec change：`contract-review-mvp-prefill`。**依赖 change `llm-disable-thinking` 先完成**（见 `docs/superpowers/plans/2026-09-16-llm-disable-thinking.md`）。
> 设计依据：`docs/superpowers/specs/2026-09-15-contract-review-prefill-design.md`。
> 执行方式：测试驱动，先红后绿。本计划创建时**未修改任何业务代码**。
>
> ⚠️ **历史快照声明（2026-10-14 补注）**：本文是 **2026-09-16 当时的实施计划快照**，其中的口径为**当时状态**，**不随后续轮次更新**。若与下方文件冲突，**以下列文件为准**：
> - 口径总账 → `openspec/changes/contract-review-mvp-prefill/{spec.md,tasks.md}`（含 §20–§26 各轮定案）；
> - 接口契约 → `docs/integration/2026-09-16-contract-review-prefill-api-integration.md`；
> - 设计 → `docs/superpowers/specs/2026-09-15-contract-review-prefill-design.md`；
> - 实现 → `app/capabilities/contract_review/prefill_{prompts,response_formats,schemas}.py` + `prompts/contract_review.yaml`。
> 🔴 **已知过期点（勿据此实现）**：本文 L266 / L430 / L630 把 `guarantee.type` 写作 `["履约保函","履约保证金"]`（2 值或 3 值）—— **当前 schema 枚举为 7 值**（2026-10-13 扩），且 **服务只输出履约两类**（2026-10-14 定案，见 tasks.md §26：其余 5 类仅作**负向参考**）。

**目标：** 在 `POST /api/v1/contract-review` 上新增 `mode=prefill` 形态，从合同正文抽出 D-02（合同管理员，17 字段）+ D-03（销售，9 字段）共 26 个返回字段，经 `prefill_scope` 可按场景只抽一半。

**架构：** 路由层按 `mode` 分流 —— `review` 走现有 `review_contract()`（一行不改），`prefill` 走新增的独立链路（独立 prompt / 独立 schema / 独立响应模型 / 独立 service）。预填与评审**互不调用、互不共享状态**。

**技术约束：** Python 3.11、pydantic v2、pytest；不新增第三方依赖；`_invoke_json_prompt` 的关思考由依赖 change 提供，本计划**不重复实现**。

**四条红线：**

1. `app/capabilities/contract_review/two_stage/**` 零改动（不得新增该目录下的 git 变更条目）。
2. `app/models/llm.py`、`app/capabilities/translate/**` 零改动。
3. `mode=review` 的**运行时行为**不变：prompt / 响应字段集合与类型 / `checks.py` / `amounts.py` / 错误码全不动；`data` 段仍恰好 4 个键。
4. `ContractReviewData`（`schemas.py:45-49`）**不与预填共用**，零改动。

---

## Task 0：修设计文档 §10 的一处自相矛盾（先说清，再动手）

**文件：** 修改 `docs/superpowers/specs/2026-09-15-contract-review-prefill-design.md`

**问题**：§3.1 明确 `mode` / `prefill_scope` 是 `POST /api/v1/contract-review` 请求体新增字段，而 §10（`:382`）又写"不改 `schemas.py`"。同一份文档自相矛盾。

**定案（本次按此执行）**：

- 请求参数必须落在 `ContractReviewRequest`（`schemas.py:18`）——**这是 §10 那处措辞必须让位的地方**。做法是**加 2 个带默认值的可选字段**，`review` 路径一个字都不读它们，运行时行为不变。
- **`response_formats.py` 仍然零改动**（§10 这一半有效）：预填 schema 放**新模块**，见 Task 6。

**Step 1：** 把 §10 那一行（`:382`）改为：

```
- `mode=review` 的既有链路**只关思考，其它一律不碰**（红线，第八轮）：不改 prompt、不改 `response_formats.py` 的任何现有条目、不改 `checks.py` / `amounts.py`、不改错误码、不改响应字段集合与类型。**唯一例外**是 `schemas.py` 的 `ContractReviewRequest` 新增 2 个带默认值的可选请求字段（`mode` / `prefill_scope`）——评审路径不读取它们，属纯加性。
```

**Step 2：** 在 §11 追加第九轮记录（三行表格，格式照抄第八轮），登记"§10 ↔ §3.1 矛盾"的修正。

**验证：**

```powershell
Select-String -Path "docs\superpowers\specs\2026-09-15-contract-review-prefill-design.md" -Pattern "不改 `schemas.py`" -SimpleMatch
```

预期：无输出。

## Task 1：写失败测试 —— 换行归一化

**背景**：合同系统实际传入的正文是「一整行 + 字面量 `\n`」（样例 `tmp/samples/c1.md` 即此形态，10,632 字符）。不还原真换行，markdown 结构（尤其付款计划表）会丢。

**文件：** 新建 `tests/test_contract_review_prefill.py`

### Step 1：写入（本任务只需这一段，后续 Task 会继续追加）

```python
from app.capabilities.contract_review.prefill_prompts import normalize_contract_text


def test_normalize_single_line_with_literal_backslash_n():
    raw = "第一条 总则\\n第二条 付款方式\\n（一）合同签订后支付30%"
    assert normalize_contract_text(raw) == "第一条 总则\n第二条 付款方式\n（一）合同签订后支付30%"


def test_normalize_keeps_text_with_real_newlines_untouched():
    raw = "第一条 总则\n第二条 付款方式\n"
    assert normalize_contract_text(raw) == raw


def test_normalize_is_idempotent():
    once = normalize_contract_text("甲\\n乙")
    assert normalize_contract_text(once) == once
```

### Step 2：运行，确认失败（RED）

```powershell
.venv\Scripts\python.exe -m pytest tests/test_contract_review_prefill.py -k normalize -v
```

预期：3 个用例失败，报 `ModuleNotFoundError: ... prefill_prompts`。

## Task 2：实现换行归一化（GREEN）

**文件：** 新建 `app/capabilities/contract_review/prefill_prompts.py`

### Step 1：写入

```python
"""预填链路的输入归一化与 prompt 参数构造。只被 prefill 链路使用。"""


def normalize_contract_text(text: str) -> str:
    """把「一整行 + 字面量 \\n」形态的正文还原为真换行。

    保守策略：仅当文本内**不含任何真换行**时才替换，避免误改正文里本就存在的字面量 "\\n"。
    """
    if "\n" in text:
        return text
    return text.replace("\\n", "\n")
```

### Step 2：运行，确认转绿

```powershell
.venv\Scripts\python.exe -m pytest tests/test_contract_review_prefill.py -k normalize -v
```

预期：3 个用例通过。

### Step 3：拿真实样例人工核验一次（非自动测试）

> `tmp/samples/c1.md` 已被 `.gitignore` 覆盖，**不写进自动测试**（否则换台机器必红）。用一个一次性脚本确认即可：

```python
import pathlib, sys
sys.path.insert(0, ".")
from app.capabilities.contract_review.prefill_prompts import normalize_contract_text

raw = pathlib.Path("tmp/samples/c1.md").read_text(encoding="utf-8")
out = normalize_contract_text(raw)
print("before newlines:", raw.count("\n"), "after newlines:", out.count("\n"))
print("top-level titles:", sum(1 for ln in out.splitlines() if ln.startswith("# 第")))
```

预期：before `0`（或 1）、after **16**，top-level titles **16**（对齐设计文档 §4.5 的实测数）。

## Task 3：写失败测试 —— 预填响应模型

**文件：** 追加到 `tests/test_contract_review_prefill.py`

### Step 1：追加

```python
from app.capabilities.contract_review.prefill_schemas import PrefillData, PrefillPayload


def test_prefill_payload_defaults_are_all_null_and_empty():
    payload = PrefillPayload()
    assert payload.contract_info.payment_terms is None
    assert payload.contract_info.inspection_count is None
    assert payload.contract_plan == []
    assert payload.finance_info.contract_amount is None
    assert payload.guarantee == []


def test_prefill_payload_has_exactly_four_top_level_keys():
    assert list(PrefillPayload().model_dump().keys()) == [
        "contract_info",
        "contract_plan",
        "finance_info",
        "guarantee",
    ]


def test_prefill_data_failed_keeps_full_structure():
    data = PrefillData(prefill_status="failed")
    dumped = data.model_dump()
    assert dumped["mode"] == "prefill"
    assert dumped["prefill_status"] == "failed"
    assert dumped["prefill"]["contract_plan"] == []
    assert dumped["prefill"]["guarantee"] == []


def test_prefill_evidence_requires_quote_allows_null_section():
    from app.capabilities.contract_review.prefill_schemas import PrefillEvidence

    assert PrefillEvidence(quote="合同签订后7个工作日内").section is None
    assert PrefillEvidence(section="第四条 付款方式及条件", quote="…").section == "第四条 付款方式及条件"
```

### Step 2：运行，确认失败（RED）

```powershell
.venv\Scripts\python.exe -m pytest tests/test_contract_review_prefill.py -k "prefill_payload or prefill_data or evidence" -v
```

预期：4 个用例失败，报 `ModuleNotFoundError: ... prefill_schemas`。

## Task 4：实现预填响应模型（GREEN）

**文件：** 新建 `app/capabilities/contract_review/prefill_schemas.py`

### Step 1：写入完整文件

```python
"""智能预填的响应模型。**独立于 ContractReviewData**，评审响应模型零改动。"""
from typing import Literal

from pydantic import BaseModel, Field

PrefillStatus = Literal["ok", "failed"]


class PrefillEvidence(BaseModel):
    """原文依据。section 取顶层条款标题原文，原文无标题结构时为 null。"""

    section: str | None = None
    quote: str = ""


class ContractInfo(BaseModel):
    """D-02 合同信息（9 字段）。本组不附 evidence。"""

    payment_terms: str | None = None
    payment_method: str | None = None
    service_content: str | None = None
    service_valid_months: float | None = None
    service_sla: str | None = None
    service_start_date: str | None = None
    service_end_date: str | None = None
    onsite_service_count: float | None = None
    inspection_count: float | None = None


class ContractPlanItem(BaseModel):
    """D-02 合同计划（数组，每项 8 字段）。"""

    milestone_name: str | None = None
    milestone_code: str | None = None
    milestone_text: str | None = None
    milestone_seq: int | None = None
    plan_finish_date: str | None = None
    plan_payment_date: str | None = None
    payment_amount: float | None = None
    evidence: list[PrefillEvidence] = Field(default_factory=list)


class FinanceInfo(BaseModel):
    """D-03 财务信息（2 字段）。本组不附 evidence。"""

    contract_amount: float | None = None
    currency: str | None = None


class GuaranteeItem(BaseModel):
    """D-03 履约保证金 / 保函（数组，每项 7 字段，支持多笔）。"""

    type: str | None = None
    amount: float | None = None
    payee: str | None = None
    bank_name: str | None = None
    bank_account: str | None = None
    return_clause: str | None = None
    evidence: list[PrefillEvidence] = Field(default_factory=list)


class PrefillPayload(BaseModel):
    """四组固定结构。未请求 / 未抽到的组按「未取到」表达，不省略键。"""

    contract_info: ContractInfo = Field(default_factory=ContractInfo)
    contract_plan: list[ContractPlanItem] = Field(default_factory=list)
    finance_info: FinanceInfo = Field(default_factory=FinanceInfo)
    guarantee: list[GuaranteeItem] = Field(default_factory=list)


class PrefillData(BaseModel):
    """mode=prefill 的 data 段。不含 overall_result / check_time / checks / metrics。"""

    mode: Literal["prefill"] = "prefill"
    prefill_status: PrefillStatus
    prefill: PrefillPayload = Field(default_factory=PrefillPayload)
```

> `type` 声明为 `str | None` 而非 `Literal["履约保函","履约保证金"]`：**枚举约束由 json_schema 在模型侧强制**（Task 6），Pydantic 侧放宽可避免模型偶发越界导致整份预填降级为 `failed`。

### Step 2：运行，确认转绿

```powershell
.venv\Scripts\python.exe -m pytest tests/test_contract_review_prefill.py -v
```

预期：全部通过。

## Task 5：写失败测试 —— 预填 schema 与字段清单逐字段一致、且按 scope 变组

**文件：** 追加到 `tests/test_contract_review_prefill.py`

### Step 1：追加

```python
from app.capabilities.contract_review.prefill_response_formats import (
    SCOPE_GROUPS,
    get_prefill_response_format,
    get_prefill_top_level_keys,
)

_EXPECTED = {
    "contract_info": [
        "payment_terms", "payment_method", "service_content", "service_valid_months",
        "service_sla", "service_start_date", "service_end_date",
        "onsite_service_count", "inspection_count",
    ],
    "contract_plan": [
        "milestone_name", "milestone_code", "milestone_text", "milestone_seq",
        "plan_finish_date", "plan_payment_date", "payment_amount", "evidence",
    ],
    "finance_info": ["contract_amount", "currency"],
    "guarantee": [
        "type", "amount", "payee", "bank_name", "bank_account", "return_clause", "evidence",
    ],
}


def _schema_of(scope: str) -> dict:
    return get_prefill_response_format(scope)["json_schema"]["schema"]


def test_scope_groups_match_with_design():
    assert SCOPE_GROUPS["d02"] == ("contract_info", "contract_plan")
    assert SCOPE_GROUPS["d03"] == ("finance_info", "guarantee")
    assert SCOPE_GROUPS["all"] == ("contract_info", "contract_plan", "finance_info", "guarantee")
    assert get_prefill_top_level_keys("d03") == ["finance_info", "guarantee"]


def test_schema_scope_only_exposes_requested_groups():
    assert list(_schema_of("d02")["properties"].keys()) == ["contract_info", "contract_plan"]
    assert list(_schema_of("d03")["properties"].keys()) == ["finance_info", "guarantee"]
    assert list(_schema_of("all")["properties"].keys()) == [
        "contract_info", "contract_plan", "finance_info", "guarantee",
    ]
    assert _schema_of("d02")["required"] == ["contract_info", "contract_plan"]


def test_schema_fields_match_design_field_list_exactly():
    props = _schema_of("all")["properties"]
    assert list(props["contract_info"]["properties"].keys()) == _EXPECTED["contract_info"]
    assert list(props["contract_plan"]["items"]["properties"].keys()) == _EXPECTED["contract_plan"]
    assert list(props["finance_info"]["properties"].keys()) == _EXPECTED["finance_info"]
    assert list(props["guarantee"]["items"]["properties"].keys()) == _EXPECTED["guarantee"]


def test_evidence_is_object_array_with_section_and_quote():
    evidence = _schema_of("all")["properties"]["contract_plan"]["items"]["properties"]["evidence"]
    assert evidence["type"] == "array"
    assert list(evidence["items"]["properties"].keys()) == ["section", "quote"]


def test_schema_is_strict_and_named_per_scope():
    for scope in ("all", "d02", "d03"):
        fmt = get_prefill_response_format(scope)
        assert fmt["type"] == "json_schema"
        assert fmt["json_schema"]["strict"] is True
        assert fmt["json_schema"]["name"] == f"contract_review_prefill_{scope}"


def test_get_prefill_response_format_returns_independent_copies():
    first = get_prefill_response_format("all")
    first["json_schema"]["schema"]["properties"]["contract_info"]["properties"]["payment_terms"] = {}
    assert _schema_of("all")["properties"]["contract_info"]["properties"]["payment_terms"] != {}
```

### Step 2：运行，确认失败（RED）

```powershell
.venv\Scripts\python.exe -m pytest tests/test_contract_review_prefill.py -v
```

预期：新增 6 个用例全红（`ModuleNotFoundError: ... prefill_response_formats`），Task 1-4 的用例仍绿。

## Task 6：实现预填 schema（GREEN）

**文件：** 新建 `app/capabilities/contract_review/prefill_response_formats.py`

> **为什么不写进 `response_formats.py`**：§10 的"不改 `response_formats.py`"这条红线要保持有效，所以预填 schema 独立成模块。复用它的两个**公共构造习惯**（`_nullable_string` / `_object`）—— 通过 import，不复制、不改动那个文件。

### Step 1：写入完整文件

```python
"""智能预填的结构化输出 schema。独立模块，response_formats.py 零改动。"""
from copy import deepcopy
from typing import Any

from app.capabilities.contract_review.response_formats import _nullable_string, _object


def _nullable_number() -> dict[str, Any]:
    """金额 / 计数：只允许 JSON number（不给 string），避免模型输出千分位导致解析失败。"""
    return {"type": ["number", "null"]}


def _nullable_integer() -> dict[str, Any]:
    return {"type": ["integer", "null"]}


EVIDENCE_SCHEMA = _object({
    "section": _nullable_string(),
    "quote": _nullable_string(max_length=60),
})


CONTRACT_INFO_SCHEMA = _object({
    "payment_terms": _nullable_string(),
    "payment_method": _nullable_string(),
    "service_content": _nullable_string(),
    "service_valid_months": _nullable_number(),
    "service_sla": _nullable_string(),
    "service_start_date": _nullable_string(max_length=10),
    "service_end_date": _nullable_string(max_length=10),
    "onsite_service_count": _nullable_number(),
    "inspection_count": _nullable_number(),
})


CONTRACT_PLAN_SCHEMA = {
    "type": "array",
    "items": _object({
        "milestone_name": _nullable_string(),
        "milestone_code": _nullable_string(),
        "milestone_text": _nullable_string(),
        "milestone_seq": _nullable_integer(),
        "plan_finish_date": _nullable_string(max_length=10),
        "plan_payment_date": _nullable_string(max_length=10),
        "payment_amount": _nullable_number(),
        "evidence": {"type": "array", "items": deepcopy(EVIDENCE_SCHEMA)},
    }),
}


FINANCE_INFO_SCHEMA = _object({
    "contract_amount": _nullable_number(),
    "currency": _nullable_string(max_length=8),
})


GUARANTEE_SCHEMA = {
    "type": "array",
    "items": _object({
        "type": {"type": ["string", "null"], "enum": ["履约保函", "履约保证金", None]},
        "amount": _nullable_number(),
        "payee": _nullable_string(),
        "bank_name": _nullable_string(),
        "bank_account": _nullable_string(),
        "return_clause": _nullable_string(),
        "evidence": {"type": "array", "items": deepcopy(EVIDENCE_SCHEMA)},
    }),
}


_GROUP_SCHEMAS: dict[str, Any] = {
    "contract_info": CONTRACT_INFO_SCHEMA,
    "contract_plan": CONTRACT_PLAN_SCHEMA,
    "finance_info": FINANCE_INFO_SCHEMA,
    "guarantee": GUARANTEE_SCHEMA,
}

SCOPE_GROUPS: dict[str, tuple[str, ...]] = {
    "all": ("contract_info", "contract_plan", "finance_info", "guarantee"),
    "d02": ("contract_info", "contract_plan"),
    "d03": ("finance_info", "guarantee"),
}


def get_prefill_top_level_keys(scope: str) -> list[str]:
    """该 scope 下模型必须输出的顶层键（同时用作 required_keys 内容兜底）。"""
    return list(SCOPE_GROUPS[scope])


def get_prefill_response_format(scope: str) -> dict[str, Any]:
    groups = SCOPE_GROUPS[scope]
    return {
        "type": "json_schema",
        "json_schema": {
            "name": f"contract_review_prefill_{scope}",
            "strict": True,
            "schema": _object({name: deepcopy(_GROUP_SCHEMAS[name]) for name in groups}),
        },
    }
```

### Step 2：运行，确认转绿

```powershell
.venv\Scripts\python.exe -m pytest tests/test_contract_review_prefill.py -v
```

预期：全部通过。

## Task 7：给 `_invoke_json_prompt` 加一个显式的 `response_format` 入参

**为什么必须**：`_invoke_json_prompt` 现在自己用 `get_response_format(prompt_name)`（`service.py:296`）查表；预填的 schema 不在那张表里（Task 6 的决定）。需要一个**默认 `None`、不改任何既有行为**的可选入参。

**文件：** 修改 `app/capabilities/contract_review/service.py`

### Step 1：把 `_invoke_json_prompt` 签名（`service.py:284-293`）里的

```python
    metric_name: str | None = None,
    **kwargs,
) -> dict:
```

改为

```python
    metric_name: str | None = None,
    response_format: dict | None = None,
    **kwargs,
) -> dict:
```

### Step 2：把 `service.py:296` 的

```python
    response_format = get_response_format(prompt_name)
```

改为

```python
    if response_format is None:
        response_format = get_response_format(prompt_name)
```

> 既有调用方一个字不改，行为逐字节不变（`response_format` 默认 `None` → 仍查表）。

### Step 3：验证既有行为未变（回归）

```powershell
.venv\Scripts\python.exe -m pytest tests/test_contract_review_service.py tests/test_contract_review_api.py tests/test_contract_review_prompts.py -q
```

预期：全绿。

## Task 8：写预填 prompt（含 per-scope 字段说明）

**文件：** 修改 `prompts/contract_review.yaml`（**追加一条**，现有 7 条一个字不动）

### Step 1：在文件末尾追加

```yaml
prefill:
  system: |
    你是一个合同信息抽取助手。只抽取合同里明确写出的信息，不做判断、不下结论、不给建议。
    【重要】只输出纯JSON，不要任何解释文字、不要markdown代码块、不要思考过程。
    【原文依据】每条依据必须来自合同原文；quote 为原文片段（≤60字，不改写、不翻译）；禁止编造。
    【取不到就留空】原文没有写的一律返回 null（数组返回 []），不要用空字符串、不要猜。
    【日期】一律 YYYY-MM-DD；原文只给相对表述（如"合同签订后7个工作日内"）时，
    只有在能由已抽到的明确日期直接推出时才填，推不出返回 null。
    【金额】一律返回数字（含税，两位小数），不要千分位、不要"元"、不要货币符号。
    【章节位置】每条依据必须带 section：取该原文所在的顶层条款标题原文
    （如"第四条 付款方式及条件"、"合同计划"）；原文没有标题结构时 section 返回 null。
  user: |
    请从下面的合同全文中抽取以下字段。

    一、抽取字段清单
    {field_spec}

    二、输出 JSON 结构示例
    {json_example}

    三、硬性要求
    - 只返回一个 JSON 对象，顶层键必须恰好是：{top_level_keys}，不多不少。
    - {scope_note}
    - contract_plan 按 milestone_seq 升序返回；milestone_seq 从 1 起，按付款条件原文的顺序编号。
    - milestone_name 必须从这 13 个标准里程碑名里选一个，取不到语义相近的填 null：
      启动(begin)、环境确认(confirm)、交付(deliver)、设计(design)、开发(develop)、
      维护期(end)、终验(finalaccept)、阶段维护(midmaintain)、策划(plan)、初验(preaccept)、
      需求(require)、测试(test)、试运行(testrun)；milestone_code 填对应的英文 code。
    - payment_method 只取支付手段（电汇/转账/汇票/承兑…）；payment_terms 取分期与条件条款的整段原文。
      两者只有同一处原文时，payment_method 只取其中的支付手段词，其余归 payment_terms，不整段重复。

    【合同全文】
    {contract_md}
```

> ⚠️ **模板里绝不能出现单个 `{` 或 `}`**（`build_prompt` 走 `.format(**kwargs)`）。所有 JSON 示例都通过 `{json_example}` 变量注入，**不写进模板**。

### Step 2：写渲染测试（**本步会红**，Task 9 实现 `build_prefill_messages` 后转绿）

**文件：** 追加到 `tests/test_contract_review_prefill.py`

```python
def test_prefill_prompt_renders_for_every_scope():
    from app.capabilities.contract_review.prefill_prompts import build_prefill_messages

    for scope in ("all", "d02", "d03"):
        messages = build_prefill_messages(scope, "第一条 总则")
        assert len(messages) == 2
        text = messages[1].content
        assert "第一条 总则" in text
        for key in get_prefill_top_level_keys(scope):
            assert key in text
```

### Step 3：运行（先红后绿）

```powershell
.venv\Scripts\python.exe -m pytest tests/test_contract_review_prefill.py -k prompt_renders -v
```

## Task 9：实现 `build_prefill_messages` 与 per-scope 字段说明（GREEN）

**文件：** 追加到 `app/capabilities/contract_review/prefill_prompts.py`

### Step 1：追加（模块内新增 import 到文件顶部：`from langchain_core.messages import BaseMessage`、`from app.capabilities.contract_review.prompts import build_prompt`）

```python
_SCOPE_NOTES = {
    "all": "本次请求两组场景的全部字段，四组都要返回。",
    "d02": "本次请求 D-02（合同管理员预填）字段，只需返回 contract_info 与 contract_plan 两组。",
    "d03": "本次请求 D-03（销售预填）字段，只需返回 finance_info 与 guarantee 两组。",
}

_FIELDS = {
    "contract_info": """1) contract_info（对象，9 个字段）
   - payment_terms 付款条件：分期与条件条款的整段原文
   - payment_method 付款方式：支付手段（如"电汇"）
   - service_content 服务内容及方式：原文
   - service_valid_months 服务有效期限（月）：数字
   - service_sla 服务级别（SLA）：原文
   - service_start_date 服务开始时间：YYYY-MM-DD
   - service_end_date 服务结束时间：YYYY-MM-DD
   - onsite_service_count 现场服务次数：数字
   - inspection_count 巡检次数：数字""",
    "contract_plan": """2) contract_plan（数组，每个付款阶段一项，每项 8 个字段）
   - milestone_name 里程碑标准名 / milestone_code 对应 code
   - milestone_text 里程碑原文描述 / milestone_seq 阶段序号（从 1 起）
   - plan_finish_date 计划完成时间：YYYY-MM-DD
   - plan_payment_date 计划回款时间：YYYY-MM-DD
   - payment_amount 回款金额：数字（含税，两位小数）
   - evidence：该行全部字段的原文出处，按出处各列一条、去重；每个元素是
     {"section": 顶层条款标题原文或 null, "quote": 原文片段（≤60字）}；
     一行通常 2-3 条（付款条件、合同计划章节或交付/验收条款、合同金额条款）""",
    "finance_info": """3) finance_info（对象，2 个字段）
   - contract_amount 合同额：数字（含税，两位小数）
   - currency 币种：如 "CNY\"""",
    "guarantee": """4) guarantee（数组，支持多笔、不设上限，无则 []，每项 7 个字段）
   - type 申请类型：只能取 "履约保函" 或 "履约保证金"
   - amount 申请金额：数字（含税，两位小数；原文写"按合同金额的5%收取"时按合同额计算）
   - payee 收款单位/受益人 / bank_name 银行名称 / bank_account 银行账号（甲方开户信息）
   - return_clause 归还条款：原文
   - evidence：同 contract_plan 的 evidence 结构""",
}

_EXAMPLES = {
    "contract_info": '{"contract_info": {"payment_terms": null, "payment_method": null, '
                     '"service_content": null, "service_valid_months": null, "service_sla": null, '
                     '"service_start_date": null, "service_end_date": null, '
                     '"onsite_service_count": null, "inspection_count": null}}',
    "contract_plan": '{"contract_plan": [{"milestone_name": "启动", "milestone_code": "begin", '
                     '"milestone_text": "合同签订及预付款", "milestone_seq": 1, '
                     '"plan_finish_date": null, "plan_payment_date": null, "payment_amount": null, '
                     '"evidence": [{"section": "第四条 付款方式及条件", "quote": "合同签订后7个工作日内支付30%"}]}]}',
    "finance_info": '{"finance_info": {"contract_amount": null, "currency": "CNY"}}',
    "guarantee": '{"guarantee": [{"type": "履约保证金", "amount": null, "payee": null, '
                 '"bank_name": null, "bank_account": null, "return_clause": null, '
                 '"evidence": [{"section": "第八条 履约保证金", "quote": "按合同金额的5%收取"}]}]}',
}


def _json_example(scope: str) -> str:
    """按 scope 组装示例：单组直接返回该组示例，多组拼成一个合法 JSON 对象。

    注意 scope 名（all/d02/d03）与组名（contract_info/…）不是一回事，
    必须经 SCOPE_GROUPS 映射后再取 _EXAMPLES。（原稿此处直接 _EXAMPLES[scope]，
    执行时被 test_prefill_prompt_renders_for_every_scope 抓到 KeyError: 'd02'，已修正。）
    """
    groups = SCOPE_GROUPS[scope]
    if len(groups) == 1:
        return _EXAMPLES[groups[0]]
    inner = ", ".join(_EXAMPLES[name].strip()[1:-1] for name in groups)
    return "{" + inner + "}"


def prefill_prompt_kwargs(scope: str, contract_md: str) -> dict:
    """构造 `build_prompt("prefill", **kwargs)` 所需的全部模板变量。

    真实链路（prefill_service）与测试（build_prefill_messages）共用这一处，
    保证「测到的就是跑到的」。
    """
    groups = SCOPE_GROUPS[scope]
    return {
        "field_spec": "\n\n".join(_FIELDS[name] for name in groups),
        "json_example": _json_example(scope),
        "top_level_keys": "、".join(groups),
        "scope_note": _SCOPE_NOTES[scope],
        "contract_md": contract_md,
    }


def build_prefill_messages(scope: str, contract_md: str) -> list[BaseMessage]:
    return build_prompt("prefill", **prefill_prompt_kwargs(scope, contract_md))
```

> ⚠️ `_FIELDS` / `_EXAMPLES` 里的 `{` `}` 是**普通 Python 字符串里的字面量**（作为 `.format()` 的**入参值**注入），**不要写成 `{{` `}}`** —— 那会导致实际输出里出现双花括号。只有 yaml 模板正文里的花括号才需要双写（本计划已把全部 JSON 示例移出模板，故模板里没有花括号）。

> 顶部需 import：`from app.capabilities.contract_review.prefill_response_formats import SCOPE_GROUPS`。

### Step 2：运行，确认转绿

```powershell
.venv\Scripts\python.exe -m pytest tests/test_contract_review_prefill.py -v
```

预期：全部通过。

## Task 10：请求模型加 `mode` / `prefill_scope`

**文件：** 修改 `app/capabilities/contract_review/schemas.py`

### Step 1：把 `ContractReviewRequest`（`schemas.py:18-20`）改为

```python
class ContractReviewRequest(BaseModel):
    contract_md: str = Field(..., min_length=1)
    attachments: list[AttachmentInput] = Field(default_factory=list)
    mode: Literal["review", "prefill"] = "review"
    prefill_scope: Literal["all", "d02", "d03"] = "all"
```

（`Literal` 该文件已导入。**这是本计划对该文件唯一改动**。）

### Step 2：写测试并运行

追加到 `tests/test_contract_review_prefill.py`：

```python
from app.capabilities.contract_review.schemas import ContractReviewRequest


def test_request_defaults_to_review_mode():
    req = ContractReviewRequest(contract_md="正文")
    assert req.mode == "review"
    assert req.prefill_scope == "all"


def test_request_accepts_prefill_scope_values():
    for scope in ("all", "d02", "d03"):
        assert ContractReviewRequest(contract_md="正文", mode="prefill", prefill_scope=scope).prefill_scope == scope
```

```powershell
.venv\Scripts\python.exe -m pytest tests/test_contract_review_prefill.py tests/test_contract_review_schemas.py tests/test_contract_review_api.py -q
```

预期：全绿。**「不传 `mode` 就是老行为」由默认值保证**，既有 API 测试即回归判据。

## Task 11：写失败测试 —— 预填编排（scope 选组、失败兜底、排序）

**文件：** 追加到 `tests/test_contract_review_prefill.py`

### Step 1：追加

```python
from unittest.mock import patch

from app.capabilities.contract_review.prefill_service import run_prefill
from app.capabilities.contract_review.schemas import ContractReviewRequest


def _request(scope="all", md="正文"):
    return ContractReviewRequest(contract_md=md, mode="prefill", prefill_scope=scope)


def _ok_payload():
    return {
        "contract_info": {"payment_terms": "分期", "payment_method": "电汇"},
        "contract_plan": [
            {"milestone_name": "终验", "milestone_seq": 3, "payment_amount": 100.0},
            {"milestone_name": "启动", "milestone_seq": 1, "payment_amount": 200.0},
        ],
        "finance_info": {"contract_amount": 10492500.0, "currency": "CNY"},
        "guarantee": [{"type": "履约保证金", "amount": 524625.0}],
    }


def test_run_prefill_all_returns_four_groups_ok():
    with patch("app.capabilities.contract_review.prefill_service._invoke_json_prompt", return_value=_ok_payload()):
        data = run_prefill(_request("all"))
    dumped = data.model_dump()
    assert dumped["prefill_status"] == "ok"
    assert dumped["prefill"]["finance_info"]["contract_amount"] == 10492500.0
    assert len(dumped["prefill"]["guarantee"]) == 1


def test_run_prefill_d03_blanks_unrequested_groups():
    with patch("app.capabilities.contract_review.prefill_service._invoke_json_prompt", return_value=_ok_payload()):
        dumped = run_prefill(_request("d03")).model_dump()
    assert dumped["prefill"]["contract_info"]["payment_terms"] is None
    assert dumped["prefill"]["contract_plan"] == []
    assert dumped["prefill"]["finance_info"]["currency"] == "CNY"


def test_run_prefill_sorts_plan_by_milestone_seq():
    with patch("app.capabilities.contract_review.prefill_service._invoke_json_prompt", return_value=_ok_payload()):
        dumped = run_prefill(_request("d02")).model_dump()
    assert [row["milestone_seq"] for row in dumped["prefill"]["contract_plan"]] == [1, 3]


def test_run_prefill_asks_model_for_scope_specific_schema_and_keys():
    with patch("app.capabilities.contract_review.prefill_service._invoke_json_prompt", return_value=_ok_payload()) as mocked:
        run_prefill(_request("d03"))
    kwargs = mocked.call_args.kwargs
    assert kwargs["required_keys"] == ["finance_info", "guarantee"]
    assert kwargs["response_format"]["json_schema"]["name"] == "contract_review_prefill_d03"


def test_run_prefill_normalizes_newlines_before_prompt():
    captured = {}

    def fake(prompt_name, **kwargs):
        captured.update(kwargs)
        return _ok_payload()

    with patch("app.capabilities.contract_review.prefill_service._invoke_json_prompt", side_effect=fake):
        run_prefill(_request("d03", md="第一条 总则\\n第二条 付款"))
    assert captured["contract_md"] == "第一条 总则\n第二条 付款"


def test_run_prefill_returns_failed_on_model_error():
    with patch(
        "app.capabilities.contract_review.prefill_service._invoke_json_prompt",
        side_effect=RuntimeError("boom"),
    ):
        dumped = run_prefill(_request("all")).model_dump()
    assert dumped["prefill_status"] == "failed"
    assert dumped["prefill"]["contract_plan"] == []
    assert dumped["prefill"]["finance_info"]["contract_amount"] is None
```

### Step 2：运行，确认失败（RED）

```powershell
.venv\Scripts\python.exe -m pytest tests/test_contract_review_prefill.py -k run_prefill -v
```

预期：6 个用例全红（`ModuleNotFoundError: ... prefill_service`）。

## Task 12：实现预填编排（GREEN）

**文件：** 新建 `app/capabilities/contract_review/prefill_service.py`

### Step 1：写入完整文件

```python
"""智能预填编排。与评审链路完全独立：不调用 review_contract，也不共享状态。"""
from app.capabilities.contract_review.prefill_prompts import normalize_contract_text, prefill_prompt_kwargs
from app.capabilities.contract_review.prefill_response_formats import (
    SCOPE_GROUPS,
    get_prefill_response_format,
    get_prefill_top_level_keys,
)
from app.capabilities.contract_review.prefill_schemas import PrefillData, PrefillPayload
from app.capabilities.contract_review.schemas import ContractReviewRequest
from app.capabilities.contract_review.service import _invoke_json_prompt
from app.core.logging import get_logger

logger = get_logger("contract_review_prefill")


def _plan_sort_key(row) -> tuple[bool, int]:
    raw = row.get("milestone_seq") if isinstance(row, dict) else None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = None
    return (value is None, value or 0)


def _build_payload(scope: str, payload: dict) -> PrefillPayload:
    groups = set(SCOPE_GROUPS[scope])
    data: dict = {}
    if "contract_info" in groups:
        data["contract_info"] = payload.get("contract_info") or {}
    if "contract_plan" in groups:
        rows = payload.get("contract_plan") or []
        data["contract_plan"] = sorted(rows, key=_plan_sort_key) if isinstance(rows, list) else []
    if "finance_info" in groups:
        data["finance_info"] = payload.get("finance_info") or {}
    if "guarantee" in groups:
        rows = payload.get("guarantee") or []
        data["guarantee"] = rows if isinstance(rows, list) else []
    return PrefillPayload.model_validate(data)


def run_prefill(request: ContractReviewRequest) -> PrefillData:
    """执行预填。任何失败都降级为 prefill_status=failed + 全空结构，HTTP 仍为成功。"""
    scope = request.prefill_scope
    contract_md = normalize_contract_text(request.contract_md)
    try:
        payload = _invoke_json_prompt(
            "prefill",
            required_keys=get_prefill_top_level_keys(scope),
            validation_label=f"预填-{scope}",
            response_format=get_prefill_response_format(scope),
            **prefill_prompt_kwargs(scope, contract_md),
        )
        return PrefillData(prefill_status="ok", prefill=_build_payload(scope, payload))
    except Exception:
        logger.exception("prefill failed", extra={"prefill_scope": scope})
        return PrefillData(prefill_status="failed")
```

> **依赖说明**：本模块在**模块顶层** import `service._invoke_json_prompt`，**不存在循环导入** —— `service.py` 不反向 import 本模块（`service` 与 `prefill_service` 是单向依赖，`router` 只 import 后者）。
> `prefill_prompt_kwargs(scope, md)` 把 `{field_spec}` / `{json_example}` / `{top_level_keys}` / `{scope_note}` / `{contract_md}` 五个模板变量一次给全，`_invoke_json_prompt` 会透传给 `build_prompt("prefill", **kwargs)`。
> `except Exception` 是**设计要求的兜底**（§6：调用失败 / 超时 / 输出超长 → `prefill_status: "failed"`，HTTP 仍成功）；用 `logger.exception` 保证异常栈可查，不是静默吞错。

### Step 2：运行，确认转绿

```powershell
.venv\Scripts\python.exe -m pytest tests/test_contract_review_prefill.py -v
```

预期：全部通过。

## Task 13：路由层按 `mode` 分流

**文件：** 修改 `app/capabilities/contract_review/router.py`

### Step 1：import 区加一行

```python
from app.capabilities.contract_review.prefill_service import run_prefill
```

### Step 2：把 `contract_review_endpoint`（`router.py:11-17`）改为

```python
@router.post("/contract-review")
def contract_review_endpoint(request: ContractReviewRequest) -> dict:
    if request.mode == "prefill":
        data = run_prefill(request)
    else:
        data = review_contract(request)
    body = ApiResponse(data=data).to_dict()
    body.setdefault("traceId", "")
    body.setdefault("duration_seconds", 0.0)
    return body
```

> `review_contract()` 本身与 `/contract-review/upload-md` 一行不改；预填不提供 multipart 形态。

### Step 3：验证分流

追加到 `tests/test_contract_review_prefill.py`：

```python
def _client():
    from fastapi.testclient import TestClient

    from app.main import create_app

    return TestClient(create_app(register_middleware=False))


def test_router_routes_prefill_by_mode():
    with patch("app.capabilities.contract_review.router.run_prefill") as prefill, patch(
        "app.capabilities.contract_review.router.review_contract"
    ) as review:
        prefill.return_value = PrefillData(prefill_status="ok")
        _client().post("/api/v1/contract-review", json={"contract_md": "正文", "mode": "prefill"})
    assert prefill.call_count == 1
    assert review.call_count == 0


def test_router_keeps_review_path_for_default_mode():
    from app.capabilities.contract_review.schemas import CheckItem, ContractReviewData

    fake = ContractReviewData(
        overall_result="PASS",
        check_time="2026-09-16T10:00:00",
        checks=[CheckItem(id="序号1", name="合同首页完整性", result="PASS", block_level="通过")],
    )
    with patch("app.capabilities.contract_review.router.review_contract", return_value=fake) as review, patch(
        "app.capabilities.contract_review.router.run_prefill"
    ) as prefill:
        _client().post("/api/v1/contract-review", json={"contract_md": "正文"})
    assert review.call_count == 1
    assert prefill.call_count == 0
```

```powershell
.venv\Scripts\python.exe -m pytest tests/test_contract_review_prefill.py -q
```

预期：全绿。

## Task 14：预填契约测试（响应形状 / 兜底 / 非法值）

**文件：** 追加到 `tests/test_contract_review_prefill.py`

### Step 1：追加

```python
def test_prefill_response_data_has_only_three_keys():
    with patch("app.capabilities.contract_review.router.run_prefill", return_value=PrefillData(prefill_status="ok")):
        body = _client().post(
            "/api/v1/contract-review", json={"contract_md": "正文", "mode": "prefill"}
        ).json()
    assert body["code"] == 0
    assert set(body["data"].keys()) == {"mode", "prefill_status", "prefill"}
    assert body["data"]["mode"] == "prefill"
    assert set(body["data"]["prefill"].keys()) == {
        "contract_info", "contract_plan", "finance_info", "guarantee",
    }


def test_prefill_response_never_contains_review_keys():
    with patch("app.capabilities.contract_review.router.run_prefill", return_value=PrefillData(prefill_status="failed")):
        body = _client().post(
            "/api/v1/contract-review", json={"contract_md": "正文", "mode": "prefill"}
        ).json()
    for key in ("overall_result", "check_time", "checks", "metrics"):
        assert key not in body["data"]
    assert body["data"]["prefill_status"] == "failed"


def test_prefill_scope_d03_returns_blank_unrequested_groups():
    with patch("app.capabilities.contract_review.router.run_prefill", return_value=PrefillData(prefill_status="ok")):
        body = _client().post(
            "/api/v1/contract-review",
            json={"contract_md": "正文", "mode": "prefill", "prefill_scope": "d03"},
        ).json()
    assert body["data"]["prefill"]["contract_plan"] == []
    assert body["data"]["prefill"]["contract_info"]["payment_terms"] is None


def test_review_response_shape_is_unchanged_and_has_no_mode_key():
    from app.capabilities.contract_review.schemas import CheckItem, ContractReviewData

    fake = ContractReviewData(
        overall_result="PASS",
        check_time="2026-09-16T10:00:00",
        checks=[CheckItem(id="序号1", name="合同首页完整性", result="PASS", block_level="通过")],
    )
    with patch("app.capabilities.contract_review.router.review_contract", return_value=fake):
        body = _client().post("/api/v1/contract-review", json={"contract_md": "正文"}).json()
    assert set(body["data"].keys()) == {"overall_result", "check_time", "checks", "metrics"}
    assert "mode" not in body["data"]


def test_invalid_mode_returns_10001():
    response = _client().post(
        "/api/v1/contract-review", json={"contract_md": "正文", "mode": "review_prefill"}
    )
    assert response.status_code == 422
    assert response.json()["code"] == 10001


def test_invalid_prefill_scope_returns_10001():
    response = _client().post(
        "/api/v1/contract-review", json={"contract_md": "正文", "mode": "prefill", "prefill_scope": "d01"}
    )
    assert response.status_code == 422
    assert response.json()["code"] == 10001


def test_prefill_ignores_attachments():
    with patch("app.capabilities.contract_review.router.run_prefill", return_value=PrefillData(prefill_status="ok")):
        response = _client().post(
            "/api/v1/contract-review",
            json={
                "contract_md": "正文",
                "mode": "prefill",
                "attachments": [{"filename": "附件一.md", "text": "附件正文"}],
            },
        )
    assert response.status_code == 200
```

### Step 2：运行

```powershell
.venv\Scripts\python.exe -m pytest tests/test_contract_review_prefill.py -v
```

预期：全部通过。

## Task 15：回归测试 —— 预填调用确实携带 schema 与关思考

**文件：** 追加到 `tests/test_contract_review_prefill.py`

> 这条是设计文档 §7 点名的**回归保护**：将来谁把 schema 或关思考去掉，会静默退回"返回思考草稿"的失败态。

```python
def test_prefill_call_carries_strict_schema_and_thinking_off():
    from app.capabilities.contract_review import service as svc

    seen = {}

    def fake_invoke(model, messages, response_format=None):
        seen["model"] = model
        seen["response_format"] = response_format
        return ('{"finance_info": {"contract_amount": 1.0, "currency": "CNY"}, "guarantee": []}', {})

    with patch("app.capabilities.contract_review.service.invoke_model", fake_invoke):
        run_prefill(_request("d03"))

    assert seen["response_format"]["json_schema"]["strict"] is True
    assert seen["response_format"]["json_schema"]["name"] == "contract_review_prefill_d03"
    assert seen["model"].kwargs.get("extra_body") == {"chat_template_kwargs": {"enable_thinking": False}}


def test_prefill_requires_all_scope_top_level_keys():
    from app.capabilities.contract_review.service import _invoke_json_prompt
    from app.core.errors import ModelFormatError

    with patch(
        "app.capabilities.contract_review.service.invoke_model",
        return_value=('{"finance_info": {"contract_amount": 1.0, "currency": "CNY"}}', {}),
    ):
        with pytest.raises(ModelFormatError):
            _invoke_json_prompt(
                "prefill",
                required_keys=["finance_info", "guarantee"],
                response_format=get_prefill_response_format("d03"),
                field_spec="x", json_example="y", top_level_keys="a", scope_note="z",
                contract_md="正文",
            )
```

（`import pytest` 需在本文件顶部；Task 1 建文件时未加，本任务补上。）

```powershell
.venv\Scripts\python.exe -m pytest tests/test_contract_review_prefill.py -v
```

预期：全部通过。第二个用例依赖重试路径也返回缺键的输出 → 抛 `ModelFormatError`。

## Task 16：真实样例抽取调优（人工验收，D1 的真正变量）

**文件（不改代码，只调 prompt）：** `prompts/contract_review.yaml` 的 `prefill` 条目

### Step 1：写一次性脚本，对 `tmp/samples/c1.md` 与 `c2.md` 各跑 `all` / `d02` / `d03`

```powershell
.venv\Scripts\python.exe tmp/run_prefill_samples.py
```

（脚本自建，输出每份样例的 26 字段命中情况 + 耗时 + `prefill_status`。）

### Step 2：验收判据

| 项 | 判据 |
|---|---|
| `prefill_status` | 两份样例、三个 scope **全部 `ok`** |
| 耗时 | `all` ≤ 10s、`d02` ≤ 8s、`d03` ≤ 5s（实测基线：7.42 / 5.66 / 3.01s） |
| 关键闭合校验 | `contract_amount` 与 `contract_plan` 各行 `payment_amount` 之和相等（`c1` 实测 10,492,500.00） |
| `guarantee.amount` | 若原文写"按合同金额的 5%"，应等于 `contract_amount × 5%`（`c1` 实测 524,625.00） |
| 已知缺口 | `contract_info` 9 字段在 `c1` 上只填出 4 个（缺 start/end date、现场服务次数、巡检次数）——**属"合同确实没写"还是"没抽到"，需与用户确认后再决定是否继续调 prompt** |

### Step 3：调 prompt 直到达标（只改 yaml，不改代码）

> 设计文档 §8 已定：D1 的真正变量是**抽取质量**，不是代码量。prompt 调优属于本任务范围。

## Task 17：全量回归 + 红线 + 隔离核验

### Step 1：全量测试

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```

预期：**全绿**，且 `tests/two_stage/` 仍 **467 passed / 0 failed**。
**不得改测试期望凑绿** —— 有红就回查。

### Step 2：红线核验（前两条允许你既有的两个并行改动，不得新增；后两条必须无输出）

```powershell
git status --short app/capabilities/contract_review/two_stage
git status --short app/models/llm.py
git status --short app/capabilities/translate
git status --short app/capabilities/contract_review/response_formats.py
```

### Step 3：逐条核对设计文档 §10「明确不做」

```powershell
git status --short
```

预期改动只落在：`app/capabilities/contract_review/{router,service,schemas}.py`、新增 `prefill_{prompts,schemas,response_formats,service}.py`、`prompts/contract_review.yaml`、`tests/test_contract_review_prefill.py`、`app/core/config.py`（依赖 change）、设计文档与两个 change。

### Step 4：OpenSpec 校验

```powershell
openspec.cmd validate contract-review-mvp-prefill --strict
openspec.cmd validate llm-disable-thinking --strict
```

预期：两条都是 `Change '...' is valid`。

---

## 完成判据

1. `mode=prefill` 返回 `data` 恰好 3 键（`mode` / `prefill_status` / `prefill`），`prefill` 恰好 4 组 26 字段。
2. `mode` 不传或 `=review` 时，`data` 恰好 4 键、**不含 `mode`**，与今天逐字段一致（Task 14 有断言）。
3. 非法 `mode` / `prefill_scope` → HTTP 422 + `code=10001`（已有异常处理，无需新代码）。
4. 模型失败 → HTTP 200 + `prefill_status: "failed"` + 结构完整全空，**不抛 5xx**。
5. `two_stage/`、`app/models/llm.py`、`translate/`、`response_formats.py` **零新增 git 变更条目**；`tests/two_stage/` 仍 467 passed。
6. `c1` / `c2` 三个 scope 全部 `prefill_status: ok`，闭合校验通过。
