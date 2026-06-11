#!/usr/bin/env python3

"""检索 A/B 对比脚本（语义-only vs 混合检索）。

放在 tests/ 目录，方便开发者本地直接复用。

示例：
python tests/retrieval_ab_compare.py \
  --dataset-id czszwfw_41712e4e6abe446eb7f01d54b251fa6b \
  --query "常州市自建房过户" \
  --top-k 10 \
  --threshold 0.0
"""

from __future__ import annotations

import argparse
import json
from collections import Counter


def _top_ids(pairs: list[tuple], k: int = 10) -> list[str]:
    ids: list[str] = []
    for item in pairs[:k]:
        ids.append(item[0])
    return ids


def main() -> None:
    parser = argparse.ArgumentParser(description="检索 A/B 对比工具")
    parser.add_argument("--dataset-id", required=True, help="数据集 ID")
    parser.add_argument("--query", required=True, help="检索 query")
    parser.add_argument("--top-k", type=int, default=10, help="返回条数")
    parser.add_argument("--threshold", type=float, default=0.0, help="分数阈值")
    parser.add_argument(
        "--metadata-filter",
        type=str,
        default="",
        help='metadata 过滤条件 JSON 字符串，例如 {"category":"policy"}',
    )
    args = parser.parse_args()

    metadata_filter = None
    if args.metadata_filter.strip():
        metadata_filter = json.loads(args.metadata_filter)

    from src.qsql.chromadb import bm25_jieba
    from src.qsql.chromadb import hybrid_search
    from src.qsql.chromadb.vector_store_service import get_chroma_collection
    from src.qsql.openai_compatible.embedding import OpenAICompatibleEmbeddingFunction

    collection = get_chroma_collection(args.dataset_id)
    embed_fn = OpenAICompatibleEmbeddingFunction("none")

    sem_only = embed_fn.smart_recall(
        collection, args.query, top_k=args.top_k, where=metadata_filter
    )

    alpha, mode = bm25_jieba.auto_alpha(args.query)
    sem_pairs, bm25_pairs, ngram_pairs, substr_pairs, query_variants = (
        hybrid_search._recall_all_sources(
            args.query,
            args.dataset_id,
            collection,
            embed_fn,
            args.top_k,
            metadata_filter,
            alpha,
            mode,
        )
    )

    combined, combined_pairs = hybrid_search._merge_scores(
        sem_pairs,
        bm25_pairs,
        ngram_pairs,
        substr_pairs,
        alpha,
        mode,
        query_variants,
        args.dataset_id,
    )

    ranked = hybrid_search._apply_rerank(
        args.query, combined_pairs, args.threshold, mode, embed_fn
    )

    final_hybrid = hybrid_search.chroma_search(
        args.query,
        args.dataset_id,
        top_k=args.top_k,
        threshold=args.threshold,
        metadata_filter=metadata_filter,
    )

    print("=" * 80)
    print(f"query={args.query}")
    print(f"dataset_id={args.dataset_id}")
    print(f"mode={mode}, alpha={alpha}, top_k={args.top_k}, threshold={args.threshold}")
    print(f"metadata_filter={metadata_filter}")
    print("=" * 80)

    print("\n[阶段计数]")
    print(f"semantic_only                 : {len(sem_only)}")
    print(f"hybrid.sem_pairs              : {len(sem_pairs)}")
    print(f"hybrid.bm25_pairs             : {len(bm25_pairs)}")
    print(f"hybrid.ngram_pairs            : {len(ngram_pairs)}")
    print(f"hybrid.substring_pairs        : {len(substr_pairs)}")
    print(f"hybrid.combined_pairs         : {len(combined_pairs)}")
    print(f"hybrid.ranked(after threshold): {len(ranked)}")
    print(f"hybrid.final                  : {len(final_hybrid)}")

    sem_ids = _top_ids(sem_only, args.top_k)
    hyb_ids = _top_ids(final_hybrid, args.top_k)
    overlap = set(sem_ids) & set(hyb_ids)

    print("\n[TopK 重叠]")
    print(f"semantic_top_ids: {sem_ids}")
    print(f"hybrid_top_ids  : {hyb_ids}")
    print(f"overlap_count   : {len(overlap)}")
    print(f"overlap_ids     : {list(overlap)}")

    reason_counter: Counter[str] = Counter()
    for _, v in combined.items():
        norm = v.get("_norm", {})
        if norm.get("intent_hit", 0.0) <= 0:
            reason_counter["intent_miss"] += 1
        if v.get("semantic", 0.0) <= 0:
            reason_counter["no_semantic_support"] += 1
        if v.get("bm25", 0.0) <= 0:
            reason_counter["no_bm25_support"] += 1
        if (
            v.get("semantic", 0.0) <= 0
            and v.get("bm25", 0.0) <= 0
            and v.get("substr", 0.0) <= 0
            and v.get("ngram", 0.0) > 0
        ):
            reason_counter["ngram_only_noise"] += 1

    print("\n[候选特征统计(粗)]")
    for key, count in reason_counter.items():
        print(f"{key:25s}: {count}")

    print("\n[融合Top5明细]")
    for i, (doc_id, _, score) in enumerate(ranked[:5], start=1):
        raw = combined.get(doc_id, {})
        norm = raw.get("_norm", {})
        print(
            f"#{i} id={doc_id} score={score:.4f} "
            f"src={raw.get('source')} "
            f"sem={raw.get('semantic', 0):.4f} bm25={raw.get('bm25', 0):.4f} "
            f"sub={raw.get('substr', 0):.4f} ng={raw.get('ngram', 0):.4f} "
            f"intent_hit={norm.get('intent_hit')} text_hit_cnt={norm.get('text_hit_cnt')}"
        )


if __name__ == "__main__":
    main()
