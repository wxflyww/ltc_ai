import re


_ATTACHMENT_HEADING_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(附件\s*(?:[一二三四五六七八九十]+|\d+))\s*[：:、.]?\s*$"
)


def _match_attachment_heading(line: str) -> str | None:
    match = _ATTACHMENT_HEADING_RE.match(line)
    if not match:
        return None
    return re.sub(r"\s+", "", match.group(1))


def _make_attachment(title: str, lines: list[str], index: int) -> dict:
    return {
        "index": index,
        "filename": f"{title}.md",
        "file_type": "md",
        "title": title,
        "source": "合同正文内嵌",
        "text": "\n".join(lines).strip(),
    }


def split_embedded_attachments(contract_md: str) -> tuple[str, list[dict]]:
    lines = contract_md.splitlines()
    cleaned_lines: list[str] = []
    attachments: list[dict] = []
    current_title: str | None = None
    current_lines: list[str] = []

    for line in lines:
        title = _match_attachment_heading(line)
        if title is not None:
            if current_title is not None:
                attachments.append(_make_attachment(current_title, current_lines, len(attachments) + 1))
            current_title = title
            current_lines = [line]
            continue

        if current_title is None:
            cleaned_lines.append(line)
        else:
            current_lines.append(line)

    if current_title is not None:
        attachments.append(_make_attachment(current_title, current_lines, len(attachments) + 1))

    if not attachments:
        return contract_md, []

    cleaned = "\n".join(cleaned_lines).rstrip()
    if contract_md.endswith("\n") and cleaned:
        cleaned += "\n"
    return cleaned, attachments
