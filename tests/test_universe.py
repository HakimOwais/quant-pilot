from __future__ import annotations

from datetime import date

from quant_pilot.adapters.persistence.repository import SqlAlchemyRepository
from quant_pilot.engine.data.universe import (
    MembershipEvent,
    build_membership_intervals,
    parse_membership_events,
    read_membership_csv,
)


def _ev(symbol: str, action: str, d: str) -> MembershipEvent:
    return MembershipEvent(
        index="NIFTY50", symbol=symbol, action=action, date=date.fromisoformat(d)
    )


def test_open_interval_for_current_member():
    rows = build_membership_intervals([_ev("TCS.NS", "add", "2015-01-01")])
    assert len(rows) == 1
    assert rows[0].effective_from == date(2015, 1, 1)
    assert rows[0].effective_to is None


def test_add_then_drop_closes_interval():
    rows = build_membership_intervals(
        [_ev("YESBANK.NS", "add", "2015-01-01"), _ev("YESBANK.NS", "drop", "2020-03-19")]
    )
    assert len(rows) == 1
    assert rows[0].effective_to == date(2020, 3, 19)


def test_readd_creates_two_intervals():
    rows = build_membership_intervals(
        [
            _ev("X.NS", "add", "2015-01-01"),
            _ev("X.NS", "drop", "2018-01-01"),
            _ev("X.NS", "add", "2020-01-01"),
        ]
    )
    assert len(rows) == 2
    assert rows[0].effective_to == date(2018, 1, 1)
    assert rows[1].effective_from == date(2020, 1, 1)
    assert rows[1].effective_to is None


def test_events_unsorted_are_handled():
    rows = build_membership_intervals(
        [_ev("Y.NS", "drop", "2020-01-01"), _ev("Y.NS", "add", "2015-01-01")]
    )
    assert len(rows) == 1
    assert (rows[0].effective_from, rows[0].effective_to) == (date(2015, 1, 1), date(2020, 1, 1))


def test_parse_from_dicts():
    events = parse_membership_events(
        [{"index": "NIFTY50", "symbol": " tcs.ns ", "action": "ADD", "date": "2015-01-01"}]
    )
    assert events[0].symbol == "tcs.ns"
    assert events[0].action == "add"


def test_csv_to_repository_roundtrip(tmp_path, session):
    csv_path = tmp_path / "membership.csv"
    csv_path.write_text(
        "index,symbol,action,date\n"
        "NIFTY50,YESBANK.NS,add,2015-01-01\n"
        "NIFTY50,YESBANK.NS,drop,2020-03-19\n"
        "NIFTY50,TCS.NS,add,2015-01-01\n"
    )
    intervals = build_membership_intervals(read_membership_csv(csv_path))
    repo = SqlAlchemyRepository(session)
    repo.add_universe_membership(intervals)

    on_2018 = {m.symbol for m in repo.get_universe_membership("NIFTY50", date(2018, 6, 1))}
    on_2022 = {m.symbol for m in repo.get_universe_membership("NIFTY50", date(2022, 6, 1))}
    assert on_2018 == {"YESBANK.NS", "TCS.NS"}  # survivorship-correct: YESBANK present in 2018
    assert on_2022 == {"TCS.NS"}  # ...and gone by 2022
