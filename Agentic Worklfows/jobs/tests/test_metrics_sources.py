"""services/metrics/sources.py: the read-only collectors behind O4."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from services.metrics import sources

CT = sources.settings.TZ
FIXTURES = sources.Path(__file__).resolve().parent.parent.parent / "services" / "metrics" / "fixtures"


def load(name):
    with open(FIXTURES / name, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ------------------------------------------------------------------ clock
def test_ct_day_uses_central_not_utc():
    # 2026-09-23 02:00 UTC is still 2026-09-22 in Chicago. The tracker has one
    # row per Central day, so a UTC day here would file the evening's numbers
    # under tomorrow.
    assert sources.ct_day(datetime(2026, 9, 23, 2, 0, tzinfo=timezone.utc)) == date(2026, 9, 22)
    assert sources.ct_day(datetime(2026, 9, 22, 23, 0, tzinfo=timezone.utc)) == date(2026, 9, 22)


def test_parse_day_accepts_dates_and_timestamps():
    assert sources.parse_day("2026-09-21") == date(2026, 9, 21)
    assert sources.parse_day("2026-09-21T18:00:00Z") == date(2026, 9, 21)
    assert sources.parse_day("") is None
    assert sources.parse_day("not a date") is None


def test_ratio_is_none_not_zero_without_a_denominator():
    assert sources.ratio(3, 0) is None
    assert sources.ratio(None, 100) is None
    assert sources.ratio(3, 300) == pytest.approx(0.01)


# --------------------------------------------------------------- analytics
def test_real_replies_never_subtracts_the_automatic_counter():
    """The regression this module was written around.

    unique_replies_automatic is NOT a subset of unique_replies: the recorded
    2026-09-18 day is 4 unique and 7 automatic. Subtracting clamps to zero and
    reports a 0.0% real reply rate for a week that ran at about 1.1%."""
    rows = [
        {"date": "2026-09-18", "sent": 300, "unique_replies": 4, "unique_replies_automatic": 7, "bounced": 6},
        {"date": "2026-09-19", "sent": 300, "unique_replies": 0, "unique_replies_automatic": 7, "bounced": 3},
    ]
    totals = sources.summarize_account_rows(rows)
    assert totals["replies"] == 4
    assert totals["replies_automatic"] == 14
    assert totals["real_replies"] == 4          # not max(0, 4 - 14) == 0
    assert sources.ratio(totals["real_replies"], totals["sent"]) == pytest.approx(4 / 600.0)


def test_recorded_week_matches_the_measured_live_numbers():
    """Sept 15-21 on the recorded pull: about 1.1% bounce, about 1.1% real reply."""
    rows = load("instantly_daily_account_2026-09-08_21.json")
    week = [r for r in rows if date(2026, 9, 15) <= sources.parse_day(r["date"]) <= date(2026, 9, 21)]
    totals = sources.summarize_account_rows(week)
    assert totals["sent"] == 1800
    assert sources.ratio(totals["bounced"], totals["sent"]) == pytest.approx(0.0111, abs=0.002)
    assert sources.ratio(totals["real_replies"], totals["sent"]) == pytest.approx(0.0106, abs=0.002)


def test_account_rows_for_filters_by_day():
    rows = load("instantly_daily_account_2026-09-08_21.json")
    day_rows = sources.account_rows_for(rows, date(2026, 9, 21))
    assert day_rows and all(r["date"].startswith("2026-09-21") for r in day_rows)
    assert sources.summarize_account_rows(day_rows)["sent"] == 300


def test_summarize_campaign_rows_labels_campaigns_from_ids_json():
    rows = load("instantly_campaign_analytics_2026-09-21.json")
    summary = sources.summarize_campaign_rows(rows)
    # The 2026-09-21 pull: six campaigns, 50 sends each.
    assert len(summary["campaigns"]) == 6
    assert summary["totals"]["sent"] == 300
    assert summary["totals"]["real_replies"] == summary["totals"]["replies"]
    keys = set(c["key"] for c in summary["campaigns"])
    assert "cleaning_reactivation" in keys and None not in keys


def test_fetch_account_daily_chunks_and_survives_a_failed_chunk():
    calls = []

    class Fake(object):
        def daily_account_analytics(self, emails=None, start_date=None, end_date=None):
            calls.append(list(emails))
            if len(calls) == 2:
                raise sources.InstantlyError("413 too large")
            return [{"date": start_date, "email_account": e, "sent": 25} for e in emails]

    emails = ["a%d@x.com" % i for i in range(7)]
    notes = []
    rows, complete = sources.fetch_account_daily(
        Fake(), emails, "2026-09-21", "2026-09-21", chunk=3, notes=notes)
    assert [len(c) for c in calls] == [3, 3, 1]
    assert complete is False                      # the run is partial, not silently short
    assert len(rows) == 4                         # chunk 1 and chunk 3
    assert any("chunk failed" in n for n in notes)


def test_warmup_health_reports_no_data_rather_than_zero():
    assert sources.warmup_health(None, ["a@x.com"])["worst"] is None
    accounts = {"items": [{"email": "a@x.com", "stat_warmup_score": 100},
                          {"email": "b@x.com", "stat_warmup_score": 91},
                          {"email": "other@x.com", "stat_warmup_score": 10}]}
    health = sources.warmup_health(accounts, ["a@x.com", "b@x.com"])
    assert health["worst"] == 91 and health["below_98"] == ["b@x.com"]
    assert "other@x.com" not in health["scores"]  # not an active inbox


def test_plan_sends_per_day_from_ids_json():
    assert sources.plan_sends_per_day() == 12 * 25    # 12 active inboxes x 25/day
    assert sources.plan_sends_per_day([]) is None


# ------------------------------------------------------------------ Upwork
def test_upwork_handoff_for_another_day_is_ignored(tmp_env):
    path = tmp_env / "upwork_daily.json"
    path.write_text(json.dumps({"date": "2026-09-20", "proposals": 3, "connects": 90}))
    assert sources.read_upwork_daily(path, day=date(2026, 9, 22)) is None
    assert sources.read_upwork_daily(path, day=date(2026, 9, 20))["proposals"] == 3


def test_upwork_handoff_derives_rates(tmp_env):
    path = tmp_env / "upwork_daily.json"
    path.write_text(json.dumps({"date": "2026-09-22", "proposals": 4, "views": 2, "replies": 1,
                                "proposals_7d": 20, "replies_7d": 3}))
    data = sources.read_upwork_daily(path, day=date(2026, 9, 22))
    assert data["view_rate"] == 0.5 and data["reply_rate"] == 0.25
    assert data["reply_rate_7d"] == 0.15


def test_upwork_handoff_absent_is_none(tmp_env):
    assert sources.read_upwork_daily(tmp_env / "nope.json") is None


def test_an_upwork_handoff_with_no_date_is_treated_as_absent(tmp_env):
    """The guard used to be `data.get("date") and parse_day(...) != day`, so a
    file with no date short-circuited past it. The same 8 proposals and the same
    $64.50 of Connects were then written into the tracker and into the public
    post as *every* day's activity until somebody overwrote the file."""
    path = tmp_env / "upwork_daily.json"
    path.write_text(json.dumps({"proposals": 8, "connects": 430, "views": 2, "replies": 1}))
    notes = []
    assert sources.read_upwork_daily(path, day=date(2026, 9, 21), notes=notes) is None
    assert sources.read_upwork_daily(path, day=date(2026, 9, 20)) is None
    assert any("no date field" in n for n in notes)
    # With no day asked for (a raw read) the file still parses.
    assert sources.read_upwork_daily(path)["proposals"] == 8


def test_upwork_response_hours_identifies_the_room_it_measured():
    now = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
    rooms = [{"awaiting": "lorenzo", "client": "Jennifer Lawson",
              "last_message_at": (now - timedelta(hours=171)).isoformat()},
             {"awaiting": "lorenzo", "client": "RoutVox",
              "last_message_at": (now - timedelta(hours=3)).isoformat()}]
    out = sources.upwork_response(rooms, now)
    assert out["hours"] == pytest.approx(171.0, abs=0.01)
    assert out["room"] == "Jennifer Lawson"
    assert "Jennifer Lawson" in out["note"]


def test_a_stale_rooms_handoff_is_not_aged_into_a_permanent_alert():
    """Answering a room does not rewrite .tmp/upwork_rooms.json. Without a
    freshness check the same handled room keeps climbing past the 4 h line and
    fires one high-priority push per run forever."""
    now = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
    rooms = [{"awaiting": "lorenzo", "client": "Jennifer Lawson",
              "last_message_at": (now - timedelta(hours=171)).isoformat()}]
    fresh = sources.upwork_response(rooms, now, generated_at=(now - timedelta(hours=1)).isoformat())
    assert fresh["hours"] is not None and fresh["stale"] is False
    stale = sources.upwork_response(rooms, now, generated_at=(now - timedelta(hours=30)).isoformat())
    assert stale["hours"] is None and stale["stale"] is True
    assert "not measured" in stale["note"]


def test_read_upwork_rooms_file_carries_generated_at(tmp_env):
    path = tmp_env / "upwork_rooms.json"
    path.write_text(json.dumps({"generated_at": "2026-09-22T00:45:00-05:00",
                                "rooms": [{"awaiting": "lorenzo"}]}))
    payload = sources.read_upwork_rooms_file(path)
    assert payload["generated_at"] == "2026-09-22T00:45:00-05:00"
    assert len(payload["rooms"]) == 1
    assert sources.read_upwork_rooms(path) == payload["rooms"]
    assert sources.read_upwork_rooms_file(tmp_env / "nope.json") is None


# ------------------------------------------------------- the partial day
def test_day_elapsed_fraction_knows_the_day_is_not_over_at_18_00():
    """O4 runs at 18:00 CT; the send window closes at 19:00. Comparing a
    partial count against the whole day's plan printed a 72% volume ALERT on a
    day that was running exactly to plan."""
    at_18 = datetime(2026, 9, 21, 23, 0, tzinfo=timezone.utc)       # 18:00 CT
    assert sources.day_elapsed_fraction(at_18, date(2026, 9, 21)) == pytest.approx(11 / 12.0)
    at_0730 = datetime(2026, 9, 21, 12, 30, tzinfo=timezone.utc)    # 07:30 CT
    assert sources.day_elapsed_fraction(at_0730, date(2026, 9, 21)) == pytest.approx(0.5 / 12.0)
    # yesterday is finished, tomorrow has not started
    assert sources.day_elapsed_fraction(at_18, date(2026, 9, 20)) == 1.0
    assert sources.day_elapsed_fraction(at_18, date(2026, 9, 22)) == 0.0


def test_the_worst_inbox_is_named_even_when_the_aggregate_is_green():
    """Section 6's action on bounce rate is per inbox ("> 2% remove inbox")."""
    rows = [{"date": "2026-09-21", "email_account": "bad@x.com", "sent": 150, "bounced": 12}]
    rows += [{"date": "2026-09-21", "email_account": "ok%d@x.com" % i, "sent": 150, "bounced": 0}
             for i in range(11)]
    aggregate = sources.summarize_account_rows(rows)
    assert sources.ratio(aggregate["bounced"], aggregate["sent"]) == pytest.approx(0.0067, abs=0.001)
    worst = sources.worst_bounce_inbox(rows)
    assert worst["email"] == "bad@x.com" and worst["bounce_rate"] == pytest.approx(0.08)
    # An inbox with almost no sends is noise, not a removal signal.
    assert sources.worst_bounce_inbox(
        [{"date": "2026-09-21", "email_account": "new@x.com", "sent": 8, "bounced": 1}]) is None


def test_upwork_response_hours_uses_the_worst_waiting_room():
    now = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
    rooms = [
        {"awaiting": "lorenzo", "last_message_at": (now - timedelta(hours=3)).isoformat()},
        {"awaiting": "lorenzo", "last_message_at": (now - timedelta(hours=30)).isoformat()},
        {"awaiting": "client", "last_message_at": (now - timedelta(hours=99)).isoformat()},
    ]
    assert sources.upwork_response_hours(rooms, now) == pytest.approx(30.0, abs=0.01)
    assert sources.upwork_response_hours([], now) is None


# --------------------------------------------------------------------- GHL
def test_ghl_stage_counts_is_none_without_a_token():
    from shared.ghl import GHL

    notes = []
    assert sources.ghl_stage_counts(GHL(token=None), notes=notes) is None
    assert any("ghl_token_missing" in n for n in notes)


def test_ghl_stage_counts_maps_stage_ids_to_names():
    stages = sources.settings.GHL_STAGES

    class Fake(object):
        def search_opportunities(self, **kwargs):
            return {"opportunities": [
                {"pipelineStageId": stages["proposal_sent"]},
                {"pipelineStageId": stages["proposal_sent"]},
                {"pipelineStageId": stages["won"]},
            ]}

    out = sources.ghl_stage_counts(Fake())
    counts = out["stages"]
    assert counts["proposal_sent"] == 2 and counts["won"] == 1 and counts["lost"] == 0
    assert out["complete"] is True
    # No opportunity carries a stage-change timestamp, so there is no dated flow
    # to write into the tracker's daily columns.
    assert out["dated"] is None


def test_stage_occupancy_and_dated_transitions_are_different_answers():
    """A census is not a flow. Four opportunities parked in Won is not "four
    closed today", and the tracker's Closes column is summed across days."""
    stages = sources.settings.GHL_STAGES

    class Fake(object):
        def search_opportunities(self, **kwargs):
            return {"opportunities": [
                {"id": "o1", "pipelineStageId": stages["won"],
                 "lastStageChangeAt": "2026-09-21T15:00:00+00:00"},      # today
                {"id": "o2", "pipelineStageId": stages["won"],
                 "lastStageChangeAt": "2026-08-30T15:00:00+00:00"},      # a month ago
                {"id": "o3", "pipelineStageId": stages["proposal_sent"],
                 "lastStageChangeAt": "2026-09-10T15:00:00+00:00"},
            ]}

    out = sources.ghl_stage_counts(Fake(), day=date(2026, 9, 21))
    assert out["stages"]["won"] == 2          # two sit in Won
    assert out["dated"]["won"] == 1           # one got there today
    assert out["dated"]["proposal_sent"] == 0
    assert out["dated_field"] == "lastStageChangeAt"


def test_ops4_an_edit_only_updated_at_is_never_written_as_a_close_or_a_proposal():
    """Two August Won deals and an August proposal, edited on the run day:
    the updatedAt fallback wrote {won: 2, proposal_sent: 1} into the flow
    columns, and the retro showed a phantom $10,000 week."""
    stages = sources.settings.GHL_STAGES
    edited = [
        {"id": "o1", "pipelineStageId": stages["won"], "monetaryValue": 6000,
         "updatedAt": "2026-09-21T15:00:00+00:00"},
        {"id": "o2", "pipelineStageId": stages["won"], "monetaryValue": 4000,
         "updatedAt": "2026-09-21T15:00:05+00:00"},
        {"id": "o3", "pipelineStageId": stages["proposal_sent"],
         "updatedAt": "2026-09-21T15:00:09+00:00"},
    ]

    class Fake(object):
        def __init__(self, rows):
            self.rows = rows

        def search_opportunities(self, **kwargs):
            return {"opportunities": self.rows}

    notes = []
    out = sources.ghl_stage_counts(Fake(edited), day=date(2026, 9, 21), notes=notes)
    assert out["dated"] is None                              # blank, with a note
    assert any("lastStageChangeAt" in n for n in notes)
    from jobs import daily_metrics
    written = daily_metrics.measured_metrics({
        "today": {}, "engine": {}, "complete": True, "ghl_stages": out})
    assert "Closes" not in written and "Proposals Sent" not in written

    # August moves edited today: dated correctly, nothing today
    dated = [dict(edited[0], lastStageChangeAt="2026-08-10T15:00:00+00:00"),
             dict(edited[1], lastStatusChangeAt="2026-08-11T15:00:00+00:00"),
             dict(edited[2], lastStageChangeAt="2026-08-12T15:00:00+00:00")]
    out = sources.ghl_stage_counts(Fake(dated), day=date(2026, 9, 21))
    assert out["dated"]["won"] == 0 and out["dated"]["proposal_sent"] == 0

    # a proposal with only an edit time among dated ones: that column is blank
    notes = []
    out = sources.ghl_stage_counts(Fake(dated[:2] + [edited[2]]), day=date(2026, 9, 21),
                                   notes=notes)
    assert out["dated"]["proposal_sent"] is None and out["dated"]["won"] == 0
    assert any("left blank" in n for n in notes)


def test_ghl_stage_counts_follows_the_cursor_and_says_when_it_is_truncated():
    """shared.ghl.search_opportunities takes start_after_id precisely because a
    single page stops at 100 opportunities. Reporting a capped count as if it
    were the pipeline is how a stage silently shrinks."""
    stages = sources.settings.GHL_STAGES
    pages = []

    class Paged(object):
        def search_opportunities(self, **kwargs):
            pages.append(kwargs.get("start_after_id"))
            if len(pages) == 1:
                return {"opportunities": [
                    {"id": "o%d" % i, "pipelineStageId": stages["won"]} for i in range(3)]}
            return {"opportunities": [{"id": "z1", "pipelineStageId": stages["won"]}]}

    out = sources.ghl_stage_counts(Paged(), page_limit=3)
    assert pages == [None, "o2"]              # the second call continued from the last id
    assert out["stages"]["won"] == 4 and out["pages"] == 2 and out["complete"] is True

    class Endless(object):
        def search_opportunities(self, **kwargs):
            return {"opportunities": [
                {"id": "x%d" % i, "pipelineStageId": stages["won"]} for i in range(2)]}

    notes = []
    out = sources.ghl_stage_counts(Endless(), page_limit=2, max_pages=3, notes=notes)
    assert out["complete"] is False
    assert any("truncated" in n for n in notes)


# ------------------------------------------------------------ engine signals
class MemStore(object):
    def __init__(self, data=None):
        self.data = dict(data or {})

    def items(self, prefix=""):
        return [(k, v) for k, v in self.data.items() if k.startswith(prefix)]


def job_row(ts, job, status, details=None):
    return {"ts_utc": ts, "job": job, "status": status, "mode": "shadow",
            "details": json.dumps(details or {}), "details_parsed": details or {}}


def test_engine_metrics_counts_drafts_and_bookings_on_the_central_day():
    day = date(2026, 9, 22)
    rows = [
        job_row("2026-09-22T14:00:00+00:00", "reply_engine.approval", "would_send"),
        job_row("2026-09-22T15:00:00+00:00", "reply_engine.approval", "sent"),
        job_row("2026-09-22T16:00:00+00:00", "reply_engine.approval", "created"),
        job_row("2026-09-21T14:00:00+00:00", "reply_engine.approval", "sent"),   # yesterday
    ]
    store = MemStore({
        "appointment:a1": {"booked_at": "2026-09-22T18:00:00+00:00", "start": "2026-09-24T20:00:00+00:00"},
        "appointment:a2": {"booked_at": "2026-09-20T18:00:00+00:00"},
        "noshow_state:a3": {"state": "showed", "start_iso": "2026-09-22T17:00:00+00:00"},
        "noshow_state:a4": {"state": "no_show", "start_iso": "2026-09-22T19:00:00+00:00"},
    })
    out = sources.engine_metrics(rows, store, day)
    assert out["drafts_sent"] == 2 and out["drafts_would_send"] == 1 and out["drafts_created"] == 1
    assert out["calls_booked"] == 1
    assert out["calls_held"] == 1 and out["no_shows"] == 1
    assert out["show_rate"] == pytest.approx(0.5)


def test_show_rate_is_none_when_no_call_has_a_verdict():
    store = MemStore({"noshow_state:a1": {"state": "pending", "start_iso": "2026-09-22T17:00:00+00:00"}})
    out = sources.engine_metrics([], store, date(2026, 9, 22))
    assert out["calls_on_day"] == 1
    assert out["show_rate"] is None and out["calls_held"] is None


def test_engine_metrics_scopes_the_engine_signal_to_the_day():
    """`appointments_known` counts every appointment the store has ever held.
    One booking from August made the job believe the engine had run today."""
    store = MemStore({"appointment:old": {"booked_at": "2026-08-01T18:00:00+00:00"}})
    out = sources.engine_metrics([], store, date(2026, 9, 21))
    assert out["appointments_known"] == 1
    assert out["artifacts_on_day"] is False
    assert out["booked_on_day"] == 0 and out["engine_rows_on_day"] == 0
    assert out["process_events_on_day"] == 0


def test_show_rate_over_a_window_needs_a_minimum_sample():
    """Section 6's 90/80 lines are sized for a weekly cohort. On a one-call day
    the metric can only be 0% or 100%, and one no-show pushed a show-rate
    emergency."""
    one_call = MemStore({"noshow_state:a1": {"state": "no_show",
                                             "start_iso": "2026-09-21T17:00:00+00:00"}})
    out = sources.show_rate_range(one_call, date(2026, 9, 15), date(2026, 9, 21))
    assert out["decided"] == 1 and out["rate"] is None and out["enough"] is False

    week = MemStore(dict(
        ("noshow_state:a%d" % i,
         {"state": "showed" if i < 4 else "no_show",
          "start_iso": "2026-09-%02dT17:00:00+00:00" % (15 + i)})
        for i in range(5)))
    out = sources.show_rate_range(week, date(2026, 9, 15), date(2026, 9, 21))
    assert out["decided"] == 5 and out["rate"] == pytest.approx(0.8)


def test_no_show_rebooked_counts_both_shapes_the_engine_writes():
    """no_show.py records a rebooking two ways: a reschedule resets the state to
    pending with previous_state=no_show, and cancel_recovery_for_rebooking
    writes state=done with done_reason=rebooked."""
    store = MemStore({
        "noshow_state:a1": {"state": "done", "done_reason": "rebooked",
                            "start_iso": "2026-09-16T17:00:00+00:00"},
        "noshow_state:a2": {"state": "pending", "previous_state": "no_show",
                            "start_iso": "2026-09-21T17:00:00+00:00",
                            "previous_start_iso": "2026-09-17T17:00:00+00:00"},
        "noshow_state:a3": {"state": "no_show", "start_iso": "2026-09-18T17:00:00+00:00"},
        "noshow_state:a4": {"state": "showed", "start_iso": "2026-09-18T18:00:00+00:00"},
    })
    out = sources.no_show_rebooked_range(store, date(2026, 9, 15), date(2026, 9, 21))
    assert out["no_shows"] == 3 and out["rebooked"] == 2
    assert out["rate"] == pytest.approx(2 / 3.0)


def test_bookings_in_range_counts_the_window_not_the_store():
    store = MemStore({
        "appointment:a1": {"booked_at": "2026-09-16T18:00:00+00:00"},
        "appointment:a2": {"booked_at": "2026-09-21T18:00:00+00:00"},
        "appointment:old": {"booked_at": "2026-08-01T18:00:00+00:00"},
    })
    assert sources.bookings_in_range(store, date(2026, 9, 15), date(2026, 9, 21)) == 2


def test_positive_replies_over_a_window_covers_every_day_in_it():
    """The KPI divides by a seven-day send total, so the numerator has to cover
    the same seven days: one day's positives over the week's sends understated
    the rate about sevenfold and printed a false ALERT."""
    rows = []
    for offset in range(7):
        rows.append(job_row("2026-09-%02dT14:00:00+00:00" % (15 + offset),
                            "reply_engine.process_event", "ok", {"label": "positive_interested"}))
        rows.append(job_row("2026-09-%02dT15:00:00+00:00" % (15 + offset),
                            "reply_engine.process_event", "ok", {"label": "positive_booking"}))
    assert sources.positive_replies(rows, date(2026, 9, 21)) == 2
    assert sources.positive_replies_range(rows, date(2026, 9, 15), date(2026, 9, 21)) == 14
    assert sources.positive_replies_range([], date(2026, 9, 15), date(2026, 9, 21)) is None


def test_positive_replies_is_none_when_the_engine_never_ran():
    day = date(2026, 9, 22)
    assert sources.positive_replies([], day) is None
    rows = [job_row("2026-09-22T14:00:00+00:00", "reply_engine.process_event", "ok",
                    {"label": "positive_interested"}),
            job_row("2026-09-22T14:05:00+00:00", "reply_engine.process_event", "ok",
                    {"label": "not_interested"})]
    assert sources.positive_replies(rows, day) == 1


def test_first_reply_minutes_is_the_median_and_none_without_timestamps():
    """OPS-10: reply landed -> reply SENT, from the sent row (or its created
    row by approval id). A created row alone is draft-queued, the wrong
    interval, and a shadow would_send is not a send."""
    day = date(2026, 9, 22)
    rows = [
        job_row("2026-09-22T14:10:00+00:00", "reply_engine.approval", "sent",
                {"approval": "a1", "reply_at": "2026-09-22T14:00:00+00:00"}),
        job_row("2026-09-22T15:02:00+00:00", "reply_engine.approval", "created",
                {"approval": "a2", "reply_at": "2026-09-22T15:00:00+00:00"}),
        job_row("2026-09-22T15:04:00+00:00", "reply_engine.approval", "sent", {"approval": "a2"}),
    ]
    assert sources.first_reply_minutes(rows, day) == pytest.approx(7.0)
    # created alone (draft queued) never counts, whatever it carries
    assert sources.first_reply_minutes(
        [job_row("2026-09-22T14:10:00+00:00", "reply_engine.approval", "created",
                 {"approval": "a1", "reply_at": "2026-09-22T14:00:00+00:00"})], day) is None
    # a shadow would_send is not a reply sent
    assert sources.first_reply_minutes(
        [job_row("2026-09-22T14:10:00+00:00", "reply_engine.approval", "would_send",
                 {"reply_at": "2026-09-22T14:00:00+00:00"})], day) is None
    # a send with no recorded reply time is skipped, not estimated
    assert sources.first_reply_minutes(
        [job_row("2026-09-22T14:10:00+00:00", "reply_engine.approval", "sent")], day) is None


def test_ops14_positives_are_counted_per_lead_not_per_event():
    day = date(2026, 9, 22)
    rows = [job_row("2026-09-22T14:00:00+00:00", "reply_engine.process_event", "ok",
                    {"label": "positive_interested", "lead": "a@x.com"}),
            job_row("2026-09-22T15:00:00+00:00", "reply_engine.process_event", "ok",
                    {"label": "positive_booking", "lead": "A@x.com"}),
            job_row("2026-09-22T16:00:00+00:00", "reply_engine.process_event", "ok",
                    {"label": "positive_interested", "lead": "b@x.com"})]
    assert sources.positive_replies(rows, day) == 2


def test_read_job_log_parses_details_and_survives_a_missing_file(tmp_env):
    assert sources.read_job_log(tmp_env / "nope.csv") == []
    path = tmp_env / "job_log.csv"
    path.write_text("ts_utc,job,status,mode,details\n"
                    "2026-09-22T14:00:00+00:00,x,ok,shadow,\"{\"\"a\"\": 1}\"\n")
    rows = sources.read_job_log(path)
    assert rows[0]["details_parsed"] == {"a": 1}


def test_ops9_carried_rooms_are_judged_by_their_own_older_stamp(tmp_path):
    path = tmp_path / "upwork_rooms.json"
    path.write_text(json.dumps({
        "generated_at": "2026-09-22T12:00:00-05:00",
        "carried": {"rooms": {"generated_at": "2026-09-20T09:00:00-05:00"}},
        "rooms": [{"client": "X", "awaiting": "you", "last_message_at": "2026-09-19T12:00:00+00:00"}],
    }), encoding="utf-8")
    payload = sources.read_upwork_rooms_file(path)
    assert payload["generated_at"] == "2026-09-20T09:00:00-05:00"
