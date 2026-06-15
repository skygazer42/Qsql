"""Dataset-scoped semantic value retrieval."""

from __future__ import annotations

import json
from typing import Any

from .metadata_store import MetadataStore
from .schemas import (
    SemanticCatalog,
    SemanticDimensionDefinition,
    SemanticValueCandidate,
)


class MetadataValueRetriever:
    """Retrieve dimension value candidates from metadata store records."""

    def __init__(self, store: MetadataStore):
        self._store = store

    @staticmethod
    def _dimension_by_physical_column(
        catalog: SemanticCatalog,
        dimensions: dict[str, SemanticDimensionDefinition],
    ) -> dict[tuple[str, str], SemanticDimensionDefinition]:
        table_map = {table.key: table.physical_table for table in catalog.tables}
        result: dict[tuple[str, str], SemanticDimensionDefinition] = {}
        for dimension in dimensions.values():
            physical_table = table_map.get(dimension.table_key)
            if physical_table is None:
                continue
            result[(physical_table, dimension.field)] = dimension
        return result

    @staticmethod
    def _sample_values(column: dict[str, Any]) -> list[str]:
        raw_value = column.get("sample_values_json")
        if not raw_value:
            return []
        try:
            parsed = json.loads(str(raw_value))
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [str(item) for item in parsed if item is not None]

    def retrieve(
        self,
        *,
        question: str,
        catalog: SemanticCatalog,
        dimensions: dict[str, SemanticDimensionDefinition],
    ) -> list[SemanticValueCandidate]:
        # [CUSTOM] 先用 metadata 中的人工映射和样例值做轻量 value retrieval；
        # 后续可在同一 Pydantic 输出契约下替换为 BM25/向量值索引。
        dimension_by_column = self._dimension_by_physical_column(catalog, dimensions)
        candidates: list[SemanticValueCandidate] = []

        for mapping in self._store.list_value_mappings(catalog.dataset_id):
            if int(mapping.get("enabled") or 0) != 1:
                continue
            dimension = dimension_by_column.get(
                (str(mapping["table_name"]), str(mapping["column_name"]))
            )
            if dimension is None:
                continue
            nl_term = str(mapping["nl_term"])
            db_value = mapping["db_value"]
            if nl_term not in question and str(db_value) not in question:
                continue
            candidates.append(
                SemanticValueCandidate(
                    dataset_id=catalog.dataset_id,
                    dimension_key=dimension.key,
                    nl_term=nl_term,
                    db_value=db_value,
                    operator=str(mapping.get("match_mode") or "eq"),
                    score=1.0,
                    source=mapping.get("source") or "metadata_mapping",
                )
            )

        for column in self._store.list_schema_columns(catalog.dataset_id):
            dimension = dimension_by_column.get(
                (str(column["table_name"]), str(column["column_name"]))
            )
            if dimension is None:
                continue
            for value in self._sample_values(column):
                if value not in question:
                    continue
                candidates.append(
                    SemanticValueCandidate(
                        dataset_id=catalog.dataset_id,
                        dimension_key=dimension.key,
                        nl_term=value,
                        db_value=value,
                        operator="eq",
                        score=0.8,
                        source="metadata_sample",
                    )
                )

        candidates.sort(key=lambda item: (-item.score, item.dimension_key, item.nl_term))
        return candidates
