from app.capabilities.contract_review.embedded_attachments import split_embedded_attachments


def test_extracts_three_embedded_attachments_and_removes_from_contract():
    contract_md = """# 合同

甲方：客户公司
乙方：我方公司

附件一
技术规范内容

附件二：
报价明细内容

## 附件3
服务承诺内容
"""

    cleaned, attachments = split_embedded_attachments(contract_md)

    assert "甲方：客户公司" in cleaned
    assert "附件一" not in cleaned
    assert "技术规范内容" not in cleaned
    assert [item["title"] for item in attachments] == ["附件一", "附件二", "附件3"]
    assert [item["text"] for item in attachments] == [
        "附件一\n技术规范内容",
        "附件二：\n报价明细内容",
        "## 附件3\n服务承诺内容",
    ]
    assert [item["filename"] for item in attachments] == ["附件一.md", "附件二.md", "附件3.md"]
    assert all(item["source"] == "合同正文内嵌" for item in attachments)


def test_does_not_split_inline_attachment_references():
    contract_md = """# 合同

本合同详见附件一。
附件一式三份，甲乙双方各执一份。
正文继续。
"""

    cleaned, attachments = split_embedded_attachments(contract_md)

    assert cleaned == contract_md
    assert attachments == []


def test_no_embedded_attachments_keeps_contract_unchanged():
    contract_md = "# 合同\n\n甲方：客户公司\n乙方：我方公司\n"

    cleaned, attachments = split_embedded_attachments(contract_md)

    assert cleaned == contract_md
    assert attachments == []
