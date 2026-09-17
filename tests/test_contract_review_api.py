from unittest.mock import patch

from fastapi.testclient import TestClient

from app.capabilities.contract_review.schemas import CheckItem, ContractReviewData
from app.core.errors import ModelInputTooLongError
from app.main import create_app


def _client():
    return TestClient(create_app(register_middleware=False))


def test_contract_review_success_response_contract():
    fake = ContractReviewData(
        overall_result="BLOCK",
        check_time="2026-07-07T10:00:00",
        checks=[
            CheckItem(id="序号2", name="签章页完整性", result="FAIL", block_level="硬阻断", reason="银行账号不一致"),
            CheckItem(id="序号2", name="签章页完整性", result="WARN", block_level="提示", reason="传真缺失"),
        ],
    )
    with patch("app.capabilities.contract_review.router.review_contract", return_value=fake):
        response = _client().post("/api/v1/contract-review", json={"contract_md": "# 合同", "attachments": []})
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["overall_result"] == "BLOCK"
    assert len(body["data"]["checks"]) == 2
    assert "traceId" in body
    assert "duration_seconds" in body


def test_contract_review_validation_error_returns_10001():
    response = _client().post("/api/v1/contract-review", json={"attachments": []})
    assert response.status_code == 422
    assert response.json()["code"] == 10001


def test_contract_review_context_length_error_returns_blocking_check_item():
    with patch(
        "app.capabilities.contract_review.service.run_review_pipeline",
        side_effect=ModelInputTooLongError("B-1-附件一内容过长，超过模型单次处理长度限制，请拆分该部分内容或减少单次上传内容后重试"),
    ):
        response = _client().post("/api/v1/contract-review", json={"contract_md": "# 合同", "attachments": []})

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["overall_result"] == "BLOCK"
    assert len(body["data"]["checks"]) == 1
    assert body["data"]["checks"][0]["id"] == "模型上下文长度"
    assert body["data"]["checks"][0]["block_level"] == "硬阻断"
    assert "B-1-附件一内容过长" in body["data"]["checks"][0]["reason"]


def test_contract_review_upload_md_builds_existing_request_contract():
    fake = ContractReviewData(
        overall_result="PASS",
        check_time="2026-07-09T10:00:00",
        checks=[CheckItem(id="序号1", name="合同首页完整性", result="PASS", block_level="通过")],
    )
    files = [
        ("contract_file", ("contract.md", "# 合同\n正文".encode("utf-8"), "text/markdown")),
        ("attachment_files", ("附件一.md", "附件一内容".encode("utf-8"), "text/markdown")),
        ("attachment_files", ("附件二.md", "附件二内容".encode("utf-8"), "text/markdown")),
    ]
    with patch("app.capabilities.contract_review.router.review_contract", return_value=fake) as mocked:
        response = _client().post("/api/v1/contract-review/upload-md", files=files)

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    request = mocked.call_args.args[0]
    assert request.contract_md == "# 合同\n正文"
    assert [(item.index, item.filename, item.file_type, item.text) for item in request.attachments] == [
        (1, "附件一.md", "md", "附件一内容"),
        (2, "附件二.md", "md", "附件二内容"),
    ]


def test_contract_review_upload_md_rejects_non_md_contract_file():
    files = [
        ("contract_file", ("contract.txt", "正文".encode("utf-8"), "text/plain")),
    ]
    response = _client().post("/api/v1/contract-review/upload-md", files=files)
    assert response.status_code == 400
    assert response.json()["code"] == 10001


def test_contract_review_upload_md_rejects_non_md_attachment_file():
    files = [
        ("contract_file", ("contract.md", "正文".encode("utf-8"), "text/markdown")),
        ("attachment_files", ("附件一.txt", "附件".encode("utf-8"), "text/plain")),
    ]
    response = _client().post("/api/v1/contract-review/upload-md", files=files)
    assert response.status_code == 400
    assert response.json()["code"] == 10001


def test_contract_review_upload_md_prefill_mode_routes_to_prefill():
    payload = {"mode": "prefill", "prefill_status": "ok", "prefill": {"contract_plan": []}}
    files = [("contract_file", ("contract.md", "# 合同\n正文".encode("utf-8"), "text/markdown"))]
    with patch(
        "app.capabilities.contract_review.router.run_prefill", return_value=payload
    ) as prefill_mocked, patch(
        "app.capabilities.contract_review.router.review_contract"
    ) as review_mocked:
        response = _client().post(
            "/api/v1/contract-review/upload-md",
            files=files,
            data={"mode": "prefill", "prefill_scope": "d02"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"] == payload
    assert review_mocked.called is False
    request = prefill_mocked.call_args.args[0]
    assert request.contract_md == "# 合同\n正文"
    assert request.mode == "prefill"
    assert request.prefill_scope == "d02"


def test_contract_review_upload_md_defaults_to_review_mode():
    fake = ContractReviewData(overall_result="PASS", check_time="2026-07-09T10:00:00", checks=[])
    files = [("contract_file", ("contract.md", "# 合同\n正文".encode("utf-8"), "text/markdown"))]
    with patch("app.capabilities.contract_review.router.review_contract", return_value=fake) as mocked:
        response = _client().post("/api/v1/contract-review/upload-md", files=files)

    assert response.status_code == 200
    assert response.json()["data"]["overall_result"] == "PASS"
    request = mocked.call_args.args[0]
    assert request.mode == "review"
    assert request.prefill_scope == "all"


def test_contract_review_upload_md_rejects_unknown_mode():
    files = [("contract_file", ("contract.md", "正文".encode("utf-8"), "text/markdown"))]
    response = _client().post("/api/v1/contract-review/upload-md", files=files, data={"mode": "prefil"})
    assert response.status_code == 422
    assert response.json()["code"] == 10001
