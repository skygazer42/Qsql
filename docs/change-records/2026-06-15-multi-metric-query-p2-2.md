# 2026-06-15 multi metric query P2-2

## 改了什么

- `SemanticQueryDraft` 新增 `metric_keys`，用于表达同一问题中明确选择的多个指标。
- `QueryExecutionPlan` 新增 `metric_keys` / `metric_labels`，保留 `metric_key` / `metric_label` 作为主指标兼容字段。
- `sql_builder` 支持同一语义表、同一 group_by 粒度下生成多个聚合指标列。
- 多指标跨语义表时明确拒绝，避免静默扩展到多事实表查询。
- `SemanticPostprocessor` 在 draft 已覆盖问题中命中的多个指标时，不再强制转澄清。
- `SemanticQueryAgent` prompt 增加 `metric_keys` 输出规则。

## 为什么改

- 减少“销售额和销量”这类常见复合问句被无谓澄清打断。
- 保持通用底座和受控 SQL 路线：只允许 catalog 已声明指标，并限制在同表同粒度的确定性 SQL 生成范围内。

## 涉及文件

- `src/qsql/schemas.py`
- `src/qsql/sql_builder.py`
- `src/qsql/semantic_postprocessor.py`
- `src/qsql/semantic_service.py`
- `src/qsql/semantic_agent.py`
- `tests/test_semantic_query_pipeline.py`
- `tests/test_semantic_postprocessor.py`
- `docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md`

## 如何验证

- `.venv/bin/python -m pytest tests/test_semantic_query_pipeline.py tests/test_semantic_postprocessor.py -q`
- `ruff check src/ app.py scripts tests test_search_algorithm.py`
- `.venv/bin/python -m pytest tests/`
