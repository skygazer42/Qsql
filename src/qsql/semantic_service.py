"""Semantic query orchestration service."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from .schemas import (
    SemanticCandidateSelection,
    SemanticCatalog,
    SemanticClarificationOption,
    SemanticParseResponse,
    SemanticQueryCandidate,
    SemanticQueryDraft,
    SemanticQueryRequest,
    SemanticStageTimings,
)
from .semantic_agent import SemanticQueryAgent
from .semantic_catalog import load_semantic_catalog
from .semantic_postprocessor import SemanticPostprocessor
from .sql_builder import build_query_execution_plan


class SemanticQueryService:
    """Prepare dataset-scoped semantic queries into controlled SQL plans."""

    def __init__(
        self,
        semantic_base_dir: str | Path | None = None,
        parser=None,
        sql_builder=build_query_execution_plan,
        catalog_loader=load_semantic_catalog,
        postprocessor: SemanticPostprocessor | None = None,
        candidate_count: int = 1,
        candidate_sampling_temperature: float | None = None,
        feedback_retry_limit: int = 0,
    ):
        self._semantic_base_dir = semantic_base_dir
        self._parser = parser
        self._sql_builder = sql_builder
        self._catalog_loader = catalog_loader
        self._postprocessor = postprocessor or SemanticPostprocessor()
        self._candidate_count = max(1, int(candidate_count))
        self._candidate_sampling_temperature = candidate_sampling_temperature
        self._feedback_retry_limit = max(0, int(feedback_retry_limit))

    @classmethod
    def from_model_config(
        cls,
        *,
        model_name: str,
        base_url: str,
        api_key: str,
        temperature: float,
        semantic_base_dir: str | Path | None = None,
        postprocessor: SemanticPostprocessor | None = None,
        candidate_count: int = 1,
        candidate_sampling_temperature: float | None = None,
        feedback_retry_limit: int = 0,
    ) -> "SemanticQueryService":
        return cls(
            semantic_base_dir=semantic_base_dir,
            parser=SemanticQueryAgent(
                model_name=model_name,
                base_url=base_url,
                api_key=api_key,
                temperature=temperature,
            ),
            postprocessor=postprocessor,
            candidate_count=candidate_count,
            candidate_sampling_temperature=candidate_sampling_temperature,
            feedback_retry_limit=feedback_retry_limit,
        )

    def _get_parser(self):
        if self._parser is None:
            raise RuntimeError("SemanticQueryService 缺少语义解析器")
        return self._parser

    def _parse_candidates(
        self,
        *,
        question: str,
        catalog: SemanticCatalog,
        history: list[str],
    ) -> list[SemanticQueryDraft]:
        parser = self._get_parser()
        if hasattr(parser, "parse_candidates"):
            return parser.parse_candidates(
                question,
                catalog,
                history=history,
                candidate_count=self._candidate_count,
                sampling_temperature=self._candidate_sampling_temperature,
            )
        return [parser.parse(question, catalog, history=history)]

    @staticmethod
    def _candidate_signature(semantic_query: SemanticQueryDraft) -> str:
        filters = [
            {
                "dimension_key": item.dimension_key,
                "operator": item.operator,
                "value": item.value,
            }
            for item in semantic_query.filters
        ]
        filters.sort(
            key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True)
        )
        payload = {
            "analysis_type": semantic_query.analysis_type,
            "metric_key": semantic_query.metric_key,
            "metric_keys": semantic_query.metric_keys,
            "group_by_dimension_keys": semantic_query.group_by_dimension_keys,
            "filters": filters,
            "time_range": (
                semantic_query.time_range.model_dump()
                if semantic_query.time_range is not None
                else None
            ),
            "metric_version_key": semantic_query.metric_version_key,
            "order_by_metric": semantic_query.order_by_metric,
            "limit": semantic_query.limit,
            "needs_clarification": semantic_query.needs_clarification,
            "clarification_question": semantic_query.clarification_question,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def _select_candidates(
        self,
        semantic_queries: list[SemanticQueryDraft],
    ) -> SemanticCandidateSelection:
        signature_counts: dict[str, int] = {}
        first_candidates: dict[str, SemanticQueryCandidate] = {}
        for index, semantic_query in enumerate(semantic_queries):
            signature = self._candidate_signature(semantic_query)
            signature_counts[signature] = signature_counts.get(signature, 0) + 1
            first_candidates.setdefault(
                signature,
                SemanticQueryCandidate(
                    index=index,
                    semantic_query=semantic_query,
                    signature=signature,
                    vote_count=1,
                ),
            )

        candidates = [
            SemanticQueryCandidate(
                index=item.index,
                semantic_query=item.semantic_query,
                signature=item.signature,
                vote_count=signature_counts[item.signature],
            )
            for item in first_candidates.values()
        ]
        candidates.sort(key=lambda item: (-item.vote_count, item.index))
        selected_index = candidates[0].index if candidates else 0
        return SemanticCandidateSelection(
            candidates=candidates,
            selected_index=selected_index,
        )

    def _candidate_selection_for_index(
        self,
        selection: SemanticCandidateSelection,
        selected_index: int,
    ) -> SemanticCandidateSelection:
        return SemanticCandidateSelection(
            candidates=selection.candidates,
            selected_index=selected_index,
        )

    @staticmethod
    def _metric_terms(catalog: SemanticCatalog) -> dict[str, set[str]]:
        terms = {metric.key: {metric.key, metric.label} for metric in catalog.metrics}
        for alias in catalog.aliases:
            if alias.target_type == "metric" and alias.target_key in terms:
                terms[alias.target_key].add(alias.alias)
        return terms

    @staticmethod
    def _metric_clarification_options(
        *,
        question: str,
        catalog: SemanticCatalog,
    ) -> list[SemanticClarificationOption]:
        # [CUSTOM] 多指标澄清只认强指标词，避免 accounts/clients 这类实体名把问题误判成多指标。
        matched_metric_keys = SemanticPostprocessor.matched_metric_keys(
            question, catalog
        )
        if len(matched_metric_keys) <= 1:
            return []

        return [
            SemanticClarificationOption(
                target_type="metric",
                key=metric.key,
                label=metric.label,
                value={"metric_key": metric.key},
            )
            for metric in catalog.metrics
            if metric.key in matched_metric_keys
        ]

    @staticmethod
    def _time_range_clarification_options(
        *,
        catalog: SemanticCatalog,
        semantic_query: SemanticQueryDraft,
    ) -> list[SemanticClarificationOption]:
        metric = next(
            (
                item
                for item in catalog.metrics
                if item.key == semantic_query.metric_key
            ),
            None,
        )
        dimension_key = metric.default_time_dimension_key if metric else None
        if not dimension_key:
            return []

        return [
            SemanticClarificationOption(
                target_type="time_range",
                key="current_year",
                label="今年",
                value={"preset": "current_year", "dimension_key": dimension_key},
            ),
            SemanticClarificationOption(
                target_type="time_range",
                key="current_month",
                label="本月",
                value={"preset": "current_month", "dimension_key": dimension_key},
            ),
            SemanticClarificationOption(
                target_type="time_range",
                key="custom_range",
                label="自定义时间范围",
                value={"preset": "custom_range", "dimension_key": dimension_key},
            ),
        ]

    @staticmethod
    def _metric_requires_time_range(
        *,
        catalog: SemanticCatalog,
        semantic_query: SemanticQueryDraft,
    ) -> bool:
        metric = next(
            (
                item
                for item in catalog.metrics
                if item.key == semantic_query.metric_key
            ),
            None,
        )
        return bool(metric and metric.default_time_dimension_key)

    def _load_catalog_and_select_candidate(
        self,
        *,
        request_model: SemanticQueryRequest,
        overall_started_at: float,
    ) -> tuple[
        SemanticCatalog,
        SemanticCandidateSelection,
        int,
        int,
        int,
    ]:
        catalog_started_at = time.perf_counter()
        catalog = self._catalog_loader(
            request_model.dataset_id, base_dir=self._semantic_base_dir
        )
        catalog_load_ms = int((time.perf_counter() - catalog_started_at) * 1000)

        semantic_started_at = time.perf_counter()
        semantic_queries = self._parse_candidates(
            question=request_model.question,
            catalog=catalog,
            history=request_model.history,
        )
        semantic_queries = [
            self._postprocessor.repair(
                question=request_model.question,
                catalog=catalog,
                semantic_query=semantic_query,
            )
            for semantic_query in semantic_queries
        ]
        selection = self._select_candidates(semantic_queries)
        semantic_agent_ms = int((time.perf_counter() - semantic_started_at) * 1000)
        total_ms = int((time.perf_counter() - overall_started_at) * 1000)
        return catalog, selection, catalog_load_ms, semantic_agent_ms, total_ms

    def _build_response_for_candidate(
        self,
        *,
        request_model: SemanticQueryRequest,
        catalog: SemanticCatalog,
        candidate: SemanticQueryCandidate,
        selection: SemanticCandidateSelection,
        catalog_load_ms: int,
        semantic_agent_ms: int,
        overall_started_at: float,
    ) -> SemanticParseResponse:
        semantic_query = candidate.semantic_query
        selected_selection = self._candidate_selection_for_index(
            selection,
            candidate.index,
        )

        if semantic_query.needs_clarification:
            return SemanticParseResponse(
                dataset_id=request_model.dataset_id,
                question=request_model.question,
                status="clarification",
                clarification_question=semantic_query.clarification_question
                or "请补充查询条件",
                clarification_options=self._metric_clarification_options(
                    question=request_model.question,
                    catalog=catalog,
                ),
                semantic_query=semantic_query,
                execution_plan=None,
                candidate_selection=selected_selection,
                timings=SemanticStageTimings(
                    catalog_load_ms=catalog_load_ms,
                    semantic_agent_ms=semantic_agent_ms,
                    sql_build_ms=0,
                    total_ms=int((time.perf_counter() - overall_started_at) * 1000),
                ),
            )

        if (
            semantic_query.time_range is None
            and self._metric_requires_time_range(
                catalog=catalog,
                semantic_query=semantic_query,
            )
        ):
            return SemanticParseResponse(
                dataset_id=request_model.dataset_id,
                question=request_model.question,
                status="clarification",
                clarification_question="请补充时间范围，例如今年、本月或具体起止日期。",
                clarification_options=self._time_range_clarification_options(
                    catalog=catalog,
                    semantic_query=semantic_query,
                ),
                semantic_query=semantic_query,
                execution_plan=None,
                candidate_selection=selected_selection,
                timings=SemanticStageTimings(
                    catalog_load_ms=catalog_load_ms,
                    semantic_agent_ms=semantic_agent_ms,
                    sql_build_ms=0,
                    total_ms=int((time.perf_counter() - overall_started_at) * 1000),
                ),
            )

        sql_build_started_at = time.perf_counter()
        execution_plan = self._sql_builder(
            catalog=catalog,
            semantic_query=semantic_query,
        )
        sql_build_ms = int((time.perf_counter() - sql_build_started_at) * 1000)
        return SemanticParseResponse(
            dataset_id=request_model.dataset_id,
            question=request_model.question,
            status="ready",
            clarification_question=None,
            semantic_query=semantic_query,
            execution_plan=execution_plan,
            candidate_selection=selected_selection,
            timings=SemanticStageTimings(
                catalog_load_ms=catalog_load_ms,
                semantic_agent_ms=semantic_agent_ms,
                sql_build_ms=sql_build_ms,
                total_ms=int((time.perf_counter() - overall_started_at) * 1000),
            ),
        )

    def prepare_query(self, request_model: SemanticQueryRequest) -> SemanticParseResponse:
        # [CUSTOM] 输出 catalog/agent/sql_builder 分阶段耗时，支撑路由级观测与排障。
        overall_started_at = time.perf_counter()

        catalog, selection, catalog_load_ms, semantic_agent_ms, _ = (
            self._load_catalog_and_select_candidate(
                request_model=request_model,
                overall_started_at=overall_started_at,
            )
        )

        return self._build_response_for_candidate(
            request_model=request_model,
            catalog=catalog,
            candidate=selection.candidates[0],
            selection=selection,
            catalog_load_ms=catalog_load_ms,
            semantic_agent_ms=semantic_agent_ms,
            overall_started_at=overall_started_at,
        )

    @staticmethod
    def _has_rows(execution_result: Any) -> bool:
        if execution_result is None:
            return False
        if hasattr(execution_result, "empty"):
            return not bool(execution_result.empty)
        try:
            return len(execution_result) > 0
        except TypeError:
            return True

    def _empty_result_response(
        self,
        *,
        request_model: SemanticQueryRequest,
        semantic_query: SemanticQueryDraft | None,
        selection: SemanticCandidateSelection,
        catalog_load_ms: int,
        semantic_agent_ms: int,
        overall_started_at: float,
    ) -> SemanticParseResponse:
        return SemanticParseResponse(
            dataset_id=request_model.dataset_id,
            question=request_model.question,
            status="clarification",
            clarification_question="查询结果为空，请补充或调整过滤条件。",
            semantic_query=semantic_query,
            execution_plan=None,
            candidate_selection=selection,
            timings=SemanticStageTimings(
                catalog_load_ms=catalog_load_ms,
                semantic_agent_ms=semantic_agent_ms,
                sql_build_ms=0,
                total_ms=int((time.perf_counter() - overall_started_at) * 1000),
            ),
        )

    def prepare_query_with_feedback(
        self,
        request_model: SemanticQueryRequest,
        *,
        execute_plan: Callable[[Any], Any],
    ) -> tuple[SemanticParseResponse, Any | None]:
        # [CUSTOM] 执行反馈只在 draft 候选之间切换，不把 SQL 错误交回 LLM 自由修复。
        overall_started_at = time.perf_counter()
        catalog, selection, catalog_load_ms, semantic_agent_ms, _ = (
            self._load_catalog_and_select_candidate(
                request_model=request_model,
                overall_started_at=overall_started_at,
            )
        )

        attempts = 0
        last_response: SemanticParseResponse | None = None
        max_attempts = 1 + self._feedback_retry_limit
        for candidate in selection.candidates:
            if attempts >= max_attempts:
                break
            response = self._build_response_for_candidate(
                request_model=request_model,
                catalog=catalog,
                candidate=candidate,
                selection=selection,
                catalog_load_ms=catalog_load_ms,
                semantic_agent_ms=semantic_agent_ms,
                overall_started_at=overall_started_at,
            )
            last_response = response
            if response.status != "ready" or response.execution_plan is None:
                return response, None

            attempts += 1
            execution_result = execute_plan(response.execution_plan)
            if self._has_rows(execution_result):
                return response, execution_result

        return (
            self._empty_result_response(
                request_model=request_model,
                semantic_query=last_response.semantic_query if last_response else None,
                selection=selection,
                catalog_load_ms=catalog_load_ms,
                semantic_agent_ms=semantic_agent_ms,
                overall_started_at=overall_started_at,
            ),
            None,
        )
