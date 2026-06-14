"""Universe endpoint: point-in-time index membership as of a date."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends

from quant_pilot.api.deps import get_repository
from quant_pilot.domain import ports
from quant_pilot.domain.models import UniverseMembership

router = APIRouter(prefix="/universes", tags=["universe"])


@router.get("/{index}/members", response_model=list[UniverseMembership])
def universe_members(
    index: str,
    as_of: date | None = None,
    repo: ports.Repository = Depends(get_repository),
) -> list[UniverseMembership]:
    return repo.get_universe_membership(index, as_of or date.today())
