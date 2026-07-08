from app.capabilities.contract_review.attachments import check_copies_and_attachments


def test_declared_three_but_actual_two_fails():
    result = check_copies_and_attachments(
        a4_result={
            "copies": {"total_copies": 2, "party_copies": [{"role": "甲方", "copies": 1}, {"role": "乙方", "copies": 1}]},
            "attachments_declared": [
                {"index": 1, "title": "附件一", "content_embedded_in_contract": False, "section_heading_hint": None},
                {"index": 2, "title": "附件二", "content_embedded_in_contract": False, "section_heading_hint": None},
                {"index": 3, "title": "附件三", "content_embedded_in_contract": False, "section_heading_hint": None},
            ],
            "total_declared": 3,
        },
        sections=[],
        attachments=[
            {"index": 1, "filename": "附件一.xlsx", "text": "1"},
            {"index": 2, "filename": "附件二.xlsx", "text": "2"},
        ],
        full_text="",
    )
    attach_items = [item for item in result["check_results"] if item.id == "附件检查-数量标题"]
    assert attach_items[0].result == "FAIL"
    assert "实际仅获取到2份" in attach_items[0].reason


def test_embedded_one_plus_uploaded_two_satisfies_declared_three():
    result = check_copies_and_attachments(
        a4_result={
            "copies": {"total_copies": 2, "party_copies": [{"role": "甲方", "copies": 1}, {"role": "乙方", "copies": 1}]},
            "attachments_declared": [
                {"index": 1, "title": "附件一", "content_embedded_in_contract": True, "section_heading_hint": "附件一"},
            ],
            "total_declared": 3,
        },
        sections=[{"title": "附件一", "content": "内嵌"}],
        attachments=[
            {"index": 2, "filename": "附件二.xlsx", "text": "2"},
            {"index": 3, "filename": "附件三.xlsx", "text": "3"},
        ],
        full_text="",
    )
    attach_items = [item for item in result["check_results"] if item.id == "附件检查-数量标题"]
    assert all(item.result != "FAIL" for item in attach_items)
    assert len(result["resolved_attachments"]) == 3


def test_party_copies_sum_mismatch_fails_seq12():
    result = check_copies_and_attachments(
        a4_result={
            "copies": {"total_copies": 3, "party_copies": [{"role": "甲方", "copies": 1}, {"role": "乙方", "copies": 1}]},
            "attachments_declared": [],
            "total_declared": None,
        },
        sections=[],
        attachments=[],
        full_text="",
    )
    assert result["check_results"][0].id == "序号12"
    assert result["check_results"][0].result == "FAIL"
