#!/usr/bin/env python3
"""
LangGraph Agent 本地测试脚本（最终版）

功能：
1. 构建知识库
2. 运行多工具 LangGraph Agent
3. 显式打印消息轨迹（观察是否触发 tool_calls）
4. 测试：
   - 简单问题
   - 文档问题
   - 章节标题问题
   - 表格统计问题
   - 带 history 的连续两轮问题

用法：
    python test_langgraph_agent.py
    python test_langgraph_agent.py test.pdf
    python test_langgraph_agent.py /absolute/path/to/your.pdf

说明：
- 如果不传 PDF 路径，默认使用当前项目根目录下的 test.pdf
- 本脚本不依赖 FastAPI 路由，直接走 service + agent graph
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.graph import build_agent_graph
from app.services.upload_service import create_knowledge_base_from_saved_pdf


def print_banner(title: str) -> None:
    """打印分隔标题，方便终端观察。"""
    width = 72
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def preview_text(text: str, max_len: int = 180) -> str:
    """预览文本，避免终端输出过长。"""
    text = str(text).replace("\n", " ")
    return text if len(text) <= max_len else text[:max_len] + "..."


def resolve_pdf_path(raw: str) -> Path:
    """
    解析并校验 PDF 路径。
    - 支持相对路径 / 绝对路径 / ~
    - 检查文件是否存在
    - 检查扩展名是否为 .pdf
    """
    path = Path(raw).expanduser().resolve()

    if not path.is_file():
        raise FileNotFoundError(f"PDF 文件不存在: {path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError(f"仅支持 .pdf 文件: {path}")

    return path


def assert_pdf_magic(path: Path) -> None:
    """
    检查文件头是否为 PDF 魔数。
    防止只是后缀名叫 .pdf，但内容不是真 PDF。
    """
    with path.open("rb") as f:
        header = f.read(5)

    if len(header) < 4 or not header.startswith(b"%PDF"):
        raise ValueError(f"文件内容与 PDF 格式不符: {path}")


def extract_final_answer(messages) -> str:
    """
    从消息流中逆序找到最后一条 AIMessage，并取其内容。
    这样比直接 messages[-1].content 更稳。
    """
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            return str(msg.content)
    return "未找到最终 AIMessage。"


def print_message_trace(messages) -> None:
    """
    显式打印 LangGraph 消息轨迹，方便观察：
    - 有没有产生 tool_calls
    - 工具节点有没有真正执行
    - 工具返回了什么
    - 最终消息链长什么样
    """
    print_banner("消息轨迹（Message Trace）")

    for i, msg in enumerate(messages, 1):
        msg_type = type(msg).__name__
        print(f"\n[{i}] {msg_type}")

        # 1. 用户消息
        if isinstance(msg, HumanMessage):
            print("角色: 用户")
            print("内容:", preview_text(msg.content))

        # 2. AI 消息
        elif isinstance(msg, AIMessage):
            print("角色: AI")
            tool_calls = getattr(msg, "tool_calls", None)
            if tool_calls:
                print("tool_calls:", tool_calls)
            if msg.content:
                print("内容:", preview_text(msg.content))

        # 3. 工具消息
        elif isinstance(msg, ToolMessage):
            print("角色: 工具")
            tool_name = getattr(msg, "name", None)
            if tool_name:
                print("工具名:", tool_name)
            print("工具输出:", preview_text(msg.content))

        # 4. 其他消息
        else:
            print("内容:", preview_text(getattr(msg, "content", msg)))


def build_knowledge_base(pdf_path: Path) -> tuple[str, dict]:
    """
    构建知识库并返回：
    - knowledge_base_id
    - result 原始结果字典
    """
    print_banner("步骤 1 / 构建知识库")
    print(f"PDF 路径: {pdf_path}")
    print(f"文件名:   {pdf_path.name}")
    print("正在切块、向量化并注册知识库（需网络与 DASHSCOPE_API_KEY）...")

    result = create_knowledge_base_from_saved_pdf(
        str(pdf_path),
        pdf_path.name,
    )
    kb_id = result["knowledge_base_id"]

    print(f"\n✅ {result['message']}")
    print(f"knowledge_base_id: {kb_id}")
    print(f"chunks_count:      {result['chunks_count']}")

    return kb_id, result


def run_single_turn_case(graph, kb_id: str, title: str, question: str) -> None:
    """
    运行单轮问题测试。
    """
    print_banner(title)
    print("问题:", question)

    result = graph.invoke({
        "messages": [HumanMessage(content=question)],
        "knowledge_base_id": kb_id,
    })

    messages = result["messages"]
    print_message_trace(messages)

    print_banner("最终回答")
    print(extract_final_answer(messages))

def has_tool_call(messages, tool_name: str | None = None) -> bool:
    """
    检查消息列表中是否出现过 tool_call。
    如果指定 tool_name，则只检查该工具。
    """
    for msg in messages:
        if isinstance(msg, AIMessage):
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                continue

            if tool_name is None:
                return True

            for tc in tool_calls:
                if tc.get("name") == tool_name:
                    return True
    return False

def has_any_tool_call(messages, tool_names: list[str]|None = None) -> bool:
    """
    检查消息列表中是否出现过指定工具调用。
    - tool_names 为 None：任意工具都算
    - tool_names 为列表：只要命中其中一个就算
    """
    for msg in messages:
        if isinstance(msg, AIMessage):
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                continue

            if tool_names is None:
                return True
            for tc in tool_calls:
                if tc.get("name") in tool_names:
                    return True
    return False

def run_history_case(graph, kb_id: str) -> None:
    """
    运行带 history 的两轮连续测试。
    第二轮会把第一轮消息继续传入，并显式检查是否再次调用 retrieve_chunks 或 list_headings。
    """
    print_banner("测试 5：带 history 的连续两轮问题(追问)")

    # 第一轮
    first_question = "这份文档主要讲什么？"
    print("\n[第一轮问题]")
    print(first_question)

    result1 = graph.invoke({
        "messages": [HumanMessage(content=first_question)],
        "knowledge_base_id": kb_id,
    })

    messages1 = result1["messages"]
    print_message_trace(messages1)

    print_banner("第一轮最终回答")
    print(extract_final_answer(messages1))

    # 第二轮：沿用第一轮消息历史
    second_question = "它具体包含哪些部分？请结合上文说明。"
    print("\n[第二轮问题]")
    print(second_question)

    result2 = graph.invoke({
        "messages": messages1 + [HumanMessage(content=second_question)],
        "knowledge_base_id": kb_id,
    })

    messages2 = result2["messages"]
    print_message_trace(messages2)

    print_banner("第二轮最终回答")
    print(extract_final_answer(messages2))

    # 只看第二轮新增消息
    new_messages = messages2[len(messages1):]

    print_banner("第二轮工具验证结果")
    if has_any_tool_call(new_messages, ["retrieve_chunks", "list_headings"]):
        print("✅ 第二轮已再次调用 retrieve_chunks 或 list_headings")
    else:
        print("⚠️ 第二轮没有再次调用 retrieve_chunks / list_headings，可继续优化 prompt 或图路由")

def run_content_followup_case(graph, kb_id: str) -> None:
    """
    运行带 history 的两轮连续测试（内容型追问）。
    第二轮更期待再次调用 retrieve_chunks。
    """
    print_banner("测试 6: 带 history 的连续两轮问题（内容型追问）")

    first_question = "这份文档主要讲什么？"
    print("\n[第一轮问题]")
    print(first_question)

    result1 = graph.invoke({
        "messages": [HumanMessage(content=first_question)],
        "knowledge_base_id": kb_id,
    })
    messages1 = result1["messages"]
    print_message_trace(messages1)

    print_banner("第一轮最终回答")
    print(extract_final_answer(messages1))

    second_question = "它开头具体是如何定义软件的？请结合上文说明。"
    print("\n[第二轮问题]")
    print(second_question)

    result2 = graph.invoke({
        "messages": messages1 + [HumanMessage(content = second_question)],
        "knowledge_base_id": kb_id,
    })

    messages2 = result2["messages"]
    print_message_trace(messages2)

    print_banner("第二轮最终回答")
    print(extract_final_answer(messages2))

    print_banner("第二轮工具验证结果")
    if has_any_tool_call(messages2, ["retrieve_chunks"]):
        print("✅ 第二轮已再次调用 retrieve_chunks")
    else:
        print("⚠️ 第二轮没有再次调用 retrieve_chunks，可继续优化 prompt 或图路由")

def main() -> int:
    """
    主流程：
    1. 解析参数
    2. 检查 PDF
    3. 构建知识库
    4. 构建 Agent 图
    5. 跑多组测试
    """
    parser = argparse.ArgumentParser(
        description="LangGraph Agent 本地测试脚本（默认使用 test.pdf）"
    )
    parser.add_argument(
        "pdf_path",
        nargs="?",
        default="test.pdf",
        help="用于构建知识库的 PDF 文件路径，默认 test.pdf",
    )
    args = parser.parse_args()

    try:
        # 1. 校验 PDF
        pdf_path = resolve_pdf_path(args.pdf_path)
        assert_pdf_magic(pdf_path)

        # 2. 构建知识库
        kb_id, _ = build_knowledge_base(pdf_path)

        # 3. 构建 Agent 图
        print_banner("步骤 2 / 构建 LangGraph Agent")
        graph = build_agent_graph(kb_id)
        print("✅ Agent 图构建成功")

        # 4. 测试 1：简单问题（通常不调工具）
        run_single_turn_case(
            graph,
            kb_id,
            title="测试 1：简单问题（通常不调工具）",
            question="你好",
        )

        # 5. 测试 2：文档问题（通常应触发 retrieve_chunks）
        run_single_turn_case(
            graph,
            kb_id,
            title="测试 2：文档问题（应尝试调 retrieve_chunks）",
            question="这份文档主要讲什么？",
        )

        # 6. 测试 3：章节标题问题（通常应触发 list_headings）
        run_single_turn_case(
            graph,
            kb_id,
            title="测试 3：章节标题问题（应尝试调 list_headings）",
            question="列出这份文档中的章节标题。",
        )

        # 7. 测试 4：表格统计问题（通常应触发 count_tables）
        run_single_turn_case(
            graph,
            kb_id,
            title="测试 4：表格统计问题（应尝试调 count_tables）",
            question="这份文档里大概有几个表格？",
        )

        # 8. 测试 5：带 history 的连续问题
        run_history_case(graph, kb_id)

        run_content_followup_case(graph, kb_id)

        print_banner("测试完成")
        print("所有 LangGraph Agent 测试已执行完成。")
        return 0

    except FileNotFoundError as e:
        print(f"\n❌ 文件错误: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"\n❌ 值错误: {e}", file=sys.stderr)
        return 1

    except (ValueError, RuntimeError, SystemExit) as e:
        print(f"\n❌ 未预期错误: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())