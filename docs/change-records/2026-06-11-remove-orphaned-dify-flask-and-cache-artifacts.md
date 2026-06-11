# 移除孤立 Dify 残片、上游 Flask 兼容层与源码缓存产物

## 改了什么

- 删除 `src/qsql/chromadb/dify_retrieval.py`
- 删除 `src/qsql/flask/` 兼容包
- 清理 `src/` 目录下所有 `__pycache__` 与 `.pyc`
- 新增 `tests/conftest.py`，在测试进程中关闭 bytecode 写入并清理 `src/` 下缓存产物
- 更新 `tests/test_imports.py`，约束上述模块与缓存产物不得再次出现

## 为什么改

- `dify_retrieval.py` 依赖当前仓库不存在的 `api.*` / `rag.*` 体系，属于外部项目残片，未接入当前主链路。
- `src/qsql/flask/` 依赖已经从主依赖集中移除的 `flasgger` / `flask_sock`，且当前 `app.py` 不再使用该兼容层。
- `__pycache__` / `.pyc` 属于构建缓存，不应长期保留在源码树中。

## 涉及文件

- `src/qsql/chromadb/dify_retrieval.py`
- `src/qsql/flask/__init__.py`
- `src/qsql/flask/auth.py`
- `src/qsql/flask/assets.py`
- `tests/test_imports.py`
- `tests/conftest.py`

## 如何验证

- `pytest tests/test_imports.py -q`
- `pytest tests -q`
- `ruff check app.py src tests`
- `python -m py_compile app.py $(find src -name '*.py' -print) $(find tests -name '*.py' -print)`
