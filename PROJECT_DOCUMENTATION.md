# Nifty 50 Option-Chain Direction Tool

## Complete Project Documentation (Single Source of Truth)

**Version:** 2.0
**Last Updated:** August 11, 2026
**Repository:** https://github.com/ddtambe/Nifty50_Options (public)
**Live Dashboard:** https://ddtambe.github.io/Nifty50_Options/docs/

> This single document supersedes the older `README.md`, `SETUP_COMPLETE.md`, and
> `EXTERNAL_CRON_SETUP.md` notes. It reflects the code as it stands today, including
> brewing-move detection, the per-strike OI heatmaps, TradingView-style chart zoom,
> the weekend market-hours guard, and the spot-resolution fix.
>
> **Not financial advice.** This tool surfaces evidence; *you* make the trade decision.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture and Data Flow](#2-architecture-and-data-flow)
3. [File Structure](#3-file-structure)
4. [Configuration (`config.py`)](#4-configuration-configpy)
5. [The Pipeline, Module by Module](#5-the-pipeline-module-by-module)
6. [Indicators (`indicators.py`)](#6-indicators-indicatorspy)
7. [Brewing-Move / OI-Surge Detection (`signals.py`)](#7-brewing-move--oi-surge-detection-signalspy)
8. [The `brewing_today` Accumulator (`writer.py`)](#8-the-brewing_today-accumulator-writerpy)
9. [5paisa API Integration and Spot Resolution (`fetcher.py`)](#9-5paisa-api-integration-and-spot-resolution-fetcherpy)
10. [Market-Hours Guard (`clock.py`)](#10-market-hours-guard-clockpy)
11. [GitHub Actions Workflow and External Cron](#11-github-actions-workflow-and-external-cron)
12. [The Web Dashboard (`docs/`)](#12-the-web-dashboard-docs)
13. [Data Formats](#13-data-formats)
14. [GitHub Secrets Setup](#14-github-secrets-setup)
15. [Install, Run, and Test](#15-install-run-and-test)
16. [Security Considerations](#16-security-considerations)
17. [Troubleshooting](#17-troubleshooting)
18. [Recent Changes (Session Changelog)](#18-recent-changes-session-changelog)
19. [Known Limitations and Pending Work](#19-known-limitations-and-pending-work)
20. [Appendix: Module and Test Summary](#20-appendix-module-and-test-summary)

---

## 1. Project Overview

### Purpose

An automated tool that fetches the Nifty 50 option chain every ~15 minutes during market
hours, computes direction indicators, detects OI surges that hint where a move is
*building*, commits CSV + JSON to a public repo, and serves an interactive Plotly
dashboard on GitHub Pages — all on GitHub's free tier, with zero servers.

### Key Features

- **Automated collection** every ~15 min (Mon–Fri, 09:15–15:30 IST) via GitHub Actions.
- **Legitimate broker API** (5paisa `py5paisa` SDK, TOTP auth) — not web scraping.
- **Direction indicators:** PCR, Max Pain, Support/Resistance, buildup/unwinding, verdict.
- **Brewing-move detection:** flags strikes whose CE/PE OI is surging over 30-min / 1-hr
  windows — a *leading* signal that price may move.
- **Interactive dashboard:** S/R walls, day timeline, buildup table, per-strike OI
  heatmaps, and brewing-move cards, all with TradingView-style zoom/pan.
- **Multi-expiry** (current + next 2 weekly expiries) and **historical comparison**
  (overlay the same expiry across days).
- **Zero infrastructure cost.**

### Technology Stack

| Component    | Technology                          |
|--------------|-------------------------------------|
| Backend      | Python 3.11 (CI) / 3.14 (local dev) |
| Data source  | 5paisa API via `py5paisa`           |
| Automation   | GitHub Actions (+ external cron)    |
| Storage      | Git repo (CSV + JSON)               |
| Frontend     | HTML + CSS + vanilla JS             |
| Charts       | Plotly.js                           |
| Hosting      | GitHub Pages                        |
| Tests        | pytest                              |

---

## 2. Architecture and Data Flow

```
+---------------------------------------------------------------------+
|                          GitHub Actions                             |
|  Schedule (cron "*/15 3-10 * * 1-5") + workflow_dispatch            |
|  (external cron-job.org can also trigger the dispatch)             |
|                              |                                       |
|                              v                                       |
|   Python pipeline:  clock -> fetcher -> parse -> indicators         |
|                     -> snapshot -> signals -> writer                |
|                              |                                       |
|                              v                                       |
|   git add data/ && commit && push   (only if data changed)         |
+---------------------------------------------------------------------+
                               |
                               v
+---------------------------------------------------------------------+
|                          GitHub Pages                               |
|  docs/index.html + app.js + style.css                              |
|  fetches ../data/index.json and ../data/<date>/<expiry>.json       |
|  renders Plotly charts, heatmaps, and brewing cards                |
+---------------------------------------------------------------------+
```

### Cycle data flow (one run of `python -m nifty_oc.main`)

1. **Guard** — `clock.is_market_hours(now_ist)` — skip if weekend or outside 09:15–15:30
   IST (unless `FORCE_FETCH=true`).
2. **Load previous LTP** — `writer.load_prev_ltp()` reads the day's `_raw.csv` files so
   buildup can compare this snapshot against the last.
3. **Fetch** — `fetcher.fetch_option_chain()` logs in via TOTP, pulls expiries + chains,
   resolves spot, returns an NSE-compatible payload. A `FetchError` is a **non-fatal
   skip** (the cycle exits cleanly, retried next time).
4. **Build snapshot** — `snapshot.build_snapshot()` computes indicators per expiry and
   builds display rows with buildup labels.
5. **Write** — `writer` appends `summary.csv` + `_raw.csv`, overwrites `_buildup.csv`,
   updates each `<expiry>.json` (timeline, strikes, `strikes_timeline`, `brewing`,
   `brewing_today`), and rebuilds `index.json`.
6. **Commit & deploy** — the workflow commits `data/`; GitHub Pages serves it.

---

## 3. File Structure

```
nifty-oc/
├── nifty_oc/                     # Python package (the pipeline)
│   ├── __init__.py
│   ├── main.py                   # Orchestrator: guard -> fetch -> compute -> write
│   ├── config.py                 # User-editable constants + surge thresholds
│   ├── clock.py                  # Market-hours guard (weekend + time window)
│   ├── fetcher.py                # 5paisa API client, TOTP auth, spot resolution
│   ├── dates.py                  # NSE expiry parsing/selection
│   ├── parse.py                  # Raw payload -> clean row dicts (pure)
│   ├── indicators.py             # PCR, Max Pain, S/R, buildup, verdict (pure)
│   ├── signals.py                # Brewing-move (OI-surge) detection (pure)
│   ├── snapshot.py               # Assemble one cycle's computed snapshot
│   └── writer.py                 # CSV/JSON writers + brewing_today accumulator
│
├── tests/                        # pytest suite (81 tests)
│   ├── test_clock.py             ├── test_indicators.py  ├── test_snapshot.py
│   ├── test_fetcher.py           ├── test_main.py        ├── test_writer.py
│   ├── test_dates.py             ├── test_parse.py       └── test_signals.py
│   └── fixtures/sample_chain.json
│
├── docs/                         # Dashboard (served by GitHub Pages)
│   ├── index.html                # Layout + Plotly include
│   ├── app.js                    # Data load, chart rendering, zoom config
│   ├── style.css                 # Styling (incl. brewing cards / heatmaps)
│   ├── sample/                   # Bundled fallback data
│   └── superpowers/              # Design specs + implementation plans
│       ├── specs/                #   *-design.md (brainstormed specs)
│       └── plans/                #   *.md (implementation plans)
│
├── data/                         # Generated at runtime (git-tracked)
│   ├── index.json                # {days: [{trade_date, expiries:[...]}]}
│   └── <trade-date>/             # One folder per trade date
│       ├── summary.csv           #   day timeline, all expiries (append)
│       ├── <expiry>_raw.csv      #   every displayed strike, every snapshot (append)
│       ├── <expiry>_buildup.csv  #   latest snapshot, readable (overwrite)
│       └── <expiry>.json         #   dashboard feed (read-modify-write)
│
├── .github/workflows/fetch.yml   # GitHub Actions workflow
├── requirements.txt
├── README.md                     # (superseded by this document)
├── SETUP_COMPLETE.md             # (superseded)
├── EXTERNAL_CRON_SETUP.md        # (superseded)
└── PROJECT_DOCUMENTATION.md      # THIS FILE — single source of truth
```

---

## 4. Configuration (`config.py`)

```python
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
SURGE_WINDOWS = {"30min": 2, "1hr": 4}   # label -> snapshots-ago (15-min steps)

MARKET_OPEN = (9, 15)    # IST hh, mm
MARKET_CLOSE = (15, 30)  # IST hh, mm

DATA_DIR = "data"
DOCS_DIR = "docs"
```

| Parameter             | Default            | Meaning                                                  |
|-----------------------|--------------------|----------------------------------------------------------|
| `STRIKE_STEP`         | 50                 | Native strike gap — indicators computed on **all** 50-pt strikes for accuracy. |
| `DISPLAY_STEP`        | 200                | Output granularity — CSV/JSON/dashboard show 200-pt strikes for a clean view. |
| `NUM_EXPIRIES`        | 3                  | Weekly expiries fetched each cycle.                      |
| `SURGE_PCT_THRESHOLD` | 0.30               | A leg must grow ≥30% over a window to flag.              |
| `SURGE_ABS_THRESHOLD` | 500,000            | ...**and** grow ≥500K contracts (both conditions).       |
| `SURGE_WINDOWS`       | `{30min:2, 1hr:4}` | Look-back offsets in 15-min snapshots (2 back ≈ 30 min). |

**Why compute-on-50 / display-on-200?** PCR and Max Pain are sums across strikes; computing
only on 200-pt strikes would drop most of the OI and skew the indicators. So the math runs
on every 50-pt strike, while output is thinned to 200-pt strikes for readability.

---

## 5. The Pipeline, Module by Module

### `main.py` — Orchestrator

```python
def run(now=None, fetch=None, data_dir=None) -> int:
    now = now or now_ist()
    if not is_market_hours(now):
        print(f"[skip] outside market hours: {now}")
        return 0
    ts = now.strftime("%Y-%m-%d %H:%M"); trade_date = ts[:10]
    prev = writer.load_prev_ltp(trade_date, data_dir)
    try:
        payload = fetch()
    except FetchError as exc:
        print(f"[skip] fetch failed (non-fatal): {exc}")   # e.g. spot unresolvable
        return 0
    snap = build_snapshot(payload, ts, prev)
    writer.write_summary(snap, data_dir); writer.write_raw(snap, data_dir)
    writer.write_buildup(snap, data_dir); writer.write_json_feed(snap, data_dir)
    writer.write_index(data_dir)
    print(f"[ok] {ts} spot={snap['spot']} | ...verdicts...")
    return 0
```

`run()` is dependency-injectable (`now`, `fetch`, `data_dir`) so tests drive it without
network or the clock. `main()` just calls `sys.exit(run())`.

### `dates.py` — Expiry helpers (pure)

- `parse_nse_expiry("31-Jul-2026") -> "2026-07-31"`.
- `select_expiries(list, count) -> [iso, ...]` — first `count`, order preserved.

### `parse.py` — Raw payload → clean rows (pure)

- `extract_spot(payload) -> float` — `payload["records"]["underlyingValue"]`.
- `extract_expiries(payload, count) -> [iso]`.
- `rows_for_expiry(payload, iso_expiry, min, max) -> [{strike, ce, pe}]` — each leg is a
  dict `{oi, chg_oi, ltp, iv, volume}`; a missing leg defaults to zeros.
- `nearest_atm(spot, step) -> int`.

### `snapshot.py` — Assemble one cycle

- `build_snapshot(payload, timestamp_ist, prev_ltp) -> snapshot` — per expiry: `pcr`,
  `max_pain`, `support`, `resistance`, `ce_oi_total`, `pe_oi_total`, `verdict`, and
  `display_rows` (200-pt strikes) with buildup labels.
- `_buildup_for(leg, key, prev_ltp)` — returns `N/A` on a strike's first sighting;
  otherwise classifies from ΔLTP vs ΔOI.
- `ltp_index(snapshot)` — maps `(expiry, strike, leg) -> ltp` for the next cycle's
  `prev_ltp`.

### `writer.py` — All file output

| Function            | File                     | Mode              |
|---------------------|--------------------------|-------------------|
| `write_summary`     | `summary.csv`            | append            |
| `write_raw`         | `<expiry>_raw.csv`       | append            |
| `write_buildup`     | `<expiry>_buildup.csv`   | overwrite (latest)|
| `write_json_feed`   | `<expiry>.json`          | read-modify-write |
| `write_index`       | `index.json`             | overwrite         |
| `load_prev_ltp`     | reads `_raw.csv`         | read              |

`write_json_feed` is the heart of the dashboard feed — see §7 and §8.

---

## 6. Indicators (`indicators.py`)

All pure functions, no I/O.

### Buildup — `classify_buildup(chg_ltp, chg_oi)`

| ΔOI       | ΔLTP        | Label            | Meaning                 |
|-----------|-------------|------------------|-------------------------|
| = 0       | (any)       | `N/A`            | No OI change → no signal |
| > 0       | > 0         | `Long Buildup`   | Fresh longs (bullish)   |
| > 0       | ≤ 0         | `Short Buildup`  | Fresh shorts (bearish)  |
| < 0       | > 0         | `Short Covering` | Shorts exiting (bullish)|
| < 0       | ≤ 0         | `Long Unwinding` | Longs exiting (bearish) |

### PCR — `pcr(rows)`

`PCR = ΣPE_OI / ΣCE_OI`, rounded to 2 decimals; returns `0.0` if there is no CE OI.

### Max Pain — `max_pain(rows)`

The strike that minimizes total writer payout at expiry:

```
for each candidate expiry_price K*:
    pain = Σ over strikes k [ (K*-k)·CE_OI(k) if K*>k ]  +  Σ [ (k-K*)·PE_OI(k) if K*<k ]
max_pain = the K* with the smallest pain
```

### Support / Resistance

- `support(rows)` — strike with the highest **PE** OI (put writers defend it).
- `resistance(rows)` — strike with the highest **CE** OI (call writers defend it).

### Zone — `zone_200(strike)`

Returns the 200-pt band, e.g. `24800` → `"24800-25000"`.

### Verdict — `verdict(pcr_value, rows, atm)`

Currently a **PCR-only** heuristic (thresholds from `indicators.py`):

| PCR                    | Verdict           |
|------------------------|-------------------|
| ≥ 1.2 (`_BULLISH_PCR`) | `Leaning Bullish` |
| ≤ 0.8 (`_BEARISH_PCR`) and > 0 | `Leaning Bearish` |
| otherwise              | `Rangebound`      |

> Note: `rows` and `atm` are accepted for a future spot-vs-max-pain refinement but are
> not yet used in the verdict math.

### `display_strikes(rows, step)`

Keeps only rows where `strike % step == 0` (the 200-pt display subset).

---

## 7. Brewing-Move / OI-Surge Detection (`signals.py`)

**Idea:** the option chain is forward-looking. If OI at a strike is *surging* over the last
30 min or 1 hr, a price move is likely *building*. This module reads the feed's accumulated
`strikes_timeline` and flags surging strikes on the latest snapshot.

### Direction mapping

| Surging leg | Interpretation           | Direction |
|-------------|--------------------------|-----------|
| **PE**      | Support building         | `BULLISH` (favor CE) |
| **CE**      | Resistance building      | `BEARISH` (favor PE) |
| **Both** at same strike | Two-sided pinning | `PIN` (rangebound)   |

### Flagging rule (per leg, per window)

A window flags only if **both** thresholds clear:
`pct ≥ SURGE_PCT_THRESHOLD (30%)` **and** `delta ≥ SURGE_ABS_THRESHOLD (500K)`.
A leg with no prior baseline (`oi_past ≤ 0`) is skipped.

### Confidence

- `HIGH` if the leg flags in **≥ 2 windows**, **or** it is *textbook* — a PE surge **below**
  spot (real support) or a CE surge **above** spot (real resistance).
- `MEDIUM` otherwise.

### Output

`detect_brewing(strikes_timeline, spot, pct_threshold, abs_threshold, windows)` returns a
list of signals sorted by confidence (HIGH first) then by largest absolute surge. Each
signal carries `strike, leg, direction, confidence, windows, oi_now, side_of_spot`, plus
per-window `oi_past_*`, `pct_*`, `abs_*` stats. Returns `[]` when there are fewer than 2
snapshots or no window has enough history.

---

## 8. The `brewing_today` Accumulator (`writer.py`)

**The bug it fixes:** `write_json_feed` recomputes `brewing` against the *latest* snapshot
each cycle. Because a surge is transient, a strong mid-day signal would be gone (`brewing ==
[]`) by a quiet close — so the dashboard showed "nothing brewing" regardless of the day
selected.

**The fix — `_accumulate_brewing_today(existing, current, ts)`:** additive, never drops a
signal once seen. Signals are keyed by `(strike, leg, direction)`:

- **New key** → append with `first_seen = last_seen = ts`.
- **Existing key, stronger surge** (`_max_abs` higher) → replace stats, keep original
  `first_seen`, update `last_seen`.
- **Existing key, not stronger** → just update `last_seen`.

The feed therefore keeps a running, timestamped list of every surge seen during the session.
The dashboard prefers `brewing_today` and falls back to live `brewing` if the accumulator is
empty. Detection is wrapped in `try/except` so it can **never** break the fetch/write.

---

## 9. 5paisa API Integration and Spot Resolution (`fetcher.py`)

### Authentication (TOTP)

`_generate_totp(secret)` derives the current 6-digit code (RFC 6238) from the base32 TOTP
secret; `get_totp_session(client_code, totp, pin)` establishes the session. No 6-digit code
is ever stored — only the secret (a GitHub Secret).

### Methods used

| Method                                       | Purpose                    |
|----------------------------------------------|----------------------------|
| `get_totp_session(client_code, totp, pin)`   | Authenticate               |
| `get_expiry("N", "NIFTY")`                   | Expiry list (+ index LTP)  |
| `get_option_chain("N", "NIFTY", expiry_ts)`  | Chain for one expiry       |
| `fetch_market_feed_scrip([...])`             | Fallback spot lookup       |

### Spot resolution (order of precedence)

The pipeline is worthless with a wrong spot (it drives Max Pain, verdict, and brewing
side-of-spot). Resolution now tries three sources, in order, and **fails the cycle** rather
than faking a value:

1. **`lastrate` in the `get_expiry` response** — 5paisa returns the live NIFTY index LTP
   here, e.g. `lastrate: [{"ExchType": "C", "LTP": 24449.55, "ScripCode": 999920000}]`.
   `_spot_from_expiry_response()` reads `lastrate[0]["LTP"]` — no extra API call. This is the
   primary, most reliable source because the option-chain rows usually omit
   `UnderlyingValue`.
2. **`UnderlyingValue` / `SpotPrice` / `Spot`** on an option row (if present).
3. **Market feed** — `fetch_market_feed_scrip([{Exch:"N", ExchType:"C", ScripCode:999920000}])`.
   The NIFTY index lives on the **Cash** segment (`ExchType "C"`), **not** derivatives
   (`"D"`); the old code queried `"D"`, which silently returned nothing.

If all three fail, `fetch_option_chain()` raises `FetchError("Could not resolve NIFTY
spot...")`, which `main.py` treats as a clean, non-fatal skip. **No fabricated `24000.0`
fallback exists anymore** — an honest gap beats publishing garbage.

### Response transformation

5paisa's response is transformed into the NSE-compatible shape the rest of the pipeline
expects: `{"records": {"underlyingValue", "expiryDates", "data": [{strikePrice, expiryDate,
CE, PE}]}}`.

---

## 10. Market-Hours Guard (`clock.py`)

```python
def is_market_hours(now_ist) -> bool:
    if os.environ.get("FORCE_FETCH", "").lower() == "true":
        return True                      # manual runs bypass all checks
    if now_ist.weekday() >= 5:           # 5=Sat, 6=Sun — NSE closed
        return False
    open_t, close_t = time(*MARKET_OPEN), time(*MARKET_CLOSE)
    return open_t <= now_ist.time() <= close_t
```

The **weekend guard** was added because the previous version only checked the time-of-day —
so Saturday/Sunday runs published 5paisa's *frozen last-session* OI (and burned Actions
minutes). `now_ist` must already be in IST (see `main.now_ist()`).

---

## 11. GitHub Actions Workflow and External Cron

`.github/workflows/fetch.yml` (current):

```yaml
name: fetch-nifty-option-chain
on:
  schedule:
    - cron: "*/15 3-10 * * 1-5"   # ~ every 15 min during the IST market window
  workflow_dispatch:               # manual + external-cron trigger
permissions:
  contents: write
concurrency:
  group: fetch-nifty
  cancel-in-progress: false
jobs:
  fetch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt
      - name: Run fetch cycle
        run: python -m nifty_oc.main
        env:                         # all 9 secrets injected here (masked in logs)
          FIVEPAISA_APP_NAME: ${{ secrets.FIVEPAISA_APP_NAME }}
          # ... FIVEPAISA_APP_SOURCE, USER_ID, PASSWORD, USER_KEY, ENCRYPTION_KEY,
          #     CLIENT_CODE, TOTP_SECRET, PIN
      - name: Commit data if changed
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          if [ -d data/ ]; then
            git add data/
            git diff --staged --quiet || { git commit -m "data: snapshot"; git push; }
          fi
```

- GitHub's scheduled crons can lag under load; an **external cron (cron-job.org)** hits the
  `workflow_dispatch` endpoint every ~15 min for more reliable triggering.
- The in-code guard (`clock.py`) is the real gate — a triggered run outside market hours
  simply prints `[skip]` and exits 0.
- The commit step pushes only when `data/` actually changed, so quiet cycles produce no
  commit noise.

---

## 12. The Web Dashboard (`docs/`)

Static Plotly dashboard; loads `../data/index.json`, then the selected day/expiry feed.

### Controls
- **Day** dropdown — trade date.
- **Expiry** dropdown — weekly expiry.
- **Compare** checkboxes — overlay other days for the same expiry.

### Charts and panels
1. **Support/Resistance Walls** — CE OI (resistance) vs PE OI (support) bars per strike.
2. **Day Timeline** — spot, Max Pain, and PCR (right axis) through the day; comparison days
   render as dashed overlays.
3. **Buildup Map** (table) — per strike: CE/PE OI, ΔOI, buildup label, and zone. Rendered
   XSS-safe with `createElement`/`textContent` (never `innerHTML` with data).
4. **Per-strike OI Heatmaps** (CE and PE ΔOI):
   - **Active-strike filter** (`MIN_PEAK_OI = 1,000,000`) drops dead strikes so the map isn't
     mostly empty rows.
   - **Robust color cap** (~90th percentile) prevents one giant ΔOI from washing out the rest.
   - **Green/red diverging scale**, with **zero mapped to gray** (`#475569`, not the page
     background) and `xgap`/`ygap` so tiles are individually visible.
5. **Brewing Moves** cards — one card per accumulated `brewing_today` signal, showing
   direction/confidence and a `seen HH:MM` (or `seen HH:MM → HH:MM`) timestamp. Empty state:
   "No strong OI surges seen this session."

### TradingView-style zoom (all charts)

Uniform interaction config in `app.js`:

```js
const CHART_CONFIG = {
  responsive: true, scrollZoom: true,       // wheel zooms
  doubleClick: "reset",                      // double-click refits
  displayModeBar: true, displaylogo: false,
  modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"],
};
const CHART_INTERACTION_LAYOUT = { dragmode: "pan" };  // drag body to pan
```

Every `newPlot` spreads `CHART_INTERACTION_LAYOUT`, sets axis `fixedrange: false` (so
dragging an axis stretches it), and passes `CHART_CONFIG`. On categorical axes (heatmaps),
axis-drag stretch is "steppy" per cell — a Plotly characteristic, not a bug.

---

## 13. Data Formats

### `summary.csv` (append)
`timestamp_ist, trade_date, expiry, spot, atm, pcr, max_pain, support, resistance, ce_oi_total, pe_oi_total, verdict`

### `<expiry>_raw.csv` (append)
`timestamp_ist, expiry, ce_oi, ce_chg_oi, ce_ltp, ce_iv, ce_volume, strike, pe_volume, pe_iv, pe_ltp, pe_chg_oi, pe_oi, ce_buildup, pe_buildup`

### `<expiry>_buildup.csv` (overwrite — latest snapshot)
`strike, ce_oi, ce_chg_oi, ce_buildup, pe_oi, pe_chg_oi, pe_buildup, zone_200pt`

### `<expiry>.json` (dashboard feed)

```json
{
  "meta":   { "trade_date": "2026-08-11", "expiry": "2026-08-11", "updated_ist": "2026-08-11 15:30" },
  "timeline": [ { "t": "...", "spot": 24449.55, "pcr": 0.85, "max_pain": 24400,
                  "ce_oi_total": 0, "pe_oi_total": 0 } ],
  "strikes":  [ { "strike": 24400, "ce_oi": 0, "ce_chg_oi": 0, "ce_buildup": "Long Buildup",
                  "pe_oi": 0, "pe_chg_oi": 0, "pe_buildup": "Short Covering", "zone_200pt": "24400-24600", "...": "..." } ],
  "strikes_timeline": [ { "t": "...", "rows": [ { "strike": 24400, "ce_oi": 0, "pe_oi": 0 } ] } ],
  "brewing":       [ { "strike": 24400, "leg": "PE", "direction": "BULLISH", "confidence": "HIGH", "windows": ["30min"], "oi_now": 0, "side_of_spot": "below" } ],
  "brewing_today": [ { "strike": 24400, "leg": "PE", "direction": "BULLISH", "first_seen": "2026-08-11 11:15", "last_seen": "2026-08-11 13:00", "...": "..." } ]
}
```

### `index.json`
`{ "days": [ { "trade_date": "2026-08-11", "expiries": ["2026-08-11", "2026-08-18", "2026-08-25"] } ] }`

---

## 14. GitHub Secrets Setup

Settings → Secrets and variables → Actions → **New repository secret**. All 9 are required:

| Secret Name                | Source                          |
|----------------------------|---------------------------------|
| `FIVEPAISA_APP_NAME`       | 5paisa Developer Portal         |
| `FIVEPAISA_APP_SOURCE`     | 5paisa Developer Portal         |
| `FIVEPAISA_USER_ID`        | 5paisa Developer Portal         |
| `FIVEPAISA_PASSWORD`       | 5paisa Developer Portal         |
| `FIVEPAISA_USER_KEY`       | 5paisa Developer Portal         |
| `FIVEPAISA_ENCRYPTION_KEY` | 5paisa Developer Portal         |
| `FIVEPAISA_CLIENT_CODE`    | Your 5paisa account             |
| `FIVEPAISA_TOTP_SECRET`    | 5paisa 2FA setup (base32 key)   |
| `FIVEPAISA_PIN`            | Your 5paisa trading PIN         |

**TOTP secret** is the base32 key shown on the 2FA "Can't scan? Enter manually" screen
(e.g. `JBSWY3DPEHPK3PXP`) — **not** a 6-digit code. The code is regenerated each run.

---

## 15. Install, Run, and Test

### One-time repo setup
1. Public GitHub repo (free Actions minutes + Pages).
2. Settings → Actions → General → Workflow permissions → **Read and write**.
3. Settings → Pages → Source **Deploy from a branch** → default branch, folder **`/ (root)`**
   (root is required so `data/` at repo root is served; the dashboard fetches `../data`).
4. Add the 9 secrets (§14).

### Local run (Windows uses `python`, not `python3`)

```bash
pip install -r requirements.txt

# set the 9 FIVEPAISA_* env vars, then:
python -m nifty_oc.main            # respects the market-hours guard
# FORCE_FETCH=true bypasses the guard for a manual test

python -m pytest -q                # run the test suite
python -m http.server 8000 --directory docs   # preview dashboard at localhost:8000
```

---

## 16. Security Considerations

- **No secrets in the repo.** All credentials live in GitHub Secrets (encrypted, masked as
  `***` in logs). The repo is public, but only public market data is committed.
- **TOTP secret, not codes.** Only the base32 secret is stored; 6-digit codes are derived at
  runtime and never persisted.
- **XSS-safe dashboard.** All data-driven DOM uses `createElement` + `textContent`; never
  `innerHTML` with data.
- **Fail closed on bad data.** The fetcher raises rather than fabricating a spot, so a
  corrupt cycle is skipped instead of publishing misleading indicators.

---

## 17. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `[skip] outside market hours` | Weekend, or outside 09:15–15:30 IST | Expected; use `FORCE_FETCH=true` to test. |
| `[skip] fetch failed (non-fatal): Could not resolve NIFTY spot...` | None of the 3 spot sources returned a value | Confirm `get_expiry` carries `lastrate`; check the market-feed `ExchType` is `C`; inspect one run's `[debug]` logs. |
| `Missing credentials: ...` | A secret/env var is unset | Add all 9 secrets/vars. |
| `Illegal header value b'Bearer '` | TOTP auth failed | Verify `TOTP_SECRET` is the base32 key and `CLIENT_CODE`/`PIN` are correct. |
| Dashboard shows only sample data | No live `data/` yet, or Pages source is `/docs` not `/ (root)` | Set Pages source to root; wait for Pages deploy; hard-refresh. |
| Brewing panel empty on an old day | That day's feed predates the accumulator | Only cycles after deploying `brewing_today` populate it; not retroactive. |
| Workflow exit code 128 | Actions lacks write permission | Enable **Read and write permissions**. |

---

## 18. Recent Changes (Session Changelog)

All implemented locally (pushed manually by the maintainer). Highlights:

1. **`brewing_today` accumulator** (`writer.py`, `docs/app.js`, `docs/style.css`) — persists
   every intraday OI surge with `first_seen`/`last_seen`, fixing "Brewing Moves not
   updating." Additive; never drops a signal.
2. **Heatmap readability + color** (`docs/app.js`) — active-strike filter
   (`MIN_PEAK_OI = 1M`), robust ~90th-percentile color cap, green/red diverging scale,
   gray zero tiles, visible `xgap`/`ygap`.
3. **TradingView-style axis zoom** (`docs/app.js`) — uniform `CHART_CONFIG` +
   `CHART_INTERACTION_LAYOUT`: body-drag pan, axis-drag stretch, wheel zoom, double-click
   reset (spec + plan under `docs/superpowers/`).
4. **Weekend guard** (`clock.py`) — `weekday() >= 5` returns `False`; stops publishing frozen
   weekend OI and burning Actions minutes.
5. **Spot-resolution fix** (`fetcher.py`) — removed the silent `24000.0` fallback; added
   `_spot_from_expiry_response()` reading the `lastrate` index LTP as the primary source; and
   corrected the market-feed fallback `ExchType` from `"D"` → `"C"`. Confirmed against a live
   Actions log that resolved spot `24449.55`.

---

## 19. Known Limitations and Pending Work

### Known limitations
- **Not retroactive:** feeds published before the `brewing_today` change won't backfill.
- **Categorical axis stretch is "steppy"** on heatmaps (Plotly behavior).
- **Verdict is PCR-only** — `rows`/`atm` are plumbed but not yet used for a spot-vs-max-pain
  refinement.

### Pending: Falling-OI (UNWIND) detection — **not yet implemented**

`signals.py` currently detects **increases** only. Four **intentionally red** tests in
`tests/test_signals.py` specify the next feature:

- `test_ce_unwind_above_spot_is_bullish`
- `test_pe_unwind_below_spot_is_bearish`
- `test_build_tags_kind_build`
- `test_ce_unwind_pe_build_same_strike_not_pinned`

**Required behavior:**
- Detect OI **decreases** with symmetric thresholds (mirror of the surge rule).
- Add a `kind` field: `"BUILD"` (rising OI) vs `"UNWIND"` (falling OI).
- Direction on unwind: **CE unwind → BULLISH** (resistance melting), **PE unwind → BEARISH**
  (support melting).
- **PIN only when the two legs conflict** at a strike — a CE-unwind alongside a PE-build at
  the same strike is *not* a pin.

This is the single open task; running `python -m pytest -q` today shows **77 passing, 4
failing** (exactly these UNWIND specs).

---

## 20. Appendix: Module and Test Summary

### Modules

| File                    | Responsibility                                            |
|-------------------------|-----------------------------------------------------------|
| `nifty_oc/main.py`      | Orchestrate a cycle; non-fatal fetch skip.                |
| `nifty_oc/config.py`    | Constants + surge thresholds + market window.             |
| `nifty_oc/clock.py`     | Weekend + time-window market-hours guard.                 |
| `nifty_oc/fetcher.py`   | 5paisa TOTP auth, chain fetch, 3-tier spot resolution.    |
| `nifty_oc/dates.py`     | NSE expiry parse/select.                                  |
| `nifty_oc/parse.py`     | Raw payload → clean rows (pure).                          |
| `nifty_oc/indicators.py`| PCR, Max Pain, S/R, buildup, verdict (pure).              |
| `nifty_oc/signals.py`   | Brewing-move (OI-surge) detection (pure).                 |
| `nifty_oc/snapshot.py`  | Assemble computed snapshot per expiry.                    |
| `nifty_oc/writer.py`    | CSV/JSON writers + `brewing_today` accumulator.           |
| `docs/app.js`           | Dashboard load, charts, heatmaps, zoom config.            |

### Test coverage

`python -m pytest -q` → **81 tests: 77 passing, 4 pending** (the UNWIND specs in §19).
Test files: `test_clock`, `test_dates`, `test_fetcher`, `test_indicators`, `test_main`,
`test_parse`, `test_signals`, `test_snapshot`, `test_writer`.

### URLs

| Resource            | URL                                                    |
|---------------------|--------------------------------------------------------|
| Repository          | https://github.com/ddtambe/Nifty50_Options             |
| Live dashboard      | https://ddtambe.github.io/Nifty50_Options/docs/        |
| Actions             | https://github.com/ddtambe/Nifty50_Options/actions     |
| 5paisa Developer API| https://www.5paisa.com/developerapi                    |
| py5paisa SDK        | https://github.com/OpenApi-5p/py5paisa                 |

---

**End of Documentation**
