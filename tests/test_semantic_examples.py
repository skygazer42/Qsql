import json
from pathlib import Path

from src.qsql.schemas import SemanticCatalog, SemanticQueryDraft, ValidateRequest
from src.qsql.semantic_agent import SemanticQueryAgent
from src.qsql.semantic_examples import FileSemanticExampleRetriever


def _catalog() -> SemanticCatalog:
    return ValidateRequest.parse(
        SemanticCatalog,
        {
            "catalog_version": "2026-06-15",
            "dataset_id": "sales",
            "tables": [
                {
                    "key": "sales_order_wide",
                    "label": "销售订单宽表",
                    "physical_table": "sales_orders",
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
                }
            ],
            "dimensions": [
                {
                    "key": "city",
                    "label": "城市",
                    "table_key": "sales_order_wide",
                    "field": "city_name",
                    "kind": "categorical",
                    "operators": ["eq"],
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
    )


def _write_examples(base_dir: Path) -> Path:
    example_dir = base_dir / "semantic_examples"
    example_dir.mkdir()
    (example_dir / "sales.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "question": "2026年各城市订单金额是多少？",
                        "semantic_query": {
                            "analysis_type": "group_by",
                            "metric_key": "order_amount",
                            "group_by_dimension_keys": ["city"],
                            "filters": [],
                            "time_range": {
                                "dimension_key": "order_date",
                                "start": "2026-01-01",
                                "end": "2026-12-31",
                            },
                        },
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "question": "2026年订单金额是多少？",
                        "semantic_query": {
                            "analysis_type": "summary",
                            "metric_key": "order_amount",
                            "group_by_dimension_keys": [],
                            "filters": [],
                            "time_range": {
                                "dimension_key": "order_date",
                                "start": "2026-01-01",
                                "end": "2026-12-31",
                            },
                        },
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return example_dir


def test_file_semantic_example_retriever_returns_ranked_draft_examples(tmp_path: Path):
    example_dir = _write_examples(tmp_path)
    retriever = FileSemanticExampleRetriever(base_dir=example_dir)

    matches = retriever.retrieve(
        dataset_id="sales",
        question="今年每个城市的订单金额",
        top_k=1,
    )

    assert len(matches) == 1
    assert matches[0].example.question == "2026年各城市订单金额是多少？"
    assert isinstance(matches[0].example.semantic_query, SemanticQueryDraft)
    assert matches[0].example.semantic_query.group_by_dimension_keys == ["city"]


def test_semantic_agent_examples_prompt_includes_retrieved_draft(tmp_path: Path):
    example_dir = _write_examples(tmp_path)
    agent = SemanticQueryAgent.__new__(SemanticQueryAgent)
    agent._example_retriever = FileSemanticExampleRetriever(base_dir=example_dir)
    agent._example_top_k = 2

    prompt = agent._examples_prompt(
        question="今年每个城市的订单金额",
        catalog=_catalog(),
    )

    assert "相似成功示例" in prompt
    assert "2026年各城市订单金额是多少？" in prompt
    assert '"metric_key":"order_amount"' in prompt
    assert '"group_by_dimension_keys":["city"]' in prompt
