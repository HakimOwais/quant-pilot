"""Market-impact model (MASTER_PROMPT §Transaction Costs (b)) — the dominant cost.

impact_fraction = temporary_impact + half_spread + slippage_buffer
  temporary_impact = k · daily_vol · sqrt(participation),   participation = |qty| / ADV_shares

Plus an ADV participation cap (orders are clipped to a fraction of average daily volume). Quoted
spread is not available from daily bars (see Step 3 gotcha), so `assumed_spread_bps` defaults to
0 and the buffer/temp terms carry the cost; a real spread can be wired later.

Scalar `compute_impact` for clarity/tests; `*_vec` forms for the engine.
"""

from __future__ import annotations

import math

import numpy as np
from pydantic import BaseModel

_BPS = 1e4


class ImpactConfig(BaseModel):
    impact_k: float = 0.9
    max_adv_participation: float = 0.10
    slippage_buffer_bps: float = 5.0
    assumed_spread_bps: float = 0.0  # quoted spread needs intraday data; flat assumption optional


class ImpactResult(BaseModel):
    participation: float
    impact_fraction: float
    cost: float


def compute_impact(
    quantity: float,
    price: float,
    adv_shares: float,
    daily_vol: float,
    config: ImpactConfig,
    spread_bps: float | None = None,
) -> ImpactResult:
    qty = abs(quantity)
    participation = qty / adv_shares if adv_shares and adv_shares > 0 else 0.0
    vol = daily_vol if daily_vol and math.isfinite(daily_vol) else 0.0
    temporary = config.impact_k * vol * math.sqrt(participation)
    spread = (config.assumed_spread_bps if spread_bps is None else spread_bps) / _BPS * 0.5
    slippage = config.slippage_buffer_bps / _BPS
    fraction = temporary + spread + slippage
    return ImpactResult(
        participation=participation, impact_fraction=fraction, cost=fraction * qty * price
    )


def cap_quantity(desired_qty: float, adv_shares: float, max_participation: float) -> float:
    """Clip an order to max_participation × ADV. No cap if ADV is unknown/non-positive."""
    if not adv_shares or adv_shares <= 0 or not math.isfinite(adv_shares):
        return desired_qty
    cap = max_participation * adv_shares
    return math.copysign(min(abs(desired_qty), cap), desired_qty)


def cap_quantity_vec(
    desired: np.ndarray, adv_shares: np.ndarray, max_participation: float
) -> np.ndarray:
    valid = np.isfinite(adv_shares) & (adv_shares > 0)
    cap = np.where(valid, max_participation * np.nan_to_num(adv_shares), np.inf)
    return np.sign(desired) * np.minimum(np.abs(desired), cap)


def impact_cost_vec(
    quantities: np.ndarray,
    prices: np.ndarray,
    adv_shares: np.ndarray,
    daily_vol: np.ndarray,
    config: ImpactConfig,
    spread_bps: float | None = None,
) -> np.ndarray:
    qty = np.abs(quantities)
    adv_ok = np.isfinite(adv_shares) & (adv_shares > 0)
    participation = np.where(adv_ok, qty / np.where(adv_ok, adv_shares, 1.0), 0.0)
    vol = np.nan_to_num(daily_vol, nan=0.0)
    temporary = config.impact_k * vol * np.sqrt(participation)
    spread = (config.assumed_spread_bps if spread_bps is None else spread_bps) / _BPS * 0.5
    slippage = config.slippage_buffer_bps / _BPS
    fraction = temporary + spread + slippage
    return fraction * qty * prices
