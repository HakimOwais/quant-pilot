# Step 16 — SmartAPI Broker Adapter + Live Readiness

**Build sequence:** 16 · **Status:** ✅ done

## Goal

A real broker adapter (Angel One SmartAPI) behind the `Broker` port, plus the live-readiness checks
from SYSTEM_DESIGN §8.7 that must pass before real capital: broker reconciliation, slippage
monitoring, and paper-vs-sim P&L divergence.

## What was built

### [`adapters/broker/smartapi_broker.py`](../../src/quant_pilot/adapters/broker/smartapi_broker.py)
`SmartApiBroker` implements the `Broker` port against Angel One SmartConnect:
- `place_order` builds SmartAPI params (symboltoken from an injected token map, transaction/order
  type, product, exchange) and returns **SUBMITTED** + broker order id (live orders are async).
- `get_orders` maps the order book status → `OrderStatus`; `get_positions`, `get_margin` map the
  position/funds responses; `cancel_order`/`modify_order` call through.
- The SDK **client is injected** (lazily imported in the live factory), so all translation logic is
  unit-tested with a fake client — no network or credentials needed. Same port as PaperBroker, so
  switching is a wiring change.

### Live readiness — [`live/`](../../src/quant_pilot/live/)
- [`reconciliation.py`](../../src/quant_pilot/live/reconciliation.py) — `reconcile_positions`:
  broker positions vs the internal book; any mismatch ⇒ not ok (halt and investigate).
- [`slippage.py`](../../src/quant_pilot/live/slippage.py) — `SlippageMonitor`: records realized
  fill vs expected price as **adverse bps**; flags when the mean exceeds a threshold (the impact
  model is too optimistic).
- [`pnl.py`](../../src/quant_pilot/live/pnl.py) — `pnl_divergence`: correlation + tracking error +
  max diff between live/paper and simulated returns; not ok if tracking error is too high.

## Design decisions & why

- **Same Broker port** for paper and live — the engine, API, and order path never change; going
  live is selecting `SmartApiBroker` in the live factory and flipping `trading_enabled`.
- **Injected SDK client** mirrors the yfinance pattern: testable offline, real SDK imported lazily,
  credentials from the SecretStore.
- **Async order model** (place → SUBMITTED → poll order book) matches how real brokers actually
  work, rather than pretending fills are synchronous.
- **Live readiness as explicit gates**, not vibes — reconciliation/slippage/PnL are computable
  pass/fail checks that operationalize §8.7's "reconcile paper to live before risking capital".

## How to use

```python
from quant_pilot.live.reconciliation import reconcile_positions
from quant_pilot.live.slippage import SlippageMonitor
from quant_pilot.live.pnl import pnl_divergence

reconcile_positions(broker.get_positions(), internal_book)        # must be ok before/while trading
mon = SlippageMonitor(threshold_bps=20); mon.record(side, expected, fill); mon.report()
pnl_divergence(live_returns, sim_returns)                          # gate before going live
```

The live `SmartApiBroker` is constructed in a factory that pulls credentials from the SecretStore
and a symbol→token map; it then slots into `get_broker` behind `trading_enabled`.

## Tests & verification

- `tests/test_smartapi_broker.py` — port conformance; place_order builds the right params + returns
  SUBMITTED/broker id; missing token raises; order-book status mapping (complete→FILLED);
  positions/margin mapping; cancel ack. All via a fake SmartAPI client.
- `tests/test_live_readiness.py` — reconciliation match/mismatch; adverse-slippage sign + flagging;
  P&L tracks when close, flags when divergent.
- **126 tests total**; `ruff`, `mypy` (80 files), `pytest` all green.

## Gotchas

- SmartConnect field names/response shapes are taken from the documented API; verify against the
  installed SDK version and adjust the mappers if Angel One changes them.
- Live fills are asynchronous — `place_order` returns SUBMITTED; reconcile via `get_orders()` /
  `get_positions()`, don't assume an immediate fill.
- The symbol→token map and session/credentials are operational prerequisites (SecretStore), not
  modeled here beyond the injection point.

## Next

The remaining operational rails (audit hash-chaining, dead-man's-heartbeat, the live broker
factory + reconciliation loop), and the **read-only dashboard** once a Node toolchain is available.
