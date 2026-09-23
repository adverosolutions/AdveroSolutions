#!/usr/bin/env python3
"""
Scrape leads via Apify code_crafter/leads-finder.

Usage:
    python3 scrape.py inputs/my_filter.json
    python3 scrape.py inputs/my_filter.json --label custom_label

Reads APIFY_API_TOKEN from .env in this script's directory (or from the
process env). Pure stdlib — no pip install required.

Saves results to:
    output/{label}_{YYYYMMDD_HHMMSS}.json
    output/{label}_{YYYYMMDD_HHMMSS}.csv
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ENV_FILE = SCRIPT_DIR / ".env"
OUT_DIR = SCRIPT_DIR / "output"
ENDPOINT = "https://api.apify.com/v2/acts/code_crafter~leads-finder/run-sync-get-dataset-items"

START_FEE_USD = 0.02
PER_LEAD_USD = 0.002
# The actor's own fetch_count default is 100000 (~$200). Never inherit it.
MAX_FETCH_COUNT = 5000


def check_cost(payload: dict, assume_yes: bool) -> None:
    """Refuse to run without an explicit, bounded fetch_count.

    Omitting fetch_count silently inherits the actor default of 100000 leads,
    which bills ~$200. This is the single most expensive mistake available here.
    """
    fc = payload.get("fetch_count")
    if fc is None:
        sys.exit(
            "ERROR: 'fetch_count' is missing from the payload.\n"
            "The actor defaults to 100000 leads (~$200). Set it explicitly, "
            "e.g. \"fetch_count\": 100"
        )
    if not isinstance(fc, int) or fc <= 0:
        sys.exit(f"ERROR: 'fetch_count' must be a positive integer, got {fc!r}")
    if fc > MAX_FETCH_COUNT:
        sys.exit(
            f"ERROR: fetch_count={fc} exceeds the {MAX_FETCH_COUNT} safety cap "
            f"(~${START_FEE_USD + fc * PER_LEAD_USD:.2f}).\n"
            "Raise MAX_FETCH_COUNT in scrape.py only if that spend is intended."
        )

    est = START_FEE_USD + fc * PER_LEAD_USD
    print(f"[scrape] fetch_count={fc}  estimated max cost=${est:.2f}")
    if est > 1.00 and not assume_yes:
        reply = input(f"[scrape] This may cost up to ${est:.2f}. Continue? [y/N] ")
        if reply.strip().lower() not in ("y", "yes"):
            sys.exit("[scrape] aborted by user")


def load_token() -> str:
    """Return APIFY_API_TOKEN from process env or .env file."""
    if os.environ.get("APIFY_API_TOKEN"):
        return os.environ["APIFY_API_TOKEN"].strip()
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("APIFY_API_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit(
        "ERROR: APIFY_API_TOKEN not found.\n"
        "Add it to .env in this folder:\n"
        f"  echo 'APIFY_API_TOKEN=your_token_here' > {ENV_FILE}\n"
        "Or export it: export APIFY_API_TOKEN=your_token_here"
    )


def post_to_apify(payload: dict, token: str) -> list:
    """POST filters to Apify, return list of lead dicts."""
    url = f"{ENDPOINT}?{urllib.parse.urlencode({'token': token})}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3000) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:1000]
        sys.exit(f"ERROR {e.code}: {err_body}")
    except urllib.error.URLError as e:
        sys.exit(f"ERROR: network failure: {e.reason}")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(f"ERROR: response was not JSON:\n{raw[:500]}")


def write_csv(leads: list, path: Path) -> None:
    """Flatten lead dicts into a CSV. Union of all keys across leads."""
    if not leads:
        path.write_text("")
        return
    keys = []
    seen = set()
    for lead in leads:
        for k in lead.keys():
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for lead in leads:
            row = {k: ("" if v is None else v) for k, v in lead.items()}
            # Coerce nested structures to JSON strings so csv stays flat.
            for k, v in row.items():
                if isinstance(v, (list, dict)):
                    row[k] = json.dumps(v, ensure_ascii=False)
            w.writerow(row)


def main() -> None:
    p = argparse.ArgumentParser(description="Scrape leads via Apify leads-finder")
    p.add_argument("input_file", help="path to JSON file with Apify filter payload")
    p.add_argument("--label", default=None, help="output filename label (defaults to file_name in payload)")
    p.add_argument("-y", "--yes", action="store_true", help="skip the cost confirmation prompt")
    args = p.parse_args()

    input_path = Path(args.input_file)
    if not input_path.exists():
        sys.exit(f"ERROR: input file not found: {input_path}")

    try:
        payload = json.loads(input_path.read_text())
    except json.JSONDecodeError as e:
        sys.exit(f"ERROR: input file is not valid JSON: {e}")

    label = args.label or payload.get("file_name") or "leads"
    label = "".join(c if c.isalnum() or c in "_-" else "_" for c in label)

    check_cost(payload, args.yes)

    token = load_token()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[scrape] POST {ENDPOINT}")
    print(f"[scrape] filters: {json.dumps(payload, indent=2)}")
    print("[scrape] waiting for Apify (this can take 30-120s)...")

    t0 = time.time()
    leads = post_to_apify(payload, token)
    elapsed = time.time() - t0

    if not isinstance(leads, list):
        sys.exit(f"ERROR: expected list of leads, got {type(leads).__name__}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = OUT_DIR / f"{label}_{ts}.json"
    csv_path = OUT_DIR / f"{label}_{ts}.csv"

    json_path.write_text(json.dumps(leads, indent=2, ensure_ascii=False))
    write_csv(leads, csv_path)

    with_email = sum(1 for l in leads if l.get("email")) if leads else 0
    fill_rate = (with_email / len(leads) * 100) if leads else 0

    print(f"[scrape] done in {elapsed:.1f}s")
    print(f"[scrape] leads returned: {len(leads)}")
    print(f"[scrape] with email:     {with_email} ({fill_rate:.1f}%)")
    print(f"[scrape] json: {json_path}")
    print(f"[scrape] csv:  {csv_path}")


if __name__ == "__main__":
    main()
