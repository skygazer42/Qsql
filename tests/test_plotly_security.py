from pathlib import Path

import pandas as pd

from src.qsql.base.base import VannaBase


class _PlotlyOnlyVanna(VannaBase):
    def generate_embedding(self, data: str, **kwargs):
        return []

    def get_similar_question_sql(self, question: str, **kwargs):
        return []

    def get_related_ddl(self, question: str, **kwargs):
        return []

    def get_related_documentation(self, question: str, **kwargs):
        return []

    def add_question_sql(self, question: str, sql: str, **kwargs):
        return "question-sql"

    def add_ddl(self, ddl: str, **kwargs):
        return "ddl"

    def add_documentation(self, documentation: str, **kwargs):
        return "documentation"

    def get_training_data(self, **kwargs):
        return pd.DataFrame()

    def remove_training_data(self, id: str, **kwargs):
        return True

    def system_message(self, message: str):
        return {"role": "system", "content": message}

    def user_message(self, message: str):
        return {"role": "user", "content": message}

    def assistant_message(self, message: str):
        return {"role": "assistant", "content": message}

    def submit_prompt(self, prompt, **kwargs):
        return ""


def test_plotly_renderer_does_not_execute_untrusted_python(tmp_path: Path):
    marker = tmp_path / "pwned.txt"
    code = f"open({str(marker)!r}, 'w').write('owned')\nfig = px.line(df)"
    df = pd.DataFrame([{"name": "A", "value": 1}, {"name": "B", "value": 2}])

    fig = _PlotlyOnlyVanna().get_plotly_figure(code, df, dark_mode=False)

    assert marker.exists() is False
    assert fig is not None
