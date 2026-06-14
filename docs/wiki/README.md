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
| 8 | API: read endpoints + job submission + SSE | 8 | ✅ done | [10-api-layer.md](10-api-layer.md) |
| 14 | PaperBroker (Broker port, simulated) | 14 | ✅ done | [11-paper-broker.md](11-paper-broker.md) |
| 15 | Gated order/approval path (2FA, kill switch, audit) | 15 | ✅ done | [12-order-approval-path.md](12-order-approval-path.md) |
| 16 | SmartAPI broker adapter + live readiness (§8.7) | 16 | ✅ done | [13-smartapi-live-readiness.md](13-smartapi-live-readiness.md) |
| 9 | Read-only dashboard (containerized) | 9 | ✅ shipped¹ | [14-dashboard.md](14-dashboard.md) |
| 17 | Data ingestion wiring (API + dashboard + shared datalake) | 17 | ✅ done | [15-data-ingestion-wiring.md](15-data-ingestion-wiring.md) |
| — | Live broker factory + reconciliation loop | 18+ | ⬜ planned | — |

¹ Dashboard builds inside Docker (`make up`); not verified in this env (no Node/Docker daemon here).

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
- API: async backtest submission (202 + job), run/universe read endpoints, SSE job stream — all
  behind ports (RQ or in-memory job queue); OpenAPI at /docs for the future dashboard client.
- PaperBroker: the Broker port simulated — impact/cost-aware fills, limit orders, kill switch,
  buying-power check, positions/margin (Kite adapter slots into the same port later).
- Gated order/approval path: propose→approve with trading gate + TOTP 2FA step-up, server-side
  kill switch, buying-power check, and append-only audit — all off by default.
- SmartAPI (Angel One) broker adapter behind the Broker port (injected SDK, offline-tested) +
  live-readiness checks: reconciliation, slippage monitor, paper-vs-sim P&L divergence.
- Read-only dashboard (Vite+React+TS) that builds inside Docker — no host Node; `make up` serves
  it at :3000. Redesigned with a sidebar layout, metric-tile tearsheet, SVG equity/drawdown +
  price charts, status badges, and 4s live polling (backed by GET /backtests/{id}/equity).
- Postgres schema via Alembic (`0001_initial`, `0002_orders`).
- Quality bar held every step: `ruff`, `mypy`, `pytest`, `pip-audit` all green (126 tests).

## Conventions

- Engine code is pure (no `fastapi`/`httpx`/`psycopg`/broker imports). IO lives in adapters.
- Every external integration sits behind a port so it is swappable and offline-testable.
- New work ships with tests and updates this wiki in the same step.
