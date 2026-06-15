# Pydantic 模型定义：统一 app.py 的输入输出结构与配置验证。
"""QSQL API 与配置的数据模型。"""

from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ErrorResponse(BaseModel):
    """统一错误响应。"""

    type: str = Field(default="error")
    error: str


class ValidateRequest(BaseModel):
    """带可选错误码的模型解析工具基类。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    @staticmethod
    def errors_to_string(error: Exception) -> str:
        if not hasattr(error, "errors"):
            return str(error)

        items = []
        for item in error.errors():  # type: ignore[attr-defined]
            loc = ".".join(str(x) for x in item.get("loc", [])) or "request"
            message = item.get("msg", "invalid")
            items.append(f"{loc} {message}")
        return "; ".join(items) if items else str(error)

    @staticmethod
    def parse(model: type["BaseModel"], payload: dict[str, Any]):
        return model.model_validate(payload)

    @staticmethod
    def as_dict(model_obj) -> dict[str, Any]:
        return model_obj.model_dump()


class AppConfigModel(ValidateRequest):
    """服务配置。"""

    llm_base_url: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    llm_api_key: str = Field(default="")
    temperature: float = Field(default=0.7, ge=0.0, le=10.0)
    n_results_ddl: int = Field(default=10, ge=1, le=100)
    n_results_sql: int = Field(default=10, ge=1, le=200)
    n_results_documentation: int = Field(default=10, ge=1, le=200)
    semantic_candidate_count: int = Field(default=1, ge=1, le=8)
    semantic_candidate_sampling_temperature: Optional[float] = Field(
        default=None, ge=0.0, le=10.0
    )
    semantic_feedback_retry_limit: int = Field(default=0, ge=0, le=5)
    question_sql_max_distance: Optional[float] = Field(
        default=0.45, ge=0.0, le=2.0
    )
    question_sql_distance_filter_enabled: bool = False


class GenerateSQLRequest(ValidateRequest):
    """/api/v0/generate_sql 入参。"""

    dataset_id: str = Field(min_length=1)
    question: str = Field(min_length=1, max_length=4000)


class SearchRequest(GenerateSQLRequest):
    """/api/v0/search 入参。"""

    history: list[str] = Field(default_factory=list)


class IDRequest(ValidateRequest):
    """带 id 的 body 入参。"""

    id: str = Field(min_length=1)


class TrainRequest(ValidateRequest):
    """/api/v0/train 入参。"""

    question: Optional[str] = Field(default=None, min_length=1)
    sql: Optional[str] = Field(default=None, min_length=1)
    ddl: Optional[str] = Field(default=None, min_length=1)
    documentation: Optional[str] = Field(default=None, min_length=1)

    def has_payload(self) -> bool:
        return any(
            bool((self.question or "").strip())
            or bool((self.sql or "").strip())
            or bool((self.ddl or "").strip())
            or bool((self.documentation or "").strip())
        )


class GenerateSQLResponse(ValidateRequest):
    """/api/v0/generate_sql 的响应。"""

    type: str = Field(default="sql")
    id: str
    text: str


class SQLNormalizationResult(ValidateRequest):
    """pydantic-ai 规范化后的 SQL 结构。"""

    question: str = Field(min_length=1)
    raw_sql: str = Field(min_length=1)
    sql: str = Field(min_length=1)
    statement_type: str = Field(min_length=1)
    is_select: bool
    normalizer: str = Field(min_length=1)


class SQLExecutionPayload(ValidateRequest):
    """执行前落缓存的结构化 SQL 载荷。"""

    id: str = Field(min_length=1)
    dataset_id: Optional[str] = None
    question: str = Field(min_length=1)
    raw_sql: str = Field(min_length=1)
    sql: str = Field(min_length=1)
    statement_type: str = Field(min_length=1)
    is_select: bool
    normalizer: str = Field(min_length=1)
    execution_plan: Optional["QueryExecutionPlan"] = None

    @classmethod
    def from_normalized_result(
        cls, *, id: str, normalized: SQLNormalizationResult
    ) -> "SQLExecutionPayload":
        return ValidateRequest.parse(
            cls,
            {
                "id": id,
                "question": normalized.question,
                "raw_sql": normalized.raw_sql,
                "sql": normalized.sql,
                "statement_type": normalized.statement_type,
                "is_select": normalized.is_select,
                "normalizer": normalized.normalizer,
            },
        )

    @classmethod
    def from_execution_plan(
        cls,
        *,
        id: str,
        question: str,
        execution_plan: "QueryExecutionPlan",
        normalizer: str = "pydantic_ai_semantic_builder",
    ) -> "SQLExecutionPayload":
        return ValidateRequest.parse(
            cls,
            {
                "id": id,
                "dataset_id": execution_plan.dataset_id,
                "question": question,
                "raw_sql": execution_plan.sql,
                "sql": execution_plan.sql,
                "statement_type": "SELECT",
                "is_select": True,
                "normalizer": normalizer,
                "execution_plan": ValidateRequest.as_dict(execution_plan),
            },
        )

    def ensure_select_query(self) -> "SQLExecutionPayload":
        # [CUSTOM] 执行前强校验，只允许结构化后的查询 SQL 进入数据库执行链路。
        if self.statement_type not in {"SELECT", "WITH"} or not self.is_select:
            raise ValueError(
                f"只允许执行查询 SQL，当前 statement_type={self.statement_type}"
            )
        return self


class DataFrameResponse(ValidateRequest):
    """DataFrame JSON 响应。"""

    type: str = Field(default="df")
    id: str = Field(min_length=1)
    df: str


class SearchResponse(ValidateRequest):
    """/api/v0/search 响应。"""

    code: int
    data: Optional[DataFrameResponse] = None
    msg: str

    @classmethod
    def success(cls, data: DataFrameResponse) -> "SearchResponse":
        return cls(code=0, data=data, msg="success")

    @classmethod
    def error(cls, message: str) -> "SearchResponse":
        return cls(code=-1, data=None, msg=message)


class SemanticAliasDefinition(ValidateRequest):
    """自然语言别名到语义对象的映射定义。"""

    alias: str = Field(min_length=1)
    target_type: str = Field(min_length=1)
    target_key: str = Field(min_length=1)


class SemanticFilter(ValidateRequest):
    """语义过滤条件。"""

    dimension_key: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    value: Any


class SemanticDimensionDefinition(ValidateRequest):
    """维度配置。"""

    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    table_key: str = Field(min_length=1)
    field: str = Field(min_length=1)
    kind: str = Field(default="categorical", min_length=1)
    operators: list[str] = Field(default_factory=list)


class SemanticTableDefinition(ValidateRequest):
    """语义宽表配置。"""

    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    physical_table: str = Field(min_length=1)
    description: Optional[str] = None
    default_time_dimension_key: Optional[str] = None


# [CUSTOM] 受控多表 join 只允许通过显式实体/关系配置暴露可用路径。
class SemanticEntityDefinition(ValidateRequest):
    """语义实体定义，用于受控 join。"""

    key: str = Field(min_length=1)
    table_key: str = Field(min_length=1)
    field: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)


class SemanticRelationshipDefinition(ValidateRequest):
    """语义关系定义，只允许 catalog 显式声明的 join path。"""

    key: str = Field(min_length=1)
    left_entity_key: str = Field(min_length=1)
    right_entity_key: str = Field(min_length=1)
    join_type: str = Field(default="left", min_length=1)
    allowed: bool = True
    description: Optional[str] = None


class SemanticMetricVersionDefinition(ValidateRequest):
    """指标口径配置。"""

    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    metric_key: str = Field(min_length=1)
    description: Optional[str] = None
    filters: list[SemanticFilter] = Field(default_factory=list)


class SemanticMetricDefinition(ValidateRequest):
    """指标配置。"""

    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    table_key: str = Field(min_length=1)
    field: str = Field(min_length=1)
    aggregation: str = Field(min_length=1)
    supported_dimension_keys: list[str] = Field(default_factory=list)
    default_time_dimension_key: Optional[str] = None
    allowed_version_keys: list[str] = Field(default_factory=list)
    description: Optional[str] = None


class SemanticCatalog(ValidateRequest):
    """按 dataset_id 加载的语义目录。"""

    catalog_version: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    tables: list[SemanticTableDefinition] = Field(default_factory=list)
    entities: list[SemanticEntityDefinition] = Field(default_factory=list)
    relationships: list[SemanticRelationshipDefinition] = Field(default_factory=list)
    metrics: list[SemanticMetricDefinition] = Field(default_factory=list)
    dimensions: list[SemanticDimensionDefinition] = Field(default_factory=list)
    aliases: list[SemanticAliasDefinition] = Field(default_factory=list)
    metric_versions: list[SemanticMetricVersionDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_catalog_references(self) -> "SemanticCatalog":
        # [CUSTOM] 语义目录改成正式结构后，在加载阶段就校验表/指标/维度/口径引用，
        # 避免业务配置错误拖到 SQL 生成期才暴露。
        table_keys = {item.key for item in self.tables}
        entity_map = {item.key: item for item in self.entities}
        metric_map = {item.key: item for item in self.metrics}
        dimension_map = {item.key: item for item in self.dimensions}
        version_map = {item.key: item for item in self.metric_versions}

        if not self.tables:
            raise ValueError("语义目录至少需要定义一张语义表")

        for entity in self.entities:
            if entity.table_key not in table_keys:
                raise ValueError(f"实体引用了未定义的语义表: {entity.key} -> {entity.table_key}")
            if entity.entity_type not in {"primary", "foreign"}:
                raise ValueError(f"不支持的实体类型: {entity.key} -> {entity.entity_type}")

        for relationship in self.relationships:
            left_entity = entity_map.get(relationship.left_entity_key)
            right_entity = entity_map.get(relationship.right_entity_key)
            if left_entity is None:
                raise ValueError(
                    f"关系引用了未定义的左侧实体: {relationship.key} -> {relationship.left_entity_key}"
                )
            if right_entity is None:
                raise ValueError(
                    f"关系引用了未定义的右侧实体: {relationship.key} -> {relationship.right_entity_key}"
                )
            if relationship.left_entity_key == relationship.right_entity_key:
                raise ValueError(f"关系两端不能引用同一实体: {relationship.key}")
            if left_entity.table_key == right_entity.table_key:
                raise ValueError(
                    f"当前不支持同表自连接关系: {relationship.key} -> {left_entity.table_key}"
                )
            if relationship.join_type.lower() not in {"left", "inner"}:
                raise ValueError(
                    f"不支持的关系 join_type: {relationship.key} -> {relationship.join_type}"
                )

        for metric in self.metrics:
            if metric.table_key not in table_keys:
                raise ValueError(f"指标引用了未定义的语义表: {metric.key} -> {metric.table_key}")
            if metric.default_time_dimension_key:
                metric_time_dimension = dimension_map.get(metric.default_time_dimension_key)
                if metric_time_dimension is None:
                    raise ValueError(
                        f"指标默认时间维度未定义: {metric.key} -> {metric.default_time_dimension_key}"
                    )
                if metric_time_dimension.kind != "time":
                    raise ValueError(
                        f"指标默认时间维度必须是 time 类型: {metric.key} -> {metric.default_time_dimension_key}"
                    )
            for dimension_key in metric.supported_dimension_keys:
                dimension = dimension_map.get(dimension_key)
                if dimension is None:
                    raise ValueError(f"指标引用了未定义的维度: {metric.key} -> {dimension_key}")
            for version_key in metric.allowed_version_keys:
                version = version_map.get(version_key)
                if version is None:
                    raise ValueError(f"指标引用了未定义的口径: {metric.key} -> {version_key}")
                if version.metric_key != metric.key:
                    raise ValueError(
                        f"指标允许的口径不属于当前指标: {metric.key} -> {version_key}"
                    )

        for dimension in self.dimensions:
            if dimension.table_key not in table_keys:
                raise ValueError(
                    f"维度引用了未定义的语义表: {dimension.key} -> {dimension.table_key}"
                )

        for table in self.tables:
            if table.default_time_dimension_key:
                time_dimension = dimension_map.get(table.default_time_dimension_key)
                if time_dimension is None:
                    raise ValueError(
                        f"语义表默认时间维度未定义: {table.key} -> {table.default_time_dimension_key}"
                    )
                if time_dimension.table_key != table.key:
                    raise ValueError(
                        f"语义表默认时间维度不属于当前表: {table.key} -> {table.default_time_dimension_key}"
                    )
                if time_dimension.kind != "time":
                    raise ValueError(
                        f"语义表默认时间维度必须是 time 类型: {table.key} -> {table.default_time_dimension_key}"
                    )

        for version in self.metric_versions:
            metric = metric_map.get(version.metric_key)
            if metric is None:
                raise ValueError(
                    f"指标口径引用了未定义的指标: {version.key} -> {version.metric_key}"
                )
            for filter_obj in version.filters:
                dimension = dimension_map.get(filter_obj.dimension_key)
                if dimension is None:
                    raise ValueError(
                        f"指标口径引用了未定义的维度: {version.key} -> {filter_obj.dimension_key}"
                    )

        for alias in self.aliases:
            if alias.target_type == "metric" and alias.target_key not in metric_map:
                raise ValueError(f"别名引用了未定义的指标: {alias.alias} -> {alias.target_key}")
            if alias.target_type == "dimension" and alias.target_key not in dimension_map:
                raise ValueError(f"别名引用了未定义的维度: {alias.alias} -> {alias.target_key}")
            if alias.target_type == "metric_version" and alias.target_key not in version_map:
                raise ValueError(f"别名引用了未定义的口径: {alias.alias} -> {alias.target_key}")
            if alias.target_type not in {"metric", "dimension", "metric_version"}:
                raise ValueError(f"不支持的别名目标类型: {alias.target_type}")

        return self


class SemanticTimeRange(ValidateRequest):
    """查询时间范围。"""

    dimension_key: str = Field(min_length=1)
    start: str = Field(min_length=1)
    end: str = Field(min_length=1)


class SemanticQueryDraft(ValidateRequest):
    """由 pydantic-ai 产出的结构化查询语义。"""

    analysis_type: str = Field(min_length=1)
    metric_key: str = Field(min_length=1)
    metric_keys: list[str] = Field(default_factory=list)
    group_by_dimension_keys: list[str] = Field(default_factory=list)
    filters: list[SemanticFilter] = Field(default_factory=list)
    time_range: Optional[SemanticTimeRange] = None
    metric_version_key: Optional[str] = None
    needs_clarification: bool = False
    clarification_question: Optional[str] = None

    @model_validator(mode="after")
    def _sync_metric_keys(self) -> "SemanticQueryDraft":
        # [CUSTOM] 兼容旧单指标字段；多指标查询用 metric_keys 表达同粒度指标集合。
        if not self.metric_keys:
            self.metric_keys = [self.metric_key]
        elif self.metric_key not in self.metric_keys:
            self.metric_keys = [self.metric_key, *self.metric_keys]
        return self


class QueryParameter(ValidateRequest):
    """SQL 计划中的审计参数。"""

    name: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    value: Any


class SemanticExample(ValidateRequest):
    """可注入解析 prompt 的成功语义示例。"""

    dataset_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    semantic_query: SemanticQueryDraft
    note: Optional[str] = None


class SemanticExampleMatch(ValidateRequest):
    """语义示例检索命中结果。"""

    example: SemanticExample
    score: float = Field(ge=0.0)


class QueryExecutionPlan(ValidateRequest):
    """后端受控生成的 SQL 执行计划。"""

    dataset_id: str = Field(min_length=1)
    table: str = Field(min_length=1)
    sql: str = Field(min_length=1)
    parameters: list[QueryParameter] = Field(default_factory=list)
    analysis_type: str = Field(min_length=1)
    metric_key: str = Field(min_length=1)
    metric_label: str = Field(min_length=1)
    metric_keys: list[str] = Field(default_factory=list)
    metric_labels: list[str] = Field(default_factory=list)
    group_by_dimension_keys: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sync_metric_lists(self) -> "QueryExecutionPlan":
        # [CUSTOM] 保持单指标响应兼容，同时给多指标结果暴露完整指标列表。
        if not self.metric_keys:
            self.metric_keys = [self.metric_key]
        if not self.metric_labels:
            self.metric_labels = [self.metric_label]
        return self


class SemanticQueryCandidate(ValidateRequest):
    """语义候选及其投票信息。"""

    index: int = Field(ge=0)
    semantic_query: SemanticQueryDraft
    signature: str = Field(min_length=1)
    vote_count: int = Field(default=1, ge=1)


class SemanticCandidateSelection(ValidateRequest):
    """多候选投票选择结果。"""

    candidates: list[SemanticQueryCandidate] = Field(default_factory=list)
    selected_index: int = Field(default=0, ge=0)


class SemanticValueCandidate(ValidateRequest):
    """从值索引或元数据映射召回的过滤值候选。"""

    dataset_id: str = Field(min_length=1)
    dimension_key: str = Field(min_length=1)
    nl_term: str = Field(min_length=1)
    db_value: Any
    operator: str = Field(default="eq", min_length=1)
    score: float = Field(default=1.0, ge=0.0)
    source: Optional[str] = None


class SemanticClarificationOption(ValidateRequest):
    """结构化澄清候选项。"""

    target_type: str = Field(min_length=1)
    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    value: Any = None


class SemanticQueryRequest(ValidateRequest):
    """语义查询请求。"""

    dataset_id: str = Field(min_length=1)
    question: str = Field(min_length=1, max_length=4000)
    history: list[str] = Field(default_factory=list)


class SemanticCatalogValidationRequest(ValidateRequest):
    """语义目录校验请求。"""

    dataset_id: str = Field(min_length=1)


class SemanticCatalogSummary(ValidateRequest):
    """语义目录摘要。"""

    catalog_version: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    table_count: int = Field(ge=0)
    metric_count: int = Field(ge=0)
    dimension_count: int = Field(ge=0)
    alias_count: int = Field(ge=0)
    metric_version_count: int = Field(ge=0)


class SemanticCatalogListResponse(ValidateRequest):
    """语义目录列表响应。"""

    type: str = Field(default="semantic_catalog_list")
    catalogs: list[SemanticCatalogSummary] = Field(default_factory=list)


class SemanticCatalogValidationResponse(ValidateRequest):
    """语义目录校验响应。"""

    type: str = Field(default="semantic_catalog_validation")
    dataset_id: str = Field(min_length=1)
    valid: bool
    summary: Optional[SemanticCatalogSummary] = None
    error: Optional[str] = None


class SemanticStageTimings(ValidateRequest):
    """语义链路阶段耗时。"""

    catalog_load_ms: int = Field(ge=0)
    semantic_agent_ms: int = Field(ge=0)
    sql_build_ms: int = Field(ge=0)
    total_ms: int = Field(ge=0)


class SemanticParseResponse(ValidateRequest):
    """语义解析响应。"""

    type: str = Field(default="semantic_parse")
    dataset_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    status: str = Field(min_length=1)
    clarification_question: Optional[str] = None
    clarification_options: list[SemanticClarificationOption] = Field(
        default_factory=list
    )
    semantic_query: Optional[SemanticQueryDraft] = None
    execution_plan: Optional[QueryExecutionPlan] = None
    candidate_selection: Optional[SemanticCandidateSelection] = None
    timings: Optional[SemanticStageTimings] = None


class SemanticRunResponse(ValidateRequest):
    """语义查询执行响应。"""

    type: str = Field(default="semantic_run")
    dataset_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    status: str = Field(min_length=1)
    clarification_question: Optional[str] = None
    clarification_options: list[SemanticClarificationOption] = Field(
        default_factory=list
    )
    semantic_query: Optional[SemanticQueryDraft] = None
    execution_plan: Optional[QueryExecutionPlan] = None
    candidate_selection: Optional[SemanticCandidateSelection] = None
    df: Optional[str] = None
    timings: Optional[SemanticStageTimings] = None


# [CUSTOM] 元数据落库/同步/值映射管理统一通过 pydantic 请求模型收敛输入结构。
class MetadataConnectionUpsertRequest(ValidateRequest):
    """元数据连接配置写入请求。"""

    dataset_id: str = Field(min_length=1)
    db_type: str = Field(min_length=1)
    host: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)
    database_name: str = Field(min_length=1)
    username: str = Field(min_length=1)
    password: str = Field(default="")
    enabled: bool = True


class MetadataSchemaSyncRequest(ValidateRequest):
    """元数据 schema 同步请求。"""

    dataset_id: str = Field(min_length=1)


class MetadataValueMappingItem(ValidateRequest):
    """自然语言值映射项。"""

    table_name: str = Field(min_length=1)
    column_name: str = Field(min_length=1)
    nl_term: str = Field(min_length=1)
    db_value: str = Field(min_length=1)
    match_mode: str = Field(default="eq", min_length=1)
    source: Optional[str] = None
    enabled: bool = True


class MetadataValueMappingReplaceRequest(ValidateRequest):
    """批量替换值映射请求。"""

    mappings: list[MetadataValueMappingItem] = Field(default_factory=list)


class SemanticDraftGenerateRequest(ValidateRequest):
    """语义草稿生成请求。"""

    write_file: bool = False


# [CUSTOM] 语义草稿和正式运行时目录分离，草稿响应允许附带值映射/关系提示信息。
class SemanticDraftArtifact(ValidateRequest):
    """基于元数据生成的语义草稿。"""

    catalog: SemanticCatalog
    value_mapping_hints: list[dict[str, Any]] = Field(default_factory=list)
    relationship_hints: list[dict[str, Any]] = Field(default_factory=list)


class MetadataSuccessResponse(ValidateRequest):
    """元数据 API 成功响应。"""

    code: int = 0
    data: Any = None
    msg: str = "success"


# [CUSTOM] 统一按 pydantic v2 解析前向引用，确保响应模型可直接实例化。
SQLExecutionPayload.model_rebuild()
SearchResponse.model_rebuild()
SemanticCatalogListResponse.model_rebuild()
SemanticCatalogValidationResponse.model_rebuild()
SemanticParseResponse.model_rebuild()
SemanticRunResponse.model_rebuild()
MetadataValueMappingReplaceRequest.model_rebuild()
