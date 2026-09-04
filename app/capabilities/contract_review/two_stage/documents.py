from __future__ import annotations

from dataclasses import dataclass
import re
from typing import NamedTuple

from app.capabilities.contract_review.two_stage.hashing import (
    compute_document_set_hash,
    normalize_snapshot_name,
    parsed_content_sha256,
)
from app.capabilities.contract_review.two_stage.keys import stable_key
from app.capabilities.contract_review.two_stage.schemas import (
    EmbeddedAttachmentSnapshot,
    MainDocumentSnapshot,
    PreparationIssue,
    PrepareRequest,
    SourceSnapshot,
    UploadedAttachmentSnapshot,
)


class PrepareDuplicateError(ValueError):
    pass


@dataclass
class PreparedDocuments:
    source_snapshot: SourceSnapshot
    markdown_by_document: dict[str, str]
    preparation_issues: list[PreparationIssue]


class _EmbeddedAttachmentCandidate(NamedTuple):
    document_key: str
    title: str
    markdown: str
    body_content_sha256: str
    source_locator: str
    parsed_content_sha256: str


class _UploadedAttachmentCandidate(NamedTuple):
    document_key: str
    attachment_id: str
    filename: str
    markdown: str
    parsed_content_sha256: str
    source_file_sha256: str | None


_ATTACHMENT_TITLE_PREFIX_RE = re.compile(r"^附件[一二三四五六七八九十0-9]+[：:\-\s]*")


def _normalize_title_compare_key(value: str) -> str:
    normalized = normalize_snapshot_name(value)
    lowered = normalized.lower()
    for extension in [".md", ".markdown", ".txt", ".doc", ".docx", ".pdf"]:
        if lowered.endswith(extension):
            normalized = normalized[: -len(extension)]
            break
    normalized = normalized.strip()
    normalized = _ATTACHMENT_TITLE_PREFIX_RE.sub("", normalized)
    if normalized.startswith("上传"):
        normalized = normalized[2:]
    return "".join(normalized.split())


def _extract_embedded_attachments(main_document_id: str, markdown: str) -> list[_EmbeddedAttachmentCandidate]:
    lines = markdown.splitlines(keepends=True)
    offsets: list[int] = []
    cursor = 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line)

    candidates: list[tuple[int, str, int]] = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("##"):
            continue
        heading = stripped.lstrip("#").strip()
        if not heading.startswith("附件"):
            continue
        candidates.append((idx, heading, offsets[idx]))

    embedded: list[_EmbeddedAttachmentCandidate] = []
    for ordinal, (start_idx, heading, start_offset) in enumerate(candidates, start=1):
        end_idx = len(lines)
        for next_start_idx, _, _ in candidates:
            if next_start_idx > start_idx:
                end_idx = next_start_idx
                break

        segment = "".join(lines[start_idx:end_idx])
        segment_lines = segment.splitlines()
        body = "\n".join(segment_lines[1:]).strip() if len(segment_lines) > 1 else ""
        if not body:
            continue

        document_key = stable_key(
            "embedded",
            {
                "main_document_id": main_document_id,
                "start": start_offset,
                "end": start_offset + len(segment),
                "title": normalize_snapshot_name(heading),
            },
        )
        locator = f"markdown-chars:{start_offset}-{start_offset + len(segment)}"
        embedded.append(
            _EmbeddedAttachmentCandidate(
                document_key=document_key,
                title=normalize_snapshot_name(heading),
                markdown=segment,
                body_content_sha256=parsed_content_sha256(body),
                source_locator=locator,
                parsed_content_sha256=parsed_content_sha256(segment),
            )
        )

    return embedded


def _build_uploaded_candidates(request: PrepareRequest) -> list[_UploadedAttachmentCandidate]:
    candidates: list[_UploadedAttachmentCandidate] = []
    for item in request.uploaded_attachments:
        document_key = stable_key(
            "uploaded",
            {
                "attachment_id": item.attachment_id,
            },
        )
        candidates.append(
            _UploadedAttachmentCandidate(
                document_key=document_key,
                attachment_id=item.attachment_id,
                filename=normalize_snapshot_name(item.filename),
                markdown=item.markdown,
                parsed_content_sha256=parsed_content_sha256(item.markdown),
                source_file_sha256=item.source_file_sha256,
            )
        )
    return candidates


def _reject_definite_duplicates(
    uploaded: list[_UploadedAttachmentCandidate],
    embedded: list[_EmbeddedAttachmentCandidate],
) -> None:
    attachment_ids: set[str] = set()
    for item in uploaded:
        if item.attachment_id in attachment_ids:
            raise PrepareDuplicateError(f"attachment_id 重复: {item.attachment_id}")
        attachment_ids.add(item.attachment_id)

    uploaded_pairs: set[tuple[str, str]] = set()
    for item in uploaded:
        pair = (item.filename, item.parsed_content_sha256)
        if pair in uploaded_pairs:
            raise PrepareDuplicateError("上传附件存在 文件名+内容 明确重复")
        uploaded_pairs.add(pair)

    embedded_pairs: dict[tuple[str, str], _EmbeddedAttachmentCandidate] = {}
    for item in embedded:
        pair = (_normalize_title_compare_key(item.title), item.body_content_sha256)
        if pair in embedded_pairs:
            raise PrepareDuplicateError("内嵌附件存在 标题+内容 明确重复")
        embedded_pairs[pair] = item
    for item in uploaded:
        probe = (_normalize_title_compare_key(item.filename), item.parsed_content_sha256)
        if probe in embedded_pairs:
            raise PrepareDuplicateError("内嵌附件标题与上传附件内容明确重复")


def _build_suspected_duplicate_issues(
    uploaded: list[_UploadedAttachmentCandidate],
    embedded: list[_EmbeddedAttachmentCandidate],
) -> list[PreparationIssue]:
    issues: list[PreparationIssue] = []

    def append_issue(document_keys: list[str], basis: str) -> None:
        ordered_keys = sorted(set(document_keys))
        issue_key = stable_key(
            "preparation_issue",
            {
                "code": "SUSPECTED_DUPLICATE",
                "basis": basis,
                "document_keys": ordered_keys,
            },
        )
        issues.append(
            PreparationIssue(
                preparation_issue_key=issue_key,
                code="SUSPECTED_DUPLICATE",
                message="附件疑似重复，请人工核验",
                related_document_keys=ordered_keys,
                evidence_ids=[],
            )
        )

    by_name: dict[str, list[_UploadedAttachmentCandidate]] = {}
    by_content: dict[str, list[_UploadedAttachmentCandidate]] = {}
    for item in uploaded:
        by_name.setdefault(item.filename, []).append(item)
        by_content.setdefault(item.parsed_content_sha256, []).append(item)

    for filename, items in sorted(by_name.items()):
        contents = {item.parsed_content_sha256 for item in items}
        if len(items) >= 2 and len(contents) >= 2:
            append_issue([item.document_key for item in items], f"name:{filename}")

    for digest, items in sorted(by_content.items()):
        names = {item.filename for item in items}
        if len(items) >= 2 and len(names) >= 2:
            append_issue([item.document_key for item in items], f"content:{digest}")

    embedded_by_title_key: dict[str, list[_EmbeddedAttachmentCandidate]] = {}
    embedded_by_content: dict[str, list[_EmbeddedAttachmentCandidate]] = {}
    for item in embedded:
        embedded_by_title_key.setdefault(_normalize_title_compare_key(item.title), []).append(item)
        embedded_by_content.setdefault(item.body_content_sha256, []).append(item)

    for item in uploaded:
        normalized_name = _normalize_title_compare_key(item.filename)
        embedded_name_matches = embedded_by_title_key.get(normalized_name, [])
        if embedded_name_matches and all(
            match.body_content_sha256 != item.parsed_content_sha256
            for match in embedded_name_matches
        ):
            append_issue(
                [item.document_key, *[match.document_key for match in embedded_name_matches]],
                f"cross-name:{normalized_name}",
            )

        embedded_content_matches = embedded_by_content.get(item.parsed_content_sha256, [])
        if embedded_content_matches and all(
            _normalize_title_compare_key(match.title) != normalized_name
            for match in embedded_content_matches
        ):
            append_issue(
                [item.document_key, *[match.document_key for match in embedded_content_matches]],
                f"cross-content:{item.parsed_content_sha256}",
            )

    unique: dict[str, PreparationIssue] = {}
    for issue in issues:
        unique[issue.preparation_issue_key] = issue
    return [unique[key] for key in sorted(unique.keys())]


def build_document_inputs(request: PrepareRequest) -> PreparedDocuments:
    main = request.main_document
    main_markdown = main.markdown

    uploaded = _build_uploaded_candidates(request)
    embedded = _extract_embedded_attachments(main.document_id, main_markdown)

    _reject_definite_duplicates(uploaded, embedded)
    preparation_issues = _build_suspected_duplicate_issues(uploaded, embedded)

    main_snapshot = MainDocumentSnapshot(
        document_key="main",
        document_id=main.document_id,
        filename=normalize_snapshot_name(main.filename),
        parsed_content_sha256=parsed_content_sha256(main_markdown),
        source_file_sha256=main.source_file_sha256,
    )

    uploaded_snapshots = [
        UploadedAttachmentSnapshot(
            document_key=item.document_key,
            source_kind="UPLOADED",
            attachment_id=item.attachment_id,
            filename=item.filename,
            parsed_content_sha256=item.parsed_content_sha256,
            source_file_sha256=item.source_file_sha256,
        )
        for item in sorted(uploaded, key=lambda item: item.document_key)
    ]
    embedded_snapshots = [
        EmbeddedAttachmentSnapshot(
            document_key=item.document_key,
            source_kind="EMBEDDED",
            source_main_document_id=main.document_id,
            source_locator=item.source_locator,
            title=item.title,
            parsed_content_sha256=item.parsed_content_sha256,
        )
        for item in sorted(embedded, key=lambda item: item.document_key)
    ]

    source_snapshot = SourceSnapshot(
        contract_id=request.contract_id,
        revision_id=request.revision_id,
        document_set_hash="sha256:" + "0" * 64,
        main_document=main_snapshot,
        attachments=[*uploaded_snapshots, *embedded_snapshots],
        parser_meta=request.parser_meta,
    )

    source_snapshot = source_snapshot.model_copy(
        update={
            "document_set_hash": compute_document_set_hash(source_snapshot),
        }
    )

    markdown_by_document: dict[str, str] = {
        "main": main_markdown,
        **{item.document_key: item.markdown for item in uploaded},
        **{item.document_key: item.markdown for item in embedded},
    }

    return PreparedDocuments(
        source_snapshot=source_snapshot,
        markdown_by_document=markdown_by_document,
        preparation_issues=preparation_issues,
    )
