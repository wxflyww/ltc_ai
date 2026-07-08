from fastapi import APIRouter

from app.capabilities.contract_review.schemas import ContractReviewRequest
from app.capabilities.contract_review.service import review_contract
from app.core.response import ApiResponse

router = APIRouter(prefix="/api/v1", tags=["contract-review"])


@router.post("/contract-review")
def contract_review_endpoint(request: ContractReviewRequest) -> dict:
    data = review_contract(request)
    body = ApiResponse(data=data).to_dict()
    body.setdefault("traceId", "")
    body.setdefault("duration_seconds", 0.0)
    return body
