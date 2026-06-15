# 2026-06-15 structured clarification P1-3

## 改了什么

- 新增 `SemanticClarificationOption` Pydantic 模型。
- `SemanticParseResponse` / `SemanticRunResponse` 增加 `clarification_options`，兼容保留原 `clarification_question`。
- 多指标澄清时，根据 catalog 中的 metric label / alias 返回匹配到的指标候选。
- 缺时间范围澄清时，根据指标默认时间维度返回通用时间范围候选：今年、本月、自定义时间范围。

## 为什么改

- 把开放式澄清升级为前端可直接渲染的结构化选项，减少用户二次输入成本。
- 保持通用底座边界：候选项只来自 catalog 元数据和通用时间预设，不写死业务项目规则。

## 涉及文件

- `src/qsql/schemas.py`
- `src/qsql/semantic_service.py`
- `tests/test_semantic_query_pipeline.py`
- `docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md`

## 如何验证

- `.venv/bin/python -m pytest tests/test_semantic_query_pipeline.py -q`
- `ruff check src/ app.py scripts tests test_search_algorithm.py`
- `.venv/bin/python -m pytest tests/`
