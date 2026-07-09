from typing import Literal

from pydantic import BaseModel, Field


CheckResult = Literal["PASS", "WARN", "FAIL", "NA"]
BlockLevel = Literal["通过", "提示", "硬阻断", "不适用"]
OverallResult = Literal["PASS", "BLOCK"]


class AttachmentInput(BaseModel):
    index: int | None = None
    filename: str = Field(..., min_length=1)
    file_type: str | None = None
    text: str = ""


class ContractReviewRequest(BaseModel):
    contract_md: str = Field(..., min_length=1)
    attachments: list[AttachmentInput] = Field(default_factory=list)


class CheckItem(BaseModel):
    id: str
    name: str
    result: CheckResult
    block_level: BlockLevel
    reason: str | None = None


class ContractReviewData(BaseModel):
    overall_result: OverallResult
    check_time: str
    checks: list[CheckItem]


class ContractParty(BaseModel):
    role: str | None = None
    name: str | None = None


class HeaderInfo(BaseModel):
    contract_name: str | None = None
    project_name: str | None = None
    project_number: str | None = None
    contract_number: str | None = None
    signing_location: str | None = None
    signing_date: str | None = None
    parties: list[ContractParty] = Field(default_factory=list)


class SignatureInfo(BaseModel):
    signature_parties: list[ContractParty] = Field(default_factory=list)
    role: str | None = None
    name: str | None = None
    legal_rep_name: str | None = None
    signer_id_number: str | None = None
    signing_date: str | None = None
    bank_name: str | None = None
    bank_account: str | None = None
    account_holder: str | None = None
    address: str | None = None
    phone: str | None = None
    fax: str | None = None
    website: str | None = None
    postal_code: str | None = None


class AuthorizedRep(BaseModel):
    name: str = ""
    id_number: str = ""


class SystemPreset(BaseModel):
    entity_name: str = ""
    legal_rep_name: str = ""
    legal_rep_id_number: str = ""
    authorized_reps: list[AuthorizedRep] = Field(default_factory=list)
    bank_name: str = ""
    bank_account: str = ""
    account_holder: str = ""
    address: str = ""
    phone: str = ""
    fax: str = ""
    website: str = ""
    postal_code: str = ""


class OurPartyContext(BaseModel):
    role: str
    name: str
    identification_source: Literal["preset_hit"] = "preset_hit"
    preset_available: bool = True
