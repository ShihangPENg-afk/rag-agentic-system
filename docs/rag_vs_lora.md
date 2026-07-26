# RAG 与 LoRA 在工业设备运维项目中的分工

> 关联项目：`rag-agentic-system`、`llm-finetune-for-manufacturing`、`predictive-maintenance-mini`  
> 当前状态：主系统仍使用 DashScope `qwen-plus` 生成答案；LoRA adapter 尚未接入主系统。

本文档用于解释：为什么这个项目同时出现 RAG、Agent、LoRA 微调和工业预测服务；它们各自解决什么问题，以及哪些部分只是流程验证，不能夸大成生产效果。

---

## 1. RAG 适合什么场景

RAG 更适合“答案依赖外部知识，且知识经常变化”的场景。

典型例子：

- 设备维护手册、SOP、报警码说明、备件清单等文档问答
- 需要引用具体文档片段、页码、标题或来源的回答
- 企业知识库更新频繁，不希望每次文档变化都重新训练模型
- 希望降低幻觉，让模型先检索证据，再基于证据组织回答
- 多租户或多用户文档隔离场景，不希望把所有私有文档混入模型权重

在这个项目里，RAG 的价值不是“让模型真的学会所有手册”，而是把手册内容切块、向量化、检索出来，再交给 LLM 生成更像人能读懂的回答。它的强项是可更新、可追溯、可替换。

---

## 2. LoRA 微调适合什么场景

LoRA 更适合“想调整模型回答风格、任务格式或领域表达习惯”的场景。

典型例子：

- 固定格式输出：例如维护建议必须包含风险、原因、步骤、注意事项
- 领域语言习惯：例如工业运维中常见的报警、点检、复核、停机、备件表达
- 指令遵循优化：让模型更稳定地按照内部模板回答
- 少量参数高效训练：只训练 adapter，不改动完整基座模型
- 在受控数据集上做专项能力对齐，而不是把所有知识硬塞进模型

LoRA 不适合替代知识库。设备手册、报警码、工艺参数这类内容如果经常变化，用 RAG 管理更合适。LoRA 更适合让模型“说得更像这个领域的人”，而不是承担全部事实存储。

---

## 3. 在工业设备运维项目中，RAG 负责什么

在 `rag-agentic-system` 中，RAG 主要负责“查资料”和“给回答提供依据”。

当前主系统的 RAG 职责包括：

- 上传 PDF 技术手册
- 抽取文本并切块
- 调用 embedding provider 生成向量
- 使用 FAISS / pgvector 检索相关片段
- 将检索结果作为上下文交给 Agent 或问答链路
- 在回答里保留 sources、confidence、debug trace 等可观察信息

换句话说，RAG 负责把“当前问题可能需要的文档证据”找出来。它不是模型训练，也不改变 LLM 权重。

---

## 4. LoRA 负责什么

在这个项目体系里，LoRA 的合理职责是增强生成模型在工业运维任务上的表达和指令遵循能力。

后续如果接入 LoRA，它更适合负责：

- 把检索到的手册片段整理成稳定的维护建议
- 按固定结构输出：现象、可能原因、检查步骤、风险提示、下一步动作
- 对工业运维常见术语更敏感
- 减少回答风格漂移，让输出更贴近维护工程师的工作语言
- 在 RAG 已给出证据的前提下，更好地总结和组织答案

当前 `llm-finetune-for-manufacturing` 已经跑通 CPU 下的 LoRA 流程验证，但这不等于已经得到可上线的领域模型。它目前更像是“训练管线可跑通”的证明。

---

## 5. 为什么不直接微调整个模型

直接全参数微调整个大模型成本高、风险也高。

主要原因：

- 资源成本高：全量微调 7B 级别模型通常需要较大显存和更完整的训练环境
- 数据要求高：少量 PDF 转换样本不足以支撑全参数微调，容易过拟合
- 维护成本高：手册更新后重新训练完整模型不现实
- 可控性较差：知识写进权重后，很难判断某个回答到底来自哪里
- 合规与部署压力大：完整模型权重管理、推理服务、评估回归都更重

相比之下，RAG 负责动态知识，LoRA 只调轻量 adapter，是更现实的组合。对这个项目来说，全量微调不是当前阶段最划算的路线。

---

## 6. 为什么当前 CPU 环境只做流程验证

当前 CPU 环境能跑通 LoRA 微调流程，但不适合做正式训练结论。

原因很直接：

- CPU 训练速度慢，只能用很小的数据量和很少 epoch
- batch size、sequence length、样本规模都会被限制
- 很难进行系统性的超参搜索和多轮对照实验
- 训练 loss 下降不代表实际问答效果提升
- 没有足够 GPU 资源时，before / after 评估覆盖面会很有限

所以当前 CPU 版本应该被描述为：

> 已完成 PDF 到 Alpaca 数据集、LoRA 配置、训练脚本、adapter 输出的端到端流程验证。

不应该描述为：

> 已训练出高质量工业运维大模型。

这个边界很重要，面试或项目答辩时也要说清楚。

---

## 7. 如果有 GPU，后续如何正式训练

如果后续有 GPU，正式训练可以按以下步骤推进：

1. 扩充数据集  
   从更多设备手册、报警案例、点检记录中构造高质量 instruction 数据，覆盖问答、总结、步骤生成、故障排查、格式化输出等任务。

2. 划分 train / validation / test  
   不要只看训练 loss。至少保留一批未参与训练的问题，用来做微调前后对比。

3. 选择基座模型和训练配置  
   例如 Qwen 系列 instruct 模型，加 LoRA / QLoRA；根据显存选择 batch size、sequence length、rank、learning rate。

4. 做小规模试训  
   先确认数据格式、loss 曲线、输出样例没有明显问题，再扩大训练。

5. 做 before / after 评估  
   对同一批问题比较原模型、RAG + 原模型、RAG + LoRA 模型的效果。指标可以包括人工评分、格式遵循率、引用一致性、RAGAS 指标等。

6. 做失败案例分析  
   记录哪些问题变好了，哪些没有变，哪些反而变差。工业项目里这比单个平均分更有价值。

7. 固化推理服务  
   用 vLLM、TGI、Ollama 或其他 OpenAI-compatible 服务加载基座模型 + LoRA adapter，对外提供稳定 HTTP 接口。

---

## 8. 如何把 LoRA 模型作为 local provider 接入主系统

主系统当前通过 OpenAI-compatible 接口调用 DashScope。后续接入本地 LoRA 模型，可以沿用类似 provider 思路，不必重写 Agent。

推荐路径：

1. 启动本地推理服务  
   用支持 OpenAI-compatible API 的推理框架加载基座模型和 LoRA adapter，例如本地服务暴露：

   ```text
   http://127.0.0.1:8001/v1
   ```

2. 增加 LLM provider 配置  
   可以在 `.env` 中增加类似配置：

   ```env
   LLM_PROVIDER=local
   LOCAL_LLM_BASE_URL=http://127.0.0.1:8001/v1
   LOCAL_LLM_API_KEY=not-needed
   LOCAL_LLM_MODEL=qwen2-7b-lora-maintenance
   ```

3. 抽象生成模型客户端  
   将当前直接读取 `DASHSCOPE_BASE_URL`、`DASHSCOPE_API_KEY`、`MODEL_NAME` 的位置封装成 `get_chat_model()` 或 `LLMProvider`：

   ```text
   LLM_PROVIDER=dashscope -> DashScope OpenAI-compatible endpoint
   LLM_PROVIDER=local     -> local OpenAI-compatible endpoint
   LLM_PROVIDER=fake      -> tests / offline mock
   ```

4. Agent answer 节点切换 provider  
   Agent graph、tool、RAG 检索逻辑不需要大改，只把最终生成节点使用的 chat model 换成本地 provider。

5. 保留回退能力  
   本地 LoRA 服务不可用时，可以回退到 DashScope 或返回明确错误，避免整个主服务不可用。

6. 重新跑评估  
   接入后必须重新跑 smoke test、RAGAS、人工样例对比。不能只因为 LoRA 接入成功就认为效果提升。

接入后的目标架构可以是：

```text
PDF / RAG 检索
      ↓
Agent 编排
      ↓
LLMProvider
  ├─ dashscope provider
  ├─ local LoRA provider
  └─ fake provider for tests
```

---

## 9. 面试时如何回答“你这个微调有没有实际效果”

可以真实地回答，不要硬夸。

推荐回答：

> 当前阶段我没有把 LoRA 描述成已经带来可验证的线上效果变化。这个仓库里的主系统仍然使用 RAG + DashScope 生成，LoRA 是在独立仓库里完成的流程验证：包括 PDF 数据转换、Alpaca 数据构造、LoRA 配置、训练和 adapter 输出。<br>
>
> 所以我能证明的是“微调管线跑通了”，而不是“微调模型已经优于原模型”。如果要证明实际效果，需要在 GPU 环境下扩大数据集，并做严格的 before / after 对照评估，比如比较原模型、RAG + 原模型、RAG + LoRA 在同一批工业运维问题上的格式遵循、事实一致性和人工评分。

如果面试官继续追问“那这个 LoRA 的价值在哪里”，可以补充：

> 它的价值在于我已经把后续训练链路打通了。当前主系统用 RAG 保证知识可追溯，LoRA 后续可以用来优化回答格式和领域表达。这个组合比单纯把手册背进模型权重更可维护，也更符合企业知识经常更新的场景。

如果面试官问“为什么不直接说提升了”，可以回答：

> 因为没有足够 GPU 训练和完整评估之前，说提升是不严谨的。我更愿意把当前结果说成工程流程验证，后续用实验数据证明效果。

这类回答更可信，也更符合当前项目真实状态。
