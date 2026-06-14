"""Broker reconciliation (SYSTEM_DESIGN §8.7): broker positions must equal the internal book.

A mismatch means the system's view of the world is wrong — halt and investigate before trading.
"""

from __future__ import annotations

from pydantic import BaseModel

from quant_pilot.domain.models import Position


class PositionMismatch(BaseModel):
    symbol: str
    broker_qty: int
    book_qty: int


class ReconciliationReport(BaseModel):
    ok: bool
    mismatches: list[PositionMismatch]


def reconcile_positions(
    broker_positions: list[Position], book: dict[str, int], tolerance: int = 0
) -> ReconciliationReport:
    broker = {p.symbol: p.quantity for p in broker_positions}
    mismatches = [
        PositionMismatch(symbol=sym, broker_qty=broker.get(sym, 0), book_qty=book.get(sym, 0))
        for sym in set(broker) | set(book)
        if abs(broker.get(sym, 0) - book.get(sym, 0)) > tolerance
    ]
    return ReconciliationReport(
        ok=not mismatches, mismatches=sorted(mismatches, key=lambda m: m.symbol)
    )
