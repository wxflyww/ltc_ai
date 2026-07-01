from app.core.errors import ErrorCode, AppError, ValidationError, AuthError, ModelInvocationError, ModelTimeoutError, ModelFormatError
from app.core.response import ApiResponse


def test_api_response_success():
    resp = ApiResponse(data={"translated_text": "hi"}, trace_id="t1", duration_seconds=0.123)
    body = resp.to_dict()
    assert body["code"] == 0
    assert body["message"] == "ok"
    assert body["data"] == {"translated_text": "hi"}
    assert body["traceId"] == "t1"
    assert body["duration_seconds"] == 0.123


def test_api_response_error():
    resp = ApiResponse(code=ErrorCode.PARAM_INVALID, message="bad", data=None,
                       trace_id="t1", duration_seconds=0.1)
    body = resp.to_dict()
    assert body["code"] == 10001
    assert body["data"] is None


def test_app_error_carries_code_and_http_status():
    err = ValidationError("text is empty")
    assert err.code == ErrorCode.PARAM_INVALID
    assert err.http_status == 400
    assert "text is empty" in err.message


def test_error_code_segments():
    assert ErrorCode.SUCCESS == 0
    assert ErrorCode.AUTH_INVALID == 10002
    assert ErrorCode.MODEL_INVOCATION == 20001
    assert ErrorCode.MODEL_TIMEOUT == 20002
    assert ErrorCode.MODEL_FORMAT == 20003
    assert ErrorCode.UNKNOWN == 29999


def test_model_errors_distinct():
    assert ModelInvocationError("x").http_status == 500
    assert ModelTimeoutError("x").http_status == 504
    assert ModelFormatError("x").http_status == 500
