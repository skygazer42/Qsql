# 2026-05-15 QSQL 漂移诊断日志

## 改了什么

- 在 `qsql/app.py` 增加 `/api/v0/train` 与 `/api/v0/generate_sql` 的 `[QSQL]` 诊断日志。
- 在 `qsql/src/qsql/base/base.py` 增加训练入口、相似 SQL 召回、prompt 构建、LLM 响应与最终 SQL 的 `[QSQL]` 诊断日志。
- 在 `qsql/src/qsql/chromadb/chromadb_vector.py` 增加 question-SQL 训练样本写入与 Chroma 召回诊断日志。
- 在 `qsql/src/qsql/vllm/vllm.py` 增加 vLLM 初始化、请求与响应诊断日志。

## 为什么改

- 定位“同样问题命中训练 SQL 后生成结果仍漂移”的真实环节。
- 判断训练 SQL 是否成功写入、是否被 Chroma 召回、是否进入 prompt，以及是否由 LLM 生成阶段改写。
- 日志只记录 hash、长度、数量、耗时、状态码等摘要信息，不输出原始问题、SQL、prompt 或鉴权信息。

## 涉及文件

- `qsql/app.py`
- `qsql/src/qsql/base/base.py`
- `qsql/src/qsql/chromadb/chromadb_vector.py`
- `qsql/src/qsql/vllm/vllm.py`

## 如何验证

```bash
python -m py_compile app.py src/qsql/base/base.py src/qsql/chromadb/chromadb_vector.py src/qsql/vllm/vllm.py
node --check static/custom-train-question.js
```

## 观测方式

- 复现一次“保存训练 SQL + 相同问题生成 SQL”。
- 查看 `qsql/resources/logs/<date>/<hour>.log` 中的 `[QSQL]` 日志。
- 重点字段：
  - `train请求` / `Chroma写入SQL训练样本`：确认训练样本写入。
  - `Chroma召回SQL训练样本`：确认召回数量、距离与 `exact_question_count`。
  - `base召回完成` / `prompt构建完成`：确认训练 SQL 是否进入 prompt。
  - `VLLM请求` / `VLLM响应` / `base生成SQL完成`：确认温度参数与最终 SQL hash 是否漂移。
