"""Booking without Lorenzo's hands (Blueprint S3).

match_reply_to_slot(text, offered_slots, now)  -> Optional[datetime]  (CT)
evaluate_reply(text, offered_slots, now, ...)  -> BookingMatch (status + counter-proposal)
book(state, slot, ghl, instantly, now=...)      -> BookingResult (guarded writes + confirmation Draft)

Rules (offers.md rule 2, Blueprint S2/S3): a proposed time is bookable when it
is Mon-Fri, inside 12:00-18:00 CT, at least 4 hours out, within the next 5
business days AND free on the calendar. A time that matches a slot we offered is
accepted unless the calendar has moved on since. "Any day 3-6pm ET" style windows
resolve to the earliest compliant slot inside the window. An auto-responder never
proposes a time, whatever dates its body contains.

Availability is the part that used to be missing: with ``free_slots=None`` the
verdict is flagged ``verified=False`` (it was judged against a synthetic grid,
not Lorenzo's calendar) and known bookings from config/ids.json are treated as
busy. ``book()`` refuses to write an unverified or busy slot, refuses to confirm
an appointment GHL did not actually create, and cancels the previous event when
a booked lead is rescheduled. Every refusal comes back as a BookingResult whose
draft carries a problem, so approval.send_approved blocks it and Lorenzo decides
instead of a prospect being told about a call that does not exist.

Every write (GHL appointment, opportunity stage, Instantly interest status)
goes through the shared clients, which call settings.guard_write first: in
MODE=shadow each is a would_do record and no HTTP request is made.
"""
import dataclasses
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

from shared import settings
from shared import slots as slot_rules
from shared.settings import TZ, guard_write

from services.reply_engine import cadence
from services.reply_engine.cadence import Draft, _field, company_of, first_name_of, niche_and_offer, subject_for

logger = logging.getLogger("reply_engine.booking")

SLOT_MINUTES = slot_rules.SLOT_MINUTES
INTEREST_MEETING_BOOKED = 2  # config/ids.json interest_status_codes
BUFFER_MINUTES = 15  # Discovery Call buffer (config/ids.json), applied around known bookings

# Problems that make a confirmation draft unsendable: approval.send_approved
# refuses any draft with problems, so these route the reply to Lorenzo's card
# instead of telling a prospect a call exists when it does not.
SLOT_NOT_VERIFIED = "slot_not_verified"
SLOT_ALREADY_TAKEN = "slot_already_taken"
APPOINTMENT_NOT_CREATED = "appointment_not_created"

# Status vocabulary for BookingMatch
OFFERED_SLOT_MATCH = "offered_slot_match"
VALID_SLOT = "valid_slot"
WINDOW_EARLIEST = "window_earliest"
WINDOW_NO_FIT = "window_no_fit"
OUTSIDE_WINDOW = "outside_window"
WEEKEND = "weekend"
TOO_SOON = "too_soon"
BEYOND_HORIZON = "beyond_horizon"
SLOT_TAKEN = "slot_taken"
NO_TIME = "no_time"
BOOKABLE = (OFFERED_SLOT_MATCH, VALID_SLOT, WINDOW_EARLIEST)


@dataclasses.dataclass
class BookingMatch(object):
    slot: Optional[datetime]                 # bookable slot in CT, or None
    status: str
    proposed: Optional[datetime] = None      # what the lead asked for (CT), if parseable
    reason: str = ""
    counter_slots: List[datetime] = dataclasses.field(default_factory=list)
    lead_tz: Optional[str] = None
    window: Optional[Tuple[int, int, str]] = None  # (start_hour, end_hour, tz name) in the lead's tz
    slots_source: str = "provided"   # provided | default_grid
    verified: bool = True            # False: judged against a synthetic grid, not Lorenzo's calendar

    @property
    def bookable(self) -> bool:
        return self.slot is not None and self.status in BOOKABLE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slot": self.slot.isoformat() if self.slot else None,
            "status": self.status,
            "proposed": self.proposed.isoformat() if self.proposed else None,
            "reason": self.reason,
            "counter_slots": [c.isoformat() for c in self.counter_slots],
            "lead_tz": self.lead_tz,
            "window": list(self.window) if self.window else None,
            "slots_source": self.slots_source,
            "verified": self.verified,
        }


@dataclasses.dataclass
class BookingResult(object):
    slot: datetime
    draft: Any                                # Draft (confirmation text, for Lorenzo's approval)
    contact_id: Optional[str]
    appointment: Optional[Dict[str, Any]]
    opportunity: Optional[Dict[str, Any]]
    interest_status: Optional[Dict[str, Any]]
    zoom_not_connected: bool
    zoom_link: Optional[str]
    shadow: bool
    records: List[Dict[str, Any]] = dataclasses.field(default_factory=list)
    problems: List[str] = dataclasses.field(default_factory=list)
    # The call IS on the calendar but a later pipeline write (opportunity
    # stage, Instantly interest) raised: "booked, pipeline update failed",
    # not a failed booking. Empty when every write went through.
    pipeline_errors: List[str] = dataclasses.field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        d["slot"] = self.slot.isoformat()
        if hasattr(self.draft, "model_dump"):
            d["draft"] = self.draft.model_dump(mode="json")
        return d


# ------------------------------------------------------------ compliance
def _horizon_date(now: datetime):
    return slot_rules.business_days_ahead(slot_rules.to_tz(now), slot_rules.MAX_BUSINESS_DAYS).date()


def compliance(dt: datetime, now: datetime) -> Optional[str]:
    """None when ``dt`` is offerable; else the rule it breaks."""
    ct = slot_rules.to_tz(dt)
    now_ct = slot_rules.to_tz(now)
    if ct.weekday() >= 5:
        return WEEKEND
    minute = ct.hour * 60 + ct.minute
    if minute < slot_rules.SLOT_WINDOW[0] * 60 or minute + SLOT_MINUTES > slot_rules.SLOT_WINDOW[1] * 60:
        return OUTSIDE_WINDOW
    if ct < now_ct + timedelta(hours=slot_rules.MIN_LEAD_HOURS):
        return TOO_SOON
    if ct.date() > _horizon_date(now_ct):
        return BEYOND_HORIZON
    return None


def _keys(items) -> set:
    out = set()
    for it in items or ():
        try:
            out.add(int(slot_rules.parse_iso(it).timestamp()))
        except (ValueError, TypeError):
            continue
    return out


def known_busy_blocks(exclude_email: Optional[str] = None) -> List[Tuple[str, str]]:
    """Bookings we know about without a GHL token (config/ids.json). Owned by
    draft.py; imported lazily so booking still runs if that module is absent.

    ``exclude_email`` drops the blocks that belong to that lead: a lead's own
    call must not make the engine refuse to confirm or move it."""
    try:
        from services.reply_engine import draft as draft_mod  # noqa: WPS433 - optional sibling

        try:
            return list(draft_mod.busy_blocks_from_ids(exclude_email=exclude_email) or [])
        except TypeError:  # older draft.py without exclude_email
            return list(draft_mod.busy_blocks_from_ids() or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("busy_blocks_from_ids unavailable: %s", exc)
        return []


def collides_with_known_booking(slot: datetime, busy_blocks: Optional[List[Tuple[Any, Any]]] = None,
                                exclude_email: Optional[str] = None) -> bool:
    """True when ``slot`` (plus the calendar buffer) overlaps a known booking."""
    start = slot_rules.to_tz(slot)
    end = start + timedelta(minutes=SLOT_MINUTES)
    blocks = known_busy_blocks(exclude_email) if busy_blocks is None else busy_blocks
    for b_start, b_end in blocks or ():
        try:
            bs = slot_rules.to_tz(slot_rules.parse_iso(b_start)) - timedelta(minutes=BUFFER_MINUTES)
            be = slot_rules.to_tz(slot_rules.parse_iso(b_end)) + timedelta(minutes=BUFFER_MINUTES)
        except (ValueError, TypeError):
            continue
        if start < be and end > bs:
            return True
    return False


def _resolve_candidates(now: datetime, free_slots: Optional[List[Any]],
                        exclude: Optional[List[Any]] = None) -> Tuple[List[datetime], str]:
    """Compliant candidates plus where they came from. ``default_grid`` means
    nobody has checked these against Lorenzo's calendar."""
    if free_slots is not None:
        return slot_rules.candidate_slots(free_slots, now, already_offered=exclude), "provided"
    grid = [s for s in cadence.default_slot_grid(now)
            if not collides_with_known_booking(slot_rules.parse_iso(s))]
    return slot_rules.candidate_slots(grid, now, already_offered=exclude), "default_grid"


def _candidates(now: datetime, free_slots: Optional[List[Any]], exclude: Optional[List[Any]] = None) -> List[datetime]:
    return _resolve_candidates(now, free_slots, exclude)[0]


def _counter(cands: List[datetime], proposed: Optional[datetime], count: int = 2) -> List[datetime]:
    """Nearest compliant slots, preferring the day the lead asked for, always
    offered in chronological order ("Thu 5:00 or Thu 5:30", never the reverse)."""
    if not cands:
        return []
    out = []  # type: List[datetime]
    if proposed is not None:
        same_day = [c for c in cands if c.date() == proposed.date()]
        same_day.sort(key=lambda c: abs((c - proposed).total_seconds()))
        # nearest to what they asked for, but read out in clock order so the
        # sentence never says "Thu 5:30 or Thu 5:00"
        out.extend(sorted(same_day[:count]))
    if len(out) < count:
        for c in slot_rules.pick_two([c for c in cands if c not in out]):
            if c not in out:
                out.append(c)
            if len(out) >= count:
                break
    return out[:count]


def _tz_name(tz) -> Optional[str]:
    return getattr(tz, "zone", None) if tz is not None else None


# --------------------------------------------------------------- matching
# A mail signature starts at "-- " on its own line (RFC 3676) or at a run of
# dashes. Nothing below it is the writer proposing a time.
_SIGNATURE_SEP_RE = re.compile(r"\n\s*-{2,}\s*\n")
# An explicitly labelled opening-hours block is the business's hours, not an
# offer of a meeting window.
_OFFICE_HOURS_LABEL_RE = re.compile(
    r"\b(office hours|business hours|hours of operation|opening hours|our hours|we are open|store hours)\b", re.I)
# Automated acknowledgements that OOO_STRONG_RE does not catch, because they
# never say "out of office": they say the mailbox is a formality.
_AUTO_ACK_RE = re.compile(
    r"(responses? to e-?mails? can be expected|e-?mail is a secondary form of communication|"
    r"this e-?mail address is not my primary|is not my primary (channel|e-?mail)|"
    r"this (e-?mail address|inbox|mailbox) is (used|monitored) (for |by )|"
    r"please (utilize|use) the client portal|do not reply to this|this mailbox is not monitored|"
    r"my response time may be delayed|i have limited access to e-?mail)", re.I)


def proposal_region(text: str) -> str:
    """The part of a reply in which a human could be proposing a time.

    Everything from the signature separator down is dropped, and so is an
    explicitly labelled office-hours block. Fixture #23 (Sienna Consulting) is
    the case: an auto-acknowledgement whose signature carries "OFFICE HOURS:
    Mon - Thurs 10am to 2pm", which parsed as an availability window and yielded
    a bookable Tuesday 12:00 for a robot that never proposed anything."""
    body = text or ""
    sig = _SIGNATURE_SEP_RE.search(body)
    if sig:
        body = body[:sig.start()]
    label = _OFFICE_HOURS_LABEL_RE.search(body)
    if label:
        body = body[:label.start()]
    return body


def looks_like_auto_responder(text: str, subject: str = "") -> bool:
    """Out-of-office and unmonitored-mailbox bodies name dates ("I will return
    to the office Monday, 9/21") and office hours ("open 8am-4pm MST") that
    parse as perfectly good meeting times. Today only classify's rule layer
    keeps them out of book(); this is the second layer, so a classifier change
    or a direct call to match_reply_to_slot cannot book a meeting off a robot.

    ``subject`` is the strongest signal but app.py does not pass one, so the
    body has to stand on its own: OOO_STRONG_RE plus the automated
    acknowledgements that never mention an office."""
    body = text or ""
    if _AUTO_ACK_RE.search(body):
        return True
    try:
        from services.reply_engine import classify as classify_mod  # noqa: WPS433 - optional sibling

        if subject and classify_mod.AUTO_SUBJECT_RE.match(subject):
            return True
        return bool(classify_mod.OOO_STRONG_RE.search(body))
    except Exception as exc:  # noqa: BLE001 - classify is another brief's module
        logger.warning("classify auto-reply signals unavailable: %s", exc)
        return bool(re.search(r"\b(out of (the )?office|on (vacation|leave|holiday|pto)|will return to the office|"
                              r"do not reply to this|this mailbox is not monitored|automatic reply)\b", body, re.I))


def evaluate_reply(text: str, offered_slots: Optional[List[Any]], now: datetime,
                   free_slots: Optional[List[Any]] = None, tz=TZ, subject: str = "") -> BookingMatch:
    """Full verdict on a reply that may contain a time.

    ``free_slots=None`` means nobody has checked Lorenzo's calendar: the verdict
    is still returned (so a counter-proposal can be drafted) but it is flagged
    ``verified=False`` and book() refuses to write on it in live mode."""
    top = slot_rules.strip_quoted(text or "")
    lead_tz = slot_rules.detect_tz(top)
    now_ct = slot_rules.to_tz(now, tz)
    offered_keys = _keys(offered_slots)

    if looks_like_auto_responder(top, subject):
        return BookingMatch(slot=None, status=NO_TIME, reason="auto-responder: no human proposed a time",
                            lead_tz=_tz_name(lead_tz), verified=free_slots is not None,
                            slots_source="provided" if free_slots is not None else "default_grid")

    cands, source = _resolve_candidates(now_ct, free_slots)
    verified = source != "default_grid"
    free_keys = _keys(free_slots) if free_slots is not None else set()
    meta = {"lead_tz": _tz_name(lead_tz), "slots_source": source, "verified": verified}

    # An availability window only counts when the writer states it, not when it
    # sits in a signature or under an "OFFICE HOURS" label.
    window = slot_rules.parse_availability_window(proposal_region(top), tz)
    if window is not None:
        start_h, end_h, wtz = window
        fit = []
        for c in cands:
            local = c.astimezone(wtz)
            minute = local.hour * 60 + local.minute
            if minute >= start_h * 60 and minute + SLOT_MINUTES <= end_h * 60:
                fit.append(c)
        if fit:
            return BookingMatch(slot=fit[0], status=WINDOW_EARLIEST, proposed=None,
                                reason="earliest compliant slot inside %02d:00-%02d:00 %s" % (start_h, end_h, _tz_name(wtz)),
                                counter_slots=fit[1:3], window=(start_h, end_h, _tz_name(wtz) or ""), **meta)
        return BookingMatch(slot=None, status=WINDOW_NO_FIT, proposed=None,
                            reason="no free slot inside the window", counter_slots=slot_rules.pick_two(cands),
                            window=(start_h, end_h, _tz_name(wtz) or ""), **meta)

    proposed = slot_rules.parse_proposed_time(top, now_ct, tz)
    if proposed is None:
        return BookingMatch(slot=None, status=NO_TIME, reason="no day and time in the reply", **meta)

    key = int(proposed.timestamp())
    if key in offered_keys and proposed > now_ct:
        # It was compliant when we offered it, but the calendar can have moved on
        # since (Lorenzo booked something by hand, another lead took it).
        if free_slots is not None and key not in free_keys and key not in {int(c.timestamp()) for c in cands}:
            return BookingMatch(slot=None, status=SLOT_TAKEN, proposed=proposed,
                                reason="we offered it, but the calendar is no longer free then",
                                counter_slots=_counter(cands, proposed), **meta)
        return BookingMatch(slot=proposed, status=OFFERED_SLOT_MATCH, proposed=proposed,
                            reason="matches a slot we offered", **meta)

    broken = compliance(proposed, now_ct)
    if broken is None:
        if free_slots is None or key in free_keys or key in {int(c.timestamp()) for c in cands}:
            if free_slots is None and collides_with_known_booking(proposed):
                return BookingMatch(slot=None, status=SLOT_TAKEN, proposed=proposed,
                                    reason="collides with a booking recorded in config/ids.json",
                                    counter_slots=_counter(cands, proposed), **meta)
            return BookingMatch(slot=proposed, status=VALID_SLOT, proposed=proposed,
                                reason="inside 12:00-18:00 CT, 4 h out, within 5 business days", **meta)
        return BookingMatch(slot=None, status=SLOT_TAKEN, proposed=proposed, reason="calendar not free at that time",
                            counter_slots=_counter(cands, proposed), **meta)

    reasons = {
        OUTSIDE_WINDOW: "outside 12:00-18:00 CT",
        WEEKEND: "falls on a weekend",
        TOO_SOON: "less than %d hours out" % slot_rules.MIN_LEAD_HOURS,
        BEYOND_HORIZON: "beyond the next %d business days" % slot_rules.MAX_BUSINESS_DAYS,
    }
    return BookingMatch(slot=None, status=broken, proposed=proposed, reason=reasons[broken],
                        counter_slots=_counter(cands, proposed), **meta)


def match_reply_to_slot(text: str, offered_slots: Optional[List[Any]], now: datetime,
                        free_slots: Optional[List[Any]] = None, subject: str = "") -> Optional[datetime]:
    """Bookable slot (CT) or None. Use evaluate_reply() for the reason and the counter-proposal."""
    return evaluate_reply(text, offered_slots, now, free_slots=free_slots, subject=subject).slot


def _their_time(dt: datetime, lead_tz_name: Optional[str]) -> str:
    """'4:00 ET' when the lead wrote in another timezone; '' otherwise."""
    if not lead_tz_name or lead_tz_name == "America/Chicago":
        return ""
    import pytz

    tz = pytz.timezone(lead_tz_name)
    return " (%s your time)" % slot_rules.format_slots([dt], tz=tz).split(" ", 1)[1]


def _dated_slot(dt: datetime) -> str:
    """'Tue Sep 29 2:00pm' - a weekday name alone is ambiguous across weeks."""
    local = slot_rules.to_tz(dt)
    time_part = slot_rules.format_slot(local).split(" ", 1)[1]
    return "%s %s %d %s" % (local.strftime("%a"), local.strftime("%b"), local.day, time_part)


def _dated_slots(slots: List[datetime]) -> str:
    named = [_dated_slot(s) for s in slots[:2]]
    if not named:
        return ""
    label = slot_rules.format_slots(slots[:1]).rsplit(" ", 1)[-1]
    return "%s %s" % (" or ".join(named), label)


def _crosses_a_week(proposed: Optional[datetime], counters: List[datetime]) -> bool:
    """True when the refused time and an alternative fall in different ISO weeks.

    "Tue 2:00pm is further out than I can lock in right now. Could you do Tue
    12:00pm instead?" reads as a contradiction: both are "Tue", one is next week.
    _counter() deliberately prefers a different day, so this is the normal shape
    of a beyond_horizon counter, not an edge case."""
    if proposed is None or not counters:
        return False
    week = slot_rules.to_tz(proposed).isocalendar()[:2]
    return any(slot_rules.to_tz(c).isocalendar()[:2] != week for c in counters[:2])


def _counter_values(match: BookingMatch, state: Any) -> Dict[str, Any]:
    """What a counter-proposal writes, computed once for the text and for
    its template-gate bindings: the greeting name, the alternatives and the
    refused time (None where the text is worded without it: a request for
    the lead's own times instead of alternatives, "That time does not work
    on my side" instead of the refused time).

    The refused time is written back in the zone the lead wrote it in, with
    its label ("Thu 11:00am ET"), and "CT" when they named Central or no
    zone (slots.format_asked_time). Printed bare in Central, "Thursday 11am
    ET" came back as "Thu 10:00am is a touch early", a time the lead never
    asked for."""
    dated = _crosses_a_week(match.proposed, list(match.counter_slots or []))
    if not match.counter_slots:
        alts = None
    elif dated:
        alts = _dated_slots(list(match.counter_slots))
    else:
        alts = slot_rules.format_slots(match.counter_slots[:2])
    if match.proposed is None:
        asked = None
    else:
        asked = slot_rules.format_asked_time(match.proposed, match.lead_tz, dated=dated)
    return {"first": first_name_of(state), "alts": alts, "asked": asked}


def _counter_early(match: BookingMatch) -> bool:
    """OUTSIDE_WINDOW: before the window opens (else past its last slot)."""
    return bool(match.proposed and match.proposed.hour < slot_rules.SLOT_WINDOW[0])


def counter_template_id(match: Optional[BookingMatch]) -> Optional[str]:
    """The catalogue id of the counter-proposal counter_proposal_text writes
    for ``match`` (booking.counter.<case>), or None when there is none (a
    bookable time, no time at all). An id string only: the catalogue is
    never read here."""
    if match is None or match.bookable or match.status == NO_TIME:
        return None
    if match.status == WINDOW_NO_FIT:
        return "booking.counter.window_no_fit"
    if match.status == OUTSIDE_WINDOW:
        return "booking.counter.outside_window_%s" % ("early" if _counter_early(match) else "late")
    if match.status in (WEEKEND, TOO_SOON, BEYOND_HORIZON):
        return "booking.counter.%s" % match.status
    return "booking.counter.slot_taken"


def counter_bindings(match: BookingMatch, state: Any) -> Dict[str, str]:
    """{placeholder: value} for what counter_proposal_text wrote: the lead's
    first name (when one is on file), the alternatives and the refused time.
    Never the booking link: no counter-proposal carries one (Lorenzo,
    2026-09-23). Only values actually written."""
    v = _counter_values(match, state)
    out = {}  # type: Dict[str, str]
    if _field(state, "first_name") and v["first"]:
        out["first_name"] = v["first"]
    if v["alts"]:
        out["alt_slots"] = v["alts"]
    if v["asked"] and match.status != WINDOW_NO_FIT:
        out["asked_time"] = v["asked"]
    return dict((k, val) for k, val in out.items() if val)


NO_ALTERNATIVES_ASK = "Could you send me a couple of times that work for you next week?"


def _counter_ask(alts: Optional[str], question: str = "Could you do %s instead?") -> str:
    """The ask after the refusal line: the two alternatives or, with no
    alternative to offer, a request for the lead's own times (never "any
    afternoon slot", which offers nothing). Never a booking link (Lorenzo,
    2026-09-23: the lead picks a time and Lorenzo sends the invite)."""
    if alts:
        return question % alts
    return NO_ALTERNATIVES_ASK


def counter_proposal_text(match: BookingMatch, state: Any) -> Optional[str]:
    """Reply body when the proposed time cannot be booked. None when it can."""
    if match.bookable:
        return None
    v = _counter_values(match, state)
    first = v["first"]
    alts = v["alts"]
    if match.status == NO_TIME:
        return None
    if match.status == WINDOW_NO_FIT:
        return ("Hey %s,\n\nNothing inside that window is open on my side in the next week. %s\n\nLorenzo"
                % (first, _counter_ask(alts, "Could you do %s?")))
    asked = v["asked"]
    if asked is None:
        # No readable time: nothing to say about it beyond that it does not
        # fit (the early/late split below needs the time itself).
        lead_line = "That time does not work on my side"
    elif match.status == OUTSIDE_WINDOW:
        lead_line = "%s is a touch early on my side" % asked if _counter_early(match) else "%s is past my last slot" % asked
    elif match.status == WEEKEND:
        lead_line = "%s lands on a weekend for me" % asked
    elif match.status == TOO_SOON:
        lead_line = "%s is a little tight on my end" % asked
    elif match.status == BEYOND_HORIZON:
        lead_line = "%s is further out than I can lock in right now" % asked
    else:
        lead_line = "%s just got taken on my calendar" % asked
    return "Hey %s,\n\n%s. %s\n\nLorenzo" % (first, lead_line, _counter_ask(alts))


# ----------------------------------------------------------------- booking
def zoom_connected_default() -> bool:
    conf = str(settings.IDS.get("ghl", {}).get("calendars", {}).get("discovery_call", {}).get("conferencing", "")).lower()
    return "zoom" in conf and "not connected" not in conf


def _extract_id(resp: Any, *paths: str) -> Optional[str]:
    if not isinstance(resp, dict) or resp.get("shadow"):
        return None
    for p in paths:
        cur = resp  # type: Any
        for part in p.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
            if cur is None:
                break
        if cur:
            return str(cur)
    return None


def _extract_zoom(resp: Any) -> Optional[str]:
    if not isinstance(resp, dict) or resp.get("shadow"):
        return None
    for key in ("address", "meetingLocation", "location", "zoomLink", "join_url"):
        val = resp.get(key) or (resp.get("appointment") or {}).get(key) if isinstance(resp.get("appointment"), dict) else resp.get(key)
        if isinstance(val, str) and "zoom.us" in val:
            return val
    return None


def _draft(subject: str, body: str, slot: datetime, problems: List[str], template_id: Optional[str] = None,
           booking_link: Optional[str] = cadence.DEFAULT_BOOKING_URL) -> Any:
    kwargs = dict(subject=subject, body_text=body, offered_slots=[slot.isoformat()], booking_link=booking_link,
                  rationale="booking confirmation", model="template", label="booking_confirmation", problems=problems,
                  template_id=template_id)
    try:
        return Draft(**kwargs)
    except TypeError:  # unknown Draft shape: keep the fields that exist
        return Draft(subject=subject, body_text=body)


def verify_slot(slot: datetime, ghl: Any, now: datetime, free_slots: Optional[List[Any]] = None,
                lead_email: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """(ok, problem) for writing this slot to the calendar.

    A slot is only bookable when we have actually seen Lorenzo's calendar. With
    no GHL token the cadence refuses to *offer* unverified times
    (skipped_unverified_slots); booking applies the same rule before it *writes*
    one, so a reply can never land on top of an existing call."""
    start = slot_rules.to_tz(slot)
    if free_slots is None and ghl is not None and getattr(ghl, "has_token", False):
        resolved, source = cadence.resolve_free_slots(ghl, now)
        if source == "ghl":
            free_slots = resolved
    if free_slots is not None:
        if int(start.timestamp()) in _keys(free_slots):
            return True, None
        return False, SLOT_ALREADY_TAKEN
    if collides_with_known_booking(start, exclude_email=lead_email):
        return False, SLOT_ALREADY_TAKEN
    return False, SLOT_NOT_VERIFIED


# Problems that say something about the world, not about the wording: the copy
# validator does not re-check them, so an editor that re-validates the body must
# carry them across rather than clearing the list.
NON_COPY_PROBLEMS = (SLOT_NOT_VERIFIED, SLOT_ALREADY_TAKEN, APPOINTMENT_NOT_CREATED, "zoom_not_connected")

# CT3 template ids (template_approvals._booking_entries): which catalogued
# text a booking draft is. Ids only; the pipeline stamps the hashes.
CONFIRMATION_IDS = {"zoom_link": "booking.confirmation.zoom_link", "no_zoom_link": "booking.confirmation.no_zoom_link"}
SLOT_ALREADY_TAKEN_ID = "booking.slot_already_taken"


def _unbookable_result(state: Any, start: datetime, problem: str, now_ct: datetime,
                       free_slots: Optional[List[Any]] = None,
                       extra_problems: Optional[List[str]] = None) -> BookingResult:
    """No write happened: hand Lorenzo a card instead of telling the prospect a
    call exists. The draft carries ``problem`` so approval.send_approved blocks.

    For SLOT_NOT_VERIFIED / APPOINTMENT_NOT_CREATED the body is a card, not a
    reply. It used to read "Thu 3:00pm CT works on my side. I will send the
    invite shortly." - one missing booking link away from being sendable, so an
    edit that pasted the link in turned a failed write into a confirmation for a
    call that does not exist. Nothing here is send-ready wording."""
    first = first_name_of(state)
    cands = _candidates(now_ct, free_slots)
    open_times = slot_rules.format_slots(_counter(cands, start))
    alts = open_times or "another afternoon this week"  # Lorenzo's card only
    if problem == SLOT_ALREADY_TAKEN:
        # A genuine counter-proposal: the slot is gone and we know it. The
        # taken time carries its zone like every other time in the reply.
        body = ("Hey %s,\n\n%s CT just got taken on my calendar. %s\n\nLorenzo"
                % (first, slot_rules.format_slot(start), _counter_ask(open_times or None)))
    else:
        body = ("NOT SENT - for Lorenzo.\n\n%s asked for %s and nothing was written to the Discovery Call "
                "calendar (%s). There is no appointment and no invite. Put it on the calendar by hand, then "
                "write the confirmation yourself. Open times if you need to counter: %s."
                % (first, slot_rules.format_slots([start]), problem, alts))
    problems = cadence.copy_problems(body, campaign_key=cadence.campaign_key_of(state)) + [problem]
    problems += [p for p in (extra_problems or []) if p]
    # booking.slot_already_taken is catalogued, but its draft always carries
    # the slot_already_taken problem, so it stays a card (CT3 decision 6).
    # The slot-already-taken counter carries no booking link (Lorenzo,
    # 2026-09-23), so its draft stores none: an edit re-validates against the
    # stored link and would otherwise demand it back in.
    draft = _draft(subject_for(state), body, start, problems,
                   template_id=SLOT_ALREADY_TAKEN_ID if problem == SLOT_ALREADY_TAKEN else None,
                   booking_link=None if problem == SLOT_ALREADY_TAKEN else cadence.DEFAULT_BOOKING_URL)
    logger.warning("booking refused for %s at %s: %s", _field(state, "lead_email"), start.isoformat(), problem)
    return BookingResult(slot=start, draft=draft, contact_id=_field(state, "ghl_contact_id"), appointment=None,
                         opportunity=None, interest_status=None, zoom_not_connected=not zoom_connected_default(),
                         zoom_link=None, shadow=True, records=[], problems=problems)


def _confirmation_draft(state: Any, start: datetime, lead_tz: Optional[str], zoom_link: Optional[str],
                        zoom_connected: bool) -> Tuple[Any, List[str]]:
    """The "Locked in ..." draft, built the same way whichever path produced the
    appointment, so a repeat call cannot answer in different words."""
    their = _their_time(start, lead_tz)
    when = "%s%s" % (slot_rules.format_slots([start]), their)
    if zoom_link:
        # The link on a line of its own, so no mail client runs the next
        # sentence into it.
        body = ("Hey %s,\n\nLocked in %s, invite on the way. Here is the Zoom link:\n%s\n\n"
                "I will keep it to 15 minutes.\n\nLorenzo" % (first_name_of(state), when, zoom_link))
    else:
        body = ("Hey %s,\n\nLocked in %s. The calendar invite with the video link follows in a separate email. "
                "I will keep it to 15 minutes.\n\nLorenzo" % (first_name_of(state), when))
    problems = cadence.copy_problems(body, campaign_key=cadence.campaign_key_of(state))
    if not zoom_connected:
        problems = problems + ["zoom_not_connected"]
    # The confirmation carries no booking link, so its draft stores none: an
    # edit re-validates against the stored link and would demand it back in.
    return _draft(subject_for(state), body, start, problems, template_id=confirmation_template_id(zoom_link),
                  booking_link=None), problems


def confirmation_template_id(zoom_link: Optional[str]) -> str:
    """booking.confirmation.zoom_link when the draft carries the Zoom link,
    else booking.confirmation.no_zoom_link (approved separately)."""
    return CONFIRMATION_IDS["zoom_link" if zoom_link else "no_zoom_link"]


def confirmation_bindings(state: Any, start: datetime, lead_tz: Optional[str],
                          zoom_link: Optional[str]) -> Dict[str, str]:
    """{placeholder: value} for what _confirmation_draft wrote: the lead's
    first name (when on file), the call time, the lead's own time (another
    zone only) and the Zoom link. Only values actually written."""
    out = {"slot": slot_rules.format_slot(slot_rules.to_tz(start))}  # type: Dict[str, str]
    if _field(state, "first_name") and first_name_of(state):
        out["first_name"] = first_name_of(state)
    their = _their_time(start, lead_tz)
    if their:
        out["lead_local_time"] = their[len(" ("):-len(" your time)")]
    if zoom_link:
        out["zoom_link"] = zoom_link
    return out


def _already_booked_result(state: Any, start: datetime, existing: Dict[str, Any], lead_tz: Optional[str],
                           zoom_connected: Optional[bool]) -> BookingResult:
    """This exact call is already on the calendar: return it, write nothing."""
    connected = zoom_connected_default() if zoom_connected is None else bool(zoom_connected)
    if existing.get("zoom_not_connected"):
        connected = False
    zoom_link = existing.get("zoom_link")
    draft, problems = _confirmation_draft(state, start, lead_tz, zoom_link, connected)
    return BookingResult(slot=start, draft=draft, contact_id=_field(state, "ghl_contact_id"),
                         appointment={"id": existing.get("appointment_id"), "already_booked": True},
                         opportunity=None, interest_status=None, zoom_not_connected=not connected,
                         zoom_link=zoom_link, shadow=bool(existing.get("shadow", True)), records=[],
                         problems=problems)


def book(state: Any, slot: Union[str, datetime], ghl: Any, instantly: Any, now: Optional[datetime] = None,
         lead_tz: Optional[str] = None, zoom_connected: Optional[bool] = None,
         free_slots: Optional[List[Any]] = None, store: Any = None,
         allow_outside_rules: bool = False) -> BookingResult:
    """Create the GHL appointment (guarded), move the opportunity to Call
    Booked (guarded), set Instantly interest status 2 (guarded), stop the
    cadence and return the confirmation Draft for Lorenzo's approval.

    Refuses (no writes, no cadence stop, unsendable draft) when the slot cannot
    be shown to be free, or when the appointment was not actually created. A
    lead that already has an appointment is rescheduled: the old event is
    cancelled first so two calls are never left on the calendar.

    ``store`` is the one shared store. Passing it is what makes a booking part
    of the rest of the system rather than a write that only GHL knows about:
    ``register_booking`` reserves the slot against every other lead, writes the
    ``appointment:<id>`` row the 07:30 sweep reads and the ``appt:<id>`` row the
    Zoom webhook resolves joins through, and arms the show-rate sequence
    immediately instead of waiting for the next ten-minute tick.

    ``now`` should always be injected; the wall clock is only used when it is
    omitted outside tests."""
    start = slot_rules.to_tz(slot_rules.parse_iso(slot))
    end = start + timedelta(minutes=SLOT_MINUTES)
    now_ct = slot_rules.to_tz(now) if now is not None else datetime.now(TZ)
    existing = dict((getattr(state, "cadence", None) or {}).get("booking") or {})
    # Idempotent on (lead, slot): a lead who replies twice in a minute, a retry,
    # or approval.accept_requested calling straight through used to create a
    # SECOND appointment at the same time, cancel nothing (rescheduled_from is
    # only set when the slot CHANGED) and orphan the first appointment id along
    # with its store rows and its armed show-rate schedule.
    if existing.get("appointment_id") and existing.get("slot") == start.isoformat():
        logger.info("booking %s at %s is already on the calendar (%s): no second write",
                    _field(state, "lead_email"), start.isoformat(), existing.get("appointment_id"))
        return _already_booked_result(state, start, existing, lead_tz, zoom_connected)
    # verify_slot answers AVAILABILITY only. Lorenzo's own slot rules (Mon-Fri,
    # 12:00-18:00 CT, >=4 h out, <=5 business days) are a separate question, and
    # slot_rules.parse_proposed_time deliberately does not know about them: Ilmi's
    # real "this Wednesday around 11:30 am" parses fine and breaks the no-mornings
    # rule. evaluate_reply checks compliance() before it calls anything bookable,
    # but book() is also reachable directly, so it re-checks here.
    #
    # allow_outside_rules=True is Lorenzo tapping "Book as asked" on the card:
    # that waives HIS policy, never availability, so the verify_slot call below
    # still runs and a genuinely busy slot is still refused.
    broken_rule = compliance(start, now_ct)
    if broken_rule and not allow_outside_rules and not (existing.get("slot") == start.isoformat()):
        logger.info("refusing to book %s for %s: %s", start.isoformat(), _field(state, "lead_email"), broken_rule)
        return _unbookable_result(state, start, broken_rule, now_ct, free_slots)
    ok, problem = verify_slot(start, ghl, now_ct, free_slots, lead_email=_field(state, "lead_email"))
    if not ok and not (existing.get("slot") == start.isoformat()):
        if problem == SLOT_ALREADY_TAKEN or settings.is_live():
            return _unbookable_result(state, start, problem, now_ct, free_slots)
        logger.info("booking %s unverified in shadow: recording the intent", start.isoformat())
    # The slot was judged free from a registry read made earlier (the caller's
    # free list excludes other leads' offers). Claimed atomically before the
    # calendar write: another lead's card or booking that took it in the
    # meantime makes this a counter-proposal, never a second call on the same
    # 15 minutes (SAL-10). register_booking adds the booking's own row; the
    # provisional claim is dropped once it has, or on any way out without one.
    claim_fields = {"approval": "%s%s:%s" % (BOOKING_CLAIM_PREFIX, _field(state, "lead_email"), start.isoformat())}
    claimed = False
    if store is not None:
        try:
            from services.reply_engine import approval as approval_mod

            taken = approval_mod.claim_slots(store, _field(state, "lead_email"), [start.isoformat()], now_ct,
                                             fields=claim_fields)
        except Exception as exc:  # noqa: BLE001 - an unreadable registry refuses rather than double-book
            logger.warning("could not claim %s for %s: %s", start.isoformat(), _field(state, "lead_email"), exc)
            taken = [start.isoformat()]
        if taken:
            logger.warning("refusing to book %s for %s: another lead holds it", start.isoformat(),
                           _field(state, "lead_email"))
            return _unbookable_result(state, start, SLOT_ALREADY_TAKEN, now_ct, free_slots)
        claimed = True
    try:
        return _book_claimed(state, start, end, now_ct, existing, ok, ghl, instantly, lead_tz, zoom_connected,
                             free_slots, store)
    finally:
        if claimed:
            _release_booking_claim(store, state, start, claim_fields)


BOOKING_CLAIM_PREFIX = "booking-claim:"

# The status of the classification-time hold. Unapproved, so never "confirmed"
# (see _book_claimed); approval.send_approved moves it to "confirmed".
HOLD_APPOINTMENT_STATUS = "new"


def _release_booking_claim(store: Any, state: Any, start: datetime, fields: Dict[str, Any]) -> None:
    try:
        from services.reply_engine import approval as approval_mod

        approval_mod.release_claimed(store, _field(state, "lead_email"), [start.isoformat()], fields=fields)
    except Exception as exc:  # noqa: BLE001 - a leftover provisional row only offers less
        logger.warning("could not drop the provisional claim on %s: %s", start.isoformat(), exc)


def _book_claimed(state: Any, start: datetime, end: datetime, now_ct: datetime, existing: Dict[str, Any], ok: bool,
                  ghl: Any, instantly: Any, lead_tz: Optional[str], zoom_connected: Optional[bool],
                  free_slots: Optional[List[Any]], store: Any) -> BookingResult:
    """book() once the slot is claimed for this lead: the calendar write and
    everything after it."""
    zoom_connected = zoom_connected_default() if zoom_connected is None else bool(zoom_connected)
    email = _field(state, "lead_email")
    campaign_id = _field(state, "campaign_id")
    first = first_name_of(state)
    company = company_of(state)
    niche, offer = niche_and_offer(state)
    records = []  # type: List[Dict[str, Any]]
    shadow = True

    # 1. contact
    contact_id = _field(state, "ghl_contact_id")
    if not contact_id and ghl is not None:
        res = ghl.upsert_contact(email, first_name=first if first != "there" else None, company=company if company != "your team" else None,
                                 tags=["cold-email", "instantly-positive-reply"])
        if isinstance(res, dict):
            records.append(res)
            contact_id = _extract_id(res, "contact.id", "id")
            if contact_id:
                state.ghl_contact_id = contact_id

    # 2. appointment on the Discovery Call calendar. A lead who is already booked
    # is being rescheduled: cancel the old event first, or GHL keeps both and the
    # show-rate / no-show schedule for the original is orphaned.
    rescheduled_from = existing.get("appointment_id") if existing.get("slot") != start.isoformat() else None

    title = "Lorenzo <> %s: 15-min %s plan" % (company, "reactivation" if offer == "reactivation" else "outbound")
    try:
        # to_notify=False: book() runs at CLASSIFICATION time, before Lorenzo has
        # seen the card, so GHL's own invite email would reach the prospect for a
        # call he never approved - and if he vetoes, cancel_booking then has to
        # un-say it. The invite is released in approval.send_approved once the
        # confirmation reply is actually out (update_appointment_status
        # to_notify=True), which is the moment "invite on the way" becomes true.
        #
        # appointment_status="new", never GHL's default "confirmed": the hold is
        # unapproved. The GHL show-rate workflow (changesets/ghl_workflows/
        # show_rate_workflow.md) fires on Appointment Status -> Confirmed, so a
        # "confirmed" hold would mail "Confirmed: <time>", the pre-read and the
        # reminders a minute after classification, before Lorenzo sees the card;
        # and Approve's confirmed -> confirmed would be no transition at all.
        # "new" still blocks the slot on the calendar; approval.send_approved
        # makes the real new -> confirmed move.
        if ghl is not None:
            appt = ghl.create_appointment(settings.GHL_CALENDAR_ID, contact_id or "pending", start.isoformat(), end.isoformat(), title,
                                          appointment_status=HOLD_APPOINTMENT_STATUS, to_notify=False)
        else:
            appt = guard_write("ghl", "create_appointment", {"calendarId": settings.GHL_CALENDAR_ID, "contactId": contact_id or "pending",
                                                              "startTime": start.isoformat(), "endTime": end.isoformat(), "title": title,
                                                              "appointmentStatus": HOLD_APPOINTMENT_STATUS,
                                                              "toNotify": False})
    except Exception as exc:  # noqa: BLE001 - a calendar error degrades to Lorenzo's card, it never 500s the webhook
        logger.warning("create_appointment failed for %s at %s: %s", email, start.isoformat(), exc)
        return _unbookable_result(state, start, APPOINTMENT_NOT_CREATED, now_ct, free_slots)
    appt = appt if isinstance(appt, dict) else ({"result": appt} if appt is not None else None)
    if appt:
        records.append(appt)
        shadow = shadow and bool(appt.get("shadow", False))
    zoom_link = _extract_zoom(appt) if zoom_connected else None
    appointment_id = _extract_id(appt, "id", "appointment.id")

    # A live write that returned nothing (no Private Integration token, per
    # config/ids.json) is not a booking: never tell the prospect it is, never
    # stop the cadence on it, and never move the pipeline.
    if settings.is_live() and (appt is None or (not appt.get("shadow", False) and not appointment_id)):
        return _unbookable_result(state, start, APPOINTMENT_NOT_CREATED, now_ct, free_slots)
    if not appointment_id and (appt is None or appt.get("shadow", False)):
        # Shadow is the only mode Lorenzo allows before go-live, and a guarded
        # write returns no id, so every downstream coupling (show-rate,
        # no-show, the Zoom index, the sweep) would first have run for real in
        # production. Give the shadow booking a deterministic local id instead.
        appointment_id = shadow_appointment_id(state, start)

    # From here on an engine-created appointment exists. It must never be left
    # with neither (a booking record + a held show-rate ladder) nor a silent
    # cancel: jobs/appointments_tick would find the GHL event with no hold and
    # arm an unheld ladder that mails the prospect "Confirmed: ..." about a
    # call Lorenzo never approved. Hold first - ensure_scheduled stamps any
    # schedule born later from this marker - then do the fallible writes.
    if store is not None and appointment_id:
        hold_problem = _hold_new_appointment(store, state, appointment_id, start, now_ct)
        if hold_problem:
            rollback = _silent_rollback(ghl, appointment_id, email, start, hold_problem)
            return _unbookable_result(state, start, APPOINTMENT_NOT_CREATED, now_ct, free_slots,
                                      extra_problems=[rollback])
    pipeline_errors = []  # type: List[str]

    # Reschedule: the new event exists, so the old one can be cancelled. GHL
    # keeps both otherwise and appointments_tick chases the orphan.
    # to_notify=False, as on every cancel the engine starts (SAL-9): the lead
    # asked for the new time and hears about it in the confirmation Lorenzo
    # approves; GHL's default notification setting must not mail them a
    # cancellation of their call in the meantime.
    if rescheduled_from:
        try:
            if ghl is not None:
                cancel = ghl.update_appointment_status(rescheduled_from, "cancelled", to_notify=False)
            else:
                cancel = guard_write("ghl", "update_appointment_status",
                                     {"appointment_id": rescheduled_from, "status": "cancelled", "toNotify": False})
        except Exception as exc:  # noqa: BLE001 - the new call exists; surface the orphan instead of losing it
            logger.warning("could not cancel %s: %s", rescheduled_from, exc)
            cancel = {"error": str(exc), "appointment_id": rescheduled_from}
        if isinstance(cancel, dict):
            records.append(cancel)

    # 3. opportunity -> Call Booked. A raise here used to escape book() after
    # the appointment existed, with no booking record and no hold.
    stage = settings.GHL_STAGES.get("call_booked")
    opp_id = _field(state, "ghl_opportunity_id")
    opp = None
    try:
        if ghl is not None and opp_id:
            opp = ghl.update_opportunity_stage(opp_id, stage)
        elif ghl is not None:
            opp = ghl.upsert_opportunity(contact_id or "pending", settings.GHL_SALES_PIPELINE_ID, stage,
                                         "%s - %s (Cold Email)" % (company, _field(state, "first_name", default=email)))
        else:
            opp = guard_write("ghl", "update_opportunity_stage", {"opportunity_id": opp_id, "stage_id": stage})
    except Exception as exc:  # noqa: BLE001 - the call is booked; report the pipeline miss
        logger.error("opportunity stage update failed for %s after booking %s: %s", email, appointment_id, exc)
        pipeline_errors.append("opportunity stage not moved to Call Booked: %s" % str(exc)[:200])
    opp = opp if isinstance(opp, dict) else ({"result": opp} if opp is not None else None)
    if opp:
        records.append(opp)
        new_opp = _extract_id(opp, "opportunity.id", "id")
        if new_opp and not opp_id:
            state.ghl_opportunity_id = new_opp

    # 4. Instantly interest status -> Meeting Booked (2)
    interest = None
    try:
        if instantly is not None and campaign_id:
            interest = instantly.update_interest_status(email, campaign_id, INTEREST_MEETING_BOOKED)
        else:
            interest = guard_write("instantly", "update_interest_status", {"lead_email": email, "campaign_id": campaign_id, "interest_value": INTEREST_MEETING_BOOKED})
    except Exception as exc:  # noqa: BLE001 - the call is booked; report the pipeline miss
        logger.error("interest status update failed for %s after booking %s: %s", email, appointment_id, exc)
        pipeline_errors.append("Instantly interest not set to Meeting Booked: %s" % str(exc)[:200])
    if interest is not None or not pipeline_errors:
        interest = interest if isinstance(interest, dict) else {"result": interest}
        records.append(interest)

    shadow = all(bool(r.get("shadow", False)) for r in records if isinstance(r, dict)) if records else True

    # 5. stop the cadence, remember the booking on the state
    cad = dict(getattr(state, "cadence", None) or {})
    cad["booking"] = {
        "slot": start.isoformat(),
        "end": end.isoformat(),
        "appointment_id": appointment_id,
        "appointment_id_synthetic": appointment_id is not None and _extract_id(appt, "id", "appointment.id") is None,
        "zoom_link": zoom_link,
        "zoom_not_connected": not zoom_connected,
        "booked_at": now_ct.isoformat(),
        "shadow": shadow,
        "slot_verified": bool(ok),
        "rescheduled_from": rescheduled_from,
        # Booked at classification time: the confirmation has not gone out and
        # the invite is withheld until an approved card sends it. The card
        # that owns this booking is recorded under "owner" by the caller
        # (approval.claim_booking); approval._mark_booking_confirmed clears
        # both once the owning card is sent.
        "awaiting_approval": True,
    }
    if pipeline_errors:
        cad["booking"]["pipeline_errors"] = list(pipeline_errors)
    state.cadence = cad
    if cad.get("armed_at"):
        try:
            cadence.stop(state, "booked", now_ct)
        except Exception as exc:  # noqa: BLE001 - the booking record is written; never lose it
            logger.error("could not stop the cadence for %s after booking: %s", email, exc)
            pipeline_errors.append("cadence not stopped: %s" % str(exc)[:200])
    try:
        state.status = "call_booked"
    except Exception:  # noqa: BLE001 - a frozen/strict model must not break the booking
        pass

    # 6. confirmation draft (for approval)
    draft, problems = _confirmation_draft(state, start, lead_tz, zoom_link, zoom_connected)
    try:
        history = list(getattr(state, "history", None) or [])
        history.append({"ts": now_ct.isoformat(), "event": "booked", "slot": start.isoformat(), "shadow": shadow})
        state.history = history
    except Exception:  # noqa: BLE001
        pass

    result = BookingResult(slot=start, draft=draft, contact_id=contact_id, appointment=appt, opportunity=opp,
                           interest_status=interest, zoom_not_connected=not zoom_connected, zoom_link=zoom_link,
                           shadow=shadow, records=records, problems=problems,
                           pipeline_errors=pipeline_errors)
    if store is not None:
        register_booking(store, state, result, now_ct, lead_tz=lead_tz)
    return result


HOLD_UNVERIFIED = "hold_unverified"


def _hold_new_appointment(store: Any, state: Any, appointment_id: Any, start: datetime,
                          now_ct: datetime) -> Optional[str]:
    """Write the show-rate hold for a just-created appointment. Returns the
    problem, or None once the hold is confirmed in the store.

    The check reads the marker back with ``show_rate.read_hold``, which tells
    "no marker" apart from "could not read it" (``is_held`` reads a store error
    as "not held"). A read error is read once more before anything is rolled
    back: a single blip must not cancel a call the hold was written for. Two
    read errors return HOLD_UNVERIFIED and the caller still rolls back (a call
    whose hold nobody can confirm must not reach the lead), but the card line
    says the hold could not be checked, not that it was not written."""
    try:
        from services.reply_engine import show_rate

        show_rate.hold(store, appointment_id, reason="awaiting_approval", now=now_ct,
                       meta={"lead_email": _field(state, "lead_email"), "start_iso": start.isoformat()})
    except Exception as exc:  # noqa: BLE001
        logger.error("could not hold the new appointment %s: %s", appointment_id, exc)
        return "hold_failed: %s" % str(exc)[:200]
    error = None  # type: Optional[str]
    for _read in range(2):
        rec, error = show_rate.read_hold(store, appointment_id)
        if error is None:
            return None if rec is not None else "hold_not_written"
        logger.warning("could not read back the hold on the new appointment %s: %s", appointment_id, error)
    return "%s: %s" % (HOLD_UNVERIFIED, error)


def _silent_rollback(ghl: Any, appointment_id: Any, email: Any, start: datetime, why: str) -> str:
    """Cancel an appointment the engine could not hold, without notifying the
    lead. Returns the problem line for Lorenzo's card; alerts him when the
    cancel also fails (the event is then live and unheld)."""
    unverified = str(why).startswith(HOLD_UNVERIFIED)
    if unverified:
        held_phrase = ("its hold was written but could not be checked (the store read failed twice: %s)"
                       % str(why).split(": ", 1)[-1])
    else:
        held_phrase = "could not be held (%s)" % why
    try:
        if ghl is not None and not str(appointment_id).startswith("shadow-"):
            res = ghl.update_appointment_status(appointment_id, "cancelled", to_notify=False)
            if res is None:
                raise RuntimeError("the cancel returned nothing")
        return "the appointment was created but %s, so it was cancelled silently" % held_phrase
    except Exception as exc:  # noqa: BLE001
        logger.error("could not roll back appointment %s for %s: %s", appointment_id, email, exc)
        try:
            from services.reply_engine import approval as approval_mod

            what = ("could not confirm its reminders are held (%s)" % why if unverified
                    else "could not hold its reminders (%s)" % why)
            approval_mod._alert("Unheld call on the calendar for %s" % email,
                                "The engine created appointment %s (%s) but %s and GHL refused the silent cancel "
                                "(%s). Cancel it in GHL without notifying the lead."
                                % (appointment_id, start.isoformat(), what, exc), priority="urgent")
        except Exception:  # noqa: BLE001
            logger.exception("could not alert about appointment %s", appointment_id)
        return ("the appointment %s was created but %s and the silent cancel failed (%s): "
                "cancel it by hand" % (appointment_id, held_phrase, exc))


# ------------------------------------------------------- system registration
def appointment_payload(state: Any, result: "BookingResult") -> Dict[str, Any]:
    """The ``appointment:<id>`` row jobs/pipeline_sweep.py reads for "booked
    calls starting in the next 24 h". Without it the sweep falls back to the
    static seed in config/ids.json and never sees a call the engine booked."""
    cad = (getattr(state, "cadence", None) or {}).get("booking") or {}
    return {
        "lead_email": _field(state, "lead_email"),
        "start": result.slot.isoformat(),
        "end": cad.get("end"),
        "confirmed": False,
        "name": _field(state, "first_name", default=None) or company_of(state),
        "company": company_of(state),
        "campaign_id": _field(state, "campaign_id"),
        "contact_id": result.contact_id,
        "opportunity_id": _field(state, "ghl_opportunity_id"),
        "appointment_id": cad.get("appointment_id"),
        "shadow": bool(result.shadow),
        "booked_at": cad.get("booked_at"),
    }


def show_rate_appointment(state: Any, result: "BookingResult", lead_tz: Optional[str] = None) -> Dict[str, Any]:
    """The appointment dict show_rate/no_show speak, built from what we just
    wrote rather than from a later calendar read.

    ``lead_tz`` and ``tags`` matter: show_rate.lead_tz_of decides which clock an
    SMS window is measured in, and offer-*/niche-* tags are its fallback when
    the explicit niche/offer are absent. jobs/appointments_tick supplies both
    for a calendar-sourced booking; a booking made here used to arrive without
    them and fell back to Central plus offer "reactivation".
    """
    cad = (getattr(state, "cadence", None) or {}).get("booking") or {}
    niche, offer = niche_and_offer(state)
    first = first_name_of(state)
    tz_name = lead_tz or cad.get("lead_tz") or _field(state, "lead_tz") or _field(state, "timezone")
    tags = list(_field(state, "ghl_tags") or [])
    for derived in ("offer-%s" % offer if offer else None, "niche-%s" % niche if niche else None):
        if derived and derived not in tags:
            tags.append(derived)
    return {
        "lead_tz": tz_name,
        "tags": tags,
        "id": cad.get("appointment_id"),
        "contact_id": result.contact_id,
        "opportunity_id": _field(state, "ghl_opportunity_id"),
        "start_iso": result.slot.isoformat(),
        "end_iso": cad.get("end"),
        "zoom_link": result.zoom_link,
        "email": _field(state, "lead_email"),
        "phone": _field(state, "phone"),
        "first_name": None if first == "there" else first,
        "contact_name": None if first == "there" else first,
        "company": company_of(state),
        "niche": niche,
        "offer": offer,
        "campaign_id": _field(state, "campaign_id"),
        "booked_at": cad.get("booked_at"),
    }


def register_booking(store: Any, state: Any, result: "BookingResult", now_ct: datetime,
                     lead_tz: Optional[str] = None) -> Dict[str, Any]:
    """Join a booking to the rest of the system. Never raises: the call is on
    the calendar by the time we get here, so a store hiccup must not turn a
    successful booking into an exception the webhook reports as a failure."""
    out = {"appointment": False, "appt_index": False, "slot_reserved": False, "show_rate": None}  # type: Dict[str, Any]
    cad = (getattr(state, "cadence", None) or {}).get("booking") or {}
    appointment_id = cad.get("appointment_id")
    slot_iso = result.slot.isoformat()
    try:
        # 1. hold the slot against every other lead. In shadow there is no real
        # GHL calendar to filter it out, so without this two leads can be
        # offered the same time off the synthetic grid.
        try:
            from services.reply_engine import approval as approval_mod

            approval_mod.reserve_slots(store, _field(state, "lead_email"), [slot_iso],
                                       "booking:%s" % (appointment_id or slot_iso), now_ct)
            out["slot_reserved"] = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not reserve the booked slot %s: %s", slot_iso, exc)
        if not appointment_id:
            return out
        # 2. the sweep's view of a booked call
        store.set("appointment:%s" % appointment_id, appointment_payload(state, result))
        out["appointment"] = True
        # 3. the Zoom webhook's meeting -> appointment index
        index = {"appointment_id": appointment_id, "contact_id": result.contact_id,
                 "opportunity_id": _field(state, "ghl_opportunity_id"),
                 "zoom_meeting_id": _zoom_meeting_id(result.zoom_link), "start_iso": slot_iso}
        store.set("appt:%s" % appointment_id, index)
        out["appt_index"] = True
        if index["zoom_meeting_id"]:
            store.set("zoom_meeting:%s" % index["zoom_meeting_id"], {"appointment_id": appointment_id})
        # 4. arm the show-rate sequence now instead of on the next 10-minute tick,
        # but HELD: this runs at classification time, so the call on the
        # calendar is one Lorenzo has not approved yet. The GHL invite is
        # already withheld (create_appointment sends toNotify=False); the
        # engine's own T+0 "Locked in for ..." confirmation is the other half,
        # and without the hold the next ten-minute tick mails it to the
        # prospect ahead of the approval tap, or after a veto.
        # approval.send_approved -> show_rate.release_hold starts the ladder;
        # approval.cancel_booking tears it down.
        from services.reply_engine import show_rate

        appt_dict = show_rate_appointment(state, result, lead_tz=lead_tz)
        try:
            out["held"] = show_rate.hold(
                store, appointment_id, reason="awaiting_approval", now=now_ct,
                meta={"lead_email": _field(state, "lead_email"), "start_iso": slot_iso})
        except Exception as exc:  # noqa: BLE001 - see below: never arm what we could not hold
            logger.error("could not hold the show-rate ladder for %s: %s", appointment_id, exc)
            out["error"] = "hold_failed: %s" % exc
            return out
        # A lead who books again while a no-show recovery ladder is running must
        # not keep getting "we missed you" touches. jobs/appointments_tick does
        # this from the calendar as a stopgap; doing it here closes the window
        # between the booking and the next tick.
        try:
            from services.reply_engine import no_show as no_show_mod

            cancelled = no_show_mod.cancel_recovery_for_rebooking(store, appointment_id)
            if cancelled:
                out["recovery_cancelled"] = cancelled
        except Exception as exc:  # noqa: BLE001 - bookkeeping must never lose the booking
            logger.warning("cancel_recovery_for_rebooking failed for %s: %s", appointment_id, exc)
        out["show_rate"] = show_rate.ensure_scheduled(store, appt_dict, now_ct)
    except Exception as exc:  # noqa: BLE001 - the appointment exists; never lose it over bookkeeping
        logger.warning("register_booking failed for %s: %s", appointment_id, exc, exc_info=True)
        out["error"] = str(exc)
    return out


def shadow_appointment_id(state: Any, start: datetime) -> str:
    """Deterministic id for a booking that only exists in the shadow log, so
    the same reply replayed twice produces the same appointment."""
    import hashlib

    key = getattr(state, "key", None) or "%s:%s" % (_field(state, "campaign_id"), _field(state, "lead_email"))
    digest = hashlib.sha1(("%s|%s" % (key, start.isoformat())).encode("utf-8")).hexdigest()[:12]
    return "shadow-appt-%s" % digest


def _zoom_meeting_id(link: Optional[str]) -> Optional[str]:
    if not link:
        return None
    try:
        from services.reply_engine import zoom_webhook

        return zoom_webhook.meeting_id_from_link(link)
    except Exception:  # noqa: BLE001
        return None
