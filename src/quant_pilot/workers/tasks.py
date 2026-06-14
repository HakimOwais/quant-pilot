"""Background jobs (run by the RQ worker). These wire engine logic + adapters + repository.

Each task owns its own DB session/transaction (workers are not request-scoped). Heavy logic
lives in the engine (pure) and adapters; tasks are thin orchestration.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

from sqlalchemy.orm import Session

from quant_pilot.adapters.data.parquet_cache import OHLCVCache
from quant_pilot.adapters.data.yfinance_provider import YFinanceMarketDataProvider
from quant_pilot.adapters.persistence.repository import SqlAlchemyRepository
from quant_pilot.config.settings import get_settings
from quant_pilot.db.base import get_sessionmaker
from quant_pilot.engine.data.universe import build_membership_intervals, read_membership_csv
from quant_pilot.log import get_logger

log = get_logger("worker")


@contextmanager
def _unit_of_work() -> Iterator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ingest_universe(csv_path: str) -> dict:
    """Rebuild point-in-time index membership from an add/drop events CSV and persist it."""
    events = read_membership_csv(csv_path)
    intervals = build_membership_intervals(events)
    with _unit_of_work() as session:
        n = SqlAlchemyRepository(session).add_universe_membership(intervals)
    log.info("universe.ingested", events=len(events), intervals=n, source=csv_path)
    return {"events": len(events), "intervals": n}


def ingest_ohlcv(symbols: list[str], start: str, end: str) -> dict:
    """Download + cache OHLCV for symbols over [start, end] (ISO dates)."""
    settings = get_settings()
    cache = OHLCVCache(settings.data_dir)
    start_d, end_d = date.fromisoformat(start), date.fromisoformat(end)
    ok, failed = 0, []
    with _unit_of_work() as session:
        provider = YFinanceMarketDataProvider(SqlAlchemyRepository(session), cache)
        for symbol in symbols:
            try:
                rows = len(provider.get_ohlcv(symbol, start_d, end_d))
                log.info("ohlcv.cached", symbol=symbol, rows=rows)
                ok += 1
            except Exception as exc:  # record and continue the rest of the batch
                log.warning("ohlcv.failed", symbol=symbol, error=str(exc))
                failed.append(symbol)
    return {"ok": ok, "failed": failed}
