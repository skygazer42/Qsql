"""Periodic metadata schema synchronization."""

from __future__ import annotations

import os
import threading
from typing import Callable

from src.utils import Log

from .metadata_store import MetadataStore
from .schema_sync import sync_mysql_dataset_schema


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if value == "":
        return default
    return value in {"1", "true", "yes", "on"}


class MetadataSyncScheduler:
    """Background scheduler that periodically syncs enabled dataset schemas."""

    def __init__(
        self,
        *,
        store: MetadataStore,
        sync_runner: Callable[..., dict[str, int]] = sync_mysql_dataset_schema,
        interval_seconds: int = 1800,
        logger: Log | None = None,
    ):
        self._store = store
        self._sync_runner = sync_runner
        self._interval_seconds = interval_seconds
        self._logger = logger or Log()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        # [CUSTOM] 定时同步默认走守护线程，避免阻塞 Flask 主服务启动。
        if self._thread is not None and self._thread.is_alive():
            return self
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_forever,
            name="metadata-sync-scheduler",
            daemon=True,
        )
        self._thread.start()
        self._logger.info(
            f"[Metadata] 定时同步器已启动 interval_seconds={self._interval_seconds}"
        )
        return self

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1)

    def run_pending_once(self) -> None:
        connections = self._store.list_dataset_connections(enabled_only=True)
        for connection in connections:
            dataset_id = connection["dataset_id"]
            db_type = connection.get("db_type", "")
            if db_type != "mysql":
                self._logger.warning(
                    f"[Metadata] 跳过非 mysql 数据集 dataset_id={dataset_id} db_type={db_type}"
                )
                continue
            try:
                result = self._sync_runner(store=self._store, dataset_id=dataset_id)
                self._logger.info(
                    "[Metadata] 定时同步完成 "
                    f"dataset_id={dataset_id} "
                    f"table_count={result.get('table_count', 0)} "
                    f"column_count={result.get('column_count', 0)} "
                    f"relationship_count={result.get('relationship_count', 0)}"
                )
            except Exception as exc:
                self._logger.error(
                    f"[Metadata] 定时同步失败 dataset_id={dataset_id} "
                    f"error={type(exc).__name__}: {exc}"
                )

    def _run_forever(self) -> None:
        while not self._stop_event.is_set():
            self.run_pending_once()
            self._stop_event.wait(self._interval_seconds)


def start_metadata_sync_scheduler(
    *,
    store: MetadataStore,
    enabled: bool | None = None,
    interval_seconds: int | None = None,
    sync_runner: Callable[..., dict[str, int]] = sync_mysql_dataset_schema,
    scheduler_factory: Callable[..., MetadataSyncScheduler] = MetadataSyncScheduler,
):
    # [CUSTOM] 用环境变量控制是否启用定时同步，默认关闭，避免测试/本地开发无感启动后台线程。
    enabled_value = _env_flag("METADATA_SYNC_ENABLED", default=False) if enabled is None else enabled
    if not enabled_value:
        return None

    interval = (
        int(os.environ.get("METADATA_SYNC_INTERVAL_SECONDS", "1800"))
        if interval_seconds is None
        else int(interval_seconds)
    )
    scheduler = scheduler_factory(
        store=store,
        sync_runner=sync_runner,
        interval_seconds=interval,
    )
    return scheduler.start()
