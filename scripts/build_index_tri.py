#!/usr/bin/env python3
"""Builds docs/index-tri.json (published) + data/history/_index_tri.dat (persisted cache,
committed by the existing "git add data/history" step; non-.json name so the NAV scripts skip it): year-end Total Return Index (TRI) levels for NSE sector /
broad indices, straight from niftyindices.com (NSE Indices Ltd). Uses NSE's back-calculated
history, so most indices go back well before their launch date.
Shape: {"v":1,"generated_ist":..,"years":[2005..],"i":{id:{"name":..,"ye":[TRI|0,..],
        "latest_date":"YYYY-MM-DD","latest":TRI,"base":"YYYY-MM-DD"}}}
Incremental: past year-ends already in the file are never re-fetched."""
import os, sys, json, time, urllib.request, http.cookiejar
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
BASE = "https://www.niftyindices.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
FIRST_YEAR = 2005

# id -> official NSE index name (niftyindices spelling)
INDICES = {
    "nifty50":     "NIFTY 50",
    "nifty100":    "NIFTY 100",
    "nifty500":    "NIFTY 500",
    "midcap150":   "NIFTY MIDCAP 150",
    "smallcap250": "NIFTY SMALLCAP 250",
    "bank":        "NIFTY BANK",
    "finserv":     "NIFTY FINANCIAL SERVICES",
    "psubank":     "NIFTY PSU BANK",
    "it":          "NIFTY IT",
    "pharma":      "NIFTY PHARMA",
    "auto":        "NIFTY AUTO",
    "fmcg":        "NIFTY FMCG",
    "consumption": "NIFTY INDIA CONSUMPTION",
    "infra":       "NIFTY INFRASTRUCTURE",
    "energy":      "NIFTY ENERGY",
    "metal":       "NIFTY METAL",
    "realty":      "NIFTY REALTY",
    "media":       "NIFTY MEDIA",
    "mnc":         "NIFTY MNC",
    "cpse":        "NIFTY CPSE",
    "commodities": "NIFTY COMMODITIES",
    "defence":     "NIFTY INDIA DEFENCE",
}

_cj = http.cookiejar.CookieJar()
_op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cj))

def _session():
    req = urllib.request.Request(BASE + "/reports/historical-data", headers={"User-Agent": UA})
    _op.open(req, timeout=60).read()

def fetch_tri(name, start, end, tries=3):
    """Daily TRI rows between two dates (range must be <= 1 year). Returns [(date, value)]."""
    cinfo = "{'name':'%s','startDate':'%s','endDate':'%s','indexName':'%s'}" % (
        name, start.strftime("%d-%b-%Y"), end.strftime("%d-%b-%Y"), name)
    body = json.dumps({"cinfo": cinfo}).encode()
    for k in range(tries):
        try:
            req = urllib.request.Request(BASE + "/BackPage/getTotalReturnIndexString", data=body, headers={
                "User-Agent": UA, "Content-Type": "application/json; charset=utf-8",
                "X-Requested-With": "XMLHttpRequest", "Referer": BASE + "/reports/historical-data"})
            raw = _op.open(req, timeout=60).read().decode("utf-8")
            j = json.loads(raw)
            if isinstance(j, dict) and "d" in j:
                j = json.loads(j["d"]) if isinstance(j["d"], str) else j["d"]
            out = []
            for r in j or []:
                v = str(r.get("TotalReturnsIndex", "")).replace(",", "").strip()
                try:
                    out.append((datetime.strptime(r["Date"].strip(), "%d %b %Y"), float(v)))
                except (ValueError, KeyError):
                    pass
            return out
        except Exception as e:
            if k == tries - 1:
                raise
            time.sleep(2 + 3 * k)
            try: _session()
            except Exception: pass
    return []

def year_end(name, y):
    """TRI on the last trading day on/before 31-Dec-y (0 if index had no value then)."""
    rows = fetch_tri(name, datetime(y, 12, 15), datetime(y, 12, 31))
    rows = [r for r in rows if r[0].year == y]
    return max(rows)[1] if rows else 0

def run(root):
    path = os.path.join(root, "data", "history", "_index_tri.dat")
    pub = os.path.join(root, "docs", "index-tri.json")
    now = datetime.now(IST)
    this_year = now.year
    years = list(range(FIRST_YEAR, this_year))
    try:
        old = json.load(open(path))
    except Exception:
        old = {"i": {}}
    _session()
    out = {}
    for iid, name in INDICES.items():
        prev = old.get("i", {}).get(iid, {})
        prev_map = dict(zip(old.get("years", []), prev.get("ye", [])))
        ye = []
        try:
            for y in years:
                v = prev_map.get(y)
                if v is None:            # never fetched (0 = fetched, index not live yet)
                    v = year_end(name, y); time.sleep(0.4)
                ye.append(v)
            rows = fetch_tri(name, now - timedelta(days=14), now)
            ld, lv = max(rows) if rows else (None, 0)
            base = next((str(y) for y, v in zip(years, ye) if v), None)
            out[iid] = {"name": name, "ye": ye, "base": base,
                        "latest_date": ld.strftime("%Y-%m-%d") if ld else prev.get("latest_date"),
                        "latest": lv or prev.get("latest", 0)}
            print(f"  {name}: from {base}, latest {out[iid]['latest']} ({out[iid]['latest_date']})")
        except Exception as e:
            print(f"  {name}: FAILED ({e}) — keeping previous", file=sys.stderr)
            if prev: out[iid] = prev
    if not out:
        raise RuntimeError("no index data fetched")
    doc = {"v": 1, "generated_ist": now.isoformat(), "source": "niftyindices.com TRI (NSE Indices Ltd)",
           "years": years, "i": out}
    for p in (path, pub):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            json.dump(doc, f, separators=(",", ":"))
    print(f"  index-tri.json written ({len(out)} indices)")
    return True

if __name__ == "__main__":
    run(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
