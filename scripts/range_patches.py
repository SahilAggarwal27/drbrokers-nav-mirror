"""📅 Custom Range tab for the Sector Cycle page: pick any two dates, a month or a year and see
which sectors / size segments beat or lagged Nifty 50 (daily NSE TRI from docs/sector-daily.json,
built by scripts/build_sector_daily.py). Applied after PATCHES + WL_PATCHES in patch_sector_page."""

RANGE_PATCHES = [
# 1. Tab button, right after Performance Matrix
('''    <button class="view-tab on" data-view="heatmap">📊 Performance Matrix</button>
''', '''    <button class="view-tab on" data-view="heatmap">📊 Performance Matrix</button>
    <button class="view-tab" data-view="rangeview" style="border-color:var(--accent)">📅 Custom Range</button>
'''),

# 2. View container
('''  <div id="sigView" style="display:none">''', r'''  <div id="rangeView" style="display:none">
    <h2 style="font-size:14px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin:0 0 6px;font-weight:700">📅 Custom Range — which sectors did well, and which didn't</h2>
    <p style="color:var(--muted);font-size:12.5px;margin:0 0 12px;line-height:1.6">Pick any two dates, a month or a year. Returns are NSE index <b>Total Return</b> (dividends included, niftyindices.com) from the close on the last trading day <i>before</i> the start date to the close on/before the end date, ranked and compared with Nifty 50. Index returns, not a specific fund's.</p>
    <style>
      #rangeView .rg-in{background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:5px 8px;font-size:12.5px;color-scheme:dark}
      #rangeView .rg-chip{background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:99px;padding:4px 11px;font-size:12px;cursor:pointer}
      #rangeView .rg-chip.on{background:var(--accent);border-color:var(--accent);color:#fff}
      #rangeView .rg-lbl{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.5px}
      #rangeView .rg-sep{width:1px;height:22px;background:var(--border);margin:0 4px}
    </style>
    <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:10px">
      <span class="rg-lbl">Quick</span>
      <span id="rgChips" style="display:flex;gap:6px;flex-wrap:wrap">
        <button class="rg-chip" data-rg="1W" onclick="_rgPreset('1W')">1W</button>
        <button class="rg-chip" data-rg="1M" onclick="_rgPreset('1M')">1M</button>
        <button class="rg-chip" data-rg="3M" onclick="_rgPreset('3M')">3M</button>
        <button class="rg-chip" data-rg="6M" onclick="_rgPreset('6M')">6M</button>
        <button class="rg-chip" data-rg="YTD" onclick="_rgPreset('YTD')">YTD</button>
        <button class="rg-chip" data-rg="1Y" onclick="_rgPreset('1Y')">1Y</button>
        <button class="rg-chip" data-rg="3Y" onclick="_rgPreset('3Y')">3Y</button>
        <button class="rg-chip" data-rg="5Y" onclick="_rgPreset('5Y')">5Y</button>
      </span>
    </div>
    <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:14px">
      <span class="rg-lbl">From</span><input type="date" id="rgFrom" class="rg-in">
      <span class="rg-lbl">To</span><input type="date" id="rgTo" class="rg-in">
      <button class="rg-chip" onclick="_rgDates()">Show</button>
      <span class="rg-sep"></span>
      <span class="rg-lbl">Month</span><input type="month" id="rgMonth" class="rg-in" onchange="_rgMonth()">
      <span class="rg-sep"></span>
      <span class="rg-lbl">Year</span><select id="rgYear" class="rg-in" onchange="_rgYear()"></select>
      <span class="rg-sep"></span>
      <span class="rg-lbl">Show</span><select id="rgGroup" class="rg-in" onchange="_rgRender()">
        <option value="all">Sectors + size segments</option><option value="sector">Sectors only</option><option value="size">Size segments only</option></select>
    </div>
    <div id="rgBody" style="color:var(--muted)">Loading…</div>
  </div>
  <div id="sigView" style="display:none">'''),

# 3. switchView hook
('''  if(v === "comboview") setTimeout(renderComboView, 20);
''', '''  if(v === "comboview") setTimeout(renderComboView, 20);
  $("rangeView").style.display = v==="rangeview" ? "block" : "none";
  if(v === "rangeview") setTimeout(renderRangeView, 20);
'''),

# 4. Logic
('''// Tab click handler — wire all view-tab buttons to switchView''', r'''// ── 📅 Custom Range: daily NSE TRI (docs/sector-daily.json) → returns between any two dates ──
let _RG = null, _rgSel = null;
const _rgPad = n => String(n).padStart(2, "0");
const _rgIso = d => d.getFullYear() + "-" + _rgPad(d.getMonth()+1) + "-" + _rgPad(d.getDate());
const _rgD = s => { const [y,m,d] = s.split("-").map(Number); return new Date(y, m-1, d); };
const _rgFmt = s => _rgD(s).toLocaleDateString("en-IN", {day:"numeric", month:"short", year:"numeric"});
const _rgAddDays = (s, k) => { const d = _rgD(s); d.setDate(d.getDate()+k); return _rgIso(d); };
const _rgAddMonths = (s, k) => { const d = _rgD(s), day = d.getDate(); d.setDate(1); d.setMonth(d.getMonth()+k);
  const last = new Date(d.getFullYear(), d.getMonth()+1, 0).getDate(); d.setDate(Math.min(day, last)); return _rgIso(d); };
// last position i with dates[i] <= iso (dates sorted ascending), else -1
function _rgPos(dates, iso){ let lo=0, hi=dates.length-1, a=-1;
  while(lo<=hi){ const m=(lo+hi)>>1; if(dates[m]<=iso){ a=m; lo=m+1; } else hi=m-1; } return a; }
function _rgBack(v, i){ while(i>=0 && v[i]==null) i--; return i; }
// Pure: rows for every index between from..to (inclusive dates, ISO strings).
function _rgCompute(J, from, to){
  const D = J.dates, base = _rgAddDays(from, -1);
  const one = v => {
    const i0 = _rgBack(v, _rgPos(D, base)), i1 = _rgBack(v, _rgPos(D, to));
    if(i0 < 0 || i1 <= i0) return null;
    if((_rgD(base) - _rgD(D[i0])) / 864e5 > 10) return null;     // series stale/absent at start
    let peak = v[i0], dd = 0;
    for(let i=i0+1;i<=i1;i++){ const x=v[i]; if(x==null) continue; if(x>peak) peak=x; else dd=Math.min(dd, x/peak-1); }
    return { ret: (v[i1]/v[i0]-1)*100, dd: dd*100, d0: D[i0], d1: D[i1] };
  };
  const n = J.i.nifty50 ? one(J.i.nifty50.v) : null;
  const rows = [];
  for(const id in J.i){
    if(id === "nifty50") continue;
    const s = J.i[id], r = one(s.v);
    rows.push({ id, label: s.label, group: s.group, r, vs: (r && n) ? r.ret - n.ret : null });
  }
  rows.sort((a,b) => (b.r ? b.r.ret : -1e9) - (a.r ? a.r.ret : -1e9));
  return { nifty: n, rows };
}
async function _rgLoad(){
  if(_RG) return _RG;
  const r = await fetch(_MIR + "sector-daily.json", {cache:"no-cache"});
  if(!r.ok) throw new Error("sector-daily.json HTTP " + r.status);
  _RG = await r.json(); return _RG;
}
function _rgSet(from, to, chip){
  const J = _RG, first = J.dates[0], last = J.as_of;
  if(to > last) to = last;
  if(from < first) from = first;
  _rgSel = { from, to, chip: chip || null };
  $("rgFrom").value = from; $("rgTo").value = to;
  document.querySelectorAll("#rgChips .rg-chip").forEach(b => b.classList.toggle("on", b.dataset.rg === chip));
  _rgRender();
}
function _rgPreset(k){
  if(!_RG) return;
  const to = _RG.as_of; let from;
  if(k === "YTD") from = to.slice(0,4) + "-01-01";
  else if(k === "1W") from = _rgAddDays(to, -6);
  else { const m = {"1M":1,"3M":3,"6M":6,"1Y":12,"3Y":36,"5Y":60}[k]; from = _rgAddDays(_rgAddMonths(to, -m), 1); }
  _rgSet(from, to, k);
}
function _rgDates(){ const f = $("rgFrom").value, t = $("rgTo").value; if(f && t) _rgSet(f, t); }
function _rgMonth(){ const m = $("rgMonth").value; if(!m) return; const [y,mo] = m.split("-").map(Number);
  _rgSet(m + "-01", _rgIso(new Date(y, mo, 0))); }
function _rgYear(){ const y = $("rgYear").value; if(y) _rgSet(y + "-01-01", y + "-12-31"); }
function _rgRender(){
  const J = _RG, s = _rgSel; if(!J || !s) return;
  const body = $("rgBody");
  if(s.from > s.to){ body.innerHTML = '<span style="color:var(--bad)">Start date is after end date.</span>'; return; }
  const { nifty, rows } = _rgCompute(J, s.from, s.to);
  const grp = $("rgGroup").value;
  const list = rows.filter(x => grp === "all" || x.group === grp);
  if(!nifty){ body.textContent = "No Nifty 50 data for this period (daily data starts " + _rgFmt(J.dates[0]) + ")."; return; }
  const yrs = (_rgD(nifty.d1) - _rgD(nifty.d0)) / (365.25*864e5);
  const cagr = r => yrs >= 1 ? (Math.pow(1 + r/100, 1/yrs) - 1) * 100 : null;
  const pc = (v, b) => v==null ? "—" : `<span style="color:${v>=0?'var(--good)':'var(--bad)'};font-weight:${b?700:500}">${v>=0?"+":""}${v.toFixed(1)}%</span>`;
  const have = list.filter(x => x.r), beat = have.filter(x => x.vs > 0).length;
  const maxAbs = Math.max(1, ...have.map(x => Math.abs(x.r.ret)), Math.abs(nifty.ret));
  const bar = v => { const w = Math.round(Math.abs(v)/maxAbs*100);
    return `<div style="display:flex;height:8px;width:180px;background:rgba(255,255,255,.04);border-radius:4px;overflow:hidden">
      <div style="width:50%;display:flex;justify-content:flex-end">${v<0?`<div style="width:${w}%;background:var(--bad)"></div>`:""}</div>
      <div style="width:50%">${v>=0?`<div style="width:${w}%;height:100%;background:var(--good)"></div>`:""}</div></div>`; };
  const TH = 'style="padding:9px 10px;text-align:left;border-bottom:1px solid var(--border);color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.4px"';
  const TD = 'style="padding:8px 10px;border-bottom:1px solid var(--border);font-size:12.5px;vertical-align:middle"';
  let h = `<div style="display:flex;flex-wrap:wrap;gap:18px;align-items:baseline;margin-bottom:10px">
    <div style="font-size:13px;color:var(--text)"><b>${_rgFmt(s.from)} → ${_rgFmt(s.to)}</b>
      <span style="font-size:11.5px;color:var(--muted)">(closes ${_rgFmt(nifty.d0)} → ${_rgFmt(nifty.d1)}${yrs>=1?` · ${yrs.toFixed(1)} yrs`:""})</span></div>
    <div style="font-size:13px">Nifty 50: ${pc(nifty.ret, 1)}${yrs>=1?` <span style="font-size:11.5px">(${cagr(nifty.ret).toFixed(1)}% CAGR)</span>`:""}</div>
    <div style="font-size:13px"><b style="color:var(--good)">${beat}</b> of ${have.length} beat Nifty 50</div></div>`;
  h += `<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--border);border-radius:10px;overflow:hidden">
    <tr><th ${TH}>#</th><th ${TH}>Sector / Segment</th><th ${TH}>Return</th><th ${TH}></th><th ${TH}>vs Nifty 50</th>${yrs>=1?`<th ${TH}>CAGR</th>`:""}<th ${TH}>Worst fall in period</th><th ${TH}>Verdict</th></tr>`;
  let k = 0;
  for(const x of list){
    const r = x.r;
    const verdict = !r ? '<span style="color:var(--muted)">No index data</span>'
      : x.vs > 2 ? '<span style="display:inline-block;padding:3px 9px;border-radius:99px;font-size:11px;font-weight:800;background:rgba(16,185,129,.18);color:var(--good)">OUTPERFORMED</span>'
      : x.vs < -2 ? '<span style="display:inline-block;padding:3px 9px;border-radius:99px;font-size:11px;font-weight:800;background:rgba(239,68,68,.15);color:var(--bad)">UNDERPERFORMED</span>'
      : '<span style="display:inline-block;padding:3px 9px;border-radius:99px;font-size:11px;font-weight:800;background:rgba(148,163,184,.12);color:var(--muted)">IN LINE</span>';
    h += `<tr><td ${TD}>${r ? ++k : ""}</td><td ${TD}><b style="color:var(--text)">${x.label}</b><div style="font-size:10.5px;color:var(--muted)">${x.group==="size"?"Size segment":"Sector"}${r && r.d0 > nifty.d0 ? " · data from "+_rgFmt(r.d0) : ""}</div></td>
      <td ${TD}>${r ? pc(r.ret, 1) : "—"}</td><td ${TD}>${r ? bar(r.ret) : ""}</td><td ${TD}>${pc(x.vs)}</td>${yrs>=1?`<td ${TD}>${r ? pc(cagr(r.ret)) : "—"}</td>`:""}
      <td ${TD}>${r ? `<span style="color:${r.dd<-10?'var(--bad)':'var(--muted)'}">${r.dd.toFixed(1)}%</span>` : "—"}</td><td ${TD}>${verdict}</td></tr>`;
  }
  h += `</table></div><div style="font-size:11px;margin-top:10px;line-height:1.6">OUTPERFORMED / UNDERPERFORMED = more than 2% points ahead of / behind Nifty 50 over the period. Worst fall = deepest peak-to-trough drop inside the period. Daily data ${_rgFmt(J.dates[0])} → ${_rgFmt(J.as_of)}, refreshed ${new Date(J.generated_ist).toLocaleString("en-IN")}. Past performance is not indicative of future returns. Research output, not investment advice.</div>`;
  body.innerHTML = h;
}
async function renderRangeView(){
  if(_rgSel){ _rgRender(); return; }
  try { await _rgLoad(); }
  catch(e){ $("rgBody").textContent = "Could not load daily sector data (" + e.message + "). It is built by the nightly data job — try again after the next run."; return; }
  const J = _RG, y0 = +J.dates[0].slice(0,4), y1 = +J.as_of.slice(0,4);
  $("rgFrom").min = $("rgTo").min = J.dates[0]; $("rgFrom").max = $("rgTo").max = J.as_of;
  $("rgMonth").min = J.dates[0].slice(0,7); $("rgMonth").max = J.as_of.slice(0,7);
  let o = '<option value="">—</option>';
  for(let y=y1; y>=y0; y--) o += `<option value="${y}">${y}${y===y1?" (YTD)":""}</option>`;
  $("rgYear").innerHTML = o;
  _rgPreset("1Y");
}

// Tab click handler — wire all view-tab buttons to switchView'''),
]
