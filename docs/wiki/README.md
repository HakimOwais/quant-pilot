# Quant Pilot — Implementation Wiki

A running, detailed record of what has been built, **why**, and how to use it. Updated at the
end of every implementation step. Companion to the two source-of-truth specs:

- [`MASTER_PROMPT.md`](../../MASTER_PROMPT.md) — quant / strategy decisions
- [`SYSTEM_DESIGN.md`](../SYSTEM_DESIGN.md) — platform / architecture / security

## How to read this wiki

Each step page follows the same shape: **Goal → What was built → Design decisions & why →
How to use → Tests & verification → Gotchas → Next**. Steps map to the build sequence in
[`SYSTEM_DESIGN.md` §12](../SYSTEM_DESIGN.md).

## Progress

| Step | Title | Build-seq | Status | Page |
|------|-------|-----------|--------|------|
| 0 | Scaffold (packaging, API skeleton, infra, CI) | 0 | ✅ done | [01-scaffold.md](01-scaffold.md) |
| 1 | Domain models, ports, adapters, first migration | 1–2 | ✅ done | [02-domain-ports-adapters.md](02-domain-ports-adapters.md) |
| 3 | Data infrastructure: PIT universe, OHLCV, quality, corp-actions | 3–4 | ✅ done | [03-data-ingestion.md](03-data-ingestion.md) |
| 5 | Math models (OU, Black-Scholes, Monte Carlo) | 4–6 | ✅ done | [04-math-models.md](04-math-models.md) |
| 7 | Backtest engine + cost/impact model | 7–8 | ✅ done | [05-backtest-engine.md](05-backtest-engine.md) |
| 9 | Momentum strategy (long-only factor tilt) | 9 | ✅ done | [06-momentum-strategy.md](06-momentum-strategy.md) |
| 10 | Attribution + validation (alpha vs beta) | 10 | ✅ done | [07-attribution-validation.md](07-attribution-validation.md) |
| 11 | Pairs trading (cointegration → OU → SSF) | 11–12 | ✅ done | [08-pairs-trading.md](08-pairs-trading.md) |
| 13 | Risk layer (CVaR/Kelly sizing, drawdown breaker) | 13 | ✅ done | [09-risk-layer.md](09-risk-layer.md) |
| — | API read endpoints + job submission + SSE | 8 | ⏳ next | — |
| — | Dashboard (read-only) | 9 | ⬜ planned | — |
| — | PaperBroker + live readiness | 14+ | ⬜ planned | — |

## Current capability snapshot

- Runnable FastAPI app with health/readiness, security headers, session middleware.
- 7 ports defined; adapters for secrets (keychain), artifacts (local FS), persistence
  (Postgres/SQLAlchemy), market data (yfinance), parquet cache, clock.
- **Point-in-time, survivorship-free** universe ingestion.
- OHLCV download + parquet cache + liquidity (ADV); data-quality + corporate-action verifiers.
- Math models: OU fit/half-life/z-score, Black-Scholes pricing/Greeks/IV (from scratch),
  Monte Carlo GBM/OU paths + fat-tailed (Student-t) VaR/CVaR + stationary bootstrap.
- Backtest engine: no look-ahead, next-bar fills, Indian explicit costs + market-impact model
  with ADV participation cap and circuit guards.
- Momentum strategy: PIT-eligible cross-sectional selection, inverse-vol sizing, adaptive VRP
  regime scaling — producing engine-ready target weights.
- Analysis: performance stats, factor attribution (HAC alpha t-stat), and Sharpe validation
  (PSR, Deflated Sharpe, block-bootstrap CI) — the alpha-vs-beta gate.
- Pairs trading: cointegration (Engle-Granger) + FDR control, OU half-life filter, OOS
  confirmation, no-mean-cross break guard, SSF-tradeable signed weights.
- Risk layer: fractional-Kelly / CVaR sizing, position + sector caps, latching drawdown breaker.
- Postgres schema via Alembic (`0001_initial`).
- Quality bar held every step: `ruff`, `mypy`, `pytest`, `pip-audit` all green (94 tests).

## Conventions

- Engine code is pure (no `fastapi`/`httpx`/`psycopg`/broker imports). IO lives in adapters.
- Every external integration sits behind a port so it is swappable and offline-testable.
- New work ships with tests and updates this wiki in the same step.
