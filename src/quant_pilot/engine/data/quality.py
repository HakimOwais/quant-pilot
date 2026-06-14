"""OHLCV data-quality checks (MASTER_PROMPT Phase 1: gaps, stale prices, volume spikes).

Pure: takes a normalized OHLCV DataFrame (DatetimeIndex; columns include close, volume) and
an optional set of expected trading sessions (from the NSE calendar), returns a report.
A name failing hard checks (missing sessions, non-positive prices, long stale runs) should be
quarantined before it is eligible to trade. Volume spikes/zero-volume are surfaced as warnings.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from pydantic import BaseModel


class QualityReport(BaseModel):
    ok: bool
    n_rows: int
    missing_sessions: list[date]
    stale_runs: list[tuple[date, int]]  # (run start, length) of repeated identical closes
    nonpositive: list[date]  # close <= 0
    zero_volume: list[date]
    volume_spikes: list[date]  # volume > spike_factor × median volume


def check_quality(
    df: pd.DataFrame,
    expected_sessions: set[date] | None = None,
    stale_limit: int = 5,
    spike_factor: float = 10.0,
) -> QualityReport:
    dates = [pd.Timestamp(ts).date() for ts in df.index]
    closes = [float(c) for c in df["close"].tolist()]
    volumes = [float(v) for v in df["volume"].tolist()]

    present = set(dates)
    missing = sorted(expected_sessions - present) if expected_sessions else []
    nonpositive = [d for d, c in zip(dates, closes, strict=True) if c <= 0]
    zero_volume = [d for d, v in zip(dates, volumes, strict=True) if v == 0]

    stale_runs = _stale_runs(dates, closes, stale_limit)

    positive_volumes = [v for v in volumes if v > 0]
    median_volume = pd.Series(positive_volumes).median() if positive_volumes else 0.0
    spikes = [
        d
        for d, v in zip(dates, volumes, strict=True)
        if median_volume > 0 and v > spike_factor * median_volume
    ]

    return QualityReport(
        ok=not missing and not nonpositive and not stale_runs,
        n_rows=len(dates),
        missing_sessions=missing,
        stale_runs=stale_runs,
        nonpositive=nonpositive,
        zero_volume=zero_volume,
        volume_spikes=spikes,
    )


def _stale_runs(dates: list[date], closes: list[float], stale_limit: int) -> list[tuple[date, int]]:
    runs: list[tuple[date, int]] = []
    run_len = 0
    run_start: date | None = None
    prev: float | None = None
    for d, c in zip(dates, closes, strict=True):
        if prev is not None and c == prev:
            run_len += 1
        else:
            if run_start is not None and run_len >= stale_limit:
                runs.append((run_start, run_len))
            run_len = 1
            run_start = d
        prev = c
    if run_start is not None and run_len >= stale_limit:
        runs.append((run_start, run_len))
    return runs
