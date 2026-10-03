"""评审智能总结业务：装配区 + 两处 AI 生成 + 服务端铁律校验 + 空态降级 + 缓存。

分层（设计文档 §2.2 / §2.3 / §5.1，change design.md D4）：

- **装配区**（`key_concerns`、`opinion_details` 骨架）纯确定性、零模型参与，输入原文照搬；
- **AI 生成只有两处**：`review_summary.text`（总述）与 `opinion_details[].summary`（意见摘要，
  一次调用批量生成，按 index 一一对应）；
- **五条铁律在服务端强制**，不只靠 prompt：source_refs 无引用/悬空即丢弃，存在 reject 时
  总述含正面定性即判失败；丢弃只影响该 AI 字段，不阻塞装配区；
- **错误码复用** 20001（调用失败）/ 20002（超时）/ 20003（格式异常），不新增。
"""
import json
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

# 输出顺序固定，便于前端与用例断言（去重后按此序输出）
_DEGRADED_ORDER = (
    DEGRADED_KEY_CONCERNS,
    DEGRADED_OPINION_DETAILS,
    DEGRADED_SUMMARY_OPINIONS,
    DEGRADED_SUMMARY_MODEL,
    DEGRADED_OPINION_MODEL,
)

# 存在 reject 意见时，总述出现下列正面定性即判违规（铁律 5）
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
_ACTION_LABELS = {"pass": "通过", "conditional": "有条件通过", "reject": "不通过"}

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
    # AI 质量降级（source_refs 悬空、reject 正面定性）不落缓存：模型输出有随机性，
    # 钉死坏结果会让同一输入永远拿不到总述。空态降级由输入决定，可安全缓存。
    if not any(marker.endswith(".model") for marker in data.degraded_sections):
        set_cached(cache_key, data.model_dump(mode="json"))
    return data


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
    model = _bound_model()
    review_summary = _generate_summary(request, model, valid_refs, valid_ref_set, degraded)
    _apply_opinion_summaries(request, opinion_details, model, valid_refs, valid_ref_set, degraded)

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


def _opinions_block(request: ReviewSummaryRequest) -> str:
    if not request.opinions:
        return _NO_OPINIONS
    return _dumps(
        [
            {
                "index": index,
                **_present_fields(opinion, _OPINION_FIELDS),
                "action_label": _ACTION_LABELS.get(opinion.action, opinion.action),
            }
            for index, opinion in enumerate(request.opinions)
        ]
    )


def _distribution_note(request: ReviewSummaryRequest) -> str:
    if not request.opinions:
        return "本次评审意见尚未提交：总述只陈述已传入的合同要素等事实，不得概括任何评审意见。"
    counts = {action: 0 for action in _ACTION_LABELS}
    for opinion in request.opinions:
        counts[opinion.action] = counts.get(opinion.action, 0) + 1
    total = len(request.opinions)
    if counts["reject"]:
        return (
            f"共 {total} 条意见：通过 {counts['pass']} 条、有条件通过 {counts['conditional']} 条、"
            f"不通过 {counts['reject']} 条。存在不通过（reject）意见，总述必须退化为中性陈述："
            "只列事实 + \"评审意见存在分歧\"类客观描述，禁止任何正面定性。"
        )
    return (
        f"共 {total} 条意见：通过 {counts['pass']} 条、有条件通过 {counts['conditional']} 条、"
        "不通过 0 条。"
    )


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


def _has_summary_input(request: ReviewSummaryRequest) -> bool:
    """有无可写进总述的可溯源事实；全空则不发起模型调用（避免无源生成）。"""
    if request.opinions or request.risk_register or request.route_reason is not None:
        return True
    return bool(request.contract_meta is not None and _present_fields(request.contract_meta, _CONTRACT_META_FIELDS))


def _refs_are_valid(refs: Any, valid_ref_set: set[str]) -> bool:
    """无引用、非字符串、引用悬空（含数组越界）一律判不合规。"""
    if not isinstance(refs, list) or not refs:
        return False
    return all(isinstance(ref, str) and ref.strip() in valid_ref_set for ref in refs)


def _has_reject(request: ReviewSummaryRequest) -> bool:
    return any(opinion.action == "reject" for opinion in request.opinions)


def _has_positive_tone(text: str) -> bool:
    return any(phrase in text for phrase in _POSITIVE_TONE_PHRASES)


def _discard_summary(degraded: set[str], reason: str) -> ReviewSummarySection:
    degraded.add(DEGRADED_SUMMARY_MODEL)
    logger.warning("总述被丢弃", extra={"reason": reason})
    return ReviewSummarySection(text=None, source_refs=[])


def _generate_summary(
    request: ReviewSummaryRequest,
    model: Any,
    valid_refs: list[str],
    valid_ref_set: set[str],
    degraded: set[str],
) -> ReviewSummarySection:
    if not _has_summary_input(request):
        logger.info("无可溯源输入，跳过总述生成")
        return ReviewSummarySection(text=None, source_refs=[])

    payload = _invoke_json(
        model,
        "summary",
        contract_meta_block=_contract_meta_block(request),
        route_reason_block=_route_reason_block(request),
        risk_register_block=_risk_register_block(request),
        opinions_block=_opinions_block(request),
        distribution_note=_distribution_note(request),
        valid_refs_block=_refs_block(valid_refs),
    )
    text = payload.get("text")
    refs = payload.get("source_refs")
    if not isinstance(text, str) or not text.strip():
        return _discard_summary(degraded, "text 为空或非字符串")
    if not _refs_are_valid(refs, valid_ref_set):
        return _discard_summary(degraded, f"source_refs 无引用或悬空：{_dumps(refs)}")
    if _has_reject(request) and _has_positive_tone(text):
        return _discard_summary(degraded, "存在不通过意见但总述含正面定性")
    return ReviewSummarySection(text=text.strip(), source_refs=[ref.strip() for ref in refs])


def _apply_opinion_summaries(
    request: ReviewSummaryRequest,
    details: list[OpinionDetail],
    model: Any,
    valid_refs: list[str],
    valid_ref_set: set[str],
    degraded: set[str],
) -> None:
    """批量生成意见摘要并就地写回骨架；逐条校验，单条不合规只丢该条。"""
    if not request.opinions:
        return
    payload = _invoke_json(
        model,
        "opinion",
        opinions_block=_opinions_block(request),
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

    discarded = 0
    for position, detail in enumerate(details):
        item = by_index.get(position)
        summary = item.get("summary") if item else None
        refs = item.get("source_refs") if item else None
        if isinstance(summary, str) and summary.strip() and _refs_are_valid(refs, valid_ref_set):
            detail.summary = summary.strip()
        else:
            discarded += 1
    if discarded:
        degraded.add(DEGRADED_OPINION_MODEL)
        logger.warning("部分意见摘要被丢弃", extra={"discarded": discarded, "total": len(details)})
