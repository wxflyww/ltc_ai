from datetime import datetime

from app.capabilities.contract_review.checks import build_review_data
from app.capabilities.contract_review.schemas import CheckItem, ContractReviewData, ContractReviewRequest
from app.models.llm import get_chat_model, invoke_model


def run_review_pipeline(request: ContractReviewRequest) -> list[CheckItem | dict]:
    return []


def review_contract(request: ContractReviewRequest, check_time: str | None = None) -> ContractReviewData:
    timestamp = check_time or datetime.now().isoformat(timespec="seconds")
    raw_items = run_review_pipeline(request)
    items = [item if isinstance(item, CheckItem) else CheckItem(**item) for item in raw_items]
    return build_review_data(timestamp, items)
