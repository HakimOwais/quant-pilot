"""Corporate-action verification (MASTER_PROMPT NON-NEGOTIABLE #2).

yfinance "adjusted close" for NSE is unreliable for bonus issues and silently wrong on some
names. A correctly adjusted series is *continuous* across a split/bonus (the ratio is baked
into history), so:

  - a large jump in adj_close on a KNOWN action date  => the adjustment did NOT apply (bad).
  - a large jump on a date with NO known action        => unrecorded action or corrupt data.

Either case quarantines the symbol rather than trading on corrupt prices. Pure DataFrame in,
report out — no IO.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from pydantic import BaseModel


class CorpActionReport(BaseModel):
    ok: bool
    unexplained_jumps: list[date]  # jumps with no matching known action
    bad_adjustments: list[date]  # jumps coinciding with a known action (adjustment failed)


def _near(day: date, known: set[date], tol_days: int = 1) -> bool:
    return any(abs((day - k).days) <= tol_days for k in known)


def verify_adjustments(
    df: pd.DataFrame,
    known_actions: list[date] | None = None,
    jump_threshold: float = 0.35,
) -> CorpActionReport:
    """Flag discontinuities in `adj_close`. `df` must have an 'adj_close' column."""
    known = set(known_actions or [])
    adj = df["adj_close"].astype(float)
    returns = adj.pct_change().abs()

    jumps = [
        pd.Timestamp(ts).date()
        for ts, value in returns.items()
        if pd.notna(value) and value > jump_threshold
    ]
    unexplained = [d for d in jumps if not _near(d, known)]
    bad = [d for d in jumps if _near(d, known)]
    return CorpActionReport(
        ok=not unexplained and not bad,
        unexplained_jumps=unexplained,
        bad_adjustments=bad,
    )
