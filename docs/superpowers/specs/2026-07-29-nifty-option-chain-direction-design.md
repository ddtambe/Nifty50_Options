# Nifty 50 Option-Chain Direction Tool — Design Spec

**Date:** 2026-07-29
**Status:** Approved for planning
**Owner:** dtambe

---

## 1. Purpose

Read the likely intraday/closing **direction bias** of the Nifty 50 index from NSE
option-chain data, fully hands-off, and present it as CSV files **plus a live
GitHub Pages web dashboard** so the user can make the **manual** call on where price is
likely to close.

This tool does **not** predict price with certainty. It computes the standard evidence
traders use — per-strike buildup/unwinding, PCR, Max Pain, and support/resistance OI
walls — refreshes it on a schedule, and lays it out clearly. The trade decision stays
with the user.

---

## 2. Success Criteria

- Every ~15 minutes during market hours, a fresh snapshot is fetched, computed, and
  committed to the repository without any local machine running.
- Two extra closing snapshots are captured near **15:25** and **15:30 IST**.
- Three expiries are tracked each cycle: **current, next, next-to-next**.
- Output is human-readable CSVs (for Excel) plus JSON feeds that power a live,
  interactive web dashboard, organized by trading day.
- Indicator math (PCR, Max Pain, support/resistance) is accurate.
- A missed/blocked cycle never crashes the pipeline; the next cycle recovers.
- The web dashboard is served free via GitHub Pages and auto-updates as each cycle
  commits new data.

---

## 3. Architecture Overview

The only moving part is **GitHub Actions** (cloud). It wakes on a cron schedule, runs a
stateless Python job (fetch → compute → write files → commit), then sleeps. There is
**no local machine, no Google Cloud, no service account, and no external credentials.**
Files are committed back into the repo using GitHub's built-in `GITHUB_TOKEN`.

```
Every ~15 min (GitHub Actions cron, guarded to market hours in code):
  main.py
    ├─ fetcher.py     → prime cookies, GET NSE option chain (3 expiries), retry on block
    ├─ indicators.py  → buildup/unwinding, PCR, Max Pain, support/resistance, verdict
    ├─ writer.py      → append summary.csv & raw.csv, rewrite buildup.csv,
    │                    emit JSON feeds + index.json for the web dashboard
    └─ git commit + push (GITHUB_TOKEN)
  exit

GitHub Pages serves docs/ as a static site:
  docs/index.html + app.js (Plotly.js) → fetch JSON feeds → render charts in the browser
  (no server; runs entirely client-side, auto-reflects newly committed data)
```

---

## 4. Runtime & Scheduling

- **Platform:** GitHub Actions, **public** repository (unlimited free Actions minutes;
  code is visible — no credentials exist anywhere, so nothing sensitive is exposed).
- **Regular cadence:** cron every 15 minutes.
- **Extra closing snapshots:** explicit cron entries near **15:25** and **15:30 IST**.
- **Market-hours guard (in code):** each run exits immediately unless the current IST
  time is within **09:15–15:30**, so off-hours cron ticks cost nothing.
- **Cron drift caveat:** GitHub cron runs in UTC and can be delayed a few minutes under
  load. It is not a precise stopwatch. Every row stamps the **real fetch time**, so a
  delayed run is always visible. Exact-to-the-second closing prints are not guaranteed
  from cloud cron (only a local machine can do that); minor drift is acceptable for
  reading closing buildup.

---

## 5. Data Source & NSE Handling

- **Endpoint:** `https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY`
  (the JSON behind the option-chain page).
- **Access pattern:** a `requests.Session` first visits the NSE homepage to obtain
  cookies, sends browser-like headers (User-Agent, Accept, Referer), then calls the API.
- **Retry:** exponential backoff on 401/403/429/timeout within a run.
- **Known risk:** NSE actively throttles datacenter IPs (which GitHub uses). Mitigations
  above work most of the time but cannot be guaranteed. If a run is still blocked, it
  **logs the failure and exits cleanly**; the next scheduled run retries. Documented
  fallback: run the same script locally on demand from a residential connection. This
  risk is inherent to scraping NSE from the cloud and cannot be fully eliminated in code.

---

## 6. Strike Selection

Hardcoded, user-editable range in `config.py` (not auto ATM-relative):

```python
STRIKE_MIN  = 21000   # bottom strike to include (user edits)
STRIKE_MAX  = 30000   # top strike to include   (user edits)
STRIKE_STEP = 50      # Nifty native strike gap
DISPLAY_STEP = 200    # strikes shown/stored in output files
```

**Compute vs. display (important design decision):**

- **Compute** PCR, Max Pain, support, and resistance on **all 50-step strikes** within
  `[STRIKE_MIN, STRIKE_MAX]`. These indicators are sums/aggregations across every strike;
  skipping strikes would make PCR and Max Pain inaccurate.
- **Store & display** rows and charts at **200-step strikes only** (21000, 21200, …,
  30000) for a clean, readable view — this honors the user's "200" preference for what
  they look at.
- A single flag can switch to capturing only 200-step strikes everywhere (including the
  math), at the cost of less-accurate PCR/Max Pain. Default is the split behavior above.

Per kept strike, both **CE** and **PE** legs are recorded: OI, change-in-OI, LTP, IV,
volume.

---

## 7. Indicators (the "brains")

Computed per snapshot across the three expiries.

### 7.1 Buildup / Unwinding

Classified per leg from change in LTP vs. change in OI, comparing the current snapshot to
the **previous snapshot** (the last matching rows in `raw.csv`):

| Price (LTP) | Open Interest | Label            | Reads as |
|-------------|---------------|------------------|----------|
| Up          | Up            | **Long Buildup** | Fresh buyers, bullish |
| Down        | Up            | **Short Buildup**| Fresh sellers, bearish |
| Up          | Down          | **Short Covering**| Sellers exiting, bullish |
| Down        | Down          | **Long Unwinding**| Buyers exiting, bearish |

The very first snapshot of a day has no previous snapshot to diff against; buildup is
labeled `N/A` for that cycle and computed normally from the second snapshot onward.

### 7.2 PCR (Put-Call Ratio, by OI)

`PCR = Σ(PE OI) / Σ(CE OI)` over all 50-step strikes in range, per expiry.
`> 1` = bullish lean, `< 1` = bearish lean; extremes can signal reversal.

### 7.3 Max Pain

The strike at which total option-writer payout is minimized (price "magnet" toward
expiry), computed across all 50-step strikes.

### 7.4 Support / Resistance

- **Support** = strike with the highest **PE** OI.
- **Resistance** = strike with the highest **CE** OI.
- Also rolled up into **200-point zones** so the user sees support/resistance *bands*,
  not just single strikes.

### 7.5 Verdict

A one-line combined read (e.g., "Leaning Bullish", "Leaning Bearish", "Rangebound")
derived from PCR level/trend plus the dominant buildup pattern around ATM.

---

## 8. Output Files (committed to repo, day-wise)

```
data/
  2026-07-29/                       # trade date (one folder per trading day)
    summary.csv                     # APPEND: 1 row per (snapshot × expiry)
    2026-07-31_raw.csv              # APPEND: every displayed strike, every snapshot
    2026-08-07_raw.csv              # next expiry
    2026-08-14_raw.csv              # next-to-next expiry
    2026-07-31_buildup.csv          # REWRITTEN each run: latest snapshot, readable
    2026-08-07_buildup.csv
    2026-08-14_buildup.csv
    2026-07-31.json                 # per-expiry JSON feed for the web dashboard
    2026-08-07.json                 # (timeline + latest strike rows + buildup labels)
    2026-08-14.json
  index.json                        # lists available trading days & expiries (feeds switchers)

docs/                               # GitHub Pages site root (static, client-side)
  index.html                        # dashboard shell + expiry/day dropdowns
  app.js                            # loads index.json + selected JSON feed, draws Plotly charts
  style.css
```

**JSON feed shape (`data/<day>/<expiry>.json`):** an object with
`{ meta: {trade_date, expiry, updated_ist}, timeline: [ {t, spot, pcr, max_pain} ... ],
strikes: [ {strike, ce_oi, ce_chg_oi, ce_buildup, pe_oi, pe_chg_oi, pe_buildup, zone_200pt} ... ] }`.
`index.json` is `{ days: [ {trade_date, expiries: [...]} ... ] }`. These are the exact
fields the CSVs already carry, re-serialized for the browser — a single source of truth
in `indicators.py`.

### 8.1 `summary.csv` columns
`timestamp_ist, trade_date, expiry, spot, atm, pcr, max_pain, support, resistance,
ce_oi_total, pe_oi_total, verdict`
- `timestamp_ist` format `YYYY-MM-DD HH:MM`; `trade_date`/`expiry` format `YYYY-MM-DD`.

### 8.2 `<expiry>_raw.csv` columns
`timestamp_ist, expiry, ce_oi, ce_chg_oi, ce_ltp, ce_iv, ce_volume, strike,
pe_volume, pe_iv, pe_ltp, pe_chg_oi, pe_oi, ce_buildup, pe_buildup`
(standard option-chain layout: CE on the left, strike in the middle, PE on the right).

### 8.3 `<expiry>_buildup.csv` columns
`strike, ce_oi, ce_chg_oi, ce_buildup, pe_oi, pe_chg_oi, pe_buildup, zone_200pt`
- Rewritten each cycle so it always reflects the latest picture.

**CSV number format:** `change-in-OI` is stored as a plain signed integer
(`-15200`, `22400`) — **no leading `+`**, because Excel interprets a leading `+` as a
formula. Negative sign is preserved.

---

## 9. Web Dashboard (GitHub Pages)

A static, client-side web page served free from the repo's `docs/` folder via **GitHub
Pages** (URL: `https://<user>.github.io/<repo>/`). It loads the committed **JSON feeds**
in the browser and renders interactive charts with **Plotly.js** (loaded from CDN — no
build step). It auto-reflects new data as each cycle commits; the user just refreshes.

**Views (all four):**

1. **Strike-wise OI walls** — bar chart of CE OI vs PE OI across (200-step) strikes for
   the selected expiry; the support/resistance wall profile. (Primary "strike-wise
   graph" request.)
2. **Day timeline** — line chart of Spot vs Max Pain vs PCR over the trading day
   (direction drift + magnet).
3. **Buildup heatmap/table** — latest snapshot per strike, color-coded by Long Buildup /
   Short Buildup / Short Covering / Long Unwinding; the at-a-glance action map.
4. **Expiry + day switcher** — dropdowns to select which of the 3 expiries and which
   trading day to view; populated from `index.json`.

**Data format:** Plotly reads JSON, so `writer.py` emits compact JSON feeds alongside the
CSVs (see §8). The web page is **read-only** and does no computation beyond charting; all
indicators are precomputed by `indicators.py`.

**matplotlib is not used** — the interactive web page replaces static PNGs. CSVs remain
committed so the user can still chart in Excel/Sheets independently.

---

## 10. Module Structure

```
nifty_oc/
  config.py     # STRIKE_MIN/MAX/STEP, DISPLAY_STEP, symbol, market hours, expiry count, trigger times, file names
  fetcher.py    # NSE session, cookie priming, GET per expiry, retry/backoff
  indicators.py # pure functions: buildup, PCR, max pain, support/resistance, verdict
  writer.py     # build/append summary & raw & buildup CSVs, emit JSON feeds + index.json
  main.py       # market-hours guard → fetch 3 expiries → compute → write → (Actions commits)
docs/
  index.html    # GitHub Pages dashboard shell + expiry/day switchers
  app.js        # client-side: load index.json + selected feed, render Plotly charts
  style.css
.github/workflows/fetch.yml   # cron: every 15 min + ~15:25 & ~15:30 IST closing snapshots
requirements.txt              # requests, pandas   (no matplotlib)
tests/                        # unit tests for indicators.py
README.md                     # one-time setup: enable Actions write permission + GitHub Pages
```

Design intent: small, focused files. `indicators.py` is pure and independently unit-tested;
`fetcher.py` isolates all NSE quirks; `writer.py` isolates all file/JSON I/O; `main.py`
is thin orchestration; the `docs/` web app is read-only and does no computation.

---

## 11. Error Handling

- **NSE blocked / network error:** retry with backoff; if still failing, log and exit 0
  (non-fatal) so the workflow is green and the next cycle retries.
- **Off market hours:** guard exits immediately, no fetch, no commit.
- **Malformed/empty JSON:** validated at the boundary in `fetcher.py`; a bad payload is
  treated as a failed fetch (skip cycle), never written as garbage rows.
- **First snapshot of day:** buildup = `N/A` (no previous snapshot to diff).

---

## 12. Testing

- **Unit tests (`tests/`)** for `indicators.py` against synthetic option-chain fixtures:
  - buildup classification (all four quadrants + N/A first-snapshot case)
  - PCR calculation
  - Max Pain calculation
  - support/resistance selection and 200-pt zone rollup
- Target: the indicator logic (the part that must be correct) is covered; fetch/IO are
  thin and validated manually against a live NSE payload during setup.
- The `docs/` web app is verified manually in a browser against committed sample JSON
  (open `index.html` locally, confirm charts render and the switchers work).

---

## 13. Non-Goals (YAGNI)

- No machine-learning or probabilistic price prediction.
- No server-side/backend web app — the dashboard is static, client-side only.
- No static PNG charts (replaced by the interactive web dashboard).
- No broker/trade integration or order placement.
- No Google Sheets / Google Cloud (removed).
- No historical backfill of past days.

---

## 14. Confirmed Decisions

| Item | Decision |
|------|----------|
| Runtime | GitHub Actions (cloud), no local machine |
| Storage | CSV files (for Excel) + JSON feeds (for the web page), committed day-wise |
| Charts | Live **GitHub Pages** dashboard with **Plotly.js** (no PNGs); CSVs remain for manual charting |
| Dashboard views | Strike-wise OI walls, day timeline (Spot/MaxPain/PCR), buildup heatmap/table, expiry+day switcher |
| Expiries | Current + next + next-to-next |
| Schedule | Every 15 min + ~15:25 & ~15:30 IST |
| Strike range | Hardcoded `STRIKE_MIN=21000`, `STRIKE_MAX=30000`, user-editable |
| Strike display | 200-step strikes for storage/display; 50-step for internal PCR/Max Pain math |
| Repo visibility | **Public** |
