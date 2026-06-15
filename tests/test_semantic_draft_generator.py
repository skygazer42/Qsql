import json
from pathlib import Path

from src.qsql.metadata_store import MetadataStore
from src.qsql.semantic_draft_generator import (
    generate_semantic_catalog_draft,
    write_semantic_catalog_draft,
)


def _build_store(tmp_path: Path) -> MetadataStore:
    store = MetadataStore(tmp_path / "semantic_metadata.sqlite3")
    store.initialize()
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
                "column_name": "city_name",
                "data_type": "varchar",
                "column_comment": "城市",
                "is_primary_key": 0,
                "is_foreign_key": 0,
                "is_nullable": 1,
                "ordinal_position": 2,
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
                "ordinal_position": 3,
                "sample_values_json": None,
            },
            {
                "table_name": "sales_orders",
                "column_name": "amount",
                "data_type": "decimal",
                "column_comment": "订单金额",
                "is_primary_key": 0,
                "is_foreign_key": 0,
                "is_nullable": 0,
                "ordinal_position": 4,
                "sample_values_json": None,
            },
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
    return store


def test_generate_semantic_catalog_draft_returns_formal_catalog(tmp_path: Path):
    store = _build_store(tmp_path)

    draft = generate_semantic_catalog_draft(store=store, dataset_id="sales")

    assert draft.catalog.dataset_id == "sales"
    assert draft.catalog.tables[0].key == "sales_orders"
    assert draft.catalog.tables[0].physical_table == "sales_orders"
    assert draft.catalog.tables[0].default_time_dimension_key == "order_date"
    assert any(dimension.key == "city_name" for dimension in draft.catalog.dimensions)
    assert any(dimension.key == "order_date" for dimension in draft.catalog.dimensions)
    assert any(metric.key == "sales_orders_count" for metric in draft.catalog.metrics)
    assert draft.value_mapping_hints[0]["nl_term"] == "杭州市"


def test_write_semantic_catalog_draft_writes_json_file(tmp_path: Path):
    store = _build_store(tmp_path)
    draft_dir = tmp_path / "semantic_drafts"

    output_path = write_semantic_catalog_draft(
        store=store,
        dataset_id="sales",
        output_dir=draft_dir,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert output_path.name == "sales.json"
    assert payload["dataset_id"] == "sales"
    assert payload["tables"][0]["physical_table"] == "sales_orders"


def test_generate_semantic_catalog_draft_includes_join_entities_and_relationships(
    tmp_path: Path,
):
    store = MetadataStore(tmp_path / "semantic_metadata.sqlite3")
    store.initialize()
    store.replace_schema_metadata(
        dataset_id="sales_join",
        tables=[
            {
                "table_name": "sales_orders",
                "table_type": "BASE TABLE",
                "table_comment": "销售订单事实表",
                "semantic_table_key": None,
                "is_enabled": 1,
            },
            {
                "table_name": "dim_customers",
                "table_type": "BASE TABLE",
                "table_comment": "客户维表",
                "semantic_table_key": None,
                "is_enabled": 1,
            },
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
                "column_name": "customer_id",
                "data_type": "bigint",
                "column_comment": "客户ID",
                "is_primary_key": 0,
                "is_foreign_key": 1,
                "is_nullable": 0,
                "ordinal_position": 2,
                "sample_values_json": None,
            },
            {
                "table_name": "sales_orders",
                "column_name": "amount",
                "data_type": "decimal",
                "column_comment": "订单金额",
                "is_primary_key": 0,
                "is_foreign_key": 0,
                "is_nullable": 0,
                "ordinal_position": 3,
                "sample_values_json": None,
            },
            {
                "table_name": "dim_customers",
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
                "table_name": "dim_customers",
                "column_name": "city_name",
                "data_type": "varchar",
                "column_comment": "城市",
                "is_primary_key": 0,
                "is_foreign_key": 0,
                "is_nullable": 1,
                "ordinal_position": 2,
                "sample_values_json": None,
            },
        ],
        relationships=[
            {
                "source_table_name": "sales_orders",
                "source_column_name": "customer_id",
                "target_table_name": "dim_customers",
                "target_column_name": "id",
                "relationship_type": "foreign_key",
                "description": "订单关联客户",
            }
        ],
    )

    draft = generate_semantic_catalog_draft(store=store, dataset_id="sales_join")

    assert any(entity.key == "sales_orders_customer_id" for entity in draft.catalog.entities)
    assert any(entity.key == "dim_customers_id" for entity in draft.catalog.entities)
    assert any(
        relationship.left_entity_key == "sales_orders_customer_id"
        and relationship.right_entity_key == "dim_customers_id"
        for relationship in draft.catalog.relationships
    )
