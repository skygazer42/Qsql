# Semantic Voting And Feedback Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 QSQL 的受控语义解析链路增加 draft 层多候选投票，以及空结果后的受控反馈重试。

**Architecture:** 由 `SemanticQueryAgent` 负责生成多个 `SemanticQueryDraft` 候选，`SemanticQueryService` 负责对候选做确定性排序和选择。执行反馈不回传给 LLM 改 SQL，只在已生成的 draft 候选中切换，若仍为空则转澄清。

**Tech Stack:** Python, pydantic-ai, pytest

---

### Task 1: 锁定最小支持边界

**Files:**
- Modify: `docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md`
- Modify: `docs/plans/2026-06-15-semantic-voting-feedback-implementation-plan.md`

**Step 1: 定义最小范围**

- 支持 `candidate_count > 1`
- 支持 parser 显式提供 `parse_candidates`
- 支持服务层对候选做确定性排序
- 支持空结果时尝试下一个 ready 候选
- 所有候选都空时转澄清

**Step 2: 明确暂不做**

- 不做自由 SQL 修复
- 不做多轮 LLM 反思
- 不做 selection-agent 新模型
- 不做路由级复杂分数学习

### Task 2: 先写失败测试

**Files:**
- Create: `tests/test_semantic_voting_feedback.py`

**Step 1: 写多候选投票测试**

- fake parser 返回三个候选
- 两个候选语义一致，一个不同
- 断言服务选择多数候选

**Step 2: 写空结果切换候选测试**

- 主候选执行结果为空
- 次候选执行结果非空
- 断言返回次候选

**Step 3: 写所有候选都空时转澄清测试**

- 所有 ready 候选都执行为空
- 断言返回 `clarification`

**Step 4: 跑测试确认先失败**

Run: `.venv/bin/python -m pytest tests/test_semantic_voting_feedback.py -q`

### Task 3: 最小实现

**Files:**
- Modify: `src/qsql/semantic_agent.py`
- Modify: `src/qsql/semantic_service.py`
- Modify: `app.py`

**Step 1: agent 支持多候选采样**

- 新增 `parse_candidates(...)`
- 支持 `model_settings` 覆盖采样温度

**Step 2: service 实现候选排序**

- 统一归一化 candidate signature
- 按 exact signature 频次 + 字段多数一致度排序
- 选择主候选

**Step 3: service 实现执行反馈**

- 新增 `prepare_query_with_feedback(...)`
- 主候选为空时尝试下一个 ready 候选
- 全部为空时转澄清

**Step 4: search 链路接入**

- 只在会执行 SQL 的 `/api/v0/search` 路径使用反馈
- `generate_sql` 继续只走 `prepare_query`

### Task 4: 回归验证

**Files:**
- Test: `tests/test_semantic_voting_feedback.py`
- Test: `tests/test_semantic_query_pipeline.py`
- Test: `tests/test_app_semantic_migration.py`

**Step 1: 跑新增测试**

Run: `.venv/bin/python -m pytest tests/test_semantic_voting_feedback.py -q`

**Step 2: 跑相关回归**

Run: `.venv/bin/python -m pytest tests/test_semantic_query_pipeline.py tests/test_app_semantic_migration.py -q`

**Step 3: 跑静态检查**

Run: `ruff check src/qsql/semantic_agent.py src/qsql/semantic_service.py app.py tests/test_semantic_voting_feedback.py tests/test_semantic_query_pipeline.py tests/test_app_semantic_migration.py`
