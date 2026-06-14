from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient

from quant_pilot.adapters.persistence.repository import SqlAlchemyRepository
from quant_pilot.api.deps import get_job_queue
from quant_pilot.api.main import create_app
from quant_pilot.db.session import get_db
from quant_pilot.domain.models import UniverseMembership
from quant_pilot.workers.queue import InMemoryJobQueue


@pytest.fixture
def api(session):
    """Client with the DB and job queue overridden to in-memory test doubles."""
    app = create_app()
    queue = InMemoryJobQueue()

    def _db() -> Iterator:
        yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_job_queue] = lambda: queue
    return TestClient(app)


def test_submit_backtest_returns_202_and_persists(api):
    resp = api.post(
        "/api/v1/backtests", json={"strategy": "momentum", "params": {"symbols": ["TCS.NS"]}}
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert body["run_id"] and body["job_id"]

    run_id = body["run_id"]
    got = api.get(f"/api/v1/backtests/{run_id}")
    assert got.status_code == 200
    assert got.json()["params"] == {"symbols": ["TCS.NS"]}

    listed = api.get("/api/v1/backtests").json()
    assert any(r["id"] == run_id for r in listed)


def test_get_unknown_backtest_404(api):
    assert api.get("/api/v1/backtests/does-not-exist").status_code == 404


def test_job_status_and_sse_stream(api):
    job_id = api.post("/api/v1/backtests", json={"strategy": "momentum"}).json()["job_id"]

    status = api.get(f"/api/v1/jobs/{job_id}")
    assert status.status_code == 200
    assert status.json()["status"] == "finished"  # in-memory stub marks done

    stream = api.get(f"/api/v1/jobs/{job_id}/stream")
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert "data:" in stream.text


def test_universe_members_endpoint(api, session):
    repo = SqlAlchemyRepository(session)
    repo.add_universe_membership(
        [
            UniverseMembership(
                index="NIFTY50",
                symbol="OLDCO.NS",
                effective_from=date(2015, 1, 1),
                effective_to=date(2020, 1, 1),
            ),
            UniverseMembership(
                index="NIFTY50", symbol="RELIANCE.NS", effective_from=date(2015, 1, 1)
            ),
        ]
    )
    session.commit()

    on_2018 = api.get("/api/v1/universes/NIFTY50/members", params={"as_of": "2018-06-01"}).json()
    on_2023 = api.get("/api/v1/universes/NIFTY50/members", params={"as_of": "2023-06-01"}).json()
    assert {m["symbol"] for m in on_2018} == {"OLDCO.NS", "RELIANCE.NS"}
    assert {m["symbol"] for m in on_2023} == {"RELIANCE.NS"}


def test_execute_backtest_produces_metrics():
    import numpy as np
    import pandas as pd

    from quant_pilot.engine.backtest.engine import PriceData
    from quant_pilot.workers.tasks import execute_backtest

    n = 300
    t = np.arange(n)
    close = pd.DataFrame(
        {"WIN": 100 * 1.0015**t, "FLAT": np.full(n, 100.0), "LOSE": 100 * 0.9985**t},
        index=pd.bdate_range("2020-01-01", periods=n),
    )
    metrics = execute_backtest(PriceData(open=close, close=close), strategy="momentum")
    assert "performance" in metrics and "significance" in metrics
    assert metrics["summary"]["total_return"] > 0
