"""All file output: CSV (append/rewrite) and JSON feeds for the web app."""
import csv
import json
import os

SUMMARY_HEADER = [
    "timestamp_ist", "trade_date", "expiry", "spot", "atm", "pcr", "max_pain",
    "support", "resistance", "ce_oi_total", "pe_oi_total", "verdict",
]
RAW_HEADER = [
    "timestamp_ist", "expiry", "ce_oi", "ce_chg_oi", "ce_ltp", "ce_iv", "ce_volume",
    "strike", "pe_volume", "pe_iv", "pe_ltp", "pe_chg_oi", "pe_oi",
    "ce_buildup", "pe_buildup",
]
BUILDUP_HEADER = [
    "strike", "ce_oi", "ce_chg_oi", "ce_buildup", "pe_oi", "pe_chg_oi",
    "pe_buildup", "zone_200pt",
]


def _day_dir(data_dir: str, trade_date: str) -> str:
    path = os.path.join(data_dir, trade_date)
    os.makedirs(path, exist_ok=True)
    return path


def _append_rows(path: str, header: list, rows: list) -> None:
    exists = os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(header)
        w.writerows(rows)


def write_summary(snapshot: dict, data_dir: str) -> None:
    day = _day_dir(data_dir, snapshot["trade_date"])
    rows = [[
        snapshot["timestamp"], snapshot["trade_date"], e["expiry"], snapshot["spot"],
        snapshot["atm"], e["pcr"], e["max_pain"], e["support"], e["resistance"],
        e["ce_oi_total"], e["pe_oi_total"], e["verdict"],
    ] for e in snapshot["expiries"]]
    _append_rows(os.path.join(day, "summary.csv"), SUMMARY_HEADER, rows)


def write_raw(snapshot: dict, data_dir: str) -> None:
    day = _day_dir(data_dir, snapshot["trade_date"])
    for e in snapshot["expiries"]:
        rows = [[
            snapshot["timestamp"], e["expiry"], r["ce_oi"], r["ce_chg_oi"], r["ce_ltp"],
            r["ce_iv"], r["ce_volume"], r["strike"], r["pe_volume"], r["pe_iv"],
            r["pe_ltp"], r["pe_chg_oi"], r["pe_oi"], r["ce_buildup"], r["pe_buildup"],
        ] for r in e["display_rows"]]
        _append_rows(os.path.join(day, f"{e['expiry']}_raw.csv"), RAW_HEADER, rows)


def write_buildup(snapshot: dict, data_dir: str) -> None:
    day = _day_dir(data_dir, snapshot["trade_date"])
    for e in snapshot["expiries"]:
        path = os.path.join(day, f"{e['expiry']}_buildup.csv")
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(BUILDUP_HEADER)
            for r in e["display_rows"]:
                w.writerow([
                    r["strike"], r["ce_oi"], r["ce_chg_oi"], r["ce_buildup"],
                    r["pe_oi"], r["pe_chg_oi"], r["pe_buildup"], r["zone_200pt"],
                ])


def write_json_feed(snapshot: dict, data_dir: str) -> None:
    day = _day_dir(data_dir, snapshot["trade_date"])
    for e in snapshot["expiries"]:
        path = os.path.join(day, f"{e['expiry']}.json")
        if os.path.exists(path):
            with open(path) as f:
                feed = json.load(f)
        else:
            feed = {"meta": {}, "timeline": [], "strikes": []}
        feed["meta"] = {
            "trade_date": snapshot["trade_date"], "expiry": e["expiry"],
            "updated_ist": snapshot["timestamp"],
        }
        feed["timeline"].append({
            "t": snapshot["timestamp"], "spot": snapshot["spot"],
            "pcr": e["pcr"], "max_pain": e["max_pain"],
        })
        feed["strikes"] = e["display_rows"]
        with open(path, "w") as f:
            json.dump(feed, f)


def write_index(data_dir: str) -> None:
    days = []
    if os.path.isdir(data_dir):
        for trade_date in sorted(os.listdir(data_dir)):
            day_path = os.path.join(data_dir, trade_date)
            if not os.path.isdir(day_path):
                continue
            expiries = sorted(
                fn[:-5] for fn in os.listdir(day_path)
                if fn.endswith(".json")
            )
            if expiries:
                days.append({"trade_date": trade_date, "expiries": expiries})
    with open(os.path.join(data_dir, "index.json"), "w") as f:
        json.dump({"days": days}, f)


def load_prev_ltp(trade_date: str, data_dir: str) -> dict:
    day = os.path.join(data_dir, trade_date)
    prev = {}
    if not os.path.isdir(day):
        return prev
    for fn in os.listdir(day):
        if not fn.endswith("_raw.csv"):
            continue
        with open(os.path.join(day, fn), newline="") as f:
            rows = list(csv.DictReader(f))
        for row in rows:  # later rows overwrite → last value wins
            expiry, strike = row["expiry"], int(row["strike"])
            prev[(expiry, strike, "CE")] = float(row["ce_ltp"])
            prev[(expiry, strike, "PE")] = float(row["pe_ltp"])
    return prev
