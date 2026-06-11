"""OpenAI-compatible chat provider."""

from __future__ import annotations

import os
from typing import Any

import httpx
from openai import OpenAI

from ..base import VannaBase


class OpenAICompatibleChat(VannaBase):
    # 统一 OpenAI-compatible 聊天接口，兼容 OpenAI 与 vLLM。

    def __init__(self, client=None, config=None):
        normalized_config = dict(config or {})
        VannaBase.__init__(self, config=normalized_config)

        self.temperature = normalized_config.get("temperature", 0.7)
        self.model = normalized_config.get("model") or normalized_config.get("engine")

        if client is not None:
            self.client = client
            return

        api_key = (
            normalized_config.get("api_key")
            or os.getenv("OPENAI_API_KEY")
        )
        base_url = (
            normalized_config.get("base_url")
            or normalized_config.get("api_base")
            or None
        )

        if base_url and not api_key:
            # 兼容本地 OpenAI 协议服务，很多服务要求传 Bearer 但并不校验值。
            api_key = "openai-compatible"

        client_kwargs: dict[str, Any] = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        if base_url:
            client_kwargs["base_url"] = base_url

        self.client = OpenAI(
            http_client=httpx.Client(trust_env=False),
            **client_kwargs,
        )

    def system_message(self, message: str) -> Any:
        return {"role": "system", "content": message}

    def user_message(self, message: str) -> Any:
        return {"role": "user", "content": message}

    def assistant_message(self, message: str) -> Any:
        return {"role": "assistant", "content": message}

    def _resolve_model(self, **kwargs) -> str:
        return (
            kwargs.get("model")
            or kwargs.get("engine")
            or (self.config or {}).get("model")
            or (self.config or {}).get("engine")
            or self.model
            or os.getenv("OPENAI_MODEL")
            or "gpt-3.5-turbo"
        )

    def submit_prompt(self, prompt, **kwargs) -> str:
        if prompt is None:
            raise Exception("Prompt is None")

        if len(prompt) == 0:
            raise Exception("Prompt is empty")

        model = self._resolve_model(**kwargs)
        response = self.client.chat.completions.create(
            model=model,
            messages=prompt,
            stop=None,
            temperature=self.temperature,
        )

        for choice in response.choices:
            text = getattr(choice, "text", None)
            if text:
                return text

            message = getattr(choice, "message", None)
            content = getattr(message, "content", None)
            if content:
                return content

        return response.choices[0].message.content
