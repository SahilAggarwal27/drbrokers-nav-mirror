#!/usr/bin/env python3
"""Builds docs/fund-combo.json: an automated 2-fund combo per category (REGULAR Growth only).
Backtest (2014-26, 188 funds): fund leadership flips with the market - aggressive / recent
winners lead in rising years, defensive / low-downside funds lead in falling years. So each
category holds ONE of each, 50:50:
  AGGRESSIVE : best 12M return among funds with >=60% consistency (rolling 12M beat category
               median in last 24 months) and downside capture < 110% vs category average.
  DEFENSIVE  : lowest downside capture (36M, vs category average) among funds whose 3Y CAGR
               is at least the category median.
  Slump rule : a fund >= 8% behind its category (relative line vs 36M high) gets no new money.
  Stability  : reviewed once a month; a current pick is replaced only after failing its
               slot's test at 2 consecutive monthly reviews.
Monthly NAVs come from api.mfapi.in (full daily history); on any fetch failure the last good
fund-combo.json is kept. State: data/history/_combo.dat."""
import os, re, json, math, statistics as st, urllib.request
import concurrent.futures as cf
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
AMFI_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
CATS = {  # id -> (label, AMFI category regex)
    "large":    ("Large Cap",        r"(?<!& )large cap fund"),
    "largemid": ("Large & Mid Cap",  r"large & mid cap fund"),
    "mid":      ("Mid Cap",          r"(?<!large & )mid cap fund"),
    "small":    ("Small Cap",        r"small cap fund"),
    "flexi":    ("Flexi Cap",        r"flexi cap fund"),
    "multi":    ("Multi Cap",        r"multi cap fund"),
    "elss":     ("ELSS",             r"elss"),
    "focused":  ("Focused",          r"focused fund"),
    "value":    ("Value / Contra",   r"value fund|contra fund"),
}
BAD = re.compile(r"direct|idcw|dividend|bonus|payout|reinvest|segregated|unclaimed", re.I)
SLUMP = 0.08

def sh(m, k):
    t = m[0] * 12 + m[1] - 1 - k
    return (t // 12, t % 12 + 1)

def amfi_universe():
    req = urllib.request.Request(AMFI_URL, headers={"User-Agent": "drbrokers-nav-mirror/1.0"})
    txt = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    cat, out = "", {}
    for line in txt.splitlines():
        line = line.strip()
        if line.startswith("Open Ended"):
            cat = line.lower(); continue
        p = [x.strip() for x in line.split(";")]
        if len(p) < 6 or not p[0].isdigit() or "equity" not in cat: continue
        name = " ".join(x for x in p[3:-2] if x and x != "-") or p[3]
        if BAD.search(name) or "growth" not in name.lower(): continue
        for cid, (_, pat) in CATS.items():
            if re.search(pat, cat):
                out[p[0]] = (cid, name); break
    return out

def monthly(code):
    for _ in range(3):
        try:
            j = json.loads(urllib.request.urlopen(f"https://api.mfapi.in/mf/{code}", timeout=60).read())
            m = {}
            for x in j.get("data", []):
                v = float(x["nav"])
                if v <= 0: continue
                d = datetime.strptime(x["date"], "%d-%m-%Y"); k = (d.year, d.month)
                if k not in m or d > m[k][0]: m[k] = (d, v)
            return code, {k: v for k, (_, v) in m.items()}
        except Exception:
            pass
    return code, None

def run(root):
    docs = os.path.join(root, "docs")
    out_p = os.path.join(docs, "fund-combo.json")
    state_p = os.path.join(root, "data", "history", "_combo.dat")
    now = datetime.now(IST); month = now.strftime("%Y-%m")
    try: state = json.load(open(state_p))
    except Exception: state = {}
    if state.get("_month") == month and state.get("_doc"):
        with open(out_p, "w") as fh: json.dump(state["_doc"], fh, separators=(",", ":"))
        print("  fund-combo: already reviewed this month — republished"); return True
    try:
        return _review(root, state, state_p, out_p, now, month)
    except Exception as e:
        if state.get("_doc"):
            with open(out_p, "w") as fh: json.dump(state["_doc"], fh, separators=(",", ":"))
            print(f"  fund-combo: review failed ({e}) — republished last good combo")
            return False
        raise

def _review(root, state, state_p, out_p, now, month):
    uni = amfi_universe()
    with cf.ThreadPoolExecutor(12) as ex:
        S = {c: s for c, s in ex.map(monthly, list(uni)) if s}
    t = sh((now.year, now.month), 1)                       # last complete month-end
    if sum(1 for s in S.values() if t in s) < 0.8 * len(S):
        t = sh(t, 1)
    mret = lambda c, m: (S[c][m] / S[c][sh(m, 1)] - 1) if m in S[c] and sh(m, 1) in S[c] else None
    pret = lambda c, a, b: (S[c][b] / S[c][a] - 1) if a in S[c] and b in S[c] else None

    doc = {"v": 1, "generated_ist": now.isoformat(), "as_of": "%d-%02d" % t, "plan": "Regular Growth",
           "split": "50:50 (tilt 40:60 to defensive in a weak market)", "categories": {}}
    for cid, (label, _) in CATS.items():
        fs = [c for c in S if uni[c][0] == cid and t in S[c] and sh(t, 36) in S[c]]
        if len(fs) < 6: continue
        catm = {}
        for k in range(36):
            m = sh(t, k); rs = [r for r in (mret(c, m) for c in fs) if r is not None]
            catm[m] = st.mean(rs) if rs else 0
        cat12 = {}
        for k in range(24):
            m = sh(t, k); rs = [r for r in (pret(c, sh(m, 12), m) for c in fs) if r is not None]
            cat12[m] = st.median(rs) if rs else None
        rows = {}
        for c in fs:
            mr = [(mret(c, sh(t, k)), catm[sh(t, k)]) for k in range(36)]
            mr = [(f, b) for f, b in mr if f is not None]
            if len(mr) < 30: continue
            dn = [(f, b) for f, b in mr if b < 0]
            dcap = st.mean(f for f, _ in dn) / st.mean(b for _, b in dn) if dn else 1.0
            cons = sum(1 for k in range(24) if cat12.get(sh(t, k)) is not None
                       and (pret(c, sh(sh(t, k), 12), sh(t, k)) or -9) > cat12[sh(t, k)]) / 24
            rel = hi = 1.0
            for k in range(35, -1, -1):
                f = mret(c, sh(t, k))
                if f is None: continue
                rel *= (1 + f) / (1 + catm[sh(t, k)]); hi = max(hi, rel)
            fr = [f for f, _ in mr]
            ann = math.prod(1 + x for x in fr) ** (12 / len(fr)) - 1
            dd = math.sqrt(sum(min(0, x - 0.065 / 12) ** 2 for x in fr) / len(fr)) * math.sqrt(12) or 1e-9
            rows[c] = {"code": c, "name": uni[c][1], "ret1y": pret(c, sh(t, 12), t) * 100,
                       "cagr3y": ((1 + pret(c, sh(t, 36), t)) ** (1 / 3) - 1) * 100,
                       "downside_capture": dcap * 100, "consistency": cons * 100,
                       "slump": (1 - rel / hi) * 100, "sortino": (ann - 0.065) / dd,
                       "history_yrs": round(len(S[c]) / 12, 1)}
        med3 = st.median(r["cagr3y"] for r in rows.values())
        ok_agg = lambda r: r["consistency"] >= 60 and r["downside_capture"] < 110 and r["slump"] < SLUMP * 100
        ok_def = lambda r: r["cagr3y"] >= med3 and r["slump"] < SLUMP * 100
        agg = sorted([r for r in rows.values() if ok_agg(r)], key=lambda r: -r["ret1y"])
        dfn = sorted([r for r in rows.values() if ok_def(r)], key=lambda r: r["downside_capture"])

        cs = state.get(cid, {})
        def keep(slot, ranked, test):
            cur = cs.get(slot, {}); code = cur.get("code"); strikes = cur.get("strikes", 0)
            if code in rows:
                strikes = 0 if test(rows[code]) else strikes + 1
                if strikes < 2: return {"code": code, "strikes": strikes}
            for r in ranked:
                if r["code"] not in other: return {"code": r["code"], "strikes": 0}
            return {"code": None, "strikes": 0}
        other = set()
        a = keep("aggressive", agg, ok_agg); other = {a["code"]}
        d = keep("defensive", dfn, ok_def)
        state[cid] = {"aggressive": a, "defensive": d}
        fmt = lambda r: {k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()}
        doc["categories"][cid] = {
            "label": label, "funds_scored": len(rows), "median_cagr3y": round(med3, 2),
            "aggressive": fmt(rows[a["code"]]) if a["code"] in rows else None,
            "defensive": fmt(rows[d["code"]]) if d["code"] in rows else None,
            "slumping": [fmt(r) for r in rows.values() if r["slump"] >= SLUMP * 100 and r["consistency"] >= 50][:5],
            "runners_up": {"aggressive": [fmt(r) for r in agg[:4] if r["code"] not in (a["code"], d["code"])][:2],
                           "defensive": [fmt(r) for r in dfn[:4] if r["code"] not in (a["code"], d["code"])][:2]},
        }
        print(f"  combo {label}: AGG {doc['categories'][cid]['aggressive'] and doc['categories'][cid]['aggressive']['name'][:32]}"
              f" | DEF {doc['categories'][cid]['defensive'] and doc['categories'][cid]['defensive']['name'][:32]}")
    if not doc["categories"]:
        raise RuntimeError("no categories scored — keeping previous combo")
    state["_month"], state["_doc"] = month, doc
    with open(out_p, "w") as fh: json.dump(doc, fh, separators=(",", ":"))
    os.makedirs(os.path.dirname(state_p), exist_ok=True)
    with open(state_p, "w") as fh: json.dump(state, fh, separators=(",", ":"))
    return True

if __name__ == "__main__":
    run(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
