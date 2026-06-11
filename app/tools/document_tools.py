"""
文档结构工具：
- list_headings_tool：提取文档中的章节/小节标题（启发式增强版）
- count_tables_tool：统计文档中的表格迹象数量（启发式增强版）
"""

from __future__ import annotations

import re
from typing import List

from app.services.kb_registry import get_knowledge_base
from app.tools.common import kb_not_found_message


def _unique_keep_order(items: List[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        norm = item.strip()
        if not norm:
            continue
        if norm not in seen:
            seen.add(norm)
            result.append(norm)
    return result


def _normalize_text(text: str) -> str:
    text = str(text).replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _sanitize_heading(text: str) -> str:
    """
    对标题候选做轻量清洗：
    - 去掉多余空格
    - 去掉后面嵌入的下一层编号
    - 去掉明显混入的正文尾巴
    """
    text = _normalize_text(text)

    # 如果章节标题后面又接了 1.1 / 2.1 这类编号，截断
    text = re.sub(r"\s+\d+\.\d.*$", "", text)

    # 如果混入正文，尽量在常见断点前截断
    text = re.split(r"[。；：:]", text, maxsplit=1)[0]

    # 常见正文起始标记，命中后截断
    body_markers = [
        " 软件是",
        " 软件工程是",
        " 需求分析是",
        " 需求获取是",
        " 模型是",
        " 方法是",
        " 经过",
        " 随着",
        " 形成",
    ]
    for marker in body_markers:
        if marker in text and len(text) > 10:
            text = text.split(marker, 1)[0]
            break

    return text.strip(" -—")


def list_headings_tool(knowledge_base_id: str, limit: int = 20) -> str:
    """
    启发式提取标题。
    当前仍基于 chunks 文本内容做规则识别，不依赖原始 PDF 目录结构。
    """
    rag = get_knowledge_base(knowledge_base_id)
    if rag is None:
        return kb_not_found_message(knowledge_base_id)

    if not rag.chunks:
        return "## 章节标题\n未找到可用文本块。"

    headings: List[str] = []

    # 常见标题模式（启发式）
    chapter_pattern = re.compile(r"(第\s*\d+\s*章[^\n]{1,40})")
    section_pattern = re.compile(r"(\d+(?:\.\d+){1,2}\s*[^\n]{1,40})")

    for chunk in rag.chunks:
        chunk = _normalize_text(chunk)

        chapter_matches = chapter_pattern.findall(chunk)
        section_matches = section_pattern.findall(chunk)

        for m in chapter_matches:
            cleaned = _sanitize_heading(m)
            if 4 <= len(cleaned) <= 40:
                headings.append(cleaned)

        for m in section_matches:
            cleaned = _sanitize_heading(m)
            if 4 <= len(cleaned) <= 40:
                headings.append(cleaned)

        # 再做一次按行扫描补充
        for raw_line in chunk.splitlines():
            line = _sanitize_heading(raw_line)
            if 3 <= len(line) <= 40:
                if line.startswith("第") and "章" in line:
                    headings.append(line)
                elif re.match(r"^\d+(?:\.\d+){1,2}\s*", line):
                    headings.append(line)

    headings = _unique_keep_order(headings)

    if limit > 0:
        headings = headings[:limit]

    if not headings:
        return "## 章节标题\n未能从当前知识库中识别出明显标题（可能是 PDF 提取结果较连续，标题与正文混在一起）。"

    lines = ["## 章节标题"]
    for i, h in enumerate(headings, 1):
        lines.append(f"{i}. {h}")
    return "\n".join(lines)


def count_tables_tool(knowledge_base_id: str) -> str:
    """
    启发式统计“表格迹象”数量。
    说明：这不是精确表格解析，只是根据文本模式粗略估计。
    """
    rag = get_knowledge_base(knowledge_base_id)
    if rag is None:
        return kb_not_found_message(knowledge_base_id)

    if not rag.chunks:
        return "## 表格统计\n知识库为空，无法统计。"

    table_title_hits = 0
    pipe_hits = 0
    column_like_hits = 0
    examples: List[str] = []

    table_title_pattern = re.compile(r"(表\s*\d+|Table\s*\d+)", re.IGNORECASE)
    pipe_pattern = re.compile(r"\|.+\|")
    multi_space_columns_pattern = re.compile(r"\S+\s{2,}\S+\s{2,}\S+")

    for chunk in rag.chunks:
        chunk = _normalize_text(chunk)

        title_matches = table_title_pattern.findall(chunk)
        if title_matches:
            table_title_hits += len(title_matches)
            examples.extend(title_matches)

        for line in chunk.splitlines():
            line = _normalize_text(line)
            if not line:
                continue

            if pipe_pattern.search(line):
                pipe_hits += 1
                examples.append(line[:60])
            elif multi_space_columns_pattern.search(line):
                column_like_hits += 1
                examples.append(line[:60])

    examples = _unique_keep_order(examples)[:5]

    estimated_table_count = max(
        table_title_hits,
        min(table_title_hits + pipe_hits // 2 + column_like_hits // 2, 50),
    )

    if table_title_hits >= 2:
        confidence = "高"
    elif table_title_hits >= 1 or pipe_hits >= 2 or column_like_hits >= 2:
        confidence = "中"
    else:
        confidence = "低"

    lines = ["## 表格统计"]
    lines.append(f"estimated_table_count: {estimated_table_count}")
    lines.append(f"confidence: {confidence}")
    lines.append(f"table_title_hits: {table_title_hits}")
    lines.append(f"pipe_hits: {pipe_hits}")
    lines.append(f"column_like_hits: {column_like_hits}")
    lines.append("说明：这是基于文本模式的粗略统计，不等于精确表格数量。")

    if examples:
        lines.append("examples:")
        for i, ex in enumerate(examples, 1):
            lines.append(f"{i}. {ex}")

    return "\n".join(lines)