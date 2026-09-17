"""智能预填的响应模型。**独立于 ContractReviewData**，评审响应模型零改动。

取值口径（2026-09-17 定）：**除 `milestone_seq` 外，业务字段一律字符串**，内容为
原文原样摘录 —— 不做数字换算、不剥货币符号、不去千分位、不做日期归一。
原因：任何本机类型转换都是加工误差来源（`float` 会把整数 `13` 序列化成 `13.0`，
`int` 遇到原文 `13.5` 直接报错）。展示类型由合同系统自行定夺。

`milestone_seq` 是例外：它不是原文摘录，而是本链路生成的阶段流水号，且排序依赖数值比较。

两个时间字段的来源固定（2026-09-17 第十一轮），且**服务端不做任何推算**：
`plan_finish_date` = 合同计划章节 → 交付/验收条款 → `null`；`plan_payment_date` = 只取自付款条件。
它们的值可能是绝对日期、相对表述或事件起算，故 `*_date` 字段名有误导性 —— 调用方须先试解析、
失败就原样展示。

`evidence` 是**行级、按出处**的（`contract_plan` 每行固定 3 条）。某处出处原文确实不存在时，
该条为 `{"section": null, "quote": "无"}` —— 「无」按**出处**而非按字段理解，否则会自相矛盾
（同一行的 `payment_amount` 明明有依据）。本模块不含任何字段级抽取状态。
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PrefillStatus = Literal["ok", "failed"]


class _VerbatimModel(BaseModel):
    """取值模型基类：业务值一律字符串。

    `coerce_numbers_to_str` 是**兜底**：万一模型违反 strict schema 吐了数字，
    就按原值字符串化（`13` → `"13"`），而不是让整次预填降级成 `failed`（26 个字段全空）。
    它**不做格式加工** —— 原值一字节不改，只把类型摆正。正常路径下 strict grammar
    不允许数字出现，这一层是给"后端不强制 strict"的保险。
    """

    model_config = ConfigDict(coerce_numbers_to_str=True)


class PrefillEvidence(BaseModel):
    """原文依据。section 取顶层条款标题原文，原文无标题结构时为 null。

    `quote == "无"` 是**出处缺失的显式声明**（该处出处在原文里确实不存在），不是空值占位 ——
    调用方须用**全等**判定，否则原文里的"无违约条款"会被误判成缺失。
    """

    section: str | None = None
    quote: str = ""


class ContractInfo(_VerbatimModel):
    """D-02 合同信息（9 字段）。本组不附 evidence。全部为原文摘录字符串。"""

    payment_terms: str | None = None
    payment_method: str | None = None
    service_content: str | None = None
    service_valid_months: str | None = None
    service_sla: str | None = None
    service_start_date: str | None = None
    service_end_date: str | None = None
    onsite_service_count: str | None = None
    inspection_count: str | None = None


class ContractPlanItem(_VerbatimModel):
    """D-02 合同计划（数组，每项 8 字段）。`milestone_seq` 是唯一的整数字段。"""

    milestone_name: str | None = None
    milestone_code: str | None = None
    milestone_text: str | None = None
    milestone_seq: int | None = None
    plan_finish_date: str | None = None
    plan_payment_date: str | None = None
    payment_amount: str | None = None
    evidence: list[PrefillEvidence] = Field(default_factory=list)


class FinanceInfo(_VerbatimModel):
    """D-03 财务信息（2 字段）。本组不附 evidence。"""

    contract_amount: str | None = None
    currency: str | None = None


class GuaranteeItem(_VerbatimModel):
    """D-03 履约保证金 / 保函（数组，每项 7 字段，支持多笔）。"""

    type: str | None = None
    amount: str | None = None
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
