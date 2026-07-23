import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pgvector.sqlalchemy import Vector
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_DB_DIR = None
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
if TEST_DATABASE_URL is None:
    TEST_DB_DIR = tempfile.TemporaryDirectory(prefix="rag-agentic-system-tests-")
    TEST_DB_PATH = Path(TEST_DB_DIR.name) / "test.db"
    TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH}"

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["EMBEDDING_PROVIDER"] = "fake"
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(32)"


@compiles(Vector, "sqlite")
def _compile_vector_sqlite(type_, compiler, **kw):
    return "JSON"


from app.db import database as database_module  # noqa: E402
from app.db import init_db as init_db_module  # noqa: E402
from app.db import session as session_module  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ChatSession, Document, Message, QALog, User  # noqa: E402


IS_SQLITE_TEST_DB = TEST_DATABASE_URL.startswith("sqlite")
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False} if IS_SQLITE_TEST_DB else {},
    pool_pre_ping=True,
)


if IS_SQLITE_TEST_DB:

    @event.listens_for(test_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)

session_module.engine = test_engine
database_module.engine = test_engine
init_db_module.engine = test_engine
session_module.SessionLocal.configure(bind=test_engine)


@pytest.fixture(autouse=True)
def reset_test_database():
    app.dependency_overrides.clear()
    if not IS_SQLITE_TEST_DB:
        with test_engine.begin() as connection:
            connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def user_password():
    return "TestPassword123!"


@pytest.fixture
def register_user(client, user_password):
    def _register(email: str, password: str = user_password) -> dict:
        response = client.post(
            "/auth/register",
            json={"email": email, "password": password},
        )
        assert response.status_code == 200, response.text
        return response.json()

    return _register


@pytest.fixture
def auth_headers(client, user_password):
    def _headers(email: str, password: str = user_password) -> dict[str, str]:
        response = client.post(
            "/auth/login",
            json={"email": email, "password": password},
        )
        assert response.status_code == 200, response.text
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _headers


@pytest.fixture
def create_document(db_session):
    def _create_document(
        user_id: str | uuid.UUID,
        filename: str = "sample.pdf",
        chunks_count: int = 3,
        status: str = "ready",
    ) -> Document:
        document = Document(
            user_id=uuid.UUID(str(user_id)),
            filename=filename,
            content_type="application/pdf",
            chunks_count=chunks_count,
            status=status,
        )
        db_session.add(document)
        db_session.commit()
        db_session.refresh(document)
        return document

    return _create_document


@pytest.fixture
def create_chat_session(db_session):
    def _create_chat_session(
        user_id: str | uuid.UUID,
        title: str = "Test chat",
    ) -> ChatSession:
        chat_session = ChatSession(user_id=uuid.UUID(str(user_id)), title=title)
        db_session.add(chat_session)
        db_session.commit()
        db_session.refresh(chat_session)
        return chat_session

    return _create_chat_session


@pytest.fixture
def create_message(db_session):
    def _create_message(
        session_id: str | uuid.UUID,
        role: str = "user",
        content: str = "hello",
    ) -> Message:
        message = Message(
            session_id=uuid.UUID(str(session_id)),
            role=role,
            content=content,
        )
        db_session.add(message)
        db_session.commit()
        db_session.refresh(message)
        return message

    return _create_message


@pytest.fixture
def create_qa_log(db_session):
    def _create_qa_log(
        document_id: str | uuid.UUID,
        question: str = "What is this document about?",
        answer: str = "A mocked answer.",
        mode: str = "agent",
    ) -> QALog:
        qa_log = QALog(
            document_id=uuid.UUID(str(document_id)),
            question=question,
            answer=answer,
            mode=mode,
            debug={"source": "pytest"},
        )
        db_session.add(qa_log)
        db_session.commit()
        db_session.refresh(qa_log)
        return qa_log

    return _create_qa_log
