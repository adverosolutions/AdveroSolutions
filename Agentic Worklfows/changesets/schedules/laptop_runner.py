#!/usr/bin/env python3
"""Run ONE laptop schedule once, record the result, alert on failure.

Owner decision R4: the jobs that hand work to each other through files run on
the laptop, not on Modal. The staged launchd plists and crontab lines in
changesets/schedules/laptop/ call this script with a schedule name:

    cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
    python3 changesets/schedules/laptop_runner.py deliverability_monitor
    python3 changesets/schedules/laptop_runner.py deliverability_monitor --plan   # print, run nothing
    python3 changesets/schedules/laptop_runner.py --self-test      # no job: proves the runner can read the repo
                                                                   # and write its record (the 2c kick-start)

What it does, in order
----------------------
1. Looks the schedule up in changesets/schedules/schedules.json (generated
   from modal_app.SCHEDULES) and refuses anything that is not runtime=laptop.
2. Decides the child's mode. The child runs with MODE=shadow and
   ALLOW_LIVE_WRITES=0 unless the job's tier is named in LAPTOP_LIVE_TIERS
   (comma list, empty by default); only then does it get MODE=live and
   ALLOW_LIVE_WRITES=1. The .env's own MODE is ignored for scheduled jobs, so
   one tier goes live at a time. ALLOW_PAID_CALLS is 0 unless the job is named
   in LAPTOP_PAID_JOBS (owner decision R7: that flag alone gates paid calls,
   in shadow as well as live).
   LAPTOP_LIVE_TIERS and LAPTOP_PAID_JOBS are live switches like MODE and
   ALLOW_LIVE_WRITES, and they are read ONLY from the saved .env files
   (shared.paths.ENV_PATHS), never from the process environment: a shell
   prefix such as ``LAPTOP_LIVE_TIERS=marketing python3 ...`` cannot make a job
   live or paid. A shell value that differs is ignored and noted in the
   record. Neither switch is passed on to the job.
3. Takes a per-job lock, so a run launchd starts after the Mac wakes cannot
   overlap one still running. A consumer in modal_app.SCHEDULE_ORDERING (the
   07:00 monitor, the 16:00 retro) waits up to 30 minutes for a producer due
   today that is still running, and records ``ordering_not_met`` when a
   producer due today has not run.
4. Runs ``python3 -m <module> <argv>`` ONCE, output to .tmp/laptop_runs/.
5. Records one line in .tmp/laptop_runs/runs.jsonl and one Job_Log row
   ``laptop.<name>`` with the exit code. A non-zero exit (several jobs exit 1
   on a partial run) is status ``failed`` plus a high-priority push. There is
   no retry: the plists carry no KeepAlive, and nothing here loops.
   A job that exits 0 and prints ``ADVERO_OUTCOME=<outcome>`` for an outcome
   in DESIGNED_OUTCOMES is recorded with that status instead of ``ok``: a
   designed result the watch accepts (the list factory's Sunday run with paid
   calls off is ``paid_calls_off``). The job sends its own one note.

A job in config/turned_off_jobs.json (Lorenzo runs it by hand now) is not run:
a plist still loaded on the Mac records ``turned_off``, exits 0, and pushes one
normal-priority note a day saying how to unload it.

Exit code: the job's own exit code (0 when skipped for an overlap or in
--plan). Python 3.9.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(os.path.dirname(HERE))          # .../Agentic Worklfows
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

SCHEDULES_JSON = os.path.join(HERE, "schedules.json")
LIVE_TIERS_ENV = "LAPTOP_LIVE_TIERS"
PAID_JOBS_ENV = "LAPTOP_PAID_JOBS"
DEFAULT_TIMEOUT_S = 3600
TIMEOUTS_S = {"list_factory": 4 * 3600}
ORDER_WAIT_S = 1800
ORDER_POLL_S = 15
CT = "America/Chicago"


# Designed, healthy results a job reports with an ``ADVERO_OUTCOME=<name>``
# line on a zero exit. changesets/deploy/watch_report.LAPTOP_HEALTHY accepts
# exactly these plus ``ok`` and ``turned_off``.
OUTCOME_MARKER = "ADVERO_OUTCOME="
DESIGNED_OUTCOMES = {
    "paid_calls_off": "the list factory ran with paid calls off (LAPTOP_PAID_JOBS does not name it): "
                      "nothing sourced or staged, by design",
}
TURNED_OFF_STATUS = "turned_off"


class RunnerRefused(Exception):
    """The runner will not run this schedule (unknown, or not a laptop job)."""


def load_schedule(name: str, path: str = SCHEDULES_JSON) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """(entry, whole document) for ``name``; refuses a non-laptop schedule."""
    with open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    for entry in doc.get("schedules", []):
        if entry.get("name") == name:
            if entry.get("runtime") != "laptop":
                raise RunnerRefused("%s runs on %s, not on the laptop" % (name, entry.get("runtime")))
            if not isinstance(entry.get("argv"), list):
                raise RunnerRefused("%s has no argv in schedules.json" % name)
            return entry, doc
    raise RunnerRefused("%s is not a schedule in %s" % (name, path))


SWITCHES = (LIVE_TIERS_ENV, PAID_JOBS_ENV)
# Test seams: which .env files hold the switches and how they are read. None
# means shared.paths.ENV_PATHS and python-dotenv's dotenv_values.
SWITCH_ENV_PATHS = None  # type: Optional[List[str]]
SWITCH_LOADER = None


def saved_switches(paths=None, loader=None) -> Dict[str, str]:
    """LAPTOP_LIVE_TIERS and LAPTOP_PAID_JOBS as saved in the .env files, in
    the same order load_env reads them (the first file that sets a key wins).
    The process environment is never consulted."""
    if paths is None:
        paths = SWITCH_ENV_PATHS
    if paths is None:
        from shared.paths import ENV_PATHS

        paths = [str(p) for p in ENV_PATHS]
    loader = loader or SWITCH_LOADER
    if loader is None:
        from dotenv import dotenv_values as loader
    out = {}  # type: Dict[str, str]
    for path in paths:
        if not os.path.isfile(str(path)):
            continue
        values = loader(str(path)) or {}
        for key in SWITCHES:
            if key not in out and values.get(key) is not None:
                out[key] = str(values.get(key))
    return out


def _csv(value: Optional[str]) -> List[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def ignored_shell_switches(switches: Dict[str, str], environ: Optional[Dict[str, str]] = None) -> List[str]:
    environ = os.environ if environ is None else environ
    return ["%s (shell value ignored; .env has %r)" % (key, switches.get(key, ""))
            for key in SWITCHES if key in environ and environ.get(key, "") != switches.get(key, "")]


def child_environment(entry: Dict[str, Any], base: Optional[Dict[str, str]] = None,
                      switches: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """The environment the job runs with. Live only for a tier named in the
    saved .env; paid only for a job named there."""
    switches = saved_switches() if switches is None else switches
    env = dict(os.environ if base is None else base)
    for key in SWITCHES:
        env.pop(key, None)
    live = entry["tier"] in _csv(switches.get(LIVE_TIERS_ENV))
    env["MODE"] = "live" if live else "shadow"
    env["ALLOW_LIVE_WRITES"] = "1" if live else "0"
    env["ALLOW_PAID_CALLS"] = "1" if entry["name"] in _csv(switches.get(PAID_JOBS_ENV)) else "0"
    env["RUNTIME"] = "local"
    return env


def runs_dir() -> str:
    from shared.paths import tmp_dir

    path = os.path.join(str(tmp_dir()), "laptop_runs")
    if not os.path.isdir(path):
        os.makedirs(path)
    return path


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _ct_now(now: datetime) -> datetime:
    import pytz

    return now.astimezone(pytz.timezone(CT))


def laptop_clock_is_central(now: Optional[datetime] = None) -> bool:
    """launchd and cron fire on the Mac's local clock; the crons are CT."""
    now = now or _now()
    local_offset = datetime.now().astimezone().utcoffset()
    return local_offset == _ct_now(now).utcoffset()


def _dow_matches(cron: str, weekday_sun0: int) -> bool:
    field = cron.split()[4]
    if field == "*":
        return True
    days = set()
    for part in field.split(","):
        if "-" in part:
            lo, hi = part.split("-", 1)
            days.update(range(int(lo), int(hi) + 1))
        else:
            days.add(int(part))
    return weekday_sun0 in days or (weekday_sun0 == 0 and 7 in days)


def read_runs(directory: str) -> List[Dict[str, Any]]:
    out = []  # type: List[Dict[str, Any]]
    path = os.path.join(directory, "runs.jsonl")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
    except OSError:
        return []
    return out


def _lock_path(directory: str, name: str) -> str:
    return os.path.join(directory, "%s.lock" % name)


def _try_lock(path: str):
    import fcntl

    fh = open(path, "a+")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, OSError):
        fh.close()
        return None
    return fh


def _is_locked(path: str) -> bool:
    fh = _try_lock(path)
    if fh is None:
        return True
    fh.close()
    return False


def producers_due_today(name: str, doc: Dict[str, Any], now: datetime) -> List[Dict[str, Any]]:
    """Producers that must run before ``name`` and are scheduled today (CT)."""
    ct = _ct_now(now)
    weekday = (ct.weekday() + 1) % 7          # Python Mon=0 -> cron Sun=0
    out = []
    for entry in doc.get("schedules", []):
        rule = entry.get("must_run_before") or {}
        if rule.get("schedule") == name and _dow_matches(entry["cron_ct"], weekday):
            out.append(entry)
    return out


def wait_for_producers(name: str, doc: Dict[str, Any], directory: str, now: datetime,
                       sleep=time.sleep, wait_s: int = ORDER_WAIT_S) -> List[str]:
    """Wait (bounded) for a due producer that is still running. Returns the
    producers that still have no run recorded today: the card or packet this
    job builds is then missing a section, and the record says so."""
    producers = producers_due_today(name, doc, now)
    if not producers:
        return []
    waited = 0
    while waited < wait_s and any(_is_locked(_lock_path(directory, p["name"])) for p in producers):
        sleep(ORDER_POLL_S)
        waited += ORDER_POLL_S
    today = _ct_now(now).date().isoformat()
    ran = set(r.get("name") for r in read_runs(directory)
              if r.get("ct_date") == today and r.get("status") in ("ok", "failed"))
    return [p["name"] for p in producers if p["name"] not in ran]


def _alert(title: str, message: str, priority: str = "high") -> None:
    try:
        from shared.notify import notify

        notify(title, message, priority=priority)
    except Exception as exc:  # noqa: BLE001 - the record is already written
        sys.stderr.write("laptop_runner: alert failed: %s\n" % exc)


def _record(directory: str, record: Dict[str, Any]) -> None:
    with open(os.path.join(directory, "runs.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    try:
        from shared.job_log import log_run

        details = dict((k, v) for k, v in record.items() if k not in ("name", "status"))
        log_run("laptop.%s" % record["name"], record["status"], details)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("laptop_runner: Job_Log row failed: %s\n" % exc)


def _tz_alert_once(directory: str, now: datetime) -> None:
    marker = os.path.join(directory, "tz_alert_%s" % _ct_now(now).date().isoformat())
    if os.path.exists(marker):
        return
    open(marker, "w").close()
    _alert("Laptop clock is not on Central Time",
           "The staged laptop schedules fire on the Mac's local clock and are written in CT. "
           "Jobs are running at the wrong hour until the Mac is set to Central Time.")


def designed_outcome(log_path: str, max_bytes: int = 65536) -> Optional[str]:
    """The ``ADVERO_OUTCOME=`` the job printed last, if it is a designed one."""
    try:
        with open(log_path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - max_bytes))
            text = fh.read().decode("utf-8", "replace")
    except OSError:
        return None
    found = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(OUTCOME_MARKER):
            found = line[len(OUTCOME_MARKER):].strip()
    return found if found in DESIGNED_OUTCOMES else None


def unload_commands(name: str) -> List[str]:
    return ['launchctl bootout "gui/$(id -u)/%s%s"' % ("com.advero.", name),
            "rm ~/Library/LaunchAgents/com.advero.%s.plist" % name]


def _turned_off(name: str, started: datetime) -> int:
    """A plist for a turned-off job is still loaded: record it, note it once a day."""
    from shared import turned_off

    directory = runs_dir()
    note = turned_off.label(name)
    record = {"name": name, "status": TURNED_OFF_STATUS, "ts_start": started.isoformat(),
              "ct_date": _ct_now(started).date().isoformat(), "exit_code": None, "warnings": [],
              "note": note}
    _record(directory, record)
    marker = os.path.join(directory, "turned_off_alert_%s_%s" % (name, _ct_now(started).date().isoformat()))
    if not os.path.exists(marker):
        open(marker, "w").close()
        _alert("Laptop job is turned off: %s" % name,
               "%s is %s, but its launchd agent is still loaded, so it was not run. Unload it:\n%s"
               % (name, note, "\n".join(unload_commands(name))), priority="default")
    return 0


def run(name: str, plan: bool = False, runner=subprocess.run, sleep=time.sleep,
        now: Optional[datetime] = None) -> int:
    from shared import settings  # noqa: F401 - loads .env (never under pytest) before the env is read
    from shared import turned_off

    started = now or _now()
    if turned_off.is_off(name):
        if plan:
            print(json.dumps({"name": name, "status": TURNED_OFF_STATUS, "note": turned_off.label(name)},
                             indent=2, sort_keys=True))
            return 0
        return _turned_off(name, started)
    try:
        entry, doc = load_schedule(name)
    except (RunnerRefused, OSError, ValueError) as exc:
        sys.stderr.write("laptop_runner: REFUSED: %s\n" % exc)
        try:
            from shared.job_log import log_run

            log_run("laptop.%s" % name, "refused", {"error": str(exc)})
        except Exception:  # noqa: BLE001
            pass
        _alert("Laptop job refused: %s" % name, str(exc))
        return 2

    switches = saved_switches()
    env = child_environment(entry, switches=switches)
    argv = [sys.executable, "-m", entry["module"]] + list(entry["argv"])
    summary = {"name": name, "tier": entry["tier"], "argv": argv[1:], "child_mode": env["MODE"],
               "child_allow_live_writes": env["ALLOW_LIVE_WRITES"],
               "child_allow_paid_calls": env["ALLOW_PAID_CALLS"],
               "switches_from_env_file": dict((k, switches.get(k, "")) for k in SWITCHES)}
    ignored = ignored_shell_switches(switches)
    if ignored:
        summary["shell_switches_ignored"] = ignored
    if plan:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    directory = runs_dir()
    warnings = []  # type: List[str]
    if not laptop_clock_is_central(started):
        warnings.append("laptop_clock_not_central")
        _tz_alert_once(directory, started)

    lock = _try_lock(_lock_path(directory, name))
    if lock is None:
        record = dict(summary, status="skipped_overlap", ts_start=started.isoformat(),
                      ct_date=_ct_now(started).date().isoformat(), exit_code=None, warnings=warnings)
        _record(directory, record)
        _alert("Laptop job skipped: %s" % name, "The previous %s run is still going; this one did not start." % name)
        return 0
    try:
        missing = wait_for_producers(name, doc, directory, started, sleep=sleep)
        if missing:
            warnings.append("ordering_not_met: no run today for %s" % ", ".join(missing))
        log_path = os.path.join(directory, "%s_%s.log" % (name, started.strftime("%Y%m%dT%H%M%SZ")))
        t0 = time.time()
        exit_code = None  # type: Any
        error = None
        with open(log_path, "w", encoding="utf-8") as out:
            try:
                proc = runner(argv, cwd=BASE_DIR, env=env, stdout=out, stderr=subprocess.STDOUT,
                              timeout=TIMEOUTS_S.get(name, DEFAULT_TIMEOUT_S))
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                error = "timed out after %ss" % TIMEOUTS_S.get(name, DEFAULT_TIMEOUT_S)
            except Exception as exc:  # noqa: BLE001 - a runner crash is a failed run, recorded once
                error = "%s: %s" % (type(exc).__name__, exc)
        status = "ok" if (error is None and exit_code == 0) else "failed"
        outcome = designed_outcome(log_path) if status == "ok" else None
        if outcome:
            status = outcome
        record = dict(summary, status=status, exit_code=exit_code, error=error,
                      ts_start=started.isoformat(), ct_date=_ct_now(started).date().isoformat(),
                      duration_s=round(time.time() - t0, 1), log_path=log_path, warnings=warnings)
        _record(directory, record)
        if status == "failed":
            _alert("Laptop job FAILED: %s" % name,
                   "%s exited %s%s (tier %s, %s). Not retried. Output: %s" % (
                       name, exit_code, (", " + error) if error else "", entry["tier"], env["MODE"], log_path))
        elif missing:
            _alert("Laptop job ran out of order: %s" % name,
                   "%s ran but %s had no run today, so its section is missing." % (name, ", ".join(missing)),
                   priority="default")
        return 0 if status != "failed" else (exit_code if isinstance(exit_code, int) and exit_code else 1)
    finally:
        lock.close()


SELF_TEST_NAME = "self_test"
SELF_TEST_STATUS = "self_test_ok"
# Set only by the com.advero.self_test plist (build_schedules.py). A self-test
# run by hand in Terminal records started_by "hand" and does not open the
# report clock (watch_clock.py start-report wants a launchd start).
SELF_TEST_MARKER_ENV = "ADVERO_STARTED_BY"
SELF_TEST_MARKER_VALUE = "launchd"


def self_test(now: Optional[datetime] = None) -> int:
    """Run no job: read schedules.json and write one runs.jsonl record.

    launchd starts a python that macOS privacy protection may keep out of
    ~/Desktop, where the repo lives. Kick-starting the com.advero.self_test
    agent proves launchd can run the runner here, with no side effect: no
    job, no push, no model call."""
    started = now or _now()
    with open(SCHEDULES_JSON, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    directory = runs_dir()
    started_by = "launchd" if os.environ.get(SELF_TEST_MARKER_ENV) == SELF_TEST_MARKER_VALUE else "hand"
    record = {"name": SELF_TEST_NAME, "status": SELF_TEST_STATUS, "ts_start": started.isoformat(),
              "started_by": started_by,
              "ct_date": _ct_now(started).date().isoformat(), "exit_code": 0, "warnings": [],
              "python": sys.executable, "schedules_read": len(doc.get("schedules") or []),
              "clock_is_central": laptop_clock_is_central(started)}
    _record(directory, record)
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("name", nargs="?", help="a runtime=laptop schedule from schedules.json")
    parser.add_argument("--plan", action="store_true",
                        help="print the command and the child mode, run nothing")
    parser.add_argument("--self-test", action="store_true",
                        help="run no job: read schedules.json and record one self_test row")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.name:
        parser.error("a schedule name, or --self-test")
    return run(args.name, plan=args.plan)


if __name__ == "__main__":
    sys.exit(main())
