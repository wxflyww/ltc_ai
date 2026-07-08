from unittest.mock import patch

from app.capabilities.contract_review.schemas import ContractReviewRequest
from app.capabilities.contract_review.service import review_contract


def test_review_contract_preserves_fail_and_warn_from_checks():
    request = ContractReviewRequest(contract_md="# 合同", attachments=[])
    with patch("app.capabilities.contract_review.service.run_review_pipeline") as fake_pipeline:
        fake_pipeline.return_value = [
            {"id": "序号2", "name": "签章页完整性", "result": "FAIL", "block_level": "硬阻断", "reason": "银行账号不一致"},
            {"id": "序号2", "name": "签章页完整性", "result": "WARN", "block_level": "提示", "reason": "传真缺失"},
        ]
        data = review_contract(request, check_time="2026-07-07T10:00:00")
    assert data.overall_result == "BLOCK"
    assert len(data.checks) == 2


def test_review_contract_does_not_call_real_llm_in_unit_test():
    request = ContractReviewRequest(contract_md="# 合同", attachments=[])
    with patch("app.capabilities.contract_review.service.invoke_model") as fake_invoke:
        with patch("app.capabilities.contract_review.service.run_review_pipeline", return_value=[]):
            review_contract(request, check_time="2026-07-07T10:00:00")
    fake_invoke.assert_not_called()
