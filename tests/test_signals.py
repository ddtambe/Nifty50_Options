from nifty_oc.signals import detect_brewing

WINDOWS = {"30min": 2, "1hr": 4}
PCT = 0.30
ABS = 500_000


def r(strike, ce, pe):
    return {"strike": strike, "ce_oi": ce, "pe_oi": pe}


def snap(t, rows):
    return {"t": t, "rows": rows}


def five_snaps(ce_series, pe_series, strike=24500):
    """Build 5 snapshots for one strike from per-snapshot CE/PE OI series."""
    return [snap(f"t{i}", [r(strike, ce_series[i], pe_series[i])]) for i in range(5)]


def three_snaps(ce_series, pe_series, strike=24500):
    return [snap(f"t{i}", [r(strike, ce_series[i], pe_series[i])]) for i in range(3)]


def test_pe_surge_both_windows_is_bullish_high():
    # PE rises 6M (1hr base, idx0) -> 8M (30min base, idx2) -> 13M (now, idx4)
    tl = five_snaps(
        ce_series=[1_000_000] * 5,
        pe_series=[6_000_000, 7_000_000, 8_000_000, 10_000_000, 13_000_000],
    )
    sigs = detect_brewing(tl, spot=24500, pct_threshold=PCT, abs_threshold=ABS, windows=WINDOWS)
    assert len(sigs) == 1
    s = sigs[0]
    assert s["leg"] == "PE"
    assert s["direction"] == "BULLISH"
    assert s["confidence"] == "HIGH"          # flagged on both windows
    assert s["windows"] == ["30min", "1hr"]
    assert s["oi_now"] == 13_000_000
    assert s["oi_past_30min"] == 8_000_000
    assert s["oi_past_1hr"] == 6_000_000
    assert s["pct_1hr"] == 1.1667
    assert s["abs_30min"] == 5_000_000


def test_ce_surge_is_bearish():
    tl = five_snaps(
        ce_series=[6_000_000, 7_000_000, 8_000_000, 10_000_000, 13_000_000],
        pe_series=[1_000_000] * 5,
    )
    sigs = detect_brewing(tl, spot=24500, pct_threshold=PCT, abs_threshold=ABS, windows=WINDOWS)
    assert len(sigs) == 1
    assert sigs[0]["leg"] == "CE"
    assert sigs[0]["direction"] == "BEARISH"


def test_both_legs_surge_merges_to_pin():
    tl = five_snaps(
        ce_series=[6_000_000, 7_000_000, 8_000_000, 10_000_000, 13_000_000],
        pe_series=[6_000_000, 7_000_000, 8_000_000, 10_000_000, 13_000_000],
    )
    sigs = detect_brewing(tl, spot=24500, pct_threshold=PCT, abs_threshold=ABS, windows=WINDOWS)
    assert len(sigs) == 1
    s = sigs[0]
    assert s["leg"] == "BOTH"
    assert s["direction"] == "PIN"
    assert s["ce_oi_now"] == 13_000_000
    assert s["pe_oi_now"] == 13_000_000
    assert s["ce_pct_1hr"] == 1.1667
    assert s["pe_abs_30min"] == 5_000_000


def test_clears_abs_but_not_pct_not_flagged():
    # 30min only (3 snaps). 10M -> 10.6M: delta 600K (>=ABS) but pct 6% (<PCT).
    tl = three_snaps(ce_series=[1] * 3,
                     pe_series=[10_000_000, 10_300_000, 10_600_000])
    sigs = detect_brewing(tl, spot=24500, pct_threshold=PCT, abs_threshold=ABS, windows=WINDOWS)
    assert sigs == []


def test_clears_pct_but_not_abs_not_flagged():
    # 1M -> 1.4M: pct 40% (>=PCT) but delta 400K (<ABS).
    tl = three_snaps(ce_series=[1] * 3,
                     pe_series=[1_000_000, 1_200_000, 1_400_000])
    sigs = detect_brewing(tl, spot=24500, pct_threshold=PCT, abs_threshold=ABS, windows=WINDOWS)
    assert sigs == []


def test_single_window_wrong_side_is_medium():
    # PE surge but strike ABOVE spot (not textbook) + single window -> MEDIUM.
    tl = three_snaps(ce_series=[1] * 3,
                     pe_series=[6_000_000, 8_000_000, 13_000_000],
                     strike=25000)
    sigs = detect_brewing(tl, spot=24500, pct_threshold=PCT, abs_threshold=ABS, windows=WINDOWS)
    assert len(sigs) == 1
    assert sigs[0]["confidence"] == "MEDIUM"
    assert sigs[0]["windows"] == ["30min"]
    assert sigs[0]["side_of_spot"] == "above"


def test_single_window_textbook_side_is_high():
    # PE surge below spot -> textbook support -> HIGH even on one window.
    tl = three_snaps(ce_series=[1] * 3,
                     pe_series=[6_000_000, 8_000_000, 13_000_000],
                     strike=24000)
    sigs = detect_brewing(tl, spot=24500, pct_threshold=PCT, abs_threshold=ABS, windows=WINDOWS)
    assert len(sigs) == 1
    assert sigs[0]["confidence"] == "HIGH"
    assert sigs[0]["side_of_spot"] == "below"


def test_zero_past_oi_skipped_no_crash():
    tl = three_snaps(ce_series=[1] * 3, pe_series=[0, 500_000, 1_000_000])
    sigs = detect_brewing(tl, spot=24500, pct_threshold=PCT, abs_threshold=ABS, windows=WINDOWS)
    assert sigs == []


def test_too_few_snapshots_returns_empty():
    assert detect_brewing([], 24500, PCT, ABS, WINDOWS) == []
    one = [snap("t0", [r(24500, 1_000_000, 1_000_000)])]
    assert detect_brewing(one, 24500, PCT, ABS, WINDOWS) == []


def test_only_30min_history_available():
    # 3 snapshots: 30min window has a baseline, 1hr does not.
    tl = three_snaps(ce_series=[1] * 3,
                     pe_series=[6_000_000, 8_000_000, 13_000_000],
                     strike=24000)
    sigs = detect_brewing(tl, spot=24500, pct_threshold=PCT, abs_threshold=ABS, windows=WINDOWS)
    assert len(sigs) == 1
    assert sigs[0]["windows"] == ["30min"]      # 1hr contributes nothing
    assert "oi_past_1hr" not in sigs[0]


def test_ordering_high_before_medium_then_by_abs():
    # Strike A (24000, PE below spot): single window -> HIGH.
    # Strike B (25000, PE above spot): single window -> MEDIUM.
    tl = [
        snap("t0", [r(24000, 1, 6_000_000), r(25000, 1, 6_000_000)]),
        snap("t1", [r(24000, 1, 8_000_000), r(25000, 1, 8_000_000)]),
        snap("t2", [r(24000, 1, 13_000_000), r(25000, 1, 13_000_000)]),
    ]
    sigs = detect_brewing(tl, spot=24500, pct_threshold=PCT, abs_threshold=ABS, windows=WINDOWS)
    assert [s["confidence"] for s in sigs] == ["HIGH", "MEDIUM"]
    assert sigs[0]["strike"] == 24000
