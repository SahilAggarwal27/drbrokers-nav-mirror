#!/usr/bin/env python3
"""Builds docs/intl-signals.json: which OVERSEAS market/theme to favour now, and which Indian
international funds give access to it (with their subscription status).

Same rule-shape as build_sector_signals.py, measured in RUPEES against Nifty 50 TRI:
  DRY     : 24M INR return trails Nifty 50 TRI by > 10%
  CHEAP   : INR price is unusually far BELOW its own 5-yr (60M) average —
            z-score of (price / 60M avg) vs its trailing 10-yr history < -0.5
            (no P/E history for overseas markets, so the "stretch vs own trend" is the value proxy)
  TURNING : 3M INR return ahead of Nifty 50 TRI
  ENTER = DRY + CHEAP + TURNING;  WAIT FOR TURN = DRY + CHEAP;  WATCH = CHEAP only
  AVOID / TRIM = 24M ahead of Nifty > 20% and z > 0.5;  EXPENSIVE = z > 2;  NEUTRAL = rest
Market data: Yahoo Finance monthly (ETF adjusted close = total return) x USD/INR.
The evidence table is recomputed on every run: next-12M INR return vs Nifty 50 TRI per call.
Subscription status lives in data/intl_status.json (edit by hand when AMCs open/close)."""
import os, re, sys, json, math, time, statistics as st, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
UA = "Mozilla/5.0"

# id -> (label, group, yahoo symbol, currency of symbol: "USD" or "HKD")
MKT = {
  "us500":   ("US — S&P 500",                "region", "^SP500TR", "USD"),
  "nasdaq":  ("US — Nasdaq 100 (Tech)",      "region", "QQQ",  "USD"),
  "usvalue": ("US — Value stocks",           "region", "IWD",  "USD"),
  "world":   ("World (developed + EM)",      "region", "ACWI", "USD"),
  "devxus":  ("Developed ex-US",             "region", "EFA",  "USD"),
  "europe":  ("Europe",                      "region", "VGK",  "USD"),
  "japan":   ("Japan",                       "region", "EWJ",  "USD"),
  "china":   ("China / Greater China",       "region", "MCHI", "USD"),
  "chtech":  ("China Internet / HS TECH",    "region", "KWEB", "USD"),
  "taiwan":  ("Taiwan",                      "region", "EWT",  "USD"),
  "korea":   ("South Korea",                 "region", "EWY",  "USD"),
  "asiaxj":  ("Asia ex-Japan",               "region", "AAXJ", "USD"),
  "em":      ("Emerging Markets",            "region", "EEM",  "USD"),
  "brazil":  ("Brazil",                      "region", "EWZ",  "USD"),
  "gtech":   ("Global Tech / Innovation",    "theme",  "IXN",  "USD"),
  "health":  ("Global Healthcare",           "theme",  "IXJ",  "USD"),
  "water":   ("Global Water",                "theme",  "PHO",  "USD"),
  "clean":   ("Global Clean Energy",         "theme",  "ICLN", "USD"),
  "goldmin": ("Gold Miners",                 "theme",  "GDX",  "USD"),
  "mining":  ("Global Metals & Mining",      "theme",  "PICK", "USD"),
  "reit":    ("Global Real Estate (REITs)",  "theme",  "RWO",  "USD"),
}
FX = "INR=X"  # INR per USD

# Indian schemes (Regular Plan Growth codes) mapped to the market they give exposure to.
# kind: "fof"/"fund" = distributor product; "etf" = exchange-traded (demat, no SIP via ARN).
FUNDS = {
  "us500":   [(148382, "fund"), (149171, "fof"), (149169, "etf"), (149290, "fof"), (148661, "fof"), (117691, "fof"),
              (148762, "fof"), (134922, "fund"), (117620, "fund"), (116633, "fof"), (149100, "fof"), (149830, "fof")],
  "nasdaq":  [(145551, "fof"), (114984, "etf"), (149438, "etf"), (149218, "fund"), (150750, "fof"), (149960, "fof"),
              (149910, "fof"), (148929, "fof"), (148927, "etf"), (148064, "fof")],
  "usvalue": [(140273, "fund")],
  "world":   [(149180, "fof"), (148486, "fof"), (132005, "fof"), (106873, "fund"), (138523, "fof"), (123651, "fof"),
              (147647, "fof"), (129187, "fof"), (148613, "fof"), (106370, "fof"), (154286, "fof")],
  "devxus":  [(152091, "fof")],
  "europe":  [(140295, "fund"), (126351, "fof")],
  "japan":   [(130863, "fund")],
  "china":   [(148701, "fof"), (140242, "fund")],
  "chtech":  [(149380, "fof"), (149379, "etf")],
  "taiwan":  [(149328, "fund")],
  "asiaxj":  [(106979, "fund")],
  "em":      [(107988, "fof"), (106441, "fof"), (138453, "fof"), (140328, "fund"), (132138, "fof")],
  "brazil":  [(115116, "fof")],
  "gtech":   [(148953, "fof"), (149817, "fof"), (149056, "fof"), (150596, "fof"), (150594, "fof")],
  "health":  [(148557, "fund")],
  "water":   [(150284, "fof")],
  "clean":   [(112126, "fof")],
  "goldmin": [(106597, "fof")],
  "mining":  [(112293, "fof"), (149456, "fof")],
  "reit":    [(149299, "fof"), (148645, "fof"), (149228, "fof")],
}

def sh(m, k):
    y, mo = map(int, m.split("-")); t = y * 12 + mo - 1 - k
    return "%d-%02d" % (t // 12, t % 12 + 1)

def yahoo_monthly(sym):
    u = ("https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(sym) +
         "?period1=946684800&period2=9999999999&interval=1mo&includeAdjustedClose=true")
    for k in range(3):
        try:
            j = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=40).read())
            r = j["chart"]["result"][0]
            ind = r["indicators"]
            px = (ind.get("adjclose") or [{}])[0].get("adjclose") or ind["quote"][0]["close"]
            out = {}
            for t, v in zip(r["timestamp"], px):
                if v is None or v <= 0: continue
                out[datetime.utcfromtimestamp(t + 86400 * 3).strftime("%Y-%m")] = float(v)
            return out
        except Exception:
            time.sleep(2 + 3 * k)
    return {}

def refresh(hist):
    fx = yahoo_monthly(FX)
    if len(fx) > 100: hist["_fx"] = fx
    for iid, (_, _, sym, _) in MKT.items():
        s = yahoo_monthly(sym); time.sleep(0.3)
        if len(s) > 24: hist[iid] = s
        else: print(f"  intl-signals: {sym} fetch failed — keeping stored history")
    return hist

def inr_series(hist, iid):
    fx, s = hist.get("_fx", {}), hist.get(iid, {})
    return {m: v * fx[m] for m, v in s.items() if m in fx}

def signals_at(T, N, t):
    need = [t, sh(t, 3), sh(t, 6), sh(t, 12), sh(t, 24)]
    if not all(k in T and k in N for k in need): return None
    dev = {}
    for k in T:
        if sh(t, 120) <= k <= t:
            w = [T[sh(k, i)] for i in range(60) if sh(k, i) in T]
            if len(w) >= 54: dev[k] = math.log(T[k] / st.mean(w))
    if t not in dev or len(dev) < 48: return None
    d = list(dev.values()); sd = st.pstdev(d) or 1e-9
    rel = lambda a: (T[t] / T[a]) / (N[t] / N[a]) - 1
    return {"z": (dev[t] - st.mean(d)) / sd, "vs_avg": math.exp(dev[t]) - 1,
            "rel3": rel(sh(t, 3)), "rel6": rel(sh(t, 6)), "rel24": rel(sh(t, 24)),
            "ret12": T[t] / T[sh(t, 12)] - 1, "ret24": T[t] / T[sh(t, 24)] - 1}

def classify(s):
    dry, cheap, turn = s["rel24"] < -0.10, s["z"] < -0.5, s["rel3"] > 0
    hot = s["rel24"] > 0.20 and s["z"] > 0.5
    if s["z"] > 2: return "EXPENSIVE — NO NEW MONEY", dry, cheap, turn
    if hot: return "AVOID / TRIM", dry, cheap, turn
    if dry and cheap and turn: return "ENTER", dry, cheap, turn
    if dry and cheap: return "WAIT FOR TURN", dry, cheap, turn
    if cheap: return "WATCH (cheap)", dry, cheap, turn
    return "NEUTRAL", dry, cheap, turn

def evidence(series, N):
    buckets = {}
    for t in sorted(k for k in N if k >= "2014-01"):
        f = sh(t, -12)
        if f not in N: continue
        for iid, T in series.items():
            s = signals_at(T, N, t)
            if not s or f not in T: continue
            x = (T[f] / T[t]) / (N[f] / N[t]) - 1
            buckets.setdefault(classify(s)[0], []).append(x)
            buckets.setdefault("ALL", []).append(x)
    return {k: {"n": len(v), "avg": round(100 * st.mean(v), 1), "median": round(100 * st.median(v), 1),
                "beat_pct": round(100 * sum(x > 0 for x in v) / len(v))} for k, v in buckets.items() if len(v) >= 5}

def cal_years(T, N, first=2013):
    """Calendar-year INR returns (Dec->Dec) + YTD, for the heat map."""
    last = max(T); out = {}
    for y in range(first, int(last[:4]) + 1):
        a, b = f"{y-1}-12", (f"{y}-12" if f"{y}-12" in T and y < int(last[:4]) else last)
        if a in T and b in T: out[str(y)] = round(100 * (T[b] / T[a] - 1), 1)
    return out

def fund_rows(root, status):
    rows = {}
    hd = os.path.join(root, "data", "history")
    for iid, lst in FUNDS.items():
        for code, kind in lst:
            p = os.path.join(hd, f"{code}.json")
            try: h = json.load(open(p))
            except Exception: continue
            pts = []
            for d, v in h.get("points", {}).items():
                try: pts.append((datetime.strptime(d, "%d-%m-%Y"), float(v)))
                except (ValueError, TypeError): pass
            if not pts: continue
            pts.sort(); ld, ln = pts[-1]
            def on_or_before(dt):
                c = [v for t, v in pts if t <= dt]
                return c[-1] if c else None
            y = ld.year
            ye = {yy: on_or_before(datetime(yy, 12, 31)) for yy in range(y - 6, y)}
            cy = {}
            for yy in range(y - 5, y):
                if ye.get(yy - 1) and ye.get(yy) and pts[0][0] <= datetime(yy - 1, 12, 31):
                    cy[str(yy)] = round(100 * (ye[yy] / ye[yy - 1] - 1), 1)
            ytd = round(100 * (ln / ye[y - 1] - 1), 1) if ye.get(y - 1) else None
            def cagr(n):
                b = ye.get(y - n)
                if not b or pts[0][0] > datetime(y - n, 12, 31): return None
                yrs = (ld - datetime(y - n, 12, 31)).days / 365.25
                return round(100 * ((ln / b) ** (1 / yrs) - 1), 1)
            st_ = status.get(str(code), {})
            rows.setdefault(iid, []).append({
                "code": code, "name": h.get("meta", {}).get("scheme_name", str(code)), "kind": kind,
                "nav": ln, "nav_date": ld.strftime("%d-%m-%Y"), "ytd": ytd, "cy": cy,
                "cagr3": cagr(3), "cagr5": cagr(5),
                "lumpsum": st_.get("lumpsum", "exchange" if kind == "etf" else "closed"),
                "sip": st_.get("sip", "n/a" if kind == "etf" else "closed"),
                "note": st_.get("note", "")})
    rank = {"open": 0, "limited": 1, "exchange": 2, "closed": 3, "suspended": 4}
    for iid in rows:
        rows[iid].sort(key=lambda r: (min(rank.get(r["lumpsum"], 5), rank.get(r["sip"], 5)), r["kind"] == "etf", r["code"]))
    return rows

# ── Fund selection: SAME rules as build_fund_picks.py (domestic sector picks) ──────────────
# Benchmark = the market's own ₹ proxy (year-end Dec closes). Regular Growth, >= 5 complete years.
#   roll3_hit (35) · roll3_edge pct (25) · downside pct (25) · year_hit (15);  PASS = roll3_hit >= 60%
# Picks = top 2 PASS funds, reviewed monthly, replaced only after 2 consecutive FAILs.
# Most intl schemes are passive FoFs that track (and so trail) their index after costs; when none
# PASS, the highest-scoring scheme is shown as "best tracker" — the role the index fund plays at home.
PICK_LOOKBACK, PICK_MIN_YEARS, PICK_PASS = 10, 5, 0.60
MIXED = {148557: "Half India healthcare — the world-healthcare benchmark is not like-for-like"}

def _pct_rank(vals):
    s = sorted(v for v in vals if v is not None)
    return [None if v is None else (sum(1 for x in s if x < v) + 0.5 * (s.count(v) - 1)) / max(1, len(s) - 1) for v in vals]

def score_funds(root, rows, series, state, month):
    hd = os.path.join(root, "data", "history"); cur_y = int(month[:4])
    years = list(range(cur_y - PICK_LOOKBACK - 1, cur_y))
    picks_out = {}
    for iid, lst in rows.items():
        T = series.get(iid) or {}
        ilv = {y: T[f"{y}-12"] for y in years if f"{y}-12" in T}
        scored = []
        for r in lst:
            if r["kind"] == "etf": continue
            try: h = json.load(open(os.path.join(hd, f"{r['code']}.json")))
            except Exception: continue
            pts = sorted((datetime.strptime(d, "%d-%m-%Y"), float(v)) for d, v in h.get("points", {}).items()
                         if re.match(r"\d\d-\d\d-\d{4}$", d))
            def ye(y):
                c = [v for t, v in pts if t.year == y and t.month == 12]
                return c[-1] if c else None
            flv = {y: ye(y) for y in years}; flv = {y: v for y, v in flv.items() if v}
            ys = [y for y in years if y in flv and y in ilv]
            ann = [(y, (flv[y] / flv[y - 1] - 1) * 100, (ilv[y] / ilv[y - 1] - 1) * 100)
                   for y in ys if y - 1 in flv and y - 1 in ilv]
            if len(ann) < PICK_MIN_YEARS: continue
            roll = [(((flv[y] / flv[y - 3]) ** (1 / 3) - 1) * 100, ((ilv[y] / ilv[y - 3]) ** (1 / 3) - 1) * 100)
                    for y in ys if y - 3 in flv and y - 3 in ilv]
            if not roll: continue
            ex = sorted(f - i for f, i in roll)
            weak = sorted(ann, key=lambda a: a[2])[:max(1, len(ann) // 3)]
            r.update({"years": len(ann),
                      "roll3_hit": round((sum(1 for f, i in roll if f > i) + 1) / (len(roll) + 2), 3),
                      "roll3_windows": len(roll), "roll3_edge": round(ex[len(ex) // 2], 2),
                      "downside": round(sum(f - i for _, f, i in weak) / len(weak), 2),
                      "year_hit": round(sum(1 for _, f, i in ann if f > i) / len(ann), 3)})
            scored.append(r)
        pe = _pct_rank([f["roll3_edge"] for f in scored]); pd = _pct_rank([f["downside"] for f in scored])
        for f, a, b in zip(scored, pe, pd):
            f["score"] = round(35 * f["roll3_hit"] + 25 * (a or 0) + 25 * (b or 0) + 15 * f["year_hit"], 1)
            f["pick_status"] = "PASS" if f["roll3_hit"] >= PICK_PASS else ("WATCH" if f["roll3_hit"] >= 0.4 else "FAIL")
            if f["code"] in MIXED: f["pick_note"] = MIXED[f["code"]]
        scored.sort(key=lambda f: -f["score"])
        byc = {f["code"]: f for f in scored}
        st = state.get(iid, {"picks": [], "strikes": {}, "month": ""})
        if st.get("month") != month:
            keep = []
            for c in st.get("picks", []):
                f = byc.get(c); ok = f is not None and f["pick_status"] == "PASS"
                st["strikes"][str(c)] = 0 if ok else st["strikes"].get(str(c), 0) + 1
                if f is not None and st["strikes"][str(c)] < 2: keep.append(c)
            for f in scored:
                if len(keep) >= 2: break
                if f["pick_status"] == "PASS" and f["code"] not in keep: keep.append(f["code"])
            st["strikes"] = {c: n for c, n in st["strikes"].items() if int(c) in keep}
            st["picks"], st["month"] = keep, month
        state[iid] = st
        picks = [byc[c] for c in st["picks"] if c in byc]
        for f in picks: f["pick"] = "PICK"
        best = None
        if not picks and scored:
            best = scored[0]; best["pick"] = "BEST TRACKER"
        open_ = lambda f: f["lumpsum"] in ("open", "limited") or f["sip"] in ("open", "limited")
        best_open = next((f for f in scored if open_(f)), None)
        picks_out[iid] = {"universe": len(scored), "passing": sum(1 for f in scored if f["pick_status"] == "PASS"),
                          "picks": [f["code"] for f in picks], "best_tracker": best and best["code"],
                          "best_open": best_open and best_open["code"]}
        lst.sort(key=lambda r: (0 if r.get("pick") else 1, -(r.get("score") or -1), r["kind"] == "etf"))
    return picks_out

def run(root):
    p = os.path.join(root, "data", "history", "_intl_hist.dat")
    try: hist = json.load(open(p))
    except Exception: hist = {}
    try: hist = refresh(hist)
    except Exception as e: print(f"  intl-signals refresh failed ({e}) — using stored history")
    with open(p, "w") as fh: json.dump(hist, fh, separators=(",", ":"))

    sec = json.load(open(os.path.join(root, "data", "history", "_sector_hist.dat")))
    N = sec["nifty50"]["tri"]
    series = {iid: inr_series(hist, iid) for iid in MKT}
    series = {k: v for k, v in series.items() if len(v) > 36}
    t = min(max(N), *(max(v) for v in series.values()))
    try: status = json.load(open(os.path.join(root, "data", "intl_status.json")))
    except Exception: status = {"as_of": "", "funds": {}}
    funds = fund_rows(root, status.get("funds", {}))
    sp = os.path.join(root, "data", "history", "_intl_picks.dat")
    try: pstate = json.load(open(sp))
    except Exception: pstate = {}
    picks = score_funds(root, funds, series, pstate, datetime.now(IST).strftime("%Y-%m"))
    with open(sp, "w") as fh: json.dump(pstate, fh, separators=(",", ":"))

    out = {"v": 1, "generated_ist": datetime.now(IST).isoformat(), "as_of": t,
           "status_as_of": status.get("as_of", ""), "status_sources": status.get("sources", []),
           "rules": {"dry": "24M INR return trails Nifty 50 TRI by >10%",
                     "cheap": "Price vs own 5-yr average unusually low (z < -0.5 vs 10-yr history)",
                     "turning": "3M INR return ahead of Nifty 50 TRI",
                     "hot": "24M ahead of Nifty >20% and z > 0.5", "exit": "z > 2"},
           "evidence": evidence(series, N),
           "nifty_cy": cal_years(N, N), "items": []}
    for iid, (label, group, sym, _) in MKT.items():
        T = series.get(iid)
        s = signals_at(T, N, t) if T else None
        it = {"id": iid, "label": label, "group": group, "proxy": sym, "funds": funds.get(iid, []),
              "selection": picks.get(iid, {"universe": 0, "passing": 0, "picks": [], "best_tracker": None, "best_open": None})}
        if not s:
            it["call"] = "INSUFFICIENT HISTORY"
        else:
            call, dry, cheap, turn = classify(s)
            it.update({"call": call, "dry": dry, "cheap": cheap, "turning": turn, "z": round(s["z"], 2),
                       "vs_avg": round(100 * s["vs_avg"], 1), "rel3": round(100 * s["rel3"], 1),
                       "rel6": round(100 * s["rel6"], 1), "rel24": round(100 * s["rel24"], 1),
                       "ret12": round(100 * s["ret12"], 1), "ret24": round(100 * s["ret24"], 1),
                       "cy": cal_years(T, N)})
        it["open_now"] = any(f["kind"] != "etf" and (f["lumpsum"] in ("open", "limited") or f["sip"] in ("open", "limited"))
                             for f in it["funds"])
        it["etf_route"] = any(f["kind"] == "etf" for f in it["funds"])
        out["items"].append(it)
    order = {"ENTER": 0, "WAIT FOR TURN": 1, "WATCH (cheap)": 2, "NEUTRAL": 3, "AVOID / TRIM": 4,
             "EXPENSIVE — NO NEW MONEY": 5, "INSUFFICIENT HISTORY": 6}
    out["items"].sort(key=lambda x: (order.get(x["call"], 9), x.get("z", 0)))
    with open(os.path.join(root, "docs", "intl-signals.json"), "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    tpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), "intl_tracker.html")
    if os.path.exists(tpl):
        with open(tpl) as a, open(os.path.join(root, "docs", "intl-tracker.html"), "w") as b: b.write(a.read())
    print("  intl-signals: " + ", ".join(f"{i['label']}={i['call']}" for i in out["items"]))
    return True

if __name__ == "__main__":
    run(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
