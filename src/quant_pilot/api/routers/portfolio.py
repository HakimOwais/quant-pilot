"""Portfolio endpoints: live positions and margin from the broker (trading-gated)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from quant_pilot.api.deps import get_broker
from quant_pilot.api.security.auth import require_trading_enabled
from quant_pilot.domain import ports
from quant_pilot.domain.models import MarginInfo, Position

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get(
    "/positions", response_model=list[Position], dependencies=[Depends(require_trading_enabled)]
)
def positions(broker: ports.Broker = Depends(get_broker)) -> list[Position]:
    return broker.get_positions()


@router.get("/margin", response_model=MarginInfo, dependencies=[Depends(require_trading_enabled)])
def margin(broker: ports.Broker = Depends(get_broker)) -> MarginInfo:
    return broker.get_margin()
