"""Pure indicator functions. No I/O, no globals mutated."""

# PCR thresholds for the verdict.
_BULLISH_PCR = 1.2
_BEARISH_PCR = 0.8


def classify_buildup(chg_ltp: float, chg_oi: int) -> str:
    """Standard 4-quadrant buildup classification from ΔLTP vs ΔOI.

    Returns "N/A" whenever chg_oi == 0 (no OI change → no buildup signal),
    regardless of ΔLTP. Otherwise: OI up → Long Buildup (price up) / Short
    Buildup (price flat or down); OI down → Short Covering (price up) /
    Long Unwinding (price flat or down).
    """
    if chg_ltp == 0 and chg_oi == 0:
        return "N/A"
    if chg_oi > 0:
        return "Long Buildup" if chg_ltp > 0 else "Short Buildup"
    if chg_oi < 0:
        return "Short Covering" if chg_ltp > 0 else "Long Unwinding"
    return "N/A"


def pcr(rows: list[dict]) -> float:
    ce_total = sum(r["ce"]["oi"] for r in rows)
    pe_total = sum(r["pe"]["oi"] for r in rows)
    if ce_total == 0:
        return 0.0
    return round(pe_total / ce_total, 2)


def max_pain(rows: list[dict]) -> int:
    """Strike where total writer payout (CE + PE) is minimized at expiry."""
    if not rows:
        raise ValueError("max_pain: rows is empty")
    strikes = sorted(r["strike"] for r in rows)
    best_strike, best_pain = strikes[0], None
    for expiry_price in strikes:
        pain = 0
        for r in rows:
            k = r["strike"]
            if expiry_price > k:  # ITM calls pay out
                pain += (expiry_price - k) * r["ce"]["oi"]
            if expiry_price < k:  # ITM puts pay out
                pain += (k - expiry_price) * r["pe"]["oi"]
        if best_pain is None or pain < best_pain:
            best_pain, best_strike = pain, expiry_price
    return best_strike


def support(rows: list[dict]) -> int:
    if not rows:
        raise ValueError("support: rows is empty")
    return max(rows, key=lambda r: r["pe"]["oi"])["strike"]


def resistance(rows: list[dict]) -> int:
    if not rows:
        raise ValueError("resistance: rows is empty")
    return max(rows, key=lambda r: r["ce"]["oi"])["strike"]


def zone_200(strike: int) -> str:
    lower = (strike // 200) * 200
    return f"{lower}-{lower + 200}"


def verdict(pcr_value: float, rows: list[dict], atm: int) -> str:
    if pcr_value >= _BULLISH_PCR:
        return "Leaning Bullish"
    if pcr_value <= _BEARISH_PCR and pcr_value > 0:
        return "Leaning Bearish"
    return "Rangebound"


def display_strikes(rows: list[dict], step: int) -> list[dict]:
    return [r for r in rows if r["strike"] % step == 0]
