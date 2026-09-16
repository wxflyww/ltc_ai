from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.capabilities.contract_review.two_stage.evidence import (
    EvidenceLocationError,
    EvidenceRegistry,
)
from app.core.errors import ModelFormatError
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
_GENERIC_SUFFIXES = re.compile(r"(合同|协议|合约|契约)$")
_CONTRACT_TYPE_WORDS = {"合同", "协议", "合约", "契约"}
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

    core = _GENERIC_SUFFIXES.sub("", value)
    if not core or core in _CONTRACT_TYPE_WORDS:
        return "GENERIC"

    normalized = core
    for token in sorted(_GENERIC_ROOTS, key=len, reverse=True):
        normalized = normalized.replace(token, "＃")
    marker_count = normalized.count("＃")
    remainder = normalized.replace("＃", "").strip()
    has_placeholder = any(c in _PLACEHOLDER_CHARS for c in core)

    if marker_count >= 2:
        return "GENERIC"
    if marker_count == 1:
        return "UNCERTAIN" if has_placeholder else "GENERIC"
    if not remainder:
        return "UNCERTAIN" if has_placeholder else "GENERIC"
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


def _fact_issue_key(
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


def _evidence_start(evidence: EvidenceRegistry, evidence_id: str) -> int:
    if evidence.is_unlocatable(evidence_id):
        return -1
    for item in evidence.items():
        if item.evidence_id == evidence_id:
            parts = item.source_locator.split(":")[-1].split("-")
            return int(parts[0]) if parts and parts[0].isdigit() else 0
    return 0


def _dedupe_issues(issues: list[FactIssue]) -> list[FactIssue]:
    """按键去重并保持确定性顺序，重复键合并 evidence_ids。"""
    merged: dict[str, FactIssue] = {}
    for issue in issues:
        existing = merged.get(issue.fact_issue_key)
        if existing is None:
            merged[issue.fact_issue_key] = issue
            continue
        extra = [eid for eid in issue.evidence_ids if eid not in existing.evidence_ids]
        if extra:
            merged[issue.fact_issue_key] = existing.model_copy(
                update={"evidence_ids": [*existing.evidence_ids, *sorted(extra)]}
            )
    return [merged[key] for key in sorted(merged)]


def _locate_evidence(
    evidence: EvidenceRegistry,
    document_key: str,
    quote: str,
    allowed_ranges: Sequence[MarkdownRange] | None = None,
    issue_basis: str = "local",
    affected_fact_kinds: Sequence[str] = (),
) -> tuple[str | None, FactIssue | None]:
    """Locate evidence. On failure emit a FactIssue keyed on business coordinates.

    定位失败不再返回 quote 派生的内部 unlocatable id：不可定位证据不得
    流入任何公开 evidence 引用（PartyMention.evidence_ids 等）。
    """
    try:
        if allowed_ranges is not None:
            item = evidence.register(
                document_key=document_key,
                quote=quote,
                allowed_ranges=list(allowed_ranges),
            )
        else:
            item = evidence.register(document_key=document_key, quote=quote)
        return item.evidence_id, None
    except EvidenceLocationError:
        return None, _unlocatable_issue(document_key, issue_basis, affected_fact_kinds)


def _register_mention(
    mentions_by_key: dict[str, PartyMention],
    mention: PartyMention,
) -> None:
    """同键仅允许完全相同的重复候选去重；不同语义碰撞必须失败，禁止静默覆盖。"""
    existing = mentions_by_key.get(mention.mention_key)
    if existing is None:
        mentions_by_key[mention.mention_key] = mention
        return
    if existing != mention:
        raise ModelFormatError("party mention 稳定键冲突：不同语义候选产生相同 mention_key")


def _require_matching_document_key(candidate_document_key: str, document_key: str) -> None:
    """错文档候选违反模型组装契约，按现有格式错误语义使请求失败。"""
    if candidate_document_key != document_key:
        raise ModelFormatError(
            f"候选 document_key 与当前处理文档不一致: {candidate_document_key} != {document_key}"
        )


def _unlocatable_issue(
    document_key: str,
    basis: str,
    affected_fact_kinds: Sequence[str],
) -> FactIssue:
    issue_key = _fact_issue_key(
        "EVIDENCE_UNLOCATABLE",
        basis,
        [document_key],
        list(affected_fact_kinds) if affected_fact_kinds else ["UNKNOWN"],
    )
    return FactIssue(
        fact_issue_key=issue_key,
        code="EVIDENCE_UNLOCATABLE",
        message="候选引文在文档中无法唯一定位",
        related_document_keys=[document_key],
        affected_fact_kinds=list(affected_fact_kinds) if affected_fact_kinds else ["UNKNOWN"],
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
    basis = f"evidence:{evidence_id}" if evidence_id else "local"
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
    if all((v or "").strip() == "" for v, _ in entries):
        obs = NameObservation(
            raw_text="",
            normalized_value="",
            specificity="UNCERTAIN",
            evidence_ids=[entries[0][1]],
        )
        return ObservedField[NameObservation](
            presence="PRESENT_EMPTY",
            normalization_state="NOT_APPLICABLE",
            observations=[obs],
        )
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
    return ObservedField[NameObservation](
        presence=presence, normalization_state="VALID", observations=observations
    )


def _plain_value_field(entries: list[tuple[str | None, str]]) -> ObservedField[ObservedValue[str]]:
    if not entries:
        return _absent()
    if all((v or "").strip() == "" for v, _ in entries):
        obs = ObservedValue(raw_text="", normalized_value="", evidence_ids=[entries[0][1]])
        return ObservedField[ObservedValue[str]](
            presence="PRESENT_EMPTY",
            normalization_state="NOT_APPLICABLE",
            observations=[obs],
        )
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
    return ObservedField[ObservedValue[str]](
        presence=presence, normalization_state="VALID", observations=observations
    )


def _location_field(entries: list[tuple[str, str]]) -> ObservedField[SigningLocationObservation]:
    if not entries:
        return _absent()
    if all((v or "").strip() == "" for v, _ in entries):
        obs = SigningLocationObservation(
            raw_text="",
            normalized_value="",
            city_candidates=[],
            evidence_ids=[entries[0][1]],
        )
        return ObservedField[SigningLocationObservation](
            presence="PRESENT_EMPTY",
            normalization_state="NOT_APPLICABLE",
            observations=[obs],
        )
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
    return ObservedField[SigningLocationObservation](
        presence=presence, normalization_state="VALID", observations=observations
    )


def _date_field(entries: list[tuple[str, str]]) -> ObservedField[ObservedValue[str]]:
    if not entries:
        return _absent()
    if all((r or "").strip() == "" for r, _ in entries):
        obs = ObservedValue(raw_text="", normalized_value=None, evidence_ids=[entries[0][1]])
        return ObservedField[ObservedValue[str]](
            presence="PRESENT_EMPTY",
            normalization_state="NOT_APPLICABLE",
            observations=[obs],
        )
    # 合法值按规范化后的日期合并；非法值按原始文本保留独立候选。
    valid: dict[str, dict[str, list[str]]] = {}
    invalid: dict[str, list[str]] = {}
    for raw, eid in entries:
        key = (raw or "").strip()
        if not key:
            continue
        normalized = _normalize_iso_date(key)
        if normalized is not None:
            valid.setdefault(normalized, {}).setdefault(key, []).append(eid)
        else:
            invalid.setdefault(key, []).append(eid)
    observations: list[ObservedValue[str]] = []
    for normalized in sorted(valid):
        raws = valid[normalized]
        eids = sorted({eid for group in raws.values() for eid in group})
        observations.append(
            ObservedValue(
                raw_text=sorted(raws)[0],
                normalized_value=normalized,
                evidence_ids=eids,
            )
        )
    for raw in sorted(invalid):
        observations.append(
            ObservedValue(raw_text=raw, normalized_value=None, evidence_ids=sorted(set(invalid[raw])))
        )
    if valid and invalid:
        # 合法与非法混合：不得静默按合法值判定。
        return ObservedField[ObservedValue[str]](
            presence="UNCERTAIN", normalization_state="UNCERTAIN", observations=observations
        )
    if invalid:
        return ObservedField[ObservedValue[str]](
            presence="PRESENT_VALUE", normalization_state="INVALID", observations=observations
        )
    if len(valid) > 1:
        return ObservedField[ObservedValue[str]](
            presence="UNCERTAIN", normalization_state="VALID", observations=observations
        )
    return ObservedField[ObservedValue[str]](
        presence="PRESENT_VALUE", normalization_state="VALID", observations=observations
    )


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
    for _group_key, group in sorted(raw_groups.items()):
        norm_name = (group.get("norm_name") or "").strip()
        raw_names = sorted(group["raw_names"])
        definition_evidence: list[str] = sorted(group["evidence"])
        if not norm_name:
            declared_name = ObservedField[ObservedValue[str]](
                presence="PRESENT_EMPTY",
                normalization_state="NOT_APPLICABLE",
                observations=[
                    ObservedValue(
                        raw_text="",
                        normalized_value="",
                        evidence_ids=definition_evidence[:1],
                    )
                ],
            )
        else:
            name_obs = ObservedValue(
                raw_text=raw_names[0] if raw_names else norm_name,
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
            dk = stable_key(
                "designation",
                {"party_key": group["party_key"], "kind": "CONTRACT_ROLE", "text": role},
            )
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
            dk = stable_key(
                "designation",
                {"party_key": group["party_key"], "kind": "NAME_ALIAS", "text": alias},
            )
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
                party_key=group["party_key"],
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
                # 同一 (party, designation) 只登记一次：多条证据不构成多主体。
                by_role.setdefault(des.text, []).append(
                    (party.party_key, des.designation_key, des.evidence_ids[0])
                )
    return {
        "by_name": by_name,
        "by_role": by_role,
        "designation_by_key": designation_by_key,
    }


def _mention_key(
    document_key: str,
    mention_kind: str,
    candidate_party_keys: Sequence[str],
    evidence_start: int,
    entity_coordinates: Sequence[str] = (),
) -> str:
    return stable_key(
        "mention",
        {
            "document_key": document_key,
            "mention_kind": mention_kind,
            "candidate_party_keys": list(candidate_party_keys),
            "evidence_start": evidence_start,
            "entity_coordinates": list(entity_coordinates),
        },
    )


def _assemble_single_mention(
    *,
    document_key: str,
    observed_text: str,
    explicit_name: str | None,
    role: str | None,
    structured_kind: str | None = None,
    canonical_parties: list[CanonicalParty],
    lookup: dict[str, Any],
    evidence_id: str,
    evidence_start: int,
) -> PartyMention:
    name = (explicit_name or "").strip()
    role_text = (role or "").strip()
    by_name = lookup["by_name"]
    by_role = lookup["by_role"]
    is_main = document_key == "main"
    def build(
        mention_kind: str,
        *,
        entity_coordinates: Sequence[str],
        candidate_party_keys: Sequence[str] = (),
        referenced_designation_keys: Sequence[str] = (),
        explicit_entity_name: ObservedField[ObservedValue[str]] | None = None,
        local_definition_state: str,
        comparison_state: str,
    ) -> PartyMention:
        return PartyMention(
            mention_key=_mention_key(
                document_key,
                mention_kind,
                list(candidate_party_keys),
                evidence_start,
                list(entity_coordinates),
            ),
            document_key=document_key,
            mention_kind=mention_kind,  # type: ignore[arg-type]
            observed_text=observed_text,
            referenced_designation_keys=list(referenced_designation_keys),
            explicit_entity_name=explicit_entity_name,
            candidate_party_keys=list(candidate_party_keys),
            local_definition_state=local_definition_state,  # type: ignore[arg-type]
            comparison_state=comparison_state,  # type: ignore[arg-type]
            evidence_ids=[evidence_id],
        )

    def role_reference() -> PartyMention:
        matches = by_role.get(role_text, [])
        if len(matches) == 1:
            party_key, designation_key, _eid = matches[0]
            if not is_main:
                # 附件角色引用不得借主合同 canonical 基准直接判定 MATCHED；
                # 主合同定义状态仍按角色引用语义保持 ABSENT。
                return build(
                    "ROLE_REFERENCE",
                    entity_coordinates=[role_text],
                    candidate_party_keys=[party_key],
                    referenced_designation_keys=[designation_key],
                    local_definition_state="ABSENT",
                    comparison_state="UNCERTAIN",
                )
            return build(
                "ROLE_REFERENCE",
                entity_coordinates=[role_text],
                candidate_party_keys=[party_key],
                referenced_designation_keys=[designation_key],
                local_definition_state="ABSENT",
                comparison_state="MATCHED_DECLARATION",
            )
        if len(matches) > 1:
            candidate_keys = sorted({pk for pk, _, _ in matches})
            return build(
                "ROLE_REFERENCE",
                entity_coordinates=[role_text],
                candidate_party_keys=candidate_keys,
                local_definition_state="UNCERTAIN",
                comparison_state="UNCERTAIN",
            )
        return build(
            "ROLE_REFERENCE",
            entity_coordinates=[role_text],
            local_definition_state="ABSENT",
            comparison_state="UNCERTAIN",
        )

    def appellation(designation: str, *, from_observed: bool = False) -> PartyMention:
        # 称谓引用本身不建立本地定义；定义状态不得由主合同名称匹配倒推。
        # 无结构化坐标（designation 来自裸 observed_text）时，稳定键不得嵌入展示文案。
        coordinates: list[str] = [] if from_observed else [designation]
        matched_key = by_name.get(designation)
        if matched_key is not None:
            return build(
                "PARTY_APPELLATION",
                entity_coordinates=coordinates,
                candidate_party_keys=[matched_key],
                local_definition_state="NOT_APPLICABLE" if is_main else "UNCERTAIN",
                comparison_state="MATCHED_DECLARATION",
            )
        return build(
            "PARTY_APPELLATION",
            entity_coordinates=coordinates,
            local_definition_state="NOT_APPLICABLE" if is_main else "UNCERTAIN",
            comparison_state="OUTSIDE_DECLARED_SET",
        )

    def definition() -> PartyMention:
        # PARTY_DEFINITION 必须由显式结构化类别或有组织名称+角色关系建立，
        # explicit_entity_name 只在有名称时装配；名称匹配不得倒推定义状态。
        entity_coordinates = [coord for coord in (name, role_text) if coord]
        if not entity_coordinates:
            return appellation(observed_text.strip(), from_observed=True)
        matched_key = by_name.get(name) if name else None
        return build(
            "PARTY_DEFINITION",
            entity_coordinates=entity_coordinates,
            explicit_entity_name=_plain_value_field([(name, evidence_id)]) if name else None,
            local_definition_state="PRESENT",
            comparison_state="MATCHED_DECLARATION" if matched_key else "OUTSIDE_DECLARED_SET",
        )

    if structured_kind == "ROLE_REFERENCE":
        if not role_text:
            return build(
                "ROLE_REFERENCE",
                entity_coordinates=[],
                local_definition_state="UNCERTAIN",
                comparison_state="UNCERTAIN",
            )
        return role_reference()
    if structured_kind == "PARTY_APPELLATION":
        return appellation(name or observed_text.strip(), from_observed=not name)
    if structured_kind == "PARTY_DEFINITION":
        return definition()

    # 无显式结构化类别（mention_kind=None）：绝不产出 PARTY_DEFINITION；
    # 有名称按称谓解析，仅角色按角色引用解析，其余按裸称谓（键不含展示文案）。
    if name:
        return appellation(name)
    if role_text:
        return role_reference()
    return appellation(observed_text.strip(), from_observed=True)


def _index_source_gaps(
    gaps: list[SourceGapCandidate],
    document_key: str,
    evidence: EvidenceRegistry,
) -> tuple[list[FactIssue], dict[str, str]]:
    fact_issues: list[FactIssue] = []
    quote_to_evidence: dict[str, str] = {}
    for gap in gaps:
        eid: str | None = None
        code = "SOURCE_UNREADABLE"
        if gap.quote:
            eid, issue = _locate_evidence(
                evidence, document_key, gap.quote, issue_basis=f"gap:{document_key}"
            )
            if issue is not None:
                fact_issues.append(issue)
                code = "EVIDENCE_UNLOCATABLE"
            if eid:
                quote_to_evidence[gap.quote] = eid
        fact_issues.append(_gap_issue(gap, document_key, evidence_id=eid, code=code))
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
        if candidate.document_key != document_key:
            _require_matching_document_key(candidate.document_key, document_key)
        quote = candidate.quote
        evidence_id, issue = _locate_evidence(
            evidence, document_key, quote, affected_fact_kinds=[candidate.candidate_kind]
        )
        if issue is not None:
            fact_issues.append(issue)
        if evidence_id is None:
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
            role = (candidate.party_role or "").strip()
            if party_name:
                group_key = party_name
                party_id_coords = {"declared_name": party_name}
            else:
                # 空主体分组与 party_key 只用业务坐标（文档+角色+证据位置），不依赖 candidate_ref。
                start = _evidence_start(evidence, evidence_id)
                group_key = f"empty:{role}:{start}"
                party_id_coords = {
                    "document_key": document_key,
                    "role": role,
                    "evidence_start": start,
                }
            party_key = stable_key("party", party_id_coords)
            group = canonical_groups.setdefault(
                group_key,
                {
                    "party_key": party_key,
                    "norm_name": party_name,
                    "raw_names": set(),
                    "roles": {},
                    "aliases": {},
                    "evidence": set(),
                },
            )
            group["raw_names"].add(party_name)
            group["evidence"].add(evidence_id)
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
                        "mention_kind": candidate.mention_kind,
                        "evidence_id": evidence_id,
                    },
                )

    gap_issues, _gap_quote_to_evidence = _index_source_gaps(
        envelope.source_gaps, document_key, evidence
    )
    fact_issues.extend(gap_issues)
    fact_issues = _dedupe_issues(fact_issues)

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

    mentions_by_key: dict[str, PartyMention] = {}
    for spec in sorted(mention_specs, key=lambda s: (s["evidence_id"], s["observed_text"])):
        eid = spec["evidence_id"]
        start = _evidence_start(evidence, eid)
        mention = _assemble_single_mention(
            document_key=document_key,
            observed_text=spec["observed_text"],
            explicit_name=spec["explicit_name"],
            role=spec["role"],
            structured_kind=spec["mention_kind"],
            canonical_parties=canonical_parties,
            lookup=lookup,
            evidence_id=eid,
            evidence_start=start,
        )
        _register_mention(mentions_by_key, mention)
    party_mentions = sorted(
        mentions_by_key.values(), key=lambda m: (m.evidence_ids[0], m.mention_key)
    )

    return HeaderPartiesExtraction(
        header=header,
        canonical_parties=canonical_parties,
        party_mentions=party_mentions,
        fact_issues=fact_issues,
    )


def assemble_party_mentions(
    envelope: PrepareModelEnvelope,
    canonical_parties: list[CanonicalParty],
    document: PreparedDocument,
    evidence: EvidenceRegistry,
    extraction_ranges: Sequence[MarkdownRange] | None = None,
    fact_issues: list[FactIssue] | None = None,
) -> list[PartyMention]:
    document_key = document.document_key or "main"
    output_issues = fact_issues if fact_issues is not None else []
    lookup = _build_lookup(canonical_parties)
    mentions_by_key: dict[str, PartyMention] = {}
    for candidate in envelope.candidates:
        if not isinstance(candidate, AttachmentCandidate):
            continue
        if candidate.candidate_kind != "PARTY_MENTION":
            continue
        if candidate.document_key != document_key:
            _require_matching_document_key(candidate.document_key, document_key)
        quote = candidate.quote
        observed_text = (candidate.mention_text or quote or "").strip()
        if not observed_text:
            continue
        issue_basis = (
            (candidate.party_name or "").strip()
            or (candidate.party_role or "").strip()
            or "local"
        )
        evidence_id, issue = _locate_evidence(
            evidence,
            document_key,
            quote,
            allowed_ranges=extraction_ranges,
            issue_basis=issue_basis,
            affected_fact_kinds=["PARTY_MENTION"],
        )
        if issue is not None:
            output_issues.append(issue)
        if evidence_id is None:
            continue
        start = _evidence_start(evidence, evidence_id)
        mention = _assemble_single_mention(
            document_key=document_key,
            observed_text=observed_text,
            explicit_name=candidate.party_name,
            role=candidate.party_role,
            structured_kind=candidate.mention_kind,
            canonical_parties=canonical_parties,
            lookup=lookup,
            evidence_id=evidence_id,
            evidence_start=start,
        )
        _register_mention(mentions_by_key, mention)

    gap_issues, _ = _index_source_gaps(envelope.source_gaps, document_key, evidence)
    output_issues.extend(gap_issues)
    if fact_issues is not None:
        output_issues[:] = _dedupe_issues(output_issues)

    return sorted(
        mentions_by_key.values(), key=lambda m: (m.evidence_ids[0], m.mention_key)
    )


def invoke_attachment_candidates(
    document: PreparedDocument,
    extraction_ranges: Sequence[MarkdownRange] | None = None,
) -> PrepareModelEnvelope:
    if extraction_ranges is None:
        extraction_input = "{}"
    else:
        extraction_input = json.dumps(
            {
                "extraction_ranges": [
                    {"start": start, "end": end} for start, end in extraction_ranges
                ]
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return invoke_typed_prepare_model(
        "prepare_attachment_document",
        markdown=document.markdown,
        scope_label="attachment",
        extraction_input=extraction_input,
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
    fact_issues: list[FactIssue] | None = None,
) -> list[PartyMention]:
    envelope = invoke_attachment_candidates(document, extraction_ranges=extraction_ranges)
    return assemble_party_mentions(
        envelope,
        canonical_parties,
        document,
        evidence,
        extraction_ranges=extraction_ranges,
        fact_issues=fact_issues,
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

