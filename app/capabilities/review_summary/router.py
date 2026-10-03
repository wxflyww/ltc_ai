"""POST /api/v1/review-summary 路由（JSON-only）。"""
from fastapi import APIRouter

from app.capabilities.review_summary.schemas import ReviewSummaryRequest
from app.capabilities.review_summary.service import generate_review_summary
from app.core.response import ApiResponse

router = APIRouter(prefix="/api/v1", tags=["review-summary"])


@router.post("/review-summary")
def review_summary_endpoint(request: ReviewSummaryRequest) -> dict:
    data = generate_review_summary(request)
    body = ApiResponse(data=data).to_dict()
    # traceId / duration_seconds 由中间件在响应阶段注入，此处先占位
    body.setdefault("traceId", "")
    body.setdefault("duration_seconds", 0.0)
    return body
