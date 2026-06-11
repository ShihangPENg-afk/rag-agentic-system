"""
通用工具函数
"""
import re
from difflib import SequenceMatcher
from typing import List

import requests

from config import MIN_CHUNK_LENGTH, NETWORK_CHECK_URL, NETWORK_TIMEOUT


def clean_blank_chunks(chunks: List[str]) -> List[str]:
    """过滤空内容、空白、过短文本块"""
    cleaned = []
    for c in chunks:
        s = c.strip()
        if not s:
            continue
        if len(s) >= MIN_CHUNK_LENGTH:
            cleaned.append(s)
    return cleaned


def calculate_similarity(a: str, b: str) -> float:
    """计算文本相似度，用于去重"""
    return SequenceMatcher(None, a, b).ratio()


def deduplicate_chunks(chunks: List[str]) -> List[str]:
    """文本去重"""
    from config import SIMILARITY_THRESHOLD

    chunks = clean_blank_chunks(chunks)
    unique_chunks = []

    for chunk in chunks:
        is_duplicate = False
        for unique in unique_chunks:
            sim = calculate_similarity(chunk, unique)
            if sim > SIMILARITY_THRESHOLD:
                is_duplicate = True
                break
        if not is_duplicate:
            unique_chunks.append(chunk)

    print(f"去重前{len(chunks)} -> 去重后{len(unique_chunks)}")
    return unique_chunks


def clean_raw_text(text: str) -> str:
    """原始文本清洗：去除多余空格换行"""
    if not text:
        return ""
    text = re.sub(r"\n+", "\n", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def check_network() -> bool:
    """检测网络连接"""
    try:
        requests.get(NETWORK_CHECK_URL, timeout=NETWORK_TIMEOUT)
        return True
    except Exception:
        return False