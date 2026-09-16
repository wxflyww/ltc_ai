from __future__ import annotations

"""Task 7 Step 1-4: copy_terms 商业事实闭合矩阵。

闭合矩阵（正式要求 -> 候选/Schema -> 装配对象与引用 -> 证据/coverage -> 稳定键 -> 测试）：

| 正式要求 (spec) | 候选 (AmountCopyCandidate) | 装配对象/引用 | 证据 / 逐文档 coverage | 稳定键 | 测试 |
|---|---|---|---|---|---|
| 原文明示整体总份数与索引 (spec 211) | COPY_TOTAL | CopyStatement + overall_total_statement_key 指向现存 statement | 陈述 evidence_ids>=1 | statement_key 由坐标 | test_copy_terms_explicit_overall_total_statement_key |
| 各方分配语义 | COPY_ALLOCATION | CopyAllocation.statement_key 指向现存陈述, semantics EACH/COLLECTIVE/UNCERTAIN | candidate_party_keys 限 canonical | allocation_key 由坐标 | test_copy_terms_allocation_semantics_each_collective_uncertain |
| 冲突陈述保留为不确定 (spec 95-99) | 两条异值 COPY_TOTAL | 两条陈述都保留, overall 索引不得静默择一 | 全部候选与证据保留 | 键互异 | test_copy_terms_conflicting_statements_stay_uncertain |
| 无整体总数不得推算 (spec 213-217) | 只有 allocation | overall_total_statement_key 省略 | 不得由各方份数推算 | - | test_copy_terms_without_overall_total_not_derived_from_party_counts |
| 附件份数排除 (spec 219-221) | 附件文档内 COPY_TOTAL | 本域只含 main | coverage 仅 main | - | test_copy_terms_attachment_copy_counts_excluded |
| 悬空 overall_total_statement_key | - | CopyTermsFacts Schema 拒绝 | - | - | test_copy_terms_schema_rejects_dangling_overall_total_statement_key |
| 引用与稳定键闭合 (spec 237-243) | 乱序 + 改名 | 引用闭合, 键不变 | - | 键不含 candidate_ref | test_copy_terms_reference_closure_and_stable_keys |
| 共用 envelope 的 source_gap 不跨域误判 | COPY_TOTAL source_gap | copy coverage 降级, amount_payment 不失败 | gap 引文定位 | - | test_copy_terms_source_gap_copy_total_does_not_fail_amount_payment |

本文件为可执行验收矩阵：正式要求、候选与 Schema、装配对象与引用、证据与逐文档 coverage、
稳定键到测试逐行对应；Schema 守卫验证已存在的公共契约, 其余用例断言商业装配行为是否闭合,
装配能力缺失或与正式条款不一致时相应用例失败, 直接指向缺口, 不经由 fixture、导入或环境错误伪装。

入口契约（DEC-LTC-20260910-003）：
1. 装配入口模块 app/capabilities/contract_review/two_stage/extract_commercial.py，
   唯一入口 extract_amount_copy_manifest(documents: PreparedDocuments,
   canonical_parties, evidence, extraction_ranges=None) -> CommercialFactDomains。
2. 结果仅承载 amount_payment、copy_terms、attachment_manifest 三个 FactDomain；
   _domain_from 直取 copy_terms 域。
3. documents 为 PreparedDocuments（source_snapshot + markdown_by_document）；
   模型调用经模块 invoke_typed_prepare_model（沿用 Task 5/6 导入约定，便于定点 patch）。
4. COPY_ALLOCATION 候选配套生成自身 CopyStatement 并以 copy_count 承载份数，
   overall_total_statement_key 仅由 COPY_TOTAL 候选建立；稳定键只用已定位证据坐标。
"""

import importlib
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
    CanonicalParty,
    CopyTermsFacts,
    EmbeddedAttachmentSnapshot,
    MainDocumentSnapshot,
    ObservedField,
    ObservedValue,
    SourceSnapshot,
    UploadedAttachmentSnapshot,
)

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
    "本合同一式叁份\n"
    "本合同一式肆份\n"
    "甲乙双方各执贰份\n"
    "双方共同留存额外一份备查\n"
    "丙方留档一份\n"
)

UPLOADED_MD = (
    "附件份数声明\n"
    "附件一式伍份\n"
)

EMBEDDED_MD = (
    "附件二：份数说明\n"
    "本附件仅有标题, 无正文内容。\n"
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


def _prepared_documents(docs: dict[str, PreparedDocument], selected: list[str]) -> PreparedDocuments:
    """构造真实 PreparedDocuments：快照固定含 main + 两个附件，正文按 selected 收口。"""
    snapshot = SourceSnapshot(
        contract_id="c-1",
        revision_id="r-1",
        document_set_hash="sha256:" + "0" * 64,
        main_document=MainDocumentSnapshot(
            document_key="main",
            document_id="doc-main",
            filename="采购合同.md",
            parsed_content_sha256="sha256:" + "0" * 64,
        ),
        attachments=[
            UploadedAttachmentSnapshot(
                document_key="uploaded:att-001",
                source_kind="UPLOADED",
                attachment_id="att-001",
                filename="附件.md",
                parsed_content_sha256="sha256:" + "0" * 64,
            ),
            EmbeddedAttachmentSnapshot(
                document_key="embedded:main:001",
                source_kind="EMBEDDED",
                source_main_document_id="doc-main",
                source_locator="markdown-chars:0-1",
                title="文档标题",
                parsed_content_sha256="sha256:" + "0" * 64,
            ),
        ],
    )
    return PreparedDocuments(
        source_snapshot=snapshot,
        markdown_by_document={key: docs[key].markdown for key in selected},
        preparation_issues=[],
    )


def _copy_candidate(
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


def _copy_env(
    candidates: list[dict[str, Any]],
    gaps: list[dict[str, Any]] | None = None,
) -> PrepareModelEnvelope:
    return PrepareModelEnvelope[list[AmountCopyCandidate]].model_validate(
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


def _domain_from(result):
    """装配入口返回 CommercialFactDomains：唯一入口下直取 copy_terms 域。"""
    domain = getattr(result, "copy_terms", None)
    if domain is not None and hasattr(domain, "data") and hasattr(domain, "coverage"):
        return domain
    pytest.fail(RED_REASON + "：装配入口未返回 copy_terms 域", pytrace=False)


def _assemble_raw(
    envelopes_by_doc: dict[str, PrepareModelEnvelope],
    *,
    doc_keys: list[str] | None = None,
    extraction_ranges: dict[str, list[tuple[int, int]]] | None = None,
    side_effect: Exception | None = None,
    registry_box: list | None = None,
):
    """按 patch 约定调用唯一入口, 返回原始 CommercialFactDomains（供跨域断言复用）。"""
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
    prepared_documents = _prepared_documents(docs, selected)

    def _fake(prompt_name: str, **kwargs: Any):
        if side_effect is not None:
            raise side_effect
        if prompt_name == "prepare_amount_copy_main":
            markdown = kwargs.get("markdown")
            for key in selected:
                if docs[key].markdown == markdown:
                    return envelopes_by_doc[key]
            return _empty_amount_env()
        return _empty_attachment_env()

    with patch.object(module, "invoke_typed_prepare_model", side_effect=_fake):
        return fn(prepared_documents, canonical, registry, extraction_ranges)


def _assemble(
    envelopes_by_doc: dict[str, PrepareModelEnvelope],
    *,
    doc_keys: list[str] | None = None,
    extraction_ranges: dict[str, list[tuple[int, int]]] | None = None,
    side_effect: Exception | None = None,
    registry_box: list | None = None,
):
    return _domain_from(
        _assemble_raw(
            envelopes_by_doc,
            doc_keys=doc_keys,
            extraction_ranges=extraction_ranges,
            side_effect=side_effect,
            registry_box=registry_box,
        )
    )


def _overall_total_candidate(ref: str, quote: str, total: str) -> dict[str, Any]:
    return _copy_candidate(ref, "COPY_TOTAL", quote, copies_total=total)


def _allocation_candidate(
    ref: str, quote: str, role: str, count: str
) -> dict[str, Any]:
    return _copy_candidate(
        ref,
        "COPY_ALLOCATION",
        quote,
        copy_role=role,
        copy_count=count,
    )


# ---------------------------------------------------------------------------
# A. 原文明示整体总数
# ---------------------------------------------------------------------------


def test_copy_terms_explicit_overall_total_statement_key():
    """原文明示整体总数：陈述保留, overall_total_statement_key 指向现存陈述,
    计数为原文明示值（不得由 allocation 推算）。"""
    domain = _assemble(
        {
            "main": _copy_env(
                [_overall_total_candidate("c1", "本合同一式叁份", "叁")]
            )
        }
    )
    data = domain.data
    assert data.statements, "原文明示整体总份数必须装配为 statement"
    keys = {s.statement_key for s in data.statements}
    assert data.overall_total_statement_key in keys
    picked = next(
        s for s in data.statements if s.statement_key == data.overall_total_statement_key
    )
    assert picked.count.presence == "PRESENT_VALUE"
    assert picked.count.observations[0].normalized_value == 3
    assert picked.evidence_ids
    assert all(s.document_key == "main" for s in data.statements)


def test_copy_terms_allocation_semantics_each_collective_uncertain():
    """各方分配：EACH / COLLECTIVE / UNCERTAIN 三种语义都要保留,
    allocation 引用现存 statement, candidate_party_keys 限于 canonical 主体。"""
    domain = _assemble(
        {
            "main": _copy_env(
                [
                    _overall_total_candidate("c1", "本合同一式叁份", "叁"),
                    _allocation_candidate("c2", "甲乙双方各执贰份", "甲乙双方", "2"),
                    _allocation_candidate("c3", "双方共同留存额外一份备查", "双方", "1"),
                    _allocation_candidate("c4", "丙方留档一份", "丙方", "1"),
                ]
            )
        }
    )
    data = domain.data
    assert data.allocations
    semantics = {a.allocation_semantics for a in data.allocations}
    assert semantics == {"EACH", "COLLECTIVE", "UNCERTAIN"}
    statement_keys = {s.statement_key for s in data.statements}
    assert all(a.statement_key in statement_keys for a in data.allocations)
    assert len({a.allocation_key for a in data.allocations}) == len(data.allocations)

    party_keys = {
        stable_key("party", {"declared_name": "甲乙科技有限公司"}),
        stable_key("party", {"declared_name": "丙丁工程有限公司"}),
    }
    for allocation in data.allocations:
        assert set(allocation.candidate_party_keys) <= party_keys
        assert all(a.evidence_ids for a in data.allocations)


def test_copy_terms_conflicting_statements_stay_uncertain():
    """冲突陈述保留为不确定：整体总份数出现两个异值时, 两条陈述都保留,
    overall 索引不得静默择一, 不得丢弃任一候选与证据。"""
    domain = _assemble(
        {
            "main": _copy_env(
                [
                    _overall_total_candidate("c1", "本合同一式叁份", "叁"),
                    _overall_total_candidate("c5", "本合同一式肆份", "肆"),
                ]
            )
        }
    )
    data = domain.data
    assert len(data.statements) == 2, "冲突陈述必须全部保留, 不得静默择一"
    assert len({s.statement_key for s in data.statements}) == 2
    assert all(s.evidence_ids for s in data.statements)

    keys = {s.statement_key for s in data.statements}
    if data.overall_total_statement_key is not None:
        assert data.overall_total_statement_key in keys
        picked = next(
            s
            for s in data.statements
            if s.statement_key == data.overall_total_statement_key
        )
        assert picked.count.presence == "UNCERTAIN", (
            "冲突整体总数不得被静默确定为 PRESENT_VALUE"
        )


def test_copy_terms_without_overall_total_not_derived_from_party_counts():
    """无整体总数：只写明各方份数时 overall_total_statement_key 必须省略,
    不得由各方份数求和推算。"""
    domain = _assemble(
        {
            "main": _copy_env(
                [
                    _allocation_candidate("c2", "甲乙双方各执贰份", "甲乙双方", "2"),
                    _allocation_candidate("c3", "双方共同留存额外一份备查", "双方", "1"),
                ]
            )
        }
    )
    data = domain.data
    assert data.overall_total_statement_key is None, "不得由各方份数推算整体总份数"
    counts = {
        obs.normalized_value
        for statement in data.statements
        for obs in statement.count.observations
        if obs.normalized_value is not None
    }
    assert counts <= {2, 1}, "不得写入由求和/推算得到的整体总份数"
    assert data.allocations, "各方份数分配事实必须保留"


def test_copy_terms_attachment_copy_counts_excluded():
    """附件份数排除：附件自身份数声明不得补足或冲突主合同总份数,
    copy_terms 只覆盖 main。"""
    domain = _assemble(
        {
            "main": _copy_env(
                [_overall_total_candidate("c1", "本合同一式叁份", "叁")]
            ),
            "uploaded:att-001": _copy_env(
                [
                    _overall_total_candidate(
                        "c6", "附件一式伍份", "伍"
                    )
                ]
            ),
        },
        doc_keys=["main", "uploaded:att-001"],
    )
    data = domain.data
    assert [c.document_key for c in domain.coverage] == ["main"]
    counts = {
        obs.normalized_value
        for statement in data.statements
        for obs in statement.count.observations
        if obs.normalized_value is not None
    }
    assert 5 not in counts, "附件份数不得进入主合同份数事实"
    assert data.overall_total_statement_key is not None


# ---------------------------------------------------------------------------
# B. Schema 守卫（验证已存在公共契约, 预期绿灯）
# ---------------------------------------------------------------------------


def test_copy_terms_schema_rejects_dangling_overall_total_statement_key():
    """公共 Schema 必须拒绝悬空 overall_total_statement_key（引用类型正确的现存目标）。"""
    with pytest.raises(ValidationError):
        CopyTermsFacts(
            statements=[],
            overall_total_statement_key="statement:does-not-exist",
            allocations=[],
        )


# ---------------------------------------------------------------------------
# C. 引用闭合与稳定键
# ---------------------------------------------------------------------------


def _stable_candidates() -> list[dict[str, Any]]:
    return [
        _overall_total_candidate("c1", "本合同一式叁份", "叁"),
        _allocation_candidate("c2", "甲乙双方各执贰份", "甲乙双方", "2"),
        _allocation_candidate("c3", "双方共同留存额外一份备查", "双方", "1"),
    ]


def test_copy_terms_reference_closure_and_stable_keys():
    """引用闭合与稳定键：分配引用现存陈述, overall 索引闭合, 候选重排/改名不改键。"""
    forward = _stable_candidates()
    shuffled = [forward[2], forward[0], forward[1]]
    renamed = [
        dict(candidate, candidate_ref="z" + str(70 + index))
        for index, candidate in enumerate(forward)
    ]

    first = _assemble({"main": _copy_env(forward)})
    second = _assemble({"main": _copy_env(shuffled)})
    third = _assemble({"main": _copy_env(renamed)})

    for domain in (first, second, third):
        data = domain.data
        statement_keys = {s.statement_key for s in data.statements}
        assert data.overall_total_statement_key is None or (
            data.overall_total_statement_key in statement_keys
        )
        for allocation in data.allocations:
            assert allocation.statement_key in statement_keys

    assert sorted(s.statement_key for s in first.data.statements) == sorted(
        s.statement_key for s in second.data.statements
    )
    assert sorted(s.statement_key for s in first.data.statements) == sorted(
        s.statement_key for s in third.data.statements
    )
    assert sorted(a.allocation_key for a in first.data.allocations) == sorted(
        a.allocation_key for a in third.data.allocations
    )


# ---------------------------------------------------------------------------
# D. 跨域 source_gap 隔离
# ---------------------------------------------------------------------------


def test_copy_terms_source_gap_copy_total_does_not_fail_amount_payment():
    """共用 main envelope 的合法 source_gap 不得跨域误判：
    COPY_TOTAL 缺口只降级 copy_terms 对应 coverage, amount_payment 仍为 COMPLETE 而非技术失败。"""
    gaps = [
        {
            "affected_fact_kinds": ["COPY_TOTAL"],
            "message": "整体总份数声明疑似被涂改",
            "quote": "本合同一式叁份",
        }
    ]
    result = _assemble_raw(
        {
            "main": _copy_env(
                [_overall_total_candidate("c1", "本合同一式叁份", "叁")],
                gaps=gaps,
            )
        }
    )
    copy_coverage = next(
        item for item in result.copy_terms.coverage if item.document_key == "main"
    )
    assert copy_coverage.state == "PARTIAL", "COPY_TOTAL 缺口只降级 copy_terms 对应 coverage"
    assert copy_coverage.affected_fact_kinds == ["COPY_TOTAL"]
    assert result.amount_payment.state == "COMPLETE", "COPY_TOTAL 缺口不得令 amount_payment 技术失败"
    assert result.amount_payment.issues == []
