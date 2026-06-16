from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_qsql_static_home_loads_dedicated_assistant_assets():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

    assert "<title>QSQL 多表问答工作台</title>" in html
    assert "/qsql-assistant.css" in html
    assert "/qsql-assistant.js" in html
    assert "Vanna.AI" not in html


def test_qsql_assistant_frontend_binds_dataset_and_ask_endpoints():
    js = (ROOT / "static" / "qsql-assistant.js").read_text(encoding="utf-8")

    assert "/api/v0/qsql/datasets" in js
    assert "/api/v0/qsql/ask" in js
    assert "renderResultTable" in js
    assert "sqlOutput" in js
