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
| — | Backtest engine + costs/impact | 7–8 | ⏳ next | — |
| — | Momentum strategy + attribution/validation | 9–10 | ⬜ planned | — |
| — | API read endpoints + job submission + SSE | 8 | ⬜ planned | — |
| — | Dashboard (read-only) | 9 | ⬜ planned | — |
| — | PaperBroker + pairs + risk + live readiness | 10–12 | ⬜ planned | — |

## Current capability snapshot

- Runnable FastAPI app with health/readiness, security headers, session middleware.
- 7 ports defined; adapters for secrets (keychain), artifacts (local FS), persistence
  (Postgres/SQLAlchemy), market data (yfinance), parquet cache, clock.
- **Point-in-time, survivorship-free** universe ingestion.
- OHLCV download + parquet cache + liquidity (ADV); data-quality + corporate-action verifiers.
- Math models: OU fit/half-life/z-score, Black-Scholes pricing/Greeks/IV (from scratch),
  Monte Carlo GBM/OU paths + fat-tailed (Student-t) VaR/CVaR + stationary bootstrap.
- Postgres schema via Alembic (`0001_initial`).
- Quality bar held every step: `ruff`, `mypy`, `pytest`, `pip-audit` all green (51 tests).

## Conventions

- Engine code is pure (no `fastapi`/`httpx`/`psycopg`/broker imports). IO lives in adapters.
- Every external integration sits behind a port so it is swappable and offline-testable.
- New work ships with tests and updates this wiki in the same step.
