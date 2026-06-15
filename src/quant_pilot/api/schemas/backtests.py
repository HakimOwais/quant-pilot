"""API request/response schemas for backtests. Responses reuse the domain models directly."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from quant_pilot.domain.models import RunStatus, StrategyType


class BacktestCreate(BaseModel):
    strategy: StrategyType
    params: dict[str, Any] = {}


class BacktestSubmitOut(BaseModel):
    run_id: str
    job_id: str
    status: RunStatus


class EquityPoint(BaseModel):
    date: str
    equity: float
    drawdown: float
    benchmark: float | None = None  # benchmark buy-and-hold, same initial capital
