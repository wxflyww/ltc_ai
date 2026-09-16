from __future__ import annotations

"""Task 7: amount_payment / copy_terms / attachment_manifest 商业事实装配。

唯一内部入口: extract_amount_copy_manifest(documents, canonical_parties, evidence,
extraction_ranges) -> CommercialFactDomains。结果只承载三个 FactDomain, 不构造公开 API 包装。
模型调用经本模块 invoke_typed_prepare_model (便于定点 patch)。

护栏:
- 仅主合同调用 prepare_amount_copy_main; 附件清单候选逐文档调用
  prepare_attachment_document 并透传 extraction_ranges;
- 实际物理附件只来自 source_snapshot.attachments;
- 稳定键只用规范化业务坐标 (document_key + 已定位证据 start-end + 域 kind),
  不使用 candidate_ref、数组顺序或模型自由文案;
- 不计算阶段金额、比例合计、差额、舍入或尾差, 不自动补写大写金额,
  不由各方份数或附件数量推算整体总份数;
- 附件金额与份数不回填主合同; 附件关系保持中性 LINKED|UNCERTAIN,
  不输出缺失、多余或标题一致性裁决;
- 候选引文无法定位或引用不闭合整体失败。
"""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.capabilities.contract_review.two_stage.documents import PreparedDocuments
from app.capabilities.contract_review.two_stage.evidence import (
    EvidenceLocationError,
    EvidenceRegistry,
    format_markdown_locator,
    parse_markdown_locator,
)
from app.capabilities.contract_review.two_stage.keys import stable_key
from app.capabilities.contract_review.two_stage.prepare_model import (
    PrepareModelEnvelope,
    invoke_typed_prepare_model,
)
from app.capabilities.contract_review.two_stage.schemas import (
    AmountFact,
    AmountPaymentFacts,
    AmountRelation,
    AttachmentDeclaration,
    AttachmentManifestFacts,
    AttachmentRelation,
    CanonicalParty,
    CopyAllocation,
    CopyStatement,
    CopyTermsFacts,
    DocumentCoverage,
    FactDomain,
    FactIssue,
    LogicalAttachmentCandidate,
    ObservedField,
    ObservedValue,
    PaymentMethodObservation,
    PaymentStage,
)
from app.core.errors import ModelFormatError

MarkdownRange = tuple[int, int]

_AMOUNT_FACT_KINDS = {
    "CURRENCY",
    "PAYMENT_METHOD",
    "TOTAL_AMOUNT",
    "AMOUNT_PAIR",
    "PAYMENT_STAGE",
}
_COPY_FACT_KINDS = {"COPY_TOTAL", "COPY_ALLOCATION"}
_ATTACHMENT_FACT_KINDS = {
    "PARTY_MENTION",
    "DECLARED_ATTACHMENT",
    "LOGICAL_ATTACHMENT",
    "ATTACHMENT_RELATION",
    "DECLARED_TOTAL",
}

_DECIMAL_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_CN_NUMERALS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "壹": 1,
    "二": 2,
    "贰": 2,
    "三": 3,
    "叁": 3,
    "四": 4,
    "肆": 4,
    "五": 5,
    "伍": 5,
    "六": 6,
    "陆": 6,
    "七": 7,
    "柒": 7,
    "八": 8,
    "捌": 8,
    "九": 9,
    "玖": 9,
    "十": 10,
    "拾": 10,
}


@dataclass
class CommercialFactDomains:
    """Task 7 商业三域结果容器: 只承载三个 FactDomain, 不构造公开 API 包装。"""

    amount_payment: FactDomain[AmountPaymentFacts]
    copy_terms: FactDomain[CopyTermsFacts]
    attachment_manifest: FactDomain[AttachmentManifestFacts]


def _extraction_input(ranges: Sequence[MarkdownRange] | None) -> str:
    if ranges is None:
        return "{}"
    return json.dumps(
        {
            "extraction_ranges": [
                {"start": start, "end": end} for start, end in ranges
            ]
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _invoke_amount_copy_main(
    markdown: str, ranges: Sequence[MarkdownRange] | None
) -> PrepareModelEnvelope:
    return invoke_typed_prepare_model(
        "prepare_amount_copy_main",
        markdown=markdown,
        scope_label="main",
        extraction_input=_extraction_input(ranges),
    )


def _attachment_extraction_input(
    ranges: Sequence[MarkdownRange] | None,
    document_key: str,
    available_keys: Sequence[str],
) -> str:
    """附件文档模型上下文: 始终给出提取范围、当前文档键与可选目标文档键集合。"""
    return json.dumps(
        {
            "extraction_ranges": [
                {"start": start, "end": end} for start, end in (ranges or [])
            ],
            "document_key": document_key,
            "available_attachment_document_keys": list(available_keys),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _invoke_attachment_document(
    markdown: str,
    document_key: str,
    ranges: Sequence[MarkdownRange] | None,
    available_keys: Sequence[str],
) -> PrepareModelEnvelope:
    return invoke_typed_prepare_model(
        "prepare_attachment_document",
        markdown=markdown,
        scope_label="main" if document_key == "main" else "attachment",
        extraction_input=_attachment_extraction_input(
            ranges, document_key, available_keys
        ),
    )


def _require_document(candidate_document_key: str, document_key: str) -> None:
    if candidate_document_key != document_key:
        raise ModelFormatError(
            "候选 document_key "
            f"{candidate_document_key} 与当前文档 {document_key} 不一致"
        )


def _locate(
    evidence: EvidenceRegistry,
    document_key: str,
    quote: str,
    allowed_ranges: Sequence[MarkdownRange] | None,
) -> tuple[str, MarkdownRange]:
    """定位候选引文; 普通候选与 source_gap 引文无法唯一定位即整体失败。"""
    try:
        if allowed_ranges is not None:
            item = evidence.register(
                document_key=document_key,
                quote=quote,
                allowed_ranges=list(allowed_ranges),
            )
        else:
            item = evidence.register(document_key=document_key, quote=quote)
    except EvidenceLocationError as exc:
        raise ModelFormatError(
            f"候选引文在文档 {document_key} 中无法唯一定位，引用不闭合"
        ) from exc
    start, end = parse_markdown_locator(item.source_locator)
    return item.evidence_id, (start, end)


def _locate_gap(
    evidence: EvidenceRegistry,
    document_key: str,
    quote: str,
    allowed_ranges: Sequence[MarkdownRange] | None,
) -> MarkdownRange | None:
    try:
        _, span = _locate(evidence, document_key, quote, allowed_ranges)
    except ModelFormatError:
        return None
    return span


def _issue_key(
    code: str,
    basis: str,
    document_keys: Sequence[str],
    affected_fact_kinds: Sequence[str],
) -> str:
    return stable_key(
        "fact_issue",
        {
            "code": code,
            "basis": basis,
            "document_keys": list(document_keys),
            "affected_fact_kinds": list(affected_fact_kinds),
        },
    )


def _collect_source_gaps(
    gaps: Sequence[object],
    document_key: str,
    evidence: EvidenceRegistry,
    allowed_ranges: Sequence[MarkdownRange] | None,
    known_kinds: set[str],
    domain_kinds: set[str] | None = None,
) -> list[FactIssue]:
    """仅显式、可定位的 source_gap 参与本域 coverage。

    known_kinds 为整体合法类别(主合同为金额∪份数); 给出 domain_kinds 时只保留与该域
    类别相交的缺口, 使共用 envelope 的缺口不会误伤另一域。无可信定位引文的稳定键只用
    固定错误码、document_key 与排序后的 affected_fact_kinds, 不含模型自由文案。
    """
    fact_issues: list[FactIssue] = []
    for gap in gaps:
        gap_document_key = getattr(gap, "document_key", None)
        if gap_document_key is not None and gap_document_key != document_key:
            raise ModelFormatError(
                f"source_gap 引用其它文档 {gap_document_key} != {document_key}，"
                "来源缺口必须属于当前文档"
            )
        raw_affected = list(gap.affected_fact_kinds)
        unknown = set(raw_affected) - known_kinds
        if unknown:
            raise ModelFormatError(
                "source_gap 引用未知事实类别: " + ", ".join(sorted(unknown))
            )
        affected = raw_affected
        if domain_kinds is not None:
            affected = [kind for kind in raw_affected if kind in domain_kinds]
            if not affected:
                continue
        affected = sorted(affected)
        related = [document_key]
        quote = gap.quote
        span = (
            _locate_gap(evidence, document_key, quote, allowed_ranges)
            if quote is not None
            else None
        )
        if quote is not None and span is None:
            fact_issues.append(
                FactIssue(
                    fact_issue_key=_issue_key(
                        "EVIDENCE_UNLOCATABLE",
                        f"gap:{document_key}",
                        related,
                        affected,
                    ),
                    code="EVIDENCE_UNLOCATABLE",
                    message="候选引文在文档中无法唯一定位",
                    related_document_keys=related,
                    affected_fact_kinds=affected,
                    evidence_ids=[],
                )
            )
            continue
        evidence_ids: list[str] = []
        if span is not None and quote is not None:
            evidence_id, (start, end) = _locate(
                evidence, document_key, quote, allowed_ranges
            )
            evidence_ids = [evidence_id]
            basis = f"gap:{document_key}:{start}:{end}"
        else:
            basis = f"gap:{document_key}"
        fact_issues.append(
            FactIssue(
                fact_issue_key=_issue_key("SOURCE_UNREADABLE", basis, related, affected),
                code="SOURCE_UNREADABLE",
                message=(
                    gap.message
                    if span is not None
                    else "已声明的来源缺口未提供可定位引文"
                ),
                related_document_keys=related,
                affected_fact_kinds=affected,
                evidence_ids=evidence_ids,
            )
        )
    return fact_issues


def _absent_observed() -> ObservedField:
    return ObservedField(
        presence="ABSENT",
        normalization_state="NOT_APPLICABLE",
        observations=[],
    )


def _observed_text(value: str | None, evidence_id: str) -> ObservedField:
    text = (value or "").strip()
    if not text:
        return _absent_observed()
    return ObservedField(
        presence="PRESENT_VALUE",
        normalization_state="VALID",
        observations=[
            ObservedValue(raw_text=text, normalized_value=text, evidence_ids=[evidence_id])
        ],
    )


def _observed_decimal(value: str | None, evidence_id: str) -> ObservedField:
    text = (value or "").strip()
    if not text:
        return _absent_observed()
    if not _DECIMAL_RE.fullmatch(text):
        return ObservedField(
            presence="UNCERTAIN",
            normalization_state="UNCERTAIN",
            observations=[
                ObservedValue(raw_text=text, normalized_value=None, evidence_ids=[evidence_id])
            ],
        )
    return ObservedField(
        presence="PRESENT_VALUE",
        normalization_state="VALID",
        observations=[
            ObservedValue(raw_text=text, normalized_value=text, evidence_ids=[evidence_id])
        ],
    )


def _parse_count(value: str | None) -> int | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if re.fullmatch(r"\d+", text):
        return int(text)
    if len(text) == 1:
        return _CN_NUMERALS.get(text)
    total = 0
    found = False
    for char in text:
        digit = _CN_NUMERALS.get(char)
        if digit is None:
            continue
        total = total * 10 + digit
        found = True
    return total if found else None


def _observed_int(value: str | None, evidence_id: str) -> ObservedField:
    text = (value or "").strip()
    parsed = _parse_count(value)
    if parsed is None:
        return _absent_observed()
    return ObservedField(
        presence="PRESENT_VALUE",
        normalization_state="VALID",
        observations=[
            ObservedValue(raw_text=text, normalized_value=parsed, evidence_ids=[evidence_id])
        ],
    )


def _observed_tax_treatment(quote: str, explicit: str | None, evidence_id: str) -> ObservedField:
    text = (explicit or "").strip()
    if text:
        return _observed_text(text, evidence_id)
    if "不含税" in quote:
        return _observed_text("不含税", evidence_id)
    if "含税" in quote:
        return _observed_text("含税", evidence_id)
    return _absent_observed()


def _party_keys_in_quote(
    quote: str, canonical_parties: Sequence[CanonicalParty]
) -> list[str]:
    keys: list[str] = []
    for party in canonical_parties:
        names: set[str] = set()
        for observation in party.declared_name.observations:
            for value in (observation.raw_text, observation.normalized_value):
                name = (value or "").strip()
                if name:
                    names.add(name)
        if any(name in quote for name in names) and party.party_key not in keys:
            keys.append(party.party_key)
    return sorted(keys)


def _derive_allocation_semantics(quote: str) -> str:
    if "各执" in quote or "各持" in quote or "分别" in quote:
        return "EACH"
    if "共同" in quote:
        return "COLLECTIVE"
    return "UNCERTAIN"


def _build_domain(
    data: object,
    issues: Sequence[FactIssue],
    document_keys: Sequence[str],
    kind_universe: set[str],
) -> FactDomain:
    """coverage 只由显式、可定位来源缺口驱动; 并集覆盖全部适用类别才 UNAVAILABLE。"""
    unique: dict[str, FactIssue] = {}
    for issue in issues:
        unique[issue.fact_issue_key] = issue
    all_issues = [unique[key] for key in sorted(unique)]

    coverage: list[DocumentCoverage] = []
    for document_key in document_keys:
        doc_issues = [
            issue for issue in all_issues if document_key in issue.related_document_keys
        ]
        if not doc_issues:
            coverage.append(
                DocumentCoverage(
                    document_key=document_key,
                    state="COMPLETE",
                    affected_fact_kinds=[],
                    fact_issue_keys=[],
                )
            )
            continue
        affected = sorted(
            kind_universe.intersection(
                {kind for issue in doc_issues for kind in issue.affected_fact_kinds}
            )
        )
        locatable_kinds: set[str] = set()
        for issue in doc_issues:
            if issue.code != "EVIDENCE_UNLOCATABLE":
                locatable_kinds |= set(issue.affected_fact_kinds)
        state = "UNAVAILABLE" if kind_universe <= locatable_kinds else "PARTIAL"
        coverage.append(
            DocumentCoverage(
                document_key=document_key,
                state=state,
                affected_fact_kinds=affected,
                fact_issue_keys=sorted({issue.fact_issue_key for issue in doc_issues}),
            )
        )

    coverage.sort(key=lambda item: item.document_key)
    states = {item.state for item in coverage}
    if states == {"COMPLETE"}:
        domain_state = "COMPLETE"
    elif states == {"UNAVAILABLE"}:
        domain_state = "UNAVAILABLE"
    else:
        domain_state = "PARTIAL"
    return FactDomain(
        state=domain_state,
        coverage=coverage,
        data=data,
        issues=all_issues if domain_state != "COMPLETE" else [],
    )


def _locate_candidates(
    envelope: PrepareModelEnvelope,
    document_key: str,
    evidence: EvidenceRegistry,
    allowed_ranges: Sequence[MarkdownRange] | None,
) -> list[tuple[object, str, MarkdownRange]]:
    located: list[tuple[object, str, MarkdownRange]] = []
    for candidate in envelope.candidates:
        _require_document(candidate.document_key, document_key)
        evidence_id, span = _locate(evidence, document_key, candidate.quote, allowed_ranges)
        located.append((candidate, evidence_id, span))
    return located


def _assemble_amount(
    envelope: PrepareModelEnvelope,
    evidence: EvidenceRegistry,
    allowed_ranges: Sequence[MarkdownRange] | None,
) -> FactDomain[AmountPaymentFacts]:
    located = _locate_candidates(envelope, "main", evidence, allowed_ranges)

    amounts: list[AmountFact] = []
    stages: list[PaymentStage] = []
    methods: list[PaymentMethodObservation] = []
    relations: list[AmountRelation] = []
    overall_hits: list[tuple[str, str]] = []

    def _amount_key(span: MarkdownRange) -> str:
        return stable_key(
            "amount",
            {"document_key": "main", "start": span[0], "end": span[1]},
        )

    def _stage_amount_key(span: MarkdownRange) -> str:
        return stable_key(
            "amount",
            {
                "document_key": "main",
                "start": span[0],
                "end": span[1],
                "role": "PAYMENT_STAGE",
            },
        )

    def _stage_method_key(span: MarkdownRange) -> str:
        return stable_key(
            "payment_method",
            {
                "document_key": "main",
                "start": span[0],
                "end": span[1],
                "role": "PAYMENT_STAGE",
            },
        )

    for candidate, evidence_id, span in located:
        kind = candidate.candidate_kind
        if kind in ("TOTAL_AMOUNT", "AMOUNT_PAIR"):
            if kind == "TOTAL_AMOUNT":
                numeric_raw = candidate.total_amount_numeric
                uppercase_raw = candidate.total_amount_uppercase
            else:
                numeric_raw = candidate.amount_numeric
                uppercase_raw = candidate.amount_uppercase
            label = candidate.amount_label or candidate.amount_role
            amount_key = _amount_key(span)
            amounts.append(
                AmountFact(
                    amount_key=amount_key,
                    document_key="main",
                    semantic_role=_observed_text(label, evidence_id),
                    numeric_amount=_observed_decimal(numeric_raw, evidence_id),
                    uppercase_amount=_observed_text(uppercase_raw, evidence_id),
                    currency=_observed_text(candidate.currency, evidence_id),
                    tax_treatment=_observed_tax_treatment(
                        candidate.quote, candidate.tax_treatment, evidence_id
                    ),
                    evidence_ids=[evidence_id],
                )
            )
            if (
                "合同总价" in candidate.quote
                or (candidate.relation_kind or "").strip() == "CONTRACT_OVERALL"
            ):
                overall_hits.append((amount_key, evidence_id))
            continue
        if kind == "PAYMENT_STAGE":
            stage_key = stable_key(
                "payment_stage",
                {"document_key": "main", "start": span[0], "end": span[1]},
            )
            stage_amount_keys: list[str] = []
            if candidate.stage_amount_numeric or candidate.stage_amount_uppercase:
                amount_key = _stage_amount_key(span)
                amounts.append(
                    AmountFact(
                        amount_key=amount_key,
                        document_key="main",
                        semantic_role=_observed_text(
                            candidate.amount_role or candidate.stage_name, evidence_id
                        ),
                        numeric_amount=_observed_decimal(
                            candidate.stage_amount_numeric, evidence_id
                        ),
                        uppercase_amount=_observed_text(
                            candidate.stage_amount_uppercase, evidence_id
                        ),
                        currency=_observed_text(candidate.currency, evidence_id),
                        tax_treatment=_observed_tax_treatment(
                            candidate.quote, candidate.tax_treatment, evidence_id
                        ),
                        evidence_ids=[evidence_id],
                    )
                )
                stage_amount_keys.append(amount_key)
                relations.append(
                    AmountRelation(
                        amount_relation_key=stable_key(
                            "amount_relation",
                            {
                                "kind": "PAYMENT_STAGE",
                                "amount_key": amount_key,
                                "payment_stage_key": stage_key,
                            },
                        ),
                        amount_key=amount_key,
                        relation_kind="PAYMENT_STAGE",
                        relation_state="CONFIRMED",
                        payment_stage_key=stage_key,
                        evidence_ids=[evidence_id],
                    )
                )
            stage_method_keys: list[str] = []
            stage_method_raw = (candidate.stage_payment_method or "").strip()
            if stage_method_raw:
                method_key = _stage_method_key(span)
                methods.append(
                    PaymentMethodObservation(
                        payment_method_key=method_key,
                        raw_text=stage_method_raw,
                        normalized_value=stage_method_raw,
                        evidence_ids=[evidence_id],
                    )
                )
                stage_method_keys.append(method_key)
            stages.append(
                PaymentStage(
                    payment_stage_key=stage_key,
                    name=_observed_text(candidate.stage_name or candidate.quote, evidence_id),
                    sequence=_observed_int(candidate.stage_order, evidence_id),
                    ratio_percent=_observed_decimal(candidate.stage_ratio, evidence_id),
                    amount_keys=stage_amount_keys,
                    trigger_condition=_observed_text(
                        candidate.stage_trigger_condition, evidence_id
                    ),
                    payment_term=_observed_text(candidate.stage_payment_term, evidence_id),
                    payment_method_keys=stage_method_keys,
                    evidence_ids=[evidence_id],
                )
            )
            continue
        if kind == "PAYMENT_METHOD":
            raw = (candidate.payment_method or candidate.quote).strip()
            methods.append(
                PaymentMethodObservation(
                    payment_method_key=stable_key(
                        "payment_method",
                        {"document_key": "main", "start": span[0], "end": span[1]},
                    ),
                    raw_text=raw,
                    normalized_value=raw,
                    evidence_ids=[evidence_id],
                )
            )

    for amount_key, evidence_id in overall_hits:
        relations.append(
            AmountRelation(
                amount_relation_key=stable_key(
                    "amount_relation",
                    {"kind": "CONTRACT_OVERALL", "amount_key": amount_key},
                ),
                amount_key=amount_key,
                relation_kind="CONTRACT_OVERALL",
                relation_state="CONFIRMED",
                payment_stage_key=None,
                evidence_ids=[evidence_id],
            )
        )

    issues = _collect_source_gaps(
        envelope.source_gaps,
        "main",
        evidence,
        allowed_ranges,
        _AMOUNT_FACT_KINDS | _COPY_FACT_KINDS,
        _AMOUNT_FACT_KINDS,
    )
    data = AmountPaymentFacts(
        amounts=sorted(amounts, key=lambda item: item.amount_key),
        amount_relations=sorted(relations, key=lambda item: item.amount_relation_key),
        payment_methods=sorted(methods, key=lambda item: item.payment_method_key),
        payment_stages=sorted(stages, key=lambda item: item.payment_stage_key),
    )
    return _build_domain(data, issues, ["main"], _AMOUNT_FACT_KINDS)


def _assemble_copy(
    envelope: PrepareModelEnvelope,
    canonical_parties: Sequence[CanonicalParty],
    evidence: EvidenceRegistry,
    allowed_ranges: Sequence[MarkdownRange] | None,
) -> FactDomain[CopyTermsFacts]:
    located = _locate_candidates(envelope, "main", evidence, allowed_ranges)

    statements: list[CopyStatement] = []
    allocations: list[CopyAllocation] = []
    scope_key = stable_key("scope", {"document_key": "main"})
    total_statements: list[tuple[str, int | None]] = []

    for candidate, evidence_id, span in located:
        kind = candidate.candidate_kind
        if kind not in ("COPY_TOTAL", "COPY_ALLOCATION"):
            continue
        statement_key = stable_key(
            "copy_statement",
            {"document_key": "main", "start": span[0], "end": span[1]},
        )
        if kind == "COPY_TOTAL":
            count_value = _parse_count(candidate.copies_total)
            statements.append(
                CopyStatement(
                    statement_key=statement_key,
                    scope_key=scope_key,
                    document_key="main",
                    raw_text=candidate.quote,
                    count=_observed_int(candidate.copies_total, evidence_id),
                    evidence_ids=[evidence_id],
                )
            )
            total_statements.append((statement_key, count_value))
            continue
        statements.append(
            CopyStatement(
                statement_key=statement_key,
                scope_key=scope_key,
                document_key="main",
                raw_text=candidate.quote,
                count=_observed_int(candidate.copy_count, evidence_id),
                evidence_ids=[evidence_id],
            )
        )
        semantics = (candidate.copy_allocation_semantics or "").strip() or (
            _derive_allocation_semantics(candidate.quote)
        )
        if semantics not in ("EACH", "COLLECTIVE", "UNCERTAIN"):
            semantics = "UNCERTAIN"
        allocations.append(
            CopyAllocation(
                allocation_key=stable_key(
                    "copy_allocation",
                    {"document_key": "main", "start": span[0], "end": span[1]},
                ),
                statement_key=statement_key,
                candidate_party_keys=_party_keys_in_quote(candidate.quote, canonical_parties),
                allocation_semantics=semantics,
                evidence_ids=[evidence_id],
            )
        )

    overall_total_statement_key: str | None = None
    if total_statements:
        counts = {value for _, value in total_statements}
        if len(counts) == 1 and None not in counts:
            overall_total_statement_key = min(key for key, _ in total_statements)

    issues = _collect_source_gaps(
        envelope.source_gaps,
        "main",
        evidence,
        allowed_ranges,
        _AMOUNT_FACT_KINDS | _COPY_FACT_KINDS,
        _COPY_FACT_KINDS,
    )
    data = CopyTermsFacts(
        statements=sorted(statements, key=lambda item: item.statement_key),
        overall_total_statement_key=overall_total_statement_key,
        allocations=sorted(allocations, key=lambda item: item.allocation_key),
    )
    return _build_domain(data, issues, ["main"], _COPY_FACT_KINDS)


def _assemble_attachment(
    documents: PreparedDocuments,
    evidence: EvidenceRegistry,
    extraction_ranges: Mapping[str, Sequence[MarkdownRange]] | None,
) -> FactDomain[AttachmentManifestFacts]:
    document_keys = sorted(documents.markdown_by_document)
    snapshot_keys = {
        attachment.document_key for attachment in documents.source_snapshot.attachments
    }
    available_attachment_keys = sorted(snapshot_keys)
    valid_target_keys = set(snapshot_keys)

    declarations: list[AttachmentDeclaration] = []
    logicals: list[LogicalAttachmentCandidate] = []
    links: list[AttachmentRelation] = []
    issues: list[FactIssue] = []
    declared_total: ObservedField | None = None

    for document_key in document_keys:
        ranges = (
            extraction_ranges.get(document_key) if extraction_ranges is not None else None
        )
        envelope = _invoke_attachment_document(
            documents.markdown_by_document[document_key],
            document_key,
            ranges,
            available_attachment_keys,
        )
        located = _locate_candidates(envelope, document_key, evidence, ranges)
        candidate_refs = {
            candidate.candidate_ref for candidate, _evidence_id, _span in located
        }

        ref_to_declaration_key: dict[str, str] = {}
        for candidate, _evidence_id, span in located:
            if candidate.candidate_kind == "DECLARED_ATTACHMENT":
                ref_to_declaration_key[candidate.candidate_ref] = stable_key(
                    "attachment_declaration",
                    {"document_key": document_key, "start": span[0], "end": span[1]},
                )

        for candidate, evidence_id, span in located:
            kind = candidate.candidate_kind
            if kind == "DECLARED_TOTAL":
                if document_key == "main" and declared_total is None:
                    declared_total = _observed_int(candidate.declared_total, evidence_id)
                continue
            if kind == "DECLARED_ATTACHMENT":
                declarations.append(
                    AttachmentDeclaration(
                        attachment_declaration_key=ref_to_declaration_key[
                            candidate.candidate_ref
                        ],
                        title=_observed_text(
                            candidate.declared_title or candidate.quote, evidence_id
                        ),
                        ordinal=_observed_int(candidate.declared_index, evidence_id),
                        evidence_ids=[evidence_id],
                    )
                )
                continue
            if kind == "LOGICAL_ATTACHMENT":
                logicals.append(
                    LogicalAttachmentCandidate(
                        logical_attachment_candidate_key=stable_key(
                            "logical_attachment_candidate",
                            {
                                "document_key": document_key,
                                "start": span[0],
                                "end": span[1],
                            },
                        ),
                        parent_document_key=document_key,
                        title=_observed_text(
                            candidate.logical_title or candidate.quote, evidence_id
                        ),
                        source_locator=format_markdown_locator(span[0], span[1]),
                        evidence_ids=[evidence_id],
                    )
                )
                continue
            if kind == "ATTACHMENT_RELATION":
                declaration_ref = (candidate.relation_declaration_ref or "").strip()
                if not declaration_ref or declaration_ref not in ref_to_declaration_key:
                    raise ModelFormatError(
                        "ATTACHMENT_RELATION 的 relation_declaration_ref 未引用同一输出内的 "
                        "DECLARED_ATTACHMENT 候选，引用不闭合"
                    )
                targets = list(candidate.relation_target_document_keys)
                if not targets:
                    raise ModelFormatError(
                        "ATTACHMENT_RELATION 必须给出关系目标 document_key"
                    )
                for target in targets:
                    if target in candidate_refs:
                        raise ModelFormatError(
                            "ATTACHMENT_RELATION 目标不得引用本次输出的 candidate_ref: "
                            + target
                        )
                    if target == "main" or target not in valid_target_keys:
                        raise ModelFormatError(
                            "ATTACHMENT_RELATION 目标必须是实际 document_key: " + target
                        )
                if candidate.relation_state is None:
                    raise ModelFormatError(
                        "ATTACHMENT_RELATION 必须显式给出 relation_state"
                    )
                if candidate.relation_state == "LINKED" and len(targets) != 1:
                    raise ModelFormatError("LINKED 关系必须且只能关联一个实际文档")
                links.append(
                    AttachmentRelation(
                        attachment_relation_key=stable_key(
                            "attachment_relation",
                            {
                                "document_key": document_key,
                                "start": span[0],
                                "end": span[1],
                            },
                        ),
                        attachment_declaration_key=ref_to_declaration_key[declaration_ref],
                        candidate_document_keys=sorted(dict.fromkeys(targets)),
                        relation_state=candidate.relation_state,
                        evidence_ids=[evidence_id],
                    )
                )
                continue
            # PARTY_MENTION 等主体称谓观察不进入附件清单装配

        issues.extend(
            _collect_source_gaps(
                envelope.source_gaps,
                document_key,
                evidence,
                ranges,
                _ATTACHMENT_FACT_KINDS,
            )
        )

    if declared_total is None:
        declared_total = _absent_observed()

    data = AttachmentManifestFacts(
        declared_total=declared_total,
        declarations=sorted(
            declarations, key=lambda item: item.attachment_declaration_key
        ),
        logical_attachment_candidates=sorted(
            logicals, key=lambda item: item.logical_attachment_candidate_key
        ),
        links=sorted(links, key=lambda item: item.attachment_relation_key),
    )
    return _build_domain(data, issues, document_keys, _ATTACHMENT_FACT_KINDS)


def extract_amount_copy_manifest(
    documents: PreparedDocuments,
    canonical_parties: Sequence[CanonicalParty],
    evidence: EvidenceRegistry,
    extraction_ranges: Mapping[str, Sequence[MarkdownRange]] | None = None,
) -> CommercialFactDomains:
    """商业三域唯一内部入口: 主合同金额/份数 + 逐文档附件清单装配。"""
    main_ranges = (
        extraction_ranges.get("main") if extraction_ranges is not None else None
    )
    main_envelope = _invoke_amount_copy_main(
        documents.markdown_by_document["main"], main_ranges
    )
    return CommercialFactDomains(
        amount_payment=_assemble_amount(main_envelope, evidence, main_ranges),
        copy_terms=_assemble_copy(
            main_envelope, canonical_parties, evidence, main_ranges
        ),
        attachment_manifest=_assemble_attachment(documents, evidence, extraction_ranges),
    )
