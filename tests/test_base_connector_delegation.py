from src.qsql.base.base import VannaBase


class DummyVannaBase(VannaBase):
    def generate_embedding(self, data: str, **kwargs):
        return []

    def get_similar_question_sql(self, question: str, **kwargs):
        return []

    def get_related_ddl(self, question: str, **kwargs):
        return []

    def get_related_documentation(self, question: str, **kwargs):
        return []

    def add_question_sql(self, question: str, sql: str, **kwargs):
        return "question-sql-id"

    def add_ddl(self, ddl: str, **kwargs):
        return "ddl-id"

    def add_documentation(self, documentation: str, **kwargs):
        return "doc-id"

    def get_training_data(self, **kwargs):
        return []

    def remove_training_data(self, id: str, **kwargs):
        return True

    def system_message(self, message: str):
        return message

    def user_message(self, message: str):
        return message

    def assistant_message(self, message: str):
        return message

    def submit_prompt(self, prompt, **kwargs):
        return ""


def test_optional_connector_methods_delegate_to_helper_module(monkeypatch):
    from src.qsql.base import base as base_module

    connector_specs = [
        (
            "connect_to_snowflake",
            "connect_to_snowflake_impl",
            ("account", "username", "password", "database"),
            {"role": "analyst", "warehouse": "wh", "keep_alive": True},
        ),
        (
            "connect_to_postgres",
            "connect_to_postgres_impl",
            (),
            {
                "host": "localhost",
                "dbname": "db",
                "user": "user",
                "password": "pwd",
                "port": 5432,
                "sslmode": "disable",
            },
        ),
        (
            "connect_to_mysql",
            "connect_to_mysql_impl",
            (),
            {
                "host": "localhost",
                "dbname": "db",
                "user": "user",
                "password": "pwd",
                "port": 3306,
                "charset": "utf8mb4",
            },
        ),
        (
            "connect_to_clickhouse",
            "connect_to_clickhouse_impl",
            (),
            {
                "host": "localhost",
                "dbname": "db",
                "user": "user",
                "password": "pwd",
                "port": 8123,
                "secure": False,
            },
        ),
        (
            "connect_to_oracle",
            "connect_to_oracle_impl",
            (),
            {"user": "user", "password": "pwd", "dsn": "host:1521/sid"},
        ),
        (
            "connect_to_bigquery",
            "connect_to_bigquery_impl",
            (),
            {"cred_file_path": "/tmp/cred.json", "project_id": "project"},
        ),
        (
            "connect_to_duckdb",
            "connect_to_duckdb_impl",
            (":memory:",),
            {"init_sql": "select 1", "read_only": False},
        ),
        (
            "connect_to_mssql",
            "connect_to_mssql_impl",
            ("Driver={ODBC Driver 18 for SQL Server};",),
            {"echo": False},
        ),
        (
            "connect_to_presto",
            "connect_to_presto_impl",
            ("host.example.com",),
            {
                "catalog": "hive",
                "schema": "default",
                "user": "user",
                "password": "pwd",
                "port": 8443,
                "combined_pem_path": None,
                "protocol": "https",
                "requests_kwargs": None,
            },
        ),
        (
            "connect_to_hive",
            "connect_to_hive_impl",
            (),
            {
                "host": "host.example.com",
                "dbname": "default",
                "user": "user",
                "password": "pwd",
                "port": 10000,
                "auth": "CUSTOM",
            },
        ),
    ]

    for method_name, helper_name, args, kwargs in connector_specs:
        captured = {}

        def recorder(vn, *helper_args, **helper_kwargs):
            captured["vn"] = vn
            captured["args"] = helper_args
            captured["kwargs"] = helper_kwargs
            return helper_name

        monkeypatch.setattr(base_module, helper_name, recorder)
        vn = DummyVannaBase(config={})

        result = getattr(vn, method_name)(*args, **kwargs)

        assert result == helper_name
        assert captured["vn"] is vn
        assert captured["args"] == args
        assert captured["kwargs"] == kwargs
