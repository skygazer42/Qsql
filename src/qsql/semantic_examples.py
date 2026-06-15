"""Dataset-scoped few-shot semantic draft examples."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from .schemas import SemanticExample, SemanticExampleMatch, ValidateRequest


DEFAULT_SEMANTIC_EXAMPLE_DIR = (
    Path(__file__).resolve().parents[2] / "resources" / "semantic_examples"
)


def _tokens(text: str) -> set[str]:
    # [CUSTOM] 轻量文件示例检索先用中英文 token overlap，后续可替换为 Chroma/向量实现。
    raw_tokens = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text.lower())
    return {item for item in raw_tokens if item.strip()}


def load_semantic_examples(
    dataset_id: str,
    *,
    base_dir: str | Path | None = None,
) -> list[SemanticExample]:
    example_dir = Path(base_dir) if base_dir is not None else DEFAULT_SEMANTIC_EXAMPLE_DIR
    example_path = example_dir / f"{dataset_id}.jsonl"
    if not example_path.exists():
        return []

    examples: list[SemanticExample] = []
    with example_path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            payload = json.loads(stripped)
            payload.setdefault("dataset_id", dataset_id)
            try:
                examples.append(ValidateRequest.parse(SemanticExample, payload))
            except Exception as exc:
                raise ValueError(
                    f"语义示例格式不合法: {example_path}:{line_no} {exc}"
                ) from exc
    return examples


class FileSemanticExampleRetriever:
    """Retrieve few-shot examples from dataset-scoped JSONL files."""

    def __init__(self, base_dir: str | Path | None = None):
        self._base_dir = Path(base_dir) if base_dir is not None else DEFAULT_SEMANTIC_EXAMPLE_DIR

    @staticmethod
    def _score(question_tokens: set[str], example: SemanticExample) -> float:
        example_tokens = _tokens(example.question)
        if not question_tokens or not example_tokens:
            return 0.0
        overlap = question_tokens & example_tokens
        return len(overlap) / len(question_tokens | example_tokens)

    def retrieve(
        self,
        *,
        dataset_id: str,
        question: str,
        top_k: int = 3,
    ) -> list[SemanticExampleMatch]:
        question_tokens = _tokens(question)
        matches = [
            SemanticExampleMatch(
                example=example,
                score=self._score(question_tokens, example),
            )
            for example in load_semantic_examples(dataset_id, base_dir=self._base_dir)
        ]
        matches = [match for match in matches if match.score > 0]
        matches.sort(key=lambda item: (-item.score, item.example.question))
        return matches[: max(0, int(top_k))]


def format_semantic_examples(matches: Iterable[SemanticExampleMatch]) -> str:
    lines = ["相似成功示例:"]
    match_list = list(matches)
    if not match_list:
        lines.append("无")
        return "\n".join(lines)

    for index, match in enumerate(match_list, 1):
        draft_json = json.dumps(
            match.example.semantic_query.model_dump(exclude_none=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        lines.append(
            f"{index}. question={match.example.question} draft={draft_json}"
        )
    return "\n".join(lines)
