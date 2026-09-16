from __future__ import annotations

"""Task 6 Step 1-3: signature 跨层契约簇闭合矩阵 -- 仅 RED 测试。

闭合矩阵（正式要求 -> 候选/Schema -> 装配对象与引用 -> 证据/逐文档 coverage -> 稳定键 -> 测试）：

| 要求 | 候选(SignatureCandidate) | 装配对象/引用 | 证据/coverage | 稳定键 | 测试 |
|---|---|---|---|---|---|
| 真实块多栏位 | SIGNATURE_BLOCK+SIGNER_NAME | SignatureBlock/SignerSlot(slot->block) | 块 evidence_ids>=1; main COMPLETE | block/slot key 由坐标生成 | test_sig_real_block_multiple_slots |
| 一栏多人 | 多条 SIGNER_NAME 同 role_text | slot.signer_keys 全部保留 | 每人独立证据 | signer key 由姓名+栏位坐标 | test_sig_multiple_names_in_one_slot_all_kept |
| 多人多号不清 | 2 SIGNER_NAME+2 IDENTITY_NUMBER | PersonIdRelation 全 UNCERTAIN, 禁顺序配对 | - | 乱序候选键不变 | test_sig_multiple_persons_multiple_ids_uncertain |
| 直接关联 | 显式 X身份证号:Y | relation association_state=DIRECT | 独立证据 | - | test_sig_direct_identity_association |
| 块内唯一关联 | 1人1号非显式 | association_state=UNIQUE_IN_BLOCK | - | - | test_sig_unique_in_block_association |
| 无关人员 | 见证人 SIGNER_NAME | slot.role_state=IRRELEVANT_PERSON, 无 relation | - | - | test_sig_irrelevant_person_excluded |
| 多栏替代组 | 空栏+或栏 | AlternativeSignerGroup CONFIRMED 引用多 slot | 空栏 PRESENT_EMPTY 证据 | group key 由成员 slot 集合 | test_sig_alternative_group_multi_slot |
| 并列表格按主体拆块 | 两个 SIGNATURE_BLOCK | 2 个独立块, 各自 BOUND party_key | 逐块证据 | 键互异 | test_sig_side_by_side_table_splits_by_party |
| 跨页连续块 | 同块两段引文 | 单 block, evidence_ids>=2 | 分页不产生新块 | 单 key | test_sig_cross_page_continuous_block_merged |
| 签署日期/混合状态 | SIGNING_DATE 可解析+不可解析 | SignatureDateObservation->真实 block key | IsoDate 规范化 | - | test_sig_date_normalization_and_mixed_states |
| 块外账户/联系 | BANK_*/PHONE/FAX | SignatureFieldObservation.block_key=None | document/binding/purpose/证据保留 | 每值独立 key | test_sig_outside_block_account_observation |
| 同用途多值/不同用途分离 | 多条同类候选 | 多条 observation | - | 键互不相同 | test_sig_same_purpose_multiple_values_separate_keys |
| 附件不回填主合同 | 分文档 envelope | 主合同 observations 不随附件变化 | 附件独立 coverage | 主合同键稳定 | test_sig_attachment_does_not_backfill_main |
| 重复同值合并(同一坐标) | 同人同一可定位坐标重复候选 | 单 signer | 同坐标去重 | 同键去重 | test_sig_duplicate_same_value_merges_evidence |
| 重复同值边界:不同坐标同名 | 同块同角色同名两条不同坐标引文 | 结构歧义 -> 人工确认(P1-2b) | 不得因同名静默合并 | - | test_sig_same_block_role_same_name_distinct_coordinates_needs_confirmation |
| 悬空引用(5类) | 对抗性 envelope | 整体失败或引用闭合; 禁静默删除坏对象 | - | - | test_sig_dangling_* |
| 不可定位引文(普通候选) | 未命中 quote | 引用不闭合=技术失败 ModelFormatError | 不得伪装成 coverage 降级 | - | test_sig_unlocatable_candidate_quote_fails_assembly |
| 显式可定位 source gap | SourceGapCandidate | FactIssue 引用可定位证据 | 仅此类别驱动 PARTIAL/UNAVAILABLE | issue key 用文档+类别+坐标 | test_sig_locatable_gap_partial_kinds_keeps_facts_and_locatable_issue |
| 可靠扫描无签章 | 空 envelope | SignatureFacts 全空 | COMPLETE 而非 UNAVAILABLE | - | test_sig_reliable_scan_without_signature_is_complete |
| 技术失败不得降级 coverage | invoke 抛 ModelFormatError | 请求失败向上传播 | 不得变 UNAVAILABLE | - | test_sig_technical_failure_propagates_not_coverage |
| source gap 只降本文档 | SourceGapCandidate(附件) | 主合同 COMPLETE, 附件 PARTIAL | 逐文档 coverage | - | test_sig_source_gap_downgrades_only_affected_document |
| extraction_ranges 限制模型输入 | 调用参数断言 | 每文档一次调用+窗口透传 | - | - | test_sig_extraction_ranges_restrict_model_input |
| J1 同块同角色栏位结构不可唯一解释 | 同块 2 SIGNER_NAME 同 role_text、不同证据坐标且不能证明同一栏位 | NeedsConfirmationError 停止装配 | 不产出残缺事实 | - | test_sig_same_role_slot_structure_ambiguous_needs_confirmation |
| J2 主体/用途缺关系证据 | 引文不含主体名/用途词的 party+purpose 字段 | 保留值但不得 BOUND/CONFIRMED | 引文含关系证据才可确认 | 键不含主体猜测 | test_sig_unrelated_party_purpose_keeps_value_without_confirmation |
| J3 归属冲突/自引用 | identity block_ref 与姓名归属块冲突; alternative_of_ref 指向自身 | 无残缺输出 | 技术失败 ModelFormatError | - | test_sig_conflicting_or_self_references_fail_assembly |
| J4 source_gap 跨文档/超窗口 | gap.document_key 异文档 / gap.quote 在 extraction_ranges 外 | 不得静默降级或忽略 | 技术失败 ModelFormatError | - | test_sig_source_gap_foreign_document_or_out_of_range_is_technical_failure |
| J5 可定位缺口仅部分类别 | gap 影响 SIGNING_DATE | 事实完整保留 | PARTIAL + issue 引用可定位证据 | issue key 不含 message | test_sig_locatable_gap_partial_kinds_keeps_facts_and_locatable_issue |
| J6 缺口覆盖全部适用类别 | gap affected=全部签章类别 | 无伪造事实 | UNAVAILABLE（当前误判 PARTIAL） | - | test_sig_gap_all_applicable_signature_kinds_is_unavailable |
| J7 多文档可靠空扫描 | 双文档空 envelope | 无伪造事实 | 双 COMPLETE + 域 COMPLETE | - | test_sig_reliable_empty_scan_multi_document_complete |
| J8 重复同值身份证号 | 两条引文同一号码同块 | 单 candidate 合并全部证据 | 不得因重复键崩溃 | key 不含引文文案 | test_sig_duplicate_identity_number_merges_all_evidence |
| J9 九类主投影不回填 | 主含全部九类对象+附件装配 | 主投影九类逐字段一致 | 逐文档 coverage | 全部键稳定 | test_sig_main_projection_covers_all_nine_object_kinds_without_attachment_backfill |
| Schema 层守卫(已可绿) | - | SignatureFacts/ReviewContext/DocumentCoverage 校验 | - | - | test_contract_guard_* |
| K1 同名多 canonical | SIGNATURE_BLOCK party_name 映射多个 party_key | block UNCERTAIN + 全部候选键 | 不得 setdefault 择首 | 键由坐标生成 | test_sig_duplicate_same_name_multiple_canonical_parties_uncertain |
| K2 同角色跨块反例 | 2 块各 1 同角色 SIGNER_NAME+block_ref+party; 同坐标一栏多人 | 唯一解释 -> 正常 2 slot / 1 slot | 不得把跨块唯一结构或同坐标一栏多人误判歧义 | - | test_sig_same_role_distinct_blocks_split_without_confirmation |
| K3 块主体缺引文证据 | SIGNATURE_BLOCK party_name 不在引文中 | UNBOUND + party_key=None | 不伪造关系 | 键由块坐标 | test_sig_block_party_name_without_quote_support_stays_unbound |
| K4 悬空 block_ref | SIGNER/SIGNING_DATE block_ref 指向未知 ref | 技术失败 ModelFormatError | 引用不闭合 != 人工确认 | - | test_sig_unknown_block_reference_fails_assembly |
| P1-1 未支持主体声称 | 同坐标共享引文+互斥 party_name(不在引文) | 声称非证据, 装配 1 slot 2 signer | 不得 NeedsConfirmation | 键由坐标 | test_sig_unsupported_party_claims_do_not_trigger_confirmation |
| P1-2 同块同角色异坐标 | 两条单行引文同 role 同块 | 不能证明同一栏位 -> NeedsConfirmationError; 同坐标一栏多人保留全员 | 不静默合并 | - | test_sig_same_block_role_distinct_coordinates_needs_confirmation |
| P1-3 跨块替代引用 | alternative_of_ref 指向他块 slot 成员 | ModelFormatError | 引用不闭合 | - | test_sig_cross_block_alternative_reference_fails_assembly |
| P1-4 号码引文不含姓名 | IDENTITY quote 无姓名 + signer_name 字段声称 | 不得 DIRECT; 块内唯一 -> UNIQUE_IN_BLOCK | 声称非证据 | - | test_sig_identity_quote_without_name_not_direct |
| P1-5 ref 与证据冲突 | 有效 block_ref 与已定位主体证据矛盾 | ModelFormatError | 有效 ref 仍须与证据一致 | - | test_sig_block_ref_conflicting_with_located_party_evidence_fails |
| P1-7 单类别缺口 | gap 仅影响 SIGNING_DATE | 必须 PARTIAL | 不得 UNAVAILABLE | - | test_sig_single_category_gap_never_unavailable |
| P1-8 role_text 非键 | 同坐标仅 role_text 异 | signer_slot_key 必须不变 | 键不含展示文案 (spec:238) | - | test_sig_signer_slot_key_independent_of_role_text |
| P1-2b 同块同角色同名异坐标 | 同块同角色同名两条不同坐标引文 | 不能证明同一栏位 -> NeedsConfirmationError | 不得因同名静默合并 | - | test_sig_same_block_role_same_name_distinct_coordinates_needs_confirmation |
| P1-5b 块外字段 ref 与主体证据冲突 | BANK_* block_ref 指乙方块 + 引文含甲方事实 | ModelFormatError | 引用不闭合, 禁矛盾观察 | - | test_sig_field_block_ref_conflicting_with_located_party_evidence_fails |
| P1-6b 两缺口并集覆盖全部类别 | 两条可定位 gap 各自部分类别, 并集=全部适用 | 文档 UNAVAILABLE | 不得因无单条覆盖全部而降级 PARTIAL | - | test_sig_two_locatable_gaps_union_all_kinds_is_unavailable |

装配入口契约（计划 Task 6 Step 4）：extract_signature_facts(documents,
canonical_parties, evidence, extraction_ranges) -> FactDomain[SignatureFacts]，
位于模块 app.capabilities.contract_review.two_stage.extract_signature；模型调用
经该模块的 invoke_typed_prepare_model（沿用 Task 5 导入约定，便于定点 patch）。
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.capabilities.contract_review.two_stage.evidence import EvidenceRegistry
from app.capabilities.contract_review.two_stage.extract_header_parties import PreparedDocument
from app.capabilities.contract_review.two_stage.keys import stable_key
from app.capabilities.contract_review.two_stage.prepare_model import (
    PrepareModelEnvelope,
    SignatureCandidate,
)
from app.capabilities.contract_review.two_stage.schemas import (
    CanonicalParty,
    DocumentCoverage,
    ObservedField,
    ObservedValue,
    ReviewContext,
    SignatureBlock,
    SignatureDateObservation,
    SignatureFacts,
    SignerCandidate,
    SignerSlot,
)
from tests.two_stage.factories import valid_context_payload

SIGNATURE_MODULE = "app.capabilities.contract_review.two_stage.extract_signature"
RED_REASON = "Task 6 签章装配能力尚未实现（RED：预期失败，非 fixture/导入错误）"

MAIN_MD = (
    "甲方（盖章）：甲乙科技有限公司\n"
    "签章人：张三\n"
    "签章人：李四\n"
    "盖章旁签字：张三\n"
    "身份证号：11010119900307011X\n"
    "身份证号：31010119880202003Y\n"
    "张三身份证号：44010119900505007Z\n"
    "签署日期：2026年8月20日\n"
    "签署日期：不详\n"
    "---分页符---\n"
    "甲方（盖章）续页：骑缝章处\n"
    "乙方（盖章）：丙丁工程有限公司\n"
    "乙方签字栏：王五\n"
    "见证人：钱六\n"
    "（签字栏空白）\n"
    "或授权代表：赵六\n"
    "收款开户行：某某银行滨江支行\n"
    "收款账号：6222020200112233445\n"
    "备用收款账号：6222020200198765432\n"
    "联系电话：010-12345678\n"
    "传真号码：010-87654321\n"
    "签章表：甲栏 甲乙科技有限公司\n"
    "签章表：乙栏 丙丁工程有限公司\n"
    "甲方合作方：戊己服务有限公司\n"
    "签章人（联合）：周八\n"
    "签章人（联合）：吴九\n"
    "打款账号：6217000000012345678\n"
    "甲乙科技有限公司收款账号：6217000000098765432，用于本合同结算\n"
    "身份证复印件：11010119900307011X\n"
)

ATTACH_MD = (
    "附件签章：戊己服务有限公司\n"
    "附件签字：孙七\n"
    "附件身份证号：44030119770707005W\n"
)


def _assembler():
    import importlib

    try:
        return importlib.import_module(SIGNATURE_MODULE)
    except ImportError:
        pytest.fail(RED_REASON + "：模块 " + SIGNATURE_MODULE + " 不存在", pytrace=False)


def _extract_fn(module):
    fn = getattr(module, "extract_signature_facts", None)
    if not callable(fn):
        pytest.fail(RED_REASON + "：" + SIGNATURE_MODULE + ".extract_signature_facts 缺失", pytrace=False)
    return fn


def _setup():
    registry = EvidenceRegistry({"main": MAIN_MD, "attach1": ATTACH_MD})

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
        _party("甲乙科技有限公司", "甲方（盖章）：甲乙科技有限公司"),
        _party("丙丁工程有限公司", "乙方（盖章）：丙丁工程有限公司"),
    ]
    docs = {
        "main": PreparedDocument(document_key="main", markdown=MAIN_MD),
        "attach1": PreparedDocument(document_key="attach1", markdown=ATTACH_MD),
    }
    return registry, canonical, docs


KEY_JIA = stable_key("party", {"declared_name": "甲乙科技有限公司"})
KEY_YI = stable_key("party", {"declared_name": "丙丁工程有限公司"})


def _sig_candidate(
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


def _sig_env(
    candidates: list[dict[str, Any]],
    gaps: list[dict[str, Any]] | None = None,
) -> PrepareModelEnvelope:
    return PrepareModelEnvelope[list[SignatureCandidate]].model_validate(
        {"candidates": candidates, "source_gaps": gaps or []}
    )


def _assemble(
    envelopes_by_doc: dict[str, PrepareModelEnvelope],
    *,
    doc_keys: list[str] | None = None,
    extraction_ranges: dict[str, list[tuple[int, int]]] | None = None,
    side_effect: Exception | None = None,
    calls: list[tuple[str, dict[str, Any]]] | None = None,
    registry_box: list | None = None,
):
    module = _assembler()
    fn = _extract_fn(module)
    if not hasattr(module, "invoke_typed_prepare_model"):
        pytest.fail(
            RED_REASON + "：" + SIGNATURE_MODULE + " 未按约定暴露 invoke_typed_prepare_model",
            pytrace=False,
        )
    registry, canonical, docs = _setup()
    if registry_box is not None:
        registry_box[:] = [registry, canonical]
    selected = doc_keys or list(envelopes_by_doc.keys())

    def _fake(prompt_name: str, **kwargs: Any):
        if calls is not None:
            calls.append((prompt_name, dict(kwargs)))
        if side_effect is not None:
            raise side_effect
        markdown = kwargs.get("markdown")
        for key in selected:
            if docs[key].markdown == markdown:
                return envelopes_by_doc[key]
        raise AssertionError("模型收到未知文档输入: " + str(prompt_name))

    with patch.object(module, "invoke_typed_prepare_model", side_effect=_fake):
        return fn(
            [docs[key] for key in selected],
            canonical,
            registry,
            extraction_ranges,
        )


def _assert_reference_closure(data, registry, canonical) -> None:
    """装配产物必须整体满足引用闭合；不得静默输出悬空引用。"""
    valid_evidence = {item.evidence_id for item in registry.items()}
    party_keys = {p.party_key for p in canonical}
    block_keys = {b.signature_block_key for b in data.signature_blocks}
    slot_keys = {s.signer_slot_key for s in data.signer_slots}
    signer_keys = {s.signer_key for s in data.signer_candidates}
    id_keys = {i.identity_number_key for i in data.identity_number_candidates}

    def _ev(ids):
        assert set(ids) <= valid_evidence, "装配输出引用了不存在的公开 evidence_id"

    for b in data.signature_blocks:
        _ev(b.evidence_ids)
        assert b.party_key is None or b.party_key in party_keys, "signature_block 悬空 party_key"
        assert set(b.candidate_party_keys) <= party_keys
    for s in data.signer_slots:
        assert s.signature_block_key in block_keys, "signer_slot 悬空引用 signature_block_key"
        _ev(s.evidence_ids)
        assert set(s.signer_keys) <= signer_keys, "signer_slot 悬空引用 signer_key"
        assert set(s.identity_number_keys) <= id_keys, "signer_slot 悬空引用 identity_number_key"
    for g in data.alternative_signer_groups:
        assert set(g.signer_slot_keys) <= slot_keys, "group 悬空引用 signer_slot_key"
        _ev(g.evidence_ids)
    for s in data.signer_candidates:
        assert s.signer_slot_key in slot_keys, "signer 悬空引用 signer_slot_key"
        _ev(s.evidence_ids)
    for i in data.identity_number_candidates:
        assert i.signer_slot_key is None or i.signer_slot_key in slot_keys
        _ev(i.evidence_ids)
    for r in data.person_id_relations:
        assert r.signer_key in signer_keys, "relation 悬空引用 signer_key"
        assert r.identity_number_key in id_keys, "relation 悬空引用 identity_number_key"
        _ev(r.evidence_ids)
    for d in data.signing_date_observations:
        assert d.signature_block_key in block_keys, "signing_date 悬空引用 signature_block_key"
        assert d.party_key is None or d.party_key in party_keys
    for f in [*data.account_observations, *data.contact_observations]:
        assert f.signature_block_key is None or f.signature_block_key in block_keys
        if f.field.observations:
            _ev(f.field.observations[0].evidence_ids)
        assert f.party_key is None or f.party_key in party_keys
        assert f.document_key in {"main", "attach1"}


def _assemble_or_closure_check(envelopes: dict[str, PrepareModelEnvelope]) -> None:
    """对抗输入契约：装配整体失败，或产物引用闭合；不得删除坏对象后静默变绿。"""
    from app.core.errors import ModelFormatError

    box: list = []
    try:
        domain = _assemble(envelopes, doc_keys=["main"], registry_box=box)
    except (ModelFormatError, ValueError):
        return
    registry, canonical = box
    _assert_reference_closure(domain.data, registry, canonical)

# ---------------------------------------------------------------------------
# A. 块/栏位结构
# ---------------------------------------------------------------------------


def _base_block_candidates() -> list[dict[str, Any]]:
    return [
        _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
        # 同一已定位证据坐标（一条连续引文）列出两名签署人：
        # 正式契约下这是"一栏多人"的可证明形态；不同坐标的同角色候选属于歧义（见 L 节）。
        _sig_candidate("c2", "SIGNER_NAME", "签章人：张三\n签章人：李四", role_text="法定代表人或授权代表", signer_name="张三"),
        _sig_candidate("c3", "SIGNER_NAME", "签章人：张三\n签章人：李四", role_text="法定代表人或授权代表", signer_name="李四"),
    ]


def test_sig_real_block_multiple_slots():
    """真实块：1 个 SignatureBlock、slot 引用真实 block key、主体 BOUND、公司名装配。"""
    domain = _assemble({"main": _sig_env(_base_block_candidates())})
    data = domain.data
    assert len(data.signature_blocks) == 1
    block = data.signature_blocks[0]
    assert block.document_key == "main"
    assert block.party_binding_state == "BOUND"
    assert block.party_key == KEY_JIA
    assert block.local_company_name.presence == "PRESENT_VALUE"
    assert block.local_company_name.observations[0].normalized_value == "甲乙科技有限公司"
    slots = [s for s in data.signer_slots if s.signature_block_key == block.signature_block_key]
    assert slots, "SIGNER_NAME 候选必须装配为引用真实块的 slot"
    assert all(
        s.signature_block_key in {b.signature_block_key for b in data.signature_blocks}
        for s in data.signer_slots
    )
    assert domain.state == "COMPLETE"
    assert [c.document_key for c in domain.coverage] == ["main"]


def test_sig_side_by_side_table_splits_by_party():
    """并列表格按主体拆块：两主体各成独立块，不得合并为一个块。"""
    domain = _assemble(
        {
            "main": _sig_env(
                [
                    _sig_candidate("c1", "SIGNATURE_BLOCK", "签章表：甲栏 甲乙科技有限公司", party_name="甲乙科技有限公司"),
                    _sig_candidate("c2", "SIGNATURE_BLOCK", "签章表：乙栏 丙丁工程有限公司", party_name="丙丁工程有限公司"),
                ]
            )
        }
    )
    blocks = domain.data.signature_blocks
    assert len(blocks) == 2
    assert len({b.signature_block_key for b in blocks}) == 2
    assert {b.party_key for b in blocks} == {KEY_JIA, KEY_YI}
    assert all(b.party_binding_state == "BOUND" for b in blocks)


def test_sig_cross_page_continuous_block_merged():
    """跨页连续块：同一主体续页引文并入同一块并保留多证据，分页不产生新块。"""
    domain = _assemble(
        {
            "main": _sig_env(
                [
                    _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                    _sig_candidate(
                        "c2",
                        "SIGNATURE_BLOCK",
                        "甲方（盖章）续页：骑缝章处",
                        party_name="甲乙科技有限公司",
                        continues_ref="c1",
                    ),
                ]
            )
        }
    )
    blocks = domain.data.signature_blocks
    assert len(blocks) == 1, "同一签章块跨页续写不得拆成两个块"
    assert len(blocks[0].evidence_ids) >= 2


# ---------------------------------------------------------------------------
# B. 人员与身份关系
# ---------------------------------------------------------------------------


def test_sig_multiple_names_in_one_slot_all_kept():
    """一栏多人：同栏位全部姓名进入 signer_keys，不得静默选取其一。"""
    domain = _assemble({"main": _sig_env(_base_block_candidates())})
    data = domain.data
    assert len(data.signer_candidates) == 2
    assert {s.raw_name for s in data.signer_candidates} == {"张三", "李四"}
    slot = next(s for s in data.signer_slots if s.role_text == "法定代表人或授权代表")
    assert set(slot.signer_keys) == {s.signer_key for s in data.signer_candidates}


def test_sig_multiple_persons_multiple_ids_uncertain():
    """多人多号不清：全部保留，关系一律 UNCERTAIN，禁止顺序/距离/预设配对。"""
    domain = _assemble(
        {
            "main": _sig_env(
                _base_block_candidates()
                + [
                    _sig_candidate("c4", "IDENTITY_NUMBER", "身份证号：11010119900307011X", identity_number="11010119900307011X"),
                    _sig_candidate("c5", "IDENTITY_NUMBER", "身份证号：31010119880202003Y", identity_number="31010119880202003Y"),
                ]
            )
        }
    )
    data = domain.data
    assert len(data.identity_number_candidates) == 2
    assert data.person_id_relations, "多人多号不清仍须保留候选间 UNCERTAIN 关系"
    assert all(r.association_state == "UNCERTAIN" for r in data.person_id_relations)
    assert {r.signer_key for r in data.person_id_relations} == {s.signer_key for s in data.signer_candidates}


def test_sig_direct_identity_association():
    """直接关联：显式"张三身份证号：Y"装配为 DIRECT 关系。"""
    domain = _assemble(
        {
            "main": _sig_env(
                [
                    _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                    _sig_candidate("c2", "SIGNER_NAME", "签章人：张三", role_text="授权代表", signer_name="张三"),
                    _sig_candidate(
                        "c3",
                        "IDENTITY_NUMBER",
                        "张三身份证号：44010119900505007Z",
                        signer_name="张三",
                        identity_number="44010119900505007Z",
                    ),
                ]
            )
        }
    )
    relations = domain.data.person_id_relations
    assert len(relations) == 1
    assert relations[0].association_state == "DIRECT"


def test_sig_unique_in_block_association():
    """块内唯一：块内仅一人一号且无显式绑定时装配 UNIQUE_IN_BLOCK。"""
    domain = _assemble(
        {
            "main": _sig_env(
                [
                    _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                    _sig_candidate("c2", "SIGNER_NAME", "乙方签字栏：王五", role_text="授权代表", signer_name="王五"),
                    _sig_candidate("c3", "IDENTITY_NUMBER", "身份证号：11010119900307011X", identity_number="11010119900307011X"),
                ]
            )
        }
    )
    relations = domain.data.person_id_relations
    assert len(relations) == 1
    assert relations[0].association_state == "UNIQUE_IN_BLOCK"


def test_sig_irrelevant_person_excluded():
    """无关人员：见证人栏装配为 IRRELEVANT_PERSON，不生成身份关系。"""
    domain = _assemble(
        {
            "main": _sig_env(
                [
                    _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                    _sig_candidate("c2", "SIGNER_NAME", "见证人：钱六", role_text="见证人", signer_name="钱六"),
                ]
            )
        }
    )
    data = domain.data
    slot = next(s for s in data.signer_slots if s.role_text == "见证人")
    assert slot.role_state == "IRRELEVANT_PERSON"
    witness_keys = {s.signer_key for s in data.signer_candidates if s.raw_name == "钱六"}
    assert witness_keys, "无关人员姓名仍作为事实保留"
    assert not [r for r in data.person_id_relations if r.signer_key in witness_keys]


def test_sig_alternative_group_multi_slot():
    """"或"连接的两栏归入同一 AlternativeSignerGroup，空栏 PRESENT_EMPTY 保留。"""
    domain = _assemble(
        {
            "main": _sig_env(
                [
                    _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                    _sig_candidate("c2", "SIGNER_NAME", "（签字栏空白）", role_text="法定代表人"),
                    _sig_candidate(
                        "c3",
                        "SIGNER_NAME",
                        "或授权代表：赵六",
                        role_text="授权代表",
                        signer_name="赵六",
                        alternative_of_ref="c2",
                    ),
                ]
            )
        }
    )
    data = domain.data
    groups = data.alternative_signer_groups
    assert len(groups) == 1
    assert groups[0].relation_state == "CONFIRMED"
    slot_keys = {s.signer_slot_key for s in data.signer_slots}
    assert set(groups[0].signer_slot_keys) <= slot_keys
    assert len(groups[0].signer_slot_keys) == 2
    empty_slot = next(s for s in data.signer_slots if s.role_text == "法定代表人")
    assert empty_slot.presence == "PRESENT_EMPTY"


def test_sig_duplicate_same_value_merges_evidence():
    """重复同值(同一可定位坐标去重)：同一签章块、同一角色、同一姓名由同一处
    引文重复给出，装配为一个 signer（同稳定键）；不得因候选重复而重复生成 signer。

    边界：不同可定位坐标的同名候选不属于本用例；该保守装配边界（同块同角色现有
    可靠证据无法唯一证明是一栏一人多处提及还是两个独立栏位）由
    test_sig_same_block_role_same_name_distinct_coordinates_needs_confirmation
    负责人工确认（NeedsConfirmationError），不得因同名静默合并。"""
    domain = _assemble(
        {
            "main": _sig_env(
                [
                    _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                    _sig_candidate("c2", "SIGNER_NAME", "签章人：张三", role_text="授权代表", signer_name="张三"),
                    _sig_candidate("c3", "SIGNER_NAME", "签章人：张三", role_text="授权代表", signer_name="张三"),
                ]
            )
        }
    )
    signers = domain.data.signer_candidates
    assert len(signers) == 1, "同一可定位坐标的重复候选不得重复生成 signer"
    assert signers[0].raw_name == "张三"
    assert signers[0].evidence_ids


# ---------------------------------------------------------------------------
# C. 日期与块外字段
# ---------------------------------------------------------------------------


def test_sig_date_normalization_and_mixed_states():
    """日期：引用真实块 key；可解析归一化为 IsoDate，不可解析保留 raw 并 UNCERTAIN。"""
    domain = _assemble(
        {
            "main": _sig_env(
                [
                    _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                    _sig_candidate("c2", "SIGNING_DATE", "签署日期：2026年8月20日", signing_date="2026年8月20日"),
                    _sig_candidate("c3", "SIGNING_DATE", "签署日期：不详", signing_date="不详"),
                ]
            )
        }
    )
    data = domain.data
    assert len(data.signature_blocks) == 1
    dates = data.signing_date_observations
    assert len(dates) == 2
    assert all(d.signature_block_key == data.signature_blocks[0].signature_block_key for d in dates)
    valid = next(d for d in dates if d.field.presence == "PRESENT_VALUE" and d.field.normalization_state == "VALID")
    assert valid.field.observations[0].normalized_value == "2026-08-20"
    other = next(d for d in dates if d is not valid)
    assert other.field.normalization_state == "UNCERTAIN"
    assert all(obs.normalized_value is None for obs in other.field.observations)


def test_sig_outside_block_account_observation():
    """块外账户：不伪造 signature_block_key，但保留 document、绑定状态、用途与证据。"""
    domain = _assemble(
        {
            "main": _sig_env(
                [
                    _sig_candidate("c1", "BANK_NAME", "收款开户行：某某银行滨江支行", bank_name="某某银行滨江支行"),
                    _sig_candidate("c2", "BANK_ACCOUNT", "收款账号：6222020200112233445", bank_account="6222020200112233445"),
                    _sig_candidate("c3", "PHONE", "联系电话：010-12345678", phone="010-12345678"),
                ]
            )
        }
    )
    data = domain.data
    assert data.signature_blocks == [], "块外观察不得虚构签章块"
    accounts = data.account_observations
    assert {a.field_kind for a in accounts} == {"BANK_NAME", "BANK_ACCOUNT"}
    assert all(a.signature_block_key is None for a in accounts)
    contacts = data.contact_observations
    assert [c.field_kind for c in contacts] == ["PHONE"]
    for obs in [*accounts, *contacts]:
        assert obs.document_key == "main"
        assert obs.party_binding_state in {"BOUND", "UNBOUND", "UNCERTAIN"}
        if obs.party_key is not None:
            assert obs.party_binding_state == "BOUND"
        assert obs.field.observations[0].evidence_ids
        assert obs.purpose_state in {"CONFIRMED", "UNCERTAIN", "NOT_APPLICABLE"}


def test_sig_same_purpose_multiple_values_separate_keys():
    """同用途多值：两个收款账号各自独立 observation 与稳定键；不同用途不混入。"""
    domain = _assemble(
        {
            "main": _sig_env(
                [
                    _sig_candidate("c1", "BANK_ACCOUNT", "收款账号：6222020200112233445", bank_account="6222020200112233445"),
                    _sig_candidate("c2", "BANK_ACCOUNT", "备用收款账号：6222020200198765432", bank_account="6222020200198765432"),
                    _sig_candidate("c3", "FAX", "传真号码：010-87654321", fax="010-87654321"),
                ]
            )
        }
    )
    accounts = domain.data.account_observations
    assert len(accounts) == 2
    assert len({a.field_observation_key for a in accounts}) == 2
    assert {a.field_kind for a in accounts} == {"BANK_ACCOUNT"}
    assert [c.field_kind for c in domain.data.contact_observations] == ["FAX"]


# ---------------------------------------------------------------------------
# D. 跨文档边界
# ---------------------------------------------------------------------------


def test_sig_attachment_does_not_backfill_main():
    """附件不回填：主合同装配结果不因附件调用改变；coverage 覆盖 main+全部附件。"""
    main_env = _sig_env(_base_block_candidates())
    attach_env = _sig_env(
        [
            _sig_candidate(
                "a1",
                "SIGNATURE_BLOCK",
                "附件签章：戊己服务有限公司",
                document_key="attach1",
                party_name="戊己服务有限公司",
            ),
            _sig_candidate("a2", "SIGNER_NAME", "附件签字：孙七", document_key="attach1", role_text="经办", signer_name="孙七"),
        ],
    )
    only_main = _assemble({"main": main_env}, doc_keys=["main"])
    both = _assemble({"main": main_env, "attach1": attach_env}, doc_keys=["main", "attach1"])

    def _main_signature(domain):
        data = domain.data
        main_blocks = {
            b.signature_block_key
            for b in data.signature_blocks
            if b.document_key == "main"
        }
        main_slots = {
            s.signer_slot_key
            for s in data.signer_slots
            if s.signature_block_key in main_blocks
        }
        return (
            sorted(main_blocks),
            sorted(main_slots),
            sorted(
                p.signer_key
                for p in data.signer_candidates
                if p.signer_slot_key in main_slots
            ),
        )

    assert _main_signature(only_main) == _main_signature(both)
    assert {c.document_key for c in both.coverage} == {"main", "attach1"}
    attach_blocks = [b for b in both.data.signature_blocks if b.document_key == "attach1"]
    assert len(attach_blocks) == 1
    assert attach_blocks[0].party_key is None or attach_blocks[0].party_key not in {KEY_JIA, KEY_YI}
    assert all(s.signer_slot_key not in {x.signer_slot_key for x in only_main.data.signer_slots} for s in both.data.signer_slots if s.role_text == "经办")


# ---------------------------------------------------------------------------
# E. 悬空引用 / 不可定位 / coverage 语义
# ---------------------------------------------------------------------------


def test_sig_dangling_block_reference_fails_assembly():
    """悬空 signature_block_key：日期候选无对应块时整体失败或引用闭合。"""
    _assemble_or_closure_check(
        {"main": _sig_env([_sig_candidate("c1", "SIGNING_DATE", "签署日期：2026年8月20日", signing_date="2026年8月20日")])}
    )


def test_sig_dangling_slot_owner_reference_fails_assembly():
    """悬空 signer_slot_key/identity：身份号候选装配后必须满足 slot 归属闭合。"""
    _assemble_or_closure_check(
        {
            "main": _sig_env(
                [
                    _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                    _sig_candidate("c2", "IDENTITY_NUMBER", "身份证号：11010119900307011X", identity_number="11010119900307011X"),
                ]
            )
        }
    )


def test_sig_dangling_signer_and_relation_keys_fail_assembly():
    """悬空 signer_key/identity_number_key：关系装配只允许引用同次输出内已装配实体。"""
    _assemble_or_closure_check(
        {
            "main": _sig_env(
                _base_block_candidates()
                + [
                    _sig_candidate("c4", "IDENTITY_NUMBER", "身份证号：31010119880202003Y", identity_number="31010119880202003Y"),
                ]
            )
        }
    )


def test_sig_dangling_party_reference_fails_assembly():
    """悬空 party_key：块主体名不在 canonical 集合时只能 UNBOUND/UNCERTAIN，不得虚构键。"""
    from app.core.errors import ModelFormatError

    box: list = []
    try:
        domain = _assemble(
            {
                "main": _sig_env(
                    [
                        _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方合作方：戊己服务有限公司", party_name="戊己服务有限公司"),
                        _sig_candidate("c2", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                    ]
                )
            },
            doc_keys=["main"],
            registry_box=box,
        )
    except (ModelFormatError, ValueError):
        return
    registry, canonical = box
    _assert_reference_closure(domain.data, registry, canonical)
    unknown = [b for b in domain.data.signature_blocks if b.party_key is not None and b.local_company_name.observations and b.local_company_name.observations[0].normalized_value == "戊己服务有限公司"]
    assert not unknown, "未知主体不得被绑定为 BOUND party_key"
    unbound = [b for b in domain.data.signature_blocks if b.party_binding_state != "BOUND"]
    assert unbound, "未知主体的块必须以 UNBOUND/UNCERTAIN 表达"


def test_sig_unlocatable_candidate_quote_fails_assembly():
    """#1 (重铸) 普通候选引文不可定位：引用不闭合=技术失败 ModelFormatError。
    旧断言废弃理由：它固化了"不可定位候选→跳过该事实+coverage PARTIAL"，
    而正式契约（signature spec 引用不闭合条款 / DEC-LTC-20260909-001 / design §6 保守装配）
    规定 PARTIAL/UNAVAILABLE 只由显式 source_gap 驱动；候选 quote 未命中说明模型输出
    自身不可信，必须整体失败，不得静默丢弃事实并伪装成 coverage 降级。
    可定位缺口驱动 PARTIAL 的路径由 J5/L7 显式 source_gap 测试覆盖。"""
    from app.core.errors import ModelFormatError

    with pytest.raises(ModelFormatError):
        _assemble(
            {
                "main": _sig_env(
                    _base_block_candidates()
                    + [_sig_candidate("c9", "SIGNER_NAME", "文档中不存在的签章引文XYZ", role_text="授权代表", signer_name="不明")]
                )
            },
            doc_keys=["main"],
        )


def test_sig_reliable_scan_without_signature_is_complete():
    """0 形态：可靠扫描无签章 -> COMPLETE 空事实，不得伪造事实或 UNAVAILABLE。"""
    domain = _assemble({"main": _sig_env([])})
    assert domain.state == "COMPLETE"
    assert domain.coverage[0].state == "COMPLETE"
    assert domain.coverage[0].fact_issue_keys == []
    assert domain.coverage[0].affected_fact_kinds == []
    assert domain.data.signature_blocks == []
    assert domain.data.signer_slots == []


def test_sig_technical_failure_propagates_not_coverage():
    """技术失败=请求失败：格式错误必须向上传播，不得降级为 UNAVAILABLE coverage。"""
    from app.core.errors import ModelFormatError

    with pytest.raises(ModelFormatError):
        _assemble({"main": _sig_env([])}, side_effect=ModelFormatError("prepare_signature_document 输出格式非法"))


def test_sig_source_gap_downgrades_only_affected_document():
    """source gap：附件缺口只降附件 coverage；主合同保持 COMPLETE。"""
    main_env = _sig_env(_base_block_candidates())
    attach_env = _sig_env(
        [],
        gaps=[
            {
                "affected_fact_kinds": ["SIGNATURE_BLOCK"],
                "message": "附件签章页缺失",
                "quote": "附件签章：戊己服务有限公司",
                "document_key": "attach1",
            }
        ],
    )
    domain = _assemble({"main": main_env, "attach1": attach_env}, doc_keys=["main", "attach1"])
    by_doc = {c.document_key: c for c in domain.coverage}
    assert by_doc["main"].state == "COMPLETE"
    assert by_doc["attach1"].state == "PARTIAL"
    assert by_doc["attach1"].fact_issue_keys
    assert domain.state == "PARTIAL"


# ---------------------------------------------------------------------------
# F. 稳定键
# ---------------------------------------------------------------------------


def test_sig_candidate_reorder_does_not_change_keys():
    """候选数组乱序不影响装配稳定键与输出集合。"""
    forward = _base_block_candidates()
    shuffled = [forward[2], forward[0], forward[1]]
    d1 = _assemble({"main": _sig_env(forward)})
    d2 = _assemble({"main": _sig_env(shuffled)})
    assert sorted(b.signature_block_key for b in d1.data.signature_blocks) == sorted(
        b.signature_block_key for b in d2.data.signature_blocks
    )
    assert sorted(s.signer_key for s in d1.data.signer_candidates) == sorted(
        s.signer_key for s in d2.data.signer_candidates
    )
    assert sorted(g.signer_slot_key for g in d1.data.signer_slots) == sorted(
        g.signer_slot_key for g in d2.data.signer_slots
    )


def test_sig_keys_independent_of_candidate_ref():
    """稳定键不得嵌入 candidate_ref/展示 id：renumber 候选后键不变。"""
    forward = _base_block_candidates()
    renamed = [dict(c, candidate_ref="z" + str(9 + i)) for i, c in enumerate(forward)]
    d1 = _assemble({"main": _sig_env(forward)})
    d2 = _assemble({"main": _sig_env(renamed)})
    assert sorted(b.signature_block_key for b in d1.data.signature_blocks) == sorted(
        b.signature_block_key for b in d2.data.signature_blocks
    )
    assert sorted(s.signer_key for s in d1.data.signer_candidates) == sorted(
        s.signer_key for s in d2.data.signer_candidates
    )


# ---------------------------------------------------------------------------
# G. 模型调用参数（extraction_ranges 限定输入）
# ---------------------------------------------------------------------------


def test_sig_extraction_ranges_restrict_model_input():
    """extraction_ranges 必须真实传入模型调用：逐文档调用并携带限定窗口。"""
    calls: list[tuple[str, dict[str, Any]]] = []
    ranges = {"main": [(0, MAIN_MD.index("---分页符---"))]}
    _assemble(
        {"main": _sig_env(_base_block_candidates())},
        doc_keys=["main"],
        extraction_ranges=ranges,
        calls=calls,
    )
    assert len(calls) == 1
    prompt_name, kwargs = calls[0]
    assert prompt_name == "prepare_signature_document"
    assert kwargs.get("markdown") == MAIN_MD
    dumped = json.dumps({k: str(v) for k, v in kwargs.items()}, ensure_ascii=False)
    assert "start" in dumped and "end" in dumped, "extraction_ranges 未透传给模型调用参数"


# ---------------------------------------------------------------------------
# H. 契约守卫（Schema 层已可绿：证明 RED 主体来自装配缺失而非基础设施损坏）
# ---------------------------------------------------------------------------

_EV = "evidence:main:0-10"


def _slot(block_key: str, slot_key: str, signer_keys: list[str]) -> SignerSlot:
    return SignerSlot(
        signer_slot_key=slot_key,
        signature_block_key=block_key,
        role_text="授权代表",
        role_state="ELIGIBLE_SIGNER",
        presence="PRESENT_VALUE",
        signer_keys=signer_keys,
        evidence_ids=[_EV],
    )


def _block(block_key: str) -> SignatureBlock:
    return SignatureBlock(
        signature_block_key=block_key,
        document_key="main",
        party_binding_state="UNBOUND",
        local_company_name=ObservedField(
            presence="ABSENT",
            normalization_state="NOT_APPLICABLE",
            observations=[],
        ),
        evidence_ids=[_EV],
    )


def _signer(signer_key: str, slot_key: str) -> SignerCandidate:
    return SignerCandidate(
        signer_key=signer_key,
        signer_slot_key=slot_key,
        raw_name="张三",
        evidence_ids=[_EV],
    )


def _date_obs(block_key: str) -> SignatureDateObservation:
    return SignatureDateObservation(
        signature_date_key="signature_date:1",
        signature_block_key=block_key,
        field=ObservedField(
            presence="PRESENT_VALUE",
            normalization_state="VALID",
            observations=[ObservedValue(raw_text="2026-08-20", normalized_value="2026-08-20", evidence_ids=[_EV])],
        ),
    )


def test_contract_guard_signature_facts_rejects_dangling_refs():
    """SignatureFacts 已能在 Schema 层拒绝 5 类悬空/跨 slot 引用。"""
    with pytest.raises(ValidationError):
        SignatureFacts(signature_blocks=[], signer_slots=[_slot("signature_block:missing", "signer_slot:1", [])])
    with pytest.raises(ValidationError):
        SignatureFacts(
            signature_blocks=[_block("signature_block:aaa")],
            signer_slots=[_slot("signature_block:aaa", "signer_slot:1", ["signer:orphan"])],
        )
    with pytest.raises(ValidationError):
        SignatureFacts(
            signature_blocks=[_block("signature_block:aaa")],
            signer_slots=[_slot("signature_block:aaa", "signer_slot:1", [])],
            signer_candidates=[_signer("signer:1", "signer_slot:missing")],
        )
    with pytest.raises(ValidationError):
        SignatureFacts(
            signature_blocks=[_block("signature_block:aaa")],
            signer_slots=[_slot("signature_block:aaa", "signer_slot:1", [])],
            signing_date_observations=[_date_obs("signature_block:missing")],
        )
    with pytest.raises(ValidationError):
        SignatureFacts(
            signature_blocks=[_block("signature_block:aaa")],
            signer_slots=[
                _slot("signature_block:aaa", "signer_slot:1", []),
                _slot("signature_block:aaa", "signer_slot:2", ["signer:1"]),
            ],
            signer_candidates=[_signer("signer:1", "signer_slot:1")],
        )


def test_contract_guard_review_context_rejects_unknown_signature_party():
    payload = valid_context_payload()
    payload["shared_facts"]["signature"]["data"] = {
        "signature_blocks": [
            {
                "signature_block_key": "signature_block:x",
                "document_key": "main",
                "party_binding_state": "BOUND",
                "party_key": "party:does-not-exist",
                "candidate_party_keys": [],
                "local_company_name": {
                    "presence": "ABSENT",
                    "normalization_state": "NOT_APPLICABLE",
                    "observations": [],
                },
                "evidence_ids": ["evidence:main:header-name"],
            }
        ],
        "signer_slots": [],
        "alternative_signer_groups": [],
        "signer_candidates": [],
        "identity_number_candidates": [],
        "person_id_relations": [],
        "signing_date_observations": [],
        "account_observations": [],
        "contact_observations": [],
    }
    with pytest.raises(ValidationError):
        ReviewContext.model_validate(payload)


def test_contract_guard_document_coverage_state_constraints():
    with pytest.raises(ValidationError):
        DocumentCoverage(document_key="main", state="COMPLETE", affected_fact_kinds=[], fact_issue_keys=["fact_issue:x"])
    with pytest.raises(ValidationError):
        DocumentCoverage(document_key="main", state="PARTIAL", affected_fact_kinds=["SIGNATURE_BLOCK"], fact_issue_keys=[])


# ---------------------------------------------------------------------------
# I. Round-2 复核阻断项 RED（#2-#11）
# ---------------------------------------------------------------------------


def _main_projection(domain) -> dict[str, list[str]]:
    """完整 main 文档投影：全部九类装配对象（含值），供跨运行/跨文档比较。"""
    data = domain.data.model_dump(mode="json")
    main_blocks = {
        b["signature_block_key"]
        for b in data["signature_blocks"]
        if b["document_key"] == "main"
    }
    main_slots = {
        s["signer_slot_key"]
        for s in data["signer_slots"]
        if s["signature_block_key"] in main_blocks
    }
    main_signers = {
        s["signer_key"]
        for s in data["signer_candidates"]
        if s["signer_slot_key"] in main_slots
    }
    main_relations = [
        r for r in data["person_id_relations"] if r["signer_key"] in main_signers
    ]
    main_id_keys = {
        i["identity_number_key"]
        for i in data["identity_number_candidates"]
        if i["signer_slot_key"] in main_slots
    } | {r["identity_number_key"] for r in main_relations}

    def dump(items: list[dict[str, Any]]) -> list[str]:
        return sorted(
            json.dumps(item, sort_keys=True, ensure_ascii=False) for item in items
        )

    return {
        "blocks": dump([b for b in data["signature_blocks"] if b["document_key"] == "main"]),
        "slots": dump([s for s in data["signer_slots"] if s["signature_block_key"] in main_blocks]),
        "signers": dump([s for s in data["signer_candidates"] if s["signer_slot_key"] in main_slots]),
        "identities": dump([i for i in data["identity_number_candidates"] if i["identity_number_key"] in main_id_keys]),
        "relations": dump(main_relations),
        "groups": dump(
            [
                g
                for g in data["alternative_signer_groups"]
                if g["signer_slot_keys"] and all(k in main_slots for k in g["signer_slot_keys"])
            ]
        ),
        "dates": dump([d for d in data["signing_date_observations"] if d["signature_block_key"] in main_blocks]),
        "accounts": dump([a for a in data["account_observations"] if a["document_key"] == "main"]),
        "contacts": dump([c for c in data["contact_observations"] if c["document_key"] == "main"]),
    }


def test_sig_same_party_independent_blocks_not_merged():
    """#2 同主体两个独立签章块（无 continues_ref）不得按主体名合并。"""
    domain = _assemble(
        {
            "main": _sig_env(
                [
                    _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                    _sig_candidate("c2", "SIGNATURE_BLOCK", "签章表：甲栏 甲乙科技有限公司", party_name="甲乙科技有限公司"),
                ]
            )
        }
    )
    blocks = domain.data.signature_blocks
    assert len(blocks) == 2, "同主体独立签章块不得合并"
    assert len({b.signature_block_key for b in blocks}) == 2


def test_sig_two_persons_one_number_uncertain_not_failure():
    """#3 两人一号：保留全部事实并输出 UNCERTAIN 叉乘关系，不得按数量不等整体失败。"""
    domain = _assemble(
        {
            "main": _sig_env(
                _base_block_candidates()
                + [_sig_candidate("c4", "IDENTITY_NUMBER", "身份证号：11010119900307011X", identity_number="11010119900307011X")]
            )
        }
    )
    data = domain.data
    assert len(data.identity_number_candidates) == 1
    relations = data.person_id_relations
    assert {r.signer_key for r in relations} == {s.signer_key for s in data.signer_candidates}
    assert len(relations) == 2
    assert all(r.association_state == "UNCERTAIN" for r in relations)


def test_sig_account_purpose_confirmed_keeps_party_and_text():
    """#4 明确用途账户：保留主体绑定、purpose_text 与 CONFIRMED 状态。"""
    domain = _assemble(
        {
            "main": _sig_env(
                [
                    _sig_candidate(
                        "c1",
                        "BANK_ACCOUNT",
                        "甲乙科技有限公司收款账号：6217000000098765432，用于本合同结算",
                        bank_account="6217000000098765432",
                        party_name="甲乙科技有限公司",
                        purpose_text="用于本合同结算",
                    )
                ]
            )
        }
    )
    accounts = domain.data.account_observations
    assert len(accounts) == 1
    obs = accounts[0]
    assert obs.purpose_state == "CONFIRMED"
    assert obs.purpose_text == "用于本合同结算"
    assert obs.party_binding_state == "BOUND"
    assert obs.party_key == KEY_JIA


def test_sig_document_and_candidate_order_full_projection_stable():
    """#5 documents 顺序、候选顺序、candidate_ref 变化不改变键、输出排序与完整投影。"""
    main_env_candidates = _base_block_candidates()
    attach_candidates = [
        _sig_candidate("a1", "SIGNATURE_BLOCK", "附件签章：戊己服务有限公司", document_key="attach1", party_name="戊己服务有限公司"),
        _sig_candidate("a2", "SIGNER_NAME", "附件签字：孙七", document_key="attach1", role_text="经办", signer_name="孙七"),
    ]
    forward = _assemble(
        {"main": _sig_env(main_env_candidates), "attach1": _sig_env(attach_candidates)},
        doc_keys=["main", "attach1"],
    )
    renamed_main = [dict(c, candidate_ref="q" + str(i)) for i, c in enumerate(reversed(main_env_candidates))]
    renamed_attach = [dict(c, candidate_ref="y" + str(i)) for i, c in enumerate(reversed(attach_candidates))]
    reverse = _assemble(
        {"main": _sig_env(renamed_main), "attach1": _sig_env(renamed_attach)},
        doc_keys=["attach1", "main"],
    )
    assert forward.data.model_dump(mode="json") == reverse.data.model_dump(mode="json")
    assert [c.document_key for c in forward.coverage] == [c.document_key for c in reverse.coverage]
    assert [c.state for c in forward.coverage] == [c.state for c in reverse.coverage]


def test_sig_anonymous_block_continuation_keeps_key():
    """#6 匿名块增加续页证据不得换键：键锚定主块候选坐标，不随证据集合漂移。"""
    single = _assemble(
        {"main": _sig_env([_sig_candidate("c1", "SIGNATURE_BLOCK", "（签字栏空白）")])}
    )
    with_continuation = _assemble(
        {
            "main": _sig_env(
                [
                    _sig_candidate("c1", "SIGNATURE_BLOCK", "（签字栏空白）"),
                    _sig_candidate("c2", "SIGNATURE_BLOCK", "甲方（盖章）续页：骑缝章处", continues_ref="c1"),
                ]
            )
        }
    )
    assert len(with_continuation.data.signature_blocks) == 1
    assert len(single.data.signature_blocks) == 1
    assert single.data.signature_blocks[0].signature_block_key == with_continuation.data.signature_blocks[0].signature_block_key
    assert len(with_continuation.data.signature_blocks[0].evidence_ids) == 2


def test_sig_only_unlocatable_candidates_fail_not_unavailable():
    """#7 (重铸) 文档仅有不可定位候选：必须 ModelFormatError 整请求失败。
    旧断言废弃理由：它固化了"零可定位事实+不可定位候选→UNAVAILABLE coverage"，
    与正式契约冲突（同 #1 重铸理由）：不可定位的普通候选是模型输出不合法，
    不是"来源缺口"；UNAVAILABLE 只允许由显式、可定位的 source_gap 覆盖全部
    适用类别驱动（J6），技术失败不得降级为任何 coverage 状态（红线矩阵行）。"""
    from app.core.errors import ModelFormatError

    with pytest.raises(ModelFormatError):
        _assemble(
            {
                "main": _sig_env(
                    [_sig_candidate("c9", "SIGNER_NAME", "文档中不存在的签章引文XYZ", role_text="授权代表", signer_name="不明")]
                )
            }
        )


def test_sig_attachment_backfill_full_main_projection_unchanged():
    """#8 附件存在与否，主合同完整投影（全部九类对象含值）逐字段一致。"""
    main_env = _sig_env(
        _base_block_candidates()
        + [
            _sig_candidate("c4", "IDENTITY_NUMBER", "身份证号：11010119900307011X", identity_number="11010119900307011X"),
            _sig_candidate("c5", "SIGNING_DATE", "签署日期：2026年8月20日", signing_date="2026年8月20日"),
            _sig_candidate("c6", "BANK_ACCOUNT", "收款账号：6222020200112233445", bank_account="6222020200112233445"),
        ]
    )
    attach_env = _sig_env(
        [
            _sig_candidate("a1", "SIGNATURE_BLOCK", "附件签章：戊己服务有限公司", document_key="attach1", party_name="戊己服务有限公司"),
            _sig_candidate("a2", "SIGNER_NAME", "附件签字：孙七", document_key="attach1", role_text="经办", signer_name="孙七"),
            _sig_candidate("a3", "IDENTITY_NUMBER", "附件身份证号：44030119770707005W", document_key="attach1", identity_number="44030119770707005W"),
        ]
    )
    only_main = _assemble({"main": main_env}, doc_keys=["main"])
    both = _assemble({"main": main_env, "attach1": attach_env}, doc_keys=["main", "attach1"])
    assert _main_projection(only_main) == _main_projection(both)


def test_sig_candidate_model_exposes_relation_fields():
    """#9 SignatureCandidate 必须结构化表达父块/续页/替代/用途关系。"""
    from app.capabilities.contract_review.two_stage.prepare_model import SignatureCandidate

    fields = set(SignatureCandidate.model_fields)
    assert {"block_ref", "continues_ref", "alternative_of_ref", "purpose_text"} <= fields
    model = SignatureCandidate(
        candidate_ref="c1",
        candidate_kind="SIGNATURE_BLOCK",
        document_key="main",
        quote="q",
    )
    assert model.block_ref is None
    assert model.continues_ref is None
    assert model.alternative_of_ref is None
    assert model.purpose_text is None


def test_sig_response_schema_declares_relation_fields():
    """#9 严格响应 Schema 必须与候选模型同步声明关系字段。"""
    from app.capabilities.contract_review.two_stage.prepare_response_formats import (
        SIGNATURE_CANDIDATE_SCHEMA,
    )

    props = SIGNATURE_CANDIDATE_SCHEMA["properties"]
    for name in ("block_ref", "continues_ref", "alternative_of_ref", "purpose_text"):
        assert name in props, f"响应 Schema 缺少 {name}"
        assert "null" in str(props[name].get("type", props[name].get("enum", ""))), f"{name} 必须可空"


def test_sig_prompt_declares_relations_ranges_and_null_rule():
    """#9/#10 Prompt 必须说明 ref 关系、用途语义与 extraction_ranges 范围外不得提取。"""
    text_blob = Path("prompts/contract_review_prepare.yaml").read_text(encoding="utf-8")
    start = text_blob.index("prepare_signature_document:")
    end = text_blob.index("prepare_amount_copy_main:")
    section = text_blob[start:end]
    for token in ("block_ref", "continues_ref", "alternative_of_ref", "purpose_text", "extraction_ranges"):
        assert token in section, f"signature prompt 缺少 {token} 语义说明"


def test_sig_multi_block_child_without_ref_fails():
    """#9 多块环境下子候选无 block_ref：禁止猜测归属，整体失败。"""
    from app.core.errors import ModelFormatError

    with pytest.raises((ModelFormatError, ValueError)):
        _assemble(
            {
                "main": _sig_env(
                    [
                        _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                        _sig_candidate("c2", "SIGNATURE_BLOCK", "乙方（盖章）：丙丁工程有限公司", party_name="丙丁工程有限公司"),
                        _sig_candidate("c3", "SIGNING_DATE", "签署日期：2026年8月20日", signing_date="2026年8月20日"),
                    ]
                )
            }
        )


def test_sig_no_private_imports_from_header_extractor():
    """#11 signature 不得依赖 header extractor 私有函数/类型，也不得引入旧流水线或持久化。"""
    import inspect

    source = inspect.getsource(_assembler())
    for banned in ("_locate_evidence", "_index_source_gaps", "_unlocatable_issue", "_gap_issue"):
        assert banned not in source, f"extract_signature 不得引用私有实现 {banned}"
    for banned in ("signing_preset", "get_settings", "sqlite", "requests", "httpx", "uvicorn"):
        assert banned not in source, f"extract_signature 不得引入 {banned}"


# ---------------------------------------------------------------------------
# J. Round-3 复核阻断项 RED（DEC-LTC-20260909-001 保守装配 + coverage/证据闭合）
# ---------------------------------------------------------------------------

_ALL_SIG_KINDS = [
    "SIGNATURE_BLOCK",
    "SIGNER_NAME",
    "IDENTITY_NUMBER",
    "SIGNING_DATE",
    "BANK_NAME",
    "BANK_ACCOUNT",
    "ACCOUNT_HOLDER",
    "ADDRESS",
    "PHONE",
    "FAX",
    "WEBSITE",
    "POSTAL_CODE",
]


def test_sig_same_role_slot_structure_ambiguous_needs_confirmation():
    """J1 同一块同角色、party 证据互斥：一个栏位多人还是多个栏位无法唯一解释，
    必须 NeedsConfirmationError 停止装配（DEC-LTC-20260909-001 / spec 同角色场景），
    不得静默聚合成单 slot 或按猜测拆分。
    本轮复核澄清：该用例成立的正式判据是"两条单行引文证据坐标不同，现有可靠证据
    无法唯一证明是一栏多人还是两个独立栏位"；互斥 party_name 声称本身不在已定位
    引文中，不构成证据（见 L1：未支持的声称不得触发人工确认）。"""
    from app.capabilities.contract_review.two_stage.prepare_model import (
        NeedsConfirmationError,
    )

    with pytest.raises(NeedsConfirmationError):
        _assemble(
            {
                "main": _sig_env(
                    [
                        _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                        _sig_candidate(
                            "c2", "SIGNER_NAME", "签章人（联合）：周八",
                            role_text="法定代表人或授权代表", signer_name="周八",
                            party_name="甲乙科技有限公司", block_ref="c1",
                        ),
                        _sig_candidate(
                            "c3", "SIGNER_NAME", "签章人（联合）：吴九",
                            role_text="法定代表人或授权代表", signer_name="吴九",
                            party_name="丙丁工程有限公司", block_ref="c1",
                        ),
                    ]
                )
            }
        )


def test_sig_unrelated_party_purpose_keeps_value_without_confirmation():
    """J2 引文不含主体/用途关系证据：仅模型字段声称 party/purpose 时，
    必须保留字段值与证据但不得 BOUND/CONFIRMED（spec:160 不得把模型推测升级）。
    引文自身携带关系证据时才允许 BOUND + CONFIRMED。"""
    unrel = _assemble(
        {
            "main": _sig_env(
                [
                    _sig_candidate(
                        "c1", "BANK_ACCOUNT", "打款账号：6217000000012345678",
                        bank_account="6217000000012345678",
                        party_name="甲乙科技有限公司",
                        purpose_text="收款",
                    )
                ]
            )
        }
    )
    assert len(unrel.data.account_observations) == 1, "字段值必须保留"
    obs = unrel.data.account_observations[0]
    assert obs.field.observations[0].raw_text == "6217000000012345678"
    assert obs.field.observations[0].evidence_ids, "证据必须保留"
    assert obs.party_binding_state in {"UNBOUND", "UNCERTAIN"}, "无关系证据不得 BOUND"
    assert obs.party_key is None
    assert obs.purpose_state != "CONFIRMED", "引文未明示用途不得 CONFIRMED"

    related = _assemble(
        {
            "main": _sig_env(
                [
                    _sig_candidate(
                        "c1", "BANK_ACCOUNT",
                        "甲乙科技有限公司收款账号：6217000000098765432，用于本合同结算",
                        bank_account="6217000000098765432",
                        party_name="甲乙科技有限公司",
                        purpose_text="用于本合同结算",
                    )
                ]
            )
        }
    )
    good = related.data.account_observations[0]
    assert good.party_binding_state == "BOUND"
    assert good.party_key == KEY_JIA
    assert good.purpose_state == "CONFIRMED"


def test_sig_conflicting_or_self_references_fail_assembly():
    """J3 结构化引用互相矛盾或自引用：显式 block_ref 与姓名归属块冲突、
    alternative_of_ref 指向自身，均属引用不闭合，必须技术失败（DEC-LTC-20260909-001），
    不得静默忽略或择一吸收。"""
    from app.core.errors import ModelFormatError

    with pytest.raises((ModelFormatError, ValueError)):
        _assemble(
            {
                "main": _sig_env(
                    [
                        _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                        _sig_candidate("c2", "SIGNATURE_BLOCK", "乙方（盖章）：丙丁工程有限公司", party_name="丙丁工程有限公司"),
                        _sig_candidate(
                            "c3", "SIGNER_NAME", "乙方签字栏：王五",
                            role_text="授权代表", signer_name="王五", block_ref="c2",
                        ),
                        _sig_candidate(
                            "c4", "IDENTITY_NUMBER", "身份证号：31010119880202003Y",
                            identity_number="31010119880202003Y",
                            signer_name="王五", block_ref="c1",
                        ),
                    ]
                )
            }
        )

    with pytest.raises((ModelFormatError, ValueError)):
        _assemble(
            {
                "main": _sig_env(
                    _base_block_candidates()
                    + [
                        _sig_candidate(
                            "c4", "SIGNER_NAME", "签章人（联合）：周八",
                            role_text="备选代表", signer_name="周八",
                            alternative_of_ref="c4",
                        )
                    ]
                )
            }
        )


def test_sig_source_gap_foreign_document_or_out_of_range_is_technical_failure():
    """J4 source_gap 跨文档或超 extraction_ranges：必须技术失败，
    不得静默保持主文档 COMPLETE，也不得用窗口外证据伪装可定位缺口。"""
    from app.core.errors import ModelFormatError

    with pytest.raises((ModelFormatError, ValueError)):
        _assemble(
            {
                "main": _sig_env(
                    _base_block_candidates(),
                    gaps=[
                        {
                            "affected_fact_kinds": ["SIGNING_DATE"],
                            "message": "引用了其它文档的缺口",
                            "quote": "签署日期：不详",
                            "document_key": "attach1",
                        }
                    ],
                )
            },
            doc_keys=["main"],
        )

    with pytest.raises((ModelFormatError, ValueError)):
        _assemble(
            {
                "main": _sig_env(
                    _base_block_candidates(),
                    gaps=[
                        {
                            "affected_fact_kinds": ["SIGNING_DATE"],
                            "message": "引文在授权提取窗口之外",
                            "quote": "联系电话：010-12345678",
                        }
                    ],
                )
            },
            doc_keys=["main"],
            extraction_ranges={"main": [(0, MAIN_MD.index("---分页符---"))]},
        )


def test_sig_locatable_gap_partial_kinds_keeps_facts_and_locatable_issue():
    """J5 可定位来源缺口仅影响部分类别：事实必须完整保留、coverage 为 PARTIAL；
    同坐标多条缺口不得静默丢弃任何一条的可定位证据引用。"""
    box: list = []
    domain = _assemble(
        {
            "main": _sig_env(
                _base_block_candidates(),
                gaps=[
                    {
                        "affected_fact_kinds": ["SIGNING_DATE"],
                        "message": "第一处日期栏模糊",
                        "quote": "签署日期：不详",
                    },
                    {
                        "affected_fact_kinds": ["SIGNING_DATE"],
                        "message": "第二处日期与他条款矛盾",
                        "quote": "签署日期：2026年8月20日",
                    },
                ],
            )
        },
        doc_keys=["main"],
        registry_box=box,
    )
    registry, canonical = box
    _assert_reference_closure(domain.data, registry, canonical)
    assert len(domain.data.signature_blocks) == 1, "缺口不得吞掉已装配事实"
    assert {s.raw_name for s in domain.data.signer_candidates} == {"张三", "李四"}
    coverage = next(c for c in domain.coverage if c.document_key == "main")
    assert coverage.state == "PARTIAL"
    assert coverage.fact_issue_keys
    gap_evidence = {e for i in domain.issues for e in i.evidence_ids}
    assert len(gap_evidence) >= 2, "两条可定位缺口的证据引用都必须保留"
    valid_evidence = {item.evidence_id for item in registry.items()}
    assert gap_evidence <= valid_evidence


def test_sig_gap_all_applicable_signature_kinds_is_unavailable():
    """J6 缺口明确影响全部适用签章类别：必须 UNAVAILABLE，不得 PARTIAL。"""
    domain = _assemble(
        {
            "main": _sig_env(
                [],
                gaps=[
                    {
                        "affected_fact_kinds": list(_ALL_SIG_KINDS),
                        "message": "签章扫描页整页缺失",
                        "quote": "（签字栏空白）",
                    }
                ],
            )
        },
        doc_keys=["main"],
    )
    coverage = next(c for c in domain.coverage if c.document_key == "main")
    assert coverage.state == "UNAVAILABLE"
    assert domain.state == "UNAVAILABLE"
    assert coverage.fact_issue_keys
    assert set(coverage.affected_fact_kinds) >= {"SIGNATURE_BLOCK", "SIGNER_NAME", "SIGNING_DATE"}
    assert domain.data.signature_blocks == []


def test_sig_reliable_empty_scan_multi_document_complete():
    """J7 主合同与附件均可靠扫描且无签章：逐文档 COMPLETE、域 COMPLETE，
    不得 UNAVAILABLE/PARTIAL 或伪造事实。"""
    domain = _assemble(
        {"main": _sig_env([]), "attach1": _sig_env([])},
        doc_keys=["main", "attach1"],
    )
    by_doc = {c.document_key: c for c in domain.coverage}
    assert set(by_doc) == {"main", "attach1"}
    assert all(c.state == "COMPLETE" for c in by_doc.values())
    assert all(c.fact_issue_keys == [] for c in by_doc.values())
    assert domain.state == "COMPLETE"
    assert domain.issues == []


def test_sig_duplicate_identity_number_merges_all_evidence():
    """J8 重复同值身份证号（spec:87 同值重复合并事实保留全部证据）：
    两条引文同一号码同一块必须装配为单 candidate + 多证据，不得崩溃或二选一。"""
    domain = _assemble(
        {
            "main": _sig_env(
                [
                    _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                    _sig_candidate("c2", "SIGNER_NAME", "签章人（联合）：周八", role_text="授权代表", signer_name="周八", block_ref="c1"),
                    _sig_candidate(
                        "c3", "IDENTITY_NUMBER", "身份证号：11010119900307011X",
                        identity_number="11010119900307011X", block_ref="c1",
                    ),
                    _sig_candidate(
                        "c4", "IDENTITY_NUMBER", "身份证复印件：11010119900307011X",
                        identity_number="11010119900307011X", block_ref="c1",
                    ),
                ]
            )
        },
        doc_keys=["main"],
    )
    identities = domain.data.identity_number_candidates
    assert len(identities) == 1, "同值同块号码必须合并为单一候选"
    assert len(identities[0].evidence_ids) >= 2, "合并后保留全部证据"
    assert len({i.identity_number_key for i in identities}) == 1


def test_sig_main_projection_covers_all_nine_object_kinds_without_attachment_backfill():
    """J9 主合同投影覆盖全部九类签章对象（块/slot/替代组/signer/号码/关系/日期/账户/联系），
    附件存在与否主投影逐字段一致，不得回填。"""
    main_env = _sig_env(
        [
            _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
            _sig_candidate("c2", "SIGNER_NAME", "签章人（联合）：周八", role_text="联合签署", signer_name="周八", block_ref="c1"),
            _sig_candidate(
                "c3", "SIGNER_NAME", "或授权代表：赵六",
                role_text="授权代表", signer_name="赵六", block_ref="c1", alternative_of_ref="c2",
            ),
            _sig_candidate(
                "c4", "IDENTITY_NUMBER", "身份证复印件：11010119900307011X",
                identity_number="11010119900307011X", block_ref="c1",
            ),
            _sig_candidate("c5", "SIGNING_DATE", "签署日期：2026年8月20日", signing_date="2026年8月20日", block_ref="c1"),
            _sig_candidate("c6", "BANK_ACCOUNT", "打款账号：6217000000012345678", bank_account="6217000000012345678"),
            _sig_candidate("c7", "PHONE", "联系电话：010-12345678", phone="010-12345678"),
        ]
    )
    attach_env = _sig_env(
        [
            _sig_candidate("a1", "SIGNATURE_BLOCK", "附件签章：戊己服务有限公司", document_key="attach1", party_name="戊己服务有限公司"),
            _sig_candidate("a2", "SIGNER_NAME", "附件签字：孙七", document_key="attach1", role_text="经办", signer_name="孙七"),
            _sig_candidate("a3", "IDENTITY_NUMBER", "附件身份证号：44030119770707005W", document_key="attach1", identity_number="44030119770707005W"),
        ]
    )
    only_main = _assemble({"main": main_env}, doc_keys=["main"])
    both = _assemble({"main": main_env, "attach1": attach_env}, doc_keys=["main", "attach1"])
    projection = _main_projection(only_main)
    for key in (
        "blocks", "slots", "groups", "signers", "identities",
        "relations", "dates", "accounts", "contacts",
    ):
        assert key in projection
        assert projection[key], f"主合同投影必须覆盖 {key} 类对象"
    assert projection == _main_projection(both), "附件装配不得改变主合同任何签章对象"
    assert {c.document_key for c in both.coverage} == {"main", "attach1"}


# ---------------------------------------------------------------------------
# K. Round-4 同簇 P1 守卫（栏位歧义反例 / 块外 ref / 同名多主体 / gap 类别）
# ---------------------------------------------------------------------------


def test_sig_same_role_distinct_blocks_split_without_confirmation():
    """K1(#1 反例) 同角色但分属两个显式 block_ref 的真实块：结构唯一可解释，
    必须正常拆为 2 个 slot，不得误判 NeedsConfirmationError；
    同栏同主体多人（一栏多人）同样不得触发人工确认。

    (重铸说明) 本用例后半旧断言用两条不同单行引文（周八行/吴九行，证据坐标不同）
    静默合并为 1 slot，恰好固化 L2a 要纠偏的错误行为（不同坐标同角色不能证明
    同一栏位时必须人工确认）。正式契约下"一栏多人"的可证明形态是同一已定位
    证据坐标内列出多名签署人，故改为共享合并引文；反例侧由 L2a 覆盖。"""
    domain = _assemble(
        {
            "main": _sig_env(
                [
                    _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                    _sig_candidate("c2", "SIGNATURE_BLOCK", "乙方（盖章）：丙丁工程有限公司", party_name="丙丁工程有限公司"),
                    _sig_candidate("c3", "SIGNER_NAME", "签章人：张三", role_text="法定代表人或授权代表", signer_name="张三", party_name="甲乙科技有限公司", block_ref="c1"),
                    _sig_candidate("c4", "SIGNER_NAME", "签章人：李四", role_text="法定代表人或授权代表", signer_name="李四", party_name="丙丁工程有限公司", block_ref="c2"),
                ]
            )
        }
    )
    slots = domain.data.signer_slots
    assert len(slots) == 2, "同角色跨两个真实块属唯一解释，必须正常拆为 2 个 slot"
    assert {s.signature_block_key for s in slots} == {b.signature_block_key for b in domain.data.signature_blocks}

    one_slot = _assemble(
        {
            "main": _sig_env(
                [
                    _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                    _sig_candidate("c2", "SIGNER_NAME", "签章人（联合）：周八\n签章人（联合）：吴九", role_text="联合签署", signer_name="周八", party_name="甲乙科技有限公司", block_ref="c1"),
                    _sig_candidate("c3", "SIGNER_NAME", "签章人（联合）：周八\n签章人（联合）：吴九", role_text="联合签署", signer_name="吴九", party_name="甲乙科技有限公司", block_ref="c1"),
                ]
            )
        }
    )
    assert len(one_slot.data.signer_slots) == 1, "同块同角色同主体=一栏多人，不是歧义"
    assert len(one_slot.data.signer_candidates) == 2


def test_sig_block_party_name_without_quote_support_stays_unbound():
    """K2(#2) 块主体仅在模型字段声称、已定位引文不含主体名：
    保留 local_company_name 值但绑定必须 UNBOUND，不得 BOUND。"""
    domain = _assemble(
        {
            "main": _sig_env(
                [_sig_candidate("c1", "SIGNATURE_BLOCK", "（签字栏空白）", party_name="甲乙科技有限公司")]
            )
        }
    )
    assert len(domain.data.signature_blocks) == 1
    block = domain.data.signature_blocks[0]
    assert block.local_company_name.presence == "PRESENT_VALUE", "字段值必须保留"
    assert block.party_binding_state == "UNBOUND", "引文无主体关系证据不得 BOUND"
    assert block.party_key is None
    assert block.candidate_party_keys == []


def test_sig_field_observation_block_ref_must_resolve():
    """K3(#2/#3) 块外字段显式 block_ref：未知 ref 必须 ModelFormatError；
    有效 ref 必须绑定真实块 key，不得静默忽略。"""
    from app.core.errors import ModelFormatError

    with pytest.raises((ModelFormatError, ValueError)):
        _assemble(
            {
                "main": _sig_env(
                    [
                        _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                        _sig_candidate("c2", "BANK_ACCOUNT", "收款账号：6222020200112233445", bank_account="6222020200112233445", block_ref="zz"),
                    ]
                )
            }
        )

    domain = _assemble(
        {
            "main": _sig_env(
                [
                    _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                    _sig_candidate("c2", "BANK_ACCOUNT", "收款账号：6222020200112233445", bank_account="6222020200112233445", block_ref="c1"),
                ]
            )
        }
    )
    assert domain.data.account_observations[0].signature_block_key == domain.data.signature_blocks[0].signature_block_key


def test_sig_source_gap_unknown_fact_kind_fails_assembly():
    """K4(#4) source_gap 引用未知事实类别：模型输出不合法，必须技术失败。"""
    from app.core.errors import ModelFormatError

    with pytest.raises((ModelFormatError, ValueError)):
        _assemble(
            {
                "main": _sig_env(
                    _base_block_candidates(),
                    gaps=[{"affected_fact_kinds": ["NOT_A_SIGNATURE_KIND"], "message": "未知类别缺口"}],
                )
            },
            doc_keys=["main"],
        )


def test_sig_duplicate_same_name_multiple_canonical_parties_uncertain():
    """K5(#8) canonical 同名映射多个 party_key：不得 setdefault 择首，
    必须 UNCERTAIN 并保留全部候选 party key。"""
    registry = EvidenceRegistry({"main": MAIN_MD})
    ev = registry.register("main", "甲方（盖章）：甲乙科技有限公司")
    dup_key = stable_key("party", {"declared_name": "甲乙科技有限公司", "disambiguation": 1})

    def _party(key: str) -> CanonicalParty:
        return CanonicalParty(
            party_key=key,
            declared_name=ObservedField(
                presence="PRESENT_VALUE",
                normalization_state="VALID",
                observations=[
                    ObservedValue(
                        raw_text="甲乙科技有限公司",
                        normalized_value="甲乙科技有限公司",
                        evidence_ids=[ev.evidence_id],
                    )
                ],
            ),
            definition_evidence_ids=[ev.evidence_id],
        )

    canonical = [_party(KEY_JIA), _party(dup_key)]
    env = _sig_env(
        [_sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司")]
    )
    module = _assembler()
    fn = _extract_fn(module)
    with patch.object(module, "invoke_typed_prepare_model", side_effect=lambda _prompt, **_kwargs: env):
        domain = fn(
            [PreparedDocument(document_key="main", markdown=MAIN_MD)],
            canonical,
            registry,
            None,
        )
    block = domain.data.signature_blocks[0]
    assert block.party_binding_state == "UNCERTAIN", "同名多主体必须 UNCERTAIN，不得择首 BOUND"
    assert block.party_key is None
    assert set(block.candidate_party_keys) == {KEY_JIA, dup_key}


# ---------------------------------------------------------------------------
# L. Round-6 P1 因果矩阵纠偏 RED（声称≠证据 / 坐标歧义 / 引用冲突 / 键去文案）
# ---------------------------------------------------------------------------


def test_sig_unsupported_party_claims_do_not_trigger_confirmation():
    """L1(P1-1) party_name 互斥但均未出现在已定位引文中：字段声称不是证据
    （DEC-LTC-20260909-001"模型字段声称但引文不含⇒推测"），不得据此判定
    "同角色栏位结构无法唯一解释"而抛 NeedsConfirmationError；同一证据坐标的
    一栏多人必须正常装配 1 slot/2 signer，主体绑定各自 UNBOUND。"""
    domain = _assemble(
        {
            "main": _sig_env(
                [
                    _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                    _sig_candidate(
                        "c2", "SIGNER_NAME", "签章人（联合）：周八\n签章人（联合）：吴九",
                        role_text="联合签署", signer_name="周八",
                        party_name="甲乙科技有限公司", block_ref="c1",
                    ),
                    _sig_candidate(
                        "c3", "SIGNER_NAME", "签章人（联合）：周八\n签章人（联合）：吴九",
                        role_text="联合签署", signer_name="吴九",
                        party_name="丙丁工程有限公司", block_ref="c1",
                    ),
                ]
            )
        },
        doc_keys=["main"],
    )
    data = domain.data
    assert len(data.signer_slots) == 1, "同一证据坐标一栏多人是唯一解释，不得人工确认"
    slot = data.signer_slots[0]
    assert {s.raw_name for s in data.signer_candidates} == {"周八", "吴九"}
    assert set(slot.signer_keys) == {s.signer_key for s in data.signer_candidates}


def test_sig_same_block_role_distinct_coordinates_needs_confirmation():
    """L2a(P1-2) 同块同角色、两条不同单行引文（证据坐标不同）且无任何结构 ref
    声称：现有可靠证据无法唯一证明是一栏多人还是两个独立栏位（spec 同角色场景），
    必须 NeedsConfirmationError，不得静默合并为单 slot。"""
    from app.capabilities.contract_review.two_stage.prepare_model import (
        NeedsConfirmationError,
    )

    with pytest.raises(NeedsConfirmationError):
        _assemble(
            {
                "main": _sig_env(
                    [
                        _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                        _sig_candidate("c2", "SIGNER_NAME", "签章人（联合）：周八", role_text="联合签署", signer_name="周八", block_ref="c1"),
                        _sig_candidate("c3", "SIGNER_NAME", "签章人（联合）：吴九", role_text="联合签署", signer_name="吴九", block_ref="c1"),
                    ]
                )
            },
            doc_keys=["main"],
        )

    # L2b 锚定：同一证据坐标（共享合并引文）的一栏多人不是歧义，保留全部人员。
    same_coord = _assemble(
        {
            "main": _sig_env(
                [
                    _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                    _sig_candidate(
                        "c2", "SIGNER_NAME", "签章人（联合）：周八\n签章人（联合）：吴九",
                        role_text="联合签署", signer_name="周八", block_ref="c1",
                    ),
                    _sig_candidate(
                        "c3", "SIGNER_NAME", "签章人（联合）：周八\n签章人（联合）：吴九",
                        role_text="联合签署", signer_name="吴九", block_ref="c1",
                    ),
                ]
            )
        },
        doc_keys=["main"],
    )
    assert len(same_coord.data.signer_slots) == 1
    assert len(same_coord.data.signer_candidates) == 2


def test_sig_same_block_role_same_name_distinct_coordinates_needs_confirmation():
    """P1-2b 同一签章块、同一 role_text、同一 signer_name，但两个不同可定位坐标：
    现有可靠证据无法唯一证明它是一栏一人多处提及还是两个独立栏位，属结构歧义，
    必须 NeedsConfirmationError；不得因同名而静默合并为单栏位
    （spec 同角色签署结构无法唯一解释）。"""
    from app.capabilities.contract_review.two_stage.prepare_model import (
        NeedsConfirmationError,
    )

    with pytest.raises(NeedsConfirmationError):
        _assemble(
            {
                "main": _sig_env(
                    [
                        _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                        _sig_candidate("c2", "SIGNER_NAME", "签章人：张三", role_text="授权代表", signer_name="张三"),
                        _sig_candidate("c3", "SIGNER_NAME", "盖章旁签字：张三", role_text="授权代表", signer_name="张三"),
                    ]
                )
            },
            doc_keys=["main"],
        )


def test_sig_cross_block_alternative_reference_fails_assembly():
    """L3(P1-3) alternative_of_ref 的成员分属两个不同签章块的栏位：替代关系
    只在同一块内成立，跨块替代引用不闭合，必须 ModelFormatError，
    不得静默生成跨块 AlternativeSignerGroup。"""
    from app.core.errors import ModelFormatError

    with pytest.raises(ModelFormatError):
        _assemble(
            {
                "main": _sig_env(
                    [
                        _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                        _sig_candidate("c2", "SIGNATURE_BLOCK", "乙方（盖章）：丙丁工程有限公司", party_name="丙丁工程有限公司"),
                        _sig_candidate("c3", "SIGNER_NAME", "签章人：张三", role_text="授权代表", signer_name="张三", block_ref="c1"),
                        _sig_candidate(
                            "c4", "SIGNER_NAME", "乙方签字栏：王五",
                            role_text="备选代表", signer_name="王五",
                            block_ref="c2", alternative_of_ref="c3",
                        ),
                    ]
                )
            },
            doc_keys=["main"],
        )


def test_sig_identity_quote_without_name_not_direct():
    """L4(P1-4) IDENTITY_NUMBER 引文未明示 signer_name，仅字段声称"张三"：
    名字-号码关系不在已定位证据中，不得装配 DIRECT（DEC 声称非证据）；
    块内一人一号时应为 UNIQUE_IN_BLOCK。"""
    domain = _assemble(
        {
            "main": _sig_env(
                [
                    _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                    _sig_candidate("c2", "SIGNER_NAME", "签章人：张三", role_text="授权代表", signer_name="张三", block_ref="c1"),
                    _sig_candidate(
                        "c3", "IDENTITY_NUMBER", "身份证号：11010119900307011X",
                        identity_number="11010119900307011X", signer_name="张三", block_ref="c1",
                    ),
                ]
            )
        },
        doc_keys=["main"],
    )
    relations = domain.data.person_id_relations
    assert relations
    assert all(r.association_state != "DIRECT" for r in relations), (
        "引文不含姓名的字段声称不得升级为 DIRECT"
    )
    assert {r.association_state for r in relations} == {"UNIQUE_IN_BLOCK"}


def test_sig_block_ref_conflicting_with_located_party_evidence_fails():
    """L5(P1-5) 显式 block_ref 有效（指向真实块）但候选引文携带另一块的
    已定位主体证据（乙栏 丙丁工程有限公司 ↔ c2 块）：结构化归属与证据冲突，
    引用不闭合，必须 ModelFormatError，不得按 ref 静默装配到冲突块。"""
    from app.core.errors import ModelFormatError

    with pytest.raises(ModelFormatError):
        _assemble(
            {
                "main": _sig_env(
                    [
                        _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                        _sig_candidate("c2", "SIGNATURE_BLOCK", "签章表：乙栏 丙丁工程有限公司", party_name="丙丁工程有限公司"),
                        _sig_candidate(
                            "c3", "SIGNER_NAME", "签章表：乙栏 丙丁工程有限公司",
                            role_text="授权代表", signer_name="冯十", block_ref="c1",
                        ),
                    ]
                )
            },
            doc_keys=["main"],
        )


def test_sig_field_block_ref_conflicting_with_located_party_evidence_fails():
    """P1-5b 块外账户/联系字段显式 block_ref 指向乙方签章块，但已定位引文明确包含
    甲方主体及账户事实：结构化归属（乙方块）与引文主体证据（甲方）冲突，引用不
    闭合，必须 ModelFormatError，禁止输出"所属乙方块、BOUND 甲方"的矛盾观察。"""
    from app.core.errors import ModelFormatError

    with pytest.raises(ModelFormatError):
        _assemble(
            {
                "main": _sig_env(
                    [
                        _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                        _sig_candidate("c2", "SIGNATURE_BLOCK", "签章表：乙栏 丙丁工程有限公司", party_name="丙丁工程有限公司"),
                        _sig_candidate(
                            "c3", "BANK_ACCOUNT",
                            "甲乙科技有限公司收款账号：6217000000098765432，用于本合同结算",
                            bank_account="6217000000098765432",
                            party_name="甲乙科技有限公司", block_ref="c2",
                        ),
                    ]
                )
            },
            doc_keys=["main"],
        )


def test_sig_single_category_gap_never_unavailable():
    """L7(P1-7) 仅一个事实类别（SIGNING_DATE）受可定位缺口影响：
    UNAVAILABLE 只允许在全部适用类别明确受影响时出现（spec 187-188），
    单类别缺口必须 PARTIAL。"""
    domain = _assemble(
        {
            "main": _sig_env(
                _base_block_candidates(),
                gaps=[
                    {
                        "affected_fact_kinds": ["SIGNING_DATE"],
                        "message": "日期栏模糊",
                        "quote": "签署日期：不详",
                    }
                ],
            )
        },
        doc_keys=["main"],
    )
    coverage = next(c for c in domain.coverage if c.document_key == "main")
    assert coverage.state == "PARTIAL"
    assert coverage.state != "UNAVAILABLE"
    assert set(coverage.affected_fact_kinds) == {"SIGNING_DATE"}


def test_sig_two_locatable_gaps_union_all_kinds_is_unavailable():
    """P1-6b 两条各自只覆盖部分签章类别的可定位缺口，其 affected_fact_kinds 并集
    恰覆盖全部适用签章类别：整体扫描仍无法覆盖全部适用类别，文档 coverage 必须
    UNAVAILABLE（spec:187 全部适用类别受影响），不得因无单条缺口覆盖全部类别而
    降级为 PARTIAL。"""
    gap_block = {
        "affected_fact_kinds": [
            "SIGNATURE_BLOCK", "SIGNER_NAME", "IDENTITY_NUMBER", "SIGNING_DATE",
        ],
        "message": "签章块/人员/证件/日期区域不可读",
        "quote": "（签字栏空白）",
    }
    gap_fields = {
        "affected_fact_kinds": [
            "BANK_NAME", "BANK_ACCOUNT", "ACCOUNT_HOLDER", "ADDRESS",
            "PHONE", "FAX", "WEBSITE", "POSTAL_CODE",
        ],
        "message": "账户/联系观察区域不可读",
        "quote": "联系电话：010-12345678",
    }
    assert (
        set(gap_block["affected_fact_kinds"]) | set(gap_fields["affected_fact_kinds"])
        == set(_ALL_SIG_KINDS)
    ), "本用例前提：两条缺口并集恰覆盖全部适用签章类别"
    assert not set(_ALL_SIG_KINDS) <= set(gap_block["affected_fact_kinds"])
    assert not set(_ALL_SIG_KINDS) <= set(gap_fields["affected_fact_kinds"])

    domain = _assemble(
        {"main": _sig_env([], gaps=[gap_block, gap_fields])},
        doc_keys=["main"],
    )
    coverage = next(c for c in domain.coverage if c.document_key == "main")
    assert coverage.state == "UNAVAILABLE"
    assert domain.state == "UNAVAILABLE"


def test_sig_signer_slot_key_independent_of_role_text():
    """L8(P1-8) 文档与证据坐标完全一致、仅 role_text（模型展示文案）不同：
    signer_slot_key 必须不变（spec:238 稳定键不得含模型自由文案）。"""
    def _one(role: str) -> str:
        domain = _assemble(
            {
                "main": _sig_env(
                    [
                        _sig_candidate("c1", "SIGNATURE_BLOCK", "甲方（盖章）：甲乙科技有限公司", party_name="甲乙科技有限公司"),
                        _sig_candidate("c2", "SIGNER_NAME", "签章人：张三", role_text=role, signer_name="张三", block_ref="c1"),
                    ]
                )
            },
            doc_keys=["main"],
        )
        return domain.data.signer_slots[0].signer_slot_key

    assert _one("授权代表") == _one("法定代表人"), (
        "slot key 不得由 role_text 展示文案派生"
    )
