"""No-show detection and recovery (Blueprint S5, SOP-005 repeat policy).

Detection (``detect``): GHL never marks no-shows itself. We use Zoom
participant-join events (normalised by zoom_webhook.py into the store under
``joins:<meeting_id>``):

* a non-host, non-bot join inside the meeting window and at or before
  start + 10 min                                         -> 'showed'
* an evidence channel exists but nobody joined, now < start + 10 min -> 'pending'
* an evidence channel exists but nobody joined, now >= start + 10 min -> 'no_show'
* fallback when there are no join events at all and the call has ended: a
  Fireflies transcript length of 0 -> 'no_show', > 0 -> 'showed'
* **no evidence channel at all** -> 'unknown'. "Zoom told us nobody joined"
  and "we have no Zoom telemetry" are not the same thing: the Discovery Call
  calendar is still on Google Meet and no Zoom app exists, so treating silence
  as a no-show flags every held call. ``process`` leaves the appointment
  pending and asks Lorenzo to mark it by hand instead (an internal GHL task).

An evidence channel means: at least one join was recorded for this meeting
(host, bot or lead), or Zoom told us the meeting started or ended, or a
Fireflies transcript length was supplied, or the appointment already carries a
GHL ``appointmentStatus`` of showed/noshow (which always wins).

``process`` is the state machine the tick calls for every appointment past
its start. On the first 'no_show' it marks the GHL appointment ``noshow``
(guarded write), moves nothing in the pipeline, stores ``no_show_count`` per
contact and schedules the recovery ladder. A non-host join arriving after the
flag produces a 'late_show' event: recovery is cancelled and the appointment
is set back to ``showed`` (guarded).

Recovery (section 2 rebuild, 2026-09-23; go-live timing and copy change
2026-09-24; copy in sections/2_booked_calls/copy_signed_off.md, word for
word). Email only, every email a reply in the lead's cold-email thread
(thread_reply.send_lead_email; the subject is only used for the GHL
fallback), never a booking link. S = scheduled start, "10:00 lead" = 10:00 in
the lead's zone (CT when unknown); business days skip Saturday and Sunday.

  N1 ns_still_on_email     S+5, BEFORE the flag, only with Zoom evidence (the
                           meeting started or the host joined) and no lead
                           join; once per appointment + start; never at or
                           after S+10
  First miss (count 1):
  N3 ns_reschedule_email   max(flag, S+25 min)                  two fresh slots
  N4 ns_d1_email           1 business day after, 10:00 lead     two fresh slots
  N5 ns_d2_value_email     2 business days after, 10:00 lead    two fresh slots
                           (skipped ``no_niche_point`` with no niche/offer on file)
  N9 ns_d3_retry_email     3 business days after, 10:00 lead    two fresh slots
  N6 ns_d5_yes_no_email    5 business days after, 10:00 lead    two fresh slots
  N7 ns_d7_breakup_email   7 business days after, 10:00 lead
                           -> nurture.enroll(no_show_no_rebook) + stage Follow Up Later
  Second miss (count 2): N1, N3 ``.repeat`` at S+25 (two fresh slots),
                           N6 3 business days after
                           -> nurture.enroll (+ the SOP-005 pattern note)
  Third miss (count 3+): N1, N8 ns_third_miss_email at S+25 (no slots)
                           -> nurture.enroll + stage Lost

A slot email claims two fresh times (never ones this lead was offered before).
N4 / N5 / N6 say the earlier times "got taken": once one of them reaches the
lead it gives back every earlier time still held for the lead, and they go out
only after an earlier slot email of the same ladder reached the lead (else
``no_prior_offer``). N3 and N9 give nothing back: N9 offers fresh times
without saying the earlier ones were taken, so after N9 the lead holds two
pairs (N9's and the one before) until N6 reaches them or the times pass.

No two emails of a ladder reach the lead less than SUPERSEDE_MARGIN (8 h)
apart. A late email never goes out once the next email of its ladder is due
within the margin or already went out, and no email goes out less than the
margin after an earlier one of its ladder reached the lead: both close as
``superseded``, except the ladder's last email, which waits for the end of the
margin (its hand-off must run). So a no-show marked by hand the next morning
gets N3 at once, N4 closes, and N5 goes on its own day.

Any reply from the lead since the call's start stops the rest (``replied``,
read from the lead row's ``last_inbound_at`` via thread_reply.find_thread);
a rebooking cancels it (``rebooked``).
"""
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from shared import settings, slots
from shared.settings import TZ

from services.reply_engine import show_rate as sr
from services.reply_engine.show_rate import (
    HELD,
    NICHES,
    Touch,
    call_link_of,
    company_of,
    first_name_of,
    fmt_time_only,
    fmt_when,
    lead_tz_of,
    next_send_window_open,
    niche_of,
    note_template_hold,
    record_held,
    stamp_touch,
    tagged_offer,
)

logger = logging.getLogger("reply_engine.no_show")

NO_SHOW_GRACE = timedelta(minutes=10)
# a join is only evidence for THIS appointment when it falls inside the meeting
# window. Personal Meeting IDs and recurring links are reused, and
# joins_by_appt accumulates across reschedules of the same appointment id.
JOIN_WINDOW_BEFORE = timedelta(minutes=30)
JOIN_WINDOW_AFTER = timedelta(minutes=30)
# Notetaker detection. These used to be matched as bare substrings against the
# whole display name AND the whole email, so "Fred Wilson", "Manuel Gongora"
# and "gongoraservices.com" were all discarded as bots and the lead sitting on
# the call was flagged a no-show. Names are matched on whole tokens (or as the
# first word of the display name, which is how every notetaker announces
# itself: "Fred from Fireflies", "Otter.ai Notetaker"); email is matched on the
# DOMAIN only, against known notetaker domains.
BOT_NAME_MARKERS = ("fireflies", "fireflies.ai", "notetaker", "notetaker.ai", "otter",
                    "otter.ai", "read.ai", "fathom", "fathom.video", "gong", "gong.io",
                    "tl;dv", "tldv", "tldv.io")
BOT_NAME_PHRASES = ("meeting assistant", "ai notetaker", "note taker", "meeting recorder")
BOT_EMAIL_DOMAINS = ("fireflies.ai", "otter.ai", "read.ai", "fathom.video", "fathom.ai",
                     "tldv.io", "gong.io", "grain.com", "sembly.ai", "avoma.com",
                     "fellow.app", "supernormal.com", "circleback.ai", "notetaker.ai")
_BOT_TOKEN_RE = re.compile(r"[^a-z0-9.;]+")
# recovery-only slot registry. approval.py owns "offered_slots" as a list of
# {"slot","lead","at","approval"} dicts; writing bare ISO strings into it broke
# every later positive-reply draft. Both readers union the two.
OFFERED_SLOTS_KEY = "offered_slots_recovery"
# "try again next tick", not "this touch is done". no_contact_id is retryable
# because the GHL contact upsert often has not returned an id on the tick that
# flags the miss, and burning the touch loses the whole ladder for that lead.
RETRYABLE_SKIP_REASONS = ("ghl_token_missing", "no_contact_id")
# ...but not forever: a permanently broken contact must not generate an error
# row every 5 minutes until someone notices.
MAX_TOUCH_ATTEMPTS = 12

# ------------------------------------------------------------ the ladder
N1 = "ns_still_on_email"
N3 = "ns_reschedule_email"
N4 = "ns_d1_email"
N5 = "ns_d2_value_email"
N6 = "ns_d5_yes_no_email"
N7 = "ns_d7_breakup_email"
N8 = "ns_third_miss_email"
N9 = "ns_d3_retry_email"  # added 2026-09-24; it sits between N5 and N6 in the ladder
REPEAT_SUFFIX = ".repeat"  # the second miss's N3 (catalogue id no_show.ns_reschedule_email.repeat)

# Timing rules, (kind, value):
#   ("start", td)          S + td, and never before the flag (the flag is S+10 or later)
#   ("business_days", n)   n business days after the call's day, 10:00 lead-local
#   ("days", n)            n calendar days after the call's day, moved to the next
#                          weekday, 10:00 lead-local (no ladder uses it since 2026-09-24)
STILL_ON_AFTER = timedelta(minutes=5)
RESCHEDULE_AFTER = timedelta(minutes=25)
LADDER_HOUR = 10
AT_S5 = ("start", STILL_ON_AFTER)
AT_S25 = ("start", RESCHEDULE_AFTER)

# Every lead-facing message the ladder can send, in order, as (template_key,
# channel, timing rule). template_approvals._no_show_entries enumerates this
# (plus ns_reschedule_email.repeat) to build the catalogue, so every key is
# here, N8 included. N1 goes out before the flag (still_on_nudge); which of
# the others a miss gets is LADDERS[count].
FULL_SEQUENCE = (
    (N1, "email", AT_S5),
    (N3, "email", AT_S25),
    (N4, "email", ("business_days", 1)),
    (N5, "email", ("business_days", 2)),
    (N9, "email", ("business_days", 3)),
    (N6, "email", ("business_days", 5)),
    (N7, "email", ("business_days", 7)),
    (N8, "email", AT_S25),
)
# The touches after the flag, per miss count (1, 2, 3+): (template_key, rule).
LADDERS = {
    1: ((N3, AT_S25), (N4, ("business_days", 1)), (N5, ("business_days", 2)), (N9, ("business_days", 3)),
        (N6, ("business_days", 5)), (N7, ("business_days", 7))),
    2: ((N3, AT_S25), (N6, ("business_days", 3))),
    3: ((N8, AT_S25),),
}
# What happens once the LAST touch of a ladder has gone out.
LADDER_AFTER = {1: "stage:follow_up_later", 2: "note:second_no_show_pattern", 3: "stage:lost"}
NURTURE_REASON = "no_show_no_rebook"

# The emails that offer two times ({slots}); each claims two fresh ones.
SLOT_TEMPLATES = (N3, N4, N5, N9, N6)
# The emails that say the earlier times "got taken": only after an earlier slot
# email of the same ladder reached the lead, and only they give the earlier
# times back. N9 offers times without that line, so the offer before it stays
# held until N6 (_offer_reached_lead).
TAKEN_TEMPLATES = (N4, N5, N6)

# Placeholders render() leaves in place when it has no value. A text carrying
# one is never sent (a slot email with no two held times, N5 with no niche
# line); the catalogue shows them as {slots} / {niche_point}.
SLOTS_PLACEHOLDER = "{slots}"
NICHE_POINT_PLACEHOLDER = "{niche_point}"

# N5's line per (niche, offer), verbatim from copy_signed_off.md. No campaign
# on file: no line, and N5 is skipped (never a generic one).
NICHE_POINT = {
    ("cleaning", "reactivation"): "I'd set up emails and texts to every account that cancelled, stopped renewing "
                                  "or never closed, and the ones ready to talk land on your calendar.",
    ("bookkeeping", "reactivation"): "I'd reach back out to your lost inquiries and former clients, timed around "
                                     "tax season, quarterly estimates and year-end cleanup.",
    ("recruiting", "reactivation"): "I'd set up follow-up sequences to your dormant and near-miss client accounts.",
    ("cleaning", "outbound"): "I'd watch for new leases, office expansions, property-manager changes and new "
                              "construction, then reach out under your name and put walkthroughs on your "
                              "calendar.",
    ("bookkeeping", "outbound"): "I'd watch for new business formations, part-time bookkeeper job posts and "
                                 "second locations, then reach out to those businesses under your name.",
    ("recruiting", "outbound"): "I'd watch job boards for open roles in your specialties, then reach out to the "
                                "hiring managers under your agency's name.",
}


# -------------------------------------------------------------- detection
def _email_domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].strip().strip(".") if "@" in email else ""


def is_bot(join: Dict[str, Any]) -> bool:
    """True only for a known notetaker identity.

    A bare substring match over the name and the whole email address called
    "Fred Wilson" a Fireflies bot and "manuel@gongoraservices.com" a Gong bot,
    and a discarded lead join is how someone who attended ends up in the
    recovery ladder. So: whole tokens in the display name, a known
    multi-word product phrase, or a known notetaker email DOMAIN. Never a
    fragment of a first name, and never the local part of an address.
    """
    name = str(join.get("name") or join.get("user_name") or "").lower()
    email = str(join.get("email") or "").lower()
    domain = _email_domain(email)
    if domain and any(domain == d or domain.endswith("." + d) for d in BOT_EMAIL_DOMAINS):
        return True
    if any(p in name for p in BOT_NAME_PHRASES):
        return True
    tokens = [t.strip(".") for t in _BOT_TOKEN_RE.split(name)]
    return any(t in BOT_NAME_MARKERS for t in tokens if t)


def is_host(join: Dict[str, Any], host_emails: Optional[List[str]] = None) -> bool:
    if join.get("is_host") is True:
        return True
    email = str(join.get("email") or "").lower()
    hosts = [h.lower() for h in (host_emails or default_host_emails())]
    return bool(email) and email in hosts


def default_host_emails() -> List[str]:
    owner = settings.IDS.get("owner", {})
    out = [owner.get("email"), owner.get("calendar_email")]
    return [e for e in out if e]


def lead_joins(joins: List[Dict[str, Any]], host_emails: Optional[List[str]] = None,
               lead_emails: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Non-host, non-bot joins.

    ``lead_emails`` (the appointment's own contact address) always wins over
    the notetaker heuristic: whatever a lead calls themselves on Zoom, a join
    from the address we booked is the lead turning up.
    """
    known = set(e.lower() for e in (lead_emails or []) if e)
    out = []
    for j in joins or []:
        if is_host(j, host_emails):
            continue
        email = str(j.get("email") or "").lower()
        if email and email in known:
            out.append(j)
            continue
        if is_bot(j):
            continue
        out.append(j)
    return out


def lead_emails_of(appointment: Dict[str, Any]) -> List[str]:
    return [e for e in (appointment.get("email"), appointment.get("lead_email")) if e]


def _join_id(join: Dict[str, Any]) -> str:
    """Stable identity for one join, used to remember which joins a verdict
    already accounted for (Zoom redelivers the same event)."""
    return "%s|%s|%s" % (join.get("participant_id") or "", join.get("email") or "",
                         join.get("at_iso") or join.get("join_time") or join.get("at") or "")


def _join_time(join: Dict[str, Any]) -> Optional[datetime]:
    raw = join.get("at_iso") or join.get("join_time") or join.get("at")
    if raw is None:
        return None
    try:
        return slots.parse_iso(raw)
    except (ValueError, TypeError):
        return None


def appointment_window(appointment: Dict[str, Any]):
    """(earliest, latest) instants a join can belong to this appointment."""
    start = slots.parse_iso(appointment["start_iso"])
    end = slots.parse_iso(appointment["end_iso"]) if appointment.get("end_iso") else start + timedelta(minutes=15)
    return start - JOIN_WINDOW_BEFORE, end + JOIN_WINDOW_AFTER


def joins_in_window(appointment: Dict[str, Any], joins: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop joins that cannot belong to this appointment (a stale join on a
    reused meeting id, or a join from an earlier instance of the same id)."""
    lo, hi = appointment_window(appointment)
    out = []
    for j in joins or []:
        t = _join_time(j)
        if t is None:
            continue
        if lo <= t <= hi:
            out.append(j)
    return out


def ghl_status_verdict(appointment: Dict[str, Any]) -> Optional[str]:
    """A hand-set GHL appointmentStatus always wins over telemetry."""
    status = str(appointment.get("ghl_status") or "").strip().lower()
    if status == "showed":
        return "showed"
    if status in ("noshow", "no_show", "no-show"):
        return "no_show"
    return None


def has_evidence_channel(
    appointment: Dict[str, Any],
    joins: List[Dict[str, Any]],
    fireflies_transcript_len: Optional[int] = None,
    meeting_signals: Optional[Dict[str, Any]] = None,
) -> bool:
    """True when something could have told us whether the lead turned up."""
    if joins:
        return True
    if fireflies_transcript_len is not None:
        return True
    if meeting_signals and (meeting_signals.get("started") or meeting_signals.get("ended")):
        return True
    return False


def detect(
    now: datetime,
    appointment: Dict[str, Any],
    joins: List[Dict[str, Any]],
    fireflies_transcript_len: Optional[int] = None,
    host_emails: Optional[List[str]] = None,
    grace: timedelta = NO_SHOW_GRACE,
    meeting_signals: Optional[Dict[str, Any]] = None,
) -> str:
    """'showed' | 'no_show' | 'pending' | 'unknown'."""
    now = slots.ensure_aware(now, TZ)
    start = slots.parse_iso(appointment["start_iso"])
    end = slots.parse_iso(appointment["end_iso"]) if appointment.get("end_iso") else start + timedelta(minutes=15)
    deadline = start + grace
    forced = ghl_status_verdict(appointment)
    if forced is not None:
        return forced
    window_joins = joins_in_window(appointment, joins)
    leads = lead_joins(window_joins, host_emails, lead_emails_of(appointment))
    for j in leads:
        t = _join_time(j)
        if t is not None and t <= deadline:
            return "showed"
    if not window_joins and fireflies_transcript_len is not None:
        # a transcript with words in it is positive proof someone spoke, at any
        # time. Only the EMPTY transcript has to wait for the call to end (a
        # recap fetched at start+2 min is empty because the call is still
        # running, which is not evidence of a no-show).
        if int(fireflies_transcript_len) > 0:
            return "showed"
        if now >= end:
            return "no_show"
        return "pending"
    if not has_evidence_channel(appointment, window_joins, fireflies_transcript_len, meeting_signals):
        # nothing could have told us either way: never guess a no-show.
        return "unknown"
    if now < deadline:
        return "pending"
    return "no_show"


# ---------------------------------------------------------------- copy
def known_offer(appointment: Dict[str, Any]) -> Optional[str]:
    """The offer on file, or None. offer_of() falls back to "reactivation";
    N5 must not: with no offer on file there is no approved line."""
    offer = str(appointment.get("offer") or "").strip().lower()
    if offer in ("reactivation", "outbound"):
        return offer
    tagged = tagged_offer(appointment)
    if tagged:
        return tagged
    camp = settings.CAMPAIGNS.get(appointment.get("campaign_key") or "") or settings.CAMPAIGN_BY_ID.get(
        appointment.get("campaign_id"))
    if camp and camp.get("offer") in ("reactivation", "outbound"):
        return camp["offer"]
    return None


def niche_point(appointment: Dict[str, Any]) -> Optional[str]:
    """N5's approved line for this lead's campaign, or None (no campaign or no
    offer on file: N5 is skipped, never a generic line)."""
    niche = niche_of(appointment)
    offer = known_offer(appointment)
    if niche not in NICHES or offer is None:
        return None
    return NICHE_POINT.get((niche, offer))


def render(template_key: str, appointment: Dict[str, Any], start: datetime, slots_text: str, count: int) -> Dict[str, Any]:
    """{"subject", "body"} for one ladder email, word for word from
    copy_signed_off.md. ``count`` picks the second miss's N3 (``.repeat``).
    ``slots_text`` empty leaves "{slots}" in place and a missing niche line
    leaves "{niche_point}": such a text is never sent (unfilled())."""
    first = first_name_of(appointment)
    company = company_of(appointment)
    link = call_link_of(appointment)
    two = slots_text or SLOTS_PLACEHOLDER

    if template_key == N1:
        if link:
            on_now = "I'm on the call now. Here's the link:\n%s" % link
        else:
            on_now = "I'm on the call now. The link is on your calendar invite."
        body = "Hey %s,\n\n%s\n\nLorenzo" % (first, on_now)
        return {"subject": "I'm on", "body": body}
    if template_key == N3 and int(count or 1) >= 2:
        body = ("Hey %s,\n\n"
                "Looks like I missed you again on today's call. If this isn't a priority right now, just let me "
                "know. If you still want to talk, I can do %s. If you're not looking to grow %s right now, "
                "that's fine too, just tell me.\n\nLorenzo") % (first, two, company)
        return {"subject": "Missed you again", "body": body}
    if template_key == N3:
        body = ("Hey %s,\n\n"
                "Looks like I missed you on our call today. I understand things come up, so let's get another "
                "call on the books at a time that works well for you.\n\n"
                "Could we do %s? Just reply with the one that works.\n\nLorenzo") % (first, two)
        return {"subject": "New time for our call", "body": body}
    if template_key == N4:
        body = ("Hey %s,\n\n"
                "Those two times got taken, but I can do %s if you still want to find 15 minutes. "
                "Just reply with the one that works.\n\nLorenzo") % (first, two)
        return {"subject": "Two open times", "body": body}
    if template_key == N5:
        point = niche_point(appointment) or NICHE_POINT_PLACEHOLDER
        body = ("Hey %s,\n\n"
                "One thing I was going to walk you through on our call:\n\n"
                "%s\n\n"
                "The last two times got taken, but if that's worth 15 minutes, I've got %s open. "
                "Just say which one works.\n\nLorenzo") % (first, point, two)
        return {"subject": "One thing for %s" % company, "body": body}
    if template_key == N9:
        body = ("Hey %s,\n\n"
                "Trying once more to get our call back on the calendar. I can do %s. "
                "Just reply with the one that works.\n\nLorenzo") % (first, two)
        return {"subject": "Still want to talk?", "body": body}
    if template_key == N6:
        body = ("Hey %s,\n\n"
                "Quick one on the call: still want to chat, later, or not a fit?\n\n"
                "A one-word answer is plenty. If it's later, just tell me roughly when. If you still want to chat, "
                "the last two times got taken, but I can do %s.\n\nLorenzo") % (first, two)
        return {"subject": "Quick one", "body": body}
    if template_key == N7:
        body = ("Hey %s,\n\n"
                "I'll leave this with you for now.\n\n"
                "If the timing gets better later on, just reply here and I'll send over a couple of times.\n\n"
                "Lorenzo") % first
        return {"subject": "Leaving the door open", "body": body}
    if template_key == N8:
        body = ("Hey %s,\n\n"
                "Missed you again today. I don't think this is worth pursuing anymore, and it doesn't make sense "
                "for either of us. Wish you the best of luck with %s.\n\nLorenzo") % (first, company)
        return {"subject": "Closing this out", "body": body}
    raise KeyError("unknown template %s" % template_key)


def unfilled(copy_or_body: Any) -> Optional[str]:
    """Why this text must not go out, or None: a slot line with no times
    (``no_slots``) or N5 with no niche line (``no_niche_point``)."""
    text = copy_or_body if isinstance(copy_or_body, str) else (
        "%s\n%s" % ((copy_or_body or {}).get("subject") or "", (copy_or_body or {}).get("body") or ""))
    if NICHE_POINT_PLACEHOLDER in text:
        return "no_niche_point"
    if SLOTS_PLACEHOLDER in text:
        return "no_slots"
    return None


# ------------------------------------------------------------ scheduling
def ladder_for_count(count: int) -> Tuple[Tuple[str, Any], ...]:
    """(template_key, rule) for the touches after the Nth flag (count >= 1)."""
    return LADDERS[max(1, min(3, int(count or 1)))]


def sequence_for_count(count: int) -> List[Tuple[str, str, Any]]:
    """(template_key, channel, rule) for the Nth miss: N1 first (it goes out
    before the flag), then the ladder."""
    return [(N1, "email", AT_S5)] + [(k, "email", rule) for k, rule in ladder_for_count(count)]


def _local_ten(day: date, tz) -> datetime:
    naive = datetime(day.year, day.month, day.day, LADDER_HOUR, 0)
    local = tz.localize(naive) if hasattr(tz, "localize") else naive.replace(tzinfo=tz)
    return slots.to_tz(local, TZ)


def _next_weekday(day: date) -> date:
    while day.weekday() >= 5:
        day = day + timedelta(days=1)
    return day


def _add_business_days(day: date, n: int) -> date:
    count = 0
    while count < n:
        day = day + timedelta(days=1)
        if day.weekday() < 5:
            count += 1
    return day


def touch_time(rule: Any, start: datetime, flagged_at: datetime, lead_tz=None) -> datetime:
    """When a ladder touch is armed (CT). ``start`` rules: S + offset, never
    before the flag. Day rules: 10:00 lead-local (CT when the zone is unknown)
    on the day the rule names, counted from the call's own (lead-local) day,
    then kept inside the 07:00-19:00 weekday send window for CT and the lead."""
    kind, value = rule
    start = slots.to_tz(slots.ensure_aware(start, TZ), TZ)
    flagged_at = slots.to_tz(slots.ensure_aware(flagged_at, TZ), TZ)
    if kind == "start":
        return max(flagged_at, start + value)
    tz = lead_tz if lead_tz is not None else TZ
    miss_day = start.astimezone(tz).date()
    if kind == "business_days":
        day = _add_business_days(miss_day, int(value))
    elif kind == "days":
        day = _next_weekday(miss_day + timedelta(days=int(value)))
    else:
        raise ValueError("unknown timing rule %r" % (rule,))
    return next_send_window_open(_local_ten(day, tz), lead_tz=lead_tz, weekdays_only=True)


def synthetic_free_slots(now: datetime, days: int = 7) -> List[datetime]:
    """Open-hours grid (12:00-18:00 CT, 15-min) used only when GHL cannot
    answer. Marked synthetic; live never offers these times (the slot email waits)."""
    now_ct = slots.to_tz(slots.ensure_aware(now, TZ), TZ)
    out = []
    for d in range(0, days + 1):
        day = (now_ct + timedelta(days=d)).date()
        for hour in range(settings.SLOT_WINDOW[0], settings.SLOT_WINDOW[1]):
            for minute in (0, 30):
                out.append(TZ.localize(datetime(day.year, day.month, day.day, hour, minute)))
    return out


def _approval_offered(store, now: datetime) -> List[str]:
    """The slots approval.py has promised to other leads (dict registry)."""
    try:
        from services.reply_engine import approval as approval_mod
    except Exception as exc:  # noqa: BLE001 - approval is another brief's module
        logger.warning("approval registry unavailable: %s", exc)
        return []
    try:
        return list(approval_mod.offered_slots(store, now) or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("approval.offered_slots failed: %s", exc)
        return []


def recovery_offered(store, now: Optional[datetime] = None) -> List[str]:
    """Slots this module has already offered in recovery emails, with times
    that are already in the past pruned away (the key used to grow forever)."""
    rows = store.get(OFFERED_SLOTS_KEY, []) or []
    if not isinstance(rows, list):
        return []
    keep, changed = [], False
    for row in rows:
        iso = row.get("slot") if isinstance(row, dict) else row
        if not isinstance(iso, str):
            changed = True
            continue
        if now is not None:
            try:
                if slots.parse_iso(iso) < slots.ensure_aware(now, TZ):
                    changed = True
                    continue
            except (ValueError, TypeError):
                changed = True
                continue
        keep.append(iso)
    if changed:
        try:
            store.set(OFFERED_SLOTS_KEY, keep)
        except Exception as exc:  # noqa: BLE001
            logger.warning("pruning %s failed: %s", OFFERED_SLOTS_KEY, exc)
    return keep


def free_slot_list(now: datetime, ghl) -> Tuple[List[Any], str]:
    """``(free, source)``: GHL's free slots for the next 8 days, or the
    synthetic open-hours grid when GHL cannot answer (no token)."""
    now_ct = slots.to_tz(slots.ensure_aware(now, TZ), TZ)
    free = None
    source = "ghl"
    try:
        start_ms = int(now_ct.timestamp() * 1000)
        end_ms = int((now_ct + timedelta(days=8)).timestamp() * 1000)
        raw = ghl.get_free_slots(settings.GHL_CALENDAR_ID, start_ms, end_ms) if ghl is not None else None
        free = _flatten_free_slots(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("free-slots lookup failed: %s", exc)
        free = None
    if not free:
        free = synthetic_free_slots(now_ct)
        source = "synthetic_open_hours"
    return free, source


RECOVERY_CLAIM_SOURCE = "no_show_recovery"
# Re-picks from the same free-slot list after another lead's claim won the race.
RECOVERY_CLAIM_ATTEMPTS = 3


def _recovery_claim_lead(appointment: Dict[str, Any]) -> str:
    """The registry's ``lead`` for this recovery. An appointment with no email
    still needs an owner, or every row would count as someone else's."""
    email = str(appointment.get("email") or "").strip().lower()
    return email or "no_show:%s" % appointment.get("id")


def _recovery_claim_fields(appointment: Dict[str, Any]) -> Dict[str, Any]:
    return {"source": RECOVERY_CLAIM_SOURCE, "appointment": str(appointment.get("id"))}


def release_recovery_claim(store, appointment: Dict[str, Any], slot_isos: List[str]) -> None:
    """Undo a claim_recovery_slots whose times never reached the lead: this
    appointment's rows in approval's registry and the recovery-only key.
    Never raises."""
    isos = [i for i in (slot_isos or []) if isinstance(i, str) and i]
    if not isos or store is None:
        return
    try:
        from services.reply_engine import approval as approval_mod

        approval_mod.release_claimed(store, _recovery_claim_lead(appointment), isos,
                                     fields=_recovery_claim_fields(appointment))
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not release the recovery claim on %s: %s", isos, exc)
    wanted = set(isos)
    try:
        store.mutate(OFFERED_SLOTS_KEY,
                     lambda cur: [r for r in (cur or []) if (r.get("slot") if isinstance(r, dict) else r) not in wanted],
                     default=[])
    except Exception as exc:  # noqa: BLE001
        logger.warning("releasing %s from %s failed: %s", sorted(wanted), OFFERED_SLOTS_KEY, exc)


def _withheld(info: Optional[Dict[str, Any]], reason: str) -> Dict[str, Any]:
    """No times held: the slot email waits (never a single time, never a link)."""
    info = info or {}
    return {"slots": [], "text": "", "source": info.get("source") or "unavailable", "withheld": reason}


def claim_recovery_slots(now: datetime, ghl, store, appointment: Dict[str, Any],
                         slots_fn: Optional[Callable[[datetime], Dict[str, Any]]] = None,
                         attempts: int = RECOVERY_CLAIM_ATTEMPTS,
                         exclude: Optional[List[str]] = None) -> Dict[str, Any]:
    """Pick two times AND hold them for this lead, all or nothing.

    The recovery ladder used to pick from a registry read and append its
    reservation later (``add_once``, no conflict check), so across the GHL
    free-slot read gap another card could take the same times and two leads
    were emailed the same 15 minutes. The hold now goes through
    ``approval.claim_slots``: check and write inside one ``store.mutate``.

    On a conflict the times are re-picked from the SAME free-slot list (the
    other lead's claim is excluded), up to ``attempts`` times. When no
    conflict-free pair is left, or the registry cannot be read, it offers
    nothing (``slots: []``, ``text: ""``): a time is never offered twice, and
    the slot email waits for the next run (run_recovery). A later slot touch
    re-picks. ``exclude``: times never to pick (the lead's previous
    offer, so "those times got taken" is true). Returns the fresh_two_slots
    dict (``slots: []`` when nothing could be held).
    """
    now_ct = slots.to_tz(slots.ensure_aware(now, TZ), TZ)
    lead = _recovery_claim_lead(appointment)
    fields = _recovery_claim_fields(appointment)
    free = None  # type: Optional[Tuple[List[Any], str]]
    excluded = [i for i in (exclude or []) if isinstance(i, str)]  # type: List[str]
    info = None  # type: Optional[Dict[str, Any]]
    for _attempt in range(max(1, int(attempts))):
        if slots_fn is not None:
            info = slots_fn(now_ct)
        else:
            if free is None:
                free = free_slot_list(now_ct, ghl)
            info = fresh_two_slots(now_ct, ghl, store, already_offered=list(excluded), free_slots=free)
        info = info or {}
        isos = [i for i in (info.get("slots") or []) if isinstance(i, str) and i]
        if not isos:
            return info  # nothing to offer, nothing to hold
        if len(isos) < 2:
            return _withheld(info, "one_slot")  # never "Two times ...: <one time>"
        if set(isos) & set(exclude or []):
            return _withheld(info, "not_fresh")  # an injected picker offered the previous times again
        if store is None:
            return info
        try:
            from services.reply_engine import approval as approval_mod

            taken = approval_mod.claim_slots(store, lead, isos, now_ct, fields=fields)
        except Exception as exc:  # noqa: BLE001 - an unreadable registry offers nothing, never a double-offer
            logger.warning("could not claim the recovery slots %s for %s: %s", isos, appointment.get("id"), exc)
            return _withheld(info, "registry_unavailable")
        if not taken:
            for iso in isos:  # the recovery-only key's own readers (recovery_offered)
                try:
                    store.add_once(OFFERED_SLOTS_KEY, iso)
                except Exception as exc:  # noqa: BLE001 - approval's registry already holds it
                    logger.warning("reserving %s in %s failed: %s", iso, OFFERED_SLOTS_KEY, exc)
            return info
        logger.info("recovery slots %s for %s were taken by another lead; re-picking", taken, appointment.get("id"))
        excluded.extend(t for t in taken if t not in excluded)
        if slots_fn is not None:
            break  # an injected picker cannot be steered away from the taken times
    return _withheld(info, "slot_taken")


def fresh_two_slots(now: datetime, ghl, store, already_offered: Optional[List[str]] = None,
                    free_slots: Optional[Tuple[List[Any], str]] = None) -> Dict[str, Any]:
    """Two offerable slots via GHL free-slots; synthetic grid when GHL is
    unavailable (no token). Returns {'slots': [iso], 'text', 'source'}.

    ``free_slots`` is a ``free_slot_list`` result to pick from instead of
    reading GHL again (claim_recovery_slots re-picks from the same list after a
    conflict). This only PICKS: nothing is held until claim_recovery_slots."""
    now_ct = slots.to_tz(slots.ensure_aware(now, TZ), TZ)
    free, source = free_slots if free_slots is not None else free_slot_list(now_ct, ghl)
    offered = list(already_offered or []) + recovery_offered(store, now_ct) + _approval_offered(store, now_ct)
    cands = slots.candidate_slots(free, now_ct, already_offered=offered)
    two = slots.pick_two(cands)
    if len(two) < 2:
        # "Could we do Tue 2:00pm CT?" would name one time.
        # Nothing is offered instead (the slot email waits), as the
        # cadence never offers a single slot either.
        return {"slots": [], "text": "", "source": source, "withheld": "one_slot" if two else "no_slots"}
    return {"slots": [t.isoformat() for t in two], "text": slots.format_slots(two), "source": source}


def _flatten_free_slots(raw: Any) -> List[str]:
    """GHL returns {"2026-09-23": {"slots": ["2026-09-23T12:00:00-05:00", ...]}, ...}."""
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    out = []  # type: List[str]
    for key, value in raw.items():
        if key in ("traceId",):
            continue
        if isinstance(value, dict):
            out.extend(str(x) for x in value.get("slots", []))
        elif isinstance(value, list):
            out.extend(str(x) for x in value)
    return out


def recovery_touches(
    appointment: Dict[str, Any],
    flagged_at: datetime,
    count: int,
) -> List[Touch]:
    """The ladder touches after the Nth flag (count starts at 1), armed per
    LADDERS / touch_time. Bodies are rendered without times ("{slots}"): a
    slot email claims its two times when it is dispatched."""
    flagged_at = slots.to_tz(slots.ensure_aware(flagged_at, TZ), TZ)
    start = slots.to_tz(slots.parse_iso(appointment["start_iso"]), TZ)
    appt_id = str(appointment.get("id"))
    lead_tz = lead_tz_of(appointment)
    touches = []  # type: List[Touch]
    for template_key, rule in ladder_for_count(count):
        when = touch_time(rule, start, flagged_at, lead_tz)
        copy = render(template_key, appointment, start, "", count)
        touch = Touch(
            key="%s:%s:ns%d:%s" % (appt_id, start.isoformat(), count, template_key),
            appointment_id=appt_id,
            contact_id=appointment.get("contact_id"),
            when_iso=when.isoformat(),
            channel="email",
            template_key=template_key,
            subject=copy.get("subject"),
            body=copy["body"],
            meta={"no_show_count": count, "start_iso": start.isoformat(), "rule": "%s %s" % rule},
        )
        stamp_touch(touch, appointment, "no_show", count)
        touches.append(touch)
    # the last touch of the ladder carries the stage move and the nurture hand-off
    if touches:
        last = touches[-1]
        last.meta["after"] = LADDER_AFTER[max(1, min(3, int(count or 1)))]
        last.meta["nurture"] = True
    return touches


def recovery_key(appointment_id: str, start_iso: str) -> str:
    return "recovery:%s:%s" % (appointment_id, start_iso)


# What the recovery record keeps of the appointment: everything render(),
# niche_of / offer_of and the opt-out lookup read, so the copy re-rendered at
# dispatch (CT3 flag 3) is the copy rendered at flag time.
RECOVERY_SNAPSHOT_KEYS = ("id", "contact_id", "opportunity_id", "start_iso", "end_iso", "zoom_link", "meeting_link",
                          "email", "lead_email", "phone", "niche", "offer", "first_name", "contact_name", "name",
                          "company", "campaign_key", "campaign_id", "tags", "title", "lead_tz", "timezone",
                          "reschedule_link", "booking_url")


def offer_text(info: Optional[Dict[str, Any]]) -> str:
    """The slot line a recovery touch may carry: two held times, and in live
    only times GHL verified. Anything else is "" (the slot email waits)."""
    info = info or {}
    isos = [i for i in (info.get("slots") or []) if isinstance(i, str) and i]
    if len(isos) < 2:
        return ""
    if info.get("source") != "ghl" and settings.is_live():
        return ""
    return info.get("text") or ""


def rerender_for_dispatch(touch: Touch, appt: Dict[str, Any], slots_text: str = "") -> bool:
    """Re-render a ladder touch from the current code, the record's
    appointment snapshot and the times it offers now, and re-stamp it (CT3
    flag 3: a redeploy that changed a template's hash must not leave the
    pending touches stale). True when re-rendered; on an error the touch
    keeps its copy and stamp, and the gate judges those."""
    if touch.channel != "email":
        return False
    count = int((touch.meta or {}).get("no_show_count") or 1)
    try:
        start = slots.to_tz(slots.parse_iso((touch.meta or {}).get("start_iso") or appt["start_iso"]), TZ)
        copy = render(touch.template_key, appt, start, slots_text, count)
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("re-rendering %s for dispatch failed: %s", touch.key, type(exc).__name__)
        return False
    touch.subject, touch.body = copy.get("subject"), copy["body"]
    stamp_touch(touch, appt, "no_show", count)
    return True


# ------------------------------------------------------------ reply stop
def _row_inbound_at(row: Any) -> Optional[datetime]:
    raw = row.get("last_inbound_at") if isinstance(row, dict) else getattr(row, "last_inbound_at", None)
    if not raw:
        return None
    try:
        return slots.ensure_aware(slots.parse_iso(str(raw)), TZ)
    except (ValueError, TypeError):
        return None


def lead_replied_since(store, appointment: Dict[str, Any], since: datetime) -> Tuple[bool, Optional[str]]:
    """``(replied, error)``: has the lead written in since ``since``?

    The lead's rows are the ones thread_reply.find_thread resolves (the
    thread row, and every row of the lead's own address it looked at when
    there are several or none carries a thread); a reply is a
    ``last_inbound_at`` (the reply engine's router stamps it with the reply's
    received time) later than ``since``. Rows that name somebody else never
    count. ``error`` is set when the rows cannot be read: the caller holds
    rather than risk mailing a lead who already answered."""
    from services.reply_engine import thread_reply

    since = slots.ensure_aware(since, TZ)
    try:
        found = thread_reply.find_thread(store, appointment or {})
    except Exception as exc:  # noqa: BLE001 - an unreadable row may hide the reply
        return False, type(exc).__name__
    reason = found.get("reason")
    if reason == getattr(thread_reply, "LEAD_ROW_UNREADABLE", "lead_row_unreadable"):
        return False, reason
    rows = []  # type: List[Any]
    if found.get("state") is not None:
        rows.append(found["state"])
    if reason in (None, getattr(thread_reply, "AMBIGUOUS_THREAD", "ambiguous_thread"),
                  getattr(thread_reply, "NO_THREAD_IDS", "no_thread_ids")):
        for key in found.get("candidates") or []:
            try:
                rows.append(store.get(key))
            except Exception as exc:  # noqa: BLE001
                return False, type(exc).__name__
    for row in rows:
        at = _row_inbound_at(row)
        if at is not None and at > since:
            return True, None
    return False, None


# ------------------------------------------------------------ N1 (before the flag)
def still_on_key(appointment_id: str, start_iso: str) -> str:
    return "ns_still_on:%s:%s" % (appointment_id, start_iso)


def zoom_evidence(appointment: Dict[str, Any], joins: List[Dict[str, Any]],
                  meeting_signals: Optional[Dict[str, Any]] = None) -> bool:
    """Zoom told us the call is live on our side: the meeting started, or the
    host joined inside this appointment's window."""
    if meeting_signals and meeting_signals.get("started"):
        return True
    return any(is_host(j) for j in joins_in_window(appointment, joins))


def _new_summary() -> Dict[str, List[Any]]:
    return {"sent": [], "would_do": [], "skipped": [], "errors": [], "stage_moves": [], "cancelled": [],
            "held_template": [], "needs_attention": [], "maybe_sent": [], "deferred": [], "nurture": []}


def still_on_nudge(now: datetime, appointment: Dict[str, Any], joins: List[Dict[str, Any]], store, ghl,
                   instantly=None, meeting_signals: Optional[Dict[str, Any]] = None,
                   summary: Optional[Dict[str, List[Any]]] = None) -> Optional[str]:
    """N1 "I'm on": at S+5, when Zoom shows the call is live (meeting started
    or host joined) and the lead has not joined. Once per appointment + start
    (``ns_still_on:<id>:<start>`` claim), never at or after S+10 (MAX_LATENESS,
    the moment detection flags the miss).
    A dispatch that stays pending (send window, template hold, retryable
    transport) gives the claim back so the next run inside the window tries
    again; anything else keeps it. Returns the dispatch status, or None when
    nothing was due."""
    now = slots.to_tz(slots.ensure_aware(now, TZ), TZ)
    start = slots.to_tz(slots.parse_iso(appointment["start_iso"]), TZ)
    due = start + STILL_ON_AFTER
    if now < due or (now - due) >= MAX_LATENESS[N1]:
        return None  # N1 is a pre-flag nudge: S+5 up to (not including) S+10, the flag's moment
    if lead_joins(joins_in_window(appointment, joins), None, lead_emails_of(appointment)):
        return None
    if not zoom_evidence(appointment, joins, meeting_signals):
        return None
    appt_id = str(appointment.get("id"))
    claim = still_on_key(appt_id, start.isoformat())
    if not store.set_if_absent(claim, {"at": now.isoformat(), "state": "dispatching"}):
        return None  # sent (or being sent) already
    summary = summary if summary is not None else _new_summary()
    copy = render(N1, appointment, start, "", 1)
    touch = Touch(key="%s:%s:%s" % (appt_id, start.isoformat(), N1), appointment_id=appt_id,
                  contact_id=appointment.get("contact_id"), when_iso=due.isoformat(), channel="email",
                  template_key=N1, subject=copy["subject"], body=copy["body"],
                  meta={"start_iso": start.isoformat(), "no_show_count": 1})
    stamp_touch(touch, appointment, "no_show", 1)
    entry = {"key": touch.key, "channel": "email", "template": N1, "when": touch.when_iso}
    replied, error = lead_replied_since(store, appointment, start)
    if error:
        store.delete(claim)
        entry.update(reason="reply_check_failed", error=error)
        summary["errors"].append(entry)
        return "error"
    if replied:
        store.set(claim, {"at": now.isoformat(), "state": "done", "skip_reason": "replied"})
        entry["reason"] = "replied"
        summary["skipped"].append(entry)
        return "skipped"
    out = sr.dispatch_touch(touch, ghl, now, store=store, appointment=appointment, kind="no_show",
                            instantly=instantly)
    raw = touch.to_dict()
    _record_recovery_result(raw, out, entry, summary, now)
    if out.get("status") == HELD and out.get("hold") != THREAD_HOLD:
        note_template_hold(store, raw, out, now)
    if _stays_pending(out):
        store.delete(claim)
    else:
        store.set(claim, {"at": now.isoformat(), "state": "done", "status": out.get("status"),
                          "skip_reason": raw.get("skip_reason"), "transport": out.get("transport")})
    return out.get("status")


def state_key(appointment_id: str) -> str:
    return "noshow_state:%s" % appointment_id


# ------------------------------------------------------------ state machine
def _reset_for_new_start(store, appt_id: str, state: Dict[str, Any], start_iso: str, out: Dict[str, Any]) -> Dict[str, Any]:
    """The appointment moved (a rebooking through the widget keeps the id and
    changes startTime). Cancel the recovery tied to the old start and let the
    state machine run again for the new one."""
    old_start = state.get("start_iso")
    cancelled = _cancel_recovery(store, appt_id, old_start or "", reason="rebooked")
    fresh = {"state": "pending", "start_iso": start_iso, "previous_start_iso": old_start,
             "previous_state": state.get("state"), "rebooked_cancelled": cancelled}
    store.set(state_key(appt_id), fresh)
    out["events"].append("rebooked")
    out["state"] = "pending"
    out["rebooked_cancelled"] = cancelled
    return fresh


INTEREST_MEETING_COMPLETED = 3


def _lead_identity(store, appointment: Dict[str, Any], appt_id: str):
    """(lead_email, campaign_id) for this call.

    A GHL calendar event carries neither, so fall back to the
    ``appointment:<id>`` row booking.register_booking wrote, which has both.
    """
    emails = lead_emails_of(appointment)
    email = emails[0] if emails else None
    campaign_id = appointment.get("campaign_id")
    if not (email and campaign_id):
        try:
            rec = store.get("appointment:%s" % appt_id) or {}
        except Exception:  # noqa: BLE001
            rec = {}
        email = email or rec.get("lead_email")
        campaign_id = campaign_id or rec.get("campaign_id")
    return email, campaign_id


def mark_meeting_completed(store, appointment: Dict[str, Any], appt_id: str, instantly=None) -> Dict[str, Any]:
    """Blueprint S3 item 4: held -> Instantly Meeting Completed (3).

    Nothing in S4/S5 used to touch Instantly at all, so a call that was held
    sat at interest 2 (meeting_booked) until Lorenzo dragged the opportunity
    to Proposal Sent by hand and the nightly mirror mapped it through
    pipeline_sync.STAGE_TO_INTEREST. Every held call that did not immediately
    produce a proposal therefore read as still-booked, which is exactly the
    number the Section 6 positive->booked and show-rate KPIs divide by.

    Guarded like every other write: in shadow this records a would_do.
    """
    email, campaign_id = _lead_identity(store, appointment, appt_id)
    payload = {"lead_email": email, "campaign_id": campaign_id,
               "interest_value": INTEREST_MEETING_COMPLETED}
    if not email or not campaign_id:
        # A widget booking with no campaign behind it is not a failure: there
        # is no Instantly lead to move.
        return {"action": "update_interest_status", "payload": payload,
                "status": "skipped:no_instantly_lead"}
    if instantly is None and settings.is_live():
        # guard_write in live returns {"shadow": False} and performs nothing, so
        # without a client this would report "done" for a write that never
        # happened. jobs/appointments_tick builds the client and passes it; a
        # caller that does not gets told, not silently believed.
        logger.error("no Instantly client on a held call for %s: interest 3 was NOT written", email)
        return {"action": "update_interest_status", "payload": payload,
                "status": "skipped:no_instantly_client"}
    try:
        if instantly is not None:
            res = instantly.update_interest_status(email, campaign_id, INTEREST_MEETING_COMPLETED)
        else:
            res = settings.guard_write("instantly", "update_interest_status", payload)
    except Exception as exc:  # noqa: BLE001 - the verdict stands whatever Instantly says
        logger.warning("interest 3 failed for %s: %s", email, exc)
        return {"action": "update_interest_status", "payload": payload, "status": "error", "error": str(exc)}
    return _action("update_interest_status", payload, res)


def _show_rate_held(store, appointment_id: str, now: Optional[datetime] = None) -> bool:
    """Is this appointment still waiting on the approval card?

    Fails CLOSED: a hold that could not be read (a store error, or the
    show_rate module failing to import) counts as held. The cost is one tick
    in which no-show detection waits for this call; the other way round, one
    brief store error sent "Sorry we missed each other" and a recovery ladder
    to a prospect whose call Lorenzo never approved. Nothing is written on
    this path, so the next clean tick picks the call up where it was. Logged
    once per tick.
    """
    try:
        from services.reply_engine import show_rate
    except Exception as exc:  # noqa: BLE001
        logger.warning("show_rate is unavailable, so no call's hold can be read (treated as held): %s", exc)
        return True
    try:
        rec, error = show_rate.read_hold(store, appointment_id)
    except Exception as exc:  # noqa: BLE001
        rec, error = None, "%s: %s" % (type(exc).__name__, exc)
    if error:
        try:
            show_rate.log_hold_read_failure(now, appointment_id, error)
        except Exception:  # noqa: BLE001
            logger.warning("could not read the show-rate hold for %s: %s", appointment_id, error)
        return True
    return rec is not None


def process(
    now: datetime,
    appointment: Dict[str, Any],
    joins: List[Dict[str, Any]],
    store,
    ghl,
    fireflies_transcript_len: Optional[int] = None,
    slots_fn: Optional[Callable[[datetime], Dict[str, Any]]] = None,
    meeting_signals: Optional[Dict[str, Any]] = None,
    instantly=None,
    run_ladder: bool = True,
) -> Dict[str, Any]:
    """Advance one appointment. Returns {'state', 'events': [...], 'actions': [...]}.

    States: pending -> showed | no_show | unknown; no_show -> late_show (lead
    joined after the flag) | rebooked (the call moved) | done.

    Before the flag it sends N1 (still_on_nudge) when it is due. After the
    flag it runs this appointment's ladder (run_recovery) unless
    ``run_ladder`` is False (the --no-show-watch mode: N1 and detection only).
    ``out["run"]`` is the dispatch summary of both.
    """
    now = slots.to_tz(slots.ensure_aware(now, TZ), TZ)
    appt_id = str(appointment.get("id"))
    start = slots.to_tz(slots.parse_iso(appointment["start_iso"]), TZ)
    start_iso = start.isoformat()
    contact_id = appointment.get("contact_id")
    state = store.get(state_key(appt_id)) or {"state": "pending", "start_iso": start_iso}
    out = {"appointment_id": appt_id, "state": state.get("state"), "events": [], "actions": []}  # type: Dict[str, Any]

    # A call Lorenzo has not approved yet must not be chased. booking.book()
    # puts the appointment on the calendar at classification time with the GHL
    # invite withheld and the S4 ladder held, so the prospect has been told
    # nothing about it: "Sorry we missed each other" would be the first they
    # ever hear of the call, and the recovery ladder would run for a lead who
    # may still be vetoed.
    if _show_rate_held(store, appt_id, now):
        out["events"].append("awaiting_approval")
        return out

    # a reschedule keeps the appointment id and moves startTime: checked BEFORE
    # the `now < start` return, otherwise a rebooked no-show keeps marching
    # through "Should I close your file?" and lands in Follow Up Later.
    if state.get("start_iso") and state["start_iso"] != start_iso:
        state = _reset_for_new_start(store, appt_id, state, start_iso, out)
    elif not state.get("start_iso"):
        state["start_iso"] = start_iso

    if now < start:
        return out

    if state.get("state") in ("showed", "late_show", "done"):
        return out

    leads = lead_joins(joins_in_window(appointment, joins), None, lead_emails_of(appointment))
    if state.get("state") == "no_show":
        # ANY lead join inside this appointment's own window is a show, however
        # its timestamp compares to the flag: Zoom retries and backlogs
        # participant_joined, so a join at start+2 min can land after the
        # start+10 min flag. The stale-meeting-id worry this guard was written
        # for is already handled by joins_in_window(). Idempotency is keyed on
        # which joins have been accounted for, not on when they happened.
        seen = set(state.get("seen_joins") or [])
        late = [j for j in leads if _join_id(j) not in seen]
        if late:
            # they came, just late: stop recovery, flip the appointment back
            _cancel_recovery(store, appt_id, start_iso, reason="late_show")
            res = ghl.update_appointment_status(appt_id, "showed")
            out["actions"].append(_action("update_appointment_status", {"status": "showed"}, res))
            out["actions"].append(mark_meeting_completed(store, appointment, appt_id, instantly))
            _bump_no_show_count(store, contact_id or appt_id, -1)
            state.update({"state": "late_show", "late_show_at": now.isoformat(), "start_iso": start_iso})
            store.set(state_key(appt_id), state)
            out["events"].append("late_show")
            out["state"] = "late_show"
            return out
        # keep the sequence moving
        if run_ladder:
            out["run"] = run_recovery(now, store, ghl, appointment_id=appt_id, slots_fn=slots_fn,
                                      instantly=instantly)
        return out

    # N1 "I'm on" at S+5, before the verdict (it is only ever sent pre-flag)
    run = _new_summary()
    status = still_on_nudge(now, appointment, joins, store, ghl, instantly=instantly,
                            meeting_signals=meeting_signals, summary=run)
    if status is not None:
        out["events"].append("still_on:%s" % status)
        out["run"] = run

    verdict = detect(now, appointment, joins, fireflies_transcript_len=fireflies_transcript_len,
                     meeting_signals=meeting_signals)
    out["verdict"] = verdict
    if verdict == "pending":
        return out
    if verdict == "unknown":
        # no Zoom telemetry at all: ask Lorenzo instead of guessing.
        if now >= start + NO_SHOW_GRACE and not state.get("unknown_task_at"):
            action = _unknown_telemetry_task(now, appointment, ghl)
            out["actions"].append(action)
            state.update({"state": "pending", "start_iso": start_iso})
            if action.get("status") in ("done", "would_do"):
                # only remember the task when it really was created. Recording
                # it after a dropped write (no GHL token, HTTP error) silences
                # the retry forever and the call sits pending with nobody told.
                state["unknown_task_at"] = now.isoformat()
                out["events"].append("no_telemetry")
            else:
                out["events"].append("no_telemetry_task_failed")
                out["errors"] = out.get("errors", []) + [
                    {"appointment_id": appt_id, "action": "unknown_telemetry_task", "status": action.get("status")}]
            store.set(state_key(appt_id), state)
        out["state"] = "pending"
        return out
    if verdict == "showed":
        state.update({"state": "showed", "showed_at": now.isoformat(), "start_iso": start_iso,
                      "seen_joins": sorted(_join_id(j) for j in leads)})
        store.set(state_key(appt_id), state)
        # a held call clears the SOP-005 repeat counter: someone who misses,
        # attends, then misses again is not a repeat offender.
        _reset_no_show_count(store, contact_id or appt_id)
        res = ghl.update_appointment_status(appt_id, "showed")
        out["actions"].append(_action("update_appointment_status", {"status": "showed"}, res))
        out["actions"].append(mark_meeting_completed(store, appointment, appt_id, instantly))
        out["events"].append("showed")
        out["state"] = "showed"
        return out

    # ---- no_show
    # Claim the miss ONCE, before anything else. The counter used to be bumped
    # first and the state record written last, so a GHL 5xx in between left
    # count=1 with no state: the next tick flagged the same miss again, the
    # counter reached 2, and the lead's FIRST miss got the second-no-show copy
    # ("I know this is the second time the timing did not work out").
    flag_key = "noshow_flag:%s:%s" % (appt_id, start_iso)
    claimed = store.set_if_absent(flag_key, {"at": now.isoformat(), "contact_id": contact_id})
    if not claimed:
        # a previous attempt already owns this miss. Re-arm the state record if
        # it was lost, but never increment the counter a second time.
        count = int((store.get(flag_key) or {}).get("count") or store.get(count_key_for(contact_id or appt_id), 0) or 0) or 1
    else:
        count = _bump_no_show_count(store, contact_id or appt_id, 1)
        store.set(flag_key, {"at": now.isoformat(), "contact_id": contact_id, "count": count})
    # The ladder record is written once per miss. A record left by an attempt
    # that died before the state write is kept as it is: run_recovery may
    # already have sent from it, and rebuilding it would send those again.
    # Nothing is held at the flag: each slot email claims its own two times
    # when it goes out.
    rkey = recovery_key(appt_id, start.isoformat())
    touches = recovery_touches(appointment, now, count)
    store.set_if_absent(rkey, {
        "appointment": {k: appointment.get(k) for k in RECOVERY_SNAPSHOT_KEYS if appointment.get(k) is not None},
        "flagged_at": now.isoformat(),
        "no_show_count": count,
        "slots": {},  # the last offer that reached the lead
        "held_offers": [],  # every time offered to the lead and not yet called taken
        "touches": [t.to_dict() for t in touches],
    })
    state.update({"state": "no_show", "flagged_at": now.isoformat(), "count": count, "start_iso": start_iso})
    store.set(state_key(appt_id), state)
    res = ghl.update_appointment_status(appt_id, "noshow")
    out["actions"].append(_action("update_appointment_status", {"status": "noshow"}, res))
    note = "No-show #%d at %s (flagged %s). Recovery emails started (%s). Pipeline stage unchanged." % (
        count, fmt_when(start), now.isoformat(), ", ".join(k for k, _ in ladder_for_count(count)))
    if contact_id:
        nres = ghl.create_note(contact_id, note)
        out["actions"].append(_action("create_note", {"body": note}, nres))
    out["events"].append("no_show")
    out["state"] = "no_show"
    out["no_show_count"] = count
    out["recovery_touches"] = len(touches)
    if run_ladder:
        out["run"] = _merge_summaries(out.get("run"), run_recovery(now, store, ghl, appointment_id=appt_id,
                                                                    slots_fn=slots_fn, instantly=instantly))
    return out


def _merge_summaries(*parts: Optional[Dict[str, List[Any]]]) -> Dict[str, List[Any]]:
    out = _new_summary()
    for part in parts:
        for k, v in (part or {}).items():
            out.setdefault(k, []).extend(v)
    return out


def _action(name: str, payload: Dict[str, Any], res: Any) -> Dict[str, Any]:
    shadow = bool(isinstance(res, dict) and res.get("shadow"))
    status = "would_do" if shadow else ("skipped:ghl_token_missing" if res is None else "done")
    return {"action": name, "payload": payload, "status": status}


def count_key_for(owner: str) -> str:
    return "no_show_count:%s" % owner


def _reset_no_show_count(store, owner: str) -> None:
    if store.get(count_key_for(owner)):
        store.set(count_key_for(owner), 0)


def _bump_no_show_count(store, owner: str, delta: int) -> int:
    """Read-modify-write under one lock: two ticks bumping the same contact
    must not both read 0 and both write 1."""
    def _apply(current):
        return max(0, int(current or 0) + delta)

    return int(store.mutate(count_key_for(owner), _apply, default=0))


def _unknown_telemetry_task(now: datetime, appointment: Dict[str, Any], ghl) -> Dict[str, Any]:
    """No Zoom telemetry exists for this call, so Lorenzo marks it by hand."""
    first = first_name_of(appointment)
    company = company_of(appointment)
    start = slots.to_tz(slots.parse_iso(appointment["start_iso"]), TZ)
    title = "Mark showed or no-show by hand: %s (%s) at %s" % (first, company, fmt_time_only(start))
    body = (
        "The %s call with %s (%s) has passed and there is no Zoom join data for it, so nothing was assumed.\n\n"
        "Set the appointment status in GHL to showed or noshow. Marking it noshow starts the recovery sequence on the "
        "next tick; marking it showed closes it out.\n\n"
        "This task stops once the Discovery Call calendar uses Zoom and the Zoom webhook is connected."
    ) % (fmt_when(start), first, company)
    contact_id = appointment.get("contact_id")
    if not contact_id:
        return {"action": "create_task", "payload": {"title": title}, "status": "skipped:no_contact_id"}
    res = ghl.create_task(contact_id, title, now.isoformat(), body=body)
    return _action("create_task", {"title": title, "reason": "no_zoom_telemetry"}, res)


def _cancel_recovery(store, appt_id: str, start_iso: str, reason: str) -> int:
    """Cancel through store.mutate, never get-then-set.

    A reply arriving while a tick is inside its touch loop used to be undone by
    the tick's stale write-back: the cancellation vanished and the lead who had
    just answered kept getting the recovery ladder. mutate() does the whole
    read-decide-write under one lock, so the tick's own per-touch writes (also
    mutate) merge instead of clobbering.
    """
    counted = {"n": 0}
    held = []  # type: List[str]
    appts = []  # type: List[Dict[str, Any]]

    def _apply(rec):
        rec = rec or {}
        del held[:], appts[:]  # mutate may call this more than once
        counted["n"] = 0
        for t in rec.get("touches", []):
            if not t.get("sent") and not t.get("skipped"):
                t["skipped"], t["skip_reason"] = True, reason
                counted["n"] += 1
                # times a pending slot email was holding never reached the lead.
                # The offers that did (rec["held_offers"]) stay held: a lead
                # who replied may be picking one of them.
                held.extend(_isos(t.get("slots")))
                t["slots"] = {}
        rec["cancelled"] = reason
        appts.append(rec.get("appointment") or {"id": appt_id})
        return rec

    total = 0
    for key in store.keys("recovery:%s:" % appt_id):
        store.mutate(key, _apply, default={})
        total += counted["n"]
        if held:
            release_recovery_claim(store, appts[-1], list(held))
    return total


def _persist_touch(store, key: str, touch_key: str, patch: Dict[str, Any]) -> None:
    """Fold one touch's outcome into the record under the store lock.

    Writing back a whole record read before the network call loses every other
    change made in between (a cancellation, another worker's touch result).
    """
    def _apply(rec):
        rec = rec or {}
        for t in rec.get("touches", []):
            if t.get("key") == touch_key:
                t.update(patch)
                break
        return rec

    store.mutate(key, _apply, default={})


def cancel_recovery(store, appointment_id: str, reason: str) -> int:
    """Public wrapper for the reply engine: drop every pending recovery touch
    (e.g. reason='replied' when any inbound reply arrives; Lorenzo takes over)."""
    n = _cancel_recovery(store, appointment_id, "", reason=reason)

    def _apply(st):
        st = st or {}
        if st.get("state") == "no_show":
            st["state"], st["done_reason"] = "done", reason
        return st

    store.mutate(state_key(appointment_id), _apply, default={})
    return n


def cancel_recovery_for_rebooking(store, appointment_id: str) -> int:
    """booking.py or the tick calls this when the lead books a new time: every
    pending recovery touch is dropped.

    It refuses to invent a state record. booking.register_booking calls this
    with the id of the call it has just created, which for a new booking has
    no recovery and no state at all - and writing ``state=done`` there marked
    every engine-made call finished before it happened. ``process()`` returns
    immediately on a done state, so no-show detection never ran for a single
    booking the engine made, only for widget ones.
    """
    n = _cancel_recovery(store, appointment_id, "", reason="rebooked")
    st = store.get(state_key(appointment_id)) or {}
    if n == 0 and st.get("state") != "no_show":
        return 0
    st = dict(st)
    st["state"] = "done"
    st["done_reason"] = "rebooked"
    store.set(state_key(appointment_id), st)
    return n


def rebooked_contact_ids(now: datetime, appointments: Optional[List[Dict[str, Any]]]) -> set:
    """Contacts with a call still ahead of them. Their recovery sequence must
    not run: a lead who rebooked after a no-show would otherwise be asked
    "Should I close your file?" with a confirmed call on the books."""
    now = slots.to_tz(slots.ensure_aware(now, TZ), TZ)
    out = set()
    for appt in appointments or []:
        if appt.get("cancelled"):
            continue
        cid = appt.get("contact_id")
        if not cid:
            continue
        try:
            if slots.parse_iso(appt["start_iso"]) > now:
                out.add(str(cid))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def run_recovery(
    now: datetime,
    store,
    ghl,
    appointment_id: Optional[str] = None,
    upcoming_appointments: Optional[List[Dict[str, Any]]] = None,
    slots_fn: Optional[Callable[[datetime], Dict[str, Any]]] = None,
    instantly=None,
) -> Dict[str, Any]:
    """Send due ladder emails; after the LAST email of a ladder goes out,
    apply its stage move and enroll the lead in nurture.

    ``upcoming_appointments`` is the list of appointments the caller just read
    from GHL: any recovery record whose contact has a call in the future is
    cancelled as ``rebooked`` instead of being advanced. Before anything is
    sent for a record, a reply from the lead since the call's start cancels
    the rest (``replied``). At most one email per record goes out per run.
    ``instantly`` is the client the in-thread replies go through.
    """
    now = slots.to_tz(slots.ensure_aware(now, TZ), TZ)
    summary = _new_summary()
    rebooked = rebooked_contact_ids(now, upcoming_appointments) if upcoming_appointments is not None else set()
    prefix = "recovery:%s:" % appointment_id if appointment_id else "recovery:"
    reached_leads = set()  # one email per lead per run, across records too
    for key in store.keys(prefix):
        rec = store.get(key) or {}
        if rec.get("cancelled"):
            continue
        appt = rec.get("appointment", {})
        appt_id = str(appt.get("id"))
        lead = str(appt.get("email") or "").strip().lower() or str(appt.get("contact_id") or "") or appt_id
        if lead in reached_leads:
            continue
        if rebooked and str(appt.get("contact_id") or "") in rebooked:
            n = _cancel_recovery(store, appt_id, str(appt.get("start_iso") or ""), reason="rebooked")
            summary["cancelled"].append({"key": key, "reason": "rebooked", "touches": n})
            continue
        if _appointment_was_held(store, appt):
            n = _cancel_recovery(store, appt_id, str(appt.get("start_iso") or ""), reason="showed")
            summary["cancelled"].append({"key": key, "reason": "showed", "touches": n})
            continue
        due = [raw for raw in rec.get("touches", [])
               if not raw.get("sent") and not raw.get("skipped") and Touch.from_dict(raw).when() <= now]
        if not due:
            continue
        # Reply stop, for every booking (engine or widget): any reply since the
        # call's start (the flag comes after it) ends the ladder; Lorenzo and
        # the reply engine take the conversation from there.
        try:
            since = slots.parse_iso(appt["start_iso"])
        except (KeyError, ValueError, TypeError):
            since = slots.parse_iso(rec.get("flagged_at")) if rec.get("flagged_at") else now
        replied, error = lead_replied_since(store, appt, since)
        if error:
            summary["errors"].append({"key": key, "reason": "reply_check_failed", "error": error})
            continue
        if replied:
            n = cancel_recovery(store, appt_id, "replied")
            summary["cancelled"].append({"key": key, "reason": "replied", "touches": n})
            continue
        pending_after = None  # the stage move runs after the touch loop, never inside it
        for raw in rec.get("touches", []):
            if raw.get("sent") or raw.get("skipped"):
                continue
            touch = Touch.from_dict(raw)
            if touch.when() > now:
                continue
            entry = {"key": touch.key, "channel": touch.channel, "template": touch.template_key, "when": touch.when_iso}
            skip = (_too_late_reason(touch, now) or _ladder_skip_reason(touch, rec, appt)
                    or _superseded_reason(touch.key, rec, appt, now))
            if skip is not None:
                # came due during an outage ("I'm on the call now" a day after
                # the call), nothing true can be said (no niche line, no
                # earlier offer for "those times got taken"), the next email
                # of the ladder is due (or went out) already, or the one
                # before it reached the lead less than SUPERSEDE_MARGIN ago
                _close_touch(store, key, raw, appt, skip)
                entry["reason"] = skip
                summary["skipped"].append(entry)
                after = (touch.meta or {}).get("after")
                if after:
                    mv = _after_skipped_task(after, appt, ghl, now, skip)
                    if mv:
                        summary["stage_moves"].append(mv)
                continue
            wait = _spacing_wait(touch.key, rec, appt, now)
            if wait is not None:
                # the ladder's last email, less than SUPERSEDE_MARGIN after the
                # one before it: never closed for that (its hand-off must run),
                # re-armed at the end of the margin. MAX_LATENESS then counts
                # from the new time.
                raw["rearmed_from"] = raw.get("rearmed_from") or raw.get("when_iso")
                raw["when_iso"] = wait.isoformat()
                _persist_touch(store, key, touch.key, {"when_iso": raw["when_iso"],
                                                       "rearmed_from": raw["rearmed_from"]})
                entry.update(reason=SPACING_WAIT, until=raw["when_iso"])
                summary["deferred"].append(entry)
                continue
            # contact ids are resolved from the record, not from the frozen
            # Touch: an id that arrived on a later tick must revive the ladder.
            touch.contact_id = appt.get("contact_id") or touch.contact_id
            slots_text = ""
            if touch.template_key in SLOT_TEMPLATES:
                info = _slots_for_touch(raw, rec, appt, now, ghl, store, slots_fn)
                raw["slots"] = info
                _persist_touch(store, key, touch.key, {"slots": info})
                slots_text = offer_text(info)
                if not slots_text:
                    # never a slot email without two held times, and never a
                    # booking link instead: pending, retried until MAX_LATENESS
                    out = {"status": "error", "error": "no_slots", "reason": "no_slots"}
                    _record_retry(raw, out, entry, summary, "no_slots")
                    _persist_touch(store, key, touch.key, {k: raw.get(k) for k in ("attempts", "result", "skipped",
                                                                                   "skip_reason")})
                    continue
            rerender_for_dispatch(touch, appt, slots_text)
            raw.update({"subject": touch.subject, "body": touch.body, "template_id": touch.template_id,
                        "template_hash": touch.template_hash})
            missing = unfilled({"subject": touch.subject, "body": touch.body})
            if missing is not None:
                _record_retry(raw, {"status": "error", "error": missing}, entry, summary, missing)
                _persist_touch(store, key, touch.key, {k: raw.get(k) for k in ("attempts", "result", "skipped",
                                                                               "skip_reason")})
                continue
            claim = _touch_claim_key(touch.key)
            if not store.set_if_absent(claim, {"at": now.isoformat(), "template": touch.template_key}):
                # a previous run already dispatched this touch and died before
                # it could record the fact. Never send it twice.
                raw["sent"], raw["sent_at"] = True, now.isoformat()
                raw["result"] = {"status": "skipped", "reason": "already_dispatched"}
                entry["reason"] = "already_dispatched"
                summary["skipped"].append(entry)
                _persist_touch(store, key, touch.key, {"sent": True, "sent_at": now.isoformat(),
                                                       "result": raw["result"]})
                continue
            out = sr.dispatch_touch(touch, ghl, now, store=store, appointment=appt, kind="no_show",
                                    slots_text=slots_text or None, instantly=instantly)
            _record_recovery_result(raw, out, entry, summary, now)
            if out.get("status") == HELD and out.get("hold") != THREAD_HOLD:
                note_template_hold(store, raw, out, now)
            elif raw.get("template_hold"):
                raw["template_hold"] = None
            if _stays_pending(out):
                store.delete(claim)  # retryable (or held): the next tick tries again
            reached = out.get("status") in ("sent", "would_do", MAYBE_SENT)
            if touch.template_key in SLOT_TEMPLATES:
                if reached:
                    _offer_reached_lead(store, key, rec, appt, raw.get("slots") or {}, touch.template_key)
                elif raw.get("skipped"):
                    release_recovery_claim(store, appt, _isos(raw.get("slots")))
                    raw["slots"] = {}
            # persist immediately: an exception later must not re-send this touch
            _persist_touch(store, key, touch.key, {k: raw.get(k) for k in
                                                   ("sent", "sent_at", "result", "skipped", "skip_reason", "attempts",
                                                    "subject", "body", "template_id", "template_hash",
                                                    "template_hold", "thread_hold", "maybe_sent", "maybe_sent_at",
                                                    "slots")})
            after = (touch.meta or {}).get("after")
            if after and out.get("status") in ("sent", "would_do"):
                pending_after = (after, bool((touch.meta or {}).get("nurture")))
            elif after and raw.get("skipped"):
                # nothing (or maybe nothing) reached the lead, so do not move
                # the pipeline; hand it to Lorenzo instead.
                mv = _after_skipped_task(after, appt, ghl, now, raw.get("skip_reason") or out.get("reason"))
                if mv:
                    summary["stage_moves"].append(mv)
            if reached:
                reached_leads.add(lead)
                break  # one email per lead per run, even after an outage
        if pending_after is not None:
            mv = _apply_after(pending_after[0], appt, ghl, store, now)
            if mv:
                summary["stage_moves"].append(mv)
            if pending_after[1]:
                summary["nurture"].append(enroll_nurture(store, key, appt, now))
    return summary


def enroll_nurture(store, record_key: str, appt: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    """The ladder ended with no reply and no rebooking: 90-day nurture
    (nurture.enroll(lead_email, "no_show_no_rebook", now, note=<appointment
    id>)). Once per recovery record (``nurture`` on the record); enroll itself
    is idempotent too. Never raises."""
    from services.reply_engine import nurture

    appt_id = str(appt.get("id"))
    rec = store.get(record_key) or {}
    if (rec.get("nurture") or {}).get("status") == "enrolled":
        return {"action": "nurture_enroll", "payload": {"appointment_id": appt_id}, "status": "skipped:already_enrolled"}
    email, campaign_id = _lead_identity(store, appt, appt_id)
    payload = {"lead_email": email, "reason": NURTURE_REASON, "campaign_id": campaign_id, "note": appt_id}
    if not email:
        return {"action": "nurture_enroll", "payload": payload, "status": "skipped:no_lead_email"}
    try:
        res = nurture.enroll(email, NURTURE_REASON, slots.ensure_aware(now, TZ), store=store,
                             campaign_id=campaign_id, note=appt_id)
    except Exception as exc:  # noqa: BLE001 - the ladder is over either way; surface it
        logger.warning("nurture.enroll failed for appointment %s: %s", appt_id, exc)
        return {"action": "nurture_enroll", "payload": payload, "status": "error", "error": str(exc)[:200]}

    def _apply(cur):
        cur = cur or {}
        cur["nurture"] = {"status": "enrolled", "at": slots.to_tz(now, TZ).isoformat(),
                          "created": bool(res.get("created"))}
        return cur

    store.mutate(record_key, _apply, default={})
    return {"action": "nurture_enroll", "payload": payload, "status": "done", "created": bool(res.get("created"))}


def _touch_claim_key(touch_key: str) -> str:
    return "touch_sent:%s" % touch_key


def _stays_pending(out: Dict[str, Any]) -> bool:
    """True when this dispatch outcome leaves the touch to be retried (a CT3
    template hold, a thread hold and a send-window deferral included). A
    maybe-sent email never stays pending."""
    if out.get("status") in ("error", HELD):
        return True
    return out.get("status") == "skipped" and out.get("reason") in RETRYABLE_SKIP_REASONS


def _appointment_was_held(store, appt: Dict[str, Any]) -> bool:
    """The no-show verdict was overturned (late show / hand-set showed).

    Without this the ladder keeps running off its own record even after
    process() has flipped the appointment back to showed.
    """
    st = store.get(state_key(str(appt.get("id")))) or {}
    return st.get("state") in ("showed", "late_show")


# How late a touch may be before it is dropped instead of sent. The tick can
# pause (a deploy, a held lock, a retryable error keeping a touch pending), and
# without this the backlog fires at once: "I'm on the call now" a day after
# the call ended. N1 is bound to S+10 (armed at S+5); N3 / N8 speak about
# "today"; the day touches have the rest of their day and the next.
MAX_LATENESS = {
    N1: NO_SHOW_GRACE - STILL_ON_AFTER,
    N3: timedelta(hours=6),
    N4: timedelta(days=1),
    N5: timedelta(days=1),
    N9: timedelta(days=1),
    N6: timedelta(days=1),
    N7: timedelta(days=1),
    N8: timedelta(hours=6),
}


# No two emails of one ladder reach the lead less than this apart
# (_superseded_reason, _spacing_wait):
#
# * a late email never goes out once the NEXT email of the same ladder is due,
#   due within this margin, or already went out: it is closed as
#   ``superseded`` (show_rate closes a reminder overtaken by a later one the
#   same way) and the next email carries on. Since 2026-09-24 the day emails
#   are one business day apart while MAX_LATENESS keeps a day, so without this
#   a held N5 released at 08:50 went out ten minutes before N9;
# * no email goes out less than this after an EARLIER email of the same ladder
#   reached the lead (sent or maybe sent): it is closed as ``superseded`` too.
#   The case is a no-show flagged late (Lorenzo marks it by hand in GHL while
#   the calendar is on Google Meet): N3 goes at the flag, and N4, due minutes
#   later at 10:00 lead time, would call N3's times "taken". N4 closes and N5
#   goes on its own day. The ladder's LAST email is never closed this way (its
#   stage move and nurture hand-off must run): it waits for the end of the
#   margin instead. N1 is not part of the ladder record: N3 at S+25 after N1
#   at S+5 is the approved timing.
#
# The on-time ladder never meets the margin. Calls start 12:00-17:45 CT (the
# offer window, settings.SLOT_WINDOW with 15-minute slots), so N3 at S+25 goes
# by 18:10 CT. Every day email is armed at 10:00 lead time on a business day
# after the call's own lead-local day, which is at least 9 h after S (10 h
# without a clock change), so after 21:00 CT, and next_send_window_open only
# moves it later, into 07:00-19:00 CT on a weekday: N4 (and the second miss's
# N6) goes at 07:00 CT on the next business day at the earliest, at least
# 12 h 50 min after N3. After N4 the day emails are a business day apart; where
# the lead's send window barely overlaps Central (Asia, Australia) touch_time
# can move two of them to the same afternoon, and then the earlier one closes
# by the first rule, as a late email does.
SUPERSEDE_MARGIN = timedelta(hours=8)
SUPERSEDED = "superseded"
# The summary reason (under "deferred", never a skip or a Job_Log status) when
# the ladder's last email is re-armed at the end of the margin.
SPACING_WAIT = "spacing_wait"


def _too_late_reason(touch: Touch, now: datetime) -> Optional[str]:
    limit = MAX_LATENESS.get(touch.template_key)
    if limit is None:
        return None
    return "too_late" if (now - touch.when()) > limit else None


def _superseded_reason(touch_key: str, rec: Dict[str, Any], appt: Dict[str, Any], now: datetime) -> Optional[str]:
    """``superseded`` when this email must not go, now or later; else None:

    - a LATER email of this ladder already reached the lead;
    - an EARLIER email of this ladder reached the lead (sent or maybe sent)
      less than SUPERSEDE_MARGIN ago (_last_reached_before);
    - the next later email that can still go is due by
      ``now + SUPERSEDE_MARGIN``. A later touch that will be closed anyway
      (too late, or a _ladder_skip_reason such as N5's no_niche_point or a
      "taken" email's no_prior_offer) does not count as the next email.

    The last touch of a ladder is never superseded, so its stage move and
    nurture hand-off always run; when an earlier email reached the lead less
    than the margin before it, _spacing_wait re-arms it instead."""
    all_touches = rec.get("touches") or []
    keys = [t.get("key") for t in all_touches]
    if touch_key not in keys:
        return None
    later = all_touches[keys.index(touch_key) + 1:]
    if not later:
        return None
    if any(t.get("sent") or t.get("maybe_sent") for t in later):
        return SUPERSEDED
    reached = _last_reached_before(rec, touch_key)
    if reached is not None and now - reached < SUPERSEDE_MARGIN:
        return SUPERSEDED
    for raw in later:
        if raw.get("skipped"):
            continue
        nxt = Touch.from_dict(raw)
        if _too_late_reason(nxt, now) or _ladder_skip_reason(nxt, rec, appt):
            continue
        return SUPERSEDED if nxt.when() - now <= SUPERSEDE_MARGIN else None
    return None


def _ladder_skip_reason(touch: Touch, rec: Dict[str, Any], appt: Dict[str, Any]) -> Optional[str]:
    """Why this touch can never be sent truthfully, or None.

    - a key this ladder no longer has (an SMS, call task or day-1 other-channel
      touch left in a record from before the 2026-09-23 rebuild):
      ``removed_touch``;
    - N5 with no niche line for the lead's campaign: ``no_niche_point``;
    - N4 / N5 / N6 say the earlier times "got taken": only after an earlier
      slot email of this ladder reached the lead, else ``no_prior_offer``.
    """
    if touch.channel != "email" or touch.template_key not in (N3, N4, N5, N9, N6, N7, N8):
        return "removed_touch"
    if touch.template_key == N5 and niche_point(appt) is None:
        return "no_niche_point"
    if touch.template_key in TAKEN_TEMPLATES and not _earlier_offer_reached(rec, touch.key):
        return "no_prior_offer"
    return None


def _earlier_offer_reached(rec: Dict[str, Any], touch_key: str) -> bool:
    for raw in rec.get("touches", []):
        if raw.get("key") == touch_key:
            return False
        if raw.get("template_key") in SLOT_TEMPLATES and (raw.get("sent") or raw.get("maybe_sent")):
            return True
    return False


def _reached_at(raw: Dict[str, Any]) -> Optional[datetime]:
    """When this touch reached the lead (``sent_at``), or may have
    (``maybe_sent_at``); None when it did not. A record without the stamp
    falls back to the touch's armed time. A touch a crashed run dispatched
    (``already_dispatched``) carries the time the next run found it, later
    than it went: the safe side for the spacing."""
    if raw.get("sent"):
        fields = ("sent_at", "when_iso")
    elif raw.get("maybe_sent"):
        fields = ("maybe_sent_at", "when_iso")
    else:
        return None
    for field in fields:
        value = raw.get(field)
        if not value:
            continue
        try:
            return slots.to_tz(slots.ensure_aware(slots.parse_iso(str(value)), TZ), TZ)
        except (ValueError, TypeError):
            continue
    return None


def _last_reached_before(rec: Dict[str, Any], touch_key: str) -> Optional[datetime]:
    """The latest moment an EARLIER email of this ladder (before
    ``touch_key``) reached the lead, or None."""
    latest = None  # type: Optional[datetime]
    for raw in rec.get("touches") or []:
        if raw.get("key") == touch_key:
            break
        at = _reached_at(raw)
        if at is not None and (latest is None or at > latest):
            latest = at
    return latest


def _spacing_wait(touch_key: str, rec: Dict[str, Any], appt: Dict[str, Any], now: datetime) -> Optional[datetime]:
    """For the LAST touch of a ladder only: when an earlier email of the
    ladder reached the lead less than SUPERSEDE_MARGIN ago, the moment it may
    go instead (the end of the margin, moved into the send window for CT and
    the lead). None otherwise. Any other touch in that position is closed
    (_superseded_reason); the last one carries the stage move and the nurture
    hand-off, so it waits. Example: a second miss flagged by hand on the
    morning N6 is due gets N3 at once and N6 eight hours later."""
    touches = rec.get("touches") or []
    if not touches or touches[-1].get("key") != touch_key:
        return None
    reached = _last_reached_before(rec, touch_key)
    if reached is None or now - reached >= SUPERSEDE_MARGIN:
        return None
    return next_send_window_open(reached + SUPERSEDE_MARGIN, lead_tz=lead_tz_of(appt), weekdays_only=True)


def _isos(info: Any) -> List[str]:
    return [i for i in ((info or {}).get("slots") or []) if isinstance(i, str) and i] if isinstance(info, dict) else []


def _slot_still_offerable(iso: str, now: datetime) -> bool:
    try:
        return bool(slots.is_offerable(slots.parse_iso(iso), now))
    except (ValueError, TypeError):
        return False


def _slots_for_touch(raw: Dict[str, Any], rec: Dict[str, Any], appt: Dict[str, Any], now: datetime,
                     ghl, store, slots_fn=None) -> Dict[str, Any]:
    """The two times this slot email offers: its own earlier claim when both
    are still offerable (a retried touch), else two fresh ones, never any the
    lead still holds from an earlier email (``rec["held_offers"]``).
    ``slots: []`` when none can be held (the touch then waits)."""
    held = raw.get("slots") or {}
    isos = _isos(held)
    live_ok = held.get("source") == "ghl" or not settings.is_live()
    if len(isos) >= 2 and live_ok and all(_slot_still_offerable(i, now) for i in isos):
        return held
    if isos:
        release_recovery_claim(store, appt, isos)
    # never any time the lead holds from an earlier email (after N9 that is
    # two pairs, N9's and the one before it)
    previous = _held_offer_isos(rec)
    previous += [i for i in _isos(rec.get("slots")) if i not in previous]
    try:
        # picked AND held in one step (claim_slots): never double-offered
        info = claim_recovery_slots(now, ghl, store, appt, slots_fn=slots_fn, exclude=previous)
    except Exception as exc:  # noqa: BLE001 - no times is a wait, never a dead line
        logger.warning("claiming recovery slots failed: %s", exc)
        info = {"slots": [], "text": "", "source": "unavailable"}
    claimed = _isos(info)
    if claimed and info.get("source") != "ghl" and settings.is_live():
        # never send unverified times live: they are not held for this lead either
        release_recovery_claim(store, appt, claimed)
        info = dict(info, slots=[], text="")
    return info


def _held_offer_isos(rec: Dict[str, Any]) -> List[str]:
    """Every time this ladder's emails have put in front of the lead and no
    later email has called taken: ``rec["held_offers"]``, or the last offer
    (``rec["slots"]``) on a record written before that field existed."""
    held = rec.get("held_offers")
    if isinstance(held, list):
        return [i for i in held if isinstance(i, str) and i]
    return _isos(rec.get("slots"))


def _offer_reached_lead(store, record_key: str, rec: Dict[str, Any], appt: Dict[str, Any],
                        info: Dict[str, Any], template_key: str) -> None:
    """A slot email went out: its two times are now the lead's latest offer
    (``rec["slots"]``) and join the times held for the lead
    (``rec["held_offers"]``).

    Only an email that says the earlier times "got taken" (TAKEN_TEMPLATES:
    N4 / N5 / N6) gives the earlier ones back. N3 and N9 say nothing about
    them, so after N9 the previous offer (N5's, or N4's when N5 was skipped)
    stays claimed in both registries next to N9's pair, until N6 reaches the
    lead or the times pass (both registries prune past times on read):
    handing it to another lead while this one may still pick it would be a
    double offer."""
    new = _isos(info)
    taken = template_key in TAKEN_TEMPLATES
    box = {"previous": []}  # type: Dict[str, List[str]]

    def _apply(cur):
        cur = cur or {}
        previous = _held_offer_isos(cur)
        box["previous"] = previous
        cur["slots"] = info
        cur["held_offers"] = list(new) if taken else previous + [i for i in new if i not in previous]
        return cur

    store.mutate(record_key, _apply, default={})
    rec["slots"] = info
    rec["held_offers"] = list(new) if taken else box["previous"] + [i for i in new if i not in box["previous"]]
    if taken:
        stale = [i for i in box["previous"] if i not in new]
        if stale:
            release_recovery_claim(store, appt, stale)


def _close_touch(store, record_key: str, raw: Dict[str, Any], appt: Dict[str, Any], reason: str) -> None:
    """Skip a touch for good and give back any times it was holding."""
    held = _isos(raw.get("slots"))
    if held:
        release_recovery_claim(store, appt, held)
    raw["skipped"], raw["skip_reason"], raw["slots"] = True, reason, {}
    _persist_touch(store, record_key, raw["key"], {"skipped": True, "skip_reason": reason, "slots": {}})


MAYBE_SENT = getattr(sr, "MAYBE_SENT", "maybe_sent")
THREAD_HOLD = getattr(sr, "THREAD_HOLD", "thread")


def _record_recovery_result(raw: Dict[str, Any], out: Dict[str, Any], entry: Dict[str, Any],
                            summary: Dict[str, List[Any]], now: datetime) -> None:
    """Fold one dispatch result into the touch record and the summary, the
    same way show_rate._record_result does for the reminders:

    - sent / would_do: done;
    - held by the template gate: pending, no attempt (``held_template``);
    - held by the thread lookup (thread_reply.NEEDS_ATTENTION_REASONS, a
      refused thread subject): pending, no attempt, ``needs_attention``;
    - maybe_sent (the write went out and failed or came back empty): closed
      with the error and NEVER retried; ``maybe_sent`` + ``errors``, and a
      Job_Log row for Lorenzo to check the thread by hand;
    - outside the send window: pending, no attempt (``deferred``);
    - anything else retryable: pending, one attempt (up to MAX_TOUCH_ATTEMPTS);
    - any other skip (opt-out, sender is GHL): closed.
    """
    if out.get("transport"):
        entry["transport"] = out["transport"]
    status = out.get("status")
    if status in ("sent", "would_do"):
        raw["sent"], raw["sent_at"], raw["result"] = True, now.isoformat(), out
        raw["thread_hold"] = None
        entry["shadow"] = status == "would_do"
        summary[status].append(entry)
        return
    if status == HELD and out.get("hold") == THREAD_HOLD:
        entry["reason"] = out.get("reason")
        summary["needs_attention"].append(entry)
        _note_thread_hold(raw, out, entry, now)
        return
    if status == HELD:
        record_held(entry, out, summary)  # pending, no attempt counted
        return
    if status == MAYBE_SENT:
        raw["skipped"], raw["skip_reason"], raw["maybe_sent"], raw["result"] = True, MAYBE_SENT, True, out
        raw["maybe_sent_at"] = now.isoformat()  # the ladder's spacing counts from it (_reached_at)
        entry["reason"], entry["error"] = MAYBE_SENT, out.get("error")
        summary["maybe_sent"].append(entry)
        summary["errors"].append(entry)
        logger.error("%s may have been delivered (%s); closed, never retried: check the lead's thread or GHL "
                     "conversation by hand", entry.get("key"), out.get("reason"))
        try:
            from shared import job_log

            job_log.log_run("reply_engine.no_show", "no_show_maybe_sent",
                            {"touch": entry.get("key"), "template": entry.get("template"),
                             "transport": out.get("transport"), "reason": out.get("reason")})
        except Exception as exc:  # noqa: BLE001 - the summary still carries it
            logger.warning("could not log the maybe-sent touch %s: %s", entry.get("key"), exc)
        return
    if status == "error" and out.get("deferred"):
        raw["result"] = out
        entry["reason"] = out.get("reason")
        summary["deferred"].append(entry)
        return
    if status == "skipped":
        reason = out.get("reason")
        if reason in RETRYABLE_SKIP_REASONS:
            _record_retry(raw, out, entry, summary, reason)
            return
        raw["skipped"], raw["skip_reason"] = True, reason
        entry["reason"] = reason
        summary["skipped"].append(entry)
        return
    _record_retry(raw, out, entry, summary, out.get("error") or out.get("reason"))


def _note_thread_hold(raw: Dict[str, Any], out: Dict[str, Any], entry: Dict[str, Any], now: datetime) -> None:
    """Remember a thread hold on the touch; the first run that meets a new
    reason writes one Job_Log row, later runs only count it."""
    prev = raw.get("thread_hold") or {}
    raw["thread_hold"] = {"reason": out.get("reason"), "transport": out.get("transport"),
                          "lead_key": out.get("lead_key"), "since": prev.get("since") or now.isoformat()}
    if prev.get("reason") == out.get("reason"):
        return
    logger.warning("holding %s: the lead's thread needs a look (%s)", entry.get("key"), out.get("reason"))
    try:
        from shared import job_log

        job_log.log_run("reply_engine.no_show", "no_show_needs_attention",
                        {"touch": entry.get("key"), "template": entry.get("template"), "reason": out.get("reason"),
                         "lead_key": out.get("lead_key")})
    except Exception as exc:  # noqa: BLE001 - the summary still carries it
        logger.warning("could not log the thread hold on %s: %s", entry.get("key"), exc)


def _record_retry(raw: Dict[str, Any], out: Dict[str, Any], entry: Dict[str, Any],
                  summary: Dict[str, List[Any]], error: Any) -> None:
    """Leave the touch pending for the next tick, up to MAX_TOUCH_ATTEMPTS."""
    attempts = int(raw.get("attempts") or 0) + 1
    raw["attempts"], raw["result"] = attempts, out
    entry["error"] = error
    entry["attempts"] = attempts
    if attempts >= MAX_TOUCH_ATTEMPTS:
        raw["skipped"], raw["skip_reason"] = True, "retry_exhausted"
        entry["reason"] = "retry_exhausted"
    summary["errors"].append(entry)


def _after_skipped_task(after: str, appt: Dict[str, Any], ghl, now: datetime, reason: Optional[str]) -> Optional[Dict[str, Any]]:
    """The final recovery touch was skipped, so nothing reached the lead. Ask
    Lorenzo to decide instead of silently moving the opportunity."""
    contact_id = appt.get("contact_id")
    what = after.split(":", 1)[1] if ":" in after else after
    title = "Recovery ended with nothing sent: decide on %s" % (appt.get("company") or appt.get("id"))
    body = (
        "The last recovery touch was skipped (%s), so no message reached this lead. "
        "The pipeline was left alone. Move the opportunity to %s by hand, or restart the sequence."
    ) % (reason or "skipped", what.replace("_", " "))
    if not contact_id:
        logger.warning("recovery for %s ended skipped (%s) with no contact id", appt.get("id"), reason)
        return {"action": "create_task", "payload": {"stage": what, "reason": reason}, "status": "skipped:no_contact_id"}
    res = ghl.create_task(contact_id, title, slots.to_tz(slots.ensure_aware(now, TZ), TZ).isoformat(), body=body)
    return _action("create_task", {"stage": what, "reason": reason, "not_applied": True}, res)


# Stages the recovery ladder must never overwrite: Lorenzo (or another part of
# the engine) has already moved this deal forward or closed it by hand.
PROTECTED_STAGES = ("proposal_sent", "won", "lost")
# Written on the third-no-show Lost move so pipeline_sync.desired_interest()
# mirrors it to Instantly as no_show (-4) and not not_interested (-1); its
# LOST_NO_SHOW_MARKERS look for exactly this wording.
LOST_REASON_NO_SHOW = "No show x3 (SOP-005)"


def _current_stage_key(ghl, appt: Dict[str, Any], opp_id: str) -> Optional[str]:
    """The stage the opportunity is in right now, or None when we cannot tell.

    A recovery ladder that started before Lorenzo answered must not silently
    rewrite a deal he has since moved to Proposal Sent or Won.
    """
    opp = None
    try:
        getter = getattr(ghl, "get_opportunity", None)
        if callable(getter):
            opp = getter(opp_id)
        elif appt.get("contact_id"):
            found = ghl.search_opportunities(contact_id=appt["contact_id"])
            rows = (found or {}).get("opportunities", found) if isinstance(found, dict) else found
            for row in rows or []:
                if isinstance(row, dict) and str(row.get("id")) == str(opp_id):
                    opp = row
                    break
    except Exception as exc:  # noqa: BLE001 - a read failure must not block the move
        logger.warning("could not read opportunity %s: %s", opp_id, exc)
        return None
    if isinstance(opp, dict) and isinstance(opp.get("opportunity"), dict):
        opp = opp["opportunity"]
    if not isinstance(opp, dict):
        return None
    stage_id = opp.get("pipelineStageId") or opp.get("pipeline_stage_id")
    for key, value in (settings.GHL_STAGES or {}).items():
        if value and stage_id and str(value) == str(stage_id):
            return key
    if str(opp.get("status") or "").lower() in ("won", "lost"):
        return str(opp["status"]).lower()
    return None


def _move_opportunity(ghl, opp_id: str, stage_id: str, status: Optional[str], lost_reason: Optional[str]):
    """update_opportunity_stage with a lost reason when the client supports one.

    Feature-detected rather than assumed: shared/ghl.py owns that signature and
    is another component's file (see the cross-cutting request)."""
    if lost_reason:
        try:
            return ghl.update_opportunity_stage(opp_id, stage_id, status=status, lost_reason=lost_reason)
        except TypeError:
            logger.warning("shared.ghl.update_opportunity_stage takes no lost_reason: the Lost move for %s "
                           "will mirror to Instantly as not_interested (-1), not no_show (-4)", opp_id)
    return ghl.update_opportunity_stage(opp_id, stage_id, status=status)


def _apply_after(after: str, appt: Dict[str, Any], ghl, store, now: datetime) -> Optional[Dict[str, Any]]:
    appt_id = str(appt.get("id"))
    now_iso = slots.to_tz(slots.ensure_aware(now, TZ), TZ).isoformat()
    if after.startswith("stage:"):
        stage_key = after.split(":", 1)[1]
        stage_id = settings.GHL_STAGES.get(stage_key)
        opp_id = appt.get("opportunity_id")
        if opp_id and stage_id:
            current = _current_stage_key(ghl, appt, opp_id)
            if current in PROTECTED_STAGES and current != stage_key:
                logger.info("recovery for %s leaves the opportunity in %s", appt_id, current)
                st = store.get(state_key(appt_id)) or {}
                st["state"], st["done_reason"] = "done", "stage_already_%s" % current
                store.set(state_key(appt_id), st)
                return {"action": "update_opportunity_stage", "status": "skipped:stage_already_%s" % current,
                        "payload": {"stage": stage_key, "opportunity_id": opp_id, "current_stage": current}}
            status = "lost" if stage_key == "lost" else None
            res = _move_opportunity(ghl, opp_id, stage_id, status,
                                    LOST_REASON_NO_SHOW if stage_key == "lost" else None)
            st = store.get(state_key(appt_id)) or {}
            st["state"], st["done_reason"] = "done", after
            store.set(state_key(appt_id), st)
            return _action("update_opportunity_stage", {"stage": stage_key, "opportunity_id": opp_id}, res)
        if appt.get("contact_id"):
            res = ghl.create_task(appt["contact_id"], "Move %s to %s (no opportunity id on file)" % (appt.get("company") or appt_id, stage_key),
                                  now_iso, body="Recovery sequence finished; move the Sales opportunity by hand.")
            return _action("create_task", {"stage": stage_key}, res)
        return None
    if after.startswith("note:") and appt.get("contact_id"):
        res = ghl.create_note(appt["contact_id"], "Second no-show; recovery limited to two touches per SOP-005. Watch for a pattern.")
        return _action("create_note", {"note": after}, res)
    return None
