from __future__ import annotations

import numpy as np
import pytest

from quant_pilot.engine.backtest.costs import CostConfig, compute_costs, total_costs_vec
from quant_pilot.engine.backtest.impact import (
    ImpactConfig,
    cap_quantity,
    cap_quantity_vec,
    compute_impact,
    impact_cost_vec,
)

CFG = CostConfig()


def test_delivery_buy_cost_breakdown():
    # price 100 × qty 100 -> turnover 10,000
    b = compute_costs("buy", 100, 100, CFG, "delivery")
    assert b.brokerage == pytest.approx(3.0)  # min(20, 0.03% of 10k = 3)
    assert b.stt == pytest.approx(10.0)  # 0.1% delivery, both sides
    assert b.exchange == pytest.approx(0.335)
    assert b.gst == pytest.approx(0.18 * (3.0 + 0.335))
    assert b.sebi == pytest.approx(0.01)
    assert b.stamp == pytest.approx(1.5)  # 0.015% buy side
    assert b.total == pytest.approx(15.4453, abs=1e-4)


def test_sell_has_no_stamp_duty():
    buy = compute_costs("buy", 100, 100, CFG, "delivery")
    sell = compute_costs("sell", 100, 100, CFG, "delivery")
    assert sell.stamp == 0.0
    assert sell.total == pytest.approx(buy.total - buy.stamp)


def test_intraday_stt_only_on_sell():
    assert compute_costs("buy", 100, 100, CFG, "intraday").stt == 0.0
    assert compute_costs("sell", 100, 100, CFG, "intraday").stt == pytest.approx(2.5)


def test_brokerage_is_flat_capped_on_large_orders():
    # turnover 1,000,000 -> 0.03% = 300, capped to flat 20
    assert compute_costs("buy", 100, 10_000, CFG, "delivery").brokerage == pytest.approx(20.0)


def test_vectorized_costs_match_scalar():
    prices = np.array([100.0, 100.0])
    qtys = np.array([100.0, -100.0])  # buy, sell
    vec = total_costs_vec(prices, qtys, CFG, "delivery")
    assert vec[0] == pytest.approx(compute_costs("buy", 100, 100, CFG).total)
    assert vec[1] == pytest.approx(compute_costs("sell", 100, 100, CFG).total)


# --- impact -----------------------------------------------------------------


def test_impact_square_root_law():
    cfg = ImpactConfig(impact_k=1.0, slippage_buffer_bps=0.0, assumed_spread_bps=0.0)
    res = compute_impact(1000, 100, adv_shares=100_000, daily_vol=0.02, config=cfg)
    assert res.participation == pytest.approx(0.01)
    # temp = 1.0 * 0.02 * sqrt(0.01) = 0.002 -> cost = 0.002 * 1000 * 100
    assert res.cost == pytest.approx(200.0)


def test_impact_includes_slippage_buffer():
    cfg = ImpactConfig(impact_k=1.0, slippage_buffer_bps=5.0, assumed_spread_bps=0.0)
    res = compute_impact(1000, 100, 100_000, 0.02, cfg)
    assert res.cost == pytest.approx(250.0)  # +5bps of 100,000 notional = +50


def test_adv_participation_cap():
    assert cap_quantity(10_000, adv_shares=50_000, max_participation=0.1) == 5_000
    assert cap_quantity(-10_000, 50_000, 0.1) == -5_000
    assert (
        cap_quantity(10_000, adv_shares=0.0, max_participation=0.1) == 10_000
    )  # unknown ADV: no cap


def test_vectorized_cap_and_impact():
    capped = cap_quantity_vec(np.array([10_000.0, -10_000.0]), np.array([50_000.0, np.nan]), 0.1)
    assert capped[0] == 5_000
    assert capped[1] == -10_000  # NaN ADV -> uncapped
    cost = impact_cost_vec(
        np.array([1000.0]),
        np.array([100.0]),
        np.array([100_000.0]),
        np.array([0.02]),
        ImpactConfig(impact_k=1.0, slippage_buffer_bps=0.0, assumed_spread_bps=0.0),
    )
    assert cost[0] == pytest.approx(200.0)
