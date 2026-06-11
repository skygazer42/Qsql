# [CUSTOM] 可选数据库连接器实现从 base.py 外拆，降低主基类体积并隔离非主链路依赖。
from __future__ import annotations

import importlib.util
import json
import os
import sys
from typing import Any, Union
from urllib.parse import urlparse

import pandas as pd
import requests

from ..exceptions import DependencyError, ImproperlyConfigured, ValidationError
from ..utils import validate_config_path


def _ensure_dependency(module_name: str, install_hint: str) -> None:
    if importlib.util.find_spec(module_name) is None:
        raise DependencyError(install_hint)


def connect_to_snowflake_impl(
    vn: Any,
    account: str,
    username: str,
    password: str,
    database: str,
    role: str | None = None,
    warehouse: str | None = None,
    **kwargs,
):
    _ensure_dependency(
        "snowflake.connector",
        "You need to install required dependencies to execute this method, run command:"
        " \npip install qsql[snowflake]",
    )
    import snowflake.connector

    if username == "my-username":
        username_env = os.getenv("SNOWFLAKE_USERNAME")

        if username_env is not None:
            username = username_env
        else:
            raise ImproperlyConfigured("Please set your Snowflake username.")

    if password == "mypassword":
        password_env = os.getenv("SNOWFLAKE_PASSWORD")

        if password_env is not None:
            password = password_env
        else:
            raise ImproperlyConfigured("Please set your Snowflake password.")

    if account == "my-account":
        account_env = os.getenv("SNOWFLAKE_ACCOUNT")

        if account_env is not None:
            account = account_env
        else:
            raise ImproperlyConfigured("Please set your Snowflake account.")

    if database == "my-database":
        database_env = os.getenv("SNOWFLAKE_DATABASE")

        if database_env is not None:
            database = database_env
        else:
            raise ImproperlyConfigured("Please set your Snowflake database.")

    conn = snowflake.connector.connect(
        user=username,
        password=password,
        account=account,
        database=database,
        client_session_keep_alive=True,
        **kwargs,
    )

    def run_sql_snowflake(sql: str) -> pd.DataFrame:
        cs = conn.cursor()

        if role is not None:
            cs.execute(f"USE ROLE {role}")

        if warehouse is not None:
            cs.execute(f"USE WAREHOUSE {warehouse}")
        cs.execute(f"USE DATABASE {database}")

        cur = cs.execute(sql)
        results = cur.fetchall()
        return pd.DataFrame(results, columns=[desc[0] for desc in cur.description])

    vn.dialect = "Snowflake SQL"
    vn.run_sql = run_sql_snowflake
    vn.run_sql_is_set = True


def connect_to_postgres_impl(
    vn: Any,
    host: str = None,
    dbname: str = None,
    user: str = None,
    password: str = None,
    port: int = None,
    **kwargs,
):
    _ensure_dependency(
        "psycopg2",
        "You need to install required dependencies to execute this method,"
        " run command: \npip install qsql[postgres]",
    )
    import psycopg2
    import psycopg2.extras

    if not host:
        host = os.getenv("HOST")
    if not host:
        raise ImproperlyConfigured("Please set your postgres host")

    if not dbname:
        dbname = os.getenv("DATABASE")
    if not dbname:
        raise ImproperlyConfigured("Please set your postgres database")

    if not user:
        user = os.getenv("PG_USER")
    if not user:
        raise ImproperlyConfigured("Please set your postgres user")

    if not password:
        password = os.getenv("PASSWORD")
    if not password:
        raise ImproperlyConfigured("Please set your postgres password")

    if not port:
        port = os.getenv("PORT")
    if not port:
        raise ImproperlyConfigured("Please set your postgres port")

    try:
        test_conn = psycopg2.connect(
            host=host,
            dbname=dbname,
            user=user,
            password=password,
            port=port,
            **kwargs,
        )
        test_conn.close()
    except psycopg2.Error as e:
        raise ValidationError(e)

    def connect_to_db():
        return psycopg2.connect(
            host=host,
            dbname=dbname,
            user=user,
            password=password,
            port=port,
            **kwargs,
        )

    def run_sql_postgres(sql: str) -> Union[pd.DataFrame, None]:
        conn = None
        try:
            conn = connect_to_db()
            cs = conn.cursor()
            cs.execute(sql)
            results = cs.fetchall()
            return pd.DataFrame(results, columns=[desc[0] for desc in cs.description])
        except psycopg2.InterfaceError:
            if conn:
                conn.close()
            conn = connect_to_db()
            cs = conn.cursor()
            cs.execute(sql)
            results = cs.fetchall()
            return pd.DataFrame(results, columns=[desc[0] for desc in cs.description])
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            raise ValidationError(e)
        except Exception as e:
            conn.rollback()
            raise e

    vn.dialect = "PostgreSQL"
    vn.run_sql_is_set = True
    vn.run_sql = run_sql_postgres


def connect_to_mysql_impl(
    vn: Any,
    host: str = None,
    dbname: str = None,
    user: str = None,
    password: str = None,
    port: int = None,
    **kwargs,
):
    _ensure_dependency(
        "pymysql",
        "You need to install required dependencies to execute this method,"
        " run command: \npip install PyMySQL",
    )
    import pymysql
    import pymysql.cursors

    if not host:
        host = os.getenv("HOST")
    if not host:
        raise ImproperlyConfigured("Please set your MySQL host")

    if not dbname:
        dbname = os.getenv("DATABASE")
    if not dbname:
        raise ImproperlyConfigured("Please set your MySQL database")

    if not user:
        user = os.getenv("USER")
    if not user:
        raise ImproperlyConfigured("Please set your MySQL user")

    if not password:
        password = os.getenv("PASSWORD")
    if not password:
        raise ImproperlyConfigured("Please set your MySQL password")

    if not port:
        port = os.getenv("PORT")
    if not port:
        raise ImproperlyConfigured("Please set your MySQL port")

    conn = None
    try:
        conn = pymysql.connect(
            host=host,
            user=user,
            password=password,
            database=dbname,
            port=port,
            charset=kwargs.get("charset", "utf8mb4"),
            connect_timeout=kwargs.get("connect_timeout", 10),
            read_timeout=kwargs.get("read_timeout", 30),
            cursorclass=pymysql.cursors.DictCursor,
            **kwargs,
        )
    except pymysql.Error as e:
        raise ValidationError(e)

    def run_sql_mysql(sql: str) -> Union[pd.DataFrame, None]:
        if conn:
            try:
                conn.ping(reconnect=True)
                with conn.cursor() as cs:
                    cs.execute(sql)
                    results = cs.fetchall()
                    df = pd.DataFrame(
                        results, columns=[desc[0] for desc in cs.description]
                    )
                    conn.commit()
                    return df
            except pymysql.Error as e:
                conn.rollback()
                raise ValidationError(e)
            except Exception as e:
                conn.rollback()
                raise e

    vn.run_sql_is_set = True
    vn.run_sql = run_sql_mysql


def connect_to_clickhouse_impl(
    vn: Any,
    host: str = None,
    dbname: str = None,
    user: str = None,
    password: str = None,
    port: int = None,
    **kwargs,
):
    _ensure_dependency(
        "clickhouse_connect",
        "You need to install required dependencies to execute this method,"
        " run command: \npip install clickhouse_connect",
    )
    import clickhouse_connect

    if not host:
        host = os.getenv("HOST")
    if not host:
        raise ImproperlyConfigured("Please set your ClickHouse host")

    if not dbname:
        dbname = os.getenv("DATABASE")
    if not dbname:
        raise ImproperlyConfigured("Please set your ClickHouse database")

    if not user:
        user = os.getenv("USER")
    if not user:
        raise ImproperlyConfigured("Please set your ClickHouse user")

    if not password:
        password = os.getenv("PASSWORD")
    if not password:
        raise ImproperlyConfigured("Please set your ClickHouse password")

    if not port:
        port = os.getenv("PORT")
    if not port:
        raise ImproperlyConfigured("Please set your ClickHouse port")

    conn = None
    try:
        conn = clickhouse_connect.get_client(
            host=host,
            port=port,
            username=user,
            password=password,
            database=dbname,
            **kwargs,
        )
        print(conn)
    except Exception as e:
        raise ValidationError(e)

    def run_sql_clickhouse(sql: str) -> Union[pd.DataFrame, None]:
        if conn:
            try:
                result = conn.query(sql)
                results = result.result_rows
                return pd.DataFrame(results, columns=result.column_names)
            except Exception as e:
                raise e

    vn.run_sql_is_set = True
    vn.run_sql = run_sql_clickhouse


def connect_to_oracle_impl(
    vn: Any, user: str = None, password: str = None, dsn: str = None, **kwargs
):
    _ensure_dependency(
        "oracledb",
        "You need to install required dependencies to execute this method,"
        " run command: \npip install oracledb",
    )
    import oracledb

    if not dsn:
        dsn = os.getenv("DSN")
    if not dsn:
        raise ImproperlyConfigured(
            "Please set your Oracle dsn which should include host:port/sid"
        )

    if not user:
        user = os.getenv("USER")
    if not user:
        raise ImproperlyConfigured("Please set your Oracle db user")

    if not password:
        password = os.getenv("PASSWORD")
    if not password:
        raise ImproperlyConfigured("Please set your Oracle db password")

    conn = None
    try:
        conn = oracledb.connect(user=user, password=password, dsn=dsn, **kwargs)
    except oracledb.Error as e:
        raise ValidationError(e)

    def run_sql_oracle(sql: str) -> Union[pd.DataFrame, None]:
        if conn:
            try:
                sql = sql.rstrip()
                if sql.endswith(";"):
                    sql = sql[:-1]
                cs = conn.cursor()
                cs.execute(sql)
                results = cs.fetchall()
                return pd.DataFrame(results, columns=[desc[0] for desc in cs.description])
            except oracledb.Error as e:
                conn.rollback()
                raise ValidationError(e)
            except Exception as e:
                conn.rollback()
                raise e

    vn.run_sql_is_set = True
    vn.run_sql = run_sql_oracle


def connect_to_bigquery_impl(
    vn: Any, cred_file_path: str = None, project_id: str = None, **kwargs
):
    _ensure_dependency(
        "google.cloud.bigquery",
        "You need to install required dependencies to execute this method, run command:"
        " \npip install qsql[bigquery]",
    )
    _ensure_dependency(
        "google.oauth2.service_account",
        "You need to install required dependencies to execute this method, run command:"
        " \npip install qsql[bigquery]",
    )
    from google.cloud import bigquery
    from google.oauth2 import service_account

    if not project_id:
        project_id = os.getenv("PROJECT_ID")
    if not project_id:
        raise ImproperlyConfigured("Please set your Google Cloud Project ID.")

    if "google.colab" in sys.modules:
        _ensure_dependency(
            "google.colab",
            "You need to install required dependencies to execute this method, run command:"
            " \npip install google-colab",
        )
        from google.colab import auth

        try:
            auth.authenticate_user()
        except Exception as e:
            raise ImproperlyConfigured(e)
    else:
        print("Not using Google Colab.")

    conn = None
    if not cred_file_path:
        try:
            conn = bigquery.Client(project=project_id)
        except Exception:
            print("Could not found any google cloud implicit credentials")
    else:
        validate_config_path(cred_file_path)

    if not conn:
        with open(cred_file_path, "r") as f:
            credentials = service_account.Credentials.from_service_account_info(
                json.loads(f.read()),
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )

        try:
            conn = bigquery.Client(
                project=project_id, credentials=credentials, **kwargs
            )
        except Exception:
            raise ImproperlyConfigured(
                "Could not connect to bigquery please correct credentials"
            )

    def run_sql_bigquery(sql: str) -> Union[pd.DataFrame, None]:
        if conn:
            job = conn.query(sql)
            return job.result().to_dataframe()
        return None

    vn.dialect = "BigQuery SQL"
    vn.run_sql_is_set = True
    vn.run_sql = run_sql_bigquery


def connect_to_duckdb_impl(vn: Any, url: str, init_sql: str = None, **kwargs):
    _ensure_dependency(
        "duckdb",
        "You need to install required dependencies to execute this method,"
        " run command: \npip install qsql[duckdb]",
    )
    import duckdb

    if url == ":memory:" or url == "":
        path = ":memory:"
    else:
        print(os.path.exists(url))
        if os.path.exists(url):
            path = url
        elif url.startswith("md") or url.startswith("motherduck"):
            path = url
        else:
            path = os.path.basename(urlparse(url).path)
            if not os.path.exists(path):
                response = requests.get(url)
                response.raise_for_status()
                with open(path, "wb") as f:
                    f.write(response.content)

    conn = duckdb.connect(path, **kwargs)
    if init_sql:
        conn.query(init_sql)

    def run_sql_duckdb(sql: str):
        return conn.query(sql).to_df()

    vn.dialect = "DuckDB SQL"
    vn.run_sql = run_sql_duckdb
    vn.run_sql_is_set = True


def connect_to_mssql_impl(vn: Any, odbc_conn_str: str, **kwargs):
    if importlib.util.find_spec("pyodbc") is None:
        raise DependencyError(
            "You need to install required dependencies to execute this method,"
            " run command: pip install pyodbc"
        )

    _ensure_dependency(
        "sqlalchemy",
        "You need to install required dependencies to execute this method,"
        " run command: pip install sqlalchemy",
    )
    import sqlalchemy as sa
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL

    connection_url = URL.create(
        "mssql+pyodbc", query={"odbc_connect": odbc_conn_str}
    )
    engine = create_engine(connection_url, **kwargs)

    def run_sql_mssql(sql: str):
        with engine.begin() as conn:
            df = pd.read_sql_query(sa.text(sql), conn)
            conn.close()
            return df
        raise Exception("Couldn't run sql")

    vn.dialect = "T-SQL / Microsoft SQL Server"
    vn.run_sql = run_sql_mssql
    vn.run_sql_is_set = True


def connect_to_presto_impl(
    vn: Any,
    host: str,
    catalog: str = "hive",
    schema: str = "default",
    user: str = None,
    password: str = None,
    port: int = None,
    combined_pem_path: str = None,
    protocol: str = "https",
    requests_kwargs: dict = None,
    **kwargs,
):
    _ensure_dependency(
        "pyhive.presto",
        "You need to install required dependencies to execute this method,"
        " run command: \npip install pyhive",
    )
    from pyhive import presto

    if not host:
        host = os.getenv("PRESTO_HOST")
    if not host:
        raise ImproperlyConfigured("Please set your presto host")

    if not catalog:
        catalog = os.getenv("PRESTO_CATALOG")
    if not catalog:
        raise ImproperlyConfigured("Please set your presto catalog")

    if not user:
        user = os.getenv("PRESTO_USER")
    if not user:
        raise ImproperlyConfigured("Please set your presto user")

    if not password:
        password = os.getenv("PRESTO_PASSWORD")
    if not port:
        port = os.getenv("PRESTO_PORT")
    if not port:
        raise ImproperlyConfigured("Please set your presto port")

    conn = None
    try:
        if requests_kwargs is None and combined_pem_path is not None:
            requests_kwargs = {"verify": combined_pem_path}
        conn = presto.Connection(
            host=host,
            username=user,
            password=password,
            catalog=catalog,
            schema=schema,
            port=port,
            protocol=protocol,
            requests_kwargs=requests_kwargs,
            **kwargs,
        )
    except presto.Error as e:
        raise ValidationError(e)

    def run_sql_presto(sql: str) -> Union[pd.DataFrame, None]:
        if conn:
            try:
                sql = sql.rstrip()
                if sql.endswith(";"):
                    sql = sql[:-1]
                cs = conn.cursor()
                cs.execute(sql)
                results = cs.fetchall()
                return pd.DataFrame(results, columns=[desc[0] for desc in cs.description])
            except presto.Error as e:
                print(e)
                raise ValidationError(e)
            except Exception as e:
                print(e)
                raise e

    vn.run_sql_is_set = True
    vn.run_sql = run_sql_presto


def connect_to_hive_impl(
    vn: Any,
    host: str = None,
    dbname: str = "default",
    user: str = None,
    password: str = None,
    port: int = None,
    auth: str = "CUSTOM",
    **kwargs,
):
    _ensure_dependency(
        "pyhive.hive",
        "You need to install required dependencies to execute this method,"
        " run command: \npip install pyhive",
    )
    from pyhive import hive

    if not host:
        host = os.getenv("HIVE_HOST")
    if not host:
        raise ImproperlyConfigured("Please set your hive host")

    if not dbname:
        dbname = os.getenv("HIVE_DATABASE")
    if not dbname:
        raise ImproperlyConfigured("Please set your hive database")

    if not user:
        user = os.getenv("HIVE_USER")
    if not user:
        raise ImproperlyConfigured("Please set your hive user")

    if not password:
        password = os.getenv("HIVE_PASSWORD")

    if not port:
        port = os.getenv("HIVE_PORT")
    if not port:
        raise ImproperlyConfigured("Please set your hive port")

    conn = None
    try:
        conn = hive.Connection(
            host=host,
            username=user,
            password=password,
            database=dbname,
            port=port,
            auth=auth,
        )
    except hive.Error as e:
        raise ValidationError(e)

    def run_sql_hive(sql: str) -> Union[pd.DataFrame, None]:
        if conn:
            try:
                sql = sql.rstrip()
                if sql.endswith(";"):
                    sql = sql[:-1]
                cs = conn.cursor()
                cs.execute(sql)
                results = cs.fetchall()
                return pd.DataFrame(results, columns=[desc[0] for desc in cs.description])
            except hive.Error as e:
                print(e)
                raise ValidationError(e)
            except Exception as e:
                print(e)
                raise e

    vn.run_sql_is_set = True
    vn.run_sql = run_sql_hive
