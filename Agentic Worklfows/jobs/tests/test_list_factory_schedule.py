"""MKT-3 and owner decision R10: the scheduled Sunday run can actually run,
fails loudly when it cannot, and feeds every configured campaign with
Cleaning Reactivation first."""
import json
import os

import pytest

from shared import settings

import jobs.list_factory as job
from services.list_factory import models, pipeline as pipeline_mod
from services.list_factory import suppression as supp_mod
from services.list_factory import targets as targets_mod

FIXTURE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "services", "list_factory", "fixtures", "source_cleaning_50.json",
)


@pytest.fixture
def captured(monkeypatch, tmp_path):
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.setenv("LIST_FACTORY_LEDGER_PATH", str(tmp_path / "ledger.csv"))
    rows = []
    pushes = []
    monkeypatch.setattr(job, "log_run", lambda j, status, details=None: rows.append((j, status, details or {})))
    monkeypatch.setattr(job, "notify", lambda title, body="", **kw: pushes.append((title, body, kw)))
    return {"rows": rows, "pushes": pushes, "tmp": tmp_path}


def _supp(tmp_path):
    from datetime import datetime, timezone

    supp = supp_mod.SuppressionList()
    for domain in ("gmail.com", "yahoo.com"):
        supp.add_domain(domain, "free mailbox provider")
    supp.complete = True
    supp.built_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    path = str(tmp_path / "supp.json")
    supp_mod.save_cache(supp, path)
    return path


# ------------------------------------------------ the scheduled command
def test_the_scheduled_command_no_longer_crashes_silently(captured):
    """`--now --niche cleaning` (schedules.json:214) used to raise
    `source=fixture needs --fixture <path>` with no Job_Log row and no push.
    It now refuses on purpose, with both."""
    rc = job.main(["--now", "--niche", "cleaning"])
    assert rc != 0
    assert captured["rows"], "no Job_Log row"
    assert captured["rows"][-1][1] in ("refused", "error")
    assert "--source" in captured["rows"][-1][2]["error"]
    assert captured["pushes"], "no push"
    assert captured["pushes"][-1][2].get("priority") == "high"


def test_now_never_falls_back_to_the_fixture_or_the_replay_verifier(captured):
    class A(object):
        fixtures = False
        source = "apify"
        verify = None
        dry_run = False
        preflight = False

    with pytest.raises(job.UsageError):
        job.resolve_source_and_verifier(A())
    A.verify = "millionverifier"
    assert job.resolve_source_and_verifier(A()) == ("apify", "millionverifier")
    A.fixtures = True
    A.verify = None
    assert job.resolve_source_and_verifier(A()) == ("fixture", "replay")


def test_any_crash_leaves_a_job_log_row_and_a_high_priority_push(captured, monkeypatch):
    def boom(*a, **k):
        raise ValueError("something nobody anticipated")

    monkeypatch.setattr(job, "run_factory", boom)
    rc = job.main(["--now", "--source", "apify", "--verify", "millionverifier", "--offline"])
    assert rc == 2
    assert captured["rows"][-1][1] == "error"
    assert "ValueError" in captured["rows"][-1][2]["error"]
    assert captured["pushes"] and captured["pushes"][-1][2]["priority"] == "high"


def test_an_argument_error_is_logged_and_pushed(captured):
    rc = job.main(["--now", "--source", "nonsense"])
    assert rc == 2
    assert captured["rows"][-1][1] == "error"
    assert captured["pushes"]


def test_the_sunday_command_names_a_real_source_and_verifier():
    """--all-campaigns takes them from the targets file: Apify and the real
    MillionVerifier, never the fixture or the replay."""
    targets = targets_mod.load()
    for group in targets_mod.niche_groups(targets):
        class A(object):
            fixtures = False
            source = None
            verify = None
            dry_run = False
            preflight = False

        assert job.resolve_source_and_verifier(A(), group) == ("apify", "millionverifier")


# ------------------------------------------------------ R10: the targets
def test_every_campaign_has_an_entry_and_cleaning_reactivation_runs_first():
    targets = targets_mod.load()
    keys = [e["campaign_key"] for e in targets["entries"]]
    assert sorted(keys) == sorted(settings.CAMPAIGNS)
    assert keys[0] == "cleaning_reactivation"
    first = targets["entries"][0]
    assert first["enabled"] is True and first["weekly_target"] > 0
    groups = targets_mod.niche_groups(targets)
    assert groups[0]["niche"] == "cleaning"
    assert [k for k, _t in groups[0]["campaigns"]] == ["cleaning_reactivation", "cleaning_trigger"]
    for entry in targets_mod.disabled(targets):
        assert len(entry["disabled_reason"]) > 40, entry["campaign_key"]


def test_every_enabled_entry_is_backed_by_an_icp_rubric_that_names_it():
    from services.list_factory import icp

    for entry in targets_mod.enabled(targets_mod.load()):
        rubric = icp.load_rubric(entry["niche"])
        assert entry["campaign_key"] in (rubric.get("campaigns") or {}).values()


def _write_targets(tmp_path, entries):
    path = str(tmp_path / "targets.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"defaults": {"source": "apify", "verify": "millionverifier"}, "campaigns": entries}, fh)
    return path


def _all_entries(**overrides):
    out = []
    for key, meta in settings.CAMPAIGNS.items():
        entry = {"campaign_key": key, "niche": meta.get("niche"), "enabled": False,
                 "disabled_reason": "not part of this test run, which only feeds cleaning"}
        entry.update(overrides.get(key) or {})
        out.append(entry)
    return out


def test_a_targets_file_that_leaves_a_campaign_out_is_refused(tmp_path):
    entries = [e for e in _all_entries() if e["campaign_key"] != "bookkeeping_trigger"]
    with pytest.raises(targets_mod.TargetsError) as exc:
        targets_mod.load(_write_targets(tmp_path, entries))
    assert "bookkeeping_trigger" in str(exc.value)


def test_a_disabled_entry_must_say_why(tmp_path):
    entries = _all_entries(cleaning_trigger={"disabled_reason": ""})
    with pytest.raises(targets_mod.TargetsError):
        targets_mod.load(_write_targets(tmp_path, entries))


def test_an_enabled_entry_needs_a_rubric_that_names_it(tmp_path):
    entries = _all_entries(cleaning_trigger={"enabled": True, "niche": "bookkeeping", "weekly_target": 10})
    with pytest.raises(targets_mod.TargetsError) as exc:
        targets_mod.load(_write_targets(tmp_path, entries))
    assert "does not name it" in str(exc.value)


# ------------------------------------------- one pull, split in run order
def test_the_split_serves_campaigns_in_order_and_never_twice():
    leads = []
    for i in range(10):
        leads.append({"email": "a%d@x%d.com" % (i, i), "personalization": "Hey A, line.",
                      "b_variant_eligible": i < 4, "stage": models.PERSONALIZED})
    out = pipeline_mod.split_for_campaigns(leads, [("cleaning_reactivation", 3), ("cleaning_trigger", 4)])
    react, trig = out["cleaning_reactivation"], out["cleaning_trigger"]
    emails = [l["email"] for l in react + trig]
    assert len(emails) == len(set(emails)) == 10
    assert len(trig) == 4
    assert len(react) == 6, "the leftover goes to the first campaign in run order"
    # the trigger B copy needs the trigger variables; reactivation takes the rest first
    assert all(l["b_variant_eligible"] for l in trig)


def test_all_campaigns_run_feeds_cleaning_reactivation_first_and_reports_the_disabled(captured):
    tmp = captured["tmp"]
    path = _write_targets(tmp, _all_entries(
        cleaning_reactivation={"enabled": True, "weekly_target": 5},
        cleaning_trigger={"enabled": True, "weekly_target": 200},
    ))
    # the entries come out in ids.json order; put cleaning_reactivation first as the real file does
    doc = json.load(open(path))
    doc["campaigns"].sort(key=lambda e: 0 if e["campaign_key"] == "cleaning_reactivation" else 1)
    json.dump(doc, open(path, "w"))
    rc = job.main(["--now", "--all-campaigns", "--targets", path, "--source", "fixture",
                   "--fixture", FIXTURE, "--verify", "replay", "--offline",
                   "--suppression", _supp(tmp), "--fresh", "--max-escalations", "0"])
    final = captured["rows"][-1]
    assert final[2]["all_campaigns"] is True
    assert final[2]["run_order"][:2] == ["cleaning_reactivation", "cleaning_trigger"]
    disabled = [d["campaign_key"] for d in final[2]["disabled"]]
    assert "recruiting_outbound" in disabled and "cleaning_reactivation" not in disabled
    group_rows = [r for r in captured["rows"] if r[2].get("staged_by_campaign")]
    assert group_rows, captured["rows"]
    staged = group_rows[0][2]["staged_by_campaign"]
    assert staged["cleaning_reactivation"] == 5
    assert staged["cleaning_trigger"] > 0
    assert rc in (0, 1)


# ------------------------------------- R10/MKT-3 re-review: resume keeps the split
def _cleaning_only_targets(tmp):
    path = _write_targets(tmp, _all_entries(
        cleaning_reactivation={"enabled": True, "weekly_target": 5},
        cleaning_trigger={"enabled": True, "weekly_target": 200},
    ))
    doc = json.load(open(path))
    doc["campaigns"].sort(key=lambda e: 0 if e["campaign_key"] == "cleaning_reactivation" else 1)
    json.dump(doc, open(path, "w"))
    return path


def _die_once_at_personalize(monkeypatch):
    real = pipeline_mod.stage_personalize
    state = {"died": False}

    def stage(run, cfg, led):
        if not state["died"]:
            state["died"] = True
            raise RuntimeError("the process died here")
        return real(run, cfg, led)

    monkeypatch.setattr(pipeline_mod, "STAGE_FUNCS", [
        (name, stage if name == pipeline_mod.STAGE_PERSONALIZE else func)
        for name, func in pipeline_mod.STAGE_FUNCS])


def test_a_resumed_all_campaigns_run_stages_into_both_campaigns_in_order(captured, monkeypatch):
    """--resume used to rebuild the config from the CLI flags, so an
    --all-campaigns run resumed into cleaning_trigger, target 3,300, no split."""
    tmp = captured["tmp"]
    supp = _supp(tmp)
    _die_once_at_personalize(monkeypatch)
    job.main(["--now", "--all-campaigns", "--targets", _cleaning_only_targets(tmp), "--source", "fixture",
              "--fixture", FIXTURE, "--verify", "replay", "--offline", "--suppression", supp,
              "--fresh", "--max-escalations", "0"])
    run_id = captured["rows"][-1][2]["groups"][0]["run_id"]
    assert captured["rows"][-1][2]["groups"][0]["status"] == "error"

    rc = job.main(["--now", "--resume", run_id, "--fixture", FIXTURE, "--offline",
                   "--suppression", supp, "--max-escalations", "0"])
    row = captured["rows"][-1][2]
    assert row["campaign_targets"] == [("cleaning_reactivation", 5), ("cleaning_trigger", 200)] or \
        [list(p) for p in row["campaign_targets"]] == [["cleaning_reactivation", 5], ["cleaning_trigger", 200]]
    assert row["target"] == 205
    staged = row["staged_by_campaign"]
    assert list(staged) == ["cleaning_reactivation", "cleaning_trigger"]
    assert staged["cleaning_reactivation"] == 5 and staged["cleaning_trigger"] > 0
    assert rc in (0, 1)


def test_a_resume_refuses_a_flag_that_conflicts_with_the_stored_run(captured, monkeypatch):
    tmp = captured["tmp"]
    supp = _supp(tmp)
    _die_once_at_personalize(monkeypatch)
    job.main(["--now", "--all-campaigns", "--targets", _cleaning_only_targets(tmp), "--source", "fixture",
              "--fixture", FIXTURE, "--verify", "replay", "--offline", "--suppression", supp,
              "--fresh", "--max-escalations", "0"])
    run_id = captured["rows"][-1][2]["groups"][0]["run_id"]
    for extra in (["--campaign", "cleaning_trigger"], ["--target", "3300"], ["--niche", "bookkeeping"],
                  ["--source", "apify"], ["--verify", "millionverifier"]):
        rc = job.main(["--now", "--resume", run_id, "--fixture", FIXTURE, "--offline",
                       "--suppression", supp] + extra)
        assert rc == 2, extra
        assert captured["rows"][-1][1] == "refused", extra
        assert "keeps the campaign split" in captured["rows"][-1][2]["error"], extra


def test_the_halted_next_step_is_right_for_both_modes():
    summary = {"status": "halted", "run_id": "cleaning_20260927_090000_abcd", "niche": "cleaning"}
    single = job.next_action(summary, all_campaigns=False)
    both = job.next_action(summary, all_campaigns=True)
    for text in (single, both):
        assert "--resume cleaning_20260927_090000_abcd" in text
        assert "--max-cost-per-contact" in text
    assert "WITHOUT --all-campaigns" in both
    assert "--all-campaigns" not in single


# ----------------------------------------- re-review #8: a dry run never goes paid
def test_a_dry_run_all_campaigns_resolves_to_the_fixture_and_the_replay():
    for group in targets_mod.niche_groups(targets_mod.load()):
        class A(object):
            fixtures = False
            source = None
            verify = None
            dry_run = True
            preflight = False

        assert job.resolve_source_and_verifier(A(), group) == ("fixture", "replay")

        class Named(A):
            source = "apify"
            verify = "millionverifier"

        assert job.resolve_source_and_verifier(Named(), group) == ("apify", "millionverifier")

        class Preflight(A):
            dry_run = False
            preflight = True

        # pricing the real run is the preflight's job; it makes no call
        assert job.resolve_source_and_verifier(Preflight(), group) == ("apify", "millionverifier")


def test_a_dry_run_all_campaigns_end_to_end_builds_free_sources(captured, monkeypatch):
    built = []
    real = job.build_config

    def spy(args, instantly, group=None):
        cfg = real(args, instantly, group)
        built.append((getattr(cfg.source, "name", ""), getattr(cfg.verifier, "name", None)))
        return cfg

    monkeypatch.setattr(job, "build_config", spy)
    job.main(["--dry-run", "--all-campaigns", "--targets", _cleaning_only_targets(captured["tmp"]),
              "--offline", "--suppression", _supp(captured["tmp"]), "--fresh", "--max-escalations", "0"])
    assert built and all(b == ("fixture", "replay") for b in built), built


# -------------------------------------------- re-review #3: the file is tracked
def test_the_targets_file_lives_where_git_tracks_it():
    import shutil
    import subprocess

    if shutil.which("git") is None:
        pytest.skip("git is not available")
    path = targets_mod.DEFAULT_PATH
    assert os.path.exists(path)
    root = os.path.dirname(os.path.dirname(path))
    probe = subprocess.run(["git", "-C", root, "rev-parse", "--is-inside-work-tree"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if probe.returncode != 0:
        pytest.skip("not inside a git work tree")
    out = subprocess.run(["git", "-C", root, "check-ignore", "--no-index", path],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert out.returncode == 1, "git ignores %s: %s" % (path, out.stdout.decode())


# ------------------------------- re-review 2: rehearsals never touch real runs or logs
_LOG_KEYS = ("JOB_LOG_PATH", "SHADOW_LOG_PATH", "LIST_FACTORY_LEDGER_PATH", "JOB_LOG_READ_PATH")


def _real_logs_only(monkeypatch, tmp):
    """Point the process at tmp's REAL log locations. monkeypatch restores the
    variables use_scratch_logs() sets, so nothing leaks into later tests."""
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp))
    for key in _LOG_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(job, "notify", lambda *a, **k: None)


def _open_real_run(tmp):
    """An open Sunday run (Apify + MillionVerifier) that died after sourcing."""
    from services.list_factory import models

    args = job.build_parser().parse_args(["--now", "--all-campaigns", "--offline"])
    args.target, args.niche = job.DEFAULT_TARGET, "cleaning"
    group = targets_mod.niche_groups(targets_mod.load())[0]
    cfg = job.build_config(args, None, group)
    assert (cfg.to_meta()["source"], cfg.to_meta()["verifier"]) == ("apify", "millionverifier")
    run = state_mod_load().RunState.create("cleaning_20260927_090000_real", cfg.to_meta())
    rows = json.load(open(FIXTURE))[:20]
    run.add_leads([models.new_lead(r, source="apify:leads-finder", shard="texas, us") for r in rows])
    run.mark_stage_done(pipeline_mod.STAGE_SOURCE)
    run.checkpoint(force=True)
    return run


def state_mod_load():
    from services.list_factory import state as state_mod

    return state_mod


def _snapshot(directory):
    out = {}
    for name in sorted(os.listdir(directory)):
        with open(os.path.join(directory, name), "rb") as fh:
            out[name] = fh.read()
    return out


def test_a_dry_run_never_adopts_or_touches_an_open_real_run(tmp_path, monkeypatch):
    """The reviewer's probe: --dry-run --all-campaigns picked up an open paid
    run, verified its leads with the replay verifier, wrote a staged CSV into
    the real run folder and closed it as ok."""
    _real_logs_only(monkeypatch, tmp_path)
    run = _open_real_run(tmp_path)
    run_dir = os.path.dirname(run.path)
    before = _snapshot(run_dir)
    job.main(["--dry-run", "--all-campaigns", "--offline", "--suppression", _supp(tmp_path),
              "--max-escalations", "0"])
    assert _snapshot(run_dir) == before, "the dry run changed the real run's files"
    after = state_mod_load().RunState.load(run.run_id)
    assert (after.meta.get("status") or "open") == "open"
    assert not any(lead.get("verify_source") for lead in after.leads)
    # its own state went to scratch, not beside the real run
    assert state_mod_load().list_runs() == [run.run_id]
    assert os.path.isdir(os.path.join(str(tmp_path), "scratch", "list_factory_dryrun", "runs"))


def test_a_dry_run_refuses_to_resume(tmp_path, monkeypatch):
    _real_logs_only(monkeypatch, tmp_path)
    run = _open_real_run(tmp_path)
    before = _snapshot(os.path.dirname(run.path))
    rc = job.main(["--dry-run", "--resume", run.run_id, "--offline", "--suppression", _supp(tmp_path)])
    assert rc == 2
    assert _snapshot(os.path.dirname(run.path)) == before
    assert not os.path.exists(os.path.join(str(tmp_path), "job_log.csv")), "a dry run wrote the real log"


def test_resuming_a_replay_rehearsal_writes_only_to_scratch_logs(tmp_path, monkeypatch):
    """The reviewer's probe: --now --resume <replay rehearsal> without --verify
    replay wrote a Job_Log row and a fake create_lead_batch record into the
    real logs the 48-hour shadow watch reads."""
    _real_logs_only(monkeypatch, tmp_path)
    supp = _supp(tmp_path)
    args = job.build_parser().parse_args(["--now", "--fixtures", "--verify", "replay", "--offline",
                                          "--suppression", supp, "--fresh", "--target", "200",
                                          "--max-escalations", "0"])
    args.niche, args._target_explicit, args._niche_explicit = "cleaning", True, False
    cfg = job.build_config(args, None)
    run = state_mod_load().RunState.create("cleaning_probe_replay", cfg.to_meta())
    led = cfg.new_ledger(run.run_id)

    def hook(name, result):
        if name == pipeline_mod.STAGE_VERIFY:
            led.spend("verify", 500.0, "probe")

    assert pipeline_mod.run_pipeline(run, cfg, led, on_stage=hook)["status"] == "halted"
    assert job.planned_sources(job.build_parser().parse_args(
        ["--now", "--resume", run.run_id])) == [("fixture", "replay")]
    job.main(["--now", "--resume", run.run_id, "--offline", "--suppression", supp,
              "--max-cost-per-contact", "1000"])
    assert not os.path.exists(os.path.join(str(tmp_path), "job_log.csv")), "real Job_Log written"
    assert not os.path.exists(os.path.join(str(tmp_path), "shadow_log.jsonl")), "real shadow log written"
    scratch = os.path.join(str(tmp_path), "scratch", "list_factory_fixtures")
    assert os.path.exists(os.path.join(scratch, "job_log.csv"))


def test_an_all_campaigns_run_never_adopts_an_open_rehearsal(tmp_path, monkeypatch):
    """The Sunday run finding a fixture/replay run open for its niche refuses
    rather than finishing the rehearsal as the week's list."""
    group = {"niche": "cleaning", "source": "apify", "verify": "millionverifier",
             "campaigns": [("cleaning_reactivation", 300), ("cleaning_trigger", 300)]}
    meta = {"niche": "cleaning", "campaign_key": "cleaning_reactivation", "target": 600,
            "campaign_targets": [["cleaning_reactivation", 300], ["cleaning_trigger", 300]],
            "source": "fixture", "verifier": "replay"}
    args = job.build_parser().parse_args(["--now", "--all-campaigns"])
    args.niche, args._target_explicit, args._niche_explicit = "cleaning", False, False
    with pytest.raises(job.UsageError) as exc:
        job.resume_group(args, "cleaning_rehearsal", meta, asked=group)
    assert "source apify" in str(exc.value) and "verifier millionverifier" in str(exc.value)


# -------------------- re-review 3: the targets file and dry-run refusals decide too
def test_a_rehearsal_targets_file_under_now_all_campaigns_writes_only_scratch_logs(tmp_path, monkeypatch):
    """The reviewer's probe: a targets file whose defaults are fixture + replay
    (both valid values) run under --now --all-campaigns wrote a real Job_Log
    row and a fake create_lead_batch record into the real shadow log."""
    _real_logs_only(monkeypatch, tmp_path)
    doc = json.load(open(targets_mod.DEFAULT_PATH))
    doc["defaults"] = {"source": "fixture", "verify": "replay"}
    for entry in doc["campaigns"]:
        if entry["niche"] != "cleaning":
            entry["enabled"] = False
            entry["disabled_reason"] = "rehearsal file: cleaning only"
    path = str(tmp_path / "rehearsal_targets.json")
    json.dump(doc, open(path, "w"))
    args = job.build_parser().parse_args(["--now", "--all-campaigns", "--targets", path])
    assert job.planned_sources(args) == [("fixture", "replay")]
    job.main(["--now", "--all-campaigns", "--targets", path, "--offline", "--suppression", _supp(tmp_path),
              "--fresh", "--max-escalations", "0"])
    assert not os.path.exists(os.path.join(str(tmp_path), "job_log.csv")), "real Job_Log written"
    assert not os.path.exists(os.path.join(str(tmp_path), "shadow_log.jsonl")), "real shadow log written"
    scratch = os.path.join(str(tmp_path), "scratch", "list_factory_fixtures")
    assert os.path.exists(os.path.join(scratch, "job_log.csv"))
    assert os.path.exists(os.path.join(scratch, "shadow_log.jsonl"))


def test_the_real_targets_file_is_not_a_rehearsal():
    args = job.build_parser().parse_args(["--now", "--all-campaigns"])
    pairs = job.planned_sources(args)
    assert pairs and all(pair == ("apify", "millionverifier") for pair in pairs), pairs


def test_a_dry_run_refusal_is_logged_to_scratch_not_the_real_job_log(tmp_path, monkeypatch):
    """--dry-run --all-campaigns --target 5 was refused before the scratch
    switch, so its refused row landed in the real Job_Log."""
    _real_logs_only(monkeypatch, tmp_path)
    rc = job.main(["--dry-run", "--all-campaigns", "--target", "5"])
    assert rc == 2
    assert not os.path.exists(os.path.join(str(tmp_path), "job_log.csv")), "real Job_Log written"
    scratch_log = os.path.join(str(tmp_path), "scratch", "list_factory_dryrun", "job_log.csv")
    assert os.path.exists(scratch_log)
    assert "refused" in open(scratch_log).read()


# ------------------------------- re-review 4: a mixed paid/rehearsal file is refused
def _targets_with(tmp_path, cleaning_pair):
    doc = json.load(open(targets_mod.DEFAULT_PATH))
    for entry in doc["campaigns"]:
        if entry["niche"] == "cleaning":
            entry["source"], entry["verify"] = cleaning_pair
    path = str(tmp_path / ("targets_%s_%s.json" % cleaning_pair))
    json.dump(doc, open(path, "w"))
    return path


@pytest.mark.parametrize("cleaning_pair", [("fixture", "replay"), ("apify", "replay")])
def test_a_mixed_targets_file_is_refused_into_the_real_log_before_any_pull(tmp_path, monkeypatch,
                                                                          cleaning_pair):
    """The reviewer's probe: cleaning fixture + replay beside a paid bookkeeping
    pull used to run both and put the paid pull's real spend in scratch."""
    _real_logs_only(monkeypatch, tmp_path)
    pushes, pulls, fetched = [], [], []
    monkeypatch.setattr(job, "notify", lambda title, body="", **kw: pushes.append((title, kw)))
    monkeypatch.setattr(job, "run_factory", lambda *a, **k: pulls.append(k.get("group")) or {})
    from services.list_factory import sources as sources_mod

    for cls in (sources_mod.FixtureSource, sources_mod.ApifySource):
        monkeypatch.setattr(cls, "fetch", lambda self, *a, **k: fetched.append(self.name) or [])
    path = _targets_with(tmp_path, cleaning_pair)
    rc = job.main(["--now", "--all-campaigns", "--targets", path, "--offline",
                   "--suppression", _supp(tmp_path), "--fresh", "--max-escalations", "0"])
    assert rc == 2
    assert pulls == [] and fetched == [], "a pull ran"
    real = os.path.join(str(tmp_path), "job_log.csv")
    assert os.path.exists(real), "the refusal did not reach the real Job_Log"
    text = open(real).read()
    assert "refused" in text and "mixes paid" in text
    assert not os.path.exists(os.path.join(str(tmp_path), "scratch", "list_factory_fixtures"))
    assert pushes and pushes[-1][1]["priority"] == "high"


def test_all_rehearsal_and_all_paid_files_are_not_refused_as_mixed(tmp_path):
    rehearsal = job.build_parser().parse_args(["--now", "--all-campaigns"])
    doc = json.load(open(targets_mod.DEFAULT_PATH))
    doc["defaults"] = {"source": "fixture", "verify": "replay"}
    for entry in doc["campaigns"]:
        entry.pop("source", None)
        entry.pop("verify", None)
    path = str(tmp_path / "all_rehearsal.json")
    json.dump(doc, open(path, "w"))
    rehearsal.targets = path
    job._refuse_mixed_pulls(job.planned_sources(rehearsal), rehearsal)          # no raise
    paid = job.build_parser().parse_args(["--now", "--all-campaigns"])
    job._refuse_mixed_pulls(job.planned_sources(paid), paid)                    # no raise
    assert all(pair == ("apify", "millionverifier") for pair in job.planned_sources(paid))


# ------------------------- D1 round 3, defect 4: the Sunday run with paid calls off
def _blocked_pull(args, now=None, group=None, instantly=None):
    return {"niche": group["niche"], "campaign_key": group["campaigns"][0][0],
            "campaign_targets": group["campaigns"], "target": group["target"], "status": "blocked",
            "error": "apify blocked: 500 units, would have cost $2.5000.", "staged": 0, "run_id": "r-1"}


def test_the_sunday_run_with_paid_calls_off_is_a_designed_outcome(captured, monkeypatch, capsys):
    """Paid calls are off until Lorenzo approves the figure, so every pull stops
    at its first paid call. That ends with exit 0, its own status, one
    normal-priority note and the marker the laptop runner records."""
    monkeypatch.setenv("ALLOW_PAID_CALLS", "0")
    monkeypatch.setattr(job, "run_factory", _blocked_pull)
    monkeypatch.setattr(job, "_report_run", lambda args, summary, push=True: 0)
    monkeypatch.setattr(job, "_instantly", lambda offline: None)
    rc = job.main(["--now", "--all-campaigns", "--refresh-suppression"])
    assert rc == 0
    final = captured["rows"][-1]
    assert final[1] == job.PAID_CALLS_OFF == "paid_calls_off"
    assert len(captured["pushes"]) == 1
    assert captured["pushes"][0][2].get("priority") == "default"
    assert "ADVERO_OUTCOME=paid_calls_off" in capsys.readouterr().out.splitlines()


def test_a_blocked_run_with_paid_calls_ON_still_fails_loudly(captured, monkeypatch):
    monkeypatch.setenv("ALLOW_PAID_CALLS", "1")
    monkeypatch.setattr(job, "run_factory", _blocked_pull)
    monkeypatch.setattr(job, "_report_run", lambda args, summary, push=True: 0)
    monkeypatch.setattr(job, "_instantly", lambda offline: None)
    rc = job.main(["--now", "--all-campaigns", "--refresh-suppression"])
    assert rc == 1
    assert captured["rows"][-1][1] == "partial"
    assert captured["pushes"][-1][2].get("priority") == "high"
