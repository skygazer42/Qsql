import json
import os
import pickle
import re
import time
from collections import defaultdict
from enum import Enum

import jieba.posseg as pseg
from jieba import add_word, dt
from rank_bm25 import BM25Okapi

from src.utils import setting
from src.utils.log import Log


class SearchSource(str, Enum):
    SEMANTIC = "semantic"
    KEYWORD = "keyword"
    HYBRID = "hybrid"
    BALANCED = "balanced"


log = Log()
dt.cache_file = os.path.join(setting.JIEBA_DIR, "jieba.cache")
# ============================================================
# BM25 模块（带自动分词、缓存、TTL 过期刷新）
# ============================================================
CACHE_DIR = setting.BM25_CACHE_DIR
_BM25_CACHE = {}
_NGRAM_CACHE = {}  # n-gram 索引缓存
BM25_TTL_SECONDS = 600  # BM25 缓存时间（秒），默认 10 分钟
_ALLOWED_POS = {
    "ns",
    "n",
    "v",
    "vn",
    "b",
    "nr",
    "nz",
    "nt",
    "nw",
    "j",
    "c",
    "a",
    "m",
    "r",
}

# 查询归一化词典：将高频缩写映射到知识库主表达
_DEFAULT_QUERY_SYNONYM_MAP = {}
_QUERY_SYNONYM_CACHE = {
    "mtime": 0.0,
    "data": {"global": {}, "datasets": {}},
}


def _load_query_synonym_map(dataset_id: str | None = None) -> dict[str, str]:
    path = setting.QUERY_SYNONYM_PATH
    base_map = dict(_DEFAULT_QUERY_SYNONYM_MAP)

    if not os.path.exists(path):
        return base_map
    try:
        mtime = os.path.getmtime(path)
        if _QUERY_SYNONYM_CACHE["mtime"] != mtime:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if not isinstance(loaded, dict):
                loaded = {}
            global_map = loaded.get("global", {})
            datasets_map = loaded.get("datasets", {})
            if not isinstance(global_map, dict):
                global_map = {}
            if not isinstance(datasets_map, dict):
                datasets_map = {}
            _QUERY_SYNONYM_CACHE["mtime"] = mtime
            _QUERY_SYNONYM_CACHE["data"] = {
                "global": global_map,
                "datasets": datasets_map,
            }
        cached = _QUERY_SYNONYM_CACHE["data"] or {}
        merged = dict(base_map)
        merged.update(cached.get("global", {}))
        if dataset_id:
            ds_map = cached.get("datasets", {}).get(dataset_id, {})
            if isinstance(ds_map, dict):
                merged.update(ds_map)
        return merged
    except Exception as e:
        log.error(f"[QuerySynonym] 加载词典失败: {e}")
        return base_map


def expand_query_variants(query: str, dataset_id: str | None = None) -> list[str]:
    """生成查询变体（原查询 + 归一化查询），用于关键词召回增强。"""
    q = (query or "").strip()
    if not q:
        return []

    normalized = q
    synonym_map = _load_query_synonym_map(dataset_id)
    # 长词优先替换，避免短词先替换导致结果不稳定
    for src in sorted(synonym_map.keys(), key=len, reverse=True):
        if src in normalized:
            normalized = normalized.replace(src, synonym_map[src])

    variants = [q]
    if normalized and normalized != q:
        variants.append(normalized)

    # 保序去重
    return list(dict.fromkeys(variants))


dict_plus_path = os.path.join(setting.JIEBA_DIR, "dict_plus.txt")
if os.path.exists(dict_plus_path):
    with open(dict_plus_path, "r", encoding="utf-8") as f:
        plus_words = f.read().splitlines()
    for item in plus_words:
        # 提高频率以确保自定义词不被拆分
        add_word(item, freq=2000000, tag="n")

# 加载地名停用词
# _LOCATION_STOPWORDS = set()
# location_stopwords_path = os.path.join(setting.JIEBA_DIR, "location_stopwords.txt")
# if os.path.exists(location_stopwords_path):
#     with open(location_stopwords_path, "r", encoding="utf-8") as f:
#         _LOCATION_STOPWORDS = set(f.read().splitlines())


# ====================== 权重选择 ======================
def auto_alpha(query: str) -> tuple[float, str]:
    tokens = tokenize_text(query)
    length = len(tokens)
    if length <= 2:
        return 0.2, SearchSource.KEYWORD
    elif length <= 8:
        return 0.6, SearchSource.BALANCED
    return 0.8, SearchSource.SEMANTIC


# ====================== 基础工具 ======================
def bm25_cache_path(dataset_id: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{dataset_id}.pkl")


def ngram_cache_path(dataset_id: str) -> str:
    """n-gram 索引文件路径"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{dataset_id}_ngram.pkl")


def save_bm25_index(dataset_id: str, collection):
    """从 collection 构建 BM25 索引并保存至磁盘，覆盖旧索引"""
    start_time = time.time()
    all_data = collection.get(include=["documents"])
    docs = all_data.get("documents", [])
    ids = all_data.get("ids", [])

    if not docs or not ids:
        log.error(f"[BM25] 集合 {dataset_id} 无文档，跳过索引构建。")
        return
    try:
        tokenized_corpus = [tokenize_text(doc) for doc in docs]
        bm25 = BM25Okapi(tokenized_corpus)
    except Exception as e:
        log.error(f"[BM25] 构建索引失败: {e}")
        return
    end_time = time.time()
    duration = round(end_time - start_time, 2)
    # 写缓存并附加耗时与日期
    _BM25_CACHE[dataset_id] = {
        "data": (bm25, ids, docs),
        "ts": end_time,
        "build_duration_s": duration,
        "build_time_str": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end_time)),
    }
    log.info(f"[BM25] 构建索引完成，共 {len(docs)} 条，用时 {duration} 秒。")
    """将 BM25 索引序列化保存到磁盘"""
    path = bm25_cache_path(dataset_id)
    try:
        with open(path, "wb") as f:
            pickle.dump((bm25, ids, docs), f)
        log.info(f"[BM25] 持久化保存索引: {path}")
    except Exception as e:
        log.error(f"[BM25] 保存持久化索引失败: {e}")


def load_bm25_index(dataset_id: str):
    """尝试从磁盘加载持久化索引"""
    path = bm25_cache_path(dataset_id)
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                bm25_obj, ids, docs = pickle.load(f)
            log.info(f"[BM25] 从磁盘加载索引: {path}")
            return bm25_obj, ids, docs
        except Exception as e:
            print(f"[BM25] 加载持久化索引失败: {e}")
    return None


# ====================== 分词逻辑 ======================
def _is_mostly_chinese(text: str, threshold: float = 0.3) -> bool:
    """判断文本中中文字符占比是否超过阈值"""
    if not text:
        return False
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    return len(chinese_chars) / max(len(text), 1) > threshold


def tokenize_text(text: str) -> list[str]:
    """智能分词：中文用 jieba；否则按空格拆分"""
    text = _clean_text(text)
    if _is_mostly_chinese(text):
        words = pseg.cut(text)
        tokens = [
            w.word for w in words if w.flag in _ALLOWED_POS and len(w.word.strip()) >= 1
        ]
        return tokens
    return text.split()


def _clean_text(text: str) -> str:
    """去除网址、邮件地址、特殊符号和停用词"""
    # 匹配所有 http(s):// 或 www. 开头的链接
    text = re.sub(r"https?://\S+|www\.\S+", "", text)
    # 清理邮箱
    text = re.sub(r"\S+@\S+", "", text)
    # 清理 JSON 特殊符号和标记符号
    text = re.sub(r'[{}\[\]"\\==##]+', " ", text)
    # 清理多余空格
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ====================== 核心索引逻辑 ======================
def _find_bm25_index(dataset_id: str, collection):
    """确保存在 BM25 索引；若缓存过期或不存在则重建"""
    collection_name = dataset_id
    cache_entry = _BM25_CACHE.get(collection_name)

    # 1. 先检查内存缓存
    if cache_entry:
        age = time.time() - cache_entry.get("ts", 0)
        if age < BM25_TTL_SECONDS:
            return cache_entry["data"]
        else:
            print(f"[BM25] 内存缓存过期（{int(age)}s），重新加载。")
            _BM25_CACHE.pop(collection_name, None)

    # 2. 再尝试加载磁盘持久化索引
    disk_obj = load_bm25_index(dataset_id)
    if disk_obj:
        _BM25_CACHE[collection_name] = {"data": disk_obj, "ts": time.time()}
        return disk_obj


def bm25_recall(
    query: str, dataset_id: str, collection, top_k: int, where: dict | None = None
):
    bm25_info = _find_bm25_index(dataset_id, collection)
    if not bm25_info:
        print(f"[BM25] {dataset_id} 索引未找到。")
        return []
    bm25, ids, docs = bm25_info
    query_tokens = tokenize_text(query)
    if not query_tokens:
        return []

    scores = bm25.get_scores(query_tokens)

    ranked = sorted(
        [
            (ids[i], docs[i], float(scores[i]))
            for i in range(len(docs))
            if scores[i] > 0
        ],
        key=lambda x: x[2],
        reverse=True,
    )[:top_k]

    # 如果有 metadata 过滤条件，需要过滤结果
    if where:
        valid_ids = set(collection.get(where=where, include=[]).get("ids", []))
        ranked = [(did, doc, score) for did, doc, score in ranked if did in valid_ids]

    # 从数据库实时获取最新文档内容，避免索引过期
    if ranked:
        result_ids = [did for did, _, _ in ranked]
        fresh_data = collection.get(ids=result_ids, include=["documents"])
        id_to_doc = dict(
            zip(fresh_data.get("ids", []), fresh_data.get("documents", []))
        )
        ranked = [(did, id_to_doc.get(did, doc), score) for did, doc, score in ranked]

    log.info(f"[BM25] 召回 {len(ranked)} 条文档。")
    return ranked


# ====================== n-gram 和子串匹配 ======================
def generate_char_ngrams(text: str, n: int = 2) -> list[str]:
    """生成字符级 n-gram"""
    text = _clean_text(text).replace(" ", "").replace("\n", "")
    if len(text) < n:
        return [text] if text else []
    return [text[i : i + n] for i in range(len(text) - n + 1)]


def build_ngram_index(dataset_id: str, collection, n: int = 2):
    """构建字符 n-gram 倒排索引并保存到磁盘"""
    start_time = time.time()
    all_data = collection.get(include=["documents"])
    docs = all_data.get("documents", [])
    ids = all_data.get("ids", [])

    if not docs or not ids:
        log.error(f"[N-gram] 集合 {dataset_id} 无文档，跳过索引构建。")
        return

    # 构建倒排索引: {ngram: [doc_id1, doc_id2, ...]}
    ngram_index = defaultdict(set)
    for doc_id, doc in zip(ids, docs):
        for ngram in generate_char_ngrams(doc, n):
            ngram_index[ngram].add(doc_id)

    # 转换为普通 dict以便序列化
    ngram_index = {k: list(v) for k, v in ngram_index.items()}

    end_time = time.time()
    duration = round(end_time - start_time, 2)

    # 写入内存缓存
    _NGRAM_CACHE[dataset_id] = {
        "data": (ngram_index, ids, docs),
        "ts": end_time,
        "build_duration_s": duration,
    }

    log.info(
        f"[N-gram] 构建索引完成，共 {len(docs)} 条文档，{len(ngram_index)} 个 {n}-gram，用时 {duration} 秒。"
    )

    # 持久化到磁盘
    path = ngram_cache_path(dataset_id)
    try:
        with open(path, "wb") as f:
            pickle.dump((ngram_index, ids, docs), f)
        log.info(f"[N-gram] 持久化保存索引: {path}")
    except Exception as e:
        log.error(f"[N-gram] 保存持久化索引失败: {e}")


def load_ngram_index(dataset_id: str):
    """从磁盘加载 n-gram 索引"""
    path = ngram_cache_path(dataset_id)
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                ngram_index, ids, docs = pickle.load(f)
            log.info(f"[N-gram] 从磁盘加载索引: {path}")
            return ngram_index, ids, docs
        except Exception as e:
            log.error(f"[N-gram] 加载持久化索引失败: {e}")
    return None


def _find_ngram_index(dataset_id: str, collection):
    """查找或加载 n-gram 索引（带缓存）"""
    cache_entry = _NGRAM_CACHE.get(dataset_id)

    # 1. 检查内存缓存
    if cache_entry:
        age = time.time() - cache_entry.get("ts", 0)
        if age < BM25_TTL_SECONDS:
            return cache_entry["data"]
        else:
            log.info(f"[N-gram] 内存缓存过期（{int(age)}s），重新加载。")
            _NGRAM_CACHE.pop(dataset_id, None)

    # 2. 尝试从磁盘加载
    disk_obj = load_ngram_index(dataset_id)
    if disk_obj:
        _NGRAM_CACHE[dataset_id] = {"data": disk_obj, "ts": time.time()}
        return disk_obj

    return None


def ngram_recall(
    query: str,
    dataset_id: str,
    collection,
    top_k: int,
    n: int = 2,
    where: dict | None = None,
):
    """字符 n-gram 召回（适用于短查询）"""
    ngram_info = _find_ngram_index(dataset_id, collection)
    if not ngram_info:
        log.warning(f"[N-gram] {dataset_id} 索引未找到，跳过召回。")
        return []

    ngram_index, ids, docs = ngram_info
    query_ngrams = set(generate_char_ngrams(query, n))

    if not query_ngrams:
        return []

    # 计算每个文档的 n-gram 覆盖率
    doc_scores = defaultdict(float)
    for ngram in query_ngrams:
        for doc_id in ngram_index.get(ngram, []):
            doc_scores[doc_id] += 1.0

    # 归一化：覆盖率 = 命中数 / 查询 n-gram 总数
    for doc_id in doc_scores:
        doc_scores[doc_id] /= len(query_ngrams)

    # 短查询降噪：至少命中 2 个 n-gram（若查询 n-gram 数不足 2，则要求全命中）
    # 例如“教资认定”通常有 3 个 2-gram，1/3=0.3333 的弱匹配会被过滤。
    min_hit = min(2, len(query_ngrams))
    min_coverage = min_hit / len(query_ngrams)
    doc_scores = {
        did: score for did, score in doc_scores.items() if score >= min_coverage
    }

    ranked = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

    # 从数据库实时获取最新文档内容
    if ranked:
        result_ids = [did for did, _ in ranked]
        fresh_data = collection.get(ids=result_ids, include=["documents"])
        id_to_doc = dict(
            zip(fresh_data.get("ids", []), fresh_data.get("documents", []))
        )
        results = [
            (did, id_to_doc.get(did, ""), score)
            for did, score in ranked
            if did in id_to_doc
        ]
    else:
        results = []
    # 如果有 metadata 过滤条件，需要过滤结果
    if where:
        valid_ids = set(collection.get(where=where, include=[]).get("ids", []))
        results = [(did, doc, score) for did, doc, score in results if did in valid_ids]
    log.info(f"[N-gram] 召回 {len(results)} 条文档。")
    return results


def substring_recall(
    query: str, dataset_id: str, collection, top_k: int, where: dict | None = None
):
    """直接子串匹配（最快速，适用于短查询精确匹配）"""
    all_data = collection.get(include=["documents"], where=where)
    docs = all_data.get("documents", [])
    ids = all_data.get("ids", [])

    query_clean = query.strip().lower()
    if not query_clean:
        return []

    matches = []
    for doc_id, doc in zip(ids, docs):
        doc_lower = doc.lower()
        if query_clean in doc_lower:
            # 位置权重（越靠前得分越高）+ 长度权重
            pos = doc_lower.index(query_clean)
            pos_score = 1.0 / (1 + pos / max(len(doc), 1))
            len_score = len(query_clean) / max(len(doc), 1)
            score = 0.7 * pos_score + 0.3 * len_score
            matches.append((doc_id, doc, score))

    results = sorted(matches, key=lambda x: x[2], reverse=True)[:top_k]
    log.info(f"[子串匹配] 召回 {len(results)} 条文档。")
    return results


# ====================== 缓存清理 ======================
def clear_ngram_cache(dataset_id: str | None = None):
    """清理 n-gram 缓存"""
    if dataset_id:
        _NGRAM_CACHE.pop(dataset_id, None)
        path = ngram_cache_path(dataset_id)
        if os.path.exists(path):
            os.remove(path)
            log.info(f"[N-gram] 已删除持久化索引: {path}")
    else:
        _NGRAM_CACHE.clear()
        if os.path.exists(CACHE_DIR):
            for f in os.listdir(CACHE_DIR):
                if f.endswith("_ngram.pkl"):
                    try:
                        os.remove(os.path.join(CACHE_DIR, f))
                    except Exception:
                        pass
        log.info("[N-gram] 已清空所有缓存与持久化索引。")


def clear_bm25_cache(dataset_id: str | None = None):
    """手动释放 BM25 缓存，同时清理磁盘文件"""
    if dataset_id:
        _BM25_CACHE.pop(dataset_id, None)
        path = bm25_cache_path(dataset_id)
        if os.path.exists(path):
            os.remove(path)
            log.info(f"[BM25] 已删除持久化索引: {path}")
        log.info(f"[BM25] 已释放缓存: {dataset_id}")
    else:
        _BM25_CACHE.clear()
        if os.path.exists(CACHE_DIR):
            for f in os.listdir(CACHE_DIR):
                try:
                    os.remove(os.path.join(CACHE_DIR, f))
                except Exception:
                    pass
        print("[BM25] 已清空所有缓存与持久化索引。")


if __name__ == "__main__":
    text = "常州市个人纯购新车补贴"
    seg_list = pseg.cut(text)
    word_list = []
    for seg, flag in seg_list:
        print(seg, flag)
