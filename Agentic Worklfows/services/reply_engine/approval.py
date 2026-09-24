"""Approval cards for every first reply, and the one auto-send path (CT3).

Rule (2026-09-22): an engine email (counter-proposal, booking confirmation,
cadence touch, show-rate or no-show message) is sent automatically only when
its text is exactly a template Lorenzo approved with
jobs/approve_templates.py and unchanged since, the template kill switch is
off, and every send check passes (copy gate, opt-out marker, lead reply hold,
07:00-19:00 CT send window, recipient check, slot rules); anything else goes
to Lorenzo as an approval card (replies) or is held (cadence, show-rate,
no-show). A first reply, and any reply but a booking confirmation to a lead
not answered yet, is never auto-sent (rule of 2026-09-23, draft_only,
FIRST_REPLY_LOCK_REASON): it is always a card, and he sends it himself from
the thread. This module is the card half.

create_approval(state, draft, event, auto=verdict) -> Approval (token =
<id>.<hmac>) persisted in the store under 'approval:<id>' for 48 h. Without an
allowed verdict (template_gate.draft_verdict) it pushes the card to Lorenzo
(push_card: shared.notify, the draft text and Approve / Veto / Edit URLs from
BASE_URL), with a "Not auto-sent: <reason>" line when a verdict was given.
With an allowed one nothing is pushed: notify_result records
{"deferred": "template_auto_send"} and the pipeline calls
auto_send_approved(), which goes through exactly the path a human Approve
takes (_approve_loaded(actor="template"), then send_approved) and re-runs the
gate inside send_approved, on the exact subject and body, right before the
send (a revoke, the kill switch or a redeploy between queueing and the 07:00
flush turns the card back into a pending card and pushes it). An allowed
verdict bypasses no send check. A card whose auto-send did not end in a send
or a queue is pushed once (the deferred push is claimed under the card's
lock), and push_orphaned_deferred pushes a card whose auto-send never ran
(a crash between the two). Every auto-send is counted for one FYI push per
30 minutes (flush_auto_send_fyi): counts per template id on ntfy, per-lead
lines and Veto links on the email leg only.

approve(token) sends through instantly.reply_to_email from the original inbox
and thread (guarded: shadow -> would_do), sets the Instantly interest status,
arms the cadence (services.reply_engine.cadence.arm(state) if that module
exists) unless the lead row, as it stands when the send is written, shows a
newer reply or another open card (arm_refusal), and logs. Outside 07:00-19:00
CT the send is queued until the window opens (flush_queued). veto(token)
marks the approval vetoed and releases the reserved slots. Whether the lead
may still be emailed at all is one verdict (_lead_reply_verdict, behind
lead_reply_hold and arm_refusal): their sticky opt-out marker, or a reply they
SENT after the one the card answers, read by the router's rule (the email's
own time when both replies carry one, else the order they were processed in).

mark_sent_manually(approval_id) records a send_failed card whose reply did go
out (Lorenzo checked the Instantly thread) as sent_manually and does what a
send does after the Instantly call; mark_sent_url(card) is its link. A card
stuck at sending qualifies once its send claim is SEND_CLAIM_LEASE_MINUTES
old (sending_takeover), and the send it takes over never overwrites it.
retry(token) waits out the same lease for a sending card (retry_refusal),
approve, edit, accept_requested and veto say when it ends, and taking a card
from sending writes a send_never_finished Job_Log row.

expire_overdue (run from flush_queued, so on every poller tick) retires every
open card (pending, blocked, stale_slots) past its 48 h TTL. A card whose send
may have reached Instantly (send_failed, sending, or holding a send claim) and
an approved_queued card never expire (EXPIRABLE_STATUSES). A card that holds
the lead's unconfirmed call writes nothing to GHL when it expires: the call
stays, its reminders stay held, and Lorenzo gets a high-priority Keep /
Release push (decide_expired_booking), recorded on the card and re-sent until
it is delivered. The push and the pages say only what the card's send history
(card_history) proves. Offered times are claimed atomically across leads
(claim_slots), and every cancel the engine starts passes to_notify=False.

escalate_pending(store) chases the cards he has not actioned: a rising push per
rung of ESCALATION_LADDER while a card is still `pending` inside sending hours,
and nothing outside them. It is what turns the 5-minute reply SLA from a number
the 07:30 sweep reports into something the system acts on. A chase is a push and
only a push - escalate_pending takes no Instantly client and can never send.

AUTO_SEND_AFTER_MINUTES / auto_send_due are the old timer auto-approve. CT3
does not use them and nothing calls auto_send_due (Q-E3): it defaults to 0
(disabled), is honoured only when the process is live (MODE=live +
ALLOW_LIVE_WRITES=1) and only for positive_interested; in shadow nothing is
ever auto-approved by it.
"""
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import socket
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlencode, urlparse

from shared import job_log, notify, settings, slots, store as store_mod

from services.reply_engine.models import (
    INTEREST_FOR_LABEL,
    RECEIVED_AT_EMAIL,
    RECEIVED_AT_PROCESSING,
    Approval,
    Draft,
    LeadState,
    ReplyEvent,
    entry_email_time,
    entry_received_at,
    is_synthetic_email_id,
)

logger = logging.getLogger("reply_engine.approval")

SECRET_ENV = "REPLY_ENGINE_SECRET"
TTL_HOURS = 48
APPROVAL_PREFIX = "approval:"
OFFERED_KEY = "offered_slots"  # global registry: [{"slot", "lead", "at", "approval"}]
SEND_CLAIM_PREFIX = "approval_send_claim:"
# The only two states a send may start from. Everything else (sending, sent,
# sent_manually, vetoed, expired, blocked, send_failed, superseded) refuses.
SENDABLE_STATUSES = ("pending", "approved_queued")
# A card whose reply reached the lead: sent by the engine ("sent"), or sent
# after a failed send and recorded by Lorenzo's Mark sent (mark_sent_manually:
# "sent_manually"). Every list below that means "this card's reply went out"
# is built from this one.
SENT_STATUSES = ("sent", "sent_manually")
DEV_SECRET = "dev-secret-set-REPLY_ENGINE_SECRET"
# booking.book() flags this when the GHL calendar still has no Zoom app (it does
# not, as of 2026-09-21). It is an operational note for Lorenzo, not a defect in
# the copy, so it never blocks a send; it is carried in the rationale instead.
ZOOM_NOT_CONNECTED = "zoom_not_connected"


class ApprovalSecretMissing(Exception):
    """MODE=live with no REPLY_ENGINE_SECRET: every approval token would be
    signed with the in-repo development secret, so anyone who knows the URL
    shape could mint one and send a reply as Lorenzo."""


class ApprovalUndeliverable(Exception):
    """MODE=live with no way to put the card in front of Lorenzo.

    Either BASE_URL is unset (so every action URL would be
    http://localhost:8000/... - dead on his phone) or there is no channel that
    can carry the buttons: an unprotected ntfy topic strips the Actions and
    Click headers, and with no GMAIL_*/NOTIFY_EMAIL leg there is no email
    fallback either. notify() still answers sent=True in that state, so the
    'was NOT pushed' alarm never fires and the first live positive reply
    produces a notification nobody can act on.
    """


def _secret() -> str:
    value = os.environ.get(SECRET_ENV, "").strip()
    if not value:
        if settings.is_live():
            # Fail closed. In live, an approval token IS the authorisation to
            # send an email from Lorenzo's inbox; DEV_SECRET is in the repo.
            raise ApprovalSecretMissing(
                "%s is unset and MODE=live: approval tokens would be signed with the development "
                "secret that is committed to this repository, so anyone could approve a send. "
                "Set %s in the environment (and in the Modal secret) before going live."
                % (SECRET_ENV, SECRET_ENV))
        logger.warning("%s unset; using a development secret (set it before go-live)", SECRET_ENV)
        return DEV_SECRET
    return value


BASE_URL_ENV = "BASE_URL"
BASE_URL_FALLBACK_ENV = "REPLY_ENGINE_BASE_URL"
DEV_BASE_URL = "http://localhost:8000"
BASE_URL_SCHEMES = ("http", "https")
# Only digits, dots and hex marks: the shapes inet_aton reads as an IPv4
# address ("2130706433", "0", "127.1", "0x7f.1"). A real hostname never
# parses, so running it past inet_aton is harmless.
_NUMERIC_HOST_RE = re.compile(r"^[0-9a-fx.]+$", re.I)


def _ip_of(host: str):
    """The address ``host`` denotes, in any form a resolver would accept, or None."""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
        if _NUMERIC_HOST_RE.match(host):
            try:
                ip = ipaddress.IPv4Address(socket.inet_aton(host))
            except (OSError, ValueError):
                ip = None
    mapped = getattr(ip, "ipv4_mapped", None)
    return mapped if mapped is not None else ip


def _usable_base_url(raw: Optional[str]) -> Optional[str]:
    """``raw`` without a trailing slash, or None when it cannot reach a phone.

    Requires an http(s) scheme and a host. Refuses localhost, ``localhost.``
    and any ``*.localhost`` name, and every address that is loopback,
    unspecified or link-local, in whatever form it is written: bracketed or
    long-form IPv6, IPv4-mapped IPv6, an integer ("2130706433"), "0".
    """
    value = (raw or "").strip().rstrip("/")
    if not value:
        return None
    try:
        parsed = urlparse(value)
        scheme = (parsed.scheme or "").lower()
        host = (parsed.hostname or "").strip().lower()
    except ValueError:
        return None
    if scheme not in BASE_URL_SCHEMES or not host:
        return None
    name = host.rstrip(".")
    if not name or name == "localhost" or name.endswith(".localhost"):
        return None
    ip = _ip_of(name)
    if ip is not None and (ip.is_loopback or ip.is_unspecified or ip.is_link_local):
        return None
    return value


def configured_base_url() -> Optional[str]:
    """The public base URL, or None when it is unset or only local.

    BASE_URL is the name the deployment runbook sets; REPLY_ENGINE_BASE_URL is
    the alias older code read. A BASE_URL of localhost does not shadow a real
    alias: it is treated as missing and the alias is tried next.
    """
    for name in (BASE_URL_ENV, BASE_URL_FALLBACK_ENV):
        value = _usable_base_url(os.environ.get(name))
        if value:
            return value
    return None


def base_url() -> str:
    """Where Lorenzo's phone reaches this service. The one resolver every
    link builder uses: approval cards, SLA chases, and the cadence's D1 Veto,
    D6 "Send hold" / "Email only" links.

    Fails closed in live, the way _secret() does: an approval card whose
    buttons point at http://localhost:8000 is a positive reply with no way to
    answer it, and a D1 auto-send behind such a Veto button has no brake.
    Unset, localhost, 127.0.0.1, 0.0.0.0 and ::1 all count as missing.
    """
    value = configured_base_url()
    if not value:
        if settings.is_live():
            raise ApprovalUndeliverable(
                "%s is unset (or points at a local-only host) and MODE=live: every Approve/Veto/Edit URL on the "
                "card would point at %s, which is unreachable from Lorenzo's phone. Set %s in the environment "
                "(and in the Modal secret) before going live." % (BASE_URL_ENV, DEV_BASE_URL, BASE_URL_ENV))
        # ERROR, not WARNING, in shadow as well. A 48-hour shadow watch whose
        # whole point is "can Lorenzo approve from his phone" is unobservable
        # when every button points at localhost, and a warning in a Modal log
        # nobody reads is how that went unnoticed.
        logger.error(
            "%s is unset or local-only: every Approve/Veto/Edit button will point at %s, which is dead on a "
            "phone. The 48-hour shadow watch cannot exercise the approve path until it is set in the Modal "
            "secret (runbooks/deployment.md step 2a).", BASE_URL_ENV, DEV_BASE_URL)
        return DEV_BASE_URL
    return value


def deliverable_channels() -> Dict[str, bool]:
    """Can a card with working buttons actually reach Lorenzo?

    ntfy only carries the Actions/Click headers when the topic is protected
    (NTFY_TOKEN, or NTFY_ALLOW_SENSITIVE=1); otherwise shared.notify strips
    them and appends "(details in the email)", which only helps if the email
    leg is configured.
    """
    ntfy = False
    email = False
    try:
        ntfy = not notify.is_off() and bool(notify.topic_is_protected())
    except Exception as exc:  # noqa: BLE001 - a notify import/config error must not crash the pipeline
        logger.warning("could not read the ntfy config: %s", exc)
    try:
        email = notify._email_config() is not None  # noqa: SLF001 - the only accessor there is
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not read the email config: %s", exc)
    return {"ntfy_actions": ntfy, "email": email, "any": bool(ntfy or email)}


def stored_notify_result(result: Any) -> Dict[str, Any]:
    """The part of a notify() result that is safe, and needed, in the store.

    The raw result carries the ntfy request headers (an Authorization header
    whenever NTFY_TOKEN is set), the topic name (on an unprotected topic, the
    one thing standing between a stranger and a subscription) and the full
    record with every signed action URL in it. The approval row keeps only what
    something reads back: poller._pushed, auto_send_due and the SLA chase look
    at sent / test / shadow / actionable / errors / channels.
    """
    if not isinstance(result, dict):
        return {"sent": bool(result)}
    out = {}  # type: Dict[str, Any]
    for key in ("sent", "test", "shadow", "email"):
        if key in result:
            out[key] = bool(result.get(key))
    errors = result.get("errors")
    if isinstance(errors, (list, tuple)):
        out["errors"] = [str(e)[:300] for e in errors]
    ntfy = result.get("ntfy")
    if isinstance(ntfy, dict):
        out["ntfy"] = {"ok": bool(ntfy.get("ok"))}
        if isinstance(ntfy.get("status"), int):
            out["ntfy"]["status"] = ntfy["status"]
    return out


def require_deliverable_channel() -> Dict[str, bool]:
    channels = deliverable_channels()
    if not channels["any"] and settings.is_live():
        raise ApprovalUndeliverable(
            "no channel can deliver an approval card in live: the ntfy topic is unprotected (set NTFY_TOKEN, "
            "or NTFY_ALLOW_SENSITIVE=1 to accept a public topic) so the Approve/Veto buttons are stripped, and "
            "no email leg is configured (GMAIL_SENDER_EMAIL + GMAIL_APP_PASSWORD + NOTIFY_EMAIL). "
            "The card would reach Lorenzo with nothing to tap.")
    return channels


def draft_hash(draft: Draft) -> str:
    return hashlib.sha256(("%s\n%s" % (draft.subject, draft.body_text)).encode("utf-8")).hexdigest()[:24]


def _sig(approval_id: str, state_key: str, dhash: str, expires_at: str) -> str:
    msg = "|".join([approval_id, state_key, dhash, expires_at]).encode("utf-8")
    return hmac.new(_secret().encode("utf-8"), msg, hashlib.sha256).hexdigest()[:32]


def make_token(approval_id: str, state_key: str, dhash: str, expires_at: str) -> str:
    return "%s.%s" % (approval_id, _sig(approval_id, state_key, dhash, expires_at))


def _store(store=None):
    return store if store is not None else store_mod.get_store()


def _slot_label(iso: Optional[str]) -> str:
    """Lorenzo-facing label, with the date in it.

    slots.format_slot carries no date ("Fri 2:00pm"), so a card offering a
    "Book Fri 2:00pm CT" action did not say which Friday - and shared.slots
    _parse_day resolves "next Friday" said Mon-Thu to the following week, so
    the two can disagree by seven days. This is the card, not the email: the
    customer-facing wording in draft.py is unchanged.
    """
    if not iso:
        return "that time"
    try:
        dt = slots.to_tz(slots.parse_iso(iso))
    except (ValueError, TypeError):
        return str(iso)
    hour = dt.hour % 12 or 12
    # No comma: the label travels in ntfy's Actions header, which is
    # comma-delimited, and shared.notify strips commas out of an action title.
    return "%s %s %d %d:%02d%s CT" % (dt.strftime("%a"), dt.strftime("%b"), dt.day, hour, dt.minute,
                                      "am" if dt.hour < 12 else "pm")


def _now(now: Optional[datetime]) -> datetime:
    return slots.to_tz(slots.ensure_aware(now)) if now is not None else datetime.now(slots.TZ)


def action_urls(token: str) -> Dict[str, str]:
    b = base_url()
    return {"approve": "%s/approve/%s" % (b, token), "veto": "%s/veto/%s" % (b, token), "edit": "%s/edit/%s" % (b, token),
            "accept": "%s/accept/%s" % (b, token), "retry": "%s/retry/%s" % (b, token)}


# --------------------------------------------------------- slot registry
def reserve_slots(store, lead_email: str, slot_isos: List[str], approval_id: str, now: datetime) -> None:
    """Hold these times against every other lead, exactly once each.

    store.mutate is the read-modify-write primitive: a plain append could not
    tell an existing reservation from a new one, so re-reserving (edit(), then
    accept_requested, then a retry) grew the registry without bound and
    release_slots had to delete several rows to free one time. Deduped on
    (slot, lead, approval) so a genuine second offer of the same slot to a
    DIFFERENT lead is still visible - which is what the never-double-offered
    rule reads this registry for.
    """
    if not slot_isos:
        return

    def _add(rows):
        rows = list(rows or [])
        held = set()
        for r in rows:
            if isinstance(r, dict):
                held.add((r.get("slot"), r.get("lead"), r.get("approval")))
        for iso in slot_isos:
            if (iso, lead_email, approval_id) in held:
                continue
            rows.append({"slot": iso, "lead": lead_email, "at": now.isoformat(), "approval": approval_id})
            held.add((iso, lead_email, approval_id))
        return rows

    try:
        store.mutate(OFFERED_KEY, _add, default=[])
    except AttributeError:  # a store without the atomic primitives
        for iso in slot_isos:
            try:
                store.append(OFFERED_KEY, {"slot": iso, "lead": lead_email, "at": now.isoformat(), "approval": approval_id})
            except Exception as exc:  # noqa: BLE001
                logger.warning("slot reserve failed: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("slot reserve failed: %s", exc)


def _slot_instant(iso: Any) -> Optional[int]:
    try:
        return int(slots.parse_iso(iso).timestamp())
    except (ValueError, TypeError, AttributeError):
        return None


def slot_conflicts(rows: Any, lead_email: str, slot_isos: List[str], now: datetime) -> List[str]:
    """The times in ``slot_isos`` that ``rows`` (the registry) already holds for
    a DIFFERENT lead, still ahead of ``now``. A row with no lead counts as
    another lead's: it cannot be shown to be this one's."""
    me = (lead_email or "").strip().lower()
    held = set()  # type: set
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        if str(r.get("lead") or "").strip().lower() == me and me:
            continue
        key = _slot_instant(r.get("slot"))
        if key is None or key < int(now.timestamp()):
            continue
        held.add(key)
    return [iso for iso in slot_isos or [] if _slot_instant(iso) in held]


def claim_slots(store, lead_email: str, slot_isos: List[str], now: datetime,
                fields: Optional[Dict[str, Any]] = None) -> List[str]:
    """Hold these times for this lead against every other lead, atomically:
    all of them, or none. Returns the times another lead already holds (empty
    when the claim went through).

    reserve_slots is idempotent but never refuses, and every caller picked its
    times from a read made earlier (the draft's offered_slots, the cadence's
    fresh_slots, booking's free list), so two leads processed at the same
    moment could both be offered, or booked into, the same 15 minutes (SAL-10).
    The check and the write happen inside one ``store.mutate``: the second
    claim sees the first one's rows. ``fields`` go on every new row and, with
    (slot, lead), decide whether a row is already this claim's (a replay adds
    nothing)."""
    isos = [iso for iso in (slot_isos or []) if iso]
    if not isos:
        return []
    extra = dict(fields or {})
    box = {"conflicts": []}  # type: Dict[str, Any]

    def _claim(rows):
        rows = list(rows or [])
        conflicts = slot_conflicts(rows, lead_email, isos, now)
        box["conflicts"] = conflicts
        if conflicts:
            return rows
        for iso in isos:
            if any(isinstance(r, dict) and r.get("slot") == iso and r.get("lead") == lead_email
                   and all(r.get(k) == v for k, v in extra.items()) for r in rows):
                continue
            rows.append(dict({"slot": iso, "lead": lead_email, "at": now.isoformat()}, **extra))
        return rows

    mutate = getattr(store, "mutate", None)
    if callable(mutate):
        mutate(OFFERED_KEY, _claim, default=[])
        return list(box["conflicts"])
    # A store without the atomic primitive: the same decision, best effort.
    current = store.get(OFFERED_KEY, []) or []
    new = _claim(current)
    if not box["conflicts"]:
        store.set(OFFERED_KEY, new)
    return list(box["conflicts"])


def release_claimed(store, lead_email: str, slot_isos: List[str], fields: Optional[Dict[str, Any]] = None) -> None:
    """Undo a claim_slots whose offer never went out: drop this lead's rows for
    these times that carry exactly ``fields``. Never raises."""
    extra = dict(fields or {})
    wanted = set(slot_isos or [])

    def _drop(rows):
        return [r for r in (rows or []) if not (isinstance(r, dict) and r.get("slot") in wanted
                                                 and r.get("lead") == lead_email
                                                 and all(r.get(k) == v for k, v in extra.items()))]

    try:
        store.mutate(OFFERED_KEY, _drop, default=[])
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not release the claimed slots %s: %s", sorted(wanted), exc)


def release_slots(store, approval_id: str) -> None:
    """Give this approval's held times back, atomically.

    Read-then-set loses a reservation written between the get and the set, and
    there are four writers on this key (the 5-minute poller, the hourly cadence
    tick, the 10-minute appointments tick and the web approve/veto handlers),
    which modal_app runs as separate functions. A lost reservation is exactly
    the double-offer this registry exists to prevent, so this takes the same
    ``mutate`` treatment ``reserve_slots`` documents.
    """

    def _drop(rows):
        return [r for r in (rows or []) if not (isinstance(r, dict) and r.get("approval") == approval_id)]

    try:
        store.mutate(OFFERED_KEY, _drop, default=[])
    except AttributeError:  # a store without the atomic primitives
        try:
            current = store.get(OFFERED_KEY, []) or []
            store.set(OFFERED_KEY, _drop(current))
        except Exception as exc:  # noqa: BLE001
            logger.warning("slot release failed: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("slot release failed: %s", exc)


def _release_card_slots(store, approval_id: str, keep: Optional[List[str]] = None,
                        drop: Optional[List[str]] = None) -> None:
    """Give back some of this approval's held times, atomically, as
    release_slots does: its rows whose time is not in ``keep`` (when given)
    and is in ``drop`` (when given). Never raises."""
    keep_set = None if keep is None else set(keep)
    drop_set = None if drop is None else set(drop)

    def _goes(row):
        if not (isinstance(row, dict) and row.get("approval") == approval_id):
            return False
        if keep_set is not None and row.get("slot") in keep_set:
            return False
        return drop_set is None or row.get("slot") in drop_set

    def _drop(rows):
        return [r for r in (rows or []) if not _goes(r)]

    try:
        store.mutate(OFFERED_KEY, _drop, default=[])
    except AttributeError:  # a store without the atomic primitives
        try:
            current = store.get(OFFERED_KEY, []) or []
            store.set(OFFERED_KEY, _drop(current))
        except Exception as exc:  # noqa: BLE001
            logger.warning("slot release failed: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("slot release failed: %s", exc)


def offered_slots(store, now: Optional[datetime] = None, exclude_lead: Optional[str] = None) -> List[str]:
    """Every slot currently offered to anyone (past ones are pruned); exclude_lead drops that lead's own offers."""
    try:
        rows = store.get(OFFERED_KEY, []) or []
    except Exception:  # noqa: BLE001
        return []
    out = []
    cutoff = _now(now) - timedelta(days=1) if now is not None else None
    for r in rows:
        if not isinstance(r, dict):
            # One stray string in the registry used to raise AttributeError
            # inside _reply_draft, BEFORE the reply id was recorded as
            # processed, so every retry failed the same way and the positive
            # reply was lost for good. Skip the row and say so instead.
            logger.warning("offered_slots: ignoring an unreadable registry row %r", r)
            continue
        iso = r.get("slot")
        if not iso:
            continue
        if exclude_lead and (r.get("lead") or "").lower() == exclude_lead.lower():
            continue
        if cutoff is not None:
            try:
                if slots.parse_iso(iso) < cutoff:
                    continue
            except (ValueError, TypeError):
                pass
        out.append(iso)
    return out


def _claim_send(store, approval_id: str, ts: datetime) -> Optional[str]:
    """Single-winner claim for one send.

    approve() was a read-check-send-write sequence, so two concurrent hits (a
    double tap on the ntfy action, a retried request, a link scanner following
    the URL) both passed the status check and both reached Instantly: the lead
    got the same reply twice on the same thread. store.set_if_absent does the
    whole read-decide-write inside one lock, so exactly one caller wins.
    """
    attempt = secrets.token_hex(8)
    claim = {"attempt": attempt, "at": ts.isoformat()}
    key = SEND_CLAIM_PREFIX + approval_id
    setter = getattr(store, "set_if_absent", None)
    if callable(setter):
        try:
            return attempt if setter(key, claim) else None
        except Exception as exc:  # noqa: BLE001 - a broken claim must not block the one real send
            logger.warning("send claim failed for %s: %s", approval_id, exc)
            return attempt
    try:  # older store: an atomic append still yields a single winner
        rows = store.append(key, claim)
    except Exception as exc:  # noqa: BLE001
        logger.warning("send claim failed for %s: %s", approval_id, exc)
        return attempt
    first = rows[0] if isinstance(rows, list) and rows else None
    return attempt if isinstance(first, dict) and first.get("attempt") == attempt else None


def _slot_keys(isos) -> set:
    out = set()
    for iso in isos or ():
        try:
            out.add(int(slots.parse_iso(iso).timestamp()))
        except (ValueError, TypeError):
            continue
    return out


def stale_slots(offered: List[str], now: datetime, booked: Optional[List[str]] = None) -> List[str]:
    """Offered times that are no longer offerable at send time.

    approve() checks the status, the 48 h TTL and the send window; nothing
    re-checked the times themselves. A draft written at 09:00 offering "Mon
    2:00pm" and approved 25 h later (well inside TTL_HOURS=48) went out
    byte-identical, offering a time 20 hours in the past - and slots.format_slot
    carries no date, so the lead reads it as the coming Monday and books
    nothing.

    A slot that IS the booking this reply confirms is not an offer and is never
    stale: Lorenzo may have waived his own slot rule for it on the card.
    """
    keep = _slot_keys(booked)
    out = []  # type: List[str]
    for iso in offered or ():
        try:
            key = int(slots.parse_iso(iso).timestamp())
        except (ValueError, TypeError):
            continue
        if key in keep:
            continue
        try:
            if not slots.is_offerable(iso, now):
                out.append(iso)
        except (ValueError, TypeError):
            continue
    return out


class _ThreadProbe(object):
    """The shape cadence.thread_recipient_ok reads (last_email_id + lead_email),
    built from the approval so the comparison is against the address the reply
    is actually addressed to, not the CRM key."""

    def __init__(self, email_id, recipient):
        self.last_email_id = email_id
        self.email_id = email_id
        self.lead_email = recipient


def _recipient_verdict(approval: Approval, recipient: str, instantly) -> Optional[bool]:
    """True / False / None: does the thread really belong to ``recipient``?

    Only True lets a live send through (Lorenzo, decision R6). None - no
    client, no get_email, a read error or a timeout - used to count as "not a
    refusal", so the second recipient belt opened exactly when it could not
    look. It now holds the send instead (see _hold_for_recipient).
    """
    try:
        from services.reply_engine import cadence  # type: ignore
    except ImportError:
        logger.warning("cadence module absent; the reply recipient cannot be re-read")
        return None
    try:
        return cadence.thread_recipient_ok(_ThreadProbe(approval.email_id, recipient), instantly)
    except Exception as exc:  # noqa: BLE001 - a failed re-read holds the send, it never crashes it
        logger.warning("recipient re-read failed for %s: %s", approval.lead_email, exc)
        return None


# Decision R6 (Lorenzo): a live reply goes out only on a confirmed recipient
# match. A re-read that errors or times out holds the card and retries on a
# later poller tick (flush_queued); after RECIPIENT_HOLD_MAX_ATTEMPTS it is
# escalated and stays held until he retries it by hand.
RECIPIENT_HOLD_PREFIX = "approval_recipient_hold:"
RECIPIENT_HOLD_MAX_ATTEMPTS = 3
RECIPIENT_RETRY_MINUTES = 10
# A hold that escalated to send_failed is also recorded on the card's
# notify_result under this key ({"reason", "attempts", "at", "to"}); Retry
# clears it with the RECIPIENT_HOLD_PREFIX row.
RECIPIENT_HELD_KEY = "recipient_hold"


def _alert(title: str, message: str, priority: str = "high", actions: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Tell Lorenzo something went wrong, through the ordinary notify path.
    ``actions`` are signed buttons: shared.notify strips them on a public
    topic and lists them in the email leg, as it does a card's. Never
    raises: the alert is about a failure, it must not become one."""
    kwargs = {"priority": priority, "tags": ["warning", "reply-engine"]}  # type: Dict[str, Any]
    if actions:
        kwargs["actions"] = actions
    try:
        return stored_notify_result(notify.notify(title, message, **kwargs))
    except Exception as exc:  # noqa: BLE001
        logger.warning("alert failed (%s): %s", title, exc)
        return {"sent": False, "errors": ["notify raised: %s" % exc]}


def _held_alert_buttons(approval: Approval, st, ts: datetime) -> List[Any]:
    """Retry and Veto for the alert of a card its recipient hold escalated
    (recovery_links on the card as just saved); none when the links cannot
    be built. Never raises."""
    try:
        links = recovery_links(approval, st, ts)
    except Exception as exc:  # noqa: BLE001 - the alert still goes out, and says it has no links
        logger.warning("the recipient-hold alert for %s carries no links: %s", approval.lead_email, exc)
        return []
    return [(name, links[key]) for key, name in (("retry", "Retry"), ("veto", "Veto")) if links.get(key)]


def _hold_for_recipient(approval: Approval, st, ts: datetime, approval_id: str, recipient: str,
                        verdict: Optional[bool]) -> Dict[str, Any]:
    """Nothing was sent: hold the card, say so, and retry or escalate.

    The send claim is dropped (nothing left the process, so a later attempt
    must be able to win a fresh one). A mismatch is proof, not a hiccup: it is
    escalated on the first attempt, as before. A read that could not decide is
    retried RECIPIENT_HOLD_MAX_ATTEMPTS times, RECIPIENT_RETRY_MINUTES apart,
    through the approved_queued queue flush_queued already drains.

    A card Mark sent took over while the thread was being re-read (its claim
    was past SEND_CLAIM_LEASE_MINUTES, so this worker was held up) is left
    exactly as it is: no hold row, its claim kept, nothing written over it
    (_save_unless_sent below covers the moment between the look and the
    write), and the answer is "card changed, nothing was sent".
    """
    try:
        current = st.get(APPROVAL_PREFIX + approval_id)
    except Exception:  # noqa: BLE001 - the guarded writes below still refuse a sent card
        current = None
    if isinstance(current, dict) and current.get("status") in SENT_STATUSES:
        return _card_changed(st, approval_id)
    reason = "recipient_mismatch" if verdict is False else "recipient_unconfirmed"
    key = RECIPIENT_HOLD_PREFIX + approval_id
    try:
        previous = st.get(key) or {}
    except Exception:  # noqa: BLE001
        previous = {}
    attempts = int(previous.get("attempts") or 0) + 1
    record = {"attempts": attempts, "reason": reason, "first_at": previous.get("first_at") or ts.isoformat(),
              "last_at": ts.isoformat(), "to": recipient, "email_id": approval.email_id}
    try:
        st.set(key, record)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not record the recipient hold for %s: %s", approval_id, exc)
    try:
        st.delete(SEND_CLAIM_PREFIX + approval_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not clear the send claim for %s: %s", approval_id, exc)
    who = approval.lead_email
    escalate = verdict is False or attempts >= RECIPIENT_HOLD_MAX_ATTEMPTS
    if escalate:
        approval.status = "send_failed"
        approval.decided_at = ts.isoformat()
        approval.send_after = None
        # On the card itself, so anything holding only the card (the stuck
        # push's Mark sent button, mark_sent_url) can tell this send_failed
        # from a failed send: nothing was sent, and Mark sent is not offered.
        approval.notify_result = dict(approval.notify_result or {}, **{RECIPIENT_HELD_KEY: {
            "reason": reason, "attempts": attempts, "at": ts.isoformat(), "to": recipient}})
        # Never over a card Mark sent took over while the thread was re-read.
        if _save_unless_sent(approval, st) is not None:
            return _card_changed(st, approval_id)
        why = ("the thread's last inbound is from somebody else" if verdict is False else
               "the thread could not be re-read %d times in a row" % attempts)
        logger.error("refusing to reply for %s: %s; nothing was sent", who, why)
        job_log.log_run("reply_engine.approval", reason,
                        {"lead": who, "to": recipient, "email_id": approval.email_id, "attempts": attempts,
                         "escalated": True})
        buttons = _held_alert_buttons(approval, st, ts)
        names = [name for name, _ in buttons]
        steps = []
        if "Retry" in names:
            steps.append("press Retry (the card goes back to pending and its next send checks the thread again)")
        if "Veto" in names:
            steps.append("Veto it and reply by hand")
        if steps:
            todo = ("Check the thread in the Instantly inbox, then %s. Mark sent is not available: nothing reached "
                    "Instantly." % ", or ".join(steps))
        else:
            todo = ("Check the thread in the Instantly inbox and reply by hand. This alert carries no Retry or Veto "
                    "link (BASE_URL is unset, or the card moved on).")
        alert = _alert("Reply to %s HELD: recipient not confirmed" % who,
                       "Nothing was sent. Before replying the engine re-reads the thread and checks it was %s who "
                       "wrote it; %s. The card stays held. %s" % (recipient, why, todo), priority="urgent",
                       actions=buttons)
        return {"ok": False, "status": approval.status, "error": reason, "held": True, "escalated": True,
                "attempts": attempts, "alert": alert}
    approval.status = "approved_queued"
    approval.send_after = (ts + timedelta(minutes=RECIPIENT_RETRY_MINUTES)).isoformat()
    if _save_unless_sent(approval, st) is not None:
        return _card_changed(st, approval_id)
    logger.error("holding the reply to %s: the recipient re-read could not confirm %s (attempt %d of %d)",
                 who, recipient, attempts, RECIPIENT_HOLD_MAX_ATTEMPTS)
    job_log.log_run("reply_engine.approval", "recipient_held",
                    {"lead": who, "to": recipient, "email_id": approval.email_id, "attempts": attempts,
                     "retry_after": approval.send_after})
    alert = None
    if attempts == 1:
        alert = _alert("Reply to %s held: could not confirm the recipient" % who,
                       "Nothing was sent. The thread re-read failed, so the engine could not confirm it belongs to "
                       "%s. It retries on its own after %s (up to %d attempts), then escalates."
                       % (recipient, approval.send_after, RECIPIENT_HOLD_MAX_ATTEMPTS))
    return {"ok": False, "status": approval.status, "error": reason, "held": True, "escalated": False,
            "attempts": attempts, "send_after": approval.send_after, "alert": alert}


def _booked_slots_for(state: Optional[LeadState]) -> List[str]:
    booking = (getattr(state, "cadence", None) or {}).get("booking") or {} if state is not None else {}
    iso = booking.get("slot")
    return [iso] if iso else []


# ------------------------------------------------------ booking ownership
# booking.book() runs at classification time, so a call can sit on the
# calendar (invite withheld, show-rate ladder held) while the card that would
# confirm it is still pending. Exactly one card owns that unconfirmed booking:
# approving it releases the invite and the ladder, vetoing or expiring it
# tears the booking down. The owner's approval id is recorded on the booking
# itself (state.cadence.booking.owner). It used to be implied by the label
# 'booking_confirmation', which broke as soon as a second reply superseded the
# card: the new card had another label, so approving it never released the
# invite and vetoing it tore nothing down (SAL-1, the Sopio replay).
def _approval_id(approval: Approval) -> str:
    return approval.token.split(".", 1)[0]


def booking_of(state: Optional[LeadState]) -> Dict[str, Any]:
    if state is None:
        return {}
    return dict((getattr(state, "cadence", None) or {}).get("booking") or {})


def _same_slot(a: Optional[str], b: Optional[str]) -> bool:
    if not a or not b:
        return False
    try:
        return int(slots.parse_iso(a).timestamp()) == int(slots.parse_iso(b).timestamp())
    except (ValueError, TypeError):
        return a == b


def owns_booking(approval: Approval, state: Optional[LeadState]) -> bool:
    """Does this card own the lead's still-unconfirmed booking?

    An explicit owner decides. A booking whose confirmation has already gone
    out (awaiting_approval False) belongs to no card any more. A record
    written before owners were tracked falls back to the old rule, narrowed to
    a booking_confirmation card that names the booked slot.
    """
    booking = booking_of(state)
    if not booking.get("slot"):
        return False
    owner = booking.get("owner")
    if owner:
        return owner == _approval_id(approval)
    if booking.get("awaiting_approval") is False:
        return False
    return (approval.label == "booking_confirmation"
            and any(_same_slot(iso, booking.get("slot")) for iso in approval.draft.offered_slots or []))


def claim_booking(state: LeadState, approval_id: str, now: datetime, transferred_from: Optional[str] = None) -> None:
    """Record ``approval_id`` as the card that owns the lead's booking."""
    cad = dict(getattr(state, "cadence", None) or {})
    booking = dict(cad.get("booking") or {})
    if not booking.get("slot"):
        return
    booking["owner"] = approval_id
    booking.setdefault("awaiting_approval", True)
    if transferred_from:
        booking["transferred_from"] = transferred_from
        booking["transferred_at"] = now.isoformat()
    cad["booking"] = booking
    state.cadence = cad


def card_owns_booking(approval: Approval, store=None) -> bool:
    """owns_booking() for a caller that only has the card (the veto page)."""
    try:
        raw = _store(store).get(approval.state_key)
        return owns_booking(approval, LeadState.from_store(raw) if raw else None)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not read the lead state behind %s: %s", approval.lead_email, exc)
        return approval.label == "booking_confirmation"


def keeps_booked_slot(draft: Draft, slot_iso: Optional[str]) -> bool:
    """True when the draft talks about exactly the booked time and no other."""
    offered = list(draft.offered_slots or [])
    return len(offered) == 1 and _same_slot(offered[0], slot_iso)


# Any sentence that tells the lead a calendar invite exists or is coming. Run
# on the lower-cased body with all whitespace collapsed to single spaces, so a
# claim split across a line break still matches. Covers the engine's own
# wording ("invite on the way", "the invite is on your calendar", "the invite
# with the video link follows", draft.py's "I will send the invite over") and
# the ways Lorenzo would write it by hand in Edit.
_INVITE = r"(?:calendar )?invit(?:e|es|ation|ations)\b"
INVITE_CLAIM_RE = re.compile(
    r"\b" + _INVITE + r"[^.!?]{0,60}?\b(?:on (?:the|its|it's|it’s) way|coming|to follow|follows?|following|"
    r"shortly|soon|(?:is|are) on your calendar|on your calendar|in your inbox|went out|is out|has gone out|"
    r"(?:is|was|has been|have been|will be|gets?|got) (?:sent|out|over|coming|attached|headed|landing)|"
    r"headed your way|heading your way|landed)\b"
    r"|\b(?:send|sends|sending|sent|shoot|shooting|shot|email|emailing|emailed|forward|forwarding|forwarded|"
    r"drop|dropping|dropped|put|putting|added|adding|resend|re-send|resent|issue|issued)\b[^.!?]{0,40}?\b" + _INVITE +
    r"|\b(?:get|receive|see|expect|watch for|look out for|keep an eye out for)\b[^.!?]{0,30}?\b" + _INVITE)


def claims_invite(body: Optional[str]) -> bool:
    """True when the text tells the lead a calendar invite exists or is coming."""
    text = " ".join((body or "").lower().split())
    return bool(INVITE_CLAIM_RE.search(text))


def _invite_claim_problem(approval: Approval, state: Optional[LeadState]) -> Optional[str]:
    """A body that tells the prospect a calendar invite exists may only go out
    when a booking really exists for this card: one it owns, or one whose
    confirmation has already gone out."""
    if not claims_invite(approval.draft.body_text):
        return None
    booking = booking_of(state)
    if not booking.get("slot") or not any(_same_slot(iso, booking.get("slot"))
                                          for iso in approval.draft.offered_slots or []):
        return "the draft tells the lead a calendar invite exists, but there is no booking for this card"
    if booking.get("cancel_failed"):
        return ("the draft tells the lead a calendar invite exists, but that booking is being cancelled "
                "(the GHL cancel failed and is being retried)")
    if owns_booking(approval, state):
        return None
    if booking.get("owner") or booking.get("awaiting_approval"):
        return ("the draft tells the lead a calendar invite exists, but the booking belongs to another card "
                "that has not been approved")
    return None


def _interest_value_for(approval: Approval, state: Optional[LeadState]) -> Optional[int]:
    """The Instantly interest status an approved reply should leave behind.

    Never the hard-coded 1 it used to be: a booking confirmation would then
    overwrite the 2 (meeting_booked) booking.book() had just written, so every
    booked call showed up as merely 'interested' in Instantly and disagreed with
    the GHL opportunity sitting in Call Booked.
    """
    label = approval.label or ""
    if label == "booking_confirmation":
        return None
    booking = (getattr(state, "cadence", None) or {}).get("booking") or {} if state is not None else {}
    if booking.get("slot"):
        return None
    if label in INTEREST_FOR_LABEL:
        return INTEREST_FOR_LABEL[label]
    return 1


# ------------------------------------------------------------ card context
# What the card was raised against, written when it is created and read back
# by the send. Kept beside the card (like booking_intent: and booking_choice:)
# so the Approval model stays as it is.
#   email_id          the inbound the card answers
#   reply_at          when that inbound landed (the event's own received time):
#                     "time to first reply" is measured from it (OPS-10)
#   processed_before  the lead's processed_email_ids as the pipeline saw them
#                     when it raised the card, without the card's own email:
#                     every other id processed since is a reply this answer
#                     never saw, even while the card's own email is not yet
#                     recorded as processed (arm_refusal)
#   processed_count   len(processed_before), for reading the row by eye
# and the card's send history, which status alone cannot give (edit() and
# retry() put an approved or half-sent card back to pending):
#   tracks_history    True on every row written since the history existed; a
#                     row without it (or no row) proves nothing either way
#   approved_at       the first time Lorenzo approved the card (approve())
#   send_attempts     sends that may have reached Instantly and whose claim
#                     retry() has since dropped (the live claim row,
#                     approval_send_claim:<id>, counts as one more)
# The row is written BEFORE the card and a failure raises (re-review R1 item
# 4): a card without it would skip the crash-gap check in arm_refusal. It is
# deleted by expire_overdue's sweep once its card is sent, vetoed, superseded,
# gone, or expired with nothing left to decide (sweep_card_contexts).
APPROVAL_CONTEXT_PREFIX = "approval_context:"
# A card in one of these never reads its context again.
CONTEXT_DONE_STATUSES = SENT_STATUSES + ("vetoed", "superseded")


def record_card_context(store, approval_id: str, state: LeadState, event: ReplyEvent) -> Dict[str, Any]:
    """Write the card's context row. Raises when it cannot: create_approval
    calls it before the card exists, so a failure leaves no card behind."""
    own = str(event.email_id or "")
    before = [str(x) for x in (state.processed_email_ids or []) if str(x) != own]
    received = getattr(event, "received_at", None)
    rec = {"email_id": own, "reply_at": slots.to_tz(slots.ensure_aware(received)).isoformat() if received else None,
           "processed_before": before, "processed_count": len(before),
           "tracks_history": True, "approved_at": None, "send_attempts": 0}
    _store(store).set(APPROVAL_CONTEXT_PREFIX + approval_id, rec)
    return rec


def card_context(store, approval_id: str) -> Dict[str, Any]:
    """The card's context row, or {} (a card from before the row existed, or
    an unreadable store)."""
    try:
        rec = _store(store).get(APPROVAL_CONTEXT_PREFIX + approval_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not read the context of card %s: %s", approval_id, exc)
        return {}
    return rec if isinstance(rec, dict) else {}


def _note_card_history(st, approval_id: str, ts: datetime, approved: bool = False, send_attempts: int = 0,
                       actor: Optional[str] = None) -> None:
    """Add to the card's send history, under the context row's lock. Raises
    when the store does: the callers refuse rather than lose the record.
    ``actor``: who approved ("lorenzo" or "template"), recorded with the
    first approval."""

    def _add(current):
        rec = dict(current) if isinstance(current, dict) else {}
        if approved and not rec.get("approved_at"):
            rec["approved_at"] = ts.isoformat()
            if actor:
                rec["approved_by"] = actor
        if send_attempts:
            rec["send_attempts"] = int(rec.get("send_attempts") or 0) + int(send_attempts)
            rec["last_send_attempt_at"] = ts.isoformat()
        return rec

    key = APPROVAL_CONTEXT_PREFIX + approval_id
    mutate = getattr(st, "mutate", None)
    if callable(mutate):
        try:
            mutate(key, _add, default={})
            return
        except NotImplementedError:
            pass
    st.set(key, _add(st.get(key)))


def card_history(st, approval: Approval, status: Optional[str] = None) -> Dict[str, Any]:
    """What the store can PROVE about this card's past, for any text that
    tells Lorenzo what happened to it (the expiry push, the Keep / Release
    pages). ``status`` is the status to judge by (the one the card had before
    it expired); defaults to the card's own.

    ``approved`` and ``send_started`` are True (proved), False (proved not)
    or None (unknown: the card predates the history, or the store could not
    be read). Text may say "never approved" or "nothing was sent" only on a
    proved False."""
    approval_id = _approval_id(approval)
    status = status or approval.status
    ctx = card_context(st, approval_id)
    tracked = ctx.get("tracks_history") is True
    try:
        claim = st.get(SEND_CLAIM_PREFIX + approval_id)
        claim_known = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not read the send claim of %s: %s", approval_id, exc)
        claim, claim_known = None, False
    # Every one of these is reached only through approve() (send_approved and
    # its holds, and Mark sent, which only a send_failed or sending card
    # reaches), so the status alone proves an approval.
    approved_statuses = ("approved_queued", "blocked", "stale_slots", "send_failed", "sending") + SENT_STATUSES
    if claim or ctx.get("approved_at") or status in approved_statuses:
        approved = True  # type: Optional[bool]
    elif tracked and claim_known:
        approved = False
    else:
        approved = None
    attempts = int(ctx.get("send_attempts") or 0) + (1 if claim else 0)
    if attempts or status in ("send_failed", "sending") + SENT_STATUSES:
        send_started = True  # type: Optional[bool]
    elif tracked and claim_known:
        send_started = False
    else:
        send_started = None
    first_claim = claim[0] if isinstance(claim, list) and claim else claim
    claimed_at = first_claim.get("at") if isinstance(first_claim, dict) else None
    return {"approved": approved, "approved_at": ctx.get("approved_at"), "send_started": send_started,
            "send_attempts": attempts, "send_claim": bool(claim),
            "last_send_attempt_at": claimed_at or ctx.get("last_send_attempt_at"),
            "status": status, "tracked": tracked}


def history_sentence(history: Dict[str, Any]) -> str:
    """One plain sentence on whether a reply may have left this card. Says
    "nothing was sent" only when card_history proved it."""
    if history.get("send_started") is False:
        return "No reply has been sent from this card."
    if history.get("send_started"):
        return ("A send from this card was started (%s) and may have reached the lead: check the Instantly thread "
                "before you do anything else." % (history.get("last_send_attempt_at") or "time not recorded"))
    return ("The engine has no send record for this card (it predates that record), so it cannot say whether a "
            "reply went out: check the Instantly thread before you do anything else.")


# ------------------------------------------------------------ lifecycle
def create_approval(
    state: LeadState,
    draft: Draft,
    event: ReplyEvent,
    store=None,
    now: Optional[datetime] = None,
    notify_fn=None,
    requested: Optional[Dict[str, Any]] = None,
    campaign_key: Optional[str] = None,
    auto: Any = None,
) -> Approval:
    """``requested`` = {"slot", "status", "lead_tz"} when the lead asked for a
    specific time that only Lorenzo's own slot rule blocks. The draft still
    counter-proposes, but the card adds a "Book <time> as asked" action so the
    choice is his instead of the engine's.

    ``auto`` is the template gate's verdict on this draft
    (template_gate.draft_verdict, CT3). Allowed (for this draft's template,
    with no problem on the draft): no push now; notify_result is
    {"deferred": "template_auto_send"} and the caller runs
    auto_send_approved next. Refused: the card is pushed with a "Not
    auto-sent: <reason>" line. Either way the card stores the verdict record
    (auto_send). None: the card is pushed as before."""
    st = _store(store)
    ts = _now(now)
    # Fail closed before anything is persisted: in live, a card nobody can act
    # on is worse than no card, because poller.pending_approvals reports it as
    # pushed and the push_failed alarm never fires. base_url() is checked here
    # too, not only inside action_urls below: that call used to come after the
    # approval was stored and its slots reserved, so a missing BASE_URL left a
    # card in the store that no push ever carried.
    channels = require_deliverable_channel()
    base_url()
    approval_id = secrets.token_hex(8)
    expires_at = (ts + timedelta(hours=TTL_HOURS)).isoformat()
    # The draft's times were picked from a registry read made earlier in the
    # pipeline. Claimed atomically here, before the card exists: a time another
    # lead's card (or call) took in the meantime is never offered twice. The
    # card is still raised, with a problem that blocks the send until Edit
    # offers other times (SAL-10).
    try:
        taken = claim_slots(st, state.lead_email, list(draft.offered_slots or []), ts,
                            fields={"approval": approval_id})
    except Exception as exc:  # noqa: BLE001 - an unreadable registry holds the card rather than double-offer
        logger.warning("could not claim the draft's slots for %s: %s", state.lead_email, exc)
        taken = list(draft.offered_slots or [])
    if taken:
        draft.problems = list(draft.problems or []) + [
            "%s %s already held for another lead's card or call; use Edit to offer other times"
            % (", ".join(_slot_label(iso) for iso in taken), "is" if len(taken) == 1 else "are")]
    token = make_token(approval_id, state.key, draft_hash(draft), expires_at)
    approval = Approval(
        token=token,
        state_key=state.key,
        lead_email=state.lead_email,
        campaign_id=state.campaign_id,
        campaign_key=campaign_key or state.campaign_key,
        email_id=event.email_id,
        eaccount=event.eaccount or state.eaccount,
        reply_to=event.reply_to_address,
        draft=draft,
        status="pending",
        created_at=ts.isoformat(),
        expires_at=expires_at,
        label=draft.label,
        requested_slot=(requested or {}).get("slot"),
        requested_status=(requested or {}).get("status"),
        requested_lead_tz=(requested or {}).get("lead_tz"),
        lead_reply=lead_reply_excerpt(getattr(event, "text", None)),
    )
    # The context row first, and fail closed (re-review R1 item 4): a card
    # with no context skips arm_refusal's crash-gap check, so a newer reply
    # could be missed and the ladder armed over it. Nothing is left behind:
    # the slots this card just claimed go back before the error propagates.
    try:
        context = record_card_context(st, approval_id, state, event)
    except Exception:
        release_slots(st, approval_id)
        logger.exception("could not record the context of a card for %s; no card raised", state.lead_email)
        raise
    locked = _template_draft_only(draft.template_id, state)
    deferred, note = _auto_decision(auto, draft, state)
    if auto is not None:
        approval.auto_send = _auto_record(auto, state)
        if locked:
            # The stored reason is the lock, whatever the gate said (kept
            # beside it as gate_reason).
            approval.auto_send = dict(approval.auto_send, allowed=False, reason=FIRST_REPLY_LOCK_REASON,
                                      gate_reason=approval.auto_send.get("reason"))
    if deferred:
        # Nothing is pushed now: the pipeline calls auto_send_approved next,
        # and every way that ends short of a send or a queue pushes the card
        # then (push_orphaned_deferred when it never runs).
        approval.notify_result = {"deferred": DEFERRED_AUTO_SEND, "deferred_at": ts.isoformat(),
                                  "channels": channels}
    st.set(APPROVAL_PREFIX + approval_id, approval.model_dump(mode="json"))
    state.approvals.append(token)

    if not deferred:
        push_card(approval, st, state, notify_fn=notify_fn, note=note)
    job_log.log_run("reply_engine.approval", "created", {"lead": state.lead_email, "campaign_id": state.campaign_id, "approval": approval_id,
                                                        "label": draft.label, "slots": draft.offered_slots,
                                                        "reply_at": context.get("reply_at"),
                                                        "template_id": draft.template_id, "auto": deferred,
                                                        "auto_reason": FIRST_REPLY_LOCK_REASON if locked else None})
    return approval


# ------------------------------------------------------ CT3: auto-send
# notify_result["deferred"] on a card whose push waits on auto_send_approved.
DEFERRED_AUTO_SEND = "template_auto_send"
# notify_result key: when auto_send_approved took the card (its claim).
AUTO_SEND_CLAIM_KEY = "auto_send_claimed_at"
# notify_result key: the deferred push that went out instead ({"at", "note"}).
DEFERRED_PUSHED_KEY = "deferred_pushed"
# How long an auto-send's claim keeps the orphan sweep off its card: the send
# lease, after which nothing can still be running it.
AUTO_SEND_CLAIM_MINUTES = 10
ORPHAN_NOTE = "Not auto-sent: the auto-send did not run (the engine stopped between the card and the send)."
# Outcomes of a template send that count as auto-sent (one FYI line each).
AUTO_SENT_STATUSES = ("sent", "approved_queued")
# Outcomes of a template send that leave the card for Lorenzo: pushed.
AUTO_PUSH_STATUSES = ("pending", "blocked", "stale_slots")


# What a "Not auto-sent" card line says for each gate reason code
# (template_gate.REASONS) and the pipeline's own codes: one plain sentence
# Lorenzo can act on, never any lead data. The card's stored record
# (auto_send) keeps the code. An unknown code is shown as itself.
REASON_TEXT = {
    "ok": "the template gate allowed it.",
    "kill_switch": "template auto-send is switched off (the kill switch).",
    "parity_failed": ("the deployed templates do not match the approved catalogue (parity check); nothing "
                      "auto-sends until the deploy is fixed."),
    "no_template": "this draft was not written from a catalogue template.",
    "not_template_render": "this draft is not the plain template text (it was polished or edited).",
    "unknown_id": "its template is not in the catalogue for this kind of email.",
    "unapproved": "its template is not approved yet; approve it in the emails doc, then tell Claude \"done\".",
    "changed_since_approval": ("its template changed since you approved it; review it and approve it again in the "
                               "emails doc, then tell Claude \"done\"."),
    # FIRST_REPLY_LOCK_REASON: Lorenzo's rule, checked before the gate.
    "first_reply_draft_only": "first replies are drafts you send yourself from the thread.",
    "not_approvable": "its template cannot be approved for auto-send.",
    "stale_render": "the template changed after this draft was written.",
    "classification": "the reply was not read as a clear positive with enough confidence.",
    "requested_override": ("the lead asked for a time outside your slot rule; choose the counter-proposal or "
                           "Book as asked."),
    "copy_gate": "the draft failed a copy check (a banned word, a figure or a link).",
    "nonconforming": "the text is not exactly the approved template with valid values filled in.",
    "registry_error": "the template check could not run, so it was treated as not approved.",
    "cancel_pending": "the lead's previous call is still being cancelled in GHL; check the calendar before sending.",
    # A template send that ended at send_failed (_after_template_send).
    "send_failed": ("the send to Instantly failed, so the reply may or may not have gone out; check the thread in "
                    "Instantly before you press anything."),
    "recipient_mismatch": ("the thread's last message is from somebody other than the lead, so nothing was sent; "
                           "check the thread in Instantly."),
    "recipient_unconfirmed": ("the thread could not be re-read to confirm the lead wrote it, so nothing was sent; "
                              "check the thread in Instantly."),
    "send_raised": ("the send stopped on an error, so the reply may or may not have gone out; check the thread in "
                    "Instantly before you press anything."),
}
# Statuses a template send can end in that are pushed as the "send failed"
# card (push_card's recovery variant): Retry / Veto / Mark sent, never
# Approve, which a send_failed card refuses.
FAILED_PUSH_STATUSES = ("send_failed",)
# Statuses Veto takes (veto(): anything not sent and not sending). Closed
# cards (vetoed, expired, superseded, sent_manually) get no Veto link.
VETO_LINK_STATUSES = ("pending", "approved_queued", "blocked", "stale_slots", "send_failed")


def reason_text(code: Any) -> str:
    """The plain sentence for a "Not auto-sent" reason code (REASON_TEXT),
    or the code itself when there is none."""
    key = str(code or "").strip()
    return REASON_TEXT.get(key, key or "not sent")


def _not_auto_sent(code: Any) -> str:
    return "Not auto-sent: %s" % reason_text(code)


def _gate():
    from services.reply_engine import template_gate
    return template_gate


def auto_kind(template_id: Optional[str]) -> Optional[str]:
    """The gate kind of a card's template id ("first_reply" or "booking",
    from its first segment), or None for anything else."""
    head = str(template_id or "").split(".", 1)[0]
    return head if head in ("first_reply", "booking") else None


# Lorenzo's rule (2026-09-23): first replies are never auto-sent. The engine
# drafts the first reply (two held times, no booking link) and he sends it
# himself from the thread; the engine sees his send as day 0. A first_reply.*
# draft is always an approval card, whatever the approvals file, the kill
# switch or the template gate say, and so is any other reply to a lead we have
# not answered yet, except a booking confirmation (draft_only, same reason
# and text; Lorenzo, 2026-09-23). Checked before the gate's verdict at every
# point a card can go out with no tap: create_approval (_auto_decision),
# auto_send_approved, send_approved's re-check of a "template" card
# (_template_verdict) and the old timer path (auto_send_due).
FIRST_REPLY_LOCK_REASON = "first_reply_draft_only"
# A gate refusal a locked first reply's card still shows after the lock's
# line: something to check before Lorenzo sends it himself.
LOCK_KEEPS_REASONS = ("cancel_pending",)


def first_reply_locked(template_id: Optional[str]) -> bool:
    """True for a first reply's template id (first segment "first_reply",
    read case- and space-insensitively so a look-alike id fails closed):
    never auto-sent (FIRST_REPLY_LOCK_REASON)."""
    return str(template_id or "").strip().lower().split(".", 1)[0] == "first_reply"


# The one kind of reply that still auto-sends to a lead we have not answered
# yet: the confirmation of a call their own time booked (Lorenzo, 2026-09-23).
UNANSWERED_ALLOWED_PREFIX = "booking.confirmation."


def draft_only(template_id: Optional[str], state: Any) -> bool:
    """Lorenzo's rule: never auto-sent, always a card he sends himself
    (FIRST_REPLY_LOCK_REASON). True for a first reply's template, and for
    any other reply except a booking confirmation while no reply of ours
    has reached the lead yet (_is_first_reply on ``state``: a LeadState, a
    stored lead row, or None when the row could not be read, which counts
    as not answered yet). The one check every no-tap send path runs."""
    if first_reply_locked(template_id):
        return True
    if str(template_id or "").strip().lower().startswith(UNANSWERED_ALLOWED_PREFIX):
        return False
    try:
        if isinstance(state, dict):
            state = LeadState.from_store(state)
        return _is_first_reply(state if isinstance(state, LeadState) else None)
    except Exception:  # noqa: BLE001 - an unreadable row is not answered yet
        return True


def _template_draft_only(template_id: Optional[str], state: Any) -> bool:
    """draft_only for a template render. A draft with no template id is
    never auto-sent anyway, and keeps the gate's own "Not auto-sent" line."""
    return bool(str(template_id or "").strip()) and draft_only(template_id, state)


# A first-contact card (Lorenzo, 2026-09-23): a reply to a lead nothing of
# ours has reached yet, which he sends himself from the Instantly thread. Its
# card has no Approve and no Edit: Mark sent (from pending, first_contact
# cards only: mark_sent_manually) and Veto, and Book as asked as before.
SEND_YOURSELF_LINE = "Send this yourself from the thread in Instantly, then tap Mark sent."
# Between the lead's reply and the draft on a card that shows both.
DRAFT_RULE = "----------"
DRAFT_HEAD_YOURSELF = "Your reply, to send yourself from the thread:"
DRAFT_HEAD_APPROVE = "Your reply (Approve sends it):"


def first_contact(template_id: Optional[str], state: Any) -> bool:
    """True while the lead is not answered yet (draft_only's rule and its
    fail-closed read of ``state``: a LeadState, a stored lead row, or None
    when it could not be read), for any draft but a booking confirmation
    (UNANSWERED_ALLOWED_PREFIX). A draft with no template id counts."""
    if str(template_id or "").strip().lower().startswith(UNANSWERED_ALLOWED_PREFIX):
        return False
    return draft_only(None, state)


def pending_mark_sent_ok(card: Any, store=None) -> bool:
    """Mark sent takes a pending card only when it is a first-contact card
    (first_contact on its lead row as stored now; a row that cannot be read
    counts as not answered yet). Every other pending card is refused, as
    before."""
    if isinstance(card, dict):
        card = Approval.model_validate(card)
    if getattr(card, "status", None) != "pending":
        return False
    return first_contact(card.draft.template_id, _stored_row(_store(store), card.state_key))


def mark_sent_takes(card: Any, store=None) -> bool:
    """Does Mark sent take this card at its status: MARK_SENT_FROM, or a
    pending first-contact card (pending_mark_sent_ok)? mark_sent_manually
    runs its own checks after this one."""
    status = card.get("status") if isinstance(card, dict) else getattr(card, "status", None)
    if status in MARK_SENT_FROM:
        return True
    try:
        return pending_mark_sent_ok(card, store)
    except Exception as exc:  # noqa: BLE001 - unknown: refused
        logger.warning("could not tell whether Mark sent takes a pending card: %s", exc)
        return False


# The lead's reply as a card shows it (Approval.lead_reply).
LEAD_REPLY_MAX_CHARS = 1500
LEAD_REPLY_CUT = "\n[cut: the rest is in the Instantly thread]"


def lead_reply_excerpt(text: Any) -> Optional[str]:
    """What the lead wrote, for the card: quoted history cut
    (classify.strip_quoted; the raw text when that leaves nothing, a
    bottom-posted reply), capped at LEAD_REPLY_MAX_CHARS with the cut
    marked. None when there is no text."""
    raw = str(text or "").replace("\r\n", "\n").strip()
    if not raw:
        return None
    try:
        from services.reply_engine import classify
        top = classify.strip_quoted(raw)
    except Exception:  # noqa: BLE001 - the raw text beats no text
        top = raw
    top = (top or raw).strip()
    if len(top) > LEAD_REPLY_MAX_CHARS:
        top = top[:LEAD_REPLY_MAX_CHARS].rstrip() + LEAD_REPLY_CUT
    return top


def _stored_row(st, state_key: Optional[str]) -> Optional[Dict[str, Any]]:
    """The lead row for draft_only, or None when it cannot be read."""
    try:
        row = st.get(state_key) if state_key else None
        return row if isinstance(row, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _auto_decision(auto: Any, draft: Draft, state: Any = None):
    """(deferred, note) for create_approval: deferred only for an allowed
    verdict on this very draft (its template id), a template render with no
    problem on it (create_approval adds one when a time was taken meanwhile)
    and a template kind this module sends. ``note`` is the card's "Not
    auto-sent" line when a verdict was given and it is not deferred. A draft
    Lorenzo sends himself (draft_only on ``state``, the lead) is never
    deferred, whatever the verdict, and its card says so."""
    if _template_draft_only(getattr(draft, "template_id", None), state):
        note = _not_auto_sent(FIRST_REPLY_LOCK_REASON)
        refused = getattr(auto, "reason", None) if auto is not None and not getattr(auto, "allowed", False) else None
        if refused in LOCK_KEEPS_REASONS:
            note = "%s Also, %s" % (note, reason_text(refused))
        return False, note
    if auto is None:
        return False, None
    try:
        if not getattr(auto, "allowed", False):
            return False, _not_auto_sent(getattr(auto, "reason", None) or "registry_error")
        if getattr(auto, "template_id", None) != draft.template_id or auto_kind(draft.template_id) is None:
            return False, "Not auto-sent: the template check was for another draft."
        if draft.model != "template":
            return False, _not_auto_sent("not_template_render")
        if draft.problems:
            return False, "Not auto-sent: the draft has a problem to fix first (see VALIDATION)."
        return True, None
    except Exception as exc:  # noqa: BLE001 - any doubt is a card
        logger.warning("could not read the auto-send verdict: %s", exc)
        return False, _not_auto_sent("registry_error")


def _auto_record(auto: Any, state: Optional[LeadState]) -> Dict[str, Any]:
    """What the card stores of the verdict: Verdict.to_record() (ids,
    statuses and the reason, never text), plus the classification it was
    judged on, which send_approved's re-check judges again."""
    try:
        rec = dict(auto.to_record())
    except Exception:  # noqa: BLE001
        rec = {"allowed": False, "reason": "registry_error"}
    cls = getattr(state, "classification", None) if state is not None else None
    if cls is not None:
        rec["classification"] = {"label": getattr(cls, "label", None), "confidence": getattr(cls, "confidence", None),
                                 "method": getattr(cls, "method", None)}
    return rec


def push_card(approval: Approval, st, state: Optional[LeadState], notify_fn=None,
              note: Optional[str] = None) -> Dict[str, Any]:
    """Push the approval card to Lorenzo (Approve / Veto / Edit, and Book as
    asked for a requested time) and record the result on the stored card.
    A card at send_failed (FAILED_PUSH_STATUSES, a template send that
    failed) is pushed as the recovery card instead (_failed_card_push:
    Retry / Veto / Mark sent, no lead data on a public topic). An ordinary
    card on a public topic is titled by its classification only and names no
    one; the full card goes to the email leg (_public_card_push).
    ``note`` is a first line ("Not auto-sent: <reason>"). ``state`` is the
    lead (its name and company title the card on a protected topic); None reads it from the
    store. Returns the notify_result written. Never raises for a failed
    push: an unpushed card writes a push_failed Job_Log row."""
    st = _store(st)
    approval_id = _approval_id(approval)
    if state is None:
        try:
            raw = st.get(approval.state_key)
            state = LeadState.from_store(raw) if raw else None
        except Exception as exc:  # noqa: BLE001 - the card still goes out, titled by its address
            logger.warning("could not read the lead behind card %s: %s", approval_id, exc)
            state = None
    channels = deliverable_channels()
    draft = approval.draft
    lead_email = approval.lead_email
    first = getattr(state, "first_name", None) if state is not None else None
    company = getattr(state, "company", None) if state is not None else None
    urls = action_urls(approval.token)
    who = " ".join(p for p in (first, company) if p) or lead_email
    # A first-contact card (first_contact on the lead as read above; None,
    # unreadable, counts as not answered yet): Lorenzo sends it himself, so
    # Mark sent replaces Approve and Edit, and a tap opens Mark sent.
    fresh = first_contact(draft.template_id, state)
    mark_url = None  # type: Optional[str]
    if fresh:
        mark_url = "%s/mark-sent/%s" % (base_url(), approval.token)
        title = "Reply to send yourself: %s (%s)" % (who, draft.label or "positive")
        actions = [("Mark sent", mark_url), ("Veto", urls["veto"])]
    else:
        title = "Reply to approve: %s (%s)" % (who, draft.label or "positive")
        actions = [("Approve", urls["approve"]), ("Veto", urls["veto"]), ("Edit", urls["edit"])]
    problems = ("\nVALIDATION: " + "; ".join(draft.problems)) if draft.problems else ""
    rationale = ("\nNote: " + draft.rationale) if draft.rationale else ""
    asked = ""
    if approval.requested_slot:
        label = _slot_label(approval.requested_slot)
        asked = "\nThey asked for %s, which is outside your slot rule (%s). Counter-proposal drafted above.\nBook as asked: %s" % (
            label, approval.requested_status, urls["accept"])
        actions.append(("Book %s" % label, urls["accept"]))
    # The action URLs stay in the ntfy Actions header (buttons Lorenzo taps) and
    # out of the message body: the body is mirrored into the Gmail copy, where a
    # safe-link scanner would fetch every URL in it. GET /approve only renders a
    # confirmation page now, so following one cannot send anything. The push
    # itself is a guarded write inside shared.notify (shadow records a would_do).
    # What the lead wrote goes above the draft, and the draft is labelled as
    # the text Lorenzo sends. Lead text: the email leg and a protected topic
    # only (_public_card_push keeps it off a public one).
    body = draft.body_text
    if approval.lead_reply:
        body = "They wrote:\n%s\n\n%s\n%s\n%s" % (
            approval.lead_reply, DRAFT_RULE,
            DRAFT_HEAD_YOURSELF if fresh else DRAFT_HEAD_APPROVE, draft.body_text)
    message = "%s <%s>\nReply to: %s\nSubject: %s\nSlots: %s%s%s\n\n%s%s" % (
        who, lead_email, approval.reply_to or lead_email, draft.subject,
        ", ".join(draft.offered_slots) or "none", problems, rationale, body, asked)
    card_text = message
    if note:
        message = "%s\n%s" % (note, message)
    if fresh:
        message = "%s\n%s" % (SEND_YOURSELF_LINE, message)
    kwargs = {"priority": "high", "actions": actions, "tags": ["email", "reply-engine"],
              "click": mark_url if fresh else urls["approve"]}  # type: Dict[str, Any]
    if approval.status in FAILED_PUSH_STATUSES:
        title, message, kwargs = _failed_card_push(approval, st, who, draft.label, card_text, note)
    elif not _topic_protected():
        title, message, kwargs = _public_card_push(draft.label, message, kwargs, note,
                                                   bool(approval.requested_slot), fresh=fresh)
    fn = notify_fn or notify.notify
    try:
        result = stored_notify_result(fn(title, message, **kwargs))
    except Exception as exc:  # noqa: BLE001
        logger.warning("notify failed: %s", exc)
        result = {"sent": False, "errors": ["notify raised: %s" % exc]}
    # notify() swallows its own ntfy/SMTP errors and returns sent=False, so the
    # try/except above never fires for the common failure. An unpushed card is a
    # positive reply sitting in the store that nobody will ever look at.
    # "sent" alone is not delivery. With an unprotected ntfy topic and no email
    # leg, notify() strips the Actions/Click headers, appends "(details in the
    # email)" that no email carries, and still answers sent=True.
    actionable = bool(channels.get("any")) or bool(result.get("test") or result.get("shadow"))
    result = dict(result, channels=channels, actionable=actionable)
    approval.notify_result = dict(approval.notify_result or {}, **result) if isinstance(
        approval.notify_result, dict) else result
    if not (result.get("sent") or result.get("test") or result.get("shadow")) or not actionable:
        why = result.get("errors") or ("no channel can carry the Approve/Veto buttons: %s" % channels)
        logger.error("approval %s for %s was NOT pushed: %s", approval_id, lead_email, why)
        job_log.log_run("reply_engine.approval", "push_failed",
                        {"lead": lead_email, "approval": approval_id, "errors": why, "channels": channels})
    # Only notify_result is written back, onto the card as it is stored NOW
    # (re-review R1 item 3): the push is a round trip, and Lorenzo can tap
    # Approve on it before it returns. Saving the whole copy read before the
    # push turned that "sent" back into "pending".
    _record_notify_result(st, APPROVAL_PREFIX + approval_id, result)
    return result


def recovery_links(card: Any, store=None, now: Optional[datetime] = None, mark_sent: bool = True) -> Dict[str, Any]:
    """The signed links a card that is not moving can take right now, for a
    push that tells Lorenzo what to press. Each is None when that action
    does not take the card:

    * ``retry``: RETRYABLE_STATUSES, and retry_refusal has nothing against
      it (a sending card whose send may still be running waits);
    * ``veto``: VETO_LINK_STATUSES (veto() refuses a sent or sending card);
    * ``edit``: Edit takes the card as it is (SENDABLE_STATUSES, blocked);
    * ``edit_after_retry``: the same Edit link, for a card Edit refuses now
      and Retry puts back to pending (the link works once Retry has);
    * ``mark_sent``: mark_sent_url (never for a card held for its recipient,
      nor for a sending card inside its lease); not built when the
      ``mark_sent`` argument is False (the stuck push builds its own button).

    ``held`` is the card's recipient hold (recipient_held), or None.
    ``card`` is an Approval or a stored card row. Raises when the links
    cannot be built (base_url() in live with no BASE_URL): the caller says
    so in its push."""
    if isinstance(card, dict):
        card = Approval.model_validate(card)
    status = card.status
    urls = action_urls(card.token)
    retry_ok = False
    if status in RETRYABLE_STATUSES:
        try:
            retry_ok = retry_refusal(card, store, now) is None
        except Exception as exc:  # noqa: BLE001 - unknown: no Retry link (retry() refuses it too)
            logger.warning("no Retry link for %s: %s", _approval_id(card), exc)
    try:
        held = recipient_held(card, store)
    except Exception as exc:  # noqa: BLE001 - unknown: treated as held, so no Mark sent (fail closed)
        logger.warning("could not read the recipient hold of %s: %s", _approval_id(card), exc)
        held = {"reason": "unreadable"}
    mark = None
    if mark_sent and status in MARK_SENT_FROM and not held:
        try:
            mark = mark_sent_url(card, store=store, now=now)
        except Exception as exc:  # noqa: BLE001 - unknown: no Mark sent link (the page refuses it too)
            logger.warning("no Mark sent link for %s: %s", _approval_id(card), exc)
            mark = None
    editable = status in SENDABLE_STATUSES + ("blocked",)
    return {"retry": urls["retry"] if retry_ok else None,
            "veto": urls["veto"] if status in VETO_LINK_STATUSES else None,
            "edit": urls["edit"] if editable else None,
            "edit_after_retry": urls["edit"] if (retry_ok and not editable) else None,
            "mark_sent": mark, "held": held}


def _failed_card_push(approval: Approval, st, who: str, label: Optional[str], full: str,
                      note: Optional[str]):
    """``(title, message, kwargs)`` for a card whose send ended at
    send_failed (FAILED_PUSH_STATUSES): it cannot be approved, so its
    buttons are what does take it (recovery_links): Retry, Veto and Mark
    sent where each is allowed, else Edit, at most three (ntfy's limit). An
    Edit link that did not fit, or that works only after Retry, is in the
    email leg's text. No click: a tap on the push opens nothing.

    ``full`` is the ordinary card text (lead, subject, body). The public
    ntfy topic (no NTFY_TOKEN / NTFY_ALLOW_SENSITIVE) gets the "Not
    auto-sent" line and what to do only: no name, address, company, subject,
    body or link, and shared.notify strips the buttons there. The full text
    and the links go to the email leg (``email_message``, and the buttons,
    which shared.notify renders as lines), and to a protected topic."""
    lead_email = approval.lead_email
    try:
        links = recovery_links(approval, st)
    except Exception as exc:  # noqa: BLE001 - base_url() fails closed in live; the push still goes out
        logger.warning("card %s for %s carries no links: %s", _approval_id(approval), lead_email, exc)
        links = {}
    held = links.get("held") if links else None
    steps = ["Nothing will send it on its own. Check the thread in Instantly first."]
    if links.get("mark_sent"):
        steps.append("If the reply did go out, press Mark sent (a Retry would send it a second time).")
    elif held:
        steps.append("Mark sent is not available: it was held because the recipient could not be confirmed, so "
                     "nothing reached Instantly.")
    if links.get("retry"):
        steps.append("%s, press Retry: the card goes back to pending%s, then Approve it, or Edit it first (Edit "
                     "works once it is pending; the Retry page links to it)."
                     % ("If the thread is the lead's" if held else "If it did not go out",
                        " and its next send checks the thread again" if held else ""))
    if links.get("veto"):
        steps.append("Veto drops it; then reply by hand from the Instantly inbox if you want to.")
    if not links:
        steps.append("BASE_URL is unset, so this card carries no links. Open the thread in the Instantly inbox and "
                     "reply by hand.")
    actions = []  # type: List[Any]
    for key, name in (("retry", "Retry"), ("veto", "Veto"), ("mark_sent", "Mark sent"), ("edit", "Edit")):
        if links.get(key) and len(actions) < 3:
            actions.append((name, links[key]))
    extra = []  # type: List[str]
    used = set(url for _, url in actions)
    edit = links.get("edit") or links.get("edit_after_retry")
    if edit and edit not in used:
        extra.append("Edit%s: %s" % (" (after Retry)" if links.get("edit_after_retry") else "", edit))
    head = "%s\n%s" % (note or "Not sent.", "\n".join(steps))
    title = "Reply to approve: %s (%s, not sent)" % (who, label or "positive")
    email_message = "%s\n\n%s" % (head, full)
    if extra:
        email_message = "%s\n\n%s" % (email_message, "\n".join(extra))
    kwargs = {"priority": "high", "actions": actions or None, "tags": ["warning", "reply-engine"],
              "click": None}  # type: Dict[str, Any]
    if _topic_protected():
        return title, email_message, kwargs
    public = "%s\nThe card, with its links, is in the email." % head
    kwargs["email_message"] = email_message
    return "Reply to approve: a reply was not sent", public, kwargs


def _label_words(label: Optional[str]) -> str:
    """A card's draft label as words ("positive_question" -> "positive
    question"), for a title that names no one."""
    return str(label or "positive").replace("_", " ")


def _public_card_push(label: Optional[str], full: str, kwargs: Dict[str, Any], note: Optional[str],
                      asked: bool, fresh: bool = False):
    """``(title, message, kwargs)`` for an ordinary card on the public ntfy
    topic (no NTFY_TOKEN / NTFY_ALLOW_SENSITIVE), the rule _failed_card_push
    follows: the title names the classification only, and the push carries
    the "Not auto-sent" line and what to do, with no name, address, company,
    subject, body or link (shared.notify redacts addresses and links only,
    so the lead's first name and company used to reach the topic in the
    title). ``full`` is the ordinary card text; it and the buttons (which
    shared.notify renders as lines) go to the email leg (``email_message``).
    A protected topic keeps the ordinary card. A first-contact card
    (``fresh``) is titled and worded as one Lorenzo sends himself, with the
    same redaction."""
    lines = [SEND_YOURSELF_LINE] if fresh else []
    if note:
        lines.append(note)
    if not fresh:
        lines.append("A reply is waiting for your approval: Approve, Veto or Edit it.")
    if asked:
        lines.append("They asked for a time outside your slot rule; Book as asked is on the card.")
    lines.append("The card, with its links, is in the email.")
    kwargs = dict(kwargs, email_message=full)
    return ("Reply to send yourself: %s" if fresh else "Reply to approve: %s") % _label_words(label), \
        "\n".join(lines), kwargs


def _topic_protected() -> bool:
    """shared.notify's own test for a topic that may carry lead data and
    links; False when it cannot be read (the public text goes out)."""
    try:
        return bool(notify.topic_is_protected())
    except Exception:  # noqa: BLE001
        return False


def _claim_deferred_push(st, approval_id: str, ts: datetime, note: str, orphan_only: bool = False,
                         statuses: Optional[tuple] = None) -> bool:
    """Take the one push a deferred card is owed, under the card's lock:
    True for exactly one caller, which then pushes it. The claim removes
    ``deferred`` and records DEFERRED_PUSHED_KEY. ``orphan_only`` (the
    sweep): only a pending card no auto-send holds (no claim, or one older
    than AUTO_SEND_CLAIM_MINUTES). ``statuses``: only a card in one of them
    as stored now (a send_failed push is never taken for a card Mark sent or
    Retry moved meanwhile)."""
    box = {"won": False}

    def _take(current):
        if not isinstance(current, dict):
            return current
        nr = current.get("notify_result")
        if not isinstance(nr, dict) or not nr.get("deferred"):
            return current
        if statuses is not None and current.get("status") not in statuses:
            return current
        if orphan_only:
            if current.get("status") != "pending" or _auto_claim_fresh(nr, ts):
                return current
        out = dict(current)
        new = dict(nr)
        new.pop("deferred", None)
        new[DEFERRED_PUSHED_KEY] = {"at": ts.isoformat(), "note": note}
        out["notify_result"] = new
        box["won"] = True
        return out

    _mutate_card(st, APPROVAL_PREFIX + approval_id, _take)
    return box["won"]


def _auto_claim_fresh(nr: Dict[str, Any], ts: datetime) -> bool:
    at = nr.get(AUTO_SEND_CLAIM_KEY)
    if not at:
        return False
    try:
        return slots.parse_iso(at) > ts - timedelta(minutes=AUTO_SEND_CLAIM_MINUTES)
    except (ValueError, TypeError):
        return False


def _push_deferred(st, approval_id: str, ts: datetime, note: str, notify_fn=None,
                   orphan_only: bool = False, statuses: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
    """Push a deferred card once (_claim_deferred_push), from the card as
    stored. None when there was nothing to push (already pushed, not a
    deferred card, or not in ``statuses``). Never raises."""
    try:
        if not _claim_deferred_push(st, approval_id, ts, note, orphan_only=orphan_only,
                                    **({"statuses": statuses} if statuses is not None else {})):
            return None
        card = _approval_row(st, approval_id)
        if card is None:
            return None
        return push_card(card, st, None, notify_fn=notify_fn, note=note)
    except Exception as exc:  # noqa: BLE001 - the digest and the SLA chase still list the card
        logger.exception("could not push deferred card %s: %s", approval_id, exc)
        job_log.log_run("reply_engine.approval", "push_failed",
                        {"approval": approval_id, "errors": "deferred push raised: %s" % exc})
        return {"sent": False, "errors": ["deferred push raised: %s" % exc]}


def _claim_auto_send(st, approval_id: str, ts: datetime) -> bool:
    """auto_send_approved's claim on its card, under the card's lock: only a
    pending card still waiting on its deferred push, that no other
    auto-send holds. The orphan sweep leaves a claimed card alone for
    AUTO_SEND_CLAIM_MINUTES."""
    box = {"won": False}

    def _take(current):
        if not isinstance(current, dict) or current.get("status") != "pending":
            return current
        nr = current.get("notify_result")
        if not isinstance(nr, dict) or not nr.get("deferred") or _auto_claim_fresh(nr, ts):
            return current
        out = dict(current)
        out["notify_result"] = dict(nr, **{AUTO_SEND_CLAIM_KEY: ts.isoformat()})
        box["won"] = True
        return out

    _mutate_card(st, APPROVAL_PREFIX + approval_id, _take)
    return box["won"]


def _outcome_reason(out: Dict[str, Any]) -> str:
    """The "Not auto-sent" reason of a template send that did not go out: a
    gate code's sentence (REASON_TEXT), the problems the card carries, or
    what the send said."""
    if out.get("reason"):
        return reason_text(out["reason"])
    if out.get("problems"):
        return "; ".join(str(p) for p in out["problems"])
    if out.get("stale_slots"):
        return "the offered times are no longer offerable"
    return str(out.get("error") or out.get("status") or "not sent")


def _failed_send_code(out: Dict[str, Any]) -> str:
    """The REASON_TEXT code of a template send that ended at send_failed:
    the recipient hold's own code (recipient_mismatch /
    recipient_unconfirmed), a code the caller set (``reason``), else
    send_failed. Never the raw error text, which may echo lead data."""
    if out.get("reason"):
        return str(out["reason"])
    if out.get("held") and out.get("error") in ("recipient_mismatch", "recipient_unconfirmed"):
        return str(out["error"])
    return "send_failed"


def _after_template_send(st, approval: Approval, out: Dict[str, Any], ts: datetime, notify_fn=None) -> Dict[str, Any]:
    """What follows a template send (auto_send_approved, or the queue flush
    of a card it queued): an FYI line for a send or a queue; the card
    pushed once, with its "Not auto-sent" line, when it was left for
    Lorenzo (pending, blocked, stale_slots), or when the send ended at
    send_failed (an Instantly error, a recipient hold that escalated, an
    exception in the flush): then it is the recovery card (push_card:
    Retry / Veto / Mark sent where each is allowed), since nothing else
    ever pushed it. A lead hold (``held``, blocked) raises its own HELD
    alert and is not pushed as a card to answer; a recipient hold that has
    not escalated (``held``, approved_queued) retries on its own and is not
    pushed either. Never raises."""
    approval_id = _approval_id(approval)
    status = out.get("status")
    template_id = approval.draft.template_id
    kind = auto_kind(template_id) or "first_reply"
    try:
        if out.get("ok") and status in AUTO_SENT_STATUSES:
            _gate().record_auto_send(st, kind=kind, template_id=template_id, approval_id=approval_id, status=status,
                                     send_after=out.get("send_after"), now=ts)
            return dict(out, auto_sent=True)
        if status in FAILED_PUSH_STATUSES and (not out.get("held") or out.get("escalated")):
            note = _not_auto_sent(_failed_send_code(out))
            pushed = _push_deferred(st, approval_id, ts, note, notify_fn=notify_fn, statuses=FAILED_PUSH_STATUSES)
            return dict(out, pushed=pushed)
        if out.get("held") or status not in AUTO_PUSH_STATUSES:
            return out
        note = "Not auto-sent: %s" % _outcome_reason(out)
        pushed = _push_deferred(st, approval_id, ts, note, notify_fn=notify_fn)
        return dict(out, pushed=pushed)
    except Exception as exc:  # noqa: BLE001 - the send already happened or not; this is bookkeeping
        logger.exception("after the template send of %s: %s", approval_id, exc)
        return out


def auto_send_approved(approval: Approval, instantly, store=None, now: Optional[datetime] = None, ghl=None, *,
                       verdict: Any) -> Dict[str, Any]:
    """Send a card whose draft the template gate allowed (``verdict``), with
    no tap: the same path as Approve (_approve_loaded(actor="template"), then
    send_approved with every check it runs, and the gate run again inside
    it). Refused unless the stored card is still pending and waiting on its
    deferred push, and ``verdict`` is an allowed verdict for its template.

    Sent or queued (outside 07:00-19:00 CT): one FYI line
    (template_gate.record_auto_send). Left pending, blocked or stale_slots,
    or ended at send_failed (an Instantly error, an escalated recipient
    hold): the card is pushed once with "Not auto-sent: <reason>"
    (_after_template_send). A lead hold raises its own alert, and a
    recipient hold that has not escalated retries on its own; neither is
    pushed. An exception pushes the card. In shadow the send is a would_do
    record."""
    st = _store(store)
    ts = _now(now)
    approval_id = _approval_id(approval)
    try:
        card = _approval_row(st, approval_id)
        if card is None:
            return {"ok": False, "status": None, "error": "no such card", "auto": False}
        if _template_draft_only(card.draft.template_id, _stored_row(st, card.state_key)):
            # Before the card's state and the verdict: a draft Lorenzo sends
            # himself (a first reply, or any reply but a booking confirmation
            # to a lead not answered yet) is never auto-sent. A card still waiting on its deferred push (raised
            # before this lock) is pushed now, once; any other is left as is.
            why = reason_text(FIRST_REPLY_LOCK_REASON)
            logger.info("not auto-sending %s: a reply to an unanswered lead is a draft Lorenzo sends himself",
                        approval_id)
            job_log.log_run("reply_engine.approval", "template_auto_send_refused",
                            {"lead": card.lead_email, "approval": approval_id,
                             "template_id": card.draft.template_id, "reason": FIRST_REPLY_LOCK_REASON})
            pushed = _push_deferred(st, approval_id, ts, _not_auto_sent(FIRST_REPLY_LOCK_REASON), statuses=("pending",))
            return {"ok": False, "status": card.status, "auto": False, "reason": why, "pushed": pushed}
        nr = card.notify_result if isinstance(card.notify_result, dict) else {}
        if card.status != "pending" or not nr.get("deferred"):
            return {"ok": False, "status": card.status, "auto": False,
                    "error": "the card is not waiting on an auto-send (it is %s)" % card.status}
        why = None
        if verdict is None or not getattr(verdict, "allowed", False):
            why = reason_text(getattr(verdict, "reason", None) or "registry_error")
        elif getattr(verdict, "template_id", None) != card.draft.template_id or auto_kind(card.draft.template_id) is None:
            why = "the template check was for another draft."
        elif card.draft.model != "template" or card.token != approval.token:
            why = "the card changed after the template check."
        if why is not None:
            pushed = _push_deferred(st, approval_id, ts, "Not auto-sent: %s" % why)
            return {"ok": False, "status": card.status, "auto": False, "reason": why, "pushed": pushed}
        if not _claim_auto_send(st, approval_id, ts):
            return {"ok": False, "status": card.status, "auto": False,
                    "error": "another auto-send or the orphan sweep holds this card"}
        out = _approve_loaded(card, instantly, st, ts, ghl, actor="template")
    except Exception as exc:  # noqa: BLE001 - any doubt is a card
        logger.exception("auto-send of %s raised: %s", approval_id, exc)
        job_log.log_run("reply_engine.approval", "template_auto_send_failed",
                        {"lead": approval.lead_email, "approval": approval_id, "error": str(exc)})
        current = _approval_row(st, approval_id)
        pushed = None
        if current is not None and current.status in AUTO_PUSH_STATUSES + FAILED_PUSH_STATUSES:
            pushed = _push_deferred(st, approval_id, ts, "Not auto-sent: the auto-send failed (%s)." % type(exc).__name__,
                                    statuses=AUTO_PUSH_STATUSES + FAILED_PUSH_STATUSES)
        return {"ok": False, "status": current.status if current is not None else None, "auto": False,
                "error": "auto-send raised: %s" % exc, "pushed": pushed}
    out = _after_template_send(st, card, out, ts)
    # Not "auto_send": that is the old timer path's row (auto_send_due),
    # which the deploy watch fails on.
    job_log.log_run("reply_engine.approval", "template_auto_sent" if out.get("auto_sent") else "template_auto_not_sent",
                    {"lead": card.lead_email, "approval": approval_id, "template_id": card.draft.template_id,
                     "status": out.get("status"), "ok": bool(out.get("ok")), "held": bool(out.get("held")),
                     "reason": None if out.get("ok") else _outcome_reason(out)})
    return dict(out, auto=True)


def _template_verdict(approval: Approval, state_raw: Optional[Dict[str, Any]]):
    """The gate's verdict on the card as it is about to go out: its exact
    subject and body, its template kind, the classification it was raised
    on, its campaign key and the lead's own words from the stored row
    (allow_terms), and its requested time (a Book as asked card is never
    auto-sent). Any error is a refusal."""
    gate = _gate()
    try:
        if _template_draft_only(approval.draft.template_id, state_raw):
            # Before the gate, whatever it would say: never auto-sent.
            return gate.Verdict(False, FIRST_REPLY_LOCK_REASON, approval.draft.template_id, [], {},
                                "a draft Lorenzo sends himself (draft_only)")
        from types import SimpleNamespace

        from services.reply_engine.draft import lead_terms

        kind = auto_kind(approval.draft.template_id)
        if kind is None and approval.draft.template_id:
            return gate.Verdict(False, "unknown_id", approval.draft.template_id, [], {},
                                "not a first_reply or booking template")
        # No template id at all (an edited or polished body): the gate says
        # which (not_template_render / no_template).
        kind = kind or "first_reply"
        state = LeadState.from_store(state_raw) if state_raw else None
        rec = approval.auto_send if isinstance(approval.auto_send, dict) else {}
        cls = rec.get("classification")
        classification = SimpleNamespace(**cls) if isinstance(cls, dict) else None
        return gate.draft_verdict(approval.draft, kind=kind, campaign_key=campaign_key_of(approval),
                                  allow_terms=lead_terms(None, state) or None, classification=classification,
                                  requested=approval.requested_slot or None)
    except Exception as exc:  # noqa: BLE001 - fail closed
        logger.warning("template re-check of %s failed closed: %s", _approval_id(approval), exc)
        return gate.Verdict(False, "registry_error", approval.draft.template_id, [], {}, type(exc).__name__)


def _refuse_template_send(approval: Approval, st, ts: datetime, approval_id: str, verdict: Any) -> Dict[str, Any]:
    """The gate refused a template-approved card right before its send (a
    revoke, the kill switch, a redeploy, a changed hash): back to pending,
    unapproved, and pushed to Lorenzo with the reason. Nothing was sent."""
    record = dict(approval.auto_send or {})
    try:
        record.update(verdict.to_record())
    except Exception:  # noqa: BLE001
        record.update({"allowed": False, "reason": getattr(verdict, "reason", "registry_error")})

    def _back(row):
        row["status"] = "pending"
        row["approved_by"] = None
        row["send_after"] = None
        row["decided_at"] = None
        row["auto_send"] = record
        return row

    if not _transition(st, approval_id, SENDABLE_STATUSES, _back):
        return _card_changed(st, approval_id)
    approval.status = "pending"
    approval.approved_by = None
    approval.send_after = None
    approval.decided_at = None
    approval.auto_send = record
    reason = getattr(verdict, "reason", None) or "registry_error"
    logger.warning("not auto-sending %s: the template gate refused it at send time (%s)", approval_id, reason)
    job_log.log_run("reply_engine.approval", "template_auto_send_refused",
                    {"lead": approval.lead_email, "approval": approval_id, "template_id": approval.draft.template_id,
                     "reason": reason})
    pushed = _push_deferred(st, approval_id, ts, _not_auto_sent(reason))
    return {"ok": False, "status": "pending", "reason": reason, "pushed": pushed}


def push_orphaned_deferred(store=None, now: Optional[datetime] = None,
                           min_age_minutes: int = 2) -> List[Dict[str, Any]]:
    """Push every pending card whose deferred push never went out and whose
    auto-send is not running: a crash between create_approval and
    auto_send_approved, or an auto-send that died holding its claim
    (AUTO_SEND_CLAIM_MINUTES). Cards younger than ``min_age_minutes`` are
    left to the pipeline still running them. Each card is pushed once
    (_claim_deferred_push). Never raises."""
    st = _store(store)
    ts = _now(now)
    out = []  # type: List[Dict[str, Any]]
    try:
        keys = st.keys(APPROVAL_PREFIX)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not list approvals for the orphan sweep: %s", exc)
        return out
    cutoff = ts - timedelta(minutes=min_age_minutes)
    for key in keys:
        try:
            raw = st.get(key)
            if not isinstance(raw, dict) or raw.get("status") != "pending":
                continue
            nr = raw.get("notify_result")
            if not isinstance(nr, dict) or not nr.get("deferred") or _auto_claim_fresh(nr, ts):
                continue
            if slots.parse_iso(raw.get("created_at")) > cutoff:
                continue
        except Exception:  # noqa: BLE001 - an unreadable row is skipped
            continue
        approval_id = key.split(":", 1)[-1]
        result = _push_deferred(st, approval_id, ts, ORPHAN_NOTE, orphan_only=True)
        if result is None:
            continue
        logger.error("card %s for %s: auto-send never ran; pushed to Lorenzo", approval_id, raw.get("lead_email"))
        job_log.log_run("reply_engine.approval", "template_auto_send_orphan_pushed",
                        {"lead": raw.get("lead_email"), "approval": approval_id,
                         "template_id": (raw.get("draft") or {}).get("template_id"),
                         "sent": bool(result.get("sent") or result.get("test") or result.get("shadow"))})
        out.append({"approval": approval_id, "lead": raw.get("lead_email"), "notify_result": result})
    return out


def _fyi_bucket(ts: datetime) -> str:
    local = slots.to_tz(ts)
    return "%s%d" % (local.strftime("%Y%m%d%H"), 0 if local.minute < 30 else 1)


def _fyi_pending(st) -> bool:
    gate = _gate()
    if st.get(gate.FYI_KEY):
        return True
    for key in st.keys(gate.HELD_KEY_PREFIX):
        n = st.get(key)
        if isinstance(n, int) and n > 0:
            return True
    return False


def _fyi_email_lines(st, entries: List[Dict[str, Any]]) -> List[str]:
    """The email leg's per-lead lines: who, which template, what happened,
    and a Veto link for a queued card (GET /veto only renders a confirmation
    page; the veto is its POST). Links are built now from the stored token,
    never stored. A card that cannot be read gets its ids only."""
    lines = []  # type: List[str]
    for e in entries:
        approval_id = e.get("approval_id")
        card = None
        try:
            card = _approval_row(st, approval_id) if approval_id else None
        except Exception:  # noqa: BLE001
            card = None
        who = card.lead_email if card is not None else "card %s" % approval_id
        status = e.get("status")
        if status == "sent" and not settings.is_live():
            status = "would have sent (shadow)"
        line = "%s: %s %s" % (who, e.get("template_id"), status)
        if e.get("status") == "approved_queued":
            line += " (goes out %s)" % (_when_label(e.get("send_after")) if e.get("send_after") else "at 07:00 CT")
            if card is not None and card.status == "approved_queued":
                try:
                    line += "\n  Veto: %s" % action_urls(card.token)["veto"]
                except Exception as exc:  # noqa: BLE001 - base_url() fails closed in live
                    logger.warning("no Veto link for %s in the FYI: %s", approval_id, exc)
        lines.append(line)
    return lines


def flush_auto_send_fyi(store=None, now: Optional[datetime] = None, notify_fn=None) -> Optional[Dict[str, Any]]:
    """One FYI push per 30-minute bucket about what went out on its own.

    The ntfy leg (a public topic unless NTFY_TOKEN) carries counts per
    template id and held counts per template id only: no name, address,
    company, subject, body or link, and no actions or click. The email leg
    (Lorenzo's own inbox) adds a line per card, with a Veto link for a
    queued one. The bucket is taken with set_if_absent, so two ticks send
    one. A push that did not go out (or raised) puts the entries back for
    the next bucket (template_gate.restore_fyi). None when there was nothing
    to say or the bucket is taken."""
    gate = _gate()
    st = _store(store)
    ts = _now(now)
    if not _fyi_pending(st):
        return None
    bucket = _fyi_bucket(ts)
    lease = gate.FYI_LEASE_PREFIX + bucket
    claim = getattr(st, "set_if_absent", None)
    if callable(claim) and not claim(lease, {"at": ts.isoformat()}):
        return None
    _forget_fyi_leases(st, bucket)
    entries, held = gate.drain_fyi(st)
    if not entries and not held:
        return None
    counts = {}  # type: Dict[str, Dict[str, int]]
    for e in entries:
        per = counts.setdefault(str(e.get("template_id")), {})
        per[str(e.get("status"))] = per.get(str(e.get("status")), 0) + 1
    sent = sum(1 for e in entries if e.get("status") == "sent")
    queued = sum(1 for e in entries if e.get("status") == "approved_queued")
    # In shadow a "sent" entry is a would_do record: nothing reached a lead,
    # and NOTIFY_SHADOW_SEND=1 delivers this FYI all the same.
    shadow = not settings.is_live()
    sent_word = "would have sent (shadow)" if shadow else "sent"
    title = "Auto-sent from approved templates%s: %d %s, %d queued, %d held" % (
        " (shadow)" if shadow else "", sent, sent_word, queued, sum(held.values()))
    lines = []  # type: List[str]
    for tid in sorted(counts):
        lines.append("%s: %s" % (tid, ", ".join("%d %s" % (n, sent_word if st_ == "sent" else st_)
                                              for st_, n in sorted(counts[tid].items()))))
    if held:
        lines.append("Held (not sent, template not approved or refused):")
        for tid in sorted(held):
            lines.append("%s: %d held" % (tid, held[tid]))
    lines.append("To stop these, set the kill switch, or revoke a template from your terminal "
                 "(jobs/approve_templates.py --revoke <id>).")
    message = "\n".join(lines)
    email_message = message
    detail = _fyi_email_lines(st, entries)
    if detail:
        email_message = "%s\n\nPer card:\n%s" % (message, "\n".join(detail))
    fn = notify_fn or notify.notify
    try:
        result = fn(title, message, priority="default", actions=None, tags=["email", "reply-engine"], click=None,
                    email_message=email_message)
    except Exception as exc:  # noqa: BLE001
        logger.warning("the auto-send FYI push raised: %s", exc)
        result = {"sent": False, "errors": ["notify raised: %s" % exc]}
    ok = isinstance(result, dict) and bool(result.get("sent") or result.get("test") or result.get("shadow"))
    if not ok:
        try:
            gate.restore_fyi(st, entries, held)
        except Exception as exc:  # noqa: BLE001
            logger.error("could not put the auto-send FYI back: %s", exc)
        job_log.log_run("reply_engine.approval", "push_failed",
                        {"kind": "auto_send_fyi", "entries": len(entries), "held": sum(held.values()),
                         "errors": stored_notify_result(result).get("errors")})
    return {"sent": ok, "bucket": bucket, "entries": len(entries), "held": dict(held), "counts": counts,
            "notify_result": stored_notify_result(result)}


def _forget_fyi_leases(st, keep_bucket: str) -> None:
    """Drop FYI bucket leases older than a day. Bookkeeping only."""
    prefix = _gate().FYI_LEASE_PREFIX
    try:
        for key in st.keys(prefix):
            if key[len(prefix):][:8] < keep_bucket[:8] and key != prefix + keep_bucket:
                old = datetime.strptime(key[len(prefix):][:8], "%Y%m%d")
                if (datetime.strptime(keep_bucket[:8], "%Y%m%d") - old).days >= 1:
                    st.delete(key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not forget old FYI leases: %s", exc)


def _mutate_card(st, key: str, fn) -> None:
    """Apply ``fn(row) -> row`` to the stored card under the store's lock
    (store.mutate); a store without mutate gets the same read-modify-write
    unlocked. ``fn`` must return a missing card unchanged."""
    mutate = getattr(st, "mutate", None)
    if callable(mutate):
        try:
            mutate(key, fn)
            return
        except NotImplementedError:
            pass
    current = st.get(key)
    if isinstance(current, dict):
        st.set(key, fn(current))


def _record_notify_result(st, key: str, result: Any) -> None:
    """Write the card's push result, and nothing else, onto the stored card.
    Keys already on the stored notify_result that the push did not produce
    (the expiry push record, the reopen marker) are kept."""
    if not isinstance(result, dict):
        return

    def _set(current):
        if not isinstance(current, dict):
            return current
        out = dict(current)
        out["notify_result"] = dict(current.get("notify_result") or {}, **result)
        return out

    _mutate_card(st, key, _set)


def load(token: str, store=None) -> Optional[Approval]:
    """Verify the token's HMAC against the persisted approval; None if unknown or tampered."""
    if not token or "." not in token:
        return None
    approval_id, sig = token.split(".", 1)
    raw = _store(store).get(APPROVAL_PREFIX + approval_id)
    if not raw:
        return None
    try:
        approval = Approval.model_validate(raw)
    except Exception:  # noqa: BLE001
        return None
    expected = _sig(approval_id, approval.state_key, draft_hash(approval.draft), approval.expires_at)
    if not hmac.compare_digest(expected, sig):
        return None
    return approval


def _save(approval: Approval, store) -> None:
    approval_id = approval.token.split(".", 1)[0]
    _store(store).set(APPROVAL_PREFIX + approval_id, approval.model_dump(mode="json"))


def _refresh_token(approval: Approval) -> None:
    approval_id = approval.token.split(".", 1)[0]
    approval.token = make_token(approval_id, approval.state_key, draft_hash(approval.draft), approval.expires_at)


def _expired(approval: Approval, now: datetime) -> bool:
    try:
        return slots.parse_iso(approval.expires_at) <= now
    except (ValueError, TypeError):
        return False


def _localise_at(day, hour: int) -> datetime:
    naive = datetime(day.year, day.month, day.day, hour, 0)
    try:
        return slots.TZ.localize(naive, is_dst=None)
    except Exception:  # noqa: BLE001 - ambiguous/non-existent local time
        return slots.TZ.localize(naive, is_dst=False)


def _next_window_open(ts: datetime) -> datetime:
    """The next 07:00 CT on a business day, re-localised.

    ``ts.replace(hour=7)`` keeps the offset ts already carried, so an approval
    decided at 01:30 CDT on 2026-11-01 produced 07:00-05:00, which is 06:00 CST:
    an hour before the window actually opens, and a wall-clock time that does
    not exist locally that day.

    The weekday matters too. within_send_window is hour-only, so a Friday
    evening approval used to be queued to 07:00 on Saturday and the poller fired
    it, unattended, on a weekend with slots picked on Friday. The blueprint
    lists "skip weekends" among the engine's rules.
    """
    hour = settings.SEND_WINDOW[0]
    nxt = _localise_at(ts.date(), hour)
    day = ts.date()
    while nxt <= ts or not slots.is_business_day(nxt):
        day = day + timedelta(days=1)
        nxt = _localise_at(day, hour)
    return slots.to_tz(nxt)


def _arm_cadence(state: LeadState, now: datetime) -> Dict[str, Any]:
    try:
        from services.reply_engine import cadence  # type: ignore
    except ImportError:
        state.cadence = dict(state.cadence, armed=True, paused=False, armed_at=now.isoformat(), day=0, note="cadence module absent; armed in state only")
        return {"armed": True, "module": False}
    try:
        cadence.arm(state, now)
        return {"armed": True, "module": True, "armed_at": (state.cadence or {}).get("armed_at"),
                "next_send_at": (state.cadence or {}).get("next_send_at")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("cadence.arm failed: %s", exc)
        state.cadence = dict(state.cadence, armed=True, paused=False, armed_at=now.isoformat(), error=str(exc))
        return {"armed": True, "module": True, "error": str(exc)}


def _open_other_cards(st, approval: Approval, state_raw: Optional[Dict[str, Any]], now: datetime) -> Dict[str, bool]:
    """For every other card listed on the lead row: is it still open (pending
    or queued, inside its TTL)? Read OUTSIDE the row's lock and handed to
    arm_refusal, because the locked decision cannot read the store itself
    (JsonFileStore holds one file lock for the whole mutate). A card that
    shows up on the row after this read is treated as open by arm_refusal."""
    own = _approval_id(approval)
    out = {}  # type: Dict[str, bool]
    for token in (state_raw or {}).get("approvals") or []:
        other = str(token).split(".", 1)[0]
        if other == own or other in out:
            continue
        card = _approval_row(st, other)
        out[other] = card is not None and card.status in SENDABLE_STATUSES and not _expired(card, now)
    return out


def open_card_ids(store, tokens: Optional[List[str]], now: datetime) -> List[str]:
    """The ids, among a lead row's ``approvals`` tokens, of the cards still
    waiting on Lorenzo: pending or queued (SENDABLE_STATUSES) inside their TTL.
    Each one is a reply of the lead's that nobody has answered yet. A store
    that cannot be read raises: the caller holds rather than guess."""
    st = _store(store)
    out = []  # type: List[str]
    for token in tokens or []:
        approval_id = str(token).split(".", 1)[0]
        if not approval_id or approval_id in out:
            continue
        card = _approval_row(st, approval_id)
        if card is not None and card.status in SENDABLE_STATUSES and not _expired(card, now):
            out.append(approval_id)
    return out


def arm_refusal(row: Optional[Dict[str, Any]], approval: Approval, open_cards: Dict[str, bool],
                seen_before: Optional[List[str]] = None, reply_at: Any = None) -> Optional[str]:
    """Why this approved card may not arm the follow-up ladder on ``row`` (the
    lead row as it stands under the lock), or None when it may.

    The lead's own words come first, judged by _lead_reply_verdict, the one
    helper behind every "may this lead still be emailed" decision in this
    module (lead_reply_hold is the other face of it):

    * ``opt_out:<category>``: the lead's sticky opt-out marker
      (LeadState.opt_out) is on the row, whatever order the replies were
      processed in.
    * ``newer_inbound:<email id>``: the lead SENT a reply after the one this
      card answers (lead_replies_after: by when they sent it wherever both
      times show it, else by where it sits in processed_email_ids, the
      router's rule), an opt-out or not. A machine's answer
      (an out-of-office, an unmonitored mailbox, by the label the row's
      history gives it) does not count: it raises no card, and the ladder
      treats one as a pause, never as the lead's reply
      (cadence.is_auto_reply_pause). Counted, the auto-answer a shared info@
      box fires beside a positive reply left that lead with no ladder at all
      once Lorenzo answered.
    * ``opt_out:<status or label>``: the row's status or latest
      classification is an opt-out (router.OPT_OUT_STATUSES /
      OPT_OUT_LABELS).
    * ``open_card:<approval id>``: another card for this lead is still open:
      pending or queued inside its TTL per ``open_cards``, or listed on the row
      since ``open_cards`` was read (a card that new is pending).

    ``seen_before`` and ``reply_at`` are the card's context (card_context:
    processed_before and reply_at); lead_replies_after says how they are
    used."""
    row = row or {}
    _why, refusal = _lead_reply_verdict(row, approval, seen_before, reply_at)
    if refusal:
        return refusal
    own = _approval_id(approval)
    for token in row.get("approvals") or []:
        other = str(token).split(".", 1)[0]
        if other != own and open_cards.get(other, True):
            return "open_card:%s" % other
    return None


# ------------------------------------------- the lead said no, or wrote again
# "After the reply this card answers" means after it in the order the lead
# SENT them wherever the store can show that order, and it is read by the same
# rule the router reads it by (lead_replies_after). The poller retries a reply
# whose processing raised on a later tick, after newer replies went through,
# and leaves a reply claimed by a killed run until its claim goes stale, so
# processed_email_ids can list an older reply after a newer one. Read in that
# order, a positive reply the lead sent before "please remove me", but
# processed after it, made the removal look older than the card, and the card
# was sent and the ladder armed (round-4 defect 1). Read by its processing-time
# stand-in, a reply with no email time of its own, processed before an older
# one, looked newer than the reply the router then took as the lead's newest,
# and the card answering that reply could never be sent (S-rest round 6).
#
# Cards a lead's opt-out holds the moment it lands (hold_cards_for_lead_reply):
# every status a card can still be sent from, or put back in front of Lorenzo
# from. A card holding a send claim is left to the send's own check, except a
# send_failed one, whose claim is stale (hold_cards_for_lead_reply says why).
LEAD_HOLD_STATUSES = ("pending", "approved_queued", "blocked", "stale_slots", "send_failed")
# Where a card blocked for the lead's own words records why, on the stored
# card's notify_result beside the expiry push record: {"reason", "category",
# "email_id", "at", "held_at"}. A card already held for the same reason is not
# blocked or announced a second time.
LEAD_HOLD_KEY = "lead_reply_hold"
_LEAD_SAID = {
    "unsubscribe": "asked to be removed", "unsubscribed": "asked to be removed",
    "blocklisted": "asked to be removed (blocklisted)",
    "negative_hostile": "sent a hostile reply", "hostile": "sent a hostile reply",
    "wrong_person": "said they are the wrong person",
    "negative_notfit": "said it is not a fit", "lost": "said it is not a fit (lost)",
    "negative_notnow": "said not now", "not_now": "said not now", "follow_up_later": "said not now",
    "needs_review": "sent a removal-style reply the engine held for your review",
}
# What Lorenzo is told to do after an opt-out or a final no: Veto, and do not
# answer. "Read the thread and reply by hand" is said only when the lead wrote
# again with something that is not a no (lead_reply_problem, the HELD push).
_ASKED_NOT_TO_BE_EMAILED = "Do not reply to them: they asked not to be emailed."
_NOT_A_FIT = "Do not reply to them: they said it is not a fit."
_NOT_NOW = "Do not reply to them now: they said not now."
_OPT_OUT_ADVICE = {
    "unsubscribe": _ASKED_NOT_TO_BE_EMAILED, "unsubscribed": _ASKED_NOT_TO_BE_EMAILED,
    "blocklisted": _ASKED_NOT_TO_BE_EMAILED, "negative_hostile": _ASKED_NOT_TO_BE_EMAILED,
    "hostile": _ASKED_NOT_TO_BE_EMAILED,
    "wrong_person": ("Do not email from this thread: they are not the right person, and a contact they name goes to "
                     "the list factory, never emailed from this thread (offers.md rule 7)."),
    "negative_notfit": _NOT_A_FIT, "lost": _NOT_A_FIT,
    "negative_notnow": _NOT_NOW, "not_now": _NOT_NOW, "follow_up_later": _NOT_NOW,
    "needs_review": ("Read their reply before anything else goes to them: the engine held back the blocklist because "
                     "the reply also reads as interested."),
}


def opt_out_advice(category: Optional[str]) -> str:
    """What to do about an opt-out or a final no of this category. Never
    "reply by hand"."""
    return _OPT_OUT_ADVICE.get(str(category or "").strip().lower(), "Do not reply to them.")


def _opt_out_vocab():
    from services.reply_engine.router import OPT_OUT_LABELS, OPT_OUT_STATUSES  # lazy: router pulls in classify
    return OPT_OUT_LABELS, OPT_OUT_STATUSES


def _machine_labels():
    try:
        from services.reply_engine.cadence import AUTO_REPLY_STATUSES as labels  # type: ignore
    except ImportError:
        labels = ("ooo", "auto_reply", "auto_reply_unmonitored")
    return labels


def opt_out_marker(row: Any) -> Optional[Dict[str, Any]]:
    """The lead's sticky opt-out marker (LeadState.opt_out: {"label",
    "email_id", "received_at", "set_at"}), or None when there is none. Takes
    a stored lead row (dict) or a LeadState, with or without the field. A
    marker that is present but cannot be read is still a marker: it comes
    back as {} (callers test ``is not None``)."""
    if row is None:
        return None
    raw = row.get("opt_out") if isinstance(row, dict) else getattr(row, "opt_out", None)
    if not raw:
        return None
    if hasattr(raw, "model_dump"):
        try:
            raw = raw.model_dump(mode="json")
        except Exception:  # noqa: BLE001 - unreadable, but present: it still holds
            raw = {}
    return dict(raw) if isinstance(raw, dict) else {}


def _time_of(value: Any) -> Optional[datetime]:
    """An aware datetime for an ISO string, epoch or datetime; None when
    there is none or it cannot be read."""
    if value is None or value == "":
        return None
    try:
        return slots.parse_iso(value)
    except Exception:  # noqa: BLE001 - an unreadable time is no time
        return None


def _inbound_entries(row: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """The first inbound history entry per email id, in history order. An
    entry with no email id is skipped: nothing can say which reply it is."""
    out = {}  # type: Dict[str, Dict[str, Any]]
    for entry in row.get("history") or []:
        if not isinstance(entry, dict) or entry.get("event") != "inbound":
            continue
        email_id = str(entry.get("email_id") or "")
        if email_id and email_id not in out:
            out[email_id] = entry
    return out


def _entry_time(entry: Any, opt_out: bool = False) -> Optional[datetime]:
    """When the lead sent this reply, read by the router's rule. The readers
    live in models, and router imports the same ones:

    * an opt-out (``opt_out``) by its received_at, a processing-time
      stand-in included, falling back to its ``at`` for an entry written
      before received_at existed (entry_received_at). The router keeps an
      opt-out's marker at that time and lets only a reply PROVABLY sent after
      it clear it (router.after_opt_out);
    * any other reply only by the email's own time (entry_email_time, what
      router.newer_replies reads): None for a processing-time stand-in or an
      entry with no received_at, which can never show that the reply came
      after another one.

    None too when the time cannot be read."""
    try:
        return entry_received_at(entry) if opt_out else entry_email_time(entry)
    except Exception:  # noqa: BLE001 - an unreadable time is no time
        return None


def _card_time(entries: Dict[str, Dict[str, Any]], approval: Approval, reply_at: Any = None) -> Optional[datetime]:
    source = entries.get(str(approval.email_id or "")) or {}
    times = [when for when in (_time_of(v) for v in (reply_at, source.get("received_at"), source.get("at"),
                                                      approval.created_at))
             if when is not None]
    return min(times) if times else None


def _card_email_time(entries: Dict[str, Dict[str, Any]], approval: Approval,
                     reply_at: Any = None) -> Optional[datetime]:
    """The email's own time of the reply this card answers: the earlier of
    its history entry's (entry_email_time) and the card context's reply_at
    (the same reply event's time). None when that entry records only a
    processing-time stand-in (received_at_source "processing": the context's
    reply_at is the same stand-in then), or when there is no time at all."""
    source = entries.get(str(approval.email_id or ""))
    stand_in = isinstance(source, dict) and (
        str(source.get("received_at_source") or RECEIVED_AT_EMAIL) == RECEIVED_AT_PROCESSING)
    if stand_in:
        return None
    times = [when for when in (_entry_time(source), _time_of(reply_at)) if when is not None]
    return min(times) if times else None


def card_reply_time(row: Optional[Dict[str, Any]], approval: Approval, reply_at: Any = None) -> Optional[datetime]:
    """When the lead sent the reply this card answers: the earliest of what
    the store records for it. The card context's reply_at (the reply event's
    own time, passed in as ``reply_at``) and the source reply's history
    received_at are that time; the source entry's ``at`` and the card's
    created_at are when it was processed, never earlier, and stand in for a
    card or a row written before those existed. None when nothing can be
    read. An opt-out is compared with this time (lead_replies_after); any
    other reply only with the email's own time of the card's reply."""
    return _card_time(_inbound_entries(row or {}), approval, reply_at=reply_at)


def lead_replies_after(row: Optional[Dict[str, Any]], approval: Approval, seen_before: Optional[List[str]] = None,
                       reply_at: Any = None) -> List[Dict[str, Any]]:
    """The lead's replies on ``row`` that were SENT after the one this card
    answers, oldest first, as {"email_id", "label", "at", "machine"}.

    Read by the router's rule, so a card answering the reply the router took
    as the lead's newest is never held for one it took as older (a card
    nothing could ever send):

    * a reply that is not an opt-out is newer by the email's own time when it
      and the card's reply both carry one and they differ (_entry_time and
      _card_email_time: models.entry_email_time, the reader
      router.newer_replies uses). Otherwise by the order the replies were
      processed in: the router processes a reply that cannot be shown to be
      older as the lead's newest (router.stale_reason), so one processed
      after the card's reply is newer and one processed before it is not;
    * an opt-out is newer when its received_at, a processing-time stand-in
      included (``at`` for an entry written before received_at existed), is
      later than card_reply_time: it stands unless the card's reply was
      provably sent after it, as the router's opt-out marker does. With a
      time missing, or the two equal, the processing order decides.

    The processing order is the replies' place in processed_email_ids. When
    the card's own email is not on it (its pipeline died after raising the
    card: the crash gap), a reply is newer when it is not in ``seen_before``
    (card_context's processed_before: the ids the row held when the card was
    raised). A reply whose id is not on processed_email_ids (no real row has
    one: the pipeline writes the entry and the id in the same save), or with
    no ``seen_before`` to read in the crash gap, is not newer by that order.

    ``machine`` marks a machine's answer (cadence.AUTO_REPLY_STATUSES, by the
    label the history gives it); a reply with no label is the lead's own
    ("unlabelled")."""
    row = row or {}
    source = str(approval.email_id or "")
    processed = []  # type: List[str]
    for email_id in row.get("processed_email_ids") or []:
        if str(email_id) not in processed:
            processed.append(str(email_id))
    entries = _inbound_entries(row)
    card_time = _card_time(entries, approval, reply_at=reply_at)
    card_email = _card_email_time(entries, approval, reply_at=reply_at)
    seen = set(str(x) for x in seen_before) if seen_before is not None else None
    machine = _machine_labels()
    labels_out, _statuses = _opt_out_vocab()
    out = []  # type: List[Dict[str, Any]]
    for position, email_id in enumerate(processed + [x for x in entries if x not in processed]):
        if not email_id or email_id == source:
            continue
        entry = entries.get(email_id) or {}
        label = str(entry.get("label") or "").strip().lower()
        opt_out = label in labels_out
        sent_at = _entry_time(entry, opt_out=opt_out)
        than = card_time if opt_out else card_email
        if sent_at is not None and than is not None and sent_at != than:
            newer = sent_at > than
        elif email_id not in processed:
            newer = False
        elif source in processed:
            newer = processed.index(email_id) > processed.index(source)
        else:
            newer = seen is not None and email_id not in seen
        if not newer:
            continue
        out.append({"email_id": email_id, "label": label or "unlabelled",
                    "at": entry.get("received_at") or entry.get("at"), "machine": label in machine,
                    "_order": (sent_at is not None, sent_at.timestamp() if sent_at is not None else 0.0, position)})
    out.sort(key=lambda item: item["_order"])
    for item in out:
        item.pop("_order", None)
    return out


def _why_of(reason: str, reply: Dict[str, Any]) -> Dict[str, Any]:
    return {"reason": reason, "category": reply["label"], "at": reply["at"], "email_id": reply["email_id"]}


def _lead_reply_verdict(row: Optional[Dict[str, Any]], approval: Approval, seen_before: Optional[List[str]] = None,
                        reply_at: Any = None):
    """(why, arm refusal): whether the lead may still be emailed on this
    card's behalf, judged from the lead row as stored. Both None when it may.

    ``why`` is lead_reply_hold's answer ({"reason", "category", "at",
    "email_id"}), ``arm refusal`` arm_refusal's reason string. In order:

    1. the sticky opt-out marker (LeadState.opt_out) on the row: an opt-out,
       whatever order the replies were processed in;
    2. a reply sent after the card's own (lead_replies_after) with an opt-out
       label (router.OPT_OUT_LABELS);
    3. the row's status (router.OPT_OUT_STATUSES) or its latest
       classification (router.OPT_OUT_LABELS);
    4. any other reply the lead sent after the card's own, a machine's answer
       excepted: they wrote again."""
    row = row or {}
    labels_out, statuses_out = _opt_out_vocab()
    marker = opt_out_marker(row)
    if marker is not None:
        category = str(marker.get("label") or "").strip().lower() or "opt_out"
        why = {"reason": "opt_out", "category": category, "at": marker.get("received_at") or marker.get("set_at"),
               "email_id": marker.get("email_id")}
        return why, "opt_out:%s" % category
    human = [r for r in lead_replies_after(row, approval, seen_before, reply_at) if not r["machine"]]
    newer = "newer_inbound:%s" % human[-1]["email_id"] if human else None
    opted = [h for h in human if h["label"] in labels_out]
    if opted:
        return _why_of("opt_out", opted[-1]), newer
    status = str(row.get("status") or "").strip().lower()
    last_id = str(row.get("last_email_id") or "") or None
    if status in statuses_out:
        return ({"reason": "opt_out", "category": status, "at": row.get("last_inbound_at"), "email_id": last_id},
                newer or "opt_out:%s" % status)
    cls = row.get("classification")
    cls_label = str((cls.get("label") if isinstance(cls, dict) else getattr(cls, "label", "")) or "").lower()
    if cls_label in labels_out:
        return ({"reason": "opt_out", "category": cls_label, "at": row.get("last_inbound_at"), "email_id": last_id},
                newer or "opt_out:%s" % cls_label)
    if human:
        return _why_of("newer_reply", human[-1]), newer
    return None, None


def lead_reply_hold(row: Optional[Dict[str, Any]], approval: Approval, seen_before: Optional[List[str]] = None,
                    reply_at: Any = None) -> Optional[Dict[str, Any]]:
    """Why no approved reply may go out on this card, judged from the lead row
    as stored, or None when it may. The same verdict arm_refusal reads
    (_lead_reply_verdict).

    * ``opt_out``: the lead opted out or gave a final no. The row carries the
      sticky opt-out marker (LeadState.opt_out, set by the pipeline for a
      reply labelled with router.OPT_OUT_LABELS and cleared only by a human
      reply sent after it), whatever order the replies were processed in; or
      a reply the lead sent after this card's source carries an opt-out
      label (by the label its history entry gives it); or the row's status is
      one of router.OPT_OUT_STATUSES, or its latest classification is an
      opt-out label.
    * ``newer_reply``: the lead sent another reply after the source one, which
      a machine did not write (an out-of-office or unmonitored mailbox never
      counts: cadence.AUTO_REPLY_STATUSES). A reply with no history label
      counts as the lead's own. This draft answers words they have moved past,
      whether or not that reply raised a card of its own.

    "Sent after" is read by the router's rule (lead_replies_after): when the
    lead sent each reply against when they sent the one this card answers
    where both times show it, else the order the replies were processed in;
    ``reply_at`` is the card context's reply_at and ``seen_before`` its
    processed_before, that order's fallback in the crash gap. Returns
    {"reason", "category", "at", "email_id"}."""
    return _lead_reply_verdict(row, approval, seen_before, reply_at)[0]


def _when_label(at: Any) -> str:
    try:
        return "%s CT" % _dated_label(slots.to_tz(slots.ensure_aware(slots.parse_iso(str(at)))))
    except Exception:  # noqa: BLE001
        return "at a time the row does not record"


def lead_reply_problem(why: Dict[str, Any], earlier_send: bool = False) -> str:
    """The card's stated problem: what the lead said (category and time,
    never the text), that nothing will go out, and what to do. An opt-out or
    a final no says Veto and do not reply; only a newer reply that is not a
    no says the thread may be answered by hand. ``earlier_send`` for a card
    with a failed send attempt on record (_had_send_attempt): "nothing was
    sent" would not be proved, so it says nothing MORE was sent.

    Worded from the facts ``why`` carries besides the verdict (_hold_facts;
    the arrival hold's "newer_reply" from app), and never beyond them: "after
    this card was drafted" only when their newer reply was sent after it
    ("after_card"), else "after the reply this card answers"; a card that
    holds the lead's call ("holds_call") is not told to Veto, which would
    cancel that call; a no the lead sent before a newer reply that is not a
    no ("newer_reply") names that reply and asks for the thread to be read
    before the Veto."""
    category = str(why.get("category") or "unlabelled")
    when = _when_label(why.get("at"))
    sent = ("nothing more was sent (an earlier send attempt from this card failed and may have reached the lead)"
            if earlier_send else "nothing was sent")
    if why.get("reason") == "opt_out":
        said = _LEAD_SAID.get(category, "gave a final no")
        newer = why.get("newer_reply") or {}
        if newer:
            return ("the lead %s (%s, %s): this reply must not go out; %s. They wrote again after it (%s, %s): read "
                    "the whole thread before you Veto the card. %s"
                    % (said, category, when, sent, newer.get("label") or "unlabelled", _when_label(newer.get("at")),
                       opt_out_advice(category)))
        return ("the lead %s (%s, %s): this reply must not go out; %s. Veto the card. %s"
                % (said, category, when, sent, opt_out_advice(category)))
    after = "after this card was drafted" if why.get("after_card") else "after the reply this card answers"
    if why.get("holds_call"):
        todo = ("Read the thread and any newer card for this lead before you Veto this card: it holds the call "
                "booked for %s, and a Veto cancels that call without telling the lead" % why.get("holds_call"))
    else:
        todo = "Read the thread and any newer card for this lead, then Veto this card or reply by hand"
    return ("the lead wrote again %s (%s, %s): this draft answers words they have moved past; %s. %s"
            % (after, category, when, sent, todo))


def _had_send_attempt(st, card: Approval) -> bool:
    """A send from this card started before now and may have reached the
    lead: it is send_failed (read before any hold moves it), or a failed
    attempt is on its history (card_context send_attempts, written by Retry
    and by the opt-out hold when they drop a stale claim). A claim held
    right now is not counted: the send that holds it is the caller's own, or
    is left to its own check. Never raises."""
    if getattr(card, "status", None) == "send_failed":
        return True
    try:
        return int(card_context(st, _approval_id(card)).get("send_attempts") or 0) > 0
    except Exception:  # noqa: BLE001 - unreadable: say nothing more than before
        return False


def lead_hold_record(raw: Any) -> Dict[str, Any]:
    """The lead-reply hold recorded on a stored card (a dict row or an
    Approval), or {} when it has none."""
    result = raw.get("notify_result") if isinstance(raw, dict) else getattr(raw, "notify_result", None)
    rec = (result or {}).get(LEAD_HOLD_KEY) if isinstance(result, dict) else None
    return dict(rec) if isinstance(rec, dict) else {}


def _held_for(card: Approval) -> Optional[str]:
    """Why this card is held for the lead's own words ("opt_out",
    "newer_reply"), or None. The record LEAD_HOLD_KEY first; a card blocked
    before it existed is read from its stated problem."""
    reason = lead_hold_record(card).get("reason")
    if reason:
        return str(reason)
    problems = list(getattr(card.draft, "problems", None) or [])
    if any("this reply must not go out" in str(p) for p in problems):
        return "opt_out"
    if any("the lead wrote again after this card was drafted" in str(p)
           or "the lead wrote again after the reply this card answers" in str(p) for p in problems):
        return "newer_reply"
    return None


def _block_for_lead_reply(st, approval_id: str, ts: datetime, problem: str, allowed,
                          why: Optional[Dict[str, Any]] = None) -> bool:
    """Status-guarded: the stored card -> blocked with ``problem``, only while
    its status is in ``allowed``, recording ``why`` under LEAD_HOLD_KEY. True
    when it moved."""

    def _block(row):
        draft = dict(row.get("draft") or {})
        problems = list(draft.get("problems") or [])
        if problem not in problems:
            problems.append(problem)
        draft["problems"] = problems
        row["draft"] = draft
        row["status"] = "blocked"
        row["decided_at"] = ts.isoformat()
        row["send_after"] = None
        row["send_attempt"] = None
        if why is not None:
            result = dict(row.get("notify_result") or {})
            result[LEAD_HOLD_KEY] = {"reason": why.get("reason"), "category": why.get("category"),
                                     "email_id": why.get("email_id"), "at": why.get("at"), "held_at": ts.isoformat()}
            row["notify_result"] = result
        return row

    return _transition(st, approval_id, allowed, _block)


def _booking_note(st, cards: List[Approval], why: Optional[Dict[str, Any]] = None) -> str:
    """The sentence a HELD push adds when one of the held cards owns the
    lead's unconfirmed call; "" when none does. A Veto cancels that call
    without telling the lead, so the note makes it the thing to do only
    when the lead's newest words are the no this hold is for. After a newer
    reply that is not a no (``why`` reason newer_reply, or an opt-out with a
    "newer_reply" recorded, _hold_facts), the lead may be keeping the call:
    the note says what a Veto does and leaves the call to Lorenzo, and names
    the card answering the newer reply when it names the same time
    ("newer_card" "keeps_call"). Never raises: the note is a courtesy."""
    try:
        if not cards:
            return ""
        raw = st.get(cards[0].state_key)
        state = LeadState.from_store(raw) if raw else None
        owners = [card for card in cards if state is not None and owns_booking(card, state)]
        if not owners:
            return ""
        label = _slot_label(booking_of(state).get("slot"))
        why = why or {}
        one = len(cards) == 1
        holder = "This card" if one else "Card %s" % _approval_id(owners[0])
        if why.get("reason") == "newer_reply":
            newer = why.get("newer_card") or {}
            kept = ""
            if newer.get("keeps_call"):
                kept = (" Card %s, which answers their newer reply, names the same time, so the lead may be keeping "
                        "the call." % newer.get("id"))
            return (" %s holds the call booked for %s (invite withheld), and a Veto cancels that call without "
                    "telling the lead.%s Do not Veto %s unless the call should go; if it should stand, confirm it "
                    "with the lead and in GHL by hand." % (holder, label, kept, "it" if one else "that card"))
        if why.get("newer_reply"):
            return (" %s holds the call booked for %s (invite withheld), and a Veto cancels that call without "
                    "telling the lead: decide the call once you have read the thread." % (holder, label))
        if one:
            return " This card holds the call booked for %s (invite withheld): Veto the card to cancel it." % label
        return (" Card %s holds the call booked for %s (invite withheld): Veto that card to cancel it."
                % (_approval_id(owners[0]), label))
    except Exception:  # noqa: BLE001
        return ""


def _newest_reply_after(row: Dict[str, Any], after: Any, exclude: Any = None) -> Optional[Dict[str, Any]]:
    """The lead's newest reply on ``row`` that is not a no, SENT after
    ``after`` by its email's own time, as {"email_id", "label", "at"}; None
    when there is none or ``after`` cannot be read. A machine's answer, an
    opt-out or final no (router.OPT_OUT_LABELS), the reply ``exclude``, and
    an entry with no email time of its own (it cannot be shown to be newer)
    are skipped."""
    since = _time_of(after)
    if since is None:
        return None
    labels_out, _statuses = _opt_out_vocab()
    machine = _machine_labels()
    best = None  # type: Optional[Any]
    for email_id, entry in _inbound_entries(row).items():
        if exclude is not None and email_id == str(exclude):
            continue
        label = str(entry.get("label") or "").strip().lower()
        if label in machine or label in labels_out:
            continue
        sent = entry_email_time(entry)
        if sent is None or sent <= since:
            continue
        if best is None or sent > best[0]:
            best = (sent, {"email_id": email_id, "label": label or "unlabelled", "at": entry.get("received_at")})
    return best[1] if best is not None else None


def _card_answering(st, row: Dict[str, Any], email_id: Any, skip: Optional[str] = None) -> Optional[Approval]:
    """The lead's card (from the row's approvals, ``skip`` left out) that
    answers the reply ``email_id``: an open one first (pending,
    approved_queued, sending), then a sent one, then the newest of the rest.
    None when there is none or none can be read."""
    if not email_id:
        return None
    best = None  # type: Optional[Any]
    seen = set()  # type: set
    for token in row.get("approvals") or []:
        approval_id = str(token or "").split(".", 1)[0]
        if not approval_id or approval_id in seen or approval_id == skip:
            continue
        seen.add(approval_id)
        card = _approval_row(st, approval_id)
        if card is None or str(card.email_id or "") != str(email_id):
            continue
        rank = 0 if card.status in SENDABLE_STATUSES + ("sending",) else 1 if card.status in SENT_STATUSES else 2
        created = _time_of(card.created_at)
        key = (rank, -(created.timestamp() if created is not None else 0.0))
        if best is None or key < best[0]:
            best = (key, card)
    return best[1] if best is not None else None


def _hold_facts(st, card: Approval, why: Dict[str, Any]) -> Dict[str, Any]:
    """What the lead row says around a send-time hold of ``card``, for its
    wording only (lead_reply_problem, _lead_reply_alert, _booking_note);
    ``why`` itself is what the hold records and returns. {} when the row
    cannot be read: the wording then claims nothing it cannot show.

    * An opt-out or a final no: "newer_reply", the lead's newest reply that
      is not a no, sent after it (_newest_reply_after), when there is one.
    * A newer reply: "after_card" when it came after the card was drafted
      (by the time the row records for it; with none, by the processing
      order the verdict fell back on); "holds_call", the booked call's
      label, when the card owns the lead's call; "newer_card", the card
      answering that newer reply ({"id", "status", "keeps_call": it owns or
      names the booked time}), or None when it raised none."""
    try:
        row = st.get(card.state_key)
        if not isinstance(row, dict):
            return {}
        if why.get("reason") == "opt_out":
            newer = _newest_reply_after(row, why.get("at"), exclude=why.get("email_id"))
            return {"newer_reply": newer} if newer else {}
        facts = {}  # type: Dict[str, Any]
        # The newer reply's recorded time, the verdict's "at" (received_at, else
        # when it was processed). A reply with no email time of its own, which
        # the verdict orders by processing, carries its processing time there:
        # after the drafting when it was processed after the card's own reply.
        # With no time at all, the order the verdict fell back on: processed
        # after the card's own reply, whose pipeline drafted it.
        sent, drafted = _time_of(why.get("at")), _time_of(card.created_at)
        if sent is not None:
            after_card = drafted is not None and sent > drafted
        else:
            processed = [str(x) for x in row.get("processed_email_ids") or []]
            newer_id, source_id = str(why.get("email_id") or ""), str(card.email_id or "")
            after_card = (newer_id in processed and source_id in processed
                          and processed.index(newer_id) > processed.index(source_id))
        if after_card:
            facts["after_card"] = True
        state = LeadState.from_store(row)
        slot = booking_of(state).get("slot")
        if slot and owns_booking(card, state):
            facts["holds_call"] = _slot_label(slot)
        answer = _card_answering(st, row, why.get("email_id"), skip=_approval_id(card))
        facts["newer_card"] = None
        if answer is not None:
            facts["newer_card"] = {"id": _approval_id(answer), "status": answer.status,
                                   "keeps_call": bool(slot) and (owns_booking(answer, state)
                                                                 or keeps_booked_slot(answer.draft, slot))}
        return facts
    except Exception as exc:  # noqa: BLE001 - the wording must never stop a hold
        logger.warning("could not read the lead row around the hold of %s: %s", _approval_id(card), exc)
        return {}


def _newer_card_note(why: Dict[str, Any]) -> str:
    """The HELD push's sentence on the card that answers the lead's newer
    reply ("newer_card", _hold_facts): where it stands, or that the newer
    reply raised none. "" when that was not looked up."""
    if "newer_card" not in why:
        return ""
    card = why.get("newer_card") or {}
    if not card:
        return " Their newer reply raised no card."
    status, card_id = card.get("status"), card.get("id")
    if status == "pending":
        return " Card %s answers their newer reply and is waiting on you." % card_id
    if status == "approved_queued":
        return (" Card %s answers their newer reply; it is approved and goes out when the sending window opens."
                % card_id)
    if status == "sending":
        return " Card %s answers their newer reply and is being sent." % card_id
    if status in SENT_STATUSES:
        return " Their newer reply was already answered (card %s)." % card_id
    return " Card %s, raised for their newer reply, is %s." % (card_id, status)


def _earlier_send_note(ids: List[str]) -> str:
    """The HELD push's sentence for held cards with a failed send attempt on
    record (_had_send_attempt): why holding them is safe, and that the lead
    may have that reply."""
    if not ids:
        return ""
    if len(ids) == 1:
        return (" Card %s had an earlier send attempt that failed: nothing of it is still in flight, but it may have "
                "reached the lead, so check the Instantly thread." % ids[0])
    return (" Cards %s had earlier send attempts that failed: nothing of them is still in flight, but they may have "
            "reached the lead, so check the Instantly thread." % ", ".join(ids))


def _lead_reply_alert(lead: str, why: Dict[str, Any], cards: List[str], booking_note: str = "",
                      earlier: Optional[List[str]] = None) -> Dict[str, Any]:
    """The HELD push, worded from the facts ``why`` carries besides the
    verdict (_hold_facts at send time; the arrival hold's "newer_reply" from
    app) and never beyond them. ``booking_note`` is _booking_note's sentence,
    not empty when a held card owns the lead's call.

    * An opt-out or a final no: Veto, and do not reply (what not to do
      depends on what the lead said, opt_out_advice). When the lead wrote
      again after it with something that is not a no ("newer_reply"), the
      push names that reply, says the no still stands, and asks for the whole
      thread to be read before the Veto.
    * The lead wrote again with something else: "after the card was drafted"
      only when that newer reply was sent after it ("after_card"), else
      "after the reply this card answers"; where the card answering the
      newer reply stands, or that it raised none (_newer_card_note); then
      read the thread and any newer card, and Veto or reply by hand, unless
      a held card owns the lead's call: a Veto would cancel it, so the
      booking note says what to do instead.

    ``earlier``: the held cards with a failed send attempt on record; the
    push then says nothing MORE was sent, and why."""
    category = str(why.get("category") or "unlabelled")
    when = _when_label(why.get("at"))
    many = len(cards) != 1
    blocked = ("Card%s %s %s now blocked and %s offered times are back in the pool."
               % ("s" if many else "", ", ".join(cards), "are" if many else "is", "their" if many else "its"))
    it = "them" if many else "it"
    opener = "Nothing more was sent." if earlier else "Nothing was sent."
    note = _earlier_send_note(list(earlier or []))
    if why.get("reason") == "opt_out":
        said = _LEAD_SAID.get(category, "gave a final no")
        title = "Reply to %s HELD: the lead %s" % (lead, said)
        newer = why.get("newer_reply") or {}
        if newer:
            message = ("%s The lead %s (%s, %s). They wrote again after it (%s, %s); this answer still stands. %s%s "
                       "Read the whole thread in Instantly before you Veto %s or anything else goes to them. %s%s"
                       % (opener, said, category, when, newer.get("label") or "unlabelled",
                          _when_label(newer.get("at")), blocked, note, it, opt_out_advice(category), booking_note))
        else:
            message = ("%s The lead %s (%s, %s). %s%s Veto %s. %s%s"
                       % (opener, said, category, when, blocked, note, it, opt_out_advice(category), booking_note))
    else:
        title = "Reply to %s HELD: the lead wrote again" % lead
        after = "after the card was drafted" if why.get("after_card") else "after the reply this card answers"
        if booking_note:
            todo = "Read the thread and any newer card for this lead before you do anything with %s." % it
        else:
            todo = "Read the thread and any newer card for this lead, then Veto %s or reply by hand." % it
        message = ("%s The lead wrote again %s (%s, %s), so the draft answers words they have moved past. %s%s%s "
                   "%s%s" % (opener, after, category, when, blocked, note, _newer_card_note(why), todo, booking_note))
    return _alert(title, message, priority="high")


def _hold_for_lead_reply(approval: Approval, st, ts: datetime, why: Dict[str, Any], allowed,
                         drop_claim: bool = False) -> Optional[Dict[str, Any]]:
    """Hold one card the lead's own words rule out: blocked with the stated
    problem, its offered times back in the pool, Lorenzo told. None when the
    status-guarded write lost (the card moved on; the caller answers "card
    changed"). ``drop_claim`` for a card the caller had moved to sending:
    nothing left the process, so its send claim goes too."""
    approval_id = _approval_id(approval)
    # Judged before the block moves the card: a Retry'd card's earlier failed
    # attempt is on its history; the caller's own attempt (a claim, "sending")
    # left nothing.
    earlier = _had_send_attempt(st, approval)
    # What the lead row says around this hold, for the wording only: ``why``
    # is what the hold records and the caller gets.
    told = dict(why, **_hold_facts(st, approval, why))
    problem = lead_reply_problem(told, earlier_send=earlier)
    if not _block_for_lead_reply(st, approval_id, ts, problem, allowed, why=why):
        return None
    if drop_claim:
        try:
            st.delete(SEND_CLAIM_PREFIX + approval_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not drop the unused send claim of %s: %s", approval_id, exc)
    release_slots(st, approval_id)
    approval.status = "blocked"
    approval.decided_at = ts.isoformat()
    approval.send_after = None
    approval.send_attempt = None
    if problem not in approval.draft.problems:
        approval.draft.problems = list(approval.draft.problems) + [problem]
    alert = _lead_reply_alert(approval.lead_email, told, [approval_id], _booking_note(st, [approval], told),
                              earlier=[approval_id] if earlier else None)
    logger.error("refusing to send %s: %s", approval_id, problem)
    job_log.log_run("reply_engine.approval", "blocked_lead_replied",
                    {"lead": approval.lead_email, "approval": approval_id, "reason": why.get("reason"),
                     "category": why.get("category"), "at": why.get("at"), "email_id": why.get("email_id")})
    return {"ok": False, "status": "blocked", "problems": [problem], "held": True, "lead_reply": why,
            "alert": alert}


def _drop_stale_send_claim(st, approval_id: str, ts: datetime) -> bool:
    """The send claim of a send_failed card just held for the lead's opt-out.
    It is stale: the attempt that took it has ended. Recorded in the card's
    history first, as retry() does, so card_history still says a send from
    the card started and may have reached the lead; kept when that record
    cannot be written. True when it was dropped."""
    try:
        _note_card_history(st, approval_id, ts, approved=True, send_attempts=1)
    except Exception as exc:  # noqa: BLE001 - no record, no drop: the claim is the proof
        logger.warning("keeping the send claim of %s: its send attempt could not be recorded: %s", approval_id, exc)
        return False
    try:
        st.delete(SEND_CLAIM_PREFIX + approval_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not drop the stale send claim of %s: %s", approval_id, exc)
        return False
    return True


def hold_cards_for_lead_reply(store, tokens: Optional[List[str]], why: Dict[str, Any],
                              now: Optional[datetime] = None, lead: Optional[str] = None) -> List[str]:
    """At arrival of an opt-out or final no: block every open card of the
    lead's (LEAD_HOLD_STATUSES) with the stated problem, release its offered
    times, and tell Lorenzo once. Returns the ids it held. Never raises.

    * A card already blocked for the same reason (LEAD_HOLD_KEY, or its stated
      problem on a card blocked before that record existed) is left as it is
      and not announced again. One blocked because the lead wrote again is
      held for the opt-out: that changes what to do (do not reply).
    * A card holding a send claim is left alone, and the send re-checks the
      lead row after it moves to sending (lead_reply_hold), so one of the two
      always sees the other: a pending or queued card with a claim may be
      mid-send, between the claim and "sending".
    * Except a send_failed card: nothing of it can be in flight. send_failed
      is written only once a send attempt has ended (send_approved after
      Instantly raised; the recipient hold's escalation, which drops the
      claim first; Keep reopening an expired card, which no send can be
      running for), and no new send can start from it (a send starts only
      from pending or approved_queued, and only Retry leaves send_failed, by
      a status-guarded write). The block here is guarded the same way, from
      send_failed only, so it and a Retry cannot both win. Its claim is then
      stale: recorded in the card's history and dropped
      (_drop_stale_send_claim), so the blocked card expires at its TTL and the
      stuck-card push stops asking Lorenzo to Retry a reply to a lead who
      said no. The push and the card's problem say nothing MORE was sent
      for it (its failed attempt may have reached the lead) and that nothing
      of it is in flight (_had_send_attempt, _earlier_send_note)."""
    st = _store(store)
    ts = _now(now)
    reason = why.get("reason")
    held = []  # type: List[str]
    earlier = []  # type: List[str]
    cards = []  # type: List[Approval]
    seen = set()  # type: set
    for token in tokens or []:
        approval_id = str(token).split(".", 1)[0]
        if not approval_id or approval_id in seen:
            continue
        seen.add(approval_id)
        try:
            card = _approval_row(st, approval_id)
            if card is None or card.status not in LEAD_HOLD_STATUSES:
                continue
            if card.status == "blocked" and _held_for(card) == reason:
                continue  # already held for this: no second block, no second push
            claimed = _holds_send_claim(st, approval_id)
            if claimed and card.status != "send_failed":
                logger.warning("not holding %s at arrival: it holds a send claim; the send re-checks", approval_id)
                continue
            allowed = ("send_failed",) if claimed else LEAD_HOLD_STATUSES
            tried = _had_send_attempt(st, card)
            if not _block_for_lead_reply(st, approval_id, ts, lead_reply_problem(why, earlier_send=tried), allowed,
                                         why=why):
                continue
            if claimed:
                _drop_stale_send_claim(st, approval_id, ts)
            release_slots(st, approval_id)
            held.append(approval_id)
            if tried:
                earlier.append(approval_id)
            cards.append(card)
            lead = lead or card.lead_email
        except Exception as exc:  # noqa: BLE001 - one bad card must not stop the rest
            logger.warning("could not hold card %s for the lead's reply: %s", approval_id, exc)
    if held:
        _lead_reply_alert(lead or "the lead", why, held, _booking_note(st, cards, why), earlier=earlier)
        job_log.log_run("reply_engine.approval", "blocked_lead_replied",
                        {"lead": lead, "approvals": held, "reason": why.get("reason"),
                         "category": why.get("category"), "at": why.get("at"), "email_id": why.get("email_id"),
                         "at_arrival": True, "earlier_send": earlier})
    return held


def _arm_under_lock(approval: Approval, open_cards: Dict[str, bool], now: datetime, box: Dict[str, Any],
                    seen_before: Optional[List[str]] = None, reply_at: Any = None):
    """save_lead_state's ``finish`` for a sent reply: arm the ladder on the row
    as it stands under the lock, or leave its cadence exactly as stored.

    Refused (arm_refusal), nothing in the cadence moves: stopped_reason,
    needs_fresh_draft and everything else stay as the store has them, and the
    status stays whatever the newer reply set. Armed, the ladder records which
    inbound this answer covered (armed_for_email_id), so the pipeline of that
    same reply, if it is still writing, does not stop what its own approval
    armed (app._inbound_stop_hook)."""

    def _finish(merged: Dict[str, Any]) -> Dict[str, Any]:
        why = arm_refusal(merged, approval, open_cards, seen_before=seen_before, reply_at=reply_at)
        if why:
            box["result"] = {"armed": False, "reason": why}
            logger.warning("not arming the cadence for %s: %s", approval.lead_email, why)
            return merged
        try:
            holder = LeadState.from_store(merged)
        except Exception as exc:  # noqa: BLE001 - an unreadable row is written back as it stands, unarmed
            box["result"] = {"armed": False, "error": "unreadable lead row: %s" % exc}
            return merged
        box["result"] = _arm_cadence(holder, now)
        cad = dict(holder.cadence or {})
        cad["armed_for_email_id"] = approval.email_id
        return dict(merged, cadence=cad, status="replied_awaiting_booking")

    return _finish


def _keep_stored_problems(new: Dict[str, Any], current: Any) -> Dict[str, Any]:
    """A whole-card write never drops a problem another writer put on the
    stored card since this copy was read (an older reply's time mark,
    app._mark_time_conflicts): the stored card's problems this copy lacks
    are kept, after its own."""
    stored = ((current or {}).get("draft") or {}).get("problems") if isinstance(current, dict) else None
    if not stored:
        return new
    draft = dict(new.get("draft") or {})
    mine = list(draft.get("problems") or [])
    extra = [p for p in stored if p not in mine]
    if extra:
        draft["problems"] = mine + extra
        new = dict(new, draft=draft)
    return new


def _save_open(approval: Approval, st) -> bool:
    """Save the whole card only while the stored one is still sendable
    (pending or queued), under the store's lock. False when it moved on
    (expired, vetoed, superseded, another send): nothing was written. A
    problem put on the stored card meanwhile is kept (_keep_stored_problems)."""
    return _transition(st, _approval_id(approval), SENDABLE_STATUSES,
                       lambda row: _keep_stored_problems(approval.model_dump(mode="json"), row))


def _rewrite_card(st, approval: Approval, read_status: str, fields) -> Optional[str]:
    """Write ``fields`` of ``approval`` over the stored card, with a fresh
    token for its draft, only while the stored card is still at
    ``read_status`` (the status the caller read), under the store's lock:
    edit and accept_requested. The token is signed with the stored card's own
    expires_at, and the rest of the stored card is kept as it is. Returns
    the new token (also set on ``approval``), or None when the card moved on
    and nothing was written."""
    approval_id = _approval_id(approval)
    new = approval.model_dump(mode="json")
    dhash = draft_hash(approval.draft)
    box = {}  # type: Dict[str, Any]

    def _rewrite(row):
        for field in fields:
            row[field] = new[field]
        expires_at = row.get("expires_at") or approval.expires_at
        row["token"] = make_token(approval_id, approval.state_key, dhash, expires_at)
        box.update(token=row["token"], expires_at=expires_at)
        return row

    if not _transition(st, approval_id, (read_status,), _rewrite):
        return None
    approval.token, approval.expires_at = box["token"], box["expires_at"]
    return box["token"]


def _card_changed(st, approval_id: str) -> Dict[str, Any]:
    """The answer for a send that lost its status-guarded write."""
    try:
        current = (st.get(APPROVAL_PREFIX + approval_id) or {}).get("status")
    except Exception:  # noqa: BLE001
        current = None
    return {"ok": False, "error": "the card changed before the send started (it is now %s); nothing was sent"
            % (current or "unknown"), "status": current}


# The lead-history events that record an answer reaching the lead: the
# engine's own send, and one Lorenzo marked sent (mark_sent_manually). A
# shadow "reply_would_send" is neither.
REPLY_SENT_EVENTS = ("reply_sent", "reply_sent_manually")


def _is_first_reply(state: Optional[LeadState]) -> bool:
    """Is an answer going out now the lead's first one from us? True when
    there is no lead row to say otherwise."""
    return state is None or not any(isinstance(e, dict) and e.get("event") in REPLY_SENT_EVENTS
                                    for e in (state.history or []))


def _save_unless_sent(approval: Approval, st) -> Optional[Dict[str, Any]]:
    """Write the whole card, as _save does, unless the stored card is
    already recorded as sent (SENT_STATUSES), under the store's lock: the
    send whose stale claim Mark sent took over (mark_sent_manually) never
    overwrites what it recorded, and a problem put on the stored card
    meanwhile is kept (_keep_stored_problems). None when written; the stored
    row when refused."""
    box = {}  # type: Dict[str, Any]

    def _apply(current):
        if isinstance(current, dict) and current.get("status") in SENT_STATUSES:
            box["refused"] = dict(current)
            return current
        return _keep_stored_problems(approval.model_dump(mode="json"), current)

    key = APPROVAL_PREFIX + _approval_id(approval)
    mutate = getattr(st, "mutate", None)
    if callable(mutate):
        try:
            mutate(key, _apply)
            return box.get("refused")
        except NotImplementedError:
            pass
    new = _apply(st.get(key))
    if "refused" not in box:
        st.set(key, new)
    return box.get("refused")


def _still_this_send(st, approval_id: str, attempt: Optional[str]) -> bool:
    """Is the stored card still this send's (sending, this send_attempt)?
    Read right before the Instantly call: a Mark sent that took the card
    over once its claim was past SEND_CLAIM_LEASE_MINUTES, or a Retry, may
    have moved it while this worker was held up, and the reply must then not
    go out from here. A store that cannot be read says yes, as it did before
    this check."""
    try:
        row = st.get(APPROVAL_PREFIX + approval_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not re-read card %s before its send: %s", approval_id, exc)
        return True
    return isinstance(row, dict) and row.get("status") == "sending" and row.get("send_attempt") == attempt


def _sent_after_card_sent(approval: Approval, approval_id: str, taken: Dict[str, Any], reply: Any, shadow: bool,
                          ts: datetime) -> Dict[str, Any]:
    """This send went through, but its card was already recorded as sent:
    Mark sent took it over once its claim was past SEND_CLAIM_LEASE_MINUTES
    (this worker was held up, a suspended process), or another send of it
    finished first. Nothing more is recorded: no history, no ladder, no
    interest status, no invite and no second sent row, so the reply is
    counted once. Its own Job_Log failure row and a push: the lead may have
    two replies. Never raises."""
    status = str(taken.get("status") or "sent")
    marked = (taken.get("notify_result") or {}).get(MARK_SENT_KEY) if isinstance(taken.get("notify_result"),
                                                                                 dict) else None
    marked_at = marked.get("at") if isinstance(marked, dict) else None
    logger.error("the reply for %s went through after card %s was already %s; nothing more is recorded",
                 approval.lead_email, approval_id, status)
    job_log.log_run("reply_engine.approval", "sent_after_card_sent",
                    {"lead": approval.lead_email, "approval": approval_id, "email_id": approval.email_id,
                     "card_status": status, "marked_sent_at": marked_at, "send_started_at": ts.isoformat(),
                     "shadow": shadow})
    if status == "sent_manually":
        what = "marked sent%s" % (" (%s)" % _when_label(marked_at) if marked_at else "")
        who = "If you also replied by hand, the lead has two replies: check the Instantly thread."
    else:
        what = "sent by another send of it"
        who = "The lead has two replies: check the Instantly thread."
    note = " Shadow mode: this send was recorded as would_do, nothing was sent." if shadow else ""
    alert = _alert("Reply to %s went out after its card was already %s" % (approval.lead_email,
                                                                            "marked sent" if status == "sent_manually"
                                                                            else "sent"),
                   "Card %s was already %s when this send of it, started %s, went through as well. %s Nothing more "
                   "was recorded: the card stays %s.%s" % (approval_id, what, _when_label(ts.isoformat()), who,
                                                            status, note))
    return {"ok": True, "status": status, "shadow": shadow, "reply": reply, "interest": None,
            "interest_value": None, "interest_error": None, "cadence": None, "invite": None, "show_rate": None,
            "booking_released": None, "already": status, "alert": alert}


def send_approved(approval: Approval, instantly, store=None, now: Optional[datetime] = None, ghl=None) -> Dict[str, Any]:
    """Send one approved reply exactly once.

    The order matters: the status transition is written AHEAD of the Instantly
    call and re-read from the store first. Previously the send happened before
    any state was persisted, so a 5xx on the interest update, a store error or a
    Modal worker kill left the approval 'pending' while the customer already had
    the email - and poller.run_once calls flush_queued on every tick, so the
    retry was automatic and silent.
    """
    st = _store(store)
    ts = _now(now)
    draft = approval.draft
    approval_id = approval.token.split(".", 1)[0]
    problems = list(draft.problems)
    if problems:
        approval.status = "blocked"
        if not _save_open(approval, st):
            return _card_changed(st, approval_id)
        return {"ok": False, "status": approval.status, "problems": problems}
    persisted = st.get(APPROVAL_PREFIX + approval_id) or {}
    current = persisted.get("status") or approval.status
    if current not in SENDABLE_STATUSES:
        return {"ok": False, "error": "already %s" % current, "status": current}
    # CT3: a card nobody tapped (approved_by "template") goes out only while
    # the gate still allows its exact subject and body: a revoke, the kill
    # switch, a redeploy or a changed hash between the auto-approve and this
    # send (the 07:00 flush of a card queued overnight) turns it back into a
    # pending card, pushed to Lorenzo. Every check below still runs after it.
    if approval.approved_by == "template":
        verdict = _template_verdict(approval, st.get(approval.state_key))
        if not verdict.allowed:
            return _refuse_template_send(approval, st, ts, approval_id, verdict)
    # A synthesised webhook id is an idempotency key, never a thread handle.
    # Instantly answers 4xx to reply_to_uuid="wh:kim@acme.com:...", and a
    # send_failed row is something nobody watches.
    if is_synthetic_email_id(approval.email_id):
        approval.status = "blocked"
        approval.decided_at = ts.isoformat()
        problems = ["no Instantly email id on this reply (the webhook carried none), so it cannot be answered in "
                    "thread; reply by hand from the Instantly inbox"]
        approval.draft.problems = problems
        if not _save_open(approval, st):
            return _card_changed(st, approval_id)
        logger.error("refusing to send %s: synthetic email id %s", approval_id, approval.email_id)
        job_log.log_run("reply_engine.approval", "blocked_synthetic_email_id",
                        {"lead": approval.lead_email, "email_id": approval.email_id})
        return {"ok": False, "status": approval.status, "problems": problems}
    state_raw = st.get(approval.state_key)
    state = LeadState.from_store(state_raw) if state_raw else None
    # The card's context (when the lead's reply landed, and what the lead row
    # held then) is read here, BEFORE the card moves to sending, and carried
    # through the send: the sweep deletes a sent card's row, and a read after
    # the "sent" save could find it gone (seen_before None skipped the
    # crash-gap check below and reply_at was lost).
    context = card_context(st, approval_id)
    seen_before = context.get("processed_before")
    seen_before = seen_before if isinstance(seen_before, list) else None
    # When the lead sent the reply this card answers: every "did they write
    # again since" check below reads the router's rule against it
    # (lead_replies_after: send times where both show them, else the order
    # the replies were processed in).
    reply_at = context.get("reply_at")
    # The lead's own words since this card was drafted come first: the sticky
    # opt-out marker, an opt-out, a final no, or a newer reply. A queued card
    # never expires, so without this the Monday flush sent the Friday answer
    # to a lead who asked on Saturday to be removed.
    why = lead_reply_hold(state_raw, approval, seen_before, reply_at=reply_at)
    if why:
        held = _hold_for_lead_reply(approval, st, ts, why, SENDABLE_STATUSES)
        return held if held is not None else _card_changed(st, approval_id)
    # A card that owns the lead's unconfirmed booking releases the GHL invite
    # and the reminder ladder when it goes out. What it does with the booking
    # is decided by a RECORDED intent, never by reading its own words: the
    # engine's intent for an unedited draft (record_booking_intent, written
    # when the card took the booking), or the Keep / Release choice Lorenzo
    # made on the Edit page, bound to that booking (owner_booking_decision).
    # The text reader used to decide, and "Thu 3:00pm CT just got taken, could
    # you do Friday at 1 instead?" confirmed Thursday with to_notify=True.
    owner = owns_booking(approval, state)
    booked_slot = booking_of(state).get("slot") if owner else None
    confirm_booking = False
    release_after_send = False
    if owner and not _slot_in_future(booked_slot, ts):
        return _refuse_passed_booking(approval, st, ts, state, booked_slot, ghl, instantly, base_raw=state_raw)
    if not owner and approval.draft.model == "edited" and st.get(BOOKING_CHOICE_PREFIX + approval_id):
        # Lorenzo chose Keep / Release for a booking this card no longer holds
        # (superseded, released or cancelled since): ask again, send nothing.
        try:
            st.delete(BOOKING_CHOICE_PREFIX + approval_id)
        except Exception:  # noqa: BLE001
            pass
        problem = ("the booked call you chose Keep or Release for is no longer held by this card (it was "
                   "superseded, released or cancelled): open Edit and check the text before sending")
        approval.status = "blocked"
        approval.decided_at = ts.isoformat()
        approval.draft.problems = list(approval.draft.problems) + [problem]
        if not _save_open(approval, st):
            return _card_changed(st, approval_id)
        return {"ok": False, "status": approval.status, "problems": [problem], "needs_booking_choice": True}
    if owner:
        decision, problem = owner_booking_decision(st, approval, state)
        if decision == "keep" and not _slot_in_future(booked_slot, ts + timedelta(minutes=CONFIRM_MARGIN_MINUTES)):
            return _hold_too_close_to_confirm(approval, st, ts, booked_slot)
        if decision == "keep":
            confirm_booking = True
        elif decision == "release":
            release_after_send = True
        else:
            approval.status = "blocked"
            approval.decided_at = ts.isoformat()
            approval.draft.problems = list(approval.draft.problems) + [problem]
            if not _save_open(approval, st):
                return _card_changed(st, approval_id)
            logger.error("refusing to send %s: %s", approval_id, problem)
            job_log.log_run("reply_engine.approval", "blocked_booking_choice",
                            {"lead": approval.lead_email, "approval": approval_id, "slot": booked_slot})
            return {"ok": False, "status": approval.status, "problems": [problem], "needs_booking_choice": True}
    # The 48 h TTL is far longer than the 4 h slot horizon, so a card approved a
    # day later could offer a time that has already passed - and format_slot
    # carries no date, so "Mon 2:00pm" reads as the coming Monday. The booked
    # time an owner card confirms is not an offer (checked above instead).
    offered_now = [iso for iso in draft.offered_slots if not (owner and _same_slot(iso, booked_slot))]
    stale = stale_slots(offered_now, ts, booked=_booked_slots_for(state))
    if stale:
        approval.status = "stale_slots"
        approval.decided_at = ts.isoformat()
        if not _save_open(approval, st):
            return _card_changed(st, approval_id)
        logger.error("refusing to send %s: offered slots are no longer offerable: %s", approval_id, stale)
        job_log.log_run("reply_engine.approval", "stale_slots",
                        {"lead": approval.lead_email, "slots": stale, "created_at": approval.created_at})
        return {"ok": False, "status": approval.status, "error": "offered slots are no longer offerable", "stale_slots": stale}
    invite_problem = _invite_claim_problem(approval, state)
    if invite_problem is None and release_after_send and claims_invite(draft.body_text):
        invite_problem = ("you chose to release the booked call, but the draft still tells the lead a calendar "
                          "invite exists")
    if invite_problem:
        approval.status = "blocked"
        approval.decided_at = ts.isoformat()
        approval.draft.problems = list(approval.draft.problems) + [invite_problem]
        if not _save_open(approval, st):
            return _card_changed(st, approval_id)
        logger.error("refusing to send %s: %s", approval_id, invite_problem)
        job_log.log_run("reply_engine.approval", "blocked_invite_claim",
                        {"lead": approval.lead_email, "approval": approval_id})
        return {"ok": False, "status": approval.status, "problems": [invite_problem]}
    attempt = _claim_send(st, approval_id, ts)
    if attempt is None:
        return {"ok": False, "error": "a send for this approval is already in flight", "status": "sending"}
    # "-> sending" only from a sendable status, under the store's lock
    # (re-review R1 item 3). The status check above is a plain read: the
    # tick's expiry, a veto or a newer reply's supersede can land between it
    # and here, and the whole-card save that used to stand here wrote
    # "sending" over them and sent anyway. Lost, nothing has left the
    # process: the claim just won is dropped (so a Keep or a Retry is not
    # told a send is in flight) and nothing is sent.
    approval.status = "sending"
    approval.send_attempt = attempt
    # A problem put on the stored card since the read at the top (an older
    # reply's proposed time, app._mark_time_conflicts, is written onto a
    # pending or queued card) refuses the send here, in the same locked
    # write: the card is blocked with the stored problems, never sent over
    # them (S-rest round 6 approval, flag 19).
    marked = {}  # type: Dict[str, Any]

    def _to_sending(row):
        stored = list((row.get("draft") or {}).get("problems") or [])
        if stored:
            marked["problems"] = stored
            row["status"] = "blocked"
            row["decided_at"] = ts.isoformat()
            return row
        row["status"] = "sending"
        row["send_attempt"] = attempt
        return row

    if not _transition(st, approval_id, SENDABLE_STATUSES, _to_sending) or marked:
        try:
            st.delete(SEND_CLAIM_PREFIX + approval_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not drop the unused send claim of %s: %s", approval_id, exc)
        if marked:
            approval.status = "blocked"
            approval.send_attempt = None
            approval.decided_at = ts.isoformat()
            approval.draft.problems = list(marked["problems"])
            logger.error("refusing to send %s: the stored card has problems: %s", approval_id, marked["problems"])
            job_log.log_run("reply_engine.approval", "blocked_marked_meanwhile",
                            {"lead": approval.lead_email, "approval": approval_id})
            return {"ok": False, "status": "blocked", "problems": list(marked["problems"])}
        logger.warning("not sending %s: the card changed before the send started", approval_id)
        return _card_changed(st, approval_id)
    # Last look at the lead row, now that the card is "sending": an opt-out
    # that landed since the read above is on the row (the reply pipeline
    # writes it before it holds the lead's open cards, and that hold leaves a
    # card in "sending" to this check), so one of the two always sees the
    # other. A row that cannot be read puts the card back as it was.
    try:
        lead_row = st.get(approval.state_key)
    except Exception as exc:  # noqa: BLE001
        def _back(row):
            row["status"] = current
            row["send_attempt"] = None
            return row

        _transition(st, approval_id, ("sending",), _back)
        try:
            st.delete(SEND_CLAIM_PREFIX + approval_id)
        except Exception as exc2:  # noqa: BLE001
            logger.warning("could not drop the unused send claim of %s: %s", approval_id, exc2)
        logger.warning("not sending %s: the lead row could not be re-read: %s", approval_id, exc)
        return {"ok": False, "status": current,
                "error": "could not re-read the lead's row before the send (%s); nothing was sent" % exc}
    why = lead_reply_hold(lead_row, approval, seen_before, reply_at=reply_at)
    if why:
        held = _hold_for_lead_reply(approval, st, ts, why, ("sending",), drop_claim=True)
        return held if held is not None else _card_changed(st, approval_id)
    # `to` makes Instantly validate the recipient against the thread before it
    # sends. It has to be the address that actually wrote the thread
    # (from_address_email), which is not always the CRM address in lead_email.
    recipient = approval.reply_to or approval.lead_email
    # Second belt, per config/instantly_api_contract.md and CLAUDE.md: re-read
    # the email by id and refuse unless its from_address_email IS the recipient.
    # `to` is derived from the same message, so it is self-consistent by
    # construction and cannot catch a stale or crossed reply_to_uuid; this can.
    # Nine unattended cadence touches already ride this check (cadence._send);
    # the first human-approved reply is the highest-stakes send of all and had
    # only one belt. In live only a confirmed match sends (decision R6): a
    # mismatch, a read error or a timeout holds the card and alerts Lorenzo.
    if settings.is_live():
        verdict = _recipient_verdict(approval, recipient, instantly)
        if verdict is not True:
            return _hold_for_recipient(approval, st, ts, approval_id, recipient, verdict)
        try:
            st.delete(RECIPIENT_HOLD_PREFIX + approval_id)
        except Exception:  # noqa: BLE001 - bookkeeping only
            pass
    # Last look at the card itself: a Mark sent that took it over once its
    # claim was past SEND_CLAIM_LEASE_MINUTES, or a Retry, may have moved it
    # while this worker was held up. The reply then does not go out from here.
    if not _still_this_send(st, approval_id, attempt):
        logger.warning("not sending %s: the card is no longer this send's", approval_id)
        return _card_changed(st, approval_id)
    try:
        reply = instantly.reply_to_email(approval.email_id, approval.eaccount, draft.subject, draft.body_text,
                                         to=recipient)
    except Exception as exc:  # noqa: BLE001 - never leave the row re-sendable
        approval.status = "send_failed"
        approval.decided_at = ts.isoformat()
        # Never over a card already recorded as sent (Mark sent took it over).
        taken = _save_unless_sent(approval, st)
        logger.exception("reply send failed for %s", approval.lead_email)
        job_log.log_run("reply_engine.approval", "send_failed",
                        dict({"lead": approval.lead_email, "error": str(exc)},
                             **({"card_status": taken.get("status")} if taken is not None else {})))
        if taken is not None:
            return {"ok": False, "error": "send failed: %s; the card was already %s and was left as it is"
                    % (exc, taken.get("status")), "status": taken.get("status")}
        return {"ok": False, "error": "send failed: %s" % exc, "status": approval.status}
    shadow = isinstance(reply, dict) and bool(reply.get("shadow"))
    # persisted before anything else can fail, and never over a card already
    # recorded as sent: then the one that recorded it did the bookkeeping,
    # and nothing is recorded twice (_sent_after_card_sent).
    approval.status = "sent"
    approval.decided_at = ts.isoformat()
    taken = _save_unless_sent(approval, st)
    if taken is not None:
        return _sent_after_card_sent(approval, approval_id, taken, reply, shadow, ts)

    # Re-read: the state may have moved between the staleness check and here.
    state_raw = st.get(approval.state_key)
    state = LeadState.from_store(state_raw) if state_raw else state
    interest_value = _interest_value_for(approval, state)
    interest = None
    interest_error = None
    if interest_value is not None:
        # Unguarded, this aborted everything after it: the email was already
        # sent, but state.last_outbound_at, the 'replied_awaiting_booking'
        # status, the offered-slot record and the nine-touch S2 ladder were all
        # skipped - and the exception escaped flush_queued, so every other
        # queued lead in the same flush was never attempted either.
        try:
            interest = instantly.update_interest_status(approval.lead_email, approval.campaign_id, interest_value)
        except Exception as exc:  # noqa: BLE001 - the email is out; the cadence must still arm
            interest_error = str(exc)
            logger.exception("interest status failed after a sent reply for %s", approval.lead_email)
            job_log.log_run("reply_engine.approval", "interest_failed_after_send",
                            {"lead": approval.lead_email, "campaign_id": approval.campaign_id,
                             "interest_value": interest_value, "error": interest_error})
    invite = None
    show_rate_release = None
    booking_released = None
    # Ownership, not the label: a card that took the booking over from a
    # superseded booking_confirmation is an ordinary positive_* card. Decided
    # above from the recorded intent or choice: confirm_booking for Keep,
    # release_after_send for Release.
    if release_after_send and state is not None and owns_booking(approval, state):
        # The lead was never told about that call: cancel it silently. A failed
        # cancel keeps the booking held and retries (cancel_booking).
        booking_released = cancel_booking(state, ghl, instantly, ts, store=st, reason="released_on_edit")
        state.history.append({"at": ts.isoformat(), "event": "booking_released", "from": approval_id,
                              "slot": booked_slot, "reason": "released_on_edit",
                              "cancelled": booking_cancel_done(booking_released)})
    if confirm_booking and owns_booking(approval, state):
        invite = release_booking_invite(state, ghl, ts)
        # ...and the engine's own ladder, which booking.register_booking armed
        # HELD. Both halves of "the invite is on its way" are released here, by
        # the send, so nothing reaches the prospect before the approval tap.
        # Only the engine's own unedited draft (Keep by its recorded intent:
        # it restates the booked slot) counts as the confirmation, so the
        # ladder's confirm_email / confirm_sms are skipped; an edited body
        # (Keep on the Edit page) says what Lorenzo wrote, so they stay.
        show_rate_release = release_show_rate_hold(
            state, st, ts, reason="approved_edited" if approval.draft.model == "edited" else "approved")
        if isinstance(show_rate_release, dict) and show_rate_release.get("error"):
            _alert("Show-rate reminders NOT started for %s" % approval.lead_email,
                   "The confirmation reply went out, but the held reminder ladder for appointment %s could not be "
                   "released (%s). Check the appointment's reminders by hand."
                   % (show_rate_release.get("appointment_id"), show_rate_release.get("error")))
        _mark_booking_confirmed(state, approval_id, ts, invite)
    cadence_result = None
    # Time to first reply (OPS-10): when the lead's reply landed (recorded on
    # the card when it was raised, reply_at above) and when this answer went
    # out, on the lead's history and on the Job_Log row the metric reads. An
    # answer marked sent by hand earlier (mark_sent_manually) was a reply too.
    first_reply = _is_first_reply(state)
    if state is not None:
        state.last_outbound_at = ts.isoformat()
        for iso in draft.offered_slots:
            if iso not in state.offered_slots:
                state.offered_slots.append(iso)
        state.history.append({"at": ts.isoformat(), "event": "reply_sent" if not shadow else "reply_would_send",
                              "approval": approval_id, "reply_at": reply_at, "sent_at": ts.isoformat(),
                              "first_reply": first_reply})
        # Whether this reply arms the follow-up ladder is decided under the lead
        # row's lock, against the row as it stands then, never against the copy
        # read above: a reply the lead sent while this one was going out may
        # already be on the row, its card pending. Arming over it stamped
        # armed_at at send time, later than that reply's own timestamp, so the
        # tick's inbound check never fired and D1 (or a mid-ladder D2) went out
        # on top of the unanswered card.
        box = {}  # type: Dict[str, Any]
        save_lead_state(st, state, state_raw,
                        finish=_arm_under_lock(approval, _open_other_cards(st, approval, state_raw, ts), ts, box,
                                               seen_before=seen_before, reply_at=reply_at))
        cadence_result = box.get("result") or {"armed": False, "error": "the arm decision did not run"}
    # "approval" lets services/metrics/sources.first_reply_minutes pair this
    # row with the card's "created" row when reply_at is missing here.
    job_log.log_run("reply_engine.approval", "sent" if not shadow else "would_send",
                    {"lead": approval.lead_email, "approval": approval_id, "to": recipient,
                     "campaign_id": approval.campaign_id, "eaccount": approval.eaccount,
                     "email_id": approval.email_id, "subject": draft.subject, "slots": draft.offered_slots,
                     "reply_at": reply_at, "sent_at": ts.isoformat(), "first_reply": first_reply,
                     "interest_value": interest_value, "interest_error": interest_error, "invite": invite,
                     "show_rate_released": bool((show_rate_release or {}).get("released")),
                     "booking_released": booking_cancel_done(booking_released) if booking_released else None,
                     "cadence_armed": bool((cadence_result or {}).get("armed")),
                     "cadence_not_armed": None if (cadence_result or {}).get("armed") else
                     ((cadence_result or {}).get("reason") or (cadence_result or {}).get("error"))})
    return {"ok": True, "status": approval.status, "shadow": shadow, "reply": reply, "interest": interest,
            "interest_value": interest_value, "interest_error": interest_error, "cadence": cadence_result,
            "invite": invite, "show_rate": show_rate_release, "booking_released": booking_released}


BOOKING_CHOICE_PREFIX = "booking_choice:"
BOOKING_INTENT_PREFIX = "booking_intent:"
BOOKING_CHOICES = ("keep", "release")
# A confirmation needs the lead to read it, accept the invite and turn up: a
# call less than an hour away is not confirmed by email, it is handled by hand.
CONFIRM_MARGIN_MINUTES = 60


def _booking_binding(state: Optional[LeadState]) -> Dict[str, Any]:
    booking = booking_of(state)
    return {"appointment_id": booking.get("appointment_id"), "slot": booking.get("slot")}


def _bound_to(record: Dict[str, Any], state: Optional[LeadState]) -> bool:
    now_binding = _booking_binding(state)
    return (str(record.get("appointment_id")) == str(now_binding.get("appointment_id"))
            and _same_slot(record.get("slot"), now_binding.get("slot")))


def record_booking_intent(store, approval: Approval, state: Optional[LeadState]) -> Optional[Dict[str, Any]]:
    """Record, when a card takes a booking, whether the engine's own draft
    restates that booking. Structural (the draft's offered_slots is exactly
    the booked slot), never read from the prose, and bound to the booking and
    to this exact draft text. Never raises."""
    try:
        if state is None or not owns_booking(approval, state):
            return None
        binding = _booking_binding(state)
        rec = dict(binding, restates=keeps_booked_slot(approval.draft, binding.get("slot")),
                   draft_hash=draft_hash(approval.draft), approval=_approval_id(approval))
        _store(store).set(BOOKING_INTENT_PREFIX + _approval_id(approval), rec)
        return rec
    except Exception as exc:  # noqa: BLE001 - the card exists; without an intent the send falls back to
        # owner_booking_decision's structural test (offered_slots is exactly the booked slot)
        logger.warning("could not record the booking intent for %s: %s", approval.lead_email, exc)
        return None


def owner_booking_decision(store, approval: Approval, state: Optional[LeadState]):
    """('keep' | 'release', None), or (None, problem) when the card may not go
    out until Lorenzo chooses (again) on the Edit page.

    * An edited card (draft.model == 'edited') goes by the Keep / Release
      choice recorded by edit(). The choice is bound to the booking's
      appointment id and slot and to the saved text: a booking that changed
      since (superseded, released, rescheduled) or a text changed without a
      new choice asks again.
    * An unedited engine draft goes by the intent recorded when it took the
      booking; a card from before intents existed falls back to the same
      structural test (offered_slots is exactly the booked slot).
    """
    st = _store(store)
    approval_id = _approval_id(approval)
    label = _slot_label(booking_of(state).get("slot"))
    if approval.draft.model == "edited":
        choice = st.get(BOOKING_CHOICE_PREFIX + approval_id) or {}
        if choice.get("choice") not in BOOKING_CHOICES:
            return None, ("this card holds the call booked for %s: open Edit and choose Keep the call or "
                          "Release the call before sending" % label)
        if not _bound_to(choice, state) or choice.get("draft_hash") != draft_hash(approval.draft):
            try:
                st.delete(BOOKING_CHOICE_PREFIX + approval_id)
            except Exception:  # noqa: BLE001
                pass
            return None, ("the booking this card holds changed after you chose %s (it is now %s): open Edit and "
                          "choose again" % (choice.get("choice"), label))
        return choice["choice"], None
    intent = st.get(BOOKING_INTENT_PREFIX + approval_id)
    if isinstance(intent, dict):
        if not _bound_to(intent, state) or intent.get("draft_hash") != draft_hash(approval.draft):
            return None, ("the booking this card holds changed after the draft was written (it is now %s): open "
                          "Edit and choose Keep the call or Release the call" % label)
        restates = bool(intent.get("restates"))
    else:
        restates = keeps_booked_slot(approval.draft, booking_of(state).get("slot"))
    if restates:
        return "keep", None
    return None, ("this card holds the call booked for %s but its draft does not restate it: open Edit and "
                  "choose Keep the call or Release the call" % label)


def _hold_too_close_to_confirm(approval: Approval, st, ts: datetime, booked_slot: Optional[str]) -> Dict[str, Any]:
    """Less than CONFIRM_MARGIN_MINUTES before the call: nothing is confirmed
    by email. The card is blocked with a problem saying so, the booking and
    its held reminders stay (the lead did ask for that time), and Lorenzo is
    told to handle it by hand."""
    approval_id = _approval_id(approval)
    label = _slot_label(booked_slot)
    problem = ("the call at %s is less than %d minutes away, too close to confirm by email. Nothing was sent; the "
               "call stays on the calendar with its reminders held. Handle it by hand (message or call the lead), "
               "then veto this card to cancel the call or leave it" % (label, CONFIRM_MARGIN_MINUTES))
    approval.status = "blocked"
    approval.decided_at = ts.isoformat()
    approval.draft.problems = list(approval.draft.problems) + [problem]
    if not _save_open(approval, st):
        return _card_changed(st, approval_id)
    job_log.log_run("reply_engine.approval", "blocked_call_too_close",
                    {"lead": approval.lead_email, "approval": approval_id, "slot": booked_slot})
    alert = _alert("Call for %s is too close to confirm" % approval.lead_email,
                   "The reply confirming %s was approved less than %d minutes before the call. Nothing was sent and "
                   "no invite went out; the call is still on the calendar, reminders held. Handle it by hand."
                   % (label, CONFIRM_MARGIN_MINUTES), priority="urgent")
    return {"ok": False, "status": approval.status, "problems": [problem], "alert": alert}


def _refuse_passed_booking(approval: Approval, st, ts: datetime, state: Optional[LeadState],
                           booked_slot: Optional[str], ghl, instantly,
                           base_raw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The owned booking's time has passed: never confirm it. Nothing is sent,
    the card goes to stale_slots with a problem (so a retry() still cannot send
    it unedited), the call is released silently and Lorenzo is told."""
    approval_id = approval.token.split(".", 1)[0]
    label = _slot_label(booked_slot)
    approval.status = "stale_slots"
    approval.decided_at = ts.isoformat()
    approval.draft.problems = list(approval.draft.problems) + [
        "the call this card was confirming (%s) has already passed; it was released. Offer new times" % label]
    if not _save_open(approval, st):
        return _card_changed(st, approval_id)
    released = None
    if state is not None:
        released = cancel_booking(state, ghl, instantly, ts, store=st, reason="passed_before_approval")
        state.history.append({"at": ts.isoformat(), "event": "booking_released", "from": approval_id,
                              "slot": booked_slot, "reason": "passed_before_approval",
                              "cancelled": booking_cancel_done(released)})
        save_lead_state(st, state, base_raw)
    logger.error("refusing to send %s: its booked call %s has passed", approval_id, booked_slot)
    job_log.log_run("reply_engine.approval", "booking_passed_before_approval",
                    {"lead": approval.lead_email, "approval": approval_id, "slot": booked_slot,
                     "released": booking_cancel_done(released)})
    alert = _alert("Call time passed before approval for %s" % approval.lead_email,
                   "The reply confirming %s was approved after that time had passed, so nothing was sent and the "
                   "call was released without notifying the lead. Offer new times from the Instantly inbox or the "
                   "next card." % label)
    return {"ok": False, "status": approval.status, "error": "the booked call time has already passed",
            "stale_slots": [booked_slot], "booking_released": released, "alert": alert}


def release_show_rate_hold(state, store, now: datetime, reason: str = "released") -> Optional[Dict[str, Any]]:
    """Start the S4 show-rate ladder, now that the approved reply has gone out.

    ``booking.register_booking`` creates the schedule at classification time
    and holds it: its first touch is the T+0 "Locked in for ..." confirmation,
    which is due the instant the reply is classified and would otherwise be
    mailed to the prospect by the next ten-minute tick, before Lorenzo has
    tapped anything. Unlike the GHL invite this also applies to shadow
    appointment ids, which is the only version of this that a shadow run ever
    exercises.

    ``reason`` says what went out (show_rate.release_hold records it):
    "approved" only when it was the engine's own unedited draft, which then
    counts as the confirmation, so the ladder's confirm_email / confirm_sms
    are skipped (show_rate.ENGINE_CONFIRMED_RELEASE_REASONS); "approved_edited"
    for a body Lorenzo edited (Keep on the Edit page) and "marked_sent" for a
    reply he sent by hand (Mark sent) keep them, as does the default: text
    the engine did not write, or did not see, is never taken for its
    confirmation.

    Never raises: the reply has already left, and a failure here means a
    missing confirmation (reported), not a failed send.
    """
    if state is None or store is None:
        return None
    booking = (getattr(state, "cadence", None) or {}).get("booking") or {}
    appointment_id = booking.get("appointment_id")
    if not appointment_id:
        return None
    try:
        from services.reply_engine import show_rate

        return show_rate.release_hold(store, appointment_id, now, reason=reason)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not release the show-rate hold for %s: %s", appointment_id, exc)
        job_log.log_run("reply_engine.approval", "show_rate_release_failed",
                        {"appointment_id": appointment_id, "error": str(exc)})
        return {"appointment_id": appointment_id, "error": str(exc)}


def _mark_booking_confirmed(state, approval_id: str, now: datetime, invite: Optional[Dict[str, Any]]) -> None:
    """The owning card went out: the booking is the lead's now, owned by no card.

    ``invite_released`` is recorded only from what release_booking_invite
    actually reports, so a later "already booked" draft can tell a call whose
    invite is on the lead's calendar from one whose invite never left.
    """
    if state is None:
        return
    cad = dict(getattr(state, "cadence", None) or {})
    booking = dict(cad.get("booking") or {})
    if not booking.get("slot"):
        return
    booking.pop("owner", None)
    booking["awaiting_approval"] = False
    booking["confirmed_by"] = approval_id
    booking["confirmation_sent_at"] = now.isoformat()
    if isinstance(invite, dict):
        booking["invite_released"] = bool(invite.get("released"))
    cad["booking"] = booking
    state.cadence = cad


def _invite_failed(state, out: Dict[str, Any]) -> Dict[str, Any]:
    """Log and alert: the confirmation went out, the calendar invite did not."""
    lead = getattr(state, "lead_email", None)
    logger.error("the invite for %s (%s) was NOT released: %s", lead, out.get("appointment_id"), out.get("error"))
    job_log.log_run("reply_engine.approval", "invite_release_failed",
                    {"lead": lead, "appointment_id": out.get("appointment_id"), "error": out.get("error")})
    out["alert"] = _alert("Calendar invite NOT sent to %s" % lead,
                          "The confirmation reply went out, but GHL did not release the calendar invite for "
                          "appointment %s (%s). Send the invite by hand from GHL so the reply is true."
                          % (out.get("appointment_id"), out.get("error")))
    return out


def release_booking_invite(state, ghl, now: datetime) -> Optional[Dict[str, Any]]:
    """Let GHL email the prospect the calendar invite, now that the reply is out.

    booking.book() creates the appointment with toNotify=False, because it runs
    at classification time and Lorenzo may still veto. The confirmation body
    says "invite on the way", so the invite has to follow the approved reply -
    this is the call that releases it.

    ``released: True`` means the write was attempted and succeeded; in shadow
    the guarded would_do record is the success. Anything else - no GHL client
    in live (guard_write alone writes nothing), a synthetic shadow id in live,
    a client that returned nothing or raised - is ``released: False`` with an
    ``error``, logged and pushed to Lorenzo. It used to answer released: True
    in live without writing anything.

    Never raises: the reply has already left, and a failure here is a missing
    invite (recoverable, and reported), not a failed send.
    """
    if state is None:
        return None
    booking = (getattr(state, "cadence", None) or {}).get("booking") or {}
    appointment_id = booking.get("appointment_id")
    if not appointment_id:
        return None
    base = {"appointment_id": appointment_id, "released": False}  # type: Dict[str, Any]
    live = settings.is_live()
    if str(appointment_id).startswith("shadow-"):
        if live:
            return _invite_failed(state, dict(base, error="synthetic_appointment_id: the booking was only ever "
                                                         "recorded in shadow, there is no GHL event to release"))
        return None
    try:
        if ghl is not None:
            rec = ghl.update_appointment_status(appointment_id, "confirmed", to_notify=True)
        elif live:
            return _invite_failed(state, dict(base, error="no_ghl_client"))
        else:
            rec = settings.guard_write("ghl", "update_appointment_status",
                                       {"appointment_id": appointment_id, "status": "confirmed", "toNotify": True})
    except TypeError:  # an older shared.ghl without to_notify
        logger.warning("shared.ghl.update_appointment_status has no to_notify; the invite stays unsent for %s",
                       appointment_id)
        return _invite_failed(state, dict(base, error="no_to_notify"))
    except Exception as exc:  # noqa: BLE001 - the reply is out; a missing invite is reported, never raised
        return _invite_failed(state, dict(base, error=str(exc)[:300]))
    if rec is None:
        return _invite_failed(state, dict(base, error="ghl_write_returned_nothing"))
    shadow = isinstance(rec, dict) and bool(rec.get("shadow"))
    if live and shadow:
        return _invite_failed(state, dict(base, error="guarded_as_shadow_in_live"))
    out = dict(base, released=True)
    if shadow:
        out["shadow"] = True
    return out


# Statuses a card expires from at its TTL (expire_overdue): the ones still
# waiting on Lorenzo's first decision, or on an edit only he can make.
# Left out on purpose (re-review R1 item 2):
#   * 'sending' and 'send_failed': a send may have reached Instantly, so
#     retry() owns them (the poller flags both as stuck), and any expiry text
#     would have to guess what the lead received;
#   * 'approved_queued': Lorenzo already approved it; flush_queued sends it
#     when the window opens, and send_approved's own checks (times that have
#     passed, a call that has passed, the recipient) still refuse anything
#     unsafe;
#   * any card holding a send claim (approval_send_claim:<id>), whatever its
#     status says: the claim means a send started and nothing cleared it;
#   * 'sent' and 'sent_manually' (SENT_STATUSES): the reply went out, there
#     is nothing left to expire.
EXPIRABLE_STATUSES = ("pending", "blocked", "stale_slots")
EXPIRED_BOOKING_CHOICES = ("keep", "release")
# The Keep / Release push is recorded on the card (notify_result.expiry_push)
# and re-sent on later poller ticks until it is delivered (re-review R1 item
# 1): it used to go out once, unrecorded, so an ntfy outage plus an SMTP
# timeout at the moment of expiry left the call held with nobody told. The
# wait after the Nth failed attempt is EXPIRY_PUSH_RETRY_MINUTES[N-1] (the
# last one repeating). From EXPIRY_PUSH_MAX_ATTEMPTS on, every attempt is
# urgent and titled UNANSWERED, logs at ERROR and repeats once an hour until
# one is delivered or the call is decided. Every failed attempt writes a
# "push_failed" Job_Log row, which fails the deploy watch.
EXPIRY_PUSH_RETRY_MINUTES = (5, 15, 30, 60, 120)
EXPIRY_PUSH_MAX_ATTEMPTS = 6
EXPIRY_PUSH_ESCALATED_RETRY_MINUTES = 60
# An attempt claims the record for this long, so two overlapping ticks never
# push the same attempt twice; a worker killed mid-push is retried after it.
EXPIRY_PUSH_LEASE_MINUTES = 10
EXPIRY_PUSH_KEY = "expiry_push"
REOPEN_KEY = "reopened"


def _transition(st, approval_id: str, allowed, fn) -> bool:
    """Apply ``fn(row) -> row`` to the stored card only while its status is in
    ``allowed``, under the store's lock. True when it did: the one winner of
    two workers expiring (or reopening) the same card."""
    box = {"won": False}

    def _apply(current):
        if not isinstance(current, dict) or current.get("status") not in allowed:
            return current
        box["won"] = True
        return fn(dict(current))

    key = APPROVAL_PREFIX + approval_id
    mutate = getattr(st, "mutate", None)
    if callable(mutate):
        try:
            mutate(key, _apply)
            return box["won"]
        except NotImplementedError:
            pass
    current = st.get(key)
    new = _apply(current)
    if box["won"]:
        st.set(key, new)
    return box["won"]


def expired_booking_urls(token: str) -> Dict[str, str]:
    """The Keep / Release links for an expired card that still holds a call.
    GET renders a confirmation page; the decision is the POST behind it."""
    b = base_url()
    return {"keep": "%s/expired/%s/keep" % (b, token), "release": "%s/expired/%s/release" % (b, token)}


def expiry_push_record(raw: Any) -> Dict[str, Any]:
    """The Keep / Release push record on a stored card (a dict row or an
    Approval), or {} when it has none."""
    result = raw.get("notify_result") if isinstance(raw, dict) else getattr(raw, "notify_result", None)
    rec = (result or {}).get(EXPIRY_PUSH_KEY) if isinstance(result, dict) else None
    return dict(rec) if isinstance(rec, dict) else {}


def reopen_record(raw: Any) -> Dict[str, Any]:
    """The Keep reopen marker on a stored card ({"at", "generation"}), or {}."""
    result = raw.get("notify_result") if isinstance(raw, dict) else getattr(raw, "notify_result", None)
    rec = (result or {}).get(REOPEN_KEY) if isinstance(result, dict) else None
    return dict(rec) if isinstance(rec, dict) else {}


def _push_delivered(result: Any) -> bool:
    """The same test create_approval and poller._pushed use: notify() left the
    process (or a test/shadow run recorded it)."""
    return isinstance(result, dict) and bool(result.get("sent") or result.get("test") or result.get("shadow"))


def _holds_send_claim(st, approval_id: str) -> bool:
    """Does a send claim exist for this card? True when the store cannot be
    read: a card is never expired on a guess."""
    try:
        return bool(st.get(SEND_CLAIM_PREFIX + approval_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not read the send claim of %s: %s", approval_id, exc)
        return True


def _expired_status_line(approval: Approval, history: Dict[str, Any], from_status: Optional[str]) -> str:
    """The first line of the expiry push: what state the card was in, said
    only as far as card_history proves it."""
    who = approval.lead_email
    if history.get("approved") is False:
        return ("The reply confirming the call for %s was never approved, and its card expired after %d hours."
                % (who, TTL_HOURS))
    if history.get("approved"):
        if from_status == "blocked":
            why = "; ".join(str(p) for p in (approval.draft.problems or []))[:300] or "a check refused it"
            return ("You approved the reply confirming the call for %s, but it was held back (%s), and its card "
                    "expired after %d hours." % (who, why, TTL_HOURS))
        if from_status == "stale_slots":
            return ("You approved the reply confirming the call for %s, but it was held back because the times it "
                    "offered had passed, and its card expired after %d hours." % (who, TTL_HOURS))
        return ("The reply confirming the call for %s was approved earlier (%s), then put back to pending by an "
                "edit or a retry, and its card expired after %d hours without being approved again."
                % (who, history.get("approved_at") or "time not recorded", TTL_HOURS))
    return ("The card for the reply confirming the call for %s expired after %d hours (it was %s). The engine has "
            "no record of whether it was approved before." % (who, TTL_HOURS, from_status or "open"))


def _push_expired_booking(approval: Approval, booking: Dict[str, Any], ts: datetime,
                          history: Optional[Dict[str, Any]] = None, from_status: Optional[str] = None,
                          attempt: int = 1, previous_errors: Optional[List[str]] = None) -> Dict[str, Any]:
    """The high-priority push for a card that expired holding a call: what
    state the card was in and what may have been sent (card_history, never a
    guess), the appointment, that nothing was changed in GHL, and the Keep /
    Release choice. From EXPIRY_PUSH_MAX_ATTEMPTS on it is urgent and says it
    is unanswered. Never raises."""
    who = approval.lead_email
    history = history or {}
    label = _slot_label(booking.get("slot"))
    appointment_id = booking.get("appointment_id")
    passed = not _slot_in_future(booking.get("slot"), ts)
    escalated = attempt >= EXPIRY_PUSH_MAX_ATTEMPTS
    title = "Card expired with a call still booked: %s" % who
    if escalated:
        title = "UNANSWERED (attempt %d): %s" % (attempt, title)
    elif attempt > 1:
        title = "%s (attempt %d)" % (title, attempt)
    told = " The lead has not been told about it." if history.get("send_started") is False else ""
    lines = [
        _expired_status_line(approval, history, from_status),
        history_sentence(history),
        "Nothing was changed in GHL: appointment %s, %s, is still on the Discovery Call calendar, no invite has gone "
        "out for it and its reminders stay held.%s" % (appointment_id, label, told),
    ]
    if passed:
        lines.append("That time has passed. Release the call: it is cancelled in GHL without notifying the lead.")
    elif history.get("send_claim"):
        lines.append("Keep the call: the card comes back as 'send failed' for another %d hours, because a send from "
                     "it was started; check the Instantly thread, then use Retry on it before approving. Release the "
                     "call: it is cancelled in GHL without notifying the lead." % TTL_HOURS)
    else:
        lines.append("Keep the call: the card comes back as pending for another %d hours so you can approve the "
                     "confirmation (nothing is sent until you do). Release the call: it is cancelled in GHL without "
                     "notifying the lead." % TTL_HOURS)
    lines.append("Until you choose, the card cannot be sent and the call stays as it is.")
    if attempt > 1:
        lines.append("This is attempt %d to reach you; the earlier ones were not delivered (%s)."
                     % (attempt, "; ".join(previous_errors or []) or "no detail"))
    kwargs = {"priority": "urgent" if escalated else "high",
              "tags": ["warning", "reply-engine", "calendar"]}  # type: Dict[str, Any]
    try:
        urls = expired_booking_urls(approval.token)
        actions = [] if passed else [("Keep the call", urls["keep"])]
        actions.append(("Release the call", urls["release"]))
        kwargs.update(actions=actions, click=urls["release"] if passed else urls["keep"])
    except Exception as exc:  # noqa: BLE001 - base_url() fails closed in live; the push must still go out
        logger.warning("expired-booking push for %s carries no buttons: %s", who, exc)
        lines.append("BASE_URL is unset, so this push carries no Keep / Release buttons. Handle the call in GHL by "
                     "hand (cancel it without notifying the lead, or confirm it yourself).")
    try:
        return stored_notify_result(notify.notify(title, "\n".join(lines), **kwargs))
    except Exception as exc:  # noqa: BLE001
        logger.warning("expired-booking push failed for %s: %s", who, exc)
        return {"sent": False, "errors": ["notify raised: %s" % exc]}


def _expiry_retry_wait(attempts: int) -> int:
    """Minutes to wait after ``attempts`` undelivered pushes."""
    if attempts >= EXPIRY_PUSH_MAX_ATTEMPTS:
        return EXPIRY_PUSH_ESCALATED_RETRY_MINUTES
    return EXPIRY_PUSH_RETRY_MINUTES[min(max(attempts, 1), len(EXPIRY_PUSH_RETRY_MINUTES)) - 1]


def _edit_expiry_record(st, approval_id: str, fn) -> Dict[str, Any]:
    """Apply ``fn(rec) -> rec or None`` to the card's expiry push record,
    under the card's lock, only while the card is still expired and has a
    record. Returns the record as written ({} when nothing was)."""
    box = {"rec": {}}  # type: Dict[str, Any]

    def _apply(row):
        if not isinstance(row, dict) or row.get("status") != "expired":
            return row
        result = dict(row.get("notify_result") or {})
        rec = result.get(EXPIRY_PUSH_KEY)
        if not isinstance(rec, dict):
            return row
        new = fn(dict(rec))
        if new is None:
            return row
        result[EXPIRY_PUSH_KEY] = new
        box["rec"] = new
        return dict(row, notify_result=result)

    _mutate_card(st, APPROVAL_PREFIX + approval_id, _apply)
    return box["rec"]


def _claim_expiry_attempt(st, approval_id: str, ts: datetime) -> Optional[Dict[str, Any]]:
    """Take the next attempt at the Keep / Release push, if one is due. The
    record is leased for EXPIRY_PUSH_LEASE_MINUTES, so a second worker on the
    same tick finds nothing due. None when nothing is due (delivered, settled,
    not yet time, or another worker holds it)."""

    def _take(rec):
        if rec.get("settled") or rec.get("delivered"):
            return None
        try:
            due = slots.parse_iso(rec.get("next_at")) <= ts
        except (ValueError, TypeError):
            due = True
        if not due:
            return None
        rec["attempts"] = int(rec.get("attempts") or 0) + 1
        rec["last_at"] = ts.isoformat()
        rec["next_at"] = (ts + timedelta(minutes=EXPIRY_PUSH_LEASE_MINUTES)).isoformat()
        return rec

    rec = _edit_expiry_record(st, approval_id, _take)
    return rec or None


def _finish_expiry_attempt(st, approval_id: str, attempt: int, result: Dict[str, Any],
                           ts: datetime) -> Dict[str, Any]:
    """Record what the attempt's push did, on the card."""
    delivered = _push_delivered(result)

    def _done(rec):
        if int(rec.get("attempts") or 0) != attempt:
            return None  # a later attempt owns the record now
        rec["delivered"] = delivered
        rec["result"] = stored_notify_result(result)
        if delivered:
            rec["delivered_at"] = ts.isoformat()
            rec["next_at"] = None
        else:
            errors = list(rec.get("errors") or [])
            errors.append("attempt %d: %s" % (attempt, "; ".join((result or {}).get("errors") or [])
                                               or "not delivered"))
            rec["errors"] = errors[-EXPIRY_PUSH_MAX_ATTEMPTS:]
            rec["next_at"] = (ts + timedelta(minutes=_expiry_retry_wait(attempt))).isoformat()
            rec["escalated"] = attempt >= EXPIRY_PUSH_MAX_ATTEMPTS
        return rec

    return _edit_expiry_record(st, approval_id, _done)


def _settle_expiry_push(st, approval_id: str, ts: datetime, reason: str) -> None:
    """Nothing is left to push: the card holds no call (any more), or Lorenzo
    decided. Never raises."""

    def _settle(rec):
        if rec.get("settled"):
            return None
        rec["settled"] = True
        rec["settled_at"] = ts.isoformat()
        rec["settled_reason"] = reason
        rec["next_at"] = None
        return rec

    try:
        _edit_expiry_record(st, approval_id, _settle)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not settle the expiry push record of %s: %s", approval_id, exc)


def _push_expired_attempt(approval: Approval, st, ts: datetime, booking: Dict[str, Any]) -> Dict[str, Any]:
    """One attempt at the Keep / Release push, if one is due: claimed on the
    card, pushed, and recorded. An undelivered attempt writes a "push_failed"
    Job_Log row (not a healthy status: the deploy watch fails on it) and
    logs at ERROR; from EXPIRY_PUSH_MAX_ATTEMPTS on it is marked escalated."""
    approval_id = _approval_id(approval)
    claimed = _claim_expiry_attempt(st, approval_id, ts)
    if not claimed:
        return {"attempted": False}
    attempt = int(claimed.get("attempts") or 1)
    history = card_history(st, approval, status=claimed.get("from_status"))
    result = _push_expired_booking(approval, booking, ts, history=history, from_status=claimed.get("from_status"),
                                   attempt=attempt, previous_errors=claimed.get("errors"))
    rec = _finish_expiry_attempt(st, approval_id, attempt, result, ts)
    delivered = _push_delivered(result)
    if not delivered:
        escalated = attempt >= EXPIRY_PUSH_MAX_ATTEMPTS
        logger.error("the Keep / Release push for %s (card %s, call %s) was NOT delivered, attempt %d%s: %s",
                     approval.lead_email, approval_id, booking.get("slot"), attempt,
                     " (ESCALATED)" if escalated else "", result.get("errors"))
        job_log.log_run("reply_engine.approval", "push_failed",
                        {"kind": "expired_booking", "lead": approval.lead_email, "approval": approval_id,
                         "appointment_id": booking.get("appointment_id"), "attempt": attempt,
                         "escalated": escalated, "next_at": rec.get("next_at"), "errors": result.get("errors")})
    return {"attempted": True, "attempt": attempt, "delivered": delivered, "result": result,
            "next_at": rec.get("next_at"), "escalated": bool(rec.get("escalated"))}


def _expire(approval: Approval, st, ts: datetime, ghl=None, instantly=None) -> Optional[Dict[str, Any]]:
    """Retire a card whose 48 h TTL has lapsed. Never writes to GHL.

    A card that holds the lead's unconfirmed booking used to cancel it here,
    on its own: an automatic GHL write nobody chose. Now nothing on the
    calendar moves at expiry (SAL-6). The call stays booked, its reminders stay
    held (the lead hears nothing), the card is retired so it can never be sent
    as it stands, and Lorenzo gets a high-priority push naming the appointment
    with a Keep / Release choice (decide_expired_booking), re-sent on later
    ticks until it is delivered (expire_overdue). A newer reply from the lead
    settles the booking as it would for any retired owner
    (ORPHAN_OWNER_STATUSES).

    The status moves only while the stored card is still open
    (EXPIRABLE_STATUSES) and holds no send claim, under the store's lock, so
    two workers expiring the same card push once, and a card Lorenzo actioned
    meanwhile is left alone. The status it expired from is kept on the push
    record (from_status). Returns the held booking's summary for an owner
    card, else None. ``ghl`` and ``instantly`` are accepted for the callers'
    sake and never used."""
    approval_id = _approval_id(approval)
    if _holds_send_claim(st, approval_id):
        logger.warning("not expiring %s: it holds a send claim (a send started); Retry owns it", approval_id)
        return None
    box = {}  # type: Dict[str, Any]

    def _retire(row):
        box["from"] = row.get("status")
        row["status"] = "expired"
        row["decided_at"] = ts.isoformat()
        result = dict(row.get("notify_result") or {})
        result[EXPIRY_PUSH_KEY] = {"from_status": box["from"], "since": ts.isoformat(),
                                   "attempts": 0, "delivered": False, "settled": False, "escalated": False,
                                   "next_at": ts.isoformat(), "errors": []}
        row["notify_result"] = result
        return row

    if not _transition(st, approval_id, EXPIRABLE_STATUSES, _retire):
        return None
    approval.status = "expired"
    approval.decided_at = ts.isoformat()
    release_slots(st, approval_id)
    held = None
    raw = st.get(approval.state_key)
    state = LeadState.from_store(raw) if raw else None
    if state is not None and owns_booking(approval, state):
        booking = booking_of(state)
        state.history.append({"at": ts.isoformat(), "event": "approval_expired", "approval": approval_id,
                              "booking_held": True, "appointment_id": booking.get("appointment_id"),
                              "slot": booking.get("slot")})
        save_lead_state(st, state, raw)
        push = _push_expired_attempt(approval, st, ts, booking)
        held = {"held": True, "appointment_id": booking.get("appointment_id"), "slot": booking.get("slot"),
                "alert": push.get("result"), "delivered": push.get("delivered")}
    else:
        _settle_expiry_push(st, approval_id, ts, "no_booking")
    job_log.log_run("reply_engine.approval", "expired",
                    {"lead": approval.lead_email, "approval": approval_id, "expires_at": approval.expires_at,
                     "from_status": box.get("from"), "booking_held": bool(held),
                     "appointment_id": (held or {}).get("appointment_id"),
                     "push_delivered": (held or {}).get("delivered")})
    return held


def _revisit_expired(raw: Dict[str, Any], st, ts: datetime) -> Optional[Dict[str, Any]]:
    """A later tick's look at an expired card whose Keep / Release question is
    still open: settle the record once the card no longer holds an undecided
    call, or re-push when the last push was not delivered and the next
    attempt is due."""
    approval = Approval.model_validate(raw)
    approval_id = _approval_id(approval)
    rec = expiry_push_record(raw)
    lead_raw = st.get(approval.state_key)
    state = LeadState.from_store(lead_raw) if lead_raw else None
    if state is None or not owns_booking(approval, state) or cancel_pending(state):
        _settle_expiry_push(st, approval_id, ts, "no_longer_held" if state is not None else "no_lead_row")
        return None
    if rec.get("delivered"):
        return None  # asked and delivered; the poller lists it until he decides
    push = _push_expired_attempt(approval, st, ts, booking_of(state))
    if not push.get("attempted"):
        return None
    return {"approval": approval_id, "lead": approval.lead_email, "expiry_push_attempt": push.get("attempt"),
            "delivered": push.get("delivered"), "escalated": push.get("escalated")}


# A card sent less than this long ago keeps its context row through the sweep:
# the send (or Mark sent) that marked it sent may still be writing the lead's
# history.
CONTEXT_SWEEP_GRACE_MINUTES = 10


def _sent_recently(card: Dict[str, Any], ts: datetime) -> bool:
    """Was this sent card (SENT_STATUSES) marked sent within
    CONTEXT_SWEEP_GRACE_MINUTES of ``ts`` (its decided_at)? A card with no
    readable time is not: nothing would ever make it readable, and its row
    would never be swept."""
    try:
        sent_at = slots.ensure_aware(slots.parse_iso(card.get("decided_at")))
    except Exception:  # noqa: BLE001
        return False
    return ts - sent_at < timedelta(minutes=CONTEXT_SWEEP_GRACE_MINUTES)


def sweep_card_contexts(st, ts: datetime) -> int:
    """Delete the context rows nothing will read again: the card is sent
    (SENT_STATUSES, after CONTEXT_SWEEP_GRACE_MINUTES), vetoed, superseded or
    gone, or it expired with nothing left to decide. Returns how many were
    deleted. Never raises."""
    deleted = 0
    try:
        keys = st.keys(APPROVAL_CONTEXT_PREFIX)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not list the card contexts: %s", exc)
        return 0
    for key in keys:
        try:
            approval_id = key[len(APPROVAL_CONTEXT_PREFIX):]
            card = st.get(APPROVAL_PREFIX + approval_id)
            status = card.get("status") if isinstance(card, dict) else None
            if status in SENT_STATUSES and _sent_recently(card, ts):
                continue  # its send may still be finishing (send_approved reads the row before, this is a 2nd layer)
            if isinstance(card, dict) and status not in CONTEXT_DONE_STATUSES:
                rec = expiry_push_record(card)
                if status != "expired" or (rec and not rec.get("settled")):
                    continue  # open, or expired with the Keep / Release question still open
            st.delete(key)
            deleted += 1
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the rest
            logger.warning("could not sweep %s: %s", key, exc)
    return deleted


def expire_overdue(store=None, now: Optional[datetime] = None, skip_statuses=()) -> List[Dict[str, Any]]:
    """Expire every open card past its TTL (SAL-6: cards never expired unless
    someone tapped one), re-send any Keep / Release push that was not
    delivered, and sweep the context rows nothing reads any more. Called from
    flush_queued, so on every poller tick. Never raises; never writes to GHL
    (see _expire). The rows it returns are the cards it expired, then any
    re-pushes (``expiry_push_attempt``)."""
    st = _store(store)
    ts = _now(now)
    out = []  # type: List[Dict[str, Any]]
    try:
        keys = st.keys(APPROVAL_PREFIX)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not list the approvals to expire: %s", exc)
        return out
    revisits = []  # type: List[Dict[str, Any]]
    for key in keys:
        try:
            raw = st.get(key)
            status = (raw or {}).get("status") if isinstance(raw, dict) else None
            if status == "expired":
                rec = expiry_push_record(raw)
                if rec and not rec.get("settled"):
                    again = _revisit_expired(raw, st, ts)
                    if again:
                        revisits.append(again)
                continue
            if status not in EXPIRABLE_STATUSES or status in skip_statuses:
                continue
            approval = Approval.model_validate(raw)
            if not _expired(approval, ts):
                continue
            held = _expire(approval, st, ts)
            if approval.status == "expired":
                out.append({"approval": key.split(":", 1)[-1], "lead": approval.lead_email, "from_status": status,
                            "booking_held": bool(held),
                            "appointment_id": (held or {}).get("appointment_id")})
        except Exception as exc:  # noqa: BLE001 - one bad card must not stop the rest
            logger.exception("could not expire %s: %s", key, exc)
    sweep_card_contexts(st, ts)
    return out + revisits


def decide_expired_booking(token: str, choice: str, ghl=None, instantly=None, store=None,
                           now: Optional[datetime] = None) -> Dict[str, Any]:
    """Lorenzo's Keep / Release for a card that expired holding a call.

    * ``release``: the call is cancelled in GHL without notifying the lead
      (cancel_booking; a failed cancel keeps the booking and hold and retries,
      as everywhere else), and the card stays expired.
    * ``keep``: nothing is written to GHL. The card comes back for another
      TTL_HOURS with a fresh token, still owning the call, with a fresh SLA
      chase (escalations 0, clock from now, a new reopen generation for the
      chase's claim keys). Normally it comes back as ``pending`` and nothing
      is sent until he approves it. If a send claim exists (a send from the
      card started and nothing cleared it) it comes back as ``send_failed``
      instead, the status the Retry flow owns: Approve would otherwise answer
      "a send is already in flight" for ever, and a send that may have
      reached the lead must be checked in the thread before a second one
      (re-review R1 item 2). Refused once the call's time has passed.

    Only for a card that is ``expired`` and still owns the lead's booking: a
    call released, cancelled or handed to a newer card since has nothing left
    to decide."""
    st = _store(store)
    ts = _now(now)
    pick = (choice or "").strip().lower()
    if pick not in EXPIRED_BOOKING_CHOICES:
        return {"ok": False, "error": "choose keep or release"}
    approval = load(token, st)
    if approval is None:
        return {"ok": False, "error": "unknown or invalid token"}
    if approval.status != "expired":
        return {"ok": False, "error": "this card is %s; there is nothing to decide" % approval.status,
                "status": approval.status}
    raw = st.get(approval.state_key)
    state = LeadState.from_store(raw) if raw else None
    approval_id = _approval_id(approval)
    if state is None or not owns_booking(approval, state):
        _settle_expiry_push(st, approval_id, ts, "no_longer_held")
        return {"ok": False, "status": approval.status,
                "error": "this card no longer holds a call (it was released, cancelled or handed to a newer card)"}
    if cancel_pending(state):
        _settle_expiry_push(st, approval_id, ts, "cancel_pending")
        return {"ok": False, "status": approval.status,
                "error": "that call is already being cancelled in GHL (the cancel is retrying)"}
    booking = booking_of(state)
    before = expiry_push_record(approval)
    history = card_history(st, approval, status=before.get("from_status"))
    if pick == "release":
        cancelled = cancel_booking(state, ghl, instantly, ts, store=st, reason="released_after_expiry",
                                   to_notify=False)
        state.history.append({"at": ts.isoformat(), "event": "booking_released", "from": approval_id,
                              "slot": booking.get("slot"), "reason": "released_after_expiry",
                              "cancelled": booking_cancel_done(cancelled)})
        save_lead_state(st, state, raw)
        _settle_expiry_push(st, approval_id, ts, "released")
        # "booking_released", the status every other release writes; a failed
        # cancel writes its own booking_cancel_failed row (cancel_booking).
        job_log.log_run("reply_engine.approval", "booking_released",
                        {"lead": approval.lead_email, "from": approval_id, "reason": "released_after_expiry",
                         "slot": booking.get("slot"), "appointment_id": booking.get("appointment_id"),
                         "cancelled": booking_cancel_done(cancelled),
                         "appointment_error": (cancelled or {}).get("appointment_error")})
        return {"ok": True, "choice": "release", "status": approval.status, "slot": booking.get("slot"),
                "appointment_id": booking.get("appointment_id"), "history": history,
                "booking_cancelled": cancelled if booking_cancel_done(cancelled) else None,
                "booking_cancel_failed": cancelled if (cancelled or {}).get("cancel_failed") else None}
    if not _slot_in_future(booking.get("slot"), ts):
        return {"ok": False, "status": approval.status,
                "error": "the call time (%s) has passed; release it instead" % _slot_label(booking.get("slot"))}
    try:
        claimed_send = st.get(SEND_CLAIM_PREFIX + approval_id)
    except Exception as exc:  # noqa: BLE001 - never reopen a card on a guess
        logger.warning("could not read the send claim of %s: %s", approval_id, exc)
        return {"ok": False, "status": approval.status,
                "error": "could not check whether a send from this card is in flight; nothing changed, try again"}
    reopened = approval.model_copy(deep=True)
    reopened_as = "send_failed" if claimed_send else "pending"
    reopened.status = reopened_as
    reopened.decided_at = ts.isoformat() if claimed_send else None
    reopened.send_after = None
    if not claimed_send:
        reopened.send_attempt = None
    reopened.expires_at = (ts + timedelta(hours=TTL_HOURS)).isoformat()
    # A fresh chase for the reopened card (re-review R1 item 6): its old
    # escalations and claim keys would otherwise keep it silent.
    reopened.escalations = 0
    reopened.last_escalated_at = None
    result = dict(reopened.notify_result or {})
    result.pop(EXPIRY_PUSH_KEY, None)
    result[REOPEN_KEY] = {"at": ts.isoformat(), "generation": int(reopen_record(approval).get("generation") or 0) + 1}
    reopened.notify_result = result
    # The card's other offered times went back in the pool at expiry. Claimed
    # again BEFORE the card reopens (the booked time is held by the booking
    # itself), so it is never sendable without the problem a taken time puts
    # on it. A store error counts every time as taken, as in create_approval
    # and edit: an unreadable registry holds the card rather than double-offer.
    others = [iso for iso in reopened.draft.offered_slots or [] if not _same_slot(iso, booking.get("slot"))]
    try:
        taken = claim_slots(st, approval.lead_email, others, ts, fields={"approval": approval_id}) if others else []
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not claim the kept card's slots for %s: %s", approval.lead_email, exc)
        taken = list(others)
    if taken:
        reopened.draft.problems = list(reopened.draft.problems) + [
            "%s %s already held for another lead's card or call; use Edit to offer other times"
            % (", ".join(_slot_label(iso) for iso in taken), "is" if len(taken) == 1 else "are")]
    _refresh_token(reopened)
    # One status-guarded write of the whole reopened card (re-review R1 item 3).
    if not _transition(st, approval_id, ("expired",), lambda row: reopened.model_dump(mode="json")):
        current = (_approval_row(st, approval_id) or approval).status
        if current not in (reopened_as,) and others and not taken:
            release_claimed(st, approval.lead_email, others, fields={"approval": approval_id})
        return {"ok": False, "error": "the card changed while you decided; open it again", "status": current}
    state.history.append({"at": ts.isoformat(), "event": "booking_kept_after_expiry", "approval": approval_id,
                          "slot": booking.get("slot"), "appointment_id": booking.get("appointment_id"),
                          "reopened_as": reopened_as})
    save_lead_state(st, state, raw)
    # "retry": the status of every card put back in front of Lorenzo.
    job_log.log_run("reply_engine.approval", "retry",
                    {"lead": approval.lead_email, "approval": approval_id, "from_status": "expired",
                     "booking_kept": True, "appointment_id": booking.get("appointment_id"),
                     "reopened_as": reopened_as, "expires_at": reopened.expires_at})
    return {"ok": True, "choice": "keep", "status": reopened_as, "token": reopened.token,
            "expires_at": reopened.expires_at, "slot": booking.get("slot"), "history": history,
            "appointment_id": booking.get("appointment_id"), "problems": list(reopened.draft.problems)}


def booking_cancel_done(result: Optional[Dict[str, Any]]) -> bool:
    """True only when cancel_booking actually cancelled (or shadow-recorded)
    the call. A failed GHL cancel is never reported as done."""
    return bool(result) and bool(result.get("cancelled")) and not result.get("cancel_failed")


def approve(token: str, instantly, store=None, now: Optional[datetime] = None, ghl=None) -> Dict[str, Any]:
    """Lorenzo's Approve (and Retry's and Book as asked's, which come through
    here): approved_by "lorenzo"."""
    st = _store(store)
    ts = _now(now)
    approval = load(token, st)
    if approval is None:
        return {"ok": False, "error": "unknown or invalid token"}
    return _approve_loaded(approval, instantly, st, ts, ghl, actor="lorenzo")


def _approve_loaded(approval: Approval, instantly, st, ts: datetime, ghl, actor: str) -> Dict[str, Any]:
    """Approve a card already loaded: queue it outside sending hours, else
    send it (send_approved). ``actor`` is who approved it: "lorenzo" from
    approve(), "template" from auto_send_approved. The card records it
    (approved_by) and send_approved re-runs the template gate for a
    "template" card right before its send."""
    approval.approved_by = actor
    if approval.status not in SENDABLE_STATUSES:
        # A card at sending inside its send's lease also says when that ends.
        return _already(approval, st, ts)
    # An approved_queued card past its TTL is not expired (EXPIRABLE_STATUSES):
    # Lorenzo already approved it, and the send below re-checks its times.
    if _expired(approval, ts) and approval.status in EXPIRABLE_STATUSES:
        held = _expire(approval, st, ts, ghl=ghl, instantly=instantly)
        if approval.status != "expired":
            # _expire refused: a send claim exists or the card moved on.
            current = (_approval_row(st, _approval_id(approval)) or approval).status
            return {"ok": False, "status": current,
                    "error": "this card is past its 48 hours but could not be expired (it is %s, or a send from it "
                             "started): nothing was sent; check the Instantly thread" % current}
        out = {"ok": False, "error": "expired", "status": "expired", "booking_held": held}
        if held:
            out["error"] = ("expired; the call it booked (%s) is still on the calendar: choose Keep or Release from "
                            "the alert" % _slot_label(held.get("slot")))
        return out
    # The card's send history (card_history): the first approval is recorded
    # before anything is queued or sent, so no later text can call an
    # approved card "never approved". A store that cannot take the record
    # refuses the approval rather than lose it; the tap can be repeated.
    try:
        _note_card_history(st, _approval_id(approval), ts, approved=True, actor=actor)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not record the approval of %s: %s", _approval_id(approval), exc)
        return {"ok": False, "status": approval.status,
                "error": "could not record the approval (store error); nothing was sent, try again"}
    # is_send_time, not within_send_window: the latter is hour-only and answers
    # True on a Saturday, and its own docstring says anything that auto-sends
    # must use is_send_time().
    if not slots.is_send_time(ts):
        # Not queued for a lead who has since said no (or written again): the
        # send would refuse it anyway, and Lorenzo hears it now, not at 07:00.
        context = card_context(st, _approval_id(approval))
        seen_before = context.get("processed_before")
        why = lead_reply_hold(st.get(approval.state_key), approval,
                              seen_before if isinstance(seen_before, list) else None,
                              reply_at=context.get("reply_at"))
        if why:
            held = _hold_for_lead_reply(approval, st, ts, why, SENDABLE_STATUSES)
            return held if held is not None else _card_changed(st, _approval_id(approval))
        approval.status = "approved_queued"
        approval.decided_at = ts.isoformat()
        approval.send_after = _next_window_open(ts).isoformat()
        # Status-guarded, like the send's "-> sending" write: the tick's expiry
        # (which releases the card's times), a veto or a newer reply's
        # supersede can land between the read above and here. The whole-card
        # save that stood here wrote the card back as approved_queued over
        # them, with no reservations, and the 07:05 flush sent it.
        if not _save_open(approval, st):
            logger.warning("not queueing %s: the card changed before the approval was written", _approval_id(approval))
            return _card_changed(st, _approval_id(approval))
        job_log.log_run("reply_engine.approval", "queued", {"lead": approval.lead_email, "send_after": approval.send_after})
        return {"ok": True, "status": approval.status, "send_after": approval.send_after}
    return send_approved(approval, instantly, st, ts, ghl=ghl)


BOOKING_RESERVATION_PREFIX = "booking:"


CANCEL_RETRY_PREFIX = "booking_cancel_retry:"
# Five-minute poller ticks: half an hour of silent retries, then Lorenzo is
# told to cancel it by hand. The booking and the show-rate hold stay in place
# the whole time, so nothing reaches the prospect while it is unresolved.
CANCEL_RETRY_MAX_ATTEMPTS = 6
# After the "BY HAND" alert the retry does not stop for good (that wedged the
# lead for ever once Lorenzo had cancelled it himself): it keeps trying once an
# hour, so a GHL that recovers - or answers "not found" because he deleted the
# event - still clears it. The signed "I cancelled it" link clears it at once.
CANCEL_ESCALATED_RETRY_MINUTES = 60
CANCEL_DONE_TTL_DAYS = 7

# A cancel that fails with 404 / 410 MAY mean the event is already gone - or
# a route typo, a proxy page, a wrong location. The status code alone is only
# a candidate; the appointment is then re-read, and it counts as gone only if
# that read also answers 404 / 410 or shows it cancelled. Message text is never
# read: "calendar not found" (422), "Contact does not exist" (400) or a 502
# page mentioning 404 all used to be taken as a finished cancel while the
# event stayed live and the lead was sent its reminders.
GONE_STATUSES = (404, 410)
CANCELLED_STATUSES = ("cancelled", "canceled")
_HTTP_STATUS_RE = re.compile(r"->\s*HTTP\s+(\d{3})\b")
TEARDOWN_AFTER_PREFIX = "booking_teardown_after:"


def http_status_of(error: Any) -> Optional[int]:
    """The HTTP status of a failed GHL call: from the exception's own
    status_code / response, else from shared.ghl's "-> HTTP NNN" message."""
    for obj in (error, getattr(error, "response", None)):
        code = getattr(obj, "status_code", None)
        if isinstance(code, int):
            return code
    m = _HTTP_STATUS_RE.search(str(error or ""))
    return int(m.group(1)) if m else None


def _appointment_status(rec: Any) -> Optional[str]:
    if not isinstance(rec, dict):
        return None
    for holder in (rec, rec.get("appointment"), rec.get("event")):
        if isinstance(holder, dict):
            status = holder.get("appointmentStatus") or holder.get("status")
            if status:
                return str(status).lower()
    return None


def confirm_appointment_gone(ghl, appointment_id: Any) -> Optional[str]:
    """Re-read the appointment after a 404 / 410 cancel. The evidence string
    when the read confirms it is gone (itself 404 / 410, or cancelled), else
    None - including when there is no client or no read method to ask."""
    getter = getattr(ghl, "get_appointment", None) if ghl is not None else None
    if not callable(getter):
        return None
    try:
        rec = getter(appointment_id)
    except Exception as exc:  # noqa: BLE001
        code = http_status_of(exc)
        return "re-read answered HTTP %s" % code if code in GONE_STATUSES else None
    status = _appointment_status(rec)
    return "re-read shows it %s" % status if status in CANCELLED_STATUSES else None


def _cancel_appointment(booking: Dict[str, Any], ghl, to_notify: Optional[bool]) -> Dict[str, Any]:
    """Cancel the GHL event behind ``booking``. {"ok": bool, ...}; never raises.

    ok means the write was attempted and succeeded - or, in shadow, that the
    guarded would_do record was written, which is shadow's success - or GHL
    answered 404 / 410 AND a re-read confirmed the event is gone
    (``inferred: True``: the engine did not cancel it itself). There is
    nothing to cancel for a booking with no appointment id or with a synthetic
    ``shadow-`` id (no GHL event was ever created for it).
    """
    appointment_id = booking.get("appointment_id")
    live = settings.is_live()
    # Every cancel the engine starts is explicit about GHL's notification
    # (SAL-9): False unless a caller says otherwise. Leaving it unset let the
    # calendar's default notification setting decide whether the lead was
    # emailed about a cancel (a retry row written before this carries None).
    to_notify = False if to_notify is None else bool(to_notify)
    payload = {"appointment_id": appointment_id, "status": "cancelled", "toNotify": to_notify}  # type: Dict[str, Any]
    if appointment_id is None:
        rec = settings.guard_write("ghl", "update_appointment_status",
                                   dict(payload, slot=booking.get("slot"), note="no appointment id on the booking record"))
        return {"ok": True, "appointment": rec, "note": "no_appointment_id"}
    if live and str(appointment_id).startswith("shadow-"):
        return {"ok": True, "note": "synthetic_appointment_id: no GHL event exists"}
    try:
        if ghl is None:
            if live:
                return {"ok": False, "error": "no_ghl_client"}
            rec = settings.guard_write("ghl", "update_appointment_status", payload)
        else:
            rec = ghl.update_appointment_status(appointment_id, "cancelled", to_notify=to_notify)
    except Exception as exc:  # noqa: BLE001 - reported to the caller, never raised
        code = http_status_of(exc)
        if code in GONE_STATUSES:
            evidence = confirm_appointment_gone(ghl, appointment_id)
            if evidence:
                logger.warning("appointment %s: cancel answered HTTP %s and %s: treated as gone",
                               appointment_id, code, evidence)
                return {"ok": True, "note": "already_gone", "inferred": True, "evidence": evidence,
                        "error_seen": str(exc)[:300]}
        logger.warning("appointment cancel failed for %s: %s", appointment_id, exc)
        return {"ok": False, "error": str(exc)[:300], "status_code": code}
    if rec is None:
        return {"ok": False, "error": "ghl_write_returned_nothing"}
    if live and isinstance(rec, dict) and rec.get("shadow"):
        return {"ok": False, "error": "guarded_as_shadow_in_live", "appointment": rec}
    return {"ok": True, "appointment": rec}


# ------------------------------------------------ "I cancelled it" (by hand)
def _cancel_done_message(state_key: str, appointment_id: Any, expires_at: str) -> bytes:
    return "|".join(["booking_cancelled_by_hand", str(state_key), str(appointment_id), expires_at]).encode("utf-8")


def make_cancel_done_token(state_key: str, appointment_id: Any, now: datetime) -> Optional[str]:
    """``<expires_at>.<hmac>`` for the "I cancelled it" link; None when there
    is no secret to sign with (live without REPLY_ENGINE_SECRET)."""
    try:
        secret = _secret()
    except Exception:  # noqa: BLE001 - ApprovalSecretMissing: no link rather than a dev-signed one
        return None
    expires_at = (slots.to_tz(now) + timedelta(days=CANCEL_DONE_TTL_DAYS)).isoformat()
    sig = hmac.new(secret.encode("utf-8"), _cancel_done_message(state_key, appointment_id, expires_at),
                   hashlib.sha256).hexdigest()[:32]
    return "%s.%s" % (expires_at, sig)


def verify_cancel_done_token(state_key: str, appointment_id: Any, token: Optional[str], now: datetime) -> bool:
    if not token or "." not in str(token):
        return False
    try:
        secret = _secret()
    except Exception:  # noqa: BLE001
        return False
    expires_at, sig = str(token).rsplit(".", 1)
    expected = hmac.new(secret.encode("utf-8"), _cancel_done_message(state_key, appointment_id, expires_at),
                        hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(expected, sig):
        return False
    try:
        return slots.parse_iso(expires_at) > slots.to_tz(now)
    except (ValueError, TypeError):
        return False


def cancel_done_url(state: LeadState, appointment_id: Any, now: datetime) -> Optional[str]:
    """The signed link Lorenzo taps once he has cancelled the call in GHL
    himself, or None when no usable base URL or secret exists."""
    base = configured_base_url()
    token = make_cancel_done_token(state.key, appointment_id, now)
    if not base or not token:
        return None
    return "%s/booking/cancelled/%s/%s?%s" % (
        base, quote(str(state.campaign_id or "unknown"), safe=""), quote(str(state.lead_email or ""), safe=""),
        urlencode({"a": str(appointment_id), "t": token}))


def _alert_with_done_link(title: str, message: str, state: LeadState, appointment_id: Any, now: datetime,
                          priority: str = "high") -> Dict[str, Any]:
    url = cancel_done_url(state, appointment_id, now) if appointment_id else None
    if url:
        message = ("%s Once you have cancelled it in GHL yourself, tap \"I cancelled it\" and the engine finishes "
                   "the cleanup without calling GHL." % message)
    else:
        message = ("%s No \"I cancelled it\" link could be signed (BASE_URL or REPLY_ENGINE_SECRET is missing)."
                   % message)
    try:
        kwargs = {"priority": priority, "tags": ["warning", "reply-engine"]}  # type: Dict[str, Any]
        if url:
            kwargs.update(actions=[("I cancelled it", url)], click=url)
        return stored_notify_result(notify.notify(title, message, **kwargs))
    except Exception as exc:  # noqa: BLE001
        logger.warning("alert failed (%s): %s", title, exc)
        return {"sent": False, "errors": ["notify raised: %s" % exc]}


# ----------------------------------------------------- cancel bookkeeping
def _mutate_lead(st, state_key: str, fn) -> Any:
    """Apply ``fn(raw) -> (new_raw, result)`` to the lead row under the store's
    lock, so a concurrent writer is never overwritten with a stale copy.
    Returns ``result``; the row is left untouched when ``new_raw`` is None."""
    box = {"result": None}

    def _apply(current):
        if not current:
            return current
        new_raw, result = fn(json.loads(json.dumps(current)))
        box["result"] = result
        return current if new_raw is None else new_raw

    mutate = getattr(st, "mutate", None)
    try:
        if callable(mutate):
            mutate(state_key, _apply)
            return box["result"]
    except NotImplementedError:
        pass
    current = st.get(state_key)
    if current:
        new = _apply(current)
        if new is not current:
            st.set(state_key, new)
    return box["result"]


# The cadence fields that record a booking and its cancel. A writer that read
# the lead row earlier must never put back an older copy of these: the cancel
# retry (and "I cancelled it") change them under the row's lock while a reply
# pipeline, a veto or a send is still holding the copy it read at the start.
BOOKING_STATE_KEYS = ("booking", "booking_cancelled")


def _normalize_lead_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """A stored lead row in the shape ``LeadState.to_store()`` writes, so the
    merge compares like with like: a default the model fills in on the way
    through is not mistaken for this writer's change."""
    return LeadState.from_store(row).to_store()


def save_lead_state(store, state: LeadState, base_raw: Optional[Dict[str, Any]],
                    finish: Any = None) -> Dict[str, Any]:
    """Write ``state`` under the lead row's lock as a three-way merge with what
    is stored now: the same merge the cadence tick's write uses
    (merge_stale_write). A field this writer did not change keeps its stored
    value; the booking fields and the stop group keep the stored value whenever
    the store changed them since ``base_raw`` was read; ``last_inbound_at``
    never moves backwards; the append-only lists (approvals, processed ids,
    history, offered slots, drafts) are combined, never overwritten.

    ``finish(row) -> row`` runs under the same lock on the merged row, for a
    decision that must be taken against the row as it stands rather than the
    copy this writer read (send_approved's arm, a reply pipeline's stop).

    A plain ``st.set(key, state.to_store())`` used to write the whole row read
    at the start of a reply's pipeline: a cancel retry that finished in the
    meantime (booking removed, hold and schedules torn down) was undone, and
    the lead was left with a cancel_failed booking and no hold behind it. Only
    the booking fields were protected after that, so a send, a veto or a Resume
    that held an older copy still wrote it back whole: a newer reply's card fell
    out of ``approvals``, its id out of ``processed_email_ids``, its inbound
    time went backwards and its stop was undone (the round-4 R4 race)."""
    base = base_raw
    if base_raw is not None:
        try:
            base = _normalize_lead_row(base_raw)
        except Exception as exc:  # noqa: BLE001 - an unreadable base is merged as read
            logger.warning("could not normalise the row %s was read from: %s", state.key, exc)
    return save_stale_write(store, state.key, state.to_store(), base, normalize=_normalize_lead_row,
                            finish=finish)


# The cadence fields that record whether the ladder may still send. A reply
# stops the ladder (cadence.stop: stopped_reason, stopped_at, next_send_at=None,
# needs_fresh_draft) under its own read-modify-write, and an approval re-arms
# it (armed_at, and armed_for_email_id: the inbound that approved reply
# answered). A tick that read the row before that must never put back its
# older copy: that is SAL-4, "a tick can erase a reply's stop and D2 goes out
# anyway". They move as one group: when any of them changed in the store since
# the tick read the row, all of them are taken from the store. The auto-reply
# pause's baseline (resumed_after_auto_reply_at, auto_reply_seen_through,
# auto_reply_seen_email_id) is part of the group: it is written by the same
# resume that clears stopped_reason, and a writer holding an older copy must
# not pair the store's stop with its own baseline (or the reverse).
STOP_STATE_KEYS = ("armed_at", "stopped_reason", "stopped_at", "next_send_at", "needs_fresh_draft",
                   "armed_for_email_id", "resumed_after_auto_reply_at", "auto_reply_seen_through",
                   "auto_reply_seen_email_id")
# Keys whose stored value always wins over a writer's older copy.
_PROTECTED_CADENCE_KEYS = BOOKING_STATE_KEYS + STOP_STATE_KEYS
# Lead-row lists that every writer only ever appends to. When a writer changed
# one, its list and the stored one are combined: a card, a processed reply id,
# a history entry or an offered slot another writer added after this one read
# the row is never dropped. A slot kept by one writer and not the other stays
# reserved, which offers less, never double-books.
COMBINED_LIST_KEYS = ("approvals", "processed_email_ids", "processed_keys", "history", "offered_slots", "drafts")
# The latest inbound's timestamp only moves forward: a writer holding an older
# copy, or a pipeline processing an older email late, never puts back an
# earlier value than the stored one. The tick's inbound check reads it.
FORWARD_ONLY_KEYS = ("last_inbound_at",)
_MISSING = object()


def _combined_list(mine: Any, current: Any) -> Any:
    """The stored list, then every item of the writer's that it lacks."""
    if not isinstance(current, list):
        return mine
    if not isinstance(mine, list):
        return current
    out = list(current)
    for item in mine:
        if item not in out:
            out.append(item)
    return out


def _later_timestamp(mine: Any, current: Any) -> Any:
    """Whichever of two ISO timestamps is later; a value that cannot be read
    never replaces one that can."""
    pm = _parse_or_none(mine) if mine is not _MISSING else None
    pc = _parse_or_none(current) if current is not _MISSING else None
    if pc is None:
        return mine
    if pm is None:
        return current
    return mine if pm > pc else current


def merge_stale_write(base: Optional[Dict[str, Any]], mine: Dict[str, Any],
                      current: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Three-way merge of a lead row written from an older read.

    ``base`` is the row the writer read, ``mine`` what it wants to write,
    ``current`` what is stored now. A field the writer did not change keeps its
    stored value (a concurrent reply's history, status and inbound time
    survive). A field only the writer changed takes the writer's value, with
    two exceptions: the append-only lists (COMBINED_LIST_KEYS) are combined
    with the stored list, and ``last_inbound_at`` takes the later of the two.
    When both changed a field, the booking and stop fields keep the stored
    value and anything else takes the writer's. The booking fields and the
    stop group keep the stored value whenever the store changed them, whatever
    the writer did."""
    if not current:
        return mine
    if base is None:
        base = {}
    out = {}  # type: Dict[str, Any]
    for k in list(current.keys()) + [k for k in mine.keys() if k not in current]:
        b = base.get(k, _MISSING)
        m = mine.get(k, _MISSING)
        c = current.get(k, _MISSING)
        if k == "cadence":
            val = _merge_cadence(b if isinstance(b, dict) else {}, m if isinstance(m, dict) else {},
                                 c if isinstance(c, dict) else {})
        elif m == b:
            val = c
        elif k in COMBINED_LIST_KEYS:
            val = _combined_list(m, c)
        elif k in FORWARD_ONLY_KEYS:
            val = _later_timestamp(m, c)
        elif c == b:
            val = m
        else:
            val = m
        if val is not _MISSING:
            out[k] = val
    return out


def _merge_cadence(base: Dict[str, Any], mine: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    stop_moved = any(current.get(k, _MISSING) != base.get(k, _MISSING) for k in STOP_STATE_KEYS)
    out = {}  # type: Dict[str, Any]
    for k in list(current.keys()) + [k for k in mine.keys() if k not in current]:
        b = base.get(k, _MISSING)
        m = mine.get(k, _MISSING)
        c = current.get(k, _MISSING)
        if k in STOP_STATE_KEYS and stop_moved:
            val = c
        elif m == b:
            val = c
        elif c == b:
            val = m
        elif k in _PROTECTED_CADENCE_KEYS:
            val = c
        else:
            val = m
        if val is not _MISSING:
            out[k] = val
    return out


def save_stale_write(store, key: str, mine: Dict[str, Any], base: Optional[Dict[str, Any]],
                     normalize: Any = None, finish: Any = None) -> Dict[str, Any]:
    """Write ``mine`` to ``key`` under the row's lock, merged with whatever
    changed in the store since ``base`` was read (see merge_stale_write).

    ``normalize`` maps a stored row to the shape ``mine`` is in (the cadence
    tick round-trips rows through LeadState), so a field nobody changed is not
    mistaken for a change because its stored spelling differs.

    ``finish(merged) -> row`` runs under the same lock, after the merge. It
    must not touch the store (JsonFileStore holds one file lock for the whole
    mutate, so a nested get or set would wait on it forever). If it raises, the
    merged row is written without it and the error is logged."""
    st = _store(store)

    def _norm(row):
        if row is None or normalize is None:
            return row
        try:
            return normalize(row)
        except Exception as exc:  # noqa: BLE001 - an unreadable row is merged as stored
            logger.warning("could not normalise %s for the merge: %s", key, exc)
            return row

    def _merge(current):
        cur = _norm(current)
        merged = merge_stale_write(base, mine, cur)
        if cur:
            cad_c = cur.get("cadence") or {}
            cad_b = (base or {}).get("cadence") or {}
            kept = [f for f in _PROTECTED_CADENCE_KEYS if cad_c.get(f) != cad_b.get(f)]
            if kept:
                logger.warning("kept the stored %s for %s: it changed while this writer held an older copy",
                               ", ".join(kept), key)
        if finish is not None:
            try:
                merged = finish(merged)
            except Exception as exc:  # noqa: BLE001 - the merged write must still land
                logger.error("the locked decision for %s failed (%s); the merged row is written without it",
                             key, exc)
        return merged

    mutate = getattr(st, "mutate", None)
    if callable(mutate):
        try:
            return mutate(key, _merge)
        except NotImplementedError:
            pass
    merged = _merge(st.get(key))
    st.set(key, merged)
    return merged


def _record_cancelled(cad: Dict[str, Any], booking: Dict[str, Any], now: datetime, reason: str) -> Dict[str, Any]:
    cad = dict(cad or {})
    cad.pop("booking", None)
    done = dict(booking)
    done.pop("cancel_failed", None)
    cad["booking_cancelled"] = dict(done, cancelled_at=now.isoformat(), reason=reason)
    return cad


def _row_said_no(row: Any) -> Optional[str]:
    """The category of a no the stored lead row shows (the sticky opt-out
    marker, an opt-out status or an opt-out classification), or None."""
    if not isinstance(row, dict):
        return None
    marker = opt_out_marker(row)
    if marker is not None:
        return str(marker.get("label") or "").strip().lower() or "opt_out"
    labels_out, statuses_out = _opt_out_vocab()
    status = str(row.get("status") or "").strip().lower()
    if status in statuses_out:
        return status
    cls = row.get("classification")
    label = str((cls.get("label") if isinstance(cls, dict) else getattr(cls, "label", "")) or "").strip().lower()
    return label if label in labels_out else None


def _reset_refusal(store, state: LeadState, booking: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Why a cancel must not set the opportunity back to New Reply and the
    Instantly interest back to 1, read from the stored lead row: it holds
    another call (not the one cancelled), or the lead said no. None when the
    reset may run. An unreadable row refuses it too."""
    try:
        row = store.get(getattr(state, "key", None)) if store is not None else None
    except Exception as exc:  # noqa: BLE001 - fail toward not undoing a no
        return {"reason": "row_unreadable", "error": str(exc)}
    if not isinstance(row, dict):
        return None
    said = _row_said_no(row)
    if said:
        return {"reason": "opt_out", "category": said}
    current = dict((row.get("cadence") or {}).get("booking") or {})
    if current.get("slot") and not _same_call(current, booking):
        return {"reason": "other_call", "appointment_id": current.get("appointment_id"), "slot": current.get("slot")}
    return None


def _after_cancel(state: LeadState, booking: Dict[str, Any], ghl, instantly, store, reason: str,
                  keep_hold: bool = False, now: Optional[datetime] = None,
                  keep_reset: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Everything that follows a done cancel: opportunity back to New Reply,
    Instantly interest back to 1, the slot reservation and the store rows the
    booking wrote. Never raises.

    ``keep_hold``: the engine did not see the cancel succeed itself (GHL's
    "gone" confirmed by a re-read, or Lorenzo's "I cancelled it"). If the event
    is in fact still live, jobs/appointments_tick would otherwise arm a fresh,
    unheld reminder ladder for it. The hold, the held schedules and the
    appointment rows stay until the call's time has passed; flush_queued's
    retry pass tears them down then (run_deferred_teardowns).

    ``keep_reset`` (cancel_booking's guard_reset, _reset_refusal): the
    opportunity stage and the Instantly interest are left as they are, and
    the result says why (``reset_skipped``)."""
    out = {}  # type: Dict[str, Any]
    appointment_id = booking.get("appointment_id")
    if store is not None:
        try:
            store.delete(CANCEL_RETRY_PREFIX + str(getattr(state, "key", None) or ""))
        except Exception:  # noqa: BLE001 - bookkeeping only
            pass
    stage = settings.GHL_STAGES.get("new_reply")
    if keep_reset:
        out["reset_skipped"] = dict(keep_reset)
        ghl_for_stage, instantly_for_interest = None, None
    else:
        ghl_for_stage, instantly_for_interest = ghl, instantly
    if ghl_for_stage is not None and getattr(state, "ghl_opportunity_id", None) and stage:
        try:
            out["opportunity"] = ghl.update_opportunity_stage(state.ghl_opportunity_id, stage, status="open")
        except Exception as exc:  # noqa: BLE001
            logger.warning("opportunity revert failed: %s", exc)
            out["opportunity_error"] = str(exc)
    if instantly_for_interest is not None and getattr(state, "campaign_id", None):
        try:
            out["interest"] = instantly.update_interest_status(state.lead_email, state.campaign_id, 1)
        except Exception as exc:  # noqa: BLE001
            logger.warning("interest reset failed: %s", exc)
            out["interest_error"] = str(exc)
    # booking.register_booking reserves the booked time under its own
    # 'booking:<appointment_id>' id. A cancelled call must give that time back,
    # or the slot stays blocked for every lead with no event behind it. When
    # the hold is kept (the engine did not see the cancel itself), the event
    # may still be live, so the time stays reserved with it and is given back
    # by the deferred teardown: freeing it at once let another lead be offered
    # or booked into a slot whose call might still be on the calendar.
    reservation = "%s%s" % (BOOKING_RESERVATION_PREFIX, appointment_id or booking.get("slot"))
    deferred = store is not None and bool(appointment_id) and keep_hold
    if store is not None and not deferred:
        try:
            release_slots(store, reservation)
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not release the booked slot %s: %s", booking.get("slot"), exc)
    # ...and everything else register_booking wrote: the show-rate ladder and
    # its hold, the appointment:/appt: rows the 07:30 sweep and the no-show
    # index read. jobs/appointments_tick only cancels schedules GHL reports as
    # cancelled, so without this the residue never self-healed.
    if deferred:
        _keep_hold(store, state, booking, now or datetime.now(slots.TZ))
        after = _teardown_after(booking)
        store.set(TEARDOWN_AFTER_PREFIX + str(appointment_id),
                  {"appointment_id": appointment_id, "after": after, "reason": reason,
                   "lead": getattr(state, "lead_email", None), "reservation": reservation})
        out["teardown_deferred_until"] = after
        out["slot_kept_until"] = after
    elif store is not None and appointment_id:
        out["teardown"] = teardown_booking_records(store, appointment_id, reason=reason)
    return out


def _parse_or_none(iso: Any) -> Optional[datetime]:
    try:
        return slots.parse_iso(iso) if iso else None
    except (ValueError, TypeError):
        return None


def _teardown_after(booking: Dict[str, Any]) -> str:
    """When a kept hold may go: an hour after the call's end (or start)."""
    end = _parse_or_none(booking.get("end")) or _parse_or_none(booking.get("slot"))
    if end is None:
        return datetime.now(slots.TZ).isoformat()
    return (slots.to_tz(end) + timedelta(hours=1)).isoformat()


def run_deferred_teardowns(store, now: datetime) -> List[Dict[str, Any]]:
    """Tear down the kept holds whose call time has passed. Never raises."""
    st = _store(store)
    out = []  # type: List[Dict[str, Any]]
    try:
        keys = st.keys(TEARDOWN_AFTER_PREFIX)
    except Exception:  # noqa: BLE001
        return out
    for key in keys:
        try:
            rec = st.get(key) or {}
            after = _parse_or_none(rec.get("after"))
            if after is not None and now < after:
                continue
            out.append(dict(teardown_booking_records(st, rec.get("appointment_id"),
                                                     reason=rec.get("reason") or "cancelled"),
                            appointment_id=rec.get("appointment_id")))
            # The booked time was kept reserved with the hold; it goes now.
            release_slots(st, rec.get("reservation") or "%s%s" % (BOOKING_RESERVATION_PREFIX,
                                                                    rec.get("appointment_id")))
            st.delete(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("deferred teardown %s failed: %s", key, exc)
    return out


def _hold_after_failed_cancel(store, state: LeadState, booking: Dict[str, Any], now: datetime, reason: str,
                              to_notify: Optional[bool], error: str, announce: bool = True) -> Dict[str, Any]:
    """The GHL event is still live: keep everything that keeps it silent.

    The booking record stays (marked ``cancel_failed``), the show-rate hold
    stays - re-written if it was ever missing, so jobs/appointments_tick cannot
    arm an unheld reminder ladder and no_show cannot chase the call - and a
    retry is queued for flush_queued. Lorenzo is told on the first failure,
    unless the caller tells him itself (``announce`` False).
    """
    appointment_id = booking.get("appointment_id")
    key = CANCEL_RETRY_PREFIX + str(getattr(state, "key", None) or "")
    previous = {}  # type: Dict[str, Any]
    if store is not None:
        try:
            previous = store.get(key) or {}
        except Exception:  # noqa: BLE001
            previous = {}
    attempts = int(previous.get("attempts") or 0) + 1
    record = {"state_key": getattr(state, "key", None), "lead": getattr(state, "lead_email", None),
              "appointment_id": appointment_id, "slot": booking.get("slot"), "reason": reason,
              "to_notify": to_notify, "attempts": attempts, "last_error": error,
              "first_at": previous.get("first_at") or now.isoformat(), "last_at": now.isoformat(),
              "escalated": bool(previous.get("escalated"))}
    held = False
    if store is not None:
        try:
            store.set(key, record)
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not queue the cancel retry for %s: %s", appointment_id, exc)
        held = _keep_hold(store, state, booking, now)
    cad = dict(getattr(state, "cadence", None) or {})
    kept = dict(cad.get("booking") or booking)
    kept["cancel_failed"] = {"at": now.isoformat(), "reason": reason, "error": error, "attempts": attempts,
                             "to_notify": to_notify}
    cad["booking"] = kept
    state.cadence = cad
    logger.error("the GHL cancel of %s for %s FAILED (%s); booking and hold kept, retry queued",
                 appointment_id, getattr(state, "lead_email", None), error)
    job_log.log_run("reply_engine.approval", "booking_cancel_failed",
                    {"lead": getattr(state, "lead_email", None), "appointment_id": appointment_id,
                     "reason": reason, "error": error, "attempts": attempts, "hold_kept": held})
    alert = None
    if attempts == 1 and announce:
        alert = _alert_with_done_link(
            "Call NOT cancelled for %s" % getattr(state, "lead_email", None),
            "GHL refused to cancel appointment %s (%s, reason: %s). The call is still on the calendar; the "
            "engine keeps its reminders held so the lead hears nothing, and retries the cancel every few "
            "minutes." % (appointment_id, error, reason), state, appointment_id, now)
    return {"cancelled": False, "cancel_failed": True, "appointment_error": error, "attempts": attempts,
            "hold_kept": held, "retry_key": key, "alert": alert}


def _keep_hold(store, state, booking: Dict[str, Any], now: datetime) -> Optional[bool]:
    """Make sure the show-rate hold on the booking's appointment is in place.

    True: the hold is confirmed held. False: it is confirmed missing (the
    write did not stick, or failed). None: unknown (the store could not be
    read back). Read with show_rate.read_hold, which tells "no marker" apart
    from "could not read it": is_held answered "not held" on a read error.
    A marker that could not be read is written anyway (fail closed: a hold
    only keeps the reminder ladder quiet)."""
    appointment_id = booking.get("appointment_id")
    if store is None or not appointment_id:
        return False
    try:
        from services.reply_engine import show_rate

        existing, error = show_rate.read_hold(store, appointment_id)
        if existing is None:
            if error:
                logger.warning("show-rate hold on %s unreadable (%s); writing it anyway", appointment_id, error)
            show_rate.hold(store, appointment_id, reason="cancel_pending", now=now,
                           meta={"lead_email": getattr(state, "lead_email", None),
                                 "start_iso": booking.get("slot")})
        confirmed, error = show_rate.read_hold(store, appointment_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("could not keep the show-rate hold on %s: %s", appointment_id, exc)
        return False
    if confirmed is not None:
        logger.info("show-rate hold on %s kept", appointment_id)
        return True
    if error:
        logger.error("show-rate hold on %s written but UNKNOWN: it could not be read back (%s)", appointment_id, error)
        return None
    logger.error("show-rate hold on %s is NOT in place after writing it", appointment_id)
    return False


def cancel_booking(state: LeadState, ghl, instantly, now: datetime, store=None, reason: str = "vetoed",
                   to_notify: Optional[bool] = None, announce: bool = True,
                   guard_reset: bool = False) -> Optional[Dict[str, Any]]:
    """Undo everything a booking wrote, so a vetoed confirmation leaves no call.

    _reply_draft books the call at classification time, before Lorenzo sees
    anything: a GHL appointment, the opportunity moved to Call Booked and
    Instantly interest 2. veto() used to release the offered slots and stop
    there, so a refused draft still left a real 15 minute call on the calendar
    for a lead who was never told about it.

    The GHL cancel comes first and everything else only follows a successful
    one (or, in shadow, its would_do record; or GHL saying the event is
    already gone). A failed cancel keeps the booking (marked cancel_failed)
    and the hold, alerts, and queues a retry (retry_failed_cancels); the result
    says ``cancelled: False``.

    ``to_notify``: False unless the caller says otherwise, for every booking
    (SAL-9). A booking still awaiting approval was never confirmed to the lead;
    a confirmed one used to keep GHL's default notification setting, which
    decided on its own whether the lead was emailed about the cancel.

    ``announce`` False: the caller pushes its own alert about a failed cancel
    (_book_as_asked_undone); the kept hold, the queued retry and the Job_Log
    row are the same.

    ``guard_reset`` (the Book-as-asked undo): once the cancel is done, the
    stored lead row is read, and when it holds another call or shows the
    lead said no (_reset_refusal), the opportunity stage and the Instantly
    interest are NOT set back; ``reset_skipped`` says why (S-rest round 6
    approval, flag 20).
    """
    booking = dict((getattr(state, "cadence", None) or {}).get("booking") or {})
    if not booking.get("slot"):
        return None
    if to_notify is None:
        to_notify = False
    out = {"slot": booking.get("slot"), "appointment_id": booking.get("appointment_id"),
           "to_notify": to_notify}  # type: Dict[str, Any]
    result = _cancel_appointment(booking, ghl, to_notify)
    if "appointment" in result:
        out["appointment"] = result["appointment"]
    if result.get("note"):
        out["note"] = result["note"]
    if not result.get("ok"):
        out.update(_hold_after_failed_cancel(store, state, booking, now, reason, to_notify,
                                             result.get("error") or "cancel_failed", announce=announce))
        return out
    out["cancelled"] = True
    keep_reset = _reset_refusal(store, state, booking) if guard_reset else None
    out.update(_after_cancel(state, booking, ghl, instantly, store, reason, keep_hold=bool(result.get("inferred")),
                             now=now, keep_reset=keep_reset))
    state.cadence = _record_cancelled(getattr(state, "cadence", None) or {}, booking, now, reason)
    return out


def cancel_pending(state: Optional[LeadState]) -> bool:
    """True while a booking's GHL cancel has failed and is being retried."""
    return bool(booking_of(state).get("cancel_failed"))


def _finish_pending_cancel(st, state_key: str, appointment_id: Any, now: datetime, reason: str,
                           event: str, **extra: Any) -> Optional[Dict[str, Any]]:
    """Under the lead row's lock: drop the booking and record it cancelled, but
    only if the row still holds THIS cancel-pending booking. Returns the
    booking that was removed, or None when another worker already finished
    it or the booking moved on."""

    def _fn(raw):
        cad = raw.get("cadence") or {}
        booking = cad.get("booking") or {}
        if not booking.get("cancel_failed") or str(booking.get("appointment_id")) != str(appointment_id):
            return None, None
        raw["cadence"] = _record_cancelled(cad, booking, now, reason)
        history = list(raw.get("history") or [])
        history.append(dict({"at": now.isoformat(), "event": event, "appointment_id": appointment_id}, **extra))
        raw["history"] = history
        return raw, dict(booking)

    return _mutate_lead(st, state_key, _fn)


def _count_failed_retry(st, state_key: str, appointment_id: Any, now: datetime, error: str) -> Optional[int]:
    """Under the lead row's lock: bump the attempt count on THIS cancel-pending
    booking. None when the booking is gone or different (nothing to write)."""

    def _fn(raw):
        cad = raw.get("cadence") or {}
        booking = cad.get("booking") or {}
        failed = booking.get("cancel_failed")
        if not failed or str(booking.get("appointment_id")) != str(appointment_id):
            return None, None
        attempts = int(failed.get("attempts") or 0) + 1
        booking["cancel_failed"] = dict(failed, attempts=attempts, error=error, at=now.isoformat())
        cad["booking"] = booking
        raw["cadence"] = cad
        return raw, attempts

    return _mutate_lead(st, state_key, _fn)


def retry_failed_cancels(store, ghl, instantly, now: datetime) -> List[Dict[str, Any]]:
    """Retry every GHL cancel that failed (called from flush_queued, so on
    every poller tick). Never raises.

    The lead row is only ever written under its lock and only while it still
    holds the same cancel-pending booking: two overlapping poller ticks used to
    read the row, call GHL and write their whole stale copy back, so the slower
    one resurrected a booking the faster one had already cancelled. After
    CANCEL_RETRY_MAX_ATTEMPTS Lorenzo is told once to cancel it by hand (with
    the "I cancelled it" link); the retry then continues once an hour, and the
    booking and hold stay until it succeeds or he taps the link."""
    st = _store(store)
    ts = _now(now)
    out = []  # type: List[Dict[str, Any]]
    run_deferred_teardowns(st, ts)
    try:
        keys = st.keys(CANCEL_RETRY_PREFIX)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not list the failed cancels: %s", exc)
        return out
    for key in keys:
        try:
            rec = st.get(key) or {}
            if rec.get("escalated"):
                try:
                    last = slots.parse_iso(rec.get("last_at"))
                except (ValueError, TypeError):
                    last = None
                if last is not None and (ts - last).total_seconds() < CANCEL_ESCALATED_RETRY_MINUTES * 60:
                    continue
            state_key = rec.get("state_key") or ""
            raw = st.get(state_key)
            if not raw:
                st.delete(key)
                continue
            state = LeadState.from_store(raw)
            booking = booking_of(state)
            appointment_id = rec.get("appointment_id")
            if not booking.get("cancel_failed") or str(booking.get("appointment_id")) != str(appointment_id):
                st.delete(key)  # the booking moved on (cancelled by hand, by another worker, or replaced)
                continue
            result = _cancel_appointment(booking, ghl, rec.get("to_notify"))
            if result.get("ok"):
                removed = _finish_pending_cancel(st, state_key, appointment_id, ts, rec.get("reason") or "vetoed",
                                                 "booking_cancel_retried", attempts=rec.get("attempts"),
                                                 note=result.get("note"))
                if removed is None:
                    st.delete(key)  # another worker finished it first: nothing to undo twice
                    out.append({"lead": rec.get("lead"), "cancelled": False, "skipped": "already_finished"})
                    continue
                # The same rule as the Book-as-asked undo (cancel_booking's
                # guard_reset): read the row as it stands now that the cancel
                # is recorded; another call on it, the lead's no, or a row that
                # cannot be read leaves the opportunity and the interest alone.
                keep_reset = _reset_refusal(st, state, removed)
                side = _after_cancel(state, removed, ghl, instantly, st, rec.get("reason") or "vetoed",
                                     keep_hold=bool(result.get("inferred")), now=ts, keep_reset=keep_reset)
                job_log.log_run("reply_engine.approval", "booking_cancel_retry_ok",
                                dict({"lead": rec.get("lead"), "appointment_id": appointment_id,
                                      "note": result.get("note")},
                                     **({"reset_skipped": keep_reset.get("reason")} if keep_reset else {})))
                out.append(dict(side, lead=rec.get("lead"), cancelled=True, appointment_id=appointment_id,
                                note=result.get("note")))
                continue
            error = result.get("error") or "cancel_failed"
            attempts = _count_failed_retry(st, state_key, appointment_id, ts, error)
            if attempts is None:
                st.delete(key)
                out.append({"lead": rec.get("lead"), "cancelled": False, "skipped": "booking_gone"})
                continue
            _keep_hold(st, state, booking, ts)
            entry = {"lead": rec.get("lead"), "cancelled": False, "cancel_failed": True, "attempts": attempts,
                     "appointment_error": error, "appointment_id": appointment_id}
            updated = dict(rec, attempts=attempts, last_error=error, last_at=ts.isoformat())
            if attempts >= CANCEL_RETRY_MAX_ATTEMPTS and not rec.get("escalated"):
                updated["escalated"] = True
                entry["escalated"] = True
                entry["escalation_alert"] = _alert_with_done_link(
                    "Cancel the call for %s BY HAND" % rec.get("lead"),
                    "GHL refused to cancel appointment %s %d times (%s). Cancel it in GHL without notifying the "
                    "lead. Its reminders stay held until the cancel is done; the engine keeps retrying once an "
                    "hour." % (appointment_id, attempts, error), state, appointment_id, ts, priority="urgent")
            st.set(key, updated)
            out.append(entry)
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the rest
            logger.exception("cancel retry failed for %s", key)
            out.append({"key": key, "error": str(exc)})
    return out


def mark_cancelled_by_hand(store, state_key: str, appointment_id: Any, token: Optional[str], now: datetime,
                           instantly=None) -> Dict[str, Any]:
    """Lorenzo tapped "I cancelled it": he cancelled the event in GHL himself.

    Finishes the cleanup a successful cancel would have done - booking record,
    hold, schedules, slot reservation, retry key, Instantly interest - without
    calling GHL (the event is his to manage now; the opportunity stage is left
    for him to move). Only for a booking whose cancel failed, and only on a
    link signed for this lead and this appointment."""
    st = _store(store)
    ts = _now(now)
    if not verify_cancel_done_token(state_key, appointment_id, token, ts):
        return {"ok": False, "error": "that link is not signed for this call, or it has expired"}
    raw = st.get(state_key)
    if not raw:
        return {"ok": False, "error": "no lead state"}
    state = LeadState.from_store(raw)
    booking = booking_of(state)
    if str(booking.get("appointment_id")) != str(appointment_id) or not booking.get("cancel_failed"):
        return {"ok": False, "error": "that call is not waiting on a cancel any more", "status": "nothing_to_do"}
    removed = _finish_pending_cancel(st, state_key, appointment_id, ts, "cancelled_by_hand", "booking_cancelled_by_hand")
    if removed is None:
        return {"ok": False, "error": "that call is not waiting on a cancel any more", "status": "nothing_to_do"}
    # Lorenzo's word is not the engine seeing the cancel: the hold stays until
    # the call's time has passed, in case the event is still live after all.
    side = _after_cancel(state, removed, None, instantly, st, "cancelled_by_hand", keep_hold=True, now=ts)
    job_log.log_run("reply_engine.approval", "booking_cancelled_by_hand",
                    {"lead": state.lead_email, "appointment_id": appointment_id})
    return dict(side, ok=True, slot=removed.get("slot"), appointment_id=appointment_id)


def teardown_booking_records(store, appointment_id: Any, reason: str = "vetoed") -> Dict[str, Any]:
    """Erase every store row ``booking.register_booking`` wrote for one call.

    Deletes rather than tombstones the schedules: nothing can have been
    dispatched from them (the ladder is held until the approved reply goes
    out, and veto() refuses once the status is sending/sent), and a tombstoned
    record would leave a rebooking of the same id and start permanently dead.

    Never raises: a veto must succeed even if the store is unhappy.
    """
    out = {"appointment_id": str(appointment_id), "schedules": [], "touches_cancelled": 0,
           "keys_deleted": [], "hold_cleared": False}  # type: Dict[str, Any]
    try:
        from services.reply_engine import show_rate
    except Exception as exc:  # noqa: BLE001 - deletion of the index rows still has to happen
        logger.warning("show_rate is unavailable during teardown of %s: %s", appointment_id, exc)
        show_rate = None
    try:
        if show_rate is None:
            raise RuntimeError("show_rate unavailable")
        for key in store.keys("showrate:%s:" % appointment_id):
            try:
                out["touches_cancelled"] += show_rate.cancel_schedule(store, key, reason)
            except Exception as exc:  # noqa: BLE001
                logger.warning("could not cancel the show-rate schedule %s: %s", key, exc)
            store.delete(key)
            out["schedules"].append(key)
        out["hold_cleared"] = show_rate.clear_hold(store, appointment_id, reason)
        store.delete(show_rate.confirmed_key(str(appointment_id)))
    except Exception as exc:  # noqa: BLE001
        logger.warning("show-rate teardown failed for %s: %s", appointment_id, exc)
        out["error"] = str(exc)
    try:
        zoom_meeting_id = (store.get("appt:%s" % appointment_id) or {}).get("zoom_meeting_id")
    except Exception:  # noqa: BLE001
        zoom_meeting_id = None
    doomed = ["appointment:%s" % appointment_id, "appt:%s" % appointment_id]
    if zoom_meeting_id:
        doomed.append("zoom_meeting:%s" % zoom_meeting_id)
    if show_rate is not None:
        try:
            doomed.extend(store.keys("%s%s:" % (show_rate.FIRST_SEEN_PREFIX, appointment_id)))
        except Exception:  # noqa: BLE001
            pass
    for key in doomed:
        try:
            store.delete(key)
            out["keys_deleted"].append(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not delete %s: %s", key, exc)
    return out


def veto(token: str, store=None, now: Optional[datetime] = None, ghl=None, instantly=None) -> Dict[str, Any]:
    st = _store(store)
    ts = _now(now)
    approval = load(token, st)
    if approval is None:
        return {"ok": False, "error": "unknown or invalid token"}
    # A card whose reply went out (by the engine, or by hand and marked sent)
    # has nothing left to veto; one at sending may be going out right now
    # (_already says until when).
    if approval.status in SENT_STATUSES + ("sending",):
        return _already(approval, st, ts)
    approval_id = _approval_id(approval)

    def _to_vetoed(row):
        row["status"] = "vetoed"
        row["decided_at"] = ts.isoformat()
        return row

    # Written only over the status read above, under the store's lock. A send
    # that started since (the card at sending, or already sent), a newer
    # reply's supersede or a hold keeps the card as it is, and nothing below
    # runs: the booking the reply may confirm is never cancelled and the times
    # it offers stay held (S-rest round 6).
    if not _transition(st, approval_id, (approval.status,), _to_vetoed):
        return _changed_meanwhile(st, approval_id, ts, "nothing was vetoed")
    approval.status = "vetoed"
    approval.decided_at = ts.isoformat()
    release_slots(st, approval_id)
    state_raw = st.get(approval.state_key)
    cancelled = None
    if state_raw:
        state = LeadState.from_store(state_raw)
        # Only the card that OWNS the still-unconfirmed booking may cancel it:
        # the one that booked it, or the one it was handed to when a newer
        # reply superseded that card. Vetoing an ordinary answer to a lead who
        # already has a call - or vetoing the superseded card itself - must
        # leave that call alone.
        if owns_booking(approval, state):
            # to_notify defaults to False while the booking awaits approval:
            # the lead was never told about that call.
            cancelled = cancel_booking(state, ghl, instantly, ts, store=st)
        # The HELD push tells Lorenzo to Veto a card the lead's opt-out or
        # final no holds. That must not wipe the no off the row: an opt-out
        # status (router.OPT_OUT_STATUSES) stays, and only the history records
        # the veto.
        if str(state.status or "").strip().lower() not in _opt_out_vocab()[1]:
            state.status = "vetoed"
        state.history.append({"at": ts.isoformat(), "event": "vetoed", "approval": token.split(".")[0],
                              "booking_cancelled": booking_cancel_done(cancelled),
                              "booking_cancel_failed": bool((cancelled or {}).get("cancel_failed"))})
        save_lead_state(st, state, state_raw)
    job_log.log_run("reply_engine.approval", "vetoed", {"lead": approval.lead_email, "campaign_id": approval.campaign_id,
                                                        "booking_cancelled": booking_cancel_done(cancelled),
                                                        "booking_cancel_failed": bool((cancelled or {}).get("cancel_failed"))})
    return {"ok": True, "status": "vetoed", "booking_cancelled": cancelled if booking_cancel_done(cancelled) else None,
            "booking_cancel_failed": cancelled if (cancelled or {}).get("cancel_failed") else None}


RETRYABLE_STATUSES = ("send_failed", "stale_slots", "sending")


def retry(token: str, store=None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Put a stuck approval back in front of Lorenzo.

    send_failed and stale_slots were terminal with no owner: nothing retries
    them (neither is in SENDABLE_STATUSES), poller.pending_approvals only
    looked at status == 'pending', and the only trace was a Job_Log CSV row, so
    a lead's positive reply was simply never answered. 'sending' is included for
    the container-kill case, where the claim is held by a worker that no longer
    exists; the send claim is dropped with it so the next approve can win one.

    A sending card is taken only once no worker can still be running its
    send: its own send claim at least SEND_CLAIM_LEASE_MINUTES old, the lease
    Mark sent waits for too. Inside the lease Retry is refused and says when
    it becomes available (retry_refusal): putting the card back to pending
    while its worker was still inside the Instantly call, then approving it,
    sent the lead a second reply. A card whose claim cannot tell when its send
    started (none, another attempt's, no readable time) is taken as before;
    one whose claim cannot be read is refused. The move back to pending is
    status-guarded and, from sending, bound to the send attempt this Retry
    read, and only the Retry that wins drops the claim: a second Retry that
    read the old attempt never frees the send the first one led to. Taking a
    card from sending writes a send_never_finished Job_Log row
    (_send_never_finished): its worker wrote nothing, and the deploy watch
    must see it.
    """
    st = _store(store)
    ts = _now(now)
    approval = load(token, st)
    if approval is None:
        return {"ok": False, "error": "unknown or invalid token"}
    if approval.status not in RETRYABLE_STATUSES:
        return {"ok": False, "error": "nothing to retry (status %s)" % approval.status, "status": approval.status}
    approval_id = approval.token.split(".", 1)[0]
    attempt = approval.send_attempt
    lease = None  # type: Optional[Dict[str, Any]]
    if approval.status == "sending":
        try:
            lease = send_claim_lease(approval, st, ts)
        except Exception as exc:  # noqa: BLE001 - unknown is refused
            return {"ok": False, "status": approval.status,
                    "error": "could not read this card's send claim (%s); nothing changed, try again" % exc}
        if lease["state"] == "running":
            return {"ok": False, "status": approval.status, "error": _retry_wait_text(lease),
                    "actionable_at": lease["free_at"].isoformat()}
    # send_failed and sending never expire (EXPIRABLE_STATUSES): a send may
    # have reached Instantly, and this is the flow that owns them. One past its
    # 48 h used to be refused here as "expired" while the tick left it alone,
    # a dead end; it comes back with a fresh TTL (and so a fresh token).
    refreshed = _expired(approval, ts)
    if refreshed:
        approval.expires_at = (ts + timedelta(hours=TTL_HOURS)).isoformat()
    # The claim is the proof that a send started. Before it is dropped, that
    # is written into the card's history (card_history), so a later expiry
    # push or page never says "nothing was sent" about a card that may have
    # reached the lead. No record, no retry.
    try:
        if st.get(SEND_CLAIM_PREFIX + approval_id):
            _note_card_history(st, approval_id, ts, approved=True, send_attempts=1)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not record the send attempt of %s: %s", approval_id, exc)
        return {"ok": False, "status": approval.status,
                "error": "could not record this card's earlier send attempt (store error); nothing changed, try again"}
    previous = approval.status
    approval.status = "pending"
    approval.send_attempt = None
    approval.decided_at = None
    # Back to pending is back to unapproved: the next Approve records who.
    approval.approved_by = None
    if isinstance(approval.notify_result, dict) and RECIPIENT_HELD_KEY in approval.notify_result:
        # Its recipient hold ends with the RECIPIENT_HOLD_PREFIX row, dropped
        # below: the next send re-checks the thread from scratch.
        approval.notify_result = dict((k, v) for k, v in approval.notify_result.items() if k != RECIPIENT_HELD_KEY)
    if previous == "stale_slots":
        # The body still names times that have passed. Say so on the card rather
        # than letting a second tap send the same words.
        approval.draft.problems = list(approval.draft.problems) + [
            "the times in this draft have passed; use Edit to offer new ones"]
    if refreshed:
        _refresh_token(approval)
    moved = {}  # type: Dict[str, Any]

    def _back_to_pending(row):
        if previous == "sending" and row.get("send_attempt") != attempt:
            # Another send of the card started since this Retry read it (a
            # Retry that won, then an approval): not this Retry's to undo.
            moved["send_attempt"] = row.get("send_attempt")
            return row
        return approval.model_dump(mode="json")

    # Status-guarded: only from the status this retry read (a Keep, a veto or
    # the tick may have moved the card meanwhile), and from sending only from
    # the send attempt it read.
    if not _transition(st, approval_id, (previous,), _back_to_pending) or moved:
        current = (_approval_row(st, approval_id) or approval).status
        return {"ok": False, "error": "the card changed meanwhile (it is now %s); open it again" % current,
                "status": current}
    # Dropped only now, by the Retry that won: one that lost must never drop
    # the claim of a send that started since, which would free that send's
    # card for a second one.
    for key in (SEND_CLAIM_PREFIX + approval_id, RECIPIENT_HOLD_PREFIX + approval_id):
        try:
            st.delete(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not clear %s: %s", key, exc)
    if previous == "sending":
        claim_state = (lease or {}).get("state")
        started_at = (((lease or {}).get("claim") or {}).get("at")
                      if claim_state in ("running", "stale") else None)
        _send_never_finished(approval_id, approval.lead_email, attempt, started_at, claim_state, "retry", ts)
    job_log.log_run("reply_engine.approval", "retry", {"lead": approval.lead_email, "approval": approval_id,
                                                       "from_status": previous, "ttl_refreshed": refreshed})
    return {"ok": True, "status": "pending", "from_status": previous, "token": approval.token}


# ------------------------------------------------------------- Mark sent
# A send_failed card whose reply DID reach the lead (Instantly raised after
# accepting it, or Lorenzo sent it by hand) had one way out that kept the
# lead's call: none. Retry would send it again, Veto cancels the call, and a
# send_failed card never expires, so the stuck-card push went on for good.
# Mark sent records it as sent_manually (SENT_STATUSES) instead. A card stuck
# at sending (its worker died after taking the send claim, and the reply may
# have gone out) had the same dead end, and Veto refuses it as well: Mark sent
# takes it too, once its claim is past SEND_CLAIM_LEASE_MINUTES
# (sending_takeover).
MARK_SENT_FROM = ("send_failed", "sending")
# Mark sent takes a `sending` card only once its send claim is at least this
# old, when no worker can still be running that send. Not a new figure: it is
# the send path's own allowance for a send that may still be finishing, the
# context sweep's CONTEXT_SWEEP_GRACE_MINUTES, reused (the stuck push's lease,
# EXPIRY_PUSH_LEASE_MINUTES, after which a worker is taken for dead, is the
# same ten minutes). Every worker that takes a claim runs inside one Modal
# call (the web app 120 s, the poller 240 s: modal_app), and even a local
# run's slowest send (the thread re-read's retries and backoff, then the
# reply's POST, each request under a 30 s timeout) is under six minutes. The
# stuck detector lists a `sending` card by the same lease
# (poller.pending_approvals), so the push that lists one can carry the
# button. A worker held up past it anyway (a suspended process) never
# overwrites what Mark sent recorded: it re-reads the card before the
# Instantly call (_still_this_send), and its writes refuse a card already
# sent (_save_unless_sent). Retry waits for the same lease before it puts a
# `sending` card back to pending (retry_refusal): approving the card again
# while its worker is still inside the Instantly call would send the lead a
# second reply.
SEND_CLAIM_LEASE_MINUTES = CONTEXT_SWEEP_GRACE_MINUTES
# Where a card marked sent records who marked it and when, on the stored
# card's notify_result: {"at", "by", "send_failed_at"}; a card taken from
# sending adds "from": "sending" and "send_claim", the claim it took over
# ({"attempt", "at"}), and its send_failed_at is None.
MARK_SENT_KEY = "marked_sent"
# A send_failed card the recipient check ended on (_hold_for_recipient: the
# thread's last inbound was somebody else, or the thread could not be re-read)
# never went to Instantly, and the thread may not be the lead's: Mark sent is
# not offered for it (orchestrator's round-4 decision, fail closed).
RECIPIENT_HELD_REFUSAL = ("This card was held because the recipient could not be confirmed; Veto it, or check "
                          "the thread in Instantly. Mark sent is not available.")


def recipient_held(card: Any, store=None) -> Optional[Dict[str, Any]]:
    """The recipient hold a card ended on, or None: the record on the card
    itself (notify_result[RECIPIENT_HELD_KEY], written when the hold
    escalated it to send_failed), else, when ``store`` is given, the hold's
    own row (RECIPIENT_HOLD_PREFIX), which is all a card escalated before the
    card-side record existed has. ``card`` is an Approval or a stored card
    row. A store read that fails raises: the caller refuses."""
    result = card.get("notify_result") if isinstance(card, dict) else getattr(card, "notify_result", None)
    rec = result.get(RECIPIENT_HELD_KEY) if isinstance(result, dict) else None
    if isinstance(rec, dict) and rec:
        return dict(rec)
    if store is None:
        return None
    token = card.get("token") if isinstance(card, dict) else getattr(card, "token", None)
    approval_id = str(token or "").split(".", 1)[0]
    if not approval_id:
        return None
    rec = store.get(RECIPIENT_HOLD_PREFIX + approval_id)
    return dict(rec) if isinstance(rec, dict) and rec else None


def send_claim_record(store, approval_id: str) -> Optional[Dict[str, Any]]:
    """The card's send claim ({"attempt", "at"}; an older store's appended
    list gives its first entry), or None when it has none. A store read
    that fails raises."""
    raw = store.get(SEND_CLAIM_PREFIX + approval_id)
    first = raw[0] if isinstance(raw, list) and raw else raw
    return dict(first) if isinstance(first, dict) and first else None


def send_claim_lease(card: Any, store, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Where a sending card's send claim stands against
    SEND_CLAIM_LEASE_MINUTES: {"state", "claim", "started", "free_at"}.

    * "running": the claim is the card's own send attempt (send_attempt) and
      younger than the lease, so its send may still be under way; the lease
      ends at ``free_at``.
    * "stale": its own attempt, at least the lease old: nothing can still be
      running that send.
    * "no_claim", "other_attempt", "no_time": the engine cannot tell when the
      send started (no claim, a claim from another attempt, or one with no
      readable time).

    Mark sent takes only "stale" (sending_takeover); Retry waits out
    "running" (retry_refusal). ``card`` is an Approval or a stored card row.
    A store read that fails raises: the caller refuses."""
    ts = _now(now)
    if isinstance(card, dict):
        token, attempt = card.get("token"), card.get("send_attempt")
    else:
        token, attempt = getattr(card, "token", None), getattr(card, "send_attempt", None)
    approval_id = str(token or "").split(".", 1)[0]
    claim = send_claim_record(store, approval_id) if approval_id else None
    out = {"state": "no_claim", "claim": claim, "started": None, "free_at": None}  # type: Dict[str, Any]
    if not claim:
        return out
    if not attempt or str(claim.get("attempt") or "") != str(attempt):
        out["state"] = "other_attempt"
        return out
    try:
        started = slots.to_tz(slots.ensure_aware(slots.parse_iso(str(claim.get("at")))))
    except Exception:  # noqa: BLE001 - no readable time
        out["state"] = "no_time"
        return out
    free_at = started + timedelta(minutes=SEND_CLAIM_LEASE_MINUTES)
    out.update(state="running" if ts < free_at else "stale", started=started, free_at=free_at)
    return out


# Why the engine cannot tell when a sending card's send started
# (send_claim_lease's states other than running and stale).
_NO_USABLE_CLAIM = {"no_claim": "it holds no send claim",
                    "other_attempt": "its send claim is from another send attempt",
                    "no_time": "its send claim has no readable time"}


def sending_takeover(card: Any, store, now: Optional[datetime] = None):
    """May Mark sent take this `sending` card? ``(claim, None)`` when its
    send claim is the card's own send attempt (send_attempt) and was taken
    at least SEND_CLAIM_LEASE_MINUTES before ``now``: nothing can still be
    running that send. Otherwise ``(claim, why not)``, failing closed: no
    claim, a claim from another attempt or with no readable time, or one
    still inside the lease (send_claim_lease). ``card`` is an Approval or a
    stored card row. A store read that fails raises: the caller refuses."""
    lease = send_claim_lease(card, store, now)
    claim = lease["claim"]
    if lease["state"] == "stale":
        return claim, None
    if lease["state"] == "running":
        return claim, ("This card's send started %s and may still be running. Mark sent is available from %s, "
                       "%d minutes after it started: check the Instantly thread again then. Nothing was recorded."
                       % (_when_label(lease["started"].isoformat()), _when_label(lease["free_at"].isoformat()),
                          SEND_CLAIM_LEASE_MINUTES))
    return claim, ("The engine has no usable record of when this card's send started (%s), so a send that is still "
                   "running cannot be ruled out. Mark sent is not available for it; nothing was recorded. See the "
                   "runbook reply_engine_alerts.md, Replies with no owner." % _NO_USABLE_CLAIM[lease["state"]])


def _retry_wait_text(lease: Dict[str, Any]) -> str:
    """Retry's refusal for a sending card inside its lease (send_claim_lease
    "running"), with when Retry becomes available."""
    return ("This card's send started %s and may still be running, so a Retry now could send the reply a second "
            "time. Retry is available from %s, %d minutes after it started: check the Instantly thread then, and "
            "press Mark sent instead if the reply went out. Nothing changed."
            % (_when_label(lease["started"].isoformat()), _when_label(lease["free_at"].isoformat()),
               SEND_CLAIM_LEASE_MINUTES))


def retry_refusal(card: Any, store, now: Optional[datetime] = None) -> Optional[str]:
    """Why Retry may not take this card yet, or None: retry()'s own check,
    for a page to show before the POST. A sending card whose send may still
    be running (send_claim_lease: its own claim inside
    SEND_CLAIM_LEASE_MINUTES) waits for the lease to end, and the text says
    when. ``card`` is an Approval or a stored card row. A store read that
    fails raises: the caller refuses."""
    status = card.get("status") if isinstance(card, dict) else getattr(card, "status", None)
    if status != "sending":
        return None
    lease = send_claim_lease(card, store, now)
    return _retry_wait_text(lease) if lease["state"] == "running" else None


def _already(approval: Approval, st, ts: datetime) -> Dict[str, Any]:
    """The refusal for an action a card's status does not take ("already
    <status>"), from approve, edit, accept_requested and veto. A card at
    sending whose send may still be running (send_claim_lease: its own claim
    inside SEND_CLAIM_LEASE_MINUTES) also says when that ends and what to do
    then, as retry() and mark_sent_manually do, whichever button was
    pressed. Never raises."""
    out = {"ok": False, "error": "already %s" % approval.status, "status": approval.status}  # type: Dict[str, Any]
    running = _running_send(approval, st, ts)
    if running is not None:
        out["error"] = "already sending: %s" % running[0]
        out["actionable_at"] = running[1]
    return out


def _running_send(approval: Approval, st, ts: datetime):
    """(text, actionable_at) for a card at sending whose send may still be
    running (send_claim_lease: its own claim inside SEND_CLAIM_LEASE_MINUTES):
    when it started, and when and how it can be acted on. None for any other
    card, or when the claim cannot be read. Never raises."""
    if approval.status != "sending":
        return None
    try:
        lease = send_claim_lease(approval, st, ts)
    except Exception as exc:  # noqa: BLE001 - the refusal stands without the time
        logger.warning("could not read the send claim of %s: %s", _approval_id(approval), exc)
        return None
    if lease["state"] != "running":
        return None
    return (("its send started %s and may still be running. If the card still shows sending at %s, %d minutes "
             "after it started, check the Instantly thread: press Mark sent if the reply went out, or Retry if it "
             "did not" % (_when_label(lease["started"].isoformat()), _when_label(lease["free_at"].isoformat()),
                          SEND_CLAIM_LEASE_MINUTES)),
            lease["free_at"].isoformat())


def _changed_meanwhile(st, approval_id: str, ts: datetime, nothing: str) -> Dict[str, Any]:
    """The refusal for an edit, a Book as asked or a veto whose status-guarded
    write lost: the card moved after the action read it (a send started or
    finished, a newer reply superseded it, the lead's words held it, it
    expired). Says what the card is now and ``nothing`` (what did not
    happen); a card at sending whose send may still be running also says
    when it can be acted on, as _already does. Never raises."""
    try:
        current = _approval_row(st, approval_id)
    except Exception as exc:  # noqa: BLE001 - the refusal stands without the status
        logger.warning("could not re-read card %s: %s", approval_id, exc)
        current = None
    status = current.status if current is not None else "unknown"
    out = {"ok": False, "status": status,
           "error": "the card changed meanwhile (it is now %s); %s" % (status, nothing)}  # type: Dict[str, Any]
    running = _running_send(current, st, ts) if current is not None else None
    if running is not None:
        out["error"] = "%s. %s%s" % (out["error"], running[0][:1].upper(), running[0][1:])
        out["actionable_at"] = running[1]
    return out


def _send_never_finished(approval_id: str, lead: Optional[str], attempt: Optional[str], started_at: Optional[str],
                         claim_state: Optional[str], taken_by: str, ts: datetime) -> None:
    """Mark sent or Retry took over a card stuck at sending: its send started
    and never finished, and the worker that ran it wrote nothing of its own
    (it died, or was held up past SEND_CLAIM_LEASE_MINUTES). Its own Job_Log
    failure row, send_never_finished, so the deploy watch sees what the stuck
    push told Lorenzo: the attempt, when it started (None when its claim
    cannot tell), the claim's state (send_claim_lease) and who took the card
    (``taken_by``: mark_sent or retry)."""
    job_log.log_run("reply_engine.approval", "send_never_finished",
                    {"lead": lead, "approval": approval_id, "send_attempt": attempt, "send_started_at": started_at,
                     "claim": claim_state, "taken_by": taken_by, "taken_at": ts.isoformat()})


def mark_sent_url(card: Any, store=None, now: Optional[datetime] = None) -> Optional[str]:
    """The Mark sent link for a card stuck at send_failed, or at sending once
    Mark sent may take it: the app route /mark-sent/{token} (GET renders a
    confirmation page, the POST behind it calls mark_sent_manually). Built
    like action_urls, from the card's signed token, with
    configured_base_url(), the resolver base_url() is built on. ``card`` is
    an Approval, a stored card row, or a token.

    None when no usable base URL is set (unset, or local-only: a localhost
    link is dead on a phone), when the card carries no token, when the card
    was held because its recipient could not be confirmed (recipient_held:
    read from the card, and from ``store`` when one is given; a store that
    cannot be read gives no link), and for a sending card Mark sent may not
    take at ``now`` (sending_takeover, which reads the send claim from
    ``store``; without a store a sending card gets no link)."""
    if isinstance(card, dict):
        token = card.get("token")
    elif isinstance(card, str):
        token = card
    else:
        token = getattr(card, "token", None)
    token = str(token or "").strip()
    if "." not in token:
        return None
    if not isinstance(card, str):
        try:
            if recipient_held(card, store):
                return None
        except Exception as exc:  # noqa: BLE001 - unknown: no button
            logger.warning("no Mark sent link for %s: its recipient hold could not be read: %s",
                           token.split(".", 1)[0], exc)
            return None
        status = card.get("status") if isinstance(card, dict) else getattr(card, "status", None)
        if status == "sending":
            if store is None:
                return None
            try:
                _claim, problem = sending_takeover(card, store, now)
            except Exception as exc:  # noqa: BLE001 - unknown: no button
                logger.warning("no Mark sent link for %s: its send claim could not be read: %s",
                               token.split(".", 1)[0], exc)
                return None
            if problem:
                return None
    base = configured_base_url()
    if not base:
        return None
    return "%s/mark-sent/%s" % (base, token)


def _mark_sent_changed(st, approval_id: str) -> Dict[str, Any]:
    """The answer for a Mark sent that lost its status-guarded write."""
    try:
        current = (st.get(APPROVAL_PREFIX + approval_id) or {}).get("status")
    except Exception:  # noqa: BLE001
        current = None
    return {"ok": False, "status": current,
            "error": "the card changed before it could be marked sent (it is now %s); nothing was recorded"
                     % (current or "unknown")}


def _left_held(card: Approval, booking: Dict[str, Any], why: Optional[Dict[str, Any]], st, state: LeadState,
               ts: datetime):
    """Why Mark sent leaves the call this card holds unconfirmed, and what
    to do with it in GHL: (reason, todo), or (None, None) when a send would
    confirm it now (Keep on record, bound to this booking, and its time more
    than CONFIRM_MARGIN_MINUTES ahead, as send_approved requires)."""
    if why and why.get("reason") == "opt_out":
        return ("the lead %s (%s, %s)" % (_LEAD_SAID.get(str(why.get("category")), "gave a final no"),
                                           why.get("category"), _when_label(why.get("at"))),
                "Cancel it in GHL without notifying the lead. %s" % opt_out_advice(why.get("category")))
    if why:
        # Worded as the HELD push is (_hold_facts): "after the card was
        # drafted" only when their newer reply was sent after it. The verdict
        # itself proves only that it came after the reply this card answers.
        after = ("after the card was drafted" if _hold_facts(st, card, why).get("after_card")
                 else "after the reply this card answers")
        return ("the lead wrote again %s (%s, %s)" % (after, why.get("category"), _when_label(why.get("at"))),
                "Read the thread, then confirm it in GHL or cancel it there without notifying the lead.")
    decision, _problem = owner_booking_decision(st, card, state)
    slot = booking.get("slot")
    if decision == "release":
        return ("your recorded choice for it is Release the call",
                "Cancel it in GHL without notifying the lead, as you chose.")
    if decision != "keep":
        return ("no Keep choice for it is on record, or the booking changed since the card was drafted",
                "Read the reply that went out, then confirm the call in GHL or cancel it there without notifying "
                "the lead.")
    if not _slot_in_future(slot, ts):
        return ("its time has passed", "Settle it in GHL (a no-show, or cancel it without notifying the lead).")
    if not _slot_in_future(slot, ts + timedelta(minutes=CONFIRM_MARGIN_MINUTES)):
        return ("it starts in less than %d minutes, too close to confirm by email" % CONFIRM_MARGIN_MINUTES,
                "Confirm it with the lead by hand, or cancel it in GHL without notifying the lead.")
    return None, None


def _call_left_held_alert(card: Approval, booking: Dict[str, Any], left_why: str, todo: str) -> Dict[str, Any]:
    """Mark sent confirmed nothing for the call this card holds: say so, and
    what to do with it in GHL. Never raises."""
    return _alert("Call for %s still held after Mark sent" % card.lead_email,
                  "Card %s is marked sent, but the call booked for %s (appointment %s) was not confirmed: %s. It "
                  "stays on the calendar with its invite withheld and its reminders held; the engine released "
                  "nothing. %s" % (_approval_id(card), _slot_label(booking.get("slot")), booking.get("appointment_id"),
                                   left_why, todo))


def _record_not_updated(card: Approval, approval_id: str, problem: str,
                        invite: Optional[Dict[str, Any]] = None, row_unread: bool = False) -> Dict[str, Any]:
    """Mark sent won, but nothing on the lead's row moved (``problem``: it
    could not be read, parsed or written, or it is gone; ``row_unread``: it
    was never read, so no call it holds was looked at). Its own Job_Log
    failure row, which the deploy watch judges by status, and the push.
    Never raises."""
    job_log.log_run("reply_engine.approval", "mark_sent_record_not_updated",
                    {"lead": card.lead_email, "approval": approval_id, "error": problem})
    extra = ""
    if isinstance(invite, dict) and invite.get("released"):
        extra = (" The call's calendar invite WAS released in GHL, but the lead's booking record still shows it "
                 "waiting on this card.")
    elif row_unread:
        extra = (" If this card holds the lead's call, it was not confirmed: it stays on the calendar with its "
                 "invite withheld and its reminders held.")
    return _alert("Mark sent for %s: the lead's record was NOT updated" % card.lead_email,
                  "Card %s is marked sent, but %s: its history, its offered times and the follow-up ladder were "
                  "not updated.%s Check the lead by hand." % (approval_id, problem, extra))


def mark_sent_manually(approval_id: str, now: Optional[datetime], by: str = "lorenzo", store=None,
                       ghl=None) -> Dict[str, Any]:
    """Record a stuck card's reply as sent: Lorenzo checked the Instantly
    thread and the reply is there. ``approval_id`` may also be the card's
    token.

    * From send_failed, or from sending once Mark sent may take it
      (MARK_SENT_FROM; sending_takeover: its send claim is the card's own
      attempt and at least SEND_CLAIM_LEASE_MINUTES old, so nothing can
      still be running that send; a claim inside the lease, from another
      attempt, missing or unreadable is refused and nothing is recorded).
      Through the status-guarded _transition from the status read, bound for
      sending to the card's send attempt: one winner against a Retry, a Veto,
      the opt-out hold, a second tap, or the send it took over finishing
      after all (whose own writes refuse a card already sent,
      _save_unless_sent). The loser answers "card changed" and records
      nothing. The claim taken over stays, and is recorded on the card
      (MARK_SENT_KEY's send_claim), on the lead's history entry and on the
      Job_Log row (from_status, send_started_at). A card taken from sending
      also writes a send_never_finished Job_Log row (_send_never_finished):
      its worker wrote nothing, and the deploy watch must see it.
    * From pending, for a first-contact card only (pending_mark_sent_ok):
      Lorenzo sent it himself from the thread. Same bookkeeping, and the
      reply_sent_manually history entry releases draft_only's lock. It never
      confirms a call the card holds (no GHL invite): that stays held and an
      alert says so. Any other pending card is refused as before.
    * Never for a card its recipient check held (recipient_held: the record
      on the card, checked again under the card's lock, or the hold's own
      row): refused with RECIPIENT_HELD_REFUSAL, nothing moved or recorded.
    * Then the bookkeeping send_approved's success branch does, without the
      Instantly calls (the reply itself, and the interest status): the card's
      offered times stay reserved and it holds a send claim, as a sent card
      does (the failed attempt's own, or a fresh one); the lead row gets
      last_outbound_at, the offered slots, and a history entry (event
      reply_sent_manually, with reply_at, sent_at and first_reply); a card
      that owns the lead's unconfirmed call confirms it exactly when a send
      would (Keep on record, bound to the booking, more than
      CONFIRM_MARGIN_MINUTES ahead): the GHL invite released through ``ghl``
      (confirmed, to_notify=True), the held reminder ladder released, the
      booking marked confirmed; the ladder is armed under the row's lock
      (arm_refusal); and the Job_Log row the metrics read
      (reply_engine.approval / sent_manually) carries reply_at and sent_at.
      sent_at is when he marked it: the reply went out at or before then (the
      failed attempt was at send_failed_at; a send taken from sending started
      at send_started_at).
    * A lead row that cannot be read, cannot be parsed or is gone once the
      card is marked is never guessed at: nothing on the lead moves (no
      history, no call confirmed, no ladder). That, and a lead-row write
      that fails, is its own Job_Log failure row
      (reply_engine.approval / mark_sent_record_not_updated) and a push
      (_record_not_updated); the sent_manually row is written as always,
      and when the row was not read its first_reply is None (unknown, never
      the True _is_first_reply gives no row).
    * Nothing booked is ever released or cancelled here. A call this card
      holds that a send would not confirm (Release or no choice on record, a
      time that has passed or is under an hour away, or the lead's words,
      below) stays exactly as it is, and an alert says what to do in GHL.
    * The lead's own words since the reply the card answers
      (_lead_reply_verdict, as for a send: the sticky opt-out marker, an
      opt-out, a final no, a newer reply) still let the card move to
      sent_manually, but nothing is armed and no call is confirmed.

    ``ghl`` is the client the invite is released through (the app passes its
    own). Without one, shadow records the guarded would_do; live reports the
    invite as not released and alerts, as a send does."""
    st = _store(store)
    ts = _now(now)
    approval_id = str(approval_id or "").strip().split(".", 1)[0]
    try:
        card = _approval_row(st, approval_id) if approval_id else None
    except Exception as exc:  # noqa: BLE001 - nothing moves on a card that cannot be read
        return {"ok": False, "error": "could not read the card (%s); nothing was recorded, try again" % exc}
    if card is None:
        return {"ok": False, "error": "unknown card"}
    if card.status in SENT_STATUSES:
        return {"ok": False, "error": "already %s" % card.status, "status": card.status}
    if card.status not in MARK_SENT_FROM and not pending_mark_sent_ok(card, st):
        return {"ok": False, "status": card.status,
                "error": "only a card stuck at send_failed, or at sending once its send is %d minutes old, can be "
                         "marked sent; this one is %s" % (SEND_CLAIM_LEASE_MINUTES, card.status)}
    # Not for a card its recipient check held (fail closed): nothing of it
    # reached Instantly, and the thread may not be the lead's.
    try:
        held = recipient_held(card, st)
    except Exception as exc:  # noqa: BLE001 - unknown is refused
        return {"ok": False, "status": card.status,
                "error": "could not check whether this card's recipient was confirmed (%s); nothing was recorded, "
                         "try again" % exc}
    if held:
        return {"ok": False, "status": card.status, "recipient_held": held, "error": RECIPIENT_HELD_REFUSAL}
    # A sending card only once nothing can still be running its send.
    from_status = card.status
    attempt = card.send_attempt
    claim = None  # type: Optional[Dict[str, Any]]
    if from_status == "sending":
        try:
            claim, problem = sending_takeover(card, st, ts)
        except Exception as exc:  # noqa: BLE001 - unknown is refused
            return {"ok": False, "status": card.status,
                    "error": "could not read this card's send claim (%s); nothing was recorded, try again" % exc}
        if problem:
            return {"ok": False, "status": card.status, "error": problem}
    # The card's context is read before its status moves: the sweep deletes a
    # sent card's context row (sweep_card_contexts).
    context = card_context(st, approval_id)
    seen_before = context.get("processed_before")
    seen_before = seen_before if isinstance(seen_before, list) else None
    reply_at = context.get("reply_at")
    try:
        state_raw = st.get(card.state_key)
    except Exception as exc:  # noqa: BLE001 - nothing moves on a row that cannot be read
        return {"ok": False, "status": card.status,
                "error": "could not read the lead's row (%s); nothing was recorded, try again" % exc}
    # A sending card's decided_at is when it was approved, not a failure.
    failed_at = card.decided_at if from_status == "send_failed" else None
    started_at = (claim or {}).get("at")
    refused = {}  # type: Dict[str, Any]

    def _mark(row):
        result = dict(row.get("notify_result") or {})
        if isinstance(result.get(RECIPIENT_HELD_KEY), dict) and result[RECIPIENT_HELD_KEY]:
            # Held for its recipient since the read above: left exactly as it is.
            refused["recipient_held"] = dict(result[RECIPIENT_HELD_KEY])
            return row
        if from_status == "sending" and row.get("send_attempt") != attempt:
            # Another send of this card started since its claim was read.
            refused["send_attempt"] = True
            return row
        if from_status == "sending":
            result[MARK_SENT_KEY] = {"at": ts.isoformat(), "by": by, "send_failed_at": None, "from": "sending",
                                     "send_claim": dict(claim or {})}
        elif from_status == "pending":
            # A first-contact card Lorenzo sent himself from the thread.
            result[MARK_SENT_KEY] = {"at": ts.isoformat(), "by": by, "send_failed_at": None, "from": "pending"}
        else:
            result[MARK_SENT_KEY] = {"at": ts.isoformat(), "by": by, "send_failed_at": row.get("decided_at")}
        row["notify_result"] = result
        row["status"] = "sent_manually"
        row["decided_at"] = ts.isoformat()
        row["send_after"] = None
        return row

    # From the status read, and for sending bound to the send attempt read:
    # the send taken over, finishing after all, and Mark sent never both win.
    if not _transition(st, approval_id, (from_status,), _mark):
        return _mark_sent_changed(st, approval_id)
    if refused.get("recipient_held"):
        return {"ok": False, "status": card.status, "recipient_held": refused["recipient_held"],
                "error": RECIPIENT_HELD_REFUSAL}
    if refused:
        return {"ok": False, "status": from_status,
                "error": "the card changed before it could be marked sent (another send of it started); nothing "
                         "was recorded"}
    card.status = "sent_manually"
    card.decided_at = ts.isoformat()
    card.send_after = None
    # Only after the win: a claim written before it could outlive a Retry
    # that won instead and leave its pending card unsendable.
    _claim_send(st, approval_id, ts)
    if from_status == "sending":
        # Its worker wrote nothing of its own: this row is the watch's record.
        _send_never_finished(approval_id, card.lead_email, attempt, started_at, "stale", "mark_sent", ts)
    # The lead row as it stands now. One that cannot be read or parsed, or is
    # gone, is not guessed at from the read above: nothing on the lead moves
    # (no call confirmed, no history, no ladder) and Lorenzo is told, as for
    # a write that fails (_record_not_updated).
    row_problem = None  # type: Optional[str]
    state = None  # type: Optional[LeadState]
    try:
        state_raw = st.get(card.state_key)
    except Exception as exc:  # noqa: BLE001
        state_raw = None
        row_problem = "the lead's row could not be read (%s)" % exc
    if row_problem is None and not state_raw:
        row_problem = "the lead's row is missing"
    if row_problem is None:
        try:
            state = LeadState.from_store(state_raw)
        except Exception as exc:  # noqa: BLE001
            row_problem = "the lead's row could not be parsed (%s)" % exc
    why, refusal = (None, None) if state is None else _lead_reply_verdict(state_raw, card, seen_before, reply_at)

    invite = None
    show_rate_release = None
    left = None  # type: Optional[Dict[str, Any]]
    alerts = []  # type: List[Dict[str, Any]]
    if state is not None and owns_booking(card, state):
        booking = booking_of(state)
        try:
            if from_status == "pending":
                # Nothing ever went through the engine for this card, so
                # Mark sent sends nothing on its behalf either: no invite.
                left_why, todo = ("it was marked sent straight from a pending card (a reply you sent yourself), "
                                  "which confirms nothing on its own",
                                  "Confirm the call in GHL, or cancel it there without notifying the lead.")
            else:
                left_why, todo = _left_held(card, booking, why, st, state, ts)
        except Exception as exc:  # noqa: BLE001 - unreadable choice: confirm nothing, say so
            logger.warning("Mark sent for %s: the booking choice could not be read: %s", approval_id, exc)
            left_why, todo = ("its Keep or Release choice could not be read (%s)" % exc,
                              "Confirm the call in GHL, or cancel it there without notifying the lead.")
        if left_why is None:
            invite = release_booking_invite(state, ghl, ts)
            # Sent by hand: the engine never saw the text, so it is not taken
            # for a confirmation and the ladder's own stays.
            show_rate_release = release_show_rate_hold(state, st, ts, reason="marked_sent")
            if isinstance(show_rate_release, dict) and show_rate_release.get("error"):
                alerts.append(_alert(
                    "Show-rate reminders NOT started for %s" % card.lead_email,
                    "The reply was marked sent, but the held reminder ladder for appointment %s could not be "
                    "released (%s). Check the appointment's reminders by hand."
                    % (show_rate_release.get("appointment_id"), show_rate_release.get("error"))))
            _mark_booking_confirmed(state, approval_id, ts, invite)
        else:
            left = {"slot": booking.get("slot"), "appointment_id": booking.get("appointment_id"), "why": left_why}
            alerts.append(_call_left_held_alert(card, booking, left_why, todo))

    # Without the lead's row nobody knows whether this was the first answer
    # (_is_first_reply would say True): None, never a guess.
    first_reply = _is_first_reply(state) if state is not None else None
    cadence_result = None  # type: Optional[Dict[str, Any]]
    if state is not None:
        state.last_outbound_at = ts.isoformat()
        for iso in card.draft.offered_slots:
            if iso not in state.offered_slots:
                state.offered_slots.append(iso)
        state.history.append({"at": ts.isoformat(), "event": "reply_sent_manually", "approval": approval_id,
                              "by": by, "reply_at": reply_at, "sent_at": ts.isoformat(),
                              "send_failed_at": failed_at, "first_reply": first_reply,
                              "from_status": from_status, "send_started_at": started_at})
        try:
            if why:
                # The lead's words rule the ladder out: recorded, never armed.
                save_lead_state(st, state, state_raw)
                cadence_result = {"armed": False, "reason": refusal}
            else:
                box = {}  # type: Dict[str, Any]
                save_lead_state(st, state, state_raw,
                                finish=_arm_under_lock(card, _open_other_cards(st, card, state_raw, ts), ts, box,
                                                       seen_before=seen_before, reply_at=reply_at))
                cadence_result = box.get("result") or {"armed": False, "error": "the arm decision did not run"}
        except Exception as exc:  # noqa: BLE001 - the card is marked; say what did not land
            logger.exception("Mark sent for %s: the lead row could not be written", approval_id)
            cadence_result = {"armed": False, "error": "the lead row could not be written: %s" % exc}
            row_problem = "the lead's row could not be written (%s)" % exc
    if row_problem is not None:
        if cadence_result is None:
            cadence_result = {"armed": False, "error": row_problem}
        alerts.append(_record_not_updated(card, approval_id, row_problem, invite, row_unread=state is None))
    armed = bool((cadence_result or {}).get("armed"))
    job_log.log_run("reply_engine.approval", "sent_manually",
                    {"lead": card.lead_email, "approval": approval_id, "by": by,
                     "to": card.reply_to or card.lead_email, "campaign_id": card.campaign_id,
                     "eaccount": card.eaccount, "email_id": card.email_id, "subject": card.draft.subject,
                     "slots": card.draft.offered_slots, "reply_at": reply_at, "sent_at": ts.isoformat(),
                     "send_failed_at": failed_at, "first_reply": first_reply, "invite": invite,
                     "from_status": from_status, "send_started_at": started_at,
                     "show_rate_released": bool((show_rate_release or {}).get("released")),
                     "booking_left_held": left, "lead_reply": why, "cadence_armed": armed,
                     "cadence_not_armed": None if armed else
                     ((cadence_result or {}).get("reason") or (cadence_result or {}).get("error"))})
    return {"ok": True, "status": "sent_manually", "shadow": False, "reply": None, "interest": None,
            "interest_value": None, "interest_error": None, "cadence": cadence_result, "invite": invite,
            "show_rate": show_rate_release, "booking_released": None, "by": by, "marked_at": ts.isoformat(),
            "send_failed_at": failed_at, "first_reply": first_reply, "lead_reply": why,
            "booking_left_held": left, "alerts": alerts, "from_status": from_status, "send_started_at": started_at}


def _approval_row(st, approval_id: str) -> Optional[Approval]:
    """The stored card for this id, without the token check. Never raises."""
    raw = st.get(APPROVAL_PREFIX + approval_id)
    if not raw:
        return None
    try:
        return Approval.model_validate(raw)
    except Exception:  # noqa: BLE001
        return None


def _retired(now: datetime):
    """The status-guarded write that marks a stored card superseded (its
    status and decided_at, nothing else)."""
    def _apply(row):
        row["status"] = "superseded"
        row["decided_at"] = now.isoformat()
        return row
    return _apply


def supersede_pending(store, state: LeadState, now: datetime, keep_token: Optional[str] = None) -> List[str]:
    """Retire this lead's still-open approvals when a newer reply arrives.

    Two replies forty seconds apart used to raise two independent cards holding
    four different slots for one lead, and approving both sent two near-identical
    emails on the same thread.

    Matched by approval id, not by token: edit() and accept_requested() re-sign
    the card, and state.approvals still holds the old token, so load(old) failed
    the HMAC check and an edited (or Book-as-asked) card queued at 20:00 stayed
    approved_queued beside its replacement and went out at 07:00. Returns the
    cards' current tokens.
    """
    st = _store(store)
    out = []  # type: List[str]
    keep_id = keep_token.split(".", 1)[0] if keep_token else None
    seen = set()
    for token in list(state.approvals):
        approval_id = str(token).split(".", 1)[0]
        if approval_id in seen or (keep_id and approval_id == keep_id):
            continue
        seen.add(approval_id)
        approval = _approval_row(st, approval_id)
        if approval is None or approval.status not in SENDABLE_STATUSES:
            continue
        # Written only while the stored card is still open (pending or
        # queued), under the store's lock, and only its status: a send that
        # started since the read (Approve on another device, the 07:00 flush)
        # is never overwritten with superseded, and nothing it wrote is lost
        # (S-rest round 6 approval, flag 18). Lost, its times stay held.
        if not _transition(st, approval_id, SENDABLE_STATUSES, _retired(now)):
            logger.warning("not superseding %s: the card moved on before the write", approval_id)
            continue
        release_slots(st, approval_id)
        out.append(approval.token)
    if out:
        job_log.log_run("reply_engine.approval", "superseded", {"lead": state.lead_email, "count": len(out)})
    return out


# A booking owner in one of these can never send the confirmation: nothing
# retries 'superseded', and a 'send_failed' / 'blocked' / 'stale_slots' card is
# replaced by the newer reply's card rather than retried beside it.
# 'expired' too: a card that expired holding a call waits on Lorenzo's Keep /
# Release (decide_expired_booking), and a newer reply from the lead settles
# the call the same way it settles any other retired owner's.
ORPHAN_OWNER_STATUSES = ("superseded", "send_failed", "blocked", "stale_slots", "expired")


def orphaned_booking_owner(store, state: LeadState, superseded: Optional[List[str]] = None) -> Optional[str]:
    """The approval id of a superseded card that still owns the lead's
    unconfirmed booking, or None when the booking (if any) has a live owner.

    Read from the store rather than only from this run's ``superseded`` list,
    so a pipeline that crashed after supersede_pending and before the booking
    was settled is still settled by the retry.
    """
    st = _store(store)
    booking = booking_of(state)
    if not booking.get("slot"):
        return None
    if booking.get("cancel_failed"):
        return None  # already being cancelled (retry_failed_cancels); nothing to hand over
    owner = booking.get("owner")
    if owner:
        raw = st.get(APPROVAL_PREFIX + owner) or {}
        return owner if raw.get("status") in ORPHAN_OWNER_STATUSES else None
    if booking.get("awaiting_approval") is False:
        return None
    # A booking written before owners were tracked: the superseded
    # booking_confirmation card for the booked slot is its owner.
    for token in superseded or []:
        approval = load(token, st)
        if approval is not None and approval.status == "superseded" and owns_booking(approval, state):
            return _approval_id(approval)
    return None


def will_transfer_booking(draft: Draft, slot_iso: Optional[str], now: datetime) -> bool:
    """The one rule for a superseded card's booking: handed to the new card
    only when the new draft talks about exactly the booked time AND that time
    is still ahead; released otherwise. app.py writes the card note from this
    same rule, before settle_superseded_booking acts on it."""
    return keeps_booked_slot(draft, slot_iso) and _slot_in_future(slot_iso, now)


def _slot_in_future(slot_iso: Optional[str], now: datetime) -> bool:
    try:
        return slots.parse_iso(slot_iso) > now
    except (ValueError, TypeError):
        return False


def _retire_orphan_owner(st, owner: str, now: datetime) -> None:
    """A booking owner stuck at send_failed / blocked / stale_slots is marked
    superseded (its slots released), so retry() cannot bring back a card whose
    booking was just handed on or released - one live card owns a booking."""
    card = _approval_row(st, owner)
    retirable = tuple(s for s in ORPHAN_OWNER_STATUSES + SENDABLE_STATUSES if s != "superseded")
    if card is None or card.status not in retirable:
        return
    # Status-guarded, under the store's lock, and only the status: a Retry
    # that took the card to sending, or a send that finished, since the read
    # is never overwritten, and then nothing of it is released (S-rest
    # round 6 approval, flag 18).
    if not _transition(st, owner, retirable, _retired(now)):
        logger.warning("not retiring booking owner %s: the card moved on before the write", owner)
        return
    release_slots(st, owner)
    for key in (SEND_CLAIM_PREFIX + owner, RECIPIENT_HOLD_PREFIX + owner):
        try:
            st.delete(key)
        except Exception:  # noqa: BLE001 - bookkeeping only
            pass


def settle_superseded_booking(store, state: LeadState, new_approval: Optional[Approval], now: datetime,
                              ghl=None, instantly=None, superseded: Optional[List[str]] = None,
                              old_owner: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Give a superseded card's booking an explicit new owner, or release it.

    * The new draft talks about exactly the booked slot AND that slot is still
      ahead: the booking is handed to the new card, so approving it releases the invite and the held
      show-rate ladder, and vetoing or expiring it tears the booking down.
    * Anything else (a counter-proposal, fresh times, no replacement card):
      the booking is released now - GHL cancel with to_notify=False, because
      the lead was never told about that call, plus the slot reservation, the
      held ladder and the store rows (cancel_booking).

    Returns None when there is nothing to settle. Never raises: the new card
    already exists and must not be lost to bookkeeping.
    """
    st = _store(store)
    owner = old_owner or orphaned_booking_owner(st, state, superseded)
    if not owner:
        return None
    booking = booking_of(state)
    lead = getattr(state, "lead_email", None)
    try:
        _retire_orphan_owner(st, owner, now)
        if new_approval is not None and will_transfer_booking(new_approval.draft, booking.get("slot"), now):
            new_id = _approval_id(new_approval)
            claim_booking(state, new_id, now, transferred_from=owner)
            record_booking_intent(st, new_approval, state)
            state.history.append({"at": now.isoformat(), "event": "booking_transferred", "from": owner,
                                  "to": new_id, "slot": booking.get("slot")})
            job_log.log_run("reply_engine.approval", "booking_transferred",
                            {"lead": lead, "from": owner, "to": new_id, "slot": booking.get("slot"),
                             "appointment_id": booking.get("appointment_id")})
            return {"action": "transferred", "from": owner, "to": new_id, "slot": booking.get("slot"),
                    "appointment_id": booking.get("appointment_id")}
        released = cancel_booking(state, ghl, instantly, now, store=st, reason="superseded", to_notify=False)
        state.history.append({"at": now.isoformat(), "event": "booking_released", "from": owner,
                              "slot": booking.get("slot"), "reason": "superseded"})
        job_log.log_run("reply_engine.approval", "booking_released",
                        {"lead": lead, "from": owner, "slot": booking.get("slot"),
                         "appointment_id": booking.get("appointment_id"),
                         "appointment_error": (released or {}).get("appointment_error")})
        out = {"action": "released", "from": owner, "slot": booking.get("slot"),
               "appointment_id": booking.get("appointment_id"), "cancelled": released}
        if (released or {}).get("cancel_failed"):
            # cancel_booking kept the booking and its hold, queued a retry and
            # alerted Lorenzo; say so here rather than reporting a release.
            out["action"] = "release_pending"
            out["alert"] = released.get("alert")
        return out
    except Exception as exc:  # noqa: BLE001
        logger.exception("could not settle the superseded booking for %s", lead)
        job_log.log_run("reply_engine.approval", "booking_settle_failed", {"lead": lead, "error": str(exc)})
        return {"action": "error", "from": owner, "error": str(exc),
                "alert": _alert("Booking for %s needs you" % lead,
                                "A newer reply superseded the card that booked %s and the engine could not hand "
                                "the booking to the new card or release it (%s). Check the calendar by hand."
                                % (booking.get("slot"), exc))}


def campaign_key_of(approval: Approval) -> Optional[str]:
    """The offers.md key for this card: stored at create time, else resolved
    from the campaign id, so a card minted before the field existed still gets
    the cross-offer guard."""
    if approval.campaign_key:
        return approval.campaign_key
    meta = settings.CAMPAIGN_BY_ID.get(approval.campaign_id or "") or {}
    return meta.get("key")


def _dated_label(dt: datetime) -> str:
    """'Tue Sep 29 2:00pm', the wording booking.py's counter-proposals use."""
    time_part = slots.format_slot(dt).split(" ", 1)[1]
    return "%s %s %d %s" % (dt.strftime("%a"), dt.strftime("%b"), dt.day, time_part)


def slots_named_in(body: str, now: datetime, extra: Optional[List[str]] = None) -> List[str]:
    """The offerable times the body names in the engine's own wording, in the
    order it names them. For the slot REGISTRY only (which times an edited card
    holds against other leads); it never decides what happens to a booking.

    Recognises the dated wording ("Tue Sep 29 2:00pm") and the short one
    ("Tue 2:00pm"), case- and whitespace-insensitively, over a universe of the
    slots this card already held plus the ordinary Mon-Fri 12:00-18:00 grid.
    """
    from services.reply_engine.draft import fallback_free_slots

    universe = list(extra or []) + fallback_free_slots(now)
    text = " ".join((body or "").lower().split())
    # Dedupe the short label on first match: "Tue 2:00pm" names this coming
    # Tuesday, and the grid runs nine days, so the same wording matches next
    # week's Tuesday too. The card's own slots come first and the grid is
    # chronological, so the first match for a label is the one Lorenzo means.
    seen_labels = set()  # type: set
    found = {}  # type: Dict[str, int]
    for iso in universe:
        try:
            dt = slots.to_tz(slots.parse_iso(iso))
        except (ValueError, TypeError):
            continue
        key = dt.isoformat()
        dated = _dated_label(dt).lower()
        idx = text.find(dated)
        if idx >= 0:
            found[key] = min(idx, found.get(key, idx))
            continue
        label = slots.format_slot(dt).lower()
        if label in seen_labels:
            continue
        seen_labels.add(label)
        idx = text.find(label)
        if idx >= 0 and key not in found:
            found[key] = idx
    return [iso for iso, _ in sorted(found.items(), key=lambda kv: kv[1])]


def _kept_problems(problems) -> List[str]:
    """The problems an edit must NOT clear: the ones about the booking, not the copy.

    booking.NON_COPY_PROBLEMS names them (slot_not_verified, slot_already_taken,
    appointment_not_created, zoom_not_connected). Imported lazily because
    booking imports cadence which imports this module's siblings; a missing
    booking module must not break editing.

    ZOOM_NOT_CONNECTED is deliberately NOT kept. It is an operational note that
    accept_requested and app.py already strip into the rationale, so re-adding
    it here would let an edit turn a sendable card into a blocked one.
    """
    try:
        from services.reply_engine.booking import NON_COPY_PROBLEMS
    except Exception as exc:  # noqa: BLE001
        logger.warning("booking.NON_COPY_PROBLEMS unavailable: %s", exc)
        return []
    keep = tuple(p for p in NON_COPY_PROBLEMS if p != ZOOM_NOT_CONNECTED)
    return [p for p in (problems or []) if p in keep]


def edit(token: str, new_body: str, store=None, now: Optional[datetime] = None,
         booking_choice: Optional[str] = None) -> Dict[str, Any]:
    """Replace the draft body (validated); returns the new token (the hash changed).

    Two things beyond the body have to move with it. The cross-offer proof and
    guarantee guards are only armed when validate_draft is given a campaign key,
    and this is the one path where a human rewrites the email by hand - pasting
    the reactivation proof line into a cleaning_trigger card passed clean and was
    sent immediately. And the slot registry has to follow the new times: leaving
    draft.offered_slots on the times Lorenzo just replaced meant the times he
    actually wrote were free for the next lead's card, while the ones he deleted
    stayed blocked for everyone.

    A card that holds the lead's unconfirmed booking needs ``booking_choice``:
    'keep' (send the invite for the booked time) or 'release' (cancel it
    silently, no invite). Without one nothing is saved. The choice, not the
    edited words, decides what the send does with the booking; it is recorded
    bound to the booking (appointment id and slot) and to this text.
    """
    from services.reply_engine.draft import lead_terms, validate_draft

    st = _store(store)
    ts = _now(now)
    approval = load(token, st)
    if approval is None:
        return {"ok": False, "error": "unknown or invalid token"}
    if approval.status not in SENDABLE_STATUSES + ("blocked",):
        return _already(approval, st, ts)
    raw = st.get(approval.state_key)
    state = LeadState.from_store(raw) if raw else None
    problems = validate_draft(new_body, booking_link=approval.draft.booking_link,
                              campaign_key=campaign_key_of(approval),
                              allow_terms=lead_terms(None, state))
    if problems:
        return {"ok": False, "error": "draft rejected", "problems": problems, "token": approval.token}
    approval_id = approval.token.split(".", 1)[0]
    booked = _booked_slots_for(state)
    owner_slot = booking_of(state).get("slot") if owns_booking(approval, state) else None
    choice = (booking_choice or "").strip().lower() or None
    if owner_slot and choice not in BOOKING_CHOICES:
        return {"ok": False, "error": "choose Keep the call or Release the call for %s" % _slot_label(owner_slot),
                "needs_booking_choice": True, "booked_slot": owner_slot, "token": approval.token}
    # The text reader is only for the slot registry (which times this card
    # holds against other leads); it never decides what happens to a booking.
    named = slots_named_in(new_body, ts, extra=([owner_slot] if owner_slot else []) +
                           list(approval.draft.offered_slots) + booked)
    if owner_slot and choice == "keep":
        new_slots = [owner_slot]
    elif owner_slot:
        new_slots = [iso for iso in named if not _same_slot(iso, owner_slot)]
    else:
        new_slots = named
    read_status = approval.status
    offered_before = list(approval.draft.offered_slots)
    # Claimed, not just recorded: a time Lorenzo typed that another lead's card
    # or call already holds is never offered twice (SAL-10). The edit is saved
    # with a problem that blocks the send until he picks other times. The new
    # times are claimed BEFORE the card's old ones are given back, and those go
    # only once the edit is written (below): an edit that loses its write drops
    # only what it claimed, and the times the card's reply offers stay held.
    try:
        taken = claim_slots(st, approval.lead_email, new_slots, ts, fields={"approval": approval_id})
    except Exception as exc:  # noqa: BLE001 - an unreadable registry holds the card rather than double-offer
        logger.warning("could not claim the edited slots for %s: %s", approval.lead_email, exc)
        taken = list(new_slots)
    approval.draft.offered_slots = new_slots
    approval.draft.body_text = new_body
    # validate_draft only checks COPY. Clearing the list outright also dropped
    # booking's slot_not_verified / slot_already_taken / appointment_not_created,
    # and app.py's edit_submit calls approve() straight afterwards - so rewording
    # the body was enough to confirm a prospect into a call GHL never created.
    # Those survive an edit; only Lorenzo booking it by hand clears them.
    approval.draft.problems = validate_draft(
        new_body, booking_link=approval.draft.booking_link,
        campaign_key=campaign_key_of(approval),
        allow_terms=lead_terms(None, state)) + _kept_problems(approval.draft.problems)
    if taken:
        approval.draft.problems = list(approval.draft.problems) + [
            "%s %s already held for another lead's card or call; offer other times"
            % (", ".join(_slot_label(iso) for iso in taken), "is" if len(taken) == 1 else "are")]
    approval.draft.model = "edited"
    # CT3: an edited body is never a template render: it is sent only on
    # Lorenzo's own Approve, and the auto path refuses it.
    approval.draft.template_id = None
    approval.draft.template_hash = None
    approval.draft.template_parts = {}
    approval.approved_by = None
    approval.auto_send = None
    approval.status = "pending"
    # Written only over the status read above, under the store's lock (S-rest
    # round 6). A send that started since (the card at sending, or already
    # sent) keeps the card and its draft: the whole-card save that stood here
    # put a card whose reply was going out back to pending with the new text,
    # and Approve sent the lead a second reply. A newer reply's supersede, a
    # hold or the expiry keeps it the same way.
    if _rewrite_card(st, approval, read_status, ("draft", "status", "approved_by", "auto_send")) is None:
        _release_card_slots(st, approval_id, drop=[iso for iso in new_slots if iso not in offered_before])
        return dict(_changed_meanwhile(st, approval_id, ts, "the edit was not saved"), token=token)
    _release_card_slots(st, approval_id, keep=[] if taken else new_slots)
    if owner_slot:
        st.set(BOOKING_CHOICE_PREFIX + approval_id,
               dict(_booking_binding(state), choice=choice, draft_hash=draft_hash(approval.draft),
                    at=ts.isoformat(), approval=approval_id))
    else:
        try:
            st.delete(BOOKING_CHOICE_PREFIX + approval_id)
        except Exception:  # noqa: BLE001
            pass
    job_log.log_run("reply_engine.approval", "edited",
                    {"lead": approval.lead_email, "approval": approval_id, "slots": new_slots,
                     "booking_choice": choice if owner_slot else None})
    out = {"ok": True, "status": "pending", "token": approval.token, "offered_slots": new_slots,
           "problems": list(approval.draft.problems)}
    if owner_slot:
        out["booking_choice"] = choice
        out["booked_slot"] = owner_slot
    return out


def _requested_slot_taken(store, approval: Approval, now: datetime) -> Optional[str]:
    """Why the asked-for time is not free, or None.

    Two sources, both the ones booking.verify_slot would have consulted if it
    had not been handed a one-element free list: Lorenzo's known bookings
    (config/ids.json, minus this lead's own call) and the global registry of
    times offered to other leads.
    """
    iso = approval.requested_slot
    if not iso:
        return None
    try:
        slot = slots.to_tz(slots.parse_iso(iso))
    except (ValueError, TypeError):
        return None
    try:
        from services.reply_engine import booking as booking_mod

        if booking_mod.collides_with_known_booking(slot, exclude_email=approval.lead_email):
            return "a call is already on the calendar at that time"
    except Exception as exc:  # noqa: BLE001 - never block an override on a helper error
        logger.warning("known-booking check failed: %s", exc)
    key = int(slot.timestamp())
    for other in offered_slots(store, now, exclude_lead=approval.lead_email):
        try:
            if int(slots.parse_iso(other).timestamp()) == key:
                return "that time is held for another lead's pending card"
        except (ValueError, TypeError):
            continue
    return None


def _availability_including(store, approval: Approval, now: datetime) -> List[str]:
    """The ordinary availability view plus the one time Lorenzo is waiving his
    slot rule for, so verify_slot still checks the calendar for everything else."""
    from services.reply_engine.draft import fallback_free_slots

    others = set()  # type: set
    for iso in offered_slots(store, now, exclude_lead=approval.lead_email):
        try:
            others.add(int(slots.parse_iso(iso).timestamp()))
        except (ValueError, TypeError):
            continue
    out = []  # type: List[str]
    try:
        from services.reply_engine import booking as booking_mod

        busy = booking_mod.known_busy_blocks(exclude_email=approval.lead_email)
    except Exception:  # noqa: BLE001
        busy = []
    for iso in fallback_free_slots(now, busy_blocks=busy):
        try:
            if int(slots.parse_iso(iso).timestamp()) not in others:
                out.append(iso)
        except (ValueError, TypeError):
            continue
    if approval.requested_slot and approval.requested_slot not in out:
        out.append(approval.requested_slot)
    return out


def accept_requested(token: str, ghl, instantly, store=None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Lorenzo overrides his own slot rule and takes the time the lead asked for.

    Books it through services.reply_engine.booking (guarded, so shadow records a
    would_do), swaps the counter-proposal for the confirmation draft and sends
    that. Only reachable when create_approval recorded a ``requested_slot``.

    The confirmation draft is written over the card only while the card is
    still at the status read here, under the store's lock (S-rest round 6).
    A card that moved while the call was being booked (a send started or
    finished with the counter-proposal, a newer reply superseded it, the
    lead's words held it, it expired) keeps its own draft and the times it
    offers, and what the booking wrote is undone (_book_as_asked_undone): the
    call is cancelled again without notifying the lead (shadow: a would_do),
    its time goes back in the pool, and one push says so.
    """
    from services.reply_engine import booking as booking_mod

    st = _store(store)
    ts = _now(now)
    approval = load(token, st)
    if approval is None:
        return {"ok": False, "error": "unknown or invalid token"}
    if approval.status not in SENDABLE_STATUSES:
        return _already(approval, st, ts)
    read_status = approval.status
    if not approval.requested_slot:
        return {"ok": False, "error": "no requested time on this approval"}
    raw = st.get(approval.state_key)
    if not raw:
        return {"ok": False, "error": "no lead state for %s" % approval.state_key}
    # The lead's own words since the card was drafted, BEFORE anything is
    # booked: the send at the end (approve) would refuse a lead who has since
    # opted out or written again, but only after book() had put a call on the
    # calendar and moved their GHL stage and Instantly interest. Held here
    # exactly as the send holds it.
    context = card_context(st, _approval_id(approval))
    seen_before = context.get("processed_before")
    why = lead_reply_hold(raw, approval, seen_before if isinstance(seen_before, list) else None,
                          reply_at=context.get("reply_at"))
    if why:
        held = _hold_for_lead_reply(approval, st, ts, why, SENDABLE_STATUSES)
        return held if held is not None else _card_changed(st, _approval_id(approval))
    state = LeadState.from_store(raw)
    # The lead's previous call is still being cancelled (the GHL cancel failed
    # and is retrying): book() would take it for a reschedule and cancel it a
    # second way, or book beside a call that is still live. Nothing is booked
    # or sent until that cancel is settled; the reply pipeline refuses the
    # same thing (app._reply_draft).
    if cancel_pending(state):
        pending = booking_of(state)
        return {"ok": False, "status": approval.status, "slot": approval.requested_slot,
                "error": ("this lead's previous call (%s) is still being cancelled in GHL; nothing was booked or "
                          "sent. Try again once that cancel is done, or tap 'I cancelled it' on its alert"
                          % _slot_label(pending.get("slot")))}
    # Lorenzo is waiving his own POLICY rules (outside_window / weekend /
    # too_soon / beyond_horizon), not the question of whether the time is free.
    # free_slots=[the slot] made booking.verify_slot a tautology - the
    # membership test passed by construction - so tapping "Book as asked" could
    # write over a call already on the calendar or a slot reserved for another
    # lead's pending card, and then mail "Locked in ..., invite on the way."
    taken = _requested_slot_taken(st, approval, ts)
    if taken:
        return {"ok": False, "error": "that time is no longer free: %s" % taken, "status": approval.status,
                "slot": approval.requested_slot}
    free = _availability_including(st, approval, ts)
    before = dict(booking_of(state))
    try:
        try:
            # allow_outside_rules=True: this endpoint IS Lorenzo waiving his own
            # 12:00-18:00 Mon-Fri rule for this one lead (that is what the
            # "Book as asked" button means). Availability is NOT waived -
            # booking.verify_slot still runs against `free`, which
            # _availability_including builds from the real grid.
            result = booking_mod.book(state, approval.requested_slot, ghl, instantly, now=ts,
                                      lead_tz=approval.requested_lead_tz, free_slots=free,
                                      store=st, allow_outside_rules=True)
        except TypeError:  # older booking.book without free_slots/store
            result = booking_mod.book(state, approval.requested_slot, ghl, instantly, now=ts, lead_tz=approval.requested_lead_tz)
    except Exception as exc:  # noqa: BLE001 - a booking failure must not lose the approval
        logger.exception("accept_requested booking failed")
        return {"ok": False, "error": "booking failed: %s" % exc}
    draft = result.draft
    draft.problems = [p for p in list(draft.problems or []) if p != ZOOM_NOT_CONNECTED]
    draft.rationale = "%s; Lorenzo accepted the time the lead asked for (%s)" % (draft.rationale or "booking confirmation",
                                                                                approval.requested_status)
    approval_id = approval.token.split(".")[0]
    # Booked only when the booking is really on the state for the asked-for
    # time: booking.book() answers a refused or failed write (slot taken, GHL
    # error, nothing created in live) with an unsendable draft and no booking.
    booked = _same_slot(booking_of(state).get("slot"), approval.requested_slot) and not any(
        p in (getattr(booking_mod, "NON_COPY_PROBLEMS", ()) or ()) and p != ZOOM_NOT_CONNECTED
        for p in draft.problems)
    approval.draft = draft
    approval.label = draft.label or approval.label
    approval.status = "pending"
    # Written only over the status read above, under the store's lock (S-rest
    # round 6). The whole-card save that stood here put a card whose
    # counter-proposal was going out (or had gone out) back to pending with
    # the confirmation, and the approve below sent the lead a second reply.
    if _rewrite_card(st, approval, read_status, ("draft", "label", "status")) is None:
        return _book_as_asked_undone(st, approval, state, before, ghl, instantly, ts)
    if booked:
        claim_booking(state, approval_id, ts)
    release_slots(st, approval_id)  # the counter-proposal times go back in the pool
    reserve_slots(st, approval.lead_email, draft.offered_slots, approval_id, ts)  # the booked one does not
    if booked:
        record_booking_intent(st, approval, state)
    save_lead_state(st, state, raw)
    job_log.log_run("reply_engine.approval", "accepted_requested",
                    {"lead": approval.lead_email, "slot": approval.requested_slot, "status": approval.requested_status,
                     "shadow": result.shadow, "booked": booked})
    if not booked:
        # Nothing was written to the calendar, so nothing is sent either: the
        # card now carries the "NOT SENT - for Lorenzo" body and its problems.
        problems = list(draft.problems or []) or ["the booking was not written"]
        logger.error("book-as-asked for %s failed: %s", approval.lead_email, problems)
        return {"ok": False, "status": approval.status, "error": "booking failed: %s" % "; ".join(problems),
                "problems": problems, "booked": None, "token": approval.token,
                "zoom_not_connected": result.zoom_not_connected}
    # ghl=: send_approved releases the GHL invite through it. Without it the
    # release fell through to a bare guard_write that, in live, writes nothing
    # and still answered released: True.
    sent = approve(approval.token, instantly, st, ts, ghl=ghl)
    out = dict(sent, booked=approval.requested_slot, token=approval.token,
               zoom_not_connected=result.zoom_not_connected)
    pipeline_errors = list(getattr(result, "pipeline_errors", None) or [])
    if pipeline_errors:
        # Booked, pipeline update failed: the call and its held ladder exist,
        # only the CRM bookkeeping is behind. Not a failed booking.
        out["pipeline_errors"] = pipeline_errors
        out["pipeline_alert"] = _alert(
            "Booked, pipeline update failed for %s" % approval.lead_email,
            "The call for %s is on the calendar, but: %s. Fix the stage / interest by hand."
            % (approval.requested_slot, "; ".join(pipeline_errors)))
    return out


# Why a call Book as asked had just booked is cancelled again: its card moved
# while the call was being booked (accept_requested's guarded write lost). The
# cancel reason, the lead-history event and the Job_Log status.
BOOK_AS_ASKED_UNDONE = "book_as_asked_undone"
# What the card's new status means for the lead, in the push.
_UNDONE_CARD_NOW = {
    "sending": "its counter-proposal is the reply going out now",
    "sent": "its counter-proposal is the reply that went out",
    "sent_manually": "its reply was marked sent",
    "superseded": "a newer reply from the lead replaced it; answer the card for that reply instead",
    "blocked": "it was held; open it to see why",
    "vetoed": "it was vetoed",
    "expired": "it expired",
}


def _said_label(category: Any) -> str:
    """"asked to be removed", "said not now"...: what the lead's no was."""
    return _LEAD_SAID.get(str(category or "").strip().lower(), "said no (%s)" % (category or "opt-out"))


def _lead_row_or_none(st, state_key: str) -> Optional[Dict[str, Any]]:
    try:
        row = st.get(state_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not re-read %s: %s", state_key, exc)
        return None
    return row if isinstance(row, dict) else None


def _same_call(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Two booking records of one call: the same appointment at the same time."""
    return (a.get("appointment_id"), a.get("slot")) == (b.get("appointment_id"), b.get("slot"))


def _book_as_asked_undone(st, approval: Approval, state: LeadState, before: Dict[str, Any], ghl, instantly,
                          ts: datetime) -> Dict[str, Any]:
    """accept_requested lost its card write: the card moved while the call
    was being booked. The card keeps its own draft and the times it offers
    (nothing of the counter-proposal was released). What the booking wrote is
    undone: a call it made (``state``'s booking, when it is not the one
    ``before`` recorded) is cancelled again through cancel_booking, without
    notifying the lead (shadow: the would_do record), which gives its time
    back to the pool, tears down its hold and records and sets the
    opportunity and Instantly interest back. The lead row is not written
    with what book() changed on ``state``; a history entry records the undo.

    A cancel GHL refuses keeps the call held and retried as every failed
    cancel is (its booking goes on the row, marked cancel_failed, so the
    retry and the "I cancelled it" link find it). Either way one push says
    what was undone, and a book_as_asked_undone Job_Log row records it.
    Nothing booked (book() refused, or the call was already this one): the
    refusal alone.

    A call another writer put on the lead row while this one was being
    booked (neither ``before``'s nor this one: a newer reply's card booked
    it) is never overwritten. The push names it: the undo set the
    opportunity and interest back under it, and a cancel GHL refused cannot
    be retried from a row that holds another call, so Lorenzo cancels that
    one by hand."""
    approval_id = _approval_id(approval)
    out = _changed_meanwhile(st, approval_id, ts, "Book as asked was not applied")
    out["booked"] = None
    made = dict(booking_of(state))
    if not made.get("slot") or _same_call(made, before):
        return out
    slot_label = _slot_label(made.get("slot"))
    try:
        cancelled = cancel_booking(state, ghl, instantly, ts, store=st, reason=BOOK_AS_ASKED_UNDONE,
                                   announce=False, guard_reset=True) or {}
    except Exception as exc:  # noqa: BLE001 - reported below, never raised
        logger.exception("could not cancel the call Book as asked booked for %s", approval.lead_email)
        cancelled = {"cancelled": False, "appointment_error": "cancel raised: %s" % exc}
    done = bool(cancelled.get("cancelled"))
    error = None if done else str(cancelled.get("appointment_error") or "cancel_failed")
    entry = {"at": ts.isoformat(), "event": BOOK_AS_ASKED_UNDONE, "approval": approval_id, "slot": made.get("slot"),
             "appointment_id": made.get("appointment_id"), "cancelled": done}
    kept = dict(booking_of(state) or made)
    if not done and not kept.get("cancel_failed"):
        kept["cancel_failed"] = {"at": ts.isoformat(), "reason": BOOK_AS_ASKED_UNDONE, "error": error,
                                 "attempts": 1, "to_notify": False}

    box = {}  # type: Dict[str, Any]

    def _record(raw):
        current = dict((raw.get("cadence") or {}).get("booking") or {})
        # Another call on the row (not the one this action read, not the one
        # it made) was booked meanwhile: it is never overwritten.
        other = bool(current.get("slot")) and not _same_call(current, before) and not _same_call(current, made)
        box["other"] = current if other else None
        if not done and not other:
            # Still on the calendar: onto the row, where the cancel retry and
            # the "I cancelled it" link read it.
            raw["cadence"] = dict(raw.get("cadence") or {}, booking=kept)
        record = dict(entry, other_call=current.get("appointment_id")) if other else entry
        raw["history"] = list(raw.get("history") or []) + [record]
        return raw, True

    try:
        _mutate_lead(st, approval.state_key, _record)
    except Exception as exc:  # noqa: BLE001 - the push below still says what happened
        logger.error("could not record the undone Book as asked on %s: %s", approval.state_key, exc)
    other = box.get("other")
    other_label = ("appointment %s for %s" % (other.get("appointment_id"), _slot_label(other.get("slot")))
                   if other else None)
    status = out.get("status")
    card_now = _UNDONE_CARD_NOW.get(str(status), "it is now %s" % status)
    message = ("Book as asked for %s was not applied: card %s moved while the call for %s was being booked (%s)."
               % (approval.lead_email, approval_id, slot_label, card_now))
    skipped = cancelled.get("reset_skipped") if isinstance(cancelled.get("reset_skipped"), dict) else None
    said_no = _row_said_no(_lead_row_or_none(st, approval.state_key))
    if done:
        shadow = "" if settings.is_live() else " (shadow: recorded as would_do)"
        if skipped is None:
            message += (" The engine cancelled that call again in GHL without notifying the lead%s, gave its time "
                        "back to the pool, and set the opportunity back to New Reply and Instantly interest to 1."
                        % shadow)
            if other:
                message += (" The lead's row now holds another call (%s), booked while this one was being booked, "
                            "and setting the opportunity and interest back may have undone what that call set: "
                            "check that the opportunity is at Call Booked and the Instantly interest at Meeting "
                            "Booked." % other_label)
        else:
            message += (" The engine cancelled that call again in GHL without notifying the lead%s and gave its time "
                        "back to the pool. It left the opportunity and the Instantly interest as they are" % shadow)
            if skipped.get("reason") == "opt_out":
                message += ", because the lead has since %s." % _said_label(skipped.get("category"))
            elif skipped.get("reason") == "other_call":
                message += (", because the lead's row now holds another call (%s), booked while this one was being "
                            "booked." % (other_label or "appointment %s for %s" % (
                                skipped.get("appointment_id"), _slot_label(skipped.get("slot")))))
            else:
                message += (", because the lead's row could not be read to check for another call or an opt-out: "
                            "check the opportunity and the Instantly interest by hand.")
        out["error"] = "%s. The call booked for %s was cancelled again" % (out["error"], slot_label)
    elif other:
        message += (" That call could NOT be cancelled: GHL refused (%s). It is still on the calendar with its "
                    "reminders held, so the lead hears nothing, and the engine cannot retry the cancel: the lead's "
                    "row now holds another call (%s), booked while this one was being booked. Cancel appointment %s "
                    "in GHL by hand, without notifying the lead." % (error, other_label, made.get("appointment_id")))
        out["error"] = ("%s. The call booked for %s could not be cancelled (%s), and the lead's row now holds "
                        "another call, so it is not retried: cancel it in GHL by hand"
                        % (out["error"], slot_label, error))
        out["booked"] = made.get("slot")
    else:
        message += (" That call could NOT be cancelled: GHL refused (%s). It is still on the calendar; its reminders "
                    "stay held so the lead hears nothing, and the engine retries the cancel every few minutes."
                    % error)
        out["error"] = ("%s. The call booked for %s could not be cancelled (%s); it stays held and the cancel is "
                        "retried" % (out["error"], slot_label, error))
        out["booked"] = made.get("slot")
    if said_no and (skipped or {}).get("reason") != "opt_out":
        # A cancel GHL refused, or a no that landed after the reset was
        # decided: the push still says the lead said no.
        message += " The lead has since %s. %s" % (_said_label(said_no), opt_out_advice(said_no))
    elif said_no:
        message += " %s" % opt_out_advice(said_no)
    if made.get("rescheduled_from"):
        message += (" Booking it had also asked GHL to cancel the lead's earlier call (appointment %s), which is not "
                    "restored: check it in GHL, and rebook it with the lead if it should stand."
                    % made.get("rescheduled_from"))
    title = "Book as asked undone for %s" % approval.lead_email
    # No "I cancelled it" link while the row holds another call: it finishes
    # only the cancel-pending call the row records.
    alert = (_alert(title, message) if done or other
             else _alert_with_done_link(title, message, state, made.get("appointment_id"), ts))
    job_log.log_run("reply_engine.approval", "book_as_asked_undone",
                    {"lead": approval.lead_email, "approval": approval_id, "card_status": status,
                     "slot": made.get("slot"), "appointment_id": made.get("appointment_id"), "cancelled": done,
                     "cancel_error": error, "rescheduled_from": made.get("rescheduled_from"),
                     "other_call": other.get("appointment_id") if other else None,
                     **dict(({"reset_skipped": skipped.get("reason")} if skipped else {}),
                            **({"opt_out": said_no} if said_no else {}))})
    out["undone"] = {"slot": made.get("slot"), "appointment_id": made.get("appointment_id"), "cancelled": done,
                     "error": error}
    out["alert"] = alert
    return out


def flush_queued(instantly, store=None, now: Optional[datetime] = None, ghl=None) -> List[Dict[str, Any]]:
    """Send approvals queued outside the send window once it is open.

    Also the retry hook for failed GHL cancels (retry_failed_cancels): the
    poller calls this every five minutes, whatever the hour, and a silent
    cancel is not a send to the lead. Those results are logged, not returned,
    so the poller's ``flushed`` count still means replies sent.
    """
    st = _store(store)
    ts = _now(now)
    out = []
    try:
        retried = retry_failed_cancels(st, ghl, instantly, ts)
        if retried:
            job_log.log_run("reply_engine.approval", "booking_cancel_retries",
                            {"count": len(retried),
                             "cancelled": sum(1 for r in retried if booking_cancel_done(r)),
                             "still_failing": sum(1 for r in retried if r.get("cancel_failed"))})
    except Exception as exc:  # noqa: BLE001 - never block the queued sends
        logger.exception("cancel retries failed: %s", exc)
    # Every open card past its TTL is retired here (SAL-6), and every Keep /
    # Release push that was not delivered is re-sent. approved_queued cards
    # are not expired (EXPIRABLE_STATUSES): the loop below sends them.
    send_time = slots.is_send_time(ts)
    try:
        # Each expiry writes its own "expired" Job_Log row (_expire).
        expire_overdue(st, ts)
    except Exception as exc:  # noqa: BLE001 - never block the queued sends
        logger.exception("card expiry failed: %s", exc)
    # is_send_time: within_send_window is hour-only, so this used to fire at
    # 07:00 on a Saturday or Sunday for anything approved on Friday evening.
    if not send_time:
        return out
    for key in st.keys(APPROVAL_PREFIX):
        raw = st.get(key)
        if not raw or raw.get("status") != "approved_queued":
            continue
        try:
            approval = Approval.model_validate(raw)
        except Exception:  # noqa: BLE001
            continue
        try:
            if approval.send_after and slots.parse_iso(approval.send_after) > ts:
                continue
        except (ValueError, TypeError):
            pass
        # A queued card past its 48 h TTL is still sent: Lorenzo approved it,
        # and expiring it would drop that decision (re-review R1 item 2). The
        # weekend-outage case this check used to cover (times that passed
        # while it sat in the queue) is refused inside send_approved, which
        # moves the card to stale_slots, or releases a booked call whose time
        # has passed, and sends nothing.
        # One lead per iteration. An exception here used to escape flush_queued
        # entirely (poller.run_once logs it as 'flush failed: %s' and moves on),
        # so one Instantly 5xx left every other approved lead in the queue with
        # no send attempted and nothing saying so.
        try:
            sent = send_approved(approval, instantly, st, ts, ghl=ghl)
            if approval.approved_by == "template":
                # A card the template gate queued: pushed to Lorenzo when the
                # send leaves it for him (it was never pushed before).
                sent = _after_template_send(st, approval, dict(sent), ts)
            out.append(dict(sent, lead=approval.lead_email))
        except Exception as exc:  # noqa: BLE001
            logger.exception("flush_queued: send_approved raised for %s", approval.lead_email)
            job_log.log_run("reply_engine.approval", "flush_send_raised",
                            {"lead": approval.lead_email, "approval": approval.token.split(".")[0], "error": str(exc)})
            failed = {"ok": False, "status": raw.get("status"), "lead": approval.lead_email, "error": str(exc)}
            if approval.approved_by == "template":
                # Never pushed before: when the card is left for Lorenzo
                # (send_failed, or back at pending / blocked / stale_slots) it
                # is pushed now, once. Still at sending or approved_queued: its
                # send may be running or retries, and the stuck detector owns
                # it after the lease.
                try:
                    current = _approval_row(st, _approval_id(approval))
                    if current is not None:
                        failed["status"] = current.status
                        failed = dict(_after_template_send(st, current, dict(failed, reason="send_raised"), ts),
                                      lead=approval.lead_email)
                except Exception as exc2:  # noqa: BLE001 - the stuck detector still lists it
                    logger.exception("flush_queued: could not push the card of %s: %s", approval.lead_email, exc2)
            out.append(failed)
    return out


# ------------------------------------------------------- SLA escalation
# The Sales tier's headline promise is a reply inside 5 minutes. It was measured
# once a day (jobs/pipeline_sweep's 24 h REPLY_SLA_HOURS) and never enforced: a
# card Lorenzo did not action got the one push create_approval sent and then
# nothing at all for the next 23 hours, while the prospect who replied sat there.
REPLY_SLA_MINUTES = 5
# (minutes the card has sat unactioned INSIDE sending hours, ntfy priority).
# Rising, and the ladder repeats past its last rung rather than going quiet,
# because a chase that stops is the same silence in a different shape.
ESCALATION_LADDER = (
    (REPLY_SLA_MINUTES, "high"),
    (15, "high"),
    (30, "urgent"),
    (60, "urgent"),
)
ESCALATION_REPEAT_MINUTES = 60
# Eight pushes is roughly seven sending hours of chasing. After that the card is
# still pending, still on every sweep, and will expire on its own at TTL_HOURS;
# more pushes would only train him to swipe them away.
ESCALATION_MAX_PUSHES = 8
ESCALATION_CLAIM_PREFIX = "approval_escalation:"
# A corrupt created_at must not turn the day walk below into a long loop.
ESCALATION_MAX_DAYS = 14


def sending_minutes_between(start: datetime, end: datetime) -> float:
    """Minutes between two instants that fall inside the CT send window on a
    business day (shared.settings.SEND_WINDOW, 07:00-19:00, Mon-Fri).

    Wall clock is the wrong ruler here. A card raised at 18:58 on a Friday is
    two minutes into its SLA, not 62 hours: escalated on wall-clock age it would
    open Monday already at the top of the ladder, for minutes during which
    nobody could have answered it, and every ordinary overnight card would do
    the same thing every single morning.
    """
    try:
        first = slots.to_tz(slots.ensure_aware(start))
        last = slots.to_tz(slots.ensure_aware(end))
    except (ValueError, TypeError):
        return 0.0
    if last <= first:
        return 0.0
    total = 0.0
    day = first.date()
    for _ in range(ESCALATION_MAX_DAYS):
        if day > last.date():
            break
        open_at = _localise_at(day, settings.SEND_WINDOW[0])
        if slots.is_business_day(open_at):
            close_at = _localise_at(day, settings.SEND_WINDOW[1])
            lo = max(open_at, first)
            hi = min(close_at, last)
            if hi > lo:
                total += (hi - lo).total_seconds() / 60.0
        day = day + timedelta(days=1)
    return total


def escalation_step(waited_minutes: float) -> int:
    """Which rung a card that has waited this long is owed (0 = none yet)."""
    step = 0
    for index, (threshold, _priority) in enumerate(ESCALATION_LADDER):
        if waited_minutes >= threshold:
            step = index + 1
    if step == len(ESCALATION_LADDER) and ESCALATION_REPEAT_MINUTES > 0:
        over = waited_minutes - ESCALATION_LADDER[-1][0]
        step += int(over // ESCALATION_REPEAT_MINUTES)
    return min(step, ESCALATION_MAX_PUSHES)


def escalation_priority(step: int) -> str:
    if step <= 0:
        return "default"
    if step <= len(ESCALATION_LADDER):
        return ESCALATION_LADDER[step - 1][1]
    return ESCALATION_LADDER[-1][1]


def _escalation_card(approval: Approval, step: int, waited: float) -> Dict[str, Any]:
    """Title, body and buttons for one chase.

    The buttons stay in the ntfy Actions header and out of the body, exactly as
    create_approval does it: the body is mirrored into the Gmail copy, where a
    safe-link scanner would fetch every URL in it.
    """
    who = approval.lead_email
    title = "Still waiting on you (%d min): %s" % (int(waited), who)
    lines = [
        "%s replied and the draft has been sitting unapproved for %d minute(s) of sending time."
        % (who, int(waited)),
        "Reply target is %d minutes. This is chase %d of %d; nothing has been sent."
        % (REPLY_SLA_MINUTES, step, ESCALATION_MAX_PUSHES),
        "",
        "Subject: %s" % (approval.draft.subject or ""),
        "Slots held: %s" % (", ".join(approval.draft.offered_slots) or "none"),
    ]
    pushed = approval.notify_result if isinstance(approval.notify_result, dict) else {}
    if not (pushed.get("sent") or pushed.get("test") or pushed.get("shadow")):
        lines.append("")
        lines.append("The original card never left the process, so this may be the first you have seen of it.")
    actions = []  # type: List[Any]
    click = None
    try:
        urls = action_urls(approval.token)
        actions = [("Approve", urls["approve"]), ("Veto", urls["veto"]), ("Edit", urls["edit"])]
        click = urls["approve"]
    except Exception as exc:  # noqa: BLE001 - base_url() fails closed in live; a chase must still go out
        logger.warning("escalation card for %s carries no buttons: %s", who, exc)
        lines.append("")
        lines.append("BASE_URL is unset, so this chase carries no buttons. Open the card by hand.")
    card = {"title": title, "message": "\n".join(lines), "actions": actions, "click": click}
    if not _topic_protected():
        # The thread's subject often carries the lead's first name or company
        # ("Re: <name>, question"): on the public topic it goes to the email
        # leg only, the rule _public_card_push follows.
        card["email_message"] = card["message"]
        card["message"] = "\n".join(line for line in lines if not line.startswith("Subject: "))
    return card


def chase_generation(raw: Any) -> int:
    """How many times Keep has reopened this card (0 for a card never
    reopened)."""
    try:
        return int(reopen_record(raw).get("generation") or 0)
    except (TypeError, ValueError):
        return 0


def chase_started_at(approval: Approval) -> datetime:
    """When the card's current SLA clock started: its creation, or the Keep
    that last reopened it (re-review R1 item 6). Raises ValueError on an
    unreadable created_at, as slots.parse_iso does."""
    start = slots.parse_iso(approval.created_at)
    reopened = reopen_record(approval).get("at")
    if reopened:
        try:
            start = max(start, slots.parse_iso(reopened))
        except (ValueError, TypeError):
            pass
    return start


def escalation_claim_key(approval_id: str, step: int, generation: int = 0) -> str:
    """The set_if_absent key for one rung of one card's chase. A card Keep
    reopened chases under its own generation's keys: the first life's keys
    for rungs 1..8 would otherwise refuse every rung of the second."""
    if generation:
        return "%s%s:r%d:%d" % (ESCALATION_CLAIM_PREFIX, approval_id, generation, step)
    return "%s%s:%d" % (ESCALATION_CLAIM_PREFIX, approval_id, step)


def _record_escalation(st, key: str, step: int, ts: datetime, generation: Optional[int] = None) -> None:
    """Write the chase counter onto the card as it is stored NOW, and nothing
    else. The card was read before the push; Lorenzo may have approved or
    vetoed it since, and writing that copy back reverted ``sent`` to
    ``pending`` (SAL-5), which a later flush or tap could send again. Only
    ``escalations`` (never lowered) and ``last_escalated_at`` move; the status
    and every other field keep the stored value. With ``generation``, nothing
    is written once the stored card is a later life of it (Keep reopened it
    meanwhile and reset its count)."""

    def _bump(current):
        if not isinstance(current, dict):
            return current
        if generation is not None and chase_generation(current) != generation:
            return current
        out = dict(current)
        out["escalations"] = max(int(current.get("escalations") or 0), int(step))
        out["last_escalated_at"] = ts.isoformat()
        return out

    mutate = getattr(st, "mutate", None)
    if callable(mutate):
        try:
            mutate(key, _bump)
            return
        except NotImplementedError:
            pass
    current = st.get(key)
    if isinstance(current, dict):
        st.set(key, _bump(current))


def escalate_pending(store=None, now: Optional[datetime] = None, notify_fn=None) -> List[Dict[str, Any]]:
    """Chase every approval card Lorenzo has not actioned. Never sends anything.

    This function takes no Instantly client and calls nothing that does: it
    loads pending cards, pushes, and writes the chase counter back. The only
    outbound call is shared.notify.notify, which goes through
    settings.guard_write like every other write, so in MODE=shadow a chase is a
    would_do record and nothing leaves the process.

    Escalation stops on all four of the conditions that should stop it:
      * outside sending hours (07:00-19:00 CT, Mon-Fri) - nobody is on shift,
        and a card's waiting time does not accrue then either;
      * the card is no longer ``pending`` - approved, queued, vetoed, sending,
        sent, sent_manually or superseded all mean it was actioned;
      * the card has expired (TTL_HOURS) - _expire owns it from there;
      * ESCALATION_MAX_PUSHES chases have already gone out.
    """
    st = _store(store)
    ts = _now(now)
    out = []  # type: List[Dict[str, Any]]
    if not slots.is_send_time(ts):
        return out
    try:
        keys = st.keys(APPROVAL_PREFIX)
    except Exception as exc:  # noqa: BLE001 - a store hiccup must not fail the tick
        logger.warning("could not list approvals to escalate: %s", exc)
        return out
    fn = notify_fn or notify.notify
    for key in keys:
        raw = st.get(key)
        if not raw or raw.get("status") != "pending":
            continue
        try:
            approval = Approval.model_validate(raw)
        except Exception:  # noqa: BLE001
            continue
        if _expired(approval, ts):
            continue
        try:
            created = chase_started_at(approval)
        except (ValueError, TypeError):
            continue
        generation = chase_generation(raw)
        waited = sending_minutes_between(created, ts)
        step = escalation_step(waited)
        already = int(approval.escalations or 0)
        if step <= already:
            continue
        approval_id = key.split(":", 1)[-1]
        # Two overlapping */5 ticks must not both shout about the same rung.
        claim = getattr(st, "set_if_absent", None)
        if callable(claim):
            try:
                if not claim(escalation_claim_key(approval_id, step, generation), {"at": ts.isoformat()}):
                    continue
            except Exception as exc:  # noqa: BLE001
                logger.warning("escalation bookkeeping failed for %s: %s", approval_id, exc)
        # Re-read just before the push: a card approved or vetoed since the
        # listing above is not chased.
        fresh = st.get(key)
        if not isinstance(fresh, dict) or fresh.get("status") != "pending" or chase_generation(fresh) != generation:
            continue
        priority = escalation_priority(step)
        card = _escalation_card(approval, step, waited)
        result = None
        try:
            extra = {"email_message": card["email_message"]} if "email_message" in card else {}
            result = fn(card["title"], card["message"], priority=priority,
                        actions=card["actions"], tags=["warning", "reply-engine"], click=card["click"], **extra)
        except Exception as exc:  # noqa: BLE001 - the tick must not fail on a push
            logger.warning("escalation push failed for %s: %s", approval.lead_email, exc)
            result = {"sent": False, "errors": ["notify raised: %s" % exc]}
        approval.escalations = step
        approval.last_escalated_at = ts.isoformat()
        # Written back under the key it was READ from, not the one _save derives
        # from the token: if those two ever disagree the counter would be saved
        # somewhere nothing reads and this card would be chased forever.
        _record_escalation(st, key, step, ts, generation=generation)
        logger.warning("approval %s for %s escalated to step %d after %d sending minutes",
                       approval_id, approval.lead_email, step, int(waited))
        job_log.log_run("reply_engine.approval", "escalated",
                        {"lead": approval.lead_email, "approval": approval_id, "step": step,
                         "priority": priority, "waited_sending_minutes": int(waited),
                         "sla_minutes": REPLY_SLA_MINUTES})
        out.append({"approval": approval_id, "lead": approval.lead_email, "step": step,
                    "priority": priority, "waited_sending_minutes": waited,
                    # Only the safe fields: this list is written to the Job_Log
                    # (CSV and Sheet) by poller.run_once, and the raw result
                    # carries the signed Approve/Veto URLs, the ntfy headers
                    # and the topic.
                    "notified": stored_notify_result(result)})
    return out


def auto_send_minutes() -> int:
    try:
        return int(os.environ.get("AUTO_SEND_AFTER_MINUTES", "0") or 0)
    except ValueError:
        return 0


def auto_send_due(instantly, store=None, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Disabled by default (AUTO_SEND_AFTER_MINUTES=0). Live-only, positive_interested only.

    CT3 does not use this or auto_send_minutes: the template auto-send is
    auto_send_approved, called by the reply pipeline for a draft the
    template gate allows. This timer path stays unwired (Q-E3).

    NOT wired into the scheduled poller tick any more. CLAUDE.md is explicit
    that the first reply to a positive is drafted for approval and never
    auto-sent, and one environment variable on a */5 schedule was one
    copy-paste away from contradicting it (.env already carries a look-alike
    AUTO_APPROVE_AFTER_MINUTES from the old system). This function stays so a
    deliberate operator run is possible, and it now refuses any card whose push
    did not actually reach Lorenzo: a card he never saw is not a card he
    declined to answer.
    """
    minutes = auto_send_minutes()
    if minutes <= 0 or not settings.is_live():
        return []
    st = _store(store)
    ts = _now(now)
    out = []
    for key in st.keys(APPROVAL_PREFIX):
        raw = st.get(key)
        if not raw or raw.get("status") != "pending" or raw.get("label") != "positive_interested":
            continue
        try:
            approval = Approval.model_validate(raw)
            created = slots.parse_iso(approval.created_at)
        except Exception:  # noqa: BLE001
            continue
        if created + timedelta(minutes=minutes) > ts or _expired(approval, ts) or approval.draft.problems:
            continue
        # Lorenzo's rule (FIRST_REPLY_LOCK_REASON): a first reply is never
        # auto-sent, by its template id or, for any other body, by the lead
        # row (no reply of ours sent yet, or no row at all).
        if draft_only(approval.draft.template_id, _stored_row(st, approval.state_key)):
            job_log.log_run("reply_engine.approval", "auto_send_refused_first_reply",
                            {"lead": approval.lead_email, "approval": key.split(":", 1)[-1],
                             "reason": FIRST_REPLY_LOCK_REASON})
            continue
        pushed = approval.notify_result if isinstance(approval.notify_result, dict) else {}
        if not (pushed.get("sent") and pushed.get("actionable", True)):
            logger.error("refusing to auto-send %s: the card never reached Lorenzo (%s)",
                         key, pushed.get("errors") or pushed.get("channels"))
            job_log.log_run("reply_engine.approval", "auto_send_refused_unpushed",
                            {"lead": approval.lead_email, "approval": key.split(":", 1)[-1]})
            continue
        logger.error("AUTO-SENDING %s to %s with no human in the loop (AUTO_SEND_AFTER_MINUTES=%d)",
                     key, approval.lead_email, minutes)
        job_log.log_run("reply_engine.approval", "auto_send",
                        {"lead": approval.lead_email, "approval": key.split(":", 1)[-1], "after_minutes": minutes,
                         "label": approval.label})
        result = approve(approval.token, instantly, st, ts)
        try:
            notify.notify("Auto-sent without approval: %s" % approval.lead_email,
                          "AUTO_SEND_AFTER_MINUTES=%d fired for %s. Status: %s."
                          % (minutes, approval.lead_email, result.get("status")),
                          priority="high", tags=["warning", "reply-engine"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("auto-send notice failed: %s", exc)
        out.append(dict(result, lead=approval.lead_email, auto=True))
    return out
