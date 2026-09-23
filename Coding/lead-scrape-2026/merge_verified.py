#!/usr/bin/env python3
"""Join MillionVerifier results back onto the lead list.

MillionVerifier buckets every address into one of:
    ok          -- mailbox confirmed, safe to send
    catch_all   -- domain accepts everything, so the mailbox can't be proven
    unknown     -- server wouldn't answer in time
    disposable  -- temp-mail provider
    invalid     -- mailbox does not exist

Only `ok` is genuinely clean. catch_all/unknown are the "risky" bucket: they
may well deliver, but they can't be confirmed, and they're where bounce rate
comes from if you send them blind.

Usage: python3 merge_verified.py
"""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
V = ROOT / "verify"
FINAL = ROOT / "output" / "final"
OUT = ROOT / "output" / "verified"

CLEAN = {"ok"}
RISKY = {"catch_all", "unknown"}
BAD = {"invalid", "disposable"}


def load_results() -> dict:
    """Map lowercased email -> MillionVerifier result string."""
    res = {}
    path = V / "results.csv"
    with path.open(encoding="utf-8-sig", errors="replace") as f:
        sample = f.read(4096)
        f.seek(0)
        delim = "," if sample.count(",") >= sample.count(";") else ";"
        rdr = csv.reader(f, delimiter=delim)
        header = next(rdr, [])
        low = [h.strip().lower() for h in header]
        ei = low.index("email") if "email" in low else 0
        # MV names this column "result" (v2) or "quality" on some plans
        ri = low.index("result") if "result" in low else (
             low.index("quality") if "quality" in low else 1)
        for row in rdr:
            if len(row) <= max(ei, ri):
                continue
            res[row[ei].strip().lower()] = row[ri].strip().lower()
    return res


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    res = load_results()
    print(f"[merge] {len(res)} verification results loaded")
    print("[merge] distribution:", dict(Counter(res.values())))

    rows = list(csv.DictReader((FINAL / "ALL_LEADS.csv").open(encoding="utf-8-sig")))
    cols = list(rows[0].keys()) + ["mv_result", "mv_bucket"]

    buckets = defaultdict(list)
    per_niche = defaultdict(Counter)
    for r in rows:
        v = res.get(r["email"].strip().lower(), "unknown")
        bucket = "clean" if v in CLEAN else "risky" if v in RISKY else "bad"
        r["mv_result"], r["mv_bucket"] = v, bucket
        buckets[bucket].append(r)
        per_niche[r["niche"]][bucket] += 1
        per_niche[r["niche"]][f"r:{v}"] += 1

    def write(name, data):
        p = OUT / name
        with p.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(data)
        return p

    write("CLEAN_all.csv", buckets["clean"])
    write("RISKY_all.csv", buckets["risky"])
    write("BAD_all.csv", buckets["bad"])
    for niche in ("recruiting", "law", "dental", "cleaning", "bookkeeping"):
        write(f"CLEAN_{niche}.csv", [r for r in buckets["clean"] if r["niche"] == niche])
        write(f"RISKY_{niche}.csv", [r for r in buckets["risky"] if r["niche"] == niche])

    n = len(rows)
    print(f"\n{'niche':12s} {'total':>6s} {'CLEAN':>7s} {'RISKY':>7s} {'BAD':>6s}   clean%")
    for niche in ("recruiting", "law", "dental", "cleaning", "bookkeeping"):
        c = per_niche[niche]
        t = c["clean"] + c["risky"] + c["bad"]
        print(f"{niche:12s} {t:6d} {c['clean']:7d} {c['risky']:7d} {c['bad']:6d}   {100*c['clean']//max(1,t)}%")
    tc, tr, tb = len(buckets["clean"]), len(buckets["risky"]), len(buckets["bad"])
    print(f"{'TOTAL':12s} {n:6d} {tc:7d} {tr:7d} {tb:6d}   {100*tc//n}%")

    print("\nrisky breakdown by niche:")
    for niche in ("recruiting", "law", "dental", "cleaning", "bookkeeping"):
        c = per_niche[niche]
        print(f"  {niche:12s} catch_all={c['r:catch_all']:4d}  unknown={c['r:unknown']:4d}")
    print("\nbad breakdown:", dict(Counter(
        r["mv_result"] for r in buckets["bad"])))
    print(f"\nfiles -> {OUT}")


if __name__ == "__main__":
    main()
