"""SQLAlchemy implementation of the Repository port.

Takes a Session (unit of work). Methods flush so generated/echoed values are available,
but do NOT commit — the caller owns the transaction boundary (api/deps.get_db commits,
workers wrap their own session).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from quant_pilot.adapters.persistence.models import (
    AuditEventORM,
    BacktestRunORM,
    InstrumentORM,
    StrategyConfigORM,
    UniverseMembershipORM,
)
from quant_pilot.domain.models import (
    ArtifactRef,
    AuditEvent,
    BacktestRun,
    Instrument,
    RunStatus,
    StrategyConfig,
    UniverseMembership,
)


class SqlAlchemyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --- strategy configs ---------------------------------------------------

    def save_strategy_config(self, cfg: StrategyConfig) -> StrategyConfig:
        orm = self.session.get(StrategyConfigORM, cfg.id)
        if orm is None:
            orm = StrategyConfigORM(id=cfg.id)
            self.session.add(orm)
        orm.name = cfg.name
        orm.strategy_type = cfg.strategy_type.value
        orm.params = cfg.params
        orm.created_at = cfg.created_at
        self.session.flush()
        return StrategyConfig.model_validate(orm)

    def get_strategy_config(self, config_id: str) -> StrategyConfig | None:
        orm = self.session.get(StrategyConfigORM, config_id)
        return StrategyConfig.model_validate(orm) if orm else None

    # --- backtest runs ------------------------------------------------------

    def create_backtest_run(self, run: BacktestRun) -> BacktestRun:
        orm = BacktestRunORM(
            id=run.id,
            strategy_config_id=run.strategy_config_id,
            status=run.status.value,
            params=run.params,
            metrics=run.metrics,
            artifacts=self._dump_artifacts(run.artifacts),
            error=run.error,
            requested_at=run.requested_at,
            started_at=run.started_at,
            finished_at=run.finished_at,
        )
        self.session.add(orm)
        self.session.flush()
        return self._run_to_domain(orm)

    def update_backtest_run(self, run: BacktestRun) -> BacktestRun:
        orm = self.session.get(BacktestRunORM, run.id)
        if orm is None:
            raise KeyError(f"backtest run not found: {run.id}")
        orm.status = run.status.value
        orm.params = run.params
        orm.metrics = run.metrics
        orm.artifacts = self._dump_artifacts(run.artifacts)
        orm.error = run.error
        orm.started_at = run.started_at
        orm.finished_at = run.finished_at
        self.session.flush()
        return self._run_to_domain(orm)

    def get_backtest_run(self, run_id: str) -> BacktestRun | None:
        orm = self.session.get(BacktestRunORM, run_id)
        return self._run_to_domain(orm) if orm else None

    def list_backtest_runs(self, *, limit: int = 50, offset: int = 0) -> list[BacktestRun]:
        stmt = (
            select(BacktestRunORM)
            .order_by(BacktestRunORM.requested_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [self._run_to_domain(o) for o in self.session.scalars(stmt)]

    # --- audit (append-only) ------------------------------------------------

    def append_audit(self, event: AuditEvent) -> AuditEvent:
        orm = AuditEventORM(
            id=event.id,
            ts=event.ts,
            actor=event.actor,
            action=event.action,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            payload=event.payload,
            ip=event.ip,
        )
        self.session.add(orm)
        self.session.flush()
        return AuditEvent.model_validate(orm)

    def list_audit(self, *, limit: int = 100) -> list[AuditEvent]:
        stmt = select(AuditEventORM).order_by(AuditEventORM.ts.desc()).limit(limit)
        return [AuditEvent.model_validate(o) for o in self.session.scalars(stmt)]

    # --- instruments + point-in-time universe -------------------------------

    def upsert_instrument(self, instrument: Instrument) -> Instrument:
        orm = self.session.get(InstrumentORM, instrument.symbol)
        if orm is None:
            orm = InstrumentORM(symbol=instrument.symbol)
            self.session.add(orm)
        orm.exchange = instrument.exchange.value
        orm.name = instrument.name
        orm.sector = instrument.sector
        orm.has_liquid_ssf = instrument.has_liquid_ssf
        orm.lot_size = instrument.lot_size
        self.session.flush()
        return Instrument.model_validate(orm)

    def get_instrument(self, symbol: str) -> Instrument | None:
        orm = self.session.get(InstrumentORM, symbol)
        return Instrument.model_validate(orm) if orm else None

    def add_universe_membership(self, rows: list[UniverseMembership]) -> int:
        self.session.add_all(
            UniverseMembershipORM(
                id=r.id,
                index=r.index,
                symbol=r.symbol,
                effective_from=r.effective_from,
                effective_to=r.effective_to,
            )
            for r in rows
        )
        self.session.flush()
        return len(rows)

    def get_universe_membership(self, index: str, as_of: date) -> list[UniverseMembership]:
        """Members of `index` on `as_of`: interval [effective_from, effective_to)."""
        stmt = select(UniverseMembershipORM).where(
            UniverseMembershipORM.index == index,
            UniverseMembershipORM.effective_from <= as_of,
            or_(
                UniverseMembershipORM.effective_to.is_(None),
                UniverseMembershipORM.effective_to > as_of,
            ),
        )
        return [UniverseMembership.model_validate(o) for o in self.session.scalars(stmt)]

    # --- mapping helpers ----------------------------------------------------

    @staticmethod
    def _dump_artifacts(artifacts: list[ArtifactRef]) -> list[dict] | None:
        return [a.model_dump(mode="json") for a in artifacts] or None

    @staticmethod
    def _run_to_domain(orm: BacktestRunORM) -> BacktestRun:
        return BacktestRun(
            id=orm.id,
            strategy_config_id=orm.strategy_config_id,
            status=RunStatus(orm.status),
            params=orm.params or {},
            metrics=orm.metrics,
            artifacts=[ArtifactRef.model_validate(a) for a in (orm.artifacts or [])],
            error=orm.error,
            requested_at=orm.requested_at,
            started_at=orm.started_at,
            finished_at=orm.finished_at,
        )
