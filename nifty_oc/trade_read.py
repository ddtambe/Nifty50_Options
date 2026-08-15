"""Fuse existing signals into one CE/PE call and pick a strike (pure functions).

Direction fuses the PCR verdict with the brewing OI-surge signal. Strike
selection applies Blasco/Corredor/Santamaria's findings: informed/directional
trading concentrates in OTM (favor it over ATM), ITM is negligible (excluded),
and the pick must be confirmed by real per-strike signed volume (F2' quote
rule, already used by moneyness.py) plus OI buildup — not OI/volume alone.

Signed volume here is single-cycle (current vs. previous snapshot), matching
moneyness.py's "quote_rule_5min" method: best_bid/best_ask are not retained
across snapshots, so a multi-interval rolling score isn't available without
new data plumbing.
"""
from nifty_oc.moneyness import classify_moneyness, quote_side

_PE_ASYMMETRY_NOTE = (
    "Bearish/PE reads are backed by stronger evidence than bullish/CE reads "
    "in the reference study (bad-news volume has a larger, more significant "
    "effect than good-news volume)."
)


def _pcr_lean(pcr_verdict: str) -> str | None:
    if pcr_verdict == "Leaning Bullish":
        return "BULLISH"
    if pcr_verdict == "Leaning Bearish":
        return "BEARISH"
    return None


def _brewing_lean(brewing_signals: list[dict]) -> tuple[str | None, str | None]:
    """Direction + confidence of the strongest non-PIN brewing signal, if any."""
    for sig in brewing_signals:
        if sig.get("direction") in ("BULLISH", "BEARISH"):
            return sig["direction"], sig.get("confidence")
    return None, None


def fuse_direction(pcr_verdict: str, brewing_signals: list[dict]) -> dict:
    """Combine the PCR verdict and brewing signal into one CE/PE/None call."""
    pcr_lean = _pcr_lean(pcr_verdict)
    brew_lean, brew_conf = _brewing_lean(brewing_signals or [])

    if pcr_lean and brew_lean:
        if pcr_lean == brew_lean:
            side = "CE" if pcr_lean == "BULLISH" else "PE"
            return {"side": side, "confidence": "HIGH",
                    "reason": "PCR verdict and brewing signal agree"}
        return {"side": None, "confidence": None,
                "reason": "PCR verdict and brewing signal disagree"}

    lean = pcr_lean or brew_lean
    if lean:
        source = "PCR verdict" if pcr_lean else "brewing signal"
        side = "CE" if lean == "BULLISH" else "PE"
        return {"side": side, "confidence": "MEDIUM",
                "reason": f"Only the {source} shows a lean"}

    return {"side": None, "confidence": None,
            "reason": "No lean from PCR verdict or brewing signal"}


def _leg_row(row: dict, leg: str, spot: float) -> dict:
    p = "ce_" if leg == "CE" else "pe_"
    side = quote_side(
        row.get(p + "ltp", 0.0), row.get(p + "best_bid", 0.0),
        row.get(p + "best_ask", 0.0), row.get(p + "ltp_prev"),
    )
    dvol = row.get(p + "dvol", 0)
    signed = dvol if side == "BUY" else (-dvol if side == "SELL" else 0)
    return {
        "strike": row["strike"],
        "moneyness": classify_moneyness(row["strike"], spot, leg),
        "buildup": row.get(p + "buildup"),
        "oi": row.get(p + "oi", 0),
        "signed_volume": signed,
    }


def _pick_from(candidates: list[dict], key) -> dict | None:
    if not candidates:
        return None
    return max(candidates, key=key)


def pick_strike(rows: list[dict], spot: float, leg: str) -> dict:
    """Pick the strike to trade for `leg` ("CE" or "PE") from moneyness rows.

    Preference order: OTM strike with confirmed buying (Long Buildup + net
    positive signed volume) > OTM strike with net positive signed volume
    alone > nearest liquid OTM strike > ATM strike as last resort.
    """
    legs = [_leg_row(r, leg, spot) for r in rows]
    otm = [l for l in legs if l["moneyness"] == "OTM"]

    confirmed = [l for l in otm if l["buildup"] == "Long Buildup" and l["signed_volume"] > 0]
    top = _pick_from(confirmed, key=lambda l: l["signed_volume"])
    if top:
        rest = [l["signed_volume"] for l in confirmed if l is not top]
        dominant = not rest or top["signed_volume"] >= 2 * max(rest)
        return _result(top, "HIGH" if dominant else "MEDIUM", leg,
                        f"Strongest confirmed {leg} buying at an OTM strike "
                        f"(Long Buildup, net buy volume {top['signed_volume']})")

    buying = [l for l in otm if l["signed_volume"] > 0]
    top = _pick_from(buying, key=lambda l: l["signed_volume"])
    if top:
        return _result(top, "MEDIUM", leg,
                        f"Net {leg} buying at an OTM strike, no OI buildup confirmation yet "
                        f"(net buy volume {top['signed_volume']})")

    liquid = [l for l in otm if l["oi"] > 0]
    top = _pick_from(liquid, key=lambda l: (-abs(l["strike"] - spot)))
    if top:
        return _result(top, "LOW", leg,
                        "No confirmed OTM buying signal; falling back to the nearest liquid OTM strike")

    atm_rows = [l for l in legs if l["moneyness"] == "ATM"]
    top = _pick_from(atm_rows, key=lambda l: (-abs(l["strike"] - spot)))
    if top:
        return _result(top, "LOW", leg,
                        "No usable OTM signal; falling back to the ATM strike")

    return {"strike": None, "confidence": None, "reason": "No option rows available", "note": None}


def _result(pick: dict, confidence: str, leg: str, reason: str) -> dict:
    return {
        "strike": pick["strike"], "confidence": confidence, "reason": reason,
        "note": _PE_ASYMMETRY_NOTE if leg == "PE" else None,
    }


def trade_read(pcr_verdict: str, brewing_signals: list[dict],
                moneyness_rows: list[dict], spot: float) -> dict:
    """Fuse direction + strike pick into one Trade Read result."""
    direction = fuse_direction(pcr_verdict, brewing_signals)
    if not direction["side"]:
        return {**direction, "strike": None, "strike_confidence": None,
                "strike_reason": None, "note": None}

    pick = pick_strike(moneyness_rows, spot, direction["side"])
    return {
        **direction,
        "strike": pick["strike"],
        "strike_confidence": pick["confidence"],
        "strike_reason": pick["reason"],
        "note": pick["note"],
    }
