# 2026-06-11 移除文档知识库、OCR 插件与 mock 包

## 改了什么

- 从 `app.py` 移除 `document_embed_api` 蓝图注册与导入。
- 删除 `src/server/document_embed_api.py`。
- 删除整套文档知识库 / OCR / 解析相关源码：
  - `src/knowledge/`
  - `src/plugins/`
  - `src/storage/minio/`
- 删除测试用 mock 包：
  - `src/qsql/mock/`
- 删除未再使用的图片处理工具：
  - `src/utils/image_processor.py`
- 收紧 `pyproject.toml`，移除文档链路相关依赖与 extras：
  - `aiofiles`
  - `minio`
  - `starlette`
  - `langchain-community`
  - `langchain-text-splitters`
  - `pymupdf`
  - `plugins`
- 更新 README 与测试约束，明确这些模块不再属于当前 SQL 精简分支。

## 为什么改

- 当前仓库目标已经收敛为 Vanna 的 SQL / Text2SQL / 结构化语义问答分支。
- 文档知识库、OCR、对象存储和 mock 测试包不属于这条主链路，继续留在仓库里会抬高依赖复杂度，也会让边界变模糊。
- 这些模块被保留会造成两个问题：
  - 安装依赖被无关能力拖重
  - 项目定位从 SQL 问答分支重新变回“大而全”的混合仓库

## 涉及文件

- `app.py`
- `pyproject.toml`
- `README.md`
- `tests/test_imports.py`
- `tests/test_instantiation.py`
- `tests/test_plugins_lazy_loading.py`
- `tests/test_pyproject_dependencies.py`
- `src/server/document_embed_api.py`
- `src/knowledge/**`
- `src/plugins/**`
- `src/storage/minio/**`
- `src/qsql/mock/**`
- `src/utils/image_processor.py`

## 如何验证

- `.venv/bin/python -m pytest tests/test_imports.py tests/test_instantiation.py tests/test_plugins_lazy_loading.py tests/test_pyproject_dependencies.py tests/test_openai_compatible_provider.py tests/test_vanna.py tests/test_semantic_query_pipeline.py -q`
- `ruff check app.py src tests`
- `.venv/bin/python -m py_compile app.py $(find src -name '*.py' -print) $(find tests -name '*.py' -print)`
