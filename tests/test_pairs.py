from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from quant_pilot.engine.backtest.engine import BacktestEngine, PriceData
from quant_pilot.engine.models.ou_process import OUParams, fit_ou
from quant_pilot.engine.strategies.cointegration import (
    benjamini_hochberg,
    cusum_break,
    engle_granger,
)
from quant_pilot.engine.strategies.pairs_trading import (
    PairConfig,
    PairsStrategy,
    ValidatedPair,
    pair_leg_weights,
    reversion_robustness,
    select_pairs,
)


def _exact_ou(theta, mu, sigma, n, seed):
    rng = np.random.default_rng(seed)
    b = math.exp(-theta)
    sd = sigma * math.sqrt((1 - math.exp(-2 * theta)) / (2 * theta))
    x = np.empty(n)
    x[0] = mu
    for t in range(1, n):
        x[t] = mu + (x[t - 1] - mu) * b + sd * rng.standard_normal()
    return x


def _cointegrated_close(n=800, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2018-01-01", periods=n)
    x = 100 + np.cumsum(rng.normal(0, 8, n))  # random walk with strong variation (pins the hedge)
    spread = _exact_ou(math.log(2) / 15, 0.0, 0.5, n, seed + 1)  # half-life ~15d
    y = 10 + 1.5 * x + spread  # cointegrated with X
    x2 = 100 + np.cumsum(rng.normal(0, 1, n))  # independent walks (not cointegrated)
    y2 = 50 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame({"Y": y, "X": x, "Y2": y2, "X2": x2}, index=dates)


# --- cointegration primitives ----------------------------------------------


def test_engle_granger_detects_cointegration():
    close = _cointegrated_close()
    hedge, _, p_good = engle_granger(close["Y"], close["X"])
    _, _, p_bad = engle_granger(close["Y2"], close["X2"])
    assert hedge == pytest.approx(1.5, abs=0.1)
    assert p_good < 0.05
    assert p_bad > 0.05


def test_benjamini_hochberg_mask():
    assert benjamini_hochberg([0.001, 0.02, 0.5, 0.9], alpha=0.05) == [True, True, False, False]
    assert benjamini_hochberg([0.9, 0.8, 0.7]) == [False, False, False]


def test_cusum_detects_structural_break():
    rng = np.random.default_rng(0)
    stable = rng.normal(0, 1, 300)
    shifted = np.concatenate([rng.normal(0, 1, 150), rng.normal(8, 1, 150)])
    assert cusum_break(stable) is False
    assert cusum_break(shifted) is True


# --- selection --------------------------------------------------------------


def test_select_pairs_keeps_only_validated():
    close = _cointegrated_close()
    pairs = select_pairs([("Y", "X"), ("Y2", "X2")], close)
    assert len(pairs) == 1
    p = pairs[0]
    assert (p.y, p.x) == ("Y", "X")
    assert p.hedge_ratio == pytest.approx(1.5, abs=0.1)
    assert 5.0 <= p.ou.half_life <= 60.0


def test_ssf_filter_excludes_pairs_without_both_legs():
    close = _cointegrated_close()
    assert select_pairs([("Y", "X")], close, ssf_eligible={"Y2", "X2"}) == []


# --- signals ----------------------------------------------------------------


def _pair(hedge=1.0):
    ou = OUParams(
        theta=0.05, mu=0.0, sigma=1.0, half_life=math.log(2) / 0.05, is_mean_reverting=True
    )
    return ValidatedPair(y="Y", x="X", hedge_ratio=hedge, intercept=0.0, pvalue=0.01, ou=ou)


def test_signal_enters_on_zscore_excursion():
    n = 200
    idx = pd.bdate_range("2020-01-01", periods=n)
    rng = np.random.default_rng(1)
    spread = rng.normal(0, 1, n)
    spread[120] = -4.0  # deep dip -> z well below -2 -> long the spread
    cy = pd.Series(100 + spread, index=idx)
    cx = pd.Series(100.0, index=idx)

    wy, wx = pair_leg_weights(cy, cx, _pair(), PairConfig(zscore_window=60))
    assert (wy > 0).any()  # long-spread position opened
    assert (wx < 0).any()  # short the X leg


def test_structural_break_retires_pair():
    n = 240
    idx = pd.bdate_range("2020-01-01", periods=n)
    rng = np.random.default_rng(2)
    spread = np.concatenate([rng.normal(0, 1, 120), np.linspace(0, 30, 120)])  # regime shift
    cy = pd.Series(100 + spread, index=idx)
    cx = pd.Series(100.0, index=idx)

    wy, _ = pair_leg_weights(cy, cx, _pair(), PairConfig(zscore_window=40))
    assert cusum_break(spread) is True
    assert wy.iloc[-1] == 0.0  # forced flat / retired after the break


# --- end to end + robustness -----------------------------------------------


def test_pairs_through_engine_runs():
    # clean pair with the true hedge so the spread is pure OU and signals fire
    n = 400
    idx = pd.bdate_range("2020-01-01", periods=n)
    rng = np.random.default_rng(7)
    x = 100 + np.cumsum(rng.normal(0, 1, n))
    spread = _exact_ou(math.log(2) / 15, 0.0, 1.0, n, 8)
    y = 1.5 * x + spread
    close = pd.DataFrame({"A": y, "B": x}, index=idx)
    pair = ValidatedPair(
        y="A", x="B", hedge_ratio=1.5, intercept=0.0, pvalue=0.01, ou=fit_ou(spread)
    )

    weights = PairsStrategy([pair]).generate_weights(close)
    vol = pd.DataFrame(1e9, index=close.index, columns=close.columns)
    result = BacktestEngine().run(PriceData(open=close, close=close, volume=vol), weights)
    assert result.equity.notna().all()
    assert np.isfinite(result.summary["final_equity"])
    assert result.summary["n_rebalances"] >= 1.0


def test_reversion_robustness_decays_with_weaker_theta():
    ou = OUParams(theta=0.1, mu=0.0, sigma=0.3, half_life=math.log(2) / 0.1, is_mean_reverting=True)
    r = reversion_robustness(ou, horizon_days=30, n_paths=3000, decay=0.5, seed=0)
    assert r["nominal"] > r["stressed"]  # weaker mean reversion -> less likely to revert
