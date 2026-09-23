"""GOL-2: the shadow gate reads the DEPLOYED store, read-only, and never
reports healthy without evidence. The store is a fake."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from changesets.deploy import watch_report
from changesets.tests.deploy_fakes import FakeModalStore

START = datetime(2026, 9, 23, 5, 0, tzinfo=timezone.utc)      # 00:00 CDT, a Wednesday
END = START + timedelta(hours=48)


def _deployed():
    from services.reply_engine import modal_app

    return dict((n, modal_app.SCHEDULES[n].cron) for n in modal_app.SCHEDULED_FUNCTIONS)


def _healthy_records(start=START, end=END):
    """One tick row for every run each deployed cron makes in the window, plus
    a few would_do records."""
    import pytz

    zone = pytz.timezone("America/Chicago")
    data = {}
    n = 0
    for name, cron in _deployed().items():
        t = start
        while t < end:
            local = t.astimezone(zone)
            if watch_report.expected_runs(cron, t, t + timedelta(minutes=1)):
                n += 1
                data["obs:job:%s:%06d" % (t.strftime("%Y%m%d%H%M%S"), n)] = {
                    "ts_utc": (t + timedelta(seconds=30)).isoformat(), "job": "modal.%s" % name,
                    "status": "tick", "mode": "shadow", "details": {}}
            t += timedelta(minutes=1)
    for i, action in enumerate(("reply", "update_interest_status", "reply")):
        data["obs:shadow:20260923%06d:%d" % (i, i)] = {
            "ts_utc": (start + timedelta(hours=3 + i)).isoformat(), "mode": "shadow",
            "system": "instantly", "action": action, "payload": {"to": "lead%d@x.test" % i}}
    return data


def _report(data, argv=None, now=END):
    store = FakeModalStore(data, read_only=True)            # any write raises
    return watch_report.main((argv or ["--skip-laptop"]) + ["--json", "--since", START.isoformat()],
                             store=store, now=now)


def _criteria(capsys):
    out = json.loads(capsys.readouterr().out)
    return out, dict((c["criterion"], c) for c in out["criteria"])


def test_a_clean_48_hours_passes_the_automated_criteria_only(tmp_env, capsys):
    assert _report(_healthy_records()) == 0
    out, crit = _criteria(capsys)
    assert out["automated_passed"] is True
    assert all(c["passed"] for c in crit.values())
    assert out["would_do_total"] == 3
    assert out["would_do_counts"] == {"instantly.reply": 2, "instantly.update_interest_status": 1}
    # the manual criteria are always listed, and the gate is never declared passed
    assert any("would_do" in m for m in out["manual_not_checked"])
    assert any("approval card was tapped" in m for m in out["manual_not_checked"])
    with open(out["would_do_file"], "r", encoding="utf-8") as fh:
        assert len(fh.readlines()) == 3


def test_the_text_report_never_says_the_gate_passed(tmp_env, capsys):
    store = FakeModalStore(_healthy_records(), read_only=True)
    assert watch_report.main(["--since", START.isoformat(), "--skip-laptop"], store=store, now=END) == 0
    text = capsys.readouterr().out
    assert "Gate: NOT YET PASSED" in text
    assert "MANUAL CRITERIA" in text


def test_no_evidence_is_a_failure_not_a_pass(tmp_env, capsys):
    assert _report({}) == 1
    out, crit = _criteria(capsys)
    assert crit["evidence exists"]["passed"] is False
    assert crit["poller ran on schedule"]["passed"] is False


def test_a_watch_shorter_than_48_hours_fails(tmp_env, capsys):
    data = _healthy_records(end=START + timedelta(hours=20))
    assert _report(data, now=START + timedelta(hours=20)) == 1
    _out, crit = _criteria(capsys)
    assert crit["the window spans at least 48 hours"]["passed"] is False


def test_each_bad_row_kind_fails_the_healthy_list(tmp_env, capsys):
    data = _healthy_records()
    bad = {
        "error": "modal.pipeline_sync", "failed": "modal.precall_tick",
        "entrypoint_missing": "modal.appointments_tick", "partial": "pipeline_sweep",
        "refused": "llm.budget",
    }
    for i, (status, job) in enumerate(sorted(bad.items())):
        data["obs:job:20260924120000:bad%d" % i] = {"ts_utc": "2026-09-24T12:00:00+00:00", "job": job,
                                                    "status": status, "mode": "shadow", "details": {}}
    data["obs:job:20260924120000:lw"] = {"ts_utc": "2026-09-24T12:00:00+00:00", "job": "instantly.reply",
                                         "status": "live_write_intent", "mode": "shadow", "details": {}}
    assert _report(data) == 1
    out, crit = _criteria(capsys)
    detail = crit["every Job_Log status is on the healthy list"]["detail"]
    assert crit["every Job_Log status is on the healthy list"]["passed"] is False
    for status, job in bad.items():
        assert "%s %s x1" % (job, status) in detail
    assert crit["zero live_write_* rows"]["passed"] is False
    assert out["automated_passed"] is False


# The statuses the sales tier actually writes when it is failing (review item
# 1, probe_watch_statuses.py): every one of them used to pass.
REAL_FAILURES = [
    ("reply_engine.poller", "errors"), ("reply_engine.poller", "replies_stuck"),
    ("reply_engine.poller", "flush_failed"), ("reply_engine.poller", "escalation_failed"),
    ("reply_engine.approval", "push_failed"), ("reply_engine.approval", "send_failed"),
    ("reply_engine.approval", "recipient_mismatch"), ("reply_engine.approval", "blocked_invite_claim"),
    ("reply_engine.pipeline_sync", "skipped_ghl_unreadable"), ("reply_engine.cadence", "d1_held_no_base_url"),
    ("reply_engine.cadence", "d6_card_no_base_url"), ("ghl.upsert_contact", "skipped_no_token"),
    ("some.new_job", "a_status_nobody_has_seen"),
]


@pytest.mark.parametrize("job,status", REAL_FAILURES)
def test_a_real_failure_status_fails_the_watch(tmp_env, capsys, job, status):
    data = _healthy_records()
    data["obs:job:20260924120000:real"] = {"ts_utc": "2026-09-24T12:00:00+00:00", "job": job,
                                           "status": status, "mode": "shadow", "details": {}}
    assert _report(data) == 1
    _out, crit = _criteria(capsys)
    c = crit["every Job_Log status is on the healthy list"]
    assert c["passed"] is False and ("%s %s x1" % (job, status)) in c["detail"]


def test_the_probe_statuses_fail(tmp_env):
    """probe_watch_statuses.py, as a regression test."""
    until = datetime(2026, 9, 25, 15, 0, tzinfo=timezone.utc)
    start = until - timedelta(hours=49)
    ts = lambda h: (start + timedelta(hours=h)).isoformat()
    jobs = [{"ts_utc": ts(0), "job": "modal.pipeline_sync", "status": "tick", "mode": "shadow"}]
    jobs += [{"ts_utc": ts(i + 1), "job": j, "status": st, "mode": "shadow"} for i, (j, st) in enumerate([
        ("reply_engine.poller", "errors"), ("reply_engine.poller", "replies_stuck"),
        ("reply_engine.approval", "push_failed"), ("reply_engine.poller", "escalation_failed"),
        ("reply_engine.poller", "flush_failed"), ("reply_engine.approval", "send_failed")])]
    rep = watch_report.build_report(jobs, [], {"pipeline_sync": "0 6 * * *"}, None, until, 48.0)
    assert rep["automated_passed"] is False
    table = watch_report.render(rep, None).split("MANUAL")[0]
    for status in ("errors", "replies_stuck", "push_failed", "escalation_failed", "flush_failed", "send_failed"):
        assert status in table


def test_a_daily_job_that_missed_one_of_two_runs_fails(tmp_env, capsys):
    """No slack: the old max(1, 5%) let a daily job miss one of its two runs."""
    data = dict((k, v) for k, v in _healthy_records().items()
                if not (v.get("job") == "modal.pipeline_sync" and v["ts_utc"].startswith("2026-09-24")))
    assert _report(data) == 1
    _out, crit = _criteria(capsys)
    c = crit["pipeline_sync ran on schedule"]
    assert c["passed"] is False and "1 of 2 due runs" in c["detail"] and "2026-09-24T11:00:00" in c["detail"]


def test_a_late_or_manual_row_cannot_stand_in_for_a_missed_run():
    cron = "30 7 * * *"
    start = datetime(2026, 9, 23, 5, 0, tzinfo=timezone.utc)
    until = start + timedelta(hours=48)
    # the 07:30 CDT run on the 23rd is missing; a manual run at 15:00 CDT the same day is not it
    rows = [datetime(2026, 9, 23, 20, 0, 5, tzinfo=timezone.utc), datetime(2026, 9, 24, 12, 30, 40, tzinfo=timezone.utc)]
    m = watch_report.match_runs(cron, rows, start, until, 720)
    assert m["checked"] == 2 and m["missing"] == ["2026-09-23T12:30:00+00:00"]


def test_every_status_the_deployed_code_writes_is_classified():
    """Scans the deployed modules for Job_Log statuses. A new status must be
    added to HEALTHY_STATUSES or KNOWN_FAILURES before the watch can read it."""
    import ast
    import glob
    import os

    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    files = (glob.glob(os.path.join(base, "services", "reply_engine", "*.py"))
             + glob.glob(os.path.join(base, "shared", "*.py"))
             + [os.path.join(base, "jobs", n) for n in ("precall_tick.py", "appointments_tick.py", "pipeline_sweep.py")])
    first_arg = {"_log_job", "_log_budget"}
    second_arg = {"log_run", "_log", "_log_row"}
    found = set()
    for path in files:
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            index = 0 if name in first_arg else 1 if name in second_arg else None
            if index is None or len(node.args) <= index:
                continue
            arg = node.args[index]
            values = [arg] if not isinstance(arg, ast.IfExp) else [arg.body, arg.orelse]
            for v in values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    found.add(v.value)
    # Statuses built at run time (read from each module by hand).
    found.update(["partial", "dry_run_partial", "recipient_mismatch", "recipient_unconfirmed",
                  "skipped_ghl_unreadable", "live_write_intent", "live_write_ok", "live_write_failed"])
    assert len(found) > 40
    unclassified = sorted(st for st in found
                          if st not in watch_report.HEALTHY_STATUSES and st not in watch_report.KNOWN_FAILURES
                          and not st.startswith(watch_report.FAIL_PREFIXES))
    assert unclassified == []
    assert not (watch_report.HEALTHY_STATUSES & watch_report.KNOWN_FAILURES)


def test_the_text_report_prints_the_job_status_table(tmp_env, capsys):
    data = _healthy_records()
    data["obs:job:20260924120000:x"] = {"ts_utc": "2026-09-24T12:00:00+00:00", "job": "reply_engine.poller",
                                        "status": "errors", "mode": "shadow", "details": {}}
    store = FakeModalStore(data, read_only=True)
    assert watch_report.main(["--since", START.isoformat(), "--skip-laptop"], store=store, now=END) == 1
    text = capsys.readouterr().out
    assert "JOB / STATUS TABLE" in text
    assert "FAIL" in text and "reply_engine.poller" in text and "errors" in text
    assert "HEALTHY" in text and "modal.poller" in text


def test_a_record_made_in_live_mode_fails(tmp_env, capsys):
    data = _healthy_records()
    data["obs:shadow:20260924:live"] = {"ts_utc": "2026-09-24T12:00:00+00:00", "mode": "live",
                                        "system": "instantly", "action": "reply", "payload": {}}
    assert _report(data) == 1
    _out, crit = _criteria(capsys)
    assert crit["zero records written in live mode"]["passed"] is False


def test_a_schedule_that_stopped_running_fails(tmp_env, capsys):
    data = dict((k, v) for k, v in _healthy_records().items()
                if not (v.get("job") == "modal.cadence_tick" and v["ts_utc"] > "2026-09-24T12"))
    assert _report(data) == 1
    _out, crit = _criteria(capsys)
    assert crit["cadence_tick ran on schedule"]["passed"] is False
    assert crit["poller ran on schedule"]["passed"] is True


def test_a_weekend_only_watch_proves_nothing_about_the_weekday_veto_run(tmp_env, capsys):
    saturday = datetime(2026, 9, 26, 5, 0, tzinfo=timezone.utc)
    data = _healthy_records(start=saturday, end=saturday + timedelta(hours=48))
    store = FakeModalStore(data, read_only=True)
    assert watch_report.main(["--json", "--skip-laptop", "--since", saturday.isoformat()], store=store,
                             now=saturday + timedelta(hours=48)) == 1
    _out, crit = _criteria(capsys)
    assert crit["cadence_veto_ping ran on schedule"]["passed"] is False
    assert "never due" in crit["cadence_veto_ping ran on schedule"]["detail"]


def test_an_unreadable_store_exits_2(tmp_env, capsys):
    class Broken(object):
        class _D(object):
            def items(self):
                raise RuntimeError("network down")

        _dict = _D()

    assert watch_report.main(["--since", START.isoformat()], store=Broken(), now=END) == 2
    assert "No evidence" in capsys.readouterr().out


def test_expected_runs_reads_crons_in_central_time():
    day = datetime(2026, 9, 23, 5, 0, tzinfo=timezone.utc)          # Wed 00:00 CDT
    assert watch_report.expected_runs("*/5 * * * *", day, day + timedelta(hours=1)) == 12
    assert watch_report.expected_runs("0 7-19 * * *", day, day + timedelta(days=1)) == 13
    assert watch_report.expected_runs("30 9 * * 1-5", day, day + timedelta(days=7)) == 5
    assert watch_report.expected_runs("30 7 * * *", day, day + timedelta(days=2)) == 2


# ----------------------------------------------------- review item 5: the laptop half
def _laptop_runs(start=START, end=END, drop=None, status="ok"):
    out = []
    for name, cron in watch_report.laptop_schedules().items():
        for t in watch_report.due_times(cron, start, end):
            if drop and drop(name, t):
                continue
            out.append({"name": name, "status": status, "ts_start": (t + timedelta(seconds=3)).isoformat(),
                        "exit_code": 0 if status == "ok" else 1, "warnings": []})
    return out


def _write_runs(tmp_path, runs):
    path = tmp_path / "runs.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in runs), encoding="utf-8")
    return str(path)


def _laptop_report(tmp_path, runs, capsys):
    store = FakeModalStore(_healthy_records(), read_only=True)
    argv = ["--json", "--since", START.isoformat()]
    if runs is not None:
        argv += ["--laptop-runs", _write_runs(tmp_path, runs)]
    else:
        argv += ["--laptop-runs", str(tmp_path / "no_such_runs.jsonl")]
    code = watch_report.main(argv, store=store, now=END)
    out, crit = _criteria(capsys)
    return code, out, crit


def test_laptop_runs_on_schedule_pass_and_weekly_jobs_are_not_proven(tmp_path, tmp_env, capsys):
    code, out, crit = _laptop_report(tmp_path, _laptop_runs(), capsys)
    assert code == 0, [c for c in out["criteria"] if not c["passed"]]
    assert crit["laptop daily_metrics ran on schedule"]["passed"] is True
    assert crit["every laptop run is ok with no warning"]["passed"] is True
    # Wed-Fri 00:00 CDT: the Friday/Monday/Sunday jobs are never due, so nothing is proven for them
    assert any("retro_packet" in m and "nothing proven" in m for m in out["manual_not_checked"])
    assert "laptop retro_packet ran on schedule" not in crit


def test_a_missed_laptop_run_fails(tmp_path, tmp_env, capsys):
    runs = _laptop_runs(drop=lambda name, t: name == "deliverability_monitor" and t.day == 24)
    code, _out, crit = _laptop_report(tmp_path, runs, capsys)
    assert code == 1
    assert crit["laptop deliverability_monitor ran on schedule"]["passed"] is False


def test_a_failed_or_warned_laptop_run_fails(tmp_path, tmp_env, capsys):
    runs = _laptop_runs()
    runs[0] = dict(runs[0], status="failed", exit_code=1)
    runs[1] = dict(runs[1], warnings=["ordering_not_met: no run today for inbox_placement"])
    code, _out, crit = _laptop_report(tmp_path, runs, capsys)
    assert code == 1
    assert crit["every laptop run is ok with no warning"]["passed"] is False


def test_no_laptop_runs_file_is_a_failure_not_a_pass(tmp_path, tmp_env, capsys):
    code, _out, crit = _laptop_report(tmp_path, None, capsys)
    assert code == 1
    assert crit["every laptop run is ok with no warning"]["passed"] is False
    assert crit["laptop daily_metrics ran on schedule"]["passed"] is False


def test_skip_laptop_lists_it_as_not_checked(tmp_env, capsys):
    assert _report(_healthy_records()) == 0
    out, _crit = _criteria(capsys)
    assert any("laptop half" in m for m in out["manual_not_checked"])
