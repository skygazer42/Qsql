import json
import os
import shutil
import sqlite3
import uuid

import chromadb
import numpy as np
import base64

from typing import Union, List, Dict
from chromadb.config import Settings
from src.qsql.chromadb import bm25_jieba
from src.qsql.chromadb.vectorize_helpers import (
    ensure_data_list,
    build_prompt_template,
    build_llm_request_context,
    resolve_text_content,
    stringify_for_embedding,
    normalize_meta_value,
    normalize_vector_fields,
    build_vector_source_from_fields,
    build_chunk_metadatas,
    insert_chunks_to_collection,
)
from src.qsql.openai_compatible.embedding import OpenAICompatibleEmbeddingFunction
from src.utils.log import Log
from sklearn.metrics.pairwise import cosine_similarity
from simhash import Simhash

log = Log()
# 内存中缓存所有集合的 BM25 索引，避免重复计算
_BM25_CACHE = {}
# [CUSTOM] 检索向量函数与主 LLM 统一收口到 OpenAI-compatible 协议。
embed_fn = OpenAICompatibleEmbeddingFunction("none")

CHROMA_PATH = os.environ["CHROMA_PATH"]
COLLECTION_NAME = "structured_vectors"
LLM_CONFIG = {
    "base_url": os.environ["LLM_BASE_URL"],
    "model": os.environ["LLM_MODEL"],
    "api_key": os.environ["LLM_API_KEY"],
    "language": "Chinese",
}


# ======================================================================
# 辅助函数
# ======================================================================)


def get_chroma_collection(
    dataset_id: str | None = None,
    verify: bool = True,
    create_if_not_exist: bool = False,
):
    """
    获取指定名称的 Chroma collection。
    - 若 create_if_not_exist=True，则不存在时自动创建；
    - 若 create_if_not_exist=False，则仅尝试获取已存在的集合，不创建。
    """
    client = chromadb.PersistentClient(
        path=CHROMA_PATH, settings=Settings(anonymized_telemetry=False)
    )
    collection_name = dataset_id or COLLECTION_NAME
    if create_if_not_exist:
        # 校验 dataset_id 合法性（可选项）
        if verify and not collection_name.isidentifier():
            raise ValueError(f"dataset_id: {collection_name} 不合法")
        collection = client.get_or_create_collection(
            name=collection_name, embedding_function=embed_fn
        )
    else:
        collection = client.get_collection(
            name=collection_name, embedding_function=embed_fn
        )
    return collection


def list_collections():
    client = chromadb.PersistentClient(
        path=CHROMA_PATH, settings=Settings(anonymized_telemetry=False)
    )
    collections = client.list_collections()
    results = []
    for dataset_id in collections:
        path = bm25_jieba.bm25_cache_path(dataset_id)
        indexed = os.path.exists(path)
        results.append({"dataset_id": dataset_id, "indexed": indexed})
    return results


def delete_collection(dataset_id):
    client = chromadb.PersistentClient(
        path=CHROMA_PATH, settings=Settings(anonymized_telemetry=False)
    )
    collection = client.get_collection(dataset_id)
    db_file = os.path.join(CHROMA_PATH, "chroma.sqlite3")
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT id FROM segments WHERE scope='VECTOR' and collection='{str(collection.id)}';"
    )
    row = cursor.fetchone()
    internal_id = row[0] if row else None
    dir_path = os.path.join(CHROMA_PATH, internal_id)
    # 先逻辑删除
    client.delete_collection(dataset_id)
    # 再物理删除
    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)
        print(f"[Chroma] 已删除 {dataset_id} 对应文件目录 {internal_id}")
    # 删除索引文件
    bm25_jieba.clear_bm25_cache(dataset_id)
    bm25_jieba.clear_ngram_cache(dataset_id)


def clear_chroma_collection():
    client = chromadb.PersistentClient(
        path=CHROMA_PATH, settings=Settings(anonymized_telemetry=False)
    )
    return client.delete_collection(name=COLLECTION_NAME)


def preview(page=1, page_size=10, dataset_id=None):
    """
    安全分页预览指定知识库内容。
    适合大集合：先获取全部ID，再按分页ID精确取文档。
    """
    collection = get_chroma_collection(dataset_id)

    if page < 1 or page_size <= 0:
        raise ValueError("page 与 page_size 必须为正整数")

    # 获取所有 ID 列表（轻量操作，不含 embeddings）
    all_data = collection.get(include=[])  # 仅取出 ids
    all_ids = all_data.get("ids", [])
    total = len(all_ids)

    if total == 0:
        return {
            "total": 0,
            "page": page,
            "page_size": page_size,
            "data": [],
        }

    # 计算分页范围
    start = (page - 1) * page_size
    end = start + page_size
    sub_ids = all_ids[start:end]
    # 仅获取这一页的文档
    sub_docs = collection.get(ids=sub_ids, include=["documents", "metadatas"])
    ids = sub_docs.get("ids", [])
    docs = sub_docs.get("documents", [])
    meta_datas = sub_docs.get("metadatas", [])
    max_preview_len = 200
    results = [
        {
            "id": i,
            "text": (d[:max_preview_len] + "...") if len(d) > max_preview_len else d,
            "metadatas": m or {},
        }
        for i, d, m in zip(ids, docs, meta_datas)
    ]
    result = {"total": total, "data": results}
    return json.dumps(result, ensure_ascii=False)


def get_document_detail(doc_id: str, dataset_id: str | None = None):
    """
    获取某个文档详情（根据 doc_id）
    """
    if not doc_id:
        raise ValueError("doc_id 不能为空")

    collection = get_chroma_collection(dataset_id)
    data = collection.get(ids=[str(doc_id)], include=["documents", "metadatas"])

    ids = data.get("ids", [])
    docs = data.get("documents", [])
    metas = data.get("metadatas", [])
    if not ids:
        raise ValueError(f"未找到文档: {doc_id}")

    return {
        "id": ids[0],
        "text": docs[0],
        "metadata": metas[0] if metas else {},
    }


# ======================================================================
# 功能函数：生成 + 向量存储 + 检索等
# ======================================================================
def generate_and_vectorize(
    data, dataset_id=None, enable_describe=False, custom_prompt=""
):
    """
    生成自然语言描述 + 向量化入库。

    参数:
        data: dict | list[dict]
            需要处理的结构化数据（单条或多条）
        dataset_id: str | None
            向量库集合 ID
        enable_describe: bool
            是否调用 LLM 将结构化数据转成自然语言（默认 False）
        custom_prompt: str
            用户自定义前缀提示，将拼接到系统默认提示前

    返回:
        list[dict]: [{'id': doc_id, 'text': '文本内容'}, ...]
    """
    data_list = ensure_data_list(data)
    prompt_template = build_prompt_template(custom_prompt)
    url, headers = build_llm_request_context(LLM_CONFIG)
    collection = get_chroma_collection(dataset_id, create_if_not_exist=True)
    results = []
    for i, item in enumerate(data_list):
        try:
            doc_id = item.get("doc_id", "")
            if doc_id:
                item.pop("doc_id")

            text = resolve_text_content(
                source_item=item,
                enable_describe=enable_describe,
                prompt_template=prompt_template,
                url=url,
                headers=headers,
                model=LLM_CONFIG["model"],
                fallback_text=json.dumps(item, ensure_ascii=False),
                logger=log,
                log_prefix="generate_and_vectorize",
                item_index=i,
            )

            # Step 2 — 判断是不是更新操作
            if doc_id:
                chroma_update(doc_id, text, dataset_id)
                results.append({"id": doc_id, "text": text})
                continue

            chunk_type = "text" if enable_describe else "json"
            chunks = embed_fn.smart_chunk_text(text, chunk_type=chunk_type)

            metas = build_chunk_metadatas(chunks)
            ids = insert_chunks_to_collection(collection, chunks, metas, embed_fn)

            log.info(f"[generate_and_vectorize]入库 {len(chunks)} 个 chunks。")
            results.extend(
                {"id": cid, "text": chunk["text"]} for cid, chunk in zip(ids, chunks)
            )
        except Exception as e:
            log.error(f"[generate_and_vectorize] 第{i + 1}条失败: {e}")
    return results


def generate_and_vectorize_advanced(
    data,
    dataset_id=None,
    enable_describe=False,
    custom_prompt="",
    vector_fields=None,
    metadata_fields=None,
):
    """
    高级向量化入库：
    - 支持多字段 vector_fields（用于多个目标检索字段）
    - 支持 metadata_fields 作为独立元数据
    """
    data_list = ensure_data_list(data)
    metadata_fields = metadata_fields if isinstance(metadata_fields, list) else []
    target_fields = normalize_vector_fields(vector_fields)
    prompt_template = build_prompt_template(custom_prompt)
    url, headers = build_llm_request_context(LLM_CONFIG)
    collection = get_chroma_collection(dataset_id, create_if_not_exist=True)
    results = []
    for i, item in enumerate(data_list):
        try:
            if not isinstance(item, dict):
                raise ValueError("data 列表中的每个元素必须是 dict")
            doc_id = item.get("doc_id", "")
            raw_item = dict(item)
            if doc_id:
                raw_item.pop("doc_id", None)
            vector_source = build_vector_source_from_fields(raw_item, target_fields)
            text = resolve_text_content(
                source_item=vector_source,
                enable_describe=enable_describe,
                prompt_template=prompt_template,
                url=url,
                headers=headers,
                model=LLM_CONFIG["model"],
                fallback_text=stringify_for_embedding(vector_source),
                logger=log,
                log_prefix="generate_and_vectorize_advanced",
                item_index=i,
            )
            if doc_id:
                chroma_update(doc_id, text, dataset_id)
                results.append({"id": doc_id, "text": text})
                continue
            chunk_type = "text" if (enable_describe or target_fields) else "json"
            chunks = embed_fn.smart_chunk_text(text, chunk_type=chunk_type)
            base_meta = {}
            for field in metadata_fields:
                if field in raw_item:
                    base_meta[field] = normalize_meta_value(raw_item[field])
            metas = build_chunk_metadatas(chunks, base_meta=base_meta)
            ids = insert_chunks_to_collection(collection, chunks, metas, embed_fn)
            log.info(f"[generate_and_vectorize_advanced]入库 {len(chunks)} 个 chunks。")
            results.extend(
                {"id": cid, "text": chunk["text"]} for cid, chunk in zip(ids, chunks)
            )
        except Exception as e:
            log.error(f"[generate_and_vectorize_advanced] 第{i + 1}条失败: {e}")
    return results


def chroma_delete(doc_id, dataset_id=None):
    """删除某个 id"""
    collection = get_chroma_collection(dataset_id)
    collection.delete(ids=[str(doc_id)])
    print(f"[Chroma] 已删除 id={doc_id} (dataset={dataset_id or 'default'})")


def chroma_update(doc_id, new_text, dataset_id=None, new_doc_id=None):
    """修改某条数据"""
    collection = get_chroma_collection(dataset_id)
    # 检查 ID 是否存在
    existing = collection.get(ids=[str(doc_id)])
    if not existing or not existing.get("ids") or not existing["ids"][0]:
        raise Exception(f"[{doc_id}]不存在")
    chunk = embed_fn.smart_chunk_text(new_text)[0]
    embeddings = [embed_fn.embed_chunk(chunk["text"])]
    if new_doc_id:
        doc_id = new_doc_id
    collection.update(
        ids=[str(doc_id)],
        documents=chunk["text"],
        embeddings=embeddings,
    )
    print(f"[Chroma] 已更新 id={doc_id} (dataset={dataset_id or 'default'})")


def build_bm25_index(dataset_id):
    collection = get_chroma_collection(dataset_id)
    bm25_jieba.save_bm25_index(dataset_id, collection)
    # 自动构建 n-gram 索引（用于短查询增强）
    bm25_jieba.build_ngram_index(dataset_id, collection)


def build_ngram_index(dataset_id):
    """构建 n-gram 索引（用于短查询增强）"""
    collection = get_chroma_collection(dataset_id)
    bm25_jieba.build_ngram_index(dataset_id, collection)


def clear_bm25_index(dataset_id):
    bm25_jieba.clear_bm25_cache(dataset_id)


def clear_ngram_index(dataset_id):
    """清理 n-gram 索引"""
    bm25_jieba.clear_ngram_cache(dataset_id)


# region AI问数训练数据知识库


def save_train_data(data: Union[Dict, List[Dict]]):
    valid_types = ["sql", "ddl", "documentation"]
    if isinstance(data, dict):
        data_list = [data]
    elif isinstance(data, list) and all(isinstance(d, dict) for d in data):
        data_list = data
    else:
        raise ValueError("输入必须是 dict 或 list[dict]")
    results = []
    for i, item in enumerate(data_list):
        try:
            # Step 0 — 从键中识别 dataset_id
            found_keys = [k for k in item.keys() if k in valid_types]
            if not found_keys:
                log.warning(
                    f"[save_train_data] 第{i + 1}条跳过：未找到有效 dataset_id 键"
                )
                continue
            dataset_id = found_keys[0]
            text = item[dataset_id]
            if not isinstance(text, str) or not text.strip():
                log.error(
                    f"[save_train_data] 第{i + 1}条的 {dataset_id} 内容为空，跳过"
                )
                continue
            # base64解码
            try:
                text = base64.b64decode(text).decode("utf-8")
            except Exception:
                pass
            #   Step 0.1 - SQL 特殊检查：必须有 question 字段
            if dataset_id == "sql":
                question = item.get("question")
                if not isinstance(question, str) or not question.strip():
                    log.error(
                        f"[save_train_data] 第{i + 1}条跳过：SQL 数据缺少 question 字段"
                    )
                    continue
                text = json.dumps(
                    {"question": question, "sql": text}, ensure_ascii=False
                )
            collection = get_chroma_collection(
                dataset_id, verify=False, create_if_not_exist=True
            )
            # Step 1 — 判断是不是更新操作
            doc_id = item.get("doc_id", "")
            if doc_id:
                chroma_update(doc_id, text, dataset_id)
                results.append({"id": doc_id, "text": text})
            else:
                # Step 2 — 分块与 embedding
                chunk = embed_fn.smart_chunk_text(text)[0]
                chunk_text = chunk.get("text") if isinstance(chunk, dict) else chunk
                if not isinstance(chunk_text, str) or not chunk_text.strip():
                    raise ValueError("分块结果无有效文本")
                embeddings = [embed_fn.embed_chunk(chunk_text)]
                # Step 3 — 入向量库
                doc_id = str(uuid.uuid4()) + "-" + dataset_id
                collection.add(
                    ids=[doc_id],
                    documents=[chunk_text],
                    embeddings=embeddings,
                )
                results.append({"id": doc_id, "text": chunk_text})
        except Exception as e:
            log.error(f"[save_train_data] 第{i + 1}条失败: {e}")
    return results


def preview_train_data(page=1, page_size=10):
    """
    安全分页预览内置知识库内容。
    适合大集合：先获取全部ID，再按分页ID精确取文档。
    """
    dataset_types = ["sql", "ddl", "documentation"]
    combined_docs = []

    # Step 1 — 遍历每个知识库
    for dataset_id in dataset_types:
        try:
            collection = get_chroma_collection(dataset_id)
            all_data = collection.get(include=["documents"])
            ids = all_data.get("ids", [])
            docs = all_data.get("documents", [])
            for i, d in zip(ids, docs):
                combined_docs.append(
                    {
                        "id": i,
                        "dataset": dataset_id,
                        "text": d,
                    }
                )
        except Exception as e:
            log.error(f"[get_train_data_list] 读取 {dataset_id} 集合失败: {e}")
            continue

    total = len(combined_docs)
    if total == 0:
        return json.dumps(
            {
                "total": 0,
                "page": page,
                "page_size": page_size,
                "data": [],
            },
            ensure_ascii=False,
        )

    # Step 2 — 分页 (对所有知识库结果汇总分页)
    start = (page - 1) * page_size
    end = start + page_size
    subset = combined_docs[start:end]
    # Step 3 — 文本截断
    max_preview_len = 200
    results = [
        {
            "id": item["id"],
            "dataset": item["dataset"],
            "text": (
                (item["text"][:max_preview_len] + "...")
                if len(item["text"]) > max_preview_len
                else item["text"]
            ),
        }
        for item in subset
    ]
    return json.dumps(
        {"total": total, "data": results},
        ensure_ascii=False,
    )


def remove_training_data(doc_id: str):
    """
    从对应的 Chroma 向量库中安全删除指定文档。
    根据 doc_id 后缀自动识别 dataset (sql / ddl / documentation)。
    """
    if not doc_id or not isinstance(doc_id, str):
        raise Exception("无效的 doc_id 参数")

    dataset_id = None
    lower_id = doc_id.lower()
    if lower_id.endswith("-sql"):
        dataset_id = "sql"
    elif lower_id.endswith("-ddl"):
        dataset_id = "ddl"
    elif lower_id.endswith("-documentation"):
        dataset_id = "documentation"
    if not dataset_id:
        raise Exception("未能找到dataset_id")

    collection = get_chroma_collection(dataset_id)
    collection.delete(ids=[str(doc_id)])
    log.info(f"[Chroma] 已删除 id={doc_id} (dataset={dataset_id})")


# endregion


def chroma_similarity(text_a: str, text_b: str):
    """
    混合相似度 (Chroma embedding + BM25_jieba)
    逻辑：
        1. 通过 smart_chunk_text 分块并计算两个文本的平均 embedding；
        2. 由 bm25_jieba._tokenize_text() 分词计算关键词相似度；
        3. 输出语义、关键词、融合得分。
    """

    text_a, text_b = text_a.strip(), text_b.strip()
    if not text_a or not text_b:
        return {"semantic": 0.0, "bm25": 0.0, "combined": 0.0}

    # === Step 1. 获取 embedding function ===
    try:
        chunks_a = embed_fn.smart_chunk_text(text_a)
        chunks_b = embed_fn.smart_chunk_text(text_b)

        emb_a = np.mean([embed_fn.embed_chunk(json.dumps(c)) for c in chunks_a], axis=0)
        emb_b = np.mean([embed_fn.embed_chunk(json.dumps(c)) for c in chunks_b], axis=0)

        sem_sim = float(cosine_similarity([emb_a], [emb_b])[0][0])
    except Exception as e:
        log.error(f"[chroma_similarity] 语义计算失败: {e}")
        sem_sim = 0.0

    # === Step 2. semhash  相似度 ===
    try:
        hash_a, hash_b = Simhash(text_a), Simhash(text_b)
        hamming_dist = hash_a.distance(hash_b)
        semhash_sim = 1 - hamming_dist / 64.0  # 映射到 0~1
    except Exception as e:
        log.error(f"[chroma_similarity] semhash 计算失败: {e}")
        semhash_sim = 0.0

    # === Step 3. 权重融合 ===
    alpha, mode = bm25_jieba.auto_alpha(text_b)
    combined = alpha * sem_sim + (1 - alpha) * semhash_sim
    log.info(
        f"[chroma_similarity] 模式={mode}, α={alpha:.2f}, sem={sem_sim:.3f}, bm25={semhash_sim:.3f}, combined={combined:.3f}"
    )
    same_words = []
    try:
        tokens_a = bm25_jieba.tokenize_text(text_a)
        tokens_b = bm25_jieba.tokenize_text(text_b)
        # 公共词交集
        same_words = sorted(set(tokens_a) & set(tokens_b))
    except Exception as e:
        log.error(f"[chroma_similarity] 没有关键词交集{e}")
    return {
        "semantic": sem_sim,
        "semhash": semhash_sim,
        "combined": combined,
        "same_words": same_words,
    }
