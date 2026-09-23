"""Push (ntfy.sh) + optional Gmail SMTP notifications. Never raises.

    from shared.notify import notify
    notify("Positive reply", "Tiffany asked about pricing", priority="high",
           actions=[("Approve", approve_url), ("Veto", veto_url)])

Two rules this module enforces, both learned the hard way:

1. **It is a write.** Every send goes through ``settings.guard_write('notify',
   ...)`` first. In MODE=shadow the intent is recorded and nothing leaves the
   process, exactly like an Instantly or GHL write. ``NOTIFY_SHADOW_SEND=1``
   opts back in to real pushes during a shadow run (they only ever go to
   Lorenzo's own topic and address).
2. **ntfy.sh topics are public.** Anyone who knows the topic name can read it
   and click its action buttons. Unless the topic is protected (``NTFY_TOKEN``
   set, or ``NTFY_ALLOW_SENSITIVE=1``), the push carries no email addresses, no
   URLs and no action buttons: the full card goes to the email leg instead.

NOTIFY=off short-circuits to ``notify.sent_in_test`` (a list) so tests and
dry runs can assert what WOULD have been sent.

Topic: NTFY_TOPIC, else a generated ``advero-<12 hex>`` persisted to
.tmp/ntfy_topic.txt; the first message on a generated topic carries the
subscribe URL.
"""
import logging
import os
import re
import secrets
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional, Union

import httpx

from shared import settings
from shared.paths import tmp_file

logger = logging.getLogger("shared.notify")

NTFY_BASE = "https://ntfy.sh"
TOPIC_FILE_NAME = "ntfy_topic.txt"
VALID_PRIORITIES = ("min", "low", "default", "high", "urgent")
TRUTHY = ("1", "true", "yes", "on", "y", "t")

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL_RE = re.compile(r"https?://\S+")
_GENERATED_TOPIC_RE = re.compile(r"^advero-[0-9a-f]{12}$")

sent_in_test = []  # type: List[Dict[str, Any]]
_state = {"topic": None, "announced": False, "warned_public": False}  # type: Dict[str, Any]

# Test seams (tests may replace these)
_smtp_factory = smtplib.SMTP_SSL


def is_off() -> bool:
    return os.environ.get("NOTIFY", "on").strip().lower() in ("off", "0", "false", "no")


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in TRUTHY


def shadow_send_allowed() -> bool:
    """Deliver real pushes/emails while MODE=shadow? Off by default."""
    return _truthy("NOTIFY_SHADOW_SEND")


def topic_is_protected() -> bool:
    """True when the ntfy topic is safe for lead PII and action buttons: an
    access token is configured, or Lorenzo has explicitly accepted the risk."""
    return bool(os.environ.get("NTFY_TOKEN", "").strip()) or _truthy("NTFY_ALLOW_SENSITIVE")


def redact(text: str) -> str:
    """Strip anything a stranger on the topic must not read or click."""
    out = _EMAIL_RE.sub("[email hidden]", text or "")
    return _URL_RE.sub("[link hidden]", out)


def topic_file():
    return tmp_file(TOPIC_FILE_NAME)


def get_topic() -> str:
    """NTFY_TOPIC, else persisted generated topic, else generate + persist."""
    env_topic = os.environ.get("NTFY_TOPIC", "").strip()
    if env_topic:
        _state["topic"] = env_topic
        _state["announced"] = True
        return env_topic
    if _state["topic"]:
        return _state["topic"]
    path = topic_file()
    try:
        if path.exists():
            saved = path.read_text(encoding="utf-8").strip()
            if saved:
                _state["topic"] = saved
                _state["announced"] = True  # persisted topic was announced when created
                return saved
    except OSError as exc:
        logger.warning("could not read %s: %s", path, exc)
    topic = "advero-" + secrets.token_hex(6)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(topic + "\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("could not persist ntfy topic to %s: %s", path, exc)
    _state["topic"] = topic
    _state["announced"] = False
    logger.warning("Generated ntfy topic %s. Subscribe at %s/%s", topic, NTFY_BASE, topic)
    return topic


def subscribe_url(topic: Optional[str] = None) -> str:
    return "%s/%s" % (NTFY_BASE, topic or get_topic())


def format_actions(actions: Union[None, str, List[Any]]) -> Optional[str]:
    """ntfy "Actions" header: "view, Approve, <url>; view, Veto, <url>"."""
    if not actions:
        return None
    if isinstance(actions, str):
        return actions
    parts = []
    for a in actions:
        if isinstance(a, dict):
            kind = a.get("action", "view")
            label = str(a.get("label", "Open"))
            url = str(a.get("url", ""))
            clear = a.get("clear")
        else:
            seq = list(a)
            kind = "view"
            label, url = str(seq[0]), str(seq[1])
            clear = seq[2] if len(seq) > 2 else None
        label = label.replace(",", " ").replace(";", " ").strip()
        piece = "%s, %s, %s" % (kind, label, url)
        if clear:
            piece += ", clear=true"
        parts.append(piece)
    return "; ".join(parts)


def _ntfy_token() -> str:
    return os.environ.get("NTFY_TOKEN", "").strip()


def _scrub_secret(text: Any) -> str:
    """``text`` as a string with the ntfy token masked.

    Everything this module returns, logs or raises ends up somewhere a person
    or a store can read it (approval.py saves the notify result into the JSON
    store). An httpx error or an ntfy error body can quote the request back, so
    every such string passes through here before it leaves the module.
    """
    out = str(text)
    token = _ntfy_token()
    if token:
        out = out.replace("Bearer %s" % token, "[ntfy token hidden]").replace(token, "[ntfy token hidden]")
    return out


def _public_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """The request headers minus Authorization, for the result dict. The
    bearer token authenticates the push; it is never part of what notify()
    reports back, because callers persist that report."""
    return dict((k, v) for k, v in headers.items() if k.lower() != "authorization")


def _header_value(value: str) -> str:
    """httpx sends headers as ASCII; ntfy accepts RFC 2047 for anything else."""
    try:
        value.encode("ascii")
        return value
    except UnicodeEncodeError:
        return Header(value, "utf-8").encode()


def _warn_public_topic(topic: str) -> None:
    if _state.get("warned_public"):
        return
    _state["warned_public"] = True
    guessable = "" if _GENERATED_TOPIC_RE.match(topic or "") else (
        " The configured NTFY_TOPIC is also guessable; rotate it to the generated advero-<12 hex> form."
    )
    logger.warning(
        "ntfy topic %r is unauthenticated: anyone who knows the name can read it and press its "
        "buttons, so lead details, links and action buttons are being withheld from the push and "
        "sent by email instead. Set NTFY_TOKEN (or NTFY_ALLOW_SENSITIVE=1 to accept the risk).%s",
        topic, guessable,
    )


def _send_ntfy(topic: str, title: str, message: str, priority: str, actions, tags, click, transport,
               banner: Optional[str] = None) -> Dict[str, Any]:
    protected = topic_is_protected()
    if not protected:
        clean_title, clean_message = redact(title), redact(message)
        withheld = clean_title != title or clean_message != message or bool(actions) or bool(click)
        title, message = clean_title, clean_message
        # An action button on a public topic is a one-tap live send for anyone
        # subscribed; the Click URL is the same link in another header.
        actions = None
        click = None
        if withheld:
            _warn_public_topic(topic)
            if not message.endswith("(details in the email)"):
                message = message + "\n\n(details in the email)"
    if banner:
        # The subscribe URL is this topic's own address, which whoever reads the
        # message already has; it is added after redaction on purpose.
        message = banner + "\n\n" + message
    headers = {"Title": _header_value(title)}
    if priority and priority in VALID_PRIORITIES:
        headers["Priority"] = priority
    if tags:
        headers["Tags"] = ",".join(str(t) for t in tags) if not isinstance(tags, str) else tags
    if click:
        headers["Click"] = str(click)
    acts = format_actions(actions)
    if acts:
        headers["Actions"] = acts
    headers["Content-Type"] = "text/plain; charset=utf-8"
    # The token goes on the wire copy only. ``headers`` is what the result
    # reports, and the result is saved by callers (SAF-5, 2026-09-22: the
    # bearer token was landing in the JSON store).
    wire_headers = dict(headers)
    token = _ntfy_token()
    if token:
        wire_headers["Authorization"] = "Bearer %s" % token
    with httpx.Client(timeout=15.0, transport=transport) as client:
        resp = client.post("%s/%s" % (NTFY_BASE, topic), content=message.encode("utf-8"), headers=wire_headers)
    ok = 200 <= resp.status_code < 300
    if not ok:
        logger.warning("ntfy returned %s: %s", resp.status_code, _scrub_secret(resp.text)[:200])
    return {"ok": ok, "status": resp.status_code, "headers": _public_headers(headers),
            "authenticated": bool(token)}


def _email_config() -> Optional[Dict[str, str]]:
    to = os.environ.get("NOTIFY_EMAIL") or os.environ.get("NOTIFICATION_EMAIL")
    sender = os.environ.get("GMAIL_SENDER_EMAIL")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if to and sender and password:
        return {"to": to, "sender": sender, "password": password}
    return None


def _action_lines(actions: Union[None, str, List[Any]]) -> List[str]:
    """The Approve/Veto URLs as plain "Label: url" lines, for the email leg.

    format_actions() produces the ntfy header ("view, Approve, <url>; view,
    Veto, <url>"). ntfy only carries that header on a PROTECTED topic, so on
    Lorenzo's current unprotected topic the buttons are stripped and the push
    says "(details in the email)" - and the email used to carry no link either,
    which left no way to approve or veto anything at all.
    """
    formatted = format_actions(actions)
    if not formatted:
        return []
    lines = []
    for piece in formatted.split(";"):
        parts = [p.strip() for p in piece.split(",")]
        # "view, Approve, <url>" -> label is parts[1], url parts[2]
        if len(parts) >= 3 and parts[2]:
            lines.append("%s: %s" % (parts[1], parts[2]))
    return lines


def _send_email(cfg: Dict[str, str], title: str, message: str, click: Optional[str],
                actions: Union[None, str, List[Any]] = None) -> bool:
    body = message
    if click:
        body += "\n\n" + str(click)
    # The action URLs never reached the email. On an unprotected ntfy topic the
    # push drops them too, so the card arrived with nothing to act on.
    lines = _action_lines(actions)
    if lines:
        body += "\n\n" + "\n".join(lines)
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = title
    msg["From"] = cfg["sender"]
    msg["To"] = cfg["to"]
    server = _smtp_factory("smtp.gmail.com", 465, timeout=20)
    try:
        server.login(cfg["sender"], cfg["password"])
        server.sendmail(cfg["sender"], [cfg["to"]], msg.as_string())
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001
            pass
    return True


def notify(
    title: str,
    message: str,
    priority: str = "default",
    actions: Union[None, str, List[Any]] = None,
    tags: Optional[List[str]] = None,
    click: Optional[str] = None,
    transport: Optional[httpx.BaseTransport] = None,
    email_message: Optional[str] = None,
) -> Dict[str, Any]:
    """Send a push (and email when configured). Returns a result dict; never raises.

    ``email_message`` is the longer body for the EMAIL leg only. Without it
    both legs carry the same text, so a caller that wants counts on the public
    ntfy topic ("Upwork: 5 waiting, 2 post-contract asks") and the full digest
    in the inbox had to choose one or the other for both. ntfy topics are
    world-readable, so the detail belongs on the email leg. Defaults to
    ``message``, which is the old behaviour exactly.
    """
    record = {
        "title": title,
        "message": message,
        "priority": priority,
        "actions": format_actions(actions),
        "tags": list(tags) if tags else None,
        "click": click,
    }
    if email_message is not None and email_message != message:
        # The guarded record is what a live run would send, so it has to carry
        # both bodies or the shadow log under-describes the email.
        record["email_message"] = email_message
    if is_off():
        sent_in_test.append(record)
        return {"sent": False, "test": True, "record": record}

    # A push and an SMTP send are outbound writes like any other: in shadow the
    # intent is recorded and nothing leaves the process.
    guard = settings.guard_write("notify", "push_email", record)
    if guard.get("shadow") and not shadow_send_allowed():
        return {"sent": False, "test": False, "shadow": True, "record": record, "guard": guard,
                "ntfy": None, "email": False, "topic": None, "errors": []}

    result = {"sent": False, "test": False, "shadow": False, "ntfy": None, "email": False, "topic": None, "errors": []}  # type: Dict[str, Any]
    try:
        topic = get_topic()
        result["topic"] = topic
        banner = None
        if not _state.get("announced"):
            banner = "Subscribe to this topic on your phone: %s" % subscribe_url(topic)
        ntfy = _send_ntfy(topic, title, message, priority, actions, tags, click, transport, banner=banner)
        result["ntfy"] = ntfy
        if ntfy["ok"]:
            result["sent"] = True
            _state["announced"] = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("ntfy send failed: %s", _scrub_secret(exc))
        result["errors"].append("ntfy: %s" % _scrub_secret(exc))

    cfg = _email_config()
    if cfg:
        try:
            result["email"] = _send_email(
                cfg, title, message if email_message is None else email_message, click, actions)
            result["sent"] = result["sent"] or result["email"]
        except Exception as exc:  # noqa: BLE001
            logger.warning("email send failed: %s", _scrub_secret(exc))
            result["errors"].append("email: %s" % _scrub_secret(exc))
    return result


def reset_for_tests() -> None:
    del sent_in_test[:]
    _state["topic"] = None
    _state["announced"] = False
    _state["warned_public"] = False
