from datetime import datetime
from nifty_oc.clock import is_market_hours


def test_inside_market_hours():
    assert is_market_hours(datetime(2026, 7, 29, 10, 0)) is True
    assert is_market_hours(datetime(2026, 7, 29, 9, 15)) is True
    assert is_market_hours(datetime(2026, 7, 29, 15, 30)) is True


def test_outside_market_hours():
    assert is_market_hours(datetime(2026, 7, 29, 9, 0)) is False
    assert is_market_hours(datetime(2026, 7, 29, 15, 31)) is False
    assert is_market_hours(datetime(2026, 7, 29, 18, 0)) is False
