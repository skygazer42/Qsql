## 改了什么

- `qsql/static/index.html` 引入自定义前端补丁脚本。
- `qsql/static/custom-train-question.js` 在 SQL 训练弹窗中增加 `Question` 输入框。
- 提交 `/api/v0/train` 时，如果当前是 SQL 训练且填写了问题，会把 `question` 与 `sql` 一起提交。

## 为什么改

当前仓库只保留了前端打包产物，原 SQL 训练弹窗只有 SQL 输入框，无法手动指定问题。
后端 `/api/v0/train` 已支持 `question + sql`，因此通过轻量前端补丁补齐输入能力，避免直接修改压缩后的官方 bundle。

## 涉及文件

- `qsql/static/index.html`
- `qsql/static/custom-train-question.js`

## 如何验证

- `node --check static/custom-train-question.js`
- 打开训练数据页面，点击 `Add training data`，选择 `SQL`，确认出现 `Your Question` 输入框。
- 填写问题与 SQL 保存时，请求体应包含 `question` 与 `sql`。
