import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.chat import ChatSession, Message


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _session_to_dict(session: ChatSession) -> dict:
    return {
        "id": str(session.id),
        "user_id": str(session.user_id),
        "title": session.title,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }


def _message_to_dict(message: Message) -> dict:
    return {
        "id": str(message.id),
        "session_id": str(message.session_id),
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }


def create_chat_session(
    user_id: str | uuid.UUID,
    title: str,
    db: Session | None = None,
) -> dict:
    owns_session = db is None
    db = db or SessionLocal()
    try:
        session = ChatSession(user_id=uuid.UUID(str(user_id)), title=title[:255])
        db.add(session)
        db.commit()
        db.refresh(session)
        return _session_to_dict(session)
    finally:
        if owns_session:
            db.close()


def get_chat_session_by_user(
    session_id: str | uuid.UUID,
    user_id: str | uuid.UUID,
    db: Session | None = None,
) -> dict | None:
    owns_session = db is None
    db = db or SessionLocal()
    try:
        stmt = select(ChatSession).where(
            ChatSession.id == uuid.UUID(str(session_id)),
            ChatSession.user_id == uuid.UUID(str(user_id)),
        )
        session = db.execute(stmt).scalar_one_or_none()
        return _session_to_dict(session) if session is not None else None
    finally:
        if owns_session:
            db.close()


def list_chat_sessions_by_user(
    user_id: str | uuid.UUID,
    limit: int = 50,
) -> list[dict]:
    db = SessionLocal()
    try:
        stmt = (
            select(ChatSession)
            .where(ChatSession.user_id == uuid.UUID(str(user_id)))
            .order_by(ChatSession.updated_at.desc())
            .limit(limit)
        )
        return [_session_to_dict(item) for item in db.execute(stmt).scalars().all()]
    finally:
        db.close()


def create_message(
    session_id: str | uuid.UUID,
    role: str,
    content: str,
    db: Session | None = None,
) -> dict:
    owns_session = db is None
    db = db or SessionLocal()
    try:
        message = Message(
            session_id=uuid.UUID(str(session_id)),
            role=role,
            content=content,
        )
        db.add(message)
        chat_session = db.get(ChatSession, uuid.UUID(str(session_id)))
        if chat_session is not None:
            chat_session.updated_at = _utcnow()
        db.commit()
        db.refresh(message)
        return _message_to_dict(message)
    finally:
        if owns_session:
            db.close()


def list_messages_by_session_and_user(
    session_id: str | uuid.UUID,
    user_id: str | uuid.UUID,
    limit: int = 200,
) -> list[dict] | None:
    db = SessionLocal()
    try:
        session_stmt = select(ChatSession.id).where(
            ChatSession.id == uuid.UUID(str(session_id)),
            ChatSession.user_id == uuid.UUID(str(user_id)),
        )
        if db.execute(session_stmt).scalar_one_or_none() is None:
            return None

        stmt = (
            select(Message)
            .where(Message.session_id == uuid.UUID(str(session_id)))
            .order_by(Message.created_at.asc())
            .limit(limit)
        )
        return [_message_to_dict(item) for item in db.execute(stmt).scalars().all()]
    finally:
        db.close()
