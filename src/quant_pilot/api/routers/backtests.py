"""Backtest endpoints: submit (async, 202), list, fetch."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from quant_pilot.api.deps import get_job_queue, get_repository
from quant_pilot.api.schemas.backtests import BacktestCreate, BacktestSubmitOut
from quant_pilot.domain import ports
from quant_pilot.domain.models import BacktestRun, RunStatus, StrategyConfig

router = APIRouter(prefix="/backtests", tags=["backtests"])

_RUN_TASK = "quant_pilot.workers.tasks.run_backtest"


@router.post("", status_code=202, response_model=BacktestSubmitOut)
def submit_backtest(
    body: BacktestCreate,
    repo: ports.Repository = Depends(get_repository),
    queue: ports.JobQueue = Depends(get_job_queue),
) -> BacktestSubmitOut:
    cfg = StrategyConfig(
        name=f"{body.strategy.value}-run", strategy_type=body.strategy, params=body.params
    )
    repo.save_strategy_config(cfg)
    run = repo.create_backtest_run(
        BacktestRun(strategy_config_id=cfg.id, status=RunStatus.QUEUED, params=body.params)
    )
    job_id = queue.enqueue(_RUN_TASK, run.id)
    return BacktestSubmitOut(run_id=run.id, job_id=job_id, status=run.status)


@router.get("", response_model=list[BacktestRun])
def list_backtests(
    limit: int = 50, offset: int = 0, repo: ports.Repository = Depends(get_repository)
) -> list[BacktestRun]:
    return repo.list_backtest_runs(limit=limit, offset=offset)


@router.get("/{run_id}", response_model=BacktestRun)
def get_backtest(run_id: str, repo: ports.Repository = Depends(get_repository)) -> BacktestRun:
    run = repo.get_backtest_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="backtest run not found")
    return run
