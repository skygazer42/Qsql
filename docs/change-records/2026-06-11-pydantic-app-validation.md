## 改了什么

- 新增 `src/qsql/schemas.py`，定义 `AppConfigModel`、`GenerateSQLRequest`、`TrainRequest`
  等 Pydantic 模型，并提供 v1/v2 兼容解析与序列化方法。
- `app.py` 用 Pydantic 校验环境配置，替代手工 `_env_*` 转换；
  配置项包括 `VLLM_TEMPERATURE`、`N_RESULTS_*`、`QUESTION_SQL_*`。
- `app.py` 用模型化参数替代手工读取，覆盖：
  - `/api/v0/generate_sql`
  - `/api/v0/train`
  - `/api/v0/search`
  - `/api/v0/remove_training_data`
  - `/api/v0/delete_question_history`
- `pyproject.toml` 增加运行依赖 `pydantic`。
- `app.py` 加入 `_error_response`，把 Pydantic 参数校验失败统一返回 `400`。

## 为什么改

- 当前项目 `app.py` 大量依赖手工 `request.json.get(...)` 与环境变量类型转换，
  容易产生隐性空值、类型错误和跨端报文不一致问题。
- Text2SQL 流程链路关键字段（问题文本、SQL、DDL、训练内容、数据库配置）需要统一结构化边界与失败反馈，
  便于上线前快速发现参数污染与异常输入。

## 涉及文件

- `app.py`
- `pyproject.toml`
- `src/qsql/schemas.py`
- `docs/change-records/2026-06-11-pydantic-app-validation.md`

## 如何验证

- `python -m py_compile app.py src/qsql/schemas.py`
- `ruff check app.py src/qsql/schemas.py`
- `python -m pip install -e .`
- `curl 'http://127.0.0.1:5005/api/v0/generate_sql'`  
  - 缺少 `question` 应返回：`{\"type\":\"error\",\"error\":\"参数错误: ...\"}`
- `curl -X POST 'http://127.0.0.1:5005/api/v0/train' -H 'Content-Type: application/json' -d '{}'`  
  - 应返回：`{\"type\":\"error\",\"error\":\"No training content provided\"}`
