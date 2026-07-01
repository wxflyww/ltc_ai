"""全局异常 → 统一响应。"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.core.response import ApiResponse

logger = get_logger("errors")


def _json(resp: ApiResponse, status: int) -> JSONResponse:
    return JSONResponse(status_code=status, content=resp.to_dict())


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        resp = ApiResponse(
            code=ErrorCode.PARAM_INVALID, message="参数校验失败",
            data=None, trace_id="", duration_seconds=0.0,
        )
        return _json(resp, 422)

    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        logger.error("app error: %s", exc.message)
        resp = ApiResponse(
            code=exc.code, message=exc.message, data=None,
            trace_id="", duration_seconds=0.0,
        )
        return _json(resp, exc.http_status)

    @app.exception_handler(Exception)
    async def _unknown(request: Request, exc: Exception):
        logger.exception("unhandled exception")
        resp = ApiResponse(
            code=ErrorCode.UNKNOWN, message="内部错误", data=None,
            trace_id="", duration_seconds=0.0,
        )
        return _json(resp, 500)
