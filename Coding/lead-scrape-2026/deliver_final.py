#!/usr/bin/env python3
"""Final campaign files for the three ACTIVE niches only (recruiting, cleaning,
bookkeeping). Law/dental stay in output/verified/ but are excluded here."""
import csv
from collections import Counter
from pathlib import Path
OUT = Path("output/verified"); FIN = Path("output/FINAL"); FIN.mkdir(exist_ok=True)
ACTIVE = ("recruiting", "cleaning", "bookkeeping")
order = {"ok": 0, "catch_all": 1, "unknown": 2}
rows = []
for f in ("CLEAN_all.csv", "RISKY_all.csv"):
    rows += [r for r in csv.DictReader((OUT / f).open(encoding="utf-8-sig")) if r["niche"] in ACTIVE]
rows.sort(key=lambda r: (r["niche"], order.get(r["mv_result"], 9), r["contact_rank_at_company"]))
cols = list(rows[0].keys())
def write(name, data):
    with (FIN / name).open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(data)
write("SENDABLE_3niches.csv", rows)
write("CLEAN_3niches.csv", [r for r in rows if r["mv_result"] == "ok"])
for n in ACTIVE:
    write(f"CLEAN_{n}.csv", [r for r in rows if r["niche"] == n and r["mv_result"] == "ok"])
    write(f"SENDABLE_{n}.csv", [r for r in rows if r["niche"] == n])
print(f"{'niche':12s} {'CLEAN':>6s} {'catch_all':>9s} {'unknown':>7s} {'sendable':>9s}")
for n in ACTIVE:
    c = Counter(r["mv_result"] for r in rows if r["niche"] == n)
    print(f"{n:12s} {c['ok']:6d} {c['catch_all']:9d} {c['unknown']:7d} {sum(c.values()):9d}")
c = Counter(r["mv_result"] for r in rows)
print(f"{'TOTAL':12s} {c['ok']:6d} {c['catch_all']:9d} {c['unknown']:7d} {sum(c.values()):9d}")
print(f"\nfiles -> {FIN}/")
