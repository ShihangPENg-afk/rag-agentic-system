from pydantic import BaseModel, Field
from typing import List, Tuple, Optional

class ChatState(BaseModel):
    """
    对话状态模型(Pydantic 版本）
    """
    # 知识库ID
    knowledge_base_id: str
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
