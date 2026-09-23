"""One chunked, cached reader for Instantly's analytics endpoints.

Four components read the same three endpoints: the 07:00 deliverability
monitor, the 07:00 inbox inventory, the 18:00 daily metrics and the Friday
retro packet (plus the client scorecard, per campaign). Before this module
each of them carried its own chunking loop, its own idea of what to do with a
chunk that fails, and its own answer to the 413 this workspace returns on an
unfiltered pull. Four copies of one API quirk is four places to fix it and
three places to forget.

What this module owns
---------------------
* **Chunking.** ``GET /accounts/analytics/daily`` answers HTTP 413 without an
  emails filter on this workspace, and the failure mode is a whole silent
  report rather than a visible error, so the size of a call is never left to
  the endpoint. 45 emails over 28 days did answer read-only on 2026-09-22, so
  the 413 is about the *unfiltered* call, not the list length; the chunk is
  conservative anyway because a missing report is worse than a slow one.
* **Degradation.** One failing chunk must not lose the other eleven inboxes,
  and inboxes nobody could read must be reported as *unread*, never as
  *sent nothing*. An inbox silently reported as having sent nothing reads as a
  0% reply rate, which is a removal proposal.
* **A short TTL cache**, per client object. A single run that asks for the same
  window twice (this week and last week, then the same week again for a
  per-campaign breakdown) pays for one HTTP call. The cache is process-local
  and keyed on the exact arguments, so it can never serve one window's numbers
  for another's.

The cache is deliberately *short* and *in-process*: it exists to stop one run
double-pulling, not to persist anything. Two jobs that run at 07:00 are two
processes and share nothing, which is correct: they should each see live data.

    from shared import analytics
    got = analytics.account_daily(client, emails, "2026-09-15", "2026-09-21")
    if not got.complete:
        notes.append("unread inboxes: %s" % ", ".join(got.missing))

Python 3.9 compatible.
"""
import logging
import os
import time
import weakref
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger("shared.analytics")

# Conservative default chunk. shared.thresholds.DAILY_ANALYTICS_CHUNK_EMAILS is
# the deliverability monitor's own number and is passed in by that caller; this
# is the fallback for anything that does not care.
DEFAULT_CHUNK_EMAILS = 25
# Seconds between chunked calls. Cheap insurance against the shared workspace
# budget (100 req/s, 6,000 req/min), not a limit anybody is near.
DEFAULT_CHUNK_SLEEP_SECONDS = 0.5
# How many times a failing chunk is split in half before its inboxes are given
# up and reported as unread.
DEFAULT_RETRY_DEPTH = 2
# Cache lifetime. Short on purpose: long enough that one run does not pull the
# same window twice, short enough that nothing acts on yesterday's numbers.
DEFAULT_TTL_SECONDS = 300.0

# on_error policies
RAISE = "raise"        # let the caller see the exception (the monitor's choice)
DEGRADE = "degrade"    # record the chunk as unread and carry on
HALVE = "halve"        # split the chunk and retry, then degrade

_CACHE_ATTR = "_advero_analytics_cache"
# Clients that refuse an attribute (``__slots__``) are cached here instead,
# keyed WEAKLY. Keying by id() would be a correctness hazard rather than an
# optimisation: CPython reuses the id of a collected object, so a dead client's
# rows could be served to a live one that happened to land on the same address.
_WEAK_CACHES = weakref.WeakKeyDictionary()  # type: Any
_STATS = {"hits": 0, "misses": 0}


# --------------------------------------------------------------------- cache
def ttl_seconds() -> float:
    """ANALYTICS_CACHE_TTL_SECONDS, else 300. Zero or negative disables the
    cache entirely, which is what a test that counts HTTP calls wants."""
    raw = os.environ.get("ANALYTICS_CACHE_TTL_SECONDS")
    if raw is None or str(raw).strip() == "":
        return DEFAULT_TTL_SECONDS
    try:
        return float(raw)
    except (TypeError, ValueError):
        logger.warning("ANALYTICS_CACHE_TTL_SECONDS=%r is not a number; using %.0fs",
                       raw, DEFAULT_TTL_SECONDS)
        return DEFAULT_TTL_SECONDS


def _cache_for(client: Any) -> Optional[Dict[Any, Tuple[float, Any]]]:
    """The cache belonging to this client object.

    It lives on the client so it dies with the client: two Instantly() objects
    in one process (a real one and a recorded stub in a test) never see each
    other's rows. Objects that refuse attributes (``__slots__``) fall back to a
    weak-keyed dict, and anything that is neither gets no cache at all rather
    than a cache that could be served to the wrong object.
    """
    cache = getattr(client, _CACHE_ATTR, None)
    if cache is not None:
        return cache
    cache = {}
    try:
        setattr(client, _CACHE_ATTR, cache)
        return cache
    except (AttributeError, TypeError):
        pass
    try:
        return _WEAK_CACHES.setdefault(client, cache)
    except TypeError:
        # Not weak-referenceable either: no cache at all rather than a wrong
        # one. Every call goes to the API, which is always correct.
        return None


def _cached(client: Any, key: Any, produce: Callable[[], Any]) -> Any:
    ttl = ttl_seconds()
    if ttl <= 0:
        _STATS["misses"] += 1
        return produce()
    cache = _cache_for(client)
    if cache is None:
        _STATS["misses"] += 1
        return produce()
    now = time.time()
    hit = cache.get(key)
    if hit is not None and (now - hit[0]) < ttl:
        _STATS["hits"] += 1
        return hit[1]
    _STATS["misses"] += 1
    value = produce()
    cache[key] = (now, value)
    return value


def clear_cache(client: Optional[Any] = None) -> None:
    """Drop cached rows for one client, or for every client."""
    if client is None:
        _WEAK_CACHES.clear()
        _STATS["hits"] = 0
        _STATS["misses"] = 0
        return
    try:
        setattr(client, _CACHE_ATTR, {})
        return
    except (AttributeError, TypeError):
        pass
    try:
        _WEAK_CACHES.pop(client, None)
    except TypeError:
        pass


def cache_stats() -> Dict[str, int]:
    """{'hits': n, 'misses': n} since the last clear_cache(). Evidence that the
    one-reader refactor actually removed calls rather than moving them."""
    return dict(_STATS)


# ---------------------------------------------------------------- helpers
def items(payload: Any) -> List[Dict[str, Any]]:
    """Rows out of either shape Instantly answers.

    ``GET /accounts/analytics/daily`` returns a BARE JSON ARRAY of
    ``{date, email_account, sent, bounced, contacted, new_leads_contacted,
    opened, unique_opened, replies, unique_replies, replies_automatic,
    unique_replies_automatic, clicks, unique_clicks}`` - not ``{items: [...]}``,
    which is what most of the v2 reads answer. Both are accepted here so no
    caller has to remember which endpoint does which.
    """
    if payload is None:
        return []
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        rows = payload.get("items")
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
    return []


def chunked(seq: Sequence[Any], size: int) -> List[List[Any]]:
    size = max(1, int(size or 1))
    seq = list(seq)
    return [seq[i:i + size] for i in range(0, len(seq), size)]


class AccountDaily(object):
    """The result of one windowed account-analytics pull.

    ``complete`` is False whenever a single inbox could not be read. Callers
    must say so on the card rather than printing the partial total as if it
    were the whole fleet: the difference between "12 inboxes sent 1,800" and
    "10 inboxes sent 1,500, two unread" is the difference between a healthy
    week and an incident nobody looked at.
    """

    __slots__ = ("rows", "missing", "errors", "retries", "emails", "start_date", "end_date")

    def __init__(self, rows=None, missing=None, errors=None, retries=None,
                 emails=None, start_date=None, end_date=None):
        self.rows = list(rows or [])
        self.missing = list(missing or [])
        self.errors = list(errors or [])
        self.retries = list(retries or [])
        self.emails = list(emails or [])
        self.start_date = start_date
        self.end_date = end_date

    @property
    def complete(self) -> bool:
        return not self.missing and not self.errors

    def __len__(self) -> int:
        return len(self.rows)

    def __iter__(self):
        return iter(self.rows)

    def __repr__(self):  # pragma: no cover - debugging aid
        return "<AccountDaily %d rows, %d unread, %s..%s>" % (
            len(self.rows), len(self.missing), self.start_date, self.end_date)


# ------------------------------------------------------------------- reads
def account_daily(
    client: Any,
    emails: Sequence[str],
    start_date: str,
    end_date: str,
    chunk: Optional[int] = None,
    sleep: Callable[[float], None] = time.sleep,
    sleep_seconds: float = DEFAULT_CHUNK_SLEEP_SECONDS,
    on_error: str = DEGRADE,
    retry_depth: int = DEFAULT_RETRY_DEPTH,
) -> AccountDaily:
    """GET /accounts/analytics/daily for ``emails`` over a date window.

    ``on_error``:
      * ``"raise"``   - the exception reaches the caller untouched.
      * ``"degrade"`` - the chunk's inboxes go into ``missing`` and the rest of
        the fleet is still read.
      * ``"halve"``   - the chunk is split and retried up to ``retry_depth``
        times before degrading. Use it when the likely cause is size (413).

    The whole call is cached under the exact (emails, window) it was asked for,
    so two callers in one process that want the same week pay for it once.
    """
    emails = [e for e in (emails or []) if e]
    if not emails:
        return AccountDaily(emails=[], start_date=start_date, end_date=end_date,
                            errors=["no inboxes to read"])
    if on_error not in (RAISE, DEGRADE, HALVE):
        raise ValueError("on_error must be one of %r (got %r)" % ((RAISE, DEGRADE, HALVE), on_error))
    size = int(chunk or DEFAULT_CHUNK_EMAILS)
    key = ("account_daily", tuple(emails), start_date, end_date, size, on_error, int(retry_depth))

    def produce() -> AccountDaily:
        result = AccountDaily(emails=emails, start_date=start_date, end_date=end_date)
        _pull(client, emails, start_date, end_date, size, result,
              sleep, sleep_seconds, on_error, retry_depth, 0)
        return result

    return _cached(client, key, produce)


def _pull(client, emails, start_date, end_date, size, result,
          sleep, sleep_seconds, on_error, retry_depth, depth) -> None:
    batches = chunked(emails, size)
    for i, batch in enumerate(batches):
        try:
            payload = client.daily_account_analytics(
                emails=list(batch), start_date=start_date, end_date=end_date)
        except Exception as exc:  # noqa: BLE001 - one bad chunk must not lose the rest
            if on_error == RAISE:
                raise
            if on_error == HALVE and len(batch) > 1 and depth < retry_depth:
                half = max(1, len(batch) // 2)
                result.retries.append(
                    "chunk of %d split to %d after: %s" % (len(batch), half, str(exc)[:120]))
                _pull(client, list(batch), start_date, end_date, half, result,
                      sleep, sleep_seconds, on_error, retry_depth, depth + 1)
                continue
            result.errors.append(
                "analytics for %d inbox(es) starting %s: %s" % (len(batch), batch[0], str(exc)[:200]))
            result.missing.extend(batch)
            continue
        result.rows.extend(items(payload))
        if i + 1 < len(batches) and sleep_seconds:
            sleep(sleep_seconds)


def campaign_totals(client: Any, start_date: Optional[str] = None,
                    end_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """GET /campaigns/analytics, cached.

    **Read the dates carefully.** Verified read-only 2026-09-22: with
    start_date/end_date this endpoint returns LIFETIME totals for a campaign
    that was active in the range and an empty list for one that was not. It is
    a presence filter, not a window filter, and it cannot produce a
    week-over-week or day-over-day delta. Use ``campaign_daily`` or
    ``account_daily`` for anything windowed.
    """
    key = ("campaign_totals", start_date, end_date)
    return _cached(client, key,
                   lambda: items(client.campaign_analytics(start_date=start_date, end_date=end_date)))


def campaign_daily(client: Any, campaign_id: str, start_date: str,
                   end_date: str) -> List[Dict[str, Any]]:
    """GET /campaigns/analytics/daily for one campaign, cached. This one IS a
    real window."""
    key = ("campaign_daily", campaign_id, start_date, end_date)
    return _cached(client, key,
                   lambda: items(client.daily_campaign_analytics(campaign_id, start_date, end_date)))


def campaign_steps(client: Any, campaign_id: str, start_date: Optional[str] = None,
                   end_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """GET /campaigns/analytics/steps for one campaign, cached, totals row kept.

    Callers drop the leading totals row themselves; it carries ``step: null``
    as a real JSON null on five campaigns and the literal string ``"null"`` on
    recruiting_reactivation, so the filter belongs where both shapes are known
    (``services.experiments.analytics.is_totals_row``).
    """
    key = ("campaign_steps", campaign_id, start_date, end_date)

    def produce():
        public = getattr(client, "campaign_step_analytics", None)
        if callable(public):
            return items(public(campaign_id, start_date, end_date))
        return items(client._get("campaigns/analytics/steps",
                                 {"campaign_id": campaign_id,
                                  "start_date": start_date, "end_date": end_date}))

    return _cached(client, key, produce)


# ------------------------------------------------------------- reply maths
def real_replies(row: Dict[str, Any], unique: bool = True) -> int:
    """The human-reply count for one daily row.

    **``replies`` and ``replies_automatic`` are DISJOINT counters on this
    workspace.** ``replies`` is already the human count. Subtracting one from
    the other is the single most repeated bug in this repo: on 2026-09-19 the
    twelve active inboxes recorded replies=0 with replies_automatic=7, so the
    subtraction returns -7 and sinks every inbox below the 1% line; over the
    week of Sept 14 it reported 2 instead of 17. Nothing here ever subtracts.

    ``unique`` picks ``unique_replies`` (one lead who replies three times counts
    once), which is what the Section 6 per-lead rule means.
    """
    keys = ("unique_replies", "replies") if unique else ("replies",)
    for key in keys:
        value = row.get(key)
        if value is not None:
            try:
                return max(0, int(value))
            except (TypeError, ValueError):
                return 0
    return 0
