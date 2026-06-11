import os

import chromadb
import pymysql.cursors
import pytest
from pymysql.err import MySQLError
from chromadb.config import Settings
from chromadb.api.types import EmbeddingFunction
from dotenv import load_dotenv

os.environ.setdefault("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
os.environ.setdefault("LLM_MODEL", "test-model")
os.environ.setdefault("LLM_API_KEY", "EMPTY")
os.environ.setdefault("EMBEDDING_BASE_URL", "http://127.0.0.1:3000/v1")
os.environ.setdefault("EMBEDDING_MODEL", "test-embedding")
os.environ.setdefault("EMBEDDING_API_KEY", "EMPTY")
os.environ.setdefault("CHROMA_PATH", "./resources/db")

load_dotenv()

# [CUSTOM] 测试链路与运行时一致，统一使用 OpenAI-compatible embedding。
from src.qsql.openai_compatible.embedding import (  # noqa: E402
    OpenAICompatibleEmbeddingFunction,
)
from src.qsql.chromadb import vector_store_service as vector_service  # noqa: E402

openai_compatible_ef: EmbeddingFunction = OpenAICompatibleEmbeddingFunction()

CHROMA_PATH = "./resources/db"
COLLECTION_NAME = "structured_vectors"

LLM_CONFIG = {
    "base_url": os.environ["LLM_BASE_URL"],
    "model": os.environ["LLM_MODEL"],
    "api_key": os.environ["LLM_API_KEY"],
    "language": "Chinese",
}

# ============ 辅助函数 ============


def get_chroma_collection():
    client = chromadb.PersistentClient(
        path=CHROMA_PATH, settings=Settings(anonymized_telemetry=False)
    )
    return client.get_or_create_collection(
        name=COLLECTION_NAME, embedding_function=openai_compatible_ef
    )


# ============ 功能函数 ============


def generate_and_vectorize(data):
    """
    生成自然语言描述 + 向量化入库：
    data: 可以是单条 dict，也可以是 list[dict]
    返回: [{'id': doc_id, 'text': '自然语言'}, ...]
    """

    try:
        return vector_service.generate_and_vectorize(
            data, dataset_id="company_d53b26a0d0c8d169908dc92212d48bc4"
        )
    except Exception as e:
        print(e)


def chroma_search(query, top_k=10, threshold=0.5):
    """
    检索接口
    """
    try:
        return vector_service.chroma_search(query, top_k, threshold)
    except Exception as e:
        print(e)


def chroma_delete(doc_id):
    """删除某个 id"""
    try:
        vector_service.chroma_delete(doc_id)
    except Exception as e:
        print(e)


def chroma_update(doc_id, new_text):
    """修改某条数据"""
    try:
        if not new_text:
            raise Exception("参数异常")
        vector_service.chroma_update(doc_id, new_text)
    except Exception as e:
        print(e)


# ============ main 部分 ============


def test_main():
    # 先连接数据库，只在 main 中创建连接
    MYSQL_CONFIG = {
        "host": os.getenv("MYSQL_HOST"),
        "user": os.getenv("MYSQL_USER"),
        "password": os.getenv("MYSQL_PASSWORD"),
        "database": os.getenv("MYSQL_DBNAME"),
        "port": int(os.getenv("MYSQL_PORT", 3306)),
    }

    # [CUSTOM] 这是依赖本地 MySQL 与 embedding 服务的集成测试；环境未配齐时直接跳过，避免全量回归被外部条件卡死。
    missing_keys = [key for key, value in MYSQL_CONFIG.items() if key != "port" and not value]
    if missing_keys:
        pytest.skip(f"MySQL 集成测试环境未配置: {', '.join(missing_keys)}")

    try:
        conn = pymysql.connect(**MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    except MySQLError as exc:
        pytest.skip(f"MySQL 集成测试不可用: {exc}")

    try:
        with conn.cursor() as cursor:
            sql = "SELECT * FROM view_kjc_company_info LIMIT 50"
            cursor.execute(sql)
            rows = cursor.fetchall()
    except MySQLError as e:
        print(f"MySQL 读取失败: {e}")
    all_results = []
    for row in rows:
        # 逐条生成自然语言描述
        result = generate_and_vectorize(row)
        # result 是一个 list（长度为1），取第 0 条即可
        if not result:
            continue
        doc = result[0]
        print(f"已生成 doc_id={doc['id']}，描述片段={doc['text'][:60]}...")

        all_results.append(doc)

    # Example: 检索
    res = chroma_search("今点软件是一家怎么样的公司？")
    print("检索结果：", res)

    # 修改 / 删除示例
    # chroma_update("1", "这是一家专注于AI软件的公司。")
    # chroma_delete("2")
