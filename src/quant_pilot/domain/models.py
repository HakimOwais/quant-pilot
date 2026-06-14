"""Domain models — persistence-agnostic entities shared across engine, API, and adapters.

These are Pydantic models (the boundary contract). The persistence layer maps them
to/from SQLAlchemy ORM rows; the engine consumes them directly. Nothing here imports
SQLAlchemy, FastAPI, or any broker SDK.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _uuid() -> str:
    return uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


# --- enumerations -----------------------------------------------------------


class Exchange(StrEnum):
    NSE = "NSE"
    BSE = "BSE"


class StrategyType(StrEnum):
    MOMENTUM = "momentum"
    PAIRS = "pairs"
    COMBINED = "combined"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(StrEnum):
    PENDING = "pending"  # proposed, awaiting approval
    APPROVED = "approved"  # 2FA-confirmed, not yet sent
    SUBMITTED = "submitted"  # sent to broker
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


# --- entities ---------------------------------------------------------------


class DomainModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Instrument(DomainModel):
    symbol: str
    exchange: Exchange = Exchange.NSE
    name: str | None = None
    sector: str | None = None
    has_liquid_ssf: bool = False  # gates the pairs short leg (SSF tradeability)
    lot_size: int | None = None


class UniverseMembership(DomainModel):
    """One point-in-time membership interval. effective_to=None means still a member."""

    id: str = Field(default_factory=_uuid)
    index: str
    symbol: str
    effective_from: date
    effective_to: date | None = None


class StrategyConfig(DomainModel):
    id: str = Field(default_factory=_uuid)
    name: str
    strategy_type: StrategyType
    params: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)


class ArtifactRef(DomainModel):
    key: str
    uri: str
    size: int
    content_type: str = "application/octet-stream"
    created_at: datetime = Field(default_factory=_now)


class BacktestRun(DomainModel):
    id: str = Field(default_factory=_uuid)
    strategy_config_id: str | None = None
    status: RunStatus = RunStatus.QUEUED
    params: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] | None = None
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    error: str | None = None
    requested_at: datetime = Field(default_factory=_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class Order(DomainModel):
    id: str = Field(default_factory=_uuid)
    symbol: str
    side: OrderSide
    quantity: int
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    broker_order_id: str | None = None
    reason: str | None = None
    created_at: datetime = Field(default_factory=_now)
    approved_at: datetime | None = None


class Position(DomainModel):
    symbol: str
    quantity: int
    avg_price: float
    last_price: float | None = None


class MarginInfo(DomainModel):
    available: float
    used: float
    total: float


class AuditEvent(DomainModel):
    """Append-only audit record (SYSTEM_DESIGN §8.6)."""

    id: str = Field(default_factory=_uuid)
    ts: datetime = Field(default_factory=_now)
    actor: str
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    ip: str | None = None


class JobStatus(DomainModel):
    id: str
    status: str  # queued | started | finished | failed
    result: Any | None = None
    error: str | None = None
