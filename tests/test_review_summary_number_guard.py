"""归档前补强用例（2026-10-03 验收追加，tasks §6）。

1) 铁律 1「数字零生成」的服务端半覆盖抽验：总述/意见摘要中的阿拉伯数字 token
   必须能在规范化输入全文中逐字找到，否则按 D4 路径丢弃并标 `.model` 降级；
2) `route_reason.text` 非空契约：空串属未定义格，直接 422+10001 挡住。

模型层边界 mock 与 `test_review_summary_service.py` 同法，不发真实调用。
"""
import json
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.capabilities.review_summary import service as svc
from app.capabilities.review_summary.cache import clear_cache
from app.capabilities.review_summary.schemas import ReviewSummaryRequest, RouteReason
from app.main import create_app

_SUMMARY_GOOD = {
    "text": "该合同为硬件集成合同，合同总额 ¥126 万元，综合毛利率 27.7%；主要关注点集中在预付款比例。",
    "source_refs": [
        "contract_meta.contract_type",
        "contract_meta.contract_amount",
        "contract_meta.gross_margin",
    ],
}
_SUMMARY_FAKE_AMOUNT = {
    "text": "该合同为硬件集成合同，合同总额 ¥129 万元，主要关注点集中在预付款比例。",
    "source_refs": ["contract_meta.contract_amount"],
}
_SUMMARY_PCT_DRIFT = {
    "text": "该合同综合毛利率 15.5%，主要关注点集中在预付款比例。",
    "source_refs": ["contract_meta.gross_margin"],
}
_OPINION_OK = {
    "summaries": [
        {"index": 0, "summary": "认可推进：让步 3% 换续约优先权。", "source_refs": ["opinions[0]"]},
        {"index": 1, "summary": "须补充仲裁地后方可通过。", "source_refs": ["opinions[1]"]},
    ]
}
_OPINION_FAKE_PCT = {
    "summaries": [
        {"index": 0, "summary": "有条件调整：预付款须提至 25% 方可接受。", "source_refs": ["opinions[0]"]},
        {"index": 1, "summary": "须补充仲裁地后方可通过。", "source_refs": ["opinions[1]"]},
    ]
}
_OPINION_DATE_QUOTE = {
    "summaries": [
        {"index": 0, "summary": "于 2026-09-25 提交意见：让步 3%。", "source_refs": ["opinions[0]"]},
        {"index": 1, "summary": "须补充仲裁地后方可通过。", "source_refs": ["opinions[1]"]},
    ]
}


class _Stub:
    def __init__(self, *responses):
        self._responses = list(responses) or [_SUMMARY_GOOD, _OPINION_OK]
        self.calls: list[dict] = []

    def bind(self, **kwargs):
        return self

    def invoke(self, model, messages, response_format=None):
        self.calls.append({"messages": messages, "response_format": response_format})
        item = self._responses[min(len(self.calls) - 1, len(self._responses) - 1)]
        if not isinstance(item, str):
            item = json.dumps(item, ensure_ascii=False)
        return item, {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


@contextmanager
def _stub_model(*responses):
    stub = _Stub(*responses)
    with patch.object(svc, "get_chat_model", return_value=stub), patch.object(
        svc, "invoke_model", stub.invoke
    ):
        yield stub


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


def _request() -> ReviewSummaryRequest:
    return ReviewSummaryRequest.model_validate(
        {
            "contract_meta": {
                "contract_type": "硬件集成",
                "contract_amount": "¥126 万元",
                "gross_margin": "27.7%",
            },
            "route_reason": {"text": "合同总额超过 ¥100 万，触发副总经理终审"},
            "risk_register": [
                {
                    "risk_id": "RSK-001",
                    "title": "付款风险",
                    "description": "客户预付款比例 15%，低于我司标准 30%",
                }
            ],
            "opinions": [
                {
                    "node_name": "销售评审",
                    "approver_name": "张某",
                    "role": "销售",
                    "action": "pass",
                    "comment": "认可推进：让步 3% 换续约优先权。",
                    "submitted_at": "2026-09-25T14:32:00+08:00",
                },
                {
                    "node_name": "法务评审",
                    "approver_name": "陈某",
                    "role": "法务",
                    "action": "conditional",
                    "comment": "付款争议条款须补充仲裁地后方可通过。",
                },
            ],
        }
    )


# ------------------------------------------------------------ 铁律 1 数字抽验


def test_summary_with_input_numbers_is_kept():
    with _stub_model(_SUMMARY_GOOD, _OPINION_OK):
        data = svc.generate_review_summary(_request())
    assert data.review_summary.text is not None
    assert data.degraded_sections == []


def test_summary_with_fabricated_amount_is_discarded_and_assembly_survives():
    with _stub_model(_SUMMARY_FAKE_AMOUNT, _OPINION_OK):
        data = svc.generate_review_summary(_request())
    assert data.review_summary.text is None
    assert "review_summary.model" in data.degraded_sections
    # 丢弃不阻塞装配区：提级块 + 1 风险项 + 2 条意见骨架完好
    assert len(data.key_concerns) == 2
    assert len(data.opinion_details) == 2
    assert all(d.summary is not None for d in data.opinion_details)


def test_summary_with_percent_drift_is_discarded():
    with _stub_model(_SUMMARY_PCT_DRIFT, _OPINION_OK):
        data = svc.generate_review_summary(_request())
    assert data.review_summary.text is None
    assert "review_summary.model" in data.degraded_sections


def test_opinion_summary_with_fabricated_percent_discards_only_that_item():
    with _stub_model(_SUMMARY_GOOD, _OPINION_FAKE_PCT):
        data = svc.generate_review_summary(_request())
    assert data.opinion_details[0].summary is None
    assert data.opinion_details[1].summary == "须补充仲裁地后方可通过。"
    assert "opinion_details.model" in data.degraded_sections
    # 骨架字段不受影响
    assert data.opinion_details[0].action == "pass"


def test_opinion_summary_quoting_input_date_passes():
    with _stub_model(_SUMMARY_GOOD, _OPINION_DATE_QUOTE):
        data = svc.generate_review_summary(_request())
    assert data.opinion_details[0].summary is not None
    assert data.degraded_sections == []


def test_discarded_by_number_guard_is_not_cached():
    with _stub_model(_SUMMARY_FAKE_AMOUNT, _OPINION_OK) as stub:
        first = svc.generate_review_summary(_request())
        calls_after_first = len(stub.calls)
        second = svc.generate_review_summary(_request())
    assert first.review_summary.text is None
    assert calls_after_first == 2
    # 数字违规降级不落缓存：第二次仍发起模型调用（模型可能写出合格文本）
    assert len(stub.calls) == 4
    assert second.degraded_sections == first.degraded_sections or second.review_summary.text is not None


# ------------------------------------------------------- route_reason 非空契约


def test_route_reason_empty_text_rejected_by_schema():
    with pytest.raises(ValidationError):
        RouteReason.model_validate({"text": ""})


def test_route_reason_empty_text_returns_422_via_api():
    from fastapi.testclient import TestClient

    body = _request().model_dump(mode="json")
    body["route_reason"] = {"text": ""}
    with patch(
        "app.capabilities.review_summary.router.generate_review_summary"
    ) as mocked:
        r = TestClient(create_app(register_middleware=False)).post(
            "/api/v1/review-summary", json=body
        )
    assert r.status_code == 422
    assert r.json()["code"] == 10001
    mocked.assert_not_called()
