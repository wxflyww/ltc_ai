# Contract Review Context Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变旧合同评审接口的前提下，实现版本化 `ReviewContext` 领域模型、确定性摘要和跨字段一致性校验。

**Architecture:** 新代码全部位于 `app/capabilities/contract_review/two_stage/`，由 `schemas.py`、`hashing.py` 和 `validation.py` 三个无副作用模块组成。新测试独立放在 `tests/two_stage/`；旧 `router.py`、`service.py`、Prompt 和模型调用保持不变。

**Tech Stack:** Python 3.11、Pydantic v2、标准库 `hashlib/json/unicodedata/pathlib`、pytest、OpenSpec。

---

### Task 1: ReviewContext 领域模型

**Files:**
- Create: `tests/two_stage/test_context_schemas.py`
- Create: `app/capabilities/contract_review/two_stage/schemas.py`
- Modify: `app/capabilities/contract_review/two_stage/__init__.py`

- [x] **Step 1: 编写来源、事实和证据模型失败测试**

测试必须直接实例化真实 Pydantic 模型，并至少覆盖：

```python
def test_source_snapshot_accepts_uploaded_and_embedded_union():
    snapshot = make_source_snapshot()
    assert snapshot.attachments[0].source_kind == "UPLOADED"
    assert snapshot.attachments[1].source_kind == "EMBEDDED"

def test_source_snapshot_rejects_duplicate_document_keys():
    with pytest.raises(ValidationError, match="document_key"):
        SourceSnapshot.model_validate(duplicate_key_payload())

def test_partial_fact_requires_issue():
    with pytest.raises(ValidationError, match="issues"):
        FactDomain(state="PARTIAL", data={}, issues=[])

def test_evidence_requires_traceable_quote():
    with pytest.raises(ValidationError):
        EvidenceRef(document_key="main", source_locator="", quote="")

def test_context_payload_omits_optional_source_metadata():
    payload = make_context().to_payload()
    assert "source_file_sha256" not in payload["source_snapshot"]["main_document"]
    assert "parser_meta" not in payload["source_snapshot"]
```

- [x] **Step 2: 运行测试并确认因模块或类型尚不存在而失败**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage/test_context_schemas.py -v`

Expected: FAIL，原因是 `two_stage.schemas` 或目标模型尚不存在，不是测试语法错误。

- [x] **Step 3: 实现最小领域模型**

`schemas.py` 必须定义并校验以下公开类型：

```python
SCHEMA_VERSION = "review-context/v1"
FactState = Literal["COMPLETE", "PARTIAL", "UNAVAILABLE"]

class MainDocumentSnapshot(BaseModel): ...
class UploadedAttachmentSnapshot(BaseModel): ...
class EmbeddedAttachmentSnapshot(BaseModel): ...
AttachmentSnapshot = Annotated[
    UploadedAttachmentSnapshot | EmbeddedAttachmentSnapshot,
    Field(discriminator="source_kind"),
]
class SourceSnapshot(BaseModel): ...
class FactDomain(BaseModel): ...
class SharedFacts(BaseModel): ...
class EvidenceRef(BaseModel): ...
class EvidenceIndex(BaseModel): ...
class PreparationIssue(BaseModel): ...
class PreparationMeta(BaseModel): ...
class ReviewContext(BaseModel):
    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)
```

所有身份、定位和引文字段使用 `min_length=1`；SHA-256 字段匹配 `^sha256:[0-9a-f]{64}$`。`SourceSnapshot` 拒绝重复键和附件键 `main`；`FactDomain` 强制非完整状态说明原因，完整状态不得携带缺口。

- [x] **Step 4: 运行模型测试并确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage/test_context_schemas.py -v`

Expected: PASS。

### Task 2: 确定性规范化与摘要

**Files:**
- Create: `tests/two_stage/test_context_hashing.py`
- Create: `app/capabilities/contract_review/two_stage/hashing.py`

- [x] **Step 1: 编写固定测试向量**

测试必须覆盖以下可复现行为：

```python
def test_markdown_hash_normalizes_bom_newlines_and_unicode():
    left = "\ufeff# Caf\u00e9\r\n正文\r"
    right = "# Cafe\u0301\n正文\n"
    assert parsed_content_sha256(left) == parsed_content_sha256(right)

def test_markdown_hash_preserves_spaces_and_markup():
    assert parsed_content_sha256("# A\n") != parsed_content_sha256("#  A\n")

def test_document_set_hash_is_attachment_order_independent():
    first = make_snapshot(attachments=[uploaded(), embedded()])
    second = make_snapshot(attachments=[embedded(), uploaded()])
    assert compute_document_set_hash(first) == compute_document_set_hash(second)

def test_context_digest_ignores_existing_digest_and_json_key_order():
    assert compute_context_digest(payload_a()) == compute_context_digest(payload_b())
```

- [x] **Step 2: 运行测试并确认目标函数尚不存在**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage/test_context_hashing.py -v`

Expected: FAIL，原因是摘要函数尚未实现。

- [x] **Step 3: 实现纯摘要函数**

`hashing.py` 必须提供：

```python
def normalize_markdown(markdown: str) -> str: ...
def parsed_content_sha256(markdown: str) -> str: ...
def normalize_snapshot_name(value: str) -> str: ...
def canonical_json_bytes(value: Any) -> bytes: ...
def compute_document_set_hash(
    source: SourceSnapshot | MainDocumentSnapshot,
    attachments: Sequence[AttachmentSnapshot] | None = None,
) -> str: ...
def compute_context_digest(context: ReviewContext | Mapping[str, Any]) -> str: ...
```

`canonical_json_bytes` 使用 `ensure_ascii=False`、`sort_keys=True`、`separators=(",", ":")`、`allow_nan=False`；摘要统一加 `sha256:` 前缀。文档集合主文档固定第一，附件按 `document_key` 排序，内嵌附件以 `title` 填入统一的 `filename` 摘要槽位。

- [x] **Step 4: 运行摘要测试并确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage/test_context_hashing.py -v`

Expected: PASS。

### Task 3: ReviewContext 一致性校验

**Files:**
- Create: `tests/two_stage/test_context_validation.py`
- Create: `app/capabilities/contract_review/two_stage/validation.py`
- Modify: `app/capabilities/contract_review/two_stage/__init__.py`

- [x] **Step 1: 编写五类失败路径测试**

```python
def test_rejects_unsupported_schema():
    with pytest.raises(ContextSchemaUnsupportedError):
        validate_review_context(context_with(schema_version="review-context/v2"))

def test_rejects_changed_document_set():
    with pytest.raises(ContextIntegrityError, match="document_set_hash"):
        validate_review_context(context_with_wrong_document_set_hash())

def test_rejects_changed_context_payload():
    with pytest.raises(ContextIntegrityError, match="context_digest"):
        validate_review_context(tampered_context())

def test_rejects_evidence_pointing_outside_snapshot():
    with pytest.raises(ContextIntegrityError, match="document_key"):
        validate_review_context(context_with_unknown_evidence_document())

def test_rejects_outer_revision_mismatch():
    with pytest.raises(DocumentRevisionMismatchError):
        validate_review_context(valid_context(), contract_id="C001", revision_id="V2")
```

- [x] **Step 2: 运行测试并确认校验器尚不存在**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage/test_context_validation.py -v`

Expected: FAIL，原因是领域异常或 `validate_review_context` 尚未实现。

- [x] **Step 3: 实现异常和固定校验顺序**

```python
class ReviewContextValidationError(ValueError): ...
class ContextSchemaUnsupportedError(ReviewContextValidationError): ...
class ContextIntegrityError(ReviewContextValidationError): ...
class DocumentRevisionMismatchError(ReviewContextValidationError): ...

def validate_review_context(
    context: ReviewContext,
    *,
    contract_id: str | None = None,
    revision_id: str | None = None,
) -> None:
    # 1. schema；2. document_set_hash；3. context_digest；4. 证据来源；5. 外层版本
    ...
```

校验失败不得返回 PASS/WARN/FAIL，也不在本变更中映射 HTTP 错误码。

- [x] **Step 4: 运行校验测试和全部两阶段测试**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage -v`

Expected: PASS。

### Task 4: 打包、回归和规范校验

**Files:**
- Modify: `pyproject.toml`
- Modify: `docs/superpowers/specs/2026-07-28-contract-review-two-stage-upgrade-draft.md`
- Modify: `docs/integration/2026-07-28-contract-system-two-stage-review-communication-draft.md`
- Modify: `openspec/changes/contract-review-context-foundation/tasks.md`
- Modify: `docs/superpowers/plans/2026-07-31-contract-review-context-foundation.md`

- [x] **Step 1: 将新子包加入打包清单**

在 `[tool.setuptools].packages` 中增加：

```toml
"app.capabilities.contract_review.two_stage",
```

- [x] **Step 2: 运行定点和旧合同评审回归**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage -v`

Run: `.venv\Scripts\python.exe -m pytest tests -q -k contract_review`

Expected: 两阶段测试和旧合同评审测试均 PASS。

- [x] **Step 3: 运行完整测试**

Run: `.venv\Scripts\python.exe -m pytest tests -q`

Expected: 全量 PASS；只允许记录基线已有的 Starlette/httpx 弃用警告。

- [x] **Step 4: 严格校验 OpenSpec 和变更格式**

Run: `openspec.cmd validate contract-review-context-foundation --strict`

Run: `git diff --check`

Expected: 两条命令均退出码 0。

- [x] **Step 5: 更新任务状态并复核范围**

确认所有 OpenSpec 任务标记为完成；`git diff --stat` 只包含本 change、实施计划、新模块、新测试、打包清单、正式 Schema 权威来源同步，以及已承诺的基线 Markdown 行尾清理。按用户要求不创建实现提交，只在最终回复中给出建议提交边界和提交信息。
