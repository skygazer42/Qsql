# 2026-06-11 pydantic-ai SQL 输出规范化（直连版）

## 改了什么

- 在项目依赖中加入 `pydantic-ai`，将 SQL 输出标准化从“可选实验”升级为可直接启用的功能链路。
- 优化 `src/qsql/sql_output_refiner.py`：
  - 兼容 `OpenAIChatModel` 与 `OpenAIModel` 的模型导入方式；
  - 兼容 `pydantic-ai` 运行结果对象中可能出现的 `output` / `data` 字段差异；
  - 使用 `ValidateRequest.parse` 做返回体二次解析兜底。
- 将 `.env` 示例中的 `SQL_OUTPUT_REFINER_ENABLED` 调整为 `true`，默认按开关启用标准化。

## 为什么改

- 之前的实现更偏“兜底方案”；本次改造在不改变主链路前提下，让 `pydantic-ai` 直接参与 SQL 清洗输出，使 `generate_sql/search` 的执行 SQL 统一经过结构化约束层。
- 保持 fallback 机制，避免外部模型返回异常结构时影响核心查询链路。

## 涉及文件

- `pyproject.toml`
- `src/qsql/sql_output_refiner.py`
- `.env`
- `docs/change-records/2026-06-11-sql-output-refiner.md`
