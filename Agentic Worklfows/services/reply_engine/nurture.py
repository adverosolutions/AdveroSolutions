"""90-day nurture enrollment (section 1): the hook other code calls when a lead
leaves the active follow-up and should hear from us again later.

This is the enrollment contract (and ``leave``). The nurture emails and the
nurture tick job are not built yet; ``touches`` is reserved for them.

    enroll(lead_email, reason, now)            # the positional contract
    enroll(lead_email, reason, now, store=None, campaign_id=None, note=None)
    leave(lead_email, reason, now, store=None)   # reason: "booked" / "re_engaged"

The record lives at its own key ``nurture:<lead email, stripped and
lowercased>``, not on the lead row, so enrolling never writes a
``lead:<campaign>:<email>`` row and needs no campaign id:

    {
      "lead_email": str,
      "status": "active",          # later: "ended" / "left" (a later call re-enrolls)
      "reason": str,               # the reason that started this enrollment
      "enrolled_at": ISO (CT),
      "ends_at": ISO (CT),         # enrolled_at + NURTURE_DAYS calendar days, same wall-clock time
      "campaign_id": str|None,
      "events": [ {"reason", "at", "campaign_id", "note"}, ... ],
      "touches": [],               # reserved for the nurture sends
    }

Idempotent: a call on an active record keeps ``enrolled_at``, ``reason`` and
``ends_at``, appends an event only when the reason differs from the latest
event's (a retrying job does not grow the list) and fills a missing
``campaign_id``. The returned dict carries ``created`` (True only when this
call started a new active enrollment); it is never stored.

Shadow contract: nothing here sends, calls a network client or goes through
shared.settings.guard_write. It writes the engine's own store only (one
``store.mutate``), which shadow mode allows.

A lead enrolled here is stopped by the follow-up cadence with reason
``nurture`` (cadence.tick_lead) and is never re-armed by cadence.resume.

All functions take ``now`` explicitly. No wall-clock reads.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from shared import slots as slot_rules
from shared.settings import TZ

logger = logging.getLogger("reply_engine.nurture")

REASONS = ("no_reply_after_sequence", "not_now_reply", "no_show_no_rebook")
LEAVE_REASONS = ("booked", "re_engaged")
NURTURE_DAYS = 90   # the plan's length; content and cadence come later
PREFIX = "nurture:"
ACTIVE = "active"
LEFT = "left"


def _normalize(lead_email: Any) -> str:
    email = str(lead_email or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("nurture needs a lead email, got %r" % (lead_email,))
    return email


def nurture_key(lead_email: Any) -> str:
    """``nurture:<normalized email>``. Raises ValueError for an empty email or
    one without an "@"."""
    return PREFIX + _normalize(lead_email)


def _store(store: Any) -> Any:
    if store is not None:
        return store
    from shared.store import get_store

    return get_store()


def _ends_at(enrolled: datetime) -> datetime:
    # Calendar days on the CT wall clock: enrolled 10:00 CDT ends 10:00 CST,
    # not 09:00 because the offset changed in between.
    return TZ.localize(enrolled.replace(tzinfo=None) + timedelta(days=NURTURE_DAYS))


def enroll(lead_email: Any, reason: str, now: datetime, store: Any = None,
           campaign_id: Optional[str] = None, note: Optional[str] = None) -> Dict[str, Any]:
    """Enroll ``lead_email`` in the 90-day nurture (or leave an active
    enrollment as it is). Returns the stored record plus ``created``.

    Raises ValueError for an empty email or one without an "@", a reason
    outside REASONS, or a naive ``now``."""
    email = _normalize(lead_email)
    if reason not in REASONS:
        raise ValueError("unknown nurture reason %r (expected one of %s)" % (reason, ", ".join(REASONS)))
    if not isinstance(now, datetime) or now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
        raise ValueError("nurture.enroll needs a timezone-aware now, got %r" % (now,))
    ct = slot_rules.to_tz(now)
    at = ct.isoformat()
    campaign = str(campaign_id) if campaign_id not in (None, "") else None
    event = {"reason": reason, "at": at, "campaign_id": campaign,
             "note": str(note) if note is not None else None}
    box = {}  # type: Dict[str, Any]

    def fresh(old_events: Any, old_campaign: Any) -> Dict[str, Any]:
        events = [e for e in old_events if isinstance(e, dict)] if isinstance(old_events, list) else []
        return {
            "lead_email": email,
            "status": ACTIVE,
            "reason": reason,
            "enrolled_at": at,
            "ends_at": _ends_at(ct).isoformat(),
            "campaign_id": campaign or old_campaign,
            "events": events + [event],
            "touches": [],
        }

    def apply(current: Any) -> Dict[str, Any]:
        # mutate may call this more than once on some stores; decide from scratch each time.
        box["created"] = True
        if not isinstance(current, dict):
            # absent, or a malformed value: a fresh record, nothing kept
            return fresh([], None)
        if current.get("status") != ACTIVE:
            # a finished enrollment ("ended" / "left"): start again, keep its trail
            return fresh(current.get("events"), current.get("campaign_id"))
        box["created"] = False
        rec = dict(current)
        events = [e for e in (rec.get("events") or []) if isinstance(e, dict)] \
            if isinstance(rec.get("events"), list) else []
        if not events or events[-1].get("reason") != reason:
            events.append(event)
        rec["events"] = events
        if not isinstance(rec.get("touches"), list):
            rec["touches"] = []
        if rec.get("campaign_id") in (None, "") and campaign:
            rec["campaign_id"] = campaign
        # An active record missing its dates (hand-edited) gets them now; one
        # that has them keeps them.
        rec["lead_email"] = email
        rec.setdefault("reason", reason)
        if not rec.get("enrolled_at"):
            rec["enrolled_at"] = at
        if not rec.get("ends_at"):
            try:
                start = slot_rules.to_tz(slot_rules.parse_iso(rec["enrolled_at"]))
            except (ValueError, TypeError):
                start = ct
            rec["ends_at"] = _ends_at(start).isoformat()
        return rec

    stored = _store(store).mutate(nurture_key(email), apply)
    if box.get("created"):
        logger.info("nurture: enrolled %s (%s) until %s", email, reason, stored.get("ends_at"))
    return dict(stored, created=bool(box.get("created")))


def leave(lead_email: Any, reason: str, now: datetime, store: Any = None) -> Optional[Dict[str, Any]]:
    """Take ``lead_email`` out of the nurture: an active record gets
    ``status`` "left", ``left_at``, ``left_reason`` and one event. Returns the
    stored record, or None when the lead has no nurture record.

    Idempotent: a record that is not active (already left, or ended) is
    returned unchanged. Raises ValueError for an empty email or one without an
    "@", a reason outside LEAVE_REASONS, or a naive ``now``."""
    email = _normalize(lead_email)
    if reason not in LEAVE_REASONS:
        raise ValueError("unknown nurture leave reason %r (expected one of %s)" % (reason, ", ".join(LEAVE_REASONS)))
    if not isinstance(now, datetime) or now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
        raise ValueError("nurture.leave needs a timezone-aware now, got %r" % (now,))
    at = slot_rules.to_tz(now).isoformat()
    box = {"left": False}

    def apply(current: Any) -> Any:
        box["left"] = False
        if not isinstance(current, dict) or current.get("status") != ACTIVE:
            return current  # not enrolled, or already out: nothing changes
        box["left"] = True
        rec = dict(current)
        events = [e for e in (rec.get("events") or []) if isinstance(e, dict)] \
            if isinstance(rec.get("events"), list) else []
        events.append({"reason": reason, "at": at, "campaign_id": rec.get("campaign_id"), "note": "left"})
        rec.update(status=LEFT, left_at=at, left_reason=reason, events=events)
        return rec

    st = _store(store)
    seen = st.get(nurture_key(email))
    if not isinstance(seen, dict):
        return None  # never enrolled: write nothing
    if seen.get("status") != ACTIVE:
        return seen  # already out: write nothing
    stored = st.mutate(nurture_key(email), apply)
    if box["left"]:
        logger.info("nurture: %s left (%s)", email, reason)
    return stored if isinstance(stored, dict) else None


def get(lead_email: Any, store: Any = None) -> Optional[Dict[str, Any]]:
    """The stored nurture record, or None (never enrolled, a malformed value,
    or an email no enrollment could have been written for)."""
    try:
        key = nurture_key(lead_email)
    except ValueError:
        return None
    value = _store(store).get(key)
    return value if isinstance(value, dict) else None


def is_enrolled(lead_email: Any, store: Any = None) -> bool:
    """True only while the lead's nurture record is ``active``."""
    rec = get(lead_email, store)
    return bool(rec) and rec.get("status") == ACTIVE
