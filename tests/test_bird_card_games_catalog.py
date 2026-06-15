from src.qsql.schemas import SemanticQueryDraft, SemanticQueryRequest
from src.qsql.semantic_catalog import load_semantic_catalog
from src.qsql.semantic_service import SemanticQueryService
from src.qsql.sql_builder import build_query_execution_plan


def test_bird_card_games_catalog_builds_foreign_set_sql():
    catalog = load_semantic_catalog("bird_card_games")

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="translated_card_count",
            group_by_dimension_keys=["set_block"],
            filters=[
                {
                    "dimension_key": "story_spotlight_flag",
                    "operator": "eq",
                    "value": 1,
                },
                {
                    "dimension_key": "foreign_language",
                    "operator": "eq",
                    "value": "French",
                },
            ],
            time_range=None,
        ),
    )

    assert plan.table == "foreign_data"
    assert "FROM foreign_data AS t0" in plan.sql
    assert "LEFT JOIN cards AS t1 ON t0.uuid = t1.uuid" in plan.sql
    assert "LEFT JOIN sets AS t2 ON t1.setCode = t2.code" in plan.sql
    assert "COUNT(DISTINCT t0.uuid) AS metric_value" in plan.sql
    assert "t1.isStorySpotlight = 1" in plan.sql
    assert "t0.language = 'French'" in plan.sql
    assert "t2.block AS set_block" in plan.sql
    assert "GROUP BY t2.block" in plan.sql


def test_bird_card_games_catalog_builds_legality_set_sql():
    catalog = load_semantic_catalog("bird_card_games")

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="legal_card_count",
            group_by_dimension_keys=["legality_format"],
            filters=[
                {
                    "dimension_key": "card_rarity",
                    "operator": "eq",
                    "value": "mythic",
                },
                {
                    "dimension_key": "set_name",
                    "operator": "eq",
                    "value": "Hour of Devastation",
                }
            ],
            time_range=None,
        ),
    )

    assert plan.table == "legalities"
    assert "FROM legalities AS t0" in plan.sql
    assert "LEFT JOIN cards AS t1 ON t0.uuid = t1.uuid" in plan.sql
    assert "LEFT JOIN sets AS t2 ON t1.setCode = t2.code" in plan.sql
    assert "COUNT(DISTINCT t0.uuid) AS metric_value" in plan.sql
    assert "t1.rarity = 'mythic'" in plan.sql
    assert "t2.name = 'Hour of Devastation'" in plan.sql
    assert "t0.format AS legality_format" in plan.sql
    assert "GROUP BY t0.format" in plan.sql


def test_bird_card_games_catalog_builds_set_translation_sql():
    catalog = load_semantic_catalog("bird_card_games")

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="translated_set_count",
            group_by_dimension_keys=["translation_language"],
            filters=[
                {
                    "dimension_key": "set_block",
                    "operator": "eq",
                    "value": "Commander",
                }
            ],
            time_range=None,
        ),
    )

    assert plan.table == "set_translations"
    assert "FROM set_translations AS t0" in plan.sql
    assert "LEFT JOIN sets AS t1 ON t0.setCode = t1.code" in plan.sql
    assert "COUNT(DISTINCT t0.setCode) AS metric_value" in plan.sql
    assert "t1.block = 'Commander'" in plan.sql
    assert "t0.language AS translation_language" in plan.sql
    assert "GROUP BY t0.language" in plan.sql


class _CardGamesPortugueseCommanderParser:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="summary",
            metric_key="translated_set_count",
            group_by_dimension_keys=[],
            filters=[
                {
                    "dimension_key": "translation_language",
                    "operator": "eq",
                    "value": "Brazilian Portuguese",
                },
                {
                    "dimension_key": "set_block",
                    "operator": "eq",
                    "value": "commander block",
                },
            ],
            time_range=None,
        )


class _CardGamesColdsnapMultiMetricParser:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="card_count",
            metric_keys=["card_count", "converted_mana_cost_avg"],
            group_by_dimension_keys=["set_name"],
            filters=[
                {
                    "dimension_key": "set_block",
                    "operator": "eq",
                    "value": "Commander",
                }
            ],
            time_range=None,
        )


def test_bird_card_games_service_normalizes_portuguese_and_block():
    service = SemanticQueryService(parser=_CardGamesPortugueseCommanderParser())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_card_games",
            question="How many Commander-block sets have Brazilian Portuguese translations?",
        )
    )

    assert result.status == "ready"
    assert result.semantic_query is not None
    assert result.execution_plan is not None
    assert [item.model_dump() for item in result.semantic_query.filters] == [
        {
            "dimension_key": "translation_language",
            "operator": "eq",
            "value": "Portuguese (Brazil)",
        },
        {
            "dimension_key": "set_block",
            "operator": "eq",
            "value": "Commander",
        },
    ]
    assert "t0.language = 'Portuguese (Brazil)'" in result.execution_plan.sql
    assert "t1.block = 'Commander'" in result.execution_plan.sql


def test_bird_card_games_service_keeps_multi_metric_ready():
    service = SemanticQueryService(parser=_CardGamesColdsnapMultiMetricParser())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_card_games",
            question="Show card count and average converted mana cost by set name for Commander block.",
        )
    )

    assert result.status == "ready"
    assert result.semantic_query is not None
    assert result.execution_plan is not None
    assert result.semantic_query.metric_keys == [
        "card_count",
        "converted_mana_cost_avg",
    ]
    assert "COUNT(DISTINCT" in result.execution_plan.sql
    assert "AVG(" in result.execution_plan.sql
