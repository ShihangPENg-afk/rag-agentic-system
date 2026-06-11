"""
RAG 核心薄封装
"""
from app.services.index_service import init_index_from_pdf
from app.services.chat_service import answer_with_index


class RAGSystem:
    def __init__(self):
        self.index = None
        self.chunks = []

    def init_from_pdf(self, pdf_path: str) -> bool:
        """从 PDF 初始化 RAG 系统"""
        index, chunks = init_index_from_pdf(pdf_path)
        if index is None or not chunks:
            self.index = None
            self.chunks = []
            return False

        self.index = index
        self.chunks = chunks
        return True

    def query(self, user_query: str, history=None, max_history: int = 3):
        """查询接口"""
        return answer_with_index(
            index=self.index,
            chunks=self.chunks,
            user_query=user_query,
            history=history,
            max_history=max_history,
        )