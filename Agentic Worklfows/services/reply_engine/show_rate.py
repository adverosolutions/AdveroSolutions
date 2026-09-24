"""Show-rate sequence (Blueprint S4, rebuilt for section 2 on 2026-09-23):
the widget-booking confirmation and three pre-call reminder emails.

    confirm_email            T+0 (widget bookings; an engine booking's approved
                             reply already confirmed it, see release_hold)
    reminder_24h_email  R2   24 h before the call
    reminder_morning_email R3  08:30 lead-local on the call day, only when R2
                             was skipped and the call is not on the day it was
                             booked (CT when the lead's zone is unknown)
    reminder_1h_email   R4   1 h before the call, everyone

Email only: no texts, no tasks for Lorenzo, no pre-read, no booking link, no
"reply C" (copy: sections/2_booked_calls/copy_signed_off.md).

* ``schedule_for(appointment, now)`` returns the exact list of Touch objects
  for one appointment. A reminder that does not apply is still listed, with
  ``skipped=True`` and its reason (``booked_late``, ``not_needed``,
  ``same_day``, ``past_time``, ...).
* ``ensure_scheduled(store, appointment, now)`` is re-entry safe: the schedule
  is keyed by appointment id + start time, so a reschedule creates a new
  schedule and marks the old one's pending touches ``rescheduled``.
* ``run(now, store, ghl, instantly=...)`` sends due touches. Emails go out
  through ``thread_reply.send_lead_email``: a reply in the lead's own Instantly
  thread, a GHL email only when the lead has no thread. Every write is guarded
  by ``shared.settings.guard_write``; in MODE=shadow the clients return a
  ``{"shadow": True, ...}`` record and no HTTP request is made.

Clocks are always injected (``now``); nothing here reads the wall clock.
Copy rules: no em dashes, signed "Lorenzo", never mentions automation.
"""
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from shared import settings, slots
from shared.settings import BOOKING_URL, GHL_CALENDAR_ID, TZ

try:  # core models are built concurrently; keep a local fallback
    from services.reply_engine import models as _models  # noqa: F401
except Exception:  # noqa: BLE001
    _models = None

logger = logging.getLogger("reply_engine.show_rate")

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
NICHES = ("cleaning", "bookkeeping", "recruiting")
# A2P/SMS: the show-rate ladder sends no texts any more (section 2, email
# only). a2p_registered() stays because no_show and jobs/appointments_tick
# still import it; nothing in this module gates on it.
A2P_ENV = "A2P_10DLC_REGISTERED"
SENDER_ENV = "SHOW_RATE_SENDER"  # "engine" (default) or "ghl": never both
SEND_WINDOW = settings.SEND_WINDOW
# Read by template_gate for an SMS touch; no show-rate touch is SMS any more.
SMS_MAX_LEN = 320
LOOM_PLACEHOLDER_RE = re.compile(r"\[Loom:[^\]]*\]")
# A booking older than this was not made "just now": the T+0 confirmation copy
# ("Locked in ... the calendar invite is on its way") would read as three weeks
# late, so it is skipped instead of sent. See jobs/appointments_tick LOOKAHEAD.
BOOKING_STALE_AFTER = timedelta(hours=2)
# dispatch reasons that mean "try again next tick", not "this touch is done".
# Emails no longer use these (thread_reply's record says whether a retry is
# safe, see _email_outcome); a task still does.
RETRYABLE_SKIP_REASONS = ("ghl_token_missing", "no_contact_id")
# ...but not forever. A permanently broken contact used to produce an error row
# on every 10-minute tick with no cap.
MAX_TOUCH_ATTEMPTS = 12
# Set once, the first time any schedule is created against a store. A store
# with no marker is a cold start (first deploy, or a rebuild after
# JsonFileStore quarantined a corrupt file): every booking already on the
# 30-day calendar is old news, whatever GHL says about dateAdded.
BOOTSTRAP_KEY = "showrate_bootstrap"
FIRST_SEEN_PREFIX = "showrate_seen:"
# How late a touch may be before it is dropped instead of sent. The tick can
# pause (a deploy, a held lock, a retryable error keeping a touch pending), and
# "Still good for tomorrow?" on the day of the call is worse than silence.
MAX_LATENESS = {
    "confirm_email": BOOKING_STALE_AFTER,
    "reminder_24h_email": timedelta(hours=6),
    "reminder_morning_email": timedelta(hours=3),
    "reminder_1h_email": timedelta(minutes=30),
}

# Touch template keys in send order. The tuple is (key, channel, offset).
# confirm_email is relative to the scheduling moment (T+0); the reminders are
# relative to the call's start, except the morning reminder, whose time is a
# clock time (MORNING_REMINDER_AT, lead-local) and has no offset.
SEQUENCE = (
    ("confirm_email", "email", timedelta(0)),
    ("reminder_24h_email", "email", timedelta(hours=-24)),
    ("reminder_morning_email", "email", None),
    ("reminder_1h_email", "email", timedelta(hours=-1)),
)
SEQUENCE_KEYS = tuple(k for k, _, _ in SEQUENCE)
RELATIVE_TO_BOOKING = ("confirm_email",)
# R3 goes out at this lead-local clock time on the call day.
MORNING_REMINDER_AT = (8, 30)
# R2 is skipped (booked_late) when the lead booked less than this long before
# R2's send time: "still good for tomorrow?" minutes after booking reads oddly.
R2_MIN_AFTER_BOOKING = timedelta(hours=6)
BOOKED_LATE = "booked_late"


# --------------------------------------------------------------------- model
@dataclass
class Touch(object):
    key: str                      # unique: <appointment_id>:<start_iso>:<template_key>
    appointment_id: str
    contact_id: Optional[str]
    when_iso: str                 # ISO 8601 with offset, America/Chicago
    channel: str                  # 'email' | 'sms' | 'task'
    template_key: str
    body: str
    subject: Optional[str] = None
    skipped: bool = False
    skip_reason: Optional[str] = None
    sent: bool = False
    sent_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    meta: Dict[str, Any] = field(default_factory=dict)
    # CT3: the catalogue id this copy was rendered from and its hash at render
    # time. Stamped when the touch is scheduled and again when it is
    # dispatched (the copy is re-rendered there, see refresh_copy).
    template_id: Optional[str] = None
    template_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Touch":
        allowed = {k: d.get(k) for k in cls.__dataclass_fields__.keys() if k in d}  # type: ignore[attr-defined]
        allowed.setdefault("meta", {})
        return cls(**allowed)

    def when(self) -> datetime:
        return slots.parse_iso(self.when_iso)


# ------------------------------------------------------------------ helpers
def a2p_registered(override: Optional[bool] = None) -> bool:
    if override is not None:
        return bool(override)
    return os.environ.get(A2P_ENV, "0").strip() in ("1", "true", "yes")


def _tags_of(appointment: Dict[str, Any]) -> List[str]:
    raw = appointment.get("tags") or []
    if isinstance(raw, str):
        raw = [t for t in re.split(r"[,;]", raw)]
    return [str(t).strip().lower() for t in raw if str(t).strip()]


def tagged_niche(appointment: Dict[str, Any]) -> Optional[str]:
    """``niche-cleaning`` etc., the tag the published GHL workflows branch on."""
    for tag in _tags_of(appointment):
        if tag.startswith("niche-") and tag[len("niche-"):] in NICHES:
            return tag[len("niche-"):]
    return None


def tagged_offer(appointment: Dict[str, Any]) -> Optional[str]:
    """``offer-reactivation`` / ``offer-outbound``.

    This is the authoritative source for a GHL booking: a calendar event
    carries no campaign key, so without the tag every real booking fell back
    to "reactivation" and an outbound/trigger prospect was quoted commission
    pricing and the reactivation proof point instead of their own guarantee.
    """
    for tag in _tags_of(appointment):
        if tag.startswith("offer-") and tag[len("offer-"):] in ("reactivation", "outbound"):
            return tag[len("offer-"):]
    return None


def niche_of(appointment: Dict[str, Any]) -> str:
    niche = (appointment.get("niche") or "").strip().lower()
    if niche in NICHES:
        return niche
    tagged = tagged_niche(appointment)
    if tagged:
        return tagged
    campaign_key = appointment.get("campaign_key") or ""
    camp = settings.CAMPAIGNS.get(campaign_key) or settings.CAMPAIGN_BY_ID.get(appointment.get("campaign_id"))
    if camp and camp.get("niche") in NICHES:
        return camp["niche"]
    blob = " ".join(str(appointment.get(k) or "") for k in ("title", "company", "tags")).lower()
    for n in NICHES:
        if n in blob or (n == "bookkeeping" and ("accounting" in blob or "tax" in blob or "cpa" in blob)):
            return n
    if "clean" in blob or "janitorial" in blob or "facility" in blob:
        return "cleaning"
    if "staffing" in blob or "recruit" in blob or "talent" in blob:
        return "recruiting"
    return "generic"


def offer_of(appointment: Dict[str, Any]) -> str:
    offer = (appointment.get("offer") or "").strip().lower()
    if offer in ("reactivation", "outbound"):
        return offer
    tagged = tagged_offer(appointment)
    if tagged:
        return tagged
    camp = settings.CAMPAIGNS.get(appointment.get("campaign_key") or "") or settings.CAMPAIGN_BY_ID.get(
        appointment.get("campaign_id")
    )
    if camp and camp.get("offer") in ("reactivation", "outbound"):
        return camp["offer"]
    return "reactivation"


def first_name_of(appointment: Dict[str, Any]) -> str:
    name = appointment.get("first_name") or ""
    if not name:
        full = appointment.get("contact_name") or appointment.get("name") or ""
        name = full.split(" ")[0] if full else ""
    return name.strip() or "there"


def company_of(appointment: Dict[str, Any]) -> str:
    return (appointment.get("company") or "your business").strip()


def _clock(dt: datetime) -> str:
    """'11:30am', '12:05pm': the clock with am/pm, as shared.slots writes slots.
    Without am/pm a lead reading '3:00 CT' could not tell 3am from 3pm."""
    return "%d:%02d%s" % (dt.hour % 12 or 12, dt.minute, "am" if dt.hour < 12 else "pm")


def fmt_when(dt: datetime, lead_tz=None) -> str:
    """'Tue, Sep 23 at 11:30am CT' (+ ' (12:30pm ET)' when the lead's tz is known)."""
    ct = slots.to_tz(dt, TZ)
    text = "%s, %s %d at %s CT" % (ct.strftime("%a"), ct.strftime("%b"), ct.day, _clock(ct))
    if lead_tz is not None and getattr(lead_tz, "zone", "") not in ("", "America/Chicago"):
        local = ct.astimezone(lead_tz)
        label = slots._tz_label(local, lead_tz)  # noqa: SLF001 - small shared helper
        text += " (%s %s)" % (_clock(local), label)
    return text


def fmt_time_only(dt: datetime, lead_tz=None) -> str:
    """'4:30pm CT' (+ ' (5:30pm ET)' when the lead's tz is known and not
    Central, as fmt_when). Called with one argument it is exactly the old
    Central-only form, which no_show and the template gate's checks use."""
    ct = slots.to_tz(dt, TZ)
    text = "%s CT" % _clock(ct)
    if lead_tz is not None and getattr(lead_tz, "zone", "") not in ("", "America/Chicago"):
        local = ct.astimezone(lead_tz)
        label = slots._tz_label(local, lead_tz)  # noqa: SLF001 - small shared helper
        text += " (%s %s)" % (_clock(local), label)
    return text


def lead_tz_of(appointment: Dict[str, Any]):
    raw = appointment.get("lead_tz") or appointment.get("timezone")
    if not raw:
        return None
    if hasattr(raw, "zone"):
        return raw
    tz = slots.detect_tz(str(raw))
    if tz is not None:
        return tz
    try:
        import pytz

        return pytz.timezone(str(raw))
    except Exception:  # noqa: BLE001
        return None


def call_link_of(appointment: Dict[str, Any]) -> str:
    """The call's join link on file (Zoom, or Google Meet for widget
    bookings), or "". The template gate judges the link itself."""
    return str(appointment.get("zoom_link") or appointment.get("meeting_link") or "").strip()


def loom_line(niche: str) -> str:
    """The Loom sentence, or '' when no URL is configured.

    It used to emit a ``[Loom: ...]`` placeholder, which ``dispatch_touch``
    then refuses to send in live mode: on go-live day that silently dropped
    the single most important S4 message. The line is optional copy, so an
    unrecorded Loom simply removes the sentence.
    """
    url = os.environ.get("LOOM_URL_%s" % niche.upper()) or os.environ.get("LOOM_URL_GENERIC")
    if url:
        return "Here is a 60-second walkthrough of what I will show you, if you want a head start: %s" % url
    return ""


def has_unresolved_placeholder(text: str) -> bool:
    return bool(LOOM_PLACEHOLDER_RE.search(text or "")) or "{{" in (text or "")


AGENDA = {
    ("cleaning", "reactivation"): [
        "which of your lost or dormant accounts are worth going after first",
        "what the email and text sequences say, so it sounds like you and not a vendor",
        "the commission-only numbers, so you know exactly what a returned account pays me",
    ],
    ("cleaning", "outbound"): [
        "which building types and trigger events (new leases, expansions, PM changes) fit your crews",
        "how the outreach runs under your name and books walkthroughs on your calendar",
        "the guarantee ($24,000 a year in new cleaning contracts signed within 90 days) and what it would cost",
    ],
    ("bookkeeping", "reactivation"): [
        "which former clients and lost inquiries to go after first, timed to tax season and year-end",
        "what the email and text sequences say, so it reads like your practice",
        "the numbers: $0 up front, 20 to 30% of first-year fees on clients that come back",
    ],
    ("bookkeeping", "outbound"): [
        "which triggers (new formations, bookkeeper job posts, second locations) fit your ideal client",
        "how the outreach runs under your name and books discovery calls on your calendar",
        "the guarantee ($15,000 in new annual client fees within 90 days) and what it would cost",
    ],
    ("recruiting", "reactivation"): [
        "which dormant and near-miss client accounts are worth going after first",
        "what the sequences say to a hiring manager who used you once",
        "the numbers: $0 up front, a cut of the first placement fee on accounts that come back",
    ],
    ("recruiting", "outbound"): [
        "which specialties and geographies to watch for open roles",
        "how the outreach reaches hiring managers under your agency's name",
        "the guarantee ($40,000 in new placement fees within 180 days) and what it would cost",
    ],
    # No niche on file: the offer still decides the agenda. An outbound
    # prospect used to get the reactivation agenda (dormant accounts).
    ("generic", "outbound"): [
        "who is in market for what you sell right now",
        "how the outreach runs under your name and books calls on your calendar",
        "the guarantee and what it would cost",
    ],
}
GENERIC_AGENDA = [
    "which of your dormant accounts are worth going after first",
    "what the sequences say, so it sounds like you",
    "the numbers, so you know exactly what it pays me and what it costs you",
]


def agenda_for(niche: str, offer: str) -> List[str]:
    return AGENDA.get((niche, offer)) or AGENDA.get(("generic", offer)) or GENERIC_AGENDA


# ------------------------------------------------------------------- copy
def render(template_key: str, appointment: Dict[str, Any], start: datetime, now: datetime) -> Dict[str, str]:
    """Return {'subject', 'body'} for a template key. All copy lives here.

    The reminders are word for word sections/2_booked_calls/copy_signed_off.md
    (Lorenzo signed off every word, 2026-09-23), with its no-link variants.
    The subject is used only when the lead has no thread and the email goes
    as a GHL email; in the thread the reply carries "Re: <thread subject>"."""
    first = first_name_of(appointment)
    niche = niche_of(appointment)
    offer = offer_of(appointment)
    lead_tz = lead_tz_of(appointment)
    when_ct = fmt_when(start, lead_tz)
    # {time}: the lead's own clock in brackets when their zone is known and
    # not Central, as {when}: "2:00pm CT (3:00pm ET)".
    time_local = fmt_time_only(start, lead_tz)
    # The call's join link (a Zoom or Google Meet link), or "" when none is on
    # file. Platform-neutral wording: widget bookings are on Google Meet. With
    # no link, each message says where the link is instead of quoting one;
    # that wording is its own catalogue variant (no_call_link), never a phrase
    # standing in for the link.
    link = call_link_of(appointment)

    if template_key == "confirm_email":
        bullets = "\n".join("- %s" % b for b in agenda_for(niche, offer))
        loom = loom_line(niche)
        if link:
            invite = ("The calendar invite is on its way with the call link, and here it is too so you do not have "
                      "to dig: %s" % link)
        else:
            invite = "The calendar invite is on its way with the call link."
        body = (
            "Hey %s,\n\n"
            "Locked in for %s. %s\n\n"
            "Here is what I want to cover in the 15 minutes:\n%s\n\n"
            "%s"
            "If anything comes up before then, reply here and we will move it.\n\n"
            "Lorenzo"
        ) % (first, when_ct, invite, bullets, (loom + "\n\n") if loom else "")
        return {"subject": "Confirmed: %s, 15 minutes with Lorenzo" % when_ct, "body": body}

    if template_key == "reminder_24h_email":
        # R2, the day-before check. Any reply counts as a yes.
        link_line = ("Link for tomorrow: %s" % link) if link else "The link is on your calendar invite."
        body = (
            "Hey %s,\n\n"
            "Still good for tomorrow? I have you down for %s. A quick yes works.\n\n"
            "%s\n\n"
            "If the time doesn't work anymore, just reply and I'll send a couple of other times.\n\n"
            "Lorenzo"
        ) % (first, when_ct, link_line)
        return {"subject": "Tomorrow's call", "body": body}

    if template_key == "reminder_morning_email":
        # R3, the morning-of check (only when R2 was skipped). Any reply counts as a yes.
        where = ("Link's here: %s" % link) if link else "The link's on your calendar invite."
        body = (
            "Hey %s,\n\n"
            "Morning. Are we still set for %s today? %s\n\n"
            "If something came up, just reply and we'll find another time.\n\n"
            "Lorenzo"
        ) % (first, time_local, where)
        return {"subject": "Today's call", "body": body}

    if template_key == "reminder_1h_email":
        # R4, the one-hour heads-up, to everyone (confirmed or not).
        if link:
            opener = "Talk in an hour. Here's the link:\n%s" % link
        else:
            opener = "Talk in an hour. The call link is on the calendar invite from when we booked."
        body = (
            "Hey %s,\n\n"
            "%s\n\n"
            "If %s won't work after all, reply here and we'll move it.\n\n"
            "Lorenzo"
        ) % (first, opener, time_local)
        return {"subject": "See you at %s" % time_local, "body": body}

    raise KeyError("unknown template %s" % template_key)


# --------------------------------------------------- template gate (CT3)
# The lead-facing channels the template gate judges. Tasks are Lorenzo's own
# to-do items and are not gated.
GATED_CHANNELS = ("email", "sms")
# dispatch statuses: "held" (CT3) means the template gate refused the copy.
# The touch stays pending (not sent, not skipped, no attempt counted) until an
# approval lets it out or MAX_LATENESS expires it.
HELD = "held"


def template_kind(template_key: str) -> str:
    """"no_show" for the recovery ladder's keys (ns_*), else "show_rate"."""
    return "no_show" if str(template_key or "").startswith("ns_") else "show_rate"


def resolve_template_id(template_key: str, appointment: Dict[str, Any], kind: Optional[str] = None,
                        count: int = 1) -> Optional[str]:
    """The catalogue id for this touch's copy, from the appointment's niche and
    offer as render() resolves them (niche_of / offer_of, flag 12). The second
    no-show's reschedule email has its own copy (.repeat). None when no
    entry covers the combination (the gate then holds the touch)."""
    try:
        from services.reply_engine import template_gate

        kind = kind or template_kind(template_key)
        repeat = kind == "no_show" and template_key == "ns_reschedule_email" and int(count or 1) >= 2
        return template_gate.resolve_combo_id(kind, template_key, niche_of(appointment), offer_of(appointment),
                                              repeat=repeat)
    except Exception as exc:  # noqa: BLE001 - no id is a hold, never a send
        logger.warning("could not resolve the template id of %s: %s", template_key, type(exc).__name__)
        return None


def stamp_touch(touch: "Touch", appointment: Dict[str, Any], kind: Optional[str] = None, count: int = 1) -> None:
    """Record which template the touch's current copy was rendered from, and
    that template's hash now. Lead-facing channels only; never raises."""
    if touch.channel not in GATED_CHANNELS:
        return
    try:
        from services.reply_engine import template_gate

        template_gate.stamp(touch, resolve_template_id(touch.template_key, appointment, kind, count))
    except Exception as exc:  # noqa: BLE001 - an unstamped touch is held by the gate
        logger.warning("could not stamp %s: %s", touch.key, type(exc).__name__)


def _touch_start(touch: "Touch", appointment: Dict[str, Any]) -> datetime:
    """The call time this touch's schedule is for (its meta), else the
    appointment's."""
    raw = (touch.meta or {}).get("start_iso") or appointment.get("start_iso")
    return slots.to_tz(slots.parse_iso(raw), TZ)


def refresh_copy(touch: "Touch", appointment: Dict[str, Any], now: datetime) -> bool:
    """Re-render a lead-facing show-rate touch from the current code and the
    freshest appointment snapshot, and re-stamp it (flag 3). Stamping only at
    schedule time meant any redeploy that changed a template's hash left every
    pending touch stale, held until it expired. True when re-rendered; on an
    error the touch is left as it was (the gate judges its old stamp)."""
    if touch.channel not in GATED_CHANNELS:
        return False
    try:
        copy = render(touch.template_key, appointment, _touch_start(touch, appointment), now)
    except Exception as exc:  # noqa: BLE001 - the frozen copy is judged instead
        logger.warning("re-rendering %s failed: %s", touch.key, type(exc).__name__)
        return False
    touch.subject, touch.body = copy.get("subject"), copy["body"]
    stamp_touch(touch, appointment, "show_rate")
    return True


def appointment_allow_terms(appointment: Dict[str, Any]) -> List[str]:
    """The lead's own values render() quotes back (flag 8): a company called
    "Automated Janitorial" is not a copy failure."""
    return [v for v in (company_of(appointment), first_name_of(appointment)) if v]


def touch_bindings(touch: "Touch", appointment: Dict[str, Any], slots_text: Optional[str] = None) -> Dict[str, str]:
    """What render() put into each placeholder, for the gate's conformance
    check: the call time from the engine's own formatters
    (template_gate.appointment_bindings), the names, the links and (no-show)
    the offered slots. Only values that were rendered are bound."""
    out = {}  # type: Dict[str, Any]
    try:
        from services.reply_engine import template_gate

        start = _touch_start(touch, appointment)
        out.update(template_gate.appointment_bindings(appointment, start))
        if "time_ct" in out and template_kind(touch.template_key) == "show_rate":
            # The reminders' {time} carries the lead's own clock in brackets
            # (fmt_time_only with the lead's zone, as render() writes it);
            # appointment_bindings binds the Central-only form the no-show
            # copy uses. Same formatter, same appointment: an engine value.
            out["time_ct"] = template_gate._EngineTime(  # noqa: SLF001 - the gate's own engine-value marker
                fmt_time_only(start, lead_tz_of(appointment)))
    except Exception as exc:  # noqa: BLE001 - unbound times still get the typed check
        logger.warning("no time bindings for %s: %s", touch.key, type(exc).__name__)
    out["first_name"] = first_name_of(appointment)
    out["company"] = company_of(appointment)
    link = call_link_of(appointment)
    if link and "zoom_link" not in out:
        # appointment_bindings() binds it as the engine's own link (the only
        # way a Meet link passes); a plain binding here only narrows
        out["zoom_link"] = link
    booking = appointment.get("reschedule_link") or appointment.get("booking_url") or BOOKING_URL
    if booking:
        out["booking_url"] = booking
    loom = os.environ.get("LOOM_URL_%s" % niche_of(appointment).upper()) or os.environ.get("LOOM_URL_GENERIC")
    if loom:
        out["loom_url"] = loom
    if slots_text:
        out["slots"] = slots_text
    return dict((k, v) for k, v in out.items() if isinstance(v, str) and v)


def _opt_out_marker(row: Any) -> Any:
    if _models is not None and hasattr(_models, "opt_out_marker"):
        return _models.opt_out_marker(row)
    marker = row.get("opt_out") if isinstance(row, dict) else None
    return marker or None


def lead_opted_out(store, appointment: Optional[Dict[str, Any]], appointment_id: Any) -> Optional[bool]:
    """Does any stored lead row of this call's lead carry the sticky opt-out
    marker? The lead is the appointment's email, else the one the
    ``appointment:<id>`` row booking.register_booking wrote (the same
    resolution as no_show._lead_identity, repeated here because no_show
    imports this module). Every campaign's row for that email counts. None
    when there is no store or no email to look up; raises when the store
    cannot be read (the caller holds)."""
    if store is None:
        return None
    appointment = appointment or {}
    emails = [e for e in (appointment.get("email"), appointment.get("lead_email")) if e]
    rec = store.get("appointment:%s" % appointment_id) if appointment_id is not None else None
    if isinstance(rec, dict) and rec.get("lead_email"):
        emails.append(rec["lead_email"])
    wanted = set(str(e).strip().lower() for e in emails if str(e).strip())
    if not wanted:
        return None
    for key in store.keys("lead:"):
        if key.rsplit(":", 1)[-1].strip().lower() not in wanted:
            continue
        if _opt_out_marker(store.get(key) or {}):
            return True
    return False


def gate_touch(touch: "Touch", appointment: Optional[Dict[str, Any]], kind: Optional[str] = None,
               slots_text: Optional[str] = None) -> Any:
    """template_gate.appointment_touch_verdict on the touch's exact subject and
    body, with allow_terms (flag 8) and the rendered values bound. Fails
    closed: an error is a failed verdict."""
    appointment = appointment or {}
    kind = kind or template_kind(touch.template_key)
    try:
        from services.reply_engine import template_gate

        return template_gate.appointment_touch_verdict(
            touch, kind=kind, allow_terms=appointment_allow_terms(appointment),
            campaign_key=appointment.get("campaign_key") or None,
            bindings=touch_bindings(touch, appointment, slots_text))
    except Exception as exc:  # noqa: BLE001 - a gate that cannot answer holds the touch
        logger.warning("template gate failed closed for %s: %s", touch.key, type(exc).__name__)

        class _Failed(object):
            allowed = False
            reason = "registry_error"
            template_id = touch.template_id

            @staticmethod
            def to_record():
                return {"allowed": False, "reason": "registry_error", "template_id": touch.template_id,
                        "ids": [touch.template_id] if touch.template_id else [], "statuses": {}}
        return _Failed()


def note_template_hold(store, raw: Dict[str, Any], out: Dict[str, Any], now: datetime) -> None:
    """Count a held touch once per reason for the FYI (template_gate.note_held)
    and remember the hold on the touch record. A touch held on every tick is
    counted once, not every five minutes."""
    prev = raw.get("template_hold") or {}
    hold = {"template_id": out.get("template_id"), "reason": out.get("reason"),
            "since": prev.get("since") or now.isoformat()}
    raw["template_hold"] = hold
    if prev.get("reason") == hold["reason"] and prev.get("template_id") == hold["template_id"]:
        return
    try:
        from services.reply_engine import template_gate

        template_gate.note_held(store, kind=out.get("kind") or template_kind(raw.get("template_key")),
                                template_id=hold["template_id"], reason=hold["reason"], now=now)
    except Exception as exc:  # noqa: BLE001 - the FYI count must not fail the tick
        logger.warning("could not count the held touch %s: %s", raw.get("key"), type(exc).__name__)


# ------------------------------------------------------------- scheduling
def schedule_key(appointment_id: str, start_iso: str) -> str:
    return "showrate:%s:%s" % (appointment_id, start_iso)


def _localize(tz, date_, hour: int, minute: int = 0) -> datetime:
    naive = datetime(date_.year, date_.month, date_.day, hour, minute)
    if hasattr(tz, "localize"):
        return tz.localize(naive)
    return naive.replace(tzinfo=tz)


def _advance_for_zone(ct: datetime, tz, weekdays_only: bool) -> datetime:
    """The same instant, or the next 07:00 in ``tz`` when ``ct`` is outside
    that zone's 07:00-19:00 (and, for SMS, outside Mon-Fri). Returns CT."""
    local = ct.astimezone(tz)
    if weekdays_only and local.weekday() >= 5:  # Sat -> +2, Sun -> +1
        monday = (local + timedelta(days=7 - local.weekday())).date()
        return slots.to_tz(_localize(tz, monday, SEND_WINDOW[0]), TZ)
    if local.hour < SEND_WINDOW[0]:
        return slots.to_tz(_localize(tz, local.date(), SEND_WINDOW[0]), TZ)
    if local.hour >= SEND_WINDOW[1]:
        tomorrow = (local + timedelta(days=1)).date()
        return slots.to_tz(_localize(tz, tomorrow, SEND_WINDOW[0]), TZ)
    return ct


def next_send_window_open(dt: datetime, lead_tz=None, weekdays_only: bool = False) -> datetime:
    """Move ``dt`` to the next moment inside 07:00-19:00 Central AND, when the
    lead's timezone is known, inside 07:00-19:00 there too.

    ``weekdays_only`` (every email since section 2: the in-thread send refuses
    a weekend, slots.is_send_time) also pushes a Saturday or Sunday arming to
    Monday 07:00 local. Without the lead-side check a Friday-night booking from
    a Pacific lead deferred to 07:00 CT, which is 05:00 Saturday for them.
    The returned instant is always expressed in Central.
    """
    ct = slots.to_tz(dt, TZ)
    zones = [TZ]
    if lead_tz is not None and getattr(lead_tz, "zone", "") not in ("", "America/Chicago"):
        zones.append(lead_tz)
    for _ in range(12):  # each pass moves forward; 12 is far more than needed
        moved = ct
        for tz in zones:
            moved = _advance_for_zone(moved, tz, weekdays_only)
            if moved != ct:
                break
        if moved == ct:
            return ct
        ct = moved
    return ct


def booking_moment(appointment: Dict[str, Any], now: datetime) -> datetime:
    """When the lead booked: ``min(booked_at, now)`` when ``booked_at`` is on
    the appointment and readable, else ``now`` (the schedule is being created
    the tick after the booking). Central."""
    now = slots.to_tz(slots.ensure_aware(now, TZ), TZ)
    raw = appointment.get("booked_at")
    if not raw:
        return now
    try:
        booked = slots.to_tz(slots.parse_iso(raw), TZ)
    except (ValueError, TypeError):
        return now
    return min(booked, now)


def morning_reminder_time(start: datetime, lead_tz=None) -> datetime:
    """08:30 on the call day in the lead's zone (Central when it is unknown),
    expressed in Central."""
    zone = lead_tz or TZ
    local_day = slots.to_tz(start, TZ).astimezone(zone).date()
    hour, minute = MORNING_REMINDER_AT
    return slots.to_tz(_localize(zone, local_day, hour, minute), TZ)


def reminder_plan(start: datetime, now: datetime, booked: datetime, lead_tz=None) -> Dict[str, Dict[str, Any]]:
    """{template_key: {"when": datetime, "skip": reason|None, "why": detail|None}}
    for R2, R3 and R4 (copy_signed_off.md, "Reminders").

    R2 (-24 h) is skipped ``booked_late`` when its time is already past, when
    the booking moment is later than R2's time minus six hours, or when R2's
    time is outside the send window (a Saturday or Sunday: slots.is_send_time
    is weekdays only, so a Monday call gets R3 instead).

    R3 (08:30 lead-local on the call day) is scheduled only when R2 was
    skipped and the call is not on the booking's own lead-local day. 08:30
    lead-local before the Central window opens (a zone east of Eastern) moves
    to the window's opening. It is skipped ``past_time`` when its time is gone
    and ``too_close_to_call`` when it would land at or after R4.

    R4 (-1 h) goes to everyone unless its time is already past."""
    start = slots.to_tz(start, TZ)
    now = slots.to_tz(now, TZ)
    booked = slots.to_tz(booked, TZ)
    late = now - timedelta(seconds=1)
    plan = {}  # type: Dict[str, Dict[str, Any]]

    r2 = start - timedelta(hours=24)  # absolute-instant arithmetic: 24 real hours, DST-safe
    why = None
    if r2 < late:
        why = "past"
    elif booked > r2 - R2_MIN_AFTER_BOOKING:
        why = "within_6h_of_booking"
    elif not slots.is_send_time(r2):
        why = "weekend" if r2.weekday() >= 5 else "outside_send_window"
    plan["reminder_24h_email"] = {"when": r2, "skip": BOOKED_LATE if why else None, "why": why}

    r4 = start - timedelta(hours=1)
    plan["reminder_1h_email"] = {"when": r4, "skip": "past_time" if r4 < late else None, "why": None}

    zone = lead_tz or TZ
    r3 = morning_reminder_time(start, lead_tz)
    skip, why = None, None
    if plan["reminder_24h_email"]["skip"] is None:
        skip = "not_needed"            # R2 goes: R3 is only its stand-in
    elif start.astimezone(zone).date() == booked.astimezone(zone).date():
        skip = "same_day"              # booked on the call day: the confirmation and R4 are enough
    else:
        moved = next_send_window_open(r3, lead_tz=lead_tz, weekdays_only=True)
        if moved != r3:
            why, r3 = "deferred_from %s" % r3.isoformat(), moved
        if r3 < late:
            skip = "past_time"
        elif r3 >= r4:
            skip = "too_close_to_call"
    plan["reminder_morning_email"] = {"when": r3, "skip": skip, "why": why}
    return plan


def schedule_for(
    appointment: Dict[str, Any],
    now: datetime,
    a2p: Optional[bool] = None,
    stale_booking: Optional[bool] = None,
    booked: Optional[datetime] = None,
) -> List[Touch]:
    """Exactly the S4 touches for one appointment, in send order.

    appointment: id, contact_id, start_iso, end_iso, zoom_link|None, email,
    niche, first_name, company, lead_tz, booked_at (optional).

    ``stale_booking`` is the caller's verdict on "was this booked just now".
    ``ensure_scheduled`` decides it from the store (which knows whether the
    engine has seen this appointment before); passing None falls back to the
    ``booked_at`` field alone, which is all a bare ``schedule_for`` can know.

    ``booked`` is the booking moment the R2/R3 rules measure from; default
    ``booking_moment(appointment, now)``. ensure_scheduled passes ``now`` for
    a reschedule (GHL's dateAdded does not move when the lead moves the call).
    ``a2p`` is accepted for old callers and ignored: nothing here is SMS.
    """
    now = slots.to_tz(slots.ensure_aware(now, TZ), TZ)
    start = slots.to_tz(slots.parse_iso(appointment["start_iso"]), TZ)
    start_iso = start.isoformat()
    appt_id = str(appointment.get("id"))
    contact_id = appointment.get("contact_id")
    lead_tz = lead_tz_of(appointment)
    if stale_booking is None:
        stale_booking = _booking_is_stale(appointment, now)
    booked = booking_moment(appointment, now) if booked is None else slots.to_tz(booked, TZ)
    plan = reminder_plan(start, now, booked, lead_tz)
    touches = []  # type: List[Touch]
    for template_key, channel, offset in SEQUENCE:
        if template_key in RELATIVE_TO_BOOKING:
            when = slots.to_tz(now + offset, TZ)
            step = {"skip": None, "why": None}  # type: Dict[str, Any]
        else:
            step = plan[template_key]
            when = step["when"]
        copy = render(template_key, appointment, start, now)
        touch = Touch(
            key="%s:%s:%s" % (appt_id, start_iso, template_key),
            appointment_id=appt_id,
            contact_id=contact_id,
            when_iso=when.isoformat(),
            channel=channel,
            template_key=template_key,
            subject=copy.get("subject"),
            body=copy["body"],
            meta={"niche": niche_of(appointment), "offer": offer_of(appointment), "start_iso": start_iso},
        )
        stamp_touch(touch, appointment, "show_rate")
        if template_key in RELATIVE_TO_BOOKING:
            # only the touch armed off the booking moment can land at a bad
            # local hour: the widget takes bookings at any hour, and the engine
            # sends 07:00-19:00 CT on weekdays only (the in-thread send refuses
            # anything else, slots.is_send_time). A Saturday booking's
            # confirmation goes on Monday morning rather than never. A reminder
            # anchored to the call is at a time the lead picked and never moves.
            moved = next_send_window_open(when, lead_tz=lead_tz, weekdays_only=True)
            if moved != when:
                touch.when_iso = moved.isoformat()
                touch.meta["deferred_from"] = when.isoformat()
            if stale_booking:
                # picked up long after the lead booked: "Locked in ... the invite
                # is on its way" would arrive days late, so it is not sent at all.
                touch.skipped, touch.skip_reason = True, "stale_booking"
        elif step["skip"]:
            touch.skipped, touch.skip_reason = True, step["skip"]
        if step.get("why"):
            touch.meta["why"] = step["why"]
        touches.append(touch)
    return touches


def _booking_is_stale(appointment: Dict[str, Any], now: datetime) -> bool:
    """Does ``booked_at`` prove this booking is old news?

    A missing field is "cannot tell" here, not "fresh": the fail-closed
    decision needs the store and lives in ``_staleness``. An UNPARSEABLE field
    is treated as stale, because a value we cannot read is not evidence that
    the lead booked in the last two hours.
    """
    raw = appointment.get("booked_at") or appointment.get("created_iso")
    if not raw:
        return False
    try:
        booked = slots.to_tz(slots.parse_iso(raw), TZ)
    except (ValueError, TypeError):
        logger.warning("appointment %s has an unreadable booked_at %r; treating it as an old booking",
                       appointment.get("id"), raw)
        return True
    return (now - booked) > BOOKING_STALE_AFTER


def claim_bootstrap(store, now: datetime) -> bool:
    """True exactly once per store: this is the engine's first run against it.

    Claimed ONCE PER RUN, not per appointment: a cold start sees the whole
    30-day calendar at once, and if each appointment claimed the marker in
    turn only the first would count as a backfill.
    """
    return bool(store.set_if_absent(BOOTSTRAP_KEY, {"at": now.isoformat()}))


def _staleness(store, appointment: Dict[str, Any], now: datetime,
               cold_start: Optional[bool] = None) -> Dict[str, Any]:
    """Decide, once per (appointment id, start), whether the T+0 confirmation
    copy is still true. Returns {'stale': bool, 'reason': str}.

    ``booked_at`` alone is not enough in either direction:

    * GHL's calendar-events payload need not carry ``dateAdded``, and treating
      a missing field as "freshly booked" mailed "Locked in for ... the
      calendar invite is on its way" to every booking already sitting in the
      30-day window on the first tick after deploy;
    * ``dateAdded`` does NOT move on a reschedule (only ``dateUpdated`` does),
      so a lead who moved her call looked like a two-day-old booking and got
      no confirmation and no pre-read for the new time.

    So the store answers instead: a key the engine has never seen while it was
    already running was booked between two ticks, and an appointment id it
    already knows under another start has just been rescheduled.
    """
    appt_id = str(appointment.get("id"))
    start_iso = slots.to_tz(slots.parse_iso(appointment["start_iso"]), TZ).isoformat()
    if cold_start is None:
        cold_start = claim_bootstrap(store, now)
    store.set_if_absent("%s%s:%s" % (FIRST_SEEN_PREFIX, appt_id, start_iso), {"at": now.isoformat()})
    rescheduled = any(k != schedule_key(appt_id, start_iso) for k in store.keys("showrate:%s:" % appt_id))
    raw = appointment.get("booked_at") or appointment.get("created_iso")
    if raw:
        stale = _booking_is_stale(appointment, now)
        if stale and rescheduled:
            return {"stale": False, "reason": "rescheduled"}
        return {"stale": stale, "reason": "booked_at"}
    if rescheduled:
        return {"stale": False, "reason": "rescheduled"}
    if cold_start:
        logger.warning("appointment %s has no booked_at and this is the first run against this store; "
                       "treating it as an existing booking and skipping the T+0 confirmation", appt_id)
        return {"stale": True, "reason": "cold_start_no_booked_at"}
    return {"stale": False, "reason": "first_seen"}


def ensure_scheduled(store, appointment: Dict[str, Any], now: datetime, a2p: Optional[bool] = None,
                     cold_start: Optional[bool] = None, _quiet_hold_errors: bool = False) -> Dict[str, Any]:
    """Create the schedule once per (appointment id, start). Re-entry safe.

    Returns {'key', 'created', 'rearmed', 'touches': [dict], 'cancelled': [keys]}.
    A reschedule marks the other schedules' pending touches ``rescheduled`` and
    clears the confirmation flag (it belonged to the old time). Coming
    *back* to a slot the appointment already used re-arms that schedule instead
    of returning a record whose every touch is dead.
    """
    now = slots.to_tz(slots.ensure_aware(now, TZ), TZ)
    start = slots.to_tz(slots.parse_iso(appointment["start_iso"]), TZ)
    start_iso = start.isoformat()
    appt_id = str(appointment.get("id"))
    key = schedule_key(appt_id, start_iso)
    existing = store.get(key)
    cancelled = []  # type: List[str]
    # a reschedule: other schedules for the same appointment id lose their pending touches
    for other in store.keys("showrate:%s:" % appointment.get("id")):
        if other == key:
            continue
        marker = {"changed": False}

        def _supersede(rec, _marker=marker):
            rec = rec or {}
            for t in rec.get("touches", []):
                if not t.get("sent") and not t.get("skipped"):
                    t["skipped"], t["skip_reason"], _marker["changed"] = True, "rescheduled", True
            if _marker["changed"]:
                rec["superseded_by"] = key
            return rec

        store.mutate(other, _supersede, default={})
        if marker["changed"]:
            cancelled.append(other)
    if cancelled or (existing and existing.get("superseded_by")):
        clear_confirmed(store, appt_id, start_iso)
    # An appointment awaiting Lorenzo's approval is on the calendar but must not
    # be spoken to. The marker outlives this call, so a schedule created here
    # OR by the next calendar-driven tick is born held.
    #
    # A marker that could not be READ is not a missing marker: the saved
    # ``held`` stays exactly as it is (never dropped on an error), a new
    # schedule is born provisionally held, and the result carries
    # ``hold_unreadable`` so run() sends nothing from this schedule this tick.
    # The next tick that reads the store cleanly settles it either way.
    holding, hold_error = read_hold(store, appt_id)
    if hold_error and not _quiet_hold_errors:
        log_hold_read_failure(now, appt_id, hold_error)
    if existing:
        touches = existing.get("touches", [])
        rearmed = _rearm_touches(appointment, touches, now, a2p=a2p)
        existing["appointment"] = _merge_snapshot(existing.get("appointment"), appointment)
        if holding is not None:
            existing["held"] = holding
        elif hold_error is None and existing.get("held"):
            existing.pop("held", None)
        if rearmed:
            existing["touches"] = touches
            existing.pop("superseded_by", None)
            existing["rearmed_at"] = now.isoformat()
        store.set(key, existing)
        return {"key": key, "created": False, "rearmed": rearmed, "touches": touches, "cancelled": cancelled,
                "held": holding, "hold_unreadable": hold_error}
    stale = _staleness(store, appointment, now, cold_start)
    # A reschedule: GHL's dateAdded (booked_at) does not move when the lead
    # moves the call, so the booking moment the R2 six-hour rule measures from
    # is now, when the new time was chosen.
    booked = now if stale.get("reason") == "rescheduled" else None
    touches = [t.to_dict() for t in schedule_for(appointment, now, a2p=a2p, stale_booking=stale["stale"],
                                                  booked=booked)]
    rec = {
        "appointment": _appointment_snapshot(appointment),
        "scheduled_at": now.isoformat(),
        "first_seen": now.isoformat(),
        "freshness": stale,
        "touches": touches,
    }
    if holding is not None:
        rec["held"] = holding
    elif hold_error:
        rec["held"] = {"reason": "hold_unreadable", "provisional": True, "at": now.isoformat(),
                       "error": hold_error}
    store.set(key, rec)
    return {"key": key, "created": True, "rearmed": False, "touches": touches, "cancelled": cancelled,
            "freshness": stale, "held": holding, "hold_unreadable": hold_error}


def _rearm_touches(appointment: Dict[str, Any], touches: List[Dict[str, Any]], now: datetime,
                   a2p: Optional[bool] = None) -> bool:
    """Bring back the touches of a schedule that was superseded and is now the
    live one again. Anything already sent stays sent."""
    dead = [t for t in touches if t.get("skipped") and t.get("skip_reason") == "rescheduled"]
    if not dead:
        return False
    # coming back to a slot this appointment already used IS a reschedule, so
    # the T+0 copy is about a time the lead just chose: never stale.
    fresh = {t.key: t for t in schedule_for(appointment, now, a2p=a2p, stale_booking=False, booked=now)}
    for t in touches:
        if not (t.get("skipped") and t.get("skip_reason") == "rescheduled"):
            continue
        new = fresh.get(t.get("key"))
        if new is None:
            continue
        t.update(new.to_dict())
    return True


def _appointment_snapshot(appointment: Dict[str, Any]) -> Dict[str, Any]:
    keep = ("id", "contact_id", "opportunity_id", "start_iso", "end_iso", "zoom_link", "email", "phone",
            "niche", "offer", "first_name", "company", "campaign_key", "campaign_id", "lead_tz",
            "reschedule_link", "title", "tags", "confirmed", "booked_at", "ghl_status")
    snap = {k: appointment.get(k) for k in keep if appointment.get(k) is not None}
    if snap.get("start_iso"):
        # one canonical form everywhere: is_confirmed() and mark_confirmed()
        # compare these strings.
        snap["start_iso"] = _normalise_start(snap["start_iso"])
    return snap


def _merge_snapshot(old: Optional[Dict[str, Any]], appointment: Dict[str, Any]) -> Dict[str, Any]:
    """Refresh the stored snapshot from the freshly fetched appointment: tags
    and confirmation state change after booking and must not stay frozen."""
    merged = dict(old or {})
    merged.update(_appointment_snapshot(appointment))
    return merged


# ------------------------------------------------------- approval hold
# A booking made from a reply is on the GHL calendar at CLASSIFICATION time,
# before Lorenzo has seen the approval card: booking.book() creates it with
# toNotify=False precisely so GHL does not mail the prospect an invite he may
# still veto. The engine's own T+0 "Locked in for ..." confirmation is the
# other half of that promise, and it used to go out on the next ten-minute
# tick regardless - ahead of the approval tap, and sometimes after a veto.
#
# The marker is keyed on the appointment id rather than on a schedule key,
# because the schedule can be created from two places: booking.register_booking
# (immediately) and jobs/appointments_tick (from the calendar read, in live,
# where the appointment is visible to the tick whether or not the engine armed
# it). Both go through ensure_scheduled, which stamps ``held`` onto the record
# from this marker, and run() dispatches nothing from a held record.
#
# Fail-closed by construction: a hold that is never released sends nothing.
HOLD_PREFIX = "showrate_hold:"
# A call booked from a reply can get its confirmation from the reply itself.
# approval.send_approved and Mark sent release the hold only after the card
# that KEEPS the booked call has gone out, and say what went out:
#   "approved"         the engine's own unedited draft, which restates exactly
#                      the booked slot (Keep by its recorded intent). The
#                      ladder's own T+0 confirmation would repeat
#                      "Locked in ..." minutes later, so this release skips
#                      it; the reminders anchored to the call still go.
#   "approved_edited"  a body Lorenzo edited (Keep on the Edit page), and
#   "marked_sent"      a reply he sent by hand (Mark sent): the engine did not
#                      write or did not see that text, so it is never taken for
#                      the confirmation and confirm_email stays.
# Any reason not listed here keeps them too. Widget and hand-made bookings are
# never held, so they keep confirm_email.
ENGINE_CONFIRMED_RELEASE_REASONS = ("approved",)
ENGINE_CONFIRMATION_DUPLICATES = ("confirm_email",)
ENGINE_CONFIRMATION_SKIP = "engine_confirmation_sent"


def hold_key(appointment_id: Any) -> str:
    return "%s%s" % (HOLD_PREFIX, appointment_id)


def read_hold(store, appointment_id: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """``(hold, error)``: tells "no marker" apart from "could not read it".

    ``(record, None)`` held; ``(None, None)`` no marker; ``(None, "<error>")``
    the store read failed, so nobody knows. A caller that decides whether the
    prospect may be spoken to must treat the third case as held (fail closed):
    one brief store error used to read as "no hold", and the ten-minute tick
    then dropped ``held`` from the saved schedule for good and mailed the
    "Locked in for ..." confirmation for a call Lorenzo never approved.
    Never raises, and never logs: the caller logs once per tick."""
    if store is None or appointment_id is None:
        return None, None
    try:
        rec = store.get(hold_key(appointment_id))
    except Exception as exc:  # noqa: BLE001
        return None, "%s: %s" % (type(exc).__name__, str(exc)[:200])
    if not rec:
        return None, None
    return (rec if isinstance(rec, dict) else {"reason": str(rec)}), None


# One warning per tick for hold-read failures (keyed on the tick's ``now``):
# a store outage fails every read in the tick, and one line says it.
_HOLD_READ_LOGGED = {"tick": None}  # type: Dict[str, Any]


def log_hold_read_failure(now: Any, appointment_id: Any, error: str) -> None:
    tick = now.isoformat() if hasattr(now, "isoformat") else str(now)
    if _HOLD_READ_LOGGED.get("tick") == tick:
        logger.debug("show-rate hold unreadable for %s: %s", appointment_id, error)
        return
    _HOLD_READ_LOGGED["tick"] = tick
    logger.warning("could not read the show-rate hold for %s (treated as held; nothing is sent to it "
                   "this tick): %s", appointment_id, error)


def held_record(store, appointment_id: Any) -> Optional[Dict[str, Any]]:
    """The hold on this appointment, or None. Never raises.

    None also on a read error. Anything deciding whether a prospect may be
    contacted uses ``read_hold`` instead and treats the error as held."""
    rec, error = read_hold(store, appointment_id)
    if error:
        logger.warning("could not read the show-rate hold for %s: %s", appointment_id, error)
    return rec


def is_held(store, appointment_id: Any) -> bool:
    return held_record(store, appointment_id) is not None


def hold(store, appointment_id: Any, reason: str = "awaiting_approval", now: Optional[datetime] = None,
         meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Freeze every S4 touch for this appointment until ``release_hold``.

    Written BEFORE the schedule is created, so there is no window in which a
    concurrent tick can dispatch the T+0 confirmation. Any schedule that
    already exists is stamped too, for the reschedule case.
    """
    rec = {"reason": reason, "at": (slots.to_tz(now, TZ).isoformat() if now is not None else None)}
    if meta:
        rec.update(meta)
    store.set(hold_key(appointment_id), rec)
    for key in store.keys("showrate:%s:" % appointment_id):
        store.mutate(key, lambda r, _rec=rec: dict(r or {}, held=_rec), default={})
    return rec


def clear_hold(store, appointment_id: Any, reason: str = "cleared") -> bool:
    """Drop the marker without arming anything (the cancel/veto path)."""
    existing, error = read_hold(store, appointment_id)
    if error:
        # unknown is not "no marker": try the delete anyway, so a marker that
        # is there does not outlive its release. A delete that also fails
        # leaves the marker, which only keeps the ladder quiet (fail closed).
        try:
            store.delete(hold_key(appointment_id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not clear the show-rate hold for %s (read: %s; delete: %s)",
                           appointment_id, error, exc)
            return False
        return True
    if existing is None:
        return False
    store.delete(hold_key(appointment_id))
    return True


# A release whose marker could not be removed (re-review r3 item 2). Both the
# marker read and its delete failing used to return released=False with no
# error: nobody was told, and the next tick re-held the approved call's
# reminders from the surviving marker, for good. Now release_hold returns an
# error (approval.send_approved alerts Lorenzo on it), writes one
# "show_rate_release_failed" Job_Log row per call, and records the release
# here; run() retries it at the start of every tick until it goes through.
RELEASE_PENDING_PREFIX = "showrate_release_pending:"


def release_pending_key(appointment_id: Any) -> str:
    return "%s%s" % (RELEASE_PENDING_PREFIX, appointment_id)


def _clear_hold_checked(store, appointment_id: Any) -> Tuple[bool, Optional[str]]:
    """``(released, error)``. ``(False, None)`` means there was no marker (read
    cleanly); an error means a marker may still be there."""
    existing, error = read_hold(store, appointment_id)
    if error is None and existing is None:
        return False, None
    try:
        store.delete(hold_key(appointment_id))
    except Exception as exc:  # noqa: BLE001
        why = "delete: %s: %s" % (type(exc).__name__, str(exc)[:200])
        return False, ("read: %s; %s" % (error, why)) if error else why
    return True, None


def _record_release_failure(store, appointment_id: Any, now: datetime, reason: str, error: str) -> Dict[str, Any]:
    """Remember a release that did not go through, so run() retries it, and
    write the Job_Log failure row the first time only (once per call). Never
    raises."""
    box = {"new": True, "recorded": False}

    def _note(rec):
        rec = dict(rec) if isinstance(rec, dict) else {}
        box["new"] = not rec
        rec.setdefault("first_at", now.isoformat())
        rec.setdefault("reason", reason)
        rec["appointment_id"] = str(appointment_id)
        rec["attempts"] = int(rec.get("attempts") or 0) + 1
        rec["last_at"] = now.isoformat()
        rec["last_error"] = error
        return rec

    try:
        store.mutate(release_pending_key(appointment_id), _note, default={})
        box["recorded"] = True
    except Exception as exc:  # noqa: BLE001 - the caller's alert is then the only trace besides Job_Log
        logger.error("could not record the pending show-rate release for %s (it will NOT be retried): %s",
                     appointment_id, exc)
    if box["new"] or not box["recorded"]:
        logger.error("the show-rate hold on %s could not be released: %s", appointment_id, error)
        try:
            from shared import job_log

            job_log.log_run("reply_engine.show_rate", "show_rate_release_failed",
                            {"appointment_id": str(appointment_id), "error": error, "reason": reason,
                             "retry_recorded": box["recorded"]})
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not log the failed show-rate release for %s: %s", appointment_id, exc)
    return box


def release_hold(store, appointment_id: Any, now: datetime, a2p: Optional[bool] = None,
                 reason: str = "approved") -> Dict[str, Any]:
    """Start the ladder: the approved confirmation reply is out.

    The T+0 touches are re-anchored to ``now`` rather than to the moment the
    call was booked. An approval that lands three hours after classification
    would otherwise dispatch a confirmation stamped three hours ago, which
    ``dispatch_block_reason`` then drops as ``too_late`` - the lead would get
    the invite and no confirmation at all.

    With ``reason="approved"`` (the engine's own unedited confirming draft is
    out, see ENGINE_CONFIRMED_RELEASE_REASONS) the ladder's own confirmation
    touch is skipped as ``engine_confirmation_sent`` instead
    (ENGINE_CONFIRMATION_DUPLICATES).
    Any other reason ("approved_edited", "marked_sent") re-anchors them and
    they go. A retried release keeps the reason it was recorded with.

    When the marker cannot be removed (its read and its delete both failed, or
    the delete failed), or the schedules cannot be re-anchored, the result
    carries ``error``, one "show_rate_release_failed" Job_Log row is written
    for the call, and the release is recorded under RELEASE_PENDING_PREFIX for
    run() to retry on every later tick. Never raises on a store error.
    """
    now = slots.to_tz(slots.ensure_aware(now, TZ), TZ)
    out = {"appointment_id": str(appointment_id), "released": False, "schedules": [], "rearmed": 0,
           "reason": reason}  # type: Dict[str, Any]
    if store is None or appointment_id is None:
        return out
    released, error = _clear_hold_checked(store, appointment_id)
    out["released"] = released
    try:
        keys = store.keys("showrate:%s:" % appointment_id)
    except Exception as exc:  # noqa: BLE001
        keys = []
        error = "; ".join(e for e in (error, "schedules unreadable: %s" % str(exc)[:200]) if e)
    for key in keys:
        counted = {"n": 0}

        def _release(rec, _counted=counted):
            rec = rec or {}
            rec.pop("held", None)
            appt = rec.get("appointment") or {}
            if not appt.get("start_iso"):
                return rec
            try:
                fresh = {t.key: t for t in schedule_for(appt, now, a2p=a2p, stale_booking=False)}
            except Exception as exc:  # noqa: BLE001 - never lose the release over a render error
                logger.warning("could not re-anchor the held touches for %s: %s", appointment_id, exc)
                return rec
            engine_confirmed = reason in ENGINE_CONFIRMED_RELEASE_REASONS
            for t in rec.get("touches", []):
                if t.get("sent") or t.get("skipped"):
                    continue
                if t.get("template_key") not in RELATIVE_TO_BOOKING:
                    continue
                if engine_confirmed and t.get("template_key") in ENGINE_CONFIRMATION_DUPLICATES:
                    # the approved reply that just went out already said
                    # "Locked in ...": a second confirmation minutes later is
                    # noise.
                    t["skipped"], t["skip_reason"] = True, ENGINE_CONFIRMATION_SKIP
                    continue
                new = fresh.get(t.get("key"))
                if new is None or new.skipped:
                    continue
                t["when_iso"] = new.when_iso
                t["body"] = new.body
                t["subject"] = new.subject
                meta = dict(t.get("meta") or {})
                meta["released_at"] = now.isoformat()
                t["meta"] = meta
                _counted["n"] += 1
            rec["released_at"] = now.isoformat()
            if engine_confirmed:
                rec["engine_confirmation_sent_at"] = now.isoformat()
            return rec

        try:
            store.mutate(key, _release, default={})
        except Exception as exc:  # noqa: BLE001
            error = "; ".join(e for e in (error, "%s not re-armed: %s" % (key, str(exc)[:200])) if e)
            continue
        out["schedules"].append(key)
        out["rearmed"] += counted["n"]
    if error:
        out["error"] = ("the show-rate hold could not be released (%s); the appointments tick retries the release "
                        "every run until it goes through" % error)
        out["retry_recorded"] = _record_release_failure(store, appointment_id, now, reason, error)["recorded"]
    return out


def retry_pending_releases(store, now: datetime, a2p: Optional[bool] = None) -> List[Dict[str, Any]]:
    """Retry every recorded release that did not go through (run() calls this
    first, before any schedule is stamped from a surviving marker). A release
    that now goes through drops its record and tells Lorenzo the reminders
    started after all (he was told to check them by hand). Never raises."""
    out = []  # type: List[Dict[str, Any]]
    try:
        keys = store.keys(RELEASE_PENDING_PREFIX)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not list the pending show-rate releases: %s", exc)
        return out
    for key in keys:
        appointment_id = key[len(RELEASE_PENDING_PREFIX):]
        try:
            rec = store.get(key) or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not read %s: %s", key, exc)
            continue
        res = release_hold(store, appointment_id, now, a2p=a2p, reason=(rec or {}).get("reason") or "approved")
        row = {"appointment_id": appointment_id, "released": res.get("released"), "error": res.get("error"),
               "attempts": int((rec or {}).get("attempts") or 0) + (1 if res.get("error") else 0)}
        out.append(row)
        if res.get("error"):
            continue
        try:
            store.delete(key)
        except Exception as exc:  # noqa: BLE001 - the next retry finds nothing held and deletes it then
            logger.warning("could not drop %s: %s", key, exc)
        logger.info("the show-rate hold on %s was released on a later tick", appointment_id)
        try:
            from shared import notify

            notify.notify("Show-rate reminders started for appointment %s" % appointment_id,
                          "The held reminder ladder for appointment %s could not be released when the "
                          "confirmation went out (first failure %s). It was released on a later tick and the "
                          "reminders now run as normal. Nothing to do."
                          % (appointment_id, (rec or {}).get("first_at") or "time not recorded"),
                          priority="default", tags=["reply-engine", "calendar"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not send the release-recovered note for %s: %s", appointment_id, exc)
    return out


def confirmed_key(appointment_id: str) -> str:
    return "confirmed:%s" % appointment_id


def _current_start_iso(store, appointment_id: str) -> Optional[str]:
    """The start of the newest live schedule for this appointment, if any."""
    best = None
    for key in store.keys("showrate:%s:" % appointment_id):
        rec = store.get(key) or {}
        if rec.get("superseded_by"):
            continue
        start_iso = (rec.get("appointment") or {}).get("start_iso") or key.split(":", 2)[-1]
        if best is None or start_iso > best:
            best = start_iso
    return best


def mark_confirmed(store, appointment_id: str, at: datetime, source: str = "reply_c",
                   start_iso: Optional[str] = None) -> None:
    """Record a C reply. The flag carries the start it refers to, so it does
    not survive a reschedule to a time the lead has never confirmed."""
    if start_iso is None:
        start_iso = _current_start_iso(store, appointment_id)
    # normalise in BOTH branches. is_confirmed() always normalises before
    # comparing, so storing GHL's raw "2026-09-24T20:00:00.000Z" made the two
    # strings differ and the 4 h "text or call them personally" task fired
    # against a lead who had already replied C.
    start_iso = _normalise_start(start_iso)
    store.set(confirmed_key(appointment_id),
              {"at": slots.to_tz(at, TZ).isoformat(), "source": source, "start_iso": start_iso})


def _normalise_start(start_iso: Optional[str]) -> Optional[str]:
    if not start_iso:
        return start_iso
    try:
        return slots.to_tz(slots.parse_iso(start_iso), TZ).isoformat()
    except (ValueError, TypeError):
        logger.warning("could not normalise start_iso %r", start_iso)
        return start_iso


def clear_confirmed(store, appointment_id: str, start_iso: Optional[str] = None) -> bool:
    """Drop a confirmation that does not belong to ``start_iso``."""
    rec = store.get(confirmed_key(appointment_id))
    if not rec:
        return False
    if start_iso is not None and isinstance(rec, dict) and rec.get("start_iso") == start_iso:
        return False
    store.delete(confirmed_key(appointment_id))
    return True


def is_confirmed(store, appointment: Dict[str, Any]) -> bool:
    if appointment.get("confirmed") or appointment.get("confirmed_by_reply"):
        return True
    tags = [str(t).lower() for t in (appointment.get("tags") or [])]
    if "call-confirmed" in tags:
        return True
    rec = store.get(confirmed_key(appointment.get("id")))
    if not rec:
        return False
    if isinstance(rec, dict) and rec.get("start_iso") and appointment.get("start_iso"):
        try:
            want = slots.to_tz(slots.parse_iso(appointment["start_iso"]), TZ).isoformat()
        except (ValueError, TypeError):
            return True
        return rec["start_iso"] == want
    return True


# ------------------------------------------- the retired "reply C" scan
def scan_ghl_confirmations(now: datetime, store, ghl) -> Dict[str, Any]:
    """Retired with the 4 h "has not confirmed" task (section 2, 2026-09-23).

    It read the GHL conversations for a "C" so that task would not fire on a
    lead who had confirmed. Nothing is gated on a confirmation any more (R4
    goes to everyone, and every reminder is a reply in the lead's own thread,
    where the Instantly poller sees the answer), so there is nothing to scan.
    Kept as a no-op with the old result shape because jobs/appointments_tick
    still calls it; drop it once that call is gone. Makes no request."""
    return {"checked": 0, "confirmed": [], "skipped": [], "errors": []}


# --------------------------------------------------------------- dispatch
# Dispatch outcomes of an email (thread_reply.send_lead_email's record mapped
# by _email_outcome). Shaped so the old per-status handling stays safe:
#   "sent" / "would_do"   delivered / recorded in shadow;
#   "error" + retryable   nothing left the process: the touch stays pending and
#                         the next tick tries again (an attempt is counted, up
#                         to MAX_TOUCH_ATTEMPTS; MAX_LATENESS still expires it);
#   "error" + deferred    outside the send window: pending, no attempt counted;
#   HELD + hold "thread"  the thread lookup needs a look (ambiguous or foreign
#                         lead row, broken thread, recipient mismatch): pending,
#                         surfaced as needs_attention for Lorenzo;
#   MAYBE_SENT            the write went out and failed or came back empty: the
#                         email may be in the lead's inbox, so the touch is
#                         closed with an error and NEVER retried automatically.
MAYBE_SENT = "maybe_sent"
THREAD_HOLD = "thread"
THREAD_SUBJECT_REFUSED = "thread_subject_refused"
REPLY_PREFIX = "Re: "


def _email_outcome(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Map thread_reply.send_lead_email's record to a dispatch outcome."""
    from services.reply_engine import thread_reply

    reason = rec.get("reason")
    base = {"transport": rec.get("transport"), "route": rec.get("route"), "lead_key": rec.get("lead_key")}
    if rec.get("shadow"):
        return dict(base, status="would_do", record=rec.get("result"), reason=reason)
    if rec.get("sent"):
        return dict(base, status="sent", response=rec.get("result"), reason=reason)
    if rec.get("maybe_sent"):
        err = (rec.get("result") or {}).get("error") if isinstance(rec.get("result"), dict) else None
        return dict(base, status=MAYBE_SENT, reason=reason, error=err or reason)
    if reason == thread_reply.OUTSIDE_SEND_WINDOW:
        return dict(base, status="error", reason=reason, error=reason, deferred=True, retryable=True)
    if rec.get("needs_attention") or reason in thread_reply.NEEDS_ATTENTION_REASONS:
        return dict(base, status=HELD, reason=reason, hold=THREAD_HOLD)
    if rec.get("retryable"):
        return dict(base, status="error", reason=reason, error=reason, retryable=True)
    # anything this mapping does not know: fail closed, pending and surfaced
    return dict(base, status=HELD, reason=reason or "unknown_transport_outcome", hold=THREAD_HOLD)


def in_thread_subject(store, appointment: Optional[Dict[str, Any]]) -> Optional[str]:
    """The subject the in-thread reply will actually carry
    (cadence.subject_for on the lead row thread_reply.find_thread resolves), or
    None when the email will not go in a thread (no thread: the GHL fallback
    sends the touch's own subject) or the row cannot be resolved (send_lead_email
    then holds and sends nothing). Store reads only."""
    from services.reply_engine import cadence, thread_reply

    try:
        found = thread_reply.find_thread(store, appointment or {})
    except Exception:  # noqa: BLE001 - send_lead_email repeats the lookup and holds on the same error
        return None
    state = found.get("state")
    if state is None:
        return None
    return cadence.subject_for(state)


def thread_subject_problems(subject: str, appointment: Optional[Dict[str, Any]]) -> List[str]:
    """The template gate judges the touch's own subject, which is what a GHL
    fallback email carries. In the thread the reply carries "Re: <the thread's
    subject>" instead, a text the catalogue does not hold, so it gets the same
    checks the cadence gate applies to its "Re: {original_subject}": the copy
    rules for a subject (banned words, figures, "!", no link or address:
    template_gate._subject_problems) and the free-text rule for the thread
    subject itself (template_gate._free_text_ok, the {original_subject} rule).
    Empty when it passes. Fails closed: an error is a problem."""
    appointment = appointment or {}
    try:
        from services.reply_engine import template_gate

        problems = list(template_gate._subject_problems(  # noqa: SLF001 - the gate's own subject rules
            subject, appointment.get("campaign_key") or None, appointment_allow_terms(appointment)))
        if not subject.startswith(REPLY_PREFIX):
            problems.append("thread subject: not a reply subject")
        elif not template_gate._free_text_ok(subject[len(REPLY_PREFIX):]):  # noqa: SLF001
            problems.append("thread subject: fails the original_subject rule")
        return problems
    except Exception as exc:  # noqa: BLE001 - a check that cannot run holds the email
        return ["thread subject check failed: %s" % type(exc).__name__]


def dispatch_touch(touch: Touch, ghl, now: datetime, a2p: Optional[bool] = None, store=None,
                   appointment: Optional[Dict[str, Any]] = None, kind: Optional[str] = None,
                   slots_text: Optional[str] = None, instantly=None) -> Dict[str, Any]:
    """Send one touch. Never raises for a missing token; returns
    {'status': 'would_do'|'sent'|'skipped'|'held'|'error'|'maybe_sent', ...}.

    The one choke point for every show-rate and no-show message. After the
    sender and placeholder checks:

    1. opt-out: a lead row carrying the sticky opt-out marker skips the touch
       (``opt_out``, burned); a store that cannot be read holds it;
    2. CT3 template gate, email only (tasks are Lorenzo's): the exact subject
       and body must be an approved template with only its placeholders filled
       (template_gate.appointment_touch_verdict, with the lead's own values
       allowed and the rendered values bound). A refusal is
       ``{"status": "held", "reason": ...}``: the touch stays pending;
    3. an email that will go in the lead's thread carries "Re: <thread
       subject>", not the touch's subject: that subject gets the gate's
       subject checks too (thread_subject_problems), or the email is held
       (``thread_subject_refused``);
    4. the email goes through thread_reply.send_lead_email (``instantly`` is
       the Instantly client; the GHL client is the fallback for a lead with no
       thread) and its record is mapped by _email_outcome (see the table
       above). A task is still a GHL task.

    An SMS touch (none is scheduled any more) is skipped ``sms_removed``.
    ``kind`` is "show_rate" or "no_show" (default: from the template key);
    ``slots_text`` is the slot line a no-show touch rendered; ``a2p`` is
    accepted for old callers and ignored."""
    if os.environ.get(SENDER_ENV, "engine").strip().lower() == "ghl":
        # the published GHL workflow carries the sequence; the engine only schedules and logs
        return {"status": "skipped", "reason": "sender_is_ghl"}
    if touch.channel == "sms":
        # section 2 (2026-09-23): email only. A legacy SMS touch still in a
        # store is closed, never sent.
        return {"status": "skipped", "reason": "sms_removed"}
    if touch.channel == "email" and settings.is_live() and has_unresolved_placeholder(touch.body):
        return {"status": "skipped", "reason": "unresolved_placeholder"}
    if touch.channel == "task" and not touch.contact_id:
        # an email needs no GHL contact when it goes in the lead's thread;
        # thread_reply asks for one only for the GHL fallback
        return {"status": "skipped", "reason": "no_contact_id"}
    try:
        opted_out = lead_opted_out(store, appointment, touch.appointment_id)
    except Exception as exc:  # noqa: BLE001 - an unreadable row may hide an opt-out
        logger.warning("could not read the lead row for %s, holding it: %s", touch.key, type(exc).__name__)
        return {"status": HELD, "reason": "lead_row_unreadable", "template_id": touch.template_id,
                "kind": kind or template_kind(touch.template_key)}
    if opted_out:
        return {"status": "skipped", "reason": "opt_out"}
    kind = kind or template_kind(touch.template_key)
    if touch.channel in GATED_CHANNELS:
        verdict = gate_touch(touch, appointment, kind=kind, slots_text=slots_text)
        if not verdict.allowed:
            return {"status": HELD, "reason": verdict.reason, "template_id": verdict.template_id,
                    "kind": kind, "verdict": verdict.to_record()}
    if touch.channel == "email":
        subject = in_thread_subject(store, appointment)
        if subject is not None:
            problems = thread_subject_problems(subject, appointment)
            if problems:
                logger.warning("holding %s: the thread's subject fails the subject checks (%s)", touch.key,
                               "; ".join(problems))
                return {"status": HELD, "reason": THREAD_SUBJECT_REFUSED, "template_id": touch.template_id,
                        "kind": kind, "problems": problems}
        try:
            from services.reply_engine import thread_reply

            rec = thread_reply.send_lead_email(store, appointment or {}, touch.subject or "", touch.body, now,
                                               instantly=instantly, ghl=ghl, contact_id=touch.contact_id)
        except Exception as exc:  # noqa: BLE001 - send_lead_email catches its writes; this is a lookup bug
            logger.error("dispatch %s failed before any send: %s", touch.key, exc)
            return {"status": "error", "error": str(exc), "retryable": True}
        return _email_outcome(rec)
    if touch.channel != "task":
        return {"status": "skipped", "reason": "unknown_channel"}
    try:
        due = slots.to_tz(slots.parse_iso(touch.when_iso), TZ).isoformat()
        res = ghl.create_task(touch.contact_id, touch.subject or touch.template_key, due, body=touch.body)
    except Exception as exc:  # noqa: BLE001
        logger.error("dispatch %s failed: %s", touch.key, exc)
        return {"status": "error", "error": str(exc)}
    if res is None:
        return {"status": "skipped", "reason": "ghl_token_missing"}
    if isinstance(res, dict) and res.get("shadow"):
        return {"status": "would_do", "record": res}
    return {"status": "sent", "response": res}


def _text_to_html(text: str) -> str:
    """The HTML body of the GHL fallback email (thread_reply keeps its own
    copy so its send path has no late import; the two must stay equal)."""
    esc = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return "<p>%s</p>" % esc.replace("\n\n", "</p><p>").replace("\n", "<br>")


def cancel_schedule(store, key: str, reason: str = "cancelled") -> int:
    """Mark every pending touch of one schedule skipped. Used when the GHL
    appointment is cancelled or deleted. Goes through store.mutate so a
    concurrent per-touch write cannot undo it."""
    counted = {"n": 0}

    def _apply(rec):
        rec = rec or {}
        for t in rec.get("touches", []):
            if not t.get("sent") and not t.get("skipped"):
                t["skipped"], t["skip_reason"] = True, reason
                counted["n"] += 1
        rec["cancelled"] = reason
        return rec

    store.mutate(key, _apply, default={})
    return counted["n"]


def _touch_claim_key(touch_key: str) -> str:
    return "touch_sent:%s" % touch_key


def _stays_pending(out: Dict[str, Any]) -> bool:
    """True when this dispatch outcome leaves the touch to be retried (a CT3
    template hold, a thread hold and a send-window deferral included). Never
    for MAYBE_SENT: its claim stays, so no later tick can send it again."""
    if out.get("status") in ("error", HELD):
        return True
    return out.get("status") == "skipped" and out.get("reason") in RETRYABLE_SKIP_REASONS


def _persist_touch(store, key: str, touch_key: str, patch: Dict[str, Any]) -> None:
    """Fold one touch's outcome into the record under the store lock.

    Writing back a record read before the network call loses every change made
    in between (a cancellation from the reply webhook, another worker's touch).
    """
    def _apply(rec):
        rec = rec or {}
        for t in rec.get("touches", []):
            if t.get("key") == touch_key:
                t.update(patch)
                break
        return rec

    store.mutate(key, _apply, default={})


def dispatch_block_reason(touch: Touch, start: Optional[datetime], now: datetime) -> Optional[str]:
    """Why this due touch must NOT go out now, or None.

    Staleness used to be decided only at scheduling time, so a touch held back
    by a GHL outage (or by a retryable skip) was delivered whenever the outage
    ended: "Confirmed: Wed, Sep 23 at 3:00 CT" an hour after the call ended,
    "Tomorrow at 2:00 CT, still good?" on the morning of the call, and the
    pre-read ten minutes into a call booked inside 15 minutes.
    """
    if start is not None and now >= start:
        # nothing in the S4 sequence is worth sending once the call has begun,
        # confirmations and pre-reads included.
        return "appointment_started"
    limit = MAX_LATENESS.get(touch.template_key)
    if limit is not None and (now - touch.when()) > limit:
        return "too_late"
    return None


def run(
    now: datetime,
    store,
    ghl,
    a2p: Optional[bool] = None,
    appointments: Optional[List[Dict[str, Any]]] = None,
    active_ids: Optional[Any] = None,
    window: Optional[Any] = None,
    instantly=None,
) -> Dict[str, Any]:
    """Send every due show-rate touch. Returns a summary dict.

    ``instantly`` is the Instantly client the in-thread emails go out through
    (thread_reply.send_lead_email); ``ghl`` is the GHL fallback for a lead
    with no thread. In shadow neither makes a request.

    If ``appointments`` is given they are (re)scheduled first; otherwise only
    schedules already in the store are processed.

    ``active_ids`` is the set of appointment ids the caller just read from GHL
    and found alive (not cancelled). When it is given, a stored schedule whose
    appointment is no longer in that set, and whose start falls inside
    ``window`` (a ``(start, end)`` pair of datetimes), is cancelled: otherwise a
    cancelled call keeps getting reminders. The caller must pass ``None`` when
    the GHL read failed, so an outage is never read as "everything cancelled".
    """
    now = slots.to_tz(slots.ensure_aware(now, TZ), TZ)
    # "held": schedules awaiting Lorenzo's approval card; "held_template":
    # touches the CT3 template gate refused (they stay pending);
    # "needs_attention": emails the thread lookup held (pending, for Lorenzo);
    # "deferred": emails due outside the send window (pending);
    # "maybe_sent": emails that may have gone out and are never retried (also
    # counted in "errors" so the tick reports partial).
    summary = {"sent": [], "would_do": [], "skipped": [], "errors": [], "scheduled": [],
               "cancelled": [], "rearmed": [], "held": [], "held_template": [], "needs_attention": [],
               "deferred": [], "maybe_sent": []}  # type: Dict[str, List[Any]]
    fresh = {}  # type: Dict[str, Dict[str, Any]]
    # one claim for the whole run: see claim_bootstrap()
    cold_start = claim_bootstrap(store, now) if appointments else False
    if cold_start:
        summary["cold_start"] = True
    # A release that could not remove its marker is retried before any
    # schedule is stamped from that marker (re-review r3 item 2).
    retried = retry_pending_releases(store, now, a2p=a2p)
    if retried:
        summary["release_retried"] = retried
    unreadable = {}  # type: Dict[str, str]
    for appt in appointments or []:
        fresh[str(appt.get("id"))] = appt
        res = ensure_scheduled(store, appt, now, a2p=a2p, cold_start=cold_start, _quiet_hold_errors=True)
        if res.get("hold_unreadable"):
            unreadable[res["key"]] = res["hold_unreadable"]
        if res["created"]:
            summary["scheduled"].append(res["key"])
        if res.get("rearmed"):
            summary["rearmed"].append(res["key"])
        summary["cancelled"].extend(res["cancelled"])
    if unreadable:
        # once per tick, however many reads failed
        logger.warning("could not read the show-rate hold for %d schedule(s) this tick (%s); treated as held, "
                       "nothing sent from them: %s", len(unreadable), ", ".join(sorted(unreadable)),
                       next(iter(unreadable.values())))
        summary["hold_unreadable"] = sorted(unreadable)
    for key in store.keys("showrate:"):
        rec = store.get(key) or {}
        if rec.get("cancelled"):
            continue
        if key in unreadable:
            # the marker could not be read: whether this call is approved is
            # unknown, so nothing goes to the prospect from it this tick.
            summary.setdefault("held", []).append(key)
            continue
        if rec.get("held"):
            # awaiting Lorenzo's approval: the touches stay pending, unburned,
            # and release_hold() re-anchors the T+0 ones when the reply goes out.
            summary.setdefault("held", []).append(key)
            continue
        appt = rec.get("appointment", {})
        # prefer the freshly fetched appointment: tags and status move after booking
        live = fresh.get(str(appt.get("id")))
        if live is not None:
            appt = _merge_snapshot(appt, live)
        start = slots.parse_iso(appt.get("start_iso")) if appt.get("start_iso") else None
        if _is_cancelled(appt, start, active_ids, window):
            n = cancel_schedule(store, key, "cancelled")
            if n:
                summary["cancelled"].append(key)
            continue
        for raw in rec.get("touches", []):
            if raw.get("sent") or raw.get("skipped"):
                continue
            touch = Touch.from_dict(raw)
            when = touch.when()
            if when > now:
                continue
            entry = {"key": touch.key, "channel": touch.channel, "template": touch.template_key, "when": touch.when_iso}
            if touch.template_key not in SEQUENCE_KEYS:
                # a touch from the retired sequence (SMS legs, the pre-read, the
                # 4 h task) still in a store written before 2026-09-23: closed.
                raw["skipped"], raw["skip_reason"] = True, "retired_template"
                _persist_touch(store, key, touch.key, {"skipped": True, "skip_reason": "retired_template"})
                summary["skipped"].append(dict(entry, reason="retired_template"))
                continue
            blocked = dispatch_block_reason(touch, start, now)
            if blocked is not None:
                raw["skipped"], raw["skip_reason"] = True, blocked
                _persist_touch(store, key, touch.key, {"skipped": True, "skip_reason": blocked})
                summary["skipped"].append(dict(entry, reason=blocked))
                continue
            # resolve the contact id from the REFRESHED snapshot, not from the
            # Touch: a schedule created before GHL returned a contact id used
            # to burn every touch with skip_reason no_contact_id.
            touch.contact_id = appt.get("contact_id") or touch.contact_id
            raw["contact_id"] = touch.contact_id
            # CT3 flag 3: the copy is re-rendered and re-stamped now, from the
            # freshest snapshot, so the gate judges today's template.
            if refresh_copy(touch, appt, now):
                raw.update({"subject": touch.subject, "body": touch.body, "template_id": touch.template_id,
                            "template_hash": touch.template_hash})
            claim = _touch_claim_key(touch.key)
            if not store.set_if_absent(claim, {"at": now.isoformat(), "template": touch.template_key}):
                # a previous run dispatched this and died before it could write
                # the sent flag. Never send the same message twice.
                raw["sent"], raw["sent_at"] = True, now.isoformat()
                raw["result"] = {"status": "skipped", "reason": "already_dispatched"}
                _persist_touch(store, key, touch.key,
                               {"sent": True, "sent_at": now.isoformat(), "result": raw["result"]})
                summary["skipped"].append(dict(entry, reason="already_dispatched"))
                continue
            out = dispatch_touch(touch, ghl, now, a2p=a2p, store=store, appointment=appt, kind="show_rate",
                                 instantly=instantly)
            _record_result(raw, out, entry, summary, now)
            if out.get("status") == HELD and out.get("hold") == THREAD_HOLD:
                note_thread_hold(raw, out, entry, now)
            elif out.get("status") == HELD:
                note_template_hold(store, raw, out, now)
            else:
                if raw.get("template_hold"):
                    raw["template_hold"] = None
                if raw.get("thread_hold"):
                    raw["thread_hold"] = None
            if _stays_pending(out):
                store.delete(claim)  # retryable: let the next tick try again
            # persist immediately: a crash after a send must never re-send it
            _persist_touch(store, key, touch.key, {k: raw.get(k) for k in
                                                   ("sent", "sent_at", "result", "skipped", "skip_reason",
                                                    "attempts", "contact_id", "subject", "body", "template_id",
                                                    "template_hash", "template_hold", "thread_hold")})
    return summary


def _is_cancelled(appt: Dict[str, Any], start, active_ids, window) -> bool:
    if appt.get("cancelled") or str(appt.get("ghl_status") or "").lower() in ("cancelled", "canceled"):
        return True
    if active_ids is None or start is None:
        return False
    if window is not None and not (window[0] <= start <= window[1]):
        return False  # outside the window we read: we know nothing about it
    return str(appt.get("id")) not in active_ids


def _record_result(raw: Dict[str, Any], out: Dict[str, Any], entry: Dict[str, Any],
                   summary: Dict[str, List[Any]], now: datetime) -> None:
    """Fold one dispatch result into the touch record and the summary.

    A retryable outcome (no GHL token, nothing left the process) leaves the
    touch PENDING and counts as an error, so a token rotation does not silently
    destroy an appointment's whole sequence one touch at a time. A send-window
    deferral is pending without an attempt. MAYBE_SENT closes the touch with
    the error: it may be in the lead's inbox, so it is never retried.
    """
    if out.get("transport"):
        entry["transport"] = out["transport"]
    if out["status"] in ("sent", "would_do"):
        raw["sent"], raw["sent_at"], raw["result"] = True, now.isoformat(), out
        entry["shadow"] = out["status"] == "would_do"
        summary[out["status"]].append(entry)
        return
    if out["status"] == HELD and out.get("hold") == THREAD_HOLD:
        entry["reason"] = out.get("reason")
        summary.setdefault("needs_attention", []).append(entry)
        return
    if out["status"] == HELD:
        record_held(entry, out, summary)
        return
    if out["status"] == MAYBE_SENT:
        raw["skipped"], raw["skip_reason"], raw["result"] = True, MAYBE_SENT, out
        entry["reason"], entry["error"] = MAYBE_SENT, out.get("error")
        summary.setdefault("maybe_sent", []).append(entry)
        summary["errors"].append(entry)
        logger.error("%s may have been delivered (%s); closed, never retried: check the lead's thread or GHL "
                     "conversation by hand", entry.get("key"), out.get("reason"))
        try:
            from shared import job_log

            job_log.log_run("reply_engine.show_rate", "show_rate_maybe_sent",
                            {"touch": entry.get("key"), "template": entry.get("template"),
                             "transport": out.get("transport"), "reason": out.get("reason")})
        except Exception as exc:  # noqa: BLE001 - the summary still carries it
            logger.warning("could not log the maybe-sent touch %s: %s", entry.get("key"), exc)
        return
    if out["status"] == "error" and out.get("deferred"):
        raw["result"] = out
        entry["reason"] = out.get("reason")
        summary.setdefault("deferred", []).append(entry)
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


def note_thread_hold(raw: Dict[str, Any], out: Dict[str, Any], entry: Dict[str, Any], now: datetime) -> None:
    """Remember a thread hold on the touch (reason and since when). The touch
    stays pending until the data is fixed or MAX_LATENESS expires it; the
    first tick that meets a new reason writes one Job_Log row, later ticks
    only count it in the summary's needs_attention."""
    prev = raw.get("thread_hold") or {}
    raw["thread_hold"] = {"reason": out.get("reason"), "transport": out.get("transport"),
                          "lead_key": out.get("lead_key"), "since": prev.get("since") or now.isoformat()}
    if prev.get("reason") == out.get("reason"):
        return
    logger.warning("holding %s: the lead's thread needs a look (%s)", entry.get("key"), out.get("reason"))
    try:
        from shared import job_log

        job_log.log_run("reply_engine.show_rate", "show_rate_needs_attention",
                        {"touch": entry.get("key"), "template": entry.get("template"), "reason": out.get("reason"),
                         "lead_key": out.get("lead_key")})
    except Exception as exc:  # noqa: BLE001 - the summary still carries it
        logger.warning("could not log the thread hold on %s: %s", entry.get("key"), exc)


def record_held(entry: Dict[str, Any], out: Dict[str, Any], summary: Dict[str, List[Any]]) -> None:
    """A CT3 template hold: the touch stays pending, no attempt is counted
    (a hold is not a failure of the touch), and the summary names the template
    id and the gate's reason, never the copy."""
    entry["reason"] = out.get("reason")
    entry["template_id"] = out.get("template_id")
    summary.setdefault("held_template", []).append(entry)


def _record_retry(raw: Dict[str, Any], out: Dict[str, Any], entry: Dict[str, Any],
                  summary: Dict[str, List[Any]], error: Any) -> None:
    """Leave the touch pending for the next tick, but only up to
    MAX_TOUCH_ATTEMPTS: a permanently broken contact used to retry forever."""
    attempts = int(raw.get("attempts") or 0) + 1
    raw["attempts"], raw["result"] = attempts, out
    entry["error"] = error
    entry["attempts"] = attempts
    if attempts >= MAX_TOUCH_ATTEMPTS:
        raw["skipped"], raw["skip_reason"] = True, "retry_exhausted"
        entry["reason"] = "retry_exhausted"
    summary["errors"].append(entry)


def pending_touches(store, appointment_id: Optional[str] = None) -> List[Dict[str, Any]]:
    prefix = "showrate:%s:" % appointment_id if appointment_id else "showrate:"
    out = []
    for key in store.keys(prefix):
        for t in (store.get(key) or {}).get("touches", []):
            if not t.get("sent") and not t.get("skipped"):
                out.append(t)
    return sorted(out, key=lambda t: t["when_iso"])


# --------------------------------------------------------- scheduled entrypoint
def appointments_tick(now=None, store=None, dry_run: bool = False) -> Dict[str, Any]:
    """Zero-argument entrypoint for the Modal ``appointments_tick`` schedule.

    ``services/reply_engine/modal_app.py`` looks for
    ``show_rate.appointments_tick`` and logged ``entrypoint_missing`` because the
    run body lives in ``jobs/appointments_tick.py``. This wrapper joins them:
    same GHL calendar read, same lock file, same shared store, same Job_Log row,
    so the scheduled tick and ``python3 -m jobs.appointments_tick`` are the same
    run. It never raises: a scheduled tick that dies takes the schedule's next
    run with it only if the exception escapes, so failures come back as
    ``{"status": "error"}`` and a Job_Log row.
    """
    from datetime import datetime, timezone

    from shared import job_log, slots as slot_rules
    from shared.ghl import GHL
    from shared.settings import TZ
    from shared.store import get_store

    from jobs import appointments_tick as job

    if dry_run:
        # the parameter used to be accepted and never read, so a caller passing
        # dry_run=True in a live-configured process performed the full live
        # run: confirmations sent, appointment statuses flipped.
        job._force_shadow()
    try:
        if now is None:
            ts = datetime.now(timezone.utc).astimezone(TZ)
        else:
            # accept an ISO string as well as a datetime: ensure_aware() used to
            # be handed the string directly and raised AttributeError before the
            # try block, so the "it never raises" contract did not hold.
            parsed = slot_rules.parse_iso(now) if isinstance(now, str) else now
            ts = slot_rules.to_tz(slot_rules.ensure_aware(parsed), TZ)
    except (ValueError, TypeError, AttributeError) as exc:
        logger.error("appointments_tick got an unusable now=%r: %s", now, exc)
        job_log.log_run(job.JOB, "error", {"error": "bad_now: %s" % exc})
        return {"status": "error", "error": "bad_now: %s" % exc}
    store = store if store is not None else get_store()
    ghl = GHL()
    # the scheduled tick must do exactly what `python3 -m jobs.appointments_tick`
    # does, interest 3 on a held call included
    instantly = None
    try:
        from shared.instantly import default_client
        instantly = default_client()
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not build the Instantly client for the tick: %s", exc)
    try:
        fetched = job.fetch_appointments(ghl, ts, None)
        with job._run_lock():
            result = job.tick(ts, store, ghl, fetched["appointments"],
                              active_ids=fetched.get("active_ids"), window=fetched.get("window"),
                              cancelled=fetched.get("cancelled"), instantly=instantly)
        result["source"] = fetched["source"]
        result["read_error"] = fetched.get("error")
        result["status"] = "partial" if fetched.get("error") else "ok"
        job_log.log_run(job.JOB, result["status"], {
            "source": result["source"], "read_error": result["read_error"],
            "appointments": result["appointments"], "show_rate": result["show_rate"],
            "recovery": result["recovery"], "pending_touches": result["pending_touches"],
            "held_template": result.get("held_template") or {},
        })
        return result
    except Exception as exc:  # noqa: BLE001 - a scheduled tick reports, it does not crash the app
        logger.exception("appointments_tick failed")
        job_log.log_run(job.JOB, "error", {"error": str(exc)})
        return {"status": "error", "error": str(exc)}
    finally:
        try:
            ghl.close()
        except Exception:  # noqa: BLE001
            pass
        if instantly is not None:
            try:
                instantly.close()
            except Exception:  # noqa: BLE001
                pass
