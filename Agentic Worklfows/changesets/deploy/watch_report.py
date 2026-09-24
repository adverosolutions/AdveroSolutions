#!/usr/bin/env python3
"""Read-only report on the DEPLOYED evidence against the 48-hour shadow exit criteria.

    cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
    python3 changesets/deploy/watch_report.py --since "$(cat .tmp/deploy/report_start.txt)"   # the watch gate
    python3 changesets/deploy/watch_report.py                       # shadow evidence, since the first record
    python3 changesets/deploy/watch_report.py --store-mode live --min-hours 1 --since <cutover time>
    python3 changesets/deploy/watch_report.py --json

Every Job_Log row and every shadow record a Modal container writes is mirrored
into the evidence Dict of its mode (``advero-reply-engine-obs-shadow`` or
``-live``) under ``obs:job:*`` and ``obs:shadow:*`` (shared.job_log). This
script reads those keys back. It never writes to a Dict (it opens it with
create_if_missing=False and only lists and reads). It writes one local file:
the would_do records, for Lorenzo to read. It also reads the laptop runner's
own record, .tmp/laptop_runs/runs.jsonl.

Automated criteria (each PASS or FAIL):
  * there is evidence at all, and it spans at least --min-hours (48);
  * every deployed Modal schedule was due at least once, and EVERY run due
    before the last timeout window left its ``modal.<name>`` row within its
    timeout (no slack: a daily job that missed one run fails);
  * every Job_Log status is on the explicit healthy list (HEALTHY_STATUSES).
    Anything else fails, including a status this file has never heard of;
    the failing job/status pairs are listed;
  * zero ``live_write_*`` rows and zero records made in live mode;
  * the laptop: every laptop schedule due in the window has a runner record
    starting within LAPTOP_START_GRACE of its due time, and every record is
    ``ok`` with no warning. A laptop schedule never due in the window (the
    weekly ones) is listed as not proven, not passed. --skip-laptop turns the
    laptop half into a NOT CHECKED line.
--since is the REPORT START (changesets/deploy/watch_clock.py start-report,
.tmp/deploy/report_start.txt), set once the app is up, the laptop agents are
installed and the first-poll backlog has drained. It is NOT the hand-off start
(.tmp/deploy/handoff_start.txt, written before the first deploy): every cron
due before the app existed would count as missed forever.

Jobs Lorenzo turned off (config/turned_off_jobs.json) are listed as turned
off, never checked, and a ``turned_off`` runner record is healthy.

Manual criteria (NOT checked here, listed every time): every would_do is an
action Lorenzo would have taken, a push arrived each morning, one approval
card was tapped end to end, no positive waited more than 24 hours.

The text report prints the full job/status table.

Exit 0 only when every automated criterion passed; 1 when one failed; 2 when
the store could not be read. It never reports the gate as passed: the manual
items decide it. Python 3.9.
"""
import argparse
import bisect
import collections
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from changesets.deploy import common
except ImportError:  # run as a script
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from changesets.deploy import common

# Every Job_Log status the deployed code writes that means "this went as
# designed". Anything NOT in this set fails the watch, known or not (review
# item 1). changesets/tests/test_deploy_watch_report.py scans the deployed
# modules and fails when a status is in neither this set nor KNOWN_FAILURES.
HEALTHY_STATUSES = frozenset([
    "tick",                                            # modal_app: a scheduled run finished
    "ok", "dry_run",                                   # jobs and the web event path
    "approvals_waiting",                               # poller: cards wait on Lorenzo (the manual criteria)
    "created", "would_send", "sent", "queued", "vetoed", "retry", "superseded", "edited",
    "accepted_requested", "escalated", "expired",      # approval: the card life cycle
    # approval: Lorenzo pressed Mark sent on a card stuck at send_failed, or at
    # sending past its lease, whose reply did go out
    # (approval.mark_sent_manually). An operator action that closes a failure
    # the watch already has: the send_failed row the failed attempt wrote, or,
    # for a card taken from sending (whose worker wrote nothing), the
    # send_never_finished row written beside it.
    "sent_manually",
    # approval: Book as asked lost its card to a send, a newer reply or a hold
    # while the call was being booked; the call was cancelled again without
    # notifying the lead and Lorenzo was pushed. A cancel GHL refused writes
    # booking_cancel_failed beside it, which fails the watch.
    "book_as_asked_undone",
    "booking_released", "booking_transferred", "booking_cancel_retry_ok",
    "ignored_campaign",                                # web: an event for a campaign not in scope
    "recipient_hold_resumed", "d1_veto_window_deferred",   # cadence: designed holds that resolved
    # CT3 (template auto-send). approval: a card whose text is exactly an
    # approved template went out (or was queued) with no tap, or its auto-send
    # left it to Lorenzo as an ordinary card ("Not auto-sent: <reason>"); the
    # gate refused a queued template card at send time (a revoke, the kill
    # switch, a redeploy) and it went back to him as a pending card. Each is
    # the rule working; a push that did not go out writes push_failed.
    "template_auto_sent", "template_auto_not_sent", "template_auto_send_refused",
    # approval: the timed auto-send skipped a first reply (Lorenzo's rule:
    # first replies are drafts he sends himself); its card stays pending.
    "auto_send_refused_first_reply",
    # cadence: a touch held because its template is not approved (counted in
    # the FYI), and a ladder resumed after such a stop.
    "template_held", "template_hold_resumed",
    # cadence (section 1, P3b): the tick found Lorenzo's own first reply in the
    # Instantly thread and recorded it as day 0 (cadence.detect_manual_first_reply).
    "first_reply_from_thread",
    # approval: that first reply's pending card closed as sent_manually
    # (approval.mark_answered_in_thread); nothing sent, nothing pushed.
    "card_closed_from_thread",
])
# Statuses the deployed code is known to write that FAIL the watch. Listed so
# the classification is complete and reviewable; failing does not depend on
# this list (anything not healthy fails).
KNOWN_FAILURES = frozenset([
    "error", "failed", "entrypoint_missing", "refused", "partial", "dry_run_partial",
    "errors", "replies_stuck", "flush_failed", "escalation_failed",             # poller
    "push_failed", "send_failed", "recipient_mismatch", "recipient_unconfirmed", "recipient_held",
    "stale_slots", "interest_failed_after_send", "show_rate_release_failed", "invite_release_failed",
    "booking_cancel_failed", "booking_cancel_retries", "booking_cancelled_by_hand",
    "booking_passed_before_approval", "booking_settle_failed", "flush_send_raised",
    "auto_send", "auto_send_refused_unpushed",                                   # approval
    "mark_sent_record_not_updated",   # approval: Mark sent won, the lead's row was not read or written
    # approval: a held-up send went through after its card was already
    # recorded as sent (Mark sent took over its stale claim, or another send
    # of it finished first): recorded once, but the lead may have two replies
    "sent_after_card_sent",
    # approval: Mark sent or Retry took over a card stuck at sending: its send
    # started and never finished, and its worker (dead, or held up past the
    # lease) wrote no row of its own; this is the watch's only record of it
    "send_never_finished",
    "d1_held_no_base_url", "d6_card_no_base_url",                               # cadence
    "warned",                                                                    # llm.budget near its cap
    "skipped_no_token",                                                          # ghl
    "ghl_contact_needs_identity",   # ghl: a live contact with no email and no phone, refused before any request
    "live_write_failed",                                                         # a live write that failed
    # CT3. approval: an auto-send raised (its card was pushed instead); a card
    # whose auto-send never ran (a crash between the card and the send) was
    # pushed by the orphan sweep. poller: the orphan sweep or the FYI push
    # raised. cadence: a ladder stopped after TEMPLATE_HOLD_STALL_DAYS of
    # holds on an unapproved template (Lorenzo approves it, then resumes).
    "template_auto_send_failed", "template_auto_send_orphan_pushed",
    "orphan_sweep_failed", "autosend_fyi_failed",
    "template_unapproved_stop",
    # Section 2 (show_rate, no_show): a reminder or no-show email whose send
    # request went out and failed or returned nothing (it may have reached
    # the lead; never retried, checked by hand), and one held because the
    # lead's thread or row could not be trusted (fix the data).
    "show_rate_maybe_sent", "show_rate_needs_attention",
    "no_show_maybe_sent", "no_show_needs_attention",
])
FAIL_PREFIXES = ("skipped_", "blocked_", "live_write")
LIVE_WRITE_PREFIX = "live_write"
# A live write that failed is a failure first: it fails the health criterion
# in live as well as the zero-live-writes criterion in shadow.
LIVE_WRITE_FAILED = ("live_write_failed",)
DEFAULT_MIN_HOURS = 48.0
DEFAULT_MODAL_TIMEOUT_S = 600
# A Modal cron can start a little after its minute; the row is written when
# the body ends, within the function's timeout.
MODAL_START_GRACE_S = 120
# A Modal run that starts this soon after the previous run of the same job
# ended was queued behind it (max_containers=1); see match_runs.
QUEUED_GAP_S = 90
QUEUED_CLOCK_SKEW_S = 5
# launchd starts a calendar job within seconds; the runner records its start.
LAPTOP_START_GRACE_S = 15 * 60
# ``ok``, plus the designed outcomes laptop_runner.DESIGNED_OUTCOMES records
# (the list factory's Sunday run with paid calls off), plus ``turned_off`` (a
# plist still loaded for a job Lorenzo turned off: not run, by design).
# ``self_test_ok`` is the no-job self-test the 2c kick-start runs.
LAPTOP_HEALTHY = ("ok", "paid_calls_off", "turned_off", "self_test_ok")
MANUAL_CRITERIA = (
    "every would_do record is an action Lorenzo would have taken himself (read the file named above)",
    "at least one push arrived on the phone each morning (a silent 48 hours is a failure)",
    "at least one approval card was tapped end to end from the phone",
    "no positive reply waited more than 24 hours in the 07:30 sweep digest",
)


# ------------------------------------------------------------------ reading
def iter_prefix(store, prefix: str) -> Iterable[Tuple[str, Any]]:
    """(key, value) for every key under ``prefix``, read-only.

    A modal.Dict streams items() in batches; one get() per key would be
    thousands of round trips for a 48-hour watch."""
    raw = getattr(store, "_dict", None)
    if raw is not None and hasattr(raw, "items"):
        for key, value in raw.items():
            if str(key).startswith(prefix):
                yield str(key), value
        return
    for key in store.keys(prefix):
        yield key, store.get(key)


def parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        ts = datetime.fromisoformat(text)
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def load_records(store) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    from shared.job_log import OBS_JOB_PREFIX, OBS_SHADOW_PREFIX

    jobs = [dict(v, _key=k) for k, v in iter_prefix(store, OBS_JOB_PREFIX) if isinstance(v, dict)]
    shadows = [dict(v, _key=k) for k, v in iter_prefix(store, OBS_SHADOW_PREFIX) if isinstance(v, dict)]
    return jobs, shadows


# ---------------------------------------------------------- cron counting
def _field_values(field: str, lo: int, hi: int) -> set:
    out = set()
    for part in field.split(","):
        step = 1
        if "/" in part:
            part, step_text = part.split("/", 1)
            step = int(step_text)
        if part == "*":
            start, end = lo, hi
        elif "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(part)
        out.update(range(start, end + 1, step))
    return out


def due_times(cron: str, start: datetime, end: datetime, tz_name: str = "America/Chicago") -> List[datetime]:
    """Every time a 5-field cron (read in ``tz_name``) fires in [start, end), UTC."""
    import pytz

    minute, hour, dom, month, dow = cron.split()
    minutes = _field_values(minute, 0, 59)
    hours = _field_values(hour, 0, 23)
    doms = _field_values(dom, 1, 31)
    months = _field_values(month, 1, 12)
    dows = set(d % 7 for d in _field_values(dow, 0, 7))
    zone = pytz.timezone(tz_name)
    out = []  # type: List[datetime]
    t = start.replace(second=0, microsecond=0)
    if t < start:
        t += timedelta(minutes=1)
    while t < end:
        local = t.astimezone(zone)
        if (local.minute in minutes and local.hour in hours and local.day in doms
                and local.month in months and ((local.weekday() + 1) % 7) in dows):
            out.append(t)
        t += timedelta(minutes=1)
    return out


def expected_runs(cron: str, start: datetime, end: datetime, tz_name: str = "America/Chicago") -> int:
    """How many times a 5-field cron (read in ``tz_name``) fires in [start, end)."""
    return len(due_times(cron, start, end, tz_name))


def run_started(row: Dict[str, Any]) -> Optional[datetime]:
    """When a Modal run started: details.started_at, else the row time."""
    details = row.get("details") if isinstance(row.get("details"), dict) else {}
    return parse_ts(details.get("started_at")) or parse_ts(row.get("ts_utc"))


def is_live_write(status: Any) -> bool:
    """Any live_write_* row, failed or not: a write was attempted in live."""
    return str(status).startswith(LIVE_WRITE_PREFIX)


def classify(status: Any) -> str:
    """'healthy', 'live_write' or 'fail' (known or not). A failed live write
    (``live_write_failed``) is 'fail', never 'live_write'."""
    status = str(status)
    if status in LIVE_WRITE_FAILED:
        return "fail"
    if status.startswith(LIVE_WRITE_PREFIX):
        return "live_write"
    return "healthy" if status in HEALTHY_STATUSES else "fail"


def match_runs(cron: str, stamps: List[datetime], start: datetime, until: datetime,
               window_s: int, ends: Optional[List[Optional[datetime]]] = None) -> Dict[str, Any]:
    """Which due runs left a record.

    Only runs due before ``until - window_s`` are checked: a later one may
    still be running. Each record is credited to the LATEST due time at or
    before it (the run that wrote it) and counts only when it lands within
    ``window_s`` of that due time, so one late or manual record can never
    stand in for a missing run.

    ``ends`` (Modal rows): ``stamps`` are then the runs' START times and
    ``ends`` when each row was written. A run that started within
    QUEUED_GAP_S of the previous run's end was queued behind it
    (max_containers=1: precall_tick's slow run makes the next one wait), so
    it is credited to the EARLIEST due time it can have been waiting for:
    after the previous run's slot, at or before its own start, within
    ``window_s``. Any other run is credited by the strict rule above, so a
    run that never started is still missing. Returns due/checked counts and
    the misses."""
    checked_end = until - timedelta(seconds=window_s)
    all_due = due_times(cron, start - timedelta(days=8), until)
    due = [t for t in all_due if start <= t < checked_end]
    credited = set()
    if ends is None:
        for ts in stamps:
            i = bisect.bisect_right(all_due, ts)
            if i == 0:
                continue
            t = all_due[i - 1]
            if (ts - t).total_seconds() <= window_s:
                credited.add(t)
    else:
        runs = sorted(((s, e if e is not None else s) for s, e in zip(stamps, ends)), key=lambda r: r[0])
        prev_start = prev_end = prev_slot = None  # type: Optional[datetime]
        for run_start, run_end in runs:
            i = bisect.bisect_right(all_due, run_start)
            latest = all_due[i - 1] if i else None
            slot = None
            gap = (run_start - prev_end).total_seconds() if prev_end is not None else None
            if gap is not None and -QUEUED_CLOCK_SKEW_S <= gap <= QUEUED_GAP_S:
                lower = prev_slot
                if lower is None and prev_start is not None:
                    j = bisect.bisect_right(all_due, prev_start)
                    lower = all_due[j - 1] if j else None
                k = max(bisect.bisect_right(all_due, lower) if lower is not None else 0,
                        bisect.bisect_left(all_due, run_start - timedelta(seconds=window_s)))
                while k < i:
                    if all_due[k] not in credited:
                        slot = all_due[k]
                        break
                    k += 1
            if slot is None and latest is not None and latest not in credited \
                    and (run_start - latest).total_seconds() <= window_s:
                slot = latest
            if slot is not None:
                credited.add(slot)
            prev_start, prev_end, prev_slot = run_start, run_end, slot
    missing = [t for t in due if t not in credited]
    return {"due_in_window": len([t for t in all_due if start <= t < until]), "checked": len(due),
            "missing": [t.isoformat() for t in missing]}


# ---------------------------------------------------------------- the report
def _schedule_spec(value: Any) -> Tuple[str, int]:
    if isinstance(value, (tuple, list)):
        return str(value[0]), int(value[1])
    return str(value), DEFAULT_MODAL_TIMEOUT_S


def _laptop_section(criterion, laptop_runs: List[Dict[str, Any]], laptop_schedules: Dict[str, str],
                    start: datetime, until: datetime) -> Dict[str, Any]:
    runs = {}  # type: Dict[str, Any]
    not_proven = []  # type: List[str]
    in_window = [r for r in laptop_runs if (parse_ts(r.get("ts_start")) or until) >= start
                 and (parse_ts(r.get("ts_start")) or start) <= until]
    for name in sorted(laptop_schedules):
        stamps = [parse_ts(r.get("ts_start")) for r in in_window if r.get("name") == name]
        stamps = [t for t in stamps if t is not None]
        m = match_runs(laptop_schedules[name], stamps, start, until, LAPTOP_START_GRACE_S)
        runs[name] = dict(m, cron=laptop_schedules[name], observed=len(stamps))
        if m["checked"] == 0:
            not_proven.append("laptop %s (%s): never due in this window, nothing proven"
                              % (name, laptop_schedules[name]))
            continue
        criterion("laptop %s ran on schedule" % name, not m["missing"],
                  "%d of %d due runs started within %d min%s" % (
                      m["checked"] - len(m["missing"]), m["checked"], LAPTOP_START_GRACE_S // 60,
                      ("; missing: %s" % ", ".join(m["missing"][:5])) if m["missing"] else ""))
    bad = [r for r in in_window if r.get("status") not in LAPTOP_HEALTHY or r.get("warnings")]
    pairs = collections.Counter("%s %s%s" % (r.get("name"), r.get("status"), " (warnings)" if r.get("warnings") else "")
                                for r in bad)
    criterion("every laptop run is ok with no warning", not bad,
              "%d: %s" % (len(bad), ", ".join("%s x%d" % kv for kv in sorted(pairs.items())) or "none"))
    return {"runs": runs, "not_proven": not_proven,
            "by_name_status": dict(sorted(collections.Counter(
                "%s %s" % (r.get("name"), r.get("status")) for r in in_window).items()))}


def build_report(jobs: List[Dict[str, Any]], shadows: List[Dict[str, Any]], schedules: Dict[str, Any],
                 since: Optional[datetime], until: datetime, min_hours: float,
                 laptop_runs: Optional[List[Dict[str, Any]]] = None,
                 laptop_schedules: Optional[Dict[str, str]] = None,
                 turned_off: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """``schedules`` maps each deployed Modal schedule to its cron, or to
    (cron, timeout seconds). ``laptop_runs`` None means the laptop half was
    not checked (it is then listed as a manual item). ``turned_off`` maps a
    job Lorenzo turned off to its label; they are listed, never checked."""
    def in_window(rec):
        ts = parse_ts(rec.get("ts_utc"))
        return ts is not None and (since is None or ts >= since) and ts <= until

    jobs = [r for r in jobs if in_window(r)]
    shadows = [r for r in shadows if in_window(r)]
    stamps = [parse_ts(r.get("ts_utc")) for r in jobs + shadows]
    first = min(stamps) if stamps else None
    start = since or first
    span_hours = ((until - start).total_seconds() / 3600.0) if start else 0.0

    by_status = collections.Counter((str(r.get("job")), str(r.get("status"))) for r in jobs)
    criteria = []  # type: List[Dict[str, Any]]

    def criterion(name, passed, detail):
        criteria.append({"criterion": name, "passed": bool(passed), "detail": detail})

    criterion("evidence exists", bool(jobs), "%d Job_Log rows, %d shadow records in the window"
              % (len(jobs), len(shadows)))
    criterion("the window spans at least %g hours" % min_hours, span_hours >= min_hours,
              "%.1f hours from %s to %s" % (span_hours, start.isoformat() if start else "-", until.isoformat()))

    runs = {}
    for name in sorted(schedules):
        cron, timeout = _schedule_spec(schedules[name])
        # matched on each run's START (details.started_at; rows written
        # before it existed fall back to the row time, when the run ended)
        pairs = [(run_started(r), parse_ts(r.get("ts_utc"))) for r in jobs if r.get("job") == "modal.%s" % name]
        pairs = [(a, b) for a, b in pairs if a is not None]
        rows = [a for a, _b in pairs]
        m = match_runs(cron, rows, start, until, timeout + MODAL_START_GRACE_S,
                       ends=[b for _a, b in pairs]) if start else \
            {"due_in_window": 0, "checked": 0, "missing": []}
        runs[name] = dict(m, cron=cron, timeout_s=timeout, observed=len(rows))
        # A schedule never due in the window proved nothing, so it fails: the
        # watch has to cover a weekday for cadence_veto_ping.
        if m["checked"] == 0:
            detail = "never due before the last %ds of this window: nothing proven" % (timeout + MODAL_START_GRACE_S)
        else:
            detail = "%d of %d due runs left a row within %ds%s" % (
                m["checked"] - len(m["missing"]), m["checked"], timeout + MODAL_START_GRACE_S,
                ("; missing: %s" % ", ".join(m["missing"][:5]) + (" ..." if len(m["missing"]) > 5 else ""))
                if m["missing"] else "")
        criterion("%s ran on schedule" % name, m["checked"] > 0 and not m["missing"], detail)

    unhealthy = sorted(((job, status), n) for (job, status), n in by_status.items() if classify(status) == "fail")
    criterion("every Job_Log status is on the healthy list", not unhealthy,
              "%d row(s): %s" % (sum(n for _k, n in unhealthy),
                                 ", ".join("%s %s x%d" % (j, st, n) for (j, st), n in unhealthy) or "none"))
    live_rows = [r for r in jobs if is_live_write(r.get("status"))]
    criterion("zero live_write_* rows", not live_rows,
              "%d: %s" % (len(live_rows), ", ".join(sorted(set(str(r.get("job")) for r in live_rows))) or "none"))
    live_mode = [r for r in jobs + shadows if r.get("mode") == "live"]
    criterion("zero records written in live mode", not live_mode, "%d" % len(live_mode))

    manual = list(MANUAL_CRITERIA)
    laptop = None
    if laptop_runs is None:
        manual.append("the laptop half (--skip-laptop was given): every laptop run in "
                      ".tmp/laptop_runs/runs.jsonl is ok and on schedule")
    elif start is not None:
        laptop = _laptop_section(criterion, laptop_runs, laptop_schedules or {}, start, until)
        manual.extend(laptop["not_proven"])

    would_do = collections.Counter("%s.%s" % (r.get("system"), r.get("action")) for r in shadows)
    return {
        "window": {"since": start.isoformat() if start else None, "until": until.isoformat(),
                   "hours": round(span_hours, 2)},
        "criteria": criteria,
        "automated_passed": all(c["passed"] for c in criteria),
        "runs": runs,
        "laptop": laptop,
        "rows_by_job_status": [{"job": j, "status": st, "rows": n, "class": classify(st)}
                               for (j, st), n in sorted(by_status.items())],
        "would_do_counts": dict(sorted(would_do.items())),
        "would_do_total": len(shadows),
        "manual_not_checked": manual,
        "turned_off": dict(sorted((turned_off or {}).items())),
    }


def write_would_do(shadows: List[Dict[str, Any]], directory: str, stamp: str) -> str:
    path = os.path.join(directory, "would_do_%s.jsonl" % stamp)
    with open(path, "w", encoding="utf-8") as fh:
        for rec in sorted(shadows, key=lambda r: str(r.get("ts_utc"))):
            fh.write(json.dumps(dict((k, v) for k, v in rec.items() if k != "_key"), sort_keys=True) + "\n")
    return path


def render(report: Dict[str, Any], would_do_path: Optional[str]) -> str:
    lines = ["Shadow watch report (%s to %s, %.1f h)" % (report["window"]["since"], report["window"]["until"],
                                                         report["window"]["hours"]), ""]
    lines.append("AUTOMATED CRITERIA")
    for c in report["criteria"]:
        lines.append("  %s  %s  (%s)" % ("PASS" if c["passed"] else "FAIL", c["criterion"], c["detail"]))
    lines.append("")
    lines.append("JOB / STATUS TABLE (every Job_Log row in the window; anything not healthy fails)")
    for row in report["rows_by_job_status"]:
        lines.append("  %-10s %6d  %-40s %s" % (row["class"].upper(), row["rows"], row["job"], row["status"]))
    if report.get("laptop"):
        lines.append("")
        lines.append("LAPTOP RUNS (runs.jsonl, name and status)")
        for key, n in report["laptop"]["by_name_status"].items():
            lines.append("  %6d  %s" % (n, key))
    if report.get("turned_off"):
        lines.append("")
        lines.append("TURNED OFF (Lorenzo runs these by hand; not scheduled, not checked, never a failure)")
        for name, text in report["turned_off"].items():
            lines.append("  %-22s %s" % (name, text))
    lines.append("")
    lines.append("would_do records: %d%s" % (report["would_do_total"],
                                             ("  -> %s" % would_do_path) if would_do_path else ""))
    for name, n in report["would_do_counts"].items():
        lines.append("  %5d  %s" % (n, name))
    lines.append("")
    lines.append("MANUAL CRITERIA (not checked by this report; the gate is not passed until each is done)")
    for item in report["manual_not_checked"]:
        lines.append("  [ ] %s" % item)
    lines.append("")
    if report["automated_passed"]:
        lines.append("Automated criteria: all met. Gate: NOT YET PASSED - the manual items above decide it.")
    else:
        failed = sum(1 for c in report["criteria"] if not c["passed"])
        lines.append("Automated criteria: %d FAILED. Gate: FAILED. Do not cut over." % failed)
    return "\n".join(lines)


def deployed_schedules() -> Dict[str, Tuple[str, int]]:
    from services.reply_engine import modal_app

    return dict((name, (modal_app.SCHEDULES[name].cron, int(modal_app.MODAL_TIMEOUTS[name])))
                for name in modal_app.SCHEDULED_FUNCTIONS)


def laptop_schedules() -> Dict[str, str]:
    from services.reply_engine import modal_app

    return dict((name, modal_app.SCHEDULES[name].cron) for name in modal_app.LAPTOP_SCHEDULES)


def turned_off_jobs() -> Dict[str, str]:
    from shared import turned_off

    return dict((name, turned_off.label(name)) for name in turned_off.names())


def default_laptop_runs_path() -> str:
    from shared.paths import tmp_dir

    return os.path.join(str(tmp_dir()), "laptop_runs", "runs.jsonl")


def read_laptop_runs(path: str) -> Optional[List[Dict[str, Any]]]:
    """The runner's records, or None when the file does not exist."""
    if not os.path.isfile(path):
        return None
    out = []  # type: List[Dict[str, Any]]
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                out.append({"name": "?", "status": "unreadable_line", "ts_start": None})
                continue
            if isinstance(rec, dict):
                out.append(rec)
    return out


def main(argv: Optional[List[str]] = None, store=None, now: Optional[datetime] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--store-mode", choices=("shadow", "live"), default="shadow")
    parser.add_argument("--since", help="the REPORT start: .tmp/deploy/report_start.txt (watch_clock.py "
                                        "start-report); default: the first record in the store")
    parser.add_argument("--min-hours", type=float, default=DEFAULT_MIN_HOURS)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--laptop-runs", help="the laptop runner's record (default .tmp/laptop_runs/runs.jsonl)")
    parser.add_argument("--skip-laptop", action="store_true",
                        help="leave the laptop half out (it is then listed as NOT CHECKED)")
    args = parser.parse_args(argv)

    until = now or datetime.now(timezone.utc)
    since = parse_ts(args.since) if args.since else None
    if args.since and since is None:
        print("--since is not an ISO time: %r" % args.since)
        return 2
    if store is None:
        from shared import store as store_mod

        store = store_mod.open_obs_store(args.store_mode, create_if_missing=False)
    try:
        jobs, shadows = load_records(store)
    except Exception as exc:  # noqa: BLE001 - no evidence is not a pass
        print("could not read the %s store (%s: %s). No evidence, so nothing passed."
              % (args.store_mode, type(exc).__name__, exc))
        return 2

    laptop_runs = None  # type: Optional[List[Dict[str, Any]]]
    if not args.skip_laptop:
        laptop_runs = read_laptop_runs(args.laptop_runs or default_laptop_runs_path())
        if laptop_runs is None:
            # No file is not "nothing ran": it is no evidence, and it fails.
            laptop_runs = [{"name": "(runs.jsonl)", "status": "file_missing", "ts_start": until.isoformat()}]
    report = build_report(jobs, shadows, deployed_schedules(), since, until, args.min_hours,
                          laptop_runs=laptop_runs, laptop_schedules=laptop_schedules(),
                          turned_off=turned_off_jobs())
    in_window = [r for r in shadows if (parse_ts(r.get("ts_utc")) or until) <= until
                 and (since is None or (parse_ts(r.get("ts_utc")) or until) >= since)]
    path = write_would_do(in_window, common.deploy_tmp(), until.strftime("%Y%m%dT%H%M%SZ")) if in_window else None
    if args.json:
        print(json.dumps(dict(report, would_do_file=path), indent=2, sort_keys=True))
    else:
        print(render(report, path))
    return 0 if report["automated_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
