"""Smoke tests: the app imports, starts, serves health, sets security headers,
and produces a valid OpenAPI schema (the frontend client generation depends on it).
These run without any external dependency (no DB/Redis needed)."""

from __future__ import annotations


def test_liveness(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "quant-pilot"


def test_security_headers_present(client):
    r = client.get("/health")
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" in r.headers


def test_openapi_contract(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert r.json()["info"]["title"] == "Quant Pilot API"


def test_readiness_degrades_without_deps(client):
    # No DB/Redis in the test env -> 200 with status 'degraded', never a 500.
    r = client.get("/api/v1/system/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["trading_enabled"] is False
