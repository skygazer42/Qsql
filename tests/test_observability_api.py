import importlib
import json
import sys
from pathlib import Path


def _load_app_module(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "EMPTY")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "http://127.0.0.1:3000/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "test-embedding")
    monkeypatch.setenv("EMBEDDING_API_KEY", "EMPTY")
    monkeypatch.setenv("SECRET_ACCESS_KEY", "")
    monkeypatch.setenv("QSQL_ALLOW_UNAUTHENTICATED", "true")
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "db"))
    monkeypatch.setenv("QSQL_EVENT_LOG_DIR", str(tmp_path / "events"))
    sys.modules.pop("app", None)
    sys.modules.pop("src.server.observability_api", None)
    return importlib.import_module("app")


def _write_event_file(event_dir: Path):
    event_dir.mkdir(parents=True, exist_ok=True)
    event_path = event_dir / "2026-06-11.jsonl"
    events = [
        {
            "timestamp": "2026-06-11T10:00:00",
            "route": "/api/v0/search",
            "status": "success",
            "dataset_id": "sales",
            "total_ms": 50,
            "run_sql_ms": 20,
        },
        {
            "timestamp": "2026-06-11T10:01:00",
            "route": "/api/v0/search",
            "status": "error",
            "dataset_id": "sales",
            "total_ms": 80,
            "run_sql_ms": 0,
        },
        {
            "timestamp": "2026-06-11T10:02:00",
            "route": "/api/v0/generate_sql",
            "status": "success",
            "dataset_id": "crm",
            "total_ms": 30,
            "run_sql_ms": 0,
        },
    ]
    event_path.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in events) + "\n",
        encoding="utf-8",
    )


def test_observability_api_lists_recent_events(monkeypatch, tmp_path: Path):
    app_module = _load_app_module(monkeypatch, tmp_path)
    _write_event_file(tmp_path / "events")

    response = app_module.app.test_client().get(
        "/api/v0/observability/routes/recent",
        query_string={"route": "/api/v0/search", "limit": 2},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert len(payload["data"]["events"]) == 2
    assert all(item["route"] == "/api/v0/search" for item in payload["data"]["events"])


def test_observability_api_returns_route_summary(monkeypatch, tmp_path: Path):
    app_module = _load_app_module(monkeypatch, tmp_path)
    _write_event_file(tmp_path / "events")

    response = app_module.app.test_client().get(
        "/api/v0/observability/routes/summary",
        query_string={"route": "/api/v0/search"},
    )

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["route"] == "/api/v0/search"
    assert payload["total_count"] == 2
    assert payload["success_count"] == 1
    assert payload["error_count"] == 1
