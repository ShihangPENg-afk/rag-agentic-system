import app.models.user  # noqa: F401 — register User model for Document FK resolution
import app.models.document  # noqa: F401 — register Document model with Base.metadata
import app.models.qa_log  # noqa: F401 — register QALog model with Base.metadata
from app.db.database import Base, engine


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    create_tables()
    print("Database tables created.")
