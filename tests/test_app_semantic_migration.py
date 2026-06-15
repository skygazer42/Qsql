import importlib
import json
import sys
from pathlib import Path

import pandas as pd

from src.qsql.schemas import (
    QueryExecutionPlan,
    SemanticParseResponse,
    SemanticQueryDraft,
    SemanticStageTimings,
    SemanticTimeRange,
)


class _FakeSemanticService:
    def __init__(self) -> None:
        self.requests = []

    def prepare_query(self, request_model):
        self.requests.append(request_model)
        return SemanticParseResponse(
            dataset_id=request_model.dataset_id,
            question=request_model.question,
            status="ready",
            clarification_question=None,
            semantic_query=SemanticQueryDraft(
                analysis_type="summary",
                metric_key="order_amount",
                group_by_dimension_keys=[],
                filters=[],
                time_range=SemanticTimeRange(
                    dimension_key="order_date",
                    start="2026-01-01",
                    end="2026-01-31",
                ),
                metric_version_key=None,
                needs_clarification=False,
                clarification_question=None,
            ),
            execution_plan=QueryExecutionPlan(
                dataset_id=request_model.dataset_id,
                table="sales_orders",
                sql="SELECT 1 AS metric_value",
                parameters=[],
                analysis_type="summary",
                metric_key="order_amount",
                metric_label="订单金额",
                group_by_dimension_keys=[],
            ),
            timings=SemanticStageTimings(
                catalog_load_ms=1,
                semantic_agent_ms=2,
                sql_build_ms=3,
                total_ms=6,
            ),
        )


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
    sys.modules.pop("app", None)
    return importlib.import_module("app")


def test_generate_sql_v0_uses_semantic_service(monkeypatch, tmp_path: Path):
    app_module = _load_app_module(monkeypatch, tmp_path)
    fake_service = _FakeSemanticService()
    app_module.__semantic_query_service = fake_service
    app_module.vn.generate_sql = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("old vn.generate_sql should not be called")
    )

    response = app_module.app.test_client().get(
        "/api/v0/generate_sql",
        query_string={"dataset_id": "sales", "question": "成交金额是多少"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["type"] == "sql"
    assert payload["text"] == "SELECT 1 AS metric_value"
    assert fake_service.requests[0].dataset_id == "sales"


def test_search_v0_uses_semantic_service(monkeypatch, tmp_path: Path):
    app_module = _load_app_module(monkeypatch, tmp_path)
    fake_service = _FakeSemanticService()
    app_module.__semantic_query_service = fake_service
    app_module.vn.generate_sql = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("old vn.generate_sql should not be called")
    )
    captured_sql = []

    def _fake_run_sql(*, sql):
        captured_sql.append(sql)
        return pd.DataFrame([{"metric_value": 1}])

    app_module.vn.run_sql = _fake_run_sql

    response = app_module.app.test_client().post(
        "/api/v0/search",
        json={"dataset_id": "sales", "question": "成交金额是多少"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == 0
    assert payload["data"]["df"] == '[{"metric_value":1}]'
    assert captured_sql == ["SELECT 1 AS metric_value"]
    assert fake_service.requests[0].dataset_id == "sales"


def test_app_no_longer_exposes_v1_semantic_routes(monkeypatch, tmp_path: Path):
    app_module = _load_app_module(monkeypatch, tmp_path)
    semantic_rules = {
        rule.rule
        for rule in app_module.app.url_map.iter_rules()
        if "/api/v1/query/semantic/" in rule.rule
    }

    assert semantic_rules == set()


def test_generate_sql_v0_writes_structured_route_event(monkeypatch, tmp_path: Path):
    event_dir = tmp_path / "events"
    monkeypatch.setenv("QSQL_EVENT_LOG_DIR", str(event_dir))
    app_module = _load_app_module(monkeypatch, tmp_path)
    fake_service = _FakeSemanticService()
    app_module.__semantic_query_service = fake_service

    response = app_module.app.test_client().get(
        "/api/v0/generate_sql",
        query_string={"dataset_id": "sales", "question": "成交金额是多少"},
    )

    assert response.status_code == 200

    event_files = sorted(event_dir.glob("*.jsonl"))
    assert event_files

    lines = event_files[0].read_text(encoding="utf-8").strip().splitlines()
    assert lines
    event = json.loads(lines[-1])
    assert event["route"] == "/api/v0/generate_sql"
    assert event["status"] == "success"
    assert event["dataset_id"] == "sales"
    assert event["request_id"]
    assert event["semantic_parse_ms"] >= 0
    assert event["catalog_load_ms"] == 1
    assert event["semantic_agent_ms"] == 2
    assert event["sql_build_ms"] == 3


def test_search_v0_writes_structured_route_event(monkeypatch, tmp_path: Path):
    event_dir = tmp_path / "events"
    monkeypatch.setenv("QSQL_EVENT_LOG_DIR", str(event_dir))
    app_module = _load_app_module(monkeypatch, tmp_path)
    fake_service = _FakeSemanticService()
    app_module.__semantic_query_service = fake_service
    app_module.vn.run_sql = lambda *, sql: pd.DataFrame([{"metric_value": 1}])

    response = app_module.app.test_client().post(
        "/api/v0/search",
        json={"dataset_id": "sales", "question": "成交金额是多少"},
    )

    assert response.status_code == 200

    event_files = sorted(event_dir.glob("*.jsonl"))
    assert event_files

    lines = event_files[0].read_text(encoding="utf-8").strip().splitlines()
    event = json.loads(lines[-1])
    assert event["route"] == "/api/v0/search"
    assert event["status"] == "success"
    assert event["dataset_id"] == "sales"
    assert event["catalog_load_ms"] == 1
    assert event["semantic_agent_ms"] == 2
    assert event["sql_build_ms"] == 3
    assert event["run_sql_ms"] >= 0
    assert event["row_count"] == 1
