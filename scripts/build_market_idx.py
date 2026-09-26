#!/usr/bin/env python3
"""Builds docs/market-idx.json: year-end closes of the headline price indices
(Nifty 50, BSE Sensex) for the Performance Matrix reference rows.
Source: Yahoo Finance monthly bars (^NSEI, ^BSESN); Dec-2006 anchors seeded
(Yahoo's Nifty series starts Sep-2007).
Shape: {"v":1,"generated_ist":..,"years":[2006..],"i":{id:{"name":..,"ye":[close|0,..],
        "latest":close,"latest_date":"YYYY-MM-DD"}}}"""
import os, sys, json, urllib.request
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
FIRST_YEAR = 2006
INDICES = {
    "nifty50": ("Nifty 50", "%5ENSEI", {2006: 3966.40}),
    "sensex":  ("BSE Sensex", "%5EBSESN", {2006: 13786.91}),
}

def monthly(sym):
    out = {}
    for host in ("query1", "query2"):
        try:
            url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}?range=max&interval=1mo"
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            d = json.loads(urllib.request.urlopen(req, timeout=60).read())["chart"]["result"][0]
            for t, c in zip(d["timestamp"], d["indicators"]["quote"][0]["close"]):
                if c:
                    dt = datetime.fromtimestamp(t, IST)
                    out[(dt.year, dt.month)] = float(c)
            m = d.get("meta", {})
            lp, lt = m.get("regularMarketPrice"), m.get("regularMarketTime")
            return out, (float(lp) if lp else None), (datetime.fromtimestamp(lt, IST) if lt else None)
        except Exception as e:
            err = e
    raise err

def _sh(m, k):
    y, mo = map(int, m.split("-")); t = y * 12 + mo - 1 - k
    return "%d-%02d" % (t // 12, t % 12 + 1)

def market_context(root):
    """Nifty 50 context for the Cycle Summary: TRI momentum, drawdown from peak, P/E vs its
    10-yr history. Reads the monthly NSE TRI + P/E cache kept by build_sector_signals.py."""
    import statistics as st
    h = json.load(open(os.path.join(root, "data", "history", "_sector_hist.dat")))["nifty50"]
    T, P = h["tri"], h["pe"]
    t = max(T); tp = max(P)
    r = lambda k: round(100 * (T[t] / T[_sh(t, k)] - 1), 1) if _sh(t, k) in T else None
    dd = lambda k: round(100 * (T[t] / max(v for m, v in T.items() if _sh(t, 12 * k) <= m <= t) - 1), 1)
    ph = [v for m, v in P.items() if _sh(tp, 120) <= m <= tp]
    z = (P[tp] - st.mean(ph)) / (st.pstdev(ph) or 1e-9)
    return {"as_of": t, "r3m": r(3), "r6m": r(6), "r12m": r(12), "dd5y": dd(5), "dd10y": dd(10),
            "pe": round(P[tp], 1), "pe_median": round(st.median(ph), 1), "pe_z": round(z, 2)}

def run(root):
    pub = os.path.join(root, "docs", "market-idx.json")
    now = datetime.now(IST)
    years = list(range(FIRST_YEAR, now.year))
    try:
        old = json.load(open(pub))
    except Exception:
        old = {"i": {}}
    out = {}
    for iid, (name, sym, seed) in INDICES.items():
        try:
            m, lp, lt = monthly(sym)
            ye = [m.get((y, 12)) or seed.get(y) or 0 for y in years]
            if not lp:
                k = max(m); lp = m[k]
            out[iid] = {"name": name, "ye": [round(v, 2) for v in ye], "latest": round(lp, 2),
                        "latest_date": (lt or now).strftime("%Y-%m-%d")}
            print(f"  {name}: latest {out[iid]['latest']} ({out[iid]['latest_date']})")
        except Exception as e:
            print(f"  {name}: FAILED ({e}) — keeping previous", file=sys.stderr)
            if iid in old.get("i", {}): out[iid] = old["i"][iid]
    if not out:
        raise RuntimeError("no market index data")
    doc = {"v": 1, "generated_ist": now.isoformat(), "source": "Yahoo Finance (^NSEI, ^BSESN), price index",
           "years": years, "i": out}
    try:
        doc["market"] = market_context(root)
    except Exception as e:
        print(f"  market context skipped: {e}", file=sys.stderr)
        if old.get("market"): doc["market"] = old["market"]
    os.makedirs(os.path.dirname(pub), exist_ok=True)
    with open(pub, "w") as f:
        json.dump(doc, f, separators=(",", ":"))
    print(f"  market-idx.json written ({len(out)} indices)")
    return True

# ── Performance Matrix: Nifty 50 + Sensex calendar-year (price) returns rows (26-Sep-2026) ──
# Data: docs/market-idx.json (scripts/build_market_idx.py, rebuilt daily).
MKT_PATCHES = [
(r'''  } catch(e){ console.warn("Fund picks load failed", e); }
''',
 r'''  } catch(e){ console.warn("Fund picks load failed", e); }
  // Headline price indices (Nifty 50, Sensex) — calendar-year returns for reference rows.
  const mktIdx = {};
  try {
    const mr = await fetch("https://sahilaggarwal27.github.io/drbrokers-nav-mirror/market-idx.json", {cache:"no-cache"});
    if(mr.ok){
      const mj = await mr.json();
      const curY = new Date().getFullYear();
      for(const iid of ["nifty50","sensex"]){
        const ix = mj.i && mj.i[iid]; if(!ix) continue;
        const lv = {};
        mj.years.forEach((y,k)=>{ if(ix.ye[k]) lv[y] = ix.ye[k]; });
        if(ix.latest && +String(ix.latest_date).slice(0,4) === curY) lv[curY] = ix.latest;
        const r = {};
        for(const y of YEARS){ if(lv[y] && lv[y-1]) r[y] = (lv[y]/lv[y-1] - 1)*100; }
        mktIdx[iid] = { name: ix.name, ret: r, asOf: ix.latest_date };
      }
      if(mj.market) mktIdx._market = mj.market;
    }
  } catch(e){ console.warn("Market index load failed", e); }
'''),

('''  const data = { entries, indexUsed, sectorFunds, expandedSectors,''', '''  const data = { entries, mktIdx, indexUsed, sectorFunds, expandedSectors,'''),

(r'''  html += "</tbody>";
  $("heatmap").innerHTML = html;''',
 r'''  for(const [iid, lbl] of [["sensex","Sensex"]]){
    const mx = (d.mktIdx||{})[iid]; if(!mx) continue;
    html += `<tr><th class='row-label' style='background:var(--panel)'>${lbl} <span style="background:rgba(255,255,255,.08);color:var(--muted);font-size:8px;font-weight:800;padding:1px 5px;border-radius:99px;letter-spacing:.4px">PRICE</span><br><span style="font-size:9.5px;color:var(--muted);font-weight:400">Calendar-year · excl. dividends</span></th>`;
    for(const y of YEARS){
      const ret = mx.ret[y];
      html += `<td class='${ret==null?'empty':'h-mid'}' title='${y}: ${mx.name} ${ret==null?'no data':fmtPct1(ret)}${y===curYr?' (YTD to '+mx.asOf+')':''}' style="background:rgba(255,255,255,.04);color:${ret==null?'inherit':ret>=0?'var(--good)':'var(--bad)'}">${ret==null?"":fmtPct(ret)}</td>`;
    }
    html += "</tr>";
  }
  html += "</tbody>";
  $("heatmap").innerHTML = html;'''),

('const CACHE_KEY = "mf_sector_cycle_v77_sip";', 'const CACHE_KEY = "mf_sector_cycle_v80_niftydry";'),

# One Nifty row only: the benchmark row is Nifty 50 TRI (not the UTI fund) — say so.
(r"""<span style="font-size:9.5px;color:var(--muted);font-weight:400">${bFund?bFund.schemeName.slice(0,24)+"…":'—'}</span></th>`;""",
 r"""<span style="font-size:9.5px;color:var(--muted);font-weight:400">NSE TRI · incl. dividends</span></th>`;"""),

# Cycle Summary: pinned "Market — Nifty 50" context row (TRI momentum, DD, P/E z). Dry/bounce/verdict
# columns don't apply to the benchmark itself.
(r"""  </tr></thead><tbody>`;
  for(const r of rows){
    const bExt""",
 r"""  </tr></thead><tbody>`;
  (function(){
    // Nifty 50 rating — 3 checks: CHEAP (P/E z ≤ -0.5 vs 10Y), CORRECTED (≥10% off 5Y peak),
    // DRY (calendar-year TRI return < 7% ≈ FD, i.e. equity paid less than debt; YTD counts if < 0).
    const m = (d.mktIdx||{})._market; if(!m) return;
    const na = "<span style='color:var(--muted)'>—</span>";
    const R = (d.returnsByYear||{}).benchmark || {};
    const cy = new Date().getFullYear(), HURDLE = 7;
    const isDry = y => R[y] != null && (y === cy ? R[y] < 0 : R[y] < HURDLE);
    // dry streaks + current streak
    const streaks = []; let st0 = null;
    for(const y of YEARS){ if(isDry(y)){ if(st0==null) st0 = y; } else if(st0!=null){ streaks.push([st0, y-1]); st0 = null; } }
    if(st0!=null) streaks.push([st0, YEARS[YEARS.length-1]]);
    const cur = st0!=null ? YEARS[YEARS.length-1] - st0 + 1 : 0;
    const lens = streaks.map(s => s[1]-s[0]+1);
    const avgDry = lens.length ? lens.reduce((a,b)=>a+b,0)/lens.length : 0, maxDry = lens.length ? Math.max(...lens) : 0;
    // after-dry: buy at the end of EVERY dry year (no hindsight), forward 1/2/3Y CAGR on completed years
    const fwd = (y,k) => { let g = 1; for(let t=y+1; t<=y+k; t++){ if(R[t]==null || t>=cy) return null; g *= 1 + R[t]/100; } return (Math.pow(g, 1/k) - 1)*100; };
    const ent = YEARS.filter(y => y < cy && isDry(y));
    const av = k => { const v = ent.map(y => fwd(y,k)).filter(x => x!=null); return v.length ? v.reduce((a,b)=>a+b,0)/v.length : null; };
    const f1 = ent.map(y => fwd(y,1)).filter(x => x!=null);
    const bExt = { count: f1.length, avg1y: av(1), avg2y: av(2), avg3y: av(3) };
    const won = f1.filter(x => x > HURDLE).length;
    const z = m.pe_z;
    const cheap = z <= -0.5, corrected = m.dd5y <= -10, dry = cur >= 1;
    const hits = [cheap, corrected, dry].filter(Boolean).length;
    let v;
    if(z > 1 && !corrected) v = { t:"🔴 EXPENSIVE", c:"var(--bad)", sip:["▶ CONTINUE","#60a5fa"], lump:["⏳ STP 6–12M only","var(--warn)"] };
    else if(hits === 3) v = { t:"🟢 GOOD TO BUY", c:"var(--good)", sip:["✅ START / STEP-UP","var(--good)"], lump:["✅ DEPLOY (or STP 3M)","var(--good)"] };
    else if(hits === 2) v = { t:"🟡 ACCUMULATE", c:"var(--warn)", sip:["✅ STEP-UP","var(--good)"], lump:["▶ STP 3–6M","#60a5fa"] };
    else v = { t:"🔵 FAIR", c:"#60a5fa", sip:["▶ CONTINUE","#60a5fa"], lump:["▶ STP 6M","#60a5fa"] };
    const val = z > 1 ? ["EXPENSIVE","var(--bad)"] : z > 0.5 ? ["ABOVE AVG","var(--warn)"] : z < -1 ? ["CHEAP","var(--good)"] : z < -0.5 ? ["BELOW AVG","var(--good)"] : ["FAIR","#60a5fa"];
    const ck = (ok, txt) => `<span style="color:${ok?"var(--good)":"var(--muted)"}">${ok?"✓":"✗"} ${txt}</span>`;
    const ytd = R[cy];
    const pc = x => x==null ? "—" : (x>=0?"+":"")+x.toFixed(1)+"%";
    const S = "background:rgba(96,165,250,.07)";
    html += `<tr style="${S};border-bottom:2px solid var(--border)">
      <td style="${S}"><strong>📈 MARKET — Nifty 50</strong><br><span style="font-size:9.5px;color:var(--muted)">context · as of ${m.as_of}</span></td>
      <td style="color:var(--muted);font-size:11.5px">Nifty 50 TRI (NSE)<br><span style="font-size:10px">benchmark for every row below</span></td>
      <td class='r'>${sparkline("benchmark")}</td>
      <td class='r'><span style='color:#60a5fa;font-weight:800;font-size:10px'>📊 PURE INDEX</span></td>
      <td class='r' title="Dry year = Nifty TRI return below ${HURDLE}% (≈ FD); current year counts if YTD is negative">${lens.length ? avgDry.toFixed(1)+'y / '+maxDry+'y' : '—'}<br><span style="font-size:9.5px;color:var(--muted)">yr &lt; ${HURDLE}% (FD)</span></td>
      <td class='r' style='font-size:12px' title="Bought at the end of every dry year; ${won}/${f1.length} next years beat ${HURDLE}%">${fmtBounceCagr(bExt)}<br><span style="font-size:9.5px;color:var(--muted)">${won}/${f1.length} beat FD next yr</span></td>
      <td class='r' style='font-size:12px'>${fmtDD({dd5y:m.dd5y, dd10y:m.dd10y})}</td>
      <td class='r'>${na}</td>
      <td class='r' style='font-size:12px'>${fmtMom({r3m:m.r3m, r6m:m.r6m, r12m:m.r12m})}</td>
      <td class='r'>${cur ? `<span style='font-size:15px;font-weight:800;color:${cur>=2?"var(--warn)":"var(--accent)"}'>${cur}y</span><br><span style='font-size:10px;color:var(--muted)'>below FD</span>` : "<span style='color:var(--muted)'>0</span>"}</td>
      <td><span style='font-size:11px;font-weight:800;color:${val[1]};white-space:nowrap'>${val[0]}</span><br><span style='font-size:9.5px;color:var(--muted);line-height:1.3'>P/E ${m.pe} vs 10Y median ${m.pe_median} · z ${z>0?"+":""}${z.toFixed(2)}</span></td>
      <td><span style='font-size:11.5px;font-weight:800;color:${v.c};white-space:nowrap'>${v.t}</span><br><span style='font-size:9.5px;line-height:1.5'>${ck(cheap,"Cheap (P/E z ≤ -0.5)")}<br>${ck(corrected,"≥10% off peak")}<br>${ck(dry,"Dry (yr < FD)")}</span><br><span style='font-size:9.5px;color:${ytd==null?"var(--muted)":ytd>=0?"var(--good)":"var(--bad)"}'>YTD ${pc(ytd)}</span></td>
      <td><span style='font-size:11px;font-weight:800;color:${v.sip[1]};white-space:nowrap'>${v.sip[0]}</span><br><span style='font-size:9.5px;color:var(--muted)'>core diversified SIPs</span></td>
      <td><span style='font-size:11px;font-weight:800;color:${v.lump[1]};white-space:nowrap'>${v.lump[0]}</span><br><span style='font-size:9.5px;color:var(--muted)'>${hits}/3 checks</span></td>
      <td class='r'>${na}</td>
    </tr>`;
  })();
  for(const r of rows){
    const bExt"""),
]


if __name__ == "__main__":
    run(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
