"""traceId 注入、API Key 校验、耗时记录中间件。"""
import json
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.errors import ErrorCode
from app.core.logging import bind_trace_id, clear_trace_id, get_logger
from app.core.response import ApiResponse

# 重导出，便于 main 统一从 middleware 引入装配入口
from app.core.exception_handlers import register_exception_handlers  # noqa: E402,F401

logger = get_logger("middleware")

_AUTH_FREE_PATHS = {"/health", "/metrics"}


class TraceIdMiddleware(BaseHTTPMiddleware):
    """生成/透传 traceId，计时，并把 traceId/duration_seconds 注入 JSON 响应体。"""

    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex
        bind_trace_id(trace_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            clear_trace_id()
        duration = time.perf_counter() - start
        response = await _inject_trace_fields(response, trace_id, duration)
        logger.info("request done", extra={
            "endpoint": request.url.path,
            "duration_seconds": round(duration, 3),
        })
        return response


class AuthMiddleware(BaseHTTPMiddleware):
    """API Key 校验。/health 与 /metrics 放行。"""

    def __init__(self, app, allowed_keys: list[str] | None = None):
        super().__init__(app)
        self.allowed_keys = set(allowed_keys or [])

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _AUTH_FREE_PATHS:
            return await call_next(request)
        token = request.headers.get("X-API-Key") or _extract_bearer(request)
        if not token or token not in self.allowed_keys:
            return _auth_error_response()
        return await call_next(request)


def _extract_bearer(request: Request) -> str | None:
    h = request.headers.get("Authorization", "")
    if h.lower().startswith("bearer "):
        return h[7:].strip()
    return None


def _auth_error_response() -> Response:
    resp = ApiResponse(
        code=ErrorCode.AUTH_INVALID, message="API Key 无效或缺失",
        data=None, trace_id="", duration_seconds=0.0,
    )
    return Response(
        content=json.dumps(resp.to_dict(), ensure_ascii=False),
        media_type="application/json", status_code=401,
    )


async def _inject_trace_fields(response: Response, trace_id: str, duration: float) -> Response:
    """对 JSON 响应体补 traceId / duration_seconds；非 JSON（如 /metrics）原样返回。"""
    body = b""
    async for chunk in response.body_iterator:
        body += chunk
    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type:
        # 非 JSON：保持原内容返回
        return Response(content=body, status_code=response.status_code,
                        headers=dict(response.headers), media_type=response.media_type)
    try:
        obj = json.loads(body)
        if isinstance(obj, dict):
            obj["traceId"] = trace_id
            obj["duration_seconds"] = round(duration, 3)
            return JSONResponse(content=obj, status_code=response.status_code)
    except Exception:  # noqa: BLE001
        pass
    return Response(content=body, status_code=response.status_code,
                    headers=dict(response.headers), media_type=response.media_type)
