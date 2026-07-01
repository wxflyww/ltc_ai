"""POST /api/v1/translate 路由。"""
from fastapi import APIRouter

from app.core.response import ApiResponse
from app.capabilities.translate.schemas import TranslateRequest
from app.capabilities.translate.service import translate

router = APIRouter(prefix="/api/v1", tags=["translate"])


@router.post("/translate")
def translate_endpoint(request: TranslateRequest) -> dict:
    data = translate(request)
    body = ApiResponse(data=data).to_dict()
    # traceId / duration_seconds 由中间件在响应阶段注入，此处先占位
    body.setdefault("traceId", "")
    body.setdefault("duration_seconds", 0.0)
    return body
