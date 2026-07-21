import pytest
from fastapi.testclient import TestClient

from app.core.config import _reset_settings
from app.main import create_app


def test_health_returns_ok():
    c = TestClient(create_app())
    r = c.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == "1.0.0"


def test_health_does_not_require_auth():
    # /health 免鉴权；create_app 默认 register_middleware=True，dev 环境 api_keys=[]
    c = TestClient(create_app())
    r = c.get("/health")
    assert r.status_code == 200


def test_metrics_exposed():
    c = TestClient(create_app())
    r = c.get("/metrics")
    assert r.status_code == 200
    # prometheus 文本格式，包含 http 指标或 python_info
    assert "http_requests_total" in r.text or "python_info" in r.text


def test_prod_requires_auth_keys(monkeypatch):
    monkeypatch.setenv("LTC_ENV", "prod")
    monkeypatch.setenv("LTC__AUTH__API_KEYS", "[]")
    _reset_settings()
    with pytest.raises(RuntimeError, match="LTC__AUTH__API_KEYS"):
        create_app()
