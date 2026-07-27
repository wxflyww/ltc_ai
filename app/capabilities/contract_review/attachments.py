import re
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from app.capabilities.contract_review.checks import build_check_items
from app.capabilities.contract_review.schemas import CheckItem


def similarity(a: str | None, b: str | None) -> float:
    left = (a or "").strip()
    right = (b or "").strip()
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _normalize_attachment_title(value: str | None, *, remove_extension: bool) -> str:
    raw = (value or "").replace("\\", "/")
    stem = Path(raw).name if remove_extension else raw
    if remove_extension:
        suffix = Path(stem).suffix
        stem = stem[:-len(suffix)] if suffix else stem
    normalized = unicodedata.normalize("NFKC", stem).casefold().strip()
    prefix = re.match(r"^附件\s*[0-9一二三四五六七八九十百千〇零]+(?P<tail>.*)$", normalized)
    if prefix:
        remainder = prefix.group("tail").lstrip(" ：:、._-")
        if remainder:
            normalized = remainder
    return re.sub(r"[\s《》「」“”‘’\"'（）()\[\]【】]+", "", normalized)


def normalize_attachment_title(value: str | None) -> str:
    return _normalize_attachment_title(value, remove_extension=False)


def normalize_uploaded_attachment_filename(value: str | None) -> str:
    return _normalize_attachment_title(value, remove_extension=True)


def _attachment_title_candidates(declared: list[dict], attachments: list[dict]) -> tuple[list[dict], list[dict]]:
    declared_candidates = []
    for position, item in enumerate(declared):
        title = item.get("title")
        if item.get("content_embedded_in_contract") or not normalize_attachment_title(title):
            continue
        declared_candidates.append({
            "id": f"declared-{position}",
            "position": position,
            "index": item.get("index"),
            "title": title,
        })

    uploaded_candidates = []
    for position, item in enumerate(attachments):
        filename = item.get("filename", "")
        if item.get("source") == "合同正文内嵌" or not normalize_uploaded_attachment_filename(filename):
            continue
        uploaded_candidates.append({
            "id": f"uploaded-{position}",
            "position": position,
            "index": item.get("index"),
            "filename": filename,
        })
    return declared_candidates, uploaded_candidates


def build_attachment_title_match_plan(declared: list[dict], attachments: list[dict]) -> dict:
    declared_candidates, uploaded_candidates = _attachment_title_candidates(declared, attachments)
    declared_by_title: dict[str, list[dict]] = defaultdict(list)
    uploaded_by_title: dict[str, list[dict]] = defaultdict(list)
    for item in declared_candidates:
        declared_by_title[normalize_attachment_title(item["title"])].append(item)
    for item in uploaded_candidates:
        uploaded_by_title[normalize_uploaded_attachment_filename(item["filename"])].append(item)

    matches: list[dict] = []
    matched_declared_ids: set[str] = set()
    matched_uploaded_ids: set[str] = set()
    for title, declared_items in declared_by_title.items():
        uploaded_items = uploaded_by_title.get(title, [])
        if len(declared_items) != 1 or len(uploaded_items) != 1:
            continue
        declared_item = declared_items[0]
        uploaded_item = uploaded_items[0]
        matches.append({"declared_id": declared_item["id"], "uploaded_id": uploaded_item["id"]})
        matched_declared_ids.add(declared_item["id"])
        matched_uploaded_ids.add(uploaded_item["id"])

    return {
        "matches": matches,
        "declared_candidates": declared_candidates,
        "uploaded_candidates": uploaded_candidates,
        "unresolved_declared": [item for item in declared_candidates if item["id"] not in matched_declared_ids],
        "unresolved_uploaded": [item for item in uploaded_candidates if item["id"] not in matched_uploaded_ids],
    }


def validate_attachment_title_matches(decisions: list[dict], match_plan: dict) -> list[dict]:
    declared_ids = {item["id"] for item in match_plan.get("unresolved_declared", [])}
    uploaded_ids = {item["id"] for item in match_plan.get("unresolved_uploaded", [])}
    candidates = [
        {"declared_id": item.get("declared_id"), "uploaded_id": item.get("uploaded_id")}
        for item in decisions
        if item.get("judgement") == "MATCH"
        and item.get("declared_id") in declared_ids
        and item.get("uploaded_id") in uploaded_ids
    ]
    declared_counts = Counter(item["declared_id"] for item in candidates)
    uploaded_counts = Counter(item["uploaded_id"] for item in candidates)
    return [
        item for item in candidates
        if declared_counts[item["declared_id"]] == 1 and uploaded_counts[item["uploaded_id"]] == 1
    ]


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
    semantic_matches: list[dict] | None = None,
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

    match_plan = build_attachment_title_match_plan(declared, attachments)
    direct_pairs = {(item["declared_id"], item["uploaded_id"]) for item in match_plan["matches"]}
    semantic_pairs = {
        (item["declared_id"], item["uploaded_id"])
        for item in (semantic_matches or [])
    }
    declared_by_id = {item["id"]: item for item in match_plan["declared_candidates"]}
    matched_by_uploaded_id = {
        uploaded_id: (declared_id, "单独上传-标题规范化匹配")
        for declared_id, uploaded_id in direct_pairs
    }
    matched_by_uploaded_id.update({
        uploaded_id: (declared_id, "单独上传-标题语义匹配")
        for declared_id, uploaded_id in semantic_pairs
    })

    for position, uploaded in enumerate(attachments):
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

        matched_pair = matched_by_uploaded_id.get(f"uploaded-{position}")
        if matched_pair is not None:
            declared_id, source = matched_pair
            declared_item = declared_by_id[declared_id]
            title = declared_item.get("title")
            confidence = "high"
        else:
            source = "单独上传-标题未匹配"
            title = filename
            confidence = "unmatched"
            if declared:
                warn.append(f"上传附件《{filename}》无法与合同声明附件标题唯一对应，请业务确认")
        resolved_attachments.append({
            "index": uploaded.get("index"),
            "filename": filename,
            "title": title,
            "source": source,
            "text": uploaded.get("text", ""),
            "match_confidence": confidence,
        })

    actual_count = len(resolved_attachments)
    if total_declared is not None and actual_count < total_declared:
        hard.append(f"正文声明附件{total_declared}份，实际仅获取到{actual_count}份")

    check_results: list[CheckItem] = [_check_copies(a4_result)]
    check_results.extend(build_check_items("附件检查-数量标题", "附件数量/标题一致性", hard, warn))
    return {"check_results": check_results, "resolved_attachments": resolved_attachments}
