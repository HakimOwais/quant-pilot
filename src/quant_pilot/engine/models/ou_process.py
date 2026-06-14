"""Ornstein-Uhlenbeck process: fitting, half-life, and z-score signal.

Model:  dX = theta (mu - X) dt + sigma dW

Fitted by OLS on the discrete AR(1) form  X_{t+1} = a + b X_t + eps  (b = exp(-theta·dt)):
    theta = -ln(b) / dt
    mu    = a / (1 - b)
    sigma = std(eps) · sqrt( 2·theta / (1 - b²) )      [maps residual std to OU sigma]
    half_life = ln(2) / theta

Used by the pairs strategy (spread mean-reversion) and Monte-Carlo. Pure: array in, params out.
A series is only treated as mean-reverting when 0 < b < 1.
"""

from __future__ import annotations

import math

import numpy as np
from pydantic import BaseModel


class OUParams(BaseModel):
    theta: float  # mean-reversion speed (per unit time)
    mu: float  # long-run mean
    sigma: float  # instantaneous volatility
    half_life: float  # ln(2)/theta (inf if not mean-reverting)
    is_mean_reverting: bool


def half_life(theta: float) -> float:
    return math.inf if theta <= 0.0 else math.log(2.0) / theta


def equilibrium_std(theta: float, sigma: float) -> float:
    """Stationary (long-run) standard deviation of the OU process: sigma / sqrt(2·theta)."""
    return math.inf if theta <= 0.0 else sigma / math.sqrt(2.0 * theta)


def fit_ou(series: object, dt: float = 1.0, mr_tstat: float = -2.0) -> OUParams:
    """Fit OU params by AR(1) OLS.

    `is_mean_reverting` requires the slope b to be *significantly* below 1, via a
    Dickey-Fuller-style t-statistic (b - 1) / SE(b) < `mr_tstat`. This rejects random walks
    whose noisy slope lands just under 1. (Full ADF/cointegration testing arrives with the
    pairs phase + statsmodels; this is the lightweight gate.)
    """
    x = np.asarray(series, dtype=float)
    if x.size < 3:
        raise ValueError("fit_ou needs at least 3 observations")

    x_prev, x_next = x[:-1], x[1:]
    b, a = (float(v) for v in np.polyfit(x_prev, x_next, 1))  # slope, intercept

    residuals = x_next - (a + b * x_prev)
    dof = max(len(residuals) - 2, 1)
    sigma_eps = math.sqrt(float(residuals @ residuals) / dof)

    sxx = float(((x_prev - x_prev.mean()) ** 2).sum())
    se_b = math.sqrt(sigma_eps * sigma_eps / sxx) if sxx > 0 else math.inf
    t_stat = (b - 1.0) / se_b if math.isfinite(se_b) and se_b > 0 else 0.0

    if 0.0 < b < 1.0 and t_stat < mr_tstat:
        theta = -math.log(b) / dt
        mu = a / (1.0 - b)
        sigma = sigma_eps * math.sqrt(2.0 * theta / (1.0 - b * b))
        return OUParams(
            theta=theta, mu=mu, sigma=sigma, half_life=half_life(theta), is_mean_reverting=True
        )

    # No statistically usable mean reversion (random walk / explosive / oscillatory).
    return OUParams(
        theta=0.0,
        mu=float(np.mean(x)),
        sigma=sigma_eps,
        half_life=math.inf,
        is_mean_reverting=False,
    )


def ou_zscore(value: float, params: OUParams) -> float:
    """Standardize a level against the OU stationary distribution: (value - mu) / eq_std."""
    sd = equilibrium_std(params.theta, params.sigma)
    if not math.isfinite(sd) or sd == 0.0:
        return 0.0
    return (value - params.mu) / sd


def spread_zscore(series: object, params: OUParams) -> float:
    """Z-score of the latest observation of a spread series under fitted OU params."""
    x = np.asarray(series, dtype=float)
    return ou_zscore(float(x[-1]), params)
