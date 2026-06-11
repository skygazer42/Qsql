# 2026-06-11 Metadata 定时同步器与阶段耗时埋点

## 改了什么

- 新增 `src/qsql/metadata_scheduler.py`
  - `MetadataSyncScheduler`
  - `start_metadata_sync_scheduler`
- `MetadataStore` 增加 `list_dataset_connections(enabled_only=...)`
- `metadata_api` 增加 `get_metadata_store()`
- `SemanticParseResponse` / `SemanticRunResponse` 增加 `timings`
- 新增 `SemanticStageTimings`
- `SemanticQueryService.prepare_query(...)` 输出阶段耗时：
  - `catalog_load_ms`
  - `semantic_agent_ms`
  - `sql_build_ms`
  - `total_ms`
- `app.py` 的 `/api/v0/generate_sql` 与 `/api/v0/search` 事件日志改为记录真实阶段耗时
- 应用启动时按环境变量可选启用 metadata 定时同步器

## 为什么改

- 前一轮已经有：
  - metadata store
  - 手动 schema sync
  - 路由结构化事件
- 但目标里还缺两块显式能力：
  1. 定时同步
  2. 更细的工具/阶段耗时埋点

这次不改主方向，只补这两个缺口：

- 定时同步仍然只服务 metadata 层
- 运行时查询仍然走 `pydantic + pydantic-ai + controlled SQL`

## 涉及文件

- `app.py`
- `src/qsql/metadata_scheduler.py`
- `src/qsql/metadata_store.py`
- `src/qsql/semantic_service.py`
- `src/qsql/schemas.py`
- `src/server/metadata_api.py`
- `tests/test_metadata_scheduler.py`
- `tests/test_semantic_query_pipeline.py`
- `tests/test_app_semantic_migration.py`

## 如何验证

```bash
.venv/bin/python -m pytest tests/test_metadata_scheduler.py tests/test_semantic_query_pipeline.py tests/test_app_semantic_migration.py -q
ruff check app.py src tests scripts
python -m py_compile app.py $(find src -name '*.py' -print) $(find tests -name '*.py' -print) $(find scripts -name '*.py' -print)
.venv/bin/python -m pytest tests -q
```
