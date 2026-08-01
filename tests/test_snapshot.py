import json
from pathlib import Path
from nifty_oc.snapshot import build_snapshot, ltp_index, trade_date_of

PAYLOAD = json.loads((Path(__file__).parent / "fixtures" / "sample_chain.json").read_text())


def test_trade_date_of():
    assert trade_date_of("2026-07-29 09:30") == "2026-07-29"


def test_build_snapshot_shape_and_values():
    snap = build_snapshot(PAYLOAD, "2026-07-29 09:30", prev_ltp={})
    assert snap["spot"] == 24812.35
    assert snap["atm"] == 24800
    assert snap["trade_date"] == "2026-07-29"
    # 3 expiries requested; fixture has 07-Aug data too.
    expiries = [e["expiry"] for e in snap["expiries"]]
    assert expiries[:2] == ["2026-07-31", "2026-08-07"]


def test_build_snapshot_first_cycle_buildup_is_na():
    snap = build_snapshot(PAYLOAD, "2026-07-29 09:30", prev_ltp={})
    first = snap["expiries"][0]
    for dr in first["display_rows"]:
        assert dr["ce_buildup"] == "N/A"
        assert dr["pe_buildup"] == "N/A"


def test_build_snapshot_uses_prev_ltp_for_buildup():
    # Prime prev LTP lower than current for CE 24800 (74.2), OI change +22400 → Long Buildup.
    prev = {("2026-07-31", 24800, "CE"): 70.0}
    snap = build_snapshot(PAYLOAD, "2026-07-29 09:45", prev_ltp=prev)
    row = next(r for r in snap["expiries"][0]["display_rows"] if r["strike"] == 24800)
    assert row["ce_buildup"] == "Long Buildup"


def test_ltp_index_roundtrip():
    snap = build_snapshot(PAYLOAD, "2026-07-29 09:30", prev_ltp={})
    idx = ltp_index(snap)
    assert idx[("2026-07-31", 24800, "CE")] == 74.2
    assert idx[("2026-07-31", 24800, "PE")] == 78.9


def test_display_rows_are_200_step_only():
    snap = build_snapshot(PAYLOAD, "2026-07-29 09:30", prev_ltp={})
    strikes = [r["strike"] for r in snap["expiries"][0]["display_rows"]]
    # 24900 is not a 200-multiple → excluded from display; 24800 kept.
    assert 24800 in strikes
    assert 24900 not in strikes
