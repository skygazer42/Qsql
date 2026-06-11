#!/usr/bin/env python
"""Manual entrypoint for dataset-scoped MySQL schema synchronization."""

from __future__ import annotations

import argparse

from src.qsql.metadata_store import MetadataStore
from src.qsql.schema_sync import sync_mysql_dataset_schema


def main() -> None:
    parser = argparse.ArgumentParser(description="同步指定 dataset_id 的 MySQL Schema 元数据")
    parser.add_argument("--dataset-id", required=True, help="语义数据集 ID")
    parser.add_argument(
        "--metadata-db-path",
        default=None,
        help="元数据库路径，默认使用 resources/metadata/semantic_metadata.sqlite3",
    )
    args = parser.parse_args()

    # [CUSTOM] 提供最小可用的人工同步入口，后续调度器和运维入口都基于同一同步模块复用。
    store = MetadataStore(args.metadata_db_path)
    store.initialize()
    result = sync_mysql_dataset_schema(store=store, dataset_id=args.dataset_id)
    print(
        f"dataset_id={args.dataset_id} table_count={result['table_count']} "
        f"column_count={result['column_count']} relationship_count={result['relationship_count']}"
    )


if __name__ == "__main__":
    main()
