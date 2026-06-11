# 2026-06-11 pydantic-ai SQL 标准化（无 fallback）

## 改了什么

- `app.py`
  - 取消 `sql_output_refiner_enabled` 配置字段读取与透传。
  - `build_sql_output_refiner(...)` 改为固定入参构建，不再按环境变量启停。
  - 启动日志移除 `sql_output_refiner_enabled` 输出。
- `src/qsql/schemas.py`
  - 移除 `AppConfigModel.sql_output_refiner_enabled` 字段。
- `.env`
  - 移除 `SQL_OUTPUT_REFINER_ENABLED` 示例配置，避免误导。
- `src/qsql/sql_output_refiner.py`
  - 保持 `pydantic-ai` 作为唯一标准化路径（只通过 `pydantic-ai` 结构化返回做校验）。
  - 继续保留 `output`/`data` 字段读取兼容，不再引入本地 `fallback` 分支。

## 为什么改

- 用户要求“不要 fallback”，改造为固定标准化路径，避免静默降级回退。

## 涉及文件

- `app.py`
- `src/qsql/schemas.py`
- `.env`
- `src/qsql/sql_output_refiner.py`
- `docs/change-records/2026-06-11-sql-output-refiner-no-fallback.md`
