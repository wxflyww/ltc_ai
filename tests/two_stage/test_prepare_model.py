from unittest.mock import Mock, patch

import json
import logging
import pytest
from pydantic import ValidationError as PydanticValidationError

from app.capabilities.contract_review.two_stage.prepare_model import (
    HeaderPartiesCandidate,
    PrepareModelEnvelope,
    SourceGapCandidate,
    invoke_typed_prepare_model,
)
from app.core.errors import (
    ModelFormatError,
    ModelInvocationError,
    ModelOutputTooLongError,
    ModelTimeoutError,
)


def _mock_model_output(candidates: list[dict]) -> str:
    return json.dumps(
        {
            "candidates": candidates,
            "source_gaps": [],
        },
        ensure_ascii=False,
    )


def _valid_header_candidate() -> dict:
    return {
        "candidate_ref": "c1",
        "candidate_kind": "CONTRACT_NAME",
        "document_key": "main",
        "quote": "采购合同",
        "contract_name": "采购合同",
        "contract_number": None,
        "project_name": None,
        "project_number": None,
        "signing_location": None,
        "signing_date": None,
        "party_role": None,
        "party_name": None,
        "party_aliases": [],
        "mention_text": None,
    }


def test_invoke_typed_prepare_model_success():
    with patch("app.capabilities.contract_review.two_stage.prepare_model.get_chat_model", return_value=Mock()):
        with patch(
            "app.capabilities.contract_review.two_stage.prepare_model.invoke_model",
            return_value=(_mock_model_output([_valid_header_candidate()]), {"total_tokens": 9}),
        ):
            envelope = invoke_typed_prepare_model(
                prompt_name="prepare_header_parties_main",
                markdown="示例",
                scope_label="main",
                extraction_input="{}",
            )

    assert isinstance(envelope, PrepareModelEnvelope)
    assert isinstance(envelope.candidates[0], HeaderPartiesCandidate)
    assert envelope.candidates[0].candidate_ref == "c1"


def test_invoke_typed_prepare_model_uses_prompt_specific_candidate_schema():
    loose_payload = [{"candidate_ref": "c1", "quote": "证据"}]
    with patch("app.capabilities.contract_review.two_stage.prepare_model.get_chat_model", return_value=Mock()):
        with patch(
            "app.capabilities.contract_review.two_stage.prepare_model.invoke_model",
            side_effect=[
                (_mock_model_output(loose_payload), {"total_tokens": 3}),
                (_mock_model_output(loose_payload), {"total_tokens": 4}),
            ],
        ) as mocked_invoke:
            with pytest.raises(ModelFormatError):
                invoke_typed_prepare_model(
                    prompt_name="prepare_header_parties_main",
                    markdown="示例",
                    scope_label="main",
                    extraction_input="{}",
                )
    assert mocked_invoke.call_count == 2


def test_invoke_typed_prepare_model_length_output_raises_specific_error():
    with patch("app.capabilities.contract_review.two_stage.prepare_model.get_chat_model", return_value=Mock()):
        with patch(
            "app.capabilities.contract_review.two_stage.prepare_model.invoke_model",
            side_effect=ModelOutputTooLongError("finish_reason=length"),
        ) as mocked_invoke:
            with pytest.raises(ModelOutputTooLongError):
                invoke_typed_prepare_model(
                    prompt_name="prepare_header_parties_main",
                    markdown="示例",
                    scope_label="main",
                    extraction_input="{}",
                )
    assert mocked_invoke.call_count == 2


def test_invoke_typed_prepare_model_format_error_after_retry():
    with patch("app.capabilities.contract_review.two_stage.prepare_model.get_chat_model", return_value=Mock()):
        with patch(
            "app.capabilities.contract_review.two_stage.prepare_model.invoke_model",
            side_effect=[("not-json", {"total_tokens": 3}), ("still-not-json", {"total_tokens": 4})],
        ) as mocked_invoke:
            with pytest.raises(ModelFormatError):
                invoke_typed_prepare_model(
                    prompt_name="prepare_header_parties_main",
                    markdown="示例",
                    scope_label="main",
                    extraction_input="{}",
                )
    assert mocked_invoke.call_count == 2


def test_invoke_typed_prepare_model_rejects_extra_candidate_fields_after_single_fix_retry():
    candidate = _valid_header_candidate()
    candidate["unexpected"] = "forbidden"

    with patch("app.capabilities.contract_review.two_stage.prepare_model.get_chat_model", return_value=Mock()):
        with patch(
            "app.capabilities.contract_review.two_stage.prepare_model.invoke_model",
            side_effect=[
                (_mock_model_output([candidate]), {"total_tokens": 3}),
                (_mock_model_output([candidate]), {"total_tokens": 4}),
            ],
        ) as mocked_invoke:
            with pytest.raises(ModelFormatError):
                invoke_typed_prepare_model(
                    prompt_name="prepare_header_parties_main",
                    markdown="示例",
                    scope_label="main",
                    extraction_input="{}",
                )
    assert mocked_invoke.call_count == 2


def test_invoke_typed_prepare_model_transient_errors_retry_at_most_three_times():
    with patch("app.capabilities.contract_review.two_stage.prepare_model.get_chat_model", return_value=Mock()):
        with patch(
            "app.capabilities.contract_review.two_stage.prepare_model.invoke_model",
            side_effect=RuntimeError("boom"),
        ) as mocked_invoke:
            with patch("app.capabilities.contract_review.two_stage.prepare_model._sleep_transient_backoff", return_value=None):
                with pytest.raises(ModelInvocationError):
                    invoke_typed_prepare_model(
                        prompt_name="prepare_header_parties_main",
                        markdown="示例",
                        scope_label="main",
                        extraction_input="{}",
                    )
    assert mocked_invoke.call_count == 3


def test_invoke_typed_prepare_model_timeout_retries_and_keeps_timeout_error_type():
    with patch("app.capabilities.contract_review.two_stage.prepare_model.get_chat_model", return_value=Mock()):
        with patch(
            "app.capabilities.contract_review.two_stage.prepare_model.invoke_model",
            side_effect=ModelTimeoutError("timeout"),
        ) as mocked_invoke:
            with patch("app.capabilities.contract_review.two_stage.prepare_model._sleep_transient_backoff", return_value=None):
                with pytest.raises(ModelTimeoutError):
                    invoke_typed_prepare_model(
                        prompt_name="prepare_header_parties_main",
                        markdown="示例",
                        scope_label="main",
                        extraction_input="{}",
                    )
    assert mocked_invoke.call_count == 3


def test_source_gap_candidate_allows_quote_to_be_none():
    model = SourceGapCandidate(
        affected_fact_kinds=["signature"],
        message="附件表格丢列",
        quote=None,
    )

    assert model.quote is None


def test_prepare_model_envelope_rejects_duplicate_candidate_refs():
    candidate = _valid_header_candidate()

    with pytest.raises(PydanticValidationError, match="candidate_ref"):
        PrepareModelEnvelope[list[HeaderPartiesCandidate]].model_validate(
            {
                "candidates": [candidate, candidate],
                "source_gaps": [],
            }
        )


def test_sanitized_validation_error_does_not_retain_sensitive_input_context():
    payload = json.dumps(
        {
            "candidates": [
                {
                    "candidate_ref": "c1",
                    "document_key": "main",
                    "quote": "SENSITIVE-VALIDATION-INPUT-123",
                }
            ],
            "source_gaps": [],
        }
    )

    with patch("app.capabilities.contract_review.two_stage.prepare_model.get_chat_model", return_value=Mock()):
        with patch(
            "app.capabilities.contract_review.two_stage.prepare_model.invoke_model",
            side_effect=[(payload, {}), (payload, {})],
        ):
            with pytest.raises(ModelFormatError) as exc_info:
                invoke_typed_prepare_model(
                    prompt_name="prepare_header_parties_main",
                    markdown="示例",
                    scope_label="main",
                    extraction_input="{}",
                )

    assert "SENSITIVE-VALIDATION-INPUT-123" not in str(exc_info.value)
    assert exc_info.value.__context__ is None


def test_invalid_json_error_does_not_retain_sensitive_model_content():
    sensitive_content = "SENSITIVE-MODEL-CONTENT-456"

    with patch("app.capabilities.contract_review.two_stage.prepare_model.get_chat_model", return_value=Mock()):
        with patch(
            "app.capabilities.contract_review.two_stage.prepare_model.invoke_model",
            side_effect=[(sensitive_content, {}), (sensitive_content, {})],
        ):
            with pytest.raises(ModelFormatError) as exc_info:
                invoke_typed_prepare_model(
                    prompt_name="prepare_header_parties_main",
                    markdown="示例",
                    scope_label="main",
                    extraction_input="{}",
                )

    assert sensitive_content not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


@pytest.mark.parametrize(
    ("source_error", "expected_error"),
    [
        (RuntimeError("SENSITIVE-INVOCATION-ERROR-789"), ModelInvocationError),
        (ModelTimeoutError("SENSITIVE-TIMEOUT-ERROR-987"), ModelTimeoutError),
    ],
)
def test_exhausted_call_error_does_not_retain_sensitive_source_error(
    source_error,
    expected_error,
):
    with patch("app.capabilities.contract_review.two_stage.prepare_model.get_chat_model", return_value=Mock()):
        with patch(
            "app.capabilities.contract_review.two_stage.prepare_model.invoke_model",
            side_effect=source_error,
        ):
            with patch(
                "app.capabilities.contract_review.two_stage.prepare_model._sleep_transient_backoff",
                return_value=None,
            ):
                with pytest.raises(expected_error) as exc_info:
                    invoke_typed_prepare_model(
                        prompt_name="prepare_header_parties_main",
                        markdown="示例",
                        scope_label="main",
                        extraction_input="{}",
                    )

    assert "SENSITIVE-" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


# ---------------------------------------------------------------------------
# M2-SANITIZED-VALIDATION-ATTRIBUTION-01：ValidationError 只归并为稳定安全码，
# 不输出原始 loc、未知键名、取值、异常 message 或模型内容。
# 权威来源：spec「技术失败不得伪装成覆盖不足」「新旧流程和敏感数据保持隔离」。
# ---------------------------------------------------------------------------

_ATTEMPT_EVENT_MESSAGE = "prepare_model_attempt"


def _invoke_until_format_error(outputs: list[tuple[str, dict]]) -> ModelFormatError:
    with patch("app.capabilities.contract_review.two_stage.prepare_model.get_chat_model", return_value=Mock()):
        with patch(
            "app.capabilities.contract_review.two_stage.prepare_model.invoke_model",
            side_effect=outputs,
        ):
            with pytest.raises(ModelFormatError) as exc_info:
                invoke_typed_prepare_model(
                    prompt_name="prepare_header_parties_main",
                    markdown="示例",
                    scope_label="main",
                    extraction_input="{}",
                )
    return exc_info.value


def _attempt_constraint_codes(caplog) -> list[str | None]:
    return [
        getattr(record, "validation_constraint", None)
        for record in caplog.records
        if record.name == "prepare_model" and record.getMessage() == _ATTEMPT_EVENT_MESSAGE
    ]


@pytest.mark.parametrize(
    ("mutate_candidate", "expected_code"),
    [
        (lambda candidate: candidate.pop("quote"), "MISSING_REQUIRED_FIELD"),
        (lambda candidate: candidate.update(quote="   "), "BLANK_OR_TOO_SHORT"),
        (lambda candidate: candidate.update(candidate_kind="NOT_A_CANDIDATE_KIND"), "INVALID_ENUM_VALUE"),
        (lambda candidate: candidate.update(party_aliases="not-a-list"), "OTHER_SCHEMA_REJECTION"),
    ],
    ids=[
        "missing-required-field",
        "blank-or-too-short",
        "invalid-enum-value",
        "other-schema-rejection",
    ],
)
def test_validation_error_reports_stable_constraint_code(mutate_candidate, expected_code, caplog):
    candidate = _valid_header_candidate()
    mutate_candidate(candidate)
    failing_output = (_mock_model_output([candidate]), {"total_tokens": 3})

    with caplog.at_level(logging.INFO, logger="prepare_model"):
        exc = _invoke_until_format_error([failing_output, failing_output])

    assert _attempt_constraint_codes(caplog) == [expected_code, expected_code]
    assert expected_code in str(exc)


def test_validation_error_reports_duplicate_candidate_ref_constraint(caplog):
    candidate = _valid_header_candidate()
    failing_output = (_mock_model_output([candidate, candidate]), {"total_tokens": 3})

    with caplog.at_level(logging.INFO, logger="prepare_model"):
        exc = _invoke_until_format_error([failing_output, failing_output])

    assert _attempt_constraint_codes(caplog) == [
        "DUPLICATE_CANDIDATE_REF",
        "DUPLICATE_CANDIDATE_REF",
    ]
    assert "DUPLICATE_CANDIDATE_REF" in str(exc)


def test_validation_error_does_not_leak_unexpected_sensitive_field(caplog):
    sensitive_key = "SENSITIVE-EXTRA-KEY-321"
    sensitive_value = "SENSITIVE-EXTRA-VALUE-654"
    candidate = _valid_header_candidate()
    candidate[sensitive_key] = sensitive_value
    failing_output = (_mock_model_output([candidate]), {"total_tokens": 3})

    with caplog.at_level(logging.INFO, logger="prepare_model"):
        exc = _invoke_until_format_error([failing_output, failing_output])

    assert _attempt_constraint_codes(caplog) == ["UNEXPECTED_FIELD", "UNEXPECTED_FIELD"]

    observed = str(exc) + caplog.text
    assert sensitive_key not in observed
    assert sensitive_value not in observed


def test_non_validation_failure_does_not_carry_validation_constraint(caplog):
    with caplog.at_level(logging.INFO, logger="prepare_model"):
        with patch(
            "app.capabilities.contract_review.two_stage.prepare_model.get_chat_model",
            return_value=Mock(),
        ):
            with patch(
                "app.capabilities.contract_review.two_stage.prepare_model.invoke_model",
                side_effect=ModelTimeoutError("timeout"),
            ):
                with patch(
                    "app.capabilities.contract_review.two_stage.prepare_model._sleep_transient_backoff",
                    return_value=None,
                ):
                    with pytest.raises(ModelTimeoutError):
                        invoke_typed_prepare_model(
                            prompt_name="prepare_header_parties_main",
                            markdown="示例",
                            scope_label="main",
                            extraction_input="{}",
                        )

    assert _attempt_constraint_codes(caplog) == [None, None, None]
