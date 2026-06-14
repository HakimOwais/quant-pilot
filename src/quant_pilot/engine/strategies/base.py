"""Abstract Strategy: produces target weights the backtest engine executes.

A strategy maps market data to a (rebalance-dates × symbols) weight DataFrame. It owns *what* to
hold; the engine owns *how/when* to fill it (next-bar, costs, impact). Weights may be sparse —
rows only on rebalance dates — since the engine forward-fills between them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

import pandas as pd


class Strategy(ABC):
    name: ClassVar[str] = "strategy"

    @abstractmethod
    def generate_weights(self, close: pd.DataFrame) -> pd.DataFrame:
        """Return target weights (index = rebalance dates, columns = symbols)."""
