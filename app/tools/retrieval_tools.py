"""
检索工具：仅返回相关文本片段，不生成最终答案。
"""
from typing import List, Optional, Tuple

from app.services.chat_service import (
    enhance_query_with_history,
    normalize_history,
    retrieve_relevant_chunks,
)
from app.retrievers.retriever_v2_hybrid import (
    retrieve_similar_chunks as retrieve_hybrid_chunks,
)
from app.retrievers.confidence import (
    LOW_CONFIDENCE_ANSWER,
    calculate_confidence,
    is_low_confidence,
)
from app.retrievers.retriever_v2_pgvector import (
    list_persisted_chunks_for_document,
    retrieve_similar_chunks,
)
from app.services.kb_registry import get_knowledge_base
from app.tools.common import kb_not_found_message

def format_retrieved_chunks(
    chunks: List[str],
    title: str = "检索结果",
    preview_length: int | None = None,
) -> str:
    """
    把检索结果格式化成统一文本，便于后续直接给大模型或调试输出。
    如果 preview_length 不为 None，则只展示每个片段的前若干字符。
    """
    if not chunks:
        return f"## {title}\n未检索到相关片段。"

    lines = [f"## {title}"]
    for i, chunk in enumerate(chunks, 1):
        text = str(chunk).replace("\u3000", " ").strip()
        text = " ".join(text.split())

        if preview_length is not None and preview_length > 0:
            text = text[:preview_length] + ("..." if len(text) > preview_length else "")

        lines.append(f"{i}. {text}")

    return "\n".join(lines)


def format_retrieved_chunk_results(
    results: list[dict],
    title: str = "检索结果",
    preview_length: int | None = None,
) -> str:
    if not results:
        return f"## {title}\n未检索到相关片段。"

    lines = [f"## {title}"]
    for i, item in enumerate(results, 1):
        text = str(item["content"]).replace("\u3000", " ").strip()
        text = " ".join(text.split())
        if preview_length is not None and preview_length > 0:
            text = text[:preview_length] + ("..." if len(text) > preview_length else "")

        score = float(item.get("final_score", item.get("score", 0.0)) or 0.0)
        score_parts = [f"score={score:.4f}"]
        if item.get("dense_score") is not None:
            score_parts.append(f"dense_score={float(item['dense_score']):.4f}")
        if item.get("bm25_score") is not None:
            score_parts.append(f"bm25_score={float(item['bm25_score']):.4f}")
        if item.get("rerank_score") is not None:
            score_parts.append(f"rerank_score={float(item['rerank_score']):.4f}")

        source_metadata = item.get("source_metadata") or {}
        source_parts = []
        if source_metadata.get("document_filename"):
            source_parts.append(f"document_filename={source_metadata['document_filename']}")
        if source_metadata.get("collection_name"):
            source_parts.append(f"collection_name={source_metadata['collection_name']}")
        if source_metadata.get("chunk_index") is not None:
            source_parts.append(f"chunk_index={source_metadata['chunk_index']}")
        retrieval_sources = source_metadata.get("retrieval_sources") or {}
        if retrieval_sources:
            source_parts.append(f"retrieval_sources={','.join(retrieval_sources.keys())}")

        lines.append(
            f"{i}. chunk_id={item['chunk_id']} "
            f"document_id={item['document_id']} "
            f"{' '.join(score_parts)}"
            + (f"\nsource_metadata: {'; '.join(source_parts)}" if source_parts else "")
            + f"\n{text}"
        )

    return "\n".join(lines)


def retrieve_chunks_tool(
    knowledge_base_id: str,
    user_query: str,
    user_id: str | None = None,
    collection_id: str | None = None,
    retriever_version: str = "v1",
    history: Optional[List[Tuple[str, str]]] = None,
    max_history: int = 3,
    limit: int = 3,
    use_rerank: bool = False,
) -> str:
    """
    根据用户问题检索知识库中的相关文本片段（不调用大模型生成答案）。
    """
    valid_turns = normalize_history(history, max_history=max_history)
    enhanced_query = enhance_query_with_history(user_query, valid_turns)

    normalized_version = (retriever_version or "v1").lower()
    if normalized_version == "v2":
        results, error = retrieve_hybrid_chunks(
            query=enhanced_query,
            user_id=user_id,
            document_id=knowledge_base_id,
            collection_id=collection_id,
            top_k=limit,
            use_rerank=use_rerank,
        )
        if error is None:
            if is_low_confidence(calculate_confidence(results)):
                return LOW_CONFIDENCE_ANSWER
            return format_retrieved_chunk_results(
                results,
                title="检索到的相关片段",
            )
        if not error.startswith("⚠️ hybrid 检索服务异常"):
            return error

    results, error = retrieve_similar_chunks(
        query=enhanced_query,
        user_id=user_id,
        document_id=knowledge_base_id,
        collection_id=collection_id,
        limit=limit,
    )
    if error is None:
        if is_low_confidence(calculate_confidence(results)):
            return LOW_CONFIDENCE_ANSWER
        return format_retrieved_chunk_results(results, title="检索到的相关片段")
    if not error.startswith("⚠️ pgvector 检索服务异常"):
        return error

    rag = get_knowledge_base(knowledge_base_id)
    if rag is None:
        return kb_not_found_message(knowledge_base_id)

    relevant_texts, error = retrieve_relevant_chunks(
        rag.index, rag.chunks, enhanced_query
    )

    if error:
        return error

    if limit > 0:
        relevant_texts = relevant_texts[:limit]

    return format_retrieved_chunks(relevant_texts, title="检索到的相关片段")


def preview_chunks_tool(
    knowledge_base_id: str,
    user_id: str | None = None,
    limit: int = 3,
    preview_length: int = 200,
) -> str:
    """
    预览知识库中前几个 chunk（按存储顺序），便于调试索引内容。
    """
    persisted_chunks = list_persisted_chunks_for_document(
        knowledge_base_id=knowledge_base_id,
        user_id=user_id,
        limit=limit,
    )
    if persisted_chunks:
        return format_retrieved_chunk_results(
            [
                {
                    "chunk_id": item["chunk_id"],
                    "document_id": item["document_id"],
                    "score": 1.0,
                    "content": item["content"],
                }
                for item in persisted_chunks
            ],
            title="知识库片段预览",
            preview_length=preview_length,
        )

    rag = get_knowledge_base(knowledge_base_id)
    if rag is None:
        return kb_not_found_message(knowledge_base_id)

    if not rag.chunks:
        return "## 知识库预览\n（知识库为空，请先上传文档）"

    count = max(0, limit)
    samples = rag.chunks[:count] if count else []

    return format_retrieved_chunks(
        samples,
        title="知识库片段预览",
        preview_length=preview_length,
    )
