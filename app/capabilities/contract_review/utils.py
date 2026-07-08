import re
from datetime import date


def is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"", "null"}
    return False


def to_halfwidth(value: str | None) -> str | None:
    if value is None:
        return None
    result = []
    for ch in value:
        code = ord(ch)
        if code == 0x3000:
            code = 0x20
        elif 0xFF01 <= code <= 0xFF5E:
            code -= 0xFEE0
        result.append(chr(code))
    return "".join(result)


def normalize_date(value: str | None) -> date | None:
    if is_empty(value):
        return None
    text = str(value).strip()
    match = re.match(r"(\d{4})[年\-/\.](\d{1,2})[月\-/\.](\d{1,2})日?", text)
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def mask_id_number(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) < 10:
        return "*" * len(text)
    return f"{text[:6]}{'*' * (len(text) - 10)}{text[-4:]}"
