# 顶部 Logo 与架构图标识统一

## 改了什么

- 重做顶部 `QSQL` wordmark：
  - `static/brand/qsql-logo.svg`
- 重做 `mark` 图标：
  - `static/brand/qsql-mark.svg`
- 同步更新前端兼容别名：
  - `static/vanna.svg`
- 补充测试，约束 `logo` 与 `mark` 共享同一套核心图形标识

## 为什么改

- README 顶部原先使用的是一套抽象数据/线路风格图标
- 新增的中文架构总览图使用的是另一套更简洁的蓝色圆环标
- 两者同时出现时视觉不一致，品牌识别会断裂

这次统一后，README 顶部和架构图会使用同一套标识语言。

## 涉及文件

- `static/brand/qsql-logo.svg`
- `static/brand/qsql-mark.svg`
- `static/vanna.svg`
- `tests/test_brand_assets.py`

## 如何验证

```bash
python -m pytest tests/test_brand_assets.py
```
