import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import SessionLocal
from app.models.document import Document

logger = logging.getLogger(__name__)


def _document_to_dict(doc: Document) -> dict[str, Any]:
    return {
        "id": str(doc.id),
        "knowledge_base_id": str(doc.id),
        "user_id": str(doc.user_id) if doc.user_id is not None else None,
        "filename": doc.filename,
        "content_type": doc.content_type,
        "chunks_count": doc.chunks_count,
        "status": doc.status,
        "created_at": doc.created_at.isoformat(),
        "updated_at": doc.updated_at.isoformat(),
    }


def record_document(
    knowledge_base_id: str,
    filename: str,
    chunks_count: int,
    user_id: str | uuid.UUID | None = None,
    content_type: str = "application/pdf",
) -> None:
    db = SessionLocal()
    try:
        doc = Document(
            id=uuid.UUID(knowledge_base_id),
            user_id=uuid.UUID(str(user_id)) if user_id is not None else None,
            filename=filename,
            content_type=content_type,
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


def get_document_by_id_and_user(
    document_id: str | uuid.UUID,
    user_id: str | uuid.UUID,
) -> dict[str, Any] | None:
    db = SessionLocal()
    try:
        stmt = select(Document).where(
            Document.id == uuid.UUID(str(document_id)),
            Document.user_id == uuid.UUID(str(user_id)),
        )
        doc = db.execute(stmt).scalar_one_or_none()
        return _document_to_dict(doc) if doc is not None else None
    except ValueError:
        return None
    except SQLAlchemyError as e:
        logger.warning("按用户查询 document 失败: %s", e)
        return None
    except Exception as e:
        logger.warning("按用户查询 document 时发生异常: %s", e)
        return None
    finally:
        db.close()


def get_document_by_id(document_id: str | uuid.UUID) -> dict[str, Any] | None:
    db = SessionLocal()
    try:
        stmt = select(Document).where(Document.id == uuid.UUID(str(document_id)))
        doc = db.execute(stmt).scalar_one_or_none()
        return _document_to_dict(doc) if doc is not None else None
    except ValueError:
        return None
    except SQLAlchemyError as e:
        logger.warning("查询 document 失败: %s", e)
        return None
    except Exception as e:
        logger.warning("查询 document 时发生异常: %s", e)
        return None
    finally:
        db.close()


def list_recent_documents_by_user(
    user_id: str | uuid.UUID,
    limit: int = 50,
) -> list[dict[str, Any]]:
    db = SessionLocal()
    try:
        stmt = (
            select(Document)
            .where(Document.user_id == uuid.UUID(str(user_id)))
            .order_by(Document.created_at.desc())
            .limit(limit)
        )
        docs = db.execute(stmt).scalars().all()
        return [_document_to_dict(doc) for doc in docs]
    except SQLAlchemyError as e:
        logger.warning("按用户查询 documents 表失败: %s", e)
        return []
    except Exception as e:
        logger.warning("按用户查询 documents 表时发生异常: %s", e)
        return []
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
