import concurrent.futures

from flask import Blueprint, request, jsonify
from src.qsql.chromadb import vector_store_service, hybrid_search

executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
tasks = {}  # 可选: 记录活跃任务状态
# 创建蓝图
structured_bp = Blueprint("structured", __name__, url_prefix="/api/v0")

# =============================================================================
# === 数据库管理分组 ===
# =============================================================================


@structured_bp.route("/dataset/create", methods=["POST"])
def create_dataset():
    """创建一个新的知识库"""
    try:
        payload = request.get_json() or {}
        dataset_id = payload.get("dataset_id")
        if not dataset_id:
            raise Exception("缺少 dataset_id")
        # 校验 ID 合法性
        if not dataset_id.isidentifier():
            raise Exception("dataset_id 不合法，应仅由字母、数字、下划线组成")
        # 检查是否重复
        existing = vector_store_service.list_collections()
        if dataset_id in existing:
            raise Exception(f"dataset [{dataset_id}] 已存在")
        vector_store_service.get_chroma_collection(dataset_id, True, True)
        return jsonify({"code": 0, "data": None, "msg": "success"})
    except Exception as e:
        return jsonify({"code": -1, "data": None, "msg": str(e)})


@structured_bp.route("/dataset/list", methods=["GET"])
def dataset_list():
    """列出当前 Chroma 中所有 collection 名称"""
    try:
        names = vector_store_service.list_collections()
        return jsonify({"code": 0, "data": names, "msg": "success"})
    except Exception as e:
        return jsonify({"code": -1, "data": None, "msg": str(e)})


@structured_bp.route("/dataset/delete", methods=["POST"])
def dataset_delete():
    """清空整个 Chroma Collection"""
    try:
        dataset_id = request.json.get("dataset_id")
        vector_store_service.delete_collection(dataset_id)
        return jsonify({"code": 0, "data": None, "msg": "success"})
    except Exception as e:
        return jsonify({"code": -1, "data": None, "msg": str(e)})


# =============================================================================
# === 结构化数据向量化分组 ===
# =============================================================================
@structured_bp.route("/<dataset_id>/preview", methods=["GET"])
def preview_route(dataset_id):
    """快速预览向量库前 N 条记录"""
    try:
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("size", 10))
        return vector_store_service.preview(page, page_size, dataset_id)
    except Exception as e:
        return jsonify({"code": -1, "data": None, "msg": str(e)})


@structured_bp.route("/<dataset_id>/generate", methods=["POST"])
def generate_route(dataset_id):
    """
    接收结构化JSON -> 生成自然语言描述 + 向量化入库
    """
    try:
        payload = request.get_json(silent=True)
        if not payload:
            raise Exception("参数异常")
        data = payload.get("data")
        enable_describe = payload.get("enable_describe", False)
        custom_prompt = payload.get("custom_prompt", "")
        results = vector_store_service.generate_and_vectorize(
            data, dataset_id, enable_describe, custom_prompt
        )
        return jsonify({"code": 0, "data": results, "msg": "success"})
    except Exception as e:
        return jsonify({"code": -1, "data": None, "msg": str(e)})


@structured_bp.route("/<dataset_id>/generate/advanced", methods=["POST"])
def generate_advanced_route(dataset_id):
    """
    接收结构化JSON -> 指定多向量字段 + 元数据增强入库
    """
    try:
        payload = request.get_json(silent=True)
        if not payload:
            raise Exception("参数异常")

        data = payload.get("data")
        enable_describe = payload.get("enable_describe", False)
        custom_prompt = payload.get("custom_prompt", "")
        vector_fields = payload.get("vector_fields")
        metadata_fields = payload.get("metadata_fields")

        results = vector_store_service.generate_and_vectorize_advanced(
            data=data,
            dataset_id=dataset_id,
            enable_describe=enable_describe,
            custom_prompt=custom_prompt,
            vector_fields=vector_fields,
            metadata_fields=metadata_fields,
        )
        return jsonify({"code": 0, "data": results, "msg": "success"})
    except Exception as e:
        return jsonify({"code": -1, "data": None, "msg": str(e)})


@structured_bp.route("/<dataset_id>/search", methods=["POST"])
def search_route(dataset_id):
    """
    语义检索 + rerank
    """
    try:
        payload = request.get_json(silent=True)
        if not payload or "query" not in payload:
            raise Exception("参数异常")
        query = payload["query"]
        if not query:
            raise Exception("检索内容不能为空")
        top_k = int(payload.get("top_k", 10))
        threshold = float(payload.get("threshold", 0.5))

        # 新增：metadata 过滤条件
        metadata_filter = payload.get("metadata_filter", None)
        results = hybrid_search.chroma_search(
            query, dataset_id, top_k, threshold, metadata_filter=metadata_filter
        )
        # 将元组结果转为结构化 dict（只保留 id, text, score, source）
        return jsonify({"code": 0, "data": results, "msg": "success"})
    except Exception as e:
        return jsonify({"code": -1, "data": None, "msg": str(e)})


@structured_bp.route("/<dataset_id>/update", methods=["POST"])
def update_route(dataset_id):
    """更新向量库"""
    try:
        doc_id = request.json.get("doc_id")
        new_text = request.json.get("text")
        if not new_text:
            raise Exception("参数异常")
        vector_store_service.chroma_update(doc_id, new_text, dataset_id)
        return jsonify({"code": 0, "data": None, "msg": f"[{doc_id}] 已更新"})
    except Exception as e:
        return jsonify({"code": -1, "data": None, "msg": str(e)})


@structured_bp.route("/<dataset_id>/delete", methods=["POST"])
def delete_route(dataset_id):
    """删除向量"""
    try:
        doc_id = request.json.get("doc_id")
        if not doc_id:
            raise Exception("参数异常")
        vector_store_service.chroma_delete(doc_id, dataset_id)
        return jsonify({"code": 0, "data": None, "msg": f"[{doc_id}]已删除"})
    except Exception as e:
        return jsonify({"code": -1, "data": None, "msg": str(e)})


@structured_bp.route("/<dataset_id>/document/<doc_id>", methods=["GET"])
def get_route(dataset_id, doc_id):
    """获取指定文档的详细内容"""
    try:
        result = vector_store_service.get_document_detail(
            doc_id=doc_id, dataset_id=dataset_id
        )
        return jsonify({"code": 0, "data": result, "msg": "success"})
    except Exception as e:
        return jsonify({"code": -1, "data": None, "msg": str(e)})


@structured_bp.route("/<dataset_id>/index/build", methods=["POST"])
def build_index_route(dataset_id):
    """异步构建 BM25 索引"""
    try:
        future = executor.submit(vector_store_service.build_bm25_index, dataset_id)
        tasks[dataset_id] = future
        return jsonify(
            {
                "code": 0,
                "data": {"dataset_id": dataset_id, "status": "running"},
                "msg": "索引构建任务已启动",
            }
        )
    except Exception as e:
        return jsonify({"code": -1, "data": None, "msg": str(e)})


@structured_bp.route("/<dataset_id>/index/clear", methods=["POST"])
def clear_index_route(dataset_id):
    try:
        vector_store_service.clear_bm25_index(dataset_id)
        vector_store_service.clear_ngram_index(dataset_id)
        return jsonify({"code": 0, "data": None, "msg": "索引删除成功"})
    except Exception as e:
        return jsonify({"code": -1, "data": None, "msg": str(e)})


@structured_bp.route("/dify/retrieval", methods=["POST"])  # noqa: F821
def retrieval():
    req = request.json
    query = req["query"]
    kb_id = req["knowledge_id"]
    retrieval_setting = req.get("retrieval_setting", {})
    similarity_threshold = float(retrieval_setting.get("score_threshold", 0.3))
    top_k = int(retrieval_setting.get("top_k", 1024))
    try:
        records = []
        results = hybrid_search.chroma_search(
            query, kb_id, top_k, threshold=similarity_threshold
        )
        for doc_id, doc, score, source in results:
            # dify 格式需要 metadata，这里只放 doc_id
            records.append(
                {
                    "content": doc,
                    "score": score,
                    "title": "",
                    "metadata": {"doc_id": doc_id},
                }
            )

        return jsonify({"records": records})
    except Exception as e:
        print("dify_retrieval", e)
        return jsonify({"records": []})


@structured_bp.route("/text/similarity", methods=["POST"])
def chroma_similarity():
    """文本相似度比较"""
    try:
        text_a = request.json.get("textA")
        text_b = request.json.get("textB")
        if not text_a or not text_b:
            raise Exception("参数异常")
        data = vector_store_service.chroma_similarity(text_a, text_b)
        return jsonify({"code": 0, "data": data, "msg": "success"})
    except Exception as e:
        return jsonify({"code": -1, "data": None, "msg": str(e)})
