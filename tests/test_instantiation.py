import importlib.util


def _module_removed(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is None
    except ModuleNotFoundError:
        return True


# [CUSTOM] 约束精简后的 SQL 分支不再保留测试用 mock 包，避免继续维护无业务价值的伪实现。
def test_qsql_mock_package_removed():
    assert _module_removed("src.qsql.mock")
