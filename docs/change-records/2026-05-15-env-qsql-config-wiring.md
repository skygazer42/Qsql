# 2026-05-15 接入 QSQL 相关环境变量

## 改了什么

- `app.py` 接入 `.env` 中的以下配置：
  - `VLLM_TEMPERATURE`
  - `N_RESULTS_SQL`
  - `N_RESULTS_DOCUMENTATION`
  - `QUESTION_SQL_MAX_DISTANCE`
  - `QUESTION_SQL_DISTANCE_FILTER_ENABLED`
- `src/qsql/chromadb/chromadb_vector.py` 增加 question-SQL 历史样本距离过滤。
- 距离过滤只作用于非 exact 历史样本；exact question 命中永远保留，避免误杀已训练的相同问题 SQL。

## 为什么改

- 原先 `.env` 中只有 `N_RESULTS_DDL` 接入主链路。
- `VLLM_TEMPERATURE=0.0`、`N_RESULTS_SQL`、`N_RESULTS_DOCUMENTATION` 写在 `.env` 里但运行时不生效。
- 非 exact 的低相似 SQL 样本可能进入 prompt，增加 token 长度并干扰生成。

## 涉及文件

- `app.py`
- `src/qsql/chromadb/chromadb_vector.py`

## 如何验证

```bash
python -m py_compile app.py src/qsql/chromadb/chromadb_vector.py src/qsql/base/base.py src/qsql/vllm/vllm.py
```

启动后检查日志：

```text
[QSQL] 应用启动配置 ... temperature=... n_results_sql=... n_results_documentation=...
[QSQL] Chroma召回SQL训练样本 ... distance_filter_enabled=... distance_threshold=...
```
