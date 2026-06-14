"""Background job definitions (run by the RQ worker).

These are placeholders that establish the call signature and logging contract.
Real engine wiring lands in the data/backtest phases — the API already enqueues
against these names so the async path is exercised end-to-end from day one.
"""

from __future__ import annotations

from quant_pilot.log import get_logger

log = get_logger("worker")


def run_backtest(run_id: str) -> dict:
    """Run a backtest by id. TODO: build engine with adapters, persist results/artifacts."""
    log.info("backtest.start", run_id=run_id)
    log.info("backtest.done", run_id=run_id, status="not_implemented")
    return {"run_id": run_id, "status": "not_implemented"}


def ingest_data(symbols: list[str]) -> dict:
    """Download/cache OHLCV for the given symbols. TODO: MarketDataProvider adapter."""
    log.info("ingest.start", n=len(symbols))
    return {"symbols": symbols, "status": "not_implemented"}
