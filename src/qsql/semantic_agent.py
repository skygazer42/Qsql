"""pydantic-ai semantic parser for dataset-scoped query catalogs."""

from __future__ import annotations

import httpx

from .schemas import SemanticCatalog, SemanticQueryDraft, ValidateRequest
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel as OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider


class SemanticQueryAgent:
    """Parse natural language into a structured semantic query draft."""

    def __init__(self, model_name: str, base_url: str, api_key: str, temperature: float):
        self._temperature = temperature
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
            output_type=SemanticQueryDraft,
            instructions="""
你是企业数据问答的语义解析器，不要生成 SQL。
你只能从提供的候选指标、维度、口径中选择，并返回结构化 JSON。

规则：
1) 只返回结构化 JSON。
2) 如果用户问题缺少必要时间范围或存在明确歧义，设置 needs_clarification=true。
3) 如果需要澄清，clarification_question 必须是一个可以直接问用户的问题。
4) 除非候选目录中明确存在，不要发明新的 metric_key、dimension_key、metric_version_key。
5) 当前 analysis_type 仅允许 summary / group_by / trend。
""",
            model_settings={"temperature": temperature},
        )

    @staticmethod
    def _catalog_prompt(catalog: SemanticCatalog) -> str:
        # [CUSTOM] 把正式语义表/指标/维度/口径目录直接暴露给解析器，
        # 让模型只做候选选择，不再隐式猜测来源表。
        tables = ", ".join(
            f"{item.key}({item.label}->{item.physical_table})" for item in catalog.tables
        ) or "无"
        entities = ", ".join(
            f"{item.key}({item.table_key}.{item.field},{item.entity_type})"
            for item in catalog.entities
        ) or "无"
        relationships = ", ".join(
            f"{item.key}({item.left_entity_key}->{item.right_entity_key},{item.join_type})"
            for item in catalog.relationships
        ) or "无"
        metrics = ", ".join(
            f"{item.key}({item.label})" for item in catalog.metrics
        ) or "无"
        dimensions = ", ".join(
            f"{item.key}({item.label})" for item in catalog.dimensions
        ) or "无"
        versions = ", ".join(
            f"{item.key}({item.label})" for item in catalog.metric_versions
        ) or "无"
        aliases = ", ".join(
            f"{item.alias}->{item.target_type}:{item.target_key}"
            for item in catalog.aliases
        ) or "无"

        return (
            f"catalog_version={catalog.catalog_version}\n"
            f"dataset_id={catalog.dataset_id}\n"
            f"候选语义表: {tables}\n"
            f"候选实体: {entities}\n"
            f"候选关系: {relationships}\n"
            f"候选指标: {metrics}\n"
            f"候选维度: {dimensions}\n"
            f"候选口径: {versions}\n"
            f"候选别名: {aliases}"
        )

    @staticmethod
    def _coerce_output(result) -> SemanticQueryDraft:
        draft = getattr(result, "output", None)
        if draft is None:
            draft = getattr(result, "data", None)
        if draft is None:
            raise RuntimeError("pydantic-ai 返回结果缺少 output 字段")
        if not isinstance(draft, SemanticQueryDraft):
            draft = ValidateRequest.parse(SemanticQueryDraft, draft)
        return draft

    def _run_prompt(self, prompt: str, *, temperature: float | None) -> SemanticQueryDraft:
        result = self._agent.run_sync(
            prompt,
            model_settings={
                "temperature": self._temperature if temperature is None else temperature
            },
        )
        return self._coerce_output(result)

    def parse_candidates(
        self,
        question: str,
        catalog: SemanticCatalog,
        history: list[str] | None = None,
        *,
        candidate_count: int,
        sampling_temperature: float | None = None,
    ) -> list[SemanticQueryDraft]:
        history_text = "\n".join(history or []) or "无"
        prompt = (
            f"{self._catalog_prompt(catalog)}\n\n"
            f"历史对话:\n{history_text}\n\n"
            f"用户问题:\n{question}"
        )
        total = max(1, int(candidate_count))
        drafts = [self._run_prompt(prompt, temperature=self._temperature)]
        for _ in range(total - 1):
            drafts.append(self._run_prompt(prompt, temperature=sampling_temperature))
        return drafts

    def parse(
        self, question: str, catalog: SemanticCatalog, history: list[str] | None = None
    ) -> SemanticQueryDraft:
        return self.parse_candidates(
            question,
            catalog,
            history=history,
            candidate_count=1,
            sampling_temperature=None,
        )[0]
