"""
FAISS 向量索引
"""

from typing import List, Optional

import faiss
import numpy as np

def build_faiss_index(embeddings: List[List], dimension: int) -> Optional[faiss.IndexFlatL2]:
    """构建 FAISS 向量索引"""
    if not embeddings:
        return None

    if dimension <= 0:
        raise ValueError("向量纬度必须大于0")

    index = faiss.IndexFlatL2(dimension)
    index.add(np.array(embeddings, dtype=np.float32))
    return index
    