# QSQL

QSQL 是当前仓库的正式名称。

它不是通用的 “LLM 直接写 SQL” 演示项目，而是一套已经收口到
`pydantic + pydantic-ai + controlled SQL` 的数据问答服务。

## 当前定位

- 模型负责语义解析，不直接自由生成 SQL
- 后端根据语义目录受控构造 SQL
- 运行时保留只读校验、结构校验、阶段耗时埋点
- 支持 metadata 落库、schema sync、semantic draft 生成

## 目录说明

- `app.py`
  - Flask 入口
- `src/qsql`
  - QSQL 核心运行时、语义服务、metadata、observability
- `src/server`
  - API 蓝图
- `resources/semantic`
  - 正式语义目录
- `resources/semantic_drafts`
  - 由 metadata 生成的语义草稿
- `tests`
  - 单测与回归测试

## 安装

```bash
pip install -e .
```

可选依赖：

```bash
pip install -e ".[all]"
```

## 运行

```bash
python app.py
```

## 核心环境变量

- `LLM_BASE_URL`
- `LLM_MODEL`
- `LLM_API_KEY`
- `LLM_TEMPERATURE`
- `METADATA_SYNC_ENABLED`
- `METADATA_SYNC_INTERVAL_SECONDS`

## 测试

```bash
python -m pytest tests/
ruff check app.py src tests scripts
```

## 当前架构

主链路已经统一到一条线上：

```text
question
-> semantic catalog
-> pydantic-ai semantic parse
-> pydantic validation
-> controlled SQL builder
-> read-only SQL execution
-> structured response
```

metadata 侧能力：

```text
dataset connection
-> schema sync
-> metadata store
-> value mappings
-> semantic draft generation
```

## 说明

这个仓库已经不再把自己当作“原样上游镜像”使用。
当前维护目标是面向业务数据问答的 QSQL 重构分支。
