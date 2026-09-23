#!/usr/bin/env python3
"""The shadow watch's two clocks, kept apart (D1 round 3, defect 1).

    cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
    python3 changesets/deploy/watch_clock.py show
    python3 changesets/deploy/watch_clock.py begin                 # install_schedules.sh --first-pass runs this
    python3 changesets/deploy/watch_clock.py begin --new-watch     # a new watch: archive the old files first
    python3 changesets/deploy/watch_clock.py start-report          # after 2b's second pass and 2c's kick-start
    python3 changesets/deploy/watch_clock.py start-report --restart --reason "budget cap: first-poll backlog"

Two recorded times, never one:

* the HAND-OFF START (.tmp/deploy/handoff_start.txt). Written by
  ``install_schedules.sh --deploy shadow --first-pass`` just BEFORE the first
  ``modal deploy``, so it is at or before the first reply the shadow poller can
  see. Step 5 passes it to ``cutover.py --watch-start``: every reply the shadow
  engine saw from then on is on the hand-off list. It never moves: a retried
  first pass keeps it (moving it later would drop the replies in between from
  the hand-off). A NEW watch (weeks later, after a rollback, a fresh cycle)
  archives the old files and starts over with ``begin --new-watch``; ``begin``
  refuses to reuse a hand-off start older than NEW_WATCH_AFTER_DAYS.
* the REPORT START (.tmp/deploy/report_start.txt). ``watch_report.py --since``
  reads it. It is set by ``start-report`` only once the app is really up and
  settled: the last ``verify_health.py`` in shadow passed with the URL check
  (second pass), the launchd-started self-test was recorded after the
  hand-off start with the Mac on Central Time (the 2c kick-start, so the
  agents are installed and launchd can reach the repo), and the shadow poller has a
  complete cursor (a complete scan, so the first-poll backlog has drained).
  Every cron due between the hand-off start and this moment (image build,
  first deploy, second pass, laptop install, backlog) is outside the gate.
  After a failure whose cause is KNOWN, ``start-report --restart --reason ..``
  moves only this time later, and logs why. The hand-off start stays.

Writes files under .tmp/deploy/ only (plus a Job_Log row). Reads the shadow
engine Dict for the cursor, never writes it. Python 3.9.
"""
import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

try:
    from changesets.deploy import common
except ImportError:  # run as a script
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from changesets.deploy import common

HANDOFF_START_NAME = "handoff_start.txt"
REPORT_START_NAME = "report_start.txt"
HISTORY_NAME = "watch_clock_history.jsonl"
HEALTH_HISTORY_NAME = "health_history.jsonl"
ARCHIVE_DIR = "watch_archive"
# A hand-off start older than this is a previous watch's, not a retried first
# pass: begin refuses to reuse it without --new-watch or --same-watch.
NEW_WATCH_AFTER_DAYS = 7


class ClockRefused(Exception):
    """The time cannot be recorded safely; nothing was written."""


def _path(name: str, directory: Optional[str] = None) -> str:
    return os.path.join(directory or common.deploy_tmp(), name)


def _stamp(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(value: Any) -> Optional[datetime]:
    from changesets.deploy.watch_report import parse_ts

    return parse_ts(value)


def read_time(name: str, directory: Optional[str] = None) -> Optional[datetime]:
    try:
        with open(_path(name, directory), "r", encoding="utf-8") as fh:
            return _parse(fh.read().strip())
    except OSError:
        return None


def _write_time(name: str, ts: datetime, directory: Optional[str] = None) -> str:
    path = _path(name, directory)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(_stamp(ts) + "\n")
    return path


def _history(event: Dict[str, Any], directory: Optional[str] = None) -> None:
    with open(_path(HISTORY_NAME, directory), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True) + "\n")
    try:
        from shared.job_log import log_run

        log_run("deploy.watch_clock", str(event.get("event")), event)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("could not write the Job_Log row: %s\n" % exc)


def last_health(directory: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The newest verify_health.py result (verify_health appends one per run)."""
    last = None
    try:
        with open(_path(HEALTH_HISTORY_NAME, directory), "r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if isinstance(rec, dict):
                    last = rec
    except OSError:
        return None
    return last


def archive(directory: Optional[str] = None, now: Optional[datetime] = None) -> Optional[str]:
    """Move the current watch's files into watch_archive/<stamp>/. None when there were none."""
    directory = directory or common.deploy_tmp()
    names = [n for n in (HANDOFF_START_NAME, REPORT_START_NAME, HISTORY_NAME)
             if os.path.exists(os.path.join(directory, n))]
    if not names:
        return None
    target = os.path.join(directory, ARCHIVE_DIR, (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ"))
    os.makedirs(target)
    for n in names:
        shutil.move(os.path.join(directory, n), os.path.join(target, n))
    return target


def begin(now: datetime, new_watch: bool = False, same_watch: bool = False,
          directory: Optional[str] = None) -> Dict[str, Any]:
    """Record the hand-off start before the first deploy, or keep the one on file."""
    existing = read_time(HANDOFF_START_NAME, directory)
    archived = None
    if existing is not None and not new_watch:
        if now - existing > timedelta(days=NEW_WATCH_AFTER_DAYS) and not same_watch:
            raise ClockRefused(
                "a hand-off start from %s (%d days ago) is on file. That is a previous watch, not a retried "
                "first pass. Pass --new-watch to archive it and start a fresh watch, or --same-watch to keep it."
                % (_stamp(existing), (now - existing).days))
        return {"handoff_start": _stamp(existing), "kept": True, "archived": None}
    if new_watch:
        archived = archive(directory, now)
    _write_time(HANDOFF_START_NAME, now, directory)
    _history({"event": "handoff_start", "at": _stamp(now), "new_watch": bool(new_watch), "archived": archived},
             directory)
    return {"handoff_start": _stamp(now), "kept": False, "archived": archived}


def _laptop_rows_since(since: datetime, path: Optional[str] = None) -> List[Dict[str, Any]]:
    from changesets.deploy import watch_report

    rows = watch_report.read_laptop_runs(path or watch_report.default_laptop_runs_path()) or []
    return [r for r in rows if (_parse(r.get("ts_start")) or since - timedelta(seconds=1)) >= since]


def launchd_self_test(row: Dict[str, Any]) -> bool:
    """A self_test_ok row the com.advero.self_test agent wrote (its plist sets
    the marker laptop_runner records as started_by) on a Central Time clock."""
    return (row.get("name") == "self_test" and row.get("status") == "self_test_ok"
            and row.get("started_by") == "launchd" and row.get("clock_is_central") is True)


def check_report_start(now: datetime, shadow_store, directory: Optional[str] = None,
                       skip_laptop: bool = False, laptop_runs_path: Optional[str] = None) -> List[str]:
    """Why the report start cannot be set now (empty: it can)."""
    problems = []  # type: List[str]
    handoff = read_time(HANDOFF_START_NAME, directory)
    if handoff is None:
        return ["no hand-off start is recorded (.tmp/deploy/%s): the first-pass deploy writes it; nothing else "
                "can stand in for it" % HANDOFF_START_NAME]
    health = last_health(directory)
    health_at = _parse((health or {}).get("ts_utc"))
    if not health or not health.get("passed") or health.get("expect_mode") != "shadow" or health.get("first_pass"):
        problems.append("the last verify_health.py run is not a passing SECOND-pass shadow check (%s). Run step "
                        "2b's second pass (or verify_health.py --expect-mode shadow) until it prints 'All /health "
                        "checks passed'" % (json.dumps(health, sort_keys=True) if health else "none recorded"))
    elif health_at is None or health_at < handoff:
        problems.append("the last passing /health check (%s) is older than the hand-off start (%s)"
                        % ((health or {}).get("ts_utc"), _stamp(handoff)))
    if not skip_laptop:
        rows = _laptop_rows_since(handoff, laptop_runs_path)
        if not any(launchd_self_test(r) for r in rows):
            by_hand = [r for r in rows if r.get("name") == "self_test"]
            problems.append(
                "no self_test_ok row started by launchd, with the Mac on Central Time, is recorded since the "
                "hand-off start%s: install the laptop agents and kick-start com.advero.self_test (step 2c), or "
                "pass --skip-laptop for a Modal-only watch" % (
                    " (a self-test run by hand in Terminal proves nothing about launchd)" if by_hand else ""))
    try:
        from services.reply_engine import poller

        cursor = shadow_store.get(poller.CURSOR_KEY)
    except Exception as exc:  # noqa: BLE001 - cannot read: refuse, never guess
        problems.append("the shadow engine store could not be read (%s: %s)" % (type(exc).__name__, exc))
    else:
        if not (isinstance(cursor, dict) and cursor.get("last_email_id") and cursor.get("last_timestamp")):
            problems.append("the shadow poller has no complete cursor yet, so the first-poll backlog has not "
                            "drained (it drains over several polls). Wait, then run this again")
    return problems


def start_report(now: datetime, shadow_store, restart: bool = False, reason: str = "",
                 directory: Optional[str] = None, skip_laptop: bool = False,
                 laptop_runs_path: Optional[str] = None) -> Dict[str, Any]:
    existing = read_time(REPORT_START_NAME, directory)
    if existing is not None and not restart:
        raise ClockRefused("the report start is already %s. It moves only after a failure whose cause you know: "
                           "start-report --restart --reason \"<the cause>\"" % _stamp(existing))
    if restart:
        if not (reason or "").strip():
            raise ClockRefused("--restart needs --reason: the watch clock only restarts for a known cause")
        if existing is not None and now <= existing:
            raise ClockRefused("the new report start must be later than the current one (%s)" % _stamp(existing))
    problems = check_report_start(now, shadow_store, directory, skip_laptop=skip_laptop,
                                  laptop_runs_path=laptop_runs_path)
    if problems:
        raise ClockRefused("; ".join(problems))
    path = _write_time(REPORT_START_NAME, now, directory)
    _history({"event": "report_restart" if restart else "report_start", "at": _stamp(now),
              "previous": _stamp(existing) if existing else None, "reason": reason or None,
              "skip_laptop": bool(skip_laptop)}, directory)
    return {"report_start": _stamp(now), "previous": _stamp(existing) if existing else None, "file": path}


def show(directory: Optional[str] = None) -> Dict[str, Any]:
    handoff = read_time(HANDOFF_START_NAME, directory)
    report = read_time(REPORT_START_NAME, directory)
    return {"handoff_start": _stamp(handoff) if handoff else None,
            "report_start": _stamp(report) if report else None,
            "handoff_start_file": _path(HANDOFF_START_NAME, directory),
            "report_start_file": _path(REPORT_START_NAME, directory)}


def main(argv: Optional[List[str]] = None, shadow_store=None, now: Optional[datetime] = None,
         directory: Optional[str] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="action")
    sub.add_parser("show")
    b = sub.add_parser("begin")
    b.add_argument("--new-watch", action="store_true", help="archive the previous watch's files and start fresh")
    b.add_argument("--same-watch", action="store_true", help="keep a hand-off start older than %d days"
                   % NEW_WATCH_AFTER_DAYS)
    r = sub.add_parser("start-report")
    r.add_argument("--restart", action="store_true", help="move the report start later (a known-cause failure)")
    r.add_argument("--reason", default="", help="why the watch clock restarts (required with --restart)")
    r.add_argument("--skip-laptop", action="store_true", help="a Modal-only watch: no laptop run is required")
    r.add_argument("--laptop-runs", help="the laptop runner's record (default .tmp/laptop_runs/runs.jsonl)")
    args = parser.parse_args(argv)
    now = (now or datetime.now(timezone.utc)).replace(microsecond=0)

    if args.action in (None, "show"):
        print(json.dumps(show(directory), indent=2, sort_keys=True))
        return 0
    try:
        if args.action == "begin":
            if args.new_watch and args.same_watch:
                raise ClockRefused("--new-watch and --same-watch together: pick one")
            out = begin(now, new_watch=args.new_watch, same_watch=args.same_watch, directory=directory)
            if out["kept"]:
                print("hand-off start kept: %s (a retried first pass keeps the earliest boundary)"
                      % out["handoff_start"])
            else:
                print("hand-off start recorded: %s%s" % (out["handoff_start"], (
                    " (previous watch archived to %s)" % out["archived"]) if out["archived"] else ""))
            return 0
        if shadow_store is None:
            from shared import store as store_mod

            shadow_store = store_mod.open_modal_store("shadow", create_if_missing=False)
        out = start_report(now, shadow_store, restart=args.restart, reason=args.reason, directory=directory,
                           skip_laptop=args.skip_laptop, laptop_runs_path=args.laptop_runs)
    except ClockRefused as exc:
        print("REFUSED: %s" % exc)
        print("Nothing was written.")
        return 1
    print("report start recorded: %s%s -> %s" % (out["report_start"], (
        " (was %s)" % out["previous"]) if out["previous"] else "", out["file"]))
    print("The watch report now reads: python3 changesets/deploy/watch_report.py --since "
          "\"$(cat .tmp/deploy/%s)\"" % REPORT_START_NAME)
    return 0


if __name__ == "__main__":
    sys.exit(main())
