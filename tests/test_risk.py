from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_pilot.engine.risk.config import RiskConfig
from quant_pilot.engine.risk.drawdown import DrawdownMonitor, drawdown_breaker_mask
from quant_pilot.engine.risk.position_sizing import (
    RiskManager,
    apply_position_caps,
    fractional_kelly,
    target_vol_scale,
)
from quant_pilot.engine.risk.var import cvar_position_size, portfolio_var_cvar

# --- position sizing --------------------------------------------------------


def test_fractional_kelly():
    # f* = mu/var = 0.001/0.0004 = 2.5 ; quarter Kelly -> 0.625
    assert fractional_kelly(0.001, 0.0004, fraction=0.25) == pytest.approx(0.625)
    assert fractional_kelly(-0.001, 0.0004, fraction=0.25) == pytest.approx(-0.625)
    assert fractional_kelly(0.01, 0.0, fraction=0.25) == 0.0  # no variance -> no position
    assert fractional_kelly(1.0, 0.0001, fraction=1.0, cap=1.0) == 1.0  # capped


def test_target_vol_scale():
    assert target_vol_scale(0.20, 0.10) == pytest.approx(0.5)  # de-lever
    assert target_vol_scale(0.05, 0.10, max_leverage=1.5) == 1.5  # capped, no over-lever
    assert target_vol_scale(0.0, 0.10) == 0.0


def test_position_caps_clip_and_sector_scale():
    w = pd.Series({"A": 0.08, "B": 0.03, "C": -0.07})
    sector = {"A": "tech", "B": "tech", "C": "bank"}
    capped = apply_position_caps(w, max_position_pct=0.05, sector_map=sector, max_sector_pct=0.07)
    assert capped["A"] == pytest.approx(0.05 * 0.07 / 0.08)  # tech (0.05+0.03) scaled to 0.07 gross
    assert capped["B"] == pytest.approx(0.03 * 0.07 / 0.08)
    assert capped["C"] == pytest.approx(-0.05)  # clipped to max position, bank under cap


def test_risk_manager_caps_frame():
    weights = pd.DataFrame({"A": [0.09, 0.0], "B": [0.0, -0.2]})
    capped = RiskManager(RiskConfig(max_position_pct=0.05)).cap_weights(weights)
    assert capped["A"].iloc[0] == pytest.approx(0.05)
    assert capped["B"].iloc[1] == pytest.approx(-0.05)


# --- VaR / CVaR sizing ------------------------------------------------------


def test_cvar_position_size_uses_tail_risk():
    rng = np.random.default_rng(0)
    returns = pd.Series(0.01 * rng.standard_t(df=5, size=5000))
    cfg = RiskConfig(risk_measure="cvar", var_distribution="student_t")
    res = portfolio_var_cvar(returns, cfg)
    size = cvar_position_size(0.01, returns, cfg)
    assert size == pytest.approx(0.01 / res.cvar)
    assert size > 0


# --- drawdown circuit breaker ----------------------------------------------


def test_drawdown_monitor_latches_halt():
    mon = DrawdownMonitor(max_drawdown=0.15)
    assert not mon.update(100).halted
    assert not mon.update(110).halted
    assert not mon.update(105).halted  # -4.5% dd, fine
    assert mon.update(90).halted  # 90/110-1 = -18% -> trip
    assert mon.update(120).halted  # latched even after recovery


def test_drawdown_breaker_mask():
    equity = pd.Series([100, 110, 105, 90, 120], dtype=float)
    allowed = drawdown_breaker_mask(equity, max_drawdown=0.15)
    assert allowed.tolist() == [True, True, True, False, False]  # halted from the breach onward
