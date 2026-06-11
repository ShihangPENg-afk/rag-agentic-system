"""
索引构建服务：切块、向量化、从PDF初始化索引
"""
from typing import List, Tuple, Optional

import dashscope
from dashscope.embeddings import TextEmbedding
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import (
    API_KEY,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    FIXED_DIMENSION,
)
from app.services.pdf_service import read_pdf
from app.vectordb.faiss_store import build_faiss_index
from utils.utils import check_network, deduplicate_chunks

dashscope.api_key = API_KEY


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


def get_embeddings(texts: List[str]) -> Tuple[List[list], int]:
    """获取文本向量"""
    if not texts:
        print("❌ 无文本内容，无法生成向量")
        return [], FIXED_DIMENSION

    if not check_network():
        print("❌ 错误：当前网络断开，无法调用向量API")
        return [], FIXED_DIMENSION

    batch_size = 20
    all_embeddings = []
    dimension = FIXED_DIMENSION

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        print(f"🔍 生成第 {i // batch_size + 1} 批向量...")

        try:
            resp = TextEmbedding.call(
                model=TextEmbedding.Models.text_embedding_v1,
                input=batch,
            )

            if resp.status_code != 200:
                print(f"❌ API调用失败: {resp.message}")
                continue

            embeddings = []
            for item in resp.output["embeddings"]:
                embedding = item["embedding"]
                if len(embedding) == FIXED_DIMENSION:
                    embeddings.append(embedding)

            all_embeddings.extend(embeddings)
            print(f"✅ 本批生成 {len(embeddings)} 个向量，维度：{dimension}")

        except Exception as e:
            print(f"❌ 向量生成失败：{str(e)}")
            print("💡 可能原因：网络异常、API限流、API密钥错误")
            try:
                if "resp" in locals():
                    print(f"🔍 接口返回状态：{resp.status_code}")
                    print(f"🔍 接口返回消息：{resp.message}")
            except Exception:
                pass
            continue

    print(f"\n✅ 总向量数：{len(all_embeddings)}")
    print(f"✅ 向量维度：{dimension}")

    return all_embeddings, dimension


def init_index_from_pdf(pdf_path: str):
    """从 PDF 初始化向量索引和文本块"""
    try:
        pdf_text = read_pdf(pdf_path)
        if not pdf_text:
            print("❌ 无法构建知识库：PDF无有效内容")
            return None, []

        chunks = split_text(pdf_text)
        if not chunks:
            print("❌ 无法构建知识库：无有效文本切块")
            return None, []

        embeddings, dimension = get_embeddings(chunks)
        if len(embeddings) == 0 or dimension != FIXED_DIMENSION:
            print(f"❌ 无法构建知识库：无有效 {FIXED_DIMENSION} 维向量")
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