"""索引构建服务：切块、从PDF初始化索引。"""
from typing import List

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import (
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    FIXED_DIMENSION,
)
from app.services.embedding_service import get_embeddings
from app.services.pdf_service import read_pdf
from app.vectordb.faiss_store import build_faiss_index
from utils.utils import deduplicate_chunks


def split_text(long_text: str) -> List[str]:
    """文本拆分"""
    if not long_text:
        print("ℹ️ 无有效文本，跳过切块")
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", "。", "！", "？", " "],
    )

    chunks = splitter.split_text(long_text)
    chunks = deduplicate_chunks(chunks)

    print(f"✅ 文本拆分完成，共 {len(chunks)} 块")
    return chunks


def build_chunks_and_embeddings_from_pdf(pdf_path: str):
    """从 PDF 提取文本、切块并生成向量。"""
    try:
        pdf_text = read_pdf(pdf_path)
        if not pdf_text:
            print("❌ 无法构建知识库：PDF无有效内容")
            return [], [], FIXED_DIMENSION

        chunks = split_text(pdf_text)
        if not chunks:
            print("❌ 无法构建知识库：无有效文本切块")
            return [], [], FIXED_DIMENSION

        embeddings, dimension = get_embeddings(chunks)
        if len(embeddings) == 0 or dimension != FIXED_DIMENSION:
            print(f"❌ 无法构建知识库：无有效 {FIXED_DIMENSION} 维向量")
            return [], [], dimension

        return chunks, embeddings, dimension

    except Exception as e:
        print(f"❌ 知识库初始化异常：{str(e)}")
        return [], [], FIXED_DIMENSION


def init_index_from_pdf(pdf_path: str):
    """从 PDF 初始化 FAISS 向量索引和文本块。"""
    try:
        chunks, embeddings, dimension = build_chunks_and_embeddings_from_pdf(pdf_path)
        if not chunks or not embeddings:
            return None, []

        index = build_faiss_index(embeddings, dimension)
        if index is None:
            print("❌ 向量库建立失败")
            return None, []

        print(f"✅ 向量库建立完成，共 {index.ntotal} 条向量，维度 {dimension}")
        return index, chunks

    except Exception as e:
        print(f"❌ 知识库初始化异常：{str(e)}")
        return None, []
