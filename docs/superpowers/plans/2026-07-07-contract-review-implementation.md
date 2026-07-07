# Contract Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the LTC403.1-C02 contract organization review capability as a new FastAPI capability package that reviews provided contract Markdown and attachment texts, returning complete PASS/WARN/FAIL/NA check results under the existing `ApiResponse.data` envelope.

**Architecture:** Add an isolated `app/capabilities/contract_review/` package following the existing translate capability pattern. Deterministic rule checks live in focused modules (`party.py`, `checks.py`, `attachments.py`, `preset_client.py`, `utils.py`); LLM calls go only through `app.models.llm.get_chat_model()` and `app.models.llm.invoke_model()`. The router returns the existing `ApiResponse` envelope and registers with `app.main:create_app()`.

**Tech Stack:** FastAPI, Pydantic v2, LangChain messages, pytest, existing `app.core` error/response/middleware infrastructure.

---

## File Structure

Create:

- `app/capabilities/contract_review/__init__.py`
- `app/capabilities/contract_review/schemas.py`
- `app/capabilities/contract_review/utils.py`
- `app/capabilities/contract_review/party.py`
- `app/capabilities/contract_review/preset_client.py`
- `app/capabilities/contract_review/attachments.py`
- `app/capabilities/contract_review/checks.py`
- `app/capabilities/contract_review/prompts.py`
- `app/capabilities/contract_review/service.py`
- `app/capabilities/contract_review/router.py`
- `prompts/contract_review.yaml`
- `tests/test_contract_review_schemas.py`
- `tests/test_contract_review_utils.py`
- `tests/test_contract_review_party.py`
- `tests/test_contract_review_preset_client.py`
- `tests/test_contract_review_attachments.py`
- `tests/test_contract_review_checks.py`
- `tests/test_contract_review_prompts.py`
- `tests/test_contract_review_service.py`
- `tests/test_contract_review_api.py`

Modify:

- `app/main.py`
- `pyproject.toml`

Do not modify:

- `app/models/llm.py` for contract review behavior. API key cleanup is owned by the model adapter/framework workstream.
- Existing translate capability behavior.

---

### Task 1: Package Registration and Core Schemas

**Files:**

- Create: `app/capabilities/contract_review/__init__.py`
- Create: `app/capabilities/contract_review/schemas.py`
- Test: `tests/test_contract_review_schemas.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write schema tests**

Create `tests/test_contract_review_schemas.py`:

```python
import pytest
from pydantic import ValidationError

from app.capabilities.contract_review.schemas import (
    AttachmentInput,
    CheckItem,
    ContractReviewData,
    ContractReviewRequest,
)


def test_request_accepts_contract_markdown_and_attachment_texts():
    req = ContractReviewRequest(
        contract_md="# 合同\n正文",
        attachments=[
            AttachmentInput(index=1, filename="附件1.xlsx", file_type="xlsx", text="附件文本")
        ],
    )
    assert req.contract_md.startswith("# 合同")
    assert req.attachments[0].filename == "附件1.xlsx"


def test_request_rejects_empty_contract_markdown():
    with pytest.raises(ValidationError):
        ContractReviewRequest(contract_md="", attachments=[])


def test_check_item_allows_required_enums():
    item = CheckItem(
        id="序号2",
        name="签章页完整性",
        result="WARN",
        block_level="提示",
        reason="传真信息缺失或未填写",
    )
    assert item.result == "WARN"


def test_review_data_keeps_duplicate_ids_in_list():
    data = ContractReviewData(
        overall_result="BLOCK",
        check_time="2026-07-07T10:00:00",
        checks=[
            CheckItem(id="序号2", name="签章页完整性", result="FAIL", block_level="硬阻断", reason="银行账号不一致"),
            CheckItem(id="序号2", name="签章页完整性", result="WARN", block_level="提示", reason="传真缺失"),
        ],
    )
    assert [item.result for item in data.checks] == ["FAIL", "WARN"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/Scripts/python -m pytest tests/test_contract_review_schemas.py -v
```

Expected: FAIL because `app.capabilities.contract_review.schemas` does not exist.

- [ ] **Step 3: Implement schemas**

Create `app/capabilities/contract_review/__init__.py`:

```python
"""Contract organization review capability."""
```

Create `app/capabilities/contract_review/schemas.py`:

```python
from typing import Literal

from pydantic import BaseModel, Field


CheckResult = Literal["PASS", "WARN", "FAIL", "NA"]
BlockLevel = Literal["通过", "提示", "硬阻断", "不适用"]
OverallResult = Literal["PASS", "BLOCK"]


class AttachmentInput(BaseModel):
    index: int | None = None
    filename: str = Field(..., min_length=1)
    file_type: str | None = None
    text: str = ""


class ContractReviewRequest(BaseModel):
    contract_md: str = Field(..., min_length=1)
    attachments: list[AttachmentInput] = Field(default_factory=list)


class CheckItem(BaseModel):
    id: str
    name: str
    result: CheckResult
    block_level: BlockLevel
    reason: str | None = None


class ContractReviewData(BaseModel):
    overall_result: OverallResult
    check_time: str
    checks: list[CheckItem]


class ContractParty(BaseModel):
    role: str | None = None
    name: str | None = None


class HeaderInfo(BaseModel):
    contract_name: str | None = None
    contract_number: str | None = None
    signing_location: str | None = None
    signing_date: str | None = None
    parties: list[ContractParty] = Field(default_factory=list)


class SignatureInfo(BaseModel):
    signature_parties: list[ContractParty] = Field(default_factory=list)
    role: str | None = None
    name: str | None = None
    legal_rep_name: str | None = None
    signer_id_number: str | None = None
    signing_date: str | None = None
    bank_name: str | None = None
    bank_account: str | None = None
    account_holder: str | None = None
    address: str | None = None
    phone: str | None = None
    fax: str | None = None
    website: str | None = None
    postal_code: str | None = None


class AuthorizedRep(BaseModel):
    name: str = ""
    id_number: str = ""


class SystemPreset(BaseModel):
    entity_name: str = ""
    legal_rep_name: str = ""
    legal_rep_id_number: str = ""
    authorized_reps: list[AuthorizedRep] = Field(default_factory=list)
    bank_name: str = ""
    bank_account: str = ""
    account_holder: str = ""
    address: str = ""
    phone: str = ""
    fax: str = ""
    website: str = ""
    postal_code: str = ""


class OurPartyContext(BaseModel):
    role: str
    name: str
    identification_source: Literal["preset_hit"] = "preset_hit"
    preset_available: bool = True
```

Modify `pyproject.toml` packages list:

```toml
packages = [
    "app",
    "app.core",
    "app.models",
    "app.capabilities",
    "app.capabilities.translate",
    "app.capabilities.contract_review",
]
```

- [ ] **Step 4: Run tests**

Run:

```bash
.venv/Scripts/python -m pytest tests/test_contract_review_schemas.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml app/capabilities/contract_review/__init__.py app/capabilities/contract_review/schemas.py tests/test_contract_review_schemas.py
git commit -m "feat: add contract review schemas"
```

---

### Task 2: Utility Functions and Sensitive Data Masking

**Files:**

- Create: `app/capabilities/contract_review/utils.py`
- Test: `tests/test_contract_review_utils.py`

- [ ] **Step 1: Write utility tests**

Create `tests/test_contract_review_utils.py`:

```python
from datetime import date

from app.capabilities.contract_review.utils import (
    is_empty,
    mask_id_number,
    normalize_date,
    to_halfwidth,
)


def test_is_empty_handles_none_blank_and_string_null():
    assert is_empty(None)
    assert is_empty("")
    assert is_empty("   ")
    assert is_empty("null")
    assert not is_empty("0")


def test_to_halfwidth_converts_ascii_range_and_fullwidth_space():
    assert to_halfwidth("１２３：ＡＢＣ　x") == "123:ABC x"


def test_normalize_date_accepts_common_numeric_formats():
    assert normalize_date("2026年7月8日") == date(2026, 7, 8)
    assert normalize_date("2026-07-08") == date(2026, 7, 8)
    assert normalize_date("2026/7/8") == date(2026, 7, 8)
    assert normalize_date("2026.7.8") == date(2026, 7, 8)


def test_normalize_date_returns_none_for_unknown_or_invalid_dates():
    assert normalize_date(None) is None
    assert normalize_date("二〇二六年七月八日") is None
    assert normalize_date("2026-13-08") is None


def test_mask_id_number_uses_first_6_last_4():
    assert mask_id_number("210102197001010011") == "210102********0011"


def test_mask_id_number_masks_short_values_completely():
    assert mask_id_number("123456789") == "*********"
    assert mask_id_number(None) is None
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/Scripts/python -m pytest tests/test_contract_review_utils.py -v
```

Expected: FAIL because utilities do not exist.

- [ ] **Step 3: Implement utilities**

Create `app/capabilities/contract_review/utils.py`:

```python
import re
from datetime import date


def is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"", "null"}
    return False


def to_halfwidth(value: str | None) -> str | None:
    if value is None:
        return None
    result = []
    for ch in value:
        code = ord(ch)
        if code == 0x3000:
            code = 0x20
        elif 0xFF01 <= code <= 0xFF5E:
            code -= 0xFEE0
        result.append(chr(code))
    return "".join(result)


def normalize_date(value: str | None) -> date | None:
    if is_empty(value):
        return None
    text = str(value).strip()
    match = re.match(r"(\d{4})[年\-/\.](\d{1,2})[月\-/\.](\d{1,2})日?", text)
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def mask_id_number(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) < 10:
        return "*" * len(text)
    return f"{text[:6]}{'*' * (len(text) - 10)}{text[-4:]}"
```

- [ ] **Step 4: Run tests**

Run:

```bash
.venv/Scripts/python -m pytest tests/test_contract_review_utils.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/capabilities/contract_review/utils.py tests/test_contract_review_utils.py
git commit -m "feat: add contract review utilities"
```

---

### Task 3: Result Aggregation Without Dropping Warnings

**Files:**

- Modify: `app/capabilities/contract_review/checks.py`
- Test: `tests/test_contract_review_checks.py`

- [ ] **Step 1: Write aggregation tests**

Create initial `tests/test_contract_review_checks.py`:

```python
from app.capabilities.contract_review.checks import build_check_items, build_review_data
from app.capabilities.contract_review.schemas import CheckItem


def test_build_check_items_splits_fail_and_warn_for_same_id():
    items = build_check_items(
        item_id="序号2",
        item_name="签章页完整性",
        hard_reasons=["银行账号不一致"],
        warn_reasons=["传真信息缺失"],
    )
    assert [item.result for item in items] == ["FAIL", "WARN"]
    assert [item.block_level for item in items] == ["硬阻断", "提示"]


def test_build_check_items_returns_pass_when_no_reasons():
    items = build_check_items("序号1", "合同首页完整性", [], [])
    assert len(items) == 1
    assert items[0].result == "PASS"
    assert items[0].block_level == "通过"


def test_build_review_data_preserves_duplicate_ids_and_blocks():
    checks = [
        CheckItem(id="序号2", name="签章页完整性", result="FAIL", block_level="硬阻断", reason="银行账号不一致"),
        CheckItem(id="序号2", name="签章页完整性", result="WARN", block_level="提示", reason="传真信息缺失"),
    ]
    data = build_review_data("2026-07-07T10:00:00", checks)
    assert data.overall_result == "BLOCK"
    assert len(data.checks) == 2
    assert [item.reason for item in data.checks] == ["银行账号不一致", "传真信息缺失"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/Scripts/python -m pytest tests/test_contract_review_checks.py -v
```

Expected: FAIL because `checks.py` does not exist.

- [ ] **Step 3: Implement aggregation helpers**

Create `app/capabilities/contract_review/checks.py`:

```python
from app.capabilities.contract_review.schemas import CheckItem, ContractReviewData


def build_check_items(
    item_id: str,
    item_name: str,
    hard_reasons: list[str],
    warn_reasons: list[str],
) -> list[CheckItem]:
    items: list[CheckItem] = []
    if hard_reasons:
        items.append(CheckItem(
            id=item_id,
            name=item_name,
            result="FAIL",
            block_level="硬阻断",
            reason="；".join(hard_reasons),
        ))
    if warn_reasons:
        items.append(CheckItem(
            id=item_id,
            name=item_name,
            result="WARN",
            block_level="提示",
            reason="；".join(warn_reasons),
        ))
    if not items:
        items.append(CheckItem(
            id=item_id,
            name=item_name,
            result="PASS",
            block_level="通过",
            reason=None,
        ))
    return items


def build_review_data(check_time: str, *check_lists) -> ContractReviewData:
    checks: list[CheckItem] = []
    for item in check_lists:
        if isinstance(item, list):
            checks.extend(item)
        else:
            checks.append(item)
    overall = (
        "BLOCK"
        if any(item.result == "FAIL" and item.block_level == "硬阻断" for item in checks)
        else "PASS"
    )
    return ContractReviewData(overall_result=overall, check_time=check_time, checks=checks)
```

- [ ] **Step 4: Run tests**

Run:

```bash
.venv/Scripts/python -m pytest tests/test_contract_review_checks.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/capabilities/contract_review/checks.py tests/test_contract_review_checks.py
git commit -m "feat: preserve contract review check results"
```

---

### Task 4: Party Candidate Ordering

**Files:**

- Create: `app/capabilities/contract_review/party.py`
- Test: `tests/test_contract_review_party.py`

- [ ] **Step 1: Write party tests**

Create `tests/test_contract_review_party.py`:

```python
from app.capabilities.contract_review.party import build_candidate_parties, classify_role
from app.capabilities.contract_review.schemas import ContractParty


def test_classify_customer_supplier_and_unknown_roles():
    assert classify_role("甲方") == "customer"
    assert classify_role("买方") == "customer"
    assert classify_role("乙方") == "supplier"
    assert classify_role("卖方") == "supplier"
    assert classify_role("实施单位") == "neutral"


def test_build_candidates_skips_customer_and_orders_supplier_before_neutral():
    parties = [
        ContractParty(role="买方", name="客户公司"),
        ContractParty(role="第三方", name="中性公司"),
        ContractParty(role="卖方", name="我方公司"),
        ContractParty(role="实施单位", name="未知角色公司"),
    ]
    candidates = build_candidate_parties(parties)
    assert [(p.role, p.name) for p in candidates] == [
        ("卖方", "我方公司"),
        ("第三方", "中性公司"),
        ("实施单位", "未知角色公司"),
    ]


def test_build_candidates_ignores_empty_names():
    parties = [ContractParty(role="乙方", name=""), ContractParty(role="服务方", name="服务公司")]
    candidates = build_candidate_parties(parties)
    assert [(p.role, p.name) for p in candidates] == [("服务方", "服务公司")]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/Scripts/python -m pytest tests/test_contract_review_party.py -v
```

Expected: FAIL because `party.py` does not exist.

- [ ] **Step 3: Implement party logic**

Create `app/capabilities/contract_review/party.py`:

```python
from typing import Literal

from app.capabilities.contract_review.schemas import ContractParty
from app.capabilities.contract_review.utils import is_empty

RoleType = Literal["customer", "supplier", "neutral"]

CUSTOMER_SIDE_ROLES = {
    "甲方", "买方", "采购方", "需方", "委托方",
    "发包方", "建设方", "出租方", "授权方", "许可方",
}

SUPPLIER_SIDE_ROLES = {
    "乙方", "卖方", "供应方", "供方", "服务方", "服务提供方",
    "受托方", "承包方", "施工方", "承租方", "被授权方", "被许可方", "受让方",
}


def classify_role(role: str | None) -> RoleType:
    if role in CUSTOMER_SIDE_ROLES:
        return "customer"
    if role in SUPPLIER_SIDE_ROLES:
        return "supplier"
    return "neutral"


def build_candidate_parties(parties: list[ContractParty]) -> list[ContractParty]:
    supplier_candidates: list[ContractParty] = []
    neutral_candidates: list[ContractParty] = []

    for party in parties:
        if is_empty(party.name):
            continue
        role_type = classify_role(party.role)
        if role_type == "supplier":
            supplier_candidates.append(party)
        elif role_type == "neutral":
            neutral_candidates.append(party)

    return supplier_candidates + neutral_candidates
```

- [ ] **Step 4: Run tests**

Run:

```bash
.venv/Scripts/python -m pytest tests/test_contract_review_party.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/capabilities/contract_review/party.py tests/test_contract_review_party.py
git commit -m "feat: identify contract review party candidates"
```

---

### Task 5: Signing Entity Preset Client

**Files:**

- Create: `app/capabilities/contract_review/preset_client.py`
- Modify: `app/core/config.py`
- Modify: `pyproject.toml`
- Test: `tests/test_contract_review_preset_client.py`

- [ ] **Step 1: Write preset client tests**

Create `tests/test_contract_review_preset_client.py`:

```python
from app.capabilities.contract_review.preset_client import fetch_preset, identify_our_party
from app.capabilities.contract_review.schemas import ContractParty, SystemPreset


def test_identify_our_party_stops_after_first_hit():
    calls: list[str] = []

    def fake_fetch(entity_name: str) -> SystemPreset | None:
        calls.append(entity_name)
        if entity_name == "我方公司":
            return SystemPreset(entity_name="我方公司", legal_rep_name="张三")
        return None

    parties = [
        ContractParty(role="甲方", name="客户公司"),
        ContractParty(role="乙方", name="我方公司"),
        ContractParty(role="第三方", name="中性公司"),
    ]
    context, preset = identify_our_party(parties, fake_fetch)
    assert context is not None
    assert context.name == "我方公司"
    assert preset is not None
    assert calls == ["我方公司"]


def test_identify_our_party_tries_neutral_when_supplier_misses():
    calls: list[str] = []

    def fake_fetch(entity_name: str) -> SystemPreset | None:
        calls.append(entity_name)
        if entity_name == "中性公司":
            return SystemPreset(entity_name="中性公司")
        return None

    parties = [
        ContractParty(role="乙方", name="供应商未命中"),
        ContractParty(role="合作方二", name="中性公司"),
    ]
    context, preset = identify_our_party(parties, fake_fetch)
    assert context is not None
    assert context.name == "中性公司"
    assert preset is not None
    assert calls == ["供应商未命中", "中性公司"]


def test_identify_our_party_returns_none_when_all_candidates_miss():
    def fake_fetch(entity_name: str) -> SystemPreset | None:
        return None

    context, preset = identify_our_party([ContractParty(role="乙方", name="未命中公司")], fake_fetch)
    assert context is None
    assert preset is None


def test_fetch_preset_posts_entity_name_and_parses_response():
    calls = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "code": 0,
                "data": {
                    "entity_name": "我方公司",
                    "legal_rep_name": "张三",
                    "legal_rep_id_number": "210102197001010011",
                    "authorized_reps": [{"name": "李四", "id_number": "210102197001010022"}],
                    "bank_name": "招商银行",
                    "bank_account": "123456",
                    "account_holder": "我方公司",
                    "address": "地址",
                    "phone": "024-12345678",
                    "fax": "",
                    "website": "",
                    "postal_code": "110000",
                },
            }

    class FakeClient:
        def post(self, url, json, timeout):
            calls.append((url, json, timeout))
            return FakeResponse()

        def close(self):
            pass

    preset = fetch_preset(
        "我方公司",
        client_factory=FakeClient,
        base_url="http://preset.local",
        path="/api/v1/signature-presets/by-entity-name",
        timeout=2.0,
    )
    assert preset is not None
    assert preset.entity_name == "我方公司"
    assert preset.authorized_reps[0].name == "李四"
    assert calls == [
        (
            "http://preset.local/api/v1/signature-presets/by-entity-name",
            {"entity_name": "我方公司"},
            2.0,
        )
    ]


def test_fetch_preset_returns_none_when_not_configured():
    assert fetch_preset("我方公司", base_url="") is None
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/Scripts/python -m pytest tests/test_contract_review_preset_client.py -v
```

Expected: FAIL because `preset_client.py` and signing preset settings do not exist.

- [ ] **Step 3: Add signing preset runtime dependency and config**

Modify `pyproject.toml` dependencies so `httpx` is available in production runtime, not only in dev:

```toml
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
    "openai>=1.40.0",
    "httpx>=0.27.0",
]
```

Modify `app/core/config.py`:

```python
class SigningPresetSettings(BaseModel):
    base_url: str = ""
    path: str = "/api/v1/signature-presets/by-entity-name"
    timeout: float = 3.0
```

Add the field to `Settings`:

```python
class Settings(BaseSettings):
    model_config = {"env_prefix": "LTC__", "env_nested_delimiter": "__"}

    server: ServerSettings = ServerSettings()
    llm: LlmSettings = LlmSettings()
    auth: AuthSettings = AuthSettings()
    signing_preset: SigningPresetSettings = SigningPresetSettings()
    app: AppMeta = AppMeta()
```

Supported environment variables:

```text
LTC__SIGNING_PRESET__BASE_URL
LTC__SIGNING_PRESET__PATH
LTC__SIGNING_PRESET__TIMEOUT
```

- [ ] **Step 4: Implement preset HTTP fetch and identification wrapper**

Create `app/capabilities/contract_review/preset_client.py`:

```python
from collections.abc import Callable
from urllib.parse import urljoin

import httpx

from app.capabilities.contract_review.party import build_candidate_parties
from app.capabilities.contract_review.schemas import ContractParty, OurPartyContext, SystemPreset
from app.core.config import get_settings

FetchPreset = Callable[[str], SystemPreset | None]


def _join_url(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def fetch_preset(
    entity_name: str,
    *,
    client_factory: Callable[[], httpx.Client] = httpx.Client,
    base_url: str | None = None,
    path: str | None = None,
    timeout: float | None = None,
) -> SystemPreset | None:
    settings = get_settings().signing_preset
    resolved_base_url = settings.base_url if base_url is None else base_url
    if not resolved_base_url:
        return None

    resolved_path = settings.path if path is None else path
    resolved_timeout = settings.timeout if timeout is None else timeout
    client = client_factory()
    try:
        response = client.post(
            _join_url(resolved_base_url, resolved_path),
            json={"entity_name": entity_name},
            timeout=resolved_timeout,
        )
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            close()

    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        return None

    payload = response.json()
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not isinstance(data, dict):
        return None
    return SystemPreset.model_validate(data)


def identify_our_party(
    parties: list[ContractParty],
    fetch_preset: FetchPreset,
) -> tuple[OurPartyContext | None, SystemPreset | None]:
    for candidate in build_candidate_parties(parties):
        if candidate.name is None:
            continue
        preset = fetch_preset(candidate.name)
        if preset is None:
            continue
        return (
            OurPartyContext(role=candidate.role or "", name=candidate.name, preset_available=True),
            preset,
        )
    return None, None
```

- [ ] **Step 5: Run tests**

Run:

```bash
.venv/Scripts/python -m pytest tests/test_contract_review_preset_client.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml app/core/config.py app/capabilities/contract_review/preset_client.py tests/test_contract_review_preset_client.py
git commit -m "feat: identify contract review preset party"
```

---

### Task 6: Core Checks for Sequence 1, 2, 3, and 11

**Files:**

- Modify: `app/capabilities/contract_review/checks.py`
- Test: `tests/test_contract_review_checks.py`

- [ ] **Step 1: Extend checks tests**

Append to `tests/test_contract_review_checks.py`:

```python
from app.capabilities.contract_review.checks import check_seq1, check_seq2_11, check_seq3
from app.capabilities.contract_review.schemas import (
    AuthorizedRep,
    ContractParty,
    HeaderInfo,
    OurPartyContext,
    SignatureInfo,
    SystemPreset,
)


def _preset():
    return SystemPreset(
        entity_name="我方公司",
        legal_rep_name="张三",
        legal_rep_id_number="210102197001010011",
        authorized_reps=[AuthorizedRep(name="李四", id_number="210102197001010022")],
        bank_name="招商银行",
        bank_account="123456",
        account_holder="我方公司",
        address="地址",
        phone="024-12345678",
        fax="",
        website="http://example.com",
        postal_code="110000",
    )


def _header():
    return HeaderInfo(
        contract_name="测试合同",
        contract_number=None,
        signing_location="沈阳",
        signing_date="2026年7月8日",
        parties=[ContractParty(role="买方", name="客户公司"), ContractParty(role="卖方", name="我方公司")],
    )


def _signature():
    return SignatureInfo(
        signature_parties=[ContractParty(role="买方", name="客户公司"), ContractParty(role="卖方", name="我方公司")],
        role="卖方",
        name="我方公司",
        legal_rep_name="李四",
        signer_id_number="210102197001010022",
        signing_date="2026年7月8日",
        bank_name="招商银行",
        bank_account="123456",
        account_holder="我方公司",
        address="地址",
        phone="024-12345678",
        fax=None,
        website="http://example.com",
        postal_code="110000",
    )


def test_seq1_warns_contract_number_but_passes_required_fields():
    items = check_seq1(_header(), OurPartyContext(role="卖方", name="我方公司"), _preset())
    assert [item.result for item in items] == ["WARN"]
    assert "合同编号缺失" in items[0].reason


def test_seq1_fails_when_preset_unavailable():
    items = check_seq1(_header(), None, None)
    assert items[0].result == "FAIL"
    assert "无法校验我方签署主体名称" in items[0].reason


def test_seq2_11_preserves_fail_and_warn():
    sig = _signature()
    sig.bank_account = "999999"
    sig.fax = None
    seq2_items, seq11_items = check_seq2_11(_header(), sig, OurPartyContext(role="卖方", name="我方公司"), _preset())
    assert [item.result for item in seq2_items] == ["FAIL", "WARN"]
    assert [item.result for item in seq11_items] == ["FAIL"]


def test_seq2_allows_authorized_rep_and_matching_id_number():
    seq2_items, seq11_items = check_seq2_11(_header(), _signature(), OurPartyContext(role="卖方", name="我方公司"), _preset())
    assert seq2_items[0].result == "WARN"
    assert "传真信息缺失" in seq2_items[0].reason
    assert seq11_items[0].result == "PASS"


def test_seq2_warns_when_id_number_without_name():
    sig = _signature()
    sig.legal_rep_name = None
    sig.signer_id_number = "210102197001010022"
    seq2_items, _ = check_seq2_11(_header(), sig, OurPartyContext(role="卖方", name="我方公司"), _preset())
    assert any(item.result == "WARN" and "身份证号" in (item.reason or "") for item in seq2_items)


def test_seq3_fails_when_our_party_missing():
    item = check_seq3(_header(), _signature(), None)
    assert item.result == "FAIL"


def test_seq3_passes_when_signature_date_empty():
    sig = _signature()
    sig.signing_date = None
    item = check_seq3(_header(), sig, OurPartyContext(role="卖方", name="我方公司"))
    assert item.result == "PASS"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/Scripts/python -m pytest tests/test_contract_review_checks.py -v
```

Expected: FAIL because check functions are not implemented.

- [ ] **Step 3: Implement seq1/2/3/11**

Add to `app/capabilities/contract_review/checks.py`:

```python
from datetime import date

from app.capabilities.contract_review.schemas import HeaderInfo, OurPartyContext, SignatureInfo, SystemPreset
from app.capabilities.contract_review.utils import is_empty, mask_id_number, normalize_date, to_halfwidth


NORMALIZE_FIELDS = {"bank_account", "phone", "fax", "website", "postal_code"}
ACCOUNT_FIELDS = {"bank_name", "bank_account", "account_holder"}
NINE_FIELDS = {
    "legal_rep_name": "法定代表人/授权人",
    "bank_name": "开户银行",
    "bank_account": "银行账号",
    "account_holder": "开户名称",
    "address": "通讯地址",
    "phone": "电话",
    "fax": "传真",
    "website": "网址",
    "postal_code": "邮政编码",
}


def check_seq1(header: HeaderInfo, our_party: OurPartyContext | None, preset: SystemPreset | None) -> list[CheckItem]:
    hard: list[str] = []
    warn: list[str] = []
    if our_party is None or preset is None:
        hard.append("签署地预设数据不可用，无法校验我方签署主体名称")
    if is_empty(header.contract_name):
        hard.append("合同名称缺失")
    if not header.parties:
        hard.append("首页签约方名称缺失")
    if is_empty(header.signing_location):
        hard.append("签订地点缺失")
    elif str(header.signing_location).startswith("错误："):
        hard.append(f"签订地点不是有效地名：{header.signing_location}")
    if preset is not None and our_party is not None and our_party.name != preset.entity_name:
        hard.append(f"我方签署主体名称（{our_party.name}）与系统预设值（{preset.entity_name}）不一致")
    if is_empty(header.signing_date):
        warn.append("首页签订日期缺失")
    if is_empty(header.contract_number):
        warn.append("合同编号缺失")
    return build_check_items("序号1", "合同首页完整性", hard, warn)


def _same_value(field: str, actual: str | None, expected: str | None) -> bool:
    if field in NORMALIZE_FIELDS:
        return to_halfwidth(actual) == to_halfwidth(expected)
    return actual == expected


def check_seq2_11(
    header: HeaderInfo,
    signature: SignatureInfo,
    our_party: OurPartyContext | None,
    preset: SystemPreset | None,
) -> tuple[list[CheckItem], list[CheckItem]]:
    hard: list[str] = []
    warn: list[str] = []
    account_hard: list[str] = []
    account_warn: list[str] = []
    if our_party is None or preset is None:
        hard.append("签署地预设数据不可用，无法校验签章页预设信息")
        account_hard.append("签署地预设数据不可用，无法校验账户信息")

    header_by_role = {p.role: p.name for p in header.parties if not is_empty(p.role)}
    sig_by_role = {p.role: p.name for p in signature.signature_parties if not is_empty(p.role)}
    for role, header_name in header_by_role.items():
        sig_name = sig_by_role.get(role)
        if is_empty(sig_name):
            warn.append(f"签章区块{role}名称缺失")
        elif sig_name != header_name:
            hard.append(f"签章区块{role}名称与首部{role}名称不一致")

    for field, label in NINE_FIELDS.items():
        value = getattr(signature, field)
        if is_empty(value):
            msg = f"{label}信息缺失或未填写"
            warn.append(msg)
            if field in ACCOUNT_FIELDS:
                account_warn.append(msg)
            continue
        if preset is None or our_party is None:
            continue
        if field == "legal_rep_name":
            authorized_names = [rep.name for rep in preset.authorized_reps if not is_empty(rep.name)]
            matched = value == preset.legal_rep_name or value in authorized_names
            display = f"法定代表人{preset.legal_rep_name}或授权人{authorized_names}"
        else:
            expected = getattr(preset, field)
            matched = _same_value(field, value, expected)
            display = expected
        if not matched:
            msg = f"{label}（{value}）与系统预设值（{display}）不一致"
            hard.append(msg)
            if field in ACCOUNT_FIELDS:
                account_hard.append(msg)

    if preset is not None and not is_empty(signature.legal_rep_name) and not is_empty(signature.signer_id_number):
        expected_id = None
        if signature.legal_rep_name == preset.legal_rep_name:
            expected_id = preset.legal_rep_id_number
        else:
            for rep in preset.authorized_reps:
                if rep.name == signature.legal_rep_name:
                    expected_id = rep.id_number
                    break
        if is_empty(expected_id):
            hard.append(f"我方法定代表人/授权人（{signature.legal_rep_name}）在合同中填写了身份证号，但系统无有效身份证号主数据可供验证")
        elif to_halfwidth(signature.signer_id_number) != to_halfwidth(expected_id):
            hard.append(f"我方法定代表人/授权人（{signature.legal_rep_name}）身份证号与系统预设值不一致，合同值{mask_id_number(signature.signer_id_number)}")
    elif is_empty(signature.legal_rep_name) and not is_empty(signature.signer_id_number):
        warn.append(f"合同出现我方法定代表人/授权人身份证号{mask_id_number(signature.signer_id_number)}，但没有对应姓名，无法验证身份证号正确性")

    return (
        build_check_items("序号2", "签章页完整性", hard, warn),
        build_check_items("序号11", "账户信息", account_hard, account_warn),
    )


def check_seq3(header: HeaderInfo, signature: SignatureInfo, our_party: OurPartyContext | None) -> CheckItem:
    if our_party is None:
        return CheckItem(id="序号3", name="签署日期", result="FAIL", block_level="硬阻断", reason="无法识别我方签署主体，无法校验我方签署日期")
    if is_empty(signature.signing_date):
        return CheckItem(id="序号3", name="签署日期", result="PASS", block_level="通过", reason="签章区块我方签署日期缺失，跳过校验")
    hard: list[str] = []
    sig_date = normalize_date(signature.signing_date)
    if sig_date is None:
        hard.append(f"签章区块我方签署日期（{signature.signing_date}）格式无法识别")
    else:
        header_date = normalize_date(header.signing_date)
        if header_date is not None and sig_date != header_date:
            hard.append(f"签章区块我方签署日期（{signature.signing_date}）与首部签订日期（{header.signing_date}）不一致")
        if sig_date < date.today():
            hard.append(f"签署日期（{signature.signing_date}）早于当前系统日期（{date.today().isoformat()}）")
    if hard:
        return CheckItem(id="序号3", name="签署日期", result="FAIL", block_level="硬阻断", reason="；".join(hard))
    return CheckItem(id="序号3", name="签署日期", result="PASS", block_level="通过", reason=None)
```

Ensure imports at the top include `CheckItem` only once.

- [ ] **Step 4: Run tests**

Run:

```bash
.venv/Scripts/python -m pytest tests/test_contract_review_checks.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/capabilities/contract_review/checks.py tests/test_contract_review_checks.py
git commit -m "feat: add core contract review checks"
```

---

### Task 7: Amount and Payment Checks

**Files:**

- Modify: `app/capabilities/contract_review/checks.py`
- Test: `tests/test_contract_review_checks.py`

- [ ] **Step 1: Add amount/payment tests**

Append to `tests/test_contract_review_checks.py`:

```python
from app.capabilities.contract_review.checks import check_amount_payment


def test_payment_method_missing_fails():
    items = check_amount_payment({"currency": "人民币", "payment_method": None, "total_amount_numeric": "100", "total_amount_uppercase": "壹佰元整", "payment_stages": []})
    seq9 = next(item for item in items if item.id == "序号9")
    assert seq9.result == "FAIL"


def test_empty_payment_stages_warns_not_fail():
    items = check_amount_payment({"currency": "人民币", "payment_method": "电汇", "total_amount_numeric": "100", "total_amount_uppercase": "壹佰元整", "payment_stages": []})
    seq10 = next(item for item in items if item.id == "序号10")
    assert seq10.result == "WARN"
    assert "付款阶段不明确" in seq10.reason


def test_currency_missing_fails():
    items = check_amount_payment({"currency": None, "payment_method": "电汇", "total_amount_numeric": "100", "total_amount_uppercase": "壹佰元整", "payment_stages": []})
    seq8 = next(item for item in items if item.id == "序号8")
    assert seq8.result == "FAIL"


def test_stage_percentage_not_100_fails():
    items = check_amount_payment({
        "currency": "人民币",
        "payment_method": "电汇",
        "total_amount_numeric": "100",
        "total_amount_uppercase": "壹佰元整",
        "payment_stages": [{"stage_name": "首付款", "percentage": "50", "amount_numeric": "50", "amount_uppercase": "伍拾元整"}],
    })
    seq10 = next(item for item in items if item.id == "序号10")
    assert seq10.result == "FAIL"
    assert "不等于100%" in seq10.reason
```

- [ ] **Step 2: Run tests**

Run:

```bash
.venv/Scripts/python -m pytest tests/test_contract_review_checks.py -v
```

Expected: FAIL because `check_amount_payment` is not implemented.

- [ ] **Step 3: Implement amount/payment check**

Add deterministic amount/payment helpers to `checks.py`:

```python
from decimal import Decimal, InvalidOperation


def _to_decimal(value) -> Decimal | None:
    if is_empty(value):
        return None
    text = str(value).replace(",", "").replace("，", "").replace("%", "").strip()
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _make_single_check(item_id: str, name: str, hard: list[str], warn: list[str]) -> CheckItem:
    if hard:
        return CheckItem(id=item_id, name=name, result="FAIL", block_level="硬阻断", reason="；".join(hard))
    if warn:
        return CheckItem(id=item_id, name=name, result="WARN", block_level="提示", reason="；".join(warn))
    return CheckItem(id=item_id, name=name, result="PASS", block_level="通过", reason=None)


def check_amount_payment(a3_result: dict) -> list[CheckItem]:
    total_numeric = _to_decimal(a3_result.get("total_amount_numeric"))
    total_uppercase = a3_result.get("total_amount_uppercase")
    amount_match = a3_result.get("total_amount_match")
    currency = a3_result.get("currency")
    payment_method = a3_result.get("payment_method")
    stages = a3_result.get("payment_stages") or []

    seq7_hard: list[str] = []
    if total_numeric is None or is_empty(total_uppercase):
        seq7_hard.append("合同总价金额或大写金额缺失，无法校验总价大小写一致性")
    elif amount_match is False:
        seq7_hard.append("合同总价大小写金额不一致")

    seq8_hard: list[str] = []
    if is_empty(currency):
        seq8_hard.append("币种缺失")

    seq9_hard: list[str] = []
    if is_empty(payment_method):
        seq9_hard.append("付款方式缺失")

    seq10_hard: list[str] = []
    seq10_warn: list[str] = []
    if not stages:
        seq10_warn.append("付款阶段不明确")
    else:
        percentages: list[Decimal] = []
        stage_amounts: list[Decimal] = []
        for index, stage in enumerate(stages, start=1):
            percentage = _to_decimal(stage.get("percentage"))
            amount = _to_decimal(stage.get("amount_numeric"))
            if percentage is None:
                seq10_warn.append(f"第{index}个付款阶段比例缺失或格式无法识别")
            else:
                percentages.append(percentage)
            if amount is None:
                seq10_warn.append(f"第{index}个付款阶段金额缺失或格式无法识别")
            else:
                stage_amounts.append(amount)

        if percentages and sum(percentages) != Decimal("100"):
            seq10_hard.append(f"付款阶段比例合计{sum(percentages)}%，不等于100%")
        if total_numeric is not None and stage_amounts and sum(stage_amounts) != total_numeric:
            seq10_hard.append(f"付款阶段金额合计{sum(stage_amounts)}，与合同总价{total_numeric}不一致")

    return [
        _make_single_check("序号7", "总价大小写一致性", seq7_hard, []),
        _make_single_check("序号8", "货币条款", seq8_hard, []),
        _make_single_check("序号9", "付款方式", seq9_hard, []),
        _make_single_check("序号10", "付款阶段校验", seq10_hard, seq10_warn),
    ]
```

Do not implement payment method dictionary matching.

- [ ] **Step 4: Run tests**

Run:

```bash
.venv/Scripts/python -m pytest tests/test_contract_review_checks.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/capabilities/contract_review/checks.py tests/test_contract_review_checks.py
git commit -m "feat: add amount and payment checks"
```

---

### Task 8: Attachment Resolution and Sequence 12

**Files:**

- Create: `app/capabilities/contract_review/attachments.py`
- Test: `tests/test_contract_review_attachments.py`

- [ ] **Step 1: Write attachment tests**

Create `tests/test_contract_review_attachments.py`:

```python
from app.capabilities.contract_review.attachments import check_copies_and_attachments


def test_declared_three_but_actual_two_fails():
    result = check_copies_and_attachments(
        a4_result={
            "copies": {"total_copies": 2, "party_copies": [{"role": "甲方", "copies": 1}, {"role": "乙方", "copies": 1}]},
            "attachments_declared": [
                {"index": 1, "title": "附件一", "content_embedded_in_contract": False, "section_heading_hint": None},
                {"index": 2, "title": "附件二", "content_embedded_in_contract": False, "section_heading_hint": None},
                {"index": 3, "title": "附件三", "content_embedded_in_contract": False, "section_heading_hint": None},
            ],
            "total_declared": 3,
        },
        sections=[],
        attachments=[
            {"index": 1, "filename": "附件一.xlsx", "text": "1"},
            {"index": 2, "filename": "附件二.xlsx", "text": "2"},
        ],
        full_text="",
    )
    attach_items = [item for item in result["check_results"] if item.id == "附件检查-数量标题"]
    assert attach_items[0].result == "FAIL"
    assert "实际仅获取到2份" in attach_items[0].reason


def test_embedded_one_plus_uploaded_two_satisfies_declared_three():
    result = check_copies_and_attachments(
        a4_result={
            "copies": {"total_copies": 2, "party_copies": [{"role": "甲方", "copies": 1}, {"role": "乙方", "copies": 1}]},
            "attachments_declared": [
                {"index": 1, "title": "附件一", "content_embedded_in_contract": True, "section_heading_hint": "附件一"},
            ],
            "total_declared": 3,
        },
        sections=[{"title": "附件一", "content": "内嵌"}],
        attachments=[
            {"index": 2, "filename": "附件二.xlsx", "text": "2"},
            {"index": 3, "filename": "附件三.xlsx", "text": "3"},
        ],
        full_text="",
    )
    attach_items = [item for item in result["check_results"] if item.id == "附件检查-数量标题"]
    assert all(item.result != "FAIL" for item in attach_items)
    assert len(result["resolved_attachments"]) == 3


def test_party_copies_sum_mismatch_fails_seq12():
    result = check_copies_and_attachments(
        a4_result={
            "copies": {"total_copies": 3, "party_copies": [{"role": "甲方", "copies": 1}, {"role": "乙方", "copies": 1}]},
            "attachments_declared": [],
            "total_declared": None,
        },
        sections=[],
        attachments=[],
        full_text="",
    )
    assert result["check_results"][0].id == "序号12"
    assert result["check_results"][0].result == "FAIL"
```

- [ ] **Step 2: Run tests**

Run:

```bash
.venv/Scripts/python -m pytest tests/test_contract_review_attachments.py -v
```

Expected: FAIL because `attachments.py` does not exist.

- [ ] **Step 3: Implement attachments**

Create `app/capabilities/contract_review/attachments.py`:

```python
from difflib import SequenceMatcher

from app.capabilities.contract_review.checks import build_check_items
from app.capabilities.contract_review.schemas import CheckItem


def similarity(a: str | None, b: str | None) -> float:
    left = (a or "").strip()
    right = (b or "").strip()
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def find_matching_section(
    sections: list[dict],
    heading_hint: str | None,
    full_text: str | None = None,
    fallback_length: int = 1500,
) -> dict | None:
    if heading_hint:
        best_section = None
        best_score = 0.0
        for section in sections:
            score = similarity(heading_hint, section.get("title"))
            if score > best_score:
                best_section = section
                best_score = score
        if best_section is not None and best_score >= 0.6:
            return {
                "title": best_section.get("title"),
                "text": best_section.get("content", ""),
                "match_confidence": "high",
                "score": best_score,
            }
        if best_section is not None and best_score >= 0.3:
            return {
                "title": best_section.get("title"),
                "text": best_section.get("content", ""),
                "match_confidence": "low",
                "score": best_score,
            }

    if heading_hint and full_text:
        position = full_text.find(heading_hint)
        if position >= 0:
            return {
                "title": heading_hint,
                "text": full_text[position: position + fallback_length],
                "match_confidence": "fallback",
                "score": 0.0,
            }
    return None


def _to_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _check_copies(a4_result: dict) -> CheckItem:
    copies = a4_result.get("copies") or {}
    total = _to_int(copies.get("total_copies"))
    party_copies = copies.get("party_copies") or []
    hard: list[str] = []
    warn: list[str] = []

    if total is None:
        warn.append("合同份数缺失或无法识别")
    else:
        parsed_party_copies = []
        for item in party_copies:
            copies_value = _to_int(item.get("copies"))
            if copies_value is not None:
                parsed_party_copies.append(copies_value)
        if party_copies and sum(parsed_party_copies) != total:
            hard.append(f"各方持有份数合计{sum(parsed_party_copies)}份，与合同总份数{total}份不一致")

    return build_check_items("序号12", "合同份数", hard, warn)[0]


def check_copies_and_attachments(
    a4_result: dict,
    sections: list[dict],
    attachments: list[dict],
    full_text: str,
) -> dict:
    declared = a4_result.get("attachments_declared") or []
    total_declared = _to_int(a4_result.get("total_declared"))
    resolved_attachments: list[dict] = []
    hard: list[str] = []
    warn: list[str] = []

    for declared_item in declared:
        if declared_item.get("content_embedded_in_contract"):
            matched = find_matching_section(
                sections,
                declared_item.get("section_heading_hint") or declared_item.get("title"),
                full_text,
            )
            if matched is None:
                warn.append(f"声明附件《{declared_item.get('title')}》标记为正文内嵌，但未定位到对应正文段落")
                continue
            if matched["match_confidence"] in {"low", "fallback"}:
                warn.append(f"声明附件《{declared_item.get('title')}》仅低置信度匹配到正文段落")
            resolved_attachments.append({
                "index": declared_item.get("index"),
                "title": declared_item.get("title"),
                "source": "正文内嵌",
                "text": matched["text"],
                "match_confidence": matched["match_confidence"],
            })

    for uploaded in attachments:
        filename = uploaded.get("filename", "")
        best_declared = None
        best_score = 0.0
        for declared_item in declared:
            score = similarity(filename, declared_item.get("title"))
            if score > best_score:
                best_declared = declared_item
                best_score = score
        if best_declared is not None and best_score >= 0.6:
            source = "单独上传-标题匹配"
            title = best_declared.get("title")
        else:
            source = "单独上传-标题未匹配"
            title = filename
            if declared and total_declared is not None and len(attachments) >= total_declared:
                warn.append(f"上传附件《{filename}》未能与合同声明附件标题高置信度匹配")
        resolved_attachments.append({
            "index": uploaded.get("index"),
            "title": title,
            "source": source,
            "text": uploaded.get("text", ""),
            "match_confidence": "high" if best_score >= 0.6 else "unmatched",
        })

    actual_count = len(resolved_attachments)
    if total_declared is not None and actual_count < total_declared:
        hard.append(f"正文声明附件{total_declared}份，实际仅获取到{actual_count}份")

    check_results: list[CheckItem] = [_check_copies(a4_result)]
    check_results.extend(build_check_items("附件检查-数量标题", "附件数量/标题一致性", hard, warn))
    return {"check_results": check_results, "resolved_attachments": resolved_attachments}
```

- [ ] **Step 4: Run tests**

Run:

```bash
.venv/Scripts/python -m pytest tests/test_contract_review_attachments.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/capabilities/contract_review/attachments.py tests/test_contract_review_attachments.py
git commit -m "feat: resolve contract review attachments"
```

---

### Task 9: Prompt Loading and JSON Parsing

**Files:**

- Create: `prompts/contract_review.yaml`
- Create: `app/capabilities/contract_review/prompts.py`
- Test: `tests/test_contract_review_prompts.py`

- [ ] **Step 1: Write prompt tests**

Create `tests/test_contract_review_prompts.py`:

```python
from langchain_core.messages import HumanMessage, SystemMessage

from app.capabilities.contract_review.prompts import build_prompt, parse_json_object


def test_build_prompt_returns_system_and_human_messages():
    messages = build_prompt("a1a_party_extraction", full_text="合同正文")
    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], HumanMessage)
    assert "合同正文" in messages[1].content


def test_parse_json_object_accepts_plain_json():
    assert parse_json_object('{"x": 1}') == {"x": 1}


def test_parse_json_object_accepts_fenced_json():
    assert parse_json_object('```json\\n{"x": 1}\\n```') == {"x": 1}
```

- [ ] **Step 2: Run tests**

Run:

```bash
.venv/Scripts/python -m pytest tests/test_contract_review_prompts.py -v
```

Expected: FAIL because prompt module does not exist.

- [ ] **Step 3: Implement prompt template and loader**

Create `prompts/contract_review.yaml`:

```yaml
a1a_party_extraction:
  system: |
    你是一个合同信息提取助手。只提取，不判断。输出严格JSON。
  user: |
    请从以下合同全文中提取合同首部签约方、签章区块签约方和正文分节。
    输出字段必须包含：header、signature_parties、sections。
    【合同全文】
    {full_text}

a1b_our_signature:
  system: |
    你是一个合同信息提取助手。只提取我方签署主体签章区块信息。输出严格JSON。
  user: |
    我方签署主体：{our_party}
    【合同全文】
    {full_text}

a3_amount_payment:
  system: |
    你是一个合同信息提取助手。只提取价格和付款条款字段。输出严格JSON。
  user: |
    【合同全文】
    {full_text}

a4_copies_attachments:
  system: |
    你是一个合同信息提取助手。只提取合同份数和附件声明。输出严格JSON。
  user: |
    【合同全文】
    {full_text}

b1_appellation:
  system: |
    你是一个合同审查助手。检查各签约方称谓是否全文统一。输出严格JSON。
  user: |
    【合同全文及附件文本】
    {full_text_and_attachments}

b4_attachment_content:
  system: |
    你是一个合同审查助手。检查附件内容与合同正文关键信息是否一致。输出严格JSON。
  user: |
    【比对基准】
    {baseline}
    【当前附件】
    {attachment_text}
```

Create `app/capabilities/contract_review/prompts.py`:

```python
import json
import re
from pathlib import Path

import yaml
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.core.errors import ModelFormatError

_PROMPT_FILE = Path(__file__).resolve().parents[3] / "prompts" / "contract_review.yaml"
_template: dict | None = None


def _load_template() -> dict:
    global _template
    if _template is None:
        _template = yaml.safe_load(_PROMPT_FILE.read_text(encoding="utf-8"))
    return _template


def build_prompt(name: str, **kwargs) -> list[BaseMessage]:
    tpl = _load_template()[name]
    return [
        SystemMessage(content=tpl["system"].strip()),
        HumanMessage(content=tpl["user"].format(**kwargs)),
    ]


def parse_json_object(content: str) -> dict:
    text = content.strip()
    match = re.match(r"^```(?:json|JSON)?\\s*(.*?)\\s*```$", text, re.S)
    if match:
        text = match.group(1).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ModelFormatError("模型输出不是合法JSON") from exc
    if not isinstance(parsed, dict):
        raise ModelFormatError("模型输出JSON不是对象")
    return parsed
```

- [ ] **Step 4: Run tests**

Run:

```bash
.venv/Scripts/python -m pytest tests/test_contract_review_prompts.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add prompts/contract_review.yaml app/capabilities/contract_review/prompts.py tests/test_contract_review_prompts.py
git commit -m "feat: add contract review prompts"
```

---

### Task 10: Service Orchestration with Mocked LLM Boundary

**Files:**

- Create: `app/capabilities/contract_review/service.py`
- Test: `tests/test_contract_review_service.py`

- [ ] **Step 1: Write service tests**

Create `tests/test_contract_review_service.py`:

```python
from unittest.mock import patch

from app.capabilities.contract_review.schemas import ContractReviewRequest, SystemPreset
from app.capabilities.contract_review.service import review_contract, run_review_pipeline


def test_review_contract_preserves_fail_and_warn_from_checks():
    request = ContractReviewRequest(contract_md="# 合同", attachments=[])
    with patch("app.capabilities.contract_review.service.run_review_pipeline") as fake_pipeline:
        fake_pipeline.return_value = [
            {"id": "序号2", "name": "签章页完整性", "result": "FAIL", "block_level": "硬阻断", "reason": "银行账号不一致"},
            {"id": "序号2", "name": "签章页完整性", "result": "WARN", "block_level": "提示", "reason": "传真缺失"},
        ]
        data = review_contract(request, check_time="2026-07-07T10:00:00")
    assert data.overall_result == "BLOCK"
    assert len(data.checks) == 2


def test_review_contract_does_not_call_real_llm_in_unit_test():
    request = ContractReviewRequest(contract_md="# 合同", attachments=[])
    with patch("app.capabilities.contract_review.service.invoke_model") as fake_invoke:
        with patch("app.capabilities.contract_review.service.run_review_pipeline", return_value=[]):
            review_contract(request, check_time="2026-07-07T10:00:00")
    fake_invoke.assert_not_called()
```

- [ ] **Step 2: Run tests**

Run:

```bash
.venv/Scripts/python -m pytest tests/test_contract_review_service.py -v
```

Expected: FAIL because `service.py` does not exist.

- [ ] **Step 3: Implement service shell**

Create `app/capabilities/contract_review/service.py`:

```python
from datetime import datetime

from app.capabilities.contract_review.checks import build_review_data
from app.capabilities.contract_review.schemas import CheckItem, ContractReviewData, ContractReviewRequest
from app.models.llm import get_chat_model, invoke_model


def run_review_pipeline(request: ContractReviewRequest) -> list[CheckItem | dict]:
    return []


def review_contract(request: ContractReviewRequest, check_time: str | None = None) -> ContractReviewData:
    timestamp = check_time or datetime.now().isoformat(timespec="seconds")
    raw_items = run_review_pipeline(request)
    items = [item if isinstance(item, CheckItem) else CheckItem(**item) for item in raw_items]
    return build_review_data(timestamp, items)
```

- [ ] **Step 4: Run tests**

Run:

```bash
.venv/Scripts/python -m pytest tests/test_contract_review_service.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/capabilities/contract_review/service.py tests/test_contract_review_service.py
git commit -m "feat: add contract review service shell"
```

---

### Task 11: API Router and App Registration

**Files:**

- Create: `app/capabilities/contract_review/router.py`
- Modify: `app/main.py`
- Test: `tests/test_contract_review_api.py`

- [ ] **Step 1: Write API tests**

Create `tests/test_contract_review_api.py`:

```python
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.capabilities.contract_review.schemas import CheckItem, ContractReviewData
from app.main import create_app


def _client():
    return TestClient(create_app(register_middleware=False))


def test_contract_review_success_response_contract():
    fake = ContractReviewData(
        overall_result="BLOCK",
        check_time="2026-07-07T10:00:00",
        checks=[
            CheckItem(id="序号2", name="签章页完整性", result="FAIL", block_level="硬阻断", reason="银行账号不一致"),
            CheckItem(id="序号2", name="签章页完整性", result="WARN", block_level="提示", reason="传真缺失"),
        ],
    )
    with patch("app.capabilities.contract_review.router.review_contract", return_value=fake):
        response = _client().post("/api/v1/contract-review", json={"contract_md": "# 合同", "attachments": []})
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["overall_result"] == "BLOCK"
    assert len(body["data"]["checks"]) == 2
    assert "traceId" in body
    assert "duration_seconds" in body


def test_contract_review_validation_error_returns_10001():
    response = _client().post("/api/v1/contract-review", json={"attachments": []})
    assert response.status_code == 422
    assert response.json()["code"] == 10001
```

- [ ] **Step 2: Run tests**

Run:

```bash
.venv/Scripts/python -m pytest tests/test_contract_review_api.py -v
```

Expected: FAIL because route is not registered.

- [ ] **Step 3: Implement router and registration**

Create `app/capabilities/contract_review/router.py`:

```python
from fastapi import APIRouter

from app.capabilities.contract_review.schemas import ContractReviewRequest
from app.capabilities.contract_review.service import review_contract
from app.core.response import ApiResponse

router = APIRouter(prefix="/api/v1", tags=["contract-review"])


@router.post("/contract-review")
def contract_review_endpoint(request: ContractReviewRequest) -> dict:
    data = review_contract(request)
    body = ApiResponse(data=data).to_dict()
    body.setdefault("traceId", "")
    body.setdefault("duration_seconds", 0.0)
    return body
```

Modify `app/main.py`:

```python
from app.capabilities.contract_review.router import router as contract_review_router
```

Then in `create_app()` after translate registration:

```python
app.include_router(contract_review_router)
```

- [ ] **Step 4: Run API tests**

Run:

```bash
.venv/Scripts/python -m pytest tests/test_contract_review_api.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/capabilities/contract_review/router.py app/main.py tests/test_contract_review_api.py
git commit -m "feat: expose contract review api"
```

---

### Task 12: Full Orchestration and Integration Tests

**Files:**

- Modify: `app/capabilities/contract_review/service.py`
- Modify: `tests/test_contract_review_service.py`

- [ ] **Step 1: Add integration-style service test with mocked pipeline pieces**

Append to `tests/test_contract_review_service.py`:

```python
from app.capabilities.contract_review.schemas import AttachmentInput


def test_review_contract_blocks_when_declared_attachments_missing():
    request = ContractReviewRequest(
        contract_md="# 合同\n正文声明附件共3份",
        attachments=[
            AttachmentInput(index=1, filename="附件一.xlsx", text="附件一"),
            AttachmentInput(index=2, filename="附件二.xlsx", text="附件二"),
        ],
    )
    with patch("app.capabilities.contract_review.service.run_review_pipeline") as fake_pipeline:
        fake_pipeline.return_value = [
            {"id": "附件检查-数量标题", "name": "附件数量/标题一致性", "result": "FAIL", "block_level": "硬阻断", "reason": "正文声明附件3份，实际仅获取到2份"}
        ]
        data = review_contract(request, check_time="2026-07-07T10:00:00")
    assert data.overall_result == "BLOCK"
    assert data.checks[0].reason == "正文声明附件3份，实际仅获取到2份"


def test_run_review_pipeline_uses_llm_adapter_and_preset_fetch():
    request = ContractReviewRequest(
        contract_md="# 合同\n甲方：客户公司\n乙方：我方公司\n附件共3份",
        attachments=[
            AttachmentInput(index=1, filename="附件一.xlsx", text="附件一"),
            AttachmentInput(index=2, filename="附件二.xlsx", text="附件二"),
        ],
    )
    outputs = [
        '{"header":{"contract_name":"测试合同","contract_number":"HT-1","signing_location":"沈阳","signing_date":"2026年7月8日","parties":[{"role":"甲方","name":"客户公司"},{"role":"乙方","name":"我方公司"}]},"signature_parties":[{"role":"甲方","name":"客户公司"},{"role":"乙方","name":"我方公司"}],"sections":[]}',
        '{"signature":{"role":"乙方","name":"我方公司","legal_rep_name":"张三","signing_date":"2026年7月8日","bank_name":"招商银行","bank_account":"123456","account_holder":"我方公司","address":"地址","phone":"024-12345678","fax":"","website":"","postal_code":"110000"}}',
        '{"currency":"人民币","payment_method":"电汇","total_amount_numeric":"100","total_amount_uppercase":"壹佰元整","total_amount_match":true,"payment_stages":[]}',
        '{"copies":{"total_copies":2,"party_copies":[{"role":"甲方","copies":1},{"role":"乙方","copies":1}]},"attachments_declared":[{"index":1,"title":"附件一","content_embedded_in_contract":false},{"index":2,"title":"附件二","content_embedded_in_contract":false},{"index":3,"title":"附件三","content_embedded_in_contract":false}],"total_declared":3}',
        '{"checks":[]}',
        '{"checks":[]}',
        '{"checks":[]}',
    ]

    def fake_invoke(model, messages):
        return outputs.pop(0), {"total_tokens": 1}

    with patch("app.capabilities.contract_review.service.get_chat_model", return_value=object()):
        with patch("app.capabilities.contract_review.service.invoke_model", side_effect=fake_invoke):
            with patch("app.capabilities.contract_review.service.fetch_preset") as fake_fetch:
                fake_fetch.return_value = SystemPreset(
                    entity_name="我方公司",
                    legal_rep_name="张三",
                    legal_rep_id_number="",
                    authorized_reps=[],
                    bank_name="招商银行",
                    bank_account="123456",
                    account_holder="我方公司",
                    address="地址",
                    phone="024-12345678",
                    fax="",
                    website="",
                    postal_code="110000",
                )
                items = run_review_pipeline(request)

    assert fake_fetch.call_args.args == ("我方公司",)
    assert any(item.id == "附件检查-数量标题" and item.result == "FAIL" for item in items)
```

- [ ] **Step 2: Implement orchestration incrementally**

Replace `app/capabilities/contract_review/service.py` with this implementation, preserving `review_contract()`:

```python
from datetime import datetime

from app.capabilities.contract_review.attachments import check_copies_and_attachments
from app.capabilities.contract_review.checks import (
    build_review_data,
    check_amount_payment,
    check_seq1,
    check_seq2_11,
    check_seq3,
)
from app.capabilities.contract_review.preset_client import fetch_preset, identify_our_party
from app.capabilities.contract_review.prompts import build_prompt, parse_json_object
from app.capabilities.contract_review.schemas import (
    CheckItem,
    ContractReviewData,
    ContractReviewRequest,
    HeaderInfo,
    SignatureInfo,
)
from app.core.errors import ModelFormatError
from app.models.llm import get_chat_model, invoke_model


def _require_keys(payload: dict, keys: list[str], prompt_name: str) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise ModelFormatError(f"{prompt_name}模型输出缺少字段：{', '.join(missing)}")


def _invoke_json_prompt(prompt_name: str, **kwargs) -> dict:
    model = get_chat_model()
    content, _usage = invoke_model(model, build_prompt(prompt_name, **kwargs))
    return parse_json_object(content)


def _preprocess_request(request: ContractReviewRequest) -> dict:
    attachment_dicts = [item.model_dump() for item in request.attachments]
    full_text_and_attachments = request.contract_md
    if attachment_dicts:
        attachment_text = "\n\n".join(
            f"【附件】{item.get('filename')}\n{item.get('text', '')}"
            for item in attachment_dicts
        )
        full_text_and_attachments = f"{request.contract_md}\n\n{attachment_text}"
    return {
        "full_text": request.contract_md,
        "full_text_and_attachments": full_text_and_attachments,
        "attachments": attachment_dicts,
    }


def _parse_model_checks(payload: dict, item_id: str, item_name: str) -> list[CheckItem]:
    raw_checks = payload.get("checks", [])
    if not isinstance(raw_checks, list):
        raise ModelFormatError(f"{item_id}模型输出checks不是数组")
    items: list[CheckItem] = []
    for raw in raw_checks:
        if not isinstance(raw, dict):
            raise ModelFormatError(f"{item_id}模型输出checks元素不是对象")
        raw.setdefault("id", item_id)
        raw.setdefault("name", item_name)
        items.append(CheckItem.model_validate(raw))
    if not items:
        items.append(CheckItem(id=item_id, name=item_name, result="PASS", block_level="通过", reason=None))
    return items


def _run_b1(full_text_and_attachments: str) -> list[CheckItem]:
    payload = _invoke_json_prompt("b1_appellation", full_text_and_attachments=full_text_and_attachments)
    return _parse_model_checks(payload, "B-1", "称谓一致性")


def _run_b4(resolved_attachments: list[dict], baseline: dict) -> list[CheckItem]:
    items: list[CheckItem] = []
    for attachment in resolved_attachments:
        payload = _invoke_json_prompt(
            "b4_attachment_content",
            baseline=baseline,
            attachment_text=attachment.get("text", ""),
        )
        items.extend(_parse_model_checks(payload, "B-4", f"附件内容一致性-{attachment.get('title') or attachment.get('index')}"))
    if not resolved_attachments:
        items.append(CheckItem(id="B-4", name="附件内容一致性", result="NA", block_level="不适用", reason="无可检查附件"))
    return items


def run_review_pipeline(request: ContractReviewRequest) -> list[CheckItem | dict]:
    prepared = _preprocess_request(request)

    a1a = _invoke_json_prompt("a1a_party_extraction", full_text=prepared["full_text"])
    _require_keys(a1a, ["header", "signature_parties", "sections"], "A-1a")
    header = HeaderInfo.model_validate(a1a["header"])

    our_party, preset = identify_our_party(header.parties, fetch_preset)

    if our_party is not None:
        a1b = _invoke_json_prompt("a1b_our_signature", our_party=our_party.name, full_text=prepared["full_text"])
        _require_keys(a1b, ["signature"], "A-1b")
        signature = SignatureInfo.model_validate({
            **a1b["signature"],
            "signature_parties": a1a.get("signature_parties", []),
        })
    else:
        signature = SignatureInfo(signature_parties=[])

    items: list[CheckItem] = []
    items.extend(check_seq1(header, our_party, preset))
    seq2_items, seq11_items = check_seq2_11(header, signature, our_party, preset)
    items.extend(seq2_items)
    items.append(check_seq3(header, signature, our_party))
    items.extend(seq11_items)

    a3 = _invoke_json_prompt("a3_amount_payment", full_text=prepared["full_text"])
    items.extend(check_amount_payment(a3))

    a4 = _invoke_json_prompt("a4_copies_attachments", full_text=prepared["full_text"])
    _require_keys(a4, ["copies", "attachments_declared"], "A-4")
    attachment_result = check_copies_and_attachments(
        a4,
        a1a.get("sections", []),
        prepared["attachments"],
        prepared["full_text"],
    )
    items.extend(attachment_result["check_results"])

    items.extend(_run_b1(prepared["full_text_and_attachments"]))
    items.extend(_run_b4(attachment_result["resolved_attachments"], {
        "header": header.model_dump(),
        "signature": signature.model_dump(),
        "preset": preset.model_dump() if preset is not None else None,
    }))
    return items


def review_contract(request: ContractReviewRequest, check_time: str | None = None) -> ContractReviewData:
    timestamp = check_time or datetime.now().isoformat(timespec="seconds")
    raw_items = run_review_pipeline(request)
    items = [item if isinstance(item, CheckItem) else CheckItem(**item) for item in raw_items]
    return build_review_data(timestamp, items)
```

This keeps A-1a responsible for all-party extraction and A-1b responsible only for my-party signature block extraction.

- [ ] **Step 3: Run focused tests**

Run:

```bash
.venv/Scripts/python -m pytest tests/test_contract_review_service.py tests/test_contract_review_api.py -v
```

Expected: PASS.

- [ ] **Step 4: Run full test suite**

Run:

```bash
.venv/Scripts/python -m pytest tests/ -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/capabilities/contract_review/service.py tests/test_contract_review_service.py
git commit -m "feat: orchestrate contract review pipeline"
```

---

### Task 13: Documentation and Final Verification

**Files:**

- Modify: `README.md`
- Modify: `AGENTS.md` only if the user explicitly wants repository guidance updated.

- [ ] **Step 1: Add README API entry**

Modify README interface table to include:

```markdown
| POST | `/api/v1/contract-review` | 是 | 合同组织评审 |
```

Add a short curl example:

```bash
curl -X POST http://localhost:8000/api/v1/contract-review \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-key>" \
  -d '{"contract_md":"# 合同\n正文","attachments":[]}'
```

- [ ] **Step 2: Run full verification**

Run:

```bash
.venv/Scripts/python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 3: Run import/package smoke check**

Run:

```bash
.venv/Scripts/python -c "from app.main import create_app; app=create_app(register_middleware=False); print('routes', len(app.routes))"
```

Expected: prints route count and exits 0.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document contract review api"
```

---

## Self-Review Checklist

- Spec coverage:
  - Input/output contract: Tasks 1, 11
  - Existing response envelope: Tasks 1, 11
  - Error mapping: Tasks 9, 12
  - LLM adapter reuse: Tasks 9, 10, 12
  - Party identification: Tasks 4, 5
  - Preset v1.2 fields: Tasks 1, 5, 6
  - Seq1/2/3/11: Task 6
  - Seq7/8/9/10: Task 7
  - Seq12/attachments: Task 8
  - B-1/B-4: Tasks 9, 12
  - Sensitive ID handling: Tasks 2, 6, 12
  - Duplicate `id` result preservation: Tasks 3, 11

- Placeholder scan:
  - No unfinished placeholder markers or deferred implementation instructions are allowed inside implementation tasks.
  - Task 12 uses named helper functions and explicit orchestration order; it must be implemented in the same task before completion.

- Type consistency:
  - `ContractReviewRequest`, `CheckItem`, `ContractReviewData`, `HeaderInfo`, `SignatureInfo`, `SystemPreset`, and `OurPartyContext` are defined in Task 1 and reused consistently.
  - `build_review_data()` returns `ContractReviewData`.
  - Router returns `ApiResponse(data=data).to_dict()`.
