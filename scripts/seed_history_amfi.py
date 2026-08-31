#!/usr/bin/env python3
"""
Build FULL NAV history from AMFI's own historical report — NO mfapi dependency.

AMFI endpoint (undocumented but stable):
  https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx?frmdt=DD-Mon-YYYY&todt=DD-Mon-YYYY
Returns every scheme's NAV for the date range, 8-field ';'-delimited:
  Scheme Code;NAV Name;Plan;Option;ISIN1;ISIN2;NAV;Date

The Sector Cycle tool only needs YEAR-END NAVs (2007..last complete year) + latest,
so we pull a short window around each Dec 31 (last ~5 days, to skip holidays) plus a
recent window for the newest point. ~21 requests total, not daily.

Writes per-scheme history into data/history/<code>.json and mfapi-shaped public files
into docs/mf/<code>.json (newest-first), identical to build_nav.py's output, so the
mirror is complete on first run and stays mfapi-independent forever.

Run once to bootstrap; build_nav.py's daily AMFI pull keeps it current thereafter.
"""
import os, sys, json, time, io, urllib.request
from datetime import datetime, timezone, timedelta

HIST_URL = "https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx?frmdt={f}&todt={t}"
ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST_DIR = os.path.join(ROOT, "data", "history")
OUT_DIR  = os.path.join(ROOT, "docs", "mf")
IST      = timezone(timedelta(hours=5, minutes=30))
os.makedirs(HIST_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

def fetch_range(frm, to, retries=4):
    url = HIST_URL.format(f=frm, t=to)
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:
            last = e; time.sleep(2*(i+1))
    print(f"  WARN: range {frm}..{to} failed: {last}", file=sys.stderr)
    return ""

def parse_hist(text):
    """Yield (code:int, name:str, nav:str, date_ddmmyyyy:str). Keeps only the LAST
    trading day per (code) within the window by letting later dates overwrite."""
    for line in text.splitlines():
        line = line.strip().rstrip("\r")
        if not line or ";" not in line: continue
        p = [x.strip() for x in line.split(";")]
        if len(p) < 8: continue
        code = p[0]
        if not code.isdigit(): continue
        name, nav, date = p[1], p[-2], p[-1]
        if not nav: continue
        try: float(nav)
        except ValueError: continue
        # normalize date DD-Mon-YYYY -> DD-MM-YYYY
        try:
            d = datetime.strptime(date, "%d-%b-%Y").strftime("%d-%m-%Y")
        except ValueError:
            continue
        yield int(code), name, nav, d

def load_json(path, default):
    if os.path.exists(path):
        try: return json.load(open(path))
        except Exception: return default
    return default

def main():
    cur = datetime.now(IST).year
    # Year-end windows 2007..(cur-1): pull Dec 24..31 to dodge holidays; keep latest date per fund.
    windows = []
    for y in range(2007, cur):
        windows.append((f"24-Dec-{y}", f"31-Dec-{y}"))
    # Recent window for the newest point (last ~10 days)
    today = datetime.now(IST)
    ago = today - timedelta(days=12)
    windows.append((ago.strftime(f"%d-%b-%Y"), today.strftime("%d-%b-%Y")))

    print(f"Pulling {len(windows)} AMFI history windows (2007..{cur})…")
    hist = {}  # code -> {name, points:{date:nav}}
    for (frm, to) in windows:
        txt = fetch_range(frm, to)
        if not txt:
            continue
        # within a window, keep the chronologically latest date per code
        latest_in_win = {}  # code -> (date_obj, date_str, nav, name)
        for code, name, nav, d in parse_hist(txt):
            do = datetime.strptime(d, "%d-%m-%Y")
            prev = latest_in_win.get(code)
            if prev is None or do > prev[0]:
                latest_in_win[code] = (do, d, nav, name)
        for code, (do, d, nav, name) in latest_in_win.items():
            h = hist.setdefault(code, {"name": name, "points": {}})
            h["name"] = name or h["name"]
            h["points"][d] = nav
        print(f"  {frm}..{to}: {len(latest_in_win)} schemes")
        time.sleep(0.4)

    # Merge with any existing history, then write outputs
    written = 0
    for code, h in hist.items():
        scode = str(code)
        hp = os.path.join(HIST_DIR, f"{scode}.json")
        cur_h = load_json(hp, {"meta": {"scheme_code": code}, "points": {}})
        cur_h.setdefault("meta", {})["scheme_code"] = code
        cur_h["meta"]["scheme_name"] = h["name"]
        cur_h.setdefault("points", {}).update(h["points"])
        json.dump(cur_h, open(hp, "w"), separators=(",", ":"))

        pts = sorted(cur_h["points"].items(),
                     key=lambda kv: datetime.strptime(kv[0], "%d-%m-%Y"), reverse=True)
        out = {"meta": {"scheme_code": code, "scheme_name": h["name"]},
               "data": [{"date": k, "nav": v} for k, v in pts], "status": "SUCCESS"}
        json.dump(out, open(os.path.join(OUT_DIR, f"{scode}.json"), "w"), separators=(",", ":"))
        written += 1

    print(f"\nWrote {written} schemes with year-end history to docs/mf/")
    print("mfapi is no longer required for history — AMFI serves it directly.")

if __name__ == "__main__":
    main()
