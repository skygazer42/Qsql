# 2026-06-11 pydantic SQL 链路收口

## 改了什么

- `src/qsql/schemas.py`
  - 新增 `SQLNormalizationResult`，统一承接 `pydantic-ai` 的结构化输出。
  - 新增 `SQLExecutionPayload`，作为缓存与执行前校验的唯一 SQL 载荷。
  - 新增 `DataFrameResponse` / `SearchResponse`，减少接口层手拼 dict。
- `src/qsql/sql_output_refiner.py`
  - 直接复用 `schemas.py` 中的 `SQLNormalizationResult`。
- `app.py`
  - 新增统一 helper：生成原始 SQL、调用 `pydantic-ai` 标准化、构建 `SQLExecutionPayload`、执行前校验、落缓存。
  - `generate_sql` / `search` 复用同一条结构化 SQL 链路。
  - `run_sql` 改为从缓存中的 `sql_payload` 读取并再次做 `pydantic` 校验后执行。
- `tests/test_sql_pipeline_models.py`
  - 新增最小测试，覆盖查询 SQL 放行、非查询 SQL 拒绝、`SearchResponse` 包装。

## 为什么改

- 之前虽然已经去掉 fallback，但 `app.py` 里仍然存在散乱的字符串缓存与执行逻辑。
- 本次进一步把 SQL 从“字符串约定”改成“结构化载荷约定”，让 `pydantic` 负责执行前的数据约束，`pydantic-ai` 负责生成该结构。

## 涉及文件

- `app.py`
- `src/qsql/schemas.py`
- `src/qsql/sql_output_refiner.py`
- `tests/test_sql_pipeline_models.py`
- `docs/change-records/2026-06-11-pydantic-sql-pipeline-tightening.md`
