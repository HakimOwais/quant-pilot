from __future__ import annotations

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from quant_pilot.api.main import create_app
from quant_pilot.engine.backtest.engine import PriceData
from quant_pilot.workers.tasks import sweep_parameter


def _prices(n=320):
    t = np.arange(n)
    return pd.DataFrame(
        {
            "A": 100 * 1.0015**t,
            "B": 100 * 1.0010**t,
            "C": 100 * 1.0005**t,
            "D": 100 * 0.9990**t,
            "E": 100 * 0.9985**t,
        },
        index=pd.bdate_range("2020-01-01", periods=n),
    )


def test_sweep_returns_point_per_value():
    close = _prices()
    pts = sweep_parameter(PriceData(open=close, close=close), "long_pct", [0.2, 0.4, 0.6])
    assert len(pts) == 3
    assert [p["value"] for p in pts] == [0.2, 0.4, 0.6]
    assert all("sharpe" in p and "total_return" in p for p in pts)


def test_sweep_endpoint_rejects_bad_param():
    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/sweep",
        json={
            "symbols": ["X"],
            "start": "2020-01-01",
            "end": "2020-12-31",
            "param": "evil",
            "values": [1],
        },
    )
    assert resp.status_code == 422


def test_sweep_endpoint_no_data():
    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/sweep",
        json={
            "symbols": ["NOTCACHED.NS"],
            "start": "2020-01-01",
            "end": "2020-12-31",
            "param": "long_pct",
            "values": [0.2, 0.4],
        },
    )
    assert resp.status_code == 422
