"""Factor attribution — THE deliverable for the momentum tilt (MASTER_PROMPT Phase 5).

Regresses strategy excess returns on factor returns (market, size, value, momentum). The
intercept is alpha; a t-stat that isn't significant means the strategy is *factor exposure, not
skill*. Standard errors are Newey-West (HAC) so autocorrelation/heteroskedasticity don't inflate
significance. OLS + HAC implemented with numpy (statsmodels arrives with the pairs phase).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel

TRADING_DAYS = 252


class FactorAttribution(BaseModel):
    alpha_annual: float  # intercept, annualized
    alpha_tstat: float  # HAC t-stat on the (per-period) intercept
    betas: dict[str, float]  # factor loadings
    r_squared: float
    n_obs: int

    @property
    def alpha_is_significant(self) -> bool:
        return abs(self.alpha_tstat) > 2.0


def _newey_west_lags(n: int) -> int:
    return int(np.floor(4.0 * (n / 100.0) ** (2.0 / 9.0)))


def factor_attribution(
    returns: pd.Series,
    factors: pd.DataFrame,
    rf: float = 0.0,
    periods_per_year: int = TRADING_DAYS,
    hac_lags: int | None = None,
) -> FactorAttribution:
    df = pd.concat([returns.rename("_y"), factors], axis=1).dropna()
    if len(df) <= factors.shape[1] + 1:
        raise ValueError("not enough observations for the regression")

    y = (df["_y"] - rf / periods_per_year).to_numpy(dtype=float)
    f = df[list(factors.columns)].to_numpy(dtype=float)
    n = len(y)
    X = np.column_stack([np.ones(n), f])

    xtx_inv = np.linalg.inv(X.T @ X)
    beta = xtx_inv @ X.T @ y
    resid = y - X @ beta

    # Newey-West HAC covariance.
    lags = _newey_west_lags(n) if hac_lags is None else hac_lags
    scores = X * resid[:, None]
    s = (scores.T @ scores) / n
    for j in range(1, lags + 1):
        w = 1.0 - j / (lags + 1.0)
        g = (scores[j:].T @ scores[:-j]) / n
        s += w * (g + g.T)
    bread = np.linalg.inv((X.T @ X) / n)
    cov = bread @ s @ bread / n
    se = np.sqrt(np.diag(cov))

    sst = float(((y - y.mean()) ** 2).sum())
    sse = float((resid**2).sum())
    r_squared = 1.0 - sse / sst if sst > 0 else 0.0
    alpha_se = float(se[0])

    return FactorAttribution(
        alpha_annual=float(beta[0]) * periods_per_year,
        alpha_tstat=float(beta[0] / alpha_se) if alpha_se > 0 else 0.0,
        betas={col: float(beta[i + 1]) for i, col in enumerate(factors.columns)},
        r_squared=r_squared,
        n_obs=n,
    )
