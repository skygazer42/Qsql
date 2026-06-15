from src.qsql.schemas import SemanticQueryDraft, SemanticQueryRequest
from src.qsql.semantic_catalog import load_semantic_catalog
from src.qsql.semantic_service import SemanticQueryService
from src.qsql.sql_builder import build_query_execution_plan


def test_bird_toxicology_catalog_builds_connected_role_sql():
    catalog = load_semantic_catalog("bird_toxicology")

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="connected_bond_count",
            group_by_dimension_keys=["atom_target_element"],
            filters=[
                {
                    "dimension_key": "atom_source_element",
                    "operator": "eq",
                    "value": "c",
                },
                {
                    "dimension_key": "molecule_label",
                    "operator": "eq",
                    "value": "-",
                },
            ],
            time_range=None,
        ),
    )

    assert plan.table == "connected"
    assert "FROM connected AS t0" in plan.sql
    assert "LEFT JOIN atom AS" in plan.sql
    assert "LEFT JOIN bond AS" in plan.sql
    assert "LEFT JOIN molecule AS" in plan.sql
    assert "COUNT(DISTINCT t0.bond_id) AS metric_value" in plan.sql
    assert "t1.element = 'c'" in plan.sql or "t2.element = 'c'" in plan.sql
    assert "t4.label = '-'" in plan.sql or "t3.label = '-'" in plan.sql


def test_bird_toxicology_catalog_builds_atom_multi_metric_sql():
    catalog = load_semantic_catalog("bird_toxicology")

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="atom_count",
            metric_keys=["atom_count", "atom_molecule_count"],
            group_by_dimension_keys=["atom_element"],
            filters=[
                {
                    "dimension_key": "molecule_label",
                    "operator": "eq",
                    "value": "+",
                }
            ],
            time_range=None,
        ),
    )

    assert plan.table == "atom"
    assert "FROM atom AS t0" in plan.sql
    assert "LEFT JOIN molecule AS" in plan.sql
    assert "COUNT(DISTINCT t0.atom_id) AS atom_count" in plan.sql
    assert "COUNT(DISTINCT t0.molecule_id) AS atom_molecule_count" in plan.sql
    assert "t0.element AS atom_element" in plan.sql
    assert "label = '+'" in plan.sql


class _ToxicologyBondParser:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="bond_count",
            group_by_dimension_keys=["molecule_label"],
            filters=[
                {
                    "dimension_key": "bond_type",
                    "operator": "eq",
                    "value": "double bond",
                }
            ],
            time_range=None,
        )


class _ToxicologyRoleParser:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="connected_bond_count",
            group_by_dimension_keys=["atom_target_element"],
            filters=[
                {
                    "dimension_key": "atom_source_element",
                    "operator": "eq",
                    "value": "carbon",
                },
                {
                    "dimension_key": "molecule_label",
                    "operator": "eq",
                    "value": "negative",
                },
            ],
            time_range=None,
        )


class _ToxicologyConnectedMultiMetricParser:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="connected_bond_count",
            metric_keys=["connected_bond_count", "connected_source_atom_count"],
            group_by_dimension_keys=["atom_target_element"],
            filters=[
                {
                    "dimension_key": "atom_source_element",
                    "operator": "eq",
                    "value": "carbon",
                },
                {
                    "dimension_key": "molecule_label",
                    "operator": "eq",
                    "value": "negative",
                },
            ],
            time_range=None,
        )


class _ToxicologyAtomMultiMetricParser:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="atom_count",
            metric_keys=["atom_count", "atom_molecule_count"],
            group_by_dimension_keys=["atom_element"],
            filters=[
                {
                    "dimension_key": "molecule_label",
                    "operator": "eq",
                    "value": "positive",
                }
            ],
            time_range=None,
        )


def test_bird_toxicology_service_normalizes_bond_type():
    service = SemanticQueryService(parser=_ToxicologyBondParser())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_toxicology",
            question="Show bond count by molecule label for double bonds.",
        )
    )

    assert result.status == "ready"
    assert result.semantic_query is not None
    assert result.execution_plan is not None
    assert result.semantic_query.filters[0].value == "="
    assert "bond_type = '='" in result.execution_plan.sql


def test_bird_toxicology_service_normalizes_role_element_and_label():
    service = SemanticQueryService(parser=_ToxicologyRoleParser())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_toxicology",
            question="Show connected bond count by target atom element for carbon source atoms in negative molecules.",
        )
    )

    assert result.status == "ready"
    assert result.semantic_query is not None
    assert result.execution_plan is not None
    normalized_filters = {
        filter_obj.dimension_key: filter_obj.value
        for filter_obj in result.semantic_query.filters
    }
    assert normalized_filters["atom_source_element"] == "c"
    assert normalized_filters["molecule_label"] == "-"


def test_bird_toxicology_service_keeps_connected_multi_metric_ready():
    service = SemanticQueryService(parser=_ToxicologyConnectedMultiMetricParser())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_toxicology",
            question="Show connected bond count and source atom count by target atom element for carbon source atoms in negative molecules.",
        )
    )

    assert result.status == "ready"
    assert result.semantic_query is not None
    assert result.execution_plan is not None
    assert result.semantic_query.metric_keys == [
        "connected_bond_count",
        "connected_source_atom_count",
    ]
    assert "COUNT(DISTINCT" in result.execution_plan.sql


def test_bird_toxicology_service_keeps_atom_multi_metric_ready():
    service = SemanticQueryService(parser=_ToxicologyAtomMultiMetricParser())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_toxicology",
            question="Show atom count and distinct molecule count by element for positive molecules.",
        )
    )

    assert result.status == "ready"
    assert result.semantic_query is not None
    assert result.execution_plan is not None
    assert result.semantic_query.metric_keys == [
        "atom_count",
        "atom_molecule_count",
    ]
    assert "COUNT(DISTINCT" in result.execution_plan.sql
