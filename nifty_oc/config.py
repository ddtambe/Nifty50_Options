"""User-editable configuration constants."""

SYMBOL = "NIFTY"

# Strike window — edit these two to change coverage.
STRIKE_MIN = 21000
STRIKE_MAX = 30000
STRIKE_STEP = 50       # Nifty native strike gap (used for indicator math)
DISPLAY_STEP = 200     # strikes shown/stored in output files

NUM_EXPIRIES = 3       # current + next + next-to-next

# --- Brewing-move (OI-surge) signal thresholds ---
SURGE_PCT_THRESHOLD = 0.30       # min fractional OI growth over a window (30%)
SURGE_ABS_THRESHOLD = 500_000    # min absolute OI growth over a window (contracts)
# label -> snapshots-ago (15-min cadence). Windows capped at 5hr: a 6h15m NSE
# session cannot fire a 6hr/7hr window usefully. Per-day only — detect_brewing
# reads a single day's timeline, so lookback never crosses into a prior day.
SURGE_WINDOWS = {
    "30min": 2, "1hr": 4,
    "2hr": 8, "3hr": 12, "4hr": 16, "5hr": 20,
}

MARKET_OPEN = (9, 15)   # IST hh, mm
MARKET_CLOSE = (15, 30)  # IST hh, mm

DATA_DIR = "data"
DOCS_DIR = "docs"
