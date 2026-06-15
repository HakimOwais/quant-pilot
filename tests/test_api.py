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
    assert len(metrics["equity_curve"]) > 0
    assert {"date", "equity", "drawdown"} <= metrics["equity_curve"][0].keys()


def test_execute_backtest_benchmark_overlay():
    import numpy as np
    import pandas as pd

    from quant_pilot.engine.backtest.engine import PriceData
    from quant_pilot.workers.tasks import execute_backtest

    n = 300
    idx = pd.bdate_range("2020-01-01", periods=n)
    t = np.arange(n)
    close = pd.DataFrame(
        {"WIN": 100 * 1.0015**t, "FLAT": np.full(n, 100.0), "LOSE": 100 * 0.9985**t}, index=idx
    )
    rng = np.random.default_rng(0)
    bench = pd.Series(
        100 * np.cumprod(1 + rng.normal(0.0004, 0.008, n)), index=idx
    )  # noisy benchmark
    metrics = execute_backtest(PriceData(open=close, close=close), benchmark_close=bench)
    pts = metrics["equity_curve"]
    assert any("benchmark" in p for p in pts)
    last = pts[-1]
    assert last["benchmark"] > 0  # normalized buy-and-hold from initial capital

    attr = metrics["attribution"]
    assert {"alpha_annual", "beta", "information_ratio", "r_squared"} <= attr.keys()
    assert isinstance(attr["alpha_significant"], bool)


def test_equity_curve_endpoint(session, tmp_path):
    from quant_pilot.adapters.artifacts.local_store import LocalArtifactStore
    from quant_pilot.api.deps import get_artifact_store

    app = create_app()
    store = LocalArtifactStore(tmp_path)

    def _db():
        yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_artifact_store] = lambda: store
    client = TestClient(app)

    store.save_json(
        "runs/abc/equity.json", [{"date": "2020-01-01", "equity": 1_000_000.0, "drawdown": 0.0}]
    )
    ok = client.get("/api/v1/backtests/abc/equity")
    assert ok.status_code == 200
    assert ok.json()[0]["equity"] == 1_000_000.0
    assert client.get("/api/v1/backtests/missing/equity").status_code == 404


def test_execute_backtest_honours_custom_momentum_params():
    import numpy as np
    import pandas as pd

    from quant_pilot.engine.backtest.engine import PriceData
    from quant_pilot.workers.tasks import execute_backtest

    n = 320
    t = np.arange(n)
    close = pd.DataFrame(
        {
            "A": 100 * 1.0015**t,
            "B": 100 * 1.0010**t,
            "C": 100 * 1.0005**t,
            "D": 100 * 0.9990**t,
        },
        index=pd.bdate_range("2020-01-01", periods=n),
    )
    # custom params: shorter lookback, no skip, wider selection (extra keys like symbols ignored)
    metrics = execute_backtest(
        PriceData(open=close, close=close),
        strategy_params={"lookbacks": [3], "skip_months": 0, "long_pct": 0.5, "symbols": ["A"]},
    )
    assert metrics["summary"]["n_rebalances"] >= 1
    assert len(metrics["equity_curve"]) > 0


def test_execute_backtest_empty_data_raises_clear_error():
    import pandas as pd
    import pytest

    from quant_pilot.engine.backtest.engine import PriceData
    from quant_pilot.workers.tasks import execute_backtest

    with pytest.raises(ValueError, match="no price data"):
        execute_backtest(PriceData(open=pd.DataFrame(), close=pd.DataFrame()))
