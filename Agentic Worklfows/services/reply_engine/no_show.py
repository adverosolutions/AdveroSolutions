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
  pending and asks Lorenzo to mark it by hand instead.

An evidence channel means: at least one join was recorded for this meeting
(host, bot or lead), or Zoom told us the meeting started or ended, or a
Fireflies transcript length was supplied, or the appointment already carries a
GHL ``appointmentStatus`` of showed/noshow (which always wins).

``process`` is the state machine the tick calls for every appointment past
its start. On the first 'no_show' it marks the GHL appointment ``noshow``
(guarded write), moves nothing in the pipeline, stores ``no_show_count`` per
contact and schedules the recovery sequence. A non-host join arriving after
the flag produces a 'late_show' event: recovery is cancelled and the
appointment is set back to ``showed`` (guarded).

Recovery sequence (first no-show, full):
  +5 m  SMS + email  "Still on? I'll stay on 10 more minutes" + link
  +10 m task         call + 30-second voicemail script
  +1 h  email        reschedule link + two fresh slots (shared.slots)
  +1 d  SMS (task fallback when A2P is not registered)  two slots
  +3 d  email        value add + re-ask
  +7 d  email        yes / no
  +14 d email        breakup, then stage -> Follow Up Later
Second no-show: +5 m and +1 h only, note the pattern. Third: +5 m only,
then stage -> Lost.

All copy: no em dashes, signed "Lorenzo", nothing about automation.
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from shared import settings, slots
from shared.settings import BOOKING_URL, TZ

from services.reply_engine.show_rate import (
    HELD,
    SMS_MAX_LEN,
    Touch,
    a2p_registered,
    call_link_of,
    company_of,
    dispatch_touch,
    first_name_of,
    fmt_time_only,
    fmt_when,
    lead_tz_of,
    next_send_window_open,
    niche_of,
    note_template_hold,
    offer_of,
    record_held,
    stamp_touch,
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

# (template_key, channel, offset from the no-show flag time)
FULL_SEQUENCE = (
    ("ns_still_on_sms", "sms", timedelta(minutes=5)),
    ("ns_still_on_email", "email", timedelta(minutes=5)),
    ("ns_call_task", "task", timedelta(minutes=10)),
    ("ns_reschedule_email", "email", timedelta(hours=1)),
    ("ns_d1_other_channel", "sms", timedelta(days=1)),
    ("ns_d3_value_email", "email", timedelta(days=3)),
    ("ns_d7_yes_no_email", "email", timedelta(days=7)),
    ("ns_d14_breakup_email", "email", timedelta(days=14)),
)
SECOND_SEQUENCE_KEYS = ("ns_still_on_sms", "ns_still_on_email", "ns_reschedule_email")
THIRD_SEQUENCE_KEYS = ("ns_still_on_sms", "ns_still_on_email")

MECHANISM = {
    ("cleaning", "reactivation"): "email and text sequences to every account that cancelled or went quiet, timed to when they re-bid, with the ready ones landing on your calendar",
    ("cleaning", "outbound"): "watching new leases, expansions and PM changes in your area and putting walkthroughs on your calendar under your name",
    ("bookkeeping", "reactivation"): "sequences to your lost inquiries and former clients timed to tax season and year-end, with the ready ones landing on your calendar",
    ("bookkeeping", "outbound"): "watching new formations and bookkeeper job posts and putting discovery calls on your calendar under your name",
    ("recruiting", "reactivation"): "sequences to your dormant and near-miss client accounts, with the hiring managers who bite landing on your calendar",
    ("recruiting", "outbound"): "watching open roles in your specialty and putting intro calls with hiring managers on your calendar under your agency's name",
    # no niche on file: the offer still decides (an outbound prospect used to
    # get the reactivation line below)
    ("generic", "outbound"): "watching for the events that put a buyer in the market and putting those calls on your calendar under your name",
}
GENERIC_MECHANISM = "sequences to every account that went quiet, with the ready ones landing on your calendar"
PROOF = {
    "reactivation": "I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.",
    "outbound": "I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.",
}


# -------------------------------------------------------------- detection
def _email_domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].strip().strip(".") if "@" in email else ""


def is_bot(join: Dict[str, Any]) -> bool:
    """True only for a known notetaker identity.

    A bare substring match over the name and the whole email address called
    "Fred Wilson" a Fireflies bot and "manuel@gongoraservices.com" a Gong bot,
    and a discarded lead join is how someone who attended ends up in the
    14-day recovery ladder. So: whole tokens in the display name, a known
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
def render(template_key: str, appointment: Dict[str, Any], start: datetime, slots_text: str, count: int) -> Dict[str, Any]:
    first = first_name_of(appointment)
    company = company_of(appointment)
    niche = niche_of(appointment)
    offer = offer_of(appointment)
    when_ct = fmt_when(start, lead_tz_of(appointment))
    time_ct = fmt_time_only(start)
    # The call's join link (Zoom, or Google Meet for widget bookings). With no
    # link on file the sentence says where it is instead (the no_call_link
    # catalogue variant), never a phrase in the link's place.
    link = call_link_of(appointment)
    booking = appointment.get("reschedule_link") or appointment.get("booking_url") or BOOKING_URL or ""
    mechanism = MECHANISM.get((niche, offer), GENERIC_MECHANISM)
    # "Or <link>" only follows the two offered times; with no times the link
    # line stands on its own.
    if slots_text:
        times_line = "Two times that work on my side: %s. " % slots_text
        grab_line = "Or grab any time here: %s" % booking
    else:
        times_line = ""
        grab_line = "Grab any time that suits you here: %s" % booking

    if template_key == "ns_still_on_sms":
        on_now = ("I am on the call now: %s." % link) if link else "I am on the call now. The link is on your calendar invite."
        body = "Hey %s, Lorenzo here. %s I will stay on for 10 more minutes. If today fell apart, grab another time: %s" % (first, on_now, booking)
        return {"subject": None, "body": body[:SMS_MAX_LEN]}
    if template_key == "ns_still_on_email":
        on_now = ("I am on the call now: %s" % link) if link else "I am on the call now. The link is on your calendar invite."
        body = (
            "Hey %s,\n\nStill on? %s\n\n"
            "I will stay on for 10 more minutes in case you are running behind. If today fell apart, no worries, grab another time here: %s\n\nLorenzo"
        ) % (first, on_now, booking)
        return {"subject": "Still on?", "body": body}
    if template_key == "ns_call_task":
        phone = appointment.get("phone") or "no phone on file"
        body = (
            "Call %s (%s) now. Phone: %s. If no answer, leave this 30-second voicemail:\n\n"
            "\"Hey %s, Lorenzo Villarreal. We had a call on the books at %s today. I stayed on the line for a bit but did not see you join, and I know things come up. "
            "I am sending you a link to grab a new time, or just text me back at this number and we will sort it out. Talk soon.\"\n\n"
            "Then send the text: \"Hey %s, Lorenzo here, just left you a voicemail. Grab a new time whenever works: %s\""
        ) % (first, company, phone, first, time_ct, first, booking)
        return {"subject": "No-show at %s: call %s (%s) + voicemail" % (time_ct, first, company), "body": body}
    if template_key == "ns_reschedule_email":
        # second no-show: offer a shorter call or another day. Never "the
        # numbers in writing": the sale closes on one call.
        pattern = "" if count < 2 else ("I know this is the second time the timing did not work out, so if a shorter "
                                        "call or a different day works better, just tell me. ")
        body = (
            "Hey %s,\n\n"
            "I was on the line at %s but did not see you join. No worries, things come up.\n\n"
            "%s%s%s\n\n"
            "If something changed and this is no longer a fit, just say so and I will close it out.\n\nLorenzo"
        ) % (first, time_ct, pattern, times_line, grab_line)
        return {"subject": "Missed you on our call", "body": body}
    if template_key == "ns_d1_other_channel":
        body = "Hey %s, Lorenzo again. Still happy to walk through the plan for %s. %s%s" % (
            first, company, times_line, grab_line)
        return {"subject": None, "body": body[:SMS_MAX_LEN]}
    if template_key == "ns_d1_other_channel_task":
        body = (
            "Texting is not enabled yet, so reach %s (%s) on a second channel by hand: LinkedIn note or a text from your phone.\n"
            "Phone: %s\nSuggested text: \"Hey %s, Lorenzo again. Still happy to walk through the plan for %s. %s%s\""
        ) % (first, company, appointment.get("phone") or "no phone on file", first, company, times_line, grab_line)
        return {"subject": "Day 1 after no-show: LinkedIn or text %s (%s)" % (first, company), "body": body}
    if template_key == "ns_d3_value_email":
        body = (
            "Hey %s,\n\n"
            "Quick thought while this is still on your desk. %s\n\n"
            "For %s the first step is the same: %s.\n\n"
            "%s%s\n\nLorenzo"
        ) % (first, PROOF.get(offer, PROOF["reactivation"]), company, mechanism, times_line, grab_line)
        return {"subject": "One thing worth knowing before you decide", "body": body}
    if template_key == "ns_d7_yes_no_email":
        body = (
            "Hey %s,\n\n"
            "I know you were interested enough to book, so I wanted to check in directly before I close things out.\n\n"
            "Still want to talk through the plan for %s, or has the timing changed? Either answer is fine. It just helps me update my notes.\n\n"
            "If yes: %s\n\nLorenzo"
        ) % (first, company, booking)
        return {"subject": "Should I close your file?", "body": body}
    if template_key == "ns_d14_breakup_email":
        body = (
            "Hey %s,\n\n"
            "Have not heard back, so I am going to assume the timing is not right and close out your file for now.\n\n"
            "If things change down the road, this link will still work: %s\n\n"
            "Best of luck with everything.\n\nLorenzo"
        ) % (first, booking)
        return {"subject": "Closing your file", "body": body}
    raise KeyError("unknown template %s" % template_key)


# ------------------------------------------------------------ scheduling
def sequence_for_count(count: int):
    if count <= 1:
        return list(FULL_SEQUENCE)
    if count == 2:
        return [s for s in FULL_SEQUENCE if s[0] in SECOND_SEQUENCE_KEYS]
    return [s for s in FULL_SEQUENCE if s[0] in THIRD_SEQUENCE_KEYS]


def synthetic_free_slots(now: datetime, days: int = 7) -> List[datetime]:
    """Open-hours grid (12:00-18:00 CT, 15-min) used only when GHL cannot
    answer. Marked synthetic; live sends fall back to link-only copy."""
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


def _approval_offered_key() -> str:
    """approval.py's global registry key, without importing it at module import
    time (approval is another brief's module and may be mid-edit)."""
    try:
        from services.reply_engine import approval as approval_mod

        return approval_mod.OFFERED_KEY
    except Exception:  # noqa: BLE001
        return "offered_slots"


def release_recovery_slots(store, slot_isos: List[str]) -> None:
    """Give slots back when the recovery copy that advertised them is re-rendered.

    Holding a reservation for a time we no longer offer blocks it for every
    other lead while nobody has been promised it."""
    wanted = set(slot_isos or [])
    if not wanted:
        return
    try:
        store.mutate(OFFERED_SLOTS_KEY,
                     lambda cur: [r for r in (cur or []) if (r.get("slot") if isinstance(r, dict) else r) not in wanted],
                     default=[])
    except Exception as exc:  # noqa: BLE001
        logger.warning("releasing %s failed: %s", sorted(wanted), exc)
    try:
        store.mutate(_approval_offered_key(),
                     lambda cur: [r for r in (cur or [])
                                  if not (isinstance(r, dict) and r.get("source") == "no_show_recovery"
                                          and r.get("slot") in wanted)],
                     default=[])
    except Exception as exc:  # noqa: BLE001
        logger.warning("releasing %s from the shared registry failed: %s", sorted(wanted), exc)


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
    """Link-only: no times in the copy, so nothing to double-offer."""
    info = info or {}
    return {"slots": [], "text": "", "source": info.get("source") or "unavailable", "withheld": reason}


def claim_recovery_slots(now: datetime, ghl, store, appointment: Dict[str, Any],
                         slots_fn: Optional[Callable[[datetime], Dict[str, Any]]] = None,
                         attempts: int = RECOVERY_CLAIM_ATTEMPTS) -> Dict[str, Any]:
    """Pick two times AND hold them for this lead, all or nothing.

    The recovery ladder used to pick from a registry read and append its
    reservation later (``add_once``, no conflict check), so across the GHL
    free-slot read gap another card could take the same times and two leads
    were emailed the same 15 minutes. The hold now goes through
    ``approval.claim_slots``: check and write inside one ``store.mutate``.

    On a conflict the times are re-picked from the SAME free-slot list (the
    other lead's claim is excluded), up to ``attempts`` times. When no
    conflict-free pair is left, or the registry cannot be read, the copy goes
    out link-only (``slots: []``, ``text: ""``) - like the cadence's
    ``slot_taken`` path, a time is never offered twice; unlike it, the touch
    is not deferred, because a recovery email is time-bound. A later slot
    touch re-picks (``_refresh_slot_copy``). Returns the fresh_two_slots dict.
    """
    now_ct = slots.to_tz(slots.ensure_aware(now, TZ), TZ)
    lead = _recovery_claim_lead(appointment)
    fields = _recovery_claim_fields(appointment)
    free = None  # type: Optional[Tuple[List[Any], str]]
    excluded = []  # type: List[str]
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
        if store is None:
            return info
        try:
            from services.reply_engine import approval as approval_mod

            taken = approval_mod.claim_slots(store, lead, isos, now_ct, fields=fields)
        except Exception as exc:  # noqa: BLE001 - an unreadable registry is link-only, never a double-offer
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
        # "Two times that work on my side: Tue 2:00pm CT." names one time.
        # The copy goes link-only instead (render drops the line), as the
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
    slots_text: str = "",
    a2p: Optional[bool] = None,
    slots_source: str = "ghl",
) -> List[Touch]:
    """The recovery touches for the Nth no-show (count starts at 1)."""
    flagged_at = slots.to_tz(slots.ensure_aware(flagged_at, TZ), TZ)
    start = slots.to_tz(slots.parse_iso(appointment["start_iso"]), TZ)
    appt_id = str(appointment.get("id"))
    sms_ok = a2p_registered(a2p)
    if slots_source != "ghl" and settings.is_live():
        slots_text = ""  # never send unverified times live; link-only copy
    touches = []  # type: List[Touch]
    seq = sequence_for_count(count)
    for template_key, channel, offset in seq:
        key = template_key
        if template_key == "ns_d1_other_channel" and not sms_ok:
            key, channel = "ns_d1_other_channel_task", "task"
        when = slots.to_tz(flagged_at + offset, TZ)
        copy = render(key, appointment, start, slots_text, count)
        touch = Touch(
            key="%s:%s:ns%d:%s" % (appt_id, start.isoformat(), count, key),
            appointment_id=appt_id,
            contact_id=appointment.get("contact_id"),
            when_iso=when.isoformat(),
            channel=channel,
            template_key=key,
            subject=copy.get("subject"),
            body=copy["body"],
            meta={"no_show_count": count, "slots_source": slots_source, "start_iso": start.isoformat()},
        )
        stamp_touch(touch, appointment, "no_show", count)
        if channel == "sms":
            # recovery touches are armed off the flag time, not off a time the
            # lead picked, so they respect the lead's own 07:00-19:00 Mon-Fri.
            moved = next_send_window_open(when, lead_tz=lead_tz_of(appointment), weekdays_only=True)
            if moved != when:
                touch.when_iso = moved.isoformat()
                touch.meta["deferred_from"] = when.isoformat()
            if not sms_ok:
                touch.skipped, touch.skip_reason = True, "a2p_not_registered"
        if channel == "email" and template_key != "ns_still_on_email":
            # weekdays_only, like every other proactive email the engine sends:
            # "Missed you on our call" and the day-3 value email used to be
            # deferred by hour only, so a Thursday no-show put the day-3 email
            # on a Sunday and a Friday evening miss put the reschedule email on
            # a Saturday morning.
            moved = next_send_window_open(when, weekdays_only=True)
            if moved != when:
                touch.when_iso = moved.isoformat()
                touch.meta["deferred_from"] = when.isoformat()
        touches.append(touch)
    # the last touch of the sequence carries the stage move
    if touches:
        last = touches[-1]
        if count >= 3:
            last.meta["after"] = "stage:lost"
        elif count == 1:
            last.meta["after"] = "stage:follow_up_later"
        else:
            last.meta["after"] = "note:second_no_show_pattern"
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
    only times GHL verified. Anything else is link-only ("")."""
    info = info or {}
    isos = [i for i in (info.get("slots") or []) if isinstance(i, str) and i]
    if len(isos) < 2:
        return ""
    if info.get("source") != "ghl" and settings.is_live():
        return ""
    return info.get("text") or ""


def rerender_for_dispatch(touch: Touch, rec: Dict[str, Any], appt: Dict[str, Any]) -> bool:
    """Re-render a lead-facing recovery touch from the current code, the
    record's appointment snapshot and its current slot line, and re-stamp it
    (CT3 flag 3: a redeploy that changed a template's hash must not leave the
    pending touches stale). True when re-rendered; on an error the touch
    keeps its copy and stamp, and the gate judges those."""
    if touch.channel not in ("email", "sms"):
        return False
    count = int((touch.meta or {}).get("no_show_count") or 1)
    try:
        start = slots.to_tz(slots.parse_iso((touch.meta or {}).get("start_iso") or appt["start_iso"]), TZ)
        copy = render(touch.template_key, appt, start, offer_text(rec.get("slots")), count)
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("re-rendering %s for dispatch failed: %s", touch.key, type(exc).__name__)
        return False
    touch.subject, touch.body = copy.get("subject"), copy["body"]
    stamp_touch(touch, appt, "no_show", count)
    return True


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
    a2p: Optional[bool] = None,
    slots_fn: Optional[Callable[[datetime], Dict[str, Any]]] = None,
    meeting_signals: Optional[Dict[str, Any]] = None,
    instantly=None,
) -> Dict[str, Any]:
    """Advance one appointment. Returns {'state', 'events': [...], 'actions': [...]}.

    States: pending -> showed | no_show | unknown; no_show -> late_show (lead
    joined after the flag) | rebooked (the call moved) | done.
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
        out["run"] = run_recovery(now, store, ghl, appointment_id=appt_id, a2p=a2p)
        return out

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
    # A recovery record left by an attempt that died before the state write
    # is about to be replaced: its times are given back once the new record
    # is in, or they would stay held for nobody.
    rkey = recovery_key(appt_id, start.isoformat())
    try:
        prior_slots = [i for i in (((store.get(rkey) or {}).get("slots") or {}).get("slots") or [])
                       if isinstance(i, str)]
    except Exception:  # noqa: BLE001
        prior_slots = []
    # picked AND held in one step (claim_slots): never double-offered
    slot_info = claim_recovery_slots(now, ghl, store, appointment, slots_fn=slots_fn)
    claimed = [i for i in (slot_info.get("slots") or []) if isinstance(i, str)]
    if claimed and slot_info.get("source") != "ghl" and settings.is_live():
        # recovery_touches sends unverified times link-only in live: the copy
        # will not name these, so they are not held for this lead either
        release_recovery_claim(store, appointment, claimed)
        slot_info, claimed = dict(slot_info, slots=[], text=""), []
    try:
        touches = recovery_touches(appointment, now, count, slots_text=slot_info.get("text", ""), a2p=a2p,
                                   slots_source=slot_info.get("source", "ghl"))
        # every store record is written BEFORE the GHL calls, so a failed write
        # cannot make the next tick treat this as a fresh, second miss.
        store.set(rkey, {
            "appointment": {k: appointment.get(k) for k in RECOVERY_SNAPSHOT_KEYS if appointment.get(k) is not None},
            "flagged_at": now.isoformat(),
            "no_show_count": count,
            "slots": slot_info,
            "touches": [t.to_dict() for t in touches],
        })
    except Exception:
        # no record carries these times, so no touch will ever offer them
        release_recovery_claim(store, appointment, claimed)
        raise
    stale_prior = [i for i in prior_slots if i not in claimed]
    if stale_prior:
        release_recovery_claim(store, appointment, stale_prior)
    state.update({"state": "no_show", "flagged_at": now.isoformat(), "count": count, "start_iso": start_iso})
    store.set(state_key(appt_id), state)
    res = ghl.update_appointment_status(appt_id, "noshow")
    out["actions"].append(_action("update_appointment_status", {"status": "noshow"}, res))
    note = "No-show #%d at %s (flagged %s). Recovery sequence %s started. Pipeline stage unchanged." % (
        count, fmt_when(start), now.isoformat(), "full" if count == 1 else ("2-touch" if count == 2 else "1-touch then Lost"))
    if contact_id:
        nres = ghl.create_note(contact_id, note)
        out["actions"].append(_action("create_note", {"body": note}, nres))
    out["events"].append("no_show")
    out["state"] = "no_show"
    out["no_show_count"] = count
    out["recovery_touches"] = len(touches)
    out["run"] = run_recovery(now, store, ghl, appointment_id=appt_id, a2p=a2p)
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
    just answered kept getting the 14-day ladder. mutate() does the whole
    read-decide-write under one lock, so the tick's own per-touch writes (also
    mutate) merge instead of clobbering.
    """
    counted = {"n": 0}

    def _apply(rec):
        rec = rec or {}
        for t in rec.get("touches", []):
            if not t.get("sent") and not t.get("skipped"):
                t["skipped"], t["skip_reason"] = True, reason
                counted["n"] += 1
        rec["cancelled"] = reason
        return rec

    for key in store.keys("recovery:%s:" % appt_id):
        store.mutate(key, _apply, default={})
    return counted["n"]


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
    a2p: Optional[bool] = None,
    upcoming_appointments: Optional[List[Dict[str, Any]]] = None,
    slots_fn: Optional[Callable[[datetime], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Send due recovery touches; apply the 'after' stage move when the last
    touch of a sequence actually goes out.

    ``upcoming_appointments`` is the list of appointments the caller just read
    from GHL: any recovery record whose contact has a call in the future is
    cancelled as ``rebooked`` instead of being advanced.
    """
    now = slots.to_tz(slots.ensure_aware(now, TZ), TZ)
    summary = {"sent": [], "would_do": [], "skipped": [], "errors": [], "stage_moves": [],
               "cancelled": [], "held_template": []}  # type: Dict[str, List[Any]]
    rebooked = rebooked_contact_ids(now, upcoming_appointments) if upcoming_appointments is not None else set()
    prefix = "recovery:%s:" % appointment_id if appointment_id else "recovery:"
    for key in store.keys(prefix):
        rec = store.get(key) or {}
        if rec.get("cancelled"):
            continue
        appt = rec.get("appointment", {})
        if rebooked and str(appt.get("contact_id") or "") in rebooked:
            n = _cancel_recovery(store, str(appt.get("id")), str(appt.get("start_iso") or ""), reason="rebooked")
            summary["cancelled"].append({"key": key, "reason": "rebooked", "touches": n})
            continue
        if _appointment_was_held(store, appt):
            n = _cancel_recovery(store, str(appt.get("id")), str(appt.get("start_iso") or ""), reason="showed")
            summary["cancelled"].append({"key": key, "reason": "showed", "touches": n})
            continue
        pending_after = None  # the stage move runs after the touch loop, never inside it
        for raw in rec.get("touches", []):
            if raw.get("sent") or raw.get("skipped"):
                continue
            touch = Touch.from_dict(raw)
            if touch.when() > now:
                continue
            entry = {"key": touch.key, "channel": touch.channel, "template": touch.template_key, "when": touch.when_iso}
            late = _too_late_reason(touch, now)
            if late is not None:
                # came due during an outage: "I am on the Zoom now" a day after
                # the call, or a reschedule email that names a dead slot.
                raw["skipped"], raw["skip_reason"] = True, late
                entry["reason"] = late
                summary["skipped"].append(entry)
                _persist_touch(store, key, touch.key, {"skipped": True, "skip_reason": late})
                continue
            # contact ids are resolved from the record, not from the frozen
            # Touch: an id that arrived on a later tick must revive the ladder.
            touch.contact_id = appt.get("contact_id") or touch.contact_id
            refreshed = _refresh_slot_copy(touch, rec, appt, now, ghl, store, slots_fn, key)
            if refreshed:
                raw.update(refreshed)
                _persist_touch(store, key, touch.key, refreshed)
            elif rerender_for_dispatch(touch, rec, appt):
                raw.update({"subject": touch.subject, "body": touch.body})
            raw.update({"template_id": touch.template_id, "template_hash": touch.template_hash})
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
            out = dispatch_touch(touch, ghl, now, a2p=a2p, store=store, appointment=appt, kind="no_show",
                                 slots_text=offer_text(rec.get("slots")) or None)
            _record_recovery_result(raw, out, entry, summary, now)
            if out.get("status") == HELD:
                note_template_hold(store, raw, out, now)
            elif raw.get("template_hold"):
                raw["template_hold"] = None
            if _stays_pending(out):
                store.delete(claim)  # retryable (or held by the template gate): the next tick tries again
            # persist immediately: an exception later must not re-send this touch
            _persist_touch(store, key, touch.key, {k: raw.get(k) for k in
                                                   ("sent", "sent_at", "result", "skipped", "skip_reason", "attempts",
                                                    "subject", "body", "template_id", "template_hash",
                                                    "template_hold")})
            after = (touch.meta or {}).get("after")
            if after and out["status"] in ("sent", "would_do"):
                pending_after = (after, touch.key)
            elif after and out["status"] == "skipped":
                # nothing was actually said to the lead, so do not move the
                # pipeline; hand it to Lorenzo instead.
                mv = _after_skipped_task(after, appt, ghl, now, out.get("reason"))
                if mv:
                    summary["stage_moves"].append(mv)
        if pending_after is not None:
            mv = _apply_after(pending_after[0], appt, ghl, store, now)
            if mv:
                summary["stage_moves"].append(mv)
    return summary


def _touch_claim_key(touch_key: str) -> str:
    return "touch_sent:%s" % touch_key


def _stays_pending(out: Dict[str, Any]) -> bool:
    """True when this dispatch outcome leaves the touch to be retried (a CT3
    template hold included)."""
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


# How late a recovery touch may be before it is dropped instead of sent. The
# tick can pause (a deploy, a held lock, an appointment that used to crash the
# whole run), and without this the entire backlog fires at once: "Still on? I
# am on the Zoom now" a day after the call ended.
MAX_LATENESS = {
    "ns_still_on_sms": timedelta(minutes=15),
    "ns_still_on_email": timedelta(minutes=15),
    "ns_call_task": timedelta(hours=2),
    "ns_reschedule_email": timedelta(hours=6),
    "ns_d1_other_channel": timedelta(hours=12),
    "ns_d1_other_channel_task": timedelta(hours=12),
    "ns_d3_value_email": timedelta(days=1),
    "ns_d7_yes_no_email": timedelta(days=1),
    "ns_d14_breakup_email": timedelta(days=1),
}


def _too_late_reason(touch: Touch, now: datetime) -> Optional[str]:
    limit = MAX_LATENESS.get(touch.template_key)
    if limit is None:
        return None
    return "too_late" if (now - touch.when()) > limit else None


# The recovery templates whose body carries "Two times that work on my side".
SLOT_TEMPLATES = ("ns_reschedule_email", "ns_d1_other_channel", "ns_d1_other_channel_task",
                  "ns_d3_value_email")


def _slot_still_offerable(iso: str, now: datetime) -> bool:
    try:
        return bool(slots.is_offerable(slots.parse_iso(iso), now))
    except (ValueError, TypeError):
        return False


def _refresh_slot_copy(touch: Touch, rec: Dict[str, Any], appt: Dict[str, Any], now: datetime,
                       ghl, store, slots_fn=None, record_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Re-render the slot line at dispatch time.

    Every touch used to be rendered once, at flag time, so the +1 day SMS and
    the +3 day email quoted two times that had already passed (and the engine
    went on holding those slots against every other lead). Only the template
    key and its parameters are durable; the times are decided now.
    """
    if touch.template_key not in SLOT_TEMPLATES:
        return None
    stored = rec.get("slots") or {}
    stored_isos = [i for i in (stored.get("slots") or []) if isinstance(i, str)]
    good = [i for i in stored_isos if _slot_still_offerable(i, now)]
    if stored_isos and len(good) == len(stored_isos):
        return None  # the frozen copy is still true
    dead = [i for i in stored_isos if i not in good]
    if dead:
        release_recovery_slots(store, dead)
    try:
        # picked AND held in one step (claim_slots): never double-offered
        info = claim_recovery_slots(now, ghl, store, appt, slots_fn=slots_fn)
    except Exception as exc:  # noqa: BLE001 - a dead slot line is worse than none
        logger.warning("re-offering recovery slots failed: %s", exc)
        info = {"slots": [], "text": "", "source": "unavailable"}
    claimed = [i for i in (info.get("slots") or []) if isinstance(i, str)]
    slots_text = (info.get("text") or "") if len(claimed) >= 2 else ""  # one time is link-only
    if info.get("source") != "ghl" and settings.is_live():
        slots_text = ""  # never send unverified times live; link-only copy
        if claimed:
            # the copy will not name them, so nobody is holding them for this lead
            release_recovery_claim(store, appt, claimed)
            info, claimed = dict(info, slots=[], text=""), []
    try:
        start = slots.to_tz(slots.parse_iso(appt["start_iso"]), TZ)
        copy = render(touch.template_key, appt, start, slots_text, int((touch.meta or {}).get("no_show_count") or 1))
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("re-rendering %s failed: %s", touch.key, exc)
        release_recovery_claim(store, appt, claimed)  # the frozen copy goes out; these times never do
        return None
    touch.subject, touch.body = copy.get("subject"), copy["body"]
    stamp_touch(touch, appt, "no_show", int((touch.meta or {}).get("no_show_count") or 1))
    if record_key:
        def _apply(cur):
            cur = cur or {}
            cur["slots"] = info
            return cur

        try:
            store.mutate(record_key, _apply, default={})
        except Exception:
            # the record still names the old times; this run dies before the send
            release_recovery_claim(store, appt, claimed)
            raise
    rec["slots"] = info
    return {"subject": touch.subject, "body": touch.body, "template_id": touch.template_id,
            "template_hash": touch.template_hash,
            "meta": dict(touch.meta or {}, slots_source=info.get("source"), rerendered_at=now.isoformat())}


def _record_recovery_result(raw: Dict[str, Any], out: Dict[str, Any], entry: Dict[str, Any],
                            summary: Dict[str, List[Any]], now: datetime) -> None:
    if out["status"] in ("sent", "would_do"):
        raw["sent"], raw["sent_at"], raw["result"] = True, now.isoformat(), out
        entry["shadow"] = out["status"] == "would_do"
        summary[out["status"]].append(entry)
        return
    if out["status"] == HELD:
        record_held(entry, out, summary)  # pending, no attempt counted
        return
    if out["status"] == "skipped":
        reason = out.get("reason")
        if reason in RETRYABLE_SKIP_REASONS:
            _record_retry(raw, out, entry, summary, reason)
            return
        raw["skipped"], raw["skip_reason"] = True, reason
        entry["reason"] = reason
        summary["skipped"].append(entry)
        return
    _record_retry(raw, out, entry, summary, out.get("error"))


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

    A 14-day ladder that started before Lorenzo answered must not silently
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
