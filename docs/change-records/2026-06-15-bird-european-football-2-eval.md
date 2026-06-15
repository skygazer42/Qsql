# 2026-06-15 BIRD Mini-Dev european_football_2 多表评测接入

## 改了什么

- 新增 `resources/semantic/bird_european_football_2.json`
  - 为 BIRD Mini-Dev 的 `european_football_2` 库定义受控语义目录
  - 以 `Match` 事实表为中心，接入 `Country`、`League` 和 `Team`
  - 将同一物理表 `Team` 拆成 `home_team_dim` / `away_team_dim` 两个语义角色
  - 显式声明 `Match -> Country`、`Match -> League`、`Match -> home_team_dim`、`Match -> away_team_dim` 安全 join path
- 新增 `resources/semantic_plugins/bird_european_football_2.json`
  - 补 `Premier League -> England Premier League`
  - 补 `La Liga -> Spain LIGA BBVA`
  - 补 `Barcelona -> FC Barcelona`、`Real Madrid -> Real Madrid CF`
- 新增 `resources/semantic_examples/bird_european_football_2.jsonl`
  - 补联赛赛季统计、双角色过滤、双角色 group_by、多指标 season 分析 few-shot 示例
- 新增 `resources/eval_cases/bird_european_football_2.jsonl`
  - 落 12 条多表 BI 子集评测题
  - 覆盖国家/联赛/赛季/轮次/主队/客队六个维度
  - 覆盖 3 条双角色问题和 2 条多指标问题
- 新增 [tests/test_bird_european_football_2_catalog.py](/data/temp/qsql/tests/test_bird_european_football_2_catalog.py)
  - 覆盖 `League + HomeTeam + AwayTeam` 三跳 SQL
  - 覆盖双角色值归一化
- 修改 [src/qsql/semantic_postprocessor.py](/data/temp/qsql/src/qsql/semantic_postprocessor.py)
  - 当同一个 alias 在多个维度中复用时，plugin 不再盲目自动追加缺失 filter
  - 已有 filter 会优先按自身值归一化，而不是被题面里的另一个最长 alias 覆盖
- 修改 [tests/test_semantic_postprocessor.py](/data/temp/qsql/tests/test_semantic_postprocessor.py)
  - 新增“多 alias 命中时保留已有 role filter”
  - 新增“共享 alias 不自动补到另一个 role 维度”的通用回归测试
- 修改 [src/qsql/sql_builder.py](/data/temp/qsql/src/qsql/sql_builder.py)
  - 渲染 SQL 前会对 filters 做确定序排序
  - 解决同一语义下 SQL 文本因 filter 顺序抖动而导致的稳定性波动
- 修改 [tests/test_sql_builder_join.py](/data/temp/qsql/tests/test_sql_builder_join.py)
  - 新增 filter 顺序变化下 SQL 输出稳定的回归测试
- 修改 [docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md](/data/temp/qsql/docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md)
  - 同步八套 harder 子集的当前 EX 结果与累计准确率

## 为什么改

- `european_football_2` 这套库的价值不在表数，而在**同一物理表的多角色复用**：
  - `Match.home_team_api_id` 和 `Match.away_team_api_id` 都连到 `Team.team_api_id`
  - 如果底座不能区分主队/客队角色，多表 join 虽然能跑，语义会串位
- 这次 EX 首轮就暴露了一个很典型的通用问题：
  - 问题里同时出现 `Barcelona` / `Real Madrid` 这类值时，plugin 会把同一个球队名补到两个角色维度
  - 同一语义下 filter 顺序偶尔抖动，还会让 `repeat=3` 的 SQL 文本不稳定
- 所以这轮不是单纯接一个数据集，而是顺手把**role-aware value mapping** 和 **stable SQL rendering** 补成通用能力。

## 如何验证

- 定向单测：
  - `.venv/bin/python -m pytest tests/test_bird_european_football_2_catalog.py tests/test_semantic_postprocessor.py::test_postprocessor_prefers_existing_filter_value_when_multiple_aliases_match tests/test_semantic_postprocessor.py::test_postprocessor_does_not_auto_append_ambiguous_role_filter tests/test_sql_builder_join.py::test_build_query_execution_plan_is_stable_when_filter_order_changes -q`
- 真实 SQLite EX 评测：
  - `.venv/bin/python scripts/semantic_eval_runner.py --dataset-id bird_european_football_2 --cases resources/eval_cases/bird_european_football_2.jsonl --sqlite-db resources/uploads/bird_mini_dev/minidev/MINIDEV/dev_databases/european_football_2/european_football_2.sqlite --row-limit 40`
  - `.venv/bin/python scripts/semantic_eval_runner.py --dataset-id bird_european_football_2 --cases resources/eval_cases/bird_european_football_2.jsonl --sqlite-db resources/uploads/bird_mini_dev/minidev/MINIDEV/dev_databases/european_football_2/european_football_2.sqlite --row-limit 40 --repeat 3`
- 全量回归：
  - `.venv/bin/python -m pytest tests/`
  - `ruff check src/ tests/`

## 结果

- `bird_european_football_2` 12 条多表 BI 子集首轮 `12/12` 通过，全部 `EX` 命中。
- `repeat=3` 为 `36/36`，`stability_rate=1.0000`。
- 当前八套 BIRD harder 子集累计：
  - `debit_card_specializing`：`12/12`，`repeat=3 -> 36/36`
  - `student_club`：`12/12`，`repeat=3 -> 36/36`
  - `financial`：`12/12`，`repeat=3 -> 36/36`
  - `formula_1`：`12/12`，`repeat=3 -> 36/36`
  - `codebase_community`：`12/12`，`repeat=3 -> 36/36`
  - `superhero`：`12/12`，`repeat=3 -> 36/36`
  - `california_schools`：`12/12`，`repeat=3 -> 36/36`
  - `european_football_2`：`12/12`，`repeat=3 -> 36/36`
  - 合计单轮 `96/96`，`repeat=3` 累计 `288/288`
