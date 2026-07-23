from datetime import datetime, timedelta, timezone
import base64
import hashlib
from uuid import UUID

import bcrypt
from jose import JWTError, jwt

from app.core.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    JWT_SECRET_KEY,
)


def hash_password(password: str) -> str:
    digest = _password_digest(password)
    hashed = bcrypt.hashpw(digest, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    digest = _password_digest(plain_password)
    return bcrypt.checkpw(digest, hashed_password.encode("utf-8"))


def _password_digest(password: str) -> bytes:
    raw = password.encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return base64.b64encode(digest)


def create_access_token(subject: UUID | str, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": str(subject),
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise ValueError("Invalid token") from exc
