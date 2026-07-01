from fastapi import FastAPI

from app.core.exception_handlers import register_exception_handlers
from app.capabilities.translate.router import router as translate_router


def create_app(register_middleware: bool = True) -> FastAPI:
    app = FastAPI(title="LTC AI能力服务", version="1.0.0")
    register_exception_handlers(app)
    app.include_router(translate_router)
    if register_middleware:
        pass  # Task 9 接入
    return app


app = create_app()
