## 改了什么

- `qsql/app.py` 给 `generate_plotly_figure` 增加 `/api/v0/generate_plotly_figure` 路由别名。
- 保留原 `/api/v0/generate_plotly_figure/json` 路由不变。
- `qsql/static/custom-train-question.js` 增加前端请求兼容，将无 `/json` 的图表请求改写到已有 `/json` 路由，避免旧后端进程未重启时继续 404。
- `qsql/static/index.html` 为自定义脚本追加版本参数，避免浏览器继续使用旧缓存。

## 为什么改

当前静态前端打包产物调用的是无 `/json` 的 `/api/v0/generate_plotly_figure`。
后端只注册 `/api/v0/generate_plotly_figure/json` 时，前端会收到 404，并显示通用错误：
`The server returned an error. See the server logs for more details.`

## 涉及文件

- `qsql/app.py`
- `qsql/static/custom-train-question.js`

## 如何验证

- `python -m py_compile app.py`
- 导入 `app` 后检查 URL map 同时包含两个路由。
- `node --check static/custom-train-question.js`
