"""Performance metrics (MASTER_PROMPT Phase 5). Pure: a returns Series in, stats out.

Risk-free rate is annual (default RBI repo ~6.5% in config); it is converted to per-period
internally. Sharpe/Sortino/Calmar use the standard annualization by sqrt(periods_per_year).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel

TRADING_DAYS = 252


class PerformanceStats(BaseModel):
    total_return: float
    cagr: float
    ann_vol: float
    sharpe: float
    sortino: float
    calmar: float
    max_drawdown: float  # negative fraction (e.g. -0.15)
    max_drawdown_days: int
    hit_rate: float
    n_periods: int


def drawdown_series(returns: pd.Series) -> pd.Series:
    equity = (1.0 + returns).cumprod()
    return equity / equity.cummax() - 1.0


def sharpe_ratio(
    returns: pd.Series, rf: float = 0.0, periods_per_year: int = TRADING_DAYS
) -> float:
    r = returns.to_numpy(dtype=float)
    sd = r.std(ddof=1)
    if sd == 0:
        return 0.0
    excess = r.mean() - rf / periods_per_year
    return float(excess / sd * np.sqrt(periods_per_year))


def sortino_ratio(
    returns: pd.Series, rf: float = 0.0, periods_per_year: int = TRADING_DAYS
) -> float:
    r = returns.to_numpy(dtype=float)
    excess = r - rf / periods_per_year
    downside = np.minimum(excess, 0.0)
    dd = np.sqrt(np.mean(downside**2))
    if dd == 0:
        return 0.0
    return float(excess.mean() / dd * np.sqrt(periods_per_year))


def _max_drawdown_days(dd: pd.Series) -> int:
    longest = current = 0
    for v in dd.to_numpy(dtype=float):
        current = current + 1 if v < 0 else 0
        longest = max(longest, current)
    return longest


def performance_stats(
    returns: pd.Series, rf: float = 0.0, periods_per_year: int = TRADING_DAYS
) -> PerformanceStats:
    r = returns.dropna()
    n = len(r)
    if n < 2:
        raise ValueError("performance_stats needs at least 2 returns")

    total_return = float((1.0 + r).prod() - 1.0)
    cagr = float((1.0 + total_return) ** (periods_per_year / n) - 1.0)
    ann_vol = float(r.std(ddof=1) * np.sqrt(periods_per_year))
    dd = drawdown_series(r)
    max_dd = float(dd.min())
    calmar = float(cagr / abs(max_dd)) if max_dd < 0 else 0.0

    return PerformanceStats(
        total_return=total_return,
        cagr=cagr,
        ann_vol=ann_vol,
        sharpe=sharpe_ratio(r, rf, periods_per_year),
        sortino=sortino_ratio(r, rf, periods_per_year),
        calmar=calmar,
        max_drawdown=max_dd,
        max_drawdown_days=_max_drawdown_days(dd),
        hit_rate=float((r > 0).mean()),
        n_periods=n,
    )
