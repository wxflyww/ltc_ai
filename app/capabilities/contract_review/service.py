import time
from dataclasses import dataclass
from datetime import datetime

from langchain_core.messages import HumanMessage

from app.capabilities.contract_review.attachments import check_copies_and_attachments
from app.capabilities.contract_review.checks import (
    build_review_data,
    check_amount_payment,
    check_seq1,
    check_seq2_11,
    check_seq3,
)
from app.capabilities.contract_review.embedded_attachments import split_embedded_attachments
from app.capabilities.contract_review.preset_client import fetch_preset, identify_our_party
from app.capabilities.contract_review.party import build_candidate_parties
from app.capabilities.contract_review.prompts import build_prompt, parse_json_object
from app.capabilities.contract_review.response_formats import get_response_format
from app.capabilities.contract_review.schemas import (
    CheckItem,
    CheckMetric,
    ContractReviewData,
    ContractReviewRequest,
    HeaderInfo,
    SignatureInfo,
)
from app.core.config import get_settings
from app.core.errors import ModelFormatError, ModelInputTooLongError
from app.models.llm import get_chat_model, invoke_model


PROMPT_METRIC_NAMES = {
    "A-1a": "合同首页/签约方提取",
    "A-1b": "我方签章区块提取",
    "A-3": "金额和付款条款提取",
    "A-4": "合同份数和附件声明提取",
    "B-1": "称谓一致性",
    "B-4": "附件内容一致性",
}


@dataclass
class PipelineResult:
    items: list[CheckItem | dict]
    metrics: list[CheckMetric]

    def __iter__(self):
        return iter(self.items)

    def __getitem__(self, key: str):
        if key == "items":
            return self.items
        if key == "metrics":
            return self.metrics
        raise KeyError(key)


def _empty_usage() -> dict:
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def _add_usage(left: dict, right: dict | None) -> dict:
    right = right or {}
    return {
        "prompt_tokens": int(left.get("prompt_tokens", 0)) + int(right.get("prompt_tokens", 0)),
        "completion_tokens": int(left.get("completion_tokens", 0)) + int(right.get("completion_tokens", 0)),
        "total_tokens": int(left.get("total_tokens", 0)) + int(right.get("total_tokens", 0)),
    }


def _is_context_length_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "context length" in text
        or "maximum input length" in text
        or "input tokens" in text and "context" in text
    )


def _raise_if_context_length_error(exc: Exception, label: str) -> None:
    if _is_context_length_error(exc):
        raise ModelInputTooLongError(
            f"{label}内容过长，超过模型单次处理长度限制，请拆分该部分内容或减少单次上传内容后重试"
        ) from exc


def _require_keys(payload: dict, keys: list[str], prompt_name: str) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise ModelFormatError(f"{prompt_name}模型输出缺少字段：{', '.join(missing)}")


def _invoke_json_prompt(
    prompt_name: str,
    *,
    required_keys: list[str] | None = None,
    validation_label: str | None = None,
    metrics: list[CheckMetric] | None = None,
    metric_id: str | None = None,
    metric_name: str | None = None,
    **kwargs,
) -> dict:
    model = get_chat_model()
    messages = build_prompt(prompt_name, **kwargs)
    response_format = get_response_format(prompt_name)
    label = validation_label or metric_id or prompt_name
    usage = _empty_usage()
    start = time.perf_counter()

    def parse_and_validate(raw_content: str) -> dict:
        payload = parse_json_object(raw_content)
        if required_keys:
            _require_keys(payload, required_keys, label)
        return payload

    try:
        content, call_usage = invoke_model(model, messages, response_format=response_format)
        usage = _add_usage(usage, call_usage)
        try:
            return parse_and_validate(content)
        except ModelFormatError as first_error:
            retry_messages = [
                *messages,
                HumanMessage(content=(
                    "上一次输出不是符合要求的JSON。请只返回一个JSON对象，"
                    "不要解释、不要markdown代码块、不要<think>内容；"
                    "必须严格包含提示词要求的顶层字段和JSON结构。"
                )),
            ]
            try:
                retry_content, retry_usage = invoke_model(
                    model,
                    retry_messages,
                    response_format=response_format,
                )
                usage = _add_usage(usage, retry_usage)
            except Exception as exc:
                _raise_if_context_length_error(exc, label)
                raise
            try:
                return parse_and_validate(retry_content)
            except ModelFormatError as second_error:
                if required_keys and label in second_error.message:
                    raise second_error from first_error
                raise ModelFormatError(f"{prompt_name}{second_error.message}") from first_error
    except Exception as exc:
        _raise_if_context_length_error(exc, label)
        raise
    finally:
        if metrics is not None:
            final_id = metric_id or label
            metrics.append(CheckMetric(
                id=final_id,
                name=metric_name or PROMPT_METRIC_NAMES.get(final_id, prompt_name),
                duration_seconds=round(time.perf_counter() - start, 3),
                token_usage=usage,
            ))


def _preprocess_request(request: ContractReviewRequest) -> dict:
    contract_md, embedded_attachments = split_embedded_attachments(request.contract_md)
    uploaded_attachments = [item.model_dump() for item in request.attachments]
    attachment_dicts = [*embedded_attachments, *uploaded_attachments]
    return {
        "full_text": contract_md,
        "attachments": attachment_dicts,
    }


def _parse_model_checks(payload: dict, item_id: str, item_name: str) -> list[CheckItem]:
    raw_checks = payload.get("checks", [])
    if not isinstance(raw_checks, list):
        raise ModelFormatError(f"{item_id}模型输出checks不是数组")
    items: list[CheckItem] = []
    for raw in raw_checks:
        if not isinstance(raw, dict):
            raise ModelFormatError(f"{item_id}模型输出checks元素不是对象")
        raw.setdefault("id", item_id)
        raw.setdefault("name", item_name)
        items.append(CheckItem.model_validate(raw))
    if not items:
        items.append(CheckItem(id=item_id, name=item_name, result="PASS", block_level="通过", reason=None))
    return items


GENERIC_B1_REASONS = {
    "称谓存在不一致",
    "存在称谓不一致",
    "称谓不一致",
    "称谓不统一",
    "各签约方称谓存在不一致",
    "各签约方称谓不统一",
}


def _has_generic_b1_reason(items: list[CheckItem]) -> bool:
    for item in items:
        if item.result not in {"WARN", "FAIL"}:
            continue
        reason = (item.reason or "").strip().rstrip("。；;")
        if reason in GENERIC_B1_REASONS:
            return True
    return False


def _b1_segment_id(scope_label: str) -> str:
    return f"B-1-{scope_label}"


def _attachment_scope_label(attachment: dict) -> str:
    if str(attachment.get("source", "")).startswith("单独上传") and attachment.get("filename"):
        return str(attachment["filename"])
    return str(attachment.get("title") or attachment.get("filename") or f"附件{attachment.get('index')}")


def _run_b1_segment(
    scope_label: str,
    segment_text: str,
    parties: list[dict],
    metrics: list[CheckMetric] | None = None,
) -> list[CheckItem]:
    segment_id = _b1_segment_id(scope_label)
    payload = _invoke_json_prompt(
        "b1_appellation",
        required_keys=["checks"],
        validation_label=segment_id,
        metrics=metrics,
        metric_id=segment_id,
        metric_name=f"称谓一致性-{scope_label}",
        parties=parties,
        scope_label=scope_label,
        segment_text=segment_text,
    )
    items = _parse_model_checks(payload, "B-1", "称谓一致性")
    if not _has_generic_b1_reason(items):
        return items

    retry_payload = _invoke_json_prompt(
        "b1_appellation",
        required_keys=["checks"],
        validation_label=segment_id,
        metrics=metrics,
        metric_id=f"{segment_id}-补充说明",
        metric_name=f"称谓一致性-{scope_label}-补充说明",
        parties=parties,
        scope_label=scope_label,
        segment_text=(
            f"{segment_text}\n\n"
            "【补充要求】上一次reason过于笼统。若存在称谓不一致，"
            "必须说明涉及哪一方或哪个主体、出现了哪些不同称谓、分别出现在哪些位置或上下文中；"
            "禁止只输出“称谓存在不一致”“存在称谓不一致”“称谓不统一”等泛化描述。"
        ),
    )
    return _parse_model_checks(retry_payload, "B-1", "称谓一致性")


def _run_b1(contract_text: str, attachments: list[dict], parties: list[dict], metrics: list[CheckMetric] | None = None) -> list[CheckItem]:
    segment_metrics: list[CheckMetric] = []
    items: list[CheckItem] = []
    items.extend(_run_b1_segment("合同正文", contract_text, parties, segment_metrics))
    for attachment in attachments:
        scope_label = _attachment_scope_label(attachment)
        items.extend(_run_b1_segment(scope_label, attachment.get("text", ""), parties, segment_metrics))

    if metrics is not None:
        total_usage = _empty_usage()
        for metric in segment_metrics:
            total_usage = _add_usage(total_usage, metric.token_usage.model_dump())
        metrics.append(CheckMetric(
            id="B-1",
            name="称谓一致性",
            duration_seconds=round(sum(metric.duration_seconds for metric in segment_metrics), 3),
            token_usage=total_usage,
            segments=segment_metrics,
        ))
    return items


def _run_b4(resolved_attachments: list[dict], baseline: dict, metrics: list[CheckMetric] | None = None) -> list[CheckItem]:
    items: list[CheckItem] = []
    for attachment in resolved_attachments:
        scope_label = _attachment_scope_label(attachment)
        payload = _invoke_json_prompt(
            "b4_attachment_content",
            required_keys=["checks"],
            validation_label=f"B-4-{scope_label}",
            metrics=metrics,
            metric_id=f"B-4-{scope_label}",
            metric_name=f"附件内容一致性-{scope_label}",
            baseline=baseline,
            attachment_text=attachment.get("text", ""),
        )
        items.extend(_parse_model_checks(payload, "B-4", f"附件内容一致性-{attachment.get('title') or attachment.get('index')}"))
    if not resolved_attachments:
        items.append(CheckItem(id="B-4", name="附件内容一致性", result="NA", block_level="不适用", reason="无可检查附件"))
    return items


def run_review_pipeline(request: ContractReviewRequest) -> PipelineResult:
    prepared = _preprocess_request(request)
    metrics: list[CheckMetric] = []

    a1a = _invoke_json_prompt(
        "a1a_party_extraction",
        required_keys=["header", "signature_parties", "sections"],
        validation_label="A-1a",
        metrics=metrics,
        metric_id="A-1a",
        full_text=prepared["full_text"],
    )
    _require_keys(a1a, ["header", "signature_parties", "sections"], "A-1a")
    header = HeaderInfo.model_validate(a1a["header"])

    seen_candidate_names: set[str] = set()
    candidate_names: list[str] = []
    for party in build_candidate_parties(header.parties):
        name = (party.name or "").strip()
        if name and name not in seen_candidate_names:
            candidate_names.append(name)
            seen_candidate_names.add(name)
    preset_configured = bool(get_settings().signing_preset.base_url)
    our_party, preset = identify_our_party(header.parties, fetch_preset)

    if our_party is not None:
        a1b = _invoke_json_prompt(
            "a1b_our_signature",
            required_keys=["signature"],
            validation_label="A-1b",
            metrics=metrics,
            metric_id="A-1b",
            our_party=our_party.name,
            full_text=prepared["full_text"],
        )
        _require_keys(a1b, ["signature"], "A-1b")
        signature = SignatureInfo.model_validate({
            **a1b["signature"],
            "signature_parties": a1a.get("signature_parties", []),
        })
    else:
        signature = SignatureInfo(signature_parties=[])

    items: list[CheckItem] = []
    items.extend(check_seq1(
        header,
        our_party,
        preset,
        candidate_names=candidate_names,
        preset_configured=preset_configured,
    ))
    seq2_items, seq11_items = check_seq2_11(header, signature, our_party, preset)
    items.extend(seq2_items)
    items.append(check_seq3(header, signature, our_party))
    items.extend(seq11_items)

    a3 = _invoke_json_prompt(
        "a3_amount_payment",
        validation_label="A-3",
        metrics=metrics,
        metric_id="A-3",
        full_text=prepared["full_text"],
    )
    items.extend(check_amount_payment(a3))

    a4 = _invoke_json_prompt(
        "a4_copies_attachments",
        required_keys=["copies", "attachments_declared"],
        validation_label="A-4",
        metrics=metrics,
        metric_id="A-4",
        full_text=prepared["full_text"],
    )
    _require_keys(a4, ["copies", "attachments_declared"], "A-4")
    attachment_result = check_copies_and_attachments(
        a4,
        a1a.get("sections", []),
        prepared["attachments"],
        prepared["full_text"],
    )
    items.extend(attachment_result["check_results"])

    b1_parties = [party.model_dump() for party in header.parties]
    items.extend(_run_b1(prepared["full_text"], attachment_result["resolved_attachments"], b1_parties, metrics))
    items.extend(_run_b4(attachment_result["resolved_attachments"], {
        "header": header.model_dump(),
        "signature": signature.model_dump(),
        "preset": preset.model_dump() if preset is not None else None,
    }, metrics))
    return PipelineResult(items=items, metrics=metrics)


def review_contract(request: ContractReviewRequest, check_time: str | None = None) -> ContractReviewData:
    timestamp = check_time or datetime.now().isoformat(timespec="seconds")
    pipeline_result = run_review_pipeline(request)
    if isinstance(pipeline_result, PipelineResult):
        raw_items = pipeline_result.items
        metrics = pipeline_result.metrics
    elif isinstance(pipeline_result, dict):
        raw_items = pipeline_result.get("items", [])
        metrics = [metric if isinstance(metric, CheckMetric) else CheckMetric(**metric) for metric in pipeline_result.get("metrics", [])]
    else:
        raw_items = pipeline_result
        metrics = []
    items = [item if isinstance(item, CheckItem) else CheckItem(**item) for item in raw_items]
    return build_review_data(timestamp, items, metrics=metrics)
