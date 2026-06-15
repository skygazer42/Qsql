# 2026-06-15 BIRD Mini-Dev debit_card_specializing 多表评测接入

## 改了什么

- 新增 `resources/semantic/bird_debit_card_specializing.json`
  - 为 BIRD Mini-Dev 的 `debit_card_specializing` 库定义受控语义目录
  - 覆盖 `customers` / `gasstations` / `products` / `transactions_1k` / `yearmonth`
  - 显式声明实体与关系，复用现有受控 join builder
- 新增 `resources/semantic_plugins/bird_debit_card_specializing.json`
  - 补 `Czech Republic -> CZE`、`euro -> EUR` 等值映射
- 新增 `resources/semantic_examples/bird_debit_card_specializing.jsonl`
  - 补 few-shot 示例，覆盖 `YYYYMM` 时间键、多表 join、时间窗口、多指标
- 新增 `resources/eval_cases/bird_debit_card_specializing.jsonl`
  - 落 12 条多表 BI 子集评测题，全部带 `expected_sql`
- 新增 [tests/test_bird_debit_card_catalog.py](/data/temp/qsql/tests/test_bird_debit_card_catalog.py)
  - 覆盖 BIRD catalog 的 yearmonth join、transaction 多表 join、`YYYYMM` 年份补全、数值过滤值归一化
- 修改 [src/qsql/schemas.py](/data/temp/qsql/src/qsql/schemas.py)
  - `SemanticDimensionDefinition` 新增可选 `time_format`
- 修改 [src/qsql/semantic_postprocessor.py](/data/temp/qsql/src/qsql/semantic_postprocessor.py)
  - 显式年份补全支持按维度时间格式输出
  - 新增 number 维度过滤值归一化，避免 `"6"` 与 `6` 语义一致但评测误判

## 为什么改

- Online Retail 是单宽表，不足以验证当前 text2sql 底座的多表 join 能力。
- BIRD Mini-Dev 的 `debit_card_specializing` 具备真实多表、多过滤、多指标、多时间键场景，适合做第一批多表评测。
- 该库的 `yearmonth.Date` 采用 `YYYYMM`，直接暴露了底座当前默认 ISO 日期补全的边界，需要最小修正。

## 如何验证

- 单测：
  - `.venv/bin/python -m pytest tests/test_bird_debit_card_catalog.py`
  - `.venv/bin/python -m pytest tests/test_bird_debit_card_catalog.py tests/test_semantic_eval_runner.py tests/test_sql_builder_join.py tests/test_real_business_online_retail_catalog.py`
  - `.venv/bin/python -m pytest tests/`
- Lint：
  - `ruff check src/ tests/`
- 真实 SQLite EX 评测：
  - `.venv/bin/python scripts/semantic_eval_runner.py --dataset-id bird_debit_card_specializing --cases resources/eval_cases/bird_debit_card_specializing.jsonl --sqlite-db resources/uploads/bird_mini_dev/minidev/MINIDEV/dev_databases/debit_card_specializing/debit_card_specializing.sqlite --row-limit 20`
  - `.venv/bin/python scripts/semantic_eval_runner.py --dataset-id bird_debit_card_specializing --cases resources/eval_cases/bird_debit_card_specializing.jsonl --sqlite-db resources/uploads/bird_mini_dev/minidev/MINIDEV/dev_databases/debit_card_specializing/debit_card_specializing.sqlite --row-limit 20 --repeat 3`

## 结果

- 12 条 BIRD 多表 BI 子集首轮 `12/12` 通过，全部 `EX` 命中。
- `repeat=3` 下 `36/36` 通过，`stability_rate=1.0000`。
- 全量回归 `138 passed, 1 skipped`。
