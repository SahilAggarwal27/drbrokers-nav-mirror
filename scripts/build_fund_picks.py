#!/usr/bin/env python3
"""Builds docs/fund-picks.json: automated fund selection per sector (REGULAR Growth plans only).
Each fund is judged against its own sector's NSE TRI (index-tri.json), on consistency, not
recent rank:
  eligibility : Regular Growth plan, >= 5 complete calendar years of NAV history
  roll3_hit   : % of rolling 3Y windows (year-end to year-end) beating the index, shrunk (35)
  roll3_edge  : median rolling-3Y CAGR excess over the index (percentile within sector)      (25)
  downside    : avg excess in the index's weakest third of years (percentile within sector)   (25)
  year_hit    : % of calendar years beating the index                                        (15)
  PASS = roll3_hit >= 60%.  Picks = top 2 PASS funds; none pass -> the sector's index fund.
Stability: reviewed once a month; a current pick is only replaced after it FAILS the bar at
2 consecutive monthly reviews (state kept in data/history/_fund_picks.dat).
Recent returns (1Y / YTD) are shown for context but never used for selection."""
import os, re, json, urllib.request
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
AMFI_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
LOOKBACK = 10          # complete calendar years scored
MIN_YEARS = 5
PASS_HIT = 0.60

# sector id -> (index id, category test, name regex for sectoral/thematic, index-fund name regex)
SECTORS = {
  "smallcap": ("smallcap250", r"small cap fund", None, r"small ?cap 250"),
  "midcap":   ("midcap150",   r"(?<!large & )mid cap fund", None, r"mid ?cap 150"),
  "largecap": ("nifty100",    r"(?<!& )large cap fund", None, r"nifty 100 index|nifty 50 index"),
  "flexicap": ("nifty500",    r"flexi cap fund|multi cap fund", None, r"nifty 500 index"),
  "pharma":   ("pharma",      "SECT", r"pharma|health", r"nifty pharma|healthcare index"),
  "tech":     ("it",          "SECT", r"technolog|digital|\bit\b", r"nifty it index"),
  "auto":     ("auto",        "SECT", r"\bauto|transport|mobility", r"nifty auto index"),
  "banking":  ("finserv",     "SECT", r"banking|financial serv|bfsi|bank fund|financials", r"nifty bank index|financial services index"),
  "fmcg":     ("fmcg",        "SECT", r"fmcg|consum|bharat consum", r"nifty fmcg index|consumption index"),
  "infra":    ("infra",       "SECT", r"infra", r"infrastructure index"),
  "energy":   ("energy",      "SECT", r"energy|power|natural resource", r"nifty energy index"),
  "defense":  ("defence",     "SECT", r"defen", r"defence index"),
  "mnc":      ("mnc",         "SECT", r"\bmnc\b", r"nifty mnc index"),
}
BAD = re.compile(r"direct|idcw|dividend|bonus|payout|reinvest|segregated|unclaimed", re.I)

def amfi_categories():
    req = urllib.request.Request(AMFI_URL, headers={"User-Agent": "drbrokers-nav-mirror/1.0"})
    txt = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    cat, out = "", {}
    for line in txt.splitlines():
        line = line.strip()
        if line.startswith("Open Ended Schemes") or line.startswith("Close Ended") or line.startswith("Interval Fund"):
            cat = line.lower(); continue
        p = line.split(";")
        if len(p) >= 6 and p[0].strip().isdigit():
            out[p[0].strip()] = cat
    return out

def cagr(a, b, n): return ((b / a) ** (1.0 / n) - 1) * 100

def pct_rank(vals):
    s = sorted(v for v in vals if v is not None)
    return [None if v is None else (sum(1 for x in s if x < v) + 0.5 * (s.count(v) - 1)) / max(1, len(s) - 1) for v in vals]

def run(root):
    docs = os.path.join(root, "docs")
    snap = json.load(open(os.path.join(docs, "snapshots.json")))
    tri = json.load(open(os.path.join(docs, "index-tri.json")))
    cats = amfi_categories()
    now = datetime.now(IST); cur_y = now.year; month = now.strftime("%Y-%m")
    years = [y for y in range(cur_y - LOOKBACK - 1, cur_y)]          # year-ends used (first = base)
    sy = snap["years"]
    state_p = os.path.join(root, "data", "history", "_fund_picks.dat")
    try: state = json.load(open(state_p))
    except Exception: state = {}

    out = {"v": 1, "generated_ist": now.isoformat(), "plan": "Regular Growth", "pass_hit": PASS_HIT,
           "lookback_years": LOOKBACK, "sectors": {}}
    for sid, (iid, catpat, namepat, idxpat) in SECTORS.items():
        ix = tri["i"].get(iid)
        if not ix: continue
        ilv = {y: v for y, v in zip(tri["years"], ix["ye"]) if v}
        funds, idx_funds = [], []
        for code, (name, ld, lnav, ye) in snap["f"].items():
            nm = name or ""; low = nm.lower(); cat = cats.get(code, "")
            if not cat or BAD.search(nm) or "growth" not in low: continue
            if "index fund" in cat or "etf" in cat:
                if idxpat and re.search(idxpat, low): idx_funds.append((code, nm, ye))
                continue
            if "equity" not in cat: continue
            if catpat == "SECT":
                if not ("sectoral" in cat or "thematic" in cat) or not re.search(namepat, low): continue
            elif not re.search(catpat, cat): continue
            flv = {y: v for y, v in zip(sy, ye) if v}
            ys = [y for y in years if y in flv and y in ilv]
            ann = [(y, (flv[y] / flv[y - 1] - 1) * 100, (ilv[y] / ilv[y - 1] - 1) * 100)
                   for y in ys if y - 1 in flv and y - 1 in ilv]
            if len(ann) < MIN_YEARS: continue
            roll = [(cagr(flv[y - 3], flv[y], 3), cagr(ilv[y - 3], ilv[y], 3))
                    for y in ys if y - 3 in flv and y - 3 in ilv]
            if not roll: continue
            ex = sorted(f - i for f, i in roll)
            weak = sorted(ann, key=lambda a: a[2])[:max(1, len(ann) // 3)]
            ytd = (lnav / flv[cur_y - 1] - 1) * 100 if flv.get(cur_y - 1) else None
            iytd = (ix["latest"] / ilv[cur_y - 1] - 1) * 100 if ilv.get(cur_y - 1) else None
            funds.append({"code": code, "name": nm, "years": len(ann),
                          # Laplace-shrunk so a young fund with 3/3 windows doesn't outrank a 9/10 veteran
                          "roll3_hit": (sum(1 for f, i in roll if f > i) + 1) / (len(roll) + 2),
                          "roll3_windows": len(roll),
                          "roll3_edge": ex[len(ex) // 2],
                          "downside": sum(f - i for _, f, i in weak) / len(weak),
                          "year_hit": sum(1 for _, f, i in ann if f > i) / len(ann),
                          "ytd": ytd, "ytd_vs_index": (ytd - iytd) if ytd is not None and iytd is not None else None})
        pe = pct_rank([f["roll3_edge"] for f in funds]); pd = pct_rank([f["downside"] for f in funds])
        for f, a, b in zip(funds, pe, pd):
            f["score"] = round(35 * f["roll3_hit"] + 25 * (a or 0) + 25 * (b or 0) + 15 * f["year_hit"], 1)
            f["status"] = "PASS" if f["roll3_hit"] >= PASS_HIT else ("WATCH" if f["roll3_hit"] >= 0.4 else "FAIL")
        funds.sort(key=lambda f: -f["score"])
        byc = {f["code"]: f for f in funds}

        # ── stability: monthly review, replace a pick only after 2 consecutive FAILs ──
        st = state.get(sid, {"picks": [], "strikes": {}, "month": ""})
        if st.get("month") != month:
            keep = []
            for c in st.get("picks", []):
                f = byc.get(c)
                ok = f is not None and f["status"] == "PASS"
                st["strikes"][c] = 0 if ok else st["strikes"].get(c, 0) + 1
                if f is not None and st["strikes"][c] < 2: keep.append(c)
            for f in funds:
                if len(keep) >= 2: break
                if f["status"] == "PASS" and f["code"] not in keep: keep.append(f["code"])
            st["strikes"] = {c: n for c, n in st["strikes"].items() if c in keep}
            st["picks"], st["month"] = keep, month
        state[sid] = st
        picks = [byc[c] for c in st["picks"] if c in byc]
        idx_pick = None
        if idx_funds:
            c, nm, ye = max(idx_funds, key=lambda t: sum(1 for v in t[2] if v))
            idx_pick = {"code": c, "name": nm}
        out["sectors"][sid] = {
            "index": ix["name"], "universe": len(funds),
            "passing": sum(1 for f in funds if f["status"] == "PASS"),
            "picks": [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in f.items()} for f in picks],
            "fallback_index_fund": idx_pick if not picks else None,
            "candidates": [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in f.items()} for f in funds[:10]],
        }
        print(f"  picks {sid}: {len(funds)} funds, {out['sectors'][sid]['passing']} pass -> "
              + (", ".join(p['name'][:30] for p in picks) or f"index fund: {idx_pick and idx_pick['name'][:40]}"))
    with open(os.path.join(docs, "fund-picks.json"), "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    os.makedirs(os.path.dirname(state_p), exist_ok=True)
    with open(state_p, "w") as fh:
        json.dump(state, fh, separators=(",", ":"))
    return True

if __name__ == "__main__":
    run(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
