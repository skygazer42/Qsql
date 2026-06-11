import json
from pathlib import Path

from src.qsql.metadata_store import MetadataStore


def _build_store(metadata_db_path: Path):
    store = MetadataStore(metadata_db_path)
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


def test_generate_semantic_draft_script_writes_draft_file(tmp_path: Path, capsys):
    metadata_db_path = tmp_path / "semantic_metadata.sqlite3"
    output_dir = tmp_path / "semantic_drafts"
    _build_store(metadata_db_path)

    from scripts.generate_semantic_draft import main

    main(
        [
            "--dataset-id",
            "sales",
            "--metadata-db-path",
            str(metadata_db_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    output_path = output_dir / "sales.json"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    captured = capsys.readouterr()

    assert output_path.exists()
    assert payload["dataset_id"] == "sales"
    assert "sales_orders" in payload["tables"][0]["physical_table"]
    assert "output_path=" in captured.out
