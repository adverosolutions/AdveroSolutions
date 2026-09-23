#!/usr/bin/env python3
"""Recover datasets from the interrupted production run.

Killing the local process does NOT abort an Apify run -- those 21 shards ran
to completion server-side and were billed. Their datasets are still readable
(reads are free), so pull them back rather than pay twice for the same leads.
"""
import json
import urllib.request
from collections import Counter
from pathlib import Path

from runner import token, write_outputs

ROOT = Path(__file__).resolve().parent
API = "https://api.apify.com/v2"
WINDOW = ("2026-08-18T02:16:00", "2026-08-18T02:18:00")  # the orphaned burst

tok = token()
with urllib.request.urlopen(f"{API}/actor-runs?token={tok}&limit=250&desc=1") as r:
    runs = json.load(r)["data"]["items"]

orphans = [x for x in runs if WINDOW[0] <= (x.get("startedAt") or "") <= WINDOW[1]]
print(f"[recover] {len(orphans)} orphaned runs, "
      f"${sum(x.get('usageTotalUsd') or 0 for x in orphans):.2f} already billed")

leads = []
for x in orphans:
    with urllib.request.urlopen(
            f"{API}/datasets/{x['defaultDatasetId']}/items?token={tok}&format=json") as r:
        items = json.load(r)
    if items and "error" not in items[0]:
        leads += items

print(f"[recover] {len(leads)} leads pulled back")
by = Counter()
for l in leads:
    ind = (l.get("industry") or "").lower()
    kw = (l.get("keywords") or "").lower()
    if "staffing" in ind or "recruit" in ind:
        by["recruiting"] += 1
    elif "law" in ind or "legal" in ind:
        by["law"] += 1
    else:
        by["dental"] += 1
print("[recover] by niche:", dict(by))

for niche in ("recruiting", "law", "dental"):
    sub = [l for l in leads if (
        ("staffing" in (l.get("industry") or "").lower() or "recruit" in (l.get("industry") or "").lower()) if niche == "recruiting"
        else ("law" in (l.get("industry") or "").lower() or "legal" in (l.get("industry") or "").lower()) if niche == "law"
        else not any(k in (l.get("industry") or "").lower() for k in ("staffing", "recruit", "law", "legal")))]
    if sub:
        jp, _ = write_outputs(f"{niche}__recovered", sub, "orphan", "production")
        print(f"  {niche}: {len(sub)} -> {jp.name}")
