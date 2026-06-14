"""Background jobs (run by the RQ worker). These wire engine logic + adapters + repository.

Each task owns its own DB session/transaction (workers are not request-scoped). Heavy logic
lives in the engine (pure) and adapters; tasks are thin orchestration.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime

import pandas as pd
from sqlalchemy.orm import Session

from quant_pilot.adapters.artifacts.local_store import LocalArtifactStore
from quant_pilot.adapters.data.parquet_cache import OHLCVCache
from quant_pilot.adapters.data.yfinance_provider import YFinanceMarketDataProvider
from quant_pilot.adapters.persistence.repository import SqlAlchemyRepository
from quant_pilot.config.settings import get_settings
from quant_pilot.db.base import get_sessionmaker
from quant_pilot.domain.models import RunStatus
from quant_pilot.engine.analysis.performance import drawdown_series, performance_stats
from quant_pilot.engine.analysis.validation import sharpe_significance
from quant_pilot.engine.backtest.engine import BacktestEngine, PriceData
from quant_pilot.engine.data.universe import build_membership_intervals, read_membership_csv
from quant_pilot.engine.strategies.momentum import MomentumStrategy
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


def execute_backtest(prices: PriceData, strategy: str = "momentum", rf: float = 0.065) -> dict:
    """Run a strategy through the engine and compute performance + significance. Pure-ish: prices
    in, metrics out (testable with synthetic data, no IO)."""
    if prices.close is None or prices.close.empty:
        raise ValueError("no price data for the requested symbols/date range (ingest OHLCV first)")
    if strategy == "momentum":
        weights = MomentumStrategy().generate_weights(prices.close)
    else:
        raise ValueError(f"unsupported strategy: {strategy!r}")
    result = BacktestEngine().run(prices, weights)
    perf = performance_stats(result.returns, rf=rf)
    sig = sharpe_significance(result.returns, n_resamples=200)
    dd = drawdown_series(result.returns)
    equity_curve = [
        {"date": pd.Timestamp(ts).date().isoformat(), "equity": float(eq), "drawdown": float(d)}
        for ts, eq, d in zip(result.equity.index, result.equity.to_numpy(), dd.to_numpy())
    ]
    return {
        "summary": result.summary,
        "performance": perf.model_dump(),
        "significance": sig.model_dump(),
        "equity_curve": equity_curve,
    }


def _prices_from_cache(symbols: list[str], start: str, end: str) -> PriceData:
    cache = OHLCVCache(get_settings().data_dir)
    closes, opens = {}, {}
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    for sym in symbols:
        df = cache.read(sym)
        if df is None or df.empty:
            continue
        window = df[(df.index >= s) & (df.index <= e)]
        closes[sym] = window["close"]
        opens[sym] = window["open"]
    return PriceData(open=pd.DataFrame(opens), close=pd.DataFrame(closes))


def run_backtest(run_id: str) -> dict:
    """Worker entrypoint: load run, execute, persist metrics/status. Params: symbols, start, end."""
    with _unit_of_work() as session:
        run = SqlAlchemyRepository(session).get_backtest_run(run_id)
        if run is None:
            return {"error": "run not found", "run_id": run_id}
        run.status = RunStatus.RUNNING
        run.started_at = datetime.now(UTC)
        SqlAlchemyRepository(session).update_backtest_run(run)
        params = dict(run.params)

    try:
        prices = _prices_from_cache(
            params.get("symbols", []),
            params.get("start", "2015-01-01"),
            params.get("end", "2025-12-31"),
        )
        metrics = execute_backtest(prices, strategy=params.get("strategy", "momentum"))
        curve = metrics.pop("equity_curve", None)
        if curve:
            LocalArtifactStore(get_settings().artifacts_dir).save_json(
                f"runs/{run_id}/equity.json", curve
            )
        status, error = RunStatus.SUCCEEDED, None
    except Exception as exc:
        metrics, status, error = None, RunStatus.FAILED, str(exc)
        log.warning("backtest.failed", run_id=run_id, error=str(exc))

    with _unit_of_work() as session:
        repo = SqlAlchemyRepository(session)
        run = repo.get_backtest_run(run_id)
        if run is not None:
            run.status = status
            run.metrics = metrics
            run.error = error
            run.finished_at = datetime.now(UTC)
            repo.update_backtest_run(run)
    return {"run_id": run_id, "status": status.value}
