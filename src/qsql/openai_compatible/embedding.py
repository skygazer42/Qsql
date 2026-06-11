import json
import os
import re
import uuid

from collections import defaultdict
from typing import Literal

import requests
import tiktoken
from chromadb.api.types import IncludeEnum
from chromadb.utils.embedding_functions import EmbeddingFunction

from src.utils.log import Log


def _build_embedding_url(base_url: str) -> str:
    normalized_base_url = base_url.rstrip("/")
    if normalized_base_url.endswith("/embeddings"):
        return normalized_base_url
    return f"{normalized_base_url}/embeddings"


def _build_rerank_url(base_url: str) -> str:
    normalized_base_url = base_url.rstrip("/")
    configured_rerank_url = os.environ.get("RERANK_BASE_URL", "").strip().rstrip("/")
    if configured_rerank_url:
        if configured_rerank_url.endswith("/rerank"):
            return configured_rerank_url
        return f"{configured_rerank_url}/rerank"
    if normalized_base_url.endswith("/embeddings"):
        normalized_base_url = normalized_base_url[: -len("/embeddings")]
    if normalized_base_url.endswith("/v1"):
        normalized_base_url = normalized_base_url[: -len("/v1")]
    return f"{normalized_base_url}/rerank"


class OpenAICompatibleEmbeddingFunction(EmbeddingFunction):
    """符合 Chroma EmbeddingFunction 协议的 OpenAI-compatible embedding 实现。"""

    def __init__(
        self,
        aggregation: Literal["mean", "none"] = "mean",
        config: dict | None = None,
    ) -> None:
        # [CUSTOM] Embedding 统一走 OpenAI-compatible `/embeddings` 接口，移除 Xinference 特化实现。
        self.log = Log()
        self.config = config or {}
        self.aggregation = aggregation
        self.base_url = (
            self.config.get("base_url") or os.environ["EMBEDDING_BASE_URL"]
        ).rstrip("/")
        self.model = self.config.get("model") or os.environ["EMBEDDING_MODEL"]
        self.api_key = self.config.get("api_key") or os.environ.get(
            "EMBEDDING_API_KEY", ""
        )
        self.max_chunk_tokens = int(os.environ.get("MAX_CHUNK_TOKENS", 5000))
        self.embedding_url = _build_embedding_url(self.base_url)
        self.headers = {"Content-Type": "application/json"}
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"
        self.encoding = tiktoken.get_encoding("cl100k_base")
        self.rerank_url = _build_rerank_url(self.base_url)
        self.rerank_model = os.environ.get("RERANK_MODEL", "").strip()

    def __call__(self, texts: list[str]) -> list[list[float]]:
        """基础 embedding 调用，只为工具库兼容，不自动做分块聚合。"""
        return [self.embed_chunk(text) for text in texts]

    def chunk_text(self, text: str) -> list[str]:
        tokens = self.encoding.encode(text)
        chunks = []
        for i in range(0, len(tokens), self.max_chunk_tokens):
            chunk_text = self.encoding.decode(tokens[i : i + self.max_chunk_tokens])
            chunks.append(chunk_text)
        return chunks

    def smart_chunk_text(
        self, text: str, max_tokens: int | None = None, chunk_type: str = "text"
    ) -> list[dict]:
        """
        智能分块 + 元数据标注：
        1. 先取 max_chunk_tokens 大小的窗口；
        2. 若附近未找到标点，则逐步扩大窗口；
        3. 若未标点则强制切割；
        4. 每个块自动附带 chunk 元数据。
        """
        if max_tokens is None:
            max_tokens = self.max_chunk_tokens
        tokens = self.encoding.encode(text)
        parent_id = str(uuid.uuid4())

        if len(tokens) <= max_tokens:
            return [
                {
                    "text": text,
                    "meta": {
                        "chunk_index": 0,
                        "chunk_total": 1,
                        "parent_id": parent_id,
                        "chunk_type": chunk_type,
                    },
                }
            ]

        chars = list(text)
        chunks: list[str] = []
        start = 0
        window_size = 200
        max_lookahead = 800

        while start < len(chars):
            end = min(len(chars), start + max_tokens)
            found_punct = False
            lookahead = 0
            while (
                not found_punct
                and end + lookahead < len(chars)
                and lookahead < max_lookahead
            ):
                search_window = "".join(
                    chars[end + lookahead : end + lookahead + window_size]
                )
                punct_match = re.search(r"[。！？!?；;]", search_window)
                if punct_match:
                    end = end + lookahead + punct_match.start() + 1
                    found_punct = True
                else:
                    lookahead += window_size
            if not found_punct:
                end = min(len(chars), end + lookahead)
            sub_text = "".join(chars[start:end]).strip()
            if sub_text:
                chunks.append(sub_text)
            start = end

        structured_chunks = []
        total = len(chunks)
        for index, chunk in enumerate(chunks):
            structured_chunks.append(
                {
                    "text": chunk,
                    "meta": {
                        "chunk_index": index,
                        "chunk_total": total,
                        "parent_id": parent_id,
                        "chunk_type": chunk_type,
                    },
                }
            )
        return structured_chunks

    def smart_chunk_json(self, item: dict) -> list[dict]:
        """对超长字段进行智能切分，同时保留 JSON 文档语义。"""
        expanded_items = []
        parent_id = str(uuid.uuid4())
        for value in item.values():
            if isinstance(value, str):
                chunks = self.smart_chunk_text(value, chunk_type="json")
                if len(chunks) > 1:
                    for index, chunk in enumerate(chunks):
                        expanded_items.append(
                            {
                                "text": chunk["text"],
                                "meta": {
                                    "chunk_index": index,
                                    "chunk_total": len(chunks),
                                    "parent_id": parent_id,
                                    "chunk_type": "json",
                                },
                            }
                        )
                    break
        if not expanded_items:
            expanded_items = [
                {
                    "text": json.dumps(item, ensure_ascii=False),
                    "meta": {
                        "chunk_index": 0,
                        "chunk_total": 1,
                        "parent_id": parent_id,
                        "chunk_type": "json",
                    },
                }
            ]
        return expanded_items

    def embed_chunk(self, chunk: str) -> list[float]:
        payload = {"model": self.model, "input": [chunk]}
        try:
            response = requests.post(
                self.embedding_url,
                json=payload,
                headers=self.headers,
                timeout=120,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Embedding request failed: {exc}") from exc

        data = response.json()
        return data["data"][0]["embedding"]

    def rerank_documents(
        self, query: str, docs: list[tuple[str, str]] | list[str]
    ) -> list[tuple[str, str, float]]:
        # [CUSTOM] rerank 改为通用命名，避免在检索链路继续暴露供应商语义。
        if not self.rerank_model:
            self.log.warning("[Rerank] 未配置 RERANK_MODEL，跳过重排序。")
            return []

        max_chunk_tokens = int(
            os.environ.get("RERANK_MAX_CHUNK_TOKENS", self.max_chunk_tokens)
        )
        batch_size = 5
        if docs and isinstance(docs[0], str):
            docs = [(f"auto_{i}", text) for i, text in enumerate(docs)]

        expanded_docs = []
        doc_map: dict[str, list[str]] = defaultdict(list)
        for doc_id, text in docs:
            chunks = self.smart_chunk_text(text, max_chunk_tokens)
            for index, chunk_dict in enumerate(chunks):
                sub_id = f"{doc_id}_ch{index}"
                chunk_text = (
                    chunk_dict["text"] if isinstance(chunk_dict, dict) else chunk_dict
                )
                expanded_docs.append((sub_id, chunk_text))
                doc_map[doc_id].append(sub_id)

        sub_results: dict[str, float] = {}
        for i in range(0, len(expanded_docs), batch_size):
            batch = expanded_docs[i : i + batch_size]
            payload = {
                "model": self.rerank_model,
                "query": query,
                "documents": [text for _, text in batch],
            }

            try:
                response = requests.post(
                    self.rerank_url,
                    json=payload,
                    headers=self.headers,
                    timeout=120,
                )
                if response.status_code != 200:
                    self.log.error(
                        f"[Rerank] 第 {i // batch_size + 1} 批响应错误 {response.status_code}: {response.text[:200]}"
                    )
                    continue
                data = response.json()
                results = data.get("results", [])
                if len(results) != len(batch):
                    self.log.warning(
                        f"[Rerank] 结果数量异常: 期望 {len(batch)} 实际 {len(results)}"
                    )
                for (sub_id, _), result in zip(batch, results):
                    sub_results[sub_id] = result.get("score") or result.get(
                        "relevance_score", 0.0
                    )
            except Exception as exc:  # noqa: BLE001
                self.log.error(f"[Rerank] 第 {i // batch_size + 1} 批请求失败: {exc}")
                continue

        if not sub_results:
            self.log.warning("[Rerank] 无有效结果返回")
            return []

        final_results = []
        for doc_id, text in docs:
            sub_ids = doc_map[doc_id]
            sub_scores = [sub_results[sid] for sid in sub_ids if sid in sub_results]
            agg_score = max(sub_scores) if sub_scores else 0.0
            final_results.append((doc_id, text, agg_score))

        final_results.sort(key=lambda item: item[2], reverse=True)
        return final_results

    def smart_recall(
        self, collection, query: str, top_k: int = 5, where: dict | None = None
    ) -> list[tuple[str, str, float]]:
        """
        智能召回：
          1. 语义检索找到 query 最相似的块；
          2. 通过相似块找到 parent_id；
          3. 对于每个相似块，合并其上下文块。
        """
        if not collection or not query:
            self.log.warning("[Hybrid] collection 或 query 为空，无法召回。")
            return []

        try:
            query_params = {
                "query_texts": [query],
                "n_results": top_k,
                "include": [
                    IncludeEnum.documents,
                    IncludeEnum.metadatas,
                    IncludeEnum.distances,
                ],
            }
            if where:
                query_params["where"] = where
            semantic_results = collection.query(**query_params)
        except Exception as exc:  # noqa: BLE001
            self.log.error(f"[Hybrid] 语义召回失败: {exc}")
            return []

        ids_list = semantic_results.get("ids", [[]])[0]
        docs_list = semantic_results.get("documents", [[]])[0]
        dists_list = semantic_results.get("distances", [[]])[0]
        metas_list = semantic_results.get("metadatas", [[]])[0]
        self.log.info(f"[Hybrid] 语义召回 {len(ids_list)} 条。")

        semantic_pairs = []
        for chunk_id, document, distance, metadata in zip(
            ids_list, docs_list, dists_list, metas_list
        ):
            merged = ""
            if metadata:
                parent_id = metadata.get("parent_id", chunk_id)
                chunk_index = metadata.get("chunk_index", 0)
                chunk_type = metadata.get("chunk_type", "text")
                merged = self._merge_sub_chunks(
                    parent_id, chunk_index, chunk_type, collection
                )
            score = 1 - distance
            semantic_pairs.append((chunk_id, merged or document, score))

        self.log.info(f"[Hybrid] 聚合完成，共 {len(semantic_pairs)} 个父文档。")
        return semantic_pairs

    def _merge_sub_chunks(
        self,
        parent_id: str,
        target_index: int,
        chunk_type: str,
        collection,
    ) -> str:
        """合并同一 parent_id 的 chunk。"""
        try:
            response = collection.get(
                where={"parent_id": parent_id},
                include=["documents", IncludeEnum.documents],
            )
            docs = response.get("documents", [])
            metas = response.get("metadatas", [])
        except Exception as exc:  # noqa: BLE001
            self.log.warning(
                f"[merge_text_chunks] 获取 parent_id={parent_id} 失败: {exc}"
            )
            return ""

        if not docs:
            return ""

        chunks = []
        for document, metadata in zip(docs, metas or [{}] * len(docs)):
            chunks.append(
                {"idx": (metadata or {}).get("chunk_index", 0), "text": document.strip()}
            )
        if not chunks:
            return ""

        chunks.sort(key=lambda item: item["idx"])
        if chunk_type == "json":
            merged = "\n".join(item["text"] for item in chunks)
        else:
            start = max(target_index - 1, 0)
            end = min(target_index + 2, len(chunks))
            merged = "\n".join(item["text"] for item in chunks[start:end])
        return merged.strip()
