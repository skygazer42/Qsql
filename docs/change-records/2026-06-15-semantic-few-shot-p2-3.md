# 2026-06-15 semantic few-shot P2-3

## 改了什么

- 新增 `SemanticExample` / `SemanticExampleMatch` Pydantic 模型。
- 新增 `src/qsql/semantic_examples.py`：
  - 从 `resources/semantic_examples/<dataset_id>.jsonl` 加载示例。
  - 使用轻量 token overlap 做本地相似示例检索。
  - 将命中示例格式化为 prompt 片段。
- `SemanticQueryAgent` 在解析 prompt 中注入相似成功示例。
- 新增 `resources/semantic_examples/online_retail.jsonl` 示例。

## 为什么改

- 复用 Vanna “成功样例”思路，但注入的是受控 `SemanticQueryDraft`，不是自由 SQL。
- 默认文件检索器无外部服务依赖，后续可以在同一 Pydantic 契约下替换为 Chroma/向量检索。

## 涉及文件

- `src/qsql/schemas.py`
- `src/qsql/semantic_agent.py`
- `src/qsql/semantic_examples.py`
- `resources/semantic_examples/online_retail.jsonl`
- `tests/test_semantic_examples.py`
- `docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md`

## 如何验证

- `.venv/bin/python -m pytest tests/test_semantic_examples.py -q`
- `ruff check src/ app.py scripts tests test_search_algorithm.py`
- `.venv/bin/python -m pytest tests/`
