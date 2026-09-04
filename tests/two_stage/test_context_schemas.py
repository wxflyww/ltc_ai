import pytest
from pydantic import ValidationError

from app.capabilities.contract_review.two_stage.schemas import ReviewContext
from tests.two_stage.factories import clone_payload, sha256, valid_context_payload


def test_review_context_requires_exact_six_domains():
    payload = valid_context_payload()
    payload["shared_facts"].pop("copy_terms")

    with pytest.raises(ValidationError, match="copy_terms"):
        ReviewContext.model_validate(payload)


def test_review_context_rejects_extra_fact_domain():
    payload = valid_context_payload()
    payload["shared_facts"]["extra_domain"] = payload["shared_facts"]["header"]

    with pytest.raises(ValidationError, match="extra_domain"):
        ReviewContext.model_validate(payload)


def test_observed_field_absent_requires_not_applicable_and_empty_observations():
    payload = valid_context_payload()
    payload["shared_facts"]["header"]["data"]["contract_identity"]["number"] = {
        "presence": "ABSENT",
        "normalization_state": "VALID",
        "observations": [
            {
                "raw_text": "CN-001",
                "normalized_value": "CN-001",
                "evidence_ids": ["evidence:main:number"],
            }
        ],
    }

    with pytest.raises(ValidationError, match="ABSENT"):
        ReviewContext.model_validate(payload)


def test_observed_field_present_empty_requires_empty_observation_text_and_not_applicable():
    payload = valid_context_payload()
    payload["shared_facts"]["header"]["data"]["project_identity"]["name"] = {
        "presence": "PRESENT_EMPTY",
        "normalization_state": "VALID",
        "observations": [
            {
                "raw_text": "项目名称",
                "specificity": "UNCERTAIN",
                "evidence_ids": ["evidence:main:project-name"],
            }
        ],
    }

    with pytest.raises(ValidationError, match="PRESENT_EMPTY"):
        ReviewContext.model_validate(payload)


def test_observed_field_present_value_requires_non_empty_observations():
    payload = valid_context_payload()
    payload["shared_facts"]["header"]["data"]["contract_identity"]["name"] = {
        "presence": "PRESENT_VALUE",
        "normalization_state": "VALID",
        "observations": [],
    }

    with pytest.raises(ValidationError, match="PRESENT_VALUE"):
        ReviewContext.model_validate(payload)


def test_observed_field_uncertain_requires_candidates_and_evidence():
    payload = valid_context_payload()
    payload["shared_facts"]["header"]["data"]["signing_location"] = {
        "presence": "UNCERTAIN",
        "normalization_state": "UNCERTAIN",
        "observations": [],
    }

    with pytest.raises(ValidationError, match="UNCERTAIN"):
        ReviewContext.model_validate(payload)


def test_fact_domain_complete_coverage_must_not_reference_fact_issue():
    payload = valid_context_payload()
    payload["shared_facts"]["signature"]["coverage"][0]["fact_issue_keys"] = ["fact-issue:1"]

    with pytest.raises(ValidationError, match="COMPLETE"):
        ReviewContext.model_validate(payload)


def test_fact_domain_partial_coverage_requires_fact_issue_reference_and_issue_body():
    payload = valid_context_payload()
    payload["shared_facts"]["signature"]["state"] = "PARTIAL"
    payload["shared_facts"]["signature"]["coverage"][0]["state"] = "PARTIAL"
    payload["shared_facts"]["signature"]["coverage"][0]["fact_issue_keys"] = []

    with pytest.raises(ValidationError, match="fact_issue_keys"):
        ReviewContext.model_validate(payload)


def test_fact_domain_partial_references_must_resolve_to_same_domain_issue_keys():
    payload = valid_context_payload()
    payload["shared_facts"]["signature"]["state"] = "PARTIAL"
    payload["shared_facts"]["signature"]["coverage"][0]["state"] = "PARTIAL"
    payload["shared_facts"]["signature"]["coverage"][0]["affected_fact_kinds"] = ["signer_slots"]
    payload["shared_facts"]["signature"]["coverage"][0]["fact_issue_keys"] = ["fact-issue:missing"]
    payload["shared_facts"]["signature"]["issues"] = [
        {
            "fact_issue_key": "fact-issue:other",
            "code": "SIG_PARTIAL",
            "message": "签章附件表格列丢失",
            "related_document_keys": ["uploaded:att-001"],
            "affected_fact_kinds": ["signer_slots"],
            "evidence_ids": [],
        }
    ]

    with pytest.raises(ValidationError, match="fact_issue_key"):
        ReviewContext.model_validate(payload)


def test_evidence_index_must_be_global_unique_and_reference_existing_documents():
    payload = valid_context_payload()
    payload["evidence_index"]["items"] = [
        {
            "evidence_id": "evidence:dup",
            "document_key": "main",
            "source_locator": "markdown-chars:0-4",
            "quote": "采购合同",
        },
        {
            "evidence_id": "evidence:dup",
            "document_key": "not-exists",
            "source_locator": "markdown-chars:4-8",
            "quote": "正文",
        },
    ]

    with pytest.raises(ValidationError, match="evidence_id"):
        ReviewContext.model_validate(payload)


def test_prepare_issue_requires_non_empty_related_documents():
    payload = valid_context_payload()
    payload["preparation_issues"] = [
        {
            "preparation_issue_key": "prep-issue:dup",
            "code": "SUSPECTED_DUPLICATE",
            "message": "附件疑似重复",
            "related_document_keys": [],
            "evidence_ids": [],
        }
    ]

    with pytest.raises(ValidationError, match="related_document_keys"):
        ReviewContext.model_validate(payload)


def test_context_accepts_strongly_typed_six_domain_payload():
    payload = valid_context_payload()

    context = ReviewContext.model_validate(payload)

    dumped = context.to_payload()
    assert dumped["schema_version"] == "review-context/v1"
    assert set(dumped["shared_facts"].keys()) == {
        "header",
        "parties",
        "signature",
        "amount_payment",
        "copy_terms",
        "attachment_manifest",
    }
    assert "review_context" not in dumped


def test_context_rejects_sha256_format_violations_in_top_level_digests():
    payload = clone_payload(valid_context_payload())
    payload["source_snapshot"]["document_set_hash"] = sha256("A")

    with pytest.raises(ValidationError, match="document_set_hash"):
        ReviewContext.model_validate(payload)


def test_attachment_relation_linked_rejects_multiple_candidate_documents():
    payload = valid_context_payload()
    payload["shared_facts"]["attachment_manifest"]["data"]["declarations"] = [
        {
            "attachment_declaration_key": "decl:1",
            "title": {
                "presence": "PRESENT_VALUE",
                "normalization_state": "VALID",
                "observations": [
                    {
                        "raw_text": "附件一",
                        "normalized_value": "附件一",
                        "evidence_ids": ["evidence:main:header-name"],
                    }
                ],
            },
            "ordinal": {
                "presence": "ABSENT",
                "normalization_state": "NOT_APPLICABLE",
                "observations": [],
            },
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]
    payload["shared_facts"]["attachment_manifest"]["data"]["links"] = [
        {
            "attachment_relation_key": "rel:1",
            "attachment_declaration_key": "decl:1",
            "candidate_document_keys": ["uploaded:att-001", "embedded:main:001"],
            "relation_state": "LINKED",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]

    with pytest.raises(ValidationError, match="LINKED"):
        ReviewContext.model_validate(payload)


def test_review_context_rejects_attachment_relation_candidate_document_outside_snapshot():
    payload = valid_context_payload()
    payload["shared_facts"]["attachment_manifest"]["data"]["declarations"] = [
        {
            "attachment_declaration_key": "decl:1",
            "title": {
                "presence": "PRESENT_VALUE",
                "normalization_state": "VALID",
                "observations": [
                    {
                        "raw_text": "附件一",
                        "normalized_value": "附件一",
                        "evidence_ids": ["evidence:main:header-name"],
                    }
                ],
            },
            "ordinal": {
                "presence": "ABSENT",
                "normalization_state": "NOT_APPLICABLE",
                "observations": [],
            },
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]
    payload["shared_facts"]["attachment_manifest"]["data"]["links"] = [
        {
            "attachment_relation_key": "rel:1",
            "attachment_declaration_key": "decl:1",
            "candidate_document_keys": ["uploaded:not-exists"],
            "relation_state": "LINKED",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]

    with pytest.raises(ValidationError, match="candidate_document_key"):
        ReviewContext.model_validate(payload)


def test_review_context_rejects_signature_party_key_not_in_canonical_parties():
    payload = valid_context_payload()
    payload["shared_facts"]["signature"]["data"]["signature_blocks"] = [
        {
            "signature_block_key": "sig-block:1",
            "document_key": "main",
            "party_binding_state": "BOUND",
            "party_key": "party:not-exists",
            "candidate_party_keys": [],
            "local_company_name": {
                "presence": "ABSENT",
                "normalization_state": "NOT_APPLICABLE",
                "observations": [],
            },
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]

    with pytest.raises(ValidationError, match="party_key"):
        ReviewContext.model_validate(payload)


def test_review_context_rejects_logical_attachment_parent_document_outside_snapshot():
    payload = valid_context_payload()
    payload["shared_facts"]["attachment_manifest"]["data"]["logical_attachment_candidates"] = [
        {
            "logical_attachment_candidate_key": "logical:1",
            "parent_document_key": "uploaded:not-exists",
            "title": {
                "presence": "PRESENT_VALUE",
                "normalization_state": "VALID",
                "observations": [
                    {
                        "raw_text": "逻辑附件",
                        "normalized_value": "逻辑附件",
                        "evidence_ids": ["evidence:main:header-name"],
                    }
                ],
            },
            "source_locator": "markdown-chars:0-4",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]

    with pytest.raises(ValidationError, match="parent_document_key"):
        ReviewContext.model_validate(payload)


def test_review_context_rejects_party_mention_document_key_outside_snapshot():
    payload = valid_context_payload()
    payload["shared_facts"]["parties"]["data"]["party_mentions"] = [
        {
            "mention_key": "mention:1",
            "document_key": "uploaded:not-exists",
            "mention_kind": "PARTY_DEFINITION",
            "observed_text": "甲方",
            "local_definition_state": "PRESENT",
            "comparison_state": "MATCHED_DECLARATION",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]

    with pytest.raises(ValidationError, match="document_key"):
        ReviewContext.model_validate(payload)


def test_review_context_rejects_signer_slot_signer_key_not_in_candidates():
    payload = valid_context_payload()
    payload["shared_facts"]["signature"]["data"]["signature_blocks"] = [
        {
            "signature_block_key": "sig-block:1",
            "document_key": "main",
            "party_binding_state": "BOUND",
            "party_key": "party:1",
            "candidate_party_keys": [],
            "local_company_name": {
                "presence": "ABSENT",
                "normalization_state": "NOT_APPLICABLE",
                "observations": [],
            },
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]
    payload["shared_facts"]["signature"]["data"]["signer_slots"] = [
        {
            "signer_slot_key": "slot:1",
            "signature_block_key": "sig-block:1",
            "role_text": "法定代表人",
            "role_state": "ELIGIBLE_SIGNER",
            "presence": "PRESENT_VALUE",
            "signer_keys": ["signer:not-exists"],
            "identity_number_keys": [],
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]

    with pytest.raises(ValidationError, match="signer_key"):
        ReviewContext.model_validate(payload)


def test_review_context_rejects_signer_slot_identity_number_key_not_in_candidates():
    payload = valid_context_payload()
    payload["shared_facts"]["signature"]["data"]["signature_blocks"] = [
        {
            "signature_block_key": "sig-block:1",
            "document_key": "main",
            "party_binding_state": "BOUND",
            "party_key": "party:1",
            "candidate_party_keys": [],
            "local_company_name": {
                "presence": "ABSENT",
                "normalization_state": "NOT_APPLICABLE",
                "observations": [],
            },
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]
    payload["shared_facts"]["signature"]["data"]["signer_slots"] = [
        {
            "signer_slot_key": "slot:1",
            "signature_block_key": "sig-block:1",
            "role_text": "法定代表人",
            "role_state": "ELIGIBLE_SIGNER",
            "presence": "PRESENT_VALUE",
            "signer_keys": [],
            "identity_number_keys": ["idnum:not-exists"],
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]

    with pytest.raises(ValidationError, match="identity_number_key"):
        ReviewContext.model_validate(payload)


def test_review_context_rejects_attachment_relation_candidate_main():
    payload = valid_context_payload()
    payload["shared_facts"]["attachment_manifest"]["data"]["declarations"] = [
        {
            "attachment_declaration_key": "decl:1",
            "title": {
                "presence": "PRESENT_VALUE",
                "normalization_state": "VALID",
                "observations": [
                    {
                        "raw_text": "附件一",
                        "normalized_value": "附件一",
                        "evidence_ids": ["evidence:main:header-name"],
                    }
                ],
            },
            "ordinal": {
                "presence": "ABSENT",
                "normalization_state": "NOT_APPLICABLE",
                "observations": [],
            },
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]
    payload["shared_facts"]["attachment_manifest"]["data"]["links"] = [
        {
            "attachment_relation_key": "rel:1",
            "attachment_declaration_key": "decl:1",
            "candidate_document_keys": ["main"],
            "relation_state": "LINKED",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]

    with pytest.raises(ValidationError, match="candidate_document_key"):
        ReviewContext.model_validate(payload)


def _canonical_party(party_key: str, designation_key: str) -> dict:
    return {
        "party_key": party_key,
        "declared_name": {
            "presence": "PRESENT_VALUE",
            "normalization_state": "VALID",
            "observations": [
                {
                    "raw_text": "甲方",
                    "normalized_value": "甲方",
                    "evidence_ids": ["evidence:main:header-name"],
                }
            ],
        },
        "declared_designations": [
            {
                "designation_key": designation_key,
                "kind": "CONTRACT_ROLE",
                "text": "甲方",
                "evidence_ids": ["evidence:main:header-name"],
            }
        ],
        "definition_evidence_ids": ["evidence:main:header-name"],
    }


def test_review_context_rejects_duplicate_designation_key_across_parties():
    payload = valid_context_payload()
    payload["shared_facts"]["parties"]["data"]["canonical_parties"] = [
        _canonical_party("party:1", "designation:dup"),
        _canonical_party("party:2", "designation:dup"),
    ]

    with pytest.raises(ValidationError, match="designation_key"):
        ReviewContext.model_validate(payload)


def test_review_context_accepts_distinct_designation_keys_across_parties():
    payload = valid_context_payload()
    payload["shared_facts"]["parties"]["data"]["canonical_parties"] = [
        _canonical_party("party:1", "designation:1"),
        _canonical_party("party:2", "designation:2"),
    ]

    context = ReviewContext.model_validate(payload)

    assert len(context.shared_facts.parties.data.canonical_parties) == 2


def test_review_context_rejects_signer_slot_cross_slot_signer_reference():
    payload = valid_context_payload()
    payload["shared_facts"]["signature"]["data"]["signature_blocks"] = [
        {
            "signature_block_key": "sig-block:1",
            "document_key": "main",
            "party_binding_state": "BOUND",
            "party_key": "party:1",
            "candidate_party_keys": [],
            "local_company_name": {
                "presence": "ABSENT",
                "normalization_state": "NOT_APPLICABLE",
                "observations": [],
            },
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]
    payload["shared_facts"]["signature"]["data"]["signer_slots"] = [
        {
            "signer_slot_key": "slot:1",
            "signature_block_key": "sig-block:1",
            "role_text": "法定代表人",
            "role_state": "ELIGIBLE_SIGNER",
            "presence": "PRESENT_VALUE",
            "signer_keys": ["signer:1"],
            "identity_number_keys": [],
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]
    payload["shared_facts"]["signature"]["data"]["signer_candidates"] = [
        {
            "signer_key": "signer:1",
            "signer_slot_key": "slot:OTHER",  # 归属其他 slot，cross-slot 引用
            "raw_name": "张三",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]

    with pytest.raises(ValidationError, match="signer_key"):
        ReviewContext.model_validate(payload)


def test_review_context_rejects_signer_slot_cross_slot_identity_number_reference():
    payload = valid_context_payload()
    payload["shared_facts"]["signature"]["data"]["signature_blocks"] = [
        {
            "signature_block_key": "sig-block:1",
            "document_key": "main",
            "party_binding_state": "BOUND",
            "party_key": "party:1",
            "candidate_party_keys": [],
            "local_company_name": {
                "presence": "ABSENT",
                "normalization_state": "NOT_APPLICABLE",
                "observations": [],
            },
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]
    payload["shared_facts"]["signature"]["data"]["signer_slots"] = [
        {
            "signer_slot_key": "slot:1",
            "signature_block_key": "sig-block:1",
            "role_text": "法定代表人",
            "role_state": "ELIGIBLE_SIGNER",
            "presence": "PRESENT_VALUE",
            "signer_keys": [],
            "identity_number_keys": ["idnum:1"],
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]
    payload["shared_facts"]["signature"]["data"]["identity_number_candidates"] = [
        {
            "identity_number_key": "idnum:1",
            "signer_slot_key": "slot:OTHER",  # 归属其他 slot，cross-slot 引用
            "raw_text": "110101199001011234",
            "normalization_state": "VALID",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]

    with pytest.raises(ValidationError, match="identity_number_key"):
        ReviewContext.model_validate(payload)


def _signature_with_two_slots(payload: dict) -> None:
    payload["shared_facts"]["signature"]["data"]["signature_blocks"] = [
        {
            "signature_block_key": "sig-block:1",
            "document_key": "main",
            "party_binding_state": "UNBOUND",
            "candidate_party_keys": [],
            "local_company_name": {
                "presence": "ABSENT",
                "normalization_state": "NOT_APPLICABLE",
                "observations": [],
            },
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]
    payload["shared_facts"]["signature"]["data"]["signer_slots"] = [
        {
            "signer_slot_key": "slot:1",
            "signature_block_key": "sig-block:1",
            "role_text": "法定代表人",
            "role_state": "ELIGIBLE_SIGNER",
            "presence": "PRESENT_VALUE",
            "signer_keys": ["signer:1"],
            "identity_number_keys": [],
            "evidence_ids": ["evidence:main:header-name"],
        },
        {
            "signer_slot_key": "slot:2",
            "signature_block_key": "sig-block:1",
            "role_text": "经办人",
            "role_state": "ELIGIBLE_SIGNER",
            "presence": "PRESENT_VALUE",
            "signer_keys": [],
            "identity_number_keys": ["idnum:1"],
            "evidence_ids": ["evidence:main:header-name"],
        },
    ]


def test_review_context_rejects_person_id_relation_cross_slot_owner():
    payload = valid_context_payload()
    _signature_with_two_slots(payload)
    payload["shared_facts"]["signature"]["data"]["signer_candidates"] = [
        {
            "signer_key": "signer:1",
            "signer_slot_key": "slot:1",
            "raw_name": "张三",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]
    payload["shared_facts"]["signature"]["data"]["identity_number_candidates"] = [
        {
            "identity_number_key": "idnum:1",
            "signer_slot_key": "slot:2",
            "raw_text": "110101199001011234",
            "normalization_state": "VALID",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]
    payload["shared_facts"]["signature"]["data"]["person_id_relations"] = [
        {
            "signer_key": "signer:1",
            "identity_number_key": "idnum:1",
            "association_state": "DIRECT",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]

    with pytest.raises(ValidationError, match="person_id_relation"):
        ReviewContext.model_validate(payload)


def test_review_context_accepts_person_id_relation_same_owner_slot():
    payload = valid_context_payload()
    _signature_with_two_slots(payload)
    payload["shared_facts"]["signature"]["data"]["signer_slots"] = [
        {
            "signer_slot_key": "slot:1",
            "signature_block_key": "sig-block:1",
            "role_text": "法定代表人",
            "role_state": "ELIGIBLE_SIGNER",
            "presence": "PRESENT_VALUE",
            "signer_keys": [],
            "identity_number_keys": [],
            "evidence_ids": ["evidence:main:header-name"],
        },
        {
            "signer_slot_key": "slot:2",
            "signature_block_key": "sig-block:1",
            "role_text": "经办人",
            "role_state": "ELIGIBLE_SIGNER",
            "presence": "PRESENT_VALUE",
            "signer_keys": ["signer:1"],
            "identity_number_keys": ["idnum:1"],
            "evidence_ids": ["evidence:main:header-name"],
        },
    ]
    payload["shared_facts"]["signature"]["data"]["signer_candidates"] = [
        {
            "signer_key": "signer:1",
            "signer_slot_key": "slot:2",
            "raw_name": "张三",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]
    payload["shared_facts"]["signature"]["data"]["identity_number_candidates"] = [
        {
            "identity_number_key": "idnum:1",
            "signer_slot_key": "slot:2",
            "raw_text": "110101199001011234",
            "normalization_state": "VALID",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]
    payload["shared_facts"]["signature"]["data"]["person_id_relations"] = [
        {
            "signer_key": "signer:1",
            "identity_number_key": "idnum:1",
            "association_state": "DIRECT",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]

    context = ReviewContext.model_validate(payload)
    assert len(context.shared_facts.signature.data.person_id_relations) == 1


def test_review_context_does_not_decide_identity_number_none_owner_semantics():
    payload = valid_context_payload()
    _signature_with_two_slots(payload)
    payload["shared_facts"]["signature"]["data"]["signer_slots"] = [
        {
            "signer_slot_key": "slot:1",
            "signature_block_key": "sig-block:1",
            "role_text": "法定代表人",
            "role_state": "ELIGIBLE_SIGNER",
            "presence": "PRESENT_VALUE",
            "signer_keys": ["signer:1"],
            "identity_number_keys": [],
            "evidence_ids": ["evidence:main:header-name"],
        },
        {
            "signer_slot_key": "slot:2",
            "signature_block_key": "sig-block:1",
            "role_text": "经办人",
            "role_state": "ELIGIBLE_SIGNER",
            "presence": "PRESENT_VALUE",
            "signer_keys": [],
            "identity_number_keys": [],
            "evidence_ids": ["evidence:main:header-name"],
        },
    ]
    payload["shared_facts"]["signature"]["data"]["signer_candidates"] = [
        {
            "signer_key": "signer:1",
            "signer_slot_key": "slot:1",
            "raw_name": "张三",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]
    payload["shared_facts"]["signature"]["data"]["identity_number_candidates"] = [
        {
            "identity_number_key": "idnum:1",
            "signer_slot_key": None,
            "raw_text": "110101199001011234",
            "normalization_state": "VALID",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]
    payload["shared_facts"]["signature"]["data"]["person_id_relations"] = [
        {
            "signer_key": "signer:1",
            "identity_number_key": "idnum:1",
            "association_state": "DIRECT",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]

    context = ReviewContext.model_validate(payload)
    assert len(context.shared_facts.signature.data.person_id_relations) == 1


def test_review_context_rejects_logical_attachment_parent_main():
    payload = valid_context_payload()
    payload["shared_facts"]["attachment_manifest"]["data"]["logical_attachment_candidates"] = [
        {
            "logical_attachment_candidate_key": "logical:1",
            "parent_document_key": "main",
            "title": {
                "presence": "PRESENT_VALUE",
                "normalization_state": "VALID",
                "observations": [
                    {
                        "raw_text": "逻辑附件",
                        "normalized_value": "逻辑附件",
                        "evidence_ids": ["evidence:main:header-name"],
                    }
                ],
            },
            "source_locator": "markdown-chars:0-4",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]

    with pytest.raises(ValidationError, match="parent_document_key"):
        ReviewContext.model_validate(payload)


# ---------- Task 2 剩余覆盖：1.4 引用完整性（悬空引用 / 引用集合类型错误 / 跨集合）----------

def _absent_field() -> dict:
    return {
        "presence": "ABSENT",
        "normalization_state": "NOT_APPLICABLE",
        "observations": [],
    }

def _sig_block(block_key: str = "sig:1") -> dict:
    return {
        "signature_block_key": block_key,
        "document_key": "main",
        "party_binding_state": "UNBOUND",
        "candidate_party_keys": [],
        "local_company_name": _absent_field(),
        "evidence_ids": ["evidence:main:header-name"],
    }

def test_amount_relation_rejects_dangling_amount_key():
    payload = valid_context_payload()
    payload["shared_facts"]["amount_payment"]["data"]["amount_relations"] = [
        {
            "amount_relation_key": "rel:1",
            "amount_key": "amount:missing",
            "relation_kind": "CONTRACT_OVERALL",
            "relation_state": "CONFIRMED",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]

    with pytest.raises(ValidationError, match="amount_key"):
        ReviewContext.model_validate(payload)

def test_amount_relation_rejects_cross_collection_left_references_to_stage():
    # 引用集合类型错误：amount_key 指向一个已存在的 payment_stage_key 值
    payload = valid_context_payload()
    payload["shared_facts"]["amount_payment"]["data"]["payment_stages"] = [
        {
            "payment_stage_key": "stage:1",
            "name": _absent_field(),
            "sequence": _absent_field(),
            "ratio_percent": _absent_field(),
            "amount_keys": [],
            "trigger_condition": _absent_field(),
            "payment_term": _absent_field(),
            "payment_method_keys": [],
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]
    payload["shared_facts"]["amount_payment"]["data"]["amount_relations"] = [
        {
            "amount_relation_key": "rel:1",
            "amount_key": "stage:1",  # 类型错误：指向 payment_stage_key
            "relation_kind": "CONTRACT_OVERALL",
            "relation_state": "CONFIRMED",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]

    with pytest.raises(ValidationError, match="amount_key"):
        ReviewContext.model_validate(payload)

def test_payment_stage_rejects_dangling_amount_and_method_references():
    payload = valid_context_payload()
    payload["shared_facts"]["amount_payment"]["data"]["payment_stages"] = [
        {
            "payment_stage_key": "stage:1",
            "name": _absent_field(),
            "sequence": _absent_field(),
            "ratio_percent": _absent_field(),
            "amount_keys": ["amount:missing"],
            "trigger_condition": _absent_field(),
            "payment_term": _absent_field(),
            "payment_method_keys": ["method:missing"],
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]

    with pytest.raises(ValidationError, match="amount_key|payment_method_key"):
        ReviewContext.model_validate(payload)

def test_payment_stage_rejects_amount_key_cross_referencing_own_stage():
    # 引用集合类型错误：amount_keys 指向本阶段自身的 payment_stage_key
    payload = valid_context_payload()
    payload["shared_facts"]["amount_payment"]["data"]["payment_stages"] = [
        {
            "payment_stage_key": "stage:1",
            "name": _absent_field(),
            "sequence": _absent_field(),
            "ratio_percent": _absent_field(),
            "amount_keys": ["stage:1"],
            "trigger_condition": _absent_field(),
            "payment_term": _absent_field(),
            "payment_method_keys": [],
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]

    with pytest.raises(ValidationError, match="amount_key"):
        ReviewContext.model_validate(payload)

def test_copy_allocation_rejects_dangling_statement_key():
    payload = valid_context_payload()
    payload["shared_facts"]["copy_terms"]["data"]["allocations"] = [
        {
            "allocation_key": "al:1",
            "statement_key": "st:missing",
            "candidate_party_keys": [],
            "allocation_semantics": "EACH",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]

    with pytest.raises(ValidationError, match="statement_key"):
        ReviewContext.model_validate(payload)

def test_copy_allocation_rejects_statement_key_cross_referencing_allocation():
    # 引用集合类型错误：statement_key 指向一个已存在的 allocation_key 值
    payload = valid_context_payload()
    payload["shared_facts"]["copy_terms"]["data"]["allocations"] = [
        {
            "allocation_key": "al:1",
            "statement_key": "al:1",
            "candidate_party_keys": [],
            "allocation_semantics": "EACH",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]

    with pytest.raises(ValidationError, match="statement_key"):
        ReviewContext.model_validate(payload)

def test_copy_terms_rejects_dangling_overall_total_statement_key():
    payload = valid_context_payload()
    payload["shared_facts"]["copy_terms"]["data"]["overall_total_statement_key"] = "st:missing"

    with pytest.raises(ValidationError, match="overall_total_statement_key"):
        ReviewContext.model_validate(payload)

def test_signer_candidate_rejects_dangling_signer_slot_key():
    payload = valid_context_payload()
    payload["shared_facts"]["signature"]["data"]["signer_candidates"] = [
        {
            "signer_key": "signer:1",
            "signer_slot_key": "slot:missing",
            "raw_name": "张三",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]

    with pytest.raises(ValidationError, match="signer_slot_key"):
        ReviewContext.model_validate(payload)

def test_alternative_signer_group_rejects_dangling_signer_slot_key():
    payload = valid_context_payload()
    payload["shared_facts"]["signature"]["data"]["alternative_signer_groups"] = [
        {
            "signer_group_key": "grp:1",
            "signer_slot_keys": ["slot:missing"],
            "relation_state": "CONFIRMED",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]

    with pytest.raises(ValidationError, match="signer_slot_key"):
        ReviewContext.model_validate(payload)

def test_signing_date_observation_rejects_dangling_signature_block_key():
    payload = valid_context_payload()
    payload["shared_facts"]["signature"]["data"]["signing_date_observations"] = [
        {
            "signature_date_key": "sd:1",
            "signature_block_key": "sig:missing",
            "field": {
                "presence": "PRESENT_VALUE",
                "normalization_state": "VALID",
                "observations": [
                    {
                        "raw_text": "2026-01-01",
                        "normalized_value": "2026-01-01",
                        "evidence_ids": ["evidence:main:header-name"],
                    }
                ],
            },
        }
    ]

    with pytest.raises(ValidationError, match="signature_block_key"):
        ReviewContext.model_validate(payload)

def test_signature_field_observation_rejects_dangling_signature_block_key():
    payload = valid_context_payload()
    payload["shared_facts"]["signature"]["data"]["account_observations"] = [
        {
            "field_observation_key": "fob:1",
            "document_key": "main",
            "signature_block_key": "sig:missing",
            "party_binding_state": "UNBOUND",
            "field_kind": "BANK_ACCOUNT",
            "purpose_state": "CONFIRMED",
            "field": {
                "presence": "PRESENT_VALUE",
                "normalization_state": "VALID",
                "observations": [
                    {
                        "raw_text": "123",
                        "normalized_value": "123",
                        "evidence_ids": ["evidence:main:header-name"],
                    }
                ],
            },
        }
    ]

    with pytest.raises(ValidationError, match="signature_block_key"):
        ReviewContext.model_validate(payload)

def test_signature_block_candidate_party_key_cross_referencing_designation():
    # 引用集合类型错误：candidate_party_keys 指向一个已存在的 designation_key 值
    payload = valid_context_payload()
    payload["shared_facts"]["parties"]["data"]["canonical_parties"] = [
        _canonical_party("party:1", "designation:1"),
    ]
    payload["shared_facts"]["signature"]["data"]["signature_blocks"] = [
        {
            "signature_block_key": "sig:1",
            "document_key": "main",
            "party_binding_state": "UNBOUND",
            "candidate_party_keys": ["designation:1"],
            "local_company_name": _absent_field(),
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]

    with pytest.raises(ValidationError, match="candidate_party_key"):
        ReviewContext.model_validate(payload)

def test_copy_allocation_candidate_party_key_cross_referencing_designation():
    # 引用集合类型错误：candidate_party_keys 指向 designation_key 而非 party_key
    payload = valid_context_payload()
    payload["shared_facts"]["parties"]["data"]["canonical_parties"] = [
        _canonical_party("party:1", "designation:1"),
    ]
    payload["shared_facts"]["copy_terms"]["data"]["statements"] = [
        {
            "statement_key": "st:1",
            "scope_key": "s:1",
            "document_key": "main",
            "raw_text": "共3份",
            "count": _absent_field(),
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]
    payload["shared_facts"]["copy_terms"]["data"]["allocations"] = [
        {
            "allocation_key": "al:1",
            "statement_key": "st:1",
            "candidate_party_keys": ["designation:1"],
            "allocation_semantics": "EACH",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]

    with pytest.raises(ValidationError, match="candidate_party_key"):
        ReviewContext.model_validate(payload)


# ---------- Task 2 剩余覆盖：2.4/2.3 参数化重复键拒绝（原始 payload 直喂 ReviewContext.model_validate）----------

def _dup_builders():
    ev = ["evidence:main:header-name"]

    def present(raw, extras=None):
        o = {"raw_text": raw, "normalized_value": raw, "evidence_ids": ev}
        if extras:
            o.update(extras)
        return {"presence": "PRESENT_VALUE", "normalization_state": "VALID", "observations": [o]}

    def absent():
        return {"presence": "ABSENT", "normalization_state": "NOT_APPLICABLE", "observations": []}

    def sig_block(bk):
        return {
            "signature_block_key": bk,
            "document_key": "main",
            "party_binding_state": "UNBOUND",
            "candidate_party_keys": [],
            "local_company_name": absent(),
            "evidence_ids": ev,
        }

    def slot(sk, signer_keys=None, idnum_keys=None):
        return {
            "signer_slot_key": sk,
            "signature_block_key": "sig:1",
            "role_text": "法定代表人",
            "role_state": "ELIGIBLE_SIGNER",
            "presence": "PRESENT_VALUE",
            "signer_keys": signer_keys or [],
            "identity_number_keys": idnum_keys or [],
            "evidence_ids": ev,
        }

    def amount(ak):
        return {
            "amount_key": ak,
            "document_key": "main",
            "semantic_role": present("总价"),
            "numeric_amount": present("100"),
            "uppercase_amount": absent(),
            "currency": absent(),
            "tax_treatment": absent(),
            "evidence_ids": ev,
        }

    def stage(stk):
        return {
            "payment_stage_key": stk,
            "name": present("首付款"),
            "sequence": present("1", extras={"normalized_value": 1}),
            "ratio_percent": present("30"),
            "amount_keys": [],
            "trigger_condition": absent(),
            "payment_term": absent(),
            "payment_method_keys": [],
            "evidence_ids": ev,
        }

    def statement(stk):
        return {
            "statement_key": stk,
            "scope_key": "s:1",
            "document_key": "main",
            "raw_text": "共3份",
            "count": present("3", extras={"normalized_value": 3}),
            "evidence_ids": ev,
        }

    def declaration(dk):
        return {
            "attachment_declaration_key": dk,
            "title": present("附件一"),
            "ordinal": absent(),
            "evidence_ids": ev,
        }

    def with_domain(payload, domain):
        return {"payload": payload, "domain": domain}

    def mutate(payload, domain, field, value):
        payload["shared_facts"][domain]["data"][field] = value
        return payload

    def sig_with_block(payload, extra=None):
        payload["shared_facts"]["signature"]["data"]["signature_blocks"] = [sig_block("sig:1")]
        if extra:
            extra(payload)
        return payload

    def sig_with_slot(payload, slot_payload, signer_keys=None, idnum_keys=None):
        payload["shared_facts"]["signature"]["data"]["signature_blocks"] = [sig_block("sig:1")]
        payload["shared_facts"]["signature"]["data"]["signer_slots"] = [slot("slot:1")]
        payload["shared_facts"]["signature"]["data"] = slot_payload
        return payload

    def document_dup():
        p = valid_context_payload()
        p["source_snapshot"]["attachments"] = [
            {"document_key": "uploaded:att-001", "source_kind": "UPLOADED", "attachment_id": "ATT-001", "filename": "a.md", "parsed_content_sha256": "sha256:" + "a" * 64, "source_file_sha256": "sha256:" + "b" * 64},
            {"document_key": "uploaded:att-001", "source_kind": "UPLOADED", "attachment_id": "ATT-002", "filename": "b.md", "parsed_content_sha256": "sha256:" + "a" * 64, "source_file_sha256": "sha256:" + "b" * 64},
        ]
        return p

    def evidence_dup():
        p = valid_context_payload()
        e = {"evidence_id": "evidence:main:header-name", "document_key": "main", "source_locator": "markdown-chars:0-4", "quote": "采购合同"}
        p["evidence_index"]["items"] = [e, dict(e)]
        return p

    def prep_issue_dup():
        p = valid_context_payload()
        it = {"preparation_issue_key": "pi:1", "code": "SUSPECTED_DUPLICATE", "message": "重复", "related_document_keys": ["main"], "evidence_ids": []}
        p["preparation_issues"] = [it, dict(it)]
        return p

    def party_dup():
        p = valid_context_payload()
        p["shared_facts"]["parties"]["data"]["canonical_parties"] = [
            _canonical_party("party:1", "d:1"),
            _canonical_party("party:1", "d:2"),
        ]
        return p

    def designation_dup():
        p = valid_context_payload()
        p["shared_facts"]["parties"]["data"]["canonical_parties"] = [
            {"party_key": "party:1", "declared_name": present("甲方"), "declared_designations": [
                {"designation_key": "d:1", "kind": "CONTRACT_ROLE", "text": "甲方", "evidence_ids": ev},
                {"designation_key": "d:1", "kind": "NAME_ALIAS", "text": "甲方", "evidence_ids": ev},
            ], "definition_evidence_ids": ev}
        ]
        return p

    def mention_dup():
        p = valid_context_payload()
        m = {"mention_key": "m:1", "document_key": "main", "mention_kind": "PARTY_DEFINITION", "observed_text": "甲方", "local_definition_state": "PRESENT", "comparison_state": "MATCHED_DECLARATION", "evidence_ids": ev}
        p["shared_facts"]["parties"]["data"]["party_mentions"] = [m, dict(m)]
        return p

    def signature_block_dup():
        p = valid_context_payload()
        p["shared_facts"]["signature"]["data"]["signature_blocks"] = [sig_block("sig:1"), sig_block("sig:1")]
        return p

    def signer_slot_dup():
        p = valid_context_payload()
        p["shared_facts"]["signature"]["data"]["signature_blocks"] = [sig_block("sig:1")]
        s = slot("slot:1")
        p["shared_facts"]["signature"]["data"]["signer_slots"] = [s, dict(s)]
        return p

    def signer_group_dup():
        p = valid_context_payload()
        p["shared_facts"]["signature"]["data"]["signature_blocks"] = [sig_block("sig:1")]
        p["shared_facts"]["signature"]["data"]["signer_slots"] = [slot("slot:1")]
        g = {"signer_group_key": "grp:1", "signer_slot_keys": ["slot:1"], "relation_state": "CONFIRMED", "evidence_ids": ev}
        p["shared_facts"]["signature"]["data"]["alternative_signer_groups"] = [g, dict(g)]
        return p

    def signer_dup():
        p = valid_context_payload()
        p["shared_facts"]["signature"]["data"]["signature_blocks"] = [sig_block("sig:1")]
        p["shared_facts"]["signature"]["data"]["signer_slots"] = [slot("slot:1", signer_keys=["signer:1"])]
        c = {"signer_key": "signer:1", "signer_slot_key": "slot:1", "raw_name": "张三", "evidence_ids": ev}
        p["shared_facts"]["signature"]["data"]["signer_candidates"] = [c, dict(c)]
        return p

    def identity_number_dup():
        p = valid_context_payload()
        p["shared_facts"]["signature"]["data"]["signature_blocks"] = [sig_block("sig:1")]
        p["shared_facts"]["signature"]["data"]["signer_slots"] = [slot("slot:1", idnum_keys=["idnum:1"])]
        c = {"identity_number_key": "idnum:1", "signer_slot_key": "slot:1", "raw_text": "110101199001011234", "normalization_state": "VALID", "evidence_ids": ev}
        p["shared_facts"]["signature"]["data"]["identity_number_candidates"] = [c, dict(c)]
        return p

    def signing_date_dup():
        p = valid_context_payload()
        p["shared_facts"]["signature"]["data"]["signature_blocks"] = [sig_block("sig:1")]
        o = {"signature_date_key": "sd:1", "signature_block_key": "sig:1", "field": {"presence": "PRESENT_VALUE", "normalization_state": "VALID", "observations": [{"raw_text": "2026-01-01", "normalized_value": "2026-01-01", "evidence_ids": ev}]}}
        p["shared_facts"]["signature"]["data"]["signing_date_observations"] = [o, dict(o)]
        return p

    def field_observation_dup():
        p = valid_context_payload()
        p["shared_facts"]["signature"]["data"]["signature_blocks"] = [sig_block("sig:1")]
        o = {"field_observation_key": "fob:1", "document_key": "main", "signature_block_key": "sig:1", "party_binding_state": "UNBOUND", "field_kind": "BANK_ACCOUNT", "purpose_state": "CONFIRMED", "field": {"presence": "PRESENT_VALUE", "normalization_state": "VALID", "observations": [{"raw_text": "123", "normalized_value": "123", "evidence_ids": ev}]}}
        p["shared_facts"]["signature"]["data"]["account_observations"] = [o, dict(o)]
        return p

    def amount_dup():
        p = valid_context_payload()
        a = amount("amount:1")
        p["shared_facts"]["amount_payment"]["data"]["amounts"] = [a, dict(a)]
        return p

    def amount_relation_dup():
        p = valid_context_payload()
        p["shared_facts"]["amount_payment"]["data"]["amounts"] = [amount("amount:1")]
        r = {"amount_relation_key": "rel:1", "amount_key": "amount:1", "relation_kind": "CONTRACT_OVERALL", "relation_state": "CONFIRMED", "evidence_ids": ev}
        p["shared_facts"]["amount_payment"]["data"]["amount_relations"] = [r, dict(r)]
        return p

    def payment_method_dup():
        p = valid_context_payload()
        m = {"payment_method_key": "pm:1", "raw_text": "转账", "normalized_value": "转账", "evidence_ids": ev}
        p["shared_facts"]["amount_payment"]["data"]["payment_methods"] = [m, dict(m)]
        return p

    def payment_stage_dup():
        p = valid_context_payload()
        s = stage("stage:1")
        p["shared_facts"]["amount_payment"]["data"]["payment_stages"] = [s, dict(s)]
        return p

    def statement_dup():
        p = valid_context_payload()
        s = statement("st:1")
        p["shared_facts"]["copy_terms"]["data"]["statements"] = [s, dict(s)]
        return p

    def allocation_dup():
        p = valid_context_payload()
        p["shared_facts"]["copy_terms"]["data"]["statements"] = [statement("st:1")]
        a = {"allocation_key": "al:1", "statement_key": "st:1", "candidate_party_keys": [], "allocation_semantics": "EACH", "evidence_ids": ev}
        p["shared_facts"]["copy_terms"]["data"]["allocations"] = [a, dict(a)]
        return p

    def declaration_dup():
        p = valid_context_payload()
        d = declaration("decl:1")
        p["shared_facts"]["attachment_manifest"]["data"]["declarations"] = [d, dict(d)]
        return p

    def logical_dup():
        p = valid_context_payload()
        l = {"logical_attachment_candidate_key": "logical:1", "parent_document_key": "uploaded:att-001", "title": present("逻辑附件"), "source_locator": "markdown-chars:0-4", "evidence_ids": ev}
        p["shared_facts"]["attachment_manifest"]["data"]["logical_attachment_candidates"] = [l, dict(l)]
        return p

    def relation_dup():
        p = valid_context_payload()
        p["shared_facts"]["attachment_manifest"]["data"]["declarations"] = [declaration("decl:1")]
        l = {"attachment_relation_key": "relA:1", "attachment_declaration_key": "decl:1", "candidate_document_keys": ["uploaded:att-001"], "relation_state": "LINKED", "evidence_ids": ev}
        p["shared_facts"]["attachment_manifest"]["data"]["links"] = [l, dict(l)]
        return p

    def coverage_dup():
        p = valid_context_payload()
        cov = [{"document_key": "main", "state": "COMPLETE", "affected_fact_kinds": [], "fact_issue_keys": []}, {"document_key": "main", "state": "COMPLETE", "affected_fact_kinds": [], "fact_issue_keys": []}]
        p["shared_facts"]["header"]["coverage"] = cov
        return p

    def fact_issue_dup():
        p = valid_context_payload()
        p["shared_facts"]["signature"]["state"] = "PARTIAL"
        p["shared_facts"]["signature"]["coverage"] = [
            {"document_key": "main", "state": "PARTIAL", "affected_fact_kinds": ["sig"], "fact_issue_keys": ["fi:1"]},
            {"document_key": "uploaded:att-001", "state": "PARTIAL", "affected_fact_kinds": ["sig"], "fact_issue_keys": ["fi:1"]},
            {"document_key": "embedded:main:001", "state": "PARTIAL", "affected_fact_kinds": ["sig"], "fact_issue_keys": ["fi:1"]},
        ]
        fi = {"fact_issue_key": "fi:1", "code": "SIG_PARTIAL", "message": "缺", "related_document_keys": ["main"], "affected_fact_kinds": ["sig"], "evidence_ids": []}
        p["shared_facts"]["signature"]["issues"] = [fi, dict(fi)]
        return p

    return [
        ("document", document_dup, "document_key"),
        ("evidence", evidence_dup, "evidence_id"),
        ("preparation_issue", prep_issue_dup, "preparation_issue_key"),
        ("party", party_dup, "party_key"),
        ("designation", designation_dup, "designation_key"),
        ("mention", mention_dup, "mention_key"),
        ("signature_block", signature_block_dup, "signature_block_key"),
        ("signer_slot", signer_slot_dup, "signer_slot_key"),
        ("signer_group", signer_group_dup, "signer_group_key"),
        ("signer", signer_dup, "signer_key"),
        ("identity_number", identity_number_dup, "identity_number_key"),
        ("signing_date", signing_date_dup, "signature_date_key"),
        ("field_observation", field_observation_dup, "field_observation_key"),
        ("amount", amount_dup, "amount_key"),
        ("amount_relation", amount_relation_dup, "amount_relation_key"),
        ("payment_method", payment_method_dup, "payment_method_key"),
        ("payment_stage", payment_stage_dup, "payment_stage_key"),
        ("statement", statement_dup, "statement_key"),
        ("allocation", allocation_dup, "allocation_key"),
        ("attachment_declaration", declaration_dup, "attachment_declaration_key"),
        ("logical_candidate", logical_dup, "logical_attachment_candidate_key"),
        ("relation", relation_dup, "attachment_relation_key"),
        ("coverage", coverage_dup, "document_key"),
        ("fact_issue", fact_issue_dup, "fact_issue_key"),
    ]


@pytest.mark.parametrize(
    ("label", "duplicate_payload", "match"),
    _dup_builders(),
    ids=[item[0] for item in _dup_builders()],
)
def test_review_context_rejects_duplicate_key_in_collection(label, duplicate_payload, match):
    payload = duplicate_payload()

    with pytest.raises(ValidationError, match=match):
        ReviewContext.model_validate(payload)
