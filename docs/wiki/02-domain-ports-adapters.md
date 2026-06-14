# Step 1 — Domain, Ports, Adapters, First Migration

**Build sequence:** 1–2 · **Status:** ✅ done

## Goal

Lock the **contract** everything else builds against: the persistence-agnostic domain models,
the port interfaces (the seams), the first concrete adapters, and the initial database schema.

## What was built

### Domain ([`domain/`](../../src/quant_pilot/domain/))
- [`models.py`](../../src/quant_pilot/domain/models.py) — Pydantic entities + `StrEnum`s:
  `Instrument`, `UniverseMembership`, `StrategyConfig`, `ArtifactRef`, `BacktestRun`, `Order`,
  `Position`, `MarginInfo`, `AuditEvent`, `JobStatus`. `from_attributes=True` enables clean
  ORM→domain mapping.
- [`ports.py`](../../src/quant_pilot/domain/ports.py) — the **7 ports** as
  `@runtime_checkable` Protocols: `Clock`, `SecretStore`, `ArtifactStore`, `Repository`,
  `JobQueue`, `MarketDataProvider`, `Broker`.

### Adapters ([`adapters/`](../../src/quant_pilot/adapters/))
- [`secrets/keyring_store.py`](../../src/quant_pilot/adapters/secrets/keyring_store.py) —
  `KeyringSecretStore` (OS keychain, injectable backend) + `InMemorySecretStore` (tests).
- [`artifacts/local_store.py`](../../src/quant_pilot/adapters/artifacts/local_store.py) —
  `LocalArtifactStore` with a **path-traversal guard**.
- [`persistence/models.py`](../../src/quant_pilot/adapters/persistence/models.py) — SQLAlchemy
  ORM (JSONB on Postgres, JSON on SQLite).
- [`persistence/repository.py`](../../src/quant_pilot/adapters/persistence/repository.py) —
  `SqlAlchemyRepository` implementing the `Repository` port.
- [`clock.py`](../../src/quant_pilot/adapters/clock.py) — `SystemClock` / `FixedClock`.

### Composition + schema
- [`api/deps.py`](../../src/quant_pilot/api/deps.py) — wires adapters to **port-typed**
  dependencies (mypy verifies conformance at this seam).
- [`db/migrations/versions/0001_initial.py`](../../src/quant_pilot/db/migrations/versions/0001_initial.py)
  — creates `strategy_configs`, `backtest_runs`, `audit_events`, `instruments`, and the
  point-in-time `universe_membership` table.

## Design decisions & why

- **Protocols, not ABCs.** Adapters conform structurally without importing anything from the
  domain — true decoupling. Conformance is still checked: by mypy at `api/deps.py` and by
  `isinstance` in tests (Protocols are `@runtime_checkable`).
- **Pydantic domain ≠ SQLAlchemy ORM.** Two representations, mapped in the repository. Slightly
  more code, but the engine never imports SQLAlchemy (keeps the hexagon clean).
- **Append-only audit.** The repository exposes `append_audit` / `list_audit` only — no update
  or delete — matching SYSTEM_DESIGN §8.6.
- **Point-in-time universe table** modeled as `(index, symbol, effective_from, effective_to)`
  intervals — the storage shape that makes survivorship-free queries trivial.
- **Hand-written first migration** using `JSONB` for Postgres correctness (autogenerate against
  SQLite would have produced plain `JSON`).

## How to use

```python
from quant_pilot.adapters.persistence.repository import SqlAlchemyRepository
repo = SqlAlchemyRepository(session)                       # session from get_db / unit-of-work
repo.save_strategy_config(cfg)
run = repo.create_backtest_run(BacktestRun(params={...}))
members = repo.get_universe_membership("NIFTY50", as_of=date(2018, 6, 1))
```

Secrets: `KeyringSecretStore().set_secret("kite_api_key", "...")`.
Artifacts: `LocalArtifactStore(dir).save_json("runs/1/metrics.json", {...})`.

## Tests & verification

- `tests/test_repository.py` — config/run/audit CRUD; **point-in-time query correctness**
  (a dropped name present in 2018, absent in 2023); port conformance.
- `tests/test_adapters.py` — artifact roundtrip + **path-traversal rejection**; secret
  roundtrip + idempotent delete; clock conformance.
- `alembic upgrade head --sql` renders valid Postgres DDL (5 tables, JSONB, indexes).

## Gotchas

- SQLite `DateTime(timezone=True)` returns naive datetimes — tests avoid asserting exact
  tz-aware equality across a roundtrip.
- `ArtifactStore` keys must be relative; `..`/absolute keys raise `ValueError` by design.

## Next

Step 3 — pull real data through these ports: point-in-time universe ingestion + the
`MarketDataProvider` adapter, with quality and corporate-action verifiers.
