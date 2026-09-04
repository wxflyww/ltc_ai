# Contract Review Prepare API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变旧合同评审接口的前提下，实现 JSON-only 的 `POST /api/v1/contract-review/prepare`，将当前合同版本的完整 Markdown 快照转换为可校验、可审计、不含正式裁决的六域强类型 `ReviewContext`。

**Architecture:** 新能力物理隔离在 `app/capabilities/contract_review/two_stage/`：请求与公共契约集中在 `schemas.py`，文档快照、证据、稳定键、模型调用、三组领域提取和最终装配分别由无状态模块承担；新路由单独注册到 `app/main.py`。模型层只复用 `app/models/llm.py`，不得导入旧 `service.py`、旧 Prompt、旧结果 Schema 或签署地预设查询。所有模型输出先进入内部候选 Schema，再由后端完成规范化、证据定位、引用闭合、稳定排序和摘要；任何技术失败都使整个请求失败。

**Tech Stack:** Python 3.11、FastAPI、Pydantic v2、LangChain、PyYAML、标准库 `hashlib/json/re/unicodedata/datetime/decimal`、pytest、OpenSpec。

---

## 开始实现前的固定边界

- 实施权威依次为：本 change 的 `spec.md`、`design.md`、两阶段主方案、字段术语表、沟通稿；本计划只拆解实现，不新增业务规则。
- 保留并扩展 `review-context/v1`，因为基础信封尚未对外；不得另建兼容旧动态 `FactDomain.data` 的第二套公开结构。
- Prepare 只输出来源、事实、候选、状态、关系、证据、覆盖和准备问题；代码与测试均不得出现正式 `PASS/WARN/FAIL`、`check_key/reason_key/issue_key` 或流程放行结果。
- `header`、`amount_payment`、`copy_terms` 只覆盖 `main`；`parties`、`signature`、`attachment_manifest` 覆盖 `main` 与全部上传/内嵌附件。
- 输入中的 Markdown、返回的敏感事实和精确证据允许进入 `ReviewContext`，但不得进入普通日志、异常消息、Trace 文件或指标标签。
- 不修改、覆盖或暂存 `config/config-dev.yaml`。实现阶段不得使用 `git add -A`；如需暂存，只能按本计划允许清单逐文件或逐 hunk 操作。未经用户另行授权，不 commit、push、archive。
- 真实 vLLM 联调是独立验收层；mock 测试通过不得表述为真实端点已验证。

## 文件职责与依赖方向

| 文件 | 责任 | 允许依赖 |
|---|---|---|
| `two_stage/schemas.py` | 对外请求、来源快照、六域事实、证据、问题、元数据和 `ReviewContext` 的唯一公开 Schema | Pydantic、标准库 |
| `two_stage/hashing.py` | Markdown、文档集合、Prompt bundle 和上下文摘要 | `schemas.py`、标准库 |
| `two_stage/keys.py` | 由业务坐标生成版本内稳定键，提供稳定排序键 | `schemas.py`、`hashing.py` |
| `two_stage/evidence.py` | Markdown 字符定位、唯一引文定位、证据注册与复用 | `schemas.py`、`keys.py` |
| `two_stage/documents.py` | 输入规范化、上传/内嵌来源识别、快照构建、重复门禁 | `schemas.py`、`hashing.py`、`keys.py` |
| `two_stage/prepare_prompts.py` | 加载 Prepare 专用 YAML，构造消息，不记录正文 | `prompts/contract_review_prepare.yaml` |
| `two_stage/prepare_response_formats.py` | 四类内部模型输出 JSON Schema | 标准库 |
| `two_stage/prepare_model.py` | 调用公共模型适配层、重试、JSON/Pydantic 校验和安全元数据 | `app/models/llm.py`、Prepare Prompt/Schema |
| `two_stage/extract_header_parties.py` | 主合同 header/canonical parties 与逐文档 party mentions | 公共 Schema、证据、键、模型调用 |
| `two_stage/extract_signature.py` | 逐文档签章事实与关系 | 公共 Schema、证据、键、模型调用 |
| `two_stage/extract_commercial.py` | 主合同金额付款/份数及全来源附件清单 | 公共 Schema、证据、键、模型调用 |
| `two_stage/long_document.py` | 四类标准附件可靠识别、全文确定性安全扫描、局部范围计划和覆盖验证 | 标准库、公共 Schema |
| `two_stage/prepare_service.py` | 固定顺序组装完整上下文 | 上述 two-stage 模块、公共配置 |
| `two_stage/prepare_router.py` | `/prepare` 路由和统一响应壳 | 请求 Schema、Prepare 服务、`ApiResponse` |

依赖必须单向流向 `prepare_service.py`；领域提取器之间不得互相导入，跨域引用只在最终装配阶段解析。`app/main.py` 只注册新路由，不改旧 `contract_review.router`。

### Task 1: 冻结 API 请求和六域公共契约

**OpenSpec mapping:** 1.1、1.2、1.3、6.1、8.3

**Files:**
- Modify: `app/capabilities/contract_review/two_stage/schemas.py`
- Modify: `app/capabilities/contract_review/two_stage/__init__.py`
- Modify: `tests/two_stage/test_context_schemas.py`
- Create: `tests/two_stage/test_prepare_request.py`
- Create: `tests/two_stage/factories.py`

- [x] **Step 1: 先把现有基础测试工厂迁移为强类型六域 payload**

在 `tests/two_stage/factories.py` 建立唯一测试构造入口，后续测试不得各自复制一套上下文：

```python
from copy import deepcopy


def complete_domain(data: dict) -> dict:
    return {
        "state": "COMPLETE",
        "coverage": [{
            "document_key": "main",
            "state": "COMPLETE",
            "affected_fact_kinds": [],
            "fact_issue_keys": [],
        }],
        "data": data,
        "issues": [],
    }


def clone_payload(payload: dict) -> dict:
    return deepcopy(payload)
```

工厂必须包含全部六域和统一 `evidence_index.items`；删除旧 `party_mentions/signature_mentions/amount_mentions/attachment_relations` 测试夹具。

- [ ] **Step 2: 编写严格请求和公开结构失败测试**

至少覆盖：`uploaded_attachments=[]` 合法；缺少业务身份、空白 Markdown、非法来源哈希、重复额外字段、请求携带 `review_context_id`、预设、历史结果或人工放行字段均失败；成功 payload 的 `data` 直接是 `ReviewContext`。

```python
def test_prepare_request_rejects_historical_review_fields():
    payload = valid_prepare_request_payload()
    payload["previous_results"] = []
    with pytest.raises(PydanticValidationError, match="previous_results"):
        PrepareRequest.model_validate(payload)


def test_shared_facts_requires_exactly_six_domains():
    payload = valid_context_payload()
    payload["shared_facts"].pop("copy_terms")
    with pytest.raises(PydanticValidationError, match="copy_terms"):
        ReviewContext.model_validate(payload)
```

- [ ] **Step 3: 运行测试并确认 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage/test_prepare_request.py tests/two_stage/test_context_schemas.py -v`

Expected: FAIL，原因是 `PrepareRequest`、强类型域或 `copy_terms` 尚不存在，不是 fixture 或导入错误。

- [x] **Step 4: 实现严格输入模型和公共基类**

请求模型必须是 `extra="forbid"`，并在模型校验阶段完成 Unicode NFC、BOM/换行规范化和规范化后非空校验：

```python
class PrepareMainDocumentInput(_StrictModel):
    document_id: NonBlankStr
    filename: NonBlankStr
    markdown: str
    source_file_sha256: Sha256Digest | None = None


class PrepareUploadedAttachmentInput(_StrictModel):
    attachment_id: NonBlankStr
    filename: NonBlankStr
    markdown: str
    source_file_sha256: Sha256Digest | None = None


class PrepareRequest(_StrictModel):
    contract_id: NonBlankStr
    revision_id: NonBlankStr
    main_document: PrepareMainDocumentInput
    uploaded_attachments: list[PrepareUploadedAttachmentInput] = Field(default_factory=list)
    parser_meta: ParserMeta | None = None
```

Markdown validator 调用 `normalize_markdown` 后检查 `value.strip()`；为避免 `schemas.py -> hashing.py -> schemas.py` 循环，将纯字符串规范化函数移入 `schemas.py` 或一个不依赖 Schema 的 `normalization.py`，`hashing.py` 再复用同一函数，不复制实现。

- [x] **Step 5: 一次性实现设计稿列出的公共模型和六域模型**

`schemas.py` 必须逐项实现 `design.md` 第 2—9 节的字段和 Literal 联合：

```python
T = TypeVar("T")


class ObservedValue(_StrictModel, Generic[T]):
    raw_text: str
    normalized_value: T | None = None
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class ObservedField(_StrictModel, Generic[T]):
    presence: Presence
    normalization_state: NormalizationState
    observations: list[T] = Field(default_factory=list)


class FactDomain(_StrictModel, Generic[T]):
    state: FactState
    coverage: list[DocumentCoverage]
    data: T
    issues: list[FactIssue] = Field(default_factory=list)


class SharedFacts(_StrictModel):
    header: FactDomain[HeaderFacts]
    parties: FactDomain[PartiesFacts]
    signature: FactDomain[SignatureFacts]
    amount_payment: FactDomain[AmountPaymentFacts]
    copy_terms: FactDomain[CopyTermsFacts]
    attachment_manifest: FactDomain[AttachmentManifestFacts]
```

`ObservedField` 的固定不变量：`ABSENT` 时 `observations=[]` 且 `normalization_state=NOT_APPLICABLE`；`PRESENT_EMPTY` 时至少保留一条 `raw_text=""`、`evidence_ids` 非空的 observation 且 `normalization_state=NOT_APPLICABLE`；`PRESENT_VALUE` 时至少一条实质 observation；`UNCERTAIN` 必须保留造成不确定性的候选或来源 observation 及其证据，不得静默选主值。`NOT_APPLICABLE` 只表示没有可规范化的实质值，可与 `ABSENT/PRESENT_EMPTY` 搭配；存在可规范化实质值时不得使用。

- [x] **Step 6: 实现覆盖和问题状态不变量**

`FactDomain` 校验必须保证：

1. `coverage.document_key` 在域内唯一；
2. `COMPLETE` coverage 的 `fact_issue_keys=[]`；
3. `PARTIAL/UNAVAILABLE` coverage 至少引用一个同域 `FactIssue`；
4. 域级 `COMPLETE` 当且仅当所有适用 coverage 完整；
5. 域级 `UNAVAILABLE` 当且仅当所有适用 coverage 不可用；其余存在缺口的组合为 `PARTIAL`；
6. 字段 `ABSENT/PRESENT_EMPTY/INVALID/UNCERTAIN` 不自动产生覆盖问题。

- [x] **Step 7: 运行公共契约测试并确认 GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage/test_prepare_request.py tests/two_stage/test_context_schemas.py -v`

Expected: PASS；序列化后没有旧动态 `data` 值、分类证据容器或字符串 `issues`。

### Task 2: 统一证据、稳定键和全上下文引用校验

**OpenSpec mapping:** 1.4、2.1、2.2、2.3、2.4

**Files:**
- Create: `app/capabilities/contract_review/two_stage/keys.py`
- Create: `app/capabilities/contract_review/two_stage/evidence.py`
- Modify: `app/capabilities/contract_review/two_stage/validation.py`
- Modify: `app/capabilities/contract_review/two_stage/hashing.py`
- Modify: `tests/two_stage/test_context_hashing.py`
- Modify: `tests/two_stage/test_context_validation.py`
- Create: `tests/two_stage/test_evidence_registry.py`
- Create: `tests/two_stage/test_stable_keys.py`

- [x] **Step 1: 编写 locator、切片和引用失败测试**

固定向量必须包含中文、组合字符和 emoji，按规范化 Markdown 的 Python Unicode code point、左闭右开坐标验证：

```python
def test_locator_uses_normalized_unicode_code_points():
    markdown = normalize_markdown("甲😀Cafe\u0301乙")
    item = register_quote("main", markdown, "😀Café")
    assert item.source_locator == "markdown-chars:1-6"
    assert markdown[1:6] == item.quote


def test_quote_must_be_unique_inside_allowed_range():
    with pytest.raises(EvidenceLocationError, match="不唯一"):
        locate_unique_quote("甲乙甲乙", "甲乙", allowed_range=(0, 4))
```

测试还要覆盖 evidence 全局重号、未知文档、悬空 evidence/key 引用、引用错误集合类型、内嵌局部坐标越界和 quote 不一致。

- [ ] **Step 2: 运行证据与键测试并确认 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage/test_evidence_registry.py tests/two_stage/test_stable_keys.py tests/two_stage/test_context_validation.py -v`

Expected: FAIL，原因是注册器、稳定键或新引用校验尚不存在。

- [x] **Step 3: 实现业务坐标稳定键**

稳定键不能包含模型文案、数组位置或随机值。统一函数以“键种类 + 规范化坐标 JSON”生成可读前缀和截断摘要：

```python
def stable_key(kind: str, coordinates: Mapping[str, JsonValue]) -> str:
    payload = {"kind": kind, "coordinates": coordinates}
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()[:24]
    return f"{kind}:{digest}"
```

各对象坐标至少包括 `document_key`、证据起止位置、对象业务种类和必要的父键；同值但不同位置必须产生不同键。重复模型候选若坐标完全相同则合并证据，不新增对象。键只承诺当前 `revision_id/context_digest` 生成过程内可复现，不承诺跨合同版本稳定。

- [x] **Step 4: 实现证据唯一定位与注册表**

```python
class EvidenceRegistry:
    def __init__(self, markdown_by_document: Mapping[str, str]):
        self._markdown_by_document = dict(markdown_by_document)
        self._items_by_coordinate: dict[tuple[str, int, int], EvidenceItem] = {}

    def register(
        self,
        document_key: str,
        quote: str,
        allowed_range: tuple[int, int] | None = None,
    ) -> EvidenceItem:
        start, end = locate_unique_quote(
            self._markdown_by_document[document_key], quote, allowed_range=allowed_range
        )
        coordinate = (document_key, start, end)
        existing = self._items_by_coordinate.get(coordinate)
        if existing is not None:
            return existing
        item = EvidenceItem(
            evidence_id=stable_key("evidence", {
                "document_key": document_key, "start": start, "end": end
            }),
            document_key=document_key,
            source_locator=f"markdown-chars:{start}-{end}",
            quote=quote,
        )
        self._items_by_coordinate[coordinate] = item
        return item
```

模型只能返回短引文候选；`evidence_id` 和 locator 永远由后端生成。歧义/失败由调用方转换成对应事实覆盖缺口；越界、未知文档或组装后切片不一致属于内部装配失败。

- [x] **Step 5: 扩展 `validate_review_context` 的固定校验顺序**

顺序固定为：Schema 版本 → `document_set_hash` → `context_digest` → 文档键 → evidence 唯一性/切片 → 各声明集合键唯一性 → 引用目标存在且类型正确 → coverage/issue 闭合 → 外层合同版本。校验器需要接收可选 `markdown_by_document`；Prepare 返回前必须传入全文映射执行切片校验，Evaluate 消费时没有 Markdown 则只做结构与摘要校验。

- [x] **Step 6: 实现确定性排序并扩充摘要测试**

每个公开数组定义唯一排序字段：来源按 `document_key`；证据按 `(document_key,start,end,evidence_id)`；业务实体按其稳定键；coverage 按 `document_key`；问题按自身键；观察值按首个证据坐标后再按规范化值。组装完成后排序一次，排序后才计算 `context_digest`。

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage/test_evidence_registry.py tests/two_stage/test_stable_keys.py tests/two_stage/test_context_hashing.py tests/two_stage/test_context_validation.py -v`

Expected: PASS；调换输入附件和模型候选顺序时，除 `created_at` 外 payload 与稳定键一致；固定同一 `created_at` 时 `context_digest` 一致。

### Task 3: 输入快照、内嵌附件与模型前重复门禁

**OpenSpec mapping:** 6.2、6.3、6.4

**Files:**
- Create: `app/capabilities/contract_review/two_stage/documents.py`
- Create: `tests/two_stage/test_prepare_documents.py`

- [ ] **Step 1: 编写完整 Markdown 保留和内嵌两跳追溯测试**

测试必须证明：主文档快照摘要基于完整主 Markdown；识别内嵌附件不会从主 Markdown 删除内容；标题有正文才形成来源；内嵌局部 Markdown 从标题开始；快照绝对 locator 的切片等于该局部 Markdown；内嵌证据使用局部坐标。

```python
def test_embedded_attachment_keeps_full_main_snapshot():
    prepared = build_document_inputs(request_with_embedded_attachment())
    assert prepared.markdown_by_document["main"] == normalize_markdown(
        request_with_embedded_attachment().main_document.markdown
    )
    embedded = prepared.source_snapshot.attachments[0]
    start, end = parse_markdown_locator(embedded.source_locator)
    assert prepared.markdown_by_document["main"][start:end] == prepared.markdown_by_document[
        embedded.document_key
    ]
```

- [ ] **Step 2: 编写明确重复零模型调用测试**

参数化覆盖：重复 `attachment_id`；不同 ID 但规范化文件名+内容摘要相同；内嵌/上传规范化标题+内容摘要相同。断言 `prepare_model.invoke_prepare_model` 调用次数为 0，错误为 `ValidationError(code=10001)`，消息只列身份/名称，不含正文。

> 2026-09-02 主控制确认：组件级明确重复门禁已经落地；“模型调用 0 次”和对外 `10001` 必须等待正式 Prepare 服务/API 生产调用链建立后验证，不得使用与 `build_document_inputs` 无调用关系的模型 mock 作为完成证据，因此本步骤保持未勾选。

- [x] **Step 3: 编写疑似重复保留测试**

仅同名、仅同内容摘要以及上传/内嵌存在单因素相似时，都保留全部来源并生成带稳定 `preparation_issue_key` 的 `PreparationIssue`。同一疑似组合只生成一次，调换附件输入顺序不改变问题键。

- [ ] **Step 4: 运行测试并确认 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage/test_prepare_documents.py -v`

Expected: FAIL，原因是文档构建和重复门禁尚不存在。

- [x] **Step 5: 实现不修改主 Markdown 的边界扫描器**

可以复用旧 `_ATTACHMENT_HEADING_RE` 的已验证标题识别语义，但不得调用旧 `split_embedded_attachments`，因为它会把内嵌范围从主合同文本移除且没有精确坐标。新实现按 `splitlines(keepends=True)` 累计字符偏移，只有标题之后到下一个同级附件标题/文末存在非空实质正文时才生成 `EmbeddedAttachmentSnapshot`。

- [x] **Step 6: 实现快照与重复分类**

```python
class PreparedDocuments(_StrictModel):
    source_snapshot: SourceSnapshot
    markdown_by_document: dict[str, str]
    preparation_issues: list[PreparationIssue]


def build_document_inputs(request: PrepareRequest) -> PreparedDocuments:
    normalized = normalize_request_documents(request)
    embedded = discover_embedded_attachments(normalized.main_document)
    reject_definite_duplicates(normalized.uploaded_attachments, embedded)
    issues = find_suspected_duplicates(normalized.uploaded_attachments, embedded)
    return assemble_source_snapshot(normalized, embedded, issues)
```

上传键由 `attachment_id` 的规范化业务身份生成；内嵌键由主文档 ID、绝对范围和标题生成；不得使用输入数组序号。

- [ ] **Step 7: 运行测试并确认 GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage/test_prepare_documents.py tests/two_stage/test_context_hashing.py -v`

Expected: PASS；重复门禁发生在任何模型 mock 之前。

### Task 4: Prepare 专用 Prompt、模型输出 Schema 与安全调用器

**OpenSpec mapping:** 7.1、7.2、7.3、7.4

**Files:**
- Create: `prompts/contract_review_prepare.yaml`
- Create: `app/capabilities/contract_review/two_stage/prepare_prompts.py`
- Create: `app/capabilities/contract_review/two_stage/prepare_response_formats.py`
- Create: `app/capabilities/contract_review/two_stage/prepare_model.py`
- Create: `tests/two_stage/test_prepare_prompts.py`
- Create: `tests/two_stage/test_prepare_model.py`

- [x] **Step 1: 固定四类模型调用，不让实现者自行合并职责**

首期调用名固定为：

1. `prepare_header_parties_main`：主合同首部、canonical parties 和主合同 party mentions；
2. `prepare_signature_document`：对普通文档全文或标准附件安全扫描命中的局部范围提取签章候选；
3. `prepare_amount_copy_main`：主合同金额付款和份数事实；
4. `prepare_attachment_document`：普通附件全文，或四类标准附件安全扫描命中的局部范围中的 party mentions、附件声明/逻辑候选和清单关系候选。

主合同附件声明由 `prepare_attachment_document` 以 `document_key=main` 调用一次；普通附件按全文调用，四类标准附件只按安全扫描命中的局部范围调用。所有来源的标题、编号、边界、来源、摘要和可靠结构化附件标题仍由后端清单处理覆盖，不能因标准附件无模型候选而丢失。附件自身调用不得产生 canonical party、主合同金额或主合同份数候选。

- [x] **Step 2: 编写 Prompt 和 bundle hash 失败测试**

测试必须扫描系统/用户模板及 JSON Schema，拒绝 `PASS/WARN/FAIL`、`check_key`、`reason_key`、Evaluate `issue_key`、旧 Seq/B 编号、预设值、管理员放行和最多三条限制；同时断言 Prompt 明确要求保留全部候选、原文短引文和可定位来源缺口。

`prompt_bundle_hash` 输入固定为按调用名字典序排列的 `{name, system, user, response_schema}` 规范 JSON；任一 Prompt 或 Schema 改动都改变摘要。

- [x] **Step 3: 定义内部候选模型而不是直接反序列化公开模型**

模型输出只允许临时局部引用和 quote，不允许输出任何公开稳定键、locator、digest 或正式状态：

```python
class QuoteCandidate(_StrictModel):
    quote: NonBlankStr


class SourceGapCandidate(_StrictModel):
    affected_fact_kinds: list[NonBlankStr] = Field(min_length=1)
    message: NonBlankStr
    quote: NonBlankStr | None = None


class PrepareModelEnvelope(_StrictModel, Generic[T]):
    candidates: T
    source_gaps: list[SourceGapCandidate] = Field(default_factory=list)
```

四类具体 candidate Schema 必须逐字段列出，`extra="forbid"`；候选之间的临时引用使用单次输出内唯一的 `candidate_ref`，最终装配后全部消失。

`SourceGapCandidate.quote` 仅在确有可信局部原文时提供。截断、乱码、表格丢列或来源边界破损可能没有可验证引文，不得为满足 Schema 伪造 quote；装配后的公开 `FactIssue.evidence_ids` 因此允许为空，但必须始终提供相关 `document_key` 和非空 `affected_fact_kinds`。模型层与装配层测试必须覆盖“无可信 quote 的来源缺口仍形成合法问题且不生成伪证据”。

- [ ] **Step 4: 运行模型层测试并确认 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage/test_prepare_prompts.py tests/two_stage/test_prepare_model.py -v`

Expected: FAIL，原因是专用 Prompt、Schema 或调用器尚不存在。

> 2026-08-31 独立复核：当前工作区未保留最初实现前的 RED 输出，无法事后伪造，因此本步骤保持未勾选；本轮新增的 `candidate_ref` 唯一性和敏感异常上下文测试均已现场观察 RED→GREEN。

- [x] **Step 5: 实现独立调用器和明确重试语义**

```python
def invoke_typed_prepare_model(
    prompt_name: PreparePromptName,
    output_type: type[T],
    **prompt_values: str,
) -> PrepareModelEnvelope[T]:
    model = get_chat_model()
    messages = build_prepare_prompt(prompt_name, **prompt_values)
    response_format = get_prepare_response_format(prompt_name)
    content, usage = invoke_model(model, messages, response_format=response_format)
    payload = parse_json_object_without_logging_content(content)
    return PrepareModelEnvelope[output_type].model_validate(payload)
```

技术规则固定：瞬时调用失败沿用项目 service 层最多 3 次指数退避+抖动；超时耗尽保留 `ModelTimeoutError`；其他调用失败耗尽转 `ModelInvocationError`；JSON/Schema/`finish_reason=length` 只允许一次结构修复重试，第二次失败转相应 `ModelFormatError/ModelOutputTooLongError`。重试日志只包含 `prompt_name/attempt/status/duration/token_usage/error_type`。

- [x] **Step 6: 禁止复用旧敏感 Trace 行为**

新调用器不得调用旧 `_log_llm_trace`，不得把 messages、完整 Markdown、模型 content、quote 或 Pydantic validation input 写入日志/异常。Schema 错误消息只返回调用名、错误类型和失败字段路径，去掉 `input_value`。

- [x] **Step 7: 运行模型层测试并确认 GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage/test_prepare_prompts.py tests/two_stage/test_prepare_model.py -v`

Expected: PASS；导入图中不存在 `app.capabilities.contract_review.service`、旧 prompts 或旧 response formats。

### Task 5: 实现 header 与 parties 提取和装配

**OpenSpec mapping:** 3.1、3.2、3.3、3.4

**Files:**
- Create: `app/capabilities/contract_review/two_stage/extract_header_parties.py`
- Create: `tests/two_stage/test_prepare_header_parties.py`

- [ ] **Step 1: 用模型候选 fixture 编写领域失败测试**

覆盖：合同/项目名称编号不串组；generic/specific/uncertain；签订城市 0..N 候选；ISO 日期合法/非法；首部外值不回填 header；多方合同；空主体栏；多称谓；正文/附件 mentions；附件本地定义只形成 mention；候选数量超过 3 不截断。

- [ ] **Step 2: 运行并确认 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage/test_prepare_header_parties.py -v`

Expected: FAIL，原因是领域装配器尚不存在。

- [ ] **Step 3: 实现两段式 header/parties 装配**

```python
def extract_header_and_main_parties(
    document: PreparedDocument,
    evidence: EvidenceRegistry,
) -> HeaderPartiesExtraction:
    raw = invoke_typed_prepare_model(
        "prepare_header_parties_main",
        HeaderPartiesCandidates,
        markdown=document.markdown,
    )
    return assemble_header_parties(raw, document, evidence)


def extract_attachment_party_mentions(
    document: PreparedDocument,
    canonical_parties: list[CanonicalParty],
    evidence: EvidenceRegistry,
    extraction_ranges: Sequence[MarkdownRange] | None,
) -> list[PartyMention]:
    raw = invoke_attachment_candidates(document, extraction_ranges=extraction_ranges)
    return assemble_party_mentions(raw, canonical_parties, document, evidence)
```

`extraction_ranges=None` 只用于普通附件全文；标准附件必须显式传入安全扫描命中范围，无命中时不调用该函数。模型负责语义候选召回，后端负责日期/字符串规范化、证据定位、稳定键、同坐标去重和候选关系校验。不得用附件候选新增/修改 canonical party，不得生成我方/对方最终分类。

- [ ] **Step 4: 实现域覆盖聚合**

`header.coverage` 永远只有 `main`；`parties.coverage` 包含快照全部文档。可见字段缺失/留空/冲突仍可 `COMPLETE`；仅模型明确返回且证据可定位的源表缺列、乱码或截断才生成 `FactIssue` 并降低对应文档覆盖。

- [ ] **Step 5: 运行并确认 GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage/test_prepare_header_parties.py -v`

Expected: PASS；响应结构中无 `identity_basis`、`our_party_key` 或等级字段。

### Task 6: 实现 signature 实体、关系和逐文档覆盖

**OpenSpec mapping:** 4.1、4.2、4.3、4.4、4.5

**Files:**
- Create: `app/capabilities/contract_review/two_stage/extract_signature.py`
- Create: `tests/two_stage/test_prepare_signature.py`

- [ ] **Step 1: 编写签章结构与关系测试矩阵**

至少包含：一个真实块多个栏位；并列表格按主体拆块；跨页连续块；一栏多人；多栏替代组；多人多号 `UNCERTAIN`；直接关联；块内唯一关联；无关人员；签署日期；块外账户/联系；同用途多值；不同用途分离；附件不回填主合同。

- [ ] **Step 2: 编写所有悬空引用失败测试**

分别破坏 `signature_block_key`、`signer_slot_key`、`signer_key`、`identity_number_key`、`party_key`，断言装配整体失败；不要通过删除坏对象让测试变绿。

- [ ] **Step 3: 运行并确认 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage/test_prepare_signature.py -v`

Expected: FAIL，原因是签章装配器尚不存在。

- [ ] **Step 4: 实现每文档独立提取和稳定装配**

```python
def extract_signature_facts(
    documents: Sequence[PreparedDocument],
    canonical_parties: Sequence[CanonicalParty],
    evidence: EvidenceRegistry,
    extraction_ranges: Mapping[str, Sequence[MarkdownRange]] | None = None,
) -> FactDomain[SignatureFacts]:
    outputs = [
        extract_signature_document(document, canonical_parties, evidence, extraction_ranges)
        for document in sorted(documents, key=lambda item: item.document_key)
    ]
    return merge_signature_outputs(outputs)
```

一个模型 `candidate_ref` 只在该文档调用内有效。后端按父块/栏位/证据坐标生成公开键，再完成替代组和人证关系重映射。禁止按数组位置、距离或预设值自动配对。

- [ ] **Step 5: 实现账户与联系观察的块外规则**

块外来源可省略 `signature_block_key`，但必须保留 `document_key`、主体绑定状态、候选主体、用途状态和证据。只有当前文档原文可靠绑定时才设置 `party_key`；附件观察不得改变主合同观察。

- [ ] **Step 6: 实现逐文档覆盖并确认 GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage/test_prepare_signature.py -v`

Expected: PASS；可靠扫描且没有签章事实的文档为 `COMPLETE`，不是 `UNAVAILABLE`。

### Task 7: 实现金额付款、份数和附件清单

**OpenSpec mapping:** 5.1、5.2、5.3、5.4、5.5

**Files:**
- Create: `app/capabilities/contract_review/two_stage/extract_commercial.py`
- Create: `tests/two_stage/test_prepare_amount_payment.py`
- Create: `tests/two_stage/test_prepare_copy_terms.py`
- Create: `tests/two_stage/test_prepare_attachment_manifest.py`

- [ ] **Step 1: 编写 amount_payment 测试并锁死“不计算”边界**

测试包含所有显式金额、数字/大写单侧、同值不同位置、币种、税务口径、原文明示整体关系、重复阶段、十进制字符串。增加负向断言：不得出现期望阶段金额、比例合计、差额、舍入、尾差吸收或自动生成的大写金额；附件金额不得进入本域。

- [ ] **Step 2: 编写 copy_terms 测试**

覆盖原文明示整体总数索引、各方 `EACH/COLLECTIVE/UNCERTAIN`、冲突陈述、无整体总数时不推算、附件份数排除、`overall_total_statement_key` 悬空失败。

- [ ] **Step 3: 编写 attachment_manifest 测试**

覆盖主合同任意位置声明、声明总数、上传/内嵌实际来源、标题无正文不形成来源、一个物理文件多个逻辑候选、`LINKED/UNCERTAIN` 基数和无关系不造记录。负向断言不得出现 `MISSING/EXTRA/NO_LINK_ESTABLISHED` 或标题一致性结论。

- [ ] **Step 4: 运行三组测试并确认 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage/test_prepare_amount_payment.py tests/two_stage/test_prepare_copy_terms.py tests/two_stage/test_prepare_attachment_manifest.py -v`

Expected: FAIL，原因是商业事实装配器尚不存在。

- [ ] **Step 5: 实现主合同商业事实提取**

金额 `normalized_value` 用已验证的十进制字符串，不转换为 float；只规范化数字表示，不更改原文大写字符。`CONTRACT_OVERALL` 必须有独立原文关系证据。PaymentStage 只引用已存在的 amount/payment method 键。

- [ ] **Step 6: 实现份数和附件清单装配**

份数总值只通过 `overall_total_statement_key` 指向原文明示 statement。附件实际集合只读 `source_snapshot.attachments`；manifest 不复制附件哈希/身份；逻辑候选只引用父文档和局部范围，不增加实际附件数量。

- [ ] **Step 7: 运行并确认 GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage/test_prepare_amount_payment.py tests/two_stage/test_prepare_copy_terms.py tests/two_stage/test_prepare_attachment_manifest.py -v`

Expected: PASS；搜索返回 payload 不包含被禁止的派生计算或裁决字段。

### Task 8: 四类标准附件安全扫描与局部提取

**OpenSpec mapping:** 7.5

**Files:**
- Create: `app/capabilities/contract_review/two_stage/long_document.py`
- Create: `tests/two_stage/test_prepare_long_document.py`
- Modify: `app/capabilities/contract_review/two_stage/prepare_service.py`

- [ ] **Step 1: 编写标准附件目录和可靠识别测试**

首期目录固定为需求说明书、技术规范书、工作说明书和质量标准四类；当前已批准同义名称集合为空，未来只能通过业务确认和版本化变更增加。测试必须证明：文件名单独命中不够；内部文档身份、可靠边界和结构交叉印证且无冲突时才进入标准路径；补充协议、商务协议、目录外类型、身份冲突和边界不可靠均回退普通完整提取；不得由模型或运行时统计扩充目录。

- [ ] **Step 2: 编写全文安全扫描召回测试**

固定测试向量覆盖主体定义与称谓、正文中的“甲方/乙方应……”、签署区、法人/授权人、人员与身份证号关系、签署日期、银行/账户/户名、地址/电话/传真/网站/邮编。扫描器必须遍历规范化 Markdown 全文并输出带绝对字符坐标的 0..N 个候选窗口；不得把单纯技术指标、功能需求或质量指标当作待展开候选。

- [ ] **Step 3: 实现目录分类和安全扫描计划**

```python
STANDARD_ATTACHMENT_TYPES = frozenset({
    "需求说明书",
    "技术规范书",
    "工作说明书",
    "质量标准",
})
APPROVED_STANDARD_ATTACHMENT_ALIASES: Mapping[str, str] = {}


class SafetyScanPlan(_StrictModel):
    document_key: NonBlankStr
    standard_type: NonBlankStr
    scanned_range: MarkdownCharLocator
    candidate_ranges: list[MarkdownCharLocator]
    scan_complete: Literal[True]


def build_standard_attachment_scan_plan(
    document: PreparedDocument,
) -> SafetyScanPlan | None:
    standard_type = classify_standard_attachment(document)
    if standard_type is None:
        return None
    candidate_ranges = scan_complete_markdown_for_review_facts(
        document.markdown,
    )
    plan = SafetyScanPlan(
        document_key=document.document_key,
        standard_type=standard_type,
        scanned_range=format_markdown_locator(0, len(document.markdown)),
        candidate_ranges=merge_overlapping_ranges(candidate_ranges),
        scan_complete=True,
    )
    validate_scan_plan(plan, document.markdown)
    return plan
```

扫描候选窗口必须是规范化 Markdown 的精确切片并保留绝对坐标。窗口重叠时合并范围；不得更改原文或用候选数组序号生成公开键。

- [ ] **Step 4: 编写无候选、命中局部提取和失败闭合测试**

安全扫描无候选时，不调用该附件的全文 LLM 提取，仍保留清单并将相关域聚合为 `COMPLETE` 空事实。命中时只对每个合并后的候选范围调用适用的 `parties/signature` 提取器；相邻窗口返回同一事实时按最终证据坐标去重。同值但不同位置仍保留。扫描、范围定位、局部调用、证据装配或合并任一步失败时整个 Prepare 请求失败。

- [ ] **Step 5: 接入服务并运行标准附件测试**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage/test_prepare_long_document.py -v`

Expected: 全部 PASS；四类标准附件完整进入清单且安全扫描覆盖全文，无候选不展开整份 LLM，命中只提取局部；目录外或识别不可靠附件走普通完整提取。

### Task 9: 无状态 Prepare 服务装配

**OpenSpec mapping:** 8.1

**Files:**
- Create: `app/capabilities/contract_review/two_stage/prepare_service.py`
- Create: `tests/two_stage/test_prepare_service.py`

- [ ] **Step 1: 编写固定调用顺序和零共享状态测试**

测试用 mock 记录阶段顺序，必须精确等于：

```python
EXPECTED_STAGES = [
    "normalize_request",
    "build_source_snapshot",
    "discover_embedded",
    "reject_duplicates",
    "classify_and_scan_standard_attachments",
    "extract_header_parties",
    "extract_signature",
    "extract_amount_copy_manifest",
    "assemble_evidence_and_coverage",
    "validate_references",
    "sort_payload",
    "compute_hashes",
]
```

并发/连续两个请求使用不同合同内容时，不得交叉复用 evidence、候选、issue、token 或文档映射。

- [ ] **Step 2: 编写技术失败与覆盖不足对照测试**

模型超时、调用失败、输出截断、Schema 重试耗尽、证据装配异常、悬空引用、摘要失败都断言没有 `ReviewContext`。只有具有具体文档、事实类别和可验证来源的局部可读性缺口才能生成 `PARTIAL/UNAVAILABLE`。

- [ ] **Step 3: 运行并确认 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage/test_prepare_service.py -v`

Expected: FAIL，原因是顶层服务尚不存在。

- [ ] **Step 4: 实现唯一公开服务入口**

```python
PIPELINE_VERSION = "contract-review-prepare/1.0.0"


def prepare_contract(request: PrepareRequest) -> ReviewContext:
    documents = build_document_inputs(request)
    evidence = EvidenceRegistry(documents.markdown_by_document)
    standard_scan_plans = build_standard_attachment_scan_plans(documents)
    extracted = run_all_extractors(documents, evidence, standard_scan_plans)
    context = assemble_review_context(
        request=request,
        documents=documents,
        extracted=extracted,
        evidence=evidence,
        pipeline_version=PIPELINE_VERSION,
        prompt_bundle_hash=compute_prepare_prompt_bundle_hash(),
        model_deployment=get_settings().llm.model,
        created_at=datetime.now(timezone.utc),
    )
    context = sort_review_context(context)
    context = set_context_digest(context)
    validate_review_context(
        context,
        contract_id=request.contract_id,
        revision_id=request.revision_id,
        markdown_by_document=documents.markdown_by_document,
    )
    return context
```

服务不得持久化、缓存业务 payload 或回调合同系统。`created_at` 由可注入 clock 提供以便确定性测试；生产默认 UTC 带时区时间。

- [ ] **Step 5: 运行服务测试并确认 GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage/test_prepare_service.py -v`

Expected: PASS；同输入、同模型候选、同 clock 的序列化结果和 digest 完全相同。

### Task 10: 注册 JSON-only 路由、错误映射和敏感数据保护

**OpenSpec mapping:** 8.2、8.3、8.4、8.5

**Files:**
- Create: `app/capabilities/contract_review/two_stage/prepare_router.py`
- Modify: `app/main.py`
- Create: `tests/two_stage/test_prepare_api.py`
- Create: `tests/two_stage/test_prepare_logging.py`
- Modify: `tests/test_contract_review_api.py` only if a regression assertion is needed; do not change existing expectations

- [ ] **Step 1: 编写 API 契约失败测试**

覆盖成功、FastAPI 422/`10001`、业务输入 `10001`、模型调用 `20001`、超时 `20002`、格式/输出过长 `20003`、未知 `29999`；失败 `data=null`。还要断言 multipart 请求不被当作 Prepare JSON 接受。

```python
def test_prepare_success_data_is_review_context_directly():
    with patch(PREPARE_SERVICE_TARGET, return_value=valid_context()) as mocked:
        response = client().post("/api/v1/contract-review/prepare", json=valid_request())
    assert response.status_code == 200
    assert response.json()["data"]["schema_version"] == "review-context/v1"
    assert "review_context" not in response.json()["data"]
    mocked.assert_called_once()
```

- [ ] **Step 2: 编写旧路由物理隔离回归测试**

Patch 新旧两个 service 入口，分别调用三条 API，断言 `/prepare` 只调用 `prepare_contract`，旧两条路由只调用 `review_contract`；旧请求、结果和 HTTP 期望原样保留。

- [ ] **Step 3: 编写日志泄露测试**

构造含完整身份证号、银行账号、电话、Markdown 和独特证据引文的成功与失败请求，捕获 `caplog` 和可写入的审计 sink，断言这些原文都不存在；允许字段仅为调用名、耗时、token、重试次数、状态、错误类型、trace ID。

- [ ] **Step 4: 运行并确认 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage/test_prepare_api.py tests/two_stage/test_prepare_logging.py tests/test_contract_review_api.py -v`

Expected: FAIL，原因是新路由尚未注册。

- [ ] **Step 5: 实现独立路由并注册**

```python
router = APIRouter(prefix="/api/v1/contract-review", tags=["contract-review-prepare"])


@router.post("/prepare")
def prepare_contract_endpoint(request: PrepareRequest) -> dict:
    context = prepare_contract(request)
    body = ApiResponse(data=context.to_payload()).to_dict()
    body.setdefault("traceId", "")
    body.setdefault("duration_seconds", 0.0)
    return body
```

`app/main.py` 只增加 `app.include_router(contract_review_prepare_router)`；不要把 Prepare 函数导入旧 router，不要修改旧 endpoint。

- [ ] **Step 6: 运行 API、日志和旧回归并确认 GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage/test_prepare_api.py tests/two_stage/test_prepare_logging.py tests/test_contract_review_api.py -v`

Expected: PASS；普通日志和审计文件不含测试敏感标记。

### Task 11: 覆盖审计、全量验证和权威文档同步

**OpenSpec mapping:** 9.1、9.2、9.3、9.4、9.5、9.6

**Files:**
- Modify after implementation evidence exists: `docs/superpowers/specs/2026-07-28-contract-review-two-stage-upgrade-draft.md`
- Modify after implementation evidence exists: `docs/superpowers/specs/2026-08-03-contract-review-two-stage-field-glossary.md`
- Modify after implementation evidence exists: `docs/integration/2026-07-28-contract-system-two-stage-review-communication-draft.md`
- Modify: `openspec/changes/contract-review-prepare-api/tasks.md`

- [ ] **Step 1: 执行静态边界扫描**

Run: `rg -n "run_review_pipeline|signing_preset|PASS|WARN|FAIL|check_key|reason_key|issue_key" app/capabilities/contract_review/two_stage prompts/contract_review_prepare.yaml`

Expected: `run_review_pipeline`、`signing_preset` 和正式结果字段无命中；`FactIssue/PreparationIssue` 中作为单词组成部分的命中需人工核对，不得存在裸 Evaluate `issue_key`。

Run: `rg -n "app\.capabilities\.contract_review\.(service|prompts|response_formats)" app/capabilities/contract_review/two_stage`

Expected: 无命中。

- [ ] **Step 2: 运行定点测试**

Run: `.venv\Scripts\python.exe -m pytest tests/two_stage -v`

Expected: 全部 PASS；记录通过数、耗时和警告。Task 8 必须证明标准附件完整清单、安全扫描全文覆盖、局部调用及失败闭合，不得用 skipped/xfail 或仅验证分类代替扫描与调用测试。

- [ ] **Step 3: 运行旧合同评审和全量回归**

Run: `.venv\Scripts\python.exe -m pytest tests -q -k contract_review`

Run: `.venv\Scripts\python.exe -m pytest tests -q`

Expected: 旧合同评审期望不变，全量 PASS；若存在变更前即可复现的基线失败，记录用例、错误和基线证据，不修改旧期望制造全绿。

- [ ] **Step 4: 对六域与 Evaluate 依赖做结构覆盖审计**

逐项核对：0/1/N 数量、键唯一范围、全部引用、唯一事实来源、域覆盖适用文档、同值重复/异值冲突、字段缺失与覆盖不足、附件不修改主合同基准。确认附件金额比较仍未迁入 Prepare，Seq7/Seq10 算术和大写裁决仍由 Evaluate 承担。

- [ ] **Step 5: 执行真实 vLLM 端点联调**

至少覆盖：无附件、多上传附件、正文内嵌附件、四类长篇标准附件安全扫描无命中/命中局部提取、目录外长附件普通提取、多方/多候选、敏感字段。逐份检查完整 JSON Schema、证据切片、稳定引用、覆盖、日志泄露、token 和耗时。

Expected: 记录真实请求环境和结果；如果没有端点/样本/授权，明确标为“真实端点未验证”，不得把 mock 测试写成联调通过。

- [ ] **Step 6: 只根据已落地行为同步三份权威文档**

主方案更新 Prepare 实施状态和真实限制；术语表把实际字段从“设计待定/基础”更新为已实施来源；沟通稿补充最终请求/响应和调用方保存要求。只改本 change 影响的状态和引用，不重写已经冻结的业务结论。

- [ ] **Step 7: 更新 OpenSpec task 状态并严格校验**

只有测试和证据真实完成后才勾选对应 task。Task 8 未证明分类、完整扫描、局部调用、普通提取回退和失败闭合时，保持 7.5 未勾选。

Run: `openspec.cmd validate contract-review-prepare-api --strict --no-interactive`

Run: `openspec.cmd validate --all --strict --no-interactive`

Expected: 两条命令退出码 0。

- [ ] **Step 8: 检查变更范围和受保护文件**

Run: `git status --short`

Run: `git diff --check`

Run: `git diff -- config/config-dev.yaml`

Expected: `git diff --check` 退出码 0；`config/config-dev.yaml` 仍只包含用户原有修改，本阶段没有新增 hunk。实施允许范围仅包括本计划列出的 two-stage 模块、Prepare Prompt、对应测试、`app/main.py`、本 OpenSpec task 状态和三份权威文档。

## 阶段3完成判定

只有同时满足以下条件，才能把 `contract-review-prepare-api` 称为“实现完成”：

1. OpenSpec 1—8 的适用任务都有对应 RED→GREEN 证据；
2. 六域强类型上下文、证据切片、稳定键、引用完整性和摘要校验通过；
3. 新旧三条 API 物理隔离且旧回归不变；
4. 技术失败不返回残缺上下文，覆盖不足不伪装业务缺失；
5. 敏感数据日志审计通过；
6. 四类标准附件具有可靠分类、完整清单、全文安全扫描及必要局部提取证据，目录外/不可靠附件正常完整提取；
7. 定点、旧回归、全量测试和严格 OpenSpec 校验完成；
8. 真实端点证据与自动化证据分层记录；
9. 三份权威文档只同步已实现事实；
10. `config/config-dev.yaml` 未被本 change 修改或暂存。

阶段3实施者完成每个 Task 后应停在可审查边界，提供：已修改文件、对应 OpenSpec task、测试命令与实际结果、尚未验证内容。不得自行 commit、push、archive，也不得扩大到 Evaluate 实现。
