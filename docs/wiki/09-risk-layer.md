# Step 13 — Risk Layer (sizing, caps, drawdown circuit breaker)

**Build sequence:** 13 · **Status:** ✅ done

## Goal

Turn raw strategy weights into risk-controlled positions and add the safety rails: fractional
Kelly / CVaR sizing, per-position and per-sector caps, and a latching drawdown circuit breaker.

## What was built — [`engine/risk/`](../../src/quant_pilot/engine/risk/)

### [`config.py`](../../src/quant_pilot/engine/risk/config.py)
`RiskConfig` (mirrors `settings.yaml: risk`): max position/sector %, VaR confidence, `risk_measure`
(cvar), `var_distribution` (student_t), `kelly_fraction` (0.25), `max_portfolio_drawdown` (0.15).

### [`position_sizing.py`](../../src/quant_pilot/engine/risk/position_sizing.py)
- `fractional_kelly(μ, σ², fraction)` — `fraction · μ/σ²`, **fractional only** (full Kelly on an
  estimated edge detonates), clipped to ±cap; 0 if variance ≤ 0.
- `target_vol_scale(realized, target, max_leverage)` — scale gross exposure toward a target vol.
- `apply_position_caps` — clip each weight to ±max_position, then scale down any sector over its
  gross cap.
- `RiskManager.cap_weights` — applies the caps across a whole weights DataFrame.

### [`var.py`](../../src/quant_pilot/engine/risk/var.py)
- `portfolio_var_cvar` — RiskConfig-driven wrapper over the MC VaR/CVaR engine (fat-tailed + CVaR
  by default).
- `cvar_position_size(risk_budget, returns)` — size = budget / tail-risk (CVaR, or VaR if configured).

### [`drawdown.py`](../../src/quant_pilot/engine/risk/drawdown.py)
- `DrawdownMonitor` — stateful live/loop form; tracks peak/drawdown and **latches halted** once the
  max drawdown is breached (a tripped breaker stays tripped until an explicit `reset()`).
- `drawdown_breaker_mask` — vectorized backtest form: allowed/halted mask over an equity curve.

## Design decisions & why

- **Fractional Kelly, never full.** Full Kelly assumes the edge is known; with estimated μ/σ² it
  oversizes catastrophically. ¼ Kelly (config) is the spec's rule.
- **CVaR over VaR for sizing**, fat-tailed by default — reuses the corrected MC risk module; VaR is
  blind to the shape of the tail it's sizing against.
- **Latching breaker.** A drawdown breach halts and *stays* halted — the conservative behavior; you
  don't want an automated system re-risking into a crash. Manual `reset()` is the deliberate
  re-entry. This is the engine-side counterpart to the live kill switch (SYSTEM_DESIGN §8).
- **Caps as a weights transform** keep the risk layer composable: strategy → `RiskManager` →
  engine, all on the same target-weights contract.

## How to use

```python
from quant_pilot.engine.risk.position_sizing import RiskManager
from quant_pilot.engine.risk.config import RiskConfig
from quant_pilot.engine.risk.drawdown import drawdown_breaker_mask

risked = RiskManager(RiskConfig(), sector_map=sectors).cap_weights(strategy_weights)
result = BacktestEngine().run(prices, risked)
allowed = drawdown_breaker_mask(result.equity, max_drawdown=0.15)   # diagnostic / live gate
```

Live loop: feed `DrawdownMonitor.update(equity)` each cycle; if `.halted`, flatten and stop.

## Tests & verification

- `tests/test_risk.py` — quarter-Kelly math (incl. cap + zero-variance), vol targeting (de-lever +
  leverage cap), position clip + **sector gross scaling**, `RiskManager` over a frame, CVaR sizing
  = budget / tail-risk, and the drawdown breaker **latching** (monitor + mask).
- **94 tests total**; `ruff`, `mypy` (65 files), `pytest` all green.

## Gotchas

- The drawdown breaker is currently a **diagnostic/live** tool; closing the loop *inside* the
  backtest (halting positions mid-run on a breach) would require engine integration — a deliberate
  next step, not done here, so backtests don't silently differ from live.
- `cvar_position_size` returns 0 when tail risk is non-positive (degenerate returns) — guard before
  dividing downstream.

## Next

The engine core is complete (data → models → strategies → backtest → attribution/validation →
risk). Natural next: **API read endpoints + job submission (SSE)** to surface runs to the dashboard,
or wire the **PaperBroker** behind the Broker port toward live readiness.
