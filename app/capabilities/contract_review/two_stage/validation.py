from app.capabilities.contract_review.two_stage.hashing import (
    compute_context_digest,
    compute_document_set_hash,
)
from app.capabilities.contract_review.two_stage.schemas import SCHEMA_VERSION, ReviewContext


class ReviewContextValidationError(ValueError):
    pass


class ContextSchemaUnsupportedError(ReviewContextValidationError):
    pass


class ContextIntegrityError(ReviewContextValidationError):
    pass


class DocumentRevisionMismatchError(ReviewContextValidationError):
    pass


def validate_review_context(
    context: ReviewContext,
    *,
    contract_id: str | None = None,
    revision_id: str | None = None,
) -> None:
    if context.schema_version != SCHEMA_VERSION:
        raise ContextSchemaUnsupportedError(
            f"不支持的 ReviewContext schema_version：{context.schema_version}"
        )

    expected_document_set_hash = compute_document_set_hash(context.source_snapshot)
    if context.source_snapshot.document_set_hash != expected_document_set_hash:
        raise ContextIntegrityError("ReviewContext document_set_hash 与文档集合不一致")

    expected_context_digest = compute_context_digest(context)
    if context.context_digest != expected_context_digest:
        raise ContextIntegrityError("ReviewContext context_digest 与上下文内容不一致")

    snapshot = context.source_snapshot
    document_keys = {
        snapshot.main_document.document_key,
        *(attachment.document_key for attachment in snapshot.attachments),
    }
    evidence_groups = (
        context.evidence_index.party_mentions,
        context.evidence_index.signature_mentions,
        context.evidence_index.amount_mentions,
        context.evidence_index.attachment_relations,
    )
    for evidence_group in evidence_groups:
        for evidence in evidence_group:
            if evidence.document_key not in document_keys:
                raise ContextIntegrityError(
                    "ReviewContext 证据 document_key 不存在于当前文档快照："
                    f"{evidence.document_key}"
                )

    if contract_id is not None and contract_id != snapshot.contract_id:
        raise DocumentRevisionMismatchError(
            f"contract_id 不一致：请求为 {contract_id}，上下文为 {snapshot.contract_id}"
        )
    if revision_id is not None and revision_id != snapshot.revision_id:
        raise DocumentRevisionMismatchError(
            f"revision_id 不一致：请求为 {revision_id}，上下文为 {snapshot.revision_id}"
        )
