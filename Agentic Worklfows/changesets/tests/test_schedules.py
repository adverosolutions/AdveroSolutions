"""The schedule change-set is data, derived from what actually deploys.

A hand-maintained copy of a schedule is worse than none: the first symptom of
one that drifted is a job that quietly stopped running, and that looks exactly
like a quiet week.
"""
import importlib.util
import json
import os
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parents[2]
SCHEDULES_DIR = BASE_DIR / "changesets" / "schedules"
SCHEDULES_JSON = SCHEDULES_DIR / "schedules.json"
INSTALL_SH = SCHEDULES_DIR / "install_schedules.sh"


def _data():
    with open(str(SCHEDULES_JSON), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _builder():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "build_schedules", str(SCHEDULES_DIR / "build_schedules.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_schedules_json_is_not_stale():
    """--check is the gate. Adding a schedule to modal_app without regenerating
    leaves the change-set describing a system that no longer exists."""
    assert _builder().main(["--check"]) == 0


def test_every_schedule_that_deploys_is_in_the_change_set():
    from services.reply_engine import modal_app

    names = set(entry["name"] for entry in _data()["schedules"])
    assert names == set(modal_app.SCHEDULES)
    on_modal = set(e["name"] for e in _data()["schedules"] if e["runtime"] == "modal")
    assert on_modal == set(modal_app.MODAL_SCHEDULES)
    assert set(modal_app.SCHEDULED_FUNCTIONS) <= on_modal


def test_every_entry_says_what_it_runs_when_and_in_which_mode():
    for entry in _data()["schedules"]:
        for field in ("name", "module", "purpose", "command", "cron_ct", "timezone",
                      "cron_utc_cdt", "cron_utc_cst", "mode", "shadow_safe", "writes"):
            assert entry.get(field) not in (None, ""), (entry["name"], field)
        assert entry["mode"] == "shadow", entry["name"]
        assert entry["timezone"] == "America/Chicago", entry["name"]
        assert len(entry["cron_ct"].split()) == 5, entry["name"]


def test_the_one_job_that_spends_money_is_marked_not_shadow_safe():
    """Shadow stops Instantly, GHL and the notifier. It does NOT stop Apify,
    MillionVerifier or a model call, so the list factory is the one schedule
    that is not safe to simply leave running."""
    entries = {e["name"]: e for e in _data()["schedules"]}
    assert entries["list_factory"]["shadow_safe"] is False
    assert "ALLOW_PAID_CALLS" in " ".join(entries["list_factory"]["needs"])
    assert entries["list_factory"].get("shadow_note")
    unsafe = [e["name"] for e in _data()["schedules"] if not e["shadow_safe"]]
    assert unsafe == ["list_factory"], (
        "a new schedule claims it is unsafe in shadow; say why in build_schedules.META: %s" % unsafe)


def test_the_utc_conversions_refuse_to_guess_a_day_rollover():
    """A naive hour shift turns 19:15 CT Friday into 01:15 UTC Saturday and runs
    the client scorecard a day early for half the year. The generator flags the
    three cases rather than emitting a wrong cron silently."""
    build = _builder()
    # a plain hour moves
    assert build.utc_cron("0 7 * * *", 5) == "0 12 * * *"
    # an interval means the same in every zone
    assert build.utc_cron("*/10 * * * *", 5) == "*/10 * * * *"
    # a rollover is flagged, not guessed
    assert "NEXT UTC day" in build.utc_cron("15 19 * * 5", 6)
    # a range that would cross midnight is flagged, not truncated
    assert "CROSSES MIDNIGHT" in build.utc_cron("0 7-19 * * *", 5)


def test_the_ordering_constraints_are_carried_into_the_data():
    from services.reply_engine import modal_app

    entries = {e["name"]: e for e in _data()["schedules"]}
    for producer, (consumer, _why) in modal_app.SCHEDULE_ORDERING.items():
        assert entries[producer]["must_run_before"]["schedule"] == consumer
        assert entries[producer]["must_run_before"]["why"]


def test_the_install_script_is_documented_and_was_not_run():
    """It deploys the Modal app, which is a live change under Lorenzo's
    controlled-environment rule. It exists so that going live is a reviewed
    file rather than a command reconstructed from memory at 07:00."""
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "DOCUMENTED AND NOT RUN" in text
    assert "--preflight" in text and "--deploy" in text
    # the deploy half must ask before it acts
    assert "read -r -p" in text and "DEPLOY" in text
    # and it must not be executable, so it cannot be run by a stray ./
    assert not os.access(str(INSTALL_SH), os.X_OK), (
        "install_schedules.sh is executable; it is meant to be read and run deliberately with bash")


def test_the_readme_names_the_daylight_saving_trap():
    """The 18:00 CT metrics run pinned to 23:00 UTC becomes 17:00 CT in
    November and misses the last hour of the sending day, every day, silently."""
    readme = (SCHEDULES_DIR / "README.md").read_text(encoding="utf-8")
    assert "2026-11-01" in readme
    assert "daily_metrics" in readme


def test_the_preflight_entrypoint_check_can_actually_pass():
    """The preflight's own gate used to refuse every deploy.

    It tested ``not callable(getattr(modal_app, name))``. A decorated
    ``@app.function`` is a ``modal.Function`` object, and ``modal.Function`` is
    not callable in modal 1.2.x, so step 2 printed
    ``REFUSING: poller has no modal function; ...`` for all twenty schedules and
    the documented path to go live dead-ended at its first command.
    """
    modal = pytest.importorskip("modal")
    from services.reply_engine import modal_app

    for name in modal_app.SCHEDULED_FUNCTIONS:
        fn = getattr(modal_app, name, None)
        assert isinstance(fn, modal.Function), name
        assert not callable(fn), (
            "%s is callable now, so the old preflight check would pass again; "
            "keep the isinstance form anyway, it says what it means" % name)

    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "isinstance(fn, modal.Function)" in text
    assert "callable(getattr(modal_app" not in text


def test_the_deploy_warning_counts_the_schedules_it_would_register():
    """`modal deploy` is all-or-nothing, so the number in the prompt is the
    number of things that start running unattended. With DEPLOY_TIERS that
    number depends on the deploy, so the script reads it from modal_app
    instead of carrying a digit that goes stale."""
    from services.reply_engine import modal_app

    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "len(modal_app.SCHEDULED_FUNCTIONS)" in text
    assert "all ${count} schedules at once" in text
    assert "these ${count} schedules?" in text

    # The README is the file a person reads under pressure. Digits, pinned to
    # the default (sales-only) deploy.
    count = len(modal_app.SCHEDULED_FUNCTIONS)
    readme = (SCHEDULES_DIR / "README.md").read_text(encoding="utf-8")
    assert "all %d Modal schedules at once" % count in readme, \
        "changesets/schedules/README.md rollback line does not say %d" % count

    entries = _data()["schedules"]
    shadow_safe = sum(1 for s in entries if s.get("shadow_safe"))
    assert "`shadow_safe` is `true` for %d of the %d schedules" % (shadow_safe, len(entries)) in readme, \
        "README shadow_safe count is not %d of %d" % (shadow_safe, len(entries))


# ---------------------------------------------- R4: the Modal-vs-laptop split
def test_the_real_split_is_valid():
    from services.reply_engine import modal_app

    assert _builder().validate(modal_app) == []


def test_every_file_handoff_job_runs_on_the_laptop():
    build = _builder()
    entries = {e["name"]: e for e in _data()["schedules"]}
    for name in build.MUST_RUN_ON_LAPTOP:
        assert entries[name]["runtime"] == "laptop", name
        assert entries[name]["why_laptop"], name
    # the named R4 set, spelled out so a later edit of the builder cannot shrink it silently
    for name in ("deliverability_monitor", "inbox_placement", "autoresponder_canary", "list_factory",
                 "client_scorecard"):
        assert name in build.MUST_RUN_ON_LAPTOP, name


def test_validate_refuses_a_file_handoff_job_on_modal(monkeypatch):
    from services.reply_engine import modal_app

    sched = modal_app.SCHEDULES["deliverability_monitor"]
    monkeypatch.setitem(modal_app.SCHEDULES, "deliverability_monitor", sched._replace(runtime="modal"))
    problems = " ".join(_builder().validate(modal_app))
    assert "deliverability_monitor hands off through files and must run on the laptop" in problems
    # its ordering pairs are now split across runtimes too
    assert "split across runtimes" in problems


def test_validate_refuses_a_second_0730_sweep(monkeypatch):
    from services.reply_engine import modal_app

    build = _builder()
    monkeypatch.setitem(modal_app.SCHEDULES, "positive_sweep",
                        modal_app.Schedule("30 7 * * *", "07:30", "ops", "laptop", ("--now",)))
    monkeypatch.setitem(modal_app.SCHEDULE_JOB_MODULE, "positive_sweep", "jobs.positive_sweep")
    monkeypatch.setitem(build.META, "positive_sweep", dict(build.META["pipeline_sweep"]))
    problems = " ".join(build.validate(modal_app))
    assert "exactly one scheduled entry" in problems


def test_every_entry_carries_its_tier_and_runtime():
    data = _data()
    for entry in data["schedules"]:
        assert entry["tier"] in ("sales", "marketing", "ops", "fulfillment"), entry["name"]
        assert entry["runtime"] in ("modal", "laptop"), entry["name"]
    assert data["deploy_default_tiers"] == ["sales"]
    assert sorted(data["tiers"]["sales"]["modal"]) == sorted(
        e["name"] for e in data["schedules"] if e["tier"] == "sales")


def test_the_list_factory_runs_the_real_sunday_command():
    """MKT-3, the schedule half: `--now --niche cleaning` refused on purpose
    (no source), so the Sunday run never ran."""
    entries = {e["name"]: e for e in _data()["schedules"]}
    lf = entries["list_factory"]
    assert lf["command"] == "python3 -m jobs.list_factory --now --all-campaigns --refresh-suppression"
    assert lf["argv"] == ["--now", "--all-campaigns", "--refresh-suppression"]
    assert lf["runtime"] == "laptop"


# ------------------------------------------------- the staged laptop files
def _laptop_files():
    import plistlib

    directory = SCHEDULES_DIR / "laptop"
    plists = {}
    for path in sorted(directory.glob("*.plist")):
        with open(str(path), "rb") as fh:
            plists[path.name] = plistlib.load(fh)
    crontab = (directory / "crontab.txt").read_text(encoding="utf-8")
    return plists, crontab


def test_every_laptop_schedule_has_a_staged_plist_and_a_crontab_line():
    plists, crontab = _laptop_files()
    laptop = [e for e in _data()["schedules"] if e["runtime"] == "laptop"]
    modal_names = [e["name"] for e in _data()["schedules"] if e["runtime"] == "modal"]
    # plus the self-test agent: no schedule, started by hand in step 2c
    assert sorted(plists) == sorted(["com.advero.%s.plist" % e["name"] for e in laptop]
                                    + ["com.advero.self_test.plist"])
    self_test = plists["com.advero.self_test.plist"]
    assert "StartCalendarInterval" not in self_test and self_test["RunAtLoad"] is False
    assert self_test["ProgramArguments"][2:] == ["--self-test"]
    for entry in laptop:
        doc = plists["com.advero.%s.plist" % entry["name"]]
        assert doc["Label"] == "com.advero.%s" % entry["name"]
        assert doc["ProgramArguments"][1].endswith("changesets/schedules/laptop_runner.py")
        assert doc["ProgramArguments"][2] == entry["name"]
        # not retried: no KeepAlive, and nothing starts at load
        assert "KeepAlive" not in doc and doc["RunAtLoad"] is False
        # the runner decides the mode per job; the plist never carries it
        for key in ("MODE", "ALLOW_LIVE_WRITES", "ALLOW_PAID_CALLS"):
            assert key not in doc["EnvironmentVariables"], (entry["name"], key)
        assert "laptop_runner.py %s " % entry["name"] in crontab
    for name in modal_names:
        assert "laptop_runner.py %s " % name not in crontab
    assert "MODE=" not in crontab.replace("NOTIFY_SHADOW_SEND=", "")


def test_launchd_intervals_expand_weekday_ranges_and_refuse_intervals():
    build = _builder()
    assert build.launchd_intervals("0 9 * * 1-5") == [
        {"Minute": 0, "Hour": 9, "Weekday": d} for d in (1, 2, 3, 4, 5)]
    assert build.launchd_intervals("0 9 * * 0") == [{"Minute": 0, "Hour": 9, "Weekday": 0}]
    assert build.launchd_intervals("0 18 * * *") == [{"Minute": 0, "Hour": 18}]
    with pytest.raises(ValueError):
        build.launchd_intervals("*/5 * * * *")


def test_check_fails_on_a_hand_edited_staged_file(tmp_path, monkeypatch):
    build = _builder()
    laptop = tmp_path / "laptop"
    laptop.mkdir()
    out = tmp_path / "schedules.json"
    monkeypatch.setattr(build, "LAPTOP_DIR", str(laptop))
    monkeypatch.setattr(build, "OUT_PATH", str(out))
    assert build.main([]) == 0
    assert build.main(["--check"]) == 0
    crontab = laptop / "crontab.txt"
    crontab.write_text(crontab.read_text(encoding="utf-8") + "MODE=live\n", encoding="utf-8")
    assert build.main(["--check"]) == 1


def test_the_image_check_catches_a_module_the_mounts_do_not_carry(monkeypatch):
    """The laptop has the whole repo on sys.path, so a local import proves
    nothing about the container. The check imports from the mounts alone."""
    from services.reply_engine import modal_app

    build = _builder()
    assert build.check_image(["jobs.pipeline_sweep"]) == []
    trimmed = dict((k, v) for k, v in modal_app.LOCAL_DIRS.items() if not v.endswith("/jobs"))
    monkeypatch.setattr(modal_app, "LOCAL_DIRS", trimmed)
    problems = build.check_image(["jobs.pipeline_sweep"])
    assert problems and "jobs.pipeline_sweep" in problems[0]


def test_the_preflight_is_honest_about_what_it_cannot_check():
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "NOT CHECKED" in text
    assert "Preflight passed." not in text
    assert "were NOT checked" in text
    # the plan quota is listed with the count of crons this deploy registers
    assert "deploy_summary" in text and "quota" in text
    # the URL comes from the deploy output, and /health is verified after
    assert "modal app list" not in text
    assert "verify_health.py --expect-mode" in text
    assert "--check-image" in text


def test_the_image_check_refuses_a_package_outside_requirements(tmp_path, monkeypatch):
    """Review item 10f: a package installed on the laptop but not in
    requirements.txt must fail, even though the laptop can import it."""
    from services.reply_engine import modal_app

    build = _builder()
    assert "pytest" not in build.allowed_imports()
    probe = tmp_path / "advero_probe_pkg"
    probe.mkdir()
    (probe / "__init__.py").write_text("", encoding="utf-8")
    (probe / "uses_pytest.py").write_text("import pytest  # not in the image\n", encoding="utf-8")
    (probe / "uses_httpx.py").write_text("import httpx  # in requirements.txt\n", encoding="utf-8")
    dirs = dict(modal_app.LOCAL_DIRS)
    dirs[str(probe)] = modal_app.REMOTE_ROOT + "/advero_probe_pkg"
    monkeypatch.setattr(modal_app, "LOCAL_DIRS", dirs)
    assert build.check_image(["advero_probe_pkg.uses_httpx"]) == []
    problems = build.check_image(["advero_probe_pkg.uses_pytest"])
    assert any("not in the image requirements" in p for p in problems)
    assert any("outside requirements.txt: pytest" in p for p in problems)


def test_allowed_imports_follow_requirements_txt(tmp_path):
    build = _builder()
    req = tmp_path / "requirements.txt"
    req.write_text("# c\nfastapi==1\npython-dotenv==1.0.0\nuvicorn[standard]==0.3\ngoogle-auth==2\n", encoding="utf-8")
    assert build.allowed_imports(str(req)) == ["dotenv", "fastapi", "google", "modal", "uvicorn"]


def test_launchd_logs_go_outside_the_protected_desktop_folder():
    """Review item 5: launchd opens the log file itself; ~/Desktop is guarded
    by macOS privacy protection, ~/Library/Logs is not."""
    plists, _crontab = _laptop_files()
    for doc in plists.values():
        assert "/Library/Logs/advero/" in doc["StandardOutPath"]
        assert "/Desktop/" not in doc["StandardOutPath"]


def test_the_deploy_answer_is_read_from_the_terminal_and_the_handoff_start_is_saved():
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert '< /dev/tty' in text and "[type DEPLOY]" in text
    # D1 round 3, defect 1: the first pass records the HAND-OFF start through
    # watch_clock.py; the report start is a separate, later file
    assert "watch_clock.py begin ${NEW_WATCH}" in text
    assert "watch_start.txt" not in text
    assert "If the live deploy fails" in text


def _deploy_body(text):
    return text[text.index("\ndeploy() {"):text.index('\ncase "$MODE_ARG" in')]


def test_the_live_flip_checks_the_preflight_stamp_and_runs_nothing_between_secret_and_deploy():
    """D1 round 3, defect 5: the preflight passes BEFORE the live secret exists;
    between the secret and `modal deploy` nothing slow or fallible runs."""
    body = _deploy_body(INSTALL_SH.read_text(encoding="utf-8"))
    stamp = body.index("preflight_stamp.py check")
    answer = body.index("[type DEPLOY]")
    secret = body.index("modal_secret.py --mode live --base-url \"$url\" --create")
    deploy = body.index("python3 -m modal deploy services/reply_engine/modal_app.py")
    assert stamp < answer < secret < deploy
    live_branch = body[body.index('if [ "$EXPECT_MODE" = "live" ]; then'):body.index("  else\n    preflight\n")]
    assert "preflight\n" not in live_branch.replace("preflight_stamp.py check", ""), \
        "the live path runs no preflight of its own"
    between = body[secret:deploy]
    for slow in ("preflight", "summary", "verify_health", "watch_clock", "read -r"):
        assert slow not in between.replace("secret_outcome_since", ""), slow
    # the state that arms the abort text is set BEFORE the secret call
    assert body.index('LIVE_SECRET_STATE="maybe"') < secret


def test_any_failure_after_the_live_secret_prints_the_abort_sequence():
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "trap on_exit EXIT" in text
    on_exit = text[text.index("on_exit() {"):text.index("trap on_exit EXIT")]
    assert '"$LIVE_SECRET_STATE" != "none"' in on_exit and "abort_text" in on_exit
    abort = text[text.index("abort_text() {"):text.index("on_exit() {")]
    for step in ("python3 -m modal app stop advero-reply-engine",
                 "modal_secret.py --mode shadow",
                 "watch_report.py --store-mode live --min-hours 0 --skip-laptop",
                 "install_schedules.sh --deploy shadow"):
        assert step in abort, step
    assert abort.index("app stop") < abort.index("--mode shadow") < abort.index("--deploy shadow")
    pre = text[text.index("preflight() {"):text.index("abort_text() {")]
    # the stamp is written last, after check 5, and only by the preflight
    assert pre.index("python3 -m pytest -q") < pre.index("preflight_stamp._write_after_preflight()")
    assert text.count("_write_after_preflight") == 1
    assert "preflight_stamp.py write" not in text


def _store_keys_module():
    spec = importlib.util.spec_from_file_location("laptop_store_keys", str(SCHEDULES_DIR / "laptop_store_keys.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runbook_store_table():
    """{key prefix: 'read only' | 'written'} from the step-7 laptop store table."""
    runbook = (BASE_DIR / "runbooks" / "deployment.md").read_text(encoding="utf-8")
    section = runbook[runbook.index("**The laptop store.**"):runbook.index("So nothing needs deleting")]
    scanner = _store_keys_module()
    rows = {}
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows[scanner.key_prefix(cells[0].strip("`"))] = cells[1]
    return rows


def test_the_runbook_names_every_laptop_store_key_the_code_can_touch():
    """D1 round 3, defect 8: the step-7 table is compared with a scan of the
    laptop jobs' code (changesets/schedules/laptop_store_keys.py), not with a
    hand-picked list, and says for each key whether any code writes it."""
    scanner = _store_keys_module()
    found = scanner.laptop_store_keys()
    assert found["unresolved"] == [], "a store key the scan cannot resolve: %s" % found["unresolved"]
    code = dict((scanner.key_prefix(k), "written" if k in found["written"] else "read only")
                for k in found["keys"])
    table = _runbook_store_table()
    assert sorted(table) == sorted(code), "runbook step 7 keys %s, the code touches %s" % (sorted(table),
                                                                                           sorted(code))
    for prefix, how in code.items():
        assert table[prefix] == how, "%s: the runbook says %r, the code %r" % (prefix, table[prefix], how)
    # the ones the round-2 review named
    for prefix in ("appointment:", "noshow_state:", "llm.spend_usd", "first_touch:"):
        assert prefix in code, prefix
    assert code["first_touch:"] == "read only"                # nothing in the repo writes it
    runbook = (BASE_DIR / "runbooks" / "deployment.md").read_text(encoding="utf-8")
    assert "python3 changesets/schedules/laptop_store_keys.py" in runbook


def test_the_store_key_scan_follows_constants_helpers_and_imports(tmp_path, monkeypatch):
    scanner = _store_keys_module()
    (tmp_path / "keys_mod.py").write_text(
        'PREFIX = "fake:thing:"\n', encoding="utf-8")
    (tmp_path / "job_mod.py").write_text(
        'from shared.fake_keys import PREFIX\n'
        'LOCAL = "fake.counter"\n'
        'def key_for(slug):\n'
        '    return PREFIX + slug\n'
        'def run(store, week):\n'
        '    store.get(LOCAL)\n'
        '    store.set(key_for(week), 1)\n'
        '    store.get("fake:%s:x" % week)\n'
        '    store.set_if_absent(f"fake:claim:{week}", 1)\n'
        '    store.get(mystery())\n', encoding="utf-8")
    paths = {"jobs.fake_job": str(tmp_path / "job_mod.py"), "shared.fake_keys": str(tmp_path / "keys_mod.py")}
    real = scanner._module_path
    monkeypatch.setattr(scanner, "_module_path", lambda name: paths.get(name) or real(name))
    sc = scanner.Scanner()
    found, unresolved, _elsewhere = sc.scan(sc.closure(["jobs.fake_job"]))
    assert sorted(found) == ["fake.counter", "fake:*", "fake:claim:*", "fake:thing:*"]
    assert sorted(sc.written) == ["fake:claim:*", "fake:thing:*"]
    assert len(unresolved) == 1 and "mystery" in unresolved[0]
