# Step 11–12 — Pairs Trading (cointegration → OU → SSF short leg)

**Build sequence:** 11–12 · **Status:** ✅ done

## Goal

Market-neutral stat-arb: find cointegrated, SSF-tradeable pairs, trade the mean-reverting spread,
and retire pairs whose relationship breaks — with every production correction from MASTER_PROMPT
(FDR multiple-testing control, OOS confirmation, the corrected Monte-Carlo role, the SSF short leg).

## What was built — [`engine/strategies/`](../../src/quant_pilot/engine/strategies/)

### [`cointegration.py`](../../src/quant_pilot/engine/strategies/cointegration.py)
- `engle_granger(y, x)` → (hedge ratio, intercept, ADF p-value) via OLS + `statsmodels.adfuller`.
- `compute_spread`.
- `benjamini_hochberg` — **FDR multiple-testing control** (mandatory: scanning many pairs at p<0.05
  guarantees false positives).
- `cusum_break` — Brownian-bridge CUSUM for periodic structural-break re-validation.

### [`pairs_trading.py`](../../src/quant_pilot/engine/strategies/pairs_trading.py)
- `select_pairs` pipeline: SSF filter (both legs) → Engle-Granger on TRAIN → **BH-FDR** → OU
  half-life in [5, 60]d and statistically mean-reverting → **OOS confirmation** (re-fit OU on the
  holdout; the spread must *still* mean-revert).
- `pair_leg_weights` — z-score state machine (entry ±2 / exit 0 / stop ±3.5) with a **no-mean-cross
  break guard** (retire a pair if the spread fails to cross its mean for > `mult × half-life`); the
  dollar hedge ratio is **frozen at entry** so weights are piecewise-constant.
- `PairsStrategy` — sums leg weights across pairs into an engine-ready (signed) weight DataFrame.
- `reversion_robustness` — the **corrected Monte-Carlo role**: stress mean reversion under
  parameter uncertainty / cointegration decay (θ → 0); it does NOT gate trades by re-simulating the
  fitted model (the spec's original circular confidence score — removed).

## Design decisions & why

- **FDR before anything** — without it, in-sample cointegration scanning manufactures phantom pairs.
- **OOS confirmation via re-fitting OU, not fresh ADF.** With an *estimated* hedge, the residual is
  `stationary + (β_true − β̂)·X`; that tiny I(1) contamination makes a fresh ADF reject out of
  sample even for a genuine pair. Re-fitting OU tests that mean reversion *persists*, which is what
  we actually trade — far more robust (a debugging finding, see Gotchas).
- **No-mean-cross break guard, not z-CUSUM.** A z-score CUSUM can't separate a normal 2–3σ trade
  excursion (peak ≈ 42 in testing) from a real break (≈ 141); "hasn't crossed its mean in
  >4× half-life" is interpretable, tied to the OU fit, and doesn't fire on normal trades.
- **Frozen entry hedge ratio** → piecewise-constant weights → the engine rebalances only on signal
  changes (no daily drift churn), and the leg ratio matches the spread definition.
- **Signed weights into the existing engine** — the short leg is just a negative weight; SSF
  tradeability is enforced upstream at selection (`ssf_eligible`), keeping the engine generic.

## How to use

```python
from quant_pilot.engine.strategies.pairs_trading import select_pairs, PairsStrategy

pairs = select_pairs(candidate_tuples, close, ssf_eligible=ssf_names)   # validated, FDR + OOS
weights = PairsStrategy(pairs).generate_weights(close)
result = BacktestEngine().run(PriceData(open=opens, close=closes, volume=vols), weights)
```

## Tests & verification

- `tests/test_pairs.py` — Engle-Granger detects cointegration (β≈1.5) and rejects independent walks;
  BH-FDR mask; CUSUM break detection; `select_pairs` keeps only the validated pair; **SSF filter**
  excludes pairs missing a leg; z-excursion opens a long with a short X leg; **structural break
  retires the pair**; end-to-end through the engine trades; robustness decays with weaker θ.
- **87 tests total**; `ruff`, `mypy` (61 files), `pytest` all green.

## Gotchas (debugging findings)

- **OOS ADF is fragile under estimated hedge** (the bug that drove the OOS redesign): a 1.3% hedge
  error over a wandering random walk leaves an I(1) residual that fails fresh ADF out of sample.
  OU-persistence OOS confirmation is the fix.
- **Pinning the hedge needs X variation** — low-variation regressors give noisy OLS hedges; the
  test generator uses a high-variance X so the hedge (and thus OOS) is clean.
- The break guard fires on *one-sided* drift; the stop-loss (z ≥ 3.5) still handles runaway
  divergence that hasn't yet tripped the no-cross window.

## Next

The **risk layer** (fractional Kelly / CVaR position sizing, drawdown circuit breaker) over the
strategy weights, or the **API read endpoints + job submission** to surface runs to the dashboard.
