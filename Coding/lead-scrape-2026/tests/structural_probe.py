#!/usr/bin/env python3
"""Structural probe: does parallel sharding actually yield unique leads?

Answers three questions for ~$0.12 total:
  A vs B  -- identical filters, run twice: does the actor return the SAME leads?
             (if yes, naive parallel duplication is pure wasted spend)
  A vs C  -- same filters, different state: are geographic shards disjoint?
             (if yes, state sharding is a safe parallelisation axis)

Each probe fetches 10 leads: 3 x ($0.02 start + 10 x $0.002) = $0.12.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACTOR = "code_crafter~leads-finder"
FETCH = 10

# Deliberately generic + high-supply so the probe measures actor mechanics,
# not the quirks of any one niche.
BASE = {
    "company_industry": ["construction"],
    "seniority_level": ["owner", "founder"],
    "email_status": ["validated"],
    "fetch_count": FETCH,
}

PROBES = {
    "A_texas":    {**BASE, "contact_location": ["texas, us"],   "file_name": "probe_A_texas"},
    "B_texas_dup": {**BASE, "contact_location": ["texas, us"],  "file_name": "probe_B_texas_dup"},
    "C_florida":  {**BASE, "contact_location": ["florida, us"], "file_name": "probe_C_florida"},
}


def token() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("APIFY_TOKEN="):
            return line.split("=", 1)[1].strip()
    sys.exit("no APIFY_TOKEN in .env")


def run(name: str, payload: dict, tok: str) -> tuple:
    """Start an async run, poll to completion, return (name, run_meta, items)."""
    url = f"https://api.apify.com/v2/acts/{ACTOR}/runs?token={tok}"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            run_info = json.loads(r.read())["data"]
    except urllib.error.HTTPError as e:
        return name, {"error": f"{e.code}: {e.read().decode()[:300]}"}, []

    rid = run_info["id"]
    for _ in range(150):  # up to ~12.5 min
        time.sleep(5)
        with urllib.request.urlopen(
                f"https://api.apify.com/v2/actor-runs/{rid}?token={tok}", timeout=60) as r:
            info = json.loads(r.read())["data"]
        if info["status"] in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break

    dsid = info["defaultDatasetId"]
    with urllib.request.urlopen(
            f"https://api.apify.com/v2/datasets/{dsid}/items?token={tok}&format=json",
            timeout=120) as r:
        items = json.loads(r.read())
    return name, info, items


def main() -> None:
    tok = token()
    est = len(PROBES) * (0.02 + FETCH * 0.002)
    print(f"[probe] {len(PROBES)} runs x {FETCH} leads -> max ${est:.2f}\n")

    with ThreadPoolExecutor(max_workers=3) as ex:
        results = list(ex.map(lambda kv: run(kv[0], kv[1], tok), PROBES.items()))

    out = {}
    for name, info, items in results:
        if info.get("error"):
            print(f"  {name}: ERROR {info['error']}")
            continue
        # A dataset whose only record has an 'error' key is the free-plan gate.
        if len(items) == 1 and "error" in items[0]:
            print(f"  {name}: GATED -> {items[0]['error']}")
            continue
        emails = [i.get("email") for i in items if i.get("email")]
        out[name] = {"items": items, "emails": set(emails)}
        cost = (info.get("usageTotalUsd") or 0)
        print(f"  {name}: {len(items)} leads, {len(emails)} emails, "
              f"status={info['status']}, billed=${cost:.4f}")

    (ROOT / "tests" / "probe_raw.json").write_text(
        json.dumps({k: v["items"] for k, v in out.items()}, indent=2))

    print("\n[probe] ---- ANSWERS ----")
    if "A_texas" in out and "B_texas_dup" in out:
        a, b = out["A_texas"]["emails"], out["B_texas_dup"]["emails"]
        ov = len(a & b)
        print(f"IDENTICAL filters (A vs B): {ov}/{min(len(a),len(b))} overlap "
              f"({100*ov/max(1,min(len(a),len(b))):.0f}%)")
        print("  -> " + ("SAME leads: parallel same-filter runs are wasted spend."
                         if ov > 0.8 * min(len(a), len(b))
                         else "DIFFERENT leads: actor varies results between runs."))
    if "A_texas" in out and "C_florida" in out:
        a, c = out["A_texas"]["emails"], out["C_florida"]["emails"]
        ov = len(a & c)
        print(f"DIFFERENT states (A vs C): {ov} overlap")
        print("  -> " + ("state shards are DISJOINT: safe parallel axis."
                         if ov == 0 else "shards leak: dedupe required."))


if __name__ == "__main__":
    main()
