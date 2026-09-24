"""Hourly cadence tick (Blueprint S2): send due follow-up touches.

    python3 -m jobs.cadence_tick --dry-run
    python3 -m jobs.cadence_tick --dry-run --now 2026-09-22T10:05:00-05:00
    python3 -m jobs.cadence_tick --store /path/to/store.json --json

Loads every ``lead:*`` state from the store, evaluates the cadence for each
one at ``--now`` (default: current CT time), sends the touches that are due
through Instantly's reply endpoint (guarded: would_do in MODE=shadow), writes a
Job_Log row and sends Lorenzo one digest per tick that had anything to say.

Safe to run hourly: a lead gets at most one touch per day, D1 waits for the
30-minute veto window in live mode, and sends only happen 10:00-19:00 CT on
business days. ``--dry-run`` plans and prints; it
never mutates the store, never calls a client, never notifies.

CT3: a touch goes out only when its text is an approved template
(services/reply_engine/template_gate.py); otherwise the lead's result is
``held_template`` and its digest line names the template id (never the body).
A ladder stopped on an unapproved template whose daily Resume reminders have
ended (cadence.template_reminders_ended) is counted in one line, at most once a
CT day (REMINDERS_ENDED_KEY).
"""
import argparse
import copy
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

if __package__ in (None, ""):  # run as a script: make "shared"/"services" importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import settings
from shared import slots as slot_rules
from shared.job_log import log_run
from shared.notify import notify
from shared.settings import TZ, get_mode, is_live
from shared.store import ABSENT, JsonFileStore, Store, get_store

from services.reply_engine import cadence
from services.reply_engine.approval import save_stale_write

logger = logging.getLogger("jobs.cadence_tick")

JOB = "cadence_tick"
# Everything Lorenzo must see in the digest. "error", "send_failed" and
# "blocked_copy" are in here on purpose: a lead that silently stops advancing is
# the failure mode that costs a positive reply.
ACTIONABLE = ("would_send", "sent", "stopped", "follow_up_later", "veto_window_opened",
              "skipped_no_slots", "skipped_unverified_slots", "vetoed", "error", "send_failed", "blocked_copy",
              "blocked_copy_stalled", "veto_undeliverable",
              "already_sent", "awaiting_fresh_draft", "resumed_after_auto_reply", "held_template")
# Actions that mean the tick did not do its job; the Job_Log row says "errors".
# held_template (CT3): the day's template is not approved, so nothing went out.
PROBLEM_ACTIONS = ("error", "send_failed", "blocked_copy", "blocked_copy_stalled", "veto_undeliverable",
                   "skipped_no_slots", "skipped_unverified_slots", "held_template")
# A touch that actually went out (or would have, in shadow). Everything else in
# ACTIONABLE is a report, not a touch, and counting skips as touches made a tick
# that sent nothing read "1 touch".
TOUCH_ACTIONS = ("would_send", "sent")
# A lead is claimed for this long while it is being ticked, so a second worker
# (a retried Modal schedule, a manual run alongside cron) skips it instead of
# sending the same touch twice.
LOCK_SECONDS = 900
# The day (CT) the "reminders ended" line last went out: it is said once a CT
# day, not every hourly tick. One key, overwritten; no lead data in it.
REMINDERS_ENDED_KEY = "cadence_digest:reminders_ended"


def _clients(dry_run: bool):
    """Instantly/GHL clients. Both are optional: without a key/token the
    cadence still plans (default slot grid) and every send is a guard record."""
    instantly = None
    ghl = None
    if dry_run:
        return None, None
    try:
        from shared.instantly import default_client
        instantly = default_client()
    except Exception as exc:  # noqa: BLE001 - missing key is fine in shadow
        logger.warning("Instantly client unavailable (%s); touches will be guard records only", exc)
    try:
        from shared.ghl import GHL

        ghl = GHL()
    except Exception as exc:  # noqa: BLE001
        logger.warning("GHL client unavailable (%s); using the default slot grid", exc)
    return instantly, ghl


def lock_key(key: str) -> str:
    return "lock:%s" % key


def _claim(store: Store, key: str, now: datetime, dry_run: bool) -> bool:
    """Claim a lead for this tick. False when another worker holds it.

    JsonFileStore locks per operation, not across the read-modify-write around a
    send, so two overlapping ticks would otherwise both load the pre-send state
    and both send the same touch.

    The claim goes through ``set_if_absent``, not ``get`` then ``set``:
    shared/store.py documents that idiom as two operations where "two workers
    both read None and both act", which is exactly the race LOCK_SECONDS exists
    for. A stale claim is taken over with ``compare_and_set`` so the takeover is
    atomic too."""
    if dry_run:
        return True
    lkey = lock_key(key)
    mine = {"ts": now.isoformat(), "pid": os.getpid()}
    try:
        if store.set_if_absent(lkey, mine):
            return True
        held = store.get(lkey)
        if isinstance(held, dict) and held.get("ts"):
            ts = slot_rules.parse_iso(held["ts"])
            if ts is not None and (now - slot_rules.to_tz(ts)).total_seconds() < LOCK_SECONDS:
                return False
        # Expired (or malformed): take it over only if nobody else did first.
        return bool(store.compare_and_set(lkey, held, mine))
    except Exception as exc:  # noqa: BLE001 - a store without locking must not stop the tick
        logger.warning("could not claim %s: %s", key, exc)
        return True


def _release(store: Store, key: str, dry_run: bool) -> None:
    if dry_run:
        return
    try:
        store.delete(lock_key(key))
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not release %s: %s", key, exc)


def _normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """A stored row in the shape the tick writes (round-tripped through
    LeadState), so the merge compares like with like."""
    return cadence.state_to_dict(cadence.state_from_dict(row))


def _stop_for_a_reply_under_lock(ct: datetime, box: Dict[str, Any]):
    """save_stale_write's ``finish`` for this tick's write: a ladder left
    running is stopped when the row, as it stands under the lock, shows a
    reply of the lead's since the ladder last took stock of the thread
    (cadence.human_reply_since_baseline).

    The tick decides on the copy it read. A reply processed while the tick
    held that copy does not touch the stop fields when the ladder was already
    stopped (an out-of-office stopped it and this tick is resuming the pause),
    so the merge keeps the tick's un-stop and the reply is left under a
    running ladder. The reply pipeline's own rule is applied again here, where
    the reply is visible. Pure: it must not touch the store (see
    approval.save_stale_write)."""

    def _finish(merged: Dict[str, Any]) -> Dict[str, Any]:
        state = cadence.state_from_dict(merged)
        cad = getattr(state, "cadence", None) or {}
        if not cad.get("armed_at") or cad.get("stopped_reason"):
            return merged
        human = cadence.human_reply_since_baseline(state)
        if not human:
            return merged
        cadence.stop(state, "inbound_reply", ct)
        box["stopped_for"] = human
        logger.warning("stopped the ladder for %s under the lock: reply %s landed while this tick held its copy",
                       getattr(state, "lead_email", None), human)
        return cadence.state_to_dict(state)

    return _finish


def _digest_line(result: Dict[str, Any]) -> str:
    line = cadence.summarize_touch(result)
    if result.get("persist_error"):
        line += (" | lead row NOT SAVED (%s): the next tick re-reads this lead, and a day already sent is "
                 "repaired from its touch marker, never sent twice" % result["persist_error"])
    return line


def _reminders_ended_line(count: int) -> str:
    """The daily word on held ladders whose Resume reminders have ended.
    Counts only (the topic may be public): no lead, company or email."""
    if count == 1:
        return ("1 follow-up ladder is still held on an email you haven't approved yet; its daily reminders "
                "ended. Approve it in the emails doc (a Resume link then comes at once), or answer the lead by "
                "hand.")
    return ("%d follow-up ladders are still held on emails you haven't approved yet; their daily reminders "
            "ended. Approve them in the emails doc (a Resume link then comes at once), or answer the leads by "
            "hand." % count)


def _claim_reminders_ended(store: Store, ct: datetime) -> bool:
    """True when this tick is the first of the CT day to say the line. The
    marker is written with compare_and_set, so two overlapping ticks cannot
    both say it; a store that cannot be read or written says nothing."""
    today = ct.date().isoformat()
    try:
        held = store.get(REMINDERS_ENDED_KEY)
        if isinstance(held, dict) and held.get("on") == today:
            return False
        return bool(store.compare_and_set(REMINDERS_ENDED_KEY, ABSENT if held is None else held,
                                          {"on": today, "at": ct.isoformat()}))
    except Exception as exc:  # noqa: BLE001 - a marker failure must not end the tick
        logger.warning("could not record the reminders-ended line for %s: %s", today, exc)
        return False


def run(now: datetime, store: Store, instantly: Any = None, ghl: Any = None, dry_run: bool = False,
        free_slots: Optional[List[Any]] = None, notify_fn: Any = notify, log_fn: Any = log_run) -> Dict[str, Any]:
    """One tick over every lead:* state. Returns the summary that is logged."""
    ct = slot_rules.to_tz(now)
    results = []  # type: List[Dict[str, Any]]
    keys = store.keys("lead:")
    for key in keys:
        raw = store.get(key)
        if not isinstance(raw, dict):
            continue
        try:
            state = cadence.state_from_dict(raw)
        except Exception as exc:  # noqa: BLE001 - one bad record must not stop the tick
            logger.warning("skipping %s: %s", key, exc)
            results.append({"key": key, "action": "error", "error": str(exc)})
            continue
        if not (getattr(state, "cadence", None) or {}).get("armed_at"):
            continue
        if not _claim(store, key, ct, dry_run):
            results.append({"key": key, "lead_email": getattr(state, "lead_email", None), "action": "locked"})
            continue
        # The claim has to span the whole read-modify-write, not just the tick:
        # releasing before the persist left a window in which a second worker
        # could re-enter tick_lead with the state it read beforehand and then
        # clobber this worker's write (losing the offered_slots it just added).
        # What this tick read, in the shape it writes back. The write below is
        # a merge against it, not a whole-row set: a reply that stops the
        # ladder, or a cancel retry that settles the booking, while this tick
        # is working must survive the tick's write (SAL-4, defect 3).
        base = copy.deepcopy(cadence.state_to_dict(state))
        try:
            try:
                res = cadence.tick_lead(state, ct, store=store, instantly=instantly, ghl=ghl, free_slots=free_slots,
                                        dry_run=dry_run, notify_fn=notify_fn)
            except Exception as exc:  # noqa: BLE001
                logger.exception("tick failed for %s", key)
                res = {"key": key, "lead_email": getattr(state, "lead_email", None), "action": "error", "error": str(exc)}
            # "error" is persisted too: cadence.tick_lead records the touch before any
            # post-send step can fail, so dropping the state here would re-send it.
            # A deferred D1 veto window is a "not_due" that moved next_send_at
            # to the day the send can really happen: it has to be persisted, or
            # the next tick re-reads the old time and opens the window at 07:00.
            persist = res.get("action") not in ("not_due", "not_armed", "already_stopped", "locked") or \
                res.get("reason") == "veto_window_deferred"
            if not dry_run and persist:
                box = {}  # type: Dict[str, Any]
                try:
                    save_stale_write(store, key, cadence.state_to_dict(state), base, normalize=_normalize_row,
                                     finish=_stop_for_a_reply_under_lock(ct, box))
                except Exception as exc:  # noqa: BLE001 - one lead's row (a lock timeout) must not end the tick
                    # for every lead after it. Nothing is lost that the next tick cannot redo: it re-reads
                    # this lead, and a day already sent is repaired from its touch marker, never re-sent.
                    logger.error("could not save %s after its tick (%s): %s", key, res.get("action"), exc)
                    res = dict(res, persist_error="%s: %s" % (type(exc).__name__, exc))
                else:
                    if box.get("stopped_for") and res.get("action") in TOUCH_ACTIONS:
                        res = dict(res, stopped_after=box["stopped_for"])
                    elif box.get("stopped_for"):
                        res = dict(res, action="stopped", reason="inbound_reply", needs_fresh_draft=True,
                                   decided=res.get("action"), stopped_for=box["stopped_for"])
        finally:
            _release(store, key, dry_run)
        # A held ladder whose daily Resume reminder has reached its cap shows up
        # nowhere else. A lead the reminder is withheld from (resume_withheld:
        # nurture, or one the ladder is over for) is not counted; dry runs do not
        # take that branch of tick_lead, so they count nothing.
        if (not dry_run and res.get("action") == "already_stopped" and res.get("reason") == "template_unapproved"
                and not res.get("resume_withheld") and cadence.template_reminders_ended(state, ct)):
            res["reminders_ended"] = True
        res["key"] = key
        results.append(res)

    counts = {}  # type: Dict[str, int]
    for r in results:
        counts[r.get("action", "?")] = counts.get(r.get("action", "?"), 0) + 1
    # ``quiet`` marks a result the engine has already reported for this lead and
    # day (a repeated copy block, a repeated slot skip, a held veto). It stays in
    # counts and in the Job_Log row; it just does not re-ping Lorenzo every hour.
    unsaved = [r for r in results if r.get("persist_error")]
    digest_lines = [_digest_line(r) for r in results
                    if (r.get("action") in ACTIONABLE and not r.get("quiet")) or r.get("persist_error")]
    reminders_ended = len([r for r in results if r.get("reminders_ended")])
    if reminders_ended and not dry_run and _claim_reminders_ended(store, ct):
        digest_lines.append(_reminders_ended_line(reminders_ended))
    summary = {
        "now": ct.isoformat(),
        "mode": get_mode(),
        "live": is_live(),
        "dry_run": dry_run,
        "leads_seen": len(keys),
        "leads_armed": len(results),
        "counts": counts,
        "digest": digest_lines,
        "reminders_ended": reminders_ended,
        "results": results,
    }
    problems = sum(counts.get(a, 0) for a in PROBLEM_ACTIONS) + len(unsaved)
    summary["problems"] = problems
    summary["unsaved"] = len(unsaved)
    # What the digest title counts: the touches that went out, and the problems
    # that are new (a repeat the engine has already reported today stays out of
    # the title as well as out of the lines).
    touches = sum(counts.get(a, 0) for a in TOUCH_ACTIONS)
    needs_you = len([r for r in results
                     if (r.get("action") in PROBLEM_ACTIONS and not r.get("quiet")) or r.get("persist_error")])
    summary["touches"] = touches
    summary["needs_you"] = needs_you
    status = "dry_run" if dry_run else ("errors" if problems else "ok")
    log_fn(JOB, status, {k: v for k, v in summary.items() if k != "results"})
    if digest_lines and not dry_run:
        title = "Cadence %s: %d touch%s" % (ct.strftime("%a %H:%M CT"), touches, "" if touches == 1 else "es")
        if needs_you:
            title = "%s, %d need%s you" % (title, needs_you, "s" if needs_you == 1 else "")
        if not is_live():
            title = "[shadow] " + title
        notify_fn(title, "\n".join(digest_lines), priority="high" if needs_you else "default", tags=["calendar"])
    return summary


def _print_table(summary: Dict[str, Any]) -> None:
    print("cadence_tick @ %s  mode=%s live=%s dry_run=%s" % (summary["now"], summary["mode"], summary["live"], summary["dry_run"]))
    print("leads in store: %d, armed: %d" % (summary["leads_seen"], summary["leads_armed"]))
    for r in summary["results"]:
        line = "  %-14s %-45s" % (r.get("action"), r.get("lead_email") or r.get("key"))
        if r.get("day") is not None:
            line += " D%-2s" % r.get("day")
        if r.get("next_send_at"):
            line += " next=%s" % r["next_send_at"]
        if r.get("reason"):
            line += " reason=%s" % r["reason"]
        tid = r.get("template_id") or (r.get("touch") or {}).get("template_id")
        if tid:
            line += " template=%s" % tid
        touch = r.get("touch")
        if touch:
            line += " slots=%s src=%s" % (
                ",".join(slot_rules.format_slot(slot_rules.parse_iso(s)) for s in touch.get("slots") or []) or "-",
                touch.get("slots_source"),
            )
        print(line)
    if summary["digest"]:
        print("digest:")
        for d in summary["digest"]:
            print("  " + d)


def _print_touch_bodies(summary: Dict[str, Any]) -> None:
    for r in summary["results"]:
        touch = r.get("touch")
        if not touch:
            continue
        print("\n--- %s D%s (%s) ---\nSubject: %s\n%s" % (r.get("lead_email"), touch["day"], touch["intent"], touch["subject"], touch["body_text"]))


def main(argv: Optional[List[str]] = None, store: Optional[Store] = None, now: Optional[datetime] = None) -> int:
    p = argparse.ArgumentParser(prog="cadence_tick", description=__doc__.split("\n\n")[0])
    p.add_argument("--dry-run", action="store_true", help="plan only: no store writes, no sends, no notifications")
    p.add_argument("--now", help="ISO timestamp to evaluate at (default: current time, America/Chicago)")
    p.add_argument("--store", help="path to a JSON store (default: STORE_PATH or .tmp/store.json)")
    p.add_argument("--json", action="store_true", help="print the full summary as JSON")
    p.add_argument("--bodies", action="store_true", help="print the planned email bodies")
    args = p.parse_args(argv)

    if args.dry_run:
        # a dry run must not write into the job log the 48-hour shadow watch is
        # gated on reading. See shared.job_log.use_scratch_logs.
        from shared.job_log import use_scratch_logs

        use_scratch_logs("cadence_tick_dryrun")

    if now is None:
        now = slot_rules.parse_iso(args.now) if args.now else datetime.now(TZ)
    if store is None:
        store = JsonFileStore(args.store) if args.store else get_store()

    # Bound and closed, the way cadence.tick closes them: the CLI is the shape a
    # cron-driven run takes, and leaving two httpx pools to the garbage collector
    # is the asymmetry that bites once this is wrapped in a loop.
    instantly, ghl = _clients(args.dry_run)
    try:
        summary = run(now, store, instantly, ghl, dry_run=args.dry_run)
    finally:
        for client in (instantly, ghl):
            try:
                if client is not None:
                    client.close()
            except Exception:  # noqa: BLE001 - closing a client must not fail the run
                logger.warning("could not close %r", client)
    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        _print_table(summary)
        if args.bodies:
            _print_touch_bodies(summary)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "WARNING"))
    sys.exit(main())
