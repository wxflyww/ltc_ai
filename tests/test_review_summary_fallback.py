"""总述"永远有字"契约（2026-10-08 用户拍板 A+B，D16 后落到主题粒度）。

背景：5.4 真实联调中总述被误杀两次（缺陷 A 引用清单、缺陷 C 数字语料），而总述是本面板
最重要的字段——核心字段被次要校验清零不可接受。改为两层保障：

- **A 逐条剔除**：非法的那几条 `opinion_refs` 剔掉，主题还剩 ≥1 条引用就照常采信
  （D16.1-R3：归属变窄不变假）；
- **B 服务端中性兜底**：AI 稿仍不可用时（主题指针全部失效 / 形状失守 / 空文本 /
  编造数字 / 「不通过」却正面定性把主题全丢），用服务端自己算得出的事实拼一句中性总述，
  标记 `review_summary.fallback`，且**不写缓存**（下次仍给 AI 稿机会）。

安全性质不变：违规内容一律不展示，只是不再出现空白总述。
模型层边界统一 mock。
"""
import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from app.capabilities.review_summary import service as svc
from app.capabilities.review_summary.cache import clear_cache, get_cached, make_cache_key
from app.capabilities.review_summary.schemas import ReviewSummaryRequest

_SUMMARY_OK = {
    "overall": "评审意见集中在管辖地约定与质保期表述。",
    "themes": [{"text": "建议管辖地约定我司所在地。", "opinion_refs": ["opinions[0]"]}],
}
_OPINION_OK = {"summaries": [{"index": 0, "summary": "建议管辖地约定我司所在地。", "source_refs": ["opinions[0]"]}]}


class _Stub:
    def __init__(self, *responses):
        self._responses = list(responses) or [_SUMMARY_OK, _OPINION_OK]
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


def _request(actions=("不通过", "通过"), comments=("要求提高预付款比例。", ""), with_risk=False):
    opinions = [
        {
            "node_name": f"节点{k}",
            "approver_name": f"评审人{k}",
            "role": f"节点{k}",
            "action": action,
            "comment": comments[k] if k < len(comments) else "",
            "submitted_at": None,
        }
        for k, action in enumerate(actions)
    ]
    body = {
        "contract_meta": {
            "contract_type": "软件集成",
            "contract_amount": "14480000 CNY",
            "gross_margin": "5.05%",
        },
        "route_reason": None,
        "risk_register": (
            [{"risk_id": "RSK-1", "title": "预付款比例偏低", "level": "高"}] if with_risk else []
        ),
        "opinions": opinions,
    }
    return ReviewSummaryRequest.model_validate(body)


def _summary_of(refs=None, text=None):
    """旧 A 契约的形状翻新：把"整段引用清单"表达成"一条主题的 opinion_refs"。"""
    theme_text = text if text is not None else "建议管辖地约定我司所在地。"
    if theme_text is None:
        return {"overall": None, "themes": []}
    return {"overall": None, "themes": [{"text": theme_text, "opinion_refs": refs if refs is not None else []}]}


# ------------------------------------------------------------------ A：引用剔除


def test_partially_invalid_refs_are_pruned_and_ai_text_survives():
    """混进一条清单外路径时只剔那一条 ref，主题与其余合法引用照常返回。"""
    payload = _summary_of(refs=["opinions[0].action_label", "opinions[0]"])
    with _stub_model(payload, _OPINION_OK):
        data = svc.generate_review_summary(_request(actions=("通过", "通过")))
    assert "建议管辖地约定我司所在地" in data.review_summary.text
    assert data.review_summary.themes[0].opinion_refs == ["opinions[0]"]
    assert "opinions[0].action_label" not in data.review_summary.source_refs
    assert "review_summary.model" not in data.degraded_sections
    assert "review_summary.fallback" not in data.degraded_sections
    assert "review_summary.incomplete" not in data.degraded_sections


def test_no_valid_ref_left_falls_back_to_server_template():
    """主题指针被剔光：不再置空，改用服务端中性兜底稿并打 fallback 标记。"""
    payload = _summary_of(refs=["opinions[99]", "contract_meta.not_a_field"])
    with _stub_model(payload, _OPINION_OK):
        data = svc.generate_review_summary(_request())
    text = data.review_summary.text
    assert text is not None
    assert "软件集成" in text and "14480000 CNY" in text
    assert "共 2 条意见" in text and "不通过 1 条" in text
    assert data.review_summary.themes == []
    assert data.review_summary.source_refs
    assert "review_summary.fallback" in data.degraded_sections


# ------------------------------------------------------- B：四条失败路径都有兜底


@pytest.mark.parametrize(
    "payload",
    [
        _summary_of(refs=["opinions[0]"], text="该合同总额 129 万元。"),  # 编造数字
        _summary_of(refs=[]),  # 无引用
        {"overall": None, "themes": []},  # 模型放弃
        _summary_of(refs=["opinions[0]"], text="  "),  # 空串
    ],
    ids=["fabricated_number", "no_refs", "null_themes", "blank_text"],
)
def test_ai_summary_failures_fall_back_instead_of_blanking(payload):
    with _stub_model(payload, _OPINION_OK):
        data = svc.generate_review_summary(_request(actions=("通过", "通过")))
    assert data.review_summary.text is not None
    assert "review_summary.fallback" in data.degraded_sections


def test_positive_tone_with_reject_falls_back_to_neutral_template():
    """「不通过」+ 正面定性：违规稿不展示，但面板仍拿到中性兜底稿。"""
    payload = _summary_of(
        refs=["opinions[0]"], text="各评审节点整体认可该单价值。"
    )
    with _stub_model(payload, _OPINION_OK):
        data = svc.generate_review_summary(_request(actions=("不通过", "通过")))
    assert "整体认可" not in data.review_summary.text
    assert "review_summary.fallback" in data.degraded_sections


def test_fallback_template_is_neutral_even_with_reject():
    """兜底稿本身不得含任何正面定性词。"""
    payload = _summary_of(refs=[])
    with _stub_model(payload, _OPINION_OK):
        data = svc.generate_review_summary(_request(actions=("不通过", "有条件通过", "通过")))
    text = data.review_summary.text
    assert not svc._has_positive_tone(text)
    assert "不通过 1 条" in text


def test_fallback_template_passes_its_own_guards():
    """兜底稿必须自证清白：数字全在语料、引用全在清单——否则等于自己造幻觉。

    I2 收口：兜底稿不再提风险项标题——总述只承载评审意见，风险由 `key_concerns` 单点承载。
    """
    payload = _summary_of(refs=[], text=None)
    with _stub_model(payload, _OPINION_OK):
        data = svc.generate_review_summary(_request(actions=("不通过", "通过"), with_risk=True))
    request = _request(actions=("不通过", "通过"), with_risk=True)
    corpus = svc._input_number_corpus(request)
    refs = set(svc._collect_valid_refs(request))
    text = data.review_summary.text
    assert svc._unverifiable_numbers(text, corpus) == []
    assert all(ref in refs for ref in data.review_summary.source_refs)
    assert "预付款比例偏低" not in text  # 风险标题不进总述
    assert "关注点" not in text


@pytest.mark.parametrize(
    "name",
    ["s05_baotou_v3", "s07_033299_v0.01_reject", "s09_nongye_v1_allpass"],
)
def test_fallback_on_real_samples_is_traceable_and_neutral(name):
    """真实样例形态下兜底稿同样可溯源（联调误杀场景的回归锁）。"""
    path = Path("tmp/review-summary-apifox") / f"{name}.json"
    if not path.exists():
        pytest.skip("真实样例请求体不在工作树")
    request = ReviewSummaryRequest.model_validate(json.loads(path.read_text(encoding="utf-8")))
    text = svc._fallback_summary_text(request)
    assert text
    assert svc._unverifiable_numbers(text, svc._input_number_corpus(request)) == []
    assert all(ref in set(svc._collect_valid_refs(request)) for ref in svc._fallback_summary_refs(request))
    assert not svc._has_positive_tone(text)


def test_fallback_names_the_nodes_that_wrote_opinions():
    """兜底稿同样要给审批人"谁提了要求"：只点名 `comment` 非空的节点（纯确定性、零推断），
    引用指向 `opinions[i].node_name`；节点名原样照搬，不数个数以免引出新数字。"""
    request = _request(
        actions=("通过", "有条件通过", "通过"),
        comments=("要求提高预付款比例。", "须补充仲裁地。", ""),
    )
    text = svc._fallback_summary_text(request)
    assert "节点0" in text and "节点1" in text
    assert "节点2" not in text  # 空意见不点名
    refs = svc._fallback_summary_refs(request)
    assert "opinions[0].node_name" in refs and "opinions[1].node_name" in refs
    assert "opinions[2].node_name" not in refs
    # 自证清白仍成立：点名不引入语料外数字
    assert svc._unverifiable_numbers(text, svc._input_number_corpus(request)) == []


def test_fallback_node_names_are_capped_without_a_count():
    """点名上限 3 个，超出只说"等节点"——写个数就要引新数字，语料里未必有。"""
    request = _request(
        actions=("通过",) * 5,
        comments=("意见一。", "意见二。", "意见三。", "意见四。", "意见五。"),
    )
    text = svc._fallback_summary_text(request)
    assert "节点0" in text and "节点1" in text and "节点2" in text
    assert "节点3" not in text
    assert "等节点" in text


# --------------------------------------------------------------- 空态与缓存边界


def test_no_traceable_input_keeps_null_summary_without_fallback_marker():
    """无任何可溯源事实时不硬凑兜底稿：属输入空态，text=null 且不打 fallback 标记。"""
    request = ReviewSummaryRequest.model_validate(
        {"contract_meta": None, "route_reason": None, "risk_register": [], "opinions": []}
    )
    with _stub_model() as stub:
        data = svc.generate_review_summary(request)
    assert data.review_summary.text is None
    assert "review_summary.fallback" not in data.degraded_sections
    assert len(stub.calls) == 0  # 无源不生成，连模型都不调


def test_no_fallback_material_keeps_the_server_only_empty_state():
    """无有字意见时不请模型（它确实没题材可写）：总述只装配 ①②，此处两者都缺 → text=null。

    属**输入决定的空态**（`review_summary.opinions`），不是模型失守：不打 `.model`/`.fallback`，
    零次模型调用，且**可落缓存**。
    """
    request = ReviewSummaryRequest.model_validate(
        {
            "contract_meta": None,
            "route_reason": {"text": "合同总额超过 ¥100 万，触发副总经理终审"},
            "risk_register": [],
            "opinions": [],
        }
    )
    with _stub_model(_summary_of(refs=["opinions[0]"]), _OPINION_OK) as stub:
        data = svc.generate_review_summary(request)
    assert data.review_summary.text is None
    assert data.review_summary.themes == []
    assert "review_summary.model" not in data.degraded_sections
    assert "review_summary.fallback" not in data.degraded_sections
    assert "review_summary.opinions" in data.degraded_sections
    assert len(stub.calls) == 0
    assert get_cached(make_cache_key(request)) is not None
    # 提级块属装配区，照常返回
    assert data.key_concerns[0].text == "合同总额超过 ¥100 万，触发副总经理终审"


def test_fallback_response_is_not_cached_but_ai_response_is():
    """兜底稿不写缓存（否则同输入永远拿不到 AI 稿）；正常 AI 稿照旧缓存。"""
    request = _request(actions=("通过", "通过"))
    with _stub_model(_summary_of(refs=[]), _OPINION_OK) as stub:
        svc.generate_review_summary(request)
        assert get_cached(make_cache_key(request)) is None
        svc.generate_review_summary(request)
        # 每发 = 总述 1 次 + 结构违规定向重试 1 次 + 意见摘要 1 次，第二发未命中缓存
        assert len(stub.calls) == 6

    ok_request = _request(actions=("通过", "通过"))
    with _stub_model(_SUMMARY_OK, _OPINION_OK) as stub:
        svc.generate_review_summary(ok_request)
        assert get_cached(make_cache_key(ok_request)) is not None
        svc.generate_review_summary(ok_request)
        assert len(stub.calls) == 2  # 第二发命中缓存

# ------------------------------------------------- 超长总述：整句裁尾，不弃用（s06）
# 用户口径（2026-10-08）："先不限制字数了，但也不能像现在这样罗列。
# 我担心限制字数又被弃用了，那仅有的 AI 能力就没有了。"
# 于是 s06 那种 407 字的失控稿不再整段清零：prompt 端禁顿号罗列，
# 服务端按整句从尾部砍到红线内；只有砍不动（首句即超限 / 不足两句）才走兜底稿。
# D16 后红线作用于**拼接后的全文**（①②装配句 + overall + 主题片段，D16.1-I5），
# 而主题之间用"；"相连、"；"本身是整句边界 → 裁尾粒度正好是"整条主题"。

_HEAD = "该合同为软件集成合同，合同总额 14480000 CNY，综合毛利率 5.05%。"
_T1 = "付款与金额上，合同复核提出硬件部分亏损、事业部级产品成本超合同额，要求控制执行成本并报领导审批。"
_T2 = "产品与报价上，开发评审要求正版授权本次不采购的风险由商务侧把控，报价名称须对应我司标准名称。"
_T3 = "开票与税率上，税务评审提出软件产品按登记证书标准名称与版本号填写、不可分包外采。"
_T4 = "条款与管辖上，法务口径是争议解决条款必须修改后方可签署，其余无重大障碍。"
_T5 = "成本与利润上，部门经理反映实际执行利润率偏低，需要在执行阶段持续压降成本。"
_T6 = "印章与授权上，电子章复核要求退回重盖并补齐授权委托书原件后方可用印。"
_T7 = "客户与履约上，风控评审附议财务口径，要求回款计划与交付里程碑逐期挂钩后方可放行。"
_ALL_THEMES = (_T1, _T2, _T3, _T4, _T5, _T6, _T7)


def _prompt_text(stub: _Stub, call_index: int) -> str:
    return chr(10).join(str(m.content) for m in stub.calls[call_index]["messages"])


def _long_request() -> ReviewSummaryRequest:
    """两个节点写字、其余留空的真实面板形态。"""
    return _request(actions=("通过", "通过"), comments=(_T1,))


def _themes_payload(*texts, overall=None):
    """失控稿的 D16 形态：模型一次交出 7 条主题，全部指向同一条有字意见。"""
    return {
        "overall": overall,
        "themes": [{"text": t, "opinion_refs": ["opinions[0]"]} for t in texts],
    }


def test_overlong_ai_summary_is_trimmed_not_discarded():
    """超红线：AI 稿整句裁尾后照常返回，不打 `.fallback`/`.model`，并且可落缓存。"""
    request = _long_request()
    payload = _themes_payload(*_ALL_THEMES)
    draft = svc._verify_summary_payload(
        payload, request, set(svc._collect_valid_refs(request)), svc._input_number_corpus(request)
    )
    draft_text, _ = svc._render_summary(request, draft)
    assert len(draft.themes) == len(_ALL_THEMES)  # 前提：这一稿本身合法，只是超长
    assert len(draft_text) > svc._SUMMARY_HARD_LIMIT  # 前提：这是一份超红线稿
    with _stub_model(payload, _OPINION_OK):
        data = svc.generate_review_summary(request)
    text = data.review_summary.text
    assert text is not None
    assert len(text) <= svc._SUMMARY_HARD_LIMIT
    assert text.startswith(_HEAD)  # ① 合同要素句由服务端装配，永远保住
    assert data.review_summary.themes  # 裁尾不是弃用：至少保住开头的 AI 主题
    assert "review_summary.fallback" not in data.degraded_sections
    assert "review_summary.incomplete" not in data.degraded_sections
    assert data.degraded_sections == ["key_concerns"]  # 只剩无风险项的空态标记
    assert get_cached(make_cache_key(request)) is not None


def test_trim_drops_whole_tail_themes_only():
    """裁的是尾部整主题：红线之内的主题一个不砍，放不下的尾部主题整条去掉，不留半句。"""
    request = _long_request()
    with _stub_model(_themes_payload(*_ALL_THEMES), _OPINION_OK):
        data = svc.generate_review_summary(request)
    text = data.review_summary.text
    kept = [t.text for t in data.review_summary.themes]
    assert kept == list(_ALL_THEMES)[: len(kept)]  # 保住的正是开头几条完整主题
    assert 0 < len(kept) < len(_ALL_THEMES)
    assert svc._open_theme(_T1) in text
    for theme in kept[1:]:
        assert svc._open_theme(theme) in text
    for theme in _ALL_THEMES[len(kept) :]:
        assert theme not in text
    assert text.endswith("。") and not text.endswith(("，", "；", "、", "："))


def test_untrimmable_oversized_sentence_falls_back():
    """整段只有一句且超红线：无从整句裁，退回服务端中性兜底稿并标 `.fallback`。"""
    giant = "评审意见集中在付款条款与开票税率两侧需要商务与税务共同把关，" * 11 + "请务必复核。"
    assert len(giant) > svc._SUMMARY_HARD_LIMIT and svc._open_theme(giant).count("。") == 0
    request = _request(actions=("通过", "通过"))
    with _stub_model(_themes_payload(giant), _OPINION_OK):
        data = svc.generate_review_summary(request)
    assert giant not in data.review_summary.text
    assert "review_summary.fallback" in data.degraded_sections
    assert get_cached(make_cache_key(request)) is None


def test_summary_prompt_bans_comma_enumeration():
    """prompt 端把"别把 comment 细项顿号罗列"写成硬禁令（s06 的失败形态）。"""
    request = _request(actions=("通过", "通过"))
    with _stub_model(_SUMMARY_OK, _OPINION_OK) as stub:
        svc.generate_review_summary(request)
    prompt = _prompt_text(stub, 0)
    assert "反罗列禁令" in prompt
    assert "禁止把一条 comment 里的多个细项用顿号串进主题句" in prompt
    assert "一个主题只写" in prompt
