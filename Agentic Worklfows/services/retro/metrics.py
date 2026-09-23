"""Funnel numbers for one week. Pure: data in, metrics out, no clients, no clock.

Every number carries the source that produced it. A number nobody could
measure is ``None`` and renders as "not available" with the reason, because a
retro that quietly prints 0 for "closes" when GHL was unreachable teaches
Lorenzo the wrong lesson and then the model writes a lesson about it.

Where the numbers come from
---------------------------
sends / bounces / replies  Instantly ``GET /accounts/analytics/daily``, one row
                           per inbox per calendar date. Summed over the window.
                           The per-campaign split comes from
                           ``GET /campaigns/analytics/daily``, same shape.
                           NOT from ``GET /campaigns/analytics`` with a date
                           range: verified read-only on 2026-09-22, that
                           endpoint returns LIFETIME totals for any campaign
                           that was active in the range (cleaning_reactivation
                           answered emails_sent_count=300, its all-time total,
                           for both 09-15..09-21 and a narrower range) and an
                           empty list for one that was not. It is a presence
                           filter, not a window filter, so it cannot produce a
                           week-over-week delta.
positives / booked / held  Instantly lead ``lt_interest_status`` plus
closes / no-shows          ``timestamp_last_interest_change``. A lead counts in
                           the week its status last changed. The codes are
                           ordinal along the funnel (1 interested, 2 booked,
                           3 completed, 4 closed), so "booked" means status >= 2
                           and booked is a subset of positives. This is a
                           stage-at-end-of-week read, not a flow: a lead that
                           went interested -> booked inside one week is counted
                           once, as booked. Instantly exposes no transition
                           history, so a true flow count is not available and
                           the packet says which reading it used.
proposals / revenue        GHL opportunities (stage proposal_sent, stage won
                           with monetaryValue). No Private Integration token
                           exists yet, so these are ``None`` today and the
                           packet names the missing token as the reason.
held / no-shows (better)   GHL appointment status when a token exists, or the
                           reply engine's store (``appointment:*`` / ``joins:*``
                           written by the S4/S5 jobs) when it does not.
"""
from typing import Any, Dict, Iterable, List, Optional

from .weeks import Window

# Instantly lt_interest_status codes, from config/ids.json.
INTERESTED = 1
MEETING_BOOKED = 2
MEETING_COMPLETED = 3
CLOSED = 4
NO_SHOW = -4


class Metric(object):
    """One funnel row: this week, last week, where it came from."""

    def __init__(self, key, label, this_week=None, last_week=None, unit="",
                 source="", note="", alert=None):
        # type: (str, str, Any, Any, str, str, str, Optional[str]) -> None
        self.key = key
        self.label = label
        self.this_week = this_week
        self.last_week = last_week
        self.unit = unit
        self.source = source
        self.note = note
        self.alert = alert

    @property
    def available(self):
        # type: () -> bool
        return self.this_week is not None

    def as_dict(self):
        return {
            "key": self.key, "label": self.label, "this_week": self.this_week,
            "last_week": self.last_week, "unit": self.unit, "source": self.source,
            "note": self.note, "alert": self.alert,
        }

    def __repr__(self):
        return "Metric(%s, %r -> %r)" % (self.key, self.last_week, self.this_week)


def _num(value):
    # type: (Any) -> float
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _rate(numerator, denominator):
    # type: (Optional[float], Optional[float]) -> Optional[float]
    if numerator is None or not denominator:
        return None
    return float(numerator) / float(denominator)


# ------------------------------------------------------------ daily rollups
def sum_daily(rows, window, fields=None):
    # type: (Iterable[Dict[str, Any]], Window, Optional[List[str]]) -> Dict[str, float]
    """Sum Instantly daily-analytics rows whose ``date`` is inside ``window``.

    Works for both the account rows (``email_account``) and the campaign rows,
    which carry the same metric field names.
    """
    fields = fields or [
        "sent", "bounced", "contacted", "new_leads_contacted", "opened", "unique_opened",
        "replies", "unique_replies", "replies_automatic", "unique_replies_automatic",
        "clicks", "unique_clicks", "opportunities", "unique_opportunities",
    ]
    out = dict((f, 0.0) for f in fields)
    out["days"] = 0.0
    seen_days = set()
    for row in rows or []:
        date = str(row.get("date") or "")[:10]
        if not window.contains_date(date):
            continue
        seen_days.add(date)
        for field in fields:
            if field in row:
                out[field] += _num(row.get(field))
    out["days"] = float(len(seen_days))
    return out


def real_replies(totals):
    # type: (Dict[str, float]) -> float
    """Replies a human actually wrote.

    **``replies`` already excludes auto-responders in this API.**
    ``replies_automatic`` is a parallel counter, not a subset of ``replies``,
    so subtracting one from the other removes the auto-responders twice and
    reports roughly a tenth of the real number.

    The proof is in the recorded week (``fixtures/week_2026-09.json``), which
    came straight off the live workspace on 2026-09-22:

      - 17 account-daily rows and 10 campaign-daily rows have ``replies: 0``
        with ``replies_automatic: 1`` or more. A subset cannot be larger than
        the set it is a subset of.
      - "2026 Bookkeeping - Trigger Outbound" is at ``reply_count: 1`` lifetime
        with ``reply_count_automatic: 6``.
      - Summed over Sept 15-21: 1,800 sent, 22 replies, 19 unique replies, 22
        automatic. Subtracting would have printed 0.00% for a week with
        nineteen real replies in it.

    **The number this function returns, and therefore the number the packet
    prints, is ``unique_replies``: 19 over 1,800 sent, 1.06%.** Unique is the
    per-lead count, which is what Section 6 wants: a lead who hits reply three
    times is one reply. The raw ``replies`` counter for the same week is 22,
    which is 1.22%, and that is the figure Lorenzo measured by hand; the two
    differ by the three leads who replied twice. Section 6's 1% line is a
    per-lead rule, so unique is the right denominator, and the packet says
    "Real replies (no auto or OOO)" with unique in it and nothing else.
    ``replies`` is the fallback only when a row carries no unique variant at
    all.
    """
    unique = totals.get("unique_replies")
    if unique is None:
        unique = totals.get("replies", 0.0)
    return max(0.0, _num(unique))


def auto_replies(totals):
    # type: (Dict[str, float]) -> float
    """Auto-responders and out-of-office, counted separately (see real_replies).
    Worth watching on its own: the Saturday canary (O7) kills an inbox that
    stops producing them."""
    unique = totals.get("unique_replies_automatic")
    if unique is None:
        unique = totals.get("replies_automatic", 0.0)
    return _num(unique)


# ------------------------------------------------------------ lead rollups
def lead_status(lead):
    # type: (Dict[str, Any]) -> Optional[int]
    raw = lead.get("lt_interest_status", lead.get("interest_status"))
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def lead_changed_at(lead):
    # type: (Dict[str, Any]) -> Optional[str]
    return (
        lead.get("timestamp_last_interest_change")
        or lead.get("timestamp_last_reply")
        or lead.get("timestamp_updated")
    )


FUNNEL_STATUSES = (INTERESTED, MEETING_BOOKED, MEETING_COMPLETED, CLOSED)
NEGATIVE_STATUSES = (-1, -2, -3)


def _funnel_rank(lead):
    # type: (Dict[str, Any]) -> int
    status = lead_status(lead)
    if status in FUNNEL_STATUSES:
        return status
    if status == NO_SHOW:
        return 0
    return -99


def dedupe_by_email(leads):
    # type: (Iterable[Dict[str, Any]]) -> Any
    """One record per email address: ``(leads, collapsed)``.

    The same person sits on two campaigns whenever a list is uploaded twice,
    and each copy has its own lead id, so an id dedupe counted them twice: the
    client card read "Interested 5" above its own note that a contact was
    counted once. The surviving copy is the one furthest up the funnel, then
    the one that changed most recently. A lead with no email is kept as is.
    Same rule as ``jobs.client_scorecard.dedupe_leads``.
    """
    best = {}  # type: Dict[str, Dict[str, Any]]
    order = []  # type: List[str]
    unkeyed = []  # type: List[Dict[str, Any]]
    collapsed = 0
    for lead in leads or []:
        email = str(lead.get("email") or "").strip().lower()
        if not email:
            unkeyed.append(lead)
            continue
        if email not in best:
            best[email] = lead
            order.append(email)
            continue
        collapsed += 1
        current = best[email]
        if (_funnel_rank(lead), str(lead_changed_at(lead) or "")) > \
                (_funnel_rank(current), str(lead_changed_at(current) or "")):
            best[email] = lead
    return [best[e] for e in order] + unkeyed, collapsed


def count_statuses(leads, window):
    # type: (Iterable[Dict[str, Any]], Window) -> Dict[str, int]
    """Cumulative stage counts for leads whose status last moved in ``window``.

    The ladder is BOUNDED to the documented codes 1 to 4. A custom lead label
    carries its own value anywhere in -30000..30000, so ``status >= 4`` read
    the first label anyone creates as a signed deal. Anything outside the
    documented set is ignored here, the same rule the client scorecard applies.
    """
    counts = {"positives": 0, "booked": 0, "held": 0, "closes": 0, "no_shows": 0, "negative": 0}
    for lead in leads or []:
        if not window.contains_date(lead_changed_at(lead)):
            continue
        status = lead_status(lead)
        if status is None:
            continue
        if status == NO_SHOW:
            counts["no_shows"] += 1
            continue
        if status in NEGATIVE_STATUSES:
            counts["negative"] += 1
            continue
        if status not in FUNNEL_STATUSES:
            continue
        counts["positives"] += 1
        if status >= MEETING_BOOKED:
            counts["booked"] += 1
        if status >= MEETING_COMPLETED:
            counts["held"] += 1
        if status >= CLOSED:
            counts["closes"] += 1
    return counts


# --------------------------------------------------------- GHL opportunities
PROPOSAL_STAGE = "proposal_sent"
WON_STAGE = "won"


# What dates a move INTO a stage. ``updatedAt`` / ``dateUpdated`` are edit
# times: a note or a nightly mirror touching an August deal put its close and
# its revenue into this week (probe: a phantom $10,000 week). Won and lost are
# also a status in GHL, so for those the status change dates the move when the
# stage change is absent. Same rule as services.metrics.sources.
STAGE_CHANGE_FIELDS = ("lastStageChangeAt", "last_stage_change_at", "stage_changed_at")
STATUS_CHANGE_FIELDS = ("lastStatusChangeAt", "last_status_change_at")


def opportunity_moved_at(opp, stage):
    # type: (Dict[str, Any], Optional[str]) -> Optional[str]
    fields = STAGE_CHANGE_FIELDS + (STATUS_CHANGE_FIELDS if stage in (WON_STAGE, "lost") else ())
    for field in fields:
        if opp.get(field):
            return opp.get(field)
    return None


def count_opportunities(opportunities, window, stage_ids):
    # type: (Optional[Iterable[Dict[str, Any]]], Window, Dict[str, str]) -> Optional[Dict[str, Any]]
    """Proposals sent and revenue won inside the window, or None when GHL could
    not be read at all (no token). An empty list is a real zero; ``None`` is not.

    A proposal or a won deal whose stage move carries no date could belong to
    any week, so the count it would belong to is None ("not available") rather
    than a number that may be short; ``undated`` says how many and why.
    """
    if opportunities is None:
        return None
    by_id = {}
    for key, value in (stage_ids or {}).items():
        if value:
            by_id[value] = key
    out = {"proposals": 0.0, "closes": 0.0, "revenue": 0.0}  # type: Dict[str, Any]
    undated = {"proposals": 0, "closes": 0}
    for opp in opportunities:
        stage = by_id.get(opp.get("pipelineStageId") or opp.get("stageId"))
        if stage not in (PROPOSAL_STAGE, WON_STAGE):
            continue
        moved = opportunity_moved_at(opp, stage)
        if moved is None:
            undated["proposals" if stage == PROPOSAL_STAGE else "closes"] += 1
            continue
        if not window.contains_date(moved):
            continue
        if stage == PROPOSAL_STAGE:
            out["proposals"] += 1
        else:
            out["closes"] += 1
            out["revenue"] += _num(opp.get("monetaryValue"))
    if undated["proposals"]:
        out["proposals"] = None
    if undated["closes"]:
        out["closes"] = None
        out["revenue"] = None
    out["undated"] = undated
    return out


# ------------------------------------------------------------- the funnel
NO_SHOW_UNMEASURED = ("not measured: the lead pull reads interest statuses 1 to 4 only, and "
                      "Instantly has no verified list filter for no-show (-4), so a 0 here would "
                      "not be a count")
BOOKED_FLOOR_NOTE = ("a lead who booked and then did not show has left status 2 and is not in "
                     "this count, so it is a floor")


def build_funnel(this_data, last_data, ghl_available=True, ghl_note="",
                 acct_note="", lead_note="", no_shows_measured=False):
    # type: (Dict[str, Any], Dict[str, Any], bool, str, str, str, bool) -> List[Metric]
    """The Section 6 funnel, this week against last week.

    ``this_data`` / ``last_data`` are the dicts ``collect`` assembles:
        {"accounts": {...daily totals...}|None, "statuses": {...}|None,
         "opps": {...}|None, "appointments": {"held": n, "no_shows": n}|None}

    A bucket is ``None`` when the read behind it failed. Those metrics come
    back with ``this_week=None``, which ``render.metric_table`` prints as
    "not available" with ``note`` beside it, and ``acct_note`` / ``lead_note``
    are the reasons ``collect`` recorded, so the failure is legible in the
    packet rather than only in the Job_Log row.
    """
    def bucket(data, key):
        """The bucket, or None when ``collect`` could not measure it.

        ``None`` and ``{}`` are different answers. ``{}`` never reaches here:
        ``collect`` passes None for a bucket whose source failed and a summed
        dict otherwise, and a summed dict over zero rows inside the window is a
        real zero. Returning ``{}`` for a failed source is what printed
        "Emails sent 0, flat" with "Instantly accounts/analytics/daily" beside
        it on a week where every read answered HTTP 500.
        """
        value = (data or {}).get(key)
        return value if isinstance(value, dict) else None

    def cell(data, key):
        return None if data is None else data.get(key)

    this_acc = bucket(this_data, "accounts")
    last_acc = bucket(last_data, "accounts")
    this_st = bucket(this_data, "statuses")
    last_st = bucket(last_data, "statuses")
    this_opp = (this_data or {}).get("opps")
    last_opp = (last_data or {}).get("opps")
    this_appt = (this_data or {}).get("appointments")
    last_appt = (last_data or {}).get("appointments")

    acct_src = "Instantly accounts/analytics/daily"
    lead_src = "Instantly leads lt_interest_status"
    ghl_src = "GHL opportunities"
    missing = ghl_note or "no GHL Private Integration token"

    this_sent = cell(this_acc, "sent")
    last_sent = cell(last_acc, "sent")
    this_real = real_replies(this_acc) if this_acc is not None else None
    last_real = real_replies(last_acc) if last_acc is not None else None
    # These notes explain an ABSENCE. Attaching one to a metric that has a
    # value put "(the Instantly accounts endpoint could not be read)" in the
    # Source column of every healthy row, which is worse than saying nothing.
    acct_missing = ("" if this_acc is not None
                    else (acct_note or "the Instantly accounts endpoint could not be read"))
    lead_missing = ("" if this_st is not None
                    else (lead_note or "the Instantly lead filters could not be read"))

    metrics = [
        Metric("sent", "Emails sent", this_sent, last_sent, "", acct_src, note=acct_missing),
        Metric("bounced", "Bounces", cell(this_acc, "bounced"), cell(last_acc, "bounced"), "",
               acct_src, note=acct_missing),
        Metric("bounce_rate", "Bounce rate",
               _rate(cell(this_acc, "bounced"), this_sent),
               _rate(cell(last_acc, "bounced"), last_sent),
               "%", acct_src, note=acct_missing,
               alert="Section 6: over 2% means remove the inbox"),
        Metric("real_replies", "Real replies (no auto or OOO)", this_real, last_real, "", acct_src,
               note=("unique_replies; replies_automatic is a separate counter, not a subset"
                     if this_real is not None else acct_missing)),
        Metric("auto_replies", "Auto-responders and OOO",
               auto_replies(this_acc) if this_acc is not None else None,
               auto_replies(last_acc) if last_acc is not None else None, "", acct_src,
               note=acct_missing),
        Metric("real_reply_rate", "Real reply rate",
               _rate(this_real, this_sent), _rate(last_real, last_sent), "%", acct_src,
               note=acct_missing,
               alert="Section 6: under 1% after 100 sent per inbox"),
        Metric("positives", "Positive replies", cell(this_st, "positives"),
               cell(last_st, "positives"), "", lead_src, note=lead_missing),
        Metric("positive_rate", "Positive reply rate",
               _rate(cell(this_st, "positives"), this_sent),
               _rate(cell(last_st, "positives"), last_sent),
               "%", lead_src, note=lead_missing, alert="Section 6: under 0.5% for 3 days"),
        Metric("booked", "Calls booked", cell(this_st, "booked"), cell(last_st, "booked"), "",
               lead_src,
               note=(lead_missing if this_st is None else
                     ("" if no_shows_measured else BOOKED_FLOOR_NOTE))),
    ]

    # Held and no-shows: GHL appointment status is the source of truth; the
    # reply engine store is the fallback; Instantly status is the last resort.
    if this_appt is not None:
        metrics.append(Metric("held", "Calls held", this_appt.get("held"),
                              (last_appt or {}).get("held"), "", "GHL appointment status"))
        metrics.append(Metric("no_shows", "No-shows", this_appt.get("no_shows"),
                              (last_appt or {}).get("no_shows"), "", "GHL appointment status"))
    else:
        metrics.append(Metric("held", "Calls held", cell(this_st, "held"), cell(last_st, "held"), "",
                              lead_src,
                              note=("meeting_completed in Instantly; GHL appointment status is the "
                                    "better source once a token exists"
                                    if this_st is not None else lead_missing)))
        if no_shows_measured:
            metrics.append(Metric("no_shows", "No-shows", cell(this_st, "no_shows"),
                                  cell(last_st, "no_shows"), "", lead_src,
                                  note=("interest status -4" if this_st is not None
                                        else lead_missing)))
        else:
            # The positive pull never reads a -4 lead, so its 0 is not a count.
            metrics.append(Metric("no_shows", "No-shows", None, None, "", lead_src,
                                  note=lead_missing if this_st is None else NO_SHOW_UNMEASURED))

    if this_opp is not None:
        undated = this_opp.get("undated") or {}
        undated_note = ("%d opportunit%s in that stage carr%s no stage-change date, so the week it "
                        "moved cannot be told")
        def _undated(kind):
            n = undated.get(kind) or 0
            return (undated_note % (n, "y" if n == 1 else "ies", "ies" if n == 1 else "y")) if n else ""
        metrics.append(Metric("proposals", "Proposals sent", this_opp.get("proposals"),
                              (last_opp or {}).get("proposals"), "", ghl_src,
                              note=_undated("proposals")))
        metrics.append(Metric("closes", "Closes", this_opp.get("closes"),
                              (last_opp or {}).get("closes"), "", ghl_src,
                              note=_undated("closes")))
        metrics.append(Metric("revenue", "Revenue won", this_opp.get("revenue"),
                              (last_opp or {}).get("revenue"), "$", ghl_src,
                              note=_undated("closes")))
    else:
        metrics.append(Metric("proposals", "Proposals sent", None, None, "", "", note=missing))
        metrics.append(Metric("closes", "Closes", cell(this_st, "closes"), cell(last_st, "closes"),
                              "", lead_src,
                              note=("Instantly status 4; GHL is the source of truth for a signed "
                                    "deal once a token exists"
                                    if this_st is not None else lead_missing)))
        metrics.append(Metric("revenue", "Revenue won", None, None, "$", "", note=missing))

    if not ghl_available:
        for metric in metrics:
            if metric.source == ghl_src and metric.this_week is None and not metric.note:
                metric.note = missing
    return metrics


def by_key(metrics):
    # type: (Iterable[Metric]) -> Dict[str, Metric]
    return dict((m.key, m) for m in metrics)


def moved(metrics):
    # type: (Iterable[Metric]) -> List[Metric]
    """Metrics that actually changed week over week. The lessons rubric refuses
    a lesson about a number that did not move."""
    out = []
    for metric in metrics:
        if metric.this_week is None or metric.last_week is None:
            continue
        try:
            if float(metric.this_week) != float(metric.last_week):
                out.append(metric)
        except (TypeError, ValueError):
            continue
    return out


def campaign_table_rows(per_campaign_this, per_campaign_last, campaign_names):
    # type: (Dict[str, Optional[Dict[str, float]]], Dict[str, Optional[Dict[str, float]]], Dict[str, str]) -> List[List[Any]]
    """Per-campaign sends / real replies / real reply rate, this week vs last.

    A campaign whose read failed carries ``None`` rather than a summed dict,
    and its row is ``None`` in every cell, which the packet prints as "not
    available". Summing the ``[]`` a failed read used to leave behind printed
    "0 sent" for a campaign nobody had measured.
    """
    rows = []
    for key in sorted(per_campaign_this.keys()):
        this_t = per_campaign_this.get(key)
        last_t = per_campaign_last.get(key)
        this_sent = this_t.get("sent", 0.0) if this_t is not None else None
        last_sent = last_t.get("sent", 0.0) if last_t is not None else None
        this_real = real_replies(this_t) if this_t is not None else None
        last_real = real_replies(last_t) if last_t is not None else None
        rows.append([
            campaign_names.get(key, key),
            this_sent, this_real, _rate(this_real, this_sent),
            last_sent, last_real, _rate(last_real, last_sent),
        ])
    return rows
