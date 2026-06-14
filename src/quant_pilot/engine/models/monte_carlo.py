"""Monte Carlo: GBM/OU path simulation + risk measures.

Risk measures follow the production corrections in MASTER_PROMPT:
  - VaR/CVaR support a fat-tailed (Student-t) method, not just Gaussian — Indian small/mid caps
    have fat tails that a normal model understates.
  - CVaR (expected shortfall) is reported alongside VaR and is what risk sizing should use.
  - A stationary (block) bootstrap is provided for dependence-preserving resampling — never an
    IID shuffle, which would destroy the autocorrelation momentum/mean-reversion exploit.

Pure: numpy/scipy in, arrays/result models out. VaR/CVaR are reported as POSITIVE loss
magnitudes (a 1-day 99% VaR of 0.03 means a 3% loss).
"""

from __future__ import annotations

import math
from typing import Literal

import numpy as np
from pydantic import BaseModel
from scipy import stats

VaRMethod = Literal["historical", "student_t"]


class VaRResult(BaseModel):
    var: float  # positive loss magnitude at the confidence level
    cvar: float  # expected shortfall (>= var)
    alpha: float
    method: VaRMethod
    observations: int


def simulate_gbm(
    s0: float,
    mu: float,
    sigma: float,
    T: float,
    n_paths: int,
    n_steps: int,
    seed: int | None = None,
) -> np.ndarray:
    """Geometric Brownian motion paths, shape [n_paths, n_steps + 1]; column 0 == s0.

    E[S_T] = s0 · exp(mu·T).
    """
    rng = np.random.default_rng(seed)
    dt = T / n_steps
    z = rng.standard_normal((n_paths, n_steps))
    increments = (mu - 0.5 * sigma * sigma) * dt + sigma * math.sqrt(dt) * z
    log_paths = np.cumsum(increments, axis=1)
    start = np.zeros((n_paths, 1))
    return s0 * np.exp(np.hstack([start, log_paths]))


def simulate_ou(
    x0: float,
    theta: float,
    mu: float,
    sigma: float,
    T: float,
    n_paths: int,
    n_steps: int,
    seed: int | None = None,
) -> np.ndarray:
    """Euler-discretized OU paths, shape [n_paths, n_steps + 1]; column 0 == x0."""
    rng = np.random.default_rng(seed)
    dt = T / n_steps
    sd = sigma * math.sqrt(dt)
    paths = np.empty((n_paths, n_steps + 1))
    paths[:, 0] = x0
    for t in range(n_steps):
        shock = sd * rng.standard_normal(n_paths)
        paths[:, t + 1] = paths[:, t] + theta * (mu - paths[:, t]) * dt + shock
    return paths


def var_cvar(returns: object, alpha: float = 0.99, method: VaRMethod = "historical") -> VaRResult:
    """1-period VaR and CVaR (expected shortfall) at confidence `alpha`."""
    r = np.asarray(returns, dtype=float)
    if r.size == 0:
        raise ValueError("var_cvar requires a non-empty return series")
    p = 1.0 - alpha

    if method == "historical":
        q = float(np.quantile(r, p))
        tail = r[r <= q]
        cvar = -float(tail.mean()) if tail.size else -q
        return VaRResult(var=-q, cvar=cvar, alpha=alpha, method=method, observations=r.size)

    # Student-t: fit (df, loc, scale), then closed-form VaR/ES.
    df, loc, scale = stats.t.fit(r)
    x_p = float(stats.t.ppf(p, df))  # standardized lower quantile (negative)
    es_std = -(float(stats.t.pdf(x_p, df)) / p) * ((df + x_p * x_p) / (df - 1.0))
    var = -(loc + scale * x_p)
    cvar = -(loc + scale * es_std)
    return VaRResult(var=var, cvar=cvar, alpha=alpha, method=method, observations=r.size)


def stationary_bootstrap(
    returns: object,
    expected_block: float = 10.0,
    n_resamples: int = 1000,
    length: int | None = None,
    seed: int | None = None,
) -> np.ndarray:
    """Politis-Romano stationary bootstrap, shape [n_resamples, length].

    Geometric block lengths (mean = `expected_block`) preserve autocorrelation; wraps around the
    series. Use for dependence-aware Sharpe CIs / significance, never an IID shuffle.
    """
    r = np.asarray(returns, dtype=float)
    n = r.size
    if n == 0:
        raise ValueError("stationary_bootstrap requires a non-empty series")
    out_len = length or n
    rng = np.random.default_rng(seed)
    p = 1.0 / expected_block
    out = np.empty((n_resamples, out_len))
    for i in range(n_resamples):
        idx = int(rng.integers(0, n))
        for t in range(out_len):
            out[i, t] = r[idx]
            idx = int(rng.integers(0, n)) if rng.random() < p else (idx + 1) % n
    return out
