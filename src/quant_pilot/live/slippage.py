"""Slippage monitor (SYSTEM_DESIGN §8.7): compare realized fills to the expected price.

Persistent adverse slippage means the impact/cost model underestimates reality — the backtest is
optimistic and should be recalibrated. Adverse slippage is positive (a buy filling above expected,
a sell below).
"""

from __future__ import annotations

from pydantic import BaseModel

from quant_pilot.domain.models import OrderSide

_BPS = 1e4


class SlippageReport(BaseModel):
    n: int
    mean_bps: float
    max_bps: float
    flagged: bool  # mean adverse slippage exceeds the threshold


class SlippageMonitor:
    def __init__(self, threshold_bps: float = 20.0) -> None:
        self.threshold_bps = threshold_bps
        self._samples: list[float] = []

    def record(self, side: OrderSide, expected_price: float, fill_price: float) -> float:
        if expected_price <= 0:
            return 0.0
        if side == OrderSide.BUY:
            bps = (fill_price - expected_price) / expected_price * _BPS
        else:
            bps = (expected_price - fill_price) / expected_price * _BPS
        self._samples.append(bps)
        return bps

    def report(self) -> SlippageReport:
        if not self._samples:
            return SlippageReport(n=0, mean_bps=0.0, max_bps=0.0, flagged=False)
        mean = sum(self._samples) / len(self._samples)
        return SlippageReport(
            n=len(self._samples),
            mean_bps=mean,
            max_bps=max(self._samples),
            flagged=mean > self.threshold_bps,
        )
