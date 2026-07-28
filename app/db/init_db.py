import os
from contextlib import contextmanager
from pathlib import Path

import app.models  # noqa: F401 — register SQLAlchemy models with Base.metadata
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.db.database import Base, DATABASE_URL, engine

ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def _temporary_database_url(url: str):
    original = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        yield
    finally:
        if original is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original


def _alembic_config() -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    return config


def _run_alembic_upgrade() -> None:
    url = engine.url.render_as_string(hide_password=False)
    with _temporary_database_url(url):
        command.upgrade(_alembic_config(), "head")


def create_tables() -> None:
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        _run_alembic_upgrade()
        return

    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    create_tables()
    print("Database tables created.")
