"""Semantic query orchestration service."""

from __future__ import annotations

import time
from pathlib import Path

from .schemas import SemanticParseResponse, SemanticQueryRequest, SemanticStageTimings
from .semantic_agent import SemanticQueryAgent
from .semantic_catalog import load_semantic_catalog
from .sql_builder import build_query_execution_plan


class SemanticQueryService:
    """Prepare dataset-scoped semantic queries into controlled SQL plans."""

    def __init__(
        self,
        semantic_base_dir: str | Path | None = None,
        parser=None,
        sql_builder=build_query_execution_plan,
        catalog_loader=load_semantic_catalog,
    ):
        self._semantic_base_dir = semantic_base_dir
        self._parser = parser
        self._sql_builder = sql_builder
        self._catalog_loader = catalog_loader

    @classmethod
    def from_model_config(
        cls,
        *,
        model_name: str,
        base_url: str,
        api_key: str,
        temperature: float,
        semantic_base_dir: str | Path | None = None,
    ) -> "SemanticQueryService":
        return cls(
            semantic_base_dir=semantic_base_dir,
            parser=SemanticQueryAgent(
                model_name=model_name,
                base_url=base_url,
                api_key=api_key,
                temperature=temperature,
            ),
        )

    def _get_parser(self):
        if self._parser is None:
            raise RuntimeError("SemanticQueryService 缺少语义解析器")
        return self._parser

    def prepare_query(self, request_model: SemanticQueryRequest) -> SemanticParseResponse:
        # [CUSTOM] 输出 catalog/agent/sql_builder 分阶段耗时，支撑路由级观测与排障。
        overall_started_at = time.perf_counter()

        catalog_started_at = time.perf_counter()
        catalog = self._catalog_loader(
            request_model.dataset_id, base_dir=self._semantic_base_dir
        )
        catalog_load_ms = int((time.perf_counter() - catalog_started_at) * 1000)

        semantic_started_at = time.perf_counter()
        semantic_query = self._get_parser().parse(
            request_model.question, catalog, history=request_model.history
        )
        semantic_agent_ms = int((time.perf_counter() - semantic_started_at) * 1000)

        if semantic_query.needs_clarification:
            return SemanticParseResponse(
                dataset_id=request_model.dataset_id,
                question=request_model.question,
                status="clarification",
                clarification_question=semantic_query.clarification_question
                or "请补充查询条件",
                semantic_query=semantic_query,
                execution_plan=None,
                timings=SemanticStageTimings(
                    catalog_load_ms=catalog_load_ms,
                    semantic_agent_ms=semantic_agent_ms,
                    sql_build_ms=0,
                    total_ms=int((time.perf_counter() - overall_started_at) * 1000),
                ),
            )

        if semantic_query.time_range is None:
            return SemanticParseResponse(
                dataset_id=request_model.dataset_id,
                question=request_model.question,
                status="clarification",
                clarification_question="请补充时间范围，例如今年、本月或具体起止日期。",
                semantic_query=semantic_query,
                execution_plan=None,
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
            timings=SemanticStageTimings(
                catalog_load_ms=catalog_load_ms,
                semantic_agent_ms=semantic_agent_ms,
                sql_build_ms=sql_build_ms,
                total_ms=int((time.perf_counter() - overall_started_at) * 1000),
            ),
        )
