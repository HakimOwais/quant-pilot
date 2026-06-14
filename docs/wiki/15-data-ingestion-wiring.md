# Step 17 — Data Ingestion Wiring (API + dashboard + shared datalake)

**Build sequence:** 17 · **Status:** ✅ done & verified live in Docker

## Goal

Make ingestion usable from the API/dashboard so backtests run on real data — closing the loop:
trigger ingest → cache → backtest → metrics, all from the UI.

## What was built

### API — [`routers/data.py`](../../src/quant_pilot/api/routers/data.py)
- `POST /api/v1/data/ohlcv` → enqueues `ingest_ohlcv(symbols, start, end)` → **202** `{job_id}`.
- `POST /api/v1/data/universe` → enqueues `ingest_universe(csv_path)` → 202.
- `GET /api/v1/data/ohlcv/{symbol}?start=&end=` → reads bars via the `MarketDataProvider`
  (cache-first), serialized as `Bar[]`.
- Schemas in [`schemas/data.py`](../../src/quant_pilot/api/schemas/data.py).

### Dashboard — [`frontend/src/App.tsx`](../../frontend/src/App.tsx)
New **Data** tab: trigger OHLCV ingestion (symbols + date range) and view cached bars for a symbol.

### Infra — shared datalake (the important fix)
- The api and worker are **separate containers**; the worker writes the parquet cache and the api
  reads it, so they must share storage. Added a named volume `datalake` mounted at
  `/app/data/storage` on api/worker/scheduler ([docker-compose.yml](../../infra/docker-compose.yml)).
- The container runs as non-root `app`; a fresh named volume mounts root-owned, so the image now
  pre-creates `/app/data/storage` owned by `app` ([Dockerfile](../../infra/Dockerfile)) and the
  volume inherits that ownership.

## Design decisions & why

- **Ingestion as async jobs** (same pattern as backtests) — downloads take seconds-to-minutes; the
  API returns a job id and the worker does the work.
- **Bars read through the provider** (cache-first) so the dashboard shows what's actually stored;
  with the shared volume, that's the same data the worker ingested.
- **Shared volume, not per-container caches** — the original bug: the api silently re-downloaded
  because it couldn't see the worker's cache. One datalake is the single source of truth.

## How to use

```bash
# from the dashboard Data tab, or:
curl -X POST localhost:8000/api/v1/data/ohlcv -d '{"symbols":["RELIANCE.NS","TCS.NS"],"start":"2022-01-01","end":"2024-06-30"}'
curl -X POST localhost:8000/api/v1/backtests   -d '{"strategy":"momentum","params":{"symbols":["RELIANCE.NS","TCS.NS"],"start":"2022-01-01","end":"2024-06-30"}}'
curl localhost:8000/api/v1/backtests/<run_id>   # status: succeeded, with metrics
```

## Tests & verification

- `tests/test_data_api.py` — ohlcv/universe ingest enqueue (202 + job id); bars serialization via a
  fake provider. **133 tests**; ruff, mypy (82 files), pytest green.
- **Verified live in Docker on real NSE data**: ingested 5 NIFTY names (613 rows each, 2022–2024);
  momentum backtest **SUCCEEDED** — ₹1.0M → ₹1.31M (+30.9%), 8 rebalances, ₹25k costs, Sharpe 0.36,
  CAGR 11.7%, max DD −14.3%. Confirmed the shared volume: worker-written parquet is visible to the
  api container.

## Gotchas

- yfinance ingestion needs network egress from the worker container (works in the verified run).
- `ingest_universe(csv_path)` needs the CSV reachable inside the worker (mount it, or switch to an
  inline-CSV body later).
- The datalake volume persists across restarts; `docker volume rm quant-pilot_datalake` to reset.

## Next

Optional: stream ingest/backtest job progress to the dashboard (SSE is already there), an
inline-CSV universe upload, and the gated order panel (TOTP) once trading is enabled.
