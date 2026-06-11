from app.db import models  # noqa: F401 — register ORM models with Base.metadata
from app.db.database import Base, engine


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    create_tables()
    print("Database tables created.")
