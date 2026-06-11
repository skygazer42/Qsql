# 2026-05-15 QSQL exact 命中直出训练 SQL

## 改了什么

- 在 `qsql/src/qsql/base/base.py` 增加 exact question 匹配辅助逻辑。
- 当用户问题与已训练 question 完全一致，且召回样本中存在对应 SQL 时，直接返回训练 SQL。
- 保留 `[QSQL] exact命中训练SQL直出` 诊断日志，记录 question/sql hash、长度、命中位置与耗时。

## 为什么改

- 诊断日志已证明：训练 SQL 被 Chroma exact 召回并进入 prompt，但 LLM 仍可能改写 SQL。
- 对用户明确训练过的相同问题，应优先稳定复用人工确认 SQL，避免 `temperature=0.7` 或模型自由生成导致漂移。

## 涉及文件

- `qsql/src/qsql/base/base.py`

## 如何验证

```bash
python -m py_compile src/qsql/base/base.py src/qsql/vllm/vllm.py
```

复现同一个已训练问题时，日志应出现：

```text
[QSQL] exact命中训练SQL直出
```

且不再出现同一次 SQL 生成对应的 `VLLM请求`。
