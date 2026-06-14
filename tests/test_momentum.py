from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from quant_pilot.engine.backtest.engine import BacktestEngine, PriceData
from quant_pilot.engine.data.universe import UniverseMembership, membership_matrix
from quant_pilot.engine.strategies.momentum import MomentumConfig, MomentumStrategy


def _trending_prices(n: int = 300):
    dates = pd.bdate_range("2020-01-01", periods=n)
    t = np.arange(n)
    return pd.DataFrame(
        {
            "WIN": 100 * 1.0015**t,  # strong uptrend
            "FLAT": np.full(n, 100.0),
            "LOSE": 100 * 0.9985**t,  # downtrend
        },
        index=dates,
    )


def test_selects_the_winner():
    close = _trending_prices()
    weights = MomentumStrategy().generate_weights(close)
    last = weights.iloc[-1]
    assert last["WIN"] == max(last)
    assert last["WIN"] > 0.9  # ~full weight (single name, scale 1.0)
    assert last["LOSE"] == 0.0
    assert last["FLAT"] == 0.0


def test_membership_excludes_ineligible_winner():
    close = _trending_prices()
    dates = close.index
    # WIN is NOT a member; FLAT and LOSE are members the whole time
    intervals = [
        UniverseMembership(index="NIFTY50", symbol="FLAT", effective_from=date(2019, 1, 1)),
        UniverseMembership(index="NIFTY50", symbol="LOSE", effective_from=date(2019, 1, 1)),
    ]
    mask = membership_matrix(intervals, dates, list(close.columns))
    weights = MomentumStrategy().generate_weights(close, membership=mask)
    last = weights.iloc[-1]
    assert last["WIN"] == 0.0  # excluded despite best momentum
    assert last["FLAT"] > 0.0  # next eligible name chosen


def test_inverse_vol_sizing_favours_lower_vol():
    dates = pd.bdate_range("2020-01-01", periods=300)
    t = np.arange(300)
    rng = np.random.default_rng(0)
    steady = 100 * 1.001**t
    noisy = steady * (1 + 0.05 * rng.standard_normal(300))  # same drift, higher vol
    close = pd.DataFrame({"STEADY": steady, "NOISY": noisy}, index=dates)

    cfg = MomentumConfig(long_pct=1.0)  # select both
    last = MomentumStrategy(cfg).generate_weights(close).iloc[-1]
    assert last["STEADY"] > last["NOISY"] > 0.0


def test_vrp_regime_reduces_gross_exposure():
    close = _trending_prices()
    rebal = MomentumStrategy()._rebalance_dates(close.index)
    calm = pd.Series(0.0, index=close.index)
    fearful = pd.Series(np.linspace(0, 1, len(close.index)), index=close.index)  # rising VRP

    w_calm = MomentumStrategy().generate_weights(close, vrp=calm).loc[rebal[-1]].sum()
    w_fear = MomentumStrategy().generate_weights(close, vrp=fearful).loc[rebal[-1]].sum()
    assert w_calm == pytest.approx(1.0)  # flat VRP -> full exposure
    assert w_fear < w_calm  # de-risked when the VRP percentile is high


def test_momentum_through_engine_is_profitable_net_of_costs():
    close = _trending_prices()
    weights = MomentumStrategy().generate_weights(close)
    prices = PriceData(open=close, close=close)  # fill at open == close for simplicity
    result = BacktestEngine().run(prices, weights)
    assert result.summary["total_return"] > 0.0  # WIN trend dominates costs
    assert result.summary["total_costs"] > 0.0
    assert result.summary["n_rebalances"] >= 1.0
