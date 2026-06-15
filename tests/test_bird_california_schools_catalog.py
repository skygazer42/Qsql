from src.qsql.schemas import SemanticQueryDraft, SemanticQueryRequest
from src.qsql.semantic_catalog import load_semantic_catalog
from src.qsql.semantic_service import SemanticQueryService
from src.qsql.sql_builder import build_query_execution_plan


def test_bird_california_schools_catalog_builds_frpm_school_type_sql():
    catalog = load_semantic_catalog("bird_california_schools")

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="frpm_enrollment_k12_sum",
            group_by_dimension_keys=["school_type"],
            filters=[
                {
                    "dimension_key": "county_name",
                    "operator": "eq",
                    "value": "Los Angeles",
                }
            ],
            time_range=None,
        ),
    )

    assert plan.table == "frpm"
    assert "FROM frpm AS t0" in plan.sql
    assert "LEFT JOIN schools AS t1 ON t0.CDSCode = t1.CDSCode" in plan.sql
    assert 'SUM(t0."Enrollment (K-12)") AS metric_value' in plan.sql
    assert 't0."School Type" AS school_type' in plan.sql
    assert "t1.County = 'Los Angeles'" in plan.sql
    assert 'GROUP BY t0."School Type"' in plan.sql


def test_bird_california_schools_catalog_builds_sat_funding_sql():
    catalog = load_semantic_catalog("bird_california_schools")

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="sat_math_avg",
            group_by_dimension_keys=["funding_type"],
            filters=[
                {
                    "dimension_key": "score_record_type",
                    "operator": "eq",
                    "value": "S",
                },
                {
                    "dimension_key": "county_name",
                    "operator": "eq",
                    "value": "Los Angeles",
                },
            ],
            time_range=None,
        ),
    )

    assert plan.table == "satscores"
    assert "FROM satscores AS t0" in plan.sql
    assert "LEFT JOIN schools AS t1 ON t0.cds = t1.CDSCode" in plan.sql
    assert "AVG(t0.AvgScrMath) AS metric_value" in plan.sql
    assert "t0.rtype = 'S'" in plan.sql
    assert "t1.County = 'Los Angeles'" in plan.sql
    assert "t1.FundingType IS NOT NULL" in plan.sql
    assert "GROUP BY t1.FundingType" in plan.sql


class _CaliforniaSchoolLevelParser:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="sat_math_avg",
            group_by_dimension_keys=["funding_type"],
            filters=[
                {
                    "dimension_key": "score_record_type",
                    "operator": "eq",
                    "value": "school-level",
                },
                {
                    "dimension_key": "county_name",
                    "operator": "eq",
                    "value": "los angeles county",
                },
            ],
            time_range=None,
        )


class _CaliforniaCharterParser:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="school_count",
            group_by_dimension_keys=["funding_type"],
            filters=[
                {
                    "dimension_key": "charter_flag",
                    "operator": "eq",
                    "value": "charter schools",
                }
            ],
            time_range=None,
        )


def test_bird_california_schools_service_normalizes_school_level_scope():
    service = SemanticQueryService(parser=_CaliforniaSchoolLevelParser())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_california_schools",
            question="Show average school-level SAT math score by funding type in Los Angeles County.",
        )
    )

    assert result.status == "ready"
    assert result.semantic_query is not None
    assert result.execution_plan is not None
    assert result.semantic_query.filters[0].value == "S"
    assert result.semantic_query.filters[1].value == "Los Angeles"
    assert "t0.rtype = 'S'" in result.execution_plan.sql
    assert "t1.County = 'Los Angeles'" in result.execution_plan.sql


def test_bird_california_schools_service_normalizes_charter_flag():
    service = SemanticQueryService(parser=_CaliforniaCharterParser())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_california_schools",
            question="Show school count by funding type for charter schools.",
        )
    )

    assert result.status == "ready"
    assert result.semantic_query is not None
    assert result.execution_plan is not None
    assert result.semantic_query.filters[0].value == 1
    assert "Charter = 1" in result.execution_plan.sql
