"""Market-hours guard. `now_ist` must already be IST."""
import os
from datetime import time
from nifty_oc.config import MARKET_OPEN, MARKET_CLOSE


def is_market_hours(now_ist) -> bool:
    # FORCE_FETCH=true bypasses all checks (for manual workflow runs)
    if os.environ.get("FORCE_FETCH", "").lower() == "true":
        return True
    if now_ist.weekday() >= 5:      # 5=Sat, 6=Sun — NSE closed on weekends
        return False
    open_t = time(*MARKET_OPEN)
    close_t = time(*MARKET_CLOSE)
    return open_t <= now_ist.time() <= close_t
