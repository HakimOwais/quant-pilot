from __future__ import annotations

from collections.abc import Iterator

import pyotp
import pytest
from fastapi.testclient import TestClient

from quant_pilot.adapters.broker.paper_broker import PaperBroker
from quant_pilot.adapters.persistence.repository import SqlAlchemyRepository
from quant_pilot.adapters.secrets.keyring_store import InMemorySecretStore
from quant_pilot.api.deps import get_broker, get_secret_store
from quant_pilot.api.main import create_app
from quant_pilot.api.security.auth import TOTP_SECRET_KEY, require_trading_enabled
from quant_pilot.db.session import get_db


def _db_override(session):
    def _db() -> Iterator:
        yield session

    return _db


@pytest.fixture
def disabled_client(session):
    """Trading disabled (default) — only the DB is overridden."""
    app = create_app()
    app.dependency_overrides[get_db] = _db_override(session)
    return TestClient(app)


@pytest.fixture
def trading(session):
    """Trading enabled, broker primed with a mark, 2FA provisioned."""
    app = create_app()
    broker = PaperBroker()
    broker.set_mark("RELIANCE.NS", 2900.0)
    secrets = InMemorySecretStore()
    totp_secret = pyotp.random_base32()
    secrets.set_secret(TOTP_SECRET_KEY, totp_secret)

    app.dependency_overrides[get_db] = _db_override(session)
    app.dependency_overrides[get_broker] = lambda: broker
    app.dependency_overrides[get_secret_store] = lambda: secrets
    app.dependency_overrides[require_trading_enabled] = lambda: None
    return TestClient(app), broker, totp_secret, session


def _propose(client, qty=100):
    return client.post(
        "/api/v1/orders",
        json={"symbol": "RELIANCE.NS", "side": "buy", "quantity": qty},
    )


def test_propose_blocked_when_trading_disabled(disabled_client):
    assert _propose(disabled_client).status_code == 403


def test_propose_creates_pending_and_audits(trading):
    client, _broker, _totp, session = trading
    resp = _propose(client)
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"

    actions = {e.action for e in SqlAlchemyRepository(session).list_audit()}
    assert "order.proposed" in actions


def test_approve_requires_2fa(trading):
    client, _broker, _totp, _session = trading
    order_id = _propose(client).json()["id"]
    assert client.post(f"/api/v1/orders/{order_id}/approve").status_code == 403  # no X-TOTP


def test_approve_with_valid_2fa_fills(trading):
    client, broker, totp_secret, _session = trading
    order_id = _propose(client).json()["id"]
    code = pyotp.TOTP(totp_secret).now()

    resp = client.post(f"/api/v1/orders/{order_id}/approve", headers={"X-TOTP": code})
    assert resp.status_code == 200
    assert resp.json()["status"] == "filled"
    assert broker.get_positions()[0].symbol == "RELIANCE.NS"


def test_kill_switch_then_approve_is_rejected(trading):
    client, _broker, totp_secret, _session = trading
    order_id = _propose(client).json()["id"]

    halt = client.post("/api/v1/system/halt")
    assert halt.status_code == 200 and halt.json()["halted"] is True

    code = pyotp.TOTP(totp_secret).now()
    resp = client.post(f"/api/v1/orders/{order_id}/approve", headers={"X-TOTP": code})
    assert resp.json()["status"] == "rejected"  # broker halted -> no fill


def test_positions_endpoint_after_fill(trading):
    client, _broker, totp_secret, _session = trading
    order_id = _propose(client).json()["id"]
    client.post(
        f"/api/v1/orders/{order_id}/approve", headers={"X-TOTP": pyotp.TOTP(totp_secret).now()}
    )

    positions = client.get("/api/v1/portfolio/positions").json()
    assert any(p["symbol"] == "RELIANCE.NS" for p in positions)


def test_resume_requires_2fa(trading):
    client, _broker, _totp, _session = trading
    assert client.post("/api/v1/system/resume").status_code == 403
