#!/usr/bin/env python3
"""
OPTIONAL fallback bootstrap: pull full NAV history from mfapi.in for a list of
scheme codes and write them into data/seed/. Only needed if AMFI's history report
(seed_history_amfi.py — the preferred path) is unavailable. Prefer that script.

Run this LOCALLY during a healthy mfapi window (not in CI — mfapi is flaky). After
it succeeds and you commit data/seed/, the next build_nav.py run ingests it into
data/history/ permanently, and you can delete the seed folder.

Usage:
  python scripts/seed_from_mfapi.py codes.txt      # one scheme code per line
  python scripts/seed_from_mfapi.py 120587 115676  # or codes as args
"""

import os, sys, json, time, urllib.request

MFAPI = "https://api.mfapi.in/mf/"
ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED  = os.path.join(ROOT, "data", "seed")
os.makedirs(SEED, exist_ok=True)


def codes_from_args(argv):
    codes = []
    for a in argv:
        if os.path.isfile(a):
            with open(a) as f:
                codes += [ln.strip() for ln in f if ln.strip().isdigit()]
        elif a.isdigit():
            codes.append(a)
    return sorted(set(codes))


def fetch(code, tries=6):
    for i in range(tries):
        try:
            req = urllib.request.Request(MFAPI + code, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                if r.status == 200:
                    return json.loads(r.read().decode())
        except Exception:
            pass
        time.sleep(1.0 * (i + 1))  # backoff; mfapi is flaky
    return None


def main():
    codes = codes_from_args(sys.argv[1:])
    if not codes:
        print("Provide a codes file or scheme codes as args.", file=sys.stderr)
        sys.exit(1)
    ok = miss = 0
    for i, c in enumerate(codes, 1):
        out = os.path.join(SEED, f"{c}.json")
        if os.path.exists(out):
            ok += 1; continue
        j = fetch(c)
        if j and j.get("data"):
            with open(out, "w") as f:
                json.dump(j, f, separators=(",", ":"))
            ok += 1
            tag = "OK"
        else:
            miss += 1
            tag = "MISS"
        print(f"[{i}/{len(codes)}] {c} {tag}  (ok={ok} miss={miss})")
        time.sleep(0.15)
    print(f"\nSeeded {ok} schemes, {miss} missed. Re-run to retry misses.")
    if miss:
        print("Misses are usually transient mfapi 502s — just run again.")


if __name__ == "__main__":
    main()
