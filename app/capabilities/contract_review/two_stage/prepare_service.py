from __future__ import annotations

"""Task 9：无状态 Prepare 服务编排的唯一入口。

prepare_contract(request) -> ReviewContext 唯一编排：
输入准备 → 标准附件安全扫描 → 六域提取 → 证据装配 → 引用验证/稳定排序 → 摘要生成。

内部顺序是语义依赖而非运行时阶段标签（DEC-LTC-20260911-004 / -005）：本模块不新增
公共 API、服务专属错误类型或阶段 trace，不缓存任何跨请求状态；全过程只依赖既有公共
协作方，技术失败一律向上传播，绝不以 coverage 降级伪装。
"""

from collections.abc import Sequence
from datetime import datetime, timezone

from app.core.config import get_settings
from app.core.logging import get_logger
from app.capabilities.contract_review.two_stage import (
    documents as documents_module,
    evidence as evidence_module,
    extract_commercial,
    extract_header_parties,
    extract_signature,
    hashing,
    long_document,
    prepare_prompts,
    validation,
)
from app.capabilities.contract_review.two_stage.extract_header_parties import (
    PreparedDocument,
)
from app.capabilities.contract_review.two_stage.schemas import (
    SCHEMA_VERSION,
    DocumentCoverage,
    EvidenceIndex,
    FactDomain,
    PreparationMeta,
    PrepareRequest,
    ReviewContext,
    SharedFacts,
)

PIPELINE_VERSION = "contract-review-prepare/1.0.0"

_logger = get_logger("prepare_service")

_MAIN_DOCUMENT_KEY = "main"
_DIGEST_PLACEHOLDER = "sha256:" + "0" * 64


def _complete_skipped_document_coverage(
    domain: FactDomain,
    skipped_document_keys: Sequence[str],
) -> FactDomain:
    """为未进入局部/全文提取的标准附件补齐 COMPLETE 覆盖，并重算域聚合状态。

    无命中的标准附件只保留清单与空事实：其证据与事实必须为空，覆盖必须为 COMPLETE，
    因此这里不新增任何 issue，只用既有 FactDomain 的聚合口径重算 state。
    """
    if not skipped_document_keys:
        return domain
    coverage = [
        *domain.coverage,
        *(
            DocumentCoverage(
                document_key=document_key,
                state="COMPLETE",
                affected_fact_kinds=[],
                fact_issue_keys=[],
            )
            for document_key in skipped_document_keys
        ),
    ]
    coverage.sort(key=lambda item: item.document_key)
    states = {item.state for item in coverage}
    if states == {"COMPLETE"}:
        state = "COMPLETE"
    elif states == {"UNAVAILABLE"}:
        state = "UNAVAILABLE"
    else:
        state = "PARTIAL"
    return domain.model_copy(update={"coverage": coverage, "state": state})


def _manifest_documents(
    prepared: documents_module.PreparedDocuments,
    skipped_document_keys: Sequence[str],
) -> documents_module.PreparedDocuments:
    """清单装配只消费可进入模型的文档正文：无命中的标准附件正文不得进入任何模型调用。

    来源快照与准备问题原样保留，只从文档映射中移除无命中附件的正文；其清单覆盖由
    调用方按既有 COMPLETE 口径补齐，附件仍作为声明目标保留在来源快照中。
    """
    if not skipped_document_keys:
        return prepared
    skipped = set(skipped_document_keys)
    return documents_module.PreparedDocuments(
        source_snapshot=prepared.source_snapshot,
        markdown_by_document={
            document_key: markdown
            for document_key, markdown in prepared.markdown_by_document.items()
            if document_key not in skipped
        },
        preparation_issues=list(prepared.preparation_issues),
    )


def prepare_contract(request: PrepareRequest) -> ReviewContext:
    # 固定入口事件：只证明边界已进入，不携带任何请求业务内容（正文/证据/号码）。
    _logger.info("prepare_contract_enter")
    prepared = documents_module.build_document_inputs(request)
    evidence = evidence_module.EvidenceRegistry(prepared.markdown_by_document)

    document_keys = sorted(prepared.markdown_by_document)
    main_document = PreparedDocument(
        document_key=_MAIN_DOCUMENT_KEY,
        markdown=prepared.markdown_by_document[_MAIN_DOCUMENT_KEY],
    )

    # 输入准备之后的唯一扫描遍：
    # - 命中附件得到合并后的绝对 locator 范围，供局部 party/signature 提取；
    # - 无命中的可靠标准附件只保留清单与空事实，不发起任何全文/局部 LLM 提取；
    # - 目录外或边界不可证明的附件返回 None，回落普通完整提取。
    extraction_ranges: dict[str, list[tuple[int, int]]] = {}
    skipped_document_keys: list[str] = []
    for document_key in document_keys:
        if document_key == _MAIN_DOCUMENT_KEY:
            continue
        plan = long_document.build_standard_attachment_scan_plan(prepared, document_key)
        if plan is None:
            continue
        if not plan.candidate_ranges:
            skipped_document_keys.append(document_key)
            continue
        # 命中窗口必须先经唯一证据定位与切片核对，才可作为局部提取的合格范围；
        # 同一坐标复用同一证据身份，无窗口的可靠标准附件不产生任何证据坐标
        # （design 第 10 节 / DEC-LTC-20260911-004）。
        markdown = prepared.markdown_by_document[document_key]
        ranges: list[tuple[int, int]] = []
        for locator in plan.candidate_ranges:
            start, end = evidence_module.parse_markdown_locator(locator)
            evidence.register(document_key, markdown[start:end], allowed_range=(start, end))
            ranges.append((start, end))
        extraction_ranges[document_key] = ranges

    # 主合同全文提取唯一确定 canonical parties，附件主体装配依赖该定义。
    main_extraction = extract_header_parties.extract_header_and_main_parties(
        main_document,
        evidence,
    )
    canonical_parties = main_extraction.canonical_parties

    # 附件主体：命中走局部范围，目录外/边界不可靠走全文；无命中的标准附件被完全跳过。
    party_issues = list(main_extraction.fact_issues)
    party_mentions = list(main_extraction.party_mentions)
    for document_key in document_keys:
        if document_key == _MAIN_DOCUMENT_KEY or document_key in skipped_document_keys:
            continue
        mentions = extract_header_parties.extract_attachment_party_mentions(
            PreparedDocument(
                document_key=document_key,
                markdown=prepared.markdown_by_document[document_key],
            ),
            canonical_parties,
            evidence,
            extraction_ranges=extraction_ranges.get(document_key),
            fact_issues=party_issues,
        )
        party_mentions.extend(mentions)

    # 签章逐文档提取：跳过无命中的标准附件，再补齐其 COMPLETE 覆盖。
    signature_domain = extract_signature.extract_signature_facts(
        [
            main_document,
            *(
                PreparedDocument(
                    document_key=document_key,
                    markdown=prepared.markdown_by_document[document_key],
                )
                for document_key in document_keys
                if document_key != _MAIN_DOCUMENT_KEY
                and document_key not in skipped_document_keys
            ),
        ],
        canonical_parties,
        evidence,
        extraction_ranges=extraction_ranges,
    )
    signature_domain = _complete_skipped_document_coverage(
        signature_domain,
        skipped_document_keys,
    )

    # 商业三域：主合同金额/份数 + 逐文档附件清单装配。清单装配只消费可进入模型的
    # 文档正文：无命中的标准附件正文不得进入任何模型调用，故传入的文档映射剔除其
    # 正文；其清单覆盖在本域以既有 COMPLETE 口径补齐，来源快照与准备问题保持不变。
    commercial_domains = extract_commercial.extract_amount_copy_manifest(
        _manifest_documents(prepared, skipped_document_keys),
        canonical_parties,
        evidence,
        extraction_ranges=extraction_ranges,
    )
    attachment_manifest_domain = _complete_skipped_document_coverage(
        commercial_domains.attachment_manifest,
        skipped_document_keys,
    )

    header_domain = extract_header_parties.build_header_fact_domain(
        main_extraction.header,
        main_extraction.fact_issues,
    )
    parties_domain = extract_header_parties.build_parties_fact_domain(
        canonical_parties,
        party_mentions,
        party_issues,
        document_keys,
    )

    context = ReviewContext(
        schema_version=SCHEMA_VERSION,
        source_snapshot=prepared.source_snapshot,
        shared_facts=SharedFacts(
            header=header_domain,
            parties=parties_domain,
            signature=signature_domain,
            amount_payment=commercial_domains.amount_payment,
            copy_terms=commercial_domains.copy_terms,
            attachment_manifest=attachment_manifest_domain,
        ),
        evidence_index=EvidenceIndex(items=evidence.items()),
        preparation_issues=list(prepared.preparation_issues),
        preparation_meta=PreparationMeta(
            pipeline_version=PIPELINE_VERSION,
            prompt_bundle_hash=prepare_prompts.compute_prepare_prompt_bundle_hash(),
            model_deployment=get_settings().llm.model,
            created_at=datetime.now(timezone.utc),
        ),
        context_digest=_DIGEST_PLACEHOLDER,
    )

    # 引用完整性 + 稳定排序 → 摘要生成：先稳定排序，再以同一载荷口径定出摘要，
    # 通过引用验证后按同一排序结果生成最终摘要。
    sorted_context = hashing.sort_review_context(context)
    provisional_digest = validation.compute_context_digest(sorted_context.to_payload())
    sorted_context = sorted_context.model_copy(
        update={"context_digest": provisional_digest}
    )
    validation.validate_review_context(
        sorted_context,
        contract_id=request.contract_id,
        revision_id=request.revision_id,
        markdown_by_document=prepared.markdown_by_document,
    )
    final_digest = hashing.compute_context_digest(sorted_context)
    return sorted_context.model_copy(update={"context_digest": final_digest})
