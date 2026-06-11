from pathlib import Path

import tomllib


# [CUSTOM] 锁定当前精简分支的依赖策略，避免主链路重新漂回未固定/未使用依赖。
PYPROJECT_PATH = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _load_pyproject() -> dict:
    with PYPROJECT_PATH.open("rb") as file:
        return tomllib.load(file)


def _dependency_name(spec: str) -> str:
    for separator in ("==", ">=", "<=", "~=", "<", ">"):
        if separator in spec:
            return spec.split(separator, 1)[0].strip()
    return spec.strip()


def test_main_dependencies_are_pinned_and_trimmed():
    pyproject = _load_pyproject()
    dependencies = pyproject["project"]["dependencies"]
    dependency_names = {_dependency_name(spec) for spec in dependencies}

    assert all("==" in spec for spec in dependencies)
    assert "httpx" in dependency_names
    assert "PyMySQL" in dependency_names
    assert "aiofiles" not in dependency_names
    assert "langchain-community" not in dependency_names
    assert "langchain-text-splitters" not in dependency_names
    assert "minio" not in dependency_names
    assert "starlette" not in dependency_names
    assert "tabulate" not in dependency_names
    assert "flask-sock" not in dependency_names
    assert "flasgger" not in dependency_names


def test_runtime_optional_dependencies_are_pinned():
    pyproject = _load_pyproject()
    runtime_dependencies = pyproject["project"]["optional-dependencies"]["runtime"]

    assert all("==" in spec for spec in runtime_dependencies)
    assert "starlette" not in {_dependency_name(spec) for spec in runtime_dependencies}
    assert "langchain-community" not in {
        _dependency_name(spec) for spec in runtime_dependencies
    }
    assert "langchain-text-splitters" not in {
        _dependency_name(spec) for spec in runtime_dependencies
    }


def test_document_plugin_optional_dependencies_removed():
    pyproject = _load_pyproject()
    optional_dependencies = pyproject["project"]["optional-dependencies"]

    assert "aiofiles" not in optional_dependencies
    assert "plugins" not in optional_dependencies
    assert "pymupdf" not in optional_dependencies
