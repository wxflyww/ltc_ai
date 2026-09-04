import pytest
from unittest import mock

from app.capabilities.contract_review.two_stage.documents import (
    PreparedDocuments,
    PrepareDuplicateError,
    build_document_inputs,
)
from app.capabilities.contract_review.two_stage.schemas import PrepareRequest
from tests.two_stage.factories import clone_payload, valid_prepare_request_payload


def _request_with_embedded_attachment() -> PrepareRequest:
    payload = valid_prepare_request_payload()
    payload["main_document"]["markdown"] = (
        "# 主合同\n\n"
        "正文第一段。\n\n"
        "## 附件一：技术规范书\n"
        "技术规范正文第一行。\n"
        "技术规范正文第二行。\n\n"
        "正文结束段。"
    )
    payload["uploaded_attachments"] = [
        {
            "attachment_id": "ATT-UP-001",
            "filename": "uploaded-tech.md",
            "markdown": "上传附件正文",
        }
    ]
    return PrepareRequest.model_validate(payload)


def test_embedded_attachment_keeps_full_main_snapshot():
    prepared = build_document_inputs(_request_with_embedded_attachment())

    assert isinstance(prepared, PreparedDocuments)
    main_markdown = prepared.markdown_by_document["main"]
    assert "正文第一段" in main_markdown
    assert "正文结束段" in main_markdown

    embedded = [
        item
        for item in prepared.source_snapshot.attachments
        if item.source_kind == "EMBEDDED"
    ][0]
    embedded_markdown = prepared.markdown_by_document[embedded.document_key]
    locator = embedded.source_locator
    prefix = "markdown-chars:"
    start, end = locator[len(prefix):].split("-", maxsplit=1)
    assert main_markdown[int(start):int(end)] == embedded_markdown


def test_heading_without_content_does_not_create_embedded_source():
    payload = valid_prepare_request_payload()
    payload["main_document"]["markdown"] = "# 主合同\n\n## 附件一：技术规范书\n\n"
    payload["uploaded_attachments"] = []

    prepared = build_document_inputs(PrepareRequest.model_validate(payload))

    assert prepared.source_snapshot.attachments == []


def test_duplicate_attachment_id_is_rejected_before_model_calls():
    payload = valid_prepare_request_payload()
    payload["uploaded_attachments"] = [
        {
            "attachment_id": "ATT-DUP",
            "filename": "A.md",
            "markdown": "A",
        },
        {
            "attachment_id": "ATT-DUP",
            "filename": "B.md",
            "markdown": "B",
        },
    ]

    with pytest.raises(PrepareDuplicateError, match="attachment_id"):
        build_document_inputs(PrepareRequest.model_validate(payload))


def test_duplicate_uploaded_name_plus_content_is_rejected():
    payload = valid_prepare_request_payload()
    payload["uploaded_attachments"] = [
        {
            "attachment_id": "ATT-001",
            "filename": "技术协议.md",
            "markdown": "同一内容",
        },
        {
            "attachment_id": "ATT-002",
            "filename": "技术协议.md",
            "markdown": "同一内容",
        },
    ]

    with pytest.raises(PrepareDuplicateError, match="文件名"):
        build_document_inputs(PrepareRequest.model_validate(payload))


def test_duplicate_embedded_title_plus_content_against_uploaded_is_rejected():
    payload = valid_prepare_request_payload()
    payload["main_document"]["markdown"] = (
        "# 主合同\n\n"
        "## 附件一：技术协议\n"
        "同一内容\n"
    )
    payload["uploaded_attachments"] = [
        {
            "attachment_id": "ATT-001",
            "filename": "上传技术协议.md",
            "markdown": "同一内容",
        }
    ]

    with pytest.raises(PrepareDuplicateError, match="标题"):
        build_document_inputs(PrepareRequest.model_validate(payload))


def test_suspected_duplicate_same_name_only_keeps_sources_and_creates_issue():
    payload = valid_prepare_request_payload()
    payload["uploaded_attachments"] = [
        {
            "attachment_id": "ATT-001",
            "filename": "同名附件.md",
            "markdown": "内容A",
        },
        {
            "attachment_id": "ATT-002",
            "filename": "同名附件.md",
            "markdown": "内容B",
        },
    ]

    prepared = build_document_inputs(PrepareRequest.model_validate(payload))

    assert len(prepared.source_snapshot.attachments) == 2
    assert len(prepared.preparation_issues) == 1
    issue = prepared.preparation_issues[0]
    assert issue.code == "SUSPECTED_DUPLICATE"
    assert len(issue.related_document_keys) == 2


def test_suspected_duplicate_content_only_stable_issue_key_regardless_of_order():
    payload_a = valid_prepare_request_payload()
    payload_a["uploaded_attachments"] = [
        {
            "attachment_id": "ATT-001",
            "filename": "A.md",
            "markdown": "同一内容",
        },
        {
            "attachment_id": "ATT-002",
            "filename": "B.md",
            "markdown": "同一内容",
        },
    ]
    payload_b = clone_payload(payload_a)
    payload_b["uploaded_attachments"] = list(reversed(payload_b["uploaded_attachments"]))

    first = build_document_inputs(PrepareRequest.model_validate(payload_a))
    second = build_document_inputs(PrepareRequest.model_validate(payload_b))

    assert first.preparation_issues[0].preparation_issue_key == second.preparation_issues[0].preparation_issue_key


def test_duplicate_embedded_title_plus_content_is_rejected():
    payload = valid_prepare_request_payload()
    payload["main_document"]["markdown"] = (
        "# 主合同\n\n"
        "## 附件一：技术协议\n"
        "同一内容\n"
        "## 附件二：技术协议\n"
        "同一内容\n"
    )
    payload["uploaded_attachments"] = []

    with pytest.raises(PrepareDuplicateError, match="标题"):
        build_document_inputs(PrepareRequest.model_validate(payload))


def test_suspected_duplicate_uploaded_embedded_name_only_keeps_sources():
    payload = valid_prepare_request_payload()
    payload["main_document"]["markdown"] = (
        "# 主合同\n\n"
        "## 附件一：技术协议\n"
        "内嵌技术协议内容。\n"
    )
    payload["uploaded_attachments"] = [
        {
            "attachment_id": "ATT-001",
            "filename": "上传技术协议.md",
            "markdown": "上传版本的不同内容。",
        }
    ]

    prepared = build_document_inputs(PrepareRequest.model_validate(payload))

    assert len(prepared.source_snapshot.attachments) == 2
    assert len(prepared.preparation_issues) == 1
    issue = prepared.preparation_issues[0]
    assert issue.code == "SUSPECTED_DUPLICATE"
    assert len(issue.related_document_keys) == 2


def test_suspected_duplicate_uploaded_embedded_content_only_keeps_sources():
    payload = valid_prepare_request_payload()
    payload["main_document"]["markdown"] = (
        "# 主合同\n\n"
        "## 附件一：服务清单\n"
        "完全相同的正文内容。\n"
    )
    payload["uploaded_attachments"] = [
        {
            "attachment_id": "ATT-001",
            "filename": "技术协议.md",
            "markdown": "完全相同的正文内容。",
        }
    ]

    prepared = build_document_inputs(PrepareRequest.model_validate(payload))

    assert len(prepared.source_snapshot.attachments) == 2
    assert len(prepared.preparation_issues) == 1
    issue = prepared.preparation_issues[0]
    assert issue.code == "SUSPECTED_DUPLICATE"
    assert len(issue.related_document_keys) == 2


def test_distinct_uploaded_embedded_creates_no_duplicate_issue():
    payload = valid_prepare_request_payload()
    payload["main_document"]["markdown"] = (
        "# 主合同\n\n"
        "## 附件二：服务清单\n"
        "服务清单正文内容。\n"
    )
    payload["uploaded_attachments"] = [
        {
            "attachment_id": "ATT-001",
            "filename": "技术协议.md",
            "markdown": "技术协议正文内容。",
        }
    ]

    prepared = build_document_inputs(PrepareRequest.model_validate(payload))

    assert len(prepared.source_snapshot.attachments) == 2
    assert prepared.preparation_issues == []


def _prepare_model_entry_sentinel():
    return mock.patch(
        "app.capabilities.contract_review.two_stage.prepare_model.invoke_typed_prepare_model",
        side_effect=AssertionError("Prepare 明确重复不得触发模型调用"),
    )


def test_duplicate_attachment_id_rejected_with_zero_model_calls():
    payload = valid_prepare_request_payload()
    payload["uploaded_attachments"] = [
        {"attachment_id": "ATT-DUP", "filename": "A.md", "markdown": "A"},
        {"attachment_id": "ATT-DUP", "filename": "B.md", "markdown": "B"},
    ]

    with _prepare_model_entry_sentinel() as entry:
        with pytest.raises(PrepareDuplicateError, match="attachment_id"):
            build_document_inputs(PrepareRequest.model_validate(payload))
        assert entry.call_count == 0


def test_duplicate_uploaded_name_plus_content_rejected_with_zero_model_calls():
    payload = valid_prepare_request_payload()
    payload["uploaded_attachments"] = [
        {"attachment_id": "ATT-001", "filename": "技术协议.md", "markdown": "同一内容"},
        {"attachment_id": "ATT-002", "filename": "技术协议.md", "markdown": "同一内容"},
    ]

    with _prepare_model_entry_sentinel() as entry:
        with pytest.raises(PrepareDuplicateError, match="文件名"):
            build_document_inputs(PrepareRequest.model_validate(payload))
        assert entry.call_count == 0


def test_duplicate_uploaded_embedded_name_plus_content_rejected_with_zero_model_calls():
    payload = valid_prepare_request_payload()
    payload["main_document"]["markdown"] = (
        "# 主合同\n\n"
        "## 附件一：技术协议\n"
        "同一内容\n"
    )
    payload["uploaded_attachments"] = [
        {"attachment_id": "ATT-001", "filename": "上传技术协议.md", "markdown": "同一内容"},
    ]

    with _prepare_model_entry_sentinel() as entry:
        with pytest.raises(PrepareDuplicateError, match="标题"):
            build_document_inputs(PrepareRequest.model_validate(payload))
        assert entry.call_count == 0


def test_duplicate_embedded_title_plus_content_rejected_with_zero_model_calls():
    payload = valid_prepare_request_payload()
    payload["main_document"]["markdown"] = (
        "# 主合同\n\n"
        "## 附件一：技术协议\n"
        "同一内容\n"
        "## 附件二：技术协议\n"
        "同一内容\n"
    )
    payload["uploaded_attachments"] = []

    with _prepare_model_entry_sentinel() as entry:
        with pytest.raises(PrepareDuplicateError, match="标题"):
            build_document_inputs(PrepareRequest.model_validate(payload))
        assert entry.call_count == 0
