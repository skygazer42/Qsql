"""Schema metadata synchronization for dataset-scoped MySQL connections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pymysql

from .metadata_store import MetadataStore


@dataclass
class ColumnInfo:
    table_name: str
    column_name: str
    data_type: str
    column_comment: str | None
    is_primary_key: bool
    is_foreign_key: bool
    is_nullable: bool
    ordinal_position: int


def _open_mysql_connection(connection: dict[str, Any]) -> pymysql.connections.Connection:
    return pymysql.connect(
        host=connection["host"],
        port=int(connection["port"]),
        user=connection["username"],
        password=connection.get("password") or "",
        database=connection["database_name"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def _load_mysql_tables(conn, database_name: str) -> list[dict[str, Any]]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                TABLE_NAME AS table_name,
                TABLE_TYPE AS table_type,
                TABLE_COMMENT AS table_comment
            FROM information_schema.tables
            WHERE TABLE_SCHEMA = %s
              AND TABLE_TYPE IN ('BASE TABLE', 'VIEW')
            """,
            (database_name,),
        )
        return list(cursor.fetchall())


def _load_mysql_columns(conn, database_name: str) -> list[ColumnInfo]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                TABLE_NAME,
                COLUMN_NAME,
                DATA_TYPE,
                COLUMN_KEY,
                IS_NULLABLE,
                ORDINAL_POSITION,
                COLUMN_COMMENT
            FROM information_schema.columns
            WHERE TABLE_SCHEMA = %s
            ORDER BY TABLE_NAME, ORDINAL_POSITION
            """,
            (database_name,),
        )
        rows = list(cursor.fetchall())

    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                TABLE_NAME,
                COLUMN_NAME
            FROM information_schema.key_column_usage
            WHERE TABLE_SCHEMA = %s
              AND REFERENCED_TABLE_NAME IS NOT NULL
            """,
            (database_name,),
        )
        fk_rows = {(row["TABLE_NAME"], row["COLUMN_NAME"]) for row in cursor.fetchall()}

    columns: list[ColumnInfo] = []
    for row in rows:
        column_key = (row.get("COLUMN_KEY") or "").upper()
        columns.append(
            ColumnInfo(
                table_name=row["TABLE_NAME"],
                column_name=row["COLUMN_NAME"],
                data_type=row.get("DATA_TYPE") or "",
                column_comment=row.get("COLUMN_COMMENT"),
                is_primary_key=column_key == "PRI",
                is_foreign_key=(row["TABLE_NAME"], row["COLUMN_NAME"]) in fk_rows,
                is_nullable=(row.get("IS_NULLABLE") or "").upper() == "YES",
                ordinal_position=int(row.get("ORDINAL_POSITION") or 0),
            )
        )
    return columns


def _load_mysql_relationships(conn, database_name: str) -> list[dict[str, Any]]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                TABLE_NAME AS source_table,
                COLUMN_NAME AS source_column,
                REFERENCED_TABLE_NAME AS target_table,
                REFERENCED_COLUMN_NAME AS target_column
            FROM information_schema.key_column_usage
            WHERE TABLE_SCHEMA = %s
              AND REFERENCED_TABLE_NAME IS NOT NULL
            """,
            (database_name,),
        )
        return list(cursor.fetchall())


def sync_mysql_dataset_schema(
    *,
    store: MetadataStore,
    dataset_id: str,
    connection_factory: Callable[[dict[str, Any]], Any] | None = None,
) -> dict[str, int]:
    """Sync MySQL schema metadata into the local metadata store."""
    connection = store.get_dataset_connection(dataset_id)
    if connection is None:
        raise ValueError(f"未找到数据集连接配置: {dataset_id}")
    if connection["db_type"] != "mysql":
        raise ValueError(f"当前仅支持 mysql 同步: {dataset_id}")

    job_id = store.create_sync_job(dataset_id=dataset_id)
    factory = connection_factory or _open_mysql_connection
    raw_connection = factory(connection)
    try:
        tables = _load_mysql_tables(raw_connection, connection["database_name"])
        columns = _load_mysql_columns(raw_connection, connection["database_name"])
        relationships = _load_mysql_relationships(raw_connection, connection["database_name"])

        store.replace_schema_metadata(
            dataset_id=dataset_id,
            tables=[
                {
                    "table_name": item["table_name"],
                    "table_type": item.get("table_type"),
                    "table_comment": item.get("table_comment"),
                    "semantic_table_key": None,
                    "is_enabled": 1,
                }
                for item in tables
            ],
            columns=[
                {
                    "table_name": item.table_name,
                    "column_name": item.column_name,
                    "data_type": item.data_type,
                    "column_comment": item.column_comment,
                    "is_primary_key": 1 if item.is_primary_key else 0,
                    "is_foreign_key": 1 if item.is_foreign_key else 0,
                    "is_nullable": 1 if item.is_nullable else 0,
                    "ordinal_position": item.ordinal_position,
                    "sample_values_json": None,
                }
                for item in columns
            ],
            relationships=[
                {
                    "source_table_name": item["source_table"],
                    "source_column_name": item["source_column"],
                    "target_table_name": item["target_table"],
                    "target_column_name": item["target_column"],
                    "relationship_type": "foreign_key",
                    "description": None,
                }
                for item in relationships
            ],
        )
        store.finish_sync_job(
            job_id=job_id,
            status="success",
            table_count=len(tables),
            column_count=len(columns),
            relationship_count=len(relationships),
        )
        store.update_dataset_sync_state(dataset_id=dataset_id, sync_status="success")
        return {
            "table_count": len(tables),
            "column_count": len(columns),
            "relationship_count": len(relationships),
        }
    except Exception as exc:
        store.finish_sync_job(
            job_id=job_id,
            status="error",
            table_count=0,
            column_count=0,
            relationship_count=0,
            error_message=str(exc),
        )
        store.update_dataset_sync_state(dataset_id=dataset_id, sync_status="error")
        raise
    finally:
        raw_connection.close()
