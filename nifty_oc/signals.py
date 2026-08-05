"""Brewing-move detection from OI surges. Pure functions, no I/O.

Reads a feed's accumulated `strikes_timeline` and detects strikes whose CE or PE
OI is surging over short windows — a leading signal that a price move is
building. Direction: PE surge => support building => BULLISH (favor CE);
CE surge => resistance building => BEARISH (favor PE); both legs => PIN.
"""


def _pct_and_delta(oi_now: int, oi_past: int) -> tuple[float, int] | None:
    """Return (pct, delta) for an OI change, or None if there is no baseline."""
    if oi_past <= 0:
        return None
    delta = oi_now - oi_past
    return delta / oi_past, delta


def _side_of_spot(strike: int, spot: float) -> str:
    if strike < spot:
        return "below"
    if strike > spot:
        return "above"
    return "at"


def _is_textbook(leg: str, side: str) -> bool:
    """PE surge below spot = support; CE surge above spot = resistance."""
    return (leg == "PE" and side == "below") or (leg == "CE" and side == "above")


def _leg_signal(leg: str, oi_now: int, past_by_window: dict[str, int],
                strike: int, spot: float,
                pct_threshold: float, abs_threshold: int) -> dict | None:
    """Build a single-leg signal, or None if no window clears both thresholds."""
    flagged: list[str] = []
    stats: dict = {}
    for label, oi_past in past_by_window.items():
        pd = _pct_and_delta(oi_now, oi_past)
        if pd is None:
            continue
        pct, delta = pd
        if pct >= pct_threshold and delta >= abs_threshold:
            flagged.append(label)
            stats[f"oi_past_{label}"] = oi_past
            stats[f"pct_{label}"] = round(pct, 4)
            stats[f"abs_{label}"] = delta
    if not flagged:
        return None
    side = _side_of_spot(strike, spot)
    direction = "BULLISH" if leg == "PE" else "BEARISH"
    high = len(flagged) >= 2 or _is_textbook(leg, side)
    return {
        "strike": strike,
        "leg": leg,
        "direction": direction,
        "confidence": "HIGH" if high else "MEDIUM",
        "windows": flagged,
        "oi_now": oi_now,
        "side_of_spot": side,
        **stats,
    }


def _merge_pin(ce_sig: dict, pe_sig: dict, strike: int, spot: float) -> dict:
    """Combine same-strike CE+PE signals into one PIN (rangebound) signal."""
    windows = list(ce_sig["windows"])
    windows += [w for w in pe_sig["windows"] if w not in windows]
    high = "HIGH" in (ce_sig["confidence"], pe_sig["confidence"])
    merged = {
        "strike": strike,
        "leg": "BOTH",
        "direction": "PIN",
        "confidence": "HIGH" if high else "MEDIUM",
        "windows": windows,
        "ce_oi_now": ce_sig["oi_now"],
        "pe_oi_now": pe_sig["oi_now"],
        "side_of_spot": _side_of_spot(strike, spot),
    }
    for k, v in ce_sig.items():
        if k.startswith(("oi_past_", "pct_", "abs_")):
            merged[f"ce_{k}"] = v
    for k, v in pe_sig.items():
        if k.startswith(("oi_past_", "pct_", "abs_")):
            merged[f"pe_{k}"] = v
    return merged


def _max_abs(sig: dict) -> int:
    """Largest absolute OI surge in a signal (single-leg or PIN), for sorting."""
    vals = [v for k, v in sig.items()
            if k.startswith("abs_") or k.startswith("ce_abs_") or k.startswith("pe_abs_")]
    return max(vals) if vals else 0


def detect_brewing(strikes_timeline: list[dict], spot: float,
                   pct_threshold: float, abs_threshold: int,
                   windows: dict[str, int]) -> list[dict]:
    """Return brewing-move signals for the latest snapshot in the timeline.

    Returns [] when there are too few snapshots for any configured window.
    """
    if not strikes_timeline or len(strikes_timeline) < 2:
        return []

    latest_rows = strikes_timeline[-1]["rows"]

    # For each window that has enough history, map strike -> row at that offset.
    past_maps: dict[str, dict[int, dict]] = {}
    for label, n in windows.items():
        if len(strikes_timeline) >= n + 1:
            past_rows = strikes_timeline[-1 - n]["rows"]
            past_maps[label] = {row["strike"]: row for row in past_rows}
    if not past_maps:
        return []

    signals: list[dict] = []
    for row in latest_rows:
        strike = row["strike"]
        per_leg: dict[str, dict] = {}
        for leg, key in (("CE", "ce_oi"), ("PE", "pe_oi")):
            past_by_window = {
                label: pmap[strike][key]
                for label, pmap in past_maps.items()
                if strike in pmap
            }
            sig = _leg_signal(leg, row[key], past_by_window, strike, spot,
                              pct_threshold, abs_threshold)
            if sig:
                per_leg[leg] = sig
        if "CE" in per_leg and "PE" in per_leg:
            signals.append(_merge_pin(per_leg["CE"], per_leg["PE"], strike, spot))
        else:
            signals.extend(per_leg.values())

    rank = {"HIGH": 0, "MEDIUM": 1}
    signals.sort(key=lambda s: (rank[s["confidence"]], -_max_abs(s)))
    return signals
