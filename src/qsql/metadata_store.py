"""SQLite-backed metadata repository for schema sync and semantic management."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

from src.utils import setting


DEFAULT_METADATA_DB_PATH = Path(setting.METADATA_DB_PATH)


class MetadataStore:
    """Store dataset-scoped schema metadata, value mappings, and sync jobs."""

    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(db_path) if db_path is not None else DEFAULT_METADATA_DB_PATH

    def initialize(self) -> None:
        # [CUSTOM] 使用独立 SQLite 保存 schema 元数据与同步任务，
        # 避免把运行时语义目录和运维元数据耦合在一起。
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS dataset_connection (
                    dataset_id TEXT PRIMARY KEY,
                    db_type TEXT NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    database_name TEXT NOT NULL,
                    username TEXT NOT NULL,
                    password TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_sync_at TEXT,
                    sync_status TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS schema_table (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_id TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    table_type TEXT,
                    table_comment TEXT,
                    semantic_table_key TEXT,
                    is_enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS schema_column (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_id TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    column_name TEXT NOT NULL,
                    data_type TEXT NOT NULL,
                    column_comment TEXT,
                    is_primary_key INTEGER NOT NULL DEFAULT 0,
                    is_foreign_key INTEGER NOT NULL DEFAULT 0,
                    is_nullable INTEGER NOT NULL DEFAULT 1,
                    ordinal_position INTEGER NOT NULL DEFAULT 0,
                    sample_values_json TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS schema_relationship (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_id TEXT NOT NULL,
                    source_table_name TEXT NOT NULL,
                    source_column_name TEXT NOT NULL,
                    target_table_name TEXT NOT NULL,
                    target_column_name TEXT NOT NULL,
                    relationship_type TEXT,
                    description TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS value_mapping (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_id TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    column_name TEXT NOT NULL,
                    nl_term TEXT NOT NULL,
                    db_value TEXT NOT NULL,
                    match_mode TEXT NOT NULL DEFAULT 'eq',
                    source TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS metadata_sync_job (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_id TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    finished_at TEXT,
                    status TEXT NOT NULL DEFAULT 'running',
                    table_count INTEGER NOT NULL DEFAULT 0,
                    column_count INTEGER NOT NULL DEFAULT 0,
                    relationship_count INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT
                );
                """
            )
            self._ensure_column(conn, "dataset_connection", "password", "TEXT NOT NULL DEFAULT ''")

    def upsert_dataset_connection(
        self,
        *,
        dataset_id: str,
        db_type: str,
        host: str,
        port: int,
        database_name: str,
        username: str,
        password: str,
        enabled: bool,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO dataset_connection (
                    dataset_id, db_type, host, port, database_name, username, password, enabled, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(dataset_id) DO UPDATE SET
                    db_type = excluded.db_type,
                    host = excluded.host,
                    port = excluded.port,
                    database_name = excluded.database_name,
                    username = excluded.username,
                    password = excluded.password,
                    enabled = excluded.enabled,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    dataset_id,
                    db_type,
                    host,
                    port,
                    database_name,
                    username,
                    password,
                    1 if enabled else 0,
                ),
            )

    def get_dataset_connection(self, dataset_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM dataset_connection WHERE dataset_id = ?",
                (dataset_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def list_dataset_connections(self, *, enabled_only: bool = False) -> list[dict[str, Any]]:
        # [CUSTOM] 定时同步器按数据集连接清单驱动，避免把同步对象硬编码在任务里。
        if enabled_only:
            return self._fetch_all(
                """
                SELECT * FROM dataset_connection
                WHERE enabled = 1
                ORDER BY dataset_id ASC
                """,
                (),
            )
        return self._fetch_all(
            """
            SELECT * FROM dataset_connection
            ORDER BY dataset_id ASC
            """,
            (),
        )

    def update_dataset_sync_state(
        self,
        *,
        dataset_id: str,
        sync_status: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE dataset_connection
                SET sync_status = ?,
                    last_sync_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE dataset_id = ?
                """,
                (sync_status, dataset_id),
            )

    def create_sync_job(self, *, dataset_id: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO metadata_sync_job (dataset_id) VALUES (?)",
                (dataset_id,),
            )
            return int(cursor.lastrowid)

    def finish_sync_job(
        self,
        *,
        job_id: int,
        status: str,
        table_count: int,
        column_count: int,
        relationship_count: int,
        error_message: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE metadata_sync_job
                SET finished_at = CURRENT_TIMESTAMP,
                    status = ?,
                    table_count = ?,
                    column_count = ?,
                    relationship_count = ?,
                    error_message = ?
                WHERE id = ?
                """,
                (
                    status,
                    table_count,
                    column_count,
                    relationship_count,
                    error_message,
                    job_id,
                ),
            )

    def list_sync_jobs(self, dataset_id: str) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT * FROM metadata_sync_job
            WHERE dataset_id = ?
            ORDER BY id DESC
            """,
            (dataset_id,),
        )

    def replace_schema_metadata(
        self,
        *,
        dataset_id: str,
        tables: list[dict[str, Any]],
        columns: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
    ) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM schema_relationship WHERE dataset_id = ?", (dataset_id,))
            conn.execute("DELETE FROM schema_column WHERE dataset_id = ?", (dataset_id,))
            conn.execute("DELETE FROM schema_table WHERE dataset_id = ?", (dataset_id,))
            self._insert_many(
                conn,
                """
                INSERT INTO schema_table (
                    dataset_id, table_name, table_type, table_comment, semantic_table_key, is_enabled
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        dataset_id,
                        item["table_name"],
                        item.get("table_type"),
                        item.get("table_comment"),
                        item.get("semantic_table_key"),
                        item.get("is_enabled", 1),
                    )
                    for item in tables
                ),
            )
            self._insert_many(
                conn,
                """
                INSERT INTO schema_column (
                    dataset_id, table_name, column_name, data_type, column_comment,
                    is_primary_key, is_foreign_key, is_nullable, ordinal_position, sample_values_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        dataset_id,
                        item["table_name"],
                        item["column_name"],
                        item["data_type"],
                        item.get("column_comment"),
                        item.get("is_primary_key", 0),
                        item.get("is_foreign_key", 0),
                        item.get("is_nullable", 1),
                        item.get("ordinal_position", 0),
                        item.get("sample_values_json"),
                    )
                    for item in columns
                ),
            )
            self._insert_many(
                conn,
                """
                INSERT INTO schema_relationship (
                    dataset_id, source_table_name, source_column_name,
                    target_table_name, target_column_name, relationship_type, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        dataset_id,
                        item["source_table_name"],
                        item["source_column_name"],
                        item["target_table_name"],
                        item["target_column_name"],
                        item.get("relationship_type"),
                        item.get("description"),
                    )
                    for item in relationships
                ),
            )

    def list_schema_tables(self, dataset_id: str) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT * FROM schema_table
            WHERE dataset_id = ?
            ORDER BY table_name ASC
            """,
            (dataset_id,),
        )

    def list_schema_columns(self, dataset_id: str) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT * FROM schema_column
            WHERE dataset_id = ?
            ORDER BY table_name ASC, ordinal_position ASC, column_name ASC
            """,
            (dataset_id,),
        )

    def list_schema_relationships(self, dataset_id: str) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT * FROM schema_relationship
            WHERE dataset_id = ?
            ORDER BY source_table_name ASC, source_column_name ASC
            """,
            (dataset_id,),
        )

    def replace_value_mappings(
        self,
        *,
        dataset_id: str,
        mappings: list[dict[str, Any]],
    ) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM value_mapping WHERE dataset_id = ?", (dataset_id,))
            self._insert_many(
                conn,
                """
                INSERT INTO value_mapping (
                    dataset_id, table_name, column_name, nl_term, db_value,
                    match_mode, source, enabled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        dataset_id,
                        item["table_name"],
                        item["column_name"],
                        item["nl_term"],
                        item["db_value"],
                        item.get("match_mode", "eq"),
                        item.get("source"),
                        item.get("enabled", 1),
                    )
                    for item in mappings
                ),
            )

    def list_value_mappings(self, dataset_id: str) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT * FROM value_mapping
            WHERE dataset_id = ?
            ORDER BY table_name ASC, column_name ASC, nl_term ASC
            """,
            (dataset_id,),
        )

    def _fetch_all(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _insert_many(
        conn: sqlite3.Connection,
        sql: str,
        rows: Iterable[tuple[Any, ...]],
    ) -> None:
        materialized = list(rows)
        if materialized:
            conn.executemany(sql, materialized)

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_sql: str,
    ) -> None:
        columns = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn
