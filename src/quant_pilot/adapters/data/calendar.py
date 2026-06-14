"""NSE trading calendar (for gap detection in data-quality checks).

Wraps pandas_market_calendars so the engine's quality check can be given the exact set of
expected trading sessions. Imported lazily; not exercised in unit tests (no network).
"""

from __future__ import annotations

from datetime import date


def nse_sessions(start: date, end: date) -> list[date]:
    import pandas_market_calendars as mcal

    calendar = mcal.get_calendar("NSE")
    schedule = calendar.schedule(start_date=start, end_date=end)
    return [ts.date() for ts in schedule.index]
