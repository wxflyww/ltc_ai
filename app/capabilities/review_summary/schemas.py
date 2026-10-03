"""评审智能总结请求/响应 Pydantic 模型。

字段定义以 `docs/integration/2026-10-02-review-summary-design.md` 为唯一事实源：
输入四组（`contract_meta` / `route_reason` / `risk_register` / `opinions`），
输出四块（`review_summary` / `key_concerns` / `opinion_details` / `degraded_sections`）。
未列出的新增可选字段沿用既有能力口径（忽略、不拒绝），为后续 CRM 扩展字段留兼容。
"""
from typing import Annotated, Literal

from pydantic import BaseModel, Field

Action = Literal["pass", "conditional", "reject"]


class ContractMeta(BaseModel):
    """合同要素（整组可选；字段全 optional，缺位由总述跳过不补）。"""

    contract_type: str | None = None
    contract_amount: str | None = None
    gross_margin: str | None = None


class RouteReason(BaseModel):
    """提级原因（合同系统已生成的人话原文，接口照搬不润色）。"""

    text: str = Field(min_length=1)


class RiskRegisterItem(BaseModel):
    """高风险项（合同系统预选；12 字段全部"有就照搬、没有就不传"）。"""

    risk_id: str | None = None
    title: str | None = None
    level: str | None = None
    source: str | None = None
    description: str | None = None
    standard_clause: str | None = None
    potential_impact: str | None = None
    measure_type: str | None = None
    measure_desc: str | None = None
    decision_type: str | None = None
    decision_note: str | None = None
    decision_by: str | None = None


class Opinion(BaseModel):
    """单条评审意见（一人多角色拆多条记录）。"""

    node_name: str
    approver_name: str
    role: str
    action: Action
    comment: str
    submitted_at: str | None = None


class ReviewSummaryRequest(BaseModel):
    """POST /api/v1/review-summary 请求体（四组数据）。"""

    contract_meta: ContractMeta | None = None
    route_reason: RouteReason | None = None
    risk_register: list[RiskRegisterItem] = Field(default_factory=list)
    opinions: list[Opinion]


class ReviewSummarySection(BaseModel):
    """一、评审总结：一句话总述（AI）+ 溯源引用。"""

    text: str | None = None
    source_refs: list[str] = Field(default_factory=list)


class EscalationConcern(BaseModel):
    """重点关注·提级原因块（原文照搬，固定置首）。"""

    type: Literal["escalation"] = "escalation"
    text: str


class RiskMeasure(BaseModel):
    """处置参考（清单应对措施原文，零 AI）。"""

    measure_type: str | None = None
    measure_desc: str | None = None


class RiskConcern(BaseModel):
    """重点关注·风险块（risk_register 字段照搬 + measure 块）。"""

    type: Literal["risk"] = "risk"
    risk_id: str | None = None
    title: str | None = None
    level: str | None = None
    source: str | None = None
    description: str | None = None
    standard_clause: str | None = None
    potential_impact: str | None = None
    decision_type: str | None = None
    decision_by: str | None = None
    decision_note: str | None = None
    measure: RiskMeasure | None = None


KeyConcern = Annotated[EscalationConcern | RiskConcern, Field(discriminator="type")]


class OpinionDetail(BaseModel):
    """三、各节点意见详情：骨架字段照搬 + AI 摘要。"""

    node_name: str
    approver_name: str
    role: str
    action: Action
    summary: str | None = None
    source_ref: str | None = None


class ReviewSummaryData(BaseModel):
    """整包面板 JSON 的 `data` 部分（四块齐全）。"""

    review_summary: ReviewSummarySection
    key_concerns: list[KeyConcern] = Field(default_factory=list)
    opinion_details: list[OpinionDetail] = Field(default_factory=list)
    degraded_sections: list[str] = Field(default_factory=list)
