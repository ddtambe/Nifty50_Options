"""User-editable configuration constants."""

SYMBOL = "NIFTY"

# Strike window — edit these two to change coverage.
STRIKE_MIN = 21000
STRIKE_MAX = 30000
STRIKE_STEP = 50       # Nifty native strike gap (used for indicator math)
DISPLAY_STEP = 200     # strikes shown/stored in output files

NUM_EXPIRIES = 10       # current + next + next-to-next

MARKET_OPEN = (9, 15)   # IST hh, mm
MARKET_CLOSE = (15, 30)  # IST hh, mm

DATA_DIR = "data"
DOCS_DIR = "docs"
