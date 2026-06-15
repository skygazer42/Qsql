from src.qsql.schemas import SemanticQueryDraft, SemanticQueryRequest
from src.qsql.semantic_catalog import load_semantic_catalog
from src.qsql.semantic_service import SemanticQueryService
from src.qsql.sql_builder import build_query_execution_plan


def test_bird_superhero_catalog_builds_powered_hero_publisher_sql():
    catalog = load_semantic_catalog("bird_superhero")

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="powered_hero_count",
            group_by_dimension_keys=["publisher_name"],
            filters=[
                {
                    "dimension_key": "power_name",
                    "operator": "eq",
                    "value": "Flight",
                }
            ],
            time_range=None,
        ),
    )

    assert plan.table == "hero_power"
    assert "FROM hero_power AS t0" in plan.sql
    assert "LEFT JOIN superpower AS t1 ON t0.power_id = t1.id" in plan.sql
    assert "LEFT JOIN superhero AS t2 ON t0.hero_id = t2.id" in plan.sql
    assert "LEFT JOIN publisher AS t3 ON t2.publisher_id = t3.id" in plan.sql
    assert "COUNT(DISTINCT t0.hero_id) AS metric_value" in plan.sql
    assert "t1.power_name = 'Flight'" in plan.sql
    assert "GROUP BY t3.publisher_name" in plan.sql


def test_bird_superhero_catalog_builds_attribute_avg_sql():
    catalog = load_semantic_catalog("bird_superhero")

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="hero_attribute_value_avg",
            group_by_dimension_keys=["attribute_name"],
            filters=[
                {
                    "dimension_key": "publisher_name",
                    "operator": "eq",
                    "value": "Marvel Comics",
                }
            ],
            time_range=None,
        ),
    )

    assert plan.table == "hero_attribute"
    assert "FROM hero_attribute AS t0" in plan.sql
    assert "LEFT JOIN attribute AS t1 ON t0.attribute_id = t1.id" in plan.sql
    assert "LEFT JOIN superhero AS t2 ON t0.hero_id = t2.id" in plan.sql
    assert "LEFT JOIN publisher AS t3 ON t2.publisher_id = t3.id" in plan.sql
    assert "AVG(t0.attribute_value) AS metric_value" in plan.sql
    assert "t3.publisher_name = 'Marvel Comics'" in plan.sql
    assert "GROUP BY t1.attribute_name" in plan.sql


def test_bird_superhero_catalog_excludes_null_group_dimension_values():
    catalog = load_semantic_catalog("bird_superhero")

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="hero_count",
            group_by_dimension_keys=["publisher_name"],
            filters=[
                {
                    "dimension_key": "eye_colour",
                    "operator": "eq",
                    "value": "Blue",
                }
            ],
            time_range=None,
        ),
    )

    assert "FROM superhero AS t0" in plan.sql
    assert "t1.colour = 'Blue'" in plan.sql
    assert "t2.publisher_name IS NOT NULL" in plan.sql
    assert "GROUP BY t2.publisher_name" in plan.sql


class _ParserSuperheroPoweredHair:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="powered_hero_count",
            group_by_dimension_keys=["hair_colour"],
            filters=[
                {
                    "dimension_key": "power_name",
                    "operator": "eq",
                    "value": "super strength",
                }
            ],
            time_range=None,
        )


class _ParserSuperheroAttributePublisher:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="hero_attribute_value_avg",
            group_by_dimension_keys=["publisher_name"],
            filters=[
                {
                    "dimension_key": "attribute_name",
                    "operator": "eq",
                    "value": "intelligence",
                }
            ],
            time_range=None,
        )


def test_bird_superhero_service_normalizes_power_value_without_time_range():
    service = SemanticQueryService(parser=_ParserSuperheroPoweredHair())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_superhero",
            question="Show powered hero count by hair colour for super strength.",
        )
    )

    assert result.status == "ready"
    assert result.semantic_query is not None
    assert result.execution_plan is not None
    assert result.semantic_query.filters[0].value == "Super Strength"
    assert "power_name = 'Super Strength'" in result.execution_plan.sql
    assert "AS hair_colour" in result.execution_plan.sql
    assert "GROUP BY" in result.execution_plan.sql


def test_bird_superhero_service_normalizes_attribute_value_without_time_range():
    service = SemanticQueryService(parser=_ParserSuperheroAttributePublisher())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_superhero",
            question="Show average attribute value by publisher for intelligence.",
        )
    )

    assert result.status == "ready"
    assert result.semantic_query is not None
    assert result.execution_plan is not None
    assert result.semantic_query.filters[0].value == "Intelligence"
    assert "t1.attribute_name = 'Intelligence'" in result.execution_plan.sql
    assert "GROUP BY t3.publisher_name" in result.execution_plan.sql
