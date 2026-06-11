#!/usr/bin/env python3
"""
文档工具本地测试脚本

用途：
1. 构建知识库
2. 测试 list_headings_tool
3. 测试 count_tables_tool
4. 测试 retrieve_chunks_tool（做对照）

用法：
    python test_document_tools.py test.pdf
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.services.upload_service import create_knowledge_base_from_saved_pdf
from app.tools.document_tools import list_headings_tool, count_tables_tool
from app.tools.retrieval_tools import retrieve_chunks_tool


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


def build_knowledge_base(pdf_path: Path) -> str:
    print_banner("步骤 1 / 构建知识库")
    print(f"PDF 路径: {pdf_path}")
    print(f"文件名:   {pdf_path.name}")

    result = create_knowledge_base_from_saved_pdf(
        str(pdf_path),
        pdf_path.name,
    )

    kb_id = result["knowledge_base_id"]
    print(f"✅ {result['message']}")
    print(f"knowledge_base_id: {kb_id}")
    print(f"chunks_count:      {result['chunks_count']}")
    return kb_id


def main() -> int:
    parser = argparse.ArgumentParser(description="文档工具本地测试脚本")
    parser.add_argument("pdf_path", nargs="?", default="test.pdf", help="PDF 文件路径")
    args = parser.parse_args()

    try:
        pdf_path = resolve_pdf_path(args.pdf_path)
        assert_pdf_magic(pdf_path)

        kb_id = build_knowledge_base(pdf_path)

        print_banner("步骤 2 / 测试 list_headings_tool")
        print(list_headings_tool(kb_id))

        print_banner("步骤 3 / 测试 count_tables_tool")
        print(count_tables_tool(kb_id))

        print_banner("步骤 4 / 测试 retrieve_chunks_tool")
        print(
            retrieve_chunks_tool(
                knowledge_base_id=kb_id,
                user_query="这份文档主要讲什么？",
                history=[],
            )
        )

        print_banner("测试完成")
        print("✅ 文档工具测试已执行完成")
        return 0

    except (FileNotFoundError, ValueError) as e:
        print(f"\n❌ 参数或文件错误: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n❌ 未预期错误: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())