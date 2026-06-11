# 2026-06-11 数据集语义查询链路

## 改了什么

- `src/qsql/schemas.py`
  - 新增语义目录、语义草稿、执行计划、语义查询请求/响应模型。
- `src/qsql/semantic_catalog.py`
  - 新增按 `dataset_id` 加载 `resources/semantic/<dataset_id>.json` 的目录加载器。
  - 新增语义目录摘要与列表能力，支持数据集发现与健康检查。
- `src/qsql/semantic_agent.py`
  - 新增 `pydantic-ai` 语义解析器，只输出 `SemanticQueryDraft`，不直接输出 SQL。
- `src/qsql/sql_builder.py`
  - 新增受控 SQL 构造器，根据指标/维度/时间范围/口径确定性生成只读 SQL。
- `src/qsql/semantic_service.py`
  - 新增语义服务，负责目录加载、语义解析、澄清判断、SQL 计划生成。
- `src/server/semantic_query_api.py`
  - 新增 `/api/v1/query/semantic/parse` 与 `/api/v1/query/semantic/run` 蓝图。
  - 新增 `/api/v1/query/semantic/catalogs` 与 `/api/v1/query/semantic/catalog/validate` 目录观测接口。
- `app.py`
  - 注册新的语义查询蓝图，不改旧 `/api/v0/*` 主链路。
- `resources/semantic/README.md`
  - 补充语义目录格式示例。
- `resources/semantic/sales.json`
  - 新增仓库内置 `sales` 示例目录，便于新链路直接联调。
- `tests/test_semantic_query_pipeline.py`
  - 新增最小测试，覆盖目录加载、执行计划生成、语义服务、蓝图响应与目录校验接口。

## 为什么改

- 当前旧链路仍然是 prompt -> SQL -> 提取 -> 执行。
- 本次先并行落一条“模型产语义、后端控 SQL”的新链路，避免一次性替换旧问答流。
- 语义目录以 `dataset_id` 为作用域，适配当前项目已有的数据集与向量检索结构。
- 增加目录列表与校验接口后，前端和运维可以先核对“接了哪些数据集、目录是否合法”，再进入真实问答链路。

## 如何验证

- `.venv/bin/python -m pytest tests/test_semantic_query_pipeline.py`
- `ruff check app.py src/qsql/schemas.py src/qsql/semantic_catalog.py src/qsql/semantic_agent.py src/qsql/semantic_service.py src/qsql/sql_builder.py src/server/semantic_query_api.py tests/test_semantic_query_pipeline.py`
- `python -m py_compile app.py src/qsql/schemas.py src/qsql/semantic_catalog.py src/qsql/semantic_agent.py src/qsql/semantic_service.py src/qsql/sql_builder.py src/server/semantic_query_api.py`
