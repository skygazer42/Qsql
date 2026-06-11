import importlib
import sys
from pathlib import Path

from src.qsql.metadata_store import MetadataStore


def _load_app_module(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "EMPTY")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "http://127.0.0.1:3000/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "test-embedding")
    monkeypatch.setenv("EMBEDDING_API_KEY", "EMPTY")
    monkeypatch.setenv("SECRET_ACCESS_KEY", "")
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "db"))
    sys.modules.pop("app", None)
    sys.modules.pop("src.server.metadata_api", None)
    return importlib.import_module("app")


def _prepare_metadata_store(tmp_path: Path):
    store = MetadataStore(tmp_path / "semantic_metadata.sqlite3")
    store.initialize()
    return store


def test_metadata_api_upserts_connection_and_lists_schema(monkeypatch, tmp_path: Path):
    app_module = _load_app_module(monkeypatch, tmp_path)
    metadata_api_module = importlib.import_module("src.server.metadata_api")
    store = _prepare_metadata_store(tmp_path)
    metadata_api_module.set_metadata_store(store)

    response = app_module.app.test_client().post(
        "/api/v0/metadata/connection/upsert",
        json={
            "dataset_id": "sales",
            "db_type": "mysql",
            "host": "127.0.0.1",
            "port": 3306,
            "database_name": "sales_db",
            "username": "root",
            "password": "secret",
            "enabled": True,
        },
    )

    assert response.status_code == 200
    assert store.get_dataset_connection("sales") is not None

    store.replace_schema_metadata(
        dataset_id="sales",
        tables=[
            {
                "table_name": "sales_orders",
                "table_type": "BASE TABLE",
                "table_comment": "销售订单宽表",
                "semantic_table_key": "sales_order_wide",
                "is_enabled": 1,
            }
        ],
        columns=[
            {
                "table_name": "sales_orders",
                "column_name": "order_date",
                "data_type": "datetime",
                "column_comment": "下单日期",
                "is_primary_key": 0,
                "is_foreign_key": 0,
                "is_nullable": 0,
                "ordinal_position": 1,
                "sample_values_json": None,
            }
        ],
        relationships=[
            {
                "source_table_name": "sales_orders",
                "source_column_name": "customer_id",
                "target_table_name": "crm_customer",
                "target_column_name": "id",
                "relationship_type": "foreign_key",
                "description": None,
            }
        ],
    )

    tables_response = app_module.app.test_client().get("/api/v0/metadata/sales/tables")
    columns_response = app_module.app.test_client().get("/api/v0/metadata/sales/columns")
    relationships_response = app_module.app.test_client().get(
        "/api/v0/metadata/sales/relationships"
    )

    assert tables_response.status_code == 200
    assert tables_response.get_json()["data"][0]["table_name"] == "sales_orders"
    assert columns_response.get_json()["data"][0]["column_name"] == "order_date"
    assert (
        relationships_response.get_json()["data"][0]["target_table_name"]
        == "crm_customer"
    )


def test_metadata_api_sync_route_uses_registered_runner(monkeypatch, tmp_path: Path):
    app_module = _load_app_module(monkeypatch, tmp_path)
    metadata_api_module = importlib.import_module("src.server.metadata_api")
    store = _prepare_metadata_store(tmp_path)
    metadata_api_module.set_metadata_store(store)

    captured = {}

    def _fake_sync_runner(*, store, dataset_id):
        captured["dataset_id"] = dataset_id
        store.create_sync_job(dataset_id=dataset_id)
        return {"table_count": 2, "column_count": 8, "relationship_count": 1}

    metadata_api_module.set_schema_sync_runner(_fake_sync_runner)

    response = app_module.app.test_client().post(
        "/api/v0/metadata/schema/sync",
        json={"dataset_id": "sales"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["dataset_id"] == "sales"
    assert payload["data"]["table_count"] == 2
    assert captured["dataset_id"] == "sales"


def test_metadata_api_replaces_and_lists_value_mappings(monkeypatch, tmp_path: Path):
    app_module = _load_app_module(monkeypatch, tmp_path)
    metadata_api_module = importlib.import_module("src.server.metadata_api")
    store = _prepare_metadata_store(tmp_path)
    metadata_api_module.set_metadata_store(store)

    replace_response = app_module.app.test_client().post(
        "/api/v0/metadata/sales/value-mappings/replace",
        json={
            "mappings": [
                {
                    "table_name": "sales_orders",
                    "column_name": "city_name",
                    "nl_term": "杭州市",
                    "db_value": "杭州",
                    "match_mode": "eq",
                    "source": "manual",
                    "enabled": True,
                }
            ]
        },
    )

    list_response = app_module.app.test_client().get(
        "/api/v0/metadata/sales/value-mappings"
    )

    assert replace_response.status_code == 200
    assert list_response.status_code == 200
    assert list_response.get_json()["data"][0]["nl_term"] == "杭州市"


def test_metadata_api_generates_semantic_draft(monkeypatch, tmp_path: Path):
    app_module = _load_app_module(monkeypatch, tmp_path)
    metadata_api_module = importlib.import_module("src.server.metadata_api")
    store = _prepare_metadata_store(tmp_path)
    metadata_api_module.set_metadata_store(store)
    metadata_api_module.set_semantic_draft_dir(tmp_path / "semantic_drafts")

    store.replace_schema_metadata(
        dataset_id="sales",
        tables=[
            {
                "table_name": "sales_orders",
                "table_type": "BASE TABLE",
                "table_comment": "销售订单宽表",
                "semantic_table_key": None,
                "is_enabled": 1,
            }
        ],
        columns=[
            {
                "table_name": "sales_orders",
                "column_name": "id",
                "data_type": "bigint",
                "column_comment": "主键",
                "is_primary_key": 1,
                "is_foreign_key": 0,
                "is_nullable": 0,
                "ordinal_position": 1,
                "sample_values_json": None,
            },
            {
                "table_name": "sales_orders",
                "column_name": "order_date",
                "data_type": "datetime",
                "column_comment": "下单日期",
                "is_primary_key": 0,
                "is_foreign_key": 0,
                "is_nullable": 0,
                "ordinal_position": 2,
                "sample_values_json": None,
            },
        ],
        relationships=[],
    )

    response = app_module.app.test_client().post(
        "/api/v0/metadata/sales/semantic-draft/generate",
        json={"write_file": True},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["catalog"]["dataset_id"] == "sales"
    assert payload["data"]["catalog"]["tables"][0]["physical_table"] == "sales_orders"
    assert payload["data"]["output_path"].endswith("/semantic_drafts/sales.json")
