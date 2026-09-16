from __future__ import annotations

"""Task 7 Step 1-4: amount_payment 商业事实闭合矩阵。

本文件为可执行验收矩阵：正式要求、候选与 Schema、装配对象与引用、证据与逐文档 coverage、
稳定键到测试逐行对应；装配能力缺失或与正式条款不一致时相应用例失败, 直接指向缺口,
不经由 fixture、导入或环境错误伪装。

闭合矩阵（正式要求 -> 候选/Schema -> 装配对象与引用 -> 证据/coverage -> 稳定键 -> 测试）：

| 正式要求 (spec) | 候选 (AmountCopyCandidate) | 装配对象/引用 | 证据 / 逐文档 coverage | 稳定键 | 测试 |
|---|---|---|---|---|---|
| 0 形态：无显式金额仍 COMPLETE | 空 envelope | AmountPaymentFacts 全空 | main COMPLETE, 无 issue | - | test_amount_payment_zero_explicit_amounts_is_complete_empty |
| 1 形态：单一显式金额保留 | 1 TOTAL_AMOUNT | 1 AmountFact | 金额 evidence_ids>=1 | amount_key 由坐标 | test_amount_payment_single_explicit_amount_retained |
| N 形态：全部显式金额保留 | N TOTAL_AMOUNT/AMOUNT_PAIR | N AmountFact, 键互异 | 各自独立证据 | 键互异 | test_amount_payment_multiple_explicit_amounts_all_retained_unique_keys |
| 数字/大写单侧 (spec 193-197) | 单侧 TOTAL_AMOUNT | 已出现一侧 PRESENT_VALUE, 另一侧 ABSENT | 不得补写/反推 | - | test_amount_payment_numeric_only_and_uppercase_only_sides_preserved |
| 同值不同业务位置 (spec 199-202) | 同值不同 label | 两个不同 amount_key | 各自保留证据 | 坐标含语义角色 | test_amount_payment_same_value_distinct_positions_get_distinct_keys |
| 币种/税务口径/十进制字符串 (spec 191) | CURRENCY / AMOUNT_PAIR | AmountFact.currency / tax_treatment | 观察绑定引文 | 十进制字符串非 float | test_amount_payment_currency_tax_and_decimal_string_preserved |
| 整体关系仅由原文明示建立 (spec 191) | 无整体措辞的单独金额 | 无 CONTRACT_OVERALL relation | 不得凭空建立关系 | - | test_amount_payment_contract_overall_requires_independent_original_relation_evidence |
| 整体关系有独立证据且多坐标全保留 | 两处"合同总价"措辞 | 2 CONTRACT_OVERALL relation | 各自独立证据, 禁止择一/合并 | 键由坐标 | test_amount_payment_contract_overall_relation_present_with_explicit_wording |
| 阶段显式金额/付款方式闭合 | PAYMENT_STAGE + stage_amount_numeric/uppercase + stage_payment_method | 阶段 AmountFact + PaymentMethodObservation + stage.amount_keys/payment_method_keys + PAYMENT_STAGE relation | 阶段证据非空 | 键由坐标 | test_amount_payment_payment_stage_explicit_amount_and_method_closure |
| 阶段大写金额原样保留并引用真实 amount_key | PAYMENT_STAGE + stage_amount_uppercase | 阶段 AmountFact.uppercase_amount PRESENT_VALUE + stage.amount_keys + PAYMENT_STAGE relation | 阶段证据非空, 数字侧不得推导 | 键由坐标 | test_amount_payment_payment_stage_uppercase_amount_preserved_and_referenced |
| 无可定位引文的 source_gap 键稳定且重复合并 | source_gaps 无 quote | FactIssue 键仅由固定码/文档/类别构成 | evidence_ids 为空 | 键不含文案 | test_amount_payment_source_gap_without_quote_key_is_stable_and_merged |
| 不可定位引文 source_gap 键稳定且重复合并 | source_gaps quote 无法定位 | FactIssue 键稳定 | 乱序/重复不新增条目 | 键不含 quote | test_amount_payment_unlocatable_source_gap_key_stable_and_merged |
| 共用 envelope 的 source_gap 不跨域误判 | TOTAL_AMOUNT source_gap | amount coverage 降级, copy_terms 不失败 | gap 引文定位 | - | test_amount_payment_source_gap_total_amount_does_not_fail_copy_terms |
| 重复付款阶段保留 (Task7 step1/6) | 2 PAYMENT_STAGE 同比例 | 2 PaymentStage, 键互异 | 不得按顺序/数值合并 | 键由坐标 | test_amount_payment_duplicate_stages_retained_without_merging |
| 禁止计算 (spec 204-208) | 总额+比例, 无阶段金额 | stage.amount_keys 空 | 无数值派生 | 原文十进制字符串 | test_amount_payment_does_not_compute_stage_amount_ratio_sum_or_autofill_uppercase |
| 附件金额不入本域 (spec 102) | 附件文档内金额候选 | 本域只含 main | coverage 仅 main | - | test_amount_payment_attachment_amounts_do_not_enter_main_domain |
| 候选重排/改名不改键 (spec 240-243) | 乱序 + candidate_ref 改名 | 键集合不变 | - | 键不含 candidate_ref | test_amount_payment_candidate_reorder_and_ref_rename_do_not_change_keys |
| 引用闭合 (spec 237-238) | 正常 envelope | 装配产物引用闭合 | - | 键在各自集合内唯一 | test_amount_payment_reference_closure_holds |

入口契约（DEC-LTC-20260910-003）：
1. 装配入口模块 app/capabilities/contract_review/two_stage/extract_commercial.py，
   唯一入口 extract_amount_copy_manifest(documents: PreparedDocuments,
   canonical_parties, evidence, extraction_ranges=None) -> CommercialFactDomains。
2. 结果仅承载 amount_payment、copy_terms、attachment_manifest 三个 FactDomain；
   _domain_from 直取 amount_payment 域。
3. documents 为 PreparedDocuments（source_snapshot + markdown_by_document）；
   模型调用经模块 invoke_typed_prepare_model（沿用 Task 5/6 导入约定，便于定点 patch）。
4. 阶段顺序字段在内部候选命名为 stage_order（公开 PaymentStage.sequence 不变），
   因 prepare prompt 校验禁词表包含阶段顺序英文缩写，避免命名漂移。
"""

import importlib
import re
from typing import Any
from unittest.mock import patch

import pytest

from app.capabilities.contract_review.two_stage.documents import PreparedDocuments
from app.capabilities.contract_review.two_stage.evidence import EvidenceRegistry
from app.capabilities.contract_review.two_stage.extract_header_parties import PreparedDocument
from app.capabilities.contract_review.two_stage.keys import stable_key
from app.capabilities.contract_review.two_stage.prepare_model import (
    AmountCopyCandidate,
    AttachmentCandidate,
    PrepareModelEnvelope,
)
from app.capabilities.contract_review.two_stage.schemas import (
    CanonicalParty,
    EmbeddedAttachmentSnapshot,
    MainDocumentSnapshot,
    ObservedField,
    ObservedValue,
    SourceSnapshot,
    UploadedAttachmentSnapshot,
)

COMMERCIAL_MODULE = "app.capabilities.contract_review.two_stage.extract_commercial"
_ENTRY_CANDIDATES = ("extract_amount_copy_manifest",)
RED_REASON = (
    "Task 7 商业装配入口不可用（非 fixture/导入/环境错误）；"
    "装配入口与返回结构已由 DEC-LTC-20260910-003 固定"
)

MAIN_MD = (
    "采购合同\n"
    "甲方：甲乙科技有限公司\n"
    "乙方：丙丁工程有限公司\n"
    "合同总价：人民币壹佰万元整\n"
    "合同总价：1000000.00元\n"
    "预付款金额：300000.00元（含税价）\n"
    "保证金金额：300000.00元\n"
    "币种：人民币\n"
    "付款方式：银行转账\n"
    "预付款阶段：签订后支付30%\n"
    "进度款阶段：验收后支付30%\n"
    "尾款阶段：质保期满后支付40%\n"
    "定金阶段：签约后支付10%，金额100000.00元，付款方式：电汇\n"
)

UPLOADED_MD = (
    "附件费用清单\n"
    "附件服务费：50000.00元\n"
    "附件税率：6%\n"
)

EMBEDDED_MD = (
    "附件一：技术规范书\n"
    "技术规范正文见下。\n"
)

_DECIMAL_RE = re.compile(r"^-?\d+(?:\.\d+)?$")


def _assembler():
    try:
        return importlib.import_module(COMMERCIAL_MODULE)
    except ImportError:
        pytest.fail(RED_REASON + "：模块 " + COMMERCIAL_MODULE + " 不存在", pytrace=False)


def _extract_fn(module):
    for name in _ENTRY_CANDIDATES:
        fn = getattr(module, name, None)
        if callable(fn):
            return fn
    pytest.fail(
        RED_REASON + "：装配入口缺失（候选名：" + ", ".join(_ENTRY_CANDIDATES) + "）",
        pytrace=False,
    )


def _setup():
    registry = EvidenceRegistry(
        {
            "main": MAIN_MD,
            "uploaded:att-001": UPLOADED_MD,
            "embedded:main:001": EMBEDDED_MD,
        }
    )

    def _party(name: str, def_quote: str) -> CanonicalParty:
        ev = registry.register("main", def_quote)
        return CanonicalParty(
            party_key=stable_key("party", {"declared_name": name}),
            declared_name=ObservedField(
                presence="PRESENT_VALUE",
                normalization_state="VALID",
                observations=[
                    ObservedValue(
                        raw_text=name,
                        normalized_value=name,
                        evidence_ids=[ev.evidence_id],
                    )
                ],
            ),
            definition_evidence_ids=[ev.evidence_id],
        )

    canonical = [
        _party("甲乙科技有限公司", "甲方：甲乙科技有限公司"),
        _party("丙丁工程有限公司", "乙方：丙丁工程有限公司"),
    ]
    docs = {
        "main": PreparedDocument(document_key="main", markdown=MAIN_MD),
        "uploaded:att-001": PreparedDocument(
            document_key="uploaded:att-001", markdown=UPLOADED_MD
        ),
        "embedded:main:001": PreparedDocument(
            document_key="embedded:main:001", markdown=EMBEDDED_MD
        ),
    }
    return registry, canonical, docs


def _prepared_documents(docs: dict[str, PreparedDocument], selected: list[str]) -> PreparedDocuments:
    """构造真实 PreparedDocuments：快照固定含 main + 两个附件，正文按 selected 收口。"""
    snapshot = SourceSnapshot(
        contract_id="c-1",
        revision_id="r-1",
        document_set_hash="sha256:" + "0" * 64,
        main_document=MainDocumentSnapshot(
            document_key="main",
            document_id="doc-main",
            filename="采购合同.md",
            parsed_content_sha256="sha256:" + "0" * 64,
        ),
        attachments=[
            UploadedAttachmentSnapshot(
                document_key="uploaded:att-001",
                source_kind="UPLOADED",
                attachment_id="att-001",
                filename="附件.md",
                parsed_content_sha256="sha256:" + "0" * 64,
            ),
            EmbeddedAttachmentSnapshot(
                document_key="embedded:main:001",
                source_kind="EMBEDDED",
                source_main_document_id="doc-main",
                source_locator="markdown-chars:0-1",
                title="文档标题",
                parsed_content_sha256="sha256:" + "0" * 64,
            ),
        ],
    )
    return PreparedDocuments(
        source_snapshot=snapshot,
        markdown_by_document={key: docs[key].markdown for key in selected},
        preparation_issues=[],
    )


def _amount_candidate(
    ref: str,
    kind: str,
    quote: str,
    *,
    document_key: str = "main",
    **fields: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "candidate_ref": ref,
        "candidate_kind": kind,
        "document_key": document_key,
        "quote": quote,
    }
    for key, value in fields.items():
        if value is not None:
            payload[key] = value
    return payload


def _amount_env(
    candidates: list[dict[str, Any]],
    gaps: list[dict[str, Any]] | None = None,
) -> PrepareModelEnvelope:
    return PrepareModelEnvelope[list[AmountCopyCandidate]].model_validate(
        {"candidates": candidates, "source_gaps": gaps or []}
    )


def _empty_amount_env() -> PrepareModelEnvelope:
    return PrepareModelEnvelope[list[AmountCopyCandidate]].model_validate(
        {"candidates": [], "source_gaps": []}
    )


def _empty_attachment_env() -> PrepareModelEnvelope:
    return PrepareModelEnvelope[list[AttachmentCandidate]].model_validate(
        {"candidates": [], "source_gaps": []}
    )


def _domain_from(result):
    """装配入口返回 CommercialFactDomains：唯一入口下直取 amount_payment 域。"""
    domain = getattr(result, "amount_payment", None)
    if domain is not None and hasattr(domain, "data") and hasattr(domain, "coverage"):
        return domain
    pytest.fail(RED_REASON + "：装配入口未返回 amount_payment 域", pytrace=False)


def _assemble_raw(
    envelopes_by_doc: dict[str, PrepareModelEnvelope],
    *,
    doc_keys: list[str] | None = None,
    extraction_ranges: dict[str, list[tuple[int, int]]] | None = None,
    side_effect: Exception | None = None,
    calls: list[tuple[str, dict[str, Any]]] | None = None,
    registry_box: list | None = None,
):
    """按 patch 约定调用唯一入口, 返回原始 CommercialFactDomains（供跨域断言复用）。"""
    module = _assembler()
    fn = _extract_fn(module)
    if not hasattr(module, "invoke_typed_prepare_model"):
        pytest.fail(
            RED_REASON + "：" + COMMERCIAL_MODULE + " 未按约定暴露 invoke_typed_prepare_model",
            pytrace=False,
        )
    registry, canonical, docs = _setup()
    if registry_box is not None:
        registry_box[:] = [registry, canonical]
    selected = doc_keys or list(envelopes_by_doc.keys())
    prepared_documents = _prepared_documents(docs, selected)

    def _fake(prompt_name: str, **kwargs: Any):
        if calls is not None:
            calls.append((prompt_name, dict(kwargs)))
        if side_effect is not None:
            raise side_effect
        if prompt_name == "prepare_amount_copy_main":
            markdown = kwargs.get("markdown")
            for key in selected:
                if docs[key].markdown == markdown:
                    return envelopes_by_doc[key]
            return _empty_amount_env()
        return _empty_attachment_env()

    with patch.object(module, "invoke_typed_prepare_model", side_effect=_fake):
        return fn(prepared_documents, canonical, registry, extraction_ranges)


def _assemble(
    envelopes_by_doc: dict[str, PrepareModelEnvelope],
    *,
    doc_keys: list[str] | None = None,
    extraction_ranges: dict[str, list[tuple[int, int]]] | None = None,
    side_effect: Exception | None = None,
    calls: list[tuple[str, dict[str, Any]]] | None = None,
    registry_box: list | None = None,
):
    return _domain_from(
        _assemble_raw(
            envelopes_by_doc,
            doc_keys=doc_keys,
            extraction_ranges=extraction_ranges,
            side_effect=side_effect,
            calls=calls,
            registry_box=registry_box,
        )
    )


def _numeric_values(data) -> list[str]:
    values: list[str] = []
    for amount in data.amounts:
        for obs in amount.numeric_amount.observations:
            if obs.normalized_value is not None:
                values.append(obs.normalized_value)
    return values


def _amount_keys(data) -> list[str]:
    return sorted(amount.amount_key for amount in data.amounts)


def _full_candidates() -> list[dict[str, Any]]:
    return [
        _amount_candidate(
            "c1",
            "TOTAL_AMOUNT",
            "合同总价：人民币壹佰万元整",
            total_amount_uppercase="壹佰万元整",
            currency="人民币",
        ),
        _amount_candidate(
            "c2",
            "TOTAL_AMOUNT",
            "合同总价：1000000.00元",
            total_amount_numeric="1000000.00",
        ),
        _amount_candidate(
            "c3",
            "AMOUNT_PAIR",
            "预付款金额：300000.00元（含税价）",
            amount_label="预付款金额",
            amount_numeric="300000.00",
        ),
        _amount_candidate(
            "c4",
            "AMOUNT_PAIR",
            "保证金金额：300000.00元",
            amount_label="保证金金额",
            amount_numeric="300000.00",
        ),
        _amount_candidate(
            "c5",
            "PAYMENT_STAGE",
            "预付款阶段：签订后支付30%",
            stage_name="预付款阶段",
            stage_ratio="30",
        ),
        _amount_candidate(
            "c6",
            "PAYMENT_STAGE",
            "进度款阶段：验收后支付30%",
            stage_name="进度款阶段",
            stage_ratio="30",
        ),
        _amount_candidate(
            "c7",
            "PAYMENT_STAGE",
            "尾款阶段：质保期满后支付40%",
            stage_name="尾款阶段",
            stage_ratio="40",
        ),
    ]


# ---------------------------------------------------------------------------
# A. 0 / 1 / N 显式金额
# ---------------------------------------------------------------------------


def test_amount_payment_zero_explicit_amounts_is_complete_empty():
    """0 形态：可靠扫描无显式金额 -> COMPLETE 空事实, coverage 仅 main。"""
    domain = _assemble({"main": _amount_env([])})
    assert domain.state == "COMPLETE"
    assert [c.document_key for c in domain.coverage] == ["main"]
    assert domain.coverage[0].state == "COMPLETE"
    assert domain.coverage[0].fact_issue_keys == []
    assert domain.data.amounts == []
    assert domain.data.amount_relations == []
    assert domain.data.payment_stages == []


def test_amount_payment_single_explicit_amount_retained():
    """1 形态：单一显式金额装配为 1 个 AmountFact 且自带证据。"""
    domain = _assemble(
        {
            "main": _amount_env(
                [
                    _amount_candidate(
                        "c2",
                        "TOTAL_AMOUNT",
                        "合同总价：1000000.00元",
                        total_amount_numeric="1000000.00",
                    )
                ]
            )
        }
    )
    data = domain.data
    assert len(data.amounts) == 1
    assert data.amounts[0].document_key == "main"
    assert data.amounts[0].evidence_ids
    assert data.amounts[0].numeric_amount.presence == "PRESENT_VALUE"
    assert data.amounts[0].numeric_amount.observations[0].normalized_value == "1000000.00"


def test_amount_payment_multiple_explicit_amounts_all_retained_unique_keys():
    """N 形态：全部显式金额保留, amount_key 互异, 不得静默丢弃任一项。"""
    domain = _assemble({"main": _amount_env(_full_candidates())})
    data = domain.data
    keys = _amount_keys(data)
    assert len(keys) >= 4
    assert len(set(keys)) == len(keys)
    assert "1000000.00" in _numeric_values(data)
    assert "300000.00" in _numeric_values(data)


# ---------------------------------------------------------------------------
# B. 单侧金额 / 同值不同位置 / 币种税务
# ---------------------------------------------------------------------------


def test_amount_payment_numeric_only_and_uppercase_only_sides_preserved():
    """数字/大写单侧：只出现一侧时保留该侧, 另一侧维持未出现状态, 不补写不反推。"""
    domain = _assemble(
        {
            "main": _amount_env(
                [
                    _amount_candidate(
                        "c1",
                        "TOTAL_AMOUNT",
                        "合同总价：人民币壹佰万元整",
                        total_amount_uppercase="壹佰万元整",
                        currency="人民币",
                    ),
                    _amount_candidate(
                        "c2",
                        "TOTAL_AMOUNT",
                        "合同总价：1000000.00元",
                        total_amount_numeric="1000000.00",
                    ),
                ]
            )
        }
    )
    data = domain.data
    assert len(data.amounts) == 2
    uppercase_only = [
        a for a in data.amounts if a.uppercase_amount.presence == "PRESENT_VALUE"
    ]
    numeric_only = [a for a in data.amounts if a.numeric_amount.presence == "PRESENT_VALUE"]
    assert len(uppercase_only) == 1
    assert len(numeric_only) == 1
    assert uppercase_only[0].numeric_amount.presence != "PRESENT_VALUE"
    assert numeric_only[0].uppercase_amount.presence != "PRESENT_VALUE"


def test_amount_payment_same_value_distinct_positions_get_distinct_keys():
    """同值不同业务位置：数值相同但语义角色不同时必须生成两个不同 amount_key。"""
    domain = _assemble(
        {
            "main": _amount_env(
                [
                    _amount_candidate(
                        "c3",
                        "AMOUNT_PAIR",
                        "预付款金额：300000.00元（含税价）",
                        amount_label="预付款金额",
                        amount_numeric="300000.00",
                    ),
                    _amount_candidate(
                        "c4",
                        "AMOUNT_PAIR",
                        "保证金金额：300000.00元",
                        amount_label="保证金金额",
                        amount_numeric="300000.00",
                    ),
                ]
            )
        }
    )
    data = domain.data
    assert len(data.amounts) == 2
    assert len({a.amount_key for a in data.amounts}) == 2
    assert set(_numeric_values(data)) == {"300000.00"}
    assert all(a.evidence_ids for a in data.amounts)


def test_amount_payment_currency_tax_and_decimal_string_preserved():
    """币种/税务口径/十进制字符串：数值用十进制字符串保留, 币种与含税口径按引文观察,
    引文未含税务口径的金额不得被自动补齐。"""
    domain = _assemble({"main": _amount_env(_full_candidates())})
    data = domain.data

    numeric_observations = _numeric_values(data)
    assert numeric_observations
    for value in numeric_observations:
        assert isinstance(value, str)
        assert _DECIMAL_RE.fullmatch(value), "数值必须是十进制字符串, 不得转 float"
    assert "1000000.00" in numeric_observations, "原文小数位必须原样保留"

    currency_values = [
        obs.normalized_value
        for amount in data.amounts
        for obs in amount.currency.observations
        if obs.normalized_value is not None
    ]
    assert "人民币" in currency_values

    taxed = [
        amount
        for amount in data.amounts
        if amount.tax_treatment.presence == "PRESENT_VALUE"
    ]
    assert taxed, "引文明示含税价时必须保留税务口径观察"
    assert any(
        "含税" in (obs.raw_text or "") or "含税" in (obs.normalized_value or "")
        for amount in taxed
        for obs in amount.tax_treatment.observations
    )
    assert len(taxed) < len(data.amounts), "引文未含税务口径的金额不得被自动补齐"


# ---------------------------------------------------------------------------
# C. 整体关系与付款阶段
# ---------------------------------------------------------------------------


def test_amount_payment_contract_overall_requires_independent_original_relation_evidence():
    """CONTRACT_OVERALL 仅由独立原文关系证据建立：只有孤立金额、无整体关系措辞时,
    不得凭空建立 CONTRACT_OVERALL 关系。"""
    domain = _assemble(
        {
            "main": _amount_env(
                [
                    _amount_candidate(
                        "c4",
                        "AMOUNT_PAIR",
                        "保证金金额：300000.00元",
                        amount_label="保证金金额",
                        amount_numeric="300000.00",
                    )
                ]
            )
        }
    )
    relations = domain.data.amount_relations
    assert not [r for r in relations if r.relation_kind == "CONTRACT_OVERALL"]


def test_amount_payment_contract_overall_relation_present_with_explicit_wording():
    """含"合同总价"明示措辞且位于不同已定位坐标的每个金额都建立独立 CONTRACT_OVERALL,
    两个金额与两条 relation 必须全部保留, 禁止 min()/择一/合并;
    无整体措辞的其它金额不得被标记为整体金额。"""
    box: list = []
    domain = _assemble(
        {"main": _amount_env(_full_candidates())},
        registry_box=box,
    )
    registry, _canonical = box
    quotes = {item.evidence_id: item.quote for item in registry.items()}
    data = domain.data

    overall = [r for r in data.amount_relations if r.relation_kind == "CONTRACT_OVERALL"]
    assert len(overall) == 2, "两处独立整体措辞必须各自保留 CONTRACT_OVERALL, 不得择一"
    reserved = {r.amount_key for r in overall}
    assert len(reserved) == 2, "两条整体关系必须指向两个不同金额"
    amount_keys = {a.amount_key for a in data.amounts}
    assert reserved <= amount_keys

    relation_evidence_ids = [e for r in overall for e in r.evidence_ids]
    assert len(set(relation_evidence_ids)) == 2, "每条整体关系必须自带独立原文关系证据"
    for evidence_id in relation_evidence_ids:
        assert "合同总价" in quotes[evidence_id]

    stage_amounts = {
        a.amount_key
        for a in data.amounts
        for obs in a.semantic_role.observations
        if obs.normalized_value in {"预付款金额", "保证金金额"}
    }
    assert not (reserved & stage_amounts), "无整体措辞的金额不得被标记为整体金额"


def test_amount_payment_duplicate_stages_retained_without_merging():
    """重复付款阶段保留：同比例不同业务阶段不得按顺序或数值合并, 键必须互异。"""
    domain = _assemble(
        {
            "main": _amount_env(
                [
                    _amount_candidate(
                        "c5",
                        "PAYMENT_STAGE",
                        "预付款阶段：签订后支付30%",
                        stage_name="预付款阶段",
                        stage_ratio="30",
                    ),
                    _amount_candidate(
                        "c6",
                        "PAYMENT_STAGE",
                        "进度款阶段：验收后支付30%",
                        stage_name="进度款阶段",
                        stage_ratio="30",
                    ),
                ]
            )
        }
    )
    stages = domain.data.payment_stages
    assert len(stages) == 2
    assert len({s.payment_stage_key for s in stages}) == 2
    ratios = {
        obs.normalized_value
        for s in stages
        for obs in s.ratio_percent.observations
        if obs.normalized_value is not None
    }
    assert ratios == {"30"}, "同比例阶段必须全部保留, 不得合并"


def test_amount_payment_does_not_compute_stage_amount_ratio_sum_or_autofill_uppercase():
    """禁止派生计算：不得生成期望阶段金额/比例合计/差额/舍入/尾差, 不得自动补大写。"""
    domain = _assemble({"main": _amount_env(_full_candidates())})
    data = domain.data

    assert set(_numeric_values(data)) == {"1000000.00", "300000.00"}, (
        "金额集合必须恰等于原文显式值, 不得不经原文计算期望阶段金额/差额/尾差"
    )
    for amount in data.amounts:
        if amount.numeric_amount.presence == "PRESENT_VALUE":
            assert amount.uppercase_amount.presence != "PRESENT_VALUE", (
                "不得由数字金额自动生成大写金额"
            )
    for stage in data.payment_stages:
        assert stage.amount_keys == [], "原文未明示阶段金额时不得计算期望阶段金额"
    ratios = {
        obs.normalized_value
        for stage in data.payment_stages
        for obs in stage.ratio_percent.observations
        if obs.normalized_value is not None
    }
    assert ratios == {"30", "40"}, "比例必须原样保留, 不得合计或调整"
    assert set(data.model_dump().keys()) == {
        "amounts",
        "amount_relations",
        "payment_methods",
        "payment_stages",
    }


# ---------------------------------------------------------------------------
# D. 附件隔离 / 稳定键 / 引用闭合
# ---------------------------------------------------------------------------


def test_amount_payment_attachment_amounts_do_not_enter_main_domain():
    """附件金额不得进入 amount_payment 本域：本域只含 main, coverage 仅 main。"""
    domain = _assemble(
        {
            "main": _amount_env(
                [
                    _amount_candidate(
                        "c2",
                        "TOTAL_AMOUNT",
                        "合同总价：1000000.00元",
                        total_amount_numeric="1000000.00",
                    )
                ]
            ),
            "uploaded:att-001": _amount_env(
                [
                    _amount_candidate(
                        "c9",
                        "AMOUNT_PAIR",
                        "附件服务费：50000.00元",
                        document_key="uploaded:att-001",
                        amount_label="附件服务费",
                        amount_numeric="50000.00",
                    )
                ]
            ),
        },
        doc_keys=["main", "uploaded:att-001"],
    )
    data = domain.data
    assert [c.document_key for c in domain.coverage] == ["main"]
    assert all(a.document_key == "main" for a in data.amounts)
    assert "50000.00" not in _numeric_values(data)


def test_amount_payment_candidate_reorder_and_ref_rename_do_not_change_keys():
    """候选重排与 candidate_ref 改名不得改变稳定键与输出集合。"""
    forward = _full_candidates()
    shuffled = [forward[6], forward[2], forward[0], forward[4], forward[1], forward[5], forward[3]]
    renamed = [
        dict(candidate, candidate_ref="z" + str(90 + index))
        for index, candidate in enumerate(forward)
    ]

    first = _assemble({"main": _amount_env(forward)})
    second = _assemble({"main": _amount_env(shuffled)})
    third = _assemble({"main": _amount_env(renamed)})

    assert _amount_keys(first.data) == _amount_keys(second.data)
    assert _amount_keys(first.data) == _amount_keys(third.data)
    assert sorted(
        stage.payment_stage_key for stage in first.data.payment_stages
    ) == sorted(stage.payment_stage_key for stage in third.data.payment_stages)


def test_amount_payment_reference_closure_holds():
    """引用闭合：关系/阶段引用现存目标, 键在各自集合内唯一, 金额证据非空。"""
    domain = _assemble({"main": _amount_env(_full_candidates())})
    data = domain.data
    amount_keys = {a.amount_key for a in data.amounts}
    method_keys = {m.payment_method_key for m in data.payment_methods}
    stage_keys = {s.payment_stage_key for s in data.payment_stages}

    assert len(amount_keys) == len(data.amounts)
    assert len(stage_keys) == len(data.payment_stages)
    for relation in data.amount_relations:
        assert relation.amount_key in amount_keys
        if relation.payment_stage_key is not None:
            assert relation.payment_stage_key in stage_keys
    for stage in data.payment_stages:
        assert set(stage.amount_keys) <= amount_keys
        assert set(stage.payment_method_keys) <= method_keys
    for amount in data.amounts:
        assert amount.evidence_ids


# ---------------------------------------------------------------------------
# E. P1 因果矩阵补强
# ---------------------------------------------------------------------------


def test_amount_payment_payment_stage_explicit_amount_and_method_closure():
    """阶段显式金额与付款方式闭合：PAYMENT_STAGE 候选带有可定位的阶段金额与付款方式时,
    必须装配出阶段 AmountFact、PaymentMethodObservation, 并让 stage.amount_keys /
    stage.payment_method_keys 指向它们, 且有 PAYMENT_STAGE relation 把金额挂到阶段上,
    禁止静默丢弃。"""
    domain = _assemble(
        {
            "main": _amount_env(
                [
                    _amount_candidate(
                        "s1",
                        "PAYMENT_STAGE",
                        "定金阶段：签约后支付10%，金额100000.00元，付款方式：电汇",
                        stage_name="定金阶段",
                        stage_ratio="10",
                        stage_order="1",
                        stage_amount_numeric="100000.00",
                        stage_payment_method="电汇",
                    )
                ]
            )
        }
    )
    data = domain.data
    assert len(data.payment_stages) == 1
    stage = data.payment_stages[0]
    amount_keys = {amount.amount_key for amount in data.amounts}
    method_keys = {method.payment_method_key for method in data.payment_methods}

    assert stage.amount_keys, "阶段显式金额必须装配为 AmountFact 并计入 stage.amount_keys"
    assert set(stage.amount_keys) <= amount_keys
    assert stage.payment_method_keys, (
        "阶段显式付款方式必须装配为 PaymentMethodObservation 并计入 stage.payment_method_keys"
    )
    assert set(stage.payment_method_keys) <= method_keys

    stage_relations = [
        relation
        for relation in data.amount_relations
        if relation.relation_kind == "PAYMENT_STAGE"
    ]
    assert stage_relations, "阶段显式金额必须建立闭合的 PAYMENT_STAGE relation"
    assert {relation.amount_key for relation in stage_relations} == set(stage.amount_keys)
    assert all(
        relation.payment_stage_key == stage.payment_stage_key
        for relation in stage_relations
    )

    numeric_values = {
        observation.normalized_value
        for amount in data.amounts
        for observation in amount.numeric_amount.observations
    }
    assert "100000.00" in numeric_values, "阶段金额数值必须原样保留"
    assert "电汇" in {method.raw_text for method in data.payment_methods}


def test_amount_payment_source_gap_total_amount_does_not_fail_copy_terms():
    """共用 main envelope 的合法 source_gap 不得跨域误判：
    TOTAL_AMOUNT 缺口只让 amount_payment 对应 coverage 降级, copy_terms 仍为 COMPLETE 而非技术失败。"""
    gaps = [
        {
            "affected_fact_kinds": ["TOTAL_AMOUNT"],
            "message": "整体金额声明疑似被涂改",
            "quote": "合同总价：1000000.00元",
        }
    ]
    result = _assemble_raw(
        {
            "main": _amount_env(
                [
                    _amount_candidate(
                        "c2",
                        "TOTAL_AMOUNT",
                        "合同总价：1000000.00元",
                        total_amount_numeric="1000000.00",
                    )
                ],
                gaps=gaps,
            )
        }
    )
    amount_coverage = next(
        item for item in result.amount_payment.coverage if item.document_key == "main"
    )
    assert amount_coverage.state == "PARTIAL", "TOTAL_AMOUNT 缺口只降级 amount_payment 对应 coverage"
    assert amount_coverage.affected_fact_kinds == ["TOTAL_AMOUNT"]
    assert result.copy_terms.state == "COMPLETE", "TOTAL_AMOUNT 缺口不得令 copy_terms 技术失败"
    assert result.copy_terms.issues == []


# ---------------------------------------------------------------------------
# E. source_gap / FactIssue 稳定键
# ---------------------------------------------------------------------------


def test_amount_payment_source_gap_fact_issue_key_ignores_model_wording():
    """source_gap/FactIssue 稳定键：保持 document、类别、错误类型与业务坐标一致,
    仅改变模型 quote/message 时 fact_issue_key 必须不变, 不得把模型自由文案纳入稳定键。"""
    first_gap = {
        "affected_fact_kinds": ["TOTAL_AMOUNT"],
        "message": "无法可靠定位总价条款（甲）",
        "quote": "总价条款文本片段甲在解析正文中并不存在",
    }
    second_gap = {
        "affected_fact_kinds": ["TOTAL_AMOUNT"],
        "message": "无法可靠定位总价条款（乙）",
        "quote": "总价条款文本片段乙在解析正文中并不存在",
    }

    def _envelope(gap: dict[str, Any]) -> PrepareModelEnvelope:
        return _amount_env(
            [
                _amount_candidate(
                    "c2",
                    "TOTAL_AMOUNT",
                    "合同总价：1000000.00元",
                    total_amount_numeric="1000000.00",
                )
            ],
            gaps=[gap],
        )

    first = _assemble_raw({"main": _envelope(first_gap)})
    second = _assemble_raw({"main": _envelope(second_gap)})

    first_keys = sorted(issue.fact_issue_key for issue in first.amount_payment.issues)
    second_keys = sorted(issue.fact_issue_key for issue in second.amount_payment.issues)
    assert len(first_keys) == 1, "不可定位缺口必须保留为一条 FactIssue"
    assert first_keys == second_keys, "仅模型文案变化不得改变 FactIssue 稳定键"


def test_amount_payment_payment_stage_uppercase_amount_preserved_and_referenced():
    """阶段大写金额：PAYMENT_STAGE 携带可定位的大写金额时, 必须原样保留为大写观察, 并由
    stage.amount_keys 与 PAYMENT_STAGE relation 引用真实 amount_key; 数字侧不得被推导补齐。"""
    domain = _assemble(
        {
            "main": _amount_env(
                [
                    _amount_candidate(
                        "s1",
                        "PAYMENT_STAGE",
                        "合同总价：人民币壹佰万元整",
                        stage_name="尾款阶段",
                        stage_order="1",
                        stage_amount_uppercase="壹佰万元整",
                    )
                ]
            )
        }
    )
    data = domain.data
    assert len(data.payment_stages) == 1
    stage = data.payment_stages[0]
    assert stage.amount_keys, "阶段大写金额必须装配为 AmountFact 并计入 stage.amount_keys"

    amount_keys = {amount.amount_key for amount in data.amounts}
    assert set(stage.amount_keys) <= amount_keys
    stage_amounts = [
        amount for amount in data.amounts if amount.amount_key in set(stage.amount_keys)
    ]
    assert stage_amounts
    for amount in stage_amounts:
        assert amount.uppercase_amount.presence == "PRESENT_VALUE", (
            "原文大写金额必须保留为 PRESENT_VALUE"
        )
        uppercase_values = {
            value
            for observation in amount.uppercase_amount.observations
            for value in (observation.raw_text, observation.normalized_value)
        }
        assert "壹佰万元整" in uppercase_values, "大写金额必须原样保留"
        assert amount.numeric_amount.presence != "PRESENT_VALUE", (
            "不得由大写金额推导数字金额"
        )

    stage_relations = [
        relation
        for relation in data.amount_relations
        if relation.relation_kind == "PAYMENT_STAGE"
    ]
    assert stage_relations, "阶段大写金额必须建立闭合的 PAYMENT_STAGE relation"
    assert {relation.amount_key for relation in stage_relations} == set(stage.amount_keys)
    assert all(
        relation.payment_stage_key == stage.payment_stage_key
        for relation in stage_relations
    )


def test_amount_payment_source_gap_without_quote_key_is_stable_and_merged():
    """无可定位引文的 source_gap：仅文案与顺序变化不得改变 FactIssue 稳定键, 同一稳定坐标
    的重复缺口必须合并为一条, 且不得伪造 evidence_ids。"""

    def _envelope(gaps: list[dict[str, Any]]) -> PrepareModelEnvelope:
        return _amount_env(
            [
                _amount_candidate(
                    "c2",
                    "TOTAL_AMOUNT",
                    "合同总价：1000000.00元",
                    total_amount_numeric="1000000.00",
                )
            ],
            gaps=gaps,
        )

    first_gap = {
        "affected_fact_kinds": ["TOTAL_AMOUNT"],
        "message": "无法可靠定位总价条款（甲）",
    }
    second_gap = {
        "affected_fact_kinds": ["TOTAL_AMOUNT"],
        "message": "无法可靠定位总价条款（乙）",
    }

    first = _assemble_raw({"main": _envelope([first_gap])})
    second = _assemble_raw({"main": _envelope([second_gap])})
    reordered = _assemble_raw({"main": _envelope([second_gap, first_gap])})
    duplicated = _assemble_raw({"main": _envelope([first_gap, second_gap, first_gap])})

    def _issue_keys(result) -> list[str]:
        return sorted(issue.fact_issue_key for issue in result.amount_payment.issues)

    assert len(_issue_keys(first)) == 1, "无引文缺口必须保留为一条 FactIssue"
    assert _issue_keys(first) == _issue_keys(second), "仅模型文案变化不得改变稳定键"
    assert _issue_keys(first) == _issue_keys(reordered), "仅缺口顺序变化不得改变稳定键"
    assert _issue_keys(duplicated) == _issue_keys(first), (
        "同一稳定坐标的重复缺口必须合并为一条"
    )
    for issue in duplicated.amount_payment.issues:
        assert issue.evidence_ids == [], "无可定位引文时不得伪造 evidence_ids"
        assert issue.code == "SOURCE_UNREADABLE"


def test_amount_payment_unlocatable_source_gap_key_stable_and_merged():
    """不可定位引文的 source_gap：引文/文案变化与缺口乱序都不得改变稳定键, 重复缺口合并,
    且不得把模型 quote/文案纳入稳定键。"""

    def _envelope(gaps: list[dict[str, Any]]) -> PrepareModelEnvelope:
        return _amount_env(
            [
                _amount_candidate(
                    "c2",
                    "TOTAL_AMOUNT",
                    "合同总价：1000000.00元",
                    total_amount_numeric="1000000.00",
                )
            ],
            gaps=gaps,
        )

    first_gap = {
        "affected_fact_kinds": ["TOTAL_AMOUNT"],
        "message": "无法定位总价条款（甲）",
        "quote": "总价条款片段甲不在解析正文中",
    }
    second_gap = {
        "affected_fact_kinds": ["TOTAL_AMOUNT"],
        "message": "无法定位总价条款（乙）",
        "quote": "总价条款片段乙不在解析正文中",
    }

    first = _assemble_raw({"main": _envelope([first_gap])})
    second = _assemble_raw({"main": _envelope([second_gap])})
    reordered = _assemble_raw({"main": _envelope([second_gap, first_gap])})
    duplicated = _assemble_raw({"main": _envelope([first_gap, second_gap, first_gap])})

    def _issue_keys(result) -> list[str]:
        return sorted(issue.fact_issue_key for issue in result.amount_payment.issues)

    assert len(_issue_keys(first)) == 1, "不可定位缺口必须保留为一条 FactIssue"
    assert _issue_keys(first) == _issue_keys(second), "仅模型文案/引文变化不得改变稳定键"
    assert _issue_keys(first) == _issue_keys(reordered), "仅缺口顺序变化不得改变稳定键"
    assert _issue_keys(duplicated) == _issue_keys(first), (
        "同一稳定坐标的重复缺口必须合并为一条"
    )
    for issue in duplicated.amount_payment.issues:
        assert issue.code == "EVIDENCE_UNLOCATABLE"
        assert issue.evidence_ids == []
