"""D16(+D16.1+D16.2) 主题结构化用例：themes 契约、结构闸 G1/G2/G3、观测 G4、服务端渲染与处置阶梯。

规格来源 = `openspec/changes/review-summary-api/design.md` 的 D16 / D16.1 / D16.2（冲突处以
D16.2、D16.1 为准）。覆盖任务书 §5 的最低必测集 18 条（可加不可减），逐条在 docstring 标号。

模型层边界统一 mock，不发任何真实调用。
"""
import json
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from app.capabilities.review_summary import service as svc
from app.capabilities.review_summary.cache import clear_cache, get_cached, make_cache_key
from app.capabilities.review_summary.schemas import ReviewSummaryRequest, SummaryTheme

# ①合同要素句（服务端装配）在本工程根 fixture 下的确定成稿，多处断言复用
_ELEMENT = "该合同为硬件集成合同，合同总额 ¥126 万元，综合毛利率 27.7%"
_OPINION_BATCH = {
    "summaries": [
        {"index": 0, "summary": "认可并附议前述条款。", "source_refs": ["opinions[0]"]},
        {"index": 1, "summary": "要求补充仲裁地后方可通过。", "source_refs": ["opinions[1]"]},
    ]
}


class _Stub:
    """模型替身：按调用顺序消费响应，耗尽后重复最后一发；元素为异常时抛出。"""

    def __init__(self, *responses):
        self._responses = list(responses) or [_SUMMARY_OK, _OPINION_BATCH]
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


def _prompt_text(stub: _Stub, call_index: int) -> str:
    return "\n".join(str(m.content) for m in stub.calls[call_index]["messages"])


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


# ------------------------------------------------------------------ 构造助手


def _op(node: str, comment: str, action: str = "通过") -> dict:
    return {
        "node_name": node,
        "approver_name": f"评审人{node}",
        "role": node,
        "action": action,
        "comment": comment,
        "submitted_at": None,
    }


def _theme(text: str, refs: list[str]) -> dict:
    return {"text": text, "opinion_refs": refs}


def _draft(overall, *themes) -> dict:
    return {"overall": overall, "themes": list(themes)}


def _request(opinions=None, **overrides) -> ReviewSummaryRequest:
    payload = {
        "contract_meta": {
            "contract_type": "硬件集成",
            "contract_amount": "¥126 万元",
            "gross_margin": "27.7%",
        },
        "route_reason": {"text": "合同总额超过 ¥100 万，触发副总经理终审"},
        "risk_register": [{"risk_id": "RSK-001", "title": "付款风险", "level": "高"}],
        "opinions": (
            opinions
            if opinions is not None
            else [
                _op("销售评审", "认可推进：让步 3% 换续约优先权。"),
                _op("法务评审", "付款争议条款须补充仲裁地后方可通过。"),
            ]
        ),
    }
    payload.update(overrides)
    return ReviewSummaryRequest.model_validate(payload)


# 一份"干净"的总述稿：两条主题各自指向自己写过字的意见，overall 无节点名、无数字
_THEME_1 = _theme("预付款比例低于公司标准，要求争取提高或确认垫资。", ["opinions[0]"])
_THEME_2 = _theme("付款争议条款须补充仲裁地后方可签署。", ["opinions[1]"])
_SUMMARY_OK = _draft("意见集中在付款条款与开票口径两处。", _THEME_1, _THEME_2)


def _batch(*summaries) -> dict:
    return {"summaries": list(summaries)}


def _clean_batch(request: ReviewSummaryRequest) -> dict:
    """按请求体里真正写了字的意见生成合规摘要批量，避免无关的 opinion_details.model。"""
    return _batch(
        *[
            {
                "index": index,
                "summary": "认可并附议前述条款。",
                "source_refs": [f"opinions[{index}]"],
            }
            for index, opinion in enumerate(request.opinions)
            if opinion.comment.strip()
        ]
    )


# --------------------------------------------------------------- 缺陷 F 拆除证明


def test_d15_text_attribution_machine_is_gone():
    """文本归属闸整体拆除：四函数与 `.attribution` 标记都不再存在（D16 拍板）。"""
    for name in (
        "_silent_node_names",
        "_misattributed_names",
        "_attribution_note",
        "_strip_silent_names",
        "DEGRADED_SUMMARY_ATTRIBUTION",
    ):
        assert not hasattr(svc, name), f"{name} 应随 D15 一起删除"


# ------------------------------------------------- 必测 1：s05 形态（沉默名⊂有字名）


def test_nested_silent_node_name_no_longer_triggers_anything():
    """s05：沉默名 `行业商务评审` 是有字名 `二级行业商务评审` 的子串。

    新契约下主题句不靠文本猜归属：零违规、零重试、可缓存，渲染后缀取 refs 反查的长名。
    """
    request = _request(
        opinions=[_op("二级行业商务评审", "要求把预付款比例提至 20%。"), _op("行业商务评审", "")]
    )
    theme = _theme("预付款比例偏低，要求提至 20%。", ["opinions[0]"])
    with _stub_model(
        _draft(None, theme), {"summaries": [{"index": 0, "summary": "要求提高预付款比例。", "source_refs": ["opinions[0]"]}]}
    ) as stub:
        data = svc.generate_review_summary(request)
    assert len(stub.calls) == 2  # 总述 1 次 + 摘要 1 次，无重试
    assert data.degraded_sections == []
    assert "（二级行业商务评审）" in data.review_summary.text
    assert data.review_summary.text.count("二级行业商务评审") == 1
    assert data.review_summary.themes[0].opinion_refs == ["opinions[0]"]
    assert get_cached(make_cache_key(request)) is not None


def test_find_node_name_mentions_uses_longest_match():
    """最大匹配扫描：长名命中后整段跳过，不留半截名（G3 的检测器）。"""
    request = _request(
        opinions=[_op("二级行业商务评审", "甲。"), _op("行业商务评审", "乙。")]
    )
    names = svc._node_names(request)
    assert svc._find_node_name_mentions("二级行业商务评审要求提价。", names) == ["二级行业商务评审"]
    assert svc._find_node_name_mentions("行业商务评审要求提价。", names) == ["行业商务评审"]
    assert svc._find_node_name_mentions("都没点名。", names) == []


# ------------------------------------------ 必测 2：s06-E 形态（未背书点名 → 重试 → 丢弃）


def test_unbacked_node_name_triggers_retry_and_model_fix_it():
    """主题句点名了 refs 里没有的节点（财经复核的话安给合同复核）→ 定向重试一次 → 改对即采信。"""
    request = _request(
        opinions=[_op("合同复核", "要求补充仲裁地。"), _op("财经复核", "预付款比例偏低，要求提高。")]
    )
    bad = _theme("财经复核提出预付款比例偏低。", ["opinions[0]"])
    good = _theme("预付款比例偏低，要求提高。", ["opinions[1]"])
    with _stub_model(
        _draft(None, bad), _draft(None, good), _clean_batch(request)
    ) as stub:
        data = svc.generate_review_summary(request)
    assert len(stub.calls) == 3  # 首发 + 定向重试 + 摘要批量
    assert "（财经复核）" in data.review_summary.text
    assert data.degraded_sections == []
    assert get_cached(make_cache_key(request)) is not None
    retry_prompt = _prompt_text(stub, 1)
    assert "财经复核" in retry_prompt  # 可核验事实：点错了名
    assert "opinions[0]" in retry_prompt
    assert "未背书" in retry_prompt
    assert "上一稿的结构问题" in retry_prompt
    # 首发话术里没有重试块（静态 system 里也有"未背书"三字，不能拿它作负向断言）
    assert "上一稿的结构问题" not in _prompt_text(stub, 0)


def test_unbacked_name_still_wrong_after_retry_drops_that_theme_only():
    """仍犯 → 违规的那条主题丢弃、其余主题保留 → `.incomplete` + 不落缓存。"""
    request = _request(
        opinions=[_op("合同复核", "要求补充仲裁地。"), _op("财经复核", "预付款比例偏低。")]
    )
    bad = _theme("财经复核提出预付款比例偏低。", ["opinions[0]"])
    ok = _theme("要求补充仲裁地后方可签署。", ["opinions[0]"])
    draft = _draft(None, bad, ok)
    with _stub_model(draft, draft, _clean_batch(request)):
        data = svc.generate_review_summary(request)
    text = data.review_summary.text
    assert "财经复核" not in text  # 整条主题丢弃，不再"删名留句"
    assert [t.text for t in data.review_summary.themes] == [ok["text"]]
    assert data.degraded_sections == ["review_summary.incomplete"]
    assert "review_summary.fallback" not in data.degraded_sections
    assert get_cached(make_cache_key(request)) is None


# ---------------------------------------------------- 必测 3：背书点名保留、后缀不重复


def test_endorsed_node_name_kept_and_suffix_skips_it():
    """点名 ⊆ 自己 refs 反查的名集合 → 保留；渲染后缀跳过文本已出现的名字，不重复。"""
    request = _request(
        opinions=[_op("合同复核", "要求补充仲裁地。"), _op("法务评审", "删除无监理方时的验收条款。")]
    )
    ok = _theme("合同复核要求补充仲裁地后方可签署。", ["opinions[0]"])
    other = _theme("验收条款需删除。", ["opinions[1]"])
    with _stub_model(_draft(None, ok, other), _clean_batch(request)) as stub:
        data = svc.generate_review_summary(request)
    text = data.review_summary.text
    assert "合同复核要求补充仲裁地后方可签署" in text
    assert "（合同复核）" not in text  # 已逐字出现，后缀不再重复
    assert "验收条款需删除（法务评审）" in text
    assert len(stub.calls) == 2  # 背书点名不算违规，不重试
    assert data.degraded_sections == []


def test_same_named_nodes_endorsement_follows_the_referenced_opinion():
    """同名多条、被引那条有字：点名成立（index 唯一天然消解 s06 的"部门经理"歧义）。"""
    request = _request(opinions=[_op("部门经理", ""), _op("部门经理", "执行利润率需提升。")])
    ok = _theme("部门经理提出执行利润率需提升。", ["opinions[1]"])
    with _stub_model(_draft(None, ok), _clean_batch(request)) as stub:
        data = svc.generate_review_summary(request)
    assert len(stub.calls) == 2
    assert data.degraded_sections == []  # 根 fixture 有 route_reason + 风险项，正常态
    assert "部门经理提出执行利润率需提升。" in data.review_summary.text
    assert "（部门经理）" not in data.review_summary.text


# --------------------------------------------------------- 必测 4：G1 逐 ref 剔除


def test_one_dangling_ref_of_three_is_pruned_theme_survives():
    """3 条 ref 中 1 条悬空 → 剔 1 剩 2，主题保留、不重试、不打标记（D16.1-R3）。"""
    request = _request(
        opinions=[_op("法务评审", "要求补充仲裁地。"), _op("税务评审", "开票口径须按标准名称。")]
    )
    theme = _theme("开票口径须按登记证书标准名称填写。", ["opinions[0]", "opinions[9]", "opinions[1]"])
    with _stub_model(_draft(None, theme), _clean_batch(request)) as stub:
        data = svc.generate_review_summary(request)
    assert len(stub.calls) == 2
    assert data.review_summary.themes[0].opinion_refs == ["opinions[0]", "opinions[1]"]
    assert data.degraded_sections == []


def test_all_refs_dangling_is_a_violation_and_retries():
    """3 条全悬空 → 剩 0 → 违规走重试；重试改对即采信。"""
    request = _request(
        opinions=[_op("法务评审", "要求补充仲裁地。"), _op("税务评审", "开票口径须按标准名称。")]
    )
    bad = _theme("开票口径须按标准名称填写。", ["opinions[7]", "opinions[8]"])
    good = _theme("开票口径须按登记证书标准名称填写。", ["opinions[1]"])
    with _stub_model(_draft(None, bad), _draft(None, good), _clean_batch(request)) as stub:
        data = svc.generate_review_summary(request)
    assert len(stub.calls) == 3
    assert [t.opinion_refs for t in data.review_summary.themes] == [["opinions[1]"]]
    assert data.degraded_sections == []


def test_subfield_opinion_ref_is_normalized_to_whole_index():
    """`opinions[1].comment` 这类子字段路径归一成 `opinions[1]`，不惩罚模型（能救就救）。"""
    request = _request(opinions=[_op("法务评审", "要求补充仲裁地。")])
    theme = _theme("要求补充仲裁地后方可签署。", ["opinions[0].comment"])
    with _stub_model(_draft(None, theme), _clean_batch(request)) as stub:
        data = svc.generate_review_summary(request)
    assert len(stub.calls) == 2
    assert data.review_summary.themes[0].opinion_refs == ["opinions[0]"]
    assert data.degraded_sections == []


# ------------------------------------------------------------------ 必测 5：G2


def test_ref_to_empty_comment_theme_dropped_after_retry():
    """refs 指向 comment 为空的意见（结构层的张冠李戴）→ 重试 → 仍指空 → 该主题丢弃。"""
    request = _request(opinions=[_op("法务评审", "要求补充仲裁地。"), _op("税务评审", "")])
    bad = _theme("开票口径须按标准名称。", ["opinions[1]"])
    ok = _theme("要求补充仲裁地后方可签署。", ["opinions[0]"])
    draft = _draft(None, bad, ok)
    with _stub_model(draft, draft, _clean_batch(request)) as stub:
        data = svc.generate_review_summary(request)
    assert [t.text for t in data.review_summary.themes] == [ok["text"]]
    assert data.degraded_sections == ["review_summary.incomplete"]
    assert get_cached(make_cache_key(request)) is None
    assert "opinions[1]" in _prompt_text(stub, 1)
    assert "空" in _prompt_text(stub, 1)  # 可核验事实：那条意见没写字


# ----------------------------------------------------- 必测 6：漏纳"同意。"不惩罚模型


def test_trivial_opinion_left_uncovered_costs_nothing():
    """只写"同意。"的意见未被任何主题引用：不打标记、不旁路缓存、不独立触发重试（D16.1-R1）。"""
    request = _request(opinions=[_op("销售评审", "要求提高预付款比例。"), _op("风控评审", "同意。")])
    theme = _theme("预付款比例偏低，要求争取提高。", ["opinions[0]"])
    with _stub_model(_draft(None, theme), _clean_batch(request)) as stub:
        data = svc.generate_review_summary(request)
    assert len(stub.calls) == 2
    assert data.degraded_sections == []
    assert get_cached(make_cache_key(request)) is not None


# ------------------------------------------------------- 必测 7：uncovered 只搭车进重试


def test_uncovered_refs_ride_along_an_already_triggered_retry():
    """因其他违规触发重试时，未纳入清单出现在话术里，并说明"同意类可忽略"。"""
    request = _request(
        opinions=[
            _op("法务评审", "要求补充仲裁地。"),
            _op("税务评审", "开票口径须按标准名称。"),
            _op("风控评审", "同意。"),
        ]
    )
    bad = _theme("开票口径须按标准名称。", ["opinions[7]"])  # 悬空 → 触发重试
    ok = _theme("要求补充仲裁地后方可签署。", ["opinions[0]"])
    with _stub_model(_draft(None, bad), _draft(None, ok), _clean_batch(request)) as stub:
        svc.generate_review_summary(request)
    retry_prompt = _prompt_text(stub, 1)
    assert "未纳入" in retry_prompt
    assert "opinions[1]" in retry_prompt  # 税务评审没进主题
    assert "同意" in retry_prompt  # 明示近空表态无需补
    # 首发：coverage_note 里也会提到"未纳入"，所以负向断言只针对重试话术的标题
    assert "上一稿的结构问题" not in _prompt_text(stub, 0)


# ------------------------------------------------------------- 必测 8：I4 重试取优


def test_retry_is_adopted_only_when_it_has_more_legal_themes():
    """首稿 3 合法 1 违规 vs 重试稿 2 合法 0 违规 → 采首稿（3 > 2），防"补一个坏一个"。"""
    request = _request(
        opinions=[
            _op("法务评审", "要求补充仲裁地。"),
            _op("税务评审", "开票口径须按标准名称。"),
            _op("风控评审", "回款计划需与里程碑挂钩。"),
        ]
    )
    a = _theme("要求补充仲裁地后方可签署。", ["opinions[0]"])
    b = _theme("开票口径须按登记证书标准名称填写。", ["opinions[1]"])
    c = _theme("回款计划需与交付里程碑逐期挂钩。", ["opinions[2]"])
    bad = _theme("税务评审提出预付款比例偏低。", ["opinions[0]"])  # 未背书点名
    first = _draft(None, a, b, c, bad)
    second = _draft(None, a, b)
    with _stub_model(first, second, _clean_batch(request)) as stub:
        data = svc.generate_review_summary(request)
    assert len(stub.calls) == 3
    assert [t.text for t in data.review_summary.themes] == [a["text"], b["text"], c["text"]]
    assert data.degraded_sections == ["review_summary.incomplete"]  # 首稿丢过 1 条


# --------------------------------------------------------- 必测 9：I3 形状失守


@pytest.mark.parametrize("payload", [{"text": "旧契约散文总述。", "source_refs": ["opinions[0]"]}, {"overall": None}])
def test_legacy_shape_retries_once_then_falls_back(payload):
    """模型惯性交回 `{"text": ...}` / 缺 `themes` 键 → 重试附新契约样例 → 仍失 → 兜底稿 + `.fallback`。

    整块缺失 ≠ 覆盖不全：SHALL NOT 打 `.incomplete`（D16.1-I3）。
    """
    request = _request(opinions=[_op("法务评审", "要求补充仲裁地。")])
    with _stub_model(payload, payload, _clean_batch(request)) as stub:
        data = svc.generate_review_summary(request)
    assert len(stub.calls) == 3
    assert data.review_summary.themes == []
    assert data.review_summary.text is not None
    assert data.degraded_sections == ["review_summary.fallback"]
    assert "review_summary.incomplete" not in data.degraded_sections
    assert get_cached(make_cache_key(request)) is None
    assert '"opinion_refs"' in _prompt_text(stub, 1)  # 重试话术附新契约形状


# ------------------------------------------------------- 必测 10：渲染名字去重保序


def test_rendered_names_deduplicate_and_keep_order():
    """同主题两条 refs 指向同名节点 → 后缀只出现一次；名字取 `node_name` 原样、按 refs 序。"""
    request = _request(
        opinions=[
            _op("财经评审", "预付款比例低于公司标准。"),
            _op("财经评审", "资金占用天数偏长。"),
            _op("法务评审", "须补充仲裁地。"),
        ]
    )
    theme = _theme("预付款与资金占用是主要口径问题。", ["opinions[0]", "opinions[1]", "opinions[2]"])
    with _stub_model(_draft(None, theme), _clean_batch(request)):
        data = svc.generate_review_summary(request)
    text = data.review_summary.text
    assert "（财经评审、法务评审）" in text
    assert text.count("财经评审") == 1


def test_themes_are_returned_and_text_is_server_assembled():
    """`themes[]` 字段照实回填；`text` = ①要素句。②分布句。overall。主题（名字）……"""
    request = _request(opinions=[_op("法务评审", "要求补充仲裁地。"), _op("税务评审", "开票口径须按标准名称。")])
    draft = _draft(
        "意见集中在付款与开票两侧。",
        _theme("要求补充仲裁地后方可签署。", ["opinions[0]"]),
        _theme("开票口径须按登记证书标准名称填写。", ["opinions[1]"]),
    )
    with _stub_model(draft, _clean_batch(request)):
        data = svc.generate_review_summary(request)
    text = data.review_summary.text
    assert text.startswith(_ELEMENT + "。")
    assert "共 2 条意见：通过 2 条。" in text
    assert "意见集中在付款与开票两侧。" in text
    assert text.index("意见集中在付款与开票两侧。") < text.index("要求补充仲裁地后方可签署")
    # 渲染格式（D16）：主题之间用"；"连接，句号只留在全段末尾，名字后缀在句号之前
    assert "要求补充仲裁地后方可签署（法务评审）；开票口径须按登记证书标准名称填写（税务评审）。" in text
    assert data.review_summary.themes == [
        SummaryTheme(text=t["text"], opinion_refs=t["opinion_refs"]) for t in draft["themes"]
    ]
    assert data.review_summary.source_refs[:4] == [
        "contract_meta.contract_type",
        "contract_meta.contract_amount",
        "contract_meta.gross_margin",
        "opinions",
    ]
    assert data.review_summary.source_refs[-2:] == ["opinions[0]", "opinions[1]"]


# ------------------------------------------------------- 必测 11：无有字意见（空态）


@pytest.mark.parametrize("comments", [[], ["", "  "]])
def test_no_written_opinion_assembles_only_two_sentences_without_model(comments):
    """无有字意见 → text = ①② only、`themes=[]`、不发起模型调用、可缓存（输入决定空态）。"""
    opinions = [_op(f"节点{k}", c) for k, c in enumerate(comments)] or []
    request = _request(opinions=opinions)
    with _stub_model() as stub:
        data = svc.generate_review_summary(request)
    assert len(stub.calls) == 0
    assert data.review_summary.themes == []
    text = data.review_summary.text
    assert text is not None
    assert text.startswith(_ELEMENT + "。")
    assert "（销售评审）" not in text and "法务评审" not in text
    assert get_cached(make_cache_key(request)) is not None


def test_all_comments_empty_still_carries_distribution_sentence():
    request = _request(opinions=[_op("节点0", ""), _op("节点1", "")])
    with _stub_model() as stub:
        data = svc.generate_review_summary(request)
    assert len(stub.calls) == 0
    assert "共 2 条意见：通过 2 条。" in data.review_summary.text


# ------------------------------------------------- 必测 12：0 合法主题 → 兜底稿


def test_all_themes_violating_falls_back_without_incomplete_marker():
    """整批主题都被丢弃（0 合法）→ D10 兜底稿 + `.fallback`，不打 `.incomplete`。"""
    request = _request(opinions=[_op("合同复核", "要求补充仲裁地。"), _op("财经复核", "预付款偏低。")])
    bad = _theme("财经复核提出预付款比例偏低。", ["opinions[0]"])  # 未背书
    draft = _draft(None, bad)
    with _stub_model(draft, draft, _clean_batch(request)):
        data = svc.generate_review_summary(request)
    assert data.review_summary.themes == []
    assert data.review_summary.text is not None
    assert _ELEMENT in data.review_summary.text
    assert "共 2 条意见" in data.review_summary.text
    assert data.degraded_sections == ["review_summary.fallback"]
    assert get_cached(make_cache_key(request)) is None


# ---------------------------------------------------- 必测 13：overall 单独违规


@pytest.mark.parametrize(
    "overall,offending",
    [
        ("法务评审认为条款无重大障碍。", "无重大障碍"),  # 含节点名 → 整句丢弃
        ("合同总额 ¥129 万元需关注。", "129"),  # 语料外数字 → 整句丢弃
    ],
    ids=["names_a_node", "fabricated_number"],
)
def test_overall_violation_drops_only_overall(overall, offending):
    request = _request(opinions=[_op("法务评审", "要求补充仲裁地。")])
    theme = _theme("要求补充仲裁地后方可签署。", ["opinions[0]"])
    with _stub_model(_draft(overall, theme), _clean_batch(request)) as stub:
        data = svc.generate_review_summary(request)
    assert offending not in data.review_summary.text
    assert "要求补充仲裁地后方可签署" in data.review_summary.text
    assert len(stub.calls) == 2  # 不重试
    assert data.degraded_sections == []  # 不打标记
    assert get_cached(make_cache_key(request)) is not None


def test_overall_with_positive_tone_under_reject_is_dropped():
    opinions = [
        _op("法务评审", "要求补充仲裁地。"),
        _op("风控评审", "条款可以接受。", action="不通过"),
    ]
    request = _request(opinions=opinions)
    theme = _theme("付款争议条款须补充仲裁地。", ["opinions[0]"])
    with _stub_model(_draft("各评审节点整体认可该单价值。", theme), _clean_batch(request)) as stub:
        data = svc.generate_review_summary(request)
    assert "整体认可" not in data.review_summary.text
    assert "付款争议条款须补充仲裁地（法务评审）" in data.review_summary.text
    assert len(stub.calls) == 2
    assert data.degraded_sections == []


def test_theme_with_positive_tone_under_reject_is_a_violation():
    """铁律 5 同样管主题句：含正面定性的主题**直接丢弃**（内容违规不消耗重试，旧口径延续）。"""
    opinions = [
        _op("法务评审", "要求补充仲裁地。"),
        _op("风控评审", "条款可以接受。", action="不通过"),
    ]
    request = _request(opinions=opinions)
    bad = _theme("各评审节点整体认可该单价值。", ["opinions[0]"])
    ok = _theme("付款争议条款须补充仲裁地。", ["opinions[0]"])
    with _stub_model(_draft(None, bad, ok), _clean_batch(request)) as stub:
        data = svc.generate_review_summary(request)
    assert len(stub.calls) == 2  # 不因内容违规追加重试
    assert "整体认可" not in data.review_summary.text
    assert [t.text for t in data.review_summary.themes] == [ok["text"]]
    assert data.degraded_sections == ["review_summary.incomplete"]  # 真丢过一条主题
    assert get_cached(make_cache_key(request)) is None


def test_content_violation_rides_along_a_structural_retry():
    """重试因结构违规而发生时，内容违规事实也写进话术：多一次改对的机会，零额外调用。"""
    opinions = [
        _op("法务评审", "要求补充仲裁地。"),
        _op("风控评审", "条款可以接受。", action="不通过"),
    ]
    request = _request(opinions=opinions)
    tone = _theme("各评审节点整体认可该单价值。", ["opinions[0]"])  # 内容违规
    dangling = _theme("付款争议条款须补充仲裁地。", ["opinions[9]"])  # 结构违规 → 扳重试
    ok = _theme("付款争议条款须补充仲裁地后方可通过。", ["opinions[0]"])
    with _stub_model(_draft(None, tone, dangling), _draft(None, ok), _clean_batch(request)) as stub:
        data = svc.generate_review_summary(request)
    assert len(stub.calls) == 3
    retry_prompt = _prompt_text(stub, 1)
    assert "整体认可" in retry_prompt  # 内容违规也列进来了
    assert "正面定性" in retry_prompt
    assert [t.text for t in data.review_summary.themes] == [ok["text"]]


# ------------------------------------------------------------ 必测 14：D13 裁尾


def _long_theme(index: int) -> dict:
    return _theme(
        f"第{index}个主题上，相关评审节点提出的诉求需要逐条落实并在执行阶段持续跟踪核对结果。",
        [f"opinions[{index}]"],
    )


def test_concatenated_text_over_limit_is_trimmed_by_whole_sentence():
    """拼接后超 300 字（含服务端装配字数）→ 整句裁尾、不打标记、可缓存。"""
    opinions = [_op(f"节点{index}", f"第{index}条意见的实质诉求原文。") for index in range(1, 8)]
    request = _request(opinions=opinions)
    # 每条主题都引用带数字的原文，数字仍在语料内
    themes = [_long_theme(index) for index in range(len(opinions))]
    with _stub_model(_draft("意见集中在执行层面。", *themes), _clean_batch(request)):
        data = svc.generate_review_summary(request)
    text = data.review_summary.text
    assert len(text) <= svc._SUMMARY_HARD_LIMIT
    assert text.startswith(_ELEMENT + "。")
    assert data.degraded_sections == []
    assert text.endswith("。") and not text.endswith("；")
    kept = [t.text for t in data.review_summary.themes]
    assert len(kept) < len(themes)  # 确实从尾部整句削掉了主题
    assert kept == [t["text"] for t in themes][: len(kept)]  # 保留的是头部连续的那些
    # 被裁掉的主题同时从 themes 里剔除，不留"字段有、正文无"
    for theme in kept:
        assert svc._open_theme(theme) in text
    assert svc._open_theme(themes[-1]["text"]) not in text
    assert get_cached(make_cache_key(request)) is not None


def test_trim_that_loses_every_ai_sentence_falls_back():
    """裁到尾主题全掉（只剩服务端装配两句）→ 视同 AI 稿不可用 → 兜底稿 + `.fallback`、不落缓存。"""
    opinions = [_op("节点0", "超长意见原文" + "需要展开的描述" * 30)]
    request = _request(opinions=opinions)
    giant = _theme("要求逐条核对合同附件中的每一项技术参数并同步更新到交付清单里" * 12, ["opinions[0]"])
    with _stub_model(_draft(None, giant), _clean_batch(request)):
        data = svc.generate_review_summary(request)
    assert data.degraded_sections == ["review_summary.fallback"]
    assert data.review_summary.themes == []
    assert get_cached(make_cache_key(request)) is None


def test_untrimmable_single_sentence_without_element_falls_back():
    """连整句都切不开（无 ① 要素、首句即超限）→ 兜底稿。"""
    request = _request(
        contract_meta=None, opinions=[_op("节点0", "要求补充仲裁地。")]
    )
    giant = _theme("评审" + "意见集中在付款条款与开票税率两侧需要商务与税务共同把关" * 12, ["opinions[0]"])
    assert giant["text"].count("。") == 0
    with _stub_model(_draft(None, giant), _clean_batch(request)):
        data = svc.generate_review_summary(request)
    assert data.degraded_sections == ["review_summary.fallback"]


# ------------------------------------------------- 必测 15：分布句单一口径（I1）


def test_distribution_sentence_is_one_and_the_same_everywhere():
    """面板 ②、prompt 注记、兜底稿共用同一句事实文本，不许第三份口径。"""
    request = _request(opinions=[_op("节点0", "要求补充仲裁地。"), _op("节点1", "预付款偏低。")])
    sentence = svc._distribution_sentence(request)
    draft = _draft("意见集中在付款与开票两侧。", _theme("要求补充仲裁地后方可签署。", ["opinions[0]"]))
    with _stub_model(draft, _clean_batch(request)) as stub:
        data = svc.generate_review_summary(request)
    assert sentence == "共 2 条意见：通过 2 条"
    assert sentence in data.review_summary.text
    assert sentence in _prompt_text(stub, 0)
    assert sentence in svc._fallback_summary_text(request)


def test_reject_instruction_stays_in_prompt_and_out_of_panel():
    """reject 场景的退化指令是给模型的话，绝不进面板 ②。"""
    opinions = [_op("节点0", "要求补充仲裁地。"), _op("节点1", "不同意该方案。", action="不通过")]
    request = _request(opinions=opinions)
    theme = _theme("付款争议条款须补充仲裁地后方可签署。", ["opinions[0]"])
    with _stub_model(_draft(None, theme), _clean_batch(request)) as stub:
        data = svc.generate_review_summary(request)
    prompt = _prompt_text(stub, 0)
    assert "存在不通过意见" in prompt and "禁止任何正面定性" in prompt
    assert "共 2 条意见：通过 1 条、不通过 1 条" in prompt
    text = data.review_summary.text
    assert "共 2 条意见：通过 1 条、不通过 1 条" in text
    assert "中性陈述" not in text and "禁止任何正面定性" not in text


# ------------------------------------------- 必测 16：兜底稿不含风险片（I2）


def test_fallback_has_no_risk_piece_and_names_written_nodes():
    request = _request(
        risk_register=[{"risk_id": "RSK-1", "title": "预付款比例偏低", "level": "高"}],
        opinions=[_op("法务评审", "要求补充仲裁地。"), _op("税务评审", "")],
    )
    text = svc._fallback_summary_text(request)
    assert _ELEMENT in text and "共 2 条意见" in text
    assert "法务评审" in text  # 书面意见点名片保留
    assert "税务评审" not in text
    assert "预付款比例偏低" not in text  # 风险项由 key_concerns 单点承载
    refs = set(svc._fallback_summary_refs(request))
    valid = set(svc._collect_valid_refs(request))
    assert refs <= valid
    assert svc._unverifiable_numbers(text, svc._input_number_corpus(request)) == []


def test_fallback_on_risk_only_request_never_blanks_the_panel():
    """只有风险项、无要素无意见时兜底稿确实无素材可拼：text=null + `.model`（D10 第二层）。"""
    request = ReviewSummaryRequest.model_validate(
        {
            "route_reason": {"text": "合同总额超过 ¥100 万，触发副总经理终审"},
            "risk_register": [{"risk_id": "RSK-1", "title": "付款风险"}],
            "opinions": [],
        }
    )
    with _stub_model() as stub:
        data = svc.generate_review_summary(request)
    assert len(stub.calls) == 0
    assert data.review_summary.text is None
    assert data.review_summary.themes == []
    assert data.key_concerns[0].text == "合同总额超过 ¥100 万，触发副总经理终审"


# ------------------------------------------------ 必测 17：既有闸在 themes 路径不变


def test_theme_with_fabricated_number_is_dropped_without_retry():
    """D9 语料口径在 themes 路径不变：语料外数字的主题直接丢弃，不消耗重试（内容违规旧口径）。"""
    request = _request(opinions=[_op("法务评审", "要求补充仲裁地。")])
    bad = _theme("合同总额 ¥129 万元需要复核。", ["opinions[0]"])
    ok = _theme("要求补充仲裁地后方可签署。", ["opinions[0]"])
    with _stub_model(_draft(None, bad, ok), _clean_batch(request)) as stub:
        data = svc.generate_review_summary(request)
    assert len(stub.calls) == 2
    assert "129" not in data.review_summary.text
    assert [t.text for t in data.review_summary.themes] == [ok["text"]]
    assert data.degraded_sections == ["review_summary.incomplete"]


def test_distribution_counts_quoted_by_theme_are_not_fabricated():
    """D9 语料口径不变：主题照抄服务端注入的条数分布不算编造。"""
    request = _request(
        contract_meta={"contract_type": "软件集成"},
        risk_register=[],
        route_reason=None,
        opinions=[_op("销售评审", "认可推进。")] * 3,
    )
    theme = _theme("本次共 3 条意见：通过 3 条。", ["opinions[0]"])
    with _stub_model(_draft(None, theme), _clean_batch(request)) as stub:
        data = svc.generate_review_summary(request)
    assert len(stub.calls) == 2
    assert data.degraded_sections == ["key_concerns"]  # 本例无风险项无提级，只有那条空态标记
    assert "共 3 条意见：通过 3 条" in data.review_summary.text


def test_opinion_summary_gates_are_unchanged():
    """意见摘要侧的分条校验、显式 null 语义、漏 index 才算丢弃——D14 口径不动。"""
    request = _request(opinions=[_op("法务评审", "要求补充仲裁地。"), _op("风控评审", "同意。")])
    payload = _batch(
        {"index": 0, "summary": "须补充仲裁地后方可通过。", "source_refs": ["opinions[0]"]},
        {"index": 1, "summary": None, "source_refs": []},
    )
    with _stub_model(_draft(None, _theme("要求补充仲裁地。", ["opinions[0]"])), payload):
        data = svc.generate_review_summary(request)
    assert data.opinion_details[0].summary == "须补充仲裁地后方可通过。"
    assert data.opinion_details[1].summary is None
    assert data.degraded_sections == []
    assert get_cached(make_cache_key(request)) is not None


# -------------------------------------- 必测 18：覆盖清单措辞 + uncovered 日志计数


def test_coverage_note_is_capacity_aware_and_makes_no_impossible_promise():
    request = _request(
        opinions=[_op(f"节点{k}", f"第 {k} 条意见的实质诉求。") for k in range(3)]
    )
    with _stub_model(_SUMMARY_OK, _clean_batch(request)) as stub:
        svc.generate_review_summary(request)
    prompt = _prompt_text(stub, 0)
    for phrase in ("容量有限", "按关键性取舍", "不算你的违约"):
        assert phrase in prompt
    assert "必须纳入" not in prompt
    assert "各节点意见详情" in prompt


def test_coverage_log_carries_covered_total_and_overlap():
    request = _request(
        opinions=[
            _op("法务评审", "要求补充仲裁地后方可签署。"),
            _op("税务评审", "开票口径须按标准名称。"),
            _op("风控评审", "同意。"),
        ]
    )
    theme = _theme("付款争议条款须补充仲裁地后方可签署。", ["opinions[0]"])
    with patch.object(svc, "logger") as log, _stub_model(_draft(None, theme), _clean_batch(request)):
        svc.generate_review_summary(request)
    extra = _coverage_extra(log)
    assert extra is not None, "未找到主题覆盖观测日志"
    assert extra["covered"] == 1
    assert extra["total"] == 3
    assert extra["uncovered_refs"] == ["opinions[1]", "opinions[2]"]
    assert len(extra["overlap_ratios"]) == 1
    assert 0 < extra["overlap_ratios"][0] <= 1


def _coverage_extra(logger_mock) -> dict | None:
    for call in logger_mock.info.call_args_list:
        extra = call.kwargs.get("extra") or {}
        if "uncovered_refs" in extra:
            return extra
    return None


# ------------------------------------------------------- 其余：接线与降级不外溢


def test_retry_call_failure_does_not_break_the_panel():
    """重试那一发炸了：不外抛、不弃整包，用首稿复检结果。"""
    from app.core.errors import ModelFormatError

    request = _request(
        opinions=[_op("合同复核", "要求补充仲裁地。"), _op("财经复核", "预付款偏低。")]
    )
    bad = _theme("财经复核提出预付款比例偏低。", ["opinions[0]"])
    ok = _theme("要求补充仲裁地后方可签署。", ["opinions[0]"])
    with _stub_model(_draft(None, bad, ok), ModelFormatError("boom"), _clean_batch(request)):
        data = svc.generate_review_summary(request)
    assert [t.text for t in data.review_summary.themes] == [ok["text"]]
    assert data.degraded_sections == ["review_summary.incomplete"]
    assert len(data.opinion_details) == 2


def test_first_summary_call_failure_still_propagates_error_code():
    from app.core.errors import ModelInvocationError

    with _stub_model(RuntimeError("connection reset")):
        with pytest.raises(ModelInvocationError) as exc:
            svc.generate_review_summary(_request())
    assert exc.value.code == 20001


def test_overall_absent_renders_without_a_gap():
    request = _request(opinions=[_op("法务评审", "要求补充仲裁地。")])
    theme = _theme("付款争议条款须补充仲裁地。", ["opinions[0]"])
    with _stub_model(_draft(None, theme), _clean_batch(request)):
        data = svc.generate_review_summary(request)
    text = data.review_summary.text
    assert text.endswith("付款争议条款须补充仲裁地（法务评审）。")
    assert "。。" not in text  # 句号只在整段末尾出现一次
    assert "。。" not in text


# ---------------------------- D16.3：概括优先 / 单意见单主题 / overall 归并范式（纯 prompt 措辞）


def test_summary_prompt_requires_synthesis_not_transcription():
    """改动一：主题句必须是模型自己概括的一句话，逐字或近似逐字搬运 comment 判不合格。

    触发条件 = s06 真机首发的摘录器形态（四条主题 `overlap_ratio` 三个 1.0，零跨意见归并）。
    """
    request = _request()
    with _stub_model(_SUMMARY_OK, _clean_batch(request)) as stub:
        svc.generate_review_summary(request)
    prompt = _prompt_text(stub, 0)
    assert "你自己概括的一句话" in prompt
    assert "不是被引意见原文的搬运" in prompt
    assert "近似逐字照搬" in prompt


def test_summary_prompt_forbids_splitting_one_opinion_into_several_themes():
    """改动二：同一条意见的多个编号诉求合并成一句概括，不得拆成多个主题；跨意见才算归并。

    触发条件 = s05/s06 真机各有两条主题同指一个 `opinions[i]`，渲染后缀随之重复。
    """
    request = _request()
    with _stub_model(_SUMMARY_OK, _clean_batch(request)) as stub:
        svc.generate_review_summary(request)
    prompt = _prompt_text(stub, 0)
    assert "合并为同一个主题" in prompt
    assert "不得把同一条意见拆成多个主题" in prompt
    assert "跨意见" in prompt


def test_summary_prompt_carries_synthesis_examples_and_overall_paradigm():
    """改动一/三：正反例落到具体句子（负例即 s06 的搬运形态），overall 点名跨意见归并句为范式。"""
    request = _request()
    with _stub_model(_SUMMARY_OK, _clean_batch(request)) as stub:
        svc.generate_review_summary(request)
    prompt = _prompt_text(stub, 0)
    assert "四流一致性" in prompt  # 合格示例：一句收住多条细项的主旨
    assert "软件产品开具13%的增值税发票" in prompt  # 不合格示例：comment 原文的目录
    assert "跨意见归并句" in prompt  # overall 即主题归并的浓缩版
