# tests/test_writer.py
import csv
import json
from pathlib import Path
from nifty_oc import writer


def sample_snapshot():
    return {
        "timestamp": "2026-07-29 09:30", "trade_date": "2026-07-29",
        "spot": 24812.35, "atm": 24800,
        "expiries": [{
            "expiry": "2026-07-31", "pcr": 1.24, "max_pain": 24700,
            "support": 24500, "resistance": 25000,
            "ce_oi_total": 4562300, "pe_oi_total": 5657250, "verdict": "Leaning Bullish",
            "display_rows": [{
                "strike": 24800, "ce_oi": 342100, "ce_chg_oi": 22400, "ce_ltp": 74.2,
                "ce_iv": 11.2, "ce_volume": 152300, "pe_oi": 288900, "pe_chg_oi": -5100,
                "pe_ltp": 78.9, "pe_iv": 12.1, "pe_volume": 61200,
                "ce_buildup": "N/A", "pe_buildup": "N/A", "zone_200pt": "24800-25000",
            }],
        }],
    }


def test_write_summary_appends_header_once(tmp_path):
    writer.write_summary(sample_snapshot(), str(tmp_path))
    writer.write_summary(sample_snapshot(), str(tmp_path))
    f = tmp_path / "2026-07-29" / "summary.csv"
    rows = list(csv.reader(f.open()))
    assert rows[0][0] == "timestamp_ist"       # one header
    assert len(rows) == 3                        # header + 2 data rows
    assert rows[1][2] == "2026-07-31"


def test_write_raw_appends(tmp_path):
    writer.write_raw(sample_snapshot(), str(tmp_path))
    writer.write_raw(sample_snapshot(), str(tmp_path))
    f = tmp_path / "2026-07-29" / "2026-07-31_raw.csv"
    rows = list(csv.reader(f.open()))
    assert rows[0][0] == "timestamp_ist"
    assert len(rows) == 3
    # chg_oi stored as plain signed integer, no leading '+'
    assert "-5100" in rows[1]


def test_write_buildup_overwrites(tmp_path):
    writer.write_buildup(sample_snapshot(), str(tmp_path))
    writer.write_buildup(sample_snapshot(), str(tmp_path))
    f = tmp_path / "2026-07-29" / "2026-07-31_buildup.csv"
    rows = list(csv.reader(f.open()))
    assert rows[0][0] == "strike"
    assert len(rows) == 2   # header + 1 row (overwritten, not appended)


def test_write_json_feed_accumulates_timeline(tmp_path):
    writer.write_json_feed(sample_snapshot(), str(tmp_path))
    snap2 = sample_snapshot()
    snap2["timestamp"] = "2026-07-29 09:45"
    writer.write_json_feed(snap2, str(tmp_path))
    feed = json.loads((tmp_path / "2026-07-29" / "2026-07-31.json").read_text())
    assert feed["meta"]["expiry"] == "2026-07-31"
    assert len(feed["timeline"]) == 2
    assert feed["strikes"][0]["strike"] == 24800


def test_write_json_feed_accumulates_strikes_timeline(tmp_path):
    # First snapshot
    writer.write_json_feed(sample_snapshot(), str(tmp_path))
    # Second snapshot with different OI values for the same strike
    snap2 = sample_snapshot()
    snap2["timestamp"] = "2026-07-29 09:45"
    snap2["expiries"][0]["display_rows"][0]["ce_oi"] = 500000
    snap2["expiries"][0]["display_rows"][0]["pe_oi"] = 400000
    writer.write_json_feed(snap2, str(tmp_path))

    feed = json.loads((tmp_path / "2026-07-29" / "2026-07-31.json").read_text())
    st = feed["strikes_timeline"]
    assert len(st) == 2                                  # one entry per snapshot
    assert st[0]["t"] == "2026-07-29 09:30"
    assert st[1]["t"] == "2026-07-29 09:45"
    # Each entry stores minimal per-strike OI
    assert st[0]["rows"][0] == {"strike": 24800, "ce_oi": 342100, "pe_oi": 288900}
    assert st[1]["rows"][0] == {"strike": 24800, "ce_oi": 500000, "pe_oi": 400000}


def test_write_index_lists_days_and_expiries(tmp_path):
    writer.write_json_feed(sample_snapshot(), str(tmp_path))
    writer.write_index(str(tmp_path))
    idx = json.loads((tmp_path / "index.json").read_text())
    assert idx["days"][0]["trade_date"] == "2026-07-29"
    assert "2026-07-31" in idx["days"][0]["expiries"]


def test_load_prev_ltp_reads_last_rows(tmp_path):
    writer.write_raw(sample_snapshot(), str(tmp_path))
    prev = writer.load_prev_ltp("2026-07-29", str(tmp_path))
    assert prev[("2026-07-31", 24800, "CE")] == 74.2
    assert prev[("2026-07-31", 24800, "PE")] == 78.9
