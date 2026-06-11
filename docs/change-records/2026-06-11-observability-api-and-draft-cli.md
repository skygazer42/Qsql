# 2026-06-11 Observability 只读 API 与 Semantic Draft CLI

## 改了什么

- `src/qsql/observability.py` 新增 `StructuredEventReader`
- 新增 `src/server/observability_api.py`
  - `GET /api/v0/observability/routes/recent`
  - `GET /api/v0/observability/routes/summary`
- `app.py` 注册 `observability_bp`
- 新增 `scripts/generate_semantic_draft.py`
- 新增 `scripts/__init__.py`，便于测试 CLI 入口
- `resources/semantic/README.md` 补充 semantic draft 脚本说明

## 为什么改

- 之前已经有：
  - route/timing 结构化事件写入
  - metadata -> semantic draft 生成器
- 但还差两层“边界闭环”：
  1. 事件虽然落盘了，但没有只读查看入口
  2. 语义草稿虽然能通过 API 生成，但缺一个更直接的离线 CLI

这次补的是运维/排障边界，不改运行时主链路：

- 查询仍然走 `pydantic + pydantic-ai + controlled SQL`
- 观测 API 只读，不会影响事件写入
- semantic draft CLI 只写 `resources/semantic_drafts`

## 涉及文件

- `app.py`
- `src/qsql/observability.py`
- `src/server/observability_api.py`
- `scripts/__init__.py`
- `scripts/generate_semantic_draft.py`
- `resources/semantic/README.md`
- `tests/test_observability_api.py`
- `tests/test_generate_semantic_draft_script.py`

## 如何验证

```bash
.venv/bin/python -m pytest tests/test_observability_api.py tests/test_generate_semantic_draft_script.py -q
ruff check app.py src tests scripts
python -m py_compile app.py $(find src -name '*.py' -print) $(find tests -name '*.py' -print) $(find scripts -name '*.py' -print)
.venv/bin/python -m pytest tests -q
```
