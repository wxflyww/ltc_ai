import math
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)


SCHEMA_VERSION = "review-context/v1"
FactState = Literal["COMPLETE", "PARTIAL", "UNAVAILABLE"]
Sha256Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _reject_non_finite_json(value: JsonValue) -> JsonValue:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JSON 数值不得为 NaN 或 Infinity")
    if isinstance(value, dict):
        for item in value.values():
            _reject_non_finite_json(item)
    elif isinstance(value, list):
        for item in value:
            _reject_non_finite_json(item)
    return value


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ParserMeta(_StrictModel):
    parser_name: NonBlankStr | None = None
    parser_version: NonBlankStr | None = None
    parsed_at: datetime | None = None

    @model_validator(mode="after")
    def require_at_least_one_value(self) -> "ParserMeta":
        if self.parser_name is None and self.parser_version is None and self.parsed_at is None:
            raise ValueError("parser_meta 至少包含一个字段")
        return self


class MainDocumentSnapshot(_StrictModel):
    document_key: Literal["main"] = "main"
    document_id: NonBlankStr
    filename: NonBlankStr
    parsed_content_sha256: Sha256Digest
    source_file_sha256: Sha256Digest | None = None


class UploadedAttachmentSnapshot(_StrictModel):
    document_key: NonBlankStr
    source_kind: Literal["UPLOADED"]
    attachment_id: NonBlankStr
    filename: NonBlankStr
    parsed_content_sha256: Sha256Digest
    source_file_sha256: Sha256Digest | None = None


class EmbeddedAttachmentSnapshot(_StrictModel):
    document_key: NonBlankStr
    source_kind: Literal["EMBEDDED"]
    source_main_document_id: NonBlankStr
    source_locator: NonBlankStr
    title: NonBlankStr
    parsed_content_sha256: Sha256Digest


AttachmentSnapshot = Annotated[
    UploadedAttachmentSnapshot | EmbeddedAttachmentSnapshot,
    Field(discriminator="source_kind"),
]


class SourceSnapshot(_StrictModel):
    contract_id: NonBlankStr
    revision_id: NonBlankStr
    document_set_hash: Sha256Digest
    main_document: MainDocumentSnapshot
    attachments: list[AttachmentSnapshot] = Field(default_factory=list)
    parser_meta: ParserMeta | None = None

    @model_validator(mode="after")
    def require_unique_document_keys(self) -> "SourceSnapshot":
        keys = [self.main_document.document_key, *(item.document_key for item in self.attachments)]
        if len(keys) != len(set(keys)):
            raise ValueError("source_snapshot 中的 document_key 必须唯一且附件不得使用 main")
        for item in self.attachments:
            if (
                isinstance(item, EmbeddedAttachmentSnapshot)
                and item.source_main_document_id != self.main_document.document_id
            ):
                raise ValueError(
                    "内嵌附件 source_main_document_id 必须指向当前 main_document"
                )
        return self


class FactDomain(_StrictModel):
    state: FactState
    data: dict[str, JsonValue] | list[JsonValue]
    issues: list[NonBlankStr] = Field(default_factory=list)

    @field_validator("data")
    @classmethod
    def require_finite_json_data(
        cls,
        value: dict[str, JsonValue] | list[JsonValue],
    ) -> dict[str, JsonValue] | list[JsonValue]:
        return _reject_non_finite_json(value)

    @model_validator(mode="after")
    def validate_state_issues(self) -> "FactDomain":
        if self.state == "COMPLETE" and self.issues:
            raise ValueError("COMPLETE 事实域不得包含 issues")
        if self.state != "COMPLETE" and not self.issues:
            raise ValueError(f"{self.state} 事实域必须包含 issues")
        return self


class SharedFacts(_StrictModel):
    header: FactDomain
    parties: FactDomain
    signature: FactDomain
    amount_payment: FactDomain
    attachment_manifest: FactDomain


class EvidenceRef(_StrictModel):
    document_key: NonBlankStr
    source_locator: NonBlankStr
    quote: str = Field(min_length=1)
    attributes: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("attributes")
    @classmethod
    def require_finite_json_attributes(
        cls,
        value: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        return _reject_non_finite_json(value)

    @field_validator("document_key", "source_locator", "quote")
    @classmethod
    def reject_blank_strings(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("证据来源和引文不得为空")
        return value


class EvidenceIndex(_StrictModel):
    party_mentions: list[EvidenceRef] = Field(default_factory=list)
    signature_mentions: list[EvidenceRef] = Field(default_factory=list)
    amount_mentions: list[EvidenceRef] = Field(default_factory=list)
    attachment_relations: list[EvidenceRef] = Field(default_factory=list)


class PreparationIssue(_StrictModel):
    code: NonBlankStr
    message: NonBlankStr
    document_key: NonBlankStr | None = None
    source_locator: NonBlankStr | None = None


class PreparationMeta(_StrictModel):
    pipeline_version: NonBlankStr
    prompt_bundle_hash: Sha256Digest
    model_deployment: NonBlankStr
    created_at: datetime


class ReviewContext(_StrictModel):
    schema_version: NonBlankStr
    source_snapshot: SourceSnapshot
    shared_facts: SharedFacts
    evidence_index: EvidenceIndex
    preparation_issues: list[PreparationIssue] = Field(default_factory=list)
    preparation_meta: PreparationMeta
    context_digest: Sha256Digest

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)
