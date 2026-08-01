"""Assemble one cycle's fully-computed snapshot from a raw payload."""
from nifty_oc import indicators
from nifty_oc.config import (
    STRIKE_MIN, STRIKE_MAX, STRIKE_STEP, DISPLAY_STEP, NUM_EXPIRIES,
)
from nifty_oc.parse import (
    extract_spot, extract_expiries, rows_for_expiry, nearest_atm,
)


def trade_date_of(timestamp_ist: str) -> str:
    return timestamp_ist[:10]


def _buildup_for(leg: dict, key, prev_ltp: dict) -> str:
    if key not in prev_ltp:
        return indicators.classify_buildup(0.0, 0)  # N/A on first sighting
    chg_ltp = leg["ltp"] - prev_ltp[key]
    return indicators.classify_buildup(chg_ltp, leg["chg_oi"])


def _display_row(r: dict, expiry: str, prev_ltp: dict) -> dict:
    ce, pe = r["ce"], r["pe"]
    strike = r["strike"]
    return {
        "strike": strike,
        "ce_oi": ce["oi"], "ce_chg_oi": ce["chg_oi"], "ce_ltp": ce["ltp"],
        "ce_iv": ce["iv"], "ce_volume": ce["volume"],
        "pe_oi": pe["oi"], "pe_chg_oi": pe["chg_oi"], "pe_ltp": pe["ltp"],
        "pe_iv": pe["iv"], "pe_volume": pe["volume"],
        "ce_buildup": _buildup_for(ce, (expiry, strike, "CE"), prev_ltp),
        "pe_buildup": _buildup_for(pe, (expiry, strike, "PE"), prev_ltp),
        "zone_200pt": indicators.zone_200(strike),
    }


def build_snapshot(payload: dict, timestamp_ist: str, prev_ltp: dict) -> dict:
    spot = extract_spot(payload)
    atm = nearest_atm(spot, STRIKE_STEP)
    expiries_iso = extract_expiries(payload, NUM_EXPIRIES)

    results = []
    for expiry in expiries_iso:
        rows = rows_for_expiry(payload, expiry, STRIKE_MIN, STRIKE_MAX)
        if not rows:
            continue
        disp = indicators.display_strikes(rows, DISPLAY_STEP)
        results.append({
            "expiry": expiry,
            "pcr": indicators.pcr(rows),
            "max_pain": indicators.max_pain(rows),
            "support": indicators.support(rows),
            "resistance": indicators.resistance(rows),
            "ce_oi_total": sum(r["ce"]["oi"] for r in rows),
            "pe_oi_total": sum(r["pe"]["oi"] for r in rows),
            "verdict": indicators.verdict(indicators.pcr(rows), rows, atm),
            "display_rows": [_display_row(r, expiry, prev_ltp) for r in disp],
        })

    return {
        "timestamp": timestamp_ist,
        "trade_date": trade_date_of(timestamp_ist),
        "spot": spot,
        "atm": atm,
        "expiries": results,
    }


def ltp_index(snapshot: dict) -> dict:
    """Map (expiry, strike, leg) -> LTP for use as next cycle's prev_ltp."""
    idx = {}
    for e in snapshot["expiries"]:
        for r in e["display_rows"]:
            idx[(e["expiry"], r["strike"], "CE")] = r["ce_ltp"]
            idx[(e["expiry"], r["strike"], "PE")] = r["pe_ltp"]
    return idx
