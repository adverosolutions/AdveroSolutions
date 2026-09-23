#!/usr/bin/env python3
"""Sweep every US state not yet scraped for cleaning. Supply is thin everywhere,
so quotas are generous (under-delivery is free) and the ceiling guards cost."""
import json, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from runner import run_shard, token, write_outputs, SHARD_WEIGHTS
DONE = set(SHARD_WEIGHTS)
FRESH = ["arizona, us","washington, us","colorado, us","minnesota, us",
 "new jersey, us","maryland, us","indiana, us","wisconsin, us","tennessee, us","missouri, us",
 "oregon, us","south carolina, us","connecticut, us","kentucky, us","nevada, us","alabama, us",
 "louisiana, us","utah, us","oklahoma, us","iowa, us","kansas, us","arkansas, us","nebraska, us",
 "new mexico, us","mississippi, us","new hampshire, us","district of columbia, us","idaho, us"]
assert not (set(FRESH) & DONE)
Q = 100
print(f"[sweep] cleaning x {len(FRESH)} states x {Q} -> worst case ${len(FRESH)*0.02 + len(FRESH)*Q*0.002:.2f}")
f = json.loads(Path('niches/cleaning.json').read_text())['filters']; tok = token()
leads, n = [], 0
with ThreadPoolExecutor(12) as ex:
    for fut in as_completed([ex.submit(run_shard, "cleaning", st, Q, f, tok) for st in FRESH]):
        r = fut.result(); n += 1; leads += r['leads']
        print(f"  [{n:2d}/{len(FRESH)}] {r['state']:22s} {r['error'] or len(r['leads'])}")
write_outputs("cleaning__sweep", leads, time.strftime("%Y%m%d_%H%M%S"), "production")
reach = sum(1 for l in leads if (l.get('email') or l.get('personal_email') or '').strip())
print(f"[sweep] +{len(leads)} raw, {reach} reachable ({100*reach//max(1,len(leads))}%), ~${len(FRESH)*0.02+len(leads)*0.002:.2f}")
