# [CUSTOM] 引入 pydantic-ai 直接输出结构化 SQL 结果，作为固定执行路径。
"""Text2SQL SQL 输出的结构化标准化（pydantic-ai 驱动）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel as OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from .schemas import SQLNormalizationResult, ValidateRequest


class _PydanticAISQLOutputRefiner:
    def __init__(self, model_name: str, base_url: str, api_key: str, temperature: float):
        # [CUSTOM] 仓库已固定到当前 pydantic-ai 依赖栈，统一使用直接导入，不再保留旧命名 fallback。
        provider = OpenAIProvider(
            base_url=base_url,
            api_key=api_key or None,
            http_client=httpx.AsyncClient(trust_env=False),
        )
        self._agent = Agent(
            OpenAIModel(
                model_name=model_name,
                provider=provider,
                settings={"temperature": temperature},
            ),
            output_type=SQLNormalizationResult,
            instructions="""
你是 SQL 规范化智能体。输入包含用户问题和原始 SQL。
仅返回结构化 JSON，字段：
- question: 用户问题
- raw_sql: 原始 SQL
- sql: 经过清洗后的 SQL（不带 markdown，不带解释）
- statement_type: SELECT/WITH/INSERT/UPDATE/DELETE/CREATE/OTHER
- is_select: sql 是否可作为查询语句（SELECT 或 WITH）
- normalizer: 输出字符串 `pydantic_ai`

规则：
1) 不允许额外说明文字，仅输出 JSON。
2) 优先保留原始 SQL 的业务意图。
3) 对于明显非 SQL 文本，返回 UNKNOWN/False。
""",
            # [CUSTOM] 使用兼容模型设置，避免与现有 config 温度参数冲突。
            model_settings={"temperature": temperature},
        )

    def normalize(self, question: str, raw_sql: str) -> SQLNormalizationResult:
        # [CUSTOM] 对 pydantic-ai 结构化返回做兼容提取，避免 output/data 命名差异导致主链路中断。
        result = self._agent.run_sync(
            f"问题：{question}\n\n原始输出：{raw_sql}"
        )
        normalized = getattr(result, "output", None)
        if normalized is None:
            normalized = getattr(result, "data", None)

        if normalized is None:
            raise RuntimeError("pydantic-ai 返回结果缺少 output 字段")

        if not isinstance(normalized, SQLNormalizationResult):
            try:
                normalized = ValidateRequest.parse(SQLNormalizationResult, normalized)
            except Exception as exc:  # pragma: no cover - 外部模型返回异常结构直接透传失败。
                raise RuntimeError(f"pydantic-ai 返回结构不符合预期: {exc}") from exc

        if not normalized.normalizer:
            normalized.normalizer = "pydantic_ai"
        if normalized.sql == "":
            raise RuntimeError("pydantic-ai 返回 SQL 为空")

        return normalized


@dataclass
class SqlOutputRefiner:
    """SQL 输出规整器执行入口。"""

    refiner: _PydanticAISQLOutputRefiner

    def normalize(self, question: str, raw_sql: Any) -> SQLNormalizationResult:
        return self.refiner.normalize(question=question, raw_sql=raw_sql)


def build_sql_output_refiner(
    model: str, base_url: str, api_key: str, temperature: float
) -> SqlOutputRefiner:
    """构建 SQL 输出规范化器。"""
    return SqlOutputRefiner(
        refiner=_PydanticAISQLOutputRefiner(
            model_name=model,
            base_url=base_url,
            api_key=api_key,
            temperature=temperature,
        )
    )
