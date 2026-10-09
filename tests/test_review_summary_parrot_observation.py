"""D16.6 代答变体的观测档（2026-10-09，s05 真机第四枪抓到的漏判）。

触发事实：D16.4 的代答档判据是"固定禁用语表逐字比对"，而 s05 第四枪把代答写成
"其余节点**无实质异议**"——"无异议"三个字被"实质"插开，子串匹配零命中，整句放行。
离线实测 `_unsupported_positive_phrases` 对它返回空列表。这是代答档的第一个真实漏判，
也是 prompt-only 约束第五次被真机绕过。

本轮口径（用户拍板"先观测不扳闸"）：不放宽判据、不动禁用语表，只加一行观测日志
`review-summary 代答观测`，把"集体指代 + 立场断言"的片段列出来；**不丢主题、不丢 overall、
不打标记、不旁路缓存**。拿一轮真实分布再决定正则族口径——现在扳闸会连带把
"其他部门无意见""均未通过会签"这类合法说法一起扫进来，误伤面没有数据支撑。

噪声纪律：prompt 已给出唯一合法句式"其余节点未填写意见"，它是**对输入事实的陈述**而不是
立场断言，所以必须被白名单放过——否则观测行天天刷屏，没人再看。
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
_THEME_A = {"text": "管辖地建议约定我司所在地。", "opinion_refs": ["opinions[0]"]}
_THEME_B = {"text": "开票须按软件产品标准名称执行。", "opinion_refs": ["opinions[1]"]}
# s05 第四枪的真实形态：代答换了说法，固定禁用语表抓不到
_PARROT = "意见聚焦管辖权与开票合规，其余节点无实质异议。"
_LEGAL = "意见聚焦管辖权与开票合规，其余节点未填写意见。"


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


def _request(opinions) -> ReviewSummaryRequest:
    return ReviewSummaryRequest.model_validate({
        "contract_meta": {"contract_type": "硬件集成", "contract_amount": "¥126 万元", "gross_margin": "27.7%"},
        "route_reason": {"text": "合同总额超过 ¥100 万，触发副总经理终审"},
        "risk_register": [],
        "opinions": opinions,
    })


def _draft(overall, *themes) -> dict:
    return {"overall": overall, "themes": list(themes)}


# 两名评审人都写了字，通篇没有任何"无异议/分歧"类表态（真实单子里"其余节点"指的是
# comment 为空的节点，这里用最小请求体复现漏判形状即可）
_REQUEST = lambda: _request([
    _op("法务评审", "管辖地建议约定我司所在地。", "有条件通过"),
    _op("税务评审", "开票须按软件产品标准名称执行。"),
])


def test_parrot_variant_is_observed_but_not_punished(caplog):
    """"无实质异议"类变体：出观测行，但固定词表档不扳——主题与 overall 全留、零标记、可缓存。"""
    with caplog.at_level("INFO"):
        with _stub_model(_draft(_PARROT, _THEME_A, _THEME_B), _OPINIONS_OK) as stub:
            data = svc.generate_review_summary(_REQUEST())
    line = [r for r in caplog.records if "代答观测" in r.getMessage()]
    assert len(line) == 1
    assert any("无实质异议" in phrase for phrase in line[0].parrot_phrases)
    # 不扳闸的四件事
    assert svc._unsupported_positive_phrases(_PARROT, _REQUEST()) == []  # 本轮已知漏判，如实钉住
    assert [t.text for t in data.review_summary.themes] == [_THEME_A["text"], _THEME_B["text"]]
    assert _PARROT[:20] in data.review_summary.text  # overall 也没被丢
    assert data.degraded_sections == []
    assert len(stub.calls) == 2
    assert get_cached(make_cache_key(_REQUEST())) is not None


def test_sanctioned_wording_is_not_logged(caplog):
    """反噪声锁：prompt 给的唯一合法句式"其余节点未填写意见"是对事实的陈述，不该进观测清单。"""
    with caplog.at_level("INFO"):
        with _stub_model(_draft(_LEGAL, _THEME_A, _THEME_B), _OPINIONS_OK):
            svc.generate_review_summary(_REQUEST())
    assert [r for r in caplog.records if "代答观测" in r.getMessage()] == []


def test_no_collective_reference_means_no_line(caplog):
    """反误伤锁：没有集体指代的正常 overall 不该出观测行。"""
    with caplog.at_level("INFO"):
        with _stub_model(_draft("意见聚焦管辖地与开票口径两处。", _THEME_A, _THEME_B), _OPINIONS_OK):
            svc.generate_review_summary(_REQUEST())
    assert [r for r in caplog.records if "代答观测" in r.getMessage()] == []


def test_theme_level_parrot_variant_is_also_observed(caplog):
    """观测面与代答档同宽：主题句里的同类写法同样进清单（仍然不扳闸）。"""
    theme = {"text": "其余节点无重大分歧，仅法务提管辖地。", "opinion_refs": ["opinions[0]"]}
    with caplog.at_level("INFO"):
        with _stub_model(_draft(_LEGAL, theme, _THEME_B), _OPINIONS_OK):
            data = svc.generate_review_summary(_REQUEST())
    line = [r for r in caplog.records if "代答观测" in r.getMessage()]
    assert len(line) == 1
    assert any("无重大分歧" in phrase for phrase in line[0].parrot_phrases)
    assert len(data.review_summary.themes) == 2


def test_collective_wording_written_by_a_reviewer_is_not_logged(caplog):
    """反误伤锁：判据只认评审人亲手写的字——有人原话这么写，逐字转述不算代答（与 D16.4 同边界）。"""
    opinions = [
        _op("法务评审", "管辖地建议约定我司所在地。", "有条件通过"),
        _op("税务评审", "其余节点无实质异议，开票须按标准名称执行。"),
    ]
    with caplog.at_level("INFO"):
        with _stub_model(_draft(_PARROT, _THEME_A, _THEME_B), _OPINIONS_OK):
            svc.generate_review_summary(_request(opinions))
    assert [r for r in caplog.records if "代答观测" in r.getMessage()] == []
