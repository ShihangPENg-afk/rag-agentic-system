# RAGAS 评估基线报告

> 评估日期：2026-06-10  
> 完整可复现命令见 [README.md](../README.md#ragas-评估结果)  
> 运行时输出目录：`evals/out/`（本地生成，未纳入 Git）

---

## 运行配置

| 项 | 值 |
|----|-----|
| PDF | `test.pdf`（83 chunks / 83 vectors） |
| 样本文件 | `evals/ragas_samples.json`（共 10 条，本次取前 3 条） |
| `RAGAS_LIMIT` | 3 |
| `RAGAS_METRICS` | all（faithfulness + answer_relevancy） |
| `RAGAS_TIMEOUT` | 600 |
| Agent 完成 | 3/3 |
| RAGAS Job | 6/6 无超时 |

---

## Summary

| 指标 | 分数 |
|------|------|
| **faithfulness** | **0.8750** |
| **answer_relevancy** | **0.8858** |

> 说明：结果为 DashScope `qwen-plus` 在线 API 下的 Agent 问答基线；LoRA 微调模型**尚未接入**本仓库。

---

## Samples

### Q: 这份文档主要讲什么？

- **reference:** 文档主要围绕软件工程概述展开，介绍软件的概念、分类、特性，以及软件工程的基本定义、目标和生命周期等基础内容。
- **answer:** 这份文档主要介绍软件工程的基础概念，重点阐述了软件的定义、组成要素（程序、数据、文档）及其核心特性（如无形性、可复用性、无磨损性等），并初步涉及软件的分类（如系统软件、支撑软件等）。内容出自《软件工程课本》第1章「软件工程概述」，属于软件工程学科的入门性概述。
- **retrieved_contexts_count:** 1

### Q: 文档中如何定义软件？

- **reference:** 软件被定义为程序、数据及其相关文档的完整集合。
- **answer:** 文档中将软件定义为：**计算机系统中与硬件相互依存的另一部分，是包括程序、数据及其相关文档的完整集合**。其中程序、数据、文档三要素均有展开说明，并补充了无形性、可复用性等特性。
- **retrieved_contexts_count:** 1

### Q: 软件通常由哪三个要素构成？

- **reference:** 软件通常由程序、数据和文档三个要素构成。
- **answer:** 软件通常由以下三个要素构成：**程序、数据和文档**，并分别给出定义。
- **retrieved_contexts_count:** 1

---

## 复现命令

```bash
make eval-ragas RAGAS_LIMIT=3 RAGAS_METRICS=all RAGAS_TIMEOUT=600
```

或：

```bash
python evals/run_ragas_eval.py \
  --pdf test.pdf \
  --samples evals/ragas_samples.json \
  --limit 3 \
  --metrics all \
  --eval-timeout 600
```

生成文件：`evals/out/ragas_report.json`、`evals/out/ragas_report.md`。
