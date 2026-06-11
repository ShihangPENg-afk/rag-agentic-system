from app.services.kb_registry import get_all_ids


def kb_not_found_message(knowledge_base_id: str) -> str:
    """
    统一生成“知识库不存在”提示。
    """
    available = get_all_ids()
    if not available:
        return f"⚠️ 知识库不存在: {knowledge_base_id}。当前还没有任何可用知识库，请先上传文档。"

    preview = ", ".join(available[:5])
    suffix = "..." if len(available) > 5 else ""
    return f"⚠️ 知识库不存在: {knowledge_base_id}。可用知识库ID: {preview}{suffix}"