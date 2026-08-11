from nifty_oc.signals import detect_brewing
from nifty_oc.config import SURGE_WINDOWS

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


def test_ce_unwind_above_spot_is_bullish():
    # CE OI falling 8M->5M above spot: resistance melting -> BULLISH, UNWIND.
    tl = three_snaps(ce_series=[8_000_000, 6_500_000, 5_000_000],
                     pe_series=[1] * 3, strike=25000)
    sigs = detect_brewing(tl, spot=24500, pct_threshold=PCT, abs_threshold=ABS, windows=WINDOWS)
    assert len(sigs) == 1
    s = sigs[0]
    assert s["leg"] == "CE"
    assert s["kind"] == "UNWIND"
    assert s["direction"] == "BULLISH"
    assert s["confidence"] == "HIGH"       # textbook: CE above spot
    assert s["abs_30min"] == -3_000_000
    assert s["pct_30min"] == -0.375


def test_pe_unwind_below_spot_is_bearish():
    # PE OI falling below spot: support melting -> BEARISH, UNWIND.
    tl = three_snaps(ce_series=[1] * 3,
                     pe_series=[8_000_000, 6_500_000, 5_000_000], strike=24000)
    sigs = detect_brewing(tl, spot=24500, pct_threshold=PCT, abs_threshold=ABS, windows=WINDOWS)
    assert len(sigs) == 1
    assert sigs[0]["kind"] == "UNWIND"
    assert sigs[0]["direction"] == "BEARISH"


def test_decrease_clears_pct_but_not_abs_not_flagged():
    # 1M -> 0.6M: -40% (clears pct) but -400K (< 500K abs) -> not flagged.
    tl = three_snaps(ce_series=[1] * 3,
                     pe_series=[1_000_000, 800_000, 600_000], strike=24000)
    sigs = detect_brewing(tl, spot=24500, pct_threshold=PCT, abs_threshold=ABS, windows=WINDOWS)
    assert sigs == []


def test_decrease_clears_abs_but_not_pct_not_flagged():
    # 10M -> 9.4M: -600K (clears abs) but -6% (< 30% pct) -> not flagged.
    tl = three_snaps(ce_series=[1] * 3,
                     pe_series=[10_000_000, 9_700_000, 9_400_000], strike=24000)
    sigs = detect_brewing(tl, spot=24500, pct_threshold=PCT, abs_threshold=ABS, windows=WINDOWS)
    assert sigs == []


def test_build_tags_kind_build():
    tl = five_snaps(ce_series=[1_000_000] * 5,
                    pe_series=[6_000_000, 7_000_000, 8_000_000, 10_000_000, 13_000_000])
    sigs = detect_brewing(tl, spot=24500, pct_threshold=PCT, abs_threshold=ABS, windows=WINDOWS)
    assert sigs[0]["kind"] == "BUILD"


def test_ce_unwind_pe_build_same_strike_not_pinned():
    # CE melting (bullish) + PE building (bullish) at one strike -> two bullish
    # cards, NOT a pin (pin is reserved for both-sides writing).
    tl = [
        snap("t0", [r(24500, 8_000_000, 6_000_000)]),
        snap("t1", [r(24500, 6_500_000, 9_000_000)]),
        snap("t2", [r(24500, 5_000_000, 13_000_000)]),
    ]
    sigs = detect_brewing(tl, spot=24500, pct_threshold=PCT, abs_threshold=ABS, windows=WINDOWS)
    assert len(sigs) == 2
    assert all(s["direction"] == "BULLISH" for s in sigs)
    assert {s["leg"] for s in sigs} == {"CE", "PE"}


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


# --- Multi-hour brewing windows (30min/1hr/2hr/3hr/4hr/5hr, per-day) ---

def pe_snaps(pe_series, strike=24000, ce_value=1):
    """Build one snapshot per PE OI value, holding CE flat. Index i == snapshot i."""
    return [snap(f"t{i}", [r(strike, ce_value, pe_series[i])]) for i in range(len(pe_series))]


def test_config_has_multi_hour_surge_windows():
    # The single production change: 30min/1hr/2hr/3hr/4hr/5hr at 15-min cadence.
    assert SURGE_WINDOWS == {
        "30min": 2, "1hr": 4, "2hr": 8, "3hr": 12, "4hr": 16, "5hr": 20,
    }


def test_five_hour_build_flags_when_recent_windows_flat():
    # PE built 6M -> 13M over 20 snapshots (5hr) but has been flat 13M for the
    # last several. Only the 5hr window should flag; 30min must not.
    pe = [6_000_000, 8_000_000, 10_000_000, 12_000_000] + [13_000_000] * 17
    #     idx0(5hr)                                         idx4..idx20 all 13M
    tl = pe_snaps(pe, strike=24000)          # 21 snapshots, now == idx20 == 13M
    sigs = detect_brewing(tl, spot=24500, pct_threshold=PCT, abs_threshold=ABS,
                          windows=SURGE_WINDOWS)
    assert len(sigs) == 1
    s = sigs[0]
    assert s["leg"] == "PE"
    assert s["direction"] == "BULLISH"
    assert s["windows"] == ["5hr"]
    assert "30min" not in s["windows"]
    assert s["oi_past_5hr"] == 6_000_000


def test_two_hour_build_flags_two_hour_window():
    # Monotonic PE 6M..14M over 9 snapshots; the 2hr window (8 back) must flag.
    pe = [6_000_000, 7_000_000, 8_000_000, 9_000_000, 10_000_000,
          11_000_000, 12_000_000, 13_000_000, 14_000_000]
    tl = pe_snaps(pe, strike=24000)          # 9 snapshots, now == idx8 == 14M
    sigs = detect_brewing(tl, spot=24500, pct_threshold=PCT, abs_threshold=ABS,
                          windows=SURGE_WINDOWS)
    assert len(sigs) == 1
    assert "2hr" in sigs[0]["windows"]


def test_insufficient_history_leaves_long_windows_inert():
    # 10 snapshots: 2hr (8 back) has a baseline; 3hr/4hr/5hr do not.
    pe = [6_000_000, 7_000_000, 8_000_000, 9_000_000, 10_000_000,
          11_000_000, 12_000_000, 13_000_000, 14_000_000, 15_000_000]
    tl = pe_snaps(pe, strike=24000)          # 10 snapshots, now == idx9 == 15M
    sigs = detect_brewing(tl, spot=24500, pct_threshold=PCT, abs_threshold=ABS,
                          windows=SURGE_WINDOWS)
    assert len(sigs) == 1
    windows = sigs[0]["windows"]
    assert "2hr" in windows                              # available and firing
    assert not any(w in windows for w in ("3hr", "4hr", "5hr"))  # no lookback


def test_full_day_all_windows_fire_within_bounds():
    # A full day of monotonic growth. Every window fires and the deepest (5hr,
    # 20 back) stays within a 21-snapshot per-day timeline — no out-of-range read.
    pe = [
        6_000_000,  6_500_000,  7_000_000,  7_500_000,  8_000_000,   # idx0..4
        8_500_000,  9_000_000,  9_500_000, 10_000_000, 10_500_000,   # idx5..9
        11_000_000, 11_500_000, 12_000_000, 12_500_000, 13_000_000,  # idx10..14
        13_500_000, 14_000_000, 14_500_000, 15_000_000, 17_500_000,  # idx15..19
        20_000_000,                                                   # idx20 (now)
    ]
    tl = pe_snaps(pe, strike=24000)
    sigs = detect_brewing(tl, spot=24500, pct_threshold=PCT, abs_threshold=ABS,
                          windows=SURGE_WINDOWS)
    assert len(sigs) == 1
    assert set(sigs[0]["windows"]) == {"30min", "1hr", "2hr", "3hr", "4hr", "5hr"}
    assert sigs[0]["confidence"] == "HIGH"
    assert all(w in SURGE_WINDOWS for w in sigs[0]["windows"])
