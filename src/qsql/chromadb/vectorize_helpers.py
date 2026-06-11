import json
import uuid

import requests


def ensure_data_list(data):
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    raise ValueError("输入必须是 dict或list[dict]")


def build_prompt_template(
    custom_prompt, base_template="请将以下结构化数据转成清晰的自然语言说明：\n{item}"
):
    if not custom_prompt:
        return base_template
    custom_prompt = custom_prompt.rstrip()
    if not custom_prompt.endswith("\n"):
        custom_prompt += "\n"
    return f"{custom_prompt}{base_template}"


def build_llm_request_context(llm_config):
    url = f"{llm_config['base_url'].rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {llm_config['api_key']}",
    }
    return url, headers


def resolve_text_content(
    source_item,
    enable_describe,
    prompt_template,
    url,
    headers,
    model,
    fallback_text,
    logger,
    log_prefix,
    item_index,
):
    if not enable_describe:
        return fallback_text

    prompt = prompt_template.format(item=source_item)
    payload = {
        "model": model,
        "temperature": 0.7,
        "stream": False,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=180)
        resp.raise_for_status()
        result = resp.json()
        return (
            result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        )
    except requests.RequestException as exc:
        logger.error(f"[{log_prefix}] LLM请求失败，第{item_index + 1}条使用原文: {exc}")
        return fallback_text


def stringify_for_embedding(value):
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def normalize_meta_value(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return json.dumps(value, ensure_ascii=False)


def normalize_vector_fields(vector_fields):
    target_fields = []
    if isinstance(vector_fields, list):
        for field in vector_fields:
            if (
                isinstance(field, str)
                and field.strip()
                and field.strip() not in target_fields
            ):
                target_fields.append(field.strip())
    return target_fields


def build_vector_source_from_fields(raw_item, target_fields):
    """将指定字段构建为 JSON 串格式的向量化源数据"""
    vector_source = raw_item
    if not target_fields:
        return vector_source
    # 提取指定字段并构建为 JSON 对象
    field_dict = {}
    for field in target_fields:
        if field in raw_item and raw_item[field] not in (None, ""):
            field_dict[field] = raw_item[field]

    if field_dict:
        # 以 JSON 串形式存储向量化字段
        vector_source = json.dumps(field_dict, ensure_ascii=False)

    return vector_source


def build_custom_data(custom_metas, max_meta_len, logger, log_prefix):
    # 防止 custom_metas 过大导致 metadata 膨胀，超过阈值时直接丢弃
    if not custom_metas:
        return ""

    custom_data = stringify_for_embedding(custom_metas)
    if len(custom_data) > max_meta_len:
        logger.warning(f"[{log_prefix}] custom_metas 超过 {max_meta_len} 字符。")
        return ""
    return custom_data


def build_chunk_metadatas(chunks, base_meta=None):
    # force_custom_data=True 时即使 custom_data 为空也写入该键，兼容旧行为
    metas = []
    base_meta = base_meta or {}
    for chunk in chunks:
        meta = chunk.get("meta", {}) or {}
        if base_meta:
            meta.update(base_meta)
        metas.append(meta)
    return metas


def insert_chunks_to_collection(collection, chunks, metadatas, embed_fn):
    embeddings = [embed_fn.embed_chunk(chunk["text"]) for chunk in chunks]
    ids = [str(uuid.uuid4()) for _ in range(len(chunks))]
    collection.add(
        ids=ids,
        documents=[chunk["text"] for chunk in chunks],
        metadatas=metadatas,
        embeddings=embeddings,
    )
    return ids
