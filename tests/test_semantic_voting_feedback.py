import json
from pathlib import Path

from src.qsql.schemas import SemanticQueryDraft, SemanticQueryRequest, SemanticTimeRange
from src.qsql.semantic_postprocessor import SemanticPostprocessor
from src.qsql.semantic_service import SemanticQueryService


def _write_catalog(tmp_path: Path, dataset_id: str = "sales") -> Path:
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
                        "key": "sales_order_wide",
                        "label": "销售订单宽表",
                        "physical_table": "sales_orders",
                        "default_time_dimension_key": "order_date",
                    }
                ],
                "entities": [],
                "relationships": [],
                "metrics": [
                    {
                        "key": "order_amount",
                        "label": "订单金额",
                        "table_key": "sales_order_wide",
                        "field": "amount",
                        "aggregation": "sum",
                        "supported_dimension_keys": ["city", "order_date"],
                        "default_time_dimension_key": "order_date",
                    },
                    {
                        "key": "order_count",
                        "label": "订单数",
                        "table_key": "sales_order_wide",
                        "field": "id",
                        "aggregation": "count",
                        "supported_dimension_keys": ["city", "order_date"],
                        "default_time_dimension_key": "order_date",
                    },
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
                "aliases": [],
                "metric_versions": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return semantic_dir


def _draft(
    *,
    metric_key: str = "order_amount",
    city: str | None = None,
) -> SemanticQueryDraft:
    filters = []
    if city is not None:
        filters.append({"dimension_key": "city", "operator": "eq", "value": city})
    return SemanticQueryDraft(
        analysis_type="summary",
        metric_key=metric_key,
        group_by_dimension_keys=[],
        filters=filters,
        time_range=SemanticTimeRange(
            dimension_key="order_date",
            start="2026-01-01",
            end="2026-01-31",
        ),
    )


class _CandidateParser:
    def __init__(self, candidates: list[SemanticQueryDraft]) -> None:
        self._candidates = candidates
        self.calls: list[dict] = []

    def parse_candidates(
        self,
        question,
        catalog,
        history=None,
        *,
        candidate_count: int,
        sampling_temperature: float | None,
    ):
        self.calls.append(
            {
                "question": question,
                "candidate_count": candidate_count,
                "sampling_temperature": sampling_temperature,
            }
        )
        return self._candidates[:candidate_count]


def test_service_factory_keeps_injected_postprocessor():
    postprocessor = SemanticPostprocessor(plugin_base_dir=Path("/missing"))

    service = SemanticQueryService.from_model_config(
        model_name="test-model",
        base_url="http://127.0.0.1:8000/v1",
        api_key="EMPTY",
        temperature=0.0,
        postprocessor=postprocessor,
    )

    assert service._postprocessor is postprocessor


def test_service_votes_for_majority_candidate(tmp_path: Path):
    semantic_dir = _write_catalog(tmp_path)
    parser = _CandidateParser(
        [
            _draft(metric_key="order_amount"),
            _draft(metric_key="order_count"),
            _draft(metric_key="order_amount"),
        ]
    )
    service = SemanticQueryService(
        semantic_base_dir=semantic_dir,
        parser=parser,
        candidate_count=3,
        candidate_sampling_temperature=0.9,
    )

    result = service.prepare_query(
        SemanticQueryRequest(dataset_id="sales", question="一月订单金额是多少")
    )

    assert result.status == "ready"
    assert result.execution_plan is not None
    assert result.execution_plan.metric_key == "order_amount"
    assert parser.calls == [
        {
            "question": "一月订单金额是多少",
            "candidate_count": 3,
            "sampling_temperature": 0.9,
        }
    ]


def test_service_feedback_retries_next_ready_candidate_when_primary_result_is_empty(
    tmp_path: Path,
):
    semantic_dir = _write_catalog(tmp_path)
    parser = _CandidateParser(
        [
            _draft(city="上海"),
            _draft(city="上海"),
            _draft(city="杭州"),
        ]
    )
    service = SemanticQueryService(
        semantic_base_dir=semantic_dir,
        parser=parser,
        candidate_count=3,
        feedback_retry_limit=1,
    )

    def _execute_plan(execution_plan):
        if "上海" in execution_plan.sql:
            return []
        return [{"metric_value": 1}]

    response, execution_result = service.prepare_query_with_feedback(
        SemanticQueryRequest(dataset_id="sales", question="一月上海订单金额是多少"),
        execute_plan=_execute_plan,
    )

    assert response.status == "ready"
    assert response.execution_plan is not None
    assert "杭州" in response.execution_plan.sql
    assert execution_result == [{"metric_value": 1}]


def test_service_feedback_turns_empty_results_into_clarification(tmp_path: Path):
    semantic_dir = _write_catalog(tmp_path)
    parser = _CandidateParser(
        [
            _draft(city="上海"),
            _draft(city="上海"),
            _draft(city="杭州"),
        ]
    )
    service = SemanticQueryService(
        semantic_base_dir=semantic_dir,
        parser=parser,
        candidate_count=3,
        feedback_retry_limit=1,
    )

    response, execution_result = service.prepare_query_with_feedback(
        SemanticQueryRequest(dataset_id="sales", question="一月订单金额是多少"),
        execute_plan=lambda execution_plan: [],
    )

    assert response.status == "clarification"
    assert response.execution_plan is None
    assert "结果为空" in (response.clarification_question or "")
    assert execution_result is None
