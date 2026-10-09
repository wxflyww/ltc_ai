"""评审智能总结输入/输出 Schema 边界用例（设计文档 §3/§4 契约）。"""
import pytest
from pydantic import ValidationError

from app.capabilities.review_summary.schemas import (
    EscalationConcern,
    Opinion,
    OpinionDetail,
    ReviewSummaryData,
    ReviewSummaryRequest,
    ReviewSummarySection,
    RiskConcern,
    RiskMeasure,
    RiskRegisterItem,
)

_OPINION = {
    "node_name": "法务评审",
    "approver_name": "陈某",
    "role": "法务",
    "action": "有条件通过",
    "comment": "付款争议解决条款约定不明确，建议补充仲裁地后方可通过。",
}


def test_minimal_request_opinions_only():
    req = ReviewSummaryRequest.model_validate({"opinions": []})
    assert req.contract_meta is None
    assert req.route_reason is None
    assert req.risk_register == []
    assert req.opinions == []


def test_opinions_missing_rejected():
    with pytest.raises(ValidationError):
        ReviewSummaryRequest.model_validate({})


def test_action_passthrough_any_non_empty_string():
    """「传过来是啥就是啥」：action 不做枚举/翻译，任意非空原值照单全收、原样回显；空串拒绝。"""
    for action in ("通过", "有条件通过", "不通过", "驳回", "approved"):
        req = ReviewSummaryRequest.model_validate({"opinions": [{**_OPINION, "action": action}]})
        assert req.opinions[0].action == action
    with pytest.raises(ValidationError):
        ReviewSummaryRequest.model_validate({"opinions": [{**_OPINION, "action": ""}]})


def test_opinion_required_fields():
    for field in ("node_name", "approver_name", "role", "action", "comment"):
        bad = {k: v for k, v in _OPINION.items() if k != field}
        with pytest.raises(ValidationError):
            Opinion.model_validate(bad)


def test_opinion_submitted_at_optional():
    op = Opinion.model_validate({**_OPINION, "submitted_at": "2026-09-25T14:32:00+08:00"})
    assert op.submitted_at == "2026-09-25T14:32:00+08:00"
    assert Opinion.model_validate(_OPINION).submitted_at is None


def test_unknown_extra_field_not_rejected():
    """未定义的新增可选字段不拒绝（spec：CRM 等后续扩展向后兼容）。"""
    req = ReviewSummaryRequest.model_validate(
        {
            "contract_meta": {"contract_type": "硬件集成", "crm_credit_rating": "AAA"},
            "opinions": [_OPINION],
        }
    )
    assert req.contract_meta.contract_type == "硬件集成"
    assert req.opinions[0].action == "有条件通过"


def test_contract_meta_group_optional_and_partial():
    req = ReviewSummaryRequest.model_validate(
        {"contract_meta": {"contract_type": "硬件集成"}, "opinions": []}
    )
    assert req.contract_meta.contract_amount is None
    assert req.contract_meta.gross_margin is None

    req2 = ReviewSummaryRequest.model_validate({"contract_meta": None, "opinions": []})
    assert req2.contract_meta is None


def test_route_reason_text_passthrough():
    text = "合同总额超过 ¥100 万，按权限规则触发副总经理终审节点"
    req = ReviewSummaryRequest.model_validate({"route_reason": {"text": text}, "opinions": []})
    assert req.route_reason.text == text


def test_risk_register_item_all_fields_optional():
    assert RiskRegisterItem.model_validate({}).risk_id is None
    full = {
        "risk_id": "RSK-001",
        "title": "付款风险",
        "level": "高",
        "source": "财经评审",
        "description": "客户预付款比例 15%，低于我司标准 30%",
        "standard_clause": "《合同签订标准》第 3.2 条：预付款比例不低于 30%",
        "potential_impact": "项目前期资金压力较大，资金占用 96 天",
        "measure_type": "缓解",
        "measure_desc": "要求客户签署补充付款承诺函，并将首付款拆分为两期",
        "decision_type": "接受风险",
        "decision_note": "考虑客户战略价值，同意让步",
        "decision_by": "陈总",
    }
    assert RiskRegisterItem.model_validate(full).model_dump() == full


def test_output_escalation_and_risk_construction():
    esc = EscalationConcern(text="合同总额超过 ¥100 万")
    assert esc.model_dump() == {"type": "escalation", "text": "合同总额超过 ¥100 万"}

    risk = RiskConcern(
        risk_id="RSK-001",
        title="付款风险",
        measure=RiskMeasure(measure_type="缓解", measure_desc="要求客户签署补充付款承诺函"),
    )
    dumped = risk.model_dump()
    assert dumped["type"] == "risk"
    assert dumped["measure"] == {"measure_type": "缓解", "measure_desc": "要求客户签署补充付款承诺函"}


def test_output_section_text_can_be_null_for_degradation():
    section = ReviewSummarySection(text=None)
    assert section.source_refs == []
    data = ReviewSummaryData(review_summary=section)
    assert data.key_concerns == []
    assert data.opinion_details == []
    assert data.degraded_sections == []


def test_output_data_requires_review_summary():
    with pytest.raises(ValidationError):
        ReviewSummaryData.model_validate({"key_concerns": []})


def test_output_matches_design_example():
    """设计文档 §4.2 示例 data 与输出 Schema 逐字段对齐（validate + roundtrip）。"""
    example = {
        "review_summary": {
            "text": (
                "该合同为硬件集成合同，合同总额 ¥126 万元，综合毛利率 27.7%。共 4 条意见：通过 2 条、"
                "有条件通过 2 条。关注点集中在预付款比例与付款争议条款两处。预付款比例 15% 低于公司标准，"
                "要求争取提至 20% 或确认垫资（财经评审、风控评审）；付款争议条款须补充仲裁地后方可通过（法务评审）。"
            ),
            "source_refs": [
                "contract_meta.contract_type",
                "contract_meta.contract_amount",
                "contract_meta.gross_margin",
                "opinions",
                "opinions[2]",
                "opinions[3]",
                "opinions[1]",
            ],
            "themes": [
                {
                    "text": "预付款比例 15% 低于公司标准，要求争取提至 20% 或确认垫资。",
                    "opinion_refs": ["opinions[2]", "opinions[3]"],
                },
                {
                    "text": "付款争议条款须补充仲裁地后方可通过。",
                    "opinion_refs": ["opinions[1]"],
                },
            ],
        },
        "key_concerns": [
            {
                "type": "escalation",
                "text": "合同总额超过 ¥100 万，按权限规则触发副总经理终审节点",
            },
            {
                "type": "risk",
                "risk_id": "RSK-001",
                "title": "付款风险",
                "level": "高",
                "source": "财经评审",
                "description": "客户预付款比例 15%，低于我司标准 30%",
                "standard_clause": "《合同签订标准》第 3.2 条：预付款比例不低于 30%",
                "potential_impact": "项目前期资金压力较大，资金占用 96 天，可能影响交付进度",
                "decision_type": "接受风险",
                "decision_by": "陈总",
                "decision_note": "考虑客户战略价值，同意让步",
                "measure": {
                    "measure_type": "缓解",
                    "measure_desc": "要求客户签署补充付款承诺函，并将首付款拆分为两期",
                },
            },
            {
                "type": "risk",
                "risk_id": "RSK-003",
                "title": "法律风险",
                "level": "高",
                "source": "法务评审",
                "description": "违约责任条款不对等，对方无违约责任约定",
                "standard_clause": "《合同法务指引》第 4.5 条：双方违约责任应对等",
                "potential_impact": "客户违约时我司难以主张赔偿",
                "decision_type": "不接受",
                "decision_by": "杨律师",
                "decision_note": "必须修改后方可签署",
                "measure": {
                    "measure_type": "预防",
                    "measure_desc": "与客户谈判补充对方逾期付款违约金条款",
                },
            },
        ],
        "opinion_details": [
            {
                "node_name": "销售评审",
                "approver_name": "张某",
                "role": "销售",
                "action": "通过",
                "summary": "认可推进：让步 3% 换三年运维续约优先权，具战略意义。",
                "source_ref": "opinions[0]",
            },
            {
                "node_name": "法务评审",
                "approver_name": "陈某",
                "role": "法务",
                "action": "有条件通过",
                "summary": "有条件通过：付款争议条款须补充仲裁地，其余无重大法律障碍。",
                "source_ref": "opinions[1]",
            },
            {
                "node_name": "财经评审",
                "approver_name": "孙某",
                "role": "财务",
                "action": "有条件通过",
                "summary": "有条件通过：预付款低于公司标准、预计占用资金 96 天，要求争取提至 20% 或确认垫资；其余预算定价合理。",
                "source_ref": "opinions[2]",
            },
            {
                "node_name": "风控评审",
                "approver_name": "周某",
                "role": "风控",
                "action": "通过",
                "summary": "认可推进：资信良好、无诉讼、历史回款正常；预付款问题附议财务。",
                "source_ref": "opinions[3]",
            },
        ],
        "degraded_sections": [],
    }
    data = ReviewSummaryData.model_validate(example)
    assert data.model_dump() == example
    assert data.key_concerns[0].type == "escalation"
    assert data.key_concerns[1].type == "risk"
    assert data.opinion_details[0] == OpinionDetail(**example["opinion_details"][0])
