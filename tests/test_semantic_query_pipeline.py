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
