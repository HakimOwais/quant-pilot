"""Clock adapters. SystemClock for production; FixedClock for deterministic tests/backtests."""

from __future__ import annotations

from datetime import UTC, date, datetime


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def today(self) -> date:
        return datetime.now(UTC).date()


class FixedClock:
    """A clock pinned to a fixed instant (no look-ahead in tests)."""

    def __init__(self, instant: datetime) -> None:
        self._instant = instant

    def now(self) -> datetime:
        return self._instant

    def today(self) -> date:
        return self._instant.date()
