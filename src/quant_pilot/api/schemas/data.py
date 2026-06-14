"""API schemas for the data-ingestion endpoints."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class IngestOhlcvRequest(BaseModel):
    symbols: list[str]
    start: str  # ISO date
    end: str


class IngestUniverseRequest(BaseModel):
    csv_path: str  # path reachable by the worker (mounted volume in container)


class JobSubmitOut(BaseModel):
    job_id: str


class Bar(BaseModel):
    date: date
    open: float
    high: float | None = None
    low: float | None = None
    close: float
    adj_close: float | None = None
    volume: float | None = None
