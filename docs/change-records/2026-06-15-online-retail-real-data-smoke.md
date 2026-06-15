# 2026-06-15 Online Retail 真实数据 smoke

## 改动内容

- 新增 `resources/semantic/online_retail.json`，为 UCI Online Retail 交易数据配置正式语义目录。
- 新增 `scripts/real_business_online_retail_smoke.py`，自动下载公开数据、转换 CSV、导入 SQLite 并执行受控 SQL 查询。
- 新增 `tests/test_real_business_online_retail_catalog.py`，离线验证该语义目录可被当前 SQL builder 正常生成查询计划。
- 增强通用语义后处理：补齐显式年份时间范围、显式分组维度、趋势月维度和符号操作符别名。
- 新增 `resources/semantic_plugins/online_retail.json`，把 Online Retail 的国家中文别名作为数据集插件注入，避免污染通用底座。
- 新增 `scripts/semantic_eval_runner.py` 与 `resources/eval_cases/online_retail*.jsonl`，支持批量问题评估。

## 改动原因

项目原有 `sales` 目录更偏示例数据。为了用真实业务数据验证链路，需要引入公开、可复现的交易明细数据，并避免把原始大文件提交到仓库。

数据源：UCI Machine Learning Repository - Online Retail，Business 领域，541,909 条线上零售交易，CC BY 4.0。

## 涉及文件

- `resources/semantic/online_retail.json`
- `scripts/real_business_online_retail_smoke.py`
- `src/qsql/semantic_service.py`
- `src/qsql/semantic_postprocessor.py`
- `scripts/semantic_eval_runner.py`
- `resources/semantic_plugins/online_retail.json`
- `resources/eval_cases/online_retail.jsonl`
- `resources/eval_cases/online_retail_extended.jsonl`
- `tests/test_real_business_online_retail_catalog.py`
- `tests/test_semantic_postprocessor.py`
- `tests/test_semantic_eval_runner.py`

## 验证方式

```bash
python -m pytest tests/test_real_business_online_retail_catalog.py
ruff check scripts/real_business_online_retail_smoke.py tests/test_real_business_online_retail_catalog.py
python scripts/real_business_online_retail_smoke.py
python scripts/semantic_eval_runner.py --dataset-id online_retail --cases resources/eval_cases/online_retail.jsonl --sqlite-db resources/uploads/online_retail/online_retail.sqlite3
python scripts/semantic_eval_runner.py --dataset-id online_retail --cases resources/eval_cases/online_retail_extended.jsonl --sqlite-db resources/uploads/online_retail/online_retail.sqlite3
```

原始数据缓存路径为 `resources/uploads/online_retail/`，该目录不进入版本库。

自然语言评估样例：

- 2011年各国家有效销售额是多少？
- 2011年英国每月有效销售额趋势怎么样？
- 2011年各国家有效订单数是多少？
- 2011年德国有效销量是多少？
- 各国家销售额是多少？

初始 5 条手工样例结果：4 条 ready，1 条因缺少时间范围进入 clarification，0 条执行错误。

30 条批量评估结果：

- total=30
- ok=30
- failed=0
- ready=27
- clarification=3
- error=0

53 条分层评估结果：

- L1 基础汇总/单条件
- L2 单维拆分/趋势/排行
- L3 复合条件/多维拆分/多条件趋势
- L4 合理澄清（缺时间范围、多指标同时查询）

最终结果：

- total=53
- ok=53
- failed=0
- ready=45
- clarification=8
- error=0

53 条分层评估稳定性复跑（repeat=2）：

- aggregate total=106
- aggregate ok=106
- aggregate failed=0
- aggregate ready=90
- aggregate clarification=16
- aggregate error=0

按层统计：

- L1: 20/20
- L2: 30/30
- L3: 40/40
- L4: 16/16
