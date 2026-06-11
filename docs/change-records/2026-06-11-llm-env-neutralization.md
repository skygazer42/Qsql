# 2026-06-11 LLM 环境变量中性化

## 改了什么

- 将应用主配置从 `VLLM_*` 改为中性命名的 `LLM_*`
  - `VLLM_HOST` -> `LLM_BASE_URL`
  - `VLLM_MODEL` -> `LLM_MODEL`
  - `VLLM_AUTH_KEY` -> `LLM_API_KEY`
  - `VLLM_TEMPERATURE` -> `LLM_TEMPERATURE`
- 更新 `src/qsql/schemas.py`
  - `AppConfigModel` 改为 `llm_base_url` / `llm_api_key`
- 更新 `app.py`
  - 启动配置、SQL 输出规整器、语义解析服务统一读取 `LLM_*`
- 更新 `src/qsql/vllm/vllm.py`
  - 不再接受 `vllm_host/auth-key` 配置，只接受 `base_url/api_key`
- 更新 `src/qsql/semantic_agent.py`
- 更新 `src/qsql/semantic_service.py`
- 更新 `src/qsql/sql_output_refiner.py`
  - 统一使用 `base_url/api_key` 参数名
- 更新 `src/qsql/chromadb/vectorize_helpers.py`
  - `build_vllm_request_context` 改为 `build_llm_request_context`
- 更新 `src/qsql/chromadb/vector_store_service.py`
  - LLM 描述生成链路统一读取 `LLM_*`
- 更新 `.env`、`README.md`、`tests/test_structured_embed.py`

## 为什么改

- 现在仓库已经收口为 OpenAI-compatible LLM 接口，不再需要沿用 `VLLM_*` 这种绑定单个供应商的命名。
- 中性配置名更符合当前架构，也便于后续切换到任何 OpenAI-compatible 服务端。
- 本次不保留双命名并存，避免配置层继续积累 fallback 和历史包袱。

## 如何验证

- `.venv/bin/python -m pytest tests/test_imports.py tests/test_openai_compatible_provider.py tests/test_vanna.py tests/test_semantic_query_pipeline.py -v`
- `ruff check app.py src/qsql/local.py src/qsql/openai/openai_compatible.py src/qsql/openai/openai_chat.py src/qsql/openai/openai_embeddings.py src/qsql/vllm/vllm.py src/qsql/chromadb/chromadb_vector.py src/qsql/chromadb/__init__.py src/qsql/chromadb/vector_store_service.py src/qsql/chromadb/vectorize_helpers.py src/qsql/schemas.py src/qsql/semantic_agent.py src/qsql/semantic_catalog.py src/qsql/semantic_service.py src/qsql/sql_builder.py src/qsql/sql_output_refiner.py src/server/semantic_query_api.py tests/test_imports.py tests/test_openai_compatible_provider.py tests/test_vanna.py tests/test_semantic_query_pipeline.py tests/test_structured_embed.py`
- `python -m py_compile app.py src/qsql/local.py src/qsql/openai/openai_compatible.py src/qsql/openai/openai_chat.py src/qsql/openai/openai_embeddings.py src/qsql/vllm/vllm.py src/qsql/chromadb/chromadb_vector.py src/qsql/chromadb/__init__.py src/qsql/chromadb/vector_store_service.py src/qsql/chromadb/vectorize_helpers.py src/qsql/schemas.py src/qsql/semantic_agent.py src/qsql/semantic_catalog.py src/qsql/semantic_service.py src/qsql/sql_builder.py src/qsql/sql_output_refiner.py src/server/semantic_query_api.py tests/test_imports.py tests/test_openai_compatible_provider.py tests/test_vanna.py tests/test_semantic_query_pipeline.py tests/test_structured_embed.py`
