# RAG Retrieval Evaluation Report: v1 vs v2

## 1. 项目背景

本项目是面向工业设备运维场景的 RAG + LangGraph Agent 系统，核心目标是让用户能够基于上传的设备维护手册、报警说明、点检记录或维修建议文档进行问答。典型问题包括设备故障原因、报警排查、维护步骤、零件检查和维修建议。

检索质量会直接影响最终回答质量：如果召回不到正确片段，后续生成模型即使表达流畅，也可能缺少可靠依据。因此本评估重点关注检索阶段，而不是只看最终回答文本。

## 2. v1 检索方式

v1 使用当前 baseline 检索路径：

- 主实现：`app.retrievers.retriever_v2_pgvector.retrieve_similar_chunks`
- 检索方式：pgvector dense retrieval
- 查询流程：将用户问题向量化后，在 `chunk_embeddings` 中按向量距离检索相似 chunk
- 支持过滤：`user_id`、`document_id`、`collection_id`
- 输出字段：`chunk_id`、`document_id`、`collection_id`、`score`、`distance`、`content`

v1 的优势是结构简单，适合语义相似问题；局限是对具体报警词、零件名、故障代码、手册章节关键词的精确匹配不一定稳定。

## 3. v2 检索方式

v2 使用 hybrid retrieval：

- 主实现：`app.retrievers.retriever_v2_hybrid.retrieve_similar_chunks`
- dense retrieval：复用 pgvector 进行语义相似度检索
- BM25 retrieval：对 chunk 文本做关键词匹配
- 融合方式：默认 RRF，也支持 weighted fusion
- 可选 rerank：通过 `use_rerank=true` 对融合后的候选结果进行二次排序
- 输出字段：`chunk_id`、`document_id`、`collection_id`、`content`、`dense_score`、`bm25_score`、`final_score`、`rerank_score`、`source_metadata`

v2 的设计目标不是替代 dense retrieval，而是补齐关键词匹配能力，尤其适合工业运维中常见的“报警原因”“零件检查”“维护手册步骤”等问题。

## 4. Golden Set 构建方式

golden set 文件为 `evals/golden_questions.jsonl`，共 30 条问题。

构建原则：

- 问题围绕通用工业设备运维场景
- 覆盖设备故障、维护手册、报警原因、维修建议、零件检查
- 不引入过于复杂或无法验证的工业细节
- 每条样本包含：
  - `question`
  - `expected_keywords`
  - `expected_source`

示例：

```json
{
  "question": "设备报警提示振动过高，常见原因有哪些？",
  "expected_keywords": ["振动过高", "轴承", "不平衡", "松动", "对中", "基础"],
  "expected_source": "alarm_reference"
}
```

当前 golden set 更适合作为检索评估集，而不是最终答案质量评估集。它主要检查召回片段中是否覆盖预期关键词和来源线索。

## 5. hit_rate@k 对比

评估脚本为 `evals/evaluate_retrieval.py`，默认输出：

- `evals/results_v1.json`
- `evals/results_v2.json`

截至本报告生成时，未发现上述两个结果文件，因此没有可验证的 hit_rate@k 数值。下面表格只记录当前评估状态，不写无法验证的提升比例。

| 指标 | v1 | v2 | 说明 |
|---|---:|---:|---|
| hit_rate@k | 未生成 | 未生成 | 需要先运行 `evals/evaluate_retrieval.py` |
| avg_keyword_coverage | 未生成 | 未生成 | 需要读取 `results_v1.json` / `results_v2.json` |

推荐运行方式：

```bash
EVAL_USER_ID=<user_id> python3 evals/evaluate_retrieval.py --top-k 5
```

如果需要限定集合或文档：

```bash
EVAL_USER_ID=<user_id> python3 evals/evaluate_retrieval.py \
  --collection-id <collection_id> \
  --document-id <document_id> \
  --top-k 5
```

如果需要评估 v2 rerank：

```bash
EVAL_USER_ID=<user_id> python3 evals/evaluate_retrieval.py \
  --collection-id <collection_id> \
  --top-k 5 \
  --use-rerank
```

## 6. source_coverage 对比

`source_coverage` 用于衡量召回结果是否命中 golden set 中的 `expected_source` 或 `expected_doc_id`。

截至本报告生成时，未发现 `results_v1.json` 和 `results_v2.json`，因此没有可验证的 source_coverage 数值。

| 指标 | v1 | v2 | 说明 |
|---|---:|---:|---|
| source_coverage | 未生成 | 未生成 | 当前缺少实际评估结果文件 |

需要注意：当前 golden set 使用的是通用 `expected_source`，例如 `alarm_troubleshooting_guide`、`fault_troubleshooting_guide`。如果真实文档 metadata 中没有这些 source 名称，source_coverage 可能偏低。这不一定代表检索失败，也可能代表 source 标注和真实文档元数据尚未对齐。

## 7. Rerank 的作用

rerank 是二阶段排序，不负责生成新证据。

当前实现：

- 文件：`app.retrievers.rerank.RerankerService`
- 配置：`RERANK_PROVIDER`
- 默认 provider：`mock`
- 输入：`query + candidate_chunks`
- 输出：重新排序后的 chunks，并保留 `rerank_score`

在 v2 hybrid retrieval 中，rerank 的位置是：

1. BM25 召回关键词相关候选
2. pgvector 召回语义相关候选
3. RRF 或 weighted fusion 合并候选
4. rerank 对融合候选进行二次排序
5. 返回最终 top_k

mock reranker 主要用于测试链路是否完整。它基于 query 与 chunk content 的词面重合度打分，并不等价于真实 cross-encoder 或商业 rerank 模型。因此在报告中不能把 mock rerank 的结果当成真实模型收益。

## 8. 当前局限

当前评估和实现仍有以下局限：

- 尚未生成 `results_v1.json` 和 `results_v2.json`，因此本报告不包含实际数值对比。
- golden set 是通用运维问题，未绑定真实上传文档的具体 `document_id`。
- `expected_source` 是逻辑来源标签，可能与真实文档 metadata 不完全一致。
- hit_rate@k 当前基于关键词覆盖，不能完全代表答案正确性。
- source_coverage 依赖文档来源 metadata 的质量。
- mock reranker 只适合测试，不代表真实 rerank 模型效果。
- RAGAS 指标是可选项，需要 LLM 和 embedding 服务可用；当前报告未包含可验证的 faithfulness 或 answer_relevancy 结果。
- v1 和 v2 的差异应通过同一批文档、同一用户权限、同一 top_k 下的结果文件来判断。

## 9. 面试时可以如何解释这部分

可以这样解释：

> 我把检索评估拆成两层。第一层是不依赖 LLM 的检索指标，用 golden questions 检查 hit_rate@k、关键词覆盖和 source coverage；第二层是可选的 RAGAS，用于在有模型服务时评估 faithfulness 和 answer relevancy。

介绍 v1 和 v2 时可以说：

> v1 是 pgvector dense retrieval baseline，适合语义相似问题。v2 是 hybrid retrieval，把 BM25 的关键词匹配和 pgvector 的语义检索结合起来，再用 RRF 或 weighted fusion 排序。工业运维里很多问题包含报警名、零件名和维护动作，纯 dense retrieval 可能漏掉关键词强相关片段，所以我加入 BM25 来补召回。

介绍 rerank 时可以说：

> rerank 是二阶段排序，只调整候选顺序，不创造新证据。当前 mock reranker 主要用于保证接口和评估流程可测试；如果接入真实 rerank 模型，可以替换 `RERANK_PROVIDER`，评估脚本仍然复用同一套 golden set。

介绍结果时应保持克制：

> 当前不能直接声称 v2 提升了多少，因为需要先在同一批真实文档上生成 `results_v1.json` 和 `results_v2.json`。我会用 hit_rate@k 和 source_coverage 做可复现对比，只在结果文件存在时报告实际数字。

可以强调工程价值：

> 这部分的价值不只是某个分数，而是建立了可重复的检索评估闭环：固定 golden set、固定 top_k、同时跑 v1/v2、输出结构化 JSON，再写对比报告。这样以后改 chunking、embedding、BM25、fusion 或 rerank 时，都可以用同一套脚本做回归评估。
