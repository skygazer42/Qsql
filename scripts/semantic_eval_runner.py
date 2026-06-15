#!/usr/bin/env python
"""Run dataset-scoped semantic query evaluation cases."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    # [CUSTOM] 支持 `python scripts/semantic_eval_runner.py` 直接运行。
    sys.path.insert(0, str(REPO_ROOT))

from src.qsql.schemas import SemanticFilter, SemanticParseResponse, SemanticQueryRequest  # noqa: E402
from src.qsql.semantic_service import SemanticQueryService  # noqa: E402


@dataclass
class EvalCase:
    id: str
    question: str
    level: str | None = None
    category: str | None = None
    expect_status: str = "ready"
    expect_metric_key: str | None = None
    expect_group_by: list[str] | None = None
    expect_filters: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class EvalResult:
    case_id: str
    question: str
    status: str
    ok: bool
    level: str | None = None
    category: str | None = None
    failure_reason: str | None = None
    row_count: int = 0
    sql: str | None = None


def load_cases(path: Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            payload = json.loads(stripped)
            cases.append(
                EvalCase(
                    id=str(payload.get("id") or f"case_{line_no}"),
                    question=str(payload["question"]),
                    level=payload.get("level"),
                    category=payload.get("category"),
                    expect_status=str(payload.get("expect_status") or "ready"),
                    expect_metric_key=payload.get("expect_metric_key"),
                    expect_group_by=payload.get("expect_group_by"),
                    expect_filters=payload.get("expect_filters") or [],
                )
            )
    return cases


def _filter_matches(actual: SemanticFilter, expected: dict[str, Any]) -> bool:
    for key in ("dimension_key", "operator", "value"):
        if key in expected and getattr(actual, key) != expected[key]:
            return False
    return True


def evaluate_case(
    case: EvalCase,
    response: SemanticParseResponse,
    *,
    rows: list[dict[str, Any]] | None,
) -> EvalResult:
    sql = response.execution_plan.sql if response.execution_plan else None
    row_count = len(rows or [])

    if response.status != case.expect_status:
        return EvalResult(
            case_id=case.id,
            question=case.question,
            level=case.level,
            category=case.category,
            status=response.status,
            ok=False,
            failure_reason="status_mismatch",
            row_count=row_count,
            sql=sql,
        )

    if case.expect_status == "clarification":
        return EvalResult(
            case_id=case.id,
            question=case.question,
            level=case.level,
            category=case.category,
            status=response.status,
            ok=True,
            row_count=row_count,
            sql=sql,
        )

    semantic_query = response.semantic_query
    if semantic_query is None:
        return EvalResult(
            case_id=case.id,
            question=case.question,
            level=case.level,
            category=case.category,
            status=response.status,
            ok=False,
            failure_reason="missing_semantic_query",
            row_count=row_count,
            sql=sql,
        )

    if case.expect_metric_key and semantic_query.metric_key != case.expect_metric_key:
        return EvalResult(
            case_id=case.id,
            question=case.question,
            level=case.level,
            category=case.category,
            status=response.status,
            ok=False,
            failure_reason="metric_mismatch",
            row_count=row_count,
            sql=sql,
        )

    if case.expect_group_by is not None and set(
        semantic_query.group_by_dimension_keys
    ) != set(case.expect_group_by):
        return EvalResult(
            case_id=case.id,
            question=case.question,
            level=case.level,
            category=case.category,
            status=response.status,
            ok=False,
            failure_reason="group_by_mismatch",
            row_count=row_count,
            sql=sql,
        )

    for expected_filter in case.expect_filters:
        if not any(
            _filter_matches(actual_filter, expected_filter)
            for actual_filter in semantic_query.filters
        ):
            return EvalResult(
                case_id=case.id,
                question=case.question,
                level=case.level,
                category=case.category,
                status=response.status,
                ok=False,
                failure_reason="filter_mismatch",
                row_count=row_count,
                sql=sql,
            )

    if response.execution_plan is None:
        return EvalResult(
            case_id=case.id,
            question=case.question,
            level=case.level,
            category=case.category,
            status=response.status,
            ok=False,
            failure_reason="missing_execution_plan",
            row_count=row_count,
            sql=sql,
        )

    if rows is not None and row_count == 0:
        return EvalResult(
            case_id=case.id,
            question=case.question,
            level=case.level,
            category=case.category,
            status=response.status,
            ok=False,
            failure_reason="empty_result",
            row_count=row_count,
            sql=sql,
        )

    return EvalResult(
        case_id=case.id,
        question=case.question,
        level=case.level,
        category=case.category,
        status=response.status,
        ok=True,
        row_count=row_count,
        sql=sql,
    )


def _fetch_rows(
    connection: sqlite3.Connection,
    response: SemanticParseResponse,
    *,
    row_limit: int,
) -> list[dict[str, Any]] | None:
    if response.execution_plan is None:
        return None

    sql = response.execution_plan.sql
    if response.execution_plan.group_by_dimension_keys:
        sql = f"SELECT * FROM ({sql}) ORDER BY metric_value DESC LIMIT ?"
        cursor = connection.execute(sql, (row_limit,))
    else:
        cursor = connection.execute(sql)
    return [dict(row) for row in cursor.fetchall()]


def _service_from_env(env_path: Path) -> SemanticQueryService:
    load_dotenv(env_path)
    return SemanticQueryService.from_model_config(
        model_name=os.getenv("LLM_MODEL", ""),
        base_url=os.getenv("LLM_BASE_URL", ""),
        api_key=os.getenv("LLM_API_KEY", ""),
        temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
    )


def run_evaluation(
    *,
    dataset_id: str,
    cases: list[EvalCase],
    service: SemanticQueryService,
    sqlite_db_path: Path | None,
    row_limit: int,
) -> list[EvalResult]:
    results: list[EvalResult] = []
    connection = sqlite3.connect(sqlite_db_path) if sqlite_db_path else None
    try:
        if connection is not None:
            connection.row_factory = sqlite3.Row

        for case in cases:
            try:
                response = service.prepare_query(
                    SemanticQueryRequest(dataset_id=dataset_id, question=case.question)
                )
                rows = (
                    _fetch_rows(connection, response, row_limit=row_limit)
                    if connection is not None
                    else None
                )
                result = evaluate_case(case, response, rows=rows)
            except Exception as exc:
                result = EvalResult(
                    case_id=case.id,
                    question=case.question,
                    level=case.level,
                    category=case.category,
                    status="error",
                    ok=False,
                    failure_reason=f"{type(exc).__name__}: {exc}",
                )
            results.append(result)
    finally:
        if connection is not None:
            connection.close()
    return results


def _count_results(results: list[EvalResult]) -> dict[str, int]:
    return {
        "total": len(results),
        "ok": sum(1 for result in results if result.ok),
        "failed": sum(1 for result in results if not result.ok),
        "ready": sum(1 for result in results if result.status == "ready"),
        "clarification": sum(
            1 for result in results if result.status == "clarification"
        ),
        "error": sum(1 for result in results if result.status == "error"),
    }


def summarize_results(results: list[EvalResult]) -> dict[str, dict[str, dict[str, int]]]:
    summary = {
        "overall": _count_results(results),
        "levels": {},
        "categories": {},
    }
    level_keys = sorted({result.level for result in results if result.level})
    category_keys = sorted({result.category for result in results if result.category})

    for level_key in level_keys:
        summary["levels"][level_key] = _count_results(
            [result for result in results if result.level == level_key]
        )
    for category_key in category_keys:
        summary["categories"][category_key] = _count_results(
            [result for result in results if result.category == category_key]
        )

    return summary


def _print_summary_block(title: str, counters: dict[str, int]) -> None:
    print(title + " " + " ".join(f"{key}={value}" for key, value in counters.items()))


def _print_results(results: list[EvalResult], *, run_label: str | None = None) -> None:
    summary = summarize_results(results)
    for result in results:
        marker = "PASS" if result.ok else "FAIL"
        print(
            f"[{marker}] {result.case_id} status={result.status} "
            f"rows={result.row_count} reason={result.failure_reason or '-'}"
        )
    if run_label:
        print(f"\nRUN {run_label}")
    _print_summary_block("SUMMARY", summary["overall"])
    for level_key, counters in summary["levels"].items():
        _print_summary_block(f"LEVEL {level_key}", counters)
    for category_key, counters in summary["categories"].items():
        _print_summary_block(f"CATEGORY {category_key}", counters)


def main() -> None:
    parser = argparse.ArgumentParser(description="运行语义问数批量评估")
    parser.add_argument("--dataset-id", required=True, help="数据集 ID")
    parser.add_argument("--cases", type=Path, required=True, help="JSONL 评估问题集")
    parser.add_argument("--sqlite-db", type=Path, default=None, help="可选 SQLite 执行库")
    parser.add_argument("--env-path", type=Path, default=REPO_ROOT / ".env")
    parser.add_argument("--row-limit", type=int, default=5, help="分组查询采样行数")
    parser.add_argument("--repeat", type=int, default=1, help="重复跑同一问题集的次数")
    args = parser.parse_args()

    cases = load_cases(args.cases)
    all_results: list[EvalResult] = []
    for run_index in range(args.repeat):
        results = run_evaluation(
            dataset_id=args.dataset_id,
            cases=cases,
            service=_service_from_env(args.env_path),
            sqlite_db_path=args.sqlite_db,
            row_limit=args.row_limit,
        )
        all_results.extend(results)
        _print_results(results, run_label=f"{run_index + 1}/{args.repeat}")

    if args.repeat > 1:
        print("\nAGGREGATE")
        _print_results(all_results)

    if any(not result.ok for result in all_results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
