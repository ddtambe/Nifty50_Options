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
- Live dashboard: `https://<your-user>.github.io/<repo>/docs/`.

## One-time setup

1. **Create a public GitHub repo** and push this project.
2. **Enable Actions write permission:** Settings → Actions → General → Workflow
   permissions → **Read and write permissions** → Save.
3. **Enable GitHub Pages:** Settings → Pages → Build and deployment → Source: **Deploy
   from a branch** → Branch: `master` (your default branch), folder: **`/ (root)`** →
   Save. Root is required because the workflow commits live data to `data/` at the repo
   root; the dashboard at `docs/` fetches `../data`. Publishing only `/docs` would leave
   `data/` unserved and the dashboard would show only the bundled sample.
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
