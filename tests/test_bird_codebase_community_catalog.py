from src.qsql.schemas import SemanticQueryDraft, SemanticQueryRequest
from src.qsql.semantic_catalog import load_semantic_catalog
from src.qsql.semantic_service import SemanticQueryService
from src.qsql.sql_builder import build_query_execution_plan


def test_bird_codebase_community_catalog_builds_comment_owner_chain_sql():
    catalog = load_semantic_catalog("bird_codebase_community")

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="comment_count",
            group_by_dimension_keys=["comment_post_type_id"],
            filters=[
                {
                    "dimension_key": "owner_user_location",
                    "operator": "eq",
                    "value": "Germany",
                }
            ],
            time_range={
                "dimension_key": "comment_creation_date",
                "start": "2014-01-01",
                "end": "2014-12-31",
            },
        ),
    )

    assert plan.table == "comments"
    assert "FROM comments AS t0" in plan.sql
    assert "LEFT JOIN posts AS t1 ON t0.PostId = t1.Id" in plan.sql
    assert "LEFT JOIN users AS t2 ON t1.OwnerUserId = t2.Id" in plan.sql
    assert "t2.Location = 'Germany'" in plan.sql
    assert "GROUP BY t1.PostTypeId" in plan.sql


def test_bird_codebase_community_catalog_builds_vote_owner_chain_sql():
    catalog = load_semantic_catalog("bird_codebase_community")

    plan = build_query_execution_plan(
        catalog=catalog,
        semantic_query=SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="vote_count",
            group_by_dimension_keys=["vote_post_type_id", "vote_type_id"],
            filters=[
                {
                    "dimension_key": "owner_user_location",
                    "operator": "eq",
                    "value": "Germany",
                }
            ],
            time_range={
                "dimension_key": "vote_creation_date",
                "start": "2011-01-01",
                "end": "2011-12-31",
            },
        ),
    )

    assert plan.table == "votes"
    assert "FROM votes AS t0" in plan.sql
    assert "LEFT JOIN posts AS t1 ON t0.PostId = t1.Id" in plan.sql
    assert "LEFT JOIN users AS t2 ON t1.OwnerUserId = t2.Id" in plan.sql
    assert "t2.Location = 'Germany'" in plan.sql
    assert "GROUP BY t1.PostTypeId, t0.VoteTypeId" in plan.sql


class _ParserCodebaseTeacherBadges:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="badge_count",
            group_by_dimension_keys=["badge_user_location"],
            filters=[
                {
                    "dimension_key": "badge_name",
                    "operator": "eq",
                    "value": "teacher",
                }
            ],
            time_range={
                "dimension_key": "badge_date",
                "start": "2014-01-01",
                "end": "2014-12-31",
            },
        )


class _ParserCodebaseQuestionComments:
    def parse(self, question, catalog, history=None):
        return SemanticQueryDraft(
            analysis_type="group_by",
            metric_key="comment_count",
            group_by_dimension_keys=["comment_post_type_id"],
            filters=[
                {
                    "dimension_key": "commenter_location",
                    "operator": "eq",
                    "value": "Germany",
                },
                {
                    "dimension_key": "comment_post_type_id",
                    "operator": "eq",
                    "value": "questions",
                }
            ],
            time_range={
                "dimension_key": "comment_creation_date",
                "start": "2014-01-01",
                "end": "2014-12-31",
            },
        )


def test_bird_codebase_community_service_normalizes_badge_name():
    service = SemanticQueryService(parser=_ParserCodebaseTeacherBadges())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_codebase_community",
            question="In 2014, show badge count by user location for Teacher badges.",
        )
    )

    assert result.status == "ready"
    assert result.semantic_query is not None
    assert result.execution_plan is not None
    assert result.semantic_query.filters[0].value == "Teacher"
    assert "t0.Name = 'Teacher'" in result.execution_plan.sql


def test_bird_codebase_community_service_normalizes_post_type_without_owner_role_noise():
    service = SemanticQueryService(parser=_ParserCodebaseQuestionComments())

    result = service.prepare_query(
        SemanticQueryRequest(
            dataset_id="bird_codebase_community",
            question="In 2014, show comment count by commented post type for commenters in Germany and question posts.",
        )
    )

    assert result.status == "ready"
    assert result.semantic_query is not None
    assert result.execution_plan is not None
    assert [item.model_dump() for item in result.semantic_query.filters] == [
        {
            "dimension_key": "commenter_location",
            "operator": "eq",
            "value": "Germany",
        },
        {
            "dimension_key": "comment_post_type_id",
            "operator": "eq",
            "value": 1,
        },
    ]
    assert "t2.Location = 'Germany'" in result.execution_plan.sql
    assert "t1.PostTypeId = 1" in result.execution_plan.sql
