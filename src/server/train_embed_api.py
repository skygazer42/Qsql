import concurrent.futures

from flask import Blueprint, request, jsonify
from src.qsql.chromadb import vector_store_service as vector_service


executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
tasks = {}  # 可选: 记录活跃任务状态
# 创建蓝图
train_bp = Blueprint("train", __name__, url_prefix="/api/v0/train")


@train_bp.route("/generate", methods=["POST"])
def generate_route():
    try:
        payload = request.get_json(silent=True)
        if not payload:
            raise Exception("参数异常")
        results = vector_service.save_train_data(payload)
        return jsonify({"code": 0, "data": results, "msg": "success"})
    except Exception as e:
        return jsonify({"code": -1, "data": None, "msg": str(e)})


@train_bp.route("/preview", methods=["GET"])
def preview_route():
    """快速预览向量库前 N 条记录"""
    try:
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("size", 10))
        return vector_service.preview_train_data(page, page_size)
    except Exception as e:
        return jsonify({"code": -1, "data": None, "msg": str(e)})


@train_bp.route("/delete", methods=["POST"])
def delete_route():
    try:
        doc_id = request.json.get("doc_id")
        if not doc_id:
            raise Exception("参数异常")
        vector_service.remove_training_data(doc_id)
        return jsonify({"code": 0, "data": None, "msg": f"[{doc_id}]已删除"})
    except Exception as e:
        return jsonify({"code": -1, "data": None, "msg": str(e)})
