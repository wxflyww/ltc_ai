"""智能预填的结构化输出 schema。独立模块，response_formats.py 零改动。

取值口径（2026-09-17 定）：**除 `milestone_seq` 外一律 string**，承载原文原样摘录。
不再有「金额 / 计数」的 number 类型 —— 一是 JSON number 语法本身不允许千分位与货币符号，
逼着模型做格式加工；二是 Pydantic 的 `float` 会把模型输出的整数序列化成 `13.0`，
下游按整型反序列化即失败。类型交给合同系统自行决定。
"""
from copy import deepcopy
from typing import Any

from app.capabilities.contract_review.response_formats import _nullable_string, _object


def _nullable_integer() -> dict[str, Any]:
    """唯一的非字符串字段：`milestone_seq`（本链路生成的阶段流水号）。"""
    return {"type": ["integer", "null"]}


EVIDENCE_SCHEMA = _object({
    "section": _nullable_string(),
    "quote": _nullable_string(max_length=300),
})


CONTRACT_INFO_SCHEMA = _object({
    "payment_terms": _nullable_string(),
    "payment_method": _nullable_string(),
    "service_content": _nullable_string(),
    "service_valid_months": _nullable_string(),
    "service_sla": _nullable_string(),
    "service_start_date": _nullable_string(),
    "service_end_date": _nullable_string(),
    "onsite_service_count": _nullable_string(),
    "inspection_count": _nullable_string(),
})


CONTRACT_PLAN_SCHEMA = {
    "type": "array",
    "items": _object({
        "milestone_name": _nullable_string(),
        "milestone_code": _nullable_string(),
        "milestone_text": _nullable_string(),
        "milestone_seq": _nullable_integer(),
        "plan_finish_date": _nullable_string(),
        "plan_payment_date": _nullable_string(),
        "payment_amount": _nullable_string(),
        "evidence": {"type": "array", "items": deepcopy(EVIDENCE_SCHEMA)},
    }),
}


FINANCE_INFO_SCHEMA = _object({
    "contract_amount": _nullable_string(),
    # `currency` 口径为 ISO 4217 三位大写代码（2026-10-05 定），故把上限由 8 收紧为 3。
    # 属 schema 约束收紧：不新增字段、不改名、不改字段集合。
    "currency": _nullable_string(max_length=3),
})


GUARANTEE_SCHEMA = {
    "type": "array",
    "items": _object({
        # `type` 取值集合（2026-10-13 扩枚举）：由 3 值扩为「保函种类表」全量 + 实务保留值。
        # 业务方判定（吴钢/王晓丽 2026-10-12/13）：保函种类按「开立方→受益人 / 担保时间段 / 核心保障 / 常见金额」
        # 区分；表内「质量·质保保函」实为 `质量保函` / `质保保函` **两种类型**（说明相同）；
        # `履约保证金` 表内无此项，按**合同实务常见概念**保留。
        # 🔴 **枚举 ≠ 可选输出值**（2026-10-14 用户定义）：d03 **只输出** `履约保函` / `履约保证金` **两种**；
        # 其余 5 类（预付款 / 投标 / 质量 / 质保 / 支付）在此保留，是作**负向参考**用的 ——
        # 命中其一即可 100% 确定"不是履约类"→ **该条不输出**；落在 7 类之外或判不清 → **同样不输出**。
        # 保留它们是为了把"不是履约类"**固化成可复核的判据**（避免语义不清时抖动），
        # **不是**把它们当候选值（取值约束在 prompt 层实现，见 `_FIELDS["guarantee"]`）。
        # 属**取值集合放宽**：不新增字段、不改名、不改字段集合、不改类型（仍是 string|null）。
        # ⚠️ 下游若对 type 做严格枚举解析，仍需认知**全部**取值；但**不应期待**出现其余 5 类之一。
        "type": {
            "type": ["string", "null"],
            "enum": [
                "履约保函", "履约保证金", "预付款保函",
                "投标保函", "质量保函", "质保保函", "支付保函",
                None,
            ],
        },
        "amount": _nullable_string(),
        "payee": _nullable_string(),
        "bank_name": _nullable_string(),
        "bank_account": _nullable_string(),
        "return_clause": _nullable_string(),
        "evidence": {"type": "array", "items": deepcopy(EVIDENCE_SCHEMA)},
    }),
}


_GROUP_SCHEMAS: dict[str, Any] = {
    "contract_info": CONTRACT_INFO_SCHEMA,
    "contract_plan": CONTRACT_PLAN_SCHEMA,
    "finance_info": FINANCE_INFO_SCHEMA,
    "guarantee": GUARANTEE_SCHEMA,
}

SCOPE_GROUPS: dict[str, tuple[str, ...]] = {
    "all": ("contract_info", "contract_plan", "finance_info", "guarantee"),
    # `finance_info`（contract_amount + currency）同时属于 d02 与 d03：
    # D-02 的 contract_plan[].payment_amount 多为比例（如 "50%"），消费方必须有合同总额才能折算成金额；
    # 故该组按「基础信息」而非「场景专有」归属，两个场景都返回。（2026-09-18 定）
    "d02": ("contract_info", "contract_plan", "finance_info"),
    "d03": ("finance_info", "guarantee"),
}


def get_prefill_top_level_keys(scope: str) -> list[str]:
    """该 scope 下模型必须输出的顶层键（同时用作 required_keys 内容兜底）。"""
    return list(SCOPE_GROUPS[scope])


def get_prefill_response_format(scope: str) -> dict[str, Any]:
    groups = SCOPE_GROUPS[scope]
    return {
        "type": "json_schema",
        "json_schema": {
            "name": f"contract_review_prefill_{scope}",
            "strict": True,
            "schema": _object({name: deepcopy(_GROUP_SCHEMAS[name]) for name in groups}),
        },
    }
