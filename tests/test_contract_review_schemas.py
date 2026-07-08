import pytest
from pydantic import ValidationError

from app.capabilities.contract_review.schemas import (
    AttachmentInput,
    CheckItem,
    ContractReviewData,
    ContractReviewRequest,
)


def test_request_accepts_contract_markdown_and_attachment_texts():
    req = ContractReviewRequest(
        contract_md="# 合同\n正文",
        attachments=[
            AttachmentInput(index=1, filename="附件1.xlsx", file_type="xlsx", text="附件文本")
        ],
    )
    assert req.contract_md.startswith("# 合同")
    assert req.attachments[0].filename == "附件1.xlsx"


def test_request_rejects_empty_contract_markdown():
    with pytest.raises(ValidationError):
        ContractReviewRequest(contract_md="", attachments=[])


def test_check_item_allows_required_enums():
    item = CheckItem(
        id="序号2",
        name="签章页完整性",
        result="WARN",
        block_level="提示",
        reason="传真信息缺失或未填写",
    )
    assert item.result == "WARN"


def test_review_data_keeps_duplicate_ids_in_list():
    data = ContractReviewData(
        overall_result="BLOCK",
        check_time="2026-07-07T10:00:00",
        checks=[
            CheckItem(id="序号2", name="签章页完整性", result="FAIL", block_level="硬阻断", reason="银行账号不一致"),
            CheckItem(id="序号2", name="签章页完整性", result="WARN", block_level="提示", reason="传真缺失"),
        ],
    )
    assert [item.result for item in data.checks] == ["FAIL", "WARN"]
