from __future__ import annotations

"""Task 9 Step 1-3：无状态 Prepare 服务编排闭合矩阵（行为验收契约）。

本文件只表达正式验收行为，不实现编排器；服务能力缺失时在测试体内惰性导入处失败，
失败根因被明确归因为“服务能力未实现”，而非收集期导入、fixture 或环境错误。

闭合矩阵（正式要求 -> 服务阶段 -> 输入 / 输出与证据 -> 失败边界 -> 测试）：

| 正式要求 (design 第 10 节 + spec 8.1 / 技术失败 + DEC-LTC-20260911-004) | 服务阶段 | 输入 / 输出与证据 | 失败边界 | 测试 |
|---|---|---|---|---|
| 唯一服务入口 prepare_contract(request) -> ReviewContext | normalize_request / 请求校验 | 输入 PrepareRequest，输出 ReviewContext | 非该形态即不合规 | test_service_entry_is_single_public_callable |
| 单次请求内的明确重复（重复 attachment_id）在模型调用前被拒绝，模型调用次数为 0 | normalize_request / 前置重复门禁（既有 build_document_inputs） | 输入含重复 attachment_id 的 PrepareRequest，输出参数错误（服务层复用既有 PrepareDuplicateError），全程无任何模型调用 | 先发起任意模型调用或把它伪装为模型技术失败即缺口 | test_definite_duplicate_request_is_rejected_before_any_model_call |
| 固定流水线语义依赖（输入准备→扫描→提取→引用验证/稳定排序→摘要生成） | 全流水线 | 可观察公共协作方调用满足正式可观察依赖（含标准附件 scan 先于其局部签章提取） | 依赖倒置即缺口 | test_pipeline_preserves_fixed_stage_order |
| 无状态：连续两份均为非空候选的不同输入不共享文档映射/候选/证据/issue | build_source_snapshot..compute_hashes | 各自 evidence/候选/issue/文档映射独立 | 交叉复用即失败 | test_consecutive_requests_do_not_share_state |
| 标准附件无扫描候选：保留清单、不发起该附件 party/signature 全文 LLM 提取、相关域 COMPLETE 空事实 | classify_and_scan_standard_attachments + 逐域提取 | 附件仍在 source_snapshot 与 attachment_manifest，覆盖 COMPLETE | 对整份附件发起 party/signature 全文 LLM 即失败 | test_no_hit_standard_attachment_is_not_sent_to_full_text_llm |
| 标准附件无扫描候选：正文不得进入任何模型调用（确定性安全扫描不产生调用），同时保留来源/清单/连接/覆盖 | classify_and_scan_standard_attachments + 逐域提取 + 清单装配 | 无命中附件正文不出现在任何已记录模型调用入参中；附件仍在 source_snapshot 与 attachment_manifest，三域 COMPLETE | 无命中正文进入任一模型调用（含逐文档清单装配）即失败 | test_no_hit_standard_attachment_body_enters_no_model_call |
| 最终引用验证接收本请求完整规范化 markdown_by_document（主合同与全部附件） | 引用完整性 | validate_review_context 的 markdown_by_document 等于 build_document_inputs 的完整映射 | 缺键、只给主合同或未传即失败 | test_final_validation_receives_complete_markdown_by_document |
| 标准附件命中：仅将合并后绝对 locator 传给 party/signature，证据归属附件、同坐标去重、同值异坐标保留 | classify_and_scan + 局部提取 | extraction_input 携带合并范围，覆盖与证据归属附件 document_key | 整份全文提取或误合并同值异坐标即失败 | test_hit_standard_attachment_local_extraction_uses_merged_locators |
| 目录外/边界或类型不可靠附件走普通完整提取 | classify_and_scan + 逐域提取 | 无局部范围，全文提取 | 错误跳过即缺口 | test_out_of_directory_attachment_uses_full_text_extraction、test_boundary_unreliable_standard_named_attachment_falls_back_to_full_text |
| 模型超时/调用失败/输出截断/格式重试耗尽整体失败 | 逐域候选召回 | 不返回 ReviewContext | 不得伪装 COMPLETE/PARTIAL/UNAVAILABLE | test_model_technical_failure_fails_whole_request |
| 安全扫描/范围定位与合并/局部提取/结果装配/证据装配与读取/引用验证/排序合并/哈希生成失败整体失败 | classify_and_scan 起至 compute_hashes | 不返回残缺上下文 | 向上传播技术失败 | test_pipeline_seam_failure_fails_whole_request |
| 仅具体文档、类别、可验证来源的局部可读性缺口可降级覆盖 | assemble_evidence_and_coverage | 该文档覆盖降级为 PARTIAL 且带问题 | 无缺口不得伪造降级 | test_verifiable_source_gap_downgrades_coverage |
| 无缺口不得伪造降级 | assemble_evidence_and_coverage | 全部覆盖 COMPLETE | - | test_no_source_gap_does_not_downgrade_coverage |
| 技术失败不得降级覆盖 | 全流水线 | 抛错且不返回上下文 | - | test_technical_failure_never_returns_partial_context |
| 偏序：输入准备先于扫描/提取、主体定义先于附件主体装配、提取先于引用验证/排序/摘要（含无附件请求） | 全流水线 | 可观察公共协作方的事件次序 | 偏序倒置即缺口 | test_pipeline_partial_order_holds_without_attachments |
| 双路径与清单保留：主合同走全文 party/signature、命中附件走局部 party/signature，清单逐文档装配且保留来源快照 | build_inputs + classify_and_scan + 逐域提取 | 主合同无局部范围；附件携带合并范围；清单调用给出当前 document_key 与快照内可选目标；attachments 与 document_set_hash 不变 | 路径错配、清单丢失或凭附件数量推算清单即失败 | test_hit_attachment_keeps_manifest_and_uses_local_paths |
| 证据按 (document_key, 绝对坐标) 去重：同坐标共享同一证据身份，同值异坐标各自保留 | assemble_evidence_and_coverage | evidence_index 坐标唯一 | 同坐标重复或异坐标被合并即失败 | test_evidence_registry_dedups_by_locator_coordinate |
| 连续与并发请求的非空问题及非公开调用元数据互不泄漏 | 全流水线 | 域 issues / preparation_issues / context_digest / 模型调用的完整 prompt 载荷 / prepare_model 私有日志事件携带的非空 token 用量 | 交叉复用即失败 | test_non_empty_issues_and_call_metadata_are_isolated_between_requests、test_concurrent_requests_do_not_share_non_empty_state、test_model_token_usage_is_isolated_between_consecutive_requests、test_model_token_usage_is_isolated_between_concurrent_requests |

入口契约（实施计划 Task 9 Step 1-4 + DEC-LTC-20260911-004 声明；Step 1-3 仅消费，不在本批次实现）：
1. 模块 app/capabilities/contract_review/two_stage/prepare_service.py，当前尚不存在。
2. 唯一公开入口 prepare_contract(request: PrepareRequest) -> ReviewContext。
3. 内部管线顺序是逻辑依赖而非运行时阶段（DEC-LTC-20260911-005）：测试只锁定唯一入口与可观察
   公共协作方的偏序及结果，不要求私有 helper、阶段 trace 或运行时阶段标签，也不要求新的公共 API。
4. long_document.py 只产生安全扫描范围计划；无候选结束、命中局部 party/signature 提取、最终证据
   坐标去重与全链技术失败闭合均由 prepare_service.py 唯一编排（DEC-LTC-20260911-004）。
5. 偏序只锁定正式可观察依赖：design 第 10 节把“引用完整性 + 稳定排序 → document_set_hash /
   context_digest 生成”归为一组语义（引用验证与稳定排序都早于摘要生成），但实施计划 Task 9 Step 4
   参考实现的调用次序为 sort_review_context -> validate_review_context，两者相对次序未在权威中固定，
   因此测试不得断言 validate_references 与 sort_payload 的先后，只断言二者都早于 compute_hashes。
"""

import importlib.util
import inspect
import json
import logging
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.capabilities.contract_review.two_stage import (
    documents as documents_module,
    extract_commercial,
    extract_header_parties,
    extract_signature,
    hashing,
    long_document,
    prepare_model,
    prepare_prompts,
    validation,
)
from app.capabilities.contract_review.two_stage.documents import (
    PrepareDuplicateError,
    build_document_inputs,
)
from app.capabilities.contract_review.two_stage.evidence import (
    EvidenceRegistry,
    parse_markdown_locator,
)
from app.capabilities.contract_review.two_stage.long_document import (
    build_standard_attachment_scan_plan,
    merge_overlapping_ranges,
    scan_complete_markdown_for_review_facts,
    validate_scan_plan,
)
from app.capabilities.contract_review.two_stage.prepare_model import (
    AmountCopyCandidate,
    AttachmentCandidate,
    HeaderPartiesCandidate,
    PrepareModelEnvelope,
    SignatureCandidate,
)
from app.capabilities.contract_review.two_stage.schemas import (
    MainDocumentSnapshot,
    PrepareMainDocumentInput,
    PrepareRequest,
    PrepareUploadedAttachmentInput,
    ReviewContext,
    SourceSnapshot,
)
from app.core.errors import (
    ModelFormatError,
    ModelInvocationError,
    ModelOutputTooLongError,
    ModelTimeoutError,
)


_SERVICE_MODULE = "app.capabilities.contract_review.two_stage.prepare_service"
_MISSING = object()

# 既定语义依赖的可观察协作方（DEC-LTC-20260911-005：逻辑依赖而非十二个运行时阶段标签）。
_ORDERED_SEAMS = (
    ("build_inputs", documents_module, "build_document_inputs"),
    ("scan", long_document, "build_standard_attachment_scan_plan"),
    ("parties_main", extract_header_parties, "extract_header_and_main_parties"),
    ("parties_attachment", extract_header_parties, "extract_attachment_party_mentions"),
    ("signature", extract_signature, "extract_signature_facts"),
    ("commercial", extract_commercial, "extract_amount_copy_manifest"),
    ("validate_references", validation, "validate_review_context"),
    ("sort_payload", hashing, "sort_review_context"),
    ("compute_hashes", hashing, "compute_context_digest"),
)

_CANDIDATE_BY_PROMPT = {
    "prepare_header_parties_main": HeaderPartiesCandidate,
    "prepare_signature_document": SignatureCandidate,
    "prepare_amount_copy_main": AmountCopyCandidate,
    "prepare_attachment_document": AttachmentCandidate,
}

_MAIN_MARKDOWN = (
    "# 采购合同\n\n"
    "甲方：主合同甲方有限公司\n"
    "乙方：主合同乙方有限公司\n\n"
    "## 一、主体与义务\n"
    "甲方应提供本项目的全部接口说明。\n"
    "乙方应按合同标准执行交付。\n\n"
    "## 二、签署区\n"
    "法定代表人：张三\n"
    "签署日期：2026年1月1日\n\n"
    "## 三、账户与联系\n"
    "开户银行：主合同银行\n"
    "联系电话：010-11112222\n"
    "## 四、附件清单\n"
    "附件一：技术规范书\n"
    "本合同附件共 1 份。\n"
)

# 主合同附件清单声明原文：显式总数与逐份声明都必须来自主合同可定位原文，
# 不得由附件数量、文件标题或其他字段推算（spec 7.5 / design 第 10 节附件清单条款）。
_MAIN_DECLARED_ATTACHMENT_LINE = "附件一：技术规范书"
_MAIN_DECLARED_TOTAL_LINE = "本合同附件共 1 份。"

# 独立原文坐标行：与“甲方：附件甲方有限公司”同值，但位于另一条单独的主体定义正文行，
# 用于验证同值异坐标候选各自保留，且不得借用同一行内的子串坐标充当独立坐标。
_STANDARD_HIT_SECOND_PARTY_LINE = "丙方：附件甲方有限公司应配合验收。"
_STANDARD_HIT_B_SECOND_PARTY_LINE = "丙方：二号技术有限公司应配合验收。"

# 可靠识别的标准附件，正文含可扫描合同事实候选（命中）。
_STANDARD_HIT_MARKDOWN = (
    "# 技术规范书\n\n"
    "文档名称：技术规范书\n"
    "文档编号：TS-2026-100\n"
    "版本：V1.0\n\n"
    "## 一、主体定义\n"
    "甲方：附件甲方有限公司\n"
    "乙方：附件乙方有限公司\n\n"
    "## 二、义务\n"
    "甲方应提供本项目的全部接口说明。\n"
    "乙方应按本标准执行交付。\n"
    + _STANDARD_HIT_SECOND_PARTY_LINE
    + "\n\n"
    "## 三、签署区\n"
    "法定代表人：李四\n"
    "签署日期：2026年2月2日\n\n"
    "## 四、账户与联系\n"
    "开户银行：附件银行\n"
    "联系电话：010-99998888\n"
)

# 第二份可靠识别标准附件：与上一份结构一致、主体与字段取值不同，
# 用于验证连续两份非空输入的请求状态互不泄漏。
_STANDARD_HIT_MARKDOWN_B = (
    "# 技术规范书\n\n"
    "文档名称：技术规范书\n"
    "文档编号：TS-2026-300\n"
    "版本：V3.0\n\n"
    "## 一、主体定义\n"
    "甲方：二号技术有限公司\n"
    "乙方：三号技术有限公司\n\n"
    "## 二、义务\n"
    "甲方应提供第二批次接口说明。\n"
    "乙方应按本标准执行交付。\n"
    + _STANDARD_HIT_B_SECOND_PARTY_LINE
    + "\n\n"
    "## 三、签署区\n"
    "法定代表人：王五\n"
    "签署日期：2026年3月3日\n\n"
    "## 四、账户与联系\n"
    "开户银行：二号银行\n"
    "联系电话：010-77776666\n"
)

# 可靠识别的标准附件，正文只含技术/功能/质量指标（无相关事实候选）。
_STANDARD_NOHIT_MARKDOWN = (
    "# 技术规范书\n\n"
    "文档名称：技术规范书\n"
    "文档编号：TS-2026-200\n"
    "版本：V2.0\n\n"
    "## 1 技术指标\n"
    "系统支持并发 1000 路，响应时间不超过 200ms。\n\n"
    "## 2 功能需求\n"
    "支持批量导入与导出，支持断点续传。\n\n"
    "## 3 质量指标\n"
    "缺陷率低于 0.1%，可用性不低于 99.9%。\n"
)

# 目录外附件（商务协议），边界可靠但类型不在目录内，须走普通完整提取。
_OUT_OF_DIRECTORY_MARKDOWN = (
    "# 商务协议\n\n"
    "甲方：商务甲方有限公司\n"
    "乙方：商务乙方有限公司\n\n"
    "## 一、结算条款\n"
    "甲方应按约定支付款项。\n"
)

# 名称标准但内部身份冲突（自述为工作说明书）的标准名称附件正文：
# 类型不可靠，必须回退普通完整提取，不得进入标准扫描路径。
_STANDARD_CONFLICT_MARKDOWN = (
    "# 附件\n\n"
    "文档名称：技术规范书\n"
    "文档编号：TS-2026-400\n"
    "版本：V1.0\n\n"
    "## 一、说明\n"
    "本文档为工作说明书，规定工作范围。\n\n"
    "## 二、主体定义\n"
    "甲方：冲突甲方有限公司\n"
)

_TECHNICAL_FAILURES = (
    ModelInvocationError,
    ModelTimeoutError,
    ModelOutputTooLongError,
    ModelFormatError,
)


def _service():
    """惰性导入服务模块；只有该模块本身确实缺失时才归因“服务能力未实现”。

    find_spec 命中后再交给 importlib 导入：若模块已存在但导入失败（依赖缺失、
    语法或导入错误），真实原因原样抛出，避免把非服务缺失误报为服务缺失。
    """
    if importlib.util.find_spec(_SERVICE_MODULE) is None:
        pytest.fail(f"服务能力未实现: 模块 {_SERVICE_MODULE} 不存在", pytrace=False)
    return importlib.import_module(_SERVICE_MODULE)


def _attr(module, name):
    value = getattr(module, name, _MISSING)
    if value is _MISSING:
        pytest.fail(f"服务能力未实现: {module.__name__}.{name} 尚未实现", pytrace=False)
    return value


def _request(
    main_markdown: str = _MAIN_MARKDOWN,
    attachments: tuple[tuple[str, str, str], ...] = (),
    *,
    contract_id: str = "C-2026-0001",
    revision_id: str = "V1",
) -> PrepareRequest:
    return PrepareRequest(
        contract_id=contract_id,
        revision_id=revision_id,
        main_document=PrepareMainDocumentInput(
            document_id="DOC-MAIN",
            filename="main.md",
            markdown=main_markdown,
        ),
        uploaded_attachments=[
            PrepareUploadedAttachmentInput(
                attachment_id=attachment_id,
                filename=filename,
                markdown=markdown,
            )
            for attachment_id, filename, markdown in attachments
        ],
    )


def _attachment_key(prepared) -> str:
    keys = [key for key in prepared.markdown_by_document if key != "main"]
    assert len(keys) == 1, f"期望单一上传附件, 实际 {keys}"
    return keys[0]


def _coverage_by_key(domain) -> dict:
    return {coverage.document_key: coverage for coverage in domain.coverage}


def _sorted_ranges_from_input(extraction_input: str) -> list[list[int]]:
    payload = json.loads(extraction_input)
    ranges = payload.get("extraction_ranges", [])
    return sorted([int(item["start"]), int(item["end"])] for item in ranges)


def _envelope(prompt_name: str, candidates, gaps):
    model = _CANDIDATE_BY_PROMPT.get(prompt_name)
    payload = {"candidates": list(candidates), "source_gaps": list(gaps)}
    if model is None:
        return PrepareModelEnvelope.model_validate(payload)
    return PrepareModelEnvelope[list[model]].model_validate(payload)


def _empty_envelope(prompt_name: str, gaps):
    return _envelope(prompt_name, [], gaps)


def _make_recorder(calls, gaps_by_prompt=None, fail=None, candidates_for=None):
    gaps_by_prompt = gaps_by_prompt or {}

    def recorder(prompt_name, **kwargs):
        calls.append((prompt_name, dict(kwargs)))
        if fail is not None and prompt_name == fail[0]:
            raise fail[1]
        gaps = gaps_by_prompt.get(prompt_name, [])
        if candidates_for is not None:
            candidates = candidates_for(prompt_name, kwargs)
            if candidates is not None:
                return _envelope(prompt_name, candidates, gaps)
        return _empty_envelope(prompt_name, gaps)

    return recorder


def _make_scoped_recorder(calls, gaps_by_prompt_markdown=None, candidates_for=None):
    """按 (prompt_name, markdown) 精确注入 source_gap，其余调用返回空信封。

    连续/并发隔离用例需要同一 prompt 在不同文档上得到不同的非空缺口，
    避免把某份文档的缺口误注到另一份文档的调用上。
    """
    gaps_by_prompt_markdown = gaps_by_prompt_markdown or {}

    def recorder(prompt_name, **kwargs):
        calls.append((prompt_name, dict(kwargs)))
        gaps = gaps_by_prompt_markdown.get((prompt_name, kwargs.get("markdown")), [])
        candidates = None
        if candidates_for is not None:
            candidates = candidates_for(prompt_name, kwargs)
        if candidates is None:
            return _empty_envelope(prompt_name, gaps)
        return _envelope(prompt_name, candidates, gaps)

    return recorder


def _patch_models(monkeypatch, recorder) -> None:
    """沿用 Task 5/6/7 的模块级 patch 约定：逐提取器模块替换 invoke_typed_prepare_model。"""
    for module in (extract_header_parties, extract_signature, extract_commercial):
        monkeypatch.setattr(module, "invoke_typed_prepare_model", recorder)


def _patch_seam(monkeypatch, service, source_module, name, replacement) -> None:
    """同时 patch 服务命名空间与来源模块，兼容两种导入风格，不需新的公共 API。"""
    if hasattr(service, name):
        monkeypatch.setattr(service, name, replacement)
    monkeypatch.setattr(source_module, name, replacement)


def _record(events, label, original):
    """包装公共协作方以记录可观察调用事件（不引入阶段 trace 或私有 helper）。"""

    def wrapper(*args, **kwargs):
        events.append(label)
        return original(*args, **kwargs)

    return wrapper


def _patch_ordered_seams(monkeypatch, service, events) -> None:
    for label, source_module, name in _ORDERED_SEAMS:
        original = getattr(source_module, name)
        _patch_seam(
            monkeypatch, service, source_module, name, _record(events, label, original)
        )


def _extraction_input_payload(kwargs) -> dict:
    raw = kwargs.get("extraction_input")
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _attachment_candidates(
    markdown: str,
    attachment_key: str,
    party_name: str,
    party_quote: str,
    second_party_quote: str,
    signer_quote: str,
):
    """构造仅对指定 markdown 附件局部调用生效的非空可定位 party/signature 候选注入器。

    - party：c1/c2 同坐标去重；c3 与 c1 同值但落在独立原文坐标，必须各自保留。
    - signature：一个 SIGNATURE_BLOCK 候选，引用附件正文签署区标题，
      用于验证附件签章事实非空且证据坐标真实归属该附件。
    """

    def candidates_for(prompt_name, kwargs):
        if kwargs.get("markdown") != markdown:
            return None
        if "document_key" in _extraction_input_payload(kwargs):
            return None  # 附件清单商业装配调用，不注入 party/signature 候选
        if prompt_name == "prepare_attachment_document":
            base = {
                "candidate_kind": "PARTY_MENTION",
                "mention_kind": "PARTY_DEFINITION",
                "party_name": party_name,
                "party_role": "甲方",
            }
            return [
                {
                    **base,
                    "candidate_ref": f"{attachment_key}-party-c1",
                    "document_key": attachment_key,
                    "quote": party_quote,
                    "mention_text": party_quote,
                },
                {
                    **base,
                    "candidate_ref": f"{attachment_key}-party-c2",
                    "document_key": attachment_key,
                    "quote": party_quote,
                    "mention_text": party_quote,
                },
                {
                    **base,
                    "candidate_ref": f"{attachment_key}-party-c3",
                    "document_key": attachment_key,
                    "quote": second_party_quote,
                    "mention_text": second_party_quote,
                },
            ]
        if prompt_name == "prepare_signature_document":
            return [
                {
                    "candidate_kind": "SIGNATURE_BLOCK",
                    "candidate_ref": f"{attachment_key}-sig-block-1",
                    "document_key": attachment_key,
                    "party_name": party_name,
                    "quote": signer_quote,
                }
            ]
        return None

    return candidates_for


def _hit_attachment_candidates(attachment_key: str):
    """命中标准附件的默认候选注入器（见 _attachment_candidates）。"""
    return _attachment_candidates(
        _STANDARD_HIT_MARKDOWN,
        attachment_key,
        party_name="附件甲方有限公司",
        party_quote="甲方：附件甲方有限公司",
        second_party_quote=_STANDARD_HIT_SECOND_PARTY_LINE,
        signer_quote="## 三、签署区",
    )


def _manifest_candidates(attachment_key: str):
    """附件清单商业装配调用的候选注入器：主合同声明总数与附件，并建立 LINKED 关系。

    只对携带 document_key 的 prepare_attachment_document 清单调用生效；
    party/signature 局部调用（无 document_key）与主合同全文 party/signature 调用不受影响。
    声明与关系都引用主合同原文可定位行，关系目标只使用 source_snapshot 内的实际 document_key。
    """

    def candidates_for(prompt_name, kwargs):
        if prompt_name != "prepare_attachment_document":
            return None
        if _extraction_input_payload(kwargs).get("document_key") != "main":
            return None
        return [
            {
                "candidate_kind": "DECLARED_TOTAL",
                "candidate_ref": "main-manifest-total-1",
                "document_key": "main",
                "declared_total": "1",
                "quote": _MAIN_DECLARED_TOTAL_LINE,
            },
            {
                "candidate_kind": "DECLARED_ATTACHMENT",
                "candidate_ref": "main-manifest-decl-1",
                "document_key": "main",
                "declared_index": "1",
                "declared_title": "技术规范书",
                "quote": _MAIN_DECLARED_ATTACHMENT_LINE,
            },
            {
                "candidate_kind": "ATTACHMENT_RELATION",
                "candidate_ref": "main-manifest-rel-1",
                "document_key": "main",
                "relation_declaration_ref": "main-manifest-decl-1",
                "relation_target_document_keys": [attachment_key],
                "relation_state": "LINKED",
                "quote": _MAIN_DECLARED_ATTACHMENT_LINE,
            },
        ]

    return candidates_for


def _combine_candidates_for(*injectors):
    """按顺序返回首个非 None 的注入结果，用于连续请求覆盖两份不同输入。"""

    def candidates_for(prompt_name, kwargs):
        for injector in injectors:
            candidates = injector(prompt_name, kwargs)
            if candidates is not None:
                return candidates
        return None

    return candidates_for


class _SeamBoom(Exception):
    """内部技术失败哨兵（正式文档未固定内部异常类型）。"""


def test_service_entry_is_single_public_callable():
    """唯一公开入口 prepare_contract(request) -> ReviewContext，无额外必需参数。"""
    service = _service()
    prepare_contract = _attr(service, "prepare_contract")
    assert callable(prepare_contract)

    signature = inspect.signature(prepare_contract, eval_str=True)
    parameters = list(signature.parameters.values())
    assert [parameter.name for parameter in parameters] == ["request"]
    assert parameters[0].default is inspect.Parameter.empty
    assert parameters[0].annotation is PrepareRequest
    assert signature.return_annotation is ReviewContext


def test_pipeline_preserves_fixed_stage_order(monkeypatch):
    """既定语义依赖：输入准备 → 扫描 → 提取 → 引用验证/排序/摘要（DEC-LTC-20260911-005）。"""
    service = _service()
    prepare_contract = _attr(service, "prepare_contract")
    events: list[str] = []
    _patch_ordered_seams(monkeypatch, service, events)
    calls: list = []

    # 附件关联调用证明偏序：把命中附件的局部签章模型调用插进与协作方事件同一条时间线，
    # 用该附件自身的调用（而非笼统的签章协作方事件）证明“扫描先于其局部签章提取”。
    attachment_signature_event = "signature_attachment_local"

    def recorder(prompt_name, **kwargs):
        calls.append((prompt_name, dict(kwargs)))
        if (
            prompt_name == "prepare_signature_document"
            and kwargs.get("markdown") == _STANDARD_HIT_MARKDOWN
            and kwargs.get("scope_label") == "attachment"
        ):
            events.append(attachment_signature_event)
        return _empty_envelope(prompt_name, [])

    _patch_models(monkeypatch, recorder)

    request = _request(
        attachments=(("ATT-STD", "技术规范书.md", _STANDARD_HIT_MARKDOWN),)
    )
    context = prepare_contract(request)

    assert isinstance(context, ReviewContext)
    assert context.context_digest.startswith("sha256:")

    def precedes(earlier: str, later: str) -> None:
        assert earlier in events, f"未观察到协作方 {earlier}"
        assert later in events, f"未观察到协作方 {later}"
        assert events.index(earlier) < events.index(later), f"{earlier} 必须早于 {later}"

    # 输入准备（请求校验/来源快照/内嵌附件/重复门禁）先于标准附件扫描与全部领域提取。
    for later in ("scan", "parties_main", "parties_attachment", "signature", "commercial"):
        precedes("build_inputs", later)

    # 标准附件分类与安全扫描先于其局部 party 提取。
    precedes("scan", "parties_attachment")

    # 标准附件分类与安全扫描先于该附件自身的局部签章提取：以附件关联调用证明偏序。
    precedes("scan", attachment_signature_event)
    attachment_signature_calls = [
        kwargs
        for prompt_name, kwargs in calls
        if prompt_name == "prepare_signature_document"
        and kwargs.get("markdown") == _STANDARD_HIT_MARKDOWN
        and kwargs.get("scope_label") == "attachment"
    ]
    assert attachment_signature_calls, (
        "命中附件的签章必须走 attachment 作用域的局部提取"
    )
    for kwargs in attachment_signature_calls:
        assert _sorted_ranges_from_input(kwargs["extraction_input"]), (
            "附件局部签章提取必须携带扫描得到的绝对 locator 范围"
        )

    # canonical parties 先于依赖它的附件主体装配。
    precedes("parties_main", "parties_attachment")

    # 六域提取先于证据/覆盖聚合、引用验证、稳定排序与摘要计算。
    for earlier in ("parties_main", "parties_attachment", "signature", "commercial"):
        precedes(earlier, "validate_references")
    # 引用验证与稳定排序的相对次序未在权威中固定，只断言二者都早于摘要生成。
    precedes("validate_references", "compute_hashes")
    precedes("sort_payload", "compute_hashes")


def test_definite_duplicate_request_is_rejected_before_any_model_call(monkeypatch):
    """单次请求内的明确重复（重复 attachment_id）必须在任何模型调用前被拒绝。

    正式要求（spec「明确重复附件在模型调用前被拒绝」+ 实施计划 Task 9 / OpenSpec 6.3）：
    同一请求内重复 attachment_id 的明确重复 SHALL 以 10001 参数错误拒绝整次请求，且模型调用
    次数 SHALL 为 0。服务层复用既有公共前置门禁 build_document_inputs 抛出的 PrepareDuplicateError
    （documents.py），不新增服务专属错误类型；对外 10001 映射属 API 层契约，不在本测试断言范围。
    """
    service = _service()
    prepare_contract = _attr(service, "prepare_contract")

    duplicate_request = _request(
        attachments=(
            ("ATT-DUP", "技术规范书.md", _STANDARD_HIT_MARKDOWN),
            ("ATT-DUP", "工作说明书.md", _STANDARD_HIT_MARKDOWN_B),
        )
    )
    assert [
        item.attachment_id for item in duplicate_request.uploaded_attachments
    ] == ["ATT-DUP", "ATT-DUP"], "本反例必须是重复 attachment_id 的明确重复输入"

    calls: list = []
    _patch_models(monkeypatch, _make_recorder(calls))

    with pytest.raises(PrepareDuplicateError, match="attachment_id") as excinfo:
        prepare_contract(duplicate_request)

    assert not isinstance(
        excinfo.value,
        (
            ModelInvocationError,
            ModelTimeoutError,
            ModelOutputTooLongError,
            ModelFormatError,
        ),
    ), "明确重复必须在模型调用前以参数错误拒绝，不得表现为模型技术失败"

    assert calls == [], (
        "明确重复请求的模型调用次数必须为 0: "
        f"{[prompt_name for prompt_name, _ in calls]!r}"
    )


def test_consecutive_requests_do_not_share_state(monkeypatch):
    """连续两份均为非空候选的不同输入不得交叉复用文档映射、候选、证据或问题。"""
    service = _service()
    prepare_contract = _attr(service, "prepare_contract")

    request_a = _request(
        contract_id="C-A",
        revision_id="RA",
        attachments=(("ATT-A", "a-spec.md", _STANDARD_HIT_MARKDOWN),),
    )
    request_b = _request(
        contract_id="C-B",
        revision_id="RB",
        attachments=(("ATT-B", "b-spec.md", _STANDARD_HIT_MARKDOWN_B),),
    )
    prepared_a = build_document_inputs(request_a)
    prepared_b = build_document_inputs(request_b)
    attachment_key_a = _attachment_key(prepared_a)
    attachment_key_b = _attachment_key(prepared_b)
    assert attachment_key_a != attachment_key_b

    calls: list = []
    _patch_models(
        monkeypatch,
        _make_recorder(
            calls,
            # 两份请求各注入一份非空、可定位且互不相同的局部候选。
            candidates_for=_combine_candidates_for(
                _hit_attachment_candidates(attachment_key_a),
                _attachment_candidates(
                    _STANDARD_HIT_MARKDOWN_B,
                    attachment_key_b,
                    party_name="二号技术有限公司",
                    party_quote="甲方：二号技术有限公司",
                    second_party_quote=_STANDARD_HIT_B_SECOND_PARTY_LINE,
                    signer_quote="## 三、签署区",
                ),
            ),
        ),
    )

    context_a = prepare_contract(request_a)
    context_b = prepare_contract(request_b)

    keys_a = {
        context_a.source_snapshot.main_document.document_key,
        *(item.document_key for item in context_a.source_snapshot.attachments),
    }
    keys_b = {
        context_b.source_snapshot.main_document.document_key,
        *(item.document_key for item in context_b.source_snapshot.attachments),
    }
    assert context_a.source_snapshot.contract_id == "C-A"
    assert context_b.source_snapshot.contract_id == "C-B"
    assert attachment_key_a in keys_a and attachment_key_b in keys_b
    assert attachment_key_b not in keys_a and attachment_key_a not in keys_b
    assert context_a.source_snapshot.document_set_hash != context_b.source_snapshot.document_set_hash

    # 证据文档映射与证据身份互不交叉。
    evidence_a = list(context_a.evidence_index.items)
    evidence_b = list(context_b.evidence_index.items)
    assert all(item.document_key in keys_a for item in evidence_a)
    assert all(item.document_key in keys_b for item in evidence_b)
    assert attachment_key_b not in {item.document_key for item in evidence_a}
    assert attachment_key_a not in {item.document_key for item in evidence_b}
    assert {item.evidence_id for item in evidence_a}.isdisjoint(
        {item.evidence_id for item in evidence_b}
    )

    # 候选不跨请求泄漏：A 的 party/signature 事实只归属 A 附件，B 只归属 B 附件。
    mention_keys_a = {
        item.document_key for item in context_a.shared_facts.parties.data.party_mentions
    }
    mention_keys_b = {
        item.document_key for item in context_b.shared_facts.parties.data.party_mentions
    }
    assert attachment_key_a in mention_keys_a
    assert attachment_key_b not in mention_keys_a
    assert mention_keys_a <= keys_a
    assert attachment_key_b in mention_keys_b
    assert attachment_key_a not in mention_keys_b
    assert mention_keys_b <= keys_b

    block_keys_a = {
        item.document_key for item in context_a.shared_facts.signature.data.signature_blocks
    }
    block_keys_b = {
        item.document_key for item in context_b.shared_facts.signature.data.signature_blocks
    }
    assert attachment_key_a in block_keys_a
    assert attachment_key_b not in block_keys_a
    assert block_keys_a <= keys_a
    assert attachment_key_b in block_keys_b
    assert attachment_key_a not in block_keys_b
    assert block_keys_b <= keys_b

    # 问题记录不引用另一请求的文档键。
    for issue in context_a.preparation_issues:
        assert attachment_key_b not in issue.related_document_keys
    for issue in context_b.preparation_issues:
        assert attachment_key_a not in issue.related_document_keys


def test_no_hit_standard_attachment_is_not_sent_to_full_text_llm(monkeypatch):
    """可靠标准附件无扫描候选：保留清单、不发起该附件 party/signature 全文 LLM、相关域 COMPLETE 空事实。"""
    service = _service()
    prepare_contract = _attr(service, "prepare_contract")

    request = _request(
        attachments=(("ATT-TS", "技术规范书.md", _STANDARD_NOHIT_MARKDOWN),)
    )
    prepared = build_document_inputs(request)
    attachment_key = _attachment_key(prepared)
    plan = build_standard_attachment_scan_plan(prepared, attachment_key)
    assert plan is not None and plan.candidate_ranges == []

    # 注入非空清单候选，使清单路径真实装配：主合同声明总数与附件，并连接该无命中附件。
    calls: list = []
    _patch_models(
        monkeypatch,
        _make_recorder(calls, candidates_for=_manifest_candidates(attachment_key)),
    )

    context = prepare_contract(request)

    # 附件仍在来源快照与附件清单中，清单覆盖为 COMPLETE。
    assert attachment_key in {
        item.document_key for item in context.source_snapshot.attachments
    }
    manifest_coverage = _coverage_by_key(context.shared_facts.attachment_manifest)
    assert manifest_coverage[attachment_key].state == "COMPLETE"

    # 该附件的 party/signature 域为真实空事实且 COMPLETE。
    for domain in (context.shared_facts.parties, context.shared_facts.signature):
        coverage = _coverage_by_key(domain)
        assert attachment_key in coverage
        assert coverage[attachment_key].state == "COMPLETE"
    assert not [
        mention
        for mention in context.shared_facts.parties.data.party_mentions
        if mention.document_key == attachment_key
    ]
    assert not [
        block
        for block in context.shared_facts.signature.data.signature_blocks
        if block.document_key == attachment_key
    ]

    # 完整空事实：无命中的标准附件不得产出任何证据坐标，也不得产生任何附件归属字段事实。
    attachment_evidence = [
        item for item in context.evidence_index.items if item.document_key == attachment_key
    ]
    assert not attachment_evidence, (
        "可靠无命中的标准附件不得产生任何证据坐标: "
        f"{[item.quote for item in attachment_evidence]!r}"
    )
    assert not [
        item
        for item in (
            context.shared_facts.signature.data.signature_blocks
            + context.shared_facts.signature.data.account_observations
            + context.shared_facts.signature.data.contact_observations
        )
        if item.document_key == attachment_key
    ]

    # 正式冻结要求（design 第 10 节“扫描无候选…结束内容处理”/ spec 7.5 无命中场景）：
    # 可靠无命中的标准附件正文 SHALL NOT 进入任何模型调用；全文确定性安全扫描不产生
    # 模型调用，因此逐文档清单装配 prepare_attachment_document 同样不得消费其正文。
    attachment_body_calls = [
        (prompt_name, dict(kwargs))
        for prompt_name, kwargs in calls
        if kwargs.get("markdown") == _STANDARD_NOHIT_MARKDOWN
    ]
    assert not attachment_body_calls, (
        "无命中的标准附件正文不得进入任何模型调用（含逐文档清单装配）: "
        f"{[(name, kwargs.get('scope_label')) for name, kwargs in attachment_body_calls]!r}"
    )

    # 清单装配仍逐文档调用主合同，且必须携带排序后的快照附件键集合，
    # 使无命中附件仍作为声明目标保留在清单语义中。
    main_manifest_calls = [
        kwargs
        for prompt_name, kwargs in calls
        if prompt_name == "prepare_attachment_document"
        and _extraction_input_payload(kwargs).get("document_key") == "main"
    ]
    assert main_manifest_calls, "主合同必须进入逐文档清单装配"
    snapshot_attachment_keys = sorted(
        item.document_key for item in context.source_snapshot.attachments
    )
    for kwargs in main_manifest_calls:
        payload = _extraction_input_payload(kwargs)
        assert (
            payload.get("available_attachment_document_keys") == snapshot_attachment_keys
        ), "清单装配必须携带排序后的快照附件键集合"

    # 注入非空清单候选后，清单仍只由主合同声明原文装配：无命中的附件不得被写进
    # 声明或连接，也不得由附件标题、数量或正文建立总数与连接。
    manifest = context.shared_facts.attachment_manifest.data
    assert manifest.declared_total.presence != "ABSENT", "主合同显式总数必须保留"
    assert manifest.declared_total.observations
    assert manifest.declarations, "主合同逐份声明必须保留"
    assert manifest.links, "声明到附件的连接必须保留"
    assert manifest.logical_attachment_candidates == []
    evidence_by_id = {item.evidence_id: item for item in context.evidence_index.items}
    for declaration in manifest.declarations:
        for evidence_id in declaration.evidence_ids:
            assert evidence_by_id[evidence_id].document_key == "main", (
                "清单声明只能来自主合同原文，不得由该附件正文或标题改写而来"
            )
    for link in manifest.links:
        assert link.candidate_document_keys == [attachment_key]
        for evidence_id in link.evidence_ids:
            assert evidence_by_id[evidence_id].document_key == "main", (
                "清单连接只能由主合同原文声明建立"
            )


def test_hit_standard_attachment_local_extraction_uses_merged_locators(monkeypatch):
    """标准附件命中：仅把合并后绝对 locator 传给局部提取，证据归属附件，同坐标去重、同值异坐标保留。"""
    service = _service()
    prepare_contract = _attr(service, "prepare_contract")

    request = _request(
        attachments=(("ATT-TS", "技术规范书.md", _STANDARD_HIT_MARKDOWN),)
    )
    prepared = build_document_inputs(request)
    attachment_key = _attachment_key(prepared)
    plan = build_standard_attachment_scan_plan(prepared, attachment_key)
    assert plan is not None and plan.candidate_ranges
    # 扫描计划的 scanned_range / candidate_ranges 必须是文档边界内的合法 MarkdownCharLocator。
    validate_scan_plan(plan, _STANDARD_HIT_MARKDOWN)

    merged = merge_overlapping_ranges(
        scan_complete_markdown_for_review_facts(_STANDARD_HIT_MARKDOWN)
    )
    assert list(plan.candidate_ranges) == list(merged)
    expected_ranges = sorted(list(parse_markdown_locator(locator)) for locator in merged)

    calls: list = []
    _patch_models(
        monkeypatch,
        _make_recorder(
            calls,
            candidates_for=_hit_attachment_candidates(attachment_key),
        ),
    )

    context = prepare_contract(request)

    attachment_calls = [
        kwargs for _, kwargs in calls if kwargs.get("markdown") == _STANDARD_HIT_MARKDOWN
    ]
    assert attachment_calls, "标准附件命中后未触发任何局部提取调用"
    for kwargs in attachment_calls:
        extraction_input = kwargs.get("extraction_input")
        assert extraction_input not in (None, "", "{}"), "标准附件不得整份全文提取"
        assert _sorted_ranges_from_input(extraction_input) == expected_ranges

    for domain in (context.shared_facts.parties, context.shared_facts.signature):
        assert attachment_key in _coverage_by_key(domain)

    evidence_by_id = {item.evidence_id: item for item in context.evidence_index.items}

    attachment_mentions = [
        mention
        for mention in context.shared_facts.parties.data.party_mentions
        if mention.document_key == attachment_key
    ]
    assert len(attachment_mentions) == 2, (
        "同坐标重复候选须去重、同值异坐标须各自保留: "
        f"{[mention.observed_text for mention in attachment_mentions]!r}"
    )
    assert len({mention.evidence_ids[0] for mention in attachment_mentions}) == 2
    for mention in attachment_mentions:
        assert mention.evidence_ids
        for evidence_id in mention.evidence_ids:
            assert evidence_by_id[evidence_id].document_key == attachment_key

    # 附件 party 证据坐标必须真实落在已定位的扫描窗口内。
    for mention in attachment_mentions:
        for evidence_id in mention.evidence_ids:
            span = parse_markdown_locator(evidence_by_id[evidence_id].source_locator)
            assert any(
                low <= span[0] and span[1] <= high for low, high in expected_ranges
            ), f"附件 party 证据坐标 {span} 必须落在已定位扫描窗口内: {expected_ranges!r}"

    # 附件签章：命中后必须产出归属附件的非空签章块，证据坐标指向附件正文真实坐标。
    attachment_blocks = [
        block
        for block in context.shared_facts.signature.data.signature_blocks
        if block.document_key == attachment_key
    ]
    assert attachment_blocks, "附件命中后签章事实不得为空"
    block_start = _STANDARD_HIT_MARKDOWN.index("## 三、签署区")
    block_end = block_start + len("## 三、签署区")
    block_evidence_ids = {
        evidence_id for block in attachment_blocks for evidence_id in block.evidence_ids
    }
    assert block_evidence_ids
    for evidence_id in block_evidence_ids:
        item = evidence_by_id[evidence_id]
        assert item.document_key == attachment_key
        assert parse_markdown_locator(item.source_locator) == (block_start, block_end)


def test_out_of_directory_attachment_uses_full_text_extraction(monkeypatch):
    """目录外附件不进入标准路径，必须走普通完整提取（无局部范围）。"""
    service = _service()
    prepare_contract = _attr(service, "prepare_contract")
    calls: list = []
    _patch_models(monkeypatch, _make_recorder(calls))

    request = _request(
        attachments=(("ATT-BIZ", "商务协议.md", _OUT_OF_DIRECTORY_MARKDOWN),)
    )
    prepared = build_document_inputs(request)
    attachment_key = _attachment_key(prepared)
    assert build_standard_attachment_scan_plan(prepared, attachment_key) is None

    prepare_contract(request)

    out_of_directory_calls = [
        kwargs
        for _, kwargs in calls
        if kwargs.get("markdown") == _OUT_OF_DIRECTORY_MARKDOWN
    ]
    assert out_of_directory_calls, "目录外附件必须走普通完整提取"
    assert any(
        kwargs.get("extraction_input") in (None, "", "{}")
        for kwargs in out_of_directory_calls
    )


def test_boundary_unreliable_standard_named_attachment_falls_back_to_full_text(monkeypatch):
    """名称标准但类型不可靠的附件必须回退普通完整提取，不得进入标准扫描路径。

    正式依据：spec 7.5“类型或边界不可靠”场景与同名 Requirement；内部身份冲突属类型不可靠。
    边界不可证明的内嵌附件在本请求完整 markdown_by_document 传入校验后不再可达
    （实施计划 281：组装后切片不一致属于内部装配失败），其覆盖见
    tests/two_stage/test_prepare_long_document.py 的两个边界用例。
    """
    service = _service()
    prepare_contract = _attr(service, "prepare_contract")

    request = _request(
        attachments=(("ATT-STD", "技术规范书.md", _STANDARD_CONFLICT_MARKDOWN),)
    )
    prepared = build_document_inputs(request)
    attachment_key = _attachment_key(prepared)
    assert build_standard_attachment_scan_plan(prepared, attachment_key) is None

    calls: list = []
    _patch_models(monkeypatch, _make_recorder(calls))

    prepare_contract(request)

    attachment_calls = [
        kwargs
        for _, kwargs in calls
        if kwargs.get("markdown") == _STANDARD_CONFLICT_MARKDOWN
    ]
    assert attachment_calls, "类型不可靠的标准名称附件必须回退普通完整提取"
    assert any(
        kwargs.get("extraction_input") in (None, "", "{}")
        for kwargs in attachment_calls
    )


@pytest.mark.parametrize("failure_type", _TECHNICAL_FAILURES, ids=lambda item: item.__name__)
def test_model_technical_failure_fails_whole_request(monkeypatch, failure_type):
    """模型超时/调用失败/输出截断/格式失败：整体失败，不得返回 ReviewContext。"""
    service = _service()
    prepare_contract = _attr(service, "prepare_contract")
    calls: list = []
    failure = failure_type("模拟技术失败")
    _patch_models(
        monkeypatch,
        _make_recorder(calls, fail=("prepare_header_parties_main", failure)),
    )

    with pytest.raises(failure_type):
        prepare_contract(_request())


_SEAM_FAILURES = (
    ("scan", long_document, "build_standard_attachment_scan_plan"),
    ("local_locator_merge", long_document, "merge_overlapping_ranges"),
    ("validate_scan_plan", long_document, "validate_scan_plan"),
    ("local_party_extract", extract_header_parties, "extract_attachment_party_mentions"),
    ("local_signature_extract", extract_signature, "extract_signature_facts"),
    ("evidence_assembly", None, "EvidenceRegistry"),
    ("evidence_register", None, "EvidenceRegistry.register"),
    ("evidence_items", None, "EvidenceRegistry.items"),
    ("merge_sort", hashing, "sort_review_context"),
    ("validate_references", validation, "validate_review_context"),
    ("digest", hashing, "compute_context_digest"),
    # 真实结果装配接缝：文档集哈希与 Prompt 包哈希在最终装配阶段计算，失败必须整体传播。
    ("document_set_hash", documents_module, "compute_document_set_hash"),
    ("prompt_bundle_hash", prepare_prompts, "compute_prepare_prompt_bundle_hash"),
    # 结果装配/合并使用的规范化序列化：最终载荷序列化失败同样必须整体传播。
    ("result_payload_serialization", hashing, "canonical_json_bytes"),
)

# 证据注册表内部接缝：装配（构造）与真实注册分别失败都必须整体传播，不得返回残缺上下文。
_EVIDENCE_REGISTRY_SEAMS = {
    "evidence_assembly": "__init__",
    "evidence_register": "register",
    "evidence_items": "items",
}


@pytest.mark.parametrize(
    ("stage", "source_module", "name"),
    _SEAM_FAILURES,
    ids=[case[0] for case in _SEAM_FAILURES],
)
def test_pipeline_seam_failure_fails_whole_request(monkeypatch, stage, source_module, name):
    """扫描/局部 locator 合并与校验/局部 party 提取/局部 signature 提取/证据装配/结果排序合并/引用验证/摘要任一步失败：向上传播，不返回残缺上下文。"""
    service = _service()
    prepare_contract = _attr(service, "prepare_contract")
    calls: list = []
    _patch_models(monkeypatch, _make_recorder(calls))

    if source_module is None:
        attribute = _EVIDENCE_REGISTRY_SEAMS[stage]

        def boom(*args, **kwargs):
            raise _SeamBoom(stage)

        monkeypatch.setattr(EvidenceRegistry, attribute, boom)
    else:
        def boom(*args, **kwargs):
            raise _SeamBoom(stage)

        _patch_seam(monkeypatch, service, source_module, name, boom)

    request = _request(
        attachments=(("ATT-STD", "技术规范书.md", _STANDARD_HIT_MARKDOWN),)
    )
    with pytest.raises(Exception):
        prepare_contract(request)


def test_multi_range_local_result_assembly_failure_fails_whole_request(monkeypatch):
    """命中附件给出多个互不重叠的局部窗口：多范围局部结果的装配/合并失败须整体失败。

    scan 对该附件给出多个独立窗口，局部 party 提取已按合并窗口发起；随后把局部候选
    装配成文档结果的协作方失败时，不得返回任何 ReviewContext，也不得降级为 coverage。
    """
    service = _service()
    prepare_contract = _attr(service, "prepare_contract")

    request = _request(
        attachments=(("ATT-STD", "技术规范书.md", _STANDARD_HIT_MARKDOWN),)
    )
    prepared = build_document_inputs(request)
    attachment_key = _attachment_key(prepared)
    plan = build_standard_attachment_scan_plan(prepared, attachment_key)
    assert plan is not None
    merged_windows = sorted(
        parse_markdown_locator(locator) for locator in plan.candidate_ranges
    )
    assert len(merged_windows) >= 2, (
        "本反例必须建立在真实多范围局部结果之上: "
        f"{merged_windows!r}"
    )

    calls: list = []
    _patch_models(
        monkeypatch,
        _make_recorder(calls, candidates_for=_hit_attachment_candidates(attachment_key)),
    )

    def boom(*args, **kwargs):
        raise _SeamBoom("multi_range_result_assembly")

    _patch_seam(
        monkeypatch, service, extract_header_parties, "assemble_party_mentions", boom
    )

    with pytest.raises(Exception):
        prepare_contract(request)

    # 失败发生在局部结果装配阶段：失败前已按合并窗口发起局部 party 提取。
    local_party_calls = [
        kwargs
        for name, kwargs in calls
        if name == "prepare_attachment_document"
        and kwargs.get("markdown") == _STANDARD_HIT_MARKDOWN
        and "document_key" not in _extraction_input_payload(kwargs)
    ]
    assert local_party_calls, "多范围局部结果装配失败前必须已发起局部 party 提取"
    expected_windows = [list(window) for window in merged_windows]
    for kwargs in local_party_calls:
        assert (
            _sorted_ranges_from_input(kwargs["extraction_input"]) == expected_windows
        ), "局部提取必须只携带扫描合并得到的多范围窗口"


def test_verifiable_source_gap_downgrades_coverage(monkeypatch):
    """具体文档、具体类别且来源可验证的局部缺口形成 PARTIAL 降级并记录问题。

    单个可定位的 SIGNING_DATE 缺口只覆盖适用签章类别的子集，因此严格为
    PARTIAL，不得被判为 UNAVAILABLE（只有缺口并集覆盖全部适用类别才允许）。
    """
    service = _service()
    prepare_contract = _attr(service, "prepare_contract")
    calls: list = []
    gaps = {
        "prepare_signature_document": [
            {
                "affected_fact_kinds": ["SIGNING_DATE"],
                "message": "签署日期局部不可读",
                "quote": "签署日期：2026年1月1日",
                "document_key": "main",
            }
        ]
    }
    _patch_models(monkeypatch, _make_recorder(calls, gaps_by_prompt=gaps))

    context = prepare_contract(_request())

    coverage = _coverage_by_key(context.shared_facts.signature)
    assert coverage["main"].state == "PARTIAL"
    assert coverage["main"].affected_fact_kinds
    assert coverage["main"].fact_issue_keys


def test_no_source_gap_does_not_downgrade_coverage(monkeypatch):
    """无缺口时不得伪造 PARTIAL/UNAVAILABLE 降级。"""
    service = _service()
    prepare_contract = _attr(service, "prepare_contract")
    calls: list = []
    _patch_models(monkeypatch, _make_recorder(calls))

    context = prepare_contract(_request())

    domains = (
        context.shared_facts.header,
        context.shared_facts.parties,
        context.shared_facts.signature,
        context.shared_facts.amount_payment,
        context.shared_facts.copy_terms,
        context.shared_facts.attachment_manifest,
    )
    for domain in domains:
        assert domain.state == "COMPLETE"
        assert all(coverage.state == "COMPLETE" for coverage in domain.coverage)


def test_technical_failure_never_returns_partial_context(monkeypatch):
    """技术失败不得伪装为覆盖不足：整体失败，不返回任何（含 PARTIAL）上下文。"""
    service = _service()
    prepare_contract = _attr(service, "prepare_contract")
    calls: list = []
    _patch_models(
        monkeypatch,
        _make_recorder(
            calls,
            fail=("prepare_header_parties_main", ModelTimeoutError("模拟超时")),
        ),
    )

    with pytest.raises(Exception):
        prepare_contract(_request())


def _snapshot_keys(snapshot) -> set[str]:
    return {
        snapshot.main_document.document_key,
        *(item.document_key for item in snapshot.attachments),
    }


def _scoped_request_pair():
    """两份结构一致、取值不同且各带一份非空命中附件的请求。"""
    request_a = _request(
        contract_id="C-A",
        revision_id="RA",
        attachments=(("ATT-A", "a-spec.md", _STANDARD_HIT_MARKDOWN),),
    )
    request_b = _request(
        contract_id="C-B",
        revision_id="RB",
        attachments=(("ATT-B", "b-spec.md", _STANDARD_HIT_MARKDOWN_B),),
    )
    attachment_key_a = _attachment_key(build_document_inputs(request_a))
    attachment_key_b = _attachment_key(build_document_inputs(request_b))
    return request_a, request_b, attachment_key_a, attachment_key_b


def _signature_gap_by_markdown(markdown: str, attachment_key: str, quote: str, message: str) -> dict:
    """按文档精确注入一个可定位的签章 source_gap（只降级该附件的签章覆盖）。"""
    return {
        ("prepare_signature_document", markdown): [
            {
                "affected_fact_kinds": ["SIGNING_DATE"],
                "message": message,
                "quote": quote,
                "document_key": attachment_key,
            }
        ]
    }


def _second_request_candidates(attachment_key_b: str):
    return _attachment_candidates(
        _STANDARD_HIT_MARKDOWN_B,
        attachment_key_b,
        party_name="二号技术有限公司",
        party_quote="甲方：二号技术有限公司",
        second_party_quote=_STANDARD_HIT_B_SECOND_PARTY_LINE,
        signer_quote="## 三、签署区",
    )


def _assert_requests_isolated(
    context_a, context_b, attachment_key_a: str, attachment_key_b: str
) -> None:
    """两份请求的文档映射、证据身份、非空问题与摘要互不交叉。"""
    keys_a = _snapshot_keys(context_a.source_snapshot)
    keys_b = _snapshot_keys(context_b.source_snapshot)
    assert context_a.source_snapshot.contract_id == "C-A"
    assert context_b.source_snapshot.contract_id == "C-B"
    assert attachment_key_a in keys_a and attachment_key_b in keys_b
    assert attachment_key_b not in keys_a and attachment_key_a not in keys_b
    assert (
        context_a.source_snapshot.document_set_hash
        != context_b.source_snapshot.document_set_hash
    )
    assert context_a.context_digest != context_b.context_digest

    evidence_a = list(context_a.evidence_index.items)
    evidence_b = list(context_b.evidence_index.items)
    assert all(item.document_key in keys_a for item in evidence_a)
    assert all(item.document_key in keys_b for item in evidence_b)
    assert attachment_key_b not in {item.document_key for item in evidence_a}
    assert attachment_key_a not in {item.document_key for item in evidence_b}
    assert {item.evidence_id for item in evidence_a}.isdisjoint(
        {item.evidence_id for item in evidence_b}
    )

    # 非空问题：两份请求各自产生只引用自身文档的事实问题，且问题键互不交叉。
    issues_a = context_a.shared_facts.signature.issues
    issues_b = context_b.shared_facts.signature.issues
    assert issues_a and issues_b, "可定位缺口必须产生非空事实问题"
    assert {issue.fact_issue_key for issue in issues_a}.isdisjoint(
        {issue.fact_issue_key for issue in issues_b}
    )
    for issue in issues_a:
        assert set(issue.related_document_keys) <= keys_a
        assert attachment_key_b not in issue.related_document_keys
    for issue in issues_b:
        assert set(issue.related_document_keys) <= keys_b
        assert attachment_key_a not in issue.related_document_keys

    for issue in context_a.preparation_issues:
        assert set(issue.related_document_keys) <= keys_a
        assert attachment_key_b not in issue.related_document_keys
    for issue in context_b.preparation_issues:
        assert set(issue.related_document_keys) <= keys_b
        assert attachment_key_a not in issue.related_document_keys


def test_pipeline_partial_order_holds_without_attachments(monkeypatch):
    """无附件请求同样满足正式偏序：输入准备 → 提取 → 引用验证 → 稳定排序 → 摘要。"""
    service = _service()
    prepare_contract = _attr(service, "prepare_contract")
    events: list[str] = []
    _patch_ordered_seams(monkeypatch, service, events)
    calls: list = []
    _patch_models(monkeypatch, _make_recorder(calls))

    context = prepare_contract(_request())

    assert isinstance(context, ReviewContext)
    assert context.context_digest.startswith("sha256:")

    def precedes(earlier: str, later: str) -> None:
        assert earlier in events, f"未观察到协作方 {earlier}: {events!r}"
        assert later in events, f"未观察到协作方 {later}: {events!r}"
        assert (
            events.index(earlier) < events.index(later)
        ), f"{earlier} 必须早于 {later}: {events!r}"

    # 输入准备先于全部领域提取。
    for later in ("parties_main", "signature", "commercial"):
        precedes("build_inputs", later)
    # 各领域提取先于引用验证、稳定排序与摘要计算。
    for earlier in ("parties_main", "signature", "commercial"):
        precedes(earlier, "validate_references")
    # 引用验证与稳定排序的相对次序未在权威中固定，只断言二者都早于摘要生成。
    precedes("validate_references", "compute_hashes")
    precedes("sort_payload", "compute_hashes")


def test_hit_attachment_keeps_manifest_and_uses_local_paths(monkeypatch):
    """双路径与清单保留：主合同走全文、命中附件走局部 party/signature，附件仍在快照与清单中。"""
    service = _service()
    prepare_contract = _attr(service, "prepare_contract")

    request = _request(
        attachments=(("ATT-STD", "技术规范书.md", _STANDARD_HIT_MARKDOWN),)
    )
    prepared = build_document_inputs(request)
    attachment_key = _attachment_key(prepared)
    expected_ranges = sorted(
        list(parse_markdown_locator(locator))
        for locator in merge_overlapping_ranges(
            scan_complete_markdown_for_review_facts(_STANDARD_HIT_MARKDOWN)
        )
    )

    calls: list = []
    _patch_models(
        monkeypatch,
        _make_recorder(
            calls,
            candidates_for=_combine_candidates_for(
                _hit_attachment_candidates(attachment_key),
                _manifest_candidates(attachment_key),
            ),
        ),
    )

    context = prepare_contract(request)

    # 主合同双域走全文路径：输入为主合同 markdown 且不携带局部范围。
    main_calls = [
        kwargs
        for name, kwargs in calls
        if name in ("prepare_header_parties_main", "prepare_signature_document")
        and kwargs.get("markdown") == _MAIN_MARKDOWN
    ]
    assert main_calls, "主合同必须走全文 party/signature 提取"
    assert all(
        kwargs.get("extraction_input") in (None, "", "{}") for kwargs in main_calls
    ), "主合同不得携带局部范围"
    assert not [
        name
        for name, kwargs in calls
        if name == "prepare_header_parties_main"
        and kwargs.get("markdown") == _STANDARD_HIT_MARKDOWN
    ], "附件正文不得作为主合同主体提取输入"

    # 命中附件的 party/signature 走局部路径，且携带合并后的绝对范围。
    local_party_calls = [
        kwargs
        for name, kwargs in calls
        if name == "prepare_attachment_document"
        and kwargs.get("markdown") == _STANDARD_HIT_MARKDOWN
        and "document_key" not in _extraction_input_payload(kwargs)
    ]
    local_signature_calls = [
        kwargs
        for name, kwargs in calls
        if name == "prepare_signature_document"
        and kwargs.get("markdown") == _STANDARD_HIT_MARKDOWN
    ]
    assert local_party_calls, "命中附件的 party 必须走局部提取路径"
    assert local_signature_calls, "命中附件的 signature 必须走局部提取路径"
    for kwargs in local_party_calls + local_signature_calls:
        assert (
            _sorted_ranges_from_input(kwargs.get("extraction_input")) == expected_ranges
        ), "命中附件局部提取必须只携带合并后的绝对 locator 范围"

    # 清单商业装配逐文档调用：每次调用各自完整携带 extraction_ranges、当前
    # document_key 与排序后的快照附件键集合，不得把全部调用拼成总 blob 后统一判定。
    manifest_calls = [
        kwargs
        for name, kwargs in calls
        if name == "prepare_attachment_document"
        and "document_key" in _extraction_input_payload(kwargs)
    ]
    assert manifest_calls, "附件清单必须逐文档调用商业装配"
    snapshot_attachment_keys = sorted(
        item.document_key for item in prepared.source_snapshot.attachments
    )
    assert {
        _extraction_input_payload(kwargs)["document_key"] for kwargs in manifest_calls
    } == {"main", attachment_key}
    for kwargs in manifest_calls:
        payload = _extraction_input_payload(kwargs)
        assert (
            "extraction_ranges" in payload
        ), "每次清单调用都必须完整携带 extraction_ranges"
        assert payload["available_attachment_document_keys"] == snapshot_attachment_keys, (
            "每次清单调用都必须携带排序后的快照附件键集合"
        )
    assert not [
        kwargs
        for kwargs in manifest_calls
        if kwargs.get("markdown") == _STANDARD_HIT_MARKDOWN
        and _extraction_input_payload(kwargs)["document_key"] != attachment_key
    ], "清单调用不得把当前 document_key 与正文错配"

    # 清单与来源快照保留：附件条目、标题与文档集哈希均不被改写。
    assert attachment_key in {
        item.document_key for item in context.source_snapshot.attachments
    }
    assert context.source_snapshot.attachments == prepared.source_snapshot.attachments
    assert (
        context.source_snapshot.document_set_hash
        == prepared.source_snapshot.document_set_hash
    )
    manifest_coverage = _coverage_by_key(context.shared_facts.attachment_manifest)
    assert manifest_coverage.keys() >= {"main", attachment_key}

    # 清单 data 必须真实装配主合同声明的总数与逐份条目，并保留声明到附件的连接。
    manifest = context.shared_facts.attachment_manifest.data
    assert manifest.declared_total.presence != "ABSENT", "主合同显式总数必须保留"
    assert manifest.declared_total.observations
    assert manifest.declarations, "主合同逐份声明必须保留"
    allowed_keys = _snapshot_keys(context.source_snapshot)
    assert manifest.links, "声明与附件之间的连接必须保留"
    for link in manifest.links:
        assert set(link.candidate_document_keys) <= allowed_keys
    declared_titles = {
        observation.raw_text
        for declaration in manifest.declarations
        for observation in declaration.title.observations
    }
    assert "技术规范书" in declared_titles, "声明标题必须是主合同原文标题，不得被改写"

    # 局部命中后附件签章事实非空。
    assert [
        block
        for block in context.shared_facts.signature.data.signature_blocks
        if block.document_key == attachment_key
    ], "命中附件的签章事实不得为空"


def test_evidence_registry_dedups_by_locator_coordinate(monkeypatch):
    """证据身份只由 (document_key, 绝对坐标) 决定：同坐标唯一、同值异坐标分别保留。"""
    service = _service()
    prepare_contract = _attr(service, "prepare_contract")

    request = _request(
        attachments=(("ATT-STD", "技术规范书.md", _STANDARD_HIT_MARKDOWN),)
    )
    prepared = build_document_inputs(request)
    attachment_key = _attachment_key(prepared)

    calls: list = []
    _patch_models(
        monkeypatch,
        _make_recorder(calls, candidates_for=_hit_attachment_candidates(attachment_key)),
    )

    context = prepare_contract(request)

    # 注册表不变量：任意 document_key 下不得出现两个相同坐标的证据项。
    spans = [
        (item.document_key, item.source_locator)
        for item in context.evidence_index.items
    ]
    assert len(spans) == len(set(spans)), "同坐标必须共享同一证据身份"

    evidence_by_id = {item.evidence_id: item for item in context.evidence_index.items}
    mentions = [
        mention
        for mention in context.shared_facts.parties.data.party_mentions
        if mention.document_key == attachment_key
    ]
    assert len(mentions) == 2, (
        "同坐标重复候选须去重、同值异坐标须各自保留: "
        f"{[mention.observed_text for mention in mentions]!r}"
    )
    assert all(mention.evidence_ids for mention in mentions)
    mention_spans = [
        parse_markdown_locator(evidence_by_id[mention.evidence_ids[0]].source_locator)
        for mention in mentions
    ]
    assert len(set(mention_spans)) == 2, "同值异坐标必须分别保留各自证据坐标"
    assert len({mention.evidence_ids[0] for mention in mentions}) == 2

    # 附件坐标互不相同的证据各自独立登记，不同域也不得共享同一坐标身份。
    attachment_spans = [
        item.source_locator
        for item in context.evidence_index.items
        if item.document_key == attachment_key
    ]
    assert len(attachment_spans) == len(set(attachment_spans))
    assert len(attachment_spans) >= 3, (
        "附件 party 两个独立坐标与签章坐标必须各自登记真实证据: "
        f"{attachment_spans!r}"
    )


def test_non_empty_issues_and_call_metadata_are_isolated_between_requests(monkeypatch):
    """连续两份含非空缺口的请求：域问题、preparation_issues、摘要与调用载荷互不泄漏。

    token 级用量只经 prepare_model 的私有日志事件出现（logger.info extra），没有任何
    公开可观察面：本用例只锁定可观察的调用载荷对象（kwargs 与 extraction_input 字符串）
    不得跨请求复用；该私有日志接缝上的非空 token 用量隔离另由
    test_model_token_usage_is_isolated_between_consecutive_requests 与
    test_model_token_usage_is_isolated_between_concurrent_requests 锁定。
    """
    service = _service()
    prepare_contract = _attr(service, "prepare_contract")
    request_a, request_b, attachment_key_a, attachment_key_b = _scoped_request_pair()

    gaps = {
        **_signature_gap_by_markdown(
            _STANDARD_HIT_MARKDOWN,
            attachment_key_a,
            "签署日期：2026年2月2日",
            "A 请求签署日期局部不可读",
        ),
        **_signature_gap_by_markdown(
            _STANDARD_HIT_MARKDOWN_B,
            attachment_key_b,
            "签署日期：2026年3月3日",
            "B 请求签署日期局部不可读",
        ),
    }
    calls: list = []
    _patch_models(
        monkeypatch,
        _make_scoped_recorder(
            calls,
            gaps,
            _combine_candidates_for(
                _hit_attachment_candidates(attachment_key_a),
                _second_request_candidates(attachment_key_b),
            ),
        ),
    )

    context_a = prepare_contract(request_a)
    first_batch = list(calls)
    markdowns_a = {kwargs.get("markdown") for _, kwargs in first_batch}
    payload_ids_a = {
        (id(kwargs), id(kwargs.get("extraction_input"))) for _, kwargs in first_batch
    }
    # 调用元数据对象不得跨请求复用：篡改 A 的调用记录不得影响 B。
    for _, kwargs in first_batch:
        kwargs["markdown"] = "MUTATED-BY-TEST"
        kwargs["extraction_input"] = "MUTATED-BY-TEST"
    context_b = prepare_contract(request_b)
    second_batch = calls[len(first_batch):]
    markdowns_b = {kwargs.get("markdown") for _, kwargs in second_batch}
    payload_ids_b = {
        (id(kwargs), id(kwargs.get("extraction_input"))) for _, kwargs in second_batch
    }

    assert _STANDARD_HIT_MARKDOWN in markdowns_a
    assert _STANDARD_HIT_MARKDOWN_B in markdowns_b
    assert _STANDARD_HIT_MARKDOWN_B not in markdowns_a
    assert _STANDARD_HIT_MARKDOWN not in markdowns_b
    assert all(markdown != "MUTATED-BY-TEST" for markdown in markdowns_b)
    assert payload_ids_a.isdisjoint(payload_ids_b), (
        "两次请求的私有调用载荷（kwargs 与 extraction_input）必须是各自独立的对象"
    )

    # 非空缺口只降级对应附件的签章覆盖，主合同保持 COMPLETE。
    signature_state_a = _coverage_by_key(context_a.shared_facts.signature)
    signature_state_b = _coverage_by_key(context_b.shared_facts.signature)
    assert signature_state_a[attachment_key_a].state == "PARTIAL"
    assert signature_state_a["main"].state == "COMPLETE"
    assert signature_state_b[attachment_key_b].state == "PARTIAL"
    assert signature_state_b["main"].state == "COMPLETE"

    _assert_requests_isolated(context_a, context_b, attachment_key_a, attachment_key_b)


def test_concurrent_requests_do_not_share_non_empty_state(monkeypatch):
    """并发两份含非空候选与问题的输入：文档映射、证据、问题与摘要互不共享。"""
    service = _service()
    prepare_contract = _attr(service, "prepare_contract")
    request_a, request_b, attachment_key_a, attachment_key_b = _scoped_request_pair()

    gaps = {
        **_signature_gap_by_markdown(
            _STANDARD_HIT_MARKDOWN,
            attachment_key_a,
            "签署日期：2026年2月2日",
            "A 请求签署日期局部不可读",
        ),
        **_signature_gap_by_markdown(
            _STANDARD_HIT_MARKDOWN_B,
            attachment_key_b,
            "签署日期：2026年3月3日",
            "B 请求签署日期局部不可读",
        ),
    }
    calls: list = []
    _patch_models(
        monkeypatch,
        _make_scoped_recorder(
            calls,
            gaps,
            _combine_candidates_for(
                _hit_attachment_candidates(attachment_key_a),
                _second_request_candidates(attachment_key_b),
            ),
        ),
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        future_a = pool.submit(prepare_contract, request_a)
        future_b = pool.submit(prepare_contract, request_b)
        context_a = future_a.result(timeout=60)
        context_b = future_b.result(timeout=60)

    assert isinstance(context_a, ReviewContext)
    assert isinstance(context_b, ReviewContext)
    _assert_requests_isolated(context_a, context_b, attachment_key_a, attachment_key_b)


# ---- 私有 token 观测接缝：连续/并发请求的非空 token 用量隔离 --------------------
# prepare_model 成功路径通过 prepare_model_attempt 私有日志事件携带 token_usage；
# 本组用例只观测该既有私有接缝，不改写它、不新增公开 API 或私有 helper 契约。

_TOKEN_MARKER_A = "请求A专用正文"
_TOKEN_MARKER_B = "请求B专用正文"
_TOKEN_USAGE_A = {"total_tokens": 111}
_TOKEN_USAGE_B = {"total_tokens": 222}


def _token_scoped_markdown(marker: str) -> str:
    """给主合同正文注入请求专属标记，使每次真实模型调用都能归属到唯一请求。"""
    return _MAIN_MARKDOWN + f"备注：{marker}。\n"


def _patch_token_seam(monkeypatch, observed: list) -> None:
    """只替换 prepare_model 的底层模型入口，让真实 invoke_typed_prepare_model 记录 token 用量。"""
    monkeypatch.setattr(prepare_model, "get_chat_model", lambda: object())

    def fake_invoke(model, messages, response_format=None):
        text = "\n".join(str(getattr(message, "content", "")) for message in messages)
        if _TOKEN_MARKER_A in text:
            kind, token_usage = "A", dict(_TOKEN_USAGE_A)
        elif _TOKEN_MARKER_B in text:
            kind, token_usage = "B", dict(_TOKEN_USAGE_B)
        else:
            kind, token_usage = "UNKNOWN", {"total_tokens": 0}
        observed.append((kind, token_usage))
        payload = {"candidates": [], "source_gaps": []}
        return json.dumps(payload, ensure_ascii=False), token_usage

    monkeypatch.setattr(prepare_model, "invoke_model", fake_invoke)


def _token_request_pair():
    request_a = _request(
        main_markdown=_token_scoped_markdown(_TOKEN_MARKER_A),
        contract_id="C-A",
        revision_id="RA",
    )
    request_b = _request(
        main_markdown=_token_scoped_markdown(_TOKEN_MARKER_B),
        contract_id="C-B",
        revision_id="RB",
    )
    return request_a, request_b


def _attempt_records(records):
    return [
        record
        for record in records
        if record.getMessage() == "prepare_model_attempt"
    ]


def _usage_pair(token_usage):
    return tuple(sorted((token_usage or {}).items()))


def test_model_token_usage_is_isolated_between_consecutive_requests(monkeypatch, caplog):
    """连续两份请求：真实适配层的非空 token 用量只归属本请求，绝不交叉或复用对象。"""
    service = _service()
    prepare_contract = _attr(service, "prepare_contract")
    observed: list = []
    _patch_token_seam(monkeypatch, observed)
    request_a, request_b = _token_request_pair()

    with caplog.at_level(logging.INFO, logger="prepare_model"):
        caplog.clear()
        prepare_contract(request_a)
        records_a = list(caplog.records)
        caplog.clear()
        prepare_contract(request_b)
        records_b = list(caplog.records)

    attempts_a = _attempt_records(records_a)
    attempts_b = _attempt_records(records_b)
    assert attempts_a, "请求 A 必须产生非空 token 用量观测"
    assert attempts_b, "请求 B 必须产生非空 token 用量观测"
    assert {kind for kind, _ in observed} == {"A", "B"}, (
        "每次真实模型调用都必须携带唯一请求正文: "
        f"{[kind for kind, _ in observed]!r}"
    )
    assert {_usage_pair(record.token_usage) for record in attempts_a} == {
        _usage_pair(_TOKEN_USAGE_A)
    }, "请求 A 的 token 用量不得混入其他请求或为空"
    assert {_usage_pair(record.token_usage) for record in attempts_b} == {
        _usage_pair(_TOKEN_USAGE_B)
    }, "请求 B 的 token 用量不得混入其他请求或为空"
    assert {id(record.token_usage) for record in attempts_a}.isdisjoint(
        {id(record.token_usage) for record in attempts_b}
    ), "两份请求不得共享同一个 token 用量对象"


def test_model_token_usage_is_isolated_between_concurrent_requests(monkeypatch, caplog):
    """并发两份请求：每次真实模型调用的非空 token 用量各自独立，不跨请求共享。"""
    service = _service()
    prepare_contract = _attr(service, "prepare_contract")
    observed: list = []
    _patch_token_seam(monkeypatch, observed)
    request_a, request_b = _token_request_pair()

    with caplog.at_level(logging.INFO, logger="prepare_model"):
        caplog.clear()
        with ThreadPoolExecutor(max_workers=2) as pool:
            future_a = pool.submit(prepare_contract, request_a)
            future_b = pool.submit(prepare_contract, request_b)
            future_a.result(timeout=60)
            future_b.result(timeout=60)
        attempts = _attempt_records(list(caplog.records))

    assert attempts, "并发请求必须产生非空 token 用量观测"
    assert {kind for kind, _ in observed} == {"A", "B"}
    assert {_usage_pair(record.token_usage) for record in attempts} == {
        _usage_pair(_TOKEN_USAGE_A),
        _usage_pair(_TOKEN_USAGE_B),
    }, "并发请求的 token 用量必须各自归属本请求，不得出现第三种或缺失归属的取值"
    assert len({id(record.token_usage) for record in attempts}) == len(attempts), (
        "每次模型调用的 token 用量必须是各自独立对象，不得跨请求共享"
    )


# ---------------------------------------------------------------------------
# FROZEN 后最小 RED 集（cluster=task9-service-red / repair_cycle=2 / fuse_state=FROZEN）
# 两条服务契约补强：正式依据为 design 第 10 节、spec 7.5 无命中场景，以及实施计划
# Task 2 Step 5 与 Task 9 Step 4 参考实现（计划 281、735–740）。本批次只补测试，
# 不改生产代码、不重置轮次、不追加 P2 清理。
# ---------------------------------------------------------------------------


def test_no_hit_standard_attachment_body_enters_no_model_call(monkeypatch):
    """可靠标准附件无扫描候选：正文不得进入任何模型调用，同时保留来源/清单/连接/覆盖。

    正式依据：design 第 10 节“扫描无候选且完整执行时…结束内容处理”、spec 7.5 无命中场景
    “系统 SHALL NOT 对整份附件发起全文 LLM 语义提取”，且“该附件仍 SHALL 保留完整清单、
    来源、摘要、声明关系和覆盖”。全文确定性安全扫描不产生模型调用，因此无命中附件正文
    SHALL NOT 出现在任何已记录模型调用入参中，包含逐文档清单装配调用
    prepare_attachment_document。
    """
    service = _service()
    prepare_contract = _attr(service, "prepare_contract")

    request = _request(
        attachments=(("ATT-TS", "技术规范书.md", _STANDARD_NOHIT_MARKDOWN),)
    )
    prepared = build_document_inputs(request)
    attachment_key = _attachment_key(prepared)
    plan = build_standard_attachment_scan_plan(prepared, attachment_key)
    assert plan is not None and plan.candidate_ranges == []

    # 注入非空清单候选，使清单路径真实装配，静态确认保留不是靠丢弃清单取得。
    calls: list = []
    _patch_models(
        monkeypatch,
        _make_recorder(calls, candidates_for=_manifest_candidates(attachment_key)),
    )

    context = prepare_contract(request)

    # 保留：来源快照、清单覆盖 COMPLETE、三域 COMPLETE、无证据坐标。
    assert attachment_key in {
        item.document_key for item in context.source_snapshot.attachments
    }, "无命中的可靠标准附件必须保留在来源快照中"
    assert (
        _coverage_by_key(context.shared_facts.attachment_manifest)[attachment_key].state
        == "COMPLETE"
    ), "无命中的可靠标准附件清单覆盖必须为 COMPLETE"
    for domain in (context.shared_facts.parties, context.shared_facts.signature):
        assert (
            _coverage_by_key(domain)[attachment_key].state == "COMPLETE"
        ), "无命中附件相关事实域必须以 COMPLETE 空事实结束"
    assert not [
        item
        for item in context.evidence_index.items
        if item.document_key == attachment_key
    ], "可靠无命中的标准附件不得产生任何证据坐标"

    # 保留：清单声明与到该附件的连接仍由主合同声明原文装配。
    manifest = context.shared_facts.attachment_manifest.data
    assert manifest.declared_total.presence != "ABSENT", "主合同显式总数必须保留"
    assert manifest.declarations, "主合同逐份声明必须保留"
    assert [
        link
        for link in manifest.links
        if attachment_key in link.candidate_document_keys
    ], "附件清单必须保留指向该附件的连接"

    # 正式要求：无命中附件正文不得进入任何模型调用。
    leaked_calls = [
        (prompt_name, kwargs.get("scope_label"))
        for prompt_name, kwargs in calls
        if isinstance(kwargs.get("markdown"), str)
        and _STANDARD_NOHIT_MARKDOWN in kwargs["markdown"]
    ]
    assert not leaked_calls, (
        "无命中的标准附件正文不得进入任何模型调用（含逐文档清单装配）: "
        f"{leaked_calls!r}"
    )


def test_final_validation_receives_complete_markdown_by_document(monkeypatch):
    """最终引用验证必须接收本请求完整的规范化 markdown_by_document（主合同与全部附件）。

    正式依据：实施计划 Task 2 Step 5“校验器需要接收可选 markdown_by_document；Prepare
    返回前必须传入全文映射执行切片校验”，以及 Task 9 Step 4 参考实现（计划 735–740）。
    映射必须覆盖本请求的主合同与全部附件，且为本请求规范化后的文档正文；缺键、只给主合同
    或完全不传都不满足要求。
    """
    service = _service()
    prepare_contract = _attr(service, "prepare_contract")

    request = _request(
        attachments=(
            ("ATT-TS", "技术规范书.md", _STANDARD_NOHIT_MARKDOWN),
            ("ATT-BIZ", "商务协议.md", _OUT_OF_DIRECTORY_MARKDOWN),
        )
    )
    prepared = build_document_inputs(request)
    expected_markdown_by_document = dict(prepared.markdown_by_document)
    assert "main" in expected_markdown_by_document
    assert len(expected_markdown_by_document) == 3, "本请求为 1 份主合同 + 2 份附件"

    calls: list = []
    _patch_models(monkeypatch, _make_recorder(calls))

    captured: list = []
    original_validate = validation.validate_review_context

    def recording_validate(context, **kwargs):
        captured.append(dict(kwargs))
        return original_validate(context, **kwargs)

    _patch_seam(
        monkeypatch,
        service,
        validation,
        "validate_review_context",
        recording_validate,
    )

    prepare_contract(request)

    assert captured, "Prepare 必须在返回前完成引用验证"
    received = captured[-1].get("markdown_by_document")
    assert received is not None, (
        "最终校验必须接收本请求完整 markdown_by_document，不得只做结构与摘要校验: "
        f"实际关键字参数 {sorted(captured[-1])!r}"
    )
    assert set(received) == set(expected_markdown_by_document), (
        "校验接收的文档键集合必须是本请求完整集合: "
        f"{sorted(received)!r} != {sorted(expected_markdown_by_document)!r}"
    )
    assert dict(received) == expected_markdown_by_document, (
        "校验接收的文档映射必须等于本请求规范化后的完整映射"
    )
