from __future__ import annotations

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
    normalize_markdown,
)


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


def _locator_key(locator: str) -> tuple[int, int, str]:
    prefix = "markdown-chars:"
    if not locator.startswith(prefix):
        return (10**18, 10**18, locator)
    body = locator[len(prefix):]
    parts = body.split("-", maxsplit=1)
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return (10**18, 10**18, locator)
    return (int(parts[0]), int(parts[1]), locator)


def _build_evidence_position_index(value: Mapping[str, Any]) -> dict[str, tuple[str, int, int, str]]:
    index: dict[str, tuple[str, int, int, str]] = {}
    evidence_items = value.get("evidence_index", {}).get("items", [])
    if not isinstance(evidence_items, list):
        return index
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        evidence_id = item.get("evidence_id")
        document_key = item.get("document_key")
        source_locator = item.get("source_locator")
        if not isinstance(evidence_id, str):
            continue
        start, end, _ = _locator_key(str(source_locator))
        index[evidence_id] = (str(document_key), start, end, evidence_id)
    return index


def _first_evidence_coordinate(
    evidence_ids: list[Any],
    evidence_position_index: Mapping[str, tuple[str, int, int, str]],
) -> tuple[str, int, int, str]:
    resolved: list[tuple[str, int, int, str]] = []
    for evidence_id in evidence_ids:
        key = str(evidence_id)
        if key in evidence_position_index:
            resolved.append(evidence_position_index[key])
    if resolved:
        return min(resolved)
    if evidence_ids:
        fallback = min(str(evidence_id) for evidence_id in evidence_ids)
        return ("", 10**18, 10**18, fallback)
    return ("", 10**18, 10**18, "")


def _normalize_for_sort(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _dict_sort_key(
    item: dict[str, Any],
    evidence_position_index: Mapping[str, tuple[str, int, int, str]],
) -> tuple[Any, ...]:
    if {
        "evidence_id",
        "document_key",
        "source_locator",
    }.issubset(item):
        start, end, _ = _locator_key(str(item["source_locator"]))
        return (
            0,
            str(item["document_key"]),
            start,
            end,
            str(item["evidence_id"]),
        )

    if "source_locator" in item and "document_key" in item:
        start, end, _ = _locator_key(str(item["source_locator"]))
        return (
            1,
            str(item["document_key"]),
            start,
            end,
            canonical_json_bytes(item),
        )

    keyed_sort_fields = [
        "fact_issue_key",
        "preparation_issue_key",
        "party_key",
        "designation_key",
        "mention_key",
        "signature_block_key",
        "signer_slot_key",
        "signer_group_key",
        "signer_key",
        "identity_number_key",
        "signature_date_key",
        "field_observation_key",
        "amount_key",
        "amount_relation_key",
        "payment_method_key",
        "payment_stage_key",
        "statement_key",
        "allocation_key",
        "attachment_declaration_key",
        "logical_attachment_candidate_key",
        "attachment_relation_key",
        "document_key",
    ]
    for order, field_name in enumerate(keyed_sort_fields, start=10):
        if field_name in item:
            return (order, str(item[field_name]), canonical_json_bytes(item))

    if "evidence_ids" in item and isinstance(item["evidence_ids"], list):
        first_coord = _first_evidence_coordinate(item["evidence_ids"], evidence_position_index)
        normalized_value = _normalize_for_sort(item.get("normalized_value"))
        raw_text = str(item.get("raw_text", ""))
        return (
            100,
            first_coord,
            normalized_value,
            raw_text,
            canonical_json_bytes(item),
        )

    return (999, canonical_json_bytes(item))


def _sort_list(
    items: list[Any],
    evidence_position_index: Mapping[str, tuple[str, int, int, str]],
) -> list[Any]:
    if not items:
        return []

    if all(isinstance(item, dict) for item in items):
        dict_items = [_deep_sort(item, evidence_position_index) for item in items]
        return sorted(
            dict_items,
            key=lambda item: _dict_sort_key(item, evidence_position_index),
        )

    if all(isinstance(item, str) for item in items) and all(item in evidence_position_index for item in items):
        return sorted(items, key=lambda item: evidence_position_index[item])

    if all(not isinstance(item, (dict, list)) for item in items):
        return sorted(items, key=lambda item: str(item))

    return [_deep_sort(item, evidence_position_index) for item in items]


def _deep_sort(
    value: Any,
    evidence_position_index: Mapping[str, tuple[str, int, int, str]],
) -> Any:
    if isinstance(value, dict):
        return {
            key: _deep_sort(value[key], evidence_position_index)
            for key in sorted(value.keys())
        }
    if isinstance(value, list):
        return _sort_list(value, evidence_position_index)
    return value


def sort_review_context(context: ReviewContext | Mapping[str, Any]) -> ReviewContext:
    resolved = context if isinstance(context, ReviewContext) else ReviewContext.model_validate(context)
    payload = resolved.to_payload()
    evidence_position_index = _build_evidence_position_index(payload)
    sorted_payload = _deep_sort(payload, evidence_position_index)
    return ReviewContext.model_validate(sorted_payload)


def compute_context_digest(context: ReviewContext | Mapping[str, Any]) -> str:
    if isinstance(context, ReviewContext):
        sorted_context = sort_review_context(context)
        payload = sorted_context.to_payload()
    else:
        raw_payload = dict(context)
        evidence_position_index = _build_evidence_position_index(raw_payload)
        payload = _deep_sort(raw_payload, evidence_position_index)
    payload = {key: value for key, value in payload.items() if key != "context_digest"}
    return _sha256_digest(canonical_json_bytes(payload))
