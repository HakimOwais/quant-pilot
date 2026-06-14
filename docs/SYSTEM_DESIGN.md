# Quant Pilot — System Design

**Status:** Draft for approval · **Scope:** platform architecture + security (companion to `MASTER_PROMPT.md`)
**Profile:** single-user · self-hosted · research-first · dashboard will gain live-order control later

> `MASTER_PROMPT.md` is the source of truth for **strategy / quant** decisions.
> This document is the source of truth for **platform / architecture / security** decisions.

---

## 1. Design Goals (and the constraints they come from)

| Goal | Why it matters here |
|------|--------------------|
| **Engine is UI-agnostic** | The strategies/models/backtest code must not know HTTP, UI, or broker exists. The dashboard then becomes "just another API client" — no retrofitting. |
| **Contract-first API** | A versioned, typed API (OpenAPI) that the frontend consumes via a **generated** client. No hand-written drift between back and front end. |
| **Async from day one** | Backtests/ingestion take minutes. Long work runs as background jobs with status/streaming — never blocking an HTTP request. Designing this later breaks the UX. |
| **Secure write-path designed now, built later** | The dashboard will eventually move real money. The order/approval/kill-switch/audit boundary is modeled now and gated off, so enabling it later is a flag flip + UI, not a re-architecture. |
| **Secrets never in repo/DB/plaintext** | Broker API keys are the crown jewels. Encrypted at rest, sourced from OS keychain, least-privilege. |
| **Deterministic & auditable** | Injected clock (no look-ahead), append-only audit log of every signal/order/config change/login. |

**Non-goals (v1):** multi-tenancy, public sign-up, horizontal scaling, real-money live trading. The architecture leaves clean seams for all of these but does not build them.

---

## 2. Architecture Style — Hexagonal (Ports & Adapters)

The quant engine sits in the center as a pure library. Everything external (data feeds, broker, database, UI, secrets) is reached through **ports** (interfaces) implemented by swappable **adapters**. This is what makes the dashboard painless and the broker stubbable.

```
                        ┌──────────────────────────────────────────────┐
                        │                  FRONTEND                     │
                        │        Next.js dashboard (typed client)       │
                        └───────────────┬──────────────────────────────┘
                                        │ HTTPS (REST + SSE/WS)
                        ┌───────────────▼──────────────────────────────┐
                        │                 API LAYER                     │
                        │  FastAPI · auth · validation · rate limit ·   │
                        │  OpenAPI contract · SSE progress streams      │
                        └───────┬───────────────────────────┬──────────┘
                                │ enqueue job               │ read
                        ┌───────▼─────────┐         ┌───────▼──────────┐
                        │   JOB QUEUE      │         │  READ MODELS /   │
                        │  (Redis + RQ)    │         │  REPOSITORIES    │
                        └───────┬─────────┘         └───────┬──────────┘
                                │ run                        │
                        ┌───────▼────────────────────────────▼─────────┐
                        │                 WORKERS                       │
                        │  backtest runner · ingestion · scheduler      │
                        └───────────────────┬──────────────────────────┘
                                            │ calls
                        ┌───────────────────▼──────────────────────────┐
                        │            QUANT ENGINE (pure lib)            │
                        │  data · models · strategies · backtest ·      │
                        │  risk · analysis    (NO IO knowledge)         │
                        └───────────────────┬──────────────────────────┘
                                            │ via PORTS (interfaces)
        ┌───────────────┬───────────────────┼───────────────┬───────────────────┐
        ▼               ▼                   ▼               ▼                   ▼
 MarketDataProvider  Repository        ArtifactStore     Broker            SecretStore
   (yfinance,        (Postgres /       (local FS /      (PaperBroker NOW,  (OS keychain,
    nsepython)        SQLAlchemy)       MinIO later)      Kite LATER)        SOPS/age)
```

**The rule:** the engine depends only on port *interfaces*. Adapters depend on the engine. The API/workers wire concrete adapters into the engine at startup (dependency injection). Nothing in `engine/` imports `fastapi`, `requests`, `psycopg`, or `kiteconnect`.

---

## 3. Repository Topology

The `MASTER_PROMPT.md` module tree describes the **engine internals**. Here is how it is wrapped into a deployable system:

```
quant-pilot/
├── src/quant_pilot/
│   ├── engine/                 # the pure quant library (UI/IO-agnostic)
│   │   ├── data/               #   ingestion logic, universe, liquidity, quality (pure)
│   │   ├── models/             #   black_scholes, monte_carlo, ou_process, ml_signals
│   │   ├── strategies/         #   momentum, pairs_trading, combined, base
│   │   ├── backtest/           #   engine, costs, impact, capacity, walk_forward
│   │   ├── risk/               #   position_sizing, var (CVaR), drawdown
│   │   └── analysis/           #   performance, attribution, validation, tearsheet, regime
│   │
│   ├── domain/                 # shared dataclasses/Pydantic models + PORT interfaces
│   │   ├── models.py           #   BacktestRun, StrategyConfig, Order, Position, AuditEvent...
│   │   └── ports.py            #   MarketDataProvider, Repository, ArtifactStore, Broker,
│   │                           #   SecretStore, JobQueue, Clock  (abstract base classes)
│   │
│   ├── adapters/               # concrete implementations of the ports
│   │   ├── data/               #   yfinance_provider.py, nsepython_provider.py
│   │   ├── persistence/        #   sqlalchemy_repository.py, alembic/ migrations
│   │   ├── artifacts/          #   local_fs_store.py  (s3_store.py later)
│   │   ├── broker/             #   paper_broker.py (NOW), kite_broker.py (LATER, stub)
│   │   └── secrets/            #   keyring_store.py, sops_store.py
│   │
│   ├── api/                    # FastAPI application
│   │   ├── main.py             #   app factory, middleware, CORS, security headers
│   │   ├── deps.py             #   DI wiring (which adapters), auth dependencies
│   │   ├── security/           #   auth, sessions, 2FA, rate limiting, csrf
│   │   ├── routers/            #   universes, data, strategies, backtests, risk,
│   │   │                       #   analysis, orders (gated), system (kill switch/health)
│   │   └── schemas/            #   request/response Pydantic models (the API contract)
│   │
│   ├── workers/                # job definitions + scheduler
│   │   ├── tasks.py            #   run_backtest, ingest_data, refresh_universe
│   │   └── scheduler.py        #   APScheduler: nightly data refresh, etc.
│   │
│   └── config/                 # settings loading (pydantic-settings), settings.yaml
│
├── frontend/                   # Next.js + TypeScript dashboard
│   ├── lib/api/                #   GENERATED OpenAPI client (do not hand-edit)
│   └── ...
│
├── infra/                      # docker-compose.yml, Caddyfile, .env.example, Dockerfiles
├── data/storage/               # parquet datalake + artifacts (gitignored)
├── notebooks/                  # research (uses engine as a library, not the API)
├── tests/                      # unit (engine) + contract (api) + integration
├── MASTER_PROMPT.md
└── docs/SYSTEM_DESIGN.md       # this file
```

**Key point for the dashboard:** the frontend's API client in `frontend/lib/api/` is **generated** from the FastAPI OpenAPI schema (`openapi-typescript` / `openapi-fetch`). When a backend endpoint changes, regeneration surfaces the break at compile time instead of at runtime in production.

---

## 4. The Ports (interfaces defined now)

These are the seams. Implement the simple/safe adapter now; swap later without touching the engine.

| Port | v1 adapter (now) | Later adapter | Purpose |
|------|------------------|---------------|---------|
| `MarketDataProvider` | yfinance + nsepython | vendor PIT feed (ICE/Nuvama) | OHLCV, **point-in-time** universe membership, option chains, liquidity (ADV/spread/SSF) |
| `Repository` | SQLAlchemy + Postgres | (same) | persist runs, configs, results metadata, orders, audit |
| `ArtifactStore` | local filesystem | MinIO / S3 | store tearsheets, plots, large result blobs (by ID) |
| `Broker` | **PaperBroker** (simulated fills via impact model) | KiteBroker / SmartAPI | positions, margin, place/modify/cancel order, kill switch |
| `SecretStore` | OS keychain (`keyring`) | Vault | fetch broker creds, encrypt-at-rest |
| `JobQueue` | RQ + Redis | (same) | enqueue long work, report status |
| `Clock` | real / injected | (same) | deterministic backtests, no look-ahead in tests |

The `Broker` port is the **execution boundary** decided now. The engine and API speak only to this interface; whether fills are paper-simulated or sent to Zerodha is an adapter choice behind a `trading_enabled` flag.

---

## 5. Persistence Strategy

Two stores, by data shape:

- **Relational DB — PostgreSQL 16** (via SQLAlchemy 2.0 + Alembic migrations).
  Holds *small, queryable, transactional* state: users (single), credentials-references, strategy configs, backtest runs + metrics, **point-in-time universe membership** (`(symbol, index, effective_from, effective_to)`), orders, positions, and the **append-only audit log**. JSONB columns for flexible metric/result blobs.
  *Why Postgres over SQLite even for one user:* the worker and API write concurrently; SQLite's single-writer lock causes contention, and we know the dashboard + background jobs are coming. SQLite remains a documented laptop-only fallback.

- **Parquet datalake on disk** (abstracted by `ArtifactStore` / data layer).
  Holds *large, append-mostly, columnar* data: OHLCV bars, computed features, large simulation outputs, tearsheet artifacts. Referenced by path/ID from the DB. Swappable to S3/MinIO later with no engine change.

Migrations are mandatory from commit #1 (Alembic) so the dashboard's schema never drifts.

---

## 6. API Design

- **Framework:** FastAPI + Pydantic v2 (same language as engine → zero serialization mismatch; auto OpenAPI).
- **Versioned:** all routes under `/api/v1`.
- **Sync vs async:**
  - Fast reads (list runs, fetch tearsheet, get positions) → normal REST.
  - Long work (run backtest, ingest data) → `POST` returns `202 Accepted` + a `job_id`; the actual work runs in a worker.
  - Progress/logs/live P&L → **Server-Sent Events** (`GET /api/v1/jobs/{id}/stream`). SSE chosen over WebSocket for one-way progress (simpler, auto-reconnect). WebSocket reserved for the future bidirectional live-trading panel.
- **Contract → client:** OpenAPI schema generates the typed TS client. Frontend never hand-writes request/response types.

**Representative resources** (read-first; order/system gated):

```
GET   /api/v1/universes                 list universes / membership snapshots
GET   /api/v1/instruments/{sym}/bars    OHLCV (paged)
POST  /api/v1/backtests                 submit run  -> 202 {job_id}
GET   /api/v1/backtests/{id}            run status + metrics
GET   /api/v1/backtests/{id}/tearsheet  artifact (factor attribution, DSR, etc.)
GET   /api/v1/jobs/{id}/stream          SSE progress
GET   /api/v1/risk/var                  current VaR/CVaR, drawdown state
--- gated behind trading_enabled + 2FA step-up (built later) ---
POST  /api/v1/orders                    propose order  (-> pending approval)
POST  /api/v1/orders/{id}/approve       2FA-confirmed execution
GET   /api/v1/positions                 live book
POST  /api/v1/system/halt               KILL SWITCH (always available)
GET   /api/v1/system/health             liveness/readiness
```

---

## 7. Core Flows

**Backtest submission (built in v1):**
```
UI ──POST /backtests──► API ──validate(Pydantic)──► enqueue(JobQueue) ──► 202 {job_id}
                                                          │
Worker ◄──dequeue──────────────────────────────────────-─┘
  └─ build engine with adapters (data, repo, artifacts, PaperBroker)
  └─ run walk-forward backtest  (emit progress events ──► Redis pub/sub)
  └─ write metrics ──► Repository ;  tearsheet ──► ArtifactStore
UI ◄── SSE /jobs/{id}/stream (progress) ;  then GET /backtests/{id} (results)
```

**Live order (designed now, enabled later) — note the gates:**
```
UI proposes order ─► API: authn? ─► trading_enabled? ─► pre-trade risk checks
   (position/sector/drawdown/fat-finger limits) ─► persist as PENDING + AUDIT
UI confirm ─► API: 2FA step-up (TOTP) ─► re-check kill switch + limits
   ─► Broker.place_order() ─► persist FILLED/REJECTED + AUDIT ─► SSE to UI
Global kill switch + dead-man's-heartbeat enforced server-side on EVERY order.
```

---

## 8. Security Design

Single-user does **not** mean low-security — the box holds broker keys and (later) can move capital. Defense in depth:

### 8.1 Authentication
- Local account, **Argon2id**-hashed password (`argon2-cffi`).
- Session via **httpOnly + Secure + SameSite=Strict** cookie (not localStorage — immune to XSS token theft).
- **TOTP 2FA** (`pyotp`) enrolled on setup; required as a **step-up** specifically for trading/secret-changing actions.
- Default **bind to `127.0.0.1`**. Remote access = SSH tunnel or VPN (recommended) rather than exposing the port. If exposed, mandatory TLS + 2FA.

### 8.2 Authorization / write-path isolation
- Read endpoints vs **act** endpoints are separated. Trading endpoints are **feature-flagged off** (`trading_enabled=false`) until explicitly turned on.
- Every order passes server-side **pre-trade risk checks** and the **global kill switch** — the UI cannot bypass them.

### 8.3 Secrets
- Broker API keys/secret/TOTP **never** in repo, `settings.yaml`, or DB plaintext.
- Sourced from **OS keychain** (`keyring`) in dev; envelope-encrypted at rest (key from keychain) for the DB credential reference. **SOPS + age** for file-based encrypted secrets if needed.
- `.env` is gitignored; `infra/.env.example` documents names only. Least-privilege broker keys (separate read vs trade where the broker supports it).

### 8.4 Transport & web hardening
- TLS for any non-local exposure (**Caddy** reverse proxy = automatic HTTPS).
- **CORS** locked to the exact frontend origin; **CSRF** token for cookie auth; security headers (HSTS, CSP, X-Frame-Options=DENY, X-Content-Type-Options=nosniff).
- **Rate limiting** on auth + order endpoints (brute-force + fat-finger protection).

### 8.5 Input & code safety
- Pydantic validates every request; unknown fields rejected. Strategy params are **config/schema-driven** (no arbitrary code execution from the UI). If custom strategy code is ever allowed, it must run in a sandbox — flagged, not in v1.
- ORM-parameterized queries only (no string-built SQL).

### 8.6 Auditability & supply chain
- **Append-only audit log**: every login, config change, signal, order, fill, risk decision, kill-switch toggle — with who/when/what (optional hash-chain for tamper-evidence).
- Pinned dependencies + lockfile; `pip-audit` in CI; structured logging (`structlog`); `/health` liveness/readiness.

### 8.7 Security checklist (gate before live trading)
```
[ ] Secrets in keychain/encrypted, none in repo or DB plaintext
[ ] 2FA enrolled; step-up enforced on order + secret-change endpoints
[ ] trading_enabled=false by default; kill switch verified server-side
[ ] Pre-trade risk limits enforced server-side, not just UI
[ ] TLS on any non-local binding; CORS/CSRF/security headers set
[ ] Rate limiting on auth + orders
[ ] Append-only audit log capturing all sensitive actions
[ ] pip-audit clean; dependencies pinned
[ ] Paper-trade reconciled to live P&L before real capital (per MASTER_PROMPT Phase 6)
```

---

## 9. Deployment Topology (single-user, self-hosted)

`docker-compose` stack, all pinned images:

| Service | Tech | Role |
|---------|------|------|
| `api` | FastAPI + uvicorn | HTTP/SSE, auth, validation |
| `worker` | RQ worker | backtests, ingestion |
| `scheduler` | APScheduler | nightly data refresh, periodic re-validation |
| `db` | PostgreSQL 16 | relational state + audit |
| `redis` | Redis 7 | job queue + cache + progress pub/sub |
| `frontend` | Next.js | dashboard (or static export served by Caddy) |
| `proxy` *(opt)* | Caddy | TLS termination when exposed beyond localhost |

Local-only by default; the proxy/TLS service is opt-in for remote access.

---

## 10. Technology Decisions (summary)

| Concern | Decision | One-line rationale |
|--------|----------|-------------------|
| Engine | Python library, hexagonal | UI/broker-agnostic; testable; reusable from notebooks + API |
| API | FastAPI + Pydantic v2 | same language as engine, auto OpenAPI → generated FE client |
| Realtime | SSE for progress; WS later for live book | one-way progress is simpler/robust than WS |
| Jobs | RQ + Redis | simplest reliable async for single-user long tasks |
| Scheduling | APScheduler | nightly data refresh without Celery beat overhead |
| DB | PostgreSQL 16 + SQLAlchemy 2 + Alembic | concurrent worker/API writes; JSONB; migrations from day 1 |
| Big data | Parquet datalake via ArtifactStore | columnar, cheap, S3-swappable later |
| Frontend | Next.js + TS + generated client + TanStack Query | typed contract, no drift; good charting ecosystem |
| Auth | Argon2id + httpOnly session cookie + TOTP step-up | XSS-resistant, money-grade for the act path |
| Secrets | `keyring` (OS keychain) + SOPS/age | keys never in repo/DB plaintext |
| TLS/proxy | Caddy (when exposed) | automatic HTTPS |
| Packaging | docker-compose, pinned | reproducible single-command stack |

---

## 11. Where I used sensible defaults (flag if you disagree)

- **Postgres over SQLite** — chosen for worker/API concurrency; SQLite documented as laptop fallback.
- **RQ over Celery** — simpler for single-user; Celery only if scheduling/workflows get complex.
- **SSE over WebSocket** for progress — WS reserved for the future live-positions stream.
- **Next.js** for the dashboard — could be a plain Vite/React SPA if you don't want SSR; the generated-client approach is identical either way.
- **Session cookie over JWT** — better for a single-user server-rendered app and easy revocation; JWT only adds value for stateless multi-service, which we don't have.

---

## 12. Proposed Build Sequence (platform-aware)

This refines `MASTER_PROMPT.md` §Implementation Order so the platform seams exist before the engine fills in:

```
0. Scaffold: repo topology, pydantic-settings, docker-compose, Postgres + Alembic, CI (lint/pip-audit)
1. domain/ports.py + domain/models.py            (the interfaces — locks the contract)
2. adapters: keyring SecretStore, local ArtifactStore, SQLAlchemy Repository
3. data/universe (POINT-IN-TIME) + MarketDataProvider adapter  (MASTER_PROMPT NON-NEGOTIABLE #1)
4. data/ingestion + corp-action verifier + liquidity dataset
5. engine models (ou, black_scholes, monte_carlo) behind ports, unit-tested with injected Clock
6. backtest costs+impact, engine; momentum strategy end-to-end
7. analysis: attribution + validation (prove alpha real before more strategies)
8. api: auth/security skeleton + read endpoints + job submission + SSE
9. frontend: generated client + read-only dashboard (backtests, tearsheets, risk)
10. PaperBroker + Broker port + order/audit domain (gated, trading_enabled=false)
11. pairs strategy (needs SSF universe + execution boundary)
12. LATER: KiteBroker adapter, live-order UI panel, full Phase-6 live-trading readiness
```

Phase 1 work therefore begins at **step 0–3**: scaffold + ports + the point-in-time universe — not a raw yfinance download script.
