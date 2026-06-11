import os
import numpy as np
import json
from src.qsql.chromadb import bm25_jieba
from src.utils.log import Log
from src.utils import setting
from src.qsql.chromadb.vector_store_service import get_chroma_collection
from src.qsql.openai_compatible.embedding import OpenAICompatibleEmbeddingFunction

log = Log()

_DEFAULT_LIGHT_QUERY_TOKENS = set()
_LIGHT_QUERY_TOKEN_CACHE = {"mtime": 0.0, "data": {"global": [], "datasets": {}}}

_NON_INTENT_SCORE_CAP = 0.2


def _append_metadata_to_text(text: str, metadata: dict) -> str:
    """将用户元数据合并到 JSON 字符串中（不覆盖已有字段）"""
    if not metadata:
        return text
    try:
        data = json.loads(text)
        for k, v in metadata.items():
            if k not in data:
                data[k] = v
        return json.dumps(data, ensure_ascii=False)
    except Exception:
        return text


def _extract_core_tokens(query_variants, dataset_id: str | None = None) -> list[str]:
    light_tokens = _load_light_query_tokens(dataset_id)
    tokens = []
    for q in query_variants:
        for t in bm25_jieba.tokenize_text((q or "").strip().lower()):
            tok = t.strip()
            if len(tok) < 2:
                continue
            if tok in light_tokens:
                continue
            if tok not in tokens:
                tokens.append(tok)
    return tokens


def _load_light_query_tokens(dataset_id: str | None = None) -> set[str]:
    result = set(_DEFAULT_LIGHT_QUERY_TOKENS)
    path = setting.QUERY_LIGHT_TOKENS_PATH
    if not os.path.exists(path):
        return result
    try:
        mtime = os.path.getmtime(path)
        if _LIGHT_QUERY_TOKEN_CACHE["mtime"] != mtime:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if not isinstance(loaded, dict):
                loaded = {}
            global_tokens = loaded.get("global", [])
            datasets = loaded.get("datasets", {})
            if not isinstance(global_tokens, list):
                global_tokens = []
            if not isinstance(datasets, dict):
                datasets = {}
            _LIGHT_QUERY_TOKEN_CACHE["mtime"] = mtime
            _LIGHT_QUERY_TOKEN_CACHE["data"] = {
                "global": global_tokens,
                "datasets": datasets,
            }
        cached = _LIGHT_QUERY_TOKEN_CACHE["data"] or {}
        result.update(
            str(x).strip() for x in cached.get("global", []) if str(x).strip()
        )
        if dataset_id:
            ds_tokens = cached.get("datasets", {}).get(dataset_id, [])
            if isinstance(ds_tokens, list):
                result.update(str(x).strip() for x in ds_tokens if str(x).strip())
    except Exception as e:
        log.error(f"[LightTokens] 加载轻词失败: {e}")
    return result


def _count_core_token_hits_in_text(core_tokens, text: str) -> int:
    if not core_tokens:
        return 0
    text_lower = (text or "").lower()
    return sum(1 for tok in core_tokens if tok in text_lower)


def _extract_item_name(text: str) -> str:
    if not text:
        return ""
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            return ""
        for key in ("事项名称", "[事项名称", "事项名称]", "[事项名称]"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().strip("[]【】")
    except Exception:
        return ""
    return ""


def _recall_all_sources(
    query, dataset_id, collection, embed_fn, top_k, metadata_filter, alpha, mode
):
    """执行所有召回通道"""

    def _merge_by_max_score(pairs):
        """同一 doc_id 多次命中时取最高分。"""
        best = {}
        for doc_id, doc, score in pairs:
            if doc_id not in best or score > best[doc_id][1]:
                best[doc_id] = (doc, score)
        merged = [(did, d, s) for did, (d, s) in best.items()]
        merged.sort(key=lambda x: x[2], reverse=True)
        return merged[:top_k]

    query_variants = bm25_jieba.expand_query_variants(query, dataset_id=dataset_id)
    if len(query_variants) > 1:
        log.info(f"[Hybrid] 关键词查询扩展: {query_variants}")

    sem_pairs = embed_fn.smart_recall(collection, query, top_k, where=metadata_filter)
    log.info(f"[Hybrid] 语义召回 {len(sem_pairs)} 条,alpha={alpha}, mode={mode}")
    for i, (doc_id, doc, score) in enumerate(sem_pairs[:3]):
        log.debug(f"[语义#{i + 1}] id={doc_id}, score={score:.4f}, text={doc[:50]}...")

    bm25_pairs_all = []
    for qv in query_variants or [query]:
        bm25_pairs_all.extend(
            bm25_jieba.bm25_recall(
                qv, dataset_id, collection, top_k, where=metadata_filter
            )
        )
    bm25_pairs = _merge_by_max_score(bm25_pairs_all)
    log.info(f"[Hybrid] BM25 召回 {len(bm25_pairs)} 条。")
    for i, (doc_id, doc, score) in enumerate(bm25_pairs[:3]):
        log.info(f"[BM25#{i + 1}] id={doc_id}, score={score:.4f}, text={doc[:50]}...")

    ngram_pairs, substr_pairs = [], []
    if mode == bm25_jieba.SearchSource.KEYWORD:
        substr_pairs_all = []
        ngram_pairs_all = []
        for qv in query_variants or [query]:
            substr_pairs_all.extend(
                bm25_jieba.substring_recall(
                    qv, dataset_id, collection, top_k, where=metadata_filter
                )
            )
            ngram_pairs_all.extend(
                bm25_jieba.ngram_recall(
                    qv, dataset_id, collection, top_k, where=metadata_filter
                )
            )
        substr_pairs = _merge_by_max_score(substr_pairs_all)
        ngram_pairs = _merge_by_max_score(ngram_pairs_all)
        log.info(
            f"[短查询增强] 子串召回 {len(substr_pairs)} 条，n-gram 召回 {len(ngram_pairs)} 条。"
        )
        for i, (doc_id, doc, score) in enumerate(substr_pairs[:3]):
            log.info(f"[子串#{i + 1}] id={doc_id}, score={score:.4f}")
        for i, (doc_id, doc, score) in enumerate(ngram_pairs[:3]):
            log.info(f"[n-gram#{i + 1}] id={doc_id}, score={score:.4f}")

    return sem_pairs, bm25_pairs, ngram_pairs, substr_pairs, query_variants


def _merge_scores(
    sem_pairs,
    bm25_pairs,
    ngram_pairs,
    substr_pairs,
    alpha,
    mode,
    query_variants,
    dataset_id=None,
):
    """合并各通道分数"""

    def minmax(x, arr):
        arr_min, arr_max = np.min(arr), np.max(arr)
        return 0.0 if arr_max == arr_min else (x - arr_min) / (arr_max - arr_min)

    combined = {}
    for doc_id, doc, sem_s in sem_pairs:
        combined[doc_id] = {
            "text": doc,
            "semantic": sem_s,
            "bm25": 0.0,
            "ngram": 0.0,
            "substr": 0.0,
            "source": bm25_jieba.SearchSource.SEMANTIC,
        }
    for doc_id, doc, bm_s in bm25_pairs:
        if doc_id not in combined:
            combined[doc_id] = {
                "text": doc,
                "semantic": 0.0,
                "bm25": bm_s,
                "ngram": 0.0,
                "substr": 0.0,
                "source": bm25_jieba.SearchSource.KEYWORD,
            }
        else:
            combined[doc_id]["bm25"] = bm_s
            combined[doc_id]["source"] = bm25_jieba.SearchSource.HYBRID
    for doc_id, doc, ng_s in ngram_pairs:
        if doc_id in combined:
            combined[doc_id]["ngram"] = ng_s
        else:
            combined[doc_id] = {
                "text": doc,
                "semantic": 0.0,
                "bm25": 0.0,
                "ngram": ng_s,
                "substr": 0.0,
                "source": "ngram",
            }
    for doc_id, doc, sub_s in substr_pairs:
        if doc_id in combined:
            combined[doc_id]["substr"] = sub_s
        else:
            combined[doc_id] = {
                "text": doc,
                "semantic": 0.0,
                "bm25": 0.0,
                "ngram": 0.0,
                "substr": sub_s,
                "source": "substring",
            }

    sem_vals = np.array([max(0, v["semantic"]) for v in combined.values()])
    bm_vals = np.array([v["bm25"] for v in combined.values()])
    ng_vals = np.array([v["ngram"] for v in combined.values()])
    sub_vals = np.array([v["substr"] for v in combined.values()])
    core_tokens = _extract_core_tokens(query_variants, dataset_id)
    if core_tokens:
        log.info(f"[Hybrid] 核心词: {core_tokens}")

    for doc_id, v in combined.items():
        sem_norm = minmax(max(0, v["semantic"]), sem_vals)
        bm_norm = minmax(v["bm25"], bm_vals)
        ng_norm = minmax(v["ngram"], ng_vals)
        sub_norm = minmax(v["substr"], sub_vals)
        text_hit_cnt = _count_core_token_hits_in_text(core_tokens, v["text"])
        item_name = _extract_item_name(v["text"])
        name_hit_cnt = _count_core_token_hits_in_text(core_tokens, item_name)
        intent_hit = text_hit_cnt >= 2
        if mode == bm25_jieba.SearchSource.KEYWORD:
            v["combined"] = (
                0.2 * sem_norm + 0.25 * bm_norm + 0.35 * sub_norm + 0.2 * ng_norm
            )
        else:
            v["combined"] = alpha * sem_norm + (1 - alpha) * bm_norm
        name_penalty = 0.0
        if core_tokens and not intent_hit:
            name_penalty = 0.12
        elif core_tokens and text_hit_cnt < len(core_tokens):
            name_penalty = 0.05
        v["combined"] = max(
            0.0,
            min(1.0, v["combined"] - name_penalty),
        )

        if core_tokens and not intent_hit:
            v["combined"] = min(v["combined"], _NON_INTENT_SCORE_CAP)
        # 调试：记录top5文档的详细评分
        v["_norm"] = {
            "sem": sem_norm,
            "bm": bm_norm,
            "ng": ng_norm,
            "sub": sub_norm,
            "name_penalty": name_penalty,
            "intent_hit": 1.0 if intent_hit else 0.0,
            "text_hit_cnt": float(text_hit_cnt),
            "name": 1.0 if name_hit_cnt > 0 else 0.0,
            "name_hit_cnt": float(name_hit_cnt),
        }

    if mode == bm25_jieba.SearchSource.BALANCED and core_tokens:
        before = len(combined)
        combined = {
            did: v
            for did, v in combined.items()
            if v["_norm"].get("intent_hit", 0.0) > 0
        }
        if before != len(combined):
            log.info(f"[Hybrid] balanced意图过滤: {before} -> {len(combined)}")

    # balanced 模式降噪：无语义支撑且事项名称不含核心词的纯关键词结果直接过滤
    if mode == bm25_jieba.SearchSource.BALANCED and core_tokens:
        before = len(combined)
        combined = {
            did: v
            for did, v in combined.items()
            if not (v["semantic"] <= 0 and v["_norm"].get("name", 0.0) <= 0)
        }
        if before != len(combined):
            log.info(
                f"[Hybrid] balanced降噪：过滤无语义且名称无核心词结果 {before - len(combined)} 条。"
            )
    # keyword 模式降噪：过滤“仅 n-gram 命中”的结果，避免短词泛匹配噪声
    if mode == bm25_jieba.SearchSource.KEYWORD:
        before = len(combined)
        combined = {
            did: v
            for did, v in combined.items()
            if not (v["semantic"] <= 0 and v["bm25"] <= 0 and v["substr"] <= 0)
        }
        if before != len(combined):
            log.info(
                f"[Hybrid] keyword降噪：过滤纯n-gram结果 {before - len(combined)} 条。"
            )

    # 同分打散：优先更“精确”的通道，再看语义，最后看 n-gram
    sorted_items = sorted(
        combined.items(),
        key=lambda kv: (
            kv[1]["combined"],
            kv[1]["_norm"].get("text_hit_cnt", 0.0),
            kv[1]["_norm"].get("sub", 0.0),
            kv[1]["_norm"].get("bm", 0.0),
            kv[1]["_norm"].get("sem", 0.0),
            kv[1]["_norm"].get("ng", 0.0),
        ),
        reverse=True,
    )
    combined_pairs = [
        (doc_id, val["text"], val["combined"]) for doc_id, val in sorted_items
    ]
    log.info(f"[Hybrid] 融合后候选 {len(combined_pairs)} 条。")
    for i, (doc_id, text, score) in enumerate(combined_pairs[:5]):
        norm = combined[doc_id].get("_norm", {})
        raw = combined[doc_id]
        log.info(f"[融合#{i + 1}] id={doc_id}, combined={score:.4f}")
        log.info(
            f"原始: sem={raw['semantic']:.4f}, bm25={raw['bm25']:.4f}, sub={raw['substr']:.4f}, ng={raw['ngram']:.4f}"
        )
        log.info(
            f"归一: sem={norm.get('sem', 0):.4f}, bm25={norm.get('bm', 0):.4f}, sub={norm.get('sub', 0):.4f}, ng={norm.get('ng', 0):.4f}, text_hit_cnt={norm.get('text_hit_cnt', 0):.0f}, name_hit_cnt={norm.get('name_hit_cnt', 0):.0f}, name_penalty={norm.get('name_penalty', 0):.4f}"
        )
    return combined, combined_pairs


def _apply_rerank(query, combined_pairs, threshold, mode, embed_fn):
    """应用rerank重排序"""
    rerank_model = os.environ.get("RERANK_MODEL", "").strip()
    if rerank_model and mode == bm25_jieba.SearchSource.SEMANTIC:
        log.info(f"[Rerank] {mode} 模式启用重排序，模型: {rerank_model}")
        try:
            rerank_input = [(doc_id, text) for doc_id, text, _ in combined_pairs]
            # [CUSTOM] rerank 接口名改为通用命名，避免检索链路继续绑定 Xinference 语义。
            reranked_results = embed_fn.rerank_documents(query, rerank_input)
            rerank_map = {doc_id: score for doc_id, _, score in reranked_results}
            ranked = [
                (d, t, rerank_map.get(d, s))
                for d, t, s in combined_pairs
                if rerank_map.get(d, s) >= threshold
            ]
            ranked.sort(key=lambda x: x[2], reverse=True)
            log.info(f"[Rerank] 重排序完成，保留 {len(ranked)} 条。")
        except Exception as e:
            log.error(f"[Rerank] 失败: {e}，回退。")
            ranked = [(d, t, s) for d, t, s in combined_pairs if s >= threshold]
    else:
        log.info(f"[Rerank] 跳过（mode={mode}）。")
        ranked = [(d, t, s) for d, t, s in combined_pairs if s >= threshold]
    return ranked


def _truncate_semantic_tail_in_keyword_mode(ranked):
    """当关键词通道失效时，按分数断崖裁剪语义长尾噪声。"""
    if len(ranked) <= 3:
        return ranked

    scores = [s for _, _, s in ranked]
    top_score = scores[0]
    if top_score <= 0:
        return ranked

    # 规则1：相对阈值，先保留与top分接近的结果
    relative_floor = top_score * 0.75
    kept = [item for item in ranked if item[2] >= relative_floor]
    if len(kept) >= 3:
        return kept

    # 规则2：断崖检测，找到首个明显跌落点进行截断
    cut_idx = len(ranked)
    for i in range(1, len(scores)):
        prev = scores[i - 1]
        cur = scores[i]
        if prev <= 0:
            continue
        drop_ratio = (prev - cur) / prev
        if i >= 2 and drop_ratio >= 0.30:
            cut_idx = i
            break

    return ranked[:cut_idx] if cut_idx > 0 else ranked


def _aggregate_chunks(result_ids, id_to_meta, collection, final_results):
    """聚合分块文档并附加过滤后的元数据

    功能：
    1. 通过 parent_id 将文档块聚合为完整文档
    2. 按 chunk_index 排序后拼接文本
    3. 过滤内部元数据字段（parent_id、chunk_index 等）
    4. 将过滤后的元数据附加到文档文本中（不覆盖已有字段）

    参数：
        result_ids: 文档ID列表
        id_to_meta: 文档ID到元数据的字典映射 {doc_id: metadata}
        collection: ChromaDB collection 对象
        final_results: 原始结果列表 [(doc_id, text, score, source), ...]

    返回：
        更新后的结果列表，文本已聚合并附加元数据
    """
    # 步骤1: 构建文档ID到(完整文本, 过滤元数据)的映射
    result_map = {}
    for did in result_ids:
        meta = id_to_meta.get(did, {})
        if not meta:
            result_map[did] = (None, {})
            continue
        # 获取parent_id，如果没有则使用当前文档ID
        parent_id = meta.get("parent_id", did)
        chunk_total = meta.get("chunk_total", 1)
        # 对于单块文档，直接使用原始文本，不需要聚合
        if chunk_total == 1:
            filtered_meta = {
                k: v
                for k, v in meta.items()
                if k
                not in (
                    "custom_data",
                    "parent_id",
                    "chunk_index",
                    "chunk_total",
                    "chunk_type",
                )
            }
            result_map[did] = (None, filtered_meta)  # None 表示使用原始文本
            continue

        # 对于多块文档，需要聚合
        try:
            # 通过 parent_id 查询所有块（所有块共享同一个 parent_id）
            parent_res = collection.get(
                where={"parent_id": parent_id}, include=["documents", "metadatas"]
            )
            parent_docs = parent_res.get("documents", [])
            parent_metas = parent_res.get("metadatas", [])
            log.debug(f"[聚合] 多块文档 did={did} 查询到 {len(parent_docs)} 个块")

            if parent_docs:
                # 按 chunk_index 排序并拼接所有块
                chunks = [
                    {"idx": (m or {}).get("chunk_index", 0), "text": d.strip()}
                    for d, m in zip(
                        parent_docs, parent_metas or [{}] * len(parent_docs)
                    )
                ]
                chunks.sort(key=lambda c: c["idx"])
                full_text = "\n".join(c["text"] for c in chunks)
                # 过滤内部字段（所有块的元数据都相同，取第一个块的即可）
                filtered_meta = {
                    k: v
                    for k, v in meta.items()
                    if k
                    not in (
                        "custom_data",
                        "parent_id",
                        "chunk_index",
                        "chunk_total",
                        "chunk_type",
                    )
                }
                result_map[did] = (full_text, filtered_meta)
            else:
                result_map[did] = (
                    None,
                    {k: v for k, v in meta.items() if k != "custom_data"},
                )
        # 异常处理：聚合失败时保留原始元数据
        except Exception as e:
            log.warning(f"[Hybrid] 聚合失败: {e}")
            result_map[did] = (
                None,
                {k: v for k, v in meta.items() if k != "custom_data"},
            )
    # 步骤2: 将聚合后的文本和元数据应用到最终结果
    final_output = []
    for d, t, s, src in final_results:
        aggregated_text = result_map.get(d, (None, {}))[0]
        filtered_meta = result_map.get(d, (None, {}))[1]
        final_text = aggregated_text or t
        merged_text = _append_metadata_to_text(final_text, filtered_meta)
        final_output.append((d, merged_text, s, src))
    return final_output


def chroma_search(
    query, dataset_id=None, top_k=10, threshold=0.5, metadata_filter=None
):
    """混合检索：Chroma 语义向量 + BM25 + 短查询增强（n-gram + 子串匹配）

    步骤：
        1. 从 Chroma 召回 top_k 语义候选
        2. 从 BM25 召回 top_k 关键词候选
        3. 【短查询增强】若查询 ≤3 tokens，启用 n-gram + 子串匹配
        4. 分数归一化、融合 (alpha 控制语义权重)
        5. 按得分阈值过滤，取前 top_k 个结果

    参数:
        metadata_filter: dict | None
            ChromaDB where 条件，用于过滤元数据
            示例: {"category": "product"} 或 {"$and": [{"category": "product"}, {"price": {"$gt": 100}}]}
    """

    embed_fn = OpenAICompatibleEmbeddingFunction("none")

    # 记录入参
    log.info(
        f"[Hybrid] 入参: query='{query}', dataset_id={dataset_id}, top_k={top_k}, threshold={threshold}, metadata_filter={metadata_filter}"
    )

    alpha, mode = bm25_jieba.auto_alpha(query)
    collection = get_chroma_collection(dataset_id)

    # Step 1-2: 召回
    sem_pairs, bm25_pairs, ngram_pairs, substr_pairs, query_variants = (
        _recall_all_sources(
            query, dataset_id, collection, embed_fn, top_k, metadata_filter, alpha, mode
        )
    )

    if not sem_pairs and not bm25_pairs and not ngram_pairs and not substr_pairs:
        log.info("[Hybrid] 无候选结果。")
        return []

    # Step 3: 分数融合
    combined, combined_pairs = _merge_scores(
        sem_pairs,
        bm25_pairs,
        ngram_pairs,
        substr_pairs,
        alpha,
        mode,
        query_variants,
        dataset_id,
    )

    # Step 4: Rerank
    ranked = _apply_rerank(query, combined_pairs, threshold, mode, embed_fn)

    # 若短查询进入 keyword 模式且关键词通道全部失效，避免语义长尾污染结果
    if (
        mode == bm25_jieba.SearchSource.KEYWORD
        and not bm25_pairs
        and not ngram_pairs
        and not substr_pairs
    ):
        before_cnt = len(ranked)
        ranked = _truncate_semantic_tail_in_keyword_mode(ranked)
        log.info(
            f"[Hybrid] keyword模式仅语义生效，长尾裁剪 {before_cnt} -> {len(ranked)} 条。"
        )

    if not ranked:
        log.info(f"[Hybrid] 无满足阈值 {threshold} 的候选。")
        return []

    # Step 5: 取top_k并添加source
    final_results = [
        (d, t, s, combined.get(d, {}).get("source", "unknown"))
        for d, t, s in ranked[:top_k]
    ]

    # Step 6: 聚合分块文档
    if final_results:
        result_ids = [doc_id for doc_id, _, _, _ in final_results]
        try:
            metadata_batch = collection.get(ids=result_ids, include=["metadatas"])
            # 构建 id→metadata 映射
            ids_list = metadata_batch.get("ids", [])
            metadatas_list = metadata_batch.get("metadatas", [])
            id_to_meta = dict(zip(ids_list, metadatas_list))
            final_results = _aggregate_chunks(
                ids_list, id_to_meta, collection, final_results
            )
            log.info(f"[Hybrid] 已附加 {len(id_to_meta)} 条完整数据。")
        except Exception as e:
            log.error(f"[Hybrid] 获取完整数据失败: {e}，返回合并文本。")

    # Step 7: 去重
    seen_ids, seen_texts = set(), set()
    unique_results = []
    for doc_id, text, score, source in final_results:
        if doc_id in seen_ids or text.strip() in seen_texts:
            continue
        seen_ids.add(doc_id)
        seen_texts.add(text.strip())
        unique_results.append((doc_id, text, score, source))

    log.info(f"[Hybrid] 去重后返回 {len(unique_results)} 条结果：")
    for i, (doc_id, text, score, source) in enumerate(unique_results):
        log.debug(
            f"[结果#{i + 1}] id={doc_id}, score={score:.4f}, source={source}, text={text[:80]}..."
        )
    return unique_results
