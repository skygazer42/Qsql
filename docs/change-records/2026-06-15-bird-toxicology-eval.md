# 2026-06-15 BIRD Mini-Dev toxicology 多表评测接入

## 改了什么

- 新增 `resources/semantic/bird_toxicology.json`
  - 为 BIRD Mini-Dev 的 `toxicology` 库定义受控语义目录
  - 以 `molecule`、`atom`、`bond`、`connected` 四张表构建图式多表 BI 子集
  - 将同一物理表 `atom` 拆成 `atom_source_dim` / `atom_target_dim` 两个语义角色
  - 显式声明 `connected -> atom_source_dim`、`connected -> atom_target_dim`、`connected -> bond -> molecule` 安全 join path
- 新增 `resources/semantic_plugins/bird_toxicology.json`
  - 补 `positive/negative -> +/-`
  - 补 `single/double/triple bond -> -/=/#`
  - 补 `carbon/oxygen/nitrogen/chlorine/bromine/hydrogen -> c/o/n/cl/br/h`
- 新增 `resources/semantic_examples/bird_toxicology.jsonl`
  - 补连接边统计、双角色过滤、多指标 group by few-shot 示例
- 新增 `resources/eval_cases/bird_toxicology.jsonl`
  - 落 12 条多表 BI 子集评测题
  - 覆盖 `molecule_label`、`atom_element`、`bond_type`、`atom_source_element`、`atom_target_element`
  - 覆盖 2 条多指标问题和 3 条图边连接统计问题
- 新增 [tests/test_bird_toxicology_catalog.py](/data/temp/qsql/tests/test_bird_toxicology_catalog.py)
  - 覆盖 `connected -> atom(source) -> atom(target) -> bond -> molecule` 多跳 SQL
  - 覆盖 `bond_type`、角色原子元素、标签值归一化
  - 覆盖多指标问句不会被误打回澄清
- 修改 `resources/semantic/bird_toxicology.json`
  - 为 `connected_bond_count`、`connected_source_atom_count`、`atom_molecule_count` 补英文复合指标 alias
  - 让 `connected bond count`、`source atom count`、`distinct molecule count` 这些长词优先匹配，避免被短词 `bond count / atom count / molecule count` 误伤
- 修改 [docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md](/data/temp/qsql/docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md)
  - 同步九套 harder 子集的当前 EX 结果与累计准确率

## 为什么改

- `toxicology` 的价值不在表数，而在**图边式多表连接 + 同表双角色**：
  - `connected.atom_id` 和 `connected.atom_id2` 都连到 `atom.atom_id`
  - `connected.bond_id` 再连到 `bond`，最后再连到 `molecule`
- 这套库能检验底座是否真的能承受：
  - 同一事实表上双角色维度过滤
  - 图边粒度的 group by / 多指标
  - 通过下游表回溯上游标签过滤
- 首轮 EX 暴露的问题也很典型：
  - parser 已经能给出正确的 `metric_keys`
  - 但 postprocessor 的强指标词检测只命中了短词 `bond count / atom count / molecule count`
  - 导致本来正确的多指标草稿被误判成“需要用户二选一”
- 这次没有改底层逻辑，而是把**复合指标 alias 契约**补完整，让长指标词先命中，避免通用多指标澄清规则误伤。

## 如何验证

- 定向单测：
  - `.venv/bin/python -m pytest tests/test_bird_toxicology_catalog.py -q`
- 真实 SQLite EX 评测：
  - `.venv/bin/python scripts/semantic_eval_runner.py --dataset-id bird_toxicology --cases resources/eval_cases/bird_toxicology.jsonl --sqlite-db resources/uploads/bird_mini_dev/minidev/MINIDEV/dev_databases/toxicology/toxicology.sqlite --row-limit 40`
  - `.venv/bin/python scripts/semantic_eval_runner.py --dataset-id bird_toxicology --cases resources/eval_cases/bird_toxicology.jsonl --sqlite-db resources/uploads/bird_mini_dev/minidev/MINIDEV/dev_databases/toxicology/toxicology.sqlite --row-limit 40 --repeat 3`
- 全量回归：
  - `.venv/bin/python -m pytest tests/`
  - `ruff check src/ tests/`

## 结果

- `bird_toxicology` 12 条多表 BI 子集首轮 `12/12` 通过，全部 `EX` 命中。
- `repeat=3` 为 `36/36`，`stability_rate=1.0000`。
- 当前九套 BIRD harder 子集累计：
  - `debit_card_specializing`：`12/12`，`repeat=3 -> 36/36`
  - `student_club`：`12/12`，`repeat=3 -> 36/36`
  - `financial`：`12/12`，`repeat=3 -> 36/36`
  - `formula_1`：`12/12`，`repeat=3 -> 36/36`
  - `codebase_community`：`12/12`，`repeat=3 -> 36/36`
  - `superhero`：`12/12`，`repeat=3 -> 36/36`
  - `california_schools`：`12/12`，`repeat=3 -> 36/36`
  - `european_football_2`：`12/12`，`repeat=3 -> 36/36`
  - `toxicology`：`12/12`，`repeat=3 -> 36/36`
  - 合计单轮 `108/108`，`repeat=3` 累计 `324/324`
