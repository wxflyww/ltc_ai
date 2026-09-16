"""智能预填的结构化输出 schema。独立模块，response_formats.py 零改动。"""
from copy import deepcopy
from typing import Any

from app.capabilities.contract_review.response_formats import _nullable_string, _object


def _nullable_number() -> dict[str, Any]:
    """金额 / 计数：只允许 JSON number（不给 string），避免模型输出千分位导致解析失败。"""
    return {"type": ["number", "null"]}


def _nullable_integer() -> dict[str, Any]:
    return {"type": ["integer", "null"]}


EVIDENCE_SCHEMA = _object({
    "section": _nullable_string(),
    "quote": _nullable_string(max_length=60),
})


CONTRACT_INFO_SCHEMA = _object({
    "payment_terms": _nullable_string(),
    "payment_method": _nullable_string(),
    "service_content": _nullable_string(),
    "service_valid_months": _nullable_number(),
    "service_sla": _nullable_string(),
    "service_start_date": _nullable_string(max_length=10),
    "service_end_date": _nullable_string(max_length=10),
    "onsite_service_count": _nullable_number(),
    "inspection_count": _nullable_number(),
})


CONTRACT_PLAN_SCHEMA = {
    "type": "array",
    "items": _object({
        "milestone_name": _nullable_string(),
        "milestone_code": _nullable_string(),
        "milestone_text": _nullable_string(),
        "milestone_seq": _nullable_integer(),
        "plan_finish_date": _nullable_string(max_length=10),
        "plan_payment_date": _nullable_string(max_length=10),
        "payment_amount": _nullable_number(),
        "evidence": {"type": "array", "items": deepcopy(EVIDENCE_SCHEMA)},
    }),
}


FINANCE_INFO_SCHEMA = _object({
    "contract_amount": _nullable_number(),
    "currency": _nullable_string(max_length=8),
})


GUARANTEE_SCHEMA = {
    "type": "array",
    "items": _object({
        "type": {"type": ["string", "null"], "enum": ["履约保函", "履约保证金", None]},
        "amount": _nullable_number(),
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
    "d02": ("contract_info", "contract_plan"),
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
