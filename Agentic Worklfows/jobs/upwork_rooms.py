"""Upwork rooms SLA check (Blueprint M6 / O2): what is waiting on Lorenzo.

Read-only, twice a day at 09:00 and 15:00 CT. It produces one list, oldest
first, of Upwork rooms and invitations awaiting a reply from Lorenzo, plus a
reminder 48 hours after any contract ends to ask for a review, a testimonial
and a maintenance retainer.

**This job never drafts and never sends on Upwork.** The application flow (job
selection, the Demo Library paste-and-record loop, the Loom, the proposal,
boosting) is out of scope and nothing here touches it. There is no Upwork
write path in this module, by construction, and
``jobs/tests/test_upwork_rooms.py`` fails if one appears.

The handoff (why there are two halves)
--------------------------------------
The Upwork MCP connector only exists inside a Claude session, so a scheduled
job cannot reach it. The split is:

    1. A session runs the MCP reads and saves the raw responses, then::

           python3 jobs/upwork_rooms.py --ingest .tmp/upwork_mcp_raw.json

       which normalises them into ``.tmp/upwork_rooms.json``.
       ``--print-collect`` prints the exact MCP calls to run.
    2. This job reads that file, applies the SLA rules and prints/pushes the
       digest. It never calls Upwork itself.

``.tmp/upwork_rooms.json`` is the same file ``jobs/pipeline_sweep.py`` (O3)
reads for its Upwork section, and the room keys written here are the ones that
reader expects (``room_id``, ``client``, ``job_title``, ``awaiting``,
``last_message_at``, ``last``, ``value``).

An ingest either replaces that file with a pull it can recognise, or refuses
and leaves the old one alone: an error envelope, an empty object or a bare
string is **not** "zero rooms waiting". A pull that carried only one of the two
halves is recorded in ``sections`` and the digest says which half was not
checked, because "no closed contracts" and "contracts were never pulled" look
identical otherwise.

When that file is missing or stale the digest carries a plain
``no fresh Upwork data, last seen <timestamp>`` line and still reports
everything it can (stale rooms, marked as stale, and the manual checks). It
does not fail: a silent job is how a five-day-old invitation stays unanswered.

Untrusted content
-----------------
Room names and message snippets are written by clients. The MCP already wraps
them in ``<untrusted_participant_content>`` tags. ``clean_text()`` strips that
wrapper, breaks any other tag-shaped run by putting a space after its ``<``
(never by deleting the span between two angle brackets, which silently rewrote
client text), and collapses newlines, so a message can never forge a line in
Lorenzo's digest. Everything out of a room is data, never an instruction, and nothing in
this job acts on it.

CLI (from "Agentic Worklfows/"):
    python3 jobs/upwork_rooms.py --dry-run                 # compute, print, Job_Log row, no push
    python3 jobs/upwork_rooms.py --now                     # same plus one notification to Lorenzo
    python3 jobs/upwork_rooms.py --dry-run --as-of 2026-09-22T09:00:00-05:00
    python3 jobs/upwork_rooms.py --dry-run --json
    python3 jobs/upwork_rooms.py --ingest .tmp/upwork_mcp_raw.json   # session helper
    python3 jobs/upwork_rooms.py --ingest -                # ... or raw MCP JSON on stdin
    python3 jobs/upwork_rooms.py --print-collect           # the MCP calls a session runs

Python 3.9 compatible. Never calls datetime.now() inside the logic: ``now`` is
injected (``--as-of`` on the CLI, a parameter in code).
"""
import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

if __package__ in (None, ""):  # run as a script: make "shared" importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import settings, slots  # noqa: E402
from shared.job_log import log_run  # noqa: E402
from shared.notify import notify, topic_is_protected  # noqa: E402
from shared.paths import tmp_file  # noqa: E402

logger = logging.getLogger("jobs.upwork_rooms")

JOB_NAME = "upwork_rooms"

# ------------------------------------------------------------------- config
SCHEDULE_HOURS = (9, 15)        # 09:00 and 15:00 CT (Blueprint Section 6, O2)
# Section 6 scoreboard: Upwork response time target < 1 h, alert > 4 h.
SLA_TARGET_HOURS = 1.0
SLA_ALERT_HOURS = 4.0
# Past this age the row reads in days, and "over the 4 h alert line" stops
# being news ("6.6 days waiting" already says it). One constant so the wording
# and the age format cannot flip at two different boundaries.
AGE_DAYS_SWITCH_HOURS = 48.0
# M6 post-contract ask: 48 h after a contract ends, review + testimonial + retainer.
POST_CONTRACT_HOURS = 48
# ... and it stops being an ask worth making after three weeks. Older closed
# contracts collapse into one summary line instead of repeating twice a day
# forever (the digest has to stay short enough to be read).
POST_CONTRACT_WINDOW_DAYS = 21
# A reminder that came due within this many hours is what makes a push urgent.
REMINDER_NEWLY_DUE_HOURS = 24
# Runs are 6 h and 18 h apart, so a snapshot older than this was not refreshed
# for at least one scheduled run.
SNAPSHOT_STALE_HOURS = 12
SNAPSHOT_FILE = "upwork_rooms.json"     # .tmp/upwork_rooms.json, shared with pipeline_sweep (O3)
RAW_FILE = "upwork_mcp_raw.json"        # .tmp/upwork_mcp_raw.json, what a session saves
SNIPPET_CHARS = 120

# The three asks M6 wants 48 h after a contract ends.
POST_CONTRACT_ASKS = ("review", "testimonial", "maintenance retainer")

# Items the MCP cannot see. Upwork's rooms/offers endpoints do not expose the
# Invitations tab, so these are carried as config and always printed as a
# manual check.
#
# This tuple is only the fallback. ``config/ids.json -> upwork.manual_checks``
# wins when it exists, which is how one gets retired without editing this
# module: give the entry ``"done": true`` (or an ``"until"`` date in the past),
# or set the key to ``[]`` when none are left. A snapshot may override the list
# too, and an explicit empty list in a snapshot means "none", not "use the
# built-ins".
MANUAL_CHECKS = (
    {
        "label": "ClosePoint USA invitation (GHL expert)",
        "since": "2026-09-16",
        "where": "Upwork Messages > Invitations tab",
        "why": "client invitation, not visible through the API",
    },
    {
        "label": "RoutVox Consulting call request",
        "since": "2026-08-27",
        "where": "Upwork Messages > Invitations tab",
        "why": "call request, not visible through the API",
    },
)

# The read-only MCP calls a session runs to refresh the snapshot.
COLLECT_INSTRUCTIONS = """\
Refresh .tmp/upwork_rooms.json from a Claude session that has the Upwork MCP.
All three calls are read-only. Never call upwork__send_message,
upwork__manage_proposals, upwork__respond_to_offer or upwork__manage_meetings:
this job exists so nothing is drafted or sent on Upwork.

  org_uid = %(org_uid)s   (config/ids.json -> upwork.org_uid)

  1. upwork__get_messages   action="list_rooms"
                            params={"limit": 50, "room_type": "ALL"}
     The tool returns the most recently active rooms first and caps limit at
     100. While the response says "hasMore": true, call it again with the
     "cursor"/"next_cursor" it returned and keep every page: the rooms that
     fall off the end are the long-unanswered ones this job exists to find.
  2. upwork__list_contracts action="search"
                            params={"contract_statuses": ["ACTIVE", "CLOSED", "PAUSED"], "limit": 10}
     limit is capped at 10 here. Page with "offset" (0, 10, 20, ...) until a
     page comes back short, or a contract that ended recently can fall off the
     page and its 48-hour review ask never fires.
  3. upwork__list_offers    action="list_mine"    (optional)
                            params={"limit": 10}

Save the raw responses as JSON. Concatenated pages are fine: pass a list of
responses, or merge the pages into one "rooms" / "contracts" list.

  {"collected_at": "<ISO now>",
   "rooms_response":     <response 1 verbatim, or [page 1, page 2, ...]>,
   "contracts_response": <response 2 verbatim, or [page 1, page 2, ...]>,
   "offers_response":    <response 3 verbatim, optional>,
   "manual_checks":      [ ... optional, overrides the built-in list; [] means none ... ]}

If a call fails, save what it actually returned rather than an empty object.
The ingest refuses an error envelope and keeps the previous snapshot, which is
what makes the "no fresh Upwork data" line fire instead of a confident,
silently empty digest.

Then normalise it:

  python3 jobs/upwork_rooms.py --ingest .tmp/%(raw)s

Or pipe a single raw response straight in:

  ... | python3 jobs/upwork_rooms.py --ingest -
""" % {"org_uid": (settings.IDS.get("upwork", {}) or {}).get("org_uid", "<see config/ids.json>"),
       "raw": RAW_FILE}


class IngestError(Exception):
    """The input is parseable JSON but is not a pull worth writing.

    Raised rather than writing a fresh-stamped empty snapshot over a good one:
    an error envelope is not "nothing is waiting".
    """


# ------------------------------------------------------------------ helpers
_WRAPPER_RE = re.compile(r"</?untrusted_participant_content\s*/?>", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(value: Any) -> str:
    """Client-written text -> one safe single-line string.

    Strips the MCP's ``<untrusted_participant_content>`` wrapper, breaks any
    remaining tag-shaped run by putting a space after its ``<``, removes
    control characters, and collapses newlines into spaces so a room message
    cannot forge a line in the digest. The result is data, never an
    instruction, and the digest is plain text in both legs (ntfy and
    MIMEText "plain"), so a broken tag is inert.

    It deliberately does **not** delete the span between a ``<`` and a ``>``.
    That rewrote ordinary client text: "budget is < 5k and > 2k" came out as
    "budget is 2k", which inverts what the client wrote, and
    "<mark@firth.com>" lost the address entirely. The security property is the
    newline collapse below, not tag deletion.
    """
    if value in (None, ""):
        return ""
    text = value if isinstance(value, str) else str(value)
    text = _WRAPPER_RE.sub(" ", text)
    # "<b>" -> "< b>": no run can look like a tag, every character survives, and
    # the doubled space is collapsed below. A lone ">" is left alone: it cannot
    # open anything, and rewriting it mangles "budget > 2k" and the
    # "Upwork Messages > Invitations tab" breadcrumb.
    text = text.replace("<", "< ")
    text = _CTRL_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def snippet(value: Any, limit: int = SNIPPET_CHARS) -> str:
    text = clean_text(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _num(value: Any, default: float = 0.0) -> float:
    """Anything -> float, ``default`` when it is not a number.

    ``value`` and ``unread`` are keys the snapshot contract defines and the MCP
    never fills in, so a human or a session is the one who writes them; a dict
    like ``{"amount": 500, "currency": "USD"}`` used to crash the ingest with a
    bare TypeError.
    """
    if value in (None, "", True, False):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.warning("upwork_rooms: ignoring unreadable number (%s)", value_shape(value))
        return default


def value_shape(value: Any) -> str:
    """``type=<name> len=<n>`` for a log line. Snapshot values come from
    Upwork or from whoever wrote the ingest file, so a log line names only
    their type and length, never the value itself."""
    try:
        size = len(value)
    except TypeError:
        size = len(str(value))
    return "type=%s len=%d" % (type(value).__name__, size)


class _Shape(object):
    """``value_shape(value)`` for a ``%r`` log argument: its repr is the
    shape text, so the value itself never reaches the log."""

    def __init__(self, value: Any) -> None:
        self.text = value_shape(value)

    def __repr__(self) -> str:
        return self.text

    __str__ = __repr__


PARSE_TS_WARNING = "upwork_rooms: could not parse timestamp %r"


def parse_ts(value: Any, default_tz=timezone.utc) -> Optional[datetime]:
    """ISO string (Z or offset), epoch seconds/ms (int or numeric string), or
    datetime -> aware datetime. None when it cannot be read.

    Upwork sends ``lastActivity`` as epoch milliseconds *in a string*, which is
    why the numeric-string branch exists. ``default_tz`` is UTC for machine
    timestamps; pass ``settings.TZ`` for a date somebody typed by hand.
    """
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else _localize(value, default_tz)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        seconds = float(value) / (1000.0 if abs(value) > 1e11 else 1.0)
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if re.match(r"^-?\d+(\.\d+)?$", text):
        return parse_ts(float(text), default_tz=default_tz)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            return slots.parse_iso(text)
        except Exception:  # noqa: BLE001 - an unreadable timestamp is never fatal
            # The format string stays PARSE_TS_WARNING because
            # services/upwork_followup/collect.py filters this exact record;
            # the argument is only the type and length, never the value.
            logger.warning(PARSE_TS_WARNING, _Shape(value))
            return None
    return dt if dt.tzinfo else _localize(dt, default_tz)


def _localize(dt: datetime, tz) -> datetime:
    """Attach a timezone to a naive datetime (pytz zones need localize())."""
    localize = getattr(tz, "localize", None)
    if callable(localize):
        return localize(dt)
    return dt.replace(tzinfo=tz)


def hours_between(now: datetime, then: Optional[datetime]) -> Optional[float]:
    if then is None or now is None:
        return None
    return (slots.ensure_aware(now) - slots.ensure_aware(then)).total_seconds() / 3600.0


def format_age(hours: Optional[float]) -> str:
    """'3.2 h waiting' / '5.1 days waiting' / 'waiting, age unknown'."""
    if hours is None:
        return "waiting, age unknown"
    if hours < 0:
        return "waiting"
    if hours < AGE_DAYS_SWITCH_HOURS:
        return "%.1f h waiting" % hours
    return "%.1f days waiting" % (hours / 24.0)


def sla_state(hours: Optional[float]) -> str:
    """Section 6: target under 1 h, alert over 4 h."""
    if hours is None:
        return "unknown"
    if hours >= SLA_ALERT_HOURS:
        return "breach"
    if hours >= SLA_TARGET_HOURS:
        return "warn"
    return "ok"


def scheduled_run_label(now: datetime) -> str:
    """Which of the two daily runs this is closest to (reporting only)."""
    local = slots.to_tz(slots.ensure_aware(now), settings.TZ)
    nearest = min(SCHEDULE_HOURS, key=lambda h: abs(local.hour + local.minute / 60.0 - h))
    return "%02d:00 CT" % nearest


# -------------------------------------------------------- normalise the MCP
_ROOM_HINTS = ("roomName", "room_id", "latestStory", "numUnread", "roomType",
               "awaiting_reply_from", "last_message_from_self", "lastActivity")
_CONTRACT_HINTS = ("clientOrganization", "clientTeam", "endDate", "offerId",
                   "contract_id", "ended_at", "deliveryModel")


def _looks_like_room(card: Dict[str, Any]) -> bool:
    return any(k in card for k in _ROOM_HINTS)


def _looks_like_contract(card: Dict[str, Any]) -> bool:
    return any(k in card for k in _CONTRACT_HINTS)


def _rooms_from_response(payload: Any) -> Optional[List[Dict[str, Any]]]:
    """The room list in an ``upwork__get_messages`` response, or None when this
    payload is not a rooms response at all.

    None and ``[]`` are different answers and the caller depends on it: ``[]``
    means the call succeeded and no rooms came back, None means nothing here
    speaks about rooms (an error envelope, the contracts response, ``{}``).
    """
    if isinstance(payload, list):
        cards = [r for r in payload if isinstance(r, dict) and _looks_like_room(r)]
        return cards or None
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("rooms"), list):
        return [r for r in data["rooms"] if isinstance(r, dict)]
    if isinstance(payload.get("rooms"), list):
        return [r for r in payload["rooms"] if isinstance(r, dict)]
    return None


def _contracts_from_response(payload: Any) -> Optional[List[Dict[str, Any]]]:
    """The contract list in an ``upwork__list_contracts`` response, or None when
    this payload is not a contracts response. Same None-vs-empty contract as
    ``_rooms_from_response``."""
    if isinstance(payload, list):
        cards = [c for c in payload if isinstance(c, dict) and _looks_like_contract(c)]
        return cards or None
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, dict):
        vendor = data.get("vendorContracts")
        if isinstance(vendor, dict) and isinstance(vendor.get("contracts"), list):
            return [c for c in vendor["contracts"] if isinstance(c, dict)]
        if isinstance(data.get("contracts"), list):
            return [c for c in data["contracts"] if isinstance(c, dict)]
    if isinstance(payload.get("contracts"), list):
        return [c for c in payload["contracts"] if isinstance(c, dict)]
    return None


def _is_error_envelope(payload: Any) -> bool:
    """A response that says it failed. Ingesting one as "zero rooms" is how a
    good snapshot gets replaced by an empty one stamped fresh."""
    if not isinstance(payload, dict):
        return False
    status = payload.get("status")
    if isinstance(status, str) and status.strip().lower() in (
            "error", "failed", "failure", "denied", "unauthorized"):
        return True
    for key in ("error", "errors", "isError", "is_error"):
        if payload.get(key):
            return True
    return False


def _is_truncated(payload: Any) -> bool:
    """The MCP says there are more pages than this response carries.

    An explicit ``hasMore``/``has_more`` is believed over a cursor field: some
    responses echo the cursor they were called with on the final page too.
    """
    if not isinstance(payload, dict):
        return False
    holders = [payload]
    if isinstance(payload.get("data"), dict):
        holders.append(payload["data"])
    for holder in holders:
        for key in ("hasMore", "has_more"):
            if key in holder:
                return bool(holder.get(key))
    for holder in holders:
        for key in ("next_cursor", "nextCursor"):
            if holder.get(key):
                return True
    return False


_PAGE_KEYS = ("data", "status", "hasMore", "has_more", "rooms", "contracts",
              "error", "errors", "isError", "is_error", "next_cursor", "nextCursor")


def _is_response_page(item: Any) -> bool:
    """A whole MCP response (one page), as opposed to one room or contract card."""
    if not isinstance(item, dict):
        return False
    if _looks_like_room(item) or _looks_like_contract(item):
        return False
    return any(k in item for k in _PAGE_KEYS)


def _pages(payload: Any) -> List[Any]:
    """One bundle value -> its pages.

    The collect instructions allow ``"rooms_response": [page 1, page 2, ...]``,
    and a list of pages is not a list of room cards: reading it as one used to
    refuse the documented format with "carries no rooms list".
    """
    if isinstance(payload, list) and payload and all(_is_response_page(x) for x in payload):
        return list(payload)
    return [payload]


def _page_section(page: Any) -> Optional[str]:
    if _rooms_from_response(page) is not None:
        return "rooms"
    if _contracts_from_response(page) is not None:
        return "contracts"
    return None


def normalize_room(raw: Dict[str, Any]) -> Dict[str, Any]:
    """One MCP room card -> the room shape pipeline_sweep (O3) also reads.

    ``awaiting_reply_from`` is absent when the MCP could not place the last
    sender (a colleague of either party wrote last). Falling back to
    ``last_message_from_self`` keeps those rooms visible: over-reporting a room
    Lorenzo can dismiss in one glance is the safe direction, silently dropping
    one is not.
    """
    awaiting = raw.get("awaiting_reply_from", raw.get("awaiting", raw.get("awaiting_you")))
    if awaiting is True:
        awaiting = "you"
    elif awaiting is False:
        awaiting = "them"
    if awaiting in (None, ""):
        from_self = raw.get("last_message_from_self")
        if from_self is True:
            awaiting = "them"
        elif from_self is False:
            awaiting = "you"
        else:
            awaiting = "unknown"

    story = raw.get("latestStory") if isinstance(raw.get("latestStory"), dict) else {}
    last_at = parse_ts(
        story.get("createdDateTime")
        or raw.get("last_message_at")
        or raw.get("lastActivity")
        or raw.get("last_at")
    )
    return {
        "room_id": raw.get("id") or raw.get("room_id") or "",
        "client": clean_text(raw.get("roomName") or raw.get("client") or raw.get("title")),
        "job_title": clean_text(raw.get("job_title") or raw.get("jobTitle") or ""),
        "contract_id": str(raw.get("contractId") or raw.get("contract_id") or "") or None,
        "contract_status": raw.get("contractStatus") or raw.get("contract_status") or None,
        "room_type": raw.get("roomType") or raw.get("room_type") or None,
        "awaiting": awaiting,
        "unread": int(_num(raw.get("numUnread") or raw.get("unread"), 0.0)),
        "last_message_at": last_at.isoformat() if last_at else None,
        "last": snippet(story.get("message") or raw.get("last") or raw.get("last_message")),
        "value": _num(raw.get("value"), 0.0),
    }


ASK_FLAGS = {"review": "review_asked",
             "testimonial": "testimonial_asked",
             "maintenance retainer": "retainer_asked",
             "retainer": "retainer_asked"}


def apply_asks_done(contract: Dict[str, Any], done: Any) -> Dict[str, Any]:
    """Mark asks as already made from an explicit ``asks_done`` list."""
    if isinstance(done, dict):
        for flag in set(ASK_FLAGS.values()):
            if done.get(flag):
                contract[flag] = True
        done = done.get("asks_done")
    if isinstance(done, str):
        done = [done]
    for name in done or []:
        flag = ASK_FLAGS.get(str(name).strip().lower())
        if flag:
            contract[flag] = True
    return contract


def normalize_contract(raw: Dict[str, Any]) -> Dict[str, Any]:
    client = raw.get("clientOrganization") or raw.get("clientTeam") or {}
    client_name = client.get("name") if isinstance(client, dict) else None
    ended = parse_ts(raw.get("endDate") or raw.get("ended_at") or raw.get("end_date"))
    started = parse_ts(raw.get("startDate") or raw.get("started_at"))
    raw_status = raw.get("status") or raw.get("contract_status") or ""
    if not isinstance(raw_status, str):
        # a dict, list or number here is not a status Upwork sends: unknown
        logger.warning("upwork_rooms: ignoring a contract status that is not text (%s)", value_shape(raw_status))
        raw_status = ""
    status = raw_status.strip().upper()
    contract = {
        "contract_id": str(raw.get("id") or raw.get("contract_id") or "") or None,
        "client": clean_text(client_name or raw.get("client") or ""),
        "title": clean_text(raw.get("title") or ""),
        "status": status or None,
        "ended_at": ended.isoformat() if ended else None,
        "started_at": started.isoformat() if started else None,
        # Asks Lorenzo has already made. Only an explicit flag (or an
        # ``asks_done`` list) suppresses one.
        "review_asked": bool(raw.get("review_asked")),
        "testimonial_asked": bool(raw.get("testimonial_asked")),
        "retainer_asked": bool(raw.get("retainer_asked")),
        "note": clean_text(raw.get("note") or ""),
    }
    return apply_asks_done(contract, raw.get("asks_done"))


def _ids_contract_seeds() -> Dict[str, Dict[str, Any]]:
    """Per-contract notes and ``asks_done`` out of config/ids.json.

    The live key is date-stamped (``rooms_awaiting_you_2026-09-21``) and the
    obvious thing to do on the next pull is to re-date it, which used to drop
    every note *and* un-suppress every ``asks_done`` recorded there. So any key
    starting with ``rooms_awaiting_you`` counts, and the stable
    ``upwork.contract_asks`` map is read too and wins.
    """
    upwork = settings.IDS.get("upwork", {}) or {}
    seeds = {}  # type: Dict[str, Dict[str, Any]]
    for key in sorted(upwork.keys()):
        if not key.startswith("rooms_awaiting_you"):
            continue
        for entry in upwork.get(key) or []:
            if not isinstance(entry, dict):
                continue
            cid = str(entry.get("contract_id") or "")
            if cid:
                seeds[cid] = entry
    stable = upwork.get("contract_asks")
    if isinstance(stable, dict):
        for cid, entry in stable.items():
            if isinstance(entry, dict):
                merged = dict(seeds.get(str(cid), {}))
                merged.update(entry)
                seeds[str(cid)] = merged
    return seeds


def _seed_notes_from_ids(contracts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Carry the per-contract notes in config/ids.json onto the contract, and
    honour an explicit ``asks_done`` list there.

    It deliberately does **not** read "already asked" out of the prose. A wrong
    suppression drops the review ask and costs a Top Rated step; a wrong
    reminder costs one glance. So the note is printed verbatim under the
    reminder and Lorenzo decides, and only an explicit flag suppresses an ask.
    """
    seeds = _ids_contract_seeds()
    if contracts and not seeds:
        logger.warning("upwork_rooms: config/ids.json has no upwork contract notes "
                       "(rooms_awaiting_you* / contract_asks); reminders will carry no note")
    for contract in contracts:
        seed = seeds.get(str(contract.get("contract_id") or ""))
        if not seed:
            continue
        if not contract.get("note"):
            contract["note"] = clean_text(seed.get("note") or "")
        apply_asks_done(contract, seed.get("asks_done"))
    return contracts


def default_manual_checks() -> List[Dict[str, Any]]:
    """``config/ids.json -> upwork.manual_checks`` when it exists, else the
    built-in pair. An empty list there means "none left", which is how the two
    invitations get retired without editing this module."""
    configured = (settings.IDS.get("upwork", {}) or {}).get("manual_checks")
    if isinstance(configured, list):
        return [dict(m) for m in configured if isinstance(m, dict)]
    return [dict(m) for m in MANUAL_CHECKS]


def _manual_is_live(entry: Dict[str, Any], now: datetime) -> bool:
    """An entry Lorenzo has answered is retired by ``done``/``resolved``, or by
    an ``until`` date that has passed."""
    for key in ("done", "resolved", "answered"):
        if entry.get(key):
            return False
    until = parse_ts(entry.get("until"), default_tz=settings.TZ)
    if until is not None and slots.ensure_aware(now) >= until:
        return False
    return True


def _manual_key(entry: Dict[str, Any]) -> str:
    return clean_text(entry.get("label") or entry.get("client") or "").lower()


def _snapshot_owns_manual_list(snapshot: Any) -> bool:
    """Whether the snapshot's own ``manual_checks`` should be read.

    Yes when a bundle put it there (``manual_checks_from: bundle``), or when the
    file was written by hand rather than by ``--ingest``. An ingest-written
    snapshot without the marker is the old format, where the list was a frozen
    copy of the config: reading it made ``"done": true`` in ids.json do nothing.
    """
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("manual_checks"), list):
        return False
    if snapshot.get("manual_checks_from") == "bundle":
        return True
    return snapshot.get("source") != "upwork_mcp"


def _retired_in_config(now: datetime) -> set:
    """Labels config/ids.json marks done (or past their ``until``)."""
    configured = (settings.IDS.get("upwork", {}) or {}).get("manual_checks")
    if not isinstance(configured, list):
        return set()
    return {_manual_key(m) for m in configured
            if isinstance(m, dict) and _manual_key(m) and not _manual_is_live(m, now)}


def build_snapshot(raw: Any, now: datetime,
                   previous: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Raw MCP responses (one, several, or a bundle) -> the snapshot this job
    and pipeline_sweep read.

    Raises ``IngestError`` when the input carries no recognisable rooms or
    contracts response, or when any page under a bundle key holds an error
    envelope, or when a bundle names a half and sets it to ``null``. That is
    the whole point: without it a failed MCP call writes an empty snapshot
    stamped with the current time, the digest reports "fresh, nothing waiting",
    and the documented degradation line never fires.

    Pages: a bundle key may hold one response or a list of pages, and the top
    level may be a list of pages for either half. ``truncated`` is taken from
    the **last** page of each half only, so a complete paged pull (every page
    but the last says ``hasMore``) is not flagged.

    ``previous`` is the snapshot this one replaces. When the new pull carries
    only one half, the other half is carried forward from ``previous`` with its
    own older stamp in ``carried`` rather than silently replaced by nothing: a
    contracts-only pull used to make every waiting room disappear.
    """
    bundle = raw if isinstance(raw, dict) else {}
    pages = []  # type: List[Tuple[Optional[str], Any]]
    is_bundle = isinstance(raw, dict) and any(
        k in raw for k in ("rooms_response", "contracts_response", "offers_response"))
    if isinstance(raw, list):
        # A bare list of room/contract cards is one payload; a list of
        # responses (what paging produces) is several.
        if raw and all(isinstance(x, dict)
                       and _rooms_from_response(x) is None
                       and _contracts_from_response(x) is None
                       and not _is_error_envelope(x) for x in raw):
            pages = [(None, raw)]
        else:
            pages = [(None, x) for x in raw]
    elif is_bundle:
        for key in ("rooms_response", "contracts_response", "offers_response"):
            if key not in bundle:
                continue
            value = bundle[key]
            section = "rooms" if key == "rooms_response" else (
                "contracts" if key == "contracts_response" else "offers")
            if value is None:
                if section == "offers":
                    continue      # optional, and never read
                # A key that is present and null is a call that returned
                # nothing, not a call that was never made.
                raise IngestError("%s is null; the pull did not succeed, the previous snapshot is kept"
                                  % key)
            for page in _pages(value):
                pages.append((section, page))
    else:
        pages = [(None, raw)]

    rooms_by_id = {}  # type: Dict[Any, Dict[str, Any]]
    contracts_by_id = {}  # type: Dict[Any, Dict[str, Any]]
    sections = {"rooms": False, "contracts": False}
    last_page_truncated = {}  # type: Dict[str, bool]
    for index, (named, payload) in enumerate(pages):
        # A named half that came back broken is refused loudly, before anything
        # is written: "the rooms call failed" must not read as "no rooms are
        # waiting". Every page is checked, not just the first.
        if _is_error_envelope(payload):
            raise IngestError("%s page %d carries an error response (%s)" % (
                ("%s_response" % named) if named else "input", index,
                json.dumps(payload, default=str)[:200]))
        found_rooms = _rooms_from_response(payload)
        found_contracts = _contracts_from_response(payload)
        if named == "rooms" and found_rooms is None:
            raise IngestError("rooms_response carries no rooms list; the pull did not succeed")
        if named == "contracts" and found_contracts is None:
            raise IngestError("contracts_response carries no contracts list; the pull did not succeed")
        if named == "offers":
            continue
        if found_rooms is not None:
            sections["rooms"] = True
            last_page_truncated["rooms"] = _is_truncated(payload)
            for order, card in enumerate(found_rooms):
                # Last write wins: overlapping pages are an expected shape, and
                # a room listed twice used to be two numbered rows.
                key = card.get("id") or card.get("room_id") or ("#%d.%d" % (index, order))
                rooms_by_id[key] = card
        if found_contracts is not None:
            sections["contracts"] = True
            last_page_truncated["contracts"] = _is_truncated(payload)
            for order, card in enumerate(found_contracts):
                key = card.get("id") or card.get("contract_id") or ("#%d.%d" % (index, order))
                contracts_by_id[key] = card

    if not (sections["rooms"] or sections["contracts"]):
        raise IngestError(
            "no rooms and no contracts response in this input; the previous snapshot is kept. "
            "Run --print-collect and save what the MCP actually returned")

    rooms = [normalize_room(r) for r in rooms_by_id.values()]
    contracts = _seed_notes_from_ids([normalize_contract(c) for c in contracts_by_id.values()])

    # Per-contract overrides a session can add to the bundle, e.g.
    # {"contract_asks": {"44501032": {"asks_done": ["review"]}}}
    overrides = bundle.get("contract_asks")
    if isinstance(overrides, dict):
        for contract in contracts:
            override = overrides.get(str(contract.get("contract_id") or ""))
            if isinstance(override, dict):
                if override.get("note"):
                    contract["note"] = clean_text(override["note"])
                apply_asks_done(contract, override)

    collected = parse_ts(bundle.get("collected_at")) or slots.ensure_aware(now)
    snapshot = {
        "generated_at": collected.isoformat(),
        "source": "upwork_mcp",
        "sections": sections,
        "truncated": any(last_page_truncated.values()),
        "truncated_sections": sorted(k for k, v in last_page_truncated.items() if v),
        "rooms": rooms,
        "contracts": contracts,
    }  # type: Dict[str, Any]

    # A snapshot carries a manual list only when the bundle said so. Copying the
    # config list in here froze it: marking an invitation done in ids.json did
    # nothing until the next ingest, because manual_items() preferred the copy.
    # An explicit [] in the bundle still means "none left".
    manual = bundle.get("manual_checks")
    if isinstance(manual, list):
        snapshot["manual_checks"] = [dict(m) for m in manual if isinstance(m, dict)]
        snapshot["manual_checks_from"] = "bundle"

    carried = _carry_forward(snapshot, previous)
    if carried:
        snapshot["carried"] = carried
    return snapshot


def _carry_forward(snapshot: Dict[str, Any], previous: Optional[Dict[str, Any]]
                   ) -> Dict[str, Any]:
    """Copy the half this pull did not carry out of the previous snapshot.

    Returns ``{"rooms": {"generated_at": ...}}`` per half carried. The carried
    rows keep their own (older) stamp, and the digest, title, push and Job_Log
    status all say so, so an old room list never reads as this pull's.
    """
    carried = {}  # type: Dict[str, Any]
    if not isinstance(previous, dict):
        return carried
    prev_sections = snapshot_sections(previous)
    prev_carried = previous.get("carried") if isinstance(previous.get("carried"), dict) else {}
    for half in ("rooms", "contracts"):
        if snapshot["sections"][half] or not prev_sections[half]:
            continue
        rows = previous.get(half)
        if not isinstance(rows, list):
            continue
        # A half the previous snapshot itself carried keeps its original stamp:
        # re-stamping it at each ingest would make it look newer every time.
        stamp = ((prev_carried.get(half) or {}).get("generated_at")
                 or previous.get("generated_at"))
        snapshot[half] = [dict(r) for r in rows if isinstance(r, dict)]
        carried[half] = {"generated_at": stamp}
    return carried


def snapshot_path(path: Optional[Any] = None) -> Path:
    return Path(path) if path else tmp_file(SNAPSHOT_FILE)


def write_snapshot(snapshot: Dict[str, Any], path: Optional[Any] = None) -> Path:
    """Atomic tmp+rename, so pipeline_sweep never reads a half-written file."""
    target = snapshot_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, indent=2, sort_keys=False)
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
        logger.warning("upwork_rooms: could not read %s: %s", target, exc)
        return None, "unreadable: %s" % exc
    if isinstance(data, list):
        data = {"rooms": data}
    if not isinstance(data, dict):
        return None, "unexpected shape"
    if not isinstance(data.get("generated_at"), str):
        # An older file (or one written by hand) has no stamp: fall back to
        # mtime so "last seen" is still a real timestamp rather than "never".
        try:
            mtime = datetime.fromtimestamp(target.stat().st_mtime, tz=timezone.utc)
            data["generated_at"] = mtime.isoformat()
            data.setdefault("source", "file mtime")
        except OSError:
            pass
    return data, None


def snapshot_sections(snapshot: Optional[Dict[str, Any]]) -> Dict[str, bool]:
    """Which halves of the pull this snapshot actually carries.

    Written by ``build_snapshot``; inferred from the keys for a file written
    before that field existed or by hand.
    """
    if not isinstance(snapshot, dict):
        return {"rooms": False, "contracts": False}
    recorded = snapshot.get("sections")
    if isinstance(recorded, dict):
        return {"rooms": bool(recorded.get("rooms")),
                "contracts": bool(recorded.get("contracts"))}
    return {"rooms": isinstance(snapshot.get("rooms"), list),
            "contracts": isinstance(snapshot.get("contracts"), list)}


# ------------------------------------------------------------------- rules
def rooms_awaiting(rooms: Iterable[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    """Rooms waiting on Lorenzo, oldest first. ``unknown`` is kept and labelled.

    De-duplicated by ``room_id`` (last wins): a snapshot that merged overlapping
    pages must not print the same client twice and count them twice.
    """
    by_id = {}  # type: Dict[Any, Dict[str, Any]]
    for index, room in enumerate(rooms or []):
        if not isinstance(room, dict):
            continue
        awaiting = room.get("awaiting", room.get("awaiting_reply_from", room.get("awaiting_you")))
        if awaiting is True:
            awaiting = "you"
        if awaiting in (None, False, "", "them", "client", "freelancer_done"):
            continue
        last = parse_ts(room.get("last_message_at") or room.get("lastActivity") or room.get("last_at"))
        age = hours_between(now, last)
        room_id = room.get("room_id") or room.get("id") or ""
        by_id[room_id or ("#%d" % index)] = {
            "kind": "room",
            "room_id": room_id,
            "client": clean_text(room.get("client") or room.get("roomName") or ""),
            "job_title": clean_text(room.get("job_title") or ""),
            "contract_id": room.get("contract_id"),
            "contract_status": room.get("contract_status"),
            "awaiting": awaiting,
            "certain": awaiting == "you",
            "unread": int(_num(room.get("unread"), 0.0)),
            "last_message_at": last.isoformat() if last else None,
            "age_hours": round(age, 1) if age is not None else None,
            "sla": sla_state(age),
            "last": snippet(room.get("last") or room.get("last_message")),
            "source": "upwork_mcp",
        }
    return sort_oldest_first(list(by_id.values()))


def manual_items(snapshot: Optional[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    """Invitations and call requests the API cannot see.

    A snapshot that carries ``"manual_checks": []`` has none: absent means
    "fall back to config", empty means "none left". Treating the two the same
    made the built-in pair impossible to clear from anywhere but this file.
    """
    entries = None
    if _snapshot_owns_manual_list(snapshot):
        entries = snapshot.get("manual_checks")
    if not isinstance(entries, list):
        entries = default_manual_checks()
    retired = _retired_in_config(now)
    items = []  # type: List[Dict[str, Any]]
    for entry in entries:
        if not isinstance(entry, dict) or not _manual_is_live(entry, now):
            continue
        if _manual_key(entry) in retired:
            # Retired in config/ids.json: that is the durable switch, and it
            # wins over a list a bundle carried for one pull.
            continue
        # A date somebody typed by hand is a CT date: every other clock in this
        # job is America/Chicago.
        since = parse_ts(entry.get("since"), default_tz=settings.TZ)
        age = hours_between(now, since)
        where = clean_text(entry.get("where") or "Upwork Messages > Invitations tab")
        why = clean_text(entry.get("why") or "not visible through the API")
        items.append({
            "kind": "manual",
            "room_id": "",
            "client": clean_text(entry.get("label") or entry.get("client") or "manual check"),
            "job_title": why,
            "contract_id": None,
            "contract_status": None,
            "awaiting": "you",
            "certain": True,
            "unread": 0,
            "last_message_at": since.isoformat() if since else None,
            "age_hours": round(age, 1) if age is not None else None,
            # A check nobody can measure is not an SLA measurement. It is
            # excluded from counts.breach and from the push priority, because a
            # permanent breach pins every digest to "high" and trains its
            # reader to swipe it away.
            "sla": "manual",
            "last": "%s (%s)" % (where, why),
            "source": "manual",
        })
    return sort_oldest_first(items)


def _contract_asks(contracts: Iterable[Dict[str, Any]], now: datetime
                   ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(due now, older than the window). Shared by the two public callers."""
    live = []  # type: List[Dict[str, Any]]
    older = []  # type: List[Dict[str, Any]]
    seen = set()
    for contract in contracts or []:
        if not isinstance(contract, dict):
            continue
        cid = str(contract.get("contract_id") or contract.get("id") or "")
        if cid and cid in seen:
            continue
        if cid:
            seen.add(cid)
        status = (contract.get("status") or "").upper()
        if status not in ("CLOSED", "ENDED", "COMPLETE", "COMPLETED"):
            continue
        ended = parse_ts(contract.get("ended_at") or contract.get("endDate"))
        if ended is None:
            continue
        due = ended + timedelta(hours=POST_CONTRACT_HOURS)
        if slots.ensure_aware(now) < due:
            continue
        # One source for the three asks, so POST_CONTRACT_ASKS and the flags
        # they are suppressed by cannot drift apart.
        asks = [name for name in POST_CONTRACT_ASKS if not contract.get(ASK_FLAGS[name])]
        if not asks:
            continue
        entry = {
            "kind": "post_contract",
            "contract_id": contract.get("contract_id"),
            "client": clean_text(contract.get("client") or ""),
            "title": clean_text(contract.get("title") or ""),
            "ended_at": ended.isoformat(),
            "due_at": due.isoformat(),
            "overdue_hours": round(hours_between(now, due) or 0.0, 1),
            "asks": asks,
            "note": clean_text(contract.get("note") or ""),
            "source": "upwork_mcp",
        }
        ended_hours = hours_between(now, ended) or 0.0
        if ended_hours > POST_CONTRACT_WINDOW_DAYS * 24:
            older.append(entry)
        else:
            live.append(entry)
    for bucket in (live, older):
        bucket.sort(key=lambda r: (r.get("ended_at") or "", r.get("contract_id") or ""))
    return live, older


def post_contract_reminders(contracts: Iterable[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    """48 h after a contract ends: review, testimonial, maintenance retainer.

    Asks already made are dropped from the list; a contract with all three done
    produces no reminder at all. Nothing is drafted and nothing is sent: the
    reminder tells Lorenzo to write it.

    A contract that ended more than ``POST_CONTRACT_WINDOW_DAYS`` ago drops out
    of this list and into ``stale_contract_asks``: an ask that stale is not
    going to be made, and ten of them printed twice a day is how the section
    stops being read.
    """
    return _contract_asks(contracts, now)[0]


def stale_contract_asks(contracts: Iterable[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    """Closed contracts past the reminder window with an ask still unmade. The
    digest collapses them into one line rather than dropping them silently."""
    return _contract_asks(contracts, now)[1]


def sort_oldest_first(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Oldest wait first. An item with no readable timestamp sorts last, not
    first: an unknown age is not evidence of a long wait."""
    def key(item: Dict[str, Any]):
        age = item.get("age_hours")
        return (0 if age is not None else 1,
                -(age or 0.0),
                item.get("client") or "",
                item.get("room_id") or "")
    return sorted(items, key=key)


def freshness(snapshot: Optional[Dict[str, Any]], now: datetime,
              error: Optional[str] = None) -> Dict[str, Any]:
    """fresh | stale | missing, plus the 'last seen' timestamp for the digest."""
    if snapshot is None:
        return {"state": "missing", "generated_at": None, "age_hours": None,
                "last_seen": "never", "reason": error or "missing"}
    generated = parse_ts(snapshot.get("generated_at"))
    age = hours_between(now, generated)
    if generated is None:
        return {"state": "stale", "generated_at": None, "age_hours": None,
                "last_seen": "unknown", "reason": "no generated_at stamp"}
    last_seen = slots.to_tz(generated, settings.TZ).isoformat()
    if age is not None and age > SNAPSHOT_STALE_HOURS:
        return {"state": "stale", "generated_at": generated.isoformat(),
                "age_hours": round(age, 1), "last_seen": last_seen,
                "reason": "older than %g h" % SNAPSHOT_STALE_HOURS}
    return {"state": "fresh", "generated_at": generated.isoformat(),
            "age_hours": round(age, 1) if age is not None else None,
            "last_seen": last_seen, "reason": None}


def _carried(snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("carried"), dict):
        return {}
    return snapshot["carried"]


def coverage_notes(snapshot: Optional[Dict[str, Any]]) -> List[str]:
    """What this pull did not cover, in Lorenzo's words.

    "No closed contracts" and "the contracts call was never made" produce the
    same empty section otherwise, and the second one hides a review ask.
    These lines carry no client names, so they also go on the public push.
    """
    notes = []  # type: List[str]
    if not isinstance(snapshot, dict):
        return notes
    sections = snapshot_sections(snapshot)
    carried = _carried(snapshot)
    for half, missing in (
            ("rooms", "rooms were not in this pull, the waiting list below is invitations only"),
            ("contracts", "contracts were not in this pull, post-contract asks are not checked")):
        if sections[half]:
            continue
        if half in carried:
            stamp = parse_ts((carried[half] or {}).get("generated_at"))
            seen = slots.to_tz(stamp, settings.TZ).isoformat() if stamp else "unknown"
            notes.append("%s were not in this pull, the %s below are from the pull of %s "
                         "and may have moved on" % (half, half, seen))
        else:
            notes.append(missing)
    if snapshot.get("truncated"):
        halves = [h for h in (snapshot.get("truncated_sections") or []) if h in ("rooms", "contracts")]
        notes.append("the pull was truncated%s, older rooms or contracts are not listed" % (
            " (%s)" % " and ".join(halves) if halves else ""))
    return notes


def coverage_tag(snapshot: Optional[Dict[str, Any]]) -> Optional[str]:
    """A few words for the title when the pull was partial, else None.

    On a lock screen the title is often all that is read, and "2 waiting"
    from a pull that never checked the rooms is not "2 waiting".
    """
    if not isinstance(snapshot, dict):
        return None
    sections = snapshot_sections(snapshot)
    carried = _carried(snapshot)
    bits = []  # type: List[str]
    for half in ("rooms", "contracts"):
        if sections[half]:
            continue
        bits.append("%s from an older pull" % half if half in carried else "%s not checked" % half)
    if snapshot.get("truncated"):
        bits.append("truncated pull")
    return ", ".join(bits) or None


# ------------------------------------------------------------------ digest
def build_digest(result: Dict[str, Any]) -> str:
    """Plain text for Lorenzo. No em dashes, no exclamation marks.

    Client-written snippets are echoed verbatim after "last:"; the copy rules
    apply to the job's own words, not to what a client typed.
    """
    lines = []  # type: List[str]
    fresh = result["freshness"]
    if fresh["state"] != "fresh":
        lines.append("no fresh Upwork data, last seen %s" % fresh["last_seen"])
        if fresh["state"] == "missing":
            lines.append("run the collect helper in a Claude session: python3 jobs/upwork_rooms.py --print-collect")
        else:
            lines.append("rooms below are from that snapshot and may have moved on")
        lines.append("")

    notes = [n for n in (result.get("notes") or []) if n]
    if notes:
        lines.extend(notes)
        lines.append("")

    waiting = result["waiting"]
    has_manual = False
    if waiting:
        lines.append("Waiting on you (%d, oldest first):" % len(waiting))
        for i, item in enumerate(waiting, 1):
            who = item.get("client") or item.get("room_id") or "unknown room"
            bits = [format_age(item.get("age_hours"))]
            # The Section 6 alert line is news on a room that is hours old. On
            # one that is days old "6.6 days waiting" already says it, and
            # repeating the phrase on every row is what makes a digest unread.
            age = item.get("age_hours")
            if (item.get("kind") == "room" and item.get("sla") == "breach"
                    and age is not None and age < AGE_DAYS_SWITCH_HOURS):
                bits.append("over the 4 h alert line")
            if not item.get("certain"):
                bits.append("last sender not placed, read the thread")
            if item.get("unread"):
                bits.append("%d unread" % item["unread"])
            lines.append("%d. %s, %s" % (i, who, ", ".join(bits)))
            if item.get("kind") == "manual":
                has_manual = True
                if item.get("last"):
                    lines.append("   %s" % item["last"])
            elif item.get("last"):
                lines.append("   last: %s" % item["last"])
    elif fresh["state"] == "fresh" and (result.get("sections") or {}).get("rooms", True):
        # Only a pull that actually read the rooms can say none are waiting.
        lines.append("No Upwork rooms waiting on you.")

    if has_manual:
        lines.append("")
        lines.append("Manual checks do not clear themselves. When one is answered, mark it done in "
                     "config/ids.json upwork.manual_checks (see runbooks/upwork_rooms.md).")

    reminders = result["reminders"]
    if reminders:
        lines.append("")
        lines.append("Post-contract asks (48 h after the contract ended):")
        for i, rem in enumerate(reminders, 1):
            who = rem.get("client") or rem.get("contract_id") or "contract"
            title = rem.get("title") or "contract"
            head = "%d. %s (%s, contract %s), ended %s" % (
                i, who, title, rem.get("contract_id") or "unknown",
                (rem.get("ended_at") or "")[:10])
            asks = ", ".join(rem["asks"])
            if rem.get("note"):
                # The note first, then the ask: asking Lorenzo to request a
                # review and telling him underneath that he already did reads
                # as a contradiction he has to resolve twice a day.
                lines.append(head)
                lines.append("   note: %s" % rem["note"])
                lines.append("   confirm the note, then ask for %s" % asks)
            else:
                lines.append("%s, ask for %s" % (head, asks))
        lines.append("To stop an ask repeating, add asks_done for that contract "
                     "(see runbooks/upwork_rooms.md).")

    older = result.get("older_asks") or []
    if older:
        lines.append("")
        lines.append("%d older contract%s past the %d-day window still ha%s no ask on record: %s" % (
            len(older), "" if len(older) == 1 else "s", POST_CONTRACT_WINDOW_DAYS,
            "s" if len(older) == 1 else "ve",
            ", ".join((o.get("client") or o.get("contract_id") or "contract") for o in older)))

    lines.append("")
    lines.append("Read only. Nothing was drafted and nothing was sent on Upwork.")
    return "\n".join(lines).strip()


def digest_title(result: Dict[str, Any]) -> str:
    waiting = len(result["waiting"])
    reminders = len(result["reminders"])
    state = result["freshness"]["state"]
    if state == "missing":
        return "Upwork: no fresh data, %d manual checks" % waiting
    parts = ["%d waiting" % waiting]
    if reminders:
        parts.append("%d post-contract ask%s" % (reminders, "" if reminders == 1 else "s"))
    title = "Upwork: %s" % ", ".join(parts)
    if state != "fresh":
        # A lock screen often shows the title and nothing else. A week-old
        # count presented as this morning's is worse than no push.
        age = result["freshness"].get("age_hours")
        if age is None:
            title += " (snapshot age unknown)"
        elif age >= AGE_DAYS_SWITCH_HOURS:
            title += " (snapshot %.0f days old)" % (age / 24.0)
        else:
            title += " (snapshot %.0f h old)" % age
    tag = result.get("coverage_tag")
    if tag:
        title += " (%s)" % tag
    return title


def push_body(result: Dict[str, Any]) -> str:
    """What goes on the ntfy card.

    ntfy topics are public unless ``NTFY_TOKEN`` is set, and
    ``shared.notify.redact()`` only strips email addresses and URLs, which this
    digest has none of. So on an unprotected topic the card carries counts
    only: client names and verbatim private Upwork messages are not something
    to post to a guessable public topic.
    """
    if topic_is_protected():
        return result["digest"]
    counts = result.get("counts") or {}
    bits = ["%d waiting" % counts.get("waiting", len(result["waiting"]))]
    if counts.get("reminders"):
        bits.append("%d post-contract ask%s" % (
            counts["reminders"], "" if counts["reminders"] == 1 else "s"))
    if result["freshness"]["state"] != "fresh":
        bits.append("no fresh Upwork data, last seen %s" % result["freshness"]["last_seen"])
    lines = ["%s." % ", ".join(bits)]
    # The coverage caveats name no client, so they belong on the card: "2
    # waiting" from a pull that never checked the rooms is not "2 waiting".
    lines.extend("%s." % n for n in (result.get("notes") or []) if n)
    lines.append("Names and messages are withheld: this ntfy topic is public. The full list "
                 "went by email; run python3 jobs/upwork_rooms.py --dry-run to see it here, "
                 "or set NTFY_TOKEN.")
    return "\n".join(lines)


def push_priority(result: Dict[str, Any]) -> str:
    """high only when something measurable is late.

    Manual invitation checks are excluded on purpose: their age comes from a
    hand-written date and can never clear itself, so counting them would pin
    every push forever to high and spend the one signal the job has.
    """
    rooms_late = any(w.get("kind") == "room" and w.get("sla") == "breach"
                     for w in result["waiting"])
    newly_due = any((r.get("overdue_hours") or 0.0) <= REMINDER_NEWLY_DUE_HOURS
                    for r in result["reminders"])
    return "high" if (rooms_late or newly_due) else "default"


def _notified_state(record: Any) -> Any:
    """What actually happened to the push.

    ``shared.notify`` returns normally in shadow mode having sent nothing, so
    ``notified: true`` in the Job_Log used to mean "the call did not raise",
    which is exactly the row Lorenzo reads to check whether his phone should
    have buzzed.
    """
    if isinstance(record, dict):
        if record.get("shadow"):
            return "shadow"
        if record.get("test"):
            return "test"
        if "sent" in record:
            return bool(record.get("sent"))
    return True


# --------------------------------------------------------------------- run
def run(now: datetime,
        snapshot: Optional[Dict[str, Any]] = None,
        path: Optional[Any] = None,
        send: bool = False,
        notify_fn=None) -> Dict[str, Any]:
    """Compute the digest. Read-only: the only side effects are the Job_Log row
    and, when ``send`` is true, one ntfy push to Lorenzo (itself guarded)."""
    now = slots.ensure_aware(now)
    error = None
    if snapshot is None:
        snapshot, error = load_snapshot(path)

    fresh = freshness(snapshot, now, error)
    rooms = (snapshot or {}).get("rooms") or []
    contracts = (snapshot or {}).get("contracts") or []

    waiting = rooms_awaiting(rooms, now) + manual_items(snapshot, now)
    waiting = sort_oldest_first(waiting)
    reminders, older = _contract_asks(contracts, now)

    result = {
        "job": JOB_NAME,
        "now": now.isoformat(),
        "run_slot": scheduled_run_label(now),
        "mode": settings.get_mode(),
        "freshness": fresh,
        "sections": snapshot_sections(snapshot) if snapshot is not None else {
            "rooms": False, "contracts": False},
        "notes": coverage_notes(snapshot),
        "coverage_tag": coverage_tag(snapshot),
        "waiting": waiting,
        "reminders": reminders,
        "older_asks": older,
        "counts": {
            "waiting": len(waiting),
            "rooms": len([w for w in waiting if w["kind"] == "room"]),
            "manual": len([w for w in waiting if w["kind"] == "manual"]),
            # Rooms only: an invitation the API cannot see is not a measured
            # response time, and Section 6's Upwork scoreboard reads this.
            "breach": len([w for w in waiting
                           if w["kind"] == "room" and w["sla"] == "breach"]),
            "reminders": len(reminders),
            "older_asks": len(older),
        },
        "snapshot_path": str(snapshot_path(path)),
        "notified": False,
    }
    result["digest"] = build_digest(result)

    if send:
        fn = notify_fn or notify
        try:
            # The card is counts-only on a public topic; the email leg always
            # carries the full digest, which is the one place the room list
            # reaches Lorenzo from a scheduled run.
            record = fn(digest_title(result), push_body(result),
                        priority=push_priority(result), tags=["briefcase"],
                        email_message=result["digest"])
            result["notified"] = _notified_state(record)
        except Exception as exc:  # noqa: BLE001 - a push must never fail the check
            logger.warning("upwork_rooms: notify failed: %s", exc)
            result["notify_error"] = str(exc)

    status = {"fresh": "ok", "stale": "stale", "missing": "no_data"}.get(fresh["state"], "ok")
    if status == "ok" and result["coverage_tag"]:
        # A partial or truncated pull is not a clean "ok" in the row Lorenzo
        # reads to check the job.
        status = "partial"
    log_run(JOB_NAME, status, {
        "run_slot": result["run_slot"],
        "waiting": result["counts"]["waiting"],
        "rooms": result["counts"]["rooms"],
        "manual": result["counts"]["manual"],
        "breach": result["counts"]["breach"],
        "reminders": result["counts"]["reminders"],
        "older_asks": result["counts"]["older_asks"],
        "snapshot": fresh["state"],
        "sections": result["sections"],
        "coverage": result["coverage_tag"] or "complete",
        "last_seen": fresh["last_seen"],
        "notified": result["notified"],
    })
    return result


# --------------------------------------------------------------------- CLI
def _read_raw(source: str) -> Any:
    if source == "-":
        return json.load(sys.stdin)
    with open(source, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="upwork_rooms", description=__doc__.split("\n\n")[0])
    p.add_argument("--dry-run", action="store_true",
                   help="compute and print, Job_Log row to a scratch log, no push")
    p.add_argument("--now", action="store_true",
                   help="same, plus one notification to Lorenzo (counts only on a public "
                        "ntfy topic; --dry-run wins over this)")
    p.add_argument("--as-of", help="ISO timestamp to evaluate at (default: current time, America/Chicago)")
    p.add_argument("--snapshot", help="path to the snapshot (default: .tmp/%s)" % SNAPSHOT_FILE)
    p.add_argument("--ingest", metavar="RAW",
                   help="normalise raw Upwork MCP JSON (a file, or - for stdin) into the snapshot")
    p.add_argument("--print-collect", action="store_true",
                   help="print the read-only MCP calls a Claude session runs to refresh the snapshot")
    p.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = p.parse_args(argv)

    if args.print_collect:
        print(COLLECT_INSTRUCTIONS)
        return 0

    now = slots.parse_iso(args.as_of) if args.as_of else datetime.now(settings.TZ)

    if args.ingest:
        try:
            raw = _read_raw(args.ingest)
            previous, _ = load_snapshot(args.snapshot)
            snap = build_snapshot(raw, now, previous=previous)
            target = write_snapshot(snap, args.snapshot)
        except IngestError as exc:
            # The old snapshot is left in place on purpose: it is what makes the
            # "no fresh Upwork data" line fire once it goes stale.
            print("refusing to write the snapshot: %s" % exc, file=sys.stderr)
            log_run(JOB_NAME, "ingest_refused", {"input": args.ingest, "reason": str(exc)[:300]})
            return 2
        except (OSError, ValueError, TypeError) as exc:
            print("could not read %s: %s" % (args.ingest, exc), file=sys.stderr)
            return 2
        sections = snap.get("sections") or {}
        covered = ", ".join(k for k in ("rooms", "contracts") if sections.get(k)) or "nothing"
        log_run(JOB_NAME, "ingest", {
            "rooms": len(snap["rooms"]),
            "contracts": len(snap["contracts"]),
            "manual_checks": len(manual_items(snap, now)),
            "sections": sections,
            "carried": sorted(_carried(snap).keys()),
            "truncated": bool(snap.get("truncated")),
            "path": str(target),
        })
        print("wrote %s: %d rooms, %d contracts, %d manual checks (generated_at %s)" % (
            target, len(snap["rooms"]), len(snap["contracts"]),
            len(manual_items(snap, now)), snap["generated_at"]))
        print("  covered: %s%s" % (covered, ", pull was truncated" if snap.get("truncated") else ""))
        for half in sorted(_carried(snap).keys()):
            print("  %s carried forward from the previous snapshot (not in this pull)" % half)
        if args.json:
            print(json.dumps(snap, indent=2, default=str))
        return 0

    if args.dry_run:
        # A dry run must not write into the job log the 48-hour shadow watch
        # reads. See shared.job_log.use_scratch_logs.
        from shared.job_log import use_scratch_logs

        use_scratch_logs("upwork_rooms_dryrun")

    # --dry-run means the same thing here as everywhere else in the build:
    # compute and print, touch nothing. It wins over --now.
    send = bool(args.now) and not args.dry_run
    if args.now and args.dry_run:
        print("--dry-run given with --now: computing and printing, no push", file=sys.stderr)

    result = run(now, path=args.snapshot, send=send)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(result["digest"])
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "WARNING"))
    sys.exit(main())
