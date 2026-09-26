"""Instantly API v2 client (httpx, dependency-injected).

Reads always go to the API. Writes call ``settings.guard_write('instantly',
name, payload)`` FIRST; in shadow they return the guard record and perform no
HTTP request at all. Only MODE=live + ALLOW_LIVE_WRITES=1 sends anything.

    from shared.instantly import Instantly
    c = Instantly()                         # keys from the environment, see below
    c.list_campaigns()['items']

    # tests
    c = Instantly(api_key='x', transport=httpx.MockTransport(handler))

Keys (decision R2(a), shared/keys.py, runbooks/read_only_keys.md): every call
that is not a guarded write sends the read key, ``INSTANTLY_API_KEY_READ``, or
``INSTANTLY_API_KEY`` while no read key exists. Only the body of ``_write``,
after ``guard_write`` has said live, sends ``INSTANTLY_API_KEY``. The split is
by method, not by HTTP verb: ``list_leads`` is a POST and a read. A 403 on a
read made with the read-only key raises :class:`InstantlyScopeError` naming the
scope the endpoint needs (``ENDPOINTS`` below; unverified scopes say so).
"""
import logging
import re
import threading
import time
from urllib.parse import quote
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import httpx

from shared import keys, settings

logger = logging.getLogger("shared.instantly")

DEFAULT_BASE_URL = "https://api.instantly.ai/api/v2"
RETRY_STATUSES = (429, 502, 503, 504)
MAX_RETRIES = 3
MAX_BACKOFF_SECONDS = 60.0  # GET /emails is capped at 20 requests/minute
# POST endpoints that only read. Everything else that is not a GET is a write
# and is never retried: a 429 can arrive after Instantly has already queued the
# send, and there is no idempotency key, so a retry is a duplicate email.
READ_POST_PATHS = (
    "leads/list",
    "accounts/warmup-analytics",
    # Two more POSTs that only read, both confirmed at runtime by the
    # deliverability monitor: without them on this list a single 429 or 503 on
    # either one killed the whole level 1 or level 2 report rather than being
    # retried like the GET beside it.
    "accounts/test/vitals",
    "inbox-placement-analytics/stats-by-test-id",
)


SYSTEM = "instantly"

# Every endpoint this client calls: (method, path regex, access, scope, verified).
# ``access`` is which key the client method sends; it is decided per method, so
# the ``read`` POSTs (leads/list and friends) are reads. ``scope`` is the
# narrowest Instantly API-key scope known to allow the call. Only three were
# verified against developer.instantly.ai on 2026-09-22 (verified=True); every
# other row is UNVERIFIED and carries None, because the reference page lists no
# scope for it (GET /campaigns/analytics among them). all:read is expected to
# cover the reads; that too is unverified per row.
# config/instantly_api_contract.md carries the same table for people.
ENDPOINTS = (
    # --- reads (read key)
    ("GET", r"campaigns", "read", None, False),
    ("GET", r"campaigns/analytics", "read", None, False),
    ("GET", r"campaigns/analytics/daily", "read", None, False),
    ("GET", r"campaigns/analytics/steps", "read", None, False),
    ("GET", r"campaigns/[^/]+", "read", None, False),
    ("GET", r"accounts", "read", None, False),
    ("GET", r"accounts/analytics/daily", "read", None, False),
    ("GET", r"accounts/[^/]+", "read", None, False),
    ("POST", r"accounts/warmup-analytics", "read", None, False),
    ("POST", r"accounts/test/vitals", "read", None, False),
    ("GET", r"emails", "read", "emails:read", True),
    ("GET", r"emails/[^/]+", "read", None, False),
    ("POST", r"leads/list", "read", "leads:read", True),
    ("GET", r"leads/[^/]+", "read", None, False),
    ("GET", r"inbox-placement-tests", "read", None, False),
    ("POST", r"inbox-placement-analytics/stats-by-test-id", "read", None, False),
    ("GET", r"block-lists-entries", "read", None, False),
    ("GET", r"audit-logs", "read", None, False),
    ("GET", r"lead-labels", "read", None, False),
    ("GET", r"webhooks", "read", None, False),
    ("GET", r"subsequences", "read", None, False),
    ("GET", r"lead-lists", "read", None, False),
    ("GET", r"background-jobs/[^/]+", "read", None, False),
    # --- writes (write key, only after guard_write said live)
    ("POST", r"emails/reply", "write", "emails:create", True),
    ("POST", r"leads/update-interest-status", "write", None, False),
    ("POST", r"leads/subsequence/move", "write", None, False),
    ("POST", r"leads", "write", None, False),
    ("PATCH", r"leads/[^/]+", "write", None, False),
    ("PATCH", r"campaigns/[^/]+", "write", None, False),
    ("POST", r"accounts/[^/]+/pause", "write", None, False),
    ("POST", r"accounts/[^/]+/resume", "write", None, False),
    ("POST", r"lead-labels", "write", None, False),
    ("POST", r"webhooks", "write", None, False),
    ("DELETE", r"webhooks/[^/]+", "write", None, False),   # the endpoint itself is unverified
    ("POST", r"subsequences", "write", None, False),
    ("POST", r"block-lists-entries", "write", None, False),
    ("POST", r"inbox-placement-tests", "write", None, False),
    ("POST", r"lead-lists", "write", None, False),
    ("POST", r"leads/move", "write", None, False),
)
# The broader scopes the reference lists as also allowing a verified one. The
# leads/list page lists leads:read alone, so it has no row here.
SCOPE_ALTERNATIVES = {
    "emails:read": ("emails:all", "all:read", "all:all"),
    "emails:create": ("emails:all", "all:create", "all:all"),
}  # type: Dict[str, Tuple[str, ...]]
_ENDPOINT_RE = [(m, re.compile(p + r"\Z"), a, s, v) for (m, p, a, s, v) in ENDPOINTS]


def endpoint_info(method: str, path: str) -> Optional[Dict[str, Any]]:
    """The ENDPOINTS row for this call as a dict, or None for an endpoint this
    client does not know."""
    bare = path.split("?", 1)[0].strip("/")
    for m, rx, access, scope, verified in _ENDPOINT_RE:
        if m == method.upper() and rx.match(bare):
            return {"method": m, "pattern": rx.pattern[:-2], "access": access, "scope": scope,
                    "verified": verified}
    return None


def scope_hint(method: str, path: str) -> str:
    """One sentence naming the scope a call needs, for error messages."""
    info = endpoint_info(method, path)
    if info and info["scope"] and info["verified"]:
        alts = SCOPE_ALTERNATIVES.get(info["scope"], ())
        return "it needs scope %s%s" % (info["scope"], " (or %s)" % ", ".join(alts) if alts else "")
    if info and info["access"] == "write":
        return ("this is a write endpoint, which a read-only key can never call; writes go through the "
                "guarded write path with INSTANTLY_API_KEY")
    return ("the scope this endpoint needs is UNVERIFIED (Instantly's reference lists none); all:read "
            "is expected to cover every read (unverified), and some endpoints accept only all:* scopes")


class InstantlyError(Exception):
    pass


class InstantlyScopeError(InstantlyError):
    """A read made with the read-only key was refused for want of a scope."""


def default_client(**kwargs) -> "Instantly":
    """The one place a job builds its Instantly client.

    Six jobs used to write ``Instantly()`` inline, which meant six places to
    patch to run the fleet offline and six places for a future default (a
    timeout, a base URL, a recorded transport) to disagree. A caller that has
    been handed a client still uses that one; this is only for the case where a
    job has to make its own.

    Because every job imports it *inside* the function that needs it, replacing
    ``shared.instantly.default_client`` replaces it for the whole process,
    which is how ``shared.offline.offline_client_factory`` drives a rehearsal.
    """
    return Instantly(**kwargs)


def interest_status_codes() -> Dict[int, str]:
    """{1: 'interested', ..., -4: 'no_show'} from config/ids.json."""
    raw = settings.IDS.get("instantly", {}).get("interest_status_codes") or {}
    out = {}  # type: Dict[int, str]
    for key, name in raw.items():
        try:
            out[int(key)] = name
        except (TypeError, ValueError):
            continue
    return out


class CursorWalk(object):
    """An iterator over a paged Instantly read that says whether it finished.

    Iterates exactly like the generator it replaced, so every existing
    ``for row in client.iterate(...)`` and ``list(client.iterate(...))`` keeps
    working. What it adds is the one fact those callers could not get:

        walk = client.iterate("leads/list", body={...}, max_pages=10)
        rows = list(walk)
        if walk.truncated:
            ...            # PARTIAL: do not apply this as if it were the whole set

    ``truncated`` and ``complete`` are only meaningful once the walk has been
    consumed; both are False on a walk nobody iterated.
    """

    def __init__(self):
        self._gen = None
        self.truncated = False
        self.complete = False
        self.pages = 0

    def _bind(self, gen) -> None:
        self._gen = gen

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._gen)

    next = __next__  # Python 2 style alias, harmless and occasionally handy

    def __repr__(self):
        return "<CursorWalk pages=%s complete=%s truncated=%s>" % (self.pages, self.complete, self.truncated)


class Instantly(object):
    def __init__(
        self,
        api_key: Optional[str] = None,
        transport: Optional[httpx.BaseTransport] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
        read_api_key: Optional[str] = None,
        write_api_key: Optional[str] = None,
    ):
        """``api_key`` (tests, replay) is used for reads AND writes, as before.
        ``read_api_key`` / ``write_api_key`` set one side each. With none of
        them the keys come from the environment through shared.keys: reads use
        INSTANTLY_API_KEY_READ, falling back to INSTANTLY_API_KEY; writes use
        INSTANTLY_API_KEY only. A client with a read key and no write key is
        valid (an agent session); its live writes raise."""
        if read_api_key:
            self._read_key, self._read_key_name = read_api_key, keys.read_name(SYSTEM)
        elif api_key:
            self._read_key, self._read_key_name = api_key, "api_key argument"
        else:
            self._read_key, self._read_key_name = keys.read_key_and_name(SYSTEM)
        self._write_key = write_api_key or api_key or keys.write_key(SYSTEM)
        if not (self._read_key or self._write_key):
            raise InstantlyError(
                "no Instantly key: set %s (read-only, repo .env) or %s (write-capable, ~/.advero/live.env "
                "and the Modal secret); see runbooks/read_only_keys.md"
                % (keys.read_name(SYSTEM), keys.main_name(SYSTEM)))
        # Kept for callers that read .api_key: the key reads are sent with.
        self.api_key = self._read_key or self._write_key
        self._ctx = threading.local()
        self.base_url = base_url.rstrip("/")
        self._sleep = sleep
        # No Authorization default: each request carries the key its access
        # needs (_auth_header), so a read can never go out with the write key
        # once a read key exists.
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "advero-shared/1.0",
            },
            timeout=timeout,
            transport=transport,
        )

    # ----------------------------------------------------------------- keys
    def _writing(self) -> bool:
        """True only inside _write's call, after guard_write said live."""
        return bool(getattr(self._ctx, "writing", False))

    def _auth_header(self) -> Dict[str, str]:
        if self._writing():
            key = self._write_key
            if not key:
                raise InstantlyError(
                    "%s is not set in this process, so no write can be sent. The write-capable key lives "
                    "in ~/.advero/live.env and the Modal secret, never the repo .env "
                    "(runbooks/read_only_keys.md)." % keys.main_name(SYSTEM))
        else:
            key = self._read_key or self._write_key
        return {"Authorization": "Bearer %s" % key}

    def _read_only_key_in_use(self) -> bool:
        return (not self._writing()) and bool(self._read_key) and keys.is_read_only_name(self._read_key_name)

    def _refused_for_scope(self, method: str, path: str, resp: httpx.Response) -> Optional[InstantlyScopeError]:
        """A 403 (or a 401 whose body says scope) on a call made with the
        read-only key: an InstantlyScopeError naming the scope needed."""
        if not self._read_only_key_in_use():
            return None
        if resp.status_code != 403 and not (resp.status_code == 401 and "scope" in resp.text.lower()):
            return None
        return InstantlyScopeError(
            "Instantly %s %s -> HTTP %s with the read-only key %s: %s. Recreate the read key with that "
            "scope (runbooks/read_only_keys.md). Response: %s"
            % (method, path, resp.status_code, self._read_key_name, scope_hint(method, path), resp.text[:200]))

    # ------------------------------------------------------------ transport
    @staticmethod
    def _is_read(method: str, path: str) -> bool:
        """Only reads may be retried (see RETRY_STATUSES)."""
        if method.upper() == "GET":
            return True
        return method.upper() == "POST" and path.strip("/") in READ_POST_PATHS

    def _backoff(self, resp_headers, attempt: int) -> float:
        retry_after = resp_headers.get("Retry-After") if resp_headers is not None else None
        try:
            delay = float(retry_after) if retry_after else 2.0 ** attempt
        except (TypeError, ValueError):
            delay = 2.0 ** attempt
        return min(delay, MAX_BACKOFF_SECONDS)

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Any] = None,
        retry: Optional[bool] = None,
    ) -> Any:
        path = "/" + path.lstrip("/")
        if params:
            params = {k: v for k, v in params.items() if v is not None}
        may_retry = self._is_read(method, path) if retry is None else bool(retry)
        auth = self._auth_header()
        attempt = 0
        while True:
            try:
                resp = self._client.request(method, path, params=params or None, json=json, headers=auth)
            except httpx.TransportError as exc:
                # A write that never got an answer may still have been accepted;
                # only reads are retried.
                if may_retry and attempt < MAX_RETRIES:
                    attempt += 1
                    delay = self._backoff(None, attempt)
                    logger.warning(
                        "Instantly %s %s transport error (%s); retry %d/%d in %.1fs",
                        method, path, exc, attempt, MAX_RETRIES, delay,
                    )
                    self._sleep(delay)
                    continue
                raise InstantlyError("Instantly %s %s -> transport error: %s" % (method, path, exc))
            if resp.status_code in RETRY_STATUSES and may_retry and attempt < MAX_RETRIES:
                attempt += 1
                delay = self._backoff(resp.headers, attempt)
                logger.warning(
                    "Instantly %s %s -> %s; retry %d/%d in %.1fs",
                    method, path, resp.status_code, attempt, MAX_RETRIES, delay,
                )
                self._sleep(delay)
                continue
            if resp.status_code in RETRY_STATUSES and not may_retry:
                logger.warning(
                    "Instantly %s %s -> %s on a write; NOT retried (no idempotency key, "
                    "the request may already have been accepted)", method, path, resp.status_code,
                )
            scope_error = self._refused_for_scope(method, path, resp)
            if scope_error is not None:
                raise scope_error
            if resp.status_code >= 400:
                err = InstantlyError(
                    "Instantly %s %s -> HTTP %s: %s" % (method, path, resp.status_code, resp.text[:400])
                )
                # Callers that must tell a 409 (a leads/move job already
                # running) from any other refusal read this, not the text.
                err.status_code = resp.status_code
                raise err
            if not resp.content:
                return {}
            try:
                return resp.json()
            except ValueError:
                return {"raw": resp.text}

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return self._request("GET", path, params=params)

    def _post(self, path: str, body: Optional[Any] = None) -> Any:
        return self._request("POST", path, json=body if body is not None else {})

    def _patch(self, path: str, body: Optional[Any] = None) -> Any:
        return self._request("PATCH", path, json=body if body is not None else {})

    def iterate(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
        max_pages: int = 200,
    ) -> "CursorWalk":
        """Follow ``next_starting_after`` cursors. GET with params, or POST with
        body when ``body`` is given (leads/list is a POST).

        Returns a :class:`CursorWalk`, which iterates exactly like the old
        generator (``for row in client.iterate(...)``, ``list(...)``) but also
        answers **whether the walk finished**. Without that, a caller could not
        tell a complete pull from one that stopped at ``max_pages``:
        pipeline_sync pulls leads with max_pages=10 per filter and would have
        silently dropped everything past the cap, then applied the result as if
        it were the whole set. Read ``.truncated`` after the loop.
        """
        walk = CursorWalk()
        walk._bind(self._iterate(path, params, body, max_pages, walk))
        return walk

    def _iterate(
        self,
        path: str,
        params: Optional[Dict[str, Any]],
        body: Optional[Dict[str, Any]],
        max_pages: int,
        walk: "CursorWalk",
    ) -> Iterator[Dict[str, Any]]:
        params = dict(params or {})
        body = dict(body) if body is not None else None
        pages = 0
        while pages < max_pages:
            if body is not None:
                page = self._post(path, body)
            else:
                page = self._get(path, params)
            # Some v2 endpoints (GET /webhooks, campaigns/analytics) answer with
            # a bare JSON array; page.get() would raise AttributeError on those.
            if isinstance(page, dict):
                items = page.get("items", [])
                cursor = page.get("next_starting_after")
            elif isinstance(page, list):
                items = page
                cursor = None
            else:
                items = []
                cursor = None
            for item in items:
                yield item
            # Stop only when the cursor is gone. An empty page that still
            # carries a cursor happens whenever a filter excludes everything on
            # that page; stopping there truncates the walk silently.
            if not cursor:
                walk.complete = True
                return
            if body is not None:
                body["starting_after"] = cursor
            else:
                params["starting_after"] = cursor
            pages += 1
            walk.pages = pages
        # Fell out of the loop with a cursor still open: this pull is PARTIAL.
        walk.truncated = True
        logger.warning("iterate(%s) stopped at max_pages=%s with the cursor still open; "
                       "the result is partial", path, max_pages)

    # ---------------------------------------------------------------- reads
    def list_campaigns(self, limit: int = 100, starting_after: Optional[str] = None) -> Dict[str, Any]:
        return self._get("campaigns", {"limit": limit, "starting_after": starting_after})

    def get_campaign(self, id: str) -> Dict[str, Any]:
        return self._get("campaigns/%s" % id)

    def list_accounts(self, limit: int = 100, starting_after: Optional[str] = None) -> Dict[str, Any]:
        return self._get("accounts", {"limit": limit, "starting_after": starting_after})

    def list_emails(
        self,
        email_type: str = "received",
        campaign_id: Optional[str] = None,
        limit: int = 100,
        starting_after: Optional[str] = None,
        eaccount: Optional[str] = None,
        **extra
    ) -> Dict[str, Any]:
        params = {
            "email_type": email_type,
            "campaign_id": campaign_id,
            "limit": limit,
            "starting_after": starting_after,
            "eaccount": eaccount,
        }
        params.update(extra)
        return self._get("emails", params)

    def get_email(self, id: str) -> Dict[str, Any]:
        return self._get("emails/%s" % id)

    def list_leads(
        self,
        filter: Optional[str] = None,
        campaign: Optional[str] = None,
        limit: int = 100,
        starting_after: Optional[str] = None,
        contacts: Optional[List[str]] = None,
        **extra
    ) -> Dict[str, Any]:
        body = {"limit": limit}  # type: Dict[str, Any]
        if filter:
            body["filter"] = filter
        if campaign:
            body["campaign"] = campaign
        if starting_after:
            body["starting_after"] = starting_after
        if contacts:
            body["contacts"] = contacts
        body.update(extra)
        return self._post("leads/list", body)

    def get_lead(self, id: str) -> Dict[str, Any]:
        return self._get("leads/%s" % id)

    def campaign_analytics(
        self,
        ids: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Any:
        params = {"start_date": start_date, "end_date": end_date}  # type: Dict[str, Any]
        if ids:
            params["ids"] = ids if len(ids) > 1 else None
            if len(ids) == 1:
                params["id"] = ids[0]
        return self._get("campaigns/analytics", params)

    def daily_campaign_analytics(self, campaign_id: str, start_date: str, end_date: str) -> Any:
        return self._get(
            "campaigns/analytics/daily",
            {"campaign_id": campaign_id, "start_date": start_date, "end_date": end_date},
        )

    def warmup_analytics(self, emails: List[str]) -> Dict[str, Any]:
        return self._post("accounts/warmup-analytics", {"emails": list(emails)})

    def daily_account_analytics(
        self,
        emails: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Any:
        """``emails`` is required by this workspace: without a filter the
        endpoint answers HTTP 413 ("Analytics request is too large"), and a
        short date range does not help (verified read-only 2026-09-21). Left
        empty it defaults to config/ids.json instantly.active_inboxes."""
        if not emails:
            emails = list(settings.IDS.get("instantly", {}).get("active_inboxes") or [])
            if emails:
                logger.warning(
                    "daily_account_analytics called with no emails filter; defaulting to the "
                    "%d active inboxes from ids.json (the workspace answers 413 without one)",
                    len(emails),
                )
        if not emails:
            raise InstantlyError(
                "daily_account_analytics needs an emails filter: this workspace answers HTTP 413 "
                "without one, even for a two-day range. Pass emails=[...] or populate "
                "config/ids.json instantly.active_inboxes."
            )
        params = {"start_date": start_date, "end_date": end_date, "emails": list(emails)}  # type: Dict[str, Any]
        return self._get("accounts/analytics/daily", params)

    def campaign_step_analytics(
        self,
        campaign_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Any:
        """GET /campaigns/analytics/steps.

        Verified read-only 2026-09-22: answers a LIST of
        ``{step, variant, sent, opened, unique_opened, replies, unique_replies,
        replies_automatic, unique_replies_automatic, clicks, unique_clicks}``
        with ``step`` and ``variant`` as zero-based **strings**, and a leading
        totals row carrying ``step: null`` (a real JSON null on five campaigns
        and the literal string ``"null"`` on recruiting_reactivation). Callers
        drop that row; ``services.experiments.analytics.is_totals_row`` handles
        both shapes.
        """
        return self._get(
            "campaigns/analytics/steps",
            {"campaign_id": campaign_id, "start_date": start_date, "end_date": end_date},
        )

    def test_vitals(self, emails: List[str]) -> Dict[str, Any]:
        """POST /accounts/test/vitals - a POST that only reads (see READ_POST_PATHS).

        Verified live 2026-09-22. Answers ``{status, success_list[],
        failure_list[]}`` grouped **by domain**, not by account: three inboxes
        on one domain produce one row carrying ``domain, mx, spf, dkim, dmarc,
        allPass``. So a failure is a DNS fault for every inbox on that domain
        and pausing one of them fixes nothing.
        """
        return self._post("accounts/test/vitals", {"accounts": list(emails)})

    def inbox_placement_list(self, limit: int = 100, starting_after: Optional[str] = None) -> Any:
        """GET /inbox-placement-tests. Empty on this workspace (no test has ever run)."""
        return self._get("inbox-placement-tests",
                         {"limit": limit, "starting_after": starting_after})

    def inbox_placement_stats_by_test(self, test_ids: List[str]) -> Any:
        """POST /inbox-placement-analytics/stats-by-test-id - a POST that only
        reads. Inbox / spam / missing counts per recipient ESP for each test."""
        return self._post("inbox-placement-analytics/stats-by-test-id",
                          {"test_ids": list(test_ids)})

    def blocklist_list(self, limit: int = 100, starting_after: Optional[str] = None) -> Any:
        """GET /block-lists-entries. Verified live 2026-09-22: answers
        ``{"items": [{id, timestamp_created, organization_id, bl_value,
        is_domain}], "next_starting_after": ...}``. ``is_domain`` is the flag
        that says whether ``bl_value`` is an address or a whole domain, and the
        suppression builder depends on it. Use ``iterate("block-lists-entries")``
        for the whole list; this is the single-page read."""
        return self._get("block-lists-entries", {"limit": limit, "starting_after": starting_after})

    def audit_logs_list(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
    ) -> Any:
        """GET /audit-logs. A pure read, so it takes the retry path. This is
        what the Friday retro's "system changes" section wants; without it the
        section degrades to the git log alone and a Claude session has to stage
        the entries by hand through the Instantly MCP."""
        return self._get("audit-logs",
                         {"start_date": start_date, "end_date": end_date, "limit": limit})

    def lead_labels_list(self, limit: int = 100) -> Dict[str, Any]:
        return self._get("lead-labels", {"limit": limit})

    def webhooks_list(self) -> Any:
        return self._get("webhooks")

    def subsequences_list(self, parent_campaign: str, limit: int = 100) -> Dict[str, Any]:
        return self._get("subsequences", {"parent_campaign": parent_campaign, "limit": limit})

    def list_lead_lists(self, search: Optional[str] = None, limit: int = 100,
                        starting_after: Optional[str] = None) -> Dict[str, Any]:
        """GET /lead-lists: ``{"items": [{id, organization_id, name,
        timestamp_created, has_enrichment_task, owned_by}], "next_starting_after"}``
        (developer.instantly.ai, read 2026-09-25). ``search`` is a substring
        match, so callers compare ``name`` exactly themselves."""
        return self._get("lead-lists", {"search": search, "limit": limit,
                                        "starting_after": starting_after})

    def get_background_job(self, job_id: str) -> Dict[str, Any]:
        """GET /background-jobs/{id}: ``{id, workspace_id, user_id, type,
        entity_id, entity_type, data, progress (0-100), status, created_at,
        updated_at}``; ``status`` is one of pending, in-progress, success,
        failed, draining, paused, cancelled (developer.instantly.ai, read
        2026-09-25; not yet seen live)."""
        return self._get("background-jobs/%s" % quote(str(job_id), safe=""))

    # --------------------------------------------------------------- writes
    def _write(self, action: str, payload: Dict[str, Any], do: Callable[[], Any], details: Optional[Dict[str, Any]] = None) -> Any:
        guard = settings.guard_write("instantly", action, payload)
        if guard.get("shadow"):
            return guard
        row = {"payload": payload}  # type: Dict[str, Any]
        if details:
            row.update(details)
        # guard_write() has already written the live_write_intent row (settings
        # logs it BEFORE the call, so a write that dies at the transport or
        # gateway still leaves something to reconcile). Here we only record how
        # it ended, through settings.record_live_write_result as its docstring
        # asks (one live_write_ok / live_write_failed row, redacted).
        # Only this block sends the write-capable key (_auth_header).
        self._ctx.writing = True
        try:
            result = do()
        except Exception as exc:  # noqa: BLE001 - re-raised below
            settings.record_live_write_result(SYSTEM, action, False, dict(row, error=str(exc)[:400]))
            raise
        finally:
            self._ctx.writing = False
        settings.record_live_write_result(SYSTEM, action, True, row)
        return result

    def reply_to_email(
        self,
        reply_to_uuid: str,
        eaccount: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        to: Optional[str] = None,
        skip_validation: bool = False,
    ) -> Any:
        """``to`` is the expected recipient and is REQUIRED.

        Instantly validates it against the thread before sending, which is the
        only server-side protection against a stale or crossed
        ``reply_to_uuid`` delivering Lorenzo's reply to a different lead. It is
        a keyword argument for backwards compatibility, but omitting it raises
        InstantlyError; ``skip_validation=True`` is the explicit, deliberate
        opt-out and should stay off.
        """
        if not to and not skip_validation:
            raise InstantlyError(
                "reply_to_email needs to=<lead email>: Instantly validates the recipient against "
                "the thread before sending, and without it a stale reply_to_uuid delivers this "
                "reply to whoever owns that thread. Pass to=..., or skip_validation=True to "
                "deliberately turn the check off."
            )
        body = {
            "reply_to_uuid": reply_to_uuid,
            "eaccount": eaccount,
            "subject": subject,
            "body": {"text": body_text, "html": body_html if body_html is not None else _text_to_html(body_text)},
        }
        if to:
            body["to"] = to
        if skip_validation:
            body["skip_validation"] = True
        return self._write("reply_to_email", body, lambda: self._post("emails/reply", body))

    def update_interest_status(self, lead_email: str, campaign_id: str, interest_value: int) -> Any:
        """``interest_value`` must be one of the codes in config/ids.json
        (1 interested, 2 meeting_booked, 3 meeting_completed, 4 won_closed,
        0 out_of_office, -1 not_interested, -2 wrong_person, -3 lost,
        -4 no_show). A typo here silently corrupts the GHL mirror (S8)."""
        value = int(interest_value)
        allowed = interest_status_codes()
        if allowed and value not in allowed:
            raise InstantlyError(
                "update_interest_status: %r is not an Instantly interest code. Allowed: %s"
                % (interest_value, ", ".join("%s=%s" % (k, allowed[k]) for k in sorted(allowed)))
            )
        body = {"lead_email": lead_email, "campaign_id": campaign_id, "interest_value": value}
        return self._write(
            "update_interest_status", body, lambda: self._post("leads/update-interest-status", body)
        )

    def update_lead(self, id: str, payload: Dict[str, Any]) -> Any:
        record = {"id": id, "payload": payload}
        return self._write("update_lead", record, lambda: self._patch("leads/%s" % id, payload))

    def update_campaign(self, id: str, payload: Dict[str, Any]) -> Any:
        record = {"id": id, "payload": payload}
        return self._write("update_campaign", record, lambda: self._patch("campaigns/%s" % id, payload))

    def pause_account(self, email: str) -> Any:
        """POST /accounts/{email}/pause: the email is URL-encoded into the path
        and the request carries NO body (config/instantly_api_contract.md).
        ``_post`` always sent ``{}`` and a raw ``@`` in the path."""
        path = "accounts/%s/pause" % quote(email, safe="")
        return self._write("pause_account", {"email": email}, lambda: self._send_no_body("POST", path))

    def _send_no_body(self, method: str, path: str) -> Any:
        """A write with no request body and no Content-Type header (a JSON
        content type with an empty body is itself a malformed request). Never
        retried, like every other write."""
        request = self._client.build_request(method, "/" + path.lstrip("/"), headers=self._auth_header())
        request.headers.pop("Content-Type", None)
        try:
            resp = self._client.send(request)
        except httpx.TransportError as exc:
            raise InstantlyError("Instantly %s /%s -> transport error: %s" % (method, path.lstrip("/"), exc))
        scope_error = self._refused_for_scope(method, "/" + path.lstrip("/"), resp)
        if scope_error is not None:
            raise scope_error
        if resp.status_code >= 400:
            raise InstantlyError(
                "Instantly %s /%s -> HTTP %s: %s" % (method, path.lstrip("/"), resp.status_code, resp.text[:400]))
        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError:
            return {"raw": resp.text}

    def resume_account(self, email: str) -> Any:
        """POST /accounts/{email}/resume: the undo of pause, same shape (URL-encoded
        path parameter, no body)."""
        path = "accounts/%s/resume" % quote(email, safe="")
        return self._write("resume_account", {"email": email}, lambda: self._send_no_body("POST", path))

    def lead_labels_create(
        self,
        label: str,
        interest_status_label: str,
        description: str = "",
        use_with_ai: bool = True,
    ) -> Any:
        body = {
            "label": label,
            "interest_status_label": interest_status_label,
            "description": description,
            "use_with_ai": bool(use_with_ai),
        }
        return self._write("lead_labels_create", body, lambda: self._post("lead-labels", body))

    def webhooks_create(self, payload: Dict[str, Any]) -> Any:
        """POST /webhooks. The target field is ``target_hook_url``.

        ``target_url`` is accepted by the API (unknown keys are not rejected)
        and creates a webhook with **no target**: every reply is then silently
        never delivered and nothing anywhere reports a failure. So a payload
        carrying the wrong key is corrected here, loudly, rather than sent."""
        payload = dict(payload or {})
        for wrong in ("target_url", "targetUrl", "targetHookUrl", "url"):
            value = payload.pop(wrong, None)
            if value and not payload.get("target_hook_url"):
                logger.warning("webhooks_create: %r is not the target field; sending it as target_hook_url", wrong)
                payload["target_hook_url"] = value
        target = payload.get("target_hook_url")
        if not isinstance(target, str) or not target.startswith(("http://", "https://")):
            raise InstantlyError(
                "webhooks_create needs target_hook_url matching ^https?:// (got %r). A webhook with no "
                "target is accepted by the API and then delivers nothing." % (target,))
        return self._write("webhooks_create", payload, lambda: self._post("webhooks", payload))

    def webhooks_delete(self, webhook_id: str) -> Any:
        """DELETE /webhooks/{id}. **UNVERIFIED**: not in the verified API contract
        and never exercised against Instantly. changesets/instantly_webhooks.py
        does not call it until DELETE_WEBHOOK_VERIFIED is set after the live
        rehearsal. Sent with no body and no Content-Type.

        This method does no matching of its own: it deletes exactly the id it
        is given. Which webhooks are "ours" is decided by the caller,
        ``changesets.instantly_webhooks.ours()``: an id recorded in the
        change-set's ledger at create time AND a name that still starts with
        NAME_PREFIX. The target URL plays no part in that rule (GOL-18: an older
        rule matched our URL OR our name)."""
        payload = {"webhook_id": webhook_id}
        return self._write("webhooks_delete", payload,
                           lambda: self._send_no_body("DELETE", "webhooks/%s" % quote(str(webhook_id), safe="")))

    def subsequences_create(self, payload: Dict[str, Any]) -> Any:
        return self._write("subsequences_create", payload, lambda: self._post("subsequences", payload))

    def blocklist_create(self, value: str, type: str = "email") -> Any:
        """POST /block-lists-entries takes the single field ``bl_value`` (an
        email or a domain; the value itself decides which). ``type`` is a note
        for the operator, never part of the request: the guarded payload has to
        be exactly what a live run would send, or the shadow log describes a
        request that cannot be replayed."""
        body = {"bl_value": value}
        return self._write(
            "blocklist_create", body,
            lambda: self._post("block-lists-entries", body),
            details={"type_hint": type},
        )

    def create_lead(
        self,
        campaign: str,
        email: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        company_name: Optional[str] = None,
        website: Optional[str] = None,
        personalization: Optional[str] = None,
        custom_variables: Optional[Dict[str, Any]] = None,
        skip_if_in_workspace: bool = True,
        verify_leads_on_import: bool = True,
    ) -> Any:
        """POST /leads - **one lead per call**.

        A 3,300-lead upload is 3,300 guarded calls and has to respect the
        workspace budget (100 req/s, 6,000 req/min shared across every
        endpoint). Both defaults are deliberately protective:
        ``skip_if_in_workspace`` stops the list factory re-importing a lead who
        is already being mailed, and ``verify_leads_on_import`` lets Instantly
        drop an address the local verifier passed.

        Before this existed, ``services/list_factory/stage_out.py`` was the one
        place in the codebase reaching past the client to
        ``settings.guard_write`` directly, so nothing owned the request schema.
        """
        email = (email or "").strip()
        if not email or "@" not in email:
            raise InstantlyError("create_lead needs a real email address (got %r)" % (email,))
        if not campaign:
            raise InstantlyError(
                "create_lead needs a campaign id: a lead created without one lands in the "
                "workspace with nothing sending to it and is invisible to every campaign report.")
        body = {
            "campaign": campaign,
            "email": email,
            "skip_if_in_workspace": bool(skip_if_in_workspace),
            "verify_leads_on_import": bool(verify_leads_on_import),
        }  # type: Dict[str, Any]
        for key, value in (
            ("first_name", first_name),
            ("last_name", last_name),
            ("company_name", company_name),
            ("website", website),
            ("personalization", personalization),
        ):
            if value:
                body[key] = value
        if custom_variables:
            body["custom_variables"] = dict(custom_variables)
        return self._write("create_lead", body, lambda: self._post("leads", body))

    def inbox_placement_create(self, payload: Dict[str, Any]) -> Any:
        """POST /inbox-placement-tests. **Spends Instantly credits**, which is
        why every placement test this repo produces is staged as a change-set
        and never fired by the job itself."""
        payload = dict(payload or {})
        return self._write("inbox_placement_create", payload,
                           lambda: self._post("inbox-placement-tests", payload))

    def create_lead_list(self, name: str) -> Any:
        """POST /lead-lists {"name"}. The schema is ``additionalProperties:
        false`` with ``name`` the only required field; the answer is the
        LeadList object (``id``, ``name``, ...)."""
        name = (name or "").strip()
        if not name:
            raise InstantlyError("create_lead_list needs a name")
        body = {"name": name}
        return self._write("create_lead_list", body, lambda: self._post("lead-lists", body))

    def move_leads(self, lead_ids: List[str], campaign: Optional[str] = None,
                   list_id: Optional[str] = None, to_campaign_id: Optional[str] = None,
                   to_list_id: Optional[str] = None, copy_leads: bool = False) -> Any:
        """POST /leads/move: up to 100 lead ids from ONE source (``campaign``
        or ``list_id``, which the API requires alongside ``ids``) to ONE
        destination (``to_campaign_id`` or ``to_list_id``).

        The answer is a BackgroundJob (``id``, ``status``, ``progress``); poll
        get_background_job(id). A second move while one runs has been seen to
        answer 409 (InstantlyError.status_code). Never retried here: a
        rejected call can still have moved some leads, so the caller re-reads
        before trying again. PATCHing a lead's ``campaign`` does NOT move it
        (it silently no-ops), which is why this endpoint exists here."""
        ids = [str(i) for i in (lead_ids or []) if i]
        if not ids:
            raise InstantlyError("move_leads needs at least one lead id")
        if len(ids) > 100:
            raise InstantlyError("move_leads takes at most 100 ids per call (got %d)" % len(ids))
        if bool(campaign) == bool(list_id):
            raise InstantlyError("move_leads needs exactly one source: campaign or list_id")
        if bool(to_campaign_id) == bool(to_list_id):
            raise InstantlyError("move_leads needs exactly one destination: to_campaign_id or to_list_id")
        body = {"ids": ids, "copy_leads": bool(copy_leads)}  # type: Dict[str, Any]
        if campaign:
            body["campaign"] = campaign
        if list_id:
            body["list_id"] = list_id
        if to_campaign_id:
            body["to_campaign_id"] = to_campaign_id
        if to_list_id:
            body["to_list_id"] = to_list_id
        return self._write("move_leads", body, lambda: self._post("leads/move", body))

    def move_to_subsequence(self, lead_id: str, subsequence_id: str) -> Any:
        """Instantly moves ONE lead per call: POST /leads/subsequence/move
        {"id", "subsequence_id"}. A list-of-ids payload is rejected; use
        move_leads_to_subsequence() for several leads."""
        body = {"id": str(lead_id), "subsequence_id": subsequence_id}
        return self._write("move_to_subsequence", body, lambda: self._post("leads/subsequence/move", body))

    def move_leads_to_subsequence(self, lead_ids: List[str], subsequence_id: str) -> List[Any]:
        """One guarded call per lead; returns one result per id, in order."""
        return [self.move_to_subsequence(lead_id, subsequence_id) for lead_id in lead_ids]

    def close(self) -> None:
        self._client.close()


def _text_to_html(text: str) -> str:
    import html

    return "<div>%s</div>" % html.escape(text).replace("\n", "<br>")
