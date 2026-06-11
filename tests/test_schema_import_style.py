import ast
import importlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
SCHEMAS_PATH = Path(__file__).resolve().parents[1] / "src" / "qsql" / "schemas.py"
IMPORT_TRY_PATTERN = re.compile(
    r"try:\n(?:[ \t]+(?:from [^\n]+ import [^\n]+|import [^\n]+)\n)+",
    re.MULTILINE,
)
ALLOWED_FUNCTION_IMPORTS = {
    ("src/utils/pdf.py", "is_text_pdf"),
    ("src/qsql/base/optional_connectors.py", "connect_to_snowflake_impl"),
    ("src/qsql/base/optional_connectors.py", "connect_to_postgres_impl"),
    ("src/qsql/base/optional_connectors.py", "connect_to_mysql_impl"),
    ("src/qsql/base/optional_connectors.py", "connect_to_clickhouse_impl"),
    ("src/qsql/base/optional_connectors.py", "connect_to_oracle_impl"),
    ("src/qsql/base/optional_connectors.py", "connect_to_bigquery_impl"),
    ("src/qsql/base/optional_connectors.py", "connect_to_duckdb_impl"),
    ("src/qsql/base/optional_connectors.py", "connect_to_mssql_impl"),
    ("src/qsql/base/optional_connectors.py", "connect_to_presto_impl"),
    ("src/qsql/base/optional_connectors.py", "connect_to_hive_impl"),
}


def test_schemas_use_direct_configdict_import():
    content = SCHEMAS_PATH.read_text(encoding="utf-8")

    assert "from pydantic import BaseModel, ConfigDict, Field" in content
    assert "except ImportError" not in content
    assert "ConfigDict = None" not in content


def test_source_files_do_not_use_try_import_blocks():
    violations: list[str] = []

    for path in SRC_ROOT.rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        if (
            "except ImportError" in content
            or "__import__(" in content
            or IMPORT_TRY_PATTERN.search(content)
        ):
            violations.append(str(path.relative_to(ROOT)))

    assert violations == []


def test_source_files_do_not_use_try_fallback_import_ast_pattern():
    violations: list[str] = []

    for path in SRC_ROOT.rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        module = ast.parse(content)

        for node in ast.walk(module):
            if not isinstance(node, ast.Try):
                continue

            if node.orelse or node.finalbody:
                continue

            if node.body and all(
                isinstance(stmt, (ast.Import, ast.ImportFrom)) for stmt in node.body
            ):
                violations.append(str(path.relative_to(ROOT)))
                break

    assert violations == []


def test_source_files_only_use_function_imports_for_allowed_optional_dependencies():
    violations: list[str] = []

    for path in SRC_ROOT.rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        module = ast.parse(content)

        for node in ast.walk(module):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            relative_path = str(path.relative_to(ROOT))
            function_imports = [
                stmt
                for stmt in node.body
                if isinstance(stmt, (ast.Import, ast.ImportFrom))
            ]
            if not function_imports:
                continue

            if (relative_path, node.name) not in ALLOWED_FUNCTION_IMPORTS:
                violations.append(f"{relative_path}:{node.name}")

    assert violations == []


def test_utils_package_does_not_export_pdf_helper_from_common_entry():
    utils_module = importlib.import_module("src.utils")
    pdf_module = importlib.import_module("src.utils.pdf")

    assert not hasattr(utils_module, "is_text_pdf")
    assert hasattr(pdf_module, "is_text_pdf")
