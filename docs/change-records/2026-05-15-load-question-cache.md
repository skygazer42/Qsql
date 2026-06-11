## 改了什么

- `qsql/app.py` 中 `requires_cache` 增加可选缓存字段支持。
- `load_question` 仅要求 `question`、`sql`、`df` 必须存在，`fig_json`、`followup_questions` 缺失时允许返回 `None`。
- `get_question_history` 只返回已生成 `df` 的完整问答记录。

## 为什么改

历史列表原先会返回只有 `question` 的半成品记录。用户点击这类历史记录时，`load_question` 找不到 `df`，会返回 `No df found`，导致查看历史问题失败。

## 涉及文件

- `qsql/app.py`

## 如何验证

- `python -m py_compile app.py`
