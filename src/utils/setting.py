#!/usr/bin/env python
# _*_ coding:utf-8 _*_

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

# 数据库存放目录
DB_DIR = os.path.join(BASE_DIR, "resources", "db")
# tiktoken缓存目录
TIKTOKEN_CACHE_DIR = os.path.join(BASE_DIR, "resources", "tiktoken_cache")
# 日志目录
LOG_DIR = os.path.join(BASE_DIR, "resources", "logs")
QSQL_EVENT_LOG_DIR = os.path.join(LOG_DIR, "events")
# 元数据目录
METADATA_DIR = os.path.join(BASE_DIR, "resources", "metadata")
METADATA_DB_PATH = os.path.join(METADATA_DIR, "semantic_metadata.sqlite3")
# 语义草稿目录
SEMANTIC_DRAFT_DIR = os.path.join(BASE_DIR, "resources", "semantic_drafts")
# yaml文件夹路径
YAML_DIR = os.path.join(BASE_DIR, "resources", "yaml")
# jieba文件目录
JIEBA_DIR = os.path.join(BASE_DIR, "resources", "jieba")
# 倒排索引缓存目录
BM25_CACHE_DIR = os.path.join(BASE_DIR, "resources", "bm25_cache")
# 任务目录
TASKS_DIR = os.path.join(BASE_DIR, "resources", "tasks")
# 上传目录
UPLOADS_DIR = os.path.join(BASE_DIR, "resources", "uploads")
# 知识库目录
WORK_DIR = os.path.join(BASE_DIR, "resources", "knowledge_base_data")
QUERY_SYNONYM_PATH = os.path.join(BASE_DIR, "resources", "query_synonyms.json")
QUERY_LIGHT_TOKENS_PATH = os.path.join(BASE_DIR, "resources", "query_light_tokens.json")
