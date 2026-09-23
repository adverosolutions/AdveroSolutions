"""Change-set: apply the deliverability monitor's proposed inbox actions.

    cd "Agentic Worklfows"
    python3 changesets/inbox_actions/apply_inbox_actions.py --dry-run
    python3 changesets/inbox_actions/apply_inbox_actions.py --dry-run --date 2026-09-22
    MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/inbox_actions/apply_inbox_actions.py \
        --apply --id remove_from_email_list:lorenzo@myadvero.com
    MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/inbox_actions/apply_inbox_actions.py \
        --restore changesets/backups/inbox_actions_campaign_<campaign_id>_before_<ts>.json --campaign <key>

``--dry-run`` (the default) re-reads live and prints the real diff: the account's
current status, the campaign's current ``email_list``, and what each action
would change it to. It never writes, and its Job_Log rows go to a scratch file.
``--apply`` needs MODE=live **and** ALLOW_LIVE_WRITES=1, takes **one proposal id
at a time**, and writes the before-image of each campaign it PATCHes to
``changesets/backups/`` first (see changesets/rollback.py for the file kinds).

Properties this script has on purpose:

**It re-reads and recomputes, it does not replay.** The change-set records
``expected_before`` for every ``email_list`` patch. If live no longer matches
that list, the action is REFUSED rather than applied: a stale list would
otherwise re-add an inbox that was removed for a different reason yesterday, or
drop one that was promoted this morning. The whole point of PATCH
``email_list`` is that it replaces the array, so sending a stale array is a
silent regression. A campaign whose live list already equals the proposal's
target list is ``satisfied`` (that PATCH landed on an earlier run).

**It stops at the first failed write (GOL-17).** One proposal can carry six
campaign PATCHes. After a failure nothing further is sent; the proposal is
re-planned from live and printed, so the PATCHes that landed show as satisfied
and a re-run finishes the rest. A proposal marked ``apply_failed`` (by this
script, or inherited by a regenerated proposal of the same id) is re-planned
from live rather than skipped.

**It honours ``not_before``.** The placement re-test the marketing lane stages
after a placement failure (``jobs/inbox_placement.py``) may not run before its
48 h ``not_before``; until then the proposal is skipped with that reason.

**It refuses to empty a campaign.** Patching ``email_list`` to zero addresses
stops a campaign sending with no error anywhere. The floor is
MIN_EMAIL_LIST_AFTER_APPLY.

**``--restore`` puts one campaign's ``email_list`` back** from the rollback
point this script wrote, and refuses any other file. It reads live first,
prints the inboxes it would remove and add, and refuses when the list changed
after the apply unless ``--override-later-changes`` is given; only then does it
ask for the typed confirmation.

**DNS and canary-send actions are not applicable here.** ``fix_dns`` is work in
a registrar, and the canary send has no v2 endpoint. Both print what to do and
are marked ``manual``.
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

HERE = Path(__file__).resolve().parent
BASE_DIR = HERE.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from shared import settings  # noqa: E402
from shared import thresholds as TH  # noqa: E402
from shared.job_log import log_run  # noqa: E402
from shared.settings import LiveWriteBlocked, require_live  # noqa: E402
from changesets import rollback as R  # noqa: E402

logger = logging.getLogger("changesets.inbox_actions")

JOB = "apply_inbox_actions"
SCRIPT = "inbox_actions"
CHANGESET_DIR = HERE
BACKUP_DIR = BASE_DIR / "changesets" / "backups"

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_REFUSED = 2

# Both operational floors live in shared/thresholds.py with the rest of the
# numbers, because a number inlined in a branch is a number nobody can find when
# Lorenzo asks why an apply refused.
MIN_EMAIL_LIST_AFTER_APPLY = TH.MIN_EMAIL_LIST_AFTER_APPLY
WARN_EMAIL_LIST_AFTER_APPLY = TH.WARN_EMAIL_LIST_AFTER_APPLY

# Actions this script knows how to execute. Anything else is manual.
EXECUTABLE_OPS = ("pause_account", "resume_account", "patch_campaign_email_list")
MANUAL_OPS = ("add_records", "stop_using_domain", "create_placement_test", "canary_send")


def changeset_path(date: Optional[str] = None, directory: Optional[Path] = None) -> Optional[Path]:
    # The module global is read at CALL time, not bound as a default, so a test
    # (or a caller with a different folder) can redirect it.
    directory = Path(directory) if directory else CHANGESET_DIR
    if date:
        path = directory / ("%s.json" % date)
        return path if path.exists() else None
    candidates = sorted(p for p in directory.glob("*.json")
                        if p.name != TH.LEVEL5_SPEC_FILENAME and not p.name.startswith("last_"))
    return candidates[-1] if candidates else None


def load_changeset(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _backup(name: str, data: Any, now: datetime, directory: Optional[Path] = None,
            kind: str = R.KIND_PREAPPLY, fields: Optional[List[str]] = None,
            campaign_id: Optional[str] = None, campaign_key: Optional[str] = None,
            object_type: str = "campaign", after: Optional[Dict[str, Any]] = None) -> Optional[Path]:
    """Write a before-image (a rollback-point envelope, changesets/rollback.py).

    Returns None when it cannot be written; the caller then refuses the write.
    """
    directory = Path(directory) if directory else BACKUP_DIR
    stem = "%s_before_%s" % (name, R.stamp(now))
    try:
        point = R.build_point(SCRIPT, kind, data if isinstance(data, dict) else {"value": data},
                              fields or [], now, campaign_id=campaign_id, campaign_key=campaign_key,
                              object_type=object_type, after=after)
        return Path(R.write_point(str(directory), stem, point))
    except (OSError, ValueError) as exc:
        logger.warning("backup write failed (%s/%s): %s", directory, stem, exc)
        return None


# =========================================================================
# Diffing against live
# =========================================================================

def _removals(action: Dict[str, Any]) -> List[str]:
    # `remove` is one address, or several when a whole domain is retired in
    # one patch. Both shapes land here.
    raw_remove = action.get("remove") or []
    if isinstance(raw_remove, str):
        raw_remove = [raw_remove]
    return list(raw_remove)


def _target_list(base: List[str], action: Dict[str, Any]) -> List[str]:
    drop = set(e.lower() for e in _removals(action))
    after = [e for e in base if e.lower() not in drop]
    add = action.get("add")
    if add and add not in after:
        after.append(add)
    return sorted(after)


def _lower(emails: List[str]) -> List[str]:
    return sorted(e.lower() for e in emails)


def _parse_not_before(value: Any) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else None


def diff_action(client: Any, action: Dict[str, Any]) -> Dict[str, Any]:
    """What this one action would do, measured against live right now."""
    op = action.get("op")
    row = {"op": op, "system": action.get("system"), "applicable": op in EXECUTABLE_OPS,
           "blocked": None, "manual": None, "satisfied": None, "warning": None,
           "live": None, "before": None, "after": None}
    if op in MANUAL_OPS or action.get("system") == "manual":
        # **Manual is not blocked.** A manual op is a note to a human, not half
        # a change, and lumping the two together made the all-or-nothing rule
        # refuse any proposal that mixed them. A retire_domain that bundled
        # `stop_using_domain` could therefore never be applied at all: the most
        # consequential level 3 verdict in the system was executable only by
        # hand in the UI, with no diff, no backup and no audit row.
        row["manual"] = "manual: %s is work outside this script (registrar, Instantly UI)" % op
        return row
    if op in ("pause_account", "resume_account"):
        email = action.get("email")
        row["target"] = email
        try:
            acc = client._get("accounts/%s" % email)
        except Exception as exc:  # noqa: BLE001
            row["blocked"] = "could not read the account (%s)" % str(exc)[:160]
            return row
        status = acc.get("status")
        row["live"] = {"status": status, "warmup_status": acc.get("warmup_status"),
                       "stat_warmup_score": acc.get("stat_warmup_score")}
        row["before"] = status
        row["after"] = 2 if op == "pause_account" else 1
        if status == row["after"]:
            # **Satisfied is not blocked.** The most likely human response to a
            # critical card is to pause the inbox in the Instantly UI. Treating
            # that as a blocker made the all-or-nothing rule refuse the whole
            # proposal, so the campaign's email_list could never be patched and
            # re-running the monitor regenerated the same dead proposal every
            # day, leaving a paused inbox sitting in every campaign.
            row["satisfied"] = "already %s (status %s); nothing to do" % (
                "paused" if row["after"] == 2 else "active", status)
        return row
    if op == "patch_campaign_email_list":
        cid = action.get("campaign_id")
        row["target"] = "%s (%s)" % (action.get("campaign_key"), cid)
        row["campaign_id"] = cid
        row["campaign_key"] = action.get("campaign_key")
        try:
            camp = client.get_campaign(cid)
        except Exception as exc:  # noqa: BLE001
            row["blocked"] = "could not read the campaign (%s)" % str(exc)[:160]
            return row
        live_list = sorted(camp.get("email_list") or [])
        expected = sorted(action.get("expected_before") or [])
        row["live"] = live_list
        row["before"] = live_list
        target = _target_list(expected, action)
        if live_list != expected and _lower(live_list) == _lower(target):
            # GOL-17: a PATCH from an earlier, partly failed run of this same
            # proposal already landed here. That is done work, not a blocker,
            # so a re-run finishes the campaigns that are still missing.
            row["after"] = live_list
            row["satisfied"] = ("already applied: live email_list is this proposal's target list "
                                "(%d inboxes)" % len(live_list))
            return row
        if live_list != expected:
            row["blocked"] = (
                "live email_list no longer matches the list this proposal was built from "
                "(live has %d, the proposal expected %d; added=%s removed=%s). Re-run the monitor "
                "so the diff is computed from what is actually there."
                % (len(live_list), len(expected),
                   sorted(set(live_list) - set(expected)) or "-",
                   sorted(set(expected) - set(live_list)) or "-"))
            return row
        raw_remove = _removals(action)
        after = _target_list(live_list, action)
        row["after"] = after
        if after == live_list:
            row["satisfied"] = "no change: %s is not in email_list" % (
                ", ".join(raw_remove) or "nothing")
        elif len(after) < MIN_EMAIL_LIST_AFTER_APPLY:
            row["blocked"] = ("this would leave %s with %d sending inbox(es); the floor is %d"
                              % (action.get("campaign_key"), len(after), MIN_EMAIL_LIST_AFTER_APPLY))
        elif len(after) < WARN_EMAIL_LIST_AFTER_APPLY:
            row["warning"] = ("this leaves %s with %d sending inbox(es), about %d sends/day; the "
                              "comfortable floor is %d"
                              % (action.get("campaign_key"), len(after),
                                 len(after) * TH.PER_INBOX_DAILY_LIMIT, WARN_EMAIL_LIST_AFTER_APPLY))
        return row
    row["blocked"] = "unknown op %r" % op
    row["applicable"] = False
    return row


# A proposal in one of these states is (re-)planned from live. apply_failed is
# retried rather than skipped (GOL-17): the monitor's regenerated proposal of the
# same id inherits that status, and every action is recomputed from live anyway.
PLANNABLE_STATUSES = (None, "proposed", "apply_failed")


def plan(client: Any, changeset: Dict[str, Any], only_id: Optional[str] = None,
         now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    rows = []
    for proposal in changeset.get("proposals") or []:
        if only_id and proposal.get("id") != only_id:
            continue
        if proposal.get("status") not in PLANNABLE_STATUSES:
            rows.append({"proposal": proposal, "skipped": "status is %r" % proposal.get("status"),
                         "actions": []})
            continue
        if proposal.get("not_before") is not None:
            # The M1 L2 placement re-test is staged at the pause and may not run
            # until its not_before (jobs/inbox_placement.py). An unreadable or
            # zone-less date is refused rather than guessed.
            not_before = _parse_not_before(proposal.get("not_before"))
            if not_before is None:
                rows.append({"proposal": proposal, "actions": [], "not_before": True,
                             "skipped": "not_before %r is not an ISO timestamp with a timezone; "
                                        "refusing to guess when it is due" % proposal.get("not_before")})
                continue
            if now < not_before:
                rows.append({"proposal": proposal, "actions": [], "not_before": True,
                             "skipped": "not due until %s (not_before); nothing may run before then"
                                        % proposal.get("not_before")})
                continue
        if proposal.get("status") == "apply_failed":
            logger.info("%s was marked apply_failed; re-planning it from live", proposal.get("id"))
        actions = [diff_action(client, a) for a in proposal.get("actions") or []]
        # Four buckets, not two. Only ``blocked`` stops an apply.
        rows.append({
            "proposal": proposal, "skipped": None, "actions": actions,
            "executable": [a for a in actions
                           if a["applicable"] and not a.get("blocked") and not a.get("satisfied")],
            "blocked": [a for a in actions if a.get("blocked")],
            "manual": [a for a in actions if a.get("manual")],
            "satisfied": [a for a in actions if a.get("satisfied")],
            "warnings": [a for a in actions if a.get("warning")],
        })
    return rows


def print_plan(rows: List[Dict[str, Any]], out: Callable[[str], None] = print) -> None:
    if not rows:
        out("nothing to do: the change-set has no proposal matching that filter")
        return
    for row in rows:
        p = row["proposal"]
        out("")
        out("[%s] L%s %s %s" % (p.get("severity", "?").upper(), p.get("level"), p.get("kind"), p.get("target")))
        out("  id:        %s" % p.get("id"))
        out("  reason:    %s" % p.get("reason"))
        if p.get("note"):
            out("  note:      %s" % p["note"])
        if p.get("first_seen"):
            out("  proposed:  %s (status %s)" % (p["first_seen"], p.get("status", "proposed")))
        if row.get("skipped"):
            out("  SKIPPED:   %s" % row["skipped"])
            continue
        for a in row["actions"]:
            out("  - %s %s" % (a["op"], a.get("target", "")))
            if a.get("blocked"):
                out("      BLOCKED: %s" % a["blocked"])
                continue
            if a.get("manual"):
                out("      FOLLOW-UP (not executed here): %s" % a["manual"])
                continue
            if a.get("satisfied"):
                out("      ALREADY DONE: %s" % a["satisfied"])
                continue
            if a.get("warning"):
                out("      WARNING: %s" % a["warning"])
            if a["op"] == "patch_campaign_email_list":
                before, after = a["before"], a["after"]
                out("      email_list %d -> %d" % (len(before), len(after)))
                for e in sorted(set(before) - set(after)):
                    out("        - %s" % e)
                for e in sorted(set(after) - set(before)):
                    out("        + %s" % e)
            else:
                out("      status %s -> %s" % (a["before"], a["after"]))
    out("")


# =========================================================================
# Applying
# =========================================================================

_NO_BACKUP = ("REFUSED: the backup of %s could not be written, so this write was NOT sent. The undo "
              "path the runbook documents is that backup file; without it a bad PATCH is "
              "unrecoverable. Check changesets/backups/ is writable and re-run.")


def _stop(record: Dict[str, Any], results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    record["stopped_here"] = True
    results.append(record)
    return results


def apply_rows(client: Any, rows: List[Dict[str, Any]], now: datetime,
               backup_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Execute the non-blocked actions. Requires live; backs up first.

    **Stops at the first failed action** (GOL-17). The caller re-plans from
    live, so what landed shows as satisfied and a re-run finishes the rest.
    Every campaign PATCH re-reads the campaign first: it is skipped when live
    already holds the target list, refused when live moved since the plan,
    and settled by changesets/rollback.py (verified, or re-read after an error)
    so the before-image is never left mislabelled.
    """
    require_live("instantly", "inbox_actions")
    results = []  # type: List[Dict[str, Any]]
    for row in rows:
        p = row["proposal"]
        for action in row.get("executable") or []:
            op = action["op"]
            record = {"proposal_id": p.get("id"), "op": op, "target": action.get("target")}
            try:
                if op == "patch_campaign_email_list":
                    cid = action.get("campaign_id")
                    # Back up the WHOLE campaign object, not just the list: a
                    # PATCH that goes wrong is restored from this file. **The
                    # backup is a precondition, not a courtesy.** It used to
                    # return None on a full disk or an unwritable directory and
                    # the PATCH went out anyway, with record['backup'] holding
                    # the string "None" so the printed line still looked like a
                    # path. CLAUDE.md's rule is that a live apply backs up the
                    # current object first, and the runbook promises the backup
                    # is the undo path.
                    camp = client.get_campaign(cid)
                    live_list = sorted(camp.get("email_list") or [])
                    if _lower(live_list) == _lower(action["after"]):
                        record["skipped"] = "live already holds the target list; nothing sent"
                        results.append(record)
                        continue
                    if live_list != sorted(action.get("before") or []):
                        record["error"] = ("live email_list changed between the plan and the write "
                                           "(live %d, planned from %d); nothing sent"
                                           % (len(live_list), len(action.get("before") or [])))
                        return _stop(record, results)
                    backup = _backup("inbox_actions_campaign_%s" % cid, camp, now, backup_dir,
                                     kind=R.KIND_PREAPPLY, fields=["email_list"], campaign_id=cid,
                                     campaign_key=action.get("campaign_key"),
                                     after={"email_list": action["after"]})
                    if backup is None:
                        record["error"] = _NO_BACKUP % ("campaign %s" % cid)
                        return _stop(record, results)
                    settled = R.patch_and_settle(client, cid, {"email_list": action["after"]},
                                                 str(backup), {"email_list": camp.get("email_list") or []})
                    record["backup"] = settled["path"]
                    record["outcome"] = settled["outcome"]
                    record["result"] = settled["response"]
                    if not settled["ok"]:
                        record["error"] = settled["error"] or R.describe_outcome(settled)
                        record["detail"] = R.describe_outcome(settled)
                elif op in ("pause_account", "resume_account"):
                    acc = client._get("accounts/%s" % action["target"])
                    backup = _backup("inbox_actions_account_%s" % action["target"], acc, now, backup_dir,
                                     kind=R.KIND_EVIDENCE, object_type="account")
                    if backup is None:
                        record["error"] = _NO_BACKUP % ("account %s" % action["target"])
                        return _stop(record, results)
                    record["backup"] = str(backup)
                    want = 2 if op == "pause_account" else 1
                    resp = (client.pause_account(action["target"]) if op == "pause_account"
                            else client.resume_account(action["target"]))
                    record["result"] = resp
                    status = resp.get("status") if isinstance(resp, dict) else None
                    if status is None:
                        status = (client._get("accounts/%s" % action["target"]) or {}).get("status")
                    if status != want:
                        record["error"] = ("%s acknowledged but the account reports status %r, not %d"
                                           % (op, status, want))
                else:
                    record["error"] = "not executable: %s" % op
            except Exception as exc:  # noqa: BLE001 - recorded, then the run stops
                record["error"] = str(exc)[:400]
                logger.warning("%s on %s failed: %s", op, action.get("target"), exc)
            if record.get("error"):
                return _stop(record, results)
            results.append(record)
    return results


def mark_applied(path: Path, results: List[Dict[str, Any]], now: datetime) -> None:
    """Write the outcome back into the change-set so a second run does not
    re-apply what already landed."""
    try:
        data = load_changeset(path)
    except (OSError, ValueError):
        return
    applied = set(r["proposal_id"] for r in results if not r.get("error"))
    failed = set(r["proposal_id"] for r in results if r.get("error"))
    stamp = now.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    for p in data.get("proposals") or []:
        if p.get("id") in failed:
            p["status"] = "apply_failed"
            p["applied_at"] = stamp
        elif p.get("id") in applied:
            p["status"] = "applied"
            p["applied_at"] = stamp
    tmp = path.with_suffix(".json.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)
            fh.write("\n")
        os.replace(str(tmp), str(path))
    except OSError as exc:
        logger.warning("could not update %s: %s", path, exc)


def main(argv: Optional[List[str]] = None, client: Any = None,
         out: Callable[[str], None] = print, confirm: Optional[Callable[[str], str]] = None,
         now: Optional[datetime] = None, directory: Optional[Path] = None) -> int:
    p = argparse.ArgumentParser(prog="apply_inbox_actions",
                                description="Apply proposed inbox actions from the deliverability monitor")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="read-only diff against live (default)")
    g.add_argument("--apply", action="store_true",
                   help="execute ONE proposal (MODE=live + ALLOW_LIVE_WRITES=1 only)")
    g.add_argument("--restore", metavar="ROLLBACK_POINT",
                   help="PATCH one campaign's email_list back from a rollback point this script "
                        "wrote (live only; needs --campaign)")
    p.add_argument("--campaign", help="campaign key from config/ids.json (with --restore)")
    p.add_argument("--accept-interrupted", action="store_true",
                   help="with --restore: also accept a .preapply file left by a run that died mid-PATCH")
    p.add_argument("--override-later-changes", action="store_true",
                   help="with --restore: restore even though email_list changed after the apply (undoes that too); never with --yes")
    p.add_argument("--backup-dir", help=argparse.SUPPRESS)
    p.add_argument("--date", help="change-set date (default: the newest file in this folder)")
    p.add_argument("--dir", help="change-set folder (default: changesets/inbox_actions)")
    p.add_argument("--id", help="proposal id (required with --apply)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--yes", action="store_true",
                   help="skip the typed confirmation on --apply and on --restore; the live flags are "
                        "still required, and it is refused together with --override-later-changes")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    now = now or datetime.now(timezone.utc)

    if R.override_with_yes(args):
        out(R.OVERRIDE_WITH_YES)
        return EXIT_REFUSED
    if args.restore:
        return _restore(args, client, out, confirm, now)
    restore_logs = None
    if not args.apply:
        # Every other --dry-run entry point in this component does this. Without
        # it a rehearsal of the apply diff appended a row to the production
        # .tmp/job_log.csv, which is the file the 48-hour shadow watch reads and
        # which was quarantined once already for exactly this kind of pollution.
        #
        # This main() is called as a library function by the tests, so the
        # redirection is undone on the way out: use_scratch_logs sets process
        # environment variables and leaving them set would silently reroute
        # every later caller's Job_Log rows.
        from shared.job_log import use_scratch_logs

        restore_logs = {k: os.environ.get(k) for k in ("JOB_LOG_PATH", "SHADOW_LOG_PATH")}
        use_scratch_logs("apply_inbox_actions_dryrun")
    try:
        return _main(args, client, out, confirm, now, directory)
    finally:
        for key, value in (restore_logs or {}).items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _restore(args: Any, client: Any, out: Callable[[str], None],
             confirm: Optional[Callable[[str], str]], now: datetime) -> int:
    """GOL-17: put one campaign's email_list back from this script's rollback point."""
    campaign_id = R.campaign_id_for(args.campaign or "")
    if not campaign_id:
        out("REFUSED: --restore needs --campaign <key> from config/ids.json (got %r)" % args.campaign)
        return EXIT_INVALID
    kinds = (R.KIND_APPLY, R.KIND_PREAPPLY) if args.accept_interrupted else (R.KIND_APPLY,)
    try:
        R.load_point(args.restore, SCRIPT, campaign_id, kinds)
    except R.RollbackRefused as exc:
        out("REFUSED: %s" % exc)
        log_run(JOB, "restore_refused", {"backup": args.restore, "error": str(exc)[:300]})
        return EXIT_INVALID
    if not settings.is_live():
        out("REFUSED: --restore is a live write and needs MODE=live and ALLOW_LIVE_WRITES=1 (have "
            "MODE=%s). Nothing was read or written." % settings.get_mode())
        return EXIT_REFUSED
    def typed() -> bool:
        if args.yes:
            return True
        answer = (confirm or input)("Type the campaign key (%s) to confirm the LIVE restore: " % args.campaign)
        return answer.strip() == args.campaign

    if client is None:
        try:
            from shared.instantly import default_client
            client = default_client()
        except Exception as exc:  # noqa: BLE001
            out("REFUSED: no Instantly client (%s)" % exc)
            return EXIT_REFUSED
    backup_dir = Path(args.backup_dir) if args.backup_dir else BACKUP_DIR
    stem = "inbox_actions_campaign_%s_before_%s" % (campaign_id, R.stamp(now))
    try:
        code, info = R.restore(client, SCRIPT, args.restore, campaign_id, args.campaign,
                               str(backup_dir), stem, now, out, accept_kinds=kinds, confirm=typed,
                               override_later_changes=args.override_later_changes)
    except Exception as exc:  # noqa: BLE001
        out("API error: %s" % str(exc)[:300])
        log_run(JOB, "restore_error", {"backup": args.restore, "error": str(exc)[:300]})
        return 3
    log_run(JOB, "restored" if code == EXIT_OK else "restore_failed", info)
    return code


def _main(args: Any, client: Any, out: Callable[[str], None],
          confirm: Optional[Callable[[str], str]], now: datetime,
          directory: Optional[Path]) -> int:

    directory = Path(directory) if directory else (Path(args.dir) if args.dir else CHANGESET_DIR)
    path = changeset_path(args.date, directory)
    if path is None:
        out("no change-set found in %s%s" % (directory, " for %s" % args.date if args.date else ""))
        return EXIT_INVALID
    try:
        changeset = load_changeset(path)
    except (OSError, ValueError) as exc:
        out("could not read %s: %s" % (path, exc))
        return EXIT_INVALID
    out("change-set: %s (%d proposal(s), generated %s)" % (
        path, len(changeset.get("proposals") or []), changeset.get("generated_at")))

    if args.apply and not args.id:
        out("REFUSED: --apply needs --id <proposal id>. Live application is one proposal at a time, "
            "so a bad threshold cannot pause the fleet in one command.")
        return EXIT_REFUSED

    if client is None:
        try:
            from shared.instantly import default_client
            client = default_client()
        except Exception as exc:  # noqa: BLE001
            out("REFUSED: no Instantly client (%s). The diff is computed against live; without a "
                "client there is nothing to diff and the plan would be fiction." % exc)
            return EXIT_REFUSED

    rows = plan(client, changeset, only_id=args.id, now=now)
    if args.json:
        out(json.dumps(rows, indent=2, default=str))
    else:
        print_plan(rows, out=out)

    if not args.apply:
        out("dry-run only; nothing was changed. mode=%s" % settings.get_mode())
        log_run(JOB, "dry_run", {"changeset": str(path), "proposals": len(rows),
                                 "blocked": sum(len(r.get("blocked") or []) for r in rows),
                                 "manual": sum(len(r.get("manual") or []) for r in rows),
                                 "satisfied": sum(len(r.get("satisfied") or []) for r in rows)})
        return EXIT_OK

    if not rows:
        out("REFUSED: no proposal with id %r in %s" % (args.id, path))
        return EXIT_REFUSED
    executable = [a for r in rows for a in (r.get("executable") or [])]
    blocked = [a for r in rows for a in (r.get("blocked") or [])]
    manual = [a for r in rows for a in (r.get("manual") or [])]
    satisfied = [a for r in rows for a in (r.get("satisfied") or [])]
    skipped = [r for r in rows if r.get("skipped")]
    if skipped and not executable and all(r["proposal"].get("status") == "applied" for r in skipped):
        out("Nothing to do: proposal %s is already applied (%s). Nothing sent."
            % (args.id, skipped[0]["proposal"].get("applied_at")))
        log_run(JOB, "already_applied", {"changeset": str(path), "id": args.id})
        return EXIT_OK
    if skipped and not executable:
        out("REFUSED: %s" % "; ".join("%s: %s" % (r["proposal"].get("id"), r["skipped"]) for r in skipped))
        log_run(JOB, "skipped", {"changeset": str(path), "id": args.id,
                                 "reasons": [r["skipped"] for r in skipped]})
        return EXIT_REFUSED
    if not executable:
        if manual and not blocked:
            out("Nothing for this script to execute: all %d action(s) in this proposal are manual "
                "follow-up work. They are printed above." % len(manual))
            log_run(JOB, "manual_only", {"changeset": str(path), "id": args.id,
                                         "manual": len(manual)})
            return EXIT_OK
        if satisfied and not blocked:
            out("Nothing left to do: all %d action(s) are already in the desired state." % len(satisfied))
            log_run(JOB, "already_applied", {"changeset": str(path), "id": args.id})
            return EXIT_OK
        out("REFUSED: nothing executable. %d action(s) blocked." % len(blocked))
        return EXIT_REFUSED
    # **Only a genuine blocker refuses.** A manual op is a note to a human and a
    # satisfied op is work somebody already did; counting either as "half a
    # change" made retire_domain permanently unapplyable and stopped a
    # hand-paused inbox from ever being removed from its campaigns.
    if blocked:
        out("REFUSED: %d of %d actions in this proposal are blocked. A partial apply would leave the "
            "campaign half-changed (paused inbox still in email_list, or the reverse). Fix the "
            "blockers or re-run the monitor." % (len(blocked), len(blocked) + len(executable)))
        return EXIT_REFUSED
    if manual:
        out("NOTE: %d action(s) in this proposal are manual follow-up work and will NOT be executed. "
            "The %d executable action(s) below will run." % (len(manual), len(executable)))
    if satisfied:
        out("NOTE: %d action(s) are already in the desired state and will be skipped."
            % len(satisfied))

    if not args.yes:
        prompt = confirm or input
        answer = prompt("Type the proposal id (%s) to confirm the LIVE change: " % args.id)
        if answer.strip() != args.id:
            out("aborted: confirmation did not match")
            return EXIT_REFUSED
    try:
        results = apply_rows(client, rows, now, Path(args.backup_dir) if args.backup_dir else None)
    except LiveWriteBlocked as exc:
        out("REFUSED: %s" % exc)
        return EXIT_REFUSED
    for r in results:
        out("%-30s %-14s %s" % (r.get("op"), r.get("target"),
                                r.get("error") or r.get("skipped")
                                or json.dumps(r.get("result"), default=str)[:120]))
        if r.get("backup"):
            out("    before-image: %s (%s)" % (r["backup"], r.get("outcome") or "evidence"))
        if r.get("detail"):
            out("    %s" % r["detail"])
    for a in manual:
        out("FOLLOW-UP (do this yourself): %s" % a["manual"])
    if any(r.get("error") for r in results):
        # GOL-17: stopped at the first failure. Show what live looks like now,
        # so what landed reads as satisfied and a re-run finishes the rest.
        out("")
        out("STOPPED at the first failed write; nothing after it was sent. Re-planned from live:")
        try:
            print_plan(plan(client, changeset, only_id=args.id, now=now), out=out)
        except Exception as exc:  # noqa: BLE001
            out("  (the re-plan could not read live: %s)" % str(exc)[:200])
        out("Re-run the same --apply --id once the cause is fixed; landed PATCHes are skipped.")
    mark_applied(path, results, now)
    log_run(JOB, "applied" if not any(r.get("error") for r in results) else "apply_partial",
            {"changeset": str(path), "id": args.id, "results": results})
    return EXIT_OK if not any(r.get("error") for r in results) else EXIT_INVALID


if __name__ == "__main__":
    sys.exit(main())
