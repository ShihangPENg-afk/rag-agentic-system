from typing import Any, Dict, List, Literal, Optional, Tuple
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

class HistoryTurn(BaseModel):
    user: str
    assistant: str


class QuestionRequest(BaseModel):
    question: str
    knowledge_base_id: str
    document_id: Optional[str] = None
    collection_id: Optional[str] = None
    retriever_version: Literal["v1", "v2"] = "v1"
    top_k: int = Field(default=3, ge=1, le=20)
    use_rerank: bool = False
    session_id: Optional[UUID] = None
    history: List[HistoryTurn] = Field(default_factory=list)
    debug: bool = False

    @model_validator(mode="after")
    def normalize_document_filter(self):
        if self.document_id is None:
            self.document_id = self.knowledge_base_id
        elif self.document_id != self.knowledge_base_id:
            raise ValueError("document_id must match knowledge_base_id")
        return self


class AnswerResponse(BaseModel):
    answer: str
    confidence: Optional[float] = None
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    knowledge_base_id: str
    session_id: Optional[UUID] = None
    history: List[Tuple[str, str]] = Field(default_factory=list)
    debug: Optional[Dict[str, Any]] = None
    mode: str = "agent"

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "answer": "这份文档主要讲软件工程概述，包括软件的概念、分类及其特点。",
                "knowledge_base_id": "89a71a65-eabe-48ea-a48c-3391d0c2ecc5",
                "history": [
                    ["这份文档主要讲什么？", "这份文档主要讲软件工程概述，包括软件的概念、分类及其特点。"]
                ],
                "debug": {
                    "tool_trace": [
                        {
                            "tool_name": "retrieve_chunks",
                            "tool_input": {"query": "这份文档主要讲什么？"},
                            "tool_output_preview": "## 检索到的相关片段\n1. ..."
                        }
                    ],
                    "message_count": 4,
                },
                "mode": "agent",
            }
        }
    )


class SingleUploadResponse(BaseModel):
    knowledge_base_id: str
    collection_id: Optional[str] = None
    status: str
    message: str
    chunks_count: int
    filename: str


class BatchUploadResult(BaseModel):
    filename: str
    knowledge_base_id: Optional[str] = None
    collection_id: Optional[str] = None
    status: str
    message: str
    chunks_count: Optional[int] = None


class BatchUploadResponse(BaseModel):
    results: List[BatchUploadResult]
    total_uploaded: int
    total_failed: int


class DocumentRecord(BaseModel):
    id: str
    knowledge_base_id: str
    collection_id: Optional[str] = None
    filename: str
    content_type: Optional[str] = None
    file_size: Optional[int] = None
    content_hash: Optional[str] = None
    chunks_count: int
    status: str
    error_message: Optional[str] = None
    created_at: str
    updated_at: str


class DocumentsListResponse(BaseModel):
    total: int
    documents: List[DocumentRecord]


class QALogRecord(BaseModel):
    id: int
    knowledge_base_id: str
    document_id: str
    question: str
    answer: str
    mode: str
    debug: Optional[Dict[str, Any]] = None
    created_at: str


class QALogsListResponse(BaseModel):
    knowledge_base_id: str
    total: int
    qa_logs: List[QALogRecord]


class RetrievalRequest(BaseModel):
    query: str
    document_id: Optional[UUID] = None
    collection_id: Optional[UUID] = None
    retriever_version: Literal["v1", "v2"] = "v1"
    limit: int = Field(default=3, ge=1, le=20)
    top_k: Optional[int] = Field(default=None, ge=1, le=20)
    use_rerank: bool = False

    @model_validator(mode="after")
    def normalize_top_k(self):
        if self.top_k is not None:
            self.limit = self.top_k
        return self


class RetrievedChunkRecord(BaseModel):
    chunk_id: str
    document_id: str
    collection_id: Optional[str] = None
    score: float
    dense_score: Optional[float] = None
    bm25_score: Optional[float] = None
    final_score: Optional[float] = None
    rerank_score: Optional[float] = None
    source_metadata: Optional[Dict[str, Any]] = None
    content: str


class RetrievalResponse(BaseModel):
    total: int
    chunks: List[RetrievedChunkRecord]
