"""R4: the laptop runner runs one file-hand-off job once, in the right mode,
records the exit code, alerts on a failure and never retries."""
import importlib.util
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parents[2]
RUNNER = BASE_DIR / "changesets" / "schedules" / "laptop_runner.py"
MONDAY_0700_CT = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)       # CDT: 07:00 on a Monday
WEDNESDAY_0700_CT = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def runner(tmp_env, monkeypatch):
    spec = importlib.util.spec_from_file_location("laptop_runner_under_test", str(RUNNER))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    alerts = []
    monkeypatch.setattr(module, "_alert", lambda title, message, priority="high": alerts.append((title, priority)))
    monkeypatch.setattr(module, "laptop_clock_is_central", lambda now=None: True)
    monkeypatch.delenv("LAPTOP_LIVE_TIERS", raising=False)
    monkeypatch.delenv("LAPTOP_PAID_JOBS", raising=False)
    # The switches are read from a saved .env only; point that at a temp file
    # read with the real python-dotenv (the session makes dotenv inert).
    import conftest

    env_file = tmp_env / "laptop.env"
    env_file.write_text("", encoding="utf-8")
    module.SWITCH_ENV_PATHS = [str(env_file)]
    module.SWITCH_LOADER = conftest._real_dotenv_values
    module.env_file = env_file
    module.alerts = alerts
    return module


class FakeRun(object):
    def __init__(self, returncode=0, raises=None):
        self.returncode = returncode
        self.raises = raises
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append({"argv": argv, "env": kwargs.get("env"), "cwd": kwargs.get("cwd")})
        if self.raises is not None:
            raise self.raises
        return subprocess.CompletedProcess(argv, self.returncode)


def _runs(module):
    return module.read_runs(module.runs_dir())


def _job_rows(tmp_env):
    import csv

    from shared import job_log

    try:
        with open(str(job_log.job_log_path()), "r", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


# ----------------------------------------------------------------- refusal
def test_a_modal_schedule_is_refused(runner, tmp_env):
    fake = FakeRun()
    assert runner.run("poller", runner=fake) == 2
    assert fake.calls == []
    assert [r["status"] for r in _job_rows(tmp_env)] == ["refused"]


def test_an_unknown_schedule_is_refused(runner):
    fake = FakeRun()
    assert runner.run("no_such_job", runner=fake) == 2
    assert fake.calls == []


# ------------------------------------------------------------------ modes
def test_scheduled_laptop_jobs_run_in_shadow_even_when_the_env_says_live(runner, live_mode):
    fake = FakeRun()
    assert runner.run("client_scorecard", runner=fake, now=WEDNESDAY_0700_CT) == 0
    env = fake.calls[0]["env"]
    assert (env["MODE"], env["ALLOW_LIVE_WRITES"], env["ALLOW_PAID_CALLS"]) == ("shadow", "0", "0")
    assert env["RUNTIME"] == "local"
    assert fake.calls[0]["argv"][1:] == ["-m", "jobs.client_scorecard", "--now"]


def test_only_a_tier_named_in_laptop_live_tiers_runs_live(runner, monkeypatch):
    runner.env_file.write_text("LAPTOP_LIVE_TIERS=marketing\n", encoding="utf-8")
    fake = FakeRun()
    runner.run("inbox_inventory", runner=fake, now=WEDNESDAY_0700_CT)
    runner.run("client_scorecard", runner=fake, now=WEDNESDAY_0700_CT)
    assert (fake.calls[0]["env"]["MODE"], fake.calls[0]["env"]["ALLOW_LIVE_WRITES"]) == ("live", "1")
    assert (fake.calls[1]["env"]["MODE"], fake.calls[1]["env"]["ALLOW_LIVE_WRITES"]) == ("shadow", "0")


def test_paid_calls_need_the_job_named_in_laptop_paid_jobs(runner, monkeypatch):
    fake = FakeRun()
    monkeypatch.setenv("ALLOW_PAID_CALLS", "1")          # a stray .env value is not enough
    runner.run("list_factory", runner=fake, now=WEDNESDAY_0700_CT)
    assert fake.calls[0]["env"]["ALLOW_PAID_CALLS"] == "0"
    runner.env_file.write_text("LAPTOP_PAID_JOBS=list_factory\n", encoding="utf-8")
    runner.run("list_factory", runner=fake, now=WEDNESDAY_0700_CT)
    assert fake.calls[1]["env"]["ALLOW_PAID_CALLS"] == "1"
    assert fake.calls[1]["argv"][1:] == ["-m", "jobs.list_factory", "--now", "--all-campaigns",
                                         "--refresh-suppression"]


def test_a_shell_prefix_cannot_make_a_job_live_or_paid(runner, monkeypatch, capsys):
    """Review item 6: LAPTOP_LIVE_TIERS=marketing LAPTOP_PAID_JOBS=list_factory
    in front of the command changes nothing; only the saved .env counts, and
    the switches are not passed on to the job."""
    monkeypatch.setenv("LAPTOP_LIVE_TIERS", "marketing,ops,fulfillment")
    monkeypatch.setenv("LAPTOP_PAID_JOBS", "list_factory")
    fake = FakeRun()
    runner.run("list_factory", runner=fake, now=WEDNESDAY_0700_CT)
    env = fake.calls[0]["env"]
    assert (env["MODE"], env["ALLOW_LIVE_WRITES"], env["ALLOW_PAID_CALLS"]) == ("shadow", "0", "0")
    assert "LAPTOP_LIVE_TIERS" not in env and "LAPTOP_PAID_JOBS" not in env
    record = _runs(runner)[-1]
    assert any("shell value ignored" in x for x in record["shell_switches_ignored"])
    assert runner.run("list_factory", plan=True) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["child_mode"] == "shadow" and plan["switches_from_env_file"]["LAPTOP_PAID_JOBS"] == ""


def test_the_switches_come_from_the_first_env_file_that_sets_them(runner, tmp_env):
    first = tmp_env / "first.env"
    second = tmp_env / "second.env"
    first.write_text("LAPTOP_LIVE_TIERS=ops\n", encoding="utf-8")
    second.write_text("LAPTOP_LIVE_TIERS=marketing\nLAPTOP_PAID_JOBS=list_factory\n", encoding="utf-8")
    got = runner.saved_switches(paths=[str(first), str(second), str(tmp_env / "missing.env")])
    assert got == {"LAPTOP_LIVE_TIERS": "ops", "LAPTOP_PAID_JOBS": "list_factory"}


# --------------------------------------------------------------- outcomes
def test_a_non_zero_exit_is_a_failed_run_with_one_alert_and_no_retry(runner, tmp_env):
    fake = FakeRun(returncode=1)
    assert runner.run("deliverability_monitor", runner=fake, now=WEDNESDAY_0700_CT) == 1
    assert len(fake.calls) == 1
    runs = _runs(runner)
    assert [(r["name"], r["status"], r["exit_code"]) for r in runs] == [("deliverability_monitor", "failed", 1)]
    assert [a for a in runner.alerts if "FAILED" in a[0]] == [("Laptop job FAILED: deliverability_monitor", "high")]
    rows = [r for r in _job_rows(tmp_env) if r["job"] == "laptop.deliverability_monitor"]
    assert [r["status"] for r in rows] == ["failed"]
    assert json.loads(rows[0]["details"])["exit_code"] == 1


def test_a_clean_exit_is_ok_and_silent(runner, tmp_env):
    fake = FakeRun(returncode=0)
    assert runner.run("daily_metrics", runner=fake, now=WEDNESDAY_0700_CT) == 0
    assert [r["status"] for r in _runs(runner)] == ["ok"]
    assert runner.alerts == []


def test_a_timeout_is_a_failed_run(runner):
    fake = FakeRun(raises=subprocess.TimeoutExpired(cmd="x", timeout=1))
    assert runner.run("retro_packet", runner=fake, now=WEDNESDAY_0700_CT) == 1
    run = _runs(runner)[0]
    assert run["status"] == "failed" and "timed out" in run["error"]
    assert len(fake.calls) == 1


def test_an_overlapping_run_is_skipped_not_started(runner):
    lock = runner._try_lock(runner._lock_path(runner.runs_dir(), "daily_metrics"))
    try:
        fake = FakeRun()
        assert runner.run("daily_metrics", runner=fake, now=WEDNESDAY_0700_CT) == 0
        assert fake.calls == []
        assert [r["status"] for r in _runs(runner)] == ["skipped_overlap"]
    finally:
        lock.close()


def test_plan_runs_nothing(runner, capsys):
    fake = FakeRun()
    assert runner.run("daily_metrics", plan=True, runner=fake) == 0
    assert fake.calls == []
    assert '"child_mode": "shadow"' in capsys.readouterr().out


# ---------------------------------------------------------------- ordering
def test_the_monday_monitor_records_a_missing_placement_run(runner):
    fake = FakeRun()
    runner.run("deliverability_monitor", runner=fake, now=MONDAY_0700_CT, sleep=lambda s: None)
    run = [r for r in _runs(runner) if r["name"] == "deliverability_monitor"][0]
    assert any("ordering_not_met" in w and "inbox_placement" in w for w in run["warnings"])


def test_the_monday_monitor_is_clean_after_placement_ran(runner):
    fake = FakeRun()
    runner.run("inbox_placement", runner=fake, now=MONDAY_0700_CT)
    runner.run("deliverability_monitor", runner=fake, now=MONDAY_0700_CT, sleep=lambda s: None)
    run = [r for r in _runs(runner) if r["name"] == "deliverability_monitor"][0]
    assert run["warnings"] == []


def test_a_consumer_waits_for_a_producer_that_is_still_running(runner):
    directory = runner.runs_dir()
    lock = runner._try_lock(runner._lock_path(directory, "inbox_placement"))
    slept = []

    def sleep(seconds):
        slept.append(seconds)
        if len(slept) == 3:
            lock.close()      # the producer finishes

    fake = FakeRun()
    runner.run("deliverability_monitor", runner=fake, now=MONDAY_0700_CT, sleep=sleep)
    assert len(slept) == 3
    assert len(fake.calls) == 1


def test_a_wrong_laptop_clock_is_flagged_once_a_day(runner, monkeypatch):
    monkeypatch.setattr(runner, "laptop_clock_is_central", lambda now=None: False)
    fake = FakeRun()
    runner.run("daily_metrics", runner=fake, now=WEDNESDAY_0700_CT)
    runner.run("pipeline_sweep", runner=fake, now=WEDNESDAY_0700_CT)
    assert len([a for a in runner.alerts if "Central Time" in a[0]]) == 1
    assert all("laptop_clock_not_central" in r["warnings"] for r in _runs(runner))
