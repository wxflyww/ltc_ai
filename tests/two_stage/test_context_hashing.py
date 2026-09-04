from app.capabilities.contract_review.two_stage.hashing import (
    canonical_json_bytes,
    compute_context_digest,
    compute_document_set_hash,
    normalize_markdown,
    normalize_snapshot_name,
    parsed_content_sha256,
    sort_review_context,
)
from app.capabilities.contract_review.two_stage.schemas import ReviewContext, SourceSnapshot
from tests.two_stage.factories import clone_payload, valid_context_payload

import pytest


def _build_context_with_consistent_hashes() -> ReviewContext:
    payload = valid_context_payload()
    source = SourceSnapshot.model_validate(payload["source_snapshot"])
    payload["source_snapshot"]["document_set_hash"] = compute_document_set_hash(source)
    payload["context_digest"] = "sha256:" + "0" * 64

    context = ReviewContext.model_validate(payload)
    sorted_context = sort_review_context(context)
    context_payload = sorted_context.to_payload()
    context_payload["context_digest"] = compute_context_digest(context_payload)
    return ReviewContext.model_validate(context_payload)


def test_markdown_hash_normalizes_bom_newlines_and_unicode():
    left = "\ufeff# Caf\u00e9\r\n正文\r"
    right = "# Cafe\u0301\n正文\n"

    assert normalize_markdown(left) == normalize_markdown(right)
    assert parsed_content_sha256(left) == parsed_content_sha256(right)


def test_markdown_hash_preserves_spaces_blank_lines_and_markup():
    assert parsed_content_sha256("# A\n") != parsed_content_sha256("#  A\n")
    assert parsed_content_sha256("# A\n") != parsed_content_sha256("A\n")
    assert parsed_content_sha256("A\n\nB") != parsed_content_sha256("A\nB")


def test_snapshot_name_removes_path_and_outer_whitespace_only():
    assert normalize_snapshot_name(r"C:\tmp\ 技术协议 V1.0.MD ") == "技术协议 V1.0.MD"
    assert normalize_snapshot_name("path/技术协议 v1.0.md") == "技术协议 v1.0.md"


def test_canonical_json_uses_sorted_compact_utf8():
    assert canonical_json_bytes({"b": 1, "a": "中文"}) == '{"a":"中文","b":1}'.encode("utf-8")


def test_document_set_hash_is_attachment_order_independent():
    payload = valid_context_payload()
    first = SourceSnapshot.model_validate(payload["source_snapshot"])

    swapped = clone_payload(payload["source_snapshot"])
    swapped["attachments"] = list(reversed(swapped["attachments"]))
    second = SourceSnapshot.model_validate(swapped)

    assert compute_document_set_hash(first) == compute_document_set_hash(second)


def test_document_set_hash_changes_with_key_name_or_content():
    payload = valid_context_payload()
    baseline = SourceSnapshot.model_validate(payload["source_snapshot"])
    baseline_hash = compute_document_set_hash(baseline)

    changed_key = clone_payload(payload["source_snapshot"])
    changed_key["attachments"][0]["document_key"] = "uploaded:att-002"
    changed_name = clone_payload(payload["source_snapshot"])
    changed_name["attachments"][0]["filename"] = "new-name.md"
    changed_content = clone_payload(payload["source_snapshot"])
    changed_content["attachments"][0]["parsed_content_sha256"] = "sha256:" + "9" * 64

    assert compute_document_set_hash(SourceSnapshot.model_validate(changed_key)) != baseline_hash
    assert compute_document_set_hash(SourceSnapshot.model_validate(changed_name)) != baseline_hash
    assert compute_document_set_hash(SourceSnapshot.model_validate(changed_content)) != baseline_hash


def test_context_digest_ignores_existing_digest_field():
    context = _build_context_with_consistent_hashes()
    first_payload = context.to_payload()
    second_payload = clone_payload(first_payload)
    second_payload["context_digest"] = "sha256:" + "f" * 64

    assert compute_context_digest(first_payload) == compute_context_digest(second_payload)


def test_context_digest_is_identical_for_model_and_json_mapping():
    context = _build_context_with_consistent_hashes()

    assert compute_context_digest(context) == compute_context_digest(context.to_payload())


def test_context_digest_distinguishes_nested_null_from_absent_key():
    payload_with_null = valid_context_payload()
    payload_with_null["shared_facts"]["copy_terms"]["data"]["overall_total_statement_key"] = None

    payload_without_key = clone_payload(payload_with_null)
    payload_without_key["shared_facts"]["copy_terms"]["data"].pop("overall_total_statement_key", None)

    assert compute_context_digest(payload_with_null) != compute_context_digest(payload_without_key)


def test_sorted_payload_and_digest_are_stable_when_same_document_evidence_input_order_swaps():
    payload_a = valid_context_payload()
    payload_a["evidence_index"]["items"] = [
        {
            "evidence_id": "evidence:main:header-name",
            "document_key": "main",
            "source_locator": "markdown-chars:0-4",
            "quote": "采购合同",
        },
        {
            "evidence_id": "evidence:main:b",
            "document_key": "main",
            "source_locator": "markdown-chars:10-12",
            "quote": "乙方",
        },
        {
            "evidence_id": "evidence:main:a",
            "document_key": "main",
            "source_locator": "markdown-chars:2-4",
            "quote": "甲方",
        },
    ]

    payload_b = clone_payload(payload_a)
    payload_b["evidence_index"]["items"] = list(reversed(payload_b["evidence_index"]["items"]))

    context_a = ReviewContext.model_validate(payload_a)
    context_b = ReviewContext.model_validate(payload_b)

    sorted_a = sort_review_context(context_a).to_payload()
    sorted_b = sort_review_context(context_b).to_payload()

    assert sorted_a == sorted_b
    assert compute_context_digest(context_a) == compute_context_digest(context_b)


def _obs(raw: str) -> dict:
    """构造一个实质观测对象（PRESENT_VALUE / VALID）。"""
    return {
        "presence": "PRESENT_VALUE",
        "normalization_state": "VALID",
        "observations": [
            {
                "raw_text": raw,
                "normalized_value": raw,
                "evidence_ids": ["evidence:main:header-name"],
            }
       ],
   }


def _absent() -> dict:
    """构造一个 ABSENT 观测对象。"""
    return {
        "presence": "ABSENT",
        "normalization_state": "NOT_APPLICABLE",
        "observations": [],
    }


def _obs_int(value: int) -> dict:
    """构造一个整型 PRESENT_VALUE / VALID 观测对象。"""
    return {
        "presence": "PRESENT_VALUE",
        "normalization_state": "VALID",
        "observations": [
            {
                "raw_text": str(value),
                "normalized_value": value,
                "evidence_ids": ["evidence:main:header-name"],
            }
        ],
    }


def _nested(payload: dict, path) -> list:
    """按键路径取出嵌套集合。"""
    node = payload
    for key in path:
        node = node[key]
    return node


def _populate_six_domains(payload: dict) -> None:
    """填充六域全部数组，每个数组至少两个可区分、引用闭合的合法对象。"""
    ev = ["evidence:main:header-name"]

    parties = payload["shared_facts"]["parties"]["data"]
    parties["canonical_parties"] = [
        {
            "party_key": "party:alpha",
            "declared_name": _obs("Party Alpha"),
            "declared_designations": [
                {
                    "designation_key": "designation:alpha",
                    "kind": "CONTRACT_ROLE",
                    "text": "PARTY ALPHA",
                    "evidence_ids": ev,
                }
            ],
            "definition_evidence_ids": ev,
        },
        {
            "party_key": "party:beta",
            "declared_name": _obs("Party Beta"),
            "declared_designations": [
                {
                    "designation_key": "designation:beta",
                    "kind": "CONTRACT_ROLE",
                    "text": "PARTY BETA",
                    "evidence_ids": ev,
                }
            ],
            "definition_evidence_ids": ev,
        },
    ]
    parties["party_mentions"] = [
        {
            "mention_key": "mention:1",
            "document_key": "main",
            "mention_kind": "PARTY_DEFINITION",
            "observed_text": "Party Alpha",
            "referenced_designation_keys": ["designation:alpha"],
            "candidate_party_keys": ["party:alpha"],
            "local_definition_state": "PRESENT",
            "comparison_state": "MATCHED_DECLARATION",
            "evidence_ids": ev,
        },
        {
            "mention_key": "mention:2",
            "document_key": "main",
            "mention_kind": "PARTY_DEFINITION",
            "observed_text": "Party Beta",
            "referenced_designation_keys": ["designation:beta"],
            "candidate_party_keys": ["party:beta"],
            "local_definition_state": "PRESENT",
            "comparison_state": "MATCHED_DECLARATION",
            "evidence_ids": ev,
        },
    ]

    sig = payload["shared_facts"]["signature"]["data"]
    sig["signature_blocks"] = [
        {
            "signature_block_key": "sig:1",
            "document_key": "main",
            "party_binding_state": "BOUND",
            "party_key": "party:alpha",
            "candidate_party_keys": [],
            "local_company_name": _absent(),
            "evidence_ids": ev,
        },
        {
            "signature_block_key": "sig:2",
            "document_key": "main",
            "party_binding_state": "BOUND",
            "party_key": "party:beta",
            "candidate_party_keys": [],
            "local_company_name": _absent(),
            "evidence_ids": ev,
        },
    ]
    sig["signer_slots"] = [
        {
            "signer_slot_key": "slot:1",
            "signature_block_key": "sig:1",
            "role_text": "Legal Rep",
            "role_state": "ELIGIBLE_SIGNER",
            "presence": "PRESENT_VALUE",
            "signer_keys": ["signer:alpha-1"],
            "identity_number_keys": ["idnum:alpha-1"],
            "evidence_ids": ev,
        },
        {
            "signer_slot_key": "slot:2",
            "signature_block_key": "sig:2",
            "role_text": "Legal Rep",
            "role_state": "ELIGIBLE_SIGNER",
            "presence": "PRESENT_VALUE",
            "signer_keys": ["signer:beta-1"],
            "identity_number_keys": ["idnum:beta-1"],
            "evidence_ids": ev,
        },
    ]
    sig["alternative_signer_groups"] = [
        {
            "signer_group_key": "grp:1",
            "signer_slot_keys": ["slot:1"],
            "relation_state": "CONFIRMED",
            "evidence_ids": ev,
        },
        {
            "signer_group_key": "grp:2",
            "signer_slot_keys": ["slot:2"],
            "relation_state": "CONFIRMED",
            "evidence_ids": ev,
        },
    ]
    sig["signer_candidates"] = [
        {
            "signer_key": "signer:alpha-1",
            "signer_slot_key": "slot:1",
            "raw_name": "Alpha Person",
            "normalized_name": "Alpha Person",
            "evidence_ids": ev,
        },
        {
            "signer_key": "signer:beta-1",
            "signer_slot_key": "slot:2",
            "raw_name": "Beta Person",
            "normalized_name": "Beta Person",
            "evidence_ids": ev,
        },
    ]
    sig["identity_number_candidates"] = [
        {
            "identity_number_key": "idnum:alpha-1",
            "signer_slot_key": "slot:1",
            "raw_text": "110101199001011234",
            "normalized_value": "110101199001011234",
            "normalization_state": "VALID",
            "evidence_ids": ev,
        },
        {
            "identity_number_key": "idnum:beta-1",
            "signer_slot_key": "slot:2",
            "raw_text": "110101199901019876",
            "normalized_value": "110101199901019876",
            "normalization_state": "VALID",
            "evidence_ids": ev,
        },
    ]
    sig["person_id_relations"] = [
        {
            "signer_key": "signer:alpha-1",
            "identity_number_key": "idnum:alpha-1",
            "association_state": "DIRECT",
            "evidence_ids": ev,
        },
        {
            "signer_key": "signer:beta-1",
            "identity_number_key": "idnum:beta-1",
            "association_state": "DIRECT",
            "evidence_ids": ev,
        },
    ]
    sig["signing_date_observations"] = [
        {
            "signature_date_key": "date:1",
            "signature_block_key": "sig:1",
            "party_key": "party:alpha",
            "field": _obs("2026-01-01"),
        },
        {
            "signature_date_key": "date:2",
            "signature_block_key": "sig:2",
            "party_key": "party:beta",
            "field": _obs("2026-06-01"),
        },
    ]
    sig["account_observations"] = [
        {
            "field_observation_key": "fo:acc:1",
            "document_key": "main",
            "signature_block_key": "sig:1",
            "party_binding_state": "BOUND",
            "party_key": "party:alpha",
            "candidate_party_keys": [],
            "field_kind": "BANK_ACCOUNT",
            "purpose_state": "CONFIRMED",
            "field": _obs("6222020200112233445"),
        },
        {
            "field_observation_key": "fo:acc:2",
            "document_key": "main",
            "signature_block_key": "sig:2",
            "party_binding_state": "BOUND",
            "party_key": "party:beta",
            "candidate_party_keys": [],
            "field_kind": "BANK_ACCOUNT",
            "purpose_state": "CONFIRMED",
            "field": _obs("6222020200556677889"),
        },
    ]
    sig["contact_observations"] = [
        {
            "field_observation_key": "fo:ct:1",
            "document_key": "main",
            "signature_block_key": "sig:1",
            "party_binding_state": "BOUND",
            "party_key": "party:alpha",
            "candidate_party_keys": [],
            "field_kind": "ADDRESS",
            "purpose_state": "CONFIRMED",
            "field": _obs("1 Alpha Road"),
        },
        {
            "field_observation_key": "fo:ct:2",
            "document_key": "main",
            "signature_block_key": "sig:2",
            "party_binding_state": "BOUND",
            "party_key": "party:beta",
            "candidate_party_keys": [],
            "field_kind": "ADDRESS",
            "purpose_state": "CONFIRMED",
            "field": _obs("2 Beta Avenue"),
        },
    ]

    amount = payload["shared_facts"]["amount_payment"]["data"]
    amount["amounts"] = [
        {
            "amount_key": "amount:1",
            "document_key": "main",
            "semantic_role": _obs("Total Price"),
            "numeric_amount": _obs("100000"),
            "uppercase_amount": _absent(),
            "currency": _absent(),
            "tax_treatment": _absent(),
            "evidence_ids": ev,
        },
        {
            "amount_key": "amount:2",
            "document_key": "main",
            "semantic_role": _obs("Deposit"),
            "numeric_amount": _obs("30000"),
            "uppercase_amount": _absent(),
            "currency": _absent(),
            "tax_treatment": _absent(),
            "evidence_ids": ev,
        },
    ]
    amount["payment_methods"] = [
        {
            "payment_method_key": "pm:1",
            "raw_text": "Bank Transfer",
            "normalized_value": "BANK_TRANSFER",
            "evidence_ids": ev,
        },
        {
            "payment_method_key": "pm:2",
            "raw_text": "Cash",
            "normalized_value": "CASH",
            "evidence_ids": ev,
        },
    ]
    amount["payment_stages"] = [
        {
            "payment_stage_key": "stage:1",
            "name": _obs("Advance"),
            "sequence": _obs_int(1),
            "ratio_percent": _obs("30"),
            "amount_keys": ["amount:1"],
            "trigger_condition": _absent(),
            "payment_term": _absent(),
            "payment_method_keys": ["pm:1"],
            "evidence_ids": ev,
        },
        {
            "payment_stage_key": "stage:2",
            "name": _obs("Delivery"),
            "sequence": _obs_int(2),
            "ratio_percent": _obs("40"),
            "amount_keys": ["amount:2"],
            "trigger_condition": _absent(),
            "payment_term": _absent(),
            "payment_method_keys": ["pm:2"],
            "evidence_ids": ev,
        },
    ]
    amount["amount_relations"] = [
        {
            "amount_relation_key": "rel-am:1",
            "amount_key": "amount:1",
            "relation_kind": "PAYMENT_STAGE",
            "relation_state": "CONFIRMED",
            "payment_stage_key": "stage:1",
            "evidence_ids": ev,
        },
        {
            "amount_relation_key": "rel-am:2",
            "amount_key": "amount:2",
            "relation_kind": "PAYMENT_STAGE",
            "relation_state": "CONFIRMED",
            "payment_stage_key": "stage:2",
            "evidence_ids": ev,
        },
    ]

    copy = payload["shared_facts"]["copy_terms"]["data"]
    copy["statements"] = [
        {
            "statement_key": "st:1",
            "scope_key": "scope:1",
            "document_key": "main",
            "raw_text": "three copies",
            "count": _obs_int(3),
            "evidence_ids": ev,
        },
        {
            "statement_key": "st:2",
            "scope_key": "scope:2",
            "document_key": "main",
            "raw_text": "four copies",
            "count": _obs_int(4),
            "evidence_ids": ev,
        },
    ]
    copy["overall_total_statement_key"] = "st:1"
    copy["allocations"] = [
        {
            "allocation_key": "allocation:1",
            "statement_key": "st:1",
            "candidate_party_keys": ["party:alpha"],
            "allocation_semantics": "EACH",
            "evidence_ids": ev,
        },
        {
            "allocation_key": "allocation:2",
            "statement_key": "st:2",
            "candidate_party_keys": ["party:beta"],
            "allocation_semantics": "EACH",
            "evidence_ids": ev,
        },
    ]

    attach = payload["shared_facts"]["attachment_manifest"]["data"]
    attach["declarations"] = [
        {
            "attachment_declaration_key": "decl:1",
            "title": _obs("Attachment One"),
            "ordinal": _absent(),
            "evidence_ids": ev,
        },
        {
            "attachment_declaration_key": "decl:2",
            "title": _obs("Attachment Two"),
            "ordinal": _absent(),
            "evidence_ids": ev,
        },
    ]
    attach["logical_attachment_candidates"] = [
        {
            "logical_attachment_candidate_key": "logical:1",
            "parent_document_key": "uploaded:att-001",
            "title": _obs("Logical One"),
            "source_locator": "markdown-chars:0-4",
            "evidence_ids": ev,
        },
        {
            "logical_attachment_candidate_key": "logical:2",
            "parent_document_key": "embedded:main:001",
            "title": _obs("Logical Two"),
            "source_locator": "markdown-chars:10-16",
            "evidence_ids": ev,
        },
    ]
    attach["links"] = [
        {
            "attachment_relation_key": "rel-att:1",
            "attachment_declaration_key": "decl:1",
            "candidate_document_keys": ["uploaded:att-001"],
            "relation_state": "LINKED",
            "evidence_ids": ev,
        },
       {
           "attachment_relation_key": "rel-att:2",
           "attachment_declaration_key": "decl:2",
           "candidate_document_keys": ["embedded:main:001"],
           "relation_state": "LINKED",
           "evidence_ids": ev,
       },
   ]

    payload["preparation_issues"] = [
        {
            "preparation_issue_key": "pi:1",
            "code": "SUSPECTED_DUPLICATE",
            "message": "attachment likely duplicate one",
            "related_document_keys": ["uploaded:att-001", "embedded:main:001"],
            "evidence_ids": ev,
        },
        {
            "preparation_issue_key": "pi:2",
            "code": "SUSPECTED_DUPLICATE",
            "message": "attachment likely duplicate two",
            "related_document_keys": ["uploaded:att-001"],
            "evidence_ids": ev,
        },
    ]


# Paths to every two-or-more-element array across the six domains, relations and prep issues.
_SWAP_PATHS = [
    ("shared_facts", "parties", "data", "canonical_parties"),
    ("shared_facts", "parties", "data", "party_mentions"),
    ("shared_facts", "signature", "data", "signature_blocks"),
    ("shared_facts", "signature", "data", "signer_slots"),
    ("shared_facts", "signature", "data", "alternative_signer_groups"),
    ("shared_facts", "signature", "data", "signer_candidates"),
    ("shared_facts", "signature", "data", "identity_number_candidates"),
    ("shared_facts", "signature", "data", "person_id_relations"),
    ("shared_facts", "signature", "data", "signing_date_observations"),
    ("shared_facts", "signature", "data", "account_observations"),
    ("shared_facts", "signature", "data", "contact_observations"),
    ("shared_facts", "amount_payment", "data", "amounts"),
    ("shared_facts", "amount_payment", "data", "payment_methods"),
    ("shared_facts", "amount_payment", "data", "payment_stages"),
    ("shared_facts", "amount_payment", "data", "amount_relations"),
    ("shared_facts", "copy_terms", "data", "statements"),
    ("shared_facts", "copy_terms", "data", "allocations"),
    ("shared_facts", "attachment_manifest", "data", "declarations"),
    ("shared_facts", "attachment_manifest", "data", "logical_attachment_candidates"),
    ("shared_facts", "attachment_manifest", "data", "links"),
    ("preparation_issues",),
]


@pytest.mark.parametrize("path", _SWAP_PATHS)
def test_sorted_payload_and_digest_are_stable_when_six_domain_arrays_swap(path):
    payload_a = valid_context_payload()
    _populate_six_domains(payload_a)
    arr_a = _nested(payload_a, path)
    assert len(arr_a) >= 2
    assert arr_a != list(reversed(arr_a))

    payload_b = clone_payload(payload_a)
    arr_b = _nested(payload_b, path)
    arr_b[:] = list(reversed(arr_b))
    assert _nested(payload_a, path) != _nested(payload_b, path)

    context_a = ReviewContext.model_validate(payload_a)
    context_b = ReviewContext.model_validate(payload_b)
    assert sort_review_context(context_a).to_payload() == sort_review_context(context_b).to_payload()
    assert compute_context_digest(context_a) == compute_context_digest(context_b)


def test_sorted_payload_and_digest_are_stable_when_coverage_swaps():
    payload_a = valid_context_payload()
    _populate_six_domains(payload_a)
    cov_a = payload_a["shared_facts"]["parties"]["coverage"]
    assert len(cov_a) >= 2
    assert cov_a != list(reversed(cov_a))

    payload_b = clone_payload(payload_a)
    payload_b["shared_facts"]["parties"]["coverage"] = list(reversed(cov_a))

    context_a = ReviewContext.model_validate(payload_a)
    context_b = ReviewContext.model_validate(payload_b)
    assert sort_review_context(context_a).to_payload() == sort_review_context(context_b).to_payload()
    assert compute_context_digest(context_a) == compute_context_digest(context_b)


def _make_partial_amount_payment(payload: dict) -> None:
    ev = ["evidence:main:header-name"]
    domain = payload["shared_facts"]["amount_payment"]
    domain["state"] = "PARTIAL"
    domain["coverage"] = [
        {
            "document_key": "main",
            "state": "PARTIAL",
            "affected_fact_kinds": ["amount"],
            "fact_issue_keys": ["fi:1", "fi:2"],
        }
    ]
    domain["issues"] = [
        {
            "fact_issue_key": "fi:1",
            "code": "AMT_PARTIAL",
            "message": "amount issue one",
            "related_document_keys": ["main"],
            "affected_fact_kinds": ["amount"],
            "evidence_ids": ev,
        },
        {
            "fact_issue_key": "fi:2",
            "code": "AMT_PARTIAL",
            "message": "amount issue two",
            "related_document_keys": ["main"],
            "affected_fact_kinds": ["amount"],
            "evidence_ids": ev,
        },
    ]


def test_sorted_payload_and_digest_are_stable_when_fact_issue_order_swaps():
    payload_a = valid_context_payload()
    _populate_six_domains(payload_a)
    _make_partial_amount_payment(payload_a)
    issues_a = payload_a["shared_facts"]["amount_payment"]["issues"]
    assert len(issues_a) >= 2
    assert issues_a != list(reversed(issues_a))

    payload_b = clone_payload(payload_a)
    payload_b["shared_facts"]["amount_payment"]["issues"] = list(reversed(issues_a))

    context_a = ReviewContext.model_validate(payload_a)
    context_b = ReviewContext.model_validate(payload_b)
    assert sort_review_context(context_a).to_payload() == sort_review_context(context_b).to_payload()
    assert compute_context_digest(context_a) == compute_context_digest(context_b)


def test_sorted_payload_and_digest_are_stable_when_observation_order_swaps():
    payload_a = valid_context_payload()
    _populate_six_domains(payload_a)
    ev = ["evidence:main:header-name"]
    name = payload_a["shared_facts"]["header"]["data"]["contract_identity"]["name"]
    name["observations"] = [
        {
            "raw_text": "Purchase Contract",
            "normalized_value": "Purchase Contract",
            "specificity": "SPECIFIC",
            "evidence_ids": ev,
        },
        {
            "raw_text": "Sales Agreement",
            "normalized_value": "Sales Agreement",
            "specificity": "GENERIC",
            "evidence_ids": ev,
        },
    ]
    obs_a = name["observations"]
    assert len(obs_a) >= 2
    assert obs_a != list(reversed(obs_a))

    payload_b = clone_payload(payload_a)
    payload_b["shared_facts"]["header"]["data"]["contract_identity"]["name"]["observations"] = list(reversed(obs_a))

    context_a = ReviewContext.model_validate(payload_a)
    context_b = ReviewContext.model_validate(payload_b)
    assert sort_review_context(context_a).to_payload() == sort_review_context(context_b).to_payload()
    assert compute_context_digest(context_a) == compute_context_digest(context_b)
