"""Cross-sectional momentum — a long-only factor tilt (MASTER_PROMPT Strategy A).

HONEST FRAMING: NSE cash can't be shorted, so this is long-only top-quintile, which is
structurally a high-beta + size tilt. Whether it is *alpha* is decided later by the
attribution regression — not by the return number here.

Pipeline per monthly rebalance date t (decided at close[t], filled next bar by the engine):
  1. score = mean over lookbacks of the return from (lb+skip) months ago to skip months ago
     (skip the last month to avoid short-term reversal — Jegadeesh-Titman).
  2. keep names that are point-in-time index members (eligibility mask) with a valid score.
  3. select the top `long_pct` by score.
  4. size by inverse 20-day realized vol (vol-scaled), normalized.
  5. scale gross exposure by the VRP regime (de-risk when the variance risk premium is high) —
     adaptive percentile, NOT hardcoded VIX levels.
  6. optional no-trade band suppresses sub-threshold weight changes (turnover control).

Pure: prices/membership/vrp in, weights out.
"""

from __future__ import annotations

import math
from typing import ClassVar

import numpy as np
import pandas as pd
from pydantic import BaseModel

from quant_pilot.engine.strategies.base import Strategy


class MomentumConfig(BaseModel):
    lookbacks: tuple[int, ...] = (6, 12)  # months
    skip_months: int = 1
    long_pct: float = 0.20
    vol_window: int = 20
    turnover_band: float = 0.0
    vrp_window: int = 504  # ~2y of sessions for the regime percentile
    min_exposure: float = 0.5
    gross_exposure: float = 1.0


class MomentumStrategy(Strategy):
    name: ClassVar[str] = "momentum"

    def __init__(self, config: MomentumConfig | None = None) -> None:
        self.cfg = config or MomentumConfig()

    def generate_weights(
        self,
        close: pd.DataFrame,
        membership: pd.DataFrame | None = None,
        vrp: pd.Series | None = None,
    ) -> pd.DataFrame:
        rebal_dates = self._rebalance_dates(close.index)
        realized_vol = close.pct_change().rolling(self.cfg.vol_window).std()
        weights = pd.DataFrame(0.0, index=rebal_dates, columns=close.columns)

        prev = pd.Series(0.0, index=close.columns)
        for t in rebal_dates:
            target = self._target_row(close, realized_vol, membership, vrp, t)
            if self.cfg.turnover_band > 0.0:
                target = self._apply_band(prev, target)
            weights.loc[t] = target
            prev = target
        return weights

    # --- per-rebalance construction ----------------------------------------

    def _target_row(self, close, realized_vol, membership, vrp, t) -> pd.Series:
        row = pd.Series(0.0, index=close.columns)
        score = self._momentum_score(close, t).dropna()
        if membership is not None and t in membership.index:
            eligible = membership.loc[t]
            score = score[eligible.reindex(score.index).fillna(False)]
        if score.empty:
            return row

        n_select = max(1, math.floor(len(score) * self.cfg.long_pct))
        chosen = score.nlargest(n_select).index

        vt = realized_vol.loc[t, chosen]
        inv = (1.0 / vt).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        w = inv / inv.sum() if inv.sum() > 0 else pd.Series(1.0 / len(chosen), index=chosen)

        scale = self._regime_scale(vrp, t) * self.cfg.gross_exposure
        row.loc[chosen] = w * scale
        return row

    def _momentum_score(self, close: pd.DataFrame, t: pd.Timestamp) -> pd.Series:
        rets = []
        for lb in self.cfg.lookbacks:
            recent = close.asof(t - pd.DateOffset(months=self.cfg.skip_months))
            old = close.asof(t - pd.DateOffset(months=lb + self.cfg.skip_months))
            rets.append(recent / old - 1.0)
        return pd.concat(rets, axis=1).mean(axis=1)

    def _regime_scale(self, vrp: pd.Series | None, t: pd.Timestamp) -> float:
        if vrp is None or t not in vrp.index:
            return 1.0
        window = vrp.loc[:t].tail(self.cfg.vrp_window)
        if len(window) < 2:
            return 1.0
        pct = float((window < window.iloc[-1]).mean())  # strict: flat/low VRP -> pct 0 -> full risk
        return self.cfg.min_exposure + (1.0 - self.cfg.min_exposure) * (1.0 - pct)

    def _apply_band(self, prev: pd.Series, target: pd.Series) -> pd.Series:
        delta = (target - prev).abs()
        return target.where(delta >= self.cfg.turnover_band, prev)

    @staticmethod
    def _rebalance_dates(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
        periods = index.to_period("M")
        return index[~periods.duplicated()]  # first trading day of each month
