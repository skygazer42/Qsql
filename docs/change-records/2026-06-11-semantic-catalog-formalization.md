# 2026-06-11 语义目录正式化

## 改了什么

- 将 `resources/semantic/<dataset_id>.json` 的目录结构正式化为：
  - `catalog_version`
  - `tables`
  - `metrics`
  - `dimensions`
  - `aliases`
  - `metric_versions`
- `metrics` 和 `dimensions` 不再直接写物理表名，统一改成引用 `table_key`。
- 新增 `SemanticTableDefinition`，由它集中维护宽表元信息和默认时间维度。
- 在 `SemanticCatalog` 上增加目录级交叉校验：
  - 指标/维度引用的语义表必须存在
  - 指标支持的维度必须存在且与指标同表
  - 指标允许的口径必须存在且属于当前指标
  - 表/指标默认时间维度必须存在、同表且类型为 `time`
  - 口径过滤维度必须存在且与指标同表
  - 别名目标必须存在且类型受限
- `sql_builder` 改为通过 `table_key -> physical_table` 解析真正的 SQL 来源表。
- 内置示例 `resources/semantic/sales.json` 改成新结构。

## 为什么改

- 这轮重构不再保留旧的平铺 `table` 字段格式。
- 目标是把业务口径、语义表、指标、维度之间的关系正式化，减少 prompt 承担的隐式制度。
- 目录错误要在加载阶段失败，不继续拖到 SQL 生成或执行阶段。

## 涉及文件

- `src/qsql/schemas.py`
- `src/qsql/semantic_catalog.py`
- `src/qsql/sql_builder.py`
- `src/qsql/semantic_agent.py`
- `resources/semantic/sales.json`
- `resources/semantic/README.md`
- `tests/test_semantic_query_pipeline.py`

## 如何验证

- `./.venv/bin/python -m pytest tests/test_semantic_query_pipeline.py -q`
- `./.venv/bin/python -m pytest tests/test_app_semantic_migration.py tests/test_semantic_query_pipeline.py -q`
- `ruff check app.py src tests`
- `python -m py_compile app.py $(find src -name '*.py' -print) $(find tests -name '*.py' -print)`
