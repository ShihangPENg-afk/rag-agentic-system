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

import dashscope
import numpy as np
from dashscope import Generation

from config import (
    API_KEY,
    MODEL_NAME,
    TOP_K,
    FINAL_TOP_K,
    DISTANCE_THRESHOLD,
    SCORE_THRESHOLD_PERCENT,
    MAX_PROMPT_LENGTH,
    SAFE_RESERVE_LENGTH,
    CONTEXT_TRUNCATE_STEP,
)
from app.services.index_service import get_embeddings
from utils.utils import check_network
dashscope.api_key = API_KEY

from app.schemas.chat_state import ChatState
from app.services.kb_registry import get_knowledge_base, get_all_ids


def build_chat_state_from_request(request) -> ChatState:
    history_pairs = [(item.user, item.assistant) for item in request.history]
    return ChatState(
        knowledge_base_id=request.knowledge_base_id,
        user_query=request.question,
        history_pairs=history_pairs,
    )

def chat_with_rag_state(state: ChatState):
    rag_system = get_knowledge_base(state.knowledge_base_id)
    if rag_system is None:
        available_ids = get_all_ids()
        raise LookupError(
            f"知识库不存在: {state.knowledge_base_id}。可用知识库ID: {available_ids[:5]}..."
        )

    answer, updated_history = rag_system.query(
        user_query=state.user_query,
        history=state.history_pairs,
    )
    return answer, updated_history

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
    """
    检索基础函数：
    输入向量索引、文本块和增强后的问题，
    返回最相关的文本片段。

    这个函数既可以被 answer_with_index() 使用，
    也可以被 tools/retrieval_tools.py 复用。
    """
    if index is None or getattr(index, "ntotal", 0) == 0:
        return [], "⚠️ 知识库未初始化或为空，请先上传文档。"

    try:
        q_embeddings, _ = get_embeddings([enhanced_query])
        if not q_embeddings:
            return [], "⚠️ 问题向量化失败，请稍后重试"

        query_vector = np.array(q_embeddings, dtype=np.float32)

    except Exception as e:
        return [], f"⚠️ 向量化服务异常: {e}"

    try:
        distances, indices = index.search(query_vector, TOP_K)
        candidate_results = []

        # 第一层过滤：距离阈值
        for i, idx in enumerate(indices[0]):
            if idx < len(chunks):
                dist = distances[0][i]
                if dist < DISTANCE_THRESHOLD:
                    candidate_results.append((dist, chunks[idx]))

        # 如果严格阈值下没有结果，则退化使用最相近的前三条
        if not candidate_results:
            print("⚠️ 无满足严格阈值的片段，使用最相关的前3条")
            for i, idx in enumerate(indices[0][:3]):
                if idx < len(chunks):
                    candidate_results.append((distances[0][i], chunks[idx]))

        # 第二层过滤：分数百分比过滤
        if candidate_results:
            min_dist = candidate_results[0][0]
            threshold = min_dist + (1 - SCORE_THRESHOLD_PERCENT) * 10

            filtered = []
            for dist, text in candidate_results:
                if dist <= threshold:
                    filtered.append((dist, text))
            candidate_results = filtered

        # 按距离升序排序
        candidate_results.sort(key=lambda x: x[0])

        # 精排，保留最终片段
        relevant_texts = [item[1] for item in candidate_results[:FINAL_TOP_K]]

        if not relevant_texts:
            return [], "📚 未在文档中找到相关信息，请尝试换个问题。"

        print(f"✅ 精排完成：保留 {len(relevant_texts)} 条高相关片段（无无关内容）")
        for idx, text in enumerate(relevant_texts, 1):
            print(f"  {idx}. {text[:100]}...")

        return relevant_texts, None

    except Exception as e:
        return [], f"⚠️ 检索服务异常: {e}"


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