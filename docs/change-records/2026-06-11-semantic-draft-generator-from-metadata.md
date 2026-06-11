# 2026-06-11 从 Metadata 生成语义草稿

## 改了什么

- 新增 `src/qsql/semantic_draft_generator.py`
  - `generate_semantic_catalog_draft(...)`
  - `write_semantic_catalog_draft(...)`
- 新增 `SemanticDraftGenerateRequest`
- 新增 `SemanticDraftArtifact`
- metadata API 新增：
  - `POST /api/v0/metadata/<dataset_id>/semantic-draft/generate`
- metadata API 增加 `set_semantic_draft_dir(...)`
- `setting.py` 增加 `SEMANTIC_DRAFT_DIR`
- `resources/semantic/README.md` 补充草稿目录说明

## 为什么改

- 现在已经有：
  - schema metadata 落库
  - 手动/定时 schema sync
  - 值映射独立建模
  - 路由与阶段耗时埋点
- 但这几层之间还缺一个“闭环”：
  - 元数据和映射能存
  - 但还不能自动产出第一版语义目录草稿

这次补的是“metadata -> semantic draft”这一层，仍然不改主方向：

- 运行时仍然只吃正式 `resources/semantic/<dataset_id>.json`
- 自动生成内容只写到 `resources/semantic_drafts/<dataset_id>.json`
- 不自动覆盖生产 catalog

## 当前生成策略

- `tables` 基于 `schema_table`
- `dimensions` 基于非主键列，按数据类型推断 `kind/operators`
- `metrics` 至少生成每张表的 `count` 指标，并对数值列生成 `sum` 指标草稿
- `aliases` 基于生成后的指标/维度 label 自动补齐
- `value_mapping_hints` 与 `relationship_hints` 作为返回提示，不直接写入正式 catalog 结构

## 涉及文件

- `src/utils/setting.py`
- `src/qsql/schemas.py`
- `src/qsql/semantic_draft_generator.py`
- `src/server/metadata_api.py`
- `resources/semantic/README.md`
- `tests/test_semantic_draft_generator.py`
- `tests/test_metadata_api.py`

## 如何验证

```bash
.venv/bin/python -m pytest tests/test_semantic_draft_generator.py tests/test_metadata_api.py -q
ruff check app.py src tests scripts
python -m py_compile app.py $(find src -name '*.py' -print) $(find tests -name '*.py' -print) $(find scripts -name '*.py' -print)
.venv/bin/python -m pytest tests -q
```
