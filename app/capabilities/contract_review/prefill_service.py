"""智能预填编排。与评审链路完全独立：不调用 review_contract，也不共享状态。"""
from app.capabilities.contract_review.prefill_prompts import normalize_contract_text, prefill_prompt_kwargs
from app.capabilities.contract_review.prefill_response_formats import (
    SCOPE_GROUPS,
    get_prefill_response_format,
    get_prefill_top_level_keys,
)
from app.capabilities.contract_review.prefill_schemas import PrefillData, PrefillPayload
from app.capabilities.contract_review.schemas import ContractReviewRequest
from app.capabilities.contract_review.service import _invoke_json_prompt
from app.core.logging import get_logger

logger = get_logger("contract_review_prefill")


def _plan_sort_key(row) -> tuple[bool, int]:
    raw = row.get("milestone_seq") if isinstance(row, dict) else None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = None
    return (value is None, value or 0)


def _build_payload(scope: str, payload: dict) -> PrefillPayload:
    groups = set(SCOPE_GROUPS[scope])
    data: dict = {}
    if "contract_info" in groups:
        data["contract_info"] = payload.get("contract_info") or {}
    if "contract_plan" in groups:
        rows = payload.get("contract_plan") or []
        data["contract_plan"] = sorted(rows, key=_plan_sort_key) if isinstance(rows, list) else []
    if "finance_info" in groups:
        data["finance_info"] = payload.get("finance_info") or {}
    if "guarantee" in groups:
        rows = payload.get("guarantee") or []
        data["guarantee"] = rows if isinstance(rows, list) else []
    return PrefillPayload.model_validate(data)


def run_prefill(request: ContractReviewRequest) -> PrefillData:
    """执行预填。任何失败都降级为 prefill_status=failed + 全空结构，HTTP 仍为成功。"""
    scope = request.prefill_scope
    contract_md = normalize_contract_text(request.contract_md)
    try:
        payload = _invoke_json_prompt(
            "prefill",
            required_keys=get_prefill_top_level_keys(scope),
            validation_label=f"预填-{scope}",
            response_format=get_prefill_response_format(scope),
            **prefill_prompt_kwargs(scope, contract_md),
        )
        return PrefillData(prefill_status="ok", prefill=_build_payload(scope, payload))
    except Exception:
        logger.exception("prefill failed", extra={"prefill_scope": scope})
        return PrefillData(prefill_status="failed")
