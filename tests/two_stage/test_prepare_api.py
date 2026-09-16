from __future__ import annotations

"""Task 10 Step 1-2：Prepare JSON-only 路由的 API 契约矩阵与旧路由物理隔离。

权威来源：
- openspec/changes/contract-review-prepare-api/specs/contract-review/spec.md
  「第一阶段材料准备接口」：data 直接是 ReviewContext、无 data.review_context 包装、不提供
  multipart 入口、现有 /api/v1/contract-review/upload-md 行为不变。
- docs/superpowers/plans/2026-08-25-contract-review-prepare-api.md Task 10 Step 1-2。

RED 归因：新路由尚未注册——准备路由模块缺失时 patch 目标不可导入；路由未注册时 /prepare 返回 404。
本文件不调用真实 vLLM、真实合同系统或真实 Endpoint，Prepare 服务入口一律被替换。
"""

import httpx
import openai
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.capabilities.contract_review.schemas import CheckItem, ContractReviewData, ContractReviewRequest
from app.capabilities.contract_review.two_stage.schemas import PrepareRequest, ReviewContext
from app.core.errors import (
    ModelFormatError,
    ModelInvocationError,
    ModelOutputTooLongError,
    ModelTimeoutError,
    ValidationError,
)
from app.main import create_app
from tests.two_stage.factories import valid_context_payload, valid_prepare_request_payload

PREPARE_PATH = "/api/v1/contract-review/prepare"
LEGACY_JSON_PATH = "/api/v1/contract-review"
LEGACY_UPLOAD_PATH = "/api/v1/contract-review/upload-md"
PREPARE_SERVICE_TARGET = "app.capabilities.contract_review.two_stage.prepare_router.prepare_contract"
LEGACY_SERVICE_TARGET = "app.capabilities.contract_review.router.review_contract"

PREPARE_MODEL_CHAT_TARGET = "app.capabilities.contract_review.two_stage.prepare_model.get_chat_model"
PREPARE_MODEL_INVOKE_TARGET = "app.capabilities.contract_review.two_stage.prepare_model.invoke_model"
PREPARE_MODEL_SLEEP_TARGET = (
    "app.capabilities.contract_review.two_stage.prepare_model._sleep_transient_backoff"
)

REVIEW_CONTEXT_KEYS = (
    "schema_version",
    "source_snapshot",
    "shared_facts",
    "evidence_index",
    "preparation_issues",
    "preparation_meta",
    "context_digest",
)
FACT_DOMAINS = (
    "header",
    "parties",
    "signature",
    "amount_payment",
    "copy_terms",
    "attachment_manifest",
)


def _client(*, raise_server_exceptions: bool = True) -> TestClient:
    return TestClient(
        create_app(register_middleware=False),
        raise_server_exceptions=raise_server_exceptions,
    )


def _context() -> ReviewContext:
    return ReviewContext.model_validate(valid_context_payload())


def _legacy_data() -> ContractReviewData:
    return ContractReviewData(
        overall_result="BLOCK",
        check_time="2026-09-14T10:00:00",
        checks=[
            CheckItem(
                id="序号2",
                name="签章页完整性",
                result="FAIL",
                block_level="硬阻断",
                reason="银行账号不一致",
            )
        ],
    )


def test_prepare_route_is_registered_and_json_only():
    """空 JSON body 走统一 422/10001，说明 /prepare 已注册且只接受 JSON body。"""
    response = _client().post(PREPARE_PATH, json={})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == 10001
    assert body["data"] is None


def test_prepare_success_data_is_review_context_directly():
    with patch(PREPARE_SERVICE_TARGET, return_value=_context()) as mocked:
        response = _client().post(PREPARE_PATH, json=valid_prepare_request_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["message"] == "ok"
    assert "traceId" in body
    assert "duration_seconds" in body

    data = body["data"]
    assert set(data) == set(REVIEW_CONTEXT_KEYS)
    assert "review_context" not in data
    assert data["schema_version"] == "review-context/v1"
    assert data["context_digest"] == valid_context_payload()["context_digest"]
    assert set(data["shared_facts"]) == set(FACT_DOMAINS)

    mocked.assert_called_once()
    request = mocked.call_args.args[0]
    assert isinstance(request, PrepareRequest)
    assert request.contract_id == "C-2026-0001"
    assert request.revision_id == "V3"
    assert request.main_document.document_id == "DOC-MAIN-1"
    assert request.main_document.markdown == "# 主合同\n\n合同正文"
    assert [item.attachment_id for item in request.uploaded_attachments] == ["ATT-001"]


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code", "expected_message"),
    [
        (ValidationError("上传附件 Markdown 为空，无法准备"), 400, 10001, "上传附件 Markdown 为空，无法准备"),
        (ModelInvocationError("模型调用失败，重试已耗尽"), 500, 20001, "模型调用失败，重试已耗尽"),
        (ModelTimeoutError("模型调用超时"), 504, 20002, "模型调用超时"),
        (ModelFormatError("模型输出不符合强类型 Schema"), 500, 20003, "模型输出不符合强类型 Schema"),
        (ModelOutputTooLongError("模型输出达到长度上限"), 500, 20003, "模型输出达到长度上限"),
        (RuntimeError("未预期的内部错误"), 500, 29999, "内部错误"),
    ],
    ids=[
        "business-10001",
        "invocation-20001",
        "timeout-20002",
        "format-20003",
        "output-too-long-20003",
        "unknown-29999",
    ],
)
def test_prepare_failure_matrix_returns_null_data(error, expected_status, expected_code, expected_message):
    with patch(PREPARE_SERVICE_TARGET, side_effect=error):
        response = _client(raise_server_exceptions=False).post(
            PREPARE_PATH, json=valid_prepare_request_payload()
        )

    assert response.status_code == expected_status
    body = response.json()
    assert body["code"] == expected_code
    assert body["data"] is None
    assert body["message"] == expected_message


def test_prepare_rejects_multipart_file_upload():
    """multipart 上传不被当作 Prepare JSON 接受，也不得触达 Prepare 服务。"""
    with patch(PREPARE_SERVICE_TARGET, return_value=_context()) as mocked:
        response = _client().post(
            PREPARE_PATH,
            files={"main_document": ("main.md", "# 主合同".encode("utf-8"), "text/markdown")},
            data={"contract_id": "C-2026-0001", "revision_id": "V3"},
        )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == 10001
    assert body["data"] is None
    mocked.assert_not_called()


def test_prepare_and_legacy_routes_are_physically_isolated():
    files = [("contract_file", ("contract.md", "# 合同\n正文".encode("utf-8"), "text/markdown"))]

    with patch(PREPARE_SERVICE_TARGET, return_value=_context()) as prepare_mocked, patch(
        LEGACY_SERVICE_TARGET, return_value=_legacy_data()
    ) as legacy_mocked:
        client = _client()
        prepare_response = client.post(PREPARE_PATH, json=valid_prepare_request_payload())
        legacy_response = client.post(LEGACY_JSON_PATH, json={"contract_md": "# 合同", "attachments": []})
        upload_response = client.post(LEGACY_UPLOAD_PATH, files=files)

    assert [
        prepare_response.status_code,
        legacy_response.status_code,
        upload_response.status_code,
    ] == [200, 200, 200]
    assert [
        prepare_response.json()["code"],
        legacy_response.json()["code"],
        upload_response.json()["code"],
    ] == [0, 0, 0]

    prepare_mocked.assert_called_once()
    assert isinstance(prepare_mocked.call_args.args[0], PrepareRequest)
    assert legacy_mocked.call_count == 2
    for call in legacy_mocked.call_args_list:
        assert isinstance(call.args[0], ContractReviewRequest)

    prepare_data = prepare_response.json()["data"]
    assert set(prepare_data) == set(REVIEW_CONTEXT_KEYS)
    assert "overall_result" not in prepare_data
    assert "checks" not in prepare_data
    for response in (legacy_response, upload_response):
        assert response.json()["data"]["overall_result"] == "BLOCK"
        assert response.json()["data"]["checks"][0]["id"] == "序号2"


def test_prepare_api_connection_error_yields_invocation_failure_envelope():
    """真实上游 APIConnectionError 经 Prepare 模型边界重试耗尽后必须产出统一失败 envelope。

    链路不被替换：invoke_model（注入 APIConnectionError）→ 真实 invoke_typed_prepare_model
    三次瞬态重试 → 真实 prepare_contract → /prepare 路由 → 全局 AppError 响应链。
    只替换底层模型入口与 sleep，不替换 prepare_contract。
    """
    connection_error = openai.APIConnectionError(
        request=httpx.Request("POST", "https://llm.invalid/v1/chat/completions")
    )

    with patch(PREPARE_MODEL_CHAT_TARGET, return_value=object()), patch(
        PREPARE_MODEL_INVOKE_TARGET, side_effect=connection_error
    ) as mocked_invoke, patch(PREPARE_MODEL_SLEEP_TARGET, return_value=None):
        response = _client(raise_server_exceptions=False).post(
            PREPARE_PATH, json=valid_prepare_request_payload()
        )

    # 瞬态重试恰好三次后耗尽，才允许进入统一失败响应。
    assert mocked_invoke.call_count == 3

    assert response.status_code == 500
    body = response.json()
    assert body["code"] == 20001
    assert body["data"] is None

    assert "traceId" in body
    assert "duration_seconds" in body
    assert isinstance(body["duration_seconds"], (int, float))
    assert not isinstance(body["duration_seconds"], bool)

    # 不得返回任何部分 ReviewContext：失败响应只有统一 envelope，且不含 review context 键。
    assert set(body) == {"code", "message", "data", "traceId", "duration_seconds"}
    assert set(body).isdisjoint(REVIEW_CONTEXT_KEYS)
