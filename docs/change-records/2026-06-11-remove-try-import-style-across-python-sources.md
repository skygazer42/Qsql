# 移除源码中的 try-import 风格

## 改了什么

- 将 `src/qsql/schemas.py` 保持为纯 `pydantic v2` 直接导入风格。
- 清理 `src/qsql/base/base.py`、`src/qsql/openai_compatible/llm.py`、`src/qsql/chromadb/chromadb_vector.py`、`src/qsql/flask/__init__.py` 中的 `try: import ...` / `except ImportError` 写法。
- 顺带确认并约束 `src/` 下不再使用动态 `__import__(...)`。
- 清理 `src/qsql/sql_output_refiner.py` 中 `pydantic-ai` 模型类名的历史兼容导入分支，统一直接使用 `OpenAIChatModel`。
- 将 `src/qsql/sql_output_refiner.py` 的核心依赖提到模块顶层，并移除 `src/qsql/base/base.py::extract_sql` 中无必要的函数内 `import re`。
- 将 PDF 相关辅助函数拆到 `src/utils/pdf.py`，不再由公共 `src.utils` 入口导出 `is_text_pdf`，避免通用工具入口隐含 `fitz` 依赖。
- 将 `VannaBase` 中的可选数据库连接器实现外拆到 `src/qsql/base/optional_connectors.py`，`base.py` 只保留签名和参数转发，降低主基类文件体积并隔离非主链路依赖。
- 将 `VannaBase` 中的 `ask/train/_get_databases/_get_information_schema_tables/get_training_plan_*` 外拆到 `src/qsql/base/runtime_helpers.py`，`base.py` 继续保留稳定方法名与自定义日志回调透传。
- 为 `tests/test_schema_import_style.py` 新增全仓约束，禁止 `src/` 下 Python 源文件继续引入这类写法。

## 为什么改

- 当前仓库已经明确以单一依赖栈运行，不再需要历史兼容式 import fallback。
- `try-import` 会让依赖边界和真实失败点变得不清晰，也不符合当前统一的代码风格要求。
- 对可选数据库驱动，改为“显式依赖探测 + 函数内直接导入”，调用路径更直接，错误提示保持不变。

## 涉及文件

- `src/qsql/schemas.py`
- `src/qsql/base/base.py`
- `src/qsql/openai_compatible/llm.py`
- `src/qsql/chromadb/chromadb_vector.py`
- `src/qsql/flask/__init__.py`
- `src/qsql/sql_output_refiner.py`
- `src/qsql/base/base.py`
- `src/utils/__init__.py`
- `src/utils/pdf.py`
- `src/qsql/base/base.py`
- `src/qsql/base/optional_connectors.py`
- `src/qsql/base/runtime_helpers.py`
- `tests/test_schema_import_style.py`
- `tests/test_base_connector_delegation.py`
- `tests/test_base_runtime_delegation.py`

## 如何验证

- `pytest tests/test_schema_import_style.py -q`
- `pytest tests -q`
- `ruff check app.py src tests`
- `python -m py_compile app.py $(find src -name '*.py' -print) $(find tests -name '*.py' -print)`
