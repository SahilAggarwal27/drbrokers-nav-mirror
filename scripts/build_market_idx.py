#!/usr/bin/env python3
"""Builds docs/market-idx.json: year-end closes of the headline price indices
(Nifty 50, BSE Sensex) for the Performance Matrix reference rows.
Source: Yahoo Finance monthly bars (^NSEI, ^BSESN); Dec-2006 anchors seeded
(Yahoo's Nifty series starts Sep-2007).
Shape: {"v":1,"generated_ist":..,"years":[2006..],"i":{id:{"name":..,"ye":[close|0,..],
        "latest":close,"latest_date":"YYYY-MM-DD"}}}"""
import os, sys, json, time, urllib.request
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

HURDLE = 7.0          # FD-like hurdle: a calendar year below this = "dry" for a broad index
# market id -> (label, id in _sector_hist.dat, id in _index_tri.dat, page sector id for sparkline)
MARKETS = {
    "nifty50": ("Nifty 50", "nifty50", "nifty50", "benchmark"),
    "mid":     ("Midcap 150", "mid", "midcap150", "midcap"),
    "small":   ("Smallcap 250", "small", "smallcap250", "smallcap"),
}
NTFY_TOPIC = "drbrokers-calls-k7x29q"       # team subscribes to this topic in the ntfy app
ALERT_EMAIL = "sahil@drbrokers.in"

def gsec_10y():
    """India 10Y G-sec yield, monthly (OECD via FRED, ~2-month lag). {YYYY-MM: pct}"""
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=INDIRLTLT01STM"
    cache = os.path.join(_ROOT[0], "data", "history", "_gsec.dat") if _ROOT else None
    g = {}
    for k in range(3):   # FRED rejects browser UAs (503); a plain client UA works
        try:
            raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "curl/8.5.0"}), timeout=60).read().decode()
            for line in raw.splitlines()[1:]:
                d, _, v = line.partition(",")
                try: g[d[:7]] = float(v)
                except ValueError: pass
            if g: break
        except Exception as e:
            err = e
    if g and cache:
        with open(cache, "w") as f: json.dump(g, f, separators=(",", ":"))
    if not g and cache and os.path.exists(cache):
        g = json.load(open(cache)); print("  gsec: using cached series", file=sys.stderr)
    if not g: raise err
    return g

def _rate(c):
    """Buy rating from the checks. EXPENSIVE overrides; else 3+ passes = GOOD TO BUY."""
    hits = sum(1 for k in ("cheap", "corrected", "dry", "bond") if c.get(k))
    if c["pe_z"] > 1 and not c["corrected"]:
        return "EXPENSIVE", "CONTINUE", "STP 6–12M only", hits
    if hits >= 3: return "GOOD TO BUY", "START / STEP-UP", "DEPLOY (or STP 3M)", hits
    if hits == 2: return "ACCUMULATE", "STEP-UP", "STP 3–6M", hits
    return "FAIR", "CONTINUE", "STP 6M", hits

_ROOT = []
def market_context(root, pk=None):
    """Per broad index: TRI momentum, drawdown, P/E z (10Y), earnings-yield vs 10Y G-sec gap,
    calendar-year dry periods (TRI < HURDLE), after-dry returns, and the 4-check rating."""
    if not _ROOT: _ROOT.append(root)
    import statistics as st
    H = json.load(open(os.path.join(root, "data", "history", "_sector_hist.dat")))
    X = json.load(open(os.path.join(root, "data", "history", "_index_tri.dat")))
    try: G = gsec_10y()
    except Exception as e:
        print(f"  gsec fetch failed ({e})", file=sys.stderr); G = {}
    cy = datetime.now(IST).year
    out = {}
    for mid, (label, hid, xid, page_id) in MARKETS.items():
        try:
            T, P = H[hid]["tri"], H[hid]["pe"]
            t = max(T); tp = max(P)
            r = lambda k: round(100 * (T[t] / T[_sh(t, k)] - 1), 1) if _sh(t, k) in T else None
            dd = lambda k: round(100 * (T[t] / max(v for m, v in T.items() if _sh(t, 12 * k) <= m <= t) - 1), 1)
            ph = [v for m, v in P.items() if _sh(tp, 120) <= m <= tp]
            z = (P[tp] - st.mean(ph)) / (st.pstdev(ph) or 1e-9)
            # bond check: earnings yield (100/PE) minus 10Y G-sec, vs its own 10Y history
            gap = gap_z = gsec = gm = None
            if G:
                gm = max(G); gsec = G[gm]
                hist_gap = [100 / P[m] - G[m] for m in sorted(P) if m in G][-120:]
                gap = 100 / P[tp] - gsec
                if len(hist_gap) >= 36:
                    gap_z = (gap - st.mean(hist_gap)) / (st.pstdev(hist_gap) or 1e-9)
            # calendar-year TRI returns (NSE, back-calculated) incl. current-year YTD
            xi = X["i"][xid]; lv = {y: v for y, v in zip(X["years"], xi["ye"]) if v}
            if xi.get("latest") and str(xi.get("latest_date", ""))[:4] == str(cy): lv[cy] = xi["latest"]
            if T.get(t) and t[:4] == str(cy) and cy - 1 in lv: lv[cy] = T[t]   # fresher YTD from monthly cache
            R = {y: 100 * (lv[y] / lv[y - 1] - 1) for y in sorted(lv) if y - 1 in lv and y >= 2007}
            isdry = lambda y: y in R and (R[y] < 0 if y == cy else R[y] < HURDLE)
            yrs = sorted(R); streaks, s0 = [], None
            for y in yrs:
                if isdry(y):
                    if s0 is None: s0 = y
                elif s0 is not None: streaks.append((s0, y - 1)); s0 = None
            if s0 is not None: streaks.append((s0, yrs[-1]))
            cur = yrs[-1] - s0 + 1 if s0 is not None else 0
            lens = [b - a + 1 for a, b in streaks]
            def fwd(y, k):
                g = 1.0
                for q in range(y + 1, y + k + 1):
                    if q not in R or q >= cy: return None
                    g *= 1 + R[q] / 100
                return 100 * (g ** (1 / k) - 1)
            ent = [y for y in yrs if y < cy and isdry(y)]
            av = lambda k: (lambda v: round(st.mean(v), 1) if v else None)([x for x in (fwd(y, k) for y in ent) if x is not None])
            f1 = [x for x in (fwd(y, 1) for y in ent) if x is not None]
            top = (pk or {}).get(xid)
            c = {"pe_z": z, "cheap": z <= -0.5, "corrected": (top["dd"] if top else dd(5)) <= -10, "dry": cur >= 1,
                 "bond": (gap_z >= 0.5) if gap_z is not None else None}
            rating, sip, lump, hits = _rate(c)
            out[mid] = {"label": label, "page_id": page_id, "as_of": t,
                        "r3m": r(3), "r6m": r(6), "r12m": r(12), "dd5y": dd(5), "dd10y": dd(10),
                        "pe": round(P[tp], 1), "pe_median": round(st.median(ph), 1), "pe_z": round(z, 2),
                        "ey": round(100 / P[tp], 2), "gsec": gsec, "gsec_month": gm,
                        "gap": round(gap, 2) if gap is not None else None,
                        "gap_z": round(gap_z, 2) if gap_z is not None else None,
                        "ytd": round(R[cy], 1) if cy in R else None, "hurdle": HURDLE,
                        "dry_years": [y for y in yrs if isdry(y)],
                        "dry_avg": round(st.mean(lens), 1) if lens else None, "dry_max": max(lens) if lens else None,
                        "dry_cur": cur,
                        "after": {"count": len(f1), "avg1y": av(1), "avg2y": av(2), "avg3y": av(3),
                                  "won": sum(1 for x in f1 if x > HURDLE)},
                        "checks": {k: c[k] for k in ("cheap", "corrected", "dry", "bond")},
                        "rating": rating, "sip": sip, "lump": lump, "hits": hits,
                        "checks_avail": sum(1 for k in ("cheap", "corrected", "dry", "bond") if c[k] is not None),
                        "level": T[t], "top": top}
        except Exception as e:
            print(f"  market {mid} skipped: {e}", file=sys.stderr)
    return out

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
    doc = {"v": 2, "generated_ist": now.isoformat(), "source": "Yahoo Finance (^NSEI, ^BSESN), price index",
           "years": years, "i": out}
    try:
        doc["mkt"] = market_context(root)
    except Exception as e:
        print(f"  market context skipped: {e}", file=sys.stderr)
        if old.get("mkt"): doc["mkt"] = old["mkt"]
    os.makedirs(os.path.dirname(pub), exist_ok=True)
    with open(pub, "w") as f:
        json.dump(doc, f, separators=(",", ":"))
    print(f"  market-idx.json written ({len(out)} indices, {len(doc.get('mkt') or {})} market rows)")
    _register_final(root)
    return doc

# ── "Fall from Top": highest DAILY close of each NSE index TRI in the last 10 years ──
# Cache data/history/_peaks.dat = {index_id: {"y": {year: [max, "YYYY-MM-DD"]}}}; past years are
# fetched once, the current year is re-fetched every build (1 request per index).
PEAK_YEARS = 10
def peaks(root):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import build_index_tri as bi
    path = os.path.join(root, "data", "history", "_peaks.dat")
    try: C = json.load(open(path))
    except Exception: C = {}
    now = datetime.now(IST); cy = now.year
    try: bi._session()
    except Exception: pass
    out = {}
    for iid, name in bi.INDICES.items():
        c = C.setdefault(iid, {"y": {}}); last = None
        try:
            for y in range(cy - PEAK_YEARS, cy + 1):
                if str(y) in c["y"] and y < cy: continue
                end = datetime(y, 12, 31) if y < cy else now.replace(tzinfo=None)
                rows = [r for r in bi.fetch_tri(name, datetime(y, 1, 1), end) if r[0].year == y]
                time.sleep(0.3)
                if rows:
                    mx = max(rows, key=lambda r: r[1]); c["y"][str(y)] = [mx[1], mx[0].strftime("%Y-%m-%d")]
                    if y == cy: last = max(rows, key=lambda r: r[0])
                elif y < cy: c["y"][str(y)] = [0, None]
        except Exception as e:
            print(f"  peaks {name}: {e}", file=sys.stderr)
        win = [v for k, v in c["y"].items() if int(k) >= cy - PEAK_YEARS and v[0]]
        if last: c["now"] = [last[1], last[0].strftime("%Y-%m-%d")]
        if win and c.get("now"):
            pk = max(win, key=lambda v: v[0])
            out[iid] = {"peak": pk[0], "peak_date": pk[1], "now": c["now"][0], "now_date": c["now"][1],
                        "dd": round(100 * (c["now"][0] / pk[0] - 1), 1)}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f: json.dump(C, f, separators=(",", ":"))
    print(f"  peaks: {len(out)} indices")
    return out

# ── Call log + change alerts (run once, at the very end of the build, on fresh data) ──
def _alert(lines):
    body = "\n".join(lines)
    try:
        req = urllib.request.Request("https://ntfy.sh/" + NTFY_TOPIC, data=body.encode("utf-8"), method="POST",
              headers={"Title": "DR Brokers: %d call change%s" % (len(lines), "" if len(lines) == 1 else "s"),
                       "Tags": "chart_with_upwards_trend", "Click": "https://nbd.drbrokers.in/sector-cycle/",
                       **({"Email": ALERT_EMAIL} if ALERT_EMAIL else {})})
        urllib.request.urlopen(req, timeout=30).read()
        print(f"  alert sent ({len(lines)} changes)")
    except Exception as e:
        print(f"  alert failed: {e}", file=sys.stderr)

def log_calls(root, mkt):
    """Persists every call change (data/history/_call_log.dat, committed by the workflow) and
    publishes docs/call-log.json with the return since each call. Alerts on changes."""
    H = json.load(open(os.path.join(root, "data", "history", "_sector_hist.dat")))
    lvl = lambda hid: (lambda T: T[max(T)] if T else None)(H.get(hid, {}).get("tri", {}))
    calls = {}
    for mid, m in (mkt or {}).items():
        calls["mkt_" + mid] = (m["label"] + " (market)", m["rating"], MARKETS[mid][1])
    try:
        sig = json.load(open(os.path.join(root, "docs", "sector-signals.json")))
        for it in sig.get("items", []):
            if it.get("call") and it["call"] != "INSUFFICIENT HISTORY":
                calls["sig_" + it["id"]] = (it["label"], it["call"], it["id"])
    except Exception as e:
        print(f"  call log: sector-signals.json unavailable ({e})", file=sys.stderr)
    if not calls: return
    path = os.path.join(root, "data", "history", "_call_log.dat")
    try: L = json.load(open(path))
    except Exception: L = {"current": {}, "changes": []}
    today = datetime.now(IST).strftime("%Y-%m-%d"); nlv = lvl("nifty50"); alerts = []
    for key, (label, call, hid) in calls.items():
        cur = L["current"].get(key)
        if cur is None:
            L["current"][key] = {"label": label, "call": call, "since": today, "level": lvl(hid), "nifty": nlv, "hid": hid}
        elif cur["call"] != call:
            L["changes"].append({"date": today, "key": key, "label": label, "from": cur["call"], "to": call,
                                 "level": lvl(hid), "nifty": nlv, "hid": hid})
            alerts.append(f"{label}: {cur['call']} → {call}")
            L["current"][key] = {"label": label, "call": call, "since": today, "level": lvl(hid), "nifty": nlv, "hid": hid}
    L["updated_ist"] = datetime.now(IST).isoformat()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f: json.dump(L, f, separators=(",", ":"))
    def since(e):
        a, b = lvl(e["hid"]), e.get("level")
        if not a or not b: return None, None
        ret = 100 * (a / b - 1)
        rel = ret - 100 * (nlv / e["nifty"] - 1) if nlv and e.get("nifty") else None
        return round(ret, 1), (round(rel, 1) if rel is not None else None)
    pubc = []
    for k, e in L["current"].items():
        if k not in calls: continue
        r1, r2 = since(e); pubc.append({"key": k, "label": e["label"], "call": e["call"], "since": e["since"], "ret": r1, "vs_nifty": r2})
    pubh = []
    for e in L["changes"][-300:][::-1]:
        r1, r2 = since(e); pubh.append({"date": e["date"], "label": e["label"], "from": e["from"], "to": e["to"], "ret": r1, "vs_nifty": r2})
    with open(os.path.join(root, "docs", "call-log.json"), "w") as f:
        json.dump({"v": 1, "generated_ist": L["updated_ist"], "tracking_since": min(e["since"] for e in L["current"].values()),
                   "current": pubc, "changes": pubh, "alerts_topic": NTFY_TOPIC}, f, separators=(",", ":"))
    print(f"  call-log.json written ({len(pubc)} calls, {len(L['changes'])} changes logged)")
    if alerts: _alert(alerts)

_FINAL = []
def _register_final(root):
    """Run once at interpreter exit — after build_index_tri / build_sector_signals have refreshed
    the caches — so the published market rows and the call log use today's data."""
    if _FINAL: return
    import atexit
    def _final():
        try:
            doc = json.load(open(os.path.join(root, "docs", "market-idx.json")))
            try:
                doc["peaks"] = peaks(root)
            except Exception as e:
                print(f"  peaks skipped: {e}", file=sys.stderr)
            try:
                doc["mkt"] = market_context(root, doc.get("peaks"))
                with open(os.path.join(root, "docs", "market-idx.json"), "w") as f:
                    json.dump(doc, f, separators=(",", ":"))
            except Exception as e:
                print(f"  final market refresh skipped: {e}", file=sys.stderr)
            log_calls(root, doc.get("mkt"))
        except Exception as e:
            print(f"  call log skipped: {e}", file=sys.stderr)
    atexit.register(_final); _FINAL.append(1)

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
      if(mj.mkt) mktIdx._mkt = mj.mkt;
      if(mj.peaks) mktIdx._peaks = mj.peaks;
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

('const CACHE_KEY = "mf_sector_cycle_v77_sip";', 'const CACHE_KEY = "mf_sector_cycle_v82_top";'),

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
    // Market rows (Nifty 50 / Midcap 150 / Smallcap 250) — all numbers + rating computed in the build
    // (build_market_idx.py). 4 checks: Cheap (P/E z ≤ -0.5 vs 10Y) · ≥10% off 5Y peak ·
    // Dry (calendar-year TRI < 7% ≈ FD; YTD counts if < 0) · Bond (earnings yield − 10Y G-sec gap z ≥ +0.5).
    const M = (d.mktIdx||{})._mkt; if(!M) return;
    const na = "<span style='color:var(--muted)'>—</span>";
    const RC = { "GOOD TO BUY":["🟢","var(--good)"], "ACCUMULATE":["🟡","var(--warn)"], "FAIR":["🔵","#60a5fa"], "EXPENSIVE":["🔴","var(--bad)"] };
    const col = t => /START|STEP|DEPLOY/.test(t) ? "var(--good)" : /only/.test(t) ? "var(--warn)" : "#60a5fa";
    const ck = (ok, txt) => ok==null ? `<span style="color:var(--muted)">· ${txt} n/a</span>` : `<span style="color:${ok?"var(--good)":"var(--muted)"}">${ok?"✓":"✗"} ${txt}</span>`;
    const pc = x => x==null ? "—" : (x>=0?"+":"")+x.toFixed(1)+"%";
    const S = "background:rgba(96,165,250,.07)";
    const ids = ["nifty50","mid","small"].filter(k => M[k]);
    ids.forEach((k, idx) => {
      const m = M[k], z = m.pe_z, rc = RC[m.rating] || ["",""];
      const val = z > 1 ? ["EXPENSIVE","var(--bad)"] : z > 0.5 ? ["ABOVE AVG","var(--warn)"] : z < -1 ? ["CHEAP","var(--good)"] : z < -0.5 ? ["BELOW AVG","var(--good)"] : ["FAIR","#60a5fa"];
      const a = m.after || {};
      const last = idx === ids.length - 1;
      html += `<tr style="${S};${last?"border-bottom:2px solid var(--border)":""}">
      <td style="${S}"><strong>📈 MARKET — ${m.label}</strong><br><span style="font-size:9.5px;color:var(--muted)">context · as of ${m.as_of}</span></td>
      <td style="color:var(--muted);font-size:11.5px">${m.label} TRI (NSE)<br><span style="font-size:10px">${k==="nifty50"?"benchmark for every row below":"broad-market reference"}</span></td>
      <td class='r'>${sparkline(m.page_id)}</td>
      <td class='r'><span style='color:#60a5fa;font-weight:800;font-size:10px'>📊 PURE INDEX</span></td>
      <td class='r' title="Dry year = TRI return below ${m.hurdle}% (≈ FD); current year counts if YTD is negative. Dry years: ${(m.dry_years||[]).join(", ")}">${m.dry_avg!=null ? m.dry_avg.toFixed(1)+'y / '+m.dry_max+'y' : '—'}<br><span style="font-size:9.5px;color:var(--muted)">yr &lt; ${m.hurdle}% (FD)</span></td>
      <td class='r' style='font-size:12px' title="Bought at the end of every dry year (no hindsight); ${a.won}/${a.count} next years beat ${m.hurdle}%">${fmtBounceCagr(a)}<br><span style="font-size:9.5px;color:var(--muted)">${a.won}/${a.count} beat FD next yr</span></td>
      <td class='r' style='font-size:12px'>${_fromTop(m.top, m.dd10y)}</td>
      <td class='r'>${na}</td>
      <td class='r' style='font-size:12px'>${fmtMom({r3m:m.r3m, r6m:m.r6m, r12m:m.r12m})}</td>
      <td class='r'>${m.dry_cur ? `<span style='font-size:15px;font-weight:800;color:${m.dry_cur>=2?"var(--warn)":"var(--accent)"}'>${m.dry_cur}y</span><br><span style='font-size:10px;color:var(--muted)'>below FD</span>` : "<span style='color:var(--muted)'>0</span>"}</td>
      <td><span style='font-size:11px;font-weight:800;color:${val[1]};white-space:nowrap'>${val[0]}</span><br><span style='font-size:9.5px;color:var(--muted);line-height:1.3'>P/E ${m.pe} vs 10Y median ${m.pe_median} · z ${z>0?"+":""}${z.toFixed(2)}${m.gap!=null?`<br>EY ${m.ey}% − G-sec ${m.gsec}% = ${m.gap>0?"+":""}${m.gap.toFixed(1)}% (z ${m.gap_z>0?"+":""}${m.gap_z})`:""}</span></td>
      <td><span style='font-size:11.5px;font-weight:800;color:${rc[1]};white-space:nowrap'>${rc[0]} ${m.rating}</span><br><span style='font-size:9.5px;line-height:1.5'>${ck(m.checks.cheap,"Cheap (P/E z ≤ -0.5)")}<br>${ck(m.checks.corrected,"≥10% off peak")}<br>${ck(m.checks.dry,"Dry (yr < FD)")}<br>${ck(m.checks.bond,"Bond gap above avg")}</span><br><span style='font-size:9.5px;color:${m.ytd==null?"var(--muted)":m.ytd>=0?"var(--good)":"var(--bad)"}'>YTD ${pc(m.ytd)}</span></td>
      <td><span style='font-size:11px;font-weight:800;color:${col(m.sip)};white-space:nowrap'>${/START|STEP/.test(m.sip)?"✅":"▶"} ${m.sip}</span><br><span style='font-size:9.5px;color:var(--muted)'>${k==="nifty50"?"core diversified SIPs":m.label+" funds"}</span></td>
      <td><span style='font-size:11px;font-weight:800;color:${col(m.lump)};white-space:nowrap'>${/DEPLOY/.test(m.lump)?"✅":/only/.test(m.lump)?"⏳":"▶"} ${m.lump}</span><br><span style='font-size:9.5px;color:var(--muted)'>${m.hits}/${m.checks_avail} checks · 3+ = buy</span></td>
      <td class='r'>${na}</td>
    </tr>`;
    });
  })();
  for(const r of rows){
    const bExt"""),

# ── Sector Signal tab: call log / track record (docs/call-log.json, built at end of each build) ──
(r"""    <div id="sigBody" style="color:var(--muted)">Loading…</div>""",
 r"""    <div id="sigBody" style="color:var(--muted)">Loading…</div>
    <div id="callLog" style="color:var(--muted);margin-top:22px"></div>"""),
(r"""  if(v === "sigview") setTimeout(renderSigView, 20);""",
 r"""  if(v === "sigview"){ setTimeout(renderSigView, 20); setTimeout(renderCallLog, 40); }"""),
(r"""// Tab click handler — wire all view-tab buttons to switchView""",
 r"""let _clDone = false;
async function renderCallLog(){
  if(_clDone) return;
  try{
    const j = await fetch("https://sahilaggarwal27.github.io/drbrokers-nav-mirror/call-log.json", {cache:"no-cache"}).then(r => r.json());
    const pc = v => v==null ? "—" : `<span style="color:${v>=0?"var(--good)":"var(--bad)"};font-weight:700">${v>=0?"+":""}${v.toFixed(1)}%</span>`;
    const TH = h => `<th style="padding:7px 9px;text-align:left;font-size:10px;background:rgba(255,255,255,.04)">${h}</th>`;
    const TD = x => `<td style="padding:7px 9px;font-size:12px;border-bottom:1px solid var(--border)">${x}</td>`;
    let h = `<h2 style="font-size:14px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin:0 0 6px;font-weight:700">📜 Call Log — track record</h2>
      <p style="font-size:12px;margin:0 0 10px">Every call is logged the day it changes, with the index level then. Return = index TRI since the call; vs Nifty = minus Nifty 50 TRI over the same period. Tracking since <b style="color:var(--text)">${j.tracking_since}</b>. Alerts: ntfy app → subscribe to <b style="color:var(--text)">${j.alerts_topic}</b>.</p>`;
    if(j.changes && j.changes.length){
      h += `<div style="overflow-x:auto;margin-bottom:14px"><table style="width:100%;border-collapse:collapse"><tr>${TH("Date")}${TH("Index")}${TH("Call change")}${TH("Return since")}${TH("vs Nifty")}</tr>`;
      for(const c of j.changes) h += `<tr>${TD(c.date)}${TD("<b style='color:var(--text)'>"+c.label+"</b>")}${TD(c.from+" → <b style='color:var(--text)'>"+c.to+"</b>")}${TD(pc(c.ret))}${TD(pc(c.vs_nifty))}</tr>`;
      h += `</table></div>`;
    } else h += `<div style="font-size:12px;margin-bottom:12px">No call changes yet — changes appear here (and as alerts) from the next build onward.</div>`;
    h += `<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse"><tr>${TH("Index")}${TH("Current call")}${TH("Since")}${TH("Return since")}${TH("vs Nifty")}</tr>`;
    for(const c of (j.current||[])) h += `<tr>${TD("<b style='color:var(--text)'>"+c.label+"</b>")}${TD(c.call)}${TD(c.since)}${TD(pc(c.ret))}${TD(pc(c.vs_nifty))}</tr>`;
    $("callLog").innerHTML = h + `</table></div>`;
    _clDone = true;
  }catch(e){ $("callLog").textContent = "Call log not available yet: " + e.message; }
}

// Tab click handler — wire all view-tab buttons to switchView"""),

# ── "Fall from Top": plain-language drawdown vs the highest DAILY close in 10 years ──
(r"""    <th class='r'>DD from peak<br><span style='font-size:9px;font-weight:400'>5Y / 10Y</span></th>""",
 r"""    <th class='r' title="How much lower it is today than its highest price in the last 10 years">Fall from Top<br><span style='font-size:9px;font-weight:400'>vs 10-yr high</span></th>"""),
(r"""function renderCycleTable(){""",
 r"""function _fromTop(t, approxDD){
  // t = {dd, peak_date} from daily NSE TRI (market-idx.json peaks); approxDD = year-end fallback
  const dd = t ? t.dd : approxDD;
  if(dd == null) return "<span style='color:var(--muted)'>—</span>";
  const b = dd > -5 ? ["Near top","var(--good)"] : dd > -10 ? ["Small dip","#fbbf24"] : dd > -20 ? ["Correction","var(--warn)"] : dd > -35 ? ["Big fall","var(--bad)"] : ["Crash","var(--bad)"];
  const M = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const when = t && t.peak_date ? M[+t.peak_date.slice(5,7)-1] + "-" + t.peak_date.slice(0,4) : null;
  const now = Math.round(100 + dd);
  const line = dd > -0.5 ? "at its 10-yr high today" : `₹100 at its ${when ? when+" " : ""}high = ₹${now} today`;
  const tip = "How much lower it is today than its highest price in the last 10 years" + (t ? " (daily NSE index data)" : " (approx — year-end data, fund proxy)");
  return `<div title="${tip}"><span style="font-size:14px;font-weight:800;color:${b[1]}">${dd > -0.5 ? "0%" : dd.toFixed(0)+"%"}</span><br><span style="font-size:9.5px;color:var(--muted);line-height:1.3">${line}</span><br><span style="font-size:10px;font-weight:700;color:${b[1]}">${b[0]}</span>${t ? "" : "<span style='font-size:9px;color:var(--muted)'> · approx</span>"}</div>`;
}
function renderCycleTable(){"""),
(r"""      <td class='r' style='font-size:12px'>${fmtDD(dd)}</td>""",
 r"""      <td class='r' style='font-size:12px'>${_fromTop((((d.mktIdx||{})._peaks)||{})[((d.indexUsed||{})[r.sec.id]||{}).id], dd && dd.dd10y)}</td>"""),
]


if __name__ == "__main__":
    run(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
