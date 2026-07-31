import pytest

from app.capabilities.contract_review.two_stage.hashing import (
    compute_context_digest,
    compute_document_set_hash,
)
from app.capabilities.contract_review.two_stage.schemas import ReviewContext, SourceSnapshot
from app.capabilities.contract_review.two_stage.validation import (
    ContextIntegrityError,
    ContextSchemaUnsupportedError,
    DocumentRevisionMismatchError,
    validate_review_context,
)


SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64


def build_context() -> ReviewContext:
    source_payload = {
        "contract_id": "C001",
        "revision_id": "V1",
        "document_set_hash": SHA_A,
        "main_document": {
            "document_key": "main",
            "document_id": "DOC-001",
            "filename": "主合同.md",
            "parsed_content_sha256": SHA_B,
        },
        "attachments": [],
    }
    source = SourceSnapshot.model_validate(source_payload)
    source_payload["document_set_hash"] = compute_document_set_hash(source)
    payload = {
        "schema_version": "review-context/v1",
        "source_snapshot": source_payload,
        "shared_facts": {
            "header": {"state": "COMPLETE", "data": {}, "issues": []},
            "parties": {"state": "COMPLETE", "data": [], "issues": []},
            "signature": {"state": "PARTIAL", "data": {}, "issues": ["签章日期未提取"]},
            "amount_payment": {"state": "COMPLETE", "data": {}, "issues": []},
            "attachment_manifest": {"state": "COMPLETE", "data": [], "issues": []},
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
        "context_digest": SHA_A,
    }
    payload["context_digest"] = compute_context_digest(payload)
    return ReviewContext.model_validate(payload)


def with_recomputed_digest(payload: dict) -> ReviewContext:
    payload["context_digest"] = compute_context_digest(payload)
    return ReviewContext.model_validate(payload)


def test_accepts_valid_context_and_matching_outer_version():
    context = build_context()

    assert validate_review_context(context, contract_id="C001", revision_id="V1") is None


def test_rejects_unsupported_schema_before_digest_checks():
    payload = build_context().to_payload()
    payload["schema_version"] = "review-context/v2"
    context = ReviewContext.model_validate(payload)

    with pytest.raises(ContextSchemaUnsupportedError, match="review-context/v2"):
        validate_review_context(context)


def test_rejects_changed_document_set_even_with_recomputed_context_digest():
    payload = build_context().to_payload()
    payload["source_snapshot"]["document_set_hash"] = SHA_A
    context = with_recomputed_digest(payload)

    with pytest.raises(ContextIntegrityError, match="document_set_hash"):
        validate_review_context(context)


def test_rejects_changed_context_payload_without_updated_digest():
    payload = build_context().to_payload()
    payload["shared_facts"]["header"]["data"] = {"contract_name": "被修改"}
    context = ReviewContext.model_validate(payload)

    with pytest.raises(ContextIntegrityError, match="context_digest"):
        validate_review_context(context)


@pytest.mark.parametrize(
    "evidence_category",
    [
        "party_mentions",
        "signature_mentions",
        "amount_mentions",
        "attachment_relations",
    ],
)
def test_rejects_evidence_pointing_to_document_outside_snapshot(
    evidence_category: str,
):
    payload = build_context().to_payload()
    payload["evidence_index"][evidence_category] = [{
        "document_key": "attachment:UNKNOWN",
        "source_locator": "paragraph:1",
        "quote": "无法追溯到当前文档快照的证据",
    }]
    payload = ReviewContext.model_validate(payload).to_payload()
    context = with_recomputed_digest(payload)

    with pytest.raises(ContextIntegrityError, match="document_key"):
        validate_review_context(context)


@pytest.mark.parametrize(
    ("contract_id", "revision_id"),
    [("C002", "V1"), ("C001", "V2")],
)
def test_rejects_outer_contract_or_revision_mismatch(contract_id: str, revision_id: str):
    context = build_context()

    with pytest.raises(DocumentRevisionMismatchError):
        validate_review_context(context, contract_id=contract_id, revision_id=revision_id)
