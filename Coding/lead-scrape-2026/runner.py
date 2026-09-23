#!/usr/bin/env python3
"""Sharded parallel lead scraper for Apify code_crafter/leads-finder.

WHY SHARDING: the actor has no offset/page/sort parameter, and identical
filters return byte-identical leads (verified: 100% overlap on a repeat run).
So running the same query on N "endpoints" in parallel bills N times for one
list. Different US states on identical filters return 0% overlap (verified),
so `contact_location` is the only safe axis to parallelise on.

COST: $0.02 per run start + $0.002 per lead fetched. You are billed per lead
ACTUALLY returned, so an over-generous shard quota is free insurance against
a thin shard -- only over-delivery costs money, never under-delivery.

Usage:
    python3 runner.py --smoke                       # 25 leads/niche, nationwide
    python3 runner.py --production                  # full sharded run
    python3 runner.py --smoke --niches dental       # one niche only
"""
import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ACTOR = "code_crafter~leads-finder"
API = "https://api.apify.com/v2"

START_FEE = 0.02
PER_LEAD = 0.002

# States carry the shard quotas. Ordered by the actor's own supply ranking;
# weights approximate business density so no single shard has to over-reach.
SHARD_WEIGHTS = {
    "california, us": 200, "texas, us": 180, "new york, us": 170,
    "florida, us": 160, "illinois, us": 120, "pennsylvania, us": 110,
    "michigan, us": 100, "north carolina, us": 100, "virginia, us": 90,
    "ohio, us": 90, "massachusetts, us": 90, "georgia, us": 90,
}

SMOKE_SHARDS = {"united states": 25}

# Production runs in geographic batches so quality can be inspected between
# them. Quotas always come from the FULL weight table below, so the batches
# still sum to each niche's target -- a batch just picks which states go now.
BATCHES = {
    "b1": ["california, us"],
    "b2": ["texas, us", "new york, us"],
    "b3": ["florida, us", "illinois, us", "pennsylvania, us"],
    "b4": ["michigan, us", "north carolina, us", "virginia, us"],
    "b5": ["ohio, us", "massachusetts, us", "georgia, us"],
}


def plan_shards(target: int, fill_rate: float) -> dict:
    """Split a per-niche emailable target into per-state fetch quotas.

    fill_rate is the measured share of returned leads that carry an email --
    we must over-fetch by 1/fill_rate to land `target` usable contacts.
    """
    total = round(target / fill_rate)
    denom = sum(SHARD_WEIGHTS.values())
    return {st: max(1, round(total * w / denom)) for st, w in SHARD_WEIGHTS.items()}

# Apify STARTER allows 32 concurrent actor jobs; stay well under so a
# three-niche production run cannot wedge the account.
MAX_WORKERS = 12


def token() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("APIFY_TOKEN="):
            return line.split("=", 1)[1].strip()
    sys.exit("ERROR: APIFY_TOKEN missing from .env")


def run_shard(niche: str, state: str, quota: int, filters: dict, tok: str) -> dict:
    """Start one actor run, poll to completion, return its leads."""
    payload = {
        **filters,
        "contact_location": [state],
        "fetch_count": quota,
        "file_name": f"{niche}_{state.replace(', ', '_').replace(' ', '-')}",
    }
    tag = f"{niche}/{state}"
    try:
        req = urllib.request.Request(
            f"{API}/acts/{ACTOR}/runs?token={tok}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=120) as r:
            info = json.loads(r.read())["data"]
    except urllib.error.HTTPError as e:
        return {"tag": tag, "niche": niche, "state": state, "leads": [],
                "error": f"HTTP {e.code}: {e.read().decode()[:200]}"}

    rid = info["id"]
    for _ in range(240):  # up to ~20 min
        time.sleep(5)
        with urllib.request.urlopen(f"{API}/actor-runs/{rid}?token={tok}", timeout=60) as r:
            info = json.loads(r.read())["data"]
        if info["status"] in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break

    if info["status"] != "SUCCEEDED":
        return {"tag": tag, "niche": niche, "state": state, "leads": [],
                "error": f"run {info['status']}"}

    with urllib.request.urlopen(
            f"{API}/datasets/{info['defaultDatasetId']}/items?token={tok}&format=json",
            timeout=180) as r:
        items = json.loads(r.read())

    # A single record carrying an 'error' key is a plan/permission gate, not data.
    if len(items) == 1 and isinstance(items[0], dict) and "error" in items[0]:
        return {"tag": tag, "niche": niche, "state": state, "leads": [],
                "error": f"GATED: {items[0]['error']}"}

    return {"tag": tag, "niche": niche, "state": state, "leads": items,
            "billed": info.get("usageTotalUsd", 0), "error": None}


def write_outputs(niche: str, leads: list, stamp: str, subdir: str = "") -> tuple:
    out = ROOT / "output" / subdir if subdir else ROOT / "output"
    out.mkdir(parents=True, exist_ok=True)
    jp = out / f"{niche}_{stamp}.json"
    cp = out / f"{niche}_{stamp}.csv"
    jp.write_text(json.dumps(leads, indent=2, ensure_ascii=False))
    if leads:
        keys = []
        for l in leads:
            for k in l:
                if k not in keys:
                    keys.append(k)
        with cp.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            w.writeheader()
            for l in leads:
                w.writerow({k: ("" if v is None else
                                json.dumps(v) if isinstance(v, (list, dict)) else v)
                            for k, v in l.items()})
    return jp, cp


def main() -> None:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--smoke", action="store_true", help="25 leads/niche, nationwide")
    g.add_argument("--production", action="store_true", help="full sharded run")
    p.add_argument("--niches", nargs="*", default=["recruiting", "law", "dental"])
    p.add_argument("--batch", choices=sorted(BATCHES), help="run one geographic batch")
    p.add_argument("--max-usd", type=float, default=12.0, help="hard spend ceiling")
    p.add_argument("-y", "--yes", action="store_true")
    args = p.parse_args()

    configs = [json.loads((ROOT / "niches" / f"{n}.json").read_text()) for n in args.niches]

    jobs = []
    for c in configs:
        if args.smoke:
            shards = SMOKE_SHARDS
        else:
            shards = plan_shards(c.get("target", 1350), c.get("fill_rate", 0.90))
            if args.batch:
                shards = {k: v for k, v in shards.items() if k in BATCHES[args.batch]}
        jobs += [(c["niche"], st, q, c["filters"]) for st, q in shards.items()]
    worst = len(jobs) * START_FEE + sum(j[2] for j in jobs) * PER_LEAD

    scope = "SMOKE" if args.smoke else f"PRODUCTION {args.batch or 'ALL'}"
    print(f"[run] {scope}: {len(configs)} niches, {len(jobs)} runs")
    print(f"[run] worst-case spend: ${worst:.2f} (ceiling ${args.max_usd:.2f})")
    if worst > args.max_usd:
        sys.exit(f"ABORT: ${worst:.2f} exceeds --max-usd ${args.max_usd:.2f}")
    if not args.yes and worst > 1.00:
        if input("[run] proceed? [y/N] ").strip().lower() not in ("y", "yes"):
            sys.exit("aborted")

    tok = token()
    t0 = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = [ex.submit(run_shard, n, st, q, f, tok) for n, st, q, f in jobs]
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            status = r["error"] or f"{len(r['leads'])} leads"
            print(f"  [{len(results)}/{len(jobs)}] {r['tag']}: {status}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\n[run] finished in {time.time()-t0:.0f}s")

    grand = 0
    for cfg in configs:
        n = cfg["niche"]
        seen, merged, dupes = set(), [], 0
        for r in sorted([x for x in results if x["niche"] == n], key=lambda x: x["state"]):
            for lead in r["leads"]:
                key = (lead.get("email") or "").lower().strip()
                if key and key in seen:
                    dupes += 1
                    continue
                if key:
                    seen.add(key)
                merged.append(lead)
        emailed = [l for l in merged if l.get("email")]
        tag = f"{n}__{args.batch}" if args.batch else n
        jp, cp = write_outputs(tag, merged, stamp,
                               "production" if args.production else "")
        grand += len(merged)
        print(f"\n[{n}] {cfg['label']}")
        print(f"  fetched={len(merged)}  with_email={len(emailed)} "
              f"({100*len(emailed)/max(1,len(merged)):.0f}%)  cross-shard dupes={dupes}")
        print(f"  -> {cp.name}")

    print(f"\n[run] total fetched={grand}  approx billed=${len(jobs)*START_FEE + grand*PER_LEAD:.2f}")


if __name__ == "__main__":
    main()
