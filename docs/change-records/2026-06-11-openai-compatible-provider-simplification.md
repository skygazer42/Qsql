# 2026-06-11 OpenAI-Compatible Provider 精简

## 改了什么

- 新增 `src/qsql/openai/openai_compatible.py`
  - 提供统一 `OpenAI-compatible` 聊天 provider，支持 `base_url + api_key + model`。
- 重写 `src/qsql/openai/openai_chat.py`
  - `OpenAI_Chat` 改为兼容旧类名的薄包装，底层统一走 `OpenAICompatibleChat`。
- 新增 `src/qsql/openai_compatible/llm.py`
  - `OpenAICompatibleLLM` 作为统一运行时 LLM，负责 SQL 提取与诊断日志。
- 更新 `src/qsql/openai/openai_embeddings.py`
  - 支持 `base_url`，嵌入接口也走 OpenAI-compatible SDK。
- 更新 `src/qsql/chromadb/chromadb_vector.py` 与 `src/qsql/chromadb/__init__.py`
  - 嵌入函数改为惰性初始化，避免模块导入时强依赖 embedding 环境变量。
- 删除未使用多供应商实现
  - 删除 `anthropic / azuresearch / bedrock / cohere / deepseek / faiss / google / hf / marqo / milvus / mistral / ollama / opensearch / oracle / pgvector / pinecone / qdrant / qianfan / qianwen / vannadb / weaviate / ZhipuAI / advanced / remote.py`
- 更新测试
  - `tests/test_imports.py` 只保留当前支持面的导入校验，并断言旧 provider 已被移除。
  - `tests/test_openai_compatible_provider.py` 校验统一 provider 与 `OpenAICompatibleLLM` 运行时配置。
  - `tests/test_vanna.py` 替换为当前运行时 mixin smoke test。
- 更新 `README.md` 与 `pyproject.toml`
  - README 明确这是 OpenAI-compatible 精简分支。
  - 删除已移除 provider 的可选依赖声明。

## 为什么改

- 当前项目运行时只使用 OpenAI-compatible LLM/Embedding 协议、ChromaDB 与业务语义链路。
- 上游保留的大量 provider 在这个仓库里没有真实使用场景，只会增加维护面、导入副作用和依赖噪音。
- `vLLM` 本身就是 OpenAI-compatible 协议，没有必要继续维护一套单独的 HTTP 调用分支。

## 涉及文件

- `src/qsql/openai/openai_compatible.py`
- `src/qsql/openai/openai_chat.py`
- `src/qsql/openai/openai_embeddings.py`
- `src/qsql/openai_compatible/llm.py`
- `src/qsql/chromadb/chromadb_vector.py`
- `src/qsql/chromadb/__init__.py`
- `tests/test_imports.py`
- `tests/test_openai_compatible_provider.py`
- `tests/test_vanna.py`
- `README.md`
- `pyproject.toml`

## 如何验证

- `.venv/bin/python -m pytest tests/test_imports.py tests/test_openai_compatible_provider.py tests/test_vanna.py tests/test_semantic_query_pipeline.py`
- `ruff check src/qsql app.py tests/test_imports.py tests/test_openai_compatible_provider.py tests/test_vanna.py tests/test_semantic_query_pipeline.py`
- `python -m py_compile app.py src/qsql/local.py src/qsql/openai/openai_compatible.py src/qsql/openai/openai_chat.py src/qsql/openai/openai_embeddings.py src/qsql/vllm/vllm.py src/qsql/chromadb/chromadb_vector.py src/qsql/chromadb/__init__.py src/qsql/schemas.py src/qsql/semantic_catalog.py src/qsql/semantic_service.py src/qsql/sql_builder.py src/server/semantic_query_api.py`
