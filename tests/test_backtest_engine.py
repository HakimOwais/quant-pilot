from __future__ import annotations

import pandas as pd
import pytest

from quant_pilot.engine.backtest.costs import CostConfig
from quant_pilot.engine.backtest.engine import BacktestEngine, PriceData
from quant_pilot.engine.backtest.impact import ImpactConfig


def _flat_prices(n: int, symbols=("A",), price: float = 100.0, volume: float | None = None):
    dates = pd.bdate_range("2020-01-01", periods=n)
    frame = lambda v: pd.DataFrame(v, index=dates, columns=list(symbols))  # noqa: E731
    vol = frame(volume) if volume is not None else None
    return dates, PriceData(open=frame(price), close=frame(price), volume=vol)


def _weights(dates, when: int, symbol: str = "A") -> pd.DataFrame:
    w = pd.DataFrame(index=dates, columns=[symbol], dtype=float)
    w.loc[dates[when], symbol] = 1.0
    return w


def _engine(**kw):
    return BacktestEngine(
        cost_config=CostConfig(),
        impact_config=ImpactConfig(
            impact_k=0.9, max_adv_participation=0.1, slippage_buffer_bps=5.0
        ),
        **kw,
    )


def test_buy_and_hold_costs_reduce_equity():
    dates, prices = _flat_prices(5)
    result = _engine().run(prices, _weights(dates, when=0))

    # Decision at close[0] -> fill at open[1]; one rebalance only.
    assert result.summary["n_rebalances"] == 1.0
    assert result.equity.iloc[0] == pytest.approx(1_000_000.0)  # nothing held day 0
    assert result.positions.iloc[-1]["A"] == pytest.approx(10_000.0)
    # explicit 1214.13 (turnover 1e6) + impact 500 (5bps slippage) = 1714.13
    assert result.summary["total_costs"] == pytest.approx(1714.13, abs=0.01)
    assert result.equity.iloc[-1] == pytest.approx(1_000_000.0 - 1714.13, abs=0.01)


def test_no_lookahead_last_day_signal_never_trades():
    dates, prices = _flat_prices(6)
    result = _engine().run(prices, _weights(dates, when=5))  # decided on the final close
    assert result.summary["total_turnover"] == 0.0
    assert result.equity.iloc[-1] == pytest.approx(1_000_000.0)


def test_adv_participation_cap_limits_fill():
    dates, prices = _flat_prices(10, volume=50_000.0)
    # rebalance after the ADV warmup so the cap is active
    result = _engine(vol_window=3, adv_window=3).run(prices, _weights(dates, when=5))
    # desired 10,000 shares but capped to 10% of ADV 50,000 = 5,000
    assert result.positions.iloc[-1]["A"] == pytest.approx(5_000.0)


def test_circuit_halt_blocks_fill():
    dates, prices = _flat_prices(5)
    prices.halted = pd.DataFrame(False, index=dates, columns=["A"])
    prices.halted.loc[dates[1], "A"] = True  # halted on the would-be fill day

    result = _engine().run(prices, _weights(dates, when=0))
    assert result.positions.iloc[-1]["A"] == 0.0
    assert result.summary["total_turnover"] == 0.0
