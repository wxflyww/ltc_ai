from datetime import date
from decimal import Decimal, InvalidOperation

from app.capabilities.contract_review.schemas import (
    HeaderInfo,
    OurPartyContext,
    SignatureInfo,
    SystemPreset,
)
from app.capabilities.contract_review.schemas import CheckItem, CheckMetric, ContractReviewData
from app.capabilities.contract_review.utils import is_empty, mask_id_number, normalize_date, to_halfwidth


NINE_FIELDS = {
    "legal_rep_name": "法定代表人/授权人",
    "bank_name": "开户银行",
    "bank_account": "银行账号",
    "account_holder": "账户名称",
    "address": "地址",
    "phone": "电话",
    "fax": "传真",
    "website": "网址",
    "postal_code": "邮编",
}

ACCOUNT_FIELDS = {"bank_name", "bank_account", "account_holder"}
GENERIC_CONTRACT_NAMES = {"合同", "合同书", "采购合同", "服务合同", "项目合同"}


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


def build_review_data(check_time: str, *check_lists, metrics: list[CheckMetric] | None = None) -> ContractReviewData:
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
    return ContractReviewData(overall_result=overall, check_time=check_time, checks=checks, metrics=metrics or [])


def check_seq1(
    header: HeaderInfo,
    our_party: OurPartyContext | None,
    preset: SystemPreset | None,
    candidate_names: list[str] | None = None,
    preset_configured: bool | None = None,
) -> list[CheckItem]:
    hard: list[str] = []
    warn: list[str] = []

    contract_name = (header.contract_name or "").strip()
    has_effective_contract_name = (
        not is_empty(contract_name)
        and contract_name not in GENERIC_CONTRACT_NAMES
    ) or not is_empty(header.project_name)
    if not has_effective_contract_name:
        hard.append("合同名称缺失")
    contract_number = (header.contract_number or "").strip()
    project_number = (header.project_number or "").strip()
    if is_empty(contract_number):
        if is_empty(project_number):
            warn.append("合同编号缺失")
        else:
            warn.append(f"合同编号缺失；首页存在项目编号：{project_number}，请人工确认是否需要补充合同编号")
    elif not is_empty(project_number) and to_halfwidth(contract_number) == to_halfwidth(project_number):
        warn.append(f"合同编号疑似使用项目编号：{project_number}，请人工确认是否需要补充合同编号")
    if is_empty(header.signing_location):
        warn.append("签订地点缺失")
    if is_empty(header.signing_date):
        warn.append("签订日期缺失")

    if our_party is None or preset is None:
        if preset_configured is False:
            hard.append("无法校验我方签署主体名称：签署地预设值服务未配置")
        elif candidate_names == []:
            hard.append("无法校验我方签署主体名称：未提取到我方候选主体")
        elif candidate_names:
            candidates = "、".join(candidate_names)
            hard.append(
                f"无法校验我方签署主体名称：已提取我方候选主体：{candidates}，"
                "但签署地预设值接口未命中"
            )
        else:
            hard.append("无法校验我方签署主体名称：未命中签署地预设值")
    elif to_halfwidth(our_party.name) != to_halfwidth(preset.entity_name):
        hard.append(f"我方签署主体名称（{our_party.name}）与系统预设值（{preset.entity_name}）不一致")

    if not header.parties:
        hard.append("合同首部签约方缺失")

    return build_check_items("序号1", "合同首页完整性", hard, warn)


def _same_value(field: str, actual: str | None, expected: str | None) -> bool:
    if field in {"bank_account", "phone", "fax", "postal_code"}:
        return to_halfwidth(actual) == to_halfwidth(expected)
    return (actual or "").strip() == (expected or "").strip()


def check_seq2_11(
    header: HeaderInfo,
    signature: SignatureInfo,
    our_party: OurPartyContext | None,
    preset: SystemPreset | None,
) -> tuple[list[CheckItem], list[CheckItem]]:
    hard: list[str] = []
    warn: list[str] = []
    account_hard: list[str] = []
    account_warn: list[str] = []

    if our_party is None or preset is None:
        hard.append("签署地预设数据不可用，无法校验签章页预设信息")
        account_hard.append("签署地预设数据不可用，无法校验账户信息")

    header_by_role = {p.role: p.name for p in header.parties if not is_empty(p.role)}
    sig_by_role = {p.role: p.name for p in signature.signature_parties if not is_empty(p.role)}
    for role, header_name in header_by_role.items():
        sig_name = sig_by_role.get(role)
        if is_empty(sig_name):
            warn.append(f"签章区块{role}名称缺失")
        elif sig_name != header_name:
            hard.append(f"签章区块{role}名称与首部{role}名称不一致")

    for field, label in NINE_FIELDS.items():
        value = getattr(signature, field)
        if is_empty(value):
            msg = f"{label}信息缺失或未填写"
            warn.append(msg)
            if field in ACCOUNT_FIELDS:
                account_warn.append(msg)
            continue
        if preset is None or our_party is None:
            continue
        if field == "legal_rep_name":
            authorized_names = [rep.name for rep in preset.authorized_reps if not is_empty(rep.name)]
            matched = value == preset.legal_rep_name or value in authorized_names
            display = f"法定代表人{preset.legal_rep_name}或授权人{authorized_names}"
        else:
            expected = getattr(preset, field)
            matched = _same_value(field, value, expected)
            display = expected
        if not matched:
            msg = f"{label}（{value}）与系统预设值（{display}）不一致"
            hard.append(msg)
            if field in ACCOUNT_FIELDS:
                account_hard.append(msg)

    if preset is not None and not is_empty(signature.legal_rep_name) and not is_empty(signature.signer_id_number):
        expected_id = None
        if signature.legal_rep_name == preset.legal_rep_name:
            expected_id = preset.legal_rep_id_number
        else:
            for rep in preset.authorized_reps:
                if rep.name == signature.legal_rep_name:
                    expected_id = rep.id_number
                    break
        if is_empty(expected_id):
            hard.append(f"我方法定代表人/授权人（{signature.legal_rep_name}）在合同中填写了身份证号，但系统无有效身份证号主数据可供验证")
        elif to_halfwidth(signature.signer_id_number) != to_halfwidth(expected_id):
            hard.append(f"我方法定代表人/授权人（{signature.legal_rep_name}）身份证号与系统预设值不一致，合同值{mask_id_number(signature.signer_id_number)}")
    elif is_empty(signature.legal_rep_name) and not is_empty(signature.signer_id_number):
        warn.append(f"合同出现我方法定代表人/授权人身份证号{mask_id_number(signature.signer_id_number)}，但没有对应姓名，无法验证身份证号正确性")

    return (
        build_check_items("序号2", "签章页完整性", hard, warn),
        build_check_items("序号11", "账户信息", account_hard, account_warn),
    )


def check_seq3(header: HeaderInfo, signature: SignatureInfo, our_party: OurPartyContext | None) -> CheckItem:
    if our_party is None:
        return CheckItem(id="序号3", name="签署日期", result="FAIL", block_level="硬阻断", reason="无法识别我方签署主体，无法校验我方签署日期")
    if is_empty(signature.signing_date):
        return CheckItem(id="序号3", name="签署日期", result="PASS", block_level="通过", reason="签章区块我方签署日期缺失，跳过校验")

    hard: list[str] = []
    sig_date = normalize_date(signature.signing_date)
    if sig_date is None:
        hard.append(f"签章区块我方签署日期（{signature.signing_date}）格式无法识别")
    else:
        header_date = normalize_date(header.signing_date)
        if header_date is not None and sig_date != header_date:
            hard.append(f"签章区块我方签署日期（{signature.signing_date}）与首部签订日期（{header.signing_date}）不一致")
        if sig_date < date.today():
            hard.append(f"签署日期（{signature.signing_date}）早于当前系统日期（{date.today().isoformat()}）")

    if hard:
        return CheckItem(id="序号3", name="签署日期", result="FAIL", block_level="硬阻断", reason="；".join(hard))
    return CheckItem(id="序号3", name="签署日期", result="PASS", block_level="通过", reason=None)


def _to_decimal(value) -> Decimal | None:
    if is_empty(value):
        return None
    text = str(value).replace(",", "").replace("，", "").replace("%", "").strip()
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _make_single_check(item_id: str, name: str, hard: list[str], warn: list[str]) -> CheckItem:
    if hard:
        return CheckItem(id=item_id, name=name, result="FAIL", block_level="硬阻断", reason="；".join(hard))
    if warn:
        return CheckItem(id=item_id, name=name, result="WARN", block_level="提示", reason="；".join(warn))
    return CheckItem(id=item_id, name=name, result="PASS", block_level="通过", reason=None)


def check_amount_payment(a3_result: dict) -> list[CheckItem]:
    total_numeric = _to_decimal(a3_result.get("total_amount_numeric"))
    total_uppercase = a3_result.get("total_amount_uppercase")
    amount_match = a3_result.get("total_amount_match")
    currency = a3_result.get("currency")
    payment_method = a3_result.get("payment_method")
    stages = a3_result.get("payment_stages") or []

    seq7_hard: list[str] = []
    if total_numeric is None or is_empty(total_uppercase):
        seq7_hard.append("合同总价金额或大写金额缺失，无法校验总价大小写一致性")
    elif amount_match is False:
        seq7_hard.append("合同总价大小写金额不一致")

    seq8_hard: list[str] = []
    if is_empty(currency):
        seq8_hard.append("币种缺失")

    seq9_hard: list[str] = []
    if is_empty(payment_method):
        seq9_hard.append("付款方式缺失")

    seq10_hard: list[str] = []
    seq10_warn: list[str] = []
    if not stages:
        seq10_warn.append("付款阶段不明确")
    else:
        percentages: list[Decimal] = []
        stage_amounts: list[Decimal] = []
        for index, stage in enumerate(stages, start=1):
            percentage = _to_decimal(stage.get("percentage"))
            amount = _to_decimal(stage.get("amount_numeric"))
            if percentage is None:
                seq10_warn.append(f"第{index}个付款阶段比例缺失或格式无法识别")
            else:
                percentages.append(percentage)
            if amount is None:
                seq10_warn.append(f"第{index}个付款阶段金额缺失或格式无法识别")
            else:
                stage_amounts.append(amount)

        if percentages and sum(percentages) != Decimal("100"):
            seq10_hard.append(f"付款阶段比例合计{sum(percentages)}%，不等于100%")
        if total_numeric is not None and stage_amounts and sum(stage_amounts) != total_numeric:
            seq10_hard.append(f"付款阶段金额合计{sum(stage_amounts)}，与合同总价{total_numeric}不一致")

    return [
        _make_single_check("序号7", "总价大小写一致性", seq7_hard, []),
        _make_single_check("序号8", "货币条款", seq8_hard, []),
        _make_single_check("序号9", "付款方式", seq9_hard, []),
        _make_single_check("序号10", "付款阶段校验", seq10_hard, seq10_warn),
    ]
