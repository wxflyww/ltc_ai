"""评审智能总结 service 用例（tasks.md §2）：装配区、模型接线、source_refs 校验、reject 中性化。

模型层边界统一 mock：patch service 命名空间内的 `get_chat_model` 与 `invoke_model`，
不发任何真实模型调用。缓存每个用例前后清空，避免跨用例串味。
"""
import json
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from app.capabilities.review_summary import service as svc
from app.capabilities.review_summary.cache import clear_cache
from app.capabilities.review_summary.schemas import ReviewSummaryRequest
from app.core.errors import ModelFormatError, ModelInvocationError, ModelTimeoutError

_SUMMARY_OK = {
    "text": "该合同为硬件集成合同，合同总额 ¥126 万元，综合毛利率 27.7%；主要关注点集中在预付款比例。",
    "source_refs": [
        "contract_meta.contract_type",
        "contract_meta.contract_amount",
        "contract_meta.gross_margin",
    ],
}
_OPINION_OK = {
    "summaries": [
        {"index": 0, "summary": "认可推进：让步 3% 换三年运维续约优先权。", "source_refs": ["opinions[0]"]},
        {
            "index": 1,
            "summary": "须补充仲裁地后方可通过，其余无重大法律障碍。",
            "source_refs": ["opinions[1]", "opinions[1].comment"],
        },
    ]
}


class _Stub:
    """模型替身：既充当 `get_chat_model()` 的返回值，也充当 `invoke_model` 的实现。

    `responses` 按调用顺序消费（第 1 次 = 总述，第 2 次 = 意见摘要），耗尽后重复最后一个；
    元素为 BaseException 时抛出，为 dict 时序列化成 JSON 文本。
    """

    def __init__(self, *responses):
        self._responses = list(responses) or [_SUMMARY_OK, _OPINION_OK]
        self.calls: list[dict] = []
        self.bound_kwargs: dict | None = None

    def bind(self, **kwargs):
        self.bound_kwargs = kwargs
        return self

    def invoke(self, model, messages, response_format=None):
        self.calls.append({"messages": messages, "response_format": response_format})
        item = self._responses[min(len(self.calls) - 1, len(self._responses) - 1)]
        if isinstance(item, BaseException):
            raise item
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


def _prompt_text(stub: _Stub, call_index: int) -> str:
    return "\n".join(str(m.content) for m in stub.calls[call_index]["messages"])


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


def _request(**overrides) -> ReviewSummaryRequest:
    payload = {
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
                "description": "客户预付款比例 15%，低于我司标准 30%",
                "standard_clause": "《合同签订标准》第 3.2 条：预付款比例不低于 30%",
                "potential_impact": "项目前期资金压力较大，资金占用 96 天，可能影响交付进度",
                "measure_type": "缓解",
                "measure_desc": "要求客户签署补充付款承诺函，并将首付款拆分为两期",
                "decision_type": "接受风险",
                "decision_note": "考虑客户战略价值，同意让步",
                "decision_by": "陈总",
            },
            {
                "risk_id": "RSK-003",
                "title": "法律风险",
                "level": "高",
                "source": "法务评审",
                "description": "违约责任条款不对等，对方无违约责任约定",
                "measure_type": "预防",
                "measure_desc": "与客户谈判补充对方逾期付款违约金条款",
                "decision_type": "不接受",
                "decision_by": "杨律师",
                "decision_note": "必须修改后方可签署",
            },
        ],
        "opinions": [
            {
                "node_name": "销售评审",
                "approver_name": "张某",
                "role": "销售",
                "action": "pass",
                "comment": "认可推进：让步 3% 换三年运维续约优先权，具战略意义。",
            },
            {
                "node_name": "法务评审",
                "approver_name": "陈某",
                "role": "法务",
                "action": "conditional",
                "comment": "付款争议解决条款约定不明确，建议补充仲裁地后方可通过。其余条款无重大障碍。",
            },
        ],
    }
    payload.update(overrides)
    return ReviewSummaryRequest.model_validate(payload)


# ---------------------------------------------------------------- §2.1 装配区


def test_escalation_block_is_first_and_risks_follow_input_order():
    with _stub_model():
        data = svc.generate_review_summary(_request())
    types = [c.type for c in data.key_concerns]
    assert types == ["escalation", "risk", "risk"]
    assert data.key_concerns[0].text == "合同总额超过 ¥100 万，按权限规则触发副总经理终审节点"
    assert [c.risk_id for c in data.key_concerns[1:]] == ["RSK-001", "RSK-003"]


def test_risk_register_order_is_never_rearranged():
    reversed_risks = list(reversed(_request().risk_register))
    req = _request(risk_register=[r.model_dump() for r in reversed_risks])
    with _stub_model():
        data = svc.generate_review_summary(req)
    assert [c.risk_id for c in data.key_concerns[1:]] == ["RSK-003", "RSK-001"]


def test_risk_fields_are_verbatim_including_numbers_and_clauses():
    with _stub_model():
        data = svc.generate_review_summary(_request())
    risk = data.key_concerns[1]
    assert risk.title == "付款风险"
    assert risk.level == "高"  # 原样展示，不做枚举映射
    assert risk.description == "客户预付款比例 15%，低于我司标准 30%"
    assert risk.standard_clause == "《合同签订标准》第 3.2 条：预付款比例不低于 30%"
    assert risk.potential_impact == "项目前期资金压力较大，资金占用 96 天，可能影响交付进度"
    assert risk.decision_type == "接受风险"
    assert risk.decision_by == "陈总"
    assert risk.decision_note == "考虑客户战略价值，同意让步"
    assert risk.measure.measure_type == "缓解"
    assert risk.measure.measure_desc == "要求客户签署补充付款承诺函，并将首付款拆分为两期"


def test_missing_measure_fields_render_no_measure_block():
    req = _request(
        risk_register=[{"risk_id": "RSK-009", "title": "交付风险", "level": "高"}],
    )
    with _stub_model():
        data = svc.generate_review_summary(req)
    assert data.key_concerns[1].measure is None
    assert data.degraded_sections == []


def test_opinion_details_skeleton_follows_input_order_with_source_ref():
    with _stub_model():
        data = svc.generate_review_summary(_request())
    assert [(d.node_name, d.approver_name, d.role, d.action) for d in data.opinion_details] == [
        ("销售评审", "张某", "销售", "pass"),
        ("法务评审", "陈某", "法务", "conditional"),
    ]
    assert [d.source_ref for d in data.opinion_details] == ["opinions[0]", "opinions[1]"]
    assert data.opinion_details[0].summary == "认可推进：让步 3% 换三年运维续约优先权。"


def test_assembly_is_deterministic_without_model_output():
    """装配区不受模型文本影响：两次不同模型输出下装配字段完全一致。"""
    with _stub_model():
        first = svc.generate_review_summary(_request())
    clear_cache()
    other_summary = {"text": "另一种总述写法。", "source_refs": ["contract_meta.contract_type"]}
    with _stub_model(other_summary, _OPINION_OK):
        second = svc.generate_review_summary(_request())
    assert first.key_concerns == second.key_concerns
    assert [d.model_dump(exclude={"summary"}) for d in first.opinion_details] == [
        d.model_dump(exclude={"summary"}) for d in second.opinion_details
    ]


# ---------------------------------------------------------------- §2.3 模型接线


def test_model_bound_with_thinking_disabled():
    with _stub_model() as stub:
        svc.generate_review_summary(_request())
    assert stub.bound_kwargs == {
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}
    }


def test_shared_factory_keeps_sdk_retries_disabled():
    """SDK 层 max_retries=0（llm.py 既有治理），本能力只消费不修改。"""
    from app.models.llm import get_chat_model

    assert get_chat_model().max_retries == 0


def test_batched_generation_uses_exactly_two_model_calls():
    opinions = [
        {
            "node_name": f"节点{i}",
            "approver_name": f"评审人{i}",
            "role": f"角色{i}",
            "action": "pass",
            "comment": f"第 {i} 条意见原文。",
        }
        for i in range(4)
    ]
    payload = {
        "summaries": [
            {"index": i, "summary": f"第 {i} 条摘要。", "source_refs": [f"opinions[{i}]"]}
            for i in range(4)
        ]
    }
    with _stub_model(_SUMMARY_OK, payload) as stub:
        data = svc.generate_review_summary(_request(opinions=opinions))
    assert len(stub.calls) == 2
    assert [d.summary for d in data.opinion_details] == [
        "第 0 条摘要。",
        "第 1 条摘要。",
        "第 2 条摘要。",
        "第 3 条摘要。",
    ]


def test_both_model_calls_use_json_schema_response_format():
    with _stub_model() as stub:
        svc.generate_review_summary(_request())
    for call in stub.calls:
        assert call["response_format"]["type"] == "json_schema"
        assert call["response_format"]["json_schema"]["strict"] is True


def test_summary_prompt_embeds_anti_hallucination_rules():
    with _stub_model() as stub:
        svc.generate_review_summary(_request())
    system_prompt = _prompt_text(stub, 0)
    assert "数字零生成" in system_prompt
    assert "事实单点归属" in system_prompt
    assert "source_refs" in system_prompt
    # CRM 暂缓期：总述不写客户评价
    assert "客户" in system_prompt and "评价" in system_prompt
    # AI 不出具决策建议
    assert "建议通过" in system_prompt


def test_summary_prompt_flags_reject_distribution():
    opinions = _request().opinions
    opinions[1].action = "reject"
    req = _request(opinions=[o.model_dump() for o in opinions])
    with _stub_model() as stub:
        svc.generate_review_summary(req)
    assert "存在不通过" in _prompt_text(stub, 0)


def test_opinion_prompt_carries_comment_verbatim():
    with _stub_model() as stub:
        svc.generate_review_summary(_request())
    prompt = _prompt_text(stub, 1)
    assert "付款争议解决条款约定不明确，建议补充仲裁地后方可通过。其余条款无重大障碍。" in prompt
    assert "opinions[1]" in prompt


# ------------------------------------------------------- §2.4 source_refs 校验


def test_valid_summary_refs_are_kept():
    with _stub_model():
        data = svc.generate_review_summary(_request())
    assert data.review_summary.text == _SUMMARY_OK["text"]
    assert data.review_summary.source_refs == _SUMMARY_OK["source_refs"]
    assert data.degraded_sections == []


@pytest.mark.parametrize(
    "refs",
    [
        [],  # 无引用
        ["opinions[9]"],  # 数组越界
        ["contract_meta.credit_rating"],  # 未传入的字段
        ["contract_meta.contract_type", "risk_register[7].title"],  # 部分悬空即整条丢弃
        ["not_a_path"],
        None,
    ],
)
def test_dangling_or_missing_summary_refs_discard_summary(refs):
    payload = {"text": "该合同为硬件集成合同。", "source_refs": refs}
    with _stub_model(payload, _OPINION_OK):
        data = svc.generate_review_summary(_request())
    assert data.review_summary.text is None
    assert data.review_summary.source_refs == []
    assert "review_summary.model" in data.degraded_sections


def test_risk_register_out_of_bounds_ref_is_dangling():
    payload = {"text": "该合同存在两项高风险。", "source_refs": ["risk_register[2]"]}
    with _stub_model(payload, _OPINION_OK):
        data = svc.generate_review_summary(_request())
    assert data.review_summary.text is None
    assert "review_summary.model" in data.degraded_sections


def test_absent_field_ref_is_dangling():
    """contract_meta 整组缺省时，指向 contract_meta.* 的引用悬空。"""
    payload = {"text": "该合同为硬件集成合同。", "source_refs": ["contract_meta.contract_type"]}
    req = _request(contract_meta=None)
    with _stub_model(payload, _OPINION_OK):
        data = svc.generate_review_summary(req)
    assert data.review_summary.text is None
    assert "review_summary.model" in data.degraded_sections


def test_blank_summary_text_is_discarded():
    payload = {"text": "   ", "source_refs": ["contract_meta.contract_type"]}
    with _stub_model(payload, _OPINION_OK):
        data = svc.generate_review_summary(_request())
    assert data.review_summary.text is None
    assert "review_summary.model" in data.degraded_sections


def test_discarded_summary_does_not_block_assembly():
    payload = {"text": "该合同为硬件集成合同。", "source_refs": ["opinions[42]"]}
    with _stub_model(payload, _OPINION_OK):
        data = svc.generate_review_summary(_request())
    assert data.review_summary.text is None
    assert len(data.key_concerns) == 3
    assert data.key_concerns[1].description == "客户预付款比例 15%，低于我司标准 30%"
    assert [d.summary for d in data.opinion_details] == [
        _OPINION_OK["summaries"][0]["summary"],
        _OPINION_OK["summaries"][1]["summary"],
    ]


def test_dangling_opinion_summary_discards_only_that_item():
    payload = {
        "summaries": [
            {"index": 0, "summary": "认可推进。", "source_refs": ["opinions[0]"]},
            {"index": 1, "summary": "须补充仲裁地。", "source_refs": ["opinions[5]"]},
        ]
    }
    with _stub_model(_SUMMARY_OK, payload):
        data = svc.generate_review_summary(_request())
    assert data.opinion_details[0].summary == "认可推进。"
    assert data.opinion_details[1].summary is None
    # 骨架与溯源指针仍完整（丢弃只影响 AI 摘要）
    assert data.opinion_details[1].source_ref == "opinions[1]"
    assert data.opinion_details[1].approver_name == "陈某"
    assert "opinion_details.model" in data.degraded_sections
    assert "review_summary.model" not in data.degraded_sections


def test_opinion_summary_without_refs_is_discarded():
    payload = {
        "summaries": [
            {"index": 0, "summary": "认可推进。", "source_refs": []},
            {"index": 1, "summary": "须补充仲裁地。", "source_refs": ["opinions[1]"]},
        ]
    }
    with _stub_model(_SUMMARY_OK, payload):
        data = svc.generate_review_summary(_request())
    assert data.opinion_details[0].summary is None
    assert data.opinion_details[1].summary == "须补充仲裁地。"
    assert "opinion_details.model" in data.degraded_sections


def test_opinion_item_missing_from_batch_is_discarded():
    payload = {"summaries": [{"index": 1, "summary": "须补充仲裁地。", "source_refs": ["opinions[1]"]}]}
    with _stub_model(_SUMMARY_OK, payload):
        data = svc.generate_review_summary(_request())
    assert data.opinion_details[0].summary is None
    assert data.opinion_details[1].summary == "须补充仲裁地。"
    assert "opinion_details.model" in data.degraded_sections


def test_malformed_opinion_batch_degrades_all_summaries_but_keeps_assembly():
    with _stub_model(_SUMMARY_OK, {"summaries": "not-a-list"}):
        data = svc.generate_review_summary(_request())
    assert [d.summary for d in data.opinion_details] == [None, None]
    assert "opinion_details.model" in data.degraded_sections
    assert len(data.key_concerns) == 3
    assert data.opinion_details[0].node_name == "销售评审"


# --------------------------------------------------------- §2.5 reject 中性化


def test_reject_with_positive_tone_discards_summary():
    opinions = _request().opinions
    opinions[1].action = "reject"
    req = _request(opinions=[o.model_dump() for o in opinions])
    payload = {
        "text": "该合同为硬件集成合同；各评审节点整体认可该单价值。",
        "source_refs": ["contract_meta.contract_type", "opinions[0]"],
    }
    with _stub_model(payload, _OPINION_OK):
        data = svc.generate_review_summary(req)
    assert data.review_summary.text is None
    assert "review_summary.model" in data.degraded_sections


def test_reject_with_neutral_statement_is_kept():
    opinions = _request().opinions
    opinions[1].action = "reject"
    req = _request(opinions=[o.model_dump() for o in opinions])
    payload = {
        "text": "该合同为硬件集成合同，合同总额 ¥126 万元；评审意见存在分歧，主要关注点集中在预付款比例。",
        "source_refs": ["contract_meta.contract_type", "contract_meta.contract_amount", "opinions[1]"],
    }
    with _stub_model(payload, _OPINION_OK):
        data = svc.generate_review_summary(req)
    assert data.review_summary.text == payload["text"]
    assert data.degraded_sections == []


def test_positive_tone_without_reject_is_kept():
    """中性化铁律只在存在 reject 时生效。"""
    payload = {
        "text": "该合同为硬件集成合同；各评审节点整体认可该单价值。",
        "source_refs": ["contract_meta.contract_type", "opinions[0]"],
    }
    with _stub_model(payload, _OPINION_OK):
        data = svc.generate_review_summary(_request())
    assert data.review_summary.text == payload["text"]
    assert "review_summary.model" not in data.degraded_sections


@pytest.mark.parametrize("phrase", ["一致看好", "一致通过", "充分肯定", "无异议"])
def test_reject_positive_phrase_lexicon_is_enforced(phrase):
    opinions = _request().opinions
    opinions[0].action = "reject"
    req = _request(opinions=[o.model_dump() for o in opinions])
    payload = {"text": f"该合同为硬件集成合同；评审{phrase}。", "source_refs": ["contract_meta.contract_type"]}
    with _stub_model(payload, _OPINION_OK):
        data = svc.generate_review_summary(req)
    assert data.review_summary.text is None
    assert "review_summary.model" in data.degraded_sections


def test_reject_neutralization_does_not_retry_model():
    """内容违规属"直接判失败"，不消耗解析重试次数。"""
    opinions = _request().opinions
    opinions[0].action = "reject"
    req = _request(opinions=[o.model_dump() for o in opinions])
    payload = {"text": "各评审节点整体认可该单价值。", "source_refs": ["opinions[1]"]}
    with _stub_model(payload, _OPINION_OK) as stub:
        svc.generate_review_summary(req)
    assert len(stub.calls) == 2  # 总述 1 次 + 意见摘要 1 次，无重试


# ------------------------------------------------------------ 错误码与重试


def test_parse_failure_is_retried_once_then_succeeds():
    with _stub_model("这不是 JSON", _SUMMARY_OK, _OPINION_OK) as stub:
        data = svc.generate_review_summary(_request())
    assert data.review_summary.text == _SUMMARY_OK["text"]
    assert len(stub.calls) == 3  # 总述 2 次（含 1 次解析重试）+ 意见摘要 1 次


def test_parse_failure_twice_raises_model_format_error():
    with _stub_model("这不是 JSON", "仍然不是 JSON", _OPINION_OK) as stub:
        with pytest.raises(ModelFormatError) as exc:
            svc.generate_review_summary(_request())
    assert exc.value.code == 20003
    assert len(stub.calls) == 2  # 仅重试 1 次


def test_opinion_parse_failure_twice_raises_model_format_error():
    with _stub_model(_SUMMARY_OK, "坏输出", "还是坏输出") as stub:
        with pytest.raises(ModelFormatError):
            svc.generate_review_summary(_request())
    assert len(stub.calls) == 3  # 总述 1 次 + 意见摘要 2 次


def test_model_call_failure_raises_model_invocation_error_without_retry():
    with _stub_model(RuntimeError("connection reset")) as stub:
        with pytest.raises(ModelInvocationError) as exc:
            svc.generate_review_summary(_request())
    assert exc.value.code == 20001
    assert len(stub.calls) == 1  # 调用失败不重试


def test_model_timeout_propagates_as_timeout_error():
    with _stub_model(ModelTimeoutError("read timeout")) as stub:
        with pytest.raises(ModelTimeoutError) as exc:
            svc.generate_review_summary(_request())
    assert exc.value.code == 20002
    assert len(stub.calls) == 1


def test_failed_generation_is_not_cached():
    with _stub_model(RuntimeError("boom")):
        with pytest.raises(ModelInvocationError):
            svc.generate_review_summary(_request())
    with _stub_model() as stub:
        data = svc.generate_review_summary(_request())
    assert data.review_summary.text == _SUMMARY_OK["text"]
    assert len(stub.calls) == 2  # 上次失败未落缓存，本次重新生成
