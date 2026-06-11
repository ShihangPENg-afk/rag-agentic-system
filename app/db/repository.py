import logging
import uuid
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.db.database import SessionLocal
from app.db.models import Document, QALog

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


def _qa_log_to_dict(log: QALog) -> dict[str, Any]:
    return {
        "id": log.id,
        "knowledge_base_id": str(log.document_id),
        "document_id": str(log.document_id),
        "question": log.question,
        "answer": log.answer,
        "mode": log.mode,
        "debug": log.debug,
        "created_at": log.created_at.isoformat(),
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


def record_qa_log(
    knowledge_base_id: str,
    question: str,
    answer: str,
    mode: str = "agent",
    debug: dict | None = None,
) -> None:
    db = SessionLocal()
    try:
        log = QALog(
            document_id=uuid.UUID(knowledge_base_id),
            question=question,
            answer=answer,
            mode=mode,
            debug=debug,
        )
        db.add(log)
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.warning("写入 qa_logs 表失败（不影响问答结果）: %s", e)
    except Exception as e:
        db.rollback()
        logger.warning("写入 qa_logs 表时发生异常（不影响问答结果）: %s", e)
    finally:
        db.close()


def list_recent_documents(limit: int = 50) -> list[dict[str, Any]]:
    db = SessionLocal()
    try:
        docs = (
            db.query(Document)
            .order_by(Document.created_at.desc())
            .limit(limit)
            .all()
        )
        return [_document_to_dict(doc) for doc in docs]
    except SQLAlchemyError as e:
        logger.warning("查询 documents 表失败: %s", e)
        return []
    except Exception as e:
        logger.warning("查询 documents 表时发生异常: %s", e)
        return []
    finally:
        db.close()


def list_qa_logs_by_knowledge_base(
    knowledge_base_id: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    db = SessionLocal()
    try:
        kb_uuid = uuid.UUID(knowledge_base_id)
        logs = (
            db.query(QALog)
            .filter(QALog.document_id == kb_uuid)
            .order_by(QALog.created_at.desc())
            .limit(limit)
            .all()
        )
        return [_qa_log_to_dict(log) for log in logs]
    except ValueError:
        logger.warning("无效的 knowledge_base_id: %s", knowledge_base_id)
        return []
    except SQLAlchemyError as e:
        logger.warning("查询 qa_logs 表失败: %s", e)
        return []
    except Exception as e:
        logger.warning("查询 qa_logs 表时发生异常: %s", e)
        return []
    finally:
        db.close()
