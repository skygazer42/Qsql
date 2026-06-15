r"""

# Nomenclature

| Prefix | Definition | Examples |
| --- | --- | --- |
| `vn.get_` | Fetch some data | [`vn.get_related_ddl(...)`][qsql.base.base.VannaBase.get_related_ddl] |
| `vn.add_` | Adds something to the retrieval layer | [`vn.add_question_sql(...)`][qsql.base.base.VannaBase.add_question_sql] <br> [`vn.add_ddl(...)`][qsql.base.base.VannaBase.add_ddl] |
| `vn.generate_` | Generates something using AI based on the information in the model | [`vn.generate_sql(...)`][qsql.base.base.VannaBase.generate_sql] <br> [`vn.generate_explanation()`][qsql.base.base.VannaBase.generate_explanation] |
| `vn.run_` | Runs code (SQL) | [`vn.run_sql`][qsql.base.base.VannaBase.run_sql] |
| `vn.remove_` | Removes something from the retrieval layer | [`vn.remove_training_data`][qsql.base.base.VannaBase.remove_training_data] |
| `vn.connect_` | Connects to a database | [`vn.connect_to_snowflake(...)`][qsql.base.base.VannaBase.connect_to_snowflake] |
| `vn.update_` | Updates something | N/A -- unused |
| `vn.set_` | Sets something | N/A -- unused  |

# Open-Source and Extending

QSQL is open-source and extensible. If you'd like to use the local runtime
without the legacy hosted service, you can extend the base classes below.

The following is an example of where various functions are implemented in the
codebase when using the default local runtime. `qsql.base.VannaBase` is the
base class which provides a `qsql.base.VannaBase.ask` and
`qsql.base.VannaBase.train` function. Those rely on abstract methods which are
implemented in the subclasses `qsql.openai.openai_chat.OpenAI_Chat` and
`qsql.chromadb.chromadb_vector.ChromaDB_VectorStore`.

If you want to use QSQL with other LLMs or databases, you can create your own subclass of `qsql.base.VannaBase` and implement the abstract methods.

```mermaid
flowchart
    subgraph VannaBase
        ask
        train
    end

    subgraph OpenAI_Chat
        get_sql_prompt
        submit_prompt
        generate_question
        generate_plotly_code
    end

    subgraph ChromaDB_VectorStore
        generate_embedding
        add_question_sql
        add_ddl
        add_documentation
        get_similar_question_sql
        get_related_ddl
        get_related_documentation
    end
```

"""

import ast
import hashlib
import json
import os
import re
import sqlite3
import time
from abc import ABC, abstractmethod
from typing import List, Tuple, Union
from urllib.parse import urlparse

import pandas as pd
import plotly
import plotly.express as px
import requests
import sqlparse

from ..types import TrainingPlan
from src.utils import Log
from .optional_connectors import connect_to_bigquery_impl
from .optional_connectors import connect_to_clickhouse_impl
from .optional_connectors import connect_to_duckdb_impl
from .optional_connectors import connect_to_hive_impl
from .optional_connectors import connect_to_mssql_impl
from .optional_connectors import connect_to_mysql_impl
from .optional_connectors import connect_to_oracle_impl
from .optional_connectors import connect_to_postgres_impl
from .optional_connectors import connect_to_presto_impl
from .optional_connectors import connect_to_snowflake_impl
from .runtime_helpers import ask_impl
from .runtime_helpers import get_databases_impl
from .runtime_helpers import get_information_schema_tables_impl
from .runtime_helpers import get_training_plan_generic_impl
from .runtime_helpers import get_training_plan_snowflake_impl
from .runtime_helpers import train_impl

#  QSQL 诊断日志：仓库已统一为直接导入风格，不再保留 try-import fallback。
qsql_log = Log()

# [CUSTOM] Plotly 代码只解释受限的 px.* 图表调用，禁止执行模型返回的任意 Python。
_ALLOWED_PLOTLY_EXPRESS_FUNCTIONS = {
    "area",
    "bar",
    "box",
    "histogram",
    "line",
    "pie",
    "scatter",
    "strip",
    "treemap",
    "violin",
}
_ALLOWED_FIGURE_UPDATE_METHODS = {
    "update_layout",
    "update_traces",
    "update_xaxes",
    "update_yaxes",
}


def _qsql_hash(value) -> str:
    if value is None:
        return "none"
    return hashlib.sha256(str(value).encode("utf-8", errors="replace")).hexdigest()[:12]


def _qsql_len(value) -> int:
    return len(str(value)) if value is not None else 0


def _qsql_norm(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


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


def _qsql_parse_example(example) -> dict | None:
    if isinstance(example, dict):
        return example
    try:
        parsed_example = json.loads(example)
    except Exception:  # noqa: BLE001
        return None
    if isinstance(parsed_example, dict):
        return parsed_example
    return None


def _qsql_examples_summary(question: str, examples: list) -> tuple[int, str]:
    question_norm = _qsql_norm(question)
    exact_count = 0
    summary = []
    for index, example in enumerate(examples or []):
        parsed_example = _qsql_parse_example(example)
        if parsed_example is None:
            summary.append(f"{index}:type={type(example).__name__}")
            continue

        example_question = parsed_example.get("question")
        example_sql = parsed_example.get("sql")
        is_exact = _qsql_norm(example_question) == question_norm
        exact_count += int(is_exact)
        summary.append(
            f"{index}:q={_qsql_hash(example_question)}:sql={_qsql_hash(example_sql)}:"
            f"q_len={_qsql_len(example_question)}:sql_len={_qsql_len(example_sql)}:"
            f"exact={int(is_exact)}"
        )

    return exact_count, ",".join(summary[:5])


def _qsql_find_exact_sql(question: str, examples: list) -> tuple[str | None, int | None]:
    question_norm = _qsql_norm(question)
    for index, example in enumerate(examples or []):
        parsed_example = _qsql_parse_example(example)
        if parsed_example is None:
            continue
        if _qsql_norm(parsed_example.get("question")) == question_norm:
            return parsed_example.get("sql"), index
    return None, None


def _qsql_default_plotly_figure(df: pd.DataFrame) -> plotly.graph_objs.Figure:
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    categorical_cols = df.select_dtypes(
        include=["object", "category", "string"]
    ).columns.tolist()

    if len(numeric_cols) >= 2:
        return px.scatter(df, x=numeric_cols[0], y=numeric_cols[1])
    if len(numeric_cols) == 1 and len(categorical_cols) >= 1:
        return px.bar(df, x=categorical_cols[0], y=numeric_cols[0])
    if len(categorical_cols) >= 1 and df[categorical_cols[0]].nunique() < 10:
        return px.pie(df, names=categorical_cols[0])
    return px.line(df)


def _qsql_eval_plotly_literal(node: ast.AST, df: pd.DataFrame):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name) and node.id == "df":
        return df
    if isinstance(node, ast.List):
        return [_qsql_eval_plotly_literal(item, df) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_qsql_eval_plotly_literal(item, df) for item in node.elts)
    if isinstance(node, ast.Dict):
        return {
            _qsql_eval_plotly_literal(key, df): _qsql_eval_plotly_literal(value, df)
            for key, value in zip(node.keys, node.values)
            if key is not None
        }
    raise ValueError("不支持的 Plotly 参数表达式")


def _qsql_eval_plotly_px_call(
    node: ast.Call, df: pd.DataFrame
) -> plotly.graph_objs.Figure:
    if not isinstance(node.func, ast.Attribute):
        raise ValueError("Plotly 调用必须是属性调用")
    if not isinstance(node.func.value, ast.Name) or node.func.value.id != "px":
        raise ValueError("只允许 plotly.express 调用")
    if node.func.attr not in _ALLOWED_PLOTLY_EXPRESS_FUNCTIONS:
        raise ValueError(f"不支持的 Plotly 图表类型: {node.func.attr}")

    args = [_qsql_eval_plotly_literal(arg, df) for arg in node.args]
    kwargs = {
        keyword.arg: _qsql_eval_plotly_literal(keyword.value, df)
        for keyword in node.keywords
        if keyword.arg is not None
    }
    return getattr(px, node.func.attr)(*args, **kwargs)


def _qsql_apply_plotly_update(
    fig: plotly.graph_objs.Figure, node: ast.Call
) -> None:
    if not isinstance(node.func, ast.Attribute):
        raise ValueError("Plotly 更新必须是属性调用")
    if not isinstance(node.func.value, ast.Name) or node.func.value.id != "fig":
        raise ValueError("只允许更新 fig 对象")
    if node.func.attr not in _ALLOWED_FIGURE_UPDATE_METHODS:
        raise ValueError(f"不支持的 Plotly 更新方法: {node.func.attr}")

    kwargs = {
        keyword.arg: _qsql_eval_plotly_literal(keyword.value, pd.DataFrame())
        for keyword in node.keywords
        if keyword.arg is not None
    }
    getattr(fig, node.func.attr)(**kwargs)


def _qsql_safe_plotly_figure(
    plotly_code: str, df: pd.DataFrame
) -> plotly.graph_objs.Figure | None:
    module = ast.parse(plotly_code or "")
    fig = None

    for statement in module.body:
        if isinstance(statement, ast.Assign):
            if len(statement.targets) != 1:
                raise ValueError("只允许单目标赋值")
            target = statement.targets[0]
            if not isinstance(target, ast.Name) or target.id != "fig":
                raise ValueError("只允许给 fig 赋值")
            if not isinstance(statement.value, ast.Call):
                raise ValueError("fig 只能来自 plotly.express 调用")
            fig = _qsql_eval_plotly_px_call(statement.value, df)
            continue

        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
            if fig is None:
                raise ValueError("必须先创建 fig")
            _qsql_apply_plotly_update(fig, statement.value)
            continue

        raise ValueError("不支持的 Plotly 语句")

    return fig


class VannaBase(ABC):
    def __init__(self, config=None):
        if config is None:
            config = {}

        self.config = config
        self.run_sql_is_set = False
        self.static_documentation = ""
        self.dialect = self.config.get("dialect", "SQL")
        self.language = self.config.get("language", None)
        self.max_tokens = self.config.get("max_tokens", 14000)

    def log(self, message: str, title: str = "Info"):
        print(f"{title}: {message}")

    def _response_language(self) -> str:
        if self.language is None:
            return ""

        return f"Respond in the {self.language} language."

    def generate_sql(self, question: str, allow_llm_to_see_data=False, **kwargs) -> str:
        """
        Example:
        ```python
        vn.generate_sql("What are the top 10 customers by sales?")
        ```

        Uses the LLM to generate a SQL query that answers a question. It runs the following methods:

        - [`get_similar_question_sql`][qsql.base.base.VannaBase.get_similar_question_sql]

        - [`get_related_ddl`][qsql.base.base.VannaBase.get_related_ddl]

        - [`get_related_documentation`][qsql.base.base.VannaBase.get_related_documentation]

        - [`get_sql_prompt`][qsql.base.base.VannaBase.get_sql_prompt]

        - [`submit_prompt`][qsql.base.base.VannaBase.submit_prompt]


        Args:
            question (str): The question to generate a SQL query for.
            allow_llm_to_see_data (bool): Whether to allow the LLM to see the data (for the purposes of introspecting the data to generate the final SQL).

        Returns:
            str: The SQL query that answers the question.
        """
        if self.config is not None:
            initial_prompt = self.config.get("initial_prompt", None)
        else:
            initial_prompt = None
        # [CUSTOM] QSQL 诊断日志：只记录 hash/数量/长度，定位训练 SQL 是否被召回并进入 prompt。
        qsql_start_time = time.time()
        question_sql_list = self.get_similar_question_sql(question, **kwargs)
        exact_count, qsql_summary = _qsql_examples_summary(question, question_sql_list)
        exact_sql, exact_index = _qsql_find_exact_sql(question, question_sql_list)
        if exact_sql:
            # [CUSTOM] 相同问题命中人工训练 SQL 时直接返回，避免 LLM 对已确认 SQL 再改写导致漂移。
            _qsql_log(
                "info",
                "[QSQL] exact命中训练SQL直出 "
                f"question_hash={_qsql_hash(question)} "
                f"sql_hash={_qsql_hash(exact_sql)} sql_len={_qsql_len(exact_sql)} "
                f"exact_index={exact_index} question_sql_count={len(question_sql_list or [])} "
                f"elapsed_ms={int((time.time() - qsql_start_time) * 1000)} "
                f"qsql_top={qsql_summary}",
            )
            return exact_sql

        ddl_list = self.get_related_ddl(question, **kwargs)
        doc_list = self.get_related_documentation(question, **kwargs)
        _qsql_log(
            "info",
            "[QSQL] base召回完成 "
            f"question_hash={_qsql_hash(question)} "
            f"question_sql_count={len(question_sql_list or [])} "
            f"exact_question_count={exact_count} ddl_count={len(ddl_list or [])} "
            f"doc_count={len(doc_list or [])} "
            f"elapsed_ms={int((time.time() - qsql_start_time) * 1000)} "
            f"qsql_top={qsql_summary}",
        )
        prompt = self.get_sql_prompt(
            initial_prompt=initial_prompt,
            question=question,
            question_sql_list=question_sql_list,
            ddl_list=ddl_list,
            doc_list=doc_list,
            **kwargs,
        )
        message_count, prompt_chars = _qsql_prompt_stats(prompt)
        _qsql_log(
            "info",
            "[QSQL] prompt构建完成 "
            f"question_hash={_qsql_hash(question)} message_count={message_count} "
            f"prompt_chars={prompt_chars} question_sql_count={len(question_sql_list or [])} "
            f"exact_question_count={exact_count}",
        )
        self.log(title="SQL Prompt", message=prompt)
        llm_response = self.submit_prompt(prompt, **kwargs)
        _qsql_log(
            "info",
            "[QSQL] LLM响应完成 "
            f"question_hash={_qsql_hash(question)} "
            f"response_hash={_qsql_hash(llm_response)} "
            f"response_len={len(str(llm_response or ''))} "
            f"has_intermediate_sql={'intermediate_sql' in str(llm_response)}",
        )
        self.log(title="LLM Response", message=llm_response)

        if "intermediate_sql" in llm_response:
            if not allow_llm_to_see_data:
                return "The LLM is not allowed to see the data in your database. Your question requires database introspection to generate the necessary SQL. Please set allow_llm_to_see_data=True to enable this."

            if allow_llm_to_see_data:
                intermediate_sql = self.extract_sql(llm_response)

                try:
                    self.log(title="Running Intermediate SQL", message=intermediate_sql)
                    df = self.run_sql(intermediate_sql)

                    prompt = self.get_sql_prompt(
                        initial_prompt=initial_prompt,
                        question=question,
                        question_sql_list=question_sql_list,
                        ddl_list=ddl_list,
                        doc_list=doc_list
                        + [
                            f"The following is a pandas DataFrame with the results of the intermediate SQL query {intermediate_sql}: \n"
                            + df.to_markdown()
                        ],
                        **kwargs,
                    )
                    self.log(title="Final SQL Prompt", message=prompt)
                    llm_response = self.submit_prompt(prompt, **kwargs)
                    self.log(title="LLM Response", message=llm_response)
                except Exception as e:
                    return f"Error running intermediate SQL: {e}"

        final_sql = self.extract_sql(llm_response)
        _qsql_log(
            "info",
            "[QSQL] base生成SQL完成 "
            f"question_hash={_qsql_hash(question)} sql_hash={_qsql_hash(final_sql)} "
            f"sql_len={len(str(final_sql or ''))}",
        )
        return final_sql

    def extract_sql(self, llm_response: str) -> str:
        """
        Example:
        ```python
        vn.extract_sql("Here's the SQL query in a code block: ```sql\nSELECT * FROM customers\n```")
        ```

        Extracts the SQL query from the LLM response. This is useful in case the LLM response contains other information besides the SQL query.
        Override this function if your LLM responses need custom extraction logic.

        Args:
            llm_response (str): The LLM response.

        Returns:
            str: The extracted SQL query.
        """

        """
        Extracts the SQL query from the LLM response, handling various formats including:
        - WITH clause
        - SELECT statement
        - CREATE TABLE AS SELECT
        - Markdown code blocks
        """

        # Match CREATE TABLE ... AS SELECT
        sqls = re.findall(
            r"\bCREATE\s+TABLE\b.*?\bAS\b.*?;", llm_response, re.DOTALL | re.IGNORECASE
        )
        if sqls:
            sql = sqls[-1]
            self.log(title="Extracted SQL", message=f"{sql}")
            return sql

        # Match WITH clause (CTEs)
        sqls = re.findall(r"\bWITH\b .*?;", llm_response, re.DOTALL | re.IGNORECASE)
        if sqls:
            sql = sqls[-1]
            self.log(title="Extracted SQL", message=f"{sql}")
            return sql

        # Match SELECT ... ;
        sqls = re.findall(r"\bSELECT\b .*?;", llm_response, re.DOTALL | re.IGNORECASE)
        if sqls:
            sql = sqls[-1]
            self.log(title="Extracted SQL", message=f"{sql}")
            return sql

        # Match ```sql ... ``` blocks
        sqls = re.findall(
            r"```sql\s*\n(.*?)```", llm_response, re.DOTALL | re.IGNORECASE
        )
        if sqls:
            sql = sqls[-1].strip()
            self.log(title="Extracted SQL", message=f"{sql}")
            return sql

        # Match any ``` ... ``` code blocks
        sqls = re.findall(r"```(.*?)```", llm_response, re.DOTALL | re.IGNORECASE)
        if sqls:
            sql = sqls[-1].strip()
            self.log(title="Extracted SQL", message=f"{sql}")
            return sql

        return llm_response

    def is_sql_valid(self, sql: str) -> bool:
        """
        Example:
        ```python
        vn.is_sql_valid("SELECT * FROM customers")
        ```
        Checks if the SQL query is valid. This is usually used to check if we should run the SQL query or not.
        By default it checks if the SQL query is a SELECT statement. You can override this method to enable running other types of SQL queries.

        Args:
            sql (str): The SQL query to check.

        Returns:
            bool: True if the SQL query is valid, False otherwise.
        """

        parsed = sqlparse.parse(sql)

        for statement in parsed:
            if statement.get_type() == "SELECT":
                return True

        return False

    def should_generate_chart(self, df: pd.DataFrame) -> bool:
        """
        Example:
        ```python
        vn.should_generate_chart(df)
        ```

        Checks if a chart should be generated for the given DataFrame. By default, it checks if the DataFrame has more than one row and has numerical columns.
        You can override this method to customize the logic for generating charts.

        Args:
            df (pd.DataFrame): The DataFrame to check.

        Returns:
            bool: True if a chart should be generated, False otherwise.
        """

        if len(df) > 1 and df.select_dtypes(include=["number"]).shape[1] > 0:
            return True

        return False

    def generate_rewritten_question(
        self, last_question: str, new_question: str, **kwargs
    ) -> str:
        """
        **Example:**
        ```python
        rewritten_question = vn.generate_rewritten_question("Who are the top 5 customers by sales?", "Show me their email addresses")
        ```

        Generate a rewritten question by combining the last question and the new question if they are related. If the new question is self-contained and not related to the last question, return the new question.

        Args:
            last_question (str): The previous question that was asked.
            new_question (str): The new question to be combined with the last question.
            **kwargs: Additional keyword arguments.

        Returns:
            str: The combined question if related, otherwise the new question.
        """
        if last_question is None:
            return new_question

        prompt = [
            self.system_message(
                "Your goal is to combine a sequence of questions into a singular question if they are related. If the second question does not relate to the first question and is fully self-contained, return the second question. Return just the new combined question with no additional explanations. The question should theoretically be answerable with a single SQL statement."
            ),
            self.user_message(
                "First question: "
                + last_question
                + "\nSecond question: "
                + new_question
            ),
        ]

        return self.submit_prompt(prompt=prompt, **kwargs)

    def generate_followup_questions(
        self, question: str, sql: str, df: pd.DataFrame, n_questions: int = 5, **kwargs
    ) -> list:
        """
        **Example:**
        ```python
        vn.generate_followup_questions("What are the top 10 customers by sales?", sql, df)
        ```

        Generate a list of followup questions that you can ask QSQL.

        Args:
            question (str): The question that was asked.
            sql (str): The LLM-generated SQL query.
            df (pd.DataFrame): The results of the SQL query.
            n_questions (int): Number of follow-up questions to generate.

        Returns:
            list: A list of followup questions that you can ask QSQL.
        """

        message_log = [
            self.system_message(
                f"You are a helpful data assistant. The user asked the question: '{question}'\n\nThe SQL query for this question was: {sql}\n\nThe following is a pandas DataFrame with the results of the query: \n{df.head(25).to_markdown()}\n\n."
            ),
            self.user_message(
                f"Generate a list of {n_questions} followup questions that the user might ask about this data. Respond with a list of questions, one per line. Do not answer with any explanations -- just the questions. Remember that there should be an unambiguous SQL query that can be generated from the question. Prefer questions that are answerable outside of the context of this conversation. Prefer questions that are slight modifications of the SQL query that was generated that allow digging deeper into the data. Each question will be turned into a button that the user can click to generate a new SQL query so don't use 'example' type questions. Each question must have a one-to-one correspondence with an instantiated SQL query."
                + self._response_language()
            ),
        ]

        llm_response = self.submit_prompt(message_log, **kwargs)

        numbers_removed = re.sub(r"^\d+\.\s*", "", llm_response, flags=re.MULTILINE)
        return numbers_removed.split("\n")

    def generate_questions(self, **kwargs) -> List[str]:
        """
        **Example:**
        ```python
        vn.generate_questions()
        ```

        Generate a list of questions that you can ask QSQL.
        """
        question_sql = self.get_similar_question_sql(question="", **kwargs)

        return [q["question"] for q in question_sql]

    def generate_summary(self, question: str, df: pd.DataFrame, **kwargs) -> str:
        """
        **Example:**
        ```python
        vn.generate_summary("What are the top 10 customers by sales?", df)
        ```

        Generate a summary of the results of a SQL query.

        Args:
            question (str): The question that was asked.
            df (pd.DataFrame): The results of the SQL query.

        Returns:
            str: The summary of the results of the SQL query.
        """

        message_log = [
            self.system_message(
                f"You are a helpful data assistant. The user asked the question: '{question}'\n\nThe following is a pandas DataFrame with the results of the query: \n{df.to_markdown()}\n\n"
            ),
            self.user_message(
                "Briefly summarize the data based on the question that was asked. Do not respond with any additional explanation beyond the summary."
                + self._response_language()
            ),
        ]

        summary = self.submit_prompt(message_log, **kwargs)

        return summary

    # ----------------- Use Any Embeddings API ----------------- #
    @abstractmethod
    def generate_embedding(self, data: str, **kwargs) -> List[float]:
        pass

    # ----------------- Use Any Database to Store and Retrieve Context ----------------- #
    @abstractmethod
    def get_similar_question_sql(self, question: str, **kwargs) -> list:
        """
        This method is used to get similar questions and their corresponding SQL statements.

        Args:
            question (str): The question to get similar questions and their corresponding SQL statements for.

        Returns:
            list: A list of similar questions and their corresponding SQL statements.
        """
        pass

    @abstractmethod
    def get_related_ddl(self, question: str, **kwargs) -> list:
        """
        This method is used to get related DDL statements to a question.

        Args:
            question (str): The question to get related DDL statements for.

        Returns:
            list: A list of related DDL statements.
        """
        pass

    @abstractmethod
    def get_related_documentation(self, question: str, **kwargs) -> list:
        """
        This method is used to get related documentation to a question.

        Args:
            question (str): The question to get related documentation for.

        Returns:
            list: A list of related documentation.
        """
        pass

    @abstractmethod
    def add_question_sql(self, question: str, sql: str, **kwargs) -> str:
        """
        This method is used to add a question and its corresponding SQL query to the training data.

        Args:
            question (str): The question to add.
            sql (str): The SQL query to add.

        Returns:
            str: The ID of the training data that was added.
        """
        pass

    @abstractmethod
    def add_ddl(self, ddl: str, **kwargs) -> str:
        """
        This method is used to add a DDL statement to the training data.

        Args:
            ddl (str): The DDL statement to add.

        Returns:
            str: The ID of the training data that was added.
        """
        pass

    @abstractmethod
    def add_documentation(self, documentation: str, **kwargs) -> str:
        """
        This method is used to add documentation to the training data.

        Args:
            documentation (str): The documentation to add.

        Returns:
            str: The ID of the training data that was added.
        """
        pass

    @abstractmethod
    def get_training_data(self, **kwargs) -> pd.DataFrame:
        """
        Example:
        ```python
        vn.get_training_data()
        ```

        This method is used to get all the training data from the retrieval layer.

        Returns:
            pd.DataFrame: The training data.
        """
        pass

    @abstractmethod
    def remove_training_data(self, id: str, **kwargs) -> bool:
        """
        Example:
        ```python
        vn.remove_training_data(id="123-ddl")
        ```

        This method is used to remove training data from the retrieval layer.

        Args:
            id (str): The ID of the training data to remove.

        Returns:
            bool: True if the training data was removed, False otherwise.
        """
        pass

    # ----------------- Use Any Language Model API ----------------- #

    @abstractmethod
    def system_message(self, message: str) -> any:
        pass

    @abstractmethod
    def user_message(self, message: str) -> any:
        pass

    @abstractmethod
    def assistant_message(self, message: str) -> any:
        pass

    def str_to_approx_token_count(self, string: str) -> int:
        return len(string) / 4

    def add_ddl_to_prompt(
        self, initial_prompt: str, ddl_list: list[str], max_tokens: int = 14000
    ) -> str:
        if len(ddl_list) > 0:
            initial_prompt += "\n===Tables \n"

            for ddl in ddl_list:
                if (
                    self.str_to_approx_token_count(initial_prompt)
                    + self.str_to_approx_token_count(ddl)
                    < max_tokens
                ):
                    initial_prompt += f"{ddl}\n\n"

        return initial_prompt

    def add_documentation_to_prompt(
        self,
        initial_prompt: str,
        documentation_list: list[str],
        max_tokens: int = 14000,
    ) -> str:
        if len(documentation_list) > 0:
            initial_prompt += "\n===Additional Context \n\n"

            for documentation in documentation_list:
                if (
                    self.str_to_approx_token_count(initial_prompt)
                    + self.str_to_approx_token_count(documentation)
                    < max_tokens
                ):
                    initial_prompt += f"{documentation}\n\n"

        return initial_prompt

    def add_sql_to_prompt(
        self, initial_prompt: str, sql_list: list[str], max_tokens: int = 14000
    ) -> str:
        if len(sql_list) > 0:
            initial_prompt += "\n===Question-SQL Pairs\n\n"

            for question in sql_list:
                if (
                    self.str_to_approx_token_count(initial_prompt)
                    + self.str_to_approx_token_count(question["sql"])
                    < max_tokens
                ):
                    initial_prompt += f"{question['question']}\n{question['sql']}\n\n"

        return initial_prompt

    def get_sql_prompt(
        self,
        initial_prompt: str,
        question: str,
        question_sql_list: list,
        ddl_list: list,
        doc_list: list,
        **kwargs,
    ):
        """
        Example:
        ```python
        vn.get_sql_prompt(
            question="What are the top 10 customers by sales?",
            question_sql_list=[{"question": "What are the top 10 customers by sales?", "sql": "SELECT * FROM customers ORDER BY sales DESC LIMIT 10"}],
            ddl_list=["CREATE TABLE customers (id INT, name TEXT, sales DECIMAL)"],
            doc_list=["The customers table contains information about customers and their sales."],
        )

        ```

        This method is used to generate a prompt for the LLM to generate SQL.

        Args:
            question (str): The question to generate SQL for.
            question_sql_list (list): A list of questions and their corresponding SQL statements.
            ddl_list (list): A list of DDL statements.
            doc_list (list): A list of documentation.

        Returns:
            any: The prompt for the LLM to generate SQL.
        """

        if initial_prompt is None:
            initial_prompt = (
                f"You are a {self.dialect} expert. "
                + "Please help to generate a SQL query to answer the question. Your response should ONLY be based on the given context and follow the response guidelines and format instructions. "
            )

        initial_prompt = self.add_ddl_to_prompt(
            initial_prompt, ddl_list, max_tokens=self.max_tokens
        )

        if self.static_documentation != "":
            doc_list.append(self.static_documentation)

        initial_prompt = self.add_documentation_to_prompt(
            initial_prompt, doc_list, max_tokens=self.max_tokens
        )

        initial_prompt += (
            "===Response Guidelines \n"
            "1. If the provided context is sufficient, please generate a valid SQL query without any explanations for the question. \n"
            "2. If the provided context is almost sufficient but requires knowledge of a specific string in a particular column, please generate an intermediate SQL query to find the distinct strings in that column. Prepend the query with a comment saying intermediate_sql \n"
            "3. If the provided context is insufficient, please explain why it can't be generated. \n"
            "4. Please use the most relevant table(s). \n"
            "5. If the question has been asked and answered before, please repeat the answer exactly as it was given before. \n"
            f"6. Ensure that the output SQL is {self.dialect}-compliant and executable, and free of syntax errors. \n"
        )

        message_log = [self.system_message(initial_prompt)]

        for example in question_sql_list:
            if example is None:
                print("example is None")
            else:
                if example is not None and "question" in example and "sql" in example:
                    message_log.append(self.user_message(example["question"]))
                    message_log.append(self.assistant_message(example["sql"]))

        message_log.append(self.user_message(question))

        return message_log

    def get_followup_questions_prompt(
        self,
        question: str,
        question_sql_list: list,
        ddl_list: list,
        doc_list: list,
        **kwargs,
    ) -> list:
        initial_prompt = f"The user initially asked the question: '{question}': \n\n"

        initial_prompt = self.add_ddl_to_prompt(
            initial_prompt, ddl_list, max_tokens=self.max_tokens
        )

        initial_prompt = self.add_documentation_to_prompt(
            initial_prompt, doc_list, max_tokens=self.max_tokens
        )

        initial_prompt = self.add_sql_to_prompt(
            initial_prompt, question_sql_list, max_tokens=self.max_tokens
        )

        message_log = [self.system_message(initial_prompt)]
        message_log.append(
            self.user_message(
                "Generate a list of followup questions that the user might ask about this data. Respond with a list of questions, one per line. Do not answer with any explanations -- just the questions."
            )
        )

        return message_log

    @abstractmethod
    def submit_prompt(self, prompt, **kwargs) -> str:
        """
        Example:
        ```python
        vn.submit_prompt(
            [
                vn.system_message("The user will give you SQL and you will try to guess what the business question this query is answering. Return just the question without any additional explanation. Do not reference the table name in the question."),
                vn.user_message("What are the top 10 customers by sales?"),
            ]
        )
        ```

        This method is used to submit a prompt to the LLM.

        Args:
            prompt (any): The prompt to submit to the LLM.

        Returns:
            str: The response from the LLM.
        """
        pass

    def generate_question(self, sql: str, **kwargs) -> str:
        response = self.submit_prompt(
            [
                self.system_message(
                    "The user will give you SQL and you will try to guess what the business question this query is answering. Return just the question without any additional explanation. Do not reference the table name in the question."
                ),
                self.user_message(sql),
            ],
            **kwargs,
        )

        return response

    def _extract_python_code(self, markdown_string: str) -> str:
        # Strip whitespace to avoid indentation errors in LLM-generated code
        markdown_string = markdown_string.strip()

        # Regex pattern to match Python code blocks
        pattern = r"```[\w\s]*python\n([\s\S]*?)```|```([\s\S]*?)```"

        # Find all matches in the markdown string
        matches = re.findall(pattern, markdown_string, re.IGNORECASE)

        # Extract the Python code from the matches
        python_code = []
        for match in matches:
            python = match[0] if match[0] else match[1]
            python_code.append(python.strip())

        if len(python_code) == 0:
            return markdown_string

        return python_code[0]

    def _sanitize_plotly_code(self, raw_plotly_code: str) -> str:
        # Remove the fig.show() statement from the plotly code
        plotly_code = raw_plotly_code.replace("fig.show()", "")

        return plotly_code

    def generate_plotly_code(
        self, question: str = None, sql: str = None, df_metadata: str = None, **kwargs
    ) -> str:
        if question is not None:
            system_msg = f"The following is a pandas DataFrame that contains the results of the query that answers the question the user asked: '{question}'"
        else:
            system_msg = "The following is a pandas DataFrame "

        if sql is not None:
            system_msg += f"\n\nThe DataFrame was produced using this query: {sql}\n\n"

        system_msg += f"The following is information about the resulting pandas DataFrame 'df': \n{df_metadata}"

        message_log = [
            self.system_message(system_msg),
            self.user_message(
                "Can you generate the Python plotly code to chart the results of the dataframe? Assume the data is in a pandas dataframe called 'df'. If there is only one value in the dataframe, use an Indicator. Respond with only Python code. Do not answer with any explanations -- just the code."
            ),
        ]

        plotly_code = self.submit_prompt(message_log, kwargs=kwargs)

        return self._sanitize_plotly_code(self._extract_python_code(plotly_code))

    # ----------------- Connect to Any Database to run the Generated SQL ----------------- #

    def connect_to_snowflake(
        self,
        account: str,
        username: str,
        password: str,
        database: str,
        role: Union[str, None] = None,
        warehouse: Union[str, None] = None,
        **kwargs,
    ):
        # [CUSTOM] 数据库连接实现已外拆到 optional_connectors，base 仅保留稳定方法入口。
        return connect_to_snowflake_impl(
            self,
            account,
            username,
            password,
            database,
            role=role,
            warehouse=warehouse,
            **kwargs,
        )

    def connect_to_sqlite(self, url: str, check_same_thread: bool = False, **kwargs):
        """
        Connect to a SQLite database. This is just a helper function to set [`vn.run_sql`][qsql.base.base.VannaBase.run_sql]

        Args:
            url (str): The URL of the database to connect to.
            check_same_thread (str): Allow the connection may be accessed in multiple threads.
        Returns:
            None
        """

        # URL of the database to download

        # Path to save the downloaded database
        path = os.path.basename(urlparse(url).path)
        # Download the database if it doesn't exist
        if not os.path.exists(url):
            response = requests.get(url)
            response.raise_for_status()  # Check that the request was successful
            with open(path, "wb") as f:
                f.write(response.content)
            url = path

        # Connect to the database
        conn = sqlite3.connect(url, check_same_thread=check_same_thread, **kwargs)

        def run_sql_sqlite(sql: str):
            return pd.read_sql_query(sql, conn)

        self.dialect = "SQLite"
        self.run_sql = run_sql_sqlite
        self.run_sql_is_set = True

    def connect_to_postgres(
        self,
        host: str = None,
        dbname: str = None,
        user: str = None,
        password: str = None,
        port: int = None,
        **kwargs,
    ):
        """
        Connect to postgres using the psycopg2 connector. This is just a helper function to set [`vn.run_sql`][qsql.base.base.VannaBase.run_sql]
        **Example:**
        ```python
        vn.connect_to_postgres(
            host="myhost",
            dbname="mydatabase",
            user="myuser",
            password="mypassword",
            port=5432
        )
        ```
        Args:
            host (str): The postgres host.
            dbname (str): The postgres database name.
            user (str): The postgres user.
            password (str): The postgres password.
            port (int): The postgres Port.
        """
        # [CUSTOM] 可选数据库连接实现已外拆到 optional_connectors，base 仅保留稳定方法入口。
        return connect_to_postgres_impl(
            self, host=host, dbname=dbname, user=user, password=password, port=port, **kwargs
        )

    def connect_to_mysql(
        self,
        host: str = None,
        dbname: str = None,
        user: str = None,
        password: str = None,
        port: int = None,
        **kwargs,
    ):
        # [CUSTOM] 数据库连接实现已外拆到 optional_connectors，base 仅保留稳定方法入口。
        return connect_to_mysql_impl(
            self, host=host, dbname=dbname, user=user, password=password, port=port, **kwargs
        )

    def connect_to_clickhouse(
        self,
        host: str = None,
        dbname: str = None,
        user: str = None,
        password: str = None,
        port: int = None,
        **kwargs,
    ):
        # [CUSTOM] 可选数据库连接实现已外拆到 optional_connectors，base 仅保留稳定方法入口。
        return connect_to_clickhouse_impl(
            self, host=host, dbname=dbname, user=user, password=password, port=port, **kwargs
        )

    def connect_to_oracle(
        self, user: str = None, password: str = None, dsn: str = None, **kwargs
    ):
        """
        Connect to an Oracle db using oracledb package. This is just a helper function to set [`vn.run_sql`][qsql.base.base.VannaBase.run_sql]
        **Example:**
        ```python
        vn.connect_to_oracle(
        user="username",
        password="password",
        dsn="host:port/sid",
        )
        ```
        Args:
            USER (str): Oracle db user name.
            PASSWORD (str): Oracle db user password.
            DSN (str): Oracle db host ip - host:port/sid.
        """
        # [CUSTOM] 可选数据库连接实现已外拆到 optional_connectors，base 仅保留稳定方法入口。
        return connect_to_oracle_impl(
            self, user=user, password=password, dsn=dsn, **kwargs
        )

    def connect_to_bigquery(
        self, cred_file_path: str = None, project_id: str = None, **kwargs
    ):
        """
        Connect to gcs using the bigquery connector. This is just a helper function to set [`vn.run_sql`][qsql.base.base.VannaBase.run_sql]
        **Example:**
        ```python
        vn.connect_to_bigquery(
            project_id="myprojectid",
            cred_file_path="path/to/credentials.json",
        )
        ```
        Args:
            project_id (str): The gcs project id.
            cred_file_path (str): The gcs credential file path
        """
        # [CUSTOM] 可选数据库连接实现已外拆到 optional_connectors，base 仅保留稳定方法入口。
        return connect_to_bigquery_impl(
            self, cred_file_path=cred_file_path, project_id=project_id, **kwargs
        )

    def connect_to_duckdb(self, url: str, init_sql: str = None, **kwargs):
        """
        Connect to a DuckDB database. This is just a helper function to set [`vn.run_sql`][qsql.base.base.VannaBase.run_sql]

        Args:
            url (str): The URL of the database to connect to. Use :memory: to create an in-memory database. Use md: or motherduck: to use the MotherDuck database.
            init_sql (str, optional): SQL to run when connecting to the database. Defaults to None.

        Returns:
            None
        """
        # [CUSTOM] 可选数据库连接实现已外拆到 optional_connectors，base 仅保留稳定方法入口。
        return connect_to_duckdb_impl(self, url, init_sql=init_sql, **kwargs)

    def connect_to_mssql(self, odbc_conn_str: str, **kwargs):
        """
        Connect to a Microsoft SQL Server database. This is just a helper function to set [`vn.run_sql`][qsql.base.base.VannaBase.run_sql]

        Args:
            odbc_conn_str (str): The ODBC connection string.

        Returns:
            None
        """
        # [CUSTOM] 可选数据库连接实现已外拆到 optional_connectors，base 仅保留稳定方法入口。
        return connect_to_mssql_impl(self, odbc_conn_str, **kwargs)

    def connect_to_presto(
        self,
        host: str,
        catalog: str = "hive",
        schema: str = "default",
        user: str = None,
        password: str = None,
        port: int = None,
        combined_pem_path: str = None,
        protocol: str = "https",
        requests_kwargs: dict = None,
        **kwargs,
    ):
        """
        Connect to a Presto database using the specified parameters.

        Args:
            host (str): The host address of the Presto database.
            catalog (str): The catalog to use in the Presto environment.
            schema (str): The schema to use in the Presto environment.
            user (str): The username for authentication.
            password (str): The password for authentication.
            port (int): The port number for the Presto connection.
            combined_pem_path (str): The path to the combined pem file for SSL connection.
            protocol (str): The protocol to use for the connection (default is 'https').
            requests_kwargs (dict): Additional keyword arguments for requests.

        Raises:
            DependencyError: If required dependencies are not installed.
            ImproperlyConfigured: If essential configuration settings are missing.

        Returns:
            None
        """
        # [CUSTOM] 可选数据库连接实现已外拆到 optional_connectors，base 仅保留稳定方法入口。
        return connect_to_presto_impl(
            self,
            host,
            catalog=catalog,
            schema=schema,
            user=user,
            password=password,
            port=port,
            combined_pem_path=combined_pem_path,
            protocol=protocol,
            requests_kwargs=requests_kwargs,
            **kwargs,
        )

    def connect_to_hive(
        self,
        host: str = None,
        dbname: str = "default",
        user: str = None,
        password: str = None,
        port: int = None,
        auth: str = "CUSTOM",
        **kwargs,
    ):
        """
        Connect to a Hive database. This is just a helper function to set [`vn.run_sql`][qsql.base.base.VannaBase.run_sql]
        Connect to a Hive database. This is just a helper function to set [`vn.run_sql`][qsql.base.base.VannaBase.run_sql]

        Args:
            host (str): The host of the Hive database.
            dbname (str): The name of the database to connect to.
            user (str): The username to use for authentication.
            password (str): The password to use for authentication.
            port (int): The port to use for the connection.
            auth (str): The authentication method to use.

        Returns:
            None
        """
        # [CUSTOM] 可选数据库连接实现已外拆到 optional_connectors，base 仅保留稳定方法入口。
        return connect_to_hive_impl(
            self,
            host=host,
            dbname=dbname,
            user=user,
            password=password,
            port=port,
            auth=auth,
            **kwargs,
        )

    def run_sql(self, sql: str, **kwargs) -> pd.DataFrame:
        """
        Example:
        ```python
        vn.run_sql("SELECT * FROM my_table")
        ```

        Run a SQL query on the connected database.

        Args:
            sql (str): The SQL query to run.

        Returns:
            pd.DataFrame: The results of the SQL query.
        """
        raise Exception(
            "You need to connect to a database first by running vn.connect_to_snowflake(), vn.connect_to_postgres(), similar function, or manually set vn.run_sql"
        )

    def ask(
        self,
        question: Union[str, None] = None,
        print_results: bool = True,
        auto_train: bool = True,
        visualize: bool = True,  # if False, will not generate plotly code
        allow_llm_to_see_data: bool = False,
    ) -> Union[
        Tuple[
            Union[str, None],
            Union[pd.DataFrame, None],
            Union[plotly.graph_objs.Figure, None],
        ],
        None,
    ]:
        """
        **Example:**
        ```python
        vn.ask("What are the top 10 customers by sales?")
        ```

        Ask QSQL a question and get the SQL query that answers it.

        Args:
            question (str): The question to ask.
            print_results (bool): Whether to print the results of the SQL query.
            auto_train (bool): Whether to automatically train QSQL on the question and SQL query.
            visualize (bool): Whether to generate plotly code and display the plotly figure.

        Returns:
            Tuple[str, pd.DataFrame, plotly.graph_objs.Figure]: The SQL query, the results of the SQL query, and the plotly figure.
        """
        # [CUSTOM] 运行期问答流程已外拆到 runtime_helpers，base 仅保留稳定方法入口。
        return ask_impl(
            self,
            question=question,
            print_results=print_results,
            auto_train=auto_train,
            visualize=visualize,
            allow_llm_to_see_data=allow_llm_to_see_data,
        )

    def train(
        self,
        question: str = None,
        sql: str = None,
        ddl: str = None,
        documentation: str = None,
        plan: TrainingPlan = None,
    ) -> str:
        """
        **Example:**
        ```python
        vn.train()
        ```

        Train QSQL on a question and its corresponding SQL query.
        If you call it with no arguments, it will check if you connected to a database and it will attempt to train on the metadata of that database.
        If you call it with the sql argument, it's equivalent to [`vn.add_question_sql()`][qsql.base.base.VannaBase.add_question_sql].
        If you call it with the ddl argument, it's equivalent to [`vn.add_ddl()`][qsql.base.base.VannaBase.add_ddl].
        If you call it with the documentation argument, it's equivalent to [`vn.add_documentation()`][qsql.base.base.VannaBase.add_documentation].
        Additionally, you can pass a [`TrainingPlan`][qsql.types.TrainingPlan] object. Get a training plan with [`vn.get_training_plan_generic()`][qsql.base.base.VannaBase.get_training_plan_generic].

        Args:
            question (str): The question to train on.
            sql (str): The SQL query to train on.
            ddl (str):  The DDL statement.
            documentation (str): The documentation to train on.
            plan (TrainingPlan): The training plan to train on.
        """
        # [CUSTOM] 训练入口逻辑已外拆到 runtime_helpers，保留 QSQL 诊断回调透传。
        return train_impl(
            self,
            question=question,
            sql=sql,
            ddl=ddl,
            documentation=documentation,
            plan=plan,
            qsql_log_fn=_qsql_log,
            qsql_hash_fn=_qsql_hash,
            qsql_len_fn=_qsql_len,
        )

    def _get_databases(self) -> List[str]:
        # [CUSTOM] 元数据探测逻辑已外拆到 runtime_helpers，base 仅保留稳定方法入口。
        return get_databases_impl(self)

    def _get_information_schema_tables(self, database: str) -> pd.DataFrame:
        # [CUSTOM] 元数据探测逻辑已外拆到 runtime_helpers，base 仅保留稳定方法入口。
        return get_information_schema_tables_impl(self, database=database)

    def get_training_plan_generic(self, df) -> TrainingPlan:
        """
        This method is used to generate a training plan from an information schema dataframe.

        Basically what it does is breaks up INFORMATION_SCHEMA.COLUMNS into groups of table/column descriptions that can be used to pass to the LLM.

        Args:
            df (pd.DataFrame): The dataframe to generate the training plan from.

        Returns:
            TrainingPlan: The training plan.
        """
        # [CUSTOM] 训练计划生成逻辑已外拆到 runtime_helpers，base 仅保留稳定方法入口。
        return get_training_plan_generic_impl(df)

    def get_training_plan_snowflake(
        self,
        filter_databases: Union[List[str], None] = None,
        filter_schemas: Union[List[str], None] = None,
        include_information_schema: bool = False,
        use_historical_queries: bool = True,
    ) -> TrainingPlan:
        # [CUSTOM] 训练计划生成逻辑已外拆到 runtime_helpers，base 仅保留稳定方法入口。
        return get_training_plan_snowflake_impl(
            self,
            filter_databases=filter_databases,
            filter_schemas=filter_schemas,
            include_information_schema=include_information_schema,
            use_historical_queries=use_historical_queries,
        )

    def get_plotly_figure(
        self, plotly_code: str, df: pd.DataFrame, dark_mode: bool = True
    ) -> plotly.graph_objs.Figure:
        """
        **Example:**
        ```python
        fig = vn.get_plotly_figure(
            plotly_code="fig = px.bar(df, x='name', y='salary')",
            df=df
        )
        fig.show()
        ```
        Get a Plotly figure from a dataframe and Plotly code.

        Args:
            df (pd.DataFrame): The dataframe to use.
            plotly_code (str): The Plotly code to use.

        Returns:
            plotly.graph_objs.Figure: The Plotly figure.
        """
        try:
            # [CUSTOM] 模型生成的 Plotly 代码只做受限 AST 解析，不执行任意 Python。
            fig = _qsql_safe_plotly_figure(plotly_code, df)
        except Exception as exc:
            _qsql_log(
                "warning",
                f"[QSQL] Plotly代码安全解析失败，已降级自动图表 error={exc}",
            )
            fig = _qsql_default_plotly_figure(df)

        if fig is None:
            return None

        if dark_mode:
            fig.update_layout(template="plotly_dark")

        return fig
