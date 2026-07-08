from app.capabilities.contract_review.schemas import CheckItem, ContractReviewData


def build_check_items(
    item_id: str,
    item_name: str,
    hard_reasons: list[str],
    warn_reasons: list[str],
) -> list[CheckItem]:
    items: list[CheckItem] = []
    if hard_reasons:
        items.append(CheckItem(
            id=item_id,
            name=item_name,
            result="FAIL",
            block_level="硬阻断",
            reason="；".join(hard_reasons),
        ))
    if warn_reasons:
        items.append(CheckItem(
            id=item_id,
            name=item_name,
            result="WARN",
            block_level="提示",
            reason="；".join(warn_reasons),
        ))
    if not items:
        items.append(CheckItem(
            id=item_id,
            name=item_name,
            result="PASS",
            block_level="通过",
            reason=None,
        ))
    return items


def build_review_data(check_time: str, *check_lists) -> ContractReviewData:
    checks: list[CheckItem] = []
    for item in check_lists:
        if isinstance(item, list):
            checks.extend(item)
        else:
            checks.append(item)
    overall = (
        "BLOCK"
        if any(item.result == "FAIL" and item.block_level == "硬阻断" for item in checks)
        else "PASS"
    )
    return ContractReviewData(overall_result=overall, check_time=check_time, checks=checks)
