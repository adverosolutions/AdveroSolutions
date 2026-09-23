"""Upwork follow-up thread state machine (U2). Binding spec: DESIGN.md.

A pure state machine over RoomContext dicts (DESIGN "Snapshot") and Thread
dicts (store key ``upwork:<room_id>``). Nothing here reads the clock, the
network or a file: time is always passed in, and the only I/O is the store
handed to ``run`` and the CLI helpers. Nothing here writes to Upwork.

Every ``store.mutate`` callback here is pure: no store call and no classifier
call while a mutate is open. JsonFileStore holds one flock for the whole
mutate, so any store call inside it (``shared.llm.complete`` makes one for its
spend counter) waits on this process's own lock forever. ``run`` therefore
classifies before its write: it reads the thread without a lock, runs the
room's step on that copy with the real classifier, then runs the same step
inside the thread's ``store.mutate`` on those answers only.

Two axes live on a thread:

* ``status`` (DESIGN ThreadStatus) is where the sequence is: a silence is
  running, the client wrote last, the client said later, and so on. Plus
  ``closed``: the room is blocked on Upwork (``room["blocked"]``). It is closed
  on first sight and nothing moves while it stays blocked. Once the room is
  open again, only a client message written after the block reopens it, and
  it takes the path the pre-block status (``marks.pre_block``) would have
  taken: a stopped thread stays stopped, a lost one stays lost, any other
  status takes the normal reply path. Otherwise ``--resume`` / ``--stage`` do.
* ``stage`` (DESIGN "Stages") is the pipeline stage Lorenzo controls. Only the
  drafting stages ``new_reply`` and ``proposal_sent`` ever get a touch or a
  reply draft. ``follow_up_later`` gets one check-in draft on ``follow_up_at``
  and then returns to ``new_reply``. A stage set by ``lorenzo`` or ``ghl`` is
  never changed by the engine, except ``won`` from a real contract. While
  Lorenzo (or GHL) holds a drafting stage, no classifier label stops drafting:
  a conflicting label becomes ``needs_review`` and the client still gets a
  reply draft.

Days
----
Every day-based rule (touch gaps, resurface, skip, close-out, dormant, the
revivable age, ``follow_up_at``) counts America/Chicago calendar days, and a
rule that is due on day N is due from 00:00 CT that day. So the day-N touch
lands in the day-N 08:30 CT morning batch, whatever the hour of the anchor,
and a DST change never shifts it.

Public API
----------
``thread_key(room_id)``, ``new_thread(room, now, enrolled_by)``,
``eligible(room, now, first_run)``, ``advance(thread, room, now, classify,
allow_draft=True)``, ``due_summary(thread, now)``, ``record_pending(...)``
(raises ``PendingRefused``), ``clear_pending(...)``,
``apply_external_stage(thread, stage, now)``, ``run(store, snapshot, now,
classify, first_run=None)`` and the CLI helpers ``stop``, ``resume``,
``enroll``, ``set_stage``.

``classify(text, room)`` is injected and returns ``{"label", "confidence",
"follow_up_at"}`` (optionally ``raw_label``) with labels ``positive``,
``question``, ``neutral``, ``not_now``, ``declined``, ``hired_other``,
``not_interested``, ``hostile``, ``machine``. Only ``label`` drives the
machine; a ``raw_label`` (a low-confidence stage-changing read the classifier
downgraded to ``neutral``) only adds a ``needs_review``.

Action vocabulary (what the orchestrator consumes)
--------------------------------------------------
Every action is a dict with a ``type``:

* ``{"type": "enrolled", "by": "auto"|"manual"}``: a thread was created.
* ``{"type": "revivable", "reason", "last_client_at"}``: a room was not
  auto-enrolled because its last client message is too old; ``--enroll``
  adds it. Listed once (kept in the ``upwork_meta`` record).
* ``{"type": "classified", "message_id", "label", "confidence"}``.
* ``{"type": "sent_detected", "kind", "touch", "message_id"}``: a freelancer
  message newer than ``pending.issued_at`` counted as the pending draft being
  sent (rewritten or not).
* ``{"type": "draft_touch", "touch": N}``: draft touch N (1..7) now.
* ``{"type": "draft_reply", "message_id"}``: draft a reply to that client
  message now.
* ``{"type": "draft_checkin", "follow_up_at"}``: draft the one check-in now.
* ``{"type": "deferred", "draft": <draft action>}``: due but over
  ``MAX_NEW_DRAFTS_PER_RUN``; nothing is reserved, the next run retries.
* ``{"type": "withdraw_pending", "reason", "pending"}``: the pending draft is
  void (client replied, won, lost, stage left drafting, skipped, stopped...).
  ``reason == "skipped"`` is the 7-day drop.
* ``{"type": "resurface", "pending"}``: 3 CT days old and unsent; show again (once).
* ``{"type": "status_change", "from", "to", "reason"}``.
* ``{"type": "stage_change", "from", "to", "by", "reason"}``: every stage move.
* ``{"type": "ghl_stage", "stage", "by": "engine"}``: an ENGINE stage move the
  GHL mirror should push. Moves by Lorenzo (CLI) or read back from GHL only
  produce ``stage_change``; the mirror follows ``thread["stage"]``.
* ``{"type": "needs_review", "reason", ...}``: surface to Lorenzo, no draft.
  Reasons: ``unknown_last_message``, ``messages_missing``,
  ``client_wrote_after_lost``, ``unrecognised_label``, ``low_confidence``
  (carries ``label`` and ``raw_label``), ``stage_kept`` (a label would have
  moved a stage Lorenzo or GHL set; carries ``label``, ``stage``, ``set_by``),
  ``not_in_pull`` (a live thread missing from the snapshot; at most once per
  7 days), ``reply_skipped`` (carries ``message_id``, ``skipped_at``,
  ``waiting_since``: the reply to a waiting client expired unsent for the
  second time. The first expiry is redrafted at once (``REPLY_REDRAFTS``); after
  the second there is no redraft, and ``due_summary`` kind ``reply_skipped``
  keeps it in the batch on every later run until Lorenzo answers, resumes,
  stops or moves it, or the client writes again), ``room_blocked`` (first
  sight of a blocked room, once per block; carries ``blocked_at``, ``stage``,
  ``set_by`` and ``stage_kept``: true when Lorenzo's or GHL's stage was kept
  instead of moving to ``lost``).
* ``{"type": "error", "error", "error_type"}``: this room was not advanced
  (StoreError, classifier failure, a corrupt record, or ``MetaUnavailable``
  when enrolment is paused because the meta record cannot be read); the
  others were.
* ``{"type": "room_deferred", "reason", "detail"}``: this room was not
  advanced and nothing was written. The thread changed between ``run``'s
  unlocked read and its write, so the write would have read other client
  messages than the ones classified: ``reason`` ``new_messages`` (one nobody
  classified) or ``message_ids_changed`` (other ids, or fewer of them). The
  next run reads it again.

Draft reservation contract
--------------------------
When ``advance`` emits a draft action it reserves the slot with a placeholder
``pending`` (``text`` and ``card_id`` null, ``issued_at`` = now). That makes a
second run at the same time a no-op. The orchestrator then fills it with
``record_pending`` (inside ``store.mutate``), or calls ``clear_pending(...,
retry=True)`` when drafting failed. A placeholder still unfilled on a later
run (a crashed tick) is released and the draft is emitted again; it is never
resurfaced or counted as a skip.

Thread fields
-------------
DESIGN fields plus ``proposal_id`` and ``job_id`` (from the room; backfilled
and kept current by ``advance``), ``stage``, ``stage_set_by``, ``stage_changed_at`` and
``marks`` (sequence-internal flags: ``initialized``, ``last_seen_at``,
``last_client_at``, ``client_waiting``, ``reply_target``, ``reply_for``,
``checkin_for``, ``review_for``, ``hold``, ``messages_missing``,
``dormant_floor``, ``not_in_pull_at``, ``reply_skipped``, ``blocked_at``,
``pre_block``). ``pending.kind`` is ``touch``,
``reply`` or ``checkin``. History entries for sent drafts:
``{"at", "event": "touch_sent", "touch", "text"}``, ``reply_sent`` and
``checkin_sent`` (``at`` = the freelancer message time; ``text`` = that
message's text, else the draft text, capped at 600 chars). Every history
event this module writes is listed in DESIGN "Field reference as built"
(a test fails when one is missing there), including the silence boundaries
draft.py reads.

A client message on a ``stopped`` or ``lost`` thread is classified only to
drop machine text: its label moves nothing. A real message still ends the
silence (``silence_ended`` when one was running) and stays the reply target,
so ``--resume`` or a move back to a drafting stage answers it.

Meta record: ``upwork_meta`` (outside the ``upwork:`` thread prefix) holds
``first_run_at`` and ``revivable``. A legacy ``upwork:meta`` is migrated.
"""
import copy
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytz

from shared.store import StoreError

# --------------------------------------------------------------- constants
PREFIX = "upwork:"
META_KEY = "upwork_meta"
LEGACY_META_KEY = "upwork:meta"
CT = pytz.timezone("America/Chicago")

GAPS = {1: 2, 2: 2, 3: 3, 4: 4, 5: 5, 6: 7, 7: 7}
LAST_TOUCH = 7
MAX_NEW_DRAFTS_PER_RUN = 10
REVIVE_DAYS = 45
DORMANT_DAYS = 60
RESURFACE_DAYS = 3
SKIP_DAYS = 7
REPLY_REDRAFTS = 1  # a reply draft that expires unsent is drafted this many more times, then waits visibly
CLOSE_OUT_WAIT_DAYS = 14
MAX_CYCLES = 3
NOT_NOW_DEFAULT_DAYS = 30
HISTORY_CAP = 50
NOT_IN_PULL_REVIEW_DAYS = 7
TEXT_CAP = 600

# ThreadStatus
ACTIVE = "active"
AWAITING = "awaiting_lorenzo"
PAUSED = "paused_not_now"
WON = "won"
LOST = "lost"
CLOSED_OUT = "closed_out"
DORMANT = "dormant"
STOPPED = "stopped"
CLOSED = "closed"  # the room is blocked on Upwork (stop_reason "room_blocked")
STATUSES = (ACTIVE, AWAITING, PAUSED, WON, LOST, CLOSED_OUT, DORMANT, STOPPED, CLOSED)
LIVE_STATUSES = (ACTIVE, AWAITING, PAUSED)
RESTING_STATUSES = (LOST, CLOSED_OUT, DORMANT, WON, STOPPED, PAUSED, CLOSED)
ROOM_BLOCKED = "room_blocked"
ROOM_UNBLOCKED = "room_unblocked"  # reason for undoing the block when the client writes after it
ROOM_DEFERRED = "room_deferred"    # run(): the thread changed between the classification and the write
NEW_MESSAGES = "new_messages"
MESSAGE_IDS_CHANGED = "message_ids_changed"

# Stages (DESIGN "Stages")
STAGES = ("new_reply", "proposal_sent", "call_booked", "follow_up_later", "won", "lost")
DRAFTING_STAGES = ("new_reply", "proposal_sent")
STAGE_SETTERS = ("engine", "lorenzo", "ghl")
MANUAL_SETTERS = ("lorenzo", "ghl")

# Classifier labels
REPLY_LABELS = ("positive", "question", "neutral")
LOST_LABELS = ("declined", "hired_other", "not_interested", "hostile")
NOT_NOW = "not_now"
MACHINE = "machine"
LABELS = REPLY_LABELS + LOST_LABELS + (NOT_NOW, MACHINE)

CLIENT = "client"
FREELANCER = "freelancer"
PENDING_KINDS = ("touch", "reply", "checkin")
DRAFT_TYPES = ("draft_touch", "draft_reply", "draft_checkin")


class ThreadNotFound(LookupError):
    """The CLI named a room that has no thread."""


class PendingRefused(ValueError):
    """record_pending refused: no matching reservation, or the thread may no
    longer draft. ``reason`` is one of ``no_reservation``,
    ``reservation_mismatch``, ``stage_not_drafting``, ``status_not_live``."""

    def __init__(self, reason: str, detail: str = ""):
        super(PendingRefused, self).__init__("%s%s" % (reason, (": " + detail) if detail else ""))
        self.reason = reason


class BadRecord(ValueError):
    """A stored thread is not a dict."""


class MetaUnavailable(RuntimeError):
    """The meta record could not be read or written; enrolment is paused."""


class ThreadChanged(RuntimeError):
    """``run``'s write asked for a classification its unlocked pass did not
    make: the stored thread changed in between. ``reason`` is ``new_messages``
    or ``message_ids_changed``. Raised inside the mutate, so nothing is written."""

    def __init__(self, reason: str, detail: str):
        super(ThreadChanged, self).__init__("%s: %s" % (reason, detail))
        self.reason = reason
        self.detail = detail


# ------------------------------------------------------------ time helpers
def _dt(value: Any) -> Optional[datetime]:
    """datetime, date, ISO-8601 string (Z or offset) or epoch -> aware UTC.
    A bare ``YYYY-MM-DD`` is 00:00 America/Chicago on that date."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return _ct_midnight(value)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        secs = float(value) / (1000.0 if abs(value) > 1e11 else 1.0)
        return datetime.fromtimestamp(secs, tz=timezone.utc)
    text = str(value).strip()
    if len(text) == 10:
        try:
            return _ct_midnight(datetime.strptime(text, "%Y-%m-%d").date())
        except ValueError:
            return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _iso(value: Any) -> Optional[str]:
    d = _dt(value)
    return d.strftime("%Y-%m-%dT%H:%M:%SZ") if d else None


def _ct_date(value: Any) -> Optional[date]:
    d = _dt(value)
    return d.astimezone(CT).date() if d else None


def _ct_midnight(d: date) -> datetime:
    """00:00 America/Chicago on calendar date ``d``, as UTC (DST-safe)."""
    return CT.localize(datetime(d.year, d.month, d.day)).astimezone(timezone.utc)


def _day_due(anchor: Any, days: int) -> Optional[datetime]:
    """Start (00:00 CT) of the CT calendar day ``days`` after ``anchor``'s CT day."""
    d = _ct_date(anchor)
    return _ct_midnight(d + timedelta(days=days)) if d else None


def _ct_day_str(d: Optional[date]) -> Optional[str]:
    return d.strftime("%Y-%m-%d") if d else None


def _now(now: Any) -> datetime:
    """``now`` as aware UTC, in whole seconds like every stored time (``_iso``).
    A reservation stores ``issued_at`` to the second, so a second run at the same
    ``now`` must compare equal to it, not 0.4 s later (DESIGN "Idempotent")."""
    d = _dt(now)
    if d is None:
        raise ValueError("now must be a datetime or an ISO-8601 string, got %r" % (now,))
    return d.replace(microsecond=0)


# ---------------------------------------------------------- room helpers
def thread_key(room_id: str) -> str:
    return PREFIX + str(room_id)


def _messages(room: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The room's spoken messages, oldest first. Room events (``event: true``,
    e.g. "X sent an offer") are dropped here, so they never reach a decision:
    holds, reply and send detection, the dormant clock, bursts."""
    return [m for m in (room.get("messages") or []) if isinstance(m, dict) and not m.get("event")]


def _side(m: Dict[str, Any]) -> str:
    side = m.get("side")
    return side if side in (CLIENT, FREELANCER) else "unknown"


def _msg_id(m: Dict[str, Any]) -> str:
    return str(m.get("id") or "%s|%s" % (m.get("at"), m.get("side")))


def _contract_status(room: Dict[str, Any]) -> Optional[str]:
    """Upper-case status of the room's contract, "UNKNOWN" for a contract with
    no status, None when the room has never had a contract."""
    contract = room.get("contract")
    if isinstance(contract, dict) and (contract.get("contract_id") or contract.get("status")):
        return str(contract.get("status") or "UNKNOWN").upper()
    if contract and not isinstance(contract, dict):
        return "UNKNOWN"
    return None


def _room_won(room: Dict[str, Any]) -> Optional[str]:
    """Why an enrolled thread is won, or None. Any contract on the room (ACTIVE,
    ENDED, CLOSED, PAUSED...) means the contract happened."""
    status = _contract_status(room)
    if status:
        return "contract_" + status.lower()
    if room.get("offer_state") == "contract_started":
        return "offer_contract_started"
    return None


def _messages_frozen(room: Dict[str, Any], snapshot: Optional[Dict[str, Any]] = None) -> bool:
    """True when THIS room's messages were not pulled: it is listed in
    ``snapshot["missing_messages"]``, or its ``messages`` is null. The global
    ``sections.messages`` flag never freezes every room (collect.py sets it
    False when any single room failed)."""
    snapshot = snapshot or {}
    missing = snapshot.get("missing_messages")
    if isinstance(missing, (list, tuple, set)) and room.get("room_id") in missing:
        return True
    room_sections = room.get("sections")
    if isinstance(room_sections, dict) and room_sections.get("messages") is False:
        return True
    return room.get("messages") is None


def _last_client_at(room: Dict[str, Any]) -> Optional[datetime]:
    times = [_dt(m.get("at")) for m in _messages(room) if _side(m) == CLIENT]
    times = [t for t in times if t]
    return max(times) if times else None


# ------------------------------------------------------- thread helpers
def _blank_marks() -> Dict[str, Any]:
    return {
        "initialized": False,       # enrolment tail processed
        "last_seen_at": None,       # time of last_seen_message_id (fallback when it scrolls out)
        "last_client_at": None,     # latest non-machine client message
        "client_waiting": False,    # the latest spoken message is an unanswered client message
        "reply_target": None,       # client message a reply would answer
        "reply_for": None,          # client message a reply draft was issued for
        "checkin_for": None,        # follow_up_at a check-in was issued for
        "review_for": None,         # unknown last_side already surfaced
        "hold": False,              # room last_side is unknown: no drafts
        "messages_missing": False,  # needs_review for missing messages already surfaced
        "dormant_floor": None,      # manual enrol / resume / revive restarts the 60-day clock
        "not_in_pull_at": None,     # last "not in today's pull" review
        "reply_skipped": None,      # {message_id, count, at}: reply drafts for that message dropped unsent
        "blocked_at": None,         # the block that closed the thread; only a client message after it reopens
        "pre_block": None,          # {status, stop_reason, stage, set_by}: the thread as the block found it
    }


def _ensure(thread: Any) -> Dict[str, Any]:
    """Fill fields a thread written by an older version may lack."""
    if not isinstance(thread, dict):
        raise BadRecord("stored thread is %s, not a dict" % type(thread).__name__)
    thread.setdefault("history", [])
    thread.setdefault("pending", None)
    thread.setdefault("touch_index", 0)
    thread.setdefault("cycles", 0)
    thread.setdefault("status", ACTIVE)
    thread.setdefault("stop_reason", None)
    thread.setdefault("follow_up_at", None)
    thread.setdefault("silence_started_at", None)
    thread.setdefault("last_seen_message_id", None)
    thread.setdefault("ghl", {"contact_id": None, "opportunity_id": None, "stage": None})
    thread.setdefault("proposal_id", None)
    thread.setdefault("job_id", None)
    thread.setdefault("stage", "new_reply")
    thread.setdefault("stage_set_by", "engine")
    thread.setdefault("stage_changed_at", thread.get("enrolled_at"))
    marks = thread.get("marks")
    if not isinstance(marks, dict):
        marks = {}
    for k, v in _blank_marks().items():
        marks.setdefault(k, v)
    thread["marks"] = marks
    return thread


def _cap(text: Any) -> Optional[str]:
    return None if text is None else str(text)[:TEXT_CAP]


def _hist(t: Dict[str, Any], now: datetime, event: str, **extra: Any) -> None:
    entry = {"at": _iso(now), "event": event}
    entry.update(extra)
    t["history"] = (list(t.get("history") or []) + [entry])[-HISTORY_CAP:]


def _set_status(t, status, now, acts, reason):
    prev = t.get("status")
    if prev == status:
        return False
    t["status"] = status
    acts.append({"type": "status_change", "from": prev, "to": status, "reason": reason})
    _hist(t, now, "status", to=status, reason=reason)
    return True


def _undo_marks(t, p):
    if p.get("kind") == "reply":
        t["marks"]["reply_for"] = None
    elif p.get("kind") == "checkin":
        t["marks"]["checkin_for"] = None


def _withdraw(t, now, acts, reason, redraft=True):
    p = t.get("pending")
    if not p:
        return
    t["pending"] = None
    acts.append({"type": "withdraw_pending", "reason": reason, "pending": copy.deepcopy(p)})
    _hist(t, now, "withdrawn", reason=reason, kind=p.get("kind"), touch=p.get("touch"))
    if redraft:
        # a withdrawn (not skipped) reply or check-in may be drafted again later
        _undo_marks(t, p)


def _reply_skip_count(t) -> int:
    """How many reply drafts for the current reply target were dropped unsent."""
    rec = t["marks"].get("reply_skipped")
    if isinstance(rec, dict) and rec.get("message_id") == t["marks"].get("reply_target"):
        return int(rec.get("count") or 0)
    return 0


def _note_reply_skip(t, now, redraft):
    """The reply drafted for the waiting client message was dropped unsent.
    Recorded in ``marks.reply_skipped`` and a ``reply_skipped`` history entry
    (what due_summary and the batch read). ``redraft`` makes it due again now."""
    marks = t["marks"]
    target = marks.get("reply_target")
    count = _reply_skip_count(t) + 1
    marks["reply_skipped"] = {"message_id": target, "count": count, "at": _iso(now)}
    if redraft:
        marks["reply_for"] = None
    _hist(t, now, "reply_skipped", message_id=target, count=count, redraft=bool(redraft))


def _reply_skipped(t) -> bool:
    """The client wrote last and the reply drafted for that message was dropped
    unsent, with no redraft coming (``due_summary`` kind ``reply_skipped``)."""
    marks = t["marks"]
    target = marks.get("reply_target")
    return (t.get("status") == AWAITING and not t.get("pending") and bool(target)
            and marks.get("reply_for") == target)


def _manual_stage(t) -> bool:
    return t.get("stage_set_by") in MANUAL_SETTERS


def _move_stage(t, stage, now, by, acts, reason, force=False):
    """Move the stage. An engine move never overrides a lorenzo/ghl stage
    unless ``force`` (won from a real contract, the check-in return).
    Only engine moves emit ``ghl_stage``."""
    if stage not in STAGES:
        raise ValueError("unknown stage %r (one of %s)" % (stage, ", ".join(STAGES)))
    cur = t.get("stage")
    if by == "engine" and not force and _manual_stage(t):
        return False
    if cur == stage:
        if by == "lorenzo":
            t["stage_set_by"] = by  # an explicit CLI pick pins the stage
        return False
    t["stage"] = stage
    t["stage_set_by"] = by
    t["stage_changed_at"] = _iso(now)
    acts.append({"type": "stage_change", "from": cur, "to": stage, "by": by, "reason": reason})
    if by == "engine":
        acts.append({"type": "ghl_stage", "stage": stage, "by": "engine"})
    _hist(t, now, "stage", to=stage, by=by, reason=reason)
    if stage not in DRAFTING_STAGES:
        _withdraw(t, now, acts, "stage_" + stage)
    return True


def _engine_stage(t, stage, now, acts, reason):
    return _move_stage(t, stage, now, "engine", acts, reason)


def _label_stage(t, stage, now, acts, label, mid):
    """An engine stage move caused by a classifier label. Blocked by a stage
    Lorenzo or GHL set, and then surfaced instead."""
    if t.get("stage") == stage:
        return
    if _manual_stage(t):
        acts.append({"type": "needs_review", "reason": "stage_kept", "label": label,
                     "stage": t.get("stage"), "set_by": t.get("stage_set_by"), "message_id": mid,
                     "note": "the client reply reads as %s; the thread stays in %s because %s set it"
                             % (label, t.get("stage"), t.get("stage_set_by"))})
        return
    _engine_stage(t, stage, now, acts, label)


def _seen(t, m):
    t["last_seen_message_id"] = _msg_id(m)
    at = _dt(m.get("at"))
    prev = _dt(t["marks"].get("last_seen_at"))
    if at and (prev is None or at >= prev):
        t["marks"]["last_seen_at"] = _iso(at)


def _new_messages(t, msgs):
    lid = t.get("last_seen_message_id")
    if lid:
        for i, m in enumerate(msgs):
            if _msg_id(m) == lid:
                return msgs[i + 1:]
    la = _dt(t["marks"].get("last_seen_at"))
    if la:
        return [m for m in msgs if (_dt(m.get("at")) or la) > la]
    return list(msgs)


def _future_follow_up(value: Any, now: datetime) -> str:
    """The classifier's date when it is a real future CT day, else +30 CT days."""
    d = _ct_date(value) if isinstance(value, (str, date, datetime)) else None
    today = _ct_date(now)
    if d and d > today:
        return _ct_day_str(d)
    return _ct_day_str(today + timedelta(days=NOT_NOW_DEFAULT_DAYS))


def _revive(t, now, acts, reason):
    """Back to life in a drafting stage. A waiting client message gets a reply
    draft; otherwise a fresh silence starts now."""
    marks = t["marks"]
    t["stop_reason"] = None
    marks["dormant_floor"] = _iso(now)
    marks["blocked_at"] = None  # a room still blocked closes the thread again on the next run
    marks["pre_block"] = None
    t["touch_index"] = 0
    if marks.get("client_waiting") and marks.get("reply_target"):
        marks["reply_for"] = None
        t["silence_started_at"] = None
        _set_status(t, AWAITING, now, acts, reason)
    else:
        t["silence_started_at"] = _iso(now)
        _set_status(t, ACTIVE, now, acts, reason)


def _sync_ids(t, room, now):
    """Keep ``proposal_id`` / ``job_id`` from the room (collect.live_threads
    re-links a live thread through them once the room ages out of the pull
    window). Backfilled when missing; a different non-null value replaces the
    stored one with a history note; a null in the room never erases one."""
    for field in ("proposal_id", "job_id"):
        new = room.get(field)
        old = t.get(field)
        if not new or new == old:
            continue
        t[field] = new
        if old:
            _hist(t, now, "%s_changed" % field, old=old, new=new)


def _mark_won(t, now, acts, reason):
    _withdraw(t, now, acts, WON, redraft=False)
    _set_status(t, WON, now, acts, reason)
    _move_stage(t, "won", now, "engine", acts, reason, force=True)


def _close_blocked(t, room, now, acts):
    """First sight of the room blocked on Upwork: the pending draft is
    withdrawn, the status is ``closed`` and the stage goes to ``lost`` (engine),
    unless Lorenzo or GHL set the stage: then it is kept, and nothing drafts
    anyway because ``closed`` is not a live status.

    ``marks.pre_block`` keeps the status, stop reason, stage and setter the
    block found, so a client message after the unblock takes the path the
    thread would have taken without the block (``_reopen``). When Lorenzo
    stopped the closed thread and the room is still blocked, the next run
    closes it again and keeps his stop as the pre-block status; the stage the
    first close replaced is carried over.

    One ``needs_review`` ``room_blocked`` per block: closing again for the same
    ``blocked_at`` after a ``--stop`` (or a ``--stage`` to lost or
    follow_up_later) adds none. A ``--resume`` or a move to a drafting stage
    clears ``marks.blocked_at``, so that re-close is flagged again."""
    marks = t["marks"]
    blocked_at = _iso(room.get("blocked_at"))
    same_block = blocked_at is not None and marks.get("blocked_at") == blocked_at
    prev = marks.get("pre_block") if isinstance(marks.get("pre_block"), dict) else None
    stage, set_by = t.get("stage"), t.get("stage_set_by")
    if prev is not None and (stage, set_by) == ("lost", "engine"):
        stage, set_by = prev.get("stage"), prev.get("set_by")
    marks["pre_block"] = {"status": t.get("status"), "stop_reason": t.get("stop_reason"),
                          "stage": stage, "set_by": set_by}
    _withdraw(t, now, acts, ROOM_BLOCKED)
    t["stop_reason"] = ROOM_BLOCKED
    marks["blocked_at"] = blocked_at or _iso(now)
    _set_status(t, CLOSED, now, acts, ROOM_BLOCKED)
    _hist(t, now, ROOM_BLOCKED, blocked_at=blocked_at)
    kept = _manual_stage(t) and t.get("stage") != "lost"
    if not kept:
        _engine_stage(t, "lost", now, acts, ROOM_BLOCKED)
    if not same_block:
        acts.append({"type": "needs_review", "reason": ROOM_BLOCKED, "blocked_at": blocked_at,
                     "stage": t.get("stage"), "set_by": t.get("stage_set_by"), "stage_kept": kept})


def _restore_stage(t, pre, now, acts):
    """Undo the block's own stage move (an engine stage it moved to ``lost``),
    unless the stage was moved since. An engine move: the GHL mirror follows."""
    stage = pre.get("stage")
    if (t.get("stage"), t.get("stage_set_by")) == ("lost", "engine") and pre.get("set_by") == "engine" \
            and stage in STAGES and stage not in ("lost", "won"):
        _engine_stage(t, stage, now, acts, ROOM_UNBLOCKED)


def _reopen(t, now, acts):
    """The room is open again and the client wrote after the block: undo the
    block from ``marks.pre_block``. The stage it replaced comes back, and so do
    the stop reason and, for ``stopped`` and ``lost``, the status. Returns the
    status whose client-message path the burst takes: ``stopped`` / ``lost``
    (it stays so, as without the block), any other pre-block status (the normal
    path, from ``closed``), or ``closed`` for a thread closed before
    ``pre_block`` existed (the normal path, like closed_out)."""
    marks = t["marks"]
    pre = marks.get("pre_block") if isinstance(marks.get("pre_block"), dict) else {}
    marks["pre_block"] = None
    marks["blocked_at"] = None
    _restore_stage(t, pre, now, acts)
    status = pre.get("status")
    if status not in STATUSES or status in (CLOSED, WON):
        t["stop_reason"] = None
        return CLOSED
    t["stop_reason"] = pre.get("stop_reason")
    if status in (STOPPED, LOST):
        _set_status(t, status, now, acts, ROOM_UNBLOCKED)
    return status


# ----------------------------------------------------------- enrolment
def new_thread(room: Dict[str, Any], now: Any, enrolled_by: str = "auto") -> Dict[str, Any]:
    """A fresh thread in stage ``new_reply``. ``advance`` reads the room
    history on its first call (the enrolment tail)."""
    if enrolled_by not in ("auto", "manual"):
        raise ValueError("enrolled_by must be 'auto' or 'manual'")
    now = _now(now)
    marks = _blank_marks()
    if enrolled_by == "manual":
        marks["dormant_floor"] = _iso(now)
    t = {
        "room_id": room.get("room_id"),
        "client": room.get("client"),
        "proposal_id": room.get("proposal_id"),
        "job_id": room.get("job_id"),
        "status": ACTIVE,
        "enrolled_at": _iso(now),
        "enrolled_by": enrolled_by,
        "silence_started_at": None,
        "touch_index": 0,
        "cycles": 0,
        "pending": None,
        "last_seen_message_id": None,
        "history": [],
        "stop_reason": None,
        "follow_up_at": None,
        "ghl": {"contact_id": None, "opportunity_id": None, "stage": None},
        "stage": "new_reply",
        "stage_set_by": "engine",
        "stage_changed_at": _iso(now),
        "marks": marks,
    }
    _hist(t, now, "enrolled", by=enrolled_by)
    return t


def eligible(room: Dict[str, Any], now: Any, first_run: bool) -> Tuple[bool, str]:
    """(True, "eligible") or (False, reason). Reasons: ``no_proposal``
    (scope: only rooms linked to one of Lorenzo's proposals), ``has_contract``
    (any contract, any status: a past or current client), ``offer_contract_started``,
    ``blocked`` (the room is blocked on Upwork: never enrolled, not even by
    ``--enroll``, while it is), ``no_client_message``, ``revivable`` (last client
    message more than 45 CT days old at the first run, or 60 or more at a later
    run: the age at which ``_transitions`` would make the new thread dormant in
    the same run)."""
    now = _now(now)
    if not room.get("proposal_id"):
        return False, "no_proposal"
    if _contract_status(room):
        return False, "has_contract"
    if room.get("offer_state") == "contract_started":
        return False, "offer_contract_started"
    if room.get("blocked"):
        return False, "blocked"
    last_client = _last_client_at(room)
    if last_client is None:
        return False, "no_client_message"
    age = (_ct_date(now) - _ct_date(last_client)).days
    if (age > REVIVE_DAYS) if first_run else (age >= DORMANT_DAYS):
        return False, "revivable"
    return True, "eligible"


# ------------------------------------------------------------- advance
class _Answers(object):
    """What ``run`` hands ``advance`` instead of the bare classifier, so each
    answer is tied to the message it was given for."""

    def answer(self, m: Dict[str, Any], room: Dict[str, Any]) -> Any:
        raise NotImplementedError


class _Recorder(_Answers):
    """``run``'s unlocked pass: asks the real classifier (the model, on a
    --run) and keeps each answer with its message id and text, in order."""

    def __init__(self, classify):
        self.classify = classify
        self.calls = []  # type: List[Tuple[str, str, Any]]

    def answer(self, m, room):
        text = m.get("text") or ""
        res = self.classify(text, room)
        self.calls.append((_msg_id(m), text, copy.deepcopy(res)))
        return res


class _Replay(_Answers):
    """``run``'s write, inside the thread's store.mutate: the unlocked pass's
    answers for the same messages in the same order. It never calls the
    classifier; any other question raises ThreadChanged."""

    def __init__(self, calls):
        self.calls = calls
        self.used = 0

    def answer(self, m, room):
        mid, text = _msg_id(m), m.get("text") or ""
        if self.used >= len(self.calls):
            raise ThreadChanged(NEW_MESSAGES, "message %s was not classified before the write" % mid)
        want_mid, want_text, res = self.calls[self.used]
        if (want_mid, want_text) != (mid, text):
            raise ThreadChanged(MESSAGE_IDS_CHANGED, "message %s read where %s was classified" % (mid, want_mid))
        self.used += 1
        return copy.deepcopy(res)

    def check_all_read(self):
        if self.used != len(self.calls):
            raise ThreadChanged(MESSAGE_IDS_CHANGED, "%d of the %d classified messages were read"
                                % (self.used, len(self.calls)))


def _classify_burst(burst, room, classify, acts):
    """Newest first until a non-machine label. Returns (message, result) or (None, None)."""
    for m in reversed(burst):
        if isinstance(classify, _Answers):
            res = classify.answer(m, room) or {}
        else:
            res = classify(m.get("text") or "", room) or {}
        label = res.get("label")
        acts.append({"type": "classified", "message_id": _msg_id(m), "label": label,
                     "confidence": res.get("confidence")})
        if label != MACHINE:
            return m, res
    return None, None


def _note_client(t, m):
    marks = t["marks"]
    at = _dt(m.get("at"))
    prev = _dt(marks.get("last_client_at"))
    if at and (prev is None or at > prev):
        marks["last_client_at"] = _iso(at)
    marks["reply_target"] = _msg_id(m)
    marks["client_waiting"] = True


def _end_silence(t, now, counted, mid):
    """A client message ends the silence: ``touch_index`` 0, no silence clock.
    When ``counted`` and a silence was running, it also completes a cycle and
    writes ``silence_ended {cycles, message_id}``, one of the entries draft.py
    reads as the start of a new silence (``SILENCE_BOUNDARIES``)."""
    if counted and t.get("silence_started_at"):
        t["cycles"] = int(t.get("cycles") or 0) + 1
        _hist(t, now, "silence_ended", cycles=t["cycles"], message_id=mid)
    t["touch_index"] = 0
    t["silence_started_at"] = None


def _on_client_burst(t, burst, room, now, classify, acts, enrolling):
    status = t["status"]
    if status == CLOSED:
        # A block closed it: only a real message written after the block
        # reopens it, through the path its pre-block status would have taken.
        since = _dt(t["marks"].get("blocked_at"))
        burst = [b for b in burst if since is None or (_dt(b.get("at")) or since) > since]
        if not burst:
            return
    latest = burst[-1]
    m, res = _classify_burst(burst, room, classify, acts)
    if m is None:
        _hist(t, now, "machine_ignored", message_id=_msg_id(latest))
        return
    label = res.get("label")
    mid = _msg_id(m)
    if res.get("raw_label"):
        acts.append({"type": "needs_review", "reason": "low_confidence", "label": label,
                     "raw_label": res.get("raw_label"), "confidence": res.get("confidence"),
                     "message_id": mid})
    if status == CLOSED:
        status = _reopen(t, now, acts)
    elif status == STOPPED and isinstance(t["marks"].get("pre_block"), dict):
        # stopped while closed, and the room opened before a run closed it
        # again: the block's stage move is undone the same way
        pre = t["marks"]["pre_block"]
        t["marks"]["pre_block"] = None
        t["marks"]["blocked_at"] = None
        _restore_stage(t, pre, now, acts)
    if status in (STOPPED, LOST):
        # Lorenzo stopped it, or it is lost: the label moves nothing here. It
        # only drops machine text (above), so an out-of-office never becomes a
        # waiting client message. A real message still ends the silence
        # (draft.py must not list the old touches as the current silence once
        # a resume or a stage move answers it) and stays the reply target.
        _end_silence(t, now, not enrolling, mid)
        _note_client(t, m)
        if status == LOST:
            acts.append({"type": "needs_review", "reason": "client_wrote_after_lost", "message_id": mid})
        _hist(t, now, "client_message_while_%s" % status, message_id=mid, label=label)
        return
    # a client reply ends the silence
    _end_silence(t, now, status == ACTIVE and not enrolling, mid)
    _note_client(t, m)
    _withdraw(t, now, acts, "client_replied" if status != AWAITING else "client_wrote_again")
    _hist(t, now, "client_reply", message_id=mid, label=label)

    # Lorenzo (or GHL) holds a drafting stage: no label stops drafting.
    manual_drafting = _manual_stage(t) and t.get("stage") in DRAFTING_STAGES
    if label == NOT_NOW:
        t["follow_up_at"] = _future_follow_up(res.get("follow_up_at"), now)
        if manual_drafting:
            _label_stage(t, "follow_up_later", now, acts, label, mid)
        else:
            _set_status(t, PAUSED, now, acts, NOT_NOW)
            _label_stage(t, "follow_up_later", now, acts, label, mid)
            return
    elif label in LOST_LABELS:
        if manual_drafting:
            _label_stage(t, "lost", now, acts, label, mid)
        else:
            t["stop_reason"] = label
            _set_status(t, LOST, now, acts, label)
            _label_stage(t, "lost", now, acts, label, mid)
            return
    elif label not in REPLY_LABELS:
        acts.append({"type": "needs_review", "reason": "unrecognised_label", "label": label,
                     "message_id": mid})
    _set_status(t, AWAITING, now, acts, label if label in LABELS else "unrecognised_label")
    if t.get("stage") in ("lost", "follow_up_later"):
        _engine_stage(t, "new_reply", now, acts, "client_replied")


def _on_freelancer(t, m, now, acts):
    t["marks"]["client_waiting"] = False
    p = t.get("pending")
    at = _dt(m.get("at"))
    issued = _dt(p.get("issued_at")) if p else None
    if p and at and issued and at > issued:
        t["pending"] = None
        acts.append({"type": "sent_detected", "kind": p.get("kind"), "touch": p.get("touch"),
                     "message_id": _msg_id(m)})
        text = _cap(m.get("text") if m.get("text") not in (None, "") else p.get("text"))
        _hist(t, at, "%s_sent" % p.get("kind"), message_id=_msg_id(m), text=text,
              **({"touch": p.get("touch")} if p.get("kind") == "touch" else {}))
        if p.get("kind") == "touch":
            nxt = p.get("touch") or (int(t.get("touch_index") or 0) + 1)
            t["touch_index"] = min(LAST_TOUCH, max(int(t.get("touch_index") or 0), int(nxt)))
            t["silence_started_at"] = _iso(at)
            _set_status(t, ACTIVE, now, acts, "touch_sent")
        else:
            if p.get("kind") == "checkin":
                t["follow_up_at"] = None
            t["touch_index"] = 0
            t["silence_started_at"] = _iso(at)
            _set_status(t, ACTIVE, now, acts, "%s_sent" % p.get("kind"))
        return
    status = t["status"]
    if status == AWAITING:
        # Lorenzo answered by hand: a new silence starts at touch 1, and a
        # reply draft issued after his message is now void
        _withdraw(t, now, acts, "lorenzo_answered", redraft=False)
        _hist(t, at or now, "reply_sent", message_id=_msg_id(m), text=_cap(m.get("text")), manual=True)
        t["marks"]["reply_for"] = t["marks"].get("reply_target")
        t["touch_index"] = 0
        t["silence_started_at"] = _iso(at)
        _set_status(t, ACTIVE, now, acts, "lorenzo_answered")
    elif status == ACTIVE:
        # the silence runs from Lorenzo's latest message; not a counted touch
        t["silence_started_at"] = _iso(at)
        _hist(t, at or now, "manual_message", message_id=_msg_id(m), text=_cap(m.get("text")))


def _process(t, new_msgs, room, now, classify, acts, enrolling=False):
    i = 0
    while i < len(new_msgs):
        m = new_msgs[i]
        side = _side(m)
        if side == CLIENT:
            j = i
            while j + 1 < len(new_msgs) and _side(new_msgs[j + 1]) == CLIENT:
                j += 1
            burst = new_msgs[i:j + 1]
            _on_client_burst(t, burst, room, now, classify, acts, enrolling)
            for b in burst:
                _seen(t, b)
            i = j + 1
            continue
        if side == FREELANCER:
            _on_freelancer(t, m, now, acts)
        # unknown side (room events, unattributable lines): never a send,
        # never a client reply
        _seen(t, m)
        i += 1


def _init(t, room, now, classify, acts):
    msgs = _messages(room)
    last_f = None
    for i, m in enumerate(msgs):
        if _side(m) == FREELANCER:
            last_f = i
    before = msgs[:last_f + 1] if last_f is not None else []
    tail = msgs[last_f + 1:] if last_f is not None else msgs
    client_before = [m for m in before if _side(m) == CLIENT]
    if client_before:
        t["marks"]["last_client_at"] = _iso(client_before[-1].get("at"))
    if last_f is not None:
        t["silence_started_at"] = _iso(msgs[last_f].get("at"))
        _seen(t, msgs[last_f])
    t["marks"]["initialized"] = True
    if t.get("stage") == "new_reply" and t.get("stage_set_by") == "engine":
        acts.append({"type": "stage_change", "from": None, "to": "new_reply", "by": "engine",
                     "reason": "enrolled"})
        acts.append({"type": "ghl_stage", "stage": "new_reply", "by": "engine"})
    _process(t, tail, room, now, classify, acts, enrolling=True)
    if not t["marks"].get("last_client_at"):
        lc = _last_client_at(room)
        t["marks"]["last_client_at"] = _iso(lc) if lc else None


def _is_placeholder(p) -> bool:
    return p.get("text") is None and p.get("card_id") is None


def _pending_lifecycle(t, now, acts):
    p = t.get("pending")
    if not p:
        return
    issued = _dt(p.get("issued_at")) or now
    if _is_placeholder(p):
        # a reservation the orchestrator never filled (a crashed tick): never
        # resurfaced or skipped; released so the draft is emitted again
        if now > issued:
            t["pending"] = None
            _undo_marks(t, p)
            _hist(t, now, "reservation_released", kind=p.get("kind"), touch=p.get("touch"))
        return
    if now >= _day_due(issued, SKIP_DAYS):
        _withdraw(t, now, acts, "skipped", redraft=False)
        kind = p.get("kind")
        if kind == "touch":
            t["touch_index"] = min(LAST_TOUCH, max(int(t.get("touch_index") or 0), int(p.get("touch") or 0)))
            t["silence_started_at"] = _iso(now)  # the next touch counts from the drop
        elif kind == "checkin":
            t["follow_up_at"] = None
            _revive(t, now, acts, "checkin_skipped")
        elif kind == "reply" and t["status"] == AWAITING:
            # The reply expired unsent (nobody said no to it): the client is
            # still waiting, so it never goes quiet. A fresh reply is drafted
            # once more (this run: it is due again at once). If that one
            # expires too, no more redrafts: due_summary kind "reply_skipped"
            # keeps it in the batch until Lorenzo answers, resumes, stops or
            # moves it, or the client writes again (a new reply is due then).
            if _reply_skip_count(t) < REPLY_REDRAFTS:
                _note_reply_skip(t, now, redraft=True)
            else:
                _note_reply_skip(t, now, redraft=False)
                acts.append({"type": "needs_review", "reason": "reply_skipped",
                             "message_id": t["marks"].get("reply_target"), "skipped_at": _iso(now),
                             "waiting_since": t["marks"].get("last_client_at")})
        return
    if now >= _day_due(issued, RESURFACE_DAYS) and not p.get("resurfaced_at"):
        p["resurfaced_at"] = _iso(now)
        acts.append({"type": "resurface", "pending": copy.deepcopy(p)})
        _hist(t, now, "resurfaced", kind=p.get("kind"), touch=p.get("touch"))


def _transitions(t, now, acts):
    status = t["status"]
    silence = _dt(t.get("silence_started_at"))
    if status == ACTIVE and silence and int(t.get("touch_index") or 0) >= LAST_TOUCH:
        if int(t.get("cycles") or 0) >= MAX_CYCLES:
            reason = "max_cycles"
        elif now >= _day_due(silence, CLOSE_OUT_WAIT_DAYS):
            reason = "no_answer_after_t7"
        else:
            reason = None
        if reason:
            _withdraw(t, now, acts, reason)
            _set_status(t, CLOSED_OUT, now, acts, reason)
            _engine_stage(t, "lost", now, acts, CLOSED_OUT)
            return
    if t["status"] in LIVE_STATUSES:
        anchors = [_dt(t["marks"].get("last_client_at")), _dt(t["marks"].get("dormant_floor"))]
        fu = t.get("follow_up_at")
        # A follow-up date holds the clock while the thread waits for it, and
        # while its check-in is out: the check-in return moves the stage off
        # follow_up_later AFTER this check, so a same-time second run must
        # still see the date (checkin_for), or it would make the thread dormant.
        if t["status"] == PAUSED or t.get("stage") == "follow_up_later" or \
                (fu and t["marks"].get("checkin_for") == fu):
            anchors.append(_dt(fu))
        anchors = [a for a in anchors if a]
        if anchors and now >= _day_due(max(anchors), DORMANT_DAYS):
            _withdraw(t, now, acts, DORMANT)
            _set_status(t, DORMANT, now, acts, "no_client_message_60_days")
            _engine_stage(t, "lost", now, acts, DORMANT)


def due_summary(thread: Dict[str, Any], now: Any) -> Dict[str, Any]:
    """What the morning batch needs for one thread.

    ``{"stage", "status", "draft_now", "kind", "touch", "next_due_at",
    "pending", "hold", "waiting_since", "skipped_at"}``. ``kind`` is ``touch``
    / ``reply`` / ``checkin`` / ``close_out`` (T7 sent, waiting out the 14
    days) / ``reply_skipped`` (the client wrote last and the reply drafted for
    that message was dropped unsent with no redraft coming: it expired twice,
    or was cleared without retry; ``draft_now`` False, ``next_due_at`` None;
    ``--resume`` asks for it again) or None.
    ``next_due_at`` is 00:00 CT of the due day, as UTC ISO. ``draft_now`` is
    True only in a stage that may draft, with a live status, nothing pending,
    no hold, when the draft is due. ``hold`` comes from the last ``advance``.
    ``waiting_since`` (``awaiting_lorenzo`` only) is the client's latest
    message time; ``skipped_at`` (kind ``reply_skipped`` only) is when that
    reply was last dropped. Both UTC ISO or None.
    """
    now = _now(now)
    t = _ensure(copy.deepcopy(thread))
    marks = t["marks"]
    stage, status, p = t.get("stage"), t.get("status"), t.get("pending")
    out = {"stage": stage, "status": status, "draft_now": False, "kind": None, "touch": None,
           "next_due_at": None, "pending": bool(p), "hold": bool(marks.get("hold")),
           "waiting_since": marks.get("last_client_at") if status == AWAITING else None, "skipped_at": None}
    if status not in LIVE_STATUSES:
        return out
    if p:
        out["kind"], out["touch"] = p.get("kind"), p.get("touch")
        return out
    checkin_stage = stage == "follow_up_later" or (stage in DRAFTING_STAGES and status == PAUSED)
    if checkin_stage:
        fu = t.get("follow_up_at")
        if not fu or marks.get("checkin_for") == fu:
            return out
        due = _dt(fu)
        out.update(kind="checkin", next_due_at=_iso(due), draft_now=now >= due)
    elif stage not in DRAFTING_STAGES:
        return out
    elif status == AWAITING:
        target = marks.get("reply_target")
        if target and marks.get("reply_for") != target:
            out.update(kind="reply", next_due_at=marks.get("last_client_at") or _iso(now), draft_now=True)
        elif target:
            rec = marks.get("reply_skipped")
            out.update(kind="reply_skipped", skipped_at=rec.get("at") if isinstance(rec, dict)
                       and rec.get("message_id") == target else None)
    elif status == ACTIVE:
        silence = _dt(t.get("silence_started_at"))
        if silence is None:
            return out
        idx = int(t.get("touch_index") or 0)
        if idx < LAST_TOUCH:
            due = _day_due(silence, GAPS[idx + 1])
            out.update(kind="touch", touch=idx + 1, next_due_at=_iso(due), draft_now=now >= due)
        else:
            wait = 0 if int(t.get("cycles") or 0) >= MAX_CYCLES else CLOSE_OUT_WAIT_DAYS
            out.update(kind="close_out", next_due_at=_iso(_day_due(silence, wait) if wait else silence))
    if out["hold"]:
        out["draft_now"] = False
    return out


def _draft_action(t, s):
    if s["kind"] == "touch":
        return {"type": "draft_touch", "touch": s["touch"]}
    if s["kind"] == "reply":
        return {"type": "draft_reply", "message_id": t["marks"].get("reply_target")}
    if s["kind"] == "checkin":
        return {"type": "draft_checkin", "follow_up_at": t.get("follow_up_at")}
    return None


def _reserve(t, kind, touch, now):
    """Write the placeholder pending (text/card_id null) for a draft action."""
    t["pending"] = {"kind": kind, "touch": touch if kind == "touch" else None,
                    "issued_at": _iso(now), "text": None, "card_id": None, "resurfaced_at": None}
    if kind == "reply":
        t["marks"]["reply_for"] = t["marks"].get("reply_target")
    elif kind == "checkin":
        t["marks"]["checkin_for"] = t.get("follow_up_at")
    _hist(t, now, "draft_reserved", kind=kind, touch=t["pending"]["touch"])


def advance(thread: Dict[str, Any], room: Dict[str, Any], now: Any,
            classify: Callable[[str, Dict[str, Any]], Dict[str, Any]],
            allow_draft: bool = True) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Advance one thread against its room. Returns (new thread, actions).

    Pure: the input thread is not modified. ``allow_draft=False`` turns a due
    draft into ``{"type": "deferred"}`` without reserving it (the run cap)."""
    now = _now(now)
    t = _ensure(copy.deepcopy(thread))
    acts = []  # type: List[Dict[str, Any]]
    msgs = _messages(room)
    _sync_ids(t, room, now)

    # Won from a real contract beats every stage, whoever set it.
    won = _room_won(room)
    if won:
        _mark_won(t, now, acts, won)
        for m in _new_messages(t, msgs):
            _seen(t, m)
        t["marks"]["initialized"] = True
        return t, acts
    if t["status"] == WON:
        for m in _new_messages(t, msgs):
            _seen(t, m)
        return t, acts

    # Blocked on Upwork: closed on first sight, then nothing moves (no
    # message is read, no ladder step, no draft) until the room is open again.
    if room.get("blocked"):
        if t["status"] != CLOSED:
            _close_blocked(t, room, now, acts)
        return t, acts

    if not t["marks"].get("initialized"):
        _init(t, room, now, classify, acts)
    else:
        _process(t, _new_messages(t, msgs), room, now, classify, acts)

    # An unknown last_side: never a send; hold drafts, surface once. Room
    # events never set last_side (collect.py), so they do not hold a thread.
    hold = room.get("last_side") == "unknown"
    t["marks"]["hold"] = bool(hold)
    if hold:
        lid = "last_side_unknown@%s" % (room.get("last_message_at") or "")
        if t["marks"].get("review_for") != lid:
            t["marks"]["review_for"] = lid
            acts.append({"type": "needs_review", "reason": "unknown_last_message",
                         "last_message_at": room.get("last_message_at")})
            _hist(t, now, "needs_review", reason="unknown_last_message")

    _pending_lifecycle(t, now, acts)
    _transitions(t, now, acts)

    # Stage moves, in the only order that is a fixed point: every step below
    # reads what the steps above left, and none of them re-enables a step
    # above it, so a second run at the same time finds nothing to do.
    # 1. The check-in return (follow_up_later -> new_reply, DESIGN "one
    #    check-in, then the stage returns to new_reply").
    # 2. The offer promotion (new_reply -> proposal_sent). It must come after
    #    1: before it, a check-in return to new_reply would be promoted only by
    #    the NEXT run. It also comes after _transitions, so a thread that just
    #    went dormant or closed out is not promoted on its way to lost.
    # Neither move changes what is due (both drafting stages draft alike).
    s = due_summary(t, now)
    action = _draft_action(t, s) if s["draft_now"] else None
    if action is not None and allow_draft and s["kind"] == "checkin" and t.get("stage") == "follow_up_later":
        _move_stage(t, "new_reply", now, "engine", acts, "checkin_due", force=True)
    if room.get("offer_state") == "awaiting_your_acceptance" and t.get("stage") == "new_reply" \
            and t["status"] in LIVE_STATUSES:
        _engine_stage(t, "proposal_sent", now, acts, "offer_awaiting_acceptance")
    if action is not None:
        if not allow_draft:
            acts.append({"type": "deferred", "draft": action})
        else:
            _reserve(t, s["kind"], s["touch"], now)
            acts.append(action)
    return t, acts


# ------------------------------------------------------- pending helpers
def record_pending(thread: Dict[str, Any], kind: str, touch: Optional[int], text: Optional[str],
                   now: Any, card_id: Optional[str]) -> Dict[str, Any]:
    """Fill the reserved pending draft with its text and card id. Returns a new
    thread. Call it inside ``store.mutate`` so a refusal writes nothing.

    Raises ``PendingRefused`` (``.reason``) unless a matching reservation
    exists (same kind and touch), the stage is a drafting stage and the status
    is live. ``issued_at`` stays the reservation's time, so a send made after
    the reservation is still detected."""
    if kind not in PENDING_KINDS:
        raise ValueError("kind must be one of %s" % (", ".join(PENDING_KINDS),))
    now = _now(now)
    t = _ensure(copy.deepcopy(thread))
    cur = t.get("pending")
    if not cur:
        raise PendingRefused("no_reservation", str(t.get("room_id")))
    if cur.get("kind") != kind or cur.get("touch") != (touch if kind == "touch" else None):
        raise PendingRefused("reservation_mismatch", "reserved %s/%s" % (cur.get("kind"), cur.get("touch")))
    if t.get("stage") not in DRAFTING_STAGES:
        raise PendingRefused("stage_not_drafting", str(t.get("stage")))
    if t.get("status") not in LIVE_STATUSES:
        raise PendingRefused("status_not_live", str(t.get("status")))
    cur["text"] = text
    cur["card_id"] = card_id
    _hist(t, now, "drafted", kind=kind, touch=cur.get("touch"), card_id=card_id)
    return t


def clear_pending(thread: Dict[str, Any], now: Any, reason: str = "cleared",
                  retry: bool = False) -> Dict[str, Any]:
    """Drop the pending draft. ``retry=True`` (drafting failed, or the run's
    budget ran out) lets the next run draft the same reply or check-in again;
    a touch is always re-derived from the ladder. ``retry=False`` drops it on
    purpose: a dropped reply is a skip (``reply_skipped``, no redraft), and the
    waiting client stays visible (``due_summary`` kind ``reply_skipped``)."""
    now = _now(now)
    t = _ensure(copy.deepcopy(thread))
    p = t.get("pending")
    _withdraw(t, now, [], reason, redraft=retry)
    if p and p.get("kind") == "reply" and not retry and t["status"] == AWAITING:
        _note_reply_skip(t, now, redraft=False)
    return t


# --------------------------------------------------------------- stages
def _apply_manual_stage(thread, stage, now, by):
    if stage not in STAGES:
        raise ValueError("unknown stage %r (one of %s)" % (stage, ", ".join(STAGES)))
    if by not in MANUAL_SETTERS:
        raise ValueError("by must be one of %s" % (", ".join(MANUAL_SETTERS),))
    now = _now(now)
    t = _ensure(copy.deepcopy(thread))
    acts = []  # type: List[Dict[str, Any]]
    was_drafting = t.get("stage") in DRAFTING_STAGES
    was = (t.get("stage"), t.get("stage_set_by"))
    pre = t["marks"].get("pre_block") if isinstance(t["marks"].get("pre_block"), dict) else None
    moved = _move_stage(t, stage, now, by, acts, "set_by_" + by, force=True)
    # The block itself moved the stage to lost: his lost on it is still his
    # decision (status lost), not a no-op pin of the block's move.
    block_lost = stage == "lost" and was == ("lost", "engine") and pre is not None \
        and (pre.get("stage"), pre.get("set_by")) != ("lost", "engine")
    if not moved and not block_lost:
        return t, acts
    reason = "stage_set_by_" + by
    if stage in ("won", "lost", "follow_up_later"):
        # his stage now decides the status, not a block (a drafting stage
        # clears the record in _revive); a later block records afresh
        t["marks"]["pre_block"] = None
    if stage == "won":
        _set_status(t, WON, now, acts, reason)
    elif stage == "lost":
        t["stop_reason"] = reason
        _set_status(t, LOST, now, acts, reason)
    elif stage == "follow_up_later":
        # always paused: exactly one check-in on follow_up_at, no close-out meanwhile
        fu = t.get("follow_up_at")
        if not fu or fu <= _ct_day_str(_ct_date(now)) or t["marks"].get("checkin_for") == fu:
            t["follow_up_at"] = _ct_day_str(_ct_date(now) + timedelta(days=NOT_NOW_DEFAULT_DAYS))
        t["marks"]["checkin_for"] = None
        t["stop_reason"] = None
        t["marks"]["dormant_floor"] = _iso(now)
        _set_status(t, PAUSED, now, acts, reason)
    elif stage in DRAFTING_STAGES:
        if t["status"] in RESTING_STATUSES:
            _revive(t, now, acts, reason)
        elif t["status"] == ACTIVE and not was_drafting and t.get("silence_started_at"):
            t["silence_started_at"] = _iso(now)  # the next touch counts from the move
    return t, acts


def apply_external_stage(thread: Dict[str, Any], stage: str, now: Any) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """A stage read back from GHL. It wins like a CLI move and never produces a
    ``ghl_stage`` action. The same stage as the thread's is a no-op (that is
    our own mirror push coming back)."""
    now = _now(now)
    if stage not in STAGES:
        raise ValueError("unknown stage %r (one of %s)" % (stage, ", ".join(STAGES)))
    t = _ensure(copy.deepcopy(thread))
    if t.get("stage") == stage:
        return t, []
    return _apply_manual_stage(t, stage, now, "ghl")


# ------------------------------------------------------------- CLI helpers
def _mutate_existing(store, room_id, fn):
    box = {}

    def wrap(cur):
        if cur is None:
            raise ThreadNotFound("no thread for room %s" % room_id)
        new, acts = fn(cur)
        box["acts"] = acts
        return new

    thread = store.mutate(thread_key(room_id), wrap)
    return thread, box.get("acts", [])


def set_stage(store, room_id: str, stage: str, now: Any, by: str = "lorenzo"):
    """``--stage``: move a thread's stage. Returns (thread, actions)."""
    now = _now(now)
    if stage not in STAGES:
        raise ValueError("unknown stage %r (one of %s)" % (stage, ", ".join(STAGES)))
    if by not in MANUAL_SETTERS:
        raise ValueError("by must be one of %s" % (", ".join(MANUAL_SETTERS),))
    return _mutate_existing(store, room_id, lambda cur: _apply_manual_stage(cur, stage, now, by))


def stop(store, room_id: str, now: Any, reason: str = "stopped_by_lorenzo"):
    """``--stop``: status ``stopped``, pending withdrawn. Returns (thread, actions)."""
    now = _now(now)

    def fn(cur):
        t = _ensure(copy.deepcopy(cur))
        acts = []
        _withdraw(t, now, acts, "stopped")
        t["stop_reason"] = reason
        _set_status(t, STOPPED, now, acts, reason)
        return t, acts

    return _mutate_existing(store, room_id, fn)


def resume(store, room_id: str, now: Any):
    """``--resume``: a fresh silence from ``now`` (or a reply draft when the
    client wrote last and is still waiting). A non-drafting stage goes back
    to ``new_reply`` as Lorenzo's move. On an ``awaiting_lorenzo`` thread whose
    reply was skipped (``due_summary`` kind ``reply_skipped``) it asks for that
    reply again: the next run drafts it."""
    now = _now(now)

    def fn(cur):
        t = _ensure(copy.deepcopy(cur))
        if _reply_skipped(t):
            acts = []
            if t.get("stage") not in DRAFTING_STAGES:
                _move_stage(t, "new_reply", now, "lorenzo", acts, "resumed", force=True)
            t["marks"]["reply_for"] = None
            _hist(t, now, "reply_resumed", message_id=t["marks"].get("reply_target"))
            return t, acts
        if t["status"] in (WON, ACTIVE, AWAITING):
            raise ValueError("thread %s is %s; nothing to resume" % (room_id, t["status"]))
        acts = []
        _withdraw(t, now, acts, "resumed")
        if t.get("stage") not in DRAFTING_STAGES:
            _move_stage(t, "new_reply", now, "lorenzo", acts, "resumed", force=True)
        _revive(t, now, acts, "resumed")
        return t, acts

    return _mutate_existing(store, room_id, fn)


def _drop_revivable(store, room_id):
    def drop(meta):
        meta = dict(meta or {})
        rev = dict(meta.get("revivable") or {})
        rev.pop(room_id, None)
        meta["revivable"] = rev
        return meta
    store.mutate(META_KEY, drop)


def enroll(store, room: Dict[str, Any], now: Any):
    """``--enroll``: enrol one room by hand (typically a revivable one).
    The age rule is waived; scope, contract and client-message rules are not.
    Returns (thread, actions). The next run reads its history. It never sets
    ``first_run_at``, so enrolling before the first tick keeps first-run
    detection intact."""
    now = _now(now)
    ok, reason = eligible(room, now, first_run=False)
    if not ok and reason != "revivable":
        raise ValueError("room %s cannot be enrolled: %s" % (room.get("room_id"), reason))
    room_id = room.get("room_id")

    def fn(cur):
        if cur is not None:
            raise ValueError("room %s already has a thread" % room_id)
        return new_thread(room, now, "manual")

    thread = store.mutate(thread_key(room_id), fn)
    _drop_revivable(store, room_id)
    return thread, [{"type": "enrolled", "by": "manual"}]


# ------------------------------------------------------------------ run
def _priority(thread, room):
    """Sort key: client waiting for a reply first, then the oldest silence.
    A thread that has not read its room yet (a manual enrol) sorts like a new room."""
    msgs = _messages(room)
    far = float("inf")

    def ts(value):
        d = _dt(value)
        return d.timestamp() if d else far

    t = _ensure(copy.deepcopy(thread)) if thread is not None else None
    if t is None or not t["marks"].get("initialized"):
        last = next((m for m in reversed(msgs) if _side(m) != "unknown"), None)
        if last is not None and _side(last) == CLIENT:
            return (0, ts(last.get("at")))
        lf = next((m for m in reversed(msgs) if _side(m) == FREELANCER), None)
        return (1, ts(lf.get("at")) if lf else far)
    new_client = [m for m in _new_messages(t, msgs) if _side(m) == CLIENT]
    if new_client:
        return (0, ts(new_client[-1].get("at")))
    if t["status"] == AWAITING:
        return (0, ts(t["marks"].get("last_client_at")))
    if t["status"] == PAUSED or t.get("stage") == "follow_up_later":
        return (1, ts(t.get("follow_up_at")))
    if t["status"] == ACTIVE:
        return (1, ts(t.get("silence_started_at")))
    return (2, far)


def _error(exc):
    return {"type": "error", "error": str(exc), "error_type": type(exc).__name__}


def _load_meta(store, now, first_run):
    """(meta, first_run, meta_ok). Migrates a legacy ``upwork:meta``. First run
    = no ``first_run_at`` yet and no auto-enrolled thread (manual enrols do not
    count). Any store failure: not the first run, and ``meta_ok`` False, which
    pauses enrolment for this run."""
    try:
        legacy = store.get(LEGACY_META_KEY)
        if legacy is not None:
            if isinstance(legacy, dict):
                def merge(cur, legacy=legacy):
                    m = dict(legacy)
                    m.update(dict(cur or {}))
                    rev = dict(legacy.get("revivable") or {})
                    rev.update(dict((cur or {}).get("revivable") or {}))
                    m["revivable"] = rev
                    return m
                store.mutate(META_KEY, merge)
            store.delete(LEGACY_META_KEY)
        meta = store.get(META_KEY)
        if meta is not None and not isinstance(meta, dict):
            raise BadRecord("meta record is %s" % type(meta).__name__)
        meta = dict(meta or {})
        if first_run is None:
            first_run = not meta.get("first_run_at")
            if first_run:
                for k in store.keys(PREFIX):
                    v = store.get(k)
                    if not isinstance(v, dict) or v.get("enrolled_by") != "manual":
                        first_run = False
                        break

        def init(cur):
            m = dict(cur or {})
            m.setdefault("first_run_at", _iso(now))
            m.setdefault("revivable", {})
            return m

        meta = store.mutate(META_KEY, init)
        return meta, bool(first_run), True
    except Exception:  # noqa: BLE001 - degrade: never mass-enrol, never abort
        return {"revivable": {}}, False, False


def run(store, snapshot: Dict[str, Any], now: Any,
        classify: Callable[[str, Dict[str, Any]], Dict[str, Any]],
        first_run: Optional[bool] = None) -> List[Tuple[Dict[str, Any], Optional[Dict[str, Any]], List[Dict[str, Any]]]]:
    """Advance every snapshot room. Returns [(room, thread or None, actions)].

    * One ``store.mutate`` per thread key. A failure on one room (store error,
      corrupt record, classifier error) is that room's ``error`` action.
    * ``classify`` is never called inside a mutate. Per room: read the thread
      without a lock, run its step on that copy with ``classify`` (no lock is
      held, so the model call and its spend counter can use the store), then
      run the same step inside the thread's ``store.mutate`` on those answers.
      When the write reads other client messages than the ones classified,
      nothing is written and the room gets ``room_deferred`` (next run).
    * At most ``MAX_NEW_DRAFTS_PER_RUN`` drafts are reserved; replies first,
      then the oldest silence; the rest come back ``deferred``.
    * ``snapshot["contracted_rooms"]``: every enrolled thread listed there is
      marked won (engine move, pending withdrawn). Its result's "room" is the
      contracted entry.
    * ``snapshot["missing_messages"]`` or ``messages: null``: only those rooms
      are frozen (``needs_review`` once). ``sections.messages`` is not read.
    * A live thread missing from both lists is left alone except for a
      ``needs_review`` ``not_in_pull`` at most once per 7 CT days; its result's
      "room" is ``{"room_id": ..., "not_in_snapshot": True}``.
    * If the meta record cannot be read or written, the run treats itself as
      not the first run and enrols nobody (``MetaUnavailable`` error actions);
      existing threads still advance."""
    now = _now(now)
    meta, first_run, meta_ok = _load_meta(store, now, first_run)
    revivable = meta.get("revivable") or {}
    results = []
    work = []
    blocked_ids = set(b for b in (snapshot.get("blocked_rooms") or []) if isinstance(b, str))
    rooms = [r if r.get("blocked") or r.get("room_id") not in blocked_ids else dict(r, blocked=True)
             for r in (snapshot.get("rooms") or []) if isinstance(r, dict) and r.get("room_id")]
    contracted = [c for c in (snapshot.get("contracted_rooms") or []) if isinstance(c, dict) and c.get("room_id")]

    for idx, room in enumerate(rooms):
        rid = room["room_id"]
        try:
            existing = store.get(thread_key(rid))
            if existing is not None and not isinstance(existing, dict):
                raise BadRecord("stored thread for %s is %s, not a dict" % (rid, type(existing).__name__))
            if existing is None:
                if _messages_frozen(room, snapshot):
                    continue
                listed = revivable.get(rid)
                if listed:
                    lc = _last_client_at(room)
                    if lc is None or lc <= (_dt(listed.get("listed_at")) or now):
                        continue  # still revivable; only --enroll or a new client message brings it in
                ok, reason = eligible(room, now, first_run)
                if not ok:
                    if reason == "revivable" and not listed and meta_ok:
                        lc = _last_client_at(room)
                        entry = {"listed_at": _iso(now), "last_client_at": _iso(lc),
                                 "client": room.get("client"), "job_title": room.get("job_title")}

                        def add(cur, rid=rid, entry=entry):
                            m = dict(cur or {})
                            rev = dict(m.get("revivable") or {})
                            rev.setdefault(rid, entry)
                            m["revivable"] = rev
                            return m

                        store.mutate(META_KEY, add)
                        results.append((room, None, [{
                            "type": "revivable",
                            "reason": ("last client message more than %d days old" % REVIVE_DAYS) if first_run
                                      else ("last client message %d or more days old" % DORMANT_DAYS),
                            "last_client_at": entry["last_client_at"]}]))
                    continue
                if not meta_ok:
                    raise MetaUnavailable("enrolment paused: the %s record could not be read or written" % META_KEY)
            work.append((_priority(existing, room), idx, room, existing is None))
        except Exception as exc:  # noqa: BLE001 - one room never stops the run
            results.append((room, None, [_error(exc)]))

    work.sort(key=lambda w: (w[0], w[1]))
    drafted = 0
    for _prio, _idx, room, enrol in work:
        rid = room["room_id"]
        box = {"acts": []}
        allow = drafted < MAX_NEW_DRAFTS_PER_RUN

        def step(cur, answers, room=room, enrol=enrol, allow=allow):
            """This room's step, pure: (thread, actions)."""
            acts = []
            if cur is None:
                if not enrol:
                    raise ThreadNotFound("thread %s vanished during the run" % room["room_id"])
                cur = new_thread(room, now, "auto")
                acts.append({"type": "enrolled", "by": "auto"})
            t = _ensure(copy.deepcopy(cur))
            if _messages_frozen(room, snapshot):
                if not t["marks"].get("messages_missing"):
                    t["marks"]["messages_missing"] = True
                    acts.append({"type": "needs_review", "reason": "messages_missing"})
                    _hist(t, now, "needs_review", reason="messages_missing")
                return t, acts
            if t["marks"].get("messages_missing"):
                t["marks"]["messages_missing"] = False
                _hist(t, now, "messages_back")
            t, more = advance(t, room, now, answers, allow_draft=allow)
            return t, acts + more

        # 1. No lock held: read the thread, run the step on that copy and ask
        #    the classifier (the model on a --run) for every message it reads.
        answers = _Recorder(classify)
        try:
            step(store.get(thread_key(rid)), answers)
        except Exception as exc:  # noqa: BLE001 - a store or classifier failure is this room's error
            results.append((room, None, [_error(exc)]))
            continue

        # 2. The write: the same step inside the thread's lock, on those answers
        #    only (no classifier, no store call while the mutate is open).
        def fn(cur, step=step, calls=answers.calls, box=box):
            replay = _Replay(calls)
            t, acts = step(cur, replay)
            replay.check_all_read()
            box["acts"] = acts
            return t

        try:
            thread = store.mutate(thread_key(rid), fn)
        except ThreadChanged as exc:
            results.append((room, None, [{"type": ROOM_DEFERRED, "reason": exc.reason, "detail": exc.detail}]))
            continue
        except Exception as exc:  # noqa: BLE001 - one thread never stops the run
            results.append((room, None, [_error(exc)]))
            continue
        if any(a.get("type") in DRAFT_TYPES for a in box["acts"]):
            drafted += 1
        results.append((room, thread, box["acts"]))

    # contracted rooms: collect.py omits them from ``rooms``
    room_ids = set(r["room_id"] for r in rooms)
    for entry in contracted:
        rid = entry["room_id"]
        if rid in room_ids:
            continue
        box = {"acts": []}
        reason = "contract_" + str(entry.get("status") or "unknown").lower()
        try:
            if store.get(thread_key(rid)) is None:
                continue  # never enrolled: nothing to do

            def won_fn(cur, box=box, reason=reason):
                t = _ensure(copy.deepcopy(cur))
                acts = []
                _mark_won(t, now, acts, reason)
                box["acts"] = acts
                return t

            thread = store.mutate(thread_key(rid), won_fn)
        except Exception as exc:  # noqa: BLE001
            results.append((entry, None, [_error(exc)]))
            continue
        results.append((entry, thread, box["acts"]))

    # live threads missing from the snapshot: surfaced, never silently frozen
    seen = room_ids | set(c["room_id"] for c in contracted)
    try:
        keys = store.keys(PREFIX)
    except Exception:  # noqa: BLE001
        keys = []
    for key in keys:
        if key == LEGACY_META_KEY:
            continue
        rid = key[len(PREFIX):]
        if rid in seen:
            continue
        pseudo = {"room_id": rid, "not_in_snapshot": True}
        try:
            cur = store.get(key)
            if not isinstance(cur, dict) or cur.get("status") not in LIVE_STATUSES:
                continue
            last = (cur.get("marks") or {}).get("not_in_pull_at")
            if last and now < _day_due(last, NOT_IN_PULL_REVIEW_DAYS):
                continue
            box = {"acts": []}

            def miss_fn(c, box=box):
                t = _ensure(copy.deepcopy(c))
                last = t["marks"].get("not_in_pull_at")
                if t["status"] in LIVE_STATUSES and (not last or now >= _day_due(last, NOT_IN_PULL_REVIEW_DAYS)):
                    t["marks"]["not_in_pull_at"] = _iso(now)
                    box["acts"] = [{"type": "needs_review", "reason": "not_in_pull",
                                    "status": t["status"], "stage": t.get("stage")}]
                    _hist(t, now, "needs_review", reason="not_in_pull")
                return t

            thread = store.mutate(key, miss_fn)
        except Exception as exc:  # noqa: BLE001
            results.append((pseudo, None, [_error(exc)]))
            continue
        if box["acts"]:
            results.append((pseudo, thread, box["acts"]))
    return results
