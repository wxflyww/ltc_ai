from __future__ import annotations

"""Task 7 Step 1-4: attachment_manifest 商业事实闭合矩阵。

闭合矩阵（正式要求 -> 候选/Schema -> 装配对象与引用 -> 证据/coverage -> 稳定键 -> 测试）：

| 正式要求 (spec) | 候选 (AttachmentCandidate) | 装配对象/引用 | 证据 / 逐文档 coverage | 稳定键 | 测试 |
|---|---|---|---|---|---|
| 主合同任意位置声明附件与显式总数 (spec 224) | DECLARED_TOTAL + DECLARED_ATTACHMENT | AttachmentManifestFacts.declared_total + declarations[] | 声明/总数 evidence_ids>=1 | declaration key 由坐标 | test_attachment_manifest_declared_total_and_declarations_from_main |
| 实际来源仅来自 source_snapshot.attachments (spec 224) | 各文档候选 | coverage 覆盖 main + 全部附件 | 无正文标题不新增来源 | 文档键来自 snapshot | test_attachment_manifest_actual_sources_only_from_snapshot_not_headings |
| 一个物理文件含 0..N 逻辑候选且不加物理数量 (spec 226-230) | LOGICAL_ATTACHMENT | LogicalAttachmentCandidate(parent_document_key!=main) | 局部范围 source_locator + 证据 | 逻辑候选键由坐标 | test_attachment_manifest_multiple_logical_candidates_do_not_add_physical_attachments |
| 关系 LINKED 只引用一个实际文档, UNCERTAIN 可多候选 (spec 224) | ATTACHMENT_RELATION | AttachmentRelation.relation_state | link evidence_ids>=1 | relation key 由坐标 | test_attachment_manifest_links_linked_single_target_uncertain_allows_candidates |
| 无可关联来源不造 link, 不输出缺失结论 (spec 232-235) | 仅 DECLARED_ATTACHMENT | links 为空 | 保留声明 | - | test_attachment_manifest_no_relation_creates_no_link_record |
| 禁止 MISSING/EXTRA/NO_LINK_ESTABLISHED/标题一致性/正式裁决 (spec 224) | 全量候选 | 数据中不得出现禁词 | - | - | test_attachment_manifest_forbidden_conclusions_absent |
| 引用与稳定键闭合 (spec 237-243) | 乱序 + 改名 | 闭合的 declaration/link 引用 | - | 键不含 candidate_ref/顺序 | test_attachment_manifest_reference_closure_and_stable_keys |
| 关系模型输入含当前文档键与快照可选目标键 | ATTACHMENT_RELATION(逐文档调用) | 调用入参含当前 document_key 与快照可选目标 collection | 目标限实际 document_key | - | test_attachment_manifest_relation_model_input_exposes_document_keys |
| 关系目标非实际 document_key (rogue/candidate_ref) | ATTACHMENT_RELATION | 拒绝并 ModelFormatError | - | - | test_attachment_manifest_relation_target_rejects_non_snapshot_and_candidate_ref |
| 关系目标限快照附件集合(正文键亦不例外) | ATTACHMENT_RELATION | 快照外目标 ModelFormatError | - | - | test_attachment_manifest_relation_target_outside_snapshot_rejected_even_if_markdown_present |
| 关系目标不得等同本次调用任一 candidate_ref | ATTACHMENT_RELATION | 目标==候选ref ModelFormatError | - | - | test_attachment_manifest_relation_target_cannot_equal_candidate_ref_even_if_snapshot_key |
| Schema 层守卫(已可绿) | - | AttachmentManifestFacts/AttachmentRelation 校验 | - | - | test_attachment_manifest_schema_rejects_dangling_and_illegal_relation_targets |

Schema 守卫测试（test_attachment_manifest_schema_rejects_dangling_and_illegal_relation_targets）
验证已存在的公共契约；其余用例断言商业装配行为是否闭合, 装配能力缺失或与正式条款不一致时
相应用例失败, 直接指向缺口, 不经由 fixture、导入或环境错误伪装。

入口契约（DEC-LTC-20260910-003）：
1. 装配入口模块 app/capabilities/contract_review/two_stage/extract_commercial.py，
   唯一入口 extract_amount_copy_manifest(documents: PreparedDocuments,
   canonical_parties, evidence, extraction_ranges=None) -> CommercialFactDomains。
2. 结果仅承载 amount_payment、copy_terms、attachment_manifest 三个 FactDomain；
   _domain_from 直取 attachment_manifest 域。
3. documents 为 PreparedDocuments（source_snapshot + markdown_by_document）；
   模型调用经模块 invoke_typed_prepare_model（沿用 Task 5/6 导入约定，便于定点 patch）。
4. ATTACHMENT_RELATION 候选以 relation_declaration_ref 引用同一输出内 DECLARED_ATTACHMENT
   候选的 candidate_ref，关系目标只接受实际 document_key（relation_target_document_keys），
   不得用候选 ref 充当公开文档键；LOGICAL_ATTACHMENT 的 source_locator 由其已定位引文生成。
"""

import importlib
import json
from typing import Any
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.capabilities.contract_review.two_stage.documents import PreparedDocuments
from app.capabilities.contract_review.two_stage.evidence import EvidenceRegistry
from app.capabilities.contract_review.two_stage.extract_header_parties import PreparedDocument
from app.capabilities.contract_review.two_stage.keys import stable_key
from app.capabilities.contract_review.two_stage.prepare_model import (
    AmountCopyCandidate,
    AttachmentCandidate,
    PrepareModelEnvelope,
)
from app.capabilities.contract_review.two_stage.schemas import (
    AttachmentManifestFacts,
    AttachmentRelation,
    CanonicalParty,
    EmbeddedAttachmentSnapshot,
    MainDocumentSnapshot,
    ObservedField,
    ObservedValue,
    SourceSnapshot,
    UploadedAttachmentSnapshot,
)
from app.core.errors import ModelFormatError

COMMERCIAL_MODULE = "app.capabilities.contract_review.two_stage.extract_commercial"
_ENTRY_CANDIDATES = ("extract_amount_copy_manifest",)
RED_REASON = (
    "Task 7 商业装配入口不可用（非 fixture/导入/环境错误）；"
    "装配入口与返回结构已由 DEC-LTC-20260910-003 固定"
)

MAIN_MD = (
    "采购合同\n"
    "甲方：甲乙科技有限公司\n"
    "乙方：丙丁工程有限公司\n"
    "本合同附件如下：\n"
    "附件一：技术规范书\n"
    "附件二：报价明细\n"
    "附件三：履约保证\n"
    "附件合计叁份\n"
)

UPLOADED_MD = (
    "技术规范书\n"
    "第一部分：总体架构\n"
    "第二部分：接口清单\n"
)

EMBEDDED_MD = (
    "附件二：报价明细\n"
)

_SNAPSHOT_ATTACHMENT_KEYS = ("uploaded:att-001", "embedded:main:001")
_ALL_DOCUMENT_KEYS = ("main",) + _SNAPSHOT_ATTACHMENT_KEYS

_FORBIDDEN_TOKENS = (
    "MISSING",
    "EXTRA",
    "NO_LINK_ESTABLISHED",
    "标题一致性",
    "正式裁决",
)


def _assembler():
    try:
        return importlib.import_module(COMMERCIAL_MODULE)
    except ImportError:
        pytest.fail(RED_REASON + "：模块 " + COMMERCIAL_MODULE + " 不存在", pytrace=False)


def _extract_fn(module):
    for name in _ENTRY_CANDIDATES:
        fn = getattr(module, name, None)
        if callable(fn):
            return fn
    pytest.fail(
        RED_REASON + "：装配入口缺失（候选名：" + ", ".join(_ENTRY_CANDIDATES) + "）",
        pytrace=False,
    )


def _setup():
    registry = EvidenceRegistry(
        {
            "main": MAIN_MD,
            "uploaded:att-001": UPLOADED_MD,
            "embedded:main:001": EMBEDDED_MD,
        }
    )

    def _party(name: str, def_quote: str) -> CanonicalParty:
        ev = registry.register("main", def_quote)
        return CanonicalParty(
            party_key=stable_key("party", {"declared_name": name}),
            declared_name=ObservedField(
                presence="PRESENT_VALUE",
                normalization_state="VALID",
                observations=[
                    ObservedValue(
                        raw_text=name,
                        normalized_value=name,
                        evidence_ids=[ev.evidence_id],
                    )
                ],
            ),
            definition_evidence_ids=[ev.evidence_id],
        )

    canonical = [
        _party("甲乙科技有限公司", "甲方：甲乙科技有限公司"),
        _party("丙丁工程有限公司", "乙方：丙丁工程有限公司"),
    ]
    docs = {
        "main": PreparedDocument(document_key="main", markdown=MAIN_MD),
        "uploaded:att-001": PreparedDocument(
            document_key="uploaded:att-001", markdown=UPLOADED_MD
        ),
        "embedded:main:001": PreparedDocument(
            document_key="embedded:main:001", markdown=EMBEDDED_MD
        ),
    }
    return registry, canonical, docs


def _snapshot_with_attachments(attachment_keys: list[str]) -> SourceSnapshot:
    """构造含 main 与指定附件键的真实 SourceSnapshot（字段沿用现有快照口径）。"""
    attachments: list[UploadedAttachmentSnapshot | EmbeddedAttachmentSnapshot] = []
    for index, key in enumerate(attachment_keys):
        if key.startswith("embedded:"):
            attachments.append(
                EmbeddedAttachmentSnapshot(
                    document_key=key,
                    source_kind="EMBEDDED",
                    source_main_document_id="doc-main",
                    source_locator="markdown-chars:0-1",
                    title="文档标题",
                    parsed_content_sha256="sha256:" + "0" * 64,
                )
            )
        else:
            attachments.append(
                UploadedAttachmentSnapshot(
                    document_key=key,
                    source_kind="UPLOADED",
                    attachment_id="att-" + f"{index + 1:03d}",
                    filename="附件.md",
                    parsed_content_sha256="sha256:" + "0" * 64,
                )
            )
    return SourceSnapshot(
        contract_id="c-1",
        revision_id="r-1",
        document_set_hash="sha256:" + "0" * 64,
        main_document=MainDocumentSnapshot(
            document_key="main",
            document_id="doc-main",
            filename="采购合同.md",
            parsed_content_sha256="sha256:" + "0" * 64,
        ),
        attachments=attachments,
    )


def _prepared_documents(docs: dict[str, PreparedDocument], selected: list[str]) -> PreparedDocuments:
    """构造真实 PreparedDocuments：快照固定含 main + 两个附件，正文按 selected 收口。"""
    snapshot = _snapshot_with_attachments(list(_SNAPSHOT_ATTACHMENT_KEYS))
    return PreparedDocuments(
        source_snapshot=snapshot,
        markdown_by_document={key: docs[key].markdown for key in selected},
        preparation_issues=[],
    )


def _att_candidate(
    ref: str,
    kind: str,
    quote: str,
    *,
    document_key: str = "main",
    **fields: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "candidate_ref": ref,
        "candidate_kind": kind,
        "document_key": document_key,
        "quote": quote,
    }
    for key, value in fields.items():
        if value is not None:
            payload[key] = value
    return payload


def _att_env(
    candidates: list[dict[str, Any]],
    gaps: list[dict[str, Any]] | None = None,
) -> PrepareModelEnvelope:
    return PrepareModelEnvelope[list[AttachmentCandidate]].model_validate(
        {"candidates": candidates, "source_gaps": gaps or []}
    )


def _empty_amount_env() -> PrepareModelEnvelope:
    return PrepareModelEnvelope[list[AmountCopyCandidate]].model_validate(
        {"candidates": [], "source_gaps": []}
    )


def _empty_attachment_env() -> PrepareModelEnvelope:
    return PrepareModelEnvelope[list[AttachmentCandidate]].model_validate(
        {"candidates": [], "source_gaps": []}
    )


def _declared_total(ref: str, quote: str, total: str, *, document_key: str = "main"):
    return _att_candidate(
        ref, "DECLARED_TOTAL", quote, document_key=document_key, declared_total=total
    )


def _declared_attachment(
    ref: str, quote: str, title: str, index: str, *, document_key: str = "main"
):
    return _att_candidate(
        ref,
        "DECLARED_ATTACHMENT",
        quote,
        document_key=document_key,
        declared_title=title,
        declared_index=index,
    )


def _logical(
    ref: str, quote: str, title: str, *, document_key: str = "uploaded:att-001"
):
    return _att_candidate(
        ref,
        "LOGICAL_ATTACHMENT",
        quote,
        document_key=document_key,
        logical_title=title,
    )


def _relation(
    ref: str,
    quote: str,
    declaration_ref: str,
    targets: list[str],
    state: str,
    *,
    document_key: str = "main",
):
    """关系候选：声明引用限同一输出内 candidate_ref，关系目标只接受实际 document_key。"""
    return _att_candidate(
        ref,
        "ATTACHMENT_RELATION",
        quote,
        document_key=document_key,
        relation_declaration_ref=declaration_ref,
        relation_target_document_keys=list(targets),
        relation_state=state,
    )


def _domain_from(result):
    """装配入口返回 CommercialFactDomains：唯一入口下直取 attachment_manifest 域。"""
    domain = getattr(result, "attachment_manifest", None)
    if domain is not None and hasattr(domain, "data") and hasattr(domain, "coverage"):
        return domain
    pytest.fail(RED_REASON + "：装配入口未返回 attachment_manifest 域", pytrace=False)


def _assemble_raw(
    envelopes_by_doc: dict[str, PrepareModelEnvelope],
    *,
    doc_keys: list[str] | None = None,
    extraction_ranges: dict[str, list[tuple[int, int]]] | None = None,
    side_effect: Exception | None = None,
    calls: list[tuple[str, dict[str, Any]]] | None = None,
    registry_box: list | None = None,
    prepared_documents: PreparedDocuments | None = None,
):
    """按 patch 约定调用唯一入口, 返回原始 CommercialFactDomains（供模型入参断言复用）。"""
    module = _assembler()
    fn = _extract_fn(module)
    if not hasattr(module, "invoke_typed_prepare_model"):
        pytest.fail(
            RED_REASON + "：" + COMMERCIAL_MODULE + " 未按约定暴露 invoke_typed_prepare_model",
            pytrace=False,
        )
    registry, canonical, docs = _setup()
    if registry_box is not None:
        registry_box[:] = [registry, canonical]
    selected = doc_keys or list(envelopes_by_doc.keys())
    if prepared_documents is None:
        prepared_documents = _prepared_documents(docs, selected)

    def _fake(prompt_name: str, **kwargs: Any):
        if calls is not None:
            calls.append((prompt_name, dict(kwargs)))
        if side_effect is not None:
            raise side_effect
        if prompt_name == "prepare_attachment_document":
            markdown = kwargs.get("markdown")
            for key in selected:
                if docs[key].markdown == markdown:
                    return envelopes_by_doc[key]
            return _empty_attachment_env()
        return _empty_amount_env()

    with patch.object(module, "invoke_typed_prepare_model", side_effect=_fake):
        return fn(prepared_documents, canonical, registry, extraction_ranges)


def _assemble(
    envelopes_by_doc: dict[str, PrepareModelEnvelope],
    *,
    doc_keys: list[str] | None = None,
    extraction_ranges: dict[str, list[tuple[int, int]]] | None = None,
    side_effect: Exception | None = None,
    calls: list[tuple[str, dict[str, Any]]] | None = None,
    registry_box: list | None = None,
    prepared_documents: PreparedDocuments | None = None,
):
    return _domain_from(
        _assemble_raw(
            envelopes_by_doc,
            doc_keys=doc_keys,
            extraction_ranges=extraction_ranges,
            side_effect=side_effect,
            calls=calls,
            registry_box=registry_box,
            prepared_documents=prepared_documents,
        )
    )


# ---------------------------------------------------------------------------
# A. 声明与显式总数
# ---------------------------------------------------------------------------


def test_attachment_manifest_declared_total_and_declarations_from_main():
    """主合同任意位置的附件声明与显式总数：declared_total 保留原文明示值,
    每条声明保留为独立 declaration 且带证据, 声明键唯一。"""
    domain = _assemble(
        {
            "main": _att_env(
                [
                    _declared_total("c1", "附件合计叁份", "叁"),
                    _declared_attachment("c2", "附件一：技术规范书", "技术规范书", "1"),
                    _declared_attachment("c3", "附件二：报价明细", "报价明细", "2"),
                    _declared_attachment("c4", "附件三：履约保证", "履约保证", "3"),
                ]
            )
        }
    )
    data = domain.data
    assert data.declared_total.presence == "PRESENT_VALUE", "显式声明总数必须装配为 PRESENT_VALUE"
    total_observation = data.declared_total.observations[0]
    assert total_observation.normalized_value == 3, "声明总数必须按原文明示值规范化, 不得推算"
    assert total_observation.evidence_ids

    assert len(data.declarations) == 3, "每条附件声明必须保留"
    assert len({d.attachment_declaration_key for d in data.declarations}) == 3
    for declaration in data.declarations:
        assert declaration.evidence_ids
        assert declaration.title.presence == "PRESENT_VALUE"


def test_attachment_manifest_actual_sources_only_from_snapshot_not_headings():
    """实际来源仅来自 source_snapshot.attachments：coverage 恰好覆盖 main 与全部
    上传/内嵌附件; 主合同正文标题或仅有标题的附件不得形成额外实际来源。"""
    domain = _assemble(
        {
            "main": _att_env(
                [
                    _declared_total("c1", "附件合计叁份", "叁"),
                    _declared_attachment("c2", "附件一：技术规范书", "技术规范书", "1"),
                    _declared_attachment("c3", "附件二：报价明细", "报价明细", "2"),
                ]
            ),
            "uploaded:att-001": _att_env([]),
            "embedded:main:001": _att_env(
                [
                    _declared_attachment(
                        "c9",
                        "附件二：报价明细",
                        "报价明细",
                        "2",
                        document_key="embedded:main:001",
                    )
                ]
            ),
        },
        doc_keys=["main", "uploaded:att-001", "embedded:main:001"],
    )
    coverage_keys = [item.document_key for item in domain.coverage]
    assert set(coverage_keys) == set(_ALL_DOCUMENT_KEYS)
    assert len(coverage_keys) == len(_ALL_DOCUMENT_KEYS), (
        "正文标题或仅有标题的附件不得形成额外实际来源"
    )


def test_attachment_manifest_multiple_logical_candidates_do_not_add_physical_attachments():
    """一个物理文件内含 0..N 个顶层逻辑候选：全部保留为带父文档和局部范围的逻辑候选,
    且不得增加物理附件数量, 也不得当作可靠关联。"""
    domain = _assemble(
        {
            "main": _att_env(
                [
                    _declared_attachment("c1", "附件一：技术规范书", "技术规范书", "1")
                ]
            ),
            "uploaded:att-001": _att_env(
                [
                    _logical("l1", "第一部分：总体架构", "总体架构"),
                    _logical("l2", "第二部分：接口清单", "接口清单"),
                ]
            ),
            "embedded:main:001": _att_env([]),
        }
    )
    data = domain.data
    assert len(data.logical_attachment_candidates) == 2, "同一物理文件的多逻辑候选必须全部保留"
    for candidate in data.logical_attachment_candidates:
        assert candidate.parent_document_key == "uploaded:att-001"
        assert candidate.parent_document_key != "main"
        assert candidate.source_locator.startswith("markdown-chars:")
        assert candidate.evidence_ids
    assert len(domain.coverage) == len(_ALL_DOCUMENT_KEYS), "逻辑候选不得增加物理附件数量"


def test_attachment_manifest_links_linked_single_target_uncertain_allows_candidates():
    """关系语义：LINKED 只关联一个实际文档, UNCERTAIN 可保留一个或多个候选;
    每条关系引用现存声明键且带证据。"""
    domain = _assemble(
        {
            "main": _att_env(
                [
                    _declared_attachment("c1", "附件一：技术规范书", "技术规范书", "1"),
                    _declared_attachment("c2", "附件二：报价明细", "报价明细", "2"),
                    _relation("r1", "附件一：技术规范书", "c1", ["uploaded:att-001"], "LINKED"),
                    _relation(
                        "r2",
                        "附件二：报价明细",
                        "c2",
                        ["uploaded:att-001", "embedded:main:001"],
                        "UNCERTAIN",
                    ),
                ]
            ),
            "uploaded:att-001": _att_env(
                [_logical("l1", "第一部分：总体架构", "总体架构")]
            ),
            "embedded:main:001": _att_env(
                [
                    _logical(
                        "l2",
                        "附件二：报价明细",
                        "报价明细",
                        document_key="embedded:main:001",
                    )
                ]
            ),
        }
    )
    data = domain.data
    assert data.links, "存在关系候选时必须生成 link 记录"
    linked = [link for link in data.links if link.relation_state == "LINKED"]
    uncertain = [link for link in data.links if link.relation_state == "UNCERTAIN"]
    assert linked and all(len(link.candidate_document_keys) == 1 for link in linked)
    assert uncertain and all(len(link.candidate_document_keys) >= 1 for link in uncertain)
    assert all(link.evidence_ids for link in data.links)

    declaration_keys = {item.attachment_declaration_key for item in data.declarations}
    for link in data.links:
        assert link.attachment_declaration_key in declaration_keys
        for candidate_document_key in link.candidate_document_keys:
            assert candidate_document_key != "main"
            assert candidate_document_key in _SNAPSHOT_ATTACHMENT_KEYS


def test_attachment_manifest_no_relation_creates_no_link_record():
    """无可关联来源：保留声明但不生成任何 link, 也不得输出附件缺失结论。"""
    domain = _assemble(
        {
            "main": _att_env(
                [
                    _declared_total("c1", "附件合计叁份", "叁"),
                    _declared_attachment("c2", "附件一：技术规范书", "技术规范书", "1"),
                    _declared_attachment("c3", "附件二：报价明细", "报价明细", "2"),
                    _declared_attachment("c4", "附件三：履约保证", "履约保证", "3"),
                ]
            )
        }
    )
    data = domain.data
    assert data.declarations, "声明必须保留"
    assert data.links == [], "没有关系时不得生成伪记录"


def test_attachment_manifest_forbidden_conclusions_absent():
    """禁止结论：数据中不得出现 MISSING/EXTRA/NO_LINK_ESTABLISHED/标题一致性/正式裁决。"""
    domain = _assemble(
        {
            "main": _att_env(
                [
                    _declared_total("c1", "附件合计叁份", "叁"),
                    _declared_attachment("c2", "附件一：技术规范书", "技术规范书", "1"),
                    _relation("r1", "附件一：技术规范书", "c2", ["uploaded:att-001"], "LINKED"),
                ]
            ),
            "uploaded:att-001": _att_env(
                [_logical("l1", "第一部分：总体架构", "总体架构")]
            ),
            "embedded:main:001": _att_env([]),
        }
    )
    blob = json.dumps(domain.data.model_dump(mode="json"), ensure_ascii=False)
    for token in _FORBIDDEN_TOKENS:
        assert token not in blob, "不得输出禁止结论: " + token


# ---------------------------------------------------------------------------
# B. Schema 守卫（验证已存在公共契约, 预期绿灯）
# ---------------------------------------------------------------------------


def test_attachment_manifest_schema_rejects_dangling_and_illegal_relation_targets():
    """公共 Schema 必须拒绝悬空 attachment_declaration_key 引用,
    以及 LINKED 关系关联非唯一实际文档。"""
    declared_total = ObservedField[ObservedValue[int]].model_validate(
        {"presence": "ABSENT", "normalization_state": "NOT_APPLICABLE", "observations": []}
    )
    with pytest.raises(ValidationError):
        AttachmentManifestFacts(
            declared_total=declared_total,
            declarations=[],
            logical_attachment_candidates=[],
            links=[
                AttachmentRelation(
                    attachment_relation_key="attachment-relation:guard",
                    attachment_declaration_key="attachment-declaration:missing",
                    candidate_document_keys=["uploaded:att-001"],
                    relation_state="UNCERTAIN",
                    evidence_ids=["evidence:guard"],
                )
            ],
        )
    with pytest.raises(ValidationError):
        AttachmentRelation(
            attachment_relation_key="attachment-relation:guard-2",
            attachment_declaration_key="attachment-declaration:any",
            candidate_document_keys=["uploaded:att-001", "embedded:main:001"],
            relation_state="LINKED",
            evidence_ids=["evidence:guard"],
        )


# ---------------------------------------------------------------------------
# C. 引用闭合与稳定键
# ---------------------------------------------------------------------------


def _stable_attachment_candidates() -> list[dict[str, Any]]:
    return [
        _declared_total("c1", "附件合计叁份", "叁"),
        _declared_attachment("c2", "附件一：技术规范书", "技术规范书", "1"),
        _declared_attachment("c3", "附件二：报价明细", "报价明细", "2"),
        _relation("r1", "附件一：技术规范书", "c2", ["uploaded:att-001"], "LINKED"),
    ]


def _attachment_key_bundle(domain) -> tuple:
    data = domain.data
    return (
        sorted(item.attachment_declaration_key for item in data.declarations),
        sorted(
            item.logical_attachment_candidate_key
            for item in data.logical_attachment_candidates
        ),
        sorted(link.attachment_relation_key for link in data.links),
    )


def test_attachment_manifest_reference_closure_and_stable_keys():
    """引用与稳定键闭合：link 引用现存声明键且只指向实际文档;
    候选重排或 candidate_ref 重命名不改变稳定键。"""
    forward = _stable_attachment_candidates()
    shuffled = [forward[2], forward[0], forward[3], forward[1]]
    ref_map = {
        candidate["candidate_ref"]: "z" + str(80 + index)
        for index, candidate in enumerate(forward)
    }
    renamed = []
    for candidate in forward:
        renamed_candidate = dict(candidate)
        renamed_candidate["candidate_ref"] = ref_map[candidate["candidate_ref"]]
        declaration_ref = renamed_candidate.get("relation_declaration_ref")
        if declaration_ref is not None:
            renamed_candidate["relation_declaration_ref"] = ref_map[declaration_ref]
        renamed.append(renamed_candidate)

    first = _assemble({"main": _att_env(forward)})
    second = _assemble({"main": _att_env(shuffled)})
    third = _assemble({"main": _att_env(renamed)})

    for domain in (first, second, third):
        data = domain.data
        declaration_keys = {item.attachment_declaration_key for item in data.declarations}
        for link in data.links:
            assert link.attachment_declaration_key in declaration_keys
            for candidate_document_key in link.candidate_document_keys:
                assert candidate_document_key != "main"
                assert candidate_document_key in _SNAPSHOT_ATTACHMENT_KEYS

    assert _attachment_key_bundle(first) == _attachment_key_bundle(second)
    assert _attachment_key_bundle(first) == _attachment_key_bundle(third)


# ---------------------------------------------------------------------------
# D. 关系模型输入与目标约束
# ---------------------------------------------------------------------------


def test_attachment_manifest_relation_model_input_exposes_document_keys():
    """附件关系模型调用：逐次调用都必须各自完整携带 extraction_ranges、当前 document_key
    与排序后的 source_snapshot.attachments 可选目标键集合; 不得把全部调用拼成一个总 blob 断言。"""
    calls: list[tuple[str, dict[str, Any]]] = []
    extraction_ranges = {
        "main": [(0, len(MAIN_MD))],
        "uploaded:att-001": [(0, len(UPLOADED_MD))],
        "embedded:main:001": [(0, len(EMBEDDED_MD))],
    }
    _assemble_raw(
        {
            "main": _att_env(
                [
                    _declared_attachment("c1", "附件一：技术规范书", "技术规范书", "1"),
                    _relation(
                        "r1",
                        "附件一：技术规范书",
                        "c1",
                        ["uploaded:att-001"],
                        "LINKED",
                    ),
                ]
            ),
            "uploaded:att-001": _att_env(
                [_logical("l1", "第一部分：总体架构", "总体架构")]
            ),
            "embedded:main:001": _att_env([]),
        },
        doc_keys=list(_ALL_DOCUMENT_KEYS),
        extraction_ranges=extraction_ranges,
        calls=calls,
    )
    attachment_calls = [
        kwargs
        for prompt_name, kwargs in calls
        if prompt_name == "prepare_attachment_document"
    ]
    assert attachment_calls, "附件装配必须逐文档调用 prepare_attachment_document"
    seen_document_keys = set()
    for kwargs in attachment_calls:
        payload = json.loads(kwargs["extraction_input"])
        assert set(payload) == {
            "extraction_ranges",
            "document_key",
            "available_attachment_document_keys",
        }, "每次附件调用都必须自带 extraction_ranges、当前 document_key 与快照附件键集合"
        current = payload["document_key"]
        seen_document_keys.add(current)
        assert payload["available_attachment_document_keys"] == sorted(
            _SNAPSHOT_ATTACHMENT_KEYS
        ), "每次调用都必须携带排序后的 source_snapshot.attachments 可选目标键"
        assert payload["extraction_ranges"] == [
            {"start": start, "end": end} for start, end in extraction_ranges[current]
        ], "每次调用必须透传当前文档的 extraction_ranges（无范围时为 []）"
    assert seen_document_keys == set(_ALL_DOCUMENT_KEYS), (
        "当前 document_key 必须逐调用出现, 不得把全部调用拼成总 blob"
    )


def test_attachment_manifest_relation_target_outside_snapshot_rejected_even_if_markdown_present():
    """关系目标必须来自 source_snapshot.attachments：即便某个 document_key 已出现在
    markdown_by_document, 只要它不在快照附件集合内, 作为关系目标仍必须 ModelFormatError。"""
    rogue_key = "uploaded:att-rogue"
    prepared = PreparedDocuments(
        source_snapshot=_snapshot_with_attachments(list(_SNAPSHOT_ATTACHMENT_KEYS)),
        markdown_by_document={"main": MAIN_MD, rogue_key: "外部文档正文\n"},
        preparation_issues=[],
    )
    with pytest.raises(ModelFormatError):
        _assemble(
            {
                "main": _att_env(
                    [
                        _declared_attachment(
                            "c1", "附件一：技术规范书", "技术规范书", "1"
                        ),
                        _relation(
                            "r1", "附件一：技术规范书", "c1", [rogue_key], "LINKED"
                        ),
                    ]
                )
            },
            prepared_documents=prepared,
        )


def test_attachment_manifest_relation_target_cannot_equal_candidate_ref_even_if_snapshot_key():
    """relation_target_document_keys 与本次调用任一 candidate_ref 相同时必须 ModelFormatError：
    即便该字符串恰好也是 source_snapshot.attachments 中的真实键, 也不得把候选 ref 当公开文档键。"""
    duplicated = "c1"
    prepared = PreparedDocuments(
        source_snapshot=_snapshot_with_attachments([duplicated]),
        markdown_by_document={"main": MAIN_MD},
        preparation_issues=[],
    )
    with pytest.raises(ModelFormatError):
        _assemble(
            {
                "main": _att_env(
                    [
                        _declared_attachment(
                            "c1", "附件一：技术规范书", "技术规范书", "1"
                        ),
                        _relation(
                            "r1", "附件一：技术规范书", "c1", [duplicated], "LINKED"
                        ),
                    ]
                )
            },
            prepared_documents=prepared,
        )


def test_attachment_manifest_relation_target_rejects_non_snapshot_and_candidate_ref():
    """关系目标必须来自实际可选 document_key：快照外 rogue 目标与以 candidate_ref
    充当目标都必须 ModelFormatError, 不得把候选 ref 当公开 document_key。"""
    declaration = _declared_attachment("c1", "附件一：技术规范书", "技术规范书", "1")
    with pytest.raises(ModelFormatError):
        _assemble(
            {
                "main": _att_env(
                    [
                        declaration,
                        _relation(
                            "r1",
                            "附件一：技术规范书",
                            "c1",
                            ["rogue:not-in-snapshot"],
                            "LINKED",
                        ),
                    ]
                )
            }
        )
    with pytest.raises(ModelFormatError):
        _assemble(
            {
                "main": _att_env(
                    [
                        declaration,
                        _relation("r1", "附件一：技术规范书", "c1", ["c1"], "LINKED"),
                    ]
                )
            }
        )
