#!/usr/bin/env python3
"""Deliverability change-set of 2026-09-25 for the six 2026 cold campaigns.

Three changes, all reversible (README.md in this folder is the runbook):

  A. remove the three proadvero.com inboxes from every campaign's email_list
     (placement test 01a0dac3-e227-7eb6-8334-f0a75795b689: 7/7 Gmail seeds in
     spam), then record them in the capacity.quarantine ledger;
  B. set allow_risky_contacts=false on every campaign (same PATCH as A);
  C. park every active, never-replied Microsoft-hosted lead of the six
     campaigns in the lead list "Parked - Microsoft recipients 2026-09-25",
     with a manifest written BEFORE the first move.

Modes (run from "Agentic Worklfows/"):

    python3 changesets/deliverability_2026_09_25/apply_deliverability.py              # dry-run (default)
    MODE=live ALLOW_LIVE_WRITES=1 python3 .../apply_deliverability.py --apply [--yes]
    python3 .../apply_deliverability.py --restore-leads                               # dry-run
    MODE=live ALLOW_LIVE_WRITES=1 python3 .../apply_deliverability.py --restore-leads --apply
    MODE=live ALLOW_LIVE_WRITES=1 python3 .../apply_deliverability.py \\
        --restore changesets/backups/deliverability_2026_09_25_<id>_<ts>.json --campaign <key>

The dry-run only reads (GET campaigns, GET lead-lists, POST leads/list, which
is a read) and writes the planned manifest to a DRYRUN-suffixed file. Every
live write goes through shared.instantly, which calls settings.guard_write
first. Refusals, before anything is written: a campaign that is not paused
(status 2), an email_list that is neither the recorded 12 nor the target 9,
a lead pull that did not finish, an existing manifest that cannot be read, a
before-image that could not be written.

Lead moves are checked from live state, never from a job's word alone. The
first move of a run is a 1-lead canary. Before each batch the source campaign
is read again and only leads that still pass the selection rules are sent;
after each job the campaign and the parked list are read again, the job's
own moved count and emails are compared with the batch, and any lead that
left the campaign without being in the batch stops the run (it is recorded
in the manifest so --restore-leads can bring it back). Every manifest write
is copied to <main checkout>/.tmp/deliverability_2026_09_25/.

Exit codes: 0 ok, 1 refused by a check, 2 live write refused, 3 API error.
"""
import argparse
import csv
import json
import logging
import os
import shutil
import sys
from collections import OrderedDict
from datetime import timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from shared import settings  # noqa: E402
from shared.instantly import default_client, InstantlyError  # noqa: E402
from shared.job_log import log_run  # noqa: E402
from shared.paths import tmp_dir  # noqa: E402
from changesets import rollback as R  # noqa: E402

logger = logging.getLogger("changesets.deliverability_2026_09_25")

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_REFUSED = 2
EXIT_API = 3

JOB = "deliverability_2026_09_25"
SCRIPT = "deliverability_2026_09_25"
BACKUP_DIR = os.path.join(ROOT, "changesets", "backups")
MANIFEST_DIR = os.path.join(HERE, "manifests")
MANIFEST_STEM = "parked_leads_2026-09-25"

CAMPAIGNS = OrderedDict([
    ("f347604e-48c7-4813-831c-dc7b9d4b50ae", "2026 Cleaning - Trigger Outbound"),
    ("f00c5e28-fdc4-4d84-a7e6-dfba9695f35d", "2026 Bookkeeping - Client Reactivation"),
    ("cd2e251c-3b5a-40d2-a3dc-d07c4004a48c", "2026 Recruiting - Outbound (specialty roles)"),
    ("87ebb167-9b64-4b6f-b658-88f3d1af9980", "2026 Bookkeeping - Trigger Outbound"),
    ("8086b41e-b546-4b36-9fa0-2d01f5cc119a", "2026 Cleaning - Client Reactivation"),
    ("1d4d5bb3-40a7-4333-bf34-b269d2cc9955", "2026 Recruiting - Client Reactivation"),
])
_LOCALS = ("lorenzo", "lorenzov", "lorenzovillarreal")
_DOMAINS = ("adveromedia.com", "myadvero.com", "proadvero.com", "theadvero.com")
RECORDED_EMAIL_LIST = sorted("%s@%s" % (l, d) for d in _DOMAINS for l in _LOCALS)
REMOVE = sorted("%s@proadvero.com" % l for l in _LOCALS)
TARGET_EMAIL_LIST = sorted(set(RECORDED_EMAIL_LIST) - set(REMOVE))

PLACEMENT_TEST_ID = "01a0dac3-e227-7eb6-8334-f0a75795b689"
QUARANTINE_REASON = "proadvero.com 7/7 Gmail seed spam 2026-09-25 (test %s)" % PLACEMENT_TEST_ID
PARKED_LIST_NAME = "Parked - Microsoft recipients 2026-09-25"

PAUSED = 2
LEAD_ACTIVE = 1
ESP_MICROSOFT = 2          # Instantly esp_code: 1 Google, 2 Microsoft, 999 other

MOVE_BATCH = 100
POLL_INTERVAL = 3.0
MAX_POLLS = 400            # 20 minutes per job at 3 s
MAX_BAD_POLLS = 3          # consecutive 4xx answers on the job GET before giving up
JOB_DATA_FIELDS = "moved_leads,moved_lead_emails"
CONFLICT_WAIT = 15.0       # a 409 means another move job is running
CONFLICT_RETRIES = 8
JOB_SUCCESS = ("success",)
JOB_FINAL_BAD = ("failed", "cancelled")

PLAN_COLUMNS = [
    "lead_id", "email", "first_name", "last_name", "company_name", "website", "campaign_id",
    "campaign_name", "status", "esp_code", "esg_code", "stage", "last_step_from", "last_step_id",
    "last_step_at", "email_reply_count", "personalization", "destination_list_id",
    "destination_list_name", "planned_at",
]
APPLY_COLUMNS = ["move_job_id", "moved_at", "verified_in_list", "verified_not_in_campaign", "skip_reason"]
RESTORE_COLUMNS = ["restore_job_id", "restored_at"]
COLUMNS = PLAN_COLUMNS + APPLY_COLUMNS + RESTORE_COLUMNS


# ------------------------------------------------------------------ campaigns
def _norm(emails: Any) -> List[str]:
    return sorted(str(e).strip().lower() for e in (emails or []))


def plan_campaign(campaign: Dict[str, Any]) -> Dict[str, Any]:
    """What A and B need for one live campaign, and why it must not run.

    ``patch`` holds only the fields live does not already hold, so a re-run
    after a partial apply PATCHes nothing it has already changed."""
    cid = campaign.get("id")
    plan = {"id": cid, "name": campaign.get("name") or CAMPAIGNS.get(cid), "problems": [],
            "patch": {}, "email_list_state": None, "risky_state": None,
            "live_email_list": campaign.get("email_list"),
            "live_risky": campaign.get("allow_risky_contacts"), "status": campaign.get("status")}
    try:
        status = int(campaign.get("status"))
    except (TypeError, ValueError):
        status = None
    if status != PAUSED:
        plan["problems"].append("status is %r, not 2 (paused): this change-set only runs on paused "
                                "campaigns" % campaign.get("status"))
    live = campaign.get("email_list")
    if not isinstance(live, list):
        plan["problems"].append("the live read carries no email_list list; a PATCH built from it "
                                "could wipe the campaign")
    elif _norm(live) == TARGET_EMAIL_LIST:
        plan["email_list_state"] = "already applied"
    elif _norm(live) == RECORDED_EMAIL_LIST:
        new = [e for e in live if str(e).strip().lower() not in REMOVE]
        if _norm(new) != TARGET_EMAIL_LIST or len(new) != len(live) - len(REMOVE):
            plan["problems"].append("live minus the 3 proadvero.com inboxes is not the 9-inbox "
                                    "target list")
        else:
            plan["patch"]["email_list"] = new
            plan["email_list_state"] = "change"
    else:
        have = set(_norm(live))
        plan["problems"].append(
            "email_list drift: live holds %d inboxes, neither the recorded 12 nor the target 9 "
            "(extra %s, missing %s). Nothing is changed for a list nobody reviewed."
            % (len(live), sorted(have - set(RECORDED_EMAIL_LIST)) or "nothing",
               sorted(set(RECORDED_EMAIL_LIST) - have) or "nothing"))
    if campaign.get("allow_risky_contacts") is False:
        plan["risky_state"] = "already applied"
    else:
        plan["patch"]["allow_risky_contacts"] = False
        plan["risky_state"] = "change"
    return plan


def _verify_campaign(campaign: Dict[str, Any]) -> List[str]:
    bad = []
    if _norm(campaign.get("email_list")) != TARGET_EMAIL_LIST:
        bad.append("email_list is %d inboxes, not the target 9" % len(campaign.get("email_list") or []))
    if campaign.get("allow_risky_contacts") is not False:
        bad.append("allow_risky_contacts is %r" % campaign.get("allow_risky_contacts"))
    return bad


# ---------------------------------------------------------------------- leads
def exclusion_reason(lead: Dict[str, Any], campaign_ids) -> Optional[str]:
    """None when the lead is parked, else the first rule it fails."""
    if lead.get("campaign") not in campaign_ids:
        return "other_campaign"
    if lead.get("status") != LEAD_ACTIVE:
        return "not_active"
    if lead.get("esp_code") != ESP_MICROSOFT:
        return "not_microsoft"
    if lead.get("email_reply_count") not in (0, None):
        return "replied"
    if lead.get("lt_interest_status") is not None:
        return "interest_set"
    return None


def select_leads(leads: List[Dict[str, Any]], campaign_ids=None) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """(parked leads in campaign order, count of exclusions by reason).
    Deduplicated by id; the campaign filter is re-applied here because
    leads/list has been seen to ignore it."""
    campaign_ids = list(campaign_ids or CAMPAIGNS.keys())
    seen = set()
    picked = []  # type: List[Dict[str, Any]]
    excluded = {}  # type: Dict[str, int]
    for lead in leads:
        lid = lead.get("id")
        if not lid or lid in seen:
            continue
        seen.add(lid)
        why = exclusion_reason(lead, campaign_ids)
        if why is None:
            picked.append(lead)
        elif why != "other_campaign":
            excluded[why] = excluded.get(why, 0) + 1
    order = dict((c, i) for i, c in enumerate(campaign_ids))
    picked.sort(key=lambda l: (order.get(l.get("campaign"), 99), (l.get("email") or "").lower()))
    return picked, excluded


def _last_step(lead: Dict[str, Any]) -> Dict[str, Any]:
    summary = lead.get("status_summary")
    step = summary.get("lastStep") if isinstance(summary, dict) else None
    return step if isinstance(step, dict) else {}


def stage_of(lead: Dict[str, Any]) -> str:
    return "mid_sequence" if _last_step(lead) else "not_started"


def manifest_row(lead: Dict[str, Any], list_id: Optional[str], planned_at: str) -> Dict[str, Any]:
    step = _last_step(lead)
    row = dict((c, "") for c in COLUMNS)
    row.update({
        "lead_id": lead.get("id"), "email": lead.get("email"), "first_name": lead.get("first_name"),
        "last_name": lead.get("last_name"), "company_name": lead.get("company_name"),
        "website": lead.get("website"), "campaign_id": lead.get("campaign"),
        "campaign_name": CAMPAIGNS.get(lead.get("campaign"), ""), "status": lead.get("status"),
        "esp_code": lead.get("esp_code"), "esg_code": lead.get("esg_code"), "stage": stage_of(lead),
        "last_step_from": step.get("from"), "last_step_id": step.get("stepID") or step.get("step_id"),
        "last_step_at": step.get("timestamp_executed") or step.get("timestamp"),
        "email_reply_count": lead.get("email_reply_count"),
        "personalization": lead.get("personalization"),
        "destination_list_id": list_id or "", "destination_list_name": PARKED_LIST_NAME,
        "planned_at": planned_at,
    })
    return dict((k, "" if v is None else v) for k, v in row.items())


def pull_leads(client, campaign_ids, out) -> List[Dict[str, Any]]:
    """Every lead the six campaign-filtered pulls return. When a pull comes
    back holding leads of other campaigns the filter is being ignored, that
    pull already is the whole workspace, and the other five are skipped."""
    leads = []  # type: List[Dict[str, Any]]
    for cid in campaign_ids:
        walk = client.iterate("leads/list", body={"campaign": cid, "limit": 100}, max_pages=2000)
        rows = list(walk)
        if walk.truncated or not walk.complete:
            raise InstantlyError("leads/list for campaign %s stopped before its last page; a partial "
                                 "pull cannot be a plan" % cid)
        leads.extend(rows)
        foreign = sum(1 for r in rows if r.get("campaign") != cid)
        if foreign:
            out("  leads/list ignored the campaign filter (%d of %d rows from other campaigns); "
                "that pull is the whole workspace, filtering client-side" % (foreign, len(rows)))
            return leads
    return leads


def find_list(client, name: str) -> Optional[Dict[str, Any]]:
    for item in client.iterate("lead-lists", params={"search": name, "limit": 100}, max_pages=50):
        if (item.get("name") or "") == name:
            return item
    return None


# ------------------------------------------------------------------- manifest
def manifest_paths(directory: str, dryrun: bool) -> Tuple[str, str]:
    stem = MANIFEST_STEM + (".DRYRUN" if dryrun else "")
    return os.path.join(directory, stem + ".csv"), os.path.join(directory, stem + ".json")


def default_mirror_dir() -> str:
    """Outside the repo: <main checkout>/.tmp/deliverability_2026_09_25 (the
    main checkout, also when this runs from a worktree). A test session gets a
    directory under its own tmp tree instead."""
    if settings.running_under_pytest():
        return str(tmp_dir() / "deliverability_manifest_mirror")
    root = Path(settings.ROOT_DIR)
    if root.parent.name == ".worktrees":
        root = root.parent.parent
    return str(root / ".tmp" / "deliverability_2026_09_25")


def write_manifest(directory: str, rows: List[Dict[str, Any]], meta: Dict[str, Any],
                   dryrun: bool = False, mirror_dir: Optional[str] = None) -> Tuple[str, str]:
    """Write the CSV and JSON atomically, then copy both to ``mirror_dir``.
    A failed copy is logged; it never stops a run halfway."""
    os.makedirs(directory, exist_ok=True)
    csv_path, json_path = manifest_paths(directory, dryrun)
    for path, writer in ((json_path, _write_json), (csv_path, _write_csv)):
        tmp = path + ".tmp"
        writer(tmp, rows, meta)
        os.replace(tmp, path)
    if mirror_dir:
        try:
            os.makedirs(mirror_dir, exist_ok=True)
            for path in (csv_path, json_path):
                shutil.copy2(path, os.path.join(mirror_dir, os.path.basename(path)))
        except OSError as exc:
            logger.warning("manifest mirror copy to %s failed: %s", mirror_dir, exc)
    return csv_path, json_path


def _write_json(path, rows, meta) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"meta": meta, "rows": rows}, fh, indent=1, ensure_ascii=False, default=str)
        fh.write("\n")


def _write_csv(path, rows, meta) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def load_manifest(directory: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Raises FileNotFoundError when there is no apply manifest and
    ValueError when there is one that cannot be trusted. Only the first
    means "start a new one"."""
    _, json_path = manifest_paths(directory, False)
    with open(json_path, "r", encoding="utf-8") as fh:
        text = fh.read()
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ValueError("%s is not valid JSON (%s)" % (json_path, exc))
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list):
        raise ValueError("%s has no rows list" % json_path)
    rows = data["rows"]
    for n, row in enumerate(rows):
        if not isinstance(row, dict) or not row.get("lead_id") or not row.get("campaign_id"):
            raise ValueError("%s row %d has no lead_id or campaign_id" % (json_path, n))
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    return meta, rows


# ---------------------------------------------------------------- live reads
def campaign_members(client, cid: str) -> Dict[str, Dict[str, Any]]:
    """{id: lead} for every lead whose ``campaign`` is ``cid`` now. Raises on
    a pull that did not finish: a partial read is never a verdict."""
    walk = client.iterate("leads/list", body={"campaign": cid, "limit": 100}, max_pages=2000)
    rows = list(walk)
    if walk.truncated or not walk.complete:
        raise InstantlyError("leads/list for campaign %s stopped before its last page" % cid)
    return dict((r["id"], r) for r in rows if r.get("id") and r.get("campaign") == cid)


def list_membership(client, list_id: str) -> set:
    """Ids the server returns for leads/list {list_id}. Live leads carry no
    ``list_id`` field, so membership is what the filtered read returns. A
    lead in a list has no campaign; if the read returns leads that sit in a
    campaign, the filter is being ignored and membership cannot be known."""
    walk = client.iterate("leads/list", body={"list_id": list_id, "limit": 100}, max_pages=2000)
    rows = list(walk)
    if walk.truncated or not walk.complete:
        raise InstantlyError("leads/list for list %s stopped before its last page" % list_id)
    stray = sum(1 for r in rows if r.get("campaign"))
    if stray:
        raise InstantlyError("leads/list {list_id: %s} returned %d leads that sit in a campaign: the "
                             "list filter looks ignored, so list membership cannot be read" % (list_id, stray))
    return set(r["id"] for r in rows if r.get("id"))


# ---------------------------------------------------------------- move engine
def wait_for_job(client, job_id: str, sleep: Callable[[float], None]) -> Dict[str, Any]:
    """Poll until success, failed or cancelled. Gives up after MAX_POLLS
    (status "timeout") or after MAX_BAD_POLLS consecutive 4xx answers
    (status "unreadable")."""
    job = {}  # type: Dict[str, Any]
    bad = 0
    for _ in range(MAX_POLLS):
        try:
            job = client.get_background_job(job_id, data_fields=JOB_DATA_FIELDS) or {}
            bad = 0
        except InstantlyError as exc:
            job = {"id": job_id, "status": "unreadable", "error": str(exc)[:200]}
            code = getattr(exc, "status_code", None)
            if code is not None and 400 <= code < 500:
                bad += 1
                if bad >= MAX_BAD_POLLS:
                    return job
            sleep(POLL_INTERVAL)
            continue
        status = str(job.get("status") or "")
        if status in JOB_SUCCESS or status in JOB_FINAL_BAD:
            return job
        sleep(POLL_INTERVAL)
    return dict(job, status="timeout")


def job_data_problem(job: Optional[Dict[str, Any]], sent: List[str],
                     emails: Dict[str, str]) -> Optional[str]:
    """Compare the job's own count and email list with what was sent."""
    data = (job or {}).get("data")
    if not isinstance(data, dict):
        return None
    moved = data.get("moved_leads")
    if isinstance(moved, (int, float)) and int(moved) != len(sent):
        return "the job reports %d moved leads; the call sent %d" % (int(moved), len(sent))
    got = data.get("moved_lead_emails")
    want = set((emails.get(i) or "").strip().lower() for i in sent)
    if isinstance(got, list) and "" not in want:
        got_set = set(str(e).strip().lower() for e in got)
        if got_set != want:
            return ("the job's moved emails differ from the batch: %d not in the batch, %d of the "
                    "batch missing" % (len(got_set - want), len(want - got_set)))
    return None


def move_batch(client, ids: List[str], source: Dict[str, str], dest: Dict[str, str],
               in_source: Callable[[], set], sleep: Callable[[float], None], out) -> Dict[str, Any]:
    """Send one move job for ``ids`` (<= 100) and wait for it.

    After ANY error ``in_source()`` is read again and only the leads still in
    the source are sent again, so nothing is moved twice. 409 (another move
    job running) and 429 wait and retry; any other error stops. A read that
    fails after an error returns ``unknown``. The caller verifies the result
    from live state either way; ``ok`` here only says the job ended well."""
    remaining = list(ids)
    attempts = 0
    while True:
        try:
            resp = client.move_leads(remaining, limit=len(remaining), **dict(source, **dest))
        except InstantlyError as exc:
            code = getattr(exc, "status_code", None)
            try:
                still = in_source()
            except InstantlyError as exc2:
                return {"ok": False, "job_status": "unknown", "sent": remaining, "job": None, "job_id": None,
                        "error": "move raised (%s) and the re-read failed too (%s)" % (str(exc)[:150], str(exc2)[:150])}
            remaining = [i for i in remaining if i in still]
            if not remaining:
                out("    move raised (%s) but a re-read shows no lead of the batch left in the source"
                    % str(exc)[:120])
                return {"ok": True, "job_status": "moved_despite_error", "sent": [], "job": None,
                        "job_id": None, "error": None}
            if code in (409, 429) and attempts < CONFLICT_RETRIES:
                attempts += 1
                out("    HTTP %s on leads/move; %d leads still in the source; waiting %.0fs (retry %d/%d)"
                    % (code, len(remaining), CONFLICT_WAIT * attempts, attempts, CONFLICT_RETRIES))
                sleep(CONFLICT_WAIT * attempts)
                continue
            return {"ok": False, "job_status": "error", "sent": remaining, "job": None, "job_id": None,
                    "error": str(exc)[:300]}
        if isinstance(resp, dict) and resp.get("shadow"):
            return {"ok": False, "job_status": "shadow", "sent": remaining, "job": None, "job_id": None,
                    "error": "guard_write returned a shadow record; nothing was sent"}
        job_id = resp.get("id") if isinstance(resp, dict) else None
        if not job_id:
            return {"ok": False, "job_status": "no_job_id", "sent": remaining, "job": None, "job_id": None,
                    "error": "the move answer carries no job id: %r" % (resp,)}
        job = wait_for_job(client, job_id, sleep)
        status = str(job.get("status"))
        return {"ok": status in JOB_SUCCESS, "job_status": status, "sent": remaining, "job": job,
                "job_id": job_id, "error": None if status in JOB_SUCCESS else "job %s ended %s" % (job_id, status)}


# ----------------------------------------------------------------------- main
def _say(msg: str) -> None:
    print(msg)


def _iso(now) -> str:
    return now.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def main(argv: Optional[List[str]] = None, client=None, now=None, backup_dir: Optional[str] = None,
         manifest_dir: Optional[str] = None, confirm=None, sleep: Optional[Callable[[float], None]] = None,
         store=None, out: Callable[[str], None] = _say, mirror_dir: Optional[str] = None) -> int:
    p = argparse.ArgumentParser(prog="apply_deliverability", description=__doc__.split("\n\n")[0])
    p.add_argument("--dry-run", action="store_true", help="explicit dry-run (the default)")
    p.add_argument("--apply", action="store_true", help="perform the writes (needs the live flags)")
    p.add_argument("--yes", action="store_true", help="skip the typed confirmation")
    p.add_argument("--restore-leads", action="store_true",
                   help="move parked leads back to their campaigns (dry-run unless --apply)")
    p.add_argument("--limit", type=int, help="with --restore-leads: restore only the first N rows still parked")
    p.add_argument("--restore", metavar="ROLLBACK_POINT",
                   help="PATCH a campaign rollback point back (live only, needs --campaign)")
    p.add_argument("--campaign", help="campaign key from config/ids.json (with --restore)")
    p.add_argument("--override-later-changes", action="store_true",
                   help="with --restore: restore even though the fields changed after the apply; never with --yes")
    args = p.parse_args(argv)
    now = now or R.utcnow()
    backup_dir = backup_dir or BACKUP_DIR
    manifest_dir = manifest_dir or MANIFEST_DIR
    mirror_dir = mirror_dir or default_mirror_dir()
    import time as _time
    sleep = sleep or _time.sleep

    if args.restore and (args.dry_run or args.apply or args.restore_leads):
        out("REFUSED: --restore runs alone (with --campaign); it cannot be combined with --dry-run, "
            "--apply or --restore-leads.")
        return EXIT_REFUSED
    if args.dry_run and args.apply:
        out("REFUSED: --dry-run cannot be combined with --apply.")
        return EXIT_REFUSED
    if args.limit is not None and (not args.restore_leads or args.limit < 1):
        out("REFUSED: --limit takes a number >= 1 and only goes with --restore-leads.")
        return EXIT_REFUSED
    if R.override_with_yes(args):
        out(R.OVERRIDE_WITH_YES)
        return EXIT_REFUSED
    if args.restore:
        return _restore_campaign(args, client, now, backup_dir, confirm)
    if client is None:
        try:
            client = default_client()
        except InstantlyError as exc:
            print("Instantly client: %s" % exc, file=sys.stderr)
            return EXIT_API
    ctx = {"client": client, "now": now, "backup_dir": backup_dir, "manifest_dir": manifest_dir,
           "mirror_dir": mirror_dir, "confirm": confirm, "sleep": sleep, "store": store, "out": out}
    if args.restore_leads:
        if args.apply:
            return _restore_leads(args, ctx)
        with R.scratch_logs(JOB + "_restore_dryrun"):
            return _restore_leads(args, ctx)
    if args.apply:
        return _run(args, ctx)
    with R.scratch_logs(JOB + "_dryrun"):
        return _run(args, ctx)


def _read_plan(client, out) -> Dict[str, Any]:
    campaigns = OrderedDict()
    for cid in CAMPAIGNS:
        campaigns[cid] = client.get_campaign(cid)
    plans = [plan_campaign(c) for c in campaigns.values()]
    parked = find_list(client, PARKED_LIST_NAME)
    leads = pull_leads(client, list(CAMPAIGNS), out)
    picked, excluded = select_leads(leads)
    return {"campaigns": campaigns, "plans": plans, "list": parked, "picked": picked,
            "excluded": excluded, "pulled": len(set(l.get("id") for l in leads))}


def _counts(picked) -> Dict[str, Dict[str, int]]:
    counts = OrderedDict((cid, {"not_started": 0, "mid_sequence": 0}) for cid in CAMPAIGNS)
    for lead in picked:
        counts[lead["campaign"]][stage_of(lead)] += 1
    return counts


def _print_plan(plan: Dict[str, Any], out) -> None:
    out("CHANGE-SET  deliverability 2026-09-25 (placement test %s)" % PLACEMENT_TEST_ID)
    out("")
    out("A + B: campaigns")
    for cp in plan["plans"]:
        out("[%s] %s  status=%s" % (cp["id"], cp["name"], cp["status"]))
        live = cp["live_email_list"] if isinstance(cp["live_email_list"], list) else []
        if cp["email_list_state"] == "change":
            out("  " + R.describe_field_change("email_list", live, cp["patch"]["email_list"]))
        elif cp["email_list_state"] == "already applied":
            out("  email_list already applied (%d inboxes, no proadvero.com)" % len(live))
        if cp["risky_state"] == "change":
            out("  allow_risky_contacts %r -> False" % cp["live_risky"])
        else:
            out("  allow_risky_contacts already False")
        for problem in cp["problems"]:
            out("  PROBLEM: %s" % problem)
    out("")
    out("C: park Microsoft-hosted leads (status 1, esp_code 2, no reply, no interest status)")
    lst = plan["list"]
    out("  destination list %r: %s" % (PARKED_LIST_NAME, ("exists, id %s" % lst["id"]) if lst
                                        else "does not exist yet (created on --apply)"))
    out("  leads read: %d unique; excluded from the six campaigns: %s"
        % (plan["pulled"], ", ".join("%s %d" % (k, v) for k, v in sorted(plan["excluded"].items())) or "none"))
    out("  %-46s %12s %13s %6s" % ("campaign", "not_started", "mid_sequence", "total"))
    tot = [0, 0]
    for cid, c in _counts(plan["picked"]).items():
        tot[0] += c["not_started"]
        tot[1] += c["mid_sequence"]
        out("  %-46s %12d %13d %6d" % (CAMPAIGNS[cid][:46], c["not_started"], c["mid_sequence"],
                                        c["not_started"] + c["mid_sequence"]))
    out("  %-46s %12d %13d %6d" % ("TOTAL", tot[0], tot[1], tot[0] + tot[1]))
    out("  on --apply: the first move is a 1-lead canary; every batch is re-read before it is sent "
        "and verified before the next one")


def _run(args, ctx) -> int:
    client, out = ctx["client"], ctx["out"]
    try:
        plan = _read_plan(client, out)
    except InstantlyError as exc:
        out("Instantly read failed: %s" % exc)
        log_run(JOB, "error", {"error": str(exc)[:300]})
        return EXIT_API
    _print_plan(plan, out)
    problems = [(cp["id"], p) for cp in plan["plans"] for p in cp["problems"]]
    counts = _counts(plan["picked"])
    if problems:
        out("")
        out("REFUSED, %d problem(s); nothing was written:" % len(problems))
        for cid, problem in problems:
            out("  - %s: %s" % (cid, problem))
        log_run(JOB, "refused", {"problems": ["%s: %s" % x for x in problems]})
        return EXIT_INVALID

    planned_at = _iso(ctx["now"])
    list_id = (plan["list"] or {}).get("id")
    rows = [manifest_row(l, list_id, planned_at) for l in plan["picked"]]
    meta = {"change_set": SCRIPT, "list_name": PARKED_LIST_NAME, "list_id": list_id,
            "planned_at": planned_at, "counts": counts}

    if not args.apply:
        csv_path, json_path = write_manifest(ctx["manifest_dir"], rows, dict(meta, dry_run=True), dryrun=True,
                                             mirror_dir=ctx["mirror_dir"])
        out("")
        out("planned manifest (dry-run, lead PII, git-ignored): %s" % csv_path)
        out("  copy outside the repo: %s" % os.path.join(ctx["mirror_dir"], os.path.basename(csv_path)))
        out("apply manifest will be: %s" % manifest_paths(ctx["manifest_dir"], False)[0])
        out("")
        out("dry-run only: no write was sent. Apply with MODE=live ALLOW_LIVE_WRITES=1 and --apply.")
        log_run(JOB, "dry_run_ok", {"counts": counts, "manifest": json_path,
                                     "campaign_patches": dict((cp["id"], sorted(cp["patch"]))
                                                              for cp in plan["plans"])})
        return EXIT_OK

    if not settings.is_live():
        out("--apply refused: MODE=%s and the live-writes flag is not set. Nothing was sent."
            % settings.get_mode())
        log_run(JOB, "live_refused", {"mode": settings.get_mode()})
        return EXIT_REFUSED
    # The manifest must be readable before anything live changes.
    try:
        load_manifest(ctx["manifest_dir"])
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as exc:
        out("REFUSED: the existing manifest cannot be read (%s). Nothing was written. Check it, "
            "move it aside only if it holds no parked leads, and re-run." % exc)
        log_run(JOB, "refused", {"error": "manifest unreadable: %s" % str(exc)[:200]})
        return EXIT_INVALID
    if not args.yes:
        answer = (ctx["confirm"] or input)("Apply A, B and C to the live workspace? type yes: ").strip().lower()
        if answer != "yes":
            out("aborted")
            return EXIT_REFUSED

    code = _apply_campaigns(client, plan, ctx["now"], ctx["backup_dir"], out)
    if code != EXIT_OK:
        return code
    _quarantine(ctx["now"], ctx["store"], out)
    return _apply_leads(plan, rows, meta, ctx)


def _apply_campaigns(client, plan, now, backup_dir, out) -> int:
    # Re-read after the prompt: a campaign that moved while it was open is
    # never PATCHed from the old read.
    fresh = OrderedDict()
    for cid in CAMPAIGNS:
        try:
            fresh[cid] = client.get_campaign(cid)
        except InstantlyError as exc:
            out("could not re-read %s after the confirmation: %s; nothing was sent" % (cid, exc))
            return EXIT_API
        before = plan["campaigns"][cid]
        for key in ("email_list", "allow_risky_contacts", "status"):
            if not R.field_equal(key, before.get(key), fresh[cid].get(key)):
                out("REFUSED: %s of %s changed while the confirmation was open; nothing was sent" % (key, cid))
                log_run(JOB, "refused", {"error": "%s moved during confirmation" % key, "campaign_id": cid})
                return EXIT_REFUSED

    todo = [cp for cp in plan["plans"] if cp["patch"]]
    preapply = {}  # type: Dict[str, str]
    for cp in todo:
        cid = cp["id"]
        try:
            preapply[cid] = R.write_point(
                backup_dir, "%s_%s_%s" % (SCRIPT, cid, R.stamp(now)),
                R.build_point(SCRIPT, R.KIND_PREAPPLY, fresh[cid], sorted(cp["patch"]), now, cid,
                              R.campaign_key_for(cid), extra={"placement_test": PLACEMENT_TEST_ID},
                              after=cp["patch"]))
        except (OSError, ValueError) as exc:
            out("REFUSED: the before-image of %s could not be written (%s); nothing was sent." % (cid, exc))
            for path in preapply.values():
                R.relabel(path, R.KIND_NOT_APPLIED, outcome="not_sent", note="a later backup failed")
            log_run(JOB, "refused", {"error": "backup failed: %s" % exc, "campaign_id": cid})
            return EXIT_REFUSED

    out("")
    for i, cp in enumerate(todo):
        cid = cp["id"]
        before = dict((k, fresh[cid].get(k)) for k in cp["patch"])
        settled = R.patch_and_settle(client, cid, cp["patch"], preapply[cid], before)
        out("[%s] %s" % (cid, R.describe_outcome(settled)))
        try:
            bad = _verify_campaign(client.get_campaign(cid))
        except InstantlyError as exc:
            bad = ["verifying re-read failed: %s" % exc]
        if not settled["ok"] or bad:
            out("STOPPED at %s: %s. The campaigns after it were not touched; leads were not moved."
                % (cid, "; ".join(bad) or settled.get("error")))
            for later in todo[i + 1:]:
                R.relabel(preapply[later["id"]], R.KIND_NOT_APPLIED, outcome="not_sent",
                          note="an earlier campaign PATCH failed")
            log_run(JOB, "apply_stopped", {"campaign_id": cid, "outcome": settled["outcome"],
                                           "error": settled.get("error"), "verify": bad})
            return EXIT_API
        out("  verified: email_list is the 9 target inboxes and allow_risky_contacts is False")
    for cid in CAMPAIGNS:
        if cid not in preapply:
            out("[%s] A and B already applied; no PATCH sent" % cid)
    log_run(JOB, "campaigns_applied", {"patched": sorted(preapply), "rollback_points": sorted(preapply.values())})
    return EXIT_OK


def _quarantine(now, store, out) -> None:
    """Record the three inboxes in capacity.quarantine (the local store of
    whichever checkout runs this). An inbox already in the ledger keeps its
    entry and its ``since``. Never pauses them, never touches warm-up."""
    try:
        from jobs import inbox_inventory as INV
        ledger = INV.load_quarantine(store)
        added = []
        for email in REMOVE:
            if email in ledger:
                continue
            INV.quarantine_inbox(email, reason=QUARANTINE_REASON, flags=["seed_test_gmail_spam"],
                                 now=now, store=store)
            added.append(email)
        ledger = INV.load_quarantine(store)
        missing = [e for e in REMOVE if e not in ledger]
    except Exception as exc:  # noqa: BLE001 - the quarantine must never undo a verified PATCH
        added, missing = [], list(REMOVE)
        out("quarantine ledger error: %s" % exc)
    if missing:
        out("QUARANTINE NOT RECORDED for %s: run the manual step in README.md" % ", ".join(missing))
        log_run(JOB, "quarantine_failed", {"inboxes": missing})
    else:
        out("capacity.quarantine: added %s; already there %s"
            % (", ".join(added) or "none", ", ".join(e for e in REMOVE if e not in added) or "none"))
        log_run(JOB, "quarantined", {"added": added})


def _stop(out, msg: str, details: Dict[str, Any]) -> int:
    out("STOPPED: %s" % msg)
    log_run(JOB, "leads_stopped", dict(details, error=msg[:300]))
    return EXIT_API


def _apply_leads(plan, rows, meta, ctx) -> int:
    client, out, sleep = ctx["client"], ctx["out"], ctx["sleep"]
    manifest_dir, mirror_dir = ctx["manifest_dir"], ctx["mirror_dir"]
    list_obj = plan["list"]
    if not list_obj:
        try:
            list_obj = find_list(client, PARKED_LIST_NAME) or client.create_lead_list(PARKED_LIST_NAME)
        except InstantlyError as exc:
            return _stop(out, "could not create the lead list: %s; no lead was moved" % exc, {})
    list_id = list_obj.get("id") if isinstance(list_obj, dict) and not list_obj.get("shadow") else None
    if not list_id:
        return _stop(out, "the lead list has no id (%r); no lead was moved" % (list_obj,), {})
    out("destination list %r id %s" % (PARKED_LIST_NAME, list_id))

    # Merge with a manifest left by an earlier apply: its rows are kept (they
    # record moves that happened), new ones are appended. Only a missing file
    # starts a new manifest; an unreadable one stops the run unwritten.
    by_id = OrderedDict()  # type: Dict[str, Dict[str, Any]]
    try:
        old_meta, old_rows = load_manifest(manifest_dir)
    except FileNotFoundError:
        old_meta, old_rows = {}, []
    except (OSError, ValueError) as exc:
        out("REFUSED: the existing manifest cannot be read (%s); it was not overwritten and no lead "
            "was moved" % exc)
        log_run(JOB, "refused", {"error": "manifest unreadable: %s" % str(exc)[:200]})
        return EXIT_INVALID
    for row in old_rows:
        by_id[row["lead_id"]] = dict((c, row.get(c, "")) for c in COLUMNS)
    for row in rows:
        row["destination_list_id"] = list_id
        by_id.setdefault(row["lead_id"], row)
    meta = dict(meta, list_id=list_id, applied_at=_iso(ctx["now"]),
                first_planned_at=old_meta.get("first_planned_at") or old_meta.get("planned_at") or meta["planned_at"])

    def save() -> Tuple[str, str]:
        return write_manifest(manifest_dir, list(by_id.values()), meta, mirror_dir=mirror_dir)

    try:
        csv_path, json_path = save()
    except OSError as exc:
        out("REFUSED: the manifest could not be written (%s); no lead was moved" % exc)
        log_run(JOB, "refused", {"error": "manifest write failed: %s" % exc})
        return EXIT_REFUSED
    out("manifest written before any move: %s (copy in %s)" % (csv_path, mirror_dir))
    log_run(JOB, "manifest_written", {"manifest": json_path, "rows": len(by_id), "list_id": list_id})

    emails = dict((lid, r.get("email") or "") for lid, r in by_id.items())
    canary_done = False
    for cid in CAMPAIGNS:
        try:
            members = campaign_members(client, cid)
        except InstantlyError as exc:
            save()
            return _stop(out, "could not read campaign %s before moving (%s); nothing more was sent" % (cid, exc),
                         {"campaign_id": cid})
        # What to move is decided from live state, not from the manifest: a
        # lead still in its source campaign still has to move, and it is
        # re-checked against the selection rules now, after the prompt.
        todo = []
        for lid, row in by_id.items():
            if row["campaign_id"] != cid or lid not in members:
                continue
            why = exclusion_reason(members[lid], [cid])
            row["moved_at"] = row["move_job_id"] = ""
            row["verified_in_list"] = row["verified_not_in_campaign"] = False
            row["skip_reason"] = why or ""
            if why is None:
                row["restored_at"] = row["restore_job_id"] = ""
                todo.append(lid)
        save()
        batches = []
        if todo and not canary_done:
            batches.append(todo[:1])
            todo = todo[1:]
        batches += [todo[i:i + MOVE_BATCH] for i in range(0, len(todo), MOVE_BATCH)]
        for n, batch in enumerate(batches):
            canary = not canary_done
            # A campaign resumed after the PATCHes would be sending while its
            # leads move: every batch, the canary included, needs it paused.
            try:
                status = client.get_campaign(cid).get("status")
            except InstantlyError as exc:
                save()
                return _stop(out, "could not re-read campaign %s before moving (%s); nothing more was sent"
                             % (cid, exc), {"campaign_id": cid})
            if str(status) != str(PAUSED):
                save()
                return _stop(out, "%s is status %r, no longer 2 (paused); no more leads were moved. Pause it "
                                  "and re-run --apply." % (CAMPAIGNS[cid], status), {"campaign_id": cid})
            before = members
            result = move_batch(client, batch, {"campaign": cid}, {"to_list_id": list_id},
                                lambda cid=cid: set(campaign_members(client, cid)), sleep, out)
            try:
                members = campaign_members(client, cid)
                inside = list_membership(client, list_id)
            except InstantlyError as exc:
                save()
                return _stop(out, "the read-back of %s batch %d failed (%s); its leads are UNKNOWN and "
                                  "were not stamped. Re-run after checking the list." % (CAMPAIGNS[cid], n + 1, exc),
                             {"campaign_id": cid, "job_id": result.get("job_id")})
            gone = set(before) - set(members)
            extra = sorted(gone - set(batch))
            stamp = _iso(R.utcnow())
            job_ref = result.get("job_id") or result.get("job_status")
            for lid in batch:
                if lid in gone and lid in inside:
                    row = by_id[lid]
                    row["moved_at"], row["move_job_id"] = stamp, job_ref
                    row["verified_in_list"] = row["verified_not_in_campaign"] = True
            for lid in extra:
                # Left the campaign without being asked: recorded so that
                # --restore-leads brings it back.
                row = manifest_row(before[lid], list_id, stamp)
                row["skip_reason"] = "over_moved_by_server"
                row["move_job_id"] = job_ref
                row["moved_at"] = stamp if lid in inside else ""
                row["verified_in_list"] = lid in inside
                row["verified_not_in_campaign"] = True
                by_id[lid] = row
                emails[lid] = row.get("email") or ""
            save()
            problems = []
            if not result["ok"]:
                problems.append(result.get("error") or result.get("job_status"))
            jp = job_data_problem(result.get("job"), result.get("sent") or [], emails)
            if jp:
                problems.append(jp)
            if extra:
                problems.append("OVER-MOVE: %d leads left the campaign that were not in this batch "
                                "(recorded in the manifest as over_moved_by_server)" % len(extra))
            unverified = [lid for lid in batch if not by_id[lid]["moved_at"]]
            if unverified:
                problems.append("%d leads of the batch are not verified out of the campaign and in the list"
                                % len(unverified))
            if canary:
                canary_done = True
                if len(before) - len(members) != 1:
                    problems.append("CANARY: the campaign went from %d to %d leads; exactly one should have left"
                                    % (len(before), len(members)))
            out("  %s %s: %d leads, job %s %s" % (CAMPAIGNS[cid][:30], "canary" if canary else "batch %d" % n,
                                                  len(batch), result.get("job_id"), result.get("job_status")))
            if problems:
                return _stop(out, "; ".join(p for p in problems if p),
                             {"campaign_id": cid, "job_id": result.get("job_id"), "manifest": json_path})
            if canary:
                out("  canary verified: 1 lead out of the campaign and in the list, campaign count down by 1")

    out("")
    out("verifying every manifest lead ...")
    ok, summary = _verify_all(client, by_id, list_id, out)
    save()
    _print_summary(summary, out)
    log_run(JOB, "leads_parked" if ok else "leads_partial",
            {"list_id": list_id, "manifest": json_path, "summary": summary})
    return EXIT_OK if ok else EXIT_API


def _verify_all(client, by_id, list_id, out) -> Tuple[bool, Dict[str, Dict[str, int]]]:
    blank = lambda: {"planned": 0, "moved": 0, "skipped": 0, "failed": 0}  # noqa: E731
    summary = OrderedDict((cid, blank()) for cid in CAMPAIGNS)
    try:
        inside = list_membership(client, list_id)
        members = dict((cid, set(campaign_members(client, cid))) for cid in CAMPAIGNS)
    except InstantlyError as exc:
        out("verification read failed: %s; no row counts as verified" % exc)
        for row in by_id.values():
            summary.setdefault(row["campaign_id"], blank())["failed"] += 1
        return False, summary
    for lid, row in by_id.items():
        cid = row["campaign_id"]
        s = summary.setdefault(cid, blank())
        s["planned"] += 1
        in_list = lid in inside
        out_of_campaign = lid not in members.get(cid, set())
        row["verified_in_list"] = in_list
        row["verified_not_in_campaign"] = out_of_campaign
        if in_list and out_of_campaign:
            s["moved"] += 1
            row["moved_at"] = row.get("moved_at") or "verified_%s" % _iso(R.utcnow())
        elif row.get("skip_reason") and row["skip_reason"] != "over_moved_by_server" and not in_list:
            s["skipped"] += 1
        elif not row.get("moved_at") and not in_list and out_of_campaign:
            row["skip_reason"] = row.get("skip_reason") or "not_in_source_campaign"
            s["skipped"] += 1
        else:
            s["failed"] += 1
    return all(s["failed"] == 0 for s in summary.values()), summary


def _print_summary(summary, out, cols=("planned", "moved", "skipped", "failed")) -> None:
    out("  %-46s" % "campaign" + "".join("%10s" % c for c in cols))
    for cid, s in summary.items():
        out("  %-46s" % CAMPAIGNS.get(cid, cid)[:46] + "".join("%10d" % s.get(c, 0) for c in cols))


def _restore_leads(args, ctx) -> int:
    client, out, sleep = ctx["client"], ctx["out"], ctx["sleep"]
    manifest_dir = ctx["manifest_dir"]
    try:
        meta, rows = load_manifest(manifest_dir)
    except FileNotFoundError:
        out("REFUSED: there is no apply manifest at %s" % manifest_paths(manifest_dir, False)[1])
        return EXIT_INVALID
    except (OSError, ValueError) as exc:
        out("REFUSED: the manifest cannot be read (%s); nothing was moved" % exc)
        return EXIT_INVALID
    list_id = meta.get("list_id") or next((r.get("destination_list_id") for r in rows
                                          if r.get("destination_list_id")), None)
    if not list_id:
        out("REFUSED: the manifest names no parked list id")
        return EXIT_INVALID

    pending = [r for r in rows if not r.get("restored_at") and r["campaign_id"] in CAMPAIGNS]
    targets = sorted(set(r["campaign_id"] for r in pending), key=list(CAMPAIGNS).index)
    try:
        members = dict((cid, campaign_members(client, cid)) for cid in targets)
        inside = list_membership(client, list_id)
        statuses = dict((cid, client.get_campaign(cid).get("status")) for cid in targets)
    except InstantlyError as exc:
        out("Instantly read failed: %s; nothing was moved" % exc)
        return EXIT_API
    active = [cid for cid in targets if str(statuses.get(cid)) != str(PAUSED)]
    to_send = [r for r in pending if r["lead_id"] in inside and r["lead_id"] not in members[r["campaign_id"]]]
    missing = [r for r in pending if (r.get("moved_at") or r.get("skip_reason") == "over_moved_by_server")
               and r["lead_id"] not in inside and r["lead_id"] not in members[r["campaign_id"]]]
    if args.limit is not None:
        to_send = to_send[:args.limit]
    groups = OrderedDict()  # type: Dict[str, List[Dict[str, Any]]]
    for row in to_send:
        groups.setdefault(row["campaign_id"], []).append(row)

    out("RESTORE LEADS from list %s back to their campaigns (manifest %s)"
        % (list_id, manifest_paths(manifest_dir, False)[0]))
    out("  %d manifest rows not yet restored; %d of them are in the parked list; sending %d%s"
        % (len(pending), sum(1 for r in pending if r["lead_id"] in inside), len(to_send),
           " (--limit %d)" % args.limit if args.limit is not None else ""))
    for cid, group in groups.items():
        mid = sum(1 for r in group if r.get("stage") == "mid_sequence")
        out("  -> %s (%s): %d leads, %d of them mid-sequence" % (CAMPAIGNS.get(cid, cid), cid, len(group), mid))
    for row in missing:
        out("  NOT FOUND: %s was recorded as parked but is neither in the list nor in %s"
            % (row["lead_id"], CAMPAIGNS.get(row["campaign_id"], row["campaign_id"])))
    out("  mid-sequence leads may restart at step 1 when moved back (unverified): restore one with "
        "--limit 1 and check it first.")
    if active:
        out("REFUSED: %s not paused (status 2); leads are only moved back into paused campaigns."
            % ", ".join("%s is status %s" % (CAMPAIGNS[c], statuses[c]) for c in active))
        return EXIT_INVALID
    if not args.apply:
        out("dry-run only: nothing was moved.")
        log_run(JOB, "restore_leads_dry_run", {"groups": dict((c, len(g)) for c, g in groups.items()),
                                               "not_found": len(missing)})
        return EXIT_API if missing else EXIT_OK
    if not settings.is_live():
        out("--restore-leads --apply refused: MODE=%s and the live-writes flag is not set." % settings.get_mode())
        return EXIT_REFUSED
    if not args.yes:
        answer = (ctx["confirm"] or input)("Move these leads back to their campaigns? type yes: ").strip().lower()
        if answer != "yes":
            out("aborted")
            return EXIT_REFUSED

    by_id = dict((r["lead_id"], r) for r in rows)
    emails = dict((r["lead_id"], r.get("email") or "") for r in rows)
    meta = dict(meta, restore_started_at=_iso(ctx["now"]))

    def save() -> None:
        write_manifest(manifest_dir, rows, meta, mirror_dir=ctx["mirror_dir"])

    for cid, group in groups.items():
        ids = [r["lead_id"] for r in group]
        for n, start in enumerate(range(0, len(ids), MOVE_BATCH)):
            batch = ids[start:start + MOVE_BATCH]
            before_members, before_inside = set(members[cid]), set(inside)
            result = move_batch(client, batch, {"list_id": list_id}, {"to_campaign_id": cid},
                                lambda: list_membership(client, list_id), sleep, out)
            try:
                members[cid] = campaign_members(client, cid)
                inside = list_membership(client, list_id)
            except InstantlyError as exc:
                save()
                return _stop(out, "the read-back after restoring to %s failed (%s); those leads were not "
                                  "stamped" % (CAMPAIGNS[cid], exc), {"campaign_id": cid})
            now_in = set(members[cid])
            stamp = _iso(R.utcnow())
            for lid in batch:
                if lid in now_in:
                    by_id[lid]["restored_at"] = stamp
                    by_id[lid]["restore_job_id"] = result.get("job_id") or result.get("job_status")
            save()
            problems = []
            if not result["ok"]:
                problems.append(result.get("error") or result.get("job_status"))
            jp = job_data_problem(result.get("job"), result.get("sent") or [], emails)
            if jp:
                problems.append(jp)
            arrived_extra = sorted((now_in - before_members) - set(batch))
            left_extra = sorted((before_inside - inside) - set(batch))
            if arrived_extra or left_extra:
                problems.append("OVER-MOVE: %d leads not in this batch arrived in the campaign and %d left "
                                "the list" % (len(arrived_extra), len(left_extra)))
            not_back = [lid for lid in batch if lid not in now_in]
            if not_back:
                problems.append("%d leads of the batch are not back in %s: %s"
                                % (len(not_back), CAMPAIGNS[cid], ", ".join(not_back[:10])))
            out("  %s batch %d: %d leads, job %s %s" % (CAMPAIGNS[cid][:30], n + 1, len(batch),
                                                       result.get("job_id"), result.get("job_status")))
            if problems:
                return _stop(out, "; ".join(p for p in problems if p), {"campaign_id": cid})
    ok = not missing
    log_run(JOB, "leads_restored" if ok else "restore_leads_partial",
            {"groups": dict((c, len(g)) for c, g in groups.items()), "not_found": len(missing)})
    if missing:
        out("%d rows recorded as parked were not found in the list or their campaign (listed above)" % len(missing))
    return EXIT_OK if ok else EXIT_API


def _restore_campaign(args, client, now, backup_dir, confirm) -> int:
    campaign_id = R.campaign_id_for(args.campaign or "")
    if not campaign_id:
        print("REFUSED: --restore needs --campaign <key> from config/ids.json (got %r)" % args.campaign,
              file=sys.stderr)
        return EXIT_INVALID
    try:
        R.load_point(args.restore, SCRIPT, campaign_id)
    except R.RollbackRefused as exc:
        print("REFUSED: %s" % exc, file=sys.stderr)
        return EXIT_INVALID
    if not settings.is_live():
        print("--restore refused: MODE=%s and the live-writes flag is not set. Nothing was read or "
              "written." % settings.get_mode(), file=sys.stderr)
        return EXIT_REFUSED
    if client is None:
        try:
            client = default_client()
        except InstantlyError as exc:
            print("Instantly client: %s" % exc, file=sys.stderr)
            return EXIT_API

    def typed() -> bool:
        if args.yes:
            return True
        answer = (confirm or input)("Restore %s from %s? type the campaign key: "
                                    % (args.campaign, args.restore)).strip()
        return answer == args.campaign

    try:
        code, info = R.restore(client, SCRIPT, args.restore, campaign_id, args.campaign, backup_dir,
                               "%s_%s_%s" % (SCRIPT, campaign_id, R.stamp(now)), now, _say,
                               confirm=typed, override_later_changes=args.override_later_changes)
    except InstantlyError as exc:
        print("Instantly error: %s" % exc, file=sys.stderr)
        return EXIT_API
    log_run(JOB, "restored" if code == EXIT_OK else "restore_failed", info)
    return code


if __name__ == "__main__":
    sys.exit(main())
