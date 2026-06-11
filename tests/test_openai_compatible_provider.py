from src.qsql.schemas import AppConfigModel, ValidateRequest
from src.qsql.openai.openai_compatible import OpenAICompatibleChat
from src.qsql.openai_compatible.embedding import OpenAICompatibleEmbeddingFunction
from src.qsql.openai_compatible.llm import OpenAICompatibleLLM


class _ConcreteOpenAICompatibleChat(OpenAICompatibleChat):
    def add_ddl(self, ddl: str, **kwargs) -> str:
        return ddl

    def add_documentation(self, documentation: str, **kwargs) -> str:
        return documentation

    def add_question_sql(self, question: str, sql: str, **kwargs) -> str:
        return question

    def generate_embedding(self, data: str, **kwargs) -> list[float]:
        return [0.0]

    def get_related_ddl(self, question: str, **kwargs) -> list:
        return []

    def get_related_documentation(self, question: str, **kwargs) -> list:
        return []

    def get_similar_question_sql(self, question: str, **kwargs) -> list:
        return []

    def get_training_data(self, **kwargs):
        return []

    def remove_training_data(self, id: str, **kwargs) -> bool:
        return True


class _ConcreteOpenAICompatibleLLM(OpenAICompatibleLLM):
    def add_ddl(self, ddl: str, **kwargs) -> str:
        return ddl

    def add_documentation(self, documentation: str, **kwargs) -> str:
        return documentation

    def add_question_sql(self, question: str, sql: str, **kwargs) -> str:
        return question

    def generate_embedding(self, data: str, **kwargs) -> list[float]:
        return [0.0]

    def get_related_ddl(self, question: str, **kwargs) -> list:
        return []

    def get_related_documentation(self, question: str, **kwargs) -> list:
        return []

    def get_similar_question_sql(self, question: str, **kwargs) -> list:
        return []

    def get_training_data(self, **kwargs):
        return []

    def remove_training_data(self, id: str, **kwargs) -> bool:
        return True


def test_openai_compatible_chat_uses_base_url_config():
    provider = _ConcreteOpenAICompatibleChat(
        config={
            "base_url": "https://llm.example.com/v1",
            "api_key": "secret",
            "model": "demo-model",
            "temperature": 0.3,
        }
    )

    assert provider.model == "demo-model"
    assert provider.temperature == 0.3
    assert str(provider.client.base_url).rstrip("/") == "https://llm.example.com/v1"


def test_openai_compatible_llm_uses_runtime_config():
    provider = _ConcreteOpenAICompatibleLLM(
        config={
            "base_url": "https://llm.example.com/v1",
            "api_key": "secret",
            "model": "demo-model",
            "temperature": 0.2,
        }
    )

    assert provider.model == "demo-model"
    assert provider.temperature == 0.2
    assert str(provider.client.base_url).rstrip("/") == "https://llm.example.com/v1"


def test_openai_compatible_embedding_uses_runtime_config():
    provider = OpenAICompatibleEmbeddingFunction(
        config={
            "base_url": "https://embed.example.com/v1",
            "api_key": "secret",
            "model": "embed-model",
        }
    )

    assert provider.model == "embed-model"
    assert provider.base_url == "https://embed.example.com/v1"
    assert provider.api_key == "secret"
    assert provider.embedding_url == "https://embed.example.com/v1/embeddings"


def test_app_config_model_uses_neutral_llm_fields():
    config = ValidateRequest.parse(
        AppConfigModel,
        {
            "llm_base_url": "https://llm.example.com/v1",
            "model": "demo-model",
            "llm_api_key": "secret",
            "temperature": 0.5,
            "n_results_ddl": 10,
            "n_results_sql": 10,
            "n_results_documentation": 10,
            "question_sql_max_distance": 0.45,
            "question_sql_distance_filter_enabled": False,
        },
    )

    assert config.llm_base_url == "https://llm.example.com/v1"
    assert config.llm_api_key == "secret"
