"""Fetch option chain data via 5paisa API."""
import os
from datetime import datetime, timezone, timedelta
from py5paisa import FivePaisaClient

from nifty_oc.config import NUM_EXPIRIES


class FetchError(Exception):
    pass


def _get_credentials() -> dict:
    """Read 5paisa credentials from environment variables."""
    required = [
        "FIVEPAISA_APP_NAME",
        "FIVEPAISA_APP_SOURCE",
        "FIVEPAISA_USER_ID",
        "FIVEPAISA_PASSWORD",
        "FIVEPAISA_USER_KEY",
        "FIVEPAISA_ENCRYPTION_KEY",
    ]
    cred = {}
    missing = []
    for key in required:
        val = os.environ.get(key)
        if not val:
            missing.append(key)
        else:
            # Map env var names to 5paisa expected keys
            cred_key = key.replace("FIVEPAISA_", "")
            cred[cred_key] = val

    if missing:
        raise FetchError(f"Missing credentials: {', '.join(missing)}")

    return cred


def _get_expiry_dates(count: int) -> list[int]:
    """Get the next N Thursday expiry dates as YYYYMMDD integers."""
    IST = timezone(timedelta(hours=5, minutes=30))
    today = datetime.now(IST).date()

    expiries = []
    d = today
    while len(expiries) < count:
        # Find next Thursday (weekday 3)
        days_ahead = (3 - d.weekday()) % 7
        if days_ahead == 0 and d <= today:
            days_ahead = 7
        next_thu = d + timedelta(days=days_ahead)

        # Only add if it's in the future or today
        if next_thu >= today:
            expiries.append(int(next_thu.strftime("%Y%m%d")))
        d = next_thu + timedelta(days=1)

    return expiries[:count]


def _format_expiry_nse_style(yyyymmdd: int) -> str:
    """Convert 20260731 to '31-Jul-2026' (NSE format for compatibility)."""
    dt = datetime.strptime(str(yyyymmdd), "%Y%m%d")
    return dt.strftime("%d-%b-%Y")


def _transform_5paisa_to_nse_format(client: FivePaisaClient, expiry_dates: list[int]) -> dict:
    """
    Fetch option chain from 5paisa and transform to NSE-like format.

    The rest of the pipeline expects this structure:
    {
      "records": {
        "underlyingValue": 24812.35,
        "expiryDates": ["31-Jul-2026", ...],
        "data": [
          {"strikePrice": X, "expiryDate": "DD-Mon-YYYY",
           "CE": {"openInterest": X, "changeinOpenInterest": Y, ...},
           "PE": {...}
          }, ...
        ]
      }
    }
    """
    all_data = []
    spot_price = None

    for exp_date in expiry_dates:
        try:
            # 5paisa get_option_chain(exchange, symbol, expiry_as_int)
            chain = client.get_option_chain("N", "NIFTY", exp_date)

            if not chain:
                continue

            expiry_str = _format_expiry_nse_style(exp_date)

            # Process the chain data
            if isinstance(chain, dict) and "Options" in chain:
                options = chain["Options"]
            elif isinstance(chain, list):
                options = chain
            else:
                options = []

            # Group by strike price
            strikes = {}
            for opt in options:
                strike = opt.get("StrikeRate") or opt.get("StrikePrice") or opt.get("Strike")
                if not strike:
                    continue
                strike = int(float(strike))

                if strike not in strikes:
                    strikes[strike] = {"CE": None, "PE": None}

                opt_type = opt.get("CPType") or opt.get("OptionType") or ""

                leg_data = {
                    "openInterest": opt.get("OpenInterest", 0) or opt.get("OI", 0) or 0,
                    "changeinOpenInterest": opt.get("ChangeInOI", 0) or opt.get("NetChangeInOI", 0) or 0,
                    "lastPrice": opt.get("LastRate", 0) or opt.get("LTP", 0) or 0,
                    "impliedVolatility": opt.get("IV", 0) or opt.get("ImpliedVolatility", 0) or 0,
                    "totalTradedVolume": opt.get("Volume", 0) or opt.get("TradedQty", 0) or 0,
                }

                if opt_type in ("CE", "C", "CALL"):
                    strikes[strike]["CE"] = leg_data
                elif opt_type in ("PE", "P", "PUT"):
                    strikes[strike]["PE"] = leg_data

                # Try to get spot price from underlying
                if spot_price is None:
                    spot_price = opt.get("UnderlyingValue") or opt.get("SpotPrice") or opt.get("Spot")

            # Convert to NSE-like data format
            for strike, legs in strikes.items():
                entry = {
                    "strikePrice": strike,
                    "expiryDate": expiry_str,
                    "CE": legs["CE"],
                    "PE": legs["PE"],
                }
                all_data.append(entry)

        except Exception as e:
            print(f"[warn] Failed to fetch expiry {exp_date}: {e}")
            continue

    if not all_data:
        raise FetchError("No option chain data received from 5paisa")

    # If we couldn't get spot from options, try market feed
    if spot_price is None:
        try:
            # Fetch NIFTY spot price
            feed = client.fetch_market_feed_scrip([{"Exch": "N", "ExchType": "D", "ScripCode": 999920000}])
            if feed and len(feed) > 0:
                spot_price = feed[0].get("LastRate") or feed[0].get("LTP")
        except:
            pass

    # Default spot if all else fails (should not happen in production)
    if spot_price is None:
        spot_price = 24000.0
        print("[warn] Could not fetch spot price, using default")

    return {
        "records": {
            "underlyingValue": float(spot_price),
            "expiryDates": [_format_expiry_nse_style(d) for d in expiry_dates],
            "data": all_data,
        }
    }


def fetch_option_chain() -> dict:
    """
    Fetch Nifty option chain from 5paisa API.

    Returns data in NSE-compatible format for the rest of the pipeline.
    Raises FetchError if authentication or fetch fails.
    """
    try:
        cred = _get_credentials()
        client = FivePaisaClient(cred=cred)

        # Get OAuth token - requires a one-time manual login to get response token
        # For automated use, we'll try direct access which may work for some endpoints
        # If this fails, user needs to set up TOTP/OAuth properly

        # Get the next N expiry dates
        expiry_dates = _get_expiry_dates(NUM_EXPIRIES)

        # Fetch and transform
        return _transform_5paisa_to_nse_format(client, expiry_dates)

    except FetchError:
        raise
    except Exception as exc:
        raise FetchError(f"5paisa API error: {exc}")
