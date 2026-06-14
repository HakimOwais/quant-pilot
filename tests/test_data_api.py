from __future__ import annotations

from collections.abc import Iterator

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from quant_pilot.api.deps import get_job_queue, get_market_data_provider
from quant_pilot.api.main import create_app
from quant_pilot.db.session import get_db
from quant_pilot.workers.queue import InMemoryJobQueue


class _FakeProvider:
    def get_ohlcv(self, symbol, start, end, frequency="1d"):
        idx = pd.date_range("2020-01-01", periods=3, freq="B")
        return pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0],
                "high": [101.0, 102.0, 103.0],
                "low": [99.0, 100.0, 101.0],
                "close": [100.5, 101.5, 102.5],
                "adj_close": [100.5, 101.5, 102.5],
                "volume": [1000.0, 1100.0, 1200.0],
            },
            index=idx,
        )


@pytest.fixture
def api(session):
    app = create_app()
    queue = InMemoryJobQueue()

    def _db() -> Iterator:
        yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_job_queue] = lambda: queue
    app.dependency_overrides[get_market_data_provider] = lambda: _FakeProvider()
    return TestClient(app)


def test_ingest_ohlcv_enqueues(api):
    resp = api.post(
        "/api/v1/data/ohlcv",
        json={"symbols": ["TCS.NS", "INFY.NS"], "start": "2018-01-01", "end": "2024-12-31"},
    )
    assert resp.status_code == 202
    assert resp.json()["job_id"]


def test_ingest_universe_enqueues(api):
    resp = api.post(
        "/api/v1/data/universe", json={"csv_path": "data/universe/sample_membership.csv"}
    )
    assert resp.status_code == 202
    assert resp.json()["job_id"]


def test_get_bars_serializes(api):
    bars = api.get(
        "/api/v1/data/ohlcv/TCS.NS", params={"start": "2020-01-01", "end": "2020-01-31"}
    ).json()
    assert len(bars) == 3
    assert bars[0]["date"] == "2020-01-01"
    assert bars[0]["close"] == 100.5
    assert bars[0]["volume"] == 1000.0
