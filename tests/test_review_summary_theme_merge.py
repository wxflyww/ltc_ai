"""D17 同源主题的服务端合并（2026-10-09，s06 真机第五枪抓到的容量违约）。

触发事实：s06 真机交回 **6 条主题**，refs 分布 `[5] [5] [6] [6] [7] [7]`——三条意见各被拆成
两条，零跨意见归并，渲染后缀"（合同复核）""（开发评审）""（税务评审）"各出现两次，全文 283 字
（距 300 红线仅 17 字），而上一轮同一份输入是 3 条主题 + 跨意见归并。prompt 里"最多 4 条"与
"单意见单主题"两条契约，服务端**一道闸都没管**（`_verify_summary_payload` 只逐主题复检，从不数
条数、也不查重复下标）——这是 prompt-only 约束第六次被真机绕过。

本轮口径（用户拍板"同源合并，不丢内容"）：refs 集合**完全相同**的主题由服务端拼接成一条，
文本一字不增不减、内容零损失、不丢句、不打标记、照常落缓存。刻意不用"；"而用"，"连接（见用例
`test_merge_join_never_introduces_sentence_ends`）：合并后的主题必须仍是 D13 整句裁尾的**原子单位**。

模型边界全 mock，不发真实调用。
"""
import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from app.capabilities.review_summary import service as svc
from app.capabilities.review_summary.cache import clear_cache, get_cached, make_cache_key
from app.capabilities.review_summary.schemas import ReviewSummaryRequest

_OPINION_BATCH = {
    # 摘要文本刻意不含数字：数字抽验对意见摘要同样生效，"摘要0"这种带数字的占位会被判语料外数字
    "summaries": [
        {"index": i, "summary": "已复核并附议前述条款。", "source_refs": [f"opinions[{i}]"]}
        for i in range(6)
    ]
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


def _request(opinions) -> ReviewSummaryRequest:
    return ReviewSummaryRequest.model_validate({
        "contract_meta": {"contract_type": "软件集成", "contract_amount": "13960000 CNY",
                          "gross_margin": "1.77%"},
        "route_reason": {"text": "合同总额超过 ¥100 万，触发副总经理终审"},
        "risk_register": [],
        "opinions": opinions,
    })


# _OPS 的节点名刻意互不为子串，合并后的后缀可逐字断言
_OPS = [
    _op("合同复核", "1、项目整体预估毛利率1.77%，硬件部分亏损，请领导审批；2、事业部级产品成本超合同额，请控制执行成本。", "通过"),
    _op("开发评审", "操作系统正版授权本次不采购，风险请商务侧把控；维保期接口免费开放条款建议删除。", "通过"),
    _op("税务评审", "软件产品按登记证书标准名称填写；13%与6%发票按合同实质开具。", "有条件通过"),
    _op("部门经理", "实际执行利润率需要努力提升。", "通过"),
    _op("交付经理", "交付周期须与付款节奏对齐。", "通过"),
    _op("法务复核", "争议解决地建议约定我司所在地。", "通过"),
]

_A1 = {"text": "项目整体预估毛利率偏低且硬件部分亏损，需领导审批。", "opinion_refs": ["opinions[0]"]}
_A2 = {"text": "事业部级产品成本超合同额，需控制执行成本。", "opinion_refs": ["opinions[0]"]}
_B1 = {"text": "国产操作系统正版授权未采购，需商务把控验收风险。", "opinion_refs": ["opinions[1]"]}
_B2 = {"text": "维保期接口免费开放条款建议删除。", "opinion_refs": ["opinions[1]"]}
_C1 = {"text": "软件产品需按登记证书标准名称填写。", "opinion_refs": ["opinions[2]"]}
_D1 = {"text": "实际执行利润率需努力提升。", "opinion_refs": ["opinions[3]"]}
# s06 真实形态：三组同源拆条、共 6 条主题
_S06_SHAPED = [_A1, _A2, _B1, _B2, _C1, _D1]


def _payload(*themes, overall=None):
    return {"overall": overall, "themes": list(themes)}


# ---------------------------------------------------------------- 纯函数层


def _themes(*items):
    return [
        svc._Theme(
            text=item["text"],
            indexes=[int(ref.split("[")[1].rstrip("]")) for ref in item["opinion_refs"]],
        )
        for item in items
    ]


def test_same_ref_themes_are_merged_into_one():
    """refs 完全相同的主题合成一条，条数 6→4、内容一字不删。"""
    merged = svc._merge_same_ref_themes(_themes(_A1, _A2, _B1, _B2, _C1, _D1))
    assert [t.refs for t in merged] == [
        ["opinions[0]"], ["opinions[1]"], ["opinions[2]"], ["opinions[3]"]]
    assert "需领导审批" in merged[0].text and "需控制执行成本" in merged[0].text
    assert "正版授权未采购" in merged[1].text and "接口免费开放" in merged[1].text


def test_merged_theme_keeps_first_position():
    """合并结果落在**首次出现**的位置——模型给的顺序就是它的关键性顺序，服务端不重排。"""
    merged = svc._merge_same_ref_themes(_themes(_A1, _C1, _A2))
    assert [t.refs for t in merged] == [["opinions[0]"], ["opinions[2]"]]
    assert merged[0].text.startswith("项目整体预估毛利率")


def test_overlapping_but_not_identical_refs_are_not_merged():
    """只合并 refs 集合完全相同者：`[0]` 与 `[0,1]` 不并（合并=断言两话题同源）；`[0]` 之间照常合并。"""
    cross = {"text": "利润率与成本两处需一并控制。", "opinion_refs": ["opinions[0]", "opinions[1]"]}
    merged = svc._merge_same_ref_themes(_themes(_A1, cross, _A2))
    assert [t.refs for t in merged] == [["opinions[0]"], ["opinions[0]", "opinions[1]"]]
    assert "两处需一并控制" in merged[1].text
    assert "需领导审批" in merged[0].text and "需控制执行成本" in merged[0].text


def test_merge_join_never_introduces_sentence_ends():
    """合并必须用非句末标点连接：整句裁尾把一条主题当**原子**，否则尾部裁开会留下没有名字后缀的半条主题。"""
    merged = svc._merge_same_ref_themes(_themes(_A1, _A2))
    text = merged[0].text
    assert "；" not in text and "。" not in text[:-1]
    assert svc._split_sentences(svc._open_theme(text) + "（合同复核）") == [svc._open_theme(text) + "（合同复核）"]


def test_no_duplicate_refs_is_a_no_op():
    """反误伤锁：每条主题各引不同意见时合并零改动（正常稿不受影响）。"""
    themes = _themes(_A1, _B1, _C1)
    assert svc._merge_same_ref_themes(themes) == themes


# ---------------------------------------------------------------- 管线层


def test_s06_shaped_response_merges_and_renders_suffix_once():
    """真机形态端到端：6 条主题出稿 → 响应 4 条、每个节点名后缀只出现一次、零标记、可缓存。"""
    with _stub_model(_payload(*_S06_SHAPED, overall="评审意见聚焦毛利率与开票合规。"), _OPINION_BATCH):
        data = svc.generate_review_summary(_request(_OPS))
    themes = data.review_summary.themes
    assert [t.opinion_refs for t in themes] == [
        ["opinions[0]"], ["opinions[1]"], ["opinions[2]"], ["opinions[3]"]]
    text = data.review_summary.text
    for suffix in ("（合同复核）", "（开发评审）", "（税务评审）", "（部门经理）"):
        assert text.count(suffix) == 1, suffix
    assert data.degraded_sections == []
    assert get_cached(make_cache_key(_request(_OPS))) is not None


def test_merge_keeps_every_sentence_of_the_ai_draft():
    """不丢内容：合并前后 AI 句子的**全部字**都在稿子里（一字不增不减，只去掉重复的名字后缀）。"""
    with _stub_model(_payload(*_S06_SHAPED), _OPINION_BATCH):
        data = svc.generate_review_summary(_request(_OPS))
    text = data.review_summary.text
    for theme in _S06_SHAPED:
        assert svc._open_theme(theme["text"]) in text


def test_merge_only_applies_to_accepted_themes():
    """合并发生在复检**之后**：含语料外数字的那一条先被丢弃，不会因为同源就被另一半"救"回来。"""
    bad = {"text": "硬件亏损 ¥888 万元，请领导审批。", "opinion_refs": ["opinions[0]"]}
    with _stub_model(_payload(_A1, bad, _B1), _OPINION_BATCH):
        data = svc.generate_review_summary(_request(_OPS))
    assert [t.opinion_refs for t in data.review_summary.themes] == [["opinions[0]"], ["opinions[1]"]]
    assert "888" not in data.review_summary.text
    assert "review_summary.incomplete" in data.degraded_sections


def test_capacity_observation_fires_only_on_residual_over_capacity(caplog):
    """观测档：合并后仍 >4 条（同源之外的超量）才记 `容量观测`；合并能解决的不刷屏。"""
    with caplog.at_level("INFO"):
        with _stub_model(_payload(*_S06_SHAPED), _OPINION_BATCH):
            svc.generate_review_summary(_request(_OPS))
    assert [r for r in caplog.records if "容量观测" in r.getMessage()] == []

    clear_cache()  # 同一个请求体已被上一发缓存，不清会直接命中缓存、走不到生成路径
    over = _S06_SHAPED + [
        {"text": "交付周期须与付款节奏对齐。", "opinion_refs": ["opinions[4]"]},
        {"text": "争议解决地建议约定我司所在地。", "opinion_refs": ["opinions[5]"]},
    ]
    with caplog.at_level("INFO"):
        with _stub_model(_payload(*over), _OPINION_BATCH):
            data = svc.generate_review_summary(_request(_OPS))
    line = [r for r in caplog.records if "容量观测" in r.getMessage()]
    assert len(line) == 1
    assert line[0].theme_count == len(data.review_summary.themes) > svc._THEME_TARGET_COUNT
    assert line[0].raw_theme_count == len(over)


def test_trim_never_leaves_half_a_merged_theme():
    """裁尾与合并的交界面：超红线时削掉的是**整条**合并主题，稿子里不会残留没有名字后缀的半句。"""
    long_a1 = {"text": "项目整体预估毛利率仅1.77%且硬件部分已经亏损，请领导在审批时一并明确成本管控的口径与责任人。",
               "opinion_refs": ["opinions[0]"]}
    long_a2 = {"text": "事业部级产品部分成本已经超过合同额，请在执行阶段控制成本并按月复核偏差。",
               "opinion_refs": ["opinions[0]"]}
    long_b1 = {"text": "国产操作系统与数据库的正版授权本次未采购，请商务侧把控验收风险并在合同里写明交付边界。",
               "opinion_refs": ["opinions[1]"]}
    long_b2 = {"text": "维保期间的政策性接口与适应性改造不得另行收费，建议合同签订时删除该条并补充说明。",
               "opinion_refs": ["opinions[1]"]}
    long_c1 = {"text": "自有软件产品须按登记证书的标准名称与版本号填写，开票商品名称必须与之完全一致否则影响退税。",
               "opinion_refs": ["opinions[2]"]}
    long_d1 = {"text": "实际执行利润率需要努力提升，请按季度跟踪项目成本归集口径。", "opinion_refs": ["opinions[3]"]}
    with _stub_model(_payload(long_a1, long_a2, long_b1, long_b2, long_c1, long_d1,
                              overall="意见集中在成本管控与开票合规两处。"), _OPINION_BATCH):
        data = svc.generate_review_summary(_request(_OPS))
    text = data.review_summary.text
    assert len(text) <= svc._SUMMARY_HARD_LIMIT
    for theme in data.review_summary.themes:
        assert svc._open_theme(theme.text) in text  # 列出来的主题必须整条在稿子里
    # 合并主题的名字后缀只随整条出现或整条消失，不会出现"有半句没名字"的形态
    for suffix in ("（合同复核）", "（开发评审）", "（税务评审）"):
        assert text.count(suffix) <= 1, suffix


# ------------------------------------------------------------------ 真实样例回放
_REAL_S06 = Path("tmp/review-summary-apifox/s06_wuhu_v1.json")
# 2026-10-09 第五枪 s06 真机原样：6 条主题、refs 三组同源
_REAL_S06_THEMES = [
    {"text": "项目整体预估毛利率偏低且硬件部分亏损，需领导审批。", "opinion_refs": ["opinions[5]"]},
    {"text": "事业部级产品部分成本超合同额，需控制执行成本。", "opinion_refs": ["opinions[5]"]},
    {"text": "国产操作系统及数据库正版授权未采购，需商务把控验收风险。", "opinion_refs": ["opinions[6]"]},
    {"text": "维保期接口免费开放条款建议删除，报价名称需对应标准名称。", "opinion_refs": ["opinions[6]"]},
    {"text": "软件产品需按登记证书标准名称填写，开票商品名称须一致。", "opinion_refs": ["opinions[7]"]},
    {"text": "软件与外采硬件开具13%发票，服务开具6%发票。", "opinion_refs": ["opinions[7]"]},
]
_REAL_S06_OVERALL = "评审意见聚焦毛利率、执行成本控制及税务开票合规性。"


@pytest.mark.skipif(not _REAL_S06.exists(), reason="真实样例请求体不在工程内（由合同系统导出）")
def test_s06_real_payload_merges_to_three_without_losing_a_sentence():
    """真机那发 6 主题原样回放：合并回 3 条、每个名字后缀只出现一次、AI 写的句子一句不少。"""
    request = ReviewSummaryRequest.model_validate(json.loads(_REAL_S06.read_text(encoding="utf-8")))
    draft = svc._verify_summary_payload(
        {"overall": _REAL_S06_OVERALL, "themes": _REAL_S06_THEMES},
        request,
        set(svc._collect_valid_refs(request)),
        svc._input_number_corpus(request),
    )
    assert draft.discarded == 0 and draft.violations == [] and len(draft.themes) == 6

    draft.themes = svc._merge_same_ref_themes(draft.themes)
    assert [t.refs for t in draft.themes] == [["opinions[5]"], ["opinions[6]"], ["opinions[7]"]]
    text, _ = svc._render_summary(request, draft)
    for theme in _REAL_S06_THEMES:
        assert svc._open_theme(theme["text"]) in text  # 一字不删
    for name in ("（合同复核）", "（开发评审）", "（税务评审）"):
        assert text.count(name) == 1, name
    assert len(text) < 283  # 省下来的正是重复后缀与句末标点
    assert svc._trim_to_sentences(text, svc._SUMMARY_HARD_LIMIT) == text  # 合并后离红线更远


def test_runaway_group_is_left_for_the_trimmer_instead_of_becoming_one_long_sentence():
    """红线相撞处的锁：一条意见拆 7 句的失控稿**不合并**——合并会造出裁不动的长句，
    把 D13"整句裁尾、降级不丢内容"直接顶成 `.fallback`。留成原句才能让裁尾一条一条削。"""
    runaway = _themes(*(
        {"text": f"第{index}项执行层面的细项要求需要在合同里逐条写清楚边界与责任人。",
         "opinion_refs": ["opinions[0]"]}
        for index in range(1, 8)
    ))
    merged = svc._merge_same_ref_themes(runaway)
    assert len(merged) == 7
    assert [t.text for t in merged] == [t.text for t in runaway]
    assert all(len(t.text) <= svc._MERGED_THEME_MAX_CHARS or len(merged) > 1 for t in merged)
