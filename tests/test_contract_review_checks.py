from app.capabilities.contract_review.checks import build_check_items, build_review_data
from app.capabilities.contract_review.schemas import CheckItem


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
