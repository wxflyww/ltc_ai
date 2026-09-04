import pytest
from pydantic import ValidationError

from app.capabilities.contract_review.two_stage.schemas import PrepareRequest
from tests.two_stage.factories import clone_payload, valid_prepare_request_payload


def test_prepare_request_accepts_empty_uploaded_attachments_snapshot():
    payload = valid_prepare_request_payload()
    payload["uploaded_attachments"] = []

    model = PrepareRequest.model_validate(payload)

    assert model.contract_id == "C-2026-0001"
    assert model.uploaded_attachments == []


def test_prepare_request_requires_uploaded_attachments_field_present():
    payload = valid_prepare_request_payload()
    payload.pop("uploaded_attachments", None)

    with pytest.raises(ValidationError, match="uploaded_attachments"):
        PrepareRequest.model_validate(payload)


@pytest.mark.parametrize(
    "path,new_value,error_field",
    [
        (("contract_id",), "   ", "contract_id"),
        (("revision_id",), "", "revision_id"),
        (("main_document", "document_id"), "", "document_id"),
        (("main_document", "filename"), "", "filename"),
        (("main_document", "markdown"), "\ufeff  \r\n\t", "markdown"),
        (("uploaded_attachments", 0, "attachment_id"), "", "attachment_id"),
        (("uploaded_attachments", 0, "filename"), "", "filename"),
        (("uploaded_attachments", 0, "markdown"), "\n\r  ", "markdown"),
        (("main_document", "source_file_sha256"), "sha256:XYZ", "source_file_sha256"),
    ],
)
def test_prepare_request_rejects_blank_or_invalid_required_fields(path, new_value, error_field):
    payload = valid_prepare_request_payload()
    cursor = payload
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = new_value

    with pytest.raises(ValidationError, match=error_field):
        PrepareRequest.model_validate(payload)


@pytest.mark.parametrize("field", ["review_context_id", "previous_results", "manual_override", "signing_preset"])
def test_prepare_request_rejects_forbidden_business_fields(field: str):
    payload = valid_prepare_request_payload()
    payload[field] = "forbidden"

    with pytest.raises(ValidationError, match=field):
        PrepareRequest.model_validate(payload)


def test_prepare_request_rejects_unknown_nested_fields():
    payload = valid_prepare_request_payload()
    payload["main_document"]["unexpected"] = "x"

    with pytest.raises(ValidationError, match="unexpected"):
        PrepareRequest.model_validate(payload)


def test_prepare_request_accepts_missing_optional_metadata():
    payload = clone_payload(valid_prepare_request_payload())
    payload["parser_meta"] = None
    payload["main_document"].pop("source_file_sha256", None)
    payload["uploaded_attachments"][0].pop("source_file_sha256", None)

    model = PrepareRequest.model_validate(payload)

    assert model.parser_meta is None
    assert model.main_document.source_file_sha256 is None
