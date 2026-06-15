# 2026-06-15 runtime security and deployment hardening

## 改了什么

- 收紧无鉴权默认行为：未配置 `SECRET_ACCESS_KEY` 时默认拒绝请求，仅允许显式设置 `QSQL_ALLOW_UNAUTHENTICATED=true` 做本地调试。
- 直连 MySQL SQL 接口增加只读守卫，仅允许单条 `SELECT` / `WITH ... SELECT` 查询。
- Plotly 图表生成不再 `exec` 模型返回的 Python 代码，改为受限 AST 解析，失败时降级自动图表。
- Docker 运行时切换到 Python 3.11，端口元数据改为 `5005`，并扩充 `.dockerignore` 排除 `.env`、`.venv`、`.git` 等本地状态。
- 依赖从 `pydantic-ai` 元包收窄为 `pydantic-ai-slim[openai]`，避免 Docker 构建拉取未使用的 provider extras。
- `.gitignore` 补充 `resources/jieba/`，避免诊断脚本运行时生成的 jieba 缓存进入版本库。
- README 词标引用切换到 PNG，并补充对应 PNG 静态资产。
- 补回 `test_search_algorithm.py` 根目录诊断入口，使 AGENTS.md 中的无参检索诊断命令可执行。

## 为什么改

- 当前依赖锁定包含 Python `>=3.11` 包，原 Docker Python 3.10 会安装失败。
- `.dockerignore` 过窄会把本地密钥文件和虚拟环境带进镜像上下文。
- 空 `SECRET_ACCESS_KEY` 会让高风险运维与 SQL 接口无鉴权暴露。
- `exec` 模型生成代码存在提示注入放大的远程代码执行面。
- README 与品牌资产测试期望不一致，导致测试不绿。

## 涉及文件

- `app.py`
- `src/server/use_mysql_api.py`
- `src/qsql/base/base.py`
- `pyproject.toml`
- `Dockerfile`
- `.dockerignore`
- `.gitignore`
- `README.md`
- `static/brand/qsql-logo-wordmark.png`
- `test_search_algorithm.py`
- `tests/`

## 如何验证

- `.venv/bin/python -m pytest tests/`
- `ruff check src/ app.py scripts tests`
- `python test_search_algorithm.py`
- `python -m pip install --dry-run "pandas==3.0.3" "scikit-learn==1.9.0" "pydantic-ai-slim[openai]==1.107.0" "requests==2.34.2"`
