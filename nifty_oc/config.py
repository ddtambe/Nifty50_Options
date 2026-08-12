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
# label -> snapshots-ago (5-min cadence). Windows capped at 5hr: a 6h15m NSE
# session cannot fire a 6hr/7hr window usefully. Per-day only — detect_brewing
# reads a single day's timeline, so lookback never crosses into a prior day.
# Coupled to the Actions cron (*/5): 30 min = 6 snapshots, 5 hr = 60. Changing
# the cron REQUIRES rescaling these or brewing look-back silently shrinks.
SURGE_WINDOWS = {
    "30min": 6, "1hr": 12,
    "2hr": 24, "3hr": 36, "4hr": 48, "5hr": 60,
}

# --- Moneyness comparison panel (paper F1: S/K band for ATM) ---
MONEYNESS_ATM_LOW = 0.98
MONEYNESS_ATM_HIGH = 1.02

MARKET_OPEN = (9, 15)   # IST hh, mm
MARKET_CLOSE = (15, 30)  # IST hh, mm

DATA_DIR = "data"
DOCS_DIR = "docs"
