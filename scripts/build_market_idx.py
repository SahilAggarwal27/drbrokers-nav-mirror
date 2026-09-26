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
    os.makedirs(os.path.dirname(pub), exist_ok=True)
    with open(pub, "w") as f:
        json.dump({"v": 1, "generated_ist": now.isoformat(), "source": "Yahoo Finance (^NSEI, ^BSESN), price index",
                   "years": years, "i": out}, f, separators=(",", ":"))
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
    }
  } catch(e){ console.warn("Market index load failed", e); }
'''),

('''  const data = { entries, indexUsed, sectorFunds, expandedSectors,''', '''  const data = { entries, mktIdx, indexUsed, sectorFunds, expandedSectors,'''),

(r'''  html += "</tbody>";
  $("heatmap").innerHTML = html;''',
 r'''  for(const [iid, lbl] of [["nifty50","Nifty 50"],["sensex","Sensex"]]){
    const mx = (d.mktIdx||{})[iid]; if(!mx) continue;
    html += `<tr${iid==="nifty50"?' style="border-top:2px solid var(--border)"':''}><th class='row-label' style='background:var(--panel)'>${lbl} <span style="background:rgba(255,255,255,.08);color:var(--muted);font-size:8px;font-weight:800;padding:1px 5px;border-radius:99px;letter-spacing:.4px">PRICE</span><br><span style="font-size:9.5px;color:var(--muted);font-weight:400">Calendar-year · excl. dividends</span></th>`;
    for(const y of YEARS){
      const ret = mx.ret[y];
      html += `<td class='${ret==null?'empty':'h-mid'}' title='${y}: ${mx.name} ${ret==null?'no data':fmtPct1(ret)}${y===curYr?' (YTD to '+mx.asOf+')':''}' style="background:rgba(255,255,255,.04);color:${ret==null?'inherit':ret>=0?'var(--good)':'var(--bad)'}">${ret==null?"":fmtPct(ret)}</td>`;
    }
    html += "</tr>";
  }
  html += "</tbody>";
  $("heatmap").innerHTML = html;'''),

('const CACHE_KEY = "mf_sector_cycle_v77_sip";', 'const CACHE_KEY = "mf_sector_cycle_v78_mkt";'),
]


if __name__ == "__main__":
    run(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
