from src.qsql.schemas import SemanticQueryDraft, SemanticQueryRequest
from src.qsql.semantic_catalog import load_semantic_catalog
from src.qsql.semantic_service import SemanticQueryService
from src.qsql.sql_builder import build_query_execution_plan


def test_bird_european_football_2_catalog_builds_dual_team_match_sql():
    catalog = load_semantic_catalog("bird_european_football_2")

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="match_count",
            group_by_dimension_keys=["away_team_name"],
            filters=[
                {
                    "dimension_key": "league_name",
                    "operator": "eq",
                    "value": "Spain LIGA BBVA",
                },
                {
                    "dimension_key": "home_team_name",
                    "operator": "eq",
                    "value": "FC Barcelona",
                },
            ],
            time_range=None,
        ),
    )

    assert plan.table == "Match"
    assert "FROM Match AS t0" in plan.sql
    assert "LEFT JOIN League AS" in plan.sql
    assert "LEFT JOIN Team AS" in plan.sql
    assert "COUNT(DISTINCT t0.id) AS metric_value" in plan.sql
    assert "Spain LIGA BBVA" in plan.sql
    assert "FC Barcelona" in plan.sql


def test_bird_european_football_2_catalog_builds_multi_metric_season_sql():
    catalog = load_semantic_catalog("bird_european_football_2")

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="home_goals_sum",
            metric_keys=["home_goals_sum", "away_goals_sum"],
            group_by_dimension_keys=["season"],
            filters=[
                {
                    "dimension_key": "league_name",
                    "operator": "eq",
                    "value": "England Premier League",
                },
                {
                    "dimension_key": "home_team_name",
                    "operator": "eq",
                    "value": "Manchester City",
                },
            ],
            time_range=None,
        ),
    )

    assert plan.table == "Match"
    assert "SUM(t0.home_team_goal) AS home_goals_sum" in plan.sql
    assert "SUM(t0.away_team_goal) AS away_goals_sum" in plan.sql
    assert "t0.season AS season" in plan.sql
    assert "England Premier League" in plan.sql
    assert "Manchester City" in plan.sql


class _FootballLeagueParser:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="home_goals_avg",
            group_by_dimension_keys=["home_team_name"],
            filters=[
                {
                    "dimension_key": "league_name",
                    "operator": "eq",
                    "value": "Premier League",
                },
                {
                    "dimension_key": "season",
                    "operator": "eq",
                    "value": "2015/2016",
                },
            ],
            time_range=None,
        )


class _FootballDualRoleParser:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="match_count",
            group_by_dimension_keys=["season"],
            filters=[
                {
                    "dimension_key": "league_name",
                    "operator": "eq",
                    "value": "La Liga",
                },
                {
                    "dimension_key": "home_team_name",
                    "operator": "eq",
                    "value": "Barcelona",
                },
                {
                    "dimension_key": "away_team_name",
                    "operator": "eq",
                    "value": "Real Madrid",
                },
            ],
            time_range=None,
        )


def test_bird_european_football_2_service_normalizes_league_name():
    service = SemanticQueryService(parser=_FootballLeagueParser())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_european_football_2",
            question="Show average home goals by home team in the Premier League during the 2015/2016 season.",
        )
    )

    assert result.status == "ready"
    assert result.semantic_query is not None
    assert result.execution_plan is not None
    assert result.semantic_query.filters[0].value == "England Premier League"
    assert "England Premier League" in result.execution_plan.sql


def test_bird_european_football_2_service_normalizes_dual_role_teams():
    service = SemanticQueryService(parser=_FootballDualRoleParser())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_european_football_2",
            question="Show match count by season for Barcelona home matches against Real Madrid in La Liga.",
        )
    )

    assert result.status == "ready"
    assert result.semantic_query is not None
    assert result.execution_plan is not None
    normalized_filters = {
        filter_obj.dimension_key: filter_obj.value
        for filter_obj in result.semantic_query.filters
    }
    assert normalized_filters["league_name"] == "Spain LIGA BBVA"
    assert normalized_filters["home_team_name"] == "FC Barcelona"
    assert normalized_filters["away_team_name"] == "Real Madrid CF"
    assert "FC Barcelona" in result.execution_plan.sql
    assert "Real Madrid CF" in result.execution_plan.sql
