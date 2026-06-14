from __future__ import annotations

from datetime import date

from quant_pilot.adapters.persistence.repository import SqlAlchemyRepository
from quant_pilot.domain import ports
from quant_pilot.domain.models import (
    ArtifactRef,
    AuditEvent,
    BacktestRun,
    Instrument,
    RunStatus,
    StrategyConfig,
    StrategyType,
    UniverseMembership,
)


def test_repository_conforms_to_port(session):
    repo = SqlAlchemyRepository(session)
    assert isinstance(repo, ports.Repository)


def test_strategy_config_roundtrip(session):
    repo = SqlAlchemyRepository(session)
    cfg = StrategyConfig(name="mom-6m", strategy_type=StrategyType.MOMENTUM, params={"lb": 6})
    saved = repo.save_strategy_config(cfg)
    assert saved.id == cfg.id

    fetched = repo.get_strategy_config(cfg.id)
    assert fetched is not None
    assert fetched.name == "mom-6m"
    assert fetched.strategy_type is StrategyType.MOMENTUM
    assert fetched.params == {"lb": 6}


def test_backtest_run_lifecycle_with_artifacts(session):
    repo = SqlAlchemyRepository(session)
    run = repo.create_backtest_run(BacktestRun(params={"universe": "NIFTY50"}))
    assert run.status is RunStatus.QUEUED

    run.status = RunStatus.SUCCEEDED
    run.metrics = {"sharpe": 1.4}
    run.artifacts = [ArtifactRef(key="t.json", uri="file:///t.json", size=10)]
    updated = repo.update_backtest_run(run)
    assert updated.status is RunStatus.SUCCEEDED
    assert updated.metrics == {"sharpe": 1.4}
    assert updated.artifacts[0].key == "t.json"

    again = repo.get_backtest_run(run.id)
    assert again is not None and again.metrics == {"sharpe": 1.4}
    assert len(repo.list_backtest_runs()) == 1


def test_audit_is_appendable(session):
    repo = SqlAlchemyRepository(session)
    repo.append_audit(AuditEvent(actor="owais", action="login", ip="127.0.0.1"))
    repo.append_audit(AuditEvent(actor="owais", action="config.update"))
    events = repo.list_audit()
    assert len(events) == 2
    assert {e.action for e in events} == {"login", "config.update"}


def test_point_in_time_universe(session):
    repo = SqlAlchemyRepository(session)
    repo.upsert_instrument(Instrument(symbol="RELIANCE.NS", sector="Energy"))
    repo.add_universe_membership(
        [
            # left the index in 2020
            UniverseMembership(
                index="NIFTY50",
                symbol="OLDCO.NS",
                effective_from=date(2015, 1, 1),
                effective_to=date(2020, 1, 1),
            ),
            # still a member
            UniverseMembership(
                index="NIFTY50", symbol="RELIANCE.NS", effective_from=date(2015, 1, 1)
            ),
        ]
    )

    on_2018 = {m.symbol for m in repo.get_universe_membership("NIFTY50", date(2018, 6, 1))}
    on_2023 = {m.symbol for m in repo.get_universe_membership("NIFTY50", date(2023, 6, 1))}
    assert on_2018 == {"OLDCO.NS", "RELIANCE.NS"}  # survivorship-correct: OLDCO present in 2018
    assert on_2023 == {"RELIANCE.NS"}  # ...and absent in 2023
