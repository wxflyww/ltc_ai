import time
from dataclasses import dataclass
from datetime import datetime

from langchain_core.messages import HumanMessage
from pydantic import ValidationError

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
from app.core.errors import ModelFormatError, ModelInputTooLongError, ModelOutputTooLongError
from app.core.llm_trace_audit import add_event as add_trace_event
from app.core.logging import get_logger
from app.models.llm import get_chat_model, invoke_model


PROMPT_METRIC_NAMES = {
    "A-1a": "合同首页/签约方提取",
    "A-1b": "我方签章区块提取",
    "A-3": "金额和付款条款提取",
    "A-4": "合同份数和附件声明提取",
    "B-1": "称谓一致性",
    "B-4": "附件内容一致性",
}

logger = get_logger("contract_review")


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


def _shorten_text(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}...(truncated, total={len(text)} chars)"


def _trace_prompt_enabled(prompt_name: str | None) -> bool:
    filters = [str(item).strip() for item in get_settings().debug.llm_trace_prompts if str(item).strip()]
    if not filters:
        return True
    if not prompt_name:
        return False
    return prompt_name in filters


def _truncate_trace_value(value, max_chars: int):
    if isinstance(value, str):
        return _shorten_text(value, max_chars)
    if isinstance(value, dict):
        return {k: _truncate_trace_value(v, max_chars) for k, v in value.items()}
    if isinstance(value, list):
        return [_truncate_trace_value(item, max_chars) for item in value]
    if isinstance(value, tuple):
        return tuple(_truncate_trace_value(item, max_chars) for item in value)
    return value


def _log_llm_trace(event: str, **extra) -> None:
    settings = get_settings()
    if not settings.debug.llm_trace:
        return

    prompt_name = str(extra.get("prompt_name", "")).strip() or None
    if not _trace_prompt_enabled(prompt_name):
        return

    max_chars = max(0, int(settings.debug.llm_trace_max_chars))
    payload: dict = {"event": event}
    for key, value in extra.items():
        payload[key] = _truncate_trace_value(value, max_chars)
    logger.info("contract review llm trace", extra={"payload": payload})
    add_trace_event(payload)


RESULT_TO_BLOCK_LEVEL = {
    "PASS": "通过",
    "WARN": "提示",
    "FAIL": "硬阻断",
    "NA": "不适用",
}


RESULT_ALIASES = {
    "通过": "PASS",
    "提示": "WARN",
    "硬阻断": "FAIL",
    "不适用": "NA",
}


BLOCK_LEVEL_ALIASES = {
    "pass": "通过",
    "warn": "提示",
    "warning": "提示",
    "fail": "硬阻断",
    "block": "硬阻断",
    "na": "不适用",
    "n/a": "不适用",
    "none": "",
    "null": "",
}


def _add_usage(left: dict, right: dict | None) -> dict:
    right = right or {}
    return {
        "prompt_tokens": int(left.get("prompt_tokens", 0)) + int(right.get("prompt_tokens", 0)),
        "completion_tokens": int(left.get("completion_tokens", 0)) + int(right.get("completion_tokens", 0)),
        "total_tokens": int(left.get("total_tokens", 0)) + int(right.get("total_tokens", 0)),
    }


def _normalize_result(raw_result) -> str:
    text = str(raw_result or "").strip()
    upper = text.upper()
    if upper in RESULT_TO_BLOCK_LEVEL:
        return upper
    return RESULT_ALIASES.get(text, upper)


def _normalize_block_level(raw_level, result: str) -> str:
    text = str(raw_level or "").strip()
    if text in {"通过", "提示", "硬阻断", "不适用"}:
        return text

    normalized = BLOCK_LEVEL_ALIASES.get(text.lower(), text)
    if normalized in {"通过", "提示", "硬阻断", "不适用"}:
        return normalized

    # 模型偶发返回“无/空”，按 result 推断 block_level，避免把可恢复问题放大成 500。
    return RESULT_TO_BLOCK_LEVEL.get(result, "不适用")


def _detect_length_issue(exc: Exception) -> str | None:
    if isinstance(exc, ModelOutputTooLongError):
        return "output"
    text = str(exc).lower()
    output_like = (
        "lengthfinishreasonerror" in text
        or "length limit was reached" in text
        or "finish reason" in text and "length" in text
    )
    input_like = (
        "tokens_limit_reached" in text
        or "context length" in text
        or "maximum context length" in text
        or "context window" in text
        or "maximum input length" in text
        or "input tokens" in text and "context" in text
    )
    if output_like and not input_like:
        return "output"
    if input_like:
        return "input"
    if output_like:
        return "output"
    return None


def _raise_if_length_issue(exc: Exception, label: str) -> None:
    issue = _detect_length_issue(exc)
    if issue == "input":
        raise ModelInputTooLongError(
            f"{label}内容过长，超过模型单次处理长度限制，请拆分该部分内容或减少单次上传内容后重试"
        ) from exc
    if issue == "output":
        raise ModelOutputTooLongError(
            f"{label}模型输出达到长度上限，结果被截断，请缩小检查范围或拆分内容后重试"
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
    _log_llm_trace(
        "invoke_json_prompt_request",
        prompt_name=prompt_name,
        label=label,
        message_count=len(messages),
        last_message=(messages[-1].content if messages else ""),
        response_format_name=((response_format or {}).get("json_schema") or {}).get("name", ""),
    )
    usage = _empty_usage()
    start = time.perf_counter()

    def parse_and_validate(raw_content: str) -> dict:
        payload = parse_json_object(raw_content)
        if required_keys:
            _require_keys(payload, required_keys, label)
        return payload

    try:
        content, call_usage = invoke_model(model, messages, response_format=response_format)
    except Exception as exc:
        _log_llm_trace(
            "invoke_json_prompt_invoke_error",
            prompt_name=prompt_name,
            label=label,
            error_type=exc.__class__.__name__,
            error=str(exc),
            length_issue=_detect_length_issue(exc),
        )
        _raise_if_length_issue(exc, label)
        raise

    try:
        _log_llm_trace(
            "invoke_json_prompt_response",
            prompt_name=prompt_name,
            label=label,
            content=content,
            usage=call_usage,
        )
        usage = _add_usage(usage, call_usage)
        try:
            return parse_and_validate(content)
        except ModelFormatError as first_error:
            _log_llm_trace(
                "invoke_json_prompt_first_parse_error",
                prompt_name=prompt_name,
                label=label,
                error=str(first_error),
            )
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
                _log_llm_trace(
                    "invoke_json_prompt_retry_response",
                    prompt_name=prompt_name,
                    label=label,
                    content=retry_content,
                    usage=retry_usage,
                )
                usage = _add_usage(usage, retry_usage)
            except Exception as exc:
                _log_llm_trace(
                    "invoke_json_prompt_retry_invoke_error",
                    prompt_name=prompt_name,
                    label=label,
                    error_type=exc.__class__.__name__,
                    error=str(exc),
                    length_issue=_detect_length_issue(exc),
                )
                _raise_if_length_issue(exc, label)
                raise
            try:
                return parse_and_validate(retry_content)
            except ModelFormatError as second_error:
                if required_keys and label in second_error.message:
                    raise second_error from first_error
                raise ModelFormatError(f"{prompt_name}{second_error.message}") from first_error
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


def _parse_model_checks(payload: dict, item_id: str, item_name: str, prompt_name: str | None = None) -> list[CheckItem]:
    raw_checks = payload.get("checks", [])
    if not isinstance(raw_checks, list):
        raise ModelFormatError(f"{item_id}模型输出checks不是数组")
    items: list[CheckItem] = []
    for raw in raw_checks:
        if not isinstance(raw, dict):
            raise ModelFormatError(f"{item_id}模型输出checks元素不是对象")
        normalized = dict(raw)
        normalized.setdefault("id", item_id)
        normalized.setdefault("name", item_name)
        normalized["result"] = _normalize_result(normalized.get("result"))
        normalized["block_level"] = _normalize_block_level(
            normalized.get("block_level"),
            normalized["result"],
        )
        _log_llm_trace(
            "parse_model_checks_item",
            prompt_name=prompt_name,
            item_id=item_id,
            item_name=item_name,
            raw=raw,
            normalized=normalized,
        )
        try:
            items.append(CheckItem.model_validate(normalized))
        except ValidationError as exc:
            raise ModelFormatError(f"{item_id}模型输出checks字段不合法：{exc}") from exc
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


_B1_NON_APPELLATION_HINTS = (
    "本合同",
    "本协议",
    "本项目",
    "该项目",
    "双方",
    "本条",
    "上述",
    "措辞",
    "行文",
    "建议统一",
)

_B1_REASON_MAX_CHARS = 160


def _truncate_b1_reason(text: str) -> str:
    if len(text) <= _B1_REASON_MAX_CHARS:
        return text
    return text[: _B1_REASON_MAX_CHARS - 1].rstrip() + "…"


def _decompose_b1_reason_tags(text: str) -> tuple[str, str, str]:
    # Supports legacy tagged reasons:
    # 【主体】...【基准称谓】...【发现称谓】...【证据】...
    def _extract(tag: str, fallback: str = "") -> str:
        if tag not in text:
            return fallback
        start = text.find(tag) + len(tag)
        end = len(text)
        for nxt in ("【主体】", "【基准称谓】", "【发现称谓】", "【证据】"):
            idx = text.find(nxt, start)
            if idx != -1:
                end = min(end, idx)
        return text[start:end].strip()

    subject = _extract("【主体】")
    baseline = _extract("【基准称谓】")
    found = _extract("【发现称谓】")
    evidence = _extract("【证据】")

    # If this is not tagged content, keep as plain evidence.
    if not any((subject, baseline, found, evidence)):
        return "", "", text.strip()

    sentence = evidence
    if found:
        if baseline and found != baseline:
            sentence = f"{subject or '该主体'}称谓疑似不一致，发现“{found}”，基准为“{baseline}”。证据：{evidence}"
        else:
            sentence = f"{subject or '该主体'}称谓未见不一致。证据：{evidence}"
    elif baseline:
        sentence = f"{subject or '该主体'}基准称谓为“{baseline}”。证据：{evidence}"

    return subject, found, sentence.strip()


def _ensure_b1_scope_prefix(reason: str | None, scope_label: str) -> str:
    text = (reason or "").strip()
    natural_prefix = f"{scope_label}中："
    if not text:
        return natural_prefix
    if text.startswith(natural_prefix):
        return _truncate_b1_reason(text)
    if text.startswith("【范围】"):
        normalized = text.removeprefix("【范围】").strip()
        if normalized.startswith(scope_label):
            normalized = normalized[len(scope_label):].strip()
        if normalized.startswith("：") or normalized.startswith(":"):
            normalized = normalized[1:].strip()
        normalized = _decompose_b1_reason_tags(normalized)[2]
        return _truncate_b1_reason(f"{natural_prefix}{normalized}" if normalized else natural_prefix)
    _, _, natural = _decompose_b1_reason_tags(text)
    return _truncate_b1_reason(f"{natural_prefix}{natural}")


def _is_b1_noise(item: CheckItem) -> bool:
    if item.result not in {"WARN", "FAIL"}:
        return False
    text = (item.reason or "")
    _, found, _ = _decompose_b1_reason_tags(text)

    # Non-subject words should not be treated as discovered appellations.
    if found and found in _B1_NON_APPELLATION_HINTS:
        return True

    # Natural-language variant: if the sentence only talks about generic document nouns.
    if any(token in text for token in ("本合同", "本协议", "本项目", "双方")) and "称谓" not in text:
        return True

    if "称谓" not in text:
        return True
    return any(token in text for token in _B1_NON_APPELLATION_HINTS)


def _b1_reason_fingerprint(reason: str | None) -> str:
    text = (reason or "").strip().lower()
    for ch in ("，", "。", "；", ";", "：", ":", "（", "）", "(", ")", " ", "\n", "\t"):
        text = text.replace(ch, "")
    return text


def _finalize_b1_items(items: list[CheckItem], scope_label: str) -> list[CheckItem]:
    finalized: list[CheckItem] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in items:
        reason = _ensure_b1_scope_prefix(item.reason, scope_label)
        normalized_item = CheckItem(
            id=item.id,
            name=f"称谓一致性-{scope_label}",
            result=item.result,
            block_level=item.block_level,
            reason=reason,
        )
        if _is_b1_noise(normalized_item):
            continue
        fp = (
            normalized_item.id,
            normalized_item.name,
            normalized_item.result,
            _b1_reason_fingerprint(normalized_item.reason),
        )
        if fp in seen:
            continue
        seen.add(fp)
        finalized.append(normalized_item)
    if not finalized:
        return [CheckItem(
            id="B-1",
            name=f"称谓一致性-{scope_label}",
            result="PASS",
            block_level="通过",
            reason=None,
        )]
    return finalized


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
    items = _parse_model_checks(payload, "B-1", "称谓一致性", prompt_name="b1_appellation")
    if not _has_generic_b1_reason(items):
        return _finalize_b1_items(items, scope_label)

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
    retry_items = _parse_model_checks(retry_payload, "B-1", "称谓一致性", prompt_name="b1_appellation")
    return _finalize_b1_items(retry_items, scope_label)


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
        items.extend(_parse_model_checks(
            payload,
            "B-4",
            f"附件内容一致性-{attachment.get('title') or attachment.get('index')}",
            prompt_name="b4_attachment_content",
        ))
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
    try:
        pipeline_result = run_review_pipeline(request)
    except ModelInputTooLongError as exc:
        return build_review_data(
            timestamp,
            CheckItem(
                id="模型上下文长度",
                name="模型上下文长度",
                result="FAIL",
                block_level="硬阻断",
                reason=exc.message,
            ),
            metrics=[],
        )
    except ModelOutputTooLongError as exc:
        return build_review_data(
            timestamp,
            CheckItem(
                id="模型输出长度",
                name="模型输出长度",
                result="FAIL",
                block_level="硬阻断",
                reason=exc.message,
            ),
            metrics=[],
        )
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
