"""SQLAlchemy engine, session factory, and declarative Base.

Engine creation is lazy/cached so importing this module never opens a connection
(keeps the app importable without a running database — e.g. in unit tests).
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from quant_pilot.config.settings import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models. Alembic autogenerate targets Base.metadata."""


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True, future=True)


@lru_cache
def get_sessionmaker() -> sessionmaker:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False, future=True)
