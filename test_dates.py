# tests/test_dates.py
from nifty_oc.dates import parse_nse_expiry, select_expiries


def test_parse_nse_expiry_converts_to_iso():
    assert parse_nse_expiry("31-Jul-2026") == "2026-07-31"
    assert parse_nse_expiry("07-Aug-2026") == "2026-08-07"


def test_select_expiries_returns_first_n_as_iso():
    raw = ["31-Jul-2026", "07-Aug-2026", "14-Aug-2026", "28-Aug-2026"]
    assert select_expiries(raw, 3) == ["2026-07-31", "2026-08-07", "2026-08-14"]


def test_select_expiries_clamps_when_fewer_available():
    raw = ["31-Jul-2026", "07-Aug-2026"]
    assert select_expiries(raw, 3) == ["2026-07-31", "2026-08-07"]
