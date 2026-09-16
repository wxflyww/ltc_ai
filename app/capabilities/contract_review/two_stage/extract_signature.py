from __future__ import annotations

"""Task 6: signature 事实装配（保守装配 + 证据坐标稳定键版）。

装配入口契约: extract_signature_facts(documents, canonical_parties,
evidence, extraction_ranges) -> FactDomain[SignatureFacts]。模型调用经本模块
的 invoke_typed_prepare_model（便于定点 patch）。

护栏: 稳定键只用业务坐标（document_key / 证据 start-end / 块坐标 / 姓名 /
号码），绝不使用 candidate_ref、数组位置、模型展示文案（如 role_text）、opaque 证据 id
或预设配对; 父块/续页/替代关系仅由候选显式 ref 表达，多块无 ref 即失败;
人证关系仅 DIRECT / UNIQUE_IN_BLOCK / UNCERTAIN; 块外观察不伪造 block key;
附件不回填主合同; 候选引文无法定位即引用不闭合，整体失败；coverage 仅由显式、
可定位的 source_gap 驱动，技术失败不得伪装 coverage 降级。
"""

import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime

from app.capabilities.contract_review.two_stage.evidence import (
    EvidenceLocationError,
    EvidenceRegistry,
    parse_markdown_locator,
)
from app.core.errors import ModelFormatError
from app.capabilities.contract_review.two_stage.extract_header_parties import (
    PreparedDocument,
)
from app.capabilities.contract_review.two_stage.keys import stable_key
from app.capabilities.contract_review.two_stage.prepare_model import (
    PrepareModelEnvelope,
    SignatureCandidate,
    SourceGapCandidate,
    invoke_typed_prepare_model,
    NeedsConfirmationError,
)
from app.capabilities.contract_review.two_stage.schemas import (
    AlternativeSignerGroup,
    CanonicalParty,
    DocumentCoverage,
    FactDomain,
    FactIssue,
    IdentityNumberCandidate,
    ObservedField,
    ObservedValue,
    PersonIdRelation,
    SignatureBlock,
    SignatureDateObservation,
    SignatureFacts,
    SignatureFieldObservation,
    SignerCandidate,
    SignerSlot,
)

MarkdownRange = tuple[int, int]

_IRRELEVANT_ROLE_KEYWORDS = ("见证", "联系人", "项目负责人", "经办")

_ACCOUNT_KINDS = {"BANK_NAME", "BANK_ACCOUNT", "ACCOUNT_HOLDER"}
_CONTACT_KINDS = {"ADDRESS", "PHONE", "FAX", "WEBSITE", "POSTAL_CODE"}
_FIELD_VALUE_ATTR = {
    "BANK_NAME": "bank_name",
    "BANK_ACCOUNT": "bank_account",
    "ACCOUNT_HOLDER": "account_holder",
    "ADDRESS": "address",
    "PHONE": "phone",
    "FAX": "fax",
    "WEBSITE": "website",
    "POSTAL_CODE": "postal_code",
}
_SIGNATURE_FACT_KINDS = {
    "SIGNATURE_BLOCK",
    "SIGNER_NAME",
    "IDENTITY_NUMBER",
    "SIGNING_DATE",
    *_ACCOUNT_KINDS,
    *_CONTACT_KINDS,
}

_IDENTITY_PATTERN = re.compile(r"^\d{17}[0-9Xx]$")
_DATE_PATTERN = re.compile(r"^\s*(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?\s*$")


def _norm(value: str | None) -> str:
    return (value or "").strip()


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


def _unlocatable_fact_issue(
    document_key: str,
    affected_fact_kinds: Sequence[str],
) -> FactIssue:
    kinds = list(affected_fact_kinds) if affected_fact_kinds else ["UNKNOWN"]
    return FactIssue(
        fact_issue_key=_issue_key("EVIDENCE_UNLOCATABLE", "local", [document_key], kinds),
        code="EVIDENCE_UNLOCATABLE",
        message="候选引文在文档中无法唯一定位",
        related_document_keys=[document_key],
        affected_fact_kinds=kinds,
        evidence_ids=[],
    )


def _locate_quote(
    evidence: EvidenceRegistry,
    document_key: str,
    quote: str,
    allowed_ranges: Sequence[MarkdownRange] | None,
) -> tuple[str, MarkdownRange] | None:
    """定位引文并返回 (公开 evidence_id, 真实坐标); 失败返回 None。"""
    try:
        if allowed_ranges is not None:
            item = evidence.register(
                document_key=document_key,
                quote=quote,
                allowed_ranges=list(allowed_ranges),
            )
        else:
            item = evidence.register(document_key=document_key, quote=quote)
    except EvidenceLocationError:
        return None
    start, end = parse_markdown_locator(item.source_locator)
    return item.evidence_id, (start, end)


def _collect_source_gaps(
    gaps: list[SourceGapCandidate],
    document_key: str,
    evidence: EvidenceRegistry,
    allowed_ranges: Sequence[MarkdownRange] | None,
) -> list[FactIssue]:
    fact_issues: list[FactIssue] = []
    for gap in gaps:
        if gap.document_key is not None and gap.document_key != document_key:
            raise ModelFormatError(
                "source_gap 引用其它文档 "
                f"{gap.document_key} != {document_key}，来源缺口必须属于当前文档"
            )
        unknown = set(gap.affected_fact_kinds) - _SIGNATURE_FACT_KINDS
        if unknown:
            raise ModelFormatError(
                "source_gap 引用未知签章事实类别: " + ", ".join(sorted(unknown))
            )
        affected = list(gap.affected_fact_kinds)
        related = [document_key]
        if gap.quote is None:
            fact_issues.append(
                FactIssue(
                    fact_issue_key=_issue_key(
                        "SOURCE_UNREADABLE", "gap:" + document_key, related, affected
                    ),
                    code="SOURCE_UNREADABLE",
                    message=gap.message,
                    related_document_keys=related,
                    affected_fact_kinds=affected,
                    evidence_ids=[],
                )
            )
            continue
        located = _locate_quote(evidence, document_key, gap.quote, allowed_ranges)
        if located is None:
            if _locate_quote(evidence, document_key, gap.quote, None) is not None:
                raise ModelFormatError(
                    "source_gap 引文位于 extraction_ranges 授权窗口之外，"
                    "不得伪装可定位缺口，按技术失败处理"
                )
            fact_issues.append(_unlocatable_fact_issue(document_key, affected))
            continue
        evidence_id, (start, end) = located
        fact_issues.append(
            FactIssue(
                fact_issue_key=_issue_key(
                    "SOURCE_UNREADABLE",
                    f"gap:{document_key}:{start}:{end}",
                    related,
                    affected,
                ),
                code="SOURCE_UNREADABLE",
                message=gap.message,
                related_document_keys=related,
                affected_fact_kinds=affected,
                evidence_ids=[evidence_id],
            )
        )
    return fact_issues


def _party_index(canonical_parties: Sequence[CanonicalParty]) -> dict[str, list[str]]:
    """主体名 -> 全部 canonical party_key；同名多主体不得择首丢弃。"""
    index: dict[str, list[str]] = {}
    for party in canonical_parties:
        for observation in party.declared_name.observations:
            for value in (observation.raw_text, observation.normalized_value):
                name = _norm(value)
                if name:
                    keys = index.setdefault(name, [])
                    if party.party_key not in keys:
                        keys.append(party.party_key)
    return index


def _resolve_party_binding(
    party_name: str | None,
    party_index: Mapping[str, list[str]],
    quotes: Sequence[str],
) -> tuple[str, str | None, list[str]]:
    """主体绑定只在已定位引文直接支持时成立；同名多主体 UNCERTAIN 保留全部候选。"""
    name = _norm(party_name)
    keys = list(party_index.get(name, [])) if name else []
    supported = bool(name) and any(name in quote for quote in quotes)
    if not (keys and supported):
        return "UNBOUND", None, []
    if len(keys) == 1:
        return "BOUND", keys[0], [keys[0]]
    return "UNCERTAIN", None, list(keys)


def _invoke_signature_document(
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
        "prepare_signature_document",
        markdown=document.markdown,
        scope_label="main" if document.document_key == "main" else "attachment",
        extraction_input=extraction_input,
    )


class _BlockAcc:
    def __init__(self, key: str, document_key: str, party_name: str | None) -> None:
        self.key = key
        self.document_key = document_key
        self.party_name = party_name
        self.evidence_ids: list[str] = []
        self.quotes: list[str] = []


class _SlotAcc:
    def __init__(self, key: str, block_key: str, role_text: str, alternative: bool) -> None:
        self.key = key
        self.block_key = block_key
        self.role_text = role_text
        self.alternative = alternative
        self.evidence_ids: list[str] = []
        self.signer_names: dict[str, list[str]] = {}


def _resolve_block(
    blocks: Sequence[_BlockAcc],
    ref_to_block: dict[str, _BlockAcc],
    block_ref: str | None,
    party_name: str | None,
    what: str,
) -> _BlockAcc:
    """子候选归属: 显式 ref 优先; 单块无歧义其次; 主体名唯一匹配再次; 否则失败。

    禁止按数组位置、距离或预设配对猜测归属; ref 悬空按引用不闭合整体失败。
    """
    if block_ref is not None:
        block = ref_to_block.get(block_ref)
        if block is None:
            raise ModelFormatError(
                what + " 候选的 block_ref/continues_ref 指向不存在的候选，引用不闭合"
            )
        return block
    if len(blocks) == 1:
        return blocks[0]
    name = _norm(party_name)
    if name:
        matched = [b for b in blocks if b.party_name == name]
        if len(matched) == 1:
            return matched[0]
    if not blocks:
        raise ModelFormatError(what + " 候选缺少签章块，引用不闭合，按格式错误失败")
    raise ModelFormatError(what + " 候选无法在多个签章块中确定归属，禁止预设配对")


def _raise_if_block_ref_conflicts(
    block: _BlockAcc,
    quote: str,
    blocks: Sequence[_BlockAcc],
    party_index: Mapping[str, list[str]],
) -> None:
    """显式 block_ref 指向的块与引文携带的其它块可验证主体证据冲突 => 引用不闭合。

    仅当另一签章块的主体名既出现在候选已定位引文中、又属于 canonical 主体时触发；
    防止按 block_ref 静默吸收与已定位证据矛盾的归属。
    """
    for other in blocks:
        name = _norm(other.party_name)
        if other.key != block.key and name and name in party_index and name in quote:
            raise ModelFormatError(
                "候选 block_ref 指向的签章块与引文携带的其它块可验证主体证据冲突，"
                "引用不闭合，禁止按 ref 静默装配"
            )


def _block_models(
    blocks: Sequence[_BlockAcc],
    party_index: Mapping[str, list[str]],
) -> list[SignatureBlock]:
    models: list[SignatureBlock] = []
    for block in blocks:
        binding, resolved_key, candidate_keys = _resolve_party_binding(
            block.party_name, party_index, block.quotes
        )
        if block.party_name:
            local_name = ObservedField(
                presence="PRESENT_VALUE",
                normalization_state="VALID",
                observations=[
                    ObservedValue(
                        raw_text=block.party_name,
                        normalized_value=block.party_name,
                        evidence_ids=sorted(block.evidence_ids),
                    )
                ],
            )
        else:
            local_name = ObservedField(
                presence="ABSENT",
                normalization_state="NOT_APPLICABLE",
                observations=[],
            )
        models.append(
            SignatureBlock(
                signature_block_key=block.key,
                document_key=block.document_key,
                party_binding_state=binding,
                party_key=resolved_key,
                candidate_party_keys=candidate_keys,
                local_company_name=local_name,
                evidence_ids=sorted(block.evidence_ids),
            )
        )
    return models

def _assemble_document(
    envelope: PrepareModelEnvelope,
    document: PreparedDocument,
    party_index: Mapping[str, list[str]],
    evidence: EvidenceRegistry,
    allowed_ranges: Sequence[MarkdownRange] | None,
) -> tuple[SignatureFacts, list[FactIssue]]:
    document_key = document.document_key
    fact_issues: list[FactIssue] = []

    # ---- 证据定位：不可定位候选=引用不闭合整体失败；错文档候选整体失败 ----
    located: list[tuple[SignatureCandidate, str, MarkdownRange]] = []
    for candidate in envelope.candidates:
        if candidate.document_key != document_key:
            raise ModelFormatError(
                "候选 document_key 与当前处理文档不一致: "
                f"{candidate.document_key} != {document_key}"
            )
        found = _locate_quote(evidence, document_key, candidate.quote, allowed_ranges)
        if found is None:
            raise ModelFormatError(
                "候选引文在文档 "
                + document_key
                + " 中无法唯一定位，属引用不闭合，整体失败，不得降级为 coverage"
            )
        evidence_id, span = found
        located.append((candidate, evidence_id, span))

    # ---- 签章块：每个主 SIGNATURE_BLOCK 候选独立成块；continues_ref 并入主块 ----
    primary_specs: dict[str, tuple[SignatureCandidate, str, MarkdownRange]] = {}
    continuations: list[tuple[SignatureCandidate, str, MarkdownRange, str]] = []
    children: list[tuple[SignatureCandidate, str, MarkdownRange]] = []
    for candidate, evidence_id, span in located:
        if candidate.candidate_kind != "SIGNATURE_BLOCK":
            children.append((candidate, evidence_id, span))
            continue
        ref = _norm(candidate.continues_ref) or None
        if ref is None:
            primary_specs[candidate.candidate_ref] = (candidate, evidence_id, span)
        else:
            continuations.append((candidate, evidence_id, span, ref))

    blocks: list[_BlockAcc] = []
    ref_to_block: dict[str, _BlockAcc] = {}
    for ref in sorted(primary_specs):
        block_candidate, evidence_id, span = primary_specs[ref]
        block = _BlockAcc(
            stable_key(
                "signature_block",
                {"document_key": document_key, "start": span[0], "end": span[1]},
            ),
            document_key,
            _norm(block_candidate.party_name) or None,
        )
        block.evidence_ids.append(evidence_id)
        block.quotes.append(block_candidate.quote)
        blocks.append(block)
        ref_to_block[ref] = block
    for candidate, evidence_id, _span, ref in sorted(continuations, key=lambda x: x[0].candidate_ref):
        block = ref_to_block.get(ref)
        if block is None:
            raise ModelFormatError(
                "SIGNATURE_BLOCK 续页候选的 continues_ref 指向不存在的候选，引用不闭合"
            )
        if evidence_id not in block.evidence_ids:
            block.evidence_ids.append(evidence_id)
        block.quotes.append(candidate.quote)
        ref_to_block[candidate.candidate_ref] = block
    block_by_key = {b.key: b for b in blocks}

    # ---- 栏位：SIGNER_NAME 归属仅由显式 ref 或无歧义解析；替代组仅由 ref 表达 ----
    slot_specs: dict[
        tuple[str, str], list[tuple[SignatureCandidate, str, MarkdownRange]]
    ] = {}
    for candidate, evidence_id, span in children:
        if candidate.candidate_kind != "SIGNER_NAME":
            continue
        block_ref = _norm(candidate.block_ref) or None
        block = _resolve_block(
            blocks,
            ref_to_block,
            block_ref,
            candidate.party_name,
            "signer_name",
        )
        if block_ref is not None:
            _raise_if_block_ref_conflicts(block, candidate.quote, blocks, party_index)
        role_text = _norm(candidate.role_text) or "UNSPECIFIED"
        slot_specs.setdefault((block.key, role_text), []).append(
            (candidate, evidence_id, span)
        )

    slots: list[_SlotAcc] = []
    slots_by_block: dict[str, list[_SlotAcc]] = {}
    ref_to_slot: dict[str, _SlotAcc] = {}
    for (block_key, role_text), members in sorted(slot_specs.items()):
        spans = sorted({span for _c, _e, span in members})
        # 同角色栏位若分布在多个可定位坐标：现有可靠证据无法唯一证明是"一栏一人
        # 多处提及"还是"多个独立栏位"，属结构歧义，一律停止自动装配；姓名相同
        # 不构成合并依据。同一坐标（同一处引文）的一栏多人不受影响。未出现在
        # 已定位引文中的 party_name 字段声称不构成证据，不参与本判定。
        if len(spans) > 1:
            raise NeedsConfirmationError(
                "同一签章块内同角色栏位分布在不同证据坐标且无法证明为同一栏位，"
                "不能唯一解释为一栏多人或多个独立栏位，停止自动装配"
            )
        slot = _SlotAcc(
            stable_key(
                "signer_slot",
                {
                    "document_key": document_key,
                    "block_key": block_key,
                    "spans": spans,
                },
            ),
            block_key,
            role_text,
            any(_norm(c.alternative_of_ref) for c, _e, _s in members),
        )
        slots.append(slot)
        slots_by_block.setdefault(block_key, []).append(slot)
        for cand, eid, _s in members:
            if eid not in slot.evidence_ids:
                slot.evidence_ids.append(eid)
            name = _norm(cand.signer_name)
            if name:
                bucket = slot.signer_names.setdefault(name, [])
                if eid not in bucket:
                    bucket.append(eid)
        for cand, _eid, _s in members:
            ref_to_slot[cand.candidate_ref] = slot
    slot_by_key = {s.key: s for s in slots}

    signers: list[SignerCandidate] = []
    signer_keys_by_slot: dict[str, list[str]] = {}
    signer_by_name: dict[str, list[tuple[str, str]]] = {}
    for slot in slots:
        for name, slot_evidence_ids in sorted(slot.signer_names.items()):
            signer_key = stable_key("signer", {"slot_key": slot.key, "name": name})
            signers.append(
                SignerCandidate(
                    signer_key=signer_key,
                    signer_slot_key=slot.key,
                    raw_name=name,
                    normalized_name=name,
                    evidence_ids=sorted(slot_evidence_ids),
                )
            )
            signer_keys_by_slot.setdefault(slot.key, []).append(signer_key)
            signer_by_name.setdefault(name, []).append((signer_key, slot.key))

    slot_models: list[SignerSlot] = []
    for slot in slots:
        slot_models.append(
            SignerSlot(
                signer_slot_key=slot.key,
                signature_block_key=slot.block_key,
                role_text=slot.role_text,
                role_state=(
                    "IRRELEVANT_PERSON"
                    if any(k in slot.role_text for k in _IRRELEVANT_ROLE_KEYWORDS)
                    else "ELIGIBLE_SIGNER"
                ),
                presence="PRESENT_VALUE" if slot.signer_names else "PRESENT_EMPTY",
                signer_keys=list(signer_keys_by_slot.get(slot.key, [])),
                identity_number_keys=[],
                evidence_ids=sorted(slot.evidence_ids),
            )
        )

    # ---- 替代组：仅由 alternative_of_ref 结构表达，不按文本或位置猜测 ----
    evidence_by_slot = {slot.key: slot.evidence_ids for slot in slots}
    grouped: set[frozenset[str]] = set()
    group_models: list[AlternativeSignerGroup] = []
    for candidate, _evidence_id, _span in children:
        if candidate.candidate_kind != "SIGNER_NAME":
            continue
        ref = _norm(candidate.alternative_of_ref) or None
        if ref is None:
            continue
        if ref == candidate.candidate_ref:
            raise ModelFormatError(
                "SIGNER_NAME 替代候选的 alternative_of_ref 指向自身，引用不闭合"
            )
        own_slot = ref_to_slot.get(candidate.candidate_ref)
        target_slot = ref_to_slot.get(ref)
        if target_slot is None:
            raise ModelFormatError(
                "SIGNER_NAME 替代候选的 alternative_of_ref 指向不存在的候选，引用不闭合"
            )
        if own_slot is None:
            continue
        if target_slot.key == own_slot.key:
            raise ModelFormatError(
                "SIGNER_NAME 替代候选的 alternative_of_ref 与自身归属同一栏位，替代关系不成立"
            )
        if target_slot.block_key != own_slot.block_key:
            raise ModelFormatError(
                "SIGNER_NAME 替代候选的 alternative_of_ref 指向另一签章块的栏位，"
                "跨块替代关系不成立，引用不闭合"
            )
        member = frozenset({target_slot.key, own_slot.key})
        if member in grouped:
            continue
        grouped.add(member)
        group_models.append(
            AlternativeSignerGroup(
                signer_group_key=stable_key("signer_group", {"members": sorted(member)}),
                signer_slot_keys=sorted(member),
                relation_state="CONFIRMED",
                evidence_ids=sorted(
                    {e for k in member for e in evidence_by_slot.get(k, [])}
                ),
            )
        )

    # ---- 证件号：显式姓名唯一命中 signer 才绑定 slot；归属解析禁止猜测 ----
    identities_by_key: dict[str, IdentityNumberCandidate] = {}
    identity_block: dict[str, str] = {}
    explicit_relations: list[tuple[str, str, str]] = []
    for candidate, evidence_id, _span in children:
        if candidate.candidate_kind != "IDENTITY_NUMBER":
            continue
        number = _norm(candidate.identity_number) or _norm(candidate.quote)
        valid = bool(_IDENTITY_PATTERN.match(number))
        canonical_number = number.upper() if valid else number
        slot_key: str | None = None
        explicit_name = _norm(candidate.signer_name)
        # 姓名-号码关系必须由已定位引文直接支持；仅模型字段声称 signer_name
        # 而引文不含该姓名时，不得据此绑定 slot 或升级为 DIRECT。
        name_supported = bool(explicit_name) and explicit_name in candidate.quote
        claimed_slot_key: str | None = None
        if explicit_name:
            owners = list(
                dict.fromkeys(sk for _, sk in signer_by_name.get(explicit_name, []))
            )
            if len(owners) == 1:
                claimed_slot_key = owners[0]
        ref = _norm(candidate.block_ref) or None
        # 显式 block_ref 与 signer_name 声称的归属块冲突即引用不闭合；该结构化
        # 冲突判定不因姓名未被引文支持而豁免（结构归属与模型归属自相矛盾）。
        if claimed_slot_key is not None and ref is not None:
            claimed_block = block_by_key[slot_by_key[claimed_slot_key].block_key]
            named_block = ref_to_block.get(ref)
            if named_block is None:
                raise ModelFormatError(
                    "identity_number 候选的 block_ref 指向不存在的候选，引用不闭合"
                )
            if named_block.key != claimed_block.key:
                raise ModelFormatError(
                    "identity_number 候选的 signer_name 归属块与 block_ref 冲突，"
                    "引用不闭合，禁止择一吸收"
                )
        if name_supported and claimed_slot_key is not None:
            slot_key = claimed_slot_key
            block = block_by_key[slot_by_key[slot_key].block_key]
        else:
            block = _resolve_block(
                blocks,
                ref_to_block,
                ref,
                candidate.party_name,
                "identity_number",
            )
        key = stable_key("identity_number", {"block_key": block.key, "number": canonical_number})
        existing = identities_by_key.get(key)
        if existing is None:
            identities_by_key[key] = IdentityNumberCandidate(
                identity_number_key=key,
                signer_slot_key=slot_key,
                raw_text=number,
                normalized_value=number.upper() if valid else None,
                normalization_state="VALID" if valid else "UNCERTAIN",
                evidence_ids=[evidence_id],
            )
            identity_block[key] = block.key
        else:
            if evidence_id not in existing.evidence_ids:
                existing.evidence_ids.append(evidence_id)
                existing.evidence_ids.sort()
            if slot_key is not None and existing.signer_slot_key is None:
                existing.signer_slot_key = slot_key
        if name_supported and slot_key is not None:
            for signer_key, owner_slot in signer_by_name[explicit_name]:
                if owner_slot == slot_key:
                    explicit_relations.append((signer_key, key, evidence_id))
    identities = list(identities_by_key.values())

    relations: list[PersonIdRelation] = []
    related_pairs: set[tuple[str, str]] = set()
    signer_model_by_key = {s.signer_key: s for s in signers}
    for signer_key, identity_key, id_evidence_id in explicit_relations:
        if (signer_key, identity_key) in related_pairs:
            continue
        related_pairs.add((signer_key, identity_key))
        signer_model = signer_model_by_key[signer_key]
        relations.append(
            PersonIdRelation(
                signer_key=signer_key,
                identity_number_key=identity_key,
                association_state="DIRECT",
                evidence_ids=sorted(set(signer_model.evidence_ids) | {id_evidence_id}),
            )
        )
        for slot_model in slot_models:
            if slot_model.signer_slot_key == signer_model.signer_slot_key:
                if identity_key not in slot_model.identity_number_keys:
                    slot_model.identity_number_keys.append(identity_key)

    # ---- 块内未绑定号码：0/1/N 全保留；唯一=UNIQUE_IN_BLOCK，歧义=UNCERTAIN 叉乘 ----
    explicit_identity_keys = {pair[1] for pair in related_pairs}
    for block in blocks:
        block_slots = [s for s in slot_models if s.signature_block_key == block.key]
        eligible_slot_keys = {
            s.signer_slot_key for s in block_slots if s.role_state == "ELIGIBLE_SIGNER"
        }
        eligible_signers = [s for s in signers if s.signer_slot_key in eligible_slot_keys]
        unbound_ids = [
            i
            for i in identities
            if identity_block[i.identity_number_key] == block.key
            and i.signer_slot_key is None
            and i.identity_number_key not in explicit_identity_keys
        ]
        if not unbound_ids or not eligible_signers:
            continue
        state = (
            "UNIQUE_IN_BLOCK"
            if len(eligible_signers) == 1 and len(unbound_ids) == 1
            else "UNCERTAIN"
        )
        for signer_model in eligible_signers:
            for id_model in unbound_ids:
                pair = (signer_model.signer_key, id_model.identity_number_key)
                if pair in related_pairs:
                    continue
                related_pairs.add(pair)
                relations.append(
                    PersonIdRelation(
                        signer_key=pair[0],
                        identity_number_key=pair[1],
                        association_state=state,
                        evidence_ids=sorted(
                            set(signer_model.evidence_ids) | set(id_model.evidence_ids)
                        ),
                    )
                )

    # ---- 签署日期：引用真实块 key；键用文档+证据坐标，不含展示文案 ----
    dates: list[SignatureDateObservation] = []
    for candidate, evidence_id, span in children:
        if candidate.candidate_kind != "SIGNING_DATE":
            continue
        block = _resolve_block(
            blocks,
            ref_to_block,
            _norm(candidate.block_ref) or None,
            candidate.party_name,
            "signing_date",
        )
        raw = _norm(candidate.signing_date) or _norm(candidate.quote)
        normalized: str | None = None
        state = "UNCERTAIN"
        match = _DATE_PATTERN.match(raw)
        if match:
            try:
                parsed = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                parsed = None
            if parsed is not None:
                normalized = parsed.strftime("%Y-%m-%d")
                state = "VALID"
        dates.append(
            SignatureDateObservation(
                signature_date_key=stable_key(
                    "signature_date",
                    {
                        "block_key": block.key,
                        "document_key": document_key,
                        "start": span[0],
                        "end": span[1],
                    },
                ),
                signature_block_key=block.key,
                party_key=None,
                field=ObservedField(
                    presence="PRESENT_VALUE",
                    normalization_state=state,
                    observations=[
                        ObservedValue(
                            raw_text=raw,
                            normalized_value=normalized,
                            evidence_ids=[evidence_id],
                        )
                    ],
                ),
            )
        )

    # ---- 账户/联系观察：block_ref 必须真实；BOUND/CONFIRMED 需引文关系证据 ----
    accounts: list[SignatureFieldObservation] = []
    contacts: list[SignatureFieldObservation] = []
    for candidate, evidence_id, span in children:
        kind = candidate.candidate_kind
        if kind not in _ACCOUNT_KINDS and kind not in _CONTACT_KINDS:
            continue
        value = _norm(getattr(candidate, _FIELD_VALUE_ATTR[kind])) or _norm(candidate.quote)
        block_ref = _norm(candidate.block_ref) or None
        resolved_block_key: str | None = None
        if block_ref is not None:
            ref_block = ref_to_block.get(block_ref)
            if ref_block is None:
                raise ModelFormatError(
                    kind + " 观察候选的 block_ref 指向不存在的签章块，引用不闭合"
                )
            _raise_if_block_ref_conflicts(ref_block, candidate.quote, blocks, party_index)
            resolved_block_key = ref_block.key
        binding, party_key, candidate_keys = _resolve_party_binding(
            candidate.party_name, party_index, [candidate.quote]
        )
        purpose = _norm(candidate.purpose_text) or None
        if purpose is not None and purpose not in candidate.quote:
            purpose = None
        purpose_state = "CONFIRMED" if purpose else "UNCERTAIN"
        observation = SignatureFieldObservation(
            field_observation_key=stable_key(
                "signature_field_observation",
                {
                    "document_key": document_key,
                    "field_kind": kind,
                    "start": span[0],
                    "end": span[1],
                },
            ),
            document_key=document_key,
            signature_block_key=resolved_block_key,
            party_binding_state=binding,
            party_key=party_key,
            candidate_party_keys=candidate_keys,
            field_kind=kind,
            purpose_state=purpose_state,
            purpose_text=purpose,
            field=ObservedField(
                presence="PRESENT_VALUE",
                normalization_state="VALID",
                observations=[
                    ObservedValue(
                        raw_text=value,
                        normalized_value=value,
                        evidence_ids=[evidence_id],
                    )
                ],
            ),
        )
        (accounts if kind in _ACCOUNT_KINDS else contacts).append(observation)

    fact_issues.extend(
        _collect_source_gaps(envelope.source_gaps, document_key, evidence, allowed_ranges)
    )

    data = SignatureFacts(
        signature_blocks=_block_models(blocks, party_index),
        signer_slots=slot_models,
        alternative_signer_groups=group_models,
        signer_candidates=signers,
        identity_number_candidates=identities,
        person_id_relations=relations,
        signing_date_observations=dates,
        account_observations=accounts,
        contact_observations=contacts,
    )
    facts_count = sum(len(getattr(data, name)) for name in _LIST_FIELDS)
    return data, fact_issues, facts_count


_LIST_FIELDS = (
    "signature_blocks",
    "signer_slots",
    "alternative_signer_groups",
    "signer_candidates",
    "identity_number_candidates",
    "person_id_relations",
    "signing_date_observations",
    "account_observations",
    "contact_observations",
)
_RELATION_SORT = ("signer_key", "identity_number_key")
_LIST_SORT_KEYS = {
    "signature_blocks": ("signature_block_key",),
    "signer_slots": ("signer_slot_key",),
    "alternative_signer_groups": ("signer_group_key",),
    "signer_candidates": ("signer_key",),
    "identity_number_candidates": ("identity_number_key",),
    "person_id_relations": _RELATION_SORT,
    "signing_date_observations": ("signature_date_key",),
    "account_observations": ("field_observation_key",),
    "contact_observations": ("field_observation_key",),
}


def extract_signature_facts(
    documents: Sequence[PreparedDocument],
    canonical_parties: Sequence[CanonicalParty],
    evidence: EvidenceRegistry,
    extraction_ranges: dict[str, list[MarkdownRange]] | None = None,
) -> FactDomain[SignatureFacts]:
    """逐文档独立调用与装配；附件不回填主合同；coverage 逐文档降级。"""
    party_index = _party_index(canonical_parties)
    lists: dict[str, list] = {name: [] for name in _LIST_FIELDS}
    all_issues: dict[str, FactIssue] = {}
    coverage: list[DocumentCoverage] = []

    for document in documents:
        document_key = document.document_key
        ranges = extraction_ranges.get(document_key) if extraction_ranges else None
        envelope = _invoke_signature_document(document, extraction_ranges=ranges)
        data, issues, _facts_count = _assemble_document(
            envelope, document, party_index, evidence, ranges
        )
        for name in _LIST_FIELDS:
            lists[name].extend(getattr(data, name))
        for issue in issues:
            all_issues.setdefault(issue.fact_issue_key, issue)
        doc_issues = [i for i in issues if document_key in i.related_document_keys]
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
            _SIGNATURE_FACT_KINDS.intersection(
                {kind for i in doc_issues for kind in i.affected_fact_kinds}
            )
        ) or ["SIGNATURE_BLOCK"]
        # 汇总当前文档全部显式、可定位 source_gap（SOURCE_UNREADABLE）的受影响
        # 类别并集；并集覆盖全部适用签章类别才 UNAVAILABLE，否则 PARTIAL。
        # 不可定位候选（EVIDENCE_UNLOCATABLE）不属来源缺口，不参与该判定。
        locatable_kinds: set[str] = set()
        for issue in doc_issues:
            if issue.code != "EVIDENCE_UNLOCATABLE":
                locatable_kinds |= set(issue.affected_fact_kinds)
        state = (
            "UNAVAILABLE" if _SIGNATURE_FACT_KINDS <= locatable_kinds else "PARTIAL"
        )
        coverage.append(
            DocumentCoverage(
                document_key=document_key,
                state=state,
                affected_fact_kinds=affected,
                fact_issue_keys=sorted({i.fact_issue_key for i in doc_issues}),
            )
        )

    merged = SignatureFacts(
        **{
            name: sorted(
                lists[name],
                key=lambda item, _keys=_LIST_SORT_KEYS[name]: tuple(
                    getattr(item, attr) for attr in _keys
                ),
            )
            for name in _LIST_FIELDS
        }
    )
    coverage.sort(key=lambda c: c.document_key)
    states = {c.state for c in coverage}
    if states == {"COMPLETE"}:
        domain_state = "COMPLETE"
    elif states == {"UNAVAILABLE"}:
        domain_state = "UNAVAILABLE"
    else:
        domain_state = "PARTIAL"
    issues_list = sorted(all_issues.values(), key=lambda i: i.fact_issue_key)
    return FactDomain(
        state=domain_state,
        coverage=coverage,
        data=merged,
        issues=issues_list if domain_state != "COMPLETE" else [],
    )
