"""services/metrics/kpi.py: the Section 6 dashboard."""
from datetime import date, datetime, timezone

import pytest

from services.metrics import kpi

DAY = date(2026, 9, 22)
NOW = datetime(2026, 9, 22, 23, 0, tzinfo=timezone.utc)


def rows_for(snapshot, prior=None):
    return dict((r["metric"], r) for r in kpi.build(snapshot, prior))


def test_every_section_6_metric_has_a_row():
    rows = rows_for({})
    assert len(rows) == 13
    for name in ("Sends/day vs plan", "Warm-up health per inbox", "Bounce rate",
                 "Real reply rate", "Positive reply rate", "Time to first reply",
                 "Positive to booked", "Show rate", "No-show rebooked",
                 "Proposal to close", "Upwork reply rate", "Upwork response time",
                 "Cost per verified lead"):
        assert name in rows


def test_a_metric_with_no_value_is_no_data_never_green():
    rows = rows_for({})
    assert all(r["state"] == kpi.NO_DATA for r in rows.values())
    assert all(r["value_text"] == "-" for r in rows.values())


def test_higher_is_better_thresholds():
    assert kpi.state_of(0.95, 0.90, 0.80, True) == kpi.GREEN
    assert kpi.state_of(0.85, 0.90, 0.80, True) == kpi.WATCH
    assert kpi.state_of(0.79, 0.90, 0.80, True) == kpi.ALERT


def test_lower_is_better_thresholds_are_not_inverted():
    """Bounce rate, response time and cost per lead are all "lower is better".
    Reading one of them with the higher-is-better rule turns a red into a green."""
    assert kpi.state_of(0.008, 0.01, 0.02, False) == kpi.GREEN
    assert kpi.state_of(0.015, 0.01, 0.02, False) == kpi.WATCH
    assert kpi.state_of(0.025, 0.01, 0.02, False) == kpi.ALERT


def test_the_measured_week_reads_as_the_live_numbers_do():
    rows = rows_for({"sends_vs_plan": 1.0, "warmup_worst": 100.0,
                     "bounce_rate": 0.0111, "real_reply_rate": 0.0106})
    assert rows["Sends/day vs plan"]["state"] == kpi.GREEN
    assert rows["Warm-up health per inbox"]["state"] == kpi.GREEN
    assert rows["Real reply rate"]["state"] == kpi.GREEN     # 1.06% clears the 1% line
    assert rows["Bounce rate"]["state"] == kpi.WATCH         # 1.11% is over green, under the 2% alert


def test_thresholds_are_rendered_with_their_direction():
    rows = rows_for({})
    assert rows["Real reply rate"]["green_text"] == ">= 1.0%"
    assert rows["Bounce rate"]["green_text"] == "<= 1.0%"
    assert rows["Bounce rate"]["alert_text"] == "> 2.0%"
    assert rows["Upwork response time"]["green_text"] == "<= 1.0 h"
    assert rows["Cost per verified lead"]["green_text"] == "<= $0.0200"


def test_trend_says_better_or_worse_not_up_or_down():
    rows = rows_for({"bounce_rate": 0.005}, {"bounce_rate": 0.02})
    assert "better" in rows["Bounce rate"]["trend"] and "↓" in rows["Bounce rate"]["trend"]
    rows = rows_for({"real_reply_rate": 0.005}, {"real_reply_rate": 0.02})
    assert "worse" in rows["Real reply rate"]["trend"]
    assert rows_for({"bounce_rate": 0.01}, {"bounce_rate": 0.01})["Bounce rate"]["trend"] == "flat"
    assert rows_for({"bounce_rate": 0.01})["Bounce rate"]["trend"] == "-"


def test_headline_names_what_is_off_and_what_is_missing():
    rows = kpi.build({"bounce_rate": 0.05, "real_reply_rate": 0.02})
    line = kpi.headline(rows)
    assert line.startswith("OFF: Bounce rate")
    assert "no data: 11 of 13" in line
    assert kpi.headline(kpi.build({"real_reply_rate": 0.02})).startswith("Nothing in alert")


def test_render_is_one_markdown_block_with_the_gaps_explained():
    text = kpi.render(kpi.build({"real_reply_rate": 0.0106}), DAY, NOW)
    assert text.startswith("# KPI dashboard 2026-09-22")
    assert "North star: discovery calls held per week." in text
    assert "| Metric | Green | Alert | Value | Window | vs last week | State |" in text
    assert "Not measured yet:" in text
    assert "- Show rate: GHL appointment status" in text


def test_render_shows_a_source_note_when_one_is_given():
    text = kpi.render(kpi.build({"show_rate_note": "no GHL token yet"}), DAY, NOW)
    assert "(no GHL token yet)" in text


def test_ghl_rows_that_are_not_implemented_say_why_even_with_a_token():
    """The note used to be attached only when there was no token, so minting
    one would have turned these rows into unexplained blanks and sent Lorenzo
    looking for a data problem that is really a "not built yet"."""
    from jobs import daily_metrics

    stages = {"stages": {"proposal_sent": 3, "won": 4}, "dated": None,
              "dated_field": None, "complete": True, "pages": 1, "counted": 7}
    data = _snapshot_data(ghl_stages=stages)
    rows = rows_for(daily_metrics.kpi_snapshot(data))
    row = rows["Proposal to close"]
    assert row["state"] == kpi.NO_DATA        # not 133% green
    assert row["note"] and "not measured" in row["note"]
    text = kpi.render(kpi.build(daily_metrics.kpi_snapshot(data)), DAY, NOW)
    assert "Proposal to close: GHL (not measured" in text


def test_every_row_window_matches_the_window_its_value_was_computed_over():
    """A row labelled "7 days" carrying one day's numerator is how a green week
    printed ALERT and how one no-show printed a show-rate emergency."""
    from jobs import daily_metrics

    data = _snapshot_data()
    snapshot = daily_metrics.kpi_snapshot(data)
    rows = rows_for(snapshot)
    # 14 positives over the 7-day window against 1,800 sends is 0.78%, green.
    assert rows["Positive reply rate"]["window"] == "7 days"
    assert rows["Positive reply rate"]["value"] == pytest.approx(14 / 1800.0)
    assert rows["Positive reply rate"]["state"] == kpi.GREEN
    # The show rate is the same 7 days, and says how big its sample was.
    assert rows["Show rate"]["window"] == "7 days"
    assert "decided calls" in (rows["Show rate"]["note"] or "")


def test_the_campaign_breakdown_is_on_the_dashboard_not_only_in_the_json():
    text = kpi.render(kpi.build({}), DAY, NOW, campaigns=[
        {"key": "cleaning_reactivation", "sent": 50, "replies": 2, "bounced": 0},
        {"key": "recruiting_reactivation", "sent": 50, "replies": 0, "bounced": 1},
    ])
    assert "Campaigns today:" in text
    assert "| cleaning_reactivation | 50 | 2 | 0 |" in text
    assert "Campaigns today:" not in kpi.render(kpi.build({}), DAY, NOW)


def _snapshot_data(**over):
    """A collect()-shaped dict with a realistic week behind it."""
    from services.metrics import sources

    class MemStore(object):
        def __init__(self, data):
            self.data = data

        def items(self, prefix=""):
            return [(k, v) for k, v in self.data.items() if k.startswith(prefix)]

    store = MemStore(dict(
        ("noshow_state:a%d" % i,
         {"state": "showed" if i < 4 else "no_show",
          "start_iso": "2026-09-%02dT17:00:00+00:00" % (16 + i)})
        for i in range(5)))
    job_rows = []
    for offset in range(7):
        for _ in range(2):
            job_rows.append({"ts_utc": "2026-09-%02dT14:00:00+00:00" % (15 + offset),
                             "job": "reply_engine.process_event", "status": "ok",
                             "details": "{}", "details_parsed": {"label": "positive_interested"}})
    # 2026-09-20 is missing exactly as it is in the recorded pull (a Sunday with
    # no sends), so the week totals 1,800, the number measured live.
    account_rows = [{"date": "2026-09-%02d" % d, "email_account": "i%d@x.com" % i,
                     "sent": 25, "bounced": 0, "unique_replies": 0}
                    for d in range(15, 22) if d != 20 for i in range(12)]
    data = {
        "day": date(2026, 9, 21), "now": NOW, "complete": True,
        "account_complete": True, "campaign_complete": True,
        "today": sources.summarize_account_rows(
            [r for r in account_rows if r["date"] == "2026-09-21"]),
        "week": sources.summarize_account_rows(account_rows),
        "week_rows": account_rows, "prior_week": {"sent": 0, "days": []},
        "warmup": {"worst": 100.0, "below_98": [], "count": 12},
        "upwork": {}, "rooms": None, "rooms_generated_at": None, "ghl_stages": None,
        "engine": sources.engine_metrics(job_rows, store, date(2026, 9, 21)),
        "engine_seen": True, "elapsed_fraction": 1.0, "day_complete": True,
        "positives": 2, "positives_window": 14, "first_reply_minutes": None,
        "show_rate_window": sources.show_rate_range(store, date(2026, 9, 15), date(2026, 9, 21)),
        "bookings_window": sources.bookings_in_range(store, date(2026, 9, 15), date(2026, 9, 21)),
        "no_show_rebooked_window": sources.no_show_rebooked_range(
            store, date(2026, 9, 15), date(2026, 9, 21)),
        "last_reported_day": date(2026, 9, 21), "last_reported": None,
        "window": {"start": "2026-09-15", "end": "2026-09-21",
                   "prior_start": "2026-09-08", "prior_end": "2026-09-14"},
    }
    data.update(over)
    return data


def test_thresholds_agree_with_the_shared_deliverability_constants():
    """`shared/thresholds.py` (M1/O1, another brief) and this dashboard both
    read the same Section 6 table. They are separate modules on purpose -
    thresholds.py carries no alert side and no direction - but a number that
    drifts between them means the 07:00 monitor and the 18:00 dashboard
    disagree about the same inbox on the same day."""
    thresholds = pytest.importorskip("shared.thresholds")
    rows = rows_for({})
    assert rows["Warm-up health per inbox"]["green"] == thresholds.WARMUP_HEALTH_MIN_PCT
    assert rows["Real reply rate"]["green"] == pytest.approx(thresholds.REPLY_RATE_MIN_PCT / 100.0)
    assert rows["Bounce rate"]["green"] == pytest.approx(thresholds.BOUNCE_RATE_GREEN_PCT / 100.0)
    assert rows["Bounce rate"]["alert"] == pytest.approx(thresholds.BOUNCE_RATE_MAX_PCT / 100.0)
