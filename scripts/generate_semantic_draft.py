#!/usr/bin/env python
"""Generate a semantic catalog draft from metadata store records."""

from __future__ import annotations

import argparse

from src.qsql.metadata_store import MetadataStore
from src.qsql.semantic_draft_generator import write_semantic_catalog_draft


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="从 metadata 元数据生成语义草稿")
    parser.add_argument("--dataset-id", required=True, help="语义数据集 ID")
    parser.add_argument(
        "--metadata-db-path",
        default=None,
        help="元数据库路径，默认使用 resources/metadata/semantic_metadata.sqlite3",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="语义草稿输出目录，默认使用 resources/semantic_drafts",
    )
    args = parser.parse_args(argv)

    # [CUSTOM] 提供 metadata -> semantic draft 的离线入口，便于业务接入前先生成草稿审阅。
    store = MetadataStore(args.metadata_db_path)
    store.initialize()
    output_path = write_semantic_catalog_draft(
        store=store,
        dataset_id=args.dataset_id,
        output_dir=args.output_dir,
    )
    print(f"dataset_id={args.dataset_id} output_path={output_path}")


if __name__ == "__main__":
    main()
