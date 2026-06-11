# 2026-06-11 OpenAI-Compatible 运行时命名中性化

## 改了什么

- 新增 `src/qsql/openai_compatible/`
  - `src/qsql/openai_compatible/llm.py`
  - `src/qsql/openai_compatible/__init__.py`
- 将运行时 LLM 类名从 `Vllm` 改为 `OpenAICompatibleLLM`
- 将本地组合类名从 `LocalContext_VLLM` 改为 `LocalContext_OpenAICompatible`
- 删除 `src/qsql/vllm/`
- 更新 `app.py`、`src/qsql/local.py`、`README.md`
- 更新测试：
  - `tests/test_imports.py`
  - `tests/test_openai_compatible_provider.py`
  - `tests/test_vanna.py`

## 为什么改

- 仓库已经不再围绕单一 `vllm` 供应商建模，而是统一为 OpenAI-compatible 协议。
- 继续保留 `Vllm` / `LocalContext_VLLM` 这类命名，会让代码语义和当前架构不一致。
- 本次直接改名并删除旧包，不保留兼容别名，避免历史命名继续滞留。

## 如何验证

- `.venv/bin/python -m pytest tests/test_imports.py tests/test_openai_compatible_provider.py tests/test_vanna.py tests/test_semantic_query_pipeline.py -v`
- `ruff check app.py src/qsql/local.py src/qsql/openai/openai_compatible.py src/qsql/openai/openai_chat.py src/qsql/openai/openai_embeddings.py src/qsql/openai_compatible/llm.py src/qsql/openai_compatible/__init__.py src/qsql/chromadb/chromadb_vector.py src/qsql/chromadb/__init__.py src/qsql/chromadb/vector_store_service.py src/qsql/chromadb/vectorize_helpers.py src/qsql/schemas.py src/qsql/semantic_agent.py src/qsql/semantic_catalog.py src/qsql/semantic_service.py src/qsql/sql_builder.py src/qsql/sql_output_refiner.py src/server/semantic_query_api.py tests/test_imports.py tests/test_openai_compatible_provider.py tests/test_vanna.py tests/test_semantic_query_pipeline.py tests/test_structured_embed.py`
- `python -m py_compile app.py src/qsql/local.py src/qsql/openai/openai_compatible.py src/qsql/openai/openai_chat.py src/qsql/openai/openai_embeddings.py src/qsql/openai_compatible/llm.py src/qsql/openai_compatible/__init__.py src/qsql/chromadb/chromadb_vector.py src/qsql/chromadb/__init__.py src/qsql/chromadb/vector_store_service.py src/qsql/chromadb/vectorize_helpers.py src/qsql/schemas.py src/qsql/semantic_agent.py src/qsql/semantic_catalog.py src/qsql/semantic_service.py src/qsql/sql_builder.py src/qsql/sql_output_refiner.py src/server/semantic_query_api.py tests/test_imports.py tests/test_openai_compatible_provider.py tests/test_vanna.py tests/test_semantic_query_pipeline.py tests/test_structured_embed.py`
