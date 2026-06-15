# 2026-06-15 relative time P2-1

## 改了什么

- `SemanticPostprocessor` 增加可选 `today` 参数，便于测试固定当前日期。
- 在缺少 `time_range` 时，新增通用中文相对时间解析：
  - 今年 / 本年
  - 本月 / 这个月
  - 近 N 天 / 最近 N 天
  - 上季度

## 为什么改

- 中文业务问数中相对时间非常高频，不能都转开放式澄清。
- 这些规则可以确定性处理，不需要交给 LLM 自由解释，也不绑定具体业务项目。

## 涉及文件

- `src/qsql/semantic_postprocessor.py`
- `tests/test_semantic_postprocessor.py`
- `docs/plans/2026-06-15-text2sql-landscape-and-integration-roadmap.md`

## 如何验证

- `.venv/bin/python -m pytest tests/test_semantic_postprocessor.py -q`
- `ruff check src/ app.py scripts tests test_search_algorithm.py`
- `.venv/bin/python -m pytest tests/`
