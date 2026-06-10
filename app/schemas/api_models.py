from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, ConfigDict

class HistoryTurn(BaseModel):
    user: str
    assistant: str


class QuestionRequest(BaseModel):
    question: str
    knowledge_base_id: str
    history: List[HistoryTurn] = Field(default_factory=list)
    debug: bool = False

class AnswerResponse(BaseModel):
    answer: str
    knowledge_base_id: str
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
    status: str
    message: str
    chunks_count: int
    filename: str


class BatchUploadResult(BaseModel):
    filename: str
    knowledge_base_id: Optional[str] = None
    status: str
    message: str
    chunks_count: Optional[int] = None


class BatchUploadResponse(BaseModel):
    results: List[BatchUploadResult]
    total_uploaded: int
    total_failed: int