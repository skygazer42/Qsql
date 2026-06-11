# 2026-06-11 pyproject 依赖收口与固定版本

## 改了什么

- 更新 [pyproject.toml](/data/temp/qsql/pyproject.toml)
  - 将主依赖固定到当前 `.venv` 中已验证的版本。
  - 删除当前服务主链路未使用的 `tabulate`、`flask-sock`、`flasgger`。
  - 补齐当前服务真实运行会直接用到但此前未放入主依赖的包：
    - `httpx`
    - `PyMySQL`
    - `starlette`
    - `langchain-community`
    - `langchain-text-splitters`
- 更新 optional dependencies
  - `runtime` extra 改为固定版本。
  - 已安装且当前仍保留的 extras（如 `openai`、`chromadb`、`aiofiles` 等）改为固定版本。
  - 未在本地环境安装的上游数据库 extras 暂不猜测版本，保持原状。
- 新增测试 [tests/test_pyproject_dependencies.py](/data/temp/qsql/tests/test_pyproject_dependencies.py)
  - 约束主依赖必须固定版本。
  - 约束 `runtime` extra 必须固定版本。
  - 约束当前主链路缺项已补齐，明显冗余项已移除。

## 为什么改

- 当前仓库已经不按上游“全功能 provider 集合”维护，而是按本地实际服务链路维护。
- 继续保留未使用依赖会增加安装体积、冲突面和排障噪音。
- 依赖不固定版本会让同一份仓库在不同环境解析出不同结果，和当前“收口主链路”的目标相冲突。

## 涉及文件

- `pyproject.toml`
- `tests/test_pyproject_dependencies.py`

## 如何验证

- `.venv/bin/python -m pytest tests/test_pyproject_dependencies.py -v`
- `.venv/bin/python -m pytest tests/test_imports.py tests/test_openai_compatible_provider.py tests/test_vanna.py tests/test_semantic_query_pipeline.py tests/test_pyproject_dependencies.py -v`
- `ruff check tests/test_pyproject_dependencies.py`
