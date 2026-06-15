# 2026-06-15 BIRD Mini-Dev formula_1 多表评测接入

## 改了什么

- 新增 `resources/semantic/bird_formula_1.json`
  - 为 BIRD Mini-Dev 的 `formula_1` 库定义受控语义目录
  - 以 `results` / `qualifying` 两张事实表为中心，接入 `races`、`circuits`、`drivers`、`constructors`、`status`
  - 显式声明 `results -> races -> circuits`、`results -> drivers`、`results -> constructors`、`results -> status`、`qualifying -> races/driver/constructor` 等安全 join path
- 新增 `resources/semantic_plugins/bird_formula_1.json`
  - 补 `Ferrari`、`McLaren`、`Red Bull`、`UK`、`Italy`、`Monaco`、`British`、`German`、`Finished` 等值映射
- 新增 `resources/semantic_examples/bird_formula_1.jsonl`
  - 补 results group_by、results multi-metric、qualifying group_by、跨年度 trend few-shot 示例
- 新增 `resources/eval_cases/bird_formula_1.jsonl`
  - 落 12 条多表 BI 子集评测题，覆盖 results summary / group_by / multi-metric / multi-dimension / qualifying group_by
- 新增 [tests/test_bird_formula_1_catalog.py](/data/temp/qsql/tests/test_bird_formula_1_catalog.py)
  - 覆盖 results 多跳 join、qualifying 多跳 join
  - 覆盖 constructor/country/status 值归一化
- 修改 [docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md](/data/temp/qsql/docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md)
  - 同步四套 harder 子集的当前 EX 结果与累计准确率

## 为什么改

- 在 `financial` 之后，需要再引入一个**不同结构**的真实多表库做交叉验证。
- `formula_1` 比前三套更接近“多事实表 + 多维表 + 长链 join”的典型 BI 问数场景：
  - `results` 与 `qualifying` 两张事实表共用 `races` / `drivers` / `constructors`
  - `races` 再继续连到 `circuits`
  - 同时有时间、国家、车队、车手国籍、状态等多种过滤和分组轴
- 这套库仍然可以被约束在受控语义底座里，不需要放开任意 SQL 编程题能力。

## 如何验证

- 单测：
  - `.venv/bin/python -m pytest tests/test_bird_formula_1_catalog.py`
- 真实 SQLite EX 评测：
  - `.venv/bin/python scripts/semantic_eval_runner.py --dataset-id bird_formula_1 --cases resources/eval_cases/bird_formula_1.jsonl --sqlite-db resources/uploads/bird_mini_dev/minidev/MINIDEV/dev_databases/formula_1/formula_1.sqlite --row-limit 40`
  - `.venv/bin/python scripts/semantic_eval_runner.py --dataset-id bird_formula_1 --cases resources/eval_cases/bird_formula_1.jsonl --sqlite-db resources/uploads/bird_mini_dev/minidev/MINIDEV/dev_databases/formula_1/formula_1.sqlite --row-limit 40 --repeat 3`
- 全量回归：
  - `.venv/bin/python -m pytest tests/`
  - `ruff check src/ tests/`

## 结果

- `formula_1` 12 条多表 BI 子集首轮 `12/12` 通过，全部 `EX` 命中。
- `repeat=3` 为 `36/36`，`stability_rate=1.0000`。
- 当前四套 BIRD harder 子集累计：
  - `debit_card_specializing`：`12/12`，`repeat=3 -> 36/36`
  - `student_club`：`12/12`，`repeat=3 -> 36/36`
  - `financial`：`12/12`，`repeat=3 -> 36/36`
  - `formula_1`：`12/12`，`repeat=3 -> 36/36`
  - 合计单轮 `48/48`，`repeat=3` 累计 `144/144`
