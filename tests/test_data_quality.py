from __future__ import annotations

from datetime import date

import pandas as pd

from quant_pilot.engine.data.corporate_actions import verify_adjustments
from quant_pilot.engine.data.quality import check_quality


def _frame(closes, volumes=None, adj=None, start="2020-01-01"):
    idx = pd.date_range(start, periods=len(closes), freq="B")
    n = len(closes)
    return pd.DataFrame(
        {
            "close": closes,
            "volume": volumes if volumes is not None else [1_000_000] * n,
            "adj_close": adj if adj is not None else closes,
        },
        index=idx,
    )


# --- quality ----------------------------------------------------------------


def test_clean_series_passes():
    report = check_quality(_frame([100, 101, 102, 103, 104]))
    assert report.ok
    assert report.n_rows == 5


def test_detects_missing_sessions():
    df = _frame([100, 101, 102])
    expected = {pd.Timestamp(ts).date() for ts in pd.date_range("2020-01-01", periods=5, freq="B")}
    report = check_quality(df, expected_sessions=expected)
    assert not report.ok
    assert len(report.missing_sessions) == 2


def test_detects_stale_run_and_nonpositive():
    report = check_quality(_frame([50, 50, 50, 50, 50, 51]), stale_limit=5)
    assert report.stale_runs and report.stale_runs[0][1] == 5
    bad = check_quality(_frame([100, 0, 102]))
    assert date(2020, 1, 2) in bad.nonpositive
    assert not bad.ok


def test_detects_volume_spike():
    report = check_quality(_frame([100, 101, 102, 103], volumes=[1_000, 1_000, 1_000, 100_000]))
    assert len(report.volume_spikes) == 1


# --- corporate actions ------------------------------------------------------


def test_clean_adjustment_passes():
    # smoothly rising adjusted series, with a known split date that is continuous in adj_close
    adj = [100, 101, 102, 103, 104, 105]
    report = verify_adjustments(_frame(adj, adj=adj), known_actions=[date(2020, 1, 3)])
    assert report.ok


def test_unexplained_jump_flagged():
    # adj_close halves overnight with no recorded action -> bad bonus/split adjustment
    adj = [100, 101, 102, 51, 52, 53]
    report = verify_adjustments(_frame(adj, adj=adj))
    assert not report.ok
    assert report.unexplained_jumps


def test_jump_on_known_date_is_bad_adjustment():
    adj = [100, 101, 102, 51, 52, 53]
    # the jump sits on the known action date -> adjustment failed to apply
    jump_day = pd.date_range("2020-01-01", periods=6, freq="B")[3].date()
    report = verify_adjustments(_frame(adj, adj=adj), known_actions=[jump_day])
    assert not report.ok
    assert report.bad_adjustments
