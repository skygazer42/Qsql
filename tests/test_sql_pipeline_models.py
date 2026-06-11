import importlib.util
from pathlib import Path

import pytest

_SCHEMAS_PATH = Path(__file__).resolve().parents[1] / "src" / "qsql" / "schemas.py"
_SCHEMAS_SPEC = importlib.util.spec_from_file_location("kd_qsql_schemas", _SCHEMAS_PATH)
assert _SCHEMAS_SPEC is not None
assert _SCHEMAS_SPEC.loader is not None
_SCHEMAS_MODULE = importlib.util.module_from_spec(_SCHEMAS_SPEC)
_SCHEMAS_SPEC.loader.exec_module(_SCHEMAS_MODULE)

DataFrameResponse = _SCHEMAS_MODULE.DataFrameResponse
SQLExecutionPayload = _SCHEMAS_MODULE.SQLExecutionPayload
SQLNormalizationResult = _SCHEMAS_MODULE.SQLNormalizationResult
SearchResponse = _SCHEMAS_MODULE.SearchResponse


def _build_normalized_result(
    *, statement_type: str = "SELECT", is_select: bool = True
) -> SQLNormalizationResult:
    return SQLNormalizationResult(
        question="查询最近订单",
        raw_sql="SELECT * FROM orders LIMIT 10",
        sql="SELECT * FROM orders LIMIT 10",
        statement_type=statement_type,
        is_select=is_select,
        normalizer="pydantic_ai",
    )


def test_sql_execution_payload_accepts_select_query():
    normalized = _build_normalized_result()

    payload = SQLExecutionPayload.from_normalized_result(
        id="req-1", normalized=normalized
    ).ensure_select_query()

    assert payload.id == "req-1"
    assert payload.sql == "SELECT * FROM orders LIMIT 10"
    assert payload.statement_type == "SELECT"


def test_sql_execution_payload_rejects_non_select_query():
    normalized = _build_normalized_result(statement_type="DELETE", is_select=False)
    payload = SQLExecutionPayload.from_normalized_result(
        id="req-2", normalized=normalized
    )

    with pytest.raises(ValueError, match="只允许执行查询 SQL"):
        payload.ensure_select_query()


def test_search_response_wraps_dataframe_payload():
    data = DataFrameResponse(id="req-3", df="[]")
    response = SearchResponse.success(data)

    assert response.code == 0
    assert response.msg == "success"
    assert response.data is not None
    assert response.data.type == "df"
