# Controlled Join Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 QSQL 增加基于 catalog 预声明关系的受控多表 join，先支持事实表到维表的确定性 join。

**Architecture:** 在 `SemanticCatalog` 中新增 `entities` 和 `relationships`，由 `sql_builder` 以指标所在表为锚点，沿预声明关系图寻找 join path。只允许命中 catalog 中存在的路径；找不到路径时明确报错，不做隐式兜底。

**Tech Stack:** Python, Pydantic v2, pytest

---

### Task 1: 锁定最小支持边界

**Files:**
- Modify: `docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md`
- Modify: `docs/plans/2026-06-15-controlled-join-implementation-plan.md`

**Step 1: 定义最小实现范围**

- 支持单指标查询
- 支持一个事实表连接多个维表
- 支持时间维、filter、group by 跨表
- 不支持多事实表
- 不支持未声明路径自动猜 join

**Step 2: 明确失败策略**

- 缺失实体定义：加载期失败
- 缺失关系定义：SQL 构建期失败
- 关系链存在但方向/列非法：加载期失败

### Task 2: 先写失败测试

**Files:**
- Create: `tests/test_sql_builder_join.py`

**Step 1: 写 join path 成功测试**

- catalog 含 `sales_orders` 与 `customers`
- `order_amount` 在 `sales_orders`
- `customer_city` 在 `customers`
- `sales_orders.customer_id -> customers.id` 由 catalog 显式声明
- 断言 SQL 生成 `LEFT JOIN`

**Step 2: 写未声明路径拒绝测试**

- 复用相同 catalog，但不声明 relationship
- 断言构建时报错

**Step 3: 运行单测并确认先失败**

Run: `python -m pytest tests/test_sql_builder_join.py -q`

### Task 3: 最小实现 entities / relationships 与 join builder

**Files:**
- Modify: `src/qsql/schemas.py`
- Modify: `src/qsql/sql_builder.py`
- Modify: `src/qsql/semantic_agent.py`
- Modify: `src/qsql/semantic_draft_generator.py`

**Step 1: schema 增加实体/关系模型**

- `SemanticEntityDefinition`
- `SemanticRelationshipDefinition`
- `SemanticCatalog` 增加 `entities` / `relationships`

**Step 2: catalog 加载期校验**

- entity 必须引用已存在语义表
- relationship 必须引用已存在 entity
- relationship 两端不能落在同一 entity

**Step 3: builder 确定性 join 规划**

- 识别时间维、filter、group_by 涉及的表
- 以 metric.table_key 为锚点做 BFS 找 path
- 生成带别名的 join SQL
- 未命中 path 时报错

**Step 4: 语义提示补充**

- parser prompt 暴露 entities / relationships 摘要

### Task 4: 回归验证

**Files:**
- Test: `tests/test_sql_builder_join.py`
- Test: `tests/test_semantic_query_pipeline.py`

**Step 1: 运行新增单测**

Run: `python -m pytest tests/test_sql_builder_join.py -q`

**Step 2: 运行关联回归**

Run: `python -m pytest tests/test_semantic_query_pipeline.py -q`

**Step 3: 运行静态检查**

Run: `ruff check src/qsql/schemas.py src/qsql/sql_builder.py src/qsql/semantic_agent.py src/qsql/semantic_draft_generator.py tests/test_sql_builder_join.py tests/test_semantic_query_pipeline.py`
