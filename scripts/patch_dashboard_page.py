#!/usr/bin/env python3
"""Builds docs/mf-dashboard.html and docs/mf-debt-dashboard.html: pulls the live MF Returns Dashboard from tools.drbrokers.in
and patches it to read every fund's NAV at each target date from ONE mirror file
(dash-navs.json, built daily from AMFI) instead of ~1,300 per-fund mfapi calls.
The original mfapi path stays as an automatic fallback."""
import os, urllib.request

SRC_URL = "https://tools.drbrokers.in/MF_Dashboard"
A = "  // 4) Fetch NAV history for all candidate codes from mfapi.in (throttled)\n"
B = "  if(!snaps.latest){ hideProgress();"
HELPER_AFTER = "// ---------- CSV parser (simple but quote-aware) ----------"
HELPER = '''// ---------- One-file NAV snapshot (DR Brokers NAV mirror, built daily from AMFI) ----------
const DASH_NAVS_URL = "https://sahilaggarwal27.github.io/drbrokers-nav-mirror/dash-navs.json";
async function loadDashSnaps(){
  const r = await fetch(DASH_NAVS_URL, {cache:"no-cache"});
  if(!r.ok) throw new Error("HTTP " + r.status);
  const j = await r.json();
  const snaps = {};
  j.keys.forEach((k, i) => { snaps[k] = { date: parseMfDate(j.dates[i]), map: Object.create(null) }; });
  let n = 0;
  for(const code in j.f){
    const a = j.f[code];
    for(let i = 0; i < j.keys.length; i++){ if(a[i]) snaps[j.keys[i]].map[code] = { nav: a[i] }; }
    n++;
  }
  if(n < 100) throw new Error("snapshot too small (" + n + ")");
  return snaps;
}

'''


def run(root):
    for fn in (run_equity, run_debt):
        try:
            fn(root)
        except Exception as e:
            print(f"  {fn.__name__} skipped: {e}")


def run_equity(root):
    req = urllib.request.Request(SRC_URL, headers={"User-Agent": "drbrokers-nav-mirror/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        s = r.read().decode("utf-8")
    if s.count(A) != 1 or s.count(B) != 1 or s.count(HELPER_AFTER) != 1:
        print("  mf-dashboard: source changed, markers missing — skipped")
        return False
    i, j = s.index(A), s.index(B)
    old = s[i:j]
    if old.count("const snaps = {};") != 1:
        print("  mf-dashboard: snaps block changed — skipped")
        return False
    inner = old.replace("const snaps = {};", "snaps = {};")
    inner = "\n".join(("  " + ln) if ln.strip() else ln for ln in inner.split("\n"))
    new = ('''  // 4) NAVs at each target date from ONE precomputed mirror file (AMFI, built daily).
  //    Falls back to per-fund mfapi fetch only if that file is unavailable.
  showProgress("Loading NAV snapshot…", 40);
  let snaps = null;
  try { snaps = await loadDashSnaps(); } catch(e){ console.warn("dash-navs.json failed, falling back to mfapi", e); }
  if(!snaps){
''' + inner.rstrip() + "\n  }\n")
    s = s[:i] + new + s[j:]
    s = s.replace(HELPER_AFTER, HELPER + HELPER_AFTER, 1)
    s = s.replace('const CACHE_KEY = "mf_dashboard_v11_mfapi";', 'const CACHE_KEY = "mf_dashboard_v12_snap";', 1)
    s = s.replace("NAV + scheme list: <b>mfapi.in</b>", "NAV: <b>AMFI (DR Brokers mirror)</b>", 1)
    s = s.replace('Returns from AMFI end-of-day NAVs (via <a href="https://www.mfapi.in" style="color:var(--accent)">mfapi.in</a>).',
                  'Returns from AMFI end-of-day NAVs (DR Brokers AMFI mirror, refreshed daily; mfapi.in as fallback).', 1)
    with open(os.path.join(root, "docs", "mf-dashboard.html"), "w", encoding="utf-8") as f:
        f.write(s)
    print("  mf-dashboard.html written")
    return True


DEBT_URL = "https://tools.drbrokers.in/MF_Debt_Dashboard"
DEBT_FETCH = """  const navMap = await fetchNavBatched(codes, (done, total) => {
    showProgress(`Fetching NAV history from mfapi.in… ${done}/${total} funds`, 28 + (done/total)*60);
  });
"""
DEBT_FETCH_NEW = """  // NAVs from ONE precomputed mirror file (AMFI, built daily); mfapi per-fund only as fallback.
  showProgress("Loading NAV snapshot…", 40);
  let navMap = null;
  try { navMap = await loadDashNavMap(codes); if(navMap.size < 50) navMap = null; }
  catch(e){ console.warn("dash-navs.json failed, falling back to mfapi", e); navMap = null; }
  if(!navMap) navMap = await fetchNavBatched(codes, (done, total) => {
    showProgress(`Fetching NAV history from mfapi.in… ${done}/${total} funds`, 28 + (done/total)*60);
  });
"""
DEBT_HELPER_AFTER = "function parseCSV(text){"
DEBT_HELPER = """// ---------- One-file NAV snapshot (DR Brokers NAV mirror, built daily from AMFI) ----------
// Builds mfapi-shaped newest-first histories holding just the target-date NAVs.
const DASH_NAVS_URL = "https://sahilaggarwal27.github.io/drbrokers-nav-mirror/dash-navs.json";
async function loadDashNavMap(codes){
  const r = await fetch(DASH_NAVS_URL, {cache:"no-cache"});
  if(!r.ok) throw new Error("HTTP " + r.status);
  const j = await r.json();
  const want = new Set(codes), m = new Map();
  const order = j.keys.map((k, i) => i).sort((a, b) => parseMfDate(j.dates[b]) - parseMfDate(j.dates[a]));
  for(const code in j.f){
    if(!want.has(code)) continue;
    const a = j.f[code], arr = [], seen = new Set();
    for(const i of order){
      if(!a[i] || seen.has(j.dates[i])) continue;
      seen.add(j.dates[i]); arr.push({ date: j.dates[i], nav: String(a[i]) });
    }
    if(arr.length && arr[0].date === j.dates[0]) m.set(code, arr);
  }
  return m;
}

"""


def run_debt(root):
    req = urllib.request.Request(DEBT_URL, headers={"User-Agent": "drbrokers-nav-mirror/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        s = r.read().decode("utf-8")
    if s.count(DEBT_FETCH) != 1 or s.count(DEBT_HELPER_AFTER) != 1:
        print("  mf-debt-dashboard: source changed, markers missing — skipped")
        return False
    s = s.replace(DEBT_FETCH, DEBT_FETCH_NEW, 1)
    s = s.replace(DEBT_HELPER_AFTER, DEBT_HELPER + DEBT_HELPER_AFTER, 1)
    s = s.replace('const CACHE_KEY = "mf_debt_dashboard_v3_mfapi";', 'const CACHE_KEY = "mf_debt_dashboard_v4_snap";', 1)
    s = s.replace("NAV + scheme list: <b>mfapi.in</b>", "NAV: <b>AMFI (DR Brokers mirror)</b>", 1)
    with open(os.path.join(root, "docs", "mf-debt-dashboard.html"), "w", encoding="utf-8") as f:
        f.write(s)
    print("  mf-debt-dashboard.html written")
    return True


if __name__ == "__main__":
    run(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
