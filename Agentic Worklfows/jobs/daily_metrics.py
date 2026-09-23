"""Daily metrics and the Maker School post (Blueprint O4), 18:00 CT.

Pulls the day's numbers read-only, renders the DAILY UPDATE block in the
format the existing Daily Metrics tracker uses, writes the day's row on that
tracker and stages the Skool post. Also renders the Section 6 KPI dashboard.

Reads (all GET / local):
    Instantly  GET /campaigns/analytics (date-ranged), GET /accounts/analytics/daily
               (chunked: the workspace answers 413 without an emails filter),
               GET /accounts (warm-up scores)
    GHL        opportunities by stage, when a Private Integration token exists
    Upwork     .tmp/upwork_daily.json and .tmp/upwork_rooms.json, written by a
               Claude session that has the Upwork MCP (jobs do not)
    Engine     .tmp/job_log.csv and the store (appointment:*, noshow_state:*)

Writes (both guarded; shadow records a would_do and touches nothing):
    Google Sheets  the day's row on "AdveroSolutions - Daily Metrics"
    Skool          the DAILY UPDATE post, staged to .tmp for a session to post

The last logged day on the tracker is 2026-08-12 and the streak is zero. This
job never backfills the gap: it writes today's row only, and reports
"day N, streak 1" with the gap in the notes.

CLI (from "Agentic Worklfows/"):
    python3 jobs/daily_metrics.py --dry-run                     # live read-only pull, print, scratch Job_Log row
    python3 jobs/daily_metrics.py --now                         # same plus the guarded sheet row and staged post
    python3 jobs/daily_metrics.py --dry-run --fixtures          # offline, on the recorded September pulls
    python3 jobs/daily_metrics.py --dry-run --as-of 2026-09-21T18:00:00-05:00
    python3 jobs/daily_metrics.py --dry-run --kpi-only          # the KPI dashboard on its own

Python 3.9 compatible. ``now`` is injected, never read inside the logic.
"""
import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

if __package__ in (None, ""):  # run as a script: make "shared"/"services" importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import settings  # noqa: E402
from shared.ghl import GHL  # noqa: E402
from shared.instantly import Instantly, default_client# noqa: E402
from shared.job_log import log_run  # noqa: E402
from shared.notify import notify, topic_is_protected  # noqa: E402
from shared.paths import tmp_file  # noqa: E402
from shared.store import get_store  # noqa: E402
from services.metrics import kpi, render, sheet, skool, sources  # noqa: E402

logger = logging.getLogger("jobs.daily_metrics")

JOB = "daily_metrics"
WINDOW_DAYS = 7            # "this week" for every rate in the KPI dashboard
# Below this much of the 07:00-19:00 CT send window, today's send count divided
# by the elapsed fraction is noise, so the pace row reports the last full day.
MIN_ELAPSED_FOR_PACE = 0.25
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "services" / "metrics" / "fixtures"
# .tmp ledger written by the list factory (O8, another brief). Absent today.
LIST_LEDGER_FILE = "list_factory_ledger.json"


# --------------------------------------------------------------- collection
def collect(
    now: datetime,
    day: date,
    instantly: Optional[Instantly] = None,
    ghl: Optional[GHL] = None,
    store: Optional[Any] = None,
    account_rows: Optional[List[Dict[str, Any]]] = None,
    campaign_rows: Optional[List[Dict[str, Any]]] = None,
    accounts: Optional[Any] = None,
    upwork: Optional[Dict[str, Any]] = None,
    rooms: Optional[List[Dict[str, Any]]] = None,
    job_rows: Optional[List[Dict[str, Any]]] = None,
    job_log_path: Optional[Any] = None,
    window_days: int = WINDOW_DAYS,
    notes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Everything the day needs, read-only. Inject any argument to skip its pull."""
    notes = notes if notes is not None else []
    # Completeness is tracked per source. It used to be one flag, so a 500 on
    # GET /campaigns/analytics withheld the day's send count even though
    # GET /accounts/analytics/daily had answered cleanly: the tracker row ended
    # up with no numeric cell at all, the "Logged" formula stayed 0, the streak
    # broke and the post read "n/a sent" for a 300-send day. Nothing in the
    # campaign pull feeds a written metric, so it must not be able to blank one.
    account_complete = True
    campaign_complete = True
    window_start = day - timedelta(days=window_days - 1)
    prior_start = day - timedelta(days=window_days * 2 - 1)
    prior_end = day - timedelta(days=window_days)

    if account_rows is None:
        if instantly is None:
            instantly = default_client()
        account_rows, account_complete = sources.fetch_account_daily(
            instantly, sources.active_inboxes(), sources.iso(prior_start), sources.iso(day), notes=notes)
    if campaign_rows is None:
        if instantly is None:
            instantly = default_client()
        campaign_rows, campaign_complete = sources.fetch_campaign_day(
            instantly, sources.iso(day), sources.iso(day), notes=notes)
    if accounts is None and instantly is not None:
        accounts = sources.fetch_accounts(instantly, notes=notes)

    today_rows = sources.account_rows_for(account_rows, day)
    today_totals = sources.summarize_account_rows(today_rows)
    week_rows = [r for r in account_rows
                 if sources.parse_day(r.get("date")) is not None
                 and window_start <= sources.parse_day(r.get("date")) <= day]
    prior_rows = [r for r in account_rows
                  if sources.parse_day(r.get("date")) is not None
                  and prior_start <= sources.parse_day(r.get("date")) <= prior_end]
    week_totals = sources.summarize_account_rows(week_rows)
    prior_totals = sources.summarize_account_rows(prior_rows)
    campaigns = sources.summarize_campaign_rows(campaign_rows)

    # The last day Instantly has any per-inbox row for. O3 runs at 07:30 and O4
    # at 18:00; at 07:30 the day has barely started, and "0 sends today" read as
    # a volume collapse is a false alarm every single morning.
    reported_days = sorted(set(d for d in (sources.parse_day(r.get("date")) for r in account_rows)
                               if d is not None and d <= day))
    last_reported_day = reported_days[-1] if reported_days else None
    last_reported = sources.summarize_account_rows(
        sources.account_rows_for(account_rows, last_reported_day)) if last_reported_day else None
    # The last day that is definitely OVER. Early in the day the elapsed
    # fraction is small enough that a handful of sends divided by it is noise
    # (at 07:30 the window is 4% gone, so 20 sends read as 1,600% of plan), so
    # the pace row falls back to this instead.
    earlier_days = [d for d in reported_days if d < day]
    last_full_day = earlier_days[-1] if earlier_days else None
    last_full = sources.summarize_account_rows(
        sources.account_rows_for(account_rows, last_full_day)) if last_full_day else None

    if not today_rows:
        sources.note(notes, "no per-inbox analytics rows for %s yet (Instantly reports a day "
                            "once it has sends)" % sources.iso(day))

    warmup = sources.warmup_health(accounts, sources.active_inboxes())
    if upwork is None:
        upwork = sources.read_upwork_daily(day=day, notes=notes)
    if upwork is None:
        sources.note(notes, "no usable .tmp/%s for %s: Upwork columns left blank"
                     % (sources.UPWORK_DAILY_FILE, sources.iso(day)))
    rooms_meta = {}
    if rooms is None:
        payload = sources.read_upwork_rooms_file()
        rooms = None if payload is None else payload["rooms"]
        rooms_meta = payload or {}

    ghl = ghl if ghl is not None else GHL()
    stages = sources.ghl_stage_counts(ghl, day=day, notes=notes)
    if stages is not None and not stages.get("complete"):
        sources.note(notes, "the GHL pipeline read was truncated: stage counts are partial")

    store = store if store is not None else get_store()
    if job_rows is None:
        job_rows = sources.read_job_log(job_log_path)
    engine = sources.engine_metrics(job_rows, store, day, now=now)
    # Scoped to the day. ``appointments_known`` counts every appointment ever
    # stored, so a single August booking made this True forever and the job
    # wrote "Calls Booked = 0" on days the engine had not run at all.
    engine_seen = bool(engine.get("artifacts_on_day"))
    if not engine_seen:
        sources.note(notes, "the reply engine has no rows for %s: drafts, positives and "
                            "calls booked are unknown, not zero" % sources.iso(day))

    elapsed = sources.day_elapsed_fraction(now, day)
    day_complete = elapsed >= 1.0
    if today_rows and not day_complete:
        sources.note(notes, "the run is %.0f%% through the %02d:00-%02d:00 CT send window, so "
                            "%s is a partial day: the plan is scaled to match and tomorrow's run "
                            "restates the final count"
                     % (elapsed * 100.0, settings.SEND_WINDOW[0], settings.SEND_WINDOW[1],
                        sources.iso(day)))

    return {
        "day": day,
        "now": now,
        "complete": account_complete and campaign_complete,
        "account_complete": account_complete,
        "campaign_complete": campaign_complete,
        "notes": notes,
        "today": today_totals,
        "today_rows": today_rows,
        "account_rows_all": account_rows,
        "week": week_totals,
        "week_rows": week_rows,
        "prior_week": prior_totals,
        "campaigns": campaigns,
        "warmup": warmup,
        "upwork": upwork or {},
        "rooms": rooms,
        "rooms_generated_at": rooms_meta.get("generated_at"),
        "ghl_stages": stages,
        "engine": engine,
        "engine_seen": engine_seen,
        "elapsed_fraction": elapsed,
        "day_complete": day_complete,
        "positives": sources.positive_replies(job_rows, day),
        "positives_window": sources.positive_replies_range(job_rows, window_start, day),
        "positive_rate_by_day": positive_rate_by_day(job_rows, account_rows, day, window_days),
        "first_reply_minutes": sources.first_reply_minutes(job_rows, day),
        "show_rate_window": sources.show_rate_range(store, window_start, day),
        "bookings_window": sources.bookings_in_range(store, window_start, day),
        "no_show_rebooked_window": sources.no_show_rebooked_range(store, window_start, day),
        "last_reported_day": last_reported_day,
        "last_reported": last_reported,
        "last_full_day": last_full_day,
        "last_full": last_full,
        "window": {"start": sources.iso(window_start), "end": sources.iso(day),
                   "prior_start": sources.iso(prior_start), "prior_end": sources.iso(prior_end)},
    }


SUSTAIN_LOOKBACK = 3


def positive_rate_by_day(job_rows: List[Dict[str, Any]], account_rows: List[Dict[str, Any]],
                         day: date, window_days: int = WINDOW_DAYS,
                         lookback: int = SUSTAIN_LOOKBACK) -> List[Dict[str, Any]]:
    """The trailing-window positive reply rate as of ``day`` and the days before.

    Section 6 alerts on "< 0.5% for 3 days", so the dashboard needs the same
    reading on each of the last three days, not one. Newest first. A day whose
    rate cannot be computed (no engine rows, no sends) is None and breaks the
    run of consecutive days: an unknown day is not evidence of a dip.
    """
    out = []  # type: List[Dict[str, Any]]
    for offset in range(lookback):
        end = day - timedelta(days=offset)
        start = end - timedelta(days=window_days - 1)
        positives = sources.positive_replies_range(job_rows, start, end)
        sent = sources.summarize_account_rows(
            [r for r in account_rows or []
             if sources.parse_day(r.get("date")) is not None
             and start <= sources.parse_day(r.get("date")) <= end]).get("sent")
        rate = sources.ratio(positives, sent) if positives is not None else None
        out.append({"day": sources.iso(end), "positives": positives, "sent": sent, "rate": rate})
    return out


def consecutive_below(readings: List[Dict[str, Any]], threshold: Optional[float]) -> Optional[int]:
    """How many of the newest readings in a row sit under ``threshold``."""
    if threshold is None or not readings:
        return None
    count = 0
    for reading in readings:
        rate = reading.get("rate")
        if rate is None or rate >= threshold:
            break
        count += 1
    return count


def measured_metrics(data: Dict[str, Any]) -> Dict[str, Any]:
    """Tracker metric names -> measured value, or absent when unknown.

    Absent is not zero. Only keys present here are written to the sheet."""
    today = data["today"]
    engine = data["engine"]
    upwork = data.get("upwork") or {}
    out = {}  # type: Dict[str, Any]

    sent = today.get("sent")
    # ``days`` is empty when Instantly has not reported the day at all. That is
    # "not yet", not "zero sends", and writing a 0 would mark the day logged and
    # poison the tracker's rolling averages and the streak.
    #
    # Gated on ``account_complete`` only: the campaign-analytics pull feeds no
    # written metric, so a failure there must not withhold a send count that was
    # measured cleanly.
    if data.get("account_complete", data["complete"]) and today.get("days") and sent is not None:
        out["Cold Emails Sent"] = sent
        out["Replies"] = today.get("replies")
        rate = sources.ratio(today.get("real_replies"), sent)
        if rate is not None:
            out["Email Reply Rate"] = rate
    # "Email View Rate" is never written: open tracking is off on all six
    # campaigns (ids.json campaign_settings_observed.open_tracking = false), so
    # a 0.0% would be a measurement of the tracking switch, not of the leads.

    # Positives are written only when the classifier itself ran that day. A
    # reply_engine.poller row (written daily in shadow) is not evidence that
    # anything was classified, and "0 positives" over a cell Lorenzo filled in
    # by hand is a deletion, not a measurement.
    if data.get("positives") is not None and engine.get("process_events_on_day"):
        out["Positive Replies"] = data["positives"]
    # Bookings are written only when the booking machinery left a trace on this
    # day (a booking, or a call whose show/no-show was decided). The engine
    # books nothing in shadow, so without this the job wrote 0 every evening.
    if engine.get("booked_on_day") or engine.get("calls_on_day"):
        out["Calls Booked"] = engine.get("booked_on_day")
    if engine.get("calls_held") is not None:
        out["Calls Held"] = engine["calls_held"]

    # "Proposals Sent" and "Closes" are FLOW columns: sheet.all_time_totals sums
    # them. GHL stage occupancy is a census ("4 opportunities sit in Won"), so
    # writing it here re-counted the same closed deals every evening and the
    # all-time total grew by that census every day. Only opportunities whose
    # stage actually changed on this CT day may be written, and today no GHL
    # token exists at all, so both columns stay absent.
    stages = data.get("ghl_stages") or {}
    dated = stages.get("dated")
    if dated is not None:
        out["Proposals Sent"] = dated.get("proposal_sent")
        out["Closes"] = dated.get("won")

    for key, name in (("proposals", "Upwork Proposals"), ("connects", "Connects Spent"),
                      ("hires", "Upwork Hires"), ("view_rate", "Upwork View Rate"),
                      ("reply_rate", "Upwork Reply Rate")):
        value = upwork.get(key)
        if value is not None:
            out[name] = value
    return dict((k, v) for k, v in out.items() if v is not None)


def kpi_snapshot(data: Dict[str, Any]) -> Dict[str, Any]:
    """Flat current-window values for the Section 6 dashboard.

    Every rate here is computed over the window its row claims. Three rows used
    to mix windows: "Positive reply rate" divided one day's positives by the
    week's sends (about a sevenfold understatement, and a false ALERT whose
    Section 6 action is "rework or kill the campaign"), "Show rate" reported a
    single day's one or two calls under a "7 days" label, and "Proposal to
    close" divided two independent stage snapshots and could print 133% green.
    """
    today, week = data["today"], data["week"]
    upwork = data.get("upwork") or {}
    window = data.get("window") or {}
    plan = sources.plan_sends_per_day()
    cost = read_list_ledger()

    # The 18:00 run sits inside the 07:00-19:00 CT send window, so comparing a
    # partial count against the whole day's plan printed 72% ALERT on a day that
    # was exactly on plan: the denominator is scaled by the elapsed fraction.
    # Early in the day that division is meaningless (at 07:30 the window is 4%
    # gone and 20 sends read as 1,600% of plan), so before MIN_ELAPSED_FOR_PACE
    # the row reports the last day that finished instead.
    elapsed = data.get("elapsed_fraction", 1.0)
    pace_today = bool(today.get("days")) and elapsed >= MIN_ELAPSED_FOR_PACE
    sends_source = today if pace_today else (data.get("last_full") or {})
    plan_so_far = plan
    if plan is not None and pace_today and elapsed < 1.0:
        plan_so_far = plan * elapsed

    show = data.get("show_rate_window") or {}
    rebooked = data.get("no_show_rebooked_window") or {}
    positives_window = data.get("positives_window")
    bookings_window = data.get("bookings_window")

    snapshot = {
        "sends_vs_plan": sources.ratio(sends_source.get("sent"), plan_so_far),
        "warmup_worst": data["warmup"].get("worst"),
        "bounce_rate": sources.ratio(week.get("bounced"), week.get("sent")),
        "real_reply_rate": sources.ratio(week.get("real_replies"), week.get("sent")),
        # Same seven days on both sides of the division.
        "positive_reply_rate": sources.ratio(positives_window, week.get("sent"))
        if positives_window is not None else None,
        "first_reply_minutes": data.get("first_reply_minutes"),
        "positive_to_booked": sources.ratio(bookings_window, positives_window)
        if positives_window else None,
        "show_rate": show.get("rate"),
        "no_show_rebooked": rebooked.get("rate"),
        # Stage occupancy cannot answer this: an opportunity that closed has
        # LEFT the Proposal Sent stage, so won / in-proposal excludes every
        # success it should contain and trends upward forever. It stays no data
        # until GHL gives us dated stage transitions.
        "proposal_to_close": None,
        "upwork_reply_rate": upwork.get("reply_rate_7d"),
        "cost_per_verified_lead": cost,
    }

    upwork_rooms = sources.upwork_response(
        data.get("rooms"), data["now"], generated_at=data.get("rooms_generated_at"))
    snapshot["upwork_response_hours"] = upwork_rooms["hours"]
    if upwork_rooms.get("note"):
        snapshot["upwork_response_hours_note"] = upwork_rooms["note"]
    elif data.get("rooms") is None:
        from shared import turned_off

        if turned_off.upwork_rooms_off():
            # The scheduled rooms digests are turned off (Lorenzo checks the
            # rooms by hand): the column is blank by design, not a failed read.
            snapshot["upwork_response_hours_note"] = "upwork rooms: %s" % turned_off.label("upwork_rooms_am")

    if not pace_today and data.get("last_full_day"):
        snapshot["sends_vs_plan_window"] = sources.iso(data["last_full_day"])
        reason = ("Instantly has no row for %s yet" % sources.iso(data["day"])
                  if not today.get("days") else
                  "%s is only %.0f%% through the send window, too early to read a pace"
                  % (sources.iso(data["day"]), elapsed * 100.0))
        snapshot["sends_vs_plan_note"] = (
            "%s, so this is %s, the last day it reported in full"
            % (reason, sources.iso(data["last_full_day"])))
    elif not pace_today:
        snapshot["sends_vs_plan"] = None
        snapshot["sends_vs_plan_note"] = (
            "no finished day to compare against yet, and %s is only %.0f%% through the send window"
            % (sources.iso(data["day"]), elapsed * 100.0))
    elif elapsed < 1.0:
        snapshot["sends_vs_plan_window"] = "today, %.0f%% of the send window" % (elapsed * 100.0)
        snapshot["sends_vs_plan_note"] = (
            "the day is not finished: %s sends against %s planned by this hour, not against the "
            "full %s" % (sends_source.get("sent"), int(plan_so_far or 0), plan))

    worst = sources.worst_bounce_inbox(data.get("week_rows") or [])
    if worst is not None and worst["bounce_rate"] is not None:
        # Section 6's action on this row is per inbox ("> 2% remove inbox") but
        # the value is the aggregate over twelve of them.
        snapshot["bounce_rate_note"] = (
            "worst inbox over the window: %s at %.1f%% (%d of %d). This row is the aggregate, so "
            "one bad inbox cannot move it far; per-inbox action is jobs/deliverability_monitor.py"
            % (worst["email"], worst["bounce_rate"] * 100.0, worst["bounced"], worst["sent"]))

    below = (data["warmup"].get("below_98") or [])
    if below:
        snapshot["warmup_worst_note"] = "below 98: %s" % ", ".join(below)

    if positives_window is not None:
        snapshot["positive_reply_rate_note"] = (
            "%d lead(s) classified positive over %s to %s against %s sends. Section 6 alerts on "
            "\"< 0.5%% for 3 days\", so one dip reads as watch"
            % (positives_window, window.get("start"), window.get("end"), week.get("sent")))
        snapshot["positive_reply_rate_alert_days"] = consecutive_below(
            data.get("positive_rate_by_day") or [], kpi.alert_threshold("Positive reply rate"))
        snapshot["positive_to_booked_note"] = (
            "from the engine's own classifications and bookings (%s booked / %s positive), not "
            "from GHL" % (bookings_window, positives_window))
    else:
        snapshot["positive_to_booked_note"] = "the reply engine has classified nothing in this window"

    if data.get("first_reply_minutes") is None:
        snapshot["first_reply_minutes_note"] = (
            "measured from the lead's reply landing to Lorenzo's reply being sent; no reply was "
            "sent on this day with the reply time recorded on it, so there is nothing to measure "
            "(the engine is in shadow and does not log the reply time yet)")
    if show.get("rate") is None:
        snapshot["show_rate_note"] = (
            "%d decided call(s) in the window, under the %d needed for a rate; a one-call day is "
            "0%% or 100%% and neither is a trend" % (show.get("decided") or 0, show.get("min_decided") or 3))
    else:
        snapshot["show_rate_note"] = "%d of %d decided calls held" % (show.get("held") or 0,
                                                                     show.get("decided") or 0)
    if rebooked.get("rate") is None:
        snapshot["no_show_rebooked_note"] = "no no-show in this window to rebook"

    # Attached whatever the token state is: with a token these rows still read
    # "no data", and a note that only appears without one sent Lorenzo chasing a
    # token that would not have fixed them.
    snapshot["proposal_to_close_note"] = (
        "not measured: GHL gives stage occupancy, not dated stage transitions, and won / "
        "in-proposal is not a conversion rate"
        if data.get("ghl_stages") is not None else
        "not measured: no GHL Private Integration token yet, and stage occupancy could not answer "
        "this even with one")
    if cost is None:
        snapshot["cost_per_verified_lead_note"] = "no .tmp/%s yet (list factory, O8)" % LIST_LEDGER_FILE
    return snapshot


def kpi_prior(data: Dict[str, Any]) -> Dict[str, Any]:
    prior = data["prior_week"]
    plan = sources.plan_sends_per_day()
    per_day = sources.ratio(prior.get("sent"), len(prior.get("days") or []) or None)
    return {
        "sends_vs_plan": sources.ratio(per_day, plan),
        "bounce_rate": sources.ratio(prior.get("bounced"), prior.get("sent")),
        "real_reply_rate": sources.ratio(prior.get("real_replies"), prior.get("sent")),
    }


def read_list_ledger(path: Optional[Path] = None) -> Optional[float]:
    """Cost per verified lead from the list factory ledger, when one exists."""
    path = path or tmp_file(LIST_LEDGER_FILE)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    value = data.get("cost_per_verified_lead")
    if value is None:
        value = sources.ratio(data.get("spend_usd"), data.get("verified_leads"))
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------- run
def run(
    now: datetime,
    dry_run: bool = True,
    day: Optional[date] = None,
    sheet_io: Optional[Any] = None,
    write_sheet: bool = True,
    post_skool: bool = True,
    stage_files: bool = True,
    **collect_kwargs
) -> Dict[str, Any]:
    """One O4 run. Read-only in --dry-run; guarded writes in --now."""
    day = day or sources.ct_day(now)
    notes = []  # type: List[str]
    data = collect(now, day, notes=notes, **collect_kwargs)

    log = None
    sheet_error = None
    try:
        log = sheet.read_daily_log(sheet_io)
    except Exception as exc:  # noqa: BLE001 - the block still renders without the sheet
        sheet_error = str(exc)[:300]
        sources.note(notes, "Daily Log unreadable (%s): streak, totals and the row write are skipped"
                     % sheet_error)

    measured = measured_metrics(data)
    schema = sheet.metric_schema()
    merged = sheet.merge_row(log, day, measured, schema)
    if merged.get("kept"):
        sources.note(notes, "kept what was already in the tracker for %s: a measured 0 does not "
                            "overwrite a number already in the cell" % ", ".join(merged["kept"]))
    if log is not None:
        streak = sheet.streak_and_day(log.logged_days(), day)
        totals = sheet.all_time_totals(log, day, schema, today=merged["render"])
        prior_totals = sheet.all_time_totals(log, day - timedelta(days=1), schema)
        if streak.get("gap_days"):
            sources.note(notes, "last logged day was %s, %d day gap: the streak restarts at 1 and "
                                "no missed day is backfilled"
                         % (streak["last_logged"].isoformat(), streak["gap_days"]))
    else:
        streak = {"day_number": None, "streak": None, "last_logged": None,
                  "gap_days": None, "restarted": False}
        totals, prior_totals = {}, {}

    # The all-time figures are summed from the rows present in the Daily Log.
    # With a 39-day gap they are not all-time at all, and this block is public
    # writing under Lorenzo's name: it says so, in the post, not only in the
    # terminal.
    gap_days = streak.get("gap_days") or 0
    post_note = None
    if gap_days:
        post_note = ("Totals below count the %s days logged in the tracker. %d days since %s "
                     "were never logged, so they are not in them."
                     % (render.fmt_int(streak.get("day_number")), gap_days,
                        streak["last_logged"].isoformat()))
    block = render.render_daily_update(
        day, merged["render"], totals, prior_totals,
        day_number=streak.get("day_number"), streak=streak.get("streak"),
        note=post_note, totals_are_partial=bool(gap_days))
    violations = render.copy_violations(block)
    if violations:
        sources.note(notes, "copy rules: %s" % ", ".join(violations))

    rows = kpi.build(kpi_snapshot(data), kpi_prior(data))
    # The run notes are printed once, by the CLI and the Job_Log row. Only the
    # "not measured yet" reasons belong inside the dashboard block.
    dashboard = kpi.render(rows, day, now, campaigns=data["campaigns"]["campaigns"])

    staged = {}
    if stage_files:
        staged = write_stage_files(day, block, dashboard, dry_run=dry_run)

    sheet_result = None
    skool_result = None
    restated = None
    if not dry_run:
        if write_sheet and log is not None:
            sheet_result = sheet.write_day(
                day, merged["write"], log.existing(day), log.row_for(day),
                io=sheet_io, schema=schema)
            restated = restate_previous_day(data, log, schema, io=sheet_io, notes=notes)
        elif write_sheet:
            sheet_result = {"ok": False, "reason": "daily_log_unreadable", "error": sheet_error}
        if post_skool:
            skool_result = skool.post(day, block)

    alerts = [r for r in rows if r["state"] == kpi.ALERT]
    stages = data.get("ghl_stages") or {}
    degraded = (not data["complete"]) or bool(violations) or (log is None) or \
        bool(sheet_result and not sheet_result.get("ok")) or \
        (bool(stages) and not stages.get("complete"))
    if dry_run:
        status = "dry_run_partial" if degraded else "dry_run"
    else:
        status = "partial" if degraded else "ok"

    log_run(JOB, status, {
        "as_of": now.isoformat(),
        "date": day.isoformat(),
        "measured": measured,
        "sent": data["today"].get("sent"),
        "replies": data["today"].get("replies"),
        "real_replies": data["today"].get("real_replies"),
        "day_number": streak.get("day_number"),
        "streak": streak.get("streak"),
        "gap_days": streak.get("gap_days"),
        "kpi_alerts": [r["metric"] for r in alerts],
        # The metric name alone does not say which inbox or which room, and
        # Section 6's action on both of those rows names one.
        "kpi_alert_detail": [alert_line(r) for r in alerts],
        "kpi_no_data": [r["metric"] for r in rows if r["state"] == kpi.NO_DATA],
        "day_complete": data.get("day_complete"),
        "warmup_below_98": data["warmup"].get("below_98"),
        "kept_manual": merged.get("kept"),
        "sheet": {"ok": bool(sheet_result and sheet_result.get("ok")),
                  "range": (sheet_result or {}).get("range")} if sheet_result else None,
        "restated": restated,
        "skool": {"posted": bool(skool_result and skool_result.get("posted")),
                  "reason": (skool_result or {}).get("reason")} if skool_result else None,
        "notes": notes,
        "staged": staged,
    })

    notified = None
    if not dry_run and (degraded or alerts):
        title = "Daily metrics: %d KPI alert(s)" % len(alerts) if alerts else "Daily metrics: partial run"
        detail = "\n".join([alert_line(r) for r in alerts] + ["note: %s" % n for n in notes])
        detail = detail or "see the Job_Log row"
        notified = notify(title, push_message(alerts, notes, detail),
                          priority="high" if alerts else "default", tags=["bar_chart"],
                          email_message=detail)

    return {
        "job": JOB, "as_of": now.isoformat(), "date": day.isoformat(),
        "mode": settings.get_mode(), "dry_run": dry_run, "status": status,
        "block": block, "dashboard": dashboard, "kpi": rows,
        "measured": measured, "render_values": merged["render"], "write_values": merged["write"],
        "kept_manual": merged.get("kept"),
        "streak": dict(streak, last_logged=streak["last_logged"].isoformat() if streak.get("last_logged") else None),
        "totals": totals, "notes": notes, "staged": staged,
        "sheet": sheet_result, "restated": restated,
        "skool": skool_result, "notified": notified,
        "degraded": degraded, "data": summarize_for_json(data),
    }


def push_message(alerts: List[Dict[str, Any]], notes: List[str], detail: str) -> str:
    """The ntfy body. Counts only unless the topic is protected.

    An alert line carries its row note, and those notes name things: the
    Upwork row names the client whose room is waiting ("the longest wait is
    <name> (171 h)"), the bounce row names an inbox. The default ntfy topic is
    readable by anyone who knows it, so on an unprotected topic the card says
    how many alerts and notes there are and the detail goes by email only.
    """
    if topic_is_protected():
        return detail
    bits = ["%d KPI alert(s)" % len(alerts), "%d run note(s)" % len(notes)]
    return ("%s.\nThe detail went by email: this ntfy topic is public, so metric notes (which "
            "can name a client or an inbox) are withheld here. Set NTFY_TOKEN to see them on "
            "the card." % ", ".join(bits))


def alert_line(row: Dict[str, Any]) -> str:
    """One alert as a human reads it: the metric, the value, and which thing.

    "Warm-up health per inbox 97 (green >= 98)" tells Lorenzo to pause an inbox
    without telling him which one; the row's note carries the address."""
    text = "%s %s (green %s)" % (row["metric"], row["value_text"], row["green_text"])
    if row.get("note"):
        text += " - %s" % row["note"]
    return text


def restate_previous_day(
    data: Dict[str, Any],
    log: Any,
    schema: Any,
    io: Optional[Any] = None,
    notes: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Rewrite yesterday's send count now that the day is over.

    O4 runs at 18:00 CT and the send window closes at 19:00, so the row it
    writes is always short by whatever goes out in that last hour, and nothing
    ever revisited it: the tracker's daily counts and its all-time total stayed
    permanently under the truth. The next evening's run has the finished day in
    the same analytics pull it already made, so it restates it before writing
    its own row. Only the three analytics-derived cells are touched; every
    manual cell is carried through untouched by ``sheet.row_values``."""
    previous = data["day"] - timedelta(days=1)
    rows = sources.account_rows_for(data.get("account_rows_all") or [], previous)
    if not rows:
        return None
    existing = log.existing(previous)
    current = existing.get("Cold Emails Sent")
    # A restatement corrects a row the 18:00 run wrote. It never creates one:
    # a day nobody logged is a gap, and filling it here backfilled the tracker
    # and repaired the public streak for a day Lorenzo never posted.
    if not log.is_logged(previous) or current in (None, ""):
        sources.note(notes, "%s was not restated: it was never logged, and this job does not "
                            "backfill a missed day" % sources.iso(previous))
        return None
    totals = sources.summarize_account_rows(rows)
    write = {"Cold Emails Sent": totals["sent"], "Replies": totals["replies"]}
    rate = sources.ratio(totals["real_replies"], totals["sent"])
    if rate is not None:
        write["Email Reply Rate"] = rate
    try:
        unchanged = current not in (None, "") and float(current) == float(totals["sent"])
    except (TypeError, ValueError):
        unchanged = False
    if unchanged:
        return None
    result = sheet.write_day(previous, write, existing, log.row_for(previous),
                             io=io, schema=schema)
    sources.note(notes, "restated %s: %s sends (the 18:00 run could only see part of that day)"
                 % (sources.iso(previous), totals["sent"]))
    return {"date": previous.isoformat(), "sent": totals["sent"],
            "was": current, "ok": bool(result.get("ok")), "range": result.get("range")}


def summarize_for_json(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "today": data["today"], "week": data["week"], "prior_week": data["prior_week"],
        "campaigns": data["campaigns"]["campaigns"], "campaign_totals": data["campaigns"]["totals"],
        "warmup": {"worst": data["warmup"].get("worst"), "count": data["warmup"].get("count"),
                   "below_98": data["warmup"].get("below_98")},
        "ghl_stages": data.get("ghl_stages"), "engine": data.get("engine"),
        "upwork": data.get("upwork"), "window": data.get("window"), "complete": data["complete"],
    }


def write_stage_files(day: date, block: str, dashboard: str,
                      dry_run: bool = False) -> Dict[str, str]:
    """Stage the block and the dashboard in .tmp for Lorenzo.

    A dry run writes to its own ``.dryrun`` files. It used to write the same
    names as a ``--now`` run, so previewing a day replaced the artifact the real
    run had produced, swapping measured numbers for n/a with nothing to say it
    had happened."""
    suffix = ".dryrun" if dry_run else ""
    paths = {}
    for name, text in (("daily_update_%s%s.txt" % (day.isoformat(), suffix), block),
                       ("kpi_dashboard_%s%s.md" % (day.isoformat(), suffix), dashboard)):
        path = tmp_file(name)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text.rstrip() + "\n")
            paths[name.split("_")[0]] = str(path)
        except OSError as exc:
            logger.warning("could not write %s: %s", path, exc)
    return paths


# ----------------------------------------------------------------- fixtures
def load_fixtures(directory: Path = FIXTURES_DIR) -> Dict[str, Any]:
    def _load(name):
        with open(directory / name, "r", encoding="utf-8") as fh:
            return json.load(fh)

    return {
        "account_rows": _load("instantly_daily_account_2026-09-08_21.json"),
        "campaign_rows": _load("instantly_campaign_analytics_2026-09-21.json"),
        "accounts": _load("instantly_accounts_2026-09-22.json"),
    }


class FixtureSheet(object):
    """The Daily Log as recorded on 2026-09-22 (read-only replay, no network)."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or (FIXTURES_DIR / "daily_log_2026-09-22.json")
        self.updates = []

    def get_all_values(self):
        with open(self.path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def update(self, range_name, values):
        self.updates.append((range_name, values))
        return {"updatedRange": range_name}


def _parse_as_of(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = sources.parse_ts(value)
    if parsed is None:
        raise SystemExit("--as-of must be an ISO timestamp, got %r" % value)
    return parsed


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Daily metrics, the DAILY UPDATE block and the KPI dashboard (O4)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true",
                       help="read-only pull, render, print, scratch Job_Log row; no sheet row, no post")
    group.add_argument("--now", action="store_true",
                       help="same plus the guarded sheet row and the staged Skool post")
    parser.add_argument("--as-of", help="ISO timestamp used as 'now' (replay / tests)")
    parser.add_argument("--date", help="the CT day to report (default: the CT day of --as-of)")
    parser.add_argument("--fixtures", action="store_true",
                        help="use the recorded pulls instead of the Instantly API and the sheet")
    parser.add_argument("--kpi-only", action="store_true", help="print the KPI dashboard only")
    parser.add_argument("--no-sheet", action="store_true", help="--now without the sheet row")
    parser.add_argument("--no-skool", action="store_true", help="--now without staging the post")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    # Captured BEFORE the redirect: use_scratch_logs() repoints JOB_LOG_PATH so
    # a dry run's own rows never pollute .tmp/job_log.csv, and that redirect
    # also moved the file this job READS. Every dry run was therefore blind to
    # the reply engine and printed "the reply engine has no rows" while the real
    # log held the day's positives, which is exactly the output the runbook
    # tells Lorenzo to validate the numbers against before going live.
    job_log_source = sources.job_log_read_path()
    if args.dry_run:
        from shared.job_log import use_scratch_logs

        use_scratch_logs("daily_metrics_dryrun")

    now = _parse_as_of(args.as_of)
    day = None
    if args.date:
        day = sources.parse_day(args.date)
        if day is None:
            raise SystemExit("--date must be YYYY-MM-DD, got %r" % args.date)

    kwargs = {"job_log_path": job_log_source}  # type: Dict[str, Any]
    sheet_io = None
    if args.fixtures:
        kwargs.update(load_fixtures())
        kwargs["ghl"] = GHL(token=None)
        sheet_io = FixtureSheet()

    instantly = None
    try:
        if not args.fixtures:
            # Constructed here, inside the guard, so a missing or rotated
            # INSTANTLY_API_KEY is a logged failure instead of a traceback, and
            # closed in the finally so the httpx client does not leak.
            instantly = default_client()
            kwargs["instantly"] = instantly
        result = run(now, dry_run=bool(args.dry_run), day=day, sheet_io=sheet_io,
                     write_sheet=not args.no_sheet, post_skool=not args.no_skool, **kwargs)
    except Exception as exc:  # noqa: BLE001 - a silent 18:00 job is worse than a loud one
        # default_client() raises at construction without a key, get_store() can
        # fault, a transport can die: all of it outside the per-call try blocks.
        # Without this the scheduled run exits on a traceback nobody reads, with
        # no Job_Log row and no push, and the first signal is the streak
        # breaking days later.
        log_run(JOB, "failed", {"error": "%s: %s" % (type(exc).__name__, str(exc)[:400]),
                                "as_of": now.isoformat(),
                                "date": day.isoformat() if day else None,
                                "dry_run": bool(args.dry_run)})
        detail = "%s: %s" % (type(exc).__name__, str(exc)[:300])
        notify("Daily metrics failed",
               detail if topic_is_protected() else
               "%s. The error text went by email: this ntfy topic is public." % type(exc).__name__,
               priority="high", tags=["warning"], email_message=detail)
        raise
    finally:
        for obj in (instantly, kwargs.get("ghl")):
            try:
                if obj is not None and hasattr(obj, "close"):
                    obj.close()
            except Exception:  # noqa: BLE001 - closing a client must not fail the run
                logger.warning("could not close %r", obj)
    if args.json:
        print(json.dumps(result, indent=1, default=str))
    elif args.kpi_only:
        print(result["dashboard"])
    else:
        print(result["block"])
        print()
        print(result["dashboard"])
        if result["notes"]:
            print()
            for note in result["notes"]:
                print("note: %s" % note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
