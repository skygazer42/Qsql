import json
from pathlib import Path

import pytest

from src.qsql.schemas import (
    QueryExecutionPlan,
    SemanticCatalog,
    SemanticQueryRequest,
    SemanticQueryDraft,
    SemanticStageTimings,
    SemanticTimeRange,
)
from src.qsql.semantic_catalog import load_semantic_catalog
from src.qsql.semantic_service import SemanticQueryService
from src.qsql.sql_builder import build_query_execution_plan


def _write_catalog(tmp_path: Path, dataset_id: str = "sales") -> Path:
    semantic_dir = tmp_path / "resources" / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = semantic_dir / f"{dataset_id}.json"
    catalog_path.write_text(
        json.dumps(
            {
                "catalog_version": "2026-06-11",
                "dataset_id": dataset_id,
                "tables": [
                    {
                        "key": "sales_order_wide",
                        "label": "销售订单宽表",
                        "physical_table": "sales_orders",
                        "description": "订单聚合分析统一宽表",
                        "default_time_dimension_key": "order_date",
                    }
                ],
                "metrics": [
                    {
                        "key": "order_amount",
                        "label": "订单金额",
                        "table_key": "sales_order_wide",
                        "field": "amount",
                        "aggregation": "sum",
                        "supported_dimension_keys": ["city", "order_date"],
                        "default_time_dimension_key": "order_date",
                        "allowed_version_keys": ["won_only"],
                    },
                    {
                        "key": "order_count",
                        "label": "订单数",
                        "table_key": "sales_order_wide",
                        "field": "order_id",
                        "aggregation": "count_distinct",
                        "supported_dimension_keys": ["city", "order_date"],
                        "default_time_dimension_key": "order_date",
                    }
                ],
                "dimensions": [
                    {
                        "key": "city",
                        "label": "城市",
                        "table_key": "sales_order_wide",
                        "field": "city_name",
                        "kind": "categorical",
                        "operators": ["eq", "in"],
                    },
                    {
                        "key": "order_date",
                        "label": "下单日期",
                        "table_key": "sales_order_wide",
                        "field": "order_date",
                        "kind": "time",
                        "operators": ["between", "gte", "lte"],
                    },
                ],
                "aliases": [
                    {"alias": "成交金额", "target_type": "metric", "target_key": "order_amount"},
                    {"alias": "订单数", "target_type": "metric", "target_key": "order_count"},
                    {"alias": "城市", "target_type": "dimension", "target_key": "city"},
                ],
                "metric_versions": [
                    {
                        "key": "won_only",
                        "label": "已赢单口径",
                        "metric_key": "order_amount",
                        "filters": [
                            {"dimension_key": "city", "operator": "eq", "value": "杭州"}
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return semantic_dir


def _write_no_time_catalog(tmp_path: Path, dataset_id: str = "heroes") -> Path:
    semantic_dir = tmp_path / "resources" / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = semantic_dir / f"{dataset_id}.json"
    catalog_path.write_text(
        json.dumps(
            {
                "catalog_version": "2026-06-15",
                "dataset_id": dataset_id,
                "tables": [
                    {
                        "key": "hero_wide",
                        "label": "英雄宽表",
                        "physical_table": "heroes",
                        "description": "无时间维英雄统计宽表"
                    }
                ],
                "metrics": [
                    {
                        "key": "hero_count",
                        "label": "英雄数",
                        "table_key": "hero_wide",
                        "field": "hero_id",
                        "aggregation": "count",
                        "supported_dimension_keys": ["publisher"]
                    }
                ],
                "dimensions": [
                    {
                        "key": "publisher",
                        "label": "出版社",
                        "table_key": "hero_wide",
                        "field": "publisher_name",
                        "kind": "categorical",
                        "operators": ["eq", "in"]
                    }
                ],
                "aliases": [
                    {"alias": "英雄数", "target_type": "metric", "target_key": "hero_count"},
                    {"alias": "出版社", "target_type": "dimension", "target_key": "publisher"}
                ],
                "metric_versions": []
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return semantic_dir


def _valid_draft() -> SemanticQueryDraft:
    return SemanticQueryDraft(
        analysis_type="summary",
        metric_key="order_amount",
        group_by_dimension_keys=[],
        filters=[],
        time_range=SemanticTimeRange(
            dimension_key="order_date",
            start="2026-01-01",
            end="2026-01-31",
        ),
        metric_version_key=None,
        needs_clarification=False,
        clarification_question=None,
    )


def test_load_semantic_catalog_returns_typed_model(tmp_path: Path):
    semantic_dir = _write_catalog(tmp_path)

    catalog = load_semantic_catalog("sales", base_dir=semantic_dir)

    assert isinstance(catalog, SemanticCatalog)
    assert catalog.catalog_version == "2026-06-11"
    assert catalog.dataset_id == "sales"
    assert catalog.tables[0].key == "sales_order_wide"
    assert catalog.tables[0].physical_table == "sales_orders"
    assert catalog.metrics[0].key == "order_amount"
    assert catalog.metrics[0].table_key == "sales_order_wide"
    assert catalog.dimensions[0].key == "city"
    assert catalog.dimensions[0].table_key == "sales_order_wide"


def test_load_builtin_sales_catalog():
    catalog = load_semantic_catalog("sales")

    assert catalog.catalog_version
    assert catalog.dataset_id == "sales"
    assert any(table.key == "sales_order_wide" for table in catalog.tables)
    assert any(metric.key == "order_amount" for metric in catalog.metrics)


def test_load_semantic_catalog_rejects_unknown_table_key(tmp_path: Path):
    semantic_dir = _write_catalog(tmp_path)
    catalog_path = semantic_dir / "sales.json"
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    payload["metrics"][0]["table_key"] = "missing_table"
    catalog_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="指标引用了未定义的语义表"):
        load_semantic_catalog("sales", base_dir=semantic_dir)


def test_load_semantic_catalog_rejects_legacy_flat_structure(tmp_path: Path):
    semantic_dir = tmp_path / "resources" / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    (semantic_dir / "sales.json").write_text(
        json.dumps(
            {
                "dataset_id": "sales",
                "metrics": [
                    {
                        "key": "order_amount",
                        "label": "订单金额",
                        "table": "sales_orders",
                        "field": "amount",
                        "aggregation": "sum",
                    }
                ],
                "dimensions": [
                    {
                        "key": "order_date",
                        "label": "下单日期",
                        "table": "sales_orders",
                        "field": "order_date",
                        "kind": "time",
                        "operators": ["between", "gte", "lte"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="只支持新版语义目录结构"):
        load_semantic_catalog("sales", base_dir=semantic_dir)


def test_build_query_execution_plan_builds_summary_sql(tmp_path: Path):
    semantic_dir = _write_catalog(tmp_path)
    catalog = load_semantic_catalog("sales", base_dir=semantic_dir)

    plan = build_query_execution_plan(catalog=catalog, semantic_query=_valid_draft())

    assert isinstance(plan, QueryExecutionPlan)
    assert plan.table == "sales_orders"
    assert "SELECT SUM(amount) AS metric_value" in plan.sql
    assert "FROM sales_orders" in plan.sql
    assert "order_date >=" in plan.sql
    assert "order_date <=" in plan.sql


def test_build_query_execution_plan_builds_same_grain_multi_metric_sql(
    tmp_path: Path,
):
    semantic_dir = _write_catalog(tmp_path)
    catalog = load_semantic_catalog("sales", base_dir=semantic_dir)
    draft = SemanticQueryDraft(
        analysis_type="group_by",
        metric_key="order_amount",
        metric_keys=["order_amount", "order_count"],
        group_by_dimension_keys=["city"],
        filters=[],
        time_range=SemanticTimeRange(
            dimension_key="order_date",
            start="2026-01-01",
            end="2026-01-31",
        ),
    )

    plan = build_query_execution_plan(catalog=catalog, semantic_query=draft)

    assert "city_name AS city" in plan.sql
    assert "SUM(amount) AS order_amount" in plan.sql
    assert "COUNT(DISTINCT order_id) AS order_count" in plan.sql
    assert "GROUP BY city_name" in plan.sql
    assert plan.metric_key == "order_amount"
    assert plan.metric_keys == ["order_amount", "order_count"]
    assert plan.metric_labels == ["订单金额", "订单数"]


def test_build_query_execution_plan_rejects_multi_metric_across_tables(
    tmp_path: Path,
):
    semantic_dir = _write_catalog(tmp_path)
    catalog_path = semantic_dir / "sales.json"
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    payload["tables"].append(
        {
            "key": "refund_wide",
            "label": "退款宽表",
            "physical_table": "refund_orders",
            "default_time_dimension_key": "refund_date",
        }
    )
    payload["metrics"].append(
        {
            "key": "refund_amount",
            "label": "退款金额",
            "table_key": "refund_wide",
            "field": "refund_amount",
            "aggregation": "sum",
            "supported_dimension_keys": ["refund_date"],
            "default_time_dimension_key": "refund_date",
        }
    )
    payload["dimensions"].append(
        {
            "key": "refund_date",
            "label": "退款日期",
            "table_key": "refund_wide",
            "field": "refund_date",
            "kind": "time",
            "operators": ["between", "gte", "lte"],
        }
    )
    catalog_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    catalog = load_semantic_catalog("sales", base_dir=semantic_dir)
    draft = SemanticQueryDraft(
        analysis_type="summary",
        metric_key="order_amount",
        metric_keys=["order_amount", "refund_amount"],
        group_by_dimension_keys=[],
        filters=[],
        time_range=SemanticTimeRange(
            dimension_key="order_date",
            start="2026-01-01",
            end="2026-01-31",
        ),
    )

    with pytest.raises(ValueError, match="多指标查询要求所有指标来自同一语义表"):
        build_query_execution_plan(catalog=catalog, semantic_query=draft)


def test_build_query_execution_plan_rejects_unsupported_dimension(tmp_path: Path):
    semantic_dir = _write_catalog(tmp_path)
    catalog = load_semantic_catalog("sales", base_dir=semantic_dir)
    draft = _valid_draft()
    draft.group_by_dimension_keys = ["unknown_dimension"]

    with pytest.raises(ValueError, match="维度未定义"):
        build_query_execution_plan(catalog=catalog, semantic_query=draft)


class _ClarificationParser:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="summary",
            metric_key="order_amount",
            group_by_dimension_keys=[],
            filters=[],
            time_range=None,
            metric_version_key=None,
            needs_clarification=True,
            clarification_question="你要查哪个时间范围？",
        )


class _ReadyParser:
    def parse(self, question, catalog, history=None):
        return _valid_draft()


class _MissingTimeParser:
    def parse(self, question, catalog, history=None):
        draft = _valid_draft()
        draft.time_range = None
        return draft


class _ReadyNoTimeParser:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="summary",
            metric_key="hero_count",
            group_by_dimension_keys=[],
            filters=[
                {
                    "dimension_key": "publisher",
                    "operator": "eq",
                    "value": "Marvel Comics",
                }
            ],
            time_range=None,
        )


def test_semantic_query_service_returns_clarification(tmp_path: Path):
    semantic_dir = _write_catalog(tmp_path)
    service = SemanticQueryService(
        semantic_base_dir=semantic_dir,
        parser=_ClarificationParser(),
    )

    result = service.prepare_query(
        SemanticQueryRequest(dataset_id="sales", question="成交金额是多少")
    )

    assert result.status == "clarification"
    assert result.clarification_question == "你要查哪个时间范围？"
    assert result.execution_plan is None


def test_semantic_query_service_returns_metric_clarification_options(
    tmp_path: Path,
):
    semantic_dir = _write_catalog(tmp_path)
    service = SemanticQueryService(
        semantic_base_dir=semantic_dir,
        parser=_ReadyParser(),
    )

    result = service.prepare_query(
        SemanticQueryRequest(dataset_id="sales", question="一月成交金额和订单数分别是多少")
    )

    assert result.status == "clarification"
    assert result.clarification_options is not None
    assert [option.target_type for option in result.clarification_options] == [
        "metric",
        "metric",
    ]
    assert {option.key for option in result.clarification_options} == {
        "order_amount",
        "order_count",
    }


def test_semantic_query_service_returns_time_range_clarification_options(
    tmp_path: Path,
):
    semantic_dir = _write_catalog(tmp_path)
    service = SemanticQueryService(
        semantic_base_dir=semantic_dir,
        parser=_MissingTimeParser(),
    )

    result = service.prepare_query(
        SemanticQueryRequest(dataset_id="sales", question="成交金额是多少")
    )

    assert result.status == "clarification"
    assert result.clarification_options is not None
    assert [option.key for option in result.clarification_options] == [
        "current_year",
        "current_month",
        "custom_range",
    ]
    assert result.clarification_options[0].target_type == "time_range"
    assert result.clarification_options[0].value["dimension_key"] == "order_date"


def test_semantic_query_service_returns_execution_plan(tmp_path: Path):
    semantic_dir = _write_catalog(tmp_path)
    service = SemanticQueryService(
        semantic_base_dir=semantic_dir,
        parser=_ReadyParser(),
    )

    result = service.prepare_query(
        SemanticQueryRequest(dataset_id="sales", question="一月成交金额是多少")
    )

    assert result.status == "ready"
    assert result.execution_plan is not None
    assert "SUM(amount)" in result.execution_plan.sql


def test_build_query_execution_plan_supports_no_time_metric(tmp_path: Path):
    semantic_dir = _write_no_time_catalog(tmp_path)
    catalog = load_semantic_catalog("heroes", base_dir=semantic_dir)

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="summary",
            metric_key="hero_count",
            group_by_dimension_keys=[],
            filters=[
                {
                    "dimension_key": "publisher",
                    "operator": "eq",
                    "value": "Marvel Comics",
                }
            ],
            time_range=None,
        ),
    )

    assert plan.table == "heroes"
    assert "COUNT(*) AS metric_value" in plan.sql
    assert "publisher_name = 'Marvel Comics'" in plan.sql
    assert "WHERE publisher_name = 'Marvel Comics'" in plan.sql
    assert "order_date" not in plan.sql


def test_semantic_query_service_returns_ready_for_no_time_metric(tmp_path: Path):
    semantic_dir = _write_no_time_catalog(tmp_path)
    service = SemanticQueryService(
        semantic_base_dir=semantic_dir,
        parser=_ReadyNoTimeParser(),
    )

    result = service.prepare_query(
        SemanticQueryRequest(dataset_id="heroes", question="Marvel Comics 的英雄数是多少")
    )

    assert result.status == "ready"
    assert result.execution_plan is not None
    assert "COUNT(*) AS metric_value" in result.execution_plan.sql
    assert "publisher_name = 'Marvel Comics'" in result.execution_plan.sql


def test_semantic_query_service_returns_stage_timings(tmp_path: Path):
    semantic_dir = _write_catalog(tmp_path)
    service = SemanticQueryService(
        semantic_base_dir=semantic_dir,
        parser=_ReadyParser(),
    )

    result = service.prepare_query(
        SemanticQueryRequest(dataset_id="sales", question="一月成交金额是多少")
    )

    assert isinstance(result.timings, SemanticStageTimings)
    assert result.timings.catalog_load_ms >= 0
    assert result.timings.semantic_agent_ms >= 0
    assert result.timings.sql_build_ms >= 0
    assert result.timings.total_ms >= 0
