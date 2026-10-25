"""Shared test setup. pytest loads this file automatically.

Every test that asks for `client` gets an app wired to a brand-new, empty,
in-memory database, so tests never touch finance.db or each other.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, enable_sqlite_foreign_keys, get_db
from app.main import app


@pytest.fixture
def db_session():
    # StaticPool keeps one connection open. An in-memory SQLite database
    # disappears when its connection closes, so every session must share it.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", enable_sqlite_foreign_keys)
    Base.metadata.create_all(engine)

    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    with TestSession() as session:
        yield session

    engine.dispose()


@pytest.fixture
def client(db_session):
    # Dependency override: wherever a route asks for get_db, hand it the test session.
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
