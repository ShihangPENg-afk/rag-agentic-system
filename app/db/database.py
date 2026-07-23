"""Backward-compatible database import path."""

from app.db.base import Base
from app.db.session import DATABASE_URL, SessionLocal, engine, get_db

__all__ = ["Base", "DATABASE_URL", "SessionLocal", "engine", "get_db"]
