# 调整 README 顶部 wordmark 尺寸

## 改了什么

- 将 `README.md` 顶部 `qsql-logo-wordmark.png` 的显示宽度从 `760` 调整为 `620`

## 为什么改

- 原尺寸在 GitHub README 首屏偏大
- 缩小后更适合作为仓库门面，不会压过正文和下面的架构总览图

## 涉及文件

- `README.md`

## 如何验证

```bash
python -m pytest tests/test_brand_assets.py
```
