from __future__ import annotations

from collections.abc import Mapping

from app.capabilities.contract_review.two_stage.keys import stable_key
from app.capabilities.contract_review.two_stage.schemas import EvidenceItem


class EvidenceLocationError(ValueError):
    pass


def parse_markdown_locator(locator: str) -> tuple[int, int]:
    prefix = "markdown-chars:"
    if not locator.startswith(prefix):
        raise EvidenceLocationError(f"不支持的 locator 格式: {locator}")
    body = locator[len(prefix):]
    parts = body.split("-", maxsplit=1)
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        raise EvidenceLocationError(f"不支持的 locator 格式: {locator}")
    start = int(parts[0])
    end = int(parts[1])
    if start < 0 or end < 0 or end < start:
        raise EvidenceLocationError(f"非法 locator 范围: {locator}")
    return start, end


def format_markdown_locator(start: int, end: int) -> str:
    if start < 0 or end < 0 or end < start:
        raise EvidenceLocationError(f"非法 locator 范围: start={start}, end={end}")
    return f"markdown-chars:{start}-{end}"


def locate_unique_quote(
    markdown: str,
    quote: str,
    *,
    allowed_range: tuple[int, int] | None = None,
) -> tuple[int, int]:
    if not quote:
        raise EvidenceLocationError("quote 不能为空")

    range_start, range_end = allowed_range or (0, len(markdown))
    if range_start < 0 or range_end < range_start or range_end > len(markdown):
        raise EvidenceLocationError("allowed_range 超出文档边界")

    matches: list[tuple[int, int]] = []
    probe = range_start
    while True:
        index = markdown.find(quote, probe, range_end)
        if index == -1:
            break
        matches.append((index, index + len(quote)))
        probe = index + 1

    if not matches:
        raise EvidenceLocationError("quote 在限定范围内未命中")
    if len(matches) > 1:
        raise EvidenceLocationError("quote 在限定范围内定位不唯一")
    return matches[0]


class EvidenceRegistry:
    def __init__(self, markdown_by_document: Mapping[str, str]):
        self._markdown_by_document = dict(markdown_by_document)
        self._items_by_coordinate: dict[tuple[str, int, int], EvidenceItem] = {}

    def register(
        self,
        document_key: str,
        quote: str,
        allowed_range: tuple[int, int] | None = None,
    ) -> EvidenceItem:
        markdown = self._markdown_by_document.get(document_key)
        if markdown is None:
            raise EvidenceLocationError(f"未知 document_key: {document_key}")

        start, end = locate_unique_quote(markdown, quote, allowed_range=allowed_range)
        coordinate = (document_key, start, end)
        existing = self._items_by_coordinate.get(coordinate)
        if existing is not None:
            return existing

        if markdown[start:end] != quote:
            raise EvidenceLocationError("quote 与 locator 切片不一致")

        item = EvidenceItem(
            evidence_id=stable_key(
                "evidence",
                {
                    "document_key": document_key,
                    "start": start,
                    "end": end,
                },
            ),
            document_key=document_key,
            source_locator=format_markdown_locator(start, end),
            quote=quote,
        )
        self._items_by_coordinate[coordinate] = item
        return item

    def items(self) -> list[EvidenceItem]:
        return [
            item
            for _, item in sorted(
                self._items_by_coordinate.items(),
                key=lambda kv: (kv[0][0], kv[0][1], kv[0][2], kv[1].evidence_id),
            )
        ]
