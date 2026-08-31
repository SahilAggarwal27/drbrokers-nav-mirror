#!/usr/bin/env python3
"""
DR Brokers NAV mirror builder.

Pulls the AMFI daily NAV snapshot (NAVAll.txt) and appends today's NAV to a
persistent per-scheme history, then writes per-scheme JSON files in the EXACT
shape mfapi.in returns, so client tools only need to swap the base URL.

Output shape per scheme (docs/mf/<code>.json):
  { "meta": { "scheme_code": <int>, "scheme_name": "<str>", ... },
    "data": [ { "date": "DD-MM-YYYY", "nav": "123.4560" }, ... ] }   # newest-first

History is persisted in data/history/<code>.json (committed by the workflow).
For a full 20-year archive, commit a prebuilt data/history-seed.tar.gz (a gzipped
tar of a history/ dir); the build MERGES it into existing history on the next run.

Design notes:
- AMFI NAVAll.txt has NO history — only "today". History comes from the seed
  tarball; the daily build keeps it current.
- Everything is deterministic and idempotent: re-running merges points, never
  duplicates or loses data.
"""

import os, sys, json, time, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

AMFI_URL   = "https://portal.amfiindia.com/spages/NAVAll.txt"  # moved from www.amfiindia.com (301)
ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST_DIR   = os.path.join(ROOT, "data", "history")
SEED_DIR   = os.path.join(ROOT, "data", "seed")
OUT_DIR    = os.path.join(ROOT, "docs", "mf")
META_DIR   = os.path.join(ROOT, "data", "meta")
IST        = timezone(timedelta(hours=5, minutes=30))

os.makedirs(HIST_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(META_DIR, exist_ok=True)


def fetch_amfi(retries=4):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(AMFI_URL, headers={"User-Agent": "drbrokers-nav-mirror/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"AMFI fetch failed after {retries} tries: {last}")


def parse_amfi(text):
    """
    NAVAll.txt is semicolon-delimited, grouped by AMC/scheme-type with blank
    lines and header rows. Real data rows have EIGHT fields, and the scheme name
    itself spans three of them (Name;Plan;Option):
      Code;ISIN_Payout;ISIN_Reinvest;Scheme Name;Plan;Option;NAV;Date
    So: nav = fields[-2], date = fields[-1], name = " ".join(fields[3:-2]).
    Returns {code:int -> {"name":str,"nav":str,"date":"DD-Mon-YYYY"}}
    """
    out = {}
    for line in text.splitlines():
        line = line.strip().rstrip("\r")
        if not line or ";" not in line:
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 6:
            continue
        code = parts[0]
        if not code.isdigit():
            continue
        nav  = parts[-2]
        date = parts[-1]
        name = " ".join(p for p in parts[3:-2] if p and p != "-").strip()
        if not name:
            name = parts[3]
        if not nav or nav.upper() in ("N.A.", "NA", "-", ""):
            continue
        try:
            float(nav)
        except ValueError:
            continue
        out[int(code)] = {"name": name, "nav": nav, "date": date}
    return out


def to_ddmmyyyy(amfi_date):
    """AMFI gives '11-Aug-2026'; mfapi uses '11-08-2026'."""
    try:
        return datetime.strptime(amfi_date, "%d-%b-%Y").strftime("%d-%m-%Y")
    except ValueError:
        return amfi_date


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return default
    return default


def ingest_seed_tarball():
    """One-time backfill: if data/history-seed.tar.gz exists, MERGE its history/<code>.json
    point-sets into the existing history files. Unlike a plain extract, this UNIONS points,
    so pre-existing single-point stubs (from earlier daily runs) get the full 20-year archive
    added rather than blocking it. Idempotent: merging the same tarball twice is a no-op."""
    import tarfile
    tb = os.path.join(ROOT, "data", "history-seed.tar.gz")
    if not os.path.exists(tb):
        return 0
    merged = 0
    try:
        with tarfile.open(tb, "r:gz") as t:
            for m in t.getmembers():
                if not m.name.startswith("history/") or not m.isfile():
                    continue
                fn = os.path.basename(m.name)
                if not fn.endswith(".json"):
                    continue
                try:
                    seed_obj = json.load(t.extractfile(m))
                except Exception:
                    continue
                seed_pts = seed_obj.get("points", {})
                if not seed_pts:
                    continue
                dest = os.path.join(HIST_DIR, fn)
                cur = load_json(dest, {"meta": seed_obj.get("meta", {}), "points": {}})
                cur.setdefault("meta", {})
                if seed_obj.get("meta"):
                    cur["meta"].update(seed_obj["meta"])
                before = len(cur.get("points", {}))
                cur.setdefault("points", {})
                # seed provides history; keep any existing points (e.g. today's) too
                for d, v in seed_pts.items():
                    cur["points"].setdefault(d, v)
                if len(cur["points"]) > before:
                    with open(dest, "w") as f:
                        json.dump(cur, f, separators=(",", ":"))
                    merged += 1
    except Exception as e:
        print(f"  seed tarball merge failed: {e}", file=sys.stderr)
        return 0
    return merged


def ingest_seed():
    """One-time backfill: read any data/seed/<code>.json (mfapi shape) into history."""
    if not os.path.isdir(SEED_DIR):
        return 0
    n = 0
    for fn in os.listdir(SEED_DIR):
        if not fn.endswith(".json"):
            continue
        code = fn[:-5]
        if not code.isdigit():
            continue
        seed = load_json(os.path.join(SEED_DIR, fn), None)
        if not seed or "data" not in seed:
            continue
        hist_path = os.path.join(HIST_DIR, f"{code}.json")
        if os.path.exists(hist_path):
            continue
        hist = {
            "meta": seed.get("meta", {"scheme_code": int(code)}),
            "points": {d["date"]: d["nav"] for d in seed["data"] if d.get("date") and d.get("nav")},
        }
        with open(hist_path, "w") as f:
            json.dump(hist, f, separators=(",", ":"))
        n += 1
    return n


def main():
    print(f"[{datetime.now(IST).isoformat()}] Building NAV mirror…")
    tb_seeded = ingest_seed_tarball()
    if tb_seeded:
        print(f"  merged history for {tb_seeded} schemes from history-seed.tar.gz")
    seeded = ingest_seed()
    if seeded:
        print(f"  seeded history for {seeded} schemes")

    text = fetch_amfi()
    snap = parse_amfi(text)
    if len(snap) < 1000:
        print(f"  ABORT: only {len(snap)} rows parsed — refusing to overwrite mirror.", file=sys.stderr)
        sys.exit(2)
    print(f"  parsed {len(snap)} scheme NAVs from AMFI")

    # Also emit public files for schemes that have history but aren't in today's AMFI snapshot
    # (dead/merged funds) so their 20yr history is still served.
    all_codes = set(str(c) for c in snap.keys())
    for fn in (os.listdir(HIST_DIR) if os.path.isdir(HIST_DIR) else []):
        if fn.endswith(".json"):
            all_codes.add(fn[:-5])

    written = 0
    for scode in all_codes:
        try:
            code = int(scode)
        except ValueError:
            continue
        hist_path = os.path.join(HIST_DIR, f"{scode}.json")
        hist = load_json(hist_path, {"meta": {"scheme_code": code}, "points": {}})
        rec = snap.get(code)
        hist.setdefault("meta", {})["scheme_code"] = code
        if rec:
            hist["meta"]["scheme_name"] = rec["name"]
            d = to_ddmmyyyy(rec["date"])
            hist.setdefault("points", {})[d] = rec["nav"]
        name = hist["meta"].get("scheme_name", "")
        if not hist.get("points"):
            continue
        with open(hist_path, "w") as f:
            json.dump(hist, f, separators=(",", ":"))

        pts = sorted(
            hist["points"].items(),
            key=lambda kv: datetime.strptime(kv[0], "%d-%m-%Y") if _isdate(kv[0]) else datetime.min,
            reverse=True,
        )
        out = {
            "meta": {"scheme_code": code, "scheme_name": name},
            "data": [{"date": k, "nav": v} for k, v in pts],
            "status": "SUCCESS",
        }
        with open(os.path.join(OUT_DIR, f"{scode}.json"), "w") as f:
            json.dump(out, f, separators=(",", ":"))
        written += 1

    manifest = {
        "generated_ist": datetime.now(IST).isoformat(),
        "scheme_count": written,
        "source": "AMFI NAVAll.txt (daily) + seeded 20yr history",
        "base_path": "/mf/",
    }
    with open(os.path.join(ROOT, "docs", "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"  wrote {written} scheme files to docs/mf/")
    print("  done.")


def _isdate(s):
    try:
        datetime.strptime(s, "%d-%m-%Y"); return True
    except ValueError:
        return False


if __name__ == "__main__":
    main()
