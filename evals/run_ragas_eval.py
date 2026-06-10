from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# 让脚本直接执行时也能导入项目根目录下的 config.py 和 app.*
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langchain_core.embeddings import Embeddings
from langchain_openai import ChatOpenAI
from ragas import EvaluationDataset, SingleTurnSample, evaluate
try:
    from ragas.metrics.collections import Faithfulness, ResponseRelevancy
except ImportError:
    from ragas.metrics import Faithfulness, ResponseRelevancy

from config import API_KEY, DASHSCOPE_BASE_URL, MODEL_NAME
from app.schemas.api_models import QuestionRequest
from app.services.agent_chat_service import chat_with_agent_state
from app.services.index_service import get_embeddings
from app.services.upload_service import create_knowledge_base_from_saved_pdf


def print_banner(title: str) -> None:
    width = 72
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def resolve_pdf_path(raw: str) -> Path:
    path = Path(raw).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"PDF 文件不存在: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"仅支持 .pdf 文件: {path}")
    return path


def assert_pdf_magic(path: Path) -> None:
    with path.open("rb") as f:
        header = f.read(5)
    if len(header) < 4 or not header.startswith(b"%PDF"):
        raise ValueError(f"文件内容与 PDF 格式不符: {path}")


def load_samples(path: Path) -> List[Dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("评估样本文件必须是非空 JSON 数组")
    for item in data:
        if "question" not in item or "reference" not in item:
            raise ValueError("每条评估样本都必须包含 question 和 reference")
    return data


def unique_keep_order(items: List[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        if text not in seen:
            seen.add(text)
            result.append(text)
    return result


def collect_contexts(debug_payload: Dict[str, Any]) -> List[str]:
    contexts: List[str] = []

    reasoning = debug_payload.get("reasoning_snapshot", {}) or {}
    evidence_by_sub_query = reasoning.get("evidence_by_sub_query", {}) or {}

    for evidences in evidence_by_sub_query.values():
        if isinstance(evidences, list):
            contexts.extend([str(x) for x in evidences if str(x).strip()])

    if not contexts:
        preview = debug_payload.get("retrieved_evidence_preview", []) or []
        contexts.extend([str(x) for x in preview if str(x).strip()])

    return unique_keep_order(contexts)


class DashScopeEmbeddingsAdapter(Embeddings):
    """
    把项目现有的 DashScope 向量逻辑适配成 LangChain Embeddings。
    这样 RAGAS 的 ResponseRelevancy 就能直接复用现有向量能力。
    """

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        last_error: Exception | None = None
        max_attempts = 3

        for attempt in range(max_attempts):
            try:
                embeddings, _ = get_embeddings(texts)
                if len(embeddings) != len(texts):
                    raise RuntimeError(
                        f"向量数量与输入文本数量不一致: {len(embeddings)} != {len(texts)}"
                    )
                return [list(map(float, emb)) for emb in embeddings]
            except Exception as exc:
                last_error = exc
                if attempt < max_attempts - 1:
                    time.sleep(attempt + 1)

        assert last_error is not None
        raise last_error

    def embed_query(self, text: str) -> List[float]:
        result = self.embed_documents([text])
        return result[0]


def safe_result_to_dict(result: Any) -> Dict[str, Any]:
    try:
        return {k: float(v) for k, v in dict(result).items()}
    except Exception:
        pass

    if hasattr(result, "model_dump"):
        try:
            dumped = result.model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass

    return {"raw_result": str(result)}


def build_metrics(choice: str) -> List[Any]:
    if choice == "relevancy":
        return [ResponseRelevancy()]
    if choice == "faithfulness":
        return [Faithfulness()]
    if choice == "all":
        return [Faithfulness(), ResponseRelevancy()]
    raise ValueError(f"不支持的指标选项: {choice}")


def metric_display_name(metric: Any) -> str:
    return getattr(metric, "name", metric.__class__.__name__)

def _extract_single_metric_score(result: Any, metric_name: str) -> float | None:
    """
    从 RAGAS evaluate 返回结果中取出单个指标分数。
    兼容 dict-like、model_dump、raw_result 字符串三种情况。
    """
    try:
        data = dict(result)
        value = data.get(metric_name)
        if value is not None:
            return float(value)
    except Exception:
        pass

    if hasattr(result, "model_dump"):
        try:
            dumped = result.model_dump()
            if isinstance(dumped, dict):
                value = dumped.get(metric_name)
                if value is not None:
                    return float(value)
        except Exception:
            pass

    try:
        text = str(result)
        marker = f"'{metric_name}':"
        if marker in text:
            tail = text.split(marker, 1)[1].strip()
            raw = tail.split(",", 1)[0].split("}", 1)[0].strip()
            return float(raw)
    except Exception:
        pass

    return None


def evaluate_faithfulness_serially(
    ragas_samples: List[SingleTurnSample],
    evaluator_llm: ChatOpenAI,
    evaluator_embeddings: Embeddings,
) -> Dict[str, Any]:
    """
    对 faithfulness 采用逐条串行评估，避免多样本并发导致的大量超时。
    返回统一 summary 结构，便于后续写入报告。
    """
    scores: List[float] = []
    failures: List[Dict[str, Any]] = []

    for i, sample in enumerate(ragas_samples, 1):
        print(f"[faithfulness serial] {i}/{len(ragas_samples)}")
        try:
            dataset = EvaluationDataset(samples=[sample])
            result = evaluate(
                dataset=dataset,
                metrics=[Faithfulness()],
                llm=evaluator_llm,
                embeddings=evaluator_embeddings,
                raise_exceptions=False,
                show_progress=False,
            )
            score = _extract_single_metric_score(result, "faithfulness")
            if score is not None:
                scores.append(score)
            else:
                failures.append(
                    {
                        "index": i - 1,
                        "reason": "未能从 evaluate 结果中解析出 faithfulness 分数",
                    }
                )
        except Exception as exc:
            failures.append(
                {
                    "index": i - 1,
                    "reason": str(exc),
                }
            )

    summary: Dict[str, Any] = {
        "faithfulness": round(sum(scores) / len(scores), 4) if scores else None,
        "faithfulness_success_count": len(scores),
        "faithfulness_failure_count": len(failures),
    }
    if failures:
        summary["faithfulness_failures"] = failures

    return summary

def main() -> int:
    parser = argparse.ArgumentParser(description="运行 RAGAS 评估")
    parser.add_argument("--pdf", default="test.pdf", help="用于构建知识库的 PDF 文件")
    parser.add_argument("--samples", default="evals/ragas_samples.json", help="评估样本 JSON")
    parser.add_argument("--out-dir", default="evals/out", help="评估输出目录")
    parser.add_argument("--limit", type=int, default=3, help="本次最多评估多少条样本")
    parser.add_argument("--eval-timeout", type=int, default=600, help="评估模型请求超时时间（秒）")
    parser.add_argument(
        "--metrics",
        choices=["relevancy", "faithfulness", "all"],
        default="relevancy",
        help="RAGAS 评估指标：relevancy / faithfulness / all",
    )
    args = parser.parse_args()

    pdf_path = resolve_pdf_path(args.pdf)
    assert_pdf_magic(pdf_path)

    sample_path = Path(args.samples).expanduser().resolve()
    if not sample_path.is_file():
        raise FileNotFoundError(f"评估样本文件不存在: {sample_path}")

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print_banner("步骤 1 / 构建知识库")
    kb_result = create_knowledge_base_from_saved_pdf(str(pdf_path), pdf_path.name)
    kb_id = kb_result["knowledge_base_id"]
    print(f"knowledge_base_id: {kb_id}")
    print(f"chunks_count:      {kb_result['chunks_count']}")

    print_banner("步骤 2 / 加载评估样本")
    specs = load_samples(sample_path)
    if args.limit > 0:
        specs = specs[: args.limit]
    print(f"本次评估样本数: {len(specs)}")

    print_banner("步骤 3 / 逐条运行 Agent")
    ragas_samples: List[SingleTurnSample] = []
    run_records: List[Dict[str, Any]] = []

    for i, item in enumerate(specs, 1):
        question = item["question"]
        reference = item["reference"]

        req = QuestionRequest(
            question=question,
            knowledge_base_id=kb_id,
            history=[],
            debug=True,
        )
        result = chat_with_agent_state(req)
        answer = result["answer"]
        debug_payload = result.get("debug", {}) or {}
        contexts = collect_contexts(debug_payload)

        ragas_samples.append(
            SingleTurnSample(
                user_input=question,
                response=answer,
                retrieved_contexts=contexts,
                reference=reference,
            )
        )

        run_records.append(
            {
                "question": question,
                "reference": reference,
                "answer": answer,
                "retrieved_contexts_count": len(contexts),
            }
        )

        print(f"[{i}/{len(specs)}] 完成: {question}")

    print_banner("步骤 4 / 运行 RAGAS")
    dataset = EvaluationDataset(samples=ragas_samples)

    evaluator_llm = ChatOpenAI(
        model=MODEL_NAME,
        api_key=API_KEY,
        base_url=DASHSCOPE_BASE_URL,
        temperature=0,
        request_timeout=args.eval_timeout,
        max_retries=2,
    )
    evaluator_embeddings = DashScopeEmbeddingsAdapter()

    metrics = build_metrics(args.metrics)
    metric_names = [metric_display_name(m) for m in metrics]
    print(f"当前运行指标: {', '.join(metric_names)}")

    # faithfulness 单独走串行模式，降低超时概率
    if args.metrics == "faithfulness":
        print("启用 faithfulness 串行评估模式（逐条样本依次打分）")
        summary = evaluate_faithfulness_serially(
            ragas_samples=ragas_samples,
            evaluator_llm=evaluator_llm,
            evaluator_embeddings=evaluator_embeddings,
        )
    else:
        eval_result = evaluate(
            dataset=dataset,
            metrics=metrics,
            llm=evaluator_llm,
            embeddings=evaluator_embeddings,
            raise_exceptions=False,
            show_progress=True,
        )
        summary = safe_result_to_dict(eval_result)

    print_banner("步骤 5 / 保存报告")
    json_path = out_dir / "ragas_report.json"
    md_path = out_dir / "ragas_report.md"

    report = {
        "summary": summary,
        "samples": run_records,
        "pdf": str(pdf_path),
        "sample_file": str(sample_path),
        "eval_config": {
            "limit": len(specs),
            "metrics": args.metrics,
            "eval_timeout": args.eval_timeout,
        },
        "note": (
            "评估可能包含部分超时任务；当前结果适合作为阶段性基线。"
            "当 metrics=faithfulness 时，脚本会自动启用逐条串行评估模式，以降低多样本并发超时概率。"
),
    }

    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    md_lines = [
        "# RAGAS Evaluation Report",
        "",
        f"- PDF: `{pdf_path.name}`",
        f"- 样本数: {len(specs)}",
        "",
        "## Summary",
        "",
    ]
    for k, v in summary.items():
        md_lines.append(f"- {k}: {v}")

    md_lines.append("")
    md_lines.append("## Samples")
    md_lines.append("")
    for item in run_records:
        md_lines.append(f"### Q: {item['question']}")
        md_lines.append(f"- retrieved_contexts_count: {item['retrieved_contexts_count']}")
        md_lines.append(f"- reference: {item['reference']}")
        md_lines.append(f"- answer: {item['answer']}")
        md_lines.append("")

    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    print("✅ 评估完成")
    print(f"JSON 报告: {json_path}")
    print(f"Markdown 报告: {md_path}")

    print_banner("最终摘要")
    for k, v in summary.items():
        print(f"{k}: {v}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
