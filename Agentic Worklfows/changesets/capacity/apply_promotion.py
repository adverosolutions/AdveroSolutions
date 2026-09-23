#!/usr/bin/env python3
"""Apply an insurance-promotion change-set to a campaign's email_list (M2 / A5).

Dry-run (the default, zero writes):
    cd "Agentic Worklfows"
    python3 changesets/capacity/apply_promotion.py --changeset changesets/capacity/promote_*.json

The dry-run GETs the live campaign (read-only), re-checks every invariant the
proposal was built on and prints the email_list diff. It saves a copy of the
live campaign under .tmp/changeset_dryruns/promotion/ with the .dryrun suffix
(never in changesets/backups/, SAF-10) and logs to a scratch Job_Log. Nothing
is sent.

Apply (refused unless the process carries both live flags, one campaign at a
time, after Lorenzo has read the diff):
    MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/capacity/apply_promotion.py --changeset <file> --apply

The write itself goes through shared.instantly.Instantly.update_campaign(),
which calls settings.guard_write() first, so even a mis-run in shadow records
a would_do record and performs no HTTP request. When live already holds the
proposed list the PATCH is skipped and nothing is written, so a re-run never
replaces the rollback point. The before-image is written as
changesets/backups/promotion_<campaign_id>_<ts>.preapply.json and settled by
changesets/rollback.py into the rollback point promotion_<campaign_id>_<ts>.json.

After the "type yes" prompt the campaign is read again; if its email_list
moved while the prompt was open, nothing is sent and the run exits 2.

Rollback (live, typed confirmation, restores email_list only):
    MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/capacity/apply_promotion.py \
        --restore changesets/backups/promotion_<campaign_id>_<ts>.json --campaign <key>

The restore reads live and prints the inboxes it would remove and add before
it asks, and refuses when email_list changed after the apply unless
--override-later-changes is given.

Invariants re-checked against live before anything is applied:
  1. the campaign still exists and its id matches the change-set;
  2. the failing inbox is still in the live email_list (otherwise someone has
     already swapped it and this change-set is stale);
  3. the proposed list is EXACTLY the live list minus the failing inbox plus
     the promoted one. Any other difference means the file was hand-edited or
     built against a different estate, and the PATCH would carry addresses
     nobody reviewed;
  4. every address in the proposed list is a live, enabled Instantly account
     (not only the promoted one);
  5. the promoted inbox is not already in the list and is not in any other
     SENDING campaign, EXCEPT a sibling campaign of this same swap: one the
     failing inbox was in when the change-set was generated
     (``remaining_campaigns``) and whose live list no longer holds it. That
     is the same insurance inbox replacing the same failing inbox, one
     change-set per campaign (GOL-20 item 9);
  6. the promoted inbox's health was actually measured: a change-set whose
     candidate has no warm-up score, or whose analytics window could not be
     read, is refused. "No data" is not "clean";
  7. no domain ends up with more than 3 inboxes in this campaign;
  8. the proposed list is not empty (a campaign with no inbox stops sending).

Invariant 5 is deliberately NOT applied to the whole list. All twelve live
inboxes sit in all six campaigns (measured 2026-09-22), so requiring every
address to be in exactly one campaign would refuse every change-set this
estate can produce. It is the PROMOTED inbox that has to be genuinely spare.

Exit codes: 0 ok, 1 invalid/stale change-set, 2 live write refused, 3 API error.
"""
import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from shared import settings  # noqa: E402
from shared.instantly import default_client, InstantlyError  # noqa: E402
from shared.job_log import log_run  # noqa: E402
from changesets import rollback as R  # noqa: E402

BACKUP_DIR = os.path.join(ROOT, "changesets", "backups")
MAX_PER_DOMAIN = 3

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_REFUSED = 2
EXIT_API = 3

JOB = "capacity_promotion_apply"
SCRIPT = "promotion"


def _domain(email: str) -> str:
    return email.split("@", 1)[1].lower() if "@" in email else ""


def load_changeset(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        record = json.load(fh)
    if record.get("action") != "promote_insurance":
        raise ValueError("%s is not a promote_insurance change-set" % path)
    for field in ("campaign_id", "remove", "proposed_email_list"):
        if record.get(field) in (None, "", []):
            raise ValueError("%s is missing %s" % (path, field))
    return record


def _campaign_sends(campaign: Dict[str, Any]) -> bool:
    """A missing status is read as sending: the conservative assumption about
    an unknown campaign is that email leaves it."""
    status = campaign.get("status")
    if status is None:
        return True
    try:
        return int(status) == 1
    except (TypeError, ValueError):
        return True


def check(record: Dict[str, Any], campaign: Dict[str, Any],
          accounts: Optional[List[Dict[str, Any]]] = None,
          all_campaigns: Optional[List[Dict[str, Any]]] = None,
          warnings: Optional[List[str]] = None) -> List[str]:
    """Return the list of reasons this change-set must not be applied.

    ``warnings`` is filled with things worth printing that do not block the
    apply (membership in a paused or draft campaign, for instance).
    """
    problems = []  # type: List[str]
    warnings = warnings if warnings is not None else []
    live_list = [e.lower() for e in campaign.get("email_list") or []]
    proposed = [e.lower() for e in record.get("proposed_email_list") or []]
    failing = (record.get("remove") or "").lower()
    promoted = (record.get("promote") or "").lower() or None

    if campaign.get("id") != record.get("campaign_id"):
        problems.append("live campaign id %s does not match the change-set (%s)"
                        % (campaign.get("id"), record.get("campaign_id")))
    if failing not in live_list:
        problems.append("stale: %s is no longer in the live email_list (%d inboxes). Regenerate "
                        "the change-set with jobs/inbox_inventory.py --promote."
                        % (failing, len(live_list)))
    if not proposed:
        problems.append("the proposed email_list is empty: the campaign would stop sending")
    recorded = [e.lower() for e in record.get("current_email_list") or []]
    if sorted(live_list) != sorted(recorded):
        added = sorted(set(live_list) - set(recorded))
        gone = sorted(set(recorded) - set(live_list))
        problems.append("the live email_list has changed since the change-set was written "
                        "(live %d inboxes, change-set %d; live has %s that the change-set does "
                        "not, and the change-set has %s that live does not). Regenerate it."
                        % (len(live_list), len(recorded), added or "nothing", gone or "nothing"))

    # Invariant 3: the proposed list is the live list minus one plus one, and
    # nothing else. Without this, a hand-edited file PATCHes arbitrary
    # addresses into a live campaign and every other check still passes.
    expected = set(live_list) - {failing}
    if promoted:
        expected.add(promoted)
    if set(proposed) != expected:
        unexpected = sorted(set(proposed) - expected)
        dropped = sorted(expected - set(proposed))
        problems.append("the proposed email_list is not 'live minus %s plus %s': it adds %s and "
                        "drops %s. Only a swap this tool generated may be applied."
                        % (failing, promoted or "nothing",
                           unexpected or "nothing", dropped or "nothing"))
    if failing in proposed:
        problems.append("%s is still in the proposed email_list: the removal would not happen"
                        % failing)
    if len(set(proposed)) != len(proposed):
        problems.append("the proposed email_list contains duplicates")

    counts = {}  # type: Dict[str, int]
    for email in proposed:
        counts[_domain(email)] = counts.get(_domain(email), 0) + 1
    for domain in sorted(counts):
        if counts[domain] > MAX_PER_DOMAIN:
            problems.append("%s would have %d inboxes in this campaign (cap %d)"
                            % (domain, counts[domain], MAX_PER_DOMAIN))

    # Invariant 4: EVERY address that would be PATCHed in, not just the
    # promoted one. A ghost address in the live list PATCHes straight back.
    by_email = {}  # type: Dict[str, Dict[str, Any]]
    if accounts is not None:
        for account in accounts:
            by_email[(account.get("email") or "").lower()] = account
        for email in proposed:
            match = by_email.get(email)
            if match is None:
                problems.append("%s is in the proposed email_list but is not an Instantly account"
                                % email)
            elif int(match.get("status") or 0) != 1 or match.get("setup_pending"):
                problems.append("%s is not enabled (status=%s setup_pending=%s)"
                                % (email, match.get("status"), match.get("setup_pending")))

    if promoted:
        if promoted in live_list:
            problems.append("%s is already in the live email_list" % promoted)
        if all_campaigns is not None:
            siblings = set(record.get("remaining_campaigns") or [])
            for other in all_campaigns:
                if other.get("id") == record.get("campaign_id"):
                    continue
                other_list = [e.lower() for e in other.get("email_list") or []]
                if promoted not in other_list:
                    continue
                other_key = R.campaign_key_for(other.get("id"))
                if other_key in siblings and failing not in other_list:
                    # The same insurance inbox already replaced the same failing
                    # inbox in a sibling campaign. An inbox that sits in all six
                    # campaigns is swapped with one change-set per campaign.
                    warnings.append("%s already replaced %s in %r (a sibling change-set of this "
                                    "swap); it will now send for both"
                                    % (promoted, failing, other.get("name")))
                elif _campaign_sends(other):
                    problems.append("%s is already sending for %r; it is not insurance"
                                    % (promoted, other.get("name")))
                else:
                    warnings.append("%s also sits in %r, which is not sending today. Resuming that "
                                    "campaign would put it in two lists."
                                    % (promoted, other.get("name")))
        # Invariant 6: the health the proposal claimed must have been measured.
        health = record.get("promote_health")
        if not isinstance(health, dict):
            problems.append("the change-set records no health figures for %s: it predates the "
                            "health gate, so regenerate it with jobs/inbox_inventory.py --promote"
                            % promoted)
        else:
            if health.get("analytics_missing"):
                problems.append("%s had no 7-day analytics when it was picked: it cannot be called "
                                "the healthiest inbox" % promoted)
            if health.get("warmup_health") is None:
                problems.append("%s has no warm-up score: it cannot be called healthy" % promoted)
            if health.get("flags"):
                problems.append("%s carries flags: %s" % (promoted, ", ".join(health["flags"])))
    return problems


def diff_lines(before: List[str], after: List[str]) -> List[str]:
    before_set = set(e.lower() for e in before)
    after_set = set(e.lower() for e in after)
    lines = []
    for email in sorted(before_set - after_set):
        lines.append("  - %s" % email)
    for email in sorted(after_set - before_set):
        lines.append("  + %s" % email)
    for email in sorted(before_set & after_set):
        lines.append("    %s" % email)
    return lines


def _stem(campaign_id: str, now) -> str:
    return "%s_%s_%s" % (SCRIPT, campaign_id, R.stamp(now))


def _say(msg: str) -> None:
    print(msg)


def main(argv: Optional[List[str]] = None, client=None, now=None, backup_dir: Optional[str] = None,
         dryrun_dir: Optional[str] = None, confirm=None) -> int:
    p = argparse.ArgumentParser(prog="apply_promotion", description=__doc__.split("\n\n")[0])
    p.add_argument("--changeset", help="path to a promote_*.json change-set")
    p.add_argument("--apply", action="store_true", help="perform the PATCH (needs the live flags)")
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    p.add_argument("--dry-run", action="store_true", help="explicit dry-run (the default)")
    p.add_argument("--restore", metavar="ROLLBACK_POINT",
                   help="PATCH a promotion rollback point's email_list back (live only, needs --campaign)")
    p.add_argument("--campaign", help="campaign key from config/ids.json (with --restore)")
    p.add_argument("--accept-interrupted", action="store_true",
                   help="with --restore: also accept a .preapply file left by a run that died mid-PATCH")
    p.add_argument("--override-later-changes", action="store_true",
                   help="with --restore: restore even though email_list changed after the apply (undoes that too); never with --yes")
    args = p.parse_args(argv)
    now = now or R.utcnow()
    backup_dir = backup_dir or BACKUP_DIR

    if args.dry_run and (args.apply or args.restore):
        print("REFUSED: --dry-run cannot be combined with --apply or --restore.", file=sys.stderr)
        return EXIT_REFUSED
    if R.override_with_yes(args):
        print(R.OVERRIDE_WITH_YES, file=sys.stderr)
        return EXIT_REFUSED
    if args.restore:
        return _restore(args, client, now, backup_dir, confirm)
    if not args.changeset:
        print("--changeset is required (or --restore <file> --campaign <key>)", file=sys.stderr)
        return EXIT_INVALID
    if args.apply:
        return _main(args, client, now, backup_dir, dryrun_dir, confirm)
    with R.scratch_logs(JOB + "_dryrun"):
        return _main(args, client, now, backup_dir, dryrun_dir, confirm)


def _restore(args, client, now, backup_dir: str, confirm) -> int:
    campaign_id = R.campaign_id_for(args.campaign or "")
    if not campaign_id:
        print("REFUSED: --restore needs --campaign <key> from config/ids.json (got %r)" % args.campaign,
              file=sys.stderr)
        return EXIT_INVALID
    try:
        R.load_point(args.restore, SCRIPT, campaign_id,
                     (R.KIND_APPLY, R.KIND_PREAPPLY) if args.accept_interrupted else (R.KIND_APPLY,))
    except R.RollbackRefused as exc:
        print("REFUSED: %s" % exc, file=sys.stderr)
        log_run(JOB, "restore_refused", {"backup": args.restore, "error": str(exc)[:300]})
        return EXIT_INVALID
    if not settings.is_live():
        print("--restore refused: MODE=%s and the live-writes flag is not set. Nothing was read or "
              "written." % settings.get_mode(), file=sys.stderr)
        return EXIT_REFUSED

    def typed() -> bool:
        if args.yes:
            return True
        answer = (confirm or input)("Restore email_list of %s from %s? type the campaign key: "
                                    % (args.campaign, args.restore)).strip()
        return answer == args.campaign

    if client is None:
        try:
            client = default_client()
        except InstantlyError as exc:
            print("Instantly client: %s" % exc, file=sys.stderr)
            return EXIT_API
    kinds = (R.KIND_APPLY, R.KIND_PREAPPLY) if args.accept_interrupted else (R.KIND_APPLY,)
    try:
        code, info = R.restore(client, SCRIPT, args.restore, campaign_id, args.campaign, backup_dir,
                               _stem(campaign_id, now), now, _say, accept_kinds=kinds, confirm=typed,
                               override_later_changes=args.override_later_changes)
    except InstantlyError as exc:
        print("Instantly error: %s" % exc, file=sys.stderr)
        log_run(JOB, "restore_error", {"backup": args.restore, "error": str(exc)[:300]})
        return EXIT_API
    log_run(JOB, "restored" if code == EXIT_OK else "restore_failed", info)
    return code


def _main(args, client, now, backup_dir: str, dryrun_dir: Optional[str], confirm) -> int:
    try:
        record = load_changeset(args.changeset)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("cannot read change-set: %s" % exc, file=sys.stderr)
        return EXIT_INVALID

    if client is None:
        try:
            client = default_client()
        except InstantlyError as exc:
            print("Instantly client: %s" % exc, file=sys.stderr)
            return EXIT_API
    try:
        campaign = client.get_campaign(record["campaign_id"])
        accounts = list(client.iterate("accounts", {"limit": 100}))
        all_campaigns = list(client.iterate("campaigns", {"limit": 100}))
    except InstantlyError as exc:
        print("Instantly read failed: %s" % exc, file=sys.stderr)
        log_run(JOB, "error", {"error": str(exc)[:300], "changeset": args.changeset})
        return EXIT_API

    if not isinstance(campaign.get("email_list"), list):
        print("REFUSED: the live read of %s carries no email_list list; a PATCH built from it "
              "could wipe the campaign. Nothing was sent." % record["campaign_id"], file=sys.stderr)
        log_run(JOB, "refused", {"changeset": args.changeset, "error": "email_list missing from live read"})
        return EXIT_INVALID

    print("CHANGE-SET  %s" % args.changeset)
    print("campaign    %s (%s)" % (record.get("campaign_name"), record.get("campaign_id")))
    print("remove      %s" % record.get("remove"))
    print("promote     %s" % (record.get("promote") or "nothing (capacity drops)"))
    print("why         %s" % record.get("reason"))

    # GOL-9: when live already holds the proposed list, nothing is sent and
    # nothing is written, so a re-run can never replace the rollback point
    # with a copy of the already-changed campaign.
    if not R.mismatches(campaign, {"email_list": record["proposed_email_list"]}):
        print("")
        print("live email_list already matches the proposed list: this change-set is applied. "
              "Nothing sent, nothing written.")
        log_run(JOB, "already_applied", {"changeset": args.changeset,
                                          "campaign_id": record["campaign_id"]})
        return EXIT_OK

    warnings = []  # type: List[str]
    problems = check(record, campaign, accounts, all_campaigns, warnings=warnings)

    print("email_list diff:")
    for line in diff_lines(campaign.get("email_list") or [], record["proposed_email_list"]):
        print(line)
    print("capacity    %+d/day (estate)" % (record.get("capacity_delta_per_day") or 0))
    if record.get("capacity_note"):
        print("            %s" % record["capacity_note"])
    if record.get("remaining_campaigns"):
        print("still in    %s: this PATCH does not stop %s sending"
              % (", ".join(record["remaining_campaigns"]), record.get("remove")))
    if warnings:
        print("")
        print("WARNINGS (not blocking):")
        for warning in warnings:
            print("  - %s" % warning)

    if problems:
        print("")
        print("REFUSED, %d problem(s):" % len(problems))
        for problem in problems:
            print("  - %s" % problem)
        log_run(JOB, "refused", {"changeset": args.changeset, "problems": problems})
        return EXIT_INVALID

    campaign_key = record.get("campaign_key") or R.campaign_key_for(record["campaign_id"])
    if not args.apply:
        copy_path = R.write_point(
            dryrun_dir or R.dryrun_dir(SCRIPT), _stem(record["campaign_id"], now),
            R.build_point(SCRIPT, R.KIND_DRYRUN, campaign, ["email_list"], now,
                          record["campaign_id"], campaign_key,
                          after={"email_list": record["proposed_email_list"]}))
        print("dry-run copy %s (not a rollback point)" % copy_path)
        print("")
        print("dry-run only. To apply after Lorenzo approves this diff, set the live flags and "
              "re-run with --apply.")
        log_run(JOB, "dry_run_ok", {
            "changeset": args.changeset, "campaign_id": record["campaign_id"],
            "remove": record["remove"], "promote": record.get("promote"), "dryrun_copy": copy_path,
        })
        return EXIT_OK

    if not settings.is_live():
        print("")
        print("--apply refused: MODE=%s and the live-writes flag is not set. Nothing was sent."
              % settings.get_mode(), file=sys.stderr)
        log_run(JOB, "live_refused", {"changeset": args.changeset, "mode": settings.get_mode()})
        return EXIT_REFUSED

    if not args.yes:
        answer = (confirm or input)("Apply this email_list to the live campaign? type yes: ").strip().lower()
        if answer != "yes":
            print("aborted")
            return EXIT_REFUSED

    # Re-review defect 1: re-read after the prompt. A list that moved while
    # it was open is never overwritten with a PATCH built from the old read.
    try:
        fresh = client.get_campaign(record["campaign_id"])
    except InstantlyError as exc:
        print("could not re-read the campaign after the confirmation: %s; nothing was sent" % exc,
              file=sys.stderr)
        return EXIT_API
    if not R.field_equal("email_list", campaign.get("email_list"), fresh.get("email_list")):
        print("REFUSED: the live email_list changed while the confirmation was open; nothing was "
              "sent or written: %s" % R.describe_field_change("email_list", campaign.get("email_list"),
                                                               fresh.get("email_list")), file=sys.stderr)
        log_run(JOB, "refused", {"changeset": args.changeset, "error": "email_list changed during confirmation"})
        return EXIT_REFUSED

    try:
        preapply = R.write_point(backup_dir, _stem(record["campaign_id"], now),
                                 R.build_point(SCRIPT, R.KIND_PREAPPLY, fresh, ["email_list"], now,
                                               record["campaign_id"], campaign_key,
                                               extra={"changeset": args.changeset},
                                               after={"email_list": record["proposed_email_list"]}))
    except OSError as exc:
        print("REFUSED: the before-image could not be written (%s); nothing was sent." % exc,
              file=sys.stderr)
        log_run(JOB, "refused", {"changeset": args.changeset, "error": "backup failed: %s" % exc})
        return EXIT_REFUSED
    settled = R.patch_and_settle(client, record["campaign_id"],
                                 {"email_list": record["proposed_email_list"]}, preapply,
                                 {"email_list": fresh.get("email_list")})
    print("")
    print(R.describe_outcome(settled))
    log_run(JOB, "applied" if settled["ok"] else "apply_unverified", {
        "changeset": args.changeset, "campaign_id": record["campaign_id"],
        "remove": record["remove"], "promote": record.get("promote"),
        "rollback_point": settled["path"], "outcome": settled["outcome"], "error": settled["error"],
    })
    return EXIT_OK if settled["ok"] else EXIT_API


if __name__ == "__main__":
    sys.exit(main())
