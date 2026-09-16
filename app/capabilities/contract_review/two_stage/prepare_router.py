"""Task 10：Prepare JSON-only 路由。

只做 HTTP 适配：把 PrepareRequest 交给已冻结的 prepare_contract，把返回的 ReviewContext
直接作为统一响应的 data（不做 review_context 包装）；错误映射完全交给既有全局异常处理器，
本模块不新增 try/except、不导入旧 router、不提供 multipart 入口。
"""

from fastapi import APIRouter

from app.capabilities.contract_review.two_stage.prepare_service import prepare_contract
from app.capabilities.contract_review.two_stage.schemas import PrepareRequest
from app.core.response import ApiResponse

router = APIRouter(prefix="/api/v1/contract-review", tags=["contract-review-prepare"])


@router.post("/prepare")
def prepare_contract_endpoint(request: PrepareRequest) -> dict:
    context = prepare_contract(request)
    body = ApiResponse(data=context.to_payload()).to_dict()
    body.setdefault("traceId", "")
    body.setdefault("duration_seconds", 0.0)
    return body
