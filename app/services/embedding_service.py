from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import List, Tuple

import dashscope
from dashscope.embeddings import TextEmbedding

from app.core.config import (
    API_KEY,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_PROVIDER,
    FIXED_DIMENSION,
)
from utils.utils import check_network

dashscope.api_key = API_KEY


class EmbeddingProvider(ABC):
    name: str
    model_name: str
    dimension: int = FIXED_DIMENSION

    @abstractmethod
    def embed_texts(self, texts: List[str]) -> Tuple[List[list], int]:
        """Return embeddings and embedding dimension for the provided texts."""


class DashScopeEmbeddingProvider(EmbeddingProvider):
    name = "dashscope"

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME):
        self.model_name = model_name

    def embed_texts(self, texts: List[str]) -> Tuple[List[list], int]:
        if not texts:
            print("❌ 无文本内容，无法生成向量")
            return [], self.dimension

        if not API_KEY:
            print("❌ 缺少 DASHSCOPE_API_KEY，无法调用 DashScope 向量 API")
            return [], self.dimension

        if not check_network():
            print("❌ 错误：当前网络断开，无法调用向量API")
            return [], self.dimension

        batch_size = 20
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            print(f"🔍 生成第 {i // batch_size + 1} 批向量...")

            try:
                resp = TextEmbedding.call(
                    model=self.model_name,
                    input=batch,
                )

                if resp.status_code != 200:
                    print(f"❌ API调用失败: {resp.message}")
                    continue

                embeddings = []
                for item in resp.output["embeddings"]:
                    embedding = item["embedding"]
                    if len(embedding) == self.dimension:
                        embeddings.append(embedding)

                all_embeddings.extend(embeddings)
                print(f"✅ 本批生成 {len(embeddings)} 个向量，维度：{self.dimension}")

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
        print(f"✅ 向量维度：{self.dimension}")

        return all_embeddings, self.dimension


class FakeEmbeddingProvider(EmbeddingProvider):
    name = "fake"
    model_name = "fake-hash-embedding"

    def embed_texts(self, texts: List[str]) -> Tuple[List[list], int]:
        if not texts:
            return [], self.dimension
        return [self._embed_one(text) for text in texts], self.dimension

    def _embed_one(self, text: str) -> list[float]:
        digest = hashlib.sha256(str(text).encode("utf-8")).digest()
        values = []
        counter = 0
        while len(values) < self.dimension:
            block = hashlib.sha256(digest + counter.to_bytes(4, "big")).digest()
            for byte in block:
                values.append((byte / 127.5) - 1.0)
                if len(values) == self.dimension:
                    break
            counter += 1

        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]


@lru_cache(maxsize=1)
def get_embedding_provider() -> EmbeddingProvider:
    if EMBEDDING_PROVIDER == "fake":
        return FakeEmbeddingProvider()
    if EMBEDDING_PROVIDER == "dashscope":
        return DashScopeEmbeddingProvider()
    raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {EMBEDDING_PROVIDER}")


def get_embedding_model_name() -> str:
    return get_embedding_provider().model_name


def get_embeddings(texts: List[str]) -> Tuple[List[list], int]:
    return get_embedding_provider().embed_texts(texts)
