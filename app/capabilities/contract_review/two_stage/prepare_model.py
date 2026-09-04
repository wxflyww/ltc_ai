from __future__ import annotations

import json
import random
import re
import time
from typing import Any, Generic, Literal, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError as PydanticValidationError,
    field_validator,
)

from app.capabilities.contract_review.two_stage.prepare_prompts import build_prepare_prompt
from app.capabilities.contract_review.two_stage.prepare_response_formats import (
    PreparePromptName,
    get_prepare_response_format,
)
from app.capabilities.contract_review.two_stage.schemas import NonBlankStr
from app.core.errors import (
    ModelFormatError,
    ModelInvocationError,
    ModelOutputTooLongError,
    ModelTimeoutError,
)
from app.core.logging import get_logger
from app.models.llm import get_chat_model, invoke_model


_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)
_FENCED_JSON_RE = re.compile(r"^```(?:json|JSON)?\s*(.*?)\s*```$", re.S)

_MAX_TRANSIENT_ATTEMPTS = 3
_MAX_FORMAT_ATTEMPTS = 2

_logger = get_logger("prepare_model")

TEnvelope = TypeVar("TEnvelope")


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class QuoteCandidate(_StrictModel):
    quote: NonBlankStr


class SourceGapCandidate(_StrictModel):
    affected_fact_kinds: list[NonBlankStr] = Field(min_length=1)
    message: NonBlankStr
    quote: NonBlankStr | None = None
    document_key: NonBlankStr | None = None


class HeaderPartiesCandidate(QuoteCandidate):
    candidate_ref: NonBlankStr
    candidate_kind: Literal[
        "CONTRACT_NAME",
        "CONTRACT_NUMBER",
        "PROJECT_NAME",
        "PROJECT_NUMBER",
        "SIGNING_LOCATION",
        "SIGNING_DATE",
        "CANONICAL_PARTY",
        "PARTY_MENTION",
    ]
    document_key: NonBlankStr
    contract_name: NonBlankStr | None = None
    contract_number: NonBlankStr | None = None
    project_name: NonBlankStr | None = None
    project_number: NonBlankStr | None = None
    signing_location: NonBlankStr | None = None
    signing_date: NonBlankStr | None = None
    party_role: NonBlankStr | None = None
    party_name: NonBlankStr | None = None
    party_aliases: list[NonBlankStr] = Field(default_factory=list)
    mention_text: NonBlankStr | None = None


class SignatureCandidate(QuoteCandidate):
    candidate_ref: NonBlankStr
    candidate_kind: Literal[
        "SIGNATURE_BLOCK",
        "SIGNER_NAME",
        "IDENTITY_NUMBER",
        "SIGNING_DATE",
        "BANK_NAME",
        "BANK_ACCOUNT",
        "ACCOUNT_HOLDER",
        "ADDRESS",
        "PHONE",
        "FAX",
        "WEBSITE",
        "POSTAL_CODE",
    ]
    document_key: NonBlankStr
    party_name: NonBlankStr | None = None
    role_text: NonBlankStr | None = None
    signer_name: NonBlankStr | None = None
    identity_number: NonBlankStr | None = None
    signing_date: NonBlankStr | None = None
    bank_name: NonBlankStr | None = None
    bank_account: NonBlankStr | None = None
    account_holder: NonBlankStr | None = None
    address: NonBlankStr | None = None
    phone: NonBlankStr | None = None
    fax: NonBlankStr | None = None
    website: NonBlankStr | None = None
    postal_code: NonBlankStr | None = None


class AmountCopyCandidate(QuoteCandidate):
    candidate_ref: NonBlankStr
    candidate_kind: Literal[
        "CURRENCY",
        "PAYMENT_METHOD",
        "TOTAL_AMOUNT",
        "AMOUNT_PAIR",
        "PAYMENT_STAGE",
        "COPY_TOTAL",
        "COPY_ALLOCATION",
    ]
    document_key: NonBlankStr
    currency: NonBlankStr | None = None
    payment_method: NonBlankStr | None = None
    total_amount_numeric: NonBlankStr | None = None
    total_amount_uppercase: NonBlankStr | None = None
    amount_label: NonBlankStr | None = None
    amount_numeric: NonBlankStr | None = None
    amount_uppercase: NonBlankStr | None = None
    stage_name: NonBlankStr | None = None
    stage_ratio: NonBlankStr | None = None
    stage_amount_numeric: NonBlankStr | None = None
    stage_amount_uppercase: NonBlankStr | None = None
    copies_total: NonBlankStr | None = None
    copy_role: NonBlankStr | None = None
    copy_count: NonBlankStr | None = None


class AttachmentCandidate(QuoteCandidate):
    candidate_ref: NonBlankStr
    candidate_kind: Literal[
        "PARTY_MENTION",
        "DECLARED_ATTACHMENT",
        "LOGICAL_ATTACHMENT",
        "ATTACHMENT_RELATION",
        "DECLARED_TOTAL",
    ]
    document_key: NonBlankStr
    mention_text: NonBlankStr | None = None
    declared_index: NonBlankStr | None = None
    declared_title: NonBlankStr | None = None
    declared_total: NonBlankStr | None = None
    content_embedded: bool | None = None
    section_heading_hint: NonBlankStr | None = None
    logical_title: NonBlankStr | None = None
    relation_target_ref: NonBlankStr | None = None
    relation_kind: NonBlankStr | None = None


class PrepareModelEnvelope(_StrictModel, Generic[TEnvelope]):
    candidates: TEnvelope
    source_gaps: list[SourceGapCandidate] = Field(default_factory=list)

    @field_validator("candidates")
    @classmethod
    def _candidate_refs_must_be_unique(cls, candidates: TEnvelope) -> TEnvelope:
        if not isinstance(candidates, list):
            return candidates
        candidate_refs = [
            candidate_ref
            for candidate in candidates
            if (candidate_ref := getattr(candidate, "candidate_ref", None)) is not None
        ]
        if len(candidate_refs) != len(set(candidate_refs)):
            raise ValueError("candidate_ref must be unique within one model output")
        return candidates


PromptCandidate = (
    HeaderPartiesCandidate
    | SignatureCandidate
    | AmountCopyCandidate
    | AttachmentCandidate
)

_CANDIDATE_MODEL_BY_PROMPT: dict[PreparePromptName, type[PromptCandidate]] = {
    "prepare_header_parties_main": HeaderPartiesCandidate,
    "prepare_signature_document": SignatureCandidate,
    "prepare_amount_copy_main": AmountCopyCandidate,
    "prepare_attachment_document": AttachmentCandidate,
}


def _strip_think_blocks(text: str) -> str:
    return _THINK_BLOCK_RE.sub("", text).strip()


def _strip_fenced_block(text: str) -> str:
    match = _FENCED_JSON_RE.match(text)
    return match.group(1).strip() if match else text


def _extract_first_json_object(text: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _parse_json_object_without_logging_content(content: str) -> dict[str, Any]:
    text = _strip_fenced_block(_strip_think_blocks(content.strip()))
    parse_failed = False
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        extracted = _extract_first_json_object(text)
        if extracted is not None:
            return extracted
        parse_failed = True
        parsed = None
    if parse_failed:
        raise ModelFormatError("模型输出不是合法JSON对象")
    if not isinstance(parsed, dict):
        raise ModelFormatError("模型输出JSON不是对象")
    return parsed


def _sanitize_validation_error(prompt_name: str, exc: PydanticValidationError) -> ModelFormatError:
    fields: list[str] = []
    for error in exc.errors():
        loc = error.get("loc", ())
        field_path = ".".join(str(part) for part in loc)
        if field_path:
            fields.append(field_path)
    unique_fields = sorted(set(fields))
    joined = ", ".join(unique_fields) if unique_fields else "unknown"
    return ModelFormatError(f"{prompt_name} 输出字段不符合预期: {joined}")


def _log_retry_event(
    *,
    prompt_name: str,
    attempt: int,
    status: str,
    duration_seconds: float,
    token_usage: dict[str, Any] | None,
    error_type: str | None,
) -> None:
    _logger.info(
        "prepare_model_attempt",
        extra={
            "prompt_name": prompt_name,
            "attempt": attempt,
            "status": status,
            "duration_seconds": round(duration_seconds, 6),
            "token_usage": token_usage,
            "error_type": error_type,
        },
    )


def _sleep_transient_backoff(attempt: int) -> None:
    base = 0.1 * (2 ** max(0, attempt - 1))
    jitter = random.uniform(0.0, 0.05)
    time.sleep(base + jitter)


def invoke_typed_prepare_model(
    prompt_name: PreparePromptName,
    **prompt_values: str,
) -> PrepareModelEnvelope[list[PromptCandidate]]:
    model = get_chat_model()
    messages = build_prepare_prompt(prompt_name, **prompt_values)
    response_format = get_prepare_response_format(prompt_name)
    candidate_model = _CANDIDATE_MODEL_BY_PROMPT[prompt_name]

    transient_attempts = 0
    format_attempts = 0
    total_attempt = 0

    while True:
        total_attempt += 1
        start = time.perf_counter()
        token_usage: dict[str, Any] | None = None
        error_to_raise: Exception | None = None
        try:
            content, token_usage = invoke_model(model, messages, response_format=response_format)
            payload = _parse_json_object_without_logging_content(content)
            envelope_model = PrepareModelEnvelope[list[candidate_model]]
            envelope = envelope_model.model_validate(payload)
            _log_retry_event(
                prompt_name=prompt_name,
                attempt=total_attempt,
                status="success",
                duration_seconds=time.perf_counter() - start,
                token_usage=token_usage,
                error_type=None,
            )
            return envelope
        except ModelOutputTooLongError as exc:
            format_attempts += 1
            _log_retry_event(
                prompt_name=prompt_name,
                attempt=total_attempt,
                status="format_retry",
                duration_seconds=time.perf_counter() - start,
                token_usage=token_usage,
                error_type=exc.__class__.__name__,
            )
            if format_attempts >= _MAX_FORMAT_ATTEMPTS:
                error_to_raise = ModelOutputTooLongError(f"{prompt_name} 模型输出达到长度上限")
            else:
                continue
        except ModelFormatError as exc:
            format_attempts += 1
            _log_retry_event(
                prompt_name=prompt_name,
                attempt=total_attempt,
                status="format_retry",
                duration_seconds=time.perf_counter() - start,
                token_usage=token_usage,
                error_type=exc.__class__.__name__,
            )
            if format_attempts >= _MAX_FORMAT_ATTEMPTS:
                error_to_raise = ModelFormatError(f"{prompt_name} 模型输出格式非法")
            else:
                continue
        except PydanticValidationError as exc:
            format_attempts += 1
            format_error = _sanitize_validation_error(prompt_name, exc)
            _log_retry_event(
                prompt_name=prompt_name,
                attempt=total_attempt,
                status="format_retry",
                duration_seconds=time.perf_counter() - start,
                token_usage=token_usage,
                error_type=exc.__class__.__name__,
            )
            if format_attempts >= _MAX_FORMAT_ATTEMPTS:
                error_to_raise = format_error
            else:
                continue
        except ModelTimeoutError as exc:
            transient_attempts += 1
            _log_retry_event(
                prompt_name=prompt_name,
                attempt=total_attempt,
                status="transient_retry",
                duration_seconds=time.perf_counter() - start,
                token_usage=token_usage,
                error_type=exc.__class__.__name__,
            )
            if transient_attempts >= _MAX_TRANSIENT_ATTEMPTS:
                error_to_raise = ModelTimeoutError(f"{prompt_name} 模型调用超时")
            else:
                _sleep_transient_backoff(transient_attempts)
                continue
        except Exception as exc:
            transient_attempts += 1
            _log_retry_event(
                prompt_name=prompt_name,
                attempt=total_attempt,
                status="transient_retry",
                duration_seconds=time.perf_counter() - start,
                token_usage=token_usage,
                error_type=exc.__class__.__name__,
            )
            if transient_attempts >= _MAX_TRANSIENT_ATTEMPTS:
                error_to_raise = ModelInvocationError(f"{prompt_name} 模型调用失败")
            else:
                _sleep_transient_backoff(transient_attempts)
                continue

        if error_to_raise is not None:
            raise error_to_raise
