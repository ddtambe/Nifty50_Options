# tests/test_main.py
import json
from datetime import datetime
from pathlib import Path
from nifty_oc import main

PAYLOAD = json.loads((Path(__file__).parents[0] / "fixtures" / "sample_chain.json").read_text())


def test_run_skips_outside_market_hours(tmp_path):
    code = main.run(now=datetime(2026, 7, 29, 8, 0),
                    fetch=lambda: PAYLOAD, data_dir=str(tmp_path))
    assert code == 0
    assert not (tmp_path / "2026-07-29").exists()  # nothing written


def test_run_writes_files_during_market_hours(tmp_path):
    code = main.run(now=datetime(2026, 7, 29, 9, 30),
                    fetch=lambda: PAYLOAD, data_dir=str(tmp_path))
    assert code == 0
    assert (tmp_path / "2026-07-29" / "summary.csv").exists()
    assert (tmp_path / "2026-07-29" / "2026-07-31.json").exists()
    assert (tmp_path / "index.json").exists()


def test_run_returns_zero_on_fetch_error(tmp_path):
    def boom():
        from nifty_oc.fetcher import FetchError
        raise FetchError("blocked")
    code = main.run(now=datetime(2026, 7, 29, 9, 30), fetch=boom, data_dir=str(tmp_path))
    assert code == 0  # non-fatal: Actions stays green


def test_now_ist_is_utc_plus_530():
    n = main.now_ist()
    assert n.utcoffset().total_seconds() == 5.5 * 3600
