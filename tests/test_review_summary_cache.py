"""规范化输入 hash 缓存单元用例（确定性逻辑，零模型参与）。"""
import pytest

from app.capabilities.review_summary.cache import (
    clear_cache,
    get_cached,
    make_cache_key,
    set_cached,
)
from app.capabilities.review_summary.schemas import ReviewSummaryRequest

_OPINION_A = {
    "node_name": "销售评审",
    "approver_name": "张某",
    "role": "销售",
    "action": "通过",
    "comment": "认可推进。",
}
_OPINION_B = {
    "node_name": "法务评审",
    "approver_name": "陈某",
    "role": "法务",
    "action": "有条件通过",
    "comment": "需补充仲裁地。",
}


def _request(opinions=None, **kwargs) -> ReviewSummaryRequest:
    payload = {"opinions": opinions if opinions is not None else [_OPINION_A, _OPINION_B]}
    payload.update(kwargs)
    return ReviewSummaryRequest.model_validate(payload)


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


def test_same_input_same_key():
    assert make_cache_key(_request()) == make_cache_key(_request())


def test_comment_change_invalidates_key():
    changed = [_OPINION_A, {**_OPINION_B, "comment": "需补充仲裁地"}]
    assert make_cache_key(_request()) != make_cache_key(_request(changed))


def test_opinion_added_invalidates_key():
    assert make_cache_key(_request([_OPINION_A])) != make_cache_key(_request([_OPINION_A, _OPINION_B]))


def test_risk_register_change_invalidates_key():
    with_risk = _request(risk_register=[{"risk_id": "RSK-001", "title": "付款风险"}])
    assert make_cache_key(_request()) != make_cache_key(with_risk)


def test_contract_meta_change_invalidates_key():
    enriched = _request(contract_meta={"contract_type": "硬件集成"})
    assert make_cache_key(_request()) != make_cache_key(enriched)


def test_array_order_participates_in_key():
    assert make_cache_key(_request([_OPINION_A, _OPINION_B])) != make_cache_key(
        _request([_OPINION_B, _OPINION_A])
    )


def test_omitted_vs_explicit_null_normalized_identically():
    omitted = ReviewSummaryRequest.model_validate({"opinions": []})
    explicit = ReviewSummaryRequest.model_validate(
        {"contract_meta": None, "route_reason": None, "risk_register": [], "opinions": []}
    )
    assert make_cache_key(omitted) == make_cache_key(explicit)


def test_get_set_clear_roundtrip():
    key = make_cache_key(_request())
    assert get_cached(key) is None
    set_cached(key, {"review_summary": {"text": "x"}})
    assert get_cached(key) == {"review_summary": {"text": "x"}}
    clear_cache()
    assert get_cached(key) is None
