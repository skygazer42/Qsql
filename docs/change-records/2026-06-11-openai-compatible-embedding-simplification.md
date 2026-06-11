# 2026-06-11 OpenAI-Compatible Embedding 精简

## 改了什么

- 新增 `src/qsql/openai_compatible/embedding.py`
  - 提供统一 `OpenAI-compatible` embedding 函数，支持 `/embeddings` 调用、智能分块、语义召回与可选 rerank。
- 更新 `src/qsql/openai_compatible/__init__.py`
  - 导出 `OpenAICompatibleEmbeddingFunction`。
- 更新 `src/qsql/chromadb/chromadb_vector.py`
  - 默认 embedding 函数改为惰性初始化的 `OpenAICompatibleEmbeddingFunction`。
- 更新 `src/qsql/chromadb/vector_store_service.py`、`src/qsql/chromadb/hybrid_search.py`
  - 检索链路统一改用 `OpenAICompatibleEmbeddingFunction`。
  - rerank 调用名从 `rerank_with_xinference` 改为 `rerank_documents`。
- 更新 `src/knowledge/implementations/chroma.py`
  - 知识库向量化改为使用标准化的 OpenAI-compatible embedding 配置。
- 更新测试与文档
  - `tests/test_imports.py` 断言 `src.qsql.xinference` 已删除。
  - `tests/test_openai_compatible_provider.py` 增加 embedding 配置测试。
  - `tests/test_structured_embed.py`、`tests/test_retrieval_ab_compare.py` 切换到新 embedding 实现。
  - `README.md`、`.env`、`docs/API_USAGE_METADATA.md` 改为中性 embedding 表述。
- 删除 `src/qsql/xinference/`
  - 移除 `embedding.py`、`xinference.py` 与包导出。
- 更新 `pyproject.toml`
  - 移除 `xinference-client` 依赖与可选 extra。

## 为什么改

- 既然主 LLM 已经统一成 OpenAI-compatible，就没有必要继续保留 Xinference 专属 embedding 分支。
- embedding 继续保留供应商特化，会让环境变量、依赖和检索链路长期处于“双轨制”，维护成本没有意义。
- 统一到 `EMBEDDING_BASE_URL + EMBEDDING_MODEL + EMBEDDING_API_KEY` 后，部署和接入模型网关都会更直接。

## 涉及文件

- `src/qsql/openai_compatible/embedding.py`
- `src/qsql/openai_compatible/__init__.py`
- `src/qsql/chromadb/chromadb_vector.py`
- `src/qsql/chromadb/vector_store_service.py`
- `src/qsql/chromadb/hybrid_search.py`
- `src/knowledge/implementations/chroma.py`
- `tests/test_imports.py`
- `tests/test_openai_compatible_provider.py`
- `tests/test_structured_embed.py`
- `tests/test_retrieval_ab_compare.py`
- `README.md`
- `.env`
- `pyproject.toml`

## 如何验证

- `.venv/bin/python -m pytest tests/test_imports.py tests/test_openai_compatible_provider.py tests/test_vanna.py tests/test_semantic_query_pipeline.py -v`
- `ruff check src/qsql src/knowledge app.py tests/test_imports.py tests/test_openai_compatible_provider.py tests/test_vanna.py tests/test_semantic_query_pipeline.py tests/test_structured_embed.py`
- `python -m py_compile app.py src/qsql/openai_compatible/embedding.py src/qsql/openai_compatible/llm.py src/qsql/chromadb/chromadb_vector.py src/qsql/chromadb/vector_store_service.py src/qsql/chromadb/hybrid_search.py src/knowledge/implementations/chroma.py tests/test_imports.py tests/test_openai_compatible_provider.py tests/test_structured_embed.py`
