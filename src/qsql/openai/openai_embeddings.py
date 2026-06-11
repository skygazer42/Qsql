from openai import OpenAI

from ..base import VannaBase


class OpenAI_Embeddings(VannaBase):
    def __init__(self, client=None, config=None):
        VannaBase.__init__(self, config=config)

        if client is not None:
            self.client = client
            return

        # [CUSTOM] 嵌入接口与聊天接口保持同一套 OpenAI-compatible 配置方式。
        client_kwargs = {}
        if config is not None and config.get("api_key"):
            client_kwargs["api_key"] = config["api_key"]
        if config is not None and config.get("base_url"):
            client_kwargs["base_url"] = config["base_url"]

        self.client = OpenAI(**client_kwargs)

    def generate_embedding(self, data: str, **kwargs) -> list[float]:
        model = (
            (self.config or {}).get("model")
            or (self.config or {}).get("engine")
            or kwargs.get("model")
            or "text-embedding-3-small"
        )
        embedding = self.client.embeddings.create(model=model, input=data)
        return embedding.data[0].embedding
