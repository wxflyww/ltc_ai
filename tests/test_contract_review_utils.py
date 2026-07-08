from datetime import date

from app.capabilities.contract_review.utils import (
    is_empty,
    mask_id_number,
    normalize_date,
    to_halfwidth,
)


def test_is_empty_handles_none_blank_and_string_null():
    assert is_empty(None)
    assert is_empty("")
    assert is_empty("   ")
    assert is_empty("null")
    assert not is_empty("0")


def test_to_halfwidth_converts_ascii_range_and_fullwidth_space():
    assert to_halfwidth("１２３：ＡＢＣ　x") == "123:ABC x"


def test_normalize_date_accepts_common_numeric_formats():
    assert normalize_date("2026年7月8日") == date(2026, 7, 8)
    assert normalize_date("2026-07-08") == date(2026, 7, 8)
    assert normalize_date("2026/7/8") == date(2026, 7, 8)
    assert normalize_date("2026.7.8") == date(2026, 7, 8)


def test_normalize_date_returns_none_for_unknown_or_invalid_dates():
    assert normalize_date(None) is None
    assert normalize_date("二〇二六年七月八日") is None
    assert normalize_date("2026-13-08") is None


def test_mask_id_number_uses_first_6_last_4():
    assert mask_id_number("210102197001010011") == "210102********0011"


def test_mask_id_number_masks_short_values_completely():
    assert mask_id_number("123456789") == "*********"
    assert mask_id_number(None) is None
