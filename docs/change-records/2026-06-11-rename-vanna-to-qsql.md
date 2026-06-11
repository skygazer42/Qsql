# 2026-06-11 Rename Vanna To QSQL

## 改了什么

- 删除了仓库内的 `.sisyphus/` 草稿与计划目录。
- 将核心 Python 包目录从 `src/vanna` 重命名为 `src/qsql`。
- 将仓库根目录从 `/data/temp/kd-vanna` 重命名为 `/data/temp/qsql`。
- 将项目分发名从 `vanna` 改为 `qsql`。
- 同步修正了 `app.py`、测试、README、`pyproject.toml` 中的包路径和项目命名。
- 保留了 `src/qsql/__init__.py` 中一个历史 hosted endpoint URL，仅作为遗留兼容常量，不再作为当前主链路品牌命名。

## 为什么改

- 当前仓库已经不是原始 Vanna 形态，而是基于 `pydantic + pydantic-ai + controlled SQL` 重构后的独立分支。
- 继续保留 `kd-vanna` / `src.vanna` 命名会误导维护者，和当前架构定位不一致。
- `.sisyphus/` 不参与运行时，也不属于当前项目正式产物，保留没有价值。

## 涉及文件

- `pyproject.toml`
- `README.md`
- `app.py`
- `src/qsql/**`
- `tests/**`
- `docs/change-records/2026-06-11-rename-vanna-to-qsql.md`

## 如何验证

```bash
.venv/bin/python -m pytest tests -q
ruff check app.py src tests scripts
python -m py_compile app.py $(find src -name '*.py' -print) $(find tests -name '*.py' -print) $(find scripts -name '*.py' -print)
```
