# Step 15 — Gated Order/Approval Path (secure write-path)

**Build sequence:** 15 · **Status:** ✅ done

## Goal

Implement the secure write-path designed up front (SYSTEM_DESIGN §6/§7/§8): propose an order, then
approve it with a 2FA step-up, with the trading gate, server-side kill switch, buying-power check,
and a full audit trail — all the controls that must exist before this dashboard ever moves capital.

## What was built

### Persistence — orders table
- `OrderORM` + `save_order`/`get_order`/`list_orders` on the Repository (+ port).
- Migration [`0002_orders.py`](../../src/quant_pilot/db/migrations/versions/0002_orders.py).

### Security deps — [`api/security/auth.py`](../../src/quant_pilot/api/security/auth.py)
- `require_trading_enabled` — 403s every trading endpoint while `trading_enabled=false` (default).
- `verify_totp` — TOTP 2FA via `pyotp`; the shared secret lives in the **SecretStore** (keychain),
  never in repo/DB.

### Endpoints
- [`routers/orders.py`](../../src/quant_pilot/api/routers/orders.py):
  `POST /api/v1/orders` → **PENDING** (trading-gated, pre-trade check, audited);
  `POST /api/v1/orders/{id}/approve` → **2FA step-up** → `broker.place_order` → FILLED/REJECTED
  (audited); `GET /orders[/{id}]`.
- [`routers/portfolio.py`](../../src/quant_pilot/api/routers/portfolio.py):
  `GET /api/v1/portfolio/positions` + `/margin` (trading-gated).
- [`routers/system.py`](../../src/quant_pilot/api/routers/system.py): `POST /api/v1/system/halt`
  (kill switch — **always available**, audited) and `POST /api/v1/system/resume`
  (trading-gated + 2FA).
- `get_broker` DI (app-session PaperBroker singleton).

## Design decisions & why

- **Two-step propose → approve** so the act of moving money requires a deliberate, **2FA-confirmed**
  second call — not a single click. Matches SYSTEM_DESIGN §7's order flow.
- **Defense in depth**: trading gate (API) → 2FA (API) → kill switch + buying power (broker). Each
  layer independently can stop a bad order; the UI can't bypass any of them.
- **Kill switch is ungated and emergency-safe** (halts without 2FA); *resuming* requires 2FA — you
  can always stop, but restarting is deliberate.
- **TOTP secret in the SecretStore**, audit log append-only — the secrets/auditability rails from
  §8.3/§8.6 are enforced here, not bolted on later.
- **Everything stays off by default** (`trading_enabled=false`); enabling live trading is a config
  decision, and even then orders are paper until the Kite adapter replaces the PaperBroker behind
  the same `Broker` port.

## How to use

```bash
# enable trading (QP_TRADING_ENABLED=true) and provision the TOTP secret in the keychain first
curl -X POST localhost:8000/api/v1/orders \
  -d '{"symbol":"RELIANCE.NS","side":"buy","quantity":100}'        # -> 201 PENDING
curl -X POST localhost:8000/api/v1/orders/<id>/approve \
  -H 'X-TOTP: 123456'                                              # -> FILLED / REJECTED
curl -X POST localhost:8000/api/v1/system/halt                    # kill switch (always works)
curl localhost:8000/api/v1/portfolio/positions
```

## Tests & verification

- `tests/test_orders.py` — propose blocked when trading disabled (403); propose → PENDING +
  `order.proposed` audit; approve without 2FA → 403; **approve with valid TOTP → FILLED** + broker
  position; **kill switch → subsequent approve REJECTED**; positions endpoint after fill; resume
  requires 2FA.
- **114 tests total**; `ruff`, `mypy` (75 files), `pytest` all green; migration 0002 renders.

## Gotchas

- The TOTP secret must be provisioned in the SecretStore (`totp_secret`) or 2FA endpoints 503 —
  a setup step before live trading.
- Identity is a fixed `"local-user"` (single-user); a real login wires the actor into the audit
  events here.
- Orders persist to the DB for history/audit; the live position book is the broker's in-memory
  state (PaperBroker) — fine for paper, revisited when the real broker adapter lands.

## Next

The remaining live-readiness items (SYSTEM_DESIGN §8.7: slippage monitor, broker reconciliation,
paper-vs-sim P&L) and the **Kite/SmartAPI broker adapter** — or the read-only dashboard once a Node
toolchain is available.
