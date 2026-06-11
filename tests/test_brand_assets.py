from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_diagram_assets_use_chinese_titles():
    architecture = _read("docs/assets/architecture-overview.svg")
    pipeline = _read("docs/assets/semantic-query-pipeline.svg")
    metadata = _read("docs/assets/metadata-ops-flow.svg")

    assert "QSQL 架构总览" in architecture
    assert "Architecture Overview" not in architecture

    assert "语义查询主链路" in pipeline
    assert "Semantic Query Pipeline" not in pipeline

    assert "元数据运维链路" in metadata
    assert "Metadata Operations Flow" not in metadata


def test_readme_uses_mermaid_for_runtime_pipeline():
    readme = _read("README.md")

    assert "```mermaid" in readme
    assert "flowchart TB" in readme
    assert "数据问答主链路" in readme
    assert "docs/assets/semantic-query-pipeline.svg" not in readme
    assert "docs/assets/qsql-architecture-overview-zh.png" in readme


def test_logo_and_mark_share_same_core_symbol():
    logo = _read("static/brand/qsql-logo.svg")
    mark = _read("static/brand/qsql-mark.svg")

    assert 'id="qsql-core-mark"' in logo
    assert 'id="qsql-core-mark"' in mark
    assert "#1E63E9" in logo
    assert "#1E63E9" in mark


def test_readme_uses_png_wordmark():
    readme = _read("README.md")

    assert "static/brand/qsql-logo-wordmark.png" in readme
    assert "static/brand/qsql-logo.svg" not in readme
