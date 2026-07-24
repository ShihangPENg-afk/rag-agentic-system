from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.retrievers.confidence import retrieval_score
from app.retrievers.retriever_v2_hybrid import (
    retrieve_similar_chunks as retrieve_hybrid_chunks,
)
from app.retrievers.retriever_v2_pgvector import (
    retrieve_similar_chunks as retrieve_v1_chunks,
)

DEFAULT_GOLDEN_FILE = ROOT / "evals" / "golden_questions.jsonl"
DEFAULT_V1_OUTPUT = ROOT / "evals" / "results_v1.json"
DEFAULT_V2_OUTPUT = ROOT / "evals" / "results_v2.json"


def _json_default(value: Any) -> str:
    return str(value)


def normalize_text(value: Any) -> str:
    return str(value or "").lower().strip()


def load_golden_questions(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Golden questions file not found: {path}")

    samples: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue

        item = json.loads(line)
        if "question" not in item:
            raise ValueError(f"line {line_number}: missing question")
        if "expected_keywords" not in item or not isinstance(item["expected_keywords"], list):
            raise ValueError(f"line {line_number}: missing expected_keywords list")
        if "expected_doc_id" not in item and "expected_source" not in item:
            raise ValueError(f"line {line_number}: missing expected_doc_id or expected_source")
        samples.append(item)

    if not samples:
        raise ValueError(f"No golden questions found in {path}")
    return samples


def result_source_blob(result: dict[str, Any]) -> str:
    metadata = result.get("source_metadata") or {}
    parts = [
        result.get("chunk_id"),
        result.get("document_id"),
        result.get("collection_id"),
        metadata.get("document_filename"),
        metadata.get("collection_id"),
        metadata.get("collection_name"),
        json.dumps(metadata.get("chunk_metadata") or {}, ensure_ascii=False, default=_json_default),
    ]
    return normalize_text(" ".join(str(part) for part in parts if part is not None))


def result_keyword_blob(results: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for result in results:
        parts.append(str(result.get("content") or ""))
        parts.append(result_source_blob(result))
    return normalize_text("\n".join(parts))


def expected_source_hit(sample: dict[str, Any], results: list[dict[str, Any]]) -> bool | None:
    expected_doc_id = sample.get("expected_doc_id")
    expected_source = sample.get("expected_source")
    if not expected_doc_id and not expected_source:
        return None

    if expected_doc_id:
        expected = str(expected_doc_id)
        if any(str(result.get("document_id")) == expected for result in results):
            return True

    if expected_source:
        expected = normalize_text(expected_source)
        if any(expected in result_source_blob(result) for result in results):
            return True

    return False


def summarize_chunk(result: dict[str, Any], rank: int) -> dict[str, Any]:
    content = str(result.get("content") or "")
    return {
        "rank": rank,
        "chunk_id": result.get("chunk_id"),
        "document_id": result.get("document_id"),
        "collection_id": result.get("collection_id"),
        "score": retrieval_score(result),
        "dense_score": result.get("dense_score"),
        "bm25_score": result.get("bm25_score"),
        "final_score": result.get("final_score"),
        "rerank_score": result.get("rerank_score"),
        "source_metadata": result.get("source_metadata") or {},
        "content_preview": content[:300],
    }


def score_retrieval_case(
    sample: dict[str, Any],
    results: list[dict[str, Any]],
    *,
    top_k: int,
    error: str | None,
) -> dict[str, Any]:
    limited_results = results[:top_k]
    expected_keywords = [str(keyword) for keyword in sample.get("expected_keywords", [])]
    blob = result_keyword_blob(limited_results)
    matched_keywords = [
        keyword for keyword in expected_keywords if normalize_text(keyword) in blob
    ]
    keyword_coverage = (
        len(matched_keywords) / len(expected_keywords) if expected_keywords else 0.0
    )
    source_hit = expected_source_hit(sample, limited_results)

    return {
        "question": sample["question"],
        "expected_keywords": expected_keywords,
        "expected_doc_id": sample.get("expected_doc_id"),
        "expected_source": sample.get("expected_source"),
        f"hit@{top_k}": bool(matched_keywords),
        "matched_keywords": matched_keywords,
        "keyword_coverage": keyword_coverage,
        "source_hit": source_hit,
        "retrieved_count": len(limited_results),
        "error": error,
        "retrieved_chunks": [
            summarize_chunk(result, rank)
            for rank, result in enumerate(limited_results, 1)
        ],
    }


def compute_summary(items: list[dict[str, Any]], *, top_k: int) -> dict[str, Any]:
    total = len(items)
    hit_key = f"hit@{top_k}"
    source_applicable = [item for item in items if item["source_hit"] is not None]
    errors = [item for item in items if item.get("error")]

    return {
        "total": total,
        f"hit_rate@{top_k}": (
            sum(1 for item in items if item[hit_key]) / total if total else 0.0
        ),
        "source_coverage": (
            sum(1 for item in source_applicable if item["source_hit"])
            / len(source_applicable)
            if source_applicable
            else None
        ),
        "avg_keyword_coverage": (
            sum(float(item["keyword_coverage"]) for item in items) / total
            if total
            else 0.0
        ),
        "avg_retrieved_count": (
            sum(int(item["retrieved_count"]) for item in items) / total if total else 0.0
        ),
        "error_count": len(errors),
    }


def call_retriever(
    retriever_version: str,
    sample: dict[str, Any],
    *,
    user_id: str,
    document_id: str | None,
    collection_id: str | None,
    top_k: int,
    use_rerank: bool,
) -> tuple[list[dict[str, Any]], str | None]:
    if retriever_version == "v1":
        return retrieve_v1_chunks(
            query=sample["question"],
            user_id=user_id,
            document_id=document_id,
            collection_id=collection_id,
            limit=top_k,
        )

    if retriever_version == "v2":
        return retrieve_hybrid_chunks(
            query=sample["question"],
            user_id=user_id,
            document_id=document_id,
            collection_id=collection_id,
            top_k=top_k,
            use_rerank=use_rerank,
        )

    raise ValueError(f"Unsupported retriever version: {retriever_version}")


def evaluate_retriever(
    retriever_version: str,
    samples: list[dict[str, Any]],
    *,
    user_id: str,
    document_id: str | None,
    collection_id: str | None,
    top_k: int,
    use_rerank: bool,
    golden_file: Path,
    with_ragas: bool,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for index, sample in enumerate(samples, 1):
        print(f"[{retriever_version}] {index}/{len(samples)} {sample['question']}")
        try:
            results, error = call_retriever(
                retriever_version,
                sample,
                user_id=user_id,
                document_id=document_id,
                collection_id=collection_id,
                top_k=top_k,
                use_rerank=use_rerank,
            )
        except Exception as exc:
            results = []
            error = str(exc)

        items.append(
            score_retrieval_case(
                sample,
                results,
                top_k=top_k,
                error=error,
            )
        )

    summary = compute_summary(items, top_k=top_k)
    summary["ragas"] = maybe_compute_ragas(
        items,
        enabled=with_ragas,
    )

    return {
        "metadata": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "retriever_version": retriever_version,
            "retriever_impl": (
                "app.retrievers.retriever_v2_pgvector.retrieve_similar_chunks"
                if retriever_version == "v1"
                else "app.retrievers.retriever_v2_hybrid.retrieve_similar_chunks"
            ),
            "golden_file": str(golden_file),
            "top_k": top_k,
            "user_id": user_id,
            "document_id": document_id,
            "collection_id": collection_id,
            "use_rerank": use_rerank if retriever_version == "v2" else False,
        },
        "summary": summary,
        "items": items,
    }


def maybe_compute_ragas(items: list[dict[str, Any]], *, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"status": "skipped", "reason": "pass --with-ragas to enable LLM metrics"}

    try:
        from langchain_core.embeddings import Embeddings
        from langchain_openai import ChatOpenAI
        from ragas import EvaluationDataset, SingleTurnSample, evaluate

        try:
            from ragas.metrics.collections import Faithfulness, ResponseRelevancy
        except ImportError:
            from ragas.metrics import Faithfulness, ResponseRelevancy

        from app.core.config import API_KEY, DASHSCOPE_BASE_URL, MODEL_NAME
        from app.services.embedding_service import get_embeddings
    except Exception as exc:
        return {"status": "skipped", "reason": f"RAGAS unavailable: {exc}"}

    if not API_KEY:
        return {"status": "skipped", "reason": "API_KEY is required for RAGAS metrics"}

    class ProjectEmbeddings(Embeddings):
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            embeddings, _dimension = get_embeddings(texts)
            return [list(map(float, item)) for item in embeddings]

        def embed_query(self, text: str) -> list[float]:
            return self.embed_documents([text])[0]

    samples: list[Any] = []
    for item in items:
        contexts = [
            str(chunk.get("content_preview") or "")
            for chunk in item.get("retrieved_chunks", [])
            if str(chunk.get("content_preview") or "").strip()
        ]
        if not contexts:
            continue
        response = "\n".join(contexts[:3])
        samples.append(
            SingleTurnSample(
                user_input=item["question"],
                response=response,
                retrieved_contexts=contexts,
            )
        )

    if not samples:
        return {"status": "skipped", "reason": "no retrieved contexts for RAGAS metrics"}

    try:
        evaluator_llm = ChatOpenAI(
            model=MODEL_NAME,
            api_key=API_KEY,
            base_url=DASHSCOPE_BASE_URL,
            temperature=0,
        )
        result = evaluate(
            dataset=EvaluationDataset(samples=samples),
            metrics=[Faithfulness(), ResponseRelevancy()],
            llm=evaluator_llm,
            embeddings=ProjectEmbeddings(),
            raise_exceptions=False,
            show_progress=False,
        )
        try:
            scores = dict(result)
        except Exception:
            scores = {"raw_result": str(result)}
        return {"status": "ok", "scores": scores}
    except Exception as exc:
        return {"status": "failed", "reason": str(exc)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate v1 baseline and v2 hybrid retrieval on golden questions.",
    )
    parser.add_argument("--golden-file", type=Path, default=DEFAULT_GOLDEN_FILE)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--user-id", default=os.getenv("EVAL_USER_ID"))
    parser.add_argument("--document-id", default=os.getenv("EVAL_DOCUMENT_ID"))
    parser.add_argument("--collection-id", default=os.getenv("EVAL_COLLECTION_ID"))
    parser.add_argument("--v1-output", type=Path, default=DEFAULT_V1_OUTPUT)
    parser.add_argument("--v2-output", type=Path, default=DEFAULT_V2_OUTPUT)
    parser.add_argument("--use-rerank", action="store_true", help="Enable rerank for v2 hybrid retrieval.")
    parser.add_argument("--with-ragas", action="store_true", help="Optionally compute RAGAS LLM metrics.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.user_id:
        raise SystemExit("请通过 --user-id 或 EVAL_USER_ID 指定当前评估用户 ID")
    if args.top_k <= 0:
        raise SystemExit("--top-k must be greater than 0")

    samples = load_golden_questions(args.golden_file)
    v1_result = evaluate_retriever(
        "v1",
        samples,
        user_id=args.user_id,
        document_id=args.document_id,
        collection_id=args.collection_id,
        top_k=args.top_k,
        use_rerank=False,
        golden_file=args.golden_file,
        with_ragas=args.with_ragas,
    )
    v2_result = evaluate_retriever(
        "v2",
        samples,
        user_id=args.user_id,
        document_id=args.document_id,
        collection_id=args.collection_id,
        top_k=args.top_k,
        use_rerank=args.use_rerank,
        golden_file=args.golden_file,
        with_ragas=args.with_ragas,
    )

    args.v1_output.parent.mkdir(parents=True, exist_ok=True)
    args.v2_output.parent.mkdir(parents=True, exist_ok=True)
    args.v1_output.write_text(
        json.dumps(v1_result, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    args.v2_output.write_text(
        json.dumps(v2_result, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )

    print(f"wrote {args.v1_output}")
    print(f"wrote {args.v2_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
