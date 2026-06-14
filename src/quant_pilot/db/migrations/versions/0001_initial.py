"""initial schema: strategy_configs, backtest_runs, audit_events, instruments, universe_membership

Revision ID: 0001
Revises:
Create Date: 2026-06-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strategy_configs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("strategy_type", sa.String(length=50), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "strategy_config_id",
            sa.String(length=32),
            sa.ForeignKey("strategy_configs.id"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("artifacts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_backtest_runs_status", "backtest_runs", ["status"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_audit_events_ts", "audit_events", ["ts"])

    op.create_table(
        "instruments",
        sa.Column("symbol", sa.String(length=32), primary_key=True),
        sa.Column("exchange", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("sector", sa.String(length=100), nullable=True),
        sa.Column("has_liquid_ssf", sa.Boolean(), nullable=False),
        sa.Column("lot_size", sa.Integer(), nullable=True),
    )

    op.create_table(
        "universe_membership",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("index", sa.String(length=50), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
    )
    op.create_index("ix_universe_index_symbol", "universe_membership", ["index", "symbol"])
    op.create_index("ix_universe_index_from", "universe_membership", ["index", "effective_from"])


def downgrade() -> None:
    op.drop_index("ix_universe_index_from", table_name="universe_membership")
    op.drop_index("ix_universe_index_symbol", table_name="universe_membership")
    op.drop_table("universe_membership")
    op.drop_table("instruments")
    op.drop_index("ix_audit_events_ts", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_backtest_runs_status", table_name="backtest_runs")
    op.drop_table("backtest_runs")
    op.drop_table("strategy_configs")
