# 向量化接口增强：向量字段与元数据分离

## 概述

本次更新在保留 `/api/v0/<dataset_id>/generate` 的同时，新增 `/api/v0/<dataset_id>/generate/advanced` 与 `/api/v0/<dataset_id>/search` 能力，支持：
1. **指定向量化字段**：可以选择数据中的特定字段进行向量化
2. **元数据字段分离**：额外的元数据用于过滤检索，不参与向量化
3. **元数据过滤检索**：支持基于元数据条件的精确过滤

## 1. 向量化接口 `/generate` 与 `/generate/advanced`

### 1.1 基础用法（向后兼容）

```bash
POST /api/v0/my_dataset/generate/advanced
Content-Type: application/json

{
    "data": [
        {
            "name": "iPhone 15 Pro",
            "description": "最新款苹果手机，搭载A17芯片",
            "price": 7999,
            "category": "电子产品"
        }
    ],
    "enable_describe": false
}
```

**说明**：整个 `data` 对象会被序列化为 JSON 字符串进行向量化。

---

### 1.2 指定向量化字段（新功能）

```bash
POST /api/v0/my_dataset/generate/advanced
Content-Type: application/json

{
    "data": [
        {
            "name": "iPhone 15 Pro",
            "description": "最新款苹果手机，搭载A17芯片",
            "price": 7999,
            "category": "电子产品",
            "brand": "Apple"
        }
    ],
    "vector_fields": ["name", "description"],
    "metadata_fields": ["category", "brand"]
}
```

**效果**：
- **向量化内容**：`name` 和 `description` 字段会被提取并以 JSON 串形式存储：`{"name": "iPhone 15 Pro", "description": "最新款苹果手机，搭载A17芯片"}`
- **元数据存储**：`category` 和 `brand` 字段会从 `data` 中自动提取并存储到 ChromaDB 的 metadata 中

---

### 1.3 使用 LLM 生成描述

```bash
POST /api/v0/my_dataset/generate
Content-Type: application/json

{
    "data": [
        {
            "product_id": "P001",
            "name": "iPhone 15 Pro",
            "specs": {
                "chip": "A17",
                "ram": "8GB",
                "storage": "256GB"
            },
            "price": 7999
        }
    ],
    "vector_fields": ["name", "specs"],
    "enable_describe": true,
    "custom_prompt": "请用专业的语言描述以下产品规格：",
    "metadata_fields": ["product_id", "category"]
}
```

**效果**：
- LLM 会将 `name` 和 `specs` 转换为自然语言描述
- 生成的描述文本用于向量化
- `product_id` 和 `category` 从 `data` 中提取并存储为元数据

---

## 2. 检索接口 `/search`

### 2.1 基础检索（向后兼容）

```bash
POST /api/v0/my_dataset/search
Content-Type: application/json

{
    "query": "高性能手机",
    "top_k": 10,
    "threshold": 0.5
}
```

---

### 2.2 基于元数据过滤的检索（新功能）

#### 示例 1：简单过滤

```bash
POST /api/v0/my_dataset/search
Content-Type: application/json

{
    "query": "高性能手机",
    "top_k": 10,
    "threshold": 0.5,
    "metadata_filter": {
        "category": "电子产品"
    }
}
```

**效果**：只检索 `category` 为 "电子产品" 的数据。

---

#### 示例 2：复杂条件过滤

```bash
POST /api/v0/my_dataset/search
Content-Type: application/json

{
    "query": "高性能手机",
    "top_k": 10,
    "threshold": 0.5,
    "metadata_filter": {
        "$and": [
            {"category": "电子产品"},
            {"brand": "Apple"},
            {"price_tier": "旗舰"}
        ]
    }
}
```

**效果**：同时满足三个条件的数据才会被检索。

---

#### 示例 3：范围查询（如果元数据支持）

```bash
POST /api/v0/my_dataset/search
Content-Type: application/json

{
    "query": "性价比手机",
    "top_k": 10,
    "metadata_filter": {
        "$and": [
            {"category": "电子产品"},
            {"timestamp": {"$gte": "2026-01-01"}}
        ]
    }
}
```

---

## 3. ChromaDB Metadata 过滤语法

ChromaDB 支持以下操作符：

### 3.1 基础操作符

| 操作符 | 说明 | 示例 |
|--------|------|------|
| `$eq` | 等于 | `{"category": {"$eq": "电子产品"}}` 或简写 `{"category": "电子产品"}` |
| `$ne` | 不等于 | `{"status": {"$ne": "deleted"}}` |
| `$gt` | 大于 | `{"price": {"$gt": 1000}}` |
| `$gte` | 大于等于 | `{"price": {"$gte": 1000}}` |
| `$lt` | 小于 | `{"price": {"$lt": 5000}}` |
| `$lte` | 小于等于 | `{"price": {"$lte": 5000}}` |
| `$in` | 在列表中 | `{"category": {"$in": ["电子产品", "数码配件"]}}` |
| `$nin` | 不在列表中 | `{"status": {"$nin": ["deleted", "archived"]}}` |

### 3.2 逻辑操作符

| 操作符 | 说明 | 示例 |
|--------|------|------|
| `$and` | 与 | `{"$and": [{"category": "电子产品"}, {"brand": "Apple"}]}` |
| `$or` | 或 | `{"$or": [{"brand": "Apple"}, {"brand": "Samsung"}]}` |

---

## 4. 完整使用流程示例

### 4.1 创建数据集

```bash
POST /api/v0/dataset/create
Content-Type: application/json

{
    "dataset_id": "product_knowledge"
}
```

---

### 4.2 批量导入产品数据

```bash
POST /api/v0/product_knowledge/generate/advanced
Content-Type: application/json

{
    "data": [
        {
            "product_id": "P001",
            "name": "iPhone 15 Pro",
            "description": "搭载A17 Pro芯片的旗舰手机，支持钛金属边框",
            "price": 7999,
            "brand": "Apple",
            "category": "智能手机"
        },
        {
            "product_id": "P002",
            "name": "MacBook Pro 16",
            "description": "M3 Max芯片，专业创作者的首选笔记本",
            "price": 25999,
            "brand": "Apple",
            "category": "笔记本电脑"
        },
        {
            "product_id": "P003",
            "name": "小米14 Ultra",
            "description": "徕卡光学镜头，骁龙8 Gen3处理器",
            "price": 5999,
            "brand": "Xiaomi",
            "category": "智能手机"
        }
    ],
    "vector_fields": ["description"],
    "metadata_fields": ["product_id", "brand", "category"]
}
```

**注意**：
- `vector_fields` 指定的字段会被提取并以 JSON 串形式向量化
- `metadata_fields` 指定的字段会从每条 `data` 中自动提取并存储为元数据
- 每条数据的元数据字段值可以不同

---

### 4.3 精确检索

#### 场景 1：查找苹果品牌的手机

```bash
POST /api/v0/product_knowledge/search
Content-Type: application/json

{
    "query": "高性能拍照手机",
    "top_k": 5,
    "threshold": 0.3,
    "metadata_filter": {
        "$and": [
            {"brand": "Apple"},
            {"category": "智能手机"}
        ]
    }
}
```

**结果**：只会返回 iPhone 15 Pro，不会返回 MacBook 或小米手机。

---

#### 场景 2：查找所有笔记本电脑

```bash
POST /api/v0/product_knowledge/search
Content-Type: application/json

{
    "query": "适合创作的设备",
    "top_k": 5,
    "metadata_filter": {
        "category": "笔记本电脑"
    }
}
```

---

#### 场景 3：查找特定来源的数据

```bash
POST /api/v0/product_knowledge/search
Content-Type: application/json

{
    "query": "专业设备",
    "top_k": 10,
    "metadata_filter": {
        "$and": [
            {"source": "产品数据库"},
            {"verified": true}
        ]
    }
}
```

---

## 5. 最佳实践

### 5.1 元数据字段设计建议

1. **分类字段**：`category`、`type`、`status` 等枚举值
2. **标识字段**：`product_id`、`user_id`、`order_id` 等唯一标识
3. **时间字段**：`created_at`、`updated_at`、`import_date` 等
4. **来源字段**：`source`、`channel`、`system` 等
5. **标签字段**：`tags`、`labels`、`flags` 等

### 5.2 向量化字段选择建议

- **优先选择语义丰富的字段**：如 `description`、`content`、`summary`
- **避免向量化结构化数据**：如 ID、价格、日期等
- **可以组合多个字段**：如果需要，可以在应用层拼接后传入

### 5.3 性能优化建议

1. **合理使用 metadata 过滤**：先用 metadata 缩小范围，再进行语义检索
2. **避免过度复杂的过滤条件**：过多的 `$and`/`$or` 嵌套会影响性能
3. **元数据字段不宜过多**：建议控制在 10 个以内
4. **元数据值不宜过长**：单个字段建议不超过 1000 字符

---

## 6. 向后兼容性

所有新参数都是可选的，现有代码无需修改：

```bash
# 旧代码仍然可以正常工作
POST /api/v0/my_dataset/generate
{
    "data": [...],
    "enable_describe": false,
    "custom_prompt": "",
    "custom_metas": ""
}
```

新参数说明：
- `vector_fields`：默认为 `[]`，为空时使用完整 data 进行向量化
- `metadata_fields`：默认为 `None`，不添加额外元数据
- `metadata_filter`：默认为 `None`，不进行元数据过滤

---

## 7. 常见问题

### Q1: `vector_fields` 和 `metadata_fields` 有什么区别？

**A**: 
- `vector_fields`：指定字段名数组，这些字段的值会被提取并以 JSON 串形式生成向量（embedding）
- `metadata_fields`：指定字段名数组，这些字段的值会从 `data` 中提取并存储为元数据，用于过滤检索

### Q2: 如果不指定 `vector_fields` 会怎样？

**A**: 整个 `data` 对象会被序列化为 JSON 字符串进行向量化（保持原有行为）。

### Q3: `metadata_fields` 支持什么格式？

**A**: 支持两种格式：
1. **字段名数组（推荐）**：`["category", "brand"]` - 自动从每条 `data` 中提取对应字段的值
2. **字典（兼容旧方式）**：`{"category": "电子产品"}` - 直接使用提供的值，应用到所有数据

### Q4: 元数据过滤会影响检索性能吗？

### Q5: 向量化字段是如何存储的？

**A**: 指定的 `vector_fields` 会被提取并以 JSON 串形式存储，例如：`{"name": "iPhone 15 Pro", "description": "最新款苹果手机"}`

---

## 8. 技术实现细节

### 8.1 数据存储结构

```python
# ChromaDB 存储结构
{
    "ids": ["uuid-1", "uuid-2"],
    "documents": ["向量化的 JSON 串"],  # 例如: {\"name\": \"iPhone 15 Pro\", \"description\": \"...\"}
    "metadatas": [
        {
            # chunk 自带的元数据
            "chunk_index": 0,
            "chunk_total": 1,
            "parent_id": "parent-uuid",
            "chunk_type": "json",
            
            # 从 data 中提取的 metadata_fields
            "category": "电子产品",
            "brand": "Apple",
            "product_id": "P001"
        }
    ],
            
            # 向后兼容：custom_metas
            "custom_data": "..."
        }
    ],
    "embeddings": [[0.1, 0.2, ...]]
}
```

### 8.2 检索流程

1. **元数据预过滤**：如果提供了 `metadata_filter`，先在 ChromaDB 层面过滤
2. **语义检索**：在过滤后的数据中进行向量相似度计算
3. **混合排序**：结合 BM25、n-gram 等多种召回策略
4. **结果返回**：返回最终的 top_k 结果

---

## 9. 示例代码（Python）

```python
import requests

# 1. 向量化数据
response = requests.post(
    "http://localhost:5000/api/v0/my_dataset/generate/advanced",
    json={
        "data": [
            {
                "title": "Python 编程指南",
                "content": "这是一本适合初学者的 Python 教程",
                "author": "张三",
                "category": "编程",
                "year": 2024
            }
        ],
        "vector_fields": ["content"],
        "metadata_fields": ["category", "author", "year"]
    }
)
print(response.json())

# 2. 检索数据
response = requests.post(
    "http://localhost:5000/api/v0/my_dataset/search",
    json={
        "query": "适合新手的编程书籍",
        "top_k": 5,
        "threshold": 0.3,
        "metadata_filter": {
            "$and": [
                {"category": "编程"},
                {"difficulty": "初级"}
            ]
        }
    }
)
print(response.json())
```

---

## 10. 总结

本次更新实现了：
✅ 向量化字段与元数据字段的清晰分离  
✅ 支持基于元数据的精确过滤检索  
✅ 完全向后兼容，不影响现有代码  
✅ 符合向量数据库的最佳实践  

这种设计模式在 Pinecone、Weaviate、Milvus 等主流向量数据库中都有广泛应用，能够显著提升检索的精确度和灵活性。

---

## 11. 自 `ae3304b7a238cf86bbe38e27329cac36c27c5f04` 起的升级记录（全量）

本节汇总提交 `ae3304b7a238cf86bbe38e27329cac36c27c5f04` 之后（不含该提交）到当前 HEAD 的全部升级/更新内容。

### 11.1 提交概览

共 5 个提交：

1. `18736d24bce9bb94ddc73e034205d18b1a077c5a`（2026-03-06）- 增加元数据的功能
2. `c9693d7d3d14f1a475a59664daa8602e6672fe15`（2026-03-07）- 升级框架
3. `5e00bb6212e97f38b037737a4bc5f8190cb6b13c`（2026-03-08）- 提升短语增强检索
4. `ba2d2e5e54868322d40ba2e10418f78799a1efc1`（2026-03-08）- 再次优化检索质量
5. `e5faeea4e46ae158d59bb547dfff8db6228e3e53`（2026-03-08）- 设置日志的级别

### 11.2 逐提交更新明细

#### 11.2.1 `18736d24` - 增加元数据能力（首轮）

核心能力：

- 新增高级向量化接口：`/api/v0/<dataset_id>/generate/advanced`
  - 支持 `vector_fields`：指定参与向量化的字段。
  - 支持 `metadata_fields`：分离并存储元数据字段。
- 检索接口 `/api/v0/<dataset_id>/search` 新增 `metadata_filter` 参数。
- 检索返回结构统一为 `id/text/score/source`。

存储与召回链路：

- 原 `utils.py` 重构为 `vector_store_service.py`（迁移/重命名）。
- 新增 `vectorize_helpers.py`，拆分数据归一化、字段抽取、元数据构建、入库等公共逻辑。
- `OpenAICompatibleEmbeddingFunction.smart_recall` 支持 `where` 过滤。
- 检索链路支持按 `parent_id` 聚合分块并回填完整内容。

部署与工程：

- Docker 基础镜像改为 `python:3.10-slim`。
- 安装流程改为 `pip install .[all]`。
- `docker-compose.yaml` 镜像版本：`qsql:0.0.2` -> `qsql:0.0.3`。
- 新增本文档（元数据接口说明）的初版。

变更文件：

- `Dockerfile`
- `docker-compose.yaml`
- `docs/API_USAGE_METADATA.md`
- `src/server/structured_embed_api.py`
- `src/server/train_embed_api.py`
- `src/qsql/chromadb/vector_store_service.py`（由 `utils.py` 迁移）
- `src/qsql/chromadb/vectorize_helpers.py`
- `src/qsql/xinference/embedding.py`
- `tests/test_structured_embed.py`

#### 11.2.2 `c9693d7d` - 框架升级与元数据语义统一

接口语义调整：

- `generate/advanced` 的 `metadata_fields` 主语义调整为“字段名列表抽取”。
- 元数据拼接策略调整为“只补充缺失字段，不覆盖已有字段”。

检索与预处理优化：

- `bm25_jieba.auto_alpha` 分段调整：
  - `<=2` 词：关键词模式
  - `<=5` 词：平衡模式
  - `<=10` 词：语义模式（0.7）
  - 其余：语义模式（0.8）
- 中文分词放宽到 `len >= 1`。
- 文本清洗增强：去链接、邮箱、JSON 特殊符号与多余空格。
- `bm25_recall`、`ngram_recall`、`substring_recall` 支持 `where`。
- `smart_recall` 支持 `where` 透传到 Chroma。

其他：

- `document_embed_api.py` 以格式化与可读性优化为主。
- 本文档同步更新示例与 FAQ，以匹配 `metadata_fields` 新语义。

变更文件：

- `docs/API_USAGE_METADATA.md`
- `src/server/document_embed_api.py`
- `src/qsql/chromadb/bm25_jieba.py`
- `src/qsql/chromadb/vector_store_service.py`
- `src/qsql/chromadb/vectorize_helpers.py`
- `src/qsql/xinference/embedding.py`

#### 11.2.3 `5e00bb62` - 提升短语增强检索（模块化）

架构升级：

- 新增独立模块：`src/qsql/chromadb/hybrid_search.py`。
- 将 `vector_store_service.py` 中检索逻辑拆出，形成向量存储与检索解耦。

检索能力增强：

- 在 `hybrid_search.py` 分层实现：多通道召回、融合打分、可选 rerank、分块聚合、去重。
- BM25/n-gram 召回阶段从数据库实时回填文档，降低索引旧数据风险。
- BM25 只保留正分结果，减少低质量候选。

参数策略：

- `auto_alpha` 调整为：
  - `<=3` 词：关键词模式（0.2）
  - `<=8` 词：平衡模式（0.5）
  - `>8` 词：语义模式（0.8）

变更文件：

- `src/qsql/chromadb/bm25_jieba.py`
- `src/qsql/chromadb/hybrid_search.py`（新增）
- `src/qsql/chromadb/vector_store_service.py`

#### 11.2.4 `ba2d2e5e` - 再次优化检索质量（权重与路由）

路由与调用链：

- `structured_embed_api.py` 的搜索入口切换为 `hybrid_search.chroma_search`。
- Dify 检索入口同样切换到 `hybrid_search`。
- 清理 `generate_route` 中旧 `custom_metas` 透传参数。

融合评分优化：

- 语义分负值先裁剪到 0 再归一化。
- 关键词模式权重调整为：
  - `0.2*semantic + 0.25*bm25 + 0.35*substring + 0.2*ngram`
- 增加原始分与归一化分日志，提升调参与排障效率。

代码组织：

- `get_chroma_collection`、`OpenAICompatibleEmbeddingFunction` 导入上移到模块级。
- `vector_store_service.py` 移除未使用的 `hybrid_search` 导入。

变更文件：

- `src/server/structured_embed_api.py`
- `src/qsql/chromadb/hybrid_search.py`
- `src/qsql/chromadb/vector_store_service.py`

#### 11.2.5 `e5faeea4` - 日志等级可配置 + 检索策略微调

日志体系：

- `src/utils/log.py` 支持 `LOG_LEVEL` 环境变量控制日志等级。
  - 默认 `DEBUG`。
  - 同步作用于 logger、控制台 handler、文件 handler。
- `docker-compose.yaml` 增加：`LOG_LEVEL: "INFO"`。

检索策略微调：

- `bm25_jieba.py`
  - `auto_alpha` 调整：`<=2` 词关键词，`<=8` 词平衡（0.6）。
  - 词性白名单新增 `r`。
  - 地名停用词加载逻辑临时注释。
- `hybrid_search.py`
  - 关键词模式权重调整为：
    - `0.1*semantic + 0.35*bm25 + 0.35*substring + 0.2*ngram`
  - 长查询模式中，语义分 `<=0` 的候选分置零，抑制纯关键词噪声上浮。
  - 部分日志由 `info` 下调为 `debug`，降低常规噪音。

变更文件：

- `docker-compose.yaml`
- `src/utils/log.py`
- `src/qsql/chromadb/bm25_jieba.py`
- `src/qsql/chromadb/hybrid_search.py`

### 11.3 本阶段升级主线总结

1. 元数据能力上线：向量字段与元数据字段彻底分离，支持 `metadata_filter` 精确检索。
2. 检索链路模块化：`hybrid_search` 独立，检索策略可维护性显著提升。
3. 检索质量持续调优：`auto_alpha`、融合权重、负分处理经历多轮迭代。
4. 可观测性增强：日志级别可配置，默认部署噪音从 `DEBUG` 收敛至 `INFO`。
