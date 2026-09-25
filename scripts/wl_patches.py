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
          + _wlTD(res) + "</tr>";
      }
      t += "</tbody></table><div style='font-size:10.5px;color:var(--muted);margin-top:6px'>Dry = lagged Nifty 50 by &gt;2% for consecutive years. Bounced = next calendar year beat Nifty by &gt;2%. 2Y/3Y = forward CAGR minus Nifty CAGR.</div>";
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
