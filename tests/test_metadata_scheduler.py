from pathlib import Path

from src.qsql.metadata_store import MetadataStore
from src.qsql.metadata_scheduler import (
    MetadataSyncScheduler,
    start_metadata_sync_scheduler,
)


def _build_store(tmp_path: Path) -> MetadataStore:
    store = MetadataStore(tmp_path / "semantic_metadata.sqlite3")
    store.initialize()
    return store


def _upsert_mysql_connection(store: MetadataStore, dataset_id: str, enabled: bool) -> None:
    store.upsert_dataset_connection(
        dataset_id=dataset_id,
        db_type="mysql",
        host="127.0.0.1",
        port=3306,
        database_name=f"{dataset_id}_db",
        username="root",
        password="secret",
        enabled=enabled,
    )


def test_metadata_sync_scheduler_syncs_only_enabled_datasets(tmp_path: Path):
    store = _build_store(tmp_path)
    _upsert_mysql_connection(store, "sales", enabled=True)
    _upsert_mysql_connection(store, "crm", enabled=False)
    called = []

    scheduler = MetadataSyncScheduler(
        store=store,
        sync_runner=lambda *, store, dataset_id: called.append(dataset_id)
        or {"table_count": 1, "column_count": 2, "relationship_count": 0},
        interval_seconds=60,
    )

    scheduler.run_pending_once()

    assert called == ["sales"]


class _FakeScheduler:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = False

    def start(self):
        self.started = True
        return self


def test_start_metadata_sync_scheduler_returns_started_scheduler_when_enabled(
    tmp_path: Path,
):
    store = _build_store(tmp_path)

    scheduler = start_metadata_sync_scheduler(
        store=store,
        enabled=True,
        interval_seconds=15,
        scheduler_factory=lambda **kwargs: _FakeScheduler(**kwargs),
    )

    assert scheduler is not None
    assert scheduler.started is True
    assert scheduler.kwargs["interval_seconds"] == 15


def test_start_metadata_sync_scheduler_returns_none_when_disabled(tmp_path: Path):
    store = _build_store(tmp_path)

    scheduler = start_metadata_sync_scheduler(
        store=store,
        enabled=False,
    )

    assert scheduler is None
