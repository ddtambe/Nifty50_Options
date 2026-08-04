# Nifty 50 Option-Chain Direction Tool

## Complete Project Documentation

**Version:** 1.0  
**Last Updated:** August 4, 2026  
**Author:** Built with Claude Code

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [File Structure](#3-file-structure)
4. [Configuration](#4-configuration)
5. [Data Pipeline](#5-data-pipeline)
6. [GitHub Actions Workflow](#6-github-actions-workflow)
7. [Dashboard Features](#7-dashboard-features)
8. [5paisa API Integration](#8-5paisa-api-integration)
9. [GitHub Secrets Setup](#9-github-secrets-setup)
10. [Installation and Setup](#10-installation-and-setup)
11. [Running Locally](#11-running-locally)
12. [Troubleshooting](#12-troubleshooting)
13. [Data Formats](#13-data-formats)
14. [Indicator Calculations](#14-indicator-calculations)
15. [Security Considerations](#15-security-considerations)

---

## 1. Project Overview

### Purpose

An automated tool that fetches Nifty 50 option chain data every 15 minutes during market hours, computes trading indicators (PCR, Max Pain, Buildup, Support/Resistance), and displays them on an interactive web dashboard.

### Key Features

- **Automated Data Collection:** Runs via GitHub Actions every 15 minutes (Mon-Fri, 09:15-15:30 IST)
- **5paisa API Integration:** Uses legitimate broker API (not web scraping)
- **Real-time Indicators:** PCR, Max Pain, Buildup analysis, S/R zones
- **Interactive Dashboard:** Plotly.js charts hosted on GitHub Pages
- **Multi-Expiry Support:** Tracks 3 expiries simultaneously
- **Historical Comparison:** Compare same expiry across different days
- **Zero Infrastructure Cost:** Runs entirely on GitHub (free tier)

### Technology Stack

| Component | Technology |
|-----------|------------|
| Backend | Python 3.11 |
| Data Source | 5paisa API (py5paisa SDK) |
| Automation | GitHub Actions |
| Storage | Git repository (CSV + JSON) |
| Frontend | HTML, CSS, JavaScript |
| Charts | Plotly.js |
| Hosting | GitHub Pages |

---

## 2. Architecture

```
+------------------------------------------------------------------+
|                      GitHub Actions                               |
|  +------------------------------------------------------------+  |
|  |  Cron Schedule: */15 min (Mon-Fri, 09:15-15:30 IST)        |  |
|  +------------------------------------------------------------+  |
|                              |                                    |
|                              v                                    |
|  +------------------------------------------------------------+  |
|  |                    Python Pipeline                          |  |
|  |  +----------+  +----------+  +----------+  +---------+     |  |
|  |  | fetcher  |->|  parser  |->|indicators|->| writer  |     |  |
|  |  | (5paisa) |  |          |  |          |  |         |     |  |
|  |  +----------+  +----------+  +----------+  +---------+     |  |
|  +------------------------------------------------------------+  |
|                              |                                    |
|                              v                                    |
|  +------------------------------------------------------------+  |
|  |              Git Commit and Push                            |  |
|  |  data/YYYY-MM-DD/*.csv, *.json -> GitHub Repository        |  |
|  +------------------------------------------------------------+  |
+------------------------------------------------------------------+
                               |
                               v
+------------------------------------------------------------------+
|                      GitHub Pages                                 |
|  +------------------------------------------------------------+  |
|  |  docs/index.html + app.js + style.css                      |  |
|  |  Loads: ../data/index.json -> renders Plotly charts        |  |
|  +------------------------------------------------------------+  |
+------------------------------------------------------------------+
```

### Data Flow

1. **Fetch:** 5paisa API -> Raw option chain JSON
2. **Parse:** Extract strikes, OI, LTP, IV for configured range
3. **Compute:** Calculate PCR, Max Pain, Buildup, S/R zones
4. **Write:** Save to CSV (for Excel) and JSON (for dashboard)
5. **Commit:** Push to GitHub repository
6. **Deploy:** GitHub Pages serves the dashboard
7. **Display:** Browser loads JSON, renders Plotly charts

---

## 3. File Structure

```
nifty-oc/
|-- nifty_oc/                    # Python package
|   |-- __init__.py
|   |-- main.py                  # Entry point, orchestrates pipeline
|   |-- config.py                # User-editable configuration
|   |-- clock.py                 # Market hours guard
|   |-- fetcher.py               # 5paisa API integration
|   |-- parser.py                # Data extraction and filtering
|   |-- indicators.py            # PCR, Max Pain, Buildup, S/R
|   |-- snapshot.py              # Build snapshot with indicators
|   +-- writer.py                # CSV/JSON file writers
|
|-- tests/                       # Test suite (53 tests)
|   |-- test_clock.py
|   |-- test_fetcher.py
|   |-- test_indicators.py
|   |-- test_main.py
|   |-- test_parse.py
|   |-- test_snapshot.py
|   +-- test_writer.py
|
|-- docs/                        # Dashboard (GitHub Pages)
|   |-- index.html               # Main HTML structure
|   |-- app.js                   # Dashboard logic, Plotly rendering
|   |-- style.css                # Styling
|   +-- sample/                  # Fallback sample data
|       |-- index.json
|       +-- 2026-07-29/
|           +-- 2026-07-31.json
|
|-- data/                        # Generated data (git-tracked)
|   |-- index.json               # Index of all days and expiries
|   +-- YYYY-MM-DD/              # One folder per trade date
|       |-- summary.csv          # Aggregated indicators per snapshot
|       |-- YYYY-MM-DD_raw.csv   # Full option chain (nearest expiry)
|       |-- YYYY-MM-DD_buildup.csv
|       |-- YYYY-MM-DD.json      # JSON for dashboard (nearest expiry)
|       +-- ...                  # More expiries
|
|-- .github/
|   +-- workflows/
|       +-- fetch.yml            # GitHub Actions workflow
|
|-- requirements.txt             # Python dependencies
|-- .gitignore
|-- README.md
|-- SETUP_COMPLETE.md            # Setup summary from initial build
+-- PROJECT_DOCUMENTATION.md     # This file
```

---

## 4. Configuration

### nifty_oc/config.py

```python
"""User-editable configuration constants."""

SYMBOL = "NIFTY"

# Strike window - edit these to change coverage
STRIKE_MIN = 21000
STRIKE_MAX = 30000
STRIKE_STEP = 50       # Nifty native strike gap (for accurate PCR/Max Pain)
DISPLAY_STEP = 200     # Strikes shown in output (46 rows: 21000 to 30000)

NUM_EXPIRIES = 3       # Current + next 2 weekly expiries

MARKET_OPEN = (9, 15)   # IST hours, minutes
MARKET_CLOSE = (15, 30)

DATA_DIR = "data"
DOCS_DIR = "docs"
```

### Configuration Options

| Parameter | Default | Description |
|-----------|---------|-------------|
| SYMBOL | "NIFTY" | Underlying symbol |
| STRIKE_MIN | 21000 | Lowest strike to track |
| STRIKE_MAX | 30000 | Highest strike to track |
| STRIKE_STEP | 50 | Native strike interval (for computation) |
| DISPLAY_STEP | 200 | Output strike interval (reduces rows) |
| NUM_EXPIRIES | 3 | Number of expiries to fetch |
| MARKET_OPEN | (9, 15) | Market open time IST |
| MARKET_CLOSE | (15, 30) | Market close time IST |

### Why 50-Compute / 200-Display?

- PCR and Max Pain are sums across all strikes
- Computing on only 200-step strikes would miss OI and produce inaccurate indicators
- We compute on all 50-step strikes for accuracy
- We display only 200-step strikes for cleaner output (46 rows instead of 181)

---

## 5. Data Pipeline

### Module Responsibilities

#### main.py - Orchestrator

```python
def run_cycle():
    # 1. Check market hours
    if not is_market_hours(now_ist):
        print("[skip] outside market hours")
        return
    
    # 2. Fetch from 5paisa
    raw = fetch_option_chain()
    
    # 3. Build snapshots for each expiry
    for expiry in expiries:
        snapshot = build_snapshot(raw, expiry, prev_ltp)
        write_files(snapshot)
    
    # 4. Update index
    write_index()
```

#### fetcher.py - 5paisa API Client

- Authenticates using TOTP (auto-generates 6-digit code from secret)
- Fetches expiry list via get_expiry("N", "NIFTY")
- Fetches option chain via get_option_chain("N", "NIFTY", expiry_timestamp)
- Transforms 5paisa response format to NSE-compatible format for pipeline

#### parser.py - Data Extraction

- extract_spot(raw) - Gets underlying spot price
- extract_expiries(raw) - Gets list of expiry dates
- rows_for_expiry(raw, expiry, min, max) - Filters strikes for an expiry
- nearest_atm(spot, step) - Rounds spot to nearest strike

#### indicators.py - Calculations

- compute_pcr(rows) - Put-Call Ratio (PE OI / CE OI)
- compute_max_pain(rows) - Strike where option buyers lose most
- buildup_label(oi_delta, ltp_delta) - Long/Short Buildup/Unwinding
- zone_label(strike, spot, atm) - ATM/ITM/OTM zone
- support_resistance(rows) - Highest PE OI (support) / CE OI (resistance)
- verdict(spot, max_pain, pcr, support, resistance) - Bullish/Bearish/Rangebound

#### snapshot.py - Snapshot Builder

- Builds complete snapshot with all indicators
- Computes buildup by comparing current LTP with previous snapshot
- Filters to DISPLAY_STEP strikes for output

#### writer.py - File Writers

- write_summary_row() - Appends to summary.csv
- write_raw_csv() - Appends full chain to raw CSV
- write_buildup_csv() - Overwrites buildup CSV (latest only)
- write_json_feed() - Appends to JSON timeline for dashboard
- write_index() - Updates data/index.json with available days/expiries

---

## 6. GitHub Actions Workflow

### .github/workflows/fetch.yml

```yaml
name: fetch-nifty-option-chain

on:
  schedule:
    # Every 15 min during IST market window (03:45-10:00 UTC)
    - cron: "*/15 3-10 * * 1-5"
    # Extra snapshots at 15:25 and 15:30 IST
    - cron: "55,59 9 * * 1-5"
    - cron: "0 10 * * 1-5"
  workflow_dispatch:
    inputs:
      force:
        description: 'Force fetch (bypass market-hours check)'
        required: false
        default: 'false'
        type: choice
        options:
          - 'false'
          - 'true'

permissions:
  contents: write   # Allow committing data back

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
        env:
          FORCE_FETCH: ${{ github.event.inputs.force || 'false' }}
          # All 9 secrets passed as environment variables
      
      - name: Commit data if changed
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          if [ -d data/ ]; then
            git add data/
            git diff --staged --quiet || git commit -m "data: snapshot" && git push
          fi
```

### Schedule Explanation

| Cron | UTC Time | IST Time | Purpose |
|------|----------|----------|---------|
| */15 3-10 * * 1-5 | 03:00-10:45 | 08:30-16:15 | Main 15-min intervals |
| 55,59 9 * * 1-5 | 09:55, 09:59 | 15:25, 15:29 | Near-close snapshots |
| 0 10 * * 1-5 | 10:00 | 15:30 | Exact close snapshot |

Note: The code has an additional market-hours guard that skips if outside 09:15-15:30 IST.

### Manual Trigger

1. Go to Actions -> fetch-nifty-option-chain
2. Click "Run workflow"
3. Set "Force fetch" to true to bypass market-hours check
4. Click "Run workflow"

---

## 7. Dashboard Features

### URL

https://ddtambe.github.io/Nifty50_Options/docs/

### Controls

| Control | Function |
|---------|----------|
| Day Dropdown | Select trade date |
| Expiry Dropdown | Select expiry (weekly options) |
| Compare Checkboxes | Overlay other days for same expiry |

### Charts

#### 1. Support/Resistance Walls (OI Chart)

- Red Bars: CE OI at each strike (resistance levels)
- Green Bars: PE OI at each strike (support levels)
- Highest bars indicate strongest S/R zones

#### 2. Day Timeline

- Blue Line: Spot price throughout the day
- Orange Line: Max Pain level
- Purple Line (Right Axis): PCR ratio
- Dashed Lines: Comparison days (when checkboxes selected)

#### 3. Buildup Map (Table)

| Column | Meaning |
|--------|---------|
| Strike | Strike price |
| CE OI | Call Open Interest |
| CE Delta OI | Change in Call OI |
| CE Buildup | Long Buildup / Short Buildup / Long Unwinding / Short Covering |
| PE Buildup | Same for Puts |
| PE Delta OI | Change in Put OI |
| PE OI | Put Open Interest |
| Zone | ATM / ITM / OTM relative to spot |

#### Buildup Color Coding

| Label | Color | Meaning |
|-------|-------|---------|
| Long Buildup | Green | OI up, Price up (bullish) |
| Short Buildup | Red | OI up, Price down (bearish) |
| Short Covering | Blue | OI down, Price up (bullish exit) |
| Long Unwinding | Orange | OI down, Price down (bearish exit) |

### Multi-Day Comparison Feature

When multiple days of data exist for the same expiry:

1. Checkboxes appear below the timeline chart
2. Check a day to overlay its Spot/Max Pain/PCR
3. Primary day = solid lines
4. Comparison days = dashed lines with distinct colors
5. Useful for tracking how an expiry evolves across days

---

## 8. 5paisa API Integration

### Authentication Flow

```
1. Create FivePaisaClient with credentials
2. Generate TOTP code from secret (RFC 6238)
3. Call get_totp_session(client_code, totp_code, pin)
4. Client is now authenticated
5. Call get_expiry() and get_option_chain()
```

### TOTP Generation

The code auto-generates the 6-digit TOTP code from your secret:

```python
def _generate_totp(secret: str) -> str:
    """Generate current TOTP code from secret (RFC 6238)."""
    key = base64.b32decode(secret.upper() + padding)
    counter = int(time.time()) // 30
    hmac_hash = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    # Dynamic truncation to get 6-digit code
    return str(code % 1000000).zfill(6)
```

### API Methods Used

| Method | Purpose |
|--------|---------|
| get_totp_session(client_code, totp, pin) | Authenticate |
| get_expiry("N", "NIFTY") | Get available expiry dates |
| get_option_chain("N", "NIFTY", expiry_ts) | Get option chain for an expiry |

### Response Transformation

5paisa returns data in their format; we transform to NSE-compatible format:

```python
# 5paisa format
{
    "Options": [
        {"StrikeRate": 24800, "CPType": "CE", "OpenInterest": 1000, ...}
    ]
}

# Transformed to NSE-like format
{
    "records": {
        "underlyingValue": 24812.35,
        "expiryDates": ["04-Aug-2026", "11-Aug-2026", ...],
        "data": [
            {
                "strikePrice": 24800,
                "expiryDate": "04-Aug-2026",
                "CE": {"openInterest": 1000, "changeinOpenInterest": 50, ...},
                "PE": {...}
            }
        ]
    }
}
```

---

## 9. GitHub Secrets Setup

### Required Secrets (9 total)

Go to: Repository -> Settings -> Secrets and variables -> Actions -> New repository secret

| Secret Name | Description | Where to Find |
|-------------|-------------|---------------|
| FIVEPAISA_APP_NAME | Application name | 5paisa Developer Portal |
| FIVEPAISA_APP_SOURCE | Application source ID | 5paisa Developer Portal |
| FIVEPAISA_USER_ID | API User ID | 5paisa Developer Portal |
| FIVEPAISA_PASSWORD | API Password | 5paisa Developer Portal |
| FIVEPAISA_USER_KEY | User Key | 5paisa Developer Portal |
| FIVEPAISA_ENCRYPTION_KEY | Encryption Key | 5paisa Developer Portal |
| FIVEPAISA_CLIENT_CODE | Your login/client code | Your 5paisa account |
| FIVEPAISA_TOTP_SECRET | TOTP secret key (base32) | 5paisa 2FA setup screen |
| FIVEPAISA_PIN | Your trading PIN | Your 5paisa account |

### Getting TOTP Secret

1. Log into 5paisa web/app
2. Go to Profile -> Settings -> Security
3. Enable TOTP / Two-Factor Authentication
4. When shown QR code, look for "Can't scan? Enter manually"
5. That key (e.g., JBSWY3DPEHPK3PXP) is your TOTP_SECRET

### Getting API Credentials

1. Go to https://www.5paisa.com/developerapi
2. Register/login as developer
3. Create an application
4. Copy APP_NAME, APP_SOURCE, USER_ID, PASSWORD, USER_KEY, ENCRYPTION_KEY

---

## 10. Installation and Setup

### Prerequisites

- Python 3.11+
- Git
- GitHub account
- 5paisa trading account with API access

### Step 1: Clone Repository

```bash
git clone https://github.com/ddtambe/Nifty50_Options.git
cd Nifty50_Options
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Configure GitHub Secrets

Add all 9 secrets as described in Section 9.

### Step 4: Enable GitHub Pages

1. Go to Repository -> Settings -> Pages
2. Source: Deploy from a branch
3. Branch: main, Folder: / (root)
4. Save

### Step 5: Verify Workflow

1. Go to Actions -> fetch-nifty-option-chain
2. Click "Run workflow" with force=true
3. Check logs for successful fetch

### Step 6: Access Dashboard

https://ddtambe.github.io/Nifty50_Options/docs/

---

## 11. Running Locally

### Set Environment Variables

```bash
# Windows PowerShell
$env:FIVEPAISA_APP_NAME = "your_app_name"
$env:FIVEPAISA_APP_SOURCE = "your_app_source"
$env:FIVEPAISA_USER_ID = "your_user_id"
$env:FIVEPAISA_PASSWORD = "your_password"
$env:FIVEPAISA_USER_KEY = "your_user_key"
$env:FIVEPAISA_ENCRYPTION_KEY = "your_encryption_key"
$env:FIVEPAISA_CLIENT_CODE = "your_client_code"
$env:FIVEPAISA_TOTP_SECRET = "your_totp_secret"
$env:FIVEPAISA_PIN = "your_pin"
$env:FORCE_FETCH = "true"  # Optional: bypass market hours

# Linux/Mac
export FIVEPAISA_APP_NAME="your_app_name"
# ... etc
```

### Run Fetch Cycle

```bash
cd nifty-oc
python -m nifty_oc.main
```

### Run Tests

```bash
python -m pytest -v
```

### Preview Dashboard Locally

```bash
python -m http.server 8000 --directory docs
# Open http://localhost:8000
```

---

## 12. Troubleshooting

### Issue: "Missing credentials" error

**Cause:** Environment variables not set or GitHub secrets not configured.

**Fix:** Verify all 9 secrets are added in GitHub -> Settings -> Secrets.

### Issue: "[skip] outside market hours"

**Cause:** Running outside Mon-Fri 09:15-15:30 IST.

**Fix:** Use manual workflow trigger with force=true.

### Issue: "Illegal header value b'Bearer '"

**Cause:** TOTP authentication failed.

**Fix:** 
- Verify FIVEPAISA_TOTP_SECRET is the base32 key (not 6-digit code)
- Verify FIVEPAISA_CLIENT_CODE and FIVEPAISA_PIN are correct

### Issue: "No option chain data received"

**Cause:** API returned empty data or market is closed.

**Fix:** 
- Run during market hours
- Check 5paisa account has API access enabled
- Verify credentials are correct

### Issue: Dashboard shows sample data only

**Cause:** No live data committed yet, or GitHub Pages not updated.

**Fix:**
- Check if data/ folder exists in GitHub repo
- Wait 1-5 minutes for GitHub Pages deployment
- Hard refresh browser (Ctrl+Shift+R)

### Issue: Dashboard shows "No data yet"

**Cause:** data/index.json not accessible.

**Fix:**
- Verify GitHub Pages source is / (root), not /docs
- Check that data/index.json exists in repo

### Issue: Workflow fails with exit code 128

**Cause:** Git permission issue.

**Fix:** Ensure repository Settings -> Actions -> Workflow permissions -> "Read and write permissions" is enabled.

---

## 13. Data Formats

### summary.csv

```csv
timestamp,expiry,spot,pcr,max_pain,support,resistance,verdict
2026-08-04 09:30:00+05:30,2026-08-04,24812.35,0.85,24800,24500,25000,Rangebound
2026-08-04 09:45:00+05:30,2026-08-04,24850.00,0.88,24800,24500,25000,Bullish
```

### *_raw.csv

```csv
timestamp,strike,ce_oi,ce_chg_oi,ce_ltp,ce_iv,ce_volume,pe_oi,pe_chg_oi,pe_ltp,pe_iv,pe_volume
2026-08-04 09:30:00+05:30,21000,50000,1000,3800.5,18.5,25000,1000,50,0.5,45.2,500
```

### *_buildup.csv

```csv
strike,ce_oi,ce_chg_oi,ce_buildup,pe_oi,pe_chg_oi,pe_buildup,zone
21000,50000,1000,Long Buildup,1000,50,Short Covering,OTM
```

### *.json (Dashboard Feed)

```json
{
  "meta": {
    "expiry": "2026-08-04",
    "updated_ist": "2026-08-04 15:30:00"
  },
  "timeline": [
    {"t": "09:30", "spot": 24812.35, "pcr": 0.85, "max_pain": 24800},
    {"t": "09:45", "spot": 24850.00, "pcr": 0.88, "max_pain": 24800}
  ],
  "strikes": [
    {
      "strike": 21000,
      "ce_oi": 50000, "ce_chg_oi": 1000, "ce_buildup": "Long Buildup",
      "pe_oi": 1000, "pe_chg_oi": 50, "pe_buildup": "Short Covering",
      "zone_200pt": "OTM"
    }
  ]
}
```

### data/index.json

```json
{
  "days": [
    {
      "trade_date": "2026-08-04",
      "expiries": ["2026-08-04", "2026-08-11", "2026-08-18"]
    }
  ]
}
```

---

## 14. Indicator Calculations

### Put-Call Ratio (PCR)

```
PCR = Total PE Open Interest / Total CE Open Interest
```

| PCR Value | Interpretation |
|-----------|----------------|
| > 1.2 | Bullish (more puts = hedging) |
| 0.8 - 1.2 | Neutral |
| < 0.8 | Bearish (more calls = speculation) |

### Max Pain

The strike price at which option buyers (both calls and puts) would lose the maximum amount of money.

```python
for each strike:
    pain = sum of (CE intrinsic value * CE OI) + (PE intrinsic value * PE OI)
max_pain = strike with minimum total pain
```

### Buildup Analysis

| OI Change | Price Change | Label | Meaning |
|-----------|--------------|-------|---------|
| Increase | Increase | Long Buildup | Fresh longs, bullish |
| Increase | Decrease | Short Buildup | Fresh shorts, bearish |
| Decrease | Increase | Short Covering | Shorts exiting, bullish |
| Decrease | Decrease | Long Unwinding | Longs exiting, bearish |

### Support/Resistance

- **Support:** Strike with highest PE OI (put writers will defend)
- **Resistance:** Strike with highest CE OI (call writers will defend)

### Verdict Logic

```python
if spot > max_pain and pcr > 1.0:
    verdict = "Bullish"
elif spot < max_pain and pcr < 0.8:
    verdict = "Bearish"
else:
    verdict = "Rangebound"
```

---

## 15. Security Considerations

### Secrets Management

- All credentials stored as GitHub Secrets (encrypted)
- Never committed to repository
- Masked in workflow logs (shown as ***)

### No Sensitive Data in Repo

- No API keys, passwords, or tokens in any file
- .gitignore excludes local environment files
- All option chain data is public market data (not sensitive)

### XSS Prevention

Dashboard uses safe DOM manipulation:

```javascript
// SAFE: Using textContent (escapes HTML)
td.textContent = data.value;

// NEVER use methods that interpret HTML with untrusted data
```

### Repository Visibility

- Repository is PUBLIC for free GitHub Actions minutes and free GitHub Pages
- This is safe because:
  - All secrets are in GitHub Secrets (not in repo)
  - Option chain data is public market data
  - Dashboard displays only public information

---

## Appendix A: File Summary

| File | Lines | Purpose |
|------|-------|---------|
| nifty_oc/main.py | ~50 | Entry point |
| nifty_oc/config.py | ~17 | Configuration |
| nifty_oc/clock.py | ~15 | Market hours guard |
| nifty_oc/fetcher.py | ~180 | 5paisa API |
| nifty_oc/parser.py | ~60 | Data extraction |
| nifty_oc/indicators.py | ~80 | Calculations |
| nifty_oc/snapshot.py | ~100 | Snapshot builder |
| nifty_oc/writer.py | ~150 | File writers |
| docs/app.js | ~180 | Dashboard logic |
| docs/index.html | ~35 | Dashboard HTML |
| docs/style.css | ~25 | Dashboard CSS |

---

## Appendix B: URLs Reference

| Resource | URL |
|----------|-----|
| GitHub Repository | https://github.com/ddtambe/Nifty50_Options |
| Live Dashboard | https://ddtambe.github.io/Nifty50_Options/docs/ |
| Actions/Workflows | https://github.com/ddtambe/Nifty50_Options/actions |
| Data Folder | https://github.com/ddtambe/Nifty50_Options/tree/main/data |
| 5paisa Developer Portal | https://www.5paisa.com/developerapi |
| py5paisa SDK | https://github.com/OpenApi-5p/py5paisa |

---

## Appendix C: Test Coverage

```
tests/test_clock.py          - 4 tests  (market hours logic)
tests/test_fetcher.py        - 12 tests (API mocking, credentials)
tests/test_indicators.py     - 10 tests (PCR, Max Pain, Buildup)
tests/test_main.py           - 3 tests  (orchestration)
tests/test_parse.py          - 6 tests  (data extraction)
tests/test_snapshot.py       - 8 tests  (snapshot building)
tests/test_writer.py         - 10 tests (file writing)
-----------------------------------------
Total:                         53 tests
```

Run tests: `python -m pytest -v`

---

**End of Documentation**
