from difflib import SequenceMatcher

from app.capabilities.contract_review.checks import build_check_items
from app.capabilities.contract_review.schemas import CheckItem


def similarity(a: str | None, b: str | None) -> float:
    left = (a or "").strip()
    right = (b or "").strip()
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def find_matching_section(
    sections: list[dict],
    heading_hint: str | None,
    full_text: str | None = None,
    fallback_length: int = 1500,
) -> dict | None:
    if heading_hint:
        best_section = None
        best_score = 0.0
        for section in sections:
            score = similarity(heading_hint, section.get("title"))
            if score > best_score:
                best_section = section
                best_score = score
        if best_section is not None and best_score >= 0.6:
            return {
                "title": best_section.get("title"),
                "text": best_section.get("content", ""),
                "match_confidence": "high",
                "score": best_score,
            }
        if best_section is not None and best_score >= 0.3:
            return {
                "title": best_section.get("title"),
                "text": best_section.get("content", ""),
                "match_confidence": "low",
                "score": best_score,
            }

    if heading_hint and full_text:
        position = full_text.find(heading_hint)
        if position >= 0:
            return {
                "title": heading_hint,
                "text": full_text[position: position + fallback_length],
                "match_confidence": "fallback",
                "score": 0.0,
            }
    return None


def _to_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _check_copies(a4_result: dict) -> CheckItem:
    copies = a4_result.get("copies") or {}
    total = _to_int(copies.get("total_copies"))
    party_copies = copies.get("party_copies") or []
    hard: list[str] = []
    warn: list[str] = []

    if total is None:
        warn.append("合同份数缺失或无法识别")
    else:
        parsed_party_copies = []
        for item in party_copies:
            copies_value = _to_int(item.get("copies"))
            if copies_value is not None:
                parsed_party_copies.append(copies_value)
        if party_copies and sum(parsed_party_copies) != total:
            hard.append(f"各方持有份数合计{sum(parsed_party_copies)}份，与合同总份数{total}份不一致")

    return build_check_items("序号12", "合同份数", hard, warn)[0]


def check_copies_and_attachments(
    a4_result: dict,
    sections: list[dict],
    attachments: list[dict],
    full_text: str,
) -> dict:
    declared = a4_result.get("attachments_declared") or []
    total_declared = _to_int(a4_result.get("total_declared"))
    resolved_attachments: list[dict] = []
    hard: list[str] = []
    warn: list[str] = []

    for declared_item in declared:
        if declared_item.get("content_embedded_in_contract"):
            matched = find_matching_section(
                sections,
                declared_item.get("section_heading_hint") or declared_item.get("title"),
                full_text,
            )
            if matched is None:
                warn.append(f"声明附件《{declared_item.get('title')}》标记为正文内嵌，但未定位到对应正文段落")
                continue
            if matched["match_confidence"] in {"low", "fallback"}:
                warn.append(f"声明附件《{declared_item.get('title')}》仅低置信度匹配到正文段落")
            resolved_attachments.append({
                "index": declared_item.get("index"),
                "title": declared_item.get("title"),
                "source": "正文内嵌",
                "text": matched["text"],
                "match_confidence": matched["match_confidence"],
            })

    for uploaded in attachments:
        filename = uploaded.get("filename", "")
        if uploaded.get("source") == "合同正文内嵌":
            resolved_attachments.append({
                "index": uploaded.get("index"),
                "filename": filename,
                "title": uploaded.get("title") or filename,
                "source": "合同正文内嵌",
                "text": uploaded.get("text", ""),
                "match_confidence": "high",
            })
            continue

        best_declared = None
        best_score = 0.0
        for declared_item in declared:
            score = similarity(filename, declared_item.get("title"))
            if score > best_score:
                best_declared = declared_item
                best_score = score
        if best_declared is not None and best_score >= 0.6:
            source = "单独上传-标题匹配"
            title = best_declared.get("title")
        else:
            source = "单独上传-标题未匹配"
            title = filename
            if declared and total_declared is not None and len(attachments) >= total_declared:
                warn.append(f"上传附件《{filename}》未能与合同声明附件标题高置信度匹配")
        resolved_attachments.append({
            "index": uploaded.get("index"),
            "filename": filename,
            "title": title,
            "source": source,
            "text": uploaded.get("text", ""),
            "match_confidence": "high" if best_score >= 0.6 else "unmatched",
        })

    actual_count = len(resolved_attachments)
    if total_declared is not None and actual_count < total_declared:
        hard.append(f"正文声明附件{total_declared}份，实际仅获取到{actual_count}份")

    check_results: list[CheckItem] = [_check_copies(a4_result)]
    check_results.extend(build_check_items("附件检查-数量标题", "附件数量/标题一致性", hard, warn))
    return {"check_results": check_results, "resolved_attachments": resolved_attachments}
