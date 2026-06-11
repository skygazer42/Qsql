# Semantic Catalog

老主接口按数据集加载语义目录：

- 路径：`resources/semantic/<dataset_id>.json`
- 生成 SQL：`GET /api/v0/generate_sql?dataset_id=<dataset_id>&question=<question>`
- 执行搜索：`POST /api/v0/search`

内置示例：

- `resources/semantic/sales.json`

最小结构示例：

```json
{
  "catalog_version": "2026-06-11",
  "dataset_id": "sales",
  "tables": [
    {
      "key": "sales_order_wide",
      "label": "销售订单宽表",
      "physical_table": "sales_orders",
      "description": "订单聚合分析统一宽表",
      "default_time_dimension_key": "order_date"
    }
  ],
  "metrics": [
    {
      "key": "order_amount",
      "label": "订单金额",
      "table_key": "sales_order_wide",
      "field": "amount",
      "aggregation": "sum",
      "supported_dimension_keys": ["city", "order_date"],
      "default_time_dimension_key": "order_date",
      "allowed_version_keys": ["won_only"]
    }
  ],
  "dimensions": [
    {
      "key": "city",
      "label": "城市",
      "table_key": "sales_order_wide",
      "field": "city_name",
      "kind": "categorical",
      "operators": ["eq", "in"]
    },
    {
      "key": "order_date",
      "label": "下单日期",
      "table_key": "sales_order_wide",
      "field": "order_date",
      "kind": "time",
      "operators": ["between", "gte", "lte"]
    }
  ],
  "aliases": [
    {
      "alias": "成交金额",
      "target_type": "metric",
      "target_key": "order_amount"
    }
  ],
  "metric_versions": [
    {
      "key": "won_only",
      "label": "已赢单口径",
      "metric_key": "order_amount",
      "filters": [
        {
          "dimension_key": "city",
          "operator": "eq",
          "value": "杭州"
        }
      ]
    }
  ]
}
```

说明：

- `tables` 是正式语义层里的来源宽表定义，`metrics/dimensions` 只引用 `table_key`，不再重复散落物理表名。
- `metric_versions` 承载业务口径过滤条件，避免把口径规则继续堆在 prompt 里。
- 当前重构分支只接受这套新结构，不再兼容旧的平铺 `table` 字段格式。
- metadata 自动生成的草稿会写到 `resources/semantic_drafts/<dataset_id>.json`，不会直接覆盖正式目录。
- 可通过脚本生成草稿：
  - `python scripts/generate_semantic_draft.py --dataset-id <dataset_id>`
