"""Paper-vs-sim P&L divergence (SYSTEM_DESIGN §8.7).

Before risking capital, live/paper returns must track the simulated returns. Persistent divergence
(high tracking error / low correlation) means the backtest does not describe reality — do not go
live.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel


class PnlDivergence(BaseModel):
    correlation: float
    tracking_error: float  # std of (live - sim) per-period return differences
    max_abs_diff: float
    n: int
    ok: bool


def pnl_divergence(
    live_returns: pd.Series, sim_returns: pd.Series, max_tracking_error: float = 0.02
) -> PnlDivergence:
    df = pd.concat([live_returns.rename("live"), sim_returns.rename("sim")], axis=1).dropna()
    if len(df) < 2:
        raise ValueError("need at least 2 overlapping observations")
    live, sim = df["live"].to_numpy(), df["sim"].to_numpy()
    diff = live - sim
    corr = float(np.corrcoef(live, sim)[0, 1]) if live.std() > 0 and sim.std() > 0 else 0.0
    te = float(diff.std(ddof=1))
    return PnlDivergence(
        correlation=corr,
        tracking_error=te,
        max_abs_diff=float(np.abs(diff).max()),
        n=len(df),
        ok=te <= max_tracking_error,
    )
