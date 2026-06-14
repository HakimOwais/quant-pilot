# Step 0 — Scaffold

**Build sequence:** 0 · **Status:** ✅ done

## Goal

Create the repository skeleton so every later piece has a home and the system **runs** from
day one — packaging, an importable/serveable API, async/job plumbing, persistence wiring,
infra (Docker), and CI — with security defaults baked in.

## What was built

| Area | Files |
|------|-------|
| Packaging | [`pyproject.toml`](../../pyproject.toml) (hatchling, src layout, ruff/mypy/pytest config) |
| Config | [`config/settings.py`](../../src/quant_pilot/config/settings.py) (pydantic-settings, env-driven) |
| Logging | [`log.py`](../../src/quant_pilot/log.py) (structlog: console in dev, JSON in prod) |
| API | [`api/main.py`](../../src/quant_pilot/api/main.py), [`api/routers/system.py`](../../src/quant_pilot/api/routers/system.py), [`api/security/headers.py`](../../src/quant_pilot/api/security/headers.py) |
| DB | [`db/base.py`](../../src/quant_pilot/db/base.py), [`db/session.py`](../../src/quant_pilot/db/session.py), Alembic env/ini |
| Workers | [`workers/queue.py`](../../src/quant_pilot/workers/queue.py), [`workers/scheduler.py`](../../src/quant_pilot/workers/scheduler.py) |
| Infra | [`infra/Dockerfile`](../../infra/Dockerfile), [`infra/docker-compose.yml`](../../infra/docker-compose.yml), `.env.example` |
| Dev/CI | [`Makefile`](../../Makefile), [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) |
| Quant config | [`config/settings.yaml`](../../config/settings.yaml) (engine reads this) |

The full package topology (`engine/`, `domain/`, `adapters/`, `api/`, `workers/`, `db/`) was
created with docstring'd `__init__.py` placeholders so subsequent steps drop straight in.

## Design decisions & why

- **Hexagonal from the start.** The engine is a pure library; the API/dashboard are clients.
  This is the decision that makes the future dashboard painless (see SYSTEM_DESIGN §2).
- **FastAPI + Pydantic v2.** Same language as the engine → no serialization mismatch, and a
  free OpenAPI schema the frontend will codegen a typed client from.
- **Postgres over SQLite** (compose) because the worker and API write concurrently.
- **RQ + Redis** for jobs, **APScheduler** for cron — simplest reliable async for one user.
- **Security defaults on first commit:** localhost-bind, security-headers middleware
  (CSP/XFO/HSTS), signed httpOnly/SameSite=strict session cookie, `trading_enabled=false`,
  and a prod guard that refuses to boot with the dev session secret.

## How to use

```bash
make install     # venv (py3.12) + deps
make smoke       # health/security/openapi tests, no DB/Redis needed
make dev         # API at http://127.0.0.1:8000 (/docs for Swagger)
make up          # full docker stack (api/worker/scheduler/postgres/redis)
make migrate     # alembic upgrade head
```

Endpoints: `GET /health` (liveness), `GET /api/v1/system/health` (readiness; degrades to
`"degraded"` instead of 500 when DB/Redis are down).

## Tests & verification

- `tests/test_health.py`: liveness, security headers present, OpenAPI schema valid, readiness
  degrades gracefully without external deps.
- All gates green: `ruff`, `mypy`, `pytest`, `pip-audit`; Alembic config loads.

## Gotchas

- macOS ships bash 3.2 (no associative arrays) — scaffolding scripts use portable loops.
- System Python was 3.10; the project targets **3.12** (use `python3.12`).
- Harmless `StarletteDeprecationWarning` from FastAPI's TestClient (httpx/starlette versions).

## Next

Step 1 — lock the contract: domain models + the 7 ports + first adapters + first migration.
