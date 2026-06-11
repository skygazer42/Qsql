# 2026-06-11 Metadata API 与值映射入口

## 改了什么

- 新增元数据运维蓝图 `src/server/metadata_api.py`
- 注册到 `app.py`
- 增加元数据相关 `pydantic` 模型：
  - `MetadataConnectionUpsertRequest`
  - `MetadataSchemaSyncRequest`
  - `MetadataValueMappingItem`
  - `MetadataValueMappingReplaceRequest`
  - `MetadataSuccessResponse`
- 新增 API：
  - `POST /api/v0/metadata/connection/upsert`
  - `POST /api/v0/metadata/schema/sync`
  - `GET /api/v0/metadata/<dataset_id>/tables`
  - `GET /api/v0/metadata/<dataset_id>/columns`
  - `GET /api/v0/metadata/<dataset_id>/relationships`
  - `GET /api/v0/metadata/<dataset_id>/sync-jobs`
  - `GET /api/v0/metadata/<dataset_id>/value-mappings`
  - `POST /api/v0/metadata/<dataset_id>/value-mappings/replace`
- 新增测试 `tests/test_metadata_api.py`

## 为什么改

- 前一轮只把 metadata store、schema sync、observability 基础打好，还缺“可用层”。
- 这次补的是最小运维闭环：
  1. 写连接配置
  2. 手动触发 schema 同步
  3. 查看表/列/关系
  4. 独立维护值映射

这样后续做“metadata -> semantic 草稿生成器”时，就不需要再绕回脚本或直接操作 SQLite。

## 涉及文件

- `app.py`
- `src/server/metadata_api.py`
- `src/qsql/schemas.py`
- `tests/test_metadata_api.py`

## 如何验证

```bash
.venv/bin/python -m pytest tests/test_metadata_api.py -q
ruff check app.py src tests scripts
python -m py_compile app.py $(find src -name '*.py' -print) $(find tests -name '*.py' -print) $(find scripts -name '*.py' -print)
.venv/bin/python -m pytest tests -q
```
