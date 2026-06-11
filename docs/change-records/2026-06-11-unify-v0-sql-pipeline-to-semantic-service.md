# 2026-06-11 收口 `/api/v0/*` 到语义控 SQL 主链路

## 改了什么

- 老主接口 `/api/v0/generate_sql` 与 `/api/v0/search` 不再调用 `vn.generate_sql()` 裸生成 SQL。
- `app.py` 改为直接调用 `SemanticQueryService.prepare_query()`，并使用 `sql_builder` 产出的 `QueryExecutionPlan.sql`。
- `GenerateSQLRequest` 与 `SearchRequest` 增加 `dataset_id`；`SearchRequest` 增加 `history`。
- `SQLExecutionPayload` 新增：
  - `dataset_id`
  - `execution_plan`
  - `from_execution_plan(...)`
- 取消注册并删除独立 `/api/v1/query/semantic/*` 路由实现：
  - `src/server/semantic_query_api.py`
- 更新 README、语义目录说明与测试：
  - 新增老接口直走语义服务的应用级测试
  - 删除独立语义蓝图测试

## 为什么改

- 当前项目目标是直接用 `pydantic + pydantic-ai` 改造老链路，而不是保留“旧链路 + 新链路”并行。
- 并行两套路由会造成：
  - 主入口仍然停留在模型裸 SQL 生成
  - 语义控 SQL 只作为旁路能力存在
  - 项目边界和最终主链路不清晰
- 这次收口后，老 `/api/v0/*` 已经直接走：
  - `pydantic` 请求校验
  - `pydantic-ai` 语义解析
  - 后端受控 SQL Builder
  - 数据库执行

## 涉及文件

- `app.py`
- `src/qsql/schemas.py`
- `src/server/semantic_query_api.py`
- `README.md`
- `resources/semantic/README.md`
- `tests/test_app_semantic_migration.py`
- `tests/test_semantic_query_pipeline.py`
- `tests/test_imports.py`

## 如何验证

- `.venv/bin/python -m pytest tests/test_app_semantic_migration.py tests/test_semantic_query_pipeline.py tests/test_imports.py -q`
- `ruff check app.py src tests`
- `.venv/bin/python -m py_compile app.py $(find src -name '*.py' -print) $(find tests -name '*.py' -print)`
