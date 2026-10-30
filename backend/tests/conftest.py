"""Shared test setup. pytest loads this file automatically.

Every test gets a brand-new, empty, in-memory database, so tests never touch
finance.db or each other.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.clock import get_today
from app.db import Base, enable_sqlite_foreign_keys, get_db
from app.main import app


@pytest.fixture
def session_factory():
    # StaticPool keeps one connection open. An in-memory SQLite database
    # disappears when its connection closes, so every session must share it.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", enable_sqlite_foreign_keys)
    Base.metadata.create_all(engine)

    yield sessionmaker(bind=engine, expire_on_commit=False)

    engine.dispose()


@pytest.fixture
def db_session(session_factory):
    """For tests that set up rows directly, skipping the API."""
    with session_factory() as session:
        yield session


@pytest.fixture
def client(session_factory):
    # Dependency override: each request gets its own fresh session, like the real app.
    def get_test_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = get_test_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def today(client):
    """Freeze "today" at Oct 23, 2026 for endpoints that use the Today dependency."""
    app.dependency_overrides[get_today] = lambda: date(2026, 10, 23)
    return date(2026, 10, 23)
