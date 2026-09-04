import math

import pytest

from app.capabilities.contract_review.amounts import format_rmb_uppercase, sanitize_amount_payment_facts


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "零元整"),
        (100, "壹佰元整"),
        (1001, "壹仟零壹元整"),
        (924528.30, "玖拾贰万肆仟伍佰贰拾捌元叁角"),
        (1000001.01, "壹佰万零壹元零壹分"),
        (-1, None),
        ("1.001", None),
        ("不是金额", None),
        (math.nan, None),
        (math.inf, None),
    ],
)
def test_format_rmb_uppercase(value, expected):
    assert format_rmb_uppercase(value) == expected


def test_sanitize_amount_payment_facts_keeps_explicit_amounts_with_normalized_evidence():
    a3_result = {
        "total_amount_numeric": "1,000.00",
        "total_amount_uppercase": "壹仟元整",
        "total_amount_evidence": "总价：1,000.00 元，\n大写：壹仟元整。",
        "contract_overall_evidence": "本合同总价为1,000.00 元，\n大写：壹仟元整。",
        "amount_pairs": [],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, "本合同总价为1,000.00 元，\n大写：壹仟元整。")

    assert sanitized["total_amount_numeric"] == "1,000.00"
    assert sanitized["total_amount_uppercase"] == "壹仟元整"
    # total_amount_evidence must come from verified contract_overall_evidence, not model's evidence
    assert sanitized["total_amount_evidence"] == a3_result["contract_overall_evidence"]
    assert sanitized is not a3_result


def test_sanitize_amount_payment_facts_clears_unverified_stage_amounts_but_keeps_ratio():
    a3_result = {
        "total_amount_numeric": "1000",
        "total_amount_uppercase": "壹仟元整",
        "total_amount_evidence": "总价1000元，大写：壹仟元整。",
        "payment_stages": [
            {
                "stage_name": "首付",
                "percentage": "100",
                "amount_numeric": "1000",
                "amount_uppercase": "壹仟圆整",
                "amount_evidence": "模型根据比例计算出1000元，大写壹仟圆整。",
            }
        ],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, "合同总价1000元，大写：壹仟元整。付款比例100%。")
    stage = sanitized["payment_stages"][0]

    assert stage["stage_name"] == "首付"
    assert stage["percentage"] == "100"
    assert stage["amount_numeric"] is None
    assert stage["amount_uppercase"] is None
    assert stage["amount_evidence"] is None
    assert a3_result["payment_stages"][0]["amount_numeric"] == "1000"


def test_sanitize_amount_payment_facts_drops_unverified_amount_pairs():
    a3_result = {
        "amount_pairs": [
            {
                "label": "编造金额",
                "amount_numeric": "500",
                "amount_uppercase": "伍佰元整",
                "amount_evidence": "模型计算所得500元。",
            }
        ],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, "合同只写付款比例50%。")

    assert sanitized["amount_pairs"] == []


def test_sanitize_amount_payment_facts_keeps_verified_numeric_stage_without_uppercase():
    a3_result = {
        "payment_stages": [
            {
                "stage_name": "首付",
                "percentage": "100",
                "amount_numeric": "1000",
                "amount_uppercase": None,
                "amount_evidence": "首付款金额为1000元。",
            }
        ]
    }

    sanitized = sanitize_amount_payment_facts(a3_result, "首付款金额为1000元。付款比例100%。")
    stage = sanitized["payment_stages"][0]

    assert stage["amount_numeric"] == "1000"
    assert stage["amount_uppercase"] is None
    assert stage["amount_evidence"] == "首付款金额为1000元。"


def _sanitize_total_fact(numeric: str, uppercase: str, evidence: str, full_text: str) -> dict:
    a3_result = {
        "total_amount_numeric": numeric,
        "total_amount_uppercase": uppercase,
        "total_amount_evidence": evidence,
        "contract_overall_evidence": evidence,
        "amount_pairs": [],
        "payment_stages": [],
    }
    return sanitize_amount_payment_facts(a3_result, full_text)


def test_sanitize_amount_payment_facts_rejects_halfwidth_percent_token_as_amount():
    evidence = "付款比例50%，大写伍拾圆整。"

    sanitized = _sanitize_total_fact("50", "伍拾圆整", evidence, evidence)

    assert sanitized["total_amount_numeric"] is None
    assert sanitized["total_amount_uppercase"] is None
    assert sanitized["total_amount_evidence"] is None


def test_sanitize_amount_payment_facts_rejects_fullwidth_percent_token_as_amount():
    evidence = "付款比例50％，大写伍拾圆整。"

    sanitized = _sanitize_total_fact("50", "伍拾圆整", evidence, evidence)

    assert sanitized["total_amount_numeric"] is None
    assert sanitized["total_amount_uppercase"] is None
    assert sanitized["total_amount_evidence"] is None


def test_sanitize_amount_payment_facts_rejects_baifenzhi_token_as_amount():
    evidence = "付款比例百分之50，大写伍拾圆整。"

    sanitized = _sanitize_total_fact("50", "伍拾圆整", evidence, evidence)

    assert sanitized["total_amount_numeric"] is None
    assert sanitized["total_amount_uppercase"] is None
    assert sanitized["total_amount_evidence"] is None


def test_sanitize_amount_payment_facts_does_not_match_100_inside_1000():
    evidence = "合同总金额为1000元，大写壹仟圆整。"

    sanitized = _sanitize_total_fact("100", "壹仟圆整", evidence, evidence)

    # numeric "100" does not match "1000" in evidence → single-sided uppercase in shared fields
    assert sanitized["total_amount_numeric"] is None
    assert sanitized["total_amount_uppercase"] == "壹仟圆整"
    assert sanitized["total_amount_evidence"] == evidence
    # Recovery extracts the true "1000" as a PRIVATE seq7 candidate, not shared
    assert sanitized["_recovered_total"]["numeric"] == "1000"
    assert sanitized["_recovered_total"]["uppercase"] == "壹仟圆整"


def test_sanitize_amount_payment_facts_keeps_normal_100_yuan_amount_token():
    evidence = "合同总金额为100元，大写壹佰圆整。"

    sanitized = _sanitize_total_fact("100", "壹佰圆整", evidence, evidence)

    assert sanitized["total_amount_numeric"] == "100"
    assert sanitized["total_amount_uppercase"] == "壹佰圆整"
    assert sanitized["total_amount_evidence"] == evidence


def test_sanitize_rejects_negotiated_tax_inclusive_quote_as_overall_evidence():
    evidence = "谈判含税报价为1,000.00元（大写：壹仟元整）。"
    a3_result = {
        "total_amount_numeric": "1,000.00",
        "total_amount_uppercase": "壹仟元整",
        "total_amount_evidence": evidence,
        "contract_overall_evidence": evidence,
        "amount_pairs": [],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, evidence)

    assert sanitized["total_amount_numeric"] is None
    assert sanitized["total_amount_uppercase"] is None
    assert sanitized["total_amount_evidence"] is None
    assert sanitized["_amount_source_keys"]["total"] is None


@pytest.mark.parametrize("numeric", ["1,000.00", "1，000.00"])
def test_sanitize_recovers_overall_amount_with_thousand_separators(numeric):
    evidence = f"合同整体金额为{numeric}元，人民币（大写）壹仟元整。"
    a3_result = {
        "total_amount_numeric": None,
        "total_amount_uppercase": None,
        "total_amount_evidence": None,
        "contract_overall_evidence": evidence,
        "amount_pairs": [],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, evidence)

    assert sanitized["_recovered_total"]["numeric"] == numeric
    assert sanitized["_recovered_total"]["uppercase"] == "壹仟元整"
    assert sanitized["_recovered_total"]["evidence"] == evidence
    assert sanitized["total_amount_numeric"] is None
    assert sanitized["total_amount_uppercase"] is None


def test_sanitize_amount_payment_facts_emits_source_keys_with_none_for_ambiguous_positions():
    full_text = "第一期金额100元（大写：壹佰圆整）；第二期金额100元（大写：壹佰圆整）。"
    shared_evidence = "第一期金额100元（大写：壹佰圆整）；第二期金额100元（大写：壹佰圆整）。"
    a3_result = {
        "total_amount_numeric": "100",
        "total_amount_uppercase": "人民币壹佰圆整",
        "total_amount_evidence": shared_evidence,
        "amount_pairs": [
            {
                "label": "第一期",
                "amount_numeric": "100",
                "amount_uppercase": "人民币壹佰圆整",
                "amount_evidence": shared_evidence,
            }
        ],
        "payment_stages": [
            {
                "stage_name": "第二期",
                "percentage": "50",
                "amount_numeric": "100",
                "amount_uppercase": "人民币壹佰圆整",
                "amount_evidence": shared_evidence,
            }
        ],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, full_text)

    assert "_amount_source_keys" in sanitized
    assert sanitized["_amount_source_keys"]["total"] is None
    assert sanitized["_amount_source_keys"]["amount_pairs"] == [None]
    assert sanitized["_amount_source_keys"]["payment_stages"] == [None]


# ---- Task 3/4: 有界整体金额证据守卫与恢复 ----

def _empty_total_a3():
    return {
        "total_amount_numeric": None,
        "total_amount_uppercase": None,
        "total_amount_evidence": None,
        "contract_overall_evidence": None,
        "amount_pairs": [],
        "payment_stages": [],
    }


def test_sanitize_clears_compat_total_without_overall_evidence():
    a3_result = {
        "total_amount_numeric": "4690000",
        "total_amount_uppercase": "肆佰陆拾玖万元整",
        "total_amount_evidence": "谈判含税报价4690000元（大写：肆佰陆拾玖万元整）。",
        "contract_overall_evidence": None,
        "amount_pairs": [],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, "谈判含税报价4690000元（大写：肆佰陆拾玖万元整）。")

    assert sanitized["total_amount_numeric"] is None
    assert sanitized["total_amount_uppercase"] is None
    assert sanitized["total_amount_evidence"] is None
    assert sanitized["_amount_source_keys"]["total"] is None


def test_sanitize_keeps_compat_total_when_overall_evidence_verified():
    evidence = "合同总金额为4690000元，人民币（大写）肆佰陆拾玖万元整。"
    a3_result = {
        "total_amount_numeric": "4690000",
        "total_amount_uppercase": "肆佰陆拾玖万元整",
        "total_amount_evidence": evidence,
        "contract_overall_evidence": evidence,
        "amount_pairs": [],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, evidence)

    assert sanitized["total_amount_numeric"] == "4690000"
    assert sanitized["total_amount_uppercase"] == "肆佰陆拾玖万元整"
    assert sanitized["_amount_source_keys"]["total"] is not None


def test_sanitize_clears_compat_total_when_overall_evidence_not_located():
    a3_result = {
        "total_amount_numeric": "4690000",
        "total_amount_uppercase": "肆佰陆拾玖万元整",
        "total_amount_evidence": "合同总金额为4690000元，大写肆佰陆拾玖万元整。",
        "contract_overall_evidence": "本合同整体对价为4690000元。",
        "amount_pairs": [],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, "合同总金额为4690000元，大写肆佰陆拾玖万元整。")

    assert sanitized["total_amount_numeric"] is None
    assert sanitized["total_amount_uppercase"] is None
    assert sanitized["total_amount_evidence"] is None


def test_sanitize_keeps_single_sided_numeric_overall_with_verified_evidence():
    evidence = "合同总金额为4690000元。"
    a3_result = {
        "total_amount_numeric": "4690000",
        "total_amount_uppercase": None,
        "total_amount_evidence": evidence,
        "contract_overall_evidence": evidence,
        "amount_pairs": [],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, evidence)

    assert sanitized["total_amount_numeric"] == "4690000"
    assert sanitized["total_amount_uppercase"] is None
    assert sanitized["_amount_source_keys"]["total"] is not None


def test_sanitize_keeps_single_sided_uppercase_overall_with_verified_evidence():
    evidence = "合同总金额（大写）肆佰陆拾玖万元整。"
    a3_result = {
        "total_amount_numeric": None,
        "total_amount_uppercase": "肆佰陆拾玖万元整",
        "total_amount_evidence": evidence,
        "contract_overall_evidence": evidence,
        "amount_pairs": [],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, evidence)

    assert sanitized["total_amount_numeric"] is None
    assert sanitized["total_amount_uppercase"] == "肆佰陆拾玖万元整"
    assert sanitized["_amount_source_keys"]["total"] is not None


def test_sanitize_keeps_single_sided_numeric_amount_pair():
    evidence = "谈判含税报价4690000元。"
    a3_result = {
        "amount_pairs": [
            {
                "label": "谈判含税报价",
                "amount_numeric": "4690000",
                "amount_uppercase": None,
                "amount_evidence": evidence,
            }
        ],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, evidence)

    assert sanitized["amount_pairs"][0]["amount_numeric"] == "4690000"
    assert sanitized["amount_pairs"][0]["amount_uppercase"] is None
    assert sanitized["_amount_source_keys"]["amount_pairs"] == [sanitized["_amount_source_keys"]["amount_pairs"][0]]


def test_sanitize_keeps_single_sided_uppercase_amount_pair():
    evidence = "谈判含税报价（大写）肆佰陆拾玖万元整。"
    a3_result = {
        "amount_pairs": [
            {
                "label": "谈判含税报价",
                "amount_numeric": None,
                "amount_uppercase": "肆佰陆拾玖万元整",
                "amount_evidence": evidence,
            }
        ],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, evidence)

    assert sanitized["amount_pairs"][0]["amount_numeric"] is None
    assert sanitized["amount_pairs"][0]["amount_uppercase"] == "肆佰陆拾玖万元整"


def test_sanitize_keeps_single_sided_numeric_stage_amount():
    evidence = "首付款金额为4690000元。"
    a3_result = {
        "payment_stages": [
            {
                "stage_name": "首付款",
                "percentage": "100",
                "amount_numeric": "4690000",
                "amount_uppercase": None,
                "amount_evidence": evidence,
            }
        ]
    }

    sanitized = sanitize_amount_payment_facts(a3_result, evidence)
    stage = sanitized["payment_stages"][0]

    assert stage["amount_numeric"] == "4690000"
    assert stage["amount_uppercase"] is None
    assert stage["amount_evidence"] == evidence


def test_sanitize_keeps_single_sided_uppercase_stage_amount():
    evidence = "首付款金额（大写）肆佰陆拾玖万元整。"
    a3_result = {
        "payment_stages": [
            {
                "stage_name": "首付款",
                "percentage": "100",
                "amount_numeric": None,
                "amount_uppercase": "肆佰陆拾玖万元整",
                "amount_evidence": evidence,
            }
        ]
    }

    sanitized = sanitize_amount_payment_facts(a3_result, evidence)
    stage = sanitized["payment_stages"][0]

    assert stage["amount_numeric"] is None
    assert stage["amount_uppercase"] == "肆佰陆拾玖万元整"
    assert stage["amount_evidence"] == evidence


def test_sanitize_recovers_overall_amount_from_bounded_evidence_when_no_full_pair():
    evidence = "合同总金额为4690000元，人民币（大写）肆佰陆拾玖万元整。"
    a3_result = {
        "total_amount_numeric": None,
        "total_amount_uppercase": None,
        "total_amount_evidence": None,
        "contract_overall_evidence": evidence,
        "amount_pairs": [],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, evidence)

    # Recovery is a PRIVATE seq7 candidate — must NOT leak to shared total_amount_* fields
    assert sanitized["total_amount_numeric"] is None
    assert sanitized["total_amount_uppercase"] is None
    assert sanitized["total_amount_evidence"] is None
    assert sanitized["_amount_source_keys"]["total"] is None
    # Private candidate available for seq7
    assert sanitized["_recovered_total"]["numeric"] == "4690000"
    assert sanitized["_recovered_total"]["uppercase"] == "肆佰陆拾玖万元整"
    assert sanitized["_recovered_total"]["evidence"] == evidence
    assert sanitized["_recovered_total"]["source_key"] is not None


def test_sanitize_recovers_overall_amount_preserving_wrong_uppercase():
    evidence = "合同总金额为4690000元，人民币（大写）肆佰陆拾玖万圆整。"
    a3_result = {
        "total_amount_numeric": None,
        "total_amount_uppercase": None,
        "total_amount_evidence": None,
        "contract_overall_evidence": evidence,
        "amount_pairs": [],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, evidence)

    # Recovery is a PRIVATE seq7 candidate — must NOT leak to shared total_amount_* fields
    assert sanitized["total_amount_numeric"] is None
    assert sanitized["total_amount_uppercase"] is None
    assert sanitized["total_amount_evidence"] is None
    assert sanitized["_amount_source_keys"]["total"] is None
    assert sanitized["_recovered_total"]["numeric"] == "4690000"
    assert sanitized["_recovered_total"]["uppercase"] == "肆佰陆拾玖万圆整"
    assert sanitized["_recovered_total"]["evidence"] == evidence


def test_sanitize_does_not_recover_overall_with_multiple_numeric_candidates():
    evidence = "合同总金额为4690000元，另含税980000元，大写肆佰陆拾玖万元整。"
    a3_result = {
        "total_amount_numeric": None,
        "total_amount_uppercase": None,
        "total_amount_evidence": None,
        "contract_overall_evidence": evidence,
        "amount_pairs": [],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, evidence)

    assert sanitized["total_amount_numeric"] is None
    assert sanitized["total_amount_uppercase"] is None
    assert sanitized["total_amount_evidence"] is None


def test_sanitize_does_not_recover_overall_with_multiple_uppercase_candidates():
    evidence = "合同总金额为4690000元，大写肆佰陆拾玖万元整、玖拾捌万元整。"
    a3_result = {
        "total_amount_numeric": None,
        "total_amount_uppercase": None,
        "total_amount_evidence": None,
        "contract_overall_evidence": evidence,
        "amount_pairs": [],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, evidence)

    assert sanitized["total_amount_numeric"] is None
    assert sanitized["total_amount_uppercase"] is None
    assert sanitized["total_amount_evidence"] is None


def test_sanitize_does_not_recover_overall_across_independent_text_blocks():
    evidence = "合同总金额为4690000元。\n\n人民币（大写）肆佰陆拾玖万元整。"
    a3_result = {
        "total_amount_numeric": None,
        "total_amount_uppercase": None,
        "total_amount_evidence": None,
        "contract_overall_evidence": evidence,
        "amount_pairs": [],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, evidence)

    assert sanitized["total_amount_numeric"] is None
    assert sanitized["total_amount_uppercase"] is None
    assert sanitized["total_amount_evidence"] is None


def test_sanitize_does_not_recover_overall_without_overall_evidence():
    full_text = "谈判含税报价4690000元（大写：肆佰陆拾玖万元整）。"
    a3_result = {
        "total_amount_numeric": None,
        "total_amount_uppercase": None,
        "total_amount_evidence": None,
        "contract_overall_evidence": None,
        "amount_pairs": [],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, full_text)

    assert sanitized["total_amount_numeric"] is None
    assert sanitized["total_amount_uppercase"] is None
    assert sanitized["total_amount_evidence"] is None


def test_sanitize_does_not_scan_full_text_for_overall_amount():
    full_text = "合同总金额为4690000元，人民币（大写）肆佰陆拾玖万元整。"
    a3_result = {
        "total_amount_numeric": None,
        "total_amount_uppercase": None,
        "total_amount_evidence": None,
        "contract_overall_evidence": None,
        "amount_pairs": [],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, full_text)

    assert sanitized["total_amount_numeric"] is None
    assert sanitized["total_amount_uppercase"] is None
    assert sanitized["total_amount_evidence"] is None


def test_sanitize_accepts_single_natural_line_break_in_bounded_evidence():
    evidence = "合同总金额为4690000元\n人民币（大写）肆佰陆拾玖万元整。"
    a3_result = {
        "total_amount_numeric": None,
        "total_amount_uppercase": None,
        "total_amount_evidence": None,
        "contract_overall_evidence": evidence,
        "amount_pairs": [],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, evidence)

    # Same fragment with one natural line break is accepted as a private seq7 candidate
    assert sanitized["total_amount_numeric"] is None
    assert sanitized["total_amount_uppercase"] is None
    assert sanitized["total_amount_evidence"] is None
    assert sanitized["_recovered_total"]["numeric"] == "4690000"
    assert sanitized["_recovered_total"]["uppercase"] == "肆佰陆拾玖万元整"
    assert sanitized["_recovered_total"]["evidence"] == evidence


def test_sanitize_keeps_model_fact_over_recovery_when_full_pair_present():
    model_evidence = "合同总金额4690000元（大写：肆佰陆拾玖万元整）。"
    a3_result = {
        "total_amount_numeric": "4690000",
        "total_amount_uppercase": "肆佰陆拾玖万元整",
        "total_amount_evidence": model_evidence,
        "contract_overall_evidence": model_evidence,
        "amount_pairs": [],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, model_evidence)

    # total_amount_evidence must come from verified contract_overall_evidence
    assert sanitized["total_amount_evidence"] == model_evidence
    assert sanitized["total_amount_numeric"] == "4690000"


# ---- Regression: paragraph-aware evidence location ----

def test_sanitize_rejects_cross_paragraph_evidence_flattened_by_model():
    """Model flattens cross-paragraph evidence into a single space; must be rejected."""
    full_text = "合同总金额为4690000元。\n\n人民币（大写）肆佰陆拾玖万元整。"
    model_evidence = "合同总金额为4690000元。 人民币（大写）肆佰陆拾玖万元整。"
    a3_result = {
        "total_amount_numeric": "4690000",
        "total_amount_uppercase": "肆佰陆拾玖万元整",
        "total_amount_evidence": model_evidence,
        "contract_overall_evidence": model_evidence,
        "amount_pairs": [],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, full_text)

    # Cross-paragraph evidence (model flattened \n\n to space) should be rejected
    assert sanitized["total_amount_numeric"] is None
    assert sanitized["total_amount_uppercase"] is None
    assert sanitized["total_amount_evidence"] is None


def test_sanitize_replaces_unverified_total_amount_evidence_with_overall_evidence():
    """Model provides unverified total_amount_evidence; must be replaced with verified contract_overall_evidence."""
    overall_evidence = "合同总金额为4690000元，\n大写：肆佰陆拾玖万元整。"
    model_evidence = "模型自己写的证据，不在原文中。"
    a3_result = {
        "total_amount_numeric": "4690000",
        "total_amount_uppercase": "肆佰陆拾玖万元整",
        "total_amount_evidence": model_evidence,
        "contract_overall_evidence": overall_evidence,
        "amount_pairs": [],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, overall_evidence)

    assert sanitized["total_amount_numeric"] == "4690000"
    assert sanitized["total_amount_uppercase"] == "肆佰陆拾玖万元整"
    # Evidence must come from verified contract_overall_evidence, not model's unverified evidence
    assert sanitized["total_amount_evidence"] == overall_evidence
    assert sanitized["total_amount_evidence"] != model_evidence


def test_sanitize_accepts_single_natural_line_break_in_overall_evidence():
    """Same fragment with one natural line break should still be accepted."""
    evidence = "合同总金额为4690000元，\n大写：肆佰陆拾玖万元整。"
    a3_result = {
        "total_amount_numeric": "4690000",
        "total_amount_uppercase": "肆佰陆拾玖万元整",
        "total_amount_evidence": evidence,
        "contract_overall_evidence": evidence,
        "amount_pairs": [],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, evidence)

    assert sanitized["total_amount_numeric"] == "4690000"
    assert sanitized["total_amount_uppercase"] == "肆佰陆拾玖万元整"
    assert sanitized["total_amount_evidence"] == evidence


# ---- Regression: paragraph boundary with horizontal whitespace (\n \n, \n\t\n) ----

def test_sanitize_rejects_cross_paragraph_evidence_with_space_blank_line():
    """Original has \\n \\n (blank line with a space); model flattens to single space; must reject."""
    full_text = "合同总金额为4690000元。\n \n人民币（大写）肆佰陆拾玖万元整。"
    model_evidence = "合同总金额为4690000元。 人民币（大写）肆佰陆拾玖万元整。"
    a3_result = {
        "total_amount_numeric": "4690000",
        "total_amount_uppercase": "肆佰陆拾玖万元整",
        "total_amount_evidence": model_evidence,
        "contract_overall_evidence": model_evidence,
        "amount_pairs": [],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, full_text)

    assert sanitized["total_amount_numeric"] is None
    assert sanitized["total_amount_uppercase"] is None
    assert sanitized["total_amount_evidence"] is None
    assert "_recovered_total" not in sanitized


def test_sanitize_rejects_cross_paragraph_evidence_with_tab_blank_line():
    """Original has \\n\\t\\n (blank line with a tab); model flattens to single space; must reject."""
    full_text = "合同总金额为4690000元。\n\t\n人民币（大写）肆佰陆拾玖万元整。"
    model_evidence = "合同总金额为4690000元。 人民币（大写）肆佰陆拾玖万元整。"
    a3_result = {
        "total_amount_numeric": "4690000",
        "total_amount_uppercase": "肆佰陆拾玖万元整",
        "total_amount_evidence": model_evidence,
        "contract_overall_evidence": model_evidence,
        "amount_pairs": [],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, full_text)

    assert sanitized["total_amount_numeric"] is None
    assert sanitized["total_amount_uppercase"] is None
    assert sanitized["total_amount_evidence"] is None
    assert "_recovered_total" not in sanitized


def test_sanitize_rejects_cross_paragraph_evidence_with_space_blank_line_recovery():
    """Original has \\n \\n; recovery must also reject cross-paragraph evidence."""
    full_text = "合同总金额为4690000元。\n \n人民币（大写）肆佰陆拾玖万元整。"
    model_evidence = "合同总金额为4690000元。 人民币（大写）肆佰陆拾玖万元整。"
    a3_result = {
        "total_amount_numeric": None,
        "total_amount_uppercase": None,
        "total_amount_evidence": None,
        "contract_overall_evidence": model_evidence,
        "amount_pairs": [],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, full_text)

    assert sanitized["total_amount_numeric"] is None
    assert sanitized["total_amount_uppercase"] is None
    assert sanitized["total_amount_evidence"] is None
    assert "_recovered_total" not in sanitized


# ---- Regression: recovery is private (seq7-only), never leaks to shared fields ----

def test_sanitize_recovery_does_not_leak_to_shared_total_fields():
    """Recovery must not write to shared total_amount_* or _amount_source_keys['total']."""
    evidence = "合同总金额为4690000元，人民币（大写）肆佰陆拾玖万元整。"
    a3_result = {
        "total_amount_numeric": None,
        "total_amount_uppercase": None,
        "total_amount_evidence": None,
        "contract_overall_evidence": evidence,
        "amount_pairs": [],
        "payment_stages": [],
    }

    sanitized = sanitize_amount_payment_facts(a3_result, evidence)

    assert sanitized["total_amount_numeric"] is None
    assert sanitized["total_amount_uppercase"] is None
    assert sanitized["total_amount_evidence"] is None
    assert sanitized["_amount_source_keys"]["total"] is None
    # Private candidate exists for seq7
    assert sanitized["_recovered_total"]["numeric"] == "4690000"
    assert sanitized["_recovered_total"]["uppercase"] == "肆佰陆拾玖万元整"
    assert sanitized["_recovered_total"]["evidence"] == evidence
    assert sanitized["_recovered_total"]["source_key"] is not None
