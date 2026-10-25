"""Database connection: the engine, the session factory, and the base class for models."""

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# The database file sits next to the backend folder by default.
# Set FINANCE_DB_URL to point somewhere else (tests use an in-memory database).
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "finance.db"
DATABASE_URL = os.environ.get("FINANCE_DB_URL", f"sqlite:///{DEFAULT_DB_PATH}")

engine = create_engine(DATABASE_URL)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    # SQLite ignores foreign keys unless you switch them on for every connection.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Every model inherits from this, so Alembic can find all tables in one place."""


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed afterwards."""
    with SessionLocal() as session:
        yield session
