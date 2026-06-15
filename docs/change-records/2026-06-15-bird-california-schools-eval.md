# 2026-06-15 BIRD Mini-Dev california_schools 多表评测接入

## 改了什么

- 新增 `resources/semantic/bird_california_schools.json`
  - 为 BIRD Mini-Dev 的 `california_schools` 库定义受控语义目录
  - 以 `schools` 维表为中心，接入 `frpm` 和 `satscores` 两张事实表
  - 显式声明 `frpm -> schools`、`satscores -> schools` 安全 join path
  - 支持学校数、K-12 招生、免费午餐人数、FRPM 比例、SAT 参考人数、SAT 数学/阅读均分、1500+ 人数
- 新增 `resources/semantic_plugins/bird_california_schools.json`
  - 补 `Los Angeles County` / `Fresno County` / `Santa Clara County` 等县名映射
  - 补 `charter schools -> 1`、`school-level -> S`、`directly funded -> Directly funded` 等值映射
- 新增 `resources/semantic_examples/bird_california_schools.jsonl`
  - 补 school / frpm / sat 三类 few-shot 示例
  - 覆盖单指标、多指标、跨表过滤、无时间维统计
- 新增 `resources/eval_cases/bird_california_schools.jsonl`
  - 落 12 条多表 BI 子集评测题
  - 覆盖 schools / frpm / satscores 三类汇总与分组
  - 覆盖两条多指标查询
- 新增 [tests/test_bird_california_schools_catalog.py](/data/temp/qsql/tests/test_bird_california_schools_catalog.py)
  - 覆盖 `frpm -> schools` 的 school_type 汇总 SQL
  - 覆盖 `satscores -> schools` 的 funding_type 汇总 SQL
  - 覆盖 `charter schools -> 1` 与 `school-level -> S` 的归一化
- 修改 [tests/test_sql_builder_join.py](/data/temp/qsql/tests/test_sql_builder_join.py)
  - 补带空格字段名的 quoted identifier 回归测试
- 修改 [src/qsql/sql_builder.py](/data/temp/qsql/src/qsql/sql_builder.py)
  - 受控 SQL builder 现在支持字段名/表名自动按 SQL identifier quoting 输出
  - `School Type`、`Enrollment (K-12)`、`Percent (%) Eligible FRPM (K-12)` 这类列名可以直接出现在 semantic catalog 里
- 修改 [docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md](/data/temp/qsql/docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md)
  - 同步七套 harder 子集的当前 EX 结果与累计准确率

## 为什么改

- `california_schools` 不是表数最多的库，但它补的是另一类非常真实的 BI 场景：
  - 公共教育统计类数据仓，维表和事实表职责清晰
  - 指标以招生、免费午餐、SAT 成绩为主，天然是问数底座该擅长的范围
  - 很多字段名带空格、括号和百分号，逼出了 SQL builder 的真实兼容性缺口
- 当前底座如果不能稳定处理这类字段名，很多现实数据库即使 schema 简单，也接不进来。
- 所以这次重点不是“再多一套数据”，而是顺手把**quoted identifier 支持**补成通用能力。

## 如何验证

- 定向单测：
  - `.venv/bin/python -m pytest tests/test_sql_builder_join.py::test_build_query_execution_plan_supports_quoted_field_identifiers tests/test_bird_california_schools_catalog.py -q`
- 真实 SQLite EX 评测：
  - `.venv/bin/python scripts/semantic_eval_runner.py --dataset-id bird_california_schools --cases resources/eval_cases/bird_california_schools.jsonl --sqlite-db resources/uploads/bird_mini_dev/minidev/MINIDEV/dev_databases/california_schools/california_schools.sqlite --row-limit 40`
  - `.venv/bin/python scripts/semantic_eval_runner.py --dataset-id bird_california_schools --cases resources/eval_cases/bird_california_schools.jsonl --sqlite-db resources/uploads/bird_mini_dev/minidev/MINIDEV/dev_databases/california_schools/california_schools.sqlite --row-limit 40 --repeat 3`
- 全量回归：
  - `.venv/bin/python -m pytest tests/`
  - `ruff check src/ tests/`

## 结果

- `bird_california_schools` 12 条多表 BI 子集首轮 `12/12` 通过，全部 `EX` 命中。
- `repeat=3` 为 `36/36`，`stability_rate=1.0000`。
- 当前七套 BIRD harder 子集累计：
  - `debit_card_specializing`：`12/12`，`repeat=3 -> 36/36`
  - `student_club`：`12/12`，`repeat=3 -> 36/36`
  - `financial`：`12/12`，`repeat=3 -> 36/36`
  - `formula_1`：`12/12`，`repeat=3 -> 36/36`
  - `codebase_community`：`12/12`，`repeat=3 -> 36/36`
  - `superhero`：`12/12`，`repeat=3 -> 36/36`
  - `california_schools`：`12/12`，`repeat=3 -> 36/36`
  - 合计单轮 `84/84`，`repeat=3` 累计 `252/252`
