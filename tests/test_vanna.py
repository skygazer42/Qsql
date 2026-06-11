from src.qsql.local import LocalContext_OpenAI, LocalContext_OpenAICompatible
from src.qsql.openai.openai_chat import OpenAI_Chat
from src.qsql.openai.openai_compatible import OpenAICompatibleChat
from src.qsql.openai_compatible.llm import OpenAICompatibleLLM


def test_openai_chat_is_openai_compatible():
    assert issubclass(OpenAI_Chat, OpenAICompatibleChat)


def test_openai_compatible_llm_is_openai_compatible():
    assert issubclass(OpenAICompatibleLLM, OpenAICompatibleChat)


def test_local_contexts_keep_runtime_mixins():
    assert issubclass(LocalContext_OpenAI, OpenAI_Chat)
    assert issubclass(LocalContext_OpenAICompatible, OpenAICompatibleLLM)
