"""Pairs trading (MASTER_PROMPT Strategy B) — stat-arb on cointegrated, SSF-tradeable pairs.

Selection pipeline (all production-corrected):
  1. candidates filtered to names with a liquid single-stock future on BOTH legs (short leg reality)
  2. Engle-Granger cointegration on the TRAIN window, with Benjamini-Hochberg FDR across all tested
  3. OU fit on the spread -> half-life in [min, max] days and statistically mean-reverting
  4. out-of-sample confirmation: the spread (train hedge) must STILL mean-revert on the holdout
     (re-fit OU; more robust than re-running ADF, which is fragile under hedge estimation error)
Signals: rolling z-score with entry/exit/stop bands, plus a no-mean-cross break guard — if the
spread fails to cross its mean for far longer than its half-life implies, the relationship has
broken (M&A/regime shift) and the pair is force-flattened and retired (no look-ahead). The dollar
hedge ratio is frozen at entry, so weights are piecewise-constant (engine rebalances only on
signal changes).

Monte-Carlo here is the CORRECTED role — `reversion_robustness` stresses parameter uncertainty /
cointegration decay (theta -> 0); it does NOT gate trades by re-simulating the fitted model (the
original spec's circular confidence score, removed).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from pydantic import BaseModel

from quant_pilot.engine.models.monte_carlo import simulate_ou
from quant_pilot.engine.models.ou_process import OUParams, equilibrium_std, fit_ou
from quant_pilot.engine.strategies.base import Strategy
from quant_pilot.engine.strategies.cointegration import (
    benjamini_hochberg,
    compute_spread,
    engle_granger,
)


class PairConfig(BaseModel):
    cointegration_pvalue: float = 0.05
    half_life_min_days: float = 5.0
    half_life_max_days: float = 60.0
    entry_zscore: float = 2.0
    exit_zscore: float = 0.0
    stop_zscore: float = 3.5
    zscore_window: int = 60
    train_frac: float = 0.7
    gross_per_pair: float = 1.0
    break_half_life_mult: float = 4.0  # break if no mean-cross for this × half-life
    break_max_no_cross: int = 120  # absolute cap on the no-cross break window


@dataclass
class ValidatedPair:
    y: str
    x: str
    hedge_ratio: float
    intercept: float
    pvalue: float
    ou: OUParams


def select_pairs(
    candidates: list[tuple[str, str]],
    close: pd.DataFrame,
    config: PairConfig | None = None,
    ssf_eligible: set[str] | None = None,
) -> list[ValidatedPair]:
    cfg = config or PairConfig()
    pairs = [
        (a, b)
        for a, b in candidates
        if ssf_eligible is None or (a in ssf_eligible and b in ssf_eligible)
    ]
    split = int(len(close) * cfg.train_frac)
    train, holdout = close.iloc[:split], close.iloc[split:]

    infos: list[tuple] = []
    pvalues: list[float] = []
    for a, b in pairs:
        hedge, intercept, pvalue = engle_granger(train[a], train[b])
        ou = fit_ou(compute_spread(train[a], train[b], hedge, intercept).dropna())
        infos.append((a, b, hedge, intercept, pvalue, ou))
        pvalues.append(pvalue)

    passed = benjamini_hochberg(pvalues, cfg.cointegration_pvalue)
    selected: list[ValidatedPair] = []
    for (a, b, hedge, intercept, pvalue, ou), ok in zip(infos, passed, strict=True):
        if not ok or not ou.is_mean_reverting:
            continue
        if not (cfg.half_life_min_days <= ou.half_life <= cfg.half_life_max_days):
            continue
        oos = compute_spread(holdout[a], holdout[b], hedge, intercept).dropna()
        if len(oos) < 20:
            continue
        oos_ou = fit_ou(oos)
        if not oos_ou.is_mean_reverting or not (
            cfg.half_life_min_days <= oos_ou.half_life <= cfg.half_life_max_days
        ):
            continue  # mean reversion that doesn't persist out-of-sample is noise
        selected.append(ValidatedPair(a, b, hedge, intercept, pvalue, ou))
    return selected


def pair_leg_weights(
    cy: pd.Series, cx: pd.Series, pair: ValidatedPair, config: PairConfig
) -> tuple[pd.Series, pd.Series]:
    """Piecewise-constant target weights for one pair's two legs (signed; x is the short leg)."""
    spread = compute_spread(cy, cx, pair.hedge_ratio, pair.intercept)
    z = (spread - spread.rolling(config.zscore_window).mean()) / spread.rolling(
        config.zscore_window
    ).std()

    wy = pd.Series(0.0, index=cy.index)
    wx = pd.Series(0.0, index=cy.index)
    pos = 0
    entry_ratio = 0.0
    broken = False
    gross = config.gross_per_pair

    hl = pair.ou.half_life
    base = config.break_half_life_mult * hl if math.isfinite(hl) and hl > 0 else float("inf")
    max_no_cross = min(base, float(config.break_max_no_cross))
    prev_sign = 0
    bars_no_cross = 0

    for i in range(len(z)):
        zi = float(z.iloc[i])
        if not broken and not np.isnan(zi):
            sign = 1 if zi > 0 else (-1 if zi < 0 else 0)
            if prev_sign != 0 and sign != 0 and sign != prev_sign:
                bars_no_cross = 0  # spread crossed its mean -> still reverting
            else:
                bars_no_cross += 1
            if sign != 0:
                prev_sign = sign
            if bars_no_cross > max_no_cross:
                broken, pos = True, 0  # no mean reversion for too long -> retire pair

            if not broken:
                if pos == 0:
                    if zi <= -config.entry_zscore:
                        pos = 1  # long spread (spread cheap, expect rise)
                    elif zi >= config.entry_zscore:
                        pos = -1  # short spread
                    if pos != 0:
                        entry_ratio = pair.hedge_ratio * float(cx.iloc[i]) / float(cy.iloc[i])
                elif (
                    pos == 1
                    and (zi >= config.exit_zscore or zi <= -config.stop_zscore)
                    or pos == -1
                    and (zi <= config.exit_zscore or zi >= config.stop_zscore)
                ):
                    pos = 0

        wy.iloc[i] = pos * gross
        wx.iloc[i] = -pos * gross * entry_ratio if pos != 0 else 0.0
    return wy, wx


class PairsStrategy(Strategy):
    name = "pairs"

    def __init__(self, pairs: list[ValidatedPair], config: PairConfig | None = None) -> None:
        self.pairs = pairs
        self.cfg = config or PairConfig()

    def generate_weights(self, close: pd.DataFrame) -> pd.DataFrame:
        weights = pd.DataFrame(0.0, index=close.index, columns=close.columns)
        for pair in self.pairs:
            wy, wx = pair_leg_weights(close[pair.y], close[pair.x], pair, self.cfg)
            weights[pair.y] = weights[pair.y] + wy
            weights[pair.x] = weights[pair.x] + wx
        return weights


def reversion_robustness(
    ou: OUParams,
    horizon_days: int = 30,
    n_paths: int = 5000,
    decay: float = 0.5,
    start_z: float = 2.0,
    seed: int | None = None,
) -> dict[str, float]:
    """Stress mean reversion under parameter uncertainty (the corrected MC role).

    Starts the spread `start_z` equilibrium-sds from the mean and reports P(revert to mean within
    horizon) under the fitted theta vs a decayed theta (cointegration weakening). This quantifies
    the real tail risk; it does NOT gate trades by re-simulating the fitted model.
    """
    eq = equilibrium_std(ou.theta, ou.sigma)
    x0 = ou.mu + start_z * eq

    def revert_prob(theta: float) -> float:
        paths = simulate_ou(
            x0,
            theta,
            ou.mu,
            ou.sigma,
            T=horizon_days,
            n_paths=n_paths,
            n_steps=horizon_days,
            seed=seed,
        )
        return float((paths <= ou.mu).any(axis=1).mean())

    return {"nominal": revert_prob(ou.theta), "stressed": revert_prob(ou.theta * decay)}
