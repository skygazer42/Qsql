import importlib
import sys
from pathlib import Path


def _load_app_module(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "EMPTY")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "http://127.0.0.1:3000/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "test-embedding")
    monkeypatch.setenv("EMBEDDING_API_KEY", "EMPTY")
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "db"))
    sys.modules.pop("app", None)
    return importlib.import_module("app")


def test_api_rejects_requests_when_auth_secret_is_missing(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SECRET_ACCESS_KEY", "")
    monkeypatch.delenv("QSQL_ALLOW_UNAUTHENTICATED", raising=False)
    app_module = _load_app_module(monkeypatch, tmp_path)

    response = app_module.app.test_client().get("/api/v0/dataset/list")

    assert response.status_code == 503
    assert "SECRET_ACCESS_KEY" in response.get_json()["error"]


def test_api_accepts_configured_api_key(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.delenv("QSQL_ALLOW_UNAUTHENTICATED", raising=False)
    app_module = _load_app_module(monkeypatch, tmp_path)

    unauthorized = app_module.app.test_client().get("/api/v0/dataset/list")
    authorized = app_module.app.test_client().get(
        "/api/v0/dataset/list",
        headers={"X-API-KEY": "test-secret"},
    )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
