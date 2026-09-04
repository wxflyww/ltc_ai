from __future__ import annotations

from copy import deepcopy


def sha256(letter: str) -> str:
    return f"sha256:{letter * 64}"


def clone_payload(payload: dict) -> dict:
    return deepcopy(payload)


def complete_coverage(document_key: str) -> dict:
    return {
        "document_key": document_key,
        "state": "COMPLETE",
        "affected_fact_kinds": [],
        "fact_issue_keys": [],
    }


def absent_field() -> dict:
    return {
        "presence": "ABSENT",
        "normalization_state": "NOT_APPLICABLE",
        "observations": [],
    }


def present_empty_field(evidence_id: str) -> dict:
    return {
        "presence": "PRESENT_EMPTY",
        "normalization_state": "NOT_APPLICABLE",
        "observations": [
            {
                "raw_text": "",
                "evidence_ids": [evidence_id],
            }
        ],
    }


def present_name_field(name: str, evidence_id: str, specificity: str = "SPECIFIC") -> dict:
    return {
        "presence": "PRESENT_VALUE",
        "normalization_state": "VALID",
        "observations": [
            {
                "raw_text": name,
                "normalized_value": name,
                "specificity": specificity,
                "evidence_ids": [evidence_id],
            }
        ],
    }


def present_value_field(raw_text: str, normalized_value, evidence_id: str) -> dict:
    return {
        "presence": "PRESENT_VALUE",
        "normalization_state": "VALID",
        "observations": [
            {
                "raw_text": raw_text,
                "normalized_value": normalized_value,
                "evidence_ids": [evidence_id],
            }
        ],
    }


def valid_prepare_request_payload() -> dict:
    return {
        "contract_id": "C-2026-0001",
        "revision_id": "V3",
        "main_document": {
            "document_id": "DOC-MAIN-1",
            "filename": "main.md",
            "markdown": "# 主合同\n\n合同正文",
            "source_file_sha256": sha256("a"),
        },
        "uploaded_attachments": [
            {
                "attachment_id": "ATT-001",
                "filename": "tech-spec.md",
                "markdown": "# 技术协议\n\n附件正文",
                "source_file_sha256": sha256("b"),
            }
        ],
        "parser_meta": {
            "parser_name": "docflow",
            "parser_version": "1.2.3",
            "parsed_at": "2026-08-20T10:20:30+08:00",
        },
    }


def valid_source_snapshot_payload() -> dict:
    return {
        "contract_id": "C-2026-0001",
        "revision_id": "V3",
        "document_set_hash": sha256("c"),
        "main_document": {
            "document_key": "main",
            "document_id": "DOC-MAIN-1",
            "filename": "main.md",
            "parsed_content_sha256": sha256("d"),
            "source_file_sha256": sha256("a"),
        },
        "attachments": [
            {
                "document_key": "uploaded:att-001",
                "source_kind": "UPLOADED",
                "attachment_id": "ATT-001",
                "filename": "tech-spec.md",
                "parsed_content_sha256": sha256("e"),
                "source_file_sha256": sha256("b"),
            },
            {
                "document_key": "embedded:main:001",
                "source_kind": "EMBEDDED",
                "source_main_document_id": "DOC-MAIN-1",
                "source_locator": "markdown-chars:10-42",
                "title": "附件一：技术规范书",
                "parsed_content_sha256": sha256("f"),
            },
        ],
        "parser_meta": {
            "parser_name": "docflow",
            "parser_version": "1.2.3",
            "parsed_at": "2026-08-20T10:20:30+08:00",
        },
    }


def _header_facts_payload() -> dict:
    evidence_id = "evidence:main:header-name"
    return {
        "contract_identity": {
            "name": present_name_field("采购合同", evidence_id),
            "number": absent_field(),
        },
        "project_identity": {
            "name": absent_field(),
            "number": absent_field(),
        },
        "signing_location": absent_field(),
        "signing_date": absent_field(),
    }


def _parties_facts_payload() -> dict:
    return {
        "canonical_parties": [],
        "party_mentions": [],
    }


def _signature_facts_payload() -> dict:
    return {
        "signature_blocks": [],
        "signer_slots": [],
        "alternative_signer_groups": [],
        "signer_candidates": [],
        "identity_number_candidates": [],
        "person_id_relations": [],
        "signing_date_observations": [],
        "account_observations": [],
        "contact_observations": [],
    }


def _amount_payment_facts_payload() -> dict:
    return {
        "amounts": [],
        "amount_relations": [],
        "payment_methods": [],
        "payment_stages": [],
    }


def _copy_terms_facts_payload() -> dict:
    return {
        "statements": [],
        "allocations": [],
    }


def _attachment_manifest_payload() -> dict:
    return {
        "declared_total": absent_field(),
        "declarations": [],
        "logical_attachment_candidates": [],
        "links": [],
    }


def complete_domain(document_keys: list[str], data: dict) -> dict:
    return {
        "state": "COMPLETE",
        "coverage": [complete_coverage(document_key) for document_key in document_keys],
        "data": data,
        "issues": [],
    }


def valid_context_payload() -> dict:
    source_snapshot = valid_source_snapshot_payload()
    all_document_keys = [
        "main",
        "uploaded:att-001",
        "embedded:main:001",
    ]
    main_only = ["main"]
    return {
        "schema_version": "review-context/v1",
        "source_snapshot": source_snapshot,
        "shared_facts": {
            "header": complete_domain(main_only, _header_facts_payload()),
            "parties": complete_domain(all_document_keys, _parties_facts_payload()),
            "signature": complete_domain(all_document_keys, _signature_facts_payload()),
            "amount_payment": complete_domain(main_only, _amount_payment_facts_payload()),
            "copy_terms": complete_domain(main_only, _copy_terms_facts_payload()),
            "attachment_manifest": complete_domain(all_document_keys, _attachment_manifest_payload()),
        },
        "evidence_index": {
            "items": [
                {
                    "evidence_id": "evidence:main:header-name",
                    "document_key": "main",
                    "source_locator": "markdown-chars:0-4",
                    "quote": "采购合同",
                }
            ]
        },
        "preparation_issues": [],
        "preparation_meta": {
            "pipeline_version": "contract-review-prepare/1.0.0",
            "prompt_bundle_hash": sha256("1"),
            "model_deployment": "qwen3.6-35b-a3b",
            "created_at": "2026-08-20T10:20:30+08:00",
        },
        "context_digest": sha256("2"),
    }
