"""Expiry date parsing/selection helpers."""
from datetime import datetime


def parse_nse_expiry(nse_date: str) -> str:
    """Convert NSE expiry like '31-Jul-2026' to ISO '2026-07-31'."""
    return datetime.strptime(nse_date, "%d-%b-%Y").strftime("%Y-%m-%d")


def select_expiries(nse_expiry_list: list[str], count: int) -> list[str]:
    """Return the first `count` expiries as ISO strings, preserving order."""
    return [parse_nse_expiry(d) for d in nse_expiry_list[:count]]
