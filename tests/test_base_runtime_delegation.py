from src.qsql.base.base import VannaBase
from src.qsql.types import TrainingPlan


class DummyVannaBase(VannaBase):
    def generate_embedding(self, data: str, **kwargs):
        return []

    def get_similar_question_sql(self, question: str, **kwargs):
        return []

    def get_related_ddl(self, question: str, **kwargs):
        return []

    def get_related_documentation(self, question: str, **kwargs):
        return []

    def add_question_sql(self, question: str, sql: str, **kwargs):
        return "question-sql-id"

    def add_ddl(self, ddl: str, **kwargs):
        return "ddl-id"

    def add_documentation(self, documentation: str, **kwargs):
        return "doc-id"

    def get_training_data(self, **kwargs):
        return []

    def remove_training_data(self, id: str, **kwargs):
        return True

    def system_message(self, message: str):
        return message

    def user_message(self, message: str):
        return message

    def assistant_message(self, message: str):
        return message

    def submit_prompt(self, prompt, **kwargs):
        return ""


def test_runtime_and_training_methods_delegate_to_helper_module(monkeypatch):
    from src.qsql.base import base as base_module

    specs = [
        (
            "ask",
            "ask_impl",
            True,
            (),
            {
                "question": "how many rows",
                "print_results": False,
                "auto_train": False,
                "visualize": False,
                "allow_llm_to_see_data": True,
            },
        ),
        (
            "train",
            "train_impl",
            True,
            (),
            {
                "question": "q",
                "sql": "select 1",
                "ddl": None,
                "documentation": None,
                "plan": TrainingPlan([]),
            },
        ),
        (
            "_get_databases",
            "get_databases_impl",
            True,
            (),
            {},
        ),
        (
            "_get_information_schema_tables",
            "get_information_schema_tables_impl",
            True,
            (),
            {"database": "analytics"},
        ),
        (
            "get_training_plan_generic",
            "get_training_plan_generic_impl",
            False,
            ("fake-df",),
            {},
        ),
        (
            "get_training_plan_snowflake",
            "get_training_plan_snowflake_impl",
            True,
            (),
            {
                "filter_databases": ["DB1"],
                "filter_schemas": ["PUBLIC"],
                "include_information_schema": True,
                "use_historical_queries": False,
            },
        ),
    ]

    for method_name, helper_name, passes_self, args, kwargs in specs:
        captured = {}

        def recorder(*helper_args, **helper_kwargs):
            captured["args"] = helper_args
            captured["kwargs"] = helper_kwargs
            return helper_name

        monkeypatch.setattr(base_module, helper_name, recorder)
        vn = DummyVannaBase(config={})

        result = getattr(vn, method_name)(*args, **kwargs)

        assert result == helper_name
        if passes_self:
            assert captured["args"][0] is vn
            assert captured["args"][1:] == args
        else:
            assert captured["args"] == args
        for key, value in kwargs.items():
            assert captured["kwargs"][key] == value
