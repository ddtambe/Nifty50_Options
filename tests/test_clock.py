import os
from datetime import datetime
from unittest.mock import patch
from nifty_oc.clock import is_market_hours

# 2026-07-29 is a Wednesday (a trading day) — used by the time-window tests.


def test_inside_market_hours():
    assert is_market_hours(datetime(2026, 7, 29, 10, 0)) is True
    assert is_market_hours(datetime(2026, 7, 29, 9, 15)) is True
    assert is_market_hours(datetime(2026, 7, 29, 15, 30)) is True


def test_outside_market_hours():
    assert is_market_hours(datetime(2026, 7, 29, 9, 0)) is False
    assert is_market_hours(datetime(2026, 7, 29, 15, 31)) is False
    assert is_market_hours(datetime(2026, 7, 29, 18, 0)) is False


def test_weekend_is_not_market_hours():
    # 2026-08-08 is a Saturday, 2026-08-09 a Sunday — closed even inside
    # the 09:15-15:30 time window.
    assert is_market_hours(datetime(2026, 8, 8, 11, 0)) is False   # Sat
    assert is_market_hours(datetime(2026, 8, 9, 11, 0)) is False   # Sun


def test_weekday_inside_window_is_market_hours():
    # 2026-08-07 is a Friday.
    assert is_market_hours(datetime(2026, 8, 7, 11, 0)) is True


def test_force_fetch_bypasses_weekend_guard():
    with patch.dict(os.environ, {"FORCE_FETCH": "true"}):
        assert is_market_hours(datetime(2026, 8, 8, 11, 0)) is True   # Sat
