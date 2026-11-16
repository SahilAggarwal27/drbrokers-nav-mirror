#!/usr/bin/env python3
"""Builds docs/sector-daily.json: DAILY NSE Total Return Index (TRI) levels for the size
segments + sectoral indices used by the Sector Signal tab (same list as build_sector_signals.IDX),
straight from niftyindices.com. Feeds the "📅 Custom Range" tab, which ranks every sector by
return between ANY two dates (or a month / a year) vs Nifty 50.
Cache: data/history/_sector_daily.dat = {iid: {"d": {"YYYY-MM-DD": tri}, "done": [years]}}
(committed by the workflow's "git add data/history"). Past years are fetched once; only the
current year is re-pulled each run. First run back-fills 2012→now (time-boxed, resumes next run).
Published shape: {"v":1,"generated_ist":..,"as_of":"YYYY-MM-DD","dates":[..],
                  "i":{iid:{"label":..,"group":"bench|size|sector","v":[tri|null,..]}}}"""
import os, sys, json, time
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
FIRST = 2012
BUDGET_SEC = 25 * 60   # cap the one-time back-fill per run; it resumes on the next run


def run(root):
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    import build_index_tri as b
    from build_sector_signals import IDX

    path = os.path.join(root, "data", "history", "_sector_daily.dat")
    pub = os.path.join(root, "docs", "sector-daily.json")
    try:
        H = json.load(open(path))
    except Exception:
        H = {}
    now = datetime.now(IST).replace(tzinfo=None)
    stop_at = time.time() + BUDGET_SEC
    try:
        b._session()
    except Exception as e:
        print(f"  sector-daily: session failed ({e})")

    for iid, (label, group, tri_n, _) in IDX.items():
        h = H.setdefault(iid, {"d": {}, "done": []})
        for y in range(FIRST, now.year + 1):
            if y in h["done"]:
                continue
            if time.time() > stop_at:
                break
            end = datetime(y, 12, 31) if y < now.year else now
            try:
                rows = b.fetch_tri(tri_n, datetime(y, 1, 1), end)
                time.sleep(0.2)
            except Exception as ex:
                print(f"  sector-daily: {tri_n} {y} failed ({ex})")
                continue
            for d, v in rows:
                if v > 0:
                    h["d"][d.strftime("%Y-%m-%d")] = round(v, 2)
            if y < now.year:
                h["done"].append(y)   # empty = index not live that year; don't re-ask

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(H, f, separators=(",", ":"))

    N = (H.get("nifty50") or {}).get("d") or {}
    if not N:
        print("  sector-daily: no Nifty 50 data yet — not published")
        return False
    dates = sorted(N)
    out = {"v": 1, "generated_ist": datetime.now(IST).isoformat(),
           "source": "niftyindices.com TRI (NSE Indices Ltd)",
           "as_of": dates[-1], "dates": dates, "i": {}}
    for iid, (label, group, _, _) in IDX.items():
        d = (H.get(iid) or {}).get("d") or {}
        if not d:
            continue
        out["i"][iid] = {"label": label, "group": group, "v": [d.get(x) for x in dates]}
    with open(pub, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"  sector-daily.json written ({len(out['i'])} indices, {dates[0]} → {dates[-1]})")
    return True


if __name__ == "__main__":
    run(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
