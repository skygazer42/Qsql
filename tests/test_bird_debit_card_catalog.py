from src.qsql.schemas import SemanticQueryDraft, SemanticQueryRequest
from src.qsql.semantic_catalog import load_semantic_catalog
from src.qsql.semantic_service import SemanticQueryService
from src.qsql.sql_builder import build_query_execution_plan


class _ParserMissingYearMonthRange:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="consumption_total",
            group_by_dimension_keys=["customer_segment"],
            filters=[],
            time_range=None,
        )


class _ParserStringCustomerIdFilter:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="summary",
            metric_key="consumption_total",
            group_by_dimension_keys=[],
            filters=[
                {
                    "dimension_key": "customer_id",
                    "operator": "eq",
                    "value": "6",
                }
            ],
            time_range={
                "dimension_key": "period_yyyymm",
                "start": "201308",
                "end": "201311",
            },
        )


def test_bird_debit_catalog_builds_join_sql_for_yearmonth_metric():
    catalog = load_semantic_catalog("bird_debit_card_specializing")

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="consumption_total",
            group_by_dimension_keys=["customer_segment"],
            filters=[
                {
                    "dimension_key": "customer_currency",
                    "operator": "eq",
                    "value": "EUR",
                }
            ],
            time_range={
                "dimension_key": "period_yyyymm",
                "start": "201201",
                "end": "201212",
            },
        ),
    )

    assert plan.table == "yearmonth"
    assert "FROM yearmonth AS t0" in plan.sql
    assert "LEFT JOIN customers AS t1 ON t0.CustomerID = t1.CustomerID" in plan.sql
    assert "t0.Date >= '201201'" in plan.sql
    assert "t0.Date <= '201212'" in plan.sql
    assert "t1.Currency = 'EUR'" in plan.sql
    assert "GROUP BY t1.Segment" in plan.sql


def test_bird_debit_catalog_builds_multi_join_sql_for_transaction_metric():
    catalog = load_semantic_catalog("bird_debit_card_specializing")

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="spend_total",
            group_by_dimension_keys=["product_description"],
            filters=[
                {
                    "dimension_key": "gasstation_country",
                    "operator": "eq",
                    "value": "CZE",
                },
                {
                    "dimension_key": "customer_currency",
                    "operator": "eq",
                    "value": "EUR",
                },
            ],
            time_range={
                "dimension_key": "transaction_date",
                "start": "2012-08-25",
                "end": "2012-08-25",
            },
        ),
    )

    assert plan.table == "transactions_1k"
    assert "FROM transactions_1k AS t0" in plan.sql
    assert "LEFT JOIN customers AS t1 ON t0.CustomerID = t1.CustomerID" in plan.sql
    assert "LEFT JOIN gasstations AS t2 ON t0.GasStationID = t2.GasStationID" in plan.sql
    assert "LEFT JOIN products AS t3 ON t0.ProductID = t3.ProductID" in plan.sql
    assert "t2.Country = 'CZE'" in plan.sql
    assert "t1.Currency = 'EUR'" in plan.sql
    assert "GROUP BY t3.Description" in plan.sql


def test_bird_debit_service_repairs_explicit_year_for_yyyymm_dimension():
    # [CUSTOM] BIRD 的 yearmonth.Date 不是 ISO 日期，显式年份补全必须按 YYYYMM 输出。
    service = SemanticQueryService(parser=_ParserMissingYearMonthRange())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_debit_card_specializing",
            question="What was the total gas consumption for each customer segment in 2013?",
        )
    )

    assert result.status == "ready"
    assert result.execution_plan is not None
    assert "t0.Date >= '201301'" in result.execution_plan.sql
    assert "t0.Date <= '201312'" in result.execution_plan.sql


def test_bird_debit_service_normalizes_numeric_filter_values():
    service = SemanticQueryService(parser=_ParserStringCustomerIdFilter())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_debit_card_specializing",
            question="How much did customer 6 consume in total between 201308 and 201311?",
        )
    )

    assert result.status == "ready"
    assert result.semantic_query is not None
    assert result.semantic_query.filters[0].value == 6
    assert result.execution_plan is not None
    assert "t1.CustomerID = 6" in result.execution_plan.sql
