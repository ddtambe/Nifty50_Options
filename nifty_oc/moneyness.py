"""Moneyness decomposition + quote-rule signed volume (pure functions).

Implements Blasco/Corredor/Santamaria's moneyness split (F1) and an adapted
quote-rule signed-volume metric (F2'). No I/O, no globals mutated. See
docs/superpowers/specs/2026-08-11-moneyness-comparison-panel-design.md.
"""
from nifty_oc.config import MONEYNESS_ATM_LOW, MONEYNESS_ATM_HIGH

BUCKETS = ("ATM", "OTM", "ITM")


def classify_moneyness(strike: float, spot: float, leg: str) -> str:
    """Bucket one option leg by S/K per formula F1 (band edges inclusive)."""
    if strike <= 0:
        return "ATM"
    ratio = spot / strike
    if MONEYNESS_ATM_LOW <= ratio <= MONEYNESS_ATM_HIGH:
        return "ATM"
    if leg == "CE":
        return "OTM" if ratio < MONEYNESS_ATM_LOW else "ITM"
    return "OTM" if ratio > MONEYNESS_ATM_HIGH else "ITM"  # PE mirror


def quote_side(ltp_now: float, best_bid: float, best_ask: float,
               ltp_prev: float | None) -> str | None:
    """Classify an interval as BUY or SELL by the quote rule (F2').

    Primary: LTP vs the bid/ask mid. Fallback (quote missing/crossed, or LTP
    exactly at mid): tick test vs the previous LTP. None when nothing resolves.
    """
    if best_bid > 0 and best_ask > 0 and best_ask >= best_bid:
        mid = (best_bid + best_ask) / 2
        if ltp_now > mid:
            return "BUY"
        if ltp_now < mid:
            return "SELL"
    if ltp_prev is not None:
        if ltp_now > ltp_prev:
            return "BUY"
        if ltp_now < ltp_prev:
            return "SELL"
    return None


def _blank_acc() -> dict:
    return {"vol_pos": 0, "vol_neg": 0, "traded_volume": 0, "ce_oi": 0, "pe_oi": 0}


def _add_leg(acc: dict, leg: str, dvol: int, side: str | None, oi: int) -> None:
    acc["traded_volume"] += dvol
    if leg == "CE":
        acc["ce_oi"] += oi
        if side == "BUY":
            acc["vol_pos"] += dvol      # call purchased -> bullish
        elif side == "SELL":
            acc["vol_neg"] += dvol      # call sold -> bearish
    else:  # PE
        acc["pe_oi"] += oi
        if side == "BUY":
            acc["vol_neg"] += dvol      # put purchased -> bearish
        elif side == "SELL":
            acc["vol_pos"] += dvol      # put sold -> bullish


def moneyness_panel(rows: list[dict], spot: float) -> dict:
    """Aggregate display rows into ATM/OTM/ITM buckets (F1 + F2' + PCR + share)."""
    acc = {name: _blank_acc() for name in BUCKETS}

    for r in rows:
        strike = r.get("strike", 0)
        for leg in ("CE", "PE"):
            p = "ce_" if leg == "CE" else "pe_"
            dvol = max(0, r.get(p + "dvol", 0))
            oi = r.get(p + "oi", 0)
            side = quote_side(
                r.get(p + "ltp", 0.0),
                r.get(p + "best_bid", 0.0),
                r.get(p + "best_ask", 0.0),
                r.get(p + "ltp_prev", None),
            )
            _add_leg(acc[classify_moneyness(strike, spot, leg)], leg, dvol, side, oi)

    total_volume = sum(a["traded_volume"] for a in acc.values())

    buckets = {}
    for name in BUCKETS:
        a = acc[name]
        buckets[name] = {
            "vol_pos": a["vol_pos"],
            "vol_neg": a["vol_neg"],
            "imbalance": a["vol_pos"] - a["vol_neg"],
            "traded_volume": a["traded_volume"],
            "volume_share": (a["traded_volume"] / total_volume) if total_volume else 0.0,
            "pcr": round(a["pe_oi"] / a["ce_oi"], 2) if a["ce_oi"] else 0.0,
        }

    return {
        "spot": spot,
        "method": "quote_rule_5min",
        "total_volume": total_volume,
        "buckets": buckets,
    }
