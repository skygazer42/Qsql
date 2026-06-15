"""Controlled SQL builder for semantic queries."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import re
from typing import Any

from .schemas import (
    SemanticCatalog,
    SemanticDimensionDefinition,
    SemanticEntityDefinition,
    QueryExecutionPlan,
    QueryParameter,
    SemanticFilter,
    SemanticMetricDefinition,
    SemanticMetricVersionDefinition,
    SemanticQueryDraft,
    SemanticRelationshipDefinition,
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


def _entity_map(catalog: SemanticCatalog) -> dict[str, SemanticEntityDefinition]:
    return {entity.key: entity for entity in catalog.entities}


def _relationship_map(
    catalog: SemanticCatalog,
) -> dict[str, SemanticRelationshipDefinition]:
    return {relationship.key: relationship for relationship in catalog.relationships}


def _version_map(
    catalog: SemanticCatalog,
) -> dict[str, SemanticMetricVersionDefinition]:
    return {version.key: version for version in catalog.metric_versions}


@dataclass(frozen=True)
class _JoinStep:
    from_table_key: str
    to_table_key: str
    from_field: str
    to_field: str
    join_type: str
    safe: bool = True


def _aggregation_expr(metric: SemanticMetricDefinition, field_ref: str) -> str:
    aggregation = metric.aggregation.lower()
    if aggregation == "count":
        return "COUNT(*)"
    if aggregation == "count_distinct":
        return f"COUNT(DISTINCT {field_ref})"
    if aggregation == "sum":
        return f"SUM({field_ref})"
    if aggregation == "avg":
        return f"AVG({field_ref})"
    if aggregation == "min":
        return f"MIN({field_ref})"
    if aggregation == "max":
        return f"MAX({field_ref})"
    raise ValueError(f"不支持的聚合函数: {metric.aggregation}")


def _render_filter(
    filter_obj: SemanticFilter,
    dimensions: dict[str, SemanticDimensionDefinition],
    field_ref: str,
) -> tuple[str, QueryParameter]:
    dimension = dimensions.get(filter_obj.dimension_key)
    if dimension is None:
        raise ValueError(f"维度未定义: {filter_obj.dimension_key}")

    operator = filter_obj.operator.lower()
    value = filter_obj.value

    if operator == "eq":
        return (
            f"{field_ref} = {_sql_literal(value)}",
            QueryParameter(name=dimension.field, operator="eq", value=value),
        )
    if operator == "in":
        if not isinstance(value, list) or len(value) == 0:
            raise ValueError(f"IN 过滤条件必须是非空数组: {dimension.key}")
        sql_values = ", ".join(_sql_literal(item) for item in value)
        return (
            f"{field_ref} IN ({sql_values})",
            QueryParameter(name=dimension.field, operator="in", value=value),
        )
    if operator == "gte":
        return (
            f"{field_ref} >= {_sql_literal(value)}",
            QueryParameter(name=dimension.field, operator="gte", value=value),
        )
    if operator == "lte":
        return (
            f"{field_ref} <= {_sql_literal(value)}",
            QueryParameter(name=dimension.field, operator="lte", value=value),
        )
    if operator == "between":
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError(f"BETWEEN 过滤条件必须是长度为 2 的数组: {dimension.key}")
        return (
            f"{field_ref} BETWEEN {_sql_literal(value[0])} AND {_sql_literal(value[1])}",
            QueryParameter(name=dimension.field, operator="between", value=value),
        )

    raise ValueError(f"不支持的过滤操作符: {filter_obj.operator}")


def _relationship_steps(
    *,
    relationships: dict[str, SemanticRelationshipDefinition],
    entities: dict[str, SemanticEntityDefinition],
) -> list[_JoinStep]:
    # [CUSTOM] 只把 FK -> PK 方向作为安全 join 边；反向 PK -> FK 仅用于诊断 fan-out 风险。
    steps: list[_JoinStep] = []
    for relationship in relationships.values():
        if not relationship.allowed:
            continue
        left_entity = entities[relationship.left_entity_key]
        right_entity = entities[relationship.right_entity_key]
        join_type = relationship.join_type.upper()
        if left_entity.entity_type == "foreign" and right_entity.entity_type == "primary":
            foreign_entity = left_entity
            primary_entity = right_entity
        elif right_entity.entity_type == "foreign" and left_entity.entity_type == "primary":
            foreign_entity = right_entity
            primary_entity = left_entity
        else:
            continue

        steps.append(
            _JoinStep(
                from_table_key=foreign_entity.table_key,
                to_table_key=primary_entity.table_key,
                from_field=foreign_entity.field,
                to_field=primary_entity.field,
                join_type=join_type,
                safe=True,
            )
        )
        steps.append(
            _JoinStep(
                from_table_key=primary_entity.table_key,
                to_table_key=foreign_entity.table_key,
                from_field=primary_entity.field,
                to_field=foreign_entity.field,
                join_type=join_type,
                safe=False,
            )
        )
    return steps


def _reachable_tables(
    *,
    anchor_table_key: str,
    steps: list[_JoinStep],
    include_unsafe: bool,
) -> set[str]:
    adjacency: dict[str, list[_JoinStep]] = {}
    for step in steps:
        if not include_unsafe and not step.safe:
            continue
        adjacency.setdefault(step.from_table_key, []).append(step)

    queue: deque[str] = deque([anchor_table_key])
    visited: set[str] = {anchor_table_key}
    while queue:
        current = queue.popleft()
        for step in adjacency.get(current, []):
            if step.to_table_key in visited:
                continue
            visited.add(step.to_table_key)
            queue.append(step.to_table_key)
    return visited


def _plan_join_steps(
    *,
    anchor_table_key: str,
    target_table_keys: set[str],
    relationships: dict[str, SemanticRelationshipDefinition],
    entities: dict[str, SemanticEntityDefinition],
) -> list[_JoinStep]:
    # [CUSTOM] 仅允许命中 catalog 中显式声明的最短 join path，找不到就明确报错。
    if not target_table_keys:
        return []

    adjacency: dict[str, list[_JoinStep]] = {}
    relationship_steps = _relationship_steps(relationships=relationships, entities=entities)
    for step in relationship_steps:
        if not step.safe:
            continue
        adjacency.setdefault(step.from_table_key, []).append(step)

    queue: deque[str] = deque([anchor_table_key])
    visited: set[str] = {anchor_table_key}
    parents: dict[str, _JoinStep] = {}

    while queue:
        current = queue.popleft()
        for step in adjacency.get(current, []):
            if step.to_table_key in visited:
                continue
            visited.add(step.to_table_key)
            parents[step.to_table_key] = step
            queue.append(step.to_table_key)

    missing_tables = sorted(table_key for table_key in target_table_keys if table_key not in visited)
    if missing_tables:
        unsafe_reachable = _reachable_tables(
            anchor_table_key=anchor_table_key,
            steps=relationship_steps,
            include_unsafe=True,
        )
        fanout_tables = [
            table_key for table_key in missing_tables if table_key in unsafe_reachable
        ]
        if fanout_tables:
            raise ValueError(
                "join path 可能导致 fan-out: "
                + ", ".join(
                    f"{anchor_table_key} -> {table_key}" for table_key in fanout_tables
                )
            )
        raise ValueError(
            "未声明可用的 join path: "
            + ", ".join(f"{anchor_table_key} -> {table_key}" for table_key in missing_tables)
        )

    join_steps: list[_JoinStep] = []
    joined_tables = {anchor_table_key}
    for target_table_key in sorted(target_table_keys):
        path: list[_JoinStep] = []
        current = target_table_key
        while current != anchor_table_key:
            step = parents[current]
            path.append(step)
            current = step.from_table_key
        for step in reversed(path):
            if step.to_table_key in joined_tables:
                continue
            join_steps.append(step)
            joined_tables.add(step.to_table_key)
    return join_steps


def _field_ref(
    *,
    table_key: str,
    field: str,
    table_aliases: dict[str, str],
) -> str:
    safe_field = _safe_identifier(field)
    alias = table_aliases.get(table_key)
    if alias is None:
        return safe_field
    return f"{alias}.{safe_field}"


def build_query_execution_plan(
    catalog: SemanticCatalog, semantic_query: SemanticQueryDraft
) -> QueryExecutionPlan:
    """Build deterministic SQL from a semantic query draft."""
    tables = _table_map(catalog)
    metrics = _metric_map(catalog)
    dimensions = _dimension_map(catalog)
    entities = _entity_map(catalog)
    relationships = _relationship_map(catalog)
    versions = _version_map(catalog)

    metric_keys = list(dict.fromkeys(semantic_query.metric_keys or [semantic_query.metric_key]))
    resolved_metrics: list[SemanticMetricDefinition] = []
    for metric_key in metric_keys:
        resolved_metric = metrics.get(metric_key)
        if resolved_metric is None:
            raise ValueError(f"指标未定义: {metric_key}")
        resolved_metrics.append(resolved_metric)

    metric = resolved_metrics[0]
    if len(resolved_metrics) > 1 and semantic_query.metric_version_key:
        raise ValueError("多指标查询暂不支持单一 metric_version_key")

    for resolved_metric in resolved_metrics[1:]:
        if resolved_metric.table_key != metric.table_key:
            raise ValueError(
                "多指标查询要求所有指标来自同一语义表: "
                f"{metric.key}->{metric.table_key}, "
                f"{resolved_metric.key}->{resolved_metric.table_key}"
            )

    if semantic_query.time_range is None:
        raise ValueError("缺少时间范围，当前仅支持带时间范围的受控查询")

    time_dimension = dimensions.get(semantic_query.time_range.dimension_key)
    if time_dimension is None:
        raise ValueError(f"时间维度未定义: {semantic_query.time_range.dimension_key}")

    # [CUSTOM] 受控 SQL 只从正式语义表配置解析物理表名，不再让指标直接散落 table 字段。
    table_definition = tables.get(metric.table_key)
    if table_definition is None:
        raise ValueError(f"指标引用了未定义的语义表: {metric.key} -> {metric.table_key}")

    where_clauses = []
    parameters = []

    time_field = _safe_identifier(time_dimension.field)

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

    resolved_filter_dimensions: list[SemanticDimensionDefinition] = []
    for filter_obj in semantic_filters:
        filter_dimension = dimensions.get(filter_obj.dimension_key)
        if filter_dimension is None:
            raise ValueError(f"维度未定义: {filter_obj.dimension_key}")
        resolved_filter_dimensions.append(filter_dimension)

    resolved_group_dimensions: list[SemanticDimensionDefinition] = []
    for dimension_key in semantic_query.group_by_dimension_keys:
        dimension = dimensions.get(dimension_key)
        if dimension is None:
            raise ValueError(f"维度未定义: {dimension_key}")
        for resolved_metric in resolved_metrics:
            if (
                resolved_metric.supported_dimension_keys
                and dimension_key not in resolved_metric.supported_dimension_keys
            ):
                raise ValueError(f"指标不支持维度: {resolved_metric.key} -> {dimension_key}")
        resolved_group_dimensions.append(dimension)

    required_table_keys = {
        time_dimension.table_key,
        *(dimension.table_key for dimension in resolved_filter_dimensions),
        *(dimension.table_key for dimension in resolved_group_dimensions),
    }
    required_table_keys.discard(metric.table_key)
    join_steps = _plan_join_steps(
        anchor_table_key=metric.table_key,
        target_table_keys=required_table_keys,
        relationships=relationships,
        entities=entities,
    )
    table_aliases: dict[str, str] = {}
    if join_steps:
        table_aliases[metric.table_key] = "t0"
        for index, step in enumerate(join_steps, start=1):
            table_aliases[step.to_table_key] = f"t{index}"

    time_field_ref = _field_ref(
        table_key=time_dimension.table_key,
        field=time_dimension.field,
        table_aliases=table_aliases,
    )
    where_clauses.append(f"{time_field_ref} >= {_sql_literal(semantic_query.time_range.start)}")
    parameters.append(
        QueryParameter(
            name=time_field,
            operator="gte",
            value=semantic_query.time_range.start,
        )
    )
    where_clauses.append(f"{time_field_ref} <= {_sql_literal(semantic_query.time_range.end)}")
    parameters.append(
        QueryParameter(
            name=time_field,
            operator="lte",
            value=semantic_query.time_range.end,
        )
    )

    for filter_obj, filter_dimension in zip(semantic_filters, resolved_filter_dimensions):
        filter_sql, parameter = _render_filter(
            filter_obj,
            dimensions,
            _field_ref(
                table_key=filter_dimension.table_key,
                field=filter_dimension.field,
                table_aliases=table_aliases,
            ),
        )
        where_clauses.append(filter_sql)
        parameters.append(parameter)

    group_dimensions = []
    select_dimensions = []
    for dimension_key, dimension in zip(
        semantic_query.group_by_dimension_keys,
        resolved_group_dimensions,
    ):
        field_ref = _field_ref(
            table_key=dimension.table_key,
            field=dimension.field,
            table_aliases=table_aliases,
        )
        select_dimensions.append(f"{field_ref} AS {dimension.key}")
        group_dimensions.append(field_ref)

    metric_select_parts = []
    for resolved_metric in resolved_metrics:
        aggregation_expr = _aggregation_expr(
            resolved_metric,
            _field_ref(
                table_key=resolved_metric.table_key,
                field=resolved_metric.field,
                table_aliases=table_aliases,
            ),
        )
        metric_alias = (
            "metric_value"
            if len(resolved_metrics) == 1
            else _safe_identifier(resolved_metric.key)
        )
        metric_select_parts.append(f"{aggregation_expr} AS {metric_alias}")
    select_parts = [*select_dimensions, *metric_select_parts]
    anchor_table = _safe_identifier(table_definition.physical_table)
    if join_steps:
        sql = f"SELECT {', '.join(select_parts)} FROM {anchor_table} AS {table_aliases[metric.table_key]}"
        for step in join_steps:
            to_table_definition = tables.get(step.to_table_key)
            if to_table_definition is None:
                raise ValueError(f"关系引用了未定义的语义表: {step.to_table_key}")
            to_table = _safe_identifier(to_table_definition.physical_table)
            to_alias = table_aliases[step.to_table_key]
            from_field_ref = _field_ref(
                table_key=step.from_table_key,
                field=step.from_field,
                table_aliases=table_aliases,
            )
            to_field_ref = _field_ref(
                table_key=step.to_table_key,
                field=step.to_field,
                table_aliases=table_aliases,
            )
            sql += (
                f" {step.join_type} JOIN {to_table} AS {to_alias}"
                f" ON {from_field_ref} = {to_field_ref}"
            )
    else:
        sql = f"SELECT {', '.join(select_parts)} FROM {anchor_table}"
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
        metric_keys=[item.key for item in resolved_metrics],
        metric_labels=[item.label for item in resolved_metrics],
        group_by_dimension_keys=semantic_query.group_by_dimension_keys,
    )
