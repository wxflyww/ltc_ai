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


def test_seq1_warns_contract_number_missing_when_project_number_exists():
    header = _header()
    header.project_number = "YZLNN2025-G3-318-GXQT"

    items = check_seq1(header, OurPartyContext(role="卖方", name="我方公司"), _preset())

    assert [item.result for item in items] == ["WARN"]
    assert "合同编号缺失" in items[0].reason
    assert "首页存在项目编号：YZLNN2025-G3-318-GXQT" in items[0].reason
    assert "请人工确认是否需要补充合同编号" in items[0].reason


def test_seq1_warns_when_contract_number_equals_project_number():
    header = _header()
    header.contract_number = "YZLNN2025-G3-318-GXQT"
    header.project_number = "YZLNN2025-G3-318-GXQT"

    items = check_seq1(header, OurPartyContext(role="卖方", name="我方公司"), _preset())

    assert [item.result for item in items] == ["WARN"]
    assert "合同编号疑似使用项目编号" in items[0].reason
    assert "YZLNN2025-G3-318-GXQT" in items[0].reason


def test_seq1_fails_when_preset_unavailable():
    items = check_seq1(_header(), None, None)
    assert items[0].result == "FAIL"
    assert "无法校验我方签署主体名称" in items[0].reason


def test_seq1_uses_project_name_when_contract_title_is_generic():
    header = HeaderInfo(
        contract_name="合同",
        project_name="广西壮族自治区渐进式延迟法定退休年龄养老保险和社会保险费统模式信息系统建设",
        contract_number="HT-1",
        signing_location="南宁",
        signing_date="2026年7月9日",
        parties=[ContractParty(role="乙方", name="我方公司")],
    )
    items = check_seq1(header, OurPartyContext(role="乙方", name="我方公司"), _preset())
    assert all("合同名称缺失" not in (item.reason or "") for item in items)


def test_seq1_reports_no_candidate_when_party_extraction_misses_supplier():
    header = HeaderInfo(
        contract_name="测试合同",
        contract_number="HT-1",
        signing_location="南宁",
        signing_date="2026年7月9日",
        parties=[ContractParty(role="甲方", name="客户公司")],
    )
    items = check_seq1(header, None, None, candidate_names=[], preset_configured=True)
    assert items[0].result == "FAIL"
    assert "未提取到我方候选主体" in items[0].reason


def test_seq1_reports_candidate_names_when_preset_lookup_misses():
    items = check_seq1(
        _header(),
        None,
        None,
        candidate_names=["东软集团股份有限公司"],
        preset_configured=True,
    )
    assert items[0].result == "FAIL"
    assert "已提取我方候选主体：东软集团股份有限公司" in items[0].reason
    assert "签署地预设值接口未命中" in items[0].reason


def test_seq1_reports_preset_service_not_configured():
    items = check_seq1(
        _header(),
        None,
        None,
        candidate_names=["东软集团股份有限公司"],
        preset_configured=False,
    )
    assert items[0].result == "FAIL"
    assert "签署地预设值服务未配置" in items[0].reason


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


def _amount_payment_result(**overrides):
    a3_result = {
        "currency": "人民币",
        "payment_method": "电汇",
        "total_amount_numeric": "924528.30",
        "total_amount_uppercase": "人民币玖拾贰万肆仟伍佰贰拾捌元叁角",
        "payment_stages": [],
    }
    full_text = "合同总价为924528.30元，大写：人民币玖拾贰万肆仟伍佰贰拾捌元叁角。"
    use_sanitize = bool(overrides.pop("_use_sanitize", False))
    a3_result.update(overrides)
    if "_full_text" in a3_result:
        full_text = str(a3_result.pop("_full_text"))
    for pair in a3_result.get("amount_pairs") or []:
        pair.setdefault("amount_evidence", f"合同中明确金额：{pair.get('amount_numeric')}元，大写：{pair.get('amount_uppercase')}。")
    for stage in a3_result.get("payment_stages") or []:
        stage.setdefault("amount_evidence", f"合同中明确付款阶段金额：{stage.get('amount_numeric')}元，大写：{stage.get('amount_uppercase')}。")
    a3_result.setdefault("total_amount_evidence", "合同总价为924528.30元，大写：人民币玖拾贰万肆仟伍佰贰拾捌元叁角。")
    a3_result.setdefault("contract_overall_evidence", "合同总价为924528.30元，大写：人民币玖拾贰万肆仟伍佰贰拾捌元叁角。")
    if use_sanitize:
        from app.capabilities.contract_review.amounts import sanitize_amount_payment_facts

        a3_result = sanitize_amount_payment_facts(a3_result, full_text)
    return next(item for item in check_amount_payment(a3_result) if item.id == "序号7")


def test_seq7_fails_when_model_reports_invalid_uppercase_amount_as_match():
    item = _amount_payment_result(
        total_amount_uppercase="人民币玖拾贰万肆仟伍佰贰拾捌点叁圆",
        total_amount_match=True,
    )

    assert item.result == "FAIL"
    assert item.block_level == "硬阻断"
    assert "金额单位错误" in item.reason
    assert "小数书写错误" in item.reason
    assert "人民币玖拾贰万肆仟伍佰贰拾捌点叁圆" in item.reason
    assert "玖拾贰万肆仟伍佰贰拾捌元叁角" in item.reason


def test_seq7_passes_for_correct_uppercase_without_model_boolean():
    item = _amount_payment_result()

    assert item.result == "PASS"
    assert item.block_level == "通过"


def test_seq7_uses_server_result_when_model_reports_false():
    item = _amount_payment_result(total_amount_match=False)

    assert item.result == "PASS"


def test_seq7_fails_when_uppercase_omits_jiao():
    item = _amount_payment_result(total_amount_uppercase="人民币玖拾贰万肆仟伍佰贰拾捌元整")

    assert item.result == "FAIL"
    assert "实际大写金额" in item.reason
    assert "期望大写金额" in item.reason


def test_seq7_fails_for_yuan_character_without_normalizing_it():
    item = _amount_payment_result(total_amount_uppercase="人民币玖拾贰万肆仟伍佰贰拾捌圆叁角")

    assert item.result == "FAIL"
    assert "金额单位错误" in item.reason
    assert "圆叁角" in item.reason


def test_seq7_checks_every_amount_pair_and_reports_all_mismatches():
    item = _amount_payment_result(
        total_amount_numeric=None,
        total_amount_uppercase=None,
        amount_pairs=[
            {
                "label": "谈判不含税报价",
                "amount_numeric": "924528.30",
                "amount_uppercase": "人民币玖拾贰万肆仟伍佰贰拾捌点叁圆",
            },
            {
                "label": "谈判含税报价",
                "amount_numeric": "980000",
                "amount_uppercase": "人民币玖拾捌万圆元",
            },
        ],
    )

    assert item.result == "FAIL"
    assert item.block_level == "硬阻断"
    assert "谈判不含税报价" in item.reason
    assert "谈判含税报价" in item.reason
    assert "玖拾贰万肆仟伍佰贰拾捌元叁角" in item.reason
    assert "玖拾捌万元整" in item.reason


def test_seq7_classifies_unit_and_decimal_errors_separately():
    item = _amount_payment_result(
        amount_pairs=[
            {
                "label": "谈判不含税报价",
                "amount_numeric": "924528.30",
                "amount_uppercase": "人民币玖拾贰万肆仟伍佰贰拾捌点叁圆",
            },
        ],
    )

    assert item.result == "FAIL"
    assert "金额单位错误" in item.reason
    assert "小数书写错误" in item.reason


def test_seq7_does_not_deduplicate_same_amount_at_different_business_positions():
    item = _amount_payment_result(
        total_amount_numeric=None,
        total_amount_uppercase=None,
        amount_pairs=[
            {
                "label": "报价一",
                "amount_numeric": "100",
                "amount_uppercase": "壹佰圆整",
                "amount_evidence": "报价一为100元，大写壹佰圆整。",
            },
            {
                "label": "报价二",
                "amount_numeric": "100",
                "amount_uppercase": "壹佰圆整",
                "amount_evidence": "报价二为100元，大写壹佰圆整。",
            },
        ],
    )

    assert item.result == "FAIL"
    assert "报价一" in item.reason
    assert "报价二" in item.reason


def test_seq7_reconciles_legacy_total_fields_with_the_same_amount_pair_source():
    evidence = "合同总金额（大写）人民币壹佰圆整（¥100.00）。"
    item = _amount_payment_result(
        _use_sanitize=True,
        _full_text=evidence,
        total_amount_numeric="100.00",
        total_amount_uppercase="人民币壹佰圆整",
        total_amount_evidence=evidence,
        amount_pairs=[
            {
                "label": "合同总金额",
                "amount_numeric": "100.00",
                "amount_uppercase": "人民币壹佰圆整",
                "amount_evidence": evidence,
            },
        ],
    )

    assert item.result == "FAIL"
    assert item.reason.count("大写金额不一致") == 1
    assert "合同总金额" in item.reason
    assert "合同总价大写金额不一致" not in item.reason


def test_seq7_deduplicates_amount_pairs_aliases_with_same_single_source_location():
    shared_evidence = "合同总金额（大写）人民币壹佰圆整（¥100.00）。"
    item = _amount_payment_result(
        _use_sanitize=True,
        _full_text=shared_evidence,
        total_amount_numeric=None,
        total_amount_uppercase=None,
        amount_pairs=[
            {
                "label": "合同总金额",
                "amount_numeric": "100.00",
                "amount_uppercase": "人民币壹佰圆整",
                "amount_evidence": shared_evidence,
            },
            {
                "label": "合同总价",
                "amount_numeric": "100.00",
                "amount_uppercase": "人民币壹佰圆整",
                "amount_evidence": shared_evidence,
            },
        ],
    )

    assert item.result == "FAIL"
    assert item.reason.count("大写金额不一致") == 1
    assert "合同总金额" in item.reason
    assert "合同总价大写金额不一致" not in item.reason


def test_seq7_keeps_two_business_positions_when_shared_evidence_spans_both_locations():
    shared_evidence = "第一期金额100元（大写：壹佰圆整）；第二期金额100元（大写：壹佰圆整）。"
    item = _amount_payment_result(
        _use_sanitize=True,
        _full_text=shared_evidence,
        total_amount_numeric=None,
        total_amount_uppercase=None,
        amount_pairs=[
            {
                "label": "第一期",
                "amount_numeric": "100",
                "amount_uppercase": "人民币壹佰圆整",
                "amount_evidence": shared_evidence,
            },
        ],
        payment_stages=[
            {
                "stage_name": "第二期",
                "percentage": "50",
                "amount_numeric": "100",
                "amount_uppercase": "人民币壹佰圆整",
                "amount_evidence": shared_evidence,
            }
        ],
    )

    assert item.result == "FAIL"
    assert "第一期" in item.reason
    assert "付款阶段（第二期）" in item.reason
    assert item.reason.count("大写金额不一致") == 2


def test_seq7_passes_when_all_amount_pairs_are_correct():
    item = _amount_payment_result(
        amount_pairs=[
            {"label": "谈判不含税报价", "amount_numeric": "924528.30", "amount_uppercase": "玖拾贰万肆仟伍佰贰拾捌元叁角"},
            {"label": "谈判含税报价", "amount_numeric": "980000", "amount_uppercase": "人民币玖拾捌万元整"},
        ],
    )

    assert item.result == "PASS"
    assert item.block_level == "通过"


def test_seq7_checks_payment_stage_amount_pairs():
    item = _amount_payment_result(
        payment_stages=[
            {"stage_name": "首付款", "percentage": "100", "amount_numeric": "924528.30", "amount_uppercase": "玖拾贰万肆仟伍佰贰拾捌点叁圆"},
        ],
    )

    assert item.result == "FAIL"
    assert "首付款" in item.reason
    assert "玖拾贰万肆仟伍佰贰拾捌元叁角" in item.reason


def test_seq7_fails_when_amount_facts_are_missing():
    numeric_missing = _amount_payment_result(total_amount_numeric=None)
    uppercase_missing = _amount_payment_result(total_amount_uppercase=None)
    both_missing = _amount_payment_result(total_amount_numeric=None, total_amount_uppercase=None)

    assert numeric_missing.result == "WARN"
    assert uppercase_missing.result == "WARN"
    assert "合同总金额没有对应的数字金额" in numeric_missing.reason
    assert "合同总金额没有对应的大写金额" in uppercase_missing.reason
    assert both_missing.result == "FAIL"
    assert "合同没有明确总金额" in both_missing.reason
    assert "PDF" not in numeric_missing.reason
    assert "解析文本断裂" not in numeric_missing.reason


def test_seq7_fails_for_unreliable_numeric_amounts():
    for numeric_amount in ("not-a-number", "-1", "NaN", "Infinity", "1.001"):
        item = _amount_payment_result(total_amount_numeric=numeric_amount)

        assert item.result == "FAIL"
        assert item.block_level == "硬阻断"
        assert "格式无法可靠校验" in item.reason


def test_seq7_uses_recovered_overall_amount_and_fails_on_wrong_uppercase():
    evidence = "合同总金额为4690000元，人民币（大写）肆佰陆拾玖万圆整。"
    item = _amount_payment_result(
        _use_sanitize=True,
        _full_text=evidence,
        total_amount_numeric=None,
        total_amount_uppercase=None,
        total_amount_evidence=None,
        contract_overall_evidence=evidence,
    )

    assert item.result == "FAIL"
    assert item.block_level == "硬阻断"
    assert "肆佰陆拾玖万圆整" in item.reason
    assert "肆佰陆拾玖万元整" in item.reason
    assert "金额单位错误" in item.reason


def test_seq7_passes_when_recovered_overall_amount_is_correct():
    evidence = "合同总金额为4690000元，人民币（大写）肆佰陆拾玖万元整。"
    item = _amount_payment_result(
        _use_sanitize=True,
        _full_text=evidence,
        total_amount_numeric=None,
        total_amount_uppercase=None,
        total_amount_evidence=None,
        contract_overall_evidence=evidence,
    )

    assert item.result == "PASS"
    assert item.block_level == "通过"


def test_seq7_warns_when_overall_has_only_numeric_amount():
    evidence = "合同总金额为4690000元。"
    item = _amount_payment_result(
        _use_sanitize=True,
        _full_text=evidence,
        total_amount_numeric="4690000",
        total_amount_uppercase=None,
        total_amount_evidence=evidence,
        contract_overall_evidence=evidence,
    )

    assert item.result == "WARN"
    assert item.block_level == "提示"
    assert "合同总金额没有对应的大写金额" in item.reason


def test_seq7_warns_when_overall_has_only_uppercase_amount():
    evidence = "合同总金额（大写）肆佰陆拾玖万元整。"
    item = _amount_payment_result(
        _use_sanitize=True,
        _full_text=evidence,
        total_amount_numeric=None,
        total_amount_uppercase="肆佰陆拾玖万元整",
        total_amount_evidence=evidence,
        contract_overall_evidence=evidence,
    )

    assert item.result == "WARN"
    assert item.block_level == "提示"
    assert "合同总金额没有对应的数字金额" in item.reason


def test_seq7_warns_when_amount_pair_has_only_numeric_amount():
    overall_evidence = "合同总金额为4690000元，人民币（大写）肆佰陆拾玖万元整。"
    evidence = "谈判含税报价4690000元。"
    item = _amount_payment_result(
        _use_sanitize=True,
        _full_text=overall_evidence + evidence,
        total_amount_numeric="4690000",
        total_amount_uppercase="肆佰陆拾玖万元整",
        total_amount_evidence=overall_evidence,
        contract_overall_evidence=overall_evidence,
        amount_pairs=[
            {
                "label": "谈判含税报价",
                "amount_numeric": "4690000",
                "amount_uppercase": None,
                "amount_evidence": evidence,
            }
        ],
    )

    assert item.result == "WARN"
    assert item.block_level == "提示"
    assert "谈判含税报价没有对应的大写金额" in item.reason


def test_seq7_warns_when_amount_pair_has_only_uppercase_amount():
    overall_evidence = "合同总金额为4690000元，人民币（大写）肆佰陆拾玖万元整。"
    evidence = "谈判含税报价（大写）肆佰陆拾玖万元整。"
    item = _amount_payment_result(
        _use_sanitize=True,
        _full_text=overall_evidence + evidence,
        total_amount_numeric="4690000",
        total_amount_uppercase="肆佰陆拾玖万元整",
        total_amount_evidence=overall_evidence,
        contract_overall_evidence=overall_evidence,
        amount_pairs=[
            {
                "label": "谈判含税报价",
                "amount_numeric": None,
                "amount_uppercase": "肆佰陆拾玖万元整",
                "amount_evidence": evidence,
            }
        ],
    )

    assert item.result == "WARN"
    assert item.block_level == "提示"
    assert "谈判含税报价没有对应的数字金额" in item.reason


def test_seq7_warns_when_stage_has_only_numeric_amount():
    overall_evidence = "合同总金额为4690000元，人民币（大写）肆佰陆拾玖万元整。"
    evidence = "首付款金额为4690000元。"
    item = _amount_payment_result(
        _use_sanitize=True,
        _full_text=overall_evidence + evidence,
        total_amount_numeric="4690000",
        total_amount_uppercase="肆佰陆拾玖万元整",
        total_amount_evidence=overall_evidence,
        contract_overall_evidence=overall_evidence,
        payment_stages=[
            {
                "stage_name": "首付款",
                "percentage": "100",
                "amount_numeric": "4690000",
                "amount_uppercase": None,
                "amount_evidence": evidence,
            }
        ],
    )

    assert item.result == "WARN"
    assert item.block_level == "提示"
    assert "付款阶段（首付款）没有对应的大写金额" in item.reason


def test_seq7_warns_when_stage_has_only_uppercase_amount():
    overall_evidence = "合同总金额为4690000元，人民币（大写）肆佰陆拾玖万元整。"
    evidence = "首付款金额（大写）肆佰陆拾玖万元整。"
    item = _amount_payment_result(
        _use_sanitize=True,
        _full_text=overall_evidence + evidence,
        total_amount_numeric="4690000",
        total_amount_uppercase="肆佰陆拾玖万元整",
        total_amount_evidence=overall_evidence,
        contract_overall_evidence=overall_evidence,
        payment_stages=[
            {
                "stage_name": "首付款",
                "percentage": "100",
                "amount_numeric": None,
                "amount_uppercase": "肆佰陆拾玖万元整",
                "amount_evidence": evidence,
            }
        ],
    )

    assert item.result == "WARN"
    assert item.block_level == "提示"
    assert "付款阶段（首付款）没有对应的数字金额" in item.reason


def test_seq7_fails_when_no_overall_amount_and_quote_is_not_labeled_total():
    evidence = "谈判含税报价4690000元（大写：肆佰陆拾玖万元整）。"
    item = _amount_payment_result(
        _use_sanitize=True,
        _full_text=evidence,
        total_amount_numeric=None,
        total_amount_uppercase=None,
        total_amount_evidence=None,
        contract_overall_evidence=None,
        amount_pairs=[
            {
                "label": "谈判含税报价",
                "amount_numeric": "4690000",
                "amount_uppercase": "肆佰陆拾玖万元整",
                "amount_evidence": evidence,
            }
        ],
    )

    assert item.result == "FAIL"
    assert item.block_level == "硬阻断"
    assert "合同没有明确总金额" in item.reason
    assert "谈判含税报价" not in item.reason
    assert "合同总价" not in item.reason


def test_seq7_aggregates_fail_over_warn():
    evidence = "合同总金额为4690000元。"
    quote_evidence = "谈判含税报价4690000元（大写：肆佰陆拾玖万圆整）。"
    item = _amount_payment_result(
        _use_sanitize=True,
        _full_text=evidence + quote_evidence,
        total_amount_numeric="4690000",
        total_amount_uppercase=None,
        total_amount_evidence=evidence,
        contract_overall_evidence=evidence,
        amount_pairs=[
            {
                "label": "谈判含税报价",
                "amount_numeric": "4690000",
                "amount_uppercase": "肆佰陆拾玖万圆整",
                "amount_evidence": quote_evidence,
            }
        ],
    )

    assert item.result == "FAIL"
    assert item.block_level == "硬阻断"
    assert "谈判含税报价" in item.reason


# ---- Regression: recovery is private (seq7-only), seq10/B-4 must not consume it ----

def test_seq10_does_not_consume_recovered_total_amount():
    """Recovery value must not leak to seq10's total comparison."""
    evidence = "合同总金额为4690000元，人民币（大写）肆佰陆拾玖万元整。"
    a3_result = {
        "currency": "人民币",
        "payment_method": "电汇",
        "total_amount_numeric": None,
        "total_amount_uppercase": None,
        "total_amount_evidence": None,
        "contract_overall_evidence": evidence,
        "payment_stages": [
            {"stage_name": "首付款", "percentage": "100", "amount_numeric": "4690000", "amount_uppercase": "肆佰陆拾玖万元整", "amount_evidence": evidence},
        ],
    }
    from app.capabilities.contract_review.amounts import sanitize_amount_payment_facts

    sanitized = sanitize_amount_payment_facts(a3_result, evidence)
    items = check_amount_payment(sanitized)

    seq7 = next(item for item in items if item.id == "序号7")
    seq10 = next(item for item in items if item.id == "序号10")

    # seq7 uses the private recovered candidate
    assert seq7.result == "PASS"
    # seq10 must NOT consume the recovered total (shared total_amount_numeric is None)
    # Stage is complete (100%, amount present) and no shared total → seq10 PASS, no total comparison
    assert seq10.result == "PASS"
    assert "与合同总价" not in (seq10.reason or "")


def test_seq10_does_not_compare_stage_sum_against_recovered_total():
    """Even when stage sum differs from recovered total, seq10 must not flag it (no shared total)."""
    evidence = "合同总金额为4690000元，人民币（大写）肆佰陆拾玖万元整。"
    stage_evidence = "首付款金额999999元，大写玖拾玖万玖仟玖佰玖拾玖元整。"
    full_text = evidence + stage_evidence
    a3_result = {
        "currency": "人民币",
        "payment_method": "电汇",
        "total_amount_numeric": None,
        "total_amount_uppercase": None,
        "total_amount_evidence": None,
        "contract_overall_evidence": evidence,
        "payment_stages": [
            {"stage_name": "首付款", "percentage": "100", "amount_numeric": "999999", "amount_uppercase": "玖拾玖万玖仟玖佰玖拾玖元整", "amount_evidence": stage_evidence},
        ],
    }
    from app.capabilities.contract_review.amounts import sanitize_amount_payment_facts

    sanitized = sanitize_amount_payment_facts(a3_result, full_text)
    items = check_amount_payment(sanitized)

    seq10 = next(item for item in items if item.id == "序号10")

    # Stage sum (999999) differs from recovered total (4690000), but seq10 must NOT compare
    # because shared total_amount_numeric is None (recovery is private to seq7)
    assert seq10.result == "PASS"
    assert "与合同总价" not in (seq10.reason or "")


def test_seq7_uses_recovered_candidate_but_shared_total_stays_empty():
    """seq7 can validate the private recovered candidate while shared total fields remain empty."""
    evidence = "合同总金额为4690000元，人民币（大写）肆佰陆拾玖万圆整。"
    a3_result = {
        "currency": "人民币",
        "payment_method": "电汇",
        "total_amount_numeric": None,
        "total_amount_uppercase": None,
        "total_amount_evidence": None,
        "contract_overall_evidence": evidence,
        "payment_stages": [],
    }
    from app.capabilities.contract_review.amounts import sanitize_amount_payment_facts

    sanitized = sanitize_amount_payment_facts(a3_result, evidence)
    items = check_amount_payment(sanitized)

    seq7 = next(item for item in items if item.id == "序号7")

    # Shared fields stay empty (no leak)
    assert sanitized["total_amount_numeric"] is None
    assert sanitized["total_amount_uppercase"] is None
    assert sanitized["total_amount_evidence"] is None
    assert sanitized["_amount_source_keys"]["total"] is None
    # seq7 still validates the private recovered candidate (wrong uppercase → FAIL)
    assert seq7.result == "FAIL"
    assert "肆佰陆拾玖万圆整" in seq7.reason
