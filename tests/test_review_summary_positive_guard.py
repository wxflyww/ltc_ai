"""D16.4 代答抽验用例（2026-10-09，s05 真机第四枪抓到的新形态）。

触发事实：D16.3 措辞微调复跑后，s05 的 `overall` 写成"……**其余节点无异议**"，而那 7 个节点
只是 `comment` 为空。空意见只能证明"没写字"，证明不了"无异议"——这是替缺席者断言立场，
四道闸一条都不拦（无节点名、无数字、引用合法、本单无「不通过」故铁律 5 的禁档没开），
讽刺的是「无异议」本就是铁律 5 列出的禁用语之一。

口径：与铁律 1 数字抽验同构的**服务端确定性比对**——正面定性短语只要在任何输入原文里
都找不到，即判"无人说过这话"。扳机不看模型脸色，也不依赖 reject 是否存在（D16.2 纪律：
护栏扳机必须服务端确定性计算）。处置沿用既有两档：主题违规 = 内容违规，整条丢弃、
**不消耗重试**；`overall` 违规 = 只丢这一句，主题照采、不打标记、照常落缓存。
"""
import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from app.capabilities.review_summary import service as svc
from app.capabilities.review_summary.cache import clear_cache, get_cached, make_cache_key
from app.capabilities.review_summary.schemas import ReviewSummaryRequest

_REAL_S05 = Path("tmp/review-summary-apifox/s05_baotou_v3.json")
_PARROTING = "意见聚焦管辖地与开票口径，其余节点无异议。"
_CLEAN_OVERALL = "意见聚焦管辖地与开票口径两处。"
_THEME_A = {"text": "管辖地建议约定我司所在地。", "opinion_refs": ["opinions[0]"]}
_THEME_B = {"text": "开票须按软件产品标准名称执行。", "opinion_refs": ["opinions[1]"]}
_OPINIONS_OK = {
    "summaries": [
        {"index": 0, "summary": "建议把管辖地定在我司。", "source_refs": ["opinions[0]"]},
        {"index": 1, "summary": "要求按标准名称开票。", "source_refs": ["opinions[1]"]},
    ]
}


class _Stub:
    """模型替身：按调用顺序消费响应，耗尽后重复最后一发。"""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def bind(self, **kwargs):
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


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


def _op(node: str, comment: str, action: str = "通过") -> dict:
    return {
        "node_name": node,
        "approver_name": f"评审人{node}",
        "role": node,
        "action": action,
        "comment": comment,
        "submitted_at": None,
    }


def _request(opinions, **overrides) -> ReviewSummaryRequest:
    payload = {
        "contract_meta": {
            "contract_type": "硬件集成",
            "contract_amount": "¥126 万元",
            "gross_margin": "27.7%",
        },
        "route_reason": {"text": "合同总额超过 ¥100 万，触发副总经理终审"},
        "risk_register": [],
        "opinions": opinions,
    }
    payload.update(overrides)
    return ReviewSummaryRequest.model_validate(payload)


def _draft(overall, *themes) -> dict:
    return {"overall": overall, "themes": list(themes)}


# 两名评审人都写了实质意见，且通篇没有任何"无异议"字样——代答无从溯源
_REQUEST = lambda: _request(
    [
        _op("法务评审", "管辖地建议约定我司所在地。", "有条件通过"),
        _op("税务评审", "开票须按软件产品标准名称执行。"),
    ]
)


def test_parroting_theme_is_dropped_without_consuming_a_retry():
    """主题替缺席者断言"无异议"→ 内容违规：整条丢弃，但**不触发定向重试**（0 额外调用）。"""
    request = _REQUEST()
    bad = {"text": "其余节点无异议，仅法务提出管辖地诉求。", "opinion_refs": ["opinions[0]"]}
    with _stub_model(_draft(_CLEAN_OVERALL, bad, _THEME_B), _OPINIONS_OK) as stub:
        data = svc.generate_review_summary(request)
    assert [t.text for t in data.review_summary.themes] == [_THEME_B["text"]]
    assert "review_summary.incomplete" in data.degraded_sections
    assert len(stub.calls) == 2  # 一次总述 + 一次意见批量，没有第三次（重试只给结构违规）


def test_parroting_overall_drops_only_that_sentence_and_stays_cacheable():
    """`overall` 代答 → 只丢这一句：主题全采、不打任何降级标记、响应照常落缓存（D16.2-R7 同档）。"""
    request = _REQUEST()
    with _stub_model(_draft(_PARROTING, _THEME_A, _THEME_B), _OPINIONS_OK) as stub:
        data = svc.generate_review_summary(request)
    text = data.review_summary.text
    assert "无异议" not in text
    assert [t.text for t in data.review_summary.themes] == [_THEME_A["text"], _THEME_B["text"]]
    assert text.startswith("该合同为硬件集成合同")  # ①② 由服务端装配，与代答无关
    assert data.degraded_sections == []  # 提级块在 → key_concerns 非空；总述零标记
    assert len(stub.calls) == 2
    assert get_cached(make_cache_key(request)) is not None


def test_verbatim_quotation_of_a_real_no_objection_is_kept():
    """意见原文真写了"无异议"→ 转述它属于溯源成功，不得误伤（服务端不得惩罚模型遵守契约）。"""
    request = _request(
        [
            _op("法务评审", "对合同条款无异议，仅建议管辖地约定为我司。", "有条件通过"),
            _op("税务评审", "开票须按软件产品标准名称执行。"),
        ]
    )
    theme = {"text": "法务对条款无异议，只提管辖地诉求。", "opinion_refs": ["opinions[0]"]}
    with _stub_model(_draft(_PARROTING, theme, _THEME_B), _OPINIONS_OK) as stub:
        data = svc.generate_review_summary(request)
    assert [t.text for t in data.review_summary.themes] == [theme["text"], _THEME_B["text"]]
    assert "无异议" in data.review_summary.text
    assert data.degraded_sections == []  # 只有装配区正常，总述无降级标记 = 代答未误伤


def test_reject_scene_ban_stays_independent_from_the_corpus():
    """回归锁：存在「不通过」时，正面定性即使原文里找得到也照样违规——两道闸互不替换。"""
    request = _request(
        [
            _op("法务评审", "对管辖地安排无异议。", "不通过"),
            _op("税务评审", "开票口径不合规，不予通过。", "不通过"),
        ]
    )
    with _stub_model(_draft("各节点对管辖地安排无异议。", _THEME_A, _THEME_B), _OPINIONS_OK) as stub:
        data = svc.generate_review_summary(request)
    assert "无异议" not in data.review_summary.text
    assert len(stub.calls) == 2


def test_guard_is_not_a_number_guard():
    """反放宽锁：代答抽验管的是短语，不是数字——无数字的编造立场同样要被拦。"""
    request = _REQUEST()
    theme = {"text": "全员一致同意本合同条款。", "opinion_refs": ["opinions[0]"]}
    with _stub_model(_draft(_CLEAN_OVERALL, theme), _OPINIONS_OK) as stub:
        data = svc.generate_review_summary(request)
    assert "一致同意" not in data.review_summary.text
    assert data.review_summary.themes == []
    # 一条合法主题都不剩 → 服务端中性兜底稿：`.fallback` 而非 `.incomplete`（既有口径，非本闸新增）
    assert "review_summary.fallback" in data.degraded_sections
    assert "review_summary.incomplete" not in data.degraded_sections
    assert len(stub.calls) == 2


def test_provenance_is_comments_only_not_the_whole_payload():
    """判据只认 `comment`：风险项描述里恰好有"无异议"，不给替评审人表态的代答背书。

    数字抽验的语料是全量输入（合同里出现的数字当然合法）；代答抽验判的是"哪位评审人表过态"，
    能给它出处的只有评审人亲手写的字，所以判据比数字抽验更窄。
    """
    request = _request(
        [
            _op("法务评审", "管辖地建议约定我司所在地。", "有条件通过"),
            _op("税务评审", "开票须按软件产品标准名称执行。"),
        ],
        risk_register=[
            {
                "risk_id": "RSK-009",
                "title": "客户已确认对本方案无异议",
                "level": "低",
                "description": "客户书面回复无异议，接受现有条款。",
            }
        ],
    )
    with _stub_model(_draft(_PARROTING, _THEME_A, _THEME_B), _OPINIONS_OK) as stub:
        data = svc.generate_review_summary(request)
    assert "无异议" not in data.review_summary.text
    assert [t.text for t in data.review_summary.themes] == [_THEME_A["text"], _THEME_B["text"]]
    assert len(stub.calls) == 2  # 代答只发生在 overall：主题全采、零重试


def test_summary_prompt_forbids_speaking_for_silent_reviewers():
    """改动配套：prompt 侧写明"空意见 ≠ 无异议"，并给出唯一合法的收尾说法。"""
    request = _REQUEST()
    with _stub_model(_draft(_CLEAN_OVERALL, _THEME_A, _THEME_B), _OPINIONS_OK) as stub:
        svc.generate_review_summary(request)
    prompt = "\n".join(str(m.content) for m in stub.calls[0]["messages"])
    assert "没写字" in prompt
    assert "其余节点未填写意见" in prompt
    assert "代答禁令" in prompt


@pytest.mark.skipif(not _REAL_S05.exists(), reason="真实样例请求体不在工程内（s05 由合同系统导出）")
def test_s05_real_parroting_shape_drops_only_the_overall():
    """s05 真机第四枪回放：真实 13 条意见 + 本轮真实的代答 overall → 只丢这一句，四条主题全保。"""
    request = ReviewSummaryRequest.model_validate(json.loads(_REAL_S05.read_text(encoding="utf-8")))
    themes = [
        {"text": "管辖地建议约定我司所在地，并删除无监理方情形下的验收条款。", "opinion_refs": ["opinions[0]"]},
        {"text": "增补合同须按软件产品标准名称开票，且软件产品不得分包外采。", "opinion_refs": ["opinions[4]"]},
        {"text": "需说明增补金额变更前后利润率的变化情况。", "opinion_refs": ["opinions[1]"]},
        {"text": "请确保原盖章文件作废。", "opinion_refs": ["opinions[5]"]},
    ]
    batch = {
        "summaries": [
            {
                "index": index,
                "summary": (
                    f"第 {index} 条意见的实质诉求。"
                    if request.opinions[index].comment.strip()
                    else None
                ),
                "source_refs": (
                    [f"opinions[{index}]"] if request.opinions[index].comment.strip() else []
                ),
            }
            for index in range(len(request.opinions))
        ]
    }
    with _stub_model(_draft(_PARROTING, *themes), batch):
        data = svc.generate_review_summary(request)
    assert len(data.review_summary.themes) == 4
    assert "无异议" not in data.review_summary.text
    assert data.degraded_sections == ["key_concerns"]  # 装配区空态，与总述无关
    assert get_cached(make_cache_key(request)) is not None
