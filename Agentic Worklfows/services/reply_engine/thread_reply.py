"""In-thread transport for the show-rate and no-show ladders (section 2, A1).

A lead-facing reminder or no-show email goes out as a reply in the lead's own
Instantly cold-email thread, from the inbox that wrote to them, under
"Re: <thread subject>". A GHL email is the fallback ONLY when the lead is known
and has no thread at all (no lead row for them, or only rows that carry none
of the thread ids). Everything else that stops the thread reply holds the
touch and sends nothing: a lead we cannot identify (no usable email on the
appointment or its row: ``no_lead_email``, never GHL), an ambiguous lead, a lead
row that belongs to somebody else or cannot be read, a row with half its
thread ids, a recipient the thread re-read does not confirm. A GHL email there
would reach the lead from a different mailbox, outside the conversation, which
is exactly what this module exists to stop.

Which row is the lead's: every row used must carry the lead's own address in
its ``lead_email`` (compared case-insensitively with the address the lookup
was made for), whatever key it is stored under. A row stored under the lead's
key that names somebody else holds with ``lead_row_mismatch``; one that is not
a readable row holds with ``lead_row_unreadable``. Neither falls back to GHL.

Recipient safety is the same two belts cadence._send uses:

1. ``to=`` is always passed to ``instantly.reply_to_email`` (shared/instantly.py
   raises without it), and it is ``cadence.recipient_for(lead row)``: the
   address that actually wrote the thread;
2. in live, ``cadence.thread_recipient_ok`` re-reads the email by id and only a
   True verdict lets the reply out. False holds with ``recipient_mismatch``,
   None (read error, no readable sender) with ``recipient_unverified``.
   Neither falls back to GHL.

Retrying (the record's ``retryable`` / ``request_issued`` / ``maybe_sent``):
a result whose reason is in ``RETRYABLE_REASONS`` was decided before any write
request left the process, so the caller may keep the touch pending and try
again. A result whose reason is in ``MAYBE_SENT_REASONS`` came after the write
request went out (an HTTP error, a timeout, a 2xx whose body is JSON null): the email may
have been delivered, and neither client retries a write for that reason (no
idempotency key), so the caller must NEVER retry it automatically; it needs a
human to check the thread or the GHL conversation first. This is the same
split as cadence.PRE_SEND_REFUSALS.

Every write goes through the clients' guarded ``_write``: in shadow the client
returns the shadow record and makes no request. The re-read is skipped in
shadow as well (as in cadence._send), so shadow makes zero HTTP requests. In
shadow with no Instantly client, the would-do reply is recorded through
``settings.guard_write`` (as cadence._send does), still with no request.

Out of scope here: the template gate and the opt-out check (the callers keep
both), and schedule changes.
"""
import logging
from datetime import datetime
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import httpx

from shared import keys as shared_keys
from shared import settings
from shared import slots as slot_rules
from shared.ghl import GHLError
from shared.instantly import InstantlyError
from services.reply_engine import cadence
from services.reply_engine.models import LeadState

logger = logging.getLogger(__name__)

LEAD_PREFIX = "lead:"
APPOINTMENT_PREFIX = "appointment:"

TRANSPORT_THREAD = "instantly_thread"
TRANSPORT_GHL = "ghl_email"

# find_thread routes
ROUTE_CAMPAIGN = "campaign"          # appointment campaign_id + email
ROUTE_APPOINTMENT = "appointment"    # the appointment:<id> row's campaign_id + lead_email
ROUTE_SCAN = "scan"                  # every lead:* row for the email

# reasons
AMBIGUOUS_THREAD = "ambiguous_thread"
NO_LEAD_EMAIL = "no_lead_email"
NO_LEAD_ROW = "no_lead_row"
NO_THREAD_IDS = "no_thread_ids"
LEAD_ROW_UNREADABLE = "lead_row_unreadable"
LEAD_ROW_MISMATCH = "lead_row_mismatch"
OUTSIDE_SEND_WINDOW = "outside_send_window"
MISSING_THREAD_IDS = "missing_thread_ids"
MISSING_RECIPIENT = "missing_recipient"
RECIPIENT_MISMATCH = "recipient_mismatch"
RECIPIENT_UNVERIFIED = "recipient_unverified"
NO_INSTANTLY_CLIENT = "no_instantly_client"
NO_GHL_CLIENT = "no_ghl_client"
NO_CONTACT_ID = "no_contact_id"
GHL_TOKEN_MISSING = "ghl_token_missing"          # GHL raised before any request: no write token
INSTANTLY_KEY_MISSING = "instantly_key_missing"  # Instantly raised before any request: no write key
CONNECT_FAILED = "connect_failed"                # the connection was never made: nothing was sent
SEND_FAILED = "send_failed"                      # the request went out and failed: MAY have been sent
NO_RESPONSE = "no_response"                      # 2xx with no body: MAY have been sent
THREAD_SUBJECT_REFUSED = "thread_subject_refused"  # the "Re:" subject failed the caller's subject_check

# The lead has no thread: the GHL email is the fallback (and the GHL record
# carries this reason).
GHL_FALLBACK_REASONS = (NO_LEAD_ROW, NO_THREAD_IDS)
# Nothing sent, and retrying alone will not help: the data needs a look (an
# unknown, ambiguous, foreign or unreadable lead row, a broken thread, a
# recipient that is somebody else). Still safe to retry: no request left the
# process. The record's ``needs_attention`` is True for these.
NEEDS_ATTENTION_REASONS = (AMBIGUOUS_THREAD, LEAD_ROW_MISMATCH, LEAD_ROW_UNREADABLE, NO_LEAD_EMAIL,
                           MISSING_THREAD_IDS, MISSING_RECIPIENT, RECIPIENT_MISMATCH)
# Decided before any write request left the process: the caller may keep the
# touch pending and retry.
RETRYABLE_REASONS = (OUTSIDE_SEND_WINDOW, RECIPIENT_UNVERIFIED, NO_INSTANTLY_CLIENT,
                     NO_GHL_CLIENT, NO_CONTACT_ID, GHL_TOKEN_MISSING, INSTANTLY_KEY_MISSING,
                     CONNECT_FAILED) + NEEDS_ATTENTION_REASONS
# The write request went out and its outcome is unknown: NEVER retry
# automatically (a retry is a duplicate email in the lead's inbox).
MAYBE_SENT_REASONS = (SEND_FAILED, NO_RESPONSE)

# The thread ids a lead row can carry. A row with none of them has no thread
# (GHL fallback); a row with some but not last_email_id + eaccount is broken
# (held, never GHL).
THREAD_ID_FIELDS = ("eaccount", "thread_id", "last_email_id")

# The exact start of the message shared/instantly.py ``_auth_header`` raises
# before any request is built when there is no write key. Matched as a prefix
# so a server error body that happens to contain the phrase stays send_failed.
INSTANTLY_KEY_MISSING_PREFIX = "%s is not set in this process, so no write can be sent." % shared_keys.main_name(
    "instantly")


def _usable_email(value: Any) -> bool:
    """An address worth looking up: "N/A", "lead", "unknown" and the like
    (no "@") count as no email."""
    return "@" in _norm(value)


def _norm(email: Any) -> str:
    return str(email or "").strip().lower()


def _key_email(key: str) -> str:
    """The email part of ``lead:<campaign_id>:<email>``: everything after the
    campaign segment (campaign ids carry no colon), so an address with a colon
    in it is never cut down to its last segment."""
    rest = key[len(LEAD_PREFIX):] if key.startswith(LEAD_PREFIX) else key
    return _norm(rest.split(":", 1)[1]) if ":" in rest else ""


def _has_any_thread_id(row: Any) -> bool:
    return isinstance(row, dict) and any(row.get(f) for f in THREAD_ID_FIELDS)


def _readable(row: Any) -> bool:
    return isinstance(row, dict) and bool(row)


def _found(key: str, row: Dict[str, Any], route: str, candidates: List[str]) -> Dict[str, Any]:
    return {"state": LeadState.from_store(row), "key": key, "route": route, "reason": None,
            "candidates": candidates}


def _none(reason: str, route: Optional[str] = None, candidates: Optional[List[str]] = None) -> Dict[str, Any]:
    return {"state": None, "key": None, "route": route, "reason": reason, "candidates": list(candidates or [])}


def _judge(rows: List[Tuple[str, Any]], owns, lead_keys: List[str], route: str,
           thread_less_reason: str) -> Dict[str, Any]:
    """Apply the module's rules to the rows a route looked at.

    ``rows`` are (key, value); ``owns(row)`` says whether a readable row
    belongs to the lead (its own lead_email); ``lead_keys``
    are the keys stored under the lead's own address. Any of those that cannot
    be read holds (``lead_row_unreadable``: it may hide the thread); any that
    names somebody else holds (``lead_row_mismatch``). Among the rows that
    belong to the lead: exactly one carrying a thread id is the thread; several
    is ``ambiguous_thread`` (never guess); none returns ``thread_less_reason``
    (or ``no_lead_row`` when there are no rows at all)."""
    lead_key_set = set(lead_keys)
    unreadable = [k for k, r in rows if k in lead_key_set and not _readable(r)]
    if unreadable:
        logger.warning("lead row(s) %s cannot be read; holding", ", ".join(unreadable))
        return _none(LEAD_ROW_UNREADABLE, route, unreadable)
    mismatched = [k for k, r in rows if k in lead_key_set and _readable(r) and not owns(r)]
    if mismatched:
        logger.error("lead row(s) %s name somebody else in lead_email; holding", ", ".join(mismatched))
        return _none(LEAD_ROW_MISMATCH, route, mismatched)
    mine = [(k, r) for k, r in rows if _readable(r) and owns(r)]
    keys = [k for k, _ in mine]
    threaded = [(k, r) for k, r in mine if _has_any_thread_id(r)]
    if len(threaded) == 1:
        return _found(threaded[0][0], threaded[0][1], route, keys)
    if len(threaded) > 1:
        logger.warning("%d lead rows with a thread for one lead (%s); holding rather than guessing", len(threaded),
                       ", ".join(k for k, _ in threaded))
        return _none(AMBIGUOUS_THREAD, route, keys)
    return _none(thread_less_reason if mine else NO_LEAD_ROW, route, keys)


def _identity(store: Any, appointment: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], str]:
    """(email, campaign_id, route) as no_show._lead_identity: the appointment's
    own values first, the ``appointment:<id>`` row for what it lacks. A store
    read that fails raises (the caller holds)."""
    emails = [e for e in (appointment.get("email"), appointment.get("lead_email")) if _usable_email(e)]
    email = str(emails[0]).strip() if emails else None
    campaign_id = appointment.get("campaign_id")
    route = ROUTE_CAMPAIGN
    if not (email and campaign_id):
        appt_id = appointment.get("id") if appointment.get("id") is not None else appointment.get("appointment_id")
        rec = store.get("%s%s" % (APPOINTMENT_PREFIX, appt_id)) if appt_id is not None else None
        rec = rec if isinstance(rec, dict) else {}
        if not email and _usable_email(rec.get("lead_email")):
            email = str(rec.get("lead_email")).strip()
        if not campaign_id and rec.get("campaign_id"):
            campaign_id = rec.get("campaign_id")
        route = ROUTE_APPOINTMENT
    return email, (str(campaign_id) if campaign_id else None), route


def find_thread(store: Any, appointment: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Resolve the lead row that holds this call's Instantly thread.

    Returns ``{"state": LeadState|None, "key", "route", "reason", "candidates"}``.
    Routes, in order:

    1. ``campaign``: ``appointment["campaign_id"]`` + the appointment's email;
    2. ``appointment``: the ``appointment:<id>`` row booking.register_booking
       wrote (its ``campaign_id`` / ``lead_email`` fill what the appointment
       lacks, as no_show._lead_identity);
    3. ``scan``: every ``lead:*`` row whose ``lead_email`` is the lead's
       address (as show_rate.lead_opted_out), for widget bookings that carry no
       campaign, and for a campaign whose row is missing or has no thread (the
       lead may have the thread in another campaign).

    No usable email on the appointment or its row (none, or a value without
    "@" such as "N/A"): ``no_lead_email``, a hold that needs attention. The
    lead is never looked up by GHL contact id (a row's contact id cannot prove
    whose thread it is), and never gets a GHL email.

    A row counts only when its own ``lead_email`` is the lead's address; the
    key it is stored under never decides. Rows stored under the lead's own key
    that cannot be read or that name somebody else hold
    (``lead_row_unreadable`` / ``lead_row_mismatch``). Several of the lead's rows carrying a thread id:
    ``ambiguous_thread`` (never guess); exactly one is the thread; none:
    ``no_thread_ids`` (rows exist) or ``no_lead_row``.

    Only ``no_lead_row`` / ``no_thread_ids`` (``GHL_FALLBACK_REASONS``) mean
    the lead is known and has no thread, so the GHL fallback applies.
    ``no_lead_email`` means we do not know who the lead is: it holds. The
    scan reads only the keys whose text contains the lead's address
    (LeadState.key is built from lead_email) and then decides on each row's
    own lead_email. A store read or
    a row that cannot be parsed raises (the caller holds)."""
    appointment = appointment or {}
    email, campaign_id, route = _identity(store, appointment)
    if not email:
        return _none(NO_LEAD_EMAIL)
    wanted = _norm(email)

    def owns(row: Dict[str, Any]) -> bool:
        return _norm(row.get("lead_email")) == wanted

    if campaign_id:
        prefix = "%s%s:" % (LEAD_PREFIX, campaign_id)
        keys = [k for k in sorted(store.keys(prefix)) if _norm(k[len(prefix):]) == wanted]
        rows = [(k, store.get(k)) for k in keys]
        found = _judge(rows, owns, keys, route, NO_THREAD_IDS)
        if found["reason"] not in (NO_LEAD_ROW, NO_THREAD_IDS):
            return found
        # The campaign has no row for the lead, or one without a thread: the
        # thread may be in another campaign's row, so scan like a widget booking.
    keys = [k for k in sorted(store.keys(LEAD_PREFIX)) if wanted in k.lower()]
    rows = [(k, store.get(k)) for k in keys]
    return _judge(rows, owns, [k for k in keys if _key_email(k) == wanted], ROUTE_SCAN, NO_THREAD_IDS)


def _record(transport: Optional[str], sent: bool = False, skipped: bool = False, reason: Optional[str] = None,
            result: Any = None, shadow: bool = False, route: Optional[str] = None,
            lead_key: Optional[str] = None, request_issued: bool = False) -> Dict[str, Any]:
    maybe_sent = bool(request_issued and not sent)
    return {"transport": transport, "sent": sent, "skipped": skipped, "reason": reason, "result": result,
            "shadow": shadow, "route": route, "lead_key": lead_key,
            "request_issued": bool(request_issued), "maybe_sent": maybe_sent,
            "retryable": bool(not request_issued and not sent and not shadow),
            "needs_attention": bool(skipped and reason in NEEDS_ATTENTION_REASONS)}


def _hold(transport: Optional[str], reason: str, **kw: Any) -> Dict[str, Any]:
    return _record(transport, skipped=True, reason=reason, **kw)


def _chain(exc: Optional[BaseException]) -> Iterator[BaseException]:
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        yield exc
        exc = exc.__cause__ or exc.__context__


def _not_issued(exc: BaseException) -> Optional[str]:
    """The reason when this write exception provably happened before any
    request left the process, else None (the request may have gone out).

    - shared/ghl.py ``_write`` raises GHLError("ghl_token_missing: ...") in
      live with no write token, before ``do()``;
    - shared/instantly.py ``_auth_header`` raises InstantlyError("... is not
      set in this process, so no write can be sent ...") inside ``_request``
      before the request is built; ``reply_to_email`` raises "reply_to_email
      needs to=..." before ``_write``;
    - httpx.ConnectError / ConnectTimeout: the connection was never made
      (Instantly re-raises it as InstantlyError inside the except, so it is the
      exception's __context__; GHL lets it through).
    Anything else (an HTTP status, a read or write timeout, a dropped
    connection, an unknown error) counts as possibly sent."""
    for e in _chain(exc):
        if isinstance(e, (httpx.ConnectError, httpx.ConnectTimeout)):
            return CONNECT_FAILED
    msg = str(exc)
    if isinstance(exc, GHLError) and msg.startswith("ghl_token_missing"):
        return GHL_TOKEN_MISSING
    if isinstance(exc, InstantlyError) and msg.startswith(INSTANTLY_KEY_MISSING_PREFIX):
        return INSTANTLY_KEY_MISSING
    if isinstance(exc, InstantlyError) and msg.startswith("reply_to_email needs to="):
        return MISSING_RECIPIENT
    return None


def _write_failed(transport: str, exc: BaseException, route: Optional[str], lead_key: Optional[str],
                  what: str) -> Dict[str, Any]:
    before = _not_issued(exc)
    if before is not None:
        logger.warning("%s not sent (%s, nothing left the process): %s", what, before, exc)
        return _hold(transport, before, result={"error": str(exc)}, route=route, lead_key=lead_key)
    logger.error("%s: the request went out and failed; it MAY have been delivered, do not retry: %s", what, exc)
    return _record(transport, reason=SEND_FAILED, result={"error": str(exc)}, route=route, lead_key=lead_key,
                   request_issued=True)


def _text_to_html(text: str) -> str:
    """The same HTML show_rate._text_to_html builds for the GHL email (kept
    here so the send path has no late import that could fail mid-send)."""
    esc = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return "<p>%s</p>" % esc.replace("\n\n", "</p><p>").replace("\n", "<br>")


def _send_ghl(ghl: Any, contact_id: Optional[str], subject: str, body: str, route: Optional[str],
              fallback_reason: str) -> Dict[str, Any]:
    """The GHL email the show-rate dispatch sends today, for a lead with no
    thread. ``reason`` on a send (or shadow) record is why the thread was not
    used (``no_lead_row`` / ``no_thread_ids``)."""
    if not contact_id:
        return _hold(TRANSPORT_GHL, NO_CONTACT_ID, route=route)
    if ghl is None:
        return _hold(TRANSPORT_GHL, NO_GHL_CLIENT, route=route)
    html = _text_to_html(body)
    try:
        res = ghl.send_message(contact_id, type="Email", subject=subject, message=body, html=html)
    except Exception as exc:  # noqa: BLE001 - a send failure must never look like a send
        return _write_failed(TRANSPORT_GHL, exc, route, None, "GHL email to %s" % contact_id)
    if not settings.is_live():
        # The client's guard recorded the write instead of making it.
        return _record(TRANSPORT_GHL, reason=fallback_reason, result=res, shadow=True, route=route)
    if res is None:
        # GHL._request returns {} for an empty body and raises on any error, so
        # None means a 2xx whose body was JSON null: the POST was accepted or
        # at least received. May have been sent: never retried.
        logger.error("GHL email to %s answered 2xx with no body; it MAY have been delivered", contact_id)
        return _record(TRANSPORT_GHL, reason=NO_RESPONSE, route=route, request_issued=True)
    return _record(TRANSPORT_GHL, sent=True, reason=fallback_reason, result=res, route=route, request_issued=True)


def send_lead_email(store: Any, appointment: Optional[Dict[str, Any]], subject: str, body: str, now: datetime,
                    *, instantly: Any, ghl: Any, contact_id: Optional[str],
                    subject_check: Optional[Callable[[str], List[str]]] = None) -> Dict[str, Any]:
    """Send one lead-facing email: in the lead's Instantly thread when there is
    one, as a GHL email only when the lead is known and has none.

    Returns ``{"transport": "instantly_thread"|"ghl_email"|None, "sent": bool,
    "skipped": bool, "reason": str|None, "result": Any, "shadow": bool,
    "route": str|None, "lead_key": str|None, "request_issued": bool,
    "maybe_sent": bool, "retryable": bool, "needs_attention": bool}``:

    - ``sent`` True for a live send the client answered 2xx, including an
      empty body (the client returns ``{}`` for it); only a JSON ``null``
      body is ``no_response``;
    - ``shadow`` True (sent False, skipped False) when the client's guard
      recorded the write instead of making it; ``result`` is that record;
    - ``skipped`` True with a ``reason`` in ``RETRYABLE_REASONS`` when the
      touch was held before any write request left the process
      (``retryable`` True; ``needs_attention`` True for the
      ``NEEDS_ATTENTION_REASONS``, the ones a retry alone will not fix);
    - ``reason`` in ``MAYBE_SENT_REASONS`` (skipped False, ``request_issued``
      and ``maybe_sent`` True, ``retryable`` False) when the write request
      went out and failed or came back empty: the email may have been
      delivered. The caller must not retry it automatically; ``result``
      carries the error;
    - on a GHL send or shadow record, ``reason`` is why the thread was not
      used (``no_lead_row`` / ``no_thread_ids``).

    ``subject`` is used for the GHL fallback only. The thread reply's subject
    is ``cadence.subject_for(lead row)``, "Re: <thread subject>", the
    convention every cadence touch uses. ``contact_id`` is the GHL contact for
    the fallback only; it is never used to find the lead.

    ``subject_check`` (optional) is applied to that exact "Re:" subject, from
    this call's own lookup, before anything is recorded or sent: any problem
    it returns, or an error inside it, holds the email
    (``thread_subject_refused``, ``result`` = {"problems": [...]})."""
    if not slot_rules.is_send_time(now):
        return _hold(None, OUTSIDE_SEND_WINDOW)
    try:
        found = find_thread(store, appointment)
    except Exception as exc:  # noqa: BLE001 - an unreadable row may hide a thread: hold, never GHL
        logger.warning("could not resolve the lead's thread, holding: %s", type(exc).__name__)
        return _hold(None, LEAD_ROW_UNREADABLE)
    state = found["state"]
    route = found["route"]
    if state is None:
        if found["reason"] in GHL_FALLBACK_REASONS:
            return _send_ghl(ghl, contact_id, subject, body, route, found["reason"])
        reason = found["reason"] or AMBIGUOUS_THREAD
        result = {"candidates": found["candidates"]} if reason in (AMBIGUOUS_THREAD, LEAD_ROW_MISMATCH) else None
        return _hold(None, reason, route=route, result=result)
    lead_key = found["key"]
    reply_to = getattr(state, "last_email_id", None)
    eaccount = getattr(state, "eaccount", None)
    if not reply_to or not eaccount:
        # Half a thread: replying is impossible and a GHL email would leave it.
        return _hold(TRANSPORT_THREAD, MISSING_THREAD_IDS, route=route, lead_key=lead_key)
    recipient = cadence.recipient_for(state)
    if not recipient:
        return _hold(TRANSPORT_THREAD, MISSING_RECIPIENT, route=route, lead_key=lead_key)
    thread_subject = cadence.subject_for(state)
    if subject_check is not None:
        try:
            problems = list(subject_check(thread_subject) or [])
        except Exception as exc:  # noqa: BLE001 - an unchecked subject never goes out
            problems = ["subject check failed: %s" % type(exc).__name__]
        if problems:
            return _hold(TRANSPORT_THREAD, THREAD_SUBJECT_REFUSED, route=route, lead_key=lead_key,
                         result={"problems": problems})
    if instantly is None:
        if settings.is_live():
            return _hold(TRANSPORT_THREAD, NO_INSTANTLY_CLIENT, route=route, lead_key=lead_key)
        # Shadow with no client (as cadence._send): the would-do reply is the
        # deliverable. guard_write records it and makes no request.
        payload = {"reply_to_uuid": reply_to, "eaccount": eaccount, "to": recipient, "subject": thread_subject,
                   "body": {"text": body}, "lead_email": getattr(state, "lead_email", None)}
        rec = settings.guard_write("instantly", "reply_to_email", payload)
        rec["skipped"] = NO_INSTANTLY_CLIENT
        return _record(TRANSPORT_THREAD, result=rec, shadow=True, route=route, lead_key=lead_key)
    if settings.is_live():
        # Decision R6: only a CONFIRMED match sends. The re-read is a GET, so
        # it runs only in live; shadow stays at zero requests.
        try:
            verdict = cadence.thread_recipient_ok(state, instantly)
        except Exception as exc:  # noqa: BLE001 - a failed re-read holds, it never sends
            logger.warning("recipient re-read failed for %s: %s", lead_key, type(exc).__name__)
            verdict = None
        if verdict is False:
            logger.error("refusing the in-thread email to %s: the thread's last inbound is from somebody else",
                         recipient)
            return _hold(TRANSPORT_THREAD, RECIPIENT_MISMATCH, route=route, lead_key=lead_key)
        if verdict is not True:
            logger.error("holding the in-thread email to %s: the thread could not be re-read to confirm the "
                         "recipient", recipient)
            return _hold(TRANSPORT_THREAD, RECIPIENT_UNVERIFIED, route=route, lead_key=lead_key)
    try:
        result = instantly.reply_to_email(reply_to, eaccount, thread_subject, body, to=recipient)
    except Exception as exc:  # noqa: BLE001 - a send failure must never look like a send
        return _write_failed(TRANSPORT_THREAD, exc, route, lead_key, "in-thread reply to %s" % recipient)
    if not settings.is_live():
        # The client's guard recorded the write instead of making it.
        return _record(TRANSPORT_THREAD, result=result, shadow=True, route=route, lead_key=lead_key)
    if result is None:
        # Instantly._request returns {} for an empty body and raises on any
        # error, so None means a 2xx whose body was JSON null. May have been
        # sent: never retried.
        logger.error("in-thread reply to %s answered 2xx with no body; it MAY have been delivered", recipient)
        return _record(TRANSPORT_THREAD, reason=NO_RESPONSE, route=route, lead_key=lead_key, request_issued=True)
    return _record(TRANSPORT_THREAD, sent=True, result=result, route=route, lead_key=lead_key,
                   request_issued=True)
