"""jobs/daily_metrics.py (O4) and jobs/positive_sweep.py (O3)."""
import csv
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from shared.ghl import GHL
from shared.job_log import job_log_path, read_shadow_log
from shared.notify import sent_in_test
from services.metrics import kpi, render, sheet, sources
from jobs import daily_metrics, positive_sweep

NOW = datetime(2026, 9, 21, 18, 0, tzinfo=timezone.utc) .astimezone(timezone.utc)
AS_OF = datetime(2026, 9, 21, 23, 0, tzinfo=timezone.utc)   # 18:00 CT on 2026-09-21
DAY = date(2026, 9, 21)


def job_log_rows():
    path = job_log_path()
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def run_on_fixtures(dry_run=True, **kw):
    fixtures = daily_metrics.load_fixtures()
    fixtures["ghl"] = GHL(token=None)
    io = daily_metrics.FixtureSheet()
    result = daily_metrics.run(AS_OF, dry_run=dry_run, sheet_io=io, **dict(fixtures, **kw))
    return result, io


def engine_row(ts, job, status="ok", details=None):
    return {"ts_utc": ts, "job": job, "status": status, "mode": "shadow",
            "details": json.dumps(details or {}), "details_parsed": details or {}}


class MemStore(object):
    def __init__(self, data=None):
        self.data = dict(data or {})

    def items(self, prefix=""):
        return [(k, v) for k, v in self.data.items() if k.startswith(prefix)]


def row_of(result, metric):
    return dict((r["metric"], r) for r in result["kpi"])[metric]


# ------------------------------------------------------------------ O4 run
def test_dry_run_reads_renders_and_writes_nothing(tmp_env, shadow_mode):
    result, io = run_on_fixtures()
    assert result["status"].startswith("dry_run")
    assert result["date"] == "2026-09-21"
    assert io.updates == []
    assert result["sheet"] is None and result["skool"] is None
    assert not [r for r in read_shadow_log() if r["action"] in ("daily_metrics_row", "posts_create")]


def test_the_block_carries_the_measured_day_and_passes_the_copy_rules(tmp_env, shadow_mode):
    result, _io = run_on_fixtures()
    assert "300 sent" in result["block"]            # 12 inboxes x 25 on 2026-09-21
    assert result["block"].rstrip().endswith("Lorenzo")
    assert render.copy_violations(result["block"]) == []
    assert result["measured"]["Cold Emails Sent"] == 300


def test_the_forty_day_gap_is_reported_and_not_backfilled(tmp_env, shadow_mode):
    result, io = run_on_fixtures()
    assert result["streak"]["streak"] == 1
    assert result["streak"]["day_number"] == 5
    assert any("day gap" in n for n in result["notes"])
    assert io.updates == []                          # nothing written for the missed days


def test_open_rate_is_never_written_because_tracking_is_off(tmp_env, shadow_mode):
    result, _io = run_on_fixtures()
    assert "Email View Rate" not in result["write_values"]
    assert result["render_values"]["Email View Rate"] is None
    assert "Open n/a" in result["block"]


def test_a_day_instantly_has_not_reported_writes_no_send_count(tmp_env, shadow_mode):
    """At 00:45 the day has no analytics rows yet. 0 would mark the day logged."""
    fixtures = daily_metrics.load_fixtures()
    fixtures["account_rows"] = []
    result = daily_metrics.run(AS_OF, dry_run=True, sheet_io=daily_metrics.FixtureSheet(),
                               ghl=GHL(token=None), **fixtures)
    assert "Cold Emails Sent" not in result["write_values"]
    assert result["render_values"]["Cold Emails Sent"] is None
    assert any("has not reported" in n or "no per-inbox analytics" in n for n in result["notes"])


def test_now_in_shadow_records_would_do_records_and_stages_the_files(tmp_env, shadow_mode):
    result, io = run_on_fixtures(dry_run=False)
    assert io.updates == []                          # the sheet is NOT touched
    sheet_records = [r for r in read_shadow_log() if r["action"] == "daily_metrics_row"]
    assert sheet_records and sheet_records[-1]["payload"]["range"] == "B51:Y51"
    post_records = [r for r in read_shadow_log() if r["action"] == "posts_create"]
    assert post_records and post_records[-1]["system"] == "skool"
    assert result["skool"]["posted"] is False
    staged = result["skool"]["staged"]
    assert staged and open(staged["markdown"], encoding="utf-8").read().startswith("\U0001F4CA DAILY UPDATE")
    assert result["staged"]["daily"].endswith("daily_update_2026-09-21.txt")
    assert result["staged"]["kpi"].endswith("kpi_dashboard_2026-09-21.md")


def test_live_writes_the_row_but_still_will_not_post_to_skool(tmp_env, live_mode):
    result, io = run_on_fixtures(dry_run=False)
    assert len(io.updates) == 1
    rng, values = io.updates[0]
    assert rng == "B51:Y51"                          # 2026-09-21 is row 51
    names = [n for n, _k in sheet.metric_schema()]
    assert values[0][names.index("Cold Emails Sent")] == 300
    assert result["skool"]["posted"] is False and result["skool"]["reason"] == "mcp_handoff"


def test_one_job_log_row_per_run(tmp_env, shadow_mode):
    run_on_fixtures()
    rows = [r for r in job_log_rows() if r["job"] == "daily_metrics"]
    assert len(rows) == 1
    details = json.loads(rows[0]["details"])
    assert details["date"] == "2026-09-21"
    assert details["sent"] == 300
    assert details["streak"] == 1 and details["gap_days"] == 39   # 2026-08-12 -> 2026-09-21
    assert "Upwork response time" in details["kpi_alerts"] or details["kpi_alerts"] == []


def test_an_unreadable_sheet_degrades_but_still_renders(tmp_env, shadow_mode):
    class Broken(object):
        def get_all_values(self):
            raise RuntimeError("no credentials")

    fixtures = daily_metrics.load_fixtures()
    result = daily_metrics.run(AS_OF, dry_run=True, sheet_io=Broken(), ghl=GHL(token=None), **fixtures)
    assert result["degraded"] is True
    assert "300 sent" in result["block"]
    assert result["streak"]["streak"] is None
    assert any("Daily Log unreadable" in n for n in result["notes"])


def test_kpi_dashboard_is_part_of_the_run(tmp_env, shadow_mode):
    result, _io = run_on_fixtures()
    assert result["dashboard"].startswith("# KPI dashboard 2026-09-21")
    states = dict((r["metric"], r["state"]) for r in result["kpi"])
    assert states["Real reply rate"] == "green"
    assert states["Positive to booked"] == "no data"    # no GHL token


def test_cli_dry_run_on_fixtures(tmp_env, shadow_mode, capsys):
    code = daily_metrics.main(["--dry-run", "--fixtures", "--as-of", "2026-09-21T18:00:00-05:00"])
    out = capsys.readouterr().out
    assert code == 0
    assert "DAILY UPDATE" in out and "KPI dashboard" in out


def test_cli_kpi_only(tmp_env, shadow_mode, capsys):
    daily_metrics.main(["--dry-run", "--fixtures", "--kpi-only",
                        "--as-of", "2026-09-21T18:00:00-05:00"])
    out = capsys.readouterr().out
    assert out.startswith("# KPI dashboard")
    assert "DAILY UPDATE" not in out


# ------------------------------------------------------------------ O3 run
def test_positive_sweep_delegates_and_does_not_reimplement_the_sweep(tmp_env, shadow_mode, monkeypatch):
    calls = []

    def fake_run_sweep(now, **kwargs):
        calls.append((now, kwargs))
        return {"digest": "Pipeline sweep: 2 item(s)", "counts": {"total": 2, "positive": 1},
                "notes": [], "status": "dry_run", "items": []}

    monkeypatch.setattr(positive_sweep.pipeline_sweep, "run_sweep", fake_run_sweep)
    result = positive_sweep.run(AS_OF, dry_run=True)
    assert len(calls) == 1 and calls[0][1]["dry_run"] is True
    assert result["delegate"] == "pipeline_sweep"
    assert result["text"] == "Pipeline sweep: 2 item(s)"
    rows = [r for r in job_log_rows() if r["job"] == "positive_sweep"]
    assert len(rows) == 1 and rows[0]["status"] == "delegated_dry_run"
    assert json.loads(rows[0]["details"])["counts"]["total"] == 2


def test_positive_sweep_appends_the_kpi_dashboard(tmp_env, shadow_mode, monkeypatch):
    monkeypatch.setattr(positive_sweep.pipeline_sweep, "run_sweep",
                        lambda now, **kw: {"digest": "list", "counts": {}, "notes": [],
                                           "status": "dry_run", "items": []})
    rows = positive_sweep.kpi.build({"bounce_rate": 0.05})
    result = positive_sweep.run(AS_OF, dry_run=True, with_kpi=True, kpi_rows=rows)
    assert result["text"].startswith("list\n\n# KPI dashboard")
    logged = json.loads([r for r in job_log_rows() if r["job"] == "positive_sweep"][0]["details"])
    assert logged["kpi_alerts"] == ["Bounce rate"] and logged["kpi_included"] is True


def test_positive_sweep_cli_on_fixtures(tmp_env, shadow_mode, capsys):
    code = positive_sweep.main(["--dry-run", "--fixtures", "--as-of", "2026-09-21T07:30:00-05:00"])
    out = capsys.readouterr().out
    assert code == 0 and "Pipeline sweep" in out


def test_positive_sweep_never_sends_a_digest_in_dry_run(tmp_env, shadow_mode, monkeypatch):
    sent = []
    monkeypatch.setattr(positive_sweep.pipeline_sweep, "notify",
                        lambda *a, **k: sent.append(a) or {})
    positive_sweep.run(AS_OF, dry_run=True, received=[], manual=[], leads_by_email={},
                       ghl=GHL(token=None))
    assert sent == []


def test_a_morning_run_before_any_sends_is_not_a_volume_alarm(tmp_env, shadow_mode):
    """O3 runs at 07:30 and Instantly has no row for the day yet. Reading that
    as 0 sends made "Sends/day vs plan" ALERT every single morning."""
    fixtures = daily_metrics.load_fixtures()
    result = daily_metrics.run(
        datetime(2026, 9, 22, 12, 30, tzinfo=timezone.utc),   # 07:30 CT
        dry_run=True, sheet_io=daily_metrics.FixtureSheet(), ghl=GHL(token=None), **fixtures)
    row = dict((r["metric"], r) for r in result["kpi"])["Sends/day vs plan"]
    assert row["state"] == "green"
    assert row["window"] == "2026-09-21"
    assert "last day it reported" in row["note"]
    assert "Read this way:" in result["dashboard"]


# ------------------------------------------------- what the reviewers found
def test_positive_reply_rate_uses_one_window_on_both_sides(tmp_env, shadow_mode):
    """The numerator was one CT day and the denominator was the week's sends:
    about a sevenfold understatement, printed as ALERT, whose Section 6 action
    is "rework or kill the campaign". 14 positives over 1,800 sends is 0.78%,
    which is green."""
    rows = []
    for offset in range(7):
        day = DAY - timedelta(days=offset)
        for _ in range(2):
            rows.append(engine_row("%sT19:00:00+00:00" % day.isoformat(),
                                   "reply_engine.process_event",
                                   details={"label": "positive_interested"}))
    result, _io = run_on_fixtures(job_rows=rows)
    row = row_of(result, "Positive reply rate")
    assert result["data"]["week"]["sent"] == 1800
    assert row["value"] == pytest.approx(14 / 1800.0)
    assert row["state"] == "green" and row["window"] == "7 days"
    assert "Positive reply rate" not in json.loads(
        [r for r in job_log_rows() if r["job"] == "daily_metrics"][0]["details"])["kpi_alerts"]


def test_a_ghl_stage_snapshot_is_not_written_as_a_daily_flow(tmp_env, shadow_mode):
    """"Proposals Sent" and "Closes" are flow columns that all_time_totals sums.
    Writing the pipeline census into them re-counted the same closed deals every
    evening, so two September clients became two closes a day forever."""
    class FakeGHL(object):
        def search_opportunities(self, **kwargs):
            stages = sources.settings.GHL_STAGES
            return {"opportunities": [
                {"id": "p1", "pipelineStageId": stages["proposal_sent"]},
                {"id": "p2", "pipelineStageId": stages["proposal_sent"]},
                {"id": "w1", "pipelineStageId": stages["won"]},
                {"id": "w2", "pipelineStageId": stages["won"]},
            ]}

    first, _io = run_on_fixtures(ghl=FakeGHL())
    assert "Closes" not in first["write_values"]
    assert "Proposals Sent" not in first["write_values"]
    assert "2 closed" not in first["block"]
    assert any("stage-change timestamp" in n for n in first["notes"])
    # The census is still available for the reader who wants it.
    assert first["data"]["ghl_stages"]["stages"]["won"] == 2


def test_a_dated_stage_transition_is_written_but_only_for_that_day(tmp_env, shadow_mode):
    class DatedGHL(object):
        def search_opportunities(self, **kwargs):
            stages = sources.settings.GHL_STAGES
            return {"opportunities": [
                {"id": "w1", "pipelineStageId": stages["won"],
                 "lastStageChangeAt": "2026-09-21T20:00:00+00:00"},
                {"id": "w2", "pipelineStageId": stages["won"],
                 "lastStageChangeAt": "2026-08-30T20:00:00+00:00"},
            ]}

    result, _io = run_on_fixtures(ghl=DatedGHL())
    assert result["write_values"]["Closes"] == 1       # not 2
    assert result["write_values"]["Proposals Sent"] == 0


def test_dry_run_reads_the_real_job_log_not_the_scratch_one(tmp_env, shadow_mode, capsys):
    """--dry-run calls use_scratch_logs(), which repoints JOB_LOG_PATH. That is
    a WRITE redirection; reading it made every preview blind to the reply
    engine, and the runbook tells Lorenzo to validate the numbers on exactly
    that preview."""
    real = tmp_env / "job_log.csv"
    with open(real, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["ts_utc", "job", "status", "mode", "details"])
        writer.writeheader()
        for _ in range(3):
            writer.writerow({"ts_utc": "2026-09-21T19:00:00+00:00",
                             "job": "reply_engine.process_event", "status": "ok",
                             "mode": "shadow", "details": json.dumps({"label": "positive_booking"})})

    code = daily_metrics.main(["--dry-run", "--fixtures", "--as-of", "2026-09-21T18:00:00-05:00",
                               "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["measured"]["Positive Replies"] == 3
    assert not any("reply engine has no rows" in n for n in out["notes"])
    # and the preview did not clobber the artifact a --now run would have left
    assert out["staged"]["daily"].endswith("daily_update_2026-09-21.dryrun.txt")


def test_a_stale_appointment_does_not_make_calls_booked_zero(tmp_env, shadow_mode):
    """engine_seen used to be true whenever the store held ANY appointment, so
    one August booking made the job write "Calls Booked = 0" on every later day,
    which the Logged formula then counted as a logged day."""
    store = MemStore({"appointment:old": {"booked_at": "2026-08-01T18:00:00+00:00"}})
    result, _io = run_on_fixtures(store=store, job_rows=[])
    assert "Calls Booked" not in result["write_values"]
    assert any("reply engine has no rows" in n for n in result["notes"])


def test_a_measured_zero_does_not_erase_a_typed_pipeline_number(tmp_env, shadow_mode):
    """The poller writes a reply_engine row every day in shadow and books
    nothing, so "0 calls booked" was written over the 2 Lorenzo had typed."""
    values = json.loads(json.dumps(daily_metrics.FixtureSheet().get_all_values()))
    header = values[0]
    row = values[1]                                    # 2026-08-03, a logged day
    row[header.index("Calls Booked")] = 2
    row[header.index("Positive Replies")] = 3

    class Seeded(daily_metrics.FixtureSheet):
        def get_all_values(self):
            return values

    rows = [engine_row("2026-08-03T19:00:00+00:00", "reply_engine.poller"),
            engine_row("2026-08-03T19:05:00+00:00", "reply_engine.process_event",
                       details={"label": "not_interested"})]
    fixtures = daily_metrics.load_fixtures()
    result = daily_metrics.run(datetime(2026, 8, 3, 23, 0, tzinfo=timezone.utc),
                               dry_run=True, sheet_io=Seeded(), ghl=GHL(token=None),
                               job_rows=rows, store=MemStore(), **fixtures)
    assert "Calls Booked" not in result["write_values"]
    assert result["write_values"].get("Positive Replies") is None
    assert result["render_values"]["Calls Booked"] == 2
    assert "2 booked" in result["block"]


def test_a_campaign_analytics_failure_does_not_blank_the_send_count(tmp_env, shadow_mode):
    """One completeness flag meant a 500 on GET /campaigns/analytics withheld a
    send count that GET /accounts/analytics/daily had answered cleanly: no
    numeric cell, no logged day, a broken streak and "n/a sent" in the post."""
    class HalfBroken(object):
        def daily_account_analytics(self, emails=None, start_date=None, end_date=None):
            return daily_metrics.load_fixtures()["account_rows"]

        def campaign_analytics(self, **kwargs):
            raise sources.InstantlyError("500 Internal Server Error")

        def list_accounts(self, **kwargs):
            return daily_metrics.load_fixtures()["accounts"]

    result = daily_metrics.run(AS_OF, dry_run=True, sheet_io=daily_metrics.FixtureSheet(),
                               ghl=GHL(token=None), instantly=HalfBroken())
    assert result["write_values"]["Cold Emails Sent"] == 300
    assert result["status"] == "dry_run_partial"          # still reported as partial
    assert any("campaign analytics failed" in n for n in result["notes"])


def test_a_warmup_alert_names_the_inbox(tmp_env, shadow_mode):
    """Section 6's action on this row is "pause the inbox", which Lorenzo cannot
    do from a dashboard that only says the score."""
    accounts = {"items": [{"email": e, "stat_warmup_score": 97 if i == 0 else 100}
                          for i, e in enumerate(sources.active_inboxes())]}
    result, _io = run_on_fixtures(accounts=accounts)
    row = row_of(result, "Warm-up health per inbox")
    assert row["state"] == "ALERT" and row["value"] == 97
    assert sources.active_inboxes()[0] in (row["note"] or "")
    assert sources.active_inboxes()[0] in result["dashboard"]
    details = json.loads([r for r in job_log_rows() if r["job"] == "daily_metrics"][0]["details"])
    assert details["warmup_below_98"] == [sources.active_inboxes()[0]]
    assert any(sources.active_inboxes()[0] in line for line in details["kpi_alert_detail"])


def test_one_inbox_over_the_bounce_line_is_not_hidden_by_the_aggregate(tmp_env, shadow_mode):
    """One inbox bouncing 8% (four times the removal line) reads 0.7% once it is
    averaged with eleven clean ones."""
    rows = json.loads(json.dumps(daily_metrics.load_fixtures()["account_rows"]))
    worst = sources.active_inboxes()[0]
    for row in rows:
        if row["email_account"] == worst:
            row["bounced"] = 2
    result, _io = run_on_fixtures(account_rows=rows)
    row = row_of(result, "Bounce rate")
    assert worst in (row["note"] or "")
    assert "deliverability_monitor" in row["note"]
    assert worst in result["dashboard"]


def test_a_partial_day_is_not_a_volume_alert(tmp_env, shadow_mode):
    """At the scheduled 18:00 run the 07:00-19:00 send window is 11/12 done."""
    rows = [r for r in json.loads(json.dumps(daily_metrics.load_fixtures()["account_rows"]))]
    for row in rows:
        if row["date"] == "2026-09-21":
            row["sent"] = 23                     # 276 of 300, on pace
    result, _io = run_on_fixtures(account_rows=rows)
    row = row_of(result, "Sends/day vs plan")
    assert row["state"] == "green"
    assert "send window" in row["window"]
    assert "not finished" in (row["note"] or "")
    assert any("partial day" in n for n in result["notes"])


def test_an_early_morning_partial_day_is_not_divided_into_a_wild_number(tmp_env, shadow_mode):
    """Scaling the plan by the elapsed window is right at 18:00 and absurd at
    07:30: the window is 4% gone, so 20 sends would read as 1,600% of plan.
    Before a quarter of the window the row reports the last day that finished."""
    rows = json.loads(json.dumps(daily_metrics.load_fixtures()["account_rows"]))
    for row in rows:
        if row["date"] == "2026-09-21":
            row["sent"] = 2                       # 24 sent so far today
    fixtures = daily_metrics.load_fixtures()
    fixtures["account_rows"] = rows
    result = daily_metrics.run(datetime(2026, 9, 21, 12, 30, tzinfo=timezone.utc),  # 07:30 CT
                               dry_run=True, sheet_io=daily_metrics.FixtureSheet(),
                               ghl=GHL(token=None), **fixtures)
    row = row_of(result, "Sends/day vs plan")
    assert row["state"] == "green" and row["value"] == pytest.approx(1.0)
    assert row["window"] == "2026-09-19"          # the last full day in the pull
    assert "too early to read a pace" in row["note"]
    # and the day's own partial count is still written to the tracker as measured
    assert result["write_values"]["Cold Emails Sent"] == 24


class LoggedSheet(daily_metrics.FixtureSheet):
    """The recorded Daily Log plus hand-written partial rows for some days, as
    the 18:00 run would have left them."""

    def __init__(self, logged):
        super(LoggedSheet, self).__init__()
        self.logged = logged     # {date: cold emails sent}

    def get_all_values(self):
        values = super(LoggedSheet, self).get_all_values()
        header = values[0]
        sent_col = header.index("Cold Emails Sent")
        logged_col = header.index("Logged")
        for day, sent in self.logged.items():
            serial = (day - sheet.SHEET_EPOCH).days
            for row in values[1:]:
                if row and row[0] == serial:
                    row[sent_col] = sent
                    row[logged_col] = 1
                    break
            else:
                row = [serial] + [""] * (len(header) - 1)
                row[sent_col] = sent
                row[logged_col] = 1
                values.append(row)
        return values


def test_the_next_run_restates_the_previous_partial_day(tmp_env, shadow_mode):
    """The 18:00 row is always short by whatever goes out before 19:00, and
    nothing ever revisited it."""
    fixtures = daily_metrics.load_fixtures()
    result = daily_metrics.run(AS_OF, dry_run=False, sheet_io=daily_metrics.FixtureSheet(),
                               ghl=GHL(token=None), **fixtures)
    # 2026-09-20 has no rows in the recorded pull, so there is nothing to restate
    assert result["restated"] is None
    # ... but a day the 18:00 run logged and Instantly reported is restated,
    # as a second guarded write
    result = daily_metrics.run(datetime(2026, 9, 20, 23, 0, tzinfo=timezone.utc),
                               dry_run=False, sheet_io=LoggedSheet({date(2026, 9, 19): 250}),
                               ghl=GHL(token=None), **fixtures)
    assert result["restated"]["date"] == "2026-09-19"
    assert result["restated"]["sent"] == 300 and result["restated"]["ok"] is True
    assert any("restated 2026-09-19" in n for n in result["notes"])
    rows = [r for r in read_shadow_log() if r["action"] == "daily_metrics_row"]
    assert [r["payload"]["date"] for r in rows[-2:]] == ["2026-09-20", "2026-09-19"]
    # a dry run never restates anything
    assert daily_metrics.run(datetime(2026, 9, 20, 23, 0, tzinfo=timezone.utc), dry_run=True,
                             sheet_io=LoggedSheet({date(2026, 9, 19): 250}), ghl=GHL(token=None),
                             **fixtures)["restated"] is None


def test_ops13_a_day_that_was_never_logged_is_not_backfilled(tmp_env, shadow_mode):
    """OPS-13: the restatement filled 2026-09-21 (an empty cell) with "the
    18:00 run could only see part of that day", which repaired the public
    streak for a day nobody posted."""
    fixtures = daily_metrics.load_fixtures()
    io = daily_metrics.FixtureSheet()
    assert not sheet.read_daily_log(io).is_logged(date(2026, 9, 21))
    result = daily_metrics.run(datetime(2026, 9, 22, 23, 0, tzinfo=timezone.utc), dry_run=False,
                               sheet_io=io, ghl=GHL(token=None), **fixtures)
    assert result["restated"] is None
    assert not any("restated 2026-09-21" in n for n in result["notes"])
    assert any("2026-09-21 was not restated" in n for n in result["notes"])
    assert all(r["payload"]["date"] != "2026-09-21" for r in read_shadow_log()
               if r["action"] == "daily_metrics_row")
    assert result["streak"]["streak"] == 1


def test_the_trend_column_is_populated_from_the_prior_week(tmp_env, shadow_mode):
    """The shipped account fixture starts on 2026-09-15 because the workspace
    genuinely has no per-inbox row before then (verified read-only: a GET for
    2026-09-01..14 returns zero rows). So the prior-week path, and with it the
    "vs last week" column the brief asks for, was never exercised. This drives
    it from a clearly-named synthetic prior week."""
    fixtures = daily_metrics.load_fixtures()
    with open(daily_metrics.FIXTURES_DIR /
              "instantly_daily_account_prior_week_synthetic_2026-09-08_14.json",
              encoding="utf-8") as fh:
        prior = json.load(fh)
    result, _io = run_on_fixtures(account_rows=fixtures["account_rows"] + prior)
    assert result["data"]["window"]["prior_start"] == "2026-09-08"
    assert result["data"]["window"]["prior_end"] == "2026-09-14"
    assert result["data"]["prior_week"]["sent"] == 1500
    bounce = row_of(result, "Bounce rate")
    reply = row_of(result, "Real reply rate")
    assert bounce["prior"] == pytest.approx(12 / 1500.0)
    assert "worse" in bounce["trend"] and "↑" in bounce["trend"]
    assert "better" in reply["trend"] and "↑" in reply["trend"]
    assert "| - |" not in result["dashboard"].split("Real reply rate")[1].split("\n")[0]


def test_a_header_only_daily_log_does_not_publish_a_fake_day_one(tmp_env, shadow_mode):
    """An unreadable date column parses to zero dated rows, which is
    indistinguishable from a first run: the post would claim "Day 1, 1 day
    streak" on day five with no note saying the sheet could not be read."""
    values = json.loads(json.dumps(daily_metrics.FixtureSheet().get_all_values()))
    for row in values[1:]:
        row[0] = "Tue, Sep 22"

    class TextDates(daily_metrics.FixtureSheet):
        def get_all_values(self):
            return values

    fixtures = daily_metrics.load_fixtures()
    result = daily_metrics.run(AS_OF, dry_run=True, sheet_io=TextDates(),
                               ghl=GHL(token=None), **fixtures)
    assert result["degraded"] is True
    assert result["streak"]["streak"] is None and result["streak"]["day_number"] is None
    assert "Day 1" not in result["block"]
    assert any("Daily Log unreadable" in n for n in result["notes"])


def test_an_unexpected_failure_still_logs_a_row_and_alerts(tmp_env, shadow_mode, monkeypatch):
    """A rotated INSTANTLY_API_KEY used to kill the 18:00 job on a traceback
    with no Job_Log row and no push: the first signal was the streak breaking
    days later."""
    monkeypatch.delenv("INSTANTLY_API_KEY", raising=False)
    monkeypatch.setenv("NOTIFY", "off")
    del sent_in_test[:]
    with pytest.raises(Exception):
        daily_metrics.main(["--dry-run", "--as-of", "2026-09-21T18:00:00-05:00"])
    rows = [r for r in job_log_rows() if r["job"] == "daily_metrics"]
    assert rows and rows[-1]["status"] == "failed"
    assert "INSTANTLY_API_KEY" in json.loads(rows[-1]["details"])["error"]
    assert sent_in_test and sent_in_test[-1]["title"] == "Daily metrics failed"


def test_the_positive_sweep_also_logs_and_alerts_on_failure(tmp_env, shadow_mode, monkeypatch):
    def boom(now, **kwargs):
        raise RuntimeError("emails endpoint 500")

    monkeypatch.setattr(positive_sweep.pipeline_sweep, "run_sweep", boom)
    monkeypatch.setenv("NOTIFY", "off")
    del sent_in_test[:]
    with pytest.raises(RuntimeError):
        positive_sweep.main(["--dry-run", "--as-of", "2026-09-21T07:30:00-05:00"])
    rows = [r for r in job_log_rows() if r["job"] == "positive_sweep"]
    assert rows and rows[-1]["status"] == "failed"
    assert sent_in_test and sent_in_test[-1]["title"] == "Positive sweep failed"


def test_the_morning_kpi_dashboard_reaches_a_channel_lorenzo_reads(tmp_env, shadow_mode, monkeypatch):
    """--kpi printed to stdout only: pipeline_sweep sends its own digest with no
    dashboard in it, so on the only run that matters the "what is off" half of
    the 07:30 read reached a process log and nothing else."""
    monkeypatch.setattr(positive_sweep.pipeline_sweep, "run_sweep",
                        lambda now, **kw: {"digest": "list", "counts": {}, "notes": [],
                                           "status": "ok", "items": []})
    rows = kpi.build({"bounce_rate": 0.05})
    result = positive_sweep.run(AS_OF, dry_run=False, with_kpi=True, kpi_rows=rows)
    assert result["staged"] and result["staged"].endswith("kpi_dashboard_2026-09-21.md")
    with open(result["staged"], encoding="utf-8") as fh:
        assert fh.read().startswith("# KPI dashboard 2026-09-21")
    logged = json.loads([r for r in job_log_rows() if r["job"] == "positive_sweep"][0]["details"])
    assert logged["staged"] == result["staged"]


def test_the_staged_skool_arguments_match_the_mcp_schema(tmp_env, shadow_mode):
    """skool_posts_create is additionalProperties: false. A stray convenience
    key in the staged arguments makes a session's paste fail validation."""
    result, _io = run_on_fixtures(dry_run=False)
    with open(result["skool"]["staged"]["arguments"], encoding="utf-8") as fh:
        staged = json.load(fh)
    assert staged["tool"] == "skool_posts_create"
    assert staged["group_slug"] == "maker-school"
    assert set(staged["arguments"]) <= {"groupId", "title", "content", "label"}
    assert set(staged["arguments"]) >= {"groupId", "title", "content"}
    assert render.copy_violations(staged["arguments"]["content"]) == []


# --------------------------------------------- re-review 2026-09-22 (OPS-2, 14)
def test_ops2_an_unprotected_topic_gets_counts_and_the_email_gets_the_names(tmp_env, shadow_mode,
                                                                          monkeypatch):
    """The Upwork row's note named the client whose room was waiting ("the
    longest wait is <name> (171 h)") and it went to the public ntfy topic."""
    monkeypatch.delenv("NTFY_TOKEN", raising=False)
    monkeypatch.delenv("NTFY_ALLOW_SENSITIVE", raising=False)
    monkeypatch.setenv("NOTIFY", "off")
    del sent_in_test[:]
    rooms = [{"client": "Pat Example, Example Co", "awaiting": "you",
              "last_message_at": "2026-09-14T19:46:43+00:00"}]
    result, _io = run_on_fixtures(dry_run=False, rooms=rooms, write_sheet=False, post_skool=False,
                                  stage_files=False)
    assert any(r["metric"] == "Upwork response time" and r["state"] == kpi.ALERT
               for r in result["kpi"])
    sent = sent_in_test[-1]
    assert "Pat Example" not in sent["message"] and "Pat Example" not in sent["title"]
    assert "KPI alert(s)" in sent["message"] and "went by email" in sent["message"]
    assert "Pat Example" in sent["email_message"]

    monkeypatch.setenv("NTFY_TOKEN", "tk-not-a-real-token")
    del sent_in_test[:]
    run_on_fixtures(dry_run=False, rooms=rooms, write_sheet=False, post_skool=False,
                    stage_files=False)
    assert "Pat Example" in sent_in_test[-1]["message"]


def test_ops2_the_failure_push_carries_no_error_text_on_a_public_topic(tmp_env, shadow_mode,
                                                                       monkeypatch):
    monkeypatch.delenv("INSTANTLY_API_KEY", raising=False)
    monkeypatch.delenv("NTFY_TOKEN", raising=False)
    monkeypatch.delenv("NTFY_ALLOW_SENSITIVE", raising=False)
    monkeypatch.setenv("NOTIFY", "off")
    del sent_in_test[:]
    with pytest.raises(Exception):
        daily_metrics.main(["--dry-run", "--as-of", "2026-09-21T18:00:00-05:00"])
    sent = sent_in_test[-1]
    assert "INSTANTLY_API_KEY" not in sent["message"]
    assert "INSTANTLY_API_KEY" in sent["email_message"]


def _positive_rows(days, leads_per_day):
    rows = []
    for day in days:
        for n in range(leads_per_day):
            rows.append(engine_row("%sT15:00:00+00:00" % day, "reply_engine.process_event", "ok",
                                   {"label": "positive_interested", "lead": "%s-%d@x.com" % (day, n)}))
    return rows


def test_ops14_one_day_under_the_line_is_watch_not_alert(tmp_env, shadow_mode):
    """Section 6: "< 0.5% for 3 days". A single reading used to go out as a
    high-priority ALERT."""
    # 1 positive lead in the week to 09-21 against 1,800 sends = 0.06%, but the
    # two earlier trailing windows had plenty.
    early = _positive_rows(["2026-09-15"], 1)
    job_rows = early + _positive_rows(["2026-09-14", "2026-09-13"], 20)
    for row in job_rows:
        row["details_parsed"] = json.loads(row["details"])
    result, _io = run_on_fixtures(job_rows=job_rows)
    row = row_of(result, "Positive reply rate")
    assert row["value"] < 0.005
    assert row["state"] == kpi.WATCH
    assert "Section 6 alerts after 3" in row["note"]


def test_ops14_three_days_under_the_line_is_an_alert(tmp_env, shadow_mode):
    job_rows = _positive_rows(["2026-09-15"], 1)
    for row in job_rows:
        row["details_parsed"] = json.loads(row["details"])
    result, _io = run_on_fixtures(job_rows=job_rows)
    row = row_of(result, "Positive reply rate")
    assert row["state"] == kpi.ALERT


def test_ops14_the_positive_rate_counts_leads_not_events(tmp_env, shadow_mode):
    one_lead = [engine_row("2026-09-2%dT15:00:00+00:00" % d, "reply_engine.process_event", "ok",
                           {"label": "positive_interested", "lead": "same@x.com"})
                for d in (0, 1)]
    for row in one_lead:
        row["details_parsed"] = json.loads(row["details"])
    result, _io = run_on_fixtures(job_rows=one_lead)
    assert result["data"]["engine"] is not None
    assert "1 lead(s) classified positive" in row_of(result, "Positive reply rate")["note"]


def test_ops15_the_skool_stage_leaves_no_orphan_live_write_intent(tmp_env, live_mode):
    """guard_write in live mode opens a live_write_intent row that the post is
    expected to close. This module never posts, so the row hung open."""
    result, _io = run_on_fixtures(dry_run=False)
    assert result["skool"]["posted"] is False and result["skool"]["reason"] == "mcp_handoff"
    intents = [r for r in job_log_rows() if r["status"] == "live_write_intent"]
    assert not [r for r in intents if r["job"].startswith("skool.")]
    assert [r for r in read_shadow_log() if r["action"] == "posts_create"]
