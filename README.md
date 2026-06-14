# Quant Pilot

Production-grade algorithmic trading platform for Indian equity markets (NSE/BSE).

- **Quant / strategy spec:** [`MASTER_PROMPT.md`](MASTER_PROMPT.md)
- **Platform / architecture / security:** [`docs/SYSTEM_DESIGN.md`](docs/SYSTEM_DESIGN.md)
- **Implementation wiki (step-by-step log):** [`docs/wiki/`](docs/wiki/README.md)

The quant **engine** is a pure, UI-agnostic library behind a typed **FastAPI** contract.
A future dashboard consumes that contract as a generated client. Long work (backtests,
ingestion) runs as async jobs (RQ + Redis). State lives in PostgreSQL; large data in a
Parquet datalake. Live trading is designed behind a `Broker` port and gated off until ready.

## Quickstart (local)

```bash
make install          # create .venv (Python 3.12) and install package + dev deps
make smoke            # health/security/openapi smoke tests — no DB/Redis needed
make dev              # run API at http://127.0.0.1:8000  (docs at /docs)
```

Health checks:

```bash
curl http://127.0.0.1:8000/health                 # liveness
curl http://127.0.0.1:8000/api/v1/system/health   # readiness (DB + Redis)
```

## Full stack (Docker)

```bash
cp infra/.env.example .env          # then edit; set QP_SESSION_SECRET
make up                             # api + worker + scheduler + postgres + redis
make migrate                        # apply DB migrations
make logs                           # tail
make down
```

## Developer workflow

```bash
make fmt     # format + autofix
make lint    # ruff check + format check
make type    # mypy
make test    # pytest
make audit   # pip-audit (dependency CVEs)
```

## Layout

```
src/quant_pilot/
  engine/      pure quant library (data, models, strategies, backtest, risk, analysis)
  domain/      shared models + PORT interfaces (ports filled in next)
  adapters/    concrete ports: data, persistence, artifacts, broker, secrets
  api/         FastAPI app (routers, security, schemas)
  workers/     RQ tasks + APScheduler
  db/          SQLAlchemy base + Alembic migrations
  config/      pydantic-settings (env-driven infra config)
config/settings.yaml   quant/strategy parameters (engine reads this)
infra/                 Dockerfile, docker-compose, .env.example
```

## Security posture (single-user, self-hosted)

- Localhost-bind by default; remote access via SSH tunnel/VPN, TLS via Caddy if exposed.
- Argon2id passwords + signed httpOnly/SameSite session cookie + TOTP 2FA step-up for trading.
- Broker secrets in the OS keychain — never in repo/DB/plaintext.
- Server-side pre-trade risk checks + kill switch; append-only audit log.
- `trading_enabled=false` by default. See `docs/SYSTEM_DESIGN.md` §8.
