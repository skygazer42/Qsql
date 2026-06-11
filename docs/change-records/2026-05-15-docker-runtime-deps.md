## 改了什么

- `qsql/pyproject.toml` 新增 `runtime` extra。
- `qsql/Dockerfile` 从 `pip install .[all]` 改为 `pip install "./[runtime]"`。

## 为什么改

`.[all]` 会安装所有可选 provider，其中包括当前镜像运行链路不使用的 `mistralai>=1.0.0`。
当 Docker 缓存失效后，pip 会重新从镜像源解析该依赖；如果镜像源缺少该包，就会导致构建失败。

## 运行时依赖范围

- 保留项目基础依赖。
- 额外补充 `app.py` 启动链路会直接或间接用到的依赖：`PyMySQL`、`starlette`、`langchain-community`、`langchain-text-splitters`。
- 不安装 Mistral、Qianfan、Anthropic、ZhipuAI、Ollama 等未使用 provider。

## 如何验证

- `python -m py_compile app.py`
- `python -m pip install --dry-run ".[runtime]"`
