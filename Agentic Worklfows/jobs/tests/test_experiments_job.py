"""jobs/campaign_verdicts.py end to end and the experiment log (brief A7).

Everything runs on the recorded fixtures through ``FakeInstantly``, which has
no write methods at all: a regression that reached for one would fail here
rather than shadow-log quietly.
"""
import csv
import datetime
import json
import os

import pytest

from jobs import campaign_verdicts as JOB
from services.experiments import experiment_log as EL
from services.experiments import analytics, verdicts as V
from services.experiments.fakes import FakeInstantly

AS_OF = datetime.date(2026, 9, 22)


@pytest.fixture
def client():
    return FakeInstantly()


@pytest.fixture
def experiments_path(tmp_path):
    return str(tmp_path / "experiments.json")


def _job_log_rows():
    from shared.job_log import job_log_path

    path = job_log_path()
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# --------------------------------------------------------------- the job
def test_dry_run_reports_but_writes_no_experiments_file(client, experiments_path, tmp_env, capsys):
    rc = JOB.main(["--dry-run", "--experiments", experiments_path], client=client, as_of=AS_OF)
    assert rc == 0
    assert not os.path.exists(experiments_path)
    out = capsys.readouterr().out
    assert "# Campaign verdicts and experiments" in out
    assert "config/experiments.json was NOT written" in out
    assert "cleaning_reactivation" in out


def test_a_real_run_writes_the_experiments_file_and_one_job_log_row(client, experiments_path, tmp_env):
    rc = JOB.main(["--experiments", experiments_path], client=client, as_of=AS_OF)
    assert rc == 0
    doc = json.load(open(experiments_path, encoding="utf-8"))
    assert [e["id"] for e in doc["experiments"]] == ["EXP-001a-reactivation-rewrite", "EXP-001b-trigger-rewrite", "EXP-002-icebreaker-style"]
    rows = [r for r in _job_log_rows() if r["job"] == "campaign_verdicts"]
    assert len(rows) == 1
    assert rows[0]["status"] == "ok"
    assert rows[0]["mode"] == "shadow"
    details = json.loads(rows[0]["details"])
    assert details["verdicts"]["cleaning_trigger"]["positives"] == 2
    assert details["verdicts"]["cleaning_trigger"]["recommendation"] == "keep_running"


def test_the_job_never_calls_a_write_method(client, experiments_path, tmp_env):
    JOB.main(["--experiments", experiments_path], client=client, as_of=AS_OF)
    for call in client.calls:
        assert call[0] in ("campaign_analytics", "GET", "iterate", "get_campaign", "daily"), call
    # iterate only ever walks the replied-lead list
    for call in [c for c in client.calls if c[0] == "iterate"]:
        assert call[1] == "leads/list"
        assert call[2]["filter"] == "FILTER_VAL_REPLIED"


def test_failure_logs_and_alerts_and_returns_one(experiments_path, tmp_env, monkeypatch):
    from shared import notify as notify_mod

    notify_mod.reset_test_log() if hasattr(notify_mod, "reset_test_log") else None
    del notify_mod.sent_in_test[:]

    class Boom(FakeInstantly):
        def campaign_analytics(self, ids=None, start_date=None, end_date=None):
            raise RuntimeError("instantly is down")

    rc = JOB.main(["--experiments", experiments_path], client=Boom(), as_of=AS_OF)
    assert rc == 1
    rows = [r for r in _job_log_rows() if r["job"] == "campaign_verdicts" and r["status"] == "failed"]
    assert rows and "instantly is down" in rows[0]["details"]
    assert notify_mod.sent_in_test, "a failed weekly job has to reach Lorenzo"
    assert "verdicts failed" in notify_mod.sent_in_test[-1]["title"].lower()


def test_an_empty_overview_is_a_failed_read_not_a_quiet_week(experiments_path, tmp_env):
    """MKT-9: an empty analytics overview used to log "ok", exit 0, push
    nothing and rewrite config/experiments.json from zeros."""
    from shared import notify as notify_mod

    del notify_mod.sent_in_test[:]
    rc = JOB.main(["--experiments", experiments_path], client=FakeInstantly(overview=[]), as_of=AS_OF)
    assert rc == 1
    assert not os.path.exists(experiments_path), "a sample rebuilt from a failed read reset the tests"
    rows = [r for r in _job_log_rows() if r["job"] == "campaign_verdicts"]
    assert rows and rows[-1]["status"] == "empty"
    assert "no row for any" in json.loads(rows[-1]["details"])["incomplete"]
    assert notify_mod.sent_in_test, "an empty pull has to reach Lorenzo"
    assert notify_mod.sent_in_test[-1].get("priority") == "high"


def test_one_missing_overview_row_is_partial_and_withholds_the_log(experiments_path, tmp_env):
    overview = [r for r in FakeInstantly().overview if r.get("campaign_name") != "2026 Cleaning - Trigger Outbound"]
    assert len(overview) == 5
    summary = JOB.run(FakeInstantly(overview=overview), AS_OF, experiments_path=experiments_path)
    assert summary["status"] == "partial"
    assert "cleaning_trigger" in summary["incomplete"]
    assert summary["experiments_written"] is None
    assert "incomplete" in summary["experiments_skipped"]
    assert "INCOMPLETE PULL" in summary["markdown"]


def test_out_writes_the_markdown(client, experiments_path, tmp_env, tmp_path):
    out = str(tmp_path / "nested" / "verdicts.md")
    JOB.main(["--experiments", experiments_path, "--out", out], client=client, as_of=AS_OF)
    text = open(out, encoding="utf-8").read()
    assert text.startswith("# Campaign verdicts and experiments")
    assert "| Campaign | Sends |" in text


def test_json_output_is_machine_readable(client, experiments_path, tmp_env, capsys):
    JOB.main(["--dry-run", "--json", "--experiments", experiments_path], client=client, as_of=AS_OF)
    summary = json.loads(capsys.readouterr().out)
    assert summary["as_of"] == "2026-09-22"
    assert summary["mode"] == "shadow"
    assert len(summary["verdicts"]) == 6
    assert summary["capacity"]["now_per_day"] == 300
    assert summary["capacity"]["after_2026_10_11_per_day"] == 1125


def test_campaign_flag_limits_the_pull(client, experiments_path, tmp_env, capsys):
    JOB.main(["--dry-run", "--campaign", "cleaning_trigger", "--experiments", experiments_path],
             client=client, as_of=AS_OF)
    summary_out = capsys.readouterr().out
    assert "cleaning_trigger" in summary_out
    assert "recruiting_outbound |" not in summary_out


def test_the_report_names_the_two_projection_columns_the_brief_asks_for(client, experiments_path, tmp_env):
    summary = JOB.run(client, AS_OF, experiments_path=experiments_path, dry_run=True)
    md = summary["markdown"]
    assert "ETA now" in md and "ETA at Oct 11 volume" in md
    for verdict in summary["verdicts"]:
        assert verdict["eta_current_volume"] and verdict["eta_oct11_volume"]


# --------------------------------------------------------- the experiment log
def test_seed_carries_the_tests_m4_names():
    doc = EL.seed_document()
    ids = [e["id"] for e in doc["experiments"]]
    assert ids == ["EXP-001a-reactivation-rewrite", "EXP-001b-trigger-rewrite", "EXP-002-icebreaker-style"]
    for cta in doc["experiments"][:2]:
        assert cta["measure"] == {"kind": "campaign_variant", "step": 1, "arms": {"A": 0, "B": 1}}
        assert cta["sample_needed"] == V.VARIANT_MIN_SENDS
        assert "rewrite of the whole email" in cta["what_changed"]
    assert "send me your list" in doc["experiments"][0]["what_changed"]
    ice = doc["experiments"][2]
    assert [a["label"] for a in ice["arms"]] == ["compliment", "researched", "none"]


def test_a_one_armed_test_is_planned_not_running(client):
    """Today variant B does not exist, so EXP-001 has one arm with 1,190 sends
    and one with zero. Reporting that as "running and losing" would be a lie."""
    stats = analytics.collect(client)
    doc = EL.seed_document()
    changes = EL.update(doc, stats, "2026-09-22")
    react, trig = doc["experiments"][0], doc["experiments"][1]
    for cta in (react, trig):
        assert cta["status"] == EL.STATUS_PLANNED
        assert cta["current_sample"]["B"] == 0
        assert cta["start_date"] is None
    assert react["current_sample"]["A"] + trig["current_sample"]["A"] == 1190
    assert "has not been applied" in changes[0]["reason"]


def test_a_lead_variable_test_stays_blocked_rather_than_reporting_zero(client):
    stats = analytics.collect(client)
    doc = EL.seed_document()
    EL.update(doc, stats, "2026-09-22")
    ice = doc["experiments"][2]
    assert ice["status"] == EL.STATUS_BLOCKED
    assert ice["current_sample"] == {}
    assert "icebreaker_style" in ice["blocked_reason"]


def test_both_arms_below_sample_run_without_a_winner(client):
    stats = analytics.collect(client)
    for key, s in stats.items():
        cells = s.variants_for_step(1)
        b = analytics.VariantStats(0, 1, 40, 1, 0)
        b.positives = 1
        s.variants = list(cells) + [b]
    doc = EL.seed_document()
    EL.update(doc, stats, "2026-09-22")
    cta = doc["experiments"][0]
    assert cta["status"] == EL.STATUS_RUNNING
    assert cta["start_date"] == "2026-09-22"
    assert cta["result"]["winner"] is None
    assert "of 500 sends" in cta["result"]["reason"]


def test_a_winner_is_flagged_once_both_arms_pass_sample(client):
    stats = analytics.collect(client)
    for key, s in stats.items():
        a = analytics.VariantStats(0, 0, 600, 30, 0)
        b = analytics.VariantStats(0, 1, 600, 4, 0)
        a.positives, b.positives = 12, 1
        s.variants = [a, b]
    doc = EL.seed_document()
    changes = EL.update(doc, stats, "2026-10-20")
    cta = doc["experiments"][0]
    assert cta["status"] == EL.STATUS_DECIDED
    assert cta["result"]["winner"] == "A" and cta["result"]["loser"] == "B"
    assert cta["result"]["decided_at"] == "2026-10-20"
    assert changes[0]["winner"] == "A"


def test_a_corrupt_experiment_log_is_refused_not_silently_reseeded(tmp_path):
    """Starting from an empty log would reset every running test to zero
    sample and let the next run re-decide it."""
    path = str(tmp_path / "experiments.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{not json")
    with pytest.raises(EL.ExperimentLogError):
        EL.load(path)


def test_missing_file_seeds_and_save_round_trips(tmp_path):
    path = str(tmp_path / "nested" / "experiments.json")
    doc = EL.load(path)
    assert doc["experiments"]
    EL.save(doc, path)
    assert json.load(open(path, encoding="utf-8"))["experiments"]
    with pytest.raises(EL.ExperimentLogError):
        EL.load(str(tmp_path / "absent.json"), seed_if_missing=False)


def test_the_committed_experiments_file_matches_the_schema():
    """config/experiments.json is a deliverable; keep it loadable and seeded."""
    doc = EL.load(EL.DEFAULT_PATH, seed_if_missing=False)
    ids = [e["id"] for e in doc["experiments"]]
    assert ids == ["EXP-001a-reactivation-rewrite", "EXP-001b-trigger-rewrite", "EXP-002-icebreaker-style"]
    for exp in doc["experiments"]:
        for field in ("id", "campaigns", "hypothesis", "what_changed", "start_date",
                      "sample_needed", "current_sample", "status", "result"):
            assert field in exp, (exp.get("id"), field)


# ------------------------------------------------ the sample rule is a rule
def _six_campaigns_with(sends_a, pos_a, sends_b, pos_b, client):
    stats = analytics.collect(client)
    for key, s in stats.items():
        a = analytics.VariantStats(0, 0, sends_a, sends_a // 50, 0)
        b = analytics.VariantStats(0, 1, sends_b, sends_b // 50, 0)
        a.positives, b.positives = pos_a, pos_b
        s.variants = [a, b]
    return stats


def test_pooled_sample_never_declares_a_winner_below_500_sends_per_campaign(client):
    """Six campaigns at 90 sends per arm pool to 540, which clears 500. The
    record's own sample_rule says "per arm, per campaign" and judge_step
    enforces it per campaign, so pooling declares a winner on a sixth of the
    sample M4 requires - across three different niches."""
    stats = _six_campaigns_with(90, 4, 90, 0, client)
    doc = EL.seed_document()
    changes = EL.update(doc, stats, "2026-10-20")
    cta = doc["experiments"][0]
    assert cta["status"] == EL.STATUS_RUNNING
    assert cta["result"]["winner"] is None
    assert cta["sample_gate"]["met"] is False
    assert "has 90 of 500 sends" in cta["result"]["reason"]
    # The pooled number is still reported; it is just not what the gate reads.
    assert cta["current_sample"] == {"A": 270, "B": 270}
    assert cta["current_sample_by_campaign"]["cleaning_reactivation"] == {"A": 90, "B": 90}
    assert changes[0]["sample_met"] is False
    # And the campaign-level judgement in the same report agrees.
    vv = V.judge_step(stats["cleaning_reactivation"], 1)
    assert vv.status == "insufficient_sample"


def test_the_two_judgements_in_one_report_never_disagree(client, experiments_path, tmp_env):
    """The Variants table and the Experiments table read the same data; a
    winner in one and insufficient_sample in the other is the bug."""
    stats = _six_campaigns_with(120, 6, 120, 0, client)

    class Stubbed(FakeInstantly):
        pass

    doc = EL.seed_document()
    EL.update(doc, stats, "2026-10-20")
    variant_statuses = set()
    for key, s in stats.items():
        variant_statuses.add(V.judge_step(s, 1).status)
    assert variant_statuses == {"insufficient_sample"}
    assert doc["experiments"][0]["status"] != EL.STATUS_DECIDED


def test_a_winner_needs_the_sample_in_every_campaign(client):
    stats = _six_campaigns_with(600, 12, 600, 1, client)
    stats["recruiting_outbound"].variants[1].sent = 100     # one campaign short
    doc = EL.seed_document()
    EL.update(doc, stats, "2026-10-20")
    cta = doc["experiments"][1]
    assert cta["status"] == EL.STATUS_RUNNING
    assert "recruiting_outbound B has 100 of 500 sends" in cta["result"]["reason"]


def test_an_unknown_sample_rule_is_refused_not_guessed(client):
    stats = _six_campaigns_with(600, 12, 600, 1, client)
    doc = EL.seed_document()
    doc["experiments"][0]["sample_rule"] = "whatever feels right"
    EL.update(doc, stats, "2026-10-20")
    cta = doc["experiments"][0]
    assert cta["sample_gate"]["unknown_rule"] is True
    assert cta["status"] == EL.STATUS_RUNNING and cta["result"]["winner"] is None


def test_a_pooled_rule_needs_the_sample_times_the_campaigns(client):
    stats = _six_campaigns_with(400, 12, 400, 1, client)
    doc = EL.seed_document()
    doc["experiments"][0]["sample_rule"] = EL.RULE_POOLED
    EL.update(doc, stats, "2026-10-20")
    cta = doc["experiments"][0]
    assert cta["sample_gate"]["needed_pooled"] == 1500
    assert cta["status"] == EL.STATUS_RUNNING            # 1,200 pooled is short
    assert "of 1500 sends pooled" in cta["result"]["reason"]


# ------------------------------------------------------- a decision is final
def test_a_decided_experiment_keeps_its_winner_and_decided_at_on_the_next_run(client):
    stats = _six_campaigns_with(600, 12, 600, 1, client)
    doc = EL.seed_document()
    EL.update(doc, stats, "2026-10-20")
    cta = doc["experiments"][0]
    assert cta["status"] == EL.STATUS_DECIDED and cta["result"]["winner"] == "A"
    assert cta["result"]["decided_at"] == "2026-10-20"

    # A week later, with more sample, the arms converge.
    converged = _six_campaigns_with(1200, 16, 1200, 12, client)
    EL.update(doc, converged, "2026-10-27")
    cta = doc["experiments"][0]
    assert cta["status"] == EL.STATUS_DECIDED
    assert cta["result"]["winner"] == "A" and cta["result"]["loser"] == "B"
    assert cta["result"]["decided_at"] == "2026-10-20"       # not re-stamped
    assert cta["current_sample"] == {"A": 3600, "B": 3600}   # numbers stay live
    assert cta["post_decision"]["as_of"] == "2026-10-27"
    assert cta["post_decision"]["recomputed"]["winner"] is None


def test_a_decided_experiment_survives_the_losing_arm_being_removed(client):
    """Once the loser is pulled from the campaigns its cell disappears from the
    steps analytics, which used to replace the whole result with "only 1 of 2
    arms has sent anything"."""
    stats = _six_campaigns_with(600, 12, 600, 1, client)
    doc = EL.seed_document()
    EL.update(doc, stats, "2026-10-20")
    for key, s in stats.items():
        s.variants = [v for v in s.variants if v.variant == 0]
    EL.update(doc, stats, "2026-11-03")
    cta = doc["experiments"][0]
    assert cta["status"] == EL.STATUS_DECIDED
    assert cta["result"]["winner"] == "A"
    assert cta["result"]["decided_at"] == "2026-10-20"


def test_clearing_decided_at_by_hand_re_opens_a_test(client):
    stats = _six_campaigns_with(600, 12, 600, 1, client)
    doc = EL.seed_document()
    EL.update(doc, stats, "2026-10-20")
    doc["experiments"][0]["result"]["decided_at"] = None
    EL.update(doc, stats, "2026-10-27")
    assert doc["experiments"][0]["result"]["decided_at"] == "2026-10-27"


def test_a_sample_that_jumps_from_zero_to_full_records_a_missed_run(client):
    """start_date is the first run that saw both arms, which after a gap is
    later than the day the change-set went live."""
    doc = EL.seed_document()
    EL.update(doc, analytics.collect(client), "2026-10-02")      # B not live yet
    assert doc["experiments"][0]["start_date"] is None
    stats = _six_campaigns_with(600, 12, 600, 11, client)
    EL.update(doc, stats, "2026-11-06")
    cta = doc["experiments"][0]
    assert cta["start_date"] == "2026-11-06"
    assert cta["start_date_source"] == "first run that saw every arm sending"
    assert "a run was missed" in cta["start_date_warning"]


# ----------------------------------------------------------- job plumbing
def test_a_single_campaign_run_does_not_write_a_partial_experiment_sample(
        client, experiments_path, tmp_env, capsys):
    """run() hands collect()'s subset straight to experiment_log.update, which
    rebuilds current_sample from scratch: one --campaign run would throw the
    other five campaigns' sample away."""
    JOB.main(["--experiments", experiments_path], client=client, as_of=AS_OF)
    full = json.load(open(experiments_path, encoding="utf-8"))
    assert full["experiments"][0]["current_sample"]["A"] == 596

    rc = JOB.main(["--experiments", experiments_path, "--campaign", "cleaning_trigger"],
                  client=FakeInstantly(), as_of=AS_OF)
    assert rc == 0
    after = json.load(open(experiments_path, encoding="utf-8"))
    assert after["experiments"][0]["current_sample"]["A"] == 596
    assert after["experiments"][1]["current_sample"]["A"] == 594
    out = capsys.readouterr().out
    assert "experiments log NOT written" in out


def test_a_dry_run_does_not_leave_the_job_log_pointed_at_the_scratch_file(
        client, experiments_path, tmp_env):
    """use_scratch_logs sets JOB_LOG_PATH process-wide. A real run after a dry
    run in the same process has to write where the 48-hour shadow watch
    reads."""
    from shared.job_log import job_log_path

    before = job_log_path()
    JOB.main(["--dry-run", "--experiments", experiments_path], client=client, as_of=AS_OF)
    assert job_log_path() == before
    assert "scratch" not in str(before)

    JOB.main(["--experiments", experiments_path], client=FakeInstantly(), as_of=AS_OF)
    assert job_log_path() == before
    rows = [r for r in _job_log_rows() if r["job"] == "campaign_verdicts"]
    assert [r["status"] for r in rows] == ["ok"]


def test_dry_run_with_out_still_writes_the_markdown_it_was_asked_for(
        client, experiments_path, tmp_env, tmp_path):
    out = str(tmp_path / "dry" / "verdicts.md")
    JOB.main(["--dry-run", "--out", out, "--experiments", experiments_path],
             client=client, as_of=AS_OF)
    assert os.path.exists(out)
    assert not os.path.exists(experiments_path)


# ------------------------------------------------------------- the report
def test_the_report_renders_a_message_when_no_campaign_matched():
    from services.experiments import report as report_mod
    from services.experiments import verdicts as VV

    cap = VV.capacity_from_ids({"instantly": {"active_inboxes": ["a"] * 12,
                                              "warming_domains": ["d"] * 11,
                                              "per_inbox_daily_limit": 25}})
    md = report_mod.render([], [], EL.seed_document(), cap, AS_OF, "shadow")
    assert "No campaigns matched." in md
    assert "nothing to act on" in md


def test_every_recommendation_prints_a_next_action():
    from services.experiments import report as report_mod
    from services.experiments import verdicts as VV

    assert set(VV.RECOMMENDATIONS) <= set(report_mod.NEXT_ACTIONS)


def test_the_report_gives_a_next_action_for_the_live_verdicts(client, experiments_path, tmp_env):
    summary = JOB.run(client, AS_OF, experiments_path=experiments_path, dry_run=True)
    md = summary["markdown"]
    assert "### Next action" in md
    assert "keep_running" in md.split("### Next action", 1)[1]
    # Twelve rows of "nothing to compare" collapse to one sentence.
    assert "nothing to compare" in md
    assert md.count("single_variant") == 0


def test_the_runbook_friday_command_does_not_disable_notifications():
    """NOTIFY=off short-circuits notify() into an in-process list, so the
    scheduled run's failure alert would reach nobody."""
    from shared.paths import BASE_DIR

    text = open(str(BASE_DIR / "runbooks" / "experiments.md"), encoding="utf-8").read()
    scheduled = [line for line in text.splitlines()
                 if "jobs.campaign_verdicts" in line and "--dry-run" not in line]
    assert scheduled, "the runbook must still show the Friday run"
    for line in scheduled:
        assert "NOTIFY=off" not in line, line


# ------------------------------------------- R12: EXP-001 split and scoped
def _step1_b_body(campaign_key):
    import re

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root, "changesets", "instantly_phase0", "sequences", campaign_key + ".json")
    doc = json.load(open(path, encoding="utf-8"))
    seq = doc.get("sequences") or doc.get("sequence") or doc
    steps = seq[0]["steps"] if isinstance(seq, list) else seq["steps"]
    body = steps[0]["variants"][1]["body"]
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))


def test_exp_001_is_split_by_what_each_staged_b_actually_asks():
    """MKT-8: one pooled record credited a send-me-your-list winner to three
    campaigns whose B offers to send the prospect a list instead."""
    doc = EL.seed_document()
    react, trig = doc["experiments"][0], doc["experiments"][1]
    assert set(react["campaigns"]) | set(trig["campaigns"]) == set(
        e for e in doc["experiments"][2]["campaigns"])
    assert not set(react["campaigns"]) & set(trig["campaigns"])
    for key in react["campaigns"]:
        body = _step1_b_body(key)
        assert "send me your list" in body, key
    for key in trig["campaigns"]:
        body = _step1_b_body(key)
        assert "send me your list" not in body, key
        assert "Reply yes and I'll get it over" in body, key
    # the cleaning trigger B needs the two lead variables the record names
    assert "{{metro}}" in _step1_b_body("cleaning_trigger")
    assert "{{metro}}" in trig["what_changed"] and "{{buildingType}}" in trig["what_changed"]
    committed = EL.load(EL.DEFAULT_PATH, seed_if_missing=False)
    for seeded, live in zip(doc["experiments"], committed["experiments"]):
        assert seeded["campaigns"] == live["campaigns"]
        assert seeded["what_changed"] == live["what_changed"]


def test_a_campaign_at_its_retirement_line_leaves_the_test_and_the_rest_can_decide(client):
    """Recruiting retires at 1,000 sends with about 250 to 300 step-1 sends per
    variant, so under "per arm, per campaign" it held EXP-001 open for ever."""
    stats = _six_campaigns_with(600, 12, 600, 1, client)
    rec = stats["recruiting_reactivation"]
    rec.variants[0].sent, rec.variants[1].sent = 270, 270
    rec.sent, rec.positives, rec.opportunities = 1000, 0, 0
    assert V.decide(rec).recommendation == "retire"
    doc = EL.seed_document()
    changes = EL.update(doc, stats, "2026-10-20")
    react = doc["experiments"][0]
    assert "recruiting_reactivation" in react["sample_gate"]["excluded"]
    assert "retirement line" in react["sample_gate"]["excluded"]["recruiting_reactivation"]
    assert react["sample_gate"]["scope"] == ["bookkeeping_reactivation", "cleaning_reactivation"]
    assert react["status"] == EL.STATUS_DECIDED and react["result"]["winner"] == "A"
    assert changes[0]["excluded"] == react["sample_gate"]["excluded"]
    md = report_table(doc)
    assert "left out of the decision: recruiting_reactivation" in md


def test_before_its_verdict_recruiting_holds_the_test_and_says_why(client):
    stats = _six_campaigns_with(600, 12, 600, 1, client)
    rec = stats["recruiting_reactivation"]
    rec.variants[0].sent, rec.variants[1].sent = 250, 250
    rec.sent, rec.positives, rec.opportunities = 800, 0, 0
    doc = EL.seed_document()
    EL.update(doc, stats, "2026-10-20")
    react = doc["experiments"][0]
    assert react["status"] == EL.STATUS_RUNNING
    assert "recruiting_reactivation A has 250 of 500 sends" in react["result"]["reason"]
    assert "M4 retires it at 1000 sends" in react["result"]["reason"]


def test_a_paused_campaign_is_left_out_with_its_status(client):
    stats = _six_campaigns_with(600, 12, 600, 1, client)
    stats["bookkeeping_trigger"].status = 2
    doc = EL.seed_document()
    EL.update(doc, stats, "2026-10-20")
    trig = doc["experiments"][1]
    assert "not active (status 2)" in trig["sample_gate"]["excluded"]["bookkeeping_trigger"]
    assert "bookkeeping_trigger" not in trig["sample_gate"]["scope"]


def test_a_test_whose_every_campaign_is_out_is_undecidable_not_planned(client):
    stats = analytics.collect(client)          # B not live anywhere
    for key in ("cleaning_trigger", "bookkeeping_trigger", "recruiting_outbound"):
        stats[key].status = 2
    doc = EL.seed_document()
    changes = EL.update(doc, stats, "2026-10-20")
    trig = doc["experiments"][1]
    assert trig["status"] == EL.STATUS_UNDECIDABLE
    assert trig["result"]["winner"] is None
    assert "cannot be decided" in trig["result"]["reason"]
    for key in trig["campaigns"]:
        assert key in trig["result"]["reason"]
    assert changes[1]["status"] == EL.STATUS_UNDECIDABLE
    # the reactivation test is untouched by the trigger campaigns' state
    assert doc["experiments"][0]["status"] == EL.STATUS_PLANNED


def report_table(doc):
    from services.experiments import report as report_mod

    return report_mod.experiment_table(doc)
