from __future__ import annotations

import math

import numpy as np
import pytest

from quant_pilot.engine.models.ou_process import (
    equilibrium_std,
    fit_ou,
    half_life,
    ou_zscore,
)


def _exact_ou_series(theta, mu, sigma, dt, n, seed=0):
    """Generate an exact discrete OU/AR(1) series so the fit can be validated precisely."""
    rng = np.random.default_rng(seed)
    b = math.exp(-theta * dt)
    sd = sigma * math.sqrt((1.0 - math.exp(-2.0 * theta * dt)) / (2.0 * theta))
    x = np.empty(n)
    x[0] = mu
    for t in range(1, n):
        x[t] = mu + (x[t - 1] - mu) * b + sd * rng.standard_normal()
    return x


def test_half_life_formula():
    assert half_life(math.log(2.0)) == pytest.approx(1.0)
    assert half_life(0.0) == math.inf
    assert half_life(-0.5) == math.inf


def test_fit_recovers_known_params():
    series = _exact_ou_series(theta=0.5, mu=2.0, sigma=0.3, dt=1.0, n=20_000, seed=42)
    p = fit_ou(series, dt=1.0)
    assert p.is_mean_reverting
    assert p.theta == pytest.approx(0.5, abs=0.08)
    assert p.mu == pytest.approx(2.0, abs=0.1)
    assert p.sigma == pytest.approx(0.3, abs=0.03)
    assert p.half_life == pytest.approx(math.log(2.0) / p.theta, rel=1e-9)


def test_random_walk_is_not_mean_reverting():
    rng = np.random.default_rng(1)
    walk = np.cumsum(rng.standard_normal(5_000))
    p = fit_ou(walk)
    assert not p.is_mean_reverting
    assert p.half_life == math.inf


def test_zscore_uses_equilibrium_std():
    from quant_pilot.engine.models.ou_process import OUParams

    params = OUParams(
        theta=0.5, mu=2.0, sigma=0.3, half_life=math.log(2) / 0.5, is_mean_reverting=True
    )
    sd = equilibrium_std(0.5, 0.3)  # 0.3 / sqrt(1.0) = 0.3
    assert sd == pytest.approx(0.3)
    assert ou_zscore(2.0 + sd, params) == pytest.approx(1.0)
    assert ou_zscore(2.0 - 2 * sd, params) == pytest.approx(-2.0)
