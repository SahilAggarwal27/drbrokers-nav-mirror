#!/usr/bin/env python3
"""Builds docs/sector-cycle.html: pulls the live Sector Cycle page from tools.drbrokers.in
and patches it to load year-end NAVs from ONE mirror file (snapshots.json) instead of
~16k per-fund mfapi calls. Only the ~60 chosen sector funds still get full daily history
from mfapi (2006 anchor + momentum). Runs inside the daily mirror build."""
import os, urllib.request

SRC_URL = "https://tools.drbrokers.in/MF_Sector_Cycle"

PATCHES = [
('''const MFAPI_BASE = "https://api.mfapi.in/mf/";''','''const MFAPI_BASE = "https://api.mfapi.in/mf/";
// One-file year-end snapshot of every scheme, rebuilt daily from AMFI by the NAV mirror.
const SNAP_URL = "https://sahilaggarwal27.github.io/drbrokers-nav-mirror/snapshots.json";'''),

('''// Throttled batch pre-fetch of NAV history for scheme codes into _NAVHIST.
async function primeNavHistory(codes, onProgress){
  const need = codes.filter(c => c && !_NAVHIST.has(c));''','''// Load year-end + latest NAVs for all wanted codes from ONE mirror file into _NAVHIST
// (synthetic newest-first histories: latest point + each 31-Dec on-or-before NAV).
async function loadSnapshotBundle(codes){
  const r = await fetch(SNAP_URL, {cache:"no-cache"});
  if(!r.ok) throw new Error("snapshots.json HTTP " + r.status);
  const j = await r.json();
  const want = new Set(codes);
  let n = 0;
  for(const code in j.f){
    if(!want.has(code)) continue;
    const [name, ld, ln, ye] = j.f[code];
    const ldT = _parseMfDate(ld).getTime();
    const arr = [{date: ld, nav: String(ln)}];
    for(let i = ye.length - 1; i >= 0; i--){
      if(!ye[i]) continue;
      const d = "31-12-" + j.years[i];
      if(_parseMfDate(d).getTime() >= ldT) continue;
      arr.push({date: d, nav: String(ye[i])});
    }
    _NAVHIST.set(code, arr);
    if(name) _NAVNAME.set(code, name);
    n++;
  }
  return n;
}
// Throttled batch pre-fetch of NAV history for scheme codes into _NAVHIST.
// force=true re-pulls codes already present (used to upgrade synthetic -> full daily history).
async function primeNavHistory(codes, onProgress, force=false){
  const need = codes.filter(c => c && (force || !_NAVHIST.has(c)));'''),

('''        if(!r.ok){ _NAVHIST.set(code, []); return; }
        const j = await r.json();
        _NAVHIST.set(code, (j && j.data && j.data.length) ? j.data : []);
        if(j && j.meta && j.meta.scheme_name) _NAVNAME.set(code, j.meta.scheme_name);
      }catch(e){ _NAVHIST.set(code, []); }''','''        if(!r.ok){ if(!_NAVHIST.has(code)) _NAVHIST.set(code, []); return; }
        const j = await r.json();
        if(j && j.data && j.data.length) _NAVHIST.set(code, j.data);
        else if(!_NAVHIST.has(code)) _NAVHIST.set(code, []);
        if(j && j.meta && j.meta.scheme_name) _NAVNAME.set(code, j.meta.scheme_name);
      }catch(e){ if(!_NAVHIST.has(code)) _NAVHIST.set(code, []); }'''),

('''  // Prime NAV history from mfapi.in for every scheme code we might read
  // (all master rows + EXTRA_FUNDS). One call per fund, throttled.
  showProgress("Fetching NAV history from mfapi.in…", 14);
  {
    const allCodes = [];
    for(let i=1;i<masterRows.length;i++){ const c = masterRows[i][masterIdx.code]; if(c) allCodes.push(c); }
    await primeNavHistory(allCodes, (done,total)=>{
      showProgress(`Fetching NAV history from mfapi.in… ${done}/${total} funds`, 14 + (done/total)*68);
    });
  }

  // Fetch year-end snapshot for each year
  const snaps = {};
  for(let i=0;i<YEARS.length;i++){
    const y = YEARS[i];
    showProgress(`Fetching ${y} year-end NAV snapshot (${i+1}/${YEARS.length})…`, 5 + (i/YEARS.length)*80);
    const s = await fetchYearEndSnapshot(y);
    if(s){ snaps[y] = { date: s.date, map: s.map }; }
    else snaps[y] = null;
  }
''','''  // Year-end NAVs for every scheme from ONE mirror file (was ~16k mfapi calls).
  // Falls back to per-fund mfapi only if the mirror file is unavailable.
  showProgress("Loading year-end NAV snapshot…", 14);
  {
    const allCodes = [];
    for(let i=1;i<masterRows.length;i++){ const c = masterRows[i][masterIdx.code]; if(c) allCodes.push(c); }
    let ok = false;
    try { ok = (await loadSnapshotBundle(allCodes)) > 0; } catch(e){ console.warn("Snapshot bundle failed, falling back to mfapi", e); }
    if(!ok){
      await primeNavHistory(allCodes, (done,total)=>{
        showProgress(`Fetching NAV history from mfapi.in… ${done}/${total} funds`, 14 + (done/total)*68);
      });
    }
  }

  // Year-end snapshot for each year (in-memory, from _NAVHIST)
  const snaps = {};
  async function buildSnaps(){
    for(let i=0;i<YEARS.length;i++){
      const y = YEARS[i];
      const s = await fetchYearEndSnapshot(y);
      snaps[y] = s ? { date: s.date, map: s.map } : null;
    }
  }
  showProgress("Building year-end snapshots…", 82);
  await buildSnaps();
'''),

('''  // Replace SECTORS at runtime for downstream computation by mutating a state-tracked list
  state.expandedSectors = expandedSectors;
''','''  // Replace SECTORS at runtime for downstream computation by mutating a state-tracked list
  state.expandedSectors = expandedSectors;

  // Upgrade ONLY the chosen sector funds to full daily history (mfapi, ~1 wave):
  // gives the Dec-2006 anchor for the 2007 column and exact month-end NAVs for momentum.
  showProgress("Refreshing daily NAVs for sector funds…", 92);
  try {
    const repCodes = [...new Set(Object.values(sectorFunds).filter(Boolean).map(f => f.code))];
    await Promise.race([
      primeNavHistory(repCodes, null, true),
      new Promise(res => setTimeout(res, 20000)),
    ]);
    await buildSnaps();
  } catch(e){ console.warn("Sector daily refresh failed", e); }
'''),

('''  async function fetchSnapOnce(targetDate, timeoutMs){
    const map = snapshotAsOf(new Date(targetDate));''','''  async function fetchSnapOnce(targetDate, timeoutMs){
    const t = new Date(targetDate).getTime(), maxGap = 20*24*3600*1000;
    const map = Object.create(null);
    for(const [code, data] of _NAVHIST){
      if(!data || !data.length) continue;
      for(let i=0;i<data.length;i++){
        const dt = _parseMfDate(data[i].date).getTime();
        if(dt <= t){ const v = parseFloat(data[i].nav); if(v>0 && t-dt <= maxGap) map[code] = { name: _NAVNAME.get(code)||"", nav: v }; break; }
      }
    }'''),

('''Data: AMFI end-of-year NAVs (2007 onwards) via <a href="https://github.com/mfapi.in" style="color:var(--accent)">mfapi.in</a>.''','''Data: AMFI end-of-year NAVs (2007 onwards) via the DR Brokers AMFI NAV mirror (sector funds' daily history via <a href="https://github.com/mfapi.in" style="color:var(--accent)">mfapi.in</a>).'''),

('const CACHE_KEY = "mf_sector_cycle_v72_mfapi";', 'const CACHE_KEY = "mf_sector_cycle_v73_snap";'),

# Heat map: show the ACTUAL calendar-year return first; the gap vs Nifty 50 goes
# underneath as a small "vs Nifty" line. Cell colour still follows the gap.
('''      html += `<td class='${cls}' title='${title}'>${rel==null?"":fmtPct(rel)}</td>`;''',
 '''      html += `<td class='${cls}' title='${title}'>${ret==null?"":fmtPct(ret)+`<div style="font-size:9px;font-weight:500;opacity:.75;margin-top:1px">${rel==null?"":"vs N "+fmtPct(rel)}</div>`}</td>`;'''),
]
REQUIRED = {1, 3}  # the page is only worth publishing if the loader + fetch block are patched


def run(root):
    req = urllib.request.Request(SRC_URL, headers={"User-Agent": "drbrokers-nav-mirror/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        s = r.read().decode("utf-8")
    applied = []
    for i, (old, new) in enumerate(PATCHES):
        if s.count(old) == 1:
            s = s.replace(old, new); applied.append(i)
    if not REQUIRED.issubset(applied):
        print(f"  sector-cycle: source changed, patches {sorted(set(range(len(PATCHES))) - set(applied))} missing — skipped")
        return False
    with open(os.path.join(root, "docs", "sector-cycle.html"), "w", encoding="utf-8") as f:
        f.write(s)
    print(f"  sector-cycle.html written ({len(applied)}/{len(PATCHES)} patches)")
    return True


if __name__ == "__main__":
    run(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
