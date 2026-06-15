#!/usr/bin/env python3

"""检索链路轻量诊断入口。

默认不依赖真实 Chroma 数据集，只检查检索配置文件可解析、分词模式判定可用。
需要做单条 A/B 对比时，传入 --dataset-id 和 --query，会委托
tests/test_retrieval_ab_compare.py 执行完整诊断。
"""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

from src.utils import setting


def _load_json(path: str) -> dict:
    with Path(path).open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"{path} 必须是 JSON object")
    return data


def _run_smoke() -> None:
    # [CUSTOM] 与 AGENTS.md 的无参诊断命令对齐，先验证配置与模式判定可用。
    Path(setting.JIEBA_DIR).mkdir(parents=True, exist_ok=True)
    from src.qsql.chromadb import bm25_jieba

    synonyms = _load_json(setting.QUERY_SYNONYM_PATH)
    light_tokens = _load_json(setting.QUERY_LIGHT_TOKENS_PATH)

    samples = [
        "自建房",
        "常州市自建房过户",
        "今年各区县自建房审批通过数量分别是多少",
    ]
    modes = [bm25_jieba.auto_alpha(query)[1].value for query in samples]

    print("[Search] smoke ok")
    print(f"query_synonyms_keys={list(synonyms.keys())}")
    print(f"query_light_tokens_keys={list(light_tokens.keys())}")
    print(f"sample_modes={modes}")


def main() -> None:
    if "--dataset-id" in sys.argv and "--query" in sys.argv:
        runpy.run_path(
            str(Path(__file__).resolve().parent / "tests" / "test_retrieval_ab_compare.py"),
            run_name="__main__",
        )
        return

    _run_smoke()


if __name__ == "__main__":
    main()
