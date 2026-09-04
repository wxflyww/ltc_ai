import pytest

from app.capabilities.contract_review.two_stage.evidence import (
    EvidenceLocationError,
    EvidenceRegistry,
    locate_unique_quote,
    parse_markdown_locator,
)
from app.capabilities.contract_review.two_stage.hashing import normalize_markdown


def test_locator_uses_normalized_unicode_code_points():
    markdown = normalize_markdown("甲😀Cafe\u0301乙")
    registry = EvidenceRegistry({"main": markdown})

    item = registry.register("main", "😀Café")

    assert item.source_locator == "markdown-chars:1-6"
    start, end = parse_markdown_locator(item.source_locator)
    assert markdown[start:end] == item.quote


def test_quote_must_be_unique_inside_allowed_range():
    with pytest.raises(EvidenceLocationError, match="不唯一"):
        locate_unique_quote("甲乙甲乙", "甲乙", allowed_range=(0, 4))


def test_registry_reuses_existing_evidence_for_same_coordinate():
    registry = EvidenceRegistry({"main": "甲方：北京公司；乙方：上海公司"})

    first = registry.register("main", "北京公司")
    second = registry.register("main", "北京公司")

    assert first.evidence_id == second.evidence_id
    assert len(registry.items()) == 1


def test_registry_rejects_unknown_document_key():
    registry = EvidenceRegistry({"main": "正文"})

    with pytest.raises(EvidenceLocationError, match="document_key"):
        registry.register("uploaded:att-001", "正文")
