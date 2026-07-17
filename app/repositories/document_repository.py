import logging
import uuid
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.db.database import SessionLocal
from app.models.document import Document

logger = logging.getLogger(__name__)


def _document_to_dict(doc: Document) -> dict[str, Any]:
    return {
        "id": str(doc.id),
        "knowledge_base_id": str(doc.id),
        "filename": doc.filename,
        "chunks_count": doc.chunks_count,
        "status": doc.status,
        "created_at": doc.created_at.isoformat(),
        "updated_at": doc.updated_at.isoformat(),
    }


def record_document(knowledge_base_id: str, filename: str, chunks_count: int) -> None:
    db = SessionLocal()
    try:
        doc = Document(
            id=uuid.UUID(knowledge_base_id),
            filename=filename,
            chunks_count=chunks_count,
            status="ready",
        )
        db.add(doc)
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.warning("写入 documents 表失败（不影响知识库构建）: %s", e)
    except Exception as e:
        db.rollback()
        logger.warning("写入 documents 表时发生异常（不影响知识库构建）: %s", e)
    finally:
        db.close()


def list_recent_documents(limit: int = 50) -> list[dict[str, Any]]:
    db = SessionLocal()
    try:
        docs = db.query(Document).order_by(Document.created_at.desc()).limit(limit).all()
        return [_document_to_dict(doc) for doc in docs]
    except SQLAlchemyError as e:
        logger.warning("查询 documents 表失败: %s", e)
        return []
    except Exception as e:
        logger.warning("查询 documents 表时发生异常: %s", e)
        return []
    finally:
        db.close()
