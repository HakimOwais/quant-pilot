"""Cointegration primitives for pairs trading (MASTER_PROMPT Strategy B).

- Engle-Granger: OLS hedge ratio + ADF unit-root test on the residual spread.
- Benjamini-Hochberg FDR: mandatory multiple-testing control — scanning many candidate pairs at
  p<0.05 guarantees false positives, so the selection threshold is corrected for the number tested.
- CUSUM break test: cointegration relationships break (M&A, regime shifts — e.g. the HDFC merger);
  this flags a structural break so a pair can be retired/force-exited.

Pure: Series/arrays in, numbers out.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller


def engle_granger(y: pd.Series, x: pd.Series) -> tuple[float, float, float]:
    """Return (hedge_ratio, intercept, adf_pvalue) for y = intercept + hedge_ratio·x + spread."""
    df = pd.concat([y, x], axis=1).dropna()
    yv = df.iloc[:, 0].to_numpy(dtype=float)
    xv = df.iloc[:, 1].to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(xv)), xv])
    intercept, hedge = (float(v) for v in np.linalg.lstsq(design, yv, rcond=None)[0])
    resid = yv - (intercept + hedge * xv)
    pvalue = float(adfuller(resid, autolag="AIC")[1])
    return hedge, intercept, pvalue


def compute_spread(y: pd.Series, x: pd.Series, hedge_ratio: float, intercept: float) -> pd.Series:
    return y - (intercept + hedge_ratio * x)


def benjamini_hochberg(pvalues: list[float], alpha: float = 0.05) -> list[bool]:
    """Benjamini-Hochberg FDR: return a mask of which hypotheses are rejected (= cointegrated)."""
    p = np.asarray(pvalues, dtype=float)
    m = len(p)
    if m == 0:
        return []
    ranked = np.sort(p)
    thresh = (np.arange(1, m + 1) / m) * alpha
    passed = ranked <= thresh
    if not passed.any():
        return [False] * m
    cutoff = ranked[np.max(np.flatnonzero(passed))]
    return (p <= cutoff).tolist()


def cusum_break(spread: pd.Series | np.ndarray, threshold: float = 1.36) -> bool:
    """Brownian-bridge CUSUM on the spread; True if a structural mean shift is detected.

    Default threshold ≈ 1.36 (Kolmogorov 5%). A stationary mean-zero spread keeps the standardized
    cumulative sum bounded; a mean shift makes it drift past the threshold.
    """
    s = np.asarray(spread, dtype=float)
    s = s[~np.isnan(s)]
    n = len(s)
    if n < 3:
        return False
    sd = s.std(ddof=1)
    if sd == 0:
        return False
    cumdev = np.cumsum(s - s.mean()) / (sd * np.sqrt(n))
    return bool(np.max(np.abs(cumdev)) > threshold)
