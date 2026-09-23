"""Pipeline sweep (Blueprint S8 / O3): one list, ordered by money, of what is
waiting on Lorenzo.

    (a) positive replies with no outbound from Lorenzo after the reply
        (Instantly, read-only: GET /emails email_type=received and
        email_type=manual, compared per thread); ``overdue`` when older than 24 h
    (b) booked calls that start inside the next 24 h that are not confirmed
        (store keys ``appointment:*`` plus show_rate's ``confirmed:<id>``
        record; ids.json google_calendar.booked_this_week is the seed while the
        store is empty)
    (c) proposals older than 7 days with no touch (GHL stage Proposal Sent, or
        store keys ``proposal:*``, with ``opptouch:<opportunity_id>`` resetting
        the clock); skipped with a note while there is no GHL token
    (d) Upwork rooms awaiting Lorenzo: the Upwork MCP is not available inside
        jobs, so this reads .tmp/upwork_rooms.json when a session has written it

Order: booked > positive > proposal > upwork; inside a kind by value, then by
age (oldest first) or start time (soonest first).

Output: the ordered list (printed), a Job_Log row and an ntfy digest.
Everything here is read-only against live systems; there is no write path.

CLI (from "Agentic Worklfows/"):
    python3 jobs/pipeline_sweep.py --dry-run             # live read-only pull, print, Job_Log row, no digest
    python3 jobs/pipeline_sweep.py --now                 # same plus the ntfy digest
    python3 jobs/pipeline_sweep.py --dry-run --fixtures  # offline replay on the recorded September replies
    python3 jobs/pipeline_sweep.py --dry-run --as-of 2026-09-21T21:10:00-05:00

Python 3.9 compatible. Never calls datetime.now() inside the logic: ``now`` is
injected (``--as-of`` on the CLI, a parameter in code).
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

if __package__ in (None, ""):  # run as a script: make "shared" importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import settings, slots  # noqa: E402
from shared.ghl import GHL  # noqa: E402
from shared.instantly import Instantly, default_client, InstantlyError  # noqa: E402
from shared.job_log import log_run  # noqa: E402
from shared.notify import notify  # noqa: E402
from shared.paths import tmp_file  # noqa: E402
from shared.store import Store, get_store  # noqa: E402

logger = logging.getLogger("jobs.pipeline_sweep")

JOB_NAME = "pipeline_sweep"

# ------------------------------------------------------------------- config
REPLY_SLA_HOURS = 24          # a positive reply unanswered this long is overdue
BOOKED_HORIZON_HOURS = 24     # booked calls inside this window must carry a confirmed flag
PROPOSAL_STALE_DAYS = 7       # proposals untouched this long are flagged
LOOKBACK_DAYS = 14            # how far back the Instantly email pull goes
# GET /emails is rate limited to 20 requests per minute
# (config/instantly_api_contract.md). The sweep pulls two types back to back,
# so the per-type cap must leave both inside one window: 9 + 9 = 18 calls.
# Hitting the cap is reported in the digest, never swallowed.
MAX_EMAIL_PAGES = 9           # 9 x 100 emails per type, 18 GET /emails calls per sweep

KIND_RANK = {"booked": 0, "positive": 1, "proposal": 2, "upwork": 3}

# Pipeline value used for ordering (same defaults as pipeline_sync).
try:
    from services.reply_engine.pipeline_sync import default_value_for_campaign  # noqa: E402
except Exception:  # noqa: BLE001 - keep the job standalone if the service moves
    def default_value_for_campaign(campaign_id: Optional[str]) -> float:  # type: ignore
        camp = settings.CAMPAIGN_BY_ID.get(campaign_id or "", {})
        return 7500.0 if camp.get("offer") == "outbound" else 6000.0

STORE_APPOINTMENT_PREFIX = "appointment:"   # {lead_email, start, confirmed, name, company, campaign_id, value}
STORE_PROPOSAL_PREFIX = "proposal:"         # {lead_email, sent_at, last_touch, name, company, campaign_id, value}
# opptouch:<opportunity_id> -> ISO timestamp of the last touch on a proposal.
# NOT "touch:": services/reply_engine/cadence.py owns that namespace with keys
# shaped touch:<campaign_id>:<lead_email>:<n>:<kind> holding dicts, so the old
# prefix matched cadence rows, never an opportunity id, and the proposal
# last-touch signal was silently dead.
STORE_OPP_TOUCH_PREFIX = "opptouch:"
STORE_TOUCH_PREFIX = STORE_OPP_TOUCH_PREFIX  # backwards-compatible alias
STORE_CONFIRMED_PREFIX = "confirmed:"       # written by show_rate.mark_confirmed when the lead replies "C"
UPWORK_ROOMS_FILE = "upwork_rooms.json"     # .tmp/upwork_rooms.json written by a Claude session with the Upwork MCP

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "services" / "reply_engine" / "tests" / "fixtures"

# show_rate owns the confirmation record; reuse its reader rather than
# re-implementing the reschedule rule. Imported lazily-safe so the job keeps
# running if the service module moves.
try:
    from services.reply_engine.show_rate import is_confirmed as _show_rate_is_confirmed  # noqa: E402
except Exception:  # noqa: BLE001
    _show_rate_is_confirmed = None


# ------------------------------------------------------------------ helpers
def parse_ts(value: Any, default_tz=timezone.utc) -> Optional[datetime]:
    """ISO string (Z or offset), epoch seconds/ms, or datetime -> aware datetime."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=default_tz)
    if isinstance(value, (int, float)):
        seconds = float(value) / (1000.0 if value > 1e11 else 1.0)
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            return slots.parse_iso(text)
        except Exception:  # noqa: BLE001
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=default_tz)


def hours_between(later: datetime, earlier: datetime) -> float:
    return (later - earlier).total_seconds() / 3600.0


def _lower(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _note(notes: Optional[List[str]], text: str) -> None:
    """Append a note when the caller passed a list, and always log it. Nothing
    in this job may fail silently: a row it could not read is a note, never a
    dropped item."""
    logger.warning("pipeline_sweep: %s", text)
    if notes is not None and text not in notes:
        notes.append(text)


def money(value: Any, default: float, label: str = "", notes: Optional[List[str]] = None) -> float:
    """Dollar value off a store or GHL row, tolerant of junk.

    The ``appointment:*`` / ``proposal:*`` store contract says ``value`` is a
    number, but a brief that writes ``"TBD"`` (or a GHL ``monetaryValue`` that
    is not parseable) used to raise ValueError straight out of the sweep, so
    Lorenzo got no digest and no Job_Log row at all on the morning one bad row
    existed. Fall back to the campaign default and say which key was bad.
    """
    if value in (None, "", False):
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        _note(notes, "unreadable value %r on %s; used the campaign default $%.0f" % (value, label or "a row", default))
        return float(default)


# Interest codes that are a statement of interest Lorenzo (or the router) made
# deliberately. -4 (no_show) is NOT one of them: it is a meeting-attendance
# state, and a no-show who writes back to reschedule is exactly the reply the
# sweep exists to catch (config/ids.json instantly.interest_status_codes).
EXPLICIT_NEGATIVE_STATUSES = (-1, -2, -3)

# Auto-responders. config/ids.json calls Instantly's code 0
# "out_of_office_or_neutral", so a 0 says nothing on its own and cannot be
# used to demote a row; the announcement in the subject can. Every marker
# below is taken from the recorded September pull, which holds 22
# auto-replies against 17 real ones.
AUTO_REPLY_SUBJECT_MARKERS = (
    "automatic reply", "automatic response", "auto reply", "auto-reply", "autoreply",
    "out of office", "out of the office", "outofoffice", "away from the office",
    "no longer monitored", "thank you for your e-mail", "thank you for your email",
    "on annual leave", "on maternity leave", "on parental leave", "on vacation",
)
AUTO_REPLY_SENDER_MARKERS = ("no-reply", "noreply", "do-not-reply", "donotreply",
                             "mailer-daemon", "postmaster")


def is_auto_reply(email: Dict[str, Any]) -> bool:
    """An out-of-office / mailbox-robot row, decided by what it announces about
    itself rather than by Instantly's interest code.

    Without this, one AI mislabel on an auto-responder puts an out-of-office at
    the top of the 07:30 money-ordered list, at the same $6,000-$7,500 rank as
    a real prospect.
    """
    subject = _lower(email.get("subject"))
    for marker in AUTO_REPLY_SUBJECT_MARKERS:
        if marker in subject:
            return True
    sender = _lower(email.get("from_address_email") or email.get("lead"))
    local_part = sender.split("@")[0] if sender else ""
    return any(marker in local_part for marker in AUTO_REPLY_SENDER_MARKERS)


def is_positive_reply(email: Dict[str, Any]) -> bool:
    """i_status 1 or ai_interest_value 1, unless Lorenzo explicitly set a
    negative status (an explicit -1/-2/-3 overrides the AI guess) or the row
    announces itself as an auto-responder. -4 no_show falls through to the AI
    value.

    An explicit i_status 1 is Lorenzo's own click and always wins; code 0 is
    "out_of_office_or_neutral" and therefore proves nothing either way, which
    is why the auto-reply test reads the subject instead.
    """
    i_status = email.get("i_status")
    ai = email.get("ai_interest_value")
    if i_status == 1:
        return True
    if i_status in EXPLICIT_NEGATIVE_STATUSES:
        return False
    if is_auto_reply(email):
        return False
    return ai == 1


def is_reengagement(email: Dict[str, Any]) -> bool:
    """A lead already marked not interested / wrong person / lost whose reply
    still reads positive.

    Instantly stamps the lead's CURRENT status on every email row, so a
    negative status says nothing about whether it was set before or after this
    reply. Suppressing these outright means that from the moment Lorenzo marks
    a lead lost, that lead's comeback ("Sorry I missed Friday, still want to do
    this") is invisible to the safety net forever. ``find_awaiting_replies``
    surfaces them and flags them so Lorenzo can see why.
    """
    if is_auto_reply(email):
        return False
    return email.get("i_status") in EXPLICIT_NEGATIVE_STATUSES and email.get("ai_interest_value") == 1


UE_TYPE_OUTBOUND = 3   # Instantly's own direction flag on a manual row
UE_TYPE_INBOUND = 2


def is_outbound(email: Dict[str, Any]) -> bool:
    """Direction of a row in Instantly's manual list, which carries BOTH
    directions of a thread.

    Three signals, in order of how much the live API guarantees them:

    1. ``ue_type``: Instantly's own direction flag, 3 outbound / 2 inbound.
    2. the sender: a row is Lorenzo's only when it was sent FROM the campaign
       inbox.
    3. the recipients, and then EVERY recipient must differ from the inbox: a
       lead who replies-all, CCs a colleague or writes to two Advero inboxes
       still addresses the inbox, and reading that as Lorenzo's own reply marks
       the whole thread answered and drops the unanswered positive from the
       sweep.

    Verified read-only on 2026-09-21 against ``GET /emails?email_type=manual``:
    145 rows, all 145 carrying ``ue_type`` AND ``from_address_email`` (30 with
    ue_type 3, whose sender is the inbox; 115 with ue_type 2). So on live data
    signal 1 decides every row. The recorded September fixture omits both
    fields, which is why the recipient fallback is the branch the
    fixture-driven tests exercise; see the cross-cutting request to re-record
    it in the live shape.
    """
    ue_type = email.get("ue_type")
    if ue_type == UE_TYPE_OUTBOUND:
        return True
    if ue_type == UE_TYPE_INBOUND:
        return False
    eaccount = _lower(email.get("eaccount"))
    sender = _lower(email.get("from_address_email"))
    if sender:
        return sender == eaccount
    to_field = email.get("to_address_email_list") or ""
    recipients = [_lower(x) for x in str(to_field).replace(";", ",").split(",") if x.strip()]
    if not recipients:
        return False
    return all(r != eaccount for r in recipients)


def email_text(email: Dict[str, Any]) -> str:
    """Reply body: flattened ``text`` (fixtures), live ``body.text``, else
    ``content_preview`` (the live GET /emails shape)."""
    text = email.get("text")
    if not text:
        body = email.get("body")
        if isinstance(body, dict):
            text = body.get("text")
        elif isinstance(body, str):
            text = body
    return text or email.get("content_preview") or ""


def snippet(text: Optional[str], n: int = 110) -> str:
    body = slots.strip_quoted(text or "").strip().replace("\n", " ")
    body = " ".join(body.split())
    return body if len(body) <= n else body[: n - 3] + "..."


def campaign_label(campaign_id: Optional[str]) -> str:
    camp = settings.CAMPAIGN_BY_ID.get(campaign_id or "", {})
    return camp.get("key") or (campaign_id or "")[:8]


# ---------------------------------------------------------- (a) positives
def _reply_order(email: Dict[str, Any], ts: datetime) -> tuple:
    """Sort key for "which of these two replies is the later one".

    Instantly stamps ``timestamp_created`` to whole seconds (every row in the
    recorded pull ends ``.000Z``), so a lead who fires "Actually hold on." and
    "Thursday 4pm works, send the invite." inside one second used to be shown
    as the first of the two, with ``reply_to_uuid`` pointing at the wrong
    email. ``timestamp_email`` (live rows carry it) then the row id break the
    tie: Instantly's ids are time-ordered, so the later message wins
    deterministically.
    """
    return (ts, str(email.get("timestamp_email") or ""), str(email.get("id") or ""))


def find_awaiting_replies(
    received: Iterable[Dict[str, Any]],
    manual: Iterable[Dict[str, Any]],
    now: datetime,
    sla_hours: int = REPLY_SLA_HOURS,
    leads_by_email: Optional[Dict[str, Dict[str, Any]]] = None,
    notes: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Positive inbound replies with no outbound from Lorenzo after them.

    Pure function: ``received`` = GET /emails?email_type=received rows,
    ``manual`` = GET /emails?email_type=manual rows (both directions), ``now``
    injected. One item per thread, for the latest positive inbound.

    A positive Instantly could not thread (no ``thread_id``: a forwarded
    message, a shape change) is NOT dropped. The one thing this job exists to
    prevent is an unanswered positive going unseen, so it falls back to
    (lead, campaign) as the thread key and adds an ``unthreadable_positives``
    note, which makes ``run_sweep`` report the run as partial.
    """
    latest_inbound = {}  # type: Dict[str, Dict[str, Any]]
    unthreadable = 0
    undated = 0
    for email in received:
        positive = is_positive_reply(email)
        reengaged = False if positive else is_reengagement(email)
        if not positive and not reengaged:
            continue
        email = dict(email, _reengaged=reengaged)
        ts = parse_ts(email.get("timestamp_created"))
        if ts is None:
            undated += 1
            continue
        thread = email.get("thread_id")
        if not thread:
            unthreadable += 1
            thread = "no-thread:%s|%s" % (
                _lower(email.get("lead") or email.get("from_address_email")),
                email.get("campaign_id") or "",
            )
        current = latest_inbound.get(thread)
        if current is None or _reply_order(email, ts) > _reply_order(current, current["_ts"]):
            latest_inbound[thread] = dict(email, _ts=ts)
    if unthreadable:
        _note(notes, "unthreadable_positives: %d positive repl%s had no thread_id and were keyed on (lead, campaign)"
              % (unthreadable, "y" if unthreadable == 1 else "ies"))
    if undated:
        _note(notes, "undated_positives: %d positive repl%s had no readable timestamp_created and could not be ranked"
              % (undated, "y" if undated == 1 else "ies"))

    last_outbound = {}  # type: Dict[str, datetime]
    for email in manual:
        if not is_outbound(email):
            continue
        ts = parse_ts(email.get("timestamp_created"))
        thread = email.get("thread_id")
        if not thread or ts is None:
            continue
        if thread not in last_outbound or ts > last_outbound[thread]:
            last_outbound[thread] = ts

    items = []  # type: List[Dict[str, Any]]
    for thread, inbound in latest_inbound.items():
        out_ts = last_outbound.get(thread)
        if out_ts is not None and out_ts > inbound["_ts"]:
            continue  # Lorenzo answered after the latest positive reply
        email = _lower(inbound.get("lead") or inbound.get("from_address_email"))
        lead = (leads_by_email or {}).get(email, {})
        age = hours_between(now, inbound["_ts"])
        campaign_id = inbound.get("campaign_id") or lead.get("campaign")
        name = ("%s %s" % (lead.get("first_name") or "", lead.get("last_name") or "")).strip()
        items.append({
            "kind": "positive",
            "lead_email": email,
            "name": name or email,
            "company": lead.get("company_name") or "",
            "campaign_id": campaign_id,
            "campaign": campaign_label(campaign_id),
            # the row's own thread id, which is None when the sweep had to fall
            # back to (lead, campaign) as the grouping key; never the synthetic key
            "thread_id": inbound.get("thread_id"),
            "threaded": bool(inbound.get("thread_id")),
            "eaccount": inbound.get("eaccount"),
            "reply_to_uuid": inbound.get("id"),
            "inbound_at": inbound["_ts"].isoformat(),
            "last_outbound_at": out_ts.isoformat() if out_ts else None,
            "age_hours": round(age, 1),
            "overdue": age >= sla_hours,
            "value": default_value_for_campaign(campaign_id),
            "snippet": snippet(email_text(inbound)),
            "subject": inbound.get("subject"),
            "previously_negative": bool(inbound.get("_reengaged")),
            "interest_status": inbound.get("i_status"),
        })
    return items


def fetch_emails(
    instantly: Instantly,
    email_type: str,
    now: datetime,
    lookback_days: int = LOOKBACK_DAYS,
    max_pages: int = MAX_EMAIL_PAGES,
    page_size: int = 100,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Read-only pull of GET /emails for one type inside the lookback window.

    Returns (rows, error). ``error`` is a short string when the pull could not
    be completed: an Instantly failure, or the page cap. It is never swallowed,
    because a sweep that could not read a single reply must not print a clean
    "0 item(s)" on Lorenzo's phone.

    Rows are FILTERED against the cutoff, never cut off at the first old row:
    GET /emails is not guaranteed to be strictly newest-first, and one
    out-of-order row used to truncate the whole pull.

    Paging is walked here rather than through ``Instantly.iterate`` so the cap
    can be reported on the FACT that stopped the walk, not on a row count.
    ``iterate`` yields items and swallows the cursor, so the old guard
    (">= max_pages whole pages accumulated") was wrong in both directions: a
    filtered pull that answers 50 rows per page never reached a whole page, so
    hitting the 9-page cap with unread replies behind it printed a clean list;
    and nine complete pages ending with a null cursor (a finished pull) raised
    a false ``instantly_page_cap`` that made the run ``partial`` and broke the
    deployment runbook's shadow gate.
    """
    cutoff = now - timedelta(days=lookback_days)
    out = []  # type: List[Dict[str, Any]]
    pages = 0
    cursor = None  # type: Optional[str]
    try:
        while pages < max_pages:
            page = instantly.list_emails(email_type=email_type, limit=page_size, starting_after=cursor)
            pages += 1
            if isinstance(page, dict):
                items = page.get("items") or []
                cursor = page.get("next_starting_after")
            elif isinstance(page, list):     # some v2 endpoints answer a bare array
                items, cursor = list(page), None
            else:
                items, cursor = [], None
            in_window = 0
            for email in items:
                ts = parse_ts(email.get("timestamp_created"))
                if ts is None or ts >= cutoff:
                    out.append(email)
                    in_window += 1
            if not cursor:
                return out, None             # the cursor is exhausted: a complete pull
            if items and in_window == 0:
                return out, None             # a whole page older than the window: done
    except InstantlyError as exc:
        logger.warning("pipeline_sweep: emails pull (%s) failed: %s", email_type, exc)
        return out, "instantly_read_failed(%s): %s" % (email_type, exc)
    error = (
        "instantly_page_cap(%s): stopped after %d pages with the cursor still open, so older replies "
        "in the %d-day window were not read" % (email_type, pages, lookback_days)
    )
    logger.warning("pipeline_sweep: %s", error)
    return out, error


def fetch_leads(instantly: Instantly, emails: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    """Lead records (name, company, campaign) for the flagged emails."""
    wanted = sorted(set(e for e in emails if e))
    out = {}  # type: Dict[str, Dict[str, Any]]
    for i in range(0, len(wanted), 50):
        chunk = wanted[i:i + 50]
        try:
            for lead in instantly.iterate("leads/list", body={"contacts": chunk, "limit": 100}, max_pages=3):
                out[_lower(lead.get("email"))] = lead
        except InstantlyError as exc:
            logger.warning("pipeline_sweep: leads lookup failed: %s", exc)
    return out


# -------------------------------------------------------- (b) booked calls
def _seed_appointments_from_ids(now: datetime) -> List[Dict[str, Any]]:
    """ids.json google_calendar.booked_this_week, future events only (stale
    entries age out by themselves)."""
    out = []  # type: List[Dict[str, Any]]
    for row in (settings.IDS.get("google_calendar") or {}).get("booked_this_week") or []:
        start = parse_ts(row.get("start"))
        if start is None or start < now - timedelta(minutes=15):
            continue
        out.append({
            "lead_email": row.get("email"),
            "name": row.get("who"),
            "start": start.isoformat(),
            "confirmed": bool(row.get("confirmed", False)),
            "note": row.get("note"),
            "source": "ids.json",
        })
    return out


def format_start_ct(start: datetime) -> str:
    """"Wed 11:30 AM CT". slots.format_slot drops the meridiem and the zone,
    which leaves an 11:30 call on Lorenzo's 07:30 push ambiguous."""
    local = start.astimezone(settings.TZ)
    return "%s %s:%02d %s CT" % (
        local.strftime("%a"),
        ((local.hour - 1) % 12) + 1,
        local.minute,
        local.strftime("%p").upper(),
    )


def appointment_id_of(appt: Dict[str, Any]) -> Optional[str]:
    """The id ``show_rate`` keys its confirmation record on: the row's own
    ``appointment_id`` / ``id``, else the tail of the ``appointment:<id>``
    store key ``appointments_from_store`` attached."""
    for key in ("appointment_id", "id"):
        value = appt.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    store_key = appt.get("store_key") or ""
    if isinstance(store_key, str) and store_key.startswith(STORE_APPOINTMENT_PREFIX):
        tail = store_key[len(STORE_APPOINTMENT_PREFIX):].strip()
        return tail or None
    return None


def is_confirmed(appt: Dict[str, Any], store: Optional[Store] = None) -> bool:
    """Has this call been confirmed?

    ``booking.appointment_payload`` hard-codes ``confirmed: False`` into the
    ``appointment:<id>`` row and never comes back to patch it. The lead's "C"
    reply is recorded by ``show_rate.mark_confirmed``, which writes a DIFFERENT
    key, ``confirmed:<appointment_id>``. Reading only ``appt["confirmed"]``
    therefore re-emitted every already-confirmed call at the top of every
    morning digest, which is the one position on the list that is supposed to
    mean "act on this now".

    ``show_rate.is_confirmed`` owns the rule (including "a reschedule drops a
    confirmation that was for the old start"), so reuse it and only fall back
    to reading the key directly if that module is unavailable.
    """
    if appt.get("confirmed") or appt.get("confirmed_by_reply"):
        return True
    if store is None:
        return False
    appt_id = appointment_id_of(appt)
    if not appt_id:
        return False
    record = {"id": appt_id, "start_iso": appt.get("start_iso") or appt.get("start"), "confirmed": False}
    if _show_rate_is_confirmed is not None:
        try:
            return bool(_show_rate_is_confirmed(store, record))
        except Exception as exc:  # noqa: BLE001 - never let this end the sweep
            logger.warning("pipeline_sweep: show_rate.is_confirmed failed for %s: %s", appt_id, exc)
    return bool(store.get(STORE_CONFIRMED_PREFIX + appt_id))


def find_unconfirmed_calls(
    appointments: Iterable[Dict[str, Any]],
    now: datetime,
    horizon_hours: int = BOOKED_HORIZON_HOURS,
    store: Optional[Store] = None,
    notes: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Appointments starting inside the horizon that are not confirmed.

    ``store`` is what lets the show-rate confirmation flag be seen; without it
    only the row's own ``confirmed`` field counts. One malformed row is a note,
    never the end of the run.
    """
    items = []  # type: List[Dict[str, Any]]
    for appt in appointments:
        label = appt.get("store_key") or appt.get("appointment_id") or appt.get("lead_email") or "an appointment row"
        try:
            start = parse_ts(appt.get("start"))
            if start is None:
                continue
            if start < now - timedelta(minutes=15) or start > now + timedelta(hours=horizon_hours):
                continue
            if is_confirmed(appt, store):
                continue
            campaign_id = appt.get("campaign_id")
            items.append({
                "kind": "booked",
                "lead_email": _lower(appt.get("lead_email")),
                "name": appt.get("name") or appt.get("lead_email") or "",
                "company": appt.get("company") or "",
                "campaign_id": campaign_id,
                "campaign": campaign_label(campaign_id),
                "start": start.isoformat(),
                "start_ct": format_start_ct(start),
                "hours_until": round(hours_between(start, now), 1),
                "confirmed": False,
                "value": money(appt.get("value"), default_value_for_campaign(campaign_id), str(label), notes),
                "source": appt.get("source") or "store",
                "note": appt.get("note"),
            })
        except Exception as exc:  # noqa: BLE001 - one bad row must not kill the 07:30 sweep
            _note(notes, "unreadable booked call %s: %s" % (label, exc))
    return items


def appointments_from_store(store: Store) -> List[Dict[str, Any]]:
    out = []  # type: List[Dict[str, Any]]
    for key in store.keys(STORE_APPOINTMENT_PREFIX):
        val = store.get(key)
        if isinstance(val, dict):
            out.append(dict(val, source="store", store_key=key))
    return out


def _appointment_person(appt: Dict[str, Any]) -> str:
    """The person a booked call names, without the company suffix.

    config/ids.json writes "Ilmi Curovic / Shining Armor Cleaning NJ" while the
    booking engine stores "Ilmi Curovic", so comparing the raw strings never
    matched and the same call was listed twice.
    """
    return _lower((str(appt.get("name") or appt.get("who") or "")).split("/")[0])


def _appointment_key(appt: Dict[str, Any]) -> tuple:
    """Identity of a booked call across the two sources.

    The start is normalised to UTC before it is compared: the booking engine
    stores Ilmi's call as ``2026-09-23T16:30:00+00:00`` and config/ids.json as
    ``2026-09-23T11:30:00-05:00``. Those are the same instant, but comparing
    ``isoformat()`` strings kept the offset, so neither the email+start nor the
    start+name fallback matched and the 07:30 digest led with the same call
    twice.
    """
    start = parse_ts(appt.get("start"))
    return (
        _lower(appt.get("lead_email")),
        start.astimezone(timezone.utc).isoformat() if start else "",
        _appointment_person(appt),
    )


def merge_appointments(stored: Iterable[Dict[str, Any]], seeded: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Store rows plus the ids.json seed, de-duplicated.

    The seed used to be all-or-nothing on the whole store, so the first
    appointment the booking engine ever wrote hid both calls already on
    Lorenzo's calendar. A seeded row is dropped only when the store already
    holds that same call (same email, or same start time and name).
    """
    out = list(stored)
    have = set(_appointment_key(a) for a in out)
    have_start_email = set((k[0], k[1]) for k in have if k[0])
    have_start_name = set((k[1], k[2]) for k in have if k[2])
    for appt in seeded:
        key = _appointment_key(appt)
        if key in have:
            continue
        if key[0] and (key[0], key[1]) in have_start_email:
            continue
        if key[2] and (key[1], key[2]) in have_start_name:
            continue
        out.append(appt)
        have.add(key)
    return out


# ---------------------------------------------------------- (c) proposals
def find_stale_proposals(
    proposals: Iterable[Dict[str, Any]],
    now: datetime,
    touches: Optional[Dict[str, Any]] = None,
    stale_days: int = PROPOSAL_STALE_DAYS,
    notes: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Proposals whose last touch (store touch, last_touch, updatedAt,
    lastStageChangeAt, sent_at) is older than ``stale_days``.

    One malformed row is a note, never the end of the run.
    """
    touches = touches or {}
    items = []  # type: List[Dict[str, Any]]
    for prop in proposals:
        opp_id = prop.get("id") or prop.get("opportunity_id")
        label = prop.get("store_key") or opp_id or prop.get("lead_email") or "a proposal row"
        try:
            candidates = [
                touches.get(opp_id) if opp_id else None,
                prop.get("last_touch"),
                prop.get("updatedAt"),
                prop.get("lastStageChangeAt"),
                prop.get("sent_at"),
                prop.get("createdAt"),
            ]
            stamps = [parse_ts(c) for c in candidates]
            stamps = [s for s in stamps if s is not None]
            if not stamps:
                continue
            last = max(stamps)
            age_days = (now - last).total_seconds() / 86400.0
            if age_days < stale_days:
                continue
            contact = prop.get("contact") or {}
            email = _lower(prop.get("lead_email") or contact.get("email") or prop.get("email"))
            campaign_id = prop.get("campaign_id")
            raw_value = prop.get("monetaryValue")
            if raw_value in (None, "", False):
                raw_value = prop.get("value")
            items.append({
                "kind": "proposal",
                "lead_email": email,
                "name": prop.get("name") or contact.get("name") or email,
                "company": prop.get("company") or contact.get("companyName") or "",
                "campaign_id": campaign_id,
                "campaign": campaign_label(campaign_id),
                "opportunity_id": opp_id,
                "last_touch": last.isoformat(),
                "age_days": round(age_days, 1),
                "value": money(raw_value, default_value_for_campaign(campaign_id), str(label), notes),
                "source": prop.get("source") or "ghl",
            })
        except Exception as exc:  # noqa: BLE001 - one bad row must not kill the 07:30 sweep
            _note(notes, "unreadable proposal %s: %s" % (label, exc))
    return items


def proposals_from_ghl(ghl: GHL) -> Optional[List[Dict[str, Any]]]:
    """Opportunities in stage Proposal Sent; None when GHL cannot be read."""
    if not ghl.has_token:
        return None
    stage_id = (settings.GHL_STAGES or {}).get("proposal_sent")
    try:
        page = ghl.search_opportunities(pipeline_id=settings.GHL_SALES_PIPELINE_ID, stage_id=stage_id, limit=100)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pipeline_sweep: GHL proposals read failed: %s", exc)
        return None
    if page is None:
        return None
    if isinstance(page, dict):
        rows = page.get("opportunities") or page.get("items") or []
    else:
        rows = list(page)
    return [dict(r, source="ghl") for r in rows]


def proposals_from_store(store: Store) -> List[Dict[str, Any]]:
    out = []  # type: List[Dict[str, Any]]
    for key in store.keys(STORE_PROPOSAL_PREFIX):
        val = store.get(key)
        if isinstance(val, dict):
            out.append(dict(val, source="store", store_key=key))
    return out


def touches_from_store(store: Store) -> Dict[str, Any]:
    """``opptouch:<opportunity_id>`` -> ISO timestamp of the last touch.

    The prefix used to be ``touch:``, which is cadence.py's namespace
    (``touch:<campaign_id>:<lead_email>:<n>:<kind>`` holding dicts): every key
    it found was a cadence row whose tail never matched an opportunity id, so
    the proposal last-touch signal was dead and only failed safe because
    ``parse_ts`` on a dict returns None.
    """
    out = {}  # type: Dict[str, Any]
    for key in store.keys(STORE_OPP_TOUCH_PREFIX):
        out[key[len(STORE_OPP_TOUCH_PREFIX):]] = store.get(key)
    return out


# --------------------------------------------------------- (d) Upwork hook
def load_upwork_rooms(path: Optional[Path] = None) -> Optional[List[Dict[str, Any]]]:
    """Hook: .tmp/upwork_rooms.json written by a session that has the Upwork
    MCP. None when the file is absent (the job skips gracefully)."""
    path = path or tmp_file(UPWORK_ROOMS_FILE)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.warning("pipeline_sweep: could not read %s: %s", path, exc)
        return None
    rooms = data.get("rooms", data) if isinstance(data, dict) else data
    return list(rooms) if isinstance(rooms, list) else []


def find_upwork_awaiting(rooms: Iterable[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    items = []  # type: List[Dict[str, Any]]
    for room in rooms:
        awaiting = room.get("awaiting", room.get("awaiting_you"))
        if awaiting in (None, False, "", "client", "them"):
            continue
        last = parse_ts(room.get("last_message_at") or room.get("last_at"))
        age = hours_between(now, last) if last else None
        items.append({
            "kind": "upwork",
            "lead_email": "",
            "name": room.get("client") or room.get("title") or room.get("room_id") or "",
            "company": room.get("job_title") or "",
            "room_id": room.get("room_id"),
            "last_message_at": last.isoformat() if last else None,
            "age_hours": round(age, 1) if age is not None else None,
            "overdue": bool(age is not None and age >= 1),  # Upwork SLA is 1 hour (M6)
            "value": float(room.get("value") or 0.0),
            "snippet": snippet(room.get("last") or room.get("last_message")),
            "source": "upwork_rooms.json",
        })
    return items


# ----------------------------------------------------------------- ordering
def order_items(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """booked > positive > proposal > upwork; inside a kind: value desc, then
    soonest start (booked) or oldest wait (others)."""
    def key(item: Dict[str, Any]):
        rank = KIND_RANK.get(item.get("kind"), 9)
        value = -float(item.get("value") or 0.0)
        if item.get("kind") == "booked":
            tiebreak = float(item.get("hours_until") or 0.0)
        else:
            tiebreak = -float(item.get("age_hours") or (item.get("age_days") or 0.0) * 24.0)
        return (rank, value, tiebreak, item.get("lead_email") or item.get("name") or "")
    return sorted(items, key=key)


def _first_name(who: str) -> str:
    """First name only, for the push notification.

    Anything that looks like an address is refused outright and becomes
    "a lead". ``name`` falls back to the lead's email address in three real
    paths: Instantly holds the lead without a first name, ``fetch_leads``
    swallowed an ``InstantlyError`` so ``leads_by_email`` is empty, or the
    booking brief wrote an ``appointment:*`` row with no name. Splitting on
    spaces and slashes leaves such an address whole, so the "first names and
    counts only" push carried the prospect's address.

    ``shared.notify.redact()`` catches it today, but that layer is skipped the
    moment ``NTFY_TOKEN`` or ``NTFY_ALLOW_SENSITIVE=1`` is set (which
    runbooks/deployment.md recommends as hardening), and the email leg receives
    the same string either way.
    """
    text = (who or "").strip()
    if "@" in text:
        return "a lead"
    return text.split(" ")[0].split("/")[0].strip() or "a lead"


def render_digest(
    items: List[Dict[str, Any]],
    now: datetime,
    notes: Optional[List[str]] = None,
    redact: bool = False,
) -> str:
    """The ordered list as text.

    ``redact=True`` is the version that leaves the laptop: the ntfy topic is an
    unauthenticated public URL, so the push carries first names and counts
    only, never a prospect's address, company or the words they wrote. The full
    version stays in the console, the Job_Log row and the return value.
    """
    lines = ["Pipeline sweep %s CT: %d item(s)" % (now.astimezone(settings.TZ).strftime("%a %b %d %I:%M %p").replace(" 0", " "), len(items))]
    for i, item in enumerate(items, 1):
        kind = item["kind"]
        who = item.get("name") or item.get("lead_email") or "?"
        if redact:
            who = _first_name(who)
        elif item.get("company") and item["company"] not in who:
            who = "%s (%s)" % (who, item["company"])
        if kind == "booked":
            lines.append("%d. BOOKED %s, %s, in %.0f h, not confirmed" % (i, who, item.get("start_ct"), item.get("hours_until") or 0))
        elif kind == "positive":
            flag = "OVERDUE" if item.get("overdue") else "awaiting reply"
            if item.get("previously_negative"):
                flag = "%s, previously marked %s" % (flag, interest_label(item.get("interest_status")))
            line = "%d. POSITIVE %s [%s], %s, %.0f h" % (i, who, item.get("campaign"), flag, item.get("age_hours") or 0)
            if not redact:
                line = "%s: %s" % (line, item.get("snippet") or "")
            lines.append(line)
        elif kind == "proposal":
            lines.append("%d. PROPOSAL %s, %.0f days since last touch, $%.0f" % (i, who, item.get("age_days") or 0, item.get("value") or 0))
        else:
            age = item.get("age_hours")
            line = "%d. UPWORK %s, %s" % (i, who, ("%.0f h waiting" % age) if age is not None else "waiting")
            if not redact:
                line = "%s: %s" % (line, item.get("snippet") or "")
            lines.append(line)
    if redact and items:
        lines.append("Names and replies are in the console output and the Job_Log sheet.")
    for note in notes or []:
        lines.append("note: %s" % note)
    return "\n".join(lines)


def interest_label(value: Any) -> str:
    codes = (settings.IDS.get("instantly") or {}).get("interest_status_codes") or {}
    return str(codes.get(str(value), value))


# ---------------------------------------------------------------------- run
def run_sweep(
    now: datetime,
    instantly: Optional[Instantly] = None,
    ghl: Optional[GHL] = None,
    store: Optional[Store] = None,
    received: Optional[List[Dict[str, Any]]] = None,
    manual: Optional[List[Dict[str, Any]]] = None,
    leads_by_email: Optional[Dict[str, Dict[str, Any]]] = None,
    upwork_rooms_path: Optional[Path] = None,
    dry_run: bool = True,
    send_digest: Optional[bool] = None,
) -> Dict[str, Any]:
    """One sweep. Pass ``received`` / ``manual`` to skip the Instantly pull
    (fixtures, tests). Read-only against every live system."""
    notes = []  # type: List[str]
    store = store if store is not None else get_store()
    ghl = ghl if ghl is not None else GHL()
    read_failed = False

    # (a) positives
    if received is None or manual is None:
        if instantly is None:
            instantly = default_client()
        if received is None:
            received, err = fetch_emails(instantly, "received", now)
            if err:
                notes.append(err)
                read_failed = True
        if manual is None:
            manual, err = fetch_emails(instantly, "manual", now)
            if err:
                notes.append(err)
                read_failed = True
    if leads_by_email is None and instantly is not None:
        wanted = set(_lower(e.get("lead") or e.get("from_address_email"))
                     for e in received if is_positive_reply(e) or is_reengagement(e))
        leads_by_email = fetch_leads(instantly, wanted) if wanted else {}
    # Notes the ROW readers raise (a reply with no thread_id, a store row whose
    # value is not a number). They are collected separately from the run notes
    # so an unreadable row makes the run "partial" the way a failed pull does,
    # instead of disappearing behind the routine "ghl_token_missing" line.
    row_notes = []  # type: List[str]
    positives = find_awaiting_replies(received, manual, now, leads_by_email=leads_by_email, notes=row_notes)

    # (b) booked: the store and the ids.json calendar seed, merged. Never
    # either/or: the first appointment the engine writes must not hide the
    # calls already on the calendar.
    appointments = merge_appointments(appointments_from_store(store), _seed_appointments_from_ids(now))
    if any(a.get("source") == "ids.json" for a in appointments):
        notes.append("booked calls include the config/ids.json calendar seed")
    # ``store`` is passed so a call the lead already confirmed with a "C" reply
    # (show_rate writes confirmed:<id>, not the appointment row) leaves the list.
    booked = find_unconfirmed_calls(appointments, now, store=store, notes=row_notes)

    # (c) proposals
    proposals = proposals_from_ghl(ghl)
    if proposals is None:
        notes.append("ghl_token_missing: proposal check used store proposal:* keys only")
        proposals = []
    proposals = proposals + proposals_from_store(store)
    stale = find_stale_proposals(proposals, now, touches=touches_from_store(store), notes=row_notes)
    degraded = bool(row_notes)
    notes.extend(row_notes)

    # (d) upwork
    rooms = load_upwork_rooms(upwork_rooms_path)
    if rooms is None:
        from shared import turned_off

        if turned_off.upwork_rooms_off():
            # Lorenzo turned the scheduled Upwork rooms digests off and checks
            # the rooms by hand (config/turned_off_jobs.json): not a gap.
            notes.append("upwork rooms: %s; not part of this sweep" % turned_off.label("upwork_rooms_am"))
        else:
            notes.append("upwork: no .tmp/upwork_rooms.json (Upwork MCP unavailable in jobs); skipped")
        upwork = []  # type: List[Dict[str, Any]]
    else:
        upwork = find_upwork_awaiting(rooms, now)

    items = order_items(booked + positives + stale + upwork)
    counts = {
        "booked": len(booked),
        "positive": len(positives),
        "positive_overdue": sum(1 for p in positives if p.get("overdue")),
        "proposal": len(stale),
        "upwork": len(upwork),
        "total": len(items),
    }
    if read_failed:
        notes.append("instantly_emails_unreadable: positives were NOT fully checked this run")
    digest = render_digest(items, now, notes)
    if dry_run:
        status = "dry_run_partial" if (read_failed or degraded) else "dry_run"
    else:
        status = "partial" if (read_failed or degraded) else "ok"
    log_run(JOB_NAME, status, {
        "as_of": now.isoformat(), "counts": counts, "notes": notes,
        "top": [{"kind": i["kind"], "who": i.get("name") or i.get("lead_email"), "value": i.get("value")} for i in items[:5]],
        "received": len(received), "manual": len(manual), "read_failed": read_failed, "degraded": degraded,
    })
    if send_digest is None:
        send_digest = not dry_run
    sent = None
    if send_digest:
        # A failed pull is never a quiet "nothing waiting": Lorenzo has to know
        # the sweep could not read the replies.
        priority = "high" if (booked or counts["positive_overdue"] or read_failed) else "default"
        title = "Pipeline sweep: could not read Instantly" if read_failed else (
            "Pipeline sweep: %d waiting on you" % len(items))
        sent = notify(title, render_digest(items, now, notes, redact=True), priority=priority, tags=["clipboard"])
    return {"job": JOB_NAME, "as_of": now.isoformat(), "mode": settings.get_mode(), "dry_run": dry_run,
            "items": items, "counts": counts, "notes": notes, "digest": digest, "notified": sent,
            "status": status, "read_failed": read_failed, "degraded": degraded, "row_notes": row_notes}


def load_fixtures(directory: Path = FIXTURES_DIR) -> Dict[str, Any]:
    def _load(name: str) -> List[Dict[str, Any]]:
        with open(directory / name, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else list(data.get("items", []))
    leads = _load("instantly_replied_leads_2026-09.json")
    return {
        "received": _load("instantly_replies_2026-09.json"),
        "manual": _load("instantly_manual_sent_2026-09.json"),
        "leads_by_email": {_lower(l.get("email")): l for l in leads},
    }


def _parse_as_of(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now(timezone.utc)  # CLI default only; library code always receives ``now``
    parsed = parse_ts(value)
    if parsed is None:
        raise SystemExit("--as-of must be an ISO timestamp, got %r" % value)
    return parsed


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Pipeline sweep: what is waiting on Lorenzo, ordered by money (S8 / O3)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="pull (read-only), print, Job_Log row; no digest")
    group.add_argument("--now", action="store_true", help="pull, print, Job_Log row and send the ntfy digest")
    parser.add_argument("--as-of", help="ISO timestamp used as 'now' (replay / tests)")
    parser.add_argument("--fixtures", action="store_true", help="use the recorded September fixtures instead of the Instantly API")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.dry_run:
        # scratch logs: see shared.job_log.use_scratch_logs. --now is the real
        # run and keeps the real log.
        from shared.job_log import use_scratch_logs

        use_scratch_logs("pipeline_sweep_dryrun")

    now = _parse_as_of(args.as_of)
    kwargs = {}  # type: Dict[str, Any]
    if args.fixtures:
        kwargs.update(load_fixtures())
        kwargs["ghl"] = GHL(token=None)
    result = run_sweep(now, dry_run=bool(args.dry_run), **kwargs)
    if args.json:
        print(json.dumps(result, indent=1, default=str))
    else:
        print(result["digest"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
