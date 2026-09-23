"""Read-only campaign analytics for the verdict engine (Blueprint M4).

Every call in this module is a read. `GET /campaigns/analytics`,
`GET /campaigns/analytics/steps`, `GET /campaigns/analytics/daily`,
`GET /campaigns/{id}` and the POST-shaped read `POST /leads/list`. Nothing
here is guarded because nothing here writes.

Four things measured on live data on 2026-09-22 that the code depends on
------------------------------------------------------------------------

1. **`reply_count_unique` already EXCLUDES automatic replies.** The obvious
   reading of Blueprint M1 level 3 ("real replies, exclude auto-replies and
   OOO") is `reply_count_unique - reply_count_automatic_unique`. That is
   wrong and it goes negative: on 2026-09-22 bookkeeping_reactivation reported
   `reply_count_unique=1, reply_count_automatic_unique=4` and
   bookkeeping_trigger `1` and `6`. Checked against the lead list, the two
   fields are disjoint buckets that sum to the replied-lead count for all six
   campaigns (4+3=7, 5+3=8, 1+4=5, 1+6=7, 3+3=6, 3+3=6). So real replies are
   `reply_count_unique` as-is, and `real_replies()` refuses to subtract.

2. **`POST /leads/list` silently ignores a filter value it does not know.**
   `FILTER_VAL_LEAD_INTERESTED` (a plausible-looking name that does not exist)
   returns the same rows as no filter at all, which would have counted every
   contacted lead as a positive. `LEAD_FILTERS` is the allow-list of values
   verified against this workspace; `replied_leads()` refuses anything else
   rather than over-counting. The walk is also de-duplicated on lead id (or
   lowercased email), because an overlapping cursor page returns the same lead
   twice and every counter here counts rows.

3. **Numbers come back as strings often enough to assume they always can.**
   Step and variant indices are **strings, zero-based** (`{"step": "0",
   "variant": "0"}`); the totals row is `step: null` on four campaigns and the
   *string* `"null"` on recruiting_reactivation. Every numeric field this
   module reads goes through a coercion helper rather than an `in (1, 2, 3, 4)`
   membership test, because a string-typed `lt_interest_status` would silently
   zero every positive and hand recruiting a retirement recommendation.

4. **A positive is "ever reached a positive status", not "is positive now".**
   `lt_interest_status` is current state, so a lead that replied, booked and
   then went no-show (-4) or was marked lost (-3) reads as a negative later.
   On 2026-09-22 rob@cjsglobal.com is -3 on cleaning_reactivation and the
   blueprint's own audit counts him as one of that campaign's two positives
   (he held his discovery call on Sept 18). Counting current state only would
   make a campaign's positive count fall as its calls close, and the verdict
   rules turn on exactly that number. `POST_REPLY_STATUSES` (-3, -4) therefore
   count as positives-at-reply and are reported separately so the table never
   says "no positives" about a campaign that booked two calls.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from shared import settings

logger = logging.getLogger("services.experiments.analytics")

# lt_interest_status values (config/ids.json instantly.interest_status_codes).
# OPEN_POSITIVE_STATUSES are positive right now; POST_REPLY_STATUSES replied
# positively and then closed out (lost, no show) - they are still positives for
# the copy verdict, which asks "did this copy produce a positive reply".
OPEN_POSITIVE_STATUSES = (1, 2, 3, 4)
POST_REPLY_STATUSES = (-3, -4)
POSITIVE_STATUSES = OPEN_POSITIVE_STATUSES + POST_REPLY_STATUSES
NEGATIVE_STATUSES = (-1, -2)

# Instantly campaign status codes: 1 active, 2 paused, 3 completed, -99 draft.
ACTIVE_CAMPAIGN_STATUS = 1

# POST /leads/list filter values verified against this workspace on 2026-09-22.
# An unknown value is IGNORED by the API, so anything outside this set is a
# silent "return everything" and must never be sent.
LEAD_FILTERS = frozenset([
    "FILTER_VAL_REPLIED",
    "FILTER_VAL_CONTACTED",
    "FILTER_VAL_NOT_CONTACTED",
    "FILTER_VAL_COMPLETED",
    "FILTER_VAL_BOUNCED",
    "FILTER_VAL_UNSUBSCRIBED",
    "FILTER_LEAD_INTERESTED",
    "FILTER_LEAD_NOT_INTERESTED",
    "FILTER_LEAD_MEETING_BOOKED",
    "FILTER_LEAD_MEETING_COMPLETED",
    "FILTER_LEAD_CLOSED",
    "FILTER_LEAD_OUT_OF_OFFICE",
    "FILTER_LEAD_WRONG_PERSON",
])

REPLIED_FILTER = "FILTER_VAL_REPLIED"

STEPS_PATH = "campaigns/analytics/steps"

# Mon-Sat is what all six campaigns send today (schedule days "1".."6" true,
# "0" false). Used only when a campaign object cannot be read.
DEFAULT_SENDING_DAYS = {"0": False, "1": True, "2": True, "3": True, "4": True, "5": True, "6": True}


class AnalyticsError(Exception):
    pass


def as_int(value: Any) -> Optional[int]:
    """``int(value)`` or None. Never raises, never guesses.

    The steps endpoint already returns ``step`` and ``variant`` as strings and
    one fixture carries the string ``"null"``, so every numeric field read off
    this API goes through here rather than through an untyped membership test.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def has_unique_reply_count(overview_row: Dict[str, Any]) -> bool:
    return as_int(overview_row.get("reply_count_unique")) is not None


def real_replies(overview_row: Dict[str, Any]) -> int:
    """Unique human replies for a campaign.

    This is `reply_count_unique` unchanged. Do not subtract
    `reply_count_automatic_unique` from it: the two are disjoint buckets and
    the subtraction is negative on four of the six live campaigns (see the
    module docstring).

    When the unique field is missing the fallback is `reply_count` **minus**
    the automatic count, never `reply_count` itself: `reply_count` is the
    human+automatic total (cleaning_reactivation reports 7 = 4 + 3), so
    returning it would print a 2.33% real reply rate where the truth is 1.33%
    and would invert the Section 6 flag. `has_unique_reply_count()` says
    whether the honest number was available, and ``collect()`` notes it on the
    campaign when it was not.
    """
    unique = as_int(overview_row.get("reply_count_unique"))
    if unique is not None:
        return max(0, unique)
    total = as_int(overview_row.get("reply_count"))
    if total is None:
        return 0
    return max(0, total - auto_replies(overview_row))


def auto_replies(overview_row: Dict[str, Any]) -> int:
    for field in ("reply_count_automatic_unique", "reply_count_automatic"):
        value = as_int(overview_row.get(field))
        if value is not None:
            return max(0, value)
    return 0


def _rate(numerator: int, denominator: int) -> float:
    if not denominator:
        return 0.0
    return float(numerator) / float(denominator)


class VariantStats(object):
    """One (step, variant) cell of `GET /campaigns/analytics/steps`.

    `step` and `variant` are stored zero-based as the API returns them;
    `step_number` / `variant_letter` are the human forms (step 1, variant A).
    """

    def __init__(self, step: int, variant: int, sent: int, replies: int, replies_auto: int):
        self.step = step
        self.variant = variant
        self.sent = sent
        self.replies = replies           # unique human replies
        self.replies_auto = replies_auto
        self.positives = 0               # filled from the replied-lead list

    @property
    def step_number(self) -> int:
        return self.step + 1

    @property
    def variant_letter(self) -> str:
        return "AB"[self.variant] if self.variant < 2 else str(self.variant)

    @property
    def label(self) -> str:
        return "step%d/%s" % (self.step_number, self.variant_letter)

    @property
    def reply_rate(self) -> float:
        return _rate(self.replies, self.sent)

    @property
    def positive_rate(self) -> float:
        return _rate(self.positives, self.sent)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step_number,
            "variant": self.variant_letter,
            "sent": self.sent,
            "real_replies": self.replies,
            "auto_replies": self.replies_auto,
            "positives": self.positives,
            "reply_rate": round(self.reply_rate, 5),
            "positive_rate": round(self.positive_rate, 5),
        }


class CampaignStats(object):
    """Everything the verdict rules need about one campaign."""

    def __init__(self, key: str, campaign_id: str, niche: str = "", offer: str = ""):
        self.key = key
        self.campaign_id = campaign_id
        self.niche = niche
        self.offer = offer
        self.name = ""
        self.sent = 0
        self.contacted = 0
        self.leads = 0
        self.bounced = 0
        self.unsubscribed = 0
        self.real_replies = 0
        self.auto_replies = 0
        self.opportunities = 0
        self.opportunity_value = 0
        self.positives = 0               # ever reached a positive status
        self.open_positives = 0          # positive right now (1..4)
        self.closed_out = 0              # replied positive, then lost/no-show
        self.negatives = 0               # not interested / wrong person
        self.status_counts = {}          # type: Dict[str, int]
        self.variants = []               # type: List[VariantStats]
        self.daily_limit = 0
        self.sending_days = dict(DEFAULT_SENDING_DAYS)
        self.observed_sends_per_day = 0  # median of the non-zero days pulled
        self.inboxes = 0
        self.inbox_emails = []           # type: List[str]
        self.status = None               # type: Optional[int]  campaign status code
        self.daily_rows_seen = None      # type: Optional[int]  None = not pulled
        self.duplicate_leads = 0         # replied leads the cursor returned twice
        self.partial = False             # a cursor walk was capped
        self.notes = []                  # type: List[str]

    # ---------------------------------------------------------------- rates
    @property
    def reply_rate(self) -> float:
        return _rate(self.real_replies, self.sent)

    @property
    def positive_rate(self) -> float:
        return _rate(self.positives, self.sent)

    @property
    def bounce_rate(self) -> float:
        return _rate(self.bounced, self.sent)

    @property
    def is_active(self) -> bool:
        """False only when the campaign object says so. An unreadable campaign
        object leaves ``status`` None, and a missing status must not silently
        blank every projection."""
        if self.status is None:
            return True
        return self.status == ACTIVE_CAMPAIGN_STATUS

    @property
    def sends_nothing(self) -> bool:
        """The campaign has sent before but sent nothing in the pulled window.

        Instantly does not zero ``daily_limit`` on a paused campaign, so the
        old fallback handed a stopped campaign a confident decision date.
        """
        if self.daily_rows_seen is None:          # the daily window was not pulled
            return False
        return self.observed_sends_per_day == 0 and self.sent > 0

    @property
    def sends_per_day(self) -> int:
        """The rate the projection uses: what the campaign actually sent on its
        sending days, falling back to its configured daily limit.

        Returns 0 - which projects to "not at this rate" rather than to a date
        - when the campaign is not active, or when it has sent before and sent
        nothing across the whole pulled window.
        """
        if not self.is_active or self.sends_nothing:
            return 0
        if self.observed_sends_per_day > 0:
            return self.observed_sends_per_day
        return self.daily_limit

    def variants_for_step(self, step_number: int) -> List[VariantStats]:
        return sorted(
            [v for v in self.variants if v.step_number == step_number],
            key=lambda v: v.variant,
        )

    @property
    def step_numbers(self) -> List[int]:
        return sorted(set([v.step_number for v in self.variants]))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "campaign_id": self.campaign_id,
            "name": self.name,
            "niche": self.niche,
            "offer": self.offer,
            "sent": self.sent,
            "contacted": self.contacted,
            "leads": self.leads,
            "bounced": self.bounced,
            "bounce_rate": round(self.bounce_rate, 5),
            "real_replies": self.real_replies,
            "auto_replies": self.auto_replies,
            "reply_rate": round(self.reply_rate, 5),
            "positives": self.positives,
            "open_positives": self.open_positives,
            "closed_out": self.closed_out,
            "negatives": self.negatives,
            "positive_rate": round(self.positive_rate, 5),
            "opportunities": self.opportunities,
            "opportunity_value": self.opportunity_value,
            "status_counts": self.status_counts,
            "daily_limit": self.daily_limit,
            "observed_sends_per_day": self.observed_sends_per_day,
            "sends_per_day": self.sends_per_day,
            "campaign_status": self.status,
            "is_active": self.is_active,
            "inboxes": self.inboxes,
            "inbox_emails": list(self.inbox_emails),
            "duplicate_leads": self.duplicate_leads,
            "variants": [v.to_dict() for v in self.variants],
            "partial": self.partial,
            "notes": list(self.notes),
        }


# --------------------------------------------------------------------- pulls
def overview_by_id(client) -> Dict[str, Dict[str, Any]]:
    """`GET /campaigns/analytics` keyed by campaign id."""
    rows = client.campaign_analytics()
    if isinstance(rows, dict):
        rows = rows.get("items") or []
    out = {}
    for row in rows or []:
        cid = row.get("campaign_id")
        if cid:
            out[cid] = row
    return out


def step_rows(client, campaign_id: str) -> List[Dict[str, Any]]:
    """`GET /campaigns/analytics/steps` with the totals row dropped.

    The API answers a list whose first element carries `step: null,
    variant: null` and all-zero counters. Summing it double-counts nothing
    today (it is zeroed) but it is not a step, so it is removed here rather
    than filtered at every call site.

    The recorded fixtures are mixed: four campaigns answer a real JSON null and
    recruiting_reactivation answers the **string** ``"null"``. An ``is not
    None`` filter lets the string through, and the row then survives until
    ``parse_variants`` chokes on ``int("null")`` and logs it as "unreadable" -
    right answer today only because the row is all zeros. The filter is on the
    rendered value so both shapes are dropped here, quietly, as totals.

    ``shared.instantly.Instantly`` has no public method for this endpoint yet
    (there is a cross-cutting request open to add ``campaign_step_analytics``).
    Until it does, this reaches for the public name first and falls back to the
    private ``_get``, so the day it lands nothing here needs changing.
    """
    public = getattr(client, "campaign_step_analytics", None)
    if callable(public):
        rows = public(campaign_id)
    else:
        rows = client._get(STEPS_PATH, {"campaign_id": campaign_id})
    if isinstance(rows, dict):
        rows = rows.get("items") or []
    return [r for r in (rows or []) if not is_totals_row(r)]


def is_totals_row(row: Dict[str, Any]) -> bool:
    """A steps row with no step: JSON null or the string "null"/"none"/""."""
    return str(row.get("step")).strip().lower() in ("none", "null", "")


def parse_variants(rows: List[Dict[str, Any]]) -> List[VariantStats]:
    out = []
    for row in rows:
        if is_totals_row(row):
            continue
        step = as_int(row.get("step"))
        variant = as_int(row.get("variant"))
        if step is None:
            logger.warning("steps analytics row with an unreadable step/variant: %r", row)
            continue
        out.append(
            VariantStats(
                step=step,
                variant=variant or 0,
                sent=as_int(row.get("sent")) or 0,
                replies=as_int(row.get("unique_replies")) or 0,
                replies_auto=as_int(row.get("unique_replies_automatic")) or 0,
            )
        )
    return sorted(out, key=lambda v: (v.step, v.variant))


def replied_leads(
    client, campaign_id: str, max_pages: int = 20, lead_filter: str = REPLIED_FILTER
) -> Tuple[List[Dict[str, Any]], bool]:
    """Every lead that has replied, with a flag saying whether the walk was
    complete. Returns ([lead, ...], partial).

    The filter name is checked against ``LEAD_FILTERS`` first. `POST
    /leads/list` ignores a value it does not recognise and answers with the
    unfiltered list, so a typo here would count every contacted lead as a
    replied one and every campaign would look like it had 200 positives.
    """
    if lead_filter not in LEAD_FILTERS:
        raise AnalyticsError(
            "%r is not a filter this workspace recognises. POST /leads/list ignores an unknown "
            "filter and returns everything, so the count would be silently wrong. Known values: %s"
            % (lead_filter, ", ".join(sorted(LEAD_FILTERS)))
        )
    walk = client.iterate(
        "leads/list",
        body={"filter": lead_filter, "campaign": campaign_id, "limit": 100},
        max_pages=max_pages,
    )
    rows = dedupe_leads([lead for lead in walk])
    partial = bool(getattr(walk, "truncated", False))
    if partial:
        logger.warning("replied-lead walk for %s stopped at max_pages=%s; counts are a floor",
                       campaign_id, max_pages)
    if rows.dropped_duplicates:
        logger.warning("replied-lead walk for %s returned %d duplicate lead(s); counted once",
                       campaign_id, rows.dropped_duplicates)
    return rows, partial


class LeadRows(list):
    """The replied-lead list, with the duplicate count the walk dropped."""

    def __init__(self, rows, dropped_duplicates=0):
        list.__init__(self, rows)
        self.dropped_duplicates = dropped_duplicates


def dedupe_leads(rows: List[Dict[str, Any]]) -> LeadRows:
    """One row per lead, keyed on ``id`` and falling back to the lowercased
    email.

    An overlapping ``starting_after`` page hands the same lead back twice, and
    every counter here counts rows. One duplicated positive on a 300-send
    campaign moves the positive rate from 0.33% to 0.67%, which at the
    3,000-send decision is the difference between ``hold`` and ``scale``.
    """
    seen = set()
    out = []
    dropped = 0
    for lead in rows:
        key = lead.get("id") or (lead.get("email") or "").strip().lower()
        if not key:
            out.append(lead)          # nothing to key on; keep it rather than drop it
            continue
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        out.append(lead)
    return LeadRows(out, dropped)


def count_statuses(leads: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {}  # type: Dict[str, int]
    for lead in leads:
        status = as_int(lead.get("lt_interest_status"))
        key = "unreadable" if status is None and lead.get("lt_interest_status") is not None else str(status)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _with_status(leads: List[Dict[str, Any]], statuses) -> List[Dict[str, Any]]:
    return [l for l in leads if as_int(l.get("lt_interest_status")) in statuses]


def positives_from_leads(leads: List[Dict[str, Any]]) -> int:
    """Leads that ever reached a positive status, including the ones that later
    closed out as lost (-3) or no-show (-4). See the module docstring."""
    return len(_with_status(leads, POSITIVE_STATUSES))


def open_positives_from_leads(leads: List[Dict[str, Any]]) -> int:
    return len(_with_status(leads, OPEN_POSITIVE_STATUSES))


def closed_out_from_leads(leads: List[Dict[str, Any]]) -> int:
    return len(_with_status(leads, POST_REPLY_STATUSES))


def negatives_from_leads(leads: List[Dict[str, Any]]) -> int:
    return len(_with_status(leads, NEGATIVE_STATUSES))


def attach_positives(variants: List[VariantStats], leads: List[Dict[str, Any]]) -> None:
    """Spread the positive leads over the (step, variant) cells they replied to.

    Leads carry `email_replied_step` and `email_replied_variant` (both
    zero-based), which is the only way to answer "which variant produced the
    positive" - the steps endpoint counts replies, not interest status.
    A positive whose reply step is unreadable is left off the variants rather
    than assigned to step 1, because a mis-assigned positive is what decides
    an A/B test wrongly.
    """
    index = {}
    for v in variants:
        index[(v.step, v.variant)] = v
        v.positives = 0
    for lead in _with_status(leads, POSITIVE_STATUSES):
        step = as_int(lead.get("email_replied_step"))
        variant = as_int(lead.get("email_replied_variant"))
        if step is None or variant is None:
            logger.warning("positive lead %s has no readable reply step/variant; not attributed",
                           lead.get("email"))
            continue
        cell = (step, variant)
        target = index.get(cell)
        if target is None:
            logger.warning("positive lead %s replied to step/variant %r, which the steps analytics "
                           "does not report; not attributed", lead.get("email"), cell)
            continue
        target.positives += 1


def observed_rate(daily_rows: List[Dict[str, Any]]) -> int:
    """Median sends on the days the campaign actually sent.

    The mean is wrong here: a campaign that launched mid-window, or a Sunday
    with the schedule off, drags it down and pushes every projection out. Days
    with zero sends are not sending days and are excluded.
    """
    sends = sorted([int(r.get("sent") or 0) for r in (daily_rows or []) if int(r.get("sent") or 0) > 0])
    if not sends:
        return 0
    mid = len(sends) // 2
    if len(sends) % 2:
        return sends[mid]
    return int(round((sends[mid - 1] + sends[mid]) / 2.0))


def campaign_meta(client, campaign_id: str) -> Dict[str, Any]:
    """daily_limit, the sending-day map and the inbox count from the campaign."""
    campaign = client.get_campaign(campaign_id)
    schedule = (campaign.get("campaign_schedule") or {}).get("schedules") or [{}]
    days = (schedule[0] or {}).get("days") or dict(DEFAULT_SENDING_DAYS)
    email_list = [str(e) for e in (campaign.get("email_list") or [])]
    return {
        "name": campaign.get("name") or "",
        "daily_limit": as_int(campaign.get("daily_limit")) or 0,
        "sending_days": days,
        "inboxes": len(email_list),
        "email_list": email_list,
        "status": as_int(campaign.get("status")),
    }


def collect(
    client,
    campaign_keys: Optional[List[str]] = None,
    daily_start: Optional[str] = None,
    daily_end: Optional[str] = None,
    campaigns: Optional[Dict[str, Any]] = None,
) -> Dict[str, CampaignStats]:
    """Pull everything the verdict rules need, read-only, for every campaign in
    config/ids.json (or the subset named in ``campaign_keys``)."""
    campaigns = campaigns if campaigns is not None else settings.CAMPAIGNS
    keys = campaign_keys or list(campaigns.keys())
    overview = overview_by_id(client)
    out = {}  # type: Dict[str, CampaignStats]
    for key in keys:
        meta = campaigns.get(key)
        if not meta:
            raise AnalyticsError("campaign key %r is not in config/ids.json" % key)
        cid = meta["id"]
        stats = CampaignStats(key, cid, niche=meta.get("niche", ""), offer=meta.get("offer", ""))
        row = overview.get(cid)
        if row is None:
            stats.notes.append("no analytics row returned for this campaign")
        else:
            stats.name = row.get("campaign_name") or ""
            stats.sent = as_int(row.get("emails_sent_count")) or 0
            stats.contacted = as_int(row.get("contacted_count")) or 0
            stats.leads = as_int(row.get("leads_count")) or 0
            stats.bounced = as_int(row.get("bounced_count")) or 0
            stats.unsubscribed = as_int(row.get("unsubscribed_count")) or 0
            stats.real_replies = real_replies(row)
            stats.auto_replies = auto_replies(row)
            stats.opportunities = as_int(row.get("total_opportunities")) or 0
            stats.opportunity_value = as_int(row.get("total_opportunity_value")) or 0
            if not has_unique_reply_count(row):
                stats.notes.append(
                    "reply_count_unique was missing; real replies are reply_count minus automatic")

        stats.variants = parse_variants(step_rows(client, cid))
        leads, partial = replied_leads(client, cid)
        stats.partial = partial
        stats.duplicate_leads = getattr(leads, "dropped_duplicates", 0)
        if stats.duplicate_leads:
            stats.notes.append("%d duplicate replied lead(s) from the cursor walk, counted once"
                               % stats.duplicate_leads)
        stats.status_counts = count_statuses(leads)
        stats.positives = positives_from_leads(leads)
        stats.open_positives = open_positives_from_leads(leads)
        stats.closed_out = closed_out_from_leads(leads)
        stats.negatives = negatives_from_leads(leads)
        unreadable = stats.status_counts.get("unreadable", 0)
        if unreadable:
            stats.notes.append("%d replied lead(s) carry an unreadable lt_interest_status" % unreadable)
        attach_positives(stats.variants, leads)

        try:
            cmeta = campaign_meta(client, cid)
            stats.name = stats.name or cmeta["name"]
            stats.daily_limit = cmeta["daily_limit"]
            stats.sending_days = cmeta["sending_days"]
            stats.inboxes = cmeta["inboxes"]
            stats.inbox_emails = cmeta["email_list"]
            stats.status = cmeta["status"]
            if not stats.is_active:
                stats.notes.append("campaign status is %s, not active" % stats.status)
        except Exception as exc:  # noqa: BLE001 - a missing campaign object must not kill the run
            logger.warning("could not read campaign %s (%s); using default schedule", cid, exc)
            stats.notes.append("campaign object unreadable: %s" % str(exc)[:120])

        if daily_start and daily_end:
            try:
                daily_rows = client.daily_campaign_analytics(cid, daily_start, daily_end) or []
                stats.daily_rows_seen = len(daily_rows)
                stats.observed_sends_per_day = observed_rate(daily_rows)
                if stats.sends_nothing:
                    stats.notes.append(
                        "no sends in the %s to %s window; the rate is 0, not the daily limit"
                        % (daily_start, daily_end))
            except Exception as exc:  # noqa: BLE001
                logger.warning("daily analytics for %s failed (%s); falling back to daily_limit", cid, exc)
                stats.notes.append("daily analytics unavailable: %s" % str(exc)[:120])
        out[key] = stats
    return out
