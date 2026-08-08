"""Fetch option chain data via 5paisa API."""
import os
import hmac
import struct
import hashlib
import base64
import time as time_module
from datetime import datetime, timezone, timedelta
from py5paisa import FivePaisaClient

from nifty_oc.config import NUM_EXPIRIES


def _generate_totp(secret: str) -> str:
    """Generate current TOTP code from secret (RFC 6238)."""
    # Decode base32 secret
    key = base64.b32decode(secret.upper() + '=' * ((8 - len(secret) % 8) % 8))
    # Get current 30-second window
    counter = int(time_module.time()) // 30
    # Generate HMAC-SHA1
    counter_bytes = struct.pack('>Q', counter)
    hmac_hash = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    # Dynamic truncation
    offset = hmac_hash[-1] & 0x0F
    code = struct.unpack('>I', hmac_hash[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % 1000000).zfill(6)


class FetchError(Exception):
    pass


def _get_credentials() -> tuple[dict, dict]:
    """Read 5paisa credentials from environment variables.

    Returns (cred_dict, login_dict) where:
    - cred_dict: APP_NAME, APP_SOURCE, USER_ID, PASSWORD, USER_KEY, ENCRYPTION_KEY
    - login_dict: CLIENT_CODE, TOTP_SECRET, PIN for TOTP login
    """
    cred_keys = [
        "FIVEPAISA_APP_NAME",
        "FIVEPAISA_APP_SOURCE",
        "FIVEPAISA_USER_ID",
        "FIVEPAISA_PASSWORD",
        "FIVEPAISA_USER_KEY",
        "FIVEPAISA_ENCRYPTION_KEY",
    ]
    login_keys = [
        "FIVEPAISA_CLIENT_CODE",
        "FIVEPAISA_TOTP_SECRET",
        "FIVEPAISA_PIN",
    ]

    cred = {}
    login = {}
    missing = []

    for key in cred_keys:
        val = os.environ.get(key)
        if not val:
            missing.append(key)
        else:
            cred_key = key.replace("FIVEPAISA_", "")
            cred[cred_key] = val

    for key in login_keys:
        val = os.environ.get(key)
        if not val:
            missing.append(key)
        else:
            login_key = key.replace("FIVEPAISA_", "")
            login[login_key] = val

    if missing:
        raise FetchError(f"Missing credentials: {', '.join(missing)}")

    return cred, login


def _timestamp_to_nse_style(ts_millis: int) -> str:
    """Convert timestamp milliseconds to '31-Jul-2026' (NSE format)."""
    dt = datetime.fromtimestamp(ts_millis / 1000, tz=timezone(timedelta(hours=5, minutes=30)))
    return dt.strftime("%d-%b-%Y")


def _parse_expiry_date(expiry_obj) -> int:
    """Extract timestamp from 5paisa expiry format.

    Input can be:
    - int: raw timestamp in milliseconds
    - str: '/Date(1785834000000+0530)/'
    - dict: {'ExpiryDate': '/Date(1785834000000+0530)/', ...}
    """
    import re

    if isinstance(expiry_obj, int):
        return expiry_obj

    if isinstance(expiry_obj, dict):
        expiry_str = expiry_obj.get("ExpiryDate", "")
    else:
        expiry_str = str(expiry_obj)

    # Parse /Date(TIMESTAMP+OFFSET)/ format
    match = re.search(r'/Date\((\d+)[+-]', expiry_str)
    if match:
        return int(match.group(1))

    # Try direct int conversion
    try:
        return int(expiry_str)
    except ValueError:
        raise FetchError(f"Cannot parse expiry date: {expiry_obj}")


def _transform_5paisa_to_nse_format(client: FivePaisaClient, num_expiries: int) -> dict:
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
    # Get expiry dates from API
    expiry_response = client.get_expiry("N", "NIFTY")
    print(f"[debug] get_expiry response: {expiry_response}")

    # Handle different response formats
    if isinstance(expiry_response, dict) and "Expiry" in expiry_response:
        expiry_list = expiry_response["Expiry"]
    elif isinstance(expiry_response, list):
        expiry_list = expiry_response
    else:
        raise FetchError(f"Unexpected expiry response format: {type(expiry_response)}")

    # Parse and take first N expiries (convert to timestamps)
    expiry_timestamps = [_parse_expiry_date(e) for e in expiry_list[:num_expiries]]
    print(f"[debug] Using expiry timestamps: {expiry_timestamps}")

    all_data = []
    spot_price = None
    expiry_dates_nse = []

    for exp_ts in expiry_timestamps:
        try:
            # 5paisa get_option_chain(exchange, symbol, expiry_timestamp)
            chain = client.get_option_chain("N", "NIFTY", exp_ts)
            print(f"[debug] Option chain for {exp_ts}: {type(chain)}, keys={chain.keys() if isinstance(chain, dict) else 'list'}")

            if not chain:
                continue

            expiry_str = _timestamp_to_nse_style(exp_ts)
            expiry_dates_nse.append(expiry_str)

            # Process the chain data - handle various response formats
            if isinstance(chain, dict):
                # Could be {"Options": [...]} or {"data": [...]} or direct list
                options = chain.get("Options") or chain.get("data") or chain.get("OptionChain") or []
            elif isinstance(chain, list):
                options = chain
            else:
                options = []

            print(f"[debug] Processing {len(options)} options for expiry {expiry_str}")

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
            print(f"[warn] Failed to fetch expiry {exp_ts}: {e}")
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

    # Never fake the spot: a wrong spot silently corrupts confidence,
    # max-pain positioning and verdicts. Fail the cycle instead so main.py
    # skips cleanly rather than publishing garbage.
    if spot_price is None:
        raise FetchError(
            "Could not resolve NIFTY spot from option chain or market feed"
        )

    return {
        "records": {
            "underlyingValue": float(spot_price),
            "expiryDates": expiry_dates_nse,
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
        cred, login = _get_credentials()
        client = FivePaisaClient(cred=cred)

        # TOTP-based login for automated access
        # Generate current 6-digit TOTP from secret
        totp_code = _generate_totp(login["TOTP_SECRET"])
        client.get_totp_session(
            login["CLIENT_CODE"],
            totp_code,
            login["PIN"]
        )

        # Fetch and transform (API provides expiry list)
        return _transform_5paisa_to_nse_format(client, NUM_EXPIRIES)

    except FetchError:
        raise
    except Exception as exc:
        raise FetchError(f"5paisa API error: {exc}")
