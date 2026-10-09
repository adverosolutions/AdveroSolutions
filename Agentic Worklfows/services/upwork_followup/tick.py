"""Upwork follow-up tick (U4): orchestration, the morning batch, cards, Job_Log.

    from services.upwork_followup.tick import run_tick
    result = run_tick(now, "dry-run")          # or "run"

One tick, in order:

1. **Snapshot.** ``collect.load_snapshot``. Missing or unreadable: an error
   result, an error batch file and a Job_Log row; nothing is drafted. Older
   than ``STALE_HOURS``: a loud warning in the batch, the cards and Job_Log,
   and the tick still runs.
2. **Sequence.** ``sequence.run(store, snapshot, now, classify)``, which also
   owns the won-by-contract rule for the snapshot's ``contracted_rooms``; the
   tick only processes the actions it returns. sequence.run classifies each
   room with no store lock held and then writes the thread on those answers
   (a thread that changed in between is ``room_deferred``: one generic note,
   the room ids in Job_Log, handled on the next run). In ``dry-run`` all of this runs on a throwaway ``JsonFileStore`` copy of the
   ``upwork:`` keys, with a deterministic classifier (machine text by rule,
   everything else ``neutral`` via ``dry_run``): no model call, and the real
   store is never written.
3. **GHL read-back** (``run`` only). ``ghl_sync.read_back_stage`` per thread;
   a stage Lorenzo set in GHL is applied with ``sequence.apply_external_stage``
   BEFORE drafting, so a job he moved to a non-drafting stage in GHL gets no
   draft this morning (the move withdraws the reservation).
4. **Drafts** (``run`` only; ``dry-run`` lists "would draft"). Each reserved
   draft goes to ``draft.draft_touch`` / ``draft_reply`` / ``draft_checkin``.
   Success: ``sequence.record_pending`` with the text and a card id, inside one
   ``store.mutate``. A model failure (``llm_error`` with no text, or an
   exception): ``sequence.clear_pending(..., retry=True)`` so the next run
   drafts again. A draft with copy-gate ``problems`` is still recorded and is
   marked "Needs edit". The tick also keeps ``thread["draft_meta"]`` (card id,
   problems, needs_you, proposes_call) so the batch can show the same flags on
   later runs, and ``thread["job_title"]`` so ``--status`` can name a job that
   has dropped out of the snapshot.
5. **GHL sync** (``run`` only). ``ghl_sync.sync_thread`` per thread, on the
   thread's FINAL stage: only its ``ghl_stage`` actions that agree with
   ``thread["stage"]`` are passed, and none when GHL itself moved the stage
   this run. ``thread["ghl"]`` is saved as sync_thread returns it (the tick
   never sets the mirrored stage itself). GHL errors are collected and never
   stop the tick. Until Lorenzo creates the Upwork pipeline (``config/ids.json``
   ``pipelines.upwork``) ghl_sync answers ``ghl_not_configured``: that is one
   note per run in the batch and Job_Log, not an error.
6. **Batch.** ``.tmp/upwork_followup/drafts_<YYYY-MM-DD>.md`` (Central date),
   written atomically on every run, grouped by stage.
7. **Cards** (``run`` only). One ``shared.notify`` card per NEW draft, one
   for a draft a killed run recorded without its card, and one summary card.
   They go through the ordinary shadow contract: in ``MODE=shadow`` notify
   records each card as a would_do and delivers nothing unless Lorenzo has set
   ``NOTIFY_SHADOW_SEND=1`` (the existing opt-in for real pushes to his own
   topic and inbox). The tick never sets that flag; the drafts file is the
   copy he always has. ntfy topics are public unless protected, so on a public
   topic the push title and body carry nothing client-derived and no local
   path ("Upwork: 1 new draft (T1)"); the full card, with the client-named
   title as its first line, rides on the email leg (``email_message``), as in
   ``jobs/upwork_rooms.py``.
8. **Job_Log.** One ``log_run("upwork_followup", status, details)`` row.
9. **Processed mark** (``run`` only, lease kept). ``TICK_KEY[PROCESSED]``
   records ``collect.snapshot_revision`` of the snapshot this run went
   through, so the watch knows whether an ingest still waits for a --run.

Idempotent: a second ``run`` on the same snapshot drafts nothing and sends no
card (the summary card is sent once per snapshot per Central day, or when
something new happened; a missing or future snapshot alerts once per Central
day); the batch file is rewritten with the same drafts shown as pending.

Guards on ``run``:

* **One run at a time.** A lease (``LOCK_KEY``: owner token, ``LOCK_TTL_MINUTES``)
  taken, renewed and released on the REAL clock (``wall_clock``, injectable as
  ``run_tick(clock=...)``), never on ``now`` (the run's --as-of). The run
  renews it (the heartbeat) before every model call (each classify and
  escalate call as well as each draft call), draft record, card and store
  write; every lease write is a compare-and-set on the owner token. A
  second run that finds a live lease returns ``status: "locked"`` and does
  nothing; a lease with no heartbeat for a TTL is taken over and noted. A run
  whose heartbeat finds another owner, or no lease, stops at once: no model
  call, draft record or card after that point, only its own unfilled
  reservations are given back (``draft_claim`` carries its token), and the
  result, the batch and Job_Log say ``lock_lost``. A lease stamped more than
  ``LOCK_DRIFT_MINUTES`` ahead of the real clock blocks for one TTL at most.
* **Spend.** A per-run model budget (``UPWORK_RUN_BUDGET_USD``, default $1.50,
  counted as shared.llm's worst-case projection per call) and a classifier cap
  (``UPWORK_RUN_MAX_CLASSIFY``, default 40); a value that is not a finite,
  non-negative number (an integer for the cap) falls back to the default, and
  a budget above ``MAX_RUN_BUDGET_USD`` ($10.00) is clamped to $10.00. Past
  either, no more calls: the remaining reservations are released for the next
  run and the batch and Job_Log say so. shared.llm's cumulative ceiling is a
  separate stop. On the laptop its counter is ``llm.spend_usd`` in the laptop
  store (``shared.store.get_store()``, ``.tmp/store.json``), shared by every
  laptop run that calls shared.llm: this tick, the scheduled retro_packet and
  list_factory, and any job run by hand. The Modal reply engine keeps its own
  counter in its Modal Dict, so resetting that one does not lift this stop.
  ``LLMBudgetExceeded`` is caught by the Meter, the reply being classified
  stays unread (never a fallback ``neutral``) and the batch names the ceiling
  and ``shared.llm.budget_status()``.
* **No store lock around a model call.** JsonFileStore holds one flock for a
  whole ``store.mutate`` and a second lock taken by the same process waits
  forever; shared.llm.complete takes it for its spend counter. So every mutate
  callback here and in sequence.py is pure, and every model call runs between
  store calls. On a --run, a renewal, a store read or a classifier call made
  while a mutate is open raises ``NestedStoreCall`` instead of hanging.
* **Snapshot from the future.** Stamped past ``collect.MAX_CLOCK_DRIFT`` (the
  ingest's own 10-minute rule): an error run with an alert.

The batch also lists, under "Needs you", every client still waiting on
Lorenzo after the reply drafted for them was dropped with no redraft coming
(``due_summary`` kind ``reply_skipped``), on every run until he acts, and,
once, the rooms the pull shows blocked on Upwork (``room["blocked"]``, the
same flag sequence.py closes a thread on; a blocked room is never drafted).
sequence.py's ``needs_review`` ``reply_skipped`` and ``room_blocked`` show
there instead of under "Check these". Either section makes the run
``attention``.

Nothing here writes to Upwork. Python 3.9.
"""
import copy
import json
import logging
import math
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from shared import llm as shared_llm
from shared import notify as notify_mod
from shared import slots
from shared.job_log import log_run
from shared.notify import notify as shared_notify
from shared.notify import topic_is_protected
from shared.paths import tmp_file
from shared.store import ABSENT, JsonFileStore, Store, StoreError, get_store

from services.upwork_followup import classify as classify_mod
from services.upwork_followup import collect, draft, ghl_sync, sequence

logger = logging.getLogger("services.upwork_followup.tick")

JOB_NAME = "upwork_followup"
MODES = ("dry-run", "run")
STALE_HOURS = 20
ROOM_URL = "https://www.upwork.com/ab/messages/rooms/%s"
BATCH_NAME = "upwork_followup/drafts_%s.md"
# ntfy caps a message at 4096 bytes; keep room for the notify banner.
CARD_MAX_BYTES = 3800
# The tick's own bookkeeping key (outside the ``upwork:`` prefix sequence owns).
TICK_KEY = "upwork_followup:tick"
# A lease so two --run ticks never overlap (a manual run during the scheduled
# one gave two cards for one touch). Owner token + TTL on the real clock,
# renewed by a heartbeat; a lease with no heartbeat for a TTL is taken over
# and noted in Job_Log.
LOCK_KEY = "upwork_followup:lock"
LOCK_TTL_MINUTES = 30
# A lease stamp further ahead of the real clock than this is a clock problem.
LOCK_DRIFT_MINUTES = 2
# The tick's claim on a reservation it is filling: {token, kind, touch,
# issued_at}. A run that loses its lease gives back only reservations that
# still carry its own token.
CLAIM_KEY = "draft_claim"
# Blocked rooms (collect.py room["blocked"]) are listed in the batch once:
# TICK_KEY[BLOCKED_LISTED] = {room_id: {blocked_at, listed_at}}.
BLOCKED_LISTED = "blocked_listed"
# The snapshot a completed --run processed: TICK_KEY[PROCESSED] =
# {"revision": collect.snapshot_revision(snapshot), "as_of"}. Written at the
# end of a --run that kept its lease; the watch (watch.py) runs --run again
# while it differs from the current snapshot's revision.
PROCESSED = "processed"
# sequence.py's stop reason for a thread whose room is blocked on Upwork.
ROOM_BLOCKED = "room_blocked"
# Per-run spend cap (worst-case projection of every model call this run) and a
# cap on classifier calls. shared.llm's cumulative ceiling still applies too.
BUDGET_ENV = "UPWORK_RUN_BUDGET_USD"
DEFAULT_RUN_BUDGET_USD = 1.50
# The most one run may project; a higher UPWORK_RUN_BUDGET_USD is clamped to it
# (config/llm_budget.json's cumulative ceiling is $10.00 as well).
MAX_RUN_BUDGET_USD = 10.00
CLASSIFY_CAP_ENV = "UPWORK_RUN_MAX_CLASSIFY"
DEFAULT_MAX_CLASSIFY = 40
# Meter.hit when shared.llm refused a call at its cumulative ceiling
# (LLMBudgetExceeded; on the laptop the llm.spend_usd counter in .tmp/store.json,
# shared by the laptop jobs that call shared.llm, not the Modal reply engine's).
CEILING_HIT = "ceiling"
CEILING_CHECK = "python3 -c 'from shared import llm; print(llm.budget_status())'"

STAGE_ORDER = (
    ("new_reply", "New reply"),
    ("proposal_sent", "Proposal sent"),
    ("follow_up_later", "Follow-up later"),
    ("call_booked", "Call booked"),
    ("won", "Won"),
    ("lost", "Lost"),
)
STAGE_LABEL = dict(STAGE_ORDER)
KIND_OF = {"draft_touch": "touch", "draft_reply": "reply", "draft_checkin": "checkin"}

COUNT_KEYS = ("rooms", "enrolled", "drafted", "needs_edit", "pending", "sent_detected", "replies", "won",
              "lost", "skipped", "resurfaced", "deferred", "budget_deferred", "needs_review", "revivable",
              "ghl_errors", "errors", "waiting_on_you", "blocked", "blocked_new", "lock_skipped", "room_deferred")


# ------------------------------------------------------------------ helpers
def _aware(now: Any) -> datetime:
    if isinstance(now, str):
        now = slots.parse_iso(now)
    if not isinstance(now, datetime):
        raise ValueError("now must be a datetime or an ISO-8601 string, got %r" % (now,))
    return slots.ensure_aware(now)


def _parse(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    try:
        return slots.parse_iso(value).astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def _ct(now: datetime) -> datetime:
    return now.astimezone(slots.TZ)


def _day(value: Any) -> str:
    d = _parse(value)
    return _ct(d).strftime("%Y-%m-%d") if d else "unknown"


def _on_day(value: Any) -> str:
    d = _parse(value)
    return _ct(d).strftime("%Y-%m-%d") if d else "an unknown date"


def _utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def room_url(room_id: Any) -> str:
    return ROOM_URL % room_id


def batch_path(now: datetime) -> Path:
    """.tmp/upwork_followup/drafts_<Central date>.md, through shared.paths
    exactly as collect.write_snapshot resolves the snapshot."""
    return tmp_file(BATCH_NAME % _ct(_aware(now)).strftime("%Y-%m-%d"))


def _write_atomic(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(str(tmp), str(path))
    return path


INCOMPLETE_SECTIONS = ("proposals", "contracts", "offers")


def incomplete_warning(snapshot: Dict[str, Any]) -> Optional[str]:
    """One line when the pull lost data the batch cannot show: proposals whose
    get_room failed (their rooms are left out, silently otherwise) and the
    proposals / contracts / offers sections marked not collected."""
    links = [x for x in (snapshot.get("link_errors") or []) if x]
    sections = snapshot.get("sections") or {}
    missing = [k for k in INCOMPLETE_SECTIONS if sections.get(k) is False]
    if not links and not missing:
        return None
    return ("Upwork data incomplete: %d room link%s failed; sections missing: %s. Rooms behind a failed link "
            "are not in this batch; re-run the collect." % (len(links), "" if len(links) == 1 else "s",
                                                           ", ".join(missing) or "none"))


def snapshot_age_hours(snapshot: Dict[str, Any], now: datetime) -> Optional[float]:
    gen = _parse((snapshot or {}).get("generated_at"))
    if gen is None:
        return None
    return round((_aware(now).astimezone(timezone.utc) - gen).total_seconds() / 3600.0, 1)


def classify_dry_run(text: Any, room: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The dry-run classifier: no model. Machine text by the deterministic
    rule, everything else neutral (a reply card), via ``dry_run``."""
    if classify_mod.is_machine_text(text):
        return {"label": "machine", "confidence": 1.0, "follow_up_at": None, "via": "rule"}
    return {"label": "neutral", "confidence": 0.0, "follow_up_at": None, "via": "dry_run"}


def _classify_live(meter: "Meter") -> Callable[[Any, Dict[str, Any]], Dict[str, Any]]:
    """The run classifier. sequence.run calls it with no store lock held (the
    pass before its write), and every model call in it goes through the Meter:
    counted, capped, and preceded by a lease renewal.

    Past the run's budget or classifier cap, or when shared.llm refused a
    call at its cumulative ceiling, it raises RunBudgetExceeded, and after a
    lost lease LockLost: sequence leaves that thread untouched (its
    error action) and the next run classifies it. Both are raised here, around
    classify_reply, because classify.py turns any error from the model
    callable into a fallback ``neutral`` label, which would advance the thread
    on a label nobody read. So the lease is checked again after the call: a
    renewal that found the lease gone (inside classify.py) is read back here.
    A call made while a store.mutate is open raises NestedStoreCall first."""
    def fn(text, room):
        if classify_mod.is_machine_text(text):
            return classify_mod.classify_reply(text, room, llm=meter)   # the rule: no model call
        if meter.lease is not None:
            meter.lease.check("a classifier call")
            meter.lease.outside_mutate("a classifier call")
        if not meter.can_classify():
            what = "the shared LLM spend ceiling" if meter.hit == CEILING_HIT else "run %s" % meter.hit
            raise RunBudgetExceeded("%s reached; this reply is classified on the next run" % what)
        refused = meter.ceiling_refusals
        out = classify_mod.classify_reply(text, room, llm=meter)
        if meter.lease is not None:
            meter.lease.check("using a classification")
        if meter.ceiling_refusals > refused:
            # classify.py turned shared.llm's LLMBudgetExceeded into a fallback
            # label nobody read: leave the message unread for the next run
            raise RunBudgetExceeded("the shared LLM spend ceiling is reached; this reply is classified on "
                                    "the next run after it is raised or reset")
        return out
    return fn


def _dry_copy(store) -> Tuple[JsonFileStore, str]:
    """A throwaway JsonFileStore seeded with every ``upwork:`` thread and the
    sequence meta key. ``sequence.run`` writes reservations and meta, so a dry
    run on the real store would block the real run's drafts."""
    tmpdir = tempfile.mkdtemp(prefix="upwork_followup_dry_")
    work = JsonFileStore(os.path.join(tmpdir, "store.json"))
    keys = set(store.keys(sequence.PREFIX))
    keys.add(sequence.META_KEY)   # the meta key may live outside the prefix
    for key in sorted(keys):
        value = store.get(key)
        if value is not None:
            work.set(key, copy.deepcopy(value))
    return work, tmpdir


META_KEYS = (sequence.META_KEY, getattr(sequence, "LEGACY_META_KEY", sequence.META_KEY))


def _thread_keys(store) -> List[str]:
    return sorted(k for k in store.keys(sequence.PREFIX) if k not in META_KEYS)


def _kind_label(kind: Optional[str], touch: Optional[int]) -> str:
    if kind == "touch":
        return "Follow-up T%s" % touch
    if kind == "reply":
        return "Reply"
    if kind == "checkin":
        return "Check-in"
    return str(kind or "draft")


def card_title(kind: str, touch: Optional[int], client: Any) -> str:
    client = " ".join(str(client or "client").split())
    if kind == "touch":
        return "Upwork T%s for %s" % (touch, client)
    if kind == "reply":
        return "Upwork reply for %s" % client
    return "Upwork check-in for %s" % client


def card_id(room_id: Any, kind: str, touch: Optional[int], now: datetime) -> str:
    what = "T%s" % touch if kind == "touch" else kind
    return "uwf-%s-%s-%s" % (room_id, what, _ct(now).strftime("%Y%m%d%H%M"))


def truncate_bytes(text: str, limit: int, pointer: str) -> str:
    """``text`` cut to ``limit`` UTF-8 bytes, ending with ``pointer``."""
    if len(text.encode("utf-8")) <= limit:
        return text
    tail = "\n\n" + pointer
    room = max(0, limit - len(tail.encode("utf-8")))
    cut = text.encode("utf-8")[:room].decode("utf-8", "ignore").rstrip()
    return cut + tail


def _fence(text: str) -> str:
    runs = [len(m) for m in re.findall(r"`+", text or "")]
    fence = "`" * max(3, (max(runs) + 1) if runs else 3)
    return "%stext\n%s\n%s" % (fence, text, fence)


def _touches_sent(thread: Dict[str, Any]) -> str:
    sent = []
    replies = 0
    for entry in thread.get("history") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("event") == "touch_sent" and entry.get("touch"):
            sent.append("T%s" % entry.get("touch"))
        elif entry.get("event") == "reply_sent":
            replies += 1
    text = ", ".join(sent) if sent else "none"
    bits = ["%d in the current silence" % int(thread.get("touch_index") or 0)]
    if replies:
        bits.append("%d repl%s sent" % (replies, "y" if replies == 1 else "ies"))
    if thread.get("cycles"):
        bits.append("%d earlier silence%s broken" % (thread["cycles"], "" if thread["cycles"] == 1 else "s"))
    return "%s (%s)" % (text, "; ".join(bits))


def for_you_lines(room: Optional[Dict[str, Any]], thread: Dict[str, Any]) -> List[str]:
    """The "For you, not the client" block. Private material only lives here."""
    room = room or {}
    job = room.get("job") if isinstance(room.get("job"), dict) else None
    lines = ["Job: %s" % (room.get("job_title") or thread.get("job_title") or "unknown"),
             "Applied: %s" % ((job or {}).get("applied_at") or "unknown"),
             "Touches sent so far: %s" % _touches_sent(thread)]
    lines.extend(draft.private_note_lines(room))
    if job is None:
        lines.append(draft.NO_JOB_NOTE)
    return lines


# A "Label: text" line in the private notes (Time, Likelihood, Standard
# pricing, ...): a field of its own in the For-you block. A "- " line is one
# only when its label is a known field ("- Standard pricing: ...").
FOR_YOU_FIELD = re.compile(r"^([A-Za-z][A-Za-z0-9 /&'()+.-]{0,40}):(?:\s+(.*))?$")
# Labels that always start a field, so an empty "Time:" never swallows the
# next field as its first line.
FOR_YOU_KNOWN_FIELDS = ("time", "likelihood", "standard pricing", "pricing")


def _unbullet(line: str) -> str:
    """``line`` without one leading "- " bullet marker; the text is kept."""
    return line[2:] if line.startswith("- ") else line


def _is_known_field(label: Optional[str]) -> bool:
    return label is not None and label.strip().lower() in FOR_YOU_KNOWN_FIELDS


def _field_label(line: str) -> Optional[str]:
    """The field label that starts ``line``, or None. A "- " bullet starts a
    field only with a known label, so a nested "- Note: x" stays nested."""
    if line.startswith("- "):
        m = FOR_YOU_FIELD.match(line[2:])
        return m.group(1) if m and _is_known_field(m.group(1)) else None
    m = FOR_YOU_FIELD.match(line)
    return m.group(1) if m else None


def private_note_bullets(notes: List[str]) -> List[str]:
    """The private-note lines as Markdown bullets. A field (``Time:``,
    ``Likelihood:``, ``Standard pricing:``, any ``Label: text`` line) is one
    top-level ``- Label: <first line>``; an empty ``Label:`` takes the next line
    as its first line, unless that line starts with a known label (Time,
    Likelihood, Standard pricing, Pricing; with or without a "- "), which
    starts a new field instead. Every line
    after it, up to the next field, is nested two spaces in as ``  - <line>``,
    its own leading "- " dropped rather than doubled. A line before any field
    is a top-level bullet. The text of each line is unchanged."""
    out = []  # type: List[str]
    in_field = False
    i = 0
    while i < len(notes):
        line = notes[i]
        i += 1
        label = _field_label(line)
        if label is not None:
            line = _unbullet(line)
            if line.rstrip() == label + ":" and i < len(notes) and not _is_known_field(_field_label(notes[i])):
                line = "%s %s" % (line.rstrip(), _unbullet(notes[i]))
                i += 1
            out.append("- %s" % line)
            in_field = True
            continue
        out.append(("  - %s" if in_field else "- %s") % _unbullet(line))
    return out


def for_you_bullets(room: Optional[Dict[str, Any]], thread: Dict[str, Any]) -> List[str]:
    """``for_you_lines`` as the Markdown bullets the batch and the card print:
    the job, applied and touches lines one bullet each, the private notes
    through :func:`private_note_bullets` (so a multi-line field reads as one
    bullet with nested lines), then the no-job note."""
    room = room or {}
    lines = for_you_lines(room, thread)
    notes = draft.private_note_lines(room)
    head, rest = lines[:3], lines[3:]
    if rest[:len(notes)] != notes:
        return ["- %s" % _unbullet(ln) for ln in lines]   # an unexpected shape: flat, never doubled
    tail = rest[len(notes):]
    return ["- %s" % ln for ln in head] + private_note_bullets(notes) + ["- %s" % ln for ln in tail]


def reply_skipped(due: Dict[str, Any], thread: Optional[Dict[str, Any]]) -> bool:
    """The client wrote last and the reply drafted for that message was
    dropped unsent with no redraft coming (it expired twice, or was cleared
    without retry), so the client is still waiting on Lorenzo with nothing
    due: ``due_summary`` kind ``reply_skipped`` (sequence.py). The same shape
    read off the thread (status ``awaiting_lorenzo`` in a drafting stage,
    nothing pending, no hold, no kind, ``marks.reply_for`` equal to
    ``marks.reply_target``) counts too, for a due summary made without that
    kind."""
    due = due or {}
    if due.get("kind") == "reply_skipped":
        return True
    t = thread or {}
    if t.get("status") != sequence.AWAITING or t.get("pending") or due.get("hold") or due.get("kind"):
        return False
    if t.get("stage") not in sequence.DRAFTING_STAGES:
        return False
    marks = t.get("marks") or {}
    return bool(marks.get("reply_target")) and marks.get("reply_for") == marks.get("reply_target")


def reply_skip_dates(thread: Optional[Dict[str, Any]],
                     due: Optional[Dict[str, Any]] = None) -> Tuple[Optional[str], Optional[str]]:
    """(skipped_at, client_waiting_since) as stored ISO strings, either None.
    ``due_summary`` gives both (``skipped_at`` from ``marks.reply_skipped.at``,
    ``waiting_since`` from ``marks.last_client_at``). Without them the thread
    is read: the later of ``marks.reply_skipped.at`` (for the current
    ``marks.reply_target``) and the newest history entry for a skip
    (``reply_skipped``, or, on an older thread, ``withdrawn`` with reason
    ``skipped`` and kind ``reply``), and ``marks.last_client_at``."""
    due = due or {}
    t = thread or {}
    marks = t.get("marks") or {}
    skipped = due.get("skipped_at")
    if not skipped:
        for entry in reversed(t.get("history") or []):
            if not isinstance(entry, dict):
                continue
            event = entry.get("event")
            if event == "reply_skipped" or (event == "withdrawn" and entry.get("reason") == "skipped"
                                            and entry.get("kind") == "reply"):
                skipped = entry.get("at")
                break
        mark = marks.get("reply_skipped")
        if isinstance(mark, dict) and mark.get("at") and mark.get("message_id") == marks.get("reply_target"):
            seen, marked = _parse(skipped), _parse(mark.get("at"))
            if marked is not None and (seen is None or marked > seen):
                skipped = mark.get("at")
    return skipped, due.get("waiting_since") or marks.get("last_client_at")


def blocked_since(thread: Optional[Dict[str, Any]], room: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """When the room was blocked on Upwork (an ISO string, "" when the date is
    unknown), or None when it is not blocked now. The snapshot room decides
    when it is given: ``room["blocked"]``, read as sequence.py reads it (a
    missing key is False), dated by ``room["blocked_at"]``, else the thread's
    ``marks.blocked_at``. Without the room (not in this pull, or no snapshot)
    the thread decides: status ``closed`` or ``stop_reason`` ``room_blocked``
    (sequence.py's closure), dated by ``marks.blocked_at`` (the room's own
    block time, which sequence.py stores), else the ``blocked_at`` of the
    newest ``room_blocked`` history entry."""
    t = thread or {}
    marks = t.get("marks") if isinstance(t.get("marks"), dict) else {}
    if isinstance(room, dict) and room.get("room_id") and not room.get("not_in_snapshot"):
        if not room.get("blocked"):
            return None
        return str(room.get("blocked_at") or marks.get("blocked_at") or "")
    if t.get("status") != sequence.CLOSED and t.get("stop_reason") != ROOM_BLOCKED:
        return None
    if marks.get("blocked_at"):
        return str(marks["blocked_at"])
    named = next((h for h in reversed(t.get("history") or [])
                  if isinstance(h, dict) and h.get("event") == ROOM_BLOCKED), None)
    return str((named or {}).get("blocked_at") or "")


def blocked_rooms(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The snapshot's rooms that are blocked on Upwork: ``room["blocked"]``
    (truthy, as sequence.py reads it) or listed in ``snapshot["blocked_rooms"]``.
    A room from a snapshot written before the flag has no key and is not
    blocked."""
    listed = set(r for r in (snapshot.get("blocked_rooms") or []) if isinstance(r, str))
    out = []
    for room in snapshot.get("rooms") or []:
        if not isinstance(room, dict) or not room.get("room_id"):
            continue
        if room.get("blocked") or room["room_id"] in listed:
            out.append({"room_id": room["room_id"], "client": room.get("client") or "unknown client",
                        "job_title": room.get("job_title") or "", "blocked_at": room.get("blocked_at")})
    return sorted(out, key=lambda b: b["room_id"])


CLOSED_TEXT = "closed (blocked on Upwork); --resume or a drafting --stage reopens it"


def due_text(due: Dict[str, Any], thread: Optional[Dict[str, Any]] = None, blocked: Optional[str] = None) -> str:
    """One line for what is due. ``thread`` helps date a skipped reply;
    ``blocked`` (from ``blocked_since``; None when not blocked) is passed by
    --status only: the batch lists a blocked room once, in its own section.
    A ``closed`` thread whose room is open again (or not known to be blocked)
    gets ``CLOSED_TEXT``."""
    if blocked is not None:
        return "blocked on Upwork since %s" % _on_day(blocked)
    kind, at = due.get("kind"), due.get("next_due_at")
    if due.get("pending"):
        return "%s drafted, not sent yet" % _kind_label(kind, due.get("touch")) if kind else "drafted, not sent yet"
    if due.get("hold"):
        return "on hold: the last message's sender is unclear, check the room"
    if reply_skipped(due, thread):
        skipped_at, waiting = reply_skip_dates(thread, due)
        if not skipped_at and not waiting:
            return "reply skipped; the client is still waiting"
        return "reply skipped on %s; client waiting since %s" % (_on_day(skipped_at), _on_day(waiting))
    if kind == "touch":
        return "T%s due %s" % (due.get("touch"), "now" if due.get("draft_now") else _day(at))
    if kind == "reply":
        return "reply due now"
    if kind == "checkin":
        return "check-in due %s" % ("now" if due.get("draft_now") else _day(at))
    if kind == "close_out":
        return "T7 sent; closes out %s with no answer" % _day(at)
    status = due.get("status")
    if status == sequence.STOPPED:
        return "stopped (no drafts; --resume brings it back)"
    if status == sequence.CLOSED:
        return CLOSED_TEXT
    if status in (sequence.WON, sequence.LOST, sequence.CLOSED_OUT, sequence.DORMANT):
        return "status %s, no drafts" % status
    return "nothing due"


# ------------------------------------------------------------ run budget
class RunBudgetExceeded(RuntimeError):
    """This run's model budget (or its classifier cap) is used up; the work
    waits for the next run."""


def _env_number(name: str, default: Any, integer: bool = False) -> Any:
    """A finite, non-negative number from the environment (a whole number when
    ``integer``), else ``default`` with a warning: ``inf``, ``nan``, a
    negative, ``1.5`` for an integer or any other text all fall back."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw) if integer else float(raw)
    except ValueError:
        value = None
    if value is None or not math.isfinite(value) or value < 0:
        logger.warning("%s=%r is not a finite, non-negative %s; using %s", name, raw,
                       "whole number" if integer else "number", default)
        return default
    return value


def run_budget_usd() -> float:
    """``UPWORK_RUN_BUDGET_USD``, default $1.50. A value above
    ``MAX_RUN_BUDGET_USD`` is clamped to $10.00 with a warning (not refused:
    a bigger one-off run still gets the most one run may spend)."""
    value = float(_env_number(BUDGET_ENV, DEFAULT_RUN_BUDGET_USD))
    if value > MAX_RUN_BUDGET_USD:
        logger.warning("%s=%s is above the $%.2f a run may project; using $%.2f", BUDGET_ENV, value,
                       MAX_RUN_BUDGET_USD, MAX_RUN_BUDGET_USD)
        return MAX_RUN_BUDGET_USD
    return value


def run_max_classify() -> int:
    return int(_env_number(CLASSIFY_CAP_ENV, DEFAULT_MAX_CLASSIFY, integer=True))


def call_cost(role: str, system: str, user: str, max_tokens: int, json_mode: bool = False,
              model: Optional[str] = None) -> float:
    """Worst-case cost of one call, exactly what shared.llm.complete() reserves
    against its ceiling for the same arguments (shared_llm.reserved_cost_usd):
    the prompt as sent, the output at max_tokens PLUS the thinking headroom
    (THINKING_HEADROOM_TOKENS, 1,024), because thinking cannot be turned off
    on claude-opus-5-5 and counts toward the API's limit. Pricing the bare
    max_tokens undercounted every call about 2x against the run budget.
    complete() does not return the real cost, so the cap errs high."""
    return shared_llm.reserved_cost_usd(role, system or "", user or "", int(max_tokens),
                                        json_mode=bool(json_mode), model=model)


CLASSIFY_ROLES = ("classify", "escalate")


class Meter(object):
    """Wraps the model callable for one run: counts calls and projected spend,
    refuses a draft call that would take the run past its budget, and renews
    the run lease before every model call, classify and escalate included (the
    heartbeat; LockLost when the lease is gone, which draft.py turns into
    ``llm_error`` and classify.py into a fallback label; the tick reads it back
    from ``lease.lost`` after each draft and each classification). No call
    runs inside a store.mutate: sequence.run classifies before its write, and
    the drafts run between store writes; a renewal inside one raises
    NestedStoreCall (see RunLease).

    It also catches shared.llm's cumulative ceiling (``LLMBudgetExceeded``,
    the $10 counter ``llm.spend_usd`` in the laptop store, shared by the
    laptop jobs that call shared.llm; the Modal reply engine's is separate): the hit
    becomes ``ceiling``, ``ceiling_refusals`` counts it (and ``refusals``, so
    a draft is released as budget-deferred), and no further model call is made
    this run. The exception is re-raised; classify.py would swallow it into a
    fallback ``neutral``, so ``_classify_live`` reads ``ceiling_refusals``
    back and raises RunBudgetExceeded instead."""

    def __init__(self, inner: Optional[Callable[..., Any]], budget: float, max_classify: int,
                 lease: Optional["RunLease"] = None):
        self.inner = inner
        self.budget = float(budget)
        self.max_classify = int(max_classify)
        self.lease = lease
        self.spent = 0.0
        self.calls = {}  # type: Dict[str, int]
        self.hit = None  # type: Optional[str]
        self.refusals = 0
        self.ceiling_refusals = 0   # calls shared.llm refused at its cumulative ceiling

    def classify_calls(self) -> int:
        return self.calls.get("classify", 0) + self.calls.get("escalate", 0)

    def can_draft(self) -> bool:
        return self.hit is None and self.spent < self.budget

    def can_classify(self) -> bool:
        if self.ceiling_refusals:
            self.hit = self.hit or CEILING_HIT
            return False
        if self.classify_calls() >= self.max_classify:
            self.hit = self.hit or "classify_cap"
            return False
        if self.spent >= self.budget:
            self.hit = self.hit or "budget"
            return False
        return True

    def _ceiling(self) -> None:
        self.hit = self.hit or CEILING_HIT
        self.ceiling_refusals += 1
        self.refusals += 1

    def __call__(self, role, system, user, **kw):
        if self.ceiling_refusals:
            # shared.llm already refused this run: do not ask it again (the
            # escalate call classify.py makes after a failed classify, or the
            # next draft), refuse the same way
            exc = shared_llm.LLMBudgetExceeded(
                "shared LLM spend ceiling reached earlier this run; no model call made (role=%s)" % role)
            self._ceiling()
            raise exc
        cost = call_cost(role, system, user, kw.get("max_tokens", 800),
                         json_mode=kw.get("json_mode", False), model=kw.get("model"))
        if role not in CLASSIFY_ROLES and self.spent + cost > self.budget:
            # a classification already started is let finish (at most two
            # small calls); the gate for it is can_classify()
            self.hit = self.hit or "budget"
            self.refusals += 1
            raise RunBudgetExceeded("run budget $%.2f reached ($%.4f spent, next call $%.4f)"
                                    % (self.budget, self.spent, cost))
        if self.lease is not None:
            self.lease.renew("a model call (%s)" % role)
        self.spent = round(self.spent + cost, 6)
        self.calls[role] = self.calls.get(role, 0) + 1
        inner = self.inner if self.inner is not None else shared_llm.complete
        try:
            return inner(role, system, user, **kw)
        except shared_llm.LLMBudgetExceeded as exc:
            self._ceiling()
            raise


# ------------------------------------------------------------------ run lock
# The lease record under LOCK_KEY: {owner (token), acquired_at, heartbeat_at,
# expires_at (heartbeat_at + TTL), beats, pid, as_of (the run's --as-of, for
# reading only)}, plus clock_suspect_at once a blocked run has seen its stamps
# ahead of the real clock. Released: {owner: None, released_at, released_by}.
# Every time in it is the REAL clock (wall_clock), never --as-of: a run with a
# past or future --as-of must not see a live lease as stale.
class LockLost(RuntimeError):
    """This run no longer holds the run lease: another run took it over, it was
    released or removed, or it could not be renewed. The run stops drafting,
    records nothing more and sends no more cards."""


class NestedStoreCall(RuntimeError):
    """A store call, a lease renewal or a model call was attempted while one of
    the run's store.mutate calls is open. On JsonFileStore it would wait on
    this process's own flock forever; raised instead, so the room errors."""


def wall_clock() -> datetime:
    """The real UTC time. The run lease is taken, renewed and released on this
    clock only; ``run_tick(clock=...)`` injects another one (tests)."""
    return datetime.now(timezone.utc)


def _lease_ttl() -> timedelta:
    return timedelta(minutes=LOCK_TTL_MINUTES)


def lease_stamp(cur: Any) -> Optional[datetime]:
    """The newest time the holder wrote into the lease: its last heartbeat,
    else when it was taken."""
    if not isinstance(cur, dict):
        return None
    stamps = [d for d in (_parse(cur.get("acquired_at")), _parse(cur.get("heartbeat_at"))) if d is not None]
    return max(stamps) if stamps else None


def clock_problem(cur: Any, wall: datetime) -> bool:
    """True when the lease's newest stamp is more than LOCK_DRIFT_MINUTES
    ahead of the real time ``wall``: the holder's clock runs ahead, or a run of
    the older code stamped it with a future --as-of."""
    stamp = lease_stamp(cur)
    return stamp is not None and stamp > wall + timedelta(minutes=LOCK_DRIFT_MINUTES)


def lease_expiry(cur: Any, wall: datetime) -> Optional[datetime]:
    """When a held lease stops blocking, judged at the real time ``wall``.

    Its ``expires_at`` (last heartbeat + TTL), and never more than one TTL
    after its newest stamp. A lease with a clock problem expires by ``wall`` +
    TTL, and by ``clock_suspect_at`` + TTL once a blocked run has recorded when
    it first saw it: the per-check cap alone moves with every check, the mark
    is what keeps a lease stamped in the future from blocking for more than
    one TTL. A stamp can only be seen as "from the future" while it is still
    ahead of the checking clock; a run that first looks after that finds an
    ordinary lease, one TTL from its stamp. None when the lease has no
    readable times: it never blocks then."""
    if not isinstance(cur, dict):
        return None
    exp, stamp = _parse(cur.get("expires_at")), lease_stamp(cur)
    if exp is None or stamp is None:
        return None
    ttl = _lease_ttl()
    limits = [exp, stamp + ttl]
    seen = _parse(cur.get("clock_suspect_at"))
    if seen is not None:
        limits.append(seen + ttl)
    if clock_problem(cur, wall):
        limits.append(wall + ttl)
    return min(limits)


def lock_state(cur: Any, wall: datetime) -> str:
    """"free", "live" or "stale" for the stored lease at the real time ``wall``."""
    if not isinstance(cur, dict) or not cur.get("owner"):
        return "free"
    exp = lease_expiry(cur, wall)
    return "live" if exp is not None and wall < exp else "stale"


def _lease_write(store, fn: Callable[[Any], Any]) -> Tuple[Any, bool]:
    """Apply ``fn`` to the lease record; returns (what is stored now, atomic).
    ``fn`` does the owner-token check, so each tier below is a compare-and-set
    on the owner token as far as the store allows:

    1. ``store.mutate``: the read, ``fn`` and the write under the store's own
       lock (JsonFileStore: one flock across processes; ModalDictStore: its
       per-key lock). Both real backends take this path.
    2. ``store.compare_and_set``: ``fn`` on a read, written only while the
       record is still exactly what was read (owner token included); a lost
       race re-reads and re-applies ``fn``, at most LEASE_CAS_TRIES times.
    3. Neither: get, set, and a re-read that the caller checks for its own
       token. The race left there: two runs whose get, set and re-read
       interleave can both read back their own token (run A re-reads before
       run B's set), so both would run. Only a test double takes this path."""
    try:
        return store.mutate(LOCK_KEY, fn), True
    except NotImplementedError:
        pass
    try:
        return _lease_cas(store, fn), True
    except NotImplementedError:
        pass
    store.set(LOCK_KEY, fn(store.get(LOCK_KEY)))
    return store.get(LOCK_KEY), False


LEASE_CAS_TRIES = 5


def _lease_cas(store, fn: Callable[[Any], Any]) -> Any:
    for _ in range(LEASE_CAS_TRIES):
        present = LOCK_KEY in store.keys(LOCK_KEY)
        cur = store.get(LOCK_KEY) if present else None
        new = fn(copy.deepcopy(cur))
        if store.compare_and_set(LOCK_KEY, cur if present else ABSENT, new):
            return new
    raise StoreError("the run lock record kept changing under compare_and_set (%d tries)" % LEASE_CAS_TRIES)


def new_lease(token: str, wall: datetime, as_of: Optional[datetime] = None) -> Dict[str, Any]:
    return {"owner": token, "acquired_at": _utc_iso(wall), "heartbeat_at": _utc_iso(wall),
            "expires_at": _utc_iso(wall + _lease_ttl()), "beats": 0, "pid": os.getpid(),
            "as_of": _utc_iso(as_of) if as_of is not None else None}


def acquire_lock(store, wall: datetime, token: str, as_of: Optional[datetime] = None) -> Dict[str, Any]:
    """Take the lease at the real time ``wall`` (never the run's --as-of).

    ``{"held": lease}`` when another run holds a live lease: nothing is taken,
    and a lease with a clock problem gets ``clock_suspect_at`` the first time a
    run is blocked by it. Otherwise ``{"stale": old lease or None, "lease":
    the new lease}`` after taking it."""
    wall = wall.astimezone(timezone.utc)
    box = {"held": None, "stale": None, "lease": None}  # type: Dict[str, Any]

    def fn(cur):
        box.update(held=None, stale=None, lease=None)    # a compare_and_set retry applies fn again
        state = lock_state(cur, wall)
        if state == "live":
            held = dict(cur)
            if clock_problem(cur, wall) and _parse(cur.get("clock_suspect_at")) is None:
                held["clock_suspect_at"] = _utc_iso(wall)
            box["held"] = held
            return held
        box["stale"] = dict(cur) if state == "stale" else None
        box["lease"] = new_lease(token, wall, as_of)
        return box["lease"]

    stored, atomic = _lease_write(store, fn)
    if box["lease"] is not None and not atomic and (not isinstance(stored, dict) or stored.get("owner") != token):
        box.update(held=dict(stored) if isinstance(stored, dict) else {}, stale=None, lease=None)
    return box


def renew_lock(store, wall: datetime, token: str) -> Tuple[Optional[Dict[str, Any]], Any]:
    """The heartbeat: ``expires_at`` becomes ``wall`` + TTL, only while the
    record still carries ``token`` (and a ``clock_suspect_at`` mark is dropped:
    the holder just proved it is alive). (lease, None) when renewed; else
    (None, what the record holds now: another run's lease, a released one, or
    None), and the record is left as it is."""
    wall = wall.astimezone(timezone.utc)
    box = {"lease": None, "found": None}  # type: Dict[str, Any]

    def fn(cur):
        box.update(lease=None, found=None)                # a compare_and_set retry applies fn again
        if not isinstance(cur, dict) or cur.get("owner") != token:
            box["found"] = copy.deepcopy(cur)
            return cur
        lease = dict(cur)
        lease.pop("clock_suspect_at", None)
        lease.update(heartbeat_at=_utc_iso(wall), expires_at=_utc_iso(wall + _lease_ttl()),
                     beats=int(cur.get("beats") or 0) + 1)
        box["lease"] = lease
        return lease

    stored, atomic = _lease_write(store, fn)
    if box["lease"] is not None and not atomic and (not isinstance(stored, dict) or stored.get("owner") != token):
        return None, stored
    return box["lease"], box["found"]


def release_lock(store, token: str, wall: datetime) -> bool:
    """Give the lease back, only while the record still carries ``token`` (the
    same compare-and-set). A failure is logged; the TTL frees the lease."""
    def fn(cur):
        if isinstance(cur, dict) and cur.get("owner") == token:
            return {"owner": None, "released_at": _utc_iso(wall), "released_by": token}
        return cur
    try:
        _lease_write(store, fn)
        return True
    except Exception as exc:  # noqa: BLE001 - the TTL frees it anyway
        logger.warning("upwork_followup: could not release the run lock: %s", exc)
        return False


class RunLease(object):
    """One --run's hold on LOCK_KEY, on the real clock only.

    ``renew`` is the heartbeat. It runs before every model call, classify and
    escalate included (Meter), every draft record, every card and every store
    write of the run (``LeasedStore``). The first renewal that finds another
    owner, a released record or no record, or that cannot write, sets ``lost``
    and raises LockLost; every later ``renew`` or ``check`` raises it again.

    ``depth`` counts the run's open store.mutate calls (LeasedStore). While one
    is open nothing may touch the store: JsonFileStore holds one flock for the
    whole mutate and a second lock taken by the same process waits forever. No
    code path does so (every mutate callback is pure, and sequence.run
    classifies before its write); a renewal, a LeasedStore read or a classifier
    call made then raises NestedStoreCall instead of hanging."""

    def __init__(self, store, clock: Callable[[], datetime], as_of: Optional[datetime] = None,
                 token: Optional[str] = None):
        self.store = store
        self.clock = clock
        self.as_of = as_of
        self.token = token or "%s-%d" % (uuid.uuid4().hex[:12], os.getpid())
        self.lost = None  # type: Optional[Dict[str, Any]]
        self.depth = 0
        self.claims = set()  # type: set

    def wall(self) -> datetime:
        return _aware(self.clock()).astimezone(timezone.utc)

    def acquire(self) -> Dict[str, Any]:
        return acquire_lock(self.store, self.wall(), self.token, self.as_of)

    def check(self, during: str) -> None:
        if self.lost is not None:
            raise LockLost("the run lease was lost (%s) before %s" % (self.lost.get("reason"), during))

    def outside_mutate(self, during: str) -> None:
        if self.depth:
            raise NestedStoreCall("%s inside an open store.mutate (it would wait on the store's own lock)" % during)

    def renew(self, during: str) -> None:
        self.check(during)
        self.outside_mutate(during)
        wall = self.wall()
        detail = None
        try:
            lease, found = renew_lock(self.store, wall, self.token)
        except Exception as exc:  # noqa: BLE001 - a lease that cannot be renewed cannot be trusted
            lease, found, detail = None, None, "%s: %s" % (type(exc).__name__, exc)
        if lease is not None:
            return
        if detail is not None:
            reason = "renew_failed"
        elif isinstance(found, dict) and found.get("owner"):
            reason = "taken_over"
        else:
            reason = "released" if isinstance(found, dict) else "gone"
        self._lose(reason, during, wall, found, detail)

    def _lose(self, reason: str, during: str, wall: datetime, found: Any, detail: Optional[str] = None) -> None:
        info = {"reason": reason, "during": during, "at": _utc_iso(wall)}  # type: Dict[str, Any]
        if detail:
            info["detail"] = detail[:300]
        if isinstance(found, dict) and found.get("owner"):
            info["holder"] = dict((k, found.get(k)) for k in ("acquired_at", "heartbeat_at", "expires_at", "pid",
                                                               "as_of"))
        self.lost = info
        logger.warning("upwork_followup: run lease lost (%s) before %s; this run stops", reason, during)
        raise LockLost("the run lease was lost (%s) before %s" % (reason, during))

    def release(self) -> bool:
        return release_lock(self.store, self.token, self.wall())


class LeasedStore(Store):
    """The store as a --run uses it. Every write renews the lease first, and is
    refused with LockLost once the lease is lost; sequence.run records that
    per room and so writes nothing more either. Reads pass through. Any call
    made while one of its mutates is open raises NestedStoreCall.

    A thread write that leaves a NEW unfilled reservation (sequence.run
    reserving a draft) gets this run's ``draft_claim`` in the same write, so
    every reservation the run makes is provably its own if it loses the lease
    before filling it."""

    def __init__(self, inner, lease: RunLease):
        self.inner = inner
        self.lease = lease

    def get(self, key: str, default: Any = None) -> Any:
        self.lease.outside_mutate("a store read (%s)" % key)
        return self.inner.get(key, default)

    def keys(self, prefix: str = "") -> List[str]:
        self.lease.outside_mutate("a store read (keys %s)" % prefix)
        return self.inner.keys(prefix)

    def mutate(self, key: str, fn, default: Any = None) -> Any:
        self.lease.renew("a store write (%s)" % key)
        if key.startswith(sequence.PREFIX):
            fn = self._claiming(key, fn)
        self.lease.depth += 1
        try:
            return self.inner.mutate(key, fn, default)
        finally:
            self.lease.depth -= 1

    def _claiming(self, key: str, fn):
        lease = self.lease

        def wrapped(cur):
            new = fn(cur)
            p = _placeholder(new)
            if p is not None and (not isinstance(cur, dict) or cur.get("pending") != p):
                new[CLAIM_KEY] = _claim_record(p, lease.token)
                lease.claims.add(new.get("room_id") or key[len(sequence.PREFIX):])
            return new
        return wrapped

    def set(self, key: str, value: Any) -> None:
        self.lease.renew("a store write (%s)" % key)
        self.inner.set(key, value)

    def delete(self, key: str) -> None:
        self.lease.renew("a store write (%s)" % key)
        self.inner.delete(key)


def _heartbeat(store, during: str) -> None:
    """Renew the lease when ``store`` is a --run's LeasedStore (no-op otherwise)."""
    lease = getattr(store, "lease", None)
    if isinstance(lease, RunLease):
        lease.renew(during)


# --------------------------------------------------------------- the tick
def _new_result(now: datetime, mode: str) -> Dict[str, Any]:
    counts = dict((k, 0) for k in COUNT_KEYS)
    counts["snapshot_age_h"] = None
    counts["mode"] = mode
    return {"job": JOB_NAME, "mode": mode, "now": now.astimezone(timezone.utc).isoformat(), "status": None,
            "counts": counts, "warnings": [], "errors": [], "ghl_errors": [], "ghl_notes": [], "check": [],
            "dropped": [], "drafts": [], "notes": [], "budget": None, "locked": None, "lock_lost": None,
            "cards": [], "cards_state": "none", "batch_path": None, "snapshot_error": None,
            "notify_errors": [], "blocked": [], "deferred_rooms": [], "stage_overrides": []}


def _mutate(store, room_id: str, fn: Callable[[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
    def wrap(cur):
        if cur is None:
            raise sequence.ThreadNotFound("no thread for room %s" % room_id)
        return fn(cur)
    return store.mutate(sequence.thread_key(room_id), wrap)


def _call_draft(kind: str, room: Dict[str, Any], thread: Dict[str, Any], touch: Optional[int], now: datetime,
                llm: Optional[Callable[..., Any]]) -> Dict[str, Any]:
    if kind == "touch":
        return draft.draft_touch(room, thread, int(touch), now, llm=llm)
    if kind == "reply":
        return draft.draft_reply(room, thread, now, llm=llm)
    return draft.draft_checkin(room, thread, now, llm=llm)


def record_pending(cur: Dict[str, Any], kind: str, touch: Optional[int], text: str, now: datetime,
                   cid: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """``sequence.record_pending`` as (thread, None), or (None, reason) when it
    refuses with ``PendingRefused`` (no reservation, a mismatch, a stage that
    no longer drafts, a status that is not live)."""
    try:
        return sequence.record_pending(cur, kind, touch, text, now, cid), None
    except sequence.PendingRefused as exc:
        return None, getattr(exc, "reason", None) or str(exc)


def _placeholder(thread: Any) -> Optional[Dict[str, Any]]:
    """The thread's pending when it is an unfilled reservation, else None."""
    p = (thread or {}).get("pending") if isinstance(thread, dict) else None
    if isinstance(p, dict) and p.get("text") is None and p.get("card_id") is None:
        return p
    return None


def _own_placeholder(thread: Any, token: str) -> bool:
    """True when the thread's pending is an unfilled reservation this run
    claimed (``draft_claim`` with its token, for that same kind, touch and
    issued_at). A reservation another run released and made again, or claimed
    itself, fails."""
    p = _placeholder(thread)
    claim = thread.get(CLAIM_KEY) if p is not None else None
    return isinstance(claim, dict) and claim.get("token") == token and \
        (claim.get("kind"), claim.get("touch"), claim.get("issued_at")) == \
        (p.get("kind"), p.get("touch"), p.get("issued_at"))


def _claim_refusal(thread: Any, token: str) -> Optional[str]:
    """None when ``thread`` holds this run's own claimed reservation, else why
    this run may not record into it: ``no_reservation`` (withdrawn),
    ``already_drafted`` (another run filled it) or ``claim_lost`` (a
    reservation another run released and made again, or claimed itself)."""
    if _own_placeholder(thread, token):
        return None
    pending = thread.get("pending") if isinstance(thread, dict) else None
    if not pending:
        return "no_reservation"
    if _placeholder(thread) is None:
        return "already_drafted"
    return "claim_lost"


def _claim_record(p: Dict[str, Any], token: str) -> Dict[str, Any]:
    return {"token": token, "kind": p.get("kind"), "touch": p.get("touch"), "issued_at": p.get("issued_at")}


def _claim(work, rid: str, kind: str, touch: Optional[int], token: str) -> bool:
    """Stamp this run's token on the reservation it is about to fill (its own,
    already stamped by LeasedStore, or one an earlier run left unfilled).
    False (nothing changed) when the reservation is gone or is not that draft."""
    box = {"ok": False}

    def fn(cur):
        p = _placeholder(cur)
        if p is None or p.get("kind") != kind or p.get("touch") != (touch if kind == "touch" else None):
            return cur
        t = copy.deepcopy(cur)
        t[CLAIM_KEY] = _claim_record(p, token)
        box["ok"] = True
        return t

    _mutate(work, rid, fn)
    return box["ok"]


def _release(work, rid: str, now: datetime, reason: str, result: Dict[str, Any],
             token: Optional[str] = None) -> bool:
    """Withdraw an unfilled reservation so the next run drafts it again
    (``clear_pending`` with ``retry``). With ``token``, only while it still
    carries that run's claim. A filled draft is never touched."""
    box = {"done": False}

    def fn(cur):
        if _placeholder(cur) is None or (token is not None and not _own_placeholder(cur, token)):
            return cur
        t = sequence.clear_pending(cur, now, reason=reason, retry=True)
        t.pop(CLAIM_KEY, None)
        box["done"] = True
        return t

    try:
        _mutate(work, rid, fn)
    except LockLost:
        raise
    except Exception as exc:  # noqa: BLE001
        result["errors"].append("%s: clear_pending failed: %s" % (rid, exc))
    return box["done"]


def _release_own(lease: "RunLease", now: datetime, result: Dict[str, Any]) -> List[str]:
    """After a lost lease: give back each reservation this run claimed and did
    not fill, but only while it still carries this run's claim (checked inside
    the store's lock). Written to the real store without the lease on purpose:
    it only ever undoes this run's own claim, which another run never holds."""
    released = []
    for rid in sorted(lease.claims):
        if _release(lease.store, rid, now, "lock_lost", result, token=lease.token):
            released.append(rid)
    lease.claims.clear()
    return released


def _draft_all(work, entries, order, now, llm, dry, result, meter: Optional[Meter] = None,
               lease: Optional["RunLease"] = None) -> None:
    """Draft every reserved slot. On a --run, each reservation is claimed with
    the run's token before any model call; the lease is renewed before each
    model call (Meter) and each record (LeasedStore); LockLost propagates."""
    plan = []  # type: List[Tuple[str, str, Optional[int]]]
    for rid in order:
        e = entries[rid]
        if any(a.get("type") == sequence.ROOM_DEFERRED for a in e["acts"]):
            # not advanced this run: not even an older unfilled reservation is
            # drafted before the next run has read its new messages
            e["draft_skipped"] = "left for the next run (the thread changed while this run classified it)"
            continue
        act = next((a for a in e["acts"] if a.get("type") in sequence.DRAFT_TYPES), None)
        try:
            thread = work.get(sequence.thread_key(rid))
        except Exception as exc:  # noqa: BLE001
            result["errors"].append("%s: %s" % (rid, exc))
            continue
        pending = (thread or {}).get("pending") or None
        if act is not None:
            kind = KIND_OF[act["type"]]
            touch = act.get("touch") if kind == "touch" else None
        elif not dry and pending and pending.get("text") is None:
            # a reservation an earlier run left unfilled (it stopped between
            # reserving and recording): fill it now
            kind, touch = pending.get("kind"), pending.get("touch")
        else:
            continue
        if (e.get("room") or {}).get("blocked"):
            # the client blocked the room on Upwork: never drafted. sequence.py
            # already closes it without reserving; a reservation found here
            # anyway (an older record) goes back.
            e["draft_skipped"] = "the room is blocked on Upwork"
            if not dry:
                _release(work, rid, now, ROOM_BLOCKED, result)
            continue
        if dry:
            e["would_draft"] = (kind, touch)
            result["counts"]["drafted"] += 1
            continue
        if not pending or pending.get("kind") != kind or pending.get("text") is not None:
            # the reservation is gone: a stage moved in GHL withdrew it
            e["draft_skipped"] = "the reservation was withdrawn before drafting"
            continue
        plan.append((rid, kind, touch))
    if lease is not None:
        claimed = []
        for rid, kind, touch in plan:
            try:
                ok = _claim(work, rid, kind, touch, lease.token)
            except LockLost:
                raise
            except Exception as exc:  # noqa: BLE001
                result["errors"].append("%s: could not claim the reservation: %s" % (rid, exc))
                continue
            if ok:
                lease.claims.add(rid)
                claimed.append((rid, kind, touch))
            else:
                entries[rid]["draft_skipped"] = "the reservation was withdrawn before drafting"
        plan = claimed
    for rid, kind, touch in plan:
        _draft_one(work, entries[rid], rid, kind, touch, now, llm, result, meter, lease)


def _draft_one(work, e: Dict[str, Any], rid: str, kind: str, touch: Optional[int], now: datetime, llm,
               result: Dict[str, Any], meter: Optional[Meter], lease: Optional["RunLease"]) -> None:
    token = lease.token if lease is not None else None
    try:
        thread = work.get(sequence.thread_key(rid))
    except Exception as exc:  # noqa: BLE001
        result["errors"].append("%s: %s" % (rid, exc))
        return
    if meter is not None and not meter.can_draft():
        # the run's budget is used up: release the reservation cleanly so
        # the next run drafts it (the same as a crashed run's)
        _release(work, rid, now, "run_budget", result, token)
        if lease is not None:
            lease.claims.discard(rid)
        e["budget_deferred"] = True
        result["counts"]["budget_deferred"] += 1
        return
    failure = None
    out = None
    refusals = meter.refusals if meter is not None else 0
    try:
        out = _call_draft(kind, e["room"], thread, touch, now, llm)
        if not (out.get("text") or "").strip():
            failure = ", ".join(out.get("problems") or []) or "empty draft"
    except LockLost:
        raise
    except Exception as exc:  # noqa: BLE001 - a draft failure is retried next run
        logger.warning("upwork_followup: drafting %s for %s failed: %s", kind, rid, exc)
        failure = "%s: %s" % (type(exc).__name__, exc)
    if lease is not None:
        # draft.py turns a LockLost from the meter's heartbeat into llm_error:
        # read it back here, before anything is recorded or released
        lease.check("recording the %s draft for %s" % (_kind_label(kind, touch), rid))
    if failure is not None and meter is not None and meter.refusals > refusals:
        _release(work, rid, now, "run_budget", result, token)
        if lease is not None:
            lease.claims.discard(rid)
        e["budget_deferred"] = True
        result["counts"]["budget_deferred"] += 1
        return
    if failure is not None:
        _release(work, rid, now, "draft_failed", result, token)
        if lease is not None:
            lease.claims.discard(rid)
        e["draft_error"] = failure
        result["errors"].append("%s: %s draft failed (%s); it is retried on the next run"
                                % (rid, _kind_label(kind, touch), failure))
        return
    cid = card_id(rid, kind, touch, now)
    meta = {"card_id": cid, "kind": kind, "touch": touch, "problems": list(out.get("problems") or []),
            "needs_you": list(out.get("needs_you") or []), "proposes_call": bool(out.get("proposes_call")),
            "drafted_at": now.astimezone(timezone.utc).isoformat()}

    box = {"refused": None}  # type: Dict[str, Any]

    def fn(cur, text=out["text"]):
        # The claim is checked BEFORE record_pending, inside the same store
        # lock: sequence.record_pending checks only kind, touch, stage and
        # status, and would fill (or overwrite) a reservation this run no
        # longer holds.
        refused = _claim_refusal(cur, token) if token is not None else None
        t = None
        if refused is None:
            t, refused = record_pending(cur, kind, touch, text, now, cid)
        if refused:
            box["refused"] = refused
            return cur
        t["draft_meta"] = meta
        t.pop(CLAIM_KEY, None)
        return t

    try:
        # on a --run, LeasedStore renews the lease first: the heartbeat
        # before each record
        _mutate(work, rid, fn)
    except LockLost:
        raise
    except Exception as exc:  # noqa: BLE001
        result["errors"].append("%s: record_pending failed: %s" % (rid, exc))
        return
    if lease is not None:
        lease.claims.discard(rid)
    if box["refused"]:
        # the reservation is gone or the stage no longer drafts: drop the
        # draft, no card, and say so in the batch
        e["draft_skipped"] = "draft dropped: %s" % box["refused"]
        result["dropped"].append({"room_id": rid, "kind": kind, "touch": touch, "reason": box["refused"]})
        return
    e["new_draft"] = dict(meta, text=out["text"], for_you=list(out.get("for_you") or []))
    result["counts"]["drafted"] += 1
    if meta["problems"]:
        result["counts"]["needs_edit"] += 1
    result["drafts"].append({"room_id": rid, "client": (thread or {}).get("client"), "kind": kind,
                             "touch": touch, "card_id": cid, "problems": meta["problems"],
                             "proposes_call": meta["proposes_call"]})


NOT_CONFIGURED = ghl_sync.NOT_CONFIGURED


def _not_configured(value: Any) -> bool:
    """ghl_sync's "the Upwork pipeline is not in config/ids.json yet" marker,
    as a returned value or as an error entry's code."""
    if isinstance(value, dict):
        value = value.get("code")
    return isinstance(value, str) and value == NOT_CONFIGURED


def _ghl_note(result: Dict[str, Any], note: str) -> None:
    if note not in result["ghl_notes"]:
        result["ghl_notes"].append(note)


def _ghl_errors(result: Dict[str, Any], errs: Any) -> None:
    for err in errs or []:
        if _not_configured(err):
            _ghl_note(result, NOT_CONFIGURED)
        else:
            result["ghl_errors"].append(err if isinstance(err, dict) else {"code": str(err)})


def _won_by_contract(rid: str, thread: Dict[str, Any], acts: List[Dict[str, Any]],
                     contracted: set) -> bool:
    """A real contract beats a GHL move: the engine only sets ``won`` from one."""
    if rid in contracted:
        return True
    if any(a.get("type") == "stage_change" and a.get("to") == "won" and a.get("by") == "engine" for a in acts):
        return True
    return thread.get("status") == sequence.WON and thread.get("stage") == "won" \
        and thread.get("stage_set_by") == "engine"


def _ghl_read_back(work, entries, order, now, ghl, result, contracted: Optional[set] = None) -> None:
    """A stage Lorenzo set in GHL, applied before anything else uses the thread.
    Skipped for a room won by a real contract, so the same run pushes ``won``.

    A GHL move is never overwritten, his own CLI stage included: when the
    thread's stage was his (``--stage`` or ``--resume``, ``stage_set_by ==
    "lorenzo"``) and GHL's card move replaces it here, the run records it in
    ``result["stage_overrides"]`` ({room_id, cli_stage, ghl_stage}) and the
    batch and the summary say so in one line, so he can run --stage again."""
    for rid in order:
        try:
            thread = work.get(sequence.thread_key(rid))
            if not thread:
                continue
            if _won_by_contract(rid, thread, entries[rid]["acts"], contracted or set()):
                continue
            stage = ghl_sync.read_back_stage(thread, ghl)
            if _not_configured(stage):
                _ghl_note(result, NOT_CONFIGURED)
                continue
            if not stage:
                continue
            if stage not in sequence.STAGES:
                result["ghl_errors"].append({"code": "ghl_unknown_stage", "room_id": rid,
                                             "detail": "read-back returned %r" % (stage,)})
                continue
            box = {"acts": [], "override": None}  # type: Dict[str, Any]

            def fn(cur, stage=stage, box=box):
                t, acts = sequence.apply_external_stage(cur, stage, now)
                box["acts"] = acts
                box["override"] = None
                if isinstance(cur, dict) and cur.get("stage_set_by") == "lorenzo" and cur.get("stage") != stage \
                        and t.get("stage") == stage:
                    box["override"] = {"room_id": rid, "cli_stage": cur.get("stage"), "ghl_stage": stage}
                return t

            _mutate(work, rid, fn)
            entries[rid]["acts"].extend(box["acts"])
            entries[rid]["external_stage"] = stage
            if box["override"]:
                result["stage_overrides"].append(box["override"])
        except LockLost:
            raise
        except Exception as exc:  # noqa: BLE001 - GHL never stops the tick
            result["ghl_errors"].append({"code": "ghl_read_back_failed", "room_id": rid, "detail": str(exc)[:400]})


def _ghl_sync(work, entries, order, now, ghl, result) -> None:
    """Mirror each thread's FINAL stage. Only ``ghl_stage`` actions that agree
    with ``thread["stage"]`` are passed (none when GHL itself set the stage this
    run). ``thread["ghl"]`` is whatever sync_thread returns; the tick never sets
    its ``stage`` itself."""
    for rid in order:
        e = entries[rid]
        try:
            thread = work.get(sequence.thread_key(rid))
            if not thread:
                continue
            stage = thread.get("stage")
            engine = [] if e.get("external_stage") else [
                a for a in e["acts"] if a.get("type") == "ghl_stage" and a.get("stage") == stage]
            _heartbeat(work, "the GHL mirror for %s" % rid)
            state, _done, errs = ghl_sync.sync_thread(copy.deepcopy(thread), e["room"], ghl, now,
                                                      dry_run=False, engine_actions=engine)
            _ghl_errors(result, errs)
            if isinstance(state, dict) and thread.get("ghl") != state:
                def fn(cur, state=state):
                    t = copy.deepcopy(cur)
                    t["ghl"] = dict(state)
                    return t
                _mutate(work, rid, fn)
        except LockLost:
            raise
        except Exception as exc:  # noqa: BLE001 - GHL never stops the tick
            result["ghl_errors"].append({"code": "ghl_sync_failed", "room_id": rid, "detail": str(exc)[:400]})


def _save_titles(work, entries, order, result) -> None:
    """Keep the job title on the thread, so --status and --stage can still name
    a job once its room drops out of the snapshot."""
    for rid in order:
        room = entries[rid]["room"]
        title = room.get("job_title")
        if not title:
            continue
        try:
            thread = work.get(sequence.thread_key(rid))
            if not thread or thread.get("job_title") == title:
                continue

            def fn(cur, title=title):
                t = copy.deepcopy(cur)
                t["job_title"] = title
                return t

            _mutate(work, rid, fn)
        except LockLost:
            raise
        except Exception as exc:  # noqa: BLE001
            result["errors"].append("%s: could not save the job title: %s" % (rid, exc))


def _count_actions(entries: Dict[str, Dict[str, Any]], result: Dict[str, Any]) -> None:
    c = result["counts"]
    for rid, e in entries.items():
        for a in e["acts"]:
            t = a.get("type")
            if t == "enrolled":
                c["enrolled"] += 1
            elif t == "sent_detected":
                c["sent_detected"] += 1
            elif t == "classified" and a.get("label") != sequence.MACHINE:
                c["replies"] += 1
            elif t == "stage_change" and a.get("to") == "won":
                c["won"] += 1
            elif t == "stage_change" and a.get("to") == "lost":
                c["lost"] += 1
            elif t == "withdraw_pending" and a.get("reason") == "skipped":
                c["skipped"] += 1
            elif t == "resurface":
                c["resurfaced"] += 1
            elif t == "deferred":
                c["deferred"] += 1
            elif t == "revivable":
                c["revivable"] += 1
            elif t == "needs_review":
                c["needs_review"] += 1
                result["check"].append({"room_id": rid, "reason": a.get("reason"),
                                        "detail": dict((k, v) for k, v in a.items() if k not in ("type", "reason"))})
            elif t == "error" and a.get("error_type") == RunBudgetExceeded.__name__:
                c["budget_deferred"] += 1       # classification waits for the next run
            elif t == "error" and a.get("error_type") == LockLost.__name__:
                c["lock_skipped"] += 1          # not advanced: the run had lost its lease
            elif t == "error":
                result["errors"].append("%s: %s (%s)" % (rid, a.get("error"), a.get("error_type")))
            elif t == sequence.ROOM_DEFERRED:
                c["room_deferred"] += 1         # not advanced: the thread changed while it was classified
                result["deferred_rooms"].append({"room_id": rid, "reason": a.get("reason"),
                                                 "detail": a.get("detail")})
    n = c["room_deferred"]
    if n:
        # generic (it goes on public pushes too); the room ids are in Job_Log
        result["notes"].append("%d room%s changed while this run classified %s, so %s left for the next run"
                               % (n, "" if n == 1 else "s", "it" if n == 1 else "them",
                                  "it is" if n == 1 else "they are"))


def _fold_reviews(result: Dict[str, Any], waiting: set, blocked_new: set) -> None:
    """sequence.py's ``needs_review`` ``reply_skipped`` (the second expiry) and
    ``room_blocked`` (first sight) are the same news as the batch's "Needs
    you" and "Blocked on Upwork" lines: shown there, once, and not counted
    again under "Check these". One whose room is not in that section this run
    keeps its "Check these" line."""
    keep = []
    for item in result["check"]:
        if (item.get("reason") == "reply_skipped" and item["room_id"] in waiting) or \
                (item.get("reason") == ROOM_BLOCKED and item["room_id"] in blocked_new):
            result["counts"]["needs_review"] -= 1
        else:
            keep.append(item)
    result["check"] = keep


def _status(result: Dict[str, Any]) -> str:
    c = result["counts"]
    if result.get("lock_lost"):
        return "lock_lost"
    if result["snapshot_error"] or result["errors"]:
        return "error"
    if c["needs_review"] or c["needs_edit"] or result["ghl_errors"] or result["warnings"] or result["budget"] \
            or c.get("waiting_on_you") or c.get("blocked_new") or result.get("stage_overrides"):
        return "attention"
    return "ok"


def stage_override_line(o: Dict[str, Any], client: Any = None) -> str:
    """One plain line for a stage Lorenzo set that GHL's card move replaced
    this run. Neutral about the source: ``--stage`` and a ``--resume`` that
    moved the stage both leave ``stage_set_by == "lorenzo"``. ``client`` only
    where the reader is Lorenzo (the batch)."""
    where = "%s (room %s)" % (" ".join(str(client).split()), o["room_id"]) if client else "room %s" % o["room_id"]
    return ("The stage you set (%s) for %s was overridden by the GHL card move to %s; run --stage %s again if "
            "you meant it." % (o.get("cli_stage"), where, o.get("ghl_stage"), o.get("cli_stage")))


def _snapshot_failed(real, send, result: Dict[str, Any], now: datetime, dry: bool, err: str,
                     where: Any, lease: Optional["RunLease"] = None) -> Dict[str, Any]:
    """No usable snapshot: an error batch, one alert per Central day, Job_Log."""
    result["snapshot_error"] = err
    result["errors"].append("snapshot %s: %s" % (err, where))
    result["status"] = "error"
    _write_atomic(Path(result["batch_path"]), render_error_batch(result, now, where))
    if not dry:
        kind = err.split(":", 1)[0]
        try:
            _summary_card(real, send, result, now, "error:%s|%s" % (kind, _ct(now).strftime("%Y-%m-%d")),
                          new_cards=0, lease=lease)
        except LockLost:
            _on_lock_lost(lease, result, now)
            result["status"] = _status(result)
    return result


def lock_lost_warning(info: Dict[str, Any]) -> str:
    """The batch and summary line for a lost lease. It goes on public pushes
    too, so the step is named without its room id (Job_Log keeps the full
    ``during``)."""
    what = {"taken_over": "another --run took the run lease over",
            "released": "the run lease was released under this run (another run took it over and finished, "
                        "or it was cleared by hand)",
            "gone": "the run lease record disappeared",
            "renew_failed": "the run lease could not be renewed (store error)"}.get(info.get("reason"),
                                                                                 "the run lease was lost")
    step = re.split(r" for | \(", str(info.get("during") or "its next step"))[0]
    released = info.get("released") or []
    return ("LOCK LOST at %s: %s. This run stopped before %s: no model call, draft record or card after "
            "that point%s. The run holding the lease does the rest; if none is running, start --run again."
            % (info.get("at"), what, step,
               "; %d unfilled reservation%s given back" % (len(released), "" if len(released) == 1 else "s")
               if released else ""))


def _on_lock_lost(lease: Optional["RunLease"], result: Dict[str, Any], now: datetime) -> None:
    """The lease is gone: give back this run's own unfilled reservations and
    say so in the result (batch, summary text, Job_Log). Once per run."""
    if result.get("lock_lost") is not None:
        return
    info = dict((lease.lost if lease is not None else None) or {"reason": "unknown"})
    info["released"] = _release_own(lease, now, result) if lease is not None else []
    result["lock_lost"] = info
    result["warnings"].append(lock_lost_warning(info))


def _lease_view(cur: Dict[str, Any], wall: datetime) -> Dict[str, Any]:
    free_by = lease_expiry(cur, wall)
    return {"acquired_at": cur.get("acquired_at"), "heartbeat_at": cur.get("heartbeat_at"),
            "expires_at": cur.get("expires_at"), "free_by": _utc_iso(free_by) if free_by else None,
            "clock_problem": bool(clock_problem(cur, wall) or cur.get("clock_suspect_at")),
            "as_of": cur.get("as_of"), "pid": cur.get("pid"), "checked_at": _utc_iso(wall)}


def run_tick(now: Any, mode: str, store=None, snapshot_path: Optional[Any] = None,
             llm: Optional[Callable[..., Any]] = None, notify_fn: Optional[Callable[..., Any]] = None,
             ghl: Any = None, clock: Optional[Callable[[], datetime]] = None) -> Dict[str, Any]:
    """Run one tick. ``mode`` is ``"dry-run"`` or ``"run"``. Returns the result
    dict (status, counts, warnings, errors, drafts, cards, batch_path).

    A ``run`` holds the ``LOCK_KEY`` lease for its whole length, on the real
    clock (``clock``, default ``wall_clock``; never ``now``). A second run that
    finds a live lease does nothing and returns ``status: "locked"``; a run
    that loses its lease stops and returns ``status: "lock_lost"``."""
    if mode not in MODES:
        raise ValueError("mode must be one of %s, got %r" % (", ".join(MODES), mode))
    now = _aware(now)
    dry = mode == "dry-run"
    real = store if store is not None else get_store()
    result = _new_result(now, mode)
    result["batch_path"] = str(batch_path(now))
    send = notify_fn or shared_notify

    lease = None
    tick_store = real
    if not dry:
        lease = RunLease(real, clock or wall_clock, as_of=now)
        try:
            got = lease.acquire()
        except Exception as exc:  # noqa: BLE001 - without the lease the run must not draft
            result["errors"].append("could not take the run lock: %s" % exc)
            result["status"] = "error"
            result["counts"]["errors"] = len(result["errors"])
            _log(result)
            return result
        if got["held"]:
            held = _lease_view(got["held"], lease.wall())
            result["locked"] = held
            result["status"] = "locked"
            result["notes"].append("another --run holds the lock (taken %s, last heartbeat %s, free by %s at the "
                                   "latest%s); this run did nothing"
                                   % (held["acquired_at"], held["heartbeat_at"], held["free_by"],
                                      "; its time stamps are ahead of this machine's clock"
                                      if held["clock_problem"] else ""))
            _log(result)
            return result
        if got["stale"]:
            old = _lease_view(got["stale"], lease.wall())
            why = ("its times are unreadable" if old["free_by"] is None else
                   "it was stamped ahead of this machine's clock" if old["clock_problem"] else
                   "no heartbeat since %s" % (old["heartbeat_at"] or old["acquired_at"]))
            result["lock_taken_over"] = dict(old, why=why)
            result["notes"].append("took over a stale run lock from %s (expired %s; %s): an earlier run did not "
                                   "finish" % (old["acquired_at"], old["expires_at"], why))
        tick_store = LeasedStore(real, lease)
    try:
        _tick(tick_store, now, dry, result, snapshot_path, llm, send, ghl, lease)
    except LockLost:
        _on_lock_lost(lease, result, now)
        result["status"] = _status(result)
    finally:
        if lease is not None:
            lease.release()
    result["counts"]["errors"] = len(result["errors"])
    _log(result)
    return result


def _tick(real, now: datetime, dry: bool, result: Dict[str, Any], snapshot_path, llm, send, ghl,
          lease: Optional[RunLease] = None) -> None:
    """``real`` is the store the run writes through: a LeasedStore on --run."""
    path = Path(result["batch_path"])
    where = collect.snapshot_path(snapshot_path)
    snapshot, err = collect.load_snapshot(snapshot_path)
    if err:
        _snapshot_failed(real, send, result, now, dry, err, where, lease)
        return

    age = snapshot_age_hours(snapshot, now)
    result["counts"]["snapshot_age_h"] = age
    result["snapshot_generated_at"] = snapshot.get("generated_at")
    if collect.is_future_stamp(snapshot.get("generated_at"), now):
        # the same rule (collect.MAX_CLOCK_DRIFT) the ingest applies to collected_at
        _snapshot_failed(real, send, result, now, dry,
                         "future: generated_at %s is %.1f h after this run"
                         % (snapshot.get("generated_at"), -(age or 0.0)), where, lease)
        return
    result["counts"]["rooms"] = len(snapshot.get("rooms") or [])
    if age is None:
        result["warnings"].append("STALE SNAPSHOT: it has no readable generated_at, so its age is unknown. "
                                  "Re-run the collect and --ingest before trusting this batch.")
    elif age > STALE_HOURS:
        result["warnings"].append("STALE SNAPSHOT: it is %.1f hours old (generated %s). The collect or the "
                                  "ingest did not run this morning; new client messages are missing from this "
                                  "batch." % (age, snapshot.get("generated_at")))
    if snapshot.get("truncated"):
        sections = ", ".join(snapshot.get("truncated_sections") or []) or "section unknown"
        result["warnings"].append("The pull was truncated (%s): older rooms may be missing." % sections)
    incomplete = incomplete_warning(snapshot)
    if incomplete:
        result["warnings"].append(incomplete)
    blocked = _blocked_now(real, snapshot)
    result["blocked"] = blocked
    result["counts"]["blocked"] = len(blocked)
    result["counts"]["blocked_new"] = len([b for b in blocked if b["new"]])

    meter = None
    if dry:
        work, tmpdir = _dry_copy(real)
        classify_fn = classify_dry_run
    else:
        work, tmpdir = real, None
        meter = Meter(llm, run_budget_usd(), run_max_classify(), lease=lease)
        classify_fn = _classify_live(meter)
    try:
        entries = {}  # type: Dict[str, Dict[str, Any]]
        order = []  # type: List[str]
        try:
            try:
                raw = sequence.run(work, snapshot, now, classify_fn)
            except LockLost:
                raise
            except Exception as exc:  # noqa: BLE001 - the store itself failed
                logger.error("upwork_followup: sequence.run failed: %s", exc)
                result["errors"].append("sequence.run failed: %s: %s" % (type(exc).__name__, exc))
                raw = []
            for room, _thread, acts in raw:
                rid = room.get("room_id")
                if rid not in entries:
                    entries[rid] = {"room": room, "acts": []}
                    order.append(rid)
                entries[rid]["acts"].extend(acts)
            if lease is not None:
                # sequence.run records a LockLost per room and carries on
                # without writing: stop here when it hit one
                lease.check("the GHL read-back and the drafts")
            contracted = set(c.get("room_id") for c in (snapshot.get("contracted_rooms") or [])
                             if isinstance(c, dict) and c.get("room_id"))

            mirror = False
            if not dry:
                off = ghl_sync.mirror_status()
                if off is not None:
                    _ghl_note(result, NOT_CONFIGURED)   # once per run; the mirror is off, nothing is called
                else:
                    mirror = True
                    if ghl is None:
                        try:
                            from shared.ghl import GHL
                            ghl = GHL()
                        except Exception as exc:  # noqa: BLE001
                            result["ghl_errors"].append({"code": "ghl_client_failed", "room_id": None,
                                                         "detail": str(exc)[:400]})
            if mirror:
                _ghl_read_back(work, entries, order, now, ghl, result, contracted)
            _draft_all(work, entries, order, now, meter, dry, result, meter, lease)
            if mirror:
                _ghl_sync(work, entries, order, now, ghl, result)
            if not dry:
                _save_titles(work, entries, order, result)
        except LockLost:
            _on_lock_lost(lease, result, now)
        _count_actions(entries, result)
        result["counts"]["ghl_errors"] = len(result["ghl_errors"])
        if meter is not None:
            result["llm"] = {"calls": dict(meter.calls), "projected_usd": round(meter.spent, 4),
                             "budget_usd": meter.budget, "max_classify": meter.max_classify}
            if meter.hit:
                n = result["counts"]["budget_deferred"]
                result["budget"] = meter.hit
                if meter.hit == CEILING_HIT:
                    result["llm"]["ceiling_refusals"] = meter.ceiling_refusals
                    result["warnings"].append(
                        "LLM SPEND CEILING: shared.llm refused a model call at its cumulative spend ceiling "
                        "(the laptop's llm.spend_usd counter, shared by every laptop job that calls the model; "
                        "the Modal reply engine's counter is separate, so resetting that one does not lift this "
                        "stop). This is not this run's own budget of $%.2f ($%.2f projected so far). %d draft%s or "
                        "classification%s wait, unread, and every run defers them until the ceiling is raised "
                        "or the counter reset. Check it with: %s" % (
                            meter.budget, meter.spent, n, "" if n == 1 else "s", "" if n == 1 else "s",
                            CEILING_CHECK))
                else:
                    what = ("the classifier cap of %d calls" % meter.max_classify if meter.hit == "classify_cap"
                            else "the run budget of $%.2f" % meter.budget)
                    result["warnings"].append(
                        "RUN BUDGET: this run reached %s ($%.2f projected). %d draft%s or classification%s wait "
                        "for the next run. The shared LLM spend ceiling is separate; check it with: %s" % (
                            what, meter.spent, n, "" if n == 1 else "s", "" if n == 1 else "s", CEILING_CHECK))

        jobs = _collect_jobs(work, snapshot, entries, now)
        result["counts"]["pending"] = len([j for j in jobs if (j["thread"].get("pending") or {}).get("text")])
        waiting = set(j["room_id"] for j in jobs if reply_skipped(j["due"], j["thread"]))
        result["counts"]["waiting_on_you"] = len(waiting)
        _fold_reviews(result, waiting, set(b["room_id"] for b in blocked if b["new"]))
        revivable = _revivable(work)
        result["counts"]["errors"] = len(result["errors"])
        result["status"] = _status(result)

        if not dry and result.get("lock_lost") is None:
            try:
                new_cards = 0
                for j in jobs:
                    if j.get("new_draft") or _card_owed(j["thread"]):
                        if _draft_card(real, send, j, result, path, lease):
                            new_cards += 1
                fingerprint = "%s|%s" % (snapshot.get("generated_at"), _ct(now).strftime("%Y-%m-%d"))
                # a stage override is recorded once (the thread then holds GHL's
                # stage), so a same-day rerun that finds one still sends the card
                _summary_card(real, send, result, now, fingerprint, new_cards, lease,
                              force=bool(result["counts"]["blocked_new"] or result.get("stage_overrides")))
            except LockLost:
                _on_lock_lost(lease, result, now)
            result["counts"]["errors"] = len(result["errors"])
            result["status"] = _status(result)
        _write_atomic(path, render_batch(result, jobs, revivable, now))
        if not dry and result.get("lock_lost") is None:
            try:
                _remember_blocked(real, blocked, snapshot, now)
            except LockLost:
                # the batch is written: the next run lists these rooms again
                _on_lock_lost(lease, result, now)
                result["status"] = _status(result)
        if not dry and result.get("lock_lost") is None and (lease is None or lease.lost is None):
            # bookkeeping after the batch, like the summary fingerprint: written
            # under the lease's store, not through a renewal
            _remember_processed(_unleased(real), snapshot, now)
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)


def _remember_processed(store, snapshot: Dict[str, Any], now: datetime) -> None:
    """Record that this --run went through the whole snapshot (see PROCESSED).
    A store failure is only logged: the watch then asks for one more --run."""
    revision = collect.snapshot_revision(snapshot)

    def fn(cur):
        rec = dict(cur or {}) if isinstance(cur, dict) else {}
        rec[PROCESSED] = {"revision": revision, "as_of": _utc_iso(now)}
        return rec

    try:
        store.mutate(TICK_KEY, fn)
    except Exception as exc:  # noqa: BLE001 - bookkeeping never fails the run
        logger.warning("upwork_followup: could not record the processed snapshot: %s", exc)


def _blocked_now(store, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    """``blocked_rooms(snapshot)``, each with ``new``: not yet listed in a
    batch for this block (``TICK_KEY[BLOCKED_LISTED]``)."""
    try:
        listed = (store.get(TICK_KEY) or {}).get(BLOCKED_LISTED) or {}
    except Exception:  # noqa: BLE001 - unreadable: list them (a repeat is harmless)
        listed = {}
    out = []
    for b in blocked_rooms(snapshot):
        prev = listed.get(b["room_id"]) if isinstance(listed, dict) else None
        out.append(dict(b, new=not isinstance(prev, dict) or prev.get("blocked_at") != b["blocked_at"]))
    return out


def _remember_blocked(store, blocked: List[Dict[str, Any]], snapshot: Dict[str, Any], now: datetime) -> None:
    """Record the blocked rooms this batch listed, so the next batches leave
    them out (--status keeps showing them). A room the pull shows unblocked
    is dropped from the record, so a later block is listed again."""
    in_pull = set(r.get("room_id") for r in (snapshot.get("rooms") or []) if isinstance(r, dict))
    blocked_ids = set(b["room_id"] for b in blocked)
    new = [b for b in blocked if b["new"]]
    try:
        listed = (store.get(TICK_KEY) or {}).get(BLOCKED_LISTED) or {}
    except Exception:  # noqa: BLE001
        listed = {}
    unblocked = [rid for rid in listed if rid in in_pull and rid not in blocked_ids]
    if not new and not unblocked:
        return

    def fn(cur):
        cur = dict(cur or {})
        rec = dict(cur.get(BLOCKED_LISTED) or {})
        for rid in unblocked:
            rec.pop(rid, None)
        for b in new:
            rec[b["room_id"]] = {"blocked_at": b["blocked_at"], "listed_at": now.astimezone(timezone.utc).isoformat()}
        cur[BLOCKED_LISTED] = rec
        return cur

    try:
        store.mutate(TICK_KEY, fn)
    except LockLost:
        raise
    except Exception as exc:  # noqa: BLE001 - the next run lists them again
        logger.warning("upwork_followup: could not record the blocked rooms: %s", exc)


def _revivable(store) -> List[Dict[str, Any]]:
    try:
        meta = store.get(sequence.META_KEY) or {}
    except Exception:  # noqa: BLE001
        return []
    out = []
    for rid, entry in sorted((meta.get("revivable") or {}).items()):
        if isinstance(entry, dict):
            out.append(dict(entry, room_id=rid))
    return out


def _collect_jobs(store, snapshot, entries, now) -> List[Dict[str, Any]]:
    rooms = dict((r.get("room_id"), r) for r in (snapshot.get("rooms") or []) if isinstance(r, dict))
    jobs = []
    for key in _thread_keys(store):
        try:
            thread = store.get(key)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(thread, dict):
            continue
        rid = thread.get("room_id") or key[len(sequence.PREFIX):]
        e = entries.get(rid) or {}
        room = rooms.get(rid)
        due = sequence.due_summary(thread, now)
        acts = e.get("acts") or []
        jobs.append({
            "room_id": rid, "thread": thread, "room": room, "due": due,
            "client": thread.get("client") or (room or {}).get("client") or "unknown client",
            "job_title": (room or {}).get("job_title") or thread.get("job_title") or "",
            "in_snapshot": room is not None,
            "new_draft": e.get("new_draft"), "would_draft": e.get("would_draft"),
            "draft_error": e.get("draft_error"), "draft_skipped": e.get("draft_skipped"),
            "resurfaced": any(a.get("type") == "resurface" for a in acts),
            "deferred": any(a.get("type") == "deferred" for a in acts),
        })
    jobs.sort(key=lambda j: (str(j["client"]).lower(), j["room_id"]))
    return jobs


# ------------------------------------------------------------------ cards
# ntfy topics are public unless NTFY_TOKEN is set (or Lorenzo accepted the risk
# with NTFY_ALLOW_SENSITIVE). On a public topic the push carries nothing that
# comes from a client and no local path: no client or company name, no job
# title, no draft text, no private notes. The full card goes on the email leg
# only (jobs/upwork_rooms.py push_body does the same).
def card_body(job: Dict[str, Any]) -> str:
    thread, room = job["thread"], job["room"] or {}
    pending = thread.get("pending") or {}
    meta = _meta_for(thread)
    lines = ["%s | %s | %s | stage %s" % (_kind_label(pending.get("kind"), pending.get("touch")), job["client"],
                                          job["job_title"] or "job title unknown", thread.get("stage"))]
    if meta.get("problems"):
        lines.append("Needs edit: %s" % ", ".join(meta["problems"]))
    if meta.get("proposes_call"):
        lines.append("Suggests a call: check the two times against your calendar.")
    if meta.get("needs_you"):
        lines.append("Needs you: %s" % "; ".join(meta["needs_you"]))
    lines += ["", pending.get("text") or "", "", "Open room: %s" % room_url(job["room_id"]), "",
              "For you, not the client:"]
    lines += for_you_bullets(room, thread)
    return "\n".join(lines)


def email_configured() -> bool:
    """True when shared.notify has an email leg to send on (checked, never read out)."""
    try:
        return notify_mod._email_config() is not None
    except Exception:  # noqa: BLE001
        return False


def _where_to_read() -> str:
    if email_configured():
        return "The full card went by email."
    return ("Read it in today's drafts file on the laptop (.tmp/upwork_followup/), or run "
            "python3 -m jobs.upwork_followup --status.")


def public_draft_title(kind: str, touch: Optional[int]) -> str:
    what = "T%s" % touch if kind == "touch" else ("reply" if kind == "reply" else "check-in")
    return "Upwork: 1 new draft (%s)" % what


def public_draft_body() -> str:
    return ("A new Upwork draft is ready. Names and text are withheld: this ntfy topic is public. %s"
            % _where_to_read())


def _notified_state(record: Any) -> str:
    if isinstance(record, dict):
        if record.get("shadow"):
            return "shadow"
        if record.get("test"):
            return "test"
        if "sent" in record:
            return "delivered" if record.get("sent") else "failed"
    return "delivered"


def _emit(send, result: Dict[str, Any], title: str, body: str, public_title: str, public_body: str,
          priority: str = "default") -> str:
    """One card. Protected topic: the full title and body (truncated to ntfy's
    limit with a pointer to the drafts file). Public topic: ``public_title`` and
    ``public_body`` only; the full card (its real title as the first line) is
    the email leg."""
    if topic_is_protected():
        push_title, push = title, truncate_bytes(body, CARD_MAX_BYTES,
                                                 "(truncated; the full text is in %s)" % result["batch_path"])
        email = body
    else:
        push_title, push = public_title, public_body
        email = "%s\n\n%s" % (title, body)
    try:
        record = send(push_title, push, priority=priority, tags=["briefcase"], email_message=email)
    except Exception as exc:  # noqa: BLE001 - a card never fails the tick
        logger.warning("upwork_followup: notify failed: %s", exc)
        result["notify_errors"].append(str(exc)[:300])
        return "failed"
    return _notified_state(record)


def _card_owed(thread: Dict[str, Any]) -> bool:
    """A draft recorded by a run that died before its card went out."""
    meta = _meta_for(thread)
    return bool((thread.get("pending") or {}).get("text")) and bool(meta) and not meta.get("card_sent_at")


def _unleased(store):
    """The store under a LeasedStore. Bookkeeping for a card that already went
    out (card_sent_at, the summary fingerprint) is written there even after a
    lost lease, so a card is never sent twice."""
    return store.inner if isinstance(store, LeasedStore) else store


def _draft_card(store, send, job: Dict[str, Any], result: Dict[str, Any], path: Path,
                lease: Optional[RunLease] = None) -> bool:
    thread = job["thread"]
    meta = _meta_for(thread)
    if not meta:
        return False
    if lease is not None:
        lease.renew("the card for %s" % job["room_id"])     # the heartbeat before each card
    title = card_title(meta["kind"], meta.get("touch"), job["client"])
    state = _emit(send, result, title, card_body(job), public_draft_title(meta["kind"], meta.get("touch")),
                  public_draft_body())
    result["cards"].append({"title": title, "room_id": job["room_id"], "card_id": meta["card_id"],
                            "state": state, "late": not job.get("new_draft")})
    _note_state(result, state)
    if state == "failed":
        return False
    cid = meta["card_id"]
    at = result["now"]

    def fn(cur):
        t = copy.deepcopy(cur)
        m = t.get("draft_meta") or {}
        if m.get("card_id") == cid:
            m["card_sent_at"] = at
            t["draft_meta"] = m
        return t

    try:
        _mutate(_unleased(store), job["room_id"], fn)
    except Exception as exc:  # noqa: BLE001
        result["errors"].append("%s: could not mark the card sent: %s" % (job["room_id"], exc))
    return True


def _note_state(result: Dict[str, Any], state: str) -> None:
    prev = result.get("cards_state")
    result["cards_state"] = state if prev in (None, "none", state) else "mixed"


def public_snapshot_error(err: str) -> str:
    """The snapshot error for a public push: the kind only, never the OS error
    text (it can hold a local path). ``unreadable: [Errno 13] ...`` becomes
    ``unreadable (OSError)``, a JSON or encoding failure ``unreadable
    (ValueError)``; the detail stays in the email body and Job_Log."""
    kind, _, detail = (err or "").partition(":")
    if kind == "unreadable":
        return "unreadable (%s)" % ("OSError" if "[Errno" in detail else "ValueError")
    if kind == "future":
        return "stamped in the future"
    return kind or "unusable"


def summary_text(result: Dict[str, Any], public: bool = False) -> str:
    """The run summary. ``public``: for an unprotected ntfy topic, so no path
    and nothing a client wrote (the warnings and counts carry neither; a
    snapshot error is reduced to its kind; blocked rooms are only counted)."""
    c = result["counts"]
    dry = result.get("mode") == "dry-run"
    lines = list(result["warnings"])
    if result.get("snapshot_error"):
        shown = public_snapshot_error(result["snapshot_error"]) if public else result["snapshot_error"]
        lines.append("No batch this run: the snapshot is %s. Nothing was drafted. Run --print-collect, the "
                     "calls and --ingest." % shown)
    for note in result.get("notes") or []:
        lines.append("Note: %s." % note)
    overrides = result.get("stage_overrides") or []
    if overrides and public:
        one = len(overrides) == 1
        lines.append("%d stage%s you set %s overridden by %s this run; the batch names %s." % (
            len(overrides), "" if one else "s", "was" if one else "were",
            "a GHL card move" if one else "GHL card moves", "it" if one else "them"))
    else:
        lines += [stage_override_line(o) for o in overrides]
    drafted = c.get("drafted", 0)
    if dry:
        head = "%d would draft (dry run: no model call, nothing saved)" % drafted
    else:
        head = "%d new draft%s (%d need edit)" % (drafted, "" if drafted == 1 else "s", c.get("needs_edit", 0))
    lines.append("%s, %d pending in total, %d to check, %d GHL error%s, %d error%s." % (
        head, c.get("pending", 0), c.get("needs_review", 0), c.get("ghl_errors", 0),
        "" if c.get("ghl_errors", 0) == 1 else "s", c.get("errors", 0), "" if c.get("errors", 0) == 1 else "s"))
    lines.append("Rooms %d, enrolled %d, sent detected %d, replies %d, won %d, lost %d, skipped %d, deferred %d%s."
                 % (c.get("rooms", 0), c.get("enrolled", 0), c.get("sent_detected", 0), c.get("replies", 0),
                    c.get("won", 0), c.get("lost", 0), c.get("skipped", 0), c.get("deferred", 0),
                    ", over the %s %d" % ("LLM spend ceiling" if result.get("budget") == CEILING_HIT
                                          else "run budget", c["budget_deferred"])
                    if c.get("budget_deferred") else ""))
    if c.get("waiting_on_you"):
        n = c["waiting_on_you"]
        lines.append("Needs you: %d client%s still waiting on a reply that was skipped." % (n, "" if n == 1 else "s"))
    new_blocked = [b for b in result.get("blocked") or [] if b.get("new")]
    if new_blocked and public:
        lines.append("%d room%s blocked on Upwork (no drafts)." % (len(new_blocked),
                                                                   "" if len(new_blocked) == 1 else "s"))
    elif new_blocked:
        for b in new_blocked:
            lines.append("Blocked on Upwork (no drafts): %s | %s | room %s, blocked %s." % (
                b["client"], b["job_title"] or "job title unknown", b["room_id"], _on_day(b.get("blocked_at"))))
    if c.get("snapshot_age_h") is not None:
        lines.append("Snapshot age: %.1f h." % c["snapshot_age_h"])
    for note in result.get("ghl_notes") or []:
        lines.append("GHL mirror: %s." % ghl_note_text(note))
    if public:
        lines.append(_where_to_read())
    else:
        lines.append("Drafts file: %s" % result["batch_path"])
    return "\n".join(lines)


def _summary_card(store, send, result: Dict[str, Any], now: datetime, fingerprint: str, new_cards: int,
                  lease: Optional[RunLease] = None, force: bool = False) -> None:
    """Once per fingerprint (snapshot + Central day, or error kind + Central
    day), or whenever this run made a new card, first saw a blocked room or
    recorded a stage override (``force``)."""
    try:
        last = (store.get(TICK_KEY) or {}).get("summary_fingerprint")
    except Exception:  # noqa: BLE001
        last = None
    if new_cards == 0 and not force and last == fingerprint:
        return
    if lease is not None:
        lease.renew("the summary card")                     # the heartbeat before each card
    c = result["counts"]
    title = "Upwork drafts: %d new, %d pending" % (c["drafted"], c["pending"])
    if result.get("snapshot_error"):
        title = ("Upwork drafts: snapshot from the future" if result["snapshot_error"].startswith("future")
                 else "Upwork drafts: no snapshot")
    elif any("STALE" in w for w in result["warnings"]):
        title += " (stale snapshot)"
    elif result.get("budget") == CEILING_HIT:
        title += " (LLM spend ceiling reached)"
    elif result.get("budget"):
        title += " (run budget reached)"
    state = _emit(send, result, title, summary_text(result), title, summary_text(result, public=True),
                  priority="high" if result["status"] == "error" else "default")
    result["cards"].append({"title": title, "room_id": None, "card_id": None, "state": state})
    _note_state(result, state)

    def fn(cur):
        cur = dict(cur or {})
        cur["summary_fingerprint"] = fingerprint
        cur["summary_at"] = now.astimezone(timezone.utc).isoformat()
        return cur

    try:
        _unleased(store).mutate(TICK_KEY, fn)
    except Exception as exc:  # noqa: BLE001
        result["errors"].append("could not record the summary card: %s" % exc)


# ------------------------------------------------------------------ batch
def _meta_for(thread: Dict[str, Any]) -> Dict[str, Any]:
    pending = thread.get("pending") or {}
    meta = thread.get("draft_meta") or {}
    if pending.get("card_id") and meta.get("card_id") == pending.get("card_id"):
        return meta
    return {}


def _job_header(job: Dict[str, Any], what: str) -> List[str]:
    thread = job["thread"]
    return ["### %s | %s | %s" % (what, job["client"], job["job_title"] or "job title unknown"),
            "",
            "Stage: %s (set by %s) | room %s" % (thread.get("stage"), thread.get("stage_set_by"), job["room_id"]),
            "Open room: %s" % room_url(job["room_id"])]


def _draft_block(job: Dict[str, Any], now: datetime) -> List[str]:
    thread = job["thread"]
    pending = thread.get("pending") or {}
    meta = _meta_for(thread)
    what = _kind_label(pending.get("kind"), pending.get("touch"))
    lines = _job_header(job, what)
    if job.get("new_draft"):
        lines.append("New today.")
    elif job.get("resurfaced"):
        lines.append("Shown again: drafted %s and not sent yet (dropped as skipped after 7 days)."
                     % _day(pending.get("issued_at")))
    else:
        lines.append("Pending since %s." % _day(pending.get("issued_at")))
    if meta.get("proposes_call"):
        lines.append("Suggests a call: check the two times against your calendar before sending.")
    if meta.get("problems"):
        lines.append("Needs edit: %s" % ", ".join(meta["problems"]))
    if meta.get("needs_you"):
        lines.append("Needs you:")
        lines += ["- %s" % n for n in meta["needs_you"]]
    lines += ["", _fence(pending.get("text") or ""), "", "For you, not the client:"]
    lines += for_you_bullets(job["room"], thread)
    lines.append("")
    return lines


def _one_line(job: Dict[str, Any], text: str) -> str:
    extra = "" if job["in_snapshot"] else " (not in today's snapshot)"
    return "- %s | %s | %s | room %s%s" % (job["client"], job["job_title"] or "job title unknown", text,
                                            job["room_id"], extra)


def render_batch(result: Dict[str, Any], jobs: List[Dict[str, Any]], revivable: List[Dict[str, Any]],
                 now: datetime) -> str:
    c = result["counts"]
    local = _ct(now)
    out = ["# Upwork follow-up drafts, %s" % local.strftime("%A %Y-%m-%d"), ""]
    out.append("Mode: %s. Run at %s CT. Status: %s." % (
        result["mode"] + (" (nothing saved, no model call, no card)" if result["mode"] == "dry-run" else ""),
        local.strftime("%H:%M"), result["status"]))
    age = c.get("snapshot_age_h")
    out.append("Snapshot: generated %s, %s old." % (
        result.get("snapshot_generated_at") or "unknown", "%.1f h" % age if age is not None else "unknown age"))
    for w in result["warnings"]:
        out += ["", "**WARNING: %s**" % w]
    out += ["", "Counts: %d rooms | %d enrolled | %d %s (%d needs edit) | %d pending | %d sent detected | "
                "%d client replies | %d won | %d lost | %d skipped | %d deferred | %d to check | %d GHL errors | "
                "%d errors" % (c["rooms"], c["enrolled"], c["drafted"],
                               "would draft" if result["mode"] == "dry-run" else "drafted", c["needs_edit"],
                               c["pending"], c["sent_detected"], c["replies"], c["won"], c["lost"], c["skipped"],
                               c["deferred"], c["needs_review"], c["ghl_errors"], c["errors"])]
    if result["mode"] == "run":
        out.append("Cards: %s." % cards_note(result))
    for note in result["ghl_notes"]:
        out.append("GHL mirror: %s." % ghl_note_text(note))
    for note in result["notes"]:
        out.append("Note: %s." % note)
    clients = dict((j["room_id"], j.get("client")) for j in jobs)
    for o in result.get("stage_overrides") or []:
        out.append("Stage override: %s" % stage_override_line(o, clients.get(o["room_id"])))
    if result.get("llm"):
        out.append("Model use this run: %s calls, $%.2f projected worst case (run budget $%.2f)." % (
            sum(result["llm"]["calls"].values()), result["llm"]["projected_usd"], result["llm"]["budget_usd"]))
    out.append("")

    by_room = dict((j["room_id"], j) for j in jobs)
    waiting = [j for j in jobs if reply_skipped(j["due"], j["thread"])]
    if waiting:
        out += ["## Needs you", ""]
        for j in waiting:
            out.append("- %s | %s | %s | room %s | %s" % (
                j["client"], j["job_title"] or "job title unknown", due_text(j["due"], j["thread"]), j["room_id"],
                room_url(j["room_id"])))
        out += ["", "Each of these clients wrote last, and the reply drafted for them was dropped unsent (it "
                    "expired twice, 7 days each, or was cleared); no new draft comes. Answer in the room, or "
                    "--resume <room_id> for a fresh draft on the next run, or --stop / --stage to close it.", ""]

    check = result["check"]
    if check or result["errors"] or result["dropped"]:
        out += ["## Check these", ""]
        for item in check:
            j = by_room.get(item["room_id"]) or {}
            detail = ", ".join("%s %s" % (k, v) for k, v in sorted(item["detail"].items()) if v is not None)
            out.append("- %s | %s | %s%s | room %s | %s" % (
                j.get("client", "unknown client"), j.get("job_title") or "job title unknown", item["reason"],
                " (%s)" % detail if detail else "", item["room_id"], room_url(item["room_id"])))
        for d in result["dropped"]:
            j = by_room.get(d["room_id"]) or {}
            out.append("- %s | %s | %s draft dropped, no card: %s | room %s" % (
                j.get("client", "unknown client"), j.get("job_title") or "job title unknown",
                _kind_label(d["kind"], d["touch"]), d["reason"], d["room_id"]))
        for err in result["errors"]:
            out.append("- error: %s" % err)
        out.append("")

    new_blocked = [b for b in result.get("blocked") or [] if b.get("new")]
    if new_blocked:
        out += ["## Blocked on Upwork (no drafts)", ""]
        for b in new_blocked:
            out.append("- %s | %s | blocked %s | room %s" % (b["client"], b["job_title"] or "job title unknown",
                                                              _on_day(b.get("blocked_at")), b["room_id"]))
        out += ["", "Listed once; --status keeps showing them.", ""]

    for stage, label in STAGE_ORDER:
        group = [j for j in jobs if j["thread"].get("stage") == stage]
        out += ["## %s (%d)" % (label, len(group)), ""]
        if not group:
            out += ["(none)", ""]
            continue
        lines = []
        for j in group:
            pending = j["thread"].get("pending") or {}
            if pending.get("text"):
                out += _draft_block(j, now)
            elif j.get("would_draft"):
                kind, touch = j["would_draft"]
                out += _job_header(j, _kind_label(kind, touch))
                out += ["Would draft %s now (dry run: no model call, nothing saved)." % _kind_label(kind, touch),
                        ""]
            elif j.get("draft_error"):
                lines.append(_one_line(j, "draft failed (%s), retried on the next run" % j["draft_error"]))
            elif stage in sequence.DRAFTING_STAGES or stage == "follow_up_later":
                due = j["due"]
                text = due_text(due, j["thread"])
                if j.get("deferred"):
                    text += ", deferred to the next run (10 new drafts per run)"
                elif pending and pending.get("text") is None:
                    text = "draft reserved but not written yet; the next run fills it"
                if stage == "follow_up_later" and j["thread"].get("follow_up_at") and due.get("kind") != "checkin":
                    text = "follow up on %s" % j["thread"].get("follow_up_at")
                lines.append(_one_line(j, text + "; status %s" % j["thread"].get("status")))
            else:
                lines.append(_one_line(j, "status %s, stage set by %s on %s" % (
                    j["thread"].get("status"), j["thread"].get("stage_set_by"),
                    _day(j["thread"].get("stage_changed_at")))))
        if lines:
            out += lines + [""]

    if revivable:
        out += ["## Revivable (not enrolled automatically; --enroll <room_id> brings one in)", ""]
        for r in revivable:
            out.append("- %s | %s | last client message %s | room %s" % (
                r.get("client") or "unknown client", r.get("job_title") or "job title unknown",
                _day(r.get("last_client_at")), r["room_id"]))
        out.append("")

    if result["ghl_errors"]:
        out += ["## GHL mirror errors (the tick carried on)", ""]
        for g in result["ghl_errors"]:
            out.append("- %s | room %s | %s" % (g.get("code"), g.get("room_id"), g.get("detail")))
        out.append("")

    out += ["## Re-stage a job", "",
            "    python3 -m jobs.upwork_followup --stage <room_id or client/title fragment> <stage>",
            "",
            "Stages: %s. Drafts only in new_reply and proposal_sent." % ", ".join(sequence.STAGES), ""]
    return "\n".join(out)


def ghl_note_text(note: str) -> str:
    if note == NOT_CONFIGURED:
        return ("off (%s: the Upwork pipeline is not in config/ids.json pipelines.upwork yet). Stages live in "
                "the local store; move them with --stage" % NOT_CONFIGURED)
    return note


def cards_note(result: Dict[str, Any]) -> str:
    n = len(result["cards"])
    state = result.get("cards_state")
    if not n:
        return "none this run (nothing new since the last card)"
    if state == "shadow":
        return ("%d recorded in the shadow log only (MODE=shadow; NOTIFY_SHADOW_SEND=1 delivers them to your own "
                "topic and inbox). This file is your copy" % n)
    if state == "test":
        return "%d captured with NOTIFY=off" % n
    return "%d sent (%s)" % (n, state)


def render_error_batch(result: Dict[str, Any], now: datetime, snap: Path) -> str:
    local = _ct(now)
    return "\n".join([
        "# Upwork follow-up drafts, %s" % local.strftime("%A %Y-%m-%d"), "",
        "**ERROR: no batch this run. The snapshot is %s (%s).**" % (result["snapshot_error"], snap), "",
        "Nothing was drafted. Run `python3 -m jobs.upwork_followup --print-collect`, make the read-only calls, "
        "save the raw JSON, then `--ingest` it and run the tick again.", ""])


def _log(result: Dict[str, Any]) -> None:
    details = dict(result["counts"])
    details.update({
        "batch": result["batch_path"],
        "cards": len(result["cards"]),
        "cards_state": result.get("cards_state"),
        "warnings": [w[:200] for w in result["warnings"]],
    })
    if result.get("snapshot_error"):
        details["snapshot_error"] = result["snapshot_error"]
    if result["errors"]:
        details["error"] = "; ".join(result["errors"])[:500]
    if result["ghl_notes"]:
        details["ghl"] = result["ghl_notes"]
    if result["ghl_errors"]:
        details["ghl_error_codes"] = sorted(set(g.get("code") for g in result["ghl_errors"]))
    if result["dropped"]:
        details["dropped"] = len(result["dropped"])
    if result.get("llm"):
        details["llm"] = result["llm"]
    if result.get("budget"):
        details["budget_hit"] = result["budget"]
    if result.get("locked"):
        details["locked_by"] = result["locked"]
    if result.get("lock_taken_over"):
        details["lock_taken_over"] = result["lock_taken_over"]
    if result.get("lock_lost"):
        details["lock_lost"] = result["lock_lost"]
    if result.get("deferred_rooms"):
        details["deferred_rooms"] = result["deferred_rooms"]
    if result.get("stage_overrides"):
        details["stage_overrides"] = result["stage_overrides"]
    if result["notify_errors"]:
        details["notify_errors"] = len(result["notify_errors"])
    log_run(JOB_NAME, result["status"] or "error", details)


def to_json(result: Dict[str, Any]) -> str:
    return json.dumps(result, indent=2, default=str)
