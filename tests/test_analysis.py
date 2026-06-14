from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_pilot.engine.analysis.attribution import factor_attribution
from quant_pilot.engine.analysis.performance import drawdown_series, performance_stats
from quant_pilot.engine.analysis.validation import (
    bootstrap_sharpe_ci,
    deflated_sharpe_ratio,
    probabilistic_sharpe_ratio,
    sharpe_significance,
)


def _returns(mean, sd, n, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    return pd.Series(mean + sd * rng.standard_normal(n), index=idx)


# --- performance ------------------------------------------------------------


def test_performance_basic_stats():
    r = _returns(0.0008, 0.01, 1500)
    stats = performance_stats(r)
    assert stats.n_periods == 1500
    assert stats.total_return > 0
    assert stats.sharpe > 0
    assert stats.max_drawdown <= 0
    assert 0.0 <= stats.hit_rate <= 1.0


def test_drawdown_detected():
    # up 10 days then a sharp fall
    r = pd.Series([0.01] * 10 + [-0.2, -0.2] + [0.0] * 5)
    dd = drawdown_series(r)
    assert dd.min() < -0.3
    assert performance_stats(r).max_drawdown < -0.3


def test_sharpe_zero_on_flat_returns():
    r = pd.Series([0.0] * 100)
    assert performance_stats(r).sharpe == 0.0


# --- attribution ------------------------------------------------------------


def test_attribution_recovers_beta_and_alpha():
    rng = np.random.default_rng(1)
    n = 2000
    idx = pd.bdate_range("2015-01-01", periods=n)
    market = pd.Series(0.0004 + 0.01 * rng.standard_normal(n), index=idx)
    daily_alpha = 0.0004
    strat = 1.2 * market + daily_alpha + 0.002 * rng.standard_normal(n)
    res = factor_attribution(strat, pd.DataFrame({"market": market}))
    assert res.betas["market"] == pytest.approx(1.2, abs=0.05)
    assert res.alpha_annual == pytest.approx(daily_alpha * 252, abs=0.03)
    assert res.alpha_is_significant  # real alpha -> significant t-stat


def test_attribution_pure_beta_has_no_alpha():
    rng = np.random.default_rng(2)
    n = 2000
    idx = pd.bdate_range("2015-01-01", periods=n)
    market = pd.Series(0.0004 + 0.01 * rng.standard_normal(n), index=idx)
    strat = 0.9 * market + 0.002 * rng.standard_normal(n)  # no alpha term
    res = factor_attribution(strat, pd.DataFrame({"market": market}))
    assert res.betas["market"] == pytest.approx(0.9, abs=0.05)
    assert not res.alpha_is_significant  # beta exposure, not skill


# --- validation -------------------------------------------------------------


def test_psr_high_for_clear_positive_sharpe():
    r = _returns(0.0008, 0.01, 2000)
    assert 0.0 <= probabilistic_sharpe_ratio(r) <= 1.0
    assert probabilistic_sharpe_ratio(r) > 0.9


def test_deflated_sharpe_decreases_with_more_trials():
    r = _returns(0.0008, 0.01, 2000)
    psr = probabilistic_sharpe_ratio(r)
    dsr_50 = deflated_sharpe_ratio(r, n_trials=50)
    dsr_1000 = deflated_sharpe_ratio(r, n_trials=1000)
    assert dsr_50 <= psr  # deflation never increases significance
    assert dsr_1000 <= dsr_50  # more trials -> harder to clear


def test_bootstrap_ci_brackets_point_estimate():
    r = _returns(0.0008, 0.01, 2000, seed=3)
    lo, hi = bootstrap_sharpe_ci(r, n_resamples=500, seed=3)
    point = sharpe_significance(r, n_resamples=200, seed=3).sharpe
    assert lo < hi
    assert lo < point < hi


def test_sharpe_significance_bundle():
    r = _returns(0.0008, 0.01, 1500, seed=4)
    sig = sharpe_significance(r, n_trials=100, n_resamples=300, seed=4)
    assert sig.sharpe > 0
    assert sig.deflated_sharpe <= sig.probabilistic_sharpe
    assert sig.p_value == pytest.approx(1.0 - sig.probabilistic_sharpe)
