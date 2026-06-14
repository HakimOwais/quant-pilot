# Step 3 — Data Infrastructure (PIT universe, OHLCV, quality, corporate actions)

**Build sequence:** 3–4 · **Status:** ✅ done

## Goal

Pull real Indian-equity data through the ports defined in Step 1, while enforcing the two
MASTER_PROMPT non-negotiables: **(#1) survivorship-free point-in-time universe** and
**(#2) verified corporate actions**. Plus OHLCV caching, liquidity, and data-quality checks.

## What was built

### Engine (pure) — [`engine/data/`](../../src/quant_pilot/engine/data/)
- [`universe.py`](../../src/quant_pilot/engine/data/universe.py) — point-in-time reconstruction.
  `parse_membership_events` / `read_membership_csv` → `build_membership_intervals`, which
  collapses add/drop **events** into `[effective_from, effective_to)` **intervals**
  (re-additions create multiple intervals; current members have `effective_to=None`).
- [`corporate_actions.py`](../../src/quant_pilot/engine/data/corporate_actions.py) —
  `verify_adjustments`: a correctly adjusted series is *continuous* across a split/bonus, so a
  jump in `adj_close` on a known action date = **bad adjustment**, and a jump with no known
  action = **unexplained** (unrecorded action / corrupt data). Returns a `CorpActionReport`.
- [`quality.py`](../../src/quant_pilot/engine/data/quality.py) — `check_quality`: missing
  sessions (vs the NSE calendar), stale-price runs, non-positive prices, zero-volume, and
  volume spikes. Returns a `QualityReport` (`ok` reflects hard failures only).

### Adapters (IO) — [`adapters/data/`](../../src/quant_pilot/adapters/data/)
- [`parquet_cache.py`](../../src/quant_pilot/adapters/data/parquet_cache.py) — `OHLCVCache`,
  one Parquet file per symbol, merge-on-write (last-write-wins per date).
- [`yfinance_provider.py`](../../src/quant_pilot/adapters/data/yfinance_provider.py) —
  `YFinanceMarketDataProvider` implementing `MarketDataProvider`: `get_ohlcv` (cache-aware,
  normalized columns), `get_liquidity` (20-day median ADV value + shares),
  `get_universe_membership` (delegates to the repository's PIT table), `get_option_chain`
  (deferred to the VRP phase). The network download is an **injectable callable**.
- [`calendar.py`](../../src/quant_pilot/adapters/data/calendar.py) — `nse_sessions` via
  `pandas_market_calendars` (feeds quality's missing-session check).

### Orchestration + sample
- [`workers/tasks.py`](../../src/quant_pilot/workers/tasks.py) — `ingest_universe(csv_path)`
  and `ingest_ohlcv(symbols, start, end)` jobs, each owning a unit-of-work transaction.
- [`api/deps.py`](../../src/quant_pilot/api/deps.py) — added `get_market_data_provider`.
- [`data/universe/sample_membership.csv`](../../data/universe/sample_membership.csv) — example
  events (includes YESBANK dropped 2020, HDFC merged out 2023).

## Design decisions & why

- **Point-in-time as intervals, rebuilt from events.** Free historical constituents don't
  exist as a table; NSE publishes add/drop revisions. Modeling intervals means a backtest on
  date D sees exactly the names in the index on D — including later-dropped/delisted names.
  This is the single biggest defense against phantom momentum alpha.
- **Continuity test for corporate actions** instead of trusting yfinance. It catches the exact
  failure mode that bites NSE data: silently wrong **bonus** adjustments (e.g. the HDFC merger
  class of events).
- **Injectable downloader.** The whole provider is unit-tested offline with a fake downloader;
  `yfinance` is imported lazily, so importing the module never needs the network.
- **Universe served from the repository, prices from yfinance.** yfinance has no historical
  constituents, so the provider delegates membership to the PIT table written in Step 1.
- **Pure engine / IO adapter split.** Universe/quality/corp-action logic is pure DataFrame-in,
  report-out (fast, deterministic tests); caching and downloads are the only IO.

## How to use

```python
# 1) ingest point-in-time membership (CSV: index,symbol,action,date)
from quant_pilot.workers.tasks import ingest_universe
ingest_universe("data/universe/sample_membership.csv")

# 2) download + cache OHLCV
from quant_pilot.workers.tasks import ingest_ohlcv
ingest_ohlcv(["RELIANCE.NS", "TCS.NS"], "2015-01-01", "2025-12-31")

# 3) query through the provider port
provider.get_universe_membership("NIFTY50", date(2018, 6, 1))   # survivorship-correct
provider.get_ohlcv("TCS.NS", date(2020, 1, 1), date(2020, 12, 31))
provider.get_liquidity("TCS.NS", date(2020, 6, 1))             # ADV for the impact model
```

Quality / corp-action checks (pure):

```python
from quant_pilot.engine.data.quality import check_quality
from quant_pilot.engine.data.corporate_actions import verify_adjustments
report = check_quality(df, expected_sessions=set(nse_sessions(start, end)))
ca = verify_adjustments(df, known_actions=[date(2023, 7, 13)])
```

## Tests & verification

- `tests/test_universe.py` — open vs closed intervals, re-additions, unsorted events,
  dict parsing, and a **CSV → repository → point-in-time query** roundtrip.
- `tests/test_market_data.py` — column normalization, **cache hit on second call** (downloader
  called once), liquidity from cache, missing-data error, deferred option chain, port
  conformance. All offline via a fake downloader.
- `tests/test_data_quality.py` — clean series passes; missing sessions / stale runs /
  non-positive / volume spikes detected; clean vs bad vs failed-on-known-date corp actions.
- 34 tests total; `ruff`, `mypy` (48 files), `pytest` all green.

## Gotchas

- Newer `yfinance` returns **MultiIndex columns** even for a single symbol — the provider
  flattens them before renaming.
- `get_liquidity` reads the **cache** and raises if prices were never ingested — ingest OHLCV
  before requesting liquidity.
- `pandas`/`pyarrow`/`yfinance` are now core deps (the API image grew); acceptable for
  single-user self-hosted, can be split into an extra later if image size matters.
- Quoted **spread** is not available from daily yfinance bars; `get_liquidity` returns ADV
  metrics only. Spread (for the full impact model) needs intraday/quote data — a later phase.

## Next

Step 5 — mathematical models (Ornstein-Uhlenbeck fit + half-life, Black-Scholes IV/Greeks,
Monte Carlo with fat-tailed/block-bootstrap VaR/CVaR), all behind the engine boundary.
