"""Lorenzo turned off campaign_verdicts and the two Upwork rooms digests
(2026-09-22): he runs them by hand. Their code stays; nothing schedules them,
and every reader says "turned off", never "missing" or "failed"."""
import json
import os

from shared import turned_off
from shared.ghl import GHL

OFF = ("campaign_verdicts", "upwork_rooms_am", "upwork_rooms_pm")


def test_the_three_jobs_are_turned_off_and_their_code_stays():
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    jobs = turned_off.load()
    assert sorted(jobs) == sorted(OFF)
    for name in OFF:
        module = jobs[name]["module"]
        assert os.path.isfile(os.path.join(base, *module.split(".")) + ".py"), module
        assert "turned off since 2026-09-22" in turned_off.label(name)
    assert turned_off.upwork_rooms_off()


def test_a_missing_file_means_nothing_is_turned_off(tmp_path):
    assert turned_off.load(tmp_path / "nope.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    assert turned_off.load(bad) == {}


def test_nothing_schedules_them_and_the_retro_waits_for_nothing_turned_off():
    from services.reply_engine import modal_app

    for name in OFF:
        assert name not in modal_app.SCHEDULES and name not in modal_app.SCHEDULE_JOB_MODULE
    assert "campaign_verdicts" not in modal_app.SCHEDULE_ORDERING
    assert all(consumer != "retro_packet" for consumer, _why in modal_app.SCHEDULE_ORDERING.values())
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(os.path.join(here, "changesets", "schedules", "schedules.json"), "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    names = set(e["name"] for e in doc["schedules"])
    assert not (names & set(OFF))
    assert sorted(e["name"] for e in doc["turned_off"]) == sorted(OFF)
    laptop = os.listdir(os.path.join(here, "changesets", "schedules", "laptop"))
    for name in OFF:
        assert "com.advero.%s.plist" % name not in laptop
    crontab = open(os.path.join(here, "changesets", "schedules", "laptop", "crontab.txt"), encoding="utf-8").read()
    for name in OFF:
        assert name not in crontab


def test_build_schedules_refuses_a_turned_off_job_that_is_still_scheduled(monkeypatch):
    import importlib.util

    from services.reply_engine import modal_app

    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    spec = importlib.util.spec_from_file_location(
        "build_schedules", os.path.join(here, "changesets", "schedules", "build_schedules.py"))
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    assert build.validate_turned_off(modal_app, turned_off.load()) == []
    fake = dict(turned_off.load(), retro_packet={"module": "jobs.retro_packet", "tier": "ops", "was_scheduled": "x",
                                                 "turned_off_on": "2026-09-22", "by_hand": "x", "why": "x"})
    problems = build.validate_turned_off(modal_app, fake)
    assert any("retro_packet is turned off" in p and "still scheduled" in p for p in problems)
    gone = dict(turned_off.load(), ghost={"module": "jobs.no_such_job", "tier": "ops", "was_scheduled": "x",
                                          "turned_off_on": "x", "by_hand": "x", "why": "x"})
    assert any("keep the code" in p for p in build.validate_turned_off(modal_app, gone))


def test_the_retro_shows_them_as_turned_off():
    from services.retro import packet
    from services.retro.sources import Source

    class Week(object):
        job_log = Source("job_log", [{"job": "laptop.retro_packet", "status": "ok", "ts_utc": "x"}], True, "", "p")

    section = packet.machine_section(Week())
    text = " ".join(section.bullets)
    for name in OFF:
        assert "%s: turned off since" % name in text
    assert "missing" not in text and "failed" not in text


def test_the_sweep_says_turned_off_not_skipped(tmp_env, shadow_mode):
    import httpx

    from jobs import pipeline_sweep as sweep
    from jobs.tests.test_pipeline_sweep import NOW, fixture_transport, make_store
    from shared.instantly import Instantly

    instantly = Instantly(api_key="k", transport=fixture_transport())
    result = sweep.run_sweep(NOW, instantly=instantly, ghl=GHL(token=None), store=make_store(tmp_env), dry_run=True,
                             upwork_rooms_path=tmp_env / "no_rooms.json")
    notes = " ".join(result["notes"])
    assert "upwork rooms: turned off since 2026-09-22" in notes
    assert "Upwork MCP unavailable" not in notes
    assert httpx  # imported for the transport


def test_daily_metrics_labels_the_upwork_column_turned_off(tmp_env, shadow_mode):
    from jobs.tests.test_metrics_jobs import row_of, run_on_fixtures

    result, _io = run_on_fixtures(rooms=None)
    row = row_of(result, "Upwork response time")
    assert "turned off since 2026-09-22" in str(row.get("note"))
    assert row.get("state") != "ALERT"


def test_the_laptop_runner_records_a_still_loaded_turned_off_job_and_exits_0(tmp_env, monkeypatch):
    from changesets.schedules import laptop_runner

    pushes = []
    monkeypatch.setattr(laptop_runner, "_alert", lambda t, m, priority="high": pushes.append((t, m, priority)))
    calls = []
    assert laptop_runner.run("upwork_rooms_am", runner=lambda *a, **k: calls.append(a)) == 0
    assert laptop_runner.run("upwork_rooms_am", runner=lambda *a, **k: calls.append(a)) == 0
    assert calls == [], "a turned-off job is never run"
    rows = laptop_runner.read_runs(laptop_runner.runs_dir())
    assert [r["status"] for r in rows] == ["turned_off", "turned_off"]
    assert len(pushes) == 1 and pushes[0][2] == "default", "one normal-priority note a day"
    assert 'launchctl bootout "gui/$(id -u)/com.advero.upwork_rooms_am"' in pushes[0][1]
