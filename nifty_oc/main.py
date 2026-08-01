"""Orchestrator: guard → fetch → compute → write. Actions runs this each cycle."""
import sys
from datetime import datetime, timezone, timedelta

from nifty_oc.config import DATA_DIR
from nifty_oc.clock import is_market_hours
from nifty_oc.fetcher import fetch_option_chain, FetchError
from nifty_oc.snapshot import build_snapshot
from nifty_oc import writer

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    return datetime.now(IST)


def run(now=None, fetch=None, data_dir=None) -> int:
    now = now or now_ist()
    data_dir = data_dir or DATA_DIR
    fetch = fetch or fetch_option_chain

    if not is_market_hours(now):
        print(f"[skip] outside market hours: {now}")
        return 0

    ts = now.strftime("%Y-%m-%d %H:%M")
    trade_date = ts[:10]
    prev = writer.load_prev_ltp(trade_date, data_dir)

    try:
        payload = fetch()
    except FetchError as exc:
        print(f"[skip] fetch failed (non-fatal): {exc}")
        return 0

    snap = build_snapshot(payload, ts, prev)
    writer.write_summary(snap, data_dir)
    writer.write_raw(snap, data_dir)
    writer.write_buildup(snap, data_dir)
    writer.write_json_feed(snap, data_dir)
    writer.write_index(data_dir)

    verdicts = ", ".join(f"{e['expiry']}:{e['verdict']}" for e in snap["expiries"])
    print(f"[ok] {ts} spot={snap['spot']} | {verdicts}")
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
