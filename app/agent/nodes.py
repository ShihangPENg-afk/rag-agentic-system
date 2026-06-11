from __future__ import annotations

import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from config import API_KEY, MODEL_NAME, DASHSCOPE_BASE_URL
from app.agent.state import AgentState
from app.tools.document_tools import count_tables_tool, list_headings_tool
from app.tools.retrieval_tools import retrieve_chunks_tool


SYSTEM_PROMPT = """
你是一个 PDF 知识库问答 Agent。

你可以使用工具：
1. retrieve_chunks(query)
   - 用于从知识库中检索与问题最相关的文本片段
2. list_headings()
   - 用于列出文档中的章节/小节标题
3. count_tables()
   - 用于粗略统计文档中的表格迹象数量

规则：
1. 如果用户问“这份文档讲什么、某个概念在哪、某部分内容是什么”，优先用 retrieve_chunks
2. 如果用户问“有哪些章节、目录结构是什么”，优先用 list_headings
3. 如果用户问“有几个表格”，优先用 count_tables
4. 工具返回的是证据或结构信息，不一定是最终答案
5. 你需要根据工具结果再组织最终回答
6. 如果问题只是简单寒暄，可以不调用工具
7. 对于涉及文档内容的追问，优先再次调用 retrieve_chunks 验证，不要只凭上一轮总结直接续写
8. 当存在对话历史时，你可以利用历史理解“它 / 上文 / 该部分”等指代，但回答文档问题时仍应优先用工具核实
"""

FOLLOW_MARKERS = (
    "它",
    "这个",
    "这些",
    "上文",
    "前面",
    "上一轮",
    "刚才",
    "上述",
    "该部分",
    "该文档",
    "文档内容",
)

STRUCTURE_MARKERS = (
    "哪些部分",
    "章节",
    "目录",
    "结构",
    "小节",
)

CONTENT_MARKERS = (
    "定义",
    "特点",
    "作用",
    "原理",
    "讲了什么",
    "如何",
    "为什么",
    "是什么",
)


def create_model():
    """
    使用 DashScope 的 OpenAI-compatible 接口接入 Qwen。
    """
    return ChatOpenAI(
        model=MODEL_NAME,
        api_key=API_KEY,
        base_url=DASHSCOPE_BASE_URL,
        temperature=0,
    )


def build_memory_system_message(memory_summary: str) -> SystemMessage | None:
    """
    把最近历史摘要注入为额外 system message。
    """
    if not memory_summary.strip():
        return None

    return SystemMessage(
        content=(
            "以下是当前会话最近几轮对话历史，请用于理解代词、追问与上下文：\n"
            f"{memory_summary}"
        )
    )


def make_agent_tools(
    knowledge_base_id: str,
    history_pairs: list[tuple[str, str]] | None = None,
):
    history_pairs = history_pairs or []

    @tool("retrieve_chunks")
    def retrieve_chunks(query: str) -> str:
        """从当前知识库检索与用户问题最相关的文本片段。"""
        return retrieve_chunks_tool(
            knowledge_base_id=knowledge_base_id,
            user_query=query,
            history=history_pairs,
        )

    @tool("list_headings")
    def list_headings() -> str:
        """列出当前知识库中的章节/小节标题。"""
        return list_headings_tool(knowledge_base_id)

    @tool("count_tables")
    def count_tables() -> str:
        """粗略统计当前知识库中的表格迹象数量。"""
        return count_tables_tool(knowledge_base_id)

    return [retrieve_chunks, list_headings, count_tables]


def get_latest_user_query(messages) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return str(msg.content).strip()
    return ""


def get_previous_user_query(messages) -> str:
    user_queries = [str(msg.content).strip() for msg in messages if isinstance(msg, HumanMessage)]
    if len(user_queries) >= 2:
        return user_queries[-2]
    return ""


def classify_followup_intent(messages) -> str:
    """
    把追问简单分成：
    - structure：更适合 list_headings
    - content：更适合 retrieve_chunks
    - none：不做特殊增强
    """
    latest_query = get_latest_user_query(messages)
    if not latest_query:
        return "none"

    has_prior_ai = any(isinstance(msg, AIMessage) for msg in messages[:-1])
    if not has_prior_ai:
        return "none"

    is_followup_like = (
        len(latest_query) <= 40
        and any(marker in latest_query for marker in FOLLOW_MARKERS)
    )
    if not is_followup_like:
        return "none"

    if any(marker in latest_query for marker in STRUCTURE_MARKERS):
        return "structure"

    if any(marker in latest_query for marker in CONTENT_MARKERS):
        return "content"

    return "none"

def is_multi_hop_question(question: str) -> bool:
    """
    粗略判断当前问题是否需要多步推理。
    规则：出现“分别 / 和 / 以及 / 对比 / 区别 / 综合 / 两者 / 哪些章节”等信号时认为是复杂问题。
    """
    markers = (
        "分别",
        "以及",
        "两者",
        "区别",
        "对比",
        "综合",
        "分别在哪",
        "哪些章节",
        "关系",
        "并说明",
        "并分析",
    )
    return any(marker in question for marker in markers)

def _normalize_evidence_text(text: str) -> str:
    """
    统一工具返回证据的格式，便于后续 debug 和 evidence_by_sub_query 展示。
    """
    text = str(text).strip()

    # 统一标题前缀
    text = text.replace("##检索到的相关片段", "## 检索到的相关片段")
    
    # 统一多余空格
    text = re.sub(r"[ \t]+", " ", text)

    # 合并过多空行
    text = re.sub(fr"\n{3,}", "\n\n", text)

    return text.strip()

def _unique_keep_order(items: list[str]) -> list[str]:
    """
    保留顺序去重
    """
    seen = set()
    result = []

    for item in items:
        norm = item.strip()
        if not norm:
            continue
        if norm not in seen:
            seen.add(norm)
            result.append(item)

    return result

def decompose_question(question: str) -> list[str]:
    """
    轻量级问题拆解：
    优先处理“X和Y分别在哪些部分/分别在哪里/分别讲了什么”这类典型双信息点问题。
    """
    q = question.strip()

    # 去掉常见前缀，避免子问题太啰嗦
    q_clean = re.sub(r"^文档中", "", q).strip()

    # 模式 1：X 和 Y 分别在哪些部分 / 分别在哪里 / 分别讲了什么
    m = re.match(
        r"^(?P<a>.+?)和(?P<b>.+?)(?P<tail>分别在哪些部分|分别在哪里|分别讲了什么|分别是什么|分别在哪一节|分别位于哪里)[？?]?(?P<extra>请一起说明|并说明|请综合说明|请一起分析)?$",
        q_clean,
    )
    if m:
        a = m.group("a").strip("，。？ ")
        b = m.group("b").strip("，。？ ")
        tail = m.group("tail")

        if "哪些部分" in tail or "哪里" in tail or "哪一节" in tail:
            suffix = "在哪些部分？"
        elif "讲了什么" in tail:
            suffix = "讲了什么？"
        else:
            suffix = "是什么？"

        return [
            f"{a}{suffix}",
            f"{b}{suffix}",
            f"综合回答：{question}",
        ]

    # 模式 2：X 以及 Y ...
    if "以及" in q_clean:
        parts = [p.strip("，。？ ") for p in q_clean.split("以及") if p.strip()]
        if len(parts) >= 2:
            return [f"{p}的相关内容是什么？" for p in parts[:2]] + [f"综合回答：{question}"]

    # 模式 3：对比 / 区别
    if "区别" in q_clean or "对比" in q_clean:
        return [
            f"找出与原问题相关的第一个概念内容：{question}",
            f"找出与原问题相关的第二个概念内容：{question}",
            f"综合比较并回答：{question}",
        ]

    return [question]

def planner_node(state: AgentState) -> dict:
    question = state.get("current_question", "").strip()

    need_multi_hop = is_multi_hop_question(question)
    sub_queries = decompose_question(question) if need_multi_hop else [question]

    return {
        "need_multi_hop": need_multi_hop,
        "sub_queries": sub_queries,
        "current_sub_query_index": 0,
        "evidence_by_sub_query": {},
        "retrieval_round": 0,
        "decision": "",
    }

def evaluator_node(state: AgentState) -> dict:
    sub_queries = state.get("sub_queries", [])
    idx = state.get("current_sub_query_index", 0)
    retrieval_round = state.get("retrieval_round", 0)
    max_rounds = state.get("max_retrieval_rounds", 4)
    messages = state.get("messages", [])
    evidence_by_sub_query = dict(state.get("evidence_by_sub_query", {}))

    if not sub_queries:
        return {"decision": "enough_to_answer"}

    current_sub_query = sub_queries[idx] if 0 <= idx < len(sub_queries) else ""
    is_synthesis_step = current_sub_query.startswith("综合回答：")

    # 从最近 ToolMessage 中提取证据
    current_evidence = []
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            text = _normalize_evidence_text(str(msg.content))
            if text:
                current_evidence.append(text)
            if len(current_evidence) >= 2:
                break
        elif isinstance(msg, HumanMessage):
            break

    current_evidence = list(reversed(current_evidence))

    if current_sub_query:
        existing = evidence_by_sub_query.get(current_sub_query, [])
        merged = existing + current_evidence
        evidence_by_sub_query[current_sub_query] = _unique_keep_order(merged)

    # 综合回答步骤：如果前面已经有证据，直接进入最终综合
    if is_synthesis_step:
        prior_evidence_exists = any(
            evidences
            for sub_q, evidences in evidence_by_sub_query.items()
            if not sub_q.startswith("综合回答：")
        )
        if prior_evidence_exists:
            return {
                "decision": "enough_to_answer",
                "evidence_by_sub_query": evidence_by_sub_query,
            }

    has_any_evidence = bool(evidence_by_sub_query.get(current_sub_query, []))

    if not has_any_evidence and retrieval_round + 1 < max_rounds:
        return {
            "decision": "need_more_retrieval",
            "retrieval_round": retrieval_round + 1,
            "evidence_by_sub_query": evidence_by_sub_query,
        }

    if idx + 1 < len(sub_queries):
        return {
            "decision": "next_sub_query",
            "current_sub_query_index": idx + 1,
            "retrieval_round": 0,
            "evidence_by_sub_query": evidence_by_sub_query,
        }

    return {
        "decision": "enough_to_answer",
        "evidence_by_sub_query": evidence_by_sub_query,
    }

def answer_node(state: AgentState) -> dict:
    question = state.get("current_question", "")
    memory_summary = state.get("memory_summary", "")
    evidence_by_sub_query = state.get("evidence_by_sub_query", {})

    model = create_model()

    evidence_lines = []
    for sub_q, evidences in evidence_by_sub_query.items():
        evidence_lines.append(f"子问题：{sub_q}")
        if evidences:
            for i, ev in enumerate(evidences[:2], 1):
                evidence_lines.append(f"证据{i}：{ev[:500]}")
        else:
            evidence_lines.append("未找到明显证据。")
        evidence_lines.append("")

    prompt = f"""
你是一个 PDF 知识库问答 Agent，现在需要基于多步检索得到的证据回答最终问题。

## 原始问题
{question}

## 最近历史摘要
{memory_summary}

## 已收集证据
{chr(10).join(evidence_lines)}

## 回答要求
1. 先回答原始问题，不要逐字复述所有证据
2. 如果某个子问题证据不足，要明确说明
3. 尽量把多个子问题综合成结构清晰的回答
4. 不要编造文档中不存在的事实
"""

    response = model.invoke([HumanMessage(content=prompt)])
    return {"messages": [response]}



def agent_node(state: AgentState) -> dict:
    messages = state["messages"]
    knowledge_base_id = state["knowledge_base_id"]
    chat_history_pairs = state.get("chat_history_pairs", [])
    current_question = state.get("current_question", get_latest_user_query(messages))

    sub_queries = state.get("sub_queries", [])
    current_sub_query_index = state.get("current_sub_query_index", 0)

    active_sub_query = state.get("current_question", "")
    if sub_queries and 0 <= current_sub_query_index < len(sub_queries):
        active_sub_query = sub_queries[current_sub_query_index]

    memory_summary = state.get("memory_summary", "")

    tools = make_agent_tools(
        knowledge_base_id=knowledge_base_id,
        history_pairs=chat_history_pairs,
    )
    model = create_model().bind_tools(tools)

    system_messages = [SystemMessage(content=SYSTEM_PROMPT)]

    memory_message = build_memory_system_message(memory_summary)
    if memory_message is not None:
        system_messages.append(memory_message)

    if active_sub_query.startswith("综合回答："):
        system_messages.append(
            SystemMessage(
                content=(
                    "当前处于多步推理的综合回答阶段。"
                    f"\n当前综合任务：{active_sub_query}"
                    "\n请优先基于已有证据整合作答，除非证据明显不足，否则不要再次调用工具。"
                )
            )
        )
    else:
        system_messages.append(
            SystemMessage(
                content=(
                "当前正在执行多步推理中的一个步骤。"
                f"\n当前待处理子问题：{active_sub_query}"
                "\n请优先围绕这个子问题决定是否调用工具，而不是一次性回答全部问题。"
            )
        )
    )

    followup_type = classify_followup_intent(messages)

    if followup_type == "content":
        retrieval_hint = get_previous_user_query(messages) or current_question
        system_messages.append(
            SystemMessage(
                content=(
                    "当前问题是对文档内容的追问。"
                    "请优先调用 retrieve_chunks 验证后再回答。"
                    f"\n检索重点：{retrieval_hint}"
                )
            )
        )
    elif followup_type == "structure":
        system_messages.append(
            SystemMessage(
                content=(
                    "当前问题是对文档结构/组成的追问。"
                    "请优先调用 list_headings 获取章节结构，再回答。"
                )
            )
        )

    working_messages = list(messages)
    if active_sub_query and active_sub_query != get_latest_user_query(messages):
        working_messages = working_messages + [
            HumanMessage(content=f"请先处理这个子问题：{active_sub_query}")
        ]

    response = model.invoke(system_messages + working_messages)

    return {
        "messages": [response],
        "current_question": current_question,
        "chat_history_pairs": chat_history_pairs,
        "memory_summary": memory_summary,
        "retrieved_evidence": state.get("retrieved_evidence", []),
    }