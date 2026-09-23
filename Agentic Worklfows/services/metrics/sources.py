"""Read-only collectors for the daily metrics job (O4) and the KPI dashboard.

Every function here either performs a GET against a live system or reads a
local file. There is no write path in this module, so it is safe to run in any
mode.

Design rules that matter more than they look:

* **A number we did not measure is ``None``, never 0.** A zero written into the
  tracker is indistinguishable from a real zero day, and the Dashboard's rolling
  averages and the streak formula both treat it as a logged value. Open tracking
  is off on all six campaigns, so "Email View Rate" is permanently ``None``
  rather than a daily 0.0% that would drag the weighted average to zero.
* **``daily_account_analytics`` is chunked.** The workspace answers HTTP 413
  without an ``emails`` filter (shared/README.md); 45 inboxes in one call did
  answer 200 read-only on 2026-09-22, but the chunk keeps the query string and
  the failure blast radius small, and a failed chunk degrades the run to
  ``partial`` instead of losing the day.
* **The CT day, not the UTC day.** Instantly's analytics ``date`` field is a
  plain date string in the workspace timezone; the Job_Log is UTC. Both are
  converted to a single America/Chicago calendar day before anything is summed.
"""
import csv
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from shared import analytics
from shared import settings
from shared.instantly import Instantly, InstantlyError
from shared.paths import tmp_file

logger = logging.getLogger("services.metrics.sources")

# One chunk of inboxes per daily-account-analytics call.
ACCOUNT_CHUNK = 12
# .tmp handoff written by a Claude session that has the Upwork MCP (jobs do not).
UPWORK_DAILY_FILE = "upwork_daily.json"
UPWORK_ROOMS_FILE = "upwork_rooms.json"
# A rooms handoff older than this is a snapshot, not a measurement: answering a
# room does not rewrite the file, so "hours since last_message_at" keeps growing
# for a room that is already handled.
UPWORK_ROOMS_STALE_HOURS = 6.0
# An inbox needs this many sends in the window before its own bounce rate means
# anything (1 bounce in 8 sends is 12.5% and is noise, not a removal signal).
BOUNCE_MIN_SENT = 50

STORE_APPOINTMENT_PREFIX = "appointment:"
STORE_NOSHOW_PREFIX = "noshow_state:"


# ------------------------------------------------------------------ helpers
def ct_day(now: datetime) -> date:
    """The America/Chicago calendar day an instant belongs to."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(settings.TZ).date()


def iso(day: date) -> str:
    return day.strftime("%Y-%m-%d")


def parse_day(value: Any) -> Optional[date]:
    """A date out of an analytics row ('2026-09-21' or an ISO timestamp)."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_ts(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def note(notes: Optional[List[str]], text: str) -> None:
    if notes is not None and text not in notes:
        notes.append(text)


def day_elapsed_fraction(now: datetime, day: date, window: Optional[Tuple[int, int]] = None) -> float:
    """How much of ``day``'s sending window has passed at ``now`` (0.0 - 1.0).

    O4 runs at 18:00 CT but the send window runs to 19:00 CT, so at the
    scheduled run the day is about 92% done. Comparing a partial count against
    the whole day's plan reported "Sends/day vs plan 72%, ALERT" on a day that
    was running exactly to plan. The plan denominator is scaled by this instead.
    """
    window = window or settings.SEND_WINDOW
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(settings.TZ)
    if local.date() > day:
        return 1.0
    if local.date() < day:
        return 0.0
    start_h, end_h = window
    hours = local.hour + local.minute / 60.0 + local.second / 3600.0
    span = float(end_h - start_h)
    if span <= 0:
        return 1.0
    return max(0.0, min(1.0, (hours - start_h) / span))


def ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    """A rate, or None when the denominator cannot support one.

    Never 0.0 for "no sends": a rate with no denominator is unknown, and the
    KPI dashboard prints that instead of a green 0%."""
    if numerator is None or denominator in (None, 0):
        return None
    try:
        return float(numerator) / float(denominator)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def chunked(items: List[Any], size: int) -> Iterable[List[Any]]:
    size = max(1, int(size))
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def _num(row: Dict[str, Any], *names) -> float:
    for name in names:
        if name in row and row[name] is not None:
            try:
                return float(row[name])
            except (TypeError, ValueError):
                continue
    return 0.0


# --------------------------------------------------------------- Instantly
def active_inboxes() -> List[str]:
    return list((settings.IDS.get("instantly") or {}).get("active_inboxes") or [])


def all_inboxes(accounts: Optional[Any] = None) -> List[str]:
    """Active plus warming, from a live accounts read when one is supplied."""
    emails = [a.get("email") for a in _items(accounts) if a.get("email")]
    return emails or active_inboxes()


def fetch_account_daily(
    instantly: Instantly,
    emails: Optional[List[str]],
    start_date: str,
    end_date: str,
    chunk: int = ACCOUNT_CHUNK,
    notes: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, Any]], bool]:
    """GET /accounts/analytics/daily, chunked. Returns (rows, complete).

    The chunking, the 413 handling and the "a failed chunk must not lose the
    other inboxes" rule all live in ``shared.analytics`` now: the deliverability
    monitor, the inbox inventory and the retro packet read the same endpoint and
    each used to carry its own copy. This keeps the (rows, complete) shape and
    the note wording its callers read.
    """
    emails = list(emails or active_inboxes())
    if not emails:
        note(notes, "no inboxes configured: account analytics skipped")
        return [], False
    got = analytics.account_daily(
        instantly, emails, start_date, end_date, chunk=chunk,
        # DEGRADE, not HALVE: a chunk of 12 that fails here is much more often
        # a transport blip than a size problem, and splitting it doubles the
        # calls on a rate-limited endpoint for no new information.
        on_error=analytics.DEGRADE,
        sleep_seconds=0.0,
    )
    for message in got.errors:
        note(notes, "account analytics chunk failed: %s" % message)
    return got.rows, got.complete


def account_rows_for(rows: Iterable[Dict[str, Any]], day: date) -> List[Dict[str, Any]]:
    return [r for r in rows if parse_day(r.get("date")) == day]


def summarize_account_rows(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Sum a set of per-inbox daily rows.

    **``real_replies`` is ``unique_replies``, with nothing subtracted.**
    ``unique_replies_automatic`` is not a subset of it: in the recorded pull for
    2026-09-18 the day totals were 4 unique replies and 7 automatic, and on
    2026-09-19 they were 0 and 7. Subtracting would have given a negative count
    clamped to zero, and the first version of this function reported a 0.0% real
    reply rate for a week that really ran at about 1.1%. The two counters are
    reported side by side and the automatic one is never used as a deduction.
    Exact auto-reply exclusion needs the message bodies, which
    jobs/pipeline_sweep.py already classifies (``is_auto_reply``); that is the
    place to tighten this, not here."""
    rows = list(rows)
    sent = sum(_num(r, "sent") for r in rows)
    bounced = sum(_num(r, "bounced") for r in rows)
    replies = sum(_num(r, "unique_replies", "replies") for r in rows)
    auto = sum(_num(r, "unique_replies_automatic", "replies_automatic") for r in rows)
    return {
        "sent": int(sent),
        "bounced": int(bounced),
        "contacted": int(sum(_num(r, "contacted") for r in rows)),
        "replies": int(replies),
        "replies_automatic": int(auto),
        "real_replies": int(replies),
        "inboxes": sorted(set(r.get("email_account") for r in rows if r.get("email_account"))),
        "days": sorted(set(iso(d) for d in (parse_day(r.get("date")) for r in rows) if d)),
    }


def per_inbox_totals(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The same sums as ``summarize_account_rows``, one entry per inbox."""
    grouped = {}  # type: Dict[str, List[Dict[str, Any]]]
    for row in rows:
        email = row.get("email_account") or row.get("email")
        if not email:
            continue
        grouped.setdefault(str(email), []).append(row)
    out = []
    for email in sorted(grouped):
        totals = summarize_account_rows(grouped[email])
        totals["email"] = email
        totals["bounce_rate"] = ratio(totals["bounced"], totals["sent"])
        out.append(totals)
    return out


def worst_bounce_inbox(rows: Iterable[Dict[str, Any]],
                       min_sent: int = BOUNCE_MIN_SENT) -> Optional[Dict[str, Any]]:
    """The single worst inbox by bounce rate over ``rows``, or None.

    Section 6's action on bounce rate is per inbox ("> 2% remove inbox"), but
    the dashboard row is the aggregate across twelve inboxes: one inbox
    bouncing 8% is diluted to 0.7% and reads green on the day it needs pulling.
    Inboxes under ``min_sent`` sends are skipped because their rate is noise."""
    candidates = [i for i in per_inbox_totals(rows)
                  if i.get("bounce_rate") is not None and i["sent"] >= min_sent]
    if not candidates:
        return None
    return max(candidates, key=lambda i: i["bounce_rate"])


def fetch_campaign_day(
    instantly: Instantly,
    start_date: str,
    end_date: str,
    notes: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, Any]], bool]:
    """GET /campaigns/analytics for a date window. Returns (rows, complete).

    An empty list is a real answer (no sends in the window), not a failure."""
    try:
        return _items(instantly.campaign_analytics(start_date=start_date, end_date=end_date)), True
    except InstantlyError as exc:
        note(notes, "campaign analytics failed: %s" % str(exc)[:160])
        return [], False


def summarize_campaign_rows(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(rows)
    per = []
    for row in rows:
        cid = row.get("campaign_id")
        meta = settings.CAMPAIGN_BY_ID.get(cid or "", {})
        per.append({
            "campaign_id": cid,
            "key": meta.get("key"),
            "name": row.get("campaign_name"),
            "sent": int(_num(row, "emails_sent_count")),
            "contacted": int(_num(row, "contacted_count")),
            "replies": int(_num(row, "reply_count_unique", "reply_count")),
            "replies_automatic": int(_num(row, "reply_count_automatic_unique", "reply_count_automatic")),
            "bounced": int(_num(row, "bounced_count")),
            "opportunities": int(_num(row, "total_opportunities")),
            "opportunity_value": _num(row, "total_opportunity_value"),
        })
    per.sort(key=lambda c: (-c["sent"], c.get("name") or ""))
    totals = {
        "sent": sum(c["sent"] for c in per),
        "contacted": sum(c["contacted"] for c in per),
        "replies": sum(c["replies"] for c in per),
        "replies_automatic": sum(c["replies_automatic"] for c in per),
        "bounced": sum(c["bounced"] for c in per),
        "opportunities": sum(c["opportunities"] for c in per),
        "opportunity_value": sum(c["opportunity_value"] for c in per),
    }
    # Same rule as summarize_account_rows: the automatic counter is reported,
    # never subtracted (reply_count_automatic exceeded reply_count_unique in the
    # 2026-09-21 snapshot, 22 against 17).
    totals["real_replies"] = totals["replies"]
    return {"campaigns": per, "totals": totals}


def fetch_accounts(instantly: Instantly, notes: Optional[List[str]] = None) -> Optional[Any]:
    try:
        return instantly.list_accounts(limit=100)
    except InstantlyError as exc:
        note(notes, "accounts list failed: %s" % str(exc)[:160])
        return None


def warmup_health(accounts: Any, emails: Optional[List[str]] = None) -> Dict[str, Any]:
    """Warm-up score per inbox, limited to ``emails`` when given.

    Section 6 alerts below 98. ``worst`` is None when nothing could be read, so
    the dashboard says "no data" instead of a green 0."""
    wanted = set(e.lower() for e in (emails or []))
    scores = {}
    for account in _items(accounts):
        email = (account.get("email") or "").lower()
        if not email or (wanted and email not in wanted):
            continue
        raw = account.get("stat_warmup_score")
        if raw is None:
            continue
        try:
            scores[email] = float(raw)
        except (TypeError, ValueError):
            continue
    below = sorted(e for e, s in scores.items() if s < 98.0)
    return {
        "scores": scores,
        "worst": min(scores.values()) if scores else None,
        "below_98": below,
        "count": len(scores),
    }


def plan_sends_per_day(emails: Optional[List[str]] = None) -> Optional[int]:
    """Planned daily volume: active inboxes x the per-inbox daily limit."""
    inst = settings.IDS.get("instantly") or {}
    limit = inst.get("per_inbox_daily_limit")
    inboxes = emails if emails is not None else active_inboxes()
    if not limit or not inboxes:
        return None
    try:
        return int(limit) * len(inboxes)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------- Upwork
def read_upwork_daily(path: Optional[Path] = None, day: Optional[date] = None,
                      notes: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """`.tmp/upwork_daily.json`, written by a Claude session with the Upwork MCP.

    Shape (every value field optional, ``date`` required):
        {"date": "2026-09-22", "proposals": 3, "connects": 120, "views": 2,
         "replies": 1, "hires": 0, "response_time_hours": 0.4,
         "proposals_7d": 14, "replies_7d": 2}

    Returns None when the file is absent (the job notes it and leaves the
    Upwork cells blank) and None when the file is not for the day being
    reported, because a stale handoff silently logged as today is worse than a
    gap.

    **A handoff with no ``date`` is treated as absent**, not as today's.
    The guard used to be ``data.get("date") and parse_day(...) != day``, so a
    file with no date short-circuited past it and the same proposals and the
    same Connects spend were written into the tracker (and into the public
    DAILY UPDATE post) every day until somebody overwrote the file."""
    path = path or tmp_file(UPWORK_DAILY_FILE)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.warning("could not read %s: %s", path, exc)
        return None
    if not isinstance(data, dict):
        return None
    if day is not None:
        stamped = parse_day(data.get("date"))
        if stamped is None:
            logger.warning("upwork handoff %s carries no usable date: ignored", path)
            note(notes, "the Upwork handoff carries no date field: ignored rather than logged as "
                        "%s (write \"date\": \"%s\" into .tmp/%s)" % (iso(day), iso(day), UPWORK_DAILY_FILE))
            return None
        if stamped != day:
            logger.warning("upwork handoff %s is for %s, not %s: ignored", path, data.get("date"), iso(day))
            note(notes, "the Upwork handoff is dated %s, not %s: ignored" % (iso(stamped), iso(day)))
            return None
    out = dict(data)
    out.setdefault("proposals", None)
    out.setdefault("connects", None)
    if out.get("view_rate") is None:
        out["view_rate"] = ratio(data.get("views"), data.get("proposals"))
    if out.get("reply_rate") is None:
        out["reply_rate"] = ratio(data.get("replies"), data.get("proposals"))
    out["reply_rate_7d"] = (
        data.get("reply_rate_7d")
        if data.get("reply_rate_7d") is not None
        else ratio(data.get("replies_7d"), data.get("proposals_7d"))
    )
    out["source"] = str(path)
    return out


def read_upwork_rooms_file(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """`.tmp/upwork_rooms.json` with its own ``generated_at``.

    Returns {"rooms": [...], "generated_at": <str or None>, "source": path}, or
    None when the file is absent."""
    path = path or tmp_file(UPWORK_ROOMS_FILE)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.warning("could not read %s: %s", path, exc)
        return None
    if isinstance(data, dict):
        rooms = data.get("rooms", [])
        generated_at = data.get("generated_at") or data.get("as_of")
        # A pull that carried only the contracts keeps the previous rooms with
        # their own, older stamp (jobs/upwork_rooms.py). The staleness check
        # has to read that stamp, not the newer pull's.
        carried = data.get("carried") if isinstance(data.get("carried"), dict) else {}
        if isinstance(carried.get("rooms"), dict) and carried["rooms"].get("generated_at"):
            generated_at = carried["rooms"]["generated_at"]
    else:
        rooms, generated_at = data, None
    return {"rooms": list(rooms) if isinstance(rooms, list) else [],
            "generated_at": generated_at, "source": str(path)}


def read_upwork_rooms(path: Optional[Path] = None) -> Optional[List[Dict[str, Any]]]:
    """The same `.tmp/upwork_rooms.json` jobs/pipeline_sweep.py reads."""
    payload = read_upwork_rooms_file(path)
    return None if payload is None else payload["rooms"]


def upwork_response(
    rooms: Optional[List[Dict[str, Any]]],
    now: datetime,
    generated_at: Optional[Any] = None,
    stale_after_hours: float = UPWORK_ROOMS_STALE_HOURS,
) -> Dict[str, Any]:
    """Worst wait among rooms awaiting Lorenzo, **and which room it is**.

    Two things the bare number could not say:

    * the room. The dashboard row used to read "171.2 h ALERT" with the client
      named nowhere, so the one-glance dashboard could not say what to do next.
    * whether the handoff is still current. Answering a room does not rewrite
      `.tmp/upwork_rooms.json`; without a freshness check the same handled room
      keeps aging and fires one high-priority push per run forever. Past
      ``stale_after_hours`` the metric degrades to None with a note, the way
      ``read_upwork_daily`` already refuses a stale dated handoff.

    Returns {"hours", "room", "stale", "generated_at", "note"}."""
    out = {"hours": None, "room": None, "stale": False,
           "generated_at": generated_at, "note": None}  # type: Dict[str, Any]
    if not rooms:
        return out
    stamped = parse_ts(generated_at)
    if stamped is not None:
        age = (now - stamped).total_seconds() / 3600.0
        if age > stale_after_hours:
            out["stale"] = True
            out["note"] = ("the rooms handoff was written %.0f h ago (%s); a room answered since "
                           "then would still be counted, so this is not measured"
                           % (age, str(generated_at)))
            return out
    best = None
    for room in rooms:
        awaiting = room.get("awaiting", room.get("awaiting_you"))
        if awaiting in (None, False, "", "client", "them"):
            continue
        last = parse_ts(room.get("last_message_at") or room.get("last_at"))
        if last is None:
            continue
        hours = (now - last).total_seconds() / 3600.0
        if best is None or hours > best[0]:
            best = (hours, room)
    if best is None:
        return out
    hours, room = best
    label = (room.get("client") or room.get("client_name") or room.get("title")
             or room.get("name") or room.get("room_id") or room.get("id"))
    out["hours"] = hours
    out["room"] = str(label) if label else None
    if out["room"]:
        out["note"] = "the longest wait is %s (%.0f h)" % (out["room"], hours)
    return out


def upwork_response_hours(rooms: Optional[List[Dict[str, Any]]], now: datetime,
                          generated_at: Optional[Any] = None) -> Optional[float]:
    """Worst wait among rooms awaiting Lorenzo (Section 6 "Upwork response time")."""
    return upwork_response(rooms, now, generated_at=generated_at)["hours"]


# ---------------------------------------------------------------------- GHL
STAGE_LABELS = ("new_reply", "call_booked", "proposal_sent", "won", "lost", "follow_up_later")


# The only fields that date a move INTO the stage an opportunity sits in.
# ``updatedAt`` is not one of them: it moves on any edit (a note, a tag, a
# value change, the nightly mirror touching the record), so reading it as a
# stage change wrote two August closes and an August proposal into the 09-21
# row as today's flow, and the retro counted a phantom $10,000 week.
STAGE_CHANGE_FIELDS = ("lastStageChangeAt", "last_stage_change_at", "stage_changed_at")
# Won and lost are also a STATUS in GHL, and marking a deal won does not always
# move its stage, so for those two stages the status change dates the move too,
# used only when the stage change date is absent.
STATUS_CHANGE_FIELDS = ("lastStatusChangeAt", "last_status_change_at")
STATUS_STAGES = ("won", "lost")
# Pagination only: the cursor is whatever timestamp the page is sorted by, which
# is unrelated to what counts as a stage change.
CURSOR_FIELDS = ("lastStageChangeAt", "lastStatusChangeAt", "last_stage_change_at",
                 "stage_changed_at", "updatedAt")


def stage_changed_at(opp: Dict[str, Any], stage: Optional[str]) -> Tuple[Optional[datetime], Optional[str]]:
    """(when the opportunity entered ``stage``, the field that said so).

    (None, None) when nothing on the record dates the stage move. An edit
    timestamp is never used: an edit is not a close and not a proposal."""
    fields = STAGE_CHANGE_FIELDS + (STATUS_CHANGE_FIELDS if stage in STATUS_STAGES else ())
    for field in fields:
        changed = parse_ts(opp.get(field))
        if changed is not None:
            return changed, field
    return None, None


def _opportunities(payload: Any) -> List[Dict[str, Any]]:
    rows = _items(payload)
    if not rows and isinstance(payload, dict):
        rows = [o for o in (payload.get("opportunities") or []) if isinstance(o, dict)]
    return rows


def ghl_stage_counts(
    ghl,
    day: Optional[date] = None,
    notes: Optional[List[str]] = None,
    page_limit: int = 100,
    max_pages: int = 20,
) -> Optional[Dict[str, Any]]:
    """The Sales pipeline, paginated, as occupancy **and** dated transitions.

    Returns None without a token (``shared.ghl`` returns None from every read
    when GHL_PRIVATE_INTEGRATION_TOKEN is unset, which is today's state), or::

        {"stages": {stage: open opportunities now},
         "dated":  {stage: opportunities whose stage changed on ``day``} or None,
         "dated_field": the timestamp field that carried the dates,
         "complete": False when the pipeline was truncated,
         "pages": n, "counted": n}

    Two things this is careful about:

    * **Occupancy is not a flow.** "4 opportunities sit in Won" is a census, not
      "4 closed today". Writing the census into the tracker's daily ``Closes``
      column re-counted the same two September clients every evening and the
      all-time total (which sums that column) grew by 2 a day. ``dated`` is the
      only thing a caller may write into a daily column, and it is None when no
      opportunity carries a usable stage-change timestamp.
    * **One page is not the pipeline.** ``shared.ghl.search_opportunities``
      takes ``start_after_id`` precisely because, in its own words, without it
      "pipeline_sync stops at 100 opportunities and refuses the whole nightly
      apply as ghl_truncated". This follows the cursor and, if it runs out of
      pages, says so with ``complete: False`` instead of reporting a capped
      number as if it were the total."""
    pipeline_id = settings.GHL_SALES_PIPELINE_ID
    if not pipeline_id:
        note(notes, "no GHL sales pipeline id in ids.json: pipeline counts skipped")
        return None
    by_id = {v: k for k, v in (settings.GHL_STAGES or {}).items()}
    counts = dict((name, 0) for name in STAGE_LABELS)
    dated = dict((name, 0) for name in STAGE_LABELS)
    dated_field = None
    seen_any_timestamp = False
    undated = dict((name, 0) for name in STAGE_LABELS)
    complete = True
    pages = 0
    counted = 0
    cursor_id = None
    cursor_value = None
    while True:
        try:
            payload = ghl.search_opportunities(
                pipeline_id=pipeline_id, limit=page_limit,
                start_after_id=cursor_id, start_after=cursor_value)
        except Exception as exc:  # noqa: BLE001 - a GHL outage must not kill the metrics run
            note(notes, "ghl opportunities read failed: %s" % str(exc)[:160])
            return None
        if payload is None:
            if pages == 0:
                note(notes, "ghl_token_missing: pipeline counts, show rate and close rate are unavailable")
                return None
            complete = False
            note(notes, "ghl pipeline read stopped after %d page(s): the counts are partial" % pages)
            break
        rows = _opportunities(payload)
        pages += 1
        counted += len(rows)
        for opp in rows:
            stage = by_id.get(opp.get("pipelineStageId") or opp.get("stage_id") or "")
            if not stage:
                continue
            counts[stage] = counts.get(stage, 0) + 1
            changed, field = stage_changed_at(opp, stage)
            if changed is None:
                undated[stage] = undated.get(stage, 0) + 1
                continue
            seen_any_timestamp = True
            dated_field = dated_field or field
            if day is not None and ct_day(changed) == day:
                dated[stage] = dated.get(stage, 0) + 1
        if len(rows) < page_limit:
            break
        if pages >= max_pages:
            complete = False
            note(notes, "ghl pipeline is larger than %d opportunities: the stage counts are "
                        "truncated and are reported as partial" % (max_pages * page_limit))
            break
        last = rows[-1]
        cursor_id = last.get("id") or last.get("_id")
        cursor_value = None
        for field in CURSOR_FIELDS + ("createdAt",):
            if last.get(field) is not None:
                cursor_value = last.get(field)
                break
        if not cursor_id:
            complete = False
            note(notes, "ghl pipeline page carried no opportunity id to continue from: partial")
            break
    if day is not None and not seen_any_timestamp and counted:
        note(notes, "no GHL opportunity carries a stage-change timestamp (lastStageChangeAt), so "
                    "\"Proposals Sent\" and \"Closes\" stay blank rather than repeating today's "
                    "pipeline census or reading an edit time as a close")
    dated_out = dated if (day is not None and seen_any_timestamp) else None
    if dated_out is not None:
        # A flow column with an undated opportunity in its stage could be
        # missing that move, so it is left blank rather than written short.
        for stage in ("proposal_sent", "won"):
            if undated.get(stage):
                dated_out = dict(dated_out, **{stage: None})
                note(notes, "%d opportunit%s in %s carr%s no stage-change date, so that column is "
                            "left blank rather than written as a possibly short count"
                     % (undated[stage], "y" if undated[stage] == 1 else "ies", stage,
                        "ies" if undated[stage] == 1 else "y"))
    return {
        "stages": counts,
        "dated": dated_out,
        "undated": undated,
        "dated_field": dated_field,
        "complete": complete,
        "pages": pages,
        "counted": counted,
    }


# ----------------------------------------------------- reply engine signals
def read_job_log(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """The Job_Log CSV as dicts, with ``details`` parsed. Never raises."""
    from shared.job_log import job_log_path

    path = Path(path) if path else job_log_path()
    rows = []  # type: List[Dict[str, Any]]
    try:
        with open(path, "r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                try:
                    row["details_parsed"] = json.loads(row.get("details") or "{}")
                except (ValueError, TypeError):
                    row["details_parsed"] = {}
                rows.append(row)
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        logger.warning("could not read job log %s: %s", path, exc)
    return rows


def job_log_read_path() -> Path:
    """Where a *reader* should look for the Job_Log.

    ``shared.job_log.use_scratch_logs`` repoints JOB_LOG_PATH at a per-run
    scratch file so a dry run's own rows never pollute `.tmp/job_log.csv`. That
    is a **write** redirection; a job that then reads JOB_LOG_PATH reads its own
    empty scratch file and reports the reply engine as silent. Entry points call
    this **before** ``use_scratch_logs`` and pass the result down."""
    from shared.job_log import job_log_path

    return job_log_path()


def job_log_for_day(rows: Iterable[Dict[str, Any]], day: date) -> List[Dict[str, Any]]:
    return job_log_for_range(rows, day, day)


def job_log_for_range(rows: Iterable[Dict[str, Any]], start: date, end: date) -> List[Dict[str, Any]]:
    out = []
    for row in rows:
        ts = parse_ts(row.get("ts_utc"))
        if ts is not None and start <= ct_day(ts) <= end:
            out.append(row)
    return out


# sent_manually: a card stuck at send_failed, or at sending past its lease
# (approval.SEND_CLAIM_LEASE_MINUTES), whose reply did go out, closed with
# Mark sent (approval.mark_sent_manually); counted on the day it was marked.
DRAFT_SENT_STATUSES = ("sent", "would_send", "auto_send", "sent_manually")
DRAFT_CREATED_STATUSES = ("created",)


def engine_metrics(
    job_rows: Iterable[Dict[str, Any]],
    store: Any,
    day: date,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Drafts sent, calls booked and show rate for one CT day.

    Sources: the reply engine's own Job_Log rows (``reply_engine.approval``)
    and the store rows booking/no_show write (``appointment:*``,
    ``noshow_state:*``). Both are local, so this works with no GHL token.

    ``show_rate`` is None until at least one call on that day has a verdict:
    0% and "no calls yet" are different facts."""
    rows = job_log_for_day(job_rows, day)
    drafts_sent = 0
    drafts_created = 0
    would_send = 0
    for row in rows:
        if row.get("job") != "reply_engine.approval":
            continue
        status = row.get("status")
        if status in DRAFT_SENT_STATUSES:
            drafts_sent += 1
            if status == "would_send":
                would_send += 1
        elif status in DRAFT_CREATED_STATUSES:
            drafts_created += 1

    booked_today = 0
    held = 0
    no_show = 0
    calls_on_day = 0
    appointments = []  # type: List[Dict[str, Any]]
    if store is not None:
        try:
            appointments = [v for _k, v in store.items(STORE_APPOINTMENT_PREFIX) if isinstance(v, dict)]
        except Exception as exc:  # noqa: BLE001 - a store read must not kill the run
            logger.warning("store appointment read failed: %s", exc)
            appointments = []
        for appt in appointments:
            booked_at = parse_ts(appt.get("booked_at"))
            if booked_at is not None and ct_day(booked_at) == day:
                booked_today += 1
        try:
            states = [(k, v) for k, v in store.items(STORE_NOSHOW_PREFIX) if isinstance(v, dict)]
        except Exception as exc:  # noqa: BLE001
            logger.warning("store no-show read failed: %s", exc)
            states = []
        for _key, state in states:
            start = parse_ts(state.get("start_iso"))
            if start is None or ct_day(start) != day:
                continue
            calls_on_day += 1
            verdict = state.get("state") or state.get("verdict")
            if verdict == "showed":
                held += 1
            elif verdict == "no_show":
                no_show += 1

    decided = held + no_show
    engine_rows_today = [r for r in rows if str(r.get("job") or "").startswith("reply_engine.")]
    return {
        "drafts_sent": drafts_sent,
        "drafts_would_send": would_send,
        "drafts_created": drafts_created,
        "calls_booked": booked_today,
        "calls_on_day": calls_on_day,
        "calls_held": held if decided else None,
        "no_shows": no_show if decided else None,
        "show_rate": ratio(held, decided),
        "appointments_known": len(appointments),
        # Scoped to the day being reported. ``appointments_known`` counts every
        # appointment the store has ever held, so one booking from August made
        # the job believe the engine had run today and write "Calls Booked = 0"
        # into every later row, marking the day logged and continuing the streak
        # off a number nobody measured.
        "engine_rows_on_day": len(engine_rows_today),
        "process_events_on_day": len([r for r in engine_rows_today
                                      if r.get("job") == "reply_engine.process_event"]),
        "booked_on_day": booked_today,
        "verdicts_on_day": decided,
        "artifacts_on_day": bool(engine_rows_today) or booked_today > 0 or calls_on_day > 0,
    }


def _store_rows(store: Any, prefix: str) -> List[Tuple[str, Dict[str, Any]]]:
    if store is None:
        return []
    try:
        return [(k, v) for k, v in store.items(prefix) if isinstance(v, dict)]
    except Exception as exc:  # noqa: BLE001 - a store read must not kill the run
        logger.warning("store read failed for %s: %s", prefix, exc)
        return []


def bookings_in_range(store: Any, start: date, end: date) -> int:
    """Appointments whose ``booked_at`` falls in the window."""
    count = 0
    for _key, appt in _store_rows(store, STORE_APPOINTMENT_PREFIX):
        booked_at = parse_ts(appt.get("booked_at"))
        if booked_at is not None and start <= ct_day(booked_at) <= end:
            count += 1
    return count


def show_rate_range(store: Any, start: date, end: date, min_decided: int = 3) -> Dict[str, Any]:
    """Show rate over a window, with a minimum sample.

    Section 6's 90% green / 80% alert lines are sized for a weekly cohort. On a
    single-call day the metric can only be 0% or 100%, so a one-call day with
    one no-show fired a "show rate emergency" push. Below ``min_decided``
    decided calls the rate is None (no data) and the note says why."""
    held = 0
    no_show = 0
    scheduled = 0
    for _key, state in _store_rows(store, STORE_NOSHOW_PREFIX):
        starts = [parse_ts(state.get("start_iso")), parse_ts(state.get("previous_start_iso"))]
        if not any(s is not None and start <= ct_day(s) <= end for s in starts):
            continue
        scheduled += 1
        verdict = state.get("state") or state.get("verdict")
        reason = state.get("done_reason")
        previous = state.get("previous_state")
        if verdict in ("showed", "late_show"):
            held += 1
        elif verdict == "no_show" or reason == "rebooked" or previous == "no_show":
            no_show += 1
    decided = held + no_show
    enough = decided >= max(1, int(min_decided))
    return {
        "calls": scheduled,
        "held": held,
        "no_shows": no_show,
        "decided": decided,
        "rate": ratio(held, decided) if enough else None,
        "min_decided": min_decided,
        "enough": enough,
    }


def no_show_rebooked_range(store: Any, start: date, end: date) -> Dict[str, Any]:
    """Of the no-shows in the window, how many were rebooked.

    ``services/reply_engine/no_show.py`` records a rebooking two ways: a
    reschedule that keeps the appointment id resets the state to ``pending``
    with ``previous_state: no_show``, and ``cancel_recovery_for_rebooking``
    writes ``state: done`` with ``done_reason: rebooked``. Both are counted,
    against every row that was ever a no-show in the window."""
    no_shows = 0
    rebooked = 0
    for _key, state in _store_rows(store, STORE_NOSHOW_PREFIX):
        starts = [parse_ts(state.get("start_iso")), parse_ts(state.get("previous_start_iso"))]
        if not any(s is not None and start <= ct_day(s) <= end for s in starts):
            continue
        verdict = state.get("state") or state.get("verdict")
        reason = state.get("done_reason")
        previous = state.get("previous_state")
        was_no_show = verdict == "no_show" or reason == "rebooked" or previous == "no_show"
        if not was_no_show:
            continue
        no_shows += 1
        if reason == "rebooked" or previous == "no_show":
            rebooked += 1
    return {"no_shows": no_shows, "rebooked": rebooked,
            "rate": ratio(rebooked, no_shows) if no_shows else None}


# Not sent_manually: its row's sent_at is when Lorenzo pressed Mark sent, and
# the reply left somewhere between send_failed_at (send_started_at for a card
# taken from sending) and then; its first_reply is None when the lead's row
# could not be read. A time that is not known is skipped, not estimated (see
# first_reply_minutes).
FIRST_REPLY_SENT_STATUSES = ("sent",)
REPLY_AT_KEYS = ("reply_at", "reply_ts", "received_at", "reply_received_at")


def first_reply_minutes(job_rows: Iterable[Dict[str, Any]], day: date) -> Optional[float]:
    """Median minutes from a lead's reply landing to Lorenzo's answer being SENT.

    Section 6's "Time to first reply" is reply landed -> reply sent. It used to
    read ``reply_engine.approval`` / ``created`` rows, which is reply -> draft
    queued, the wrong interval, and no ``created`` row carries the reply time
    anyway, so the row could never produce a value.

    Now: every ``reply_engine.approval`` / ``sent`` row on ``day`` (a real send;
    a shadow ``would_send`` is not one) is paired with the time the lead's reply
    landed, read from the sent row's own details (``reply_at``) or, failing
    that, from the ``created`` row for the same approval. A row with no recorded
    reply time is skipped rather than estimated from the engine's processing
    time, which misses the poller's lag and would flatter the number. None when
    no send on that day can be paired (in shadow nothing is sent).

    The engine logs both ends on the sent row (OPS-10, approval.send_approved):
    ``reply_at`` is the lead's reply's own received time, recorded on the card
    when it was raised, and ``sent_at`` is when the answer went out, which is
    used over the row's write time when present. ``first_reply`` says whether
    it was the lead's first answer from us: a later answer in the same thread
    (``first_reply: false``) is not a first reply and is left out. Rows from
    before the flag existed count.
    """
    rows = list(job_rows or [])
    reply_at_by_approval = {}  # type: Dict[str, datetime]
    for row in rows:
        if row.get("job") != "reply_engine.approval" or row.get("status") != "created":
            continue
        details = row.get("details_parsed") or {}
        approval = details.get("approval")
        reply_at = _reply_at(details)
        if approval and reply_at is not None:
            reply_at_by_approval[str(approval)] = reply_at
    deltas = []
    for row in job_log_for_day(rows, day):
        if row.get("job") != "reply_engine.approval" or row.get("status") not in FIRST_REPLY_SENT_STATUSES:
            continue
        details = row.get("details_parsed") or {}
        if details.get("first_reply") is False:
            continue
        reply_at = _reply_at(details)
        if reply_at is None and details.get("approval"):
            reply_at = reply_at_by_approval.get(str(details["approval"]))
        sent = parse_ts(details.get("sent_at")) or parse_ts(row.get("ts_utc"))
        if reply_at is None or sent is None:
            continue
        minutes = (sent - reply_at).total_seconds() / 60.0
        if minutes >= 0:
            deltas.append(minutes)
    if not deltas:
        return None
    deltas.sort()
    mid = len(deltas) // 2
    if len(deltas) % 2:
        return deltas[mid]
    return (deltas[mid - 1] + deltas[mid]) / 2.0


def _reply_at(details: Dict[str, Any]) -> Optional[datetime]:
    for key in REPLY_AT_KEYS:
        stamp = parse_ts(details.get(key))
        if stamp is not None:
            return stamp
    return None


def positive_replies(job_rows: Iterable[Dict[str, Any]], day: date) -> Optional[int]:
    """Positives the engine classified on that day, or None when it has not run.

    A day with no engine rows at all is unknown, not zero: the engine is in
    shadow and may simply not have been running."""
    return positive_replies_range(job_rows, day, day)


def positive_replies_range(job_rows: Iterable[Dict[str, Any]], start: date,
                           end: date) -> Optional[int]:
    """Positives classified across a window, or None when the engine never ran in it.

    The KPI "Positive reply rate" divides by a seven-day send total, so its
    numerator has to cover the same seven days. Dividing one day's positives by
    the week's sends understated the rate about sevenfold and printed ALERT
    ("< 0.5%, rework or kill the campaign") on a green week."""
    rows = job_log_for_range(job_rows, start, end)
    engine_rows = [r for r in rows if str(r.get("job") or "").startswith("reply_engine.")]
    if not engine_rows:
        return None
    # Distinct leads, not events. A lead who replies "yes", then "Tuesday
    # works" is one positive; counting both events inflated the rate Section 6
    # judges per lead. A row with no lead on it is counted on its own.
    leads = set()
    for index, row in enumerate(engine_rows):
        if row.get("job") != "reply_engine.process_event":
            continue
        details = row.get("details_parsed") or {}
        label = str(details.get("label") or details.get("classification") or "")
        if label.startswith("positive"):
            lead = str(details.get("lead") or details.get("lead_email") or "").strip().lower()
            leads.add(lead or "#row%d" % index)
    return len(leads)
