from src.qsql.schemas import SemanticQueryDraft, SemanticQueryRequest
from src.qsql.semantic_catalog import load_semantic_catalog
from src.qsql.semantic_service import SemanticQueryService
from src.qsql.sql_builder import build_query_execution_plan


def test_bird_thrombosis_catalog_builds_laboratory_patient_sql():
    catalog = load_semantic_catalog("bird_thrombosis_prediction")

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="lab_patient_count",
            group_by_dimension_keys=["patient_sex"],
            filters=[
                {
                    "dimension_key": "patient_admission_flag",
                    "operator": "eq",
                    "value": "+",
                }
            ],
            time_range=None,
        ),
    )

    assert plan.table == "Laboratory"
    assert "FROM Laboratory AS t0" in plan.sql
    assert "LEFT JOIN Patient AS t1 ON t0.ID = t1.ID" in plan.sql
    assert "COUNT(DISTINCT t0.ID) AS metric_value" in plan.sql
    assert "t1.Admission = '+'" in plan.sql
    assert "t1.SEX AS patient_sex" in plan.sql
    assert "GROUP BY t1.SEX" in plan.sql


def test_bird_thrombosis_catalog_builds_examination_patient_sql():
    catalog = load_semantic_catalog("bird_thrombosis_prediction")

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="exam_record_count",
            group_by_dimension_keys=["exam_thrombosis_flag"],
            filters=[
                {
                    "dimension_key": "patient_sex",
                    "operator": "eq",
                    "value": "F",
                }
            ],
            time_range=None,
        ),
    )

    assert plan.table == "Examination"
    assert "FROM Examination AS t0" in plan.sql
    assert "LEFT JOIN Patient AS t1 ON t0.ID = t1.ID" in plan.sql
    assert "COUNT(*) AS metric_value" in plan.sql
    assert "t1.SEX = 'F'" in plan.sql
    assert "t0.Thrombosis AS exam_thrombosis_flag" in plan.sql
    assert "GROUP BY t0.Thrombosis" in plan.sql


class _ThrombosisAdmissionParser:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="lab_patient_count",
            group_by_dimension_keys=["patient_sex"],
            filters=[
                {
                    "dimension_key": "patient_admission_flag",
                    "operator": "eq",
                    "value": "admitted",
                }
            ],
            time_range=None,
        )


class _ThrombosisMultiMetricParser:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="lab_patient_count",
            metric_keys=["lab_patient_count", "total_cholesterol_avg"],
            group_by_dimension_keys=["patient_sex"],
            filters=[
                {
                    "dimension_key": "patient_admission_flag",
                    "operator": "eq",
                    "value": "admitted",
                }
            ],
            time_range=None,
        )


class _ThrombosisFlagParser:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="summary",
            metric_key="exam_record_count",
            group_by_dimension_keys=[],
            filters=[
                {
                    "dimension_key": "patient_sex",
                    "operator": "eq",
                    "value": "female",
                },
                {
                    "dimension_key": "exam_thrombosis_flag",
                    "operator": "eq",
                    "value": "1",
                },
            ],
            time_range=None,
        )


def test_bird_thrombosis_service_normalizes_admission_flag():
    service = SemanticQueryService(parser=_ThrombosisAdmissionParser())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_thrombosis_prediction",
            question="Show laboratory patient count by sex for admitted patients.",
        )
    )

    assert result.status == "ready"
    assert result.semantic_query is not None
    assert result.execution_plan is not None
    assert result.semantic_query.filters[0].value == "+"
    assert "t1.Admission = '+'" in result.execution_plan.sql


def test_bird_thrombosis_service_keeps_multi_metric_ready():
    service = SemanticQueryService(parser=_ThrombosisMultiMetricParser())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_thrombosis_prediction",
            question="Show laboratory patient count and average total cholesterol by sex for admitted patients.",
        )
    )

    assert result.status == "ready"
    assert result.semantic_query is not None
    assert result.execution_plan is not None
    assert result.semantic_query.metric_keys == [
        "lab_patient_count",
        "total_cholesterol_avg",
    ]
    assert "COUNT(DISTINCT" in result.execution_plan.sql
    assert "AVG(" in result.execution_plan.sql


def test_bird_thrombosis_service_normalizes_sex_and_numeric_flag():
    service = SemanticQueryService(parser=_ThrombosisFlagParser())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_thrombosis_prediction",
            question="How many female examinations have thrombosis flag 1?",
        )
    )

    assert result.status == "ready"
    assert result.semantic_query is not None
    assert result.execution_plan is not None
    assert [item.model_dump() for item in result.semantic_query.filters] == [
        {
            "dimension_key": "patient_sex",
            "operator": "eq",
            "value": "F",
        },
        {
            "dimension_key": "exam_thrombosis_flag",
            "operator": "eq",
            "value": 1,
        },
    ]
    assert "t1.SEX = 'F'" in result.execution_plan.sql
    assert "t0.Thrombosis = 1" in result.execution_plan.sql
