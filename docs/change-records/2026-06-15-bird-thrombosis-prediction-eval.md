# 2026-06-15 BIRD Mini-Dev thrombosis_prediction 多表评测接入

## 改了什么

- 新增 `resources/semantic/bird_thrombosis_prediction.json`
  - 为 BIRD Mini-Dev 的 `thrombosis_prediction` 库定义受控语义目录
  - 接入 `Patient`、`Laboratory`、`Examination`
  - 明确仅开放两条安全链路：
    - `Laboratory -> Patient`
    - `Examination -> Patient`
  - 新增 `lab_record_count`、`lab_patient_count`、`total_cholesterol_avg`、`triglyceride_avg`、`hemoglobin_avg`
  - 新增 `exam_record_count`、`exam_patient_count`
- 新增 `resources/semantic_plugins/bird_thrombosis_prediction.json`
  - 补 `female/male -> F/M`
  - 补 `admitted -> +`
  - 补 `SLE/lupus`、`RA`、`APS`
  - 补 `positive/negative -> +/-` 到 `KCT/RVVT/LAC/CRP`
- 新增 `resources/semantic_examples/bird_thrombosis_prediction.jsonl`
  - 补 Laboratory 根表和 Examination 根表的 few-shot
  - 补 `lab_patient_count + total_cholesterol_avg`
  - 补 `exam_record_count + exam_patient_count`
- 新增 `resources/eval_cases/bird_thrombosis_prediction.jsonl`
  - 落 12 条两表 BI 子集评测题
  - 覆盖 3 条 summary、7 条 group by、2 条 multi-metric
  - 覆盖 `Patient -> Laboratory` 和 `Patient -> Examination` 两条稳定链路
- 新增 [tests/test_bird_thrombosis_prediction_catalog.py](/data/temp/qsql/tests/test_bird_thrombosis_prediction_catalog.py)
  - 覆盖 `Laboratory -> Patient`
  - 覆盖 `Examination -> Patient`
  - 覆盖 `admitted -> +`
  - 覆盖数值型 `thrombosis flag` 的 `"1" -> 1` 归一化
  - 覆盖 lab 多指标 ready 路径
- 修改 [docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md](/data/temp/qsql/docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md)
  - 同步十一套 harder 子集的累计 EX 结果
  - 标记 BIRD Mini-Dev 11/11 数据库已全部接入

## 为什么改

- `thrombosis_prediction` 表数少，但很适合拿来验证当前 generic base 的另一条边界：
  - `Laboratory` 与 `Examination` 都只通过 `Patient` 相连
  - 按当前底座的 join 约束，`Laboratory -> Patient -> Examination` 这种 sibling fact 拼接不能放开，否则就是 fan-out
- 所以这轮不是去追求更复杂的三表任意 SQL，而是确认底座在**不破坏安全 join 原则**的前提下，仍然能把患者维度挂到两类事实表上，稳定做：
  - 患者数 / 记录数
  - 实验室均值指标
  - 检查标记分组
  - 同根表多指标
- 这也把 Mini-Dev 里最后一个未接入库补齐了，当前 11 个 SQLite 库已经全部落入同一套受控评测框架。

## 如何验证

- 定向单测：
  - `.venv/bin/python -m pytest tests/test_bird_thrombosis_prediction_catalog.py -q`
- 真实 SQLite EX 评测：
  - `.venv/bin/python scripts/semantic_eval_runner.py --dataset-id bird_thrombosis_prediction --cases resources/eval_cases/bird_thrombosis_prediction.jsonl --sqlite-db resources/uploads/bird_mini_dev/minidev/MINIDEV/dev_databases/thrombosis_prediction/thrombosis_prediction.sqlite --row-limit 40`
  - `.venv/bin/python scripts/semantic_eval_runner.py --dataset-id bird_thrombosis_prediction --cases resources/eval_cases/bird_thrombosis_prediction.jsonl --sqlite-db resources/uploads/bird_mini_dev/minidev/MINIDEV/dev_databases/thrombosis_prediction/thrombosis_prediction.sqlite --row-limit 40 --repeat 3`
- 全量回归：
  - `find src -type d -name '__pycache__' -prune -exec rm -rf {} + && find src -type f -name '*.pyc' -delete && .venv/bin/python -B -m pytest tests/`
  - `ruff check src/ tests/`

## 结果

- `bird_thrombosis_prediction` 12 条两表 BI 子集首轮 `12/12` 通过，全部 `EX` 命中。
- `repeat=3` 为 `36/36`，`stability_rate=1.0000`。
- 当前十一套 BIRD harder 子集累计：
  - `debit_card_specializing`：`12/12`，`repeat=3 -> 36/36`
  - `student_club`：`12/12`，`repeat=3 -> 36/36`
  - `financial`：`12/12`，`repeat=3 -> 36/36`
  - `formula_1`：`12/12`，`repeat=3 -> 36/36`
  - `codebase_community`：`12/12`，`repeat=3 -> 36/36`
  - `superhero`：`12/12`，`repeat=3 -> 36/36`
  - `california_schools`：`12/12`，`repeat=3 -> 36/36`
  - `european_football_2`：`12/12`，`repeat=3 -> 36/36`
  - `toxicology`：`12/12`，`repeat=3 -> 36/36`
  - `card_games`：`12/12`，`repeat=3 -> 36/36`
  - `thrombosis_prediction`：`12/12`，`repeat=3 -> 36/36`
  - 合计单轮 `132/132`，`repeat=3` 累计 `396/396`
