from __future__ import annotations

from typing import Any

from app.capabilities.contract_review.two_stage.evidence import EvidenceRegistry
from app.capabilities.contract_review.two_stage.extract_header_parties import (
    HeaderPartiesExtraction,
    PreparedDocument,
    assemble_header_parties,
    assemble_party_mentions,
    build_header_fact_domain,
    build_parties_fact_domain,
    extract_attachment_party_mentions,
)
from app.capabilities.contract_review.two_stage.prepare_model import (
    AttachmentCandidate,
    HeaderPartiesCandidate,
    PrepareModelEnvelope,
)
from app.capabilities.contract_review.two_stage.schemas import FactIssue


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
)


ATTACH_MD = (
    "本附件定义负责人：某某项目部\n"
    "本附件再次提到 丙丁工程有限公司\n"
)


def _registry() -> EvidenceRegistry:
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
    payload: dict[str, Any] = {"candidates": candidates, "source_gaps": gaps or []}
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
) -> dict[str, Any]:
    return {
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
    assert mention.local_definition_state == "PRESENT"
    assert len(mention.candidate_party_keys) == 1


def test_main_party_mention_unmatched_is_outside_declared() -> None:
    facts = assemble_header_parties(
        _env(
            [
                _hd_candidate("c1", "CANONICAL_PARTY", "甲方：甲乙科技有限公司", party_role="甲方", party_name="甲乙科技有限公司"),
                _hd_candidate("c2", "PARTY_MENTION", "正文中提及 丙丁工程有限公司", party_name="丙丁工程有限公司", mention_text="丙丁工程有限公司"),
            ]
        ),
        _doc(),
        _registry(),
    )
    mention = facts.party_mentions[0]
    assert mention.mention_kind == "PARTY_DEFINITION"
    assert mention.comparison_state == "OUTSIDE_DECLARED_SET"
    assert mention.local_definition_state == "PRESENT"
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
    assert mentions[0].local_definition_state == "ABSENT"
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


def _att_candidate(ref: str, quote: str, mention_text: str, *, document_key: str = "attach1") -> dict[str, Any]:
    return {
        "candidate_ref": ref,
        "candidate_kind": "PARTY_MENTION",
        "document_key": document_key,
        "quote": quote,
        "mention_text": mention_text,
    }


def test_attachment_local_definition_only_forms_mention() -> None:
    main_facts = assemble_header_parties(
        _env([_hd_candidate("c1", "CANONICAL_PARTY", "甲方：甲乙科技有限公司", party_role="甲方", party_name="甲乙科技有限公司")]),
        _doc(),
        _registry(),
    )
    mentions = assemble_party_mentions(
        _att_env([_att_candidate("a1", "本附件定义负责人：某某项目部", "某某项目部")]),
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
