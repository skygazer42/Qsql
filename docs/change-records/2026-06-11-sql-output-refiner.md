# 2026-06-11 SQL 输出标准化改造（Pydantic + 可选 pydantic-ai）

## 改了什么

- 在 `src/qsql/schemas.py` 新增配置字段 `sql_output_refiner_enabled` 到
  `AppConfigModel`，用于通过环境变量控制是否启用 SQL 输出标准化。
- 新增 `src/qsql/sql_output_refiner.py`（可选改造）：
  - `SQLNormalizationResult`：统一记录 `raw_sql/sql/statement_type/is_select/normalizer`。
  - `SqlOutputRefiner`：本地兜底清洗 + 可选 pydantic-ai 标准化执行器。
  - `build_sql_output_refiner`：能力构建与降级（不可用时返回 fallback）。
- 在 `app.py` 中接入标准化器：
  - `generate_sql` 与 `search` 先生成原始 SQL，再做标准化。
  - 新增环境配置项 `SQL_OUTPUT_REFINER_ENABLED` 并写入启动日志。
  - `generate_sql`、`search` 日志追加标准化元信息（statement_type/normalizer）。

## 为什么改

- 现有输出常见包含 markdown、前缀文字或解释文本，后续执行 SQL 时会带来脏数据风险。
- 先保持生成链路不变，再做“可选标准化”，在无 pydantic-ai 可用时自动回退，本身不影响主流程。
- 该方案对“数据管理/验证”友好：Pydantic 统一边界与配置校验，减少参数污染与运行期异常。

## 涉及文件

- `src/qsql/schemas.py`
- `src/qsql/sql_output_refiner.py`
- `app.py`

## 验证

- `ruff check app.py src/qsql/schemas.py src/qsql/sql_output_refiner.py`
- `python -m py_compile app.py src/qsql/schemas.py src/qsql/sql_output_refiner.py`

## 注意

- 目前该改造默认关闭（`SQL_OUTPUT_REFINER_ENABLED=false`），不影响既有运行。
- 当前只做验证层标准化，不改变向量检索或提示词逻辑。
