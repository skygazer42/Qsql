from pathlib import Path

from src.qsql.metadata_store import MetadataStore
from src.qsql.schemas import SemanticCatalog, ValidateRequest
from src.qsql.value_retriever import MetadataValueRetriever


def _catalog() -> SemanticCatalog:
    return ValidateRequest.parse(
        SemanticCatalog,
        {
            "catalog_version": "2026-06-15",
            "dataset_id": "sales",
            "tables": [
                {
                    "key": "orders_wide",
                    "label": "订单宽表",
                    "physical_table": "orders",
                }
            ],
            "metrics": [],
            "dimensions": [
                {
                    "key": "region",
                    "label": "区域",
                    "table_key": "orders_wide",
                    "field": "region_name",
                    "kind": "categorical",
                    "operators": ["eq"],
                }
            ],
            "aliases": [],
            "metric_versions": [],
        },
    )


def test_metadata_value_retriever_maps_natural_language_value_to_dimension(
    tmp_path: Path,
):
    store = MetadataStore(tmp_path / "semantic_metadata.sqlite3")
    store.initialize()
    store.replace_value_mappings(
        dataset_id="sales",
        mappings=[
            {
                "table_name": "orders",
                "column_name": "region_name",
                "nl_term": "华北",
                "db_value": "North China",
                "match_mode": "eq",
                "source": "manual",
                "enabled": 1,
            }
        ],
    )
    retriever = MetadataValueRetriever(store=store)

    matches = retriever.retrieve(
        question="2026年华北销售额是多少？",
        catalog=_catalog(),
        dimensions={"region": _catalog().dimensions[0]},
    )

    assert len(matches) == 1
    assert matches[0].dimension_key == "region"
    assert matches[0].db_value == "North China"


def test_metadata_value_retriever_uses_schema_sample_values(tmp_path: Path):
    store = MetadataStore(tmp_path / "semantic_metadata.sqlite3")
    store.initialize()
    store.replace_schema_metadata(
        dataset_id="sales",
        tables=[
            {
                "table_name": "orders",
                "table_type": "BASE TABLE",
                "table_comment": "订单表",
                "semantic_table_key": "orders_wide",
                "is_enabled": 1,
            }
        ],
        columns=[
            {
                "table_name": "orders",
                "column_name": "region_name",
                "data_type": "varchar",
                "column_comment": "区域",
                "is_primary_key": 0,
                "is_foreign_key": 0,
                "is_nullable": 1,
                "ordinal_position": 1,
                "sample_values_json": '["North China"]',
            }
        ],
        relationships=[],
    )
    retriever = MetadataValueRetriever(store=store)

    matches = retriever.retrieve(
        question="2026年North China销售额是多少？",
        catalog=_catalog(),
        dimensions={"region": _catalog().dimensions[0]},
    )

    assert len(matches) == 1
    assert matches[0].source == "metadata_sample"
    assert matches[0].dimension_key == "region"
    assert matches[0].db_value == "North China"
