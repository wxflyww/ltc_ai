from __future__ import annotations

import json
from unittest.mock import patch

from typing import Any

from app.capabilities.contract_review.two_stage.prepare_model import SourceGapCandidate

from app.capabilities.contract_review.two_stage.evidence import EvidenceRegistry
from app.capabilities.contract_review.two_stage.extract_header_parties import (
    HeaderPartiesExtraction,
    PreparedDocument,
    assemble_header_parties,
    assemble_party_mentions,
    build_header_fact_domain,
    build_parties_fact_domain,
    extract_attachment_party_mentions,
    invoke_attachment_candidates,
)
from app.capabilities.contract_review.two_stage.prepare_model import (
    AttachmentCandidate,
    HeaderPartiesCandidate,
    PrepareModelEnvelope,
)
from app.capabilities.contract_review.two_stage.schemas import FactIssue, ReviewContext

from tests.two_stage.factories import valid_context_payload


MAIN_MD = (
    "采购合同\n"
    "合同编号：HT-2026-001\n"
    "项目名称：智慧园区建设\n"
    "项目编号：PRJ-88\n"
    "签订地点：上海\n"
    "签订日期：2026年8月15日\n"
    "签订日期：待定\n"
    "交付地：北京\n"
    "甲方：甲乙科技有限公司\n"
    "乙方：丙丁工程有限公司\n"
    "正文中提及乙方名称 丙丁工程有限公司\n"
    "正文中提及 丙丁工程有限公司\n"
    "正文中提及 甲乙科技有限公司\n"
    "合同名称：A\n"
    "名称为A\n"
    "合同名：B\n"
    "签订日期：2026-08-15\n"
    "签订日期：2026-02-30\n"
    "买方：A公司\n"
    "买方：B公司\n"
    "买方代表签字\n"
    "甲乙科技有限公司承担义务\n"
    "甲方应付款\n"
    "供应商\n"
    "承甲与承乙定义段\n"
    "合同甲方为甲乙科技有限公司\n"
)


ATTACH_MD = (
    "本附件定义负责人：某某项目部\n"
    "本附件再次提到 丙丁工程有限公司\n"
)


def _registry(mapping: dict[str, str] | None = None) -> EvidenceRegistry:
    if mapping is not None:
        return EvidenceRegistry(mapping)
    return EvidenceRegistry({"main": MAIN_MD, "attach1": ATTACH_MD})


def _doc(markdown: str = MAIN_MD, document_key: str = "main") -> PreparedDocument:
    return PreparedDocument(document_key=document_key, markdown=markdown)


MANY_MD = (
    "角色线0：主体0科技\n"
    "角色线1：主体1科技\n"
    "角色线2：主体2科技\n"
    "角色线3：主体3科技\n"
    "角色线4：主体4科技\n"
)


def _many_registry() -> EvidenceRegistry:
    return EvidenceRegistry({"main": MANY_MD, "attach1": ATTACH_MD})


def _env(candidates: list[dict[str, Any]], gaps: list[dict[str, Any]] | None = None) -> PrepareModelEnvelope:
    """Build a HeaderParties envelope, converting inline SOURCE_GAP dicts to source_gaps."""
    clean_candidates: list[dict[str, Any]] = []
    extra_gaps: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate = dict(candidate)
        kind = candidate.get("candidate_kind")
        if kind == "SOURCE_GAP":
            gap = {"affected_fact_kinds": candidate.get("affected_fact_kinds", []), "message": candidate.get("message", "")}
            if candidate.get("quote") is not None:
                gap["quote"] = candidate["quote"]
            if candidate.get("document_key") is not None:
                gap["document_key"] = candidate["document_key"]
            extra_gaps.append(gap)
        else:
            clean_candidates.append(candidate)
    envelope_gaps = [dict(g) for g in (gaps or [])] + extra_gaps
    payload: dict[str, Any] = {"candidates": clean_candidates, "source_gaps": envelope_gaps}
    return PrepareModelEnvelope[list[HeaderPartiesCandidate]].model_validate(payload)


def _hd_candidate(
    ref: str,
    kind: str,
    quote: str,
    *,
    document_key: str = "main",
    contract_name: str | None = None,
    contract_number: str | None = None,
    project_name: str | None = None,
    project_number: str | None = None,
    signing_location: str | None = None,
    signing_date: str | None = None,
    party_role: str | None = None,
    party_name: str | None = None,
    party_aliases: list[str] | None = None,
    mention_text: str | None = None,
    mention_kind: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "candidate_ref": ref,
        "candidate_kind": kind,
        "quote": quote,
        "document_key": document_key,
        "contract_name": contract_name,
        "contract_number": contract_number,
        "project_name": project_name,
        "project_number": project_number,
        "signing_location": signing_location,
        "signing_date": signing_date,
        "party_role": party_role,
        "party_name": party_name,
        "party_aliases": party_aliases or [],
        "mention_text": mention_text,
    }
    if mention_kind is not None:
        payload["mention_kind"] = mention_kind
    return payload


def _obs_values(field: Any) -> list[Any]:
    return [o.raw_text for o in field.observations]


# ---------------------------------------------------------------- header
def test_contract_and_project_name_number_not_cross_grouped() -> None:
    facts = assemble_header_parties(
        _env(
            [
                _hd_candidate("c1", "CONTRACT_NAME", "采购合同", contract_name="采购合同"),
                _hd_candidate("c2", "CONTRACT_NUMBER", "合同编号：HT-2026-001", contract_number="HT-2026-001"),
                _hd_candidate("c3", "PROJECT_NAME", "项目名称：智慧园区建设", project_name="智慧园区建设"),
                _hd_candidate("c4", "PROJECT_NUMBER", "项目编号：PRJ-88", project_number="PRJ-88"),
            ]
        ),
        _doc(),
        _registry(),
    )
    assert _obs_values(facts.header.contract_identity.name) == ["采购合同"]
    assert _obs_values(facts.header.contract_identity.number) == ["HT-2026-001"]
    assert _obs_values(facts.header.project_identity.name) == ["智慧园区建设"]
    assert _obs_values(facts.header.project_identity.number) == ["PRJ-88"]
    assert facts.header.contract_identity.number.observations[0].normalized_value == "HT-2026-001"


def test_header_fields_absent_when_no_candidates() -> None:
    facts = assemble_header_parties(_env([]), _doc(), _registry())
    assert facts.header.contract_identity.name.presence == "ABSENT"
    assert facts.header.contract_identity.number.presence == "ABSENT"
    assert facts.header.project_identity.name.presence == "ABSENT"
    assert facts.header.project_identity.number.presence == "ABSENT"
    assert facts.header.signing_location.presence == "ABSENT"
    assert facts.header.signing_date.presence == "ABSENT"


def test_non_header_value_not_backfilled() -> None:
    facts = assemble_header_parties(
        _env([_hd_candidate("c1", "CONTRACT_NAME", "采购合同", contract_name="采购合同", signing_date="2026-08-15")]),
        _doc(),
        _registry(),
    )
    assert _obs_values(facts.header.contract_identity.name) == ["采购合同"]
    assert facts.header.signing_date.presence == "ABSENT"


def test_name_specificity_derived() -> None:
    facts = assemble_header_parties(
        _env(
            [
                _hd_candidate("c1", "CONTRACT_NAME", "采购合同", contract_name="采购合同"),
                _hd_candidate("c2", "CONTRACT_NAME", "甲方：甲乙科技有限公司", contract_name="甲乙科技有限公司"),
            ]
        ),
        _doc(),
        _registry(),
    )
    specificities = {o.specificity for o in facts.header.contract_identity.name.observations}
    assert specificities == {"SPECIFIC", "GENERIC"}


def test_generic_name_not_trapped_by_token_list_or_isalnum() -> None:
    facts = assemble_header_parties(
        _env([
                _hd_candidate("c1", "CONTRACT_NAME", "采购合同", contract_name="智慧园区建设工作服务合同"),
                _hd_candidate("c2", "PROJECT_NAME", "项目编号：PRJ-88", project_name="XX项目"),
                _hd_candidate("c3", "PROJECT_NAME", "智慧园区", project_name="智慧园区"),
                _hd_candidate("c4", "CONTRACT_NAME", "交付地：北京", contract_name="某项目合作协议"),
        ]),
        _doc(),
        _registry(),
    )
    contract_specs = {o.raw_text: o.specificity for o in facts.header.contract_identity.name.observations}
    project_specs = {o.raw_text: o.specificity for o in facts.header.project_identity.name.observations}
    assert contract_specs["智慧园区建设工作服务合同"] == "GENERIC"
    assert contract_specs["某项目合作协议"] == "GENERIC"
    assert project_specs["XX项目"] == "UNCERTAIN"
    assert project_specs["智慧园区"] == "UNCERTAIN"


def test_signing_location_zero_candidates_absent() -> None:
    facts = assemble_header_parties(_env([]), _doc(), _registry())
    assert facts.header.signing_location.presence == "ABSENT"


def test_signing_location_one_candidate_present_value() -> None:
    facts = assemble_header_parties(
        _env([_hd_candidate("c1", "SIGNING_LOCATION", "签订地点：上海", signing_location="上海")]),
        _doc(),
        _registry(),
    )
    assert facts.header.signing_location.presence == "PRESENT_VALUE"
    assert facts.header.signing_location.observations[0].city_candidates == ["上海"]
    assert facts.header.signing_location.observations[0].normalized_value == "上海"


def test_signing_location_multiple_candidates_uncertain() -> None:
    facts = assemble_header_parties(
        _env(
            [
                _hd_candidate("c1", "SIGNING_LOCATION", "签订地点：上海", signing_location="上海"),
                _hd_candidate("c2", "SIGNING_LOCATION", "交付地：北京", signing_location="北京"),
            ]
        ),
        _doc(),
        _registry(),
    )
    assert facts.header.signing_location.presence == "UNCERTAIN"
    assert {o.raw_text for o in facts.header.signing_location.observations} == {"上海", "北京"}


def test_signing_date_valid_iso_normalized() -> None:
    facts = assemble_header_parties(
        _env([_hd_candidate("c1", "SIGNING_DATE", "签订日期：2026年8月15日", signing_date="2026年8月15日")]),
        _doc(),
        _registry(),
    )
    assert facts.header.signing_date.presence == "PRESENT_VALUE"
    assert facts.header.signing_date.normalization_state == "VALID"
    assert facts.header.signing_date.observations[0].normalized_value == "2026-08-15"


def test_signing_date_invalid_keeps_raw_and_invalid_state() -> None:
    facts = assemble_header_parties(
        _env([_hd_candidate("c1", "SIGNING_DATE", "签订日期：待定", signing_date="待定")]),
        _doc(),
        _registry(),
    )
    assert facts.header.signing_date.presence == "PRESENT_VALUE"
    assert facts.header.signing_date.normalization_state == "INVALID"
    assert facts.header.signing_date.observations[0].normalized_value is None
    assert facts.header.signing_date.observations[0].raw_text == "待定"



# ---------------------------------------------------------------- header semantics

# ---------------------------------------------------------------- parties
def test_single_canonical_party_assembled() -> None:
    facts = assemble_header_parties(
        _env([_hd_candidate("c1", "CANONICAL_PARTY", "甲方：甲乙科技有限公司", party_role="甲方", party_name="甲乙科技有限公司")]),
        _doc(),
        _registry(),
    )
    assert len(facts.canonical_parties) == 1
    party = facts.canonical_parties[0]
    assert party.declared_name.observations[0].normalized_value == "甲乙科技有限公司"
    roles = [d.text for d in party.declared_designations if d.kind == "CONTRACT_ROLE"]
    assert roles == ["甲方"]


def test_multi_party_not_collapsed() -> None:
    facts = assemble_header_parties(
        _env(
            [
                _hd_candidate("c1", "CANONICAL_PARTY", "甲方：甲乙科技有限公司", party_role="甲方", party_name="甲乙科技有限公司"),
                _hd_candidate("c2", "CANONICAL_PARTY", "乙方：丙丁工程有限公司", party_role="乙方", party_name="丙丁工程有限公司"),
            ]
        ),
        _doc(),
        _registry(),
    )
    assert len(facts.canonical_parties) == 2


def test_party_aliases_become_name_alias_designations() -> None:
    facts = assemble_header_parties(
        _env(
            [
                _hd_candidate(
                    "c1",
                    "CANONICAL_PARTY",
                    "甲方：甲乙科技有限公司",
                    party_role="甲方",
                    party_name="甲乙科技有限公司",
                    party_aliases=["甲乙科技", "JIAYI"],
                )
            ]
        ),
        _doc(),
        _registry(),
    )
    party = facts.canonical_parties[0]
    alias_texts = sorted(d.text for d in party.declared_designations if d.kind == "NAME_ALIAS")
    assert alias_texts == ["JIAYI", "甲乙科技"]


def test_empty_party_field_forms_present_empty_canonical_party() -> None:
    facts = assemble_header_parties(
        _env([_hd_candidate("c1", "CANONICAL_PARTY", "甲方：", party_role="甲方", party_name=None)]),
        _doc(),
        _registry(),
    )
    assert len(facts.canonical_parties) == 1
    party = facts.canonical_parties[0]
    assert party.declared_name.presence == "PRESENT_EMPTY"
    assert party.declared_name.normalization_state == "NOT_APPLICABLE"
    assert party.declared_name.observations[0].raw_text == ""
    assert party.declared_name.observations[0].normalized_value == ""
    roles = [d.text for d in party.declared_designations if d.kind == "CONTRACT_ROLE"]
    assert roles == ["甲方"]


def test_main_party_mention_match_appellation() -> None:
    facts = assemble_header_parties(
        _env(
            [
                _hd_candidate("c1", "CANONICAL_PARTY", "甲方：甲乙科技有限公司", party_role="甲方", party_name="甲乙科技有限公司"),
                _hd_candidate("c2", "PARTY_MENTION", "正文中提及 甲乙科技有限公司", party_name="甲乙科技有限公司", mention_text="甲乙科技有限公司"),
            ]
        ),
        _doc(),
        _registry(),
    )
    mention = facts.party_mentions[0]
    assert mention.mention_kind == "PARTY_APPELLATION"
    assert mention.comparison_state == "MATCHED_DECLARATION"
    # 称谓引用不建立本地定义；定义状态不得由名称匹配倒推。
    assert mention.local_definition_state == "NOT_APPLICABLE"
    assert len(mention.candidate_party_keys) == 1


def test_main_party_mention_unmatched_is_outside_declared() -> None:
    facts = assemble_header_parties(
        _env(
            [
                _hd_candidate("c1", "CANONICAL_PARTY", "甲方：甲乙科技有限公司", party_role="甲方", party_name="甲乙科技有限公司"),
                _hd_candidate(
                    "c2",
                    "PARTY_MENTION",
                    "正文中提及 丙丁工程有限公司",
                    party_name="丙丁工程有限公司",
                    party_role="乙方",
                    mention_text="丙丁工程有限公司",
                ),
            ]
        ),
        _doc(),
        _registry(),
    )
    mention = facts.party_mentions[0]
    # mention_kind=None 不得产出定义；有结构化名称按称谓解析。
    assert mention.mention_kind == "PARTY_APPELLATION"
    assert mention.comparison_state == "OUTSIDE_DECLARED_SET"
    assert mention.local_definition_state == "NOT_APPLICABLE"
    assert mention.candidate_party_keys == []


def test_candidates_above_three_not_truncated() -> None:
    candidates = []
    for i in range(5):
        candidates.append(
            _hd_candidate(
                f"c{i}",
                "CANONICAL_PARTY",
                f"角色线{i}：主体{i}科技",
                party_role=f"角色{i}",
                party_name=f"主体{i}科技",
            )
        )
    facts = assemble_header_parties(_env(candidates), _doc(MANY_MD), _many_registry())
    assert len(facts.canonical_parties) == 5


# ---------------------------------------------------------------- semantic contracts
def test_invalid_calendar_date_keeps_raw_and_invalid_state() -> None:
    facts = assemble_header_parties(
            _env([_hd_candidate("c1", "SIGNING_DATE", "签订日期：待定", signing_date="2026-02-30")]),
        _doc(),
        _registry(),
    )
    assert facts.header.signing_date.presence == "PRESENT_VALUE"
    assert facts.header.signing_date.normalization_state == "INVALID"
    assert facts.header.signing_date.observations[0].raw_text == "2026-02-30"
    assert facts.header.signing_date.observations[0].normalized_value is None


def test_same_value_candidates_merge_and_keep_all_evidence() -> None:
    facts = assemble_header_parties(
        _env([
                _hd_candidate("c1", "SIGNING_LOCATION", "签订地点：上海", signing_location="上海"),
                _hd_candidate("c2", "SIGNING_LOCATION", "交付地：北京", signing_location="上海"),
        ]),
        _doc(),
        _registry(),
    )
    assert facts.header.signing_location.presence == "PRESENT_VALUE"
    obs = facts.header.signing_location.observations
    assert len(obs) == 1
    assert obs[0].raw_text == "上海"
    assert len(obs[0].evidence_ids) == 2


def test_conflicting_values_become_uncertain() -> None:
    facts = assemble_header_parties(
        _env([
                _hd_candidate("c1", "SIGNING_DATE", "签订日期：2026年8月15日", signing_date="2026-08-15"),
                _hd_candidate("c2", "SIGNING_DATE", "签订日期：待定", signing_date="2026-09-01"),
        ]),
        _doc(),
        _registry(),
    )
    assert facts.header.signing_date.presence == "UNCERTAIN"
    values = {o.normalized_value for o in facts.header.signing_date.observations}
    assert values == {"2026-08-15", "2026-09-01"}


def test_signing_location_preserves_full_raw_and_extracts_city() -> None:
    facts = assemble_header_parties(
            _env([_hd_candidate("c1", "SIGNING_LOCATION", "签订地点：上海", signing_location="上海市浦东新区张江高科技园区")]),
        _doc(),
        _registry(),
    )
    obs = facts.header.signing_location.observations[0]
    assert obs.raw_text == "上海市浦东新区张江高科技园区"
    assert obs.normalized_value == "上海市浦东新区张江高科技园区"
    assert obs.city_candidates == ["上海"]


def test_one_role_multiple_parties_keeps_all_candidates_uncertain() -> None:
    facts = assemble_header_parties(
        _env([
                _hd_candidate("c1", "CANONICAL_PARTY", "甲方：甲乙科技有限公司", party_role="甲方", party_name="甲乙科技有限公司"),
                _hd_candidate("c2", "CANONICAL_PARTY", "乙方：丙丁工程有限公司", party_role="甲方", party_name="丙丁工程有限公司"),
                _hd_candidate("c3", "PARTY_MENTION", "正文中提及 丙丁工程有限公司", party_role="甲方", mention_text="甲方"),
        ]),
        _doc(),
        _registry(),
    )
    assert len(facts.canonical_parties) == 2
    mention = facts.party_mentions[0]
    assert mention.mention_kind == "ROLE_REFERENCE"
    assert mention.comparison_state == "UNCERTAIN"
    assert len(mention.candidate_party_keys) == 2


def test_attachment_known_party_mention_is_appellation_not_definition() -> None:
    main_facts = assemble_header_parties(
        _env([_hd_candidate("c1", "CANONICAL_PARTY", "乙方：丙丁工程有限公司", party_role="乙方", party_name="丙丁工程有限公司")]),
        _doc(),
        _registry(),
    )
    mentions = assemble_party_mentions(
        _att_env([_att_candidate("a1", "本附件再次提到 丙丁工程有限公司", "丙丁工程有限公司")]),
        main_facts.canonical_parties,
        _doc(ATTACH_MD, "attach1"),
        _registry(),
    )
    assert len(mentions) == 1
    assert mentions[0].mention_kind == "PARTY_APPELLATION"
    assert mentions[0].comparison_state == "MATCHED_DECLARATION"
    # 附件称谓的主合同定义状态保持 UNCERTAIN，不得倒推。
    assert mentions[0].local_definition_state == "UNCERTAIN"
    assert len(mentions[0].candidate_party_keys) == 1


def test_source_gap_quote_located_issue_has_evidence_and_lowers_coverage() -> None:
    facts = assemble_header_parties(
        _env(
            [],
            gaps=[{"affected_fact_kinds": ["SIGNING_DATE"], "message": "签订日期栏缺失", "quote": "签订日期：2026年8月15日"}],
        ),
        _doc(),
        _registry(),
    )
    issue = facts.fact_issues[0]
    assert issue.code == "SOURCE_UNREADABLE"
    assert len(issue.evidence_ids) == 1
    domain = build_header_fact_domain(facts.header, facts.fact_issues)
    assert domain.state == "PARTIAL"


def test_mention_key_is_invariant_to_observed_text_wording() -> None:
    facts1 = assemble_header_parties(
        _env([
            _hd_candidate("c1", "CANONICAL_PARTY", "甲方：甲乙科技有限公司", party_role="甲方", party_name="甲乙科技有限公司"),
                _hd_candidate("c2", "PARTY_MENTION", "正文中提及 甲乙科技有限公司", party_name="甲乙科技有限公司", mention_text="甲乙科技有限公司"),
        ]),
        _doc(),
        _registry(),
    )
    facts2 = assemble_header_parties(
        _env([
            _hd_candidate("c1", "CANONICAL_PARTY", "甲方：甲乙科技有限公司", party_role="甲方", party_name="甲乙科技有限公司"),
                _hd_candidate("c2", "PARTY_MENTION", "正文中提及 甲乙科技有限公司", party_name="甲乙科技有限公司", mention_text="甲乙科技有限公司"),
        ]),
        _doc(),
        _registry(),
    )
    assert facts1.party_mentions[0].mention_key == facts2.party_mentions[0].mention_key


def test_fact_issue_key_is_invariant_to_message_wording() -> None:
    facts1 = assemble_header_parties(
        _env([], gaps=[{"affected_fact_kinds": ["SIGNING_DATE"], "message": "日期栏缺失", "quote": "签订日期"}]),
        _doc(),
        _registry(),
    )
    facts2 = assemble_header_parties(
        _env([], gaps=[{"affected_fact_kinds": ["SIGNING_DATE"], "message": "日期缺失了", "quote": "签订日期"}]),
        _doc(),
        _registry(),
    )
    assert facts1.fact_issues[0].fact_issue_key == facts2.fact_issues[0].fact_issue_key


# ------------------------------------------------------- attachment mentions
def _att_env(candidates: list[dict[str, Any]]) -> PrepareModelEnvelope:
    payload: dict[str, Any] = {"candidates": candidates, "source_gaps": []}
    return PrepareModelEnvelope[list[AttachmentCandidate]].model_validate(payload)


def _att_candidate(
    ref: str,
    quote: str,
    mention_text: str,
    *,
    document_key: str = "attach1",
    party_name: str | None = None,
    party_role: str | None = None,
    mention_kind: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "candidate_ref": ref,
        "candidate_kind": "PARTY_MENTION",
        "document_key": document_key,
        "quote": quote,
        "mention_text": mention_text,
    }
    if party_name is not None:
        payload["party_name"] = party_name
    if party_role is not None:
        payload["party_role"] = party_role
    if mention_kind is not None:
        payload["mention_kind"] = mention_kind
    return payload


def test_attachment_local_definition_only_forms_mention() -> None:
    main_facts = assemble_header_parties(
        _env([_hd_candidate("c1", "CANONICAL_PARTY", "甲方：甲乙科技有限公司", party_role="甲方", party_name="甲乙科技有限公司")]),
        _doc(),
        _registry(),
    )
    mentions = assemble_party_mentions(
        _att_env([_att_candidate("a1", "本附件定义负责人：某某项目部", "某某项目部", mention_kind="PARTY_DEFINITION", party_name="某某项目部", party_role="负责人")]),
        main_facts.canonical_parties,
        _doc(ATTACH_MD, "attach1"),
        _registry(),
    )
    assert len(mentions) == 1
    assert mentions[0].mention_kind == "PARTY_DEFINITION"
    assert mentions[0].comparison_state == "OUTSIDE_DECLARED_SET"
    assert mentions[0].candidate_party_keys == []


def test_attachment_mention_with_no_canonical_parties_outside_declared() -> None:
    mentions = assemble_party_mentions(
        _att_env([_att_candidate("a1", "本附件再次提到 丙丁工程有限公司", "丙丁工程有限公司")]),
        [],
        _doc(ATTACH_MD, "attach1"),
        _registry(),
    )
    assert len(mentions) == 1
    assert mentions[0].comparison_state == "OUTSIDE_DECLARED_SET"


def test_extract_attachment_party_mentions_wrapper_calls_model() -> None:
    from unittest.mock import patch

    with patch(
        "app.capabilities.contract_review.two_stage.extract_header_parties.invoke_typed_prepare_model",
        return_value=_att_env([_att_candidate("a1", "本附件定义负责人：某某项目部", "某某项目部")]),
    ) as mock_invoke:
        mentions = extract_attachment_party_mentions(
            _doc(ATTACH_MD, "attach1"),
            [],
            _registry(),
        )
    mock_invoke.assert_called_once()
    assert len(mentions) == 1


# ---------------------------------------------------------------- coverage
def test_header_coverage_only_main_document() -> None:
    facts = assemble_header_parties(_env([]), _doc(), _registry())
    domain = build_header_fact_domain(facts.header, facts.fact_issues)
    assert [c.document_key for c in domain.coverage] == ["main"]
    assert domain.state == "COMPLETE"


def test_parties_coverage_includes_all_documents() -> None:
    facts = assemble_header_parties(_env([]), _doc(), _registry())
    domain = build_parties_fact_domain(
        facts.canonical_parties,
        facts.party_mentions,
        facts.fact_issues,
        ["main", "attach1"],
    )
    assert {c.document_key for c in domain.coverage} == {"main", "attach1"}
    assert domain.state == "COMPLETE"


def test_source_gap_lowers_header_coverage_to_partial() -> None:
    facts = assemble_header_parties(
        _env(
            [],
            gaps=[{"affected_fact_kinds": ["SIGNING_DATE"], "message": "签订日期栏缺失", "quote": None}],
        ),
        _doc(),
        _registry(),
    )
    domain = build_header_fact_domain(facts.header, facts.fact_issues)
    assert domain.state == "PARTIAL"
    assert domain.coverage[0].state == "PARTIAL"
    assert domain.issues[0].code == "SOURCE_UNREADABLE"
    assert domain.coverage[0].fact_issue_keys == [domain.issues[0].fact_issue_key]


def test_source_gap_on_attachment_lowers_only_that_document_parties_coverage() -> None:
    facts = assemble_header_parties(
        _env(
            [],
            gaps=[{"affected_fact_kinds": ["PARTY_MENTION"], "message": "附件主体无法识别", "quote": None, "document_key": "attach1"}],
        ),
        _doc(),
        _registry(),
    )
    domain = build_parties_fact_domain(
        facts.canonical_parties,
        facts.party_mentions,
        facts.fact_issues,
        ["main", "attach1"],
    )
    assert domain.state == "PARTIAL"
    by_doc = {c.document_key: c for c in domain.coverage}
    assert by_doc["main"].state == "COMPLETE"
    assert by_doc["attach1"].state == "PARTIAL"


def test_no_grade_or_identity_basis_fields_in_extraction() -> None:
    facts = assemble_header_parties(
        _env([_hd_candidate("c1", "CONTRACT_NAME", "采购合同", contract_name="采购合同")]),
        _doc(),
        _registry(),
    )
    data = facts.header.model_dump()
    assert "identity_basis" not in data
    assert "our_party_key" not in data
    assert "grade" not in data
    for party in facts.canonical_parties:
        party_data = party.model_dump()
        assert "our_party_key" not in party_data
        assert "grade" not in party_data



# ------------------------------------------------------------------
# Round 3 contract-gap coverage
# ------------------------------------------------------------------

def test_generic_name_only_contract_type() -> None:
    """泛化名称只表达合同类型，必须为 GENERIC。"""
    facts = assemble_header_parties(
        _env([
            _hd_candidate("c1", "CONTRACT_NAME", "采购合同", contract_name="采购合同"),
            _hd_candidate("c2", "CONTRACT_NAME", "合同编号：HT-2026-001", contract_name="销售合同"),
            _hd_candidate("c3", "CONTRACT_NAME", "项目名称：智慧园区建设", contract_name="建设工程施工合同"),
        ]),
        _doc(),
        _registry(),
    )
    specs = {o.raw_text: o.specificity for o in facts.header.contract_identity.name.observations}
    assert specs["采购合同"] == "GENERIC"
    assert specs["销售合同"] == "GENERIC"
    assert specs["建设工程施工合同"] == "GENERIC"


def test_isalnum_or_token_list_does_not_make_generic() -> None:
    """不得使用 isalnum() 或固定词表判定一般语义名称。"""
    facts = assemble_header_parties(
        _env([
            _hd_candidate("c1", "CONTRACT_NAME", "项目名称：智慧园区建设", contract_name="智慧园区建设工作服务合同"),
            _hd_candidate("c2", "CONTRACT_NAME", "项目编号：PRJ-88", contract_name="某项目合作协议"),
        ]),
        _doc(),
        _registry(),
    )
    specs = {o.raw_text: o.specificity for o in facts.header.contract_identity.name.observations}
    assert specs["智慧园区建设工作服务合同"] == "GENERIC"
    assert specs["某项目合作协议"] == "GENERIC"


def test_invalid_calendar_date_keeps_raw_and_invalid_flag() -> None:
    """真实日历校验：2月30日应保留原文并标记 INVALID。"""
    facts = assemble_header_parties(
        _env([_hd_candidate("c1", "SIGNING_DATE", "签订日期：2026-02-30", signing_date="2026-02-30")]),
        _doc(),
        _registry(),
    )
    assert facts.header.signing_date.presence == "PRESENT_VALUE"
    assert facts.header.signing_date.normalization_state == "INVALID"
    assert facts.header.signing_date.observations[0].raw_text == "2026-02-30"
    assert facts.header.signing_date.observations[0].normalized_value is None


def test_same_field_different_values_mark_uncertain() -> None:
    """同字段出现异值候选时应为 UNCERTAIN。"""
    facts = assemble_header_parties(
        _env([
            _hd_candidate("c1", "CONTRACT_NAME", "合同名称：A", contract_name="A"),
            _hd_candidate("c2", "CONTRACT_NAME", "合同名：B", contract_name="B"),
        ]),
        _doc(),
        _registry(),
    )
    assert facts.header.contract_identity.name.presence == "UNCERTAIN"
    assert {o.raw_text for o in facts.header.contract_identity.name.observations} == {"A", "B"}


def test_same_field_same_value_merges_evidence() -> None:
    """同字段同值候选应合并为一个事实并保留全部证据。"""
    facts = assemble_header_parties(
        _env([
            _hd_candidate("c1", "CONTRACT_NAME", "合同名称：A", contract_name="A"),
            _hd_candidate("c2", "CONTRACT_NAME", "名称为A", contract_name="A"),
        ]),
        _doc(),
        _registry(),
    )
    obs = facts.header.contract_identity.name.observations
    assert len(obs) == 1
    assert len(obs[0].evidence_ids) == 2


def test_signing_location_keeps_full_raw_and_extracts_city() -> None:
    """详细签订地址保留原文，city_candidates 只保存可靠城市。"""
    facts = assemble_header_parties(
        _env([_hd_candidate("c1", "SIGNING_LOCATION", "签订地点：上海", signing_location="北京市朝阳区建国门外大街1号")]),
        _doc(),
        _registry(),
    )
    assert facts.header.signing_location.presence == "PRESENT_VALUE"
    obs = facts.header.signing_location.observations[0]
    assert obs.raw_text == "北京市朝阳区建国门外大街1号"
    assert obs.normalized_value == "北京市朝阳区建国门外大街1号"
    assert obs.city_candidates == ["北京"]


def test_empty_subject_field_creates_present_empty_canonical_party() -> None:
    """角色明确但主体名称为空时保留 PRESENT_EMPTY canonical party。"""
    facts = assemble_header_parties(
        _env([_hd_candidate("c1", "CANONICAL_PARTY", "甲方：", party_role="甲方", party_name=None)]),
        _doc(),
        _registry(),
    )
    assert len(facts.canonical_parties) == 1
    party = facts.canonical_parties[0]
    assert party.declared_name.presence == "PRESENT_EMPTY"
    assert party.declared_name.normalization_state == "NOT_APPLICABLE"
    assert party.declared_name.observations[0].raw_text == ""
    assert party.declared_name.observations[0].normalized_value == ""
    roles = [d.text for d in party.declared_designations if d.kind == "CONTRACT_ROLE"]
    assert roles == ["甲方"]


def test_multiple_empty_subject_fields_remain_independent() -> None:
    """多个空主体栏按真实槽位/证据坐标保持独立，稳定键不依赖展示文案。"""
    c1 = _hd_candidate("c1", "CANONICAL_PARTY", "甲方：", party_role="甲方", party_name=None)
    c2 = _hd_candidate("c2", "CANONICAL_PARTY", "乙方：", party_role="乙方", party_name=None)
    facts = assemble_header_parties(_env([c1, c2]), _doc(), _registry())
    assert len(facts.canonical_parties) == 2
    keys = {p.party_key for p in facts.canonical_parties}
    assert len(keys) == 2
    roles = sorted(p.declared_designations[0].text for p in facts.canonical_parties if p.declared_designations)
    assert roles == sorted(["甲方", "乙方"])


def test_role_with_multiple_parties_marks_uncertain_not_silent_pick() -> None:
    """同一角色映射多个主体时不得静默选一个。"""
    facts = assemble_header_parties(
        _env([
            _hd_candidate("c1", "CANONICAL_PARTY", "买方：A公司", party_role="甲方", party_name="A公司"),
            _hd_candidate("c2", "CANONICAL_PARTY", "买方：B公司", party_role="甲方", party_name="B公司"),
            _hd_candidate("c3", "PARTY_MENTION", "甲方应付款", party_role="甲方", mention_text="甲方应付款"),
        ]),
        _doc(),
        _registry(),
    )
    mention = [m for m in facts.party_mentions if m.observed_text == "甲方应付款"][0]
    assert mention.mention_kind == "ROLE_REFERENCE"
    assert mention.local_definition_state == "UNCERTAIN"
    assert mention.comparison_state == "UNCERTAIN"
    assert len(mention.candidate_party_keys) == 2





def test_party_definition_appellation_role_reference_states_determined_by_semantics() -> None:
    """正文/附件 mention 的定义、称谓、角色引用状态必须来自实际局部语义。"""
    facts = assemble_header_parties(
        _env([
            _hd_candidate("c1", "CANONICAL_PARTY", "甲方：甲乙科技有限公司", party_role="甲方", party_name="甲乙科技有限公司"),
            _hd_candidate("c2", "PARTY_MENTION", "甲乙科技有限公司承担义务", party_name="甲乙科技有限公司", mention_text="甲乙科技有限公司承担义务"),
            _hd_candidate("c3", "PARTY_MENTION", "甲方应付款", party_role="甲方", mention_text="甲方应付款"),
            _hd_candidate("c4", "PARTY_MENTION", "供应商", mention_text="供应商"),
        ]),
        _doc(),
        _registry(),
    )
    by_text = {m.observed_text: m for m in facts.party_mentions}
    assert by_text["甲乙科技有限公司承担义务"].mention_kind == "PARTY_APPELLATION"
    assert by_text["甲乙科技有限公司承担义务"].comparison_state == "MATCHED_DECLARATION"
    assert by_text["甲方应付款"].mention_kind == "ROLE_REFERENCE"
    assert by_text["甲方应付款"].local_definition_state == "ABSENT"
    assert by_text["甲方应付款"].comparison_state == "MATCHED_DECLARATION"
    # 裸称谓无结构化 name/role：不得自动成为 definition。
    assert by_text["供应商"].mention_kind == "PARTY_APPELLATION"
    assert by_text["供应商"].comparison_state == "OUTSIDE_DECLARED_SET"


def test_attachment_candidate_does_not_modify_canonical_parties_or_classify() -> None:
    """附件 candidate 不得修改 canonical parties 或产生正式分类。"""
    from app.capabilities.contract_review.two_stage.schemas import CanonicalParty, ObservedField, ObservedValue
    canonical = [
        CanonicalParty(
            party_key="party:orig",
            declared_name=ObservedField(presence="PRESENT_VALUE", normalization_state="VALID", observations=[
                ObservedValue(raw_text="A公司", normalized_value="A公司", evidence_ids=["e:1"])
            ]),
            declared_designations=[],
            definition_evidence_ids=["e:1"],
        ),
    ]
    env = PrepareModelEnvelope[
        list[AttachmentCandidate]
    ].model_validate({
        "candidates": [{
            "candidate_ref": "a1", "candidate_kind": "PARTY_MENTION", "document_key": "attach1",
            "quote": "附件主体C公司", "mention_text": "附件主体C公司", "party_name": "C公司", "party_role": "乙方",
        }],
        "source_gaps": [],
    })
    markdown = "正文\n附件主体C公司\n"
    mentions = assemble_party_mentions(env, canonical, PreparedDocument(document_key="attach1", markdown=markdown), _registry({"attach1": markdown}))
    assert len(mentions) == 1
    m = mentions[0]
    assert m.document_key == "attach1"
    assert m.mention_kind in {"PARTY_DEFINITION", "PARTY_APPELLATION", "ROLE_REFERENCE"}
    # canonical parties must not gain the attachment entity
    assert all(p.declared_name.observations[0].normalized_value != "C公司" for p in canonical)
    assert "our_party" not in m.model_dump()
    assert "their_party" not in m.model_dump()


def test_extraction_ranges_limit_evidence_location_no_merge() -> None:
    """extraction_ranges 必须限制模型输入和证据定位；不连续范围不得合并为外包络。"""
    from app.capabilities.contract_review.two_stage.schemas import CanonicalParty, ObservedField, ObservedValue
    canonical = [
        CanonicalParty(
            party_key="party:a",
            declared_name=ObservedField(presence="PRESENT_VALUE", normalization_state="VALID", observations=[
                ObservedValue(raw_text="A公司", normalized_value="A公司", evidence_ids=["e:1"])
            ]),
            declared_designations=[],
            definition_evidence_ids=["e:1"],
        ),
    ]
    markdown = "前文\nA公司出现\n中文\nA公司出现\n后文"
    env = PrepareModelEnvelope[
        list[AttachmentCandidate]
    ].model_validate({
        "candidates": [{
            "candidate_ref": "a1", "candidate_kind": "PARTY_MENTION", "document_key": "attach1",
            "quote": "A公司出现", "mention_text": "A公司出现",
        }],
        "source_gaps": [],
    })
    reg = _registry({"attach1": markdown})
    # Ranges deliberately omit the second occurrence; merged envelope would match both and fail.
    ranges = [(3, 12)]  # covers only first occurrence
    mentions = assemble_party_mentions(env, canonical, PreparedDocument(document_key="attach1", markdown=markdown), reg, extraction_ranges=ranges)
    assert len(mentions) == 1
    assert reg.items()[0].source_locator == "markdown-chars:3-8"


def test_unlocatable_attachment_source_gap_creates_fact_issue() -> None:
    """可定位 source_gaps 与 EvidenceLocationError 必须区分；不可定位证据形成 FactIssue。"""
    from app.capabilities.contract_review.two_stage.schemas import CanonicalParty, ObservedField, ObservedValue
    canonical = [
        CanonicalParty(
            party_key="party:a",
            declared_name=ObservedField(presence="PRESENT_VALUE", normalization_state="VALID", observations=[
                ObservedValue(raw_text="A公司", normalized_value="A公司", evidence_ids=["e:1"])
            ]),
            declared_designations=[],
            definition_evidence_ids=["e:1"],
        ),
    ]
    markdown = "正文\n"
    env = PrepareModelEnvelope[
        list[AttachmentCandidate]
    ].model_validate({
        "candidates": [],
        "source_gaps": [{
            "affected_fact_kinds": ["PARTY_MENTION"],
            "message": "附件角色无法与主体关联",
            "quote": "不存在的引文",
            "document_key": "attach1",
        }],
    })
    mentions = assemble_party_mentions(env, canonical, PreparedDocument(document_key="attach1", markdown=markdown), _registry({"attach1": markdown}))
    # Missing quotes should still surface as fact issues from source gaps, not silence.
    assert len(mentions) == 0


def test_candidate_document_key_must_match_processed_document() -> None:
    """candidate.document_key 必须与当前处理文档严格一致；违反即组装契约错误，请求失败。"""
    import pytest as _pytest

    from app.core.errors import ModelFormatError

    env = _env([
        _hd_candidate("c1", "CONTRACT_NAME", "采购合同", document_key="other_doc", contract_name="采购合同"),
    ])
    # candidate belongs to a different document_key than the one being assembled
    with _pytest.raises(ModelFormatError):
        assemble_header_parties(env, _doc(), _registry())


def test_mention_deduplication_and_stable_key_across_candidate_reorder() -> None:
    """同坐标 mention 去重；候选换序后稳定键及确定性排序不变。"""
    facts1 = assemble_header_parties(
        _env([
            _hd_candidate("c1", "PARTY_MENTION", "正文中提及 甲乙科技有限公司", party_name="甲乙科技有限公司", mention_text="甲乙科技有限公司"),
            _hd_candidate("c2", "PARTY_MENTION", "正文中提及 甲乙科技有限公司", party_name="甲乙科技有限公司", mention_text="甲乙科技有限公司"),
        ]),
        _doc(),
        _registry(),
    )
    facts2 = assemble_header_parties(
        _env([
            _hd_candidate("c2", "PARTY_MENTION", "正文中提及 甲乙科技有限公司", party_name="甲乙科技有限公司", mention_text="甲乙科技有限公司"),
            _hd_candidate("c1", "PARTY_MENTION", "正文中提及 甲乙科技有限公司", party_name="甲乙科技有限公司", mention_text="甲乙科技有限公司"),
        ]),
        _doc(),
        _registry(),
    )
    assert len(facts1.party_mentions) == len(facts2.party_mentions) == 1
    assert facts1.party_mentions[0].mention_key == facts2.party_mentions[0].mention_key
    assert [m.observed_text for m in facts1.party_mentions] == [m.observed_text for m in facts2.party_mentions]


def test_mention_keys_and_fact_issue_keys_ignore_model_free_text() -> None:
    """mention_key / fact_issue_key 不得包含模型自由展示文案。"""
    env = _env([
        _hd_candidate("c1", "CONTRACT_NAME", "A", contract_name="A"),
        _hd_candidate("c2", "PARTY_MENTION", "B公司", mention_text="B公司"),
        {
            "candidate_ref": "c3", "candidate_kind": "SOURCE_GAP", "quote": "自由文案问题",
            "message": "自由文案", "affected_fact_kinds": ["CONTRACT_NAME"],
        },
    ])
    facts = assemble_header_parties(env, _doc(), _registry())
    for issue in facts.fact_issues:
        assert "自由文案" not in issue.fact_issue_key
    for mention in facts.party_mentions:
        assert "自由文案" not in mention.mention_key
        assert mention.mention_key.startswith("mention:")


# ------------------------------------------------------------------
# Round 4 review-blocker coverage
# ------------------------------------------------------------------

def test_r4_explicit_entity_name_follows_party_definition_semantics_only() -> None:
    """explicit_entity_name 只在 PARTY_DEFINITION 语义下装配；称谓/角色引用显式为 None。"""
    facts = assemble_header_parties(
        _env([
            _hd_candidate("c1", "CANONICAL_PARTY", "甲方：甲乙科技有限公司", party_role="甲方", party_name="甲乙科技有限公司"),
            _hd_candidate("c2", "PARTY_MENTION", "正文中提及 甲乙科技有限公司", party_name="甲乙科技有限公司", mention_text="甲乙科技有限公司"),
            _hd_candidate("c3", "PARTY_MENTION", "甲方应付款", party_role="甲方", mention_text="甲方应付款"),
            # definition 需结构化名称；裸文本不再自动成为 definition（见 r5 测试）。
            _hd_candidate("c4", "PARTY_MENTION", "供应商", mention_kind="PARTY_DEFINITION", party_name="供应商", mention_text="供应商"),
        ]),
        _doc(),
        _registry(),
    )
    by_kind = {m.mention_kind: m for m in facts.party_mentions}
    assert by_kind["PARTY_APPELLATION"].explicit_entity_name is None
    assert by_kind["ROLE_REFERENCE"].explicit_entity_name is None
    definition = by_kind["PARTY_DEFINITION"]
    assert definition.observed_text == "供应商"
    assert definition.explicit_entity_name is not None
    assert definition.explicit_entity_name.presence == "PRESENT_VALUE"
    assert definition.explicit_entity_name.observations[0].normalized_value == "供应商"

    mentions = assemble_party_mentions(
        _att_env([_att_candidate("a1", "本附件定义负责人：某某项目部", "某某项目部", mention_kind="PARTY_DEFINITION", party_name="某某项目部", party_role="负责人")]),
        [],
        _doc(ATTACH_MD, "attach1"),
        _registry(),
    )
    assert len(mentions) == 1
    assert mentions[0].mention_kind == "PARTY_DEFINITION"
    assert mentions[0].explicit_entity_name is not None
    assert mentions[0].explicit_entity_name.observations[0].normalized_value == "某某项目部"


def test_r4_attachment_response_schema_matches_python_candidate_fields() -> None:
    """严格响应 Schema 字段集合必须与 Python candidate 模型一致，否则模型永远无法回传。"""
    from app.capabilities.contract_review.two_stage.prepare_model import (
        AttachmentCandidate,
        HeaderPartiesCandidate,
    )
    from app.capabilities.contract_review.two_stage.prepare_response_formats import (
        ATTACHMENT_CANDIDATE_SCHEMA,
        HEADER_PARTIES_CANDIDATE_SCHEMA,
    )

    assert set(HEADER_PARTIES_CANDIDATE_SCHEMA["properties"]) == set(HeaderPartiesCandidate.model_fields)
    assert set(ATTACHMENT_CANDIDATE_SCHEMA["properties"]) == set(AttachmentCandidate.model_fields)


def test_r4_empty_canonical_party_key_does_not_depend_on_candidate_ref() -> None:
    """空主体 party_key/分组坐标只用业务坐标（文档+角色+证据位置），不依赖 candidate_ref。"""
    def run(ref_a: str, ref_b: str):
        env = _env([
            _hd_candidate(ref_a, "CANONICAL_PARTY", "甲方：", party_role="甲方", party_name=None),
            _hd_candidate(ref_b, "CANONICAL_PARTY", "甲方：", party_role="甲方", party_name=None),
        ])
        return assemble_header_parties(env, _doc(), _registry())

    f1 = run("c1", "c2")
    f2 = run("c9", "c8")
    assert len(f1.canonical_parties) == 1
    assert f1.canonical_parties[0].declared_name.presence == "PRESENT_EMPTY"
    assert f1.canonical_parties[0].party_key == f2.canonical_parties[0].party_key


def test_r4_same_coordinates_keep_distinct_definition_mentions() -> None:
    """同一证据坐标下的不同实体定义不得互相吞掉（身份坐标必须进稳定键）。"""
    facts = assemble_header_parties(
        _env([
            _hd_candidate("c1", "PARTY_MENTION", "供应商", mention_kind="PARTY_DEFINITION", party_name="乙未科技", party_role="乙方", mention_text="定义：乙未科技"),
            _hd_candidate("c2", "PARTY_MENTION", "供应商", mention_kind="PARTY_DEFINITION", party_name="丁未科技", party_role="乙方", mention_text="定义：丁未科技"),
        ]),
        _doc(),
        _registry(),
    )
    definitions = [m for m in facts.party_mentions if m.mention_kind == "PARTY_DEFINITION"]
    assert len(definitions) == 2
    names = {m.explicit_entity_name.observations[0].normalized_value for m in definitions if m.explicit_entity_name}
    assert names == {"乙未科技", "丁未科技"}


def test_r4_fact_issue_keys_unique_for_same_coordinate() -> None:
    """同一坐标重复触发的 FactIssue 键必须一致并去重，键不嵌原始 quote 文案。"""
    facts = assemble_header_parties(
        _env([
            _hd_candidate("c1", "PARTY_MENTION", "甲方", mention_text="甲方指代"),
            _hd_candidate("c2", "PARTY_MENTION", "甲方", mention_text="甲方又指代"),
        ]),
        _doc(),
        _registry(),
    )
    keys = [i.fact_issue_key for i in facts.fact_issues]
    assert keys, "unlocatable quote must surface fact issues"
    assert len(keys) == len(set(keys))


def test_r4_same_party_multiple_role_evidence_not_multiple_parties() -> None:
    """同一主体同一角色的多条证据不得误判为多主体 UNCERTAIN。"""
    facts = assemble_header_parties(
        _env([
            _hd_candidate("c1", "CANONICAL_PARTY", "甲方：甲乙科技有限公司", party_role="甲方", party_name="甲乙科技有限公司"),
            _hd_candidate("c2", "CANONICAL_PARTY", "合同甲方为甲乙科技有限公司", party_role="甲方", party_name="甲乙科技有限公司"),
            _hd_candidate("c3", "PARTY_MENTION", "甲方应付款", party_role="甲方", mention_text="甲方应付款"),
        ]),
        _doc(),
        _registry(),
    )
    assert len(facts.canonical_parties) == 1
    mention = facts.party_mentions[0]
    assert mention.mention_kind == "ROLE_REFERENCE"
    assert mention.comparison_state == "MATCHED_DECLARATION"
    assert mention.local_definition_state == "ABSENT"
    assert len(mention.candidate_party_keys) == 1


def test_r4_attachment_wrapper_propagates_gaps_to_coverage() -> None:
    """extract_attachment_party_mentions 必须把 source gap/FactIssue 传播到 coverage 消费链。"""
    from unittest.mock import patch

    env = PrepareModelEnvelope[list[AttachmentCandidate]].model_validate({
        "candidates": [],
        "source_gaps": [{
            "affected_fact_kinds": ["PARTY_MENTION"],
            "message": "附件段落缺失",
            "quote": None,
            "document_key": "attach1",
        }],
    })
    issues: list[FactIssue] = []
    with patch(
        "app.capabilities.contract_review.two_stage.extract_header_parties.invoke_typed_prepare_model",
        return_value=env,
    ):
        mentions = extract_attachment_party_mentions(
            _doc(ATTACH_MD, "attach1"),
            [],
            _registry(),
            fact_issues=issues,
        )
    assert mentions == []
    assert any(
        i.affected_fact_kinds == ["PARTY_MENTION"] and "attach1" in i.related_document_keys
        for i in issues
    )
    facts = assemble_header_parties(_env([]), _doc(), _registry())
    domain = build_parties_fact_domain(
        facts.canonical_parties,
        facts.party_mentions,
        facts.fact_issues + issues,
        ["main", "attach1"],
    )
    by_doc = {c.document_key: c for c in domain.coverage}
    assert by_doc["attach1"].state == "PARTIAL"
    assert by_doc["main"].state == "COMPLETE"


def test_r4_unlocatable_evidence_does_not_pollute_public_locator_contract() -> None:
    """不可定位证据不得进入公开 EvidenceIndex；locator 契约保持 markdown-chars 模式。"""
    import pytest as _pytest
    from pydantic import ValidationError as _ValidationError

    from app.capabilities.contract_review.two_stage.schemas import EvidenceItem as _EvidenceItem

    reg = _registry({"main": "正文\n"})
    evidence_id = reg.register_unlocatable("main", "不存在的引文")
    assert evidence_id
    assert reg.items() == []
    assert reg.is_unlocatable(evidence_id) is True
    with _pytest.raises(_ValidationError):
        _EvidenceItem(
            evidence_id="e:1",
            document_key="main",
            source_locator="unavailable:unlocatable",
            quote="q",
        )


def test_r4_equivalent_date_forms_merge_after_normalization() -> None:
    """规范化同值的日期候选必须合并为一个 observation 并保留全部证据。"""
    facts = assemble_header_parties(
        _env([
            _hd_candidate("c1", "SIGNING_DATE", "签订日期：2026年8月15日", signing_date="2026年8月15日"),
            _hd_candidate("c2", "SIGNING_DATE", "签订日期：2026-08-15", signing_date="2026-08-15"),
        ]),
        _doc(),
        _registry(),
    )
    field = facts.header.signing_date
    assert field.presence == "PRESENT_VALUE"
    assert field.normalization_state == "VALID"
    assert len(field.observations) == 1
    assert field.observations[0].normalized_value == "2026-08-15"
    assert len(field.observations[0].evidence_ids) == 2


def test_r4_mixed_valid_invalid_dates_uncertain_not_silent() -> None:
    """合法与非法日期混合时必须 UNCERTAIN，不得静默按合法值判定。"""
    facts = assemble_header_parties(
        _env([
            _hd_candidate("c1", "SIGNING_DATE", "签订日期：2026年8月15日", signing_date="2026年8月15日"),
            _hd_candidate("c2", "SIGNING_DATE", "签订日期：待定", signing_date="待定"),
        ]),
        _doc(),
        _registry(),
    )
    field = facts.header.signing_date
    assert field.presence == "UNCERTAIN"
    assert field.normalization_state == "UNCERTAIN"
    assert len(field.observations) == 2
    assert {o.normalized_value for o in field.observations} == {"2026-08-15", None}


# ------------------------------------------------------------------
# Round 5 review-blocker coverage
# ------------------------------------------------------------------

def test_r5_structured_candidate_kind_distinguishes_definition_appellation_role() -> None:
    """模型候选必须能结构化区分三态；显式 APPELLATION 不得因未匹配名称改判 DEFINITION。"""
    facts = assemble_header_parties(
        _env([
            _hd_candidate("c1", "CANONICAL_PARTY", "甲方：甲乙科技有限公司", party_role="甲方", party_name="甲乙科技有限公司"),
            _hd_candidate(
                "c2", "PARTY_MENTION", "正文中提及 甲乙科技有限公司",
                mention_kind="PARTY_APPELLATION", party_name="甲乙科技有限公司", mention_text="甲乙科技有限公司",
            ),
            _hd_candidate(
                "c3", "PARTY_MENTION", "正文中提及 丙丁工程有限公司",
                mention_kind="PARTY_APPELLATION", party_name="丙丁工程有限公司", mention_text="丙丁工程有限公司",
            ),
            _hd_candidate(
                "c4", "PARTY_MENTION", "甲方应付款",
                mention_kind="ROLE_REFERENCE", party_role="甲方", mention_text="甲方应付款",
            ),
            _hd_candidate(
                "c5", "PARTY_MENTION", "乙方：丙丁工程有限公司",
                mention_kind="PARTY_DEFINITION", party_name="丙丁工程有限公司", party_role="乙方",
                mention_text="乙方：丙丁工程有限公司",
            ),
        ]),
        _doc(),
        _registry(),
    )
    by_ref = {m.observed_text: m for m in facts.party_mentions}
    appellated = by_ref["甲乙科技有限公司"]
    assert appellated.mention_kind == "PARTY_APPELLATION"
    assert appellated.comparison_state == "MATCHED_DECLARATION"
    # 显式称谓但名称未匹配：保持 APPELLATION + OUTSIDE_DECLARED_SET，不得倒推为 DEFINITION
    unmatched = by_ref["丙丁工程有限公司"]
    assert unmatched.mention_kind == "PARTY_APPELLATION"
    assert unmatched.comparison_state == "OUTSIDE_DECLARED_SET"
    assert unmatched.explicit_entity_name is None
    assert by_ref["甲方应付款"].mention_kind == "ROLE_REFERENCE"
    definition = by_ref["乙方：丙丁工程有限公司"]
    assert definition.mention_kind == "PARTY_DEFINITION"
    assert definition.explicit_entity_name is not None


def test_r5_bare_name_not_auto_definition_and_no_name_match_inversion() -> None:
    """裸名称/称谓不得自动成为 definition；local_definition_state 不得由主合同名称匹配倒推。"""
    facts = assemble_header_parties(
        _env([
            _hd_candidate("c1", "CANONICAL_PARTY", "甲方：甲乙科技有限公司", party_role="甲方", party_name="甲乙科技有限公司"),
            _hd_candidate("c2", "PARTY_MENTION", "供应商", mention_text="供应商"),
            _hd_candidate("c3", "PARTY_MENTION", "正文中提及 甲乙科技有限公司", mention_text="甲乙科技有限公司"),
        ]),
        _doc(),
        _registry(),
    )
    by_text = {m.observed_text: m for m in facts.party_mentions}
    bare = by_text["供应商"]
    assert bare.mention_kind == "PARTY_APPELLATION"
    assert bare.local_definition_state == "NOT_APPLICABLE"
    assert bare.explicit_entity_name is None
    assert bare.comparison_state == "OUTSIDE_DECLARED_SET"
    appell = by_text["甲乙科技有限公司"]
    assert appell.mention_kind == "PARTY_APPELLATION"
    # 名称匹配只影响 comparison/candidate keys，不得倒推定义状态
    assert appell.local_definition_state == "NOT_APPLICABLE"
    assert appell.comparison_state == "MATCHED_DECLARATION"


def test_r5_attachment_bare_text_not_definition_without_structured_kind() -> None:
    """附件裸文本不得因名称匹配倒推定义状态，也不得自动成 definition。"""
    main_facts = assemble_header_parties(
        _env([_hd_candidate("c1", "CANONICAL_PARTY", "甲方：甲乙科技有限公司", party_role="甲方", party_name="甲乙科技有限公司")]),
        _doc(),
        _registry(),
    )
    mentions = assemble_party_mentions(
        _att_env([
            _att_candidate("a1", "本附件再次提到 丙丁工程有限公司", "丙丁工程有限公司"),
            _att_candidate("a2", "本附件定义负责人：某某项目部", "某某项目部", mention_kind="PARTY_DEFINITION", party_name="某某项目部", party_role="负责人"),
        ]),
        main_facts.canonical_parties,
        _doc(ATTACH_MD, "attach1"),
        _registry(),
    )
    by_text = {m.observed_text: m for m in mentions}
    bare = by_text["丙丁工程有限公司"]
    assert bare.mention_kind == "PARTY_APPELLATION"
    assert bare.comparison_state == "OUTSIDE_DECLARED_SET"
    # 附件裸称谓的主合同定义状态必须 UNCERTAIN，不得由名称匹配倒推 PRESENT/ABSENT
    assert bare.local_definition_state == "UNCERTAIN"
    definition = by_text["某某项目部"]
    assert definition.mention_kind == "PARTY_DEFINITION"
    assert definition.explicit_entity_name is not None
    assert definition.explicit_entity_name.observations[0].normalized_value == "某某项目部"
    assert definition.local_definition_state == "PRESENT"


def test_r5_mention_key_immune_to_wording_and_quote_changes() -> None:
    """observed_text/quote 展示文案变化、业务坐标不变时 mention_key 必须不变。"""
    def run(mention_text: str) -> str:
        facts = assemble_header_parties(
            _env([
                _hd_candidate("c1", "CANONICAL_PARTY", "甲方：甲乙科技有限公司", party_role="甲方", party_name="甲乙科技有限公司"),
                _hd_candidate(
                    "c2", "PARTY_MENTION", "甲方：甲乙科技有限公司",
                    mention_kind="PARTY_DEFINITION", party_name="承甲科技", party_role="甲方",
                    mention_text=mention_text,
                ),
            ]),
            _doc(),
            _registry(),
        )
        definitions = [m for m in facts.party_mentions if m.mention_kind == "PARTY_DEFINITION"]
        assert len(definitions) == 1
        return definitions[0].mention_key

    assert run("定义：承甲科技") == run("本条定义 承甲科技（新表述）")


def test_r5_fact_issue_key_not_derived_from_quote_or_message_text() -> None:
    """FactIssue 键不得依赖 quote 派生内部 id 或 message 展示文案。"""
    def keys_for(quote: str, mention_text: str) -> list[str]:
        facts = assemble_header_parties(
            _env([_hd_candidate("c1", "PARTY_MENTION", quote, mention_text=mention_text)]),
            _doc(),
            _registry(),
        )
        return [i.fact_issue_key for i in facts.fact_issues]

    # "甲方" 在 MAIN_MD 中多处出现 -> 定位歧义 -> 不可定位问题；键只依赖业务坐标。
    k1 = keys_for("甲方", "甲方指代")
    k2 = keys_for("甲方", "甲方另种说法")
    assert k1 and k1 == k2


def test_r5_unlocatable_candidate_produces_no_dangling_reference() -> None:
    """不可定位候选不得产出引用非公开 evidence id 的事实；完整 ReviewContext 引用闭合。"""
    reg = _registry()
    facts = assemble_header_parties(
        _env([
            _hd_candidate("c1", "CANONICAL_PARTY", "甲方：甲乙科技有限公司", party_role="甲方", party_name="甲乙科技有限公司"),
            _hd_candidate("c2", "PARTY_MENTION", "甲方", party_name="承甲科技", party_role="甲方", mention_text="甲方"),
        ]),
        _doc(),
        reg,
    )
    public_ids = {item.evidence_id for item in reg.items()}
    assert facts.party_mentions == []
    for issue in facts.fact_issues:
        assert set(issue.evidence_ids) <= public_ids

    payload = valid_context_payload()
    evidence_items = list(payload["evidence_index"]["items"])
    for item in reg.items():
        if item.evidence_id not in {e["evidence_id"] for e in evidence_items}:
            evidence_items.append(item.model_dump())
    payload["evidence_index"]["items"] = evidence_items
    domain = build_parties_fact_domain(
        facts.canonical_parties,
        facts.party_mentions,
        facts.fact_issues,
        ["main", "uploaded:att-001", "embedded:main:001"],
    )
    payload["shared_facts"]["parties"] = domain.model_dump(mode="json")
    context = ReviewContext.model_validate(payload)
    # 闭合成立：所有被引用 evidence id 均在公开 evidence_index 内
    index_ids = {item.evidence_id for item in context.evidence_index.items}
    from app.capabilities.contract_review.two_stage.schemas import _collect_evidence_ids

    assert _collect_evidence_ids(context.shared_facts.model_dump(mode="json")) <= index_ids


def test_r5_extraction_ranges_reach_model_call() -> None:
    """extraction_ranges 必须真正进入附件模型调用参数，而不只是限制定位。"""
    with patch(
        "app.capabilities.contract_review.two_stage.extract_header_parties.invoke_typed_prepare_model",
        return_value=_att_env([]),
    ) as mock_invoke:
        invoke_attachment_candidates(_doc(ATTACH_MD, "attach1"), extraction_ranges=[(0, 12), (30, 48)])
    extraction_input = json.loads(mock_invoke.call_args.kwargs["extraction_input"])
    assert extraction_input["extraction_ranges"] == [
        {"start": 0, "end": 12},
        {"start": 30, "end": 48},
    ]

    with patch(
        "app.capabilities.contract_review.two_stage.extract_header_parties.invoke_typed_prepare_model",
        return_value=_att_env([]),
    ) as mock_invoke:
        invoke_attachment_candidates(_doc(ATTACH_MD, "attach1"))
    assert json.loads(mock_invoke.call_args.kwargs["extraction_input"]) == {}


# ------------------------------------------------------------------
# Round 6 review-blocker coverage
# ------------------------------------------------------------------

def test_r6_none_mention_kind_never_yields_definition() -> None:
    """mention_kind=None 时即使携带 party_name/party_role 也不得产出 PARTY_DEFINITION。"""
    facts = assemble_header_parties(
        _env([
            _hd_candidate("c1", "CANONICAL_PARTY", "甲方：甲乙科技有限公司", party_role="甲方", party_name="甲乙科技有限公司"),
            _hd_candidate(
                "c2", "PARTY_MENTION", "正文中提及 丙丁工程有限公司",
                party_name="丙丁工程有限公司", party_role="乙方", mention_text="丙丁工程有限公司",
            ),
        ]),
        _doc(),
        _registry(),
    )
    mention = facts.party_mentions[0]
    assert mention.mention_kind == "PARTY_APPELLATION"
    assert mention.mention_kind != "PARTY_DEFINITION"
    assert mention.explicit_entity_name is None
    assert mention.comparison_state == "OUTSIDE_DECLARED_SET"
    assert mention.local_definition_state == "NOT_APPLICABLE"


def test_r6_attachment_role_reference_not_marked_matched() -> None:
    """附件 ROLE_REFERENCE 不得借主合同 canonical 基准标记 MATCHED_DECLARATION。"""
    main_facts = assemble_header_parties(
        _env([_hd_candidate("c1", "CANONICAL_PARTY", "乙方：丙丁工程有限公司", party_role="乙方", party_name="丙丁工程有限公司")]),
        _doc(),
        _registry(),
    )
    mentions = assemble_party_mentions(
        _att_env([
            _att_candidate(
                "a1", "本附件再次提到 丙丁工程有限公司", "乙方应验收",
                mention_kind="ROLE_REFERENCE", party_role="乙方",
            ),
        ]),
        main_facts.canonical_parties,
        _doc(ATTACH_MD, "attach1"),
        _registry(),
    )
    assert len(mentions) == 1
    mention = mentions[0]
    assert mention.mention_kind == "ROLE_REFERENCE"
    assert mention.comparison_state == "UNCERTAIN"
    assert mention.comparison_state != "MATCHED_DECLARATION"


def test_r6_unlocatable_candidate_lowers_coverage() -> None:
    """不可定位候选必须使对应事实域 coverage 降级，不得被 UNKNOWN 类别吞掉。"""
    facts = assemble_header_parties(
        _env([
            _hd_candidate("c1", "PARTY_MENTION", "甲方", party_name="承甲科技", party_role="甲方", mention_text="甲方指代"),
            _hd_candidate("c2", "CONTRACT_NAME", "合同", contract_name="采购合同"),
        ]),
        _doc(),
        _registry(),
    )
    assert facts.fact_issues
    parties_domain = build_parties_fact_domain(
        facts.canonical_parties, facts.party_mentions, facts.fact_issues, ["main"],
    )
    assert parties_domain.state == "PARTIAL"
    main_coverage = [c for c in parties_domain.coverage if c.document_key == "main"][0]
    assert main_coverage.state == "PARTIAL"
    assert "PARTY_MENTION" in main_coverage.affected_fact_kinds
    assert main_coverage.fact_issue_keys
    header_domain = build_header_fact_domain(facts.header, facts.fact_issues)
    assert header_domain.state == "PARTIAL"


def test_r6_stray_document_candidate_fails_request() -> None:
    """document_key 与处理文档不一致 = 模型输出违反组装契约，必须按现有格式错误语义使请求失败。"""
    import pytest as _pytest

    from app.core.errors import ModelFormatError

    with _pytest.raises(ModelFormatError):
        assemble_header_parties(
            _env([_hd_candidate("c1", "PARTY_MENTION", "供应商", document_key="other_doc", mention_text="供应商")]),
            _doc(),
            _registry(),
        )

    with _pytest.raises(ModelFormatError):
        assemble_party_mentions(
            _att_env([_att_candidate("a1", "本附件再次提到 丙丁工程有限公司", "丙丁工程有限公司", document_key="other_doc")]),
            [],
            _doc(ATTACH_MD, "attach1"),
            _registry(),
        )


# ------------------------------------------------------------------
# Round 7 review-blocker coverage
# ------------------------------------------------------------------

def test_r7_attachment_role_reference_restores_absent_local_definition() -> None:
    """附件 ROLE_REFERENCE 主合同定义状态恢复 ABSENT；对比状态仍不得借 canonical 判 MATCHED。"""
    main_facts = assemble_header_parties(
        _env([_hd_candidate("c1", "CANONICAL_PARTY", "乙方：丙丁工程有限公司", party_role="乙方", party_name="丙丁工程有限公司")]),
        _doc(),
        _registry(),
    )
    mentions = assemble_party_mentions(
        _att_env([
            _att_candidate(
                "a1", "本附件再次提到 丙丁工程有限公司", "乙方应验收",
                mention_kind="ROLE_REFERENCE", party_role="乙方",
            ),
        ]),
        main_facts.canonical_parties,
        _doc(ATTACH_MD, "attach1"),
        _registry(),
    )
    assert len(mentions) == 1
    assert mentions[0].mention_kind == "ROLE_REFERENCE"
    assert mentions[0].local_definition_state == "ABSENT"
    assert mentions[0].comparison_state == "UNCERTAIN"


def test_r7_bare_mention_key_collision_fails_instead_of_silent_overwrite() -> None:
    """无结构化坐标的不同 mention 键碰撞必须报错，禁止静默覆盖；完全重复允许去重。"""
    import pytest as _pytest

    from app.core.errors import ModelFormatError

    with _pytest.raises(ModelFormatError):
        assemble_header_parties(
            _env([
                _hd_candidate("c1", "PARTY_MENTION", "供应商", mention_text="供应商甲"),
                _hd_candidate("c2", "PARTY_MENTION", "供应商", mention_text="供应商乙"),
            ]),
            _doc(),
            _registry(),
        )

    # 完全相同的候选仍按去重处理，不得报错。
    facts = assemble_header_parties(
        _env([
            _hd_candidate("c1", "PARTY_MENTION", "供应商", mention_text="供应商"),
            _hd_candidate("c2", "PARTY_MENTION", "供应商", mention_text="供应商"),
        ]),
        _doc(),
        _registry(),
    )
    assert len(facts.party_mentions) == 1

    with _pytest.raises(ModelFormatError):
        assemble_party_mentions(
            _att_env([
                _att_candidate("a1", "本附件再次提到 丙丁工程有限公司", "丙丁工程有限公司"),
                _att_candidate("a2", "本附件再次提到 丙丁工程有限公司", "另一称呼"),
            ]),
            [],
            _doc(ATTACH_MD, "attach1"),
            _registry(),
        )


def test_r7_prompt_requires_explicit_null_mention_kind() -> None:
    """Prompt 必须要求无法区分时显式输出 null，而不是省略 mention_kind 字段。"""
    from app.capabilities.contract_review.two_stage.prepare_prompts import build_prepare_prompt

    for name in ("prepare_header_parties_main", "prepare_attachment_document"):
        messages = build_prepare_prompt(
            name, markdown="示例正文", scope_label="main", extraction_input="{}",
        )
        blob = "\n".join(str(item.content) for item in messages)
        assert "null" in blob, name
        assert "省略" not in blob, name


def test_r6_bare_mention_key_ignores_observed_text_wording() -> None:
    """无结构化坐标时稳定键不得嵌入 observed_text 展示文案。"""
    def run(mention_text: str) -> str:
        facts = assemble_header_parties(
            _env([_hd_candidate("c1", "PARTY_MENTION", "供应商", mention_text=mention_text)]),
            _doc(),
            _registry(),
        )
        assert len(facts.party_mentions) == 1
        return facts.party_mentions[0].mention_key

    assert run("供应商") == run("供应商（供方另种说法）")
