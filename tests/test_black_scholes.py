from __future__ import annotations

import math

import pytest

from quant_pilot.engine.models.black_scholes import (
    bs_call_price,
    bs_greeks,
    bs_put_price,
    implied_volatility,
)


def test_call_price_textbook_value():
    # S=100, K=100, T=1, r=5%, sigma=20%  ->  call ≈ 10.4506 (standard reference)
    assert bs_call_price(100, 100, 1.0, 0.05, 0.20) == pytest.approx(10.4506, abs=1e-3)


def test_put_call_parity():
    s, k, t, r, sigma = 100, 95, 0.75, 0.04, 0.25
    call = bs_call_price(s, k, t, r, sigma)
    put = bs_put_price(s, k, t, r, sigma)
    assert call - put == pytest.approx(s - k * math.exp(-r * t), abs=1e-9)


def test_implied_vol_roundtrip():
    s, k, t, r, true_sigma = 100, 110, 0.5, 0.03, 0.28
    price = bs_call_price(s, k, t, r, true_sigma)
    iv = implied_volatility(price, s, k, t, r, "call")
    assert iv == pytest.approx(true_sigma, abs=1e-5)


def test_implied_vol_put_roundtrip():
    s, k, t, r, true_sigma = 100, 90, 1.0, 0.05, 0.35
    price = bs_put_price(s, k, t, r, true_sigma)
    assert implied_volatility(price, s, k, t, r, "put") == pytest.approx(true_sigma, abs=1e-5)


def test_implied_vol_rejects_impossible_price():
    with pytest.raises(ValueError):
        implied_volatility(1000.0, 100, 100, 1.0, 0.05, "call")  # above S (upper bound)


def test_greeks_signs_and_relationships():
    s, k, t, r, sigma = 100, 100, 1.0, 0.05, 0.2
    call = bs_greeks(s, k, t, r, sigma, "call")
    put = bs_greeks(s, k, t, r, sigma, "put")
    assert 0.0 < call.delta < 1.0
    assert -1.0 < put.delta < 0.0
    # delta_call - delta_put = exp(-qT) = 1 with q=0
    assert call.delta - put.delta == pytest.approx(1.0, abs=1e-9)
    assert call.gamma > 0 and put.gamma == pytest.approx(call.gamma, abs=1e-12)
    assert call.vega > 0
    assert call.theta < 0  # long call decays


def test_intrinsic_at_expiry():
    assert bs_call_price(120, 100, 0.0, 0.05, 0.2) == pytest.approx(20.0)
    assert bs_put_price(80, 100, 0.0, 0.05, 0.2) == pytest.approx(20.0)
