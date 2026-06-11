import importlib
import importlib.util
from pathlib import Path

import pytest


def _module_removed(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is None
    except ModuleNotFoundError:
        return True


def test_retained_provider_imports():
    retained_modules = [
        "src.qsql.base",
        "src.qsql.chromadb",
        "src.qsql.local",
        "src.qsql.openai",
        "src.qsql.openai_compatible",
    ]

    for module_name in retained_modules:
        module = importlib.import_module(module_name)
        assert module is not None


@pytest.mark.parametrize(
    "module_name",
    [
        "src.knowledge",
        "src.plugins",
        "src.plugins.document_processor_factory",
        "src.server.document_embed_api",
        "src.server.semantic_query_api",
        "src.qsql.anthropic",
        "src.qsql.azuresearch",
        "src.qsql.bedrock",
        "src.qsql.cohere",
        "src.qsql.deepseek",
        "src.qsql.google",
        "src.qsql.mistral",
        "src.qsql.ollama",
        "src.qsql.qianwen",
        "src.qsql.qdrant",
        "src.qsql.vannadb",
        "src.qsql.vllm",
        "src.qsql.flask",
        "src.qsql.chromadb.dify_retrieval",
        "src.qsql.mock",
        "src.qsql.xinference",
        "src.qsql.ZhipuAI",
    ],
)
def test_removed_provider_imports_raise(module_name: str):
    assert _module_removed(module_name)


def test_source_tree_has_no_python_cache_artifacts():
    src_root = Path(__file__).resolve().parents[1] / "src"
    artifacts = [
        str(path.relative_to(src_root.parent))
        for path in src_root.rglob("*")
        if path.name == "__pycache__" or path.suffix == ".pyc"
    ]

    assert artifacts == []


# [CUSTOM] 仓库命名已收口到 qsql，不应再残留历史中间目录名或旧绝对路径引用。
def test_repository_files_do_not_reference_legacy_repo_name():
    root = Path(__file__).resolve().parents[1]
    legacy_repo_name = "kd" + "-qsql"
    legacy_root_path = f"/data/temp/{legacy_repo_name}"
    targets = [
        root / "app.py",
        root / "README.md",
        root / "pyproject.toml",
        root / "src",
        root / "tests",
        root / "scripts",
        root / "docs",
        root / "resources",
    ]
    violations: list[str] = []

    for target in targets:
        paths = [target] if target.is_file() else list(target.rglob("*"))
        for path in paths:
            if not path.is_file():
                continue
            if path.suffix not in {
                ".py",
                ".md",
                ".toml",
                ".json",
                ".yaml",
                ".yml",
                ".txt",
            }:
                continue
            content = path.read_text(encoding="utf-8")
            if legacy_repo_name in content or legacy_root_path in content:
                violations.append(str(path.relative_to(root)))

    assert violations == []
