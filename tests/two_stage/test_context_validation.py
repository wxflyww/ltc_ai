import pytest

from app.capabilities.contract_review.two_stage.hashing import (
    compute_context_digest,
    compute_document_set_hash,
    sort_review_context,
)
from app.capabilities.contract_review.two_stage.schemas import ReviewContext, SourceSnapshot
from app.capabilities.contract_review.two_stage.validation import (
    ContextIntegrityError,
    ContextSchemaUnsupportedError,
    DocumentRevisionMismatchError,
    validate_review_context,
)
from tests.two_stage.factories import clone_payload, valid_context_payload


def _build_valid_context() -> tuple[ReviewContext, dict[str, str]]:
    payload = valid_context_payload()
    embedded_markdown = "附件一：技术规范书\n内容"
    prefix_for_embedded = "采购合同" + "abcdef"
    embedded_start = len(prefix_for_embedded)
    embedded_end = embedded_start + len(embedded_markdown)
    payload["source_snapshot"]["attachments"][1]["source_locator"] = f"markdown-chars:{embedded_start}-{embedded_end}"

    source = SourceSnapshot.model_validate(payload["source_snapshot"])
    payload["source_snapshot"]["document_set_hash"] = compute_document_set_hash(source)
    payload["context_digest"] = "sha256:" + "0" * 64

    context = ReviewContext.model_validate(payload)
    context = sort_review_context(context)

    context_payload = context.to_payload()
    context_payload["context_digest"] = compute_context_digest(context_payload)
    context = ReviewContext.model_validate(context_payload)

    embedded = [
        item
        for item in context.source_snapshot.attachments
        if item.source_kind == "EMBEDDED"
    ][0]
    prefix = "markdown-chars:"
    start, end = embedded.source_locator[len(prefix):].split("-", maxsplit=1)
    start_idx = int(start)
    end_idx = int(end)
    main_markdown = prefix_for_embedded + embedded_markdown + "y" * 5

    markdown_by_document = {
        "main": main_markdown,
        "uploaded:att-001": "技术协议\n附件正文",
        "embedded:main:001": embedded_markdown,
    }
    return context, markdown_by_document


def test_accepts_valid_context_and_matching_outer_version():
    context, markdown_by_document = _build_valid_context()

    assert (
        validate_review_context(
            context,
            contract_id="C-2026-0001",
            revision_id="V3",
            markdown_by_document=markdown_by_document,
        )
        is None
    )


def test_rejects_unsupported_schema_before_other_checks():
    context, markdown_by_document = _build_valid_context()
    unsupported = context.model_copy(update={"schema_version": "review-context/v2"})

    with pytest.raises(ContextSchemaUnsupportedError, match="review-context/v2"):
        validate_review_context(
            unsupported,
            markdown_by_document=markdown_by_document,
        )


def test_rejects_document_set_hash_before_context_digest():
    context, markdown_by_document = _build_valid_context()
    payload = context.to_payload()
    payload["source_snapshot"]["document_set_hash"] = "sha256:" + "f" * 64
    payload["context_digest"] = compute_context_digest(payload)
    tampered = ReviewContext.model_validate(payload)

    with pytest.raises(ContextIntegrityError, match="document_set_hash"):
        validate_review_context(tampered, markdown_by_document=markdown_by_document)


def test_rejects_changed_context_payload_without_updated_digest():
    context, markdown_by_document = _build_valid_context()
    payload = context.to_payload()
    payload["shared_facts"]["header"]["data"]["contract_identity"]["number"]["presence"] = "PRESENT_EMPTY"
    payload["shared_facts"]["header"]["data"]["contract_identity"]["number"]["observations"] = [
        {
            "raw_text": "",
            "evidence_ids": ["evidence:main:header-name"],
        }
    ]
    tampered = ReviewContext.model_validate(payload)

    with pytest.raises(ContextIntegrityError, match="context_digest"):
        validate_review_context(tampered, markdown_by_document=markdown_by_document)


def test_rejects_evidence_slice_quote_mismatch_when_markdown_provided():
    context, markdown_by_document = _build_valid_context()
    wrong_markdown = clone_payload(markdown_by_document)
    wrong_markdown["main"] = wrong_markdown["main"].replace("采购合同", "采购文本", 1)

    with pytest.raises(ContextIntegrityError, match="quote"):
        validate_review_context(context, markdown_by_document=wrong_markdown)


def test_rejects_embedded_two_hop_locator_out_of_bounds():
    context, markdown_by_document = _build_valid_context()
    wrong_markdown = clone_payload(markdown_by_document)
    wrong_markdown["main"] = "too-short"

    with pytest.raises(ContextIntegrityError, match="内嵌附件 locator 越界"):
        validate_review_context(context, markdown_by_document=wrong_markdown)


def test_rejects_embedded_two_hop_locator_slice_mismatch():
    context, markdown_by_document = _build_valid_context()
    wrong_markdown = clone_payload(markdown_by_document)
    wrong_markdown["main"] = wrong_markdown["main"].replace("附件一：技术规范书\n内容", "附件一：技术规范书\n错配")

    with pytest.raises(ContextIntegrityError, match="内嵌附件绝对 locator 切片"):
        validate_review_context(context, markdown_by_document=wrong_markdown)


def test_accepts_embedded_two_hop_locator_when_slice_matches():
    context, markdown_by_document = _build_valid_context()

    assert validate_review_context(context, markdown_by_document=markdown_by_document) is None


@pytest.mark.parametrize(
    ("contract_id", "revision_id"),
    [("C-OTHER", "V3"), ("C-2026-0001", "V4")],
)
def test_rejects_outer_contract_or_revision_mismatch(contract_id: str, revision_id: str):
    context, markdown_by_document = _build_valid_context()

    with pytest.raises(DocumentRevisionMismatchError):
        validate_review_context(
            context,
            contract_id=contract_id,
            revision_id=revision_id,
            markdown_by_document=markdown_by_document,
        )
