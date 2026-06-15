# 2026-06-15 value retrieval P1-1

## 改了什么

- 新增 `SemanticValueCandidate`，用 Pydantic 定义值召回候选输出。
- 新增 `MetadataValueRetriever`，从 metadata store 的 `value_mapping` 和 schema sample values 召回真实过滤值。
- `SemanticPostprocessor` 接入可插拔 value retriever，在 plugin 映射之后自动补全或校正 `SemanticFilter`。
- `/api/v0` 默认语义服务挂接 `MetadataValueRetriever(get_metadata_store())`。

## 为什么改

- 减少对人工 `resources/semantic_plugins/*.json` 的依赖。
- 保持通用底座能力：业务特殊词仍通过 metadata value mapping、样例值或插件外挂，不写死进代码。
- 为后续 BM25/向量列值索引预留稳定的 Pydantic 候选契约。

## 涉及文件

- `src/qsql/schemas.py`
- `src/qsql/value_retriever.py`
- `src/qsql/semantic_postprocessor.py`
- `src/qsql/semantic_service.py`
- `app.py`
- `tests/test_semantic_postprocessor.py`
- `tests/test_value_retriever.py`
- `tests/test_semantic_voting_feedback.py`
- `docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md`

## 如何验证

- `.venv/bin/python -m pytest tests/test_semantic_postprocessor.py::test_postprocessor_uses_value_retriever_when_plugin_is_missing tests/test_value_retriever.py -q`
- `.venv/bin/python -m pytest tests/test_semantic_voting_feedback.py::test_service_factory_keeps_injected_postprocessor -q`
- `ruff check src/ app.py scripts tests test_search_algorithm.py`
- `.venv/bin/python -m pytest tests/`
