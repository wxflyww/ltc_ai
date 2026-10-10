"""真实联调抓出的降级标记与归属缺陷回归用例（s05 → 缺陷 A/B，s06 → 缺陷 D/E）。

缺陷 A：`_opinions_block` 向 prompt 注入展示辅助键 `action_label`，但引用清单
`_collect_valid_refs` 只登记请求体真实字段——模型逐字引用了输入里见过的
`opinions[i].action_label` 被判悬空，整段总述误杀。修法：输入块不再注入该键。

缺陷 B：comment 为空的意见没有可摘要内容，却被计入"丢弃"并打上
`opinion_details.model`——连带缓存旁路规则，真实面板（多数评审人只点通过
不写字）将永远不落缓存。修法：空意见不进批量摘要输入、回填时跳过且不计丢弃。

缺陷 D：模型按 prompt 契约对近空 comment 显式返回 `summary: null`，服务端却把
"null"也当丢弃计数。修法：显式 null 是契约内的正确结果，只有漏交 index 才算真丢弃。

缺陷 E：总述把某条诉求转给了一个字都没写过的节点（张冠李戴），数字/引用/正面定性/长度
四道闸全都拦不到——它编的是归属。D15 曾在文本空间做"沉默节点名匹配"，被 s05 证明不可行
（节点名互成子串，误判与漏判数学上不可兼得）。D16 把归属交给结构：主题只交
`opinion_refs` 指针，节点名由服务端反查 `opinions[i].node_name` 派生渲染，文本层只保留
**负向背书校验**（句内点了名，必须是该主题自己 refs 覆盖的节点，D16.1-R2/G3）：
未背书 → 定向重试一次 → 仍违规则**整条主题丢弃**并打 `review_summary.incomplete`。

模型层边界统一 mock（沿用 test_review_summary_service 的 _Stub 模式）。
"""
import json
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from app.capabilities.review_summary import service as svc
from app.capabilities.review_summary.cache import clear_cache, get_cached, make_cache_key
from app.capabilities.review_summary.schemas import ReviewSummaryRequest

_SUMMARY_OK = {
    "overall": "关注点集中在争议解决条款。",
    "themes": [{"text": "要求补充仲裁地条款后方可签署。", "opinion_refs": ["opinions[0]"]}],
}


def _opinion(index, comment, action="通过"):
    return {
        "index": index,
        "summary": f"第{index}条意见的摘要。" if comment else None,
        "source_refs": [f"opinions[{index}]"] if comment else [],
    }


class _Stub:
    """模型替身：按调用顺序消费响应（第 1 次=总述，第 2 次=意见摘要批量）。"""

    def __init__(self, *responses):
        self._responses = list(responses) or [_SUMMARY_OK, {"summaries": []}]
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


def _request(comments: list[str]) -> ReviewSummaryRequest:
    return ReviewSummaryRequest.model_validate(
        {
            "contract_meta": {
                "contract_type": "软件集成",
                "contract_amount": "14480000 CNY",
                "gross_margin": "5.05%",
            },
            "route_reason": None,
            "risk_register": [],
            "opinions": [
                {
                    "node_name": f"节点{k}",
                    "approver_name": f"评审人{k}",
                    "role": f"节点{k}",
                    "action": "通过",
                    "comment": c,
                    "submitted_at": None,
                }
                for k, c in enumerate(comments)
            ],
        }
    )


# ------------------------------------------------------------- 缺陷 A：action_label


def test_prompt_input_blocks_do_not_contain_action_label():
    """两个 prompt 的意见输入块都不再出现 action_label 键，模型无从引用悬空路径。"""
    with _stub_model() as stub:
        svc.generate_review_summary(_request(["要求补充仲裁地条款。"]))
    for call_index in range(len(stub.calls)):
        assert "action_label" not in _prompt_text(stub, call_index)


# ------------------------------------------------------------- 缺陷 B：空意见误报


def test_empty_comment_not_counted_as_discarded():
    """空 comment 只丢内容不丢信誉：无 opinion_details.model 标记，结果可落缓存。"""
    opinion_payload = {"summaries": [_opinion(0, "要求补充仲裁地条款。")]}
    request = _request(["要求补充仲裁地条款。", ""])
    with _stub_model(_SUMMARY_OK, opinion_payload) as stub:
        data = svc.generate_review_summary(request)
    assert data.opinion_details[0].summary == "第0条意见的摘要。"
    assert data.opinion_details[1].summary is None
    assert "opinion_details.model" not in data.degraded_sections
    assert not any(m.endswith(".model") for m in data.degraded_sections)
    assert get_cached(make_cache_key(request)) is not None
    # 第二次同输入必须命中缓存，不再触模型
    svc.generate_review_summary(request)
    assert len(stub.calls) == 2


def test_opinion_prompt_excludes_empty_comments():
    """批量摘要输入块只含有文字的意见，空意见不占 token。"""
    opinion_payload = {"summaries": [_opinion(0, "要求补充仲裁地条款。")]}
    with _stub_model(_SUMMARY_OK, opinion_payload) as stub:
        svc.generate_review_summary(_request(["要求补充仲裁地条款。", ""]))
    opinion_prompt = _prompt_text(stub, 1)
    assert '"index": 0' in opinion_prompt
    assert '"index": 1' not in opinion_prompt


def test_all_comments_empty_skips_model_calls_entirely():
    """全员空意见：总述与意见摘要两处都不触模型（没题材可写），装配句照常返回、可缓存。"""
    request = _request(["", "  ", ""])
    with _stub_model(_SUMMARY_OK) as stub:
        data = svc.generate_review_summary(request)
    assert len(stub.calls) == 0
    assert all(d.summary is None for d in data.opinion_details)
    assert "opinion_details.model" not in data.degraded_sections
    assert "review_summary.model" not in data.degraded_sections
    assert "review_summary.fallback" not in data.degraded_sections
    assert data.review_summary.themes == []
    # D18：全员空意见时 ②分布句自己说清"几条写了字"（正向计数，此处为 0）——零模型调用分支
    assert data.review_summary.text == (
        "该合同为软件集成合同，合同总额 14480000 CNY，综合毛利率 5.05%。"
        "共 3 条意见：通过 3 条，其中 0 条填写了意见。"
    )
    assert get_cached(make_cache_key(request)) is not None


def test_model_summary_for_empty_comment_is_ignored():
    """模型越权给空意见编摘要：不写回、也不因此打降级标记。"""
    opinion_payload = {
        "summaries": [
            _opinion(0, "要求补充仲裁地条款。"),
            {"index": 1, "summary": "同意推进。", "source_refs": ["opinions[1]"]},
        ]
    }
    with _stub_model(_SUMMARY_OK, opinion_payload):
        data = svc.generate_review_summary(_request(["要求补充仲裁地条款。", ""]))
    assert data.opinion_details[1].summary is None
    assert "opinion_details.model" not in data.degraded_sections


# ------------------------------------------- 缺陷 D（s06 复现）：显式 null 不算丢弃

# prompt 明说"某条 comment 无实质内容时该条 summary 输出 null"，但服务端旧逻辑
# 把这个契约内的 null 当成违规丢弃 → `opinion_details.model` → 缓存旁路。
# 真实面板里"同意。"这类近空意见极多，等于缓存永久失效。

_TRIVIAL = "同意。"
_SUBSTANTIAL = "要求补充仲裁地条款。"


def test_explicit_null_summary_for_trivial_comment_is_not_discarded():
    """模型对"同意。"显式返回 null：是契约内的正确输出，不打标记、可落缓存。"""
    opinion_payload = {
        "summaries": [
            {"index": 0, "summary": None, "source_refs": []},
            _opinion(1, _SUBSTANTIAL),
        ]
    }
    request = _request([_TRIVIAL, _SUBSTANTIAL])
    with _stub_model(_SUMMARY_OK, opinion_payload) as stub:
        data = svc.generate_review_summary(request)
    assert data.opinion_details[0].summary is None
    assert data.opinion_details[1].summary == "第1条意见的摘要。"
    assert "opinion_details.model" not in data.degraded_sections
    assert get_cached(make_cache_key(request)) is not None
    svc.generate_review_summary(request)
    assert len(stub.calls) == 2  # 第二发命中缓存


def test_all_trivial_comments_declared_null_keep_the_panel_cacheable():
    """全员只写"同意。"：摘要全 null、零标记、缓存照写（s06 的真实形态）。"""
    opinion_payload = {"summaries": [{"index": k, "summary": None, "source_refs": []} for k in range(3)]}
    request = _request([_TRIVIAL, _TRIVIAL, _TRIVIAL])
    with _stub_model(_SUMMARY_OK, opinion_payload) as stub:
        data = svc.generate_review_summary(request)
    assert [d.summary for d in data.opinion_details] == [None, None, None]
    # 本请求无风险项无提级原因，只有 key_concerns 空态标记；不得再出现 .model
    assert data.degraded_sections == ["key_concerns"]
    assert get_cached(make_cache_key(request)) is not None
    svc.generate_review_summary(request)
    assert len(stub.calls) == 2


def test_missing_index_is_the_only_real_discard():
    """只有模型漏交 index 才算真丢弃：标记照打，缓存照旁路。"""
    opinion_payload = {"summaries": [_opinion(1, _SUBSTANTIAL)]}  # index 0 缺席
    request = _request([_SUBSTANTIAL, _SUBSTANTIAL])
    with _stub_model(_SUMMARY_OK, opinion_payload):
        data = svc.generate_review_summary(request)
    assert data.opinion_details[0].summary is None
    assert data.opinion_details[1].summary == "第1条意见的摘要。"
    assert "opinion_details.model" in data.degraded_sections
    assert get_cached(make_cache_key(request)) is None


# ------------------------------------ 缺陷 E（s06 复现）：张冠李戴的归属闸（D16 结构层）
# s06 真实数据：总述写「财经复核与部门经理指出硬件部分亏损」，而 `财经复核` 名下
# 唯一意见的 comment 是空的，真正作者是与它只差一个字的 `合同复核`(index 5)。
# D15 曾按"沉默节点名逐字出现在文本里"检测，但 LTC 的节点名互成子串
# （`行业商务评审` ⊂ `二级行业商务评审`），文本空间里误判与漏判数学上不可兼得。
# D16 把归属搬到结构层：主题只交 `opinion_refs` 指针，名字由服务端反查派生；
# 文本层只留**负向校验**（G3）——句内点了名，就必须在这条主题自己的 refs 里（背书档），
# 否则未背书 → 定向重试一次 → 仍违规整条丢弃 + `review_summary.incomplete`。

_BAD_THEME = "节点1与节点0提出预付款比例偏低。"
_FIXED_THEME = "节点0提出预付款比例偏低。"
_GOOD_THEME = "要求提高预付款比例后方可推进。"


def _theme(text: str, refs: list[str]) -> dict:
    return {"text": text, "opinion_refs": refs}


def _draft(overall, *themes: dict) -> dict:
    return {"overall": overall, "themes": list(themes)}


def _batches(comment: str) -> dict:
    """归属用例的统一意见摘要批量（避免第三发拿错形状触发无关的 opinion_details.model）。"""
    return {"summaries": [_opinion(0, comment)]}


def test_theme_naming_an_unbacked_node_triggers_one_retry_and_model_fixes_it():
    """点名 refs 之外的节点（G3 未背书）→ 定向重试一次 → 模型改对：内容全留、可落缓存。"""
    request = _request(["要求提高预付款比例。", ""])
    with _stub_model(
        _draft(None, _theme(_BAD_THEME, ["opinions[0]"])),
        _draft(None, _theme(_FIXED_THEME, ["opinions[0]"])),
        _batches("要求提高预付款比例。"),
    ) as stub:
        data = svc.generate_review_summary(request)
    text = data.review_summary.text
    assert _FIXED_THEME.rstrip("。") in text and "节点1" not in text
    assert "review_summary.incomplete" not in data.degraded_sections
    assert data.degraded_sections == ["key_concerns"]
    assert get_cached(make_cache_key(request)) is not None
    assert len(stub.calls) == 3  # 首发 + 结构重试 + 意见摘要批量
    # 重试那一发只报可核验事实：点了哪个没背书的 name、这条主题的 refs 覆盖了谁
    retry_prompt = _prompt_text(stub, 1)
    assert "上一稿的结构问题" in retry_prompt
    assert "点名了未背书的节点：节点1" in retry_prompt
    assert "该主题的 refs 只覆盖 节点0" in retry_prompt
    # 首发没有结构问题可说，定向修正要求留空
    assert "上一稿的结构问题" not in _prompt_text(stub, 0)


def test_retry_still_unbacked_drops_the_whole_theme_and_marks_incomplete():
    """重试仍不改：**整条主题丢弃**（不删名改句），其余主题照常返回 + `.incomplete` + 不落缓存。"""
    request = _request(["要求提高预付款比例。", ""])
    both = _draft(
        None,
        _theme(_BAD_THEME, ["opinions[0]"]),
        _theme(_GOOD_THEME, ["opinions[0]"]),
    )
    with _stub_model(both, both, _batches("要求提高预付款比例。")) as stub:
        data = svc.generate_review_summary(request)
    text = data.review_summary.text
    assert _BAD_THEME not in text and "节点1" not in text
    assert _GOOD_THEME.rstrip("。") in text  # 合法主题一条不陪葬
    assert [t.text for t in data.review_summary.themes] == [_GOOD_THEME]
    assert "review_summary.incomplete" in data.degraded_sections
    assert "review_summary.fallback" not in data.degraded_sections  # 仍是 AI 稿，只是缺角
    assert get_cached(make_cache_key(request)) is None
    assert len(stub.calls) == 3  # 只重试一次，不做二次拉扯


def test_retry_call_failure_keeps_the_first_draft_instead_of_failing_the_panel():
    """重试这一发炸了（格式异常）：不外抛 500、不弃稿，沿用首稿的复检结果丢弃违规主题。"""
    from app.core.errors import ModelFormatError

    request = _request(["要求提高预付款比例。", ""])
    with _stub_model(
        _draft(None, _theme(_BAD_THEME, ["opinions[0]"]), _theme(_GOOD_THEME, ["opinions[0]"])),
        ModelFormatError("boom"),
        _batches("要求提高预付款比例。"),
    ):
        data = svc.generate_review_summary(request)
    assert _BAD_THEME not in data.review_summary.text
    assert _GOOD_THEME.rstrip("。") in data.review_summary.text
    assert "review_summary.incomplete" in data.degraded_sections


def test_same_named_node_with_any_written_opinion_is_endorsed():
    """两个同名节点、其中一个写过字：refs 指向有字那条，点名该名字即成立（不重试、不丢弃）。"""
    request = ReviewSummaryRequest.model_validate(
        {
            "contract_meta": {"contract_type": "软件集成", "contract_amount": "14480000 CNY"},
            "route_reason": None,
            "risk_register": [],
            "opinions": [
                {
                    "node_name": "部门经理",
                    "approver_name": "评审人0",
                    "role": "部门经理",
                    "action": "通过",
                    "comment": "执行利润率需提升",
                    "submitted_at": None,
                },
                {
                    "node_name": "部门经理",
                    "approver_name": "评审人1",
                    "role": "部门经理",
                    "action": "通过",
                    "comment": "",
                    "submitted_at": None,
                },
            ],
        }
    )
    theme = _theme("部门经理提出执行利润率需提升。", ["opinions[0]"])
    with _stub_model(_draft(None, theme), _batches("执行利润率需提升")) as stub:
        data = svc.generate_review_summary(request)
    assert "部门经理提出执行利润率需提升" in data.review_summary.text
    assert data.review_summary.themes[0].opinion_refs == ["opinions[0]"]
    assert "review_summary.incomplete" not in data.degraded_sections
    assert len(stub.calls) == 2  # 没有多余的归属重试


def test_node_name_scanning_prefers_the_longest_name_and_render_never_doubles_it():
    """节点名互成子串（s05）时按最长匹配取名，不留半截名；文本已点过的名不再附后缀。"""
    names = ["行业商务评审", "二级行业商务评审"]
    assert svc._find_node_name_mentions("二级行业商务评审要求补充仲裁地。", names) == [
        "二级行业商务评审"
    ]
    assert svc._find_node_name_mentions("行业商务评审与二级行业商务评审均要求降价。", names) == [
        "行业商务评审",
        "二级行业商务评审",
    ]
    assert svc._find_node_name_mentions("要求补充仲裁地。", names) == []
    # 渲染后缀去重：句内已逐字点名的节点不再重复附在括号里
    request = _request(["要求提高预付款比例。"])
    theme = svc._Theme(text="节点0要求提高预付款比例。", indexes=[0])
    assert svc._theme_segment(theme, request, svc._node_names(request)) == "节点0要求提高预付款比例"
    other = svc._Theme(text="要求提高预付款比例。", indexes=[0])
    assert svc._theme_segment(other, request, svc._node_names(request)) == "要求提高预付款比例（节点0）"


def test_summary_prompt_requires_backed_node_names():
    """prompt 端把归属规则写成硬要求：名字逐字取自 node_name，且只点自己 refs 里的节点。"""
    with _stub_model(_SUMMARY_OK, {"summaries": []}) as stub:
        svc.generate_review_summary(_request(["要求提高预付款比例。"]))
    prompt = _prompt_text(stub, 0)
    assert "逐字取自意见原文的 `node_name`" in prompt
    assert "只点这条主题自己 `opinion_refs` 里出现的节点" in prompt
    assert "未背书" in prompt
    assert "定向修正要求" in prompt
