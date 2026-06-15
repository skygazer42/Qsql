from src.qsql.schemas import SemanticQueryDraft, SemanticQueryRequest
from src.qsql.semantic_catalog import load_semantic_catalog
from src.qsql.semantic_service import SemanticQueryService
from src.qsql.sql_builder import build_query_execution_plan


def test_bird_student_club_catalog_builds_attendance_multi_hop_sql():
    catalog = load_semantic_catalog("bird_student_club")

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="attendance_count",
            group_by_dimension_keys=["major_name"],
            filters=[
                {
                    "dimension_key": "event_name",
                    "operator": "eq",
                    "value": "Women's Soccer",
                }
            ],
            time_range={
                "dimension_key": "event_date",
                "start": "2019-01-01",
                "end": "2020-12-31",
            },
        ),
    )

    assert plan.table == "attendance"
    assert "FROM attendance AS t0" in plan.sql
    assert "LEFT JOIN event AS t1 ON t0.link_to_event = t1.event_id" in plan.sql
    assert "LEFT JOIN member AS t2 ON t0.link_to_member = t2.member_id" in plan.sql
    assert "LEFT JOIN major AS t3 ON t2.link_to_major = t3.major_id" in plan.sql
    assert "t1.event_name = 'Women''s Soccer'" in plan.sql
    assert "GROUP BY t3.major_name" in plan.sql


def test_bird_student_club_catalog_builds_expense_event_chain_sql():
    catalog = load_semantic_catalog("bird_student_club")

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="expense_total",
            group_by_dimension_keys=["expense_description"],
            filters=[
                {
                    "dimension_key": "event_name",
                    "operator": "eq",
                    "value": "October Meeting",
                },
                {
                    "dimension_key": "expense_approved",
                    "operator": "eq",
                    "value": "true",
                },
            ],
            time_range={
                "dimension_key": "expense_date",
                "start": "2019-10-08",
                "end": "2019-10-08",
            },
        ),
    )

    assert plan.table == "expense"
    assert "FROM expense AS t0" in plan.sql
    assert "LEFT JOIN budget AS t1 ON t0.link_to_budget = t1.budget_id" in plan.sql
    assert "LEFT JOIN event AS t2 ON t1.link_to_event = t2.event_id" in plan.sql
    assert "t2.event_name = 'October Meeting'" in plan.sql
    assert "t0.approved = 'true'" in plan.sql
    assert "GROUP BY t0.expense_description" in plan.sql


class _ParserStudentClubExactEventDate:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="budget_amount_total",
            group_by_dimension_keys=["budget_category"],
            filters=[
                {
                    "dimension_key": "event_name",
                    "operator": "eq",
                    "value": "April Speaker",
                }
            ],
            time_range={
                "dimension_key": "event_date",
                "start": "2020-04-21",
                "end": "2020-04-21",
            },
        )


def test_bird_student_club_service_expands_exact_date_for_datetime_dimension():
    service = SemanticQueryService(parser=_ParserStudentClubExactEventDate())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_student_club",
            question="On 2020-04-21, show total budget amount by category for April Speaker.",
        )
    )

    assert result.status == "ready"
    assert result.execution_plan is not None
    assert "t1.event_date >= '2020-04-21'" in result.execution_plan.sql
    assert "t1.event_date <= '2020-04-21T23:59:59'" in result.execution_plan.sql
