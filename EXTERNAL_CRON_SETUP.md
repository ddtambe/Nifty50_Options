# Reliable Scheduling via External Cron

## Why

GitHub's built-in `schedule:` (cron) trigger is **unreliable** for public repos. Evidence
from this repo: with a `*/5 * * * *` cron set, runs still skipped 2+ hour gaps and only
fired ~2×/day instead of every 5 min. GitHub does not guarantee scheduled runs and
deprioritizes them under load
([reference](https://upptime.js.org/blog/2021/01/22/github-actions-schedule-not-working/)).

**Fix:** Keep `workflow_dispatch` (manual/API trigger — this works 100% of the time) and
call it from an external scheduler every 15 minutes.

---

## Step 1 — Create a GitHub Personal Access Token (fine-grained)

1. Go to: https://github.com/settings/personal-access-tokens/new
2. **Token name:** `nifty-oc-cron`
3. **Expiration:** 90 days (renew when it expires)
4. **Resource owner:** your account (`ddtambe`)
5. **Repository access:** "Only select repositories" → pick **Nifty50_Options**
6. **Permissions → Repository permissions → Actions:** set to **Read and write**
7. Click **Generate token** and **copy it** (starts with `github_pat_...`).
   You will paste it into cron-job.org next. Do NOT commit it anywhere.

---

## Step 2 — Create the cron job at cron-job.org

1. Sign up (free): https://cron-job.org
2. **Create cronjob** → configure:

   **URL:**
   ```
   https://api.github.com/repos/ddtambe/Nifty50_Options/actions/workflows/fetch.yml/dispatches
   ```

   **Schedule:** Every 15 minutes, Mon–Fri, 09:00–16:00 IST
   - In "Custom" / expert mode, set: minutes `0,15,30,45`, hours `9-15` (IST if the
     service supports timezone; otherwise use UTC `3-10` and any minutes).
   - Simplest: "Every 15 minutes" and let the workflow's own market-hours guard skip
     off-hours runs.

   **Request method:** `POST`

   **Request headers** (Advanced → Headers):
   ```
   Accept: application/vnd.github+json
   Authorization: Bearer github_pat_YOUR_TOKEN_HERE
   X-GitHub-Api-Version: 2022-11-28
   Content-Type: application/json
   ```

   **Request body:**
   ```json
   {"ref": "main"}
   ```

3. Save. Use "Test run" to confirm it returns **HTTP 204** (success, no content).

---

## Step 3 — Verify

- After a test run, check: https://github.com/ddtambe/Nifty50_Options/actions
- You should see a new `fetch-nifty-option-chain` run with event **workflow_dispatch**.
- The external service now triggers it reliably every 15 min.

---

## Notes

- The GitHub `schedule:` cron can stay in `fetch.yml` as a best-effort backup — it does no
  harm. The external cron is the reliable path.
- If the token expires, runs stop — renew it and update the header in cron-job.org.
- Market-hours guard: the workflow only writes data during 9:15 AM–3:30 PM IST, so
  off-hours triggers are cheap no-ops (unless `FORCE_FETCH` is set, which was removed).

---

## Quick manual test from your machine (optional)

Run this in Git Bash to trigger a run right now (replace the token):

```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer github_pat_YOUR_TOKEN_HERE" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/ddtambe/Nifty50_Options/actions/workflows/fetch.yml/dispatches \
  -d '{"ref":"main"}'
```

Expect no output and HTTP 204. Then check the Actions tab.
