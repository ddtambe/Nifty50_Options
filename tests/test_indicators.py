import pytest

from nifty_oc.indicators import (
    classify_buildup, pcr, max_pain, support, resistance,
    zone_200, verdict, display_strikes,
)


def leg(oi, chg_oi, ltp):
    return {"oi": oi, "chg_oi": chg_oi, "ltp": ltp, "iv": 12.0, "volume": 100}


def row(strike, ce_oi, ce_chg, ce_ltp, pe_oi, pe_chg, pe_ltp):
    return {"strike": strike, "ce": leg(ce_oi, ce_chg, ce_ltp),
            "pe": leg(pe_oi, pe_chg, pe_ltp)}


def test_classify_buildup_four_quadrants():
    assert classify_buildup(1.0, 100) == "Long Buildup"      # price up, OI up
    assert classify_buildup(-1.0, 100) == "Short Buildup"    # price down, OI up
    assert classify_buildup(1.0, -100) == "Short Covering"   # price up, OI down
    assert classify_buildup(-1.0, -100) == "Long Unwinding"  # price down, OI down


def test_classify_buildup_flat_is_na():
    assert classify_buildup(0.0, 0) == "N/A"


def test_pcr_basic():
    rows = [row(24800, 100, 0, 10, 150, 0, 10),
            row(24900, 100, 0, 10, 50, 0, 10)]
    # PE total 200 / CE total 200 = 1.0
    assert pcr(rows) == 1.0


def test_pcr_zero_ce_returns_zero():
    rows = [row(24800, 0, 0, 10, 150, 0, 10)]
    assert pcr(rows) == 0.0


def test_max_pain_picks_min_payout_strike():
    # Heavy OI concentrated so pain sits at 24800.
    rows = [
        row(24700, 10, 0, 0, 500, 0, 0),
        row(24800, 300, 0, 0, 300, 0, 0),
        row(24900, 500, 0, 0, 10, 0, 0),
    ]
    assert max_pain(rows) == 24800


def test_support_is_highest_pe_oi_strike():
    rows = [row(24700, 100, 0, 0, 900, 0, 0),
            row(24800, 100, 0, 0, 200, 0, 0)]
    assert support(rows) == 24700


def test_resistance_is_highest_ce_oi_strike():
    rows = [row(25000, 900, 0, 0, 100, 0, 0),
            row(24800, 200, 0, 0, 100, 0, 0)]
    assert resistance(rows) == 25000


def test_zone_200():
    assert zone_200(24800) == "24800-25000"
    assert zone_200(24900) == "24800-25000"
    assert zone_200(25000) == "25000-25200"


def test_verdict_bullish_when_pcr_high():
    rows = [row(24800, 100, 0, 0, 300, 0, 0)]
    assert verdict(1.4, rows, 24800) == "Leaning Bullish"


def test_verdict_bearish_when_pcr_low():
    rows = [row(24800, 300, 0, 0, 100, 0, 0)]
    assert verdict(0.6, rows, 24800) == "Leaning Bearish"


def test_verdict_rangebound_when_pcr_neutral():
    rows = [row(24800, 100, 0, 0, 100, 0, 0)]
    assert verdict(1.0, rows, 24800) == "Rangebound"


def test_display_strikes_keeps_only_step_multiples():
    rows = [row(24800, 1, 0, 0, 1, 0, 0),
            row(24850, 1, 0, 0, 1, 0, 0),
            row(25000, 1, 0, 0, 1, 0, 0)]
    kept = [r["strike"] for r in display_strikes(rows, 200)]
    assert kept == [24800, 25000]


def test_classify_buildup_na_when_oi_flat_regardless_of_price():
    # No OI change → no buildup signal, even if price moved.
    assert classify_buildup(5.0, 0) == "N/A"
    assert classify_buildup(-5.0, 0) == "N/A"


def test_max_pain_empty_rows_raises():
    with pytest.raises(ValueError):
        max_pain([])


def test_support_empty_rows_raises():
    with pytest.raises(ValueError):
        support([])


def test_resistance_empty_rows_raises():
    with pytest.raises(ValueError):
        resistance([])
