import pymysql.cursors
import urllib.parse
import pymysql
from flask import Blueprint, request, jsonify

# 创建蓝图
pymysql_bp = Blueprint("mysql", __name__, url_prefix="/api/v0/sql")


def create_connection(payload):
    """创建MySQL数据库连接"""
    db_host = payload.get("DB_HOST", "")
    db_user = payload.get("DB_USER", "")
    db_password = urllib.parse.unquote(payload.get("DB_PASSWORD", ""))
    db_name = payload.get("DB_NAME", "")
    db_port = int(payload.get("DB_PORT", 3306))

    db_password = urllib.parse.unquote(db_password)
    try:
        connection = pymysql.connect(
            host=db_host,
            user=db_user,
            password=db_password,
            database=db_name,
            port=db_port,
            cursorclass=pymysql.cursors.DictCursor,
            ssl={"fake_flag_to_enable_tls": True},
        )
        if connection.open:
            return connection
        else:
            return None
    except pymysql.MySQLError as e:
        print(f"[create_connection] ❌ 数据库连接失败: {e}")
        return None


@pymysql_bp.route("/dry_run", methods=["POST"])
def dry_run():
    """测试执行 SQL 语句（不修改数据库）"""
    payload = request.get_json() or {}
    sql_query = payload.get("query", "")
    if not sql_query:
        return jsonify({"error": "No SQL query provided"}), 400

    connection = create_connection(payload)
    if connection is None:
        return jsonify({"error": "Failed to connect to the database"}), 500
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"EXPLAIN {sql_query}")
            cursor.fetchall()  # 如果能执行，则 SQL 语法正确
        return jsonify({"success": True}), 200
    except pymysql.MySQLError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    finally:
        connection.close()


@pymysql_bp.route("/execute_query", methods=["POST"])
def execute_query():
    """执行 SQL 查询并返回最后一条语句结果"""
    payload = request.get_json() or {}
    sql_queries = payload.get("queries", "")
    if not sql_queries or not isinstance(sql_queries, list):
        return jsonify({"error": "No SQL queries provided or invalid format"}), 400

    connection = create_connection(payload)
    if connection is None:
        return jsonify({"error": "Failed to connect to the database"}), 500

    result = None
    try:
        with connection.cursor() as cursor:
            for query in sql_queries:
                query = query.strip()
                if not query:
                    continue
                cursor.execute(query)
                result_ = cursor.fetchall()
                if result_:
                    result = result_

        if result is None:
            return (
                jsonify(
                    {"message": "No SELECT query was executed or no results returned"}
                ),
                200,
            )

        return jsonify({"result": result}), 200

    except pymysql.MySQLError as e:
        return jsonify({"error": str(e)}), 400
    finally:
        connection.close()
