# Step 14 — PaperBroker (the Broker port, simulated)

**Build sequence:** 14 · **Status:** ✅ done

## Goal

Implement the execution boundary defined in Step 1 with a paper (simulated) broker, so the trading
path can be exercised end-to-end without a real broker — and the Kite/SmartAPI adapter later just
slots into the same `Broker` port.

## What was built — [`adapters/broker/paper_broker.py`](../../src/quant_pilot/adapters/broker/paper_broker.py)

`PaperBroker` implements the full `Broker` port: `place_order`, `modify_order`, `cancel_order`,
`get_orders`, `get_positions`, `get_margin`. Plus controls: `set_mark`/`update_marks`, `halt`/`resume`.

- **Fills** market orders at the current mark adjusted by the **impact model** (buy pays up, sell
  receives less) and charges the **Indian explicit cost stack** — reusing `engine/backtest`
  costs + impact, so paper fills match backtest assumptions.
- **Limit orders rest** until marketable; `update_marks` re-checks and fills pending orders.
- Tracks **cash, signed positions (avg price), and orders**; `get_margin` reports
  available / used / total.
- **Kill switch** (`halt`) and a **buying-power** check reject orders server-side.

## Design decisions & why

- **Same Broker port → same engine costs.** Paper fills go through the identical impact + cost
  functions the backtest uses, so paper P&L is consistent with simulated P&L (the reconciliation
  the live-readiness checklist in SYSTEM_DESIGN §8.7 demands before real capital).
- **Kill switch + buying power in the broker**, portfolio/sector limits in the API/risk layer —
  defense in depth across the layers, not duplicated.
- **Mark-driven fills.** The broker is fed marks (last prices) and fills against them; this matches
  how a live adapter receives quotes and keeps the paper broker decoupled from the data layer.
- **Stateful, in-memory.** A paper broker is inherently session state; persistence of the live book
  to the DB (via the Repository) is wired when live trading is enabled, not now.

## How to use

```python
from quant_pilot.adapters.broker.paper_broker import PaperBroker
from quant_pilot.domain.models import Order, OrderSide

broker = PaperBroker(initial_cash=1_000_000)
broker.set_mark("RELIANCE.NS", 2900.0)
filled = broker.place_order(Order(symbol="RELIANCE.NS", side=OrderSide.BUY, quantity=100))
broker.get_positions(); broker.get_margin()
broker.halt()   # kill switch -> subsequent orders rejected
```

## Tests & verification

- `tests/test_paper_broker.py` — port conformance; market buy updates cash/position with the exact
  impact-adjusted fill (100.05) + cost; **insufficient buying power rejected**; limit order rests
  then fills on a mark move; cancel pending; sell closes and returns cash; **kill switch blocks**
  orders (and resumes); margin reflects exposure.
- **107 tests total**; `ruff`, `mypy` (70 files), `pytest` all green.

## Gotchas

- Marks must be set before placing an order (no price → reject), mirroring a real feed.
- Position quantities are whole shares (Indian cash equities); fractional sizing isn't modeled.
- The book is in-memory; it isn't yet persisted via the Repository (that lands with live trading,
  behind `trading_enabled` + the order-approval/2FA path in SYSTEM_DESIGN §8).

## Next

Wire the order/approval path: a gated `POST /api/v1/orders` (behind `trading_enabled` + 2FA
step-up + audit) using a `get_broker` dependency, and persist the live book — or build the
read-only dashboard once a Node toolchain is available.
