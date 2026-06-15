#!/usr/bin/env python
"""Run dataset-scoped semantic query evaluation cases."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import Field

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    # [CUSTOM] 支持 `python scripts/semantic_eval_runner.py` 直接运行。
    sys.path.insert(0, str(REPO_ROOT))

from src.qsql.schemas import (  # noqa: E402
    SemanticFilter,
    SemanticParseResponse,
    SemanticQueryRequest,
    ValidateRequest,
)
from src.qsql.semantic_service import SemanticQueryService  # noqa: E402


class EvalCase(ValidateRequest):
    """单条语义评测用例。"""

    id: str
    question: str
    level: str | None = None
    category: str | None = None
    expect_status: str = "ready"
    expect_metric_key: str | None = None
    expect_metric_keys: list[str] | None = None
    expect_group_by: list[str] | None = None
    expect_filters: list[dict[str, Any]] = Field(default_factory=list)
    expected_sql: str | None = None


class EvalResult(ValidateRequest):
    """单条语义评测结果。"""

    case_id: str
    question: str
    status: str
    ok: bool
    level: str | None = None
    category: str | None = None
    failure_reason: str | None = None
    row_count: int = 0
    expected_row_count: int | None = None
    ex_ok: bool | None = None
    sql: str | None = None


class EvalConsistencySummary(ValidateRequest):
    """repeat 评测下同一 case 的解析一致性摘要。"""

    total_cases: int = Field(ge=0)
    stable_cases: int = Field(ge=0)
    unstable_cases: int = Field(ge=0)
    stability_rate: float = Field(ge=0.0, le=1.0)
    unstable_case_ids: list[str] = Field(default_factory=list)


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
                    expect_metric_keys=payload.get("expect_metric_keys"),
                    expect_group_by=payload.get("expect_group_by"),
                    expect_filters=payload.get("expect_filters") or [],
                    expected_sql=payload.get("expected_sql"),
                )
            )
    return cases


def _filter_matches(actual: SemanticFilter, expected: dict[str, Any]) -> bool:
    for key in ("dimension_key", "operator", "value"):
        if key in expected and getattr(actual, key) != expected[key]:
            return False
    return True


def _group_by_matches(
    *,
    actual_group_by: list[str],
    expected_group_by: list[str],
    filters: list[SemanticFilter],
) -> bool:
    actual_keys = set(actual_group_by)
    expected_keys = set(expected_group_by)
    missing_keys = expected_keys - actual_keys
    if missing_keys:
        return False

    fixed_dimension_keys = {
        item.dimension_key for item in filters if item.operator.lower() == "eq"
    }
    extra_keys = actual_keys - expected_keys
    return extra_keys.issubset(fixed_dimension_keys)


def _normalise_result_rows(
    rows: list[dict[str, Any]],
    *,
    columns: list[str],
) -> list[str]:
    normalised_rows = []
    for row in rows:
        projected = {column: row.get(column) for column in columns}
        normalised_rows.append(
            json.dumps(projected, ensure_ascii=False, sort_keys=True, default=str)
        )
    return sorted(normalised_rows)


def _result_sets_equivalent(
    *,
    actual_rows: list[dict[str, Any]],
    expected_rows: list[dict[str, Any]],
) -> bool:
    # [CUSTOM] EX 对齐 BIRD/Spider 风格：按标准 SQL 的列投影比较，容忍预测 SQL 多 SELECT 辅助列。
    expected_columns = sorted(
        {column for row in expected_rows for column in row.keys()}
    )
    if not expected_columns:
        return actual_rows == expected_rows

    if any(
        any(column not in actual_row for column in expected_columns)
        for actual_row in actual_rows
    ):
        return False

    return _normalise_result_rows(
        actual_rows, columns=expected_columns
    ) == _normalise_result_rows(expected_rows, columns=expected_columns)


def evaluate_case(
    case: EvalCase,
    response: SemanticParseResponse,
    *,
    rows: list[dict[str, Any]] | None,
    expected_rows: list[dict[str, Any]] | None = None,
) -> EvalResult:
    sql = response.execution_plan.sql if response.execution_plan else None
    row_count = len(rows or [])
    expected_row_count = len(expected_rows) if expected_rows is not None else None

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
            expected_row_count=expected_row_count,
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
            expected_row_count=expected_row_count,
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
            expected_row_count=expected_row_count,
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
            expected_row_count=expected_row_count,
            sql=sql,
        )

    if case.expect_metric_keys is not None and set(
        semantic_query.metric_keys
    ) != set(case.expect_metric_keys):
        return EvalResult(
            case_id=case.id,
            question=case.question,
            level=case.level,
            category=case.category,
            status=response.status,
            ok=False,
            failure_reason="metric_keys_mismatch",
            row_count=row_count,
            expected_row_count=expected_row_count,
            sql=sql,
        )

    if case.expect_group_by is not None and not _group_by_matches(
        actual_group_by=semantic_query.group_by_dimension_keys,
        expected_group_by=case.expect_group_by,
        filters=semantic_query.filters,
    ):
        return EvalResult(
            case_id=case.id,
            question=case.question,
            level=case.level,
            category=case.category,
            status=response.status,
            ok=False,
            failure_reason="group_by_mismatch",
            row_count=row_count,
            expected_row_count=expected_row_count,
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
                expected_row_count=expected_row_count,
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
            expected_row_count=expected_row_count,
            sql=sql,
        )

    if case.expected_sql:
        if rows is None or expected_rows is None:
            return EvalResult(
                case_id=case.id,
                question=case.question,
                level=case.level,
                category=case.category,
                status=response.status,
                ok=False,
                failure_reason="missing_ex_rows",
                row_count=row_count,
                expected_row_count=expected_row_count,
                ex_ok=False,
                sql=sql,
            )
        ex_ok = _result_sets_equivalent(
            actual_rows=rows,
            expected_rows=expected_rows,
        )
        return EvalResult(
            case_id=case.id,
            question=case.question,
            level=case.level,
            category=case.category,
            status=response.status,
            ok=ex_ok,
            failure_reason=None if ex_ok else "ex_mismatch",
            row_count=row_count,
            expected_row_count=expected_row_count,
            ex_ok=ex_ok,
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
            expected_row_count=expected_row_count,
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
        expected_row_count=expected_row_count,
        sql=sql,
    )


def _fetch_rows(
    connection: sqlite3.Connection,
    response: SemanticParseResponse,
    *,
    row_limit: int,
    apply_group_limit: bool = True,
) -> list[dict[str, Any]] | None:
    if response.execution_plan is None:
        return None

    sql = response.execution_plan.sql
    if apply_group_limit and response.execution_plan.group_by_dimension_keys:
        metric_keys = response.execution_plan.metric_keys
        order_column = "metric_value" if len(metric_keys) == 1 else metric_keys[0]
        sql = f"SELECT * FROM ({sql}) ORDER BY {order_column} DESC LIMIT ?"
        cursor = connection.execute(sql, (row_limit,))
    else:
        cursor = connection.execute(sql)
    return [dict(row) for row in cursor.fetchall()]


def _fetch_expected_rows(
    connection: sqlite3.Connection,
    case: EvalCase,
) -> list[dict[str, Any]] | None:
    if not case.expected_sql:
        return None
    cursor = connection.execute(case.expected_sql)
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
                expected_rows = (
                    _fetch_expected_rows(connection, case)
                    if connection is not None
                    else None
                )
                rows = (
                    _fetch_rows(
                        connection,
                        response,
                        row_limit=row_limit,
                        apply_group_limit=case.expected_sql is None,
                    )
                    if connection is not None
                    else None
                )
                result = evaluate_case(
                    case,
                    response,
                    rows=rows,
                    expected_rows=expected_rows,
                )
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
        "ex_checked": sum(1 for result in results if result.ex_ok is not None),
        "ex_ok": sum(1 for result in results if result.ex_ok is True),
        "ex_failed": sum(1 for result in results if result.ex_ok is False),
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


def _consistency_signature(result: EvalResult) -> str:
    payload = {
        "status": result.status,
        "ok": result.ok,
        "failure_reason": result.failure_reason,
        "ex_ok": result.ex_ok,
        "sql": result.sql,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def summarize_consistency(results: list[EvalResult]) -> EvalConsistencySummary:
    # [CUSTOM] repeat 模式下统计同一用例的输出稳定性，补足多候选投票收益观测入口。
    grouped: dict[str, list[EvalResult]] = {}
    for result in results:
        grouped.setdefault(result.case_id, []).append(result)

    unstable_case_ids: list[str] = []
    for case_id, case_results in sorted(grouped.items()):
        signatures = {_consistency_signature(result) for result in case_results}
        if len(signatures) > 1:
            unstable_case_ids.append(case_id)

    total_cases = len(grouped)
    unstable_cases = len(unstable_case_ids)
    stable_cases = total_cases - unstable_cases
    stability_rate = stable_cases / total_cases if total_cases else 1.0
    return EvalConsistencySummary(
        total_cases=total_cases,
        stable_cases=stable_cases,
        unstable_cases=unstable_cases,
        stability_rate=stability_rate,
        unstable_case_ids=unstable_case_ids,
    )


def _print_summary_block(title: str, counters: dict[str, int]) -> None:
    print(title + " " + " ".join(f"{key}={value}" for key, value in counters.items()))


def _print_consistency(results: list[EvalResult]) -> None:
    summary = summarize_consistency(results)
    unstable_ids = ",".join(summary.unstable_case_ids) or "-"
    print(
        "CONSISTENCY "
        f"total_cases={summary.total_cases} "
        f"stable_cases={summary.stable_cases} "
        f"unstable_cases={summary.unstable_cases} "
        f"stability_rate={summary.stability_rate:.4f} "
        f"unstable_case_ids={unstable_ids}"
    )


def _print_results(results: list[EvalResult], *, run_label: str | None = None) -> None:
    summary = summarize_results(results)
    for result in results:
        marker = "PASS" if result.ok else "FAIL"
        print(
            f"[{marker}] {result.case_id} status={result.status} "
            f"rows={result.row_count} ex={result.ex_ok} "
            f"reason={result.failure_reason or '-'}"
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
        _print_consistency(all_results)

    if any(not result.ok for result in all_results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
