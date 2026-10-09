"""空态矩阵用例（tasks.md §3.1）：设计文档 §5.1 六行逐行落地。

其中两行是「非降级 SHALL 为空数组」的负向断言（仅 route_reason 缺、contract_meta 部分字段缺、
风险项缺 measure_*/decision_*），必须显式断言 `degraded_sections == []`，避免把正常态误标降级。
"""
import json
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from app.capabilities.review_summary import service as svc
from app.capabilities.review_summary.cache import clear_cache
from app.capabilities.review_summary.schemas import ReviewSummaryRequest

from tests.test_review_summary_service import _Stub  # 复用同一模型替身

_THEME_TEXT = "须补充仲裁地后方可通过。"
_NORMAL_SUMMARY = {
    "overall": "关注点集中在付款与争议条款两处。",
    "themes": [{"text": _THEME_TEXT, "opinion_refs": ["opinions[0]"]}],
}
# 无有字意见时模型本就没题材可写：这一发交白卷（themes=[]），服务端只装配 ①②。
_FACT_ONLY_SUMMARY = {"overall": None, "themes": []}


@contextmanager
def _stub_model(*responses):
    stub = _Stub(*responses)
    with patch.object(svc, "get_chat_model", return_value=stub), patch.object(
        svc, "invoke_model", stub.invoke
    ):
        yield stub


def _prompt_text(stub, call_index: int = 0) -> str:
    return "\n".join(str(m.content) for m in stub.calls[call_index]["messages"])


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


_ONE_OPINION = [
    {
        "node_name": "法务评审",
        "approver_name": "陈某",
        "role": "法务",
        "action": "有条件通过",
        "comment": "建议补充仲裁地后方可通过。",
    }
]
_ONE_OPINION_SUMMARY = {
    "summaries": [{"index": 0, "summary": "须补充仲裁地。", "source_refs": ["opinions[0]"]}]
}
_ONE_RISK = [
    {
        "risk_id": "RSK-001",
        "title": "付款风险",
        "level": "高",
        "source": "财经评审",
        "description": "客户预付款比例 15%，低于我司标准 30%",
        "standard_clause": "《合同签订标准》第 3.2 条：预付款比例不低于 30%",
        "potential_impact": "资金占用 96 天",
        "measure_type": "缓解",
        "measure_desc": "要求客户签署补充付款承诺函",
        "decision_type": "接受风险",
        "decision_by": "陈总",
        "decision_note": "考虑客户战略价值，同意让步",
    }
]


def _request(**overrides) -> ReviewSummaryRequest:
    payload = {
        "contract_meta": {"contract_type": "硬件集成", "contract_amount": "¥126 万元"},
        "risk_register": _ONE_RISK,
        "opinions": _ONE_OPINION,
    }
    payload.update(overrides)
    return ReviewSummaryRequest.model_validate(payload)


# ------------------------------------------------- 行 1：无风险项且无提级原因


def test_row1_no_risk_no_route_reason_marks_key_concerns():
    req = _request(risk_register=[], route_reason=None)
    with _stub_model(_NORMAL_SUMMARY, _ONE_OPINION_SUMMARY):
        data = svc.generate_review_summary(req)
    assert data.key_concerns == []
    assert "key_concerns" in data.degraded_sections


def test_row1_only_route_reason_absent_with_risks_is_not_degraded():
    """行 2：仅 route_reason 缺 → 非降级，degraded_sections SHALL 为空数组。"""
    req = _request(route_reason=None)
    with _stub_model(_NORMAL_SUMMARY, _ONE_OPINION_SUMMARY):
        data = svc.generate_review_summary(req)
    assert [c.type for c in data.key_concerns] == ["risk"]
    assert data.degraded_sections == []


def test_route_reason_present_is_not_degraded():
    req = _request(route_reason={"text": "合同总额超过 ¥100 万，触发副总经理终审"})
    with _stub_model(_NORMAL_SUMMARY, _ONE_OPINION_SUMMARY):
        data = svc.generate_review_summary(req)
    assert [c.type for c in data.key_concerns] == ["escalation", "risk"]
    assert data.degraded_sections == []


# ------------------------------------------- 行 3：contract_meta 部分字段缺


def test_row3_partial_contract_meta_is_not_degraded():
    """负向断言：缺位不补不问，且 SHALL NOT 标记降级。"""
    req = _request(contract_meta={"contract_type": "硬件集成"})
    with _stub_model(_NORMAL_SUMMARY, _ONE_OPINION_SUMMARY) as stub:
        data = svc.generate_review_summary(req)
    assert data.degraded_sections == []
    prompt = _prompt_text(stub)
    assert "硬件集成" in prompt
    # 未传入的字段不进入可用引用路径清单
    assert "contract_meta.gross_margin" not in prompt


def test_contract_meta_wholly_absent_is_not_degraded():
    req = _request(contract_meta=None)
    with _stub_model(_NORMAL_SUMMARY, _ONE_OPINION_SUMMARY):
        data = svc.generate_review_summary(req)
    assert data.degraded_sections == []
    # ①合同要素句整段缺位，装配只从结论分布句起头
    assert "该合同为硬件集成" not in data.review_summary.text
    assert _THEME_TEXT.rstrip("。") in data.review_summary.text


# --------------------------------------------------- 行 4：opinions 为空数组


def test_row4_empty_opinions_marks_both_sections():
    req = _request(opinions=[])
    with _stub_model(_FACT_ONLY_SUMMARY) as stub:
        data = svc.generate_review_summary(req)
    assert data.opinion_details == []
    assert "opinion_details" in data.degraded_sections
    assert "review_summary.opinions" in data.degraded_sections
    # 没有有字意见 → 总述与摘要两处都不触模型（D16：①②本就确定性）
    assert len(stub.calls) == 0


def test_row4_without_opinions_assembles_only_the_server_sentences():
    """行 4 的 D16 形态：①合同要素句 + ②结论分布句照常返回，themes 为空、零模型调用。"""
    req = _request(opinions=[])
    with _stub_model(_FACT_ONLY_SUMMARY) as stub:
        data = svc.generate_review_summary(req)
    assert stub.calls == []
    text = data.review_summary.text
    assert text is not None
    assert text.startswith("该合同为硬件集成合同，合同总额 ¥126 万元。")
    assert data.review_summary.themes == []
    assert data.review_summary.source_refs == [
        "contract_meta.contract_type",
        "contract_meta.contract_amount",
    ]
    assert "review_summary.fallback" not in data.degraded_sections


def test_row4_empty_opinions_is_not_a_param_error():
    req = _request(opinions=[])
    with _stub_model(_FACT_ONLY_SUMMARY):
        data = svc.generate_review_summary(req)
    assert data.review_summary is not None
    assert data.key_concerns  # 装配区照常返回


# --------------------------------------- 行 5 / 行 6：风险项缺 measure_/decision_


def test_row5_risk_without_measure_is_not_degraded():
    risk = {k: v for k, v in _ONE_RISK[0].items() if not k.startswith("measure_")}
    req = _request(risk_register=[risk])
    with _stub_model(_NORMAL_SUMMARY, _ONE_OPINION_SUMMARY):
        data = svc.generate_review_summary(req)
    assert data.key_concerns[0].measure is None
    assert data.degraded_sections == []


def test_row5_partial_measure_fields_still_render_measure_block():
    risk = {**_ONE_RISK[0], "measure_type": None}
    req = _request(risk_register=[risk])
    with _stub_model(_NORMAL_SUMMARY, _ONE_OPINION_SUMMARY):
        data = svc.generate_review_summary(req)
    assert data.key_concerns[0].measure.measure_type is None
    assert data.key_concerns[0].measure.measure_desc == "要求客户签署补充付款承诺函"
    assert data.degraded_sections == []


def test_row6_risk_without_decision_fields_is_not_degraded():
    risk = {k: v for k, v in _ONE_RISK[0].items() if not k.startswith("decision_")}
    req = _request(risk_register=[risk])
    with _stub_model(_NORMAL_SUMMARY, _ONE_OPINION_SUMMARY):
        data = svc.generate_review_summary(req)
    concern = data.key_concerns[0]
    assert concern.decision_type is None
    assert concern.decision_by is None
    assert concern.decision_note is None
    assert data.degraded_sections == []


# ------------------------------------------------------------------ 综合与边界


def test_normal_request_has_empty_degraded_sections():
    req = _request(route_reason={"text": "触发副总经理终审"})
    with _stub_model(_NORMAL_SUMMARY, _ONE_OPINION_SUMMARY):
        data = svc.generate_review_summary(req)
    assert data.degraded_sections == []


def test_degraded_sections_has_no_duplicates_and_stable_order():
    req = _request(risk_register=[], route_reason=None, opinions=[])
    with _stub_model(_FACT_ONLY_SUMMARY):
        data = svc.generate_review_summary(req)
    assert data.degraded_sections == ["key_concerns", "opinion_details", "review_summary.opinions"]
    assert len(set(data.degraded_sections)) == len(data.degraded_sections)


def test_nothing_to_summarize_skips_model_entirely():
    """无 contract_meta、无 opinions → 无可溯源事实，不发起模型调用（实现收口）。"""
    req = ReviewSummaryRequest.model_validate({"opinions": []})
    with _stub_model() as stub:
        data = svc.generate_review_summary(req)
    assert stub.calls == []
    assert data.review_summary.text is None
    assert data.review_summary.source_refs == []
    assert data.opinion_details == []
    assert data.key_concerns == []
    assert data.degraded_sections == ["key_concerns", "opinion_details", "review_summary.opinions"]
    # 未发生模型失败 → SHALL NOT 打 model 降级标
    assert "review_summary.model" not in data.degraded_sections


def test_meta_absent_but_opinions_present_still_generates():
    req = _request(contract_meta=None)
    with _stub_model(_NORMAL_SUMMARY, _ONE_OPINION_SUMMARY) as stub:
        data = svc.generate_review_summary(req)
    assert len(stub.calls) == 2  # 总述主题 1 次 + 意见摘要 1 次，无违规重试
    assert _THEME_TEXT.rstrip("。") in data.review_summary.text
    assert data.review_summary.themes[0].opinion_refs == ["opinions[0]"]


def test_panel_always_has_four_blocks_even_in_full_empty_state():
    req = ReviewSummaryRequest.model_validate({"opinions": []})
    with _stub_model():
        data = svc.generate_review_summary(req)
    dumped = json.loads(data.model_dump_json())
    assert set(dumped.keys()) == {
        "review_summary",
        "key_concerns",
        "opinion_details",
        "degraded_sections",
    }
