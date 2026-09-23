"""D1 round 3: the two watch clocks (defect 1), the preflight stamp before the
live secret (defect 5), going live again after a rollback and the live-activity
refusal (defect 6), a failed live write is a failure (defect 10), and the
Sunday list factory / turned-off / self-test outcomes the watch accepts
(defect 4, Part B). Stores are fakes; nothing leaves the machine."""
import json
import os
import pty
import select
import shutil
import stat
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from changesets.deploy import cutover, preflight_stamp, watch_clock, watch_report
from changesets.tests.deploy_fakes import FakeModalStore
from shared import store as store_mod

BASE_DIR = Path(__file__).resolve().parents[2]
INSTALL_SH = BASE_DIR / "changesets" / "schedules" / "install_schedules.sh"
CURSOR = {"last_email_id": "e-105", "last_timestamp": "2026-09-25T14:40:00.000Z"}


def _shadow_store(cursor=CURSOR):
    return FakeModalStore({"poller:cursor": dict(cursor)} if cursor else {}, read_only=True)


def _health(directory, at, passed=True, expect_mode="shadow", first_pass=False):
    with open(os.path.join(str(directory), watch_clock.HEALTH_HISTORY_NAME), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts_utc": at.isoformat(), "expect_mode": expect_mode, "first_pass": first_pass,
                             "passed": passed, "failed_checks": 0 if passed else 1,
                             "url_host": "x--advero-reply-engine-web.modal.run"}) + "\n")


LAUNCHD_SELF_TEST = {"name": "self_test", "status": "self_test_ok", "started_by": "launchd",
                     "clock_is_central": True}


def _laptop_runs_file(tmp_path, *rows):
    path = tmp_path / "runs.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return str(path)


# ================================================== defect 1: two clocks
T0 = datetime(2026, 9, 23, 15, 2, 10, tzinfo=timezone.utc)          # the hand-off start, before `modal deploy`


def test_begin_records_the_handoff_start_once_and_a_retry_keeps_it(tmp_path, tmp_env):
    first = watch_clock.begin(T0, directory=str(tmp_path))
    assert first == {"handoff_start": "2026-09-23T15:02:10Z", "kept": False, "archived": None}
    retry = watch_clock.begin(T0 + timedelta(hours=2), directory=str(tmp_path))
    assert retry["kept"] is True and retry["handoff_start"] == "2026-09-23T15:02:10Z"
    assert watch_clock.read_time(watch_clock.HANDOFF_START_NAME, str(tmp_path)) == T0


def test_a_new_watch_gets_fresh_files_and_an_old_start_is_never_reused_silently(tmp_path, tmp_env):
    d = str(tmp_path)
    watch_clock.begin(T0, directory=d)
    watch_clock._write_time(watch_clock.REPORT_START_NAME, T0 + timedelta(hours=1), d)
    later = T0 + timedelta(days=20)
    with pytest.raises(watch_clock.ClockRefused) as exc:
        watch_clock.begin(later, directory=d)
    assert "previous watch" in str(exc.value) and "--new-watch" in str(exc.value)
    assert watch_clock.begin(later, same_watch=True, directory=d)["kept"] is True
    out = watch_clock.begin(later, new_watch=True, directory=d)
    assert out["kept"] is False and out["archived"]
    assert sorted(os.listdir(out["archived"])) == sorted(
        [watch_clock.HANDOFF_START_NAME, watch_clock.REPORT_START_NAME, watch_clock.HISTORY_NAME])
    assert watch_clock.read_time(watch_clock.HANDOFF_START_NAME, d) == later
    assert watch_clock.read_time(watch_clock.REPORT_START_NAME, d) is None       # fresh: no report start yet


def test_the_report_start_waits_for_second_pass_health_laptop_and_a_complete_cursor(tmp_path, tmp_env):
    d = str(tmp_path)
    now = T0 + timedelta(hours=1)
    with pytest.raises(watch_clock.ClockRefused) as exc:
        watch_clock.start_report(now, _shadow_store(), directory=d)
    assert "no hand-off start" in str(exc.value)
    watch_clock.begin(T0, directory=d)
    runs = _laptop_runs_file(tmp_path)
    problems = " ".join(watch_clock.check_report_start(now, _shadow_store(None), d, laptop_runs_path=runs))
    assert "SECOND-pass" in problems and "no self_test_ok row started by launchd" in problems \
        and "no complete cursor" in problems
    _health(tmp_path, T0 + timedelta(minutes=10), first_pass=True)             # the first pass is not enough
    assert "SECOND-pass" in " ".join(watch_clock.check_report_start(now, _shadow_store(), d,
                                                                    laptop_runs_path=runs))
    _health(tmp_path, T0 + timedelta(minutes=30))
    runs = _laptop_runs_file(tmp_path, dict(LAUNCHD_SELF_TEST,
                                                     ts_start=(T0 + timedelta(minutes=40)).isoformat()))
    assert watch_clock.check_report_start(now, _shadow_store(), d, laptop_runs_path=runs) == []
    assert watch_clock.check_report_start(now, _shadow_store(None), d, skip_laptop=True) != []
    out = watch_clock.start_report(now, _shadow_store(), directory=d, laptop_runs_path=runs)
    assert out["report_start"] == "2026-09-23T16:02:10Z"
    assert watch_clock.read_time(watch_clock.HANDOFF_START_NAME, d) == T0        # the hand-off start never moves


def test_the_report_start_moves_only_later_and_only_with_a_reason(tmp_path, tmp_env):
    d = str(tmp_path)
    watch_clock.begin(T0, directory=d)
    _health(tmp_path, T0 + timedelta(minutes=30))
    runs = _laptop_runs_file(tmp_path, dict(LAUNCHD_SELF_TEST,
                                                     ts_start=(T0 + timedelta(minutes=40)).isoformat()))
    first = T0 + timedelta(hours=1)
    watch_clock.start_report(first, _shadow_store(), directory=d, laptop_runs_path=runs)
    with pytest.raises(watch_clock.ClockRefused):
        watch_clock.start_report(first + timedelta(hours=3), _shadow_store(), directory=d, laptop_runs_path=runs)
    with pytest.raises(watch_clock.ClockRefused) as exc:
        watch_clock.start_report(first + timedelta(hours=3), _shadow_store(), restart=True, directory=d,
                                 laptop_runs_path=runs)
    assert "--reason" in str(exc.value)
    with pytest.raises(watch_clock.ClockRefused):
        watch_clock.start_report(first - timedelta(minutes=5), _shadow_store(), restart=True, reason="x",
                                 directory=d, laptop_runs_path=runs)
    out = watch_clock.start_report(first + timedelta(hours=3), _shadow_store(), restart=True,
                                   reason="budget cap: first-poll backlog", directory=d, laptop_runs_path=runs)
    assert out["previous"] == "2026-09-23T16:02:10Z"
    assert watch_clock.read_time(watch_clock.HANDOFF_START_NAME, d) == T0
    history = [json.loads(line) for line in open(os.path.join(d, watch_clock.HISTORY_NAME), encoding="utf-8")]
    assert [h["event"] for h in history] == ["handoff_start", "report_start", "report_restart"]
    assert history[-1]["reason"] == "budget cap: first-poll backlog"


def test_the_cli_begins_and_shows_both_clocks(tmp_path, tmp_env, capsys):
    d = str(tmp_path)
    assert watch_clock.main(["begin"], now=T0, directory=d) == 0
    assert watch_clock.main(["begin"], now=T0 + timedelta(minutes=9), directory=d) == 0
    assert "kept" in capsys.readouterr().out
    assert watch_clock.main(["start-report"], shadow_store=_shadow_store(None), now=T0 + timedelta(hours=1),
                            directory=d) == 1
    assert "Nothing was written" in capsys.readouterr().out
    assert watch_clock.main(["show"], directory=d) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["handoff_start"] == "2026-09-23T15:02:10Z" and shown["report_start"] is None


def test_verify_health_records_each_result_for_the_report_start(tmp_path, tmp_env):
    from changesets.deploy import verify_health

    path = str(tmp_path / watch_clock.HEALTH_HISTORY_NAME)
    verify_health.record_result("shadow", True, "https://x--advero-reply-engine-web.modal.run", True, path=path)
    verify_health.record_result("shadow", False, "https://x--advero-reply-engine-web.modal.run", True, path=path)
    last = watch_clock.last_health(str(tmp_path))
    assert last["expect_mode"] == "shadow" and last["first_pass"] is False and last["passed"] is True
    assert last["url_host"] == "x--advero-reply-engine-web.modal.run"


def test_rows_that_begin_after_the_handoff_start_pass_from_the_report_start(tmp_path, tmp_env):
    """The reviewer's probe as a test: the app comes up 3 minutes after the
    hand-off start. Reported from the hand-off start the gate can never pass
    (the crons due during the image build have no row, and there is no
    slack); reported from the report start, the same rows pass."""
    d = str(tmp_path)
    watch_clock.begin(T0, directory=d)
    app_up = T0 + timedelta(minutes=3)
    _health(tmp_path, T0 + timedelta(minutes=25))
    runs = _laptop_runs_file(tmp_path, dict(LAUNCHD_SELF_TEST,
                                                     ts_start=(T0 + timedelta(minutes=35)).isoformat()))
    watch_clock.start_report(T0 + timedelta(minutes=45), _shadow_store(), directory=d, laptop_runs_path=runs)
    report_start = watch_clock.read_time(watch_clock.REPORT_START_NAME, d)
    handoff_start = watch_clock.read_time(watch_clock.HANDOFF_START_NAME, d)
    until = report_start + timedelta(hours=49)
    sched = watch_report.deployed_schedules()
    jobs = []
    for name, (cron, _timeout) in sched.items():
        for t in watch_report.due_times(cron, app_up, until):
            jobs.append({"ts_utc": (t + timedelta(seconds=40)).isoformat(), "job": "modal.%s" % name,
                         "status": "tick", "mode": "shadow"})
    from_handoff = watch_report.build_report(jobs, [], sched, handoff_start, until, 48.0, laptop_runs=None)
    assert from_handoff["automated_passed"] is False
    missed = [c for c in from_handoff["criteria"] if not c["passed"]]
    assert any("15:05" in c["detail"] for c in missed), missed
    from_report = watch_report.build_report(jobs, [], sched, report_start, until, 48.0, laptop_runs=None)
    assert from_report["automated_passed"] is True, [c for c in from_report["criteria"] if not c["passed"]]


# ================================================== defect 5: the preflight stamp
def test_a_fresh_stamp_on_this_code_passes(tmp_path, tmp_env):
    path = str(tmp_path / "stamp.json")
    now = datetime(2026, 9, 25, 15, 0, tzinfo=timezone.utc)
    rec = preflight_stamp._write_after_preflight(now=now, path=path)
    assert rec["files"] > 50 and len(rec["sha256"]) == 64
    assert preflight_stamp.problems(now + timedelta(minutes=30), path) == []


def test_a_missing_old_or_other_code_stamp_is_refused(tmp_path, tmp_env, monkeypatch):
    path = str(tmp_path / "stamp.json")
    now = datetime(2026, 9, 25, 15, 0, tzinfo=timezone.utc)
    assert "no preflight stamp" in " ".join(preflight_stamp.problems(now, path))
    preflight_stamp._write_after_preflight(now=now, path=path)
    assert "not within the last 60 minutes" in " ".join(preflight_stamp.problems(now + timedelta(minutes=61),
                                                                                  path))
    real = preflight_stamp.fingerprint()
    monkeypatch.setattr(preflight_stamp, "fingerprint", lambda: dict(real, sha256="0" * 64))
    assert "changed since the preflight" in " ".join(preflight_stamp.problems(now + timedelta(minutes=1), path))


def test_the_live_secret_is_refused_without_a_passing_preflight(tmp_path, tmp_env, capsys):
    import conftest
    from changesets.deploy import modal_secret
    from changesets.tests.test_deploy_secret import FAKE_ENV, FakeRun, _write_env

    url = "https://x--advero-reply-engine-web.modal.run"
    env_path = _write_env(tmp_path, FAKE_ENV)
    asked = []
    run = FakeRun()
    argv = ["--mode", "live", "--base-url", url, "--create", "--env-file", env_path]
    code = modal_secret.main(argv, runner=run, confirm=lambda w, p: asked.append(w) or True,
                             env_loader=conftest._real_dotenv_values)
    assert code == 1 and run.calls == [] and asked == []                # refused before CREATE is even asked
    assert "only after the preflight passed" in capsys.readouterr().out
    code = modal_secret.main(argv, runner=run, confirm=lambda w, p: asked.append(w) or True,
                             env_loader=conftest._real_dotenv_values, preflight_check=lambda: [])
    assert code == 0 and asked == ["CREATE"] and len(run.calls) == 1
    assert run.payloads[0]["MODE"] == "live"
    # shadow never needs the stamp
    code = modal_secret.main(["--mode", "shadow", "--base-url", url, "--create", "--env-file", env_path],
                             runner=FakeRun(), confirm=lambda w, p: True, env_loader=conftest._real_dotenv_values)
    assert code == 0


FAKE_PYTHON = r"""#!/bin/bash
# Stands in for python3 inside a copy of install_schedules.sh. Logs every call.
echo "$*" >> "$FAKE_LOG"
case "$1" in
  changesets/deploy/preflight_stamp.py) [ "$2" = "check" ] && exit "${STAMP_RC:-0}"; exit 0 ;;
  changesets/deploy/modal_secret.py) exit "${SECRET_RC:-0}" ;;
  changesets/deploy/verify_health.py) exit "${HEALTH_RC:-0}" ;;
  changesets/deploy/watch_clock.py) exit 0 ;;
  -) cat > /dev/null; echo "${SECRET_OUTCOME:-created}"; exit 0 ;;
  -c) case "$2" in *SCHEDULED_FUNCTIONS*) echo 8 ;; *) echo sales ;; esac; exit 0 ;;
  -m) if [ "$2" = "modal" ] && [ "$3" = "deploy" ]; then
        [ -z "$NO_URL" ] && echo "Created web => https://x--advero-reply-engine-web.modal.run"
        exit "${DEPLOY_RC:-0}"
      fi
      exit 0 ;;
esac
exit 0
"""


def _run_live_flip(tmp_path, **env):
    """Run a COPY of install_schedules.sh --deploy live on a pseudo-terminal,
    with a fake python3 first on PATH, typing DEPLOY. Nothing real runs."""
    root = tmp_path / "repo"
    (root / "changesets" / "schedules").mkdir(parents=True)
    (root / ".tmp" / "deploy").mkdir(parents=True)
    shutil.copy(str(INSTALL_SH), str(root / "changesets" / "schedules" / "install_schedules.sh"))
    (root / ".tmp" / "deploy" / "web_url.txt").write_text("https://x--advero-reply-engine-web.modal.run\n")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "python3"
    fake.write_text(FAKE_PYTHON)
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "calls.log"
    # built from os.environ, so the session's test flag reaches the child (conftest refuses one without it)
    child_env = dict(os.environ)
    for key in ("STAMP_RC", "SECRET_RC", "HEALTH_RC", "DEPLOY_RC", "SECRET_OUTCOME", "NO_URL"):
        child_env.pop(key, None)
    child_env.update({"PATH": "%s:/usr/bin:/bin" % bindir, "FAKE_LOG": str(log), "DEPLOY_TIERS": "sales",
                      "TERM": "dumb"})
    child_env.update(dict((k, str(v)) for k, v in env.items()))
    pid, fd = pty.fork()
    if pid == 0:  # the child: a new session whose controlling terminal is the pty
        try:
            os.execve("/bin/bash", ["bash", str(root / "changesets" / "schedules" / "install_schedules.sh"),
                                    "--deploy", "live"], child_env)
        finally:
            os._exit(127)  # never fall back into the test session
    out = b""
    sent = False
    deadline = time.time() + 30
    while time.time() < deadline:
        ready, _w, _x = select.select([fd], [], [], 0.2)
        if ready:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
        if not sent and b"[type DEPLOY]" in out:
            os.write(fd, b"DEPLOY\n")
            sent = True
    _pid, status = os.waitpid(pid, 0)
    os.close(fd)
    calls = log.read_text().splitlines() if log.exists() else []
    return os.WEXITSTATUS(status), out.decode("utf-8", "replace"), calls


@pytest.mark.skipif(not os.path.exists("/bin/bash"), reason="needs bash")
def test_the_live_flip_order_stamp_then_secret_then_deploy_on_a_pty(tmp_path):
    code, out, calls = _run_live_flip(tmp_path)
    assert code == 0, out
    firsts = [c.split()[0] if c.split()[0] not in ("-m",) else " ".join(c.split()[:3]) for c in calls]
    assert firsts[0] == "changesets/deploy/preflight_stamp.py"             # the stamp is the first thing
    assert not any("_write_after_preflight" in c or "pytest" in c for c in calls)   # no preflight in the live path
    secret = firsts.index("changesets/deploy/modal_secret.py")
    deploy = firsts.index("-m modal deploy")
    # between the secret and the deploy: only the local read of the secret history
    assert firsts[secret + 1:deploy] == ["-"]
    assert "--mode live" in calls[secret] and "--create" in calls[secret]
    assert firsts[deploy + 1] == "changesets/deploy/verify_health.py"
    assert "THE LIVE SECRET MAY BE IN PLACE" not in out


@pytest.mark.skipif(not os.path.exists("/bin/bash"), reason="needs bash")
@pytest.mark.parametrize("env", [{"DEPLOY_RC": 1}, {"HEALTH_RC": 1}, {"SECRET_OUTCOME": "create_failed",
                                                                       "SECRET_RC": 1},
                                 {"SECRET_OUTCOME": "none", "SECRET_RC": 0}])
def test_any_failure_once_the_secret_may_exist_prints_the_abort_sequence(tmp_path, env):
    code, out, calls = _run_live_flip(tmp_path, **env)
    assert code != 0
    assert "THE LIVE SECRET MAY BE IN PLACE" in out
    assert "python3 -m modal app stop advero-reply-engine" in out


@pytest.mark.skipif(not os.path.exists("/bin/bash"), reason="needs bash")
def test_a_stale_stamp_stops_before_any_question_and_a_refused_secret_prints_no_abort(tmp_path):
    code, out, calls = _run_live_flip(tmp_path, STAMP_RC=1)
    assert code == 1 and "[type DEPLOY]" not in out
    assert not any(c.startswith("changesets/deploy/modal_secret.py") for c in calls)
    assert "THE LIVE SECRET MAY BE IN PLACE" not in out
    code, out, calls = _run_live_flip(tmp_path / "b", SECRET_RC=1, SECRET_OUTCOME="none")
    assert code == 1 and "Not deployed" in out
    assert not any("modal deploy" in c for c in calls)
    assert "THE LIVE SECRET MAY BE IN PLACE" not in out


# ================================================== defect 6: back to live, and live activity
NOW = datetime(2026, 9, 25, 15, 0, tzinfo=timezone.utc)
LIVE_CURSOR = {"last_email_id": "e-050", "last_timestamp": "2026-09-25T09:00:00.000Z"}


def _lead(email, email_id, at, cadence=None):
    state = {"lead_email": email, "campaign_id": "c1", "campaign_key": "cleaning_reactivation", "first_name": "X",
             "company": "X Co", "status": "replied", "drafts": [], "approvals": [], "last_subject": "Re: hi",
             "history": [{"at": at, "event": "inbound", "email_id": email_id, "label": "question",
                          "source": "poller"}]}
    if cadence:
        state["cadence"] = cadence
    return state


def _shadow_after_rollback(cursor=CURSOR):
    data = {
        "poller:seen": {"e-040": "2026-09-25T08:00:00.000Z", "e-060": "2026-09-25T10:00:00.000Z",
                        "e-105": "2026-09-25T14:40:00.000Z"},
        "poller:failed": {"e-070": {"timestamp_created": "2026-09-25T11:00:00.000Z", "attempts": 3,
                                    "error": "timeout"}},
        "lead:c1:old@x.test": _lead("old@x.test", "e-040", "2026-09-25T08:00:00+00:00"),
        "lead:c1:ann@x.test": _lead("ann@x.test", "e-060", "2026-09-25T10:00:00+00:00"),
        "lead:c1:cy@x.test": _lead("cy@x.test", "e-105", "2026-09-25T14:40:00+00:00"),
    }
    if cursor:
        data["poller:cursor"] = dict(cursor)
    return FakeModalStore(data, read_only=True)


def _shadow_obs():
    return FakeModalStore({"obs:job:20260925145500:a": {"ts_utc": "2026-09-25T14:55:00+00:00",
                                                         "job": "modal.poller", "status": "tick", "mode": "shadow"}},
                          read_only=True)


ARMED = {"armed_at": "2026-09-25T07:05:00+00:00", "next_send_at": "2026-09-26T13:00:00+00:00"}


def _ooo_paused(email, email_id, at):
    """A live ladder stopped by an out-of-office: the engine's own
    is_auto_reply_pause recognises it by the machine label on the inbound."""
    lead = _lead(email, email_id, at, cadence=dict(ARMED, day=1, stopped_reason="inbound_reply", next_send_at=None))
    lead["history"][-1]["label"] = "ooo"
    lead["last_inbound_at"] = at
    return lead


def _live_after_a_live_period(cursor=LIVE_CURSOR, blocker=None):
    """The live store after a live period. cy@x.test replied again during the
    rollback (a hand-off lead); dee@x.test did not. By default nothing live can
    send: cy's ladder stopped on a human reply, dee's on a booking, both cards
    sent. ``blocker`` adds one thing that could send:
    "cadence" (cy armed), "outside" (dee armed), "ooo" (cy paused by an
    out-of-office), "pending" / "queued" / "sending" (a card for cy),
    "outside_card" (a pending card for dee)."""
    cy = _lead("cy@x.test", "e-030", "2026-09-25T07:00:00+00:00", cadence=dict(ARMED, stopped_reason="inbound_reply"))
    if blocker == "cadence":
        cy = _lead("cy@x.test", "e-030", "2026-09-25T07:00:00+00:00", cadence=dict(ARMED))
    if blocker == "ooo":
        cy = _ooo_paused("cy@x.test", "e-049", "2026-09-25T08:50:00+00:00")
    data = {
        store_mod.CUTOVER_KEY: {"cutover_at": "2026-09-24T20:00:00+00:00"},
        store_mod.CUTOVER_ACCEPTED_KEY: {"job": "poller", "accepted_at": "2026-09-24T20:05:00+00:00"},
        "poller:failed": {"e-045": {"timestamp_created": "2026-09-25T08:30:00.000Z", "attempts": 1,
                                    "error": "GHL 502"}},
        "lead:c1:cy@x.test": cy,
        "lead:c1:dee@x.test": _lead("dee@x.test", "e-031", "2026-09-25T07:10:00+00:00",
                                    cadence=dict(ARMED) if blocker == "outside" else
                                    dict(ARMED, stopped_reason="booked", next_send_at=None)),
        "approval:tok-9": {"status": "pending" if blocker == "outside_card" else "sent", "lead_email": "dee@x.test",
                           "created_at": "2026-09-25T07:06:00Z"},
        "approval:tok-8": {"status": "sent", "lead_email": "cy@x.test", "created_at": "2026-09-25T06:00:00Z"},
    }
    if blocker in ("pending", "queued", "sending"):
        data["approval:tok-7"] = {"status": {"pending": "pending", "queued": "approved_queued",
                                             "sending": "sending"}[blocker],
                                  "lead_email": "cy@x.test", "created_at": "2026-09-25T07:20:00Z"}
    if cursor:
        data["poller:cursor"] = dict(cursor)
    return FakeModalStore(data, read_only=True)


def _main(tmp_path, argv, shadow=None, live=None, writer=None, words=None, live_obs=None):
    writer = writer if writer is not None else FakeModalStore()
    words = words if words is not None else []
    code = cutover.main(argv, shadow_store=shadow or _shadow_after_rollback(),
                        live_store=live or _live_after_a_live_period(), open_live_for_write=lambda: writer,
                        confirm=lambda w, p: words.append(w) or True, now=NOW,
                        handoff_dir=str(tmp_path / "cutover"), shadow_obs=_shadow_obs(),
                        live_obs=live_obs or FakeModalStore(missing=True, read_only=True))
    return code, writer


def test_live_activity_names_an_accepted_cutover_and_engine_keys():
    assert cutover.live_activity(FakeModalStore(missing=True)) == []
    clean = FakeModalStore({store_mod.CUTOVER_KEY: {"cutover_at": "x"}, store_mod.CUTOVER_ACCEPTED_KEY: None,
                            "poller:cursor": dict(LIVE_CURSOR)})
    assert cutover.live_activity(clean) == []
    found = " ".join(cutover.live_activity(_live_after_a_live_period()))
    assert "a live tick accepted the cutover" in found and "written by the live engine" in found


@pytest.mark.parametrize("argv", [["--reset", "--apply"], ["--redo", "--apply"], ["--reset"]])
def test_reset_and_redo_refuse_a_live_store_that_shows_live_activity(tmp_path, tmp_env, capsys, argv):
    code, writer = _main(tmp_path, argv)
    assert code == 1 and writer.writes == []
    out = capsys.readouterr().out
    assert "shows live activity" in out and "--resume-live" in out and "--override-live-activity" in out


def test_the_override_is_explicit_and_logged(tmp_path, tmp_env, capsys):
    words = []
    code, writer = _main(tmp_path, ["--reset", "--apply", "--override-live-activity", "test data only, no leads"],
                         words=words)
    assert code == 0 and words == ["RESET"]
    assert all(w[0] == "delete" for w in writer.writes)
    assert len(writer.writes) == len(_live_after_a_live_period().keys())
    assert "OVERRIDE" in capsys.readouterr().out
    lines = (tmp_path / "cutover" / cutover.OVERRIDES_NAME).read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[-1])
    assert rec["action"] == "reset" and rec["reason"] == "test data only, no leads" and rec["live_activity"]
    code, _w = _main(tmp_path, ["--override-live-activity", "x"])
    assert code == 2                                                    # only with --reset or --redo


def test_an_override_never_beats_a_prospect_facing_write(tmp_path, tmp_env, capsys):
    row = {"ts_utc": "2026-09-25T10:06:00+00:00", "job": "instantly.reply", "status": "live_write_ok",
           "mode": "live"}
    code, writer = _main(tmp_path, ["--reset", "--apply", "--override-live-activity", "x"],
                         live_obs=FakeModalStore({"obs:job:1:x": row}, read_only=True))
    assert code == 1 and writer.writes == []
    assert "prospect-facing write happened" in capsys.readouterr().out


def test_status_says_what_comes_next(tmp_path, tmp_env, capsys):
    assert _main(tmp_path, ["--status"])[0] == 0
    out = json.loads(capsys.readouterr().out)
    assert out["accepted_by_a_live_tick"] and "--resume-live" in out["next"]
    fresh = FakeModalStore({store_mod.CUTOVER_KEY: {"cutover_at": "2026-09-25T14:30:00+00:00"},
                            "poller:cursor": dict(LIVE_CURSOR)}, read_only=True)
    assert _main(tmp_path, ["--status"], live=fresh)[0] == 0
    out = json.loads(capsys.readouterr().out)
    assert out["cutover_age_minutes"] == 30 and "stands" in out["next"]
    stale = FakeModalStore({store_mod.CUTOVER_KEY: {"cutover_at": "2026-09-25T10:00:00+00:00"},
                            "poller:cursor": dict(LIVE_CURSOR)}, read_only=True)
    assert _main(tmp_path, ["--status"], live=stale)[0] == 0
    assert "--redo" in json.loads(capsys.readouterr().out)["next"]


def test_resume_dry_run_lists_the_rollback_period_and_writes_nothing(tmp_path, tmp_env, capsys):
    code, writer = _main(tmp_path, ["--resume-live"])
    assert code == 0 and writer.writes == []
    out = capsys.readouterr().out
    assert "Resume point: reply e-105" in out and "Rollback period after: reply e-050" in out
    doc = json.loads(next((tmp_path / "cutover").glob("*.dryrun.json")).read_text(encoding="utf-8"))
    handoff = doc["handoff"]
    # the replies the SHADOW engine saw during the rollback, after the live cursor: not old@ (before it)
    assert sorted(r["lead_email"] for r in handoff["replies"]) == ["ann@x.test", "cy@x.test"]
    assert [r["email_id"] for r in handoff["failed_in_shadow"]] == ["e-070"]
    assert [r["email_id"] for r in handoff["failed_in_live_cleared"]] == ["e-045"]
    assert handoff["open_live_cards"] == [] and handoff["live_ladders_that_could_send"] == []


def test_resume_apply_keeps_the_live_store_and_writes_the_record_last(tmp_path, tmp_env):
    words = []
    code, writer = _main(tmp_path, ["--resume-live", "--apply"], words=words)
    assert code == 0 and words == ["RESUME"]
    assert writer.writes == [("delete", store_mod.CUTOVER_ACCEPTED_KEY), ("set", "poller:cursor"),
                             ("delete", "poller:failed"), ("set", store_mod.CUTOVER_KEY)]
    assert writer.get("poller:cursor")["last_email_id"] == "e-105"
    record = writer.get(store_mod.CUTOVER_KEY)
    assert record["resumed"] is True and record["previous"] == {"cutover_at": "2026-09-24T20:00:00+00:00"}
    assert record["cutover_at"] == NOW.isoformat()           # the age limit counts from now again
    assert record["failed_in_live_cleared"] == ["e-045"]


def test_resume_falls_back_to_the_rollback_seed_when_the_live_cursor_expired(tmp_path, tmp_env, capsys):
    live = _live_after_a_live_period(cursor=None)
    code, _w = _main(tmp_path, ["--resume-live"], live=live)
    assert code == 1 and "STOP and ask" in capsys.readouterr().out
    (tmp_path / "cutover").mkdir(exist_ok=True)
    (tmp_path / "cutover" / cutover.ROLLBACK_SEED_NAME).write_text(json.dumps(
        {"seeded_at": "2026-09-25T09:01:00+00:00", "live_cursor": dict(LIVE_CURSOR)}), encoding="utf-8")
    code, _w = _main(tmp_path, ["--resume-live"], live=live)
    assert code == 0
    assert cutover.ROLLBACK_SEED_NAME in capsys.readouterr().out


def test_resume_refuses_a_first_cutover_and_a_shadow_that_has_not_caught_up(tmp_path, tmp_env, capsys):
    code, _w = _main(tmp_path, ["--resume-live"], live=FakeModalStore(missing=True, read_only=True))
    assert code == 1 and "first cutover" in capsys.readouterr().out
    behind = {"last_email_id": "e-020", "last_timestamp": "2026-09-25T06:00:00.000Z"}
    code, _w = _main(tmp_path, ["--resume-live"], shadow=_shadow_after_rollback(cursor=behind))
    assert code == 1 and "has not caught up" in capsys.readouterr().out
    code, _w = _main(tmp_path, ["--resume-live"], shadow=_shadow_after_rollback(cursor=None))
    assert code == 1 and "no complete poller:cursor" in capsys.readouterr().out


def test_the_rollback_seed_keeps_the_live_cursor_for_a_later_resume(tmp_path, tmp_env):
    shadow_writer = FakeModalStore()
    code = cutover.main(["--seed-shadow-from-live", "--apply"], shadow_store=_shadow_after_rollback(),
                        live_store=_live_after_a_live_period(), shadow_obs=_shadow_obs(),
                        live_obs=FakeModalStore(missing=True, read_only=True), now=NOW,
                        open_shadow_for_write=lambda: shadow_writer, confirm=lambda w, p: True,
                        handoff_dir=str(tmp_path / "cutover"))
    assert code == 0
    assert cutover.read_rollback_seed(str(tmp_path / "cutover"))["live_cursor"] == LIVE_CURSOR


def test_the_cursor_missing_alert_points_at_the_resume_section():
    from services.reply_engine import modal_app

    text = modal_app.REFUSAL_TEXT["cursor_missing"]
    assert "--resume-live" in text and "Going live again after a rollback" in text
    assert "--resume-live" in modal_app.REFUSAL_TEXT["cutover_stale"]


# ================================================== defect 10 and the laptop outcomes
def test_a_failed_live_write_is_a_failure_not_just_a_live_write():
    assert watch_report.classify("live_write_failed") == "fail"
    assert watch_report.classify("live_write_intent") == "live_write"
    assert watch_report.classify("live_write_ok") == "live_write"
    assert watch_report.is_live_write("live_write_failed")


SUNDAY = datetime(2026, 9, 27, 5, 0, tzinfo=timezone.utc)                  # Sun 00:00 CDT
SUNDAY_END = SUNDAY + timedelta(hours=48)                                   # to Tue 00:00, so Monday counts


def _sunday_report(tmp_path, capsys, list_factory_status, extra=()):
    from changesets.tests.test_deploy_watch_report import _healthy_records, _laptop_runs

    runs = _laptop_runs(SUNDAY, SUNDAY_END)
    assert any(r["name"] == "list_factory" for r in runs), "the window must hold the Sunday 09:00 run"
    runs = [dict(r, status=list_factory_status, exit_code=0 if list_factory_status != "failed" else 1)
            if r["name"] == "list_factory" else r for r in runs] + list(extra)
    path = tmp_path / "runs.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in runs), encoding="utf-8")
    store = FakeModalStore(_healthy_records(SUNDAY, SUNDAY_END), read_only=True)
    code = watch_report.main(["--json", "--since", SUNDAY.isoformat(), "--laptop-runs", str(path)],
                             store=store, now=SUNDAY_END)
    out = json.loads(capsys.readouterr().out)
    return code, out, dict((c["criterion"], c) for c in out["criteria"])


def test_a_watch_over_sunday_passes_with_paid_calls_off(tmp_path, tmp_env, capsys):
    extra = [{"name": "upwork_rooms_am", "status": "turned_off", "ts_start": (SUNDAY + timedelta(hours=14)).isoformat(),
              "exit_code": 0, "warnings": []},
             {"name": "self_test", "status": "self_test_ok", "ts_start": (SUNDAY + timedelta(hours=1)).isoformat(),
              "exit_code": 0, "warnings": []}]
    code, out, crit = _sunday_report(tmp_path, capsys, "paid_calls_off", extra)
    assert code == 0, [c for c in out["criteria"] if not c["passed"]]
    assert crit["laptop list_factory ran on schedule"]["passed"] is True
    assert crit["every laptop run is ok with no warning"]["passed"] is True
    assert sorted(out["turned_off"]) == ["campaign_verdicts", "upwork_rooms_am", "upwork_rooms_pm"]


def test_a_failed_sunday_list_factory_still_fails_the_watch(tmp_path, tmp_env, capsys):
    code, _out, crit = _sunday_report(tmp_path, capsys, "failed")
    assert code == 1
    assert crit["every laptop run is ok with no warning"]["passed"] is False


def test_the_text_report_lists_the_turned_off_jobs(tmp_path, tmp_env, capsys):
    from changesets.tests.test_deploy_watch_report import END, START, _healthy_records

    store = FakeModalStore(_healthy_records(), read_only=True)
    watch_report.main(["--skip-laptop", "--since", START.isoformat()], store=store, now=END)
    text = capsys.readouterr().out
    assert "TURNED OFF" in text
    for name in ("campaign_verdicts", "upwork_rooms_am", "upwork_rooms_pm"):
        assert name in text.split("TURNED OFF", 1)[1]


def _load_runner(tmp_env, monkeypatch):
    import importlib.util

    import conftest

    spec = importlib.util.spec_from_file_location(
        "laptop_runner_round3", str(BASE_DIR / "changesets" / "schedules" / "laptop_runner.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    alerts = []
    monkeypatch.setattr(module, "_alert", lambda title, message, priority="high": alerts.append((title, priority)))
    monkeypatch.setattr(module, "laptop_clock_is_central", lambda now=None: True)
    monkeypatch.delenv("LAPTOP_LIVE_TIERS", raising=False)
    monkeypatch.delenv("LAPTOP_PAID_JOBS", raising=False)
    env_file = tmp_env / "laptop.env"
    env_file.write_text("", encoding="utf-8")
    module.SWITCH_ENV_PATHS = [str(env_file)]
    module.SWITCH_LOADER = conftest._real_dotenv_values
    return module, alerts


def _printing(text, returncode=0):
    def fake(argv, **kwargs):
        kwargs["stdout"].write(text)
        return subprocess.CompletedProcess(argv, returncode)
    return fake


SUNDAY_0900_CT = datetime(2026, 9, 27, 14, 0, tzinfo=timezone.utc)


def test_the_runner_records_a_designed_outcome_and_sends_no_alert(tmp_env, monkeypatch):
    module, alerts = _load_runner(tmp_env, monkeypatch)
    code = module.run("list_factory", runner=_printing("blocked: paid calls off\nADVERO_OUTCOME=paid_calls_off\n"),
                      now=SUNDAY_0900_CT)
    assert code == 0 and alerts == []
    assert [r["status"] for r in module.read_runs(module.runs_dir())] == ["paid_calls_off"]


def test_a_marker_on_a_non_zero_exit_or_an_unknown_marker_changes_nothing(tmp_env, monkeypatch):
    module, alerts = _load_runner(tmp_env, monkeypatch)
    assert module.run("list_factory", runner=_printing("ADVERO_OUTCOME=paid_calls_off\n", 1),
                      now=SUNDAY_0900_CT) == 1
    assert module.run("list_factory", runner=_printing("ADVERO_OUTCOME=anything_goes\n"),
                      now=SUNDAY_0900_CT + timedelta(minutes=1)) == 0
    assert [r["status"] for r in module.read_runs(module.runs_dir())] == ["failed", "ok"]
    assert [a[1] for a in alerts] == ["high"]


def test_the_self_test_runs_no_job_and_records_one_row(tmp_env, monkeypatch):
    module, alerts = _load_runner(tmp_env, monkeypatch)
    assert module.main(["--self-test"]) == 0
    rows = module.read_runs(module.runs_dir())
    assert [r["status"] for r in rows] == ["self_test_ok"] and rows[0]["name"] == "self_test"
    assert rows[0]["schedules_read"] == 16 and alerts == []
    assert "self_test_ok" in watch_report.LAPTOP_HEALTHY
