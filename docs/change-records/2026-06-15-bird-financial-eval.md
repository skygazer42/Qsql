# 2026-06-15 BIRD Mini-Dev financial 多表评测接入

## 改了什么

- 新增 `resources/semantic/bird_financial.json`
  - 为 BIRD Mini-Dev 的 `financial` 库定义受控语义目录
  - 覆盖 `client` / `account` / `loan` / `trans` / `card` / `disp` / `district`
  - 显式拆分 `client_district` 与 `account_district` 两个语义角色，避免同一物理表在多跳 join 中串位
  - 显式声明 `loan -> account`、`trans -> account`、`card -> disp -> client`、`disp -> account` 等安全 join path
- 新增 `resources/semantic_plugins/bird_financial.json`
  - 补 `North Bohemia` / `East Bohemia` / `Sokolov` / `weekly issuance` / `gold` / `classic` / `OWNER` / `DISPONENT` 等值映射
- 新增 `resources/semantic_examples/bird_financial.jsonl`
  - 补 client summary、loan/account join、transaction multi-metric、card 多跳 join few-shot 示例
- 新增 `resources/eval_cases/bird_financial.jsonl`
  - 落 12 条多表 BI 子集评测题，覆盖 client/account/loan/trans/card 五类查询
- 新增 [tests/test_bird_financial_catalog.py](/data/temp/qsql/tests/test_bird_financial_catalog.py)
  - 覆盖 loan->account->district、card->disp->client->district 多跳 SQL
  - 覆盖 plugin 只补当前 metric 支持维度、英文实体词不误判多指标、alias 值归一化、region/district 冲突修复
- 修改 [src/qsql/semantic_postprocessor.py](/data/temp/qsql/src/qsql/semantic_postprocessor.py)
  - plugin 值映射只对当前 metric 可支持维度生效
  - 题面命中 alias 时，允许直接纠正已有 filter 值，例如 `weekly issuance -> POPLATEK TYDNE`
  - 新增冲突 filter 清理，避免 region/district 角色串位导致 fan-out 或空结果
  - 多指标误判改为“强指标词”识别，不再把 `accounts` / `clients` 这类实体词误伤为第二指标
- 修改 [src/qsql/semantic_service.py](/data/temp/qsql/src/qsql/semantic_service.py)
  - metric clarification options 与 postprocessor 共享同一套强指标词判定

## 为什么改

- 前两套 BIRD 子集已经证明了一般多表场景可行，但 `financial` 更接近真实 Text2SQL 难点：
  - 同时存在 `client` 角色链和 `account` 角色链
  - `district` 被两个业务角色复用，最容易暴露维度串位
  - `card -> disp -> client` 与 `trans -> account` 两类多跳路径并存
- 首轮接入时暴露了几个底座问题：
  - plugin 会把同一个 alias 同时补到多个角色维度上，导致 fan-out
  - `accounts` 这类实体名会误触发多指标澄清
  - parser 已经选中正确维度时，alias 仍可能没有把 filter 值归一到 DB 真值

## 如何验证

- 单测：
  - `.venv/bin/python -m pytest tests/test_bird_financial_catalog.py`
  - `.venv/bin/python -m pytest tests/test_semantic_postprocessor.py tests/test_bird_debit_card_catalog.py tests/test_bird_student_club_catalog.py tests/test_bird_financial_catalog.py tests/test_semantic_eval_runner.py tests/test_sql_builder_join.py tests/test_real_business_online_retail_catalog.py`
- Lint：
  - `ruff check src/qsql/semantic_postprocessor.py src/qsql/semantic_service.py tests/test_bird_financial_catalog.py`
  - `ruff check src/ tests/`
- 真实 SQLite EX 评测：
  - `.venv/bin/python scripts/semantic_eval_runner.py --dataset-id bird_financial --cases resources/eval_cases/bird_financial.jsonl --sqlite-db resources/uploads/bird_mini_dev/minidev/MINIDEV/dev_databases/financial/financial.sqlite --row-limit 40`
  - `.venv/bin/python scripts/semantic_eval_runner.py --dataset-id bird_financial --cases resources/eval_cases/bird_financial.jsonl --sqlite-db resources/uploads/bird_mini_dev/minidev/MINIDEV/dev_databases/financial/financial.sqlite --row-limit 40 --repeat 3`

## 结果

- `financial` 12 条多表 BI 子集首轮 `12/12` 通过，全部 `EX` 命中。
- 复跑 `repeat=3` 为 `36/36`，`stability_rate=1.0000`。
- 当前三套 BIRD harder 子集累计：
  - `debit_card_specializing`：`12/12`，`repeat=3 -> 36/36`
  - `student_club`：`12/12`，`repeat=3 -> 36/36`
  - `financial`：`12/12`，`repeat=3 -> 36/36`
