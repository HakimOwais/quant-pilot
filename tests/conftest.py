from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from quant_pilot.adapters.persistence import models  # noqa: F401  (register tables)
from quant_pilot.api.main import create_app
from quant_pilot.db.base import Base


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def session() -> Iterator[Session]:
    """In-memory SQLite session with the full schema created from ORM metadata.

    StaticPool + check_same_thread=False share one connection across threads, so the FastAPI
    TestClient (which runs sync endpoints in a worker thread) hits the same in-memory DB.
    """
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    sess = maker()
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()
