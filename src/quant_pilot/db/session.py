"""Request-scoped DB session dependency for FastAPI."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from quant_pilot.db.base import get_sessionmaker


def get_db() -> Iterator[Session]:
    """Yield a transactional session; commit on success, roll back on error."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
