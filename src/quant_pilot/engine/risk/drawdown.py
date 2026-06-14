"""Drawdown monitoring + circuit breaker (MASTER_PROMPT Phase: risk; SYSTEM_DESIGN §8).

`DrawdownMonitor` is the stateful, live/loop form: feed it equity, it tracks peak/drawdown and
LATCHES halted once the max drawdown is breached (a tripped breaker stays tripped until an explicit
reset — the conservative, safe behavior). `drawdown_breaker_mask` is the vectorized backtest form:
an allowed/halted mask over an equity curve.
"""

from __future__ import annotations

import pandas as pd
from pydantic import BaseModel


class DrawdownState(BaseModel):
    peak: float
    drawdown: float  # negative fraction
    halted: bool


class DrawdownMonitor:
    def __init__(self, max_drawdown: float = 0.15) -> None:
        self.max_drawdown = max_drawdown
        self.peak = float("-inf")
        self.halted = False

    def update(self, equity: float) -> DrawdownState:
        self.peak = max(self.peak, equity)
        dd = equity / self.peak - 1.0 if self.peak > 0 else 0.0
        if dd <= -self.max_drawdown:
            self.halted = True  # latches
        return DrawdownState(peak=self.peak, drawdown=dd, halted=self.halted)

    def reset(self) -> None:
        self.halted = False
        self.peak = float("-inf")


def drawdown_breaker_mask(equity: pd.Series, max_drawdown: float = 0.15) -> pd.Series:
    """Boolean series: True = trading allowed, False once max drawdown is breached (latched)."""
    dd = equity / equity.cummax() - 1.0
    halted = (dd <= -max_drawdown).astype(int).cummax().astype(bool)
    return ~halted
