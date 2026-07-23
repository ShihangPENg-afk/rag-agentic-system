import app.models  # noqa: F401 — register SQLAlchemy models with Base.metadata
from app.db.database import Base, engine
from sqlalchemy import text


def create_tables() -> None:
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    create_tables()
    print("Database tables created.")
