"""D1 rounds 4 and 5: the resume refuses, writing nothing, when any reply
arrived during the rollback (identified or not) while anything live could send
(an armed ladder, an auto-reply pause, an open card), whoever's it is; with no
rollback reply it goes ahead, and --status after a stale resume points at
--resume-live (1). Modal runs are matched on their start (2), only a launchd
self-test opens the report clock (3), there is no public stamp writer: only
``install_schedules.sh --preflight`` mints a preflight stamp (4), and a live
deploy with no URL in its output gives one instruction (5). Fakes only."""
import os
from datetime import datetime, timedelta, timezone

import pytest

from changesets.deploy import cutover, preflight_stamp, watch_clock, watch_report
from changesets.tests import test_deploy_round3 as r3


# ============================================ 1. resume: Lorenzo's broad rule (round 5)
# Any reply during the rollback (identified or not) + anything live that could
# send = STOP and ask, writing nothing. Nobody replied = the resume goes ahead.
def _refused(tmp_path, capsys, argv, **kw):
    words = []
    code, writer = r3._main(tmp_path, argv, words=words, **kw)
    assert code == 1
    assert writer.writes == [] and words == []                     # nothing written, nothing even asked
    assert not (tmp_path / "cutover").exists() or not any((tmp_path / "cutover").glob("handoff_*"))
    out = capsys.readouterr().out
    assert "STOP and ask" in out and "Going live again after a rollback" in out
    return out


BLOCKERS = [
    ("cadence", "lead:c1:cy@x.test): an armed live ladder"),
    ("outside", "dee@x.test (lead:c1:dee@x.test): an armed live ladder"),       # not a hand-off lead: still blocks
    ("ooo", "lead:c1:cy@x.test): a ladder paused by an auto-reply"),
    ("pending", "card tok-7 for cy@x.test: an open card, one tap sends it (pending)"),
    ("queued", "card tok-7 for cy@x.test: a queued approved card (approved_queued)"),
    ("sending", "card tok-7 for cy@x.test: a card being sent (sending)"),
    ("outside_card", "card tok-9 for dee@x.test: an open card, one tap sends it (pending)"),
]


@pytest.mark.parametrize("blocker,why", BLOCKERS)
@pytest.mark.parametrize("argv", [["--resume-live"], ["--resume-live", "--apply"]])
def test_any_rollback_reply_plus_anything_live_that_could_send_refuses(tmp_path, tmp_env, capsys, blocker, why,
                                                                       argv):
    out = _refused(tmp_path, capsys, argv, live=r3._live_after_a_live_period(blocker=blocker))
    assert why in out
    # the rollback replies are named, the unidentified one included
    assert "from ann@x.test, cy@x.test" in out and "failed in shadow, lead unknown: e-070" in out


def test_an_unidentified_rollback_reply_and_a_ladder_outside_the_handoff_refuse(tmp_path, tmp_env, capsys):
    """The reviewer's gap (i): only e-070 arrived during the rollback, it failed
    in shadow, so nobody knows whose it is. dee's armed ladder must block."""
    data = dict(r3._shadow_after_rollback()._dict)
    for key in [k for k in data if k.startswith("lead:")]:
        del data[key]                                               # no identified reply at all
    data["poller:seen"] = {"e-105": "2026-09-25T14:40:00.000Z"}
    shadow = r3.FakeModalStore(data, read_only=True)
    plan_live = r3._live_after_a_live_period(blocker="outside")
    out = _refused(tmp_path, capsys, ["--resume-live", "--apply"], shadow=shadow, live=plan_live)
    assert "failed in shadow, lead unknown: e-070" in out
    assert "dee@x.test (lead:c1:dee@x.test): an armed live ladder" in out


def test_an_out_of_office_pause_is_recognised_by_the_engine_itself(tmp_path, tmp_env, capsys):
    """The reviewer's gap (ii): the ladder is 'stopped', but the engine's own
    is_auto_reply_pause says the next tick restarts it."""
    from services.reply_engine import cadence
    from services.reply_engine.models import LeadState

    raw = r3._live_after_a_live_period(blocker="ooo").get("lead:c1:cy@x.test")
    state = LeadState.from_store(raw)
    assert not cadence.is_armed(state) and cadence.is_auto_reply_pause(state)
    out = _refused(tmp_path, capsys, ["--resume-live", "--apply"], live=r3._live_after_a_live_period(blocker="ooo"))
    assert "a ladder paused by an auto-reply, which the next live tick restarts by itself" in out


@pytest.mark.parametrize("blocker", [None, "outside", "outside_card", "cadence", "ooo", "queued"])
def test_an_empty_rollback_goes_ahead_whatever_is_live(tmp_path, tmp_env, blocker):
    """Nobody replied during the rollback: the live cursor already stands at the
    shadow high-water mark, so the hand-off is empty and live carries on."""
    live = r3._live_after_a_live_period(cursor=r3.CURSOR, blocker=blocker)
    plan = cutover.plan_resume(r3._shadow_after_rollback(), r3._shadow_obs(), live, r3.NOW)
    handoff = plan["handoff"]
    assert handoff["replies"] == [] and handoff["failed_in_shadow"] == [] \
        and handoff["seen_without_lead_record"] == []
    words = []
    code, writer = r3._main(tmp_path, ["--resume-live", "--apply"], live=live, words=words)
    assert code == 0 and words == ["RESUME"]
    assert writer.writes[-1] == ("set", "cutover:record")


def test_a_rollback_with_replies_and_nothing_live_that_could_send_goes_ahead(tmp_path, tmp_env):
    words = []
    code, writer = r3._main(tmp_path, ["--resume-live", "--apply"], live=r3._live_after_a_live_period(), words=words)
    assert code == 0 and words == ["RESUME"]
    assert writer.writes[-1] == ("set", "cutover:record")


def test_resume_blockers_follow_the_broad_rule():
    ladder = {"lead": "dee@x.test", "store_key": "lead:c1:dee@x.test", "why": "an armed live ladder"}
    card = {"approval": "t1", "lead": "zed@x.test", "status": "approved_queued"}
    live = {"live_ladders_that_could_send": [ladder], "open_live_cards": [card]}
    empty = dict(live, replies=[], failed_in_shadow=[], seen_without_lead_record=[])
    assert cutover.resume_blockers(empty) == []
    for key, row in (("replies", {"lead_email": "cy@x.test", "email_id": "e-1"}),
                     ("failed_in_shadow", {"email_id": "e-2"}),
                     ("seen_without_lead_record", {"email_id": "e-3"})):
        got = cutover.resume_blockers(dict(empty, **{key: [row]}))
        assert got == ["dee@x.test (lead:c1:dee@x.test): an armed live ladder",
                       "card t1 for zed@x.test: a queued approved card (approved_queued)"], key
    assert cutover.resume_blockers(dict(empty, replies=[{"lead_email": "cy@x.test"}], live_ladders_that_could_send=[],
                                        open_live_cards=[])) == []


def test_status_after_a_stale_resume_says_resume_live_not_redo(tmp_path, tmp_env, capsys):
    """A resume re-arms the age limit and deletes cutover:accepted, so a stale
    resume looks like a stale first cutover. --redo would delete the record of
    the live period (and plan_reset refuses it anyway): the way on is another
    --resume-live."""
    stale = r3.FakeModalStore({r3.store_mod.CUTOVER_KEY: {"cutover_at": "2026-09-25T10:00:00+00:00",
                                                          "resumed": True},
                               "poller:cursor": dict(r3.LIVE_CURSOR)}, read_only=True)
    assert r3._main(tmp_path, ["--status"], live=stale)[0] == 0
    nxt = r3.json.loads(capsys.readouterr().out)["next"]
    assert "--resume-live" in nxt and "stale" in nxt
    assert "run --resume-live again" in nxt and "never --redo" in nxt


# ============================================ 2. Modal runs matched on start
DAY = datetime(2026, 9, 24, 17, 0, tzinfo=timezone.utc)          # 12:00 CT, Thursday


def _precall_rows(starts_ends):
    return [{"ts_utc": e.isoformat(), "job": "modal.precall_tick", "status": "tick", "mode": "shadow",
             "details": {"started_at": s.isoformat()}} for s, e in starts_ends]


def _precall_missing(overrides, drop=()):
    """Every */5 precall run from 11:00 to 14:00 CT: 3 s start, 40 s run,
    except ``overrides`` {due: (start, end)}; ``drop`` never started."""
    cron, timeout = watch_report.deployed_schedules()["precall_tick"]
    start, until = DAY - timedelta(hours=1), DAY + timedelta(hours=2)
    pairs = []
    for t in watch_report.due_times(cron, start, until):
        if t in drop:
            continue
        pairs.append(overrides.get(t, (t + timedelta(seconds=3), t + timedelta(seconds=43))))
    rows = _precall_rows(pairs)
    stamps = [watch_report.run_started(r) for r in rows]
    ends = [watch_report.parse_ts(r["ts_utc"]) for r in rows]
    return watch_report.match_runs(cron, stamps, start, until, timeout + watch_report.MODAL_START_GRACE_S,
                                   ends=ends)["missing"]


def test_a_seven_minute_run_and_the_run_queued_behind_it_report_nothing_missing():
    m = timedelta(minutes=1)
    overrides = {DAY: (DAY + timedelta(seconds=2), DAY + 7 * m),                                   # slow: 7 min
                 DAY + 5 * m: (DAY + 7 * m + timedelta(seconds=1), DAY + 10 * m + timedelta(seconds=40)),  # queued
                 DAY + 10 * m: (DAY + 10 * m + timedelta(seconds=41), DAY + 11 * m)}               # queued again
    assert _precall_missing(overrides) == []


def test_a_run_up_to_its_timeout_plus_its_queued_successor_report_nothing_missing():
    m = timedelta(minutes=1)
    overrides = {DAY: (DAY + timedelta(seconds=2), DAY + timedelta(seconds=602)),                  # the full 600 s
                 DAY + 5 * m: (DAY + timedelta(seconds=603), DAY + timedelta(seconds=640)),
                 DAY + 10 * m: (DAY + timedelta(seconds=641), DAY + timedelta(seconds=680))}
    assert _precall_missing(overrides) == []


def test_a_run_that_never_started_is_still_missing():
    m = timedelta(minutes=1)
    assert _precall_missing({}, drop=(DAY + 5 * m,)) == [(DAY + 5 * m).isoformat()]
    # still missing when the run before it was slow: the 12:10 run started on time, not queued
    slow = {DAY: (DAY + timedelta(seconds=2), DAY + 4 * m)}
    assert _precall_missing(slow, drop=(DAY + 5 * m,)) == [(DAY + 5 * m).isoformat()]


def test_the_whole_report_passes_with_a_slow_precall_run(tmp_env):
    """The reviewer's probe, with the start stamp every row now carries."""
    start = datetime(2026, 9, 23, 15, 0, tzinfo=timezone.utc)
    until = start + timedelta(hours=49)
    sched = watch_report.deployed_schedules()
    jobs = []
    for name, (cron, _timeout) in sched.items():
        for t in watch_report.due_times(cron, start, until):
            s, e = t + timedelta(seconds=2), t + timedelta(seconds=40)
            if name == "precall_tick" and t == DAY:
                e = t + timedelta(minutes=7)
            if name == "precall_tick" and t == DAY + timedelta(minutes=5):
                s, e = DAY + timedelta(minutes=7, seconds=1), DAY + timedelta(minutes=8, seconds=40)
            jobs.append({"ts_utc": e.isoformat(), "job": "modal.%s" % name, "status": "tick", "mode": "shadow",
                         "details": {"started_at": s.isoformat()}})
    rep = watch_report.build_report(jobs, [], sched, start, until, 48.0, laptop_runs=None)
    assert rep["automated_passed"] is True, [c for c in rep["criteria"] if not c["passed"]]


def test_every_modal_row_carries_its_start_and_the_evidence_keeps_it(monkeypatch):
    from services.reply_engine import modal_app
    from shared import job_log

    rows = []
    monkeypatch.setattr(modal_app, "_log_row", lambda job, status, details: rows.append((status, details)))
    monkeypatch.setattr(modal_app, "_refuse_without_cutover", lambda job: None)
    modal_app._scheduled("precall_tick", lambda: {"exit_code": 0})
    with pytest.raises(RuntimeError):
        modal_app._scheduled("precall_tick", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert [s for s, _d in rows] == ["tick", "error"]
    for _s, details in rows:
        assert watch_report.parse_ts(details["started_at"]) is not None
    assert job_log._gate_details({"started_at": "2026-09-24T17:00:02+00:00", "noise": 1}) == {
        "started_at": "2026-09-24T17:00:02+00:00"}


# ============================================ 3. launchd self-test only
def test_only_a_launchd_self_test_on_central_time_opens_the_report_clock(tmp_path, tmp_env, monkeypatch):
    module, _alerts = r3._load_runner(tmp_env, monkeypatch)
    monkeypatch.delenv(module.SELF_TEST_MARKER_ENV, raising=False)
    now = datetime.now(timezone.utc)
    module.self_test(now=now)                                      # typed in Terminal
    monkeypatch.setenv(module.SELF_TEST_MARKER_ENV, module.SELF_TEST_MARKER_VALUE)
    module.self_test(now=now + timedelta(minutes=1))               # what the plist sets
    rows = module.read_runs(module.runs_dir())
    assert [r["started_by"] for r in rows] == ["hand", "launchd"]
    hand, launchd = rows
    assert not watch_clock.launchd_self_test(hand)
    assert watch_clock.launchd_self_test(launchd)                  # the runner fixture says Central Time
    assert not watch_clock.launchd_self_test(dict(launchd, clock_is_central=False))

    d = str(tmp_path / "deploy")
    os.makedirs(d)
    watch_clock.begin(now - timedelta(hours=1), directory=d)
    r3._health(d, now - timedelta(minutes=30))
    only_hand = r3._laptop_runs_file(tmp_path, hand)
    problems = " ".join(watch_clock.check_report_start(now, r3._shadow_store(), d, laptop_runs_path=only_hand))
    assert "started by launchd" in problems and "by hand in Terminal proves nothing" in problems
    not_central = r3._laptop_runs_file(tmp_path, dict(launchd, clock_is_central=False))
    assert watch_clock.check_report_start(now, r3._shadow_store(), d, laptop_runs_path=not_central) != []
    both = r3._laptop_runs_file(tmp_path, hand, launchd)
    assert watch_clock.check_report_start(now + timedelta(minutes=2), r3._shadow_store(), d,
                                          laptop_runs_path=both) == []


def test_the_self_test_plist_sets_the_marker_the_runner_reads():
    import importlib.util
    import plistlib

    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    spec = importlib.util.spec_from_file_location(
        "build_schedules_r4", os.path.join(here, "changesets", "schedules", "build_schedules.py"))
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    from changesets.schedules import laptop_runner

    assert (build.SELF_TEST_MARKER_ENV, build.SELF_TEST_MARKER_VALUE) == (
        laptop_runner.SELF_TEST_MARKER_ENV, laptop_runner.SELF_TEST_MARKER_VALUE)
    with open(os.path.join(here, "changesets", "schedules", "laptop", "com.advero.self_test.plist"), "rb") as fh:
        doc = plistlib.load(fh)
    assert doc["EnvironmentVariables"][laptop_runner.SELF_TEST_MARKER_ENV] == laptop_runner.SELF_TEST_MARKER_VALUE
    for name in os.listdir(os.path.join(here, "changesets", "schedules", "laptop")):
        if name.endswith(".plist") and name != "com.advero.self_test.plist":
            with open(os.path.join(here, "changesets", "schedules", "laptop", name), "rb") as fh:
                assert laptop_runner.SELF_TEST_MARKER_ENV not in plistlib.load(fh)["EnvironmentVariables"]


# ============================================ 4. no public stamp writer
def test_no_command_writes_a_preflight_stamp(tmp_env, capsys):
    path = preflight_stamp.stamp_path()
    assert not os.path.exists(path)
    with pytest.raises(SystemExit) as exc:
        preflight_stamp.main(["write"])
    assert exc.value.code == 2
    assert not os.path.exists(path)
    assert not hasattr(preflight_stamp, "write")
    assert preflight_stamp.main(["check"]) == 1                    # no stamp: the live flip is refused
    assert "no preflight stamp" in capsys.readouterr().out


# ============================================ 5. live deploy, no URL in its output
@pytest.mark.skipif(not os.path.exists("/bin/bash"), reason="needs bash")
def test_a_live_deploy_with_no_url_checks_the_saved_url_and_gives_one_instruction(tmp_path):
    code, out, calls = r3._run_live_flip(tmp_path, NO_URL=1)
    assert code == 0, out
    assert any(c.startswith("changesets/deploy/verify_health.py --expect-mode live") for c in calls)
    assert "Checking /health at the saved URL" in out
    assert "Copy it from the deploy output" not in out and "THE LIVE SECRET MAY BE IN PLACE" not in out
    code, out, calls = r3._run_live_flip(tmp_path / "b", NO_URL=1, HEALTH_RC=1)
    assert code != 0
    assert "THE LIVE SECRET MAY BE IN PLACE" in out
    assert "Copy it from the deploy output" not in out and "then run:" not in out
