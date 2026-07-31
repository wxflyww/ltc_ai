import pytest
from pydantic import ValidationError

from app.capabilities.contract_review.two_stage import (
    AttachmentSnapshot,
    FactState,
    Sha256Digest,
)
from app.capabilities.contract_review.two_stage.schemas import (
    EvidenceRef,
    FactDomain,
    ReviewContext,
    SourceSnapshot,
)


SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64
SHA_C = "sha256:" + "c" * 64


def test_foundation_package_exports_contract_type_aliases():
    assert AttachmentSnapshot is not None
    assert FactState is not None
    assert Sha256Digest is not None


def source_snapshot_payload() -> dict:
    return {
        "contract_id": "C001",
        "revision_id": "V1",
        "document_set_hash": SHA_A,
        "main_document": {
            "document_key": "main",
            "document_id": "DOC-001",
            "filename": "主合同.md",
            "parsed_content_sha256": SHA_B,
        },
        "attachments": [
            {
                "document_key": "attachment:ATT-001",
                "source_kind": "UPLOADED",
                "attachment_id": "ATT-001",
                "filename": "技术协议.md",
                "parsed_content_sha256": SHA_C,
            },
            {
                "document_key": "embedded:main:1",
                "source_kind": "EMBEDDED",
                "source_main_document_id": "DOC-001",
                "source_locator": "main:attachment-section-1",
                "title": "内嵌技术协议",
                "parsed_content_sha256": SHA_C,
            },
        ],
    }


def fact_payload(data: dict | list | None = None) -> dict:
    return {"state": "COMPLETE", "data": {} if data is None else data, "issues": []}


def context_payload() -> dict:
    return {
        "schema_version": "review-context/v1",
        "source_snapshot": source_snapshot_payload(),
        "shared_facts": {
            "header": fact_payload(),
            "parties": fact_payload([]),
            "signature": fact_payload(),
            "amount_payment": fact_payload(),
            "attachment_manifest": fact_payload([]),
        },
        "evidence_index": {
            "party_mentions": [],
            "signature_mentions": [],
            "amount_mentions": [],
            "attachment_relations": [],
        },
        "preparation_issues": [],
        "preparation_meta": {
            "pipeline_version": "contract-review-prepare/1.0.0",
            "prompt_bundle_hash": SHA_A,
            "model_deployment": "qwen3.6-35b-a3b",
            "created_at": "2026-07-31T10:00:00+08:00",
        },
        "context_digest": SHA_B,
    }


def test_source_snapshot_accepts_uploaded_and_embedded_union():
    snapshot = SourceSnapshot.model_validate(source_snapshot_payload())

    assert snapshot.attachments[0].source_kind == "UPLOADED"
    assert snapshot.attachments[0].attachment_id == "ATT-001"
    assert snapshot.attachments[1].source_kind == "EMBEDDED"
    assert snapshot.attachments[1].source_locator == "main:attachment-section-1"


def test_source_snapshot_rejects_duplicate_document_keys():
    payload = source_snapshot_payload()
    payload["attachments"][1]["document_key"] = "attachment:ATT-001"

    with pytest.raises(ValidationError, match="document_key"):
        SourceSnapshot.model_validate(payload)


def test_source_snapshot_rejects_attachment_using_main_key():
    payload = source_snapshot_payload()
    payload["attachments"][0]["document_key"] = "main"

    with pytest.raises(ValidationError, match="document_key"):
        SourceSnapshot.model_validate(payload)


def test_source_snapshot_rejects_blank_document_identity():
    payload = source_snapshot_payload()
    payload["attachments"][0]["document_key"] = "   "

    with pytest.raises(ValidationError, match="document_key"):
        SourceSnapshot.model_validate(payload)


def test_source_snapshot_rejects_embedded_attachment_from_other_main_document():
    payload = source_snapshot_payload()
    payload["attachments"][1]["source_main_document_id"] = "DOC-OTHER"

    with pytest.raises(ValidationError, match="source_main_document_id"):
        SourceSnapshot.model_validate(payload)


@pytest.mark.parametrize("state", ["PARTIAL", "UNAVAILABLE"])
def test_incomplete_fact_requires_issue(state: str):
    with pytest.raises(ValidationError, match="issues"):
        FactDomain(state=state, data={}, issues=[])


def test_complete_fact_rejects_gap_issue():
    with pytest.raises(ValidationError, match="COMPLETE"):
        FactDomain(state="COMPLETE", data={}, issues=["仍有缺口"])


def test_incomplete_fact_rejects_blank_issue():
    with pytest.raises(ValidationError, match="issues"):
        FactDomain(state="PARTIAL", data={}, issues=["   "])


def test_evidence_requires_traceable_source_and_quote():
    with pytest.raises(ValidationError):
        EvidenceRef(document_key="main", source_locator="", quote="")


def test_context_payload_omits_optional_source_metadata():
    context = ReviewContext.model_validate(context_payload())

    payload = context.to_payload()

    assert payload["schema_version"] == "review-context/v1"
    assert "source_file_sha256" not in payload["source_snapshot"]["main_document"]
    assert "parser_meta" not in payload["source_snapshot"]


def test_sha256_fields_reject_uppercase_or_missing_prefix():
    payload = source_snapshot_payload()
    payload["main_document"]["parsed_content_sha256"] = "A" * 64

    with pytest.raises(ValidationError, match="parsed_content_sha256"):
        SourceSnapshot.model_validate(payload)
