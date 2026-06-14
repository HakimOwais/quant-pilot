"""Indian explicit transaction-cost model (MASTER_PROMPT §Transaction Costs (a)).

Models the regulatory/exchange stack per order: brokerage (₹20 flat or 0.03%, whichever is
lower), STT, exchange charges, GST, SEBI charges, and stamp duty. Market *impact* — the
dominant cost — lives separately in `impact.py`.

Scalar `compute_costs` is the readable/tested form; `total_costs_vec` is the vectorized form the
engine calls per rebalance. Both share one formula. Config field names match
`config/settings.yaml: transaction_costs` (extra keys are ignored, so the same dict feeds both
CostConfig and ImpactConfig).
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import BaseModel

Side = Literal["buy", "sell"]
Segment = Literal["delivery", "intraday"]

_CRORE = 1e7


class CostConfig(BaseModel):
    flat_fee_per_order: float = 20.0
    brokerage_pct: float = 0.0003
    stt_delivery: float = 0.001
    stt_intraday_sell: float = 0.00025
    exchange_charges_nse: float = 0.0000335
    gst: float = 0.18
    sebi_charges_per_cr: float = 10.0
    stamp_duty_buy: float = 0.00015


class CostBreakdown(BaseModel):
    brokerage: float
    stt: float
    exchange: float
    gst: float
    sebi: float
    stamp: float
    total: float


def compute_costs(
    side: Side,
    price: float,
    quantity: float,
    config: CostConfig,
    segment: Segment = "delivery",
) -> CostBreakdown:
    turnover = price * abs(quantity)
    is_buy = side == "buy"

    brokerage = min(config.flat_fee_per_order, config.brokerage_pct * turnover) if turnover else 0.0
    exchange = config.exchange_charges_nse * turnover
    if segment == "delivery":
        stt = config.stt_delivery * turnover  # both buy and sell legs
    else:
        stt = 0.0 if is_buy else config.stt_intraday_sell * turnover
    gst = config.gst * (brokerage + exchange)
    sebi = config.sebi_charges_per_cr / _CRORE * turnover
    stamp = config.stamp_duty_buy * turnover if is_buy else 0.0
    total = brokerage + stt + exchange + gst + sebi + stamp
    return CostBreakdown(
        brokerage=brokerage,
        stt=stt,
        exchange=exchange,
        gst=gst,
        sebi=sebi,
        stamp=stamp,
        total=total,
    )


def total_costs_vec(
    prices: np.ndarray,
    quantities: np.ndarray,
    config: CostConfig,
    segment: Segment = "delivery",
) -> np.ndarray:
    """Vectorized per-order total cost. `quantities` are signed; only magnitude drives turnover."""
    turnover = prices * np.abs(quantities)
    has_trade = turnover > 0
    is_buy = quantities > 0

    brokerage = np.where(
        has_trade, np.minimum(config.flat_fee_per_order, config.brokerage_pct * turnover), 0.0
    )
    exchange = config.exchange_charges_nse * turnover
    if segment == "delivery":
        stt = config.stt_delivery * turnover
    else:
        stt = np.where(is_buy, 0.0, config.stt_intraday_sell * turnover)
    gst = config.gst * (brokerage + exchange)
    sebi = config.sebi_charges_per_cr / _CRORE * turnover
    stamp = np.where(is_buy, config.stamp_duty_buy * turnover, 0.0)
    return brokerage + stt + exchange + gst + sebi + stamp
