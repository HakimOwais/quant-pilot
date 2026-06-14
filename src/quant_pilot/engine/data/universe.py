"""Point-in-time universe reconstruction (MASTER_PROMPT NON-NEGOTIABLE #1).

Free historical index membership does not exist as a ready table; it must be rebuilt from
NSE index-revision events (add/drop with a date). This module is pure: it turns a stream of
membership *events* into membership *intervals* that the repository persists. A backtest on
date D then sees exactly the names that were in the index on D — including names later
dropped/delisted — eliminating survivorship bias.

Input event format (CSV columns or dict keys): index, symbol, action, date
  action ∈ {add, drop};  date = YYYY-MM-DD
"""

from __future__ import annotations

import csv
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from quant_pilot.domain.models import UniverseMembership

Action = Literal["add", "drop"]


class MembershipEvent(BaseModel):
    index: str
    symbol: str
    action: Action
    date: date


def _parse_date(value: object) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()


def parse_membership_events(
    rows: Iterable[Sequence[str] | dict[str, str]],
) -> list[MembershipEvent]:
    """Parse rows (dicts with named keys, or 4-tuples) into validated events."""
    events: list[MembershipEvent] = []
    for row in rows:
        if isinstance(row, dict):
            index, symbol, action, when = (
                row["index"],
                row["symbol"],
                row["action"],
                row["date"],
            )
        else:
            index, symbol, action, when = row
        events.append(
            MembershipEvent(
                index=index.strip(),
                symbol=symbol.strip(),
                action=action.strip().lower(),  # type: ignore[arg-type]
                date=_parse_date(when),
            )
        )
    return events


def read_membership_csv(path: str | Path) -> list[MembershipEvent]:
    with Path(path).open(newline="") as fh:
        return parse_membership_events(list(csv.DictReader(fh)))


def build_membership_intervals(events: Iterable[MembershipEvent]) -> list[UniverseMembership]:
    """Collapse add/drop events per (index, symbol) into [from, to) intervals.

    - add opens an interval; drop closes it (effective_to = drop date, exclusive).
    - a name still in the index has effective_to = None.
    - re-additions after a drop create a second interval.
    - duplicate adds / dangling drops are ignored defensively.
    """
    by_key: dict[tuple[str, str], list[MembershipEvent]] = defaultdict(list)
    for event in events:
        by_key[(event.index, event.symbol)].append(event)

    intervals: list[UniverseMembership] = []
    for (index, symbol), evs in by_key.items():
        evs.sort(key=lambda e: e.date)
        open_from: date | None = None
        for event in evs:
            if event.action == "add":
                if open_from is None:
                    open_from = event.date
            elif event.action == "drop" and open_from is not None:
                intervals.append(
                    UniverseMembership(
                        index=index,
                        symbol=symbol,
                        effective_from=open_from,
                        effective_to=event.date,
                    )
                )
                open_from = None
        if open_from is not None:
            intervals.append(
                UniverseMembership(index=index, symbol=symbol, effective_from=open_from)
            )
    return intervals
