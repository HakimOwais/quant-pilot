"""Alembic migration environment. DB URL + metadata come from the app, not alembic.ini."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context

# Importing the ORM models registers their tables on Base.metadata for autogenerate.
from quant_pilot.adapters.persistence import models as _models  # noqa: F401
from quant_pilot.config.settings import get_settings
from quant_pilot.db.base import Base, get_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with get_engine().connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
