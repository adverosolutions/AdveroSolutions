"""FastAPI service + the single processing pipeline.

process_event(event) is used by the webhook, the poller and the replay:
    classify -> route (guarded GHL/Instantly writes) -> draft + approval when
    the label deserves an answer -> LeadState persisted under
    'lead:<campaign_id>:<email>' -> Job_Log row. A stale reply is recorded
    only (router.stale_reason, _record_stale_reply): one the lead sent before
    their opt-out, or one that is not an opt-out, sent before a newer reply of
    theirs already on the row. An older reply that proposes a call time books
    nothing, and marks the lead's open card that names other times with a
    problem, so it is not sent as it is (_mark_time_conflicts). The sticky
    opt-out marker is set and cleared under the row's lock
    (_settle_opt_out_marker).

A reply that names a time goes through services.reply_engine.booking: bookable ->
book it and draft the confirmation; blocked only by Lorenzo's own slot rule ->
counter-propose AND offer "book it as asked" on the card; already booked ->
restate the booking instead of offering new times.

Endpoints: POST /webhooks/instantly (X-Advero-Secret required), GET|POST /approve/{token}
(GET renders a confirmation page, POST sends), GET|POST /veto/{token} (same split),
GET|POST /edit/{token}, GET|POST /accept/{token}, GET|POST /retry/{token},
GET|POST /mark-sent/{token} (a card stuck at send_failed, or at sending past its
lease, whose reply did go out),
GET|POST /expired/{token}/{keep|release} (a card that expired holding a call),
GET|POST /cadence/{veto|approve|veto-invite}/{campaign_id}/{email} (GET renders a
confirmation page for a signed link, POST records the decision), GET|POST
/cadence/resume/{campaign_id}/{email}, GET /health,
GET /state/{lead_email} (secret-gated debug). zoom_webhook.router is included when
that module exists, and shares app.state.store with the scheduled ticks.
"""
import dataclasses
import hashlib
import hmac
import html
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, quote, unquote, urlencode

import pytz
from fastapi import Body, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from shared import job_log, settings, slots, store as store_mod

from services.reply_engine import approval as approval_mod
# The CT3 template gate. Importing it builds nothing: every gate call below
# runs per reply or per request, never while this module is importing, so the
# catalogue (which renders app._already_booked_body) is never built half-done.
from services.reply_engine import template_gate
from services.reply_engine.classify import classify, core_text
from services.reply_engine.draft import (
    answer_paragraph,
    build_draft,
    busy_blocks_from_ids,
    campaign_key_for,
    fallback_free_slots,
    first_reply_bindings,
    first_reply_template_id,
    free_slots_from_ghl,
    lead_terms,
    reply_subject,
    validate_draft,
)
from services.reply_engine.models import (
    BLOCKLIST_LABELS,
    RECEIVED_AT_PROCESSING,
    Draft,
    LeadState,
    ReplyEvent,
    iso_utc,
    is_content_key,
    is_synthetic_email_id,
    reply_received_at,
)
from services.reply_engine.router import (
    MACHINE_LABELS,
    OPT_OUT_LABELS,
    OPT_OUT_STATUSES,
    STALE_OLDER_REPLY,
    implied_opt_out,
    newer_replies,
    next_opt_out_marker,
    route,
    stale_reason,
)

logger = logging.getLogger("reply_engine.app")

REPLY_EVENT_TYPES = {
    "reply_received", "lead_interested", "lead_not_interested", "lead_neutral", "lead_unsubscribed",
    "lead_out_of_office", "lead_wrong_person", "custom_label_any_positive", "custom_label_any_negative",
    "lead_meeting_booked", "lead_meeting_completed", "lead_closed",
}
IGNORED_EVENT_TYPES = {"email_sent", "email_opened", "email_link_clicked", "email_bounced", "campaign_completed", "account_error"}


class Deps(object):
    """Injected collaborators (tests replace them; production builds lazily)."""

    def __init__(self, store=None, ghl=None, instantly=None, clock: Optional[Callable[[], datetime]] = None):
        self._store = store
        self._ghl = ghl
        self._instantly = instantly
        self.clock = clock

    @property
    def store(self):
        if self._store is None:
            self._store = store_mod.get_store()
        return self._store

    @property
    def ghl(self):
        if self._ghl is None:
            from shared.ghl import GHL

            self._ghl = GHL()
        return self._ghl

    @property
    def instantly(self):
        if self._instantly is None:
            from shared.instantly import default_client
            self._instantly = default_client()
        return self._instantly

    def now(self) -> datetime:
        return slots.to_tz(slots.ensure_aware(self.clock())) if self.clock else datetime.now(slots.TZ)


DEPS = Deps()


def configure(store=None, ghl=None, instantly=None, clock=None) -> Deps:
    """Replace the module-level dependencies (tests, replay, dry-run)."""
    global DEPS
    DEPS = Deps(store=store, ghl=ghl, instantly=instantly, clock=clock)
    fastapi_app = globals().get("app")
    if fastapi_app is not None:
        # Keep the Zoom router on the same store object the pipeline uses; it
        # reads request.app.state.store. Assigning the raw ``store`` argument
        # left it None whenever configure() was called with no arguments (the
        # Modal poller does exactly that), so the router fell back to its own
        # get_store() lookup and the two halves only agreed by luck.
        fastapi_app.state.store = DEPS.store
    return DEPS


def _optional(name: str):
    """Import a sibling module that another brief owns; None when it is absent."""
    import importlib

    try:
        return importlib.import_module("services.reply_engine.%s" % name)
    except ImportError as exc:  # noqa: BLE001
        logger.warning("module %s unavailable: %s", name, exc)
        return None


def _stop_cadence_for_inbound(state: LeadState, now: datetime) -> Optional[str]:
    """Any new inbound reply stops a running cadence.

    cadence.stop(..., 'inbound_reply') sets needs_fresh_draft=True and leaves
    the rest of the cadence dict in place, so the next approved reply can re-arm
    it (cadence.arm) instead of starting from scratch.
    """
    cadence = _optional("cadence")
    if cadence is None:
        state.cadence = dict(state.cadence, stopped_reason="inbound_reply", stopped_at=now.isoformat(),
                             next_send_at=None, needs_fresh_draft=True)
        return "inbound_reply"
    try:
        cadence.stop(state, "inbound_reply", now)
        return "inbound_reply"
    except Exception as exc:  # noqa: BLE001
        logger.warning("cadence.stop failed: %s", exc)
        return None


class _CadenceHolder(object):
    """The one attribute cadence.stop reads and writes."""

    def __init__(self, cad: Dict[str, Any]):
        self.cadence = dict(cad)


def _settle_opt_out_marker(merged: Dict[str, Any], event: ReplyEvent, ctx: Dict[str, Any],
                           now: datetime) -> Dict[str, Any]:
    """The sticky opt-out marker, decided under the row's lock against the
    marker as stored (router.next_opt_out_marker): set by an opt-out, cleared
    only by a human reply provably sent after it. A pipeline that failed half
    way (``ctx["partial"]``) may set it but never clears it; its retry decides.
    When the result is no marker, one the history still implies
    (router.implied_opt_out) is put back: a concurrent first write of the row
    can drop it in the three-way merge. The pipeline never writes the field
    through the merge itself. Records what happened in ``ctx["opt_out"]``."""
    current = merged.get("opt_out") or None
    marker = current
    label = ctx.get("label")
    received = ctx.get("received_at")
    if label and received is not None:
        marker = next_opt_out_marker(current, label, event.email_id, received, ctx.get("received_at_source"), now)
        if marker is None and current and ctx.get("partial"):
            marker = current
    action = None
    if marker != current:
        action = "set" if marker else "cleared"
    if not marker:
        restored = implied_opt_out(merged.get("history"))
        if restored:
            marker, action = restored, "restored"
    if action is None:
        return merged
    ctx["opt_out"] = action
    if action == "cleared":
        logger.warning("opt-out marker of %s cleared by %s (a later reply of the lead's own)", event.lead_email,
                       event.email_id)
    elif action == "restored":
        logger.warning("opt-out marker of %s restored from the history under the lock", event.lead_email)
    return dict(merged, opt_out=marker)


def _inbound_stop_hook(event: ReplyEvent, state: LeadState, base_raw: Optional[Dict[str, Any]], now: datetime,
                       ctx: Optional[Dict[str, Any]] = None):
    """approval.save_lead_state's ``finish`` for a reply pipeline's write.

    _run_pipeline applies "any new inbound reply stops a running cadence" to
    the copy it read at the start. An approval sent while this pipeline was
    running can arm (or re-arm) the ladder after that read; the merge then
    keeps the store's stop fields as a group, so the stop was lost and the
    ladder ran on top of this reply's card (the arm stamps armed_at at send
    time, later than this reply's own timestamp, so the tick's inbound check
    never fired either). The rule is applied again here, under the row's lock,
    to the row as it stands: a running ladder is stopped, unless it was armed
    by the approved answer to this very reply (cadence.armed_for_email_id).
    The reason is the one this pipeline chose for its own copy (a booking
    stops with "booked"), else inbound_reply.

    ``ctx`` is the pipeline's context: the reply's label and received time
    once known, which settle the opt-out marker here (_settle_opt_out_marker),
    and ``stale`` (router.stale_reason): a stale reply (sent before the
    lead's opt-out, or before a newer reply of theirs) stops nothing."""
    base_reason = ((base_raw or {}).get("cadence") or {}).get("stopped_reason")
    own_reason = (state.cadence or {}).get("stopped_reason")
    reason = own_reason if own_reason and own_reason != base_reason else "inbound_reply"
    ctx = ctx if ctx is not None else {}

    def _finish(merged: Dict[str, Any]) -> Dict[str, Any]:
        merged = _settle_opt_out_marker(merged, event, ctx, now)
        if ctx.get("stale"):
            return merged
        cad = merged.get("cadence") or {}
        if not cad.get("armed_at") or cad.get("stopped_reason"):
            return merged
        if cad.get("armed_for_email_id") and cad.get("armed_for_email_id") == event.email_id:
            return merged
        holder = _CadenceHolder(cad)
        cadence = _optional("cadence")
        if cadence is not None:
            cadence.stop(holder, reason, now)
        else:
            holder.cadence.update(stopped_reason=reason, stopped_at=now.isoformat(), next_send_at=None,
                                  needs_fresh_draft=reason == "inbound_reply")
        logger.warning("stopped the cadence for %s under the lock (%s): it was armed after this reply's pipeline "
                       "read the row", event.lead_email, reason)
        return dict(merged, cadence=holder.cadence)

    return _finish


_CONFIRM_RE = re.compile(
    r"^\W*(c|y|yes|yep|yup|yeah|ok|okay|sure|confirm(ed|ing)?|sounds good|see you then|i'?ll be there|works for me)\b",
    re.I,
)


# "Confirmed." / "Confirming for Thursday." anywhere in a short body is a
# confirmation; the bare word is not. The old free-floating \bconfirm\b search
# matched "Before we meet, can you confirm what the percentage would be?" and
# marked the call confirmed, which disables the 4 h "no C yet" safety net for a
# lead who confirmed nothing.
_CONFIRMED_RE = re.compile(r"\bconfirm(ed|ing)\b", re.I)


def _looks_like_confirmation(text: str) -> bool:
    core = (text or "").strip()
    if not core:
        return False
    if _CONFIRM_RE.match(core):
        return True
    # a question is a question, whatever verb it uses
    return bool(_CONFIRMED_RE.search(core)) and "?" not in core


# Labels that can never be a confirmation, whatever words the body opens with.
# An out-of-office that begins "Sure, I am away until..." matched the old regex
# and marked the call confirmed, which kills the 4 h "no C yet" safety net.
NON_CONFIRMING_LABELS = ("ooo", "auto_reply_unmonitored", "unsubscribe", "negative_hostile",
                         "negative_notfit", "wrong_person")


def _body_is_out_of_office(core: str) -> bool:
    """True when the BODY carries an out-of-office marker, label or not.

    Reuses classify.OOO_STRONG_RE rather than a second copy of the phrase list,
    so the two can never drift. Import is lazy and failure-tolerant: a missing
    classify module must not break the appointment hooks.
    """
    if not core:
        return False
    try:
        from services.reply_engine import classify as classify_mod

        return bool(classify_mod.OOO_STRONG_RE.search(core))
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not read the OOO markers: %s", exc)
        return False


def _appointment_hooks(state: LeadState, core: str, store, now: datetime,
                       classification: Any = None) -> List[Dict[str, Any]]:
    """Two show-rate/no-show couplings for an inbound reply (Blueprint S4/S5):

    * a "C" / "confirm" / "yes" from a lead whose Discovery Call is still ahead
      marks the appointment confirmed, so the 4 h "no C yet" task never fires;
    * ANY reply from a lead the engine marked no_show cancels the recovery
      sequence, because Lorenzo is taking the conversation back.

    The confirmation half is gated on the classification and on the body not
    naming a different time. Of the 44 recorded September replies, Ilmi's
    "Sure Let's get together on Monday at 2 CTS that works for me" matched the
    opening-word regex: that is a request to MOVE the call, and treating it as
    a confirmation both kills the safety net and leaves the old time armed.
    """
    out = []  # type: List[Dict[str, Any]]
    booking_rec = (state.cadence or {}).get("booking") or {}
    appointment_id = booking_rec.get("appointment_id")
    start = booking_rec.get("slot")
    if appointment_id:
        no_show = _optional("no_show")
        if no_show is not None:
            try:
                rec = store.get(no_show.state_key(appointment_id)) or {}
                if rec.get("state") == "no_show":
                    cancelled = no_show.cancel_recovery(store, appointment_id, "replied")
                    out.append({"hook": "no_show.cancel_recovery", "appointment_id": appointment_id, "cancelled": cancelled})
            except Exception as exc:  # noqa: BLE001
                logger.warning("no_show.cancel_recovery failed: %s", exc)
    upcoming = False
    if start:
        try:
            upcoming = slots.parse_iso(start) > now
        except (ValueError, TypeError):
            upcoming = False
    label = getattr(classification, "label", None) if classification is not None else None
    reschedules = False
    if appointment_id and upcoming:
        if classification is not None and _names_a_different_time(classification, start or ""):
            reschedules = True
        else:
            reschedules = _text_names_another_time(core, start, now)
    # The label alone is not enough. classification defaults to None here, and
    # eleven of the 44 recorded September replies are auto-responders whose
    # FIRST WORDS match _CONFIRM_RE ("Sure, thanks for reaching out. I am
    # currently out of the office..."). Any of those would have marked the call
    # confirmed and disarmed the 4 h "no C yet" safety net. Read the body with
    # the markers classify.py already owns, whatever the classifier said.
    ooo_body = _body_is_out_of_office(core)
    if label in NON_CONFIRMING_LABELS or reschedules or ooo_body:
        if appointment_id and upcoming:
            if reschedules:
                reason = "reschedule_request"
            elif label in NON_CONFIRMING_LABELS:
                reason = "label:%s" % label
            else:
                reason = "ooo_body"
            out.append({"hook": "confirmation_skipped", "appointment_id": appointment_id,
                        "reason": reason})
    elif appointment_id and upcoming and _looks_like_confirmation(core):
        show_rate = _optional("show_rate")
        if show_rate is not None:
            try:
                _mark_confirmed(show_rate, store, appointment_id, now, start)
                booking_rec = dict(booking_rec, confirmed_at=now.isoformat())
                state.cadence = dict(state.cadence, booking=booking_rec)
                out.append({"hook": "show_rate.mark_confirmed", "appointment_id": appointment_id, "at": now.isoformat()})
            except Exception as exc:  # noqa: BLE001
                logger.warning("show_rate.mark_confirmed failed: %s", exc)
    return out


# Slot rules only Lorenzo can waive: the time the lead asked for is real and free,
# it just breaks his own 12:00-18:00 / weekday / 4 h / 5-business-day policy. These
# go to him as approve-or-counter instead of being silently counter-proposed.
OVERRIDABLE_STATUSES = ("outside_window", "weekend", "too_soon", "beyond_horizon")


def _already_booked_body(state: LeadState, slot_iso: str, booking_link: Optional[str], answer: Optional[str] = None) -> str:
    """The "we already have a call" reply. What it may say about the invite
    depends on the booking record, not on the fact that a slot exists:

    * awaiting_approval - the confirmation that booked it never went out (the
      card was superseded by this reply), so the lead has heard nothing and the
      invite is still withheld. This card takes the booking over, and its send
      is what releases the invite: "invite on the way", never "on your
      calendar".
    * invite_released False - the confirmation went out but GHL did not release
      the invite: no invite claim at all.
    * anything else (released, or a record that predates the flags): unchanged.
    """
    when = slot_iso
    try:
        when = "%s CT" % slots.format_slot(slots.to_tz(slots.parse_iso(slot_iso)))
    except (ValueError, TypeError):
        pass
    booking = (state.cadence or {}).get("booking") or {}
    first = state.first_name or "there"
    parts = ["Hey %s," % first, ""]
    if answer:
        parts += [answer, ""]
    if booking.get("awaiting_approval"):
        line = "You are locked in for %s, invite on the way." % when
    elif booking.get("invite_released") is False:
        line = "We are already set for %s." % when
    else:
        line = "We are already set for %s and the invite is on your calendar." % when
    parts += [line, "", "Lorenzo"]
    return "\n".join(parts)


def _already_booked_template_id(state: LeadState, slot_iso: str, answer: Optional[str] = None) -> Optional[str]:
    """booking.already_booked.<awaiting_approval|invite_withheld|invite_on_calendar>,
    the catalogued text _already_booked_body writes, chosen by the same booking
    record test. None when an answer paragraph is inserted (that body is not
    catalogued) or the slot does not parse (the body falls back to the raw
    ISO string). An id string only."""
    if answer:
        return None
    try:
        slots.format_slot(slots.to_tz(slots.parse_iso(slot_iso)))
    except (ValueError, TypeError):
        return None
    booking = (state.cadence or {}).get("booking") or {}
    if booking.get("awaiting_approval"):
        variant = "awaiting_approval"
    elif booking.get("invite_released") is False:
        variant = "invite_withheld"
    else:
        variant = "invite_on_calendar"
    return "booking.already_booked.%s" % variant


def _already_booked_bindings(state: LeadState, slot_iso: str, booking_link: Optional[str]) -> Dict[str, str]:
    """{placeholder: value} for what _already_booked_body wrote: the lead's
    first name (when on file) and the call time. No booking link (section 2)."""
    out = {}  # type: Dict[str, str]
    if state.first_name:
        out["first_name"] = state.first_name
    try:
        out["slot"] = slots.format_slot(slots.to_tz(slots.parse_iso(slot_iso)))
    except (ValueError, TypeError):
        pass
    return out


def _note_settlement_outcome(st, approval, handoff: Optional[Dict[str, Any]]) -> bool:
    """Record on the stored card what the settlement actually did when it is
    not what the card note announced (a cancel GHL refused, or an error). The
    alert for it has already gone out; this keeps the card itself honest.
    Rationale is not part of the signed draft hash, so the token stands.

    A status-guarded write (approval._transition): only while the card is
    still in the status read here, and it changes the note on the card as
    stored then, nothing else. The whole card read before used to be written
    back unguarded, so an approval that moved it to sending in between was
    undone: the card was pending again, and a second tap could send the reply
    twice. A card that moved on keeps its state and gets no note. True when
    the note was written. Never raises."""
    if not handoff or handoff.get("action") in ("transferred", "released"):
        return False
    try:
        approval_id = approval.token.split(".", 1)[0]
        raw = st.get(approval_mod.APPROVAL_PREFIX + approval_id)
        if not isinstance(raw, dict) or not raw:
            return False
        status = raw.get("status")
        if handoff.get("action") == "release_pending":
            note = ("UPDATE: GHL refused to cancel the call for %s. It is still on the calendar with its reminders "
                    "held, and the cancel is being retried" % handoff.get("slot"))
        else:
            note = "UPDATE: the booking for %s could not be settled (%s); check the calendar by hand" % (
                handoff.get("slot"), handoff.get("error"))
        written = {}  # type: Dict[str, Any]

        def _with_note(current: Dict[str, Any]) -> Dict[str, Any]:
            draft = dict(current.get("draft") or {})
            draft["rationale"] = "%s; %s" % (draft.get("rationale") or "", note)
            written["rationale"] = draft["rationale"]
            return dict(current, draft=draft)

        if not approval_mod._transition(st, approval_id, (status,), _with_note):
            logger.warning("did not note the settlement outcome on card %s: it moved on from %s", approval_id, status)
            return False
        approval.draft.rationale = written.get("rationale") or approval.draft.rationale
        return True
    except Exception as exc:  # noqa: BLE001 - bookkeeping on the card must not fail the reply
        logger.warning("could not note the settlement outcome on the card: %s", exc)
        return False


def _future_booking_slot(state: LeadState, now: datetime) -> Optional[str]:
    """This lead's own confirmed call, when it is still ahead of us. A booking
    whose GHL cancel failed and is being retried is not a call to restate."""
    booking = (state.cadence or {}).get("booking") or {}
    iso = booking.get("slot")
    if not iso or booking.get("cancel_failed"):
        return None
    try:
        return iso if slots.parse_iso(iso) > now else None
    except (ValueError, TypeError):
        return None


def _names_a_different_time(classification, slot_iso: str) -> bool:
    proposed = classification.extracted.proposed_time
    if not proposed:
        return bool(classification.extracted.availability_window)
    try:
        return int(slots.parse_iso(proposed).timestamp()) != int(slots.parse_iso(slot_iso).timestamp())
    except (ValueError, TypeError):
        return True


def _already_booked_draft(event: ReplyEvent, classification, state: LeadState, slot_iso: str, booking_link,
                          core: Optional[str] = None) -> Draft:
    """The reply to a lead whose call is already on the calendar.

    The old guard lived inside the names-a-time branch, so "C", "Confirmed, see
    you then." and any logistics question from a booked lead fell through to
    build_draft and were answered with two brand new call times - and two more
    slots reserved - for someone who already had a call that week.

    ``core`` is the lead's own words. Testing ``event.text`` for "?" read
    Lorenzo's OWN quoted cold email ("Does Wednesday at 2pm or Thursday at 4pm
    Central work?"), so Sopio - already booked, writing only to restate her
    availability - was sent the minimum-to-start pitch as a non sequitur.
    """
    words = core if core is not None else core_text(event.text or "")
    asks = bool(classification.extracted.question_type in ("pricing", "mechanism", "send_info")) or "?" in (words or "")
    answer = answer_paragraph(event, classification) if asks else None
    body = _already_booked_body(state, slot_iso, booking_link, answer=answer)
    key = campaign_key_for(event)
    return Draft(subject=reply_subject(event.subject), body_text=body, offered_slots=[slot_iso],
                 booking_link=None, model="template", label=classification.label,
                 rationale="already booked for %s; answered without offering new times" % slot_iso,
                 problems=validate_draft(body, booking_link=None, campaign_key=key,
                                         allow_terms=lead_terms(event, state)),
                 template_id=_already_booked_template_id(state, slot_iso, answer))


# A reply that merely contains a parseable time is not a yes. These two cues say
# the time belongs to someone else, or to a "maybe later", and the engine must
# not put a real appointment on the calendar for either.
_THIRD_PARTY_RE = re.compile(
    r"\b(not me|wrong person|not the right person)\b|"
    r"\b(our|my|the)\s+(office manager|assistant|partner|colleague|boss|owner|manager|director|controller|bookkeeper|scheduler|team)\b",
    re.I,
)
_DEFERRAL_RE = re.compile(
    r"\b(maybe|perhaps|circle back|touch base|check back|follow up|revisit|reconnect|down the road|"
    r"not (right )?now|another time|some other time|already (have|work with|use|using)|we'?re (all )?set)\b",
    re.I,
)


def _booking_blocked_reason(classification, core: str) -> Optional[str]:
    """Why this reply must not auto-book, even though it names a compliant time."""
    if classification.label == "positive_referral":
        return "referral: the time belongs to someone else"
    if _THIRD_PARTY_RE.search(core or ""):
        return "names a third party, not the replier"
    if _DEFERRAL_RE.search(core or ""):
        return "carries a deferral cue, not an acceptance"
    return None


def _bookable_grid(now: datetime, busy_blocks, others_offered, ghl=None) -> Optional[List[str]]:
    """Times that are actually free.

    booking.evaluate_reply was called with free_slots=None, so compliance() alone
    decided a time was bookable: the engine booked over calls already on
    Lorenzo's calendar and over slots reserved for another lead's pending
    approval, and counter-proposed those same slots.

    With a GHL token the grid comes from the REAL calendar. Handing
    booking.book an assumed Mon-Fri 12:00-18:00 grid made booking.verify_slot's
    GHL branch dead code (it only asks GHL when free_slots is None), so a reply
    naming a time GHL knows is taken was booked over the existing event and the
    prospect was mailed "Locked in ..., invite on the way." Returns None when a
    token exists but the calendar could not be read, so the caller lets
    verify_slot do its own lookup rather than inventing availability.
    """
    grid = free_slots_from_ghl(ghl, now) if getattr(ghl, "has_token", False) else None
    source = "ghl"
    if grid is None:
        if getattr(ghl, "has_token", False):
            logger.warning("GHL has a token but free-slots came back empty; deferring to booking.verify_slot")
            return None
        grid = fallback_free_slots(now, busy_blocks=busy_blocks or ())
        source = "fallback"
    logger.debug("bookable grid from %s: %d slots", source, len(grid))
    taken = set()
    for iso in others_offered or ():
        try:
            taken.add(int(slots.parse_iso(iso).timestamp()))
        except (ValueError, TypeError):
            continue
    out = []  # type: List[str]
    for iso in grid:
        try:
            key = int(slots.parse_iso(iso).timestamp())
        except (ValueError, TypeError):
            continue
        if key not in taken:
            out.append(iso)
    return out


def _ensure_appointment_id(state: LeadState) -> Optional[str]:
    """Give a shadow booking a deterministic local appointment id.

    booking._extract_id returns None for every guarded write, so in shadow
    cadence['booking']['appointment_id'] was always None and _appointment_hooks
    (show_rate.mark_confirmed, no_show.cancel_recovery) could never fire. Since
    shadow is the only mode Lorenzo allows before go-live, those two couplings
    would first have run for real in production.
    """
    cad = dict(state.cadence or {})
    rec = dict(cad.get("booking") or {})
    if not rec.get("slot") or rec.get("appointment_id"):
        return rec.get("appointment_id")
    digest = hashlib.sha1(("%s|%s" % (state.key, rec["slot"])).encode("utf-8")).hexdigest()[:12]
    rec["appointment_id"] = "shadow-appt-%s" % digest
    rec["appointment_id_synthetic"] = True
    cad["booking"] = rec
    state.cadence = cad
    return rec["appointment_id"]


def _mark_confirmed(show_rate, store, appointment_id: str, now: datetime, start_iso: Optional[str]) -> None:
    """show_rate.mark_confirmed gained an optional start_iso so the flag is
    scoped to the time that was confirmed; call it either way."""
    try:
        show_rate.mark_confirmed(store, appointment_id, now, source="reply_c", start_iso=start_iso)
    except TypeError:  # older show_rate without start_iso
        show_rate.mark_confirmed(store, appointment_id, now, source="reply_c")


def _text_names_another_time(core: str, start_iso: Optional[str], now: datetime) -> bool:
    """True when the BODY proposes a time that is not the booked one, so the
    reply is a reschedule request rather than a confirmation. The classifier's
    own extraction is checked first (``_names_a_different_time``); this is the
    backstop for the case it missed, which is the one that cost Ilmi's call."""
    if not core:
        return False
    try:
        proposed = slots.parse_proposed_time(core, now)
    except Exception:  # noqa: BLE001
        return False
    if proposed is None:
        return False
    if not start_iso:
        return True
    try:
        return abs((slots.to_tz(proposed) - slots.to_tz(slots.parse_iso(start_iso))).total_seconds()) > 60
    except (ValueError, TypeError):
        return True


def _classification_allows_auto(classification) -> bool:
    """The template gate's classification rule (a positive label, confidence
    at or above the floor, not the fallback classifier), for the pre-check
    before a draft is built. Any error is False."""
    try:
        template_gate._check_classification(classification)
        return True
    except Exception:  # noqa: BLE001 - a refusal or an error: not auto
        return False


def _first_reply_pre_check(event: ReplyEvent, classification) -> bool:
    """True when the first reply's template is approved (kill switch,
    parity and statuses: template_gate.ids_verdict) and the classification
    passes: the draft is then built from the template alone (no LLM polish),
    so the text that auto-sends is exactly the approved one. The full verdict
    still runs on the finished draft. Never raises; False on any error."""
    try:
        tid = first_reply_template_id(event, classification)
        if tid is None:
            return False
        return bool(template_gate.ids_verdict(tid).allowed) and _classification_allows_auto(classification)
    except Exception as exc:  # noqa: BLE001 - the pre-check only decides whether to polish
        logger.warning("template pre-check failed: %s", type(exc).__name__)
        return False


def _reply_draft(event: ReplyEvent, classification, state: LeadState, deps: "Deps", now: datetime, store,
                 busy_blocks, core: str, info: Optional[Dict[str, Any]] = None):
    """The draft for one inbound reply, plus the requested-time override (if any)
    and the BookingResult (when the reply booked the call).

    A reply that names a time goes through services.reply_engine.booking first:
    bookable -> book it and confirm; blocked by Lorenzo's own rule -> counter,
    with the asked-for time attached so the card can offer it; already booked ->
    restate the booking rather than offer new times.

    ``info`` (CT3), when given, is filled with the template gate's "kind"
    ("booking" for a confirmation, counter-proposal or already-booked reply,
    else "first_reply") and the "bindings" of every value the draft rendered.
    """
    info = info if info is not None else {}
    info.update(kind="first_reply", bindings={})
    booking = _optional("booking")
    ex = classification.extracted
    names_time = bool(ex.proposed_time or ex.availability_window)
    existing = (state.cadence or {}).get("booking") or {}
    booking_link = settings.BOOKING_URL
    campaign_key = campaign_key_for(event)
    # Computed BEFORE the booking branch: the booking path used to return before
    # these existed, so the global offered-slot registry and Lorenzo's busy
    # blocks were silently discarded for every reply that named a time.
    already = approval_mod.offered_slots(store, now)
    others = approval_mod.offered_slots(store, now, exclude_lead=event.lead_email)

    booked_slot = _future_booking_slot(state, now)
    if booked_slot and not _names_a_different_time(classification, booked_slot):
        info.update(kind="booking", bindings=_already_booked_bindings(state, booked_slot, booking_link))
        return _already_booked_draft(event, classification, state, booked_slot, booking_link, core=core), None, None
    # The previous call's GHL cancel failed and is being retried: neither
    # restate it nor book over it (book() would treat it as a reschedule).
    cancel_pending = approval_mod.cancel_pending(state)

    if booking is not None and names_time and not cancel_pending:
        free = _bookable_grid(now, busy_blocks, others, ghl=deps.ghl)
        try:
            # subject= feeds booking.looks_like_auto_responder, which is its
            # strongest robot signal ("Automatic reply:", "Out of Office").
            # Without it only classify's rule layer stood between an
            # auto-responder that happens to contain a date and a booked call.
            match = booking.evaluate_reply(core, state.offered_slots, now, free_slots=free,
                                           subject=event.subject or "")
        except TypeError:  # older booking.evaluate_reply without subject=
            match = booking.evaluate_reply(core, state.offered_slots, now, free_slots=free)
        except Exception as exc:  # noqa: BLE001 - never let the matcher lose a reply
            logger.warning("booking.evaluate_reply failed: %s", exc)
            match = None
        if match is not None and match.status != booking.NO_TIME:
            blocked = _booking_blocked_reason(classification, core)
            if match.bookable and not existing.get("slot") and not blocked:
                # the same availability view the matcher used, so booking.verify_slot
                # cannot disagree with the decision that got us here
                try:
                    # store=: the booking reserves its own slot against every
                    # other lead, writes the appointment:<id> row the 07:30
                    # sweep reads and the appt:<id> row the Zoom webhook
                    # resolves joins through, and arms the show-rate sequence.
                    result = booking.book(state, match.slot, deps.ghl, deps.instantly, now=now, lead_tz=match.lead_tz,
                                          free_slots=free, store=store)
                except TypeError:  # older booking.book without free_slots/store
                    result = booking.book(state, match.slot, deps.ghl, deps.instantly, now=now, lead_tz=match.lead_tz)
                _ensure_appointment_id(state)
                draft = result.draft
                # zoom_not_connected is stripped on purpose (a note, never a
                # blocker); the template id already tells the Zoom-link and
                # no-Zoom-link confirmations apart, each approved on its own.
                draft.problems = [p for p in list(draft.problems or []) if p != approval_mod.ZOOM_NOT_CONNECTED]
                bindings = {}  # type: Dict[str, str]
                if str(getattr(draft, "template_id", None) or "").startswith("booking.confirmation."):
                    bindings = booking.confirmation_bindings(state, result.slot, match.lead_tz, result.zoom_link)
                info.update(kind="booking", bindings=bindings)
                if result.zoom_not_connected:
                    draft.rationale = "%s; Zoom is not connected to the GHL calendar, the invite carries the Meet link" % draft.rationale
                pipeline_errors = list(getattr(result, "pipeline_errors", None) or [])
                if pipeline_errors:
                    # Booked, pipeline update failed: the call and its held
                    # ladder exist, only the CRM bookkeeping is behind. Said on
                    # the card and pushed, as Book-as-asked does.
                    draft.rationale = "%s; BOOKED, PIPELINE UPDATE FAILED: %s. Fix it by hand in GHL / Instantly" % (
                        draft.rationale, "; ".join(pipeline_errors))
                    approval_mod._alert(
                        "Booked, pipeline update failed for %s" % event.lead_email,
                        "The call for %s is on the calendar, but: %s. Fix the stage / interest by hand."
                        % (result.slot.isoformat(), "; ".join(pipeline_errors)))
                return draft, None, result
            if match.bookable and existing.get("slot"):
                info.update(kind="booking", bindings=_already_booked_bindings(state, existing["slot"], booking_link))
                return _already_booked_draft(event, classification, state, existing["slot"], booking_link, core=core), None, None
            if match.bookable and blocked:
                logger.info("not auto-booking %s: %s", event.lead_email, blocked)
            else:
                body = booking.counter_proposal_text(match, state)
                if body:
                    requested = None
                    if match.proposed is not None and match.status in OVERRIDABLE_STATUSES:
                        requested = {"slot": match.proposed.isoformat(), "status": match.status, "lead_tz": match.lead_tz}
                    info.update(kind="booking", bindings=booking.counter_bindings(match, state))
                    # No booking link on a counter-proposal (Lorenzo, 2026-09-23).
                    return Draft(subject=reply_subject(event.subject), body_text=body,
                                 offered_slots=[c.isoformat() for c in match.counter_slots[:2]], booking_link=None,
                                 model="template", label=classification.label,
                                 rationale="counter-proposal (%s: %s)" % (match.status, match.reason),
                                 problems=validate_draft(body, booking_link=None, campaign_key=campaign_key,
                                                         allow_terms=lead_terms(event, state)),
                                 template_id=booking.counter_template_id(match)), requested, None
    # CT3: an approved template with a classification the gate accepts is
    # built from the template alone (use_llm=False), so the auto-sent text is
    # exactly what Lorenzo approved. Otherwise the draft is a card and the
    # polish (when a real model is configured) runs as before.
    pre_allowed = _first_reply_pre_check(event, classification)
    draft = build_draft(event, classification, state=state, ghl=deps.ghl, now=now, already_offered=already,
                        busy_blocks=busy_blocks, core_text=core, others_offered=others,
                        use_llm=False if pre_allowed else None)
    info.update(kind="first_reply", bindings=first_reply_bindings(event, classification, draft, state=state),
                pre_allowed=pre_allowed)
    if cancel_pending:
        # CT3 (Lorenzo's decision): never auto-sent while the old call is
        # still being cancelled; _run_pipeline turns the verdict into
        # cancel_pending. Not a draft problem: the card stays approvable.
        info["cancel_pending"] = True
        draft.rationale = ("%s; this lead's previous call (%s) is still being cancelled in GHL (the cancel failed "
                           "and is retrying): check the calendar before sending"
                           % (draft.rationale, existing.get("slot")))
    return draft, None, None


# ------------------------------------------------------------ reply claim
CLAIM_PREFIX = "replyclaim:"
# How long a claim that never completed blocks a retry. Only a hard kill (a
# Modal container timeout) leaves one behind: an ordinary exception releases it
# on the way out.
CLAIM_STALE_MINUTES = 15
# A content fingerprint is time-independent so the same reply matches across
# ingestion paths. That also means a genuinely repeated body collapses onto the
# first one's key, and state.processed_keys is kept forever, so a lead sending
# "Any update on this?" in September and again three days later got
# {'skipped': 'duplicate'} - no classification, no draft, no card, no CRM note.
# The cross-source race this exists for happens within minutes.
DEDUPE_WINDOW_HOURS = 6


def _claim_key(state_key: str, dedupe_key: str) -> str:
    return "%s%s|%s" % (CLAIM_PREFIX, state_key, dedupe_key)


def _claim_is_duplicate(record: Dict[str, Any], dedupe_key: str, ts: datetime) -> Optional[str]:
    """Why an existing claim blocks this reply, or None when it may be retried."""
    if not isinstance(record, dict):
        return "duplicate"
    try:
        at = slots.parse_iso(record.get("at"))
    except (ValueError, TypeError):
        at = None
    if record.get("done"):
        if is_content_key(dedupe_key):
            if at is not None and (ts - at).total_seconds() > DEDUPE_WINDOW_HOURS * 3600:
                return None  # same words, days apart: a real new nudge
        return "duplicate"
    # claimed but never finished: another worker is on it, or a container died
    if at is not None and (ts - at).total_seconds() > CLAIM_STALE_MINUTES * 60:
        return None
    return "in_flight"


def _claim_reply(st, state_key: str, keys: List[str], ts: datetime):
    """Single-winner claim across every identity this reply is known by.

    process_event used to read the lead state, decide it was not a duplicate and
    write it back with two separate store calls. shared/store.py provides
    set_if_absent/add_once precisely so an once-only decision is one operation
    ("Every once-only decision (a processed reply id, a slot reservation) must
    go through one of these"), and approval._claim_send already uses it. Two
    overlapping poller ticks - a */5 schedule and a tick that takes longer than
    five minutes - both read the same rows and both processed them: two GHL
    write sets, two Instantly interest writes, two cards and four reserved slots
    for one inbound email.

    Returns (claimed_keys, reason). ``reason`` is set when the claim was lost.
    """
    claimed = []  # type: List[str]
    record = {"at": ts.isoformat(), "done": False}
    for dedupe_key in keys:
        ck = _claim_key(state_key, dedupe_key)
        setter = getattr(st, "set_if_absent", None)
        won = True
        if callable(setter):
            try:
                won = bool(setter(ck, record))
            except Exception as exc:  # noqa: BLE001 - a broken claim must not lose the reply
                logger.warning("reply claim failed for %s: %s", ck, exc)
                won = True
        if won:
            claimed.append(ck)
            continue
        reason = _claim_is_duplicate(st.get(ck) or {}, dedupe_key, ts)
        if reason is None:
            try:
                st.set(ck, record)  # stale or outside the dedupe window: take it over
            except Exception as exc:  # noqa: BLE001
                logger.warning("reply re-claim failed for %s: %s", ck, exc)
            claimed.append(ck)
            continue
        for done in claimed:  # give back the ones we did win
            _release_claims(st, [done])
        return [], reason
    return claimed, None


def _release_claims(st, claimed: List[str]) -> None:
    for ck in claimed:
        try:
            st.delete(ck)
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not release the reply claim %s: %s", ck, exc)


def _complete_claims(st, claimed: List[str], ts: datetime) -> None:
    for ck in claimed:
        try:
            st.set(ck, {"at": ts.isoformat(), "done": True})
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not complete the reply claim %s: %s", ck, exc)


def process_event(event: ReplyEvent, deps: Optional[Deps] = None, now: Optional[datetime] = None, busy_blocks=None) -> Dict[str, Any]:
    deps = deps or DEPS
    st = deps.store
    ts = slots.to_tz(slots.ensure_aware(now)) if now is not None else deps.now()
    key = event.state_key
    base_raw = st.get(key)
    state = LeadState.from_store(base_raw, event)
    # Idempotency keys on a stable content identity (Instantly's message_id, or
    # a fingerprint of the lead, thread and body), not only on the provider id:
    # the same reply arriving as an id-less webhook and again from the poller
    # used to book the call twice and raise two cards.
    keys = event.dedupe_keys
    # A synthesised webhook id ('wh:<email>:<ts>') is not evidence of anything:
    # two different replies in the same second share it, and the second would be
    # dropped as a duplicate. Only a real provider id counts on its own.
    synthetic_id = is_synthetic_email_id(event.email_id)
    if not synthetic_id and event.email_id in state.processed_email_ids:
        return {"skipped": "duplicate", "email_id": event.email_id, "state_key": key, "label": None}

    # Claim the reply before anything touches GHL, Instantly or the approval
    # store - but as IN FLIGHT, not as processed. Writing processed_email_ids up
    # front made poller's failure-retry path (FAILED_KEY) a no-op: a reply whose
    # classify() raised once came back on the next tick, hit its own claim,
    # answered {'skipped': 'duplicate'} - which the poller counts as a success,
    # so it cleared the retry record and advanced the cursor - and was retired
    # for good without ever being classified, drafted or shown.
    claimed, lost = _claim_reply(st, key, keys, ts)
    if lost is not None:
        return {"skipped": "duplicate" if lost == "duplicate" else lost, "email_id": event.email_id,
                "state_key": key, "label": None}
    # What the pipeline learns about this reply (its received time, label and
    # whether it is stale), for the under-lock decisions of its write, the
    # partial one below included.
    ctx = {}  # type: Dict[str, Any]
    try:
        return _run_pipeline(event, deps, ts, st, key, state, keys, claimed, busy_blocks, base_raw=base_raw,
                             ctx=ctx)
    except Exception:
        # Persist whatever the half-run pipeline already wrote (most importantly
        # a booking), so the retry sees it and does not book a second time, then
        # let the reply be reprocessed. A three-way merge like every lead-row
        # write, with the inbound's stop applied to the row as it stands, and
        # an opt-out marker set but never cleared. A stale reply (one sent
        # before the lead's opt-out, or before a newer reply of theirs) has
        # nothing to keep: saving its copy would mark it processed without its
        # alert, so its retry records it again.
        ctx["partial"] = True
        if not ctx.get("stale"):
            try:
                approval_mod.save_lead_state(st, state, base_raw,
                                             finish=_inbound_stop_hook(event, state, base_raw, ts, ctx))
            except Exception as exc:  # noqa: BLE001
                logger.warning("could not persist the partial state for %s: %s", key, exc)
        _release_claims(st, claimed)
        raise


def _hold_cards_for_opt_out(st, key: str, state: LeadState, event: ReplyEvent, label: Optional[str],
                            ts: datetime, newer: Optional[Dict[str, Any]] = None) -> List[str]:
    """Block the lead's open cards when this reply is an opt-out or a final
    no (router.OPT_OUT_LABELS). The cards are read from the row as just
    written (a card raised by a concurrent pipeline is on it) and from this
    pipeline's copy. ``newer``: the lead's newest reply sent after this one
    and processed first (_reply_after_this_opt_out), which the HELD push then
    names (the no still stands). Never raises."""
    if str(label or "").lower() not in OPT_OUT_LABELS:
        return []
    try:
        tokens = list(state.approvals or [])
        try:
            row = st.get(key) or {}
        except Exception as exc:  # noqa: BLE001 - this pipeline's copy still lists its cards
            logger.warning("could not re-read %s to hold its cards: %s", key, exc)
            row = {}
        tokens += [t for t in (row.get("approvals") or []) if t not in tokens]
        why = {"reason": "opt_out", "category": str(label).lower(),
               "at": event.received_at.isoformat() if event.received_at else None, "email_id": event.email_id}
        if newer:
            why["newer_reply"] = dict(newer)
        return approval_mod.hold_cards_for_lead_reply(st, tokens, why, now=ts, lead=event.lead_email)
    except Exception as exc:  # noqa: BLE001 - the send-time check still holds every card
        logger.warning("could not hold the open cards of %s after an opt-out: %s", event.lead_email, exc)
        return []


def _inbound_entry(event: ReplyEvent, classification, ts: datetime, ctx: Dict[str, Any],
                   stale: Optional[str] = None) -> Dict[str, Any]:
    """The lead's history entry for this reply. ``at`` is when the engine
    processed it; ``received_at`` (ISO UTC) is when the lead sent it: the
    email's own time, or, when the payload carried none, the processing time
    with ``received_at_source: "processing"``. ``stale`` marks a stale reply
    with its reason (router.stale_reason: sent before the lead's opt-out,
    "opt_out", or before a newer reply of theirs, "older_than_newest_reply"):
    it changed nothing, and the cadence's inbound readers skip it.
    ``names_time`` (only when true): the reply proposed a call time, one
    time or a range of hours (its classification's proposed_time or
    availability_window), so an older reply read later can tell the lead's
    newer word on the time from a reply that did not touch it."""
    entry = {"at": ts.isoformat(), "event": "inbound", "email_id": event.email_id, "label": classification.label,
             "source": event.source, "received_at": iso_utc(ctx["received_at"])}
    if ctx.get("received_at_source") == RECEIVED_AT_PROCESSING:
        entry["received_at_source"] = RECEIVED_AT_PROCESSING
    if stale:
        entry["stale"] = stale
    extracted = getattr(classification, "extracted", None)
    if extracted is not None and (extracted.proposed_time or extracted.availability_window):
        entry["names_time"] = True
    return entry


def _run_pipeline(event: ReplyEvent, deps: Deps, ts: datetime, st, key: str, state: LeadState,
                  keys: List[str], claimed: List[str], busy_blocks,
                  base_raw: Optional[Dict[str, Any]] = None, ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ctx = ctx if ctx is not None else {}
    received, received_source = reply_received_at(event, ts)
    ctx.update(received_at=received, received_at_source=received_source)

    classification = classify(event)
    ctx["label"] = classification.label
    # A reply processed late (a poller retry after it raised, or a reply a
    # killed run still held) that the lead sent before their opt-out, or, not
    # being an opt-out, before a newer reply of theirs already on the row, is
    # recorded and rewrites nothing (_record_stale_reply): no card of the
    # lead's is superseded, no booked call moves, no follow-up stops, and no
    # card is drafted that its send-time check would only hold. An older
    # reply that proposes a call time books nothing, and the lead's open card
    # that names other times is held until Lorenzo edits it. Decided before
    # anything on the row moves, the cadence stop included.
    stale = stale_reason(state, classification.label, received, received_source, email_id=event.email_id)
    ctx["stale"] = stale
    if stale:
        return _record_stale_reply(event, deps, ts, st, key, state, keys, claimed, classification, base_raw, ctx)

    state.last_email_id = event.email_id

    # any new inbound reply stops a running cadence (needs_fresh_draft=True)
    cadence_stopped = None
    if (state.cadence or {}).get("armed_at") and not (state.cadence or {}).get("stopped_reason"):
        cadence_stopped = _stop_cadence_for_inbound(state, ts)
    needs_fresh_draft = bool((state.cadence or {}).get("needs_fresh_draft"))

    # Supersede AFTER classification and only when this reply produces a
    # replacement. It used to run unconditionally, first: a lead's positive card
    # was retired by the out-of-office their shared info@ mailbox fired two
    # minutes later (24 of the 44 recorded replies come from auto-responders on
    # shared boxes), nothing replaced it, pending_approvals never listed it
    # because it only reports status == 'pending', and the button already on
    # Lorenzo's phone answered "already superseded".
    superseded = (approval_mod.supersede_pending(st, state, ts)
                  if (state.approvals and classification.needs_draft) else [])
    actions = route(event, classification, state, deps.ghl, deps.instantly, now=ts, store=st, stale=None)
    core = core_text(event.text)
    if classification.extracted.phone and not state.phone:
        state.phone = classification.extracted.phone

    hooks = _appointment_hooks(state, core, st, ts, classification)

    draft = None
    approval = None
    booking_result = None
    requested = None
    booking_handoff = None
    verdict = None
    draft_info = {}  # type: Dict[str, Any]
    if classification.needs_draft:
        # exclude_email: a block that IS this lead's own call must not make the
        # engine counter-propose around the appointment they are writing about.
        blocks = busy_blocks if busy_blocks is not None else busy_blocks_from_ids(exclude_email=event.lead_email)
        # A superseded card may still own an unconfirmed booking (the call is
        # on the calendar, invite withheld, show-rate ladder held). Found
        # before the draft is built so the card can say what happens to it.
        orphan_owner = approval_mod.orphaned_booking_owner(st, state, superseded)
        draft, requested, booking_result = _reply_draft(event, classification, state, deps, ts, st, blocks, core,
                                                        info=draft_info)
        if needs_fresh_draft:
            draft.rationale = "%s; fresh draft after the lead replied mid-cadence" % draft.rationale
        if superseded:
            draft.rationale = "%s; supersedes %d earlier card(s) still waiting on you" % (draft.rationale, len(superseded))
        if orphan_owner:
            # Same rule settle_superseded_booking applies below, and worded as
            # what WILL happen: the card is pushed before the settlement runs,
            # so it must not report an outcome that has not happened yet.
            held_slot = approval_mod.booking_of(state).get("slot")
            if approval_mod.will_transfer_booking(draft, held_slot, ts):
                draft.rationale = ("%s; this card takes over the call already booked for %s: approving it sends "
                                   "the invite, vetoing it cancels the call" % (draft.rationale, held_slot))
            else:
                draft.rationale = ("%s; the call the superseded card booked for %s is being released (cancelled "
                                   "in GHL without notifying the lead, who was never told about it); a separate "
                                   "alert follows if GHL refuses the cancel" % (draft.rationale, held_slot))
                if held_slot and any(approval_mod._same_slot(iso, held_slot) for iso in
                                     approval_mod.slots_named_in(draft.body_text, ts, extra=[held_slot])):
                    # The draft restates a call that is about to be released
                    # (a past booking, or one it names beside other times).
                    draft.problems = list(draft.problems) + [
                        "this draft restates the call for %s, which is being released (it has passed or the "
                        "draft names other times too); rewrite it before sending" % held_slot]
        if is_synthetic_email_id(event.email_id):
            # The id is 'wh:<email>:<ts>', which send_approved would hand to
            # instantly.reply_to_email as reply_to_uuid. `to` means it cannot be
            # mis-delivered, but a real workspace answers 4xx and the card would
            # end at send_failed, which nothing watches.
            draft.problems = list(draft.problems) + [
                "this reply arrived without an Instantly email id, so it cannot be answered in thread; "
                "reply by hand from the Instantly inbox"]
        # CT3: after every problem above, on the exact subject and body the
        # card will carry. Allowed only for an approved, unchanged template
        # with every check passing; anything else is an ordinary card.
        verdict = _template_verdict(draft, draft_info, classification, event, state, requested, booking_result)
        if draft_info.get("cancel_pending"):
            verdict = _not_while_cancel_pending(verdict)
        state.drafts.append(draft)
        approval = _create_card(state, draft, event, st, ts, requested, verdict)
        approval_id = approval.token.split(".")[0]
        if booking_result is not None and approval_mod.owns_booking(approval, state):
            # This card booked the call: it owns it until it is sent, vetoed or
            # expired, or until a newer reply supersedes it.
            approval_mod.claim_booking(state, approval_id, ts)
            approval_mod.record_booking_intent(st, approval, state)
        if orphan_owner:
            booking_handoff = approval_mod.settle_superseded_booking(
                st, state, approval, ts, ghl=deps.ghl, instantly=deps.instantly, superseded=superseded,
                old_owner=orphan_owner)
            _note_settlement_outcome(st, approval, booking_handoff)
        state.status = "draft_pending_approval"

    state.last_subject = event.subject
    state.eaccount = event.eaccount or state.eaccount
    state.thread_id = event.thread_id or state.thread_id
    state.first_name = event.first_name or state.first_name
    state.company = event.company or state.company
    state.campaign_key = event.campaign_key or state.campaign_key
    state.history.append(_inbound_entry(event, classification, ts, ctx))
    # The pipeline finished: only now is the reply "processed". A crash before
    # this point releases the claim and the poller's retry does real work.
    if event.email_id not in state.processed_email_ids:
        state.processed_email_ids.append(event.email_id)
    for k in keys:
        if k not in state.processed_keys:
            state.processed_keys.append(k)
    # Under the row's lock, as a three-way merge: any booking field, stop
    # field, card or processed id another writer changed since this pipeline
    # read the row is kept (a cancel retry finishing mid-reply used to be
    # undone here, cancel_failed booking and all), a ladder an approval
    # armed in the meantime is stopped for this reply, and the opt-out marker
    # is set or cleared against the one stored (_inbound_stop_hook).
    approval_mod.save_lead_state(st, state, base_raw, finish=_inbound_stop_hook(event, state, base_raw, ts, ctx))
    _complete_claims(st, claimed, ts)
    # An opt-out or a final no holds every open card of the lead's now, not
    # only at the next send (a queued card never expires, and one approved
    # before this reply sat in the queue until 07:00). Only after the row is
    # written: the send re-checks the row once its card is "sending", and a
    # card in that state is left to that check, so one of the two sees the
    # other. A failure here loses nothing: the send-time check still holds.
    # An opt-out the lead sent before a newer reply of theirs that was
    # processed first still takes effect (it is never stale): the HELD push
    # names that newer reply, and when no card was left to hold (the answer
    # to it already went out) one push says what was applied.
    newer = _reply_after_this_opt_out(st, key, state, event, classification.label, ctx)
    cards_held = _hold_cards_for_opt_out(st, key, state, event, classification.label, ts, newer=newer)
    late_opt_out = None
    if newer and not cards_held:
        late_opt_out = _late_opt_out_alert(st, key, state, event, classification.label, ctx, newer, cadence_stopped)
    # CT3: an allowed card sends now, through the one send path (approve ->
    # send_approved), which re-runs the gate and every send check. After the
    # row is written: send_approved reads the stored lead row. A failure here
    # loses nothing: the card is pending with its push deferred, and the
    # poller's orphan sweep pushes it.
    auto_send = _auto_send(approval, verdict, deps, st, ts)

    result = {
        "state_key": key,
        "lead_email": event.lead_email,
        "campaign_key": event.campaign_key,
        "email_id": event.email_id,
        "label": classification.label,
        "confidence": classification.confidence,
        "method": classification.method,
        "reason": classification.reason,
        "extracted": classification.extracted.model_dump(),
        "actions": [a.model_dump() for a in actions],
        "draft": draft.model_dump() if draft is not None else None,
        "cadence_stopped": cadence_stopped,
        "needs_fresh_draft": needs_fresh_draft,
        "superseded": superseded,
        "booking_handoff": booking_handoff,
        "hooks": hooks,
        "booking": booking_result.to_dict() if booking_result is not None else None,
        "requested_time": requested,
        "approval_token": approval.token if approval is not None else None,
        "cards_held": cards_held,
        "status": state.status,
        "stale": None,
        "opt_out": ctx.get("opt_out"),
        "newer_reply": (newer or {}).get("email_id"),
        "late_opt_out_alert": bool(late_opt_out),
        "auto_send": auto_send,
    }
    job_log.log_run("reply_engine.process_event", "ok", {
        "lead": event.lead_email, "campaign_key": event.campaign_key, "label": classification.label,
        "confidence": classification.confidence, "method": classification.method, "source": event.source,
        "actions": ["%s.%s:%s" % (a.system, a.action, a.kind) for a in actions],
        "draft": bool(draft), "approval": approval.token.split(".")[0] if approval else None,
        "opt_out": ctx.get("opt_out"),
        "template_id": getattr(draft, "template_id", None) if draft is not None else None,
        "auto": ({"allowed": bool(verdict.allowed), "reason": verdict.reason} if verdict is not None else None),
    })
    return result


def _template_verdict(draft: Draft, info: Dict[str, Any], classification, event: ReplyEvent, state: LeadState,
                      requested: Optional[Dict[str, Any]], booking_result) -> "template_gate.Verdict":
    """Stamp the draft with its template's current hash, then the gate's
    verdict on it. kind "booking" for a booking confirmation, a
    counter-proposal or an already-booked reply, else "first_reply". Never
    raises: any error is a refusal (registry_error), so the reply is a card."""
    tid = getattr(draft, "template_id", None)
    try:
        kind = info.get("kind") or ("booking" if booking_result is not None else "first_reply")
        template_gate.stamp(draft, tid)
        bindings = dict((k, v) for k, v in (info.get("bindings") or {}).items() if v is not None)
        return template_gate.draft_verdict(
            draft, kind=kind, campaign_key=campaign_key_for(event), allow_terms=lead_terms(event, state),
            classification=classification, requested=requested, bindings=bindings)
    except Exception as exc:  # noqa: BLE001 - the gate fails closed: a card
        logger.warning("template verdict failed for %s: %s", tid, type(exc).__name__)
        return template_gate.Verdict(False, "registry_error", tid, [tid] if tid else [], {}, type(exc).__name__)


# The verdict reason for a first reply held back because the lead's previous
# call is still being cancelled in GHL (cancel_failed, retrying). Its card
# note is approval.REASON_TEXT["cancel_pending"].
CANCEL_PENDING_REASON = "cancel_pending"


def _not_while_cancel_pending(verdict: "template_gate.Verdict") -> "template_gate.Verdict":
    """Lorenzo's rule: a reply is never auto-sent while the lead's previous
    call is still being cancelled in GHL. Whatever the gate said, the verdict
    becomes not-allowed with reason cancel_pending, so the reply is an
    ordinary card (approvable at any hour: no draft problem is added)."""
    return dataclasses.replace(verdict, allowed=False, reason=CANCEL_PENDING_REASON)


def _create_card(state: LeadState, draft: Draft, event: ReplyEvent, st, ts: datetime,
                 requested: Optional[Dict[str, Any]], verdict) -> Any:
    """The card, with the verdict: an allowed one defers the push to the
    auto-send below (approval.create_approval(auto=...))."""
    return approval_mod.create_approval(state, draft, event, store=st, now=ts, requested=requested,
                                        campaign_key=campaign_key_for(event), auto=verdict)


def _auto_send(approval, verdict, deps: Deps, st, ts: datetime) -> Optional[Dict[str, Any]]:
    """Send an allowed card through approval.auto_send_approved. The record
    returned (and put in the result) carries the reason, the template id and
    the send outcome's status only. Never raises."""
    if verdict is None:
        return None
    record = {"allowed": bool(verdict.allowed), "reason": verdict.reason, "template_id": verdict.template_id,
              "status": None}
    if approval is None or not verdict.allowed:
        return record
    try:
        out = approval_mod.auto_send_approved(approval, deps.instantly, store=st, now=ts, ghl=deps.ghl,
                                              verdict=verdict)
        record["status"] = (out or {}).get("status") if isinstance(out, dict) else None
        record["ok"] = bool((out or {}).get("ok")) if isinstance(out, dict) else False
    except Exception as exc:  # noqa: BLE001 - the orphan sweep pushes the card
        logger.warning("template auto-send failed for card %s: %s", approval.token.split(".")[0], type(exc).__name__)
        record["status"] = "error"
        record["error"] = type(exc).__name__
    return record


def _when(value: Any) -> str:
    """A time for an alert, with its date, in CT."""
    try:
        return approval_mod._slot_label(value if isinstance(value, str) else value.isoformat())
    except Exception:  # noqa: BLE001 - the wording must never fail the reply
        return str(value)


def _stale_reply_alert(event: ReplyEvent, label: str, state: LeadState, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """The one push for a reply sent before the lead's opt-out (the round-4
    contract's wording in the title). Never raises."""
    marker = state.opt_out if isinstance(state.opt_out, dict) else {}
    title = "An older reply from %s arrived after their opt-out; not drafted" % event.lead_email
    opted = "time not recorded"
    if marker.get("received_at"):
        opted = _when(marker.get("received_at"))
        if marker.get("received_at_source") == RECEIVED_AT_PROCESSING:
            opted = "seen %s, no send time of its own" % opted
    opt_out = "%s, %s" % (marker.get("label") or "opt-out", opted)
    if ctx.get("received_at_source") == RECEIVED_AT_PROCESSING:
        when = ("It carried no send time of its own (seen %s, %s), so it cannot be shown to come after their "
                "opt-out (%s)" % (_when(ctx.get("received_at")), label, opt_out))
    else:
        when = ("It was sent %s (%s), before their opt-out (%s), and processed after it"
                % (_when(ctx.get("received_at")), label, opt_out))
    removal = " The removal request in it was still applied." if label in BLOCKLIST_LABELS else ""
    message = ("Nothing was sent and no card was drafted. %s, so the lead's status, classification and follow-ups "
               "stay as the opt-out left them.%s It is on the lead's history; read it in the Instantly inbox to see "
               "what they wrote." % (when, removal))
    return approval_mod._alert(title, message, priority="high")


def _row_now(st, key: str, state: LeadState) -> Dict[str, Any]:
    """The lead's row as stored now, or this pipeline's copy of it when the
    store cannot be read. For an alert's wording only."""
    try:
        row = st.get(key)
        if isinstance(row, dict) and row:
            return row
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not re-read %s for an alert: %s", key, exc)
    try:
        return state.to_store()
    except Exception:  # noqa: BLE001
        return {}


def _lead_cards(st, row: Dict[str, Any], state: LeadState) -> List[Any]:
    """The lead's cards as stored (the row's approvals, then any only this
    pipeline's copy lists), one per approval id. An unreadable card is left
    out."""
    out = []  # type: List[Any]
    seen = set()  # type: set
    for token in list(row.get("approvals") or []) + list(state.approvals or []):
        approval_id = str(token or "").split(".", 1)[0]
        if not approval_id or approval_id in seen:
            continue
        seen.add(approval_id)
        try:
            card = approval_mod._approval_row(st, approval_id)
        except Exception:  # noqa: BLE001
            card = None
        if card is not None:
            out.append(card)
    return out


# The statuses of a lead's card that is still open: it can still go out
# (pending, approved_queued), or its send started and has not finished
# (sending).
_OPEN_STATUSES = ("pending", "approved_queued", "sending")
# What an older reply's push says of an open card of the lead's when the
# older reply proposes no call time. A card at sending is worded from its
# send claim (_sending_words).
_OPEN_CARD_WORDS = {
    "pending": "is still open and can be approved and sent as usual",
    "approved_queued": "is still approved and goes out when the sending window opens",
}
# The start of the problem an older reply's proposed time puts on a card
# that names other times (_time_conflict_problem).
_TIME_CONFLICT_PREFIX = "the lead's older reply (sent "


def _sending_words(st, card, ts: datetime) -> str:
    """What the older reply's push says of a card at sending, from its send
    claim (approval.send_claim_lease): "is being sent" only while its send
    may still be running; past the lease the card is stuck, and the push
    says so and what that means. Never raises."""
    try:
        lease = approval_mod.send_claim_lease(card, st, ts)
    except Exception as exc:  # noqa: BLE001 - the wording must never fail the reply
        logger.warning("could not read the send claim of %s: %s", approval_mod._approval_id(card), exc)
        return "is at sending, and its send claim could not be read, so it may or may not have gone out"
    if lease.get("state") == "running":
        return "is being sent (its send started %s)" % _when(lease["started"])
    if lease.get("state") == "stale":
        return ("has been stuck at sending since %s: its send started and never finished, so it may or may not have "
                "gone out (check the Instantly thread, then press Mark sent if it went out, or Retry if it did not)"
                % _when(lease["started"]))
    return ("is stuck at sending, and the engine has no record of when its send started, so it may or may not have "
            "gone out (check the Instantly thread before you do anything with it)")


def _time_asked(label: Optional[str], classification) -> Optional[Dict[str, Any]]:
    """The call time a reply of the lead's own proposes, from its
    classification (classify.extract, read against when the lead sent it):
    {"slot": ISO CT} for one time, {"window": {"start_hour", "end_hour",
    "tz"}} for a range of hours. None for an automatic reply, a no, or a
    reply that names no time."""
    norm = str(label or "").strip().lower()
    if norm in MACHINE_LABELS or norm in OPT_OUT_LABELS:
        return None
    extracted = getattr(classification, "extracted", None)
    if extracted is None:
        return None
    if extracted.proposed_time:
        try:
            return {"slot": slots.to_tz(slots.ensure_aware(slots.parse_iso(extracted.proposed_time))).isoformat()}
        except (ValueError, TypeError):
            pass
    window = extracted.availability_window
    if isinstance(window, dict) and window.get("start_hour") is not None and window.get("end_hour") is not None:
        return {"window": dict(window)}
    return None


def _window_zone(window: Dict[str, Any]):
    """The time zone of a proposed range of hours; one that cannot be read
    is CT, as slots.parse_availability_window defaults it."""
    try:
        return pytz.timezone(str(window.get("tz") or ""))
    except Exception:  # noqa: BLE001
        return slots.TZ


def _clock(dt: datetime) -> str:
    return "%d:%02d%s" % ((dt.hour % 12) or 12, dt.minute, "am" if dt.hour < 12 else "pm")


def _asked_label(asked: Dict[str, Any], sent: Any) -> str:
    """The time an older reply proposed, in CT: "at Thu Sep 24 3:00pm CT",
    or for a range of hours "between 2:00pm and 5:00pm CT", taken on the day
    the lead sent it (a range carries no day of its own)."""
    if asked.get("slot"):
        return "at %s" % _when(asked["slot"])
    window = asked.get("window") or {}
    zone = _window_zone(window)
    try:
        day = slots.ensure_aware(sent).astimezone(zone)
        midnight = datetime(day.year, day.month, day.day)
        start = zone.localize(midnight + timedelta(hours=int(window["start_hour"])))
        end = zone.localize(midnight + timedelta(hours=int(window["end_hour"])))
        return "between %s and %s CT" % (_clock(slots.to_tz(start)), _clock(slots.to_tz(end)))
    except Exception:  # noqa: BLE001 - the wording must never fail the reply
        return "between %s:00 and %s:00 (%s)" % (window.get("start_hour"), window.get("end_hour"), window.get("tz"))


def _card_times(card) -> List[str]:
    """The times a card offers or restates (its draft's offered_slots, which
    Edit keeps in step with the body)."""
    return [str(iso) for iso in (getattr(card.draft, "offered_slots", None) or []) if iso]


def _offers_time(times: List[str], asked: Dict[str, Any]) -> bool:
    """Does one of a card's times answer the time the lead proposed: the same
    minute for one time, a time inside the hours for a range? An unreadable
    time answers nothing."""
    for iso in times or ():
        try:
            offered = slots.ensure_aware(slots.parse_iso(iso))
            if asked.get("slot"):
                proposed = slots.ensure_aware(slots.parse_iso(asked["slot"]))
                if abs((offered - proposed).total_seconds()) < 60:
                    return True
                continue
            window = asked.get("window") or {}
            local = offered.astimezone(_window_zone(window))
            if float(window["start_hour"]) <= local.hour + local.minute / 60.0 < float(window["end_hour"]):
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _newer_reply_named_a_time(row: Dict[str, Any], received_at: datetime, email_id: Any) -> bool:
    """Did a reply of the lead's own, sent after ``received_at``, propose a
    call time itself (its history entry's names_time)? That reply is their
    newer word on the time, and their cards follow it. Never raises."""
    try:
        return any(entry.get("names_time") for entry in newer_replies(row, received_at, email_id=email_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not read the lead's newer replies for a proposed time: %s", exc)
        return False


def _standing_no(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The lead's no in force on the row, as the send-time check reads it
    (approval.lead_reply_hold, its opt-out arm): the sticky marker, a status
    in router.OPT_OUT_STATUSES, or an opt-out label as the latest
    classification. Returns {"label", "at", "processing", "status"}: the
    no's label and when the lead sent it (``processing`` when only the time
    it was processed is known), from the marker, else from the latest reply
    on the history with an opt-out label; or None when the row carries no
    no."""
    status = str(row.get("status") or "").strip().lower()
    marker = row.get("opt_out") if isinstance(row.get("opt_out"), dict) and row.get("opt_out") else None
    classification = row.get("classification") if isinstance(row.get("classification"), dict) else {}
    latest = str(classification.get("label") or "").strip().lower()
    if not (marker or status in OPT_OUT_STATUSES or latest in OPT_OUT_LABELS):
        return None
    source = marker
    if source is None:
        for entry in reversed(row.get("history") or []):
            if (isinstance(entry, dict) and entry.get("event") == "inbound" and not entry.get("stale")
                    and str(entry.get("label") or "").strip().lower() in OPT_OUT_LABELS):
                source = entry
                break
    source = source or {}
    label = str(source.get("label") or (latest if latest in OPT_OUT_LABELS else "")).strip().lower()
    return {"label": label or None, "at": source.get("received_at"),
            "processing": source.get("received_at_source") == RECEIVED_AT_PROCESSING, "status": status or None}


def _standing_sentence(standing: Dict[str, Any]) -> str:
    """The lead's no in force, as the HELD push words it: "the lead asked to
    be removed (unsubscribe, sent Mon Sep 28 9:00am CT), that answer still
    stands, and their status stays blocklisted". A no known only from the
    status: "their status stays blocklisted, a no that still stands"."""
    label, status = standing.get("label"), standing.get("status")
    if not label:
        return "their status stays %s, a no that still stands" % (status or "unknown")
    said = approval_mod._LEAD_SAID.get(label, "gave a final no")
    if standing.get("at"):
        when = ("seen %s, no send time of its own" if standing.get("processing") else "sent %s") % _when(standing["at"])
        told = "the lead %s (%s, %s)" % (said, label, when)
    else:
        told = "the lead %s (%s)" % (said, label)
    return "%s, that answer still stands%s" % (told, ", and their status stays %s" % status if status else "")


def _time_conflict_problem(asked: Dict[str, Any], ctx: Dict[str, Any], times: List[str]) -> str:
    """The problem an older reply's proposed time puts on a card that names
    other times. It is not one of booking.NON_COPY_PROBLEMS, so an Edit
    clears it as it clears a copy problem (approval.edit); until then a send
    refuses the card and states it (approval.send_approved)."""
    return ("%s%s, read only after this card was drafted) proposed a call %s, and this card names other times (%s); "
            "nothing was booked for it. Edit the card to answer that time, or to keep these times (the edit clears "
            "this), or reply by hand"
            % (_TIME_CONFLICT_PREFIX, _when(ctx.get("received_at")), _asked_label(asked, ctx.get("received_at")),
               ", ".join(_when(iso) for iso in times)))


def _mark_time_conflicts(st, key: str, state: LeadState, asked: Dict[str, Any],
                         ctx: Dict[str, Any]) -> Dict[str, str]:
    """An older reply that proposes a call time (``asked``) books nothing,
    and the lead's open card that names other times answers as if it had
    never come. Each such card (pending or approved_queued, with times of
    which none is the proposed one) gets _time_conflict_problem, written
    once and status-guarded on the card as stored (approval._transition).
    A send refuses a card with a problem and says why, the approve page
    states it, the queue does not send it, and an Edit clears it. A card at
    sending is past this (its send checked its problems before it started):
    the push words it. Only for a lead with no no in force on the row, and
    no newer reply of theirs that proposed a time itself (the caller
    checks). Returns {approval_id: problem} for the cards that carry it.
    Never raises."""
    out = {}  # type: Dict[str, str]
    try:
        row = st.get(key) or {}
    except Exception as exc:  # noqa: BLE001 - this pipeline's copy still lists the cards
        logger.warning("could not re-read %s to mark its cards: %s", key, exc)
        row = {}
    for card in _lead_cards(st, row, state):
        times = _card_times(card)
        if card.status not in approval_mod.SENDABLE_STATUSES or not times or _offers_time(times, asked):
            continue
        approval_id = approval_mod._approval_id(card)
        problem = _time_conflict_problem(asked, ctx, times)

        def _add(current: Dict[str, Any], problem: str = problem) -> Dict[str, Any]:
            draft = dict(current.get("draft") or {})
            problems = list(draft.get("problems") or [])
            if problem not in problems:
                problems.append(problem)
            draft["problems"] = problems
            return dict(current, draft=draft)

        try:
            if approval_mod._transition(st, approval_id, approval_mod.SENDABLE_STATUSES, _add):
                out[approval_id] = problem
            else:
                logger.warning("card %s moved on before the older reply's time could be marked on it", approval_id)
        except Exception as exc:  # noqa: BLE001 - the push says the card is not marked
            logger.warning("could not mark the older reply's time on card %s: %s", approval_id, exc)
    return out


def _open_card_line(st, card, lead: LeadState, slot: Optional[str], newest_id: str, asked: Optional[Dict[str, Any]],
                    conflict: bool, own_time: bool, standing: Optional[Dict[str, Any]], marked: Dict[str, str],
                    ts: datetime):
    """One open card's sentence in the older-reply push, from the card as
    stored. Returns (sentence, edit_it, offers_it): ``edit_it`` when
    Lorenzo must Edit the card before it can go out (it carries the time
    mark, or should and could not be marked), ``offers_it`` when one of its
    times answers the proposed one."""
    approval_id = approval_mod._approval_id(card)
    which = "Card %s" % approval_id
    if newest_id and str(card.email_id or "") == newest_id:
        which += ", which answers their newer reply,"
    times = _card_times(card)
    offers_it = bool(asked) and _offers_time(times, asked)
    other = bool(asked) and bool(times) and not offers_it
    names = "names other times (%s)" % ", ".join(_when(iso) for iso in times)
    call = ""
    if slot and approval_mod.owns_booking(card, lead):
        call = ", and sending it confirms the call booked for %s" % approval_mod._slot_label(slot)
    if card.status == "sending":
        line = "%s %s" % (which, _sending_words(st, card, ts))
        if conflict and other:
            line += "; it %s" % names
        return line + ".", False, offers_it
    if standing:
        where = "is still open" if card.status == "pending" else "is approved and queued"
        return ("%s %s, but no reply goes out to them while that answer stands: the send holds it." % (which, where),
                False, offers_it)
    carries = approval_id in marked or any(str(p).startswith(_TIME_CONFLICT_PREFIX)
                                           for p in (card.draft.problems or []))
    holds = (" It holds the call booked for %s: its Edit page asks whether to keep that call or release it."
             % approval_mod._slot_label(slot)) if call else ""
    if carries:
        if card.status == "approved_queued":
            return ("%s was approved, but it %s, so it is held until you Edit it: the queue will not send it as it "
                    "is.%s" % (which, names, holds), True, offers_it)
        return ("%s %s, so it is held until you Edit it: approving it as it is is refused.%s" % (which, names, holds),
                True, offers_it)
    if conflict and other:
        goes = ("it still goes out as it is when the sending window opens" if card.status == "approved_queued"
                else "it can still be approved as it is")
        return ("%s %s, and the engine could not mark it as held: %s, so Edit it first.%s"
                % (which, names, goes, holds), True, offers_it)
    if asked:
        where = ("is still open" if card.status == "pending"
                 else "is approved and goes out when the sending window opens")
        if offers_it:
            return "%s offers that time too; it %s%s." % (which, where, call), False, True
        if own_time:
            return "%s %s and follows the time their newer reply proposed%s." % (which, where, call), False, False
        return "%s %s and names no call time%s." % (which, where, call), False, False
    return "%s %s%s." % (which, _OPEN_CARD_WORDS.get(card.status, "is still open"), call), False, offers_it


def _no_open_card_line(row: Dict[str, Any], cards: List[Any], newest_id: str, asked: Optional[Dict[str, Any]],
                       conflict: bool, standing: Optional[Dict[str, Any]]) -> str:
    """The older-reply push's sentence when no card of the lead's is open:
    the answer to their newer reply already went out (with the times it
    named when the older reply proposed another), the card answering it
    stays blocked (a lead whose no is in force), or none is open."""
    answering = [card for card in cards if newest_id and str(card.email_id or "") == newest_id]
    answered = [card for card in answering if card.status in approval_mod.SENT_STATUSES]
    if answered:
        card = answered[-1]
        text = "The answer to their newer reply already went out (card %s)" % approval_mod._approval_id(card)
        times = _card_times(card)
        if conflict and times and not _offers_time(times, asked or {}):
            text += ", naming other times (%s)" % ", ".join(_when(iso) for iso in times)
        cad = row.get("cadence") or {}
        if cad.get("armed_at") and not cad.get("stopped_reason"):
            text += "; the follow-ups it started keep running"
        return text + "."
    blocked = [card for card in answering if card.status == "blocked"]
    if standing and blocked:
        return "Card %s, which answers their newer reply, stays blocked." % approval_mod._approval_id(blocked[-1])
    return "No card of theirs is open."


def _older_reply_alert(st, key: str, event: ReplyEvent, label: str, state: LeadState, ctx: Dict[str, Any],
                       ts: datetime, asked: Optional[Dict[str, Any]] = None,
                       marked: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """The one push for a reply the lead sent before a newer human reply of
    theirs that was processed first (router.STALE_OLDER_REPLY): its label,
    when it was sent, the newer reply it came before, and that nothing
    moved and nothing new was drafted. Then, from the row and the cards as
    stored:

    * the call time it proposed (``asked``), in CT, and that nothing was
      booked for it. A card of theirs that names other times carries the
      time mark (``marked``, _mark_time_conflicts) and is held until Lorenzo
      edits it: never "sendable as usual". When a newer reply of theirs
      proposed a time itself, their cards follow that one;
    * where each open card stands (_open_card_line; a card at sending from
      its send claim, _sending_words), or that the answer to the newer reply
      already went out;
    * what to do. A lead whose no is in force on the row (_standing_no) is
      told as the HELD push tells it: that answer stands, read the whole
      thread, and approval.opt_out_advice. Never "reply by hand", and never
      that the newer reply set the row.

    An automatic reply (router.MACHINE_LABELS) needs nothing, so its push is
    low priority. Never raises: the reply is already recorded."""
    title = "An older reply from %s arrived after their newer one; not drafted" % event.lead_email
    machine = str(label or "").strip().lower() in MACHINE_LABELS
    marked = dict(marked or {})
    when = _when(ctx.get("received_at"))
    try:
        row = _row_now(st, key, state)
        found = newer_replies(row, ctx["received_at"], email_id=event.email_id)
        newest = found[-1] if found else {}
        newest_id = str(newest.get("email_id") or "")
        newer = ("their newer reply (%s, sent %s)" % (newest.get("label") or "unlabelled",
                                                      _when(newest.get("received_at")))
                 if newest else "a newer reply of theirs")
        standing = _standing_no(row)
        if standing:
            kept = _standing_sentence(standing)
        else:
            kept = ("their status, classification, booked call and follow-ups stay as they were, and no card of "
                    "theirs was superseded")
        own_time = bool(asked) and not standing and _newer_reply_named_a_time(row, ctx["received_at"],
                                                                                event.email_id)
        conflict = bool(asked) and not standing and not own_time
        time_text = ""
        if asked:
            time_text = " It proposed a call %s; nothing was booked for it." % _asked_label(asked, ctx["received_at"])
            if own_time:
                time_text += " A newer reply of theirs proposed a time of its own, and their cards follow that one."
        lead = LeadState.from_store(row)
        slot = approval_mod.booking_of(lead).get("slot")
        cards = _lead_cards(st, row, state)
        open_cards = [card for card in cards if card.status in _OPEN_STATUSES]
        lines = []  # type: List[str]
        to_edit = []  # type: List[str]
        offered = False
        for card in open_cards:
            line, edit_it, offers_it = _open_card_line(st, card, lead, slot, newest_id, asked, conflict, own_time,
                                                       standing, marked, ts)
            lines.append(line)
            offered = offered or offers_it
            if edit_it:
                to_edit.append(approval_mod._approval_id(card))
        if not open_cards:
            lines.append(_no_open_card_line(row, cards, newest_id, asked, conflict, standing))
        if machine:
            todo = "It is an automatic reply, so nothing needs doing."
        elif standing:
            todo = ("Read the whole thread in Instantly before anything else goes to them. %s"
                    % approval_mod.opt_out_advice(standing.get("label") or standing.get("status")))
        elif to_edit:
            todo = ("Read it in the Instantly inbox, then Edit card %s: answer the time they proposed (and book that "
                    "call in GHL if it stands), or keep its times. The edit clears the hold. Or reply by hand."
                    % ", ".join(to_edit))
        elif conflict and not offered:
            todo = ("Read it in the Instantly inbox and answer the time they proposed by hand (and book that call in "
                    "GHL if it stands).")
        elif any(card.status == "pending" for card in open_cards):
            todo = ("Read it in the Instantly inbox: if it asks something the open card does not answer, Edit that "
                    "card before you approve it, or reply by hand.")
        else:
            todo = ("Read it in the Instantly inbox: if it asks something the answer to their newer reply does not "
                    "cover, reply by hand.")
        cards_text = " ".join(lines)
    except Exception as exc:  # noqa: BLE001 - the wording must never fail the reply
        logger.warning("could not word the older-reply push for %s: %s", event.lead_email, exc)
        newer, time_text = "a newer reply of theirs", ""
        kept = "no card of theirs was superseded and no call was booked"
        cards_text = "The engine could not read the lead's cards for this push."
        if marked:
            cards_text = ("Card %s names other times than the one this reply proposed, so it is held until you Edit "
                          "it." % ", ".join(sorted(marked)))
        todo = "Read it in the Instantly inbox, and the lead's cards, before you approve one."
    message = ("Nothing was sent and no new card was drafted. The lead sent it %s (%s), before %s, and it was "
               "processed after that reply, so nothing moved: %s.%s %s It is on the lead's history. %s"
               % (when, label, newer, kept, time_text, cards_text, todo))
    return approval_mod._alert(title, message, priority="low" if machine else "high")


def _reply_after_this_opt_out(st, key: str, state: LeadState, event: ReplyEvent, label: Optional[str],
                              ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """For an opt-out or a final no (router.OPT_OUT_LABELS) that carries the
    email's own time: the lead's newest reply that is not a no, SENT after it
    and already on the row (router.newer_replies), as {"email_id", "label",
    "at"}. None otherwise; an opt-out with only a processing time cannot be
    shown to come first. Read from the row as just written. Never raises."""
    if str(label or "").lower() not in OPT_OUT_LABELS:
        return None
    if ctx.get("received_at") is None or ctx.get("received_at_source") == RECEIVED_AT_PROCESSING:
        return None
    try:
        found = newer_replies(_row_now(st, key, state), ctx["received_at"], email_id=event.email_id,
                              include_opt_outs=False)
    except Exception as exc:  # noqa: BLE001 - the wording must never fail the reply
        logger.warning("could not look for a newer reply of %s: %s", event.lead_email, exc)
        return None
    if not found:
        return None
    entry = found[-1]
    return {"email_id": entry.get("email_id"), "label": entry.get("label") or "unlabelled",
            "at": entry.get("received_at")}


def _late_opt_out_alert(st, key: str, state: LeadState, event: ReplyEvent, label: str, ctx: Dict[str, Any],
                        newer: Dict[str, Any], cadence_stopped: Optional[str]) -> Optional[Dict[str, Any]]:
    """The one push for an opt-out or a final no the lead sent before a newer
    reply of theirs (``newer``) that was processed first, when it held no
    card: the answer to that newer reply already went out, or nothing was
    open. The no took effect as any no does (the status, a removal's
    blocklist, the follow-ups stopped), and nothing else would say so. None
    when a card of theirs is still open (it holds a send claim, so the
    arrival hold left it to its send): that send re-checks the row, holds the
    card and pushes the HELD alert, which names the newer reply. Never
    raises."""
    try:
        row = _row_now(st, key, state)
        cards = _lead_cards(st, row, state)
        if any(card.status in _OPEN_STATUSES for card in cards):
            return None
        norm = str(label or "").lower()
        said = approval_mod._LEAD_SAID.get(norm, "gave a final no")
        cad = row.get("cadence") or {}
        stopped = bool(cadence_stopped) or bool(cad.get("armed_at") and cad.get("stopped_reason"))
        answered = [card for card in cards if str(card.email_id or "") == str(newer.get("email_id") or "")
                    and card.status in approval_mod.SENT_STATUSES]
        if answered:
            held = ("The answer to their newer reply had already gone out (card %s), so no card was held."
                    % approval_mod._approval_id(answered[-1]))
        else:
            held = "No card of theirs was open, so no card was held."
        message = ("Nothing was sent. The lead %s (%s, sent %s) before their newer reply (%s, sent %s), and the "
                   "engine processed it after that reply. It took effect: their status is now %s%s. %s Read the "
                   "whole thread in Instantly before anything else goes to them. %s"
                   % (said, norm, _when(ctx.get("received_at")), newer.get("label") or "unlabelled",
                      _when(newer.get("at")), row.get("status") or state.status,
                      " and the follow-ups are stopped" if stopped else "", held,
                      approval_mod.opt_out_advice(norm)))
        return approval_mod._alert("An older opt-out from %s arrived after their newer reply; applied"
                                   % event.lead_email, message, priority="high")
    except Exception as exc:  # noqa: BLE001 - the wording must never fail the reply
        logger.warning("could not send the late opt-out push for %s: %s", event.lead_email, exc)
        return None


def _record_stale_reply(event: ReplyEvent, deps: Deps, ts: datetime, st, key: str, state: LeadState,
                        keys: List[str], claimed: List[str], classification, base_raw: Optional[Dict[str, Any]],
                        ctx: Dict[str, Any]) -> Dict[str, Any]:
    """A stale reply (router.stale_reason), processed only now: one the lead
    sent before their opt-out (LeadState.opt_out), or one that is not an
    opt-out, sent before a newer human reply of theirs already on the row,
    whatever order they were processed in.

    It is recorded on the history (marked ``stale`` with its reason) and its
    ids are marked processed. Nothing else: no draft and no card, so no card
    of the lead's is superseded and none is raised that its send-time check
    would only hold; no booked call taken, moved or released; no status,
    classification, last_email_id or last_inbound_at change; no cadence stop
    or arm; no appointment hook; no hold of the lead's cards. route() runs in
    its stale mode (a removal request in it is still applied; an
    auto-responder's hand-off is still queued). One alert tells Lorenzo
    (_stale_reply_alert, _older_reply_alert). The marker itself is settled
    under the lock by the same rules as for any reply: a reply sent before it
    never moves it, a human reply sent after it clears it.

    An older reply (router.STALE_OLDER_REPLY) that proposes a call time
    books nothing, and marks each open card of the lead's that names other
    times with that problem (_mark_time_conflicts), so it cannot go out as
    it is: not when the lead's no is in force on the row, and not when a
    newer reply of theirs proposed a time itself (their newer word on the
    time). Marked before the row is written: a crash after it leaves the
    reply to its retry, which marks nothing twice."""
    stale = ctx.get("stale")
    actions = route(event, classification, state, deps.ghl, deps.instantly, now=ts, store=st, stale=stale)
    asked = _time_asked(classification.label, classification) if stale == STALE_OLDER_REPLY else None
    marked = {}  # type: Dict[str, str]
    if asked:
        row_now = _row_now(st, key, state)
        if not _standing_no(row_now) and not _newer_reply_named_a_time(row_now, ctx["received_at"], event.email_id):
            marked = _mark_time_conflicts(st, key, state, asked, ctx)
    state.history.append(_inbound_entry(event, classification, ts, ctx, stale=stale))
    if event.email_id not in state.processed_email_ids:
        state.processed_email_ids.append(event.email_id)
    for k in keys:
        if k not in state.processed_keys:
            state.processed_keys.append(k)
    approval_mod.save_lead_state(st, state, base_raw, finish=_inbound_stop_hook(event, state, base_raw, ts, ctx))
    _complete_claims(st, claimed, ts)
    logger.warning("reply %s from %s was sent before %s: recorded, not drafted", event.email_id, event.lead_email,
                   "a newer reply of theirs" if stale == STALE_OLDER_REPLY else "their opt-out")
    # After the write and the claims: a crash before this point retries the
    # reply, one after it cannot send the push twice.
    if stale == STALE_OLDER_REPLY:
        alert = _older_reply_alert(st, key, event, classification.label, state, ctx, ts, asked=asked, marked=marked)
    else:
        alert = _stale_reply_alert(event, classification.label, state, ctx)
    result = {
        "state_key": key,
        "lead_email": event.lead_email,
        "campaign_key": event.campaign_key,
        "email_id": event.email_id,
        "label": classification.label,
        "confidence": classification.confidence,
        "method": classification.method,
        "reason": classification.reason,
        "extracted": classification.extracted.model_dump(),
        "actions": [a.model_dump() for a in actions],
        "draft": None,
        "cadence_stopped": None,
        "needs_fresh_draft": bool((state.cadence or {}).get("needs_fresh_draft")),
        "superseded": [],
        "booking_handoff": None,
        "hooks": [],
        "booking": None,
        "requested_time": None,
        "approval_token": None,
        "cards_held": [],
        "status": state.status,
        "stale": stale,
        "stale_alert": bool(alert),
        "opt_out": ctx.get("opt_out"),
        "time_asked": asked,
        "cards_marked": sorted(marked),
    }
    job_log.log_run("reply_engine.process_event", "ok", {
        "lead": event.lead_email, "campaign_key": event.campaign_key, "label": classification.label,
        "confidence": classification.confidence, "method": classification.method, "source": event.source,
        "actions": ["%s.%s:%s" % (a.system, a.action, a.kind) for a in actions],
        "draft": False, "approval": None, "stale": stale, "received_at": iso_utc(ctx["received_at"]),
        "opt_out": ctx.get("opt_out"), "cards_marked": sorted(marked),
    })
    return result


# ------------------------------------------------------------------ app
@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    """One store for the whole process: the Zoom router reads
    ``request.app.state.store`` and the cadence / appointment ticks run against
    the same instance, so a join written by a webhook is visible to the tick."""
    try:
        fastapi_app.state.store = DEPS.store
    except Exception as exc:  # noqa: BLE001 - a store that cannot be built must not stop the service
        logger.error("store unavailable at startup: %s", exc)
        fastapi_app.state.store = None
    yield


app = FastAPI(title="Advero Reply Engine", version="0.1.0", lifespan=lifespan)


def webhook_secret() -> str:
    """The value the X-Advero-Secret header must carry.

    Two names were in play and they never met: changesets/instantly_webhooks.py
    mints the header from REPLY_ENGINE_SECRET, runbooks/deployment.md documents
    it as <REPLY_ENGINE_SECRET> and modal_app.SECRET_KEYS ships only
    REPLY_ENGINE_SECRET, while this module validated against WEBHOOK_SECRET,
    which no deploy path sets. At go-live every reply_received delivery would
    have been refused 401 and the only reason replies were not lost is that the
    5-minute poller is the real ingestion path. WEBHOOK_SECRET still wins when
    it is set, so a deployment that does split them keeps working.
    """
    return (os.environ.get("WEBHOOK_SECRET", "").strip()
            or os.environ.get("REPLY_ENGINE_SECRET", "").strip())


def _secret_ok(provided: Optional[str]) -> bool:
    """The webhook secret is mandatory.

    This used to return True when the secret was unset, so an unauthenticated
    POST could drive a workspace-wide Instantly blocklist and a GHL dnd tag on
    any address it named.
    """
    expected = webhook_secret()
    if not expected:
        logger.error("neither WEBHOOK_SECRET nor REPLY_ENGINE_SECRET is set; refusing every webhook "
                     "until one is configured")
        return False
    return bool(provided) and hmac.compare_digest(str(provided), expected)


def _debug_ok(provided: Optional[str]) -> bool:
    expected = os.environ.get("DEBUG_SECRET", "").strip() or webhook_secret()
    return bool(expected) and bool(provided) and hmac.compare_digest(str(provided), expected)


def _query_secret_allowed() -> bool:
    """A secret in the query string lands in proxy and platform access logs and
    in the Referer of anything the page links to, and the /state path carries
    the lead's email address beside it. The header is the only accepted form in
    live; the query fallback stays for local and shadow work."""
    return not settings.is_live()


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "mode": settings.get_mode(), "live": settings.is_live(), "auto_send_after_minutes": approval_mod.auto_send_minutes(),
            "ghl_token": bool(os.environ.get("GHL_PRIVATE_INTEGRATION_TOKEN")), "webhook_secret": bool(webhook_secret()),
            # the same resolver the links use: localhost counts as unset
            "base_url_set": approval_mod.configured_base_url() is not None,
            "approval_channels": approval_mod.deliverable_channels(),
            # CT3: parity, kill switch and approved counts; no ids, no text.
            # Built per request (never at import), and it never raises.
            "templates": template_gate.health_summary()}


@app.post("/webhooks/instantly")
async def instantly_webhook(request: Request, x_advero_secret: Optional[str] = Header(default=None), secret: Optional[str] = Query(default=None)):
    if not _secret_ok(x_advero_secret or (secret if _query_secret_allowed() else None)):
        raise HTTPException(status_code=401, detail="bad secret")
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="invalid JSON")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="expected an object")
    event_type = payload.get("event_type") or payload.get("event") or "reply_received"
    if event_type in IGNORED_EVENT_TYPES:
        return {"ok": True, "ignored": event_type}
    try:
        event = ReplyEvent.from_webhook(dict(payload, event_type=event_type))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail="cannot normalise payload: %s" % exc)
    if not event.lead_email:
        raise HTTPException(status_code=422, detail="lead_email missing")
    # The allowlist used to be guarded by `if event.campaign_id`, so a payload
    # that simply omitted the field skipped it entirely and could route any
    # address through the blocklist path.
    if not event.campaign_id or event.campaign_id not in settings.CAMPAIGN_BY_ID:
        job_log.log_run("reply_engine.webhook", "ignored_campaign", {"campaign_id": event.campaign_id, "lead": event.lead_email})
        return {"ok": True, "ignored": "campaign %s not in ids.json" % (event.campaign_id or "<missing>")}
    result = process_event(event)
    return {"ok": True, "label": result.get("label"), "status": result.get("status"), "skipped": result.get("skipped"),
            "approval": bool(result.get("approval_token"))}


def _esc(value: Any) -> str:
    """Every value interpolated into a page goes through here.

    The approval host is reachable from a push notification, and the /cadence
    and /state paths put URL segments straight into the page.
    """
    return html.escape("" if value is None else str(value), quote=True)


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    safe_title = _esc(title)
    page = ("<html><head><title>%s</title><meta name='viewport' content='width=device-width'></head>"
            "<body style='font-family:-apple-system,sans-serif;max-width:640px;margin:2rem auto;padding:0 1rem'>"
            "<h2>%s</h2>%s</body></html>") % (safe_title, safe_title, body)
    return HTMLResponse(page, status_code=status)


def _confirm_page(title: str, question: str, action_url: str, button: str, extra: str = "") -> HTMLResponse:
    """A GET that would send a customer email is a GET a link scanner can fire.

    The action lives behind this POST form instead, so following the URL - from
    the notification body, an Outlook/Gmail safe-link check or a browser
    prefetch - only ever renders a page.
    """
    body = ("<p>%s</p>%s<form method='post' action='%s'>"
            "<button type='submit' style='font-size:1.1rem;padding:.6rem 1.2rem'>%s</button></form>") % (
        _esc(question), extra, _esc(action_url), _esc(button))
    return _page(title, body)


def _stated_problems(approval) -> str:
    return "; ".join(str(p) for p in (approval.draft.problems or []))


def _refusal_advice(approval, token: str) -> str:
    """What a page adds under a card's stated problems: Edit, or reply by
    hand. Nothing for a card held for the lead's own reply
    (approval._held_for): its problem carries its own advice, and for a no
    that is Veto and do not reply, which "reply by hand" would contradict."""
    try:
        held = approval_mod._held_for(approval)
    except Exception:  # noqa: BLE001 - the plain advice stands
        held = None
    if held:
        return ""
    return ("<p>Open <a href='/edit/%s'>Edit</a> to fix the draft, or reply by hand from the Instantly inbox.</p>"
            % _esc(token))


def _not_sendable_page(approval, token: str) -> HTMLResponse:
    """A card that cannot go out as it is: its problems, and what to do."""
    if approval.status == "blocked":
        text = "This approval is blocked: %s" % _stated_problems(approval)
    else:
        text = "This reply cannot go out as it is: %s" % _stated_problems(approval)
    return _page("Not sent", "<p>%s</p>%s" % (_esc(text), _refusal_advice(approval, token)), status=400)


@app.get("/approve/{token}")
def approve_confirm(token: str):
    """Confirmation page only. The send is the POST below. A card with
    problems (a copy check, or an older reply of the lead's that proposed
    another time, app._mark_time_conflicts) gets no Send button: its send
    would be refused. The page states the problems instead, as it does for
    a blocked card."""
    approval = approval_mod.load(token, DEPS.store)
    if approval is None:
        return _page("Unknown token", "<p>Nothing to approve.</p>", status=400)
    if approval.status not in approval_mod.SENDABLE_STATUSES:
        if approval.status == "blocked" and approval.draft.problems:
            return _not_sendable_page(approval, token)
        return _page("Nothing to send", "<p>This approval is already %s.</p>" % _esc(approval.status), status=400)
    if approval.draft.problems:
        return _not_sendable_page(approval, token)
    preview = "<p><b>To:</b> %s</p><p><b>Subject:</b> %s</p><pre style='white-space:pre-wrap'>%s</pre>" % (
        _esc(approval.reply_to or approval.lead_email), _esc(approval.draft.subject), _esc(approval.draft.body_text))
    return _confirm_page("Send this reply?", "Nothing has been sent yet.", "/approve/%s" % token, "Send it", preview)


def _why(result: Dict[str, Any]) -> str:
    """The reason a page shows.

    ``result.get("error", "unknown")`` printed "unknown" for every blocked
    draft, because the blocked return carries ``problems`` and no ``error`` -
    so a prospect whose company name happens to contain a banned word produced
    a page with no hint that only /edit can recover it.
    """
    problems = result.get("problems") or []
    if problems:
        return "; ".join(str(p) for p in problems)
    return str(result.get("error") or "unknown")


def _held_page(result: Dict[str, Any]) -> HTMLResponse:
    """Nothing was sent because the recipient re-read did not confirm the lead."""
    if result.get("escalated"):
        text = ("Nothing was sent. The engine could not confirm the thread belongs to this lead (%s, attempt %s), "
                "so the card is held. Check the thread in the Instantly inbox, then retry the card or reply by hand."
                % (result.get("error"), result.get("attempts")))
    else:
        text = ("Nothing was sent. The thread re-read could not confirm the recipient (attempt %s), so the reply "
                "is held and retries on its own after %s." % (result.get("attempts"), result.get("send_after")))
    return _page("Held, not sent", "<p>%s</p>" % _esc(text), status=400)


def _invite_note(result: Dict[str, Any]) -> str:
    """Say so when the confirmation went out but the calendar invite did not."""
    invite = result.get("invite") if isinstance(result.get("invite"), dict) else {}
    if invite and not invite.get("released"):
        return ("<p><b>The calendar invite was NOT released</b> (%s). Send it by hand from GHL; the lead has "
                "been told it is on the way.</p>" % _esc(invite.get("error") or "unknown"))
    return ""


def _refused_before_queue(token: str, now: datetime) -> Optional[HTMLResponse]:
    """A card with problems, approved outside the sending window. approve()
    would queue it, and the queue's send would refuse it at 07:00 for those
    problems (send_approved), with nothing on this page but "Queued".
    Approving it as it is is refused here instead, and the page states the
    problems. Inside the window approve() refuses it itself. None when
    approve() should run: no such card, or one past its TTL (approve()
    expires it)."""
    if slots.is_send_time(now):
        return None
    approval = approval_mod.load(token, DEPS.store)
    if (approval is None or approval.status not in approval_mod.SENDABLE_STATUSES or not approval.draft.problems
            or approval_mod._expired(approval, now)):
        return None
    return _not_sendable_page(approval, token)


@app.post("/approve/{token}")
def approve_endpoint(token: str):
    now = DEPS.now()
    refused = _refused_before_queue(token, now)
    if refused is not None:
        return refused
    result = approval_mod.approve(token, DEPS.instantly, store=DEPS.store, now=now, ghl=DEPS.ghl)
    if not result.get("ok"):
        # A hold for the lead's own reply carries "held" too, with lead_reply:
        # its reason is the problem it states, not a recipient re-read.
        if result.get("held") and not result.get("lead_reply"):
            return _held_page(result)
        extra = ""
        reason = _why(result)
        if result.get("status") == "blocked":
            card = approval_mod.load(token, DEPS.store)
            if card is None:
                extra = ("<p>Open <a href='/edit/%s'>Edit</a> to fix the draft, or reply by hand from the Instantly "
                         "inbox.</p>" % _esc(token))
            else:
                if not result.get("problems") and card.draft.problems:
                    reason = "This approval is blocked: %s" % _stated_problems(card)
                extra = _refusal_advice(card, token)
        return _page("Not sent", "<p>%s</p>%s" % (_esc(reason), extra), status=400)
    if result.get("status") == "approved_queued":
        return _page("Queued", "<p>Outside 07:00-19:00 CT on a business day. It will go out after %s.</p>" % _esc(result.get("send_after")))
    note = "shadow mode: recorded as would_do, nothing was sent" if result.get("shadow") else "sent through Instantly"
    return _page("Approved", "<p>%s.</p>%s" % (_esc(note), _invite_note(result)))


# A reply that went out (through Instantly, or by hand: sent_manually) or is
# going out cannot be vetoed: a veto of a card that owns a booking cancels
# the call.
NOT_VETOABLE_STATUSES = ("sent", "sent_manually", "sending")


@app.get("/veto/{token}")
def veto_confirm(token: str):
    """Confirmation page only. The veto is the POST below.

    A veto is not a read: for a booking_confirmation card it cancels the GHL
    appointment (GHL mails the lead a cancellation), reverts the opportunity and
    rewrites the Instantly interest. /approve and /accept were moved behind a
    POST for exactly that reason and /veto was left on GET, so a browser
    prefetch, a forwarded card or a safe-link scan could silently kill a booked
    call and the reply that was going to confirm it.
    """
    approval = approval_mod.load(token, DEPS.store)
    if approval is None:
        return _page("Unknown token", "<p>Nothing to veto.</p>", status=400)
    if approval.status in NOT_VETOABLE_STATUSES:
        return _page("Nothing to veto", "<p>This approval is already %s.</p>" % _esc(approval.status), status=400)
    question = "Nothing has been cancelled yet. The draft will not be sent."
    if approval_mod.card_owns_booking(approval, DEPS.store):
        question += " The call this reply booked will also be cancelled."
    preview = "<p><b>To:</b> %s</p><pre style='white-space:pre-wrap'>%s</pre>" % (
        _esc(approval.reply_to or approval.lead_email), _esc(approval.draft.body_text))
    return _confirm_page("Veto this reply?", question, "/veto/%s" % token, "Veto it", preview)


@app.post("/veto/{token}")
def veto_endpoint(token: str):
    result = approval_mod.veto(token, store=DEPS.store, now=DEPS.now(), ghl=DEPS.ghl, instantly=DEPS.instantly)
    if not result.get("ok"):
        return _page("Not vetoed", "<p>%s</p>" % _esc(_why(result)), status=400)
    extra = ""
    if result.get("booking_cancelled"):
        extra = "<p>The call that reply had already booked (%s) was cancelled and the lead is back on New Reply.</p>" % _esc(
            (result["booking_cancelled"] or {}).get("slot"))
    elif result.get("booking_cancel_failed"):
        failed = result["booking_cancel_failed"] or {}
        extra = ("<p><b>The call that reply had booked (%s) could NOT be cancelled:</b> GHL refused (%s). It is still "
                 "on the calendar. Its reminders stay held so the lead hears nothing, and the engine retries the "
                 "cancel every few minutes; you get an alert if it keeps failing.</p>" % (
                     _esc(failed.get("slot")), _esc(failed.get("appointment_error"))))
    return _page("Vetoed", "<p>The draft will not be sent. Reply by hand from the Instantly inbox if you want to.</p>%s" % extra)


def _retry_mark_sent_note(approval, token: str) -> str:
    """The retry page's line for a card whose reply may have gone out
    (send_failed, or sending past its lease): a Retry would send it to the
    lead again, so when the Instantly thread shows it, Mark sent is the
    button. Where Mark sent is refused for the card (_mark_sent_refusal),
    the page says so and why."""
    try:
        refusal = _mark_sent_refusal(approval)
    except Exception as exc:  # noqa: BLE001 - the page still warns
        refusal = "could not check whether Mark sent is available (%s)" % exc
    if refusal is None:
        return ("<p><b>If the reply went out, press <a href='/mark-sent/%s'>Mark sent</a> instead.</b> Check the "
                "Instantly thread first: a Retry would send it to the lead a second time.</p>" % _esc(token))
    return ("<p><b>If the reply went out, do not retry:</b> a Retry would send it to the lead a second time. Mark "
            "sent is not available for this card: %s</p>" % _esc(refusal))


@app.get("/retry/{token}")
def retry_confirm(token: str):
    """A card stuck at send_failed / stale_slots / sending has no owner: nothing
    retries it and it is not in SENDABLE_STATUSES. This is the operator path
    back to pending.

    A sending card whose send may still be running (inside its lease) gets
    retry()'s own refusal before the POST (approval.retry_refusal): when its
    send started and when Retry becomes available, and no form. A card whose
    reply may have gone out (send_failed, sending past the lease) is told to
    press Mark sent instead if the Instantly thread shows it
    (_retry_mark_sent_note)."""
    approval = approval_mod.load(token, DEPS.store)
    if approval is None:
        return _page("Unknown token", "<p>Nothing to retry.</p>", status=400)
    if approval.status not in approval_mod.RETRYABLE_STATUSES:
        return _page("Nothing to retry", "<p>This approval is %s.</p>" % _esc(approval.status), status=400)
    try:
        refusal = approval_mod.retry_refusal(approval, DEPS.store, DEPS.now())
    except Exception as exc:  # noqa: BLE001 - retry() refuses an unreadable claim too
        return _page("Retry not available",
                     "<p>%s</p>" % _esc("could not read this card's send claim (%s); nothing changed, try again"
                                        % exc), status=400)
    if refusal:
        return _page("Retry not available yet", "<p>%s</p>" % _esc(refusal), status=400)
    preview = "<p><b>To:</b> %s</p><pre style='white-space:pre-wrap'>%s</pre>" % (
        _esc(approval.reply_to or approval.lead_email), _esc(approval.draft.body_text))
    if approval.status in MARK_SENT_STATUSES:
        preview = _retry_mark_sent_note(approval, token) + preview
    return _confirm_page("Put this reply back in the queue?",
                         "It is stuck at %s and nothing will retry it on its own. This only moves it back to "
                         "pending; you still have to approve it." % approval.status,
                         "/retry/%s" % token, "Move it back to pending", preview)


@app.post("/retry/{token}")
def retry_endpoint(token: str):
    result = approval_mod.retry(token, store=DEPS.store, now=DEPS.now())
    if not result.get("ok"):
        return _page("Not retried", "<p>%s</p>" % _esc(_why(result)), status=400)
    return _page("Back to pending",
                 "<p>It was %s and is pending again. <a href='/approve/%s'>Review and send</a>, or "
                 "<a href='/edit/%s'>Edit</a> it first.</p>" % (
                     _esc(result.get("from_status")), _esc(result.get("token")), _esc(result.get("token"))))


# The statuses "Mark sent" acts on (approval.MARK_SENT_FROM): send_failed,
# and sending once its send claim is approval.SEND_CLAIM_LEASE_MINUTES old.
# approval.mark_sent_manually moves the card to sent_manually and checks the
# claim again itself.
MARK_SENT_STATUSES = approval_mod.MARK_SENT_FROM


def _mark_sent_refusal(approval) -> Optional[str]:
    """Why Mark sent is not offered for this card, or None. A card its
    recipient check held (approval.recipient_held) never reached Instantly
    and its thread may not be the lead's; a hold that cannot be read is
    refused too (fail closed). A sending card only once nothing can still be
    running its send (approval.sending_takeover: its send claim is its own
    attempt and SEND_CLAIM_LEASE_MINUTES old); a claim inside the lease,
    missing or unreadable is refused. mark_sent_manually refuses all of
    these on its own, the hold under the card's lock: this is the
    confirmation page's copy of it."""
    try:
        held = approval_mod.recipient_held(approval, DEPS.store)
    except Exception as exc:  # noqa: BLE001
        return ("could not check whether this card's recipient was confirmed (%s); nothing was recorded, try again"
                % exc)
    if held:
        return approval_mod.RECIPIENT_HELD_REFUSAL
    if approval.status == "sending":
        try:
            _claim, problem = approval_mod.sending_takeover(approval, DEPS.store, DEPS.now())
        except Exception as exc:  # noqa: BLE001
            return "could not read this card's send claim (%s); nothing was recorded, try again" % exc
        return problem
    return None


def _left_held_note(result: Dict[str, Any]) -> str:
    """Say so when the call this card holds was left as it was."""
    left = result.get("booking_left_held") if isinstance(result.get("booking_left_held"), dict) else {}
    if not left:
        return ""
    return ("<p><b>The call booked for %s was NOT confirmed</b>: %s. It stays on the calendar as it was; an alert "
            "says what to do with it in GHL.</p>" % (_esc(_when(left.get("slot"))), _esc(left.get("why") or "unknown")))


@app.get("/mark-sent/{token}")
def mark_sent_confirm(token: str):
    """Confirmation page only, for a card stuck at send_failed, or at
    sending once its send claim is past its lease, whose reply Lorenzo
    checked did go out (the Instantly thread shows it): the "Mark sent"
    action on the "Replies with no owner" push. The record is the POST below,
    so a link scanner cannot mark a reply sent. A card its recipient check
    held, and a sending card whose send may still be running, get no form
    (_mark_sent_refusal)."""
    approval = approval_mod.load(token, DEPS.store)
    if approval is None:
        return _page("Unknown token", "<p>Nothing to mark.</p>", status=400)
    if approval.status not in MARK_SENT_STATUSES:
        return _page("Nothing to mark", "<p>This approval is %s.</p>" % _esc(approval.status), status=400)
    refusal = _mark_sent_refusal(approval)
    if refusal:
        return _page("Mark sent not available", "<p>%s</p>" % _esc(refusal), status=400)
    try:
        said = approval_mod.history_sentence(approval_mod.card_history(DEPS.store, approval))
    except Exception as exc:  # noqa: BLE001 - the page still asks the question
        logger.warning("could not read the send history of %s: %s", approval.token.split(".", 1)[0], exc)
        said = ""
    preview = "<p>%s</p><p><b>To:</b> %s</p><p><b>Subject:</b> %s</p><pre style='white-space:pre-wrap'>%s</pre>" % (
        _esc(said), _esc(approval.reply_to or approval.lead_email), _esc(approval.draft.subject),
        _esc(approval.draft.body_text))
    return _confirm_page("Mark this reply as sent?",
                         "Only confirm once the Instantly thread shows this reply went out. Nothing is sent from "
                         "this page. The card is recorded as sent by hand, the reminders about it stop, and the "
                         "engine does what it does after any sent reply. A call booked for this lead is kept, "
                         "not cancelled.",
                         "/mark-sent/%s" % token, "It went out: mark it sent", preview)


@app.post("/mark-sent/{token}")
def mark_sent_endpoint(token: str):
    # The token is verified here: mark_sent_manually takes the card's id. Its
    # own refusals (a card its recipient check held, a lost race) are shown as
    # they are, and change nothing.
    approval = approval_mod.load(token, DEPS.store)
    if approval is None:
        return _page("Not recorded", "<p>unknown or invalid token</p>", status=400)
    if approval.status not in MARK_SENT_STATUSES:
        return _page("Not recorded", "<p>Nothing to mark: this approval is %s.</p>" % _esc(approval.status),
                     status=400)
    approval_id = approval.token.split(".", 1)[0]
    try:
        # ghl: the invite of a call this card owns is released through it, as /approve does.
        result = approval_mod.mark_sent_manually(approval_id, DEPS.now(), by="lorenzo", store=DEPS.store,
                                                 ghl=DEPS.ghl)
    except Exception as exc:  # noqa: BLE001
        logger.exception("mark sent failed for %s", approval_id)
        return _page("Not recorded", "<p>%s</p>" % _esc(exc), status=500)
    result = result if isinstance(result, dict) else {"ok": False, "error": "no result"}
    if not result.get("ok"):
        return _page("Not recorded", "<p>%s</p>" % _esc(_why(result)), status=400)
    note = ""
    if result.get("shadow") or not settings.is_live():
        note = "<p>Shadow mode: what the engine does after a sent reply is recorded as would_do.</p>"
    return _page("Marked as sent",
                 "<p>The reply to %s is recorded as sent by hand. The reminders about this card stop. Nothing was "
                 "sent from this page.</p>%s%s%s" % (_esc(approval.reply_to or approval.lead_email), note,
                                                     _invite_note(result), _left_held_note(result)))


def _expired_choice_text(choice: str, history: Dict[str, Any]):
    """Title, question and button for the Keep / Release confirmation page.
    What it says about the past comes from approval.card_history and nothing
    else: "the lead was never told" only when no send from the card is on
    record (re-review R1 item 2)."""
    said = approval_mod.history_sentence(history)
    if choice == "keep":
        if history.get("send_claim"):
            question = ("Nothing is written to GHL. A send from this card was started and never cleared, so the "
                        "card comes back as 'send failed' for another %d hours, still holding the call. Check the "
                        "Instantly thread, then use Retry on it; nothing is sent until you approve it after that. %s"
                        % (approval_mod.TTL_HOURS, said))
        else:
            question = ("Nothing is written to GHL. The card comes back as pending for another %d hours, still "
                        "holding the call; nothing is sent to the lead until you approve it. %s"
                        % (approval_mod.TTL_HOURS, said))
        return "Keep the call?", question, "Keep the call"
    told = (" No reply from this card is on record, so the lead has not been told about the call."
            if history.get("send_started") is False else " " + said)
    return ("Release the call?",
            "The call is cancelled in GHL without notifying the lead. The card stays expired.%s" % told,
            "Release the call")


_EXPIRED_CHOICES = ("keep", "release")


@app.get("/expired/{token}/{choice}")
def expired_booking_confirm(token: str, choice: str):
    """Confirmation page only, for the Keep / Release push a card sends when it
    expires holding a call. The decision is the POST below."""
    if choice not in _EXPIRED_CHOICES:
        return _page("Unknown choice", "<p>Choose keep or release.</p>", status=400)
    approval = approval_mod.load(token, DEPS.store)
    if approval is None:
        return _page("Unknown token", "<p>Nothing to decide.</p>", status=400)
    if approval.status != "expired":
        return _page("Nothing to decide", "<p>This card is %s.</p>" % _esc(approval.status), status=400)
    history = approval_mod.card_history(DEPS.store, approval,
                                        status=approval_mod.expiry_push_record(approval).get("from_status"))
    title, question, button = _expired_choice_text(choice, history)
    preview = "<p><b>Lead:</b> %s</p><pre style='white-space:pre-wrap'>%s</pre>" % (
        _esc(approval.reply_to or approval.lead_email), _esc(approval.draft.body_text))
    return _confirm_page(title, question, "/expired/%s/%s" % (token, choice), button, preview)


@app.post("/expired/{token}/{choice}")
def expired_booking_decide(token: str, choice: str):
    result = approval_mod.decide_expired_booking(token, choice, ghl=DEPS.ghl, instantly=DEPS.instantly,
                                                 store=DEPS.store, now=DEPS.now())
    if not result.get("ok"):
        return _page("Nothing changed", "<p>%s</p>" % _esc(_why(result)), status=400)
    said = approval_mod.history_sentence(result.get("history") or {})
    if result.get("choice") == "keep":
        note = ""
        if result.get("problems"):
            note = "<p>It still needs fixing before it can go out: %s</p>" % _esc("; ".join(result["problems"]))
        if result.get("status") == "send_failed":
            return _page("Call kept, check the thread first",
                         "<p>The call (%s) stays on the calendar. A send from this card was started earlier and "
                         "never cleared, so the card is back as 'send failed' until %s, not pending. %s Then "
                         "<a href='/retry/%s'>Retry</a> it to move it back to pending; nothing is sent until you "
                         "approve it after that.</p>%s" % (
                             _esc(result.get("slot")), _esc(result.get("expires_at")), _esc(said),
                             _esc(result.get("token")), note))
        return _page("Call kept",
                     "<p>The call (%s) stays on the calendar and the card is pending again until %s. %s Nothing is "
                     "sent until you approve it. <a href='/approve/%s'>Review and send</a>, or "
                     "<a href='/edit/%s'>Edit</a> it first.</p>%s" % (
                         _esc(result.get("slot")), _esc(result.get("expires_at")), _esc(said),
                         _esc(result.get("token")), _esc(result.get("token")), note))
    if result.get("booking_cancel_failed"):
        failed = result["booking_cancel_failed"] or {}
        return _page("Call NOT released",
                     "<p>GHL refused to cancel the call (%s). It is still on the calendar with its reminders held; "
                     "the engine retries the cancel every few minutes and alerts you if it keeps failing.</p>"
                     % _esc(failed.get("appointment_error")), status=400)
    return _page("Call released",
                 "<p>The call (%s) was cancelled in GHL without notifying the lead. %s</p>"
                 % (_esc(result.get("slot")), _esc(said)))


@app.get("/accept/{token}")
def accept_confirm(token: str):
    """Confirmation page only. The booking and the send are the POST below."""
    approval = approval_mod.load(token, DEPS.store)
    if approval is None:
        return _page("Unknown token", "<p>Nothing to book.</p>", status=400)
    if not approval.requested_slot:
        return _page("Not booked", "<p>no requested time on this approval</p>", status=400)
    if approval.status not in approval_mod.SENDABLE_STATUSES:
        return _page("Nothing to send", "<p>This approval is already %s.</p>" % _esc(approval.status), status=400)
    return _confirm_page("Book the time they asked for?",
                         "This books %s and sends the confirmation to %s." % (
                             approval_mod._slot_label(approval.requested_slot), approval.reply_to or approval.lead_email),
                         "/accept/%s" % token, "Book it and send")


@app.post("/accept/{token}")
def accept_requested_endpoint(token: str):
    """Lorenzo waives his own slot rule and takes the time the lead asked for.

    Reached from the "Book <time> as asked" action on the approval card; the
    counter-proposal is replaced by the booking confirmation and sent.
    """
    result = approval_mod.accept_requested(token, DEPS.ghl, DEPS.instantly, store=DEPS.store, now=DEPS.now())
    if not result.get("ok"):
        if result.get("held"):
            return _held_page(result)
        if result.get("booked"):
            return _page("Booked, not sent", "<p>The call is on the calendar (%s) but the confirmation was not sent: "
                                             "%s</p>" % (_esc(result.get("booked")), _esc(_why(result))), status=400)
        return _page("Not booked", "<p>%s</p>" % _esc(_why(result)), status=400)
    if result.get("status") == "approved_queued":
        return _page("Booked, reply queued",
                     "<p>The call is on the calendar (%s). Outside 07:00-19:00 CT on a business day, so the "
                     "confirmation and the invite go out after %s.</p>" % (_esc(result.get("booked")),
                                                                            _esc(result.get("send_after"))))
    note = "shadow mode: the booking and the confirmation are recorded as would_do" if result.get("shadow") else "booked and confirmed"
    extra = "<p>Zoom is not connected to the calendar, so the invite carries the Google Meet link.</p>" if result.get("zoom_not_connected") else ""
    if result.get("pipeline_errors"):
        extra += "<p><b>Booked, pipeline update failed:</b> %s. Fix it by hand in GHL / Instantly.</p>" % _esc(
            "; ".join(result["pipeline_errors"]))
    return _page("Booked as asked", "<p>%s (%s).</p>%s%s" % (_esc(note), _esc(result.get("booked")), extra,
                                                            _invite_note(result)))


def _cadence_state(campaign_id: str, email: str):
    """The LeadState behind a /cadence/... action, or None."""
    key = "lead:%s:%s" % (campaign_id, (email or "").strip().lower())
    raw = DEPS.store.get(key)
    if not raw:
        return None, key
    try:
        return LeadState.from_store(raw), key
    except Exception as exc:  # noqa: BLE001
        logger.warning("bad lead state at %s: %s", key, exc)
        return None, key


def _cadence_not_recorded() -> HTMLResponse:
    """The one refusal page for a cadence decision link: no lead data and no
    store key, the same body and status for a missing, forged or expired
    token, a lead with no state and no signing secret, so it does not even
    say whether the lead exists."""
    return _page("Not recorded", "<p>That link is not signed for this lead, or it has expired. "
                                 "Open the newest card and try again.</p>", status=403)


def _cadence_link_state(kind: str, campaign_id: str, email: str, token: Optional[str], now: datetime):
    """(cadence module, state, key) for a cadence decision link whose token
    verifies True for ``kind``, else (cadence, None, key). None for the module
    means it is not deployed.

    Must verify True: with no REPLY_ENGINE_SECRET nothing can be verified
    (verify_decision_token answers None), and live refuses to run without the
    secret anyway (approval.py), so an unverifiable decision is refused
    rather than honoured."""
    cadence = _optional("cadence")
    if cadence is None:
        return None, None, None
    state, key = _cadence_state(unquote(campaign_id), unquote(email))
    if state is None or cadence.verify_decision_token(kind, state, token, now) is not True:
        return cadence, None, key
    return cadence, state, key


def _cadence_decision_confirm(kind: str, campaign_id: str, email: str, token: Optional[str],
                              title: str, question: str, button: str) -> HTMLResponse:
    """GET on a cadence decision link: a confirmation page only, never a
    decision. The link goes out on the ntfy card and its email leg, and link
    scanners and chat previewers fetch URLs with GET, so the decision is the
    POST the page's one button sends (with the same token). Signed before
    anything is shown, with the check the POST and the tick use. The page
    names no lead: the URL already carries the address and the page adds
    nothing Lorenzo needs to decide."""
    cadence, state, _key = _cadence_link_state(kind, campaign_id, email, token, DEPS.now())
    if cadence is None:
        return _page("Cadence unavailable", "<p>The cadence module is not deployed.</p>", status=503)
    if state is None:
        return _cadence_not_recorded()
    # Relative to this page's own URL: the form posts to the same path with
    # the same token, and the page source carries no copy of the address.
    action = "?%s" % urlencode({"t": token or ""})
    return _confirm_page(title, question, action, button)


def _cadence_decision(kind: str, campaign_id: str, email: str, apply_fn, title: str, body: str,
                      token: Optional[str] = None):
    """Record a Veto / Approve decision from the cadence card (the POST).

    These URLs are broadcast on the ntfy topic, which is a public name on
    ntfy.sh, so the decision carries a signed token: ``cadence._decision_url``
    mints an HMAC over (kind, campaign_id, lead_email, armed_at, expiry) and
    puts it on the card as ``?t=``. The token is verified BEFORE anything is
    written: a missing, forged or expired token (or no signing secret) gets
    the neutral 403 and writes nothing. It used to write an unsigned record
    (token_ok=False) at the same key, which the tick ignores, so a forged POST
    after Lorenzo's real Veto overwrote the veto and the D1 touch went out.
    """
    now = DEPS.now()
    cadence, state, key = _cadence_link_state(kind, campaign_id, email, token, now)
    if cadence is None:
        return _page("Cadence unavailable", "<p>The cadence module is not deployed.</p>", status=503)
    if state is None:
        return _cadence_not_recorded()
    base = state.to_store()
    try:
        apply_fn(cadence, DEPS.store, state, now, token)
    except Exception as exc:  # noqa: BLE001
        logger.exception("cadence decision failed for %s", key)
        return _page("Not recorded", "<p>%s</p>" % _esc(exc), status=500)
    approval_mod.save_lead_state(DEPS.store, state, base)
    return _page(title, "<p>%s</p>" % body)


_VETO_QUESTION = ("Veto holds the D1 follow-up for this lead: it will not go out and the follow-up ladder stops. "
                  "Nothing is recorded until you press Veto.")
_APPROVE_INVITE_QUESTION = ("Send hold books the D6 calendar hold on the Discovery Call calendar on the next tick, "
                            "and the D6 follow-up goes out with the hold wording. Nothing is recorded until you "
                            "press Send hold.")
_VETO_INVITE_QUESTION = ("Email only sends the D6 follow-up with the no-hold wording and books no calendar hold. "
                         "Nothing is recorded until you press Email only.")


@app.get("/cadence/veto/{campaign_id}/{email}")
def cadence_veto_confirm(campaign_id: str, email: str, t: Optional[str] = Query(default=None)):
    """Confirmation page for the D1 card's Veto (its 30-minute window): one
    tap opens it, one tap confirms. The veto is the POST below."""
    return _cadence_decision_confirm("veto", campaign_id, email, t, "Veto the D1 follow-up?", _VETO_QUESTION, "Veto")


@app.post("/cadence/veto/{campaign_id}/{email}")
def cadence_veto(campaign_id: str, email: str, t: Optional[str] = Query(default=None)):
    """Veto the next auto-sent cadence touch (the D1 card's 30-minute window)."""
    return _cadence_decision("veto", campaign_id, email,
                             lambda c, st, state, now, tok: c.record_veto(st, state, now, token=tok),
                             "Touch vetoed", "The next cadence touch will not go out.", token=t)


@app.get("/cadence/approve/{campaign_id}/{email}")
def cadence_approve_invite_confirm(campaign_id: str, email: str, t: Optional[str] = Query(default=None)):
    """Confirmation page for the D6 card's "Send hold". The approval is the
    POST below: a scanner must not put a hold and an invite in front of a lead."""
    return _cadence_decision_confirm("approve", campaign_id, email, t, "Send the D6 calendar hold?",
                                     _APPROVE_INVITE_QUESTION, "Send hold")


@app.post("/cadence/approve/{campaign_id}/{email}")
def cadence_approve_invite(campaign_id: str, email: str, t: Optional[str] = Query(default=None)):
    """Approve the D6 calendar invite."""
    return _cadence_decision("approve", campaign_id, email,
                             lambda c, st, state, now, tok: c.record_invite_decision(st, state, "approve", now, token=tok),
                             "Invite approved",
                             "The hold goes on the calendar on the next tick and the email goes out either way.",
                             token=t)


@app.get("/cadence/veto-invite/{campaign_id}/{email}")
def cadence_veto_invite_confirm(campaign_id: str, email: str, t: Optional[str] = Query(default=None)):
    """Confirmation page for the D6 card's "Email only". The veto is the POST below."""
    return _cadence_decision_confirm("veto-invite", campaign_id, email, t, "Send D6 without a hold?",
                                     _VETO_INVITE_QUESTION, "Email only")


@app.post("/cadence/veto-invite/{campaign_id}/{email}")
def cadence_veto_invite(campaign_id: str, email: str, t: Optional[str] = Query(default=None)):
    """Veto the D6 calendar invite (the rest of the touch still goes)."""
    return _cadence_decision("veto-invite", campaign_id, email,
                             lambda c, st, state, now, tok: c.record_invite_decision(st, state, "veto", now, token=tok),
                             "Invite vetoed", "No calendar hold will be created; the email still goes out.", token=t)


def _template_resume_text(cadence: Any, state: Any) -> str:
    """The resume page's wording for a ladder CT3 stopped as
    template_unapproved: the held day, its ids and the gate's reason, what
    fixes it, and whether the ids pass the gate's pre-check right now. No
    lead details: the page does not need them."""
    hold = (state.cadence or {}).get("template_hold") or {}
    template_id = hold.get("template_id")
    ids = [i for i in (hold.get("ids") or []) if i]
    reason = hold.get("reason")
    now_ok = None
    if template_id and cadence.hold_cause(reason) == "approve":
        now_ok = bool(getattr(cadence._template_ids_verdict(template_id, [i for i in ids if i != template_id]),
                              "allowed", False))
    status = {True: "The held ids pass the template gate now.",
              False: "The held ids do NOT pass the template gate yet: approve them first, or it holds again.",
              None: cadence.hold_advice(reason)}[now_ok]
    return ("Nothing is sent from this page. D%s was held (%s; ids: %s) and the ladder was stopped. %s "
            "The next tick runs the template gate again and sends the day only if it is auto-sendable by then "
            "and every send check passes; otherwise it is held again. A D1 first opens a fresh 30-minute Veto "
            "window." % (hold.get("day") or "?", reason or "unknown", ", ".join(ids) or "-", status))


@app.get("/cadence/resume/{campaign_id}/{email}")
def cadence_resume_confirm(campaign_id: str, email: str, t: Optional[str] = Query(default=None)):
    """Confirmation page for resuming a stopped ladder: R6's recipient hold
    (the thread re-read kept failing) or CT3's template hold (the day's
    template was held TEMPLATE_HOLD_STALL_DAYS business days). The resume is
    the POST below: a link scanner must not restart a follow-up sequence.

    Signed before anything about the lead is shown, with the token the POST
    verifies: the recipient-hold page names the thread's address and the URL
    shape is guessable. A missing, forged or expired token, and a lead with
    no state (nothing to verify it against), get the same page and status,
    so the page does not even say whether the lead exists."""
    cadence = _optional("cadence")
    if cadence is None:
        return _page("Cadence unavailable", "<p>The cadence module is not deployed.</p>", status=503)
    state, _key = _cadence_state(unquote(campaign_id), unquote(email))
    if state is None or cadence.verify_decision_token("resume", state, t, DEPS.now()) is not True:
        return _page("Not resumed", "<p>That link is not signed for this lead, or it has expired.</p>", status=403)
    stopped = (state.cadence or {}).get("stopped_reason")
    if stopped not in cadence.RESUMABLE_STOPS:
        return _page("Nothing to resume", "<p>This cadence is not stopped on a hold that can be resumed.</p>",
                     status=400)
    action = "/cadence/resume/%s/%s" % (quote(unquote(campaign_id)), quote(unquote(email)))
    if t:
        action = "%s?%s" % (action, urlencode({"t": t}))
    if stopped == "template_unapproved":
        return _confirm_page("Resume the follow-ups?", _template_resume_text(cadence, state), action, "Resume")
    return _confirm_page("Resume the follow-ups?",
                         "Nothing is sent from this page. The next tick re-reads the thread and sends the held "
                         "follow-up only if it is confirmed as %s's; otherwise it holds again." % (
                             cadence.recipient_for(state) or state.lead_email),
                         action, "Resume")


@app.post("/cadence/resume/{campaign_id}/{email}")
def cadence_resume(campaign_id: str, email: str, t: Optional[str] = Query(default=None)):
    cadence = _optional("cadence")
    if cadence is None:
        return _page("Cadence unavailable", "<p>The cadence module is not deployed.</p>", status=503)
    state, _key = _cadence_state(unquote(campaign_id), unquote(email))
    now = DEPS.now()
    # Must verify True: an unsigned resume (no secret configured, or no token)
    # never restarts a stopped ladder. A lead with no state gets the same
    # neutral 403 as a bad token, like the GET: nothing says whether it exists.
    if state is None or cadence.verify_decision_token("resume", state, t, now) is not True:
        return _page("Not resumed", "<p>That link is not signed for this lead, or it has expired.</p>", status=403)
    base = state.to_store()
    stopped = (state.cadence or {}).get("stopped_reason")
    result = cadence.resume_after_recipient_hold(state, now)
    if not result.get("resumed"):
        return _page("Nothing to resume", "<p>This cadence is %s.</p>" % _esc(result.get("reason")), status=400)
    approval_mod.save_lead_state(DEPS.store, state, base)
    if stopped == "template_unapproved":
        return _page("Resumed", "<p>The held follow-up is due now. The next tick runs the template gate first: "
                                "it sends only if the day is auto-sendable (its ids approved, the kill switch "
                                "off, the text conforming) and every send check passes, and holds it again "
                                "otherwise. A D1 first opens a fresh 30-minute Veto window.</p>")
    return _page("Resumed", "<p>The held follow-up is due now. The next tick re-reads the thread first and holds "
                            "again if the recipient still cannot be confirmed.</p>")


@app.get("/booking/cancelled/{campaign_id}/{email}")
def booking_cancelled_confirm(campaign_id: str, email: str, a: Optional[str] = Query(default=None),
                              t: Optional[str] = Query(default=None)):
    """Confirmation page for "I cancelled it": Lorenzo cancelled a call in GHL
    by hand after the engine's cancel kept failing. The cleanup is the POST
    below, so a link scanner cannot fire it."""
    key = "lead:%s:%s" % (unquote(campaign_id), (unquote(email) or "").strip().lower())
    # Signed before anything about the lead is shown: the page names the call
    # time, and the URL shape is guessable.
    if not approval_mod.verify_cancel_done_token(key, a, t, DEPS.now()):
        return _page("Not recorded", "<p>That link is not signed for this call, or it has expired.</p>", status=403)
    state, key = _cadence_state(unquote(campaign_id), unquote(email))
    if state is None:
        return _page("Unknown lead", "<p>No state at %s.</p>" % _esc(key), status=404)
    booking = approval_mod.booking_of(state)
    if str(booking.get("appointment_id")) != str(a) or not booking.get("cancel_failed"):
        return _page("Nothing to do", "<p>That call is not waiting on a cancel any more.</p>", status=400)
    action = "/booking/cancelled/%s/%s?%s" % (quote(unquote(campaign_id), safe=""), quote(unquote(email), safe=""),
                                              urlencode({"a": a or "", "t": t or ""}))
    return _confirm_page("Did you cancel the call in GHL?",
                         "Only confirm once the appointment for %s (%s) is cancelled in GHL. The engine then removes "
                         "the booking and the slot reservation and stops retrying. It does not call GHL, and it keeps "
                         "the reminders held until the call's time has passed, in case the event is still live."
                         % (state.lead_email, booking.get("slot")),
                         action, "I cancelled it")


@app.post("/booking/cancelled/{campaign_id}/{email}")
def booking_cancelled(campaign_id: str, email: str, a: Optional[str] = Query(default=None),
                      t: Optional[str] = Query(default=None)):
    key = "lead:%s:%s" % (unquote(campaign_id), (unquote(email) or "").strip().lower())
    result = approval_mod.mark_cancelled_by_hand(DEPS.store, key, a, t, DEPS.now(), instantly=DEPS.instantly)
    if not result.get("ok"):
        status = 400 if result.get("status") == "nothing_to_do" else 403
        return _page("Not recorded", "<p>%s</p>" % _esc(result.get("error")), status=status)
    return _page("Cleanup done", "<p>The call for %s is recorded as cancelled. The booking and the slot "
                                 "reservation are gone and the engine stopped retrying. Its reminders stay held (nothing "
                                 "is sent) until the call's time has passed.</p>" % _esc(result.get("slot")))


@app.get("/edit/{token}")
def edit_form(token: str):
    """The edit form, with the card's problems above it when it has any
    (what the edit is for: an Edit clears the ones about the copy, and an
    older reply's proposed time, approval.edit)."""
    approval = approval_mod.load(token, DEPS.store)
    if approval is None:
        return _page("Unknown token", "<p>Nothing to edit.</p>", status=404)
    note = ""
    if approval.draft.problems:
        note = "<p><b>Why it cannot go out as it is:</b> %s</p>" % _esc(_stated_problems(approval))
    return _page("Edit draft", _edit_form_html(approval, note))


def _owned_slot(approval) -> Optional[str]:
    """The booked slot this card holds, or None."""
    if not approval_mod.card_owns_booking(approval, DEPS.store):
        return None
    raw = DEPS.store.get(approval.state_key)
    state = LeadState.from_store(raw) if raw else None
    return approval_mod.booking_of(state).get("slot")


def _edit_form_html(approval, note: str = "") -> str:
    """The edit form. A card that holds the lead's unconfirmed booking also
    asks Lorenzo, explicitly and every time, what to do with that call: the
    engine no longer guesses it from the words he wrote."""
    choice = ""
    owned = _owned_slot(approval)
    if owned:
        label = approval_mod._slot_label(owned)
        choice = ("<fieldset><legend><b>This card holds a booked call. Choose one:</b></legend>"
                  "<p><label><input type='radio' name='booking_choice' value='keep' required> "
                  "Keep the call: send the invite for %s</label></p>"
                  "<p><label><input type='radio' name='booking_choice' value='release' required> "
                  "Release the call: cancel it silently, no invite</label></p></fieldset>" % _esc(label))
    return ("%s<form method='post'><p>Subject: %s</p><textarea name='body' rows='14' style='width:100%%'>%s</textarea>"
            "%s<p><button type='submit'>Save and approve</button></p></form>") % (
        note, _esc(approval.draft.subject), _esc(approval.draft.body_text), choice)


async def _submitted_fields(request: Request) -> Dict[str, str]:
    """Read the edit form out of the request without Starlette's form parser.

    ``request.form()`` asserts python-multipart is installed even for a plain
    urlencoded post, and this service must run on the pinned dependency set
    (services/reply_engine/requirements.txt) with nothing extra. JSON bodies
    ({"body": "...", "booking_choice": "keep"}) are accepted too so the
    endpoint is scriptable.
    """
    raw = await request.body()
    text = raw.decode("utf-8", "replace")
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type == "application/json":
        try:
            payload = json.loads(text or "{}")
        except ValueError:
            return {"body": ""}
        if not isinstance(payload, dict):
            return {"body": ""}
        return {"body": str(payload.get("body", "")), "booking_choice": str(payload.get("booking_choice") or "")}
    fields = parse_qs(text, keep_blank_values=True)
    if "body" in fields:
        return {"body": fields["body"][0], "booking_choice": (fields.get("booking_choice") or [""])[0]}
    return {"body": text}


async def _submitted_body(request: Request) -> str:
    return (await _submitted_fields(request)).get("body", "")


@app.post("/edit/{token}")
async def edit_submit(token: str, request: Request):
    fields = await _submitted_fields(request)
    new_body = fields.get("body", "")
    result = approval_mod.edit(token, new_body, store=DEPS.store, now=DEPS.now(),
                               booking_choice=fields.get("booking_choice") or None)
    if not result.get("ok"):
        if result.get("needs_booking_choice"):
            # Nothing was saved. Show the form again with his text kept.
            approval = approval_mod.load(token, DEPS.store)
            if approval is not None:
                approval.draft.body_text = new_body
                note = "<p><b>Not saved:</b> %s.</p>" % _esc(result.get("error"))
                return _page("Choose what happens to the booked call", _edit_form_html(approval, note), status=400)
        return _page("Draft rejected", "<p>%s</p>" % _esc("; ".join(result.get("problems", [result.get("error", "")]))), status=400)
    if result.get("problems"):
        return _page("Saved, not sent", "<p>%s</p><p>Open <a href='/edit/%s'>Edit</a> to fix it.</p>" % (
            _esc("; ".join(result["problems"])), _esc(result["token"])), status=400)
    sent = approval_mod.approve(result["token"], DEPS.instantly, store=DEPS.store, now=DEPS.now(), ghl=DEPS.ghl)
    if not sent.get("ok"):
        return _page("Saved, not sent", "<p>%s</p>" % _esc(sent.get("error") or "; ".join(sent.get("problems") or [])),
                     status=400)
    extra = ""
    if result.get("booking_choice") == "keep":
        extra = "<p>You kept the call for %s.</p>%s" % (_esc(approval_mod._slot_label(result.get("booked_slot"))),
                                                         _invite_note(sent))
    elif result.get("booking_choice") == "release":
        released = sent.get("booking_released") or {}
        if approval_mod.booking_cancel_done(released):
            extra = "<p>You released the call for %s: it was cancelled without notifying the lead.</p>" % _esc(
                approval_mod._slot_label(result.get("booked_slot")))
        else:
            extra = ("<p><b>You released the call for %s, but GHL refused the cancel</b> (%s). It stays on the "
                     "calendar with its reminders held and the cancel is being retried.</p>" % (
                         _esc(approval_mod._slot_label(result.get("booked_slot"))),
                         _esc(released.get("appointment_error"))))
    return _page("Saved and approved", "<p>status: %s</p>%s" % (_esc(sent.get("status")), extra))


@app.get("/state/{lead_email}")
def state_endpoint(lead_email: str, x_advero_secret: Optional[str] = Header(default=None), secret: Optional[str] = Query(default=None)):
    if not _debug_ok(x_advero_secret or (secret if _query_secret_allowed() else None)):
        raise HTTPException(status_code=401, detail="debug secret required")
    st = DEPS.store
    email = lead_email.strip().lower()
    out = []  # type: List[Dict[str, Any]]
    for key in st.keys("lead:"):
        if key.endswith(":" + email):
            out.append(st.get(key))
    if not out:
        raise HTTPException(status_code=404, detail="no state for %s" % email)
    return JSONResponse(out)


@app.get("/", response_class=PlainTextResponse)
def root() -> str:
    return "advero reply engine (%s)" % settings.get_mode()


try:  # other agents own these; include their routers when present
    from services.reply_engine import zoom_webhook  # type: ignore

    if hasattr(zoom_webhook, "router"):
        app.include_router(zoom_webhook.router)
except ImportError:
    pass
