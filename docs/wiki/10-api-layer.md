# Step 8 — API Layer (read endpoints, job submission, SSE)

**Build sequence:** 8 · **Status:** ✅ done

## Goal

Surface the engine over a typed HTTP contract: submit backtests asynchronously, read runs and
point-in-time universe membership, and stream job progress — the contract the future dashboard's
generated client consumes. All behind ports so it's testable offline (no Redis/Postgres).

## What was built

### JobQueue adapters — [`workers/queue.py`](../../src/quant_pilot/workers/queue.py)
- `RqJobQueue` — production (RQ + Redis): `enqueue(func_path, *args)`, `status(job_id)`.
- `InMemoryJobQueue` — dev/test double; `eager=True` runs the job synchronously, otherwise records
  a stub marked `finished` (no worker needed).

### Worker task — [`workers/tasks.py`](../../src/quant_pilot/workers/tasks.py)
- `execute_backtest(prices, strategy)` — pure-ish: runs strategy → engine → performance +
  Sharpe-significance, returns a metrics dict (testable with synthetic prices).
- `run_backtest(run_id)` — the RQ entrypoint: load run → RUNNING → build `PriceData` from the
  parquet cache → `execute_backtest` → persist metrics + SUCCEEDED/FAILED.

### API — [`api/`](../../src/quant_pilot/api/)
- [`routers/backtests.py`](../../src/quant_pilot/api/routers/backtests.py):
  `POST /api/v1/backtests` → **202** `{run_id, job_id, status}` (persists a run, enqueues the job);
  `GET /api/v1/backtests` (list); `GET /api/v1/backtests/{id}` (404 if missing).
- [`routers/jobs.py`](../../src/quant_pilot/api/routers/jobs.py): `GET /api/v1/jobs/{id}` status;
  `GET /api/v1/jobs/{id}/stream` **Server-Sent Events** progress (ends on a terminal status).
- [`routers/universe.py`](../../src/quant_pilot/api/routers/universe.py):
  `GET /api/v1/universes/{index}/members?as_of=YYYY-MM-DD` — survivorship-free membership.
- [`schemas/backtests.py`](../../src/quant_pilot/api/schemas/backtests.py): `BacktestCreate`,
  `BacktestSubmitOut` (responses reuse domain models directly).
- [`deps.py`](../../src/quant_pilot/api/deps.py): added `get_job_queue`.

## Design decisions & why

- **202 + job_id, not a blocking call.** Backtests take minutes; the API returns immediately and
  the worker runs it — the async contract the dashboard needs from day one (SYSTEM_DESIGN §6).
- **SSE over WebSocket** for progress — one-way, simple, auto-reconnect; WS is reserved for the
  future live-positions stream.
- **Domain models as responses.** `BacktestRun`/`UniverseMembership`/`JobStatus` are already
  Pydantic, so they serialize directly — only the *request* needs a dedicated schema. Less drift.
- **Everything behind ports** (`Repository`, `JobQueue`) → tests override with in-memory doubles;
  no Redis/Postgres required in CI.
- **`execute_backtest` split from `run_backtest`** so the orchestration logic is unit-tested with
  synthetic prices while the IO wrapper (cache + persistence) stays thin.

## How to use

```bash
curl -X POST localhost:8000/api/v1/backtests \
  -H 'content-type: application/json' \
  -d '{"strategy":"momentum","params":{"symbols":["TCS.NS"],"start":"2018-01-01","end":"2024-12-31"}}'
# -> 202 {"run_id": "...", "job_id": "...", "status": "queued"}

curl localhost:8000/api/v1/jobs/<job_id>            # status
curl -N localhost:8000/api/v1/jobs/<job_id>/stream  # SSE progress
curl localhost:8000/api/v1/backtests/<run_id>       # results + metrics
curl 'localhost:8000/api/v1/universes/NIFTY50/members?as_of=2018-06-01'
```

The OpenAPI schema at `/openapi.json` (Swagger at `/docs`) is the source for the frontend's
generated TypeScript client.

## Tests & verification

- `tests/test_api.py` — submit → 202 + persisted run; list/get; 404; job status + **SSE stream**
  emits `data:` events; point-in-time universe endpoint; `execute_backtest` produces metrics on
  synthetic data. Uses dependency overrides (in-memory SQLite session + in-memory job queue).
- **99 tests total**; `ruff`, `mypy` (69 files), `pytest` all green.

## Gotchas

- **SQLite + TestClient threads**: the TestClient runs sync endpoints in a worker thread, so the
  test engine needs `check_same_thread=False` + `StaticPool` to share one in-memory connection
  (fixed in `conftest`).
- `InMemoryJobQueue` (non-eager) marks jobs `finished` immediately — it's a stub; real progress
  needs `RqJobQueue` + a running worker.
- `run_backtest` needs OHLCV already in the parquet cache (ingest first); it's integration-level
  and not exercised in CI.

## Next

The **read-only dashboard** (Next.js + generated client) consuming these endpoints, or wiring the
**PaperBroker** behind the Broker port toward live-trading readiness.
