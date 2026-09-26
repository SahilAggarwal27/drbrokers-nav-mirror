# ── Sector Track Record: click a sector row to expand every dry period (year-by-year) ──
# Applied by patch_sector_page.py (PATCHES += WL_PATCHES). Anchors are in renderBacktest().
WL_PATCHES = [
(r'''Tells you which sectors deserve contra bets and which ones are <em>traps</em>.</p>''',
 r'''Tells you which sectors deserve contra bets and which ones are <em>traps</em>. <b style="color:var(--text)">Click any sector to see its dry periods.</b></p>'''),

(r'''    const sectorWL = allSectorWinLoss(d);''',
 r'''    const sectorWL = allSectorWinLoss(d);
    const _wlCY = new Date().getFullYear();
    const _wlF = v => v==null ? "<span style='color:var(--muted)'>—</span>" : "<span style='color:"+(v>=0?"var(--good)":"var(--bad)")+";font-weight:700'>"+(v>=0?"+":"")+v.toFixed(1)+"%</span>";
    const _wlTH = (h,al) => "<th style='padding:7px 9px;text-align:"+(al||"left")+";font-size:10px;background:rgba(255,255,255,.04)'>"+h+"</th>";
    const _wlTD = (x,al) => "<td style='padding:7px 9px;font-size:12px;text-align:"+(al||"left")+";border-bottom:1px solid var(--border)'>"+x+"</td>";
    window.wlToggle = function(tr){
      const nx = tr.nextElementSibling; if(!nx || !nx.classList.contains("wl-detail")) return;
      const open = nx.style.display === "none";
      nx.style.display = open ? "table-row" : "none";
      const c = tr.querySelector(".wl-caret"); if(c) c.style.transform = open ? "rotate(90deg)" : "";
    };
    window.wlToggleAll = function(open){
      document.querySelectorAll("#sectorWLTable tr.wl-row").forEach(function(tr){
        const nx = tr.nextElementSibling; if(!nx || !nx.classList.contains("wl-detail")) return;
        nx.style.display = open ? "table-row" : "none";
        const c = tr.querySelector(".wl-caret"); if(c) c.style.transform = open ? "rotate(90deg)" : "";
      });
    };
    function wlDetailRow(secId){
      const dps = ((d.cycles||{})[secId]||[]).slice().sort(function(a,b){ return b.end - a.end; });
      if(!dps.length) return "";
      const rel = (d.relByYear||{})[secId] || {};
      let t = "<table style='width:100%;border-collapse:collapse;margin:0;background:transparent;border:none'><thead><tr>"
        + _wlTH("Dry period") + _wlTH("Yrs","right") + _wlTH("Lag vs Nifty each year") + _wlTH("Cum lag","right")
        + _wlTH("Next 1Y","right") + _wlTH("Nifty 1Y","right") + _wlTH("Alpha 1Y","right") + _wlTH("Alpha 2Y","right") + _wlTH("Alpha 3Y","right") + _wlTH("Result")
        + "</tr></thead><tbody>";
      for(const dp of dps){
        let cum = 0; const yrs = [];
        for(let y=dp.start; y<=dp.end; y++){ const v = rel[y]; if(v != null){ cum += v; yrs.push("<span style='white-space:nowrap'>"+y+" "+_wlF(v)+"</span>"); } }
        const s1 = fwdCAGR(secId, dp.end, 1), b1 = fwdCAGRBench(dp.end, 1);
        const s2 = fwdCAGR(secId, dp.end, 2), b2 = fwdCAGRBench(dp.end, 2);
        const s3 = fwdCAGR(secId, dp.end, 3), b3 = fwdCAGRBench(dp.end, 3);
        const a1 = (s1!=null && b1!=null) ? s1-b1 : null;
        const a2 = (s2!=null && b2!=null) ? s2-b2 : null;
        const a3 = (s3!=null && b3!=null) ? s3-b3 : null;
        const ytd = dp.end + 1 >= _wlCY;
        let eh = 0, en = 0;
        for(let y=dp.start; y<=dp.end; y++){ const fs = fwdCAGR(secId, y, 1), fb = fwdCAGRBench(y, 1); if(fs!=null && fb!=null){ en++; if(fs-fb > 2) eh++; } }
        let res;
        if(a1 == null) res = "<span style='color:#60a5fa;font-weight:800'>● Ongoing</span>";
        else res = (a1 > 2 ? "<span style='color:var(--good);font-weight:800'>✓ Bounced</span>" : "<span style='color:var(--bad);font-weight:800'>✗ Trap</span>")
                 + (ytd ? " <span style='font-size:10px;color:#60a5fa'>("+_wlCY+" YTD)</span>" : "");
        t += "<tr>" + _wlTD("<b style='color:var(--text)'>"+dp.start+(dp.start===dp.end?"":"–"+dp.end)+"</b>")
          + _wlTD(dp.len != null ? dp.len : (dp.end-dp.start+1), "right")
          + _wlTD(yrs.join(" · ") || "—")
          + _wlTD(_wlF(cum), "right")
          + _wlTD(_wlF(s1)+(ytd&&s1!=null?"<sup style='color:#60a5fa'>ytd</sup>":""), "right") + _wlTD(_wlF(b1), "right")
          + _wlTD(_wlF(a1), "right") + _wlTD(_wlF(a2), "right") + _wlTD(_wlF(a3), "right")
          + _wlTD(res + (en ? "<div style='font-size:10.5px;color:var(--muted);margin-top:2px'>Bought in any dry year: <b style='color:"+(eh/en>=0.6?"var(--good)":eh/en>=0.4?"var(--warn)":"var(--bad)")+"'>"+eh+"/"+en+" won</b></div>" : "")) + "</tr>";
      }
      t += "</tbody></table><div style='font-size:10.5px;color:var(--muted);margin-top:6px'>Dry = lagged Nifty 50 by &gt;2% for consecutive years. Bounced/Trap = what happened after the streak ended (hindsight — you only know the end afterwards). <b>Bought in any dry year</b> = the honest test: buy at each dry year-end, win if the next year beat Nifty by &gt;2%. Hit rates above use this honest test.</div>";
      return "<tr class='wl-detail' style='display:none'><td colspan='8' style='padding:10px 16px 14px 34px;background:rgba(124,92,255,.04)'>" + t + "</td></tr>";
    }'''),

(r'''return "<tr><td><strong>" + r.sectorLabel + "</strong></td><td class='num'>" + r.total''',
 r'''return "<tr class='wl-row' onclick='wlToggle(this)' style='cursor:pointer' title='Click to see dry periods'><td><span class='wl-caret' style='display:inline-block;width:14px;color:var(--muted);transition:transform .15s'>▸</span><strong>" + r.sectorLabel + "</strong></td><td class='num'>" + r.total'''),

(r'''+ verdict + "</td></tr>";''',
 r'''+ verdict + "</td></tr>" + wlDetailRow(r.sectorId);'''),

(r'''wlBox.innerHTML = wlHead + "<tbody>" + wlBody + "</tbody>";''',
 r'''wlBox.innerHTML = "<caption style='caption-side:top;text-align:right;padding:0 0 6px;font-size:11px'><a href='javascript:void(0)' onclick='wlToggleAll(true)' style='color:var(--accent)'>Expand all</a> · <a href='javascript:void(0)' onclick='wlToggleAll(false)' style='color:var(--accent)'>Collapse all</a></caption>" + wlHead + "<tbody>" + wlBody + "</tbody>";'''),
]

# ── Tab cleanup (25-Sep-2026): drop Contra Funds, Valuation (covered by Sector Signal),
# Client Advisor, SIP Plan, Track Record, Research Archive; merge Broadcast + Newsletter.
# Views stay in the DOM (hidden) so any internal code that references them keeps working.
TAB_PATCHES = [
(r'''    <button class="view-tab" data-view="contrafunds">💎 Contra Funds</button>
''', ''),
(r'''    <button class="view-tab" data-view="valuation">💰 Valuation</button>
    <button class="view-tab" data-view="advisor">👥 Client Advisor</button>
    <button class="view-tab" data-view="broadcast">📣 Broadcast</button>
    <button class="view-tab" data-view="newsletter">📰 Newsletter</button>
''', r'''    <button class="view-tab" data-view="broadcast">📣 Broadcast &amp; Newsletter</button>
'''),
(r'''    <button class="view-tab" data-view="sipplan">⏱ SIP Plan</button>
    <button class="view-tab" data-view="track">📋 Track Record</button>
    <button class="view-tab" data-view="archive">📸 Research Archive</button>
''', ''),
(r'''  $("newsletterView").style.display = v==="newsletter" ? "block" : "none";
  if(v === "newsletter") setTimeout(restoreNewsletter, 50);''',
 r'''  $("newsletterView").style.display = (v==="newsletter"||v==="broadcast") ? "block" : "none";
  if(v === "newsletter" || v === "broadcast") setTimeout(restoreNewsletter, 50);'''),
]
WL_PATCHES += TAB_PATCHES

# ── Tab order (25-Sep-2026): Performance Matrix → Cycle Summary → Sector Signal → Fund Combo ──
WL_PATCHES += [
(r'''    <button class="view-tab" data-view="cycle">📋 Cycle Summary</button>
''', ''),
(r'''    <button class="view-tab on" data-view="heatmap">📊 Performance Matrix</button>
''', r'''    <button class="view-tab on" data-view="heatmap">📊 Performance Matrix</button>
    <button class="view-tab" data-view="cycle">📋 Cycle Summary</button>
'''),
]

# ── Honest backtest + one source of truth (25-Sep-2026) ──
# 1) Old test was circular: a dry streak "ends" the year before the sector stops lagging, so
#    "next year beat Nifty" was ~guaranteed (every sector showed 100%). Now EVERY dry year is an
#    entry point (you can't know the streak is ending) and we test the following year.
#    All hit rates, analogs, playbook buckets and verdicts use these entry points.
# 2) Sector Contra / Exit Watch / Broadcast actions follow the Sector Signal call
#    (NSE index TRI + P/E + turning, monthly since 2016). Sectors with no NSE index are capped at WATCH.
HONEST_PATCHES = [
(r'''    cycles[sec.id] = analyzeCycles(relByYear[sec.id] || {});
  }
''', r'''    cycles[sec.id] = analyzeCycles(relByYear[sec.id] || {});
  }
  // Point-in-time entry points: every year a sector was dry = a moment you could have bought.
  const entries = {};
  for(const id in cycles){
    entries[id] = [];
    for(const c of cycles[id]) for(let y=c.start; y<=c.end; y++) entries[id].push({ start:c.start, end:y, len:y-c.start+1, streakEnd:c.end });
  }
'''),
(r'''    for(const d of cycles[sec.id]){''', r'''    for(const d of entries[sec.id]){'''),
(r'''    for(const dp of (cycles[sec.id] || [])){''', r'''    for(const dp of (entries[sec.id] || [])){'''),
(r'''  const data = { indexUsed, sectorFunds, expandedSectors,''', r'''  const data = { entries, indexUsed, sectorFunds, expandedSectors,'''),
(r'''const dryArr = (d.cycles && d.cycles[secId]) || [];''', r'''const dryArr = ((d.entries || d.cycles || {})[secId]) || [];'''),
(r'''function findAnalogs(currStreakLen, currDD, data){
  const cycles = data.cycles || {};''', r'''function findAnalogs(currStreakLen, currDD, data){
  const cycles = data.entries || data.cycles || {};'''),
(r'''function computePlaybook(data){
  const cycles = data.cycles || {};''', r'''function computePlaybook(data){
  const cycles = data.entries || data.cycles || {};'''),
(r'''    const dryArr = (d.cycles[sec.id] || []);''', r'''    const dryArr = ((d.entries || d.cycles)[sec.id] || []);'''),
(r'''card("Total dry streaks tested", rows.length, "across "+sectors.length+" sectors"),''',
 r'''card("Entry points tested", rows.length, "every dry year, "+sectors.length+" sectors — no hindsight"),
    (function(){ let h=0,n=0; for(const s of sectors){ const r=(d.returnsByYear||{})[s.id]||{}; for(const y in r){ const b=benchRet[y]; if(r[y]!=null&&b!=null){ n++; if(r[y]-b>2) h++; } } }
      return card("Baseline — any year", n?(h/n*100).toFixed(0)+"%":"—", "sector beat Nifty by >2%, no signal. Edge = hit rate minus this"); })(),'''),
('const CACHE_KEY = "mf_sector_cycle_v75_picks";', 'const CACHE_KEY = "mf_sector_cycle_v76_honest";'),
(r'''function actionSignal(secId, data){''', r'''// ── One source of truth: actions follow the Sector Signal (sector-signals.json) ──
const _SIGMAP = { smallcap:"small", midcap:"mid", largecap:"large", pharma:"pharma", tech:"it", auto:"auto",
  banking:"finserv", fmcg:"fmcg", infra:"infra", energy:"energy", defense:"defence", mnc:"mnc" };
let _SIGCALLS = null, _SIGEV = {};
fetch("https://sahilaggarwal27.github.io/drbrokers-nav-mirror/sector-signals.json", {cache:"no-cache"})
  .then(r => r.json()).then(j => { _SIGCALLS = {}; (j.items||[]).forEach(i => { _SIGCALLS[i.id] = i; }); _SIGEV = j.evidence || {};
    try { if(state && state.data) renderAll(); } catch(e){} }).catch(() => {});
function _evTxt(k){ const e = _SIGEV[k], b = _SIGEV.ALL; return e ? ` Backtest: beat Nifty ${e.beat_pct}% of ${e.n} cases (baseline ${b?b.beat_pct:"—"}%), avg ${e.avg>=0?"+":""}${e.avg}%.` : ""; }
function _pct(v){ return v==null ? "—" : (v>=0?"+":"") + Number(v).toFixed(1) + "%"; }
function actionSignal(secId, data){
  const raw = _actionSignalRaw(secId, data);
  const sid = _SIGMAP[secId];
  const s = sid && _SIGCALLS ? _SIGCALLS[sid] : null;
  if(!_SIGCALLS) return raw;                       // signal file not loaded yet — first paint only
  if(!s){
    if(raw.tag === "strong") return { tag:"watch", label:"🟡 WATCH", color:"var(--warn)",
      reason:"No NSE index to validate (fund proxy only) — capped at WATCH. Old model: " + raw.reason };
    return raw;
  }
  const facts = `P/E z ${s.pe_z!=null?(s.pe_z>0?"+":"")+s.pe_z.toFixed(1):"—"} · 3M ${_pct(s.rel3)} / 6M ${_pct(s.rel6)} / 24M ${_pct(s.rel24)} vs Nifty.`;
  const c = s.call || "";
  if(c.startsWith("ENTER")) return { tag:"strong", label:"🟢 ENTER", color:"var(--good)", reason:"Dry + cheap + turning. " + facts + _evTxt("ENTER") };
  if(c.startsWith("WAIT")) return { tag:"watch", label:"🟡 WAIT FOR TURN", color:"var(--warn)", reason:"Dry + cheap but still falling — hold, SIP only, no lumpsum. " + facts + _evTxt("WAIT FOR TURN") };
  if(c.startsWith("WATCH")) return { tag:"watch", label:"🟡 WATCH (cheap)", color:"var(--warn)", reason:"Cheap, not yet dry/turning. " + facts + _evTxt("WATCH (cheap)") };
  if(c.startsWith("AVOID")) return { tag:"exit", label:"🔴 AVOID / TRIM", color:"var(--bad)", reason:"Big 24M lead + P/E above average — trim, no fresh money. " + facts + _evTxt("AVOID / TRIM") };
  if(c.startsWith("EXPENSIVE")) return { tag:"avoid", label:"⚫ EXPENSIVE", color:"var(--muted)", reason:"No new money. " + facts + _evTxt("EXPENSIVE — NO NEW MONEY") };
  if(raw.tag === "exit" || raw.tag === "avoid" || raw.tag === "hold") return raw;
  return { tag:"hold", label:"🟠 NEUTRAL", color:"#60a5fa", reason:"No edge now — hold existing, no fresh contra money. " + facts };
}
function _actionSignalRaw(secId, data){'''),
]
WL_PATCHES += HONEST_PATCHES
WL_PATCHES += [
(r"""<th class='num'>Dry Streaks</th><th class='num'>Hits</th>""", r"""<th class='num'>Dry Years<br><span style='font-size:9px;font-weight:400'>entry points</span></th><th class='num'>Hits</th>"""),
(r"""Which sectors reliably bounce back after dry streaks vs which just stay weak.""", r"""If you bought this sector at the end of any year it was lagging Nifty, how often did the next year beat Nifty by &gt;2%? (No hindsight — compare with the baseline card above.)"""),
]

# ── Sort by action (25-Sep-2026): ENTER → WAIT FOR TURN (dry + at historical-low P/E) → WATCH → NEUTRAL → HOLD → AVOID ──
# Ties: cheaper P/E (lower z) first, then the old dry-streak order.
WL_PATCHES += [
(r'''function _actionSignalRaw(secId, data){''', r'''function _actRank(secId, data){
  let a; try { a = actionSignal(secId, data); } catch(e){ return 99; }
  const L = (a && a.label) || "";
  const base = /ENTER/.test(L) ? 0 : /WAIT FOR TURN/.test(L) ? 1 : /WATCH \(cheap\)/.test(L) ? 2 : /WATCH/.test(L) ? 3
    : /STRONG/.test(L) ? 0 : /NEUTRAL/.test(L) ? 4 : /HOLD/.test(L) ? 5 : /EXPENSIVE/.test(L) ? 6 : /AVOID|EXIT|TRIM/.test(L) ? 7 : 8;
  const s = _SIGCALLS && _SIGMAP[secId] ? _SIGCALLS[_SIGMAP[secId]] : null;
  const z = s && s.pe_z != null ? s.pe_z : 0;
  return base + Math.max(-0.49, Math.min(0.49, z / 10));
}
function _actionSignalRaw(secId, data){'''),
(r'''  rows.sort((a,b) => (order[a.verdict.tag]??9) - (order[b.verdict.tag]??9) || b.streak - a.streak);''',
 r'''  rows.sort((a,b) => (_actRank(a.sec.id, d) - _actRank(b.sec.id, d)) || (order[a.verdict.tag]??9) - (order[b.verdict.tag]??9) || b.streak - a.streak);'''),
(r'''  ranked.sort((a,b) => b.score - a.score);
  // Show all with score > 25, capped at 10''',
 r'''  ranked.sort((a,b) => (_actRank(a.sec.id, d) - _actRank(b.sec.id, d)) || b.score - a.score);
  // Show all with score > 25, capped at 10'''),
]

# ── SIP / Lumpsum split (25-Sep-2026) ──
# Action column → two columns. Lumpsum keeps the strict backtested signal + conviction.
# SIP gets its own 0–100 score from cheapness (P/E z) + drawdown + dry years, so cheap /
# falling sectors read "Start SIP" instead of "Watch". Accumulate rule: P/E z ≤ -1 and
# (5Y DD ≤ -7% or dry ≥ 1y). Late Bull / expensive / avoid never get a fresh-SIP call.
SIP_PATCHES = [
(r'''function _actionSignalRaw(secId, data){''', r'''function _sipLump(secId, d, sig, streak){
  const L = (sig && sig.label) || "";
  const s = _SIGCALLS && _SIGMAP[secId] ? _SIGCALLS[_SIGMAP[secId]] : null;
  const z = s && s.pe_z != null ? s.pe_z : null;
  const dd = ((d.drawdowns || {})[secId] || {}).dd5y;
  streak = streak || 0;
  let sc = 15;
  if(z != null) sc += z < 0 ? Math.min(-z * 25, 50) : -Math.min(z * 15, 40);
  if(dd != null && dd < 0) sc += Math.min(-dd * 1.5, 30);
  sc += Math.min(streak * 5, 15);
  if(s && s.rel3 != null && s.rel3 > 0) sc += 5;
  sc = Math.max(0, Math.min(100, Math.round(sc)));
  const acc = z != null && z <= -1 && ((dd != null && dd <= -7) || streak >= 1);
  let late = false; try { late = /Late Bull/i.test((sectorPhase(secId, d) || {}).label || ""); } catch(e){}
  const G = "var(--good)", W = "var(--warn)", B = "var(--bad)", M = "var(--muted)", N = "#60a5fa";
  let sip, lump;
  if(/ENTER|STRONG/.test(L)){ sip = ["✅ START / STEP-UP", G]; lump = ["✅ DEPLOY (or STP 3M)", G]; }
  else if(/WAIT FOR TURN/.test(L)){ sip = ["✅ START SIP", G]; lump = ["⏳ WAIT FOR TURN", W]; }
  else if(/WATCH \(cheap\)/.test(L)){ sip = acc && !late ? ["✅ START SIP · accumulate", G] : late ? ["▶ CONTINUE, no new", N] : ["▶ CONTINUE", N]; lump = ["❌ NO — wait", M]; }
  else if(/AVOID|TRIM|EXIT/.test(L)){ sip = ["⏸ NO NEW SIP", B]; lump = ["🔴 TRIM / EXIT", B]; }
  else if(/EXPENSIVE/.test(L)){ sip = ["⏸ CONTINUE, no new", W]; lump = ["❌ NO", M]; }
  else if(/WATCH/.test(L)){ sip = ["▶ CONTINUE", N]; lump = ["❌ NO — unvalidated", M]; }
  else { sip = [late ? "▶ CONTINUE, no new" : "▶ CONTINUE", N]; lump = ["❌ NO", M]; }
  return { sip, lump, sipScore: sc, acc };
}
function _actionSignalRaw(secId, data){'''),

(r'''    <th>Action</th>
    <th class='r'>Conviction<br><span style='font-size:9px;font-weight:400'>0–100 · entry signal</span></th>''',
 r'''    <th>SIP<br><span style='font-size:9px;font-weight:400'>action · score 0–100</span></th>
    <th>Lumpsum<br><span style='font-size:9px;font-weight:400'>action · signal basis</span></th>
    <th class='r'>Lumpsum Conviction<br><span style='font-size:9px;font-weight:400'>0–100 · entry signal</span></th>'''),

(r'''      <td><span style='font-size:11px;font-weight:800;color:${sig2.color};white-space:nowrap'>${sig2.label}</span><br><span style='font-size:9.5px;color:var(--muted);line-height:1.3'>${sig2.reason}</span></td>''',
 r'''      ${(function(){
        const x = _sipLump(r.sec.id, d, sig2, r.streak);
        const scCol = x.sipScore >= 60 ? "var(--good)" : x.sipScore >= 40 ? "var(--warn)" : "var(--muted)";
        return `<td title="SIP score = cheapness (P/E z) + 5Y drawdown + dry years. Accumulate rule: P/E z ≤ -1 and (DD ≤ -7% or dry ≥ 1y). Averaging aid, not a timing signal."><span style='font-size:11px;font-weight:800;color:${x.sip[1]};white-space:nowrap'>${x.sip[0]}</span><br><span style='font-size:18px;font-weight:800;color:${scCol}'>${x.sipScore}</span><span style='font-size:9.5px;color:var(--muted)'> / 100</span></td>`
             + `<td><span style='font-size:11px;font-weight:800;color:${x.lump[1]};white-space:nowrap'>${x.lump[0]}</span><br><span style='font-size:9px;color:var(--muted);font-weight:700'>${sig2.label}</span><br><span style='font-size:9.5px;color:var(--muted);line-height:1.3'>${sig2.reason}</span></td>`;
      })()}'''),

# Drawdown: ignore NAV history before a unit split / face-value change (year-end jump <0.25x or >4x),
# e.g. ETF unit splits that showed Banking 10Y DD as -79%.
(r'''    let peak5 = null, peak10 = null;
    for(let y=latestY-5; y<=latestY; y++){ if(s[y] != null && (peak5==null || s[y]>peak5)) peak5 = s[y]; }
    for(let y=latestY-10; y<=latestY; y++){ if(s[y] != null && (peak10==null || s[y]>peak10)) peak10 = s[y]; }''',
 r'''    let _sY = YEARS[0];
    for(let y=YEARS[0]+1; y<=latestY; y++){ if(s[y] != null && s[y-1] != null){ const q = s[y]/s[y-1]; if(q < 0.25 || q > 4) _sY = y; } }
    let peak5 = null, peak10 = null;
    for(let y=Math.max(latestY-5,_sY); y<=latestY; y++){ if(s[y] != null && (peak5==null || s[y]>peak5)) peak5 = s[y]; }
    for(let y=Math.max(latestY-10,_sY); y<=latestY; y++){ if(s[y] != null && (peak10==null || s[y]>peak10)) peak10 = s[y]; }'''),

# "~At historical low" only when the drawdown is actually deep; shallow DDs just say mild.
(r'''    else if(exDrop.atHistoricalDeepest){ exDropCell = `''',
 r'''    else if(exDrop.atHistoricalDeepest && exDrop.currentDD > -15){ exDropCell = `<span style='color:var(--muted);font-weight:700'>Mild DD</span><br><span style='font-size:9px;color:var(--muted)'>cur ${exDrop.currentDD.toFixed(0)}% · no year-end precedent</span>`; }
    else if(exDrop.atHistoricalDeepest){ exDropCell = `'''),

('const CACHE_KEY = "mf_sector_cycle_v76_honest";', 'const CACHE_KEY = "mf_sector_cycle_v77_sip";'),
]
WL_PATCHES += SIP_PATCHES

# ── Cycle Summary: frozen header + frozen Sector column while scrolling (26-Sep-2026) ──
# table.cycle has overflow:hidden (breaks sticky), so wrap it in its own scroll box.
WL_PATCHES += [
(r'''    <table class="cycle" id="cycleTable"></table>''',
 r'''    <style>
      .cycle-scroll{max-height:calc(100vh - 120px);overflow:auto;border:1px solid var(--border);border-radius:12px;background:var(--panel)}
      .cycle-scroll table.cycle{border:0;border-radius:0;overflow:visible}
      .cycle-scroll table.cycle thead th{position:sticky;top:0;z-index:3;background:var(--panel2);box-shadow:inset 0 -1px 0 var(--border)}
      .cycle-scroll table.cycle thead th:first-child{left:0;z-index:4}
      .cycle-scroll table.cycle tbody td:first-child{position:sticky;left:0;z-index:2;background:var(--panel);box-shadow:inset -1px 0 0 var(--border)}
    </style>
    <div class="cycle-scroll"><table class="cycle" id="cycleTable"></table></div>'''),
]

# ── Performance Matrix: Nifty 50 + Sensex calendar-year rows — builder + patches in build_market_idx.py ──
try:
    import os as _os, build_market_idx as _bm
    try:
        _bm.run(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    except Exception as _e:
        print(f"  build_market_idx skipped: {_e}")
    WL_PATCHES += _bm.MKT_PATCHES
except Exception as _e:
    print(f"  market-idx patches skipped: {_e}")
