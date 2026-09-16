from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.core.middleware import AuthMiddleware, TraceIdMiddleware, register_exception_handlers
from app.capabilities.contract_review.router import router as contract_review_router
from app.capabilities.contract_review.two_stage.prepare_router import (
    router as contract_review_prepare_router,
)
from app.capabilities.translate.router import router as translate_router


logger = get_logger("main")


def create_app(register_middleware: bool = True) -> FastAPI:
    settings = get_settings()
    setup_logging(settings.server.log_level)
    app = FastAPI(title="LTC AI能力服务", version="1.0.0")

    if register_middleware:
        if settings.app.env == "prod" and not settings.auth.api_keys:
            raise RuntimeError(
                "生产环境必须配置 LTC__AUTH__API_KEYS（JSON 数组），拒绝在无鉴权模式下启动。"
            )
        if settings.app.env != "prod" and not settings.auth.api_keys:
            logger.warning("auth disabled: LTC__AUTH__API_KEYS is empty", extra={"env": settings.app.env})

        # 注册顺序决定执行顺序：后 add 的更外层。
        # TraceIdMiddleware 在最外层，包裹 AuthMiddleware 的 401 响应，注入 traceId。
        app.add_middleware(AuthMiddleware, allowed_keys=settings.auth.api_keys)
        app.add_middleware(TraceIdMiddleware)

    register_exception_handlers(app)
    app.include_router(contract_review_router)
    app.include_router(contract_review_prepare_router)
    app.include_router(translate_router)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "1.0.0"}

    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
    return app


app = create_app()
