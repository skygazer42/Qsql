# README 顶部 Logo 替换为新的 PNG Wordmark

## 改了什么

- 将用户提供的 `qsql_logo_vector_smooth010_4x.png` 复制到仓库：
  - `static/brand/qsql-logo-wordmark.png`
- 更新 `README.md` 顶部 logo，改为引用新的 PNG wordmark
- 补充测试，约束 README 持续使用该 PNG，而不是旧的 SVG 顶部 logo

## 为什么改

- 新提供的 wordmark 视觉更简洁，识别度更强
- 它更适合 README 顶部门面展示
- 保留现有 `qsql-mark.svg`，这样 favicon 和图标位不需要一起重做

## 涉及文件

- `README.md`
- `static/brand/qsql-logo-wordmark.png`
- `tests/test_brand_assets.py`

## 如何验证

```bash
python -m pytest tests/test_brand_assets.py
```
