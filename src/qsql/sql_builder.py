"""Controlled SQL builder for semantic queries."""

from __future__ import annotations

import re
from typing import Any

from .schemas import (
    QueryExecutionPlan,
    QueryParameter,
    SemanticCatalog,
    SemanticDimensionDefinition,
    SemanticFilter,
    SemanticMetricDefinition,
    SemanticMetricVersionDefinition,
    SemanticQueryDraft,
    SemanticTableDefinition,
)


_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_identifier(value: str) -> str:
    if not _IDENTIFIER_PATTERN.match(value):
        raise ValueError(f"非法标识符: {value}")
    return value


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)

    text = str(value).replace("'", "''")
    return f"'{text}'"


def _metric_map(catalog: SemanticCatalog) -> dict[str, SemanticMetricDefinition]:
    return {metric.key: metric for metric in catalog.metrics}


def _table_map(catalog: SemanticCatalog) -> dict[str, SemanticTableDefinition]:
    return {table.key: table for table in catalog.tables}


def _dimension_map(catalog: SemanticCatalog) -> dict[str, SemanticDimensionDefinition]:
    return {dimension.key: dimension for dimension in catalog.dimensions}


def _version_map(
    catalog: SemanticCatalog,
) -> dict[str, SemanticMetricVersionDefinition]:
    return {version.key: version for version in catalog.metric_versions}


def _aggregation_expr(metric: SemanticMetricDefinition) -> str:
    field = _safe_identifier(metric.field)
    aggregation = metric.aggregation.lower()
    if aggregation == "count":
        return "COUNT(*)"
    if aggregation == "count_distinct":
        return f"COUNT(DISTINCT {field})"
    if aggregation == "sum":
        return f"SUM({field})"
    if aggregation == "avg":
        return f"AVG({field})"
    if aggregation == "min":
        return f"MIN({field})"
    if aggregation == "max":
        return f"MAX({field})"
    raise ValueError(f"不支持的聚合函数: {metric.aggregation}")


def _render_filter(
    filter_obj: SemanticFilter,
    dimensions: dict[str, SemanticDimensionDefinition],
) -> tuple[str, QueryParameter]:
    dimension = dimensions.get(filter_obj.dimension_key)
    if dimension is None:
        raise ValueError(f"维度未定义: {filter_obj.dimension_key}")

    field = _safe_identifier(dimension.field)
    operator = filter_obj.operator.lower()
    value = filter_obj.value

    if operator == "eq":
        return (
            f"{field} = {_sql_literal(value)}",
            QueryParameter(name=field, operator="eq", value=value),
        )
    if operator == "in":
        if not isinstance(value, list) or len(value) == 0:
            raise ValueError(f"IN 过滤条件必须是非空数组: {dimension.key}")
        sql_values = ", ".join(_sql_literal(item) for item in value)
        return (
            f"{field} IN ({sql_values})",
            QueryParameter(name=field, operator="in", value=value),
        )
    if operator == "gte":
        return (
            f"{field} >= {_sql_literal(value)}",
            QueryParameter(name=field, operator="gte", value=value),
        )
    if operator == "lte":
        return (
            f"{field} <= {_sql_literal(value)}",
            QueryParameter(name=field, operator="lte", value=value),
        )
    if operator == "between":
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError(f"BETWEEN 过滤条件必须是长度为 2 的数组: {dimension.key}")
        return (
            f"{field} BETWEEN {_sql_literal(value[0])} AND {_sql_literal(value[1])}",
            QueryParameter(name=field, operator="between", value=value),
        )

    raise ValueError(f"不支持的过滤操作符: {filter_obj.operator}")


def build_query_execution_plan(
    catalog: SemanticCatalog, semantic_query: SemanticQueryDraft
) -> QueryExecutionPlan:
    """Build deterministic SQL from a semantic query draft."""
    tables = _table_map(catalog)
    metrics = _metric_map(catalog)
    dimensions = _dimension_map(catalog)
    versions = _version_map(catalog)

    metric = metrics.get(semantic_query.metric_key)
    if metric is None:
        raise ValueError(f"指标未定义: {semantic_query.metric_key}")

    if semantic_query.time_range is None:
        raise ValueError("缺少时间范围，当前仅支持带时间范围的受控查询")

    time_dimension = dimensions.get(semantic_query.time_range.dimension_key)
    if time_dimension is None:
        raise ValueError(f"时间维度未定义: {semantic_query.time_range.dimension_key}")

    # [CUSTOM] 受控 SQL 只从正式语义表配置解析物理表名，不再让指标直接散落 table 字段。
    table_definition = tables.get(metric.table_key)
    if table_definition is None:
        raise ValueError(f"指标引用了未定义的语义表: {metric.key} -> {metric.table_key}")

    table = _safe_identifier(table_definition.physical_table)
    where_clauses = []
    parameters = []

    if time_dimension.table_key != metric.table_key:
        raise ValueError("当前只支持单表宽表查询")

    time_field = _safe_identifier(time_dimension.field)
    where_clauses.append(f"{time_field} >= {_sql_literal(semantic_query.time_range.start)}")
    parameters.append(
        QueryParameter(
            name=time_field,
            operator="gte",
            value=semantic_query.time_range.start,
        )
    )
    where_clauses.append(f"{time_field} <= {_sql_literal(semantic_query.time_range.end)}")
    parameters.append(
        QueryParameter(
            name=time_field,
            operator="lte",
            value=semantic_query.time_range.end,
        )
    )

    if semantic_query.metric_version_key:
        version = versions.get(semantic_query.metric_version_key)
        if version is None:
            raise ValueError(f"指标口径未定义: {semantic_query.metric_version_key}")
        if version.metric_key != metric.key:
            raise ValueError(
                f"指标口径与指标不匹配: version={version.key}, metric={metric.key}"
            )
        if metric.allowed_version_keys and version.key not in metric.allowed_version_keys:
            raise ValueError(f"指标不支持该口径: {version.key}")
        semantic_filters = [*version.filters, *semantic_query.filters]
    else:
        semantic_filters = list(semantic_query.filters)

    for filter_obj in semantic_filters:
        filter_sql, parameter = _render_filter(filter_obj, dimensions)
        filter_dimension = dimensions[filter_obj.dimension_key]
        if filter_dimension.table_key != metric.table_key:
            raise ValueError("当前只支持单表宽表查询")
        where_clauses.append(filter_sql)
        parameters.append(parameter)

    group_dimensions = []
    select_dimensions = []
    for dimension_key in semantic_query.group_by_dimension_keys:
        dimension = dimensions.get(dimension_key)
        if dimension is None:
            raise ValueError(f"维度未定义: {dimension_key}")
        if metric.supported_dimension_keys and dimension_key not in metric.supported_dimension_keys:
            raise ValueError(f"指标不支持维度: {dimension_key}")
        if dimension.table_key != metric.table_key:
            raise ValueError("当前只支持单表宽表查询")
        field = _safe_identifier(dimension.field)
        select_dimensions.append(f"{field} AS {dimension.key}")
        group_dimensions.append(field)

    aggregation_expr = _aggregation_expr(metric)
    select_parts = [*select_dimensions, f"{aggregation_expr} AS metric_value"]
    sql = f"SELECT {', '.join(select_parts)} FROM {table}"
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
    if group_dimensions:
        sql += " GROUP BY " + ", ".join(group_dimensions)
        sql += " ORDER BY " + ", ".join(group_dimensions)

    return QueryExecutionPlan(
        dataset_id=catalog.dataset_id,
        table=table_definition.physical_table,
        sql=sql,
        parameters=parameters,
        analysis_type=semantic_query.analysis_type,
        metric_key=metric.key,
        metric_label=metric.label,
        group_by_dimension_keys=semantic_query.group_by_dimension_keys,
    )
