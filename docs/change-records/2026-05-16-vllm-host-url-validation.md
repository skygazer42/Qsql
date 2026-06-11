# 2026-05-16 VLLM_HOST URL 校验与纠错

## 改了什么

- 在 `app.py` 启动早期校验 `VLLM_HOST`，确保项目模块导入前环境变量已是有效 URL。
- 对常见协议拼写错误 `hhttp://`、`hhttps://` 做自动纠正并记录 warning。
- 在 `src/qsql/vllm/vllm.py` 中清理 `vllm_host` 尾部斜杠，并在协议不合法时启动阶段报错。

## 为什么改

- 运行时出现 `requests.exceptions.InvalidSchema: No connection adapters were found for 'hhttp://.../v1/chat/completions'`。
- 仓库 `.env` 中配置为正确协议，但运行环境可能已有同名变量覆盖 `.env`，导致请求阶段才 500。
- 现在提前校验/纠错，避免错误延迟到用户请求时才暴露。

## 涉及文件

- `app.py`
- `src/qsql/vllm/vllm.py`

## 如何验证

```bash
python -m py_compile app.py src/qsql/vllm/vllm.py
```
