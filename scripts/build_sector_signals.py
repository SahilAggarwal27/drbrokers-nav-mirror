#!/usr/bin/env python3
"""Builds docs/sector-signals.json: which SEGMENT or SECTOR to favour now (size segments +
sectoral NSE indices), using only NSE index data (TRI + P/E) from niftyindices.com.
Tested rule (monthly signals 2016-25, next-12M return vs Nifty 50):
  DRY     : 24M return trails Nifty 50 by > 10%
  CHEAP   : P/E z-score vs trailing 10-yr monthly history < -0.5
  TURNING : 3M return ahead of Nifty 50
  ENTER      = DRY + CHEAP + TURNING
  WAIT FOR TURN = DRY + CHEAP but not yet turning (tested: no edge until it turns)
  AVOID/TRIM = HOT (24M ahead of Nifty > 20% and P/E z > 0.5);  EXPENSIVE = P/E z > 2
  WATCH      = CHEAP only;  NEUTRAL = everything else
Recent winners are never a buy signal (sector momentum showed no edge in the test).
The evidence table is recomputed on every run from the stored history.
Monthly history persists in data/history/_sector_hist.dat; only the current year is re-fetched."""
import os, sys, json, time, statistics as st, urllib.request
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
FIRST = 2012
# id -> (label, group, TRI name, P/E name)
IDX = {
  "nifty50":     ("Nifty 50 (benchmark)", "bench",  "NIFTY 50", "NIFTY 50"),
  "large":       ("Large Cap (Nifty 100)", "size",  "NIFTY 100", "NIFTY 100"),
  "mid":         ("Mid Cap (Midcap 150)", "size",   "NIFTY MIDCAP 150", "NIFTY MIDCAP 150"),
  "small":       ("Small Cap (Smallcap 250)", "size","NIFTY SMALLCAP 250", "NIFTY SMLCAP 250"),
  "it":          ("IT", "sector",                  "NIFTY IT", "NIFTY IT"),
  "pharma":      ("Pharma", "sector",              "NIFTY PHARMA", "NIFTY PHARMA"),
  "finserv":     ("Financial Services", "sector",  "NIFTY FINANCIAL SERVICES", "NIFTY FIN SERVICE"),
  "bank":        ("Banks", "sector",               "NIFTY BANK", "NIFTY BANK"),
  "psubank":     ("PSU Banks", "sector",           "NIFTY PSU BANK", "NIFTY PSU BANK"),
  "fmcg":        ("FMCG", "sector",                "NIFTY FMCG", "NIFTY FMCG"),
  "consumption": ("Consumption", "sector",         "NIFTY INDIA CONSUMPTION", "NIFTY CONSUMPTION"),
  "auto":        ("Auto", "sector",                "NIFTY AUTO", "NIFTY AUTO"),
  "infra":       ("Infrastructure", "sector",      "NIFTY INFRASTRUCTURE", "NIFTY INFRA"),
  "energy":      ("Energy", "sector",              "NIFTY ENERGY", "NIFTY ENERGY"),
  "metal":       ("Metal", "sector",               "NIFTY METAL", "NIFTY METAL"),
  "realty":      ("Realty", "sector",              "NIFTY REALTY", "NIFTY REALTY"),
  "media":       ("Media", "sector",               "NIFTY MEDIA", "NIFTY MEDIA"),
  "mnc":         ("MNC", "sector",                 "NIFTY MNC", "NIFTY MNC"),
  "cpse":        ("CPSE / PSU", "sector",          "NIFTY CPSE", "NIFTY CPSE"),
  "commodities": ("Commodities", "sector",         "NIFTY COMMODITIES", "NIFTY COMMODITIES"),
  "defence":     ("Defence", "sector",             "NIFTY INDIA DEFENCE", "NIFTY IND DEFENCE"),
}

def sh(m, k):
    y, mo = map(int, m.split("-")); t = y * 12 + mo - 1 - k
    return "%d-%02d" % (t // 12, t % 12 + 1)

def fetch_pe(b, name, s, e):
    body = json.dumps({"cinfo": "{'name':'%s','startDate':'%s','endDate':'%s','indexName':'%s'}" % (
        name, s.strftime("%d-%b-%Y"), e.strftime("%d-%b-%Y"), name)}).encode()
    for k in range(3):
        try:
            req = urllib.request.Request(b.BASE + "/BackPage/getpepbHistoricaldataDBtoString", data=body, headers={
                "User-Agent": b.UA, "Content-Type": "application/json; charset=utf-8",
                "X-Requested-With": "XMLHttpRequest", "Referer": b.BASE + "/reports/historical-data"})
            j = json.loads(b._op.open(req, timeout=60).read().decode())
            out = []
            for r in j or []:
                try: out.append((datetime.strptime(r["DATE"].strip(), "%d %b %Y"), float(r["pe"])))
                except (ValueError, KeyError, TypeError): pass
            return out
        except Exception:
            time.sleep(2 + 3 * k)
            try: b._session()
            except Exception: pass
    return []

def month_last(rows):
    m = {}
    for d, v in sorted(rows):
        m[d.strftime("%Y-%m")] = v
    return m

def refresh(root, hist):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import build_index_tri as b
    b._session()
    now = datetime.now(IST)
    for iid, (_, _, tri_n, pe_n) in IDX.items():
        h = hist.setdefault(iid, {"tri": {}, "pe": {}, "done": []})
        for y in range(FIRST, now.year + 1):
            if y in h["done"]: continue
            e = datetime(y, 12, 31) if y < now.year else now
            try:
                t = month_last(b.fetch_tri(tri_n, datetime(y, 1, 1), e)); time.sleep(0.2)
                p = month_last(fetch_pe(b, pe_n, datetime(y, 1, 1), e)); time.sleep(0.2)
            except Exception as ex:
                print(f"  sector-signals: {tri_n} {y} failed ({ex})"); continue
            h["tri"].update(t); h["pe"].update(p)
            if y < now.year: h["done"].append(y)
    return hist

def signals_at(hist, iid, t):
    T, P, N = hist[iid]["tri"], hist[iid]["pe"], hist["nifty50"]["tri"]
    need = [t, sh(t, 3), sh(t, 6), sh(t, 24)]
    if not all(k in T and k in N for k in need) or t not in P: return None
    ph = [P[k] for k in P if sh(t, 120) <= k <= t]
    if len(ph) < 48: return None
    sd = st.pstdev(ph) or 1e-9
    rel = lambda a: (T[t] / T[a]) / (N[t] / N[a]) - 1
    return {"z": (P[t] - st.mean(ph)) / sd, "pe": P[t], "pe_median": st.median(ph),
            "rel3": rel(sh(t, 3)), "rel6": rel(sh(t, 6)), "rel24": rel(sh(t, 24))}

def classify(s):
    dry, cheap, turn = s["rel24"] < -0.10, s["z"] < -0.5, s["rel3"] > 0
    hot = s["rel24"] > 0.20 and s["z"] > 0.5
    if s["z"] > 2: return "EXPENSIVE — NO NEW MONEY", dry, cheap, turn
    if hot: return "AVOID / TRIM", dry, cheap, turn
    if dry and cheap and turn: return "ENTER", dry, cheap, turn
    if dry and cheap: return "WAIT FOR TURN", dry, cheap, turn
    if cheap: return "WATCH (cheap)", dry, cheap, turn
    return "NEUTRAL", dry, cheap, turn

def evidence(hist):
    """Backtest of each call bucket: forward 12M return vs Nifty 50, monthly signals."""
    N = hist["nifty50"]["tri"]; buckets = {}
    months = sorted(k for k in N if k >= "2016-01")
    for t in months:
        f = sh(t, -12)
        if f not in N: continue
        for iid in IDX:
            if iid == "nifty50": continue
            s = signals_at(hist, iid, t); T = hist[iid]["tri"]
            if not s or f not in T: continue
            call = classify(s)[0]
            buckets.setdefault(call, []).append((T[f] / T[t]) / (N[f] / N[t]) - 1)
            buckets.setdefault("ALL", []).append((T[f] / T[t]) / (N[f] / N[t]) - 1)
    return {k: {"n": len(v), "avg": round(100 * st.mean(v), 1), "median": round(100 * st.median(v), 1),
                "beat_pct": round(100 * sum(x > 0 for x in v) / len(v))} for k, v in buckets.items() if len(v) >= 5}

def run(root):
    p = os.path.join(root, "data", "history", "_sector_hist.dat")
    try: hist = json.load(open(p))
    except Exception: hist = {}
    try:
        hist = refresh(root, hist)
    except Exception as e:
        print(f"  sector-signals refresh failed ({e}) — using stored history")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as fh: json.dump(hist, fh, separators=(",", ":"))
    N = hist["nifty50"]["tri"]; t = max(N)
    out = {"v": 1, "generated_ist": datetime.now(IST).isoformat(), "as_of": t,
           "rules": {"dry": "24M return trails Nifty 50 by >10%", "cheap": "P/E z < -0.5 vs 10-yr history",
                     "turning": "3M return ahead of Nifty 50", "hot": "24M ahead >20% and P/E z > 0.5",
                     "exit": "P/E z > 2"},
           "evidence": evidence(hist), "items": []}
    for iid, (label, group, _, _) in IDX.items():
        if iid == "nifty50": continue
        s = signals_at(hist, iid, t)
        if not s:
            out["items"].append({"id": iid, "label": label, "group": group, "call": "INSUFFICIENT HISTORY"}); continue
        call, dry, cheap, turn = classify(s)
        out["items"].append({"id": iid, "label": label, "group": group, "call": call,
                             "dry": dry, "cheap": cheap, "turning": turn,
                             "pe": round(s["pe"], 1), "pe_median": round(s["pe_median"], 1), "pe_z": round(s["z"], 2),
                             "rel3": round(100 * s["rel3"], 1), "rel6": round(100 * s["rel6"], 1), "rel24": round(100 * s["rel24"], 1)})
    order = {"ENTER": 0, "WAIT FOR TURN": 1, "WATCH (cheap)": 2, "NEUTRAL": 3, "AVOID / TRIM": 4, "EXPENSIVE — NO NEW MONEY": 5, "INSUFFICIENT HISTORY": 6}
    out["items"].sort(key=lambda x: (order.get(x["call"], 9), x.get("pe_z", 0)))
    with open(os.path.join(root, "docs", "sector-signals.json"), "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print("  sector-signals: " + ", ".join(f"{i['label']}={i['call']}" for i in out["items"][:6]))
    return True

if __name__ == "__main__":
    run(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
