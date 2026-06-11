import hashlib
import json
import os
import time
from typing import Any, Dict, List

import chromadb
import pandas as pd
from chromadb.api.types import EmbeddingFunction
from chromadb.config import Settings

from src.utils import Log
from ..base import VannaBase
from ..utils import deterministic_uuid
from ...utils import setting
from src.qsql.openai_compatible.embedding import OpenAICompatibleEmbeddingFunction

# QSQL 诊断日志：仓库统一改为直接导入风格，不再保留 try-import fallback。
qsql_log = Log()


def _qsql_hash(value) -> str:
    if value is None:
        return "none"
    return hashlib.sha256(str(value).encode("utf-8", errors="replace")).hexdigest()[:12]


def _qsql_norm(value) -> str:
    return " ".join(str(value or "").split())


def _qsql_log(level: str, message: str) -> None:
    if qsql_log is None:
        return
    getattr(qsql_log, level)(message)


def _qsql_flatten(value) -> list:
    if not value:
        return []
    if len(value) == 1 and isinstance(value[0], list):
        return value[0]
    return value


def _qsql_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _qsql_float_or_none(value) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _qsql_parse_document(document) -> dict | None:
    if isinstance(document, dict):
        return document
    try:
        parsed_document = json.loads(document)
    except Exception:  # noqa: BLE001
        return None
    if isinstance(parsed_document, dict):
        return parsed_document
    return None

_openai_compatible_ef: EmbeddingFunction | None = None


def _get_default_embedding_function() -> EmbeddingFunction:
    # [CUSTOM] 默认 embedding 也统一走 OpenAI-compatible，并保持惰性初始化避免导入期强依赖环境。
    global _openai_compatible_ef
    if _openai_compatible_ef is None:
        _openai_compatible_ef = OpenAICompatibleEmbeddingFunction()
    return _openai_compatible_ef


class ChromaDB_VectorStore(VannaBase):
    def __init__(self, config=None):
        VannaBase.__init__(self, config=config)
        if config is None:
            config = {}

        DB_DIR = setting.DB_DIR
        if not os.path.exists(DB_DIR):
            os.mkdir(DB_DIR)

        path = os.environ["CHROMA_PATH"]  # config.get("path", ".")
        self.embedding_function = config.get("embedding_function")
        if self.embedding_function is None:
            self.embedding_function = _get_default_embedding_function()
        curr_client = config.get("client", "persistent")
        collection_metadata = config.get("collection_metadata", None)
        self.n_results_sql = config.get("n_results_sql", config.get("n_results", 10))
        self.n_results_documentation = config.get(
            "n_results_documentation", config.get("n_results", 10)
        )
        self.n_results_ddl = config.get("n_results_ddl", config.get("n_results", 10))
        # [CUSTOM] question-SQL 距离过滤只影响非 exact 历史样本，避免低相似样本污染 prompt。
        self.question_sql_distance_filter_enabled = _qsql_bool(
            config.get("question_sql_distance_filter_enabled", False)
        )
        self.question_sql_max_distance = _qsql_float_or_none(
            config.get("question_sql_max_distance", None)
        )

        if curr_client == "persistent":
            self.chroma_client = chromadb.PersistentClient(
                path=path, settings=Settings(anonymized_telemetry=False)
            )
        elif curr_client == "in-memory":
            self.chroma_client = chromadb.EphemeralClient(
                settings=Settings(anonymized_telemetry=False)
            )
        elif isinstance(curr_client, chromadb.api.client.Client):
            # allow providing client directly
            self.chroma_client = curr_client
        else:
            raise ValueError(f"Unsupported client was set in config: {curr_client}")

        self.documentation_collection = self.chroma_client.get_or_create_collection(
            name="documentation",
            embedding_function=self.embedding_function,
            metadata=collection_metadata,
        )
        self.ddl_collection = self.chroma_client.get_or_create_collection(
            name="ddl",
            embedding_function=self.embedding_function,
            metadata=collection_metadata,
        )
        self.sql_collection = self.chroma_client.get_or_create_collection(
            name="sql",
            embedding_function=self.embedding_function,
            metadata=collection_metadata,
        )

    def generate_embedding(self, data: str, **kwargs) -> List[float]:
        embedding = self.embedding_function([data])
        if len(embedding) == 1:
            return embedding[0]
        return embedding

    def add_question_sql(self, question: str, sql: str, **kwargs) -> str:
        question_sql_json = json.dumps(
            {
                "question": question,
                "sql": sql,
            },
            ensure_ascii=False,
        )
        id = deterministic_uuid(question_sql_json) + "-sql"
        # [CUSTOM] QSQL 诊断日志：确认人工 question-SQL 写入内容的 hash 与向量维度。
        start_time = time.time()
        embedding = self.generate_embedding(question_sql_json)
        self.sql_collection.add(
            documents=question_sql_json,
            embeddings=embedding,
            ids=id,
        )
        _qsql_log(
            "info",
            "[QSQL] Chroma写入SQL训练样本 "
            f"id={id} question_hash={_qsql_hash(question)} "
            f"question_len={len(str(question or ''))} sql_hash={_qsql_hash(sql)} "
            f"sql_len={len(str(sql or ''))} "
            f"embedding_dim={len(embedding) if hasattr(embedding, '__len__') else 'unknown'} "
            f"elapsed_ms={int((time.time() - start_time) * 1000)}",
        )

        return id

    def add_ddl(self, ddl: str, **kwargs) -> str:
        id = deterministic_uuid(ddl) + "-ddl"
        self.ddl_collection.add(
            documents=ddl,
            embeddings=self.generate_embedding(ddl),
            ids=id,
        )
        return id

    def add_documentation(self, documentation: str, **kwargs) -> str:
        id = deterministic_uuid(documentation) + "-doc"
        self.documentation_collection.add(
            documents=documentation,
            embeddings=self.generate_embedding(documentation),
            ids=id,
        )
        return id

    def get_training_data(self, **kwargs) -> pd.DataFrame:
        sql_data = self.sql_collection.get()

        df = pd.DataFrame()

        if sql_data is not None:
            # Extract the documents and ids
            documents = [json.loads(doc) for doc in sql_data["documents"]]
            ids = sql_data["ids"]

            # Create a DataFrame
            df_sql = pd.DataFrame(
                {
                    "id": ids,
                    "question": [doc["question"] for doc in documents],
                    "content": [doc["sql"] for doc in documents],
                }
            )

            df_sql["training_data_type"] = "sql"

            df = pd.concat([df, df_sql])

        ddl_data = self.ddl_collection.get()

        if ddl_data is not None:
            # Extract the documents and ids
            documents = [doc for doc in ddl_data["documents"]]
            ids = ddl_data["ids"]

            # Create a DataFrame
            df_ddl = pd.DataFrame(
                {
                    "id": ids,
                    "question": [None for doc in documents],
                    "content": [doc for doc in documents],
                }
            )

            df_ddl["training_data_type"] = "ddl"

            df = pd.concat([df, df_ddl])

        doc_data = self.documentation_collection.get()

        if doc_data is not None:
            # Extract the documents and ids
            documents = [doc for doc in doc_data["documents"]]
            ids = doc_data["ids"]

            # Create a DataFrame
            df_doc = pd.DataFrame(
                {
                    "id": ids,
                    "question": [None for doc in documents],
                    "content": [doc for doc in documents],
                }
            )

            df_doc["training_data_type"] = "documentation"

            df = pd.concat([df, df_doc])

        _qsql_log(
            "debug",
            "[QSQL] Chroma训练数据统计 "
            f"sql_count={len(sql_data['ids']) if sql_data else 0} "
            f"ddl_count={len(ddl_data['ids']) if ddl_data else 0} "
            f"doc_count={len(doc_data['ids']) if doc_data else 0}",
        )
        return df

    def remove_training_data(self, id: str, **kwargs) -> bool:
        if id.endswith("-sql"):
            self.sql_collection.delete(ids=id)
            return True
        elif id.endswith("-ddl"):
            self.ddl_collection.delete(ids=id)
            return True
        elif id.endswith("-doc"):
            self.documentation_collection.delete(ids=id)
            return True
        else:
            return False

    def remove_collection(self, collection_name: str) -> bool:
        """
        This function can reset the collection to empty state.

        Args:
            collection_name (str): sql or ddl or documentation

        Returns:
            bool: True if collection is deleted, False otherwise
        """
        if collection_name == "sql":
            self.chroma_client.delete_collection(name="sql")
            self.sql_collection = self.chroma_client.get_or_create_collection(
                name="sql", embedding_function=self.embedding_function
            )
            return True
        elif collection_name == "ddl":
            self.chroma_client.delete_collection(name="ddl")
            self.ddl_collection = self.chroma_client.get_or_create_collection(
                name="ddl", embedding_function=self.embedding_function
            )
            return True
        elif collection_name == "documentation":
            self.chroma_client.delete_collection(name="documentation")
            self.documentation_collection = self.chroma_client.get_or_create_collection(
                name="documentation", embedding_function=self.embedding_function
            )
            return True
        else:
            return False

    @staticmethod
    def _extract_documents(query_results: Dict[str, Any]) -> list:
        """
        Static method to extract the documents from the results of a query.

        Args:
            query_results (pd.DataFrame): The dataframe to use.

        Returns:
            List[str] or None: The extracted documents, or an empty list or
            single document if an error occurred.
        """
        if query_results is None:
            return []

        if "documents" in query_results:
            documents = query_results["documents"]

            if len(documents) == 1 and isinstance(documents[0], list):
                try:
                    documents = [json.loads(doc) for doc in documents[0]]
                except Exception:
                    return documents[0]

            return documents

    def get_similar_question_sql(self, question: str, **kwargs) -> list:
        # [CUSTOM] QSQL 诊断日志：记录召回数量、距离与是否包含完全相同问题，不改变召回结果。
        start_time = time.time()
        try:
            query_results = self.sql_collection.query(
                query_texts=[question],
                n_results=self.n_results_sql,
            )
        except Exception as exc:
            _qsql_log(
                "error",
                "[QSQL] Chroma召回SQL训练样本失败 "
                f"query_hash={_qsql_hash(question)} query_len={len(str(question or ''))} "
                f"n_results={self.n_results_sql} "
                f"elapsed_ms={int((time.time() - start_time) * 1000)} "
                f"error={type(exc).__name__}: {exc}",
            )
            raise
        documents = ChromaDB_VectorStore._extract_documents(query_results) or []

        ids = _qsql_flatten(query_results.get("ids")) if query_results else []
        distances = _qsql_flatten(query_results.get("distances")) if query_results else []
        target_question = _qsql_norm(question)
        exact_count = 0
        filtered_count = 0
        returned_documents = []
        top_summary = []
        filter_enabled = (
            self.question_sql_distance_filter_enabled
            and self.question_sql_max_distance is not None
        )
        for index, document in enumerate(documents):
            parsed_document = _qsql_parse_document(document)
            if parsed_document is None:
                doc_question = None
                doc_sql = None
            else:
                doc_question = parsed_document.get("question")
                doc_sql = parsed_document.get("sql")
            is_exact = _qsql_norm(doc_question) == target_question
            exact_count += int(is_exact)
            distance = distances[index] if index < len(distances) else None
            doc_id = ids[index] if index < len(ids) else None
            should_filter = (
                filter_enabled
                and not is_exact
                and distance is not None
                and distance > self.question_sql_max_distance
            )
            if should_filter:
                filtered_count += 1
            else:
                returned_documents.append(document)
            if index < 5:
                top_summary.append(
                    f"{index}:id={doc_id}:q={_qsql_hash(doc_question)}:"
                    f"sql={_qsql_hash(doc_sql)}:distance={distance}:"
                    f"exact={is_exact}:filtered={should_filter}"
                )

        _qsql_log(
            "info",
            "[QSQL] Chroma召回SQL训练样本 "
            f"query_hash={_qsql_hash(question)} query_len={len(str(question or ''))} "
            f"n_results={self.n_results_sql} raw_count={len(documents)} "
            f"returned_count={len(returned_documents)} filtered_count={filtered_count} "
            f"exact_question_count={exact_count} "
            f"distance_filter_enabled={filter_enabled} "
            f"distance_threshold={self.question_sql_max_distance} "
            f"min_distance={min(distances) if distances else None} "
            f"raw_max_distance={max(distances) if distances else None} "
            f"elapsed_ms={int((time.time() - start_time) * 1000)} "
            f"top={';'.join(top_summary)}",
        )
        return returned_documents

    def get_related_ddl(self, question: str, **kwargs) -> list:
        return ChromaDB_VectorStore._extract_documents(
            self.ddl_collection.query(
                query_texts=[question],
                n_results=self.n_results_ddl,
            )
        )

    def get_related_documentation(self, question: str, **kwargs) -> list:
        return ChromaDB_VectorStore._extract_documents(
            self.documentation_collection.query(
                query_texts=[question],
                n_results=self.n_results_documentation,
            )
        )
