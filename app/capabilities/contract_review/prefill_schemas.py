"""智能预填的响应模型。**独立于 ContractReviewData**，评审响应模型零改动。"""
from typing import Literal

from pydantic import BaseModel, Field

PrefillStatus = Literal["ok", "failed"]


class PrefillEvidence(BaseModel):
    """原文依据。section 取顶层条款标题原文，原文无标题结构时为 null。"""

    section: str | None = None
    quote: str = ""


class ContractInfo(BaseModel):
    """D-02 合同信息（9 字段）。本组不附 evidence。"""

    payment_terms: str | None = None
    payment_method: str | None = None
    service_content: str | None = None
    service_valid_months: float | None = None
    service_sla: str | None = None
    service_start_date: str | None = None
    service_end_date: str | None = None
    onsite_service_count: float | None = None
    inspection_count: float | None = None


class ContractPlanItem(BaseModel):
    """D-02 合同计划（数组，每项 8 字段）。"""

    milestone_name: str | None = None
    milestone_code: str | None = None
    milestone_text: str | None = None
    milestone_seq: int | None = None
    plan_finish_date: str | None = None
    plan_payment_date: str | None = None
    payment_amount: float | None = None
    evidence: list[PrefillEvidence] = Field(default_factory=list)


class FinanceInfo(BaseModel):
    """D-03 财务信息（2 字段）。本组不附 evidence。"""

    contract_amount: float | None = None
    currency: str | None = None


class GuaranteeItem(BaseModel):
    """D-03 履约保证金 / 保函（数组，每项 7 字段，支持多笔）。"""

    type: str | None = None
    amount: float | None = None
    payee: str | None = None
    bank_name: str | None = None
    bank_account: str | None = None
    return_clause: str | None = None
    evidence: list[PrefillEvidence] = Field(default_factory=list)


class PrefillPayload(BaseModel):
    """四组固定结构。未请求 / 未抽到的组按「未取到」表达，不省略键。"""

    contract_info: ContractInfo = Field(default_factory=ContractInfo)
    contract_plan: list[ContractPlanItem] = Field(default_factory=list)
    finance_info: FinanceInfo = Field(default_factory=FinanceInfo)
    guarantee: list[GuaranteeItem] = Field(default_factory=list)


class PrefillData(BaseModel):
    """mode=prefill 的 data 段。不含 overall_result / check_time / checks / metrics。"""

    mode: Literal["prefill"] = "prefill"
    prefill_status: PrefillStatus
    prefill: PrefillPayload = Field(default_factory=PrefillPayload)
