# 2026-06-15 BIRD Mini-Dev student_club 多表评测接入

## 改了什么

- 新增 `resources/semantic/bird_student_club.json`
  - 为 BIRD Mini-Dev 的 `student_club` 库定义受控语义目录
  - 覆盖 `attendance` / `expense` / `income` / `budget` 四类带时间锚点的事实表
  - 显式声明 `member -> major`、`member -> zip_code`、`expense -> budget -> event`、`attendance -> event/member` 等安全 join path
- 新增 `resources/semantic_plugins/bird_student_club.json`
  - 补 `Women's Soccer`、`April Speaker`、`Vice President`、`Medium` 等值映射
- 新增 `resources/semantic_examples/bird_student_club.jsonl`
  - 补 attendance 多跳 join、expense 链式 join、budget 时间维、multi-metric few-shot 示例
- 新增 `resources/eval_cases/bird_student_club.jsonl`
  - 落 12 条多表 BI 子集评测题，覆盖 summary / group_by / multi-hop / multi-dimension / multi-metric
- 新增 [tests/test_bird_student_club_catalog.py](/data/temp/qsql/tests/test_bird_student_club_catalog.py)
  - 覆盖 attendance 多跳 join、expense->budget->event 链式 join、datetime 日级边界扩展
- 修改 [src/qsql/semantic_postprocessor.py](/data/temp/qsql/src/qsql/semantic_postprocessor.py)
  - 新增 `iso_datetime` 时间维日级结束边界归一化
  - 当 time range 结束值是 `YYYY-MM-DD` 且维度声明为 `iso_datetime` 时，自动扩成 `YYYY-MM-DDT23:59:59`
- 修改 [src/qsql/schemas.py](/data/temp/qsql/src/qsql/schemas.py)
  - 复用前面已新增的 `time_format` 字段，`student_club.event_date` 使用 `iso_datetime`

## 为什么改

- 单个 BIRD 库不足以说明多表能力是否稳定，需要第二个结构不同的真实库交叉验证。
- `student_club` 比 `debit_card_specializing` 更适合当前受控 join 图：
  - `attendance`、`expense`、`income`、`budget` 都能沿 FK -> PK 安全路径扩到维表
  - 不需要放开 account->disp 这类高 fan-out 风险路径
- `event.event_date` 存的是 ISO datetime 文本，暴露了当前日级时间边界只写到 `YYYY-MM-DD` 时会漏数的问题，需要底座级修复。

## 如何验证

- 单测：
  - `.venv/bin/python -m pytest tests/test_bird_student_club_catalog.py`
  - `.venv/bin/python -m pytest tests/test_bird_student_club_catalog.py tests/test_bird_debit_card_catalog.py tests/test_semantic_eval_runner.py tests/test_sql_builder_join.py tests/test_real_business_online_retail_catalog.py`
  - `.venv/bin/python -m pytest tests/`
- Lint：
  - `ruff check src/ tests/`
- 真实 SQLite EX 评测：
  - `.venv/bin/python scripts/semantic_eval_runner.py --dataset-id bird_student_club --cases resources/eval_cases/bird_student_club.jsonl --sqlite-db resources/uploads/bird_mini_dev/minidev/MINIDEV/dev_databases/student_club/student_club.sqlite --row-limit 40`
  - `.venv/bin/python scripts/semantic_eval_runner.py --dataset-id bird_student_club --cases resources/eval_cases/bird_student_club.jsonl --sqlite-db resources/uploads/bird_mini_dev/minidev/MINIDEV/dev_databases/student_club/student_club.sqlite --row-limit 40 --repeat 3`

## 结果

- `student_club` 12 条多表 BI 子集首轮 `12/12` 通过，全部 `EX` 命中。
- `repeat=3` 下 `36/36` 通过，`stability_rate=1.0000`。
- 当前两套 BIRD 子集累计：
  - `debit_card_specializing`：`12/12`，`repeat=3 -> 36/36`
  - `student_club`：`12/12`，`repeat=3 -> 36/36`
- 全量回归：`141 passed, 1 skipped`。
