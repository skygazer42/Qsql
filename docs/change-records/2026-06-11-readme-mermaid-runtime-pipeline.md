# 2026-06-11 README Mermaid Runtime Pipeline

## 改了什么

- 将 `README.md` 中原先引用的运行时链路 SVG 图替换为内联 Mermaid 图。
- Mermaid 内容直接采用当前 QSQL 的运行时主链路、metadata 运维链路、可观测性链路和模型服务层结构。

## 为什么改

- README 中的主链路图需要更贴近当前实现，而且便于直接在仓库首页维护。
- Mermaid 文本图比静态 SVG 更适合后续继续调整字段名、路由名和层次关系。

## 涉及文件

- `README.md`
- `tests/test_brand_assets.py`
- `docs/change-records/2026-06-11-readme-mermaid-runtime-pipeline.md`

## 如何验证

- `python -m pytest tests/test_brand_assets.py -q`
