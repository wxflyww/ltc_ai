"""缓存接线用例（tasks.md §3.2）：命中不发起模型调用、任一字段变更自动失效。

cache.py 的键计算本身由 `tests/test_review_summary_cache.py` 覆盖；本文件只验
service 与 cache 的接线行为（命中短路、写入内容、失败与 AI 降级结果不落缓存）。
"""
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from app.capabilities.review_summary import service as svc
from app.capabilities.review_summary.cache import clear_cache, get_cached, make_cache_key
from app.capabilities.review_summary.schemas import ReviewSummaryRequest

from tests.test_review_summary_service import _Stub

_SUMMARY = {
    "text": "该合同为硬件集成合同，合同总额 ¥126 万元。",
    "source_refs": ["contract_meta.contract_type", "contract_meta.contract_amount"],
}
_OPINIONS = {
    "summaries": [{"index": 0, "summary": "须补充仲裁地。", "source_refs": ["opinions[0]"]}]
}


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


def _request(**overrides) -> ReviewSummaryRequest:
    payload = {
        "contract_meta": {"contract_type": "硬件集成", "contract_amount": "¥126 万元"},
        "route_reason": {"text": "触发副总经理终审"},
        "risk_register": [
            {
                "risk_id": "RSK-001",
                "title": "付款风险",
                "level": "高",
                "description": "客户预付款比例 15%，低于我司标准 30%",
                "measure_type": "缓解",
                "measure_desc": "要求客户签署补充付款承诺函",
            }
        ],
        "opinions": [
            {
                "node_name": "法务评审",
                "approver_name": "陈某",
                "role": "法务",
                "action": "conditional",
                "comment": "建议补充仲裁地后方可通过。",
            }
        ],
    }
    payload.update(overrides)
    return ReviewSummaryRequest.model_validate(payload)


def test_second_identical_request_hits_cache_without_model_call():
    with _stub_model(_SUMMARY, _OPINIONS) as stub:
        first = svc.generate_review_summary(_request())
        assert len(stub.calls) == 2
        second = svc.generate_review_summary(_request())
    assert len(stub.calls) == 2  # 命中后未新增模型调用
    assert first == second


def test_cached_payload_is_panel_data_only():
    with _stub_model(_SUMMARY, _OPINIONS):
        data = svc.generate_review_summary(_request())
    cached = get_cached(make_cache_key(_request()))
    assert cached is not None
    assert set(cached.keys()) == {
        "review_summary",
        "key_concerns",
        "opinion_details",
        "degraded_sections",
    }
    assert "traceId" not in cached and "duration_seconds" not in cached
    assert cached == data.model_dump(mode="json")


def test_comment_change_invalidates_cache():
    with _stub_model(_SUMMARY, _OPINIONS) as stub:
        svc.generate_review_summary(_request())
        changed = _request(
            opinions=[
                {
                    "node_name": "法务评审",
                    "approver_name": "陈某",
                    "role": "法务",
                    "action": "conditional",
                    "comment": "建议补充仲裁地后方可通过；另需确认违约金条款。",
                }
            ]
        )
        svc.generate_review_summary(changed)
    assert len(stub.calls) == 4


def test_risk_register_change_invalidates_cache():
    with _stub_model(_SUMMARY, _OPINIONS) as stub:
        svc.generate_review_summary(_request())
        svc.generate_review_summary(_request(risk_register=[]))
    assert len(stub.calls) == 4  # 风险项变更 → 缓存键不同，总述与摘要均重新生成


def test_added_opinion_invalidates_cache():
    extra = {
        "node_name": "财经评审",
        "approver_name": "孙某",
        "role": "财务",
        "action": "pass",
        "comment": "预算定价合理。",
    }
    with _stub_model(_SUMMARY, _OPINIONS) as stub:
        svc.generate_review_summary(_request())
        svc.generate_review_summary(
            _request(
                opinions=[
                    {
                        "node_name": "法务评审",
                        "approver_name": "陈某",
                        "role": "法务",
                        "action": "conditional",
                        "comment": "建议补充仲裁地后方可通过。",
                    },
                    extra,
                ]
            )
        )
    assert len(stub.calls) == 4


def test_route_reason_change_invalidates_cache():
    with _stub_model(_SUMMARY, _OPINIONS) as stub:
        svc.generate_review_summary(_request())
        svc.generate_review_summary(_request(route_reason=None))
    assert len(stub.calls) == 4


def test_contract_meta_change_invalidates_cache():
    with _stub_model(_SUMMARY, _OPINIONS) as stub:
        svc.generate_review_summary(_request())
        svc.generate_review_summary(_request(contract_meta={"contract_type": "软件服务"}))
    assert len(stub.calls) == 4


def test_model_failure_is_not_cached():
    with _stub_model(RuntimeError("boom")):
        with pytest.raises(Exception):
            svc.generate_review_summary(_request())
    assert get_cached(make_cache_key(_request())) is None


def test_ai_degraded_result_is_not_cached():
    """总述因 source_refs 悬空被丢弃属生成质量问题，不应被钉死到缓存里。"""
    dangling = {"text": "该合同为硬件集成合同。", "source_refs": ["opinions[9]"]}
    with _stub_model(dangling, _OPINIONS) as stub:
        first = svc.generate_review_summary(_request())
    assert first.review_summary.text is None
    assert "review_summary.model" in first.degraded_sections
    assert get_cached(make_cache_key(_request())) is None
    with _stub_model(_SUMMARY, _OPINIONS) as retry:
        second = svc.generate_review_summary(_request())
    assert len(retry.calls) == 2  # 重新生成而非命中坏结果
    assert second.review_summary.text == _SUMMARY["text"]
    assert second.degraded_sections == []


def test_deterministic_empty_state_is_cached():
    """空态降级由输入决定、与模型无关，可安全缓存。"""
    req = _request(opinions=[])
    with _stub_model(_SUMMARY) as stub:
        first = svc.generate_review_summary(req)
        second = svc.generate_review_summary(req)
    assert len(stub.calls) == 1
    assert first == second
    assert "opinion_details" in first.degraded_sections


def test_cache_hit_survives_model_unavailable():
    """命中路径完全不触碰模型：即使 get_chat_model 抛错也应返回缓存。"""
    with _stub_model(_SUMMARY, _OPINIONS):
        expected = svc.generate_review_summary(_request())
    with patch.object(svc, "get_chat_model", side_effect=RuntimeError("模型不可用")):
        assert svc.generate_review_summary(_request()) == expected
