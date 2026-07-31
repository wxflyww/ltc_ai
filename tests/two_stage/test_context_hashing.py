import pytest

from app.capabilities.contract_review.two_stage.hashing import (
    canonical_json_bytes,
    compute_context_digest,
    compute_document_set_hash,
    normalize_markdown,
    normalize_snapshot_name,
    parsed_content_sha256,
)
from app.capabilities.contract_review.two_stage.schemas import ReviewContext, SourceSnapshot


SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64
SHA_C = "sha256:" + "c" * 64


def snapshot(attachments: list[dict]) -> SourceSnapshot:
    return SourceSnapshot.model_validate({
        "contract_id": "C001",
        "revision_id": "V1",
        "document_set_hash": SHA_A,
        "main_document": {
            "document_key": "main",
            "document_id": "DOC-001",
            "filename": "contracts/ 主合同.md ",
            "parsed_content_sha256": SHA_B,
        },
        "attachments": attachments,
    })


def uploaded() -> dict:
    return {
        "document_key": "attachment:ATT-002",
        "source_kind": "UPLOADED",
        "attachment_id": "ATT-002",
        "filename": "uploads/技术协议.md",
        "parsed_content_sha256": SHA_C,
    }


def embedded() -> dict:
    return {
        "document_key": "embedded:main:1",
        "source_kind": "EMBEDDED",
        "source_main_document_id": "DOC-001",
        "source_locator": "main:attachment-section-1",
        "title": " 内嵌技术协议 ",
        "parsed_content_sha256": SHA_A,
    }


def review_context_payload(header_data: dict) -> dict:
    return {
        "schema_version": "review-context/v1",
        "source_snapshot": snapshot([]).model_dump(mode="json", exclude_none=True),
        "shared_facts": {
            "header": {"state": "COMPLETE", "data": header_data, "issues": []},
            "parties": {"state": "COMPLETE", "data": [], "issues": []},
            "signature": {"state": "COMPLETE", "data": {}, "issues": []},
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
        "context_digest": SHA_B,
    }


def test_markdown_hash_normalizes_bom_newlines_and_unicode():
    left = "\ufeff# Caf\u00e9\r\n正文\r"
    right = "# Cafe\u0301\n正文\n"

    assert normalize_markdown(left) == normalize_markdown(right)
    assert parsed_content_sha256(left) == parsed_content_sha256(right)
    assert parsed_content_sha256(left) == (
        "sha256:0a53dd0f3d21d6c582ac3eeb18058852a4e8091f6c7b42faa63fb6ced14af335"
    )


def test_markdown_hash_preserves_spaces_blank_lines_and_markup():
    assert parsed_content_sha256("# A\n") != parsed_content_sha256("#  A\n")
    assert parsed_content_sha256("# A\n") != parsed_content_sha256("A\n")
    assert parsed_content_sha256("A\n\nB") != parsed_content_sha256("A\nB")


def test_snapshot_name_removes_path_and_outer_whitespace_only():
    assert normalize_snapshot_name(r"C:\tmp\ 技术协议 V1.0.MD ") == "技术协议 V1.0.MD"
    assert normalize_snapshot_name("path/技术协议 v1.0.md") == "技术协议 v1.0.md"


def test_canonical_json_uses_sorted_compact_utf8():
    assert canonical_json_bytes({"b": 1, "a": "中文"}) == '{"a":"中文","b":1}'.encode("utf-8")


def test_canonical_json_rejects_nan():
    with pytest.raises(ValueError):
        canonical_json_bytes({"value": float("nan")})


def test_document_set_hash_is_attachment_order_independent():
    first = snapshot([uploaded(), embedded()])
    second = snapshot([embedded(), uploaded()])

    assert compute_document_set_hash(first) == compute_document_set_hash(second)


def test_document_set_hash_can_be_created_before_source_snapshot_exists():
    existing = snapshot([uploaded(), embedded()])

    assert compute_document_set_hash(
        existing.main_document,
        existing.attachments,
    ) == compute_document_set_hash(existing)


def test_document_set_hash_changes_with_identity_name_or_content():
    baseline = compute_document_set_hash(snapshot([uploaded()]))

    changed_key = uploaded()
    changed_key["document_key"] = "attachment:ATT-003"
    changed_name = uploaded()
    changed_name["filename"] = "uploads/技术协议-v2.md"
    changed_content = uploaded()
    changed_content["parsed_content_sha256"] = SHA_B

    assert compute_document_set_hash(snapshot([changed_key])) != baseline
    assert compute_document_set_hash(snapshot([changed_name])) != baseline
    assert compute_document_set_hash(snapshot([changed_content])) != baseline


def test_context_digest_ignores_existing_digest_and_optional_model_none():
    first = review_context_payload({})
    first["source_snapshot"]["parser_meta"] = None
    second = review_context_payload({})
    second["context_digest"] = SHA_A

    assert compute_context_digest(first) == compute_context_digest(second)


def test_context_digest_is_identical_for_model_and_json_mapping_with_nested_null():
    payload = review_context_payload({"unknown": None})
    context = ReviewContext.model_validate(payload)

    assert compute_context_digest(context) == compute_context_digest(context.to_payload())


def test_context_digest_distinguishes_nested_null_from_absent_key():
    with_null = review_context_payload({"unknown": None})
    without_key = review_context_payload({})

    assert compute_context_digest(with_null) != compute_context_digest(without_key)
