import re
from copy import deepcopy
from decimal import Decimal, InvalidOperation


_DIGITS = "零壹贰叁肆伍陆柒捌玖"
_SMALL_UNITS = ("", "拾", "佰", "仟")
_LARGE_UNITS = ("", "万", "亿")
_NUMERIC_TOKEN_WITH_SEP_PATTERN = re.compile(
    r"(?<![\d.])"
    r"\d+(?:[，,]\d{3})*"
    r"(?:\.\d+)?"
    r"(?![\d.%％])"
)
_PERCENT_PREFIX = "百分之"
_UPPERCASE_AMOUNT_PATTERN = re.compile(r"[零壹贰叁肆伍陆柒捌玖拾佰仟万亿元角分整圆点]+")
_CURRENCY_UNIT_SUFFIX = ("元", "圆")
_CURRENCY_PREFIX = ("￥", "¥")


def _format_group(group: int) -> str:
    parts: list[str] = []
    zero_pending = False
    for position in range(3, -1, -1):
        divisor = 10 ** position
        digit = group // divisor % 10
        if digit:
            if zero_pending:
                parts.append(_DIGITS[0])
                zero_pending = False
            parts.append(_DIGITS[digit])
            parts.append(_SMALL_UNITS[position])
        elif parts:
            zero_pending = True
    return "".join(parts)


def _format_integer(value: int) -> str:
    if value == 0:
        return _DIGITS[0]

    groups: list[int] = []
    while value:
        groups.append(value % 10_000)
        value //= 10_000
    if len(groups) > len(_LARGE_UNITS):
        return ""

    parts: list[str] = []
    zero_pending = False
    for index in range(len(groups) - 1, -1, -1):
        group = groups[index]
        if group == 0:
            zero_pending = bool(parts)
            continue
        if parts and (zero_pending or group < 1000):
            parts.append(_DIGITS[0])
        parts.append(_format_group(group))
        parts.append(_LARGE_UNITS[index])
        zero_pending = False
    return "".join(parts)


def format_rmb_uppercase(value) -> str | None:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None

    if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
        return None

    integer_amount = int(amount)
    if integer_amount >= 10 ** (4 * len(_LARGE_UNITS)):
        return None
    fractional_amount = int((amount - integer_amount) * 100)
    jiao, fen = divmod(fractional_amount, 10)

    result = f"{_format_integer(integer_amount)}元"
    if not jiao and not fen:
        return f"{result}整"
    if jiao:
        result += f"{_DIGITS[jiao]}角"
    elif integer_amount and fen:
        result += "零"
    if fen:
        result += f"{_DIGITS[fen]}分"
    return result


def _normalize_amount_text(value) -> str:
    """Flatten all whitespace — used for token-level normalization (comma removal, etc.)."""
    return "".join(str(value or "").split()).replace(",", "").replace("，", "")


def _normalize_paragraph_aware(text) -> str:
    """Normalize text while preserving paragraph boundaries.

    Within each paragraph: collapse runs of whitespace (spaces, tabs, single \\n) into single spaces.
    Between paragraphs: preserve \\n\\n as paragraph separators.
    Paragraph boundary: \\n followed by optional horizontal whitespace (spaces/tabs) then \\n.
    This ensures evidence matching cannot succeed across paragraph boundaries,
    even when the model flattens \\n \\n or \\n\\t\\n into a single space.
    """
    text = str(text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Split into paragraphs: \n followed by optional horizontal whitespace then \n+
    paragraphs = re.split(r"\n[ \t]*\n+", text)
    normalized_paragraphs = []
    for para in paragraphs:
        # Collapse all whitespace within paragraph to single spaces, strip
        normalized = re.sub(r"\s+", " ", para).strip()
        normalized_paragraphs.append(normalized)
    return "\n\n".join(normalized_paragraphs)



def _evidence_is_bounded(evidence) -> bool:
    text = str(evidence or "")
    if not text.strip():
        return False
    normalized = text.replace("\r\n", "\n")
    if "\n\n" in normalized:
        return False
    return normalized.count("\n") <= 1


# Keywords that indicate contract overall consideration (positive signals)
_OVERALL_AMOUNT_POSITIVE = (
    "合同总金额", "合同总价", "合同总价款", "合同总对价",
    "总金额", "总价款", "总对价", "总金额为", "总价为",
    "整体金额", "整体总价", "整体总价款",
    "本合同金额", "本合同总价", "本合同总价款",
)

# Keywords that indicate non-overall amounts (negative signals)
_OVERALL_AMOUNT_NEGATIVE = (
    "谈判", "报价", "含税报价", "不含税报价",
    "预估", "预算", "暂定",
    "付款比例", "付款阶段", "阶段合计",
    "首付款", "预付款", "进度款", "尾款",
    "保证金", "押金", "违约金",
    "数值相等", "等于", "合计",
)


def _is_overall_amount_evidence(evidence) -> bool:
    """Check if evidence semantically expresses the contract's overall consideration.

    Returns True if the evidence contains positive signals for overall amount
    and does NOT contain negative signals (negatives take precedence).
    """
    text = str(evidence or "").strip()
    if not text:
        return False
    # Negative signals take precedence — if any negative keyword is present, reject
    for keyword in _OVERALL_AMOUNT_NEGATIVE:
        if keyword in text:
            return False
    # Must contain at least one positive signal
    return any(keyword in text for keyword in _OVERALL_AMOUNT_POSITIVE)


def _normalize_thousand_separator(text: str) -> str:
    """Remove thousand separators (both English comma and Chinese full-width comma) from numeric text.

    Handles patterns like 1,000 | 1，000 | 1,000,000 | 1，000，000
    Only removes commas that are followed by exactly 3 digits (thousand separator pattern).
    """
    result = str(text or "")
    # Replace Chinese full-width comma with English comma first
    result = result.replace("，", ",")
    # Remove thousand separators: comma followed by exactly 3 digits (and optionally more groups)
    # Pattern: digit(s),ddd — remove the comma
    result = re.sub(r"\d,(?=\d{3}(?:\d{3})*(?:\.\d*)?$)", "", result)
    return result


def _iter_numeric_token_matches(text: str):
    for match in _NUMERIC_TOKEN_WITH_SEP_PATTERN.finditer(text):
        start, end = match.span()
        prefix_start = max(0, start - len(_PERCENT_PREFIX))
        if text[prefix_start:start] == _PERCENT_PREFIX:
            continue
        yield match.group(0), start, end


def _collect_numeric_tokens(text: str, numeric_value: Decimal) -> set[str]:
    tokens: set[str] = set()
    for token, _, _ in _iter_numeric_token_matches(text):
        try:
            token_value = Decimal(_normalize_amount_text(token))
        except (InvalidOperation, ValueError):
            continue
        if token_value == numeric_value:
            tokens.add(token)
    return tokens


def _uppercase_exists_in_text(text: str, uppercase: str) -> bool:
    normalized_uppercase = _normalize_amount_text(uppercase)
    if not normalized_uppercase:
        return False
    variants = [normalized_uppercase]
    if normalized_uppercase.startswith("人民币"):
        variants.append(normalized_uppercase.removeprefix("人民币"))
    return any(variant and variant in text for variant in variants)


def _amount_numeric_evidence_verified(numeric, evidence, full_text: str) -> bool:
    if not _evidence_is_bounded(evidence):
        return False
    normalized_evidence = _normalize_amount_text(evidence)
    if not normalized_evidence:
        return False
    # Use paragraph-aware normalization for evidence location check
    para_text = _normalize_paragraph_aware(full_text)
    para_evidence = _normalize_paragraph_aware(evidence)
    if para_evidence not in para_text:
        return False

    normalized_numeric = _normalize_amount_text(numeric)
    if not normalized_numeric:
        return False
    try:
        numeric_value = Decimal(normalized_numeric)
    except (InvalidOperation, TypeError, ValueError):
        return False
    return bool(_collect_numeric_tokens(normalized_evidence, numeric_value))


def _amount_fact_is_verified(numeric, uppercase, evidence, full_text: str) -> bool:
    if not _evidence_is_bounded(evidence):
        return False
    normalized_evidence = _normalize_amount_text(evidence)
    if not normalized_evidence:
        return False
    # Use paragraph-aware normalization for evidence location check
    para_text = _normalize_paragraph_aware(full_text)
    para_evidence = _normalize_paragraph_aware(evidence)
    if para_evidence not in para_text:
        return False

    normalized_numeric = _normalize_amount_text(numeric)
    if not normalized_numeric:
        return False
    try:
        numeric_value = Decimal(normalized_numeric)
    except (InvalidOperation, TypeError, ValueError):
        return False
    if not _collect_numeric_tokens(normalized_evidence, numeric_value):
        return False

    normalized_uppercase = _normalize_amount_text(uppercase)
    if not normalized_uppercase:
        return False
    return _uppercase_exists_in_text(normalized_evidence, normalized_uppercase)


def _find_all_occurrences(text: str, needle: str) -> list[tuple[int, int]]:
    if not needle:
        return []
    positions: list[tuple[int, int]] = []
    start = 0
    while True:
        index = text.find(needle, start)
        if index < 0:
            break
        positions.append((index, index + len(needle)))
        start = index + 1
    return positions


def _find_numeric_token_positions(text: str, numeric_value: Decimal) -> list[tuple[int, int]]:
    positions: list[tuple[int, int]] = []
    for token, start, end in _iter_numeric_token_matches(text):
        try:
            token_value = Decimal(_normalize_amount_text(token))
        except (InvalidOperation, ValueError):
            continue
        if token_value == numeric_value:
            positions.append((start, end))
    return positions


def _build_unique_source_key(numeric, uppercase, evidence, full_text: str) -> str | None:
    # Use paragraph-aware normalization for evidence location
    para_text = _normalize_paragraph_aware(full_text)
    para_evidence = _normalize_paragraph_aware(evidence)
    if not para_evidence:
        return None

    evidence_positions = _find_all_occurrences(para_text, para_evidence)
    if not evidence_positions:
        return None

    normalized_numeric = _normalize_amount_text(numeric)
    normalized_uppercase = _normalize_amount_text(uppercase)
    if not normalized_numeric or not normalized_uppercase:
        return None

    normalized_evidence = _normalize_amount_text(evidence)

    if not _uppercase_exists_in_text(normalized_evidence, normalized_uppercase):
        return None

    try:
        numeric_value = Decimal(normalized_numeric)
    except (InvalidOperation, TypeError, ValueError):
        return None

    if not _collect_numeric_tokens(normalized_evidence, numeric_value):
        return None

    uppercase_base = normalized_uppercase.removeprefix("人民币") if normalized_uppercase.startswith("人民币") else normalized_uppercase
    if not uppercase_base:
        return None

    candidates: set[tuple[int, int, int, int]] = set()
    for evidence_start, evidence_end in evidence_positions:
        evidence_text = para_text[evidence_start:evidence_end]
        numeric_candidates = _find_numeric_token_positions(evidence_text, numeric_value)
        uppercase_candidates = _find_all_occurrences(evidence_text, uppercase_base)
        for num_start, num_end in numeric_candidates:
            for upper_start, upper_end in uppercase_candidates:
                candidates.add((
                    evidence_start + num_start,
                    evidence_start + num_end,
                    evidence_start + upper_start,
                    evidence_start + upper_end,
                ))

    if len(candidates) != 1:
        return None
    num_start, num_end, upper_start, upper_end = next(iter(candidates))
    return f"main:{num_start}-{num_end}:{upper_start}-{upper_end}"


def _uppercase_evidence_verified(uppercase, evidence, full_text: str) -> bool:
    if not _evidence_is_bounded(evidence):
        return False
    normalized_evidence = _normalize_amount_text(evidence)
    if not normalized_evidence:
        return False
    # Use paragraph-aware normalization for evidence location check
    para_text = _normalize_paragraph_aware(full_text)
    para_evidence = _normalize_paragraph_aware(evidence)
    if para_evidence not in para_text:
        return False
    normalized_uppercase = _normalize_amount_text(uppercase)
    if not normalized_uppercase:
        return False
    return _uppercase_exists_in_text(normalized_evidence, normalized_uppercase)


def _build_single_side_source_key(side: str, value, evidence, full_text: str) -> str | None:
    # Use paragraph-aware normalization for evidence location
    para_text = _normalize_paragraph_aware(full_text)
    para_evidence = _normalize_paragraph_aware(evidence)
    if not para_evidence:
        return None

    evidence_positions = _find_all_occurrences(para_text, para_evidence)
    if not evidence_positions:
        return None

    candidates: set[tuple[int, int]] = set()
    if side == "num":
        normalized_numeric = _normalize_amount_text(value)
        if not normalized_numeric:
            return None
        try:
            numeric_value = Decimal(normalized_numeric)
        except (InvalidOperation, TypeError, ValueError):
            return None
        normalized_evidence = _normalize_amount_text(evidence)
        if not _collect_numeric_tokens(normalized_evidence, numeric_value):
            return None
        for evidence_start, evidence_end in evidence_positions:
            evidence_text = para_text[evidence_start:evidence_end]
            numeric_candidates = _find_numeric_token_positions(evidence_text, numeric_value)
            for num_start, num_end in numeric_candidates:
                candidates.add((evidence_start + num_start, evidence_start + num_end))
        prefix = "num"
    elif side == "upper":
        normalized_uppercase = _normalize_amount_text(value)
        if not normalized_uppercase:
            return None
        normalized_evidence = _normalize_amount_text(evidence)
        if not _uppercase_exists_in_text(normalized_evidence, normalized_uppercase):
            return None
        uppercase_base = (
            normalized_uppercase.removeprefix("人民币")
            if normalized_uppercase.startswith("人民币")
            else normalized_uppercase
        )
        if not uppercase_base:
            return None
        for evidence_start, evidence_end in evidence_positions:
            evidence_text = para_text[evidence_start:evidence_end]
            uppercase_candidates = _find_all_occurrences(evidence_text, uppercase_base)
            for upper_start, upper_end in uppercase_candidates:
                candidates.add((evidence_start + upper_start, evidence_start + upper_end))
        prefix = "upper"
    else:
        return None

    if len(candidates) != 1:
        return None
    start, end = next(iter(candidates))
    return f"{prefix}:{start}-{end}"


def _overall_evidence_verified(evidence, full_text: str) -> bool:
    if not _evidence_is_bounded(evidence):
        return False
    if not _is_overall_amount_evidence(evidence):
        return False
    # Use paragraph-aware normalization for evidence location check
    para_text = _normalize_paragraph_aware(full_text)
    para_evidence = _normalize_paragraph_aware(evidence)
    if not para_evidence:
        return False
    return para_evidence in para_text


def _find_rmb_numeric_tokens(row: str) -> list[tuple[str, int, int]]:
    tokens: list[tuple[str, int, int]] = []
    for token, start, end in _iter_numeric_token_matches(row):
        after = row[end:end + 1]
        before = row[max(0, start - 1):start]
        if after in _CURRENCY_UNIT_SUFFIX or before in _CURRENCY_PREFIX:
            tokens.append((token, start, end))
    return tokens


def _find_uppercase_amount_tokens(row: str) -> list[tuple[str, int, int]]:
    tokens: list[tuple[str, int, int]] = []
    for match in _UPPERCASE_AMOUNT_PATTERN.finditer(row):
        token = match.group(0)
        if any(digit in token for digit in _DIGITS) and ("元" in token or "圆" in token):
            tokens.append((token, match.start(), match.end()))
    return tokens


def _recover_overall_amount_from_evidence(evidence, full_text: str) -> dict | None:
    if not _overall_evidence_verified(evidence, full_text):
        return None
    if not _evidence_is_bounded(evidence):
        return None

    numeric_tokens = _find_rmb_numeric_tokens(str(evidence))
    uppercase_tokens = _find_uppercase_amount_tokens(str(evidence))
    if len(numeric_tokens) != 1 or len(uppercase_tokens) != 1:
        return None

    numeric = numeric_tokens[0][0]
    uppercase = uppercase_tokens[0][0]
    source_key = _build_unique_source_key(numeric, uppercase, evidence, full_text)
    if source_key is None:
        return None

    return {
        "numeric": numeric,
        "uppercase": uppercase,
        "evidence": evidence,
        "source_key": source_key,
    }


def _has_valid_full_total_pair(source_keys: dict) -> bool:
    total_key = source_keys.get("total")
    return isinstance(total_key, str) and total_key.startswith("main:")


def sanitize_amount_payment_facts(a3_result: dict, full_text: str) -> dict:
    sanitized = deepcopy(a3_result)
    source_keys: dict[str, str | None | list[str | None]] = {
        "total": None,
        "amount_pairs": [],
        "payment_stages": [],
    }

    overall_evidence = sanitized.get("contract_overall_evidence")
    overall_verified = _overall_evidence_verified(overall_evidence, full_text)

    total_numeric = sanitized.get("total_amount_numeric")
    total_uppercase = sanitized.get("total_amount_uppercase")
    if not overall_verified:
        sanitized["total_amount_numeric"] = None
        sanitized["total_amount_uppercase"] = None
        sanitized["total_amount_evidence"] = None
    else:
        numeric_verified = _amount_numeric_evidence_verified(total_numeric, overall_evidence, full_text)
        uppercase_verified = _uppercase_evidence_verified(total_uppercase, overall_evidence, full_text)
        if numeric_verified and uppercase_verified:
            # Always use verified contract_overall_evidence as the evidence baseline
            sanitized["total_amount_evidence"] = overall_evidence
            source_keys["total"] = _build_unique_source_key(
                total_numeric,
                total_uppercase,
                overall_evidence,
                full_text,
            )
        elif numeric_verified:
            sanitized["total_amount_uppercase"] = None
            sanitized["total_amount_evidence"] = overall_evidence
            source_keys["total"] = _build_single_side_source_key("num", total_numeric, overall_evidence, full_text)
        elif uppercase_verified:
            sanitized["total_amount_numeric"] = None
            sanitized["total_amount_evidence"] = overall_evidence
            source_keys["total"] = _build_single_side_source_key("upper", total_uppercase, overall_evidence, full_text)
        else:
            sanitized["total_amount_numeric"] = None
            sanitized["total_amount_uppercase"] = None
            sanitized["total_amount_evidence"] = None

    verified_pairs: list[dict] = []
    pair_source_keys: list[str | None] = []
    for pair in sanitized.get("amount_pairs") or []:
        if not isinstance(pair, dict):
            continue
        safe_pair = dict(pair)
        numeric = safe_pair.get("amount_numeric")
        uppercase = safe_pair.get("amount_uppercase")
        evidence = safe_pair.get("amount_evidence")
        numeric_verified = _amount_numeric_evidence_verified(numeric, evidence, full_text)
        uppercase_verified = _uppercase_evidence_verified(uppercase, evidence, full_text)

        if numeric_verified and uppercase_verified:
            pair_source_keys.append(_build_unique_source_key(numeric, uppercase, evidence, full_text))
        elif numeric_verified:
            safe_pair["amount_uppercase"] = None
            pair_source_keys.append(_build_single_side_source_key("num", numeric, evidence, full_text))
        elif uppercase_verified:
            safe_pair["amount_numeric"] = None
            pair_source_keys.append(_build_single_side_source_key("upper", uppercase, evidence, full_text))
        else:
            continue

        verified_pairs.append(safe_pair)

    sanitized["amount_pairs"] = verified_pairs
    source_keys["amount_pairs"] = pair_source_keys

    sanitized_stages: list[dict] = []
    stage_source_keys: list[str | None] = []
    for stage in sanitized.get("payment_stages") or []:
        if not isinstance(stage, dict):
            continue
        safe_stage = dict(stage)
        numeric = safe_stage.get("amount_numeric")
        uppercase = safe_stage.get("amount_uppercase")
        evidence = safe_stage.get("amount_evidence")
        numeric_verified = _amount_numeric_evidence_verified(numeric, evidence, full_text)
        uppercase_verified = _uppercase_evidence_verified(uppercase, evidence, full_text)

        if numeric_verified and uppercase_verified:
            stage_source_keys.append(_build_unique_source_key(numeric, uppercase, evidence, full_text))
        elif numeric_verified:
            safe_stage["amount_uppercase"] = None
            stage_source_keys.append(_build_single_side_source_key("num", numeric, evidence, full_text))
        elif uppercase_verified:
            safe_stage["amount_numeric"] = None
            stage_source_keys.append(_build_single_side_source_key("upper", uppercase, evidence, full_text))
        else:
            safe_stage["amount_numeric"] = None
            safe_stage["amount_uppercase"] = None
            safe_stage["amount_evidence"] = None
            stage_source_keys.append(None)

        sanitized_stages.append(safe_stage)

    sanitized["payment_stages"] = sanitized_stages
    source_keys["payment_stages"] = stage_source_keys

    # Recovery: extract amount from verified overall evidence when no full pair exists.
    # Store as PRIVATE candidate for seq7 only — never leak to shared total_amount_* fields,
    # _amount_source_keys["total"], or any downstream consumer (seq10, B-4).
    if overall_verified and not _has_valid_full_total_pair(source_keys):
        recovered = _recover_overall_amount_from_evidence(overall_evidence, full_text)
        if recovered is not None:
            sanitized["_recovered_total"] = {
                "numeric": recovered["numeric"],
                "uppercase": recovered["uppercase"],
                "evidence": recovered["evidence"],
                "source_key": recovered["source_key"],
            }

    sanitized["_amount_source_keys"] = source_keys
    return sanitized
