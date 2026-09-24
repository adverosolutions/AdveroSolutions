"""Upwork follow-up watch: the cheap, frequent trigger (plan + light ingest).

A Claude scheduled task (``watch_task_prompt.md``) runs every 30 minutes on
weekdays. Each run makes ONE read-only MCP call, ``upwork__get_messages``
``list_rooms`` (first page, ``{"limit": 50, "room_type": "ALL"}``), saves it,
and asks :func:`plan` what to do next:

* ``none``: nothing to do (or a full run must wait, see below); the run stops.
* ``run``: the data is in, but no ``--run`` has finished on it yet; the
  session only runs ``--run``.
* ``light``: only the listed rooms need fresh messages. The session calls
  ``list_messages`` for each, :func:`ingest_light` merges them into the
  existing snapshot, and ``--run`` runs as always.
* ``full``: ``--mark-full-start``, then the whole collect of
  ``collect_calls.md``, ``--ingest``, ``--run``.

Nothing here writes to Upwork, calls a model, or writes the store. The plan
reads the snapshot, the full-run marker, the store (threads and the tick's
processed mark) and, only when ``ghl_sync.mirror_status()`` says the Upwork
pipeline is configured, GHL through ``ghl_sync.read_back_stage`` (a GET). The
light ingest writes only the snapshot file; :func:`full_marker` is written by
``--mark-full-start``.

The last full collect
---------------------
The snapshot's ``generated_at`` is the ``collected_at`` of the last successful
full ``--ingest`` (the light ingest never changes it), so "a full collect has
completed today" means: the snapshot exists and its ``generated_at`` falls on
today's America/Chicago date. The full ingest also writes ``listed_rooms``,
every room id on that pull's list_rooms pages.

Full runs in progress and failed full runs
------------------------------------------
Before a full collect the session runs ``--mark-full-start``, which writes
``.tmp/upwork_followup/full_start.json``: ``{"started_at", "snapshot_before"}``
(the snapshot's ``generated_at`` at that moment). The full run succeeded once
the snapshot's ``generated_at`` differs from ``snapshot_before`` (no clock is
compared). While it has not, and the plan would say ``full``:

* started less than ``FULL_IN_PROGRESS`` (45 minutes) ago: it is still
  running, so no second full starts;
* started less than ``FULL_RETRY`` (2 hours) ago: it failed; it is retried
  once 2 hours have passed, not every 30 minutes;
* otherwise the full run starts again (the reason says it is a retry).

A waiting full run still lets ``light`` and ``run`` go ahead when today's
snapshot is there; with no usable snapshot the plan is ``none`` and its
``_run`` reason says why and when the next try is.

Plan rules, in order
--------------------
``full`` when:

1. the rooms file cannot be read, is an error response, or holds no
   list_rooms page;
2. the snapshot is missing or unreadable, its ``generated_at`` is unreadable
   or in the future, or it is not from today (CT): the first run of each CT
   day is always full, so due touches, contracts and offers are read fresh;
3. a candidate room (``ONE_ON_ONE``/``INTERVIEW`` or no type, not an Upwork
   support room, no ``contractId``) that is not in the snapshot's ``rooms``
   and not in its ``listed_rooms`` shows activity newer than ``generated_at``
   (or no readable activity time): a brand-new room needs the full linking
   logic (proposals, ``get_room``). A room the last full collect listed and
   left out (unlinked, too old) stays out until tomorrow's full run, so a
   chatty out-of-scope room cannot force a full collect every 30 minutes.
   Rooms with a contract are never a trigger: an active contract client
   writing daily must not force a full collect;
4. a room in the snapshot's ``rooms`` whose card now carries a
   ``contractId`` (a contract started: the thread is won, which only the full
   ingest records);
5. the page says ``hasMore`` and even its oldest card is newer than
   ``generated_at``: more than 50 rooms moved, so rooms past page 1 may too.

(each subject to the full-run marker above). Then ``light`` when a room in
the snapshot's ``rooms`` has new activity (below), and/or (GHL configured)
Lorenzo moved its thread's card in GHL. Then ``run`` when the tick's
processed mark (``tick.TICK_KEY[tick.PROCESSED]["revision"]``) is not the
snapshot's ``collect.snapshot_revision``: an ingest or a light merge whose
``--run`` was locked out, failed, lost its lease or never started. Else
``none``.

"Newer activity" (the comparison, per room in the snapshot's ``rooms``):

* the card's activity is its ``latestStory`` (``id``, ``createdDateTime``),
  with ``last_message_at`` then ``lastActivity`` as the time when the story
  has none (the precedence ``jobs.upwork_rooms.normalize_room`` uses);
* it is already SEEN when the story id is the id of a message in the snapshot
  room, or when its time is at or before the room's watermark: the newest of
  every snapshot message time (room events included), the room's
  ``last_message_at``, the snapshot's ``watch_seen`` entry for the room
  (written by the light ingest only when its pull held the card's story) and
  the thread's ``marks.last_seen_at``; or when the light ingest gave up on
  exactly this story (``watch_gave_up``, see :func:`ingest_light`);
* a card with neither a story id nor a readable time is never flagged: there
  is nothing to compare, and flagging it would repeat every run;
* unseen activity that is Lorenzo's own spoken message (his side by the
  story's own side fields, else the card's ``last_message_side`` /
  ``last_message_from_self`` / ``awaiting_reply_from``, as ``collect`` reads
  them, and not a room event) is NOT flagged: his own message needs no draft,
  and the next full collect (or a light pull of that room for another reason)
  ingests it. A room event is flagged whatever its side: MCP "System event:
  <name>." lines come on Lorenzo's side and can sit on top of a client message
  written just before (``collect.mcp_event_name`` / ``collect.is_system_line``,
  also on the text after a "You: " style prefix). Client or unknown side is
  flagged.

GHL: for each thread (store key ``upwork:<room_id>``) whose room is in the
snapshot's ``rooms`` and not already flagged, and that is not ``won`` by a
contract, ``ghl_sync.read_back_stage`` returns the stage Lorenzo set in GHL
when it differs from both ``thread["stage"]`` and the stage GHL is known to
hold; that room is flagged. ``--run`` applies it with the tick's own read-back
(``apply_external_stage``), after which the stages agree and the read-back
returns None: no repeat. Not configured: no GHL client is built and no call is
made. A GHL failure only skips that thread.

Output of :func:`plan`::

    {"mode": "none" | "run" | "light" | "full", "rooms": [<room_id>, ...],
     "reasons": {<room_id> or "_run": "<short reason>"}, "checked": <cards read>}

``rooms`` is empty unless the mode is ``light``. Reasons are ids, times and
fixed words only, never client text.

Python 3.9. ``now`` is injected.
"""
import copy
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from jobs.upwork_rooms import normalize_room
from services.upwork_followup import collect, ghl_sync, sequence
from shared import slots
from shared.paths import tmp_file

logger = logging.getLogger("services.upwork_followup.watch")

WATCH_ROOMS_NAME = "upwork_followup/watch_rooms.json"
LIGHT_RAW_NAME = "upwork_followup/raw_light.json"
FULL_MARKER_NAME = "upwork_followup/full_start.json"
MODES = ("none", "run", "light", "full")
RUN = "_run"
FULL_IN_PROGRESS = timedelta(minutes=45)
FULL_RETRY = timedelta(hours=2)
# Light pulls in a row (distinct collected_at) that come back without the
# card's latest story before the ingest stops asking for that story.
LIGHT_MISS_CAP = 3
# tick.TICK_KEY / tick.PROCESSED, repeated here so the plan does not import
# the tick (and its model and notify stack); test_watch checks they agree.
TICK_KEY = "upwork_followup:tick"
PROCESSED = "processed"


# ------------------------------------------------------------------ reading
def _dt(value: Any) -> Optional[datetime]:
    return collect._parse_ts_quiet(value)


def _max_dt(values: List[Any]) -> Optional[datetime]:
    times = [t for t in (_dt(v) for v in values) if t is not None]
    return max(times) if times else None


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _ct_clock(value: datetime) -> str:
    return value.astimezone(sequence.CT).strftime("%H:%M CT")


def read_json(path: Any) -> Tuple[Any, Optional[str]]:
    """(data, error). Never raises."""
    try:
        with open(str(path), "r", encoding="utf-8") as fh:
            return json.load(fh), None
    except FileNotFoundError:
        return None, "missing"
    except (OSError, ValueError) as exc:
        return None, "unreadable (%s)" % type(exc).__name__


def room_pages(raw: Any) -> Optional[List[Dict[str, Any]]]:
    """The list_rooms page(s) in a saved rooms file: one page, or a list of
    pages. None when nothing usable is there (an error response, a page that
    is not a list_rooms page, an empty list)."""
    pages = raw if isinstance(raw, list) else [raw]
    if not pages:
        return None
    for page in pages:
        if collect._is_error_response(page) or collect._room_cards(page) is None:
            return None
    return pages


def room_cards(pages: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Room id -> card, the room name unwrapped as the ingest does."""
    cards = {}  # type: Dict[str, Dict[str, Any]]
    for page in pages:
        for card in collect._room_cards(page) or []:
            rid = card.get("id") or card.get("room_id")
            if isinstance(rid, str) and rid:
                card = dict(card, id=rid)
                if isinstance(card.get("roomName"), str):
                    card["roomName"] = collect.participant_text(card["roomName"])
                cards[rid] = card
    return cards


def card_activity(card: Dict[str, Any], self_ids: Set[str]) -> Tuple[Optional[str], Optional[datetime], str]:
    """(story id, activity time, side) of a list_rooms card. The time is
    ``latestStory.createdDateTime``, else ``last_message_at``, else
    ``lastActivity`` (epoch ms in a string on live cards). The side is the
    story's own side fields, else the card's claim about its last message."""
    story = card.get("latestStory") if isinstance(card.get("latestStory"), dict) else {}
    sid = story.get("id")
    sid = str(sid) if sid not in (None, "") and not isinstance(sid, (dict, list, bool)) else None
    at = None
    for value in (story.get("createdDateTime"), card.get("last_message_at"), card.get("lastActivity")):
        at = _dt(value) if value not in (None, "") else None
        if at is not None:
            break
    side = collect.message_side(story, self_ids) if story else "unknown"
    if side == "unknown":
        side = collect._card_last_side(card)
    return sid, at, side


def story_is_event(card: Dict[str, Any]) -> bool:
    """The card's latest story is a room event (an MCP "System event: <name>."
    line or a bold "**X** ended the contract" line), not a spoken message.
    Checked on the whole text and on the text after a "You: " style prefix."""
    story = card.get("latestStory") if isinstance(card.get("latestStory"), dict) else {}
    text = collect.participant_text(story.get("message"))
    if not text:
        return False
    tail = text.split(": ", 1)[-1]
    return any(collect.mcp_event_name(t) is not None or collect.is_system_line(t) for t in (text, tail))


def story_key(story_id: Optional[str], at: Optional[datetime]) -> Optional[str]:
    """One string naming a card's latest story: its id, else its time."""
    if story_id:
        return "id:" + story_id
    return "at:" + _iso(at) if at is not None else None


def _has_contract(card: Dict[str, Any]) -> bool:
    return bool(card.get("contractId") or card.get("contract_id"))


def _candidate(card: Dict[str, Any]) -> bool:
    """Could this room ever be in scope? The ingest's candidate test with no
    age window, and no contract id."""
    if _has_contract(card):
        return False
    return collect._is_candidate(card, normalize_room(card), None)


def _store_view(store: Any) -> Tuple[Dict[str, Dict[str, Any]], Optional[str], Optional[str]]:
    """(room id -> thread, processed revision, error), read only. ({}, None,
    why) when the store cannot be read."""
    if store is None:
        return {}, None, "no store"
    try:
        out = {}  # type: Dict[str, Dict[str, Any]]
        for key in store.keys(sequence.PREFIX):
            if key in (sequence.META_KEY, sequence.LEGACY_META_KEY):
                continue
            thread = store.get(key)
            if isinstance(thread, dict):
                out[thread.get("room_id") or key[len(sequence.PREFIX):]] = thread
        rec = store.get(TICK_KEY)
        done = rec.get(PROCESSED) if isinstance(rec, dict) else None
        return out, (done or {}).get("revision") if isinstance(done, dict) else None, None
    except Exception as exc:  # noqa: BLE001 - a store failure only skips the store checks
        return {}, None, type(exc).__name__


def seen(room: Dict[str, Any], thread: Optional[Dict[str, Any]], snapshot: Dict[str, Any],
         story_id: Optional[str], at: Optional[datetime]) -> bool:
    """Has the engine already ingested the activity a card shows? See the
    module docstring, "Newer activity"."""
    rid = room.get("room_id")
    messages = [m for m in (room.get("messages") or []) if isinstance(m, dict)]
    if story_id and any(str(m.get("id") or "") == story_id for m in messages):
        return True
    gave_up = snapshot.get("watch_gave_up") if isinstance(snapshot.get("watch_gave_up"), dict) else {}
    key = story_key(story_id, at)
    if key is not None and gave_up.get(rid) == key:
        return True
    if at is None:
        return story_id is None      # nothing to compare: never flagged
    marks = (thread or {}).get("marks") if isinstance((thread or {}).get("marks"), dict) else {}
    watch_seen = snapshot.get("watch_seen") if isinstance(snapshot.get("watch_seen"), dict) else {}
    watermark = _max_dt([m.get("at") for m in messages]
                        + [room.get("last_message_at"), watch_seen.get(rid), marks.get("last_seen_at")])
    return watermark is not None and at <= watermark


# ------------------------------------------------------------- full marker
def full_marker_path(path: Optional[Any] = None) -> Path:
    return Path(path) if path else tmp_file(FULL_MARKER_NAME)


def full_marker(snapshot: Optional[Dict[str, Any]], now: Any) -> Dict[str, Any]:
    """The record ``--mark-full-start`` writes before a full collect."""
    return {"started_at": _iso(slots.ensure_aware(now)),
            "snapshot_before": (snapshot or {}).get("generated_at") if isinstance(snapshot, dict) else None}


def write_full_marker(marker: Dict[str, Any], path: Optional[Any] = None) -> Path:
    target = full_marker_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(marker, fh)
        fh.write("\n")
    os.replace(str(tmp), str(target))
    return target


def full_wait(marker: Any, snapshot: Optional[Dict[str, Any]], now: datetime) -> Tuple[Optional[str], Optional[str]]:
    """(wait reason, retry note). A wait reason means: do not start a full run
    now. A retry note (no wait) means the last full run did not finish and this
    one is its retry. (None, None): no unfinished full run."""
    if not isinstance(marker, dict):
        return None, None
    started = _dt(marker.get("started_at"))
    if started is None:
        return None, None
    current = snapshot.get("generated_at") if isinstance(snapshot, dict) else None
    if current != marker.get("snapshot_before"):
        return None, None              # a full ingest succeeded since the start
    age = now - started
    if age < timedelta(0):
        age = timedelta(0)
    if age < FULL_IN_PROGRESS:
        return ("a full run started at %s is still in progress" % _ct_clock(started)), None
    if age < FULL_RETRY:
        return ("the full run started at %s did not finish; next try after %s"
                % (_ct_clock(started), _ct_clock(started + FULL_RETRY))), None
    return None, "retry: the full run started at %s did not finish" % _ct_clock(started)


# --------------------------------------------------------------------- plan
def _result(mode: str, rooms: List[str], reasons: Dict[str, str], checked: int) -> Dict[str, Any]:
    return {"mode": mode, "rooms": sorted(rooms) if mode == "light" else [], "reasons": reasons,
            "checked": checked}


def plan(rooms_raw: Any, snapshot: Optional[Dict[str, Any]], store: Any, now: Any, ghl: Any = None,
         ghl_factory: Optional[Callable[[], Any]] = None, snapshot_error: Optional[str] = None,
         rooms_error: Optional[str] = None, marker: Any = None) -> Dict[str, Any]:
    """The watch plan for one saved list_rooms result. Read only. See the
    module docstring for every rule. ``marker`` is the full-run marker
    (``--mark-full-start``), or None."""
    now = slots.ensure_aware(now)
    pages = room_pages(rooms_raw) if rooms_error is None else None
    cards = room_cards(pages) if pages is not None else {}
    checked = len(cards)

    def full(reasons: Dict[str, str]) -> Dict[str, Any]:
        wait, retry = full_wait(marker, snapshot, now)
        if wait:
            return _result("none", [], {RUN: "%s (%s)" % (wait, reasons.get(RUN) or "full run needed")}, checked)
        if retry:
            reasons = dict(reasons)
            reasons[RUN] = "%s (%s)" % (reasons.get(RUN) or "full run needed", retry)
        return _result("full", [], reasons, checked)

    if pages is None:
        return full({RUN: "rooms file %s" % (rooms_error or "is not a list_rooms result")})
    if snapshot is None or not isinstance(snapshot.get("rooms"), list):
        return full({RUN: "no snapshot (%s)" % (snapshot_error or "missing")})
    generated = _dt(snapshot.get("generated_at"))
    if generated is None:
        return full({RUN: "snapshot generated_at unreadable"})
    if collect.is_future_stamp(generated, now):
        return full({RUN: "snapshot generated_at is in the future"})
    today = now.astimezone(sequence.CT).date()
    if generated.astimezone(sequence.CT).date() != today:
        return full({RUN: "first run of the CT day (last full collect %s)"
                     % generated.astimezone(sequence.CT).date().isoformat()})

    self_ids = collect._self_ids()
    snap_rooms = dict((r.get("room_id"), r) for r in snapshot["rooms"]
                      if isinstance(r, dict) and r.get("room_id"))
    listed = snapshot.get("listed_rooms")
    listed = set(listed) if isinstance(listed, list) else set()
    threads, processed, store_error = _store_view(store)

    full_reasons = {}  # type: Dict[str, str]
    light = {}  # type: Dict[str, str]
    for rid, card in sorted(cards.items()):
        story_id, at, side = card_activity(card, self_ids)
        if rid in snap_rooms:
            if _has_contract(card):
                full_reasons[rid] = "contract on a tracked room"
                continue
            if seen(snap_rooms[rid], threads.get(rid), snapshot, story_id, at):
                continue
            if story_is_event(card):
                light[rid] = "new room event"
                continue
            if side == "freelancer":
                continue             # Lorenzo's own spoken message: no draft needed
            light[rid] = "new %s activity" % ("client" if side == "client" else "unknown-side")
            continue
        if rid in listed or not _candidate(card):
            continue
        if at is None or at > generated:
            full_reasons[rid] = "room not in the last full collect"
    last = pages[-1]
    if collect._has_more(last):
        times = [card_activity(c, self_ids)[1] for c in (collect._room_cards(last) or [])]
        if times and all(t is not None and t > generated for t in times):
            full_reasons[RUN] = "more than one page of rooms moved since the full collect"
    note = None
    if full_reasons:
        full_reasons.setdefault(RUN, "rooms changed that only the full collect can link")
        decided = full(full_reasons)
        if decided["mode"] == "full":
            return decided
        note = decided["reasons"][RUN]     # a full run is waiting: light and run may still go ahead

    # GHL read-back: only when the Upwork pipeline is configured
    if ghl_sync.mirror_status() is None:
        client = ghl
        if client is None and ghl_factory is not None:
            try:
                client = ghl_factory()
            except Exception as exc:  # noqa: BLE001 - GHL never blocks the watch
                logger.warning("upwork watch: no GHL client (%s); GHL moves wait for the next run",
                               type(exc).__name__)
                client = None
        if client is not None:
            for rid, thread in sorted(threads.items()):
                if rid not in snap_rooms or rid in light or ghl_sync._won_by_contract(thread):
                    continue
                stage = ghl_sync.read_back_stage(thread, client)
                if stage and stage in sequence.STAGES and stage != thread.get("stage"):
                    light[rid] = "GHL stage %s" % stage

    if light:
        reasons = dict(light)
        if note:
            reasons[RUN] = note
        return _result("light", list(light), reasons, checked)
    if store_error is None and processed != collect.snapshot_revision(snapshot):
        why = "the last ingest has not been through a finished --run"
        return _result("run", [], {RUN: "%s; %s" % (why, note) if note else why}, checked)
    reasons = {RUN: note or "no new activity"}
    if store_error:
        reasons[RUN] += " (store unreadable: %s; thread, GHL and --run checks skipped)" % store_error
    return _result("none", [], reasons, checked)


# ------------------------------------------------------------- light ingest
def _msg_key(m: Dict[str, Any]) -> Tuple[Any, ...]:
    if m.get("id"):
        return ("id", m["id"])
    return ("noid", m.get("at"), m.get("side"), m.get("text"))


def merge_messages(existing: List[Dict[str, Any]], pulled: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Existing snapshot messages plus a fresh pull, both oldest first, into
    one list oldest first. A pulled copy replaces the stored one (same id, or
    same time, side and text when there is no id). Order: by time, a message
    with no time first; on a tie the stored message goes before the pulled
    one, then each keeps its own order. Idempotent: merging the same pull
    again gives the same list."""
    pulled_keys = set(_msg_key(m) for m in pulled)
    items = [(0, i, m) for i, m in enumerate(m for m in existing if _msg_key(m) not in pulled_keys)] \
        + [(1, i, m) for i, m in enumerate(pulled)]

    def order(item):
        source, index, msg = item
        ts = _dt(msg.get("at"))
        return (0, 0.0, source, index) if ts is None else (1, ts.timestamp(), source, index)

    return [m for _, _, m in sorted(items, key=order)]


def pull_covers(pulled: List[Dict[str, Any]], story_id: Optional[str], at: Optional[datetime]) -> bool:
    """Does a pull hold the card's latest story: a message with its id, or a
    message at or after its time? A card with neither is covered."""
    if story_id is None and at is None:
        return True
    if story_id and any(str(m.get("id") or "") == story_id for m in pulled):
        return True
    if at is not None:
        return any((_dt(m.get("at")) or at - timedelta(seconds=1)) >= at for m in pulled)
    return False


def ingest_light(snapshot: Optional[Dict[str, Any]], raw: Any, now: Any,
                 rooms_raw: Any = None) -> Tuple[Dict[str, Any], Dict[str, List[str]]]:
    """Merge a light pull into the snapshot. Returns (new snapshot, report
    ``{"merged", "behind", "gave_up", "failed", "not_in_snapshot"}``); the
    input is not changed.

    ``raw`` is ``{"collected_at": "<ISO>", "messages": {"<room_id>":
    <list_messages response>, ...}}``, each response in the same format as the
    full collect's ``messages``. ``rooms_raw`` is the watch's saved list_rooms
    result (optional): its card for a merged room feeds ``last_side`` exactly
    as in the full ingest, and its activity is recorded in ``watch_seen``.

    A pull that does not hold the card's latest story (:func:`pull_covers`:
    empty, or only older messages) is merged but marks nothing seen: the room
    is listed in ``behind``, the card is not used for ``last_side``, and the
    next watch asks for the room again. After ``LIGHT_MISS_CAP`` such pulls in
    a row (distinct ``collected_at``) for the same story, the story is written
    to ``watch_gave_up`` and listed in ``gave_up``, so the watch stops asking;
    the next full collect reads the room anyway.

    Only the listed rooms that are in the snapshot's ``rooms`` change: their
    ``messages`` (merged, see :func:`merge_messages`), ``last_side``,
    ``last_message_at``, ``blocked`` and ``blocked_at``; plus
    ``missing_messages``, ``blocked_rooms``, ``sections.messages``,
    ``watch_seen``, ``watch_misses``, ``watch_gave_up`` and ``last_light``.
    ``generated_at`` (the last full collect), every other room, proposals,
    contracts, offers and job data stay as they are. A room whose pull failed
    is left untouched (``failed``); a room not in the snapshot is skipped
    (``not_in_snapshot``: only the full collect can link it).

    Raises ``collect.IngestError`` (nothing is written) when there is no
    snapshot, the file is not a light pull (not an object, an error response,
    no readable ``collected_at`` or one in the future, no ``messages`` map), or
    no room could be merged."""
    now = slots.ensure_aware(now)
    if snapshot is None or not isinstance(snapshot.get("rooms"), list):
        raise collect.IngestError("there is no snapshot to merge into; run the full collect and --ingest first")
    if not isinstance(raw, dict) or not raw:
        raise collect.IngestError("the light pull is not a JSON object (got %s); nothing was written"
                                  % collect._describe(raw))
    if collect._is_error_response(raw):
        raise collect.IngestError("the light pull is an error response (%s); nothing was written"
                                  % collect._error_summary(raw))
    stamp = raw.get("collected_at")
    collected = _dt(stamp) if isinstance(stamp, str) else None
    if collected is None:
        raise collect.IngestError("collected_at is missing or unreadable; nothing was written")
    if collect.is_future_stamp(collected, now):
        raise collect.IngestError("collected_at %s is in the future (more than %d minutes after this run); "
                                  "check the date and the UTC offset, nothing was written"
                                  % (_iso(collected), collect.MAX_CLOCK_DRIFT.total_seconds() // 60))
    pulled_map = raw.get("messages")
    if not isinstance(pulled_map, dict) or not pulled_map or collect._looks_like_response(pulled_map):
        raise collect.IngestError("messages must be a map of room id to its list_messages response; "
                                  "nothing was written")

    snap = copy.deepcopy(snapshot)
    rooms = dict((r.get("room_id"), r) for r in snap["rooms"] if isinstance(r, dict) and r.get("room_id"))
    pages = room_pages(rooms_raw) if rooms_raw is not None else None
    cards = room_cards(pages) if pages else {}
    self_ids = collect._self_ids()
    collected_iso = _iso(collected)
    report = {"merged": [], "behind": [], "gave_up": [], "failed": [],
              "not_in_snapshot": []}  # type: Dict[str, List[str]]

    def table(key):
        value = snap.get(key)
        return dict(value) if isinstance(value, dict) else {}

    watch_seen, misses, gave_up = table("watch_seen"), table("watch_misses"), table("watch_gave_up")
    missing = [m for m in (snap.get("missing_messages") or []) if isinstance(m, str)]
    was_missing = set(missing)

    for rid in sorted(str(k) for k in pulled_map):
        room = rooms.get(rid)
        if room is None:
            report["not_in_snapshot"].append(rid)
            continue
        ok, pulled = collect.pulled_messages(pulled_map.get(rid), self_ids)
        if not ok:
            report["failed"].append(rid)
            continue
        stored = [dict(m, event=bool(m.get("event"))) for m in (room.get("messages") or []) if isinstance(m, dict)]
        merged = merge_messages(stored, pulled)
        card = cards.get(rid)
        story_id, activity = (card_activity(card, self_ids)[:2] if card is not None else (None, None))
        covered = card is None or pull_covers(pulled, story_id, activity)
        if covered:
            misses.pop(rid, None)
        else:
            # the pull lags the card: nothing from the card may count as seen
            report["behind"].append(rid)
            key = story_key(story_id, activity)
            prev = misses.get(rid) if isinstance(misses.get(rid), dict) else {}
            count = int(prev.get("count") or 0) if prev.get("story") == key else 0
            if prev.get("story") != key or prev.get("collected_at") != collected_iso:
                count += 1
            misses[rid] = {"story": key, "count": count, "collected_at": collected_iso}
            if count >= LIGHT_MISS_CAP and key is not None:
                gave_up[rid] = key
                misses.pop(rid, None)
                report["gave_up"].append(rid)
            card = None
        if card is not None:
            card_last_at = normalize_room(card).get("last_message_at")
        else:
            card, card_last_at = {}, room.get("last_message_at")
        last_side, last_at, blocked, blocked_at = collect.room_state(merged, card, card_last_at, self_ids)
        if not card and not any(not m.get("event") for m in merged):
            last_side, last_at = room.get("last_side"), room.get("last_message_at")
        room.update({"messages": merged, "last_side": last_side, "last_message_at": last_at,
                     "blocked": blocked, "blocked_at": blocked_at})
        mark = _max_dt([m.get("at") for m in merged] + [activity if covered else None, watch_seen.get(rid)])
        if mark is not None:
            watch_seen[rid] = _iso(mark)
        if rid in missing:
            missing.remove(rid)
        report["merged"].append(rid)

    if not report["merged"]:
        raise collect.IngestError("no room could be merged (failed: %s; not in the snapshot: %s); "
                                  "nothing was written" % (", ".join(report["failed"]) or "none",
                                                           ", ".join(report["not_in_snapshot"]) or "none"))
    snap["missing_messages"] = sorted(missing)
    if was_missing and not missing and isinstance(snap.get("sections"), dict):
        snap["sections"]["messages"] = True
    snap["blocked_rooms"] = sorted(r["room_id"] for r in snap["rooms"]
                                   if isinstance(r, dict) and r.get("room_id") and r.get("blocked"))
    snap["watch_seen"] = dict(sorted(watch_seen.items()))
    snap["watch_misses"] = dict(sorted(misses.items()))
    snap["watch_gave_up"] = dict(sorted(gave_up.items()))
    snap["last_light"] = {"collected_at": collected_iso, "rooms": sorted(report["merged"])}
    return snap, report
