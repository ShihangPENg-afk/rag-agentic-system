import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


def get_user_by_email(db: Session, email: str) -> User | None:
    stmt = select(User).where(User.email == email.lower())
    return db.execute(stmt).scalar_one_or_none()


def get_user_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    stmt = select(User).where(User.id == user_id)
    return db.execute(stmt).scalar_one_or_none()


def create_user(db: Session, email: str, hashed_password: str) -> User:
    user = User(email=email.lower(), hashed_password=hashed_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
