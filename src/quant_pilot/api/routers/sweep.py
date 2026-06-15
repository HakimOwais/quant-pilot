"""Parameter-sweep endpoint: run a momentum knob across a grid, return a metric per value.

Synchronous (reads the cache, no network) and bounded; the result feeds a 'metric vs parameter'
chart for edge-hunting.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from quant_pilot.api.schemas.sweep import SweepPoint, SweepRequest
from quant_pilot.workers.tasks import _close_from_cache, _prices_from_cache, sweep_parameter

router = APIRouter(prefix="/sweep", tags=["sweep"])

SWEEPABLE = {"long_pct", "vol_window", "skip_months", "turnover_band"}


@router.post("", response_model=list[SweepPoint])
def run_sweep(body: SweepRequest) -> list[SweepPoint]:
    if body.param not in SWEEPABLE:
        raise HTTPException(status_code=422, detail=f"param must be one of {sorted(SWEEPABLE)}")
    if not body.values:
        raise HTTPException(status_code=422, detail="values must be a non-empty list")
    prices = _prices_from_cache(body.symbols, body.start, body.end)
    if prices.close is None or prices.close.empty:
        raise HTTPException(status_code=422, detail="no price data for those symbols; ingest first")
    bench = _close_from_cache(body.benchmark, body.start, body.end)
    points = sweep_parameter(prices, body.param, body.values, base=body.base, benchmark_close=bench)
    return [SweepPoint(**p) for p in points]
