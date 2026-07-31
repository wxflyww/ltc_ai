import hashlib
import json
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

from app.capabilities.contract_review.two_stage.schemas import (
    AttachmentSnapshot,
    EmbeddedAttachmentSnapshot,
    MainDocumentSnapshot,
    ReviewContext,
    SourceSnapshot,
)


def normalize_markdown(markdown: str) -> str:
    if markdown.startswith("\ufeff"):
        markdown = markdown[1:]
    normalized = unicodedata.normalize("NFC", markdown)
    return normalized.replace("\r\n", "\n").replace("\r", "\n")


def _sha256_digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def parsed_content_sha256(markdown: str) -> str:
    return _sha256_digest(normalize_markdown(markdown).encode("utf-8"))


def normalize_snapshot_name(value: str) -> str:
    filename = value.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    normalized = unicodedata.normalize("NFC", filename).strip()
    if not normalized:
        raise ValueError("文档文件名或内嵌附件标题不能为空")
    return normalized


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _document_manifest(
    main_document: MainDocumentSnapshot,
    attachments: Sequence[AttachmentSnapshot],
) -> list[dict[str, str]]:
    manifest = [{
        "document_key": main_document.document_key,
        "filename": normalize_snapshot_name(main_document.filename),
        "parsed_content_sha256": main_document.parsed_content_sha256,
    }]
    for attachment in sorted(attachments, key=lambda item: item.document_key):
        name = attachment.title if isinstance(attachment, EmbeddedAttachmentSnapshot) else attachment.filename
        manifest.append({
            "document_key": attachment.document_key,
            "filename": normalize_snapshot_name(name),
            "parsed_content_sha256": attachment.parsed_content_sha256,
        })
    return manifest


def compute_document_set_hash(
    source: SourceSnapshot | MainDocumentSnapshot,
    attachments: Sequence[AttachmentSnapshot] | None = None,
) -> str:
    if isinstance(source, SourceSnapshot):
        if attachments is not None:
            raise TypeError("传入 SourceSnapshot 时不得另行提供 attachments")
        main_document = source.main_document
        resolved_attachments = source.attachments
    else:
        main_document = source
        resolved_attachments = attachments or []
    manifest = _document_manifest(main_document, resolved_attachments)
    return _sha256_digest(canonical_json_bytes(manifest))


def compute_context_digest(context: ReviewContext | Mapping[str, Any]) -> str:
    normalized = (
        context
        if isinstance(context, ReviewContext)
        else ReviewContext.model_validate(context)
    )
    payload = normalized.to_payload()
    payload = {key: value for key, value in payload.items() if key != "context_digest"}
    return _sha256_digest(canonical_json_bytes(payload))
