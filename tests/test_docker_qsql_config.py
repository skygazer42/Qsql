from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_docker_compose_uses_qsql_service_identity_and_healthcheck():
    compose = (ROOT / "docker-compose.yaml").read_text(encoding="utf-8")

    assert "image: qsql:0.7.9" in compose
    assert "container_name: qsql" in compose
    assert "QSQL_ALLOW_UNAUTHENTICATED" in compose
    assert "/api/v0/qsql/datasets" in compose


def test_local_env_allows_frontend_to_call_api_without_key_for_demo():
    env = (ROOT / ".env").read_text(encoding="utf-8")

    assert "QSQL_ALLOW_UNAUTHENTICATED=true" in env
    assert "SQLITE_DB_PATH=resources/uploads/online_retail/online_retail.sqlite3" in env
