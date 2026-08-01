"""Market-hours guard. `now_ist` must already be IST."""
from datetime import time
from nifty_oc.config import MARKET_OPEN, MARKET_CLOSE


def is_market_hours(now_ist) -> bool:
    open_t = time(*MARKET_OPEN)
    close_t = time(*MARKET_CLOSE)
    return open_t <= now_ist.time() <= close_t
