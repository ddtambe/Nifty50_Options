"""NSE HTTP fetch with cookie priming and retry/backoff."""
import time
import requests

from nifty_oc.config import (
    OPTION_CHAIN_URL, NSE_HOME_URL, REQUEST_HEADERS,
    MAX_RETRIES, RETRY_BACKOFF_SECONDS,
)


class FetchError(Exception):
    pass


def _new_session():
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)
    return session


def fetch_option_chain(session=None, sleep=time.sleep) -> dict:
    """Return the NSE option-chain JSON, retrying on failure.

    Raises FetchError if all attempts fail.
    """
    session = session or _new_session()
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            # Prime cookies via the homepage before hitting the API.
            session.get(NSE_HOME_URL, timeout=10)
            resp = session.get(OPTION_CHAIN_URL, timeout=10)
            if resp.status_code == 200:
                payload = resp.json()
                if payload.get("records", {}).get("underlyingValue") is not None:
                    return payload
                last_error = "empty payload (no records.underlyingValue)"
            else:
                last_error = f"status {resp.status_code}"
        except Exception as exc:  # network/json errors → retry
            last_error = repr(exc)
        if attempt < MAX_RETRIES - 1:  # don't sleep after the final attempt
            sleep(RETRY_BACKOFF_SECONDS * (2 ** attempt))
    raise FetchError(f"NSE fetch failed after {MAX_RETRIES} attempts: {last_error}")
