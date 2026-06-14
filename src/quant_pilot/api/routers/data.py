"""Data endpoints: trigger OHLCV / universe ingestion (async jobs) and read cached bars."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends

from quant_pilot.api.deps import get_job_queue, get_market_data_provider
from quant_pilot.api.schemas.data import (
    Bar,
    IngestOhlcvRequest,
    IngestUniverseRequest,
    JobSubmitOut,
)
from quant_pilot.domain import ports

router = APIRouter(prefix="/data", tags=["data"])

_INGEST_OHLCV = "quant_pilot.workers.tasks.ingest_ohlcv"
_INGEST_UNIVERSE = "quant_pilot.workers.tasks.ingest_universe"


@router.post("/ohlcv", status_code=202, response_model=JobSubmitOut)
def ingest_ohlcv(
    body: IngestOhlcvRequest, queue: ports.JobQueue = Depends(get_job_queue)
) -> JobSubmitOut:
    job_id = queue.enqueue(_INGEST_OHLCV, body.symbols, body.start, body.end)
    return JobSubmitOut(job_id=job_id)


@router.post("/universe", status_code=202, response_model=JobSubmitOut)
def ingest_universe(
    body: IngestUniverseRequest, queue: ports.JobQueue = Depends(get_job_queue)
) -> JobSubmitOut:
    job_id = queue.enqueue(_INGEST_UNIVERSE, body.csv_path)
    return JobSubmitOut(job_id=job_id)


def _opt(row: Any, key: str) -> float | None:
    if key not in row:
        return None
    value = row[key]
    return None if pd.isna(value) else float(value)


@router.get("/ohlcv/{symbol}", response_model=list[Bar])
def get_bars(
    symbol: str,
    start: date,
    end: date,
    provider: ports.MarketDataProvider = Depends(get_market_data_provider),
) -> list[Bar]:
    df = provider.get_ohlcv(symbol, start, end)
    return [
        Bar(
            date=pd.Timestamp(ts).date(),
            open=float(row["open"]),
            high=_opt(row, "high"),
            low=_opt(row, "low"),
            close=float(row["close"]),
            adj_close=_opt(row, "adj_close"),
            volume=_opt(row, "volume"),
        )
        for ts, row in df.iterrows()
    ]
