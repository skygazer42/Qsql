# 2026-06-15 BIRD Mini-Dev superhero 多表评测接入

## 改了什么

- 新增 `resources/semantic/bird_superhero.json`
  - 为 BIRD Mini-Dev 的 `superhero` 库定义受控语义目录
  - 以 `superhero` / `hero_power` / `hero_attribute` 三类事实/桥表为中心，接入 `publisher`、`race`、`gender`、`alignment`、`colour`、`superpower`、`attribute`
  - 显式拆分 `eye_colour_dim`、`hair_colour_dim` 两个颜色角色
  - 显式声明 `hero_power -> superhero -> publisher/race/gender/alignment/colour`、`hero_attribute -> superhero -> ...` 等安全 join path
- 新增 `resources/semantic_plugins/bird_superhero.json`
  - 补 `Marvel Comics`、`DC Comics`、`Super Strength`、`Flight`、`Agility`、`Intelligence` 等值映射
- 新增 `resources/semantic_examples/bird_superhero.jsonl`
  - 补无时间维的 group_by、多桥表 group_by、多指标 attribute few-shot 示例
- 新增 `resources/eval_cases/bird_superhero.jsonl`
  - 落 12 条多表 BI 子集评测题，覆盖 hero / powered hero / attribute 三类查询
- 新增 [tests/test_bird_superhero_catalog.py](/data/temp/qsql/tests/test_bird_superhero_catalog.py)
  - 覆盖 `hero_power -> superhero -> publisher`
  - 覆盖 `hero_attribute -> superhero -> publisher`
  - 覆盖无时间维值归一化和 group by 排除 `NULL` 桶
- 修改 [src/qsql/sql_builder.py](/data/temp/qsql/src/qsql/sql_builder.py)
  - 支持**无默认时间维**指标直接构建 SQL
  - `group_by` 维度自动补 `IS NOT NULL`，避免聚出 `NULL` 桶
- 修改 [src/qsql/semantic_service.py](/data/temp/qsql/src/qsql/semantic_service.py)
  - 只有指标本身声明了 `default_time_dimension_key` 时才要求补时间范围
- 修改 [src/qsql/semantic_postprocessor.py](/data/temp/qsql/src/qsql/semantic_postprocessor.py)
  - 多指标强词匹配支持“长词覆盖短词”去噪，避免 `powered hero count` 误伤 `hero count`
- 修改 [tests/test_semantic_query_pipeline.py](/data/temp/qsql/tests/test_semantic_query_pipeline.py)
  - 补无时间维指标的通用回归测试
- 修改 [tests/test_semantic_postprocessor.py](/data/temp/qsql/tests/test_semantic_postprocessor.py)
  - 补重叠指标词误判的通用回归测试
- 修改 [docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md](/data/temp/qsql/docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md)
  - 同步六套 harder 子集的当前 EX 结果与累计准确率

## 为什么改

- `superhero` 是一套比 `codebase_community` 更偏**桥表 + 角色维度**的真实多表库：
  - `hero_power` / `hero_attribute` 都不是传统宽表，而是典型 bridge/fact 结构
  - `superhero` 同时挂 `publisher`、`race`、`gender`、`alignment`、`eye_colour`、`hair_colour`
  - `eye_colour` 和 `hair_colour` 共用同一物理表，能检验角色维度是否串位
- 这套库还暴露了两个底座层问题：
  - 当前语义服务默认所有指标都要时间范围，但 `superhero` 根本没有时间维
  - `group by` 维表时，缺失外键会被聚成 `NULL` 桶，EX 会和标准 SQL 偏一行
- 这两个问题都不该靠数据集特化规避，必须修成通用能力。

## 如何验证

- 定向单测：
  - `.venv/bin/python -m pytest tests/test_semantic_query_pipeline.py::test_build_query_execution_plan_supports_no_time_metric tests/test_semantic_query_pipeline.py::test_semantic_query_service_returns_ready_for_no_time_metric -q`
  - `.venv/bin/python -m pytest tests/test_semantic_postprocessor.py::test_postprocessor_does_not_treat_overlapping_metric_terms_as_multi_metric tests/test_bird_superhero_catalog.py -q`
- 真实 SQLite EX 评测：
  - `.venv/bin/python scripts/semantic_eval_runner.py --dataset-id bird_superhero --cases resources/eval_cases/bird_superhero.jsonl --sqlite-db resources/uploads/bird_mini_dev/minidev/MINIDEV/dev_databases/superhero/superhero.sqlite --row-limit 40`
  - `.venv/bin/python scripts/semantic_eval_runner.py --dataset-id bird_superhero --cases resources/eval_cases/bird_superhero.jsonl --sqlite-db resources/uploads/bird_mini_dev/minidev/MINIDEV/dev_databases/superhero/superhero.sqlite --row-limit 40 --repeat 3`
- 全量回归：
  - `.venv/bin/python -m pytest tests/`
  - `ruff check src/ tests/`

## 结果

- `bird_superhero` 12 条多表 BI 子集首轮 `12/12` 通过，全部 `EX` 命中。
- `repeat=3` 为 `36/36`，`stability_rate=1.0000`。
- 当前六套 BIRD harder 子集累计：
  - `debit_card_specializing`：`12/12`，`repeat=3 -> 36/36`
  - `student_club`：`12/12`，`repeat=3 -> 36/36`
  - `financial`：`12/12`，`repeat=3 -> 36/36`
  - `formula_1`：`12/12`，`repeat=3 -> 36/36`
  - `codebase_community`：`12/12`，`repeat=3 -> 36/36`
  - `superhero`：`12/12`，`repeat=3 -> 36/36`
  - 合计单轮 `72/72`，`repeat=3` 累计 `216/216`
