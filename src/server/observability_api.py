from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.qsql.observability import StructuredEventReader
from src.qsql.schemas import ErrorResponse, MetadataSuccessResponse


observability_bp = Blueprint(
    "observability", __name__, url_prefix="/api/v0/observability"
)


__event_reader = StructuredEventReader()


def _success_response(data=None, code: int = 200):
    return jsonify(MetadataSuccessResponse(data=data).model_dump()), code


def _error_response(message: str, code: int = 400):
    return jsonify(ErrorResponse(error=message).model_dump()), code


@observability_bp.route("/routes/recent", methods=["GET"])
def list_recent_route_events():
    route = request.args.get("route", "").strip() or None
    dataset_id = request.args.get("dataset_id", "").strip() or None
    limit = int(request.args.get("limit", "20"))
    if limit < 1:
        return _error_response("limit 必须大于 0")

    events = __event_reader.list_recent_events(
        route=route,
        limit=limit,
        dataset_id=dataset_id,
    )
    return _success_response(
        {
            "route": route,
            "dataset_id": dataset_id,
            "events": events,
        }
    )


@observability_bp.route("/routes/summary", methods=["GET"])
def summarize_route_events():
    route = request.args.get("route", "").strip()
    dataset_id = request.args.get("dataset_id", "").strip() or None
    if route == "":
        return _error_response("缺少 route 参数")

    summary = __event_reader.summarize_route(route=route, dataset_id=dataset_id)
    return _success_response(summary)
