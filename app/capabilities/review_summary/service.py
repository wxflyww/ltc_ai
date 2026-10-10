"""评审智能总结业务：装配区 + 两处 AI 生成 + 服务端结构闸校验 + 空态降级 + 缓存。

分层（设计文档 §2.2 / §2.3 / §5.1，change design.md D4/D6/D16）：

- **装配区**（`key_concerns`、`opinion_details` 骨架，以及总述的 ①合同要素句 / ②结论分布句）
  纯确定性、零模型参与，输入原文照搬；
- **AI 生成只有两处**：总述的**主题层**（`themes[] = {text, opinion_refs}` + 一句 `overall`）与
  `opinion_details[].summary`（意见摘要，一次调用批量生成，按 index 一一对应）；
- **归属不再靠文本猜**（缺陷 F 的收口，change design.md D16）：主题句点名谁由服务端从
  `opinion_refs` 反查 `opinions[i].node_name` 派生渲染，D15 的文本归属闸（沉默节点名匹配）
  整体拆除——节点名互成子串是 LTC 数据常态，文本空间里误判与漏判数学上不可兼得；
- **服务端结构闸**：G1 引用逐条剔除（剩 0 才违规，D16.1-R3）、G2 引用不得指向空意见、
  G3 句内点名必须被该主题自己的 refs 背书（D16.1-R2 两档）、G4 漏纳**只观测**（不扳闸、
  不打标记、不旁路缓存——否则就是惩罚模型遵守"容量有限、按关键性取舍"这条契约，D16.1-R1）；
  数字抽验与「不通过」中性化照旧逐主题 + overall 强制（铁律 1/5）；**代答抽验**（D16.4）同样
  逐主题 + overall：正面定性短语在任何一条 `comment` 里都找不到，即"没有评审人说过这话"，
  与语料外数字同构，但判据更窄（只认评审人亲手写的字）；词表按逐字子串比对，"无实质异议"
  这类插字变体是**已知漏判**，同类集体指代目前只观测不扳闸（D16.6）；
- **处置阶梯**（D16 / D16.2）：**结构**违规（形状失守 / G1 剩 0 / G2 / G3 未背书）→ 定向重试 1 次
  （话术只含可核验事实，内容违规与漏纳只搭车出现）→ 两稿各跑复检、取合法主题数多者（并列取
  首稿）→ 仍违规的主题**丢弃**（不删名改句）→ 丢弃过主题打 `review_summary.incomplete` →
  一条不剩才由服务端中性兜底稿顶上并打 `review_summary.fallback`；**内容**违规（语料外数字、
  无出处正面定性代答、reject 下的正面定性）不扳重试，沿用"内容违规直接判失败"的旧口径，
  只在主题粒度上丢弃；
  overall 单独违规只丢 overall、不打标记不重试；
- **同源合并**（D17）：`opinion_refs` 完全相同的主题由服务端按**首次出现位置**用"，"拼成一条——
  模型写的句子一字不删，省掉的只是重复的节点名后缀；合并发生在复检与两稿取优之后，故被丢弃的主题
  不会因同源被救回，而合并结果对四道闸封闭（无新数字、跨句拼不出正面定性短语、名字集合不变）；
  合并后仍超过 4 条**只观测**（`review-summary 容量观测`），不丢弃、不打标记；拼完超过 100 字的
  整组**不合并**——合并的目的是消掉重复后缀，不是造一条 D13 裁尾切不动的长句（红线"降级不丢内容"优先）；
- **长度**：200 字只写进 prompt 当目标；服务端红线 300 字作用于**拼接后全文**，超红线**按整句
  从尾部裁**而不整段弃用（D13），只有整句切不开（首句即超限或裁完不足两句）才退回兜底稿；
- **意见摘要的 null 语义**：模型按 prompt 契约对"同意。"这类近空意见显式返回 `summary: null`
  不算丢弃、不打标记、不旁路缓存；只有**漏交 index** 才算真丢弃（s06 缺陷 D，D16.1 沿用）；
- **错误码复用** 20001（调用失败）/ 20002（超时）/ 20003（格式异常），不新增。
"""
import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.capabilities.review_summary.cache import get_cached, make_cache_key, set_cached
from app.capabilities.review_summary.prompts import (
    build_prompt,
    get_response_format,
    parse_json_object,
)
from app.capabilities.review_summary.schemas import (
    EscalationConcern,
    OpinionDetail,
    ReviewSummaryData,
    ReviewSummaryRequest,
    ReviewSummarySection,
    RiskConcern,
    RiskMeasure,
    SummaryTheme,
)
from app.core.errors import AppError, ModelFormatError, ModelInvocationError
from app.core.logging import get_logger
from app.models.llm import get_chat_model, invoke_model

logger = get_logger("review_summary")

# 业务层仅对「解析失败」重试 1 次（设计 §6）；调用失败与内容违规均不重试。
MAX_PARSE_ATTEMPTS = 2

# 关思考唯一有效法：bind(extra_body=...)。bind 返回新对象，不污染 get_chat_model() 单例。
_THINKING_OFF_EXTRA_BODY = {"chat_template_kwargs": {"enable_thinking": False}}

# degraded_sections 标记名（设计 §5.1 空态矩阵 + change design.md D4 模型丢弃标记）
DEGRADED_KEY_CONCERNS = "key_concerns"
DEGRADED_OPINION_DETAILS = "opinion_details"
DEGRADED_SUMMARY_OPINIONS = "review_summary.opinions"
DEGRADED_SUMMARY_MODEL = "review_summary.model"
DEGRADED_OPINION_MODEL = "opinion_details.model"

# 总述长度：200 字写进 prompt 当目标值（不强校验），300 字是服务端红线。
# 红线之上不整段弃用，而是 `_trim_to_sentences` 按整句裁尾——用户口径：
# "先不限制字数了，但也不能像现在这样罗列。我担心限制字数又被弃用了，
#  那仅有的 AI 能力就没有了。"（2026-10-08，s06 总述 407 字）
# 红线作用于**拼接后的全文**（含服务端装配的 ①② 与名字后缀，change design.md D16.1-I5）。
_SUMMARY_TARGET_CHARS = 200
_SUMMARY_HARD_LIMIT = 300
_SENTENCE_ENDS = "。！？；"
_TERMINALS = ("。", "！", "？")
_TRIM_MIN_SENTENCES = 2
# 主题条数的 prompt 目标——**不是闸**（真机允许超额出稿，服务端只收同源 + 观测超量，D17）。
_THEME_TARGET_COUNT = 4
# 同源主题合并的连接符：刻意用**非句末标点**。合并后的主题必须仍是 D13 整句裁尾的原子单位——
# 用"；"连接会让尾部裁在主题中间，留下半条没有节点名后缀的句子（`_kept_after_trim` 靠整段匹配）。
_THEME_MERGE_JOIN = "，"
# 合并后主题句的字数预算：两条 40 字主题拼起来约 80 字，留标点余量取 100。超过即整组不合并，
# 让 D13 的整句裁尾继续逐条削——合并是为了消掉重复的节点名后缀，不是为了造一条切不动的长句。
_MERGED_THEME_MAX_CHARS = 100
# 总述 AI 稿被弃用、改由服务端中性兜底稿顶上（2026-10-08 A+B 契约：总述不得为空）。
# 与 `.model` 的区别：`.model` = 该区块内容缺失；`.fallback` = 内容在，但不是 AI 写的。
DEGRADED_SUMMARY_FALLBACK = "review_summary.fallback"
# 总述的 AI 稿通过校验、但其中有主题被服务端丢弃（重试仍未改对）：内容在、仍是 AI 写的，
# 只是归并视图缺了一角。与 `.fallback` 的区别必须让前端读得出来——"覆盖不全，内容仍是 AI 稿"
# vs"非 AI 稿"（change design.md D16 / D16.1-R1：只在**真丢弃过主题**时打，漏纳不算）。
DEGRADED_SUMMARY_INCOMPLETE = "review_summary.incomplete"

# 输出顺序固定，便于前端与用例断言（去重后按此序输出）
_DEGRADED_ORDER = (
    DEGRADED_KEY_CONCERNS,
    DEGRADED_OPINION_DETAILS,
    DEGRADED_SUMMARY_OPINIONS,
    DEGRADED_SUMMARY_MODEL,
    DEGRADED_SUMMARY_FALLBACK,
    DEGRADED_SUMMARY_INCOMPLETE,
    DEGRADED_OPINION_MODEL,
)

# 存在「不通过」意见时，总述出现下列正面定性即判违规（铁律 5）
_POSITIVE_TONE_PHRASES = (
    "整体认可",
    "一致认可",
    "普遍认可",
    "高度认可",
    "充分认可",
    "整体看好",
    "一致看好",
    "普遍看好",
    "一致同意",
    "一致通过",
    "整体通过",
    "充分肯定",
    "高度肯定",
    "无异议",
    "一致推荐",
    "整体评价良好",
    "评价积极",
    "认可该单价值",
)

_CONTRACT_META_FIELDS = ("contract_type", "contract_amount", "gross_margin")
_RISK_FIELDS = (
    "risk_id",
    "title",
    "level",
    "source",
    "description",
    "standard_clause",
    "potential_impact",
    "measure_type",
    "measure_desc",
    "decision_type",
    "decision_note",
    "decision_by",
)
_OPINION_FIELDS = ("node_name", "approver_name", "role", "action", "comment", "submitted_at")

# 铁律 5 扳机词：仅「不通过」逐字生效（action 废除枚举后无翻译层，词表外动作词
# 如"驳回"不触发中性化闸——fail-open 口径登记接口调用文档，change design.md D7）。
_REJECT_ACTIONS = frozenset({"不通过"})

_ABSENT = "（未提供）"
_NO_OPINIONS = "（评审意见尚未提交）"
_NO_RISKS = "（无高风险项）"


# --------------------------------------------------------------------- 入口


def generate_review_summary(request: ReviewSummaryRequest) -> ReviewSummaryData:
    """生成评审智能总结整包面板；命中输入 hash 缓存时直接返回既有结果。"""
    cache_key = make_cache_key(request)
    cached = get_cached(cache_key)
    if cached is not None:
        logger.debug("review-summary 缓存命中", extra={"cache_key": cache_key[:12]})
        return ReviewSummaryData.model_validate(cached)

    data = _build_panel(request)
    # AI 质量降级（摘要丢弃 `.model`、总述走兜底稿 `.fallback`）不落缓存：模型输出有
    # 随机性，钉死这一次的结果会让同一输入永远拿不到 AI 稿。空态降级由输入决定，可安全缓存。
    if _is_cacheable(data):
        set_cached(cache_key, data.model_dump(mode="json"))
    return data


def _is_cacheable(data: ReviewSummaryData) -> bool:
    """兜底稿、主题有缺口的稿与含丢弃标记的响应都不落缓存；纯输入决定的空态可以。

    三种 AI 质量降级（`.model` / `.fallback` / `.incomplete`）都意味着"这一发的模型成稿
    不理想"，钉死它会让同一输入永远拿不到更好的主题；漏纳（G4）不打标记，所以照常缓存
    （change design.md D16.1-R1：服务端不得惩罚模型遵守契约）。
    """
    if DEGRADED_SUMMARY_FALLBACK in data.degraded_sections:
        return False
    if DEGRADED_SUMMARY_INCOMPLETE in data.degraded_sections:
        return False
    return not any(marker.endswith(".model") for marker in data.degraded_sections)


def _build_panel(request: ReviewSummaryRequest) -> ReviewSummaryData:
    degraded: set[str] = set()

    # 1) 装配区：纯确定性，零模型参与
    key_concerns = _assemble_key_concerns(request)
    opinion_details = _assemble_opinion_details(request)
    if not key_concerns:
        degraded.add(DEGRADED_KEY_CONCERNS)
    if not request.opinions:
        degraded.add(DEGRADED_OPINION_DETAILS)
        degraded.add(DEGRADED_SUMMARY_OPINIONS)

    # 2) AI 生成两处（共用一次 bind 出来的模型对象）
    valid_refs = _collect_valid_refs(request)
    valid_ref_set = set(valid_refs)
    corpus = _input_number_corpus(request)
    model = _bound_model()
    review_summary = _generate_summary(request, model, valid_refs, valid_ref_set, corpus, degraded)
    _apply_opinion_summaries(request, opinion_details, model, valid_refs, valid_ref_set, corpus, degraded)

    return ReviewSummaryData(
        review_summary=review_summary,
        key_concerns=key_concerns,
        opinion_details=opinion_details,
        degraded_sections=_ordered_degraded(degraded),
    )


def _ordered_degraded(marked: set[str]) -> list[str]:
    return [name for name in _DEGRADED_ORDER if name in marked]


# ------------------------------------------------------------------- 装配区


def _assemble_key_concerns(request: ReviewSummaryRequest) -> list[Any]:
    """提级块固定置首（装配规则，非业务加工），风险项按传入数组顺序跟排。"""
    concerns: list[Any] = []
    if request.route_reason is not None:
        concerns.append(EscalationConcern(text=request.route_reason.text))
    for risk in request.risk_register:
        measure = None
        if risk.measure_type is not None or risk.measure_desc is not None:
            measure = RiskMeasure(measure_type=risk.measure_type, measure_desc=risk.measure_desc)
        concerns.append(
            RiskConcern(
                risk_id=risk.risk_id,
                title=risk.title,
                level=risk.level,  # 原样展示，不做枚举映射
                source=risk.source,
                description=risk.description,
                standard_clause=risk.standard_clause,
                potential_impact=risk.potential_impact,
                decision_type=risk.decision_type,
                decision_by=risk.decision_by,
                decision_note=risk.decision_note,
                measure=measure,
            )
        )
    return concerns


def _assemble_opinion_details(request: ReviewSummaryRequest) -> list[OpinionDetail]:
    """意见详情骨架按传入顺序逐条输出；`source_ref` 是指向 opinions[i] 的确定性指针。"""
    return [
        OpinionDetail(
            node_name=opinion.node_name,
            approver_name=opinion.approver_name,
            role=opinion.role,
            action=opinion.action,
            summary=None,  # 由 _apply_opinion_summaries 填充；校验不过则保持 null
            source_ref=f"opinions[{index}]",
        )
        for index, opinion in enumerate(request.opinions)
    ]


# ------------------------------------------------------------- prompt 输入块


def _present_fields(model_obj: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {name: getattr(model_obj, name) for name in fields if getattr(model_obj, name) is not None}


def _dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _contract_meta_block(request: ReviewSummaryRequest) -> str:
    if request.contract_meta is None:
        return _ABSENT
    present = _present_fields(request.contract_meta, _CONTRACT_META_FIELDS)
    return _dumps(present) if present else _ABSENT


def _route_reason_block(request: ReviewSummaryRequest) -> str:
    if request.route_reason is None:
        return _ABSENT
    return request.route_reason.text


def _risk_register_block(request: ReviewSummaryRequest) -> str:
    if not request.risk_register:
        return _NO_RISKS
    return _dumps(
        [
            {"index": index, **_present_fields(risk, _RISK_FIELDS)}
            for index, risk in enumerate(request.risk_register)
        ]
    )


def _opinions_block(
    request: ReviewSummaryRequest, *, only_with_comment: bool = False
) -> str:
    """意见输入块。不注入 `action_label` 等清单外的派生键——模型只会逐字引用
    输入里见过的路径，注入即诱导悬空误杀（5.4 联调缺陷 A）。
    `only_with_comment` 供批量摘要使用：空 comment 不进输入、不占 token（缺陷 B）。"""
    entries = [
        (index, opinion)
        for index, opinion in enumerate(request.opinions)
        if not (only_with_comment and not opinion.comment.strip())
    ]
    if not entries:
        return _NO_OPINIONS
    return _dumps(
        [
            {"index": index, **_present_fields(opinion, _OPINION_FIELDS)}
            for index, opinion in entries
        ]
    )


def _distribution_sentence(request: ReviewSummaryRequest) -> str | None:
    """②结论分布句的**唯一事实口径**（change design.md D16.1-I1、D18）。

    面板 ②、prompt 注记、服务端兜底稿三处共用这一句，不许出现第三份措辞；本函数只产
    事实，给模型的指令一律留在 `_distribution_note` 里附加，绝不进面板。
    结论分布按**传入原值**计数（action 无枚举无翻译，D7）。
    尾部的"其中 N 条填写了意见"（D18，2026-10-10 用户口令把陈述方向从"未填写"改为"填写"）
    同样是一句**服务端算得出的确定事实**，写在这里而不是让模型去猜：prompt 原先只给有字意见
    清单、从不提有多少条意见写了字，这个事实真空正是代答句（"其余节点无异议""其余为执行层面
    提醒"）填进去的位置——真机 3 例代答全在补这个洞。
    为什么报**填写条数**而不是**未填写条数**：审批人读 ② 段要的是"这份评审有多少实质内容"，
    正向计数直接给答案；缺席条数由"共 M 条 − N 条"确定可推，事实真空照样补上，而服务端依旧
    不替任何没写字的节点断言立场。措辞是中性事实陈述，不落在 `_POSITIVE_TONE_PHRASES` 上。
    数字与"共 N 条"同经 `_distribution_note` 进入 `_input_number_corpus`（缺陷 C / D9 教训），
    模型照抄属于溯源成功；反过来**未填写**条数现在②段不再逐字出现，模型若自己写出那个数字
    会被数字闸按"语料外数字"拦下（闸只做逐字比对、不做减法）——这是口径翻转的已知副作用，
    合法句式"其余节点未填写意见"不带数字，因此不受影响。
    全员有字时整句不追加（反噪声，也保住既有回放逐字不变）。
    """
    if not request.opinions:
        return None
    counts: dict[str, int] = {}
    for opinion in request.opinions:
        counts[opinion.action] = counts.get(opinion.action, 0) + 1
    distribution = "、".join(f"{action} {count} 条" for action, count in counts.items())
    sentence = f"共 {len(request.opinions)} 条意见：{distribution}"
    written = len(_written_opinion_indexes(request))
    if written != len(request.opinions):
        sentence += f"，其中 {written} 条填写了意见"
    return sentence


def _distribution_note(request: ReviewSummaryRequest) -> str:
    """给模型的「结论分布」注记 = 事实句 + 退化指令（指令只进 prompt，不进面板）。

    reject 场景的指令句仅当出现「不通过」逐字值时给出——词表外动作词（如"驳回"）
    闸静默不触发（fail-open，口径已登记接口调用文档，change design.md D7）。
    """
    sentence = _distribution_sentence(request)
    if sentence is None:
        return "本次评审意见尚未提交：总述只陈述已传入的合同要素等事实，不得概括任何评审意见。"
    note = f"{sentence}。"
    if _has_reject(request):
        note += (
            "存在不通过意见，你写的每一句（含 overall 与主题句）必须退化为中性陈述："
            "只列事实 + \"评审意见存在分歧\"类客观描述，禁止任何正面定性。"
        )
    return note


def _written_opinion_indexes(request: ReviewSummaryRequest) -> list[int]:
    """`comment` 写了字的意见下标（确定性事实，不看模型脸色）。"""
    return [index for index, opinion in enumerate(request.opinions) if opinion.comment.strip()]


def _coverage_note(request: ReviewSummaryRequest) -> str:
    """给模型的「有字意见清单」——容量感知口径（change design.md D16.2-R5）。

    主题容量是 ≤4 主题 × ≤3 引用 = 12 条，而有字意见可以远多于它（真实导出见过 141 条），
    所以这里写"优先覆盖其中关键者、装不下按关键性取舍、未纳入者由意见详情承载、不算违约"，
    **不写"必须纳入"**——那是一条结构上不可满足的承诺，等于把产品矛盾塞给模型背锅。
    """
    written = _written_opinion_indexes(request)
    if not written:
        return "（本次没有写过实质内容的评审意见：themes 输出 []、overall 输出 null）"
    listed = "、".join(f"opinions[{index}]" for index in written)
    return (
        f"有字意见清单：{listed}——请优先覆盖其中关键者；"
        "容量有限（最多 4 个主题、每主题最多 3 条引用），装不下时按关键性取舍，"
        "未纳入者由「各节点意见详情」逐条承载，不算你的违约；"
        "只写\u201c同意\u201d\u201c无异议\u201d一类的无需单独成主题。"
    )


def _node_names(request: ReviewSummaryRequest) -> list[str]:
    """全部节点名（去空、去重、按传入顺序）——G3 点名扫描的词表。"""
    names: list[str] = []
    for opinion in request.opinions:
        name = (opinion.node_name or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _find_node_name_mentions(text: str, names: list[str]) -> list[str]:
    """最大匹配扫描文本里出现的节点名（逐位置取最长命中，整段跳过、不留半截名）。

    为什么必须最长优先：真实数据里节点名互成子串（s05 的 `二级行业商务评审` ⊃
    `行业商务评审`），短名优先会在正确长名内部命中短名——D15 的死循环就是这么来的。
    本函数只回答"这句话点了哪些名"（G3 的负向背书校验），不承担归属判定
    （归属的权威判据是 `opinion_refs`，change design.md D16.2-R6）。
    """
    by_length: dict[int, set[str]] = {}
    for name in names:
        if name:
            by_length.setdefault(len(name), set()).add(name)
    if not by_length or not text:
        return []
    lengths = sorted(by_length, reverse=True)
    mentions: list[str] = []
    position = 0
    while position < len(text):
        for length in lengths:
            chunk = text[position : position + length]
            if chunk in by_length[length]:
                if chunk not in mentions:
                    mentions.append(chunk)
                position += length
                break
        else:
            position += 1
    return mentions


def _collect_valid_refs(request: ReviewSummaryRequest) -> list[str]:
    """枚举全部可溯源的输入字段路径；未传入的字段不进清单（引用它即悬空）。

    数组只生成实际存在的下标，因此 `opinions[9]`（越界）天然落在清单外。
    """
    refs: list[str] = []
    if request.contract_meta is not None:
        present = _present_fields(request.contract_meta, _CONTRACT_META_FIELDS)
        if present:
            refs.append("contract_meta")
            refs.extend(f"contract_meta.{name}" for name in present)
    if request.route_reason is not None:
        refs.extend(["route_reason", "route_reason.text"])
    for index, risk in enumerate(request.risk_register):
        refs.append(f"risk_register[{index}]")
        refs.extend(f"risk_register[{index}].{name}" for name in _present_fields(risk, _RISK_FIELDS))
    for index, opinion in enumerate(request.opinions):
        refs.append(f"opinions[{index}]")
        refs.extend(f"opinions[{index}].{name}" for name in _present_fields(opinion, _OPINION_FIELDS))
    if request.opinions:
        refs.append("opinions")  # 数组聚合路径：兜底稿的条数分布引用它
    return refs


def _refs_block(valid_refs: list[str]) -> str:
    if not valid_refs:
        return "（无可用引用路径）"
    return "\n".join(f"- {ref}" for ref in valid_refs)


# ------------------------------------------------------------------ 模型调用


def _bound_model():
    """取共享单例并关闭思考；bind 返回新对象，`get_chat_model()` 单例不受影响。"""
    return get_chat_model().bind(extra_body=dict(_THINKING_OFF_EXTRA_BODY))


def _invoke_json(model: Any, prompt_name: str, **kwargs) -> dict:
    """调模型并解析 JSON。仅解析失败重试 1 次；调用失败不重试，错误码原样映射。"""
    messages = build_prompt(prompt_name, **kwargs)
    response_format = get_response_format(prompt_name)
    last_error: ModelFormatError | None = None
    for attempt in range(MAX_PARSE_ATTEMPTS):
        try:
            content, _usage = invoke_model(model, messages, response_format=response_format)
        except AppError:
            # ModelTimeoutError(20002) 与 ModelInputTooLong/OutputTooLong(20003) 保持原码
            raise
        except Exception as err:  # noqa: BLE001
            raise ModelInvocationError(str(err)) from err
        try:
            return parse_json_object(content)
        except ModelFormatError as err:
            last_error = err
            logger.warning(
                "模型输出解析失败，重试",
                extra={"prompt": prompt_name, "attempt": attempt + 1},
            )
    assert last_error is not None  # 循环至少执行一次
    raise last_error


# -------------------------------------------------------------- AI 生成与校验


def _refs_are_valid(refs: Any, valid_ref_set: set[str]) -> bool:
    """无引用、非字符串、引用悬空（含数组越界）一律判不合规。"""
    if not isinstance(refs, list) or not refs:
        return False
    return all(isinstance(ref, str) and ref.strip() in valid_ref_set for ref in refs)


# 铁律 1 服务端抽验：AI 文本中的阿拉伯数字 token 必须能在输入原文（含服务端注入的
# 派生文本）逐字找到。覆盖「编造/抄错数字」主事故形态；中文数字（"两期"）与单位换算
# 改写（"120 天"→"4 个月"）不在射程（change design.md D6），由 prompt 第一道防线兜底。
# 带 % 的 token 整串比对，"15%" 不会被输入里的 "15.5%" 放行；短数字借长数字子串蒙混
# （如日期里的 "25"）属已知宽松。
_NUMBER_TOKEN = re.compile(r"\d+(?:\.\d+)?%?")


def _input_number_corpus(request: ReviewSummaryRequest) -> str:
    """数字核对语料 = 规范化请求体 JSON 全文 + 服务端注入 prompt 的派生文本。

    请求体部分与缓存键同源，覆盖所有输入字段；「结论分布」注记里的条数（共 N 条 /
    通过 M 条）是服务端自己算的确定事实，模型照抄它属于**溯源成功**而非幻觉。
    只认请求体会把这类照抄判成编造（5.4 联调缺陷 C：s06 的 "共 11 条" 因请求体
    通篇没有 "11" 而错杀整段总述，能否侥幸存活取决于时间戳字符串里凑不凑得出那两个
    数字——与缺陷 A 同源：注入给模型看的派生内容未被承认为输入原文）。
    除该注记外没有别的派生数字来源（其余输入块都是请求体字段的原样序列化）。
    """
    parts = [json.dumps(request.model_dump(mode="json"), ensure_ascii=False)]
    if request.opinions:
        parts.append(_distribution_note(request))
    return "\n".join(parts)


def _unverifiable_numbers(text: str, corpus: str) -> list[str]:
    """挑出语料里找不到的数字 token；空列表即全部可溯源。"""
    return [token for token in _NUMBER_TOKEN.findall(text) if token not in corpus]


def _numbers_are_verifiable(text: str, corpus: str) -> bool:
    return not _unverifiable_numbers(text, corpus)


def _has_reject(request: ReviewSummaryRequest) -> bool:
    return any(opinion.action in _REJECT_ACTIONS for opinion in request.opinions)


def _has_positive_tone(text: str) -> bool:
    return any(phrase in text for phrase in _POSITIVE_TONE_PHRASES)


_OPINION_REF = re.compile(r"^opinions\[(\d+)\](?:\..*)?$")


def _opinion_ref_index(ref: Any) -> int | None:
    """把 `opinions[i]` / `opinions[i].xxx` 解析成下标；不是意见路径则 None。

    模型写子字段路径（`opinions[0].comment`）是旧契约的惯性：能安全归一就归一，
    不惩罚（服务端不得惩罚模型遵守契约，D14/D16.1-R1 的同一条纪律）。
    """
    if not isinstance(ref, str):
        return None
    match = _OPINION_REF.match(ref.strip())
    return int(match.group(1)) if match else None


def _prune_opinion_refs(refs: Any, valid_ref_set: set[str]) -> list[int]:
    """G1（change design.md D16.1-R3）：逐条剔除清单外的引用，**剩 0 才算违规**。

    旧口径"有一条悬空就丢整段总述"代价过高（5.4 联调证明），逐条剔除让归属变窄不变假。
    返回的是各条被采信引用指向的意见下标；剔完为空即该主题不被采信（走重试/丢弃）。
    """
    if not isinstance(refs, list):
        return []
    indexes: list[int] = []
    for ref in refs:
        index = _opinion_ref_index(ref)
        if index is None:
            continue
        if f"opinions[{index}]" not in valid_ref_set:
            continue  # 下标越界或未传入：`_collect_valid_refs` 只生成真实存在的下标
        if index not in indexes:
            indexes.append(index)
    return indexes


def _element_sentence(request: ReviewSummaryRequest) -> tuple[str | None, list[str]]:
    """①合同要素句（服务端装配）：AI 总述、面板 ①、兜底稿共用同一份（D16）。"""
    if request.contract_meta is None:
        return None, []
    meta = request.contract_meta
    clause: list[str] = []
    refs: list[str] = []
    if meta.contract_type:
        type_text = meta.contract_type
        clause.append(
            f"该合同为{type_text}" if type_text.endswith("合同") else f"该合同为{type_text}合同"
        )
        refs.append("contract_meta.contract_type")
    if meta.contract_amount:
        clause.append(f"合同总额 {meta.contract_amount}")
        refs.append("contract_meta.contract_amount")
    if meta.gross_margin:
        clause.append(f"综合毛利率 {meta.gross_margin}")
        refs.append("contract_meta.gross_margin")
    if not clause:
        return None, []
    return "，".join(clause), refs


# 兜底稿只允许两类素材：请求体字段原文、服务端自己算出的统计——两者都在数字语料与引用
# 清单内，因此兜底稿天然通过全部铁律校验，不会把"防幻觉"换成"造幻觉"。
_FALLBACK_NODE_LIMIT = 3


def _fallback_pieces(request: ReviewSummaryRequest) -> list[tuple[str, list[str]]]:
    """返回 (句子片段, 该片段引用的输入路径) 列表；无素材则为空列表。

    组成与 AI 总述同构：①合同要素句 + ②结论分布句 + "谁写了字"的点名——
    **不再提风险项标题**（change design.md D16.1-I2）：总述只承载评审意见，
    风险由 `key_concerns` 单点承载，同一面板位置不给两种组成。
    """
    pieces: list[tuple[str, list[str]]] = []
    element, element_refs = _element_sentence(request)
    if element:
        pieces.append((element, element_refs))
    sentence = _distribution_sentence(request)
    if sentence:
        pieces.append((sentence, ["opinions"]))
        # 点名"谁写了话"：只按 comment 非空这一确定性事实挑节点，不判断哪个动作算负面
        # （action 已废除枚举与词表，兜底稿同样不自造词表）。不写人数，避免引入语料外数字。
        written = [
            (index, opinion.node_name)
            for index, opinion in enumerate(request.opinions)
            if opinion.comment.strip()
        ]
        if written:
            shown = written[:_FALLBACK_NODE_LIMIT]
            tail = "等节点" if len(written) > len(shown) else "节点"
            pieces.append(
                (
                    "其中" + "、".join(name for _, name in shown) + tail + "提出了书面意见",
                    [f"opinions[{index}].node_name" for index, _ in shown],
                )
            )
    return pieces


def _fallback_summary_text(request: ReviewSummaryRequest) -> str | None:
    pieces = _fallback_pieces(request)
    if not pieces:
        return None
    return "；".join(text for text, _ in pieces) + "。"


def _fallback_summary_refs(request: ReviewSummaryRequest) -> list[str]:
    refs: list[str] = []
    for _, piece_refs in _fallback_pieces(request):
        refs.extend(ref for ref in piece_refs if ref not in refs)
    return refs


def _fallback_summary(request: ReviewSummaryRequest) -> ReviewSummarySection | None:
    text = _fallback_summary_text(request)
    if text is None:
        return None
    return ReviewSummarySection(text=text, source_refs=_fallback_summary_refs(request))


def _degrade_summary(
    request: ReviewSummaryRequest, degraded: set[str], reason: str
) -> ReviewSummarySection:
    """AI 总述稿不可用时的两层兜底（2026-10-08 用户拍板 A+B）。

    优先给服务端中性稿并标 `review_summary.fallback`（内容在、但不是 AI 写的，不落缓存，
    下次仍给模型机会）；连兜底素材都没有时（只有提级原因这类装配区已展示的内容）才退回
    旧的缺失语义 `text=null` + `review_summary.model`。
    """
    fallback = _fallback_summary(request)
    if fallback is not None:
        degraded.add(DEGRADED_SUMMARY_FALLBACK)
        logger.warning("总述 AI 稿未通过校验，改用服务端中性兜底稿", extra={"reason": reason})
        return fallback
    degraded.add(DEGRADED_SUMMARY_MODEL)
    logger.warning("总述 AI 稿未通过校验且无兜底素材，置空", extra={"reason": reason})
    return ReviewSummarySection(text=None, source_refs=[])


def _split_sentences(text: str) -> list[str]:
    """按中文句末标点切整句，标点留在句内；无标点时整段视为一句。"""
    sentences: list[str] = []
    buffer = ""
    for char in text.strip():
        buffer += char
        if char in _SENTENCE_ENDS:
            sentences.append(buffer)
            buffer = ""
    if buffer.strip():
        sentences.append(buffer)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def _trim_to_sentences(text: str, limit: int) -> str | None:
    """超长 AI 总述按**整句**从尾部丢弃，只保留 ≤limit 字的完整句子（s06 后用户口径）。

    取舍是刻意的：总述是本面板最重要的字段，宁可少一个主题，也不把模型写真了的内容
    整段清零换成服务端中性稿。失控的罗列必然堆在尾部，裁尾正好削掉最没信息量的部分。
    切不开（首句即超限，或裁完不足两句）才判这份稿子不可用，交回上层走兜底。
    """
    if len(text) <= limit:
        return text
    sentences = _split_sentences(text)
    kept: list[str] = []
    for sentence in sentences:
        candidate = "".join(kept) + sentence
        if len(candidate) > limit:
            break
        kept.append(sentence)
    if len(kept) < _TRIM_MIN_SENTENCES:
        return None
    return "".join(kept)


# ------------------------------------------------------- 主题结构化校验（D16）
# 模型从"写作文"变"填表"：只交主题句 + 指向有字意见的指针，节点名由服务端按指针反查
# `opinions[i].node_name` 派生渲染——归属因此结构性不可能错。文本层只保留**负向背书校验**
# （句内点了名，就必须是该主题自己 refs 覆盖的节点，D16.2-R6）；D15 的沉默节点名匹配
# （`_silent_node_names`/`_misattributed_names`/`_attribution_note`/`_strip_silent_names`）
# 整体删除：节点名互成子串是 LTC 数据常态，文本空间里误判与漏判数学上不可兼得。


@dataclass
class _Theme:
    """一条通过了结构闸的主题：模型原文 + 服务端实际采信的意见下标。"""

    text: str
    indexes: list[int]

    @property
    def refs(self) -> list[str]:
        return [f"opinions[{index}]" for index in self.indexes]


@dataclass
class _Draft:
    """一份成稿的复检结果（首稿与重试稿各跑一遍，取合法主题数多者，D16.1-I4）。

    `violations` 只装**结构违规**（形状/G1 剩 0/G2/G3 未背书）——它们是定向重试的扳机；
    `content_notes` 装内容违规（语料外数字、reject 正面定性）：不扳闸，只在重试已发生时
    搭车进话术。两者都计入 `discarded`，因为只有真丢弃过主题才值得打 `.incomplete`。
    """

    themes: list[_Theme] = field(default_factory=list)
    overall: str | None = None
    violations: list[str] = field(default_factory=list)
    content_notes: list[str] = field(default_factory=list)
    discarded: int = 0
    shape_failed: bool = False

    @property
    def needs_retry(self) -> bool:
        return self.shape_failed or bool(self.violations)


def _positive_phrases_in(text: str) -> list[str]:
    return [phrase for phrase in _POSITIVE_TONE_PHRASES if phrase in text]


def _unsupported_positive_phrases(text: str, request: ReviewSummaryRequest) -> list[str]:
    """挑出**没有任何一条评审意见原文说过**的正面定性短语；空列表即代答不成立（D16.4）。

    与 `_unverifiable_numbers` 同构的服务端确定性比对，但判据只取 `comment` 拼接体，不取全量
    输入语料：代答错在"替评审人表态"，所以唯一能给它背书的就是评审人亲手写下的字。风险项
    描述里恰好出现"无异议"并不构成一句总结的出处。
    触发事实：s05 真机 overall 写"其余节点无异议"，而那 7 个节点只是 `comment` 为空——
    空意见只证明没写字，证明不了无异议，而 G1–G4 一条都不拦（无节点名、无数字、引用合法），
    reject 不存在时铁律 5 的禁档也没开。扳机不看出炉方脸色、不依赖结论分布，也不新增输入侧
    词表：复用的就是铁律 5 那份禁用语，只是从"有 reject 才管"收紧为"没人说过就管"。
    原文真写了"无异议"时逐字转述那一条不算代答（不惩罚守契约的输出）。
    """
    said = "\n".join(opinion.comment for opinion in request.opinions)
    return [phrase for phrase in _positive_phrases_in(text) if phrase not in said]


def _check_theme(
    item: Any,
    position: int,
    request: ReviewSummaryRequest,
    valid_ref_set: set[str],
    corpus: str,
    names: list[str],
) -> tuple[_Theme | None, str, bool]:
    """逐主题过确定性闸；返回 (主题, "", False) 或 (None, 一句可核验的违规事实, 是否扳重试)。

    闸序：形状 → G1 逐条剔引用（剩 0 才违规）→ G2 引用指空意见 → G3 点名背书 →
    铁律 1 数字 → 铁律 5 正面定性（含无出处代答）。前三类是**结构违规**，扳定向重试（处置阶梯第 1 条）；
    数字与正面定性是**内容违规**，沿用既有"内容违规不消耗重试次数"口径——直接丢弃该主题，
    违规事实只在一个重试本就发生时搭车进话术（多一次改对的机会，零额外调用）。
    """
    label = f"主题 {position}"
    if not isinstance(item, dict):
        return None, f"{label} 不是对象：形状必须是 {{'text': …, 'opinion_refs': […]}}", True
    text = item.get("text")
    if not isinstance(text, str) or not text.strip():
        return None, f"{label} 的 `text` 为空或非字符串", True
    indexes = _prune_opinion_refs(item.get("opinion_refs"), valid_ref_set)
    if not indexes:
        return None, (
            f"{label} 的 `opinion_refs` 全部不在可用引用路径清单内：{_dumps(item.get('opinion_refs'))}"
        ), True
    empty = [f"opinions[{index}]" for index in indexes if not request.opinions[index].comment.strip()]
    if empty:  # G2：空意见名下没有一个字可以转述——张冠李戴在结构层的等价物
        return None, f"{label} 的 `opinion_refs` 指向了空意见：{'、'.join(empty)}", True
    endorsed = {(request.opinions[index].node_name or "").strip() for index in indexes}
    unbacked = [name for name in _find_node_name_mentions(text, names) if name not in endorsed]
    if unbacked:  # G3 未背书档：点了自己 refs 之外的节点
        endorsed_names = "、".join(sorted(name for name in endorsed if name)) or "无"
        return None, (
            f"{label} 点名了未背书的节点：{'、'.join(unbacked)}"
            f"（该主题的 refs 只覆盖 {endorsed_names}）"
        ), True
    fabricated = _unverifiable_numbers(text, corpus)
    if fabricated:
        return None, f"{label} 出现了输入原文中找不到的数字：{_dumps(fabricated)}", False
    parroted = _unsupported_positive_phrases(text, request)
    if parroted:  # 铁律 5 的无出处代答档：与 reject 是否存在无关（D16.4）
        return None, (
            f"{label} 出现了输入原文中没有任何评审人说过的正面定性：{_dumps(parroted)}"
            "（空意见只能说明未填写意见，不能说明无异议）"
        ), False
    if _has_reject(request) and _has_positive_tone(text):
        return None, (
            f"{label} 在存在「不通过」意见时含正面定性：{_dumps(_positive_phrases_in(text))}"
        ), False
    return _Theme(text=text.strip(), indexes=indexes), "", False


def _check_overall(
    overall: Any, request: ReviewSummaryRequest, corpus: str, names: list[str]
) -> tuple[str | None, str]:
    """overall 单独违规只丢这一句：不打标记、不触发重试（D16 / D16.2-R7）。

    overall 是总述里唯一保留模型判断力的位置（态势与焦点），它不承载归属，也没有 refs 可以
    背书，因此这里是"含任何节点名即违规"的平禁令，没有 G3 的背书两档。
    """
    if overall is None or not isinstance(overall, str) or not overall.strip():
        return None, ""
    text = overall.strip()
    mentioned = _find_node_name_mentions(text, names)
    if mentioned:
        return None, f"overall 含节点名：{'、'.join(mentioned)}"
    fabricated = _unverifiable_numbers(text, corpus)
    if fabricated:
        return None, f"overall 出现了输入原文中找不到的数字：{_dumps(fabricated)}"
    parroted = _unsupported_positive_phrases(text, request)
    if parroted:  # s05 真机第四枪的形态：overall 写"其余节点无异议"而那些节点只是没写字
        return None, (
            f"overall 出现了输入原文中没有任何评审人说过的正面定性：{_dumps(parroted)}"
            "（空意见只能说明未填写意见，不能说明无异议）"
        )
    if _has_reject(request) and _has_positive_tone(text):
        return None, f"overall 在存在「不通过」意见时含正面定性：{_dumps(_positive_phrases_in(text))}"
    return text, ""


def _verify_summary_payload(
    payload: dict, request: ReviewSummaryRequest, valid_ref_set: set[str], corpus: str
) -> _Draft:
    """形状失守（D16.1-I3）+ 逐主题复检，结构违规与内容违规分流；overall 的问题单独记账。"""
    draft = _Draft()
    raw_themes = payload.get("themes")
    if not isinstance(raw_themes, list):
        draft.shape_failed = True
        draft.violations.append("输出形状不符：`themes` 必须是数组（整块缺失不等于覆盖不全）")
        return draft
    names = _node_names(request)
    for position, item in enumerate(raw_themes, start=1):
        theme, reason, triggers_retry = _check_theme(item, position, request, valid_ref_set, corpus, names)
        if theme is None:
            draft.discarded += 1
            if triggers_retry:
                draft.violations.append(reason)
            else:
                draft.content_notes.append(reason)
                logger.warning("主题未通过内容校验，直接丢弃（不消耗重试）", extra={"reason": reason})
        else:
            draft.themes.append(theme)
    draft.overall, overall_reason = _check_overall(payload.get("overall"), request, corpus, names)
    if overall_reason:
        logger.warning("总述 overall 未通过校验，只丢这一句", extra={"reason": overall_reason})
    return draft


def _uncovered_indexes(request: ReviewSummaryRequest, draft: _Draft) -> list[int]:
    """写了字却没被任何主题引用的意见下标（G4）——**只观测，不扳闸**（D16.1-R1）。"""
    covered = {index for theme in draft.themes for index in theme.indexes}
    return [index for index in _written_opinion_indexes(request) if index not in covered]


def _merge_same_ref_themes(themes: list[_Theme]) -> list[_Theme]:
    """`opinion_refs` **完全相同**的主题合并成一条（D17，同源拆条的服务端确定性收口）。

    触发事实：s06 真机交回 6 条主题、refs 分布 `[5][5][6][6][7][7]`——三条意见各拆两条，
    渲染后缀重复三次成"（合同复核）…（合同复核）"，283 字距 300 红线只剩 17 字，而同一份输入
    上一轮是 3 条主题带跨意见归并。"最多 4 条"与"单意见单主题"都只写在 prompt 里，服务端从不数
    条数也从不查重复下标——prompt-only 约束第六次被真机绕过，而这是**唯一一条判据免费、零误伤面**
    的约束（比的是整数元组，不是语义）。

    只做拼接、不做改写，因此对四道闸**封闭**：数字抽验——连接符不产生数字，两句各自已过闸；
    代答与 reject 正面定性抽验——禁用语是连续子串，插入"，"令跨句边界拼不出新短语；G3 句内点名
    背书——两条主题 refs 相同 ⇒ 服务端反查的名字集合相同、句内提及的判据不变。
    位置取**首次出现**：模型给的顺序就是它的关键性顺序，服务端不重排、不判关键性。
    合并只发生在已通过复检的主题上——被丢弃的那条不会因为同源被"救"回来。

    **合并有预算上限**（`_MERGED_THEME_MAX_CHARS`）：拼完仍超上限的整组**原样留着不合并**。
    理由是这两条纪律的相撞点——失控罗列（真机见过一条意见拆 7 句）合并后会变成一条两百字、
    内部没有任何句末标点的长句，D13 的整句裁尾**切不动它**，只能整份退回兜底稿，那正好砸掉
    "降级不丢内容"这条红线。留成多条原句，裁尾才能一条一条从尾部削。
    """
    order: list[tuple[int, ...]] = []
    groups: dict[tuple[int, ...], list[_Theme]] = {}
    for theme in themes:
        key = tuple(theme.indexes)
        if key not in groups:
            order.append(key)
            groups[key] = []
        groups[key].append(theme)
    merged: list[_Theme] = []
    for key in order:
        group = groups[key]
        if len(group) == 1:
            merged.append(group[0])
            continue
        text = _with_period(_THEME_MERGE_JOIN.join(_open_theme(theme.text) for theme in group))
        if len(text) > _MERGED_THEME_MAX_CHARS:
            merged.extend(group)
            continue
        merged.append(_Theme(text=text, indexes=list(key)))
    return merged


def _log_capacity(raw_count: int, draft: _Draft) -> None:
    """容量观测（D17）：**合并后仍超目标条数**才记一行——同源拆条已被静默修好，不该刷屏。

    不丢主题、不打标记、不旁路缓存：超出 4 条的部分继续出稿（用户口径"内容不能被弃用"优先），
    本行只回答"合并之后还剩多少条、模型原始交了几条"，为下一轮是否收紧容量提供分布。
    """
    if len(draft.themes) <= _THEME_TARGET_COUNT:
        return
    logger.info(
        "review-summary 容量观测",
        extra={"raw_theme_count": raw_count, "theme_count": len(draft.themes)},
    )


def _longest_common_substring_len(left: str, right: str) -> int:
    previous = [0] * (len(right) + 1)
    best = 0
    for char_left in left:
        current = [0] * (len(right) + 1)
        for position, char_right in enumerate(right, start=1):
            if char_left == char_right:
                current[position] = previous[position - 1] + 1
                best = max(best, current[position])
        previous = current
    return best


def _overlap_ratio(theme: _Theme, request: ReviewSummaryRequest) -> float:
    """主题句与被引 comment 的原文重叠率（D16.1-I6：拿真实语料看误伤分布，再议是否升闸）。"""
    if not theme.text:
        return 0.0
    best = max(
        (_longest_common_substring_len(theme.text, request.opinions[index].comment) for index in theme.indexes),
        default=0,
    )
    return round(best / len(theme.text), 3)


# 中文数字 token（D16.5 观测项专用，与 `_NUMBER_TOKEN` 的阿拉伯口径互不替换）。
# 刻意要求"≥2 个连续数词字"或"百分之…"带小数的完整写法，为的是把"第三方 / 第六条 /
# 一致同意"这类非数值用法挡在清单外——观测项一旦噪声过大就没人再看，这条正则的松紧本身
# 也是待真机校准的对象，所以现在只观测、不扳闸。
_CN_NUMBER_TOKEN = re.compile(r"百分之[零〇一二三四五六七八九十百千万点]+|[零〇一二两三四五六七八九十百千万亿]{2,}")


def _log_cn_number_rewrites(request: ReviewSummaryRequest, draft: _Draft) -> None:
    """中文数字改写**只观测、不扳闸**（D16.5，与 G4 漏纳、`overlap_ratio` 同纪律）。

    触发事实：s05 真机主题 3 把原文的 `50万 / 2.24%` 写成"五十万 / 百分之二点二四"——语义没变，
    但铁律 1 的"照抄不换算"被绕开，而数字抽验对它**结构性失明**（`_NUMBER_TOKEN` 只匹配阿拉伯
    数字）。真正的敞口是"写错也抓不到"：模型若把 48 万写成"六十万"，现有闸一个字节都不会拦。
    判据与数字抽验同构：token 在输入原文（含服务端注入的派生文本）里找不到逐字出处即计入观测。
    评审人自己写中文数字时逐字转述不算改写（不误伤守契约的输出）。
    """
    corpus = _input_number_corpus(request)
    texts = [theme.text for theme in draft.themes]
    if draft.overall:
        texts.append(draft.overall)
    missing = sorted({
        token
        for text in texts
        for token in _CN_NUMBER_TOKEN.findall(text)
        if token not in corpus
    })
    if missing:
        logger.info("review-summary 中文数字观测", extra={"cn_number_tokens": missing})


# 集体指代族（D16.6 观测项，D18 放宽观测面；仍**只观测、不扳闸**）。代答档（D16.4）是固定禁用
# 语表的**逐字子串**比对，s05 真机第四枪把代答写成"其余节点无**实质**异议"——"无异议"被插字断开，
# 词表零命中、整句放行，这是代答档的第一个真实漏判，也是 prompt-only 约束第五次被真机绕过。
# D18 补的是观测器自己的第二个洞：s09 真机 overall 写"其余为执行层面提醒"，"其余"在这里是
# **代词**（指代未写字的那些人），后面不接任何集体名词，旧正则要求 4 字内出现名词 → 零命中。
# 漏判的观测器等于没有观测：它交回来的"真实分布"是残缺分母，据此做的升闸判断必然偏乐观。
# 噪声封顶：代词分支必须紧跟一个**立场/态势谓词**才算嫌疑，"其他付款条款按标准模板执行"这类
# 普通名词短语仍不进清单——否则正当概括会淹没真实代答，观测行没人再看。
_PARROT_HEAD = r"(?:其余|其他|其它|剩余)"
_PARROT_NOUNS = r"节点|部门|角色|人员|评审|同事|单位|各方"
# 代词用法必须配谓词提示词才计入（集体名词分支沿用既有口径，不额外加条件）
_PARROT_STANCE_HINTS = r"异议|分歧|认可|同意|通过|一致|为|是|无|没|未"
_PARROT_TAIL = r"[^，。；！？]{0,24}"
_PARROT_COLLECTIVE = re.compile(
    _PARROT_HEAD
    + r"(?:"
    + r"[^，。；！？、]{0,4}(?:" + _PARROT_NOUNS + r")"  # 集体名词分支（D16.6 原样）
    + r"|(?![^，。；！？、]{0,4}(?:" + _PARROT_NOUNS + r"))"  # 代词分支：先排除名词紧邻
    + r"[^，。；！？、]{0,2}(?:" + _PARROT_STANCE_HINTS + r")"
    + r")"
    + _PARROT_TAIL
)

# prompt 给出的唯一合法句式（"其余节点未填写意见"）陈述的是输入事实（`comment` 为空），
# 不是替人表态，必须放过——否则每个带空意见的单子都会刷出观测行，没人再看。
# D18 之后 ②分布句自己就带着这个事实（"共 M 条…其中 N 条填写了意见"，缺席条数由减法可推），
# 豁免口径不变：带"未填写/未提交…"这类事实词的片段仍然不记观测。
_SILENCE_FACT_WORDS = ("未填写", "未提交", "未发表", "未写", "未留", "空白")


def _parrot_suspects(text: str, corpus: str) -> list[str]:
    """返回 text 里"集体指代 + 语料无出处"的片段；`corpus` = 全部 `comment` 拼接体。

    判据边界与代答档同源（只认评审人亲手写的字）：评审人自己这么写过就不算代答。
    """
    return [
        fragment.group(0)
        for fragment in _PARROT_COLLECTIVE.finditer(text)
        if not any(word in fragment.group(0) for word in _SILENCE_FACT_WORDS)
        and fragment.group(0) not in corpus
    ]


def _log_parrot_suspects(request: ReviewSummaryRequest, draft: _Draft) -> None:
    """代答变体**只观测、不扳闸**（D16.6）：清单为空时整行都不打。

    观测面与代答档同宽——逐主题 + `overall`（真实漏判就出在 overall 上）；
    不丢主题、不丢句、不打 `.incomplete`/`.fallback`、不旁路缓存。
    """
    corpus = "\n".join(opinion.comment for opinion in request.opinions)
    texts = [theme.text for theme in draft.themes]
    if draft.overall:
        texts.append(draft.overall)
    suspects: list[str] = []
    for text in texts:
        for fragment in _parrot_suspects(text, corpus):
            if fragment not in suspects:
                suspects.append(fragment)
    if suspects:
        logger.info("review-summary 代答观测", extra={"parrot_phrases": suspects})


def _log_coverage(request: ReviewSummaryRequest, draft: _Draft) -> None:
    """一行观测日志：`covered/total` 确定性计数 + 未纳入清单 + 逐主题重叠率。

    为什么不扳闸：主题容量 ≤4×≤3=12 条，而有字意见可以远多于它（真实导出见过 141 条），
    把"全覆盖"当违规等于服务端惩罚模型遵守"容量有限、按关键性取舍"这条契约；只写
    "同意。"的意见（prompt 明说无需成主题）更不该成为分母（D16.2-R5）。
    """
    total = len(_written_opinion_indexes(request))
    if not total:
        return
    uncovered = _uncovered_indexes(request, draft)
    logger.info(
        "review-summary 主题覆盖观测",
        extra={
            "covered": total - len(uncovered),
            "total": total,
            "uncovered_refs": [f"opinions[{index}]" for index in uncovered],
            "overlap_ratios": [_overlap_ratio(theme, request) for theme in draft.themes],
        },
    )


_SHAPE_SAMPLE = (
    '{"overall": "≤40 字的整体判断，无话可说写 null",'
    ' "themes": [{"text": "主题句", "opinion_refs": ["opinions[0]"]}]}'
)


def _themes_retry_note(draft: _Draft, request: ReviewSummaryRequest) -> str:
    """定向重试话术：逐条可核验事实（哪个主题、哪条引用、哪个名没背书、漏了哪几条）。

    与 D15 的假事实风险本质不同——这里每一句都能从请求体与服务端复检结果逐字对上。
    漏纳只在**已经因其他违规触发重试**时搭车出现，绝不独立扳闸（D16.1-R1）。
    """
    lines = ["【上一稿的结构问题——只修下面列出的这几处，其余主题与用词全部保持不变】"]
    lines.extend(f"- {violation}" for violation in draft.violations)
    lines.extend(f"- {note}（这一处不重试也必须改掉）" for note in draft.content_notes)
    uncovered = _uncovered_indexes(request, draft)
    if uncovered:
        listed = "、".join(f"opinions[{index}]" for index in uncovered)
        lines.append(
            f"- 未纳入归并的有字意见：{listed}——若其中有实质诉求请补进主题；"
            "只写\u201c同意\u201d\u201c无异议\u201d一类的可以忽略。"
        )
    lines.append(f"输出形状（逐字照此形状）：{_SHAPE_SAMPLE}")
    return "\n".join(lines)


def _with_period(text: str) -> str:
    """句子以句号收尾：模型自己带了句末标点就不重复补（免得渲染出"。。"）。"""
    stripped = text.rstrip()
    if stripped.endswith(_TERMINALS):
        return stripped
    if stripped.endswith(("；", "，", "、", "：")):
        return stripped[:-1] + "。"
    return stripped + "。"


def _close_tail(text: str) -> str:
    """裁尾后可能停在"；"上（分号本就是整句边界）：收掉悬挂的连接号再补句号（已有句号则不重复）。"""
    stripped = text.rstrip()
    while stripped and stripped[-1] in "；，、：":
        stripped = stripped[:-1]
    if not stripped or stripped.endswith(_TERMINALS):
        return stripped
    return stripped + "。"


def _open_theme(text: str) -> str:
    """主题句并入"；"串时去掉自己的句末标点：句号留给整段的最后（D16 渲染格式）。"""
    stripped = text.strip()
    while stripped and stripped[-1] in _SENTENCE_ENDS:
        stripped = stripped[:-1].rstrip()
    return stripped


def _theme_segment(theme: _Theme, request: ReviewSummaryRequest, names: list[str]) -> str:
    """主题句 + 服务端从 refs 反查的节点名后缀；文本已逐字点过的名不再重复附（D16.1-R2）。"""
    derived: list[str] = []
    for index in theme.indexes:
        node = (request.opinions[index].node_name or "").strip()
        if node and node not in derived:
            derived.append(node)
    mentioned = set(_find_node_name_mentions(theme.text, names))
    suffix = [node for node in derived if node not in mentioned]
    base = _open_theme(theme.text)
    if not suffix:
        return base
    return f"{base}（{'、'.join(suffix)}）"


def _render_summary(request: ReviewSummaryRequest, draft: _Draft) -> tuple[str, list[tuple[str, _Theme]]]:
    """①要素句。②分布句。overall。主题1（名A、名B）；主题2（名C）……

    返回 (拼接后全文, [(主题片段, 主题)])，片段用于裁尾后回推哪几条主题还留着。
    主题句自带的句号被移到名字后缀之后再统一收（片段本身不带句末标点），主题之间用"；"
    连接，而"；"本身在 `_SENTENCE_ENDS` 里——D13 的整句裁尾因此能一条一条地从尾部削，
    不会把中间的主题砍成半句。
    """
    element, _ = _element_sentence(request)
    names = _node_names(request)
    parts: list[str] = []
    if element:
        parts.append(_with_period(element))
    sentence = _distribution_sentence(request)
    if sentence:
        parts.append(_with_period(sentence))
    if draft.overall:
        parts.append(_with_period(draft.overall))
    segments = [_theme_segment(theme, request, names) for theme in draft.themes]
    if segments:
        parts.append("；".join(segments) + "。")
    return "".join(parts), list(zip(segments, draft.themes))


def _server_source_refs(request: ReviewSummaryRequest, themes: list[_Theme]) -> list[str]:
    """总述引用改由服务端汇总（D16）：要素字段 + 分布（opinions 聚合路径）+ 各主题采信的 refs。"""
    _, refs = _element_sentence(request)
    if _distribution_sentence(request):
        refs = refs + ["opinions"]
    for theme in themes:
        refs.extend(ref for ref in theme.refs if ref not in refs)
    return refs


def _server_only_section(request: ReviewSummaryRequest) -> ReviewSummarySection:
    """①② 两段本就确定性：没有有字意见时不请模型写（它也确实没题材可写），照常可缓存。"""
    element, refs = _element_sentence(request)
    parts: list[str] = []
    if element:
        parts.append(_with_period(element))
    sentence = _distribution_sentence(request)
    if sentence:
        parts.append(_with_period(sentence))
        refs = refs + ["opinions"]
    return ReviewSummarySection(text="".join(parts) or None, source_refs=refs, themes=[])


def _generate_summary(
    request: ReviewSummaryRequest,
    model: Any,
    valid_refs: list[str],
    valid_ref_set: set[str],
    corpus: str,
    degraded: set[str],
) -> ReviewSummarySection:
    if not _written_opinion_indexes(request):
        logger.info("没有写过实质内容的评审意见，总述只装配 ①合同要素 + ②结论分布")
        return _server_only_section(request)

    kwargs = {
        "contract_meta_block": _contract_meta_block(request),
        "route_reason_block": _route_reason_block(request),
        "risk_register_block": _risk_register_block(request),
        "opinions_block": _opinions_block(request),
        "distribution_note": _distribution_note(request),
        "coverage_note": _coverage_note(request),
        "valid_refs_block": _refs_block(valid_refs),
        "retry_note": "",
    }
    draft = _verify_summary_payload(
        _invoke_json(model, "summary", **kwargs), request, valid_ref_set, corpus
    )
    if draft.needs_retry:
        logger.warning(
            "总述主题未通过结构校验，定向重试一次", extra={"violations": draft.violations}
        )
        try:
            retried = _verify_summary_payload(
                _invoke_json(
                    model, "summary", **{**kwargs, "retry_note": _themes_retry_note(draft, request)}
                ),
                request,
                valid_ref_set,
                corpus,
            )
        except Exception:  # 重试是补救，不能因为它失败把整个面板打成 500
            logger.warning("主题定向重试调用失败，沿用首稿的复检结果")
            retried = None
        if retried is not None and len(retried.themes) > len(draft.themes):
            draft = retried  # I4 取优：并列取首稿，防"补一个漏的同时改坏另一个"

    # 同源拆条收口（D17）：refs 完全相同的主题由服务端拼成一条，内容一字不增不减。
    # 放在复检与取优**之后**、观测日志之前——观测项应当描述真正发出去的那份稿子。
    raw_theme_count = len(draft.themes)
    draft.themes = _merge_same_ref_themes(draft.themes)
    _log_capacity(raw_theme_count, draft)
    _log_coverage(request, draft)
    _log_cn_number_rewrites(request, draft)
    _log_parrot_suspects(request, draft)
    if not draft.themes:
        # 一条合法主题都不剩（含形状失守）：整块缺失走兜底稿，不打 `.incomplete`
        reason = "；".join(draft.violations) or "主题整批未通过校验"
        return _degrade_summary(request, degraded, reason)
    if draft.discarded:
        degraded.add(DEGRADED_SUMMARY_INCOMPLETE)
        logger.warning(
            "部分主题未通过结构校验，已整条丢弃（不删名不改句）",
            extra={"discarded": draft.discarded, "kept": len(draft.themes)},
        )

    text, segments = _render_summary(request, draft)
    trimmed = _trim_to_sentences(text, _SUMMARY_HARD_LIMIT)
    if trimmed is None:
        # 连首两句都放不下：这不是"超长可裁"，而是这份稿子没法读，交回兜底稿
        return _degrade_summary(request, degraded, f"总述超过 {_SUMMARY_HARD_LIMIT} 字且切不出两句")
    trimmed = _close_tail(trimmed)
    if len(trimmed) < len(text):
        logger.warning(
            "总述超长，按整句裁掉尾部",
            extra={"raw_chars": len(text), "kept_chars": len(trimmed)},
        )
    kept = _kept_after_trim(trimmed, segments, draft.overall)
    if not kept and not _overall_survived(trimmed, draft.overall):
        # 裁到最后连一句 AI 成稿都没保住：这不再是"超长"，而是这份稿子没有可用内容
        return _degrade_summary(request, degraded, "整句裁尾后总述不再含任何 AI 成稿")
    return ReviewSummarySection(
        text=trimmed,
        source_refs=_server_source_refs(request, kept),
        themes=[SummaryTheme(text=theme.text, opinion_refs=theme.refs) for theme in kept],
    )


def _overall_survived(trimmed: str, overall: str | None) -> bool:
    """overall 那句（含句末标点）是否还完整躺在裁尾后的全文里。"""
    return bool(overall) and _with_period(overall) in trimmed


def _kept_after_trim(
    trimmed: str, segments: list[tuple[str, _Theme]], overall: str | None
) -> list[_Theme]:
    """裁尾后回推哪几条主题还在稿子里。

    主题片段一律排在 overall 之后，所以 overall 被裁掉时不可能有主题幸存——这条位置约束
    同时堵死"服务端装配的 ①② 句里恰好含相同子串"造成的误判（D16.1 处置阶梯第 7 条）。
    """
    if overall and not _overall_survived(trimmed, overall):
        return []
    return [theme for segment, theme in segments if segment in trimmed]


def _apply_opinion_summaries(
    request: ReviewSummaryRequest,
    details: list[OpinionDetail],
    model: Any,
    valid_refs: list[str],
    valid_ref_set: set[str],
    corpus: str,
    degraded: set[str],
) -> None:
    """批量生成意见摘要并就地写回骨架；逐条校验，单条不合规只丢该条。

    comment 为空的意见没有可摘要内容：不进批量输入、回填时直接跳过，
    SHALL NOT 计入丢弃数（否则误打 `opinion_details.model`、连带缓存旁路，
    真实面板多数评审人不写字 → 缓存永远失效。5.4 联调缺陷 B）。
    同理，模型对"同意。"这类近空意见按 prompt 契约显式返回 `summary: null`
    也不计丢弃——只有模型漏交某个 index 才算真的丢（s06 联调复现）。
    """
    if not any(opinion.comment.strip() for opinion in request.opinions):
        return
    payload = _invoke_json(
        model,
        "opinion",
        opinions_block=_opinions_block(request, only_with_comment=True),
        valid_refs_block=_refs_block(valid_refs),
    )
    items = payload.get("summaries")
    if not isinstance(items, list):
        degraded.add(DEGRADED_OPINION_MODEL)
        logger.warning("意见摘要批量输出结构异常，全部丢弃")
        return

    by_index: dict[int, dict] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        if isinstance(index, bool) or not isinstance(index, int):
            continue
        by_index.setdefault(index, item)

    expected = sum(1 for opinion in request.opinions if opinion.comment.strip())
    discarded = 0
    for position, detail in enumerate(details):
        if not request.opinions[position].comment.strip():
            continue  # 空意见：summary 保持 null，不计丢弃
        item = by_index.get(position)
        if item is not None and item.get("summary") is None:
            # prompt 明说"某条 comment 无实质内容时该条 summary 输出 null"：
            # 显式 null 是模型按契约交出的正确结果（真实面板里"同意。"这类），
            # 不是违规，不计丢弃。真正的丢弃只有一种——模型漏交了这个 index。
            continue
        summary = item.get("summary") if item else None
        refs = item.get("source_refs") if item else None
        if (
            isinstance(summary, str)
            and summary.strip()
            and _refs_are_valid(refs, valid_ref_set)
            and _numbers_are_verifiable(summary, corpus)
        ):
            detail.summary = summary.strip()
        else:
            discarded += 1
    if discarded:
        degraded.add(DEGRADED_OPINION_MODEL)
        logger.warning(
            "部分意见摘要被丢弃",
            extra={"discarded": discarded, "expected": expected, "opinions": len(details)},
        )
