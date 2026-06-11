# 2026-06-11 plugins 依赖解耦

## 改了什么

- 更新 [src/plugins/document_processor_factory.py](/data/temp/qsql/src/plugins/document_processor_factory.py:1)
  - 处理器实现从“模块导入即全量加载”改为“按 processor_type 惰性导入”。
  - 缺少 OCR 依赖时，抛出明确的安装提示：安装 `.[plugins]`。
- 更新 [src/plugins/__init__.py](/data/temp/qsql/src/plugins/__init__.py:1)
  - `src.plugins` 包导出改为惰性加载，避免导入包时强依赖所有 OCR 后端。
- 更新 [pyproject.toml](/data/temp/qsql/pyproject.toml:1)
  - 从主依赖移除 `PyMuPDF`。
  - 新增 `plugins` extra，并固定版本：
    - `PyMuPDF==1.27.2.3`
    - `Pillow==12.2.0`
    - `rapidocr-onnxruntime==1.2.3`
- 新增测试
  - [tests/test_plugins_lazy_loading.py](/data/temp/qsql/tests/test_plugins_lazy_loading.py:1)
  - [tests/test_pyproject_dependencies.py](/data/temp/qsql/tests/test_pyproject_dependencies.py:1) 增加 `plugins` extra 约束
- 更新 [README.md](/data/temp/qsql/README.md:52)
  - 明确 `.[plugins]` 的安装方式

## 为什么改

- `src/plugins` 是可选文档处理能力，不应该继续把 OCR 依赖压在主服务安装路径里。
- 原来 `DocumentProcessorFactory` 会在导入时直接加载全部插件实现，导致即便只想导入包，也会因为缺少 `PIL` 等依赖而失败。
- 做成惰性导入后，主服务链路和可选 OCR 链路才能真正解耦。

## 涉及文件

- `src/plugins/document_processor_factory.py`
- `src/plugins/__init__.py`
- `pyproject.toml`
- `tests/test_plugins_lazy_loading.py`
- `tests/test_pyproject_dependencies.py`
- `README.md`

## 如何验证

- `.venv/bin/python -m pytest tests/test_pyproject_dependencies.py tests/test_plugins_lazy_loading.py -v`
- `.venv/bin/python -m pytest tests/test_imports.py tests/test_openai_compatible_provider.py tests/test_vanna.py tests/test_semantic_query_pipeline.py tests/test_pyproject_dependencies.py tests/test_plugins_lazy_loading.py -v`
- `ruff check src/plugins/document_processor_factory.py src/plugins/__init__.py tests/test_pyproject_dependencies.py tests/test_plugins_lazy_loading.py`
