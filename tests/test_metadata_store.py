from pathlib import Path

from src.qsql.metadata_store import MetadataStore
from src.qsql.schema_sync import sync_mysql_dataset_schema


def test_metadata_store_initializes_schema_and_round_trips_records(tmp_path: Path):
    db_path = tmp_path / "semantic_metadata.sqlite3"
    store = MetadataStore(db_path)

    store.initialize()
    store.upsert_dataset_connection(
        dataset_id="sales",
        db_type="mysql",
        host="127.0.0.1",
        port=3306,
        database_name="sales_db",
        username="root",
        password="secret",
        enabled=True,
    )
    job_id = store.create_sync_job(dataset_id="sales")
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
                "sample_values_json": '["2026-01-01"]',
            }
        ],
        relationships=[],
    )
    store.replace_value_mappings(
        dataset_id="sales",
        mappings=[
            {
                "table_name": "sales_orders",
                "column_name": "city_name",
                "nl_term": "杭州市",
                "db_value": "杭州",
                "match_mode": "eq",
                "source": "manual",
                "enabled": 1,
            }
        ],
    )
    store.finish_sync_job(
        job_id=job_id,
        status="success",
        table_count=1,
        column_count=1,
        relationship_count=0,
    )

    connection = store.get_dataset_connection("sales")
    tables = store.list_schema_tables("sales")
    columns = store.list_schema_columns("sales")
    mappings = store.list_value_mappings("sales")
    jobs = store.list_sync_jobs("sales")

    assert connection is not None
    assert connection["database_name"] == "sales_db"
    assert connection["password"] == "secret"
    assert tables[0]["semantic_table_key"] == "sales_order_wide"
    assert columns[0]["column_name"] == "order_date"
    assert mappings[0]["nl_term"] == "杭州市"
    assert jobs[0]["status"] == "success"


class _FakeCursor:
    def __init__(self, rows_by_query: dict[str, list[dict]]):
        self._rows_by_query = rows_by_query
        self._rows = []

    def execute(self, sql: str, params):
        if "information_schema.tables" in sql:
            self._rows = self._rows_by_query["tables"]
        elif "information_schema.columns" in sql:
            self._rows = self._rows_by_query["columns"]
        elif "REFERENCED_TABLE_NAME IS NOT NULL" in sql and "AS source_table" not in sql:
            self._rows = self._rows_by_query["foreign_keys"]
        elif "AS source_table" in sql:
            self._rows = self._rows_by_query["relationships"]
        else:
            raise AssertionError(f"unexpected sql: {sql}")

    def fetchall(self):
        return list(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeConnection:
    def __init__(self, rows_by_query: dict[str, list[dict]]):
        self._rows_by_query = rows_by_query
        self.closed = False

    def cursor(self):
        return _FakeCursor(self._rows_by_query)

    def close(self):
        self.closed = True


def test_sync_mysql_dataset_schema_persists_tables_columns_and_relationships(tmp_path: Path):
    db_path = tmp_path / "semantic_metadata.sqlite3"
    store = MetadataStore(db_path)
    store.initialize()
    store.upsert_dataset_connection(
        dataset_id="sales",
        db_type="mysql",
        host="127.0.0.1",
        port=3306,
        database_name="sales_db",
        username="root",
        password="secret",
        enabled=True,
    )

    fake_connection = _FakeConnection(
        {
            "tables": [
                {"table_name": "sales_orders", "table_type": "BASE TABLE", "table_comment": "销售订单宽表"}
            ],
            "columns": [
                {
                    "TABLE_NAME": "sales_orders",
                    "COLUMN_NAME": "id",
                    "DATA_TYPE": "bigint",
                    "COLUMN_KEY": "PRI",
                    "IS_NULLABLE": "NO",
                    "ORDINAL_POSITION": 1,
                    "COLUMN_COMMENT": "主键",
                },
                {
                    "TABLE_NAME": "sales_orders",
                    "COLUMN_NAME": "customer_id",
                    "DATA_TYPE": "bigint",
                    "COLUMN_KEY": "",
                    "IS_NULLABLE": "YES",
                    "ORDINAL_POSITION": 2,
                    "COLUMN_COMMENT": "客户ID",
                },
            ],
            "foreign_keys": [{"TABLE_NAME": "sales_orders", "COLUMN_NAME": "customer_id"}],
            "relationships": [
                {
                    "source_table": "sales_orders",
                    "source_column": "customer_id",
                    "target_table": "crm_customer",
                    "target_column": "id",
                }
            ],
        }
    )

    result = sync_mysql_dataset_schema(
        store=store,
        dataset_id="sales",
        connection_factory=lambda connection: fake_connection,
    )

    tables = store.list_schema_tables("sales")
    columns = store.list_schema_columns("sales")
    relationships = store.list_schema_relationships("sales")
    connection = store.get_dataset_connection("sales")
    jobs = store.list_sync_jobs("sales")

    assert result["table_count"] == 1
    assert result["column_count"] == 2
    assert result["relationship_count"] == 1
    assert tables[0]["table_name"] == "sales_orders"
    assert columns[1]["is_foreign_key"] == 1
    assert relationships[0]["target_table_name"] == "crm_customer"
    assert connection["sync_status"] == "success"
    assert connection["last_sync_at"] is not None
    assert jobs[0]["status"] == "success"
    assert fake_connection.closed is True
