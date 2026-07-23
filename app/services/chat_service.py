"""
问答服务层

当前职责：
1. State 构造
2. 问答编排
3. 检索基础函数（可被 tools 层复用）
4. Prompt 组装
5. 模型回答
"""
from typing import List, Optional, Tuple
from uuid import UUID

import dashscope
from dashscope import Generation

from app.core.config import (
    API_KEY,
    MODEL_NAME,
    MAX_PROMPT_LENGTH,
    SAFE_RESERVE_LENGTH,
    CONTEXT_TRUNCATE_STEP,
)
from app.retrievers.retriever_v1_faiss import retrieve_relevant_chunks_faiss
from app.retrievers.retriever_v2_pgvector import retrieve_relevant_chunks_pgvector
from utils.utils import check_network
dashscope.api_key = API_KEY

from app.schemas.chat_state import ChatState
from app.services.kb_registry import get_knowledge_base


def build_chat_state_from_request(request, user_id: UUID | str | None = None) -> ChatState:
    history_pairs = [(item.user, item.assistant) for item in request.history]
    return ChatState(
        knowledge_base_id=request.knowledge_base_id,
        user_id=str(user_id) if user_id is not None else None,
        collection_id=str(request.collection_id) if request.collection_id is not None else None,
        user_query=request.question,
        history_pairs=history_pairs,
    )

def chat_with_rag_state(state: ChatState):
    valid_turns = list(state.history_pairs or [])
    enhanced_query = enhance_query_with_history(state.user_query, valid_turns)

    relevant_texts, error, _results = retrieve_relevant_chunks_pgvector(
        knowledge_base_id=state.knowledge_base_id,
        enhanced_query=enhanced_query,
        user_id=state.user_id,
        collection_id=state.collection_id,
    )
    if error is None:
        return generate_answer(
            user_query=state.user_query,
            relevant_texts=relevant_texts,
            valid_turns=valid_turns,
        )

    if error.startswith("📚"):
        return error, valid_turns

    rag_system = get_knowledge_base(state.knowledge_base_id)
    if rag_system is not None:
        return rag_system.query(
            user_query=state.user_query,
            history=state.history_pairs,
        )

    return error, valid_turns

def normalize_history(history: Optional[list], max_history: int = 3) -> List[Tuple[str, str]]:
    """规范化对话历史"""
    if history is None:
        return []

    valid_turns = [
        (item[0], item[1])
        for item in history[-max_history:]
        if isinstance(item, (list, tuple)) and len(item) >= 2
    ]

    return valid_turns

def enhance_query_with_history(user_query: str, valid_turns: List[Tuple[str, str]]) -> str:
    """如果用户问题里有代词，则结合上一轮回答增强查询"""
    enhanced_query = user_query

    if valid_turns:
        pronouns = ["它", "它们", "这个", "那个", "这些", "那些", "其", "这", "那"]
        if any(pronoun in user_query for pronoun in pronouns):
            _, last_a = valid_turns[-1]
            enhanced_query = f"上一轮对话内容：{last_a}\n当前问题：{user_query}"
            print("🔄 检测到指代词，已增强问题")

    return enhanced_query

def retrieve_relevant_chunks(index, chunks: List[str], enhanced_query: str):
    return retrieve_relevant_chunks_faiss(index, chunks, enhanced_query)


def build_history_section(valid_turns: List[Tuple[str, str]]) -> str:
    """构建历史记录文本"""
    if not valid_turns:
        return ""

    history_section = "## 对话历史\n"
    for i, (q, a) in enumerate(valid_turns, 1):
        history_section += f"第{i}轮 - 用户：{q}\n第{i}轮 - 助手：{a}\n"
    history_section += "\n"
    return history_section

def build_context_section(relevant_texts: List[str]) -> str:
    """构建参考内容文本"""
    context_section = "## 参考内容\n"
    for i, text in enumerate(relevant_texts[:3], 1):
        context_section += f"{i}. {text}\n"
    context_section += "\n"
    return context_section


def truncate_context_safely(base_prompt: str, context_text: str) -> str:
        """安全截断上下文"""
        available_length = MAX_PROMPT_LENGTH - len(base_prompt) - SAFE_RESERVE_LENGTH

        if available_length <= 0:
            return ""

        original_len = len(context_text)
        if original_len <= available_length:
            return context_text

        # 超长：自动截断（保留最相关的前面内容）
        truncated = context_text[:available_length]

        # 从后往前找最近的句子结束符（。！？\n）
        split_pos = truncated.rfind("。")
        if split_pos < available_length * 0.7:  # 不要太靠前
            split_pos = truncated.rfind("！")  # rfind() 返回一个 数字（整数）
        if split_pos < available_length * 0.7:  # 代表字符在字符串中的 位置下标（索引）
            split_pos = truncated.rfind("？")
        if split_pos < available_length * 0.7:
            split_pos = truncated.rfind("\n")

        # 如果找到合理的断句位置 → 用断句位置
        if split_pos > 0:
            context_text = truncated[:split_pos + 1]
        else:
            # 找不到断句 → 用步长优雅截断（不会一下切太多）
            while len(context_text) > available_length:
                # 每次只切一步（200），但不会超过需要
                cut_length = min(CONTEXT_TRUNCATE_STEP, len(context_text) - available_length)
                context_text = context_text[:-cut_length]

        print(f"⚠️  智能截断：{original_len} → {len(context_text)} 字符（保证语义完整）")
        return context_text

def generate_answer(
    user_query: str,
    relevant_texts: List[str],
    valid_turns: List[Tuple[str, str]],
    max_history: int = 3,
):
    """根据检索结果生成最终回答"""
    history_section = build_history_section(valid_turns)
    context_section = build_context_section(relevant_texts)

    base_prompt = f"""{history_section}

## 当前问题
{user_query}

## 回答要求
1. 请严格基于【参考内容】回答问题
2. 如果参考内容中没有相关信息，请直接说"未在文档中找到相关信息"
3. 可以结合【对话历史】保持回答的连贯性
4. 不要编造答案，回答要简洁准确

## 回答
"""

    safe_context = truncate_context_safely(base_prompt, context_section)
    prompt = safe_context + base_prompt

    try:
        if not check_network():
            return "❌ 错误：网络断开，无法调用大模型服务", valid_turns

        resp = Generation.call(
            model=MODEL_NAME,
            prompt=prompt,
            result_format="message",
        )

        if resp.status_code == 200:
            answer = resp.output.choices[0].message.content
            updated_history = valid_turns + [(user_query, answer)]
            if len(updated_history) > max_history:
                updated_history = updated_history[-max_history:]
            return answer, updated_history

        return f"❌ 模型调用失败: {resp.message}", valid_turns

    except Exception as e:
        return f"❌ 模型服务异常: {e}", valid_turns


def answer_with_index(index, chunks: List[str], user_query: str, history: Optional[list] = None, max_history: int = 3):
    """对外暴露的总问答入口"""
    valid_turns = normalize_history(history, max_history=max_history)

    enhanced_query = enhance_query_with_history(user_query, valid_turns)
    relevant_texts, error = retrieve_relevant_chunks(index, chunks, enhanced_query)

    if error:
        return error, valid_turns

    return generate_answer(
        user_query=user_query,
        relevant_texts=relevant_texts,
        valid_turns=valid_turns,
        max_history=max_history,
    )


def persist_chat_exchange(
    user_id: UUID,
    question: str,
    answer: str,
    session_id: UUID | str | None = None,
) -> dict:
    """
    保存一轮用户问题和 AI 回答。

    不参与 RAG 推理，只负责把问答结果落到 sessions/messages。
    """
    from app.repositories.chat_repository import (
        create_chat_session,
        create_message,
        get_chat_session_by_id,
        get_chat_session_by_user,
    )

    if session_id is None:
        title = question.strip()[:80] or "新会话"
        session = create_chat_session(user_id=user_id, title=title)
        session_id = session["id"]
    else:
        session = get_chat_session_by_user(session_id=session_id, user_id=user_id)
        if session is None:
            if get_chat_session_by_id(session_id=session_id) is not None:
                raise PermissionError("会话不属于当前用户")
            raise LookupError("会话不存在或无权访问")

    create_message(session_id=session_id, role="user", content=question)
    create_message(session_id=session_id, role="assistant", content=answer)
    return get_chat_session_by_user(session_id=session_id, user_id=user_id) or session


def list_user_chat_sessions(user_id: UUID, limit: int = 50) -> list[dict]:
    from app.repositories.chat_repository import list_chat_sessions_by_user

    return list_chat_sessions_by_user(user_id=user_id, limit=limit)


def list_user_session_messages(
    user_id: UUID,
    session_id: UUID | str,
    limit: int = 200,
) -> list[dict]:
    from app.repositories.chat_repository import (
        get_chat_session_by_id,
        list_messages_by_session_and_user,
    )

    messages = list_messages_by_session_and_user(
        session_id=session_id,
        user_id=user_id,
        limit=limit,
    )
    if messages is None:
        if get_chat_session_by_id(session_id=session_id) is not None:
            raise PermissionError("会话不属于当前用户")
        raise LookupError("会话不存在或无权访问")
    return messages
