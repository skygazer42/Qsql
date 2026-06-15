# 2026-06-15 受控多表 Join（P0-1）最小实现

## 改了什么

- 在 `SemanticCatalog` 中新增 `entities` 和 `relationships` 结构，用于显式声明允许的 join 路径。
- `sql_builder` 从“只支持单表宽表”升级为“按 catalog 关系图做确定性 join 规划”。
- `semantic_agent` prompt 增加实体和关系摘要，便于模型理解跨表维度来源。
- `semantic_draft_generator` 会从元数据中的主外键关系自动生成 `entities/relationships` 草稿。
- 新增 `tests/test_sql_builder_join.py`，覆盖：
  - 声明过的 join path 可以生成 `LEFT JOIN`
  - 未声明的 join path 明确拒绝

## 为什么改

`docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md` 的 P0-1 明确要求把能力从单表宽表扩到受控多表 join。当前 QSQL 的核心价值不是让模型自由写 SQL，而是让模型只选语义对象、由后端确定性生成 SQL，所以 join 也必须走 catalog 预声明路径，不能放开给 LLM 猜。

## 涉及文件

- `src/qsql/schemas.py`
- `src/qsql/sql_builder.py`
- `src/qsql/semantic_agent.py`
- `src/qsql/semantic_draft_generator.py`
- `tests/test_sql_builder_join.py`
- `tests/test_semantic_draft_generator.py`

## 当前边界

- 已支持：单指标查询下，事实表到维表的显式 join path
- 已支持：时间维、filter、group by 跨表
- 未支持：多事实表、同表自连接、fan-out/chasm 防护、执行反馈重试

## 如何验证

```bash
.venv/bin/python -m pytest tests/test_sql_builder_join.py tests/test_semantic_query_pipeline.py tests/test_semantic_draft_generator.py -q
ruff check src/qsql/schemas.py src/qsql/sql_builder.py src/qsql/semantic_agent.py src/qsql/semantic_draft_generator.py tests/test_sql_builder_join.py tests/test_semantic_query_pipeline.py tests/test_semantic_draft_generator.py
```

本次验证结果：

- `14 passed`
- `ruff check` 通过
