# Step 9 — Read-only Dashboard (containerized)

**Build sequence:** 9 · **Status:** ✅ shipped (builds in Docker; not verified in this env — no Node)

## Goal

A read-only dashboard over the API, **built and served entirely from a container** so no Node is
required on the host — `make up` brings it up alongside the rest of the stack.

## What was built — [`frontend/`](../../frontend/)

- **Vite + React + TypeScript** SPA (deliberately small: React + Vite only, no router, no
  data-fetching lib).
- [`src/api.ts`](../../frontend/src/api.ts) — a **hand-written typed client** (no OpenAPI codegen
  step to break); API base baked at build time via `VITE_API_BASE` (default `localhost:8000`).
- [`src/App.tsx`](../../frontend/src/App.tsx) — three views:
  - **Overview** — liveness + readiness (DB/Redis, `trading_enabled`).
  - **Backtests** — list runs, submit a momentum/pairs run, inspect a run's metrics.
  - **Universe** — point-in-time index membership as of a date.
- [`Dockerfile`](../../frontend/Dockerfile) — multi-stage: `node:20-alpine` builds → `nginx:alpine`
  serves the static bundle (SPA fallback in [`nginx.conf`](../../frontend/nginx.conf)).
- Compose service `frontend` on `127.0.0.1:3000`; CORS already allows that origin.

## Design decisions & why

- **Build in a container, not on the host.** The host here has no Node toolchain; containerizing
  removes that dependency entirely — the user just needs Docker.
- **Hand-written client over codegen.** I can't run a codegen step in this environment, and a
  generated client that can't be regenerated is a liability; a small typed `fetch` wrapper is more
  robust and obvious. (Swap to `openapi-typescript` later if desired — the OpenAPI schema is live.)
- **Minimal dependency surface** (no react-router/query) because the code can't be type-checked
  here — fewer moving parts to get wrong blind.
- **Static nginx serve + direct API calls** (no proxy) — the browser on the host hits the API at
  `localhost:8000`; CORS is already configured for `localhost:3000`.
- **Read-only** — viewing + submitting backtests; the gated 2FA order path is intentionally not in
  the dashboard yet (it needs a TOTP-entry UX and is a separate, careful piece).

## How to use

```bash
make up                       # builds the dashboard image and serves it
# open http://localhost:3000
```

## Verification status

⚠ Unlike every Python step, the frontend is **not verified in this environment** — there's no Node
and no Docker daemon here, so `npm run build` / `tsc` couldn't be run. It is written to compile and
build; first `make up` on a machine with Docker is the verification. Python suite remains green
(126 tests).

## Gotchas

- The API base is baked at **build** time (`VITE_API_BASE` build arg). For a non-localhost host,
  rebuild with the right base, or switch to runtime config.
- First `make up` runs `npm install` in the build stage (no committed lockfile yet); commit
  `frontend/package-lock.json` after the first successful build for reproducible installs.
- `trading_enabled=false` by default, so order/portfolio endpoints 403 — the dashboard sticks to
  read-only views to match.

## Update — UI redesign + charts (verified in Docker)

The dashboard was redesigned for a real quant-tool feel and is now **built/run-verified in Docker**:

- **Layout**: sidebar nav + cards, status dots, status badges, spinners, empty states, dark theme.
- **Tearsheet** for backtests: metric tiles (Total Return, CAGR, Sharpe/Sortino/Calmar, Max DD,
  Deflated Sharpe, Final Equity, Costs) with green/red tone, plus an **equity-curve chart** and a
  **drawdown chart**.
- **Charts** are a dependency-free SVG `LineChart` ([`src/ui.tsx`](../../frontend/src/ui.tsx)) — no
  charting lib to break.
- **Live polling**: the runs list/detail refresh every 4s so a backtest goes
  queued → running → succeeded in the UI; the equity curve loads on completion.
- **Data tab** charts the close price of a loaded symbol.

New supporting API: `GET /api/v1/backtests/{id}/equity` — the engine persists the equity/drawdown
curve as an artifact (shared datalake volume) and the endpoint serves it.

**Interactive charts + benchmark overlay (later iteration):** the SVG chart gained a hover
crosshair + tooltip and y/x axis labels; the tearsheet added a statistical-significance panel
(Deflated/Probabilistic Sharpe, p-value, 95% bootstrap CI) and toast notifications. The backtest
now also overlays a **NIFTY (`^NSEI`) buy-and-hold** on the equity curve (normalized to the same
initial capital) so out/under-performance vs the benchmark is visible at a glance — e.g. a verified
run showed momentum **+30.9% vs NIFTY +36.2%** (the tilt underperformed beta — exactly the kind of
thing the overlay surfaces). Ingest `^NSEI` for the run's date range to get the overlay.

Verified live: built the frontend image (strict `tsc` + `vite build` clean), ran a momentum
backtest on real NSE data, and the equity endpoint returned **613 points** (₹1.0M → ₹1.31M) that
the chart renders.

## Next

Optionally commit the generated `package-lock.json`; add a gated order panel (TOTP entry) and live
positions once trading is enabled; richer charts (tooltips/axes) if desired.
