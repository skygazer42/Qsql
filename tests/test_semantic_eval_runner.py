from src.qsql.schemas import (
    QueryExecutionPlan,
    SemanticParseResponse,
    SemanticQueryDraft,
    SemanticTimeRange,
)
from scripts.semantic_eval_runner import EvalCase, EvalResult, evaluate_case, summarize_results


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
