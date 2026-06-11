from src.utils.tasker import tasker
from flask import Blueprint, request, jsonify


# 创建蓝图
task_bp = Blueprint("task", __name__, url_prefix="/api/v0")


@task_bp.route("/task/list", methods=["GET"])
async def list_tasks():
    """List tasks, optionally filtered by status."""
    status = request.args.get("status")
    limit = request.args.get("limit", default=50, type=int)
    try:
        if not (1 <= limit <= 50):
            raise Exception("Parameter 'limit' must be between 1 and 50")
        results = await tasker.list_tasks(status=status, limit=limit)
        return jsonify({"code": 0, "data": results, "msg": "success"})
    except Exception as e:
        return jsonify({"code": -1, "data": None, "msg": str(e)})


@task_bp.route("/task/<task_id>", methods=["GET"])
def get_task(task_id):
    """Retrieve a single task by id."""
    try:
        task = tasker.get_task(task_id)
        if not task:
            raise Exception("Task not found")
        return jsonify({"code": 0, "data": task, "msg": "success"})
    except Exception as e:
        return jsonify({"code": -1, "data": None, "msg": str(e)})


@task_bp.route("/task/<task_id>/cancel", methods=["POST"])
def cancel_task(task_id):
    """Request cancellation of a task."""
    try:
        result = tasker.cancel_task(task_id)
        return jsonify({"code": 0, "data": result, "msg": "success"})
    except Exception as e:
        return jsonify({"code": -1, "data": None, "msg": str(e)})
