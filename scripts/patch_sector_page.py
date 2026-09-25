#!/usr/bin/env python3
"""Builds docs/sector-cycle.html (index-first since 25-Sep-2026): pulls the live Sector Cycle page from tools.drbrokers.in
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

('const CACHE_KEY = "mf_sector_cycle_v72_mfapi";', 'const CACHE_KEY = "mf_sector_cycle_v75_picks";'),

# Heat map: show the ACTUAL calendar-year return first; the gap vs Nifty 50 goes
# underneath as a small "vs Nifty" line. Cell colour still follows the gap.
('''      html += `<td class='${cls}' title='${title}'>${rel==null?"":fmtPct(rel)}</td>`;''',
 '''      const _px = (((d.indexUsed||{})[sec.id]||{}).proxyYears||[]).includes(y);
      html += `<td class='${cls}' title='${title}${_px?" · fund proxy (index not yet available)":""}'${_px?" style='outline:1px dashed rgba(255,255,255,.4);outline-offset:-4px'":""}>${ret==null?"":fmtPct(ret)+`<div style="font-size:9px;font-weight:500;opacity:.75;margin-top:1px">${rel==null?"":"vs N "+fmtPct(rel)}</div>`}</td>`;'''),

# INDEX-FIRST: every sector with an NSE index uses its TRI (niftyindices, back-calculated,
# rebuilt daily into index-tri.json). Fund returns stay only for years before the index
# existed (marked "fund proxy") and for sectors with no NSE index (intl, gold, quant...).
('''  const relByYear = {};
''', '''  // ── Index-first returns: NSE TRI overrides the fund wherever the index has data ──
  const INDEX_TRI_URL = "https://sahilaggarwal27.github.io/drbrokers-nav-mirror/index-tri.json";
  const SECTOR_INDEX = { benchmark:"nifty50", smallcap:"smallcap250", midcap:"midcap150", largecap:"nifty100",
    flexicap:"nifty500", pharma:"pharma", tech:"it", auto:"auto", banking:"finserv", fmcg:"fmcg",
    infra:"infra", energy:"energy", defense:"defence", mnc:"mnc" };
  const indexUsed = {};
  try {
    const ir = await fetch(INDEX_TRI_URL, {cache:"no-cache"});
    if(ir.ok){
      const ij = await ir.json();
      const curY = new Date().getFullYear();
      for(const sec of expandedSectors){
        const iid = SECTOR_INDEX[sec.id]; if(!iid) continue;
        const ix = ij.i && ij.i[iid]; if(!ix) continue;
        const lv = {};
        ij.years.forEach((y,k)=>{ if(ix.ye[k]) lv[y] = ix.ye[k]; });
        if(ix.latest && ix.latest_date && +String(ix.latest_date).slice(0,4) === curY) lv[curY] = ix.latest;
        let n = 0; const proxyYears = [];
        for(const y of YEARS){
          if(lv[y] && lv[y-1]){ returnsByYear[sec.id][y] = (lv[y]/lv[y-1] - 1)*100; n++; }
          else if(returnsByYear[sec.id][y] != null) proxyYears.push(y);
        }
        if(n) indexUsed[sec.id] = { id: iid, name: ix.name, proxyYears };
      }
    }
  } catch(e){ console.warn("Index TRI load failed — falling back to funds", e); }
  // Automated fund picks (Regular Growth, scored vs the sector's own index; built daily).
  try {
    const pr = await fetch("https://sahilaggarwal27.github.io/drbrokers-nav-mirror/fund-picks.json", {cache:"no-cache"});
    if(pr.ok){
      const pj = await pr.json();
      for(const sid in (pj.sectors||{})){
        const p = pj.sectors[sid];
        if(!indexUsed[sid]) continue;
        indexUsed[sid].picks = (p.picks||[]).map(f => ({ name: f.name, hit: f.roll3_hit, edge: f.roll3_edge }));
        indexUsed[sid].fallback = p.fallback_index_fund ? p.fallback_index_fund.name : null;
        indexUsed[sid].passing = p.passing; indexUsed[sid].universe = p.universe;
      }
    }
  } catch(e){ console.warn("Fund picks load failed", e); }

  const relByYear = {};
'''),

('''  const data = { sectorFunds, expandedSectors,''', '''  const data = { indexUsed, sectorFunds, expandedSectors,'''),

('''      rowHeading = `${sec.label}${indexBadge}<br><span style="font-size:9.5px;color:var(--muted);font-weight:400">${fundLabel}</span>`;''',
 '''      const _iu = (d.indexUsed||{})[sec.id];
      rowHeading = _iu
        ? `${sec.label} <span style="background:rgba(16,185,129,.18);color:var(--good);font-size:8px;font-weight:800;padding:1px 5px;border-radius:99px;letter-spacing:.4px">NSE TRI</span><br><span style="font-size:9.5px;color:var(--muted);font-weight:400">${_iu.name}${_iu.proxyYears.length?` · fund proxy ${String(_iu.proxyYears[0]).slice(2)}–${String(_iu.proxyYears[_iu.proxyYears.length-1]).slice(2)}`:""}</span>${(_iu.picks&&_iu.picks.length)||_iu.fallback?`<br><span style="font-size:9.5px;color:var(--good);font-weight:600" title="Auto-picked Regular Growth funds: beat ${_iu.name} TRI in ≥60% of rolling 3Y windows. ${_iu.passing||0} of ${_iu.universe||0} funds pass. Recent returns are not used.">★ ${(_iu.picks&&_iu.picks.length)?_iu.picks.map(p=>p.name.replace(/\s*(Regular Plan|Regular|Growth|Option|Fund|Plan|-)\\b/gi," ").replace(/\s+/g," ").trim().slice(0,26)+" ("+Math.round(p.hit*100)+"%)").join(" · "):"Index fund: "+_iu.fallback.replace(/\s*(Regular Plan|Growth|Option|Plan|-)\\b/gi," ").replace(/\s+/g," ").trim().slice(0,34)}</span>`:""}`
        : `${sec.label}${indexBadge}<br><span style="font-size:9.5px;color:var(--muted);font-weight:400">${fundLabel}</span>`;'''),

# ── Integrated tabs: Sector Signal + Fund Combo (no separate pages needed) ──
('''    <button class="view-tab on" data-view="heatmap">📊 Performance Matrix</button>''',
 '''    <button class="view-tab on" data-view="heatmap">📊 Performance Matrix</button>
    <button class="view-tab" data-view="sigview" style="border-color:var(--good)">🧭 Sector Signal</button>
    <button class="view-tab" data-view="comboview" style="border-color:var(--good)">🧺 Fund Combo</button>'''),

('''  <div id="autoPortfolioView" style="display:none">''',
 '''  <div id="sigView" style="display:none">
    <h2 style="font-size:14px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin:0 0 6px;font-weight:700">🧭 Sector &amp; Segment Signal — where new money goes</h2>
    <p style="color:var(--muted);font-size:12.5px;margin:0 0 14px;line-height:1.6"><b>Dry</b>: 24M return trails Nifty 50 by &gt;10%. <b>Cheap</b>: P/E &gt;0.5 SD below its 10-yr average. <b>Turning</b>: last 3M ahead of Nifty 50. <b>ENTER</b> = all three → SIP / staggered entry. <b>WAIT FOR TURN</b> = dry + cheap, still falling. <b>AVOID / TRIM</b> = 24M lead &gt;20% and P/E above average. Recent top performers are never a buy signal. NSE index TRI + P/E data; keep all sectoral funds within 10–15% of equity.</p>
    <div id="sigBody" style="color:var(--muted)">Loading…</div>
  </div>
  <div id="comboView" style="display:none">
    <h2 style="font-size:14px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin:0 0 6px;font-weight:700">🧺 Fund Combo — 2 Regular funds per category</h2>
    <p style="color:var(--muted);font-size:12.5px;margin:0 0 14px;line-height:1.6"><b>Aggressive</b> = best 1Y return among funds beating the category median ≥60% of the last 24 months with downside capture &lt;110% (leads in rising markets). <b>Defensive</b> = lowest downside capture among funds with ≥ category-median 3Y returns (leads in falls). Split 50:50, tilt 40:60 to defensive in a weak market. Funds ≥8% behind their category are in a <b>slump</b> — no new money, hold existing. Reviewed monthly; a pick changes only after failing 2 reviews in a row.</p>
    <div id="comboBody" style="color:var(--muted)">Loading…</div>
  </div>
  <div id="autoPortfolioView" style="display:none">'''),

('''  if(v === "autoportfolio") setTimeout(renderAutoPortfolio, 50);''',
 '''  if(v === "autoportfolio") setTimeout(renderAutoPortfolio, 50);
  $("sigView").style.display = v==="sigview" ? "block" : "none";
  if(v === "sigview") setTimeout(renderSigView, 20);
  $("comboView").style.display = v==="comboview" ? "block" : "none";
  if(v === "comboview") setTimeout(renderComboView, 20);'''),

('''// Tab click handler — wire all view-tab buttons to switchView''',
 '''// ── Sector Signal + Fund Combo tabs (data built daily by the NAV mirror) ──
const _MIR = "https://sahilaggarwal27.github.io/drbrokers-nav-mirror/";
const _pc = v => v==null ? "—" : `<span style="color:${v>=0?'var(--good)':'var(--bad)'}">${v>=0?"+":""}${v.toFixed(1)}%</span>`;
const _short = n => String(n||"").replace(/\\s*(Regular Plan|Regular|Growth|Option|Plan|-)\\b/gi," ").replace(/\\s+/g," ").trim();
const _pillC = c => c.startsWith("ENTER")?["rgba(16,185,129,.18)","var(--good)"]:c.startsWith("WAIT")?["rgba(56,189,248,.15)","#38bdf8"]:c.startsWith("WATCH")?["rgba(124,92,255,.18)","#c4b5fd"]:c.startsWith("AVOID")?["rgba(245,158,11,.15)","var(--warn)"]:c.startsWith("EXPENSIVE")?["rgba(239,68,68,.15)","var(--bad)"]:["rgba(148,163,184,.12)","var(--muted)"];
const _pill = c => { const [b,f]=_pillC(c); return `<span style="display:inline-block;padding:3px 9px;border-radius:99px;font-size:11px;font-weight:800;background:${b};color:${f};white-space:nowrap">${c}</span>`; };
const _tk = b => b==null?"":b?'<span style="color:var(--good);font-weight:700">✓</span>':'<span style="color:#475569">✗</span>';
const _TH = 'style="padding:9px 10px;text-align:left;border-bottom:1px solid var(--border);color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.4px"';
const _TD = 'style="padding:9px 10px;border-bottom:1px solid var(--border);font-size:12.5px;vertical-align:top"';
const _TBL = 'style="width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--border);border-radius:10px;overflow:hidden"';
const _SIG2PICK = {large:"largecap",mid:"midcap",small:"smallcap",it:"tech",pharma:"pharma",finserv:"banking",bank:"banking",fmcg:"fmcg",consumption:"fmcg",auto:"auto",infra:"infra",energy:"energy",defence:"defense",mnc:"mnc"};
let _sigDone=false, _comboDone=false;
async function renderSigView(){
  if(_sigDone) return;
  try{
    const [s,p] = await Promise.all([fetch(_MIR+"sector-signals.json",{cache:"no-cache"}).then(r=>r.json()),
                                     fetch(_MIR+"fund-picks.json",{cache:"no-cache"}).then(r=>r.ok?r.json():{sectors:{}}).catch(()=>({sectors:{}}))]);
    const fundFor = id => { const x=(p.sectors||{})[_SIG2PICK[id]]; if(!x) return "—";
      if(x.picks&&x.picks.length) return x.picks.map(f=>_short(f.name)).join("<br>");
      return x.fallback_index_fund ? "Index fund: "+_short(x.fallback_index_fund.name) : "—"; };
    let h = `<div style="font-size:12px;margin-bottom:8px">Data to <b style="color:var(--text)">${s.as_of}</b> · refreshed ${new Date(s.generated_ist).toLocaleString("en-IN")}</div>`;
    h += `<div style="overflow-x:auto"><table ${_TBL}><tr><th ${_TH}>Segment / Sector</th><th ${_TH}>Call</th><th ${_TH}>Dry</th><th ${_TH}>Cheap</th><th ${_TH}>Turning</th><th ${_TH}>P/E now · 10y median · z</th><th ${_TH}>3M / 6M / 24M vs Nifty</th><th ${_TH}>Fund to use (Regular)</th></tr>`;
    for(const i of s.items){
      h += `<tr><td ${_TD}><b style="color:var(--text)">${i.label}</b><div style="font-size:10.5px;color:var(--muted)">${i.group==="size"?"Size segment":"Sector"}</div></td><td ${_TD}>${_pill(i.call)}</td><td ${_TD}>${_tk(i.dry)}</td><td ${_TD}>${_tk(i.cheap)}</td><td ${_TD}>${_tk(i.turning)}</td>
        <td ${_TD}>${i.pe??"—"} · ${i.pe_median??"—"} · <b>${i.pe_z!=null?(i.pe_z>0?"+":"")+i.pe_z.toFixed(1):"—"}</b></td><td ${_TD}>${_pc(i.rel3)} / ${_pc(i.rel6)} / ${_pc(i.rel24)}</td>
        <td ${_TD} style="font-size:11.5px;color:var(--text)">${i.group==="size"?'<span style="color:var(--muted)">see 🧺 Fund Combo</span>':fundFor(i.id)}</td></tr>`;
    }
    h += `</table></div><h3 style="font-size:12.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.8px;margin:22px 0 8px">Does it work? — NSE index data, monthly signals since 2016, next 12 months vs Nifty 50 (recomputed daily)</h3>`;
    h += `<div style="overflow-x:auto"><table ${_TBL}><tr><th ${_TH}>Call</th><th ${_TH}>Cases</th><th ${_TH}>Avg vs Nifty</th><th ${_TH}>Median vs Nifty</th><th ${_TH}>Beat Nifty</th></tr>`;
    for(const k of ["ENTER","WAIT FOR TURN","WATCH (cheap)","NEUTRAL","ALL","AVOID / TRIM","EXPENSIVE — NO NEW MONEY"]){
      const e=(s.evidence||{})[k]; if(!e) continue;
      h += `<tr><td ${_TD}>${k==="ALL"?"<i>All (baseline)</i>":_pill(k)}</td><td ${_TD}>${e.n}</td><td ${_TD}>${_pc(e.avg)}</td><td ${_TD}>${_pc(e.median)}</td><td ${_TD}>${e.beat_pct}%</td></tr>`;
    }
    $("sigBody").innerHTML = h + `</table></div><div style="font-size:11px;margin-top:12px">Sector funds shown pass the sector-index test (beat their own NSE index in ≥60% of rolling 3Y windows); otherwise the sector index fund. Research output, not investment advice.</div>`;
    _sigDone = true;
  }catch(e){ $("sigBody").textContent = "Could not load sector signals: " + e.message; }
}
async function renderComboView(){
  if(_comboDone) return;
  try{
    const d = await fetch(_MIR+"fund-combo.json",{cache:"no-cache"}).then(r=>r.json());
    const slot = (t,col,r) => !r ? `<div style="border-left:3px solid ${col};padding:6px 10px;margin:8px 0">${t}<br><b>No fund passes this month</b></div>` :
      `<div style="border-left:3px solid ${col};padding:6px 10px;margin:8px 0;background:rgba(255,255,255,.02);border-radius:6px"><div style="font-size:10px;font-weight:800;letter-spacing:.5px;color:${col}">${t}</div>
       <div style="font-weight:600;color:var(--text);margin:2px 0 4px">${_short(r.name)}</div>
       <div style="font-size:11.5px">1Y ${_pc(r.ret1y)} · 3Y CAGR ${_pc(r.cagr3y)} · Downside capture <b style="color:var(--text)">${r.downside_capture.toFixed(0)}%</b> · Consistency <b style="color:var(--text)">${r.consistency.toFixed(0)}%</b> · Sortino <b style="color:var(--text)">${r.sortino.toFixed(2)}</b> · ${r.history_yrs}y${r.history_yrs<5?' <span style="color:var(--warn)">(young)</span>':''}</div></div>`;
    let h = `<div style="font-size:12px;margin-bottom:10px">Month-end <b style="color:var(--text)">${d.as_of}</b> · ${d.plan} · refreshed ${new Date(d.generated_ist).toLocaleString("en-IN")}</div><div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:12px">`;
    for(const c of Object.values(d.categories)){
      h += `<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:12px 14px"><div style="display:flex;justify-content:space-between;align-items:baseline"><b style="color:var(--text)">${c.label}</b><span style="font-size:11px">${c.funds_scored} funds · 3Y median ${_pc(c.median_cagr3y)}</span></div>
        ${slot("AGGRESSIVE — leads in rising markets","var(--accent)",c.aggressive)}${slot("DEFENSIVE — holds up in falls","var(--good)",c.defensive)}
        ${c.slumping&&c.slumping.length?`<div style="color:var(--warn);font-size:11.5px;margin-top:6px">⚠ Slump — no new money: ${c.slumping.map(s=>_short(s.name)+" ("+s.slump.toFixed(0)+"% behind)").join(", ")}</div>`:""}
        <div style="font-size:11px;margin-top:6px">Runners-up: ${[...(c.runners_up.aggressive||[]),...(c.runners_up.defensive||[])].map(s=>_short(s.name)).join(" · ")||"—"}</div></div>`;
    }
    $("comboBody").innerHTML = h + `</div><div style="font-size:11px;margin-top:12px">Backtest (2014–26, 188 funds): recent winners lead in rising years, low-downside funds lead in falling years — so hold one of each. Check AUM, TER and manager tenure on the factsheet before recommending. Research output, not investment advice.</div>`;
    _comboDone = true;
  }catch(e){ $("comboBody").textContent = "Could not load fund combo: " + e.message; }
}

// Tab click handler — wire all view-tab buttons to switchView'''),
]
REQUIRED = {1, 3}  # the page is only worth publishing if the loader + fetch block are patched


def run(root):
    # Refresh NSE sector TRI data first (index-first heat map). Isolated: a failure here
    # only means the page falls back to fund returns.
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import build_index_tri
        build_index_tri.run(root)
    except Exception as e:
        print(f"  build_index_tri skipped: {e}")
    try:
        import build_fund_picks
        build_fund_picks.run(root)
    except Exception as e:
        print(f"  build_fund_picks skipped: {e}")
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
