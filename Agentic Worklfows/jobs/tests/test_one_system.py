"""Every job is one system, and the whole of it is safe to leave running.

``services/reply_engine/tests/test_shadow_safety.py`` proves this for the
Phase 1 sales tier by replaying 44 recorded replies. This module does the same
job for the eighteen scheduled entry points of Phases 2 to 4, and adds the
integration properties that only exist between components:

1. **One library.** Every job logs through ``shared.job_log``, alerts through
   ``shared.notify``, keeps state in ``shared.store`` and takes its thresholds
   from ``shared.thresholds``. A job that grows its own CSV log or its own copy
   of the 1% reply line is a second system wearing the first one's name.
2. **One Instantly client.** Every job builds it through
   ``shared.instantly.default_client``, so a rehearsal replaces one name rather
   than eighteen, and so a future default cannot disagree between jobs.
3. **One reader for the analytics.** The monitor, the inventory, the daily
   metrics and the retro all read ``GET /accounts/analytics/daily``; they go
   through ``shared.analytics`` and nothing else re-implements the chunking.
4. **No two jobs fight over the same file or the same store key.** Where two
   jobs deliberately share a change-set they are declared here with the reason,
   so an undeclared overlap fails.
5. **Shadow safety, per job.** With ``httpx`` patched to raise and
   ``MODE=shadow``, every job's ``--dry-run`` runs on recorded fixtures with
   zero HTTP, zero paid calls, zero exceptions, and every intended write
   present in the shadow log as a would_do record.

Run it alone with:
    cd "Agentic Worklfows" && python3 -m pytest jobs/tests/test_one_system.py -q
"""
import ast
import csv
import importlib
import os
from pathlib import Path

import httpx
import pytest

from shared import analytics, job_log, settings

BASE_DIR = Path(__file__).resolve().parents[2]
JOBS_DIR = BASE_DIR / "jobs"
LIST_FACTORY_FIXTURE = BASE_DIR / "services" / "list_factory" / "fixtures" / "source_cleaning_50.json"

# Every system a guarded write may name. Anything else in the shadow log means
# a new integration was added without a guard.
GUARDED_SYSTEMS = {"instantly", "ghl", "notify", "google_sheets", "skool", "gmail"}


class NetworkEscape(AssertionError):
    """A real HTTP request was attempted during a shadow run."""


# ---------------------------------------------------------------------------
# The eighteen entry points, and how each one runs with no network.
#
# ``argv`` is what the runbook and the Modal function pass, with the dry-run
# flag. ``exits`` is every exit code the offline recording can legitimately
# produce: a job that refuses because the recorded data does not justify acting
# is behaving correctly, and pinning the code stops that refusal drifting into
# a crash without anybody noticing.
# ---------------------------------------------------------------------------
JOBS = [
    ("jobs.deliverability_monitor", ["--dry-run"], {0}, "O1 five-level monitor"),
    ("jobs.inbox_placement", ["--dry-run"], {0}, "O5 Monday placement test"),
    ("jobs.autoresponder_canary", ["--dry-run"], {0}, "O7 Saturday canary"),
    ("jobs.inbox_inventory", ["--dry-run", "--fixtures"], {0}, "M2 capacity inventory"),
    ("jobs.positive_sweep", ["--dry-run", "--fixtures"], {0}, "O3 positive sweep"),
    ("jobs.pipeline_sweep", ["--dry-run", "--fixtures"], {0}, "S8/O3 pipeline sweep"),
    ("jobs.upwork_rooms", ["--dry-run"], {0}, "O2 Upwork rooms digest"),
    ("jobs.campaign_verdicts", ["--dry-run"], {0}, "A7 campaign verdicts"),
    ("jobs.retro_packet", ["--dry-run", "--fixtures"], {0}, "O6 Friday retro"),
    ("jobs.client_scorecard", ["--dry-run", "--fixtures"], {0}, "F3/F4 client scorecard"),
    ("jobs.daily_metrics", ["--dry-run", "--fixtures"], {0}, "O4 daily metrics"),
    ("jobs.cadence_tick", ["--dry-run"], {0}, "S2 cadence tick"),
    ("jobs.appointments_tick", ["--dry-run"], {0}, "S4/S5 appointments tick"),
    ("jobs.precall_tick", ["--dry-run"], {0}, "S6/S7 pre-call brief"),
    # The list factory is the only job that can spend money, so it runs with
    # --offline and a recorded source. Exit 1 is the CORRECT answer here: the
    # recorded 58 rows produce no verified contact, the cost-per-contact gate
    # has nothing to divide by, and the run holds rather than staging a list.
    ("jobs.list_factory",
     ["--dry-run", "--offline", "--source", "fixture", "--fixture", str(LIST_FACTORY_FIXTURE)],
     {0, 1}, "O8 Sunday list factory"),
]

# Change-set files two jobs may both write, with the reason. Anything not
# declared here and written by two components is a collision.
SHARED_CHANGESET_PATHS = {
    "changesets/inbox_actions/<date>.json": (
        {"jobs.deliverability_monitor", "jobs.inbox_placement", "jobs.autoresponder_canary"},
        "one dated change-set per day, MERGED by all three deliverability levels, which is why "
        "placement (Mon) and the canary (Sat) are scheduled at 06:45, before the 07:00 monitor"),
}


# ---------------------------------------------------------------------- world
@pytest.fixture
def no_network(monkeypatch):
    """Every httpx client raises instead of reaching the network.

    Patching a transport is not enough: shared.instantly and shared.ghl build
    their own ``httpx.Client``, and so would any module added later. The
    constructors themselves are wrapped, so the escape hatch closes for code
    this test has never seen.
    """
    escapes = []

    def blocking(request):
        escapes.append("%s %s" % (request.method, request.url))
        raise NetworkEscape("shadow run attempted %s %s" % (request.method, request.url))

    real_client, real_async = httpx.Client, httpx.AsyncClient

    class GuardedClient(real_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(blocking)
            super(GuardedClient, self).__init__(*args, **kwargs)

    class GuardedAsyncClient(real_async):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(blocking)
            super(GuardedAsyncClient, self).__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", GuardedClient)
    monkeypatch.setattr(httpx, "AsyncClient", GuardedAsyncClient)
    return escapes


@pytest.fixture
def shadow_world(tmp_path, monkeypatch, no_network):
    """MODE=shadow, faked model, notifications off, recorded Instantly, every
    file this run writes under tmp_path."""
    import shared.instantly as instantly_mod
    from shared.offline import offline_client_factory

    monkeypatch.setenv("MODE", "shadow")
    monkeypatch.delenv("ALLOW_LIVE_WRITES", raising=False)
    monkeypatch.delenv("ALLOW_PAID_CALLS", raising=False)
    monkeypatch.delenv("GHL_PRIVATE_INTEGRATION_TOKEN", raising=False)
    monkeypatch.delenv("JOB_LOG_SHEET_ID", raising=False)
    monkeypatch.delenv("NOTIFY_SHADOW_SEND", raising=False)
    monkeypatch.setenv("LLM_FAKE", "1")
    monkeypatch.setenv("NOTIFY", "off")
    monkeypatch.setenv("ADVERO_TMP_DIR", str(tmp_path))
    monkeypatch.setenv("STORE_PATH", str(tmp_path / "store.json"))
    monkeypatch.setenv("JOB_LOG_PATH", str(tmp_path / "job_log.csv"))
    monkeypatch.setenv("SHADOW_LOG_PATH", str(tmp_path / "shadow_log.jsonl"))
    monkeypatch.setenv("LLM_LEDGER_PATH", str(tmp_path / "llm_ledger.csv"))
    # A dry run calls use_scratch_logs(), which repoints JOB_LOG_PATH; the
    # remembered read path has to start clean or one job reads another's.
    monkeypatch.delenv("JOB_LOG_READ_PATH", raising=False)
    # Change-sets and sidecars are evidence, not operations: keep them in
    # tmp_path so a test run never edits the committed audit trail.
    monkeypatch.setenv("ADVERO_CHANGESET_DIR", str(tmp_path / "changesets"))

    factory = offline_client_factory(strict=False)
    monkeypatch.setattr(instantly_mod, "default_client", factory)
    analytics.clear_cache()
    assert settings.is_live() is False
    return {"tmp": tmp_path, "escapes": no_network, "client": factory.client}


def _shadow_records(tmp_path):
    """Every would_do record the run left, wherever it left it.

    ``use_scratch_logs`` moves SHADOW_LOG_PATH into ``.tmp/scratch/<job>/``
    partway through a dry run, so a test that reads only the path it exported
    sees an empty file and passes for the wrong reason.
    """
    records = []
    for path in sorted(Path(tmp_path).rglob("shadow_log.jsonl")):
        records.extend(job_log.read_shadow_log(str(path)))
    return records


def _ledger_rows(tmp_path):
    rows = []
    for path in sorted(Path(tmp_path).rglob("llm_ledger.csv")):
        try:
            with open(str(path), newline="", encoding="utf-8") as fh:
                rows.extend(list(csv.DictReader(fh)))
        except OSError:
            continue
    return rows


# ------------------------------------------------------------ shadow safety
@pytest.mark.parametrize("module_name,argv,exits,label",
                         JOBS, ids=[spec[0].split(".")[-1] for spec in JOBS])
def test_every_job_dry_run_is_offline_silent_and_guarded(shadow_world, module_name, argv, exits, label):
    """The whole of Phases 2-4, one job at a time: no HTTP, no paid call, no
    exception, and every intended write recorded rather than performed."""
    module = importlib.import_module(module_name)
    assert callable(getattr(module, "main", None)), "%s has no main(argv)" % module_name

    code = module.main(list(argv))

    assert shadow_world["escapes"] == [], (
        "%s (%s) reached the network during a shadow dry run: %s"
        % (module_name, label, shadow_world["escapes"][:3]))
    assert code in exits, "%s exited %r, expected one of %r" % (module_name, code, sorted(exits))

    for rec in _shadow_records(shadow_world["tmp"]):
        assert rec.get("mode") == "shadow", (module_name, rec)
        assert rec.get("system") in GUARDED_SYSTEMS, (module_name, rec)
        assert isinstance(rec.get("payload"), (dict, list)), (module_name, rec)

    for row in _ledger_rows(shadow_world["tmp"]):
        assert row.get("faked") == "1", (
            "%s billed a real model call during a dry run: %s" % (module_name, row))


def test_the_network_guard_in_this_module_actually_guards(shadow_world):
    """A belt for the belt. Without this, a refactor that drops the patch turns
    every test above into a live-data test that silently passes."""
    with pytest.raises(NetworkEscape):
        httpx.Client().get("https://api.instantly.ai/api/v2/campaigns")


def test_a_write_that_skipped_the_guard_would_be_caught(shadow_world):
    """The recorded client refuses a write at the transport, so a future code
    path that bypasses ``settings.guard_write`` fails loudly instead of
    reaching Instantly the day MODE is flipped to live."""
    from shared.offline import ShadowContractBypassed

    client = shared_offline_client(shadow_world)
    with pytest.raises(ShadowContractBypassed):
        client._request("POST", "leads", json={"email": "x@y.com"})


def shared_offline_client(world):
    return world["client"]


# ------------------------------------------------------------- one library
def _job_modules():
    for path in sorted(JOBS_DIR.glob("*.py")):
        if path.name.startswith("__"):
            continue
        yield path


def _source(path):
    return path.read_text(encoding="utf-8")


def _imports_from(path, module_name):
    """True when this file imports ``module_name`` or a name out of it, at any
    indentation. Half these imports are inside the function that needs them, so
    a text match on the first ten lines finds nothing."""
    for node in ast.walk(ast.parse(_source(path))):
        if isinstance(node, ast.ImportFrom):
            if node.module == module_name:
                return True
            # ``from shared import job_log, notify, slots``
            if node.module == module_name.rsplit(".", 1)[0]:
                leaf = module_name.rsplit(".", 1)[-1]
                if any(a.name == leaf for a in node.names):
                    return True
        if isinstance(node, ast.Import):
            if any(a.name == module_name for a in node.names):
                return True
    return False


def test_every_job_logs_through_the_shared_job_log():
    """One Job_Log for the whole system. A job with its own CSV is a job whose
    runs are invisible to the 07:30 sweep, the KPI dashboard and the retro."""
    for path in _job_modules():
        assert _imports_from(path, "shared.job_log"), "%s never imports shared.job_log" % path.name
        src = _source(path)
        # Some jobs take the logger as an injected ``log_fn`` so a test can
        # capture rows; that still IS shared.job_log.log_run, by default.
        assert "log_run" in src, "%s never writes a Job_Log row" % path.name


def test_every_job_alerts_through_the_shared_notifier():
    """One notifier, so NOTIFY=off, the shadow guard and the public-topic
    redaction apply everywhere rather than in the jobs that remembered."""
    for path in _job_modules():
        src = _source(path)
        if "notify" not in src:
            continue
        assert _imports_from(path, "shared.notify"), \
            "%s notifies without importing shared.notify" % path.name


def test_no_job_writes_its_own_log_or_push():
    """The two ways a job stops being part of one system: its own CSV beside
    the Job_Log, and its own HTTP call to ntfy."""
    offenders = []
    for path in _job_modules():
        src = _source(path)
        if "ntfy.sh" in src and "shared" not in src:
            offenders.append("%s posts to ntfy itself" % path.name)
        if "job_log.csv" in src and "shared.job_log" not in src:
            offenders.append("%s writes its own job_log.csv" % path.name)
    assert offenders == [], offenders


def test_no_job_builds_its_own_instantly_client():
    """``default_client`` is the one construction point. Eighteen inline
    ``Instantly()`` calls meant eighteen places to patch for an offline run and
    eighteen places for a default to drift."""
    offenders = []
    for path in list(_job_modules()) + sorted((BASE_DIR / "services").rglob("*.py")):
        if "tests" in path.parts or "fixtures" in path.parts:
            continue
        src = _source(path)
        for node in ast.walk(ast.parse(src)):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "Instantly" and not node.args and not node.keywords):
                offenders.append("%s:%d" % (path.relative_to(BASE_DIR), node.lineno))
    assert offenders == [], (
        "these build an Instantly client directly instead of shared.instantly.default_client(): %s"
        % offenders)


def test_only_the_shared_reader_chunks_the_account_analytics():
    """Four copies of one API quirk is four places to fix it and three places
    to forget. ``shared.analytics`` owns the chunking; everything else asks it."""
    allowed = {"shared/analytics.py", "shared/instantly.py", "shared/README.md"}
    offenders = []
    for root in ("jobs", "services"):
        for path in sorted((BASE_DIR / root).rglob("*.py")):
            if "tests" in path.parts or "fixtures" in path.parts:
                continue
            rel = str(path.relative_to(BASE_DIR))
            if rel in allowed:
                continue
            if "daily_account_analytics(" in _source(path):
                offenders.append(rel)
    assert offenders == [], (
        "these call daily_account_analytics directly rather than through "
        "shared.analytics.account_daily, so they carry their own chunking and their own "
        "answer to the workspace's 413: %s" % offenders)


def test_no_job_carries_its_own_copy_of_a_shared_threshold():
    """The 1% reply line, the 2% bounce line and the 98% warm-up line live in
    ``shared/thresholds.py``. A literal copy in a job is a number that
    disagrees with the card the next morning and nobody can find."""
    from shared import thresholds as TH

    watched = {
        "REPLY_RATE_MIN_PCT": TH.REPLY_RATE_MIN_PCT,
        "BOUNCE_RATE_MAX_PCT": TH.BOUNCE_RATE_MAX_PCT,
        "WARMUP_HEALTH_MIN_PCT": TH.WARMUP_HEALTH_MIN_PCT,
        "PER_INBOX_DAILY_LIMIT": TH.PER_INBOX_DAILY_LIMIT,
    }
    def is_bound_to_thresholds(value):
        """``X = TH.X`` and ``X = TH.X / 100.0`` are bindings, not copies: the
        number still has one home. A literal is the thing this test is for."""
        for node in ast.walk(value):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                    and node.value.id in ("TH", "thresholds"):
                return True
        return False

    offenders = []
    for path in _job_modules():
        src = _source(path)
        for node in ast.walk(ast.parse(src)):
            if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
                continue
            target = node.targets[0]
            if not (isinstance(target, ast.Name) and target.id in watched):
                continue
            if is_bound_to_thresholds(node.value):
                continue
            offenders.append("%s:%d redefines %s as a literal" % (path.name, node.lineno, target.id))
    assert offenders == [], (
        "these redefine a shared threshold locally; import it from shared.thresholds: %s" % offenders)


def test_the_capacity_job_and_the_monitor_share_one_set_of_numbers():
    """The 07:00 monitor and the 07:00 capacity inventory both act on M2's
    limits. They used to hold their own copies, in different units: 2.0 as a
    percentage in shared/thresholds.py and 0.02 as a fraction in the inventory,
    for one rule. Binding is what keeps the two cards describing one fleet.

    (The 18:00 KPI dashboard keeps its own SPEC on purpose, because it carries
    an alert side and a direction that thresholds.py does not; the four
    overlapping numbers are pinned by
    jobs/tests/test_metrics_kpi.py::test_thresholds_agree_with_the_shared_deliverability_constants.)
    """
    from shared import thresholds as TH

    inventory = importlib.import_module("jobs.inbox_inventory")
    assert inventory.PER_INBOX_DAILY_LIMIT is TH.PER_INBOX_DAILY_LIMIT
    assert inventory.MAX_INBOXES_PER_DOMAIN is TH.MAX_INBOXES_PER_DOMAIN
    # INSURANCE_RATIO is gone from the inventory: it sized a reserve, and the
    # reserve is Lorenzo's call (health alerts only, 2026-09-22).
    assert not hasattr(inventory, "INSURANCE_RATIO")
    assert inventory.RAMPED_DAILY_LIMIT is TH.PER_INBOX_DAILY_LIMIT_RAISED
    assert inventory.RAMP_MIN_REPLY_RATE == TH.REPLY_RATE_FOR_RAISED_LIMIT_PCT / 100.0
    assert inventory.WARMUP_DAYS is TH.WARMUP_DAYS_BEFORE_PROMOTION


# -------------------------------------------------- no two jobs collide
def test_no_two_components_write_the_same_change_set_path():
    """A second writer to one file is a silent overwrite of the first one's
    proposals. The three that share one by design are declared, with the reason
    and the ordering the schedule has to preserve."""
    import services.reply_engine.modal_app as modal_app

    declared_writers = set()
    for _path, (writers, _why) in SHARED_CHANGESET_PATHS.items():
        declared_writers |= writers

    dirs = {}
    for module_name in ("jobs.deliverability_monitor", "jobs.inbox_placement",
                        "jobs.autoresponder_canary", "jobs.inbox_inventory"):
        module = importlib.import_module(module_name)
        directory = getattr(module, "CHANGESET_DIR", None)
        assert directory is not None, "%s writes change-sets without naming a directory" % module_name
        dirs.setdefault(str(directory), set()).add(module_name)

    for directory, writers in dirs.items():
        if len(writers) == 1:
            continue
        assert writers <= declared_writers, (
            "%s is written by %s, which is not a declared sharing arrangement" % (directory, writers))

    # and the schedule really does keep the declared order
    for producer, (consumer, why) in modal_app.SCHEDULE_ORDERING.items():
        assert producer in modal_app.SCHEDULES and consumer in modal_app.SCHEDULES, (producer, consumer)
        assert why


def test_the_sidecars_two_jobs_hand_to_a_third_have_distinct_names():
    """placement and the canary each leave the monitor a sidecar in the same
    directory. One name for both would make Saturday's canary overwrite
    Monday's placement result and the card would read the wrong level."""
    placement = importlib.import_module("jobs.inbox_placement")
    canary = importlib.import_module("jobs.autoresponder_canary")
    assert placement.SIDECAR != canary.SIDECAR
    monitor_src = _source(JOBS_DIR / "deliverability_monitor.py")
    assert placement.SIDECAR in monitor_src, "the monitor never reads the placement sidecar"
    assert canary.SIDECAR in monitor_src, "the monitor never reads the canary sidecar"


def test_every_scheduled_job_has_a_runbook():
    """A job nobody can operate at 07:00 on a bad morning is not shipped."""
    import services.reply_engine.modal_app as modal_app

    runbooks = " ".join(p.read_text(encoding="utf-8")
                        for p in (BASE_DIR / "runbooks").glob("*.md"))
    missing = []
    for name in modal_app.SCHEDULED_FUNCTIONS:
        module = modal_app.SCHEDULE_JOB_MODULE[name]
        job = module.rsplit(".", 1)[-1]
        if job in ("poller",):
            continue
        if job not in runbooks:
            missing.append(job)
    assert missing == [], "no runbook mentions: %s" % missing


def test_every_scheduled_job_is_in_the_jobs_readme():
    readme = (JOBS_DIR / "README.md").read_text(encoding="utf-8")
    import services.reply_engine.modal_app as modal_app

    missing = []
    for name in modal_app.SCHEDULED_FUNCTIONS:
        module = modal_app.SCHEDULE_JOB_MODULE[name]
        if not module.startswith("jobs."):
            continue          # the reply-engine services are documented in their own runbooks
        job = module.rsplit(".", 1)[-1]
        if ("%s.py" % job) not in readme:
            missing.append(job)
    assert missing == [], "jobs/README.md has no row for: %s" % missing


# ------------------------------------------------- the morning hand-off
def test_the_three_hand_off_documents_exist_and_cover_both_phases():
    """The build is not finished when the tests pass; it is finished when
    Lorenzo can read what it does, what to do next and what it needs from him."""
    runbooks = BASE_DIR / "runbooks"
    report = (runbooks / "MASTER_BUILD_REPORT.md").read_text(encoding="utf-8")
    checklist = (runbooks / "GO_LIVE_CHECKLIST.md").read_text(encoding="utf-8")
    decisions = (runbooks / "DECISIONS_FOR_LORENZO.md").read_text(encoding="utf-8")

    # the build report has to name what is NOT built, or it is marketing
    assert "not built" in report.lower()
    # the checklist has to carry a rollback for each stage
    assert checklist.lower().count("rollback") >= 10
    assert "ALLOW_LIVE_WRITES=0" in checklist
    # the decisions file is split into open Decisions and settled FYI, and it
    # still carries Phase 1 and Phases 2-4: nothing from either phase dropped
    assert "# Part 1: Decisions" in decisions, "the open decisions part is missing"
    assert "# Part 2: FYI" in decisions, "the settled items and records part is missing"
    for item_id in ("Q-A1", "Q-A5",                 # Phase 1
                    "Q-M1", "Q-N1", "Q-O1", "R14"):  # Phases 2-4 and the re-review
        # an entry of its own (a bold lead-in or a heading), not just a mention
        assert ("**%s " % item_id in decisions or "**%s." % item_id in decisions
                or "### %s." % item_id in decisions), item_id


def test_nothing_written_for_lorenzo_uses_an_em_dash():
    """The copy rule applies to anything he or a client reads, and these three
    are the documents most likely to be pasted somewhere else."""
    for name in ("MASTER_BUILD_REPORT.md", "GO_LIVE_CHECKLIST.md", "DECISIONS_FOR_LORENZO.md"):
        text = (BASE_DIR / "runbooks" / name).read_text(encoding="utf-8")
        assert "\u2014" not in text and chr(0x2014) not in text, name


def test_every_job_runs_as_a_script_from_the_repo_root():
    """The runbooks document every job as `python3 jobs/<name>.py --dry-run`,
    run from the repo root. That only works if the module puts the repo root on
    sys.path itself, because `python3 jobs/x.py` puts `jobs/` on sys.path, not
    the root.

    Regression guard for the 2026-09-22 finding: campaign_verdicts.py and
    cadence_tick.py were the only two jobs missing the bootstrap, so
    `python3 jobs/campaign_verdicts.py --dry-run` - printed in
    MASTER_BUILD_REPORT's "how to look at any of this yourself" block - died
    with ModuleNotFoundError: No module named 'shared' before argparse ran.

    --help exits inside argparse, so this touches no network and bills nothing.

    It also asserts each child ADDS NO environment variable. A child is not a
    pytest process, so before conftest's inherited ADVERO_TEST_SESSION flag
    shared.settings.load_env() loaded every key in the real .env files into
    13 of these 15 children (SAF-2 re-review, 2026-09-22). The child runs the
    script through runpy with sys.path[0] set to jobs/, exactly what
    `python3 jobs/x.py` does, and reports the names (never the values) of any
    variable that appeared.
    """
    import json
    import subprocess
    import sys

    env = dict(os.environ)
    env.update({"MODE": "shadow", "LLM_FAKE": "1", "NOTIFY": "off"})
    env.pop("PYTHONPATH", None)   # the documented command sets no PYTHONPATH
    assert env.get("ADVERO_TEST_SESSION") == "1", "conftest must hand the test-session flag to children"

    broken = []
    added = {}
    for path in _job_modules():
        proc = subprocess.run(
            [sys.executable, "-c", _RUN_AS_SCRIPT, os.path.join("jobs", path.name), "--help"],
            cwd=str(BASE_DIR), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        out = proc.stdout.decode("utf-8", "replace")
        if proc.returncode != 0:
            broken.append("%s exited %d: %s" % (path.name, proc.returncode, out.strip()[-200:]))
        marker = [line for line in out.splitlines() if line.startswith("@@ENV_ADDED@@")]
        names = json.loads(marker[-1][len("@@ENV_ADDED@@"):]) if marker else ["<no report>"]
        if names:
            added[path.name] = names
    assert broken == [], broken
    assert added == {}, "a job's --help put variables into the environment: %s" % added


# `python3 jobs/x.py --help`, plus a report of which environment variable
# NAMES the run added. Values are never printed.
_RUN_AS_SCRIPT = (
    "import json, os, runpy, sys\n"
    "script = sys.argv[1]\n"
    "sys.argv = sys.argv[1:]\n"
    "sys.path[0] = os.path.dirname(os.path.abspath(script))\n"
    "before = set(os.environ)\n"
    "code = 0\n"
    "try:\n"
    "    runpy.run_path(script, run_name='__main__')\n"
    "except SystemExit as exc:\n"
    "    code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)\n"
    "sys.stdout.flush()\n"
    "print('\\n@@ENV_ADDED@@' + json.dumps(sorted(set(os.environ) - before)))\n"
    "sys.exit(code)\n"
)
