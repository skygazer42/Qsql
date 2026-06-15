# 2026-06-15 semantic eval multi-metric alignment

## 改了什么

- `semantic_eval_runner` 的 `EvalCase` 增加 `expect_metric_keys`，用于校验多指标查询。
- 分组取样逻辑支持多指标 SQL：单指标继续按 `metric_value` 排序，多指标按第一个指标列排序。
- group_by 校验允许“额外分组维度已被 eq 过滤固定”的等价情况。
- `online_retail_extended.jsonl` 中 4 条多指标用例从旧的澄清预期改为 ready 预期。

## 为什么改

- P2-2 已支持同表同粒度多指标查询，原评测集中“多指标必须澄清”的 L4 预期已经过期。
- 真实评测发现多指标分组 SQL 不再输出 `metric_value`，runner 继续按该列排序会导致 SQLite 报错。

## 涉及文件

- `scripts/semantic_eval_runner.py`
- `resources/eval_cases/online_retail_extended.jsonl`
- `tests/test_semantic_eval_runner.py`

## 如何验证

- `.venv/bin/python -m pytest tests/test_semantic_eval_runner.py -q`
- `.venv/bin/python scripts/semantic_eval_runner.py --dataset-id online_retail --cases resources/eval_cases/online_retail_extended.jsonl --sqlite-db resources/uploads/online_retail/online_retail.sqlite3 --row-limit 5`
- `.venv/bin/python scripts/semantic_eval_runner.py --dataset-id online_retail --cases resources/eval_cases/online_retail.jsonl --sqlite-db resources/uploads/online_retail/online_retail.sqlite3 --row-limit 5 --repeat 2`
