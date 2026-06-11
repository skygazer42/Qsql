import importlib


def _module_removed(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is None
    except ModuleNotFoundError:
        return True


# [CUSTOM] 约束文档 OCR / 解析插件不再留在 SQL 主项目中。
def test_plugins_package_removed():
    assert _module_removed("src.plugins")


def test_document_processor_factory_removed():
    assert _module_removed("src.plugins.document_processor_factory")
