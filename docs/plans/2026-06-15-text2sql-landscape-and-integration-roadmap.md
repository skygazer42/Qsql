# 2026-06-15 Text2SQL 主流方案调研与 QSQL 集成路线图

- 状态：提案 / 待评审（draft）
- 范围：基于主流开源 text2sql 项目与 2024–2026 学术进展，规划可集成进 QSQL 或用于优化的方向。
- 结论先行：**QSQL 当前的「语义层 + LLM 受控解析」路线与业界公认的可靠方向一致，不需要推翻；本路线图聚焦补齐已被验证的几块短板。**

---

## 一、调研方法与局限（先说清楚，便于后续校验）

- 信息来源：针对 7 个子问题发起的多路 web 搜索 + QSQL 全量代码精读。
- 局限 1：原计划的多 agent 深度研究流程因并发限流（429）失败，本报告基于常规搜索摘要，部分论文数字由检索层小模型综合，**未逐篇 fetch 原始 paper 核实**，立项时应回到原文确认。
- 局限 2：dbt / Cube 的准确率数字（如 83% vs 40%、提升 3–5×）均为**厂商自测、利益相关**，仅作方向性参考。其方向性结论有独立背书：Spider 2.0（ICLR 2025 Oral）作者明确主张 text2sql 要「超越 single-shot，引入 schema linking / value retrieval / candidate voting / selection」。
- 局限 3：Spider 2.0 企业级真实场景当前 SOTA 仅 30–42%（ReFoRCE 35.83），说明开放式 text2sql 在真实复杂库上仍不可靠——这反向印证 QSQL 受控收口的价值。

---

## 二、QSQL 在赛道中的定位

| 项目 | 路线 | 与 QSQL 的关系 |
|---|---|---|
| WrenAI | 语义层（MDL）+ RAG，metadata-only 安全优先 | 哲学最接近 QSQL；但与其 web 平台耦合深 |
| dbt MetricFlow | YAML 语义模型，实体图自动 join，确定性 SQL | QSQL 语义目录的「成熟形态」，join 机制最值得借鉴 |
| Cube | 语义层 + RAG + 预聚合 | 可借「预聚合」做查询加速 |
| Vanna | RAG + 自学习，LLM 直接生成 SQL（MIT） | 路线不同；其「训练样例库」思路可借作 few-shot |
| DB-GPT | 多 agent + workflow | 维护 eosphoros-ai/Awesome-Text2SQL，值得长期跟踪 |
| Dataherald | 早期开源 NL2SQL | 2024 后活跃度下降，可不投入 |

一句话定位：**QSQL ≈ WrenAI 的受控安全哲学 + dbt MetricFlow 的指标层雏形 + 自研中文混合检索**；缺口主要是 MetricFlow 式的受控 join 与学术界的多候选 / 执行反馈。

---

## 三、优先级总览

| 优先级 | 方向 | 对位现状 | 与受控哲学 |
|---|---|---|---|
| P0-1 | 受控多表 join（实体/关系图） | `sql_builder.py` 多处硬 `raise 单表宽表` | 完全契合 |
| P0-2 | 多候选投票 + 执行反馈（适配 draft 范式） | `semantic_agent.py` 单次 `run_sync` | 契合（投在 draft 层） |
| P1-1 | value retrieval（列值索引） | 已有 BM25 / value_mapping，可强化 | 契合 |
| P1-2 | 评测对齐 BIRD / Spider 风格 | `semantic_eval_runner.py` 已是雏形 | 契合 |
| P1-3 | 澄清升级：多选题 + 信息增益 | `semantic_service.py` 开放式澄清 | 契合 |
| P2-1 | 相对时间解析（上季度 / 近 30 天） | `semantic_postprocessor.py` 正则较弱 | 契合 |
| P2-2 | 多指标查询 | `_mark_multi_metric_questions` 直接转澄清 | 契合 |
| P2-3 | few-shot 示例检索 | 已有 chromadb，可复用 | 契合 |
| 谨慎 | LLM 自由写 SQL / 开放 agent / RL 微调 | — | 与受控哲学冲突，暂不做 |

---

## 四、P0 路线（高 ROI，完全契合受控哲学）

### P0-1 受控多表 join：把「硬拒绝」换成「实体图自动 join」

**目标**：在不放开「LLM 自由 join」的前提下，把能力从单表宽表扩展到多表。

**现状对位**：
- `src/qsql/sql_builder.py::build_query_execution_plan` 在 `time_dimension.table_key != metric.table_key`、filter 维度跨表、group_by 维度跨表三处硬 `raise ValueError("当前只支持单表宽表查询")`。
- `src/qsql/schemas.py::SemanticCatalog` 目前只有 tables / metrics / dimensions / aliases / metric_versions，无实体与关系定义。
- 但 `SemanticDraftArtifact.relationship_hints` 已存在，metadata 侧已能产出关系线索，可直接对接。

**业界做法（dbt MetricFlow，可直接照搬模型）**：
- 定义 entities（实体）= join key，分 primary / foreign 等类型。
- 引擎把 semantic models 当节点、join path 当边构成语义图，按需自动 join。
- 智能选 join 类型：fct+dim 用 LEFT JOIN，多 fct 用 FULL OUTER JOIN，并主动防止 fan-out / chasm join。

**落地设计要点**：
- `schemas.py` 新增 `SemanticEntityDefinition`（table_key、field、entity_type）与 `SemanticRelationshipDefinition`（left/right table、join key、join 类型、是否允许）。
- `SemanticCatalog._validate_catalog_references` 增加对实体 / 关系引用的加载期校验（与现有引用校验同等级别）。
- `sql_builder` 增加 join 规划：**只允许走 catalog 预声明的 join path**，找不到 path 时 `raise`（保持「不静默兜底」原则），LLM 永远不能自创 join。
- 优先支持「事实表 + 维度表」星型 join，先不做多事实表。

**改动文件（预估）**：`src/qsql/schemas.py`、`src/qsql/sql_builder.py`、`src/qsql/semantic_catalog.py`、`resources/semantic/<dataset>.json`（示例目录补 entities/relationships）、`tests/`。

**验收标准**：
- 新增 `tests/test_sql_builder_join.py`：覆盖合法 join path 生成、非法/未声明 join path 被拒、防 fan-out。
- `.venv/bin/python -m pytest tests/`、`ruff check`、`py_compile` 全绿。
- online_retail 数据集补一组跨表问句进 eval_cases，`semantic_eval_runner` 通过。

**风险**：低（纯确定性工程，无模型风险）。是收益最大、最该先做的一项。

---

### P0-2 多候选投票 + 执行反馈（适配 QSQL「输出 draft 不是 SQL」的范式）

**目标**：把单次解析升级为「多候选 + 执行引导」，提升解析稳定性与正确率。

**现状对位**：
- `src/qsql/semantic_agent.py::SemanticQueryAgent.parse` 是一次 `self._agent.run_sync(prompt)`，无投票、无重试。
- `scripts/semantic_eval_runner.py` 已有 `--repeat`，具备观测解析稳定性的基建。

**业界做法**：
- CHASE-SQL（ICLR 2025）：selection agent 显著优于朴素 self-consistency 投票；execution-guided fixer 用语法错误 / 空结果反馈迭代修正（最多 3 次）。
- CSC-SQL：self-consistency + self-correction 融合。
- CHESS：draft SQL → 执行反馈迭代精修。

**落地设计要点（关键：不能照搬，要改造）**：
- **多候选投票投在 draft 层**：对同一问题采样 N 次 `SemanticQueryDraft`，对 `metric_key / group_by_dimension_keys / filters` 做多数投票，取稳定解。
- **执行反馈利用 QSQL 的确定性优势**：`sql_builder` 是确定性的、几乎无语法错，真正的反馈信号是「空结果 / 行数异常」。在 `semantic_service` 拿到执行结果后，空结果时触发一次「换口径 / 换过滤值」的重试或转澄清。
- **守住哲学**：不要把执行错误丢回 LLM 让它改 SQL（等于放开自由生成）；只在 draft 层重采样 / 重选。
- 成本可控：N 默认 3，可配置；temperature 在采样时临时上调，投票后回落。

**改动文件（预估）**：`src/qsql/semantic_agent.py`（多候选采样 + 投票）、`src/qsql/semantic_service.py`（执行反馈钩子）、`src/qsql/schemas.py`（可选：记录候选与投票元信息用于观测）、`tests/`。

**验收标准**：
- 新增测试覆盖：投票选出多数解、候选全不一致时的兜底策略、空结果触发重试 / 澄清。
- `semantic_eval_runner --repeat 5` 下解析一致率指标可统计、较单次有提升。

**风险**：中（增加 LLM 调用成本与延迟）。建议先用 eval 集量化收益再决定默认开启与否。

---

## 五、P1 路线

### P1-1 value retrieval：把已有 BM25 复用为「列值索引」

**目标**：让过滤条件的值能自动对齐到数据库真实值，减少对人工 `semantic_plugins/*.json` 的依赖。

**现状对位**：已有 `src/qsql/chromadb/bm25_jieba.py`、`metadata` 的 value_mapping、`semantic_postprocessor._apply_value_mappings`（目前依赖人工/plugin 配置）。

**业界做法**：BIRD 强调 database content（真实值）匹配对准确率至关重要（如把问句里的词匹配到 `district.a2='Jesenik'`）；CodeS 用 BM25 索引加速 LCS 值匹配。

**落地设计要点**：对维度列的 distinct 值建 BM25 / 向量索引；解析后用问句对值索引检索，自动补全 / 校正 filter value。QSQL 已有 BM25-jieba，复用即可。

**改动文件（预估）**：`src/qsql/metadata_store.py` 或新增值索引构建脚本、`src/qsql/semantic_postprocessor.py`、`tests/`。

**验收标准**：online_retail 上「按某个具体国家/产品过滤」的问句无需人工 plugin 即可命中真实值；新增对应 eval_cases。

### P1-2 评测对齐 BIRD / Spider 风格

**目标**：让 `semantic_eval_runner` 的指标可与业界对齐、更可信。

**现状对位**：`scripts/semantic_eval_runner.py` 已支持 level / category 分层、`expect_metric_key/group_by/filters` 结构化断言、SQLite 真执行、`--repeat`。

**落地设计要点**：
- 补 **EX（结果集等价）判定模式**：与标准答案 SQL 的结果集比对（BIRD / Spider 2.0 主指标即结果集一致，且容忍 SELECT 多余列）。现有断言是结构匹配 + 非空，可作为补充而非替代。
- 难度分级对齐 BIRD 的 simple / moderate / challenging（复用现有 `level`）。
- 可选效率分：参考 BIRD Mini-Dev 的 R-VES（同样正确时奖励更快 SQL），QSQL 已有 stage timing 可接入。

**改动文件（预估）**：`scripts/semantic_eval_runner.py`、`resources/eval_cases/*.jsonl`（补标准答案 SQL / 难度）、`tests/test_semantic_eval_runner.py`。

**验收标准**：runner 能输出 EX、分难度通过率、（可选）效率分；现有测试不回归。

### P1-3 澄清升级：多选题 + 信息增益

**目标**：把开放式澄清升级为更易答、更确定的交互。

**现状对位**：`semantic_service.py` 缺时间范围时返回开放式问题；`semantic_postprocessor._mark_multi_metric_questions` 多指标时也是开放问。

**业界做法**：AmbiSQL 把歧义转成多选题（附 schema / 候选）；Expected Information Gain 维护候选分布、优先问最能减少不确定性的维度。

**落地设计要点**：把「选哪个指标 / 哪个时间口径」渲染成候选选项返回前端；多重歧义时用信息增益决定先问哪个。需扩展澄清响应结构以携带候选项。

**改动文件（预估）**：`src/qsql/schemas.py`（澄清响应带候选）、`src/qsql/semantic_service.py`、`src/qsql/semantic_postprocessor.py`、对应 API 蓝图与 `tests/`。

**验收标准**：多指标 / 缺时间场景返回结构化候选项；eval_cases 中 `expect_status=clarification` 用例覆盖。

---

## 六、P2 路线（小改造、见效快）

- **P2-1 相对时间解析**：`semantic_postprocessor._repair_explicit_year` 仅认「YYYY 年」。补「上季度 / 近 30 天 / 本月 / 同比」等相对时间→具体起止的规则化解析（纯确定性，零模型风险），是中文业务问数高频需求。
- **P2-2 多指标查询**：`_mark_multi_metric_questions` 现在直接转澄清。可在 `sql_builder` 支持同表同粒度下一次 SELECT 多个 metric，减少澄清打断。
- **P2-3 few-shot 示例检索**：用已有 chromadb 存「question → SemanticQueryDraft」成功样例，解析时检索 top-k 注入 prompt（Vanna 的训练样例思路，但存的是 draft 不是 SQL，更安全）。

---

## 七、谨慎 / 暂不做（与受控哲学冲突）

- **LLM 自由生成 SQL、Spider 2.0 式开放 agent**：违背「不让模型直接自由生成最终 SQL」；真实库 SOTA 仅 30–42%，不可靠。
- **RL 微调（CSC-SQL 的 GRPO / Knowledge-to-SQL 的 DPO）**：效果好但工程重、需训练管线与算力，不匹配当前阶段；同类收益可用「多候选投票 + 确定性 builder」拿到大部分。
- **大而全的多 agent 编排（DB-GPT 式）**：QSQL 价值在「窄而可控」，不必为像 agent 而增复杂度。

---

## 八、参考资源

- eosphoros-ai/Awesome-Text2SQL：https://github.com/eosphoros-ai/Awesome-Text2SQL
- dbt MetricFlow join 文档：https://docs.getdbt.com/docs/build/join-logic ｜ 源码：https://github.com/dbt-labs/metricflow
- OSI（Open Semantic Interchange）语义层标准：QSQL catalog schema 可逐步往该标准靠拢，便于未来互通。

### Sources（主要引用，注意厂商数字需谨慎）

- Wren AI vs Vanna 企业对比：https://www.getwren.ai/post/wren-ai-vs-vanna-the-enterprise-guide-to-choosing-a-text-to-sql-solution
- dbt: Semantic Layer vs Text-to-SQL 2026 Benchmark（厂商自测）：https://docs.getdbt.com/blog/semantic-layer-vs-text-to-sql-2026
- dbt MetricFlow 工作原理：https://www.getdbt.com/blog/how-the-dbt-semantic-layer-works
- Spider 2.0（ICLR 2025 Oral）：https://spider2-sql.github.io/ ｜ ReFoRCE：https://arxiv.org/pdf/2502.00675
- CHASE-SQL：https://arxiv.org/abs/2505.13271 ｜ CSC-SQL：https://arxiv.org/html/2505.13271 ｜ MAGIC：https://arxiv.org/pdf/2406.12692
- CodeS（value retrieval / BM25 加速）：https://arxiv.org/pdf/2402.16347 ｜ BIRD Mini-Dev：https://github.com/bird-bench/mini_dev
- AmbiSQL（多选题澄清）：https://www.arxiv.org/pdf/2508.15276 ｜ 信息增益澄清：https://arxiv.org/abs/2507.06467
- 中文数据集梳理（CSpider / DuSQL / Chase / TableQA）：https://www.cnblogs.com/ting1/p/18126496
