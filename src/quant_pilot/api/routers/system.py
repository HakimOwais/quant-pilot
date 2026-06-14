"""System endpoints: liveness, readiness, and basic info.

- /health (root)            -> liveness; never touches external deps.
- /api/v1/system/health     -> readiness; checks DB + Redis, degrades gracefully.

The trading kill switch (POST /api/v1/system/halt) is intentionally NOT implemented
here yet — it arrives with the order/execution layer, gated behind trading_enabled.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from quant_pilot.api.deps import get_broker, get_repository
from quant_pilot.api.security.auth import require_trading_enabled, verify_totp
from quant_pilot.config.settings import get_settings
from quant_pilot.domain import ports
from quant_pilot.domain.models import AuditEvent

router = APIRouter(tags=["system"])
router_v1 = APIRouter(prefix="/system", tags=["system"])


class Health(BaseModel):
    status: str
    service: str
    version: str


class Readiness(BaseModel):
    status: str
    database: str
    redis: str
    trading_enabled: bool


@router.get("/health", response_model=Health)
def liveness() -> Health:
    """Process is up. Used by container/orchestrator liveness probes."""
    settings = get_settings()
    return Health(status="ok", service=settings.app_name, version=settings.version)


@router_v1.get("/health", response_model=Readiness)
def readiness() -> Readiness:
    """Checks external dependencies; returns 'degraded' (not 500) if any are down."""
    settings = get_settings()
    db_ok = _check_db()
    redis_ok = _check_redis()
    return Readiness(
        status="ok" if (db_ok and redis_ok) else "degraded",
        database="ok" if db_ok else "down",
        redis="ok" if redis_ok else "down",
        trading_enabled=settings.trading_enabled,
    )


def _check_db() -> bool:
    try:
        from sqlalchemy import text

        from quant_pilot.db.base import get_engine

        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _check_redis() -> bool:
    try:
        import redis

        client = redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=1)
        return bool(client.ping())
    except Exception:
        return False


class HaltState(BaseModel):
    halted: bool


@router_v1.post("/halt", response_model=HaltState)
def halt_trading(
    request: Request,
    broker: ports.Broker = Depends(get_broker),
    repo: ports.Repository = Depends(get_repository),
) -> HaltState:
    """Kill switch — always available (emergency-safe direction). Halts the broker."""
    broker.halt()  # type: ignore[attr-defined]
    repo.append_audit(
        AuditEvent(
            actor="local-user",
            action="system.halt",
            resource_type="system",
            ip=request.client.host if request.client else None,
        )
    )
    return HaltState(halted=True)


@router_v1.post(
    "/resume",
    response_model=HaltState,
    dependencies=[Depends(require_trading_enabled), Depends(verify_totp)],
)
def resume_trading(
    request: Request,
    broker: ports.Broker = Depends(get_broker),
    repo: ports.Repository = Depends(get_repository),
) -> HaltState:
    """Re-enable trading after a halt — gated by trading_enabled + 2FA step-up."""
    broker.resume()  # type: ignore[attr-defined]
    repo.append_audit(
        AuditEvent(
            actor="local-user",
            action="system.resume",
            resource_type="system",
            ip=request.client.host if request.client else None,
        )
    )
    return HaltState(halted=False)
