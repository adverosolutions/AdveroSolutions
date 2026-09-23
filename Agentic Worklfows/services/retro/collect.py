"""Gather one week, from live reads or from recorded fixtures.

Read-only. Nothing in this module writes anywhere, to a live system or to
disk. Every pull is wrapped: an endpoint that fails leaves its metric ``None``
with the error attached, and the packet prints the failure instead of a zero.

That last promise is load-bearing and it is enforced in three places, because
each one of them once broke it on its own:

  - ``_window_data`` passes ``None`` (not a zeroed dict) for a bucket whose
    source failed, so ``metrics.build_funnel`` leaves those rows unavailable.
    ``sum_daily`` over zero rows returns a fully-zeroed dict, which is
    indistinguishable from a real zero week, and that is what printed
    "Emails sent 0 | flat | Instantly accounts/analytics/daily" on a week where
    every read answered HTTP 500.
  - ``pull_positive_leads`` and ``pull_campaign_daily`` mark their source ok
    only when a sub-pull actually succeeded. Both used to report ok=True after
    the loop regardless, so a 429 on one lead filter silently turned three
    booked calls into zero.
  - ``pull_campaign_daily`` stores ``None`` for a campaign whose read failed,
    and ``per_campaign`` keeps it ``None``, so the Campaigns table and the
    client card print "not available" for that campaign instead of "0 sent".
  - ``standing_caveats`` copies every entry of ``week.errors`` into the
    caveats, so the dead endpoint is printed under "Read this before you trust
    a number" in the artefact Lorenzo actually reads, not only in the Job_Log.

Live calls per run (all GET, or the POST-shaped reads the library classes as
reads):
  1 x accounts/analytics/daily   both weeks in one range, 12 inboxes
  6 x campaigns/analytics/daily  one per campaign, both weeks in one range
  4 x leads/list (paginated)     the four positive interest filters
  1 x opportunities/search       only when a GHL token exists (none today)
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from shared import analytics
from shared import settings

from . import metrics as metrics_mod
from . import recaps as recaps_mod
from . import sources as sources_mod
from .weeks import Window, shift_days, windows

logger = logging.getLogger("services.retro.collect")

POSITIVE_LEAD_FILTERS = (
    "FILTER_LEAD_INTERESTED",
    "FILTER_LEAD_MEETING_BOOKED",
    "FILTER_LEAD_MEETING_COMPLETED",
    "FILTER_LEAD_CLOSED",
)
LEADS_MAX_PAGES = 20
OPPS_PAGE_LIMIT = 100
OPPS_MAX_PAGES = 20

# The Section 6 inbox rule is evaluated over a trailing window, not over the
# current partial week. At 25 sends a day an inbox has ~100-125 sends by Friday
# 16:00, where the 1% line is a single reply, so a healthy 1.2% inbox reads
# "remove" about a third of the time by chance. The retro already pulls
# last_window.start through today (about twelve calendar days at a Friday run),
# so the wider audit window costs no extra call. See ``audit_window``.

SECTION6_THRESHOLDS = [
    "bounce rate over 2% removes the inbox",
    "real reply rate under 1% after 100 sent per inbox removes the inbox",
    "positive reply rate under 0.5% for 3 days is an alert",
    "campaign verdict lines at 1,000 and 3,000 sends",
    "variants are judged at 500 sends",
]


class Week(object):
    """Everything the packet and the scorecard are rendered from."""

    def __init__(self, now, this_window, last_window):
        # type: (datetime, Window, Window) -> None
        self.now = now
        self.this_window = this_window
        self.last_window = last_window
        self.funnel = []           # type: List[metrics_mod.Metric]
        self.campaign_rows = []    # type: List[List[Any]]
        self.per_campaign = {}     # type: Dict[str, Dict[str, Dict[str, float]]]
        self.campaign_totals = []  # type: List[Dict[str, Any]]
        self.leads = []            # type: List[Dict[str, Any]]
        self.account_rows = []     # type: List[Dict[str, Any]]
        self.campaign_daily = {}   # type: Dict[str, List[Dict[str, Any]]]
        self.inbox_rows = []       # type: List[List[Any]]
        self.audit_window = this_window   # type: Window
        self.sources = {}          # type: Dict[str, sources_mod.Source]
        self.recaps = {}           # type: Dict[str, Any]
        self.changes = {}          # type: Dict[str, Any]
        self.rize = None           # type: Optional[sources_mod.Source]
        self.job_log = None        # type: Optional[sources_mod.Source]
        self.caveats = []          # type: List[str]
        self.errors = []           # type: List[str]

    def metric(self, key):
        # type: (str) -> Optional[metrics_mod.Metric]
        return metrics_mod.by_key(self.funnel).get(key)

    def as_dict(self):
        return {
            "now": self.now.isoformat(),
            "this_window": self.this_window.as_dict(),
            "last_window": self.last_window.as_dict(),
            "funnel": [m.as_dict() for m in self.funnel],
            "campaign_rows": self.campaign_rows,
            "inbox_rows": self.inbox_rows,
            "sources": dict((k, {"ok": v.ok, "reason": v.reason, "origin": v.origin})
                            for k, v in self.sources.items()),
            "recaps": {"calls": self.recaps.get("calls", []),
                       "items": len(self.recaps.get("items", [])),
                       "note": self.recaps.get("note", "")},
            "changes": {"notable": self.changes.get("notable", []),
                        "rolled_up": self.changes.get("rolled_up", {}),
                        "total": self.changes.get("total", 0)},
            "rize": self.rize.as_dict() if self.rize else None,
            "caveats": list(self.caveats),
            "errors": list(self.errors),
        }


# ----------------------------------------------------------------- pulls
def _safe(week, name, fn, default=None):
    """Run a read; record the failure instead of raising it."""
    try:
        value = fn()
        week.sources[name] = sources_mod.Source(name, None, True, "", "live")
        return value
    except Exception as exc:  # noqa: BLE001 - one dead endpoint must not kill the retro
        message = "%s: %s" % (type(exc).__name__, str(exc)[:200])
        logger.warning("retro source %s failed (%s)", name, message)
        week.sources[name] = sources_mod.Source(name, None, False, message, "live")
        week.errors.append("%s unavailable (%s)" % (name, message))
        return default


def pull_account_daily(week, instantly, emails=None):
    # type: (Week, Any, Optional[List[str]]) -> List[Dict[str, Any]]
    if instantly is None:
        week.sources["accounts_daily"] = sources_mod.Source(
            "accounts_daily", None, False, "no Instantly client", "")
        return []
    emails = emails or list(settings.IDS.get("instantly", {}).get("active_inboxes") or [])
    # One chunked reader for every component (shared.analytics): the
    # deliverability monitor, the inbox inventory and the daily metrics read
    # this same endpoint, and a single unchunked call here was the one caller
    # that could still hit the workspace's 413 and lose the whole week.
    rows = _safe(week, "accounts_daily", lambda: analytics.account_daily(
        instantly, emails,
        week.last_window.start_date,
        week.this_window.end_date,
        on_error=analytics.RAISE,
        sleep_seconds=0.0,
    ).rows, default=[])
    return rows if isinstance(rows, list) else (rows or {}).get("items", [])


def pull_campaign_daily(week, instantly, campaigns=None):
    # type: (Week, Any, Optional[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]
    out = {}  # type: Dict[str, List[Dict[str, Any]]]
    if instantly is None:
        week.sources["campaigns_daily"] = sources_mod.Source(
            "campaigns_daily", None, False, "no Instantly client", "")
        return out
    campaigns = campaigns if campaigns is not None else settings.CAMPAIGNS
    asked = 0
    failed = []
    for key, meta in (campaigns or {}).items():
        campaign_id = meta.get("id")
        if not campaign_id:
            continue
        asked += 1
        name = "campaigns_daily:%s" % key
        rows = _safe(week, name, lambda cid=campaign_id:
                     analytics.campaign_daily(
                         instantly, cid, week.last_window.start_date,
                         week.this_window.end_date), default=[])
        if not week.sources[name].ok:
            failed.append(key)
            # None, not []: summing an empty list is a confident zero, and the
            # campaign table and the client card both printed "0 sent" for a
            # campaign whose read answered HTTP 500.
            out[key] = None
            continue
        out[key] = rows if isinstance(rows, list) else (rows or {}).get("items", [])
    # ok only when something came back. setdefault used to mark this True after
    # a loop in which all six calls raised, so the campaign table printed six
    # rows of zeros with Instantly named as the source.
    week.sources["campaigns_daily"] = sources_mod.Source(
        "campaigns_daily", None, bool(asked) and len(failed) < asked,
        ("%d of %d campaign pulls failed (%s)" % (len(failed), asked, ", ".join(failed)))
        if failed else ("no campaign ids configured" if not asked else ""),
        "live")
    if failed and len(failed) < asked:
        week.caveats.append(
            "The per-campaign table is missing %s: that read failed this run."
            % ", ".join(failed))
    return out


def pull_campaign_totals(week, instantly):
    # type: (Week, Any) -> List[Dict[str, Any]]
    """LIFETIME per-campaign totals, one call for all six.

    ``GET /campaigns/analytics`` with no date range is the right endpoint for
    exactly one thing: the cumulative send counts the Section 6 verdict lines
    (1,000 and 3,000 sends) are measured against. With a date range it is a
    presence filter, not a window filter, so it must never be used for a
    week-over-week number (see the note in metrics.py).
    """
    if instantly is None:
        week.sources["campaign_totals"] = sources_mod.Source(
            "campaign_totals", None, False, "no Instantly client", "")
        return []
    rows = _safe(week, "campaign_totals", lambda: instantly.campaign_analytics(), default=[])
    if isinstance(rows, dict):
        rows = rows.get("items") or []
    return rows or []


def pull_positive_leads(week, instantly):
    # type: (Week, Any) -> List[Dict[str, Any]]
    """Leads currently at a positive interest status, deduplicated by id."""
    if instantly is None:
        week.sources["leads"] = sources_mod.Source("leads", None, False, "no Instantly client", "")
        return []
    seen = {}  # type: Dict[str, Dict[str, Any]]
    truncated = False
    failed = []
    for flt in POSITIVE_LEAD_FILTERS:
        def pull(flt=flt):
            walk = instantly.iterate("leads/list", body={"filter": flt, "limit": 100},
                                     max_pages=LEADS_MAX_PAGES)
            rows = list(walk)
            return rows, walk.truncated
        name = "leads:%s" % flt
        result = _safe(week, name, pull, default=([], False))
        if not week.sources[name].ok:
            failed.append(flt)
        rows, was_truncated = result if isinstance(result, tuple) else (result or [], False)
        truncated = truncated or bool(was_truncated)
        for lead in rows:
            key = lead.get("id") or "%s|%s" % (lead.get("email"), lead.get("campaign"))
            seen[key] = lead
    reasons = []
    if failed:
        reasons.append("%d of %d lead filters failed (%s)"
                       % (len(failed), len(POSITIVE_LEAD_FILTERS), ", ".join(failed)))
    if truncated:
        reasons.append("one or more lead pulls hit the page cap, so positive counts are a floor")
    # ok=False only when NOTHING came back: then the statuses bucket is None and
    # the funnel prints "not available". A partial failure still has usable
    # rows, so it stays ok and says out loud which counts are floors. Reporting
    # ok=True after all four filters raised is what turned three booked calls
    # into a confident zero.
    week.sources["leads"] = sources_mod.Source(
        "leads", None, len(failed) < len(POSITIVE_LEAD_FILTERS), "; ".join(reasons), "live")
    if truncated:
        week.caveats.append(
            "A lead pull stopped at the %d-page cap, so positives, booked, held and closes are "
            "floors, not totals." % LEADS_MAX_PAGES)
    if failed and len(failed) < len(POSITIVE_LEAD_FILTERS):
        week.caveats.append(
            "%s could not be read this run, so positives, booked, held and closes are floors, not "
            "totals." % ", ".join(failed))
    return list(seen.values())


def pull_opportunities(week, ghl):
    # type: (Week, Any) -> Optional[List[Dict[str, Any]]]
    """GHL opportunities, or None when GHL cannot be read at all.

    ``shared.ghl`` returns None from every read when there is no Private
    Integration token, which is today's state. None here means "unknown", and
    the funnel prints "not available" rather than a zero.
    """
    if ghl is None:
        week.sources["ghl"] = sources_mod.Source(
            "ghl", None, False, "no GHL client", "")
        return None

    def walk():
        rows = []
        cursor_id = None
        cursor_value = None
        pages = 0
        complete = True
        while True:
            payload = ghl.search_opportunities(
                pipeline_id=settings.GHL_SALES_PIPELINE_ID, limit=OPPS_PAGE_LIMIT,
                start_after_id=cursor_id, start_after=cursor_value)
            if payload is None:
                # None is "no token" on the first page and "the walk stopped"
                # after that; only the first is a total failure.
                if pages == 0:
                    return None, True
                complete = False
                break
            page = _opportunity_rows(payload)
            pages += 1
            rows.extend(page)
            if len(page) < OPPS_PAGE_LIMIT:
                break
            if pages >= OPPS_MAX_PAGES:
                complete = False
                break
            last = page[-1]
            cursor_id = last.get("id") or last.get("_id")
            cursor_value = None
            for field in ("updatedAt", "lastStatusChangeAt", "dateUpdated", "createdAt"):
                if last.get(field) is not None:
                    cursor_value = last.get(field)
                    break
            if not cursor_id:
                complete = False
                break
        return rows, complete

    result = _safe(week, "ghl", walk, default=(None, True))
    rows, complete = result if isinstance(result, tuple) else (result, True)
    if rows is None:
        week.sources["ghl"] = sources_mod.Source(
            "ghl", None, False,
            "GHL returned nothing (no Private Integration token exists yet)", "")
        return None
    if not complete:
        # The leads pull has carried a "floors, not totals" caveat since the
        # start; this one did not, and revenue is the invoice basis for the F3
        # client scorecard, so an under-reported figure goes to a client.
        week.sources["ghl"] = sources_mod.Source(
            "ghl", None, True,
            "the opportunities walk stopped after %d pages, so proposals, closes and revenue are "
            "floors, not totals" % OPPS_MAX_PAGES, "live")
        week.caveats.append(
            "The GHL opportunities walk stopped at %d opportunities, so proposals, closes and "
            "revenue won are floors, not totals." % (OPPS_MAX_PAGES * OPPS_PAGE_LIMIT))
    return rows


def _opportunity_rows(payload):
    # type: (Any) -> List[Dict[str, Any]]
    if isinstance(payload, dict):
        rows = payload.get("opportunities") or payload.get("items") or []
    else:
        rows = payload or []
    return [r for r in rows if isinstance(r, dict)]


# --------------------------------------------------------------- assembly
def _window_data(window, account_rows, leads, opportunities, accounts_ok=True, leads_ok=True):
    # type: (Window, List[Dict[str, Any]], List[Dict[str, Any]], Optional[List[Dict[str, Any]]], bool, bool) -> Dict[str, Any]
    """The three buckets ``metrics.build_funnel`` reads, with ``None`` standing
    for "nobody could measure this".

    ``sum_daily`` and ``count_statuses`` both return a fully-populated dict of
    zeros when handed nothing, which is exactly right for a genuinely quiet
    week and exactly wrong for a dead endpoint. The ok flags come from
    ``week.sources``, so the difference is decided once, where it is known.
    """
    people, _collapsed = metrics_mod.dedupe_by_email(leads)
    return {
        "accounts": metrics_mod.sum_daily(account_rows, window) if accounts_ok else None,
        "statuses": metrics_mod.count_statuses(people, window) if leads_ok else None,
        "opps": metrics_mod.count_opportunities(opportunities, window, settings.GHL_STAGES),
        "appointments": None,
    }


def audit_window(this_window, last_window):
    # type: (Window, Window) -> Window
    """The window the Section 6 inbox rule is measured over.

    NOT ``this_window``. At a Friday 16:00 run this week holds Mon-Fri at 25
    sends an inbox, about 100-125 sends, where the 1% real-reply line is a
    single reply: on the recorded healthy week that named 5 of 12 inboxes as
    removals, 42% of the sending capacity, on a week the workspace measured at
    1.2% replies and 1.2% bounces with nothing failing a threshold.

    So the rule runs over the trailing 14 days the retro already pulls
    (``last_window.start`` through today), and the partial run day is dropped,
    because a day that is three hours from over drags every rate down.
    """
    end = shift_days(this_window.end, -1) if this_window.partial_last_day else this_window.end
    if end < last_window.start:
        # A Monday run before 19:00: dropping the partial day would leave an
        # empty window. Keep the partial day and let the quorum rule decide.
        end = this_window.end
    return Window(last_window.start, end, "inbox audit window", partial_last_day=False)


def inbox_rows(account_rows, window):
    # type: (List[Dict[str, Any]], Window) -> List[List[Any]]
    """Per-inbox sends, bounces and real replies for the deliverability audit
    half of O6 (Section 6 Friday: domain/inbox reply-rate audit)."""
    by_inbox = {}  # type: Dict[str, List[Dict[str, Any]]]
    for row in account_rows or []:
        email = row.get("email_account") or row.get("email")
        if email:
            by_inbox.setdefault(email, []).append(row)
    rows = []
    for email in sorted(by_inbox):
        totals = metrics_mod.sum_daily(by_inbox[email], window)
        sent = totals.get("sent", 0.0)
        real = metrics_mod.real_replies(totals)
        bounced = totals.get("bounced", 0.0)
        rows.append([
            email, sent, bounced,
            (bounced / sent) if sent else None,
            real, (real / sent) if sent else None,
        ])
    return rows


def collect_week(now, instantly=None, ghl=None, weeks_back=0, fixtures=None,
                 recap_messages=None, repo=None, job_log_path=None):
    # type: (datetime, Any, Any, int, Optional[Dict[str, Any]], Optional[List[Dict[str, Any]]], Optional[str], Optional[str]) -> Week
    """Assemble the week. ``fixtures`` replaces every live pull for replay.

    fixtures = {"account_rows": [...], "campaign_rows": {key: [...]},
                "leads": [...], "opportunities": [...] or None,
                "commits": [...], "recap_messages": [...]}
    """
    this_window, last_window = windows(now, weeks_back=weeks_back)
    week = Week(now, this_window, last_window)

    if fixtures is not None:
        account_rows = fixtures.get("account_rows") or []
        campaign_daily = fixtures.get("campaign_rows") or {}
        leads = fixtures.get("leads") or []
        opportunities = fixtures.get("opportunities")
        week.campaign_totals = fixtures.get("campaign_totals") or []
        week.sources["accounts_daily"] = sources_mod.Source(
            "accounts_daily", None, True, "", "fixtures")
        week.sources["campaigns_daily"] = sources_mod.Source(
            "campaigns_daily", None, True, "", "fixtures")
        week.sources["leads"] = sources_mod.Source("leads", None, True, "", "fixtures")
        if opportunities is None:
            week.sources["ghl"] = sources_mod.Source(
                "ghl", None, False, "fixtures carry no GHL opportunities", "fixtures")
    else:
        account_rows = pull_account_daily(week, instantly)
        campaign_daily = pull_campaign_daily(week, instantly)
        leads = pull_positive_leads(week, instantly)
        opportunities = pull_opportunities(week, ghl)
        week.campaign_totals = pull_campaign_totals(week, instantly)

    week.leads = leads
    week.account_rows = account_rows
    week.campaign_daily = campaign_daily

    accounts_src = week.sources.get("accounts_daily")
    leads_src = week.sources.get("leads")
    accounts_ok = accounts_src.ok if accounts_src is not None else True
    leads_ok = leads_src.ok if leads_src is not None else True
    this_data = _window_data(this_window, account_rows, leads, opportunities,
                             accounts_ok=accounts_ok, leads_ok=leads_ok)
    last_data = _window_data(last_window, account_rows, leads, opportunities,
                             accounts_ok=accounts_ok, leads_ok=leads_ok)
    week.funnel = metrics_mod.build_funnel(
        this_data, last_data,
        ghl_available=opportunities is not None,
        ghl_note=(week.sources.get("ghl").reason if week.sources.get("ghl") else ""),
        acct_note=(accounts_src.reason if accounts_src is not None and not accounts_ok else ""),
        lead_note=(leads_src.reason if leads_src is not None and not leads_ok else ""),
    )

    # A failed campaign read is None all the way down: the table and the client
    # card render it "not available", never as a summed zero.
    week.per_campaign = {
        "this": dict((k, metrics_mod.sum_daily(v, this_window) if v is not None else None)
                     for k, v in campaign_daily.items()),
        "last": dict((k, metrics_mod.sum_daily(v, last_window) if v is not None else None)
                     for k, v in campaign_daily.items()),
    }
    names = dict((k, (v.get("name") or k)) for k, v in (settings.CAMPAIGNS or {}).items())
    week.campaign_rows = metrics_mod.campaign_table_rows(
        week.per_campaign["this"], week.per_campaign["last"], names)
    week.audit_window = audit_window(this_window, last_window)
    week.inbox_rows = inbox_rows(account_rows, week.audit_window) if accounts_ok else []

    # System changes: git always, audit logs only when a session staged them.
    git = sources_mod.git_log(this_window.start_date,
                              _day_after(this_window.end_date), repo=repo)
    week.sources["git"] = git
    week.changes = sources_mod.group_commits(git.value or [])
    audit = sources_mod.audit_logs(window=this_window)
    week.sources["audit_logs"] = audit

    # Call recaps: staged by a session, or handed in directly (tests, replay).
    if recap_messages is None and fixtures is not None:
        recap_messages = fixtures.get("recap_messages")
    if recap_messages is None:
        staged = sources_mod.staged_recaps()
        week.sources["recaps"] = staged
        recap_messages = staged.value or []
    else:
        week.sources["recaps"] = sources_mod.Source("recaps", None, True, "", "provided")
    week.recaps = recaps_mod.parse_messages(recap_messages, window=this_window)

    week.rize = sources_mod.rize_hours(window=this_window)
    week.sources["rize"] = week.rize
    # job_log_path is the REAL Job_Log, captured by the caller before
    # use_scratch_logs repointed JOB_LOG_PATH at a scratch file. Without it a
    # --dry-run read the empty scratch file it had just created and rendered
    # "No Job_Log rows in the window", so the preview the runbook tells Lorenzo
    # to inspect first differed from the real output by a whole section.
    week.job_log = sources_mod.job_log_rows(path=job_log_path, window=this_window)
    week.sources["job_log"] = week.job_log

    week.caveats.extend(standing_caveats(week, opportunities))
    return week


def _day_after(date_string):
    # type: (str) -> str
    from datetime import timedelta
    day = datetime.strptime(date_string, "%Y-%m-%d") + timedelta(days=1)
    return day.strftime("%Y-%m-%d")


def standing_caveats(week, opportunities):
    # type: (Week, Optional[List[Dict[str, Any]]]) -> List[str]
    """What the reader has to know before believing a row.

    Every ``week.errors`` entry goes in here. The packet is the only artefact
    anybody reads: a failure that lives in the Job_Log row and in nothing else
    means the markdown Lorenzo edits, the Skool draft he posts and the client
    scorecard he invoices from all carry a number that nobody measured, with
    Instantly named beside it as the source.
    """
    out = []
    if week.errors:
        out.append(
            "Some reads failed this run, so every row that depends on one of them says \"not "
            "available\" rather than a number: %s." % "; ".join(week.errors))
    if week.this_window.partial_last_day:
        out.append(
            "%s is counted whole in both weeks but the run is at %s CT, so this week is missing "
            "the rest of today's sending window (07:00-19:00 CT)."
            % (week.this_window.end_date, week.now.strftime("%H:%M")))
    if opportunities is None:
        out.append(
            "Proposals and revenue are blank because there is no GHL Private Integration token. "
            "Closes and held calls fall back to Instantly interest status, which only moves when "
            "the reply engine mirror (S8) runs, and that is still in shadow, so both under-report.")
    if not (week.sources.get("recaps") and week.sources["recaps"].ok):
        out.append(
            "Wins and objections are empty: %s"
            % (week.sources["recaps"].reason if week.sources.get("recaps") else "no call recaps"))
    if week.rize is not None and not week.rize.ok:
        out.append("Hours by category are missing: %s" % week.rize.reason)
    if not week.sources.get("audit_logs") or not week.sources["audit_logs"].ok:
        out.append(
            "System changes are the git log only. %s"
            % (week.sources["audit_logs"].reason if week.sources.get("audit_logs") else ""))
    return out
