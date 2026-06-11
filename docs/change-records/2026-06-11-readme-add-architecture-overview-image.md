# README 增加用户提供的架构总览图

## 改了什么

- 将用户提供的 `41f965f3-eeae-4619-b635-85f711a6ebb3.png` 复制到仓库：
  - `docs/assets/qsql-architecture-overview-zh.png`
- 在 `README.md` 的“核心运行时链路”章节，使用该图片替换原先的总览 SVG 展示位
- 补充测试，约束 README 持续引用该图片

## 为什么改

- 这张图本身已经是完整的 QSQL 中文架构总览
- 放在 README 前半段更适合作为首个系统主视觉
- 保留后续 Mermaid 主链路图，可以兼顾“总览展示”和“文本可维护”

## 涉及文件

- `README.md`
- `docs/assets/qsql-architecture-overview-zh.png`
- `tests/test_brand_assets.py`

## 如何验证

```bash
python -m pytest tests/test_brand_assets.py
```
