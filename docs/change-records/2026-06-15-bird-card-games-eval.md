# 2026-06-15 BIRD Mini-Dev card_games 多表评测接入

## 改了什么

- 新增 `resources/semantic/bird_card_games.json`
  - 为 BIRD Mini-Dev 的 `card_games` 库定义受控语义目录
  - 接入 `cards`、`foreign_data`、`legalities`、`rulings`、`sets`、`set_translations`
  - 明确只走四类安全链路：
    - `foreign_data -> cards -> sets`
    - `legalities -> cards -> sets`
    - `rulings -> cards -> sets`
    - `set_translations -> sets`
  - 新增 `translated_card_count`、`translated_set_count`、`legal_card_count`、`ruling_count`、`ruled_card_count`
- 新增 `resources/semantic_plugins/bird_card_games.json`
  - 补 `Brazilian Portuguese -> Portuguese (Brazil)`
  - 补 `commander block -> Commander`
  - 补 `banned/legal/restricted`
  - 补 `mythic rare`、`white border`、`black border`
  - 补 `story spotlight cards`、`promo cards`
- 新增 `resources/semantic_examples/bird_card_games.jsonl`
  - 补 `legalities`、`foreign_data`、`set_translations`、`rulings` 四类根表的 few-shot
  - 补 `ruling_count + ruled_card_count` 多指标示例
- 新增 `resources/eval_cases/bird_card_games.jsonl`
  - 落 12 条多表 BI 子集评测题
  - 覆盖 3 条 summary、7 条 group by、2 条 multi-metric
  - 覆盖 `legalities` / `foreign_data` / `set_translations` / `rulings` / `cards` 五类根表
- 新增 [tests/test_bird_card_games_catalog.py](/data/temp/qsql/tests/test_bird_card_games_catalog.py)
  - 覆盖 `foreign_data -> cards -> sets`
  - 覆盖 `legalities -> cards -> sets`
  - 覆盖 `set_translations -> sets`
  - 覆盖 `translated_set_count` 的值归一化
  - 覆盖 `card_count + converted_mana_cost_avg` 多指标 ready 路径
- 修改 [docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md](/data/temp/qsql/docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md)
  - 同步十套 harder 子集的累计 EX 结果

## 为什么改

- `card_games` 这套库表面上是星型，但真实难点是：
  - `cards` 同时挂了 `foreign_data`、`legalities`、`rulings`
  - `sets` 同时挂了 `cards`、`set_translations`
- 当前底座明确限制只走 **FK -> PK 安全 join path**，不允许为了做题把 `cards -> legalities`、`sets -> set_translations` 这类反向 one-to-many 路径硬放开，否则就会直接踩 fan-out。
- 所以这轮的重点不是“把更多表硬 join 上”，而是验证**通用底座是否能在不放松 join 安全约束的前提下，重新选择正确的根表与指标锚点**：
  - 赛制问题锚到 `legalities`
  - 外语卡问题锚到 `foreign_data`
  - 系列翻译问题锚到 `set_translations`
  - 裁定问题锚到 `rulings`
- 这比单纯补一个数据集更重要，因为它说明现在的 generic base 已经能表达“同一主题下多根表分治”的方案，而不是靠为某个库开后门。

## 如何验证

- 定向单测：
  - `.venv/bin/python -m pytest tests/test_bird_card_games_catalog.py -q`
- 真实 SQLite EX 评测：
  - `.venv/bin/python scripts/semantic_eval_runner.py --dataset-id bird_card_games --cases resources/eval_cases/bird_card_games.jsonl --sqlite-db resources/uploads/bird_mini_dev/minidev/MINIDEV/dev_databases/card_games/card_games.sqlite --row-limit 40`
  - `.venv/bin/python scripts/semantic_eval_runner.py --dataset-id bird_card_games --cases resources/eval_cases/bird_card_games.jsonl --sqlite-db resources/uploads/bird_mini_dev/minidev/MINIDEV/dev_databases/card_games/card_games.sqlite --row-limit 40 --repeat 3`
- 全量回归：
  - `find src -type d -name '__pycache__' -prune -exec rm -rf {} + && find src -type f -name '*.pyc' -delete && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/`
  - `ruff check src/ tests/`

## 结果

- `bird_card_games` 12 条多表 BI 子集首轮 `12/12` 通过，全部 `EX` 命中。
- `repeat=3` 为 `36/36`，`stability_rate=1.0000`。
- 当前十套 BIRD harder 子集累计：
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
  - 合计单轮 `120/120`，`repeat=3` 累计 `360/360`
