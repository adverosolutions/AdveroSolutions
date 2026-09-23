#!/usr/bin/env python3
"""Wave 4 (2026-09-16): spend the cycle's Apify credits on fresh supply.

  python3 wave4.py TAG NICHE QUOTA STATE[|STATE...] [--seniority c_suite] [--max-usd X]

TAG      output name (output/production/<TAG>_<stamp>.json)
NICHE    niches/<NICHE>.json
QUOTA    fetch_count per state (under-delivery is free)
STATES   pipe list like "maine|vermont"  or  "nationwide"

Prints per-state counts and overlap against every lead already scraped
(output/production/*.json), so re-buys are visible immediately.
"""
import glob, json, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from runner import run_shard, token, write_outputs, START_FEE, PER_LEAD

ROOT = Path(__file__).resolve().parent
args = [a for a in sys.argv[1:] if not a.startswith("--")]
opts = {a.split("=")[0]: a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--")}
tag, niche, quota, states = args[0], args[1], int(args[2]), args[3]
if states == "nationwide":
    states = ["united states"]
else:
    states = [s.strip() for s in states.split("|") if s.strip()]
    states = [s if s.endswith(", us") else s + ", us" for s in states]
cfg = json.loads((ROOT / "niches" / f"{niche}.json").read_text())
filters = dict(cfg["filters"])
if "--seniority" in opts:
    filters["seniority_level"] = opts["--seniority"].split("|")
worst = len(states) * START_FEE + len(states) * quota * PER_LEAD
print(f"[w4:{tag}] {niche} seniority={filters.get('seniority_level')} x {len(states)} states x {quota} -> worst ${worst:.2f}")
if worst > float(opts.get("--max-usd", 8.0)):
    sys.exit("ABORT: over --max-usd")

known = set()
for f in glob.glob(str(ROOT / "output/production/*.json")):
    for l in json.load(open(f)):
        e = (l.get("email") or l.get("personal_email") or "").strip().lower()
        if e: known.add(e)

tok = token()
leads, n, err = [], 0, 0
t0 = time.time()
with ThreadPoolExecutor(12) as ex:
    futs = [ex.submit(run_shard, niche, st, quota, filters, tok) for st in states]
    for fut in as_completed(futs):
        r = fut.result(); n += 1
        if r["error"]: err += 1
        got = r["leads"]; leads += got
        em = [(l.get("email") or l.get("personal_email") or "").strip().lower() for l in got]
        em = [e for e in em if e]
        dup = sum(1 for e in em if e in known)
        print(f"  [{n:2d}/{len(states)}] {r['state']:24s} {r['error'] or f'{len(got):4d} leads, {len(em):4d} email, {dup:4d} already-known'}", flush=True)

stamp = time.strftime("%Y%m%d_%H%M%S")
jp, _ = write_outputs(tag, leads, stamp, "production")
em = [(l.get("email") or l.get("personal_email") or "").strip().lower() for l in leads]
em = [e for e in em if e]
new = len(set(em) - known)
print(f"[w4:{tag}] done {time.time()-t0:.0f}s: {len(leads)} raw, {len(em)} email, {new} NEW emails, {err} errors, ~${len(states)*START_FEE + len(leads)*PER_LEAD:.2f} -> {jp.name}", flush=True)
