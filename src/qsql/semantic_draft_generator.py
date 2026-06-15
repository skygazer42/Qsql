"""Generate formal semantic catalog drafts from metadata store records."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from src.utils import setting

from .metadata_store import MetadataStore
from .schemas import (
    SemanticAliasDefinition,
    SemanticCatalog,
    SemanticDimensionDefinition,
    SemanticDraftArtifact,
    SemanticEntityDefinition,
    SemanticMetricDefinition,
    SemanticRelationshipDefinition,
    SemanticTableDefinition,
    ValidateRequest,
)


DEFAULT_SEMANTIC_DRAFT_DIR = Path(setting.SEMANTIC_DRAFT_DIR)
_NON_IDENTIFIER_PATTERN = re.compile(r"[^A-Za-z0-9_]+")


def _normalize_key(value: str, *, prefix: str) -> str:
    key = _NON_IDENTIFIER_PATTERN.sub("_", value.strip()).strip("_").lower()
    if key == "":
        key = prefix
    if key[0].isdigit():
        key = f"{prefix}_{key}"
    return key


def _infer_dimension_kind(data_type: str) -> str:
    normalized = (data_type or "").strip().lower()
    if any(token in normalized for token in ["date", "time", "timestamp", "year"]):
        return "time"
    if any(
        token in normalized
        for token in ["int", "decimal", "numeric", "float", "double", "real"]
    ):
        return "number"
    return "categorical"


def _operators_for_kind(kind: str) -> list[str]:
    if kind == "time":
        return ["between", "gte", "lte"]
    if kind == "number":
        return ["eq", "in", "gte", "lte", "between"]
    return ["eq", "in"]


def _dimension_map_for_table(columns: list[dict]) -> list[SemanticDimensionDefinition]:
    dimensions: list[SemanticDimensionDefinition] = []
    for column in columns:
        if int(column.get("is_primary_key") or 0) == 1:
            continue
        kind = _infer_dimension_kind(column.get("data_type") or "")
        column_name = str(column["column_name"])
        dimensions.append(
            SemanticDimensionDefinition(
                key=_normalize_key(column_name, prefix="dim"),
                label=column.get("column_comment") or column_name,
                table_key=_normalize_key(str(column["table_name"]), prefix="table"),
                field=column_name,
                kind=kind,
                operators=_operators_for_kind(kind),
            )
        )
    return dimensions


def _default_time_dimension_key(
    dimensions: list[SemanticDimensionDefinition],
) -> str | None:
    for dimension in dimensions:
        if dimension.kind == "time":
            return dimension.key
    return None


def _metric_source_column(columns: list[dict]) -> str:
    for column in columns:
        if int(column.get("is_primary_key") or 0) == 1:
            return str(column["column_name"])
    return str(columns[0]["column_name"])


# [CUSTOM] metadata 草稿阶段同步生成 join 实体/关系，避免多表能力只能靠手写 catalog。
def _entity_key(table_name: str, column_name: str) -> str:
    return f"{_normalize_key(table_name, prefix='table')}_{_normalize_key(column_name, prefix='entity')}"


def _build_entities(columns: list[dict]) -> list[SemanticEntityDefinition]:
    entities: list[SemanticEntityDefinition] = []
    for column in columns:
        is_primary_key = int(column.get("is_primary_key") or 0) == 1
        is_foreign_key = int(column.get("is_foreign_key") or 0) == 1
        if not is_primary_key and not is_foreign_key:
            continue
        entities.append(
            SemanticEntityDefinition(
                key=_entity_key(str(column["table_name"]), str(column["column_name"])),
                table_key=_normalize_key(str(column["table_name"]), prefix="table"),
                field=str(column["column_name"]),
                entity_type="primary" if is_primary_key else "foreign",
            )
        )
    return entities


def _build_relationships(
    relationships: list[dict],
    entity_keys: set[str],
) -> list[SemanticRelationshipDefinition]:
    items: list[SemanticRelationshipDefinition] = []
    for relationship in relationships:
        left_entity_key = _entity_key(
            str(relationship["source_table_name"]),
            str(relationship["source_column_name"]),
        )
        right_entity_key = _entity_key(
            str(relationship["target_table_name"]),
            str(relationship["target_column_name"]),
        )
        if left_entity_key not in entity_keys or right_entity_key not in entity_keys:
            continue
        items.append(
            SemanticRelationshipDefinition(
                key=(
                    f"{_normalize_key(str(relationship['source_table_name']), prefix='table')}"
                    f"_to_{_normalize_key(str(relationship['target_table_name']), prefix='table')}"
                    f"_{_normalize_key(str(relationship['source_column_name']), prefix='entity')}"
                ),
                left_entity_key=left_entity_key,
                right_entity_key=right_entity_key,
                join_type="left",
                description=relationship.get("description"),
            )
        )
    return items


def _numeric_metric_columns(columns: list[dict]) -> list[dict]:
    items = []
    for column in columns:
        if int(column.get("is_primary_key") or 0) == 1:
            continue
        if int(column.get("is_foreign_key") or 0) == 1:
            continue
        if _infer_dimension_kind(column.get("data_type") or "") != "number":
            continue
        items.append(column)
    return items


def generate_semantic_catalog_draft(
    *,
    store: MetadataStore,
    dataset_id: str,
) -> SemanticDraftArtifact:
    """Generate a formal semantic catalog draft from schema metadata."""
    # [CUSTOM] 元数据层只生成“可编辑草稿”，不直接覆盖生产语义目录，保持主查询链路稳定。
    tables = store.list_schema_tables(dataset_id)
    columns = store.list_schema_columns(dataset_id)
    relationships = store.list_schema_relationships(dataset_id)
    value_mappings = store.list_value_mappings(dataset_id)

    if not tables:
        raise ValueError(f"数据集缺少 schema_table 元数据: {dataset_id}")

    grouped_columns: dict[str, list[dict]] = {}
    for column in columns:
        grouped_columns.setdefault(str(column["table_name"]), []).append(column)

    semantic_tables: list[SemanticTableDefinition] = []
    semantic_entities = _build_entities(columns)
    semantic_dimensions: list[SemanticDimensionDefinition] = []
    semantic_metrics: list[SemanticMetricDefinition] = []
    semantic_aliases: list[SemanticAliasDefinition] = []

    for table in tables:
        table_name = str(table["table_name"])
        table_key = _normalize_key(table_name, prefix="table")
        table_columns = grouped_columns.get(table_name, [])
        if not table_columns:
            continue

        table_dimensions = _dimension_map_for_table(table_columns)
        time_dimension_key = _default_time_dimension_key(table_dimensions)
        supported_dimension_keys = [dimension.key for dimension in table_dimensions]

        semantic_tables.append(
            SemanticTableDefinition(
                key=table_key,
                label=table.get("table_comment") or table_name,
                physical_table=table_name,
                description=table.get("table_comment"),
                default_time_dimension_key=time_dimension_key,
            )
        )
        semantic_dimensions.extend(table_dimensions)

        count_metric_key = f"{table_key}_count"
        count_metric_label = f"{table.get('table_comment') or table_name}数量"
        semantic_metrics.append(
            SemanticMetricDefinition(
                key=count_metric_key,
                label=count_metric_label,
                table_key=table_key,
                field=_metric_source_column(table_columns),
                aggregation="count",
                supported_dimension_keys=supported_dimension_keys,
                default_time_dimension_key=time_dimension_key,
                allowed_version_keys=[],
                description="自动生成的计数指标草稿",
            )
        )
        semantic_aliases.append(
            SemanticAliasDefinition(
                alias=count_metric_label,
                target_type="metric",
                target_key=count_metric_key,
            )
        )

        for numeric_column in _numeric_metric_columns(table_columns):
            column_name = str(numeric_column["column_name"])
            column_key = _normalize_key(column_name, prefix="metric")
            column_label = numeric_column.get("column_comment") or column_name
            metric_key = f"{table_key}_{column_key}_sum"
            metric_label = f"{column_label}合计"
            semantic_metrics.append(
                SemanticMetricDefinition(
                    key=metric_key,
                    label=metric_label,
                    table_key=table_key,
                    field=column_name,
                    aggregation="sum",
                    supported_dimension_keys=supported_dimension_keys,
                    default_time_dimension_key=time_dimension_key,
                    allowed_version_keys=[],
                    description="自动生成的数值聚合指标草稿",
                )
            )
            semantic_aliases.append(
                SemanticAliasDefinition(
                    alias=metric_label,
                    target_type="metric",
                    target_key=metric_key,
                )
            )

    for dimension in semantic_dimensions:
        semantic_aliases.append(
            SemanticAliasDefinition(
                alias=dimension.label,
                target_type="dimension",
                target_key=dimension.key,
            )
        )

    deduped_aliases: list[SemanticAliasDefinition] = []
    seen_alias_pairs: set[tuple[str, str, str]] = set()
    for alias in semantic_aliases:
        alias_key = (alias.alias, alias.target_type, alias.target_key)
        if alias_key in seen_alias_pairs:
            continue
        seen_alias_pairs.add(alias_key)
        deduped_aliases.append(alias)

    semantic_relationships = _build_relationships(
        relationships,
        {entity.key for entity in semantic_entities},
    )

    catalog = ValidateRequest.parse(
        SemanticCatalog,
        {
            "catalog_version": f"draft-{date.today().isoformat()}",
            "dataset_id": dataset_id,
            "tables": [item.model_dump() for item in semantic_tables],
            "entities": [item.model_dump() for item in semantic_entities],
            "relationships": [item.model_dump() for item in semantic_relationships],
            "metrics": [item.model_dump() for item in semantic_metrics],
            "dimensions": [item.model_dump() for item in semantic_dimensions],
            "aliases": [item.model_dump() for item in deduped_aliases],
            "metric_versions": [],
        },
    )

    return SemanticDraftArtifact(
        catalog=catalog,
        value_mapping_hints=value_mappings,
        relationship_hints=relationships,
    )


def write_semantic_catalog_draft(
    *,
    store: MetadataStore,
    dataset_id: str,
    output_dir: str | Path | None = None,
) -> Path:
    # [CUSTOM] 草稿统一写到独立目录，避免运行时误读未审核的 catalog。
    draft = generate_semantic_catalog_draft(store=store, dataset_id=dataset_id)
    draft_dir = Path(output_dir) if output_dir is not None else DEFAULT_SEMANTIC_DRAFT_DIR
    draft_dir.mkdir(parents=True, exist_ok=True)
    output_path = draft_dir / f"{dataset_id}.json"
    output_path.write_text(
        json.dumps(draft.catalog.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path
