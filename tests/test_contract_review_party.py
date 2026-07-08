from app.capabilities.contract_review.party import build_candidate_parties, classify_role
from app.capabilities.contract_review.schemas import ContractParty


def test_classify_customer_supplier_and_unknown_roles():
    assert classify_role("甲方") == "customer"
    assert classify_role("买方") == "customer"
    assert classify_role("乙方") == "supplier"
    assert classify_role("卖方") == "supplier"
    assert classify_role("实施单位") == "neutral"


def test_build_candidates_skips_customer_and_orders_supplier_before_neutral():
    parties = [
        ContractParty(role="买方", name="客户公司"),
        ContractParty(role="第三方", name="中性公司"),
        ContractParty(role="卖方", name="我方公司"),
        ContractParty(role="实施单位", name="未知角色公司"),
    ]
    candidates = build_candidate_parties(parties)
    assert [(p.role, p.name) for p in candidates] == [
        ("卖方", "我方公司"),
        ("第三方", "中性公司"),
        ("实施单位", "未知角色公司"),
    ]


def test_build_candidates_ignores_empty_names():
    parties = [ContractParty(role="乙方", name=""), ContractParty(role="服务方", name="服务公司")]
    candidates = build_candidate_parties(parties)
    assert [(p.role, p.name) for p in candidates] == [("服务方", "服务公司")]
