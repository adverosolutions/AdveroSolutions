"""GoHighLevel (LeadConnector) API client, httpx-based and dependency-injected.

* No read token (GHL_PRIVATE_INTEGRATION_TOKEN_READ and
  GHL_PRIVATE_INTEGRATION_TOKEN both unset): every READ logs
  ``ghl_token_missing`` and returns None. Every WRITE still calls
  ``guard_write('ghl', ...)`` first so the shadow log records the intent, then
  returns the guard record in shadow. In LIVE mode a write with no WRITE token
  (GHL_PRIVATE_INTEGRATION_TOKEN unset, whatever the _READ token holds)
  writes a ``skipped_no_token`` Job_Log row and raises GHLError: a dropped
  write must never look like a successful one, or a lead gets marked Meeting
  Booked in Instantly with no calendar event behind it.
* Writes go through guard_write() and perform HTTP only when
  MODE=live and ALLOW_LIVE_WRITES=1.
* Ids default to config/ids.json (location, pipeline, stages, calendar, user).
* Keys (decision R2(a), shared/keys.py, runbooks/read_only_keys.md): every
  ``_read`` sends ``GHL_PRIVATE_INTEGRATION_TOKEN_READ``, falling back to
  ``GHL_PRIVATE_INTEGRATION_TOKEN`` while no read token exists; only the body
  of ``_write``, after guard_write said live, sends
  ``GHL_PRIVATE_INTEGRATION_TOKEN``. Read vs write is decided per method (the
  POST contacts/search is a read). A 403 on a read made with the read-only
  token raises :class:`GHLScopeError` naming the scope (``READ_SCOPES``).
"""
import logging
import threading
from typing import Any, Callable, Dict, List, Optional

import httpx

from shared import keys, settings

logger = logging.getLogger("shared.ghl")

DEFAULT_BASE_URL = "https://services.leadconnectorhq.com"
API_VERSION = "2021-07-28"
SYSTEM = "ghl"
TOKEN_ENV = keys.main_name(SYSTEM)           # GHL_PRIVATE_INTEGRATION_TOKEN (write-capable)
READ_TOKEN_ENV = keys.read_name(SYSTEM)      # GHL_PRIVATE_INTEGRATION_TOKEN_READ

# The readonly Private Integration scope each read method needs. From the GHL
# scope list checked on 2026-09-22, except where marked: conversations.readonly
# was not part of that check and is UNVERIFIED.
READ_SCOPES = {
    "get_contact": "contacts.readonly",
    "search_contacts": "contacts.readonly",
    "search_opportunities": "opportunities.readonly",
    "get_opportunity": "opportunities.readonly",
    "get_free_slots": "calendars.readonly",
    "get_appointment": "calendars/events.readonly",
    "get_calendar_events": "calendars/events.readonly",
    "search_conversations": "conversations.readonly",
}  # type: Dict[str, str]
UNVERIFIED_SCOPES = frozenset(("conversations.readonly",))

# Whether a LIVE contact with neither an email nor a phone (an Upwork client:
# the platform gives no contact details) may be written. While False, a live
# upsert_contact with email=None and no phone is refused with
# ``ghl_contact_needs_identity`` before guard_write and before any request
# (whatever the call shape, legacy callers included). Shadow still records the
# would-do row. Flip it to True only when BOTH hold:
#   1. Lorenzo has tested against the GHL sandbox that GHL accepts such a
#      contact; and
#   2. the separate Upwork pipeline exists and is configured in config/ids.json
#      ghl.pipelines.upwork (id and all six stage ids). An email-less
#      opportunity in the Sales pipeline blocks pipeline_sync's nightly reverse
#      check (opportunities_without_email); services/upwork_followup/ghl_sync.py
#      refuses to write while that block is unconfigured, and
#      tests/test_ghl_sync.py has a tripwire that it never sends a Sales id.
CONTACT_WITHOUT_EMAIL_VERIFIED = False
CONTACT_NEEDS_IDENTITY = "ghl_contact_needs_identity"


class GHLError(Exception):
    pass


class GHLScopeError(GHLError):
    """A read made with the read-only token was refused for want of a scope."""


class GHLContactNeedsIdentity(GHLError):
    """A live contact write with no email and no phone, refused while
    CONTACT_WITHOUT_EMAIL_VERIFIED is False."""


def _log(job: str, status: str, details: Dict[str, Any]) -> None:
    """Job_Log row that must never break the call it is describing."""
    try:
        from shared import job_log

        job_log.log_run(job, status, details)
    except Exception:  # noqa: BLE001
        logger.warning("could not write job log row %s/%s", job, status)


class GHL(object):
    def __init__(
        self,
        token: Optional[str] = None,
        location_id: Optional[str] = None,
        transport: Optional[httpx.BaseTransport] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        read_token: Optional[str] = None,
        write_token: Optional[str] = None,
    ):
        """``token`` (tests) is used for reads AND writes, as before;
        ``read_token`` / ``write_token`` set one side each. With none of them
        reads use GHL_PRIVATE_INTEGRATION_TOKEN_READ, falling back to
        GHL_PRIVATE_INTEGRATION_TOKEN, and writes use
        GHL_PRIVATE_INTEGRATION_TOKEN only. ``self.token`` is the read token."""
        if read_token:
            self.token, self._read_token_name = read_token, READ_TOKEN_ENV
        elif token:
            self.token, self._read_token_name = token, "token argument"
        else:
            self.token, self._read_token_name = keys.read_key_and_name(SYSTEM)
        self.write_token = write_token or token or keys.write_key(SYSTEM)
        self._ctx = threading.local()
        self.location_id = location_id or settings.GHL_LOCATION_ID
        self.base_url = base_url.rstrip("/")
        ids = settings.IDS.get("ghl", {})
        self.user_id = ids.get("user_id")
        self.pipeline_id = ids.get("pipelines", {}).get("sales", {}).get("id")
        self.stages = settings.GHL_STAGES
        self.calendar_id = settings.GHL_CALENDAR_ID
        # No Authorization default: each request carries the token its access
        # needs (_auth_header).
        headers = {
            "Version": API_VERSION,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self._client = httpx.Client(base_url=self.base_url, headers=headers, timeout=timeout, transport=transport)

    @property
    def has_token(self) -> bool:
        """A token reads can use (the read token, or the main one as fallback)."""
        return bool(self.token)

    def _token_missing(self, what: str) -> None:
        logger.warning("ghl_token_missing: %s skipped (set %s, or %s)", what, READ_TOKEN_ENV, TOKEN_ENV)
        return None

    def _writing(self) -> bool:
        return bool(getattr(self._ctx, "writing", False))

    def _auth_header(self) -> Dict[str, str]:
        token = self.write_token if self._writing() else self.token
        return {"Authorization": "Bearer %s" % token} if token else {}

    def _scope_error(self, what: str, method: str, path: str, resp: httpx.Response) -> Optional[GHLScopeError]:
        """A 403 (or a 401 whose body says scope) on a read made with the
        read-only token: a GHLScopeError naming the readonly scope needed."""
        if self._writing() or not keys.is_read_only_name(self._read_token_name):
            return None
        if resp.status_code != 403 and not (resp.status_code == 401 and "scope" in resp.text.lower()):
            return None
        scope = READ_SCOPES.get(what)
        if scope and scope in UNVERIFIED_SCOPES:
            need = "it most likely needs scope %s (UNVERIFIED: not in the 2026-09-22 scope check)" % scope
        elif scope:
            need = "it needs scope %s" % scope
        else:
            need = "the scope this read needs is not recorded in shared/ghl.py READ_SCOPES"
        return GHLScopeError(
            "GHL %s %s (%s) -> HTTP %s with the read-only token %s: %s. Add the scope to the read-only "
            "Private Integration (runbooks/read_only_keys.md). Response: %s"
            % (method, path, what, resp.status_code, self._read_token_name, need, resp.text[:200]))

    # ------------------------------------------------------------ transport
    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None, json: Optional[Any] = None,
                 what: Optional[str] = None) -> Any:
        path = "/" + path.lstrip("/")
        if params:
            params = {k: v for k, v in params.items() if v is not None}
        resp = self._client.request(method, path, params=params or None, json=json, headers=self._auth_header())
        scope_error = self._scope_error(what or "", method, path, resp)
        if scope_error is not None:
            raise scope_error
        if resp.status_code >= 400:
            raise GHLError("GHL %s %s -> HTTP %s: %s" % (method, path, resp.status_code, resp.text[:400]))
        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError:
            return {"raw": resp.text}

    def _read(self, what: str, method: str, path: str, params=None, json=None) -> Optional[Any]:
        if not self.token:
            return self._token_missing(what)
        return self._request(method, path, params=params, json=json, what=what)

    def _write(self, action: str, payload: Dict[str, Any], do: Callable[[], Any]) -> Optional[Any]:
        guard = settings.guard_write("ghl", action, payload)
        if guard.get("shadow"):
            return guard
        if not self.write_token:
            # Live with no write token: the write did NOT happen. Returning None here
            # is indistinguishable from a read miss, which is how a booking can
            # be reported as real with no calendar event behind it. Record the
            # dropped intent and raise.
            _log("ghl.%s" % action, "skipped_no_token", {"payload": payload})
            logger.error("ghl_token_missing: %s dropped in live mode (set %s)", action, TOKEN_ENV)
            raise GHLError(
                "ghl_token_missing: %s was not written (MODE=live with no %s; a read-only %s cannot "
                "write). The write-capable token lives in ~/.advero/live.env and the Modal secret "
                "(runbooks/read_only_keys.md)." % (action, TOKEN_ENV, READ_TOKEN_ENV)
            )
        # guard_write() already wrote the live_write_intent row before this
        # point; here we only record the outcome, through
        # settings.record_live_write_result as its docstring asks. Only this
        # block sends the write-capable token (_auth_header).
        self._ctx.writing = True
        try:
            result = do()
        except Exception as exc:  # noqa: BLE001 - re-raised below
            settings.record_live_write_result(SYSTEM, action, False, {"payload": payload, "error": str(exc)[:400]})
            raise
        finally:
            self._ctx.writing = False
        settings.record_live_write_result(SYSTEM, action, True, {"payload": payload})
        return result

    # ---------------------------------------------------------------- reads
    def get_contact(self, id: str) -> Optional[Any]:
        return self._read("get_contact", "GET", "contacts/%s" % id)

    def search_contacts(self, email: str, page_limit: int = 20) -> Optional[Any]:
        body = {
            "locationId": self.location_id,
            "pageLimit": page_limit,
            "filters": [{"field": "email", "operator": "eq", "value": email}],
        }
        return self._read("search_contacts", "POST", "contacts/search", json=body)

    def search_opportunities(
        self,
        contact_id: Optional[str] = None,
        pipeline_id: Optional[str] = None,
        stage_id: Optional[str] = None,
        limit: int = 20,
        start_after_id: Optional[str] = None,
        start_after: Optional[Any] = None,
    ) -> Optional[Any]:
        """One page of the Sales pipeline. ``start_after_id`` (with the matching
        ``start_after`` timestamp when the response carried one) continues from
        the previous page: without it pipeline_sync stops at 100 opportunities
        and refuses the whole nightly apply as ``ghl_truncated``."""
        params = {
            "location_id": self.location_id,
            "contact_id": contact_id,
            "pipeline_id": pipeline_id,
            "pipeline_stage_id": stage_id,
            "limit": limit,
        }
        if start_after_id:
            params["startAfterId"] = start_after_id
        if start_after is not None:
            params["startAfter"] = start_after
        return self._read("search_opportunities", "GET", "opportunities/search", params=params)

    def get_free_slots(
        self,
        calendar_id: Optional[str],
        start_date_ms: int,
        end_date_ms: int,
        timezone: str = "America/Chicago",
        user_id: Optional[str] = None,
    ) -> Optional[Any]:
        calendar_id = calendar_id or self.calendar_id
        params = {"startDate": int(start_date_ms), "endDate": int(end_date_ms), "timezone": timezone, "userId": user_id}
        return self._read("get_free_slots", "GET", "calendars/%s/free-slots" % calendar_id, params=params)

    def get_appointment(self, id: str) -> Optional[Any]:
        return self._read("get_appointment", "GET", "calendars/events/appointments/%s" % id)

    def get_opportunity(self, id: str) -> Optional[Any]:
        """One opportunity by id, for readers that need its CURRENT stage.

        no_show._current_stage_key() has to know where an opportunity sits
        before the recovery ladder moves it. Without this it falls back to
        search_opportunities(contact_id=...) and then to "unknown", which allows
        the move; an appointment carrying an opportunity_id but no contact_id
        could not be checked at all. pipeline_sweep._apply_after uses it for the
        same reason, so a proposal_sent / won / lost stage is never overwritten.
        """
        return self._read("get_opportunity", "GET", "opportunities/%s" % id)

    def get_calendar_events(self, calendar_id: Optional[str], start_ms: int, end_ms: int) -> Optional[Any]:
        params = {
            "locationId": self.location_id,
            "calendarId": calendar_id or self.calendar_id,
            "startTime": int(start_ms),
            "endTime": int(end_ms),
        }
        return self._read("get_calendar_events", "GET", "calendars/events", params=params)

    def search_conversations(self, contact_id: str) -> Optional[Any]:
        params = {"locationId": self.location_id, "contactId": contact_id}
        return self._read("search_conversations", "GET", "conversations/search", params=params)

    # --------------------------------------------------------------- writes
    def upsert_contact(
        self,
        email: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        company: Optional[str] = None,
        phone: Optional[str] = None,
        tags: Optional[List[str]] = None,
        custom_fields: Optional[List[Dict[str, Any]]] = None,
        name: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Optional[Any]:
        """Two call shapes.

        * **Legacy** (neither ``name`` nor ``source`` passed): the body and the
          shadow payload are exactly what they always were, ``"email": None``
          included when a caller passes None (booking.book with an empty
          lead_email does), and no new ValueError.
        * **No-email contact** (``email=None`` with ``name`` or ``source``
          passed, an Upwork client): needs a name (``name``, or a first/last
          name) plus a ``source`` or tags, else ValueError; the body carries no
          ``"email"`` key. With an email, ``name`` / ``source`` are simply added.

        Either shape: while CONTACT_WITHOUT_EMAIL_VERIFIED is False, a LIVE call
        with ``email=None`` and no phone raises GHLContactNeedsIdentity (a
        GHLError, ``ghl_contact_needs_identity``) before guard_write, so there is
        no live-write intent row and no request. For a legacy caller that is the
        same exception class a GHL rejection of ``"email": null`` would raise.
        """
        no_email_shape = email is None and (name is not None or source is not None)
        if no_email_shape:
            if not (name or first_name or last_name):
                raise ValueError("upsert_contact without an email needs a name (name, first_name or last_name)")
            if not (source or tags):
                raise ValueError("upsert_contact without an email needs a source or tags")
        if email is None and not phone and not CONTACT_WITHOUT_EMAIL_VERIFIED and settings.is_live():
            label = name or " ".join(p for p in (first_name, last_name) if p) or company or ""
            details = {"name": label, "source": source, "tags": list(tags or [])}
            # The status is a literal (== CONTACT_NEEDS_IDENTITY): the watch-report
            # status scan (changesets/tests/test_deploy_watch_report.py) reads literals only.
            _log("ghl.upsert_contact", "ghl_contact_needs_identity", details)
            logger.error("%s: live contact with no email and no phone refused (%s)", CONTACT_NEEDS_IDENTITY, label)
            raise GHLContactNeedsIdentity(
                "%s: upsert_contact refused in live mode for %r: no email and no phone, and a contact without "
                "either is not cleared for live (shared.ghl.CONTACT_WITHOUT_EMAIL_VERIFIED is False: it needs the "
                "GHL sandbox test and the separate Upwork pipeline configured first)." % (CONTACT_NEEDS_IDENTITY, label)
            )
        if no_email_shape:
            body = {"locationId": self.location_id}  # type: Dict[str, Any]
        else:
            body = {"locationId": self.location_id, "email": email}
        if name:
            body["name"] = name
        if first_name:
            body["firstName"] = first_name
        if last_name:
            body["lastName"] = last_name
        if company:
            body["companyName"] = company
        if phone:
            body["phone"] = phone
        if tags:
            body["tags"] = list(tags)
        if custom_fields:
            body["customFields"] = custom_fields
        if source:
            body["source"] = source
        return self._write("upsert_contact", body, lambda: self._request("POST", "contacts/upsert", json=body))

    def add_tags(self, contact_id: str, tags: List[str]) -> Optional[Any]:
        body = {"tags": list(tags)}
        payload = {"contact_id": contact_id, "tags": list(tags)}
        return self._write("add_tags", payload, lambda: self._request("POST", "contacts/%s/tags" % contact_id, json=body))

    def create_note(self, contact_id: str, body: str) -> Optional[Any]:
        data = {"body": body, "userId": self.user_id}
        payload = {"contact_id": contact_id, "body": body}
        return self._write("create_note", payload, lambda: self._request("POST", "contacts/%s/notes" % contact_id, json=data))

    def upsert_opportunity(
        self,
        contact_id: str,
        pipeline_id: Optional[str],
        stage_id: str,
        name: str,
        monetary_value: Optional[float] = None,
        status: str = "open",
    ) -> Optional[Any]:
        body = {
            "locationId": self.location_id,
            "contactId": contact_id,
            "pipelineId": pipeline_id or self.pipeline_id,
            "pipelineStageId": stage_id,
            "name": name,
            "status": status,
        }  # type: Dict[str, Any]
        if monetary_value is not None:
            body["monetaryValue"] = monetary_value
        return self._write("upsert_opportunity", body, lambda: self._request("POST", "opportunities/upsert", json=body))

    def update_opportunity_stage(self, opportunity_id: str, stage_id: str, status: Optional[str] = None,
                                 lost_reason: Optional[str] = None) -> Optional[Any]:
        """``lost_reason`` rides the same PUT as ``status='lost'``.

        Without it the third-no-show Lost move carries no reason, and
        pipeline_sync.desired_interest() then mirrors the lead back to Instantly
        as not_interested (-1) instead of no_show (-4), which is the code
        config/ids.json defines for exactly this case. GHL accepts the free-text
        ``lostReason``; a location that requires the id form rejects the body,
        and no_show._move_opportunity already feature-detects this kwarg.
        """
        body = {"pipelineStageId": stage_id}  # type: Dict[str, Any]
        if status:
            body["status"] = status
        if lost_reason:
            body["lostReason"] = lost_reason
        payload = dict(body, opportunity_id=opportunity_id)
        return self._write(
            "update_opportunity_stage", payload, lambda: self._request("PUT", "opportunities/%s" % opportunity_id, json=body)
        )

    def update_opportunity_value(self, opportunity_id: str, monetary_value: Any) -> Optional[Any]:
        """PUT only the monetary value. pipeline_sync feature-detects this by
        name: without it a value fix on a contact holding more than one Sales
        opportunity has to be refused, because a contact-keyed upsert would
        rewrite whichever opportunity GHL returns first."""
        body = {"monetaryValue": monetary_value}  # type: Dict[str, Any]
        payload = dict(body, opportunity_id=opportunity_id)
        return self._write(
            "update_opportunity_value", payload, lambda: self._request("PUT", "opportunities/%s" % opportunity_id, json=body)
        )

    def create_appointment(
        self,
        calendar_id: Optional[str],
        contact_id: str,
        start_iso: str,
        end_iso: str,
        title: str,
        assigned_user_id: Optional[str] = None,
        appointment_status: str = "confirmed",
        to_notify: bool = True,
    ) -> Optional[Any]:
        """``to_notify=False`` for an internal block (the cadence day-6 hold):
        GHL emails the contact a booking notice otherwise, for a call they
        never agreed to."""
        body = {
            "calendarId": calendar_id or self.calendar_id,
            "locationId": self.location_id,
            "contactId": contact_id,
            "startTime": start_iso,
            "endTime": end_iso,
            "title": title,
            "assignedUserId": assigned_user_id or self.user_id,
            "appointmentStatus": appointment_status,
            "ignoreDateRange": False,
            "toNotify": bool(to_notify),
        }
        return self._write(
            "create_appointment", body, lambda: self._request("POST", "calendars/events/appointments", json=body)
        )

    def update_appointment_status(self, appointment_id: str, status: str,
                                  to_notify: Optional[bool] = None) -> Optional[Any]:
        """``to_notify=True`` is how the invite is released to the prospect.

        booking.book() creates the appointment with ``to_notify=False`` because
        it runs at classification time, before Lorenzo has approved anything;
        approval.send_approved calls this with ``to_notify=True`` once the
        confirmation reply is actually out, so "invite on the way" is true at
        the moment the prospect reads it. Leaving it None keeps GHL's default
        and sends nothing extra, which is what every cancel path wants.
        """
        body = {"appointmentStatus": status}  # type: Dict[str, Any]
        payload = {"appointment_id": appointment_id, "status": status}
        if to_notify is not None:
            body["toNotify"] = bool(to_notify)
            payload["toNotify"] = bool(to_notify)
        return self._write(
            "update_appointment_status",
            payload,
            lambda: self._request("PUT", "calendars/events/appointments/%s" % appointment_id, json=body),
        )

    def send_message(
        self,
        contact_id: str,
        type: str = "Email",
        subject: Optional[str] = None,
        message: Optional[str] = None,
        html: Optional[str] = None,
    ) -> Optional[Any]:
        body = {"type": type, "contactId": contact_id}  # type: Dict[str, Any]
        if subject:
            body["subject"] = subject
        if message:
            body["message"] = message
        if html:
            body["html"] = html
        return self._write("send_message", body, lambda: self._request("POST", "conversations/messages", json=body))

    def create_task(self, contact_id: str, title: str, due_iso: str, body: str = "") -> Optional[Any]:
        data = {"title": title, "dueDate": due_iso, "body": body, "completed": False, "assignedTo": self.user_id}
        payload = dict(data, contact_id=contact_id)
        return self._write("create_task", payload, lambda: self._request("POST", "contacts/%s/tasks" % contact_id, json=data))

    def close(self) -> None:
        self._client.close()
