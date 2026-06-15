# 2026-06-15 BIRD Mini-Dev codebase_community 多表评测接入

## 改了什么

- 新增 `resources/semantic/bird_codebase_community.json`
  - 为 BIRD Mini-Dev 的 `codebase_community` 库定义受控语义目录
  - 覆盖 `badges` / `posts` / `comments` / `votes` 四类事实表
  - 显式拆分 `badge_user`、`owner_user`、`commenter_user`、`comment_post`、`vote_post` 等语义角色
  - 显式声明 `comments -> posts -> owner_user`、`comments -> commenter_user`、`votes -> posts -> owner_user` 等安全 join path
- 新增 `resources/semantic_plugins/bird_codebase_community.json`
  - 补 `Teacher` / `Student` / `Supporter` / `Editor` 等 badge 名映射
  - 补 `question/questions -> 1`、`answer/answers -> 2` 的 post type 映射
- 新增 `resources/semantic_examples/bird_codebase_community.jsonl`
  - 补 badge group_by、post group_by、comment multi-metric、vote multi-dimension few-shot 示例
- 新增 `resources/eval_cases/bird_codebase_community.jsonl`
  - 落 12 条多表 BI 子集评测题，覆盖 badge / post / comment / vote 四类查询
- 新增 [tests/test_bird_codebase_community_catalog.py](/data/temp/qsql/tests/test_bird_codebase_community_catalog.py)
  - 覆盖 comments -> posts -> owner_user 多跳 SQL
  - 覆盖 votes -> posts -> owner_user 多跳 SQL
  - 覆盖 badge 名和 post type 的底座归一化
- 修改 [docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md](/data/temp/qsql/docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md)
  - 同步五套 harder 子集的当前 EX 结果与累计准确率

## 为什么改

- 在 `formula_1` 之后，需要一个**更真实的社区内容分析库**来继续压测底座。
- `codebase_community` 相比星型维度库更接近真实业务：
  - 同时存在 `posts`、`comments`、`votes`、`badges` 多张事实表
  - `comments` 与 `votes` 都需要经 `posts` 再连到 `owner_user`
  - `comments` 还额外有 `commenter_user` 角色，天然能检验 role 维度是否串位
- 这套库依然可以保持在受控 BI 问数边界内，不需要放开自连接和开放 SQL 编程题。

## 如何验证

- 单测：
  - `.venv/bin/python -m pytest tests/test_bird_codebase_community_catalog.py`
- 真实 SQLite EX 评测：
  - `.venv/bin/python scripts/semantic_eval_runner.py --dataset-id bird_codebase_community --cases resources/eval_cases/bird_codebase_community.jsonl --sqlite-db resources/uploads/bird_mini_dev/minidev/MINIDEV/dev_databases/codebase_community/codebase_community.sqlite --row-limit 40`
  - `.venv/bin/python scripts/semantic_eval_runner.py --dataset-id bird_codebase_community --cases resources/eval_cases/bird_codebase_community.jsonl --sqlite-db resources/uploads/bird_mini_dev/minidev/MINIDEV/dev_databases/codebase_community/codebase_community.sqlite --row-limit 40 --repeat 3`
- 全量回归：
  - `.venv/bin/python -m pytest tests/`
  - `ruff check src/ tests/`

## 结果

- `codebase_community` 12 条多表 BI 子集首轮 `12/12` 通过，全部 `EX` 命中。
- `repeat=3` 为 `36/36`，`stability_rate=1.0000`。
- 当前五套 BIRD harder 子集累计：
  - `debit_card_specializing`：`12/12`，`repeat=3 -> 36/36`
  - `student_club`：`12/12`，`repeat=3 -> 36/36`
  - `financial`：`12/12`，`repeat=3 -> 36/36`
  - `formula_1`：`12/12`，`repeat=3 -> 36/36`
  - `codebase_community`：`12/12`，`repeat=3 -> 36/36`
  - 合计单轮 `60/60`，`repeat=3` 累计 `180/180`
