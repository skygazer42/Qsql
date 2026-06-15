from src.qsql.schemas import (
    QueryExecutionPlan,
    SemanticParseResponse,
    SemanticQueryDraft,
    SemanticTimeRange,
)
from scripts.semantic_eval_runner import (
    EvalCase,
    EvalResult,
    evaluate_case,
    run_evaluation,
    summarize_results,
)


def test_evaluate_case_accepts_matching_ready_response():
    case = EvalCase(
        id="revenue_by_country",
        question="2011年各国家销售额是多少？",
        expect_status="ready",
        expect_metric_key="revenue",
        expect_group_by=["country"],
    )
    response = SemanticParseResponse(
        dataset_id="online_retail",
        question=case.question,
        status="ready",
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="revenue",
            group_by_dimension_keys=["country"],
            filters=[],
            time_range=SemanticTimeRange(
                dimension_key="invoice_date",
                start="2011-01-01",
                end="2011-12-31",
            ),
        ),
        execution_plan=QueryExecutionPlan(
            dataset_id="online_retail",
            table="online_retail_orders",
            sql="SELECT country, SUM(revenue) AS metric_value FROM online_retail_orders",
            parameters=[],
            analysis_type="group_by",
            metric_key="revenue",
            metric_label="销售额",
            group_by_dimension_keys=["country"],
        ),
    )

    result = evaluate_case(case, response, rows=[{"country": "United Kingdom"}])

    assert result.ok is True
    assert result.failure_reason is None


def test_evaluate_case_flags_semantic_mismatch():
    case = EvalCase(
        id="quantity_summary",
        question="2011年销量是多少？",
        expect_status="ready",
        expect_metric_key="quantity",
        expect_group_by=[],
    )
    response = SemanticParseResponse(
        dataset_id="online_retail",
        question=case.question,
        status="ready",
        semantic_query=SemanticQueryDraft(
            analysis_type="summary",
            metric_key="revenue",
            group_by_dimension_keys=[],
            filters=[],
            time_range=SemanticTimeRange(
                dimension_key="invoice_date",
                start="2011-01-01",
                end="2011-12-31",
            ),
        ),
    )

    result = evaluate_case(case, response, rows=[{"metric_value": 1}])

    assert result.ok is False
    assert result.failure_reason == "metric_mismatch"


def test_evaluate_case_treats_group_by_order_as_equivalent():
    case = EvalCase(
        id="country_month",
        question="2011年按国家和月份看销售额",
        expect_status="ready",
        expect_metric_key="revenue",
        expect_group_by=["country", "invoice_month"],
    )
    response = SemanticParseResponse(
        dataset_id="online_retail",
        question=case.question,
        status="ready",
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="revenue",
            group_by_dimension_keys=["invoice_month", "country"],
            filters=[],
            time_range=SemanticTimeRange(
                dimension_key="invoice_date",
                start="2011-01-01",
                end="2011-12-31",
            ),
        ),
        execution_plan=QueryExecutionPlan(
            dataset_id="online_retail",
            table="online_retail_orders",
            sql="SELECT invoice_month, country, SUM(revenue) AS metric_value FROM online_retail_orders",
            parameters=[],
            analysis_type="group_by",
            metric_key="revenue",
            metric_label="销售额",
            group_by_dimension_keys=["invoice_month", "country"],
        ),
    )

    result = evaluate_case(case, response, rows=[{"country": "United Kingdom"}])

    assert result.ok is True


def test_evaluate_case_accepts_ex_match_with_extra_actual_columns():
    case = EvalCase(
        id="revenue_summary",
        question="2011年销售额是多少？",
        expect_status="ready",
        expect_metric_key="revenue",
        expect_group_by=[],
        expected_sql="SELECT 10 AS metric_value",
    )
    response = SemanticParseResponse(
        dataset_id="online_retail",
        question=case.question,
        status="ready",
        semantic_query=SemanticQueryDraft(
            analysis_type="summary",
            metric_key="revenue",
            group_by_dimension_keys=[],
            filters=[],
            time_range=SemanticTimeRange(
                dimension_key="invoice_date",
                start="2011-01-01",
                end="2011-12-31",
            ),
        ),
        execution_plan=QueryExecutionPlan(
            dataset_id="online_retail",
            table="online_retail_orders",
            sql="SELECT 10 AS metric_value, 'extra' AS debug_label",
            parameters=[],
            analysis_type="summary",
            metric_key="revenue",
            metric_label="销售额",
            group_by_dimension_keys=[],
        ),
    )

    result = evaluate_case(
        case,
        response,
        rows=[{"metric_value": 10, "debug_label": "extra"}],
        expected_rows=[{"metric_value": 10}],
    )

    assert result.ok is True
    assert result.ex_ok is True
    assert result.expected_row_count == 1


def test_evaluate_case_flags_ex_mismatch():
    case = EvalCase(
        id="quantity_summary",
        question="2011年销量是多少？",
        expect_status="ready",
        expect_metric_key="quantity",
        expect_group_by=[],
        expected_sql="SELECT 10 AS metric_value",
    )
    response = SemanticParseResponse(
        dataset_id="online_retail",
        question=case.question,
        status="ready",
        semantic_query=SemanticQueryDraft(
            analysis_type="summary",
            metric_key="quantity",
            group_by_dimension_keys=[],
            filters=[],
            time_range=SemanticTimeRange(
                dimension_key="invoice_date",
                start="2011-01-01",
                end="2011-12-31",
            ),
        ),
        execution_plan=QueryExecutionPlan(
            dataset_id="online_retail",
            table="online_retail_orders",
            sql="SELECT 11 AS metric_value",
            parameters=[],
            analysis_type="summary",
            metric_key="quantity",
            metric_label="销量",
            group_by_dimension_keys=[],
        ),
    )

    result = evaluate_case(
        case,
        response,
        rows=[{"metric_value": 11}],
        expected_rows=[{"metric_value": 10}],
    )

    assert result.ok is False
    assert result.ex_ok is False
    assert result.failure_reason == "ex_mismatch"


class _StaticEvalService:
    def __init__(self, response: SemanticParseResponse):
        self._response = response

    def prepare_query(self, request_model):
        return self._response


def test_run_evaluation_executes_expected_sql_for_ex_check(tmp_path):
    db_path = tmp_path / "eval.sqlite3"
    import sqlite3

    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE sales (country TEXT, revenue INTEGER)")
        connection.executemany(
            "INSERT INTO sales (country, revenue) VALUES (?, ?)",
            [("UK", 7), ("US", 3)],
        )
        connection.commit()

    response = SemanticParseResponse(
        dataset_id="sales",
        question="各国家销售额是多少？",
        status="ready",
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="revenue",
            group_by_dimension_keys=["country"],
            filters=[],
            time_range=SemanticTimeRange(
                dimension_key="order_date",
                start="2026-01-01",
                end="2026-12-31",
            ),
        ),
        execution_plan=QueryExecutionPlan(
            dataset_id="sales",
            table="sales",
            sql="SELECT country, SUM(revenue) AS metric_value FROM sales GROUP BY country",
            parameters=[],
            analysis_type="group_by",
            metric_key="revenue",
            metric_label="销售额",
            group_by_dimension_keys=["country"],
        ),
    )
    case = EvalCase(
        id="country_revenue",
        question="各国家销售额是多少？",
        expect_status="ready",
        expect_metric_key="revenue",
        expect_group_by=["country"],
        expected_sql=(
            "SELECT country, SUM(revenue) AS metric_value "
            "FROM sales GROUP BY country"
        ),
    )

    results = run_evaluation(
        dataset_id="sales",
        cases=[case],
        service=_StaticEvalService(response),
        sqlite_db_path=db_path,
        row_limit=1,
    )

    assert results[0].ok is True
    assert results[0].ex_ok is True
    assert results[0].row_count == 2
    assert results[0].expected_row_count == 2


def test_summarize_results_groups_by_level_and_category():
    results = [
        EvalResult(
            case_id="c1",
            question="q1",
            level="L1",
            category="summary",
            status="ready",
            ok=True,
        ),
        EvalResult(
            case_id="c2",
            question="q2",
            level="L1",
            category="summary",
            status="clarification",
            ok=True,
        ),
        EvalResult(
            case_id="c3",
            question="q3",
            level="L3",
            category="compound",
            status="error",
            ok=False,
            failure_reason="boom",
        ),
    ]

    summary = summarize_results(results)

    assert summary["overall"]["total"] == 3
    assert summary["overall"]["ok"] == 2
    assert summary["overall"]["failed"] == 1
    assert summary["levels"]["L1"]["total"] == 2
    assert summary["levels"]["L1"]["clarification"] == 1
    assert summary["categories"]["summary"]["ok"] == 2
    assert summary["categories"]["compound"]["error"] == 1
