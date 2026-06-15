import hashlib
import logging
import os
import time
from functools import wraps
from typing import Any, Optional, Tuple

import flask
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request
from pydantic import ValidationError

from src.utils import Log, setting
# [CUSTOM] 引入 Pydantic schema 统一核心请求入参与配置校验。
from src.qsql.schemas import (
    AppConfigModel,
    DataFrameResponse,
    ErrorResponse,
    GenerateSQLRequest,
    GenerateSQLResponse,
    IDRequest,
    SearchRequest,
    SearchResponse,
    SemanticQueryRequest,
    SemanticStageTimings,
    SQLExecutionPayload,
    TrainRequest,
    ValidateRequest,
)

load_dotenv()
os.environ["CHROMA_PATH"] = setting.DB_DIR  # "./resources/db"
os.environ[
    "TIKTOKEN_CACHE_DIR"
] = setting.TIKTOKEN_CACHE_DIR  # "./resources/tiktoken_cache"


def _normalize_required_url_env(name: str) -> None:
    value = os.environ.get(name, "").strip().strip('"').strip("'")
    if value.startswith("hhttp://"):
        # [CUSTOM] 容错常见 URL 协议拼写错误，避免请求阶段才抛 InvalidSchema。
        value = "http://" + value[len("hhttp://") :]
        logging.warning("[QSQL] 环境变量%s协议写成hhttp，已自动修正为http", name)
    elif value.startswith("hhttps://"):
        # [CUSTOM] 容错常见 URL 协议拼写错误，避免请求阶段才抛 InvalidSchema。
        value = "https://" + value[len("hhttps://") :]
        logging.warning("[QSQL] 环境变量%s协议写成hhttps，已自动修正为https", name)

    if not value.startswith(("http://", "https://")):
        raise ValueError(f"{name} 必须以 http:// 或 https:// 开头")

    os.environ[name] = value.rstrip("/")


_normalize_required_url_env("LLM_BASE_URL")

# [CUSTOM] 先加载 .env 与基础路径，再导入会初始化向量/嵌入配置的项目模块，避免环境变量尚未加载时报错。
from cache import MemoryCache  # noqa: E402
from src.server.metadata_api import get_metadata_store, metadata_bp  # noqa: E402
from src.server.observability_api import observability_bp  # noqa: E402
from src.server.structured_embed_api import structured_bp  # noqa: E402
from src.server.task_api import task_bp  # noqa: E402
from src.server.train_embed_api import train_bp  # noqa: E402
from src.server.use_mysql_api import pymysql_bp  # noqa: E402
from src.qsql.local import LocalContext_OpenAICompatible  # noqa: E402
from src.qsql.metadata_scheduler import start_metadata_sync_scheduler  # noqa: E402
from src.qsql.observability import StructuredEventLogger  # noqa: E402
from src.qsql.semantic_service import SemanticQueryService  # noqa: E402

logging.getLogger("chromadb.telemetry").setLevel(logging.CRITICAL)

# [CUSTOM] QSQL 诊断日志：只记录 hash/长度/数量，不输出原始问题或 SQL。
qsql_log = Log()
__event_logger = StructuredEventLogger()


def _qsql_hash(value) -> str:
    if value is None:
        return "none"
    return hashlib.sha256(str(value).encode("utf-8", errors="replace")).hexdigest()[:12]


def _qsql_len(value) -> int:
    return len(str(value)) if value is not None else 0


def _record_route_event(route: str, **payload: Any) -> None:
    # [CUSTOM] 主链路统一记录结构化事件，供后续做 route/tool 统计与异常审计。
    try:
        __event_logger.record({"route": route, **payload})
    except Exception as exc:
        qsql_log.warning(f"[QSQL] structured_event写入失败 route={route} error={exc}")


def _parse_request(
    model: type, payload: Optional[dict[str, Any]]
) -> Tuple[Optional[Any], Optional[str]]:
    # [CUSTOM] 统一参数模型解析，失败时返回可读错误，减少手工字段取值导致的静默误判。
    if payload is None:
        payload = {}
    try:
        return ValidateRequest.parse(model, payload), None
    except ValidationError as exc:
        return None, ValidateRequest.errors_to_string(exc)


def _serialize_model(model_obj: object) -> dict[str, Any]:
    if hasattr(model_obj, "model_dump"):
        return model_obj.model_dump()  # type: ignore[no-any-return]
    return model_obj.dict()  # type: ignore[no-any-return]


def _env_value_or_default(name: str, default: str) -> str:
    value = os.environ.get(name, "")
    return default if str(value).strip() == "" else str(value)


def _model_response(model_obj: object, code: int = 200):
    return jsonify(_serialize_model(model_obj)), code


def _error_response(message: str, code: int = 400):
    return _model_response(ErrorResponse(error=message), code=code)


def _build_sql_execution_payload(
    dataset_id: str, question: str, history: Optional[list[str]] = None
) -> Tuple[SQLExecutionPayload, Any]:
    # [CUSTOM] 老 /api/v0 主链路直接切到语义解析 + 受控 SQL，不再调用 vn.generate_sql() 裸产 SQL。
    request_id = cache.generate_id(question=question)
    semantic_request = SemanticQueryRequest(
        dataset_id=dataset_id,
        question=question,
        history=history or [],
    )
    parse_response = __semantic_query_service.prepare_query(semantic_request)

    if parse_response.status != "ready" or parse_response.execution_plan is None:
        raise ValueError(parse_response.clarification_question or "请补充查询条件")

    try:
        sql_payload = SQLExecutionPayload.from_execution_plan(
            id=request_id,
            question=question,
            execution_plan=parse_response.execution_plan,
        )
        return sql_payload.ensure_select_query(), parse_response
    except ValidationError as exc:
        raise RuntimeError(
            f"SQL 结构校验失败: {ValidateRequest.errors_to_string(exc)}"
        ) from exc
    except ValueError as exc:
        raise RuntimeError(f"SQL 执行校验失败: {exc}") from exc


def _cache_sql_execution_payload(sql_payload: SQLExecutionPayload) -> None:
    cache.set(id=sql_payload.id, field="dataset_id", value=sql_payload.dataset_id)
    cache.set(id=sql_payload.id, field="question", value=sql_payload.question)
    cache.set(id=sql_payload.id, field="sql", value=sql_payload.sql)
    cache.set(
        id=sql_payload.id,
        field="sql_payload",
        value=_serialize_model(sql_payload),
    )


def _load_cached_sql_execution_payload(
    request_id: str, payload: Any
) -> SQLExecutionPayload:
    if not isinstance(payload, dict):
        raise RuntimeError("缓存中的 sql_payload 结构不合法")

    try:
        sql_payload = ValidateRequest.parse(SQLExecutionPayload, payload)
    except ValidationError as exc:
        raise RuntimeError(
            f"缓存 SQL 结构校验失败: {ValidateRequest.errors_to_string(exc)}"
        ) from exc

    if sql_payload.id != request_id:
        raise RuntimeError("缓存 SQL 与请求 id 不一致")

    try:
        return sql_payload.ensure_select_query()
    except ValueError as exc:
        raise RuntimeError(f"缓存 SQL 执行校验失败: {exc}") from exc


def _build_dataframe_response(request_id: str, df) -> DataFrameResponse:
    return DataFrameResponse(id=request_id, df=df.to_json(orient="records"))


def _load_app_config() -> dict[str, Any]:
    # [CUSTOM] 用 Pydantic 校验环境变量映射后的配置，约束数据范围与必填项。
    try:
        raw_config = {
            "llm_base_url": os.environ["LLM_BASE_URL"],
            "model": os.environ["LLM_MODEL"],
            "llm_api_key": os.environ.get("LLM_API_KEY", ""),
            "temperature": _env_value_or_default("LLM_TEMPERATURE", "0.7"),
            "n_results_ddl": _env_value_or_default("N_RESULTS_DDL", "10"),
            "n_results_sql": _env_value_or_default("N_RESULTS_SQL", "10"),
            "n_results_documentation": _env_value_or_default(
                "N_RESULTS_DOCUMENTATION", "10"
            ),
            "question_sql_max_distance": _env_value_or_default(
                "QUESTION_SQL_MAX_DISTANCE", "0.45"
            ),
            "question_sql_distance_filter_enabled": _env_value_or_default(
                "QUESTION_SQL_DISTANCE_FILTER_ENABLED", "false"
            ),
        }
    except KeyError as exc:
        raise RuntimeError(f"缺少必填环境变量: {exc.args[0]}") from exc

    try:
        app_config = ValidateRequest.parse(AppConfigModel, raw_config)
    except ValidationError as exc:
        raise RuntimeError(
            f"环境变量配置不合法: {ValidateRequest.errors_to_string(exc)}"
        ) from exc

    return {
        "base_url": app_config.llm_base_url,
        "model": app_config.model,
        "api_key": app_config.llm_api_key,
        "language": "Chinese",
        "temperature": app_config.temperature,
        "n_results_ddl": app_config.n_results_ddl,
        "n_results_sql": app_config.n_results_sql,
        "n_results_documentation": app_config.n_results_documentation,
        "question_sql_max_distance": app_config.question_sql_max_distance,
        "question_sql_distance_filter_enabled": app_config.question_sql_distance_filter_enabled,
    }

app = Flask(__name__, static_url_path="")
# 注册蓝图
app.register_blueprint(structured_bp)
app.register_blueprint(train_bp)
app.register_blueprint(task_bp)
app.register_blueprint(pymysql_bp)
# [CUSTOM] 暴露 metadata store / schema sync / value mapping 运维入口。
app.register_blueprint(metadata_bp)
# [CUSTOM] 暴露结构化事件的只读查看入口，便于 route/timing 线上排查。
app.register_blueprint(observability_bp)
# [CUSTOM] 已移除文档知识库 / OCR 蓝图，仅保留 SQL 与结构化数据问答相关入口。
# SETUP
cache = MemoryCache()

__config = _load_app_config()
vn = LocalContext_OpenAICompatible(config=__config)
qsql_log.info(
    "[QSQL] 应用启动配置 "
    f"model={__config.get('model')} language={__config.get('language')} "
    f"temperature={__config.get('temperature')} "
    f"n_results_ddl={__config.get('n_results_ddl')} "
    f"n_results_sql={__config.get('n_results_sql')} "
    f"n_results_documentation={__config.get('n_results_documentation')} "
    f"question_sql_distance_filter_enabled="
    f"{__config.get('question_sql_distance_filter_enabled')} "
    f"question_sql_max_distance={__config.get('question_sql_max_distance')}"
)

# [CUSTOM] 旧 remote 入口已移除，当前只保留本地受控 SQL 运行时。
# vn = VannaDefault(model=os.environ['VANNA_MODEL'], api_key=os.environ['VANNA_API_KEY'])

__mysql_config = {
    "host": os.environ.get("MYSQL_HOST", ""),
    "dbname": os.environ.get("MYSQL_DBNAME", ""),
    "user": os.environ.get("MYSQL_USER", ""),
    "password": os.environ.get("MYSQL_PASSWORD", ""),
    "port": int(os.environ.get("MYSQL_PORT", 3389)),
}

if all(__mysql_config.values()):
    vn.connect_to_mysql(**__mysql_config)

__semantic_query_service = SemanticQueryService.from_model_config(
    model_name=__config["model"],
    base_url=__config["base_url"],
    api_key=__config["api_key"],
    temperature=__config["temperature"],
)
# [CUSTOM] 按环境变量可选启动 metadata 定时同步，不影响默认本地开发路径。
__metadata_sync_scheduler = start_metadata_sync_scheduler(store=get_metadata_store())

# region 全局鉴权
api_key = os.getenv("SECRET_ACCESS_KEY", "")
# [CUSTOM] 默认收紧 API 访问；本地无鉴权调试必须显式声明，避免部署时静默裸奔。
allow_unauthenticated = (
    os.getenv("QSQL_ALLOW_UNAUTHENTICATED", "").strip().lower()
    in {"1", "true", "yes", "on"}
)


@app.before_request
def global_api_key_check():
    """全局请求前检查 API Key"""
    if not api_key:
        if allow_unauthenticated:
            return
        return (
            jsonify(
                {
                    "error": (
                        "SECRET_ACCESS_KEY 未配置；如需本地无鉴权调试，请显式设置 "
                        "QSQL_ALLOW_UNAUTHENTICATED=true"
                    )
                }
            ),
            503,
        )

    # 优先检查自定义 Header
    key = request.headers.get("X-API-KEY")
    # 如果没有，再尝试解析 Bearer Token
    if not key:
        auth_header = request.headers.get("Authorization", "")
        # 允许格式 “Bearer <token>”
        if auth_header.lower().startswith("bearer "):
            key = auth_header[7:].strip()
    if key != api_key:
        return jsonify({"error": "Unauthorized"}), 401


# endregion


# NO NEED TO CHANGE ANYTHING BELOW THIS LINE
def requires_cache(fields, optional_fields=None):
    # [CUSTOM] 支持 load_question 区分必需缓存与可选缓存，避免缺少图表/追问时报错。
    optional_fields = optional_fields or []

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            id = request.args.get("id")

            if id is None:
                return jsonify({"type": "error", "error": "No id provided"})

            for field in fields:
                if cache.get(id=id, field=field) is None:
                    return jsonify({"type": "error", "error": f"No {field} found"})

            field_values = {field: cache.get(id=id, field=field) for field in fields}

            for field in optional_fields:
                field_values[field] = cache.get(id=id, field=field)

            # Add the id to the field_values
            field_values["id"] = id

            return f(*args, **field_values, **kwargs)

        return decorated

    return decorator


@app.route("/api/v0/generate_questions", methods=["GET"])
def generate_questions():
    return jsonify(
        {
            "type": "question_list",
            "questions": vn.generate_questions(),
            "header": "Here are some questions you can ask:",
        }
    )


@app.route("/api/v0/generate_sql", methods=["GET"])
def generate_sql():
    request_model, error = _parse_request(
        GenerateSQLRequest, flask.request.args.to_dict()
    )
    if error is not None:
        return _error_response(f"参数错误: {error}")

    question = request_model.question
    dataset_id = request_model.dataset_id

    # [CUSTOM] QSQL 诊断日志：定位同问题训练 SQL 是否进入生成链路。
    start_time = time.time()
    qsql_log.info(
        "[QSQL] generate_sql请求 "
        f"dataset_id={dataset_id} "
        f"question_hash={_qsql_hash(question)} question_len={_qsql_len(question)}"
    )

    try:
        sql_payload, parse_response = _build_sql_execution_payload(
            dataset_id=dataset_id,
            question=question,
        )
        timings = parse_response.timings or SemanticStageTimings(
            catalog_load_ms=0,
            semantic_agent_ms=0,
            sql_build_ms=0,
            total_ms=0,
        )
        semantic_parse_ms = timings.total_ms
        _cache_sql_execution_payload(sql_payload)
    except ValueError as exc:
        elapsed_ms = int((time.time() - start_time) * 1000)
        qsql_log.error(
            "[QSQL] generate_sql澄清 "
            f"dataset_id={dataset_id} "
            f"question_hash={_qsql_hash(question)} reason={exc}"
        )
        _record_route_event(
            "/api/v0/generate_sql",
            status="clarification",
            dataset_id=dataset_id,
            request_id=None,
            question_hash=_qsql_hash(question),
            semantic_parse_ms=elapsed_ms,
            sql_build_ms=0,
            total_ms=elapsed_ms,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        return _error_response(str(exc), code=400)
    except Exception as exc:
        elapsed_ms = int((time.time() - start_time) * 1000)
        qsql_log.error(
            "[QSQL] generate_sql失败 "
            f"dataset_id={dataset_id} "
            f"question_hash={_qsql_hash(question)} error={type(exc).__name__}: {exc}"
        )
        _record_route_event(
            "/api/v0/generate_sql",
            status="error",
            dataset_id=dataset_id,
            request_id=None,
            question_hash=_qsql_hash(question),
            semantic_parse_ms=elapsed_ms,
            sql_build_ms=0,
            total_ms=elapsed_ms,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        return _error_response(f"SQL 结构化失败: {exc}", code=500)

    # [CUSTOM] 老接口已切换到语义控 SQL；这里记录的是受控执行计划而不是模型裸输出。
    elapsed_ms = int((time.time() - start_time) * 1000)
    qsql_log.info(
        "[QSQL] generate_sql完成 "
        f"id={sql_payload.id} dataset_id={dataset_id} "
        f"question_hash={_qsql_hash(question)} "
        f"raw_sql_hash={_qsql_hash(sql_payload.raw_sql)} "
        f"sql_hash={_qsql_hash(sql_payload.sql)} "
        f"statement_type={sql_payload.statement_type} "
        f"is_select={sql_payload.is_select} normalizer={sql_payload.normalizer} "
        f"sql_len={_qsql_len(sql_payload.sql)} "
        f"elapsed_ms={elapsed_ms}"
    )
    _record_route_event(
        "/api/v0/generate_sql",
        status="success",
        dataset_id=dataset_id,
        request_id=sql_payload.id,
        question_hash=_qsql_hash(question),
        catalog_load_ms=timings.catalog_load_ms,
        semantic_agent_ms=timings.semantic_agent_ms,
        semantic_parse_ms=semantic_parse_ms,
        sql_build_ms=timings.sql_build_ms,
        total_ms=elapsed_ms,
        sql_hash=_qsql_hash(sql_payload.sql),
        statement_type=sql_payload.statement_type,
        normalizer=sql_payload.normalizer,
    )

    response = GenerateSQLResponse(id=sql_payload.id, text=sql_payload.sql)
    return _model_response(response)


@app.route("/api/v0/run_sql", methods=["GET"])
@requires_cache(["sql_payload"])
def run_sql(id: str, sql_payload: dict[str, Any]):
    start_time = time.time()
    try:
        cached_sql_payload = _load_cached_sql_execution_payload(
            request_id=id, payload=sql_payload
        )
        run_sql_started_at = time.time()
        df = vn.run_sql(sql=cached_sql_payload.sql)
        run_sql_ms = int((time.time() - run_sql_started_at) * 1000)

        cache.set(id=id, field="df", value=df)
        _record_route_event(
            "/api/v0/run_sql",
            status="success",
            dataset_id=cached_sql_payload.dataset_id,
            request_id=id,
            question_hash=_qsql_hash(cached_sql_payload.question),
            run_sql_ms=run_sql_ms,
            total_ms=int((time.time() - start_time) * 1000),
            sql_hash=_qsql_hash(cached_sql_payload.sql),
            row_count=int(len(df.index)),
        )

        return _model_response(_build_dataframe_response(request_id=id, df=df))

    except Exception as e:
        _record_route_event(
            "/api/v0/run_sql",
            status="error",
            dataset_id=sql_payload.get("dataset_id") if isinstance(sql_payload, dict) else None,
            request_id=id,
            question_hash=None,
            run_sql_ms=0,
            total_ms=int((time.time() - start_time) * 1000),
            error_type=type(e).__name__,
            error_message=str(e),
        )
        return _error_response(str(e))


@app.route("/api/v0/download_csv", methods=["GET"])
@requires_cache(["df"])
def download_csv(id: str, df):
    csv = df.to_csv()

    return Response(
        csv,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={id}.csv"},
    )

# [CUSTOM] 前端打包产物调用无 /json 路径，保留官方 /json 路由并增加兼容别名。
@app.route("/api/v0/generate_plotly_figure", methods=["GET"])
@app.route("/api/v0/generate_plotly_figure/json", methods=["GET"])
@requires_cache(["df", "question", "sql"])
def generate_plotly_figure(id: str, df, question, sql):
    try:
        code = vn.generate_plotly_code(
            question=question,
            sql=sql,
            df_metadata=f"Running df.dtypes gives:\n {df.dtypes}",
        )
        fig = vn.get_plotly_figure(plotly_code=code, df=df, dark_mode=False)
        fig_json = fig.to_json()

        cache.set(id=id, field="fig_json", value=fig_json)

        return jsonify(
            {
                "type": "plotly_figure",
                "id": id,
                "fig": fig_json,
            }
        )
    except Exception as e:
        # Print the stack trace
        import traceback

        traceback.print_exc()

        return jsonify({"type": "error", "error": str(e)})


@app.route("/api/v0/get_training_data", methods=["GET"])
def get_training_data():
    df = vn.get_training_data()

    return jsonify(
        {
            "type": "df",
            "id": "training_data",
            "df": df.to_json(orient="records"),
        }
    )


@app.route("/api/v0/remove_training_data", methods=["POST"])
def remove_training_data():
    # Get id from the JSON body
    request_model, error = _parse_request(IDRequest, flask.request.get_json(silent=True))
    if error is not None:
        return _error_response(f"No id provided, {error}")
    id = request_model.id

    if id is None:
        return jsonify({"type": "error", "error": "No id provided"})

    if vn.remove_training_data(id=id):
        return jsonify({"success": True})
    else:
        return jsonify({"type": "error", "error": "Couldn't remove training data"})


@app.route("/api/v0/train", methods=["POST"])
def add_training_data():
    request_model, error = _parse_request(
        TrainRequest, flask.request.get_json(silent=True)
    )
    if error is not None:
        return _error_response(f"参数校验失败: {error}")

    question = request_model.question
    sql = request_model.sql
    ddl = request_model.ddl
    documentation = request_model.documentation

    if not request_model.has_payload():
        return jsonify({"type": "error", "error": "No training content provided"})

    # [CUSTOM] QSQL 诊断日志：确认训练样本是否带 question/sql 写入。
    start_time = time.time()
    qsql_log.info(
        "[QSQL] train请求 "
        f"has_question={question is not None} question_hash={_qsql_hash(question)} "
        f"question_len={_qsql_len(question)} has_sql={sql is not None} "
        f"sql_hash={_qsql_hash(sql)} sql_len={_qsql_len(sql)} "
        f"has_ddl={ddl is not None} ddl_len={_qsql_len(ddl)} "
        f"has_documentation={documentation is not None} "
        f"documentation_len={_qsql_len(documentation)}"
    )

    try:
        id = vn.train(question=question, sql=sql, ddl=ddl, documentation=documentation)
        qsql_log.info(
            "[QSQL] train完成 "
            f"id={id} question_hash={_qsql_hash(question)} sql_hash={_qsql_hash(sql)} "
            f"elapsed_ms={int((time.time() - start_time) * 1000)}"
        )

        return jsonify({"id": id})
    except Exception as e:
        qsql_log.error(
            "[QSQL] train失败 "
            f"question_hash={_qsql_hash(question)} sql_hash={_qsql_hash(sql)} "
            f"error={type(e).__name__}: {e}"
        )
        print("TRAINING ERROR", e)
        return jsonify({"type": "error", "error": str(e)})


@app.route("/api/v0/generate_followup_questions", methods=["GET"])
@requires_cache(["df", "question", "sql"])
def generate_followup_questions(id: str, df, question, sql):
    followup_questions = vn.generate_followup_questions(
        question=question, sql=sql, df=df
    )

    cache.set(id=id, field="followup_questions", value=followup_questions)

    return jsonify(
        {
            "type": "question_list",
            "id": id,
            "questions": followup_questions,
            "header": "Here are some followup questions you can ask:",
        }
    )


@app.route("/api/v0/load_question", methods=["GET"])
@requires_cache(
    ["question", "sql", "df"],
    optional_fields=["fig_json", "followup_questions"],
)
def load_question(id: str, question, sql, df, fig_json, followup_questions):
    try:
        return jsonify(
            {
                "type": "question_cache",
                "id": id,
                "question": question,
                "sql": sql,
                "df": df.to_json(orient="records"),
                "fig": fig_json,
                "followup_questions": followup_questions,
            }
        )

    except Exception as e:
        return jsonify({"type": "error", "error": str(e)})


@app.route("/api/v0/get_question_history", methods=["GET"])
def get_question_history():
    # [CUSTOM] 只返回已执行出 df 的完整问答，避免点击历史记录时 load_question 报 No df found。
    questions = [
        {"id": item["id"], "question": item["question"]}
        for item in cache.get_all(field_list=["question", "df"])
        if item.get("question") is not None and item.get("df") is not None
    ]

    return jsonify(
        {
            "type": "question_history",
            "questions": questions,
        }
    )


@app.route("/api/v0/delete_question_history", methods=["POST"])
def delete_question_history():
    request_model, error = _parse_request(IDRequest, flask.request.get_json(silent=True))
    if error is not None:
        return _error_response(f"No id provided, {error}")
    id = request_model.id
    cache.delete(id)
    return jsonify({"type": "delete_question_history"})


@app.route("/")
def root():
    return app.send_static_file("index.html")


@app.route("/api/v0/search", methods=["POST"])
def search():
    request_model, error = _parse_request(SearchRequest, request.get_json(silent=True))
    if error is not None:
        return _model_response(SearchResponse.error(f"参数异常: {error}"), code=400)

    dataset_id = request_model.dataset_id
    question = request_model.question
    start_time = time.time()
    try:
        sql_payload, parse_response = _build_sql_execution_payload(
            dataset_id=dataset_id,
            question=question,
            history=request_model.history,
        )
        timings = parse_response.timings or SemanticStageTimings(
            catalog_load_ms=0,
            semantic_agent_ms=0,
            sql_build_ms=0,
            total_ms=0,
        )
        semantic_parse_ms = timings.total_ms
        _cache_sql_execution_payload(sql_payload)
    except ValueError as exc:
        qsql_log.error(
            "[QSQL] search澄清 "
            f"dataset_id={dataset_id} "
            f"question_hash={_qsql_hash(question)} reason={exc}"
        )
        elapsed_ms = int((time.time() - start_time) * 1000)
        _record_route_event(
            "/api/v0/search",
            status="clarification",
            dataset_id=dataset_id,
            request_id=None,
            question_hash=_qsql_hash(question),
            semantic_parse_ms=elapsed_ms,
            sql_build_ms=0,
            run_sql_ms=0,
            total_ms=elapsed_ms,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        return _model_response(SearchResponse.error(str(exc)), code=400)
    except Exception as exc:
        qsql_log.error(
            "[QSQL] search生成失败 "
            f"dataset_id={dataset_id} "
            f"question_hash={_qsql_hash(question)} error={type(exc).__name__}: {exc}"
        )
        elapsed_ms = int((time.time() - start_time) * 1000)
        _record_route_event(
            "/api/v0/search",
            status="error",
            dataset_id=dataset_id,
            request_id=None,
            question_hash=_qsql_hash(question),
            semantic_parse_ms=elapsed_ms,
            sql_build_ms=0,
            run_sql_ms=0,
            total_ms=elapsed_ms,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        return _model_response(SearchResponse.error(f"SQL 结构化失败: {exc}"), code=500)

    # [CUSTOM] search 直接复用语义执行计划，不再经过 LLM 裸 SQL 生成。
    qsql_log.debug(
        "[QSQL] search_sql标准化 "
        f"dataset_id={dataset_id} "
        f"question_hash={_qsql_hash(question)} "
        f"raw_sql_hash={_qsql_hash(sql_payload.raw_sql)} "
        f"sql_hash={_qsql_hash(sql_payload.sql)} "
        f"statement_type={sql_payload.statement_type} "
        f"normalizer={sql_payload.normalizer}"
    )
    # 执行 SQL
    try:
        run_sql_started_at = time.time()
        df = vn.run_sql(sql=sql_payload.sql)
        run_sql_ms = int((time.time() - run_sql_started_at) * 1000)
        cache.set(id=sql_payload.id, field="df", value=df)
        result = _build_dataframe_response(request_id=sql_payload.id, df=df)
        _record_route_event(
            "/api/v0/search",
            status="success",
            dataset_id=dataset_id,
            request_id=sql_payload.id,
            question_hash=_qsql_hash(question),
            catalog_load_ms=timings.catalog_load_ms,
            semantic_agent_ms=timings.semantic_agent_ms,
            semantic_parse_ms=semantic_parse_ms,
            sql_build_ms=timings.sql_build_ms,
            run_sql_ms=run_sql_ms,
            total_ms=int((time.time() - start_time) * 1000),
            sql_hash=_qsql_hash(sql_payload.sql),
            statement_type=sql_payload.statement_type,
            normalizer=sql_payload.normalizer,
            row_count=int(len(df.index)),
        )
        return _model_response(SearchResponse.success(result))
    except Exception as e:
        _record_route_event(
            "/api/v0/search",
            status="error",
            dataset_id=dataset_id,
            request_id=sql_payload.id,
            question_hash=_qsql_hash(question),
            catalog_load_ms=timings.catalog_load_ms,
            semantic_agent_ms=timings.semantic_agent_ms,
            semantic_parse_ms=semantic_parse_ms,
            sql_build_ms=timings.sql_build_ms,
            run_sql_ms=0,
            total_ms=int((time.time() - start_time) * 1000),
            sql_hash=_qsql_hash(sql_payload.sql),
            error_type=type(e).__name__,
            error_message=str(e),
        )
        return _model_response(SearchResponse.error(str(e)))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005, debug=False)
