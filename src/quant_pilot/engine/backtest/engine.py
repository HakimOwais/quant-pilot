"""Backtest engine (MASTER_PROMPT Phase 4) — no look-ahead, next-bar fills, realistic costs.

Mechanics:
  - The strategy supplies target weights decided at close[t]; the engine executes them at
    open[t+1] (`target_weights` is forward-filled, then shifted one bar). Trailing volatility and
    ADV used for the impact model are likewise shifted, so nothing on day d uses information past
    close[d-1].
  - Positions are only rebalanced when the (shifted) target changes — no daily churn from drift.
  - Per rebalance: orders are clipped to the ADV participation cap, halted/circuit names are
    skipped (no fill), and explicit costs + market impact are charged to cash.

The engine consumes target weights (the strategy/execution contract); it is agnostic to how the
weights were produced. Signed weights are allowed (the short leg's tradeability is a strategy
concern handled upstream).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_pilot.engine.backtest.costs import CostConfig, Segment, total_costs_vec
from quant_pilot.engine.backtest.impact import ImpactConfig, cap_quantity_vec, impact_cost_vec


@dataclass
class PriceData:
    open: pd.DataFrame  # dates × symbols
    close: pd.DataFrame
    volume: pd.DataFrame | None = None  # shares; enables the ADV participation cap
    halted: pd.DataFrame | None = None  # bool; True = at circuit / untradeable that day


@dataclass
class BacktestResult:
    equity: pd.Series  # close-to-close portfolio value
    returns: pd.Series  # daily returns
    positions: pd.DataFrame  # shares held at each close
    weights: pd.DataFrame  # realized weights at each close
    costs: pd.Series  # total costs charged each day
    turnover: pd.Series  # traded notional each day
    summary: dict[str, float]


class BacktestEngine:
    def __init__(
        self,
        cost_config: CostConfig | None = None,
        impact_config: ImpactConfig | None = None,
        initial_capital: float = 1_000_000.0,
        segment: Segment = "delivery",
        vol_window: int = 20,
        adv_window: int = 20,
    ) -> None:
        self.costs = cost_config or CostConfig()
        self.impact = impact_config or ImpactConfig()
        self.initial_capital = initial_capital
        self.segment = segment
        self.vol_window = vol_window
        self.adv_window = adv_window

    def run(self, prices: PriceData, target_weights: pd.DataFrame) -> BacktestResult:
        dates = prices.open.index
        symbols = list(prices.open.columns)

        open_ = prices.open.to_numpy(dtype=float)
        close = prices.close.reindex(index=dates, columns=symbols).to_numpy(dtype=float)

        # Exec target: hold between rebalances (ffill), then shift one bar (decide t, fill t+1).
        et = (
            target_weights.reindex(index=dates, columns=symbols)
            .ffill()
            .shift(1)
            .fillna(0.0)
            .to_numpy(dtype=float)
        )

        adv = self._trailing(prices.volume, dates, symbols, self.adv_window, median=True)
        vol = self._trailing_vol(prices.close, dates, symbols, self.vol_window)
        halted = (
            prices.halted.reindex(index=dates, columns=symbols).fillna(False).to_numpy(dtype=bool)
            if prices.halted is not None
            else np.zeros((len(dates), len(symbols)), dtype=bool)
        )

        n_days, n_sym = open_.shape
        shares = np.zeros(n_sym)
        cash = self.initial_capital
        prev_target = np.zeros(n_sym)

        equity_curve = np.empty(n_days)
        cost_series = np.zeros(n_days)
        turnover_series = np.zeros(n_days)
        positions = np.empty((n_days, n_sym))

        for d in range(n_days):
            o, c, tw = open_[d], close[d], et[d]
            if d == 0 or not np.array_equal(tw, prev_target):
                cost_series[d], turnover_series[d], cash = self._rebalance(
                    o, tw, shares, cash, adv[d], vol[d], halted[d]
                )
                prev_target = tw
            positions[d] = shares
            equity_curve[d] = cash + np.nansum(np.nan_to_num(shares * c))

        equity = pd.Series(equity_curve, index=dates, name="equity")
        pos_df = pd.DataFrame(positions, index=dates, columns=symbols)
        weights = pos_df * prices.close.reindex(index=dates, columns=symbols)
        weights = weights.div(equity.replace(0, np.nan), axis=0).fillna(0.0)

        return BacktestResult(
            equity=equity,
            returns=equity.pct_change().fillna(0.0),
            positions=pos_df,
            weights=weights,
            costs=pd.Series(cost_series, index=dates, name="costs"),
            turnover=pd.Series(turnover_series, index=dates, name="turnover"),
            summary=self._summary(equity, cost_series, turnover_series),
        )

    # --- internals ----------------------------------------------------------

    def _rebalance(self, o, tw, shares, cash, adv_row, vol_row, halted_row):
        tradeable = np.isfinite(o) & (o > 0) & ~halted_row
        equity_open = cash + np.nansum(np.nan_to_num(shares * o))

        target_shares = np.where(
            tradeable & (o > 0), tw * equity_open / np.where(o > 0, o, 1.0), shares
        )
        desired = np.where(tradeable, target_shares - shares, 0.0)
        filled = cap_quantity_vec(desired, adv_row, self.impact.max_adv_participation)

        explicit = total_costs_vec(o, filled, self.costs, self.segment)
        impact = impact_cost_vec(filled, o, adv_row, vol_row, self.impact)
        trade_cost = float(np.nansum(np.nan_to_num(explicit + impact)))
        turnover = float(np.nansum(np.nan_to_num(np.abs(filled) * o)))

        cash = cash - float(np.nansum(np.nan_to_num(filled * o))) - trade_cost
        shares += np.nan_to_num(filled)
        return trade_cost, turnover, cash

    def _trailing(self, frame, dates, symbols, window, median):
        if frame is None:
            return np.full((len(dates), len(symbols)), np.nan)
        f = frame.reindex(index=dates, columns=symbols)
        roll = f.rolling(window).median() if median else f.rolling(window).mean()
        return roll.shift(1).to_numpy(dtype=float)

    def _trailing_vol(self, close, dates, symbols, window):
        rets = close.reindex(index=dates, columns=symbols).pct_change()
        return rets.rolling(window).std().shift(1).to_numpy(dtype=float)

    def _summary(self, equity, costs, turnover):
        final = float(equity.iloc[-1])
        initial = self.initial_capital
        return {
            "initial_capital": initial,
            "final_equity": final,
            "total_return": final / initial - 1.0,
            "total_costs": float(np.nansum(costs)),
            "total_turnover": float(np.nansum(turnover)),
            "n_rebalances": float(int((turnover > 0).sum())),
        }
