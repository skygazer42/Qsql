# 2026-06-11 Rename Transitional Repo Name To QSQL

## 改了什么

- 将仓库根目录从过渡目录名重命名为 `/data/temp/qsql`。
- 清理了仓库内残留的过渡目录名和旧绝对路径引用。
- 新增测试，约束仓库内不再出现历史中间目录名。

## 为什么改

- 当前项目正式名称已经收口为 `qsql`，保留 `kd-` 前缀没有业务意义。
- 之前的仓库目录名只是一次过渡命名，继续保留会让文档、路径和维护认知不一致。

## 涉及文件

- `tests/test_imports.py`
- `docs/**`
- `resources/**`
- 仓库根目录路径

## 如何验证

```bash
.venv/bin/python -m pytest tests -q
ruff check app.py src tests scripts
python -m py_compile app.py $(find src -name '*.py' -print) $(find tests -name '*.py' -print) $(find scripts -name '*.py' -print)
rg -n "legacy transitional repo name" app.py README.md pyproject.toml src tests scripts docs resources
```
