#!/usr/bin/env python3
"""Builds docs/dash-navs.json for the MF Returns Dashboard: for every Regular-Growth scheme
in the InertExpert2911 master, its NAV (last trading day on-or-before) at latest, -1M, -3M,
-6M, YTD (2-Jan), -1Y..-10Y — the exact targets the dashboard computes.
Source: AMFI's own historical NAV report, one short window per target date (~15 requests),
so the browser makes ONE request instead of ~1,300 mfapi calls. If AMFI fails, the
previously published file is reused so the dashboard never goes blank."""
import csv, io, json, os, re, sys, time, urllib.request
from datetime import date, timedelta, datetime, timezone

MASTER_URL = "https://raw.githubusercontent.com/InertExpert2911/Mutual_Fund_Data/main/mutual_fund_data.csv"
AMFI_HIST = "https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx?frmdt={f}&todt={t}"
PUBLISHED = "https://sahilaggarwal27.github.io/drbrokers-nav-mirror/dash-navs.json"
IST = timezone(timedelta(hours=5, minutes=30))
WINDOW_DAYS = 8  # look-back per target to skip weekends/holidays


def get(url, timeout=120, retries=4):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last = e; time.sleep(2 * (i + 1))
    raise RuntimeError(f"fetch failed {url}: {last}")


def is_regular_growth(n):
    ln = (n or "").lower()
    if "growth" not in ln: return False
    if re.search(r"\bdirect\b", ln): return False
    if re.search(r"dividend|idcw|payout|reinvestment|bonus", ln): return False
    return True


def js_add_months(d, n):
    """JS Date.setMonth(getMonth()+n) incl. day overflow (31-Mar -1M -> 3-Mar)."""
    m0 = d.month - 1 + n
    y, m = d.year + m0 // 12, m0 % 12 + 1
    return date(y, m, 1) + timedelta(days=d.day - 1)


def window_navs(t, want):
    """{code: (date, nav)} = last NAV on-or-before t within WINDOW_DAYS, codes in `want`."""
    f = (t - timedelta(days=WINDOW_DAYS)).strftime("%d-%b-%Y")
    txt = get(AMFI_HIST.format(f=f, t=t.strftime("%d-%b-%Y"))).decode("utf-8", "replace")
    out = {}
    for line in txt.splitlines():
        p = [x.strip() for x in line.split(";")]
        if len(p) < 8 or p[0] not in want: continue
        try:
            v = float(p[-2]); d = datetime.strptime(p[-1], "%d-%b-%Y").date()
        except ValueError:
            continue
        if v <= 0 or d > t: continue
        if p[0] not in out or d > out[p[0]][0]:
            out[p[0]] = (d, v)
    return out


def run(root):
    out_path = os.path.join(root, "docs", "dash-navs.json")
    try:
        rows = list(csv.reader(io.StringIO(get(MASTER_URL).decode("utf-8", "replace"))))
        h = rows[0]; ic, inv = h.index("Scheme_Code"), h.index("Scheme_NAV_Name")
        want = {r[ic] for r in rows[1:] if len(r) > max(ic, inv) and r[ic] and is_regular_growth(r[inv])}
        today = datetime.now(IST).date()
        cur = window_navs(today, want)
        if len(cur) < 500:
            raise RuntimeError(f"only {len(cur)} current NAVs from AMFI")
        latest = max(d for d, _ in cur.values())
        keys = ["latest", "m1", "m3", "m6", "ytd"] + [f"y{i}" for i in range(1, 11)]
        tdates = [latest, js_add_months(latest, -1), js_add_months(latest, -3), js_add_months(latest, -6),
                  date(latest.year, 1, 2)] + [js_add_months(latest, -12 * i) for i in range(1, 11)]
        snaps = [cur] + [window_navs(t, want) for t in tdates[1:]]
        f = {}
        for c, (d, v) in cur.items():
            if (latest - d).days > WINDOW_DAYS: continue
            f[c] = [float(f"{s[c][1]:.6g}") if c in s else 0 for s in snaps]
        out = {"v": 1, "generated_ist": datetime.now(IST).isoformat(), "keys": keys,
               "dates": [t.strftime("%d-%m-%Y") for t in tdates], "f": f}
        with open(out_path, "w") as fh:
            json.dump(out, fh, separators=(",", ":"))
        print(f"  dash-navs.json: {len(f)} funds, latest {latest}")
    except Exception as e:
        print(f"  dash-navs build failed ({e}); reusing published copy", file=sys.stderr)
        try:
            with open(out_path, "wb") as fh:
                fh.write(get(PUBLISHED, retries=2))
        except Exception as e2:
            print(f"  no published copy to reuse: {e2}", file=sys.stderr)


if __name__ == "__main__":
    run(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
