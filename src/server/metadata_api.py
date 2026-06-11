from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from src.utils import Log
from src.utils import setting
from src.qsql.metadata_store import MetadataStore
from src.qsql.schema_sync import sync_mysql_dataset_schema
from src.qsql.semantic_draft_generator import (
    generate_semantic_catalog_draft,
    write_semantic_catalog_draft,
)
from src.qsql.schemas import (
    ErrorResponse,
    MetadataConnectionUpsertRequest,
    MetadataSchemaSyncRequest,
    MetadataSuccessResponse,
    MetadataValueMappingReplaceRequest,
    SemanticDraftGenerateRequest,
    ValidateRequest,
)


metadata_bp = Blueprint("metadata", __name__, url_prefix="/api/v0/metadata")

__metadata_store = MetadataStore()
__metadata_store.initialize()
__schema_sync_runner: Callable[..., dict[str, int]] = sync_mysql_dataset_schema
__metadata_log = Log()
__semantic_draft_dir = Path(setting.SEMANTIC_DRAFT_DIR)


def set_metadata_store(store: MetadataStore) -> None:
    # [CUSTOM] 测试与后续运维场景可注入独立 metadata store，避免和默认 SQLite 状态耦合。
    global __metadata_store
    store.initialize()
    __metadata_store = store


def get_metadata_store() -> MetadataStore:
    return __metadata_store


def set_semantic_draft_dir(path: str | Path) -> None:
    # [CUSTOM] 测试和离线生成场景可替换语义草稿输出目录，避免污染仓库默认资源目录。
    global __semantic_draft_dir
    __semantic_draft_dir = Path(path)


def set_schema_sync_runner(runner: Callable[..., dict[str, int]]) -> None:
    # [CUSTOM] 允许在测试中替换同步执行器，隔离真实数据库依赖。
    global __schema_sync_runner
    __schema_sync_runner = runner


def _parse_request(model: type, payload: dict[str, Any] | None):
    try:
        return ValidateRequest.parse(model, payload or {}), None
    except ValidationError as exc:
        return None, ValidateRequest.errors_to_string(exc)


def _success_response(data: Any = None, code: int = 200):
    return jsonify(MetadataSuccessResponse(data=data).model_dump()), code


def _error_response(message: str, code: int = 400):
    return jsonify(ErrorResponse(error=message).model_dump()), code


@metadata_bp.route("/connection/upsert", methods=["POST"])
def upsert_connection():
    request_model, error = _parse_request(
        MetadataConnectionUpsertRequest,
        request.get_json(silent=True),
    )
    if error is not None:
        return _error_response(f"参数错误: {error}")

    # [CUSTOM] 元数据连接配置和运行时语义目录解耦，单独落到 metadata store 供 schema sync 使用。
    __metadata_store.upsert_dataset_connection(
        dataset_id=request_model.dataset_id,
        db_type=request_model.db_type,
        host=request_model.host,
        port=request_model.port,
        database_name=request_model.database_name,
        username=request_model.username,
        password=request_model.password,
        enabled=request_model.enabled,
    )
    __metadata_log.info(
        "[Metadata] 连接配置已写入 "
        f"dataset_id={request_model.dataset_id} db_type={request_model.db_type}"
    )
    return _success_response({"dataset_id": request_model.dataset_id})


@metadata_bp.route("/schema/sync", methods=["POST"])
def sync_schema():
    request_model, error = _parse_request(
        MetadataSchemaSyncRequest,
        request.get_json(silent=True),
    )
    if error is not None:
        return _error_response(f"参数错误: {error}")

    try:
        result = __schema_sync_runner(
            store=__metadata_store,
            dataset_id=request_model.dataset_id,
        )
    except Exception as exc:
        __metadata_log.error(
            "[Metadata] schema同步失败 "
            f"dataset_id={request_model.dataset_id} error={type(exc).__name__}: {exc}"
        )
        return _error_response(str(exc), code=500)

    __metadata_log.info(
        "[Metadata] schema同步完成 "
        f"dataset_id={request_model.dataset_id} "
        f"table_count={result.get('table_count', 0)} "
        f"column_count={result.get('column_count', 0)} "
        f"relationship_count={result.get('relationship_count', 0)}"
    )
    return _success_response({"dataset_id": request_model.dataset_id, **result})


@metadata_bp.route("/<dataset_id>/tables", methods=["GET"])
def list_schema_tables(dataset_id: str):
    return _success_response(__metadata_store.list_schema_tables(dataset_id))


@metadata_bp.route("/<dataset_id>/columns", methods=["GET"])
def list_schema_columns(dataset_id: str):
    return _success_response(__metadata_store.list_schema_columns(dataset_id))


@metadata_bp.route("/<dataset_id>/relationships", methods=["GET"])
def list_schema_relationships(dataset_id: str):
    return _success_response(__metadata_store.list_schema_relationships(dataset_id))


@metadata_bp.route("/<dataset_id>/sync-jobs", methods=["GET"])
def list_sync_jobs(dataset_id: str):
    return _success_response(__metadata_store.list_sync_jobs(dataset_id))


@metadata_bp.route("/<dataset_id>/value-mappings", methods=["GET"])
def list_value_mappings(dataset_id: str):
    return _success_response(__metadata_store.list_value_mappings(dataset_id))


@metadata_bp.route("/<dataset_id>/value-mappings/replace", methods=["POST"])
def replace_value_mappings(dataset_id: str):
    request_model, error = _parse_request(
        MetadataValueMappingReplaceRequest,
        request.get_json(silent=True),
    )
    if error is not None:
        return _error_response(f"参数错误: {error}")

    __metadata_store.replace_value_mappings(
        dataset_id=dataset_id,
        mappings=[
            {
                "table_name": item.table_name,
                "column_name": item.column_name,
                "nl_term": item.nl_term,
                "db_value": item.db_value,
                "match_mode": item.match_mode,
                "source": item.source,
                "enabled": 1 if item.enabled else 0,
            }
            for item in request_model.mappings
        ],
    )
    __metadata_log.info(
        "[Metadata] 值映射已替换 "
        f"dataset_id={dataset_id} mapping_count={len(request_model.mappings)}"
    )
    return _success_response({"dataset_id": dataset_id, "mapping_count": len(request_model.mappings)})


@metadata_bp.route("/<dataset_id>/semantic-draft/generate", methods=["POST"])
def generate_semantic_draft(dataset_id: str):
    request_model, error = _parse_request(
        SemanticDraftGenerateRequest,
        request.get_json(silent=True),
    )
    if error is not None:
        return _error_response(f"参数错误: {error}")

    try:
        # [CUSTOM] metadata -> semantic 草稿生成只走运维入口，不直接影响运行时 catalog 加载路径。
        draft = generate_semantic_catalog_draft(store=__metadata_store, dataset_id=dataset_id)
        output_path = None
        if request_model.write_file:
            output_path = str(
                write_semantic_catalog_draft(
                    store=__metadata_store,
                    dataset_id=dataset_id,
                    output_dir=__semantic_draft_dir,
                )
            )
    except Exception as exc:
        __metadata_log.error(
            "[Metadata] 语义草稿生成失败 "
            f"dataset_id={dataset_id} error={type(exc).__name__}: {exc}"
        )
        return _error_response(str(exc), code=500)

    __metadata_log.info(
        "[Metadata] 语义草稿生成完成 "
        f"dataset_id={dataset_id} table_count={len(draft.catalog.tables)} "
        f"metric_count={len(draft.catalog.metrics)} "
        f"dimension_count={len(draft.catalog.dimensions)}"
    )
    return _success_response(
        {
            "catalog": draft.catalog.model_dump(),
            "value_mapping_hints": draft.value_mapping_hints,
            "relationship_hints": draft.relationship_hints,
            "output_path": output_path,
        }
    )
