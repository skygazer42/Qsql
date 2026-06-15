import json
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
