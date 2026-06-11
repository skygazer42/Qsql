# KD-Vanna Agent 指南
本文档提供给在本仓库内工作的自动化编码代理。
目标：统一可执行命令、单测方式、代码风格与关键约束。

## 1. 项目基线
- 语言：Python
- Python：`>=3.9`（`pyproject.toml`）
- 构建后端：`flit_core.buildapi`
- 代码目录：`src/`
- 测试目录：`tests/`
- 应用入口：`app.py`

## 2. 常用命令（Build/Lint/Test/Run）
### 2.1 安装
```bash
# 开发安装
pip install -e .

# 含全部可选依赖
pip install -e ".[all]"
```

### 2.2 运行
```bash
python app.py

# Docker
docker-compose up
```

### 2.3 测试（重点）
```bash
# 全量
python -m pytest tests/

# 单文件
python -m pytest tests/test_vanna.py

# 单函数（推荐）
python -m pytest tests/test_vanna.py::test_vn_openai

# 关键字过滤（补充）
python -m pytest tests/ -k "vn_openai"

# 检索诊断脚本
python test_search_algorithm.py
```

### 2.4 Lint 与格式化
```bash
ruff check src/
ruff format src/
```

### 2.5 构建说明
- 日常开发通常不需要打包发布。
- 涉及发布时按团队流程执行，避免在普通功能任务中引入发布动作。

## 3. 代码风格规范
### 3.1 导入顺序
保持三段分组并用空行隔开：
1. 标准库
2. 第三方库
3. 项目内模块（优先 `from src...`）

要求：
- 不写 `import a, b`，拆分为多行。
- 删除未使用导入。

### 3.2 格式化
- 缩进：4 空格
- 编码：UTF-8
- 行尾：LF + 文件末尾换行
- 新代码目标行长：`<= 88`
- 仓库历史代码可见 `120` 行长（见 `src/.editorconfig`）
- 避免无关的大规模格式重排
- 字符串优先双引号 `"`

### 3.3 类型注解
- 新增函数应标注参数与返回类型。
- 公共接口优先完整注解。
- 可使用 `str | None`、`list[str]`、`dict[str, Any]`。

### 3.4 命名约定
- 函数/变量：`snake_case`
- 类：`PascalCase`
- 常量：`UPPER_SNAKE_CASE`
- 私有辅助函数：前缀 `_`

### 3.5 注释与文档字符串
- 变量名保持英文。
- 注释、日志、docstring 优先中文（与当前定制模块一致）。
- 注释解释“为什么”，不要复述显而易见的实现。

### 3.6 异常处理
- 关键路径必须容错，避免单点失败中断主流程。
- 记录上下文后降级返回（空列表、默认值等）。
- 可精确捕获时，不滥用裸 `except`。

### 3.7 日志规范
- 统一使用 `src.utils.log.Log`。
- 日志建议包含模块前缀、数据集 ID、数量、耗时、失败原因。
- 高频路径减少 `info` 噪音，必要时使用 `debug`。

## 4. 检索模块关键不变量
改动以下模块时必须重点保护：
- `src/vanna/chromadb/hybrid_search.py`
- `src/vanna/chromadb/bm25_jieba.py`

不变量：
1. 混合召回多通道能力不可意外删减。
2. `parent_id` 聚合链路不可破坏。
3. 元数据追加遵循“只补充缺失字段，不覆盖已有字段”。
4. 召回失败应可回退，保证主流程可用。
5. 改动索引结构时考虑 BM25/n-gram 缓存重建影响。

### 4.1 轻词过滤（`query_light_tokens.json`）约定

该配置用于“核心词抽取降噪”，避免通用词主导打分。

- 配置文件：`resources/query_light_tokens.json`
- 路径定义：`src/utils/setting.py` 中 `QUERY_LIGHT_TOKENS_PATH`
- 生效链路：
  1. `hybrid_search._load_light_query_tokens(dataset_id)` 加载 `global` 与 `datasets` 词表
  2. `hybrid_search._extract_core_tokens(...)` 分词后过滤轻词
  3. `_merge_scores(...)` 仅用剩余核心词做意图命中判断与惩罚/封顶

为什么要过滤：

1. 降低“在哪/如何/政策/咨询/常州”等高频泛词对排序的干扰。
2. 提高核心词区分度，让事项名、实体名、业务关键词更主导召回。
3. 避免意图命中误判（通用词几乎所有文档都命中，失去区分能力）。

选词原则（加入轻词前自检）：

- 高频但低区分度（多数文档都出现）。
- 问句模板词（在哪、怎么、哪里、如何等）。
- 语境默认词（如全库都在某城市，城市名可降权）。
- 不要把真正业务实体词加入轻词（会损伤召回准确率）。

维护建议：

- 优先在 `global` 放全局通用轻词；数据集特例放 `datasets.<dataset_id>`。
- 每次调整后至少执行：
  - `python test_search_algorithm.py`
  - `python -m pytest tests/test_vanna.py::test_vn_openai`
  并观察日志中的 `[Hybrid] 核心词` 是否符合预期。

### 4.2 检索链路（开发者速览）

主入口：`hybrid_search.chroma_search(query, dataset_id, top_k, threshold, metadata_filter)`

执行顺序（按真实链路）：

1. **模式判定**：`bm25_jieba.auto_alpha(query)`
   - `<=2 tokens`：KEYWORD（关键词主导）
   - `3~8 tokens`：BALANCED（语义/关键词平衡）
   - `>8 tokens`：SEMANTIC（语义主导）
2. **查询扩展**：`expand_query_variants` 读取 `resources/query_synonyms.json`，生成原查询 + 归一化查询。
3. **多通道召回**：
   - 语义：`embed_fn.smart_recall(..., where=metadata_filter)`
   - BM25：`bm25_recall(..., where=metadata_filter)`
   - 短查询增强（仅 KEYWORD）：`substring_recall` + `ngram_recall`
4. **融合打分**：`_merge_scores(...)`
   - KEYWORD：`0.2*sem + 0.25*bm25 + 0.35*substr + 0.2*ngram`
   - 其他模式：`alpha*sem + (1-alpha)*bm25`
5. **意图约束**：用核心词命中数做惩罚/封顶（`_NON_INTENT_SCORE_CAP=0.2`）。
6. **模式降噪**：
   - BALANCED：过滤无意图命中结果
   - KEYWORD：过滤“仅 n-gram 命中”噪声
7. **可选 rerank**：仅 `SEMANTIC` 且配置 `RERANK_MODEL` 时启用；失败自动回退原融合分。
8. **分块聚合**：按 `parent_id` 聚合 chunk，按 `chunk_index` 排序拼接；元数据仅补缺不覆盖。
9. **去重与截断**：按分数排序后取 `top_k`，再做 doc_id/文本去重并返回。

关键调参入口（优先级从高到低）：

1. `resources/query_light_tokens.json`（核心词降噪）
2. `resources/query_synonyms.json`（查询扩展）
3. `bm25_jieba.auto_alpha` 阈值与 `_merge_scores` 通道权重
4. `threshold`、`top_k`、`RERANK_MODEL`

### 4.3 检索超参数说明

以下参数可通过 API 入参、环境变量或配置文件调整，影响召回质量、精度与性能。

#### 入口参数（API 层）

- **`top_k`**（默认 `10`）
  - 含义：最终返回结果数量
  - 影响：值越大召回越全，但噪声可能增加
  - 建议：常规场景 5-20；需要高召回时可到 50
- **`threshold`**（默认 `0.5`）
  - 含义：融合分数/rerank 分数的最低阈值
  - 影响：值越高精度越高但召回可能下降
  - 建议：精度优先 0.6-0.8；召回优先 0.3-0.5
#### 模式与权重（自动/可调）
- **`alpha`**（自动计算，见 `auto_alpha`）
  - KEYWORD（<=2 tokens）：`alpha=0.2`（关键词主导）
  - BALANCED（3-8 tokens）：`alpha=0.6`（平衡）
  - SEMANTIC（>8 tokens）：`alpha=0.8`（语义主导）
  - 调整位置：`bm25_jieba.py:131-138`
- **KEYWORD 模式融合权重**
  - 公式：`0.2*sem + 0.25*bm25 + 0.35*substr + 0.2*ngram`
  - 调整位置：`hybrid_search.py:234-236`
#### 意图约束参数
- **`_NON_INTENT_SCORE_CAP`**（默认 `0.2`）
  - 含义：非意图命中文档的分数封顶值
  - 影响：防止无关文档排序过高
  - 调整位置：`hybrid_search.py:15`
#### 环境变量与缓存
- **`RERANK_MODEL`**（环境变量，默认空）
  - 含义：重排序模型名称
  - 启用条件：仅 SEMANTIC 模式生效
  - 调整：`export RERANK_MODEL=bge-reranker-v2-m3`
- **`BM25_TTL_SECONDS`**（默认 `600`）
  - 含义：BM25/n-gram 索引内存缓存时长（秒）
  - 调整位置：`bm25_jieba.py:29`
#### 通道特定参数
- **ngram `n`**（默认 `2`）
  - 含义：字符 n-gram 长度
  - 影响：值越大匹配越精确但召回可能下降
  - 调整位置：`bm25_jieba.py:390-395`（`ngram_recall` 参数）

## 5. 最小验证流程
建议顺序：
1. 跑受影响单测函数
2. 跑受影响测试文件
3. 跑 `ruff check src/`
4. 必要时跑全量 `python -m pytest tests/`

示例：
```bash
python -m pytest tests/test_vanna.py::test_vn_openai
python -m pytest tests/test_vanna.py
ruff check src/
```

## 6. 检索测试说明

当你（智能体）改动检索逻辑、轻词、同义词、权重或阈值时，按以下流程执行并汇报：

### 6.1 必跑命令

```bash
# 1) 单点回归（最小）
python -m pytest tests/test_vanna.py::test_vn_openai

# 2) 检索诊断脚本
python test_search_algorithm.py

# 3) A/B 对比（语义-only vs 混合）
python tests/test_retrieval_ab_compare.py \
  --dataset-id <dataset_id> \
  --query "<query>" \
  --top-k 10 \
  --threshold 0.0
```

### 6.2 A/B 对比要求

- 至少选择 3 类 query 各 3 条（共 ≥9 条）：
  1. 短 query（2 词以内，KEYWORD 倾向）
  2. 中等 query（3-8 词，BALANCED）
  3. 长 query（>8 词，SEMANTIC）
- 每条 query 记录：
  - `semantic_only` 数量
  - `hybrid.final` 数量
  - TopK 重叠数量
  - 是否出现 `balanced意图过滤: X -> 0`

### 6.3 日志核对点（必须）

在 `resources/logs/<date>/<hour>.log` 中核对：

1. `[Hybrid] 入参`（query/dataset_id/top_k/threshold/metadata_filter）
2. `[Hybrid] 语义召回 N 条` 与 `[Hybrid] BM25 召回 N 条`
3. `[Hybrid] 核心词: [...]`
4. `balanced意图过滤: X -> Y`
5. `[Hybrid] 融合后候选 N 条`
6. `[Hybrid] 去重后返回 N 条结果`

### 6.4 结果判定（建议标准）

- 不接受“静默退化”：
  - 改动前后，同一 query 集合中 `Y=0`（过滤后清空）的比例显著上升。
- 精度优先场景：
  - 允许结果数量下降，但 Top1/Top3 相关性不应变差。
- 召回优先场景：
  - 允许噪声略升，但不能大面积出现明显无关结果。

### 6.5 汇报模板（给 PR/评审）

请按下面结构输出测试结论：

```text
【改动点】
- xxx

【测试命令】
- python -m pytest tests/test_vanna.py::test_vn_openai
- python test_search_algorithm.py
- python tests/test_retrieval_ab_compare.py ...

【A/B 结果】
- query1: semantic_only=10, hybrid=3, overlap=2, balanced过滤=14->5
- query2: ...

【结论】
- 是否通过
- 风险点（如某类 query 仍易被过滤清空）
```

## 7. Agent 执行边界
- 仅修改与当前任务直接相关的代码。
- 不引入无关依赖或大规模重构。
- 不提交密钥/凭证/`.env` 等敏感信息。
- 不确定兼容性时先补测试再改动。

## ⚠️ 二开规范（必读）

本仓库基于 Vanna（<https://github.com/vanna-ai/vanna.git>）官方版本做二次开发，需要定期合并上游更新。本地官方镜像：`/work/project-github/vanna`。所有改动必须遵循以下原则。

### 1. 最小侵入原则

- 优先通过配置项关闭不需要的功能，不要删官方代码
- 没有配置项的，改最少的行数实现等价效果，避免牵连其它模块

### 2. 新增功能

- 代码中用 `# [CUSTOM]`（Python）或 `// [CUSTOM]`（TS/JS）注释标记所有新增/修改点，注明意图
- 在 `../docs/change-records/` 下创建变更记录（目录不存在时先建），命名 `YYYY-MM-DD-简要描述.md`
- 记录内容：改了什么、为什么改、涉及哪些文件、如何验证
- 重大调整先给方案、修改理由，确认后再动手

### 3. 修改现有功能

- 前提：不能影响主流程逻辑
- 所有修改点必须加 `# [CUSTOM]` / `// [CUSTOM]` 注释，说明改动意图
- 合并上游后用 `grep -rn "\[CUSTOM\]" api/ web/` 核对标记是否丢失，**升级版本时必须保留这些修改**，否则会导致功能回退
