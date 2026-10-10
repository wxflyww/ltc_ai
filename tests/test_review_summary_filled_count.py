"""D18 系列：②分布句由服务端装配"其中 N 条填写了意见"（2026-10-10，真机第七/八枪的代答病根）。

触发事实（三条，逐条对应下面的用例）：
1. **prompt 从不告诉模型有几条意见写了字、几条没写**——`_coverage_note` 只列有字意见清单，
   `_distribution_note` 只给结论分布。s05/s09 的 `overall` 收尾那句"其余节点无实质异议"
   "其余为执行层面提醒"，填的正是这个**事实真空**：模型想知道、输入里又没有、服务端也没说，
   于是替缺席者断言立场。D16.4 的词表闸拦不住（换词即绕过），只观测的正则族又漏了代词用法。
2. 与缺陷 C / D9 同族的纪律：**服务端算出来再喂给模型的确定性事实，必须同时进数字语料**，
   否则模型照抄自己被判编造。`_input_number_corpus` 本就含分布注记，所以条数进 ② 是安全的。
3. 与 D16.1-I1 同族的纪律：②分布句**只有一份措辞**——面板、prompt 注记、兜底稿共用
   `_distribution_sentence`，新增的"其中 N 条填写了意见"也必须跟着这一份走，不许第三处再拼。

陈述方向（用户 2026-10-10 口令，覆盖 D18 初版的"其中 N 条未填写意见"写法）：②句说
**填写了意见的条数**，不说未填写的条数。理由是给审批人读的是"这份评审有多少实质内容"，
正向数才是他要的信息；缺席者仍然一个都不替他们表态（未填写的条数由"共 M 条 − N 条"可推，
事实真空照样补上，代答的素材照样不存在）。

本轮口径不变（用户拍板"观测 + 装配，先不升闸"）：只把事实装配进服务端自己写的那句，
**不新增拦截、不新增标记、不动契约字段**；升闸与否等下一轮真实分布。
"""
import json
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from app.capabilities.review_summary import prompts as p
from app.capabilities.review_summary import service as svc
from app.capabilities.review_summary.cache import clear_cache
from app.capabilities.review_summary.schemas import ReviewSummaryRequest

# ①合同要素句在本工程根 fixture 下的确定成稿
_ELEMENT = "该合同为硬件集成合同，合同总额 ¥126 万元，综合毛利率 27.7%"


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


def _prompt_text(stub: _Stub, call_index: int) -> str:
    return "\n".join(str(m.content) for m in stub.calls[call_index]["messages"])


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


def _request(opinions) -> ReviewSummaryRequest:
    return ReviewSummaryRequest.model_validate(
        {
            "contract_meta": {
                "contract_type": "硬件集成",
                "contract_amount": "¥126 万元",
                "gross_margin": "27.7%",
            },
            "route_reason": {"text": "合同总额超过 ¥100 万，触发副总经理终审"},
            "risk_register": [],
            "opinions": opinions,
        }
    )


def _theme(text: str, refs: list[str]) -> dict:
    return {"text": text, "opinion_refs": refs}


def _draft(overall, *themes) -> dict:
    return {"overall": overall, "themes": list(themes)}


def _clean_batch(request: ReviewSummaryRequest) -> dict:
    return {
        "summaries": [
            {
                "index": index,
                "summary": "要求补充仲裁地后方可签署。",
                "source_refs": [f"opinions[{index}]"],
            }
            for index, opinion in enumerate(request.opinions)
            if opinion.comment.strip()
        ]
    }


_MIXED = lambda: _request(
    [
        _op("法务评审", "要求补充仲裁地后方可签署。", "有条件通过"),
        _op("税务评审", "开票须按软件产品标准名称执行。"),
        _op("财经复核", "", "通过"),
    ]
)


# ------------------------------------------------ 必测 1：填写条数进入 ②分布句


def test_filled_comment_count_is_appended_to_the_distribution_sentence():
    """有 1 条空 `comment` → ②句尾给出**填写了意见的条数**（正向计数，缺席条数由读者可推）。"""
    assert svc._distribution_sentence(_MIXED()) == (
        "共 3 条意见：有条件通过 1 条、通过 2 条，其中 2 条填写了意见"
    )


def test_distribution_sentence_unchanged_when_every_reviewer_wrote():
    """反噪声锁：全员有字时 ②句一字不改——旧断言、旧回放不受本轮影响。"""
    request = _request(
        [_op("法务评审", "要求补充仲裁地。"), _op("税务评审", "开票按标准名称执行。")]
    )
    assert svc._distribution_sentence(request) == "共 2 条意见：通过 2 条"


def test_all_blank_still_reports_both_counts():
    """全员没写字时更要说清（真实导出里 435 行仅 141 行有字）：正向计数为 0 也照实写。"""
    request = _request([_op("法务评审", ""), _op("税务评审", "")])
    assert svc._distribution_sentence(request) == (
        "共 2 条意见：通过 2 条，其中 0 条填写了意见"
    )


# ----------------------------------------- 必测 2：单一口径（D16.1-I1 同族）


def test_filled_count_reaches_panel_prompt_and_fallback_from_one_source():
    """面板 ②、prompt「结论分布」注记、服务端兜底稿三处共用同一句，不许第三份措辞。"""
    request = _MIXED()
    sentence = svc._distribution_sentence(request)
    draft = _draft("意见集中在仲裁地与开票口径两处。", _theme("要求补充仲裁地。", ["opinions[0]"]))
    with _stub_model(draft, _clean_batch(request)) as stub:
        data = svc.generate_review_summary(request)
    assert sentence in data.review_summary.text
    assert sentence in _prompt_text(stub, 0)
    assert sentence in svc._fallback_summary_text(request)


def test_server_only_section_carries_the_filled_count():
    """零模型调用分支（无有字意见）同样装配该事实：审批人据此明白"没有总结"是因为没人写字。"""
    request = _request([_op("法务评审", ""), _op("税务评审", "")])
    with _stub_model() as stub:
        data = svc.generate_review_summary(request)
    assert len(stub.calls) == 0
    assert "共 2 条意见：通过 2 条，其中 0 条填写了意见。" in data.review_summary.text
    assert data.degraded_sections == []  # 空态由输入事实决定，不因本轮装配改动而新增标记


# --------------------------------------- 必测 3：注入的数字必须已在语料里（缺陷 C / D9）


def test_the_filled_count_is_already_in_the_number_corpus():
    """模型照抄服务端给的条数属于溯源成功：`_input_number_corpus` 含分布注记 → 新数字自动在射程内。

    这里刻意挑一个**除该子句外别处都不存在**的数字（4 条填写 / 共 5 条，输入其余部分只有
    126、27.7%、100 万），否则用例会被分布句里其他计数蒙对。
    """
    request = _request(
        [
            _op("法务评审", "要求补充仲裁地后方可签署。"),
            _op("税务评审", "开票须按软件产品标准名称执行。"),
            _op("财经复核", "确认利润率无变化。"),
            _op("开发评审", "接口维保期按标准条款执行。"),
            _op("合同复核", ""),
        ]
    )
    corpus = svc._input_number_corpus(request)
    assert "其中 4 条填写了意见" in corpus
    assert svc._unverifiable_numbers("5 条意见里 4 条填写了意见。", corpus) == []


def test_a_number_the_server_never_states_is_still_caught():
    """反放宽锁：装配的是"填写意见条数"，不等于语料对所有数字开门。"""
    request = _MIXED()
    corpus = svc._input_number_corpus(request)
    assert svc._unverifiable_numbers("其余 888 条意见均无异议。", corpus) == ["888"]


def test_the_derivable_but_unstated_blank_count_is_still_caught():
    """口径只翻方向，不翻判据：②说"2 条填写了意见"，"未填写"的那 1 条是推论不是逐字事实——
    模型若自造带数字的未填写句，数字闸照常拦（闸是逐字比对，不做减法）。
    """
    request = _request(
        [
            _op("法务评审", "要求补充仲裁地后方可签署。"),
            _op("税务评审", "开票须按软件产品标准名称执行。"),
            _op("财经复核", "确认利润率无变化。"),
            _op("开发评审", "接口维保期按标准条款执行。"),
            _op("合同复核", ""),
        ]
    )
    corpus = svc._input_number_corpus(request)
    assert svc._unverifiable_numbers("其余 3 条未填写意见。", corpus) == ["3"]


# --------------------------------- 必测 4：prompt 侧——事实已在注记里，收尾不该自己编


def test_prompt_tells_the_model_the_distribution_block_is_server_assembled():
    """代答禁令里点明：②段已写明未填写意见条数，模型不需要为收尾而自造事实。"""
    p._reset_template()
    system = p._load_template()["summary"]["system"]
    assert "②段已由服务端装配" in system
    assert "未填写意见" in system


def test_prompt_overall_example_no_longer_teaches_a_collective_closing():
    """病根锁：s09 的 overall 逐字照抄了 prompt 范例尾句"其余为执行层面提醒"——
    范例本身就是代答形态时，禁令与范例互相打架，模型跟着范例走。范例必须去掉集体指代收尾。"""
    p._reset_template()
    system = p._load_template()["summary"]["system"]
    assert "其余为执行层面提醒" not in system
