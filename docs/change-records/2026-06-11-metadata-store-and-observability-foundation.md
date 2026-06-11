# 2026-06-11 metadata store 与结构化观测基础设施

## 改了什么

- 新增 `src/qsql/metadata_store.py`
  - 使用独立 SQLite 落库存储：
    - `dataset_connection`
    - `schema_table`
    - `schema_column`
    - `schema_relationship`
    - `value_mapping`
    - `metadata_sync_job`
- 新增 `src/qsql/schema_sync.py`
  - 支持按 `dataset_id` 读取 MySQL 连接配置
  - 从 `information_schema` 拉取表、列、关系
  - 回写到 `metadata store`
  - 记录同步任务状态
- 新增手动同步脚本：
  - `scripts/sync_dataset_schema.py`
- 新增 `src/qsql/observability.py`
  - 将主链路事件写成 JSON Lines
- 在 `app.py` 接入结构化路由事件：
  - `/api/v0/generate_sql`
  - `/api/v0/run_sql`
  - `/api/v0/search`
- 扩充 `src/utils/setting.py`
  - `METADATA_DIR`
  - `METADATA_DB_PATH`
  - `QSQL_EVENT_LOG_DIR`

## 为什么改

- 继续保持当前“语义层 + 受控 SQL”的主方向，不回退到 `LLM 直接产 SQL`
- 给后续三块能力打底：
  - Schema 元数据落库与同步
  - 值映射独立建模
  - 路由与阶段耗时观测
- 让后续语义草稿生成器和运维入口有稳定的数据来源

## 涉及文件

- `src/qsql/metadata_store.py`
- `src/qsql/schema_sync.py`
- `src/qsql/observability.py`
- `src/utils/setting.py`
- `app.py`
- `scripts/sync_dataset_schema.py`
- `tests/test_metadata_store.py`
- `tests/test_app_semantic_migration.py`

## 如何验证

- `./.venv/bin/python -m pytest tests/test_metadata_store.py tests/test_app_semantic_migration.py -q`
- `./.venv/bin/python -m pytest tests -q`
- `ruff check app.py src tests scripts`
- `python -m py_compile app.py $(find src -name '*.py' -print) $(find tests -name '*.py' -print) $(find scripts -name '*.py' -print)`
