from __future__ import annotations

from collections.abc import Mapping

from app.capabilities.contract_review.two_stage.evidence import parse_markdown_locator
from app.capabilities.contract_review.two_stage.hashing import (
    compute_context_digest,
    compute_document_set_hash,
    sort_review_context,
)
from app.capabilities.contract_review.two_stage.schemas import (
    SCHEMA_VERSION,
    EmbeddedAttachmentSnapshot,
    ReviewContext,
)


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
    markdown_by_document: Mapping[str, str] | None = None,
) -> None:
    if context.schema_version != SCHEMA_VERSION:
        raise ContextSchemaUnsupportedError(
            f"不支持的 ReviewContext schema_version：{context.schema_version}"
        )

    sorted_context = sort_review_context(context)

    expected_document_set_hash = compute_document_set_hash(sorted_context.source_snapshot)
    if sorted_context.source_snapshot.document_set_hash != expected_document_set_hash:
        raise ContextIntegrityError("ReviewContext document_set_hash 与文档集合不一致")

    expected_context_digest = compute_context_digest(sorted_context)
    if sorted_context.context_digest != expected_context_digest:
        raise ContextIntegrityError("ReviewContext context_digest 与上下文内容不一致")

    snapshot = sorted_context.source_snapshot
    document_keys = {
        snapshot.main_document.document_key,
        *(attachment.document_key for attachment in snapshot.attachments),
    }

    if markdown_by_document is not None:
        for key in document_keys:
            if key not in markdown_by_document:
                raise ContextIntegrityError(f"缺少用于切片校验的 markdown 文档：{key}")

        main_markdown = markdown_by_document[snapshot.main_document.document_key]
        for attachment in snapshot.attachments:
            if not isinstance(attachment, EmbeddedAttachmentSnapshot):
                continue
            start, end = parse_markdown_locator(attachment.source_locator)
            if end > len(main_markdown):
                raise ContextIntegrityError(
                    "内嵌附件 locator 越界："
                    f"{attachment.document_key} {attachment.source_locator}"
                )
            embedded_markdown = markdown_by_document[attachment.document_key]
            if main_markdown[start:end] != embedded_markdown:
                raise ContextIntegrityError(
                    "内嵌附件绝对 locator 切片与派生 Markdown 不一致"
                )

    evidence_ids: set[str] = set()
    for evidence in sorted_context.evidence_index.items:
        if evidence.evidence_id in evidence_ids:
            raise ContextIntegrityError(f"evidence_id 重复：{evidence.evidence_id}")
        evidence_ids.add(evidence.evidence_id)

        if evidence.document_key not in document_keys:
            raise ContextIntegrityError(
                "ReviewContext 证据 document_key 不存在于当前文档快照："
                f"{evidence.document_key}"
            )

        if markdown_by_document is not None:
            markdown = markdown_by_document[evidence.document_key]
            start, end = parse_markdown_locator(evidence.source_locator)
            if end > len(markdown):
                raise ContextIntegrityError(
                    f"evidence locator 越界：{evidence.document_key} {evidence.source_locator}"
                )
            if markdown[start:end] != evidence.quote:
                raise ContextIntegrityError(
                    "evidence quote 与 source_locator 切片不一致"
                )

    for issue in sorted_context.preparation_issues:
        for document_key in issue.related_document_keys:
            if document_key not in document_keys:
                raise ContextIntegrityError(
                    "preparation issue 引用了不存在的 document_key："
                    f"{document_key}"
                )
        for evidence_id in issue.evidence_ids:
            if evidence_id not in evidence_ids:
                raise ContextIntegrityError(
                    "preparation issue 引用了不存在的 evidence_id："
                    f"{evidence_id}"
                )

    for domain_name in [
        "header",
        "parties",
        "signature",
        "amount_payment",
        "copy_terms",
        "attachment_manifest",
    ]:
        domain = getattr(sorted_context.shared_facts, domain_name)
        coverage_issue_keys = {
            key
            for coverage in domain.coverage
            for key in coverage.fact_issue_keys
        }
        issue_keys = {issue.fact_issue_key for issue in domain.issues}
        if coverage_issue_keys != issue_keys:
            raise ContextIntegrityError(
                f"{domain_name} coverage 与 fact issues 引用未闭合"
            )

    if contract_id is not None and contract_id != snapshot.contract_id:
        raise DocumentRevisionMismatchError(
            f"contract_id 不一致：请求为 {contract_id}，上下文为 {snapshot.contract_id}"
        )

    if revision_id is not None and revision_id != snapshot.revision_id:
        raise DocumentRevisionMismatchError(
            f"revision_id 不一致：请求为 {revision_id}，上下文为 {snapshot.revision_id}"
        )
