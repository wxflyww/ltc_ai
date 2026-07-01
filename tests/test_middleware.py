from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.capabilities.translate.schemas import TranslateData, TokenUsage
from app.core.errors import ModelInvocationError
from app.core.middleware import TraceIdMiddleware, AuthMiddleware, register_exception_handlers
from app.capabilities.translate.router import router as translate_router


def _build(auth_keys=None):
    app = FastAPI()
    # 注册顺序：AuthMiddleware 先 add（外层），TraceIdMiddleware 后 add（更外层，包裹 Auth 响应）
    app.add_middleware(AuthMiddleware, allowed_keys=auth_keys or [])
    app.add_middleware(TraceIdMiddleware)
    register_exception_handlers(app)
    app.include_router(translate_router)
    return TestClient(app)


def test_trace_id_passthrough_and_duration():
    fake = TranslateData(translated_text="Hi", source_lang="zh", model="m",
                         token_usage=TokenUsage())
    with patch("app.capabilities.translate.router.translate", return_value=fake):
        c = _build(auth_keys=["k1"])
        r = c.post("/api/v1/translate", json={"text": "x", "target_lang": "en"},
                   headers={"X-API-Key": "k1", "X-Trace-Id": "client-trace-1"})
    assert r.status_code == 200
    body = r.json()
    assert body["traceId"] == "client-trace-1"
    assert isinstance(body["duration_seconds"], (int, float))
    assert body["duration_seconds"] >= 0


def test_auth_missing_key_returns_10002():
    c = _build(auth_keys=["k1"])
    r = c.post("/api/v1/translate", json={"text": "x", "target_lang": "en"})
    assert r.status_code == 401
    assert r.json()["code"] == 10002


def test_auth_invalid_key_returns_10002():
    c = _build(auth_keys=["k1"])
    r = c.post("/api/v1/translate", json={"text": "x", "target_lang": "en"},
               headers={"X-API-Key": "wrong"})
    assert r.status_code == 401
    assert r.json()["code"] == 10002


def test_auth_bearer_header_accepted():
    fake = TranslateData(translated_text="Hi", source_lang="zh", model="m",
                         token_usage=TokenUsage())
    with patch("app.capabilities.translate.router.translate", return_value=fake):
        c = _build(auth_keys=["k1"])
        r = c.post("/api/v1/translate", json={"text": "x", "target_lang": "en"},
                   headers={"Authorization": "Bearer k1"})
    assert r.status_code == 200


def test_health_bypasses_auth():
    app = FastAPI()
    app.add_middleware(AuthMiddleware, allowed_keys=["k1"])

    @app.get("/health")
    def h():
        return {"status": "ok"}

    c = TestClient(app)
    r = c.get("/health")
    assert r.status_code == 200


def test_app_error_returned_as_unified_response():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom():
        raise ModelInvocationError("exhausted")

    c = TestClient(app)
    r = c.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["code"] == 20001
    assert body["data"] is None


def test_unhandled_exception_returns_29999():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/crash")
    def crash():
        raise RuntimeError("unexpected")

    # raise_server_exceptions=False：让异常被全局 handler 捕获后返回 500，
    # 而非被 TestClient 重新抛出
    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/crash")
    assert r.status_code == 500
    assert r.json()["code"] == 29999
