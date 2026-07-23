"""Backward-compatible ORM model import path."""

from app.models import Chunk, ChunkEmbedding, Collection, Document, QALog

__all__ = ["Chunk", "ChunkEmbedding", "Collection", "Document", "QALog"]
