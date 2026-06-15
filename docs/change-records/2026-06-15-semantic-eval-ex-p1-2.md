# 2026-06-15 semantic eval EX P1-2

## 改了什么

- `scripts/semantic_eval_runner.py` 的 `EvalCase` / `EvalResult` 改为 Pydantic 模型。
- 评测用例新增可选 `expected_sql` 字段。
- runner 在提供 SQLite 执行库时会执行标准 SQL，并对预测 SQL 结果与标准结果做 EX 结果集等价判断。
- EX 比对按标准 SQL 输出列投影比较，容忍预测 SQL 额外 SELECT 辅助列。
- summary 新增 `ex_checked` / `ex_ok` / `ex_failed` 计数。
- `resources/eval_cases/online_retail_extended.jsonl` 补充 L1/L2/L3 标准 SQL 样本。

## 为什么改

- 让语义评测从“结构断言 + 非空结果”升级为可选的结果集等价评估，更接近 BIRD / Spider 的 EX 指标。
- 保持 QSQL 的受控路线：评测标准 SQL 只用于离线验证，不进入线上生成链路。

## 涉及文件

- `scripts/semantic_eval_runner.py`
- `tests/test_semantic_eval_runner.py`
- `resources/eval_cases/online_retail_extended.jsonl`
- `docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md`

## 如何验证

- `.venv/bin/python -m pytest tests/test_semantic_eval_runner.py -q`
- `ruff check src/ app.py scripts tests test_search_algorithm.py`
- `.venv/bin/python -m pytest tests/`
