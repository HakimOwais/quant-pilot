from __future__ import annotations

import math

import numpy as np
import pytest

from quant_pilot.engine.models.monte_carlo import (
    simulate_gbm,
    simulate_ou,
    stationary_bootstrap,
    var_cvar,
)


def test_gbm_shape_and_start():
    paths = simulate_gbm(100, 0.05, 0.2, 1.0, n_paths=1000, n_steps=50, seed=0)
    assert paths.shape == (1000, 51)
    assert np.allclose(paths[:, 0], 100.0)


def test_gbm_terminal_mean():
    s0, mu, t = 100.0, 0.08, 1.0
    paths = simulate_gbm(s0, mu, 0.2, t, n_paths=200_000, n_steps=1, seed=7)
    assert paths[:, -1].mean() == pytest.approx(s0 * math.exp(mu * t), rel=0.01)


def test_ou_reverts_to_mu():
    paths = simulate_ou(
        10.0, theta=2.0, mu=0.0, sigma=0.5, T=5.0, n_paths=5000, n_steps=500, seed=3
    )
    assert paths.shape == (5000, 501)
    assert abs(paths[:, -1].mean()) < 0.1  # pulled back to mu=0


def test_var_cvar_historical():
    returns = np.array([-0.10, -0.05, -0.02, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06])
    res = var_cvar(returns, alpha=0.9, method="historical")
    assert res.var > 0
    assert res.cvar >= res.var  # expected shortfall is at least as severe as VaR
    assert res.observations == 10


def test_var_cvar_student_t_is_fatter_tailed():
    rng = np.random.default_rng(11)
    returns = 0.01 * rng.standard_t(df=4, size=20_000)
    res = var_cvar(returns, alpha=0.99, method="student_t")
    assert res.var > 0
    assert res.cvar > res.var
    assert res.method == "student_t"


def test_stationary_bootstrap_shape_and_membership():
    returns = np.arange(20, dtype=float)
    boot = stationary_bootstrap(returns, expected_block=5, n_resamples=100, seed=0)
    assert boot.shape == (100, 20)
    assert set(np.unique(boot)).issubset(set(returns.tolist()))  # only resampled observed values
