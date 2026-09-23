#!/usr/bin/env python3
"""Wave 3: close the last gap to 4,000 verified-clean emails.

Skips dental deliberately -- it under-delivered 431 in wave 2 (supply ceiling
on size-gated practice owners) and converts worst at 53% clean. Law converts
at 71% and recruiting 60%, so the remaining budget buys the most sendable
addresses there.
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from runner import run_shard, token, write_outputs, SHARD_WEIGHTS, START_FEE, PER_LEAD

ROOT = Path(__file__).resolve().parent
USED = set(SHARD_WEIGHTS) | {
    "arizona, us", "washington, us", "colorado, us", "minnesota, us",
    "new jersey, us", "maryland, us", "indiana, us", "wisconsin, us",
    "tennessee, us", "missouri, us", "oregon, us", "south carolina, us",
    "connecticut, us", "kentucky, us", "nevada, us", "alabama, us"}

FRESH = {
    "louisiana, us": 55, "utah, us": 55, "oklahoma, us": 50, "iowa, us": 45,
    "kansas, us": 45, "arkansas, us": 40, "nebraska, us": 35,
    "new mexico, us": 35, "mississippi, us": 30, "new hampshire, us": 30,
    "district of columbia, us": 45, "idaho, us": 30,
}
assert not (set(FRESH) & USED), f"overlap: {set(FRESH) & USED}"

CLEAN_YIELD = {"law": 0.71 * 0.92, "recruiting": 0.60 * 0.92}
TARGET = {"law": 150, "recruiting": 170}   # 320 vs the 258 actually needed

plan, total = {}, 0
for niche, need in TARGET.items():
    raw = round(need / CLEAN_YIELD[niche])
    denom = sum(FRESH.values())
    plan[niche] = {st: max(1, round(raw * w / denom)) for st, w in FRESH.items()}
    total += sum(plan[niche].values())
    print(f"  {niche:11s} target {need:3d} clean -> fetch {sum(plan[niche].values()):4d} raw")

runs = sum(len(v) for v in plan.values())
cost = runs * START_FEE + total * PER_LEAD
print(f"\n[wave3] {runs} runs, {total} leads, worst case ${cost:.2f}")
if "--dry" in sys.argv:
    sys.exit(0)
if cost > 3.0:
    sys.exit(f"ABORT: ${cost:.2f} over ceiling")

tok = token()
cfgs = {n: json.loads((ROOT / "niches" / f"{n}.json").read_text()) for n in plan}
jobs = [(n, st, q, cfgs[n]["filters"]) for n, sh in plan.items() for st, q in sh.items()]
results = []
with ThreadPoolExecutor(max_workers=12) as ex:
    futs = [ex.submit(run_shard, n, st, q, f, tok) for n, st, q, f in jobs]
    for fut in as_completed(futs):
        r = fut.result()
        results.append(r)

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
for niche in plan:
    leads = [l for r in results if r["niche"] == niche for l in r["leads"]]
    jp, _ = write_outputs(f"{niche}__w3", leads, stamp, "production")
    print(f"[wave3] {niche}: {len(leads)} leads -> {jp.name}")
