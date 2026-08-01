import json
from pathlib import Path
from nifty_oc.parse import (
    extract_spot, extract_expiries, rows_for_expiry, nearest_atm,
)

PAYLOAD = json.loads((Path(__file__).parent / "fixtures" / "sample_chain.json").read_text())


def test_extract_spot():
    assert extract_spot(PAYLOAD) == 24812.35


def test_extract_expiries_first_three():
    assert extract_expiries(PAYLOAD, 3) == ["2026-07-31", "2026-08-07", "2026-08-14"]


def test_rows_for_expiry_filters_by_range_and_expiry():
    rows = rows_for_expiry(PAYLOAD, "2026-07-31", 21000, 30000)
    strikes = [r["strike"] for r in rows]
    # 20000 and 31000 are outside range; 24800/07-Aug belongs to another expiry.
    assert strikes == [24800, 24900]
    assert rows[0]["ce"]["oi"] == 342100
    assert rows[0]["pe"]["chg_oi"] == -5100


def test_rows_for_expiry_sorted_ascending():
    rows = rows_for_expiry(PAYLOAD, "2026-07-31", 21000, 30000)
    assert rows == sorted(rows, key=lambda r: r["strike"])


def test_nearest_atm_rounds_to_step():
    assert nearest_atm(24812.35, 50) == 24800
    assert nearest_atm(24826.0, 50) == 24850
