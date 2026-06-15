from src.qsql.schemas import SemanticQueryDraft, SemanticQueryRequest
from src.qsql.semantic_catalog import load_semantic_catalog
from src.qsql.semantic_service import SemanticQueryService
from src.qsql.sql_builder import build_query_execution_plan


def test_bird_formula_1_catalog_builds_results_circuit_country_sql():
    catalog = load_semantic_catalog("bird_formula_1")

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="result_points_total",
            group_by_dimension_keys=["circuit_country"],
            filters=[
                {
                    "dimension_key": "constructor_name",
                    "operator": "eq",
                    "value": "Ferrari",
                }
            ],
            time_range={
                "dimension_key": "race_date",
                "start": "2012-01-01",
                "end": "2012-12-31",
            },
        ),
    )

    assert plan.table == "results"
    assert "FROM results AS t0" in plan.sql
    assert "LEFT JOIN races AS" in plan.sql
    assert "LEFT JOIN circuits AS" in plan.sql
    assert "LEFT JOIN constructors AS" in plan.sql
    assert ".name = 'Ferrari'" in plan.sql
    assert "GROUP BY" in plan.sql
    assert ".country" in plan.sql


def test_bird_formula_1_catalog_builds_qualifying_constructor_sql():
    catalog = load_semantic_catalog("bird_formula_1")

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="qualifying_count",
            group_by_dimension_keys=["constructor_name"],
            filters=[
                {
                    "dimension_key": "driver_nationality",
                    "operator": "eq",
                    "value": "British",
                }
            ],
            time_range={
                "dimension_key": "race_date",
                "start": "2010-01-01",
                "end": "2010-12-31",
            },
        ),
    )

    assert plan.table == "qualifying"
    assert "FROM qualifying AS t0" in plan.sql
    assert "LEFT JOIN drivers AS" in plan.sql
    assert "LEFT JOIN constructors AS" in plan.sql
    assert "LEFT JOIN races AS" in plan.sql
    assert ".nationality = 'British'" in plan.sql
    assert "GROUP BY" in plan.sql


class _ParserFormulaOneFerrariUk:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="summary",
            metric_key="result_count",
            group_by_dimension_keys=[],
            filters=[
                {
                    "dimension_key": "constructor_name",
                    "operator": "eq",
                    "value": "ferrari",
                },
                {
                    "dimension_key": "circuit_country",
                    "operator": "eq",
                    "value": "uk",
                },
            ],
            time_range={
                "dimension_key": "race_date",
                "start": "2010-01-01",
                "end": "2010-12-31",
            },
        )


class _ParserFormulaOneFinishedItaly:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="result_points_total",
            group_by_dimension_keys=["constructor_name"],
            filters=[
                {
                    "dimension_key": "status_name",
                    "operator": "eq",
                    "value": "finished",
                },
                {
                    "dimension_key": "circuit_country",
                    "operator": "eq",
                    "value": "italy",
                },
            ],
            time_range={
                "dimension_key": "race_date",
                "start": "2012-01-01",
                "end": "2012-12-31",
            },
        )


def test_bird_formula_1_service_normalizes_constructor_and_country_values():
    service = SemanticQueryService(parser=_ParserFormulaOneFerrariUk())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_formula_1",
            question="In 2010, how many Ferrari results were there in UK circuits?",
        )
    )

    assert result.status == "ready"
    assert result.semantic_query is not None
    assert result.execution_plan is not None
    assert [item.model_dump() for item in result.semantic_query.filters] == [
        {
            "dimension_key": "constructor_name",
            "operator": "eq",
            "value": "Ferrari",
        },
        {
            "dimension_key": "circuit_country",
            "operator": "eq",
            "value": "UK",
        },
    ]
    assert ".name = 'Ferrari'" in result.execution_plan.sql
    assert ".country = 'UK'" in result.execution_plan.sql


def test_bird_formula_1_service_normalizes_status_value():
    service = SemanticQueryService(parser=_ParserFormulaOneFinishedItaly())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_formula_1",
            question="In 2012, show total points by constructor for finished results in Italy circuits.",
        )
    )

    assert result.status == "ready"
    assert result.semantic_query is not None
    assert result.execution_plan is not None
    assert [item.model_dump() for item in result.semantic_query.filters] == [
        {
            "dimension_key": "status_name",
            "operator": "eq",
            "value": "Finished",
        },
        {
            "dimension_key": "circuit_country",
            "operator": "eq",
            "value": "Italy",
        },
    ]
    assert ".status = 'Finished'" in result.execution_plan.sql
    assert ".country = 'Italy'" in result.execution_plan.sql
