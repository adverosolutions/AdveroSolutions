#!/usr/bin/env python3
"""Instantly webhooks change-set (runbooks/deployment.md step 4 and the step 6 rollback).

Creates the webhooks that point Instantly at the reply engine, each carrying the
shared secret header the FastAPI app checks. Nothing here runs by accident:

    cd "Agentic Worklfows"
    python3 changesets/instantly_webhooks.py --dry-run                 # default, zero writes
    python3 changesets/instantly_webhooks.py --dry-run --url https://... --json
    MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/instantly_webhooks.py --apply --yes
    MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/instantly_webhooks.py --rollback --yes

Contract (config/instantly_api_contract.md, POST /webhooks):
* the field is ``target_hook_url``, NOT ``target_url``. It is the only required
  property and must match ``^https?://``. ``webhooks_create`` passes the dict
  through unchanged, so the wrong key creates a webhook with no target and every
  reply is silently never delivered.
* ``headers`` is a flat string-to-string object sent with every delivery, which
  is how ``X-Advero-Secret`` reaches ``app.py``.

**``DELETE /webhooks/{id}`` IS UNVERIFIED.** It is not in the verified API
contract, and ``shared.instantly.Instantly.webhooks_delete`` has never been
exercised against Instantly. It has to be confirmed in the live rehearsal
(create one webhook, delete it by id with a hand-run call, read GET /webhooks)
and then added to ``config/instantly_api_contract.md``; only then is
``DELETE_WEBHOOK_VERIFIED`` flipped. Even then ``--rollback`` treats the DELETE
response as a claim, not a fact: it re-reads ``GET /webhooks`` and reports a
webhook as removed only when its id is gone from that list.

Safety, in the order the checks fire:
* ``--dry-run`` is the default and is refused together with ``--apply`` or
  ``--rollback``. ``--apply`` and ``--rollback`` both refuse unless
  ``settings.is_live()`` (MODE=live AND ALLOW_LIVE_WRITES=1) and both require
  ``--yes`` plus a typed confirmation.
* a dry-run writes nothing under ``changesets/backups/``: its copy of the live
  list goes to ``.tmp/changeset_dryruns/webhooks/`` and its Job_Log row to a
  scratch file, never the production ``.tmp/job_log.csv``.
* ``--apply`` backs the live webhook list up to
  ``changesets/backups/webhooks_<ts>.json`` BEFORE anything is created.
* a webhook whose event_type and target already exist is skipped, so a re-run
  after a partial failure does not double-deliver every reply.
* every webhook ``--apply`` creates is recorded, by the id Instantly returned,
  in the ledger ``changesets/backups/webhooks_created_ids.json``.
* a create that raised may still have landed. After any create error, and at
  the start of every ``--apply``, the live list is re-read and any webhook with
  one of our event types AND our URL AND our name prefix that the ledger lacks
  is added to it, with a printed line saying so.
* ``--rollback`` needs neither ``REPLY_ENGINE_SECRET`` nor the engine URL (the
  Modal app may already be stopped). It acts only on ids in that ledger.
  **While ``DELETE_WEBHOOK_VERIFIED`` is False it sends no DELETE at all**: it
  lists every recorded id that is still live as NOT deleted, points at
  Instantly > Settings > Webhooks, writes an ``errors`` Job_Log row and exits
  3. Once verified, it deletes the recorded ids whose name still carries
  ``NAME_PREFIX`` (AND), and reports any recorded id that is still live but
  renamed as NOT deleted, again exiting 3. A webhook this change-set never
  recorded is left alone and listed.

Exit codes: 0 ok, 1 data/validation error, 2 live write refused, 3 API error.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from shared import job_log, settings  # noqa: E402
from shared.instantly import Instantly, default_client, InstantlyError  # noqa: E402
from changesets import rollback as R  # noqa: E402

JOB = "changesets.instantly_webhooks"
BACKUP_DIR = os.path.join(ROOT, "changesets", "backups")
NAME_PREFIX = "advero-reply-engine"
SECRET_HEADER = "X-Advero-Secret"
WEBHOOK_PATH = "/webhooks/instantly"
LEDGER_NAME = "webhooks_created_ids.json"
# GOL-18: DELETE /webhooks/{id} is not in the verified contract. Flip this only
# after the live rehearsal has confirmed it and the contract records it.
DELETE_WEBHOOK_VERIFIED = False

# runbooks/deployment.md step 4. Every one points at the same endpoint; app.py
# routes on the payload, not on the URL.
EVENT_TYPES = (
    "reply_received",
    "lead_interested",
    "lead_not_interested",
    "lead_unsubscribed",
    "email_bounced",
    "lead_meeting_booked",
)


# ------------------------------------------------------------------ desired
def base_url(override: Optional[str] = None) -> str:
    """The reply engine's public base URL: --url, then REPLY_ENGINE_BASE_URL,
    then BASE_URL. There is no default: guessing a Modal URL would create six
    webhooks that deliver nowhere."""
    url = (override or os.environ.get("REPLY_ENGINE_BASE_URL") or os.environ.get("BASE_URL") or "").strip()
    return url.rstrip("/")


def target_url(override: Optional[str] = None) -> str:
    base = base_url(override)
    if not base:
        raise ValueError(
            "no base URL: pass --url https://<workspace>--advero-reply-engine-web.modal.run "
            "or set REPLY_ENGINE_BASE_URL. A webhook with the wrong target accepts the create "
            "and then silently delivers nothing.")
    if not base.startswith("http://") and not base.startswith("https://"):
        raise ValueError("base URL %r must start with http:// or https:// (the API enforces ^https?://)" % base)
    return base + WEBHOOK_PATH


def secret() -> str:
    value = (os.environ.get("REPLY_ENGINE_SECRET") or "").strip()
    if not value:
        raise ValueError(
            "REPLY_ENGINE_SECRET is unset. app.py rejects every webhook without a matching "
            "X-Advero-Secret, so creating these now would point Instantly at an endpoint that "
            "401s every delivery.")
    return value


def desired_webhooks(url_override: Optional[str] = None, include_secret: bool = True) -> List[Dict[str, Any]]:
    """The six POST /webhooks bodies, in the shape the API takes."""
    url = target_url(url_override)
    header_value = secret() if include_secret else "<REPLY_ENGINE_SECRET>"
    out = []  # type: List[Dict[str, Any]]
    for event in EVENT_TYPES:
        out.append({
            "name": "%s %s" % (NAME_PREFIX, event),
            "event_type": event,
            # NOT target_url: see the module docstring and the API contract.
            "target_hook_url": url,
            "headers": {SECRET_HEADER: header_value},
        })
    return out


def redact(payload: Dict[str, Any]) -> Dict[str, Any]:
    """The same body with the secret masked, for printing and for the backup."""
    out = dict(payload)
    if isinstance(out.get("headers"), dict):
        out["headers"] = dict((k, "<redacted>") for k in out["headers"])
    return out


# --------------------------------------------------------------------- live
def _row_target(row: Dict[str, Any]) -> str:
    for key in ("target_hook_url", "targetHookUrl", "target_url", "url"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def fetch_live(instantly: Instantly) -> List[Dict[str, Any]]:
    """GET /webhooks. The v2 read answers a bare array on this endpoint, which
    shared.instantly.iterate/_get already handle."""
    raw = instantly.webhooks_list()
    if isinstance(raw, dict):
        raw = raw.get("items", raw.get("data", []))
    return [r for r in (raw or []) if isinstance(r, dict)]


def diff(desired: List[Dict[str, Any]], live: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """What --apply would do. A webhook already pointing at our URL for that
    event is left alone: creating a second one delivers every reply twice."""
    existing = set((str(r.get("event_type") or ""), _row_target(r)) for r in live)
    create, skip = [], []
    for want in desired:
        if (want["event_type"], want["target_hook_url"]) in existing:
            skip.append(want)
        else:
            create.append(want)
    return {"create": create, "skip": skip, "live": live}


def ours(live: List[Dict[str, Any]], ledger_ids: Optional[List[str]] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(ours, theirs) split of the live list, for --rollback.

    A row is ours only when its id is one this change-set recorded when it
    created it AND its name still carries NAME_PREFIX. The old rule (our URL OR
    our prefix) could delete a hand-made webhook that happened to share either,
    and needed the URL, which may be unknown once the Modal app is stopped.
    """
    recorded = set(str(i) for i in (ledger_ids or []))
    mine, other = [], []
    for row in live:
        wid = str(row.get("id") or row.get("_id") or "")
        name = str(row.get("name") or "")
        if wid and wid in recorded and name.startswith(NAME_PREFIX):
            mine.append(row)
        else:
            other.append(row)
    return mine, other


# ------------------------------------------------------------------- ledger
def ledger_path(backup_dir: Optional[str] = None) -> str:
    return os.path.join(backup_dir or BACKUP_DIR, LEDGER_NAME)


def load_ledger(backup_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    path = ledger_path(backup_dir)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return [e for e in (data.get("created") or []) if isinstance(e, dict) and e.get("id")]


def save_ledger(entries: List[Dict[str, Any]], backup_dir: Optional[str] = None) -> str:
    path = ledger_path(backup_dir)
    R._write_json(path, {
        "_about": ("Webhooks created by changesets/instantly_webhooks.py --apply, by the id "
                   "Instantly returned. --rollback deletes only these ids (and only while their "
                   "name still starts with %s). Do not edit by hand." % NAME_PREFIX),
        "created": entries,
    })
    return path


# ------------------------------------------------------------------ backups
def write_backup(live: List[Dict[str, Any]], dry_run: bool, backup_dir: Optional[str] = None,
                 suffix: str = "") -> str:
    """Save the current webhook list (secrets redacted) before touching anything.

    A dry-run copy goes under .tmp/changeset_dryruns/webhooks/ with the
    .dryrun suffix, never into changesets/backups/ (SAF-10)."""
    if dry_run:
        directory = R.dryrun_dir("webhooks")
        suffix = ".dryrun"
    else:
        directory = backup_dir or BACKUP_DIR
    os.makedirs(directory, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(directory, "webhooks_%s%s.json" % (ts, suffix))
    n = 2
    while os.path.exists(path):          # never overwrite an earlier backup
        path = os.path.join(directory, "webhooks_%s_%d%s.json" % (ts, n, suffix))
        n += 1
    with open(path, "w", encoding="utf-8") as fh:
        json.dump([redact(r) for r in live], fh, indent=2, sort_keys=True)
    return path


# -------------------------------------------------------------------- apply
def confirm(action: str, count: int, url: str, assume_yes: bool, reader=input) -> bool:
    """--yes plus a typed confirmation. Both live paths go through this."""
    if not assume_yes:
        print("refusing: %s needs --yes as well as MODE=live ALLOW_LIVE_WRITES=1" % action)
        return False
    print("\nAbout to %s %d webhook(s) on the LIVE Instantly workspace." % (action, count))
    print("Target: %s" % url)
    typed = reader("Type %r to continue: " % action)
    if typed.strip() != action:
        print("not confirmed; nothing was sent")
        return False
    return True


def apply(instantly: Instantly, plan: Dict[str, List[Dict[str, Any]]],
          backup_dir: Optional[str] = None) -> Dict[str, Any]:
    """Create the missing webhooks. Every call goes through
    Instantly.webhooks_create -> settings.guard_write, so in shadow each is a
    would_do record and no HTTP request is made. Each live create is written to
    the ledger straight away, by the id Instantly returned, so a crash between
    two creates still leaves --rollback everything it needs."""
    results = []  # type: List[Dict[str, Any]]
    errors = []  # type: List[str]
    for payload in plan["create"]:
        try:
            res = instantly.webhooks_create(payload)
        except InstantlyError as exc:
            errors.append("%s: %s" % (payload["event_type"], exc))
            continue
        results.append({"event_type": payload["event_type"], "result": res})
        if isinstance(res, dict) and res.get("shadow"):
            continue
        wid = (res or {}).get("id") if isinstance(res, dict) else None
        if not wid:
            errors.append("%s: created, but the response carried no id, so --rollback cannot find "
                          "it. Delete it by hand in Instantly > Settings > Webhooks if needed."
                          % payload["event_type"])
            continue
        entries = load_ledger(backup_dir)
        entries.append({"id": str(wid), "event_type": payload["event_type"], "name": payload["name"],
                        "target_hook_url": payload["target_hook_url"],
                        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat()})
        save_ledger(entries, backup_dir)
    return {"created": results, "errors": errors, "skipped": len(plan["skip"])}


def rollback(instantly: Instantly, mine: List[Dict[str, Any]]) -> Dict[str, Any]:
    """DELETE each webhook (UNVERIFIED endpoint, see the module docstring)."""
    deleted, errors = [], []
    for row in mine:
        wid = row.get("id") or row.get("_id")
        if not wid:
            errors.append("a webhook row has no id: %s" % sorted(row.keys()))
            continue
        try:
            deleted.append({"id": wid, "result": instantly.webhooks_delete(str(wid))})
        except AttributeError:
            errors.append(
                "shared.instantly.Instantly has no webhooks_delete; delete these ids by hand in "
                "Instantly > Settings > Webhooks: %s" % ", ".join(str(r.get("id")) for r in mine))
            break
        except InstantlyError as exc:
            errors.append("%s: %s" % (wid, exc))
    return {"deleted": deleted, "errors": errors}


def verify_gone(instantly: Instantly, ids: List[str]) -> Tuple[List[str], List[str]]:
    """(gone, still_listed) after a rollback, from a fresh GET /webhooks."""
    live_ids = set(str(r.get("id") or r.get("_id")) for r in fetch_live(instantly))
    gone = [i for i in ids if i not in live_ids]
    return gone, [i for i in ids if i in live_ids]


# ---------------------------------------------------------------------- cli
def _print_plan(plan: Dict[str, List[Dict[str, Any]]], url: str) -> None:
    print("target_hook_url: %s" % url)
    print("secret header:   %s: <set from REPLY_ENGINE_SECRET>" % SECRET_HEADER)
    print("\nlive webhooks: %d" % len(plan["live"]))
    for row in plan["live"]:
        print("  %-24s %s  (%s)" % (row.get("event_type"), _row_target(row), row.get("name")))
    print("\nwould create: %d" % len(plan["create"]))
    for row in plan["create"]:
        print("  " + json.dumps(redact(row), sort_keys=True))
    if plan["skip"]:
        print("\nalready present, left alone: %d" % len(plan["skip"]))
        for row in plan["skip"]:
            print("  %s" % row["event_type"])


def main(argv: Optional[List[str]] = None, reader=input, client: Optional[Instantly] = None,
         backup_dir: Optional[str] = None) -> int:
    p = argparse.ArgumentParser(prog="instantly_webhooks", description=__doc__.split("\n\n")[0])
    p.add_argument("--dry-run", action="store_true", help="plan only (the default)")
    p.add_argument("--apply", action="store_true", help="create the missing webhooks (live only)")
    p.add_argument("--rollback", action="store_true",
                   help="delete the webhooks this change-set recorded creating (live only; needs no secret or URL)")
    p.add_argument("--url", help="reply engine base URL (default REPLY_ENGINE_BASE_URL or BASE_URL)")
    p.add_argument("--yes", action="store_true", help="required for --apply / --rollback, alongside the typed confirmation")
    p.add_argument("--json", action="store_true", help="print the plan as JSON")
    args = p.parse_args(argv)

    if args.apply and args.rollback:
        print("refusing: --apply and --rollback are opposites; run one at a time")
        return 2
    if args.dry_run and (args.apply or args.rollback):
        print("refusing: --dry-run cannot be combined with --apply or --rollback; say which one you mean")
        return 2
    live_action = "apply" if args.apply else ("rollback" if args.rollback else None)
    if live_action and not settings.is_live():
        print("refusing: %s needs MODE=live and ALLOW_LIVE_WRITES=1 (currently mode=%s). "
              "Re-run without --%s to see the plan." % (live_action, settings.get_mode(), live_action))
        return 2
    if args.rollback:
        return _rollback(args, reader, client, backup_dir)
    if live_action:
        return _apply_or_plan(args, reader, client, backup_dir, live_action)
    # GOL-20 item 5: a dry-run never writes the production Job_Log.
    with R.scratch_logs("instantly_webhooks_dryrun"):
        return _apply_or_plan(args, reader, client, backup_dir, None)


def _rollback(args: Any, reader, client: Optional[Instantly], backup_dir: Optional[str]) -> int:
    """GOL-18: no secret, no URL; match on the ids recorded at create time."""
    try:
        ledger = load_ledger(backup_dir)
    except (OSError, ValueError) as exc:
        print("refusing: the ledger %s cannot be read (%s)" % (ledger_path(backup_dir), exc))
        return 1
    recorded = [e["id"] for e in ledger if not e.get("deleted_at")]
    if not recorded:
        print("refusing: %s records no webhook this change-set created, so there is nothing it may "
              "delete. Anything named %s* was not created by --apply; check Instantly > Settings > "
              "Webhooks by hand." % (ledger_path(backup_dir), NAME_PREFIX))
        return 1
    instantly = client or default_client()
    try:
        return _rollback_with(args, reader, instantly, backup_dir, ledger, recorded)
    finally:
        if client is None:
            instantly.close()


def _rollback_with(args: Any, reader, instantly: Instantly, backup_dir: Optional[str],
                   ledger: List[Dict[str, Any]], recorded: List[str]) -> int:
    try:
        live = fetch_live(instantly)
    except InstantlyError as exc:
        print("could not read the live webhooks: %s" % exc)
        return 3
    backup = write_backup(live, dry_run=False, backup_dir=backup_dir, suffix=".prerollback")
    print("backup: %s" % backup)
    by_id = dict((str(r.get("id") or r.get("_id")), r) for r in live)
    recorded_live = [i for i in recorded if i in by_id]
    already = [i for i in recorded if i not in by_id]
    mine, _theirs = ours(live, recorded)
    mine_ids = [str(r.get("id") or r.get("_id")) for r in mine]
    # Re-review defect 7: a recorded id that is still live is never quietly
    # "kept". If it fails the name check (renamed in the UI, or the row has no
    # name) it is reported NOT deleted and the run fails.
    renamed = [i for i in recorded_live if i not in mine_ids]
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    for entry in ledger:
        if entry["id"] in already:
            entry.setdefault("deleted_at", stamp)
            entry.setdefault("note", "absent from GET /webhooks at rollback")
    if already:
        save_ledger(ledger, backup_dir)
        print("recorded and already absent from GET /webhooks: %s" % ", ".join(already))
    print("\nrecorded by this change-set and still live: %d" % len(recorded_live))
    for i in recorded_live:
        row = by_id[i]
        print("  %s %s name=%r target=%s" % (i, row.get("event_type"), row.get("name"), _row_target(row)))
    for i in [str(r.get("id") or r.get("_id")) for r in live if str(r.get("id") or r.get("_id")) not in recorded]:
        print("  not recorded by this change-set, left alone: %s (%s)" % (i, by_id[i].get("name")))
    if not recorded_live:
        print("nothing recorded is still live")
        job_log.log_run(JOB, "ok", {"action": "rollback", "deleted": 0, "already_absent": already,
                                    "backup": backup})
        return 0

    if not DELETE_WEBHOOK_VERIFIED:
        # Re-review defect 6: the endpoint is unverified, so nothing is sent.
        print("\nNOT deleted: DELETE /webhooks/{id} is UNVERIFIED against the API contract, so this "
              "script sends no DELETE. Delete these %d webhook(s) by hand in Instantly > Settings > "
              "Webhooks, then re-run --rollback, which records them as gone:" % len(recorded_live))
        for i in recorded_live:
            print("  NOT deleted: %s (%s, name %r)" % (i, by_id[i].get("event_type"), by_id[i].get("name")))
        errors = ["%s: NOT deleted (DELETE unverified; delete by hand in the UI)" % i for i in recorded_live]
        job_log.log_run(JOB, "errors", {"action": "rollback", "not_deleted": recorded_live,
                                        "errors": errors, "backup": backup})
        return 3

    errors = ["%s: NOT deleted, its name no longer starts with %s (renamed in the UI, or the row has "
              "no name); check it and delete it by hand" % (i, NAME_PREFIX) for i in renamed]
    gone, still = [], []  # type: List[str], List[str]
    if mine:
        if not confirm("rollback", len(mine), "(ids from %s)" % ledger_path(backup_dir), args.yes, reader):
            return 2
        try:
            out = rollback(instantly, mine)
            gone, still = verify_gone(instantly, mine_ids)
        except InstantlyError as exc:
            print("could not verify the rollback: %s" % exc)
            job_log.log_run(JOB, "errors", {"action": "rollback", "error": str(exc)[:300], "backup": backup})
            return 3
        errors += list(out["errors"])
        errors += ["%s: DELETE answered but GET /webhooks still lists it" % i for i in still]
    for entry in ledger:
        if entry["id"] in gone:
            entry.setdefault("deleted_at", stamp)
    save_ledger(ledger, backup_dir)
    for e in errors:
        print("  %s" % e)
    job_log.log_run(JOB, "errors" if errors else "ok", {"action": "rollback", "verified_gone": gone,
                                                        "still_listed": still, "not_deleted": renamed,
                                                        "errors": errors, "backup": backup})
    print(json.dumps({"verified_gone": gone, "still_listed": still, "not_deleted": renamed,
                      "errors": errors}, indent=2, default=str))
    return 3 if errors else 0


def reconcile_ledger(live: List[Dict[str, Any]], url: str, backup_dir: Optional[str],
                     write: bool = True) -> List[Dict[str, Any]]:
    """Record live webhooks this change-set evidently created but never
    recorded (re-review defect 10): a create that raised (a 504 that landed)
    or answered without an id. A row qualifies only with one of our event
    types AND our target URL AND our name prefix."""
    entries = load_ledger(backup_dir)
    known = set(e["id"] for e in entries)
    found = []
    for row in live:
        wid = str(row.get("id") or row.get("_id") or "")
        if (wid and wid not in known and str(row.get("event_type") or "") in EVENT_TYPES
                and _row_target(row) == url and str(row.get("name") or "").startswith(NAME_PREFIX)):
            found.append({"id": wid, "event_type": row.get("event_type"), "name": row.get("name"),
                          "target_hook_url": url, "recorded_by": "reconcile",
                          "created_at": row.get("timestamp_created"),
                          "recorded_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat()})
    for e in found:
        print("%s %s (%s): live, ours by event, URL and name, but missing from the ledger%s"
              % ("recording" if write else "would record", e["id"], e["event_type"],
                 "; added so --rollback covers it" if write else ""))
    if found and write:
        save_ledger(entries + found, backup_dir)
    return found


def _apply_or_plan(args: Any, reader, client: Optional[Instantly], backup_dir: Optional[str],
                   live_action: Optional[str]) -> int:
    try:
        url = target_url(args.url)
        if live_action:
            secret()            # fail before any read if the header value is missing
    except ValueError as exc:
        print("refusing: %s" % exc)
        return 1

    instantly = client or default_client()
    try:
        return _plan_with(args, reader, instantly, backup_dir, live_action, url)
    finally:
        if client is None:
            instantly.close()


def _plan_with(args: Any, reader, instantly: Instantly, backup_dir: Optional[str],
               live_action: Optional[str], url: str) -> int:
    try:
        live = fetch_live(instantly)
    except InstantlyError as exc:
        print("could not read the live webhooks: %s" % exc)
        return 3
    backup = write_backup(live, dry_run=not live_action, backup_dir=backup_dir)
    print("backup: %s" % backup)
    try:
        reconcile_ledger(live, url, backup_dir, write=bool(live_action))
    except (OSError, ValueError) as exc:
        print("refusing: the ledger %s cannot be read or written (%s)" % (ledger_path(backup_dir), exc))
        return 1

    # The dry-run is documented (runbooks/deployment.md step 4) as running
    # BEFORE the secret exists: it is generated in step 2a and is not in
    # .env. desired_webhooks() called secret() unconditionally, so the one
    # command whose whole job is to prove this change-set is safe died with
    # a raw ValueError traceback and left a stray backup behind. Print the
    # plan with the header value masked instead.
    try:
        desired = desired_webhooks(args.url, include_secret=bool(live_action))
    except ValueError as exc:
        print("refusing: %s" % exc)
        return 1
    plan = diff(desired, live)
    if args.json:
        print(json.dumps({"target": url, "create": [redact(r) for r in plan["create"]],
                          "skip": [r["event_type"] for r in plan["skip"]]}, indent=2, sort_keys=True))
    else:
        _print_plan(plan, url)
    if not args.apply:
        job_log.log_run(JOB, "dry_run", {"would_create": len(plan["create"]), "skipped": len(plan["skip"]),
                                         "target": url, "backup": backup})
        return 0
    if not confirm("apply", len(plan["create"]), url, args.yes, reader):
        return 2
    out = apply(instantly, plan, backup_dir)
    if out["errors"]:
        # A create that raised may still have landed: re-read and record it.
        try:
            out["reconciled"] = [e["id"] for e in reconcile_ledger(fetch_live(instantly), url, backup_dir)]
        except InstantlyError as exc:
            out["errors"].append("could not re-read the webhooks to reconcile the ledger: %s" % exc)
    job_log.log_run(JOB, "errors" if out["errors"] else "ok", {"action": "apply", "created": len(out["created"]),
                                                               "errors": out["errors"], "backup": backup,
                                                               "ledger": ledger_path(backup_dir)})
    print(json.dumps({"created": len(out["created"]), "skipped": out["skipped"], "errors": out["errors"],
                      "ledger": ledger_path(backup_dir)}, indent=2))
    return 3 if out["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
