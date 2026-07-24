from pydantic import BaseModel, Field
from typing import List, Tuple, Optional

class ChatState(BaseModel):
    """
    对话状态模型(Pydantic 版本）
    """
    # 知识库ID
    knowledge_base_id: str
    # 当前用户 ID，用于 pgvector 检索权限过滤
    user_id: Optional[str] = None
    # 可选集合 ID，用于 pgvector collection 过滤
    collection_id: Optional[str] = None
    # 检索版本：v1 使用现有 baseline，v2 使用 hybrid retrieval
    retriever_version: str = "v1"
    # 本轮检索返回的 chunk 数量
    top_k: int = 3
    # 是否对 hybrid retrieval 候选结果做二次排序
    use_rerank: bool = False
    # 用户问题
    user_query: str
    # 对话历史
    history_pairs: List[Tuple[str, str]] = Field(default_factory=list)
    # 检索到的文本块
    retrieved_chunks: List[str] = Field(default_factory=list)
    # 模型回答
    answer: str = ""
    
 
    def append_history(self, question: str, answer: str) -> None:
        """
        追加对话历史
        """
        self.history_pairs.append((question,answer))
