from src.qsql.schemas import (
    SemanticFilter,
    SemanticQueryDraft,
    SemanticQueryRequest,
    SemanticTimeRange,
)
from src.qsql.semantic_catalog import load_semantic_catalog
from src.qsql.semantic_service import SemanticQueryService
from src.qsql.sql_builder import build_query_execution_plan


def test_online_retail_catalog_builds_controlled_sql():
    # [CUSTOM] 真实业务数据 smoke 使用同一份语义目录，单测先守住离线 SQL 生成契约。
    catalog = load_semantic_catalog("online_retail")

    plan = build_query_execution_plan(
        catalog=catalog,
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
            metric_version_key="valid_revenue",
        ),
    )

    assert plan.table == "online_retail_orders"
    assert "SELECT country AS country, SUM(revenue) AS metric_value" in plan.sql
    assert "FROM online_retail_orders" in plan.sql
    assert "is_cancellation = 0" in plan.sql
    assert "GROUP BY country" in plan.sql


class _ParserMissingTimeRange:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="revenue",
            group_by_dimension_keys=["country"],
            filters=[],
            time_range=None,
            metric_version_key="valid_revenue",
        )


class _ParserMissingCountryFilter:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="summary",
            metric_key="quantity",
            group_by_dimension_keys=[],
            filters=[],
            time_range=None,
            metric_version_key="valid_quantity",
        )


class _ParserMissingTrendGroup:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="trend",
            metric_key="revenue",
            group_by_dimension_keys=[],
            filters=[],
            time_range=None,
            metric_version_key="valid_revenue",
        )


class _ParserSymbolicOperator:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="invoice_count",
            group_by_dimension_keys=["country"],
            filters=[
                SemanticFilter(
                    dimension_key="invoice_month",
                    operator=">=",
                    value="2011-01",
                )
            ],
            time_range=None,
            metric_version_key="valid_invoice_count",
        )


def test_semantic_service_repairs_explicit_year_into_time_range():
    service = SemanticQueryService(parser=_ParserMissingTimeRange())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="online_retail",
            question="2011年各国家有效销售额是多少？",
        )
    )

    assert result.status == "ready"
    assert result.execution_plan is not None
    assert "invoice_date >= '2011-01-01'" in result.execution_plan.sql
    assert "invoice_date <= '2011-12-31'" in result.execution_plan.sql


def test_semantic_service_repairs_common_country_alias_filter():
    service = SemanticQueryService(parser=_ParserMissingCountryFilter())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="online_retail",
            question="2011年德国有效销量是多少？",
        )
    )

    assert result.status == "ready"
    assert result.execution_plan is not None
    assert "country = 'Germany'" in result.execution_plan.sql


def test_semantic_service_repairs_trend_group_to_month_dimension():
    service = SemanticQueryService(parser=_ParserMissingTrendGroup())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="online_retail",
            question="2011年英国每月有效销售额趋势怎么样？",
        )
    )

    assert result.status == "ready"
    assert result.execution_plan is not None
    assert "invoice_month AS invoice_month" in result.execution_plan.sql
    assert "GROUP BY invoice_month" in result.execution_plan.sql


def test_semantic_service_repairs_symbolic_filter_operator():
    service = SemanticQueryService(parser=_ParserSymbolicOperator())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="online_retail",
            question="2011年各国家有效订单数是多少？",
        )
    )

    assert result.status == "ready"
    assert result.execution_plan is not None
    assert "invoice_month >= '2011-01'" in result.execution_plan.sql
