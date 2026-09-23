#!/usr/bin/env python3
"""Weekly client scorecard and the F4 retention drafts (Blueprint F3/F4, brief A12).

One page per active client: sent, replies, positives, booked, held, closed,
revenue attributed, and next week's plan. For a performance deal the scorecard
IS the invoice, so it also prints the attribution window and names the
reactivated contacts that closed inside it.

    cd "Agentic Worklfows"
    MODE=shadow LLM_FAKE=1 NOTIFY=off python3 jobs/client_scorecard.py --dry-run
    MODE=shadow LLM_FAKE=1 NOTIFY=off python3 jobs/client_scorecard.py --dry-run --self
    MODE=shadow LLM_FAKE=1 NOTIFY=off python3 jobs/client_scorecard.py --dry-run --client man-transformed --retention
    MODE=shadow LLM_FAKE=1 NOTIFY=off python3 jobs/client_scorecard.py --dry-run --fixtures --as-of 2026-09-22T00:45:00-05:00
    MODE=shadow LLM_FAKE=1 NOTIFY=off python3 jobs/client_scorecard.py --now    # + the ntfy digest to Lorenzo

Reads only. Writing a scorecard to disk under .tmp/ is the only side effect
of a run. The job never sends a card to a client, in any mode: delivery is
manual, by Lorenzo, after reading it, and the run lists the cards that are
ready for that. Invoicing is tracked by hand: the job keeps no record of what
has been billed and no card says anything about billing state.

**Two documents per client, and only one of them is the client's.**
``scorecard_<end>.md`` is the client body: the table, the invoice basis, the
plan and the caveats that change how the numbers read. ``operator_<end>.md``
is Lorenzo's: the retention schedule, the draft blockers, the run notes. The
delivery guard carries the client body only. A client must never read that a
renewal note is scheduled for them on day 25.

Seven things this job refuses to do, each because the alternative is a wrong
invoice or a wrong claim to a client:

1. **It never prints an unmeasured zero.** A client with no campaign id in the
   roster has no send data, so the row says ``no source`` rather than 0. A zero
   reads as "your week produced nothing". The same holds when every analytics
   pull behind a card failed: a 500 from the platform is not a quiet week.
2. **It never prints untraceable revenue on a performance deal.** Money is only
   reported when it traces to a named contact with a first-touch date inside
   the attribution window. Anything else is labelled an estimate and excluded
   from the invoice line.
3. **It bills only closes dated inside this reporting period, and it keeps
   no billing record.** The invoice line is what closed inside THIS reporting
   period, dated by a real close timestamp (the GHL Won move, a close date on
   the lead, or the interest-status change to closed), never by the contact's
   last reply. A close with no real date is excluded with the reason. An
   earlier close is listed as "Closed in an earlier period, not part of this
   week's figure", a close dated after the period is left off the client
   body, neither is added to the amount, and nothing on any card says whether
   a close was billed: invoicing is tracked by hand. Because there is no
   ledger, the same close CAN be counted on two cards, or on none: its date
   moves, earlier or later, when the source changes (for example between an
   Instantly status date and a GHL Won date), an off-schedule run overlaps
   the scheduled week, and a week whose card failed or did not run has no
   invoice line. The operator notes say so, list each counted, earlier and
   later close with its date source, and ask for all of them to be checked
   by hand before billing.
4. **It marks a retention draft ``ready`` only when every number in it exists**,
   only when the copy passes the client-copy rules, and, when it quotes money,
   only when that figure is in ``config/offers.md``.
5. **It does not invent the reporting week.** Instantly records only the latest
   interest-status change (``timestamp_last_interest_change``), not when each
   earlier step happened, so a lead's week is taken from
   ``timestamp_last_reply`` and that limitation is printed on the scorecard
   rather than hidden inside it. The word "week" always means seven days: an
   upstream window shorter than that is refused, not relabelled.
6. **It never quotes term-to-date numbers from one week.** The day-21 and
   day-25 drafts describe the term, so they are filled from a separate
   start-date-to-now pull and say the day they were measured through.
7. **It never hands one client another client's numbers.** ``--fixtures``
   replays recorded Advero data, so it is injected for the internal
   pseudo-client only, written to ``.replay.md`` files, and stamped on every
   card, every draft header and every digest line.

Python 3.9 compatible. ``now`` is always injected; the CLI's ``--as-of`` is the
only place a clock is read.
"""
import argparse
import json
import logging
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if __package__ in (None, ""):  # run as a script: make "shared" importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import settings  # noqa: E402
from shared import slots  # noqa: E402
from shared.ghl import GHL  # noqa: E402
from shared.instantly import Instantly, default_client, InstantlyError  # noqa: E402
from shared.job_log import log_run  # noqa: E402
from shared.notify import notify, topic_is_protected  # noqa: E402
from shared.paths import BASE_DIR, tmp_dir  # noqa: E402
from shared.store import Store, get_store  # noqa: E402

logger = logging.getLogger("jobs.client_scorecard")

JOB_NAME = "client_scorecard"

ROSTER_SEED = BASE_DIR / "changesets" / "onboarding" / "clients.seed.json"
RETENTION_DIR = BASE_DIR / "changesets" / "onboarding" / "retention"
ANALYTICS_SNAPSHOT = BASE_DIR / "config" / "snapshots" / "instantly_campaign_analytics_2026-09-21.json"
LEADS_FIXTURE = (BASE_DIR / "services" / "reply_engine" / "tests" / "fixtures"
                 / "instantly_replied_leads_2026-09.json")

STORE_CLIENT_PREFIX = "client:"            # client:<slug> -> roster overrides written by an operator
STORE_RETENTION_PREFIX = "retention:"      # retention:<slug>:<template_id> -> {"rendered_at", "handled_at"}
STORE_FIRST_TOUCH_PREFIX = "first_touch:"  # first_touch:<email> -> "YYYY-MM-DD", the attribution clock

# lt_interest_status thresholds. config/ids.json interest_status_codes:
# 1 interested, 2 meeting booked, 3 meeting completed, 4 closed.
STATUS_POSITIVE = 1
STATUS_BOOKED = 2
STATUS_HELD = 3
STATUS_CLOSED = 4
# config/instantly_api_contract.md: the documented enum is 0..4 and -1..-4, and
# "Custom lead labels use their own value in the range -30000..30000". A >= test
# therefore promotes the first custom label anyone creates to a closed deal and
# puts it on a client's invoice. Only these four codes climb the funnel.
FUNNEL_STATUSES = (STATUS_POSITIVE, STATUS_BOOKED, STATUS_HELD, STATUS_CLOSED)
KNOWN_STATUSES = frozenset([0, 1, 2, 3, 4, -1, -2, -3, -4])

MAX_LEAD_PAGES = 20        # 20 x 100 leads per campaign; a truncated pull is reported, never silent
MAX_OPPORTUNITY_PAGES = 20  # 20 x 100 won opportunities; a short page ends the walk
REACTIVATION_ATTRIBUTION_DAYS = 180   # config/offers.md, for the message only. Never a silent default.

# Section 6 states the reply-rate alert as "< 1% after 100 sent per inbox". With
# 12 active inboxes that is 1,200; at portfolio level 300 is one full day across
# all of them and the smallest sample worth a verdict. Under it the card says so
# rather than telling a client in week one to rewrite their sequence.
MIN_SENDS_FOR_REPLY_VERDICT = 300
# A touch this far past due is not news any more. Without a floor every run from
# mid-October onward lists Mike's four touches as overdue and pushes the digest
# at high priority forever, which is how a real overdue touch stops being seen.
MAX_OVERDUE_DAYS = 14

NO_SOURCE = "no source"
REPLAY_STAMP = "FIXTURES REPLAY, NOT THIS CLIENT'S NUMBERS"


# ----------------------------------------------------------------- utilities
def _lower(value: Any) -> str:
    return (value or "").strip().lower() if isinstance(value, str) else ""


class Notes(list):
    """Run notes, split by audience.

    A list of every note (which is what the Job_Log and the operator appendix
    want), plus the subset that belongs on the page a client reads. A caveat
    that changes how a number reads is the client's business: "counts are a
    floor" has to travel with the count. "ghl_token_missing" does not.
    """

    def __init__(self, items=None):
        list.__init__(self, items or [])
        self._client = []  # type: List[str]

    def add(self, text: str, client: Optional[str] = None) -> None:
        """``client`` is the plain-language version for the client's page, or
        None when the note is Lorenzo's alone."""
        self.append(text)
        if client:
            self._client.append(client)

    def client_facing(self) -> List[str]:
        return list(self._client)


def _add(notes: List[str], text: str, client: Optional[str] = None) -> None:
    """Add a note to a Notes container or to a plain list (tests pass lists)."""
    adder = getattr(notes, "add", None)
    if callable(adder):
        adder(text, client=client)
    else:
        notes.append(text)


def parse_ts(value: Any) -> Optional[datetime]:
    """ISO timestamp to an aware datetime, or None. Accepts the 'Z' suffix and
    any fractional-second length Instantly emits."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    match = re.search(r"\.(\d+)", text)
    if match and len(match.group(1)) not in (3, 6):
        digits = (match.group(1) + "000000")[:6]
        text = text[: match.start(1)] + digits + text[match.end(1):]
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_day(value: Any) -> Optional[date]:
    """A calendar day in Central time.

    The date-only check comes FIRST and deliberately. ``GET
    /campaigns/analytics/daily`` answers ``{"date": "2026-09-16", ...}``, and
    reading that as a timestamp gives midnight UTC, which converts to 19:00 the
    PREVIOUS day in Central. Every daily row then lands in the wrong bucket and
    the week silently reports six of its seven days plus one of last week's.
    Caught by running the job against the recorded snapshot: the week showed
    1500 sent and "last week" showed 300 when every fixture row was inside the
    week. A date with no time carries no timezone to convert.
    """
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str) and DATE_ONLY_RE.match(value.strip()):
        return date(*[int(part) for part in value.strip().split("-")])
    parsed = parse_ts(value)
    if parsed is not None:
        return parsed.astimezone(settings.TZ).date()
    return None


def week_bounds(now: datetime, week_ending: Optional[date] = None) -> Tuple[date, date]:
    """The reporting week: seven days ending YESTERDAY (Central), inclusive.

    Deliberately a rolling week, not Monday-to-Sunday. The job has to produce
    the same answer whichever day Lorenzo runs it, and a Monday-to-Sunday week
    run on a Wednesday either reports a stale week or a half one. ``--week-ending``
    pins it for a replay.
    """
    if week_ending is not None:
        end = week_ending
    else:
        end = now.astimezone(settings.TZ).date() - timedelta(days=1)
    return end - timedelta(days=6), end


def _iso(day: date) -> str:
    return day.strftime("%Y-%m-%d")


def _money(value: Any) -> str:
    """A dollar amount a person can read. ``"%s" % 50000.0`` is "50000.0",
    which on the one bold line of an invoice is not good enough."""
    if value is None:
        return NO_SOURCE
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number - round(number)) < 0.005:
        return "${:,.0f}".format(round(number))
    return "${:,.2f}".format(number)


# -------------------------------------------------------------------- roster
def _validate_client(client: Dict[str, Any]) -> List[str]:
    problems = []  # type: List[str]
    if not client.get("slug"):
        problems.append("a client with no slug")
        return problems
    slug = client["slug"]
    if client.get("deal_type") == "performance":
        if not client.get("attribution_window_days"):
            # A performance deal with no window cannot produce an invoice line,
            # and defaulting it silently would invoice against the wrong period.
            # The card refuses to print a window rather than inventing 180 days.
            problems.append("%s: deal_type=performance with no attribution_window_days" % slug)
        if not client.get("commission_rate"):
            # config/offers.md prices reactivation at 20 to 30 percent of first
            # year fees. Without the rate the card's only bold figure is the
            # CLIENT's contract value, which is not what Advero invoices.
            problems.append("%s: deal_type=performance with no commission_rate" % slug)
    start = parse_day(client.get("start_date"))
    term = client.get("term_days")
    end = parse_day(client.get("term_end"))
    if start and term and end:
        expected = start + timedelta(days=int(term))
        if expected != end:
            problems.append("%s: term_end %s does not equal start_date + %s days (%s)"
                            % (slug, _iso(end), term, _iso(expected)))
    return problems


def load_roster(
    path: Optional[Path] = None,
    store: Optional[Store] = None,
    include_inactive: bool = False,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Seed file merged with ``client:<slug>`` store records. The store wins,
    field by field, so a correction made by an operator survives a re-run."""
    notes = []  # type: List[str]
    path = path or ROSTER_SEED
    clients = []  # type: List[Dict[str, Any]]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        clients = list(data.get("clients") or [])
    except (OSError, ValueError) as exc:
        notes.append("roster_unreadable: %s (%s)" % (path, exc))

    if store is not None:
        by_slug = {c.get("slug"): c for c in clients}
        try:
            overrides = dict(store.items(STORE_CLIENT_PREFIX))
        except Exception as exc:  # noqa: BLE001 - a store miss must not lose the seed roster
            overrides = {}
            notes.append("store_unreadable: %s" % exc)
        for key, value in overrides.items():
            if not isinstance(value, dict):
                notes.append("store %s is not a record; ignored" % key)
                continue
            slug = value.get("slug") or key[len(STORE_CLIENT_PREFIX):]
            value = dict(value, slug=slug)
            if slug in by_slug:
                by_slug[slug].update(value)
            else:
                clients.append(value)
                by_slug[slug] = value

    for client in clients:
        notes.extend(_validate_client(client))
    if not include_inactive:
        clients = [c for c in clients if c.get("active")]
    return clients, notes


def self_client() -> Dict[str, Any]:
    """Advero's own six campaigns as a pseudo-client.

    Not a client and never invoiced. It exists so the renderer can be proved
    against live data without attributing Advero's numbers to somebody who
    would be billed for them.
    """
    return {
        "slug": "advero-internal",
        "name": "Lorenzo",
        "company": "Advero (internal)",
        "product": "internal",
        "product_name": "Advero's own outbound",
        "deal_type": "internal",
        "price_usd": None,
        "start_date": None,
        "term_days": None,
        "term_end": None,
        "attribution_window_days": None,
        "instantly_campaign_ids": [c["id"] for c in settings.CAMPAIGNS.values() if c.get("id")],
        "active": True,
        "internal": True,
        "notes": "Advero's own campaigns. Used to prove the scorecard against live data.",
    }


# --------------------------------------------------------------------- pulls
def pull_daily(
    instantly: Instantly,
    campaign_ids: List[str],
    start: date,
    end: date,
    notes: List[str],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """GET /campaigns/analytics/daily per campaign over [start, end].

    Returns ``(rows, failed_campaign_ids)``. The failures are returned rather
    than only noted because a pull that failed for every campaign must not be
    summed into zeros: a 500, a rotated key or an exhausted rate limit would
    otherwise print "Sent 0, Replies 0" on a client's card as a measurement and
    tell Lorenzo a healthy campaign had stopped.

    The daily endpoint is used rather than the windowed totals endpoint because
    it gives this week and last week from one call per campaign, and because a
    per-day series is what makes "sent nothing on Thursday" visible.
    """
    rows = []  # type: List[Dict[str, Any]]
    failed = []  # type: List[str]
    for cid in campaign_ids:
        try:
            data = instantly.daily_campaign_analytics(cid, _iso(start), _iso(end))
        except InstantlyError as exc:
            failed.append(cid)
            _add(notes, "daily_analytics_failed for %s: %s" % (cid, exc),
                 client="One of the campaigns behind this card could not be read this week.")
            continue
        if not isinstance(data, list):
            failed.append(cid)
            _add(notes, "daily_analytics for %s was %s, not a list" % (cid, type(data).__name__),
                 client="One of the campaigns behind this card could not be read this week.")
            continue
        for row in data:
            if isinstance(row, dict):
                rows.append(dict(row, campaign_id=cid))
    return rows, failed


def _row_replies(row: Dict[str, Any]) -> Tuple[int, int, int]:
    """(replies, unique_replies, automatic) off one daily row.

    ``unique_replies`` is the per-lead count (a lead who hits reply three times
    is one reply), which is what Section 6's rate wants; ``replies`` is the
    fallback when a row carries no unique variant.
    """
    replies = int(row.get("replies") or 0)
    unique = row.get("unique_replies")
    unique = replies if unique is None else int(unique or 0)
    auto = row.get("unique_replies_automatic")
    if auto is None:
        auto = row.get("replies_automatic")
    return replies, unique, int(auto or 0)


def sum_daily(rows: List[Dict[str, Any]], start: date, end: date) -> Dict[str, Any]:
    """Totals over [start, end] inclusive.

    **``replies`` already excludes auto-responders in this API, so nothing is
    subtracted here.** ``replies_automatic`` is a parallel counter, not a
    subset: in the recorded week three of the six campaigns report more
    automatic replies than replies at all ("2026 Bookkeeping - Trigger
    Outbound" is reply_count 1 with reply_count_automatic 6), which is
    impossible for a subset. Subtracting summed Sept 15-21 to 6 real replies on
    1,800 sent (0.33%) against a hand-measured 22 on 1,800 (1.22%), and then
    told the client to rewrite the first line of a sequence that was holding.
    Section 6's removal rule reads the same number, so the subtraction also fed
    a decision to strip sending capacity. ``services/retro/metrics.real_replies``
    documents the identical finding and does not subtract either.
    """
    out = {"sent": 0, "replies": 0, "replies_automatic": 0, "real_replies": 0,
           "contacted": 0, "opportunities": 0, "days_with_data": 0}
    for row in rows:
        day = parse_day(row.get("date"))
        if day is None or day < start or day > end:
            continue
        replies, unique, auto = _row_replies(row)
        out["days_with_data"] += 1
        out["sent"] += int(row.get("sent") or 0)
        out["replies"] += replies
        out["real_replies"] += unique
        out["replies_automatic"] += auto
        out["contacted"] += int(row.get("contacted") or 0)
        out["opportunities"] += int(row.get("opportunities") or 0)
    return out


def dedupe_leads(leads: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """One record per email address. Returns (leads, collapsed).

    The same address sits on two campaigns whenever a lead is moved or a list
    is uploaded twice, which is normal in this workspace (3,594 leads across
    six campaigns). Counting it twice doubles positives, booked, held and
    closed on the card and emits two attribution rows, which on a performance
    deal doubles the invoice. The surviving copy is the one furthest up the
    funnel, then the one that replied most recently.
    """
    best = {}  # type: Dict[str, Dict[str, Any]]
    order = []  # type: List[str]
    unkeyed = []  # type: List[Dict[str, Any]]
    collapsed = 0
    for lead in leads:
        email = _lower(lead.get("email"))
        if not email:
            unkeyed.append(lead)
            continue
        if email not in best:
            best[email] = lead
            order.append(email)
            continue
        collapsed += 1
        current = best[email]
        if _rank(lead) > _rank(current):
            best[email] = lead
    return [best[e] for e in order] + unkeyed, collapsed


def _rank(lead: Dict[str, Any]) -> Tuple[int, str]:
    try:
        status = int(lead.get("lt_interest_status"))
    except (TypeError, ValueError):
        status = -99
    return status, str(lead.get("timestamp_last_reply") or "")


def pull_leads(
    instantly: Instantly,
    campaign_ids: List[str],
    notes: List[str],
) -> Tuple[List[Dict[str, Any]], bool]:
    """Every lead on the client's campaigns, deduplicated by email.
    Returns (leads, truncated)."""
    leads = []  # type: List[Dict[str, Any]]
    truncated = False
    for cid in campaign_ids:
        try:
            walk = instantly.iterate("leads/list", body={"campaign": cid, "limit": 100},
                                     max_pages=MAX_LEAD_PAGES)
            for item in walk:
                if isinstance(item, dict):
                    leads.append(item)
            if getattr(walk, "truncated", False):
                truncated = True
                _add(notes, "lead pull for %s hit the %d page cap; counts are a floor"
                     % (cid, MAX_LEAD_PAGES),
                     client="Not every contact record could be read this week, so interested, "
                            "booked, held and closed are a floor rather than an exact count.")
        except InstantlyError as exc:
            truncated = True
            _add(notes, "lead_pull_failed for %s: %s" % (cid, exc),
                 client="Not every contact record could be read this week, so interested, "
                        "booked, held and closed are a floor rather than an exact count.")
    leads, collapsed = dedupe_leads(leads)
    if collapsed:
        _add(notes, "%d duplicate lead records were collapsed by email across the campaigns"
             % collapsed,
             client="%d contacts appear on more than one campaign and are counted once."
                    % collapsed)
    return leads, truncated


def count_statuses(
    leads: List[Dict[str, Any]],
    start: date,
    end: date,
) -> Dict[str, Any]:
    """Positives, booked, held and closed for the week.

    Instantly records only the latest interest-status change: a lead record
    carries ``lt_interest_status``, ``timestamp_last_reply`` and
    ``timestamp_last_interest_change``, and nothing that says when each earlier
    step (interested, booked, held) happened. So a lead counts into a week by
    its last reply. That is an approximation, it is stated on the scorecard,
    and the exact source is GHL's opportunity history once a token exists.

    The ladder is BOUNDED to the documented codes. A custom lead label carries
    its own value anywhere in -30000..30000, so ``status >= 4`` reads the first
    label anyone creates as a signed deal and puts it on the invoice. Measured:
    one lead with ``lt_interest_status: 1000`` produced positives 1, booked 1,
    held 1, closed 1 and a 50,000 dollar row in the revenue table.
    """
    out = {"positives": 0, "booked": 0, "held": 0, "closed": 0,
           "positives_all_time": 0, "closed_all_time": 0,
           "named": [], "undated": 0, "unknown_status": 0}
    for lead in leads:
        try:
            status = int(lead.get("lt_interest_status"))
        except (TypeError, ValueError):
            continue
        if status not in KNOWN_STATUSES:
            out["unknown_status"] += 1
            continue
        if status in FUNNEL_STATUSES:
            out["positives_all_time"] += 1
        if status == STATUS_CLOSED:
            out["closed_all_time"] += 1
        replied = parse_day(lead.get("timestamp_last_reply"))
        if replied is None:
            if status in FUNNEL_STATUSES:
                out["undated"] += 1
            continue
        if replied < start or replied > end:
            continue
        if status not in FUNNEL_STATUSES:
            continue
        out["positives"] += 1
        out["named"].append({
            "email": _lower(lead.get("email")),
            "company": lead.get("company_name"),
            "name": (" ".join(x for x in [lead.get("first_name"), lead.get("last_name")] if x)).strip(),
            "status": status,
            "replied": _iso(replied),
        })
        if status >= STATUS_BOOKED:
            out["booked"] += 1
        if status >= STATUS_HELD:
            out["held"] += 1
        if status >= STATUS_CLOSED:
            out["closed"] += 1
    return out


# --------------------------------------------------------------- attribution
def pull_won_values(
    ghl: Optional[GHL],
    client: Dict[str, Any],
    notes: List[str],
    close_dates: Optional[Dict[str, date]] = None,
) -> Tuple[Dict[str, float], Dict[str, date]]:
    """(email -> monetaryValue, email -> first touch) from the Won stage.

    ``close_dates``, when passed, is filled with email -> the CT date the deal
    moved into Won (``lastStageChangeAt``, else ``lastStatusChangeAt``). That is
    the close date the invoice period is keyed on. ``updatedAt`` is an edit
    time and is never read as a close.

    This is the EXACT source for a performance invoice: a number a human typed
    onto the deal when it closed. Without a GHL token there is none, and the
    scorecard falls back to the roster estimate, which is explicitly not
    invoiceable.

    The walk follows ``startAfterId``/``startAfter`` to the end. A single
    ``limit=100`` page silently drops a contact that closed this week but sits
    on page 2 once the Won stage holds more than a hundred deals: it loses its
    monetaryValue, falls to the roster estimate and is excluded from the
    invoice, so Lorenzo under-bills and nothing says the read was partial.
    ``pipeline_sync`` refuses a whole nightly apply for exactly this.
    """
    if ghl is None or not getattr(ghl, "token", None):
        notes.append("ghl_token_missing: contract values fall back to the roster estimate, "
                     "which is reported but never part of the billed figure")
        return {}, {}
    stage_id = settings.GHL_STAGES.get("won")
    out = {}  # type: Dict[str, float]
    touches = {}  # type: Dict[str, date]
    start_after_id = None  # type: Optional[str]
    start_after = None  # type: Any
    for _page in range(MAX_OPPORTUNITY_PAGES):
        try:
            page = ghl.search_opportunities(pipeline_id=settings.GHL_SALES_PIPELINE_ID,
                                            stage_id=stage_id, limit=100,
                                            start_after_id=start_after_id,
                                            start_after=start_after)
        except Exception as exc:  # noqa: BLE001 - a read failure is a note
            notes.append("ghl won-opportunity read failed: %s" % exc)
            return out, touches
        items = (page or {}).get("opportunities") if isinstance(page, dict) else None
        items = items or []
        for opp in items:
            contact = opp.get("contact") or {}
            email = _lower(contact.get("email") or opp.get("email"))
            value = opp.get("monetaryValue")
            if email and value:
                try:
                    out[email] = float(value)
                except (TypeError, ValueError):
                    notes.append("opportunity %s has a non-numeric monetaryValue" % opp.get("id"))
            touched = _first_touch_from_contact(contact)
            if email and touched:
                touches[email] = touched
            if email and close_dates is not None:
                closed_on = None
                for field in ("lastStageChangeAt", "lastStatusChangeAt"):
                    closed_on = parse_day(opp.get(field))
                    if closed_on:
                        break
                if closed_on:
                    close_dates[email] = closed_on
        if len(items) < 100:
            return out, touches
        last = items[-1]
        start_after_id = last.get("id")
        start_after = last.get("updatedAt") or last.get("dateUpdated")
        if not start_after_id:
            break
    notes.append("ghl_truncated: the Won stage read stopped at %d pages, so the attribution "
                 "table is partial" % MAX_OPPORTUNITY_PAGES)
    return out, touches


def _first_touch_from_contact(contact: Dict[str, Any]) -> Optional[date]:
    """``first_touch_date`` off a GHL contact, wherever GHL put it.

    products/reactivation_system/snapshot.md specifies it as a contact custom
    field, and GHL returns custom fields either flattened onto the contact or
    as a list of {id/key, value}.
    """
    if not isinstance(contact, dict):
        return None
    direct = parse_day(contact.get("first_touch_date"))
    if direct:
        return direct
    fields = contact.get("customFields") or contact.get("custom_fields") or []
    if isinstance(fields, dict):
        return parse_day(fields.get("first_touch_date"))
    for field in fields if isinstance(fields, list) else []:
        if not isinstance(field, dict):
            continue
        key = _lower(field.get("key") or field.get("name") or field.get("id"))
        if "first_touch" in key:
            return parse_day(field.get("value") or field.get("field_value"))
    return None


def first_touch_index(
    store: Optional[Store],
    leads: List[Dict[str, Any]],
    notes: List[str],
) -> Dict[str, date]:
    """``first_touch:<email>`` records out of the store, for the leads in hand.

    The lead record carries ``timestamp_last_contact`` and nothing else, so
    without this lookup (or the GHL custom field) a reactivation deal can never
    produce an invoice line at all. **Nothing writes these records yet**: the
    send path that would stamp the first touch is outside this job, which is
    why a closed contact with no stored value is reported as excluded with the
    reason rather than counted on an invented date.
    """
    if store is None:
        return {}
    out = {}  # type: Dict[str, date]
    for lead in leads:
        email = _lower(lead.get("email"))
        if not email or email in out:
            continue
        try:
            record = store.get(STORE_FIRST_TOUCH_PREFIX + email)
        except Exception as exc:  # noqa: BLE001 - a store miss must not lose the card
            notes.append("first-touch store read failed: %s" % exc)
            return out
        if isinstance(record, dict):
            record = record.get("first_touch_date") or record.get("date")
        touched = parse_day(record)
        if touched:
            out[email] = touched
    return out


def attribution_rows(
    leads: List[Dict[str, Any]],
    client: Dict[str, Any],
    now: datetime,
    won_values: Optional[Dict[str, float]] = None,
    first_touches: Optional[Dict[str, date]] = None,
    period: Optional[Tuple[date, date]] = None,
    close_dates: Optional[Dict[str, date]] = None,
) -> List[Dict[str, Any]]:
    """One row per contact that has closed, with the window arithmetic shown.

    ``first_touch`` is the FIRST sequence touch, which is what config/offers.md
    starts the clock on. The lead record only carries ``timestamp_last_contact``
    (the most recent touch), so a stored ``first_touch:<email>`` value or the
    GHL contact field is used when one exists and the row is flagged
    ``first_touch_source`` otherwise. A row whose first touch is unknown is
    never counted as revenue.

    ``period`` is this card's reporting window. Each row records whether the
    close happened inside it: without that, a close from August is re-invoiced
    on every weekly card until the attribution window expires.

    The close date is a CLOSE timestamp, never the lead's last reply: a
    contact who sends a thank-you three weeks after signing used to move the
    close into that later period and bill it again, and a contact who signed
    on a call without a new email was placed in an old period. In order: the
    GHL Won move (``close_dates``), a ``closed_at`` / ``close_date`` on the
    lead record, then Instantly's ``timestamp_last_interest_change`` on a lead
    whose status is closed (4), which is when the status became closed. With
    none of those the row has no close date and, when a period is asked for,
    is excluded rather than placed on a guess.

    ``attribution_window_days`` is never defaulted. A performance client with
    no window produces ``in_window: None`` and the card prints the reason
    instead of a number.
    """
    window_days = client.get("attribution_window_days")
    window_days = int(window_days) if window_days else None
    rows = []  # type: List[Dict[str, Any]]
    for lead in leads:
        try:
            status = int(lead.get("lt_interest_status"))
        except (TypeError, ValueError):
            continue
        if status != STATUS_CLOSED:
            continue
        email = _lower(lead.get("email"))
        payload = lead.get("payload") if isinstance(lead.get("payload"), dict) else {}
        first_touch = (parse_day(lead.get("first_touch_date"))
                       or parse_day(payload.get("first_touch_date"))
                       or (first_touches or {}).get(email))
        source = "recorded"
        if first_touch is None:
            first_touch = parse_day(lead.get("timestamp_last_contact"))
            source = "last_contact_fallback"
        closed, close_source = close_date_for(lead, payload, (close_dates or {}).get(email))
        deadline = (first_touch + timedelta(days=window_days)
                    if (first_touch and window_days) else None)
        in_window = None
        if first_touch and closed and deadline:
            in_window = closed <= deadline
        this_period = None
        period_position = None
        if period and closed:
            this_period = period[0] <= closed <= period[1]
            if closed < period[0]:
                period_position = "earlier"
            elif closed > period[1]:
                period_position = "later"
            else:
                period_position = "inside"
        elif period:
            this_period = "unknown"
        value = (won_values or {}).get(email)
        value_source = "ghl_opportunity" if value is not None else None
        if value is None and lead.get("contract_value"):
            value, value_source = lead.get("contract_value"), "lead_record"
        if value is None and client.get("value_per_close_usd"):
            value, value_source = client.get("value_per_close_usd"), "roster_estimate"
        rows.append({
            "email": email,
            "company": lead.get("company_name"),
            "first_touch": _iso(first_touch) if first_touch else None,
            "first_touch_source": source,
            "closed": _iso(closed) if closed else None,
            "close_source": close_source,
            "deadline": _iso(deadline) if deadline else None,
            "in_window": in_window,
            "this_period": this_period,
            "period_position": period_position,
            "value_usd": value,
            "value_source": value_source,
        })
    return rows


INVOICING_BY_HAND = ("Invoicing is tracked by hand and this job keeps no billing record, so the "
                     "same close can be counted on two cards, or on none. Before billing, check "
                     "every close on this week's invoice line against your own records. Also "
                     "check every close these notes list from an earlier period or dated after "
                     "this week's end: it may never have been on any invoice line. Why: a close's "
                     "date can move between weeks, earlier or later, when its source changes "
                     "(for example from an Instantly status-change date to a GHL Won date once "
                     "GHL is readable); a run off the Friday schedule covers a week that overlaps "
                     "the scheduled one; and a week whose card failed or did not run had no "
                     "invoice line at all.")

# Where each close date came from, in the operator's words (close_date_for).
CLOSE_SOURCE_LABELS = {
    "ghl_won_stage": "GHL Won",
    "lead_record": "lead close date",
    "interest_status_change": "Instantly status change",
}


def close_list(rows: List[Dict[str, Any]]) -> str:
    """"a@x.co closed 2026-09-22 (GHL Won), ..." for the operator notes."""
    return ", ".join("%s closed %s (%s)" % (
        r.get("email"), r.get("closed"),
        CLOSE_SOURCE_LABELS.get(r.get("close_source") or "", r.get("close_source") or "unknown source"))
        for r in rows)


def close_date_for(lead: Dict[str, Any], payload: Dict[str, Any],
                   ghl_close: Optional[date] = None) -> Tuple[Optional[date], Optional[str]]:
    """(the date this contact closed, where it came from), or (None, None).

    Never ``timestamp_last_reply``: a reply is not a close (see
    ``attribution_rows``)."""
    if ghl_close:
        return ghl_close, "ghl_won_stage"
    for source in (lead, payload):
        for key in ("closed_at", "close_date"):
            day = parse_day(source.get(key))
            if day:
                return day, "lead_record"
    try:
        status = int(lead.get("lt_interest_status"))
    except (TypeError, ValueError):
        status = None
    if status == STATUS_CLOSED:
        day = parse_day(lead.get("timestamp_last_interest_change"))
        if day:
            return day, "interest_status_change"
    return None, None


def revenue_attributed(
    rows: List[Dict[str, Any]],
    client: Dict[str, Any],
    measured: bool = True,
) -> Dict[str, Any]:
    """The invoice line, or an honest refusal.

    Countable = closed **inside this reporting period**, first touch recorded
    (not the fallback), inside the attribution window, and carrying a value.
    Everything else is listed as excluded with the reason, because on a
    performance deal the excluded rows are the conversation, not the footnote.

    A countable close from before this period goes to ``earlier_periods``:
    listed under the table, never added to the amount, and never labelled as
    billed or unbilled, because invoicing is tracked by hand and this job
    cannot know. (Calling such closes "already invoiced" was a guess that
    could hide an unbilled deal.) offers.md invoices performance deals monthly against this card, so a total
    with no period filter bills the same close every month.

    A close dated after this period's end (a late or off-schedule run) goes
    to ``later_periods``: never added to the amount, never printed under the
    earlier-period heading, and left off the client body. The operator notes
    list it.

    ``measured=False`` means nothing could be read at all (no campaigns, or
    every pull failed). Then ``invoiceable`` is None, not False: "there is
    nothing to invoice" is a measurement, and this run did not make one.
    """
    window_days = client.get("attribution_window_days")
    window_days = int(window_days) if window_days else None
    rate = client.get("commission_rate")
    if not measured:
        return {"counted": [], "excluded": [], "earlier_periods": [], "later_periods": [],
                "contract_value_usd": None, "commission_rate": rate, "commission_usd": None,
                "invoiceable": None, "estimated_usd": None, "window_days": window_days,
                "measured": False}
    counted = []  # type: List[Dict[str, Any]]
    excluded = []  # type: List[Dict[str, Any]]
    earlier = []  # type: List[Dict[str, Any]]
    later = []  # type: List[Dict[str, Any]]
    for row in rows:
        if row.get("this_period") == "unknown":
            excluded.append(dict(row, reason="no close date is recorded, so the period it "
                                             "closed in cannot be judged"))
            continue
        if row.get("in_window") is not True:
            if window_days is None:
                reason = ("no attribution window is set for this deal, so the clock cannot "
                          "be judged")
            elif row.get("in_window") is False:
                reason = "outside the window"
            elif not row.get("closed"):
                reason = "no close date is recorded, so the window cannot be judged"
            else:
                reason = "no first-touch date, so the window cannot be judged"
            excluded.append(dict(row, reason=reason))
            continue
        if row.get("first_touch_source") != "recorded":
            excluded.append(dict(row, reason="first touch inferred from the last contact, not recorded"))
            continue
        if not row.get("value_usd"):
            excluded.append(dict(row, reason="no contract value recorded"))
            continue
        if row.get("value_source") == "roster_estimate":
            # An estimate is a planning number. Invoicing one means billing a
            # client for a figure nobody wrote down at the time.
            excluded.append(dict(row, reason="value is the roster estimate, not a recorded "
                                             "contract value, so it is not invoiceable"))
            continue
        if row.get("this_period") is False:
            # A row with no position (built without a period split) keeps
            # the old behaviour: context, never counted.
            (later if row.get("period_position") == "later" else earlier).append(row)
            continue
        counted.append(row)
    total = sum(float(r["value_usd"]) for r in counted)
    estimated = sum(float(r["value_usd"]) for r in excluded
                    if r.get("value_source") == "roster_estimate" and r.get("in_window") is True)
    commission = None
    if rate and total:
        commission = round(total * float(rate), 2)
    return {
        "counted": counted,
        "excluded": excluded,
        "earlier_periods": earlier,
        "later_periods": later,
        "contract_value_usd": round(total, 2) if counted else None,
        "commission_rate": rate,
        "commission_usd": commission,
        "invoiceable": bool(counted),
        "estimated_usd": round(estimated, 2) if estimated else None,
        "window_days": window_days,
        "measured": True,
    }


# ---------------------------------------------------------- next week's plan
CLIENT_BETS_MODULE = "services.retro.lessons"
CLIENT_BETS_ATTR = "client_bets"
CLIENT_BETS_FREE_FLAG = "CLIENT_BETS_IS_FREE"


def _retro_renderer():
    """The one documented, non-billing per-client bets hook, or None.

    **Discovery by name is gone.** The previous version imported
    ``jobs.retro_packet`` (the module whose whole job is the paid Opus call)
    and called the first attribute named ``client_bets`` or
    ``next_week_bets_for_client`` it found, once per client per run, with none
    of retro_packet's week claim. The day brief A10 adds a function with one of
    those names, the weekly scorecard silently bills one unclaimed Opus call
    per client, and the ``except`` branch below catches a hook that raises, not
    one that is expensive.

    So the hook is now a single explicit import, and it is refused unless the
    module declares ``CLIENT_BETS_IS_FREE = True``: a hook that costs money has
    to say so before a per-client loop may call it.

    The A10 retro packet's own bets are deliberately NOT used here either.
    ``jobs/retro_packet.get_proposal`` proposes Advero's three bets from
    Advero's whole funnel, which is Lorenzo's plan, not a client's.
    """
    try:
        module = __import__(CLIENT_BETS_MODULE, fromlist=["*"])
    except Exception:  # noqa: BLE001 - absent or broken, both mean "use the fallback"
        return None
    fn = getattr(module, CLIENT_BETS_ATTR, None)
    if not callable(fn):
        return None
    if getattr(module, CLIENT_BETS_FREE_FLAG, False) is not True:
        logger.info("%s.%s exists but does not declare %s; using the built-in plan",
                    CLIENT_BETS_MODULE, CLIENT_BETS_ATTR, CLIENT_BETS_FREE_FLAG)
        return None
    return fn


def fallback_plan(client: Dict[str, Any], week: Dict[str, Any], prior: Dict[str, Any]) -> List[str]:
    """Three bets from the numbers, with no model call.

    Deterministic on purpose: the plan is the part of the scorecard a client
    reads twice, and it has to say the same thing to the same numbers.
    """
    bets = []  # type: List[str]
    sent = week.get("sent")
    real = week.get("real_replies")
    if sent in (None, NO_SOURCE) or not isinstance(sent, int):
        bets.append("Get this week's numbers into one place. Nothing here was measured, "
                    "so the first job is a source for sent and replies.")
        return bets
    if sent == 0:
        bets.append("Nothing sent this week. Find out why before changing anything else.")
    elif sent < MIN_SENDS_FOR_REPLY_VERDICT:
        # Section 6's line is "< 1% after 100 sent per inbox". On 25 or 40 sends
        # zero replies is the expected outcome, and a client in week one must
        # not be told to rewrite a sequence on that.
        bets.append("Only %d sent so far, which is too few to judge the reply rate. "
                    "Hold the copy and the list until there are %d."
                    % (sent, MIN_SENDS_FOR_REPLY_VERDICT))
    else:
        rate = (real or 0) / float(sent)
        if rate < 0.01:
            bets.append("Reply rate is %.1f%% on %d sent, which is under the 1%% line. "
                        "Change the first line of the sequence before changing the list."
                        % (rate * 100, sent))
        else:
            bets.append("Reply rate is %.1f%% on %d sent, which is holding. Keep the copy, "
                        "add volume." % (rate * 100, sent))
    positives = week.get("positives") or 0
    booked = week.get("booked") or 0
    if positives and booked == 0:
        bets.append("%s replied wanting to talk and did not get on the calendar. "
                    "That is the whole week's loss, and it is a speed problem, not a copy problem."
                    % _plural(positives, "person", "people"))
    elif positives and booked:
        bets.append("%d of %d interested replies booked. Hold that, and make the two offered "
                    "times the first thing in the answer." % (booked, positives))
    else:
        bets.append("No interested replies this week. Next week's change is the list, not the copy.")
    prior_sent = prior.get("sent") if isinstance(prior.get("sent"), int) else None
    if prior_sent is not None and isinstance(sent, int):
        if prior_sent == 0 and sent > 0:
            # Not "steady". Either last week is genuinely the first week, or the
            # comparison window has no data, and those read very differently.
            bets.append("There is nothing to compare against: last week shows no sends at all. "
                        "Either this is week one or the previous week is missing from the numbers.")
        elif prior_sent and sent < prior_sent * 0.8:
            bets.append("Volume fell from %d to %d. Check inbox health before reading anything "
                        "else on this page." % (prior_sent, sent))
        elif prior_sent and sent > prior_sent * 1.2:
            bets.append("Volume rose from %d to %d. Watch the bounce rate for a week before "
                        "raising it again." % (prior_sent, sent))
        else:
            bets.append("Volume is steady against last week (%d then, %d now)." % (prior_sent, sent))
    return bets[:3]


def next_week_plan(
    client: Dict[str, Any],
    week: Dict[str, Any],
    prior: Dict[str, Any],
    notes: List[str],
) -> Tuple[List[str], str]:
    """(bets, source). Prefers the A10 retro generator, falls back to rules."""
    renderer = _retro_renderer()
    if renderer is not None:
        try:
            bets = renderer(client=client, week=week, prior=prior)
            if isinstance(bets, str):
                bets = [line.strip("-* ") for line in bets.splitlines() if line.strip()]
            if bets:
                return list(bets)[:3], "retro_generator"
            notes.append("the per-client bets hook returned nothing; used the built-in plan")
        except Exception as exc:  # noqa: BLE001 - a broken hook must not lose the scorecard
            notes.append("the per-client bets hook failed (%s); used the built-in plan" % exc)
    return fallback_plan(client, week, prior), "this job's own rules, from this client's numbers"


# -------------------------------------------------------- retention (F4)
TERM_SCOPE = "term"
WEEK_SCOPE = "week"


class Template(object):
    def __init__(self, id, day, subject, body, requires, needs_price, auto_ok, path,
                 metrics_scope=WEEK_SCOPE):
        self.id = id
        self.day = day
        self.subject = subject
        self.body = body
        self.requires = requires
        self.needs_price = needs_price
        self.auto_ok = auto_ok
        self.path = path
        # "week" or "term". A template that says "the first 25 days" must be
        # filled from a start-date-to-now pull, never from the reporting week:
        # the day-25 note otherwise renders one week's 1,800 sends as the whole
        # term, and on the live path the window can be a single morning.
        self.metrics_scope = metrics_scope


def _truthy(value: str) -> bool:
    return _lower(value) in ("yes", "true", "1", "on")


def parse_template(text: str, path: str = "") -> Template:
    """Front matter between two '---' lines, then the body."""
    if not text.startswith("---"):
        raise ValueError("%s: no front matter" % path)
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("%s: front matter is not closed" % path)
    meta = {}  # type: Dict[str, str]
    for line in parts[1].splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    requires = [r.strip() for r in (meta.get("requires") or "").split(",") if r.strip()]
    if not meta.get("id") or not meta.get("day"):
        raise ValueError("%s: front matter needs id and day" % path)
    scope = _lower(meta.get("metrics_scope", "")) or WEEK_SCOPE
    if scope not in (TERM_SCOPE, WEEK_SCOPE):
        raise ValueError("%s: metrics_scope must be %r or %r, got %r"
                         % (path, TERM_SCOPE, WEEK_SCOPE, scope))
    return Template(
        id=meta["id"],
        day=int(meta["day"]),
        subject=meta.get("subject", ""),
        body=parts[2].lstrip("\n"),
        requires=requires,
        needs_price=_truthy(meta.get("needs_price", "")),
        auto_ok=_truthy(meta.get("auto_ok", "")),
        path=path,
        metrics_scope=scope,
    )


def load_templates(directory: Optional[Path] = None) -> Tuple[List[Template], List[str]]:
    directory = directory or RETENTION_DIR
    out = []  # type: List[Template]
    notes = []  # type: List[str]
    try:
        names = sorted(os.listdir(str(directory)))
    except OSError as exc:
        return [], ["retention templates unreadable: %s" % exc]
    for name in names:
        if not name.endswith(".md") or name == "README.md":
            continue
        path = directory / name
        try:
            with open(path, "r", encoding="utf-8") as fh:
                out.append(parse_template(fh.read(), str(path)))
        except (OSError, ValueError) as exc:
            notes.append("retention template %s skipped: %s" % (name, exc))
    return sorted(out, key=lambda t: t.day), notes


PLACEHOLDER_RE = re.compile(r"\{([a-z0-9_]+)\}")


def fill(text: str, values: Dict[str, Any]) -> Tuple[str, List[str]]:
    """Substitute {name}. An unknown placeholder is LEFT IN THE TEXT and
    reported, because a draft that silently contains nothing where a number
    should be is the one that goes out wrong."""
    missing = []  # type: List[str]

    def _sub(match):
        key = match.group(1)
        value = values.get(key)
        if value is None or value == "":
            missing.append(key)
            return match.group(0)
        return str(value)

    return PLACEHOLDER_RE.sub(_sub, text), sorted(set(missing))


MONEY_RE = re.compile(
    r"\$\s*(\d[\d,]*(?:\.\d+)?)\s*([kKmM])?"
    r"(?:\s*(?:-|–|—|to)\s*(\d[\d,]*(?:\.\d+)?)\s*([kKmM])?)?")
MULTIPLIER = {"k": 1000.0, "m": 1000000.0}
# A line the offer sheet itself marks unconfirmed is not a price that may be
# written down. offers.md carries "$2,500-5,000/mo (TO CONFIRM with Lorenzo
# before quoting in writing)" and the old substring test passed 2500 anyway.
UNCONFIRMED_MARKERS = ("to confirm",)
# The proof-point figures are somebody else's numbers ($150M/year roofer, a
# $1.5k build, $6M recovered). They are quotable as proof and are not prices,
# so they must not validate a price.
PROOF_HEADINGS = ("proof point",)


def _money_values(fragment: str) -> List[float]:
    """Every dollar amount in a fragment, both ends of a range included.

    The upper bound of a range has to be bigger than the lower one, or "$500 to
    2 contacts" reads as a 500-to-2 range and puts a stray 2 in the set.
    """
    out = []  # type: List[float]
    for match in MONEY_RE.finditer(fragment):
        low = _as_money(match.group(1), match.group(2))
        high = _as_money(match.group(3), match.group(4))
        if low is not None:
            out.append(low)
        if high is not None and (low is None or high > low):
            out.append(high)
    return out


def _as_money(digits: Optional[str], suffix: Optional[str]) -> Optional[float]:
    if not digits:
        return None
    try:
        value = float(digits.replace(",", ""))
    except ValueError:
        return None
    return value * MULTIPLIER.get(_lower(suffix), 1.0)


CLAUSE_SPLIT_RE = re.compile(r"\||;|(?<!\d)\.(?!\d)")


def _clauses(line: str) -> List[str]:
    """One markdown table cell can hold a whole offer, so "TO CONFIRM" has to
    be tested against the clause it qualifies, not the line. Splitting on the
    line would drop the guarantee figure that shares a cell with it, and
    splitting on every dot would break "$1.5k" in half."""
    return [c for c in CLAUSE_SPLIT_RE.split(line) if c.strip()]


def offer_figures(offers_md: Optional[str] = None) -> set:
    """Every dollar figure config/offers.md states as a PRICE.

    A set, not a substring search. ``"%d" % amount in text`` passed 50 (inside
    "150"), 15 (inside "15,000"), 500 (inside "2,500") and 1, and refused 1500
    and 750, so the only guard on money in client-facing copy guarded nothing.
    Lines the sheet marks "TO CONFIRM" and the proof-point table are excluded:
    both carry dollar figures that are not this product's price.
    """
    text = offers_md if offers_md is not None else settings.OFFERS_MD
    figures = set()
    if not text:
        return figures
    in_proof = False
    for line in text.splitlines():
        lowered = line.lower()
        if lowered.startswith("#"):
            in_proof = any(h in lowered for h in PROOF_HEADINGS)
            continue
        if in_proof:
            continue
        for clause in _clauses(line):
            if any(m in clause.lower() for m in UNCONFIRMED_MARKERS):
                continue
            for value in _money_values(clause):
                figures.add(value)
    return figures


def price_in_offers(amount: Any, offers_md: Optional[str] = None) -> bool:
    """True when the figure is one config/offers.md states as a price. The
    offer sheet is the only source for a number Lorenzo puts in front of
    anyone."""
    if amount in (None, ""):
        return False
    try:
        number = float(amount)
    except (TypeError, ValueError):
        return False
    return number in offer_figures(offers_md)


SPELLED_MONEY_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([kKmM])?\s*dollars?\b", re.I)


def unapproved_prices(text: str, offers_md: Optional[str] = None) -> List[str]:
    """Dollar figures written in a draft that the offer sheet does not price.

    The ``needs_price`` gate checks a roster field, and ``day25_renewal.md``
    has no price placeholder at all: its money lives inside ``renewal_terms``,
    operator free text that reaches the reader unchecked. So the rendered body
    is scanned too.
    """
    allowed = offer_figures(offers_md)
    found = []  # type: List[float]
    for match in MONEY_RE.finditer(text or ""):
        found.extend(_money_values(match.group(0)))
    # "2,000 dollars" is the same promise as "$2,000". A bare number is not:
    # "1,800 sent" is a count, and flagging it would block a true draft.
    for match in SPELLED_MONEY_RE.finditer(text or ""):
        value = _as_money(match.group(1), match.group(2))
        if value is not None:
            found.append(value)
    bad = []  # type: List[str]
    for value in found:
        if value not in allowed and _money(value) not in bad:
            bad.append(_money(value))
    return bad


def _roll_to_business_day(day: date) -> date:
    """A touch that lands on a Saturday goes out on the Monday.

    Day 30 from Mike's 2026-09-17 start is 2026-10-17, a Saturday. Nothing here
    sends, but the rest of the cadence holds 07:00-19:00 CT Mon-Fri
    (``shared.settings.SEND_WINDOW`` / ``SLOT_WINDOW``) and a due date that
    quietly breaks it puts a weekend date on Lorenzo's list and in a filename.
    """
    while not slots.is_business_day(day):
        day = day + timedelta(days=1)
    return day


def retention_key(slug: Optional[str], template_id: str) -> str:
    return "%s%s:%s" % (STORE_RETENTION_PREFIX, slug or "unknown", template_id)


def _handled(store: Optional[Store], slug: Optional[str], template_id: str) -> Optional[str]:
    """The ``handled_at`` stamp for a touch that has been dealt with, or None."""
    if store is None:
        return None
    try:
        record = store.get(retention_key(slug, template_id))
    except Exception:  # noqa: BLE001 - a store miss must not hide a due touch
        return None
    if isinstance(record, dict):
        return record.get("handled_at") or record.get("sent_at")
    return None


def mark_retention_handled(store: Store, slug: str, template_id: str, now: datetime) -> Dict[str, Any]:
    """Retire a touch. ``--mark-handled <slug>:<template_id>`` writes this.

    Local store only: no live system is touched. Rendering alone does NOT
    retire a touch, because the runbook regenerates Mike's drafts on purpose
    and a render-retires rule would make the second run produce nothing.
    """
    record = {"handled_at": now.astimezone(settings.TZ).isoformat(), "slug": slug,
              "template_id": template_id}
    store.set(retention_key(slug, template_id), record)
    return record


def due_retention(
    client: Dict[str, Any],
    now: datetime,
    templates: List[Template],
    lookahead_days: int = 7,
    store: Optional[Store] = None,
    max_overdue_days: int = MAX_OVERDUE_DAYS,
    notes: Optional[List[str]] = None,
) -> List[Tuple[Template, date, int]]:
    """(template, due_date, days_until) for touches due within the lookahead,
    plus anything overdue by no more than ``max_overdue_days``. Day 0 is the
    kickoff call.

    Two bounds, both because an alert that is always on is an alert nobody
    reads. A touch already marked handled in the store is gone, and a touch
    more than ``max_overdue_days`` past due is gone: without the floor, Mike's
    four touches came back on every run at -26, -68 and -250 days, and
    ``run_scorecards`` sets the digest to high priority whenever anything is
    overdue.
    """
    start = parse_day(client.get("start_date"))
    if start is None:
        return []
    today = now.astimezone(settings.TZ).date()
    out = []  # type: List[Tuple[Template, date, int]]
    for template in templates:
        due = _roll_to_business_day(start + timedelta(days=template.day))
        delta = (due - today).days
        if delta > lookahead_days:
            continue
        handled_at = _handled(store, client.get("slug"), template.id)
        if handled_at:
            if notes is not None:
                _add(notes, "day %d touch for %s was marked handled on %s; not re-drafted"
                     % (template.day, client.get("slug"), handled_at))
            continue
        if delta < -max_overdue_days:
            if notes is not None:
                _add(notes, "day %d touch for %s is %d days past due and is no longer listed; "
                            "mark it handled or move the start date"
                     % (template.day, client.get("slug"), -delta))
            continue
        out.append((template, due, delta))
    return out


def render_retention(
    template: Template,
    client: Dict[str, Any],
    due: date,
    days_until: int,
    week: Dict[str, Any],
    now: datetime,
    offers_md: Optional[str] = None,
    term: Optional[Dict[str, Any]] = None,
    render_mod: Any = None,
    replay: bool = False,
) -> Dict[str, Any]:
    """One draft. ``ready`` is False whenever a required number is missing, a
    quoted price is not in config/offers.md, or the rendered copy breaks the
    client-copy rules.

    ``term`` is the start-date-to-now aggregate and is what a ``metrics_scope:
    term`` template is filled from. The day-21 and day-25 notes describe the
    term ("What the first 25 days produced"), so filling them from the
    reporting week put a seven-day 1,800 into an email about 25 days, and on
    the live path the window can be a single morning.
    """
    if template.metrics_scope == TERM_SCOPE:
        # No fallback to the week, ever. A term template with no term numbers
        # is blocked, because the alternative is an email that calls one week
        # "the first 25 days".
        source = term or {}
    else:
        source = week or {}
    values = {
        "first_name": client.get("name"),
        "company": client.get("company"),
        "product": client.get("product_name") or client.get("product"),
        "term_end": client.get("term_end"),
        # The day the touch is FOR, not the day it was rendered. A day-25 note
        # drafted three weeks early otherwise opens "what the first 5 days
        # produced", which is both wrong and obviously machine-made.
        "days_elapsed": template.day,
        "review_link": client.get("review_link"),
        "renewal_terms": client.get("renewal_terms"),
        "expansion_line": client.get("expansion_line"),
        "starting_point": client.get("starting_point"),
        "what_we_built": client.get("what_we_built"),
        "quote_placeholder": client.get("client_quote"),
        "headline": client.get("headline"),
    }
    for key in ("sent", "replies", "real_replies", "positives", "booked", "held", "closed"):
        value = source.get(key)
        values[key] = value if isinstance(value, int) else None
    # What the numbers actually cover, so a term draft can say it out loud
    # instead of implying the figures run to the due date.
    values["metrics_through"] = source.get("through")
    values["days_measured"] = source.get("days_measured")
    if template.metrics_scope == WEEK_SCOPE:
        values["metrics_through"] = week.get("through")
        values["days_measured"] = week.get("days_measured")

    blockers = []  # type: List[str]
    for name in template.requires:
        if values.get(name) in (None, ""):
            blockers.append("missing metric: %s" % name)
    subject, missing_subject = fill(template.subject, values)
    body, missing_body = fill(template.body, values)
    for name in sorted(set(missing_subject + missing_body)):
        marker = "missing metric: %s" % name
        if marker not in blockers:
            blockers.append("unfilled placeholder: {%s}" % name)
    if template.needs_price:
        price = client.get("renewal_price_usd") or client.get("price_usd")
        if not price_in_offers(price, offers_md):
            blockers.append(
                "price %s is not in config/offers.md, so it cannot be quoted in writing"
                % (_money(price) if price is not None else "(none set)"))
    # The roster's free-text fields (renewal_terms, expansion_line, headline,
    # client_quote, starting_point, what_we_built) are substituted verbatim and
    # are the only unchecked text in a client email. An em dash or an
    # exclamation mark typed into one of them used to ship inside a draft
    # marked READY, and a dollar figure typed into renewal_terms reached the
    # reader without ever meeting the offer sheet.
    rendered = "%s\n\n%s" % (subject, body)
    for problem in copy_problems(rendered, render_mod if render_mod is not None else _copy_checker()):
        blockers.append("copy rules: the draft %s" % problem)
    for figure in unapproved_prices(rendered, offers_md):
        blockers.append("%s is written in this draft and is not a price in config/offers.md"
                        % figure)
    if replay:
        blockers.append(REPLAY_STAMP)
    ready = not blockers
    return {
        "template_id": template.id,
        "day": template.day,
        "due": _iso(due),
        "days_until": days_until,
        "overdue": days_until < 0,
        "metrics_scope": template.metrics_scope,
        "subject": subject,
        "body": body,
        "ready": ready,
        "auto_ok": template.auto_ok and ready,
        "blockers": blockers,
        "replay": replay,
        "client": client.get("slug"),
    }


_COPY_CHECKER = []  # type: List[Any]


def _copy_checker():
    """``services.retro.render`` once per process, or None."""
    if not _COPY_CHECKER:
        _COPY_CHECKER.append(retro_modules()[2])
    return _COPY_CHECKER[0]


def _as_count(value: Any) -> Optional[int]:
    """A whole count, or None. Never a float: these are people and emails."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(round(number))


def _plural(count: Any, singular: str, plural: Optional[str] = None) -> str:
    return "%s %s" % (count, singular if count == 1 else (plural or singular + "s"))


RETRO_METRIC_MAP = {"sent": "sent", "real_replies": "real_replies", "positives": "positives",
                    "booked": "booked", "held": "held", "closes": "closed"}


def _adopt_retro_numbers(client, week, prior, week_obj, scorecard_mod):
    """Overwrite this module's funnel figures with the A10 card's own."""
    try:
        metrics = scorecard_mod.client_funnel(week_obj, campaign_keys_for(client) or None)
    except Exception:  # noqa: BLE001 - keep this module's numbers if A10 cannot count
        return week, prior, False
    week, prior = dict(week), dict(prior)
    for metric in metrics:
        key = RETRO_METRIC_MAP.get(getattr(metric, "key", ""))
        if not key:
            continue
        # A10 carries its funnel as floats. Everything downstream (the plan's
        # isinstance checks, the digest, the drafts) expects counts, and a
        # draft that says "300.0 sent" is not sendable.
        week[key] = _as_count(getattr(metric, "this_week", None))
        prior[key] = _as_count(getattr(metric, "last_week", None))
    # The card has no "every reply" line, so neither does the digest.
    week["replies"] = week.get("real_replies")
    prior["replies"] = prior.get("real_replies")
    return week, prior, True


def _window_days(week_obj: Any):
    """((start, end), (prior_start, prior_end)) in Central dates from an A10
    Week, or None. ``end_date`` is the window's last day; both windows are
    inclusive here, the way every other date in this job is."""
    try:
        this_start = parse_day(week_obj.this_window.start_date)
        this_end = parse_day(week_obj.this_window.end_date)
        last_start = parse_day(week_obj.last_window.start_date)
        last_end = parse_day(week_obj.last_window.end_date)
    except Exception:  # noqa: BLE001
        return None
    if not all((this_start, this_end, last_start, last_end)):
        return None
    return (this_start, this_end), (last_start, last_end)


# -------------------------------------------------- the A10 retro renderer
def retro_modules():
    """(collect, scorecard, render) from brief A10, or (None, None, None).

    ``services/retro/scorecard.py`` says in its own docstring that A12 does not
    need its own generator, and it is right: it renders the client card in
    Nick's agenda shape and runs the offer-sheet copy rules over the result.
    This job owns the roster, the attribution table, the retention drafts and
    the CLI; A10 owns the card. The built-in renderer below stays as the
    fallback, because a shared module that is mid-build must not be able to
    take the scorecard down with it.
    """
    try:
        from services.retro import collect as collect_mod
        from services.retro import render as render_mod
        from services.retro import scorecard as scorecard_mod
    except Exception:  # noqa: BLE001 - absent or broken both mean "use the fallback"
        return None, None, None
    return collect_mod, scorecard_mod, render_mod


def campaign_keys_for(client: Dict[str, Any]) -> List[str]:
    """Roster campaign ids to the campaign KEYS the A10 renderer wants."""
    out = []  # type: List[str]
    for cid in client.get("instantly_campaign_ids") or []:
        meta = settings.CAMPAIGN_BY_ID.get(cid) or {}
        if meta.get("key"):
            out.append(meta["key"])
    return out


def agenda(client, week, drafts, notes):
    """(wins, next_steps, open_questions) for Nick's agenda, from the numbers.

    Deterministic. A win the client cannot see in the table is not a win.
    """
    wins = []  # type: List[str]
    steps = []  # type: List[str]
    questions = []  # type: List[str]
    booked, positives = week.get("booked"), week.get("positives")
    if isinstance(booked, int) and booked:
        wins.append("%s booked this week." % _plural(booked, "call"))
    if isinstance(positives, int) and positives and not booked:
        wins.append("%s replied wanting to talk."
                    % _plural(positives, "person", "people"))
        steps.append("Get %s on the calendar. That is this week's whole job."
                     % ("that one" if positives == 1 else "those %d" % positives))
    if isinstance(week.get("closed"), int) and week.get("closed"):
        wins.append("%d signed." % week["closed"])
    # Nothing about the retention drafts goes here. This is the CLIENT body:
    # "The day 25 note (due ...) is written but cannot go out yet: <blocker>"
    # told the client a renewal note was scheduled for them and quoted an
    # internal blocker. The schedule and the blockers live in the operator
    # appendix only. ``drafts`` stays in the signature for callers.
    if any("no source" in n or "no instantly_campaign_ids" in n for n in notes):
        questions.append("Some of this week's numbers have no source yet, so they are left out "
                         "rather than shown as zero.")
    return wins, steps, questions


def render_with_retro(
    client: Dict[str, Any],
    week: Dict[str, Any],
    attribution: Optional[Dict[str, Any]],
    plan: List[str],
    drafts: List[Dict[str, Any]],
    notes: List[str],
    week_obj: Any,
    scorecard_mod: Any,
    render_mod: Any,
) -> Optional[str]:
    """The A10 card, or None if it could not be produced (the caller falls back)."""
    try:
        wins, steps, questions = agenda(client, week, drafts, notes)
        revenue = attribution.get("contract_value_usd") if attribution else None
        packet = scorecard_mod.build_client_scorecard(
            week_obj,
            client_name=client.get("company") or client.get("slug"),
            campaign_keys=campaign_keys_for(client) or None,
            wins=wins, next_steps=steps, open_questions=questions,
            attributed_revenue=revenue, plan=plan,
        )
        return scorecard_mod.render_client_scorecard(packet)
    except Exception as exc:  # noqa: BLE001 - including ClientCopyError
        notes.append("A10 client card not produced (%s); used the built-in renderer" % exc)
        return None


def copy_problems(text: str, render_mod: Any) -> List[str]:
    """Offer-sheet copy rules over anything a client could read. Empty when the
    checker is unavailable, and that absence is itself noted by the caller."""
    if render_mod is None:
        return []
    try:
        return list(render_mod.check_client_copy(text))
    except Exception:  # noqa: BLE001
        return []


# ------------------------------------------------------------------- render
def _cell(value: Any) -> str:
    if value is None:
        return NO_SOURCE
    if isinstance(value, float) and abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return str(value)


def render_scorecard(
    client: Dict[str, Any],
    week: Dict[str, Any],
    prior: Dict[str, Any],
    start: date,
    end: date,
    attribution: Optional[Dict[str, Any]],
    plan: List[str],
    plan_source: str,
    drafts: List[Dict[str, Any]],
    notes: List[str],
    replay: bool = False,
) -> str:
    """The CLIENT body. The retention schedule, the blockers and the run notes
    are Lorenzo's and live in ``render_operator_appendix``."""
    lines = []  # type: List[str]
    lines.append("# %s, week ending %s" % (client.get("company") or client.get("slug"), _iso(end)))
    lines.append("")
    if replay:
        lines.append("> %s. Do not send." % REPLAY_STAMP)
        lines.append("")
    lines.append("%s. Week of %s to %s." % (client.get("product_name") or client.get("product") or "",
                                            _iso(start), _iso(end)))
    lines.append("")
    lines.append("| | This week | Last week |")
    lines.append("| --- | --- | --- |")
    for label, key in (("Sent", "sent"), ("Replies from a person", "real_replies"),
                       ("Out of office and other automatic answers", "replies_automatic"),
                       ("Interested", "positives"),
                       ("Booked", "booked"), ("Held", "held"), ("Closed", "closed")):
        lines.append("| %s | %s | %s |" % (label, _cell(week.get(key)), _cell(prior.get(key))))
    lines.append("")

    lines.extend(_attribution_lines(attribution))
    lines.append("## Next week")
    lines.append("")
    for bet in plan:
        lines.append("- %s" % bet)
    lines.append("")
    lines.extend(_footer_lines(notes))
    return "\n".join(lines)


def render_operator_appendix(
    client: Dict[str, Any],
    start: date,
    end: date,
    plan_source: str,
    card_source: str,
    drafts: List[Dict[str, Any]],
    notes: List[str],
    replay: bool = False,
) -> str:
    """Everything that is Lorenzo's and not the client's.

    The retention schedule, the draft blockers (which quote config/offers.md
    and name what is missing from the account) and the engineering notes used
    to sit on the same page as the table. A client reading their own card
    learned that a renewal note was scheduled for day 25, that their price was
    not in Lorenzo's offer sheet, and that their account had no campaigns
    wired up.
    """
    lines = ["# Operator notes: %s, week ending %s"
             % (client.get("company") or client.get("slug"), _iso(end)),
             "",
             "Internal. Not the document that goes to the client "
             "(that is scorecard_%s.md)." % _iso(end),
             ""]
    if replay:
        lines.append("> %s. Nothing here may be sent to anyone." % REPLAY_STAMP)
        lines.append("")
    lines.append("- reporting week: %s to %s" % (_iso(start), _iso(end)))
    lines.append("- card produced by: %s" % card_source)
    lines.append("- next week's plan produced by: %s" % plan_source)
    lines.append("")
    lines.extend(_retention_lines(drafts))
    if notes:
        lines.append("## Notes from this run")
        lines.append("")
        for note in notes:
            lines.append("- %s" % note)
        lines.append("")
    return "\n".join(lines)


def _attribution_lines(attribution: Optional[Dict[str, Any]]) -> List[str]:
    """The invoice basis. Appended to whichever renderer produced the card,
    because a performance client's card without the named contacts and the
    window is not an invoice, it is a claim."""
    lines = []  # type: List[str]
    if attribution is None:
        return lines
    lines.append("## Revenue attributed")
    lines.append("")
    if attribution.get("measured") is False:
        lines.append(attribution.get("unmeasured_reason") or
                     "No source: the campaigns behind this deal are not connected to this "
                     "report yet, so nothing here can be billed or ruled out.")
        lines.append("")
        return lines
    if attribution.get("window_days"):
        lines.append("Attribution window: **%d days** from the first sequence touch "
                     "(config/offers.md)." % attribution["window_days"])
    else:
        # Defaulting the window silently would invoice against a period nobody
        # agreed to, so the card prints the reason instead of a number.
        lines.append("Attribution window: **not set for this deal**, so no close can be "
                     "judged against it and nothing here is invoiceable until it is agreed "
                     "in writing.")
    lines.append("")
    if attribution["counted"]:
        lines.append("Closed in this reporting period:")
        lines.append("")
        lines.append("| Contact | First touch | Closed | Deadline | Value |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in attribution["counted"]:
            lines.append("| %s | %s | %s | %s | %s |" % (
                row.get("company") or row.get("email"), row.get("first_touch"),
                row.get("closed"), row.get("deadline"), _money(row.get("value_usd"))))
        lines.append("")
        lines.append("**Contract value closed this period: %s**"
                     % _money(attribution["contract_value_usd"]))
        if attribution.get("commission_usd") is not None:
            lines.append("")
            lines.append("Commission at %s: **%s**"
                         % (_rate_label(attribution["commission_rate"]),
                            _money(attribution["commission_usd"])))
        elif not attribution.get("commission_rate"):
            lines.append("")
            lines.append("No commission rate is recorded for this deal, so the amount owed is "
                         "not stated here. It is agreed before this card becomes an invoice.")
    else:
        lines.append("No contact closed inside the window during this reporting period, so "
                     "there is nothing new to invoice.")
    if attribution.get("earlier_periods"):
        # No billing state, either way: invoicing is tracked by hand.
        lines.append("")
        lines.append("Closed in an earlier period, not part of this week's figure:")
        lines.append("")
        for row in attribution["earlier_periods"]:
            lines.append("- %s closed %s: %s" % (row.get("company") or row.get("email"),
                                                 row.get("closed"), _money(row.get("value_usd"))))
    if attribution["excluded"]:
        lines.append("")
        lines.append("Not counted:")
        lines.append("")
        for row in attribution["excluded"]:
            lines.append("- %s: %s" % (row.get("company") or row.get("email"), row.get("reason")))
    if attribution.get("estimated_usd"):
        lines.append("")
        lines.append("An estimate of %s sits behind those exclusions. It is not part of the "
                     "figure above."
                     % _money(attribution["estimated_usd"]))
    lines.append("")
    return lines


def _rate_label(rate: Any) -> str:
    try:
        return "%g%%" % (float(rate) * 100)
    except (TypeError, ValueError):
        return str(rate)


def _retention_lines(drafts: List[Dict[str, Any]]) -> List[str]:
    lines = []  # type: List[str]
    if drafts:
        lines.append("## Retention touches due")
        lines.append("")
        for draft in drafts:
            state = "READY" if draft["ready"] else "NOT READY"
            when = "overdue by %d days" % (-draft["days_until"]) if draft["overdue"] else (
                "due in %d days" % draft["days_until"])
            lines.append("- day %d, %s (%s): %s" % (draft["day"], draft["due"], when, state))
            for blocker in draft["blockers"]:
                lines.append("    - %s" % blocker)
        lines.append("")
    return lines


COUNTED_BY_LAST_REPLY = "last_reply"
COUNTED_BY_RETRO = "retro"


def _footer_lines(notes: List[str], counted_by: str = COUNTED_BY_LAST_REPLY) -> List[str]:
    """The client's "how to read this", plus the caveats that change how a
    number reads. A count that is a floor has to carry that with it, and the
    A10 card used to drop this block entirely.

    ``counted_by`` says which card the footer sits under, because the two count
    the week differently and the footer has to describe the numbers above it:
    the built-in card places a contact by its last reply, the weekly-retro
    (A10) card by the date its status last changed."""
    lines = ["## How to read this", ""]
    lines.append("- Replies from a person counts one reply per contact. Out of office and "
                 "other automatic answers are counted on their own line and are never mixed "
                 "into it.")
    if counted_by == COUNTED_BY_RETRO:
        lines.append("- Interested, booked, held and signed are counted into the week by the date "
                     "the contact's status last changed (or, when that is not on record, their "
                     "last reply or the last update to their record). Each contact is counted "
                     "once, at the furthest step they have reached, even when they are on more "
                     "than one campaign.")
    else:
        # Byte-identical to the committed drafts under changesets/onboarding.
        lines.append("- In the weekly table, interested, booked, held and closed are counted into "
                     "the week by the date of the contact's last reply. The sending platform "
                     "records the date a status last changed but not the date of each earlier "
                     "step, so the table uses the reply date for every step. A contact whose "
                     "status moves in a later week without a new reply will not move between "
                     "weeks in the table.")
    lines.append("- A cell reading \"%s\" means there was nothing to measure, not that the "
                 "number was zero." % NO_SOURCE)
    client_notes = notes.client_facing() if isinstance(notes, Notes) else []
    if client_notes:
        lines.append("")
        lines.append("Worth knowing about this week's numbers:")
        lines.append("")
        for note in client_notes:
            lines.append("- %s" % note)
    # "Lorenzo" is not decoration: render.check_client_copy requires the
    # signature on anything a client could read, and the built-in card has to
    # pass the same check the A10 card passes.
    lines.extend(["", "Lorenzo"])
    return lines


# ---------------------------------------------------------------------- run
def run_client(
    client: Dict[str, Any],
    now: datetime,
    instantly: Optional[Instantly],
    templates: List[Template],
    week_ending: Optional[date] = None,
    leads: Optional[List[Dict[str, Any]]] = None,
    daily: Optional[List[Dict[str, Any]]] = None,
    ghl: Optional[GHL] = None,
    extra_notes: Optional[List[str]] = None,
    lookahead_days: int = 7,
    week_obj: Any = None,
    scorecard_mod: Any = None,
    render_mod: Any = None,
    store: Optional[Store] = None,
    replay: bool = False,
) -> Dict[str, Any]:
    notes = Notes(extra_notes or [])
    lead_rows = []  # type: List[Dict[str, Any]]
    start, end = week_bounds(now, week_ending)
    prior_start, prior_end = start - timedelta(days=7), start - timedelta(days=1)
    roster_ids = [c for c in (client.get("instantly_campaign_ids") or []) if c]
    use_retro_card = week_obj is not None and scorecard_mod is not None and week_ending is None
    if use_retro_card and not roster_ids and not client.get("internal"):
        # scorecard.client_funnel treats campaign_keys=None as EVERY campaign.
        # For a client with no campaigns of their own that would put the whole
        # of Advero's outbound on their card as if it were theirs. The built-in
        # renderer says "no source" instead, which is the truth.
        use_retro_card = False
        notes.add("no campaigns are assigned to %s, so the weekly-retro card is not used: it "
                  "would report every campaign as theirs. Columns read \"%s\" instead"
                  % (client.get("slug"), NO_SOURCE))
    elif use_retro_card and not campaign_keys_for(client) and not client.get("internal"):
        # The client HAS campaigns, they are simply not registered in
        # config/ids.json, so A10 cannot slice them. Telling the client "no
        # campaigns are assigned to you" under a table of their own real sends
        # is a card that contradicts itself in front of the person paying for
        # it, which is what the old shared branch did.
        use_retro_card = False
        notes.add("the campaigns for %s are not registered in config/ids.json, so the "
                  "weekly-retro card cannot slice them; the built-in renderer is used with "
                  "this job's own counts" % client.get("slug"))
    if use_retro_card:
        # Align to the A10 window or do not use its card at all. The retro's week
        # is Monday 00:00 CT to now; this job's default is the seven days ending
        # yesterday. Rendering the A10 table over one window while the plan, the
        # attribution and the retention dates are computed over another puts two
        # different sets of numbers on the same page in front of a client. Seen
        # live on 2026-09-22: the table said 300 sent and the plan underneath it
        # said 1800.
        aligned = _window_days(week_obj)
        if aligned is None:
            use_retro_card = False
            notes.add("the A10 week could not be read as dates; used the built-in renderer")
        elif (aligned[0][1] - aligned[0][0]).days < 6:
            # A10's window is Monday 00:00 CT to now, so on any day but Friday
            # evening it is one or two days. Adopting it wholesale printed
            # "week ending 2026-09-22, 300 sent" for a week that really sent
            # 1,800, and for a performance deal that document is the invoice.
            # The word "week" means seven days here or the card is not produced.
            use_retro_card = False
            notes.add("the weekly retro's window is %s to %s, which is %d day(s), so it was not "
                      "used: this card's week is always the seven days %s to %s"
                      % (_iso(aligned[0][0]), _iso(aligned[0][1]),
                         (aligned[0][1] - aligned[0][0]).days + 1, _iso(start), _iso(end)),
                      client=None)
        else:
            (start, end), (prior_start, prior_end) = aligned
            notes.add("reporting week follows the weekly retro: %s to %s" % (_iso(start), _iso(end)))
    campaign_ids = roster_ids

    unmeasured_reason = None  # type: Optional[str]
    if not campaign_ids and daily is None and leads is None:
        unmeasured_reason = ("no instantly_campaign_ids in the roster for %s: send, reply and "
                             "status columns have no source and are reported as \"%s\" rather "
                             "than zero" % (client.get("slug"), NO_SOURCE))
    elif campaign_ids and daily is None and leads is None and instantly is None:
        # An offline run with campaigns to read is not a week of zeros either.
        unmeasured_reason = ("no sending-platform client was available for %s, so nothing could "
                             "be read and every column says \"%s\"" % (client.get("slug"), NO_SOURCE))

    truncated = False
    if unmeasured_reason:
        notes.add(unmeasured_reason)
        week = {k: None for k in ("sent", "replies", "real_replies", "replies_automatic",
                                  "positives", "booked", "held", "closed")}
        prior = dict(week)
        measured = False
    else:
        daily_failures = []  # type: List[str]
        measured = True
        if daily is None:
            daily, daily_failures = pull_daily(instantly, campaign_ids, prior_start, end, notes)
        if leads is None and instantly is None:
            # Injected daily rows but no lead source. The status columns are
            # unmeasured, not zero.
            lead_rows, truncated, measured = [], True, False
            notes.add("no sending-platform client for %s, so the interested, booked, held and "
                      "closed columns have no source" % client.get("slug"),
                      client="Contact records could not be read this week, so interested, "
                             "booked, held and closed are left blank rather than shown as zero.")
        elif leads is None:
            lead_rows, truncated = pull_leads(instantly, campaign_ids, notes)
        else:
            lead_rows, collapsed = dedupe_leads(list(leads))
            if collapsed:
                notes.add("%d duplicate lead records were collapsed by email" % collapsed,
                          client="%d contacts appear on more than one campaign and are counted "
                                 "once." % collapsed)
        week = sum_daily(daily, start, end)
        prior = sum_daily(daily, prior_start, prior_end)
        if campaign_ids and len(daily_failures) == len(campaign_ids):
            # Every analytics pull failed. Summing an empty list gives zeros,
            # and "Sent 0, Replies 0" on a client's card is a claim that their
            # week produced nothing. It is also the alert that makes Lorenzo
            # think a healthy campaign stopped.
            for key in ("sent", "replies", "real_replies", "replies_automatic"):
                week[key] = None
                prior[key] = None
            notes.add("every daily-analytics pull failed for %s, so sent and replies have no "
                      "source this week and are not reported as zero" % client.get("slug"),
                      client="The sending platform could not be read for this week, so the sent "
                             "and reply rows are left blank rather than shown as zero.")
        week.update(count_statuses(lead_rows, start, end))
        prior.update(count_statuses(lead_rows, prior_start, prior_end))
        if not measured:
            for key in ("positives", "booked", "held", "closed"):
                week[key] = None
                prior[key] = None
        week["counts_are_a_floor"] = bool(truncated)
        if week.get("unknown_status"):
            notes.add("%d contacts carry an interest-status code outside the documented set "
                      "(custom lead labels use -30000..30000); they are not counted up the funnel"
                      % week["unknown_status"],
                      client="Some contacts carry a label this report does not recognise. They "
                             "are left out rather than counted as interested.")
        if week.get("undated"):
            notes.add("%d interested contacts have no reply timestamp and could not be placed "
                      "in a week; they are in the all-time count only" % week["undated"],
                      client="%d interested contacts have no reply date on record and could not "
                             "be placed in a week." % week["undated"])
    week["through"] = _iso(end)
    week["days_measured"] = (end - start).days + 1

    attribution = None
    if client.get("deal_type") == "performance":
        close_dates = {}  # type: Dict[str, date]
        won_values, ghl_touches = pull_won_values(ghl, client, notes, close_dates=close_dates)
        touches = dict(first_touch_index(store, lead_rows, notes))
        touches.update(ghl_touches)
        rows = attribution_rows(lead_rows, client, now, won_values=won_values,
                                first_touches=touches, period=(start, end),
                                close_dates=close_dates)
        attribution = revenue_attributed(rows, client, measured=measured)
        # Operator only (no client text). The job keeps no billing record.
        notes.add(INVOICING_BY_HAND)
        if attribution.get("counted"):
            notes.add("%d close(s) on this week's invoice line, with where each date came "
                      "from: %s" % (len(attribution["counted"]),
                                    close_list(attribution["counted"])))
        if attribution.get("earlier_periods"):
            notes.add("%d close(s) from an earlier period are listed under the table, not part "
                      "of this week's figure. Check each against your own records: it may never "
                      "have been on any invoice line: %s" % (
                          len(attribution["earlier_periods"]),
                          close_list(attribution["earlier_periods"])))
        if attribution.get("later_periods"):
            notes.add("%d close(s) dated after this week's end are left off this card and are "
                      "not part of its figure. Check each against your own records: a later "
                      "card is not guaranteed to count it, because its date can move back into "
                      "this week: %s" % (
                          len(attribution["later_periods"]),
                          close_list(attribution["later_periods"])))
        if not client.get("attribution_window_days"):
            notes.add("%s is a performance deal with no attribution_window_days, so no window is "
                      "printed and nothing is invoiceable until one is agreed" % client.get("slug"))
        if not client.get("commission_rate"):
            notes.add("%s is a performance deal with no commission_rate, so the card cannot state "
                      "what Advero is owed" % client.get("slug"))
        if attribution["invoiceable"] is False and attribution["excluded"]:
            notes.add("nothing invoiceable this period: %d closed contacts were excluded, "
                      "reasons on the scorecard" % len(attribution["excluded"]))

    if use_retro_card:
        # The card's numbers win. A10 counts a "reply from a person" and a
        # positive its own way (positive-lead pull, its own bucketing); this
        # module counts them from the full lead pull. Both are defensible and
        # neither is worth arguing about, but they must not appear on the same
        # page as different numbers, and the plan under the table has to be
        # about the table. So when A10 renders, A10 counts.
        week, prior, adopted = _adopt_retro_numbers(client, week, prior, week_obj, scorecard_mod)
        if adopted:
            notes.add("funnel numbers come from the weekly retro's own counts, so the table "
                      "and the plan under it cannot disagree")

    plan, plan_source = next_week_plan(client, week, prior, notes)

    due = due_retention(client, now, templates, lookahead_days=lookahead_days,
                        store=store, notes=notes)
    term = term_metrics(client, now, end, instantly, daily if not unmeasured_reason else None,
                        lead_rows, notes, measured=not unmeasured_reason,
                        needed=any(t.metrics_scope == TERM_SCOPE for t, _d, _u in due))
    drafts = []  # type: List[Dict[str, Any]]
    for template, due_date, days_until in due:
        drafts.append(render_retention(template, client, due_date, days_until, week, now,
                                       term=term, render_mod=render_mod, replay=replay))

    card_source = "built-in"
    text = None
    if use_retro_card:
        card = render_with_retro(client, week, attribution, plan, drafts, notes,
                                 week_obj, scorecard_mod, render_mod)
        if card:
            # The A10 card has no attribution table, and it carries none of the
            # caveats: a truncated pull, a failed campaign read and the "no
            # source is not zero" line used to vanish whenever A10 rendered,
            # on a document used as an invoice basis. The retention schedule
            # and the run notes go to the operator appendix, not here.
            blocks = [card]
            for block in (_attribution_lines(attribution),
                          _footer_lines(notes, counted_by=COUNTED_BY_RETRO)):
                if block:
                    blocks.append("\n".join(block))
            text = "\n\n".join(blocks)
            card_source = "retro_scorecard (A10)"
    if text is None:
        text = render_scorecard(client, week, prior, start, end, attribution,
                                plan, plan_source, drafts, notes, replay=replay)

    problems = copy_problems(text, render_mod)
    if problems:
        # Never silently. The scorecard goes to a client.
        notes.add("COPY RULES: this card breaks %s. Fix it before it is sent."
                  % "; ".join(problems))
    appendix = render_operator_appendix(client, start, end, plan_source, card_source,
                                        drafts, notes, replay=replay)
    return {
        "slug": client.get("slug"),
        "company": client.get("company"),
        "week": {"start": _iso(start), "end": _iso(end)},
        "metrics": week,
        "prior": prior,
        "term": term,
        "attribution": attribution,
        "plan": plan,
        "plan_source": plan_source,
        "card_source": card_source,
        "copy_problems": problems,
        "drafts": drafts,
        "notes": list(notes),
        "client_notes": notes.client_facing(),
        "replay": replay,
        "scorecard": text,
        "operator_appendix": appendix,
    }


def term_metrics(
    client: Dict[str, Any],
    now: datetime,
    end: date,
    instantly: Optional[Instantly],
    daily: Optional[List[Dict[str, Any]]],
    lead_rows: List[Dict[str, Any]],
    notes: List[str],
    measured: bool = True,
    needed: bool = True,
) -> Optional[Dict[str, Any]]:
    """Start-date-to-now totals, for the drafts that describe the term.

    The day-21 and day-25 notes say "the first 25 days" and "three weeks", so
    they cannot be filled from the reporting week. This is a second, wider pull
    over [start_date, end]; it stops at ``end`` because nothing past it has
    happened yet, and the draft prints ``{metrics_through}`` so the client is
    never told a Monday's numbers were their first 25 days.
    """
    if not needed or not measured:
        return None
    start = parse_day(client.get("start_date"))
    campaign_ids = [c for c in (client.get("instantly_campaign_ids") or []) if c]
    if start is None or not campaign_ids or start > end:
        return None
    rows = daily
    earliest = None  # type: Optional[date]
    for row in rows or []:
        day = parse_day(row.get("date"))
        if day is not None and (earliest is None or day < earliest):
            earliest = day
    if rows is None or earliest is None or earliest > start:
        # The week's pull starts at last week's Monday, so it does not reach
        # back to the start of the term. One more read-only call per campaign.
        if instantly is None:
            return None
        rows, failures = pull_daily(instantly, campaign_ids, start, end, notes)
        if len(failures) == len(campaign_ids):
            notes.append("term-to-date pull failed for every campaign; the day-21 and day-25 "
                         "drafts have no term numbers and stay blocked")
            return None
    out = sum_daily(rows, start, end)
    out.update(count_statuses(lead_rows, start, end))
    out["through"] = _iso(end)
    out["days_measured"] = (end - start).days + 1
    out["start"] = _iso(start)
    return out


def write_outputs(result: Dict[str, Any], root: Optional[Path] = None) -> List[str]:
    """Client body, operator appendix and drafts to .tmp/scorecards/<slug>/.

    Local files only: nothing here sends a card to a client. A replay writes ``.replay.md`` files, never the real names: a
    fixtures run and a real run used to write the same path, so whichever ran
    last was what Lorenzo opened.
    """
    root = root or (tmp_dir() / "scorecards")
    directory = root / (result.get("slug") or "unknown")
    directory.mkdir(parents=True, exist_ok=True)
    suffix = ".replay.md" if result.get("replay") else ".md"
    written = []  # type: List[str]
    path = directory / ("scorecard_%s%s" % (result["week"]["end"], suffix))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(result["scorecard"])
    written.append(str(path))
    if result.get("operator_appendix"):
        path = directory / ("operator_%s%s" % (result["week"]["end"], suffix))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(result["operator_appendix"])
        written.append(str(path))
    for draft in result.get("drafts") or []:
        name = "draft_%s_%s%s" % (draft["due"], draft["template_id"], suffix)
        path = directory / name
        header = ["# %s (day %d, due %s)" % (draft["template_id"], draft["day"], draft["due"])]
        if draft.get("replay") or result.get("replay"):
            header += ["", "> %s. Do not send." % REPLAY_STAMP]
        header += ["",
                   "Status: **%s**" % ("READY to send after approval" if draft["ready"]
                                       else "NOT READY, do not send")]
        if draft["blockers"]:
            header.append("")
            header.append("Before this can go out:")
            header.append("")
            for blocker in draft["blockers"]:
                header.append("- %s" % blocker)
        header += ["", "---", "", "Subject: %s" % draft["subject"], "", draft["body"]]
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(header))
        written.append(str(path))
    return written


AUTO = "auto"   # sentinel: "build a client if you need one". None means offline.


def run_scorecards(
    now: datetime,
    clients: Optional[List[Dict[str, Any]]] = None,
    instantly: Any = AUTO,
    ghl: Any = AUTO,
    store: Optional[Store] = None,
    week_ending: Optional[date] = None,
    dry_run: bool = True,
    send_digest: Optional[bool] = None,
    write_files: bool = True,
    roster_path: Optional[Path] = None,
    templates_dir: Optional[Path] = None,
    fixtures: Optional[Dict[str, Any]] = None,
    lookahead_days: int = 7,
    out_dir: Optional[Path] = None,
    roster_notes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    # Prefixed so the digest can surface them: a roster problem (a performance
    # deal with no window, a term_end that does not match the start) used to
    # reach a stderr warning and nothing else.
    notes = ["roster: %s" % n for n in (roster_notes or [])]  # type: List[str]
    store = store if store is not None else get_store()
    if clients is None:
        clients, loaded_notes = load_roster(roster_path, store)
        notes.extend(loaded_notes)
    templates, template_notes = load_templates(templates_dir)
    notes.extend(template_notes)
    if not templates:
        # A renamed or moved directory otherwise produces zero drafts, zero
        # signal on the card and a silent exit 0 every week, while Mike's
        # day-25 renewal has a hard 2026-10-12 deadline.
        notes.append("NO RETENTION TEMPLATES were loaded from %s: no draft can be produced for "
                     "any client this run" % (templates_dir or RETENTION_DIR))

    # An explicit None means "offline, use no client". Auto-constructing one
    # from INSTANTLY_API_KEY here sent a caller that meant offline straight at
    # api.instantly.ai, for up to 20 lead pages per campaign plus the A10
    # pulls, against a workspace capped at 20 requests a minute.
    if instantly is AUTO:
        instantly = None
        if fixtures is None:
            try:
                instantly = default_client()
            except Exception as exc:  # noqa: BLE001 - no key is a note, not a crash
                notes.append("instantly client unavailable: %s" % exc)
    if ghl is AUTO:
        ghl = GHL()

    collect_mod, scorecard_mod, render_mod = retro_modules()
    week_obj = None
    if collect_mod is None:
        notes.append("services/retro (brief A10) not importable; every card uses the built-in "
                     "renderer and the copy rules are NOT checked")
    elif fixtures is not None:
        notes.append("fixtures replay: the A10 renderer is skipped so the card comes from the "
                     "same recorded numbers the rest of this run uses")
    elif instantly is None:
        notes.append("no Instantly client; the A10 week could not be collected")
    else:
        try:
            week_obj = collect_mod.collect_week(now, instantly=instantly, ghl=ghl)
        except Exception as exc:  # noqa: BLE001 - a shared module mid-build must not take this down
            notes.append("retro collect_week failed (%s); every card uses the built-in renderer" % exc)

    results = []  # type: List[Dict[str, Any]]
    failed = []  # type: List[str]
    for client in clients:
        per_client = {}  # type: Dict[str, Any]
        replay = False
        if fixtures is not None:
            if client.get("internal"):
                replay = True
                per_client["leads"] = fixtures.get("leads") or []
                per_client["daily"] = fixtures.get("daily") or []
                # Say it on every card. A replay that looks like a real week is
                # how recorded Advero numbers end up quoted to a client as
                # their own.
                per_client["extra_notes"] = [
                    "%s: these numbers are recorded Advero data. Nothing on this card may be "
                    "sent to anyone." % REPLAY_STAMP]
            else:
                # The fixtures are Advero's own recorded leads and daily rows.
                # Handing them to a real client rendered Mike, whose roster row
                # has no campaigns at all and must read "no source", as 1,800
                # sent and 22 replies, and wrote a day-21 draft addressed to
                # him quoting them.
                per_client["extra_notes"] = [
                    "fixtures replay: the recorded fixtures are Advero's own numbers, so they "
                    "are NOT injected for %s. This card reads from this client's real sources "
                    "only." % (client.get("company") or client.get("slug"))]
        try:
            results.append(run_client(client, now, instantly, templates, ghl=ghl,
                                      week_ending=week_ending, lookahead_days=lookahead_days,
                                      week_obj=week_obj, scorecard_mod=scorecard_mod,
                                      render_mod=render_mod, store=store, replay=replay,
                                      **per_client))
        except Exception as exc:  # noqa: BLE001 - one client's failure must not sink the others
            logger.exception("client_scorecard: the card for %s failed", client.get("slug"))
            failed.append(str(client.get("slug") or "unknown"))
            notes.append("card for %s failed and was not produced: %s: %s"
                         % (client.get("slug"), type(exc).__name__, str(exc)[:200]))

    written = []  # type: List[str]
    if write_files:
        for result in results:
            written.extend(write_outputs(result, root=out_dir))

    # Delivery is manual: Lorenzo reads the card and sends it himself. This job
    # has no send path in any mode, so it does not call settings.guard_write.
    # guard_write in live mode opens a ``live_write_intent`` Job_Log row that a
    # send is expected to close with live_write_ok / live_write_failed, and with
    # no send it hung open on every run. What is recorded instead is the card
    # that is ready for Lorenzo to deliver, in the Job_Log row below.
    deliveries = []  # type: List[Dict[str, Any]]
    for result in results:
        client = next((c for c in clients if c.get("slug") == result["slug"]), {})
        if client.get("internal") or not client.get("contact_email"):
            continue
        if fixtures is not None:
            # A replay run never queues a delivery, for any client. Half the
            # cards in it are recorded Advero numbers and the other half are
            # rendered beside them.
            notes.append("%s: this is a replay run, so no delivery is queued" % result["slug"])
            continue
        deliveries.append({
            "system": "gmail", "action": "client_scorecard_send", "sent": False,
            "delivery": "manual, by Lorenzo, after reading the card",
            "payload": {
                "to": client.get("contact_email"),
                "subject": "Week ending %s, %s" % (result["week"]["end"], client.get("company")),
                "body_markdown_chars": len(result["scorecard"]),
                "slug": result["slug"],
            },
        })

    ready = sum(1 for r in results for d in r["drafts"] if d["ready"])
    blocked = sum(1 for r in results for d in r["drafts"] if not d["ready"])
    overdue = sum(1 for r in results for d in r["drafts"] if d["overdue"])
    all_notes = list(notes)
    for result in results:
        all_notes.extend("%s: %s" % (result["slug"], n) for n in result["notes"])
    digest = render_digest(results, now, notes=notes, failed=failed)

    status = "dry_run" if dry_run else "ok"
    if any("failed" in n or "unreadable" in n for n in all_notes):
        status = "dry_run_partial" if dry_run else "partial"
    if failed and not results:
        # Every card failed: not a partial run, a failed one.
        status = "dry_run_failed" if dry_run else "failed"
    log_run(JOB_NAME, status, {
        "as_of": now.isoformat(),
        "clients": [r["slug"] for r in results],
        "card_sources": sorted(set(r.get("card_source") or "" for r in results)),
        "copy_problems": sum(len(r.get("copy_problems") or []) for r in results),
        "drafts_ready": ready, "drafts_blocked": blocked, "drafts_overdue": overdue,
        "deliveries_ready_for_manual_send": len(deliveries),
        "cards_failed": failed,
        "replay": fixtures is not None,
        "notes": all_notes,
    })

    if send_digest is None:
        send_digest = not dry_run
    sent = None
    if send_digest:
        # A card that failed is the one thing on this push that must not be
        # missed: the per-client guard keeps the other cards going, and without
        # this the push read like a clean week with one client silently absent.
        priority = "high" if (overdue or failed) else "default"
        title = "Client scorecards: %d client(s), %d draft(s) due" % (len(results), ready + blocked)
        if failed:
            # A count names no client, so it is safe on a public topic.
            title += ", %s" % _failed_label(len(failed))
        if fixtures is not None:
            title = "REPLAY " + title
        sent = notify(title, push_body(results, digest, replay=fixtures is not None,
                                       failed=len(failed)),
                      priority=priority, tags=["chart_with_upwards_trend"], email_message=digest)
    return {
        "job": JOB_NAME, "as_of": now.isoformat(), "mode": settings.get_mode(),
        "dry_run": dry_run, "status": status, "results": results, "notes": all_notes,
        "written": written, "deliveries": deliveries, "digest": digest, "notified": sent,
        "counts": {"clients": len(results), "drafts_ready": ready,
                   "drafts_blocked": blocked, "drafts_overdue": overdue,
                   "cards_failed": len(failed)},
        "cards_failed": failed,
    }


def _failed_label(count: int) -> str:
    return "%d card%s failed" % (count, "" if count == 1 else "s")


def push_body(results: List[Dict[str, Any]], digest: str, replay: bool = False,
              failed: int = 0) -> str:
    """The ntfy card. The full digest only on a protected topic.

    The digest names client companies, amounts and draft blockers, and the
    default ntfy topic is readable by anyone who knows it. On an unprotected
    topic the card carries counts only and the digest goes by email
    (``email_message``). A failed card is a count here too: it names nobody."""
    if topic_is_protected():
        if failed:
            return "%s.\n%s" % (_failed_label(failed), digest)
        return digest
    drafts = [d for r in results for d in r.get("drafts") or []]
    bits = []  # type: List[str]
    if failed:
        bits.append(_failed_label(failed))
    bits.extend(["%d client card(s)" % len(results),
                 "%d draft(s) ready" % sum(1 for d in drafts if d.get("ready")),
                 "%d blocked" % sum(1 for d in drafts if not d.get("ready")),
                 "%d overdue" % sum(1 for d in drafts if d.get("overdue"))])
    return ("%s%s.\nClient names, amounts and blockers went by email: this ntfy topic is "
            "public. Set NTFY_TOKEN to see them on the card." % (
                "REPLAY " if replay else "", ", ".join(bits)))


DIGEST_NOTE_MARKERS = ("NO RETENTION TEMPLATES", "unreadable", "failed", "roster", "REPLAY")


def render_digest(results: List[Dict[str, Any]], now: datetime,
                  notes: Optional[List[str]] = None,
                  failed: Optional[List[str]] = None) -> str:
    """The push Lorenzo actually reads.

    Every client line is prefixed REPLAY when it came from the fixtures: the
    card carried the stamp in its body, but the digest line read like a real
    week. Run-level failures (an unreadable template directory, a roster
    validation problem) are printed too, because they used to reach the
    Job_Log only, and a run that produced no drafts at all looked identical to
    a quiet week.
    """
    lines = ["Client scorecards, %s" % now.astimezone(settings.TZ).strftime("%a %d %b %H:%M CT"), ""]
    for note in notes or []:
        if any(marker.lower() in note.lower() for marker in DIGEST_NOTE_MARKERS):
            lines.append("! %s" % note)
    if notes and lines[-1].startswith("!"):
        lines.append("")
    if not results:
        if failed:
            # "No active clients" under a "card for X failed" line was false.
            lines.append("No card was produced this run: %s, see above."
                         % ("the only card failed" if len(failed) == 1
                            else "all %d cards failed" % len(failed)))
        else:
            lines.append("No active clients in the roster.")
        return "\n".join(lines)
    for result in results:
        week = result["metrics"]
        prefix = "REPLAY " if result.get("replay") else ""
        lines.append("%s%s (week ending %s)" % (prefix, result["company"] or result["slug"],
                                                result["week"]["end"]))
        lines.append("  %ssent %s, replies %s, interested %s, booked %s, held %s, closed %s"
                     % (prefix, _cell(week.get("sent")), _cell(week.get("real_replies")),
                        _cell(week.get("positives")), _cell(week.get("booked")),
                        _cell(week.get("held")), _cell(week.get("closed"))))
        attribution = result.get("attribution")
        if attribution:
            if attribution.get("invoiceable"):
                invoice = _money(attribution.get("contract_value_usd"))
            elif attribution.get("invoiceable") is None:
                invoice = "no source, nothing measured"
            else:
                invoice = "nothing"
            lines.append("  invoiceable: %s" % invoice)
        for note in result.get("client_notes") or []:
            lines.append("  note: %s" % note)
        for draft in result["drafts"]:
            when = "OVERDUE %d days" % (-draft["days_until"]) if draft["overdue"] else (
                "in %d days" % draft["days_until"])
            lines.append("  %sday %d draft %s: %s%s" % (
                prefix, draft["day"], when, "ready" if draft["ready"] else "BLOCKED",
                "" if draft["ready"] else " (%s)" % "; ".join(draft["blockers"][:2])))
    return "\n".join(lines)


# ------------------------------------------------------------------ fixtures
def load_fixtures() -> Dict[str, Any]:
    """Offline replay from files already in the repo: the recorded replied
    leads and the 2026-09-21 campaign analytics snapshot, spread flat across
    the snapshot's own send window so the daily summer has something real to
    add up. Labelled as fixtures everywhere it is used."""
    with open(LEADS_FIXTURE, "r", encoding="utf-8") as fh:
        leads = json.load(fh)
    with open(ANALYTICS_SNAPSHOT, "r", encoding="utf-8") as fh:
        snapshot = json.load(fh)
    daily = []  # type: List[Dict[str, Any]]
    first_day = date(2026, 9, 15)
    for row in snapshot:
        sent = int(row.get("emails_sent_count") or 0)
        replies = int(row.get("reply_count") or 0)
        auto = int(row.get("reply_count_automatic") or 0)
        for offset in range(6):
            daily.append({
                "date": _iso(first_day + timedelta(days=offset)),
                "campaign_id": row.get("campaign_id"),
                "sent": sent // 6,
                "contacted": int(row.get("contacted_count") or 0) // 6,
                "replies": replies // 6 + (1 if offset < replies % 6 else 0),
                "replies_automatic": auto // 6 + (1 if offset < auto % 6 else 0),
                "opportunities": 0,
            })
    return {"leads": leads, "daily": daily}


def _parse_as_of(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = parse_ts(value)
    if parsed is None:
        raise SystemExit("--as-of must be an ISO timestamp, got %r" % value)
    return parsed


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Weekly client scorecard and the F4 retention drafts (F3/F4)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true",
                       help="pull (read-only), render, write to .tmp, Job_Log row; no digest")
    group.add_argument("--now", action="store_true", help="same plus the ntfy digest")
    parser.add_argument("--as-of", help="ISO timestamp used as 'now' (replay / tests)")
    parser.add_argument("--week-ending", help="YYYY-MM-DD, pins the reporting week")
    parser.add_argument("--client", help="one slug only")
    parser.add_argument("--self", dest="self_only", action="store_true",
                        help="render Advero's own six campaigns as a pseudo-client (not a client)")
    parser.add_argument("--retention", action="store_true",
                        help="print the due retention drafts in full")
    parser.add_argument("--lookahead", type=int, default=7,
                        help="render retention drafts due within this many days (default 7). "
                             "Overdue touches are always included")
    parser.add_argument("--out-dir", help="write the scorecard and drafts here instead of .tmp/scorecards")
    parser.add_argument("--fixtures", action="store_true",
                        help="offline replay from the recorded fixtures. The fixtures are "
                             "Advero's own recorded numbers, so they are injected for --self "
                             "only; every other client reads from their own sources")
    parser.add_argument("--offline", action="store_true",
                        help="make no network call at all: every funnel cell reads \"%s\" "
                             "unless --fixtures supplies the numbers. This is how the "
                             "committed drafts are regenerated deterministically" % NO_SOURCE)
    parser.add_argument("--mark-handled", metavar="SLUG:TEMPLATE_ID",
                        help="retire a retention touch so it stops appearing as due "
                             "(writes to the local store only)")
    parser.add_argument("--include-inactive", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.dry_run:
        from shared.job_log import use_scratch_logs
        use_scratch_logs("client_scorecard_dryrun")

    now = _parse_as_of(args.as_of)
    week_ending = parse_day(args.week_ending) if args.week_ending else None
    if args.week_ending and week_ending is None:
        raise SystemExit("--week-ending must be YYYY-MM-DD, got %r" % args.week_ending)

    store = get_store()
    if args.mark_handled:
        slug, _, template_id = args.mark_handled.partition(":")
        if not slug or not template_id:
            raise SystemExit("--mark-handled takes SLUG:TEMPLATE_ID, got %r" % args.mark_handled)
        record = mark_retention_handled(store, slug, template_id, now)
        log_run(JOB_NAME, "retention_marked_handled", record)
        print("marked handled: %s" % retention_key(slug, template_id))
        return 0

    roster_notes = []  # type: List[str]
    if args.self_only:
        clients = [self_client()]
    else:
        clients, roster_notes = load_roster(store=store, include_inactive=args.include_inactive)
        for note in roster_notes:
            logger.warning("%s", note)
        if args.client:
            clients = [c for c in clients if c.get("slug") == args.client]
            if not clients:
                raise SystemExit("no client with slug %r in the roster" % args.client)

    try:
        result = run_scorecards(
            now, clients=clients, store=store, week_ending=week_ending,
            dry_run=bool(args.dry_run),
            instantly=None if args.offline else AUTO,
            ghl=None if args.offline else AUTO,
            fixtures=load_fixtures() if args.fixtures else None,
            lookahead_days=args.lookahead,
            out_dir=Path(args.out_dir) if args.out_dir else None,
            # main() builds the roster itself, so without this the validation
            # problems (a performance deal with no window, a term_end that does
            # not match) reached a stderr warning and nothing else: not the
            # Job_Log, not the card, not the digest.
            roster_notes=roster_notes,
        )
    except Exception as exc:  # noqa: BLE001 - a job failure alerts, it does not vanish
        log_run(JOB_NAME, "error", {"error": str(exc)})
        # The exception text can carry a client's name or a roster value.
        notify("Client scorecard failed",
               str(exc) if topic_is_protected() else
               "%s. The error text went by email: this ntfy topic is public." % type(exc).__name__,
               priority="high", email_message=str(exc))
        logger.exception("client_scorecard failed")
        return 1

    exit_code = 0
    if result.get("cards_failed") and not result.get("results"):
        # Every card failed: the scheduler has to see a failure, not exit 0.
        exit_code = 1
    if args.json:
        print(json.dumps(result, indent=1, default=str))
    else:
        print(result["digest"])
        print("")
        for item in result["results"]:
            print(item["scorecard"])
            print("")
            if args.retention:
                for draft in item["drafts"]:
                    print("-" * 60)
                    print("DRAFT %s, day %d, due %s: %s" % (
                        draft["template_id"], draft["day"], draft["due"],
                        "READY" if draft["ready"] else "NOT READY"))
                    for blocker in draft["blockers"]:
                        print("  blocker: %s" % blocker)
                    print("")
                    print("Subject: %s" % draft["subject"])
                    print("")
                    print(draft["body"])
        for path in result["written"]:
            print("wrote %s" % path)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
