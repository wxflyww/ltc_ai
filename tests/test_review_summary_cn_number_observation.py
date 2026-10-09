"""D16.5 中文数字改写：只观测、不扳闸（2026-10-09，s05 真机第三枪抓到的形态）。

触发事实：s05 主题 3 把原文的 `50万 / 48万 / 2.24% / 5.05%` 写成"五十万/四十八万/
百分之二点二四/百分之五点零五"——语义没错，但铁律 1 的"照抄不换算"被绕开，而服务端数字抽验
**结构性失明**（`_NUMBER_TOKEN` 只匹配阿拉伯数字，该主题的"语料外数字"实测为空）。真实风险
不是观感：中文数字成了一条绕过数字闸的通道，模型若把数值写错成"六十万"，闸一个字节都不会拦。

本轮口径 = **先观测后动刀**（与 G4 漏纳、`overlap_ratio` 同纪律）：prompt 写死禁令，服务端
只在观测日志里列出"输出中出现、但输入原文里找不到逐字出处的中文数字 token"，
**不丢主题、不打标记、不旁路缓存**。等真机拿到误伤分布（"第三方""第六条"这类非数值用法）
再决定要不要升闸。
"""
import json
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from app.capabilities.review_summary import service as svc
from app.capabilities.review_summary.cache import clear_cache, get_cached, make_cache_key
from app.capabilities.review_summary.schemas import ReviewSummaryRequest

_OPINIONS_OK = {
    "summaries": [
        {"index": 0, "summary": "建议把管辖地定在我司。", "source_refs": ["opinions[0]"]},
        {"index": 1, "summary": "要求按标准名称开票。", "source_refs": ["opinions[1]"]},
    ]
}
_OVERALL = "意见聚焦管辖地与开票口径两处。"
_THEME_A = {"text": "管辖地建议约定我司所在地。", "opinion_refs": ["opinions[0]"]}
# s05 真机第三枪的真实形态：原文是阿拉伯数字，输出被转写成中文数字
_THEME_CN = {
    "text": "增补金额由五十万变更为四十八万，利润率由百分之二点二四提升至百分之五点零五。",
    "opinion_refs": ["opinions[1]"],
}


class _Stub:
    def __init__(self, *responses):
        self._responses = list(responses)
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


def _op(node: str, comment: str, action: str = "通过") -> dict:
    return {"node_name": node, "approver_name": f"评审人{node}", "role": node,
            "action": action, "comment": comment, "submitted_at": None}


def _request(opinions, **overrides) -> ReviewSummaryRequest:
    payload = {
        "contract_meta": {"contract_type": "硬件集成", "contract_amount": "¥126 万元", "gross_margin": "27.7%"},
        "route_reason": {"text": "合同总额超过 ¥100 万，触发副总经理终审"},
        "risk_register": [],
        "opinions": opinions,
    }
    payload.update(overrides)
    return ReviewSummaryRequest.model_validate(payload)


def _draft(overall, *themes) -> dict:
    return {"overall": overall, "themes": list(themes)}


# 两名评审人都写了字，意见里的数字是阿拉伯写法：50 万 / 48 万 / 2.24% / 5.05%
_REQUEST = lambda: _request(
    [
        _op("法务评审", "管辖地建议约定我司所在地。", "有条件通过"),
        _op("财经复核", "增补合同由50万变更为48万，利润率由2.24%提升至5.05%。"),
    ]
)


def test_summary_prompt_forbids_rewriting_digits_into_chinese_numerals():
    """改动一：铁律 1 写明"保持原文写法"，并把本轮真实负例写进 prompt。"""
    with _stub_model(_draft(_OVERALL, _THEME_A), _OPINIONS_OK) as stub:
        svc.generate_review_summary(_REQUEST())
    prompt = "\n".join(str(m.content) for m in stub.calls[0]["messages"])
    assert "禁止转写成中文数字" in prompt
    assert "百分之二点二四" in prompt  # 负例就是 s05 真机那句
    assert "照抄不换算" in prompt  # 铁律 1 原措辞未被改写掉


def test_rewritten_chinese_numerals_are_observed_but_not_punished(caplog):
    """改动二：中文数字无出处 → 出一行观测日志，但主题照采、零标记、照常落缓存。"""
    with caplog.at_level("INFO"):
        with _stub_model(_draft(_OVERALL, _THEME_A, _THEME_CN), _OPINIONS_OK):
            data = svc.generate_review_summary(_REQUEST())
    line = [r for r in caplog.records if "中文数字" in r.getMessage()]
    assert len(line) == 1
    assert set(line[0].cn_number_tokens) >= {"五十万", "四十八万", "百分之二点二四", "百分之五点零五"}
    # 不扳闸的三件事：主题全采、没有任何降级标记、响应可缓存
    assert [t.text for t in data.review_summary.themes] == [_THEME_A["text"], _THEME_CN["text"]]
    assert data.degraded_sections == []
    assert get_cached(make_cache_key(_REQUEST())) is not None


def test_chinese_numerals_written_by_reviewers_himself_are_not_logged(caplog):
    """反噪声锁：评审人原文就写中文数字时，逐字转述不算改写，不应出观测行。"""
    request = _request(
        [
            _op("法务评审", "管辖地建议约定我司所在地。", "有条件通过"),
            _op("财经复核", "增补合同由五十万变更为四十八万。"),
        ]
    )
    theme = {"text": "增补金额由五十万变更为四十八万。", "opinion_refs": ["opinions[1]"]}
    with caplog.at_level("INFO"):
        with _stub_model(_draft(_OVERALL, theme), _OPINIONS_OK):
            svc.generate_review_summary(request)
    assert [r for r in caplog.records if "中文数字" in r.getMessage()] == []


def test_ordinary_chinese_words_are_not_number_tokens():
    """反误伤锁（观测版）：第三方 / 第六条 / 一致同意 这类非数值用法不该被当成数字 token。"""
    assert svc._CN_NUMBER_TOKEN.findall("第三方应遵守第六条约定，双方一致同意。") == []
