#!/usr/bin/env python3
"""Wave 2: top up to a target of VERIFIED-CLEAN emails.

Sizing works backwards from the measured clean rate per niche, not from raw
lead counts -- dental needs roughly twice the raw leads law does to yield the
same number of sendable addresses.

States here are disjoint from every state used in wave 1 (the 12 shard states
plus the 4 top-up states), so nothing is re-fetched or double-billed.
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from runner import run_shard, token, write_outputs, SHARD_WEIGHTS, START_FEE, PER_LEAD

ROOT = Path(__file__).resolve().parent
USED = set(SHARD_WEIGHTS) | {"arizona, us", "washington, us", "colorado, us", "minnesota, us"}

FRESH = {
    "new jersey, us": 90, "maryland, us": 80, "indiana, us": 80,
    "wisconsin, us": 75, "tennessee, us": 75, "missouri, us": 70,
    "oregon, us": 65, "south carolina, us": 60, "connecticut, us": 60,
    "kentucky, us": 55, "nevada, us": 50, "alabama, us": 50,
}
assert not (set(FRESH) & USED), "wave 2 states must be disjoint from wave 1"

# measured in wave 1: share of fetched leads that survive cleanup AND verify ok
CLEAN_YIELD = {"law": 0.72 * 0.92, "recruiting": 0.61 * 0.92, "dental": 0.51 * 0.92}
DEFICIT = {"law": 189, "recruiting": 455, "dental": 599}

plan, total = {}, 0
for niche, need in DEFICIT.items():
    raw = round(need / CLEAN_YIELD[niche] * 1.10)  # 10% buffer
    denom = sum(FRESH.values())
    plan[niche] = {st: max(1, round(raw * w / denom)) for st, w in FRESH.items()}
    total += sum(plan[niche].values())
    print(f"  {niche:11s} need {need:4d} clean -> fetch {sum(plan[niche].values()):5d} raw")

runs = sum(len(v) for v in plan.values())
cost = runs * START_FEE + total * PER_LEAD
print(f"\n[wave2] {runs} runs, {total} leads, worst case ${cost:.2f}")
if "--dry" in sys.argv:
    sys.exit(0)
if cost > 8.0:
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
        print(f"  [{len(results)}/{len(jobs)}] {r['tag']}: {r['error'] or str(len(r['leads']))+' leads'}")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
for niche in plan:
    leads = [l for r in results if r["niche"] == niche for l in r["leads"]]
    jp, _ = write_outputs(f"{niche}__w2", leads, stamp, "production")
    print(f"[wave2] {niche}: {len(leads)} -> {jp.name}")
