from __future__ import annotations

"""Task 10 Step 3：Prepare 的普通日志与审计 sink 敏感数据保护矩阵。

权威来源：
- openspec/changes/contract-review-prepare-api/specs/contract-review/spec.md
  「新旧流程和敏感数据保持隔离」：ReviewContext 可以保留合同原文事实与证据，但普通日志和错误
  消息 SHALL NOT 回显完整号码、完整 Markdown 或证据引文；Prepare 日志允许字段仅为调用名、
  耗时、token、重试次数、状态、错误类型与 trace ID。
- docs/superpowers/plans/2026-08-25-contract-review-prepare-api.md Task 10 Step 3。

取证机制：
- TestClient 走 register_middleware=True，让既有 TraceIdMiddleware 真实产生请求日志与审计落盘；
  根 logger 的 JSON handler 输出被换到 io.StringIO，逐行 json.loads 后断言字段与内容。
- 审计 sink 通过 LTC__DEBUG__LLM_TRACE* 指向 tmp_path 打开并断言确实写出文件，
  从而证明 sink 存在且不含请求原文。
- 入口事件矩阵由真实实现发出：只补掉 documents 输入准备以便在入口之后提前中止，不 mock Service/Model；
  敏感数据与审计 sink 矩阵仍用最小代表性审计事件模拟 Service 的审计写入。本文件不改动任何产品源码。
"""

import io
import json
import logging
import pytest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.capabilities.contract_review.two_stage.schemas import ReviewContext
from app.core.config import _reset_settings
from app.core.errors import ModelInvocationError
from app.core.llm_trace_audit import add_event
from app.main import create_app
from tests.two_stage.factories import valid_context_payload, valid_prepare_request_payload

PREPARE_PATH = "/api/v1/contract-review/prepare"
PREPARE_SERVICE_TARGET = "app.capabilities.contract_review.two_stage.prepare_router.prepare_contract"
TRACE_ID = "trace-prepare-log-0001"
PREPARE_DOCUMENTS_TARGET = (
    "app.capabilities.contract_review.two_stage.prepare_service."
    "documents_module.build_document_inputs"
)
PREPARE_SERVICE_ENTER_MESSAGE = "prepare_contract_enter"
PREPARE_MODEL_ENTER_MESSAGE = "prepare_model_call_enter"

SENSITIVE_MAIN_MARKDOWN = (
    "# 采购合同 SENSITIVE-CONTRACT-MARKER\n\n"
    "甲方：某某集团有限公司（统一社会信用代码 91310000MA1FL0XXXX）\n"
    "乙方法定代表人：张三（身份证号 310101199001011234）\n"
    "收款账号：6222020200112233445 开户行：中国工商银行上海分行\n"
    "联系电话：13800138000\n"
    "签约日期：2026-09-14\n"
)
SENSITIVE_ATTACHMENT_MARKDOWN = (
    "# 附件一：技术规范书 SENSITIVE-ATTACHMENT-MARKER\n\n"
    "SENSITIVE-EVIDENCE-QUOTE\n"
)
SENSITIVE_MARKERS = (
    "SENSITIVE-CONTRACT-MARKER",
    "SENSITIVE-ATTACHMENT-MARKER",
    "SENSITIVE-EVIDENCE-QUOTE",
    "310101199001011234",
    "6222020200112233445",
    "13800138000",
    "91310000MA1FL0XXXX",
)
# 允许字段：调用名/模块、时间戳、级别、耗时、trace ID、状态；payload 只承载审计文件路径。
ALLOWED_LOG_FIELDS = {
    "timestamp",
    "level",
    "name",
    "message",
    "traceId",
    "endpoint",
    "duration_seconds",
    "llm_duration_seconds",
}


def _sensitive_request_payload() -> dict:
    payload = valid_prepare_request_payload()
    payload["main_document"]["markdown"] = SENSITIVE_MAIN_MARKDOWN
    payload["uploaded_attachments"][0]["markdown"] = SENSITIVE_ATTACHMENT_MARKDOWN
    return payload


def _open_audit_sink(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LTC__DEBUG__LLM_TRACE", "true")
    monkeypatch.setenv("LTC__DEBUG__LLM_TRACE_WRITE_HTML", "true")
    monkeypatch.setenv("LTC__DEBUG__LLM_TRACE_OUTPUT_DIR", str(tmp_path))
    _reset_settings()


def _client_with_log_capture(*, raise_server_exceptions: bool = True) -> tuple[TestClient, io.StringIO]:
    client = TestClient(
        create_app(register_middleware=True),
        raise_server_exceptions=raise_server_exceptions,
    )
    captured = io.StringIO()
    handlers = logging.getLogger().handlers
    assert handlers, "create_app 应已通过 setup_logging 配置根 logger"
    # setup_logging 重置为单一 JSON handler；pytest 只会向其追加 handler，故 [0] 即本应用 handler。
    handlers[0].setStream(captured)
    return client, captured


def _log_records(captured: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in captured.getvalue().strip().splitlines() if line.strip()]


def _audit_text(tmp_path: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(Path(tmp_path).glob("*.html")))


def test_prepare_success_log_and_audit_sink_keep_sensitive_payload_out(tmp_path, monkeypatch):
    _open_audit_sink(tmp_path, monkeypatch)
    client, captured = _client_with_log_capture()

    def _service(request):
        add_event(
            {
                "event": "prepare.model_call",
                "prompt_name": "prepare_extract",
                "status": "ok",
                "token_usage": {"prompt_tokens": 12, "completion_tokens": 3},
            }
        )
        return ReviewContext.model_validate(valid_context_payload())

    with patch(PREPARE_SERVICE_TARGET, side_effect=_service):
        response = client.post(
            PREPARE_PATH, json=_sensitive_request_payload(), headers={"X-Trace-Id": TRACE_ID}
        )

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["traceId"] == TRACE_ID

    logs = captured.getvalue()
    assert logs.strip(), "Prepare 请求应产生结构化日志"
    records = _log_records(captured)
    for record in records:
        assert set(record) <= ALLOWED_LOG_FIELDS | {"payload"}

    request_logs = [
        record
        for record in records
        if record["name"] == "middleware" and record["message"] == "request done"
    ]
    assert len(request_logs) == 1
    request_log = request_logs[0]
    assert request_log["level"] == "INFO"
    assert request_log["endpoint"] == PREPARE_PATH
    assert isinstance(request_log["duration_seconds"], (int, float))
    assert request_log["duration_seconds"] >= 0
    # 只断言字段存在：现有 middleware 在 clear_trace_id 之后写 request done，其 traceId 实测为空。
    assert "traceId" in request_log

    for marker in SENSITIVE_MARKERS:
        assert marker not in logs
        assert marker not in response.text

    audit = _audit_text(tmp_path)
    assert audit, "审计 sink 未被写入时无法证明其不含合同原文"
    assert "prepare.model_call" in audit
    assert PREPARE_PATH in audit
    assert TRACE_ID in audit
    assert "statusCode" in audit
    assert ">200<" in audit
    for marker in SENSITIVE_MARKERS:
        assert marker not in audit


def test_prepare_failure_log_and_audit_sink_keep_sensitive_payload_out(tmp_path, monkeypatch):
    _open_audit_sink(tmp_path, monkeypatch)
    client, captured = _client_with_log_capture(raise_server_exceptions=False)

    def _service(request):
        add_event(
            {
                "event": "prepare.model_call",
                "status": "error",
                "error_type": "ModelInvocationError",
            }
        )
        raise ModelInvocationError("模型调用失败，重试已耗尽")

    with patch(PREPARE_SERVICE_TARGET, side_effect=_service):
        response = client.post(
            PREPARE_PATH, json=_sensitive_request_payload(), headers={"X-Trace-Id": TRACE_ID}
        )

    assert response.status_code == 500
    body = response.json()
    assert body["code"] == 20001
    assert body["data"] is None
    assert body["message"] == "模型调用失败，重试已耗尽"

    logs = captured.getvalue()
    error_logs = [record for record in _log_records(captured) if record["name"] == "errors"]
    assert len(error_logs) == 1
    assert error_logs[0]["level"] == "ERROR"
    assert error_logs[0]["message"] == "app error: 模型调用失败，重试已耗尽"
    assert error_logs[0]["traceId"] == TRACE_ID

    for marker in SENSITIVE_MARKERS:
        assert marker not in logs
        assert marker not in response.text

    audit = _audit_text(tmp_path)
    assert audit, "审计 sink 未被写入时无法证明其不含合同原文"
    assert "ModelInvocationError" in audit
    assert "statusCode" in audit
    assert ">500<" in audit
    for marker in SENSITIVE_MARKERS:
        assert marker not in audit


# ---------------------------------------------------------------------------
# M2-OBSERVABILITY-MINIMAL-01：内部边界入口事件的定点日志契约。
# 权威来源：spec「新旧流程和敏感数据保持隔离」（Prepare 日志只记录调用名、时长、token、
# 重试和状态等非业务元数据）；playbook 2.2.1（原因不明时优先补足定位失败边界的最小证据）。
# 这些事件只证明边界是否执行，不携带任何业务内容。
# ---------------------------------------------------------------------------


def test_prepare_contract_entry_event_is_logged_before_input_preparation():
    """进入 prepare_contract 的固定入口事件必须在输入准备之前落地。"""
    client, captured = _client_with_log_capture(raise_server_exceptions=False)

    def _stop_after_entry(request):
        raise RuntimeError("stop-after-entry")

    with patch(PREPARE_DOCUMENTS_TARGET, side_effect=_stop_after_entry):
        response = client.post(
            PREPARE_PATH,
            json=valid_prepare_request_payload(),
            headers={"X-Trace-Id": TRACE_ID},
        )

    assert response.status_code == 500
    entry = [
        record
        for record in _log_records(captured)
        if record["name"] == "prepare_service"
        and record["message"] == PREPARE_SERVICE_ENTER_MESSAGE
    ]
    assert len(entry) == 1
    assert entry[0]["level"] == "INFO"
    # 入口事件必须与本请求关联：日志 traceId 应等于请求头 X-Trace-Id。
    assert entry[0]["traceId"] == TRACE_ID


def test_prepare_contract_entry_event_keeps_sensitive_payload_out():
    """入口事件只携带固定元数据，不得回显合同正文、号码或证据引文。"""
    client, captured = _client_with_log_capture(raise_server_exceptions=False)

    def _stop_after_entry(request):
        raise RuntimeError("stop-after-entry")

    with patch(PREPARE_DOCUMENTS_TARGET, side_effect=_stop_after_entry):
        client.post(
            PREPARE_PATH,
            json=_sensitive_request_payload(),
            headers={"X-Trace-Id": TRACE_ID},
        )

    entry = [
        record
        for record in _log_records(captured)
        if record["message"] == PREPARE_SERVICE_ENTER_MESSAGE
    ]
    assert entry
    for record in entry:
        assert set(record) <= ALLOWED_LOG_FIELDS | {"payload"}

    logs = captured.getvalue()
    for marker in SENSITIVE_MARKERS:
        assert marker not in logs


def test_invoke_typed_prepare_model_entry_event_is_logged_before_model_creation(monkeypatch, caplog):
    """进入 invoke_typed_prepare_model 的固定入口事件必须在创建模型之前落地。"""
    from app.capabilities.contract_review.two_stage import prepare_model as prepare_model_module

    def _no_model():
        raise RuntimeError("model-seam-stop")

    monkeypatch.setattr(prepare_model_module, "get_chat_model", _no_model)

    with caplog.at_level(logging.INFO, logger="prepare_model"):
        with pytest.raises(RuntimeError):
            prepare_model_module.invoke_typed_prepare_model("prepare_header_parties_main")

    events = [
        record
        for record in caplog.records
        if record.name == "prepare_model"
        and record.getMessage() == PREPARE_MODEL_ENTER_MESSAGE
    ]
    assert len(events) == 1
    assert events[0].prompt_name == "prepare_header_parties_main"
