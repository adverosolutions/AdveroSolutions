"""modal_app import smoke test: importing must not deploy or contact Modal.

Also pins the two things that only fail in production: a cron string modal
validates server-side at deploy, and the entrypoint helper re-running a tick
whose side effects (replies sent, statuses updated) already happened.
"""
import importlib
import sys
import types

import pytest

modal = pytest.importorskip("modal")


def test_modal_app_imports_cleanly_and_declares_schedules():
    mod = importlib.import_module("services.reply_engine.modal_app")
    assert mod.APP_NAME == "advero-reply-engine"
    assert mod.app.name == "advero-reply-engine"
    assert mod.DICT_NAME == "advero-reply-engine-store"
    assert mod.SECRET_NAME == "advero-reply-engine"
    # Every schedule in the system, Modal and laptop alike, is in SCHEDULES;
    # positive_sweep is no longer scheduled (GOL-13: one O3 entry).
    assert set(mod.SCHEDULES) == {
        "poller", "approval_escalation", "cadence_tick", "cadence_veto_ping", "appointments_tick",
        "precall_tick", "no_show_watch", "pipeline_sync", "pipeline_sweep",
        "inbox_placement", "autoresponder_canary", "deliverability_monitor", "inbox_inventory",
        "retro_packet", "client_scorecard", "daily_metrics", "list_factory",
    }
    # Turned off by Lorenzo (2026-09-22): he runs them by hand. Their code
    # stays, and config/turned_off_jobs.json lists them; nothing schedules them.
    from shared import turned_off

    for name in ("campaign_verdicts", "upwork_rooms_am", "upwork_rooms_pm"):
        assert turned_off.is_off(name) and name not in mod.SCHEDULES and name not in mod.SCHEDULE_JOB_MODULE
        assert all(name not in pair[:1] and name != producer for producer, pair in mod.SCHEDULE_ORDERING.items())
    # precall_tick's lock is a file on its container's disk: max_containers=1
    # is what stops two overlapping Modal runs.
    assert mod.MODAL_MAX_CONTAINERS == {"precall_tick": 1, "no_show_watch": 1}
    assert "takes its own lock" not in mod.SCHEDULES["precall_tick"].when
    # R3: the default deploy is the sales tier, and all of it runs on Modal.
    assert mod.DEPLOY_TIERS == ("sales",)
    assert set(mod.SCHEDULED_FUNCTIONS) == {
        "poller", "approval_escalation", "cadence_tick", "cadence_veto_ping", "appointments_tick",
        "precall_tick", "no_show_watch", "pipeline_sync", "pipeline_sweep",
    }
    assert mod.SCHEDULES["poller"][0] == "*/5 * * * *"
    assert mod.SCHEDULES["appointments_tick"][0] == "*/10 * * * *"
    assert mod.SCHEDULES["precall_tick"][0] == "*/5 * * * *"
    assert mod.SCHEDULES["no_show_watch"][0] == "* 12-18 * * 1-5"
    assert tuple(mod.SCHEDULES["no_show_watch"].argv) == ("--no-show-watch",)
    # The reply SLA is five minutes, and the chase has to survive the poller
    # failing: run_once calls fetch_new_replies, unguarded, before it reaches
    # the chase, so any Instantly error silences the SLA unless this tick exists.
    assert mod.SCHEDULES["approval_escalation"][0] == "*/5 * * * *"
    assert mod.SCHEDULE_JOB_MODULE["approval_escalation"] == "services.reply_engine.approval"
    # The D1 veto window is 30 minutes and its push goes out at 09:30 CT. The
    # hourly tick fires on the hour, so without this the window is never served
    # and a vetoed D1 is sent anyway at 10:00.
    assert mod.SCHEDULES["cadence_veto_ping"][0] == "30 9 * * 1-5"
    assert set(mod.SCHEDULE_JOB_MODULE) == set(mod.SCHEDULES)
    for name in mod.SCHEDULED_FUNCTIONS + ["web"]:
        assert hasattr(mod, name), name
    for key in ("INSTANTLY_API_KEY", "GHL_PRIVATE_INTEGRATION_TOKEN", "ANTHROPIC_API_KEY", "NTFY_TOPIC",
                "REPLY_ENGINE_SECRET", "MODE", "ALLOW_LIVE_WRITES"):
        assert key in mod.SECRET_KEYS
    assert mod.REQUIREMENTS.exists()
    assert mod.REMOTE_ROOT + "/shared" in mod.LOCAL_DIRS.values()
    assert mod.REMOTE_ROOT + "/config" in mod.LOCAL_DIRS.values()


def test_every_cron_string_has_five_fields():
    """modal.Cron takes a 5-field Unix crontab expression and does no local
    validation, so a 6-field string is only rejected server-side at
    `modal deploy` and takes all five schedules down with it."""
    mod = importlib.import_module("services.reply_engine.modal_app")
    for name, sched in mod.SCHEDULES.items():
        assert len(sched.cron.split()) == 5, (name, sched.cron)


def test_schedules_are_ct_native_so_nothing_drifts_on_nov_1():
    mod = importlib.import_module("services.reply_engine.modal_app")
    assert mod.SCHEDULE_TZ == "America/Chicago"
    assert mod.SCHEDULES["cadence_tick"][0] == "0 7-19 * * *"    # 07:00-19:00 CT, the send window
    assert mod.SCHEDULES["pipeline_sync"][0] == "0 6 * * *"      # 06:00 CT
    assert mod.SCHEDULES["pipeline_sweep"][0] == "30 7 * * *"    # 07:30 CT
    schedule = mod.cron("pipeline_sweep")
    assert isinstance(schedule, modal.Cron)


def _minute_of_day(expr):
    """(hour, minute) for a fixed-time cron. None for */n or a range."""
    minute, hour = expr.split()[0], expr.split()[1]
    if not minute.isdigit() or not hour.isdigit():
        return None
    return int(hour) * 60 + int(minute)


def test_the_jobs_that_feed_another_job_run_before_it():
    """inbox_placement and autoresponder_canary write proposals into the SAME
    dated change-set the 07:00 monitor writes, and the monitor reads their
    sidecars to build the card. Scheduling either after its consumer silently
    costs a whole section of the morning card, with nothing failing.
    (campaign_verdicts -> retro_packet is gone: that job is turned off.)"""
    mod = importlib.import_module("services.reply_engine.modal_app")
    for producer, (consumer, why) in mod.SCHEDULE_ORDERING.items():
        early = _minute_of_day(mod.SCHEDULES[producer][0])
        late = _minute_of_day(mod.SCHEDULES[consumer][0])
        assert early is not None and late is not None, (producer, consumer)
        assert early < late, "%s (%s) must run before %s (%s): %s" % (
            producer, mod.SCHEDULES[producer][0], consumer, mod.SCHEDULES[consumer][0], why)


def test_every_service_a_scheduled_job_imports_is_mounted():
    """A job that imports services.metrics runs locally and dies with
    ModuleNotFoundError in the container, on its schedule, unattended."""
    mod = importlib.import_module("services.reply_engine.modal_app")
    mounted = set(mod.LOCAL_DIRS.values())
    for service in ("metrics", "retro", "experiments", "list_factory", "reply_engine"):
        assert mod.REMOTE_ROOT + "/services/" + service in mounted, service
    assert mod.REMOTE_ROOT + "/jobs" in mounted


def test_cron_helper_refuses_a_malformed_expression(monkeypatch):
    mod = importlib.import_module("services.reply_engine.modal_app")
    monkeypatch.setitem(mod.SCHEDULES, "cadence_tick", ("0 12-23,0 * * * *", "six fields"))
    with pytest.raises(ValueError) as exc:
        mod.cron("cadence_tick")
    assert "5-field" in str(exc.value)


def test_entrypoint_helper_degrades_when_module_missing(caplog):
    mod = importlib.import_module("services.reply_engine.modal_app")
    with caplog.at_level("WARNING"):
        result = mod._call_entrypoint("services.reply_engine.__definitely_missing__", ("run_once",))
    assert result is mod.MISSING
    assert "entrypoint_missing" in caplog.text


@pytest.fixture
def fake_module(monkeypatch):
    """Register a throwaway module in sys.modules and take it out again."""
    names = []

    def register(name, **attrs):
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        monkeypatch.setitem(sys.modules, name, module)
        names.append(name)
        return name

    return register


def test_entrypoint_does_not_rerun_the_tick_when_it_raises_typeerror(fake_module):
    """`except TypeError: return fn()` was a blind retry, not a signature
    fallback: a TypeError anywhere inside cadence.tick() re-ran the whole pass,
    re-sending every reply the first pass had already sent."""
    calls = []

    def run_once():
        calls.append("REPLY SENT to lead")
        raise TypeError("None > 5")

    name = fake_module("advero_fake_tick_module", run_once=run_once)
    mod = importlib.import_module("services.reply_engine.modal_app")
    with pytest.raises(TypeError):
        mod._call_entrypoint(name, ("run_once",))
    assert calls == ["REPLY SENT to lead"]      # exactly once


def test_a_module_that_raises_at_import_does_not_kill_the_tick(caplog, monkeypatch):
    mod = importlib.import_module("services.reply_engine.modal_app")

    def boom(name):
        raise KeyError("config key missing")

    monkeypatch.setattr(importlib, "import_module", boom)
    with caplog.at_level("WARNING"):
        assert mod._call_entrypoint("advero_fake_broken_module", ("run_once",)) is mod.MISSING
    assert "entrypoint_missing" in caplog.text


def test_kwargs_are_filtered_by_signature_not_by_catching_typeerror(fake_module):
    mod = importlib.import_module("services.reply_engine.modal_app")
    seen = {}

    def takes_now(now=None):
        seen["now"] = now
        return "ran"

    name = fake_module("advero_fake_kwargs_module", takes_now=takes_now)
    assert mod._call_entrypoint(name, ("takes_now",), now=7, unknown="x") == "ran"
    assert seen == {"now": 7}


def test_a_missing_entrypoint_is_logged_as_entrypoint_missing_not_as_a_healthy_tick(tmp_env):
    """deployment.md's 48-hour gate is "zero error rows in Job_Log". A deploy
    whose image dropped poller.py must not satisfy it silently."""
    from shared import job_log

    mod = importlib.import_module("services.reply_engine.modal_app")
    mod._log_tick("poller", mod._call_entrypoint("services.reply_engine.__definitely_missing__", ("run_once",)))
    rows = open(job_log.job_log_path(), "r", encoding="utf-8").read()
    assert "modal.poller" in rows and "entrypoint_missing" in rows
    assert ",tick," not in rows


def test_every_schedule_resolves_to_a_real_entrypoint():
    """_call_entrypoint returns MISSING and logs entrypoint_missing when the
    module has none of the candidate names, so the scheduled function looks
    healthy while doing nothing. Both cadence_tick and appointments_tick were
    in exactly that state: the run bodies live in jobs/, not in the module
    modal_app imports."""
    mod = importlib.import_module("services.reply_engine.modal_app")
    wanted = {
        "poller": ("services.reply_engine.poller", ("run_once", "tick", "poll", "main")),
        "cadence_tick": ("services.reply_engine.cadence", ("tick", "run_once", "main")),
        "appointments_tick": ("services.reply_engine.show_rate", ("appointments_tick", "tick", "run_once", "main")),
    }
    for schedule, (module_name, candidates) in wanted.items():
        target = importlib.import_module(module_name)
        found = [n for n in candidates if callable(getattr(target, n, None))]
        assert found, "%s: %s has none of %s" % (schedule, module_name, list(candidates))
        # and the entrypoint takes no required arguments, because the schedule calls it bare
        import inspect

        params = inspect.signature(getattr(target, found[0])).parameters
        required = [n for n, p in params.items()
                    if p.default is inspect.Parameter.empty and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)]
        assert required == [], "%s.%s needs %s" % (module_name, found[0], required)


def test_a_missing_entrypoint_is_logged_as_missing_not_as_a_healthy_tick(monkeypatch):
    mod = importlib.import_module("services.reply_engine.modal_app")
    empty = types.ModuleType("advero_empty_module")
    monkeypatch.setitem(sys.modules, "advero_empty_module", empty)
    assert mod._call_entrypoint("advero_empty_module", ("tick", "run_once")) is mod.MISSING
    assert mod._call_entrypoint("advero_module_that_does_not_exist", ("tick",)) is mod.MISSING


# ------------------------------------------- the two bodies called directly
def test_a_crashing_schedule_body_writes_an_error_row_and_re_raises(tmp_env):
    """pipeline_sync and pipeline_sweep call their bodies directly with the
    log_run AFTER the body and nothing catching, so a rotated
    INSTANTLY_API_KEY left Job_Log completely empty: zero `error` rows and zero
    `entrypoint_missing` rows, which is exactly what deployment.md's shadow
    exit criteria read as a clean deploy."""
    from shared import job_log

    mod = importlib.import_module("services.reply_engine.modal_app")
    with pytest.raises(RuntimeError):
        with mod._tick("pipeline_sync") as tick:
            raise RuntimeError("INSTANTLY_API_KEY missing")
    rows = open(job_log.job_log_path(), "r", encoding="utf-8").read()
    assert "modal.pipeline_sync" in rows and "error" in rows
    assert "INSTANTLY_API_KEY missing" in rows


def test_a_healthy_schedule_body_still_writes_a_tick_row(tmp_env):
    from shared import job_log

    mod = importlib.import_module("services.reply_engine.modal_app")
    with mod._tick("pipeline_sweep") as tick:
        tick["result"] = {"counts": {"total": 0}}
    rows = open(job_log.job_log_path(), "r", encoding="utf-8").read()
    assert "modal.pipeline_sweep" in rows and ",tick," in rows


def test_the_shadow_secret_keys_make_the_48h_gate_observable(tmp_env, monkeypatch):
    """In MODE=shadow a push is a guarded write: `notify()` records the intent
    into the container's .tmp/ and delivers nothing, so the documented 48-hour
    watch produced no 07:30 digest on the phone at all. NOTIFY_SHADOW_SEND=1
    opts the push (only ever to Lorenzo's own topic) back in."""
    from datetime import datetime, timedelta, timezone

    from shared import notify as notify_mod
    from jobs import pipeline_sweep as sweep

    mod = importlib.import_module("services.reply_engine.modal_app")
    assert "NOTIFY_SHADOW_SEND" in mod.SECRET_KEYS

    monkeypatch.setenv("MODE", "shadow")
    monkeypatch.delenv("ALLOW_LIVE_WRITES", raising=False)
    monkeypatch.setenv("NOTIFY", "on")                 # the container does not set NOTIFY=off
    monkeypatch.setenv("NTFY_TOPIC", "advero-test-topic")
    notify_mod.reset_for_tests()
    sent = []
    monkeypatch.setattr(notify_mod, "_send_ntfy",
                        lambda *a, **kw: sent.append((a, kw)) or {"ok": True, "status": 200})
    # Only the push leg is under test here. Patching ntfy alone used to leave
    # notify() free to fall through to _send_email, which - with NOTIFY=on and
    # the shadow bypass set below - opened a real smtp.gmail.com session.
    monkeypatch.setattr(notify_mod, "_send_email", lambda *a, **kw: False)

    now = datetime.now(timezone.utc) + timedelta(days=1)
    # without the key the push is swallowed by the shadow guard
    monkeypatch.delenv("NOTIFY_SHADOW_SEND", raising=False)
    blocked = sweep.run_sweep(now, received=[], manual=[], leads_by_email={}, ghl=None, dry_run=False)
    assert blocked["notified"]["sent"] is False and blocked["notified"]["shadow"] is True
    assert sent == []

    monkeypatch.setenv("NOTIFY_SHADOW_SEND", "1")
    result = sweep.run_sweep(now, received=[], manual=[], leads_by_email={}, ghl=None, dry_run=False)
    assert result["notified"]["sent"] is True
    assert len(sent) == 1


# ------------------------------------------------- R3: deploy-time tier selection
def test_deploy_tiers_default_to_sales_and_refuse_a_guess():
    mod = importlib.import_module("services.reply_engine.modal_app")
    assert mod.parse_deploy_tiers(None) == ("sales",)
    assert mod.parse_deploy_tiers("  ") == ("sales",)
    assert mod.parse_deploy_tiers("marketing, sales") == ("sales", "marketing")
    assert mod.parse_deploy_tiers("sales,ops,fulfillment,marketing") == mod.TIERS
    with pytest.raises(ValueError) as exc:
        mod.parse_deploy_tiers("sales,marketting")
    assert "marketting" in str(exc.value)
    # a deploy replaces the whole app: leaving sales out would silently remove it
    with pytest.raises(ValueError) as exc:
        mod.parse_deploy_tiers("marketing")
    assert "sales" in str(exc.value)


def test_every_schedule_carries_its_tier_and_runtime():
    mod = importlib.import_module("services.reply_engine.modal_app")
    for name, sched in mod.SCHEDULES.items():
        assert sched.tier in mod.TIERS, name
        assert sched.runtime in mod.RUNTIMES, name
        if sched.runtime == mod.RUNTIME_LAPTOP:
            assert isinstance(sched.argv, tuple), name
    # the whole sales tier runs on Modal, nothing else does (R3 + R4)
    assert set(mod.schedules_for(mod.RUNTIME_MODAL)) == set(mod.schedules_for(mod.RUNTIME_MODAL, ("sales",)))
    assert mod.schedules_for(mod.RUNTIME_LAPTOP, ("sales",)) == []


def test_a_tier_that_is_not_deployed_is_not_selected(monkeypatch):
    mod = importlib.import_module("services.reply_engine.modal_app")
    monkeypatch.setitem(mod.SCHEDULES, "advero_fake_ops_tick",
                        mod.Schedule("0 8 * * *", "08:00 CT", "ops", mod.RUNTIME_MODAL, None))
    assert "advero_fake_ops_tick" not in mod.schedules_for(mod.RUNTIME_MODAL, ("sales",))
    assert "advero_fake_ops_tick" in mod.schedules_for(mod.RUNTIME_MODAL, ("sales", "ops"))


def _import_in_child(extra_env):
    import json
    import os
    import subprocess

    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    code = ("import json, modal\n"
            "import services.reply_engine.modal_app as m\n"
            "print(json.dumps({'tiers': list(m.DEPLOY_TIERS), 'deployed': m.SCHEDULED_FUNCTIONS,\n"
            "  'registered': sorted(m.app.registered_functions), 'image_env': m.image_env(),\n"
            "  'plain': sorted(n for n in m.MODAL_SCHEDULES if not isinstance(getattr(m, n), modal.Function)),\n"
            "  'laptop_attrs': sorted(n for n in m.LAPTOP_SCHEDULES if hasattr(m, n))}))\n")
    env = dict(os.environ)
    env.update(extra_env)
    proc = subprocess.run([sys.executable, "-c", code], cwd=base, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True, timeout=120)
    return proc.returncode, (json.loads(proc.stdout.strip().splitlines()[-1]) if proc.returncode == 0 else proc.stderr)


def test_the_app_registers_exactly_the_deployed_schedules_plus_web():
    code, out = _import_in_child({"DEPLOY_TIERS": "sales"})
    assert code == 0, out
    assert out["tiers"] == ["sales"]
    assert out["registered"] == sorted(out["deployed"] + ["web"])
    assert out["plain"] == []
    # laptop jobs are not Modal functions at all (R4)
    assert out["laptop_attrs"] == []
    # the container re-imports the module and must make the same selection
    assert out["image_env"]["DEPLOY_TIERS"] == "sales"
    assert out["image_env"]["RUNTIME"] == "modal"
    assert "MODAL_DICT_NAME" not in out["image_env"]


def test_an_unknown_deploy_tier_fails_the_import_and_so_the_deploy():
    code, err = _import_in_child({"DEPLOY_TIERS": "sales,marketting"})
    assert code != 0
    assert "marketting" in err


def test_deploy_summary_counts_the_crons_for_the_plan_quota_check():
    mod = importlib.import_module("services.reply_engine.modal_app")
    summary = mod.deploy_summary()
    assert summary["crons"] == len(mod.SCHEDULED_FUNCTIONS) == 9
    assert summary["web_endpoints"] == 1
    assert summary["modal_functions"] == 10
    assert set(summary["laptop_schedules"]) == set(mod.LAPTOP_SCHEDULES)


# ------------------------------------------------ GOL-13: one scheduled O3 sweep
def test_only_one_schedule_drives_the_0730_sweep():
    mod = importlib.import_module("services.reply_engine.modal_app")
    o3 = [n for n in mod.SCHEDULES if mod.SCHEDULE_JOB_MODULE[n] in ("jobs.pipeline_sweep", "jobs.positive_sweep")]
    assert o3 == ["pipeline_sweep"]
    assert "positive_sweep" not in mod.SCHEDULES
    assert not hasattr(mod, "positive_sweep")


# ------------------------------------------------ R7: the paid-call wording
def test_the_list_factory_entry_says_paid_calls_do_not_need_live_mode():
    mod = importlib.import_module("services.reply_engine.modal_app")
    text = open(mod.__file__, "r", encoding="utf-8").read()
    assert "as well as live mode" not in text
    assert "on top of MODE=live" not in text
    when = mod.SCHEDULES["list_factory"].when
    assert "ALLOW_PAID_CALLS=1" in when and "live or not" in when


# ----------------------------------------- R5: the store name follows the mode
def test_the_dict_names_match_shared_store():
    from shared import store as store_mod

    mod = importlib.import_module("services.reply_engine.modal_app")
    assert mod.DICT_NAME == store_mod.MODAL_DICT_BASE
    for mode in ("shadow", "live"):
        assert mod.dict_name(mode) == store_mod.modal_dict_name(mode)
    assert mod.dict_name("shadow") != mod.dict_name("live")


# ---------------------------------------------- GOL-2: a failed tick is visible
def _rows():
    import csv

    from shared import job_log

    with open(str(job_log.job_log_path()), "r", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_a_job_that_exits_non_zero_fails_the_tick_and_records_the_exit_code(tmp_env, fake_module):
    import json

    calls = []

    def main(argv):
        calls.append(list(argv))
        return 1          # several jobs exit 1 on a partial run

    name = fake_module("advero_fake_partial_job", main=main)
    mod = importlib.import_module("services.reply_engine.modal_app")
    with pytest.raises(mod.JobFailed) as exc:
        mod._run_job(name, ["--now"], "advero_fake_partial_job")
    assert exc.value.exit_code == 1
    assert calls == [["--now"]]                      # once: never retried
    rows = [r for r in _rows() if r["job"] == "modal.advero_fake_partial_job"]
    assert [r["status"] for r in rows] == ["failed"]
    assert json.loads(rows[0]["details"])["exit_code"] == 1


def test_a_job_that_exits_zero_records_a_tick_with_its_exit_code(tmp_env, fake_module):
    import json

    name = fake_module("advero_fake_clean_job", main=lambda argv: 0)
    mod = importlib.import_module("services.reply_engine.modal_app")
    mod._run_job(name, [], "advero_fake_clean_job")
    rows = [r for r in _rows() if r["job"] == "modal.advero_fake_clean_job"]
    assert [r["status"] for r in rows] == ["tick"]
    assert json.loads(rows[0]["details"])["exit_code"] == 0


def test_a_missing_entrypoint_fails_the_scheduled_run(tmp_env):
    mod = importlib.import_module("services.reply_engine.modal_app")
    with pytest.raises(mod.EntrypointMissing):
        mod._scheduled("poller", lambda: mod._call_entrypoint("services.reply_engine.__nope__", ("run_once",)))
    rows = [r for r in _rows() if r["job"] == "modal.poller"]
    assert [r["status"] for r in rows] == ["entrypoint_missing"]


# ------------------------------------------ R5: live refuses without a cutover
def _iso(dt):
    return dt.replace(microsecond=0).isoformat()


@pytest.fixture
def real_push(monkeypatch):
    """The REAL notify path (guard_write, the live_write_intent row), with only
    the ntfy transport stubbed. No email leg."""
    from shared import notify as notify_mod

    sent = []
    monkeypatch.setenv("NOTIFY", "on")
    monkeypatch.setenv("NTFY_TOPIC", "test-topic-not-real")
    for key in ("GMAIL_SENDER_EMAIL", "GMAIL_APP_PASSWORD", "NOTIFY_EMAIL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(notify_mod, "_send_ntfy", lambda *a, **k: (sent.append(a[1]) or
                                                                  {"ok": True, "status": 200, "headers": {},
                                                                   "authenticated": False}))
    return sent


def test_a_live_deploy_before_the_cutover_leaves_the_live_engine_store_empty(tmp_env, live_mode, real_push):
    """Review item 3: the refused ticks, their alert claim and the alert's own
    live_write_intent row all land in the evidence store, so the cutover still
    sees a clean live store afterwards."""
    from shared import store as store_mod

    engine = store_mod.get_store(force_new=True)
    obs = store_mod.get_obs_store(force_new=True)
    mod = importlib.import_module("services.reply_engine.modal_app")
    ran = []
    for _ in range(3):
        with pytest.raises(mod.CutoverMissing):
            mod._scheduled("poller", lambda: ran.append(1) or {"ok": True})
    assert ran == []
    assert real_push == ["Live tick refused: cutover_missing"]          # one push a day, not one per tick
    rows = [r for r in _rows() if r["job"] == "modal.poller"]
    assert [r["status"] for r in rows] == ["refused"] * 3
    assert "cutover_missing" in rows[0]["details"]
    intents = [r for r in _rows() if r["job"] == "notify.push_email"]
    assert [r["status"] for r in intents] == ["live_write_intent"]      # the real notify path ran
    assert engine.keys("") == []                                        # nothing for the cutover to trip on
    assert [k for k in obs.keys("") if k.startswith(mod.CUTOVER_ALERT_PREFIX)]


def test_live_ticks_run_once_the_cutover_seeded_the_store(tmp_env, live_mode, real_push):
    from datetime import datetime, timezone

    from services.reply_engine import poller
    from shared import store as store_mod

    engine = store_mod.get_store(force_new=True)
    engine.set(poller.CURSOR_KEY, {"last_email_id": "e-1", "last_timestamp": "2026-09-25T14:40:00.000Z"})
    engine.set(store_mod.CUTOVER_KEY, {"cutover_at": _iso(datetime.now(timezone.utc))})
    mod = importlib.import_module("services.reply_engine.modal_app")
    ran = []
    mod._scheduled("poller", lambda: ran.append(1) or {"ok": True})
    assert ran == [1]
    assert engine.get(store_mod.CUTOVER_ACCEPTED_KEY)["job"] == "poller"


def test_a_stale_cutover_is_refused_until_redone(tmp_env, live_mode, real_push):
    """Review item 7c: a cutover older than the limit that no live tick ever
    accepted is refused; one already accepted keeps working."""
    from datetime import datetime, timedelta, timezone

    from shared import store as store_mod

    engine = store_mod.get_store(force_new=True)
    old = datetime.now(timezone.utc) - timedelta(minutes=store_mod.CUTOVER_MAX_AGE_MINUTES + 5)
    engine.set(store_mod.CUTOVER_KEY, {"cutover_at": _iso(old)})
    mod = importlib.import_module("services.reply_engine.modal_app")
    ran = []
    with pytest.raises(mod.CutoverMissing):
        mod._scheduled("cadence_tick", lambda: ran.append(1))
    assert ran == []
    rows = [r for r in _rows() if r["job"] == "modal.cadence_tick"]
    assert [r["status"] for r in rows] == ["refused"] and "cutover_stale" in rows[0]["details"]
    assert real_push == ["Live tick refused: cutover_stale"]
    engine.set(store_mod.CUTOVER_ACCEPTED_KEY, {"accepted_at": _iso(old)})
    mod._scheduled("cadence_tick", lambda: ran.append(1))
    assert ran == [1]


def test_the_live_poller_refuses_without_a_complete_cursor(tmp_env, live_mode, real_push):
    """The cheap poller guard, outside poller.py: an expired or missing cursor
    would walk back 20 pages. Other schedules still run."""
    from datetime import datetime, timezone

    from services.reply_engine import poller
    from shared import store as store_mod

    engine = store_mod.get_store(force_new=True)
    engine.set(store_mod.CUTOVER_KEY, {"cutover_at": _iso(datetime.now(timezone.utc))})
    engine.set(poller.CURSOR_KEY, {"last_email_id": "e-1"})                 # no timestamp: incomplete
    mod = importlib.import_module("services.reply_engine.modal_app")
    ran = []
    with pytest.raises(mod.CutoverMissing):
        mod._scheduled("poller", lambda: ran.append("poller"))
    mod._scheduled("cadence_tick", lambda: ran.append("cadence"))
    assert ran == ["cadence"]
    assert real_push == ["Live tick refused: cursor_missing"]


def test_precall_is_scheduled_quiet():
    """Review item 2: the 5-minute precall run pushes only when it has news."""
    mod = importlib.import_module("services.reply_engine.modal_app")
    assert tuple(mod.SCHEDULES["precall_tick"].argv) == ("--scheduled",)


def test_shadow_ticks_do_not_need_a_cutover(tmp_env, shadow_mode):
    from shared import store as store_mod

    store_mod.get_store(force_new=True)
    mod = importlib.import_module("services.reply_engine.modal_app")
    ran = []
    mod._scheduled("poller", lambda: ran.append(1) or {"ok": True})
    assert ran == [1]


# --------------------------------------- review item 2: precall pushes only with news
@pytest.fixture
def precall(tmp_env, shadow_mode, monkeypatch):
    import jobs.precall_tick as pt
    from shared import notify as notify_mod

    monkeypatch.setenv("NOTIFY", "off")                  # notify records into sent_in_test instead of sending
    monkeypatch.setattr(notify_mod, "sent_in_test", [])

    def load(result):
        monkeypatch.setattr(pt, "load_appointments", lambda ghl, now, fixture: dict(
            {"source": "ghl", "error": None, "appointments": [], "ghl_count": 0, "manual_count": 0,
             "manual_duplicates": [], "manual_stale": []}, **result))

    pt.load = load
    pt.pushes = lambda: list(notify_mod.sent_in_test)
    return pt


def _scheduled_argv(tmp_env, now):
    mod = importlib.import_module("services.reply_engine.modal_app")
    return list(mod.SCHEDULES["precall_tick"].argv) + ["--no-read", "--store", str(tmp_env / "s.json"),
                                                       "--now", now]


def test_an_idle_scheduled_precall_run_pushes_nothing(precall, tmp_env):
    precall.load({})
    for minute in ("00", "05", "10"):
        assert precall.main(_scheduled_argv(tmp_env, "2026-09-24T10:%s:00-05:00" % minute)) == 0
    assert precall.pushes() == []


def test_a_scheduled_run_with_a_failed_read_pushes_once_an_hour(precall, tmp_env):
    precall.load({"error": "ghl_token_missing", "source": "none"})
    for minute in ("00", "05", "10"):
        precall.main(_scheduled_argv(tmp_env, "2026-09-24T10:%s:00-05:00" % minute))
    assert len(precall.pushes()) == 1
    precall.main(_scheduled_argv(tmp_env, "2026-09-24T11:00:00-05:00"))
    assert len(precall.pushes()) == 2


def test_precall_tick_is_registered_with_max_containers_1(monkeypatch):
    mod = importlib.import_module("services.reply_engine.modal_app")
    seen = {}

    class App(object):
        def function(self, **kwargs):
            seen.update(kwargs)
            return lambda fn: fn

    monkeypatch.setattr(mod, "app", App())
    mod._register("precall_tick")
    assert seen["max_containers"] == 1 and seen["timeout"] == mod.MODAL_TIMEOUTS["precall_tick"]
    seen.clear()
    mod._register("poller")
    assert "max_containers" not in seen


def test_a_scheduled_run_with_a_brief_pushes(precall):
    assert precall.scheduled_push_due({"briefs": [{"id": "a"}]}, False) is True
    assert precall.scheduled_push_due({"proposals": [{"id": "p"}]}, False) is True
    assert precall.scheduled_push_due({"errors": ["boom"]}, False) is True
    assert precall.scheduled_push_due({"briefs": [], "proposals": [], "errors": []}, False) is False


def test_a_hand_run_still_pushes_its_digest(precall, tmp_env):
    precall.load({})
    assert precall.main(["--no-read", "--store", str(tmp_env / "s.json"), "--now", "2026-09-24T10:00:00-05:00"]) == 0
    assert len(precall.pushes()) == 1
