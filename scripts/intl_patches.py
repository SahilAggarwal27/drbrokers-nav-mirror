"""🌍 International tab on the Sector Cycle page: embeds intl-tracker.html (built daily by
build_intl_signals.py) in an auto-height iframe. Applied last, after all other patches."""
_SRC = "https://sahilaggarwal27.github.io/drbrokers-nav-mirror/intl-tracker.html?embed=1"

INTL_PATCHES = [
('''<button class="view-tab" data-view="sigview" style="border-color:var(--good)">🧭 Sector Signal</button>''',
 '''<button class="view-tab" data-view="sigview" style="border-color:var(--good)">🧭 Sector Signal</button>
    <button class="view-tab" data-view="intlview" style="border-color:var(--accent)">🌍 International</button>'''),

('''<div id="autoPortfolioView" style="display:none">''',
 '''<div id="intlView" style="display:none">
    <iframe id="intlFrame" data-src="''' + _SRC + '''" title="International Cycle" style="width:100%;height:1600px;border:0;border-radius:10px;background:transparent" loading="lazy"></iframe>
  </div>
  <div id="autoPortfolioView" style="display:none">'''),

('''  $("rangeView").style.display = v==="rangeview" ? "block" : "none";''',
 '''  $("rangeView").style.display = v==="rangeview" ? "block" : "none";
  $("intlView").style.display = v==="intlview" ? "block" : "none";
  if(v === "intlview"){ const f = $("intlFrame"); if(f && !f.src) f.src = f.dataset.src; }
  if(!window._intlH){ window._intlH = 1; window.addEventListener("message", e => {
    if(e.data && e.data.intlHeight){ const f = $("intlFrame"); if(f) f.style.height = (e.data.intlHeight + 20) + "px"; } }); }'''),
]


def register():
    """Append INTL_PATCHES to patch_sector_page.PATCHES (called from build_sector_daily.run,
    which patch_sector_page.run invokes before it applies its patch list)."""
    import sys
    m = sys.modules.get("patch_sector_page")
    if m is None or not hasattr(m, "PATCHES"):
        return False
    if not any(o == INTL_PATCHES[0][0] for o, _ in m.PATCHES):
        m.PATCHES.extend(INTL_PATCHES)
    return True
