from __future__ import annotations

import unicodedata
from datetime import datetime
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator


SCHEMA_VERSION = "review-context/v1"

NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Sha256Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
IsoDate = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")]
DecimalString = Annotated[str, StringConstraints(pattern=r"^-?\d+(?:\.\d+)?$")]
MarkdownCharLocator = Annotated[str, StringConstraints(pattern=r"^markdown-chars:\d+-\d+$")]

DocumentKey = NonBlankStr
EvidenceId = NonBlankStr
FactIssueKey = NonBlankStr
PreparationIssueKey = NonBlankStr
PartyKey = NonBlankStr
DesignationKey = NonBlankStr
MentionKey = NonBlankStr
SignatureBlockKey = NonBlankStr
SignerSlotKey = NonBlankStr
SignerGroupKey = NonBlankStr
SignerKey = NonBlankStr
IdentityNumberKey = NonBlankStr
SignatureDateKey = NonBlankStr
SignatureFieldObservationKey = NonBlankStr
AmountKey = NonBlankStr
AmountRelationKey = NonBlankStr
PaymentMethodKey = NonBlankStr
PaymentStageKey = NonBlankStr
StatementKey = NonBlankStr
ScopeKey = NonBlankStr
AllocationKey = NonBlankStr
AttachmentDeclarationKey = NonBlankStr
LogicalAttachmentCandidateKey = NonBlankStr
AttachmentRelationKey = NonBlankStr

FactState = Literal["COMPLETE", "PARTIAL", "UNAVAILABLE"]
Presence = Literal["ABSENT", "PRESENT_EMPTY", "PRESENT_VALUE", "UNCERTAIN"]
NormalizationState = Literal["NOT_APPLICABLE", "VALID", "INVALID", "UNCERTAIN"]


TObserved = TypeVar("TObserved", bound="ObservedValue[Any]")
TDomain = TypeVar("TDomain")


def normalize_markdown(markdown: str) -> str:
    """Normalize markdown before hashing and schema validation."""
    if markdown.startswith("\ufeff"):
        markdown = markdown[1:]
    normalized = unicodedata.normalize("NFC", markdown)
    return normalized.replace("\r\n", "\n").replace("\r", "\n")


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _ensure_unique_keys(items: list[Any], key_attr: str, owner: str) -> None:
    seen: set[str] = set()
    for item in items:
        value = getattr(item, key_attr)
        if value in seen:
            raise ValueError(f"{owner} 中 {key_attr} 必须唯一: {value}")
        seen.add(value)


class ParserMeta(_StrictModel):
    parser_name: NonBlankStr | None = None
    parser_version: NonBlankStr | None = None
    parsed_at: datetime | None = None

    @model_validator(mode="after")
    def require_at_least_one_value(self) -> "ParserMeta":
        if self.parser_name is None and self.parser_version is None and self.parsed_at is None:
            raise ValueError("parser_meta 至少包含一个字段")
        return self


class PrepareMainDocumentInput(_StrictModel):
    document_id: NonBlankStr
    filename: NonBlankStr
    markdown: str
    source_file_sha256: Sha256Digest | None = None

    @field_validator("markdown")
    @classmethod
    def normalize_and_require_nonblank_markdown(cls, value: str) -> str:
        normalized = normalize_markdown(value)
        if not normalized.strip():
            raise ValueError("main_document.markdown 规范化后不能为空")
        return normalized


class PrepareUploadedAttachmentInput(_StrictModel):
    attachment_id: NonBlankStr
    filename: NonBlankStr
    markdown: str
    source_file_sha256: Sha256Digest | None = None

    @field_validator("markdown")
    @classmethod
    def normalize_and_require_nonblank_markdown(cls, value: str) -> str:
        normalized = normalize_markdown(value)
        if not normalized.strip():
            raise ValueError("uploaded_attachments.markdown 规范化后不能为空")
        return normalized


class PrepareRequest(_StrictModel):
    contract_id: NonBlankStr
    revision_id: NonBlankStr
    main_document: PrepareMainDocumentInput
    uploaded_attachments: list[PrepareUploadedAttachmentInput]
    parser_meta: ParserMeta | None = None


class MainDocumentSnapshot(_StrictModel):
    document_key: Literal["main"] = "main"
    document_id: NonBlankStr
    filename: NonBlankStr
    parsed_content_sha256: Sha256Digest
    source_file_sha256: Sha256Digest | None = None


class UploadedAttachmentSnapshot(_StrictModel):
    document_key: DocumentKey
    source_kind: Literal["UPLOADED"]
    attachment_id: NonBlankStr
    filename: NonBlankStr
    parsed_content_sha256: Sha256Digest
    source_file_sha256: Sha256Digest | None = None


class EmbeddedAttachmentSnapshot(_StrictModel):
    document_key: DocumentKey
    source_kind: Literal["EMBEDDED"]
    source_main_document_id: NonBlankStr
    source_locator: MarkdownCharLocator
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
    def validate_document_keys(self) -> "SourceSnapshot":
        keys = [self.main_document.document_key, *(item.document_key for item in self.attachments)]
        if len(keys) != len(set(keys)):
            raise ValueError("source_snapshot.document_key 必须全局唯一")
        for item in self.attachments:
            if item.document_key == "main":
                raise ValueError("附件 document_key 不能为 main")
            if isinstance(item, EmbeddedAttachmentSnapshot):
                if item.source_main_document_id != self.main_document.document_id:
                    raise ValueError("内嵌附件 source_main_document_id 必须指向 main_document")
        return self


class ObservedValue(_StrictModel, Generic[TDomain]):
    raw_text: str
    normalized_value: TDomain | None = None
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class NameObservation(ObservedValue[str]):
    specificity: Literal["SPECIFIC", "GENERIC", "UNCERTAIN"]


class SigningLocationObservation(ObservedValue[str]):
    city_candidates: list[NonBlankStr] = Field(default_factory=list)


class ObservedField(_StrictModel, Generic[TObserved]):
    presence: Presence
    normalization_state: NormalizationState
    observations: list[TObserved] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_presence_and_observations(self) -> "ObservedField[TObserved]":
        if self.presence == "ABSENT":
            if self.normalization_state != "NOT_APPLICABLE":
                raise ValueError("ABSENT 字段必须使用 NOT_APPLICABLE")
            if self.observations:
                raise ValueError("ABSENT 字段 observations 必须为空")
            return self

        if self.presence == "PRESENT_EMPTY":
            if self.normalization_state != "NOT_APPLICABLE":
                raise ValueError("PRESENT_EMPTY 字段必须使用 NOT_APPLICABLE")
            if not self.observations:
                raise ValueError("PRESENT_EMPTY 字段必须保留空栏位 observation")
            if any(item.raw_text != "" for item in self.observations):
                raise ValueError("PRESENT_EMPTY 字段 observation.raw_text 必须为空字符串")
            return self

        if self.normalization_state == "NOT_APPLICABLE":
            raise ValueError("存在实质字段值或候选时不能使用 NOT_APPLICABLE")

        if self.presence == "PRESENT_VALUE":
            if not self.observations:
                raise ValueError("PRESENT_VALUE 字段必须至少保留一个 observation")
            if all(item.raw_text.strip() == "" for item in self.observations):
                raise ValueError("PRESENT_VALUE 字段 observation 不能为空白")
            return self

        if self.presence == "UNCERTAIN":
            if not self.observations:
                raise ValueError("UNCERTAIN 字段必须保留候选 observations")
            return self

        return self


class DocumentCoverage(_StrictModel):
    document_key: DocumentKey
    state: FactState
    affected_fact_kinds: list[NonBlankStr] = Field(default_factory=list)
    fact_issue_keys: list[FactIssueKey] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_state_constraints(self) -> "DocumentCoverage":
        if self.state == "COMPLETE":
            if self.fact_issue_keys:
                raise ValueError("COMPLETE coverage 不能引用 fact_issue_keys")
            return self
        if not self.fact_issue_keys:
            raise ValueError("PARTIAL/UNAVAILABLE coverage 必须包含 fact_issue_keys")
        if not self.affected_fact_kinds:
            raise ValueError("PARTIAL/UNAVAILABLE coverage 必须包含 affected_fact_kinds")
        return self


class FactIssue(_StrictModel):
    fact_issue_key: FactIssueKey
    code: NonBlankStr
    message: NonBlankStr
    related_document_keys: list[DocumentKey] = Field(min_length=1)
    affected_fact_kinds: list[NonBlankStr] = Field(min_length=1)
    evidence_ids: list[EvidenceId] = Field(default_factory=list)


class PreparationIssue(_StrictModel):
    preparation_issue_key: PreparationIssueKey
    code: NonBlankStr
    message: NonBlankStr
    related_document_keys: list[DocumentKey] = Field(min_length=1)
    evidence_ids: list[EvidenceId] = Field(default_factory=list)


class IdentityGroup(_StrictModel):
    name: ObservedField[NameObservation]
    number: ObservedField[ObservedValue[str]]


class HeaderFacts(_StrictModel):
    contract_identity: IdentityGroup
    project_identity: IdentityGroup
    signing_location: ObservedField[SigningLocationObservation]
    signing_date: ObservedField[ObservedValue[IsoDate]]


class DeclaredDesignation(_StrictModel):
    designation_key: DesignationKey
    kind: Literal["CONTRACT_ROLE", "NAME_ALIAS", "UNCERTAIN"]
    text: NonBlankStr
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class CanonicalParty(_StrictModel):
    party_key: PartyKey
    declared_name: ObservedField[ObservedValue[str]]
    declared_designations: list[DeclaredDesignation] = Field(default_factory=list)
    definition_evidence_ids: list[EvidenceId] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_designation_keys(self) -> "CanonicalParty":
        _ensure_unique_keys(self.declared_designations, "designation_key", "canonical_party")
        return self


class PartyMention(_StrictModel):
    mention_key: MentionKey
    document_key: DocumentKey
    mention_kind: Literal["PARTY_DEFINITION", "PARTY_APPELLATION", "ROLE_REFERENCE"]
    observed_text: NonBlankStr
    referenced_designation_keys: list[DesignationKey] = Field(default_factory=list)
    explicit_entity_name: ObservedField[ObservedValue[str]] | None = None
    candidate_party_keys: list[PartyKey] = Field(default_factory=list)
    local_definition_state: Literal["PRESENT", "ABSENT", "UNCERTAIN", "NOT_APPLICABLE"]
    comparison_state: Literal[
        "MATCHED_DECLARATION",
        "OUTSIDE_DECLARED_SET",
        "UNCERTAIN",
        "NOT_APPLICABLE",
    ]
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class PartiesFacts(_StrictModel):
    canonical_parties: list[CanonicalParty] = Field(default_factory=list)
    party_mentions: list[PartyMention] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_relationships(self) -> "PartiesFacts":
        _ensure_unique_keys(self.canonical_parties, "party_key", "parties")
        _ensure_unique_keys(self.party_mentions, "mention_key", "parties")

        # designation_key 必须在整个 ReviewContext 内全局唯一（跨 canonical_party）
        designation_keys: set[str] = set()
        for party in self.canonical_parties:
            for designation in party.declared_designations:
                if designation.designation_key in designation_keys:
                    raise ValueError(
                        "designation_key 在 parties 域内重复（跨 canonical_party）: "
                        f"{designation.designation_key}"
                    )
                designation_keys.add(designation.designation_key)

        party_keys = {party.party_key for party in self.canonical_parties}

        for mention in self.party_mentions:
            for key in mention.referenced_designation_keys:
                if key not in designation_keys:
                    raise ValueError(f"party_mention 引用了不存在的 designation_key: {key}")
            for key in mention.candidate_party_keys:
                if key not in party_keys:
                    raise ValueError(f"party_mention 引用了不存在的 party_key: {key}")

        return self


class SignatureBlock(_StrictModel):
    signature_block_key: SignatureBlockKey
    document_key: DocumentKey
    party_binding_state: Literal["BOUND", "UNBOUND", "UNCERTAIN"]
    party_key: PartyKey | None = None
    candidate_party_keys: list[PartyKey] = Field(default_factory=list)
    local_company_name: ObservedField[ObservedValue[str]]
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class SignerSlot(_StrictModel):
    signer_slot_key: SignerSlotKey
    signature_block_key: SignatureBlockKey
    role_text: NonBlankStr
    role_state: Literal["ELIGIBLE_SIGNER", "IRRELEVANT_PERSON", "UNCERTAIN"]
    presence: Presence
    signer_keys: list[SignerKey] = Field(default_factory=list)
    identity_number_keys: list[IdentityNumberKey] = Field(default_factory=list)
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class AlternativeSignerGroup(_StrictModel):
    signer_group_key: SignerGroupKey
    signer_slot_keys: list[SignerSlotKey] = Field(min_length=1)
    relation_state: Literal["CONFIRMED", "UNCERTAIN"]
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class SignerCandidate(_StrictModel):
    signer_key: SignerKey
    signer_slot_key: SignerSlotKey
    raw_name: NonBlankStr
    normalized_name: NonBlankStr | None = None
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class IdentityNumberCandidate(_StrictModel):
    identity_number_key: IdentityNumberKey
    signer_slot_key: SignerSlotKey | None = None
    raw_text: NonBlankStr
    normalized_value: NonBlankStr | None = None
    normalization_state: Literal["VALID", "INVALID", "UNCERTAIN"]
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class PersonIdRelation(_StrictModel):
    signer_key: SignerKey
    identity_number_key: IdentityNumberKey
    association_state: Literal["DIRECT", "UNIQUE_IN_BLOCK", "UNCERTAIN"]
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class SignatureDateObservation(_StrictModel):
    signature_date_key: SignatureDateKey
    signature_block_key: SignatureBlockKey
    party_key: PartyKey | None = None
    field: ObservedField[ObservedValue[IsoDate]]


class SignatureFieldObservation(_StrictModel):
    field_observation_key: SignatureFieldObservationKey
    document_key: DocumentKey
    signature_block_key: SignatureBlockKey | None = None
    party_binding_state: Literal["BOUND", "UNBOUND", "UNCERTAIN"]
    party_key: PartyKey | None = None
    candidate_party_keys: list[PartyKey] = Field(default_factory=list)
    field_kind: Literal[
        "BANK_NAME",
        "BANK_ACCOUNT",
        "ACCOUNT_HOLDER",
        "ADDRESS",
        "PHONE",
        "FAX",
        "WEBSITE",
        "POSTAL_CODE",
    ]
    purpose_state: Literal["CONFIRMED", "UNCERTAIN", "NOT_APPLICABLE"]
    purpose_text: NonBlankStr | None = None
    field: ObservedField[ObservedValue[str]]


class SignatureFacts(_StrictModel):
    signature_blocks: list[SignatureBlock] = Field(default_factory=list)
    signer_slots: list[SignerSlot] = Field(default_factory=list)
    alternative_signer_groups: list[AlternativeSignerGroup] = Field(default_factory=list)
    signer_candidates: list[SignerCandidate] = Field(default_factory=list)
    identity_number_candidates: list[IdentityNumberCandidate] = Field(default_factory=list)
    person_id_relations: list[PersonIdRelation] = Field(default_factory=list)
    signing_date_observations: list[SignatureDateObservation] = Field(default_factory=list)
    account_observations: list[SignatureFieldObservation] = Field(default_factory=list)
    contact_observations: list[SignatureFieldObservation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> "SignatureFacts":
        _ensure_unique_keys(self.signature_blocks, "signature_block_key", "signature")
        _ensure_unique_keys(self.signer_slots, "signer_slot_key", "signature")
        _ensure_unique_keys(self.alternative_signer_groups, "signer_group_key", "signature")
        _ensure_unique_keys(self.signer_candidates, "signer_key", "signature")
        _ensure_unique_keys(self.identity_number_candidates, "identity_number_key", "signature")
        _ensure_unique_keys(self.signing_date_observations, "signature_date_key", "signature")
        _ensure_unique_keys(self.account_observations, "field_observation_key", "signature")
        _ensure_unique_keys(self.contact_observations, "field_observation_key", "signature")

        signature_block_keys = {item.signature_block_key for item in self.signature_blocks}
        signer_slot_keys = {item.signer_slot_key for item in self.signer_slots}
        signer_keys = {item.signer_key for item in self.signer_candidates}
        identity_number_keys = {item.identity_number_key for item in self.identity_number_candidates}

        # signer / identity_number 归属映射：用于校验 slot ownership（cross-slot 引用必须拒绝）
        signer_owner = {item.signer_key: item.signer_slot_key for item in self.signer_candidates}
        identity_number_owner = {
            item.identity_number_key: item.signer_slot_key
            for item in self.identity_number_candidates
        }

        for slot in self.signer_slots:
            if slot.signature_block_key not in signature_block_keys:
                raise ValueError(f"signer_slot 引用了不存在的 signature_block_key: {slot.signature_block_key}")
            for key in slot.signer_keys:
                if key not in signer_keys:
                    raise ValueError(f"signer_slot 引用了不存在的 signer_key: {key}")
                if signer_owner[key] != slot.signer_slot_key:
                    raise ValueError(
                        f"signer_slot 引用了不属于本 slot 的 signer_key（cross-slot）: {key}"
                    )
            for key in slot.identity_number_keys:
                if key not in identity_number_keys:
                    raise ValueError(
                        f"signer_slot 引用了不存在的 identity_number_key: {key}"
                    )
                if identity_number_owner[key] != slot.signer_slot_key:
                    raise ValueError(
                        "signer_slot 引用了不属于本 slot 的 identity_number_key"
                        f"（cross-slot）: {key}"
                    )

        for group in self.alternative_signer_groups:
            for key in group.signer_slot_keys:
                if key not in signer_slot_keys:
                    raise ValueError(f"alternative_signer_group 引用了不存在的 signer_slot_key: {key}")

        for signer in self.signer_candidates:
            if signer.signer_slot_key not in signer_slot_keys:
                raise ValueError(f"signer_candidate 引用了不存在的 signer_slot_key: {signer.signer_slot_key}")

        for identity_number in self.identity_number_candidates:
            if identity_number.signer_slot_key is not None and identity_number.signer_slot_key not in signer_slot_keys:
                raise ValueError(
                    f"identity_number_candidate 引用了不存在的 signer_slot_key: {identity_number.signer_slot_key}"
                )

        for relation in self.person_id_relations:
            if relation.signer_key not in signer_keys:
                raise ValueError(f"person_id_relation 引用了不存在的 signer_key: {relation.signer_key}")
            if relation.identity_number_key not in identity_number_keys:
                raise ValueError(
                    "person_id_relation 引用了不存在的 identity_number_key: "
                    f"{relation.identity_number_key}"
                )
            signer_owner_key = signer_owner[relation.signer_key]
            identity_number_owner_key = identity_number_owner[relation.identity_number_key]
            if (
                signer_owner_key is not None
                and identity_number_owner_key is not None
                and signer_owner_key != identity_number_owner_key
            ):
                raise ValueError(
                    "person_id_relation 关联了不同 owner slot 的 signer 与"
                    f" identity_number（cross-slot）: {relation.signer_key} / "
                    f"{relation.identity_number_key}"
                )

        for observation in self.signing_date_observations:
            if observation.signature_block_key not in signature_block_keys:
                raise ValueError(
                    "signing_date_observation 引用了不存在的 signature_block_key: "
                    f"{observation.signature_block_key}"
                )

        for field_observation in [*self.account_observations, *self.contact_observations]:
            if (
                field_observation.signature_block_key is not None
                and field_observation.signature_block_key not in signature_block_keys
            ):
                raise ValueError(
                    "signature_field_observation 引用了不存在的 signature_block_key: "
                    f"{field_observation.signature_block_key}"
                )

        return self


class AmountFact(_StrictModel):
    amount_key: AmountKey
    document_key: Literal["main"]
    semantic_role: ObservedField[ObservedValue[str]]
    numeric_amount: ObservedField[ObservedValue[DecimalString]]
    uppercase_amount: ObservedField[ObservedValue[str]]
    currency: ObservedField[ObservedValue[str]]
    tax_treatment: ObservedField[ObservedValue[str]]
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class AmountRelation(_StrictModel):
    amount_relation_key: AmountRelationKey
    amount_key: AmountKey
    relation_kind: Literal["CONTRACT_OVERALL", "PRICING_COMPONENT", "PAYMENT_STAGE"]
    relation_state: Literal["CONFIRMED", "UNCERTAIN"]
    payment_stage_key: PaymentStageKey | None = None
    evidence_ids: list[EvidenceId] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_stage_relation(self) -> "AmountRelation":
        if self.relation_kind == "PAYMENT_STAGE" and self.payment_stage_key is None:
            raise ValueError("PAYMENT_STAGE relation 必须包含 payment_stage_key")
        if self.relation_kind != "PAYMENT_STAGE" and self.payment_stage_key is not None:
            raise ValueError("非 PAYMENT_STAGE relation 不能包含 payment_stage_key")
        return self


class PaymentMethodObservation(_StrictModel):
    payment_method_key: PaymentMethodKey
    raw_text: NonBlankStr
    normalized_value: NonBlankStr | None = None
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class PaymentStage(_StrictModel):
    payment_stage_key: PaymentStageKey
    name: ObservedField[ObservedValue[str]]
    sequence: ObservedField[ObservedValue[int]]
    ratio_percent: ObservedField[ObservedValue[DecimalString]]
    amount_keys: list[AmountKey] = Field(default_factory=list)
    trigger_condition: ObservedField[ObservedValue[str]]
    payment_term: ObservedField[ObservedValue[str]]
    payment_method_keys: list[PaymentMethodKey] = Field(default_factory=list)
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class AmountPaymentFacts(_StrictModel):
    amounts: list[AmountFact] = Field(default_factory=list)
    amount_relations: list[AmountRelation] = Field(default_factory=list)
    payment_methods: list[PaymentMethodObservation] = Field(default_factory=list)
    payment_stages: list[PaymentStage] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> "AmountPaymentFacts":
        _ensure_unique_keys(self.amounts, "amount_key", "amount_payment")
        _ensure_unique_keys(self.amount_relations, "amount_relation_key", "amount_payment")
        _ensure_unique_keys(self.payment_methods, "payment_method_key", "amount_payment")
        _ensure_unique_keys(self.payment_stages, "payment_stage_key", "amount_payment")

        amount_keys = {item.amount_key for item in self.amounts}
        payment_method_keys = {item.payment_method_key for item in self.payment_methods}
        payment_stage_keys = {item.payment_stage_key for item in self.payment_stages}

        for relation in self.amount_relations:
            if relation.amount_key not in amount_keys:
                raise ValueError(f"amount_relation 引用了不存在的 amount_key: {relation.amount_key}")
            if relation.payment_stage_key is not None and relation.payment_stage_key not in payment_stage_keys:
                raise ValueError(
                    "amount_relation 引用了不存在的 payment_stage_key: "
                    f"{relation.payment_stage_key}"
                )

        for stage in self.payment_stages:
            for amount_key in stage.amount_keys:
                if amount_key not in amount_keys:
                    raise ValueError(f"payment_stage 引用了不存在的 amount_key: {amount_key}")
            for method_key in stage.payment_method_keys:
                if method_key not in payment_method_keys:
                    raise ValueError(f"payment_stage 引用了不存在的 payment_method_key: {method_key}")

        return self


class CopyStatement(_StrictModel):
    statement_key: StatementKey
    scope_key: ScopeKey
    document_key: Literal["main"]
    raw_text: NonBlankStr
    count: ObservedField[ObservedValue[int]]
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class CopyAllocation(_StrictModel):
    allocation_key: AllocationKey
    statement_key: StatementKey
    candidate_party_keys: list[PartyKey] = Field(default_factory=list)
    allocation_semantics: Literal["EACH", "COLLECTIVE", "UNCERTAIN"]
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class CopyTermsFacts(_StrictModel):
    statements: list[CopyStatement] = Field(default_factory=list)
    overall_total_statement_key: StatementKey | None = None
    allocations: list[CopyAllocation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> "CopyTermsFacts":
        _ensure_unique_keys(self.statements, "statement_key", "copy_terms")
        _ensure_unique_keys(self.allocations, "allocation_key", "copy_terms")

        statement_keys = {item.statement_key for item in self.statements}
        if self.overall_total_statement_key is not None and self.overall_total_statement_key not in statement_keys:
            raise ValueError(
                "overall_total_statement_key 必须引用已存在的 copy statement"
            )
        for allocation in self.allocations:
            if allocation.statement_key not in statement_keys:
                raise ValueError(f"copy_allocation 引用了不存在的 statement_key: {allocation.statement_key}")
        return self


class AttachmentDeclaration(_StrictModel):
    attachment_declaration_key: AttachmentDeclarationKey
    title: ObservedField[ObservedValue[str]]
    ordinal: ObservedField[ObservedValue[int]]
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class LogicalAttachmentCandidate(_StrictModel):
    logical_attachment_candidate_key: LogicalAttachmentCandidateKey
    parent_document_key: DocumentKey
    title: ObservedField[ObservedValue[str]]
    source_locator: MarkdownCharLocator
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class AttachmentRelation(_StrictModel):
    attachment_relation_key: AttachmentRelationKey
    attachment_declaration_key: AttachmentDeclarationKey
    candidate_document_keys: list[DocumentKey] = Field(min_length=1)
    relation_state: Literal["LINKED", "UNCERTAIN"]
    evidence_ids: list[EvidenceId] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_relation_state_cardinality(self) -> "AttachmentRelation":
        if self.relation_state == "LINKED" and len(self.candidate_document_keys) != 1:
            raise ValueError("LINKED relation 必须且只能关联一个 candidate_document_key")
        if self.relation_state == "UNCERTAIN" and len(self.candidate_document_keys) < 1:
            raise ValueError("UNCERTAIN relation 至少关联一个 candidate_document_key")
        return self


class AttachmentManifestFacts(_StrictModel):
    declared_total: ObservedField[ObservedValue[int]]
    declarations: list[AttachmentDeclaration] = Field(default_factory=list)
    logical_attachment_candidates: list[LogicalAttachmentCandidate] = Field(default_factory=list)
    links: list[AttachmentRelation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> "AttachmentManifestFacts":
        _ensure_unique_keys(self.declarations, "attachment_declaration_key", "attachment_manifest")
        _ensure_unique_keys(
            self.logical_attachment_candidates,
            "logical_attachment_candidate_key",
            "attachment_manifest",
        )
        _ensure_unique_keys(self.links, "attachment_relation_key", "attachment_manifest")

        declaration_keys = {item.attachment_declaration_key for item in self.declarations}
        for link in self.links:
            if link.attachment_declaration_key not in declaration_keys:
                raise ValueError(
                    "attachment_relation 引用了不存在的 attachment_declaration_key: "
                    f"{link.attachment_declaration_key}"
                )
        return self


class FactDomain(_StrictModel, Generic[TDomain]):
    state: FactState
    coverage: list[DocumentCoverage] = Field(min_length=1)
    data: TDomain
    issues: list[FactIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_consistency(self) -> "FactDomain[TDomain]":
        _ensure_unique_keys(self.coverage, "document_key", "fact_domain.coverage")
        _ensure_unique_keys(self.issues, "fact_issue_key", "fact_domain.issues")

        issue_keys = {item.fact_issue_key for item in self.issues}

        for coverage in self.coverage:
            if coverage.state == "COMPLETE":
                if coverage.fact_issue_keys:
                    raise ValueError("COMPLETE coverage 不得引用 fact_issue_keys")
            else:
                if not coverage.fact_issue_keys:
                    raise ValueError("PARTIAL/UNAVAILABLE coverage 必须引用 fact_issue_keys")
                for issue_key in coverage.fact_issue_keys:
                    if issue_key not in issue_keys:
                        raise ValueError(f"coverage 引用了不存在的 fact_issue_key: {issue_key}")

        coverage_states = {item.state for item in self.coverage}
        expected_state: FactState
        if coverage_states == {"COMPLETE"}:
            expected_state = "COMPLETE"
        elif coverage_states == {"UNAVAILABLE"}:
            expected_state = "UNAVAILABLE"
        else:
            expected_state = "PARTIAL"

        if self.state != expected_state:
            raise ValueError(f"FactDomain.state 与 coverage 聚合不一致，应为 {expected_state}")

        if self.state == "COMPLETE" and self.issues:
            raise ValueError("COMPLETE 域不能包含 fact issues")
        if self.state != "COMPLETE" and not self.issues:
            raise ValueError("PARTIAL/UNAVAILABLE 域必须包含 fact issues")

        return self


class SharedFacts(_StrictModel):
    header: FactDomain[HeaderFacts]
    parties: FactDomain[PartiesFacts]
    signature: FactDomain[SignatureFacts]
    amount_payment: FactDomain[AmountPaymentFacts]
    copy_terms: FactDomain[CopyTermsFacts]
    attachment_manifest: FactDomain[AttachmentManifestFacts]


class EvidenceItem(_StrictModel):
    evidence_id: EvidenceId
    document_key: DocumentKey
    source_locator: MarkdownCharLocator
    quote: Annotated[str, StringConstraints(min_length=1)]


class EvidenceIndex(_StrictModel):
    items: list[EvidenceItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_uniqueness(self) -> "EvidenceIndex":
        _ensure_unique_keys(self.items, "evidence_id", "evidence_index")
        return self


class PreparationMeta(_StrictModel):
    pipeline_version: NonBlankStr
    prompt_bundle_hash: Sha256Digest
    model_deployment: NonBlankStr
    created_at: datetime


def _collect_evidence_ids(value: Any) -> set[str]:
    collected: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "evidence_ids" and isinstance(item, list):
                collected.update(str(evidence_id) for evidence_id in item)
            else:
                collected.update(_collect_evidence_ids(item))
    elif isinstance(value, list):
        for item in value:
            collected.update(_collect_evidence_ids(item))
    return collected


class ReviewContext(_StrictModel):
    schema_version: Literal[SCHEMA_VERSION]
    source_snapshot: SourceSnapshot
    shared_facts: SharedFacts
    evidence_index: EvidenceIndex
    preparation_issues: list[PreparationIssue] = Field(default_factory=list)
    preparation_meta: PreparationMeta
    context_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_references(self) -> "ReviewContext":
        _ensure_unique_keys(self.preparation_issues, "preparation_issue_key", "preparation_issues")

        document_keys = {
            self.source_snapshot.main_document.document_key,
            *(item.document_key for item in self.source_snapshot.attachments),
        }

        evidence_ids = {item.evidence_id for item in self.evidence_index.items}
        for evidence in self.evidence_index.items:
            if evidence.document_key not in document_keys:
                raise ValueError(
                    "evidence_index 出现未知 document_key: "
                    f"{evidence.document_key}"
                )

        canonical_party_keys = {
            party.party_key
            for party in self.shared_facts.parties.data.canonical_parties
        }

        for mention in self.shared_facts.parties.data.party_mentions:
            if mention.document_key not in document_keys:
                raise ValueError(
                    "party_mention 引用了未知 document_key: "
                    f"{mention.document_key}"
                )

        for issue in self.preparation_issues:
            for document_key in issue.related_document_keys:
                if document_key not in document_keys:
                    raise ValueError(
                        "preparation_issue 引用了未知 document_key: "
                        f"{document_key}"
                    )
            for evidence_id in issue.evidence_ids:
                if evidence_id not in evidence_ids:
                    raise ValueError(
                        "preparation_issue 引用了未知 evidence_id: "
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
            domain: FactDomain[Any] = getattr(self.shared_facts, domain_name)
            for issue in domain.issues:
                for document_key in issue.related_document_keys:
                    if document_key not in document_keys:
                        raise ValueError(
                            f"{domain_name}.issues 引用了未知 document_key: {document_key}"
                        )
                for evidence_id in issue.evidence_ids:
                    if evidence_id not in evidence_ids:
                        raise ValueError(
                            f"{domain_name}.issues 引用了未知 evidence_id: {evidence_id}"
                        )

        signature = self.shared_facts.signature.data
        for signature_block in signature.signature_blocks:
            if signature_block.document_key not in document_keys:
                raise ValueError(
                    "signature_block 引用了未知 document_key: "
                    f"{signature_block.document_key}"
                )
            if signature_block.party_key is not None and signature_block.party_key not in canonical_party_keys:
                raise ValueError(
                    "signature_block 引用了未知 party_key: "
                    f"{signature_block.party_key}"
                )
            for party_key in signature_block.candidate_party_keys:
                if party_key not in canonical_party_keys:
                    raise ValueError(
                        "signature_block 引用了未知 candidate_party_key: "
                        f"{party_key}"
                    )

        for signing_date in signature.signing_date_observations:
            if signing_date.party_key is not None and signing_date.party_key not in canonical_party_keys:
                raise ValueError(
                    "signing_date_observation 引用了未知 party_key: "
                    f"{signing_date.party_key}"
                )

        for field_observation in [*signature.account_observations, *signature.contact_observations]:
            if field_observation.document_key not in document_keys:
                raise ValueError(
                    "signature_field_observation 引用了未知 document_key: "
                    f"{field_observation.document_key}"
                )
            if field_observation.party_key is not None and field_observation.party_key not in canonical_party_keys:
                raise ValueError(
                    "signature_field_observation 引用了未知 party_key: "
                    f"{field_observation.party_key}"
                )
            for party_key in field_observation.candidate_party_keys:
                if party_key not in canonical_party_keys:
                    raise ValueError(
                        "signature_field_observation 引用了未知 candidate_party_key: "
                        f"{party_key}"
                    )

        copy_terms = self.shared_facts.copy_terms.data
        for allocation in copy_terms.allocations:
            for party_key in allocation.candidate_party_keys:
                if party_key not in canonical_party_keys:
                    raise ValueError(
                        "copy_allocation 引用了未知 candidate_party_key: "
                        f"{party_key}"
                    )

        attachment_manifest = self.shared_facts.attachment_manifest.data
        for logical_candidate in attachment_manifest.logical_attachment_candidates:
            if logical_candidate.parent_document_key == "main":
                raise ValueError(
                    "logical_attachment_candidate 的 parent_document_key 不能是 main"
                    "（必须是实际附件来源）: "
                    f"{logical_candidate.parent_document_key}"
                )
            if logical_candidate.parent_document_key not in document_keys:
                raise ValueError(
                    "logical_attachment_candidate 引用了未知 parent_document_key: "
                    f"{logical_candidate.parent_document_key}"
                )
        for link in attachment_manifest.links:
            for candidate_document_key in link.candidate_document_keys:
                if candidate_document_key == "main":
                    raise ValueError(
                        "attachment_relation 不能把 main 当作 candidate_document_key: "
                        f"{candidate_document_key}"
                    )
                if candidate_document_key not in document_keys:
                    raise ValueError(
                        "attachment_relation 引用了未知 candidate_document_key: "
                        f"{candidate_document_key}"
                    )

        for domain_name, expected_keys in {
            "header": {"main"},
            "amount_payment": {"main"},
            "copy_terms": {"main"},
            "parties": document_keys,
            "signature": document_keys,
            "attachment_manifest": document_keys,
        }.items():
            domain: FactDomain[Any] = getattr(self.shared_facts, domain_name)
            coverage_keys = {item.document_key for item in domain.coverage}
            if coverage_keys != expected_keys:
                raise ValueError(
                    f"{domain_name}.coverage 文档范围不符合契约，期望 {sorted(expected_keys)}"
                )

        referenced_evidence_ids = _collect_evidence_ids(self.shared_facts.model_dump(mode="json"))
        referenced_evidence_ids.update(
            evidence_id
            for issue in self.preparation_issues
            for evidence_id in issue.evidence_ids
        )
        for evidence_id in referenced_evidence_ids:
            if evidence_id not in evidence_ids:
                raise ValueError(f"存在悬空 evidence_id 引用: {evidence_id}")

        return self

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)
