"""Shadow-safe poller: reads inbound replies with GET /emails (email_type=received)
and feeds process_event(). It exists because no Instantly webhook may be created
before go-live approval (config/ids.json: webhooks none).

    python3 -m services.reply_engine.poller --dry-run [--limit 200] [--pages 5] [--json] [--start-at 2026-09-15]

--dry-run uses the live key READ-ONLY, forces MODE=shadow, keeps its state in a
throwaway store and prints what would be done. Nothing is sent, tagged or moved.
"""
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from shared import job_log, llm, settings, slots

from services.reply_engine.models import ReplyEvent

logger = logging.getLogger("reply_engine.poller")

MAX_FAILED_ATTEMPTS = 3   # after this a failing reply stops holding the cursor
CURSOR_KEY = "poller:cursor"
SEEN_KEY = "poller:seen"
FAILED_KEY = "poller:failed"   # email ids whose process_event raised; retried next run
SEEN_MAX = 5000
PAGE_LIMIT = 100


def campaign_ids() -> List[str]:
    return [v.get("id") for v in settings.CAMPAIGNS.values() if v.get("id")]


def own_inboxes() -> set:
    inst = settings.IDS.get("instantly", {})
    return set(inst.get("active_inboxes", []) or []) | {"lorenzo@adverosolutions.com", "lorenzovillarreal@adverosolutions.com"}


BEFORE_START = "before_start_date"   # the skip reason of a reply older than the start date


def _row_time(value: Any) -> Optional[datetime]:
    """A GET /emails ``timestamp_created`` as an aware datetime, or None."""
    if value in (None, ""):
        return None
    try:
        return slots.parse_iso(str(value))
    except (ValueError, TypeError):
        return None


def _before_start(ts: str, start_at: Optional[datetime]) -> bool:
    """True when the row's time is known and earlier than ``start_at``. A row
    with no readable time is never skipped for it (it is processed, or fails
    and is retried, exactly as before the start date existed)."""
    if start_at is None:
        return False
    at = _row_time(ts)
    return at is not None and at < start_at


def fetch_new_replies(
    instantly,
    since_cursor: Optional[Dict[str, Any]],
    campaign_filter: Iterable[str],
    seen: Dict[str, str],
    max_pages: int = 20,
    limit: int = PAGE_LIMIT,
    max_items: Optional[int] = None,
    start_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Newest-first pages until the last-seen email id (or its timestamp) is reached.

    ``start_at`` (settings.poller_start_at): GET /emails?email_type=received
    answers newest first (checked against fixtures/instantly_replies_2026-09.json,
    44 rows in strictly descending timestamp_created), so the first row older
    than it means every row after it is older too. That row and the rest of
    its page go to ``before_start`` (never to ``items``: nothing classifies
    them) and no further page is read. The scan then counts as complete, not
    truncated, so the cursor moves to the newest row as usual. None: the scan
    is exactly what it was before the start date existed."""
    wanted = set(campaign_filter)
    last_id = (since_cursor or {}).get("last_email_id")
    last_ts = (since_cursor or {}).get("last_timestamp")
    starting_after = None
    fetched = 0
    pages = 0
    new_items = []  # type: List[Dict[str, Any]]
    # Cursor pagination keys off the last id of a page: when that id occurs
    # twice the next page starts with it again. The echo is an artifact of our
    # own cursor, so it is not counted; a genuinely repeated row is counted
    # once as data but processed once.
    seen_this_run = set()
    stop = False
    truncated = False   # the scan was cut short, so older replies are still unread
    more_pages = False
    newest_seen = None  # type: Optional[Dict[str, Any]]
    before_start = []  # type: List[Dict[str, Any]]
    past_start = False  # a row older than start_at was reached: everything after it is older
    while pages < max_pages and not stop:
        page = instantly.list_emails(email_type="received", limit=limit, starting_after=starting_after)
        items = page.get("items", []) if isinstance(page, dict) else list(page)
        pages += 1
        for item in items:
            eid = str(item.get("id"))
            if starting_after and eid == starting_after:
                continue  # the cursor row echoed back by the API, not a row of data
            if newest_seen is None:
                # pages arrive newest-first, so the first genuine row of page 1
                # is the high-water mark - whether or not we end up processing it
                newest_seen = {"last_email_id": eid, "last_timestamp": str(item.get("timestamp_created") or "")}
            fetched += 1
            ts = str(item.get("timestamp_created") or "")
            if last_id and eid == last_id:
                stop = True
                break
            if last_ts and ts and ts < last_ts:
                stop = True
                break
            if past_start or _before_start(ts, start_at):
                # Older than the start date: recorded, never classified. The
                # rest of this page is older still and is taken the same way
                # (it is already fetched, so it costs nothing); no next page.
                past_start = True
                stop = True
                if eid in seen or eid in seen_this_run:
                    continue
                seen_this_run.add(eid)
                if wanted and item.get("campaign_id") not in wanted:
                    continue
                before_start.append(item)
                continue
            if eid in seen or eid in seen_this_run:
                continue
            seen_this_run.add(eid)
            if wanted and item.get("campaign_id") not in wanted:
                continue
            new_items.append(item)
            if max_items and len(new_items) >= max_items:
                stop = True
                truncated = True
                break
        cursor = page.get("next_starting_after") if isinstance(page, dict) else None
        if not cursor or not items:
            more_pages = False
            break
        more_pages = True
        starting_after = cursor
    if not stop and more_pages and pages >= max_pages:
        truncated = True
    return {"items": new_items, "fetched": fetched, "pages": pages, "truncated": truncated, "newest_seen": newest_seen,
            "before_start": before_start, "reached_start": past_start}


def _lookup_leads(instantly, items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Read-only POST /leads/list per campaign for first_name / company (best effort)."""
    out = {}  # type: Dict[str, Dict[str, Any]]
    by_campaign = {}  # type: Dict[str, List[str]]
    for it in items:
        email = (it.get("lead") or it.get("from_address_email") or "").lower()
        if email:
            by_campaign.setdefault(it.get("campaign_id"), []).append(email)
    for cid, emails in by_campaign.items():
        try:
            page = instantly.list_leads(campaign=cid, contacts=sorted(set(emails)), limit=100)
            for lead in page.get("items", []) if isinstance(page, dict) else []:
                em = (lead.get("email") or "").lower()
                if em:
                    out[em] = lead
        except Exception as exc:  # noqa: BLE001
            logger.warning("lead lookup failed for campaign %s: %s", cid, exc)
    return out


def build_deps():
    """Wire the production collaborators. Used by run_once() when it is called
    with no arguments (the Modal ``poller`` tick does exactly that) so the
    scheduled job does not need to know how the clients are built."""
    from shared.ghl import GHL
    from shared.instantly import default_client
    from shared.store import get_store

    from services.reply_engine import app as app_mod

    # llm.is_fake(), not LLM_FAKE == "1": shared.llm accepts 1/true/yes/on, so
    # LLM_FAKE=true turned fake mode on and left the offline stand-ins
    # uninstalled, and shared.llm's generic default answers
    # positive_interested 0.95 to every reply.
    if llm.is_fake():
        from services.reply_engine.classify import ensure_offline_fakes

        ensure_offline_fakes()
    store = get_store()
    instantly = default_client()
    app_mod.configure(store=store, ghl=GHL(), instantly=instantly)
    return instantly, store


PENDING_ALERT_MINUTES = 30
# A send that started and never finished, or failed outright, is nobody's job
# until something says so. 'sending' means a worker died between the claim and
# Instantly, and 'send_failed' means Instantly raised: in both the reply may or
# may not have reached the lead (an ambiguous send, a timeout after Instantly
# accepted it). Only 'stale_slots' is certain: the send was refused before it
# started, so the lead has had no answer. None of the three is in
# SENDABLE_STATUSES, so nothing retries them, and pending_approvals only ever
# looked at status == 'pending'.
STUCK_STATUSES = ("sending", "send_failed", "stale_slots")
STUCK_ALERT_MINUTES = 5


def stuck_why(status: Optional[str]) -> str:
    """What a stuck card means, said only as far as the status proves it.
    "No answer" is true of stale_slots alone: sending and send_failed may
    have reached the lead."""
    if status == "send_failed":
        return ("stuck at send_failed; the send failed or may not have gone out. Check the thread in Instantly "
                "before you press Retry")
    if status == "sending":
        return ("stuck at sending; a send started and never finished, so it may or may not have gone out. Check "
                "the thread in Instantly before you press Retry")
    if status == "stale_slots":
        return ("stuck at stale_slots; the reply was held back because the times it offered had passed, so the "
                "lead has had no answer. Press Retry, then Edit it to offer new times")
    return "stuck at %s; nothing is chasing it" % status
# A lead holding any of these has a card that is live or that Lorenzo decided,
# so a superseded card beside it is exactly what supersede_pending is for.
# "sent_manually" is a send_failed card whose reply did go out, closed with
# Mark sent (approval.mark_sent_manually): as settled as "sent", and never
# pushed (pending_approvals does not list it).
SETTLED_STATUSES = ("pending", "approved_queued", "sending", "sent", "sent_manually", "vetoed", "expired",
                    "blocked", "send_failed", "stale_slots")
# The "Replies with no owner" push is recorded here, one record per approval
# id (re-review r3 item 1): it used to go out once, through an add_once set,
# unrecorded. An owner card in send_failed never expires, so this push is the
# only thing that says its call is still held. A record carries the episode it
# belongs to (status plus the time the card entered it), so a card that leaves
# the stuck list and comes back later starts again at attempt 1. Records of
# cards no longer stuck are forgotten after STUCK_PUSH_FORGET_DAYS.
#
# How often (S-rest round 4, defect 2: one send_failed card whose pushes were
# all delivered got 26 pushes in 24 hours, 21 of them urgent, 8 at night):
#   * until a push about the card has been delivered, the fast ladder
#     (_stuck_retry_wait: 5, 15, 30, 60, 120 minutes, then hourly), at any
#     hour, urgent and titled UNANSWERED from approval.EXPIRY_PUSH_MAX_ATTEMPTS;
#   * once one has been delivered Lorenzo knows, so the card is only reminded:
#     at most once per business day, inside sending hours (slots.is_send_time,
#     07:00-19:00 CT Mon-Fri), at high priority, never urgent, never at night
#     or at a weekend. A reminder that is not delivered is retried with the
#     ladder's spacing, still only inside sending hours and still high.
STUCK_PUSH_KEY = "poller:stuck_push"
STUCK_PUSH_FORGET_DAYS = 14
# ntfy shows at most three buttons on one push.
STUCK_PUSH_MAX_ACTIONS = 3
# What the push says when it carries a Mark sent button: for a send_failed
# card, or a sending one whose send claim is past
# approval.SEND_CLAIM_LEASE_MINUTES (approval.mark_sent_url; the page behind
# it moves the card to sent_manually).
MARK_SENT_LINE = "If the reply did go out, press Mark sent. That stops these reminders and keeps the call."


def _deferred(raw: Dict[str, Any]) -> bool:
    """A card whose push waits on its template auto-send (CT3,
    approval.create_approval): it has not been pushed yet."""
    result = raw.get("notify_result") or {}
    return isinstance(result, dict) and bool(result.get("deferred"))


def _pushed(raw: Dict[str, Any]) -> bool:
    result = raw.get("notify_result") or {}
    if _deferred(raw):
        return False
    return bool((result.get("sent") or result.get("test") or result.get("shadow")) and result.get("actionable", True))


# What the digest says of a pending card whose deferred push never went out.
DEFERRED_WHY = ("its template auto-send did not finish and its card was never pushed "
                "(approval.push_orphaned_deferred should have sent it)")


def _superseded_without_successor(store, rows: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A lead whose newest card is 'superseded' and has nothing in its place.

    supersede_pending used to run before classification and unconditionally, so
    an out-of-office arriving after a positive reply retired the positive card
    and put nothing behind it. That is fixed upstream; this is the detector, so
    the same shape can never sit silently again.
    """
    by_lead = {}  # type: Dict[str, List[Dict[str, Any]]]
    for key, raw in rows.items():
        lead = raw.get("lead_email")
        if lead:
            by_lead.setdefault(lead, []).append(dict(raw, _key=key))
    out = []  # type: List[Dict[str, Any]]
    for lead, cards in by_lead.items():
        # created_at is identical for every card a single tick raises, so sorting
        # by it cannot say which is newest. Ask the question that actually
        # matters instead: does this lead have ANY card that is live or that
        # Lorenzo decided?
        if any(c.get("status") in SETTLED_STATUSES for c in cards):
            continue
        orphans = [c for c in cards if c.get("status") == "superseded"]
        if not orphans:
            continue
        newest = orphans[-1]
        out.append({"approval": str(newest.get("_key", "")).split(":", 1)[-1], "lead": lead,
                    "created_at": newest.get("created_at"), "pushed": _pushed(newest),
                    "why": "superseded with no card in its place"})
    return out


def _expired_holding_call(store, key: str, raw: Dict[str, Any], approval_mod) -> Optional[Dict[str, Any]]:
    """The stuck-card row for an expired card that still owns the lead's
    unconfirmed call with the Keep / Release choice undecided, else None.
    Only cards carrying an unsettled expiry push record are read further (a
    card that expired holding no call, or whose question was settled, costs
    nothing per tick).

    The row is listed (the approvals_waiting row, the CLI table) but carries
    ``chased_by: expiry_push``, so _push_stuck never pushes it: the card's own
    Keep / Release push (notify_result.expiry_push, read here and never
    written) is re-sent by approval until it is delivered and then stops by
    design. The stuck push repeated the same question without the Keep /
    Release links (S-rest round 4, P17)."""
    rec = approval_mod.expiry_push_record(raw)
    if not rec or rec.get("settled"):
        return None
    try:
        card = approval_mod.Approval.model_validate(raw)
        lead_raw = store.get(card.state_key)
        state = approval_mod.LeadState.from_store(lead_raw) if lead_raw else None
    except Exception as exc:  # noqa: BLE001 - one bad row must not stop the detector
        logger.warning("could not read the lead behind expired card %s: %s", key, exc)
        return None
    if state is None or not approval_mod.owns_booking(card, state) or approval_mod.cancel_pending(state):
        return None
    booking = approval_mod.booking_of(state)
    delivered = bool(rec.get("delivered"))
    why = "expired holding the call at %s; Keep or Release not chosen" % approval_mod._slot_label(booking.get("slot"))
    if not delivered:
        why += "; the Keep / Release push was NOT delivered (%d attempt(s))" % int(rec.get("attempts") or 0)
    return {"approval": key.split(":", 1)[-1], "lead": raw.get("lead_email"), "created_at": raw.get("created_at"),
            "pushed": delivered, "why": why, "status": "expired", "appointment_id": booking.get("appointment_id"),
            "chased_by": "expiry_push"}


def pending_approvals(store, now: datetime, older_than_minutes: int = PENDING_ALERT_MINUTES) -> List[Dict[str, Any]]:
    """Approval cards that need Lorenzo and are not moving.

    Three shapes, not one:
      * ``pending`` older than ``older_than_minutes`` - he has not tapped it.
        shared.notify.notify() swallows its own ntfy/SMTP failures and returns
        sent=False, so an unreachable ntfy or an unsubscribed topic left a
        positive reply sitting in the store with nothing on his phone. A
        pending card whose push was deferred to its template auto-send
        (notify_result.deferred, CT3) has never been pushed: ``pushed`` is
        False, and it carries ``status`` "pending" and ``deferred`` so
        _push_stuck pushes it like a stuck card.
      * ``sending`` / ``send_failed`` / ``stale_slots`` older than
        STUCK_ALERT_MINUTES - a send that no longer has an owner. Nothing
        retries these and the only other trace is a Job_Log CSV row. A
        ``sending`` card is judged by its send claim instead, once that is
        readable and its own attempt (_send_started_at): listed when the
        claim is approval.SEND_CLAIM_LEASE_MINUTES old, the lease after which
        nothing can still be running the send and Mark sent may take it, so
        its push can carry the button. Before that its send may be under way
        (a card approved hours ago and sent from the queue now), and it is
        not listed.
      * a lead whose newest card is ``superseded`` with no successor.
      * ``expired`` while it still owns the lead's unconfirmed call and the
        Keep / Release choice is undecided (re-review R1 item 1), older than
        STUCK_ALERT_MINUTES: the call stays held until Lorenzo chooses, and
        ``pushed`` says whether the Keep / Release push was delivered. Listed
        only: ``chased_by`` says its own push chases it, so _push_stuck
        leaves it alone.

    A card Lorenzo closed with Mark sent (``sent_manually``) is done, like
    ``sent``, and is never listed.
    """
    from datetime import timedelta

    from services.reply_engine import approval as approval_mod

    out = []  # type: List[Dict[str, Any]]
    cutoff = now - timedelta(minutes=older_than_minutes)
    stuck_cutoff = now - timedelta(minutes=STUCK_ALERT_MINUTES)
    try:
        keys = store.keys(approval_mod.APPROVAL_PREFIX)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not list approvals: %s", exc)
        return out
    rows = {}  # type: Dict[str, Dict[str, Any]]
    for key in keys:
        raw = store.get(key)
        if not raw:
            continue
        rows[key] = raw
        status = raw.get("status")
        stamp = raw.get("decided_at") if status in STUCK_STATUSES else raw.get("created_at")
        try:
            at = slots.parse_iso(stamp or raw.get("created_at"))
        except (ValueError, TypeError):
            continue
        if status == "pending":
            if at > cutoff:
                continue
            if _deferred(raw):
                # Never pushed: nothing is on his phone, so it is listed like
                # a stuck card and _push_stuck tells him (CT3).
                out.append({"approval": key.split(":", 1)[-1], "lead": raw.get("lead_email"),
                            "created_at": raw.get("created_at"), "pushed": False, "deferred": True,
                            "why": DEFERRED_WHY, "status": "pending", "since": raw.get("created_at")})
                continue
            out.append({"approval": key.split(":", 1)[-1], "lead": raw.get("lead_email"), "created_at": raw.get("created_at"),
                        "pushed": _pushed(raw), "why": "waiting on you"})
        elif status in STUCK_STATUSES:
            started = _send_started_at(store, key.split(":", 1)[-1], raw, approval_mod) if status == "sending" else None
            if started is not None:
                if started > now - timedelta(minutes=approval_mod.SEND_CLAIM_LEASE_MINUTES):
                    continue    # its send may still be running
            elif at > stuck_cutoff:
                continue
            out.append({"approval": key.split(":", 1)[-1], "lead": raw.get("lead_email"), "created_at": raw.get("created_at"),
                        "pushed": _pushed(raw), "why": stuck_why(status), "status": status,
                        "since": stamp or raw.get("created_at")})
        elif status == "expired":
            held = _expired_holding_call(store, key, raw, approval_mod)
            if held is None:
                continue
            try:
                expired_at = slots.parse_iso(raw.get("decided_at") or raw.get("expires_at"))
            except (ValueError, TypeError):
                expired_at = None
            if expired_at is not None and expired_at > stuck_cutoff:
                continue
            out.append(held)
    out.extend(_superseded_without_successor(store, rows))
    return out


def _send_started_at(store, approval_id: str, raw: Dict[str, Any], approval_mod) -> Optional[datetime]:
    """When the send of a ``sending`` card started: its send claim's time
    (approval.send_claim_record), when the claim is readable, is the card's
    own send attempt and has a readable time. Otherwise None, and the card
    is judged as before (decided_at and STUCK_ALERT_MINUTES)."""
    try:
        claim = approval_mod.send_claim_record(store, approval_id)
    except Exception as exc:  # noqa: BLE001 - unreadable: the old rule lists it
        logger.warning("could not read the send claim of card %s: %s", approval_id, exc)
        return None
    attempt = raw.get("send_attempt")
    if not claim or not attempt or str(claim.get("attempt") or "") != str(attempt):
        return None
    try:
        return slots.parse_iso(str(claim.get("at")))
    except (ValueError, TypeError):
        return None


def _merge_seen(store, seen: Dict[str, str]) -> None:
    def merge(current):
        merged = dict(current) if isinstance(current, dict) else {}
        merged.update(seen)
        if len(merged) > SEEN_MAX:
            merged = dict(sorted(merged.items(), key=lambda kv: kv[1])[-SEEN_MAX:])
        return merged

    mutate = getattr(store, "mutate", None)
    if callable(mutate):
        mutate(SEEN_KEY, merge, {})
    else:
        store.set(SEEN_KEY, seen)


def _merge_failed(store, failed: Dict[str, Any], attempted: set) -> None:
    """This run is authoritative only for the ids it actually attempted: those
    rows are replaced (a success drops the row, a failure bumps its attempt
    count). Anything another worker recorded is left alone."""
    def merge(current):
        merged = {k: v for k, v in (current or {}).items() if k not in attempted} if isinstance(current, dict) else {}
        merged.update(failed)
        return merged

    mutate = getattr(store, "mutate", None)
    if callable(mutate):
        mutate(FAILED_KEY, merge, {})
    else:
        store.set(FAILED_KEY, failed)


def _stuck_episode(w: Dict[str, Any]) -> str:
    return "%s|%s" % (w.get("status") or "superseded", w.get("since") or w.get("created_at") or "")


def _stuck_retry_wait(attempts: int) -> int:
    """Minutes before the next push after ``attempts`` undelivered pushes in a
    row: the expired-card schedule (approval.EXPIRY_PUSH_RETRY_MINUTES,
    5/15/30/60/120), then hourly from approval.EXPIRY_PUSH_MAX_ATTEMPTS on."""
    from services.reply_engine import approval as approval_mod

    if attempts >= approval_mod.EXPIRY_PUSH_MAX_ATTEMPTS:
        return approval_mod.EXPIRY_PUSH_ESCALATED_RETRY_MINUTES
    ladder = approval_mod.EXPIRY_PUSH_RETRY_MINUTES
    return ladder[min(max(attempts, 1), len(ladder)) - 1]


def _reminder_mode(rec: Optional[Dict[str, Any]]) -> bool:
    """Has a push about this episode of the card reached Lorenzo? From then
    on the card is only reminded (once a business day, inside sending
    hours, high priority), never chased on the fast ladder."""
    try:
        return int((rec or {}).get("delivered") or 0) > 0
    except (TypeError, ValueError):
        return False


def _ct_date(stamp: Any):
    """The CT calendar date of an ISO stamp, or None."""
    try:
        return slots.to_tz(slots.parse_iso(str(stamp))).date()
    except Exception:  # noqa: BLE001 - a missing or unreadable stamp is simply no date
        return None


def _next_reminder_at(ts: datetime) -> datetime:
    """When a card whose push was delivered at ``ts`` may be reminded: the
    opening of sending hours (07:00 CT) on the first business day after
    ``ts``'s own CT day. approval._next_window_open is the send queue's rule
    for the next opening (re-localised per day, weekends skipped)."""
    from services.reply_engine import approval as approval_mod

    local = slots.to_tz(ts)
    nxt = approval_mod._next_window_open(local)
    if nxt.date() == local.date():   # delivered before 07:00 on a business day: not that same day
        nxt = approval_mod._next_window_open(nxt)
    return nxt


def _inside_send_hours(at: datetime) -> datetime:
    """``at`` when it falls inside sending hours on a business day
    (slots.is_send_time), else the next opening after it."""
    from services.reply_engine import approval as approval_mod

    if slots.is_send_time(at):
        return at
    return approval_mod._next_window_open(slots.to_tz(at))


def _edit_stuck_records(store, fn) -> None:
    """Apply ``fn(records) -> records`` to the stuck-push records under the
    store's lock (get/set on a store without ``mutate``)."""
    def _apply(current):
        return fn(dict(current) if isinstance(current, dict) else {})

    mutate = getattr(store, "mutate", None)
    if callable(mutate):
        try:
            mutate(STUCK_PUSH_KEY, _apply, {})
            return
        except NotImplementedError:
            pass
    store.set(STUCK_PUSH_KEY, _apply(store.get(STUCK_PUSH_KEY)))


def _claim_stuck_pushes(store, orphans: List[Dict[str, Any]], ts: datetime) -> List[Dict[str, Any]]:
    """Take the next push for every orphan that is due one. Each taken record
    is leased for approval.EXPIRY_PUSH_LEASE_MINUTES, so an overlapping tick
    finds nothing due; a worker killed mid-push is retried after the lease.

    A card Lorenzo has had a delivered push about (_reminder_mode) is due only
    inside sending hours on a business day, and never on a CT day that
    already had a delivered push about it, whatever next_at says: that is the
    gate a lease expiring at night, or a record written by older code, meets
    too. Returns ``[{"row", "attempt", "errors", "reminder"}]``."""
    from datetime import timedelta

    from services.reply_engine import approval as approval_mod

    lease = timedelta(minutes=approval_mod.EXPIRY_PUSH_LEASE_MINUTES)
    forget = ts - timedelta(days=STUCK_PUSH_FORGET_DAYS)
    wanted = {}  # type: Dict[str, Dict[str, Any]]
    for w in orphans:
        if w.get("approval"):
            wanted[str(w["approval"])] = w
    box = {"due": []}  # type: Dict[str, Any]

    def _claim(recs):
        box["due"] = []
        for approval_id in list(recs):
            if approval_id in wanted:
                continue
            rec = recs[approval_id]
            try:
                stale = slots.parse_iso((rec or {}).get("last_at")) < forget
            except (ValueError, TypeError, AttributeError):
                stale = True
            if stale:
                del recs[approval_id]
        for approval_id, w in wanted.items():
            episode = _stuck_episode(w)
            rec = recs.get(approval_id)
            if not isinstance(rec, dict) or rec.get("episode") != episode:
                rec = {"episode": episode, "status": w.get("status") or "superseded", "lead": w.get("lead"),
                       "first_at": ts.isoformat(), "attempts": 0, "delivered": 0, "failed_streak": 0, "errors": [],
                       "next_at": None}
            else:
                rec = dict(rec)
            reminder = _reminder_mode(rec)
            try:
                due = rec.get("next_at") is None or slots.parse_iso(rec.get("next_at")) <= ts
            except (ValueError, TypeError):
                due = True
            if due and reminder and (not slots.is_send_time(ts)
                                     or _ct_date(rec.get("delivered_at")) == slots.to_tz(ts).date()):
                due = False   # he knows: never at night or at a weekend, at most once per business day
            if due:
                rec["attempts"] = int(rec.get("attempts") or 0) + 1
                rec["last_at"] = ts.isoformat()
                rec["next_at"] = (ts + lease).isoformat()
                box["due"].append({"row": w, "attempt": rec["attempts"], "errors": list(rec.get("errors") or []),
                                   "reminder": reminder})
            recs[approval_id] = rec
        return recs

    _edit_stuck_records(store, _claim)
    return list(box["due"])


def _finish_stuck_pushes(store, due: List[Dict[str, Any]], result: Dict[str, Any], delivered: bool,
                         ts: datetime) -> None:
    """Record what the push did on every record it carried. The card is still
    stuck and nothing else will chase it, so a next push is always scheduled:

    * delivered: the next business day's opening of sending hours
      (_next_reminder_at), whatever the ladder had reached;
    * not delivered, before any push about the card was delivered: the fast
      ladder, at any hour (_stuck_retry_wait over the attempt number);
    * not delivered, a reminder: the ladder's spacing over the reminders
      missed in a row (``failed_streak``), moved into sending hours."""
    from datetime import timedelta

    from services.reply_engine import approval as approval_mod

    taken = dict((str(d["row"].get("approval")), (d["attempt"], bool(d.get("reminder")))) for d in due)

    def _done(recs):
        for approval_id, (attempt, reminder) in taken.items():
            rec = recs.get(approval_id)
            if not isinstance(rec, dict) or int(rec.get("attempts") or 0) != attempt:
                continue  # a later attempt owns the record now
            rec = dict(rec)
            rec["last_result"] = approval_mod.stored_notify_result(result)
            rec["last_delivered"] = delivered
            # Whether THIS push was the urgent UNANSWERED one: never a reminder.
            rec["escalated"] = not reminder and attempt >= approval_mod.EXPIRY_PUSH_MAX_ATTEMPTS
            if delivered:
                rec["delivered"] = int(rec.get("delivered") or 0) + 1
                rec["delivered_at"] = ts.isoformat()
                rec["failed_streak"] = 0
                rec["next_at"] = _next_reminder_at(ts).isoformat()
            else:
                errors = list(rec.get("errors") or [])
                errors.append("attempt %d: %s" % (attempt, "; ".join((result or {}).get("errors") or [])
                                                   or "not delivered"))
                rec["errors"] = errors[-approval_mod.EXPIRY_PUSH_MAX_ATTEMPTS:]
                if reminder:
                    streak = int(rec.get("failed_streak") or 0) + 1
                    retry_at = _inside_send_hours(ts + timedelta(minutes=_stuck_retry_wait(streak)))
                else:
                    streak = attempt   # nothing about this card has been delivered yet
                    retry_at = ts + timedelta(minutes=_stuck_retry_wait(attempt))
                rec["failed_streak"] = streak
                rec["next_at"] = retry_at.isoformat()
            recs[approval_id] = rec
        return recs

    _edit_stuck_records(store, _done)


def _accepts(build, name: str) -> bool:
    """Does this mark_sent_url take the keyword ``name``? Read from its
    signature; False when the signature cannot be read."""
    import inspect

    try:
        return name in inspect.signature(build).parameters
    except (TypeError, ValueError):
        return False


def _accepts_store(build) -> bool:
    return _accepts(build, "store")


def _call_mark_sent_url(build, card, store, now=None):
    """approval.mark_sent_url(card, store=store, now=now): with the store, a
    card escalated before the hold was recorded on the card itself (its hold
    is only in its own approval_recipient_hold row) is recognised too, and a
    sending card's send claim is read; ``now`` is the tick's clock, which
    the claim's age is judged by, passed only to a builder that takes it. An
    older mark_sent_url(card) answers the keyword with a TypeError and is
    called with the card alone. A TypeError from a builder that does take
    ``store`` is its own failure, not the old signature: it is raised, and
    the push goes out without the button."""
    kwargs = {"store": store}  # type: Dict[str, Any]
    if now is not None and _accepts(build, "now"):
        kwargs["now"] = now
    try:
        return build(card, **kwargs)
    except TypeError:
        if _accepts_store(build):
            raise
        return build(card)


def _mark_sent_link(store, approval_id: str, build, held, now=None) -> Tuple[Optional[str], bool]:
    """``(url, recipient_held)`` for a card in the stuck push.

    The button is approval.mark_sent_url(card, store=store, now=now) for a
    card that is send_failed or sending right now (approval.MARK_SENT_FROM);
    with the store it refuses a card held because its recipient could not
    be confirmed, wherever the hold is recorded, and a sending card whose
    send claim is not yet approval.SEND_CLAIM_LEASE_MINUTES old at ``now``
    (or is missing or unreadable). A sending card gets a button only from a
    builder that takes ``now``: one that does not cannot judge the claim.
    approval.recipient_held then says whether a hold is why there is no
    link, and is a second guard: a held card never gets the button (the
    orchestrator's round-4 decision, fail closed).

    * ``(None, True)``: held for its recipient. Mark sent is never offered.
    * ``(url, False)``: the button.
    * ``(None, False)``: no builder, the card moved on or cannot be read, its
      recipient hold cannot be read, or the builder answered None or raised.

    The card is re-read here and never put on the pending_approvals row,
    which the tick writes to the Job_Log: a signed link must not end up in a
    CSV."""
    from services.reply_engine import approval as approval_mod

    try:
        raw = store.get(approval_mod.APPROVAL_PREFIX + approval_id)
        if not isinstance(raw, dict) or raw.get("status") not in _mark_sent_from(approval_mod):
            return None, False
        card = approval_mod.Approval.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 - a push without the button beats no push
        logger.warning("no Mark sent link for card %s: %s", approval_id, exc)
        return None, False
    url = None
    if callable(build) and (raw.get("status") != "sending" or _accepts(build, "now")):
        try:
            url = _call_mark_sent_url(build, card, store, now)
        except Exception as exc:  # noqa: BLE001 - a push without the button beats no push
            logger.warning("no Mark sent link for card %s: %s", approval_id, exc)
            url = None
    if callable(held):
        try:
            if held(card, store):
                return None, True
        except Exception as exc:  # noqa: BLE001 - unknown: no button (mark_sent_url refuses it too)
            logger.warning("no Mark sent link for card %s: its recipient hold could not be read: %s",
                           approval_id, exc)
            return None, False
    return (str(url) if url else None), False


def _mark_sent_from(approval_mod) -> Tuple[str, ...]:
    """The statuses Mark sent takes (approval.MARK_SENT_FROM); send_failed
    alone beside an approval module without it."""
    return tuple(getattr(approval_mod, "MARK_SENT_FROM", ("send_failed",)))


def _mark_sent_actions(store, due: List[Dict[str, Any]], now=None):
    """``(buttons, unlinked, held)`` for the cards in ``due`` Mark sent may
    take (send_failed, and sending: approval.MARK_SENT_FROM): the Mark sent
    buttons, the leads of the cards left without one, and the leads of the
    cards held because their recipient could not be confirmed (never
    offered Mark sent; their line says what to do instead). ``now`` is the
    tick's clock, for a sending card's claim.

    approval.mark_sent_url and approval.recipient_held are looked up with
    getattr, so a poller running beside an approval module without them still
    pushes. ntfy shows at most STUCK_PUSH_MAX_ACTIONS buttons; with more than
    one card each button names its lead."""
    from services.reply_engine import approval as approval_mod

    takes = _mark_sent_from(approval_mod)
    failed = [d["row"] for d in due if d["row"].get("status") in takes and d["row"].get("approval")]
    if not failed:
        return [], [], []
    build = getattr(approval_mod, "mark_sent_url", None)
    held_fn = getattr(approval_mod, "recipient_held", None)
    links = []  # type: List[Any]
    unlinked = []  # type: List[str]
    held = []  # type: List[str]
    for w in failed:
        url, is_held = _mark_sent_link(store, str(w["approval"]), build, held_fn, now)
        if is_held:
            held.append(str(w.get("lead")))
        elif url and len(links) < STUCK_PUSH_MAX_ACTIONS:
            links.append((w.get("lead"), url))
        else:
            unlinked.append(str(w.get("lead")))
    if len(links) == 1:
        return [("Mark sent", links[0][1])], unlinked, held
    return [("Mark sent %s" % lead, url) for lead, url in links], unlinked, held


def _topic_protected() -> bool:
    """shared.notify's own test for a topic that may carry links; False
    when it cannot be read (the public text goes out)."""
    from shared import notify

    try:
        return bool(notify.topic_is_protected())
    except Exception:  # noqa: BLE001
        return False


def _card_link_lines(store, w: Dict[str, Any], now: datetime) -> Optional[List[str]]:
    """The signed links under a stuck card's line (approval.recovery_links,
    on the card as stored now): Retry and Veto where each takes it, and for
    stale_slots the Edit link its line asks for (it works once Retry has put
    the card back to pending). ``[]`` for a row that is not a stuck card
    (superseded, a deferred card) or a card that moved on; None when the
    links could not be built (BASE_URL unset in live, an unreadable card):
    the push then says so. Never raises."""
    from services.reply_engine import approval as approval_mod

    if w.get("status") not in STUCK_STATUSES or not w.get("approval"):
        return []
    build = getattr(approval_mod, "recovery_links", None)
    if not callable(build):
        return []
    try:
        raw = store.get(approval_mod.APPROVAL_PREFIX + str(w["approval"]))
        if not isinstance(raw, dict) or raw.get("status") != w.get("status"):
            return []
        links = build(raw, store, now, mark_sent=False)
    except Exception as exc:  # noqa: BLE001 - the push goes out, and says it has no links
        logger.warning("no Retry / Veto links for card %s: %s", w.get("approval"), exc)
        return None
    out = []  # type: List[str]
    if links.get("retry"):
        out.append("  Retry: %s" % links["retry"])
    if links.get("veto"):
        out.append("  Veto: %s" % links["veto"])
    edit = links.get("edit") or links.get("edit_after_retry")
    if w.get("status") == "stale_slots" and edit:
        out.append("  Edit%s: %s" % (" (after Retry)" if links.get("edit_after_retry") else "", edit))
    return out


def _send_stuck_push(store, due: List[Dict[str, Any]], ts: datetime, reminder: bool) -> None:
    """One "Replies with no owner" push for ``due``, recorded on each card's
    record. ``reminder``: every card in it has had a delivered push already,
    so the push is high priority, titled "(reminder)", never UNANSWERED.
    Otherwise it is the fast ladder's push: "(attempt N)", and urgent and
    UNANSWERED from approval.EXPIRY_PUSH_MAX_ATTEMPTS. Never raises."""
    from services.reply_engine import approval as approval_mod
    from shared import notify

    attempts = [d["attempt"] for d in due if d["attempt"]]
    top = max(attempts) if attempts else 1
    escalated = not reminder and top >= approval_mod.EXPIRY_PUSH_MAX_ATTEMPTS
    title = "Replies with no owner: %d" % len(due)
    if reminder:
        title = "%s (reminder)" % title
    elif escalated:
        title = "UNANSWERED (attempt %d): %s" % (top, title)
    elif top > 1:
        title = "%s (attempt %d)" % (title, top)
    lines = []  # type: List[str]
    linked = []  # type: List[str]
    no_links = []  # type: List[str]
    for d in due[:10]:
        w = d["row"]
        line = "%s: %s" % (w.get("lead"), w.get("why"))
        if not reminder and d["attempt"] and d["attempt"] > 1:
            line += " (push %d)" % d["attempt"]
        lines.append(line)
        linked.append(line)
        links = _card_link_lines(store, w, ts)
        if links is None:
            no_links.append(str(w.get("lead")))
        else:
            linked.extend(links)
    if len(due) > 10:
        lines.append("...and %d more" % (len(due) - 10))
        linked.append(lines[-1])
    body = ["These cards are stuck and nothing else will chase them."] + lines
    try:
        actions, unlinked, held = _mark_sent_actions(store, due, ts)
    except Exception as exc:  # noqa: BLE001 - the push goes out with or without the button
        logger.warning("could not build the Mark sent buttons: %s", exc)
        actions, unlinked, held = [], [], []
    if actions:
        body.append(MARK_SENT_LINE)
    if held:
        body.append("No Mark sent for %s: held because the recipient could not be confirmed. Veto %s, or check "
                    "the thread in Instantly." % (", ".join(held), "it" if len(held) == 1 else "them"))
    if unlinked:
        body.append("This push has no Mark sent button for %s. If that reply did go out, do not press Retry or Veto; "
                    "see the runbook reply_engine_alerts.md, Replies with no owner." % ", ".join(unlinked))
    if reminder:
        body.append("You have had a push about these already. While a card stays stuck, this reminder comes once a "
                    "business day, inside sending hours (07:00-19:00 CT, Mon-Fri).")
    elif top > 1:
        body.append("Earlier pushes were not delivered. Until one is, this repeats 5, 15, 30, 60 and 120 minutes "
                    "apart, then hourly; after that, once a business day.")
        failed = [e for d in due for e in (d["errors"] or [])][-3:]
        if failed:
            body.append("Earlier pushes not delivered: %s" % "; ".join(failed))
    if no_links:
        body.append("This push carries no Retry or Veto link for %s (BASE_URL is unset, or the card could not be "
                    "read); open the card from its own push, or reply by hand from the Instantly inbox."
                    % ", ".join(no_links))
    kwargs = {"priority": "urgent" if escalated else "high", "tags": ["warning", "reply-engine"]}  # type: Dict[str, Any]
    if actions:
        kwargs["actions"] = actions   # never a click: a tap on the push must not open Mark sent
    # The Retry / Veto links sit under each card's line, in the email leg and
    # on a protected topic only: the public topic gets the lines without them
    # (shared.notify redacts the addresses there and says the details are in
    # the email). Never on the pending_approvals row, which reaches the CSV.
    message = "\n".join(body)
    with_links = "\n".join([body[0]] + linked + body[1 + len(lines):])
    if with_links != message:
        if _topic_protected():
            message = with_links
        else:
            kwargs["email_message"] = with_links
            message += "\nThe Retry and Veto links for each card are in the email."
    try:
        result = notify.notify(title, message, **kwargs)
    except Exception as exc:  # noqa: BLE001 - the tick must not fail on a push
        result = {"sent": False, "errors": ["notify raised: %s" % exc]}
    delivered = isinstance(result, dict) and bool(result.get("sent") or result.get("test") or result.get("shadow"))
    recorded = [d for d in due if d["attempt"]]
    if recorded:
        try:
            _finish_stuck_pushes(store, recorded, result, delivered, ts)
        except Exception as exc:  # noqa: BLE001
            logger.error("could not record the stuck-approval push: %s", exc)
    if not delivered:
        logger.error("the stuck-approval %s (%d card(s), attempt %d%s) was NOT delivered: %s",
                     "reminder" if reminder else "push", len(due), top, " ESCALATED" if escalated else "",
                     (result or {}).get("errors"))
        job_log.log_run("reply_engine.poller", "push_failed",
                        {"kind": "stuck_card", "approvals": [d["row"].get("approval") for d in due][:20],
                         "leads": [d["row"].get("lead") for d in due][:20], "attempt": top,
                         "escalated": escalated, "reminder": reminder, "errors": (result or {}).get("errors")})


def _push_stuck(store, waiting: List[Dict[str, Any]], now: Optional[datetime] = None) -> List[str]:
    """Tell Lorenzo about the cards nothing else will chase, and keep telling him.

    A 'pending' card he has simply not read yet is already on his phone; a card
    stuck at sending/send_failed/stale_slots, or superseded with nothing
    behind it, has no other owner. An owner card in send_failed never
    expires, so for a booked call this push is the only alert there is. An
    expired card still holding a call is listed by pending_approvals but not
    pushed here (``chased_by``): its own Keep / Release push owns it.

    Every push is recorded (STUCK_PUSH_KEY), so a restart neither repeats it
    nor forgets it. Until a push about a card has been delivered, it repeats
    5, 15, 30, 60 and 120 minutes apart, then hourly, at any hour; from
    attempt approval.EXPIRY_PUSH_MAX_ATTEMPTS on it is urgent and titled
    UNANSWERED. Once one has been delivered, the card is only reminded: at
    most once per business day, inside sending hours, at high priority. The
    two kinds go out as separate pushes, so a reminder never rides in an
    urgent one. A send_failed card, and a sending one whose send claim is
    approval.SEND_CLAIM_LEASE_MINUTES old, carries a Mark sent button
    (approval.mark_sent_url) when one can be built, never a card held because
    its recipient could not be confirmed. An undelivered push
    writes a "push_failed" Job_Log row (the deploy watch fails on it) and
    logs at ERROR. Returns the approval ids pushed this tick.
    """
    ts = slots.to_tz(now) if now is not None else datetime.now(slots.TZ)
    # A pending card with a deferred push (CT3) was never pushed, so it is
    # an orphan too; any other pending card is on his phone already.
    orphans = [w for w in waiting if not w.get("chased_by")
               and ((w.get("status") and (w.get("status") != "pending" or w.get("deferred")))
                    or str(w.get("why", "")).startswith("superseded"))]
    if not orphans:
        return []
    try:
        due = _claim_stuck_pushes(store, orphans, ts)
    except Exception as exc:  # noqa: BLE001 - unrecorded, the push still goes out (fail toward telling)
        logger.error("stuck-approval bookkeeping failed; pushing without a record: %s", exc)
        due = [{"row": w, "attempt": None, "errors": [], "reminder": False} for w in orphans]
    pushed = []  # type: List[str]
    for reminder in (False, True):
        group = [d for d in due if bool(d.get("reminder")) is reminder]
        if group:
            _send_stuck_push(store, group, ts, reminder)
            pushed.extend(d["row"].get("approval") for d in group)
    return pushed


def run_once(
    instantly=None,
    store=None,
    since_cursor: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
    campaign_filter: Optional[Iterable[str]] = None,
    process: Optional[Callable[..., Dict[str, Any]]] = None,
    max_pages: int = 20,
    lookup_leads: bool = False,
    max_items: Optional[int] = None,
    persist_cursor: bool = True,
    time_budget_s: Optional[float] = None,
    clock: Callable[[], float] = time.monotonic,
    start_at: Any = None,
) -> Dict[str, Any]:
    """One poll: fetch -> dedupe -> ReplyEvent(source='poller') -> process_event. Read-only against Instantly.

    ``start_at``: replies received before it are never passed to
    ``process`` (no classification, draft, card or model call). Each is
    marked seen and listed in ``results`` with ``skipped`` "before_start_date",
    and paging stops at the first of them (fetch_new_replies). None (the
    default) reads settings.poller_start_at(): POLLER_START_AT, else
    settings.POLLER_START_AT_DEFAULT; "off" there, or ``start_at="off"``
    here, turns it off. An unreadable value raises before anything is read.

    ``instantly`` and ``store`` default to the production clients (build_deps),
    so ``run_once()`` with no arguments is the scheduled entrypoint Modal calls.

    ``time_budget_s`` (the Modal ``poller`` passes modal_app.POLLER_TIME_BUDGET_S,
    half its 240 s timeout): once that many seconds of this run have passed, no
    NEW reply is started. The rest are left unseen and the scan counts as
    truncated, so the cursor does not move and the next run picks them up. A
    Modal timeout kills the container mid-reply and loses everything this run
    had not saved; the budget is what keeps a run from starting a reply it
    cannot finish.

    A reply ``process_event`` answers ``{'skipped': 'in_flight'}`` for (claimed
    by a run that has not finished it: another worker, or a container that was
    killed inside the claim's 15 minutes) is NOT marked seen and holds the
    cursor, so a later run processes it once the claim is done or stale.
    Marking it seen dropped it for good when the claim belonged to a killed run.
    """
    from services.reply_engine.app import process_event

    started = clock()
    # Resolved first: a bad POLLER_START_AT must stop the run before any read.
    start = settings.poller_start_at() if start_at is None else settings.parse_start_at(start_at)

    if instantly is None or store is None:
        built_instantly, built_store = build_deps()
        instantly = instantly if instantly is not None else built_instantly
        store = store if store is not None else built_store
    process = process or process_event
    ts = slots.to_tz(slots.ensure_aware(now)) if now is not None else datetime.now(slots.TZ)
    cursor = since_cursor if since_cursor is not None else (store.get(CURSOR_KEY) or {})
    seen = store.get(SEEN_KEY) or {}
    if not isinstance(seen, dict):
        seen = {}
    wanted = list(campaign_filter) if campaign_filter is not None else campaign_ids()
    fetched = fetch_new_replies(instantly, cursor, wanted, seen, max_pages=max_pages, max_items=max_items,
                                start_at=start)
    items = fetched["items"]
    mine = own_inboxes()
    items = [it for it in items if (it.get("from_address_email") or "").lower() not in mine]
    items.sort(key=lambda it: str(it.get("timestamp_created") or ""))  # oldest first
    leads = _lookup_leads(instantly, items) if (lookup_leads and items) else {}

    results = []  # type: List[Dict[str, Any]]
    failed = store.get(FAILED_KEY) or {}
    if not isinstance(failed, dict):
        failed = {}
    # Older than the start date: seen, so no later poll takes them up, and
    # never processed. One that failed on an earlier run (before the start
    # date moved past it) leaves poller:failed too, whether or not this scan
    # reached its page: it will never be retried, so it must not hold the
    # cursor for its MAX_FAILED_ATTEMPTS.
    before_start = []  # type: List[str]
    retired = set()  # type: set
    for eid, rec in list(failed.items()):
        if isinstance(rec, dict) and _before_start(str(rec.get("timestamp_created") or ""), start):
            failed.pop(eid, None)
            retired.add(eid)
    for item in fetched.get("before_start") or []:
        eid = str(item.get("id"))
        seen[eid] = str(item.get("timestamp_created") or ts.isoformat())
        if failed.pop(eid, None) is not None:
            retired.add(eid)
        before_start.append(eid)
        results.append({"email_id": eid,
                        "lead": (item.get("lead") or item.get("from_address_email") or "").lower() or None,
                        "received_at": str(item.get("timestamp_created") or ""), "skipped": BEFORE_START})
    processed = skipped = errors = 0
    attempted = set()  # type: set
    in_flight = []  # type: List[str]
    deferred = []  # type: List[str]
    for item in items:
        eid = str(item.get("id"))
        if deferred or (time_budget_s is not None and attempted and clock() - started >= float(time_budget_s)):
            # Out of time for NEW work: leave this reply (and every newer one)
            # unseen and unattempted; the cursor stays put below. The first
            # reply of a run is always taken, so a slow fetch cannot starve
            # the queue for good.
            deferred.append(eid)
            continue
        attempted.add(eid)
        try:
            event = ReplyEvent.from_poller_item(item, lead=leads.get((item.get("lead") or item.get("from_address_email") or "").lower()), source="poller")
            res = process(event, now=ts)
            if res.get("skipped") == "in_flight":
                # Claimed by a run that has not finished it. If that run was
                # killed, only a later retry (once the claim is stale) ever
                # processes it, so it is neither seen nor passed by the cursor.
                skipped += 1
                in_flight.append(eid)
                results.append({"email_id": eid, "lead": event.lead_email, "skipped": "in_flight",
                                "received_at": event.received_at.isoformat()})
                continue
            if res.get("skipped"):
                skipped += 1
            else:
                processed += 1
            results.append({"email_id": eid, "lead": event.lead_email, "campaign_key": event.campaign_key, "received_at": event.received_at.isoformat(),
                            "label": res.get("label"), "status": res.get("status"), "skipped": res.get("skipped"),
                            "actions": ["%s.%s:%s" % (a["system"], a["action"], a["kind"]) for a in res.get("actions", [])],
                            "draft": bool(res.get("draft")), "approval": bool(res.get("approval_token"))})
        except Exception as exc:  # noqa: BLE001 - one bad reply must not stop the poll
            errors += 1
            logger.exception("process failed for %s: %s", eid, exc)
            results.append({"email_id": eid, "error": str(exc)})
            # NOT marked seen: a classifier timeout or a transient store error
            # used to retire the reply here, and the cursor then moved past it,
            # so a positive reply was dropped for good and nothing said so.
            previous = failed.get(eid) if isinstance(failed.get(eid), dict) else {}
            failed[eid] = {"at": ts.isoformat(), "error": str(exc),
                           "attempts": int(previous.get("attempts") or 0) + 1,
                           "first_at": previous.get("first_at") or ts.isoformat(),
                           "timestamp_created": str(item.get("timestamp_created") or "")}
            continue
        seen[eid] = str(item.get("timestamp_created") or ts.isoformat())
        failed.pop(eid, None)

    if len(seen) > SEEN_MAX:
        keep = sorted(seen.items(), key=lambda kv: kv[1])[-SEEN_MAX:]
        seen = dict(keep)
    newest = None
    if items:
        newest = max(items, key=lambda it: str(it.get("timestamp_created") or ""))
    new_cursor = dict(cursor)
    # Only advance the cursor when the whole backlog was scanned. The cursor
    # used to jump to the newest fetched item even when --limit or the page
    # budget cut the scan short, so everything older than the truncation point
    # was skipped forever: with --limit 3 over a 44-reply backlog, 41 replies -
    # every positive one among them - were never classified, drafted or shown.
    # A reply that raised is not recorded as seen, so the cursor must not move
    # past it either: fetch_new_replies stops at the cursor, and the retry would
    # never be fetched again.
    # A row that fails EVERY time (an item with no timestamp_created, say) used
    # to pin the cursor for good: each tick rescanned up to max_pages x 100 rows
    # against a GET /emails endpoint limited to 20 requests a minute, and once
    # the backlog grew past that budget the older replies became unreachable.
    # After MAX_FAILED_ATTEMPTS the cursor is allowed past it; the id stays in
    # FAILED_KEY so it is still visible and still retryable by hand.
    blocking = [eid for eid, rec in failed.items()
                if not isinstance(rec, dict) or int(rec.get("attempts") or 1) < MAX_FAILED_ATTEMPTS]
    stuck = sorted(set(failed) - set(blocking))
    if stuck:
        logger.error("%d repl(ies) have failed %d+ times and are no longer holding the cursor: %s",
                     len(stuck), MAX_FAILED_ATTEMPTS, stuck[:10])
        job_log.log_run("reply_engine.poller", "replies_stuck",
                        {"count": len(stuck), "email_ids": stuck[:20],
                         "errors": [(failed.get(e) or {}).get("error") for e in stuck[:5]]})
    truncated = bool(fetched.get("truncated")) or bool(blocking) or bool(in_flight) or bool(deferred)
    if deferred:
        logger.warning("time budget of %ss reached: %d repl(ies) left for the next run", time_budget_s,
                       len(deferred))
    if not truncated and fetched.get("newest_seen"):
        # the newest row the scan actually saw, not the newest row it processed:
        # after a truncated run the already-seen rows must not drag the cursor back
        new_cursor = dict(fetched["newest_seen"])
    elif newest is not None and not truncated:
        new_cursor = {"last_email_id": str(newest.get("id")), "last_timestamp": str(newest.get("timestamp_created") or "")}
    if persist_cursor:
        # store.mutate, not store.set: poller:seen and poller:failed are shared
        # state and a tick that runs longer than the */5 schedule overlaps the
        # next one, so a blind set discards whatever the other worker recorded.
        # The merge keeps both workers' rows; the cursor still takes the newer
        # high-water mark.
        _merge_seen(store, seen)
        _merge_failed(store, failed, attempted | retired)
        store.set(CURSOR_KEY, new_cursor)

    # Approved-but-queued sends go out once the window is open (shadow:
    # would_do). approval.auto_send_due is deliberately NOT called here: it is
    # the one path that would send a first reply to a positive lead with no
    # human in the loop, which CLAUDE.md forbids, and wiring it into a */5
    # schedule put that behind a single environment variable.
    # CT3: the only auto-send is the template one (approval.auto_send_approved,
    # from the reply pipeline, for text exactly an approved template); the
    # tick only pushes the cards whose auto-send never ran and sends the FYI.
    flushed = []
    try:
        from services.reply_engine import app as app_mod
        from services.reply_engine import approval as approval_mod

        # ghl: an approval that expires in the queue has to cancel the call
        # _reply_draft already booked for it, the way veto() does.
        flushed = approval_mod.flush_queued(instantly, store=store, now=ts, ghl=app_mod.DEPS.ghl)
    except Exception as exc:  # noqa: BLE001
        logger.exception("flush failed: %s", exc)
        job_log.log_run("reply_engine.poller", "flush_failed", {"error": str(exc)})

    # CT3: a card whose deferred push never went out (a crash between the
    # card and its auto-send) is pushed now, once; then the counts-only FYI
    # of what went out on its own, at most one per 30 minutes. Each in its
    # own try: neither can stop the tick, and neither sends a reply.
    orphans_pushed = []
    try:
        from services.reply_engine import approval as approval_mod

        orphans_pushed = approval_mod.push_orphaned_deferred(store=store, now=ts)
    except Exception as exc:  # noqa: BLE001
        logger.exception("orphaned auto-send sweep failed: %s", exc)
        job_log.log_run("reply_engine.poller", "orphan_sweep_failed", {"error": str(exc)})
    fyi = None
    try:
        from services.reply_engine import approval as approval_mod

        fyi = approval_mod.flush_auto_send_fyi(store=store, now=ts)
    except Exception as exc:  # noqa: BLE001
        logger.exception("auto-send FYI failed: %s", exc)
        job_log.log_run("reply_engine.poller", "autosend_fyi_failed", {"error": str(exc)})

    # The 5-minute reply SLA, enforced on the */5 tick rather than measured once
    # a day by the 07:30 sweep. A pending card gets a rising push for as long as
    # it sits unactioned inside sending hours. This chases and only chases:
    # escalate_pending takes no Instantly client, so no rung of it can send.
    escalated = []
    try:
        from services.reply_engine import approval as approval_mod

        escalated = approval_mod.escalate_pending(store=store, now=ts)
    except Exception as exc:  # noqa: BLE001 - a chase failing must not stop the poll
        logger.exception("approval escalation failed: %s", exc)
        job_log.log_run("reply_engine.poller", "escalation_failed", {"error": str(exc)})

    waiting = pending_approvals(store, ts)
    if waiting:
        logger.warning("%d approval card(s) still waiting on Lorenzo", len(waiting))
        job_log.log_run("reply_engine.poller", "approvals_waiting",
                        {"count": len(waiting), "leads": [w["lead"] for w in waiting[:20]],
                         "unpushed": [w["lead"] for w in waiting if not w["pushed"]][:20],
                         "stuck": [w["lead"] for w in waiting if w.get("status")][:20]})
        _push_stuck(store, waiting, ts)
    summary = {"fetched": fetched["fetched"], "pages": fetched["pages"], "new": len(items), "processed": processed, "skipped": skipped,
               "errors": errors, "cursor": new_cursor, "truncated": truncated, "flushed": len(flushed),
               "in_flight": in_flight, "deferred": len(deferred), "time_budget_s": time_budget_s,
               "escalated": escalated, "failed_pending": sorted(failed.keys()),
               "orphans_pushed": [o.get("approval") for o in orphans_pushed],
               "autosend_fyi": bool(fyi and fyi.get("sent")),
               "pending_approvals": waiting, "results": results, "mode": settings.get_mode(),
               "start_at": start.isoformat() if start is not None else None, "before_start": len(before_start),
               "reached_start": bool(fetched.get("reached_start"))}
    job_log.log_run("reply_engine.poller", "ok" if not errors else "errors", {k: v for k, v in summary.items() if k != "results"})
    return summary


# ------------------------------------------------------------------ CLI
def _print_table(summary: Dict[str, Any]) -> None:
    print("mode=%s fetched=%s pages=%s new=%s processed=%s skipped=%s errors=%s flushed=%s" % (
        summary["mode"], summary["fetched"], summary["pages"], summary["new"], summary["processed"], summary["skipped"], summary["errors"], summary["flushed"]))
    print("-" * 120)
    print("%-19s %-34s %-24s %-22s %-5s %s" % ("received", "lead", "campaign", "label", "draft", "would_do"))
    for r in summary["results"]:
        if r.get("error"):
            print("ERROR %s: %s" % (r["email_id"], r["error"]))
            continue
        print("%-19s %-34s %-24s %-22s %-5s %s" % ((r.get("received_at") or "")[:19], (r.get("lead") or "")[:34], (r.get("campaign_key") or "")[:24],
                                                    (r.get("label") or "-")[:22], "yes" if r.get("draft") else "", ", ".join(r.get("actions", []))))
    print("cursor:", summary["cursor"], "(kept: the scan was truncated)" if summary.get("truncated") else "")
    if summary.get("start_at"):
        print("start date %s: %d older repl(ies) recorded as %s, never classified%s" % (
            summary["start_at"], summary.get("before_start") or 0, BEFORE_START,
            "; paging stopped there" if summary.get("reached_start") else ""))
    if summary.get("pending_approvals"):
        print("approvals still waiting on you: %d" % len(summary["pending_approvals"]))
        for w in summary["pending_approvals"]:
            print("  %-38s created %s pushed=%s" % ((w["lead"] or "")[:38], w["created_at"], w["pushed"]))
    if summary.get("escalated"):
        print("chased again this tick: %d" % len(summary["escalated"]))
        for e in summary["escalated"]:
            print("  %-38s step %d (%s) after %d sending minutes"
                  % ((e["lead"] or "")[:38], e["step"], e["priority"], int(e["waited_sending_minutes"])))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Reply engine poller (read-only against Instantly)")
    parser.add_argument("--dry-run", action="store_true", help="live key, read-only, throwaway store, MODE forced to shadow")
    parser.add_argument("--limit", type=int, default=None, help="max new replies to process")
    parser.add_argument("--pages", type=int, default=5, help="max pages of 100 to scan")
    parser.add_argument("--lookup-leads", action="store_true", help="POST /leads/list (read) for names/companies")
    parser.add_argument("--json", action="store_true", help="print the summary as JSON")
    parser.add_argument("--notify", action="store_true", help="allow ntfy pushes (default off in dry-run)")
    parser.add_argument("--start-at", default=None,
                        help="skip replies received before this ISO date/datetime (a date is midnight CT; 'off' "
                             "disables). Default: POLLER_START_AT, else %s" % settings.POLLER_START_AT_DEFAULT)
    args = parser.parse_args(argv)

    if args.dry_run or not settings.is_live():
        os.environ["MODE"] = "shadow"
        os.environ.pop("ALLOW_LIVE_WRITES", None)
    if args.dry_run and not args.notify:
        os.environ["NOTIFY"] = "off"
    if llm.is_fake():
        from services.reply_engine.classify import install_offline_fakes

        install_offline_fakes()

    from shared.instantly import default_client
    from shared.ghl import GHL
    from shared.store import JsonFileStore, get_store
    from shared.paths import tmp_file
    from services.reply_engine import app as app_mod

    if args.dry_run:
        # throwaway store AND throwaway logs: a dry run must leave the job log
        # the shadow watch is gated on exactly as it found it.
        from shared.job_log import use_scratch_logs

        use_scratch_logs("poller_dryrun")
        path = tmp_file("poller_dryrun_store.json")
        store = JsonFileStore(path)
        store.clear()
    else:
        store = get_store()
    instantly = default_client()
    deps = app_mod.configure(store=store, ghl=GHL(), instantly=instantly)
    summary = run_once(instantly, store, now=deps.now(), max_pages=args.pages, lookup_leads=args.lookup_leads, max_items=args.limit,
                       persist_cursor=not args.dry_run, start_at=args.start_at)
    if args.json:
        print(json.dumps(summary, indent=1, default=str))
    else:
        _print_table(summary)
    if args.dry_run:
        print("dry-run: MODE=shadow, store=%s (throwaway), logs in .tmp/scratch/poller_dryrun/, nothing sent" % path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "WARNING"))
    sys.exit(main())
