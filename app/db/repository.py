"""Backward-compatible repository import path."""

from app.repositories.document_repository import list_recent_documents, record_document
from app.repositories.qa_log_repository import (
    list_qa_logs_by_knowledge_base,
    record_qa_log,
)

__all__ = [
    "list_qa_logs_by_knowledge_base",
    "list_recent_documents",
    "record_document",
    "record_qa_log",
]
