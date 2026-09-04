from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.capabilities.contract_review.two_stage.evidence import (
    EvidenceLocationError,
    EvidenceRegistry,
)
from app.capabilities.contract_review.two_stage.keys import stable_key
from app.capabilities.contract_review.two_stage.prepare_model import (
    AttachmentCandidate,
    HeaderPartiesCandidate,
    PrepareModelEnvelope,
    SourceGapCandidate,
    invoke_typed_prepare_model,
)
from app.capabilities.contract_review.two_stage.schemas import (
    CanonicalParty,
    DeclaredDesignation,
    DocumentCoverage,
    EvidenceItem,
    FactDomain,
    FactIssue,
    HeaderFacts,
    IdentityGroup,
    NameObservation,
    ObservedField,
    ObservedValue,
    PartiesFacts,
    PartyMention,
    SigningLocationObservation,
)


@dataclass(frozen=True)
class PreparedDocument:
    document_key: str = "main"
    markdown: str = ""


@dataclass(frozen=True)
class HeaderPartiesExtraction:
    header: HeaderFacts
    canonical_parties: list[CanonicalParty]
    party_mentions: list[PartyMention]
    fact_issues: list[FactIssue]


MarkdownRange = tuple[int, int]

_HEADER_FACT_KINDS = {
    "CONTRACT_NAME",
    "CONTRACT_NUMBER",
    "PROJECT_NAME",
    "PROJECT_NUMBER",
    "SIGNING_LOCATION",
    "SIGNING_DATE",
}
_PARTY_FACT_KINDS = {
    "CANONICAL_PARTY",
    "PARTY_MENTION",
}

_ISO_DATE_RE = re.compile(r"^(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?$")

_PLACEHOLDER_CHARS = set("某Xx某")
_GENERIC_ROOTS = {
    "采购", "销售", "买卖", "供应", "供货", "订购", "购置", "购买",
    "项目", "合作", "合伙", "协作", "联合", "战略",
    "服务", "咨询", "顾问", "代理", "委托", "托管", "承运", "经纪",
    "工程", "施工", "建设", "建造", "安装", "装修", "改造", "维修", "维护", "运维",
    "设计", "规划", "勘察", "监理", "总包", "分包", "承包", "外包", "租赁", "融资",
}
_CITY_NAMES = {
    "北京", "上海", "天津", "重庆", "石家庄", "太原", "呼和浩特", "沈阳", "长春", "哈尔滨",
    "南京", "杭州", "合肥", "福州", "南昌", "济南", "郑州", "武汉", "长沙", "广州",
    "南宁", "海口", "成都", "贵阳", "昆明", "拉萨", "西安", "兰州", "西宁", "银川",
    "乌鲁木齐", "深圳", "苏州", "宁波", "无锡", "青岛", "大连", "厦门", "珠海",
}


def _normalize_iso_date(text: str) -> str | None:
    value = (text or "").strip()
    match = _ISO_DATE_RE.match(value)
    if not match:
        return None
    year, month, day = match.group(1), match.group(2), match.group(3)
    try:
        datetime(int(year), int(month), int(day))
    except ValueError:
        return None
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _derive_name_specificity(text: str) -> str:
    """Derive SPECIFIC/GENERIC/UNCERTAIN from a name observation."""
    value = (text or "").strip()
    if not value:
        return "UNCERTAIN"
    if re.search(r"(公司|企业|集团|厂|中心|研究院|事务所|工作室|有限合伙)$", value):
        return "SPECIFIC"
    core = re.sub(r"(合同|协议|合约|契约)$", "", value)
    if not core or core in {"合同", "协议", "合约", "契约"}:
        return "GENERIC"
    normalized = core
    for token in sorted(_GENERIC_ROOTS, key=len, reverse=True):
        normalized = normalized.replace(token, "＃")
    root_hits = normalized.count("＃")
    remainder = normalized.replace("＃", "").strip()
    placeholder_present = any(c in _PLACEHOLDER_CHARS for c in core)
    if root_hits >= 2:
        return "GENERIC"
    if root_hits == 1 and not placeholder_present:
        return "GENERIC"
    if root_hits == 1 and placeholder_present:
        return "UNCERTAIN"
    if not remainder:
        if any(c in _PLACEHOLDER_CHARS for c in core):
            return "UNCERTAIN"
        return "GENERIC"
    return "UNCERTAIN"


def _extract_city_candidates(text: str) -> list[str]:
    """Return reliably extracted city names from raw location text."""
    result: list[str] = []
    seen: set[str] = set()
    for city in sorted(_CITY_NAMES, key=len, reverse=True):
        if city in text and city not in seen:
            result.append(city)
            seen.add(city)
    return result


def _fact_issue_key(code: str, basis: str, document_keys: Sequence[str], affected_fact_kinds: Sequence[str]) -> str:
    return stable_key(
        "fact_issue",
        {
            "code": code,
            "basis": basis,
            "document_keys": list(document_keys),
            "affected_fact_kinds": list(affected_fact_kinds),
        },
    )


def _locate_evidence(evidence: EvidenceRegistry, document_key: str, quote: str) -> str | None:
    try:
        item = evidence.register(document_key=document_key, quote=quote)
        return item.evidence_id
    except EvidenceLocationError:
        return None


def _unlocatable_issue(document_key: str, quote: str, affected_fact_kind: str) -> FactIssue:
    basis = f"quote:{quote}"
    issue_key = _fact_issue_key(
        "EVIDENCE_UNLOCATABLE",
        basis,
        [document_key],
        [affected_fact_kind],
    )
    return FactIssue(
        fact_issue_key=issue_key,
        code="EVIDENCE_UNLOCATABLE",
        message="候选引文在文档中无法唯一定位",
        related_document_keys=[document_key],
        affected_fact_kinds=[affected_fact_kind],
        evidence_ids=[],
    )


def _gap_issue(
    gap: SourceGapCandidate,
    document_key: str,
    evidence_id: str | None = None,
    code: str = "SOURCE_UNREADABLE",
) -> FactIssue:
    affected = list(gap.affected_fact_kinds)
    related = [gap.document_key if gap.document_key else document_key]
    basis = f"quote:{gap.quote}" if gap.quote else "local"
    issue_key = _fact_issue_key(code, basis, related, affected)
    return FactIssue(
        fact_issue_key=issue_key,
        code=code,
        message=gap.message,
        related_document_keys=related,
        affected_fact_kinds=affected,
        evidence_ids=[evidence_id] if evidence_id else [],
    )


def _absent() -> ObservedField[Any]:
    return ObservedField(presence="ABSENT", normalization_state="NOT_APPLICABLE", observations=[])


def _merge_entries(entries: list[tuple[str, str]]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for v, e in entries:
        key = (v or "").strip()
        if key:
            merged.setdefault(key, []).append(e)
    return merged


def _name_field(entries: list[tuple[str, str]]) -> ObservedField[NameObservation]:
    if not entries:
        return _absent()
    first_ev = entries[0][1]
    if all((v or "").strip() == "" for v, _ in entries):
        obs = NameObservation(raw_text="", normalized_value="", specificity="UNCERTAIN", evidence_ids=[first_ev])
        return ObservedField[NameObservation](presence="PRESENT_EMPTY", normalization_state="NOT_APPLICABLE", observations=[obs])
    merged = _merge_entries(entries)
    observations = [
        NameObservation(
            raw_text=v,
            normalized_value=v,
            specificity=_derive_name_specificity(v),
            evidence_ids=eids,
        )
        for v, eids in sorted(merged.items())
    ]
    distinct = {o.normalized_value for o in observations}
    presence = "UNCERTAIN" if len(distinct) > 1 else "PRESENT_VALUE"
    return ObservedField[NameObservation](presence=presence, normalization_state="VALID", observations=observations)


def _plain_value_field(entries: list[tuple[str | None, str]]) -> ObservedField[ObservedValue[str]]:
    if not entries:
        return _absent()
    if all((v or "").strip() == "" for v, _ in entries):
        obs = ObservedValue(raw_text="", normalized_value="", evidence_ids=[entries[0][1]])
        return ObservedField[ObservedValue[str]](presence="PRESENT_EMPTY", normalization_state="NOT_APPLICABLE", observations=[obs])
    merged: dict[str, list[str]] = {}
    for raw, eid in entries:
        key = (raw or "").strip()
        if key:
            merged.setdefault(key, []).append(eid)
    observations = [
        ObservedValue(raw_text=raw, normalized_value=raw, evidence_ids=eids)
        for raw, eids in sorted(merged.items())
    ]
    distinct = {o.normalized_value for o in observations}
    presence = "UNCERTAIN" if len(distinct) > 1 else "PRESENT_VALUE"
    return ObservedField[ObservedValue[str]](presence=presence, normalization_state="VALID", observations=observations)


def _location_field(entries: list[tuple[str, str]]) -> ObservedField[SigningLocationObservation]:
    if not entries:
        return _absent()
    if all((v or "").strip() == "" for v, _ in entries):
        obs = SigningLocationObservation(raw_text="", normalized_value="", city_candidates=[], evidence_ids=[entries[0][1]])
        return ObservedField[SigningLocationObservation](presence="PRESENT_EMPTY", normalization_state="NOT_APPLICABLE", observations=[obs])
    merged = _merge_entries(entries)
    observations = [
        SigningLocationObservation(
            raw_text=v,
            normalized_value=v,
            city_candidates=_extract_city_candidates(v),
            evidence_ids=eids,
        )
        for v, eids in sorted(merged.items())
    ]
    distinct = {o.normalized_value for o in observations}
    presence = "UNCERTAIN" if len(distinct) > 1 else "PRESENT_VALUE"
    return ObservedField[SigningLocationObservation](presence=presence, normalization_state="VALID", observations=observations)


def _date_field(entries: list[tuple[str, str]]) -> ObservedField[ObservedValue[str]]:
    if not entries:
        return _absent()
    if all((r or "").strip() == "" for r, _ in entries):
        obs = ObservedValue(raw_text="", normalized_value=None, evidence_ids=[entries[0][1]])
        return ObservedField[ObservedValue[str]](presence="PRESENT_EMPTY", normalization_state="NOT_APPLICABLE", observations=[obs])
    merged: dict[str, list[str]] = {}
    for raw, eid in entries:
        key = (raw or "").strip()
        if key:
            merged.setdefault(key, []).append(eid)
    observations = [
        ObservedValue(raw_text=raw, normalized_value=_normalize_iso_date(raw), evidence_ids=eids)
        for raw, eids in sorted(merged.items())
    ]
    normalized_values = {o.normalized_value for o in observations if o.normalized_value is not None}
    if len(normalized_values) > 1:
        return ObservedField[ObservedValue[str]](presence="UNCERTAIN", normalization_state="VALID", observations=observations)
    if all(o.normalized_value is None for o in observations):
        return ObservedField[ObservedValue[str]](presence="PRESENT_VALUE", normalization_state="INVALID", observations=observations)
    return ObservedField[ObservedValue[str]](presence="PRESENT_VALUE", normalization_state="VALID", observations=observations)



def _build_header_facts(
    contract_names: list[tuple[str, str]],
    contract_numbers: list[tuple[str, str]],
    project_names: list[tuple[str, str]],
    project_numbers: list[tuple[str, str]],
    locations: list[tuple[str, str]],
    dates: list[tuple[str, str]],
) -> HeaderFacts:
    return HeaderFacts(
        contract_identity=IdentityGroup(
            name=_name_field(contract_names),
            number=_plain_value_field(contract_numbers),
        ),
        project_identity=IdentityGroup(
            name=_name_field(project_names),
            number=_plain_value_field(project_numbers),
        ),
        signing_location=_location_field(locations),
        signing_date=_date_field(dates),
    )


def _build_canonical_parties(
    raw_groups: dict[str, dict[str, Any]],
) -> list[CanonicalParty]:
    parties: list[CanonicalParty] = []
    named = [(k, v) for k, v in raw_groups.items() if k.strip()]
    empty = [(k, v) for k, v in raw_groups.items() if not k.strip()]
    for norm_name, group in sorted(named) + sorted(empty):
        party_key = stable_key("party", {"declared_name": norm_name})
        raw_names = sorted(group["raw_names"])
        definition_evidence: list[str] = sorted(group["evidence"])
        if not norm_name.strip():
            declared_name = ObservedField[ObservedValue[str]](
                presence="PRESENT_EMPTY",
                normalization_state="NOT_APPLICABLE",
                observations=[ObservedValue(raw_text="", normalized_value="", evidence_ids=definition_evidence[:1])],
            )
        else:
            name_obs = ObservedValue(
                raw_text=raw_names[0],
                normalized_value=norm_name,
                evidence_ids=definition_evidence,
            )
            declared_name = ObservedField[ObservedValue[str]](
                presence="PRESENT_VALUE",
                normalization_state="VALID",
                observations=[name_obs],
            )
        designations: list[DeclaredDesignation] = []
        seen_designations: set[str] = set()
        for role in sorted(group["roles"].keys()):
            dk = stable_key("designation", {"party_key": party_key, "kind": "CONTRACT_ROLE", "text": role})
            if dk in seen_designations:
                continue
            seen_designations.add(dk)
            designations.append(
                DeclaredDesignation(
                    designation_key=dk,
                    kind="CONTRACT_ROLE",
                    text=role,
                    evidence_ids=group["roles"][role],
                )
            )
        for alias in sorted(group["aliases"].keys()):
            dk = stable_key("designation", {"party_key": party_key, "kind": "NAME_ALIAS", "text": alias})
            if dk in seen_designations:
                continue
            seen_designations.add(dk)
            designations.append(
                DeclaredDesignation(
                    designation_key=dk,
                    kind="NAME_ALIAS",
                    text=alias,
                    evidence_ids=group["aliases"][alias],
                )
            )
        parties.append(
            CanonicalParty(
                party_key=party_key,
                declared_name=declared_name,
                declared_designations=designations,
                definition_evidence_ids=definition_evidence,
            )
        )
    return parties


def _build_lookup(canonical_parties: list[CanonicalParty]) -> dict[str, Any]:
    by_name: dict[str, str] = {}
    by_role: dict[str, list[tuple[str, str, str]]] = {}
    designation_by_key: dict[str, str] = {}
    for party in canonical_parties:
        for obs in party.declared_name.observations:
            if obs.normalized_value:
                by_name[obs.normalized_value] = party.party_key
        for des in party.declared_designations:
            designation_by_key[des.designation_key] = des.text
            if des.kind == "CONTRACT_ROLE":
                for eid in des.evidence_ids:
                    by_role.setdefault(des.text, []).append((party.party_key, des.designation_key, eid))
    return {
        "by_name": by_name,
        "by_role": by_role,
        "designation_by_key": designation_by_key,
    }


def _mention_key(document_key: str, observed_text: str, candidate_party_keys: Sequence[str], evidence_start: int) -> str:
    return stable_key(
        "mention",
        {
            "document_key": document_key,
            "candidate_party_keys": list(candidate_party_keys),
            "evidence_start": evidence_start,
        },
    )


def _assemble_single_mention(
    *,
    document_key: str,
    observed_text: str,
    explicit_name: str | None,
    role: str | None,
    canonical_parties: list[CanonicalParty],
    lookup: dict[str, Any],
    evidence_id: str,
    evidence_start: int,
) -> PartyMention:
    name = (explicit_name or "").strip()
    role_text = (role or "").strip()
    by_name = lookup["by_name"]
    by_role = lookup["by_role"]

    if name:
        matched_key = by_name.get(name)
        if matched_key is not None:
            return PartyMention(
                mention_key=_mention_key(document_key, observed_text, [matched_key], evidence_start),
                document_key=document_key,
                mention_kind="PARTY_APPELLATION",
                observed_text=observed_text,
                referenced_designation_keys=[],
                explicit_entity_name=None,
                candidate_party_keys=[matched_key],
                local_definition_state="PRESENT",
                comparison_state="MATCHED_DECLARATION",
                evidence_ids=[evidence_id],
            )
        return PartyMention(
            mention_key=_mention_key(document_key, observed_text, [], evidence_start),
            document_key=document_key,
            mention_kind="PARTY_DEFINITION",
            observed_text=observed_text,
            referenced_designation_keys=[],
            explicit_entity_name=None,
            candidate_party_keys=[],
            local_definition_state="PRESENT",
            comparison_state="OUTSIDE_DECLARED_SET",
            evidence_ids=[evidence_id],
        )

    if role_text:
        matches = by_role.get(role_text, [])
        if len(matches) == 1:
            party_key, designation_key, _eid = matches[0]
            return PartyMention(
                mention_key=_mention_key(document_key, observed_text, [party_key], evidence_start),
                document_key=document_key,
                mention_kind="ROLE_REFERENCE",
                observed_text=observed_text,
                referenced_designation_keys=[designation_key],
                explicit_entity_name=None,
                candidate_party_keys=[party_key],
                local_definition_state="ABSENT",
                comparison_state="MATCHED_DECLARATION",
                evidence_ids=[evidence_id],
            )
        if len(matches) > 1:
            candidate_keys = sorted({pk for pk, _, _ in matches})
            return PartyMention(
                mention_key=_mention_key(document_key, observed_text, candidate_keys, evidence_start),
                document_key=document_key,
                mention_kind="ROLE_REFERENCE",
                observed_text=observed_text,
                referenced_designation_keys=[],
                explicit_entity_name=None,
                candidate_party_keys=candidate_keys,
                local_definition_state="UNCERTAIN",
                comparison_state="UNCERTAIN",
                evidence_ids=[evidence_id],
            )
        return PartyMention(
            mention_key=_mention_key(document_key, observed_text, [], evidence_start),
            document_key=document_key,
            mention_kind="ROLE_REFERENCE",
            observed_text=observed_text,
            referenced_designation_keys=[],
            explicit_entity_name=None,
            candidate_party_keys=[],
            local_definition_state="ABSENT",
            comparison_state="UNCERTAIN",
            evidence_ids=[evidence_id],
        )

    matched_key = by_name.get(observed_text.strip())
    if matched_key is not None:
        return PartyMention(
            mention_key=_mention_key(document_key, observed_text, [matched_key], evidence_start),
            document_key=document_key,
            mention_kind="PARTY_APPELLATION",
            observed_text=observed_text,
            referenced_designation_keys=[],
            explicit_entity_name=None,
            candidate_party_keys=[matched_key],
            local_definition_state="PRESENT",
            comparison_state="MATCHED_DECLARATION",
            evidence_ids=[evidence_id],
        )
    return PartyMention(
        mention_key=_mention_key(document_key, observed_text, [], evidence_start),
        document_key=document_key,
        mention_kind="PARTY_DEFINITION",
        observed_text=observed_text,
        referenced_designation_keys=[],
        explicit_entity_name=None,
        candidate_party_keys=[],
        local_definition_state="PRESENT",
        comparison_state="OUTSIDE_DECLARED_SET",
        evidence_ids=[evidence_id],
    )



def _index_source_gaps(
    gaps: list[SourceGapCandidate],
    document_key: str,
    evidence: EvidenceRegistry,
) -> tuple[list[FactIssue], dict[str, str]]:
    fact_issues: list[FactIssue] = []
    quote_to_evidence: dict[str, str] = {}
    for gap in gaps:
        eid: str | None = None
        if gap.quote:
            eid = _locate_evidence(evidence, document_key, gap.quote)
            if eid:
                quote_to_evidence[gap.quote] = eid
        fact_issues.append(_gap_issue(gap, document_key, evidence_id=eid))
    return fact_issues, quote_to_evidence


def assemble_header_parties(
    envelope: PrepareModelEnvelope,
    document: PreparedDocument,
    evidence: EvidenceRegistry,
) -> HeaderPartiesExtraction:
    document_key = document.document_key or "main"
    fact_issues: list[FactIssue] = []

    contract_names: list[tuple[str, str]] = []
    contract_numbers: list[tuple[str, str]] = []
    project_names: list[tuple[str, str]] = []
    project_numbers: list[tuple[str, str]] = []
    locations: list[tuple[str, str]] = []
    dates: list[tuple[str, str]] = []

    canonical_groups: dict[str, dict[str, Any]] = {}
    mention_specs: list[dict[str, Any]] = []

    for candidate in envelope.candidates:
        if not isinstance(candidate, HeaderPartiesCandidate):
            continue
        quote = candidate.quote
        evidence_id = _locate_evidence(evidence, document_key, quote)
        if evidence_id is None:
            fact_issues.append(_unlocatable_issue(document_key, quote, candidate.candidate_kind))
            continue
        kind = candidate.candidate_kind
        if kind == "CONTRACT_NAME":
            if candidate.contract_name is not None:
                contract_names.append((candidate.contract_name, evidence_id))
        elif kind == "CONTRACT_NUMBER":
            if candidate.contract_number is not None:
                contract_numbers.append((candidate.contract_number, evidence_id))
        elif kind == "PROJECT_NAME":
            if candidate.project_name is not None:
                project_names.append((candidate.project_name, evidence_id))
        elif kind == "PROJECT_NUMBER":
            if candidate.project_number is not None:
                project_numbers.append((candidate.project_number, evidence_id))
        elif kind == "SIGNING_LOCATION":
            if candidate.signing_location is not None:
                locations.append((candidate.signing_location, evidence_id))
        elif kind == "SIGNING_DATE":
            if candidate.signing_date is not None:
                dates.append((candidate.signing_date, evidence_id))
        elif kind == "CANONICAL_PARTY":
            party_name = (candidate.party_name or "").strip()
            norm_name = party_name
            group = canonical_groups.setdefault(
                norm_name,
                {"raw_names": set(), "roles": {}, "aliases": {}, "evidence": set()},
            )
            group["raw_names"].add(party_name)
            group["evidence"].add(evidence_id)
            role = (candidate.party_role or "").strip()
            if role:
                group["roles"].setdefault(role, set()).add(evidence_id)
            for alias in candidate.party_aliases:
                alias_text = (alias or "").strip()
                if alias_text and alias_text != party_name:
                    group["aliases"].setdefault(alias_text, set()).add(evidence_id)
        elif kind == "PARTY_MENTION":
            observed_text = (candidate.mention_text or candidate.quote or "").strip()
            if observed_text:
                mention_specs.append(
                    {
                        "observed_text": observed_text,
                        "explicit_name": candidate.party_name,
                        "role": candidate.party_role,
                        "evidence_id": evidence_id,
                    },
                )

    gap_issues, _gap_quote_to_evidence = _index_source_gaps(
        envelope.source_gaps, document_key, evidence
    )
    fact_issues.extend(gap_issues)

    header = _build_header_facts(
        contract_names,
        contract_numbers,
        project_names,
        project_numbers,
        locations,
        dates,
    )

    for group in canonical_groups.values():
        group["roles"] = {role: sorted(eids) for role, eids in group["roles"].items()}
        group["aliases"] = {alias: sorted(eids) for alias, eids in group["aliases"].items()}
        group["evidence"] = sorted(group["evidence"])
        group["raw_names"] = sorted(group["raw_names"])

    canonical_parties = _build_canonical_parties(canonical_groups)
    lookup = _build_lookup(canonical_parties)

    party_mentions: list[PartyMention] = []
    for spec in mention_specs:
        eid = spec["evidence_id"]
        start = _evidence_start(evidence, eid)
        mention = _assemble_single_mention(
            document_key=document_key,
            observed_text=spec["observed_text"],
            explicit_name=spec["explicit_name"],
            role=spec["role"],
            canonical_parties=canonical_parties,
            lookup=lookup,
            evidence_id=eid,
            evidence_start=start,
        )
        party_mentions.append(mention)

    return HeaderPartiesExtraction(
        header=header,
        canonical_parties=canonical_parties,
        party_mentions=party_mentions,
        fact_issues=fact_issues,
    )


def _evidence_start(evidence: EvidenceRegistry, evidence_id: str) -> int:
    for item in evidence.items():
        if item.evidence_id == evidence_id:
            locator = item.source_locator
            parts = locator.split(":")[-1].split("-")
            return int(parts[0]) if parts else 0
    return 0




def assemble_party_mentions(
    envelope: PrepareModelEnvelope,
    canonical_parties: list[CanonicalParty],
    document: PreparedDocument,
    evidence: EvidenceRegistry,
    extraction_ranges: Sequence[MarkdownRange] | None = None,
) -> list[PartyMention]:
    document_key = document.document_key or "main"
    lookup = _build_lookup(canonical_parties)
    declared_names = {obs.normalized_value for party in canonical_parties for obs in party.declared_name.observations if obs.normalized_value}
    result: list[PartyMention] = []
    for candidate in envelope.candidates:
        if not isinstance(candidate, AttachmentCandidate):
            continue
        if candidate.candidate_kind != "PARTY_MENTION":
            continue
        quote = candidate.quote
        observed_text = (candidate.mention_text or quote or "").strip()
        if not observed_text:
            continue
        allowed_range = None
        if extraction_ranges:
            allowed_range = (min(s for s, _ in extraction_ranges), max(e for _, e in extraction_ranges))
        try:
            item = evidence.register(document_key=document_key, quote=quote, allowed_range=allowed_range)
        except EvidenceLocationError:
            continue
        evidence_id = item.evidence_id
        start = _evidence_start(evidence, evidence_id)
        if observed_text in declared_names:
            matched_key = lookup["by_name"][observed_text]
            mention = PartyMention(
                mention_key=_mention_key(document_key, observed_text, [matched_key], start),
                document_key=document_key,
                mention_kind="PARTY_APPELLATION",
                observed_text=observed_text,
                referenced_designation_keys=[],
                explicit_entity_name=None,
                candidate_party_keys=[matched_key],
                local_definition_state="ABSENT",
                comparison_state="MATCHED_DECLARATION",
                evidence_ids=[evidence_id],
            )
        else:
            mention = _assemble_single_mention(
                document_key=document_key,
                observed_text=observed_text,
                explicit_name=observed_text,
                role=None,
                canonical_parties=canonical_parties,
                lookup=lookup,
                evidence_id=evidence_id,
                evidence_start=start,
            )
            if mention.comparison_state != "MATCHED_DECLARATION":
                mention = mention.model_copy(update={
                    "mention_kind": "PARTY_DEFINITION",
                    "local_definition_state": "PRESENT",
                    "comparison_state": "OUTSIDE_DECLARED_SET",
                })
        result.append(mention)
    return result


def invoke_attachment_candidates(
    document: PreparedDocument,
    extraction_ranges: Sequence[MarkdownRange] | None = None,
) -> PrepareModelEnvelope:
    return invoke_typed_prepare_model(
        "prepare_attachment_document",
        markdown=document.markdown,
        scope_label="attachment",
        extraction_input="{}",
    )


def extract_header_and_main_parties(
    document: PreparedDocument,
    evidence: EvidenceRegistry,
) -> HeaderPartiesExtraction:
    envelope = invoke_typed_prepare_model(
        "prepare_header_parties_main",
        markdown=document.markdown,
        scope_label="main",
        extraction_input="{}",
    )
    return assemble_header_parties(envelope, document, evidence)


def extract_attachment_party_mentions(
    document: PreparedDocument,
    canonical_parties: list[CanonicalParty],
    evidence: EvidenceRegistry,
    extraction_ranges: Sequence[MarkdownRange] | None = None,
) -> list[PartyMention]:
    envelope = invoke_attachment_candidates(document, extraction_ranges=extraction_ranges)
    return assemble_party_mentions(
        envelope,
        canonical_parties,
        document,
        evidence,
        extraction_ranges=extraction_ranges,
    )


def build_header_fact_domain(
    header: HeaderFacts,
    fact_issues: list[FactIssue],
) -> FactDomain[HeaderFacts]:
    relevant = [i for i in fact_issues if _HEADER_FACT_KINDS.intersection(i.affected_fact_kinds)]
    if not relevant:
        coverage = DocumentCoverage(document_key="main", state="COMPLETE", affected_fact_kinds=[], fact_issue_keys=[])
        return FactDomain(state="COMPLETE", coverage=[coverage], data=header, issues=[])
    issue_keys = [i.fact_issue_key for i in relevant]
    affected = sorted(_HEADER_FACT_KINDS.intersection({k for i in relevant for k in i.affected_fact_kinds}))
    coverage = DocumentCoverage(document_key="main", state="PARTIAL", affected_fact_kinds=affected, fact_issue_keys=issue_keys)
    return FactDomain(state="PARTIAL", coverage=[coverage], data=header, issues=relevant)


def build_parties_fact_domain(
    canonical_parties: list[CanonicalParty],
    party_mentions: list[PartyMention],
    fact_issues: list[FactIssue],
    document_keys: Sequence[str],
) -> FactDomain[PartiesFacts]:
    relevant = [i for i in fact_issues if _PARTY_FACT_KINDS.intersection(i.affected_fact_kinds)]
    data = PartiesFacts(canonical_parties=canonical_parties, party_mentions=party_mentions)
    if not relevant:
        coverage = [
            DocumentCoverage(document_key=dk, state="COMPLETE", affected_fact_kinds=[], fact_issue_keys=[])
            for dk in sorted(document_keys)
        ]
        return FactDomain(state="COMPLETE", coverage=coverage, data=data, issues=[])
    coverage = []
    for dk in sorted(document_keys):
        doc_issues = [i for i in relevant if dk in i.related_document_keys]
        if not doc_issues:
            coverage.append(DocumentCoverage(document_key=dk, state="COMPLETE", affected_fact_kinds=[], fact_issue_keys=[]))
        else:
            issue_keys = [i.fact_issue_key for i in doc_issues]
            affected = sorted(_PARTY_FACT_KINDS.intersection({k for i in doc_issues for k in i.affected_fact_kinds}))
            coverage.append(DocumentCoverage(document_key=dk, state="PARTIAL", affected_fact_kinds=affected, fact_issue_keys=issue_keys))
    return FactDomain(state="PARTIAL", coverage=coverage, data=data, issues=relevant)

