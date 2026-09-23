#!/usr/bin/env python3
"""Oct 11 capacity change-set: add warmed inboxes to a campaign's email_list and
set its daily_limit, one campaign at a time (GOL-8, M2 / A5).

Which inboxes go into which campaign, and each campaign's daily_limit, are NOT
in this file. Option A and Option B (R8) are defined in
runbooks/DECISIONS_FOR_LORENZO.md Q-L1, the same as
changesets/capacity/domain_order.md; which one to run is Lorenzo's choice, so
the plan comes from an input file he fills in once he has chosen. The shape is
shown by
``changesets/capacity/oct11_capacity.example.json``, which is an EXAMPLE: it
says ``"example": true`` and ``--apply`` refuses it.

Dry-run (the default, zero writes), all campaigns in the file or one:
    cd "Agentic Worklfows"
    python3 changesets/capacity/apply_capacity.py --input changesets/capacity/oct11_capacity.json
    python3 changesets/capacity/apply_capacity.py --input <file> --campaign cleaning_reactivation

Apply (live flags, ONE campaign, typed confirmation):
    MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/capacity/apply_capacity.py \\
        --input <file> --campaign cleaning_reactivation --apply

Restore (live flags, typed confirmation):
    MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/capacity/apply_capacity.py \\
        --restore changesets/backups/capacity_<campaign_id>_<ts>.json --campaign cleaning_reactivation

What the apply does, in order:
  1. reads the live campaign and the live account list (GET only);
  2. works out what is missing: the inboxes from the input that are not yet in
     the live ``email_list`` (live order kept, new ones appended) and whether
     ``daily_limit`` differs. When nothing differs it stops there: nothing is
     sent and nothing is written, so a re-run never replaces the rollback
     point (safe re-run);
  3. refuses unless every inbox it would add is an existing, enabled Instantly
     account (status 1, not setup_pending) that is warmed: warm-up running
     (warmup_status 1), warm-up score at least TH.WARMUP_HEALTH_MIN_PCT, and
     warming for at least TH.WARMUP_DAYS_BEFORE_PROMOTION days. It also
     refuses a domain the additions push past TH.MAX_INBOXES_PER_DOMAIN;
  4. writes the before-image (changesets/backups/capacity_<id>_<ts>.preapply.json),
     PATCHes only the fields that differ (``email_list``, ``daily_limit`` or
     both) and settles the before-image through changesets/rollback.py into
     the rollback point ``capacity_<id>_<ts>.json``;
  5. writes a Job_Log row.

After the typed confirmation the campaign is read AGAIN; when ``email_list``
(as a set) or ``daily_limit`` moved while the prompt was open, nothing is sent
or written and the run exits 2 with the difference. The fresh read is the
before-image. A live read without an ``email_list`` list is refused outright.

``--restore`` reads live first, prints what it would change, refuses when a
field changed after the apply (``--override-later-changes`` to undo that too),
then asks for confirmation and PATCHes back exactly the fields that apply
changed (both when both changed). It skips when live already matches and
refuses any file that is not a capacity rollback point for that campaign.

Warm-age: an inbox must have warmed TH.WARMUP_DAYS_BEFORE_PROMOTION (21) days.
The 33 inboxes whose warm-up started 2026-09-20T23:39Z are 20.6 days old at
14:00 UTC on Oct 11 and are refused until about 18:40 CT that day.

``config/`` is baked into the Modal image at deploy time. Nothing here reads or
writes ``config/``, but the go-live checklist's redeploy step after the
capacity change still applies to the jobs that read capacity figures.

Exit codes: 0 ok, 1 invalid input or refused plan, 2 live write refused, 3 API error.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from shared import settings  # noqa: E402
from shared import thresholds as TH  # noqa: E402
from shared.instantly import default_client, InstantlyError  # noqa: E402
from shared.job_log import log_run  # noqa: E402
from changesets import rollback as R  # noqa: E402

SCRIPT = "capacity"
JOB = "capacity_oct11_apply"
BACKUP_DIR = os.path.join(ROOT, "changesets", "backups")
EXAMPLE_PATH = os.path.join(HERE, "oct11_capacity.example.json")

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_REFUSED = 2
EXIT_API = 3

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _domain(email: str) -> str:
    return email.split("@", 1)[1].lower() if "@" in email else ""


# ------------------------------------------------------------------ the input
def load_input(path: str) -> Tuple[Dict[str, Any], List[str]]:
    """(document, problems). Every problem is a refusal; nothing is guessed."""
    with open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    problems = []  # type: List[str]
    if not isinstance(doc, dict):
        return {}, ["%s is not a JSON object" % path]
    if not isinstance(doc.get("option"), str) or not doc.get("option").strip():
        problems.append("`option` is missing: name the capacity option this file implements (R8)")
    campaigns = doc.get("campaigns")
    if not isinstance(campaigns, dict) or not campaigns:
        problems.append("`campaigns` must be a non-empty object keyed by campaign key")
        return doc, problems
    total = doc.get("expected_total_daily_limit")
    if not isinstance(total, int) or isinstance(total, bool) or total <= 0:
        problems.append("`expected_total_daily_limit` must be a positive integer: it is the "
                        "cross-check that catches a typo in one campaign's daily_limit")
    running = 0
    for key, spec in sorted(campaigns.items()):
        where = "campaigns.%s" % key
        canonical = R.campaign_id_for(key)
        if not canonical:
            problems.append("%s: not a campaign key in config/ids.json" % where)
            continue
        if not isinstance(spec, dict):
            problems.append("%s: must be an object" % where)
            continue
        if spec.get("campaign_id") != canonical:
            problems.append("%s: campaign_id %r does not match config/ids.json (%s)"
                            % (where, spec.get("campaign_id"), canonical))
        limit = spec.get("daily_limit")
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            problems.append("%s: daily_limit must be a positive integer" % where)
        else:
            running += limit
        adds = spec.get("add_inboxes")
        if not isinstance(adds, list):
            problems.append("%s: add_inboxes must be a list (it may be empty)" % where)
            continue
        lowered = [str(e).strip().lower() for e in adds]
        bad = [e for e in lowered if not EMAIL_RE.match(e)]
        if bad:
            problems.append("%s: not email addresses: %s" % (where, bad))
        if len(set(lowered)) != len(lowered):
            problems.append("%s: add_inboxes lists an inbox twice" % where)
    if isinstance(total, int) and not isinstance(total, bool) and running and running != total:
        problems.append("the campaigns' daily_limits add up to %d, but expected_total_daily_limit "
                        "says %d" % (running, total))
    return doc, problems


# ------------------------------------------------------------------ planning
def _age_days(account: Dict[str, Any], now: datetime) -> Optional[float]:
    raw = account.get("timestamp_warmup_start")
    if not raw:
        return None
    try:
        started = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if started.tzinfo is None:
        return None
    return (now - started).total_seconds() / 86400.0


def inbox_problems(email: str, account: Optional[Dict[str, Any]], now: datetime) -> List[str]:
    """Why ``email`` may not be added. Empty means it exists and is warmed."""
    if account is None:
        return ["%s is not an Instantly account" % email]
    out = []
    if int(account.get("status") or 0) != 1 or account.get("setup_pending"):
        out.append("%s is not enabled (status=%s setup_pending=%s)"
                   % (email, account.get("status"), account.get("setup_pending")))
    if account.get("warmup_status") != 1:
        out.append("%s has no running warm-up (warmup_status=%s)" % (email, account.get("warmup_status")))
    score = account.get("stat_warmup_score")
    if score is None:
        out.append("%s has no warm-up score: it cannot be called warmed" % email)
    elif float(score) < TH.WARMUP_HEALTH_MIN_PCT:
        out.append("%s warm-up score %s is under %s" % (email, score, TH.WARMUP_HEALTH_MIN_PCT))
    age = _age_days(account, now)
    if age is None:
        out.append("%s has no readable timestamp_warmup_start" % email)
    elif age < TH.WARMUP_DAYS_BEFORE_PROMOTION:
        out.append("%s has warmed %.1f days, under the %d-day minimum"
                   % (email, age, TH.WARMUP_DAYS_BEFORE_PROMOTION))
    return out


def plan_campaign(key: str, spec: Dict[str, Any], live: Dict[str, Any],
                  accounts: List[Dict[str, Any]], now: datetime) -> Dict[str, Any]:
    by_email = dict(((a.get("email") or "").lower(), a) for a in accounts)
    problems = []  # type: List[str]
    warnings = []  # type: List[str]
    if not isinstance(live.get("email_list"), list):
        # Re-review defect 4: `live.get("email_list") or []` turned a read
        # that omitted the field into "the campaign has no inboxes", and the
        # PATCH then replaced the real list with only the additions.
        problems.append("the live read of %s carries no email_list list (got %r); refusing, because "
                        "a PATCH built from it would replace the real list with only the additions"
                        % (key, type(live.get("email_list")).__name__))
    live_list = list(live.get("email_list") or [])
    live_lower = set(e.lower() for e in live_list)
    wanted = [str(e).strip().lower() for e in spec.get("add_inboxes") or []]
    to_add = [e for e in wanted if e not in live_lower]
    desired_list = live_list + to_add
    desired_limit = spec.get("daily_limit")
    patch = {}  # type: Dict[str, Any]
    if to_add:
        patch["email_list"] = desired_list
    if live.get("daily_limit") != desired_limit:
        patch["daily_limit"] = desired_limit
    if live.get("id") != spec.get("campaign_id"):
        problems.append("live campaign id %s is not %s" % (live.get("id"), spec.get("campaign_id")))
    for email in to_add:
        problems.extend(inbox_problems(email, by_email.get(email), now))
    for email in live_list:
        acc = by_email.get(email.lower())
        if acc is None or int(acc.get("status") or 0) != 1:
            warnings.append("%s is already in the live list but is not an enabled account "
                            "(left as it is; this change-set only adds)" % email)
    before_counts = {}  # type: Dict[str, int]
    for email in live_list:
        before_counts[_domain(email)] = before_counts.get(_domain(email), 0) + 1
    after_counts = dict(before_counts)
    for email in to_add:
        after_counts[_domain(email)] = after_counts.get(_domain(email), 0) + 1
    for domain in sorted(after_counts):
        if after_counts[domain] > TH.MAX_INBOXES_PER_DOMAIN:
            if after_counts[domain] > before_counts.get(domain, 0):
                problems.append("%s would have %d inboxes in this campaign (cap %d)"
                                % (domain, after_counts[domain], TH.MAX_INBOXES_PER_DOMAIN))
            else:
                warnings.append("%s already has %d inboxes in this campaign (cap %d)"
                                % (domain, after_counts[domain], TH.MAX_INBOXES_PER_DOMAIN))
    ceiling = len(desired_list) * TH.PER_INBOX_DAILY_LIMIT
    if isinstance(desired_limit, int) and desired_limit > ceiling:
        warnings.append("daily_limit %d is above what %d inboxes at %d/day can send (%d)"
                        % (desired_limit, len(desired_list), TH.PER_INBOX_DAILY_LIMIT, ceiling))
    return {"key": key, "campaign_id": spec.get("campaign_id"), "live_list": live_list,
            "already_in": [e for e in wanted if e in live_lower], "to_add": to_add,
            "desired_list": desired_list, "live_limit": live.get("daily_limit"),
            "desired_limit": desired_limit, "patch": patch, "problems": problems,
            "warnings": warnings}


def print_plan(pl: Dict[str, Any], out: Callable[[str], None]) -> None:
    out("=" * 78)
    out("%s  (%s)" % (pl["key"], pl["campaign_id"]))
    out("  email_list: %d live, %d already there, %d to add -> %d"
        % (len(pl["live_list"]), len(pl["already_in"]), len(pl["to_add"]), len(pl["desired_list"])))
    for email in pl["to_add"]:
        out("    + %s" % email)
    out("  daily_limit: %s -> %s%s" % (pl["live_limit"], pl["desired_limit"],
                                       "" if "daily_limit" in pl["patch"] else " (no change)"))
    out("  PATCH fields: %s" % (sorted(pl["patch"]) or "none: live already matches"))
    for w in pl["warnings"]:
        out("  WARNING %s" % w)
    for p in pl["problems"]:
        out("  REFUSED %s" % p)


# ---------------------------------------------------------------------- main
def _stem(campaign_id: str, now: datetime) -> str:
    return "%s_%s_%s" % (SCRIPT, campaign_id, R.stamp(now))


def _moved_since(first: Dict[str, Any], fresh: Dict[str, Any]) -> List[str]:
    """What changed in email_list (as a set) or daily_limit between two reads."""
    lines = []
    if not isinstance(fresh.get("email_list"), list):
        lines.append("email_list is missing from the fresh read")
    elif not R.field_equal("email_list", first.get("email_list"), fresh.get("email_list")):
        lines.append(R.describe_field_change("email_list", first.get("email_list"), fresh.get("email_list")))
    if first.get("daily_limit") != fresh.get("daily_limit"):
        lines.append("daily_limit %r -> %r" % (first.get("daily_limit"), fresh.get("daily_limit")))
    return lines


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="apply_capacity", description=__doc__.split("\n\n")[0])
    p.add_argument("--input", help="the capacity plan (see oct11_capacity.example.json)")
    p.add_argument("--campaign", help="campaign key; required with --apply and --restore")
    p.add_argument("--dry-run", action="store_true", help="the default; refused with --apply or --restore")
    p.add_argument("--apply", action="store_true", help="PATCH one campaign (live flags)")
    p.add_argument("--restore", metavar="ROLLBACK_POINT", help="PATCH a capacity rollback point back (live flags)")
    p.add_argument("--accept-interrupted", action="store_true",
                   help="with --restore: also accept a .preapply file left by a run that died mid-PATCH")
    p.add_argument("--override-later-changes", action="store_true",
                   help="with --restore: restore even though a field changed after the apply (undoes that change too); never with --yes")
    p.add_argument("--yes", action="store_true", help="skip the typed confirmation")
    return p


def main(argv: Optional[List[str]] = None, client: Any = None, now: Optional[datetime] = None,
         out: Callable[[str], None] = print, backup_dir: Optional[str] = None,
         dryrun_dir: Optional[str] = None, confirm: Optional[Callable[[str], str]] = None) -> int:
    args = build_parser().parse_args(argv)
    now = now or datetime.now(timezone.utc)
    backup_dir = backup_dir or BACKUP_DIR
    if args.dry_run and (args.apply or args.restore):
        out("REFUSED: --dry-run cannot be combined with --apply or --restore.")
        return EXIT_REFUSED
    if args.apply and args.restore:
        out("REFUSED: --apply and --restore are opposites; run one at a time.")
        return EXIT_REFUSED
    if R.override_with_yes(args):
        out(R.OVERRIDE_WITH_YES)
        return EXIT_REFUSED
    if args.restore:
        return _restore(args, client, now, out, backup_dir, confirm)
    if args.apply:
        return _run(args, client, now, out, backup_dir, dryrun_dir, confirm)
    with R.scratch_logs(JOB + "_dryrun"):
        return _run(args, client, now, out, backup_dir, dryrun_dir, confirm)


def _confirm(args: Any, confirm: Optional[Callable[[str], str]], what: str) -> bool:
    if args.yes:
        return True
    answer = (confirm or input)("Type the campaign key (%s) to confirm the LIVE %s: " % (args.campaign, what))
    return answer.strip() == args.campaign


def _client(client: Any, out: Callable[[str], None]) -> Any:
    if client is not None:
        return client
    try:
        return default_client()
    except InstantlyError as exc:
        out("no Instantly client: %s" % exc)
        return None


def _restore(args: Any, client: Any, now: datetime, out: Callable[[str], None], backup_dir: str,
             confirm: Optional[Callable[[str], str]]) -> int:
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
        out("REFUSED: --restore needs MODE=live and ALLOW_LIVE_WRITES=1 (have MODE=%s). Nothing "
            "was read or written." % settings.get_mode())
        return EXIT_REFUSED
    client = _client(client, out)
    if client is None:
        return EXIT_API
    try:
        code, info = R.restore(client, SCRIPT, args.restore, campaign_id, args.campaign, backup_dir,
                               _stem(campaign_id, now), now, out, accept_kinds=kinds,
                               confirm=lambda: _confirm(args, confirm, "restore"),
                               override_later_changes=args.override_later_changes)
    except InstantlyError as exc:
        out("API error: %s" % str(exc)[:300])
        log_run(JOB, "restore_error", {"backup": args.restore, "error": str(exc)[:300]})
        return EXIT_API
    log_run(JOB, "restored" if code == EXIT_OK else "restore_failed", info)
    return code


def _run(args: Any, client: Any, now: datetime, out: Callable[[str], None], backup_dir: str,
         dryrun_dir: Optional[str], confirm: Optional[Callable[[str], str]]) -> int:
    if not args.input:
        out("--input <plan file> is required (see %s for the shape)" % os.path.relpath(EXAMPLE_PATH, ROOT))
        return EXIT_INVALID
    try:
        doc, problems = load_input(args.input)
    except (OSError, ValueError) as exc:
        out("cannot read %s: %s" % (args.input, exc))
        return EXIT_INVALID
    is_example = doc.get("example") is not False
    if is_example:
        out("*** %s is marked as an EXAMPLE (or does not say \"example\": false). It is shown for "
            "shape only and cannot be applied. ***" % args.input)
    if problems:
        out("input refused:")
        for p in problems:
            out("  - %s" % p)
        log_run(JOB, "input_refused", {"input": args.input, "problems": problems})
        return EXIT_INVALID
    keys = sorted(doc["campaigns"])
    if args.campaign:
        if args.campaign not in doc["campaigns"]:
            out("REFUSED: %s has no entry for %r (it has %s)" % (args.input, args.campaign, keys))
            return EXIT_INVALID
        keys = [args.campaign]
    if args.apply:
        if not args.campaign:
            out("REFUSED: --apply needs --campaign <key>; capacity is applied one campaign at a time.")
            return EXIT_REFUSED
        if is_example:
            out("REFUSED: an example file is never applied. Copy it, fill in the chosen option and "
                "set \"example\": false.")
            return EXIT_REFUSED
        if not settings.is_live():
            out("REFUSED: --apply needs MODE=live and ALLOW_LIVE_WRITES=1 (have MODE=%s). Nothing was "
                "sent." % settings.get_mode())
            log_run(JOB, "live_refused", {"input": args.input, "campaign": args.campaign})
            return EXIT_REFUSED
    out("capacity plan %s: option %s, expected total daily_limit %s"
        % (args.input, doc.get("option"), doc.get("expected_total_daily_limit")))

    client = _client(client, out)
    if client is None:
        return EXIT_API
    try:
        accounts = [a for a in client.iterate("accounts", {"limit": 100}) if isinstance(a, dict)]
    except InstantlyError as exc:
        out("could not read the account list: %s" % exc)
        return EXIT_API

    plans = []
    for key in keys:
        spec = doc["campaigns"][key]
        try:
            live = client.get_campaign(spec["campaign_id"])
        except InstantlyError as exc:
            out("could not read %s: %s" % (key, exc))
            return EXIT_API
        pl = plan_campaign(key, spec, live, accounts, now)
        pl["live"] = live
        print_plan(pl, out)
        plans.append(pl)

    if not args.apply:
        for pl in plans:
            if pl["patch"] and not pl["problems"]:
                path = R.write_point(dryrun_dir or R.dryrun_dir(SCRIPT), _stem(pl["campaign_id"], now),
                                     R.build_point(SCRIPT, R.KIND_DRYRUN, pl["live"], sorted(pl["patch"]),
                                                   now, pl["campaign_id"], pl["key"], after=pl["patch"]))
                out("  dry-run copy (not a rollback point): %s" % path)
        refused = [pl["key"] for pl in plans if pl["problems"]]
        out("")
        out("DRY-RUN: %d campaign(s), %d would change, %d refused%s. writes=0"
            % (len(plans), sum(1 for pl in plans if pl["patch"] and not pl["problems"]), len(refused),
               (" (%s)" % ", ".join(refused)) if refused else ""))
        log_run(JOB, "dry_run", {"input": args.input, "example": is_example,
                                 "plans": [{"campaign": pl["key"], "patch": sorted(pl["patch"]),
                                            "to_add": pl["to_add"], "problems": pl["problems"]}
                                           for pl in plans]})
        return EXIT_INVALID if refused else EXIT_OK

    pl = plans[0]
    if pl["problems"]:
        out("REFUSED: %d problem(s); nothing was sent." % len(pl["problems"]))
        log_run(JOB, "refused", {"campaign": pl["key"], "problems": pl["problems"]})
        return EXIT_INVALID
    if not pl["patch"]:
        out("live already matches the plan for %s; nothing sent, nothing written." % pl["key"])
        log_run(JOB, "noop", {"campaign": pl["key"], "campaign_id": pl["campaign_id"]})
        return EXIT_OK
    if not _confirm(args, confirm, "capacity change"):
        out("aborted: confirmation did not match")
        return EXIT_REFUSED
    # Re-review defect 1: the PATCH replaces email_list wholesale, so it must
    # not be built from a read taken before the prompt. Anything that changed
    # while the prompt was open (a burned inbox swapped out, a promotion in
    # another terminal) would be silently reverted.
    try:
        fresh = client.get_campaign(pl["campaign_id"])
    except InstantlyError as exc:
        out("could not re-read %s after the confirmation: %s; nothing was sent" % (pl["key"], exc))
        return EXIT_API
    moved = _moved_since(pl["live"], fresh)
    if moved:
        out("REFUSED: %s changed while the confirmation was open; nothing was sent or written:" % pl["key"])
        for line in moved:
            out("  %s" % line)
        out("Re-run the dry-run and read the new plan.")
        log_run(JOB, "refused", {"campaign": pl["key"], "changed_during_confirmation": moved})
        return EXIT_REFUSED
    fields = sorted(pl["patch"])
    try:
        preapply = R.write_point(backup_dir, _stem(pl["campaign_id"], now),
                                 R.build_point(SCRIPT, R.KIND_PREAPPLY, fresh, fields, now,
                                               pl["campaign_id"], pl["key"],
                                               extra={"input": args.input, "option": doc.get("option")},
                                               after=pl["patch"]))
    except OSError as exc:
        out("REFUSED: the before-image could not be written (%s); nothing was sent." % exc)
        log_run(JOB, "refused", {"campaign": pl["key"], "error": "backup failed: %s" % exc})
        return EXIT_REFUSED
    before = dict((k, fresh.get(k)) for k in fields)
    settled = R.patch_and_settle(client, pl["campaign_id"], pl["patch"], preapply, before)
    out(R.describe_outcome(settled))
    log_run(JOB, "applied" if settled["ok"] else "apply_unverified", {
        "campaign": pl["key"], "campaign_id": pl["campaign_id"], "fields": fields,
        "added": pl["to_add"], "daily_limit": [pl["live_limit"], pl["desired_limit"]],
        "rollback_point": settled["path"], "outcome": settled["outcome"], "error": settled["error"],
        "option": doc.get("option"),
    })
    return EXIT_OK if settled["ok"] else EXIT_API


if __name__ == "__main__":
    sys.exit(main())
