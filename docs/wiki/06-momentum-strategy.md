# Step 9 — Momentum Strategy (long-only factor tilt)

**Build sequence:** 9 · **Status:** ✅ done

## Goal

The first strategy: cross-sectional momentum on the point-in-time NIFTY universe, producing target
weights the backtest engine executes. Framed **honestly as a long-only factor tilt** — whether it
is alpha is decided later by the attribution regression, not by the return here.

## What was built — [`engine/strategies/`](../../src/quant_pilot/engine/strategies/)

### [`base.py`](../../src/quant_pilot/engine/strategies/base.py)
`Strategy` ABC: `generate_weights(close) -> DataFrame` (rebalance-dates × symbols). A strategy owns
*what* to hold; the engine owns *how/when* (next-bar, costs, impact). Weights are sparse (rows only
on rebalance dates); the engine forward-fills.

### [`momentum.py`](../../src/quant_pilot/engine/strategies/momentum.py)
`MomentumConfig` + `MomentumStrategy`. Per monthly rebalance:
1. **Score** = mean over lookbacks (6 & 12m) of the return from `(lb+skip)` to `skip` months ago —
   skipping the last month to avoid short-term reversal (Jegadeesh-Titman).
2. **Eligibility** = point-in-time index membership mask ∩ valid score (survivorship-free).
3. **Select** the top `long_pct` (default 20%) by score.
4. **Size** by inverse 20-day realized vol, normalized.
5. **Regime-scale** gross exposure by the **VRP percentile** (de-risk when the variance risk
   premium is elevated) — adaptive, not hardcoded VIX levels.
6. Optional **no-trade band** suppresses sub-threshold weight changes (turnover control).

Plus a pure helper [`universe.membership_matrix`](../../src/quant_pilot/engine/data/universe.py)
turning PIT intervals into a boolean (dates × symbols) eligibility mask.

## Design decisions & why

- **Long-only, labelled as a tilt.** NSE cash can't be shorted; the module documents that this is a
  beta/size tilt and defers the alpha verdict to attribution (next step) — per the Production Mandate.
- **Target-weights output** plugs directly into the engine's contract; the strategy never touches
  fills, costs, or timing → testable in isolation.
- **Eligibility via the PIT mask** wires the survivorship-free universe into selection — a dropped
  name is simply absent on dates after its drop.
- **Inverse-vol sizing** over equal-weight: standard risk-parity-lite that down-weights the noisiest
  names.
- **Adaptive VRP percentile** for the regime filter, replacing the spec's original hardcoded
  `VIX>25/<15` (an overfitting surface that doesn't travel across regimes).
- **`asof` lookbacks** map month offsets to the nearest prior trading day, robust to holidays/gaps.

## How to use

```python
from quant_pilot.engine.strategies.momentum import MomentumStrategy, MomentumConfig
from quant_pilot.engine.data.universe import membership_matrix

mask = membership_matrix(intervals, close.index, close.columns)   # PIT eligibility
weights = MomentumStrategy(MomentumConfig(long_pct=0.2)).generate_weights(
    close, membership=mask, vrp=vrp_series
)
result = BacktestEngine().run(PriceData(open=opens, close=closes), weights)
```

## Tests & verification

- `tests/test_momentum.py` — selects the trending winner; **membership excludes an ineligible
  winner** (next eligible name chosen); inverse-vol favours the lower-vol name; **VRP regime cuts
  gross exposure** when elevated; end-to-end through the engine is profitable net of costs.
- `tests/test_universe.py` — `membership_matrix` half-open intervals.
- **69 tests total**; `ruff`, `mypy` (56 files), `pytest` all green.

## Gotchas

- **Percentile uses strict `<`** (a bug the VRP test caught): with `<=`, a flat/calm VRP series put
  the current reading at the top and wrongly de-risked. Strict `<` puts a low/flat reading at the
  bottom (full exposure); only a genuinely elevated reading de-risks.
- Early rebalances (before `lb+skip` months of history) score NaN → empty selection → zero-weight
  rows; the engine simply stays in cash until the strategy has data.
- With few symbols, `floor(n × long_pct)` can be 0 → clamped to select at least 1 name.

## Next

The **attribution + validation layer**: regress strategy returns on market/size/value/momentum
factors to test for *residual alpha*, plus the Deflated Sharpe Ratio and block-bootstrap CIs —
the gate that decides whether this tilt is actually skill before any more strategies are added.
