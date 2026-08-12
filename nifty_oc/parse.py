"""Turn raw NSE payload into clean row dicts. Pure functions."""
from nifty_oc.dates import parse_nse_expiry, select_expiries


def extract_spot(payload: dict) -> float:
    return payload["records"]["underlyingValue"]


def extract_expiries(payload: dict, count: int) -> list[str]:
    return select_expiries(payload["records"]["expiryDates"], count)


def _leg(node: dict | None) -> dict:
    if not node:
        return {"oi": 0, "chg_oi": 0, "ltp": 0.0, "iv": 0.0, "volume": 0,
                "best_bid": 0.0, "best_ask": 0.0}
    return {
        "oi": node.get("openInterest", 0),
        "chg_oi": node.get("changeinOpenInterest", 0),
        "ltp": node.get("lastPrice", 0.0),
        "iv": node.get("impliedVolatility", 0.0),
        "volume": node.get("totalTradedVolume", 0),
        "best_bid": node.get("bestBid", 0.0),
        "best_ask": node.get("bestAsk", 0.0),
    }


def rows_for_expiry(payload: dict, iso_expiry: str, strike_min: int, strike_max: int) -> list[dict]:
    rows = []
    for entry in payload["records"]["data"]:
        if parse_nse_expiry(entry["expiryDate"]) != iso_expiry:
            continue
        strike = entry["strikePrice"]
        if not (strike_min <= strike <= strike_max):
            continue
        rows.append({"strike": strike, "ce": _leg(entry.get("CE")), "pe": _leg(entry.get("PE"))})
    rows.sort(key=lambda r: r["strike"])
    return rows


def nearest_atm(spot: float, step: int) -> int:
    return int(round(spot / step) * step)
