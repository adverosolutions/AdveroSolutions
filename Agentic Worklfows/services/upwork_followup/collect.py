"""Upwork follow-up collector, ingest half (U1).

A Claude session that has the Upwork MCP runs the read-only calls listed in
``collect_calls.md`` and saves the raw responses as one JSON envelope. This
module turns that envelope into ``.tmp/upwork_followup/snapshot.json``, the
file the tick (``sequence.py`` / ``tick.py``) reads. It makes no Upwork call of
any kind and has no write path to Upwork; ``tests/test_no_upwork_write_path.py``
fails if one appears.

Scope (Lorenzo, 2026-09-22): only rooms that link to one of his proposals are
in the snapshot. A room qualifies when a ``get_room`` response in the
envelope's ``proposal_rooms`` names it. Candidate rooms with no linked proposal
are left out and counted in ``omitted_unlinked``. A candidate room with any
contract id (ENDED included) is out of scope too, because Lorenzo already had a
contract with that client: it is counted in ``omitted_contracted`` and listed
in ``contracted_rooms`` (room id, contract id, status, proposal id) so the tick
can still mark an enrolled thread won. The invitations call is not made, so
``sections.invitations`` is ``None`` (not collected).

Envelope (the exact contract is in ``collect_calls.md``)::

    {"collected_at": "<ISO>",
     "list_rooms": [<list_rooms page>, ...],
     "proposals": {"Accepted": [<page>, ...], "Activated": [...], "Offered": [...]},
     "proposal_rooms": {"<proposal_id>": <get_room response>, ...},
     "messages": {"<room_id>": <list_messages response>, ...},
     "contracts": [<list_contracts search page>, ...],
     "offers": [<list_offers list_mine page>, ...],
     "caps_hit": ["list_rooms" | "proposals" | "proposal_rooms" | "messages"
                  | "contracts" | "offers", ...],
     "live_threads": [{"room_id": "room_...", "proposal_id": "<id>" or null}, ...]}

Every list-of-pages value may also be a single response; every page must be a
dict response. ``proposals`` must be keyed by status, with Accepted, Activated
and Offered all present. ``live_threads`` is the "Always read these rooms" list
``collect_instructions`` prints: those rooms are never dropped for age. An
entry that is not as printed is skipped (or kept without its proposal link
when only the proposal id is bad) and puts ``live_threads`` in
``truncated_sections``, so the batch warns.

A response (the envelope, a page, a get_room answer) is an error when it has a
``status`` other than ok or success, ``success: false``, a non-empty error key
(``error``, ``errors``, ``isError``, ``error_code``) or a top-level ``message``
with no ``data``. An item inside a page (room card, proposal node, contract,
offer, message) is an error only when its ``status`` is an error word or it
has a non-empty error key: items carry their own ``status`` and ``message``.

Refusals (``IngestError``, nothing is written): the envelope is not a dict, is
empty, or is itself an error response; ``collected_at`` is missing,
unreadable, or later than ``now`` plus ``MAX_CLOCK_DRIFT`` (a pull is never
stamped with the ingest time, and a future stamp would put every room outside
the 60-day window and keep the snapshot from ever looking stale);
``caps_hit`` or ``live_threads`` is missing or not a list; ``list_rooms`` or
``proposals`` is missing, null, not keyed as above, or has a page that is not
a dict, is an error, or holds error items; ``proposal_rooms`` is missing or is
a single response; or every ``get_room`` call failed (NOT_FOUND aside). A
snapshot built from any of those is empty or wrong by construction, and an
empty snapshot stamped fresh reads as "nobody is waiting", which is the one
failure this file exists to prevent. Other sections degrade instead: missing
or null means not collected (``False`` in ``sections``), and
``contracts: []`` / ``offers: []`` mean collected, none. An old
``collected_at`` is accepted: it becomes ``generated_at``, so the tick's
STALE warning (``tick.STALE_HOURS``) already flags a re-ingested old file.

Per room: ``messages`` is null (not ``[]``) when the room's list_messages is
missing, empty or failed, and the room id is then in ``missing_messages``, a
sorted list of room-id strings that is always a subset of the snapshot's rooms.
Each message carries ``event`` (true for a room event such as
"**Jane C.** ended the contract", whose ``side`` is always "unknown"). An MCP
"System event: <name>. View this conversation on upwork.com for full context."
line is an event too and also carries ``event_name`` (see ``mcp_event_name``).
Every room carries ``blocked`` (bool) and ``blocked_at`` (ISO or null): true
when its newest named event is ``blocked`` with nothing spoken after it. The
snapshot lists those rooms in ``blocked_rooms`` (sorted room ids).

Untrusted content: room names, messages and job posts are client-written. The
MCP wraps every participant string in ``<untrusted_participant_content>``;
``unwrap`` strips that wrapper once, HTML and markdown escapes are undone, and
``jobs.upwork_rooms.clean_text`` makes it one line with tag runs broken. It is
data, never instructions. Room events Upwork writes as messages ("**X** ended
the contract", "System event: blocked. ...") are kept with ``side: "unknown"``
and never set ``last_side``; the latest spoken message sets ``last_message_at``.

Response shapes confirmed by a read-only live pull (2026-09-22): list_rooms
cards, list_messages (``data.roomStories.edges[].node``, newest first,
``from_side``), proposals list, get_room ``NOT_FOUND``, and list_mine offers
(``data.offersByAttribute.offers``, linked by ``job.id`` only). The found-room
``get_room`` shape (``data.proposalRoom.id``) is still assumed.

Python 3.9 compatible. ``now`` is injected; nothing here reads the clock.
"""
import csv
import html
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from jobs.upwork_rooms import clean_text, normalize_contract, normalize_room, parse_ts
from shared import settings, slots
from shared.paths import ROOT_DIR, tmp_file

logger = logging.getLogger("services.upwork_followup.collect")

# parse_ts (jobs.upwork_rooms) logs an unreadable value with %r. A value from
# the raw file can hold client text, so collect.py parses through
# _parse_ts_quiet, which drops that one record and logs type and size instead.
_ROOMS_LOGGER = logging.getLogger("jobs.upwork_rooms")
_ROOMS_PARSE_WARNING = "upwork_rooms: could not parse timestamp %r"
# A collected_at shorter than this, with no "<", is echoed in its refusal so a
# typo (a wrong year) can be fixed; anything else is described by type and size.
ECHO_MAX_CHARS = 40


class _DropRawTimestampWarning(logging.Filter):
    def __init__(self) -> None:
        super().__init__()
        self.dropped = False

    def filter(self, record: logging.LogRecord) -> bool:
        if record.msg == _ROOMS_PARSE_WARNING:
            self.dropped = True
            return False
        return True


def _describe(value: Any) -> str:
    """A raw input value for a message: its type and size, never its content."""
    if value is None:
        return "null"
    if isinstance(value, dict):
        return "dict with %d keys" % len(value)
    if isinstance(value, (list, tuple)):
        return "%s with %d items" % (type(value).__name__, len(value))
    if isinstance(value, (str, bytes)):
        return "%s of %d chars" % (type(value).__name__, len(value))
    return type(value).__name__


def _echo_safe(value: Any) -> bool:
    """A short string with no markup, safe to echo so a typo can be fixed."""
    return (isinstance(value, str) and len(value) < ECHO_MAX_CHARS and "<" not in value
            and "untrusted_participant_content" not in value)


def _parse_ts_quiet(value: Any) -> Optional[datetime]:
    """parse_ts without its raw-value warning; logs type and size instead."""
    drop = _DropRawTimestampWarning()
    _ROOMS_LOGGER.addFilter(drop)
    try:
        ts = parse_ts(value)
    finally:
        _ROOMS_LOGGER.removeFilter(drop)
    if drop.dropped:
        logger.warning("upwork_followup: could not parse a timestamp (%s)",
                       repr(value) if _echo_safe(value) else _describe(value))
    return ts

SNAPSHOT_NAME = "upwork_followup/snapshot.json"
CALLS_FILE = Path(__file__).resolve().parent / "collect_calls.md"
PIPELINE_ENV = "UPWORK_PIPELINE_DIR"

CANDIDATE_ROOM_TYPES = ("ONE_ON_ONE", "INTERVIEW")
ACTIVITY_WINDOW_DAYS = 60
# How far ``collected_at`` may run ahead of the ingest's own clock (the
# session may stamp the pull from a slightly different clock). Anything later
# is refused: every room would fall outside the window, and the tick's
# snapshot age would go negative and never read as stale.
MAX_CLOCK_DRIFT = timedelta(minutes=10)
MESSAGE_MAX_CHARS = 2000
POST_MAX_CHARS = 6000
LIST_ROOMS_PAGE_CAP = 10
LIVE_THREAD_CAP = 60
THREAD_PREFIX = "upwork:"
# Thread statuses (sequence.py) that end a thread for good. Any other status,
# including closed_out and dormant, can still move, so its room is always read.
TERMINAL_STATUSES = ("won", "lost", "stopped")

SECTION_KEYS = ("rooms", "messages", "proposals", "invitations", "contracts", "offers")
CAP_NAMES = ("list_rooms", "proposals", "proposal_rooms", "messages", "contracts", "offers")


class IngestError(Exception):
    """The envelope is parseable but is not a pull worth writing."""


# ------------------------------------------------------------------ helpers
def _as_pages(value: Any) -> List[Any]:
    """One response or a list of responses -> a list of responses."""
    if isinstance(value, list):
        return list(value)
    return [value]


def _is_error(payload: Any) -> bool:
    """A dict that says it failed: an error word as its ``status``, or a
    non-empty error key. This is the check for ITEMS inside a page (room
    cards, proposal nodes, contracts, offers, messages), whose own ``status``
    ("Accepted", "CLOSED") and ``message`` fields are data. Whole responses
    use the stricter ``_is_error_response``."""
    if not isinstance(payload, dict):
        return False
    status = payload.get("status")
    if isinstance(status, str) and status.strip().lower() in (
            "error", "failed", "failure", "denied", "unauthorized"):
        return True
    for key in ("error", "errors", "isError", "is_error", "error_code"):
        if payload.get(key):
            return True
    return False


_OK_STATUSES = ("ok", "success")


def _is_error_response(payload: Any) -> bool:
    """A whole MCP response (the envelope, a page, a get_room answer) that
    failed. On top of ``_is_error``: a ``status`` that is given must be ok or
    success (any case), ``success: false`` fails, and a top-level ``message``
    with no ``data`` is an error text ("Rate limit exceeded"). Never used on
    items: a message node has a ``message`` field of its own."""
    if not isinstance(payload, dict):
        return False
    if _is_error(payload):
        return True
    status = payload.get("status")
    if status not in (None, "") and not (
            isinstance(status, str) and status.strip().lower() in _OK_STATUSES):
        return True
    success = payload.get("success")
    if success is False or (isinstance(success, str) and success.strip().lower() == "false"):
        return True
    if payload.get("message") not in (None, "") and payload.get("data") is None:
        return True
    return False


_SIGNAL_KEYS = ("status", "success", "message", "error", "errors", "error_code", "isError", "is_error")


def _error_summary(payload: Any) -> str:
    """A refused response for the refusal message: its failure fields and its
    top-level keys only. The rest (room names, message text) is client-written
    and must not reach the log or the session's report."""
    if not isinstance(payload, dict):
        return type(payload).__name__
    shown = {}  # type: Dict[str, Any]
    for key in _SIGNAL_KEYS:
        if key in payload:
            text = json.dumps(payload[key], default=str)
            shown[key] = "(client text withheld)" if "untrusted_participant_content" in text else payload[key]
    keys = ", ".join(sorted(str(k) for k in payload)[:12])
    return "%s; keys: %s" % (json.dumps(shown, default=str)[:200], keys)


def _is_not_found(payload: Any) -> bool:
    """get_room's answer for a proposal the client never opened a room on."""
    return isinstance(payload, dict) and str(payload.get("error_code") or "").upper() == "NOT_FOUND"


def _has_more(payload: Any) -> bool:
    """An explicit hasMore / has_more on the page (or its data) is true."""
    if not isinstance(payload, dict):
        return False
    holders = [payload]
    if isinstance(payload.get("data"), dict):
        holders.append(payload["data"])
    for holder in holders:
        for key in ("hasMore", "has_more"):
            if key in holder:
                return bool(holder.get(key))
    return False


def _checked_items(items: List[Any]) -> Optional[List[Dict[str, Any]]]:
    """Unwrap ``{"node": ...}`` edges. None (not a usable page) when any item is
    not a dict or carries error keys: a list of error strings or error objects
    is a failed call, never "zero rooms"."""
    out = []  # type: List[Dict[str, Any]]
    for item in items:
        if isinstance(item, dict) and "node" in item:
            item = item["node"]
        if not isinstance(item, dict) or _is_error(item):
            return None
        out.append(item)
    return out


def _find_list(payload: Any, keys: Tuple[str, ...]) -> Optional[List[Dict[str, Any]]]:
    """The first list found under ``keys`` in a page, its ``data``, or one level
    deeper (``data.<wrapper>.<key>`` / ``data.<wrapper>.edges``). None when no
    such list exists, which is different from an empty list.

    A page must be a dict response. A list-shaped page (``[]``, ``["Error"]``,
    a page wrapped in an extra list) is not a page, and a list whose items are
    not all dicts free of error keys is not a usable list: both give None."""
    if not isinstance(payload, dict):
        return None
    holders = [payload]
    data = payload.get("data")
    if isinstance(data, dict):
        holders.append(data)
    for holder in holders:
        for key in keys:
            value = holder.get(key)
            if isinstance(value, list):
                return _checked_items(value)
            if isinstance(value, dict):
                for inner in ("edges", "items", "nodes") + keys:
                    if isinstance(value.get(inner), list):
                        return _checked_items(value[inner])
    return None


def _first(mapping: Any, *keys: str) -> Any:
    """The first non-empty value among ``keys``; dotted keys walk nested dicts."""
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping  # type: Any
        for part in key.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        if value not in (None, "", [], {}):
            return value
    return None


def _iso(value: Any) -> Optional[str]:
    """Any timestamp parse_ts reads -> ISO-8601 in UTC, else None."""
    ts = _parse_ts_quiet(value)
    return ts.astimezone(timezone.utc).isoformat() if ts else None


_JOB_ID_RE = re.compile(r"~02(\d{6,})")


def canonical_job_id(value: Any) -> Optional[str]:
    """A job URL, a ``~02<digits>`` ciphertext or a bare numeric id -> ``~02<digits>``.

    Anything else (an old ``~01<hex>`` ciphertext, garbage) -> None, so it can
    never match by accident.
    """
    if value in (None, ""):
        return None
    text = str(value).strip()
    m = _JOB_ID_RE.search(text)
    if m:
        return "~02" + m.group(1)
    if re.match(r"^\d{6,}$", text):
        return "~02" + text
    return None


def _title_key(value: Any) -> str:
    """Exact, case-insensitive title comparison key (whitespace collapsed only)."""
    return clean_text(unwrap(value)).casefold()


WRAP_OPEN = "<untrusted_participant_content>"
WRAP_CLOSE = "</untrusted_participant_content>"
_MD_ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!<>|~])")


def unwrap(value: Any) -> Any:
    """Strip the MCP's untrusted-content wrapper exactly once, at the start and
    the end. Anything else is left as it is (and stays untrusted data):
    ``clean_text`` later breaks any tag-shaped run that is still inside."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text.startswith(WRAP_OPEN) and text.endswith(WRAP_CLOSE) \
            and len(text) >= len(WRAP_OPEN) + len(WRAP_CLOSE):
        text = text[len(WRAP_OPEN):len(text) - len(WRAP_CLOSE)]
    return text


def participant_text(value: Any) -> str:
    """Participant-written text -> one clean line of data.

    Unwrap once, undo the HTML escapes Upwork applies (``&gt;``) and markdown
    backslash escapes (``\\-``), then ``clean_text`` (newlines collapsed, tag
    runs broken, so an unescaped ``<`` can never read as a tag).
    """
    if value in (None, "") or isinstance(value, (dict, list, bool)):
        return ""
    text = html.unescape(unwrap(str(value)))
    text = _MD_ESCAPE_RE.sub(r"\1", text)
    return clean_text(text)


def _self_ids(ids: Optional[Dict[str, Any]] = None) -> Set[str]:
    """Lorenzo's own Upwork ids: ``upwork.freelancer_user_id`` (and ``org_uid``)."""
    upwork = ((ids if ids is not None else settings.IDS) or {}).get("upwork", {}) or {}
    out = set()
    for key in ("freelancer_user_id", "org_uid"):
        value = upwork.get(key)
        if value not in (None, ""):
            out.add(str(value))
    return out


# ------------------------------------------------------------------- rooms
_SUPPORT_NAME_RE = re.compile(r"^upwork(\s+(support|team|help|customer support))?$", re.IGNORECASE)


def _room_cards(page: Any) -> Optional[List[Dict[str, Any]]]:
    return _find_list(page, ("rooms",))


def _is_candidate(card: Dict[str, Any], room: Dict[str, Any], window_start: Optional[datetime]) -> bool:
    """ONE_ON_ONE or INTERVIEW, not a support/system room, activity in the
    window. A room whose type or activity time is not stated (a room seen only
    through get_room) is kept: the linked proposal and its messages decide, not
    a missing field."""
    room_type = str(room.get("room_type") or "").upper()
    if room_type and room_type not in CANDIDATE_ROOM_TYPES:
        return False
    for flag in ("isSystem", "is_system", "system", "isSupport", "is_support"):
        if card.get(flag) is True:
            return False
    if _SUPPORT_NAME_RE.match(room.get("client") or ""):
        return False
    last = _parse_ts_quiet(room.get("last_message_at"))
    if window_start is not None and last is not None and last < window_start:
        return False
    return True


# --------------------------------------------------------------- proposals
def _proposal_nodes(page: Any) -> Optional[List[Dict[str, Any]]]:
    return _find_list(page, ("vendorProposals", "proposals", "edges"))


def _proposal_from_node(node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    job = node.get("marketplaceJobPosting") or node.get("jobPosting") or node.get("job") or {}
    if not isinstance(job, dict):
        job = {}
    pid = node.get("id") or node.get("proposal_id") or node.get("proposalId")
    if not pid:
        return None
    job_id = canonical_job_id(job.get("url")) or canonical_job_id(job.get("ciphertext")) \
        or canonical_job_id(job.get("id"))
    status = node.get("status")
    if isinstance(status, dict):
        status = status.get("status")
    audit = node.get("auditDetails") if isinstance(node.get("auditDetails"), dict) else {}
    created = audit.get("createdDateTime")
    if isinstance(created, dict):
        created = created.get("displayValue") or created.get("rawValue")
    title = _first(job, "content.title", "title")
    return {
        "proposal_id": str(pid),
        "job_id": job_id,
        "job_title": participant_text(title),
        "status": str(status or ""),
        "created_at": _iso(created),
    }


PROPOSAL_STATUSES = ("Accepted", "Activated", "Offered")
_RESPONSE_KEYS = ("data", "status", "message", "hasMore", "has_more", "error", "errors",
                  "error_code", "isError", "is_error", "vendorProposals", "edges", "proposalRoom")


def _looks_like_response(value: Dict[str, Any]) -> bool:
    """A single MCP response, as opposed to a map keyed by status or id."""
    return any(k in value for k in _RESPONSE_KEYS)


def _proposal_pages(value: Any) -> List[Any]:
    """``proposals`` must be keyed by status, with every one of
    ``PROPOSAL_STATUSES`` present and holding at least one page. A skipped
    status would silently drop its rooms, so it is refused, not guessed."""
    if not isinstance(value, dict) or _looks_like_response(value):
        raise IngestError("proposals must be an object keyed by status (%s); nothing was written"
                          % ", ".join(PROPOSAL_STATUSES))
    missing = [st for st in PROPOSAL_STATUSES if value.get(st) in (None, [], {})]
    if missing:
        raise IngestError("proposals has no pages for %s; that list call was not made or failed, "
                          "nothing was written" % ", ".join(missing))
    pages = []  # type: List[Any]
    for status in sorted(value):
        per = value[status]
        pages.extend(per if isinstance(per, list) else [per])
    return pages


def _room_id_from_get_room(resp: Any) -> Tuple[Optional[str], Dict[str, Any]]:
    """(room_id, room card) out of a get_room response."""
    if not isinstance(resp, dict):
        return None, {}
    data = resp.get("data") if isinstance(resp.get("data"), dict) else resp
    room = data.get("proposalRoom") or data.get("room") or data
    if not isinstance(room, dict):
        return None, {}
    rid = room.get("id") or room.get("room_id") or room.get("roomId")
    if isinstance(rid, str) and rid:
        return rid, room
    return None, {}


# ---------------------------------------------------------------- messages
_SELF_WORDS = ("freelancer", "self", "you", "me", "mine", "vendor")
# Upwork writes room events as ordinary message nodes, e.g.
# "**Jane C.** ended the contract". Only the whole-line event shape counts: a
# bold actor name followed by one of these phrases and nothing else. The
# unbolded form is NOT matched: "Yes I sent an offer" or "My Partner ended the
# contract." is a client writing, and must never disappear as an event.
_SYSTEM_EVENT = (r"(ended the contract|started (?:a|the) contract|sent an offer|"
                 r"(?:accepted|declined|withdrew) (?:an|the|your) offer|accepted|"
                 r"joined(?: the room)?|left(?: the room)?)")
_SYSTEM_LINE_RES = (
    re.compile(r"^\*\*[^*]{1,80}\*\*\s+" + _SYSTEM_EVENT + r"\s*\.?$", re.IGNORECASE),
)


def is_system_line(text: str) -> bool:
    """A room event Upwork wrote (contract ended, offer sent, someone joined),
    not a message from either side. Matched on the cleaned text."""
    line = (text or "").strip()
    return bool(line) and len(line) <= 160 and any(r.match(line) for r in _SYSTEM_LINE_RES)


# The Upwork MCP also writes some room events as a message node of their own,
# sent "from" Lorenzo (from_self true, from_side freelancer), e.g.
# "System event: blocked. View this conversation on upwork.com for full
# context." (read-only live pull, 2026-09-23). Only that whole line counts:
# "System event" in any case, a name of 1 to 40 letters, digits, spaces, "_"
# or "-", then the fixed sentence. The line counts only on a node on Lorenzo's
# side (``message_side`` is "freelancer"), which is how both live events came:
# a client-side or unknown-side copy (a client typing that exact line) stays an
# ordinary message, sets ``last_side`` as usual and can never block the room.
_MCP_EVENT_RE = re.compile(
    r"^(?i:system event): ([A-Za-z0-9 _-]{1,40})\. "
    r"View this conversation on upwork\.com for full context\.?$")
# The one event name that sets ``room["blocked"]``.
BLOCKED_EVENT = "blocked"


def mcp_event_name(text: str) -> Optional[str]:
    """The event name of an MCP "System event: <name>. View this conversation
    on upwork.com for full context." line (lowercased, each run of spaces as
    one "_"), or None. Matched on the cleaned text, stripped."""
    match = _MCP_EVENT_RE.match((text or "").strip())
    if not match:
        return None
    name = re.sub(r" +", "_", match.group(1).strip()).lower()
    return name or None


_CLIENT_WORDS = ("client", "them", "other", "buyer", "counterparty")
_SYSTEM_TYPES = ("system", "notification", "event", "system_message", "systemstory")


def _message_items(page: Any) -> Optional[List[Dict[str, Any]]]:
    return _find_list(page, ("stories", "messages", "roomStories", "items", "edges"))


def _side_word(value: Any) -> Optional[str]:
    if isinstance(value, bool) or value in (None, ""):
        return None
    word = str(value).strip().lower()
    if word in _SELF_WORDS:
        return "freelancer"
    if word in _CLIENT_WORDS:
        return "client"
    return None


def message_side(msg: Dict[str, Any], self_ids: Set[str]) -> str:
    """client | freelancer | unknown, conservatively.

    1. ``from_side`` (confirmed on live list_messages nodes, 2026-09-22), then
       any other explicit side field, then ``from_self`` (present on Lorenzo's
       own messages), then ``from_my_organization`` (on every node).
    2. Otherwise the sender's user id: equal to Lorenzo's id is ``freelancer``;
       a different id is ``client`` unless the message is marked as a system
       story.
    3. Anything else is ``unknown``.
    """
    for key in ("from_side", "side", "sender_side", "senderSide", "message_side", "messageSide",
                "last_message_side"):
        side = _side_word(msg.get(key))
        if side:
            return side
    for key in ("from_self", "fromSelf", "from_my_organization", "fromMyOrganization",
                "is_self", "isSelf", "message_from_self", "sent_by_me", "sentByMe", "is_mine", "isMine"):
        if isinstance(msg.get(key), bool):
            return "freelancer" if msg[key] else "client"
    kind = str(_first(msg, "type", "storyType", "messageType", "kind") or "").lower()
    if kind in _SYSTEM_TYPES or msg.get("isSystemStory") is True or msg.get("system") is True:
        return "unknown"
    sender = _first(msg, "user.id", "user.nid", "user.userId", "user.uid", "sender.id",
                    "sender.nid", "sender.userId", "author.id", "from.id", "createdBy.id",
                    "userId", "user_id", "senderId", "sender_id", "authorId", "author_id")
    if sender in (None, "") or isinstance(sender, (dict, list, bool)):
        return "unknown"
    return "freelancer" if str(sender) in self_ids else "client"


def normalize_message(msg: Dict[str, Any], self_ids: Set[str]) -> Dict[str, Any]:
    text = _first(msg, "message", "text", "body", "content.text", "content")
    if isinstance(text, (dict, list)):
        text = ""
    cleaned = participant_text(text)[:MESSAGE_MAX_CHARS]
    at = _first(msg, "createdDateTime", "created_at", "createdAt", "sent_at", "sentAt",
                "timestamp", "time", "updatedDateTime")
    mid = _first(msg, "id", "storyId", "story_id", "messageId", "message_id")
    # A room event is kept in the history (it is still what happened in the
    # room) but belongs to neither side, whatever its from_side says. An MCP
    # "System event: <name>." line is an event (with its ``event_name``) only
    # on a freelancer-side node: a client-side or unknown-side copy is a
    # message like any other.
    side = message_side(msg, self_ids)
    event_name = mcp_event_name(cleaned) if side == "freelancer" else None
    event = event_name is not None or is_system_line(cleaned)
    out = {
        "id": str(mid) if mid not in (None, "") else "",
        "side": "unknown" if event else side,
        "at": _iso(at),
        "text": cleaned,
        "event": event,
    }
    if event_name is not None:
        out["event_name"] = event_name
    return out


def blocked_state(messages: List[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    """(blocked, blocked_at) from time-ordered messages (oldest first).

    Blocked when the newest named system event is ``blocked`` and no spoken
    (non-event) message comes after it. A later spoken message, or a later
    named event such as ``unblocked``, means the chat is open again. A bold
    room event ("**X** joined") has no name and neither sets nor clears it."""
    for index in range(len(messages) - 1, -1, -1):
        msg = messages[index]
        if not msg.get("event"):
            return False, None          # a human spoke after any block
        name = msg.get("event_name")
        if name is None:
            continue                    # a bold room event: look further back
        if name == BLOCKED_EVENT:
            return True, msg.get("at")
        return False, None
    return False, None


def _order_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Oldest first, de-duplicated by id (last copy wins). A message with no
    readable time goes first: it can never be claimed as the latest word.
    list_messages is newest first, so two messages with the same time keep
    that order: the one earlier in the input is the newer and sorts later."""
    by_key = {}  # type: Dict[str, Tuple[int, Dict[str, Any]]]
    for order, msg in enumerate(messages):
        key = msg["id"] or ("#%d" % order)
        by_key[key] = (order, msg)

    def sort_key(item: Tuple[int, Dict[str, Any]]):
        order, msg = item
        ts = _parse_ts_quiet(msg.get("at"))
        return (0, 0.0, order) if ts is None else (1, ts.timestamp(), -order)

    return [m for _, m in sorted(by_key.values(), key=sort_key)]


def _card_last_side(card: Dict[str, Any]) -> str:
    """Who wrote last according to the list_rooms card."""
    side = _side_word(card.get("last_message_side"))
    if side:
        return side
    from_self = card.get("last_message_from_self")
    if from_self is True:
        return "freelancer"
    if from_self is False:
        return "client"
    awaiting = str(card.get("awaiting_reply_from") or "").lower()
    if awaiting == "you":
        return "client"
    if awaiting == "them":
        return "freelancer"
    return "unknown"


# --------------------------------------------------------- contracts/offers
_CONTRACT_STATUS = {"ACTIVE": "ACTIVE", "STARTED": "ACTIVE",
                    "CLOSED": "CLOSED", "ENDED": "CLOSED", "COMPLETE": "CLOSED",
                    "COMPLETED": "CLOSED", "CANCELLED": "CLOSED", "CANCELED": "CLOSED",
                    "PAUSED": "PAUSED", "SUSPENDED": "PAUSED"}


def _contract_status(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    raw = str(value).strip().upper()
    return _CONTRACT_STATUS.get(raw, raw)


def _contract_cards(page: Any) -> Optional[List[Dict[str, Any]]]:
    return _find_list(page, ("vendorContracts", "contracts"))


_OFFER_STATES = {
    "awaiting_your_acceptance": "awaiting_your_acceptance",
    "awaiting_acceptance": "awaiting_your_acceptance",
    "pending_acceptance": "awaiting_your_acceptance",
    "contract_started": "contract_started",
    "accepted": "contract_started",
    "declined": "declined",
    "rejected": "declined",
    "withdrawn": "withdrawn",
    "cancelled": "withdrawn",
    "canceled": "withdrawn",
    "expired": "expired",
}


def offer_state(value: Any) -> Optional[str]:
    """An offer's state -> the snapshot's vocabulary, or None when unsure."""
    if isinstance(value, dict):
        value = _first(value, "status", "state", "name")
    if value in (None, "") or isinstance(value, (dict, list, bool)):
        return None
    key = re.sub(r"[^a-z]+", "_", str(value).strip().lower()).strip("_")
    return _OFFER_STATES.get(key)


def _offer_items(page: Any) -> Optional[List[Dict[str, Any]]]:
    return _find_list(page, ("offersByAttribute", "offers", "vendorOffers", "items", "edges"))


def _normalize_offer(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Live list_mine offers (2026-09-22) carry no room or contract id; the
    only link to a room is ``job.id`` / ``job.url``, matched to the linked
    proposal's job."""
    job = _first(raw, "job.url", "jobPosting.url", "marketplaceJobPosting.url", "job.id",
                 "jobPosting.id", "marketplaceJobPosting.id", "jobId", "job_id",
                 "job.ciphertext", "jobPosting.ciphertext")
    stamp = _first(raw, "modifiedDateTime", "updatedDateTime", "updated_at", "createdDateTime",
                   "created_at", "auditDetails.modifiedDateTime.displayValue",
                   "auditDetails.createdDateTime.displayValue")
    return {
        "job_id": canonical_job_id(job),
        "state": offer_state(_first(raw, "state", "status", "offerStatus", "offer_state")),
        "at": _parse_ts_quiet(stamp),
    }


def _pick_offer_state(matches: List[Dict[str, Any]]) -> Optional[str]:
    """The most recent matched offer's state; None when unsure (no readable
    state, or several undated offers that disagree)."""
    stated = [m for m in matches if m.get("state")]
    if not stated:
        return None
    dated = [m for m in stated if m.get("at") is not None]
    if dated:
        return max(dated, key=lambda m: m["at"])["state"]
    states = {m["state"] for m in stated}
    return states.pop() if len(states) == 1 else None


# ------------------------------------------------------------- job folders
_KEY_LINE_RE = re.compile(r"^\s*(url|client first name|client_first_name)\s*:\s*(.*)$", re.IGNORECASE)
_META_LINE_RE = re.compile(r"^\s*(fixed price|hourly|posted|budget|bid range|prop\s*:)", re.IGNORECASE)
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*\S)\s*$")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s*(.*?)\s*#*\s*$")
_PRIVATE_HEADING_RE = re.compile(r"^(time|likelihood|standard pricing)\b", re.IGNORECASE)
_ASK_HEADING_RE = re.compile(r"^ask before quoting\b", re.IGNORECASE)
# Bold-label layout (about half the real assessment.md files): a line that
# starts with a bold label, "**Time.** 3 hours" or "**Standard pricing:**", or
# a list item whose bold label is exactly one of the four known sections,
# "- **Likelihood:** high".
_BOLD_LINE_RE = re.compile(r"^\*\*([^*]{1,120}?)\*\*\s*[:.]?\s*(.*)$")
_BOLD_ITEM_RE = re.compile(r"^\s*[-*+]\s+\*\*([^*]{1,60}?)\*\*\s*[:.]?\s*(.*)$")
_KNOWN_SECTIONS = ("time", "likelihood", "standard pricing", "ask before quoting")
_SUBHEADING_RE = re.compile(r"^\s*#{2,6}\s")
_FIRST_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z'\-]*$")
_PLACEHOLDER_NAMES = ("unknown", "n/a", "na", "none", "null", "tbd", "-", "?")


def _clean_first_name(value: Any) -> Optional[str]:
    text = clean_text(value or "")
    if not text:
        return None
    token = text.split()[0].strip(",.;:")
    if token.lower() in _PLACEHOLDER_NAMES or not _FIRST_NAME_RE.match(token):
        return None
    return token


def parse_jd(text: str) -> Dict[str, Any]:
    """jd.txt -> {"job_id", "title", "client_first_name", "post"}.

    Two layouts exist. With a ``url:`` first line and a blank line before the
    post, the metadata block is the first paragraph: key lines (``url:``,
    ``client first name:``), then the title, then Lorenzo's own summary lines.
    Otherwise the metadata is the leading key lines, the title (the first
    other line) and the run of summary lines right after it (``Fixed price``,
    ``Hourly``, ``Posted``, ``Budget``, ``Bid range``, ``Prop:``). The post is
    the rest.
    """
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    meta = {}  # type: Dict[str, str]
    title = ""
    body = []  # type: List[str]

    def take_key(line: str) -> bool:
        m = _KEY_LINE_RE.match(line)
        if not m:
            return False
        key = m.group(1).lower().replace("_", " ")
        meta.setdefault(key, m.group(2).strip())
        return True

    url_first = bool(lines) and re.match(r"^\s*url\s*:", lines[0], re.IGNORECASE)
    blank = next((i for i, line in enumerate(lines) if not line.strip()), None)
    if blank is not None and not any(line.strip() for line in lines[blank:]):
        blank = None          # only trailing blank lines: there is no separator
    if url_first and blank is not None:
        header = lines[:blank]
        rest = lines[blank + 1:]
        leftover = []  # type: List[str]
        for line in header:
            if take_key(line):
                continue
            if not title:
                title = line.strip()
        body = leftover + rest
    else:
        # No url line, or a url line with no blank separator: key lines, the
        # title, then Lorenzo's summary lines, then the post.
        i = 0
        while i < len(lines) and take_key(lines[i]):
            i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i < len(lines):
            title = lines[i].strip()
            i += 1
        while i < len(lines) and (_META_LINE_RE.match(lines[i]) or take_key(lines[i])):
            i += 1
        body = lines[i:]
    body = [line for line in body if not _KEY_LINE_RE.match(line)]
    return {
        "job_id": canonical_job_id(meta.get("url")),
        "title": clean_text(title),
        "client_first_name": _clean_first_name(meta.get("client first name")),
        "post": clean_text("\n".join(body))[:POST_MAX_CHARS],
    }


def parse_proposal_md(text: str) -> str:
    """proposal.md with the ``preview_chars:`` line removed. Lorenzo's own
    text, so line breaks are kept; control characters are dropped."""
    kept = [line.rstrip() for line in (text or "").replace("\r\n", "\n").split("\n")
            if not re.match(r"^\s*preview_chars\s*:", line, re.IGNORECASE)]
    out = "\n".join(kept).strip()
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", out)


def parse_beats(text: str) -> List[str]:
    """beats.md -> its list items, in order."""
    beats = []  # type: List[str]
    for line in (text or "").splitlines():
        m = _LIST_ITEM_RE.match(line)
        if m:
            item = clean_text(m.group(1))
            if item:
                beats.append(item)
    return beats


def _label(value: str) -> str:
    return value.strip().rstrip(".:").strip()


def _sections(text: str) -> List[Tuple[str, List[str]]]:
    """Markdown -> [(heading, body lines)].

    A file with ``##`` headings splits at its ``#`` headings only. A file
    without them uses the bold-label layout: it splits at every line that
    starts with a bold label, and at a list item whose bold label is exactly
    one of the known sections. Text after the label on the same line is the
    first body line."""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    bold_mode = not any(_SUBHEADING_RE.match(line) for line in lines)
    out = []  # type: List[Tuple[str, List[str]]]
    heading = ""
    body = []  # type: List[str]
    for line in lines:
        m = _HEADING_RE.match(line) if line.lstrip().startswith("#") else None
        if m:
            out.append((heading, body))
            heading, body = m.group(1).strip(), []
            continue
        if bold_mode:
            b = _BOLD_LINE_RE.match(line)
            if not b:
                item = _BOLD_ITEM_RE.match(line)
                if item and _label(item.group(1)).lower() in _KNOWN_SECTIONS:
                    b = item
            if b:
                out.append((heading, body))
                heading, body = _label(b.group(1)), []
                if b.group(2).strip():
                    body.append(b.group(2))
                continue
        body.append(line)
    out.append((heading, body))
    return out


def parse_assessment(text: str) -> Tuple[List[str], str]:
    """assessment.md -> (ask_before_quoting questions, private notes).

    Questions come from the "Ask before quoting" section's list items (or its
    lines, when it has no list). The private notes are the Time, Likelihood and
    Standard pricing sections, heading and lines, and nothing else. Both
    ``## Heading`` and bold-label (``**Time.**``, ``- **Time:**``) layouts are
    read. Both outputs are private: they never go into ``job.post`` or
    ``job.proposal``.
    """
    questions = []  # type: List[str]
    notes = []  # type: List[str]
    for heading, body in _sections(text):
        name = clean_text(heading)
        if _ASK_HEADING_RE.match(name):
            items = [clean_text(m.group(1)) for m in (_LIST_ITEM_RE.match(l) for l in body) if m]
            if not items:
                items = [clean_text(l) for l in body if l.strip()]
            questions.extend(i for i in items if i)
        elif _PRIVATE_HEADING_RE.match(name):
            lines = [l.rstrip() for l in body if l.strip()]
            if lines:
                notes.append("%s:\n%s" % (name, "\n".join(lines)))
    return questions, "\n\n".join(notes)


def _read(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def default_pipeline_dir() -> Path:
    override = os.environ.get(PIPELINE_ENV)
    return Path(override) if override else ROOT_DIR / "Coding" / "upwork-pipeline"


def index_job_folders(pipeline_dir: Path) -> List[Dict[str, Any]]:
    """Every ``jobs/<slug>/jd.txt`` under the pipeline dir, parsed. Read only."""
    jobs_dir = Path(pipeline_dir) / "jobs"
    folders = []  # type: List[Dict[str, Any]]
    try:
        entries = sorted(jobs_dir.iterdir())
    except OSError:
        return folders
    for entry in entries:
        if not entry.is_dir() or entry.name.startswith(("_", ".")):
            continue
        jd = _read(entry / "jd.txt")
        if jd is None:
            continue
        parsed = parse_jd(jd)
        parsed["slug"] = entry.name
        parsed["path"] = entry
        folders.append(parsed)
    return folders


def match_job_folder(folders: List[Dict[str, Any]], job_id: Optional[str],
                     job_title: str) -> Optional[Dict[str, Any]]:
    """Job id first, then an exact case-insensitive title, else None.

    Never fuzzy. Two folders with the same id or the same title are ambiguous
    and match nothing. A title match skips folders whose jd.txt names a
    different job id than the room's: a generic title shared by two clients
    must not hand one client the other's post.
    """
    if job_id:
        by_id = [f for f in folders if f.get("job_id") == job_id]
        if len(by_id) == 1:
            return by_id[0]
        if len(by_id) > 1:
            return None
    key = _title_key(job_title)
    if not key:
        return None
    by_title = [f for f in folders if _title_key(f.get("title")) == key
                and not (job_id and f.get("job_id") and f.get("job_id") != job_id)]
    return by_title[0] if len(by_title) == 1 else None


def read_proposals_csv(pipeline_dir: Path) -> List[Dict[str, str]]:
    path = Path(pipeline_dir) / "proposals.csv"
    try:
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
            return [row for row in csv.DictReader(fh) if isinstance(row, dict)]
    except (OSError, csv.Error):
        return []


def lookup_proposal_row(rows: List[Dict[str, str]], job_id: Optional[str],
                        titles: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """(loom_url, applied_at) for the proposals.csv row whose ``job_url`` names
    ``job_id`` (the latest such row wins), else the one row whose ``job_title``
    equals one of ``titles`` exactly (case-insensitive). Several title rows are
    ambiguous and give (None, None)."""
    def pick(row: Dict[str, str]) -> Tuple[Optional[str], Optional[str]]:
        loom = (row.get("loom_url") or "").strip() or None
        applied = (row.get("applied_at") or "").strip() or None
        return loom, applied

    if job_id:
        by_id = [r for r in rows if canonical_job_id(r.get("job_url")) == job_id]
        if by_id:
            return pick(by_id[-1])
    keys = {_title_key(t) for t in titles if _title_key(t)}
    if keys:
        by_title = [r for r in rows if _title_key(r.get("job_title")) in keys
                    and not (job_id and canonical_job_id(r.get("job_url"))
                             and canonical_job_id(r.get("job_url")) != job_id)]
        if len(by_title) == 1:
            return pick(by_title[0])
    return None, None


def build_job(folder: Dict[str, Any], rows: List[Dict[str, str]], job_id: Optional[str],
              job_title: str) -> Dict[str, Any]:
    path = folder["path"]
    questions, notes = parse_assessment(_read(path / "assessment.md") or "")
    loom, applied = lookup_proposal_row(rows, job_id or folder.get("job_id"),
                                        [job_title, folder.get("title") or ""])
    return {
        "post": folder.get("post") or "",
        "proposal": parse_proposal_md(_read(path / "proposal.md") or ""),
        "beats": parse_beats(_read(path / "beats.md") or ""),
        "ask_before_quoting": questions,
        "private_notes": notes,
        "loom_url": loom,
        "applied_at": applied,
    }


# ------------------------------------------------------------ first names
_COMPANY_WORDS = {"llc", "inc", "ltd", "co", "corp", "group", "agency", "labs", "studio",
                  "gmbh", "limited", "company", "solutions", "services", "team", "llp"}
_NAME_WORD_RE = re.compile(r"^[A-Z][a-z]+(?:[-'][A-Za-z][a-z]+)?$")


def _first_name_from_room(card: Dict[str, Any], client: str) -> Optional[str]:
    """An explicit first-name field on the room card, else the first word of a
    ``"First Last, Company"`` room name. A name without the comma form (it may
    be a company) gives None."""
    explicit = _first(card, "client_first_name", "clientFirstName", "firstName", "first_name")
    if explicit:
        return _clean_first_name(explicit)
    if "," not in client:
        return None
    person = client.split(",", 1)[0].strip()
    words = person.split()
    if not 2 <= len(words) <= 3:
        return None
    if any(w.lower().strip(".") in _COMPANY_WORDS or not _NAME_WORD_RE.match(w) for w in words):
        return None
    return words[0]


# ------------------------------------------------------------------ ingest
def _require_pages(raw: Dict[str, Any], key: str, finder) -> List[Any]:
    if key not in raw or raw[key] is None:
        raise IngestError("%s is missing or null; the pull did not succeed, nothing was written" % key)
    pages = _proposal_pages(raw[key]) if key == "proposals" else _as_pages(raw[key])
    if not pages:
        raise IngestError("%s holds no responses; nothing was written" % key)
    for index, page in enumerate(pages):
        if _is_error_response(page):
            raise IngestError("%s page %d is an error response (%s); nothing was written"
                              % (key, index, _error_summary(page)))
        if finder(page) is None:
            raise IngestError("%s page %d is not a %s response; nothing was written"
                              % (key, index, key))
    return pages


def _optional_pages(raw: Dict[str, Any], key: str, finder) -> Tuple[bool, List[Dict[str, Any]], List[Any]]:
    """(section ok, items, pages) for a section that degrades instead of refusing.

    Missing or null means "not collected" (ok False). An empty list means
    "collected, none" (ok True). A page that is not a usable dict response
    makes the section not ok."""
    if raw.get(key) is None:
        return False, [], []
    pages = _as_pages(raw[key])
    items = []  # type: List[Dict[str, Any]]
    ok = True
    for page in pages:
        found = None if _is_error_response(page) else finder(page)
        if found is None:
            ok = False
            continue
        items.extend(found)
    return ok, items, pages


def _live_entries(value: List[Any]) -> Tuple[Dict[str, Optional[str]], List[int]]:
    """The envelope's ``live_threads`` list -> ({room_id: proposal_id or None},
    indexes of the entries that are not as ``collect_instructions`` prints
    them).

    A printed entry is an object with a ``room_...`` ``room_id`` and a
    ``proposal_id`` that is a string or null (an integer id is read as its
    string). An entry with no usable room id is skipped. One whose room id is
    fine but whose proposal id is missing or unusable keeps the room (it is
    still never dropped for age) with no stored link. Both kinds are
    returned as bad, so the caller flags the pull: a lost entry can drop a
    live thread's room out of the snapshot."""
    out = {}  # type: Dict[str, Optional[str]]
    bad = []  # type: List[int]
    for index, entry in enumerate(value):
        rid = entry.get("room_id") if isinstance(entry, dict) else None
        if not isinstance(rid, str) or not rid.startswith("room_"):
            bad.append(index)
            continue
        pid = entry.get("proposal_id")
        if pid is None and "proposal_id" in entry:
            out[rid] = None
        elif isinstance(pid, str) and pid:
            out[rid] = pid
        elif isinstance(pid, int) and not isinstance(pid, bool):
            out[rid] = str(pid)
        else:
            out[rid] = None
            bad.append(index)
    return out, bad


def live_threads(store: Any = None) -> List[Dict[str, Optional[str]]]:
    """Threads in the store that can still move: every ``upwork:<room_id>``
    thread whose status is not won, lost or stopped. Their rooms are read on
    every pull, whatever their age. Returns [] when the store cannot be read:
    the pull then runs with the normal windows only."""
    try:
        if store is None:
            from shared.store import get_store
            store = get_store()
        out = []  # type: List[Dict[str, Optional[str]]]
        for key in sorted(store.keys(THREAD_PREFIX)):
            thread = store.get(key)
            if not isinstance(thread, dict):
                continue
            room_id = thread.get("room_id") or key[len(THREAD_PREFIX):]
            if not isinstance(room_id, str) or not room_id.startswith("room_"):
                continue      # upwork:meta and anything that is not a thread
            if str(thread.get("status") or "").lower() in TERMINAL_STATUSES:
                continue
            pid = thread.get("proposal_id")
            out.append({"room_id": room_id,
                        "proposal_id": str(pid) if pid not in (None, "") else None})
        return out
    except Exception as exc:  # noqa: BLE001 - a store failure only omits the list
        logger.warning("upwork_followup: could not read live threads from the store: %s", exc)
        return []


def is_future_stamp(stamp: Any, now: datetime) -> bool:
    """True when ``stamp`` (an ISO string or datetime) is later than ``now``
    plus ``MAX_CLOCK_DRIFT``. The ingest refuses such a ``collected_at``; the
    tick can apply the same rule to a snapshot's ``generated_at``."""
    ts = _parse_ts_quiet(stamp)
    return ts is not None and ts > slots.ensure_aware(now) + MAX_CLOCK_DRIFT


def _span(delta: timedelta) -> str:
    """A positive timedelta in words, for refusal messages."""
    minutes = int(delta.total_seconds() // 60)
    if minutes < 120:
        return "%d minutes" % minutes
    hours = minutes / 60.0
    return "%.1f hours" % hours if hours < 48 else "%.1f days" % (hours / 24.0)


def ingest(raw: Any, now: datetime, pipeline_dir: Optional[Any] = None) -> Dict[str, Any]:
    """Raw MCP envelope -> the snapshot DESIGN.md "Snapshot" and "RoomContext"
    define. Raises ``IngestError`` rather than build a snapshot that would
    read as "nobody is waiting" from a pull that failed."""
    if not isinstance(raw, dict):
        raise IngestError("the envelope is not a JSON object (got %s); nothing was written"
                          % type(raw).__name__)
    if not raw:
        raise IngestError("the envelope is an empty object; nothing was written")
    if _is_error_response(raw):
        raise IngestError("the envelope is an error response (%s); nothing was written"
                          % _error_summary(raw))

    now = slots.ensure_aware(now)
    # The pull's own time, never the ingest time: stamping an old pull with
    # "now" would make a stale snapshot look fresh. An old stamp is kept as it
    # is (the tick's STALE warning reads it); a future one is refused.
    stamp = raw.get("collected_at")
    collected = _parse_ts_quiet(stamp) if isinstance(stamp, str) else None
    if collected is None:
        if "collected_at" not in raw:
            shown = "no collected_at key"
        elif _echo_safe(stamp):
            shown = repr(stamp)
        else:
            shown = _describe(stamp)
        raise IngestError("collected_at is missing or unreadable (%s); nothing was written" % shown)
    if is_future_stamp(collected, now):
        raise IngestError(
            "collected_at %s is %s after the ingest time %s, more than the %d-minute clock-drift "
            "allowance. A pull cannot come from the future: check the date and the UTC offset. A "
            "future stamp would put every room outside the %d-day window and keep the snapshot from "
            "ever looking stale; nothing was written"
            % (collected.astimezone(timezone.utc).isoformat(), _span(collected - now),
               now.astimezone(timezone.utc).isoformat(), MAX_CLOCK_DRIFT.total_seconds() // 60,
               ACTIVITY_WINDOW_DAYS))
    window_start = collected - timedelta(days=ACTIVITY_WINDOW_DAYS)
    self_ids = _self_ids()
    caps_raw = raw.get("caps_hit")
    if not isinstance(caps_raw, list):
        raise IngestError("caps_hit must be a list (write [] when no cap was hit); got %s, "
                          "nothing was written"
                          % ("no caps_hit key" if "caps_hit" not in raw else _describe(caps_raw)))
    caps = {c for c in caps_raw if isinstance(c, str) and c in CAP_NAMES}
    live_raw = raw.get("live_threads")
    if not isinstance(live_raw, list):
        raise IngestError(
            "live_threads must be a list, copied from the \"Always read these rooms\" section of "
            "--print-collect (write [] when it lists none); got %s. Without it a live thread's room "
            "can drop out for age, nothing was written"
            % ("no live_threads key" if "live_threads" not in raw
               else _describe(live_raw)))
    live, bad_live = _live_entries(live_raw)
    truncated_sections = set()  # type: Set[str]
    if any(not (isinstance(c, str) and c in CAP_NAMES) for c in caps_raw):
        # A cap name this code does not know still means a step stopped early.
        truncated_sections.add("unrecognised_cap")
    if bad_live:
        # An entry that is not as printed was skipped or lost its link: that
        # live thread's room may be missing, so the batch must warn.
        truncated_sections.add("live_threads")

    # --- rooms (required)
    room_pages = _require_pages(raw, "list_rooms", _room_cards)
    cards = {}  # type: Dict[str, Dict[str, Any]]
    for page in room_pages:
        for card in _room_cards(page) or []:
            rid = card.get("id") or card.get("room_id")
            if isinstance(rid, str) and rid:
                cards[rid] = card
    if _has_more(room_pages[-1]) or len(room_pages) > LIST_ROOMS_PAGE_CAP or "list_rooms" in caps:
        truncated_sections.add("rooms")

    # --- proposals (required) + proposal_rooms (required key)
    proposal_pages = _require_pages(raw, "proposals", _proposal_nodes)
    proposals = {}  # type: Dict[str, Dict[str, Any]]
    for page in proposal_pages:
        for node in _proposal_nodes(page) or []:
            prop = _proposal_from_node(node)
            if prop:
                proposals[prop["proposal_id"]] = prop
    if "proposal_rooms" not in raw or not isinstance(raw.get("proposal_rooms"), dict):
        raise IngestError("proposal_rooms is missing (write {} when there were no proposals); "
                          "without it no room can be linked, nothing was written")
    if _is_error_response(raw["proposal_rooms"]) or _looks_like_response(raw["proposal_rooms"]):
        raise IngestError("proposal_rooms is a single response, not a map of proposal id to "
                          "get_room response (%s); nothing was written"
                          % _error_summary(raw["proposal_rooms"]))
    proposals_ok = True
    link_errors = []  # type: List[str]
    room_to_proposal = {}  # type: Dict[str, Dict[str, Any]]
    get_room_cards = {}  # type: Dict[str, Dict[str, Any]]
    # A get_room that failed answered nothing, even when it carries a room id.
    answered_pids = {str(k) for k, v in raw["proposal_rooms"].items()
                     if _is_not_found(v) or (not _is_error_response(v) and _room_id_from_get_room(v)[0])}
    for pid, resp in sorted(raw["proposal_rooms"].items()):
        pid = str(pid)
        if _is_not_found(resp):
            continue          # the client never opened a room on this proposal
        if _is_error_response(resp) or not isinstance(resp, dict):
            proposals_ok = False
            link_errors.append(pid)
            continue
        rid, room_card = _room_id_from_get_room(resp)
        if not rid:
            proposals_ok = False
            link_errors.append(pid)
            continue
        prop = proposals.get(pid) or {"proposal_id": pid, "job_id": None, "job_title": "",
                                      "status": "", "created_at": None}
        current = room_to_proposal.get(rid)
        # Two proposals on one room: the newest proposal wins.
        if current is None or (prop.get("created_at") or "") > (current.get("created_at") or ""):
            room_to_proposal[rid] = prop
        get_room_cards[rid] = room_card
    tried = [pid for pid, resp in raw["proposal_rooms"].items() if not _is_not_found(resp)]
    if tried and len(link_errors) == len(tried):
        raise IngestError("every get_room call failed (%d of %d, NOT_FOUND aside); no room can be "
                          "linked, nothing was written" % (len(link_errors), len(tried)))
    # A live thread's stored proposal link stands in only when this pull's
    # get_room for that proposal is missing or failed. A NOT_FOUND or a
    # different room from get_room wins over the store.
    for rid, pid in sorted(live.items()):
        if rid in room_to_proposal or not pid or pid in answered_pids:
            continue
        room_to_proposal[rid] = proposals.get(pid) or {
            "proposal_id": pid, "job_id": None, "job_title": "", "status": "", "created_at": None}
    if "proposals" in caps or "proposal_rooms" in caps:
        truncated_sections.add("proposals")

    # --- contracts and offers (degrade)
    contracts_ok, contract_cards, contract_pages = _optional_pages(raw, "contracts", _contract_cards)
    contracts = {}  # type: Dict[str, Dict[str, Any]]
    for card in contract_cards:
        c = normalize_contract(card)
        if c.get("contract_id"):
            contracts[c["contract_id"]] = c
    if "contracts" in caps or (contract_pages and _has_more(contract_pages[-1])):
        truncated_sections.add("contracts")

    offers_ok, offer_cards, offer_pages = _optional_pages(raw, "offers", _offer_items)
    offers = [_normalize_offer(o) for o in offer_cards]
    if "offers" in caps or (offer_pages and _has_more(offer_pages[-1])):
        truncated_sections.add("offers")

    # --- messages (degrade per room)
    raw_messages = raw.get("messages") if isinstance(raw.get("messages"), dict) else None
    if "messages" in caps:
        truncated_sections.add("messages")

    # --- job folders (read only)
    pdir = Path(pipeline_dir) if pipeline_dir else default_pipeline_dir()
    folders = index_job_folders(pdir)
    csv_rows = read_proposals_csv(pdir) if folders else []

    # --- which rooms are in scope
    # A room with ANY contract id (ENDED included) is out of scope: Lorenzo
    # already had a contract with that client. It is listed in
    # ``contracted_rooms`` so the tick can still mark an enrolled thread won
    # (ACTIVE) or stop it.
    omitted_unlinked = 0
    contracted_rooms = []  # type: List[Dict[str, Any]]
    in_scope = []  # type: List[Tuple[str, Dict[str, Any], Dict[str, Any]]]
    for rid in sorted(set(cards) | set(room_to_proposal)):
        card = cards.get(rid) or get_room_cards.get(rid) or {"id": rid}
        card = dict(card, id=rid)
        if isinstance(card.get("roomName"), str):
            card["roomName"] = participant_text(card["roomName"])
        base = normalize_room(card)
        # A live thread's room is never dropped for age: a paused thread whose
        # check-in is far out, or a quiet one nearing dormant, must keep moving.
        if not _is_candidate(card, base, None if rid in live else window_start):
            continue
        contract_id = base.get("contract_id")
        if contract_id:
            status = contracts.get(contract_id, {}).get("status") or base.get("contract_status")
            contracted_rooms.append({"room_id": rid, "contract_id": contract_id,
                                     "status": _contract_status(status),
                                     "proposal_id": (room_to_proposal.get(rid) or {}).get("proposal_id")})
            continue
        if rid not in room_to_proposal:
            omitted_unlinked += 1
            continue
        in_scope.append((rid, card, base))

    rooms = []  # type: List[Dict[str, Any]]
    missing_messages = []  # type: List[str]
    for rid, card, base in in_scope:
        prop = room_to_proposal[rid]

        # messages
        pulled = raw_messages.get(rid) if raw_messages is not None else None
        messages = []  # type: List[Dict[str, Any]]
        # [] or null for a room is "not pulled": a real list_messages call
        # always returns a page, so an empty value proves nothing.
        ok = pulled not in (None, [])
        for page in (_as_pages(pulled) if ok else []):
            items = None if _is_error_response(page) else _message_items(page)
            if items is None:
                ok = False
                continue
            messages.extend(normalize_message(m, self_ids) for m in items)
        messages = _order_messages(messages)
        if not ok:
            # A partial pull may have lost the newest page: nothing from it
            # decides last_side; the room card does.
            missing_messages.append(rid)
            messages = []

        # last side: the last message that is not a room event, backfilled from
        # the room card when the card's latest story is that same message (or
        # no messages came back). A room event never sets last_side, and the
        # latest spoken message sets last_message_at.
        card_side = _card_last_side(card)
        story = card.get("latestStory") if isinstance(card.get("latestStory"), dict) else {}
        spoken = [m for m in messages if not m["event"]]
        story_text = participant_text(story.get("message"))
        # An MCP system-event line is an event only on Lorenzo's side: the
        # story's own side fields, else the card's claim about its last
        # message. A client-side copy still supplies last_side.
        story_side = message_side(story, self_ids)
        if story_side == "unknown":
            story_side = card_side
        story_is_mcp_event = story_side == "freelancer" and (
            mcp_event_name(story_text) is not None
            or mcp_event_name(story_text.split(": ", 1)[-1]) is not None)
        story_is_event = is_system_line(story_text.split(": ", 1)[-1]) or story_is_mcp_event \
            or any(m["id"] == story.get("id") and m["event"] for m in messages)
        if story_is_event:
            card_side = "unknown"
        if spoken:
            last = spoken[-1]
            if last["side"] == "unknown" and card_side != "unknown" and story.get("id") \
                    and story.get("id") == last["id"]:
                last["side"] = card_side
            last_side = last["side"]
            last_at = last["at"] or _iso(base.get("last_message_at"))
        else:
            last_side = card_side
            last_at = _iso(base.get("last_message_at"))
        # A blocked room (MCP "System event: blocked." with nothing spoken
        # after it) cannot take a message; only the messages decide.
        blocked, blocked_at = blocked_state(messages)

        # offers link to a room only through the proposal's job id. A room in
        # scope has no contract id (see above), so ``contract`` is null here;
        # contracted rooms are reported in ``contracted_rooms`` instead.
        room_offers = [o for o in offers if o["job_id"] and o["job_id"] == prop.get("job_id")]
        contract = None

        job_title = prop.get("job_title") or base.get("job_title") or ""
        job_id = prop.get("job_id")
        folder = match_job_folder(folders, job_id, job_title)
        job = build_job(folder, csv_rows, job_id, job_title) if folder else None

        first_name = (folder or {}).get("client_first_name") or _first_name_from_room(card, base["client"])

        rooms.append({
            "room_id": rid,
            "client": base["client"],
            "client_first_name": first_name,
            "room_type": base.get("room_type"),
            "job_title": job_title,
            "job_id": job_id,
            "proposal_id": prop["proposal_id"],
            "origin": "proposal" if prop.get("proposal_id") else "unknown",
            "contract": contract,
            "offer_state": _pick_offer_state(room_offers),
            # null, not [], when the pull for this room is missing or failed
            # (the room is then also in missing_messages)
            "messages": messages if ok else None,
            "last_side": last_side,
            "last_message_at": last_at,
            "blocked": blocked,
            "blocked_at": blocked_at,
            "job_folder": folder["slug"] if folder else None,
            "job": job,
        })

    sections = {
        "rooms": True,
        "messages": raw_messages is not None and not missing_messages,
        "proposals": proposals_ok,
        "invitations": None,      # not collected (scope update 2026-09-22)
        "contracts": contracts_ok,
        "offers": offers_ok,
    }
    return {
        "generated_at": collected.astimezone(timezone.utc).isoformat(),
        "source": "mcp",
        "sections": sections,
        "truncated": bool(truncated_sections),
        "truncated_sections": sorted(truncated_sections),
        "live_threads": [{"room_id": rid, "proposal_id": live[rid]} for rid in sorted(live)],
        "omitted_unlinked": omitted_unlinked,
        "omitted_contracted": len(contracted_rooms),
        "contracted_rooms": contracted_rooms,
        "missing_messages": sorted(missing_messages),
        "blocked_rooms": sorted(r["room_id"] for r in rooms if r["blocked"]),
        "link_errors": sorted(link_errors),
        "rooms": rooms,
    }


# ------------------------------------------------------------------ files
def snapshot_path(path: Optional[Any] = None) -> Path:
    return Path(path) if path else tmp_file(SNAPSHOT_NAME)


def write_snapshot(snapshot: Dict[str, Any], path: Optional[Any] = None) -> Path:
    """Atomic tmp + rename, so the tick never reads a half-written file."""
    target = snapshot_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, indent=2, sort_keys=False, default=str)
        fh.write("\n")
    os.replace(str(tmp), str(target))
    return target


def load_snapshot(path: Optional[Any] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """(snapshot, error). Never raises: a missing or broken file degrades."""
    target = snapshot_path(path)
    try:
        with open(target, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return None, "missing"
    except (OSError, ValueError) as exc:
        logger.warning("upwork_followup: could not read %s: %s", target, exc)
        return None, "unreadable: %s" % exc
    if not isinstance(data, dict) or not isinstance(data.get("rooms"), list):
        return None, "unexpected shape"
    return data, None


def collect_instructions(ids: Optional[Dict[str, Any]] = None, store: Any = None) -> str:
    """collect_calls.md, plus the org_uid from config/ids.json and the live
    threads from the store ("always read these rooms")."""
    text = _read(CALLS_FILE) or "collect_calls.md is missing\n"
    upwork = ((ids if ids is not None else settings.IDS) or {}).get("upwork", {}) or {}
    org = upwork.get("org_uid") or "<missing: set upwork.org_uid in config/ids.json>"
    out = text.rstrip("\n") + "\n\norg_uid for this run (config/ids.json upwork.org_uid): %s\n" % org
    live = live_threads(store)
    out += "\n## Always read these rooms (live threads, %d)\n\n" % len(live)
    if not live:
        out += ("None. Save \"live_threads\": [] in the file (the store has no live "
                "thread, or could not be read).\n")
        return out
    out += ("Run step 3 (`get_room`) for every proposal id below and step 6\n"
            "(`list_messages`) for every room below, whatever its age and even when\n"
            "it falls outside the 60-day windows. These rooms do not count against\n"
            "the 40-room message cap; they have their own cap of %d. Copy this list\n"
            "into the file as `live_threads` exactly as written:\n\n" % LIVE_THREAD_CAP)
    out += "```\n\"live_threads\": %s\n```\n" % json.dumps(live[:LIVE_THREAD_CAP])
    if len(live) > LIVE_THREAD_CAP:
        out += ("\n%d more live threads are over the cap and are left out of this pull; "
                "add \"messages\" to `caps_hit`.\n" % (len(live) - LIVE_THREAD_CAP))
    return out
