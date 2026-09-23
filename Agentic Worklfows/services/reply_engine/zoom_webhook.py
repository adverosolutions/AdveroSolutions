"""Zoom webhook receiver (Blueprint S5 detection input).

POST /webhooks/zoom
  * ``endpoint.url_validation``: answers Zoom's challenge with
    HMAC-SHA256(ZOOM_WEBHOOK_SECRET, plainToken) as ``encryptedToken``.
  * every other event: verifies ``x-zm-signature`` =
    "v0=" + HMAC-SHA256(secret, "v0:<x-zm-request-timestamp>:<raw body>") and
    rejects a timestamp older than 5 minutes; then normalises
    ``meeting.participant_joined`` / ``meeting.ended`` into the store:
      joins:<meeting_id>         -> [ {at_iso, name, email, is_host, participant_id, event} ]
      meeting_ended:<meeting_id> -> {at_iso, duration}
    and resolves meeting id -> appointment id through ``appt:<appointment_id>``
    records (written by booking.py, another brief: {zoom_meeting_id, ...}) or
    a ``zoom_meeting:<meeting_id>`` index. Absence is tolerated: the join is
    stored under the meeting id and picked up once the mapping exists.

``handle_event`` is a pure function so tests do not need FastAPI; the router
is a thin wrapper. Nothing here writes to Zoom, GHL or anywhere else.
"""
import hashlib
import hmac
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from shared import slots
from shared.settings import TZ
from shared.store import get_store

logger = logging.getLogger("reply_engine.zoom_webhook")

SECRET_ENV = "ZOOM_WEBHOOK_SECRET"
URL_VALIDATION_ENV = "ZOOM_URL_VALIDATION"
TIMESTAMP_TOLERANCE_SECONDS = 300
PLAIN_TOKEN_RE = re.compile(r"^[A-Za-z0-9_=-]+$")
MAX_PLAIN_TOKEN_LEN = 64
# a join only belongs to an appointment if it happened around it; meeting ids
# are reused (Personal Meeting ID, recurring links) and joins_by_appt survives
# reschedules of the same appointment id.
JOIN_WINDOW_BEFORE = timedelta(minutes=30)
JOIN_WINDOW_AFTER = timedelta(minutes=30)
HANDLED_EVENTS = ("meeting.participant_joined", "meeting.participant_left", "meeting.ended", "meeting.started")

# test seam: the router reads the clock through this so tests can inject one
_now_fn = lambda: datetime.now(timezone.utc)  # noqa: E731


def set_clock(fn: Optional[Callable[[], datetime]]) -> None:
    global _now_fn
    _now_fn = fn or (lambda: datetime.now(timezone.utc))


def get_secret() -> Optional[str]:
    return os.environ.get(SECRET_ENV) or None


# ------------------------------------------------------------ crypto
def challenge_response(plain_token: str, secret: str) -> Dict[str, str]:
    digest = hmac.new(secret.encode("utf-8"), plain_token.encode("utf-8"), hashlib.sha256).hexdigest()
    return {"plainToken": plain_token, "encryptedToken": digest}


def safe_plain_token(token: Any) -> bool:
    """Zoom's plainToken is a short opaque base64url string.

    ``challenge_response`` signs whatever it is handed and returns the digest
    in the clear to an unauthenticated caller, so anything that could be a
    signature message ("v0:<ts>:<body>") would make this endpoint an HMAC
    oracle for forged events. Refuse those shapes.
    """
    text = str(token or "")
    if not text or len(text) > MAX_PLAIN_TOKEN_LEN:
        return False
    return bool(PLAIN_TOKEN_RE.match(text))


def url_validation_enabled() -> bool:
    """Zoom re-validates periodically, so this is on by default; set
    ZOOM_URL_VALIDATION=off once the subscription is validated and stable."""
    return os.environ.get(URL_VALIDATION_ENV, "on").strip().lower() not in ("0", "off", "false", "no")


def expected_signature(secret: str, timestamp: str, raw_body: bytes) -> str:
    message = b"v0:" + str(timestamp).encode("utf-8") + b":" + raw_body
    return "v0=" + hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def normalise_timestamp(timestamp: Any) -> Optional[int]:
    """Zoom sends x-zm-request-timestamp in MILLISECONDS. Only the freshness
    comparison is normalised; the HMAC message keeps the raw header string."""
    try:
        ts = int(str(timestamp))
    except (ValueError, TypeError):
        return None
    if abs(ts) > 1e11:  # same heuristic as shared.slots.parse_iso
        ts = ts // 1000
    return ts


def verify_signature(secret: str, timestamp: Optional[str], signature: Optional[str], raw_body: bytes, now: datetime) -> bool:
    if not timestamp or not signature:
        return False
    ts = normalise_timestamp(timestamp)
    if ts is None:
        return False
    now_ts = int(slots.ensure_aware(now, TZ).timestamp())
    if abs(now_ts - ts) > TIMESTAMP_TOLERANCE_SECONDS:
        return False
    return hmac.compare_digest(expected_signature(secret, timestamp, raw_body), str(signature))


# ------------------------------------------------------------ normalise
def _iso(value: Any, fallback: datetime) -> str:
    if value:
        try:
            return slots.to_tz(slots.parse_iso(value), TZ).isoformat()
        except (ValueError, TypeError):
            pass
    return slots.to_tz(slots.ensure_aware(fallback, TZ), TZ).isoformat()


def normalise_join(payload: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    obj = payload.get("object", {}) or {}
    part = obj.get("participant", {}) or {}
    host_id = obj.get("host_id")
    is_host = bool(host_id) and (part.get("participant_user_id") == host_id or part.get("id") == host_id)
    return {
        "meeting_id": str(obj.get("id") or ""),
        "meeting_uuid": obj.get("uuid"),
        "at_iso": _iso(part.get("join_time") or part.get("date_time"), now),
        "name": part.get("user_name") or part.get("name") or "",
        "email": (part.get("email") or "").lower(),
        "is_host": is_host,
        "participant_id": part.get("participant_uuid") or part.get("user_id") or part.get("id"),
        "event": "meeting.participant_joined",
    }


def resolve_appointment_id(store, meeting_id: str) -> Optional[str]:
    if not meeting_id:
        return None
    idx = store.get("zoom_meeting:%s" % meeting_id)
    if isinstance(idx, dict) and idx.get("appointment_id"):
        return str(idx["appointment_id"])
    if isinstance(idx, str) and idx:
        return idx
    for key in store.keys("appt:"):
        rec = store.get(key) or {}
        if str(rec.get("zoom_meeting_id") or "") == str(meeting_id):
            appt_id = rec.get("appointment_id") or key[len("appt:"):]
            # set_if_absent, not set: two containers resolving the same meeting
            # id concurrently must not race on the index cache.
            store.set_if_absent("zoom_meeting:%s" % meeting_id, {"appointment_id": appt_id})
            return str(appt_id)
    return None


def handle_event(body: Dict[str, Any], store, now: datetime) -> Dict[str, Any]:
    """Pure handler. Returns what was stored (never raises on odd payloads)."""
    event = body.get("event") or ""
    payload = body.get("payload", {}) or {}
    obj = payload.get("object", {}) or {}
    meeting_id = str(obj.get("id") or "")
    result = {"event": event, "meeting_id": meeting_id, "stored": False}  # type: Dict[str, Any]
    if not meeting_id:
        result["reason"] = "no_meeting_id"
        return result
    appt_id = resolve_appointment_id(store, meeting_id)
    result["appointment_id"] = appt_id
    if event == "meeting.participant_joined":
        join = normalise_join(payload, now)
        # add_once, not get-then-append: Zoom retries deliveries and two
        # containers can handle the same join concurrently. shared/store.py
        # documents this exact race and provides add_once for it.
        stored = store.add_once("joins:%s" % meeting_id, join)
        result.update({"stored": stored, "join": join})
        if appt_id and stored:
            store.add_once("joins_by_appt:%s" % appt_id, join)
    elif event == "meeting.ended":
        rec = {"at_iso": _iso(obj.get("end_time"), now), "duration": obj.get("duration"), "meeting_id": meeting_id}
        store.set("meeting_ended:%s" % meeting_id, rec)
        result.update({"stored": True, "ended": rec})
    elif event == "meeting.started":
        store.set("meeting_started:%s" % meeting_id, {"at_iso": _iso(obj.get("start_time"), now)})
        result["stored"] = True
    else:
        result["reason"] = "ignored_event"
    return result


def _appointment_window(appointment: Dict[str, Any]):
    try:
        start = slots.parse_iso(appointment["start_iso"])
    except (KeyError, ValueError, TypeError):
        return None
    end_raw = appointment.get("end_iso")
    try:
        end = slots.parse_iso(end_raw) if end_raw else start + timedelta(minutes=15)
    except (ValueError, TypeError):
        end = start + timedelta(minutes=15)
    return start - JOIN_WINDOW_BEFORE, end + JOIN_WINDOW_AFTER


def _join_is_in_window(join: Dict[str, Any], window) -> bool:
    if window is None:
        return True
    raw = join.get("at_iso") or join.get("join_time") or join.get("at")
    if raw is None:
        return False
    try:
        t = slots.parse_iso(raw)
    except (ValueError, TypeError):
        return False
    return window[0] <= t <= window[1]


def meeting_id_for_appointment(store, appointment: Dict[str, Any]) -> Optional[str]:
    meeting_id = appointment.get("zoom_meeting_id")
    if not meeting_id:
        rec = store.get("appt:%s" % str(appointment.get("id"))) or {}
        meeting_id = rec.get("zoom_meeting_id")
    if not meeting_id and appointment.get("zoom_link"):
        meeting_id = meeting_id_from_link(appointment["zoom_link"])
    return str(meeting_id) if meeting_id else None


def joins_for_appointment(store, appointment: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Joins the tick feeds into no_show.detect: by appointment id, then by
    the appointment's zoom_meeting_id, then via the appt:<id> mapping.

    Only joins inside the appointment's own window are returned. Meeting ids
    are reused, so without this a join from an earlier call on the same link
    marks every later appointment "showed".
    """
    appt_id = str(appointment.get("id"))
    window = _appointment_window(appointment)
    out = [j for j in (store.get("joins_by_appt:%s" % appt_id) or []) if _join_is_in_window(j, window)]
    meeting_id = meeting_id_for_appointment(store, appointment)
    if meeting_id:
        for j in store.get("joins:%s" % meeting_id) or []:
            if j not in out and _join_is_in_window(j, window):
                out.append(j)
    return out


def _signal_in_window(rec: Any, window) -> Optional[Dict[str, Any]]:
    """A started/ended record only counts as telemetry for THIS appointment.

    The Discovery Call link is one reusable Personal Meeting ID, so last
    week's ``meeting_ended`` record sits under the same key. Without this
    filter it turns "the Zoom webhook told us nothing" into "Zoom says the
    meeting ran and nobody joined", i.e. a no-show verdict and the whole
    recovery ladder fired at a prospect who may well have attended.
    """
    if not isinstance(rec, dict):
        return None
    if window is None:
        return rec
    raw = rec.get("at_iso") or rec.get("at")
    if not raw:
        return None  # undatable signal: cannot be attributed to this call
    try:
        t = slots.parse_iso(raw)
    except (ValueError, TypeError):
        return None
    return rec if window[0] <= t <= window[1] else None


def meeting_signals(store, appointment: Dict[str, Any]) -> Dict[str, Any]:
    """Did Zoom tell us anything at all about *this* call? Used to tell
    "nobody joined" apart from "we have no telemetry"."""
    meeting_id = meeting_id_for_appointment(store, appointment)
    if not meeting_id:
        return {"meeting_id": None, "started": None, "ended": None}
    window = _appointment_window(appointment)
    return {
        "meeting_id": meeting_id,
        "started": _signal_in_window(store.get("meeting_started:%s" % meeting_id), window),
        "ended": _signal_in_window(store.get("meeting_ended:%s" % meeting_id), window),
    }


def meeting_id_from_link(link: str) -> Optional[str]:
    import re

    m = re.search(r"/j/(\d{9,12})", link or "")
    return m.group(1) if m else None


# ------------------------------------------------------------ FastAPI
try:
    from fastapi import APIRouter, Request
    from fastapi.responses import JSONResponse

    router = APIRouter()

    @router.post("/webhooks/zoom")
    async def zoom_webhook(request: Request):
        raw = await request.body()
        secret = get_secret()
        now = _now_fn()
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            return JSONResponse({"error": "invalid_json"}, status_code=400)
        if not secret:
            logger.error("zoom_secret_missing: set %s", SECRET_ENV)
            return JSONResponse({"error": "zoom_secret_missing"}, status_code=503)
        if body.get("event") == "endpoint.url_validation":
            token = (body.get("payload") or {}).get("plainToken", "")
            if not url_validation_enabled():
                logger.warning("url_validation disabled by %s", URL_VALIDATION_ENV)
                return JSONResponse({"error": "url_validation_disabled"}, status_code=403)
            if not safe_plain_token(token):
                # refuses "v0:<ts>:<body>" shaped tokens: this branch answers
                # before signature verification, so it must never sign a
                # caller-chosen signature message.
                logger.warning("rejected url_validation plainToken of unexpected shape")
                return JSONResponse({"error": "invalid_plain_token"}, status_code=400)
            return JSONResponse(challenge_response(token, secret), status_code=200)
        ok = verify_signature(secret, request.headers.get("x-zm-request-timestamp"), request.headers.get("x-zm-signature"), raw, now)
        if not ok:
            return JSONResponse({"error": "invalid_signature"}, status_code=401)
        store = getattr(request.app.state, "store", None) or get_store()
        result = handle_event(body, store, now)
        return JSONResponse({"ok": True, "result": result}, status_code=200)

except Exception:  # noqa: BLE001 - fastapi absent: the pure functions still work
    router = None
