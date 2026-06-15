from src.server import use_mysql_api


def test_read_only_guard_rejects_write_statements():
    forbidden = [
        "DELETE FROM users",
        "UPDATE users SET name = 'x'",
        "INSERT INTO users(id) VALUES (1)",
        "DROP TABLE users",
        "SELECT 1; DELETE FROM users",
    ]

    for query in forbidden:
        assert use_mysql_api.is_read_only_query(query) is False


def test_read_only_guard_accepts_select_and_with_queries():
    allowed = [
        "SELECT * FROM users",
        "WITH recent AS (SELECT * FROM users) SELECT * FROM recent",
    ]

    for query in allowed:
        assert use_mysql_api.is_read_only_query(query) is True
