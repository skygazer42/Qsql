"""Structured route observability for the QSQL runtime."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from src.utils import setting


DEFAULT_QSQL_EVENT_DIR = Path(setting.QSQL_EVENT_LOG_DIR)


class StructuredEventLogger:
    """Write structured runtime events as JSON lines."""

    def __init__(self, base_dir: str | Path | None = None):
        env_dir = os.environ.get("QSQL_EVENT_LOG_DIR", "").strip()
        if base_dir is not None:
            self._base_dir = Path(base_dir)
        elif env_dir:
            self._base_dir = Path(env_dir)
        else:
            self._base_dir = DEFAULT_QSQL_EVENT_DIR

    def record(self, payload: dict[str, Any]) -> Path:
        # [CUSTOM] 将主链路事件落为 JSON Lines，便于后续做路由统计、耗时分析和异常审计。
        event = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            **payload,
        }
        self._base_dir.mkdir(parents=True, exist_ok=True)
        path = self._base_dir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        return path


class StructuredEventReader:
    """Read structured runtime events from JSONL files."""

    def __init__(self, base_dir: str | Path | None = None):
        env_dir = os.environ.get("QSQL_EVENT_LOG_DIR", "").strip()
        if base_dir is not None:
            self._base_dir = Path(base_dir)
        elif env_dir:
            self._base_dir = Path(env_dir)
        else:
            self._base_dir = DEFAULT_QSQL_EVENT_DIR

    def list_recent_events(
        self,
        *,
        route: str | None = None,
        limit: int = 20,
        dataset_id: str | None = None,
    ) -> list[dict[str, Any]]:
        # [CUSTOM] 运维侧按 route/dataset 读取最近事件，避免只能靠 grep 日志排查。
        events: list[dict[str, Any]] = []
        for event in self._iter_events_desc():
            if route is not None and event.get("route") != route:
                continue
            if dataset_id is not None and event.get("dataset_id") != dataset_id:
                continue
            events.append(event)
            if len(events) >= limit:
                break
        return events

    def summarize_route(
        self,
        *,
        route: str,
        dataset_id: str | None = None,
    ) -> dict[str, Any]:
        total_count = 0
        success_count = 0
        error_count = 0
        clarification_count = 0
        total_ms_sum = 0
        run_sql_ms_sum = 0
        total_ms_count = 0
        run_sql_ms_count = 0

        for event in self._iter_events_desc():
            if event.get("route") != route:
                continue
            if dataset_id is not None and event.get("dataset_id") != dataset_id:
                continue
            total_count += 1
            status = str(event.get("status") or "")
            if status == "success":
                success_count += 1
            elif status == "error":
                error_count += 1
            elif status == "clarification":
                clarification_count += 1

            if isinstance(event.get("total_ms"), int):
                total_ms_sum += int(event["total_ms"])
                total_ms_count += 1
            if isinstance(event.get("run_sql_ms"), int):
                run_sql_ms_sum += int(event["run_sql_ms"])
                run_sql_ms_count += 1

        return {
            "route": route,
            "dataset_id": dataset_id,
            "total_count": total_count,
            "success_count": success_count,
            "error_count": error_count,
            "clarification_count": clarification_count,
            "avg_total_ms": int(total_ms_sum / total_ms_count) if total_ms_count else 0,
            "avg_run_sql_ms": int(run_sql_ms_sum / run_sql_ms_count)
            if run_sql_ms_count
            else 0,
        }

    def _iter_events_desc(self):
        if not self._base_dir.exists():
            return
        for path in sorted(self._base_dir.glob("*.jsonl"), reverse=True):
            lines = path.read_text(encoding="utf-8").splitlines()
            for line in reversed(lines):
                if not line.strip():
                    continue
                yield json.loads(line)
