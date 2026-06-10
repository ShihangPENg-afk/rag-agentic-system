"""
检索工具：仅返回相关文本片段，不生成最终答案。
"""
from typing import List, Optional, Tuple

from app.services.chat_service import (
    enhance_query_with_history,
    normalize_history,
    retrieve_relevant_chunks,
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


def retrieve_chunks_tool(
    knowledge_base_id: str,
    user_query: str,
    history: Optional[List[Tuple[str, str]]] = None,
    max_history: int = 3,
    limit: int = 3,
) -> str:
    """
    根据用户问题检索知识库中的相关文本片段（不调用大模型生成答案）。
    """
    rag = get_knowledge_base(knowledge_base_id)
    if rag is None:
        return kb_not_found_message(knowledge_base_id)

    valid_turns = normalize_history(history, max_history=max_history)
    enhanced_query = enhance_query_with_history(user_query, valid_turns)
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
    limit: int = 3,
    preview_length: int = 200,
) -> str:
    """
    预览知识库中前几个 chunk（按存储顺序），便于调试索引内容。
    """
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
