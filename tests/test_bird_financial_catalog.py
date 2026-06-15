from src.qsql.schemas import SemanticQueryDraft, SemanticQueryRequest
from src.qsql.semantic_catalog import load_semantic_catalog
from src.qsql.semantic_service import SemanticQueryService
from src.qsql.sql_builder import build_query_execution_plan


def test_bird_financial_catalog_builds_loan_account_region_sql():
    catalog = load_semantic_catalog("bird_financial")

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="loan_amount_total",
            group_by_dimension_keys=["account_region"],
            filters=[
                {
                    "dimension_key": "account_frequency",
                    "operator": "eq",
                    "value": "POPLATEK MESICNE",
                }
            ],
            time_range={
                "dimension_key": "loan_date",
                "start": "1997-01-01",
                "end": "1997-12-31",
            },
        ),
    )

    assert plan.table == "loan"
    assert "FROM loan AS t0" in plan.sql
    assert "LEFT JOIN account AS t1 ON t0.account_id = t1.account_id" in plan.sql
    assert "LEFT JOIN district AS t2 ON t1.district_id = t2.district_id" in plan.sql
    assert "t1.frequency = 'POPLATEK MESICNE'" in plan.sql
    assert "GROUP BY t2.A3" in plan.sql


def test_bird_financial_catalog_builds_card_client_region_multi_hop_sql():
    catalog = load_semantic_catalog("bird_financial")

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="card_count",
            group_by_dimension_keys=["card_type"],
            filters=[
                {
                    "dimension_key": "client_gender",
                    "operator": "eq",
                    "value": "F",
                },
                {
                    "dimension_key": "client_region",
                    "operator": "eq",
                    "value": "north Bohemia",
                },
            ],
            time_range={
                "dimension_key": "card_issued",
                "start": "1998-01-01",
                "end": "1998-12-31",
            },
        ),
    )

    assert plan.table == "card"
    assert "FROM card AS t0" in plan.sql
    assert "LEFT JOIN disp AS t1 ON t0.disp_id = t1.disp_id" in plan.sql
    assert "LEFT JOIN client AS t2 ON t1.client_id = t2.client_id" in plan.sql
    assert "LEFT JOIN district AS t3 ON t2.district_id = t3.district_id" in plan.sql
    assert "t2.gender = 'F'" in plan.sql
    assert "t3.A3 = 'north Bohemia'" in plan.sql
    assert "GROUP BY t0.type" in plan.sql


class _ParserFinancialClientSokolov:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="summary",
            metric_key="client_count",
            group_by_dimension_keys=[],
            filters=[
                {
                    "dimension_key": "client_gender",
                    "operator": "eq",
                    "value": "F",
                },
                {
                    "dimension_key": "client_district_name",
                    "operator": "eq",
                    "value": "Sokolov",
                },
            ],
            time_range={
                "dimension_key": "client_birth_date",
                "start": "1900-01-01",
                "end": "1949-12-31",
            },
        )


class _ParserFinancialNorthBohemiaTransaction:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="trans_amount_total",
            group_by_dimension_keys=["trans_type"],
            filters=[
                {
                    "dimension_key": "account_region",
                    "operator": "eq",
                    "value": "north Bohemia",
                }
            ],
            time_range={
                "dimension_key": "trans_date",
                "start": "1998-01-01",
                "end": "1998-12-31",
            },
        )


class _ParserFinancialWeeklyFrequency:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="account_count",
            group_by_dimension_keys=["account_region"],
            filters=[
                {
                    "dimension_key": "account_frequency",
                    "operator": "eq",
                    "value": "weekly",
                }
            ],
            time_range={
                "dimension_key": "account_open_date",
                "start": "1995-01-01",
                "end": "1995-12-31",
            },
        )


class _ParserFinancialEastBohemiaWrongDistrict:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="trans_amount_total",
            group_by_dimension_keys=["account_frequency", "trans_type"],
            filters=[
                {
                    "dimension_key": "account_district_name",
                    "operator": "eq",
                    "value": "East Bohemia",
                }
            ],
            time_range={
                "dimension_key": "trans_date",
                "start": "1998-01-01",
                "end": "1998-12-31",
            },
        )


def test_bird_financial_service_keeps_supported_district_role_only():
    service = SemanticQueryService(parser=_ParserFinancialClientSokolov())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_financial",
            question="From 1900-01-01 to 1949-12-31, how many female clients were there in Sokolov?",
        )
    )

    assert result.status == "ready"
    assert result.semantic_query is not None
    assert result.execution_plan is not None
    assert [item.dimension_key for item in result.semantic_query.filters] == [
        "client_gender",
        "client_district_name",
    ]
    assert "JOIN district AS t1" in result.execution_plan.sql
    assert "t1.A2 = 'Sokolov'" in result.execution_plan.sql


def test_bird_financial_service_does_not_treat_entity_nouns_as_second_metric():
    service = SemanticQueryService(parser=_ParserFinancialNorthBohemiaTransaction())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_financial",
            question="In 1998, show total transaction amount by transaction type for North Bohemia accounts.",
        )
    )

    assert result.status == "ready"
    assert result.semantic_query is not None
    assert result.semantic_query.metric_keys == ["trans_amount_total"]
    assert result.execution_plan is not None
    assert "SUM(t0.amount) AS metric_value" in result.execution_plan.sql
    assert "t2.A3 = 'north Bohemia'" in result.execution_plan.sql


def test_bird_financial_service_normalizes_frequency_alias_from_question():
    service = SemanticQueryService(parser=_ParserFinancialWeeklyFrequency())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_financial",
            question="In 1995, show account count by region for weekly issuance accounts.",
        )
    )

    assert result.status == "ready"
    assert result.semantic_query is not None
    assert result.semantic_query.filters[0].value == "POPLATEK TYDNE"
    assert result.execution_plan is not None
    assert "t0.frequency = 'POPLATEK TYDNE'" in result.execution_plan.sql


def test_bird_financial_service_repairs_region_value_from_wrong_district_dimension():
    service = SemanticQueryService(parser=_ParserFinancialEastBohemiaWrongDistrict())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_financial",
            question="In 1998, show total transaction amount by account frequency and transaction type for East Bohemia.",
        )
    )

    assert result.status == "ready"
    assert result.semantic_query is not None
    assert result.execution_plan is not None
    assert [item.model_dump() for item in result.semantic_query.filters] == [
        {
            "dimension_key": "account_region",
            "operator": "eq",
            "value": "east Bohemia",
        }
    ]
    assert "t2.A3 = 'east Bohemia'" in result.execution_plan.sql
