# Step 10 — Attribution + Validation (alpha vs beta, is the Sharpe real?)

**Build sequence:** 10 · **Status:** ✅ done

## Goal

The Production-Mandate gate. Before any more strategies are built, prove whether the momentum
tilt's return is **residual alpha** (not repackaged beta/size/momentum) and whether its Sharpe is
**statistically real** (not luck or backtest overfit). Pure analysis modules over a returns Series.

## What was built — [`engine/analysis/`](../../src/quant_pilot/engine/analysis/)

### [`performance.py`](../../src/quant_pilot/engine/analysis/performance.py)
`performance_stats` → `PerformanceStats(total_return, cagr, ann_vol, sharpe, sortino, calmar,
max_drawdown, max_drawdown_days, hit_rate, n_periods)`; plus `sharpe_ratio`, `sortino_ratio`,
`drawdown_series`. Risk-free is annual (RBI repo from config), converted per-period internally.

### [`attribution.py`](../../src/quant_pilot/engine/analysis/attribution.py) — THE deliverable
`factor_attribution(returns, factors, rf, hac_lags)` → `FactorAttribution(alpha_annual,
alpha_tstat, betas, r_squared, n_obs)` with `alpha_is_significant`. OLS of excess returns on
factor returns (market/size/value/momentum); the intercept is alpha, with **Newey-West (HAC)**
standard errors so autocorrelation/heteroskedasticity don't inflate significance. Implemented in
numpy (statsmodels deferred to the pairs phase).

> If `alpha_tstat` isn't significant, the strategy is **factor exposure, not skill** — exactly the
> verdict the momentum module deferred to here.

### [`validation.py`](../../src/quant_pilot/engine/analysis/validation.py)
- `probabilistic_sharpe_ratio` (PSR) — P(true SR > benchmark), skew/kurtosis-adjusted.
- `deflated_sharpe_ratio` (DSR) — PSR vs the **expected maximum** SR over N research trials
  (Bailey & López de Prado); the headline significance number, not the raw Sharpe.
- `bootstrap_sharpe_ci` — **stationary block bootstrap** (from the MC module), dependence-preserving.
- `sharpe_significance` bundles sharpe + PSR + DSR + p-value + bootstrap CI.

## Design decisions & why

- **Attribution is the deliverable, not the return.** A long-only momentum tilt loads on beta/size;
  only the regression intercept tells you if there's skill left over — so this module exists before
  the pairs strategy, per the Production Mandate.
- **HAC standard errors** (not OLS classic) because daily strategy returns are autocorrelated;
  classic SEs would overstate the alpha t-stat.
- **DSR over raw Sharpe** because the research process tries many parameter sets/strategies; the
  best-looking Sharpe is upward-biased. DSR deflates for the number of trials.
- **Block bootstrap, never IID shuffle** — shuffling destroys the autocorrelation momentum/mean-
  reversion exploit, invalidating the null (reuses `monte_carlo.stationary_bootstrap`).
- **Numpy HAC from scratch** keeps the dependency surface small; statsmodels comes with cointegration.

## How to use

```python
from quant_pilot.engine.analysis.performance import performance_stats
from quant_pilot.engine.analysis.attribution import factor_attribution
from quant_pilot.engine.analysis.validation import sharpe_significance

stats = performance_stats(result.returns, rf=0.065)
attr = factor_attribution(result.returns, factor_returns_df, rf=0.065)
if not attr.alpha_is_significant:
    print("factor exposure, not alpha")        # don't claim skill

sig = sharpe_significance(result.returns, n_trials=200)   # trials run during research
print(sig.sharpe, sig.deflated_sharpe, sig.ci_low, sig.ci_high)
```

## Tests & verification

- `tests/test_analysis.py` — performance stats + drawdown detection + flat-returns Sharpe=0;
  **attribution recovers β≈1.2 and a significant alpha**, and flags a pure-beta strategy as
  **not significant**; PSR high for a clear positive Sharpe; **DSR decreases as trials increase**
  and never exceeds PSR; bootstrap CI brackets the point estimate; the significance bundle is
  internally consistent.
- **78 tests total**; `ruff`, `mypy` (59 files), `pytest` all green.

## Gotchas

- DSR needs the **dispersion of Sharpe across trials**; when not supplied it's approximated by the
  SR estimator's sampling std under observed moments — a documented proxy, not the full
  cross-trial variance. Pass `trials_sr_std` when the trial set is known for an exact DSR.
- The factor return series (market/size/value/momentum) for Indian equities still needs to be
  built/sourced (IIMA/NSE factor indices or self-constructed from the PIT universe) — the math is
  ready; the data wiring is a data-layer task.
- `alpha_is_significant` uses |t| > 2 (~95%); tighten per preference.

## Next

The **pairs trading strategy** (cointegration → OU half-life → SSF-tradeable short leg), or the
**API read endpoints + job submission** to start surfacing runs to the future dashboard. Either
way, attribution/validation now gates every strategy's claim to alpha.
