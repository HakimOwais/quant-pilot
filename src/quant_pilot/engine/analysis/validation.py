"""Statistical validation of a Sharpe ratio (MASTER_PROMPT Phase 5 corrections).

Answers "is this Sharpe real, or luck / backtest overfit?":
  - Probabilistic Sharpe Ratio (PSR) — P(true SR > benchmark), adjusting for skew/kurtosis.
  - Deflated Sharpe Ratio (DSR) — PSR against the *expected maximum* SR from N research trials
    (Bailey & López de Prado); the headline significance number, not the raw Sharpe.
  - Block-bootstrap Sharpe CI — dependence-preserving (never an IID shuffle).

Per-period SR (mean/std) drives PSR/DSR; the reported `sharpe` is annualized.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from pydantic import BaseModel
from scipy import stats

from quant_pilot.engine.models.monte_carlo import stationary_bootstrap

TRADING_DAYS = 252
_EULER = 0.5772156649015329


class SharpeSignificance(BaseModel):
    sharpe: float  # annualized
    probabilistic_sharpe: float  # PSR vs 0
    deflated_sharpe: float  # DSR given n_trials
    p_value: float  # 1 - PSR (P that true SR <= 0)
    ci_low: float  # block-bootstrap annualized-Sharpe CI
    ci_high: float
    n_trials: int
    n_obs: int


def _per_period_sharpe(r: np.ndarray) -> float:
    sd = r.std(ddof=1)
    return float(r.mean() / sd) if sd > 0 else 0.0


def annualized_sharpe(returns: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    return _per_period_sharpe(returns.to_numpy(dtype=float)) * math.sqrt(periods_per_year)


def probabilistic_sharpe_ratio(returns: pd.Series, benchmark_sr: float = 0.0) -> float:
    """PSR against a per-period benchmark Sharpe (Bailey & López de Prado)."""
    r = returns.to_numpy(dtype=float)
    n = len(r)
    sr = _per_period_sharpe(r)
    skew = float(stats.skew(r, bias=False))
    kurt = float(stats.kurtosis(r, fisher=False, bias=False))
    denom = math.sqrt(max(1e-12, 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr))
    z = (sr - benchmark_sr) * math.sqrt(n - 1) / denom
    return float(stats.norm.cdf(z))


def _expected_max_sharpe(n_trials: int, sr_std: float) -> float:
    """Expected maximum of N i.i.d. SR estimates (per-period units)."""
    if n_trials <= 1:
        return 0.0
    a = stats.norm.ppf(1.0 - 1.0 / n_trials)
    b = stats.norm.ppf(1.0 - 1.0 / (n_trials * math.e))
    return float(sr_std * ((1.0 - _EULER) * a + _EULER * b))


def deflated_sharpe_ratio(
    returns: pd.Series, n_trials: int, trials_sr_std: float | None = None
) -> float:
    """PSR benchmarked against the SR you'd expect as the best of `n_trials` random trials.

    `trials_sr_std` is the dispersion of Sharpe across trials; if unknown, it is approximated by
    the sampling std of the SR estimator under the observed moments (documented proxy).
    """
    r = returns.to_numpy(dtype=float)
    n = len(r)
    sr = _per_period_sharpe(r)
    if trials_sr_std is None:
        skew = float(stats.skew(r, bias=False))
        kurt = float(stats.kurtosis(r, fisher=False, bias=False))
        trials_sr_std = math.sqrt(
            max(1e-12, (1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr) / (n - 1))
        )
    return probabilistic_sharpe_ratio(
        returns, benchmark_sr=_expected_max_sharpe(n_trials, trials_sr_std)
    )


def bootstrap_sharpe_ci(
    returns: pd.Series,
    n_resamples: int = 1000,
    ci: float = 0.95,
    expected_block: float = 10.0,
    periods_per_year: int = TRADING_DAYS,
    seed: int | None = None,
) -> tuple[float, float]:
    samples = stationary_bootstrap(
        returns.to_numpy(dtype=float), expected_block, n_resamples, seed=seed
    )
    scale = math.sqrt(periods_per_year)
    srs = np.array([_per_period_sharpe(row) * scale for row in samples])
    lo = float(np.quantile(srs, (1.0 - ci) / 2.0))
    hi = float(np.quantile(srs, 1.0 - (1.0 - ci) / 2.0))
    return lo, hi


def sharpe_significance(
    returns: pd.Series,
    n_trials: int = 1,
    periods_per_year: int = TRADING_DAYS,
    n_resamples: int = 1000,
    seed: int | None = None,
) -> SharpeSignificance:
    psr = probabilistic_sharpe_ratio(returns)
    dsr = deflated_sharpe_ratio(returns, n_trials) if n_trials > 1 else psr
    lo, hi = bootstrap_sharpe_ci(
        returns, n_resamples=n_resamples, periods_per_year=periods_per_year, seed=seed
    )
    return SharpeSignificance(
        sharpe=annualized_sharpe(returns, periods_per_year),
        probabilistic_sharpe=psr,
        deflated_sharpe=dsr,
        p_value=1.0 - psr,
        ci_low=lo,
        ci_high=hi,
        n_trials=n_trials,
        n_obs=len(returns),
    )
