import json
from datetime import date
from pathlib import Path

from src.qsql.schemas import (
    SemanticCatalog,
    SemanticFilter,
    SemanticQueryDraft,
    SemanticValueCandidate,
    SemanticTimeRange,
    ValidateRequest,
)
from src.qsql.semantic_postprocessor import SemanticPostprocessor


def _catalog(dataset_id: str = "custom_dataset") -> SemanticCatalog:
    return ValidateRequest.parse(
        SemanticCatalog,
        {
            "catalog_version": "2026-06-15",
            "dataset_id": dataset_id,
            "tables": [
                {
                    "key": "orders_wide",
                    "label": "订单宽表",
                    "physical_table": "orders",
                    "default_time_dimension_key": "order_date",
                }
            ],
            "metrics": [
                {
                    "key": "amount",
                    "label": "销售额",
                    "table_key": "orders_wide",
                    "field": "amount",
                    "aggregation": "sum",
                    "supported_dimension_keys": [
                        "region",
                        "order_date",
                        "order_month",
                    ],
                    "default_time_dimension_key": "order_date",
                }
            ],
            "dimensions": [
                {
                    "key": "region",
                    "label": "区域",
                    "table_key": "orders_wide",
                    "field": "region_name",
                    "kind": "categorical",
                    "operators": ["eq"],
                },
                {
                    "key": "order_date",
                    "label": "订单日期",
                    "table_key": "orders_wide",
                    "field": "order_date",
                    "kind": "time",
                    "operators": ["gte", "lte", "between"],
                },
                {
                    "key": "order_month",
                    "label": "订单月份",
                    "table_key": "orders_wide",
                    "field": "order_month",
                    "kind": "time",
                    "operators": ["gte", "lte", "between"],
                },
            ],
            "aliases": [
                {"alias": "销售额", "target_type": "metric", "target_key": "amount"},
                {"alias": "区域", "target_type": "dimension", "target_key": "region"},
                {"alias": "月份", "target_type": "dimension", "target_key": "order_month"},
            ],
            "metric_versions": [],
        },
    )


def test_postprocessor_repairs_generic_year_operator_and_month_trend():
    postprocessor = SemanticPostprocessor(plugin_base_dir=Path("/missing"))
    query = SemanticQueryDraft(
        analysis_type="trend",
        metric_key="amount",
        group_by_dimension_keys=[],
        filters=[
            SemanticFilter(
                dimension_key="order_month",
                operator=">=",
                value="2026-01",
            )
        ],
        time_range=None,
    )

    repaired = postprocessor.repair(
        question="2026年每月销售额是多少？",
        catalog=_catalog(),
        semantic_query=query,
    )

    assert repaired.time_range == SemanticTimeRange(
        dimension_key="order_date",
        start="2026-01-01",
        end="2026-12-31",
    )
    assert repaired.group_by_dimension_keys == ["order_month"]
    assert repaired.filters[0].operator == "gte"


def test_postprocessor_repairs_current_year_relative_time():
    postprocessor = SemanticPostprocessor(
        plugin_base_dir=Path("/missing"),
        today=date(2026, 6, 15),
    )
    query = SemanticQueryDraft(
        analysis_type="summary",
        metric_key="amount",
        group_by_dimension_keys=[],
        filters=[],
        time_range=None,
    )

    repaired = postprocessor.repair(
        question="今年销售额是多少？",
        catalog=_catalog(),
        semantic_query=query,
    )

    assert repaired.time_range == SemanticTimeRange(
        dimension_key="order_date",
        start="2026-01-01",
        end="2026-12-31",
    )


def test_postprocessor_repairs_current_month_relative_time():
    postprocessor = SemanticPostprocessor(
        plugin_base_dir=Path("/missing"),
        today=date(2026, 6, 15),
    )
    query = SemanticQueryDraft(
        analysis_type="summary",
        metric_key="amount",
        group_by_dimension_keys=[],
        filters=[],
        time_range=None,
    )

    repaired = postprocessor.repair(
        question="本月销售额是多少？",
        catalog=_catalog(),
        semantic_query=query,
    )

    assert repaired.time_range == SemanticTimeRange(
        dimension_key="order_date",
        start="2026-06-01",
        end="2026-06-30",
    )


def test_postprocessor_repairs_recent_30_days_relative_time():
    postprocessor = SemanticPostprocessor(
        plugin_base_dir=Path("/missing"),
        today=date(2026, 6, 15),
    )
    query = SemanticQueryDraft(
        analysis_type="summary",
        metric_key="amount",
        group_by_dimension_keys=[],
        filters=[],
        time_range=None,
    )

    repaired = postprocessor.repair(
        question="近30天销售额是多少？",
        catalog=_catalog(),
        semantic_query=query,
    )

    assert repaired.time_range == SemanticTimeRange(
        dimension_key="order_date",
        start="2026-05-17",
        end="2026-06-15",
    )


def test_postprocessor_repairs_previous_quarter_relative_time():
    postprocessor = SemanticPostprocessor(
        plugin_base_dir=Path("/missing"),
        today=date(2026, 6, 15),
    )
    query = SemanticQueryDraft(
        analysis_type="summary",
        metric_key="amount",
        group_by_dimension_keys=[],
        filters=[],
        time_range=None,
    )

    repaired = postprocessor.repair(
        question="上季度销售额是多少？",
        catalog=_catalog(),
        semantic_query=query,
    )

    assert repaired.time_range == SemanticTimeRange(
        dimension_key="order_date",
        start="2026-01-01",
        end="2026-03-31",
    )


def test_postprocessor_repairs_explicit_dimension_group_by():
    postprocessor = SemanticPostprocessor(plugin_base_dir=Path("/missing"))
    query = SemanticQueryDraft(
        analysis_type="group_by",
        metric_key="amount",
        group_by_dimension_keys=[],
        filters=[],
        time_range=SemanticTimeRange(
            dimension_key="order_date",
            start="2026-01-01",
            end="2026-12-31",
        ),
    )

    repaired = postprocessor.repair(
        question="2026年各区域销售额是多少？",
        catalog=_catalog(),
        semantic_query=query,
    )

    assert repaired.group_by_dimension_keys == ["region"]


def test_postprocessor_repairs_meige_dimension_group_by():
    postprocessor = SemanticPostprocessor(plugin_base_dir=Path("/missing"))
    query = SemanticQueryDraft(
        analysis_type="group_by",
        metric_key="amount",
        group_by_dimension_keys=[],
        filters=[],
        time_range=SemanticTimeRange(
            dimension_key="order_date",
            start="2026-01-01",
            end="2026-12-31",
        ),
    )

    repaired = postprocessor.repair(
        question="2026年每个区域的销售额是多少？",
        catalog=_catalog(),
        semantic_query=query,
    )

    assert repaired.group_by_dimension_keys == ["region"]


def test_postprocessor_repairs_multiple_explicit_group_by_dimensions():
    postprocessor = SemanticPostprocessor(plugin_base_dir=Path("/missing"))
    query = SemanticQueryDraft(
        analysis_type="group_by",
        metric_key="amount",
        group_by_dimension_keys=[],
        filters=[],
        time_range=SemanticTimeRange(
            dimension_key="order_date",
            start="2026-01-01",
            end="2026-12-31",
        ),
    )

    repaired = postprocessor.repair(
        question="2026年按区域和月份看销售额",
        catalog=_catalog(),
        semantic_query=query,
    )

    assert repaired.group_by_dimension_keys == ["region", "order_month"]


def test_postprocessor_repairs_top_n_metric_ranking():
    postprocessor = SemanticPostprocessor(plugin_base_dir=Path("/missing"))
    query = SemanticQueryDraft(
        analysis_type="group_by",
        metric_key="amount",
        group_by_dimension_keys=["region"],
        filters=[],
        time_range=SemanticTimeRange(
            dimension_key="order_date",
            start="2026-01-01",
            end="2026-12-31",
        ),
    )

    repaired = postprocessor.repair(
        question="2026年各区域销售额前5名",
        catalog=_catalog(),
        semantic_query=query,
    )

    assert repaired.order_by_metric == "desc"
    assert repaired.limit == 5


def test_postprocessor_normalizes_symbolic_operator_with_suffix():
    postprocessor = SemanticPostprocessor(plugin_base_dir=Path("/missing"))
    query = SemanticQueryDraft(
        analysis_type="summary",
        metric_key="amount",
        group_by_dimension_keys=[],
        filters=[
            SemanticFilter(
                dimension_key="order_month",
                operator=">=start",
                value="2026-01",
            )
        ],
        time_range=SemanticTimeRange(
            dimension_key="order_date",
            start="2026-01-01",
            end="2026-12-31",
        ),
    )

    repaired = postprocessor.repair(
        question="2026年区域销售额是多少？",
        catalog=_catalog(),
        semantic_query=query,
    )

    assert repaired.filters[0].operator == "gte"


def test_postprocessor_marks_multi_metric_question_for_clarification():
    catalog = _catalog()
    catalog.metrics.append(
        catalog.metrics[0].model_copy(
            update={"key": "quantity", "label": "销量", "field": "quantity"}
        )
    )
    catalog.aliases.append(
        catalog.aliases[0].model_copy(
            update={"alias": "销量", "target_type": "metric", "target_key": "quantity"}
        )
    )
    postprocessor = SemanticPostprocessor(plugin_base_dir=Path("/missing"))
    query = SemanticQueryDraft(
        analysis_type="summary",
        metric_key="amount",
        group_by_dimension_keys=[],
        filters=[],
        time_range=SemanticTimeRange(
            dimension_key="order_date",
            start="2026-01-01",
            end="2026-12-31",
        ),
    )

    repaired = postprocessor.repair(
        question="2026年销售额和销量分别是多少？",
        catalog=catalog,
        semantic_query=query,
    )

    assert repaired.needs_clarification is True
    assert repaired.clarification_question == "当前一次只支持查询一个指标，请选择一个指标。"


def test_postprocessor_keeps_explicit_multi_metric_draft_ready():
    catalog = _catalog()
    catalog.metrics.append(
        catalog.metrics[0].model_copy(
            update={"key": "quantity", "label": "销量", "field": "quantity"}
        )
    )
    catalog.aliases.append(
        catalog.aliases[0].model_copy(
            update={"alias": "销量", "target_type": "metric", "target_key": "quantity"}
        )
    )
    postprocessor = SemanticPostprocessor(plugin_base_dir=Path("/missing"))
    query = SemanticQueryDraft(
        analysis_type="summary",
        metric_key="amount",
        metric_keys=["amount", "quantity"],
        group_by_dimension_keys=[],
        filters=[],
        time_range=SemanticTimeRange(
            dimension_key="order_date",
            start="2026-01-01",
            end="2026-12-31",
        ),
    )

    repaired = postprocessor.repair(
        question="2026年销售额和销量分别是多少？",
        catalog=catalog,
        semantic_query=query,
    )

    assert repaired.needs_clarification is False
    assert repaired.metric_keys == ["amount", "quantity"]


def test_postprocessor_does_not_treat_overlapping_metric_terms_as_multi_metric():
    catalog = _catalog()
    catalog.metrics[0] = catalog.metrics[0].model_copy(
        update={"key": "hero_count", "label": "hero count", "field": "hero_count"}
    )
    catalog.metrics.append(
        catalog.metrics[0].model_copy(
            update={
                "key": "powered_hero_count",
                "label": "powered hero count",
                "field": "powered_hero_count",
            }
        )
    )
    catalog.aliases[0] = catalog.aliases[0].model_copy(
        update={
            "alias": "hero count",
            "target_type": "metric",
            "target_key": "hero_count",
        }
    )
    catalog.aliases.append(
        catalog.aliases[0].model_copy(
            update={
                "alias": "powered hero count",
                "target_type": "metric",
                "target_key": "powered_hero_count",
            }
        )
    )
    postprocessor = SemanticPostprocessor(plugin_base_dir=Path("/missing"))
    query = SemanticQueryDraft(
        analysis_type="summary",
        metric_key="powered_hero_count",
        metric_keys=["powered_hero_count"],
        group_by_dimension_keys=[],
        filters=[],
        time_range=SemanticTimeRange(
            dimension_key="order_date",
            start="2026-01-01",
            end="2026-12-31",
        ),
    )

    repaired = postprocessor.repair(
        question="Show powered hero count by publisher.",
        catalog=catalog,
        semantic_query=query,
    )

    assert repaired.needs_clarification is False
    assert repaired.clarification_question is None


def test_postprocessor_loads_dataset_value_mapping_plugin(tmp_path: Path):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "custom_dataset.json").write_text(
        json.dumps(
            {
                "dataset_id": "custom_dataset",
                "value_mappings": [
                    {
                        "dimension_key": "region",
                        "operator": "eq",
                        "terms": {
                            "华东": "East China",
                            "华南": "South China",
                        },
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    postprocessor = SemanticPostprocessor(plugin_base_dir=plugin_dir)
    query = SemanticQueryDraft(
        analysis_type="summary",
        metric_key="amount",
        group_by_dimension_keys=[],
        filters=[],
        time_range=SemanticTimeRange(
            dimension_key="order_date",
            start="2026-01-01",
            end="2026-12-31",
        ),
    )

    repaired = postprocessor.repair(
        question="2026年华东销售额是多少？",
        catalog=_catalog(),
        semantic_query=query,
    )

    assert repaired.filters == [
        SemanticFilter(dimension_key="region", operator="eq", value="East China")
    ]


def test_postprocessor_normalizes_existing_filter_value_with_plugin(tmp_path: Path):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "custom_dataset.json").write_text(
        json.dumps(
            {
                "dataset_id": "custom_dataset",
                "value_mappings": [
                    {
                        "dimension_key": "region",
                        "operator": "eq",
                        "terms": {
                            "华东": "East China",
                            "EC": "East China",
                        },
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    postprocessor = SemanticPostprocessor(plugin_base_dir=plugin_dir)
    query = SemanticQueryDraft(
        analysis_type="summary",
        metric_key="amount",
        group_by_dimension_keys=[],
        filters=[
            SemanticFilter(
                dimension_key="region",
                operator="eq",
                value="EC",
            )
        ],
        time_range=SemanticTimeRange(
            dimension_key="order_date",
            start="2026-01-01",
            end="2026-12-31",
        ),
    )

    repaired = postprocessor.repair(
        question="2026年华东销售额是多少？",
        catalog=_catalog(),
        semantic_query=query,
    )

    assert repaired.filters == [
        SemanticFilter(dimension_key="region", operator="eq", value="East China")
    ]


def test_postprocessor_prefers_existing_filter_value_when_multiple_aliases_match(
    tmp_path: Path,
):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "football_dataset.json").write_text(
        json.dumps(
            {
                "dataset_id": "football_dataset",
                "value_mappings": [
                    {
                        "dimension_key": "home_team_name",
                        "operator": "eq",
                        "terms": {
                            "Barcelona": "FC Barcelona",
                            "Real Madrid": "Real Madrid CF",
                        },
                    },
                    {
                        "dimension_key": "away_team_name",
                        "operator": "eq",
                        "terms": {
                            "Barcelona": "FC Barcelona",
                            "Real Madrid": "Real Madrid CF",
                        },
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    catalog = ValidateRequest.parse(
        SemanticCatalog,
        {
            "catalog_version": "2026-06-15",
            "dataset_id": "football_dataset",
            "tables": [
                {
                    "key": "match_fact",
                    "label": "比赛事实表",
                    "physical_table": "match_fact",
                },
                {
                    "key": "home_team_dim",
                    "label": "主队维表",
                    "physical_table": "team",
                },
                {
                    "key": "away_team_dim",
                    "label": "客队维表",
                    "physical_table": "team",
                },
            ],
            "entities": [],
            "relationships": [],
            "metrics": [
                {
                    "key": "match_count",
                    "label": "比赛数",
                    "table_key": "match_fact",
                    "field": "id",
                    "aggregation": "count_distinct",
                    "supported_dimension_keys": [
                        "home_team_name",
                        "away_team_name",
                    ],
                }
            ],
            "dimensions": [
                {
                    "key": "home_team_name",
                    "label": "主队",
                    "table_key": "home_team_dim",
                    "field": "team_long_name",
                    "kind": "categorical",
                    "operators": ["eq"],
                },
                {
                    "key": "away_team_name",
                    "label": "客队",
                    "table_key": "away_team_dim",
                    "field": "team_long_name",
                    "kind": "categorical",
                    "operators": ["eq"],
                },
            ],
            "aliases": [],
            "metric_versions": [],
        },
    )
    postprocessor = SemanticPostprocessor(plugin_base_dir=plugin_dir)
    query = SemanticQueryDraft(
        analysis_type="summary",
        metric_key="match_count",
        group_by_dimension_keys=[],
        filters=[
            SemanticFilter(
                dimension_key="home_team_name",
                operator="eq",
                value="Barcelona",
            ),
            SemanticFilter(
                dimension_key="away_team_name",
                operator="eq",
                value="Real Madrid",
            ),
        ],
        time_range=None,
    )

    repaired = postprocessor.repair(
        question="Show Barcelona home matches against Real Madrid.",
        catalog=catalog,
        semantic_query=query,
    )

    normalized_filters = {
        filter_obj.dimension_key: filter_obj.value for filter_obj in repaired.filters
    }
    assert normalized_filters["home_team_name"] == "FC Barcelona"
    assert normalized_filters["away_team_name"] == "Real Madrid CF"


def test_postprocessor_does_not_auto_append_ambiguous_role_filter(tmp_path: Path):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "football_dataset.json").write_text(
        json.dumps(
            {
                "dataset_id": "football_dataset",
                "value_mappings": [
                    {
                        "dimension_key": "home_team_name",
                        "operator": "eq",
                        "terms": {
                            "Barcelona": "FC Barcelona",
                        },
                    },
                    {
                        "dimension_key": "away_team_name",
                        "operator": "eq",
                        "terms": {
                            "Barcelona": "FC Barcelona",
                        },
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    catalog = ValidateRequest.parse(
        SemanticCatalog,
        {
            "catalog_version": "2026-06-15",
            "dataset_id": "football_dataset",
            "tables": [
                {
                    "key": "match_fact",
                    "label": "比赛事实表",
                    "physical_table": "match_fact",
                },
                {
                    "key": "home_team_dim",
                    "label": "主队维表",
                    "physical_table": "team",
                },
                {
                    "key": "away_team_dim",
                    "label": "客队维表",
                    "physical_table": "team",
                },
            ],
            "entities": [],
            "relationships": [],
            "metrics": [
                {
                    "key": "match_count",
                    "label": "比赛数",
                    "table_key": "match_fact",
                    "field": "id",
                    "aggregation": "count_distinct",
                    "supported_dimension_keys": [
                        "home_team_name",
                        "away_team_name",
                    ],
                }
            ],
            "dimensions": [
                {
                    "key": "home_team_name",
                    "label": "主队",
                    "table_key": "home_team_dim",
                    "field": "team_long_name",
                    "kind": "categorical",
                    "operators": ["eq"],
                },
                {
                    "key": "away_team_name",
                    "label": "客队",
                    "table_key": "away_team_dim",
                    "field": "team_long_name",
                    "kind": "categorical",
                    "operators": ["eq"],
                },
            ],
            "aliases": [],
            "metric_versions": [],
        },
    )
    postprocessor = SemanticPostprocessor(plugin_base_dir=plugin_dir)
    query = SemanticQueryDraft(
        analysis_type="summary",
        metric_key="match_count",
        group_by_dimension_keys=[],
        filters=[
            SemanticFilter(
                dimension_key="home_team_name",
                operator="eq",
                value="Barcelona",
            )
        ],
        time_range=None,
    )

    repaired = postprocessor.repair(
        question="Show Barcelona home matches.",
        catalog=catalog,
        semantic_query=query,
    )

    assert repaired.filters == [
        SemanticFilter(
            dimension_key="home_team_name",
            operator="eq",
            value="FC Barcelona",
        )
    ]


class _FakeValueRetriever:
    def retrieve(self, *, question, catalog, dimensions):
        return [
            SemanticValueCandidate(
                dataset_id=catalog.dataset_id,
                dimension_key="region",
                nl_term="华北",
                db_value="North China",
                operator="eq",
                score=1.0,
                source="fake",
            )
        ]


def test_postprocessor_uses_value_retriever_when_plugin_is_missing():
    postprocessor = SemanticPostprocessor(
        plugin_base_dir=Path("/missing"),
        value_retriever=_FakeValueRetriever(),
    )
    query = SemanticQueryDraft(
        analysis_type="summary",
        metric_key="amount",
        group_by_dimension_keys=[],
        filters=[],
        time_range=SemanticTimeRange(
            dimension_key="order_date",
            start="2026-01-01",
            end="2026-12-31",
        ),
    )

    repaired = postprocessor.repair(
        question="2026年华北销售额是多少？",
        catalog=_catalog(),
        semantic_query=query,
    )

    assert repaired.filters == [
        SemanticFilter(dimension_key="region", operator="eq", value="North China")
    ]
