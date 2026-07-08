from app.capabilities.contract_review.checks import (
    build_check_items,
    build_review_data,
    check_amount_payment,
    check_seq1,
    check_seq2_11,
    check_seq3,
)
from app.capabilities.contract_review.schemas import (
    AuthorizedRep,
    CheckItem,
    ContractParty,
    HeaderInfo,
    OurPartyContext,
    SignatureInfo,
    SystemPreset,
)


def test_build_check_items_splits_fail_and_warn_for_same_id():
    items = build_check_items(
        item_id="序号2",
        item_name="签章页完整性",
        hard_reasons=["银行账号不一致"],
        warn_reasons=["传真信息缺失"],
    )
    assert [item.result for item in items] == ["FAIL", "WARN"]
    assert [item.block_level for item in items] == ["硬阻断", "提示"]


def test_build_check_items_returns_pass_when_no_reasons():
    items = build_check_items("序号1", "合同首页完整性", [], [])
    assert len(items) == 1
    assert items[0].result == "PASS"
    assert items[0].block_level == "通过"


def test_build_review_data_preserves_duplicate_ids_and_blocks():
    checks = [
        CheckItem(id="序号2", name="签章页完整性", result="FAIL", block_level="硬阻断", reason="银行账号不一致"),
        CheckItem(id="序号2", name="签章页完整性", result="WARN", block_level="提示", reason="传真信息缺失"),
    ]
    data = build_review_data("2026-07-07T10:00:00", checks)
    assert data.overall_result == "BLOCK"
    assert len(data.checks) == 2
    assert [item.reason for item in data.checks] == ["银行账号不一致", "传真信息缺失"]


def _preset():
    return SystemPreset(
        entity_name="我方公司",
        legal_rep_name="张三",
        legal_rep_id_number="210102197001010011",
        authorized_reps=[AuthorizedRep(name="李四", id_number="210102197001010022")],
        bank_name="招商银行",
        bank_account="123456",
        account_holder="我方公司",
        address="地址",
        phone="024-12345678",
        fax="",
        website="http://example.com",
        postal_code="110000",
    )


def _header():
    return HeaderInfo(
        contract_name="测试合同",
        contract_number=None,
        signing_location="沈阳",
        signing_date="2026年7月8日",
        parties=[ContractParty(role="买方", name="客户公司"), ContractParty(role="卖方", name="我方公司")],
    )


def _signature():
    return SignatureInfo(
        signature_parties=[ContractParty(role="买方", name="客户公司"), ContractParty(role="卖方", name="我方公司")],
        role="卖方",
        name="我方公司",
        legal_rep_name="李四",
        signer_id_number="210102197001010022",
        signing_date="2026年7月8日",
        bank_name="招商银行",
        bank_account="123456",
        account_holder="我方公司",
        address="地址",
        phone="024-12345678",
        fax=None,
        website="http://example.com",
        postal_code="110000",
    )


def test_seq1_warns_contract_number_but_passes_required_fields():
    items = check_seq1(_header(), OurPartyContext(role="卖方", name="我方公司"), _preset())
    assert [item.result for item in items] == ["WARN"]
    assert "合同编号缺失" in items[0].reason


def test_seq1_fails_when_preset_unavailable():
    items = check_seq1(_header(), None, None)
    assert items[0].result == "FAIL"
    assert "无法校验我方签署主体名称" in items[0].reason


def test_seq2_11_preserves_fail_and_warn():
    sig = _signature()
    sig.bank_account = "999999"
    sig.fax = None
    seq2_items, seq11_items = check_seq2_11(_header(), sig, OurPartyContext(role="卖方", name="我方公司"), _preset())
    assert [item.result for item in seq2_items] == ["FAIL", "WARN"]
    assert [item.result for item in seq11_items] == ["FAIL"]


def test_seq2_allows_authorized_rep_and_matching_id_number():
    seq2_items, seq11_items = check_seq2_11(_header(), _signature(), OurPartyContext(role="卖方", name="我方公司"), _preset())
    assert seq2_items[0].result == "WARN"
    assert "传真信息缺失" in seq2_items[0].reason
    assert seq11_items[0].result == "PASS"


def test_seq2_warns_when_id_number_without_name():
    sig = _signature()
    sig.legal_rep_name = None
    sig.signer_id_number = "210102197001010022"
    seq2_items, _ = check_seq2_11(_header(), sig, OurPartyContext(role="卖方", name="我方公司"), _preset())
    assert any(item.result == "WARN" and "身份证号" in (item.reason or "") for item in seq2_items)


def test_seq3_fails_when_our_party_missing():
    item = check_seq3(_header(), _signature(), None)
    assert item.result == "FAIL"


def test_seq3_passes_when_signature_date_empty():
    sig = _signature()
    sig.signing_date = None
    item = check_seq3(_header(), sig, OurPartyContext(role="卖方", name="我方公司"))
    assert item.result == "PASS"


def test_payment_method_missing_fails():
    items = check_amount_payment({"currency": "人民币", "payment_method": None, "total_amount_numeric": "100", "total_amount_uppercase": "壹佰元整", "payment_stages": []})
    seq9 = next(item for item in items if item.id == "序号9")
    assert seq9.result == "FAIL"


def test_empty_payment_stages_warns_not_fail():
    items = check_amount_payment({"currency": "人民币", "payment_method": "电汇", "total_amount_numeric": "100", "total_amount_uppercase": "壹佰元整", "payment_stages": []})
    seq10 = next(item for item in items if item.id == "序号10")
    assert seq10.result == "WARN"
    assert "付款阶段不明确" in seq10.reason


def test_currency_missing_fails():
    items = check_amount_payment({"currency": None, "payment_method": "电汇", "total_amount_numeric": "100", "total_amount_uppercase": "壹佰元整", "payment_stages": []})
    seq8 = next(item for item in items if item.id == "序号8")
    assert seq8.result == "FAIL"


def test_stage_percentage_not_100_fails():
    items = check_amount_payment({
        "currency": "人民币",
        "payment_method": "电汇",
        "total_amount_numeric": "100",
        "total_amount_uppercase": "壹佰元整",
        "payment_stages": [{"stage_name": "首付款", "percentage": "50", "amount_numeric": "50", "amount_uppercase": "伍拾元整"}],
    })
    seq10 = next(item for item in items if item.id == "序号10")
    assert seq10.result == "FAIL"
    assert "不等于100%" in seq10.reason
