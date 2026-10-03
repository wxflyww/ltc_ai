"""POST /api/v1/review-summary API 契约用例（服务层 mock，不发真实模型调用）。"""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.capabilities.review_summary.schemas import (
    OpinionDetail,
    ReviewSummaryData,
    ReviewSummarySection,
    RiskConcern,
    RiskMeasure,
)
from app.core.config import _reset_settings
from app.main import create_app

_PATCH_TARGET = "app.capabilities.review_summary.router.generate_review_summary"

_VALID_BODY = {
    "contract_meta": {
        "contract_type": "硬件集成",
        "contract_amount": "¥126 万元",
        "gross_margin": "27.7%",
    },
    "route_reason": {"text": "合同总额超过 ¥100 万，按权限规则触发副总经理终审节点"},
    "risk_register": [
        {
            "risk_id": "RSK-001",
            "title": "付款风险",
            "level": "高",
            "source": "财经评审",
            "measure_type": "缓解",
            "measure_desc": "要求客户签署补充付款承诺函，并将首付款拆分为两期",
        }
    ],
    "opinions": [
        {
            "node_name": "销售评审",
            "approver_name": "张某",
            "role": "销售",
            "action": "pass",
            "comment": "认可推进。",
        },
        {
            "node_name": "法务评审",
            "approver_name": "陈某",
            "role": "法务",
            "action": "conditional",
            "comment": "付款争议解决条款约定不明确，建议补充仲裁地后方可通过。",
        },
    ],
}


def _client():
    return TestClient(create_app(register_middleware=False))


def _fake_panel() -> ReviewSummaryData:
    return ReviewSummaryData(
        review_summary=ReviewSummarySection(
            text="该合同为硬件集成合同，合同总额 ¥126 万元。",
            source_refs=["contract_meta.contract_type"],
        ),
        key_concerns=[
            RiskConcern(
                risk_id="RSK-001",
                title="付款风险",
                measure=RiskMeasure(
                    measure_type="缓解",
                    measure_desc="要求客户签署补充付款承诺函，并将首付款拆分为两期",
                ),
            )
        ],
        opinion_details=[
            OpinionDetail(
                node_name="销售评审",
                approver_name="张某",
                role="销售",
                action="pass",
                summary="认可推进。",
                source_ref="opinions[0]",
            )
        ],
        degraded_sections=[],
    )


def test_success_returns_full_panel_with_envelope():
    with patch(_PATCH_TARGET, return_value=_fake_panel()) as mocked:
        r = _client().post("/api/v1/review-summary", json=_VALID_BODY)
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    data = body["data"]
    assert set(data.keys()) == {
        "review_summary",
        "key_concerns",
        "opinion_details",
        "degraded_sections",
    }
    assert data["review_summary"]["text"] == "该合同为硬件集成合同，合同总额 ¥126 万元。"
    assert data["key_concerns"][0]["type"] == "risk"
    assert data["key_concerns"][0]["measure"]["measure_desc"] == "要求客户签署补充付款承诺函，并将首付款拆分为两期"
    assert data["opinion_details"][0]["action"] == "pass"
    assert data["degraded_sections"] == []
    assert "traceId" in body
    assert "duration_seconds" in body
    assert mocked.call_count == 1


def test_minimal_body_opinions_only_accepted():
    with patch(_PATCH_TARGET, return_value=_fake_panel()):
        r = _client().post("/api/v1/review-summary", json={"opinions": []})
    assert r.status_code == 200
    assert r.json()["code"] == 0


def test_missing_opinions_422_and_no_model_call():
    body_in = {k: v for k, v in _VALID_BODY.items() if k != "opinions"}
    with patch(_PATCH_TARGET) as mocked:
        r = _client().post("/api/v1/review-summary", json=body_in)
    assert r.status_code == 422
    payload = r.json()
    assert payload["code"] == 10001
    assert payload["data"] is None
    assert "traceId" in payload
    assert "duration_seconds" in payload
    # 参数校验必须先于任何模型调用（服务层即模型入口：未被调用 = 模型调用 0 次）
    assert not mocked.called


def test_invalid_action_422_and_no_model_call():
    bad = {**_VALID_BODY, "opinions": [{**_VALID_BODY["opinions"][0], "action": "approved"}]}
    with patch(_PATCH_TARGET) as mocked:
        r = _client().post("/api/v1/review-summary", json=bad)
    assert r.status_code == 422
    assert r.json()["code"] == 10001
    assert not mocked.called


def test_auth_shell_missing_key_401(monkeypatch):
    monkeypatch.setenv("LTC__AUTH__API_KEYS", '["test-key"]')
    _reset_settings()
    r = TestClient(create_app()).post("/api/v1/review-summary", json=_VALID_BODY)
    assert r.status_code == 401
    assert r.json()["code"] == 10002


def test_auth_shell_valid_key_reaches_service(monkeypatch):
    monkeypatch.setenv("LTC__AUTH__API_KEYS", '["test-key"]')
    _reset_settings()
    with patch(_PATCH_TARGET, return_value=_fake_panel()) as mocked:
        r = TestClient(create_app()).post(
            "/api/v1/review-summary",
            json=_VALID_BODY,
            headers={"X-API-Key": "test-key", "X-Trace-Id": "trace-review-summary-01"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["traceId"] == "trace-review-summary-01"
    assert isinstance(body["duration_seconds"], (int, float))
    assert mocked.call_count == 1
