# Step 5 — Mathematical Models (OU, Black-Scholes, Monte Carlo)

**Build sequence:** 4–6 · **Status:** ✅ done

## Goal

Implement the core quant math as pure engine modules: Ornstein-Uhlenbeck mean-reversion
(for pairs), Black-Scholes pricing/Greeks/IV (option machinery + VRP groundwork), and Monte
Carlo simulation + fat-tailed risk measures (for the risk layer). All numeric, deterministic
under a seed, and fully unit-tested.

## What was built — [`engine/models/`](../../src/quant_pilot/engine/models/)

### [`black_scholes.py`](../../src/quant_pilot/engine/models/black_scholes.py)
From scratch (no external BS library, per MASTER_PROMPT). Normal CDF via `math.erf`.
- `bs_call_price` / `bs_put_price` / `bs_price` — European pricing with continuous dividend `q`.
- `bs_greeks` → `Greeks(delta, gamma, theta, vega, rho)`; `bs_vega` helper.
- `implied_volatility` — Newton-Raphson (Brenner-Subrahmanyam seed) with a **bisection fallback**
  and no-arbitrage bound checks.

> This is option *machinery* — used to validate Monte-Carlo pricing and to back the IV solver.
> It is **not** the regime signal; the real signal is the variance risk premium on India VIX
> (a later phase), as corrected in MASTER_PROMPT.

### [`ou_process.py`](../../src/quant_pilot/engine/models/ou_process.py)
`dX = θ(μ − X)dt + σ dW`, fit by AR(1) OLS (`b = e^{−θdt}`).
- `fit_ou` → `OUParams(theta, mu, sigma, half_life, is_mean_reverting)`.
- `half_life`, `equilibrium_std`, `ou_zscore`, `spread_zscore`.

> **Mean-reversion is gated statistically**, not just numerically: `is_mean_reverting` requires
> the slope `b` to be *significantly* below 1 via a Dickey-Fuller-style t-stat
> `(b − 1)/SE(b) < −2`. Without this, a random walk's noisy slope (`b` slightly < 1) would be
> mislabelled mean-reverting with an absurd half-life. (Full ADF/cointegration arrives with the
> pairs phase + statsmodels; this is the lightweight gate.)

### [`monte_carlo.py`](../../src/quant_pilot/engine/models/monte_carlo.py)
- `simulate_gbm` (E[S_T] = S₀·e^{μT}) and `simulate_ou` (Euler) path matrices.
- `var_cvar(returns, alpha, method)` — `"historical"` or fat-tailed `"student_t"`; **CVaR
  (expected shortfall) reported alongside VaR** and is what risk sizing should use. VaR/CVaR are
  positive loss magnitudes.
- `stationary_bootstrap` — Politis-Romano geometric blocks that **preserve autocorrelation**.

> These encode three MASTER_PROMPT corrections: fat-tailed (Student-t) tails instead of
> Gaussian, CVaR over VaR for sizing, and a **block** bootstrap instead of an IID shuffle (which
> would destroy the very autocorrelation momentum/mean-reversion exploit).

## Design decisions & why

- **From-scratch Black-Scholes** keeps the model transparent and dependency-light; `math.erf`
  gives the normal CDF without scipy for pricing (scipy is only used for Student-t tails).
- **Newton + bisection** IV: Newton is fast where vega is healthy; bisection guarantees
  convergence for deep ITM/OTM where vega collapses.
- **OU via AR(1) OLS** is the standard, fast estimator; the t-stat gate makes the
  mean-reversion flag trustworthy for the pairs selector.
- **Seeded RNG** (`np.random.default_rng`) so simulations are reproducible in tests/backtests.
- **Pure engine, no IO** — these slot under the engine boundary and are consumed later by the
  pairs strategy, the VRP signal, and the risk/VaR layer via ports.

## How to use

```python
from quant_pilot.engine.models.black_scholes import bs_call_price, implied_volatility, bs_greeks
bs_call_price(100, 100, 1.0, 0.065, 0.20)             # ≈ 11.0 at r=6.5%
implied_volatility(10.45, 100, 100, 1.0, 0.05, "call")  # ≈ 0.20
bs_greeks(100, 100, 1.0, 0.05, 0.2, "call").delta

from quant_pilot.engine.models.ou_process import fit_ou, spread_zscore
p = fit_ou(spread_series, dt=1.0)                      # p.half_life, p.is_mean_reverting
z = spread_zscore(spread_series, p)                    # entry/exit signal for pairs

from quant_pilot.engine.models.monte_carlo import simulate_gbm, var_cvar
var_cvar(daily_returns, alpha=0.99, method="student_t")  # fat-tailed VaR + CVaR
```

## Tests & verification

- `tests/test_black_scholes.py` — textbook call value (10.4506), put-call parity, **IV
  round-trips** (call & put), no-arb rejection, Greek signs + `Δcall − Δput = e^{−qT}`, intrinsic.
- `tests/test_ou_process.py` — half-life formula, **param recovery** on an exact OU series,
  random walk → not mean-reverting, z-score against equilibrium std.
- `tests/test_monte_carlo.py` — GBM shape/start/terminal-mean, OU reverts to μ, historical &
  Student-t VaR/CVaR (CVaR ≥ VaR; t fatter), stationary bootstrap shape/membership.
- **51 tests total**; `ruff`, `mypy` (51 files), `pytest` all green.

## Gotchas

- `theta` (BS) is **per year** (÷365 for per-day); `vega` is per **1.00** vol (÷100 for per 1%).
- `simulate_ou` uses Euler discretization — fine for simulation/stress, but the *fit* test uses
  an exact AR(1) series so estimator accuracy is tested independently of the Euler scheme.
- Student-t CVaR uses the closed-form ES and needs `df > 1` (always true for fitted financial
  returns).

## Next

Backtest engine + the full cost model (explicit costs **and** the square-root market-impact
model with ADV participation), with next-bar fills and no look-ahead.
