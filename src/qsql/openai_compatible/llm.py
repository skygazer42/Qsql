import hashlib
import re
import time

from ..openai.openai_compatible import OpenAICompatibleChat
from src.utils import Log

# [CUSTOM] QSQL 诊断日志：仓库统一改为直接导入风格，不再保留 try-import fallback。
qsql_log = Log()


def _qsql_hash(value) -> str:
    if value is None:
        return "none"
    return hashlib.sha256(str(value).encode("utf-8", errors="replace")).hexdigest()[:12]


def _qsql_log(level: str, message: str) -> None:
    if qsql_log is None:
        return
    getattr(qsql_log, level)(message)


def _qsql_prompt_stats(prompt) -> tuple[int, int]:
    message_count = len(prompt or [])
    total_chars = 0
    for message in prompt or []:
        if isinstance(message, dict):
            total_chars += len(str(message.get("content", "")))
        else:
            total_chars += len(str(message))
    return message_count, total_chars


class OpenAICompatibleLLM(OpenAICompatibleChat):
    # [CUSTOM] 面向 Text2SQL 主链路的 OpenAI-compatible 运行时 LLM，实现 SQL 提取与诊断日志。
    def __init__(self, config=None):
        normalized_config = dict(config or {})

        if "base_url" not in normalized_config:
            raise ValueError("config must contain base_url for openai-compatible llm")

        self.host = str(normalized_config["base_url"]).strip().rstrip("/")
        if not self.host.startswith(("http://", "https://")):
            raise ValueError("base_url 必须以 http:// 或 https:// 开头")

        if "model" not in normalized_config:
            raise ValueError("check the config for openai-compatible llm")

        normalized_config["base_url"] = self.host
        normalized_config["api_key"] = normalized_config.get("api_key", "")

        super().__init__(config=normalized_config)
        self.api_key = normalized_config.get("api_key") or None

        _qsql_log(
            "info",
            "[QSQL] OpenAICompatibleLLM初始化 "
            f"model={self.model} temperature={self.temperature} "
            f"host_hash={_qsql_hash(self.host)} has_api_key={self.api_key is not None}",
        )

    def system_message(self, message: str) -> any:
        return {"role": "system", "content": message}

    def user_message(self, message: str) -> any:
        return {"role": "user", "content": message}

    def assistant_message(self, message: str) -> any:
        return {"role": "assistant", "content": message}

    def extract_sql_query(self, text):
        pattern = re.compile(
            r"(?:select|with)\b.*?(?:;|```|$)", re.IGNORECASE | re.DOTALL
        )
        match = pattern.search(text)
        if match:
            return match.group(0).replace("```", "")
        return text

    def generate_sql(self, question: str, **kwargs) -> str:
        sql = super().generate_sql(question, **kwargs)
        sql = sql.replace("\\_", "_")
        sql = sql.replace("\\", "")
        return self.extract_sql_query(sql)

    def submit_prompt(self, prompt, **kwargs) -> str:
        start_time = time.time()
        message_count, prompt_chars = _qsql_prompt_stats(prompt)
        _qsql_log(
            "info",
            "[QSQL] OpenAICompatibleLLM请求 "
            f"model={self.model} temperature={self.temperature} "
            f"message_count={message_count} prompt_chars={prompt_chars}",
        )

        try:
            content = super().submit_prompt(prompt, **kwargs)
        except Exception as exc:
            _qsql_log(
                "error",
                "[QSQL] OpenAICompatibleLLM请求失败 "
                f"model={self.model} temperature={self.temperature} "
                f"elapsed_ms={int((time.time() - start_time) * 1000)} "
                f"error={type(exc).__name__}: {exc}",
            )
            raise

        _qsql_log(
            "info",
            "[QSQL] OpenAICompatibleLLM响应 "
            f"model={self.model} response_hash={_qsql_hash(content)} "
            f"response_len={len(str(content or ''))} "
            f"elapsed_ms={int((time.time() - start_time) * 1000)}",
        )
        return content
