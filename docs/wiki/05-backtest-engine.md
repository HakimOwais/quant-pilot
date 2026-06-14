# Step 7–8 — Backtest Engine + Cost/Impact Model

**Build sequence:** 7–8 · **Status:** ✅ done

## Goal

A backtest engine that produces P&L which survives contact with the market: **no look-ahead**,
**next-bar fills**, the full **Indian explicit cost stack**, and — critically — a **market-impact
model** with an ADV participation cap and circuit guards. Costs come before the engine so nothing
is ever backtested frictionlessly.

## What was built — [`engine/backtest/`](../../src/quant_pilot/engine/backtest/)

### [`costs.py`](../../src/quant_pilot/engine/backtest/costs.py) — explicit costs
`CostConfig` (mirrors `settings.yaml: transaction_costs`) + `compute_costs` →
`CostBreakdown(brokerage, stt, exchange, gst, sebi, stamp, total)`:
- brokerage = min(₹20, 0.03% × turnover)
- STT 0.1% both legs (delivery) / 0.025% sell-only (intraday)
- exchange 0.00335%, GST 18% on (brokerage+exchange), SEBI ₹10/cr, stamp 0.015% buy-side
- `total_costs_vec` — the vectorized form the engine calls per rebalance (same formula).

### [`impact.py`](../../src/quant_pilot/engine/backtest/impact.py) — the dominant cost
`ImpactConfig` + `compute_impact`:
`impact_fraction = k·daily_vol·√participation + ½·spread + slippage_buffer`,
`participation = |qty| / ADV_shares`. Plus `cap_quantity` — clip orders to
`max_adv_participation × ADV` (no cap when ADV is unknown). Vectorized `*_vec` forms for the engine.

### [`engine.py`](../../src/quant_pilot/engine/backtest/engine.py) — the engine
`BacktestEngine(cost_config, impact_config, initial_capital, segment, vol_window, adv_window)` with
`run(prices: PriceData, target_weights) -> BacktestResult`.
- `PriceData(open, close, volume?, halted?)`; `BacktestResult(equity, returns, positions, weights,
  costs, turnover, summary)`.
- Decisions at close[t] execute at **open[t+1]** (`target_weights` ffill → shift(1)); trailing vol
  and ADV are also `shift(1)`. **Nothing on day d uses data past close[d-1].**
- Rebalances **only when the target changes** (no daily drift churn); per rebalance applies the ADV
  cap, skips halted/circuit names, and charges explicit + impact costs to cash.

## Design decisions & why

- **Costs/impact as standalone, tested modules** — impact is the #1 way Indian backtests lie, so
  it is first-class, not an afterthought; `compute_*` (scalar) is the readable/tested truth and the
  engine uses the matching vectorized form.
- **Target-weights contract.** The engine executes weights; it doesn't know how they were produced.
  This cleanly separates strategy (momentum/pairs, later) from execution mechanics, and allows
  signed weights for the future pairs short leg.
- **Two shifts = no look-ahead, provably.** Target, vol, and ADV are all lagged one bar; a signal
  computed on the last day can never trade (tested).
- **Rebalance-on-change** avoids the classic cost-bleed of re-solving to target every day as prices
  drift — matches monthly rebalancing reality.
- **Daily loop, per-day vectorized.** ~2,500 day iterations with numpy across symbols — correct and
  fast enough; fully vectorizing the path is a later optimization if needed.

## How to use

```python
from quant_pilot.engine.backtest.engine import BacktestEngine, PriceData
from quant_pilot.engine.backtest.costs import CostConfig
from quant_pilot.engine.backtest.impact import ImpactConfig

engine = BacktestEngine(CostConfig(), ImpactConfig(), initial_capital=1_000_000)
result = engine.run(PriceData(open=opens, close=closes, volume=vols), target_weights=weights)
result.summary    # initial/final equity, total_return, total_costs, total_turnover, n_rebalances
result.equity     # close-to-close equity curve
```

Cost/impact config can be loaded straight from the YAML: `CostConfig.model_validate(tc_dict)` and
`ImpactConfig.model_validate(tc_dict)` (each ignores the other's keys).

## Tests & verification

- `tests/test_costs_impact.py` — exact Indian cost breakdown (buy total ₹15.4453 on ₹10k turnover),
  no stamp on sells, intraday STT sell-only, flat-fee cap on big orders, scalar↔vector parity;
  square-root impact (₹200 / ₹250 with slippage), ADV cap (+ unknown-ADV no-cap), vector parity.
- `tests/test_backtest_engine.py` — buy-and-hold where costs reduce equity by exactly ₹1714.13;
  **last-day signal never trades** (no look-ahead); ADV cap limits the fill to 5,000 of 10,000
  desired; **circuit halt blocks the fill**.
- **64 tests total**; `ruff`, `mypy` (54 files), `pytest` all green.

## Gotchas

- Quoted spread isn't in daily bars, so `assumed_spread_bps` defaults to 0 — the slippage buffer +
  temporary impact carry the cost until intraday quotes are wired (consistent with Step 3).
- Targeting 100% weight then paying costs makes cash slightly negative (a hair over fully invested);
  position-sizing/cash-buffer rules live in the risk layer (later), not the engine.
- Impact during the ADV/vol warmup window is under-estimated (trailing stats are NaN → no cap, zero
  temporary impact); strategies generally don't trade during warmup.

## Next

Momentum strategy (long-only factor tilt) end-to-end through the engine, then the
attribution + validation layer that proves residual alpha before any more strategies are added.
