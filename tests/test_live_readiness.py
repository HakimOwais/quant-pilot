from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_pilot.domain.models import OrderSide, Position
from quant_pilot.live.pnl import pnl_divergence
from quant_pilot.live.reconciliation import reconcile_positions
from quant_pilot.live.slippage import SlippageMonitor

# --- reconciliation ---------------------------------------------------------


def test_reconciliation_matches():
    broker = [Position(symbol="A", quantity=100, avg_price=10.0)]
    report = reconcile_positions(broker, {"A": 100})
    assert report.ok
    assert report.mismatches == []


def test_reconciliation_detects_mismatch():
    broker = [Position(symbol="A", quantity=100, avg_price=10.0)]
    report = reconcile_positions(broker, {"A": 90, "B": 5})
    assert not report.ok
    syms = {m.symbol for m in report.mismatches}
    assert syms == {"A", "B"}  # A differs, B exists only in the book


# --- slippage ---------------------------------------------------------------


def test_slippage_adverse_is_positive_and_flags():
    mon = SlippageMonitor(threshold_bps=20.0)
    # buy filled above expected -> adverse
    assert mon.record(OrderSide.BUY, 100.0, 100.5) == pytest.approx(50.0)  # +50 bps
    # sell filled below expected -> adverse
    assert mon.record(OrderSide.SELL, 100.0, 99.7) == pytest.approx(30.0)
    report = mon.report()
    assert report.n == 2
    assert report.flagged  # mean 40 bps > 20 threshold


def test_slippage_favorable_not_flagged():
    mon = SlippageMonitor(threshold_bps=20.0)
    mon.record(OrderSide.BUY, 100.0, 99.9)  # filled below expected -> favorable (negative)
    assert not mon.report().flagged


# --- paper vs sim P&L -------------------------------------------------------


def test_pnl_tracks_when_close():
    rng = np.random.default_rng(0)
    sim = pd.Series(rng.normal(0.0005, 0.01, 500))
    live = sim + rng.normal(0, 0.0005, 500)  # small noise around sim
    res = pnl_divergence(live, sim, max_tracking_error=0.02)
    assert res.ok
    assert res.correlation > 0.9


def test_pnl_flags_divergence():
    rng = np.random.default_rng(1)
    sim = pd.Series(rng.normal(0.0005, 0.01, 500))
    live = pd.Series(rng.normal(0.0005, 0.05, 500))  # unrelated, high vol
    res = pnl_divergence(live, sim, max_tracking_error=0.02)
    assert not res.ok
