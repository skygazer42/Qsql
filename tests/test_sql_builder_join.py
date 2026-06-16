import json
from pathlib import Path

import pytest

from src.qsql.schemas import SemanticQueryDraft, SemanticTimeRange
from src.qsql.semantic_catalog import load_semantic_catalog
from src.qsql.sql_builder import build_query_execution_plan


def _write_join_catalog(
    tmp_path: Path,
    *,
    include_relationships: bool,
    relationship_allowed: bool = True,
) -> Path:
    semantic_dir = tmp_path / "resources" / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = semantic_dir / "sales_join.json"
    catalog_path.write_text(
        json.dumps(
            {
                "catalog_version": "2026-06-15",
                "dataset_id": "sales_join",
                "tables": [
                    {
                        "key": "sales_orders",
                        "label": "销售订单事实表",
                        "physical_table": "sales_orders",
                        "default_time_dimension_key": "order_date",
                    },
                    {
                        "key": "customers",
                        "label": "客户维表",
                        "physical_table": "dim_customers",
                    },
                ],
                "entities": [
                    {
                        "key": "sales_orders_customer_id",
                        "table_key": "sales_orders",
                        "field": "customer_id",
                        "entity_type": "foreign",
                    },
                    {
                        "key": "customers_id",
                        "table_key": "customers",
                        "field": "id",
                        "entity_type": "primary",
                    },
                ],
                "relationships": (
                    [
                        {
                            "key": "sales_orders_to_customers",
                            "left_entity_key": "sales_orders_customer_id",
                            "right_entity_key": "customers_id",
                            "join_type": "left",
                            "allowed": relationship_allowed,
                        }
                    ]
                    if include_relationships
                    else []
                ),
                "metrics": [
                    {
                        "key": "order_amount",
                        "label": "订单金额",
                        "table_key": "sales_orders",
                        "field": "amount",
                        "aggregation": "sum",
                        "supported_dimension_keys": [
                            "order_date",
                            "customer_city",
                            "customer_level",
                        ],
                        "default_time_dimension_key": "order_date",
                    },
                    {
                        "key": "customer_count",
                        "label": "客户数",
                        "table_key": "customers",
                        "field": "id",
                        "aggregation": "count_distinct",
                        "supported_dimension_keys": ["order_date"],
                    }
                ],
                "dimensions": [
                    {
                        "key": "order_date",
                        "label": "下单日期",
                        "table_key": "sales_orders",
                        "field": "order_date",
                        "kind": "time",
                        "operators": ["between", "gte", "lte"],
                    },
                    {
                        "key": "customer_city",
                        "label": "客户城市",
                        "table_key": "customers",
                        "field": "city_name",
                        "kind": "categorical",
                        "operators": ["eq", "in"],
                    },
                    {
                        "key": "customer_level",
                        "label": "客户等级",
                        "table_key": "customers",
                        "field": "customer_level",
                        "kind": "categorical",
                        "operators": ["eq", "in"],
                    },
                ],
                "aliases": [],
                "metric_versions": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return semantic_dir


def _join_draft() -> SemanticQueryDraft:
    return SemanticQueryDraft(
        analysis_type="group_by",
        metric_key="order_amount",
        group_by_dimension_keys=["customer_city"],
        filters=[
            {
                "dimension_key": "customer_level",
                "operator": "eq",
                "value": "VIP",
            }
        ],
        time_range=SemanticTimeRange(
            dimension_key="order_date",
            start="2026-01-01",
            end="2026-01-31",
        ),
    )


def test_build_query_execution_plan_supports_declared_join_path(tmp_path: Path):
    semantic_dir = _write_join_catalog(tmp_path, include_relationships=True)

    catalog = load_semantic_catalog("sales_join", base_dir=semantic_dir)
    plan = build_query_execution_plan(catalog=catalog, semantic_query=_join_draft())

    assert "FROM sales_orders" in plan.sql
    assert "LEFT JOIN dim_customers" in plan.sql
    assert "customer_id" in plan.sql
    assert "city_name AS customer_city" in plan.sql
    assert "customer_level = 'VIP'" in plan.sql


def test_build_query_execution_plan_supports_metric_ranking_limit(tmp_path: Path):
    semantic_dir = _write_join_catalog(tmp_path, include_relationships=True)

    catalog = load_semantic_catalog("sales_join", base_dir=semantic_dir)
    draft = _join_draft()
    draft.order_by_metric = "desc"
    draft.limit = 5
    plan = build_query_execution_plan(catalog=catalog, semantic_query=draft)

    assert "ORDER BY metric_value DESC" in plan.sql
    assert plan.sql.endswith("LIMIT 5")


def test_build_query_execution_plan_rejects_undeclared_join_path(tmp_path: Path):
    semantic_dir = _write_join_catalog(tmp_path, include_relationships=False)

    catalog = load_semantic_catalog("sales_join", base_dir=semantic_dir)

    with pytest.raises(ValueError, match="未声明可用的 join path"):
        build_query_execution_plan(catalog=catalog, semantic_query=_join_draft())


def test_build_query_execution_plan_rejects_disabled_join_path(tmp_path: Path):
    semantic_dir = _write_join_catalog(
        tmp_path,
        include_relationships=True,
        relationship_allowed=False,
    )

    catalog = load_semantic_catalog("sales_join", base_dir=semantic_dir)

    with pytest.raises(ValueError, match="未声明可用的 join path"):
        build_query_execution_plan(catalog=catalog, semantic_query=_join_draft())


def test_build_query_execution_plan_rejects_reverse_pk_to_fk_fanout(
    tmp_path: Path,
):
    semantic_dir = _write_join_catalog(tmp_path, include_relationships=True)
    catalog = load_semantic_catalog("sales_join", base_dir=semantic_dir)
    draft = SemanticQueryDraft(
        analysis_type="summary",
        metric_key="customer_count",
        group_by_dimension_keys=[],
        filters=[],
        time_range=SemanticTimeRange(
            dimension_key="order_date",
            start="2026-01-01",
            end="2026-01-31",
        ),
    )

    with pytest.raises(ValueError, match="fan-out"):
        build_query_execution_plan(catalog=catalog, semantic_query=draft)


def test_build_query_execution_plan_supports_quoted_field_identifiers(tmp_path: Path):
    semantic_dir = tmp_path / "resources" / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = semantic_dir / "quoted_fields.json"
    catalog_path.write_text(
        json.dumps(
            {
                "catalog_version": "2026-06-15",
                "dataset_id": "quoted_fields",
                "tables": [
                    {
                        "key": "sales_fact",
                        "label": "销售事实表",
                        "physical_table": "sales_fact",
                    }
                ],
                "entities": [],
                "relationships": [],
                "metrics": [
                    {
                        "key": "sales_amount",
                        "label": "销售额",
                        "table_key": "sales_fact",
                        "field": "Sales Amount",
                        "aggregation": "sum",
                        "supported_dimension_keys": ["school_type"],
                    }
                ],
                "dimensions": [
                    {
                        "key": "school_type",
                        "label": "学校类型",
                        "table_key": "sales_fact",
                        "field": "School Type",
                        "kind": "categorical",
                        "operators": ["eq", "in"],
                    }
                ],
                "aliases": [],
                "metric_versions": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    catalog = load_semantic_catalog("quoted_fields", base_dir=semantic_dir)
    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="sales_amount",
            group_by_dimension_keys=["school_type"],
            filters=[
                {
                    "dimension_key": "school_type",
                    "operator": "eq",
                    "value": "High School",
                }
            ],
            time_range=None,
        ),
    )

    assert 'SUM("Sales Amount") AS metric_value' in plan.sql
    assert '"School Type" AS school_type' in plan.sql
    assert '"School Type" = \'High School\'' in plan.sql


def test_build_query_execution_plan_is_stable_when_filter_order_changes(tmp_path: Path):
    semantic_dir = _write_join_catalog(tmp_path, include_relationships=True)
    catalog = load_semantic_catalog("sales_join", base_dir=semantic_dir)

    draft_a = SemanticQueryDraft(
        analysis_type="group_by",
        metric_key="order_amount",
        group_by_dimension_keys=["customer_city"],
        filters=[
            {
                "dimension_key": "customer_level",
                "operator": "eq",
                "value": "VIP",
            },
            {
                "dimension_key": "customer_city",
                "operator": "eq",
                "value": "Shanghai",
            },
        ],
        time_range=SemanticTimeRange(
            dimension_key="order_date",
            start="2026-01-01",
            end="2026-01-31",
        ),
    )
    draft_b = SemanticQueryDraft(
        analysis_type="group_by",
        metric_key="order_amount",
        group_by_dimension_keys=["customer_city"],
        filters=list(reversed(draft_a.filters)),
        time_range=draft_a.time_range,
    )

    plan_a = build_query_execution_plan(catalog=catalog, semantic_query=draft_a)
    plan_b = build_query_execution_plan(catalog=catalog, semantic_query=draft_b)

    assert plan_a.sql == plan_b.sql
