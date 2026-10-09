"""归档前补强用例（2026-10-03 验收追加，tasks §6）。

1) 铁律 1「数字零生成」的服务端半覆盖抽验：**逐主题** + overall 中的阿拉伯数字 token
   必须能在规范化输入全文中逐字找到。主题违规属**内容违规**：不扳重试，该主题直接丢弃
   （D16 / 沿用旧"内容违规不消耗重试次数"口径）；主题全被丢弃 → 弃用 AI 稿、服务端中性
   兜底稿顶上并标 `review_summary.fallback`（2026-10-08 A+B 契约，总述不得空白）；
   意见摘要违规 → 逐条丢弃、标 `opinion_details.model`；
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

_GOOD_THEME = "合同总额 ¥126 万元、综合毛利率 27.7%，关注点集中在预付款比例。"
_SUMMARY_GOOD = {
    "overall": None,
    "themes": [{"text": _GOOD_THEME, "opinion_refs": ["opinions[0]", "opinions[1]"]}],
}
_SUMMARY_FAKE_AMOUNT = {
    "overall": None,
    "themes": [
        {
            "text": "该合同为硬件集成合同，合同总额 ¥129 万元，关注点集中在预付款比例。",
            "opinion_refs": ["opinions[0]"],
        }
    ],
}
_SUMMARY_PCT_DRIFT = {
    "overall": None,
    "themes": [{"text": "该合同综合毛利率 15.5%，关注点集中在预付款比例。", "opinion_refs": ["opinions[0]"]}],
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


def _prompt_text(stub: _Stub, call_index: int) -> str:
    return "\n".join(str(m.content) for m in stub.calls[call_index]["messages"])


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
                    "action": "通过",
                    "comment": "认可推进：让步 3% 换续约优先权。",
                    "submitted_at": "2026-09-25T14:32:00+08:00",
                },
                {
                    "node_name": "法务评审",
                    "approver_name": "陈某",
                    "role": "法务",
                    "action": "有条件通过",
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


def test_summary_with_fabricated_amount_falls_back_and_assembly_survives():
    with _stub_model(_SUMMARY_FAKE_AMOUNT, _OPINION_OK):
        data = svc.generate_review_summary(_request())
    # 2026-10-08 A+B 契约：编造数字的 AI 稿弃用，总述由服务端中性兜底稿顶上
    assert data.review_summary.text is not None
    assert "129" not in data.review_summary.text
    assert "review_summary.fallback" in data.degraded_sections
    # 兜底不阻塞装配区：提级块 + 1 风险项 + 2 条意见骨架完好
    assert len(data.key_concerns) == 2
    assert len(data.opinion_details) == 2
    assert all(d.summary is not None for d in data.opinion_details)


def test_summary_with_percent_drift_falls_back():
    with _stub_model(_SUMMARY_PCT_DRIFT, _OPINION_OK):
        data = svc.generate_review_summary(_request())
    assert data.review_summary.text is not None
    assert "15.5%" not in data.review_summary.text
    assert "review_summary.fallback" in data.degraded_sections


def test_opinion_summary_with_fabricated_percent_discards_only_that_item():
    with _stub_model(_SUMMARY_GOOD, _OPINION_FAKE_PCT):
        data = svc.generate_review_summary(_request())
    assert data.opinion_details[0].summary is None
    assert data.opinion_details[1].summary == "须补充仲裁地后方可通过。"
    assert "opinion_details.model" in data.degraded_sections
    # 骨架字段不受影响
    assert data.opinion_details[0].action == "通过"


def test_opinion_summary_quoting_input_date_passes():
    with _stub_model(_SUMMARY_GOOD, _OPINION_DATE_QUOTE):
        data = svc.generate_review_summary(_request())
    assert data.opinion_details[0].summary is not None
    assert data.degraded_sections == []


def test_fallback_by_number_guard_is_not_cached():
    """数字编造属内容违规：**不扳重试**（沿用旧口径），主题全丢才落兜底稿，且兜底稿不落缓存。"""
    with _stub_model(_SUMMARY_FAKE_AMOUNT, _OPINION_OK, _SUMMARY_FAKE_AMOUNT, _OPINION_OK) as stub:
        first = svc.generate_review_summary(_request())
        calls_after_first = len(stub.calls)
        second = svc.generate_review_summary(_request())
    assert first.review_summary.text is not None
    assert "review_summary.fallback" in first.degraded_sections
    assert calls_after_first == 2  # 总述 1 次 + 意见摘要 1 次，没有为内容违规多花一发
    # 兜底稿不落缓存：第二次仍发起模型调用（模型可能写出合格文本）
    assert len(stub.calls) == 4
    assert second.degraded_sections == first.degraded_sections


# ------------------------------------------- 缺陷 C：派生注入文本的数字属于原文

_NO_DIGITS_THEME = "本次共 3 条评审意见：通过 3 条，各方均认可推进。"
_NO_DIGITS_TEXT = {
    "overall": None,
    "themes": [{"text": _NO_DIGITS_THEME, "opinion_refs": ["opinions[0]"]}],
}
_TEXT_WITH_EXTRA_DIGIT = {
    "overall": None,
    "themes": [
        {"text": "本次共 3 条评审意见，合同总额 888 万元。", "opinion_refs": ["opinions[0]"]}
    ],
}


def _digit_free_request() -> ReviewSummaryRequest:
    """请求体通篇无阿拉伯数字，唯一数字来源是服务端注入的「结论分布」注记。"""
    return ReviewSummaryRequest.model_validate(
        {
            "contract_meta": {"contract_type": "软件集成"},
            "route_reason": None,
            "risk_register": [],
            "opinions": [
                {
                    "node_name": "销售评审",
                    "approver_name": "张某",
                    "role": "销售",
                    "action": "通过",
                    "comment": "认可推进。",
                }
            ]
            * 3,
        }
    )


def test_summary_quoting_distribution_counts_is_kept():
    """模型照抄服务端给的条数（共 3 条 / 通过 3 条）必须放行：
    那是它看到的输入原文，不是幻觉（5.4 缺陷 C，s06 的 "共 11 条" 错杀）。"""
    with _stub_model(_NO_DIGITS_TEXT, {"summaries": []}) as stub:
        data = svc.generate_review_summary(_digit_free_request())
    assert _NO_DIGITS_THEME.rstrip("。") in data.review_summary.text
    assert data.review_summary.themes[0].text == _NO_DIGITS_THEME
    assert "review_summary.model" not in data.degraded_sections
    assert "review_summary.fallback" not in data.degraded_sections
    assert "共 3 条意见" in _prompt_text(stub, 0)


def test_distribution_note_digits_are_part_of_the_corpus():
    """语料口径断言：请求体 JSON 之外的注入文本也进语料，但只此一处派生数字。"""
    request = _digit_free_request()
    corpus = svc._input_number_corpus(request)
    assert "11" not in corpus  # 与本例无关的数字仍然不在语料里
    assert "3" in corpus
    assert svc._numbers_are_verifiable(_NO_DIGITS_THEME, corpus)


def test_fabricated_digit_beside_distribution_counts_still_rejected():
    """扩语料不能让护栏失效：注记里没有的 888 依然判编造，AI 稿弃用改兜底稿。"""
    with _stub_model(_TEXT_WITH_EXTRA_DIGIT, {"summaries": []}):
        data = svc.generate_review_summary(_digit_free_request())
    assert "888" not in data.review_summary.text
    assert "review_summary.fallback" in data.degraded_sections
    assert "review_summary.model" not in data.degraded_sections


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
