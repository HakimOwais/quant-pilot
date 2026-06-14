"""Position sizing (MASTER_PROMPT Phase: risk).

- fractional_kelly: f = fraction · μ/σ² — FRACTIONAL only; full Kelly on an *estimated* edge is a
  portfolio-detonator (estimation error), so the spec caps it at ¼ Kelly.
- target_vol_scale: scale gross exposure to a target portfolio volatility.
- apply_position_caps: enforce per-position and per-sector gross limits.

Pure: numbers / Series in, sized weights out.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_pilot.engine.risk.config import RiskConfig


def fractional_kelly(
    mean_return: float, variance: float, fraction: float = 0.25, cap: float = 1.0
) -> float:
    """Fractional Kelly weight: fraction · (μ/σ²), clipped to ±cap. 0 if variance ≤ 0."""
    if variance <= 0:
        return 0.0
    return float(np.clip(fraction * mean_return / variance, -cap, cap))


def target_vol_scale(realized_vol: float, target_vol: float, max_leverage: float = 1.5) -> float:
    """Multiplier to bring realized portfolio vol toward target_vol (capped at max_leverage)."""
    if realized_vol <= 0:
        return 0.0
    return float(min(target_vol / realized_vol, max_leverage))


def apply_position_caps(
    weights: pd.Series,
    max_position_pct: float,
    sector_map: dict[str, str] | None = None,
    max_sector_pct: float | None = None,
) -> pd.Series:
    """Clip each weight to ±max_position_pct, then scale down any sector over its gross cap."""
    w = weights.clip(-max_position_pct, max_position_pct).astype(float)
    if sector_map and max_sector_pct:
        sectors: dict[str, list[str]] = {}
        for sym in w.index:
            sec = sector_map.get(sym)
            if sec is not None:
                sectors.setdefault(sec, []).append(sym)
        for syms in sectors.values():
            gross = float(w[syms].abs().sum())
            if gross > max_sector_pct > 0:
                w[syms] = w[syms] * (max_sector_pct / gross)
    return w


class RiskManager:
    """Applies position/sector caps across a weights DataFrame (one row per rebalance)."""

    def __init__(self, config: RiskConfig | None = None, sector_map: dict[str, str] | None = None):
        self.cfg = config or RiskConfig()
        self.sector_map = sector_map

    def cap_weights(self, weights: pd.DataFrame) -> pd.DataFrame:
        return weights.apply(
            lambda row: apply_position_caps(
                row, self.cfg.max_position_pct, self.sector_map, self.cfg.max_sector_pct
            ),
            axis=1,
        )
