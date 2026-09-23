#!/usr/bin/env python3
"""Top up a niche from fresh states after the main batches under-deliver.

Uses states NOT in SHARD_WEIGHTS, so the new leads stay disjoint from
everything already scraped and nothing is billed twice.
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from runner import run_shard, token, write_outputs, SHARD_WEIGHTS

ROOT = Path(__file__).resolve().parent
EXTRA = ["arizona, us", "washington, us", "colorado, us", "minnesota, us"]

niche = sys.argv[1]
per = int(sys.argv[2])

assert not (set(EXTRA) & set(SHARD_WEIGHTS)), "top-up states must be fresh"
cfg = json.loads((ROOT / "niches" / f"{niche}.json").read_text())
print(f"[topup] {niche}: {len(EXTRA)} fresh states x {per} "
      f"-> max ${len(EXTRA)*0.02 + len(EXTRA)*per*0.002:.2f}")

tok = token()
with ThreadPoolExecutor(max_workers=4) as ex:
    res = list(ex.map(lambda st: run_shard(niche, st, per, cfg["filters"], tok), EXTRA))

leads = []
for r in res:
    print(f"  {r['tag']}: {r['error'] or str(len(r['leads'])) + ' leads'}")
    leads += r["leads"]

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
jp, _ = write_outputs(f"{niche}__topup", leads, stamp, "production")
reach = sum(1 for l in leads if (l.get("email") or l.get("personal_email") or "").strip())
print(f"[topup] +{len(leads)} leads, {reach} reachable -> {jp.name}")
