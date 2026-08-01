# Nifty 50 Option-Chain Direction Tool — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fetch NSE Nifty option-chain data every ~15 min via GitHub Actions, compute direction indicators (buildup/unwinding, PCR, Max Pain, support/resistance), commit CSV + JSON to a public repo, and serve a live Plotly.js dashboard on GitHub Pages.

**Architecture:** A stateless Python job runs on a GitHub Actions cron schedule (guarded to IST market hours). Pure indicator functions are isolated in `indicators.py` and unit-tested; `fetcher.py` isolates NSE HTTP quirks; `writer.py` handles all CSV/JSON output. A static client-side `docs/` web app reads the committed JSON and renders charts. No local machine, no external credentials, no backend.

**Tech Stack:** Python 3.11, `requests`, `pandas`, `pytest`; Plotly.js (CDN) + vanilla JS/HTML/CSS; GitHub Actions (cron + `GITHUB_TOKEN` commit); GitHub Pages (serve `/docs`).

## Global Constraints

- Python version floor: **3.11**.
- Dependencies limited to: **requests, pandas** (runtime) and **pytest** (test). No matplotlib, no Google/gspread libraries.
- Symbol: **NIFTY**. Endpoint: `https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY`.
- Strike range hardcoded and user-editable: **STRIKE_MIN=21000, STRIKE_MAX=30000, STRIKE_STEP=50, DISPLAY_STEP=200**.
- Indicators (PCR, Max Pain, support/resistance) computed on **all 50-step strikes**; storage/display use **200-step strikes only**.
- Market hours guard: **09:15–15:30 IST**; extra closing snapshots near **15:25** and **15:30 IST**.
- Expiries per cycle: **current + next + next-to-next** (3).
- Timestamps stored as **real fetch time** in IST, format `YYYY-MM-DD HH:MM`; dates `YYYY-MM-DD`.
- `change-in-OI` stored as plain signed integer (no leading `+`).
- Repo visibility: **public**. Dashboard is static/client-side only (read-only).
- Buildup labels: `Long Buildup`, `Short Buildup`, `Short Covering`, `Long Unwinding`, `N/A` (first snapshot of day).
- A blocked/failed fetch must **exit 0** (non-fatal) so the workflow stays green and the next cycle retries.
- **Web dashboard security:** the browser code must NEVER use `innerHTML` with data values. Build DOM with `createElement` + `textContent`. (An XSS-safe rule even though the JSON is repo-controlled.)

---

### Task 1: Project scaffold, config, and expiry-date helpers

**Files:**
- Create: `requirements.txt`
- Create: `nifty_oc/__init__.py`
- Create: `nifty_oc/config.py`
- Create: `nifty_oc/dates.py`
- Create: `tests/__init__.py`
- Create: `tests/test_dates.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `config.py` module-level constants: `SYMBOL:str`, `OPTION_CHAIN_URL:str`, `NSE_HOME_URL:str`, `STRIKE_MIN:int`, `STRIKE_MAX:int`, `STRIKE_STEP:int`, `DISPLAY_STEP:int`, `NUM_EXPIRIES:int`, `MARKET_OPEN:tuple[int,int]` (=(9,15)), `MARKET_CLOSE:tuple[int,int]` (=(15,30)), `DATA_DIR:str` (="data"), `DOCS_DIR:str` (="docs"), `REQUEST_HEADERS:dict`, `MAX_RETRIES:int`, `RETRY_BACKOFF_SECONDS:float`.
  - `dates.py`:
    - `parse_nse_expiry(nse_date: str) -> str` — convert NSE `"31-Jul-2026"` to ISO `"2026-07-31"`.
    - `select_expiries(nse_expiry_list: list[str], count: int) -> list[str]` — return the first `count` expiries as ISO strings, preserving NSE order.

- [ ] **Step 1: Write `requirements.txt`**

```
requests>=2.31
pandas>=2.0
pytest>=8.0
```

- [ ] **Step 2: Create empty package markers**

Create `nifty_oc/__init__.py` (empty) and `tests/__init__.py` (empty).

- [ ] **Step 3: Write `nifty_oc/config.py`**

```python
"""User-editable configuration constants."""

SYMBOL = "NIFTY"
OPTION_CHAIN_URL = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
NSE_HOME_URL = "https://www.nseindia.com"

# Strike window — edit these two to change coverage.
STRIKE_MIN = 21000
STRIKE_MAX = 30000
STRIKE_STEP = 50       # Nifty native strike gap (used for indicator math)
DISPLAY_STEP = 200     # strikes shown/stored in output files

NUM_EXPIRIES = 3       # current + next + next-to-next

MARKET_OPEN = (9, 15)   # IST hh, mm
MARKET_CLOSE = (15, 30)  # IST hh, mm

DATA_DIR = "data"
DOCS_DIR = "docs"

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/option-chain",
}

MAX_RETRIES = 4
RETRY_BACKOFF_SECONDS = 2.0
```

- [ ] **Step 4: Write the failing test for `dates.py`**

```python
# tests/test_dates.py
from nifty_oc.dates import parse_nse_expiry, select_expiries


def test_parse_nse_expiry_converts_to_iso():
    assert parse_nse_expiry("31-Jul-2026") == "2026-07-31"
    assert parse_nse_expiry("07-Aug-2026") == "2026-08-07"


def test_select_expiries_returns_first_n_as_iso():
    raw = ["31-Jul-2026", "07-Aug-2026", "14-Aug-2026", "28-Aug-2026"]
    assert select_expiries(raw, 3) == ["2026-07-31", "2026-08-07", "2026-08-14"]


def test_select_expiries_clamps_when_fewer_available():
    raw = ["31-Jul-2026", "07-Aug-2026"]
    assert select_expiries(raw, 3) == ["2026-07-31", "2026-08-07"]
```

- [ ] **Step 5: Run test to verify it fails**

Run: `pytest tests/test_dates.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nifty_oc.dates'`.

- [ ] **Step 6: Write `nifty_oc/dates.py`**

```python
"""Expiry date parsing/selection helpers."""
from datetime import datetime


def parse_nse_expiry(nse_date: str) -> str:
    """Convert NSE expiry like '31-Jul-2026' to ISO '2026-07-31'."""
    return datetime.strptime(nse_date, "%d-%b-%Y").strftime("%Y-%m-%d")


def select_expiries(nse_expiry_list: list[str], count: int) -> list[str]:
    """Return the first `count` expiries as ISO strings, preserving order."""
    return [parse_nse_expiry(d) for d in nse_expiry_list[:count]]
```

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest tests/test_dates.py -v`
Expected: PASS (3 tests).

- [ ] **Step 8: Commit**

```bash
git add requirements.txt nifty_oc/__init__.py nifty_oc/config.py nifty_oc/dates.py tests/__init__.py tests/test_dates.py
git commit -m "feat: project scaffold, config constants, expiry-date helpers"
```

---

### Task 2: Indicator functions (the brains) — pure and fully unit-tested

**Files:**
- Create: `nifty_oc/indicators.py`
- Test: `tests/test_indicators.py`

**Interfaces:**
- Consumes: `config` constants (`STRIKE_STEP`, `DISPLAY_STEP`).
- Produces (all pure functions; a "leg" dict is `{"oi": int, "chg_oi": int, "ltp": float, "iv": float, "volume": int}`; a "row" dict is `{"strike": int, "ce": leg, "pe": leg}`):
  - `classify_buildup(chg_ltp: float, chg_oi: int) -> str` — one of the 5 labels.
  - `pcr(rows: list[dict]) -> float` — Σ PE OI / Σ CE OI (rounded to 2 dp); returns `0.0` if CE total is 0.
  - `max_pain(rows: list[dict]) -> int` — strike minimizing total writer payout.
  - `support(rows: list[dict]) -> int` — strike with highest PE OI.
  - `resistance(rows: list[dict]) -> int` — strike with highest CE OI.
  - `zone_200(strike: int) -> str` — e.g. `24800 -> "24800-25000"` (lower bound = floor to 200, upper = +200).
  - `verdict(pcr_value: float, rows: list[dict], atm: int) -> str` — "Leaning Bullish" / "Leaning Bearish" / "Rangebound".
  - `display_strikes(rows: list[dict], step: int) -> list[dict]` — filter rows to strikes divisible by `step`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_indicators.py
from nifty_oc.indicators import (
    classify_buildup, pcr, max_pain, support, resistance,
    zone_200, verdict, display_strikes,
)


def leg(oi, chg_oi, ltp):
    return {"oi": oi, "chg_oi": chg_oi, "ltp": ltp, "iv": 12.0, "volume": 100}


def row(strike, ce_oi, ce_chg, ce_ltp, pe_oi, pe_chg, pe_ltp):
    return {"strike": strike, "ce": leg(ce_oi, ce_chg, ce_ltp),
            "pe": leg(pe_oi, pe_chg, pe_ltp)}


def test_classify_buildup_four_quadrants():
    assert classify_buildup(1.0, 100) == "Long Buildup"      # price up, OI up
    assert classify_buildup(-1.0, 100) == "Short Buildup"    # price down, OI up
    assert classify_buildup(1.0, -100) == "Short Covering"   # price up, OI down
    assert classify_buildup(-1.0, -100) == "Long Unwinding"  # price down, OI down


def test_classify_buildup_flat_is_na():
    assert classify_buildup(0.0, 0) == "N/A"


def test_pcr_basic():
    rows = [row(24800, 100, 0, 10, 150, 0, 10),
            row(24900, 100, 0, 10, 50, 0, 10)]
    # PE total 200 / CE total 200 = 1.0
    assert pcr(rows) == 1.0


def test_pcr_zero_ce_returns_zero():
    rows = [row(24800, 0, 0, 10, 150, 0, 10)]
    assert pcr(rows) == 0.0


def test_max_pain_picks_min_payout_strike():
    # Heavy OI concentrated so pain sits at 24800.
    rows = [
        row(24700, 10, 0, 0, 500, 0, 0),
        row(24800, 300, 0, 0, 300, 0, 0),
        row(24900, 500, 0, 0, 10, 0, 0),
    ]
    assert max_pain(rows) == 24800


def test_support_is_highest_pe_oi_strike():
    rows = [row(24700, 100, 0, 0, 900, 0, 0),
            row(24800, 100, 0, 0, 200, 0, 0)]
    assert support(rows) == 24700


def test_resistance_is_highest_ce_oi_strike():
    rows = [row(25000, 900, 0, 0, 100, 0, 0),
            row(24800, 200, 0, 0, 100, 0, 0)]
    assert resistance(rows) == 25000


def test_zone_200():
    assert zone_200(24800) == "24800-25000"
    assert zone_200(24900) == "24800-25000"
    assert zone_200(25000) == "25000-25200"


def test_verdict_bullish_when_pcr_high():
    rows = [row(24800, 100, 0, 0, 300, 0, 0)]
    assert verdict(1.4, rows, 24800) == "Leaning Bullish"


def test_verdict_bearish_when_pcr_low():
    rows = [row(24800, 300, 0, 0, 100, 0, 0)]
    assert verdict(0.6, rows, 24800) == "Leaning Bearish"


def test_verdict_rangebound_when_pcr_neutral():
    rows = [row(24800, 100, 0, 0, 100, 0, 0)]
    assert verdict(1.0, rows, 24800) == "Rangebound"


def test_display_strikes_keeps_only_step_multiples():
    rows = [row(24800, 1, 0, 0, 1, 0, 0),
            row(24850, 1, 0, 0, 1, 0, 0),
            row(25000, 1, 0, 0, 1, 0, 0)]
    kept = [r["strike"] for r in display_strikes(rows, 200)]
    assert kept == [24800, 25000]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_indicators.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nifty_oc.indicators'`.

- [ ] **Step 3: Write `nifty_oc/indicators.py`**

```python
"""Pure indicator functions. No I/O, no globals mutated."""

# PCR thresholds for the verdict.
_BULLISH_PCR = 1.2
_BEARISH_PCR = 0.8


def classify_buildup(chg_ltp: float, chg_oi: int) -> str:
    """Standard 4-quadrant buildup classification from ΔLTP vs ΔOI."""
    if chg_ltp == 0 and chg_oi == 0:
        return "N/A"
    if chg_oi > 0:
        return "Long Buildup" if chg_ltp > 0 else "Short Buildup"
    if chg_oi < 0:
        return "Short Covering" if chg_ltp > 0 else "Long Unwinding"
    return "N/A"


def pcr(rows: list[dict]) -> float:
    ce_total = sum(r["ce"]["oi"] for r in rows)
    pe_total = sum(r["pe"]["oi"] for r in rows)
    if ce_total == 0:
        return 0.0
    return round(pe_total / ce_total, 2)


def max_pain(rows: list[dict]) -> int:
    """Strike where total writer payout (CE + PE) is minimized at expiry."""
    strikes = sorted(r["strike"] for r in rows)
    best_strike, best_pain = strikes[0], None
    for expiry_price in strikes:
        pain = 0
        for r in rows:
            k = r["strike"]
            if expiry_price > k:  # ITM calls pay out
                pain += (expiry_price - k) * r["ce"]["oi"]
            if expiry_price < k:  # ITM puts pay out
                pain += (k - expiry_price) * r["pe"]["oi"]
        if best_pain is None or pain < best_pain:
            best_pain, best_strike = pain, expiry_price
    return best_strike


def support(rows: list[dict]) -> int:
    return max(rows, key=lambda r: r["pe"]["oi"])["strike"]


def resistance(rows: list[dict]) -> int:
    return max(rows, key=lambda r: r["ce"]["oi"])["strike"]


def zone_200(strike: int) -> str:
    lower = (strike // 200) * 200
    return f"{lower}-{lower + 200}"


def verdict(pcr_value: float, rows: list[dict], atm: int) -> str:
    if pcr_value >= _BULLISH_PCR:
        return "Leaning Bullish"
    if pcr_value <= _BEARISH_PCR and pcr_value > 0:
        return "Leaning Bearish"
    return "Rangebound"


def display_strikes(rows: list[dict], step: int) -> list[dict]:
    return [r for r in rows if r["strike"] % step == 0]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_indicators.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add nifty_oc/indicators.py tests/test_indicators.py
git commit -m "feat: pure indicator functions (buildup, PCR, max pain, S/R, verdict)"
```

---

### Task 3: NSE parsing + market-hours guard (pure, testable slices of fetch)

**Files:**
- Create: `nifty_oc/parse.py`
- Create: `nifty_oc/clock.py`
- Test: `tests/test_parse.py`
- Test: `tests/test_clock.py`
- Create: `tests/fixtures/sample_chain.json`

**Interfaces:**
- Consumes: `config` (`STRIKE_MIN`, `STRIKE_MAX`, `NUM_EXPIRIES`), `dates.select_expiries`.
- Produces:
  - `parse.py`:
    - `extract_spot(payload: dict) -> float` — `payload["records"]["underlyingValue"]`.
    - `extract_expiries(payload: dict, count: int) -> list[str]` — ISO expiries via `select_expiries`.
    - `rows_for_expiry(payload: dict, iso_expiry: str, strike_min: int, strike_max: int) -> list[dict]` — returns sorted list of row dicts (shape from Task 2) for one expiry, filtered to `[strike_min, strike_max]`; missing CE/PE legs default to zeros.
    - `nearest_atm(spot: float, step: int) -> int` — round spot to nearest `step`.
  - `clock.py`:
    - `is_market_hours(now_ist) -> bool` — True iff `MARKET_OPEN <= now_ist.time() <= MARKET_CLOSE`. `now_ist` is a `datetime`.

- [ ] **Step 1: Create the JSON fixture**

```json
{
  "records": {
    "underlyingValue": 24812.35,
    "expiryDates": ["31-Jul-2026", "07-Aug-2026", "14-Aug-2026", "28-Aug-2026"],
    "data": [
      {"strikePrice": 20000, "expiryDate": "31-Jul-2026",
       "CE": {"openInterest": 5, "changeinOpenInterest": 1, "lastPrice": 4800.0, "impliedVolatility": 20.0, "totalTradedVolume": 3},
       "PE": {"openInterest": 7, "changeinOpenInterest": 2, "lastPrice": 0.5, "impliedVolatility": 30.0, "totalTradedVolume": 4}},
      {"strikePrice": 24800, "expiryDate": "31-Jul-2026",
       "CE": {"openInterest": 342100, "changeinOpenInterest": 22400, "lastPrice": 74.2, "impliedVolatility": 11.2, "totalTradedVolume": 152300},
       "PE": {"openInterest": 288900, "changeinOpenInterest": -5100, "lastPrice": 78.9, "impliedVolatility": 12.1, "totalTradedVolume": 61200}},
      {"strikePrice": 24900, "expiryDate": "31-Jul-2026",
       "CE": {"openInterest": 289500, "changeinOpenInterest": 41200, "lastPrice": 38.7, "impliedVolatility": 11.6, "totalTradedVolume": 210800},
       "PE": {"openInterest": 178200, "changeinOpenInterest": -12800, "lastPrice": 142.3, "impliedVolatility": 12.6, "totalTradedVolume": 33400}},
      {"strikePrice": 24800, "expiryDate": "07-Aug-2026",
       "CE": {"openInterest": 120000, "changeinOpenInterest": 3000, "lastPrice": 120.0, "impliedVolatility": 12.0, "totalTradedVolume": 5000},
       "PE": {"openInterest": 130000, "changeinOpenInterest": 4000, "lastPrice": 118.0, "impliedVolatility": 12.5, "totalTradedVolume": 6000}},
      {"strikePrice": 31000, "expiryDate": "31-Jul-2026",
       "CE": {"openInterest": 10, "changeinOpenInterest": 1, "lastPrice": 0.5, "impliedVolatility": 25.0, "totalTradedVolume": 2},
       "PE": {"openInterest": 12, "changeinOpenInterest": 1, "lastPrice": 6200.0, "impliedVolatility": 35.0, "totalTradedVolume": 3}}
    ]
  }
}
```

- [ ] **Step 2: Write the failing tests for `parse.py`**

```python
# tests/test_parse.py
import json
from pathlib import Path
from nifty_oc.parse import (
    extract_spot, extract_expiries, rows_for_expiry, nearest_atm,
)

PAYLOAD = json.loads((Path(__file__).parent / "fixtures" / "sample_chain.json").read_text())


def test_extract_spot():
    assert extract_spot(PAYLOAD) == 24812.35


def test_extract_expiries_first_three():
    assert extract_expiries(PAYLOAD, 3) == ["2026-07-31", "2026-08-07", "2026-08-14"]


def test_rows_for_expiry_filters_by_range_and_expiry():
    rows = rows_for_expiry(PAYLOAD, "2026-07-31", 21000, 30000)
    strikes = [r["strike"] for r in rows]
    # 20000 and 31000 are outside range; 24800/07-Aug belongs to another expiry.
    assert strikes == [24800, 24900]
    assert rows[0]["ce"]["oi"] == 342100
    assert rows[0]["pe"]["chg_oi"] == -5100


def test_rows_for_expiry_sorted_ascending():
    rows = rows_for_expiry(PAYLOAD, "2026-07-31", 21000, 30000)
    assert rows == sorted(rows, key=lambda r: r["strike"])


def test_nearest_atm_rounds_to_step():
    assert nearest_atm(24812.35, 50) == 24800
    assert nearest_atm(24826.0, 50) == 24850
```

- [ ] **Step 3: Run to verify fail**

Run: `pytest tests/test_parse.py -v`
Expected: FAIL — `No module named 'nifty_oc.parse'`.

- [ ] **Step 4: Write `nifty_oc/parse.py`**

```python
"""Turn raw NSE payload into clean row dicts. Pure functions."""
from nifty_oc.dates import parse_nse_expiry, select_expiries


def extract_spot(payload: dict) -> float:
    return payload["records"]["underlyingValue"]


def extract_expiries(payload: dict, count: int) -> list[str]:
    return select_expiries(payload["records"]["expiryDates"], count)


def _leg(node: dict | None) -> dict:
    if not node:
        return {"oi": 0, "chg_oi": 0, "ltp": 0.0, "iv": 0.0, "volume": 0}
    return {
        "oi": node.get("openInterest", 0),
        "chg_oi": node.get("changeinOpenInterest", 0),
        "ltp": node.get("lastPrice", 0.0),
        "iv": node.get("impliedVolatility", 0.0),
        "volume": node.get("totalTradedVolume", 0),
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
```

- [ ] **Step 5: Write the failing tests for `clock.py`**

```python
# tests/test_clock.py
from datetime import datetime
from nifty_oc.clock import is_market_hours


def test_inside_market_hours():
    assert is_market_hours(datetime(2026, 7, 29, 10, 0)) is True
    assert is_market_hours(datetime(2026, 7, 29, 9, 15)) is True
    assert is_market_hours(datetime(2026, 7, 29, 15, 30)) is True


def test_outside_market_hours():
    assert is_market_hours(datetime(2026, 7, 29, 9, 0)) is False
    assert is_market_hours(datetime(2026, 7, 29, 15, 31)) is False
    assert is_market_hours(datetime(2026, 7, 29, 18, 0)) is False
```

- [ ] **Step 6: Run to verify fail**

Run: `pytest tests/test_clock.py -v`
Expected: FAIL — `No module named 'nifty_oc.clock'`.

- [ ] **Step 7: Write `nifty_oc/clock.py`**

```python
"""Market-hours guard. `now_ist` must already be IST."""
from datetime import time
from nifty_oc.config import MARKET_OPEN, MARKET_CLOSE


def is_market_hours(now_ist) -> bool:
    open_t = time(*MARKET_OPEN)
    close_t = time(*MARKET_CLOSE)
    return open_t <= now_ist.time() <= close_t
```

- [ ] **Step 8: Run both test files to verify pass**

Run: `pytest tests/test_parse.py tests/test_clock.py -v`
Expected: PASS (all tests).

- [ ] **Step 9: Commit**

```bash
git add nifty_oc/parse.py nifty_oc/clock.py tests/test_parse.py tests/test_clock.py tests/fixtures/sample_chain.json
git commit -m "feat: NSE payload parsing + IST market-hours guard"
```

---

### Task 4: NSE fetcher (cookie priming + retry/backoff)

**Files:**
- Create: `nifty_oc/fetcher.py`
- Test: `tests/test_fetcher.py`

**Interfaces:**
- Consumes: `config` (`OPTION_CHAIN_URL`, `NSE_HOME_URL`, `REQUEST_HEADERS`, `MAX_RETRIES`, `RETRY_BACKOFF_SECONDS`).
- Produces:
  - `fetch_option_chain(session=None, sleep=time.sleep) -> dict` — primes cookies via `NSE_HOME_URL`, GETs the option-chain JSON, retries up to `MAX_RETRIES` with backoff on non-200/exception/empty payload. Raises `FetchError` if all attempts fail. `session` and `sleep` are injectable for tests.
  - `class FetchError(Exception)`.

- [ ] **Step 1: Write the failing tests (with a fake session, no network)**

```python
# tests/test_fetcher.py
import pytest
from nifty_oc.fetcher import fetch_option_chain, FetchError


class FakeResp:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}

    def json(self):
        return self._json


class FakeSession:
    def __init__(self, home_status, api_responses):
        self.headers = {}
        self._home_status = home_status
        self._api_responses = list(api_responses)
        self.get_calls = []

    def get(self, url, timeout=None):
        self.get_calls.append(url)
        if "option-chain-indices" in url:
            return self._api_responses.pop(0)
        return FakeResp(self._home_status)  # homepage prime


def test_fetch_succeeds_first_try():
    good = FakeResp(200, {"records": {"underlyingValue": 24800, "expiryDates": [], "data": []}})
    session = FakeSession(home_status=200, api_responses=[good])
    payload = fetch_option_chain(session=session, sleep=lambda s: None)
    assert payload["records"]["underlyingValue"] == 24800


def test_fetch_retries_then_succeeds():
    bad = FakeResp(401, {})
    good = FakeResp(200, {"records": {"underlyingValue": 1, "expiryDates": [], "data": []}})
    session = FakeSession(home_status=200, api_responses=[bad, good])
    payload = fetch_option_chain(session=session, sleep=lambda s: None)
    assert payload["records"]["underlyingValue"] == 1


def test_fetch_raises_after_max_retries():
    bad = FakeResp(429, {})
    session = FakeSession(home_status=200, api_responses=[bad, bad, bad, bad, bad, bad])
    with pytest.raises(FetchError):
        fetch_option_chain(session=session, sleep=lambda s: None)


def test_fetch_treats_empty_payload_as_failure():
    empty = FakeResp(200, {})  # no "records"
    good = FakeResp(200, {"records": {"underlyingValue": 2, "expiryDates": [], "data": []}})
    session = FakeSession(home_status=200, api_responses=[empty, good])
    payload = fetch_option_chain(session=session, sleep=lambda s: None)
    assert payload["records"]["underlyingValue"] == 2
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_fetcher.py -v`
Expected: FAIL — `No module named 'nifty_oc.fetcher'`.

- [ ] **Step 3: Write `nifty_oc/fetcher.py`**

```python
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
        sleep(RETRY_BACKOFF_SECONDS * (2 ** attempt))
    raise FetchError(f"NSE fetch failed after {MAX_RETRIES} attempts: {last_error}")
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_fetcher.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add nifty_oc/fetcher.py tests/test_fetcher.py
git commit -m "feat: NSE fetcher with cookie priming and retry/backoff"
```

---

### Task 5: Snapshot builder — assemble one cycle's computed result

**Files:**
- Create: `nifty_oc/snapshot.py`
- Test: `tests/test_snapshot.py`

**Interfaces:**
- Consumes: `parse` (`extract_spot`, `extract_expiries`, `rows_for_expiry`, `nearest_atm`), `indicators` (all), `config` (`STRIKE_MIN`, `STRIKE_MAX`, `STRIKE_STEP`, `DISPLAY_STEP`, `NUM_EXPIRIES`).
- Produces:
  - `build_snapshot(payload: dict, timestamp_ist: str, prev_ltp: dict) -> dict` — returns
    `{"timestamp": str, "trade_date": str, "spot": float, "atm": int, "expiries": [ExpiryResult, ...]}`
    where each `ExpiryResult` is
    `{"expiry": str, "pcr": float, "max_pain": int, "support": int, "resistance": int, "ce_oi_total": int, "pe_oi_total": int, "verdict": str, "display_rows": [DisplayRow, ...]}`
    and each `DisplayRow` is
    `{"strike": int, "ce_oi", "ce_chg_oi", "ce_ltp", "ce_iv", "ce_volume", "pe_oi", "pe_chg_oi", "pe_ltp", "pe_iv", "pe_volume", "ce_buildup", "pe_buildup", "zone_200pt"}`.
  - `prev_ltp` maps `(expiry, strike, "CE"/"PE") -> last LTP`; empty dict means first snapshot → buildup `N/A`.
  - `ltp_index(snapshot: dict) -> dict` — build the `prev_ltp` map from a snapshot for the next cycle.
  - `trade_date_of(timestamp_ist: str) -> str` — first 10 chars (the date).

**Note on buildup:** indicators compute buildup from ΔLTP vs ΔOI. ΔOI comes straight from NSE (`chg_oi`). ΔLTP is `current_ltp - prev_ltp` using `prev_ltp`; if the key is missing (first snapshot), pass `chg_ltp=0` **and** `chg_oi=0` so the label is `N/A`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_snapshot.py
import json
from pathlib import Path
from nifty_oc.snapshot import build_snapshot, ltp_index, trade_date_of

PAYLOAD = json.loads((Path(__file__).parent / "fixtures" / "sample_chain.json").read_text())


def test_trade_date_of():
    assert trade_date_of("2026-07-29 09:30") == "2026-07-29"


def test_build_snapshot_shape_and_values():
    snap = build_snapshot(PAYLOAD, "2026-07-29 09:30", prev_ltp={})
    assert snap["spot"] == 24812.35
    assert snap["atm"] == 24800
    assert snap["trade_date"] == "2026-07-29"
    # 3 expiries requested; fixture has 07-Aug data too.
    expiries = [e["expiry"] for e in snap["expiries"]]
    assert expiries[:2] == ["2026-07-31", "2026-08-07"]


def test_build_snapshot_first_cycle_buildup_is_na():
    snap = build_snapshot(PAYLOAD, "2026-07-29 09:30", prev_ltp={})
    first = snap["expiries"][0]
    for dr in first["display_rows"]:
        assert dr["ce_buildup"] == "N/A"
        assert dr["pe_buildup"] == "N/A"


def test_build_snapshot_uses_prev_ltp_for_buildup():
    # Prime prev LTP lower than current for CE 24800 (74.2), OI change +22400 → Long Buildup.
    prev = {("2026-07-31", 24800, "CE"): 70.0}
    snap = build_snapshot(PAYLOAD, "2026-07-29 09:45", prev_ltp=prev)
    row = next(r for r in snap["expiries"][0]["display_rows"] if r["strike"] == 24800)
    assert row["ce_buildup"] == "Long Buildup"


def test_ltp_index_roundtrip():
    snap = build_snapshot(PAYLOAD, "2026-07-29 09:30", prev_ltp={})
    idx = ltp_index(snap)
    assert idx[("2026-07-31", 24800, "CE")] == 74.2
    assert idx[("2026-07-31", 24800, "PE")] == 78.9


def test_display_rows_are_200_step_only():
    snap = build_snapshot(PAYLOAD, "2026-07-29 09:30", prev_ltp={})
    strikes = [r["strike"] for r in snap["expiries"][0]["display_rows"]]
    # 24900 is not a 200-multiple → excluded from display; 24800 kept.
    assert 24800 in strikes
    assert 24900 not in strikes
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_snapshot.py -v`
Expected: FAIL — `No module named 'nifty_oc.snapshot'`.

- [ ] **Step 3: Write `nifty_oc/snapshot.py`**

```python
"""Assemble one cycle's fully-computed snapshot from a raw payload."""
from nifty_oc import indicators
from nifty_oc.config import (
    STRIKE_MIN, STRIKE_MAX, STRIKE_STEP, DISPLAY_STEP, NUM_EXPIRIES,
)
from nifty_oc.parse import (
    extract_spot, extract_expiries, rows_for_expiry, nearest_atm,
)


def trade_date_of(timestamp_ist: str) -> str:
    return timestamp_ist[:10]


def _buildup_for(leg: dict, key, prev_ltp: dict) -> str:
    if key not in prev_ltp:
        return indicators.classify_buildup(0.0, 0)  # N/A on first sighting
    chg_ltp = leg["ltp"] - prev_ltp[key]
    return indicators.classify_buildup(chg_ltp, leg["chg_oi"])


def _display_row(r: dict, expiry: str, prev_ltp: dict) -> dict:
    ce, pe = r["ce"], r["pe"]
    strike = r["strike"]
    return {
        "strike": strike,
        "ce_oi": ce["oi"], "ce_chg_oi": ce["chg_oi"], "ce_ltp": ce["ltp"],
        "ce_iv": ce["iv"], "ce_volume": ce["volume"],
        "pe_oi": pe["oi"], "pe_chg_oi": pe["chg_oi"], "pe_ltp": pe["ltp"],
        "pe_iv": pe["iv"], "pe_volume": pe["volume"],
        "ce_buildup": _buildup_for(ce, (expiry, strike, "CE"), prev_ltp),
        "pe_buildup": _buildup_for(pe, (expiry, strike, "PE"), prev_ltp),
        "zone_200pt": indicators.zone_200(strike),
    }


def build_snapshot(payload: dict, timestamp_ist: str, prev_ltp: dict) -> dict:
    spot = extract_spot(payload)
    atm = nearest_atm(spot, STRIKE_STEP)
    expiries_iso = extract_expiries(payload, NUM_EXPIRIES)

    results = []
    for expiry in expiries_iso:
        rows = rows_for_expiry(payload, expiry, STRIKE_MIN, STRIKE_MAX)
        if not rows:
            continue
        disp = indicators.display_strikes(rows, DISPLAY_STEP)
        results.append({
            "expiry": expiry,
            "pcr": indicators.pcr(rows),
            "max_pain": indicators.max_pain(rows),
            "support": indicators.support(rows),
            "resistance": indicators.resistance(rows),
            "ce_oi_total": sum(r["ce"]["oi"] for r in rows),
            "pe_oi_total": sum(r["pe"]["oi"] for r in rows),
            "verdict": indicators.verdict(indicators.pcr(rows), rows, atm),
            "display_rows": [_display_row(r, expiry, prev_ltp) for r in disp],
        })

    return {
        "timestamp": timestamp_ist,
        "trade_date": trade_date_of(timestamp_ist),
        "spot": spot,
        "atm": atm,
        "expiries": results,
    }


def ltp_index(snapshot: dict) -> dict:
    """Map (expiry, strike, leg) -> LTP for use as next cycle's prev_ltp."""
    idx = {}
    for e in snapshot["expiries"]:
        for r in e["display_rows"]:
            idx[(e["expiry"], r["strike"], "CE")] = r["ce_ltp"]
            idx[(e["expiry"], r["strike"], "PE")] = r["pe_ltp"]
    return idx
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_snapshot.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add nifty_oc/snapshot.py tests/test_snapshot.py
git commit -m "feat: snapshot builder assembling one cycle's computed result"
```

---

### Task 6: Writer — CSV append/rewrite + JSON feeds + index.json

**Files:**
- Create: `nifty_oc/writer.py`
- Test: `tests/test_writer.py`

**Interfaces:**
- Consumes: `config` (`DATA_DIR`), a snapshot dict (Task 5).
- Produces (all take an explicit `data_dir` arg so tests use `tmp_path`):
  - `write_summary(snapshot: dict, data_dir: str) -> None` — append one row per expiry to `<data_dir>/<trade_date>/summary.csv` (header written once).
  - `write_raw(snapshot: dict, data_dir: str) -> None` — append display rows per expiry to `<data_dir>/<trade_date>/<expiry>_raw.csv`.
  - `write_buildup(snapshot: dict, data_dir: str) -> None` — overwrite `<data_dir>/<trade_date>/<expiry>_buildup.csv` with latest display rows.
  - `write_json_feed(snapshot: dict, data_dir: str) -> None` — write `<data_dir>/<trade_date>/<expiry>.json` per expiry (shape from spec §8: `meta`, `timeline` appended, `strikes` latest). Timeline accumulates across the day by reading the existing feed if present.
  - `write_index(data_dir: str) -> None` — scan `<data_dir>/*/` and write `<data_dir>/index.json` = `{"days": [{"trade_date":..., "expiries":[...]}]}`.
  - `load_prev_ltp(trade_date: str, data_dir: str) -> dict` — rebuild `prev_ltp` from the last rows of each `<expiry>_raw.csv`; empty dict if none.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_writer.py
import csv
import json
from pathlib import Path
from nifty_oc import writer


def sample_snapshot():
    return {
        "timestamp": "2026-07-29 09:30", "trade_date": "2026-07-29",
        "spot": 24812.35, "atm": 24800,
        "expiries": [{
            "expiry": "2026-07-31", "pcr": 1.24, "max_pain": 24700,
            "support": 24500, "resistance": 25000,
            "ce_oi_total": 4562300, "pe_oi_total": 5657250, "verdict": "Leaning Bullish",
            "display_rows": [{
                "strike": 24800, "ce_oi": 342100, "ce_chg_oi": 22400, "ce_ltp": 74.2,
                "ce_iv": 11.2, "ce_volume": 152300, "pe_oi": 288900, "pe_chg_oi": -5100,
                "pe_ltp": 78.9, "pe_iv": 12.1, "pe_volume": 61200,
                "ce_buildup": "N/A", "pe_buildup": "N/A", "zone_200pt": "24800-25000",
            }],
        }],
    }


def test_write_summary_appends_header_once(tmp_path):
    writer.write_summary(sample_snapshot(), str(tmp_path))
    writer.write_summary(sample_snapshot(), str(tmp_path))
    f = tmp_path / "2026-07-29" / "summary.csv"
    rows = list(csv.reader(f.open()))
    assert rows[0][0] == "timestamp_ist"       # one header
    assert len(rows) == 3                        # header + 2 data rows
    assert rows[1][2] == "2026-07-31"


def test_write_raw_appends(tmp_path):
    writer.write_raw(sample_snapshot(), str(tmp_path))
    writer.write_raw(sample_snapshot(), str(tmp_path))
    f = tmp_path / "2026-07-29" / "2026-07-31_raw.csv"
    rows = list(csv.reader(f.open()))
    assert rows[0][0] == "timestamp_ist"
    assert len(rows) == 3
    # chg_oi stored as plain signed integer, no leading '+'
    assert "-5100" in rows[1]


def test_write_buildup_overwrites(tmp_path):
    writer.write_buildup(sample_snapshot(), str(tmp_path))
    writer.write_buildup(sample_snapshot(), str(tmp_path))
    f = tmp_path / "2026-07-29" / "2026-07-31_buildup.csv"
    rows = list(csv.reader(f.open()))
    assert rows[0][0] == "strike"
    assert len(rows) == 2   # header + 1 row (overwritten, not appended)


def test_write_json_feed_accumulates_timeline(tmp_path):
    writer.write_json_feed(sample_snapshot(), str(tmp_path))
    snap2 = sample_snapshot()
    snap2["timestamp"] = "2026-07-29 09:45"
    writer.write_json_feed(snap2, str(tmp_path))
    feed = json.loads((tmp_path / "2026-07-29" / "2026-07-31.json").read_text())
    assert feed["meta"]["expiry"] == "2026-07-31"
    assert len(feed["timeline"]) == 2
    assert feed["strikes"][0]["strike"] == 24800


def test_write_index_lists_days_and_expiries(tmp_path):
    writer.write_json_feed(sample_snapshot(), str(tmp_path))
    writer.write_index(str(tmp_path))
    idx = json.loads((tmp_path / "index.json").read_text())
    assert idx["days"][0]["trade_date"] == "2026-07-29"
    assert "2026-07-31" in idx["days"][0]["expiries"]


def test_load_prev_ltp_reads_last_rows(tmp_path):
    writer.write_raw(sample_snapshot(), str(tmp_path))
    prev = writer.load_prev_ltp("2026-07-29", str(tmp_path))
    assert prev[("2026-07-31", 24800, "CE")] == 74.2
    assert prev[("2026-07-31", 24800, "PE")] == 78.9
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_writer.py -v`
Expected: FAIL — `No module named 'nifty_oc.writer'`.

- [ ] **Step 3: Write `nifty_oc/writer.py`**

```python
"""All file output: CSV (append/rewrite) and JSON feeds for the web app."""
import csv
import json
import os

SUMMARY_HEADER = [
    "timestamp_ist", "trade_date", "expiry", "spot", "atm", "pcr", "max_pain",
    "support", "resistance", "ce_oi_total", "pe_oi_total", "verdict",
]
RAW_HEADER = [
    "timestamp_ist", "expiry", "ce_oi", "ce_chg_oi", "ce_ltp", "ce_iv", "ce_volume",
    "strike", "pe_volume", "pe_iv", "pe_ltp", "pe_chg_oi", "pe_oi",
    "ce_buildup", "pe_buildup",
]
BUILDUP_HEADER = [
    "strike", "ce_oi", "ce_chg_oi", "ce_buildup", "pe_oi", "pe_chg_oi",
    "pe_buildup", "zone_200pt",
]


def _day_dir(data_dir: str, trade_date: str) -> str:
    path = os.path.join(data_dir, trade_date)
    os.makedirs(path, exist_ok=True)
    return path


def _append_rows(path: str, header: list, rows: list) -> None:
    exists = os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(header)
        w.writerows(rows)


def write_summary(snapshot: dict, data_dir: str) -> None:
    day = _day_dir(data_dir, snapshot["trade_date"])
    rows = [[
        snapshot["timestamp"], snapshot["trade_date"], e["expiry"], snapshot["spot"],
        snapshot["atm"], e["pcr"], e["max_pain"], e["support"], e["resistance"],
        e["ce_oi_total"], e["pe_oi_total"], e["verdict"],
    ] for e in snapshot["expiries"]]
    _append_rows(os.path.join(day, "summary.csv"), SUMMARY_HEADER, rows)


def write_raw(snapshot: dict, data_dir: str) -> None:
    day = _day_dir(data_dir, snapshot["trade_date"])
    for e in snapshot["expiries"]:
        rows = [[
            snapshot["timestamp"], e["expiry"], r["ce_oi"], r["ce_chg_oi"], r["ce_ltp"],
            r["ce_iv"], r["ce_volume"], r["strike"], r["pe_volume"], r["pe_iv"],
            r["pe_ltp"], r["pe_chg_oi"], r["pe_oi"], r["ce_buildup"], r["pe_buildup"],
        ] for r in e["display_rows"]]
        _append_rows(os.path.join(day, f"{e['expiry']}_raw.csv"), RAW_HEADER, rows)


def write_buildup(snapshot: dict, data_dir: str) -> None:
    day = _day_dir(data_dir, snapshot["trade_date"])
    for e in snapshot["expiries"]:
        path = os.path.join(day, f"{e['expiry']}_buildup.csv")
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(BUILDUP_HEADER)
            for r in e["display_rows"]:
                w.writerow([
                    r["strike"], r["ce_oi"], r["ce_chg_oi"], r["ce_buildup"],
                    r["pe_oi"], r["pe_chg_oi"], r["pe_buildup"], r["zone_200pt"],
                ])


def write_json_feed(snapshot: dict, data_dir: str) -> None:
    day = _day_dir(data_dir, snapshot["trade_date"])
    for e in snapshot["expiries"]:
        path = os.path.join(day, f"{e['expiry']}.json")
        if os.path.exists(path):
            feed = json.loads(open(path).read())
        else:
            feed = {"meta": {}, "timeline": [], "strikes": []}
        feed["meta"] = {
            "trade_date": snapshot["trade_date"], "expiry": e["expiry"],
            "updated_ist": snapshot["timestamp"],
        }
        feed["timeline"].append({
            "t": snapshot["timestamp"], "spot": snapshot["spot"],
            "pcr": e["pcr"], "max_pain": e["max_pain"],
        })
        feed["strikes"] = e["display_rows"]
        with open(path, "w") as f:
            json.dump(feed, f)


def write_index(data_dir: str) -> None:
    days = []
    if os.path.isdir(data_dir):
        for trade_date in sorted(os.listdir(data_dir)):
            day_path = os.path.join(data_dir, trade_date)
            if not os.path.isdir(day_path):
                continue
            expiries = sorted(
                fn[:-5] for fn in os.listdir(day_path)
                if fn.endswith(".json")
            )
            if expiries:
                days.append({"trade_date": trade_date, "expiries": expiries})
    with open(os.path.join(data_dir, "index.json"), "w") as f:
        json.dump({"days": days}, f)


def load_prev_ltp(trade_date: str, data_dir: str) -> dict:
    day = os.path.join(data_dir, trade_date)
    prev = {}
    if not os.path.isdir(day):
        return prev
    for fn in os.listdir(day):
        if not fn.endswith("_raw.csv"):
            continue
        with open(os.path.join(day, fn), newline="") as f:
            rows = list(csv.DictReader(f))
        for row in rows:  # later rows overwrite → last value wins
            expiry, strike = row["expiry"], int(row["strike"])
            prev[(expiry, strike, "CE")] = float(row["ce_ltp"])
            prev[(expiry, strike, "PE")] = float(row["pe_ltp"])
    return prev
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_writer.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add nifty_oc/writer.py tests/test_writer.py
git commit -m "feat: writer for CSV (summary/raw/buildup) + JSON feeds + index"
```

---

### Task 7: Orchestrator `main.py` + IST clock wiring

**Files:**
- Create: `nifty_oc/main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `clock.is_market_hours`, `fetcher.fetch_option_chain` + `FetchError`, `snapshot.build_snapshot` + `load`/`ltp_index`, `writer.*`, `config.DATA_DIR`.
- Produces:
  - `now_ist() -> datetime` — current time in IST (UTC+5:30), using `timezone(timedelta(hours=5, minutes=30))`.
  - `run(now=None, fetch=None, data_dir=None) -> int` — orchestration entrypoint (all deps injectable for tests). Returns process exit code: `0` always on the happy path AND on handled failures (blocked fetch, off-hours) so Actions stays green.
  - `main() -> None` — CLI wrapper calling `sys.exit(run())`.

**Orchestration logic (exact):**
1. `now = now or now_ist()`. If `not is_market_hours(now)`: print "outside market hours", return 0.
2. `ts = now.strftime("%Y-%m-%d %H:%M")`; `trade_date = ts[:10]`.
3. `prev = writer.load_prev_ltp(trade_date, data_dir)`.
4. `try: payload = (fetch or fetch_option_chain)()` — on `FetchError`: print error, return 0.
5. `snap = build_snapshot(payload, ts, prev)`.
6. `writer.write_summary/write_raw/write_buildup/write_json_feed(snap, data_dir)`; `writer.write_index(data_dir)`.
7. print one-line summary; return 0.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_main.py
import json
from datetime import datetime
from pathlib import Path
from nifty_oc import main

PAYLOAD = json.loads((Path(__file__).parents[0] / "fixtures" / "sample_chain.json").read_text())


def test_run_skips_outside_market_hours(tmp_path):
    code = main.run(now=datetime(2026, 7, 29, 8, 0),
                    fetch=lambda: PAYLOAD, data_dir=str(tmp_path))
    assert code == 0
    assert not (tmp_path / "2026-07-29").exists()  # nothing written


def test_run_writes_files_during_market_hours(tmp_path):
    code = main.run(now=datetime(2026, 7, 29, 9, 30),
                    fetch=lambda: PAYLOAD, data_dir=str(tmp_path))
    assert code == 0
    assert (tmp_path / "2026-07-29" / "summary.csv").exists()
    assert (tmp_path / "2026-07-29" / "2026-07-31.json").exists()
    assert (tmp_path / "index.json").exists()


def test_run_returns_zero_on_fetch_error(tmp_path):
    def boom():
        from nifty_oc.fetcher import FetchError
        raise FetchError("blocked")
    code = main.run(now=datetime(2026, 7, 29, 9, 30), fetch=boom, data_dir=str(tmp_path))
    assert code == 0  # non-fatal: Actions stays green


def test_now_ist_is_utc_plus_530():
    n = main.now_ist()
    assert n.utcoffset().total_seconds() == 5.5 * 3600
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_main.py -v`
Expected: FAIL — `No module named 'nifty_oc.main'`.

- [ ] **Step 3: Write `nifty_oc/main.py`**

```python
"""Orchestrator: guard → fetch → compute → write. Actions runs this each cycle."""
import sys
from datetime import datetime, timezone, timedelta

from nifty_oc.config import DATA_DIR
from nifty_oc.clock import is_market_hours
from nifty_oc.fetcher import fetch_option_chain, FetchError
from nifty_oc.snapshot import build_snapshot
from nifty_oc import writer

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    return datetime.now(IST)


def run(now=None, fetch=None, data_dir=None) -> int:
    now = now or now_ist()
    data_dir = data_dir or DATA_DIR
    fetch = fetch or fetch_option_chain

    if not is_market_hours(now):
        print(f"[skip] outside market hours: {now}")
        return 0

    ts = now.strftime("%Y-%m-%d %H:%M")
    trade_date = ts[:10]
    prev = writer.load_prev_ltp(trade_date, data_dir)

    try:
        payload = fetch()
    except FetchError as exc:
        print(f"[skip] fetch failed (non-fatal): {exc}")
        return 0

    snap = build_snapshot(payload, ts, prev)
    writer.write_summary(snap, data_dir)
    writer.write_raw(snap, data_dir)
    writer.write_buildup(snap, data_dir)
    writer.write_json_feed(snap, data_dir)
    writer.write_index(data_dir)

    verdicts = ", ".join(f"{e['expiry']}:{e['verdict']}" for e in snap["expiries"])
    print(f"[ok] {ts} spot={snap['spot']} | {verdicts}")
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_main.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the full suite**

Run: `pytest -v`
Expected: PASS (all tests across all files).

- [ ] **Step 6: Commit**

```bash
git add nifty_oc/main.py tests/test_main.py
git commit -m "feat: orchestrator wiring guard/fetch/compute/write"
```

---

### Task 8: GitHub Actions workflow (cron + commit)

**Files:**
- Create: `.github/workflows/fetch.yml`

**Interfaces:**
- Consumes: `python -m nifty_oc.main`, `requirements.txt`.
- Produces: a scheduled workflow that runs the fetch and commits any changed files under `data/` using `GITHUB_TOKEN`.

**Cron note:** GitHub cron is UTC. IST market hours 09:15–15:30 = **03:45–10:00 UTC**. A `*/15` cron over `3-10` UTC covers the window (the in-code guard trims the edges precisely). Extra closing snapshots 15:25 & 15:30 IST = **09:55 & 10:00 UTC** — covered by the `*/5` tail below.

- [ ] **Step 1: Write `.github/workflows/fetch.yml`**

```yaml
name: fetch-nifty-option-chain

on:
  schedule:
    # Every 15 min across the IST market window (03:45–10:00 UTC).
    - cron: "*/15 3-10 * * 1-5"
    # Fine-grained tail to capture ~15:25 & ~15:30 IST (09:55 & 10:00 UTC).
    - cron: "55,59 9 * * 1-5"
    - cron: "0 10 * * 1-5"
  workflow_dispatch: {}

permissions:
  contents: write   # allow committing data back to the repo

concurrency:
  group: fetch-nifty
  cancel-in-progress: false

jobs:
  fetch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run fetch cycle
        run: python -m nifty_oc.main

      - name: Commit data if changed
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/
          if git diff --staged --quiet; then
            echo "No data changes to commit."
          else
            git commit -m "data: option-chain snapshot $(date -u +'%Y-%m-%dT%H:%MZ')"
            git push
          fi
```

- [ ] **Step 2: Validate YAML locally**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/fetch.yml'))"`
Expected: no error (valid YAML). (If PyYAML absent: `pip install pyyaml` first.)

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/fetch.yml
git commit -m "ci: scheduled GitHub Actions workflow to fetch and commit data"
```

---

### Task 9: Web dashboard (GitHub Pages, Plotly.js) — all four views

**Files:**
- Create: `docs/index.html`
- Create: `docs/app.js`
- Create: `docs/style.css`
- Create: `docs/sample/index.json` (local preview fixture)
- Create: `docs/sample/2026-07-29/2026-07-31.json` (local preview fixture)

**Interfaces:**
- Consumes: JSON feeds from `../data/` in production; `./sample/` for local file preview.
- Produces: a static page rendering four views: strike-wise OI walls (bar), day timeline (line: spot/max_pain/pcr), buildup table (color-coded), and expiry+day switcher dropdowns.

**Data path note:** In production the page lives at `docs/` and data at `data/`, so the page fetches `../data/index.json`. For local preview without the full data tree, `app.js` falls back to `./sample/` when `../data/` 404s.

**SECURITY (must follow):** No `innerHTML` anywhere. All dynamic content is inserted via `createElement` + `textContent`. Dropdowns and the buildup table are built with DOM APIs only. This is enforced by a security hook and is a real XSS-avoidance rule.

- [ ] **Step 1: Write `docs/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Nifty Option-Chain Dashboard</title>
  <link rel="stylesheet" href="style.css" />
  <script src="https://cdn.plot.ly/plotly-2.32.0.min.js" charset="utf-8"></script>
</head>
<body>
  <header>
    <h1>Nifty 50 Option-Chain Direction</h1>
    <div class="controls">
      <label>Day <select id="daySelect"></select></label>
      <label>Expiry <select id="expirySelect"></select></label>
      <span id="updated"></span>
    </div>
  </header>
  <main>
    <section><h2>Support / Resistance Walls (CE vs PE OI)</h2><div id="wallsChart"></div></section>
    <section><h2>Day Timeline — Spot vs Max Pain vs PCR</h2><div id="timelineChart"></div></section>
    <section><h2>Buildup Map (latest snapshot)</h2><div id="buildupTable"></div></section>
  </main>
  <footer>
    <p>Data auto-updates every ~15 min during market hours. Not financial advice; you decide the trade.</p>
  </footer>
  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write `docs/style.css`**

```css
* { box-sizing: border-box; }
body { font-family: system-ui, Arial, sans-serif; margin: 0; background: #0f172a; color: #e2e8f0; }
header { padding: 16px 24px; background: #1e293b; }
h1 { margin: 0 0 8px; font-size: 20px; }
.controls { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
select { padding: 4px 8px; background: #334155; color: #e2e8f0; border: 1px solid #475569; border-radius: 4px; }
#updated { color: #94a3b8; font-size: 13px; }
main { padding: 16px 24px; display: grid; gap: 24px; }
section { background: #1e293b; border-radius: 8px; padding: 12px; }
h2 { font-size: 15px; margin: 0 0 8px; color: #cbd5e1; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 4px 8px; text-align: right; border-bottom: 1px solid #334155; }
th:first-child, td:first-child { text-align: center; font-weight: 600; }
.bu-long-buildup { background: #14532d; }
.bu-short-buildup { background: #7f1d1d; }
.bu-short-covering { background: #1e3a8a; }
.bu-long-unwinding { background: #78350f; }
footer { padding: 16px 24px; color: #94a3b8; font-size: 12px; }
```

- [ ] **Step 3: Write `docs/app.js`** (no `innerHTML` — DOM built with `createElement`/`textContent`)

```javascript
"use strict";

const DATA_ROOTS = ["../data", "./sample"]; // prod first, local-preview fallback

async function fetchJson(path) {
  for (const root of DATA_ROOTS) {
    try {
      const res = await fetch(`${root}/${path}`, { cache: "no-store" });
      if (res.ok) return await res.json();
    } catch (_) { /* try next root */ }
  }
  throw new Error(`could not load ${path}`);
}

function buildupClass(label) {
  return "bu-" + label.toLowerCase().replace(/\s+/g, "-").replace(/\//g, "");
}

function clearNode(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function option(value) {
  const o = document.createElement("option");
  o.value = value;
  o.textContent = value;
  return o;
}

async function loadIndex() {
  const idx = await fetchJson("index.json");
  const daySel = document.getElementById("daySelect");
  clearNode(daySel);
  idx.days.forEach((d) => daySel.appendChild(option(d.trade_date)));
  daySel.onchange = () => populateExpiries(idx);
  if (idx.days.length) daySel.value = idx.days[idx.days.length - 1].trade_date;
  populateExpiries(idx);
}

function populateExpiries(idx) {
  const day = document.getElementById("daySelect").value;
  const dayEntry = idx.days.find((d) => d.trade_date === day);
  const expSel = document.getElementById("expirySelect");
  clearNode(expSel);
  (dayEntry ? dayEntry.expiries : []).forEach((e) => expSel.appendChild(option(e)));
  expSel.onchange = renderSelected;
  renderSelected();
}

async function renderSelected() {
  const day = document.getElementById("daySelect").value;
  const expiry = document.getElementById("expirySelect").value;
  if (!day || !expiry) return;
  const feed = await fetchJson(`${day}/${expiry}.json`);
  document.getElementById("updated").textContent = "Updated: " + (feed.meta.updated_ist || "");
  renderWalls(feed);
  renderTimeline(feed);
  renderBuildup(feed);
}

function renderWalls(feed) {
  const strikes = feed.strikes.map((r) => r.strike);
  Plotly.newPlot("wallsChart", [
    { x: strikes, y: feed.strikes.map((r) => r.ce_oi), name: "CE OI (resistance)", type: "bar", marker: { color: "#ef4444" } },
    { x: strikes, y: feed.strikes.map((r) => r.pe_oi), name: "PE OI (support)", type: "bar", marker: { color: "#22c55e" } },
  ], { barmode: "group", paper_bgcolor: "#1e293b", plot_bgcolor: "#1e293b", font: { color: "#e2e8f0" }, margin: { t: 10 } }, { responsive: true });
}

function renderTimeline(feed) {
  const t = feed.timeline.map((p) => p.t);
  Plotly.newPlot("timelineChart", [
    { x: t, y: feed.timeline.map((p) => p.spot), name: "Spot", type: "scatter", mode: "lines+markers", line: { color: "#38bdf8" } },
    { x: t, y: feed.timeline.map((p) => p.max_pain), name: "Max Pain", type: "scatter", mode: "lines+markers", line: { color: "#f59e0b" } },
    { x: t, y: feed.timeline.map((p) => p.pcr), name: "PCR", type: "scatter", mode: "lines+markers", yaxis: "y2", line: { color: "#a78bfa" } },
  ], {
    paper_bgcolor: "#1e293b", plot_bgcolor: "#1e293b", font: { color: "#e2e8f0" }, margin: { t: 10 },
    yaxis: { title: "Price" }, yaxis2: { title: "PCR", overlaying: "y", side: "right" },
  }, { responsive: true });
}

// Build the buildup table with DOM APIs only — NO innerHTML (XSS-safe).
function cell(text, className) {
  const td = document.createElement("td");
  td.textContent = text;
  if (className) td.className = className;
  return td;
}

function headerRow() {
  const tr = document.createElement("tr");
  ["Strike", "CE OI", "CE ΔOI", "CE Buildup", "PE Buildup", "PE ΔOI", "PE OI", "Zone"]
    .forEach((h) => {
      const th = document.createElement("th");
      th.textContent = h;
      tr.appendChild(th);
    });
  return tr;
}

function renderBuildup(feed) {
  const table = document.createElement("table");
  table.appendChild(headerRow());
  feed.strikes.forEach((r) => {
    const tr = document.createElement("tr");
    tr.appendChild(cell(r.strike));
    tr.appendChild(cell(r.ce_oi));
    tr.appendChild(cell(r.ce_chg_oi));
    tr.appendChild(cell(r.ce_buildup, buildupClass(r.ce_buildup)));
    tr.appendChild(cell(r.pe_buildup, buildupClass(r.pe_buildup)));
    tr.appendChild(cell(r.pe_chg_oi));
    tr.appendChild(cell(r.pe_oi));
    tr.appendChild(cell(r.zone_200pt));
    table.appendChild(tr);
  });
  const container = document.getElementById("buildupTable");
  clearNode(container);
  container.appendChild(table);
}

loadIndex().catch((e) => {
  document.getElementById("updated").textContent = "No data yet: " + e.message;
});
```

- [ ] **Step 4: Write preview fixtures**

`docs/sample/index.json`:

```json
{"days": [{"trade_date": "2026-07-29", "expiries": ["2026-07-31"]}]}
```

`docs/sample/2026-07-29/2026-07-31.json`:

```json
{
  "meta": {"trade_date": "2026-07-29", "expiry": "2026-07-31", "updated_ist": "2026-07-29 09:45"},
  "timeline": [
    {"t": "2026-07-29 09:30", "spot": 24812.35, "pcr": 1.24, "max_pain": 24700},
    {"t": "2026-07-29 09:45", "spot": 24788.0, "pcr": 1.18, "max_pain": 24700}
  ],
  "strikes": [
    {"strike": 24600, "ce_oi": 142800, "ce_chg_oi": -24600, "ce_ltp": 148.9, "ce_iv": 11.1, "ce_volume": 74200,
     "pe_oi": 468900, "pe_chg_oi": 18400, "pe_ltp": 14.2, "pe_iv": 12.8, "pe_volume": 52100,
     "ce_buildup": "Short Covering", "pe_buildup": "Short Buildup", "zone_200pt": "24600-24800"},
    {"strike": 24800, "ce_oi": 298600, "ce_chg_oi": -43500, "ce_ltp": 52.1, "ce_iv": 10.9, "ce_volume": 188400,
     "pe_oi": 341500, "pe_chg_oi": 9800, "pe_ltp": 54.7, "pe_iv": 11.6, "pe_volume": 49300,
     "ce_buildup": "Short Covering", "pe_buildup": "Short Buildup", "zone_200pt": "24800-25000"},
    {"strike": 25000, "ce_oi": 398200, "ce_chg_oi": -53000, "ce_ltp": 9.8, "ce_iv": 11.9, "ce_volume": 352600,
     "pe_oi": 489100, "pe_chg_oi": -8700, "pe_ltp": 201.6, "pe_iv": 12.4, "pe_volume": 14200,
     "ce_buildup": "Short Covering", "pe_buildup": "Long Unwinding", "zone_200pt": "25000-25200"}
  ]
}
```

- [ ] **Step 5: Manually verify in a browser**

Run: open `docs/index.html` via a local server so `fetch` works:
`python -m http.server 8000 --directory docs` then browse `http://localhost:8000/`.
Expected: day/expiry dropdowns populate from `./sample/index.json`; walls bar chart, timeline line chart, and color-coded buildup table all render.

- [ ] **Step 6: Commit**

```bash
git add docs/index.html docs/app.js docs/style.css docs/sample/
git commit -m "feat: GitHub Pages dashboard (Plotly walls, timeline, buildup table, switchers)"
```

---

### Task 10: README + `.gitignore` + final full-suite verification

**Files:**
- Create: `README.md`
- Create: `.gitignore`

**Interfaces:**
- Consumes: everything above.
- Produces: setup docs (one-time GitHub steps) and a clean repo.

- [ ] **Step 1: Write `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
.venv/
venv/
```

- [ ] **Step 2: Write `README.md`**

````markdown
# Nifty 50 Option-Chain Direction Tool

Fetches the NSE Nifty option chain every ~15 min via GitHub Actions, computes direction
indicators (buildup/unwinding, PCR, Max Pain, support/resistance), commits CSV + JSON to
this repo, and serves a live Plotly dashboard on GitHub Pages.

> Not financial advice. This tool surfaces evidence; **you** make the trade decision.

## What you get

- `data/<trade-date>/summary.csv` — day timeline (per expiry).
- `data/<trade-date>/<expiry>_raw.csv` — every displayed strike, every snapshot.
- `data/<trade-date>/<expiry>_buildup.csv` — latest snapshot, readable.
- `data/<trade-date>/<expiry>.json` + `data/index.json` — feeds for the web dashboard.
- Live dashboard: `https://<your-user>.github.io/<repo>/`.

## One-time setup

1. **Create a public GitHub repo** and push this project.
2. **Enable Actions write permission:** Settings → Actions → General → Workflow
   permissions → **Read and write permissions** → Save.
3. **Enable GitHub Pages:** Settings → Pages → Build and deployment → Source: **Deploy
   from a branch** → Branch: `main`, folder: **`/docs`** → Save.
4. The workflow runs on a schedule automatically. To test immediately: Actions tab →
   **fetch-nifty-option-chain** → **Run workflow** (`workflow_dispatch`).

## Configure the strike window

Edit `nifty_oc/config.py`:

```python
STRIKE_MIN = 21000   # bottom strike
STRIKE_MAX = 30000   # top strike
```

Indicators (PCR, Max Pain) are computed on all 50-point strikes for accuracy; the CSVs,
JSON, and dashboard display 200-point strikes for a clean view.

## Run locally (fallback if NSE blocks the cloud IP)

```bash
pip install -r requirements.txt
python -m nifty_oc.main          # respects market-hours guard
pytest -v                        # run the test suite
python -m http.server 8000 --directory docs   # preview dashboard at localhost:8000
```

## Known limitation

NSE may throttle datacenter IPs (which GitHub uses). The fetcher primes cookies, sends
browser-like headers, and retries; a blocked cycle is skipped (non-fatal) and retried
next cycle. If cloud blocking is persistent, run `python -m nifty_oc.main` locally from a
residential connection.
````

- [ ] **Step 3: Run the full test suite one final time**

Run: `pytest -v`
Expected: PASS (all tests: dates, indicators, parse, clock, fetcher, snapshot, writer, main).

- [ ] **Step 4: Commit**

```bash
git add README.md .gitignore
git commit -m "docs: README setup guide and .gitignore"
```

---

## Self-Review (completed)

**1. Spec coverage:**
- Runtime/GitHub Actions/no creds → Task 8. ✅
- Schedule 15-min + 15:25/15:30 IST + market-hours guard → Task 8 (cron) + Task 3 (`clock`) + Task 7 (guard). ✅
- NSE fetch + cookie prime + retry + non-fatal skip → Task 4 + Task 7. ✅
- Strike range hardcoded, 50-compute / 200-display → Task 1 (config) + Task 2 (`display_strikes`) + Task 5. ✅
- Indicators (buildup, PCR, Max Pain, S/R, zones, verdict) → Task 2, exercised in Task 5. ✅
- 3 expiries → Task 1 (`NUM_EXPIRIES`) + Task 3 (`select_expiries`) + Task 5. ✅
- Output CSVs (summary/raw/buildup) + JSON feeds + index → Task 6. ✅
- Web dashboard, 4 views, Plotly, GitHub Pages → Task 9 + Task 10 (Pages setup). ✅
- Testing of indicator logic → Tasks 2/3/5/6/7. ✅
- Column sets & `YYYY-MM-DD HH:MM` / signed-int chg_oi → Task 6 headers + Task 7 timestamp. ✅

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to Task N". All code blocks are concrete. ✅

**3. Type consistency:** Row dict shape (`{"strike", "ce": leg, "pe": leg}`) is consistent across `parse.rows_for_expiry` (Task 3), `indicators` (Task 2), and `snapshot` (Task 5). DisplayRow keys used in `writer` (Task 6) and `app.js` (Task 9) match those emitted by `snapshot._display_row` (Task 5). `fetch_option_chain`/`FetchError` names match across Tasks 4 and 7. `is_market_hours`, `build_snapshot`, `load_prev_ltp`, `ltp_index` signatures consistent between definition and callers. ✅

**4. Security:** Dashboard uses no `innerHTML`; all dynamic DOM built via `createElement`/`textContent` (Task 9). No credentials anywhere; commits use built-in `GITHUB_TOKEN` (Task 8). ✅
