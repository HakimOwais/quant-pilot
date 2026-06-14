"""Black-Scholes pricing, Greeks, and implied-vol solver — implemented from scratch.

Per MASTER_PROMPT this is the option *machinery* (used to validate Monte-Carlo pricing and to
back the IV solver); it is NOT the regime signal — the real signal is the variance risk
premium built on India VIX (a later phase). Continuous dividend yield `q` is supported
(defaults to 0). All inputs are scalars.

Conventions:
  - theta is per YEAR (divide by 365 for per-calendar-day).
  - vega is per 1.00 change in vol (divide by 100 for per 1%).
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel

OptionType = Literal["call", "put"]

_SQRT_2 = math.sqrt(2.0)
_SQRT_2PI = math.sqrt(2.0 * math.pi)


class Greeks(BaseModel):
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / _SQRT_2))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / _SQRT_2PI


def _d1_d2(S: float, K: float, T: float, r: float, sigma: float, q: float) -> tuple[float, float]:
    vol = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vol
    return d1, d1 - vol


def _intrinsic(S: float, K: float, option_type: OptionType) -> float:
    return max(S - K, 0.0) if option_type == "call" else max(K - S, 0.0)


def bs_price(
    S: float, K: float, T: float, r: float, sigma: float, option_type: OptionType, q: float = 0.0
) -> float:
    if T <= 0.0 or sigma <= 0.0:
        return _intrinsic(S, K, option_type)
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    disc_q, disc_r = math.exp(-q * T), math.exp(-r * T)
    if option_type == "call":
        return S * disc_q * _norm_cdf(d1) - K * disc_r * _norm_cdf(d2)
    return K * disc_r * _norm_cdf(-d2) - S * disc_q * _norm_cdf(-d1)


def bs_call_price(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> float:
    return bs_price(S, K, T, r, sigma, "call", q)


def bs_put_price(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> float:
    return bs_price(S, K, T, r, sigma, "put", q)


def bs_vega(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> float:
    if T <= 0.0 or sigma <= 0.0:
        return 0.0
    d1, _ = _d1_d2(S, K, T, r, sigma, q)
    return S * math.exp(-q * T) * _norm_pdf(d1) * math.sqrt(T)


def bs_greeks(
    S: float, K: float, T: float, r: float, sigma: float, option_type: OptionType, q: float = 0.0
) -> Greeks:
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    disc_q, disc_r = math.exp(-q * T), math.exp(-r * T)
    pdf = _norm_pdf(d1)
    sqrt_t = math.sqrt(T)
    gamma = disc_q * pdf / (S * sigma * sqrt_t)
    vega = S * disc_q * pdf * sqrt_t
    common_theta = -S * disc_q * pdf * sigma / (2.0 * sqrt_t)
    if option_type == "call":
        delta = disc_q * _norm_cdf(d1)
        theta = common_theta - r * K * disc_r * _norm_cdf(d2) + q * S * disc_q * _norm_cdf(d1)
        rho = K * T * disc_r * _norm_cdf(d2)
    else:
        delta = disc_q * (_norm_cdf(d1) - 1.0)
        theta = common_theta + r * K * disc_r * _norm_cdf(-d2) - q * S * disc_q * _norm_cdf(-d1)
        rho = -K * T * disc_r * _norm_cdf(-d2)
    return Greeks(delta=delta, gamma=gamma, theta=theta, vega=vega, rho=rho)


def implied_volatility(
    market_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    option_type: OptionType,
    q: float = 0.0,
    tol: float = 1e-7,
    max_iter: int = 100,
) -> float:
    """Newton-Raphson IV with a bisection fallback. Raises if the price is outside no-arb bounds."""
    if T <= 0.0:
        raise ValueError("implied_volatility requires T > 0")

    disc_q, disc_r = math.exp(-q * T), math.exp(-r * T)
    lower = (
        max(0.0, S * disc_q - K * disc_r)
        if option_type == "call"
        else max(0.0, K * disc_r - S * disc_q)
    )
    upper = S * disc_q if option_type == "call" else K * disc_r
    if not (lower - tol <= market_price <= upper + tol):
        raise ValueError(f"price {market_price} outside no-arbitrage bounds [{lower}, {upper}]")

    # Newton-Raphson from a Brenner-Subrahmanyam style seed.
    sigma = max(1e-3, math.sqrt(2.0 * math.pi / T) * market_price / S)
    for _ in range(max_iter):
        price = bs_price(S, K, T, r, sigma, option_type, q)
        diff = price - market_price
        if abs(diff) < tol:
            return sigma
        vega = bs_vega(S, K, T, r, sigma, q)
        if vega < 1e-10:
            break
        sigma = min(max(sigma - diff / vega, 1e-6), 5.0)

    # Bisection fallback on [1e-6, 5].
    lo, hi = 1e-6, 5.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        diff = bs_price(S, K, T, r, mid, option_type, q) - market_price
        if abs(diff) < tol:
            return mid
        if diff > 0:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)
