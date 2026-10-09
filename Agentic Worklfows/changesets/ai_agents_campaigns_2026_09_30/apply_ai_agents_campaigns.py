#!/usr/bin/env python3
"""Change-set: create six "2026 <niche> - AI Agents" Instantly campaigns, left in DRAFT.

  python3 apply_ai_agents_campaigns.py [--dry-run]   # dry-run (default, GETs only)
  MODE=live ALLOW_LIVE_WRITES=1 python3 apply_ai_agents_campaigns.py --apply --yes
                                                     # live: POST six draft campaigns

Settings are read from the live template campaign "2026 Service - AI Agents" at run time.
Copy comes from copy_source.json (byte for byte from Lorenzo's Claude Doc).
New ids go to Coding/lead-scrape-2026/instantly_campaigns_ai_agents.json, never to
instantly_campaigns.json.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]  # .../AdveroSolutions
LEAD_DIR = REPO / "Coding" / "lead-scrape-2026"
TMP_DIR = REPO / ".tmp" / "ai_agents_2026_09_30"
IDS_FILE = LEAD_DIR / "instantly_campaigns_ai_agents.json"
COPY_FILE = HERE / "copy_source.json"
APPLIED_FILE = HERE / "APPLIED.md"

sys.path.insert(0, str(LEAD_DIR))
import instantly_push  # noqa: E402  (key() and call(); the key is never printed)

TEMPLATE_ID = "d81f1d53-23d6-48a6-aea3-80c21192e17e"
SUBJECT = "{{firstName}}, question"

# (campaign name, ids-file key, copy key)
CAMPAIGNS = [
    ("2026 Bookkeeping & tax - AI Agents", "bookkeeping_ai", "bookkeeping"),
    ("2026 Insurance brokers - AI Agents", "insurance_broker_ai", "insurance_broker"),
    ("2026 Landscaping - AI Agents", "landscaping_ai", "landscaping"),
    ("2026 Marketing agencies - AI Agents", "marketing_agency_ai", "marketing_agency"),
    ("2026 MSP - AI Agents", "msp_ai", "msp"),
    ("2026 Pest control - AI Agents", "pest_control_ai", "pest_control"),
]

COPIED_SETTINGS = ["email_list", "daily_limit", "email_gap", "text_only", "stop_on_reply",
                   "link_tracking", "open_tracking", "pl_value"]
FIXED_SETTINGS = {"insert_unsubscribe_header": True, "allow_risky_contacts": False}
STEP_FIELDS = ["delay", "delay_unit"]

BR_DIV = "<div><br /></div>"
MAYBE_ORPHAN = "{}: this campaign may exist without a recorded id; check by name in Instantly"


def call(method, path, body=None, tok=None):
    return instantly_push.call(method, path, body, tok)


# ---------------------------------------------------------------- HTML
def to_html(plain):
    out = []
    for line in plain.split("\n"):
        out.append(BR_DIV if line == "" else "<div>" + line + "</div>")
    return "".join(out)


def from_html(html):
    lines = []
    rest = html
    while rest:
        if rest.startswith(BR_DIV):
            lines.append("")
            rest = rest[len(BR_DIV):]
        elif rest.startswith("<div>"):
            end = rest.find("</div>")
            if end < 0:
                raise ValueError("unclosed <div> in html")
            lines.append(rest[len("<div>"):end])
            rest = rest[end + len("</div>"):]
        else:
            raise ValueError("unexpected html at: " + rest[:40])
    return "\n".join(lines)


def structure_check(plain, html):
    back = from_html(html)
    assert back == plain, "structure check failed: html does not round-trip to the plain text"
    return True


# ---------------------------------------------------------------- payloads
def load_copy():
    data = json.loads(COPY_FILE.read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


def build_payload(name, copy, template):
    a, b, s2 = to_html(copy["A"]), to_html(copy["B"]), to_html(copy["step2"])
    sched = template["campaign_schedule"]
    schedule = {"schedules": sched["schedules"]}
    for k in ("start_date", "end_date"):
        if sched.get(k) is not None:
            schedule[k] = sched[k]
    body = {"name": name, "campaign_schedule": schedule}
    for k in COPIED_SETTINGS:
        body[k] = template[k]
    body.update(FIXED_SETTINGS)
    body["sequences"] = [{"steps": [
        {"type": "email", "delay": 3, "delay_unit": "days",
         "variants": [{"subject": SUBJECT, "body": a}, {"subject": SUBJECT, "body": b}]},
        {"type": "email", "delay": 3, "delay_unit": "days",
         "variants": [{"subject": "", "body": s2}]},
    ]}]
    return body


def build_all(template, copy=None):
    copy = copy if copy is not None else load_copy()
    out = []
    for name, key, ck in CAMPAIGNS:
        c = copy[ck]
        payload = build_payload(name, c, template)
        steps = payload["sequences"][0]["steps"]
        checks = {
            "A": structure_check(c["A"], steps[0]["variants"][0]["body"]),
            "B": structure_check(c["B"], steps[0]["variants"][1]["body"]),
            "step2": structure_check(c["step2"], steps[1]["variants"][0]["body"]),
        }
        out.append({"name": name, "key": key, "payload": payload, "structure": checks})
    return out


# ---------------------------------------------------------------- live reads
def list_campaigns(tok):
    out, after = [], None
    while True:
        path = "campaigns?limit=100" + ("&starting_after=" + after if after else "")
        d = call("GET", path, tok=tok)
        out += d.get("items", [])
        after = d.get("next_starting_after")
        if not after:
            break
    return out


def existing_conflicts(live):
    names = {c.get("name") for c in live}
    return [n for n, _, _ in CAMPAIGNS if n in names]


def print_before(live):
    print("\nLive campaigns ({}):".format(len(live)))
    for c in sorted(live, key=lambda x: x.get("name") or ""):
        print("  status={}  {}  {}".format(c.get("status"), c.get("id"), c.get("name")))


def preflight(tok):
    live = list_campaigns(tok)
    template = call("GET", "campaigns/" + TEMPLATE_ID, tok=tok)
    clash = existing_conflicts(live)
    if clash:
        print("REFUSING: these campaign names already exist live: " + ", ".join(clash))
        return live, template, None
    built = build_all(template)
    return live, template, built


# ---------------------------------------------------------------- verify
def diff_text(sent, got):
    got = got if isinstance(got, str) else ""
    if sent == got:
        return None
    i = 0
    while i < min(len(sent), len(got)) and sent[i] == got[i]:
        i += 1
    return "differs at char {}: sent ...{!r}... got ...{!r}... (len sent {}, got {})".format(
        i, sent[max(0, i - 30):i + 40], got[max(0, i - 30):i + 40], len(sent), len(got))


def verify_campaign(got, payload):
    """Compare a read-back campaign with the payload that was POSTed. Returns a list of problems."""
    if not isinstance(got, dict):
        return ["read-back is not an object: {!r}".format(got)[:300]]
    problems = []
    if got.get("status") != 0:  # 0 = draft; 1 would mean running
        problems.append("status is {!r}, expected 0".format(got.get("status")))
    for k in COPIED_SETTINGS:
        if k == "email_list":
            if set(got.get(k) or []) != set(payload[k]):
                problems.append("email_list differs from what was sent: got {!r} sent {!r}".format(
                    got.get(k), payload[k]))
        elif got.get(k) != payload[k]:
            problems.append("{} {!r} != sent {!r}".format(k, got.get(k), payload[k]))
    gsched = (got.get("campaign_schedule") or {}).get("schedules")
    ssched = payload["campaign_schedule"]["schedules"]
    if gsched != ssched:
        problems.append("campaign_schedule.schedules differs: got {} sent {}".format(
            json.dumps(gsched, sort_keys=True), json.dumps(ssched, sort_keys=True)))
    try:
        gsteps = got["sequences"][0]["steps"]
    except (KeyError, IndexError, TypeError):
        return problems + ["no sequences returned"]
    if not isinstance(gsteps, list):
        return problems + ["sequence steps is not a list"]
    ssteps = payload["sequences"][0]["steps"]
    if len(gsteps) != len(ssteps):
        problems.append("step count {} != {}".format(len(gsteps), len(ssteps)))
    for si, (ss, gs) in enumerate(zip(ssteps, gsteps)):
        if not isinstance(gs, dict):
            problems.append("step {} is not an object".format(si + 1))
            continue
        for f in STEP_FIELDS:
            if gs.get(f) != ss[f]:
                problems.append("step {} {} {!r} != sent {!r}".format(si + 1, f, gs.get(f), ss[f]))
        gv = gs.get("variants") or []
        if len(gv) != len(ss["variants"]):
            problems.append("step {} variant count {} != {}".format(si + 1, len(gv), len(ss["variants"])))
        for vi, (sv, v) in enumerate(zip(ss["variants"], gv)):
            if not isinstance(v, dict):
                problems.append("step {} variant {} is not an object".format(si + 1, vi + 1))
                continue
            gbody = v.get("body")
            if not isinstance(gbody, str):
                problems.append("step {} variant {} body missing".format(si + 1, vi + 1))
            d = diff_text(sv["body"], gbody)
            if d:
                problems.append("step {} variant {} body {}".format(si + 1, vi + 1, d))
            if (v.get("subject") or "") != sv["subject"]:
                problems.append("step {} variant {} subject {!r} != {!r}".format(
                    si + 1, vi + 1, v.get("subject"), sv["subject"]))
    return problems


# ---------------------------------------------------------------- main
def dry_run(tok):
    live, template, built = preflight(tok)
    if built is None:
        print_before(live)
        return 2
    print("Template: {} ({}) status={}".format(template.get("name"), TEMPLATE_ID, template.get("status")))
    for b in built:
        print("\n=== {} -> {} ===".format(b["name"], b["key"]))
        print(json.dumps(b["payload"], indent=2, ensure_ascii=False))
    print("\nSummary:")
    for b in built:
        ok = all(b["structure"].values())
        print("  {:40s} key={:22s} structure A/B/step2: {}".format(
            b["name"], b["key"], "OK" if ok else "FAIL"))
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    out = TMP_DIR / "dryrun_payloads.json"
    out.write_text(json.dumps({b["key"]: b["payload"] for b in built}, indent=2, ensure_ascii=False))
    print("Payloads written to " + str(out))
    print_before(live)
    print("\nDRY-RUN only. Nothing was created.")
    return 0


def write_ids(ids):
    IDS_FILE.write_text(json.dumps(ids, indent=2) + "\n")


def apply(tok):
    live, template, built = preflight(tok)
    if built is None:
        print_before(live)
        return 2
    ts = time.strftime("%Y%m%dT%H%M%S")
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    before = [{"id": c.get("id"), "name": c.get("name"), "status": c.get("status")} for c in live]
    snap = TMP_DIR / "before_{}.json".format(ts)
    snap.write_text(json.dumps(before, indent=2))
    print("Before snapshot: " + str(snap))
    print_before(live)

    ids = {}
    if IDS_FILE.exists():
        ids = json.loads(IDS_FILE.read_text())
    created = []
    for b in built:
        try:
            resp = call("POST", "campaigns", b["payload"], tok=tok)
        except (SystemExit, Exception) as e:  # HTTP error, timeout, network, bad JSON
            print("POST failed for {}: {}: {}".format(b["name"], type(e).__name__, e))
            print("Created so far: " + json.dumps({k: ids[k] for k in created}))
            print(MAYBE_ORPHAN.format(b["name"]))
            return 3
        cid = resp.get("id") if isinstance(resp, dict) else None
        if not cid:
            print("POST for {} returned no id: {}".format(b["name"], repr(resp)[:300]))
            print("Created so far: " + json.dumps({k: ids[k] for k in created}))
            print(MAYBE_ORPHAN.format(b["name"]))
            return 3
        ids[b["key"]] = cid
        created.append(b["key"])
        write_ids(ids)
        print("created {} -> {}".format(b["name"], cid))

    results = {}
    fail = False
    for b in built:
        try:
            got = call("GET", "campaigns/" + ids[b["key"]], tok=tok)
        except (SystemExit, Exception) as e:
            problems = ["read-back GET failed ({}: {}); unverified".format(type(e).__name__, e)]
        else:
            problems = verify_campaign(got, b["payload"])
        results[b["key"]] = problems
        print("{} {}".format("PASS" if not problems else "FAIL", b["name"]))
        for p in problems:
            print("    " + p)
            fail = True

    relist_error = None
    changed = []
    try:
        after = {c.get("id"): c.get("status") for c in list_campaigns(tok)}
    except (SystemExit, Exception) as e:
        relist_error = "re-list GET failed ({}: {}); pre-existing statuses unverified".format(type(e).__name__, e)
        print("FAIL " + relist_error)
    else:
        changed = [(c["name"], c["status"], after.get(c["id"])) for c in before if after.get(c["id"]) != c["status"]]
        for n, s0, s1 in changed:
            print("PRE-EXISTING STATUS CHANGED: {} {} -> {}".format(n, s0, s1))
        print("Pre-existing campaigns unchanged: " + ("yes" if not changed else "NO"))

    lines = ["# APPLIED", "", "Applied: " + ts, "Before snapshot: " + str(snap), "", "| campaign | key | id | verify |",
             "|---|---|---|---|"]
    for b in built:
        p = results[b["key"]]
        lines.append("| {} | {} | {} | {} |".format(b["name"], b["key"], ids[b["key"]],
                                                   "PASS" if not p else "FAIL: " + "; ".join(p)))
    if relist_error:
        unchanged = "UNVERIFIED: " + relist_error
    else:
        unchanged = "yes" if not changed else "NO " + repr(changed)
    lines += ["", "Pre-existing campaign statuses unchanged: " + unchanged, ""]
    APPLIED_FILE.write_text("\n".join(lines))
    return 3 if (fail or changed or relist_error) else 0


def is_live():
    """Same rule as shared.settings.is_live(): MODE=live and ALLOW_LIVE_WRITES=1.

    Checked here directly: importing shared.settings would also load .env files.
    """
    return os.environ.get("MODE", "shadow") == "live" and os.environ.get("ALLOW_LIVE_WRITES") == "1"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="read-only, GETs only (the default)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args(argv)
    if args.apply and args.dry_run:
        print("REFUSING: --dry-run and --apply together")
        return 2
    if args.apply:
        if not args.yes:
            print("REFUSING: --apply needs --yes")
            return 2
        if not is_live():
            print("REFUSING --apply: needs MODE=live and ALLOW_LIVE_WRITES=1 in the environment")
            return 2
        return apply(instantly_push.key())
    return dry_run(instantly_push.key())


if __name__ == "__main__":
    sys.exit(main())
