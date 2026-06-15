"""Generic semantic query postprocessing hooks."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .schemas import (
    SemanticCatalog,
    SemanticDimensionDefinition,
    SemanticFilter,
    SemanticMetricDefinition,
    SemanticQueryDraft,
    SemanticTimeRange,
)


DEFAULT_PLUGIN_DIR = Path(__file__).resolve().parents[2] / "resources" / "semantic_plugins"


class SemanticPostprocessor:
    """Repair model output with generic rules and dataset-scoped plugin hints."""

    def __init__(self, plugin_base_dir: str | Path | None = None):
        self._plugin_base_dir = (
            Path(plugin_base_dir) if plugin_base_dir is not None else DEFAULT_PLUGIN_DIR
        )

    @staticmethod
    def _metric_map(catalog: SemanticCatalog) -> dict[str, SemanticMetricDefinition]:
        return {metric.key: metric for metric in catalog.metrics}

    @staticmethod
    def _dimension_map(
        catalog: SemanticCatalog,
    ) -> dict[str, SemanticDimensionDefinition]:
        return {dimension.key: dimension for dimension in catalog.dimensions}

    @staticmethod
    def _has_filter(semantic_query: SemanticQueryDraft, dimension_key: str) -> bool:
        return any(
            filter_obj.dimension_key == dimension_key
            for filter_obj in semantic_query.filters
        )

    @staticmethod
    def _normalise_filter_operators(semantic_query: SemanticQueryDraft) -> None:
        for filter_obj in semantic_query.filters:
            raw_operator = filter_obj.operator.strip().lower()
            if raw_operator in {"=", "=="}:
                filter_obj.operator = "eq"
            elif raw_operator.startswith(">=") or ">=" in raw_operator:
                filter_obj.operator = "gte"
            elif raw_operator.startswith("<=") or "<=" in raw_operator:
                filter_obj.operator = "lte"
            elif raw_operator.startswith(">") or ">" in raw_operator:
                filter_obj.operator = "gte"
            elif raw_operator.startswith("<") or "<" in raw_operator:
                filter_obj.operator = "lte"

    @staticmethod
    def _repair_explicit_year(
        *,
        question: str,
        metric: SemanticMetricDefinition | None,
        semantic_query: SemanticQueryDraft,
    ) -> None:
        if semantic_query.time_range is not None or metric is None:
            return

        year_match = re.search(r"(?<!\d)((?:19|20)\d{2})\s*年?", question)
        if year_match is None or not metric.default_time_dimension_key:
            return

        year = year_match.group(1)
        semantic_query.time_range = SemanticTimeRange(
            dimension_key=metric.default_time_dimension_key,
            start=f"{year}-01-01",
            end=f"{year}-12-31",
        )

    @staticmethod
    def _repair_month_trend(
        *,
        question: str,
        metric: SemanticMetricDefinition | None,
        dimensions: dict[str, SemanticDimensionDefinition],
        semantic_query: SemanticQueryDraft,
    ) -> None:
        if semantic_query.analysis_type != "trend" or semantic_query.group_by_dimension_keys:
            return
        if metric is None or "月" not in question:
            return

        for dimension_key in metric.supported_dimension_keys:
            dimension = dimensions.get(dimension_key)
            if dimension is None or dimension.kind != "time":
                continue
            searchable_text = f"{dimension.key} {dimension.label} {dimension.field}".lower()
            if "month" in searchable_text or "月" in searchable_text:
                semantic_query.group_by_dimension_keys = [dimension.key]
                return

    @staticmethod
    def _dimension_terms(catalog: SemanticCatalog) -> dict[str, set[str]]:
        terms = {
            dimension.key: {dimension.key, dimension.label}
            for dimension in catalog.dimensions
        }
        for alias in catalog.aliases:
            if alias.target_type == "dimension" and alias.target_key in terms:
                terms[alias.target_key].add(alias.alias)
        return terms

    @staticmethod
    def _metric_terms(catalog: SemanticCatalog) -> dict[str, set[str]]:
        terms = {metric.key: {metric.key, metric.label} for metric in catalog.metrics}
        for alias in catalog.aliases:
            if alias.target_type == "metric" and alias.target_key in terms:
                terms[alias.target_key].add(alias.alias)
        return terms

    @staticmethod
    def _mark_multi_metric_questions(
        *,
        question: str,
        catalog: SemanticCatalog,
        semantic_query: SemanticQueryDraft,
    ) -> None:
        matched_metric_keys: set[str] = set()
        for metric_key, terms in SemanticPostprocessor._metric_terms(catalog).items():
            if any(term and term in question for term in terms):
                matched_metric_keys.add(metric_key)

        if len(matched_metric_keys) <= 1:
            return

        semantic_query.needs_clarification = True
        semantic_query.clarification_question = "当前一次只支持查询一个指标，请选择一个指标。"

    @staticmethod
    def _repair_explicit_group_by(
        *,
        question: str,
        catalog: SemanticCatalog,
        metric: SemanticMetricDefinition | None,
        semantic_query: SemanticQueryDraft,
    ) -> None:
        if semantic_query.group_by_dimension_keys or metric is None:
            return
        if semantic_query.analysis_type not in {"group_by", "trend"}:
            return

        dimension_terms = SemanticPostprocessor._dimension_terms(catalog)
        matched_dimension_keys: list[str] = []
        for dimension_key in metric.supported_dimension_keys:
            for term in dimension_terms.get(dimension_key, set()):
                if not term:
                    continue
                patterns = (
                    f"各{term}",
                    f"每个{term}",
                    f"按{term}",
                    f"分{term}",
                    f"每{term}",
                    f"和{term}",
                    f"及{term}",
                    f"、{term}",
                    f"{term}维度",
                    f"{term}排名",
                )
                if any(pattern in question for pattern in patterns):
                    matched_dimension_keys.append(dimension_key)
                    break

        if matched_dimension_keys:
            semantic_query.group_by_dimension_keys = matched_dimension_keys

    def _plugin_path(self, dataset_id: str) -> Path:
        return self._plugin_base_dir / f"{dataset_id}.json"

    def _load_plugin(self, dataset_id: str) -> dict[str, Any]:
        plugin_path = self._plugin_path(dataset_id)
        if not plugin_path.exists():
            return {}
        return json.loads(plugin_path.read_text(encoding="utf-8"))

    def _apply_value_mappings(
        self,
        *,
        question: str,
        dimensions: dict[str, SemanticDimensionDefinition],
        semantic_query: SemanticQueryDraft,
        plugin: dict[str, Any],
    ) -> None:
        for mapping in plugin.get("value_mappings", []):
            if not isinstance(mapping, dict):
                continue
            dimension_key = str(mapping.get("dimension_key", ""))
            if dimension_key not in dimensions:
                continue

            operator = str(mapping.get("operator") or "eq")
            terms = mapping.get("terms", {})
            if not isinstance(terms, dict):
                continue

            for filter_obj in semantic_query.filters:
                if filter_obj.dimension_key != dimension_key:
                    continue
                filter_value = str(filter_obj.value)
                if filter_value in terms:
                    filter_obj.value = terms[filter_value]

            if self._has_filter(semantic_query, dimension_key):
                continue

            for alias, value in terms.items():
                if str(alias) in question:
                    semantic_query.filters.append(
                        SemanticFilter(
                            dimension_key=dimension_key,
                            operator=operator,
                            value=value,
                        )
                    )
                    break

    def repair(
        self,
        *,
        question: str,
        catalog: SemanticCatalog,
        semantic_query: SemanticQueryDraft,
    ) -> SemanticQueryDraft:
        # [CUSTOM] 底座只做通用可解释修复；业务值映射通过 dataset plugin 注入。
        metrics = self._metric_map(catalog)
        dimensions = self._dimension_map(catalog)
        metric = metrics.get(semantic_query.metric_key)

        self._mark_multi_metric_questions(
            question=question,
            catalog=catalog,
            semantic_query=semantic_query,
        )
        self._repair_explicit_year(
            question=question,
            metric=metric,
            semantic_query=semantic_query,
        )
        self._repair_month_trend(
            question=question,
            metric=metric,
            dimensions=dimensions,
            semantic_query=semantic_query,
        )
        self._repair_explicit_group_by(
            question=question,
            catalog=catalog,
            metric=metric,
            semantic_query=semantic_query,
        )
        self._normalise_filter_operators(semantic_query)
        self._apply_value_mappings(
            question=question,
            dimensions=dimensions,
            semantic_query=semantic_query,
            plugin=self._load_plugin(catalog.dataset_id),
        )
        self._normalise_filter_operators(semantic_query)
        return semantic_query
