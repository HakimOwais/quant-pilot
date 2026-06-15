"""API schemas for the parameter-sweep endpoint."""

from __future__ import annotations

from pydantic import BaseModel


class SweepRequest(BaseModel):
    symbols: list[str]
    start: str
    end: str
    param: str
    values: list[float]
    base: dict = {}
    benchmark: str = "^NSEI"


class SweepPoint(BaseModel):
    value: float
    total_return: float
    cagr: float
    sharpe: float
    max_drawdown: float
    n_rebalances: float
    alpha: float | None = None
    beta: float | None = None
    information_ratio: float | None = None
