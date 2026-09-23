#!/usr/bin/env python3
"""Sequential Apify runner: waits for the account's single-run lock, runs, reports."""
import json, os, sys, time, urllib.request, urllib.error

TOKEN = os.environ["APIFY_TOKEN"]
ACTOR = "braveleads~leads-finder-linkedin-apollo-leads-generator"
API = "https://api.apify.com/v2"

FREE_DOMAINS = {
    "gmail.com", "yahoo.com", "aol.com", "hotmail.com", "outlook.com", "icloud.com",
    "comcast.net", "sbcglobal.net", "msn.com", "bellsouth.net", "att.net",
    "verizon.net", "me.com", "live.com", "cox.net", "charter.net",
}


def api(path, method="GET", body=None):
    url = f"{API}{path}{'&' if '?' in path else '?'}token={TOKEN}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def wait_for_free_slot(timeout=900):
    """The actor permits one concurrent run per account; wait it out."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        runs = api(f"/acts/{ACTOR}/runs?status=RUNNING&limit=5")["data"]["items"]
        if not runs:
            return True
        print(f"    ...waiting on run {runs[0]['id']}", flush=True)
        time.sleep(15)
    return False


def run_probe(label, inp, attempts=4, cooldown=90):
    """The actor holds an opaque backend lock after each run and still charges
    the $0.05 start fee when it refuses, so back off hard between attempts."""
    print(f"\n===== {label} =====", flush=True)
    print(f"  input: {json.dumps(inp)}", flush=True)

    for attempt in range(1, attempts + 1):
        wait_for_free_slot()
        run = api(f"/acts/{ACTOR}/runs", "POST", inp)["data"]
        rid = run["id"]

        while True:
            d = api(f"/actor-runs/{rid}")["data"]
            if d["status"] not in ("READY", "RUNNING"):
                break
            time.sleep(10)

        log = urllib.request.urlopen(f"{API}/actor-runs/{rid}/log?token={TOKEN}").read().decode()
        if "already in progress" not in log:
            break
        print(f"  !! REJECTED (backend lock), attempt {attempt}/{attempts}; "
              f"sleeping {cooldown}s", flush=True)
        if attempt == attempts:
            print("  !! GAVE UP")
            return None
        time.sleep(cooldown)
    found = next((l.split("Leads Found:")[1].strip()
                  for l in log.splitlines() if "Leads Found:" in l), "?")

    items = api(f"/actor-runs/{rid}/dataset/items?format=json&clean=true")
    rows = [r for r in items if r.get("employee_id")]
    print(f"  pool={found}  stored={len(rows)}  cost=${d.get('usageTotalUsd', 0):.3f}")

    if rows:
        n = len(rows)
        pct = lambda f: f"{100 * sum(1 for r in rows if r.get(f)) / n:.0f}%"
        emails = [r["email"] for r in rows if r.get("email")]
        consumer = sum(1 for e in emails if e.split("@")[-1].lower() in FREE_DOMAINS)
        print(f"  fill: email {pct('email')} | phone {pct('phone_numbers')} | "
              f"site {pct('organizationWebsite')} | orgPhone {pct('organizationPhone')}")
        print(f"  consumer-domain emails: {consumer}/{len(emails)}")
        from collections import Counter
        print("  SIC:", dict(Counter(r.get("organizationSIC") for r in rows).most_common(5)))
        print("  titles:", dict(Counter(r.get("title") for r in rows).most_common(5)))
        json.dump(rows, open(f"runs/{label}.leads.json", "w"), indent=1)
    return rows


if __name__ == "__main__":
    probes = json.load(open(sys.argv[1]))
    for label, inp in probes.items():
        run_probe(label, inp)
