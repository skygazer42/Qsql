# 2026-06-15 语义多候选投票与空结果反馈（P0-2）

## 改了什么

- `SemanticQueryAgent` 新增 `parse_candidates(...)`，支持按配置生成多个 `SemanticQueryDraft`。
- `SemanticQueryService` 新增候选投票逻辑，候选、投票信息和选中索引用 Pydantic 模型承载。
- `SemanticQueryService.prepare_query_with_feedback(...)` 支持在执行结果为空时切换到下一个 ready 候选。
- `/api/v0/search` 接入执行反馈；`/api/v0/generate_sql` 仍然只生成受控 SQL，不触发数据库执行。
- `AppConfigModel` 增加：
  - `semantic_candidate_count`
  - `semantic_candidate_sampling_temperature`
  - `semantic_feedback_retry_limit`

## 为什么改

路线图 P0-2 要把单次解析升级为“多候选 + 执行反馈”。QSQL 的约束是不能让 LLM 自由改 SQL，所以这次只在 `SemanticQueryDraft` 层投票和切换候选，最终 SQL 仍由 `sql_builder` 确定性生成。

## 涉及文件

- `app.py`
- `src/qsql/schemas.py`
- `src/qsql/semantic_agent.py`
- `src/qsql/semantic_service.py`
- `tests/test_semantic_voting_feedback.py`
- `tests/test_app_semantic_migration.py`

## 当前边界

- 已支持：exact draft signature 多数投票
- 已支持：主候选结果为空时尝试下一个 ready 候选
- 已支持：所有候选为空时转澄清
- 未支持：selection-agent、复杂置信度模型、执行错误反思修复、自由 SQL 重写

## 如何验证

```bash
.venv/bin/python -m pytest tests/test_semantic_voting_feedback.py tests/test_app_semantic_migration.py tests/test_semantic_query_pipeline.py -q
ruff check src/qsql/semantic_agent.py src/qsql/semantic_service.py src/qsql/schemas.py app.py tests/test_semantic_voting_feedback.py tests/test_app_semantic_migration.py
```

本次验证结果：

- `17 passed`
- `ruff check` 通过
