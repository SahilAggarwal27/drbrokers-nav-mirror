# DR Brokers NAV Mirror

Self-hosted daily NAV cache so DR Brokers dashboards stop depending on the flaky
`api.mfapi.in`. Pulls **AMFI's own data** and serves per-scheme JSON in the **exact
shape mfapi returns** — so tools need only a one-line base-URL swap.

**Why this exists:** every dashboard fetched NAVs live from mfapi.in. When mfapi has
a bad day (frequent 502s), all tools blank at once. This mirror is served from your
own infrastructure and doesn't go down when mfapi does.

```
scripts/seed_history_amfi.py  # ONE-TIME: rebuild 20yr year-end history from AMFI's history report (NO mfapi)
scripts/build_nav.py          # daily: AMFI NAVAll.txt -> per-scheme JSON (docs/mf/<code>.json), appends today's point
scripts/seed_from_mfapi.py    # OPTIONAL fallback seeder from mfapi (only if AMFI history report is unavailable)
client/navfetch.js            # drop-in fetcher for all tools: mirror-first, mfapi fallback, last-good
.github/workflows/build-nav.yml  # runs build daily, commits history, deploys to Pages (ADD MANUALLY — see below)
docs/                         # published root (GitHub Pages)
data/history/<code>.json      # persistent accumulated NAV points (committed by the bot)
```

## Response shape (matches mfapi exactly)
```json
{ "meta": { "scheme_code": 120587, "scheme_name": "ICICI Prudential FMCG Fund Direct Plan Growth" },
  "data": [ { "date": "28-08-2026", "nav": "447.74" }, ... ] }   // newest-first
```

## One-time setup

1. **Enable Pages:** repo Settings -> Pages -> Source = **GitHub Actions**.

2. **Add the workflow file manually.** The API connector can't write to
   `.github/workflows/` (needs a special scope), so create it in the browser:
   repo -> Add file -> Create new file -> path `.github/workflows/build-nav.yml`
   -> paste the workflow (provided separately) -> Commit.

3. **Bootstrap 20 years of history:** clone the repo locally and run:
   ```bash
   python scripts/seed_history_amfi.py
   git add data/history docs/mf && git commit -m "seed history" && git push
   ```
   This pulls year-end NAVs 2007..now from AMFI's own history report — **no mfapi
   needed**. (~20 requests, a couple of minutes.) After this the mirror is complete.

4. **Run the workflow once** (Actions -> Build NAV mirror -> Run workflow) to publish
   and verify daily updates work.

## Wire the tools to the mirror

Add the module and swap the fetch. In each dashboard's `<head>`:
```html
<script src="https://sahilaggarwal27.github.io/drbrokers-nav-mirror/client/navfetch.js"></script>
```
Then replace the tool's own `fetchNavHistoryOnce(code)` body with:
```js
async function fetchNavHistoryOnce(code, timeoutMs){
  NavFetch.configure({ perReqTimeoutMs: timeoutMs || 10000 });
  const r = await NavFetch.fetchOne(code);
  if (r.retry) return { retry:true };
  return { data: r.data || [], name: r.name || "" };
}
```
Everything downstream (snapshot building, sector matching) is unchanged — the shape
is identical to what the tools already parse.

**Go fully mfapi-independent:** once seeded, set `useMfapiFallback:false` in
`NavFetch.configure({...})`. The tools then never touch mfapi at all.

## Freshness / health
`docs/manifest.json` carries `generated_ist` and `scheme_count` — surface it in the
UI as a "NAV as of <date>" banner so users know the data is fresh.

## Notes
- AMFI's `NAVAll.txt` has **no history** — only today. The 20-year archive comes from
  `seed_history_amfi.py` (AMFI's history report); the daily build then keeps it current.
- `build_nav.py` aborts if it parses <1000 rows, so a bad AMFI pull never overwrites good data.
- Runs are idempotent: re-running on the same day upserts today's point, never duplicates.
