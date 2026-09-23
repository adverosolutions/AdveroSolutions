"""The Section 6 KPI dashboard as one rendered block.

Every metric in the blueprint's "KPI dashboard and alert thresholds" table,
with its green threshold, its alert threshold, today's value and the trend
against last week, so one glance says what is off.

Two rules the whole module exists to enforce:

* **A metric with no source reads "no data", never green.** Ten of the
  thirteen rows depend on GHL, the reply engine log or a handoff file that may
  be absent; a dashboard that prints 0% and colours it green for a number
  nobody measured is worse than no dashboard.
* **The threshold and its direction live next to the metric**, so the state is
  derived, never typed. Four of the thirteen are "lower is better" (bounce
  rate, time to first reply, Upwork response time, cost per verified lead) and
  eyeballing them is how a red gets read as a green.
* **The window in the row is the window the value was computed over.** A row
  labelled "7 days" carrying one day's numerator is how a green week printed
  ALERT; every snapshot key may override its row's window with
  ``<key>_window`` and explain itself with ``<key>_note``.
"""
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

GREEN = "green"
ALERT = "ALERT"
WATCH = "watch"
NO_DATA = "no data"

PCT = "pct"
NUM = "num"
MINUTES = "minutes"
HOURS = "hours"
MONEY4 = "money4"
SCORE = "score"

# name, unit, green, alert, higher_is_better, window, source
SPEC = [
    ("Sends/day vs plan",        PCT,     0.90,   0.80,  True,  "today",   "Instantly daily analytics"),
    ("Warm-up health per inbox", SCORE,   98.0,   98.0,  True,  "now",     "Warmup analytics"),
    ("Bounce rate",              PCT,     0.01,   0.02,  False, "7 days",  "Accounts analytics"),
    ("Real reply rate",          PCT,     0.01,   0.01,  True,  "7 days",  "Accounts + emails"),
    ("Positive reply rate",      PCT,     0.007,  0.005, True,  "7 days",  "Lead labels / reply engine"),
    ("Time to first reply",      MINUTES, 5.0,    60.0,  False, "today",   "Reply engine log"),
    ("Positive to booked",       PCT,     0.50,   0.40,  True,  "7 days",  "GHL pipeline"),
    ("Show rate",                PCT,     0.90,   0.80,  True,  "7 days",  "GHL appointment status"),
    ("No-show rebooked",         PCT,     0.40,   0.25,  True,  "7 days",  "GHL"),
    ("Proposal to close",        PCT,     0.30,   0.20,  True,  "7 days",  "GHL"),
    ("Upwork reply rate",        PCT,     0.15,   0.08,  True,  "7 days",  "Upwork proposals list"),
    ("Upwork response time",     HOURS,   1.0,    4.0,   False, "now",     "Rooms audit"),
    ("Cost per verified lead",   MONEY4,  0.02,   0.04,  False, "last run", "List factory ledger"),
]

# snapshot key per metric name
KEYS = {
    "Sends/day vs plan": "sends_vs_plan",
    "Warm-up health per inbox": "warmup_worst",
    "Bounce rate": "bounce_rate",
    "Real reply rate": "real_reply_rate",
    "Positive reply rate": "positive_reply_rate",
    "Time to first reply": "first_reply_minutes",
    "Positive to booked": "positive_to_booked",
    "Show rate": "show_rate",
    "No-show rebooked": "no_show_rebooked",
    "Proposal to close": "proposal_to_close",
    "Upwork reply rate": "upwork_reply_rate",
    "Upwork response time": "upwork_response_hours",
    "Cost per verified lead": "cost_per_verified_lead",
}


# Rows whose Section 6 alert is sustained, not instant: "Positive reply rate
# < 0.5% for 3 days". One reading below the line is WATCH; the row goes to
# ALERT only when the snapshot says the rate was under the alert line on this
# many consecutive days (``<key>_alert_days``). Without that count the row
# cannot prove three days and stays WATCH: a high-priority push on one dip is
# how an alert stops being read.
SUSTAIN_DAYS = {
    "Positive reply rate": 3,
}


def alert_threshold(name: str) -> Optional[float]:
    for row in SPEC:
        if row[0] == name:
            return row[3]
    return None


def fmt(value: Optional[float], unit: str) -> str:
    if value is None:
        return "-"
    if unit == PCT:
        return "{:.1f}%".format(value * 100.0)
    if unit == SCORE:
        return "{:.0f}".format(value)
    if unit == MINUTES:
        return "{:.0f} min".format(value)
    if unit == HOURS:
        return "{:.1f} h".format(value)
    if unit == MONEY4:
        return "${:,.4f}".format(value)
    return "{:,.2f}".format(value)


def state_of(value: Optional[float], green: float, alert: float, higher_is_better: bool) -> str:
    if value is None:
        return NO_DATA
    if higher_is_better:
        if value >= green:
            return GREEN
        if value < alert:
            return ALERT
        return WATCH
    if value <= green:
        return GREEN
    if value > alert:
        return ALERT
    return WATCH


def trend_of(value: Optional[float], prior: Optional[float], unit: str, higher_is_better: bool) -> str:
    """"vs last week" as an arrow plus the delta, or "-" when either side is unknown."""
    if value is None or prior is None:
        return "-"
    delta = value - prior
    if unit == PCT:
        body = "{:+.1f} pts".format(delta * 100.0)
    elif unit == MONEY4:
        body = "{:+,.4f}".format(delta)
    elif unit == MINUTES:
        body = "{:+.0f} min".format(delta)
    elif unit == HOURS:
        body = "{:+.1f} h".format(delta)
    else:
        body = "{:+,.1f}".format(delta)
    if abs(delta) < 1e-9:
        return "flat"
    better = (delta > 0) == bool(higher_is_better)
    return "%s %s (%s)" % ("↑" if delta > 0 else "↓", body, "better" if better else "worse")


def threshold_text(green: float, alert: float, unit: str, higher_is_better: bool) -> Tuple[str, str]:
    if higher_is_better:
        return (">= %s" % fmt(green, unit), "< %s" % fmt(alert, unit))
    return ("<= %s" % fmt(green, unit), "> %s" % fmt(alert, unit))


def build(snapshot: Dict[str, Any], prior: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """One row per Section 6 metric, from a flat snapshot of measured values."""
    prior = prior or {}
    rows = []
    for name, unit, green, alert, higher, window, source in SPEC:
        key = KEYS[name]
        value = snapshot.get(key)
        before = prior.get(key)
        # A collector may report a different window than the default (the 07:30
        # run has no sends yet today and falls back to the last reported day).
        window = snapshot.get("%s_window" % key) or window
        green_text, alert_text = threshold_text(green, alert, unit, higher)
        state = state_of(value, green, alert, higher)
        note = snapshot.get("%s_note" % key)
        need = SUSTAIN_DAYS.get(name)
        if need and state == ALERT:
            days = snapshot.get("%s_alert_days" % key)
            if days is None or days < need:
                state = WATCH
                held = ("under the alert line on %d consecutive day(s)" % days
                        if days is not None else "the run could not count how many days in a row "
                        "it has been under the alert line")
                extra = ("%s; Section 6 alerts after %d, so this is watch" % (held, need))
                note = "%s. %s" % (note, extra) if note else extra
        rows.append({
            "metric": name,
            "unit": unit,
            "window": window,
            "source": source,
            "value": value,
            "value_text": fmt(value, unit),
            "prior": before,
            "prior_text": fmt(before, unit),
            "green": green,
            "alert": alert,
            "green_text": green_text,
            "alert_text": alert_text,
            "higher_is_better": higher,
            "state": state,
            "trend": trend_of(value, before, unit, higher),
            "note": note,
        })
    return rows


def headline(rows: List[Dict[str, Any]]) -> str:
    alerts = [r["metric"] for r in rows if r["state"] == ALERT]
    missing = [r["metric"] for r in rows if r["state"] == NO_DATA]
    if alerts:
        text = "OFF: %s" % ", ".join(alerts)
    else:
        text = "Nothing in alert"
    if missing:
        text += "  |  no data: %d of %d (%s)" % (len(missing), len(rows), ", ".join(missing))
    return text


def campaign_table(campaigns: Optional[List[Dict[str, Any]]]) -> List[str]:
    """Per-campaign sends and replies for the day.

    The job already pays for ``GET /campaigns/analytics`` on every run; before
    this the answer was parsed, summarised and then read by nothing but the
    ``--json`` dump. Section 6's verdict line is per campaign (recruiting has
    zero positives in 400 contacts, cleaning has four), so the breakdown
    belongs on the dashboard Lorenzo actually reads."""
    campaigns = [c for c in (campaigns or []) if c.get("sent") or c.get("replies")]
    if not campaigns:
        return []
    out = ["", "Campaigns today:", "", "| Campaign | Sent | Replies | Bounced |", "| --- | --- | --- | --- |"]
    for row in campaigns:
        out.append("| %s | %s | %s | %s |" % (
            row.get("key") or row.get("name") or row.get("campaign_id") or "?",
            "{:,}".format(int(row.get("sent") or 0)),
            "{:,}".format(int(row.get("replies") or 0)),
            "{:,}".format(int(row.get("bounced") or 0))))
    return out


def render(rows: List[Dict[str, Any]], day: date, now: Optional[datetime] = None,
           notes: Optional[List[str]] = None,
           campaigns: Optional[List[Dict[str, Any]]] = None) -> str:
    """The dashboard as a markdown block (also readable as plain text)."""
    stamp = now.strftime("%Y-%m-%d %H:%M %Z") if now is not None else day.isoformat()
    out = [
        "# KPI dashboard %s" % day.isoformat(),
        "",
        "North star: discovery calls held per week. Generated %s." % stamp,
        "",
        headline(rows),
        "",
        "| Metric | Green | Alert | Value | Window | vs last week | State |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        out.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            row["metric"], row["green_text"], row["alert_text"], row["value_text"],
            row["window"], row["trend"], row["state"]))
    gaps = [r for r in rows if r["state"] == NO_DATA]
    caveats = [r for r in rows if r["state"] != NO_DATA and r.get("note")]
    if caveats:
        out.append("")
        out.append("Read this way:")
        for row in caveats:
            out.append("- %s: %s" % (row["metric"], row["note"]))
    if gaps:
        out.append("")
        out.append("Not measured yet:")
        for row in gaps:
            out.append("- %s: %s%s" % (row["metric"], row["source"],
                                       (" (%s)" % row["note"]) if row.get("note") else ""))
    out.extend(campaign_table(campaigns))
    if notes:
        out.append("")
        out.append("Notes:")
        for text in notes:
            out.append("- %s" % text)
    return "\n".join(out)
