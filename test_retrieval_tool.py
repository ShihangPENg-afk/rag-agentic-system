#!/usr/bin/env python3
"""
检索工具本地测试（不依赖 FastAPI 路由）。

用法:
    python test_retrieval_tool.py <PDF 文件路径>

示例:
    python test_retrieval_tool.py ./data/sample.pdf
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 保证从项目根目录运行时能正确 import app.*
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.upload_service import create_knowledge_base_from_saved_pdf
from app.tools.retrieval_tools import preview_chunks_tool, retrieve_chunks_tool


def print_banner(title: str) -> None:
    width = 72
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def print_block(label: str, content: str) -> None:
    print(f"\n--- {label} ---")
    print(content)


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


def build_knowledge_base(pdf_path: Path) -> dict:
    print_banner("步骤 1 / 构建知识库")
    print(f"PDF 路径: {pdf_path}")
    print(f"文件名:   {pdf_path.name}")
    print("正在切块、向量化并注册知识库（需网络与 DASHSCOPE_API_KEY）...")

    result = create_knowledge_base_from_saved_pdf(
        str(pdf_path),
        pdf_path.name,
    )
    print(f"\n✅ {result['message']}")
    print(f"   chunks_count = {result['chunks_count']}")
    return result


def run_preview(knowledge_base_id: str, limit: int = 3, preview_length: int = 200) -> None:
    print_banner("步骤 2 / 预览知识库片段（preview_chunks_tool）")
    print(f"knowledge_base_id = {knowledge_base_id}")
    output = preview_chunks_tool(
        knowledge_base_id=knowledge_base_id,
        limit=limit,
        preview_length=preview_length,
    )
    print_block("preview_chunks_tool 输出", output)


def run_retrieval(
    knowledge_base_id: str,
    label: str,
    user_query: str,
    history: list[tuple[str, str]] | None = None,
) -> None:
    print_banner(label)
    print(f"问题: {user_query}")
    if history:
        print("历史轮次:")
        for i, (q, a) in enumerate(history, 1):
            preview_a = a if len(a) <= 120 else a[:120] + "..."
            print(f"  [{i}] 用户: {q}")
            print(f"      助手: {preview_a}")

    output = retrieve_chunks_tool(
        knowledge_base_id=knowledge_base_id,
        user_query=user_query,
        history=history,
    )
    print_block("retrieve_chunks_tool 输出", output)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="本地测试 retrieval_tools（构建知识库 + 预览 + 检索）",
    )
    parser.add_argument(
        "pdf_path",
        help="用于构建知识库的 PDF 文件路径",
    )
    parser.add_argument(
        "--preview-limit",
        type=int,
        default=3,
        help="preview_chunks_tool 预览的片段数量（默认 3）",
    )
    parser.add_argument(
        "--preview-length",
        type=int,
        default=200,
        help="每个预览片段的最大字符数（默认 200）",
    )
    args = parser.parse_args()

    try:
        pdf_path = resolve_pdf_path(args.pdf_path)
        assert_pdf_magic(pdf_path)

        result = build_knowledge_base(pdf_path)
        kb_id = result["knowledge_base_id"]

        print_banner("知识库 ID")
        print(kb_id)

        run_preview(
            kb_id,
            limit=args.preview_limit,
            preview_length=args.preview_length,
        )

        run_retrieval(
            kb_id,
            label="步骤 3 / 普通检索问题（retrieve_chunks_tool）",
            user_query="文档中主要讨论了哪些主题或关键概念？",
        )

        run_retrieval(
            kb_id,
            label="步骤 4 / 总结型问题（retrieve_chunks_tool）",
            user_query="请总结这份文档的核心要点与结论。",
        )

        run_retrieval(
            kb_id,
            label="步骤 5 / 带 history 的指代问题（retrieve_chunks_tool）",
            user_query="它具体包含哪些部分？请结合上文说明。",
            history=[
                (
                    "这份文档的整体结构是什么？",
                    "文档按章节组织，包含背景介绍、方法说明与结论等部分。",
                ),
            ],
        )

        print_banner("测试完成")
        print("所有步骤已执行。检索结果见上方各步骤输出。")
        return 0

    except (FileNotFoundError, ValueError) as e:
        print(f"\n❌ 参数或文件错误: {e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"\n❌ 运行环境错误: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n❌ 未预期错误: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
