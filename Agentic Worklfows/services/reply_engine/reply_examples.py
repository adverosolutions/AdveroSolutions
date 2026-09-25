"""Lorenzo's own replies, kept as examples (2026-09-25).

Lorenzo: "we'll add context every time I reply to a new one." The engine
keeps one example per reply of his it captures: what the lead wrote, what he
answered, how the engine classified the lead's message, the campaign and
offer, the thread and the lead. A future decide() step puts the most recent
ones into its prompt (runbooks/reply_examples.md).

What is captured, exactly (not every reply he sends):
  * his FIRST hand-sent reply per lead, found by the hourly cadence tick's
    thread check (cadence.detect_manual_first_reply -> capture_first_reply),
    and only when that check records it on the lead row (day 0, armed or
    not; not on a dry run, at most 10 thread reads a tick): the lead has a card of
    status pending, blocked, stale_slots or expired as its newest card, no
    reply of ours recorded, an unarmed ladder, a thread id and inbox, an
    inbound within the last 14 days (the card's reply too), and the lead's
    ladder is not over (booked, opted out, lost...). The reply must be a
    manual row with ue_type 3 in the lead's thread, sent after the reply the
    card answers. His later replies in the same thread are not captured.
  * whatever jobs/seed_reply_examples.py finds when Lorenzo runs it: his
    replies since the poller's start date that answer a lead message, read
    with GET /emails (dry run by default, --write to record).

Where they live: the engine store (shared.store), one key per example,
``reply_example:<his Instantly email id>``, written with set_if_absent, so the
same email is never recorded twice (the tick and the seed may both see it).
On Modal that is the Dict of the mode, which deletes an entry after 7 days
with no read or write: the hourly cadence tick reads every example
(keep_alive), so they last as long as the tick runs. At cutover they are
copied from the shadow Dict to the live one (copy_all, via the seed job).

What they never do: decide what auto-sends. Examples may shape a draft
(decide(), later); auto-send still needs an exact approved-template match
(template_gate). No module of the send or auto-send path reads them
(test_reply_examples.py pins it). recent() is the whole read API.
"""
import inspect
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from shared import settings, slots

logger = logging.getLogger("reply_engine.reply_examples")

PREFIX = "reply_example:"
# Each text is capped, quoted history cut (approval.lead_reply_excerpt): a
# prompt needs the words, not the thread below them.
SOURCES = ("thread", "seed")


def key_for(email_id: Any) -> str:
    return PREFIX + str(email_id)


def _text(value: Any) -> Optional[str]:
    """The top of an email body: quoted history cut, capped (the card's own
    rule, approval.lead_reply_excerpt). None when there is no text."""
    from services.reply_engine.approval import lead_reply_excerpt

    return lead_reply_excerpt(value)


def row_text(row: Dict[str, Any]) -> str:
    """The body of a GET /emails row: ``text`` (recorded fixtures), live
    ``body.text``, else ``content_preview`` (pipeline_sweep.email_text)."""
    from jobs.pipeline_sweep import email_text

    return email_text(row or {})


def _takes_retry(getter: Any) -> bool:
    """True when ``getter`` accepts ``retry=`` (shared.instantly.Instantly.get_email
    does; a test fake taking only the id does not, and is called without it)."""
    try:
        params = inspect.signature(getter).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(p.name == "retry" or p.kind == inspect.Parameter.VAR_KEYWORD for p in params)


def read_text(instantly: Any, row: Optional[Dict[str, Any]], single_try: bool = False) -> Tuple[str, Optional[str]]:
    """``(text, read)``: the row's body, else the body of GET /emails/{id}
    (one read-only call). ``read`` says what that call did: None when none
    was made (the row had text, no id, no client), "ok" when it answered
    (with or without text), "failed" when it raised. ``single_try`` asks the
    client for one attempt, no retries (the hourly tick: a failing read can
    take minutes of backoff). Never raises."""
    text = row_text(row or {})
    if str(text or "").strip():
        return text, None
    eid = (row or {}).get("id")
    getter = getattr(instantly, "get_email", None)
    if not eid or not callable(getter):
        return "", None
    try:
        if single_try and _takes_retry(getter):
            full = getter(str(eid), retry=False)
        else:
            full = getter(str(eid))
    except Exception as exc:  # noqa: BLE001 - a failed read is reported, never raised
        logger.warning("could not read email %s for its text: %s", eid, exc)
        return "", "failed"
    return (row_text(full) if isinstance(full, dict) else ""), "ok"


def fetch_text(instantly: Any, row: Optional[Dict[str, Any]], single_try: bool = False) -> str:
    """The row's body, else the body of GET /emails/{id} (one read-only call):
    a list page can carry an outbound row without its text (the recorded
    September manual list has an empty ``text`` on every row we sent). ""
    when neither has any, or the read failed (read_text tells the two apart);
    never raises."""
    return read_text(instantly, row, single_try=single_try)[0]


def _iso(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    try:
        return slots.to_tz(slots.parse_iso(value if isinstance(value, datetime) else str(value))).isoformat()
    except (ValueError, TypeError):
        return None


def build(email_id: Any, sent_at: Any, reply_text: Any, lead_email: Any, thread_id: Any = None,
          campaign_id: Any = None, lead_message: Any = None, lead_message_id: Any = None,
          lead_message_at: Any = None, category: Any = None, subject: Any = None, eaccount: Any = None,
          source: str = "thread", now: Optional[datetime] = None) -> Dict[str, Any]:
    """One example record. Raises ValueError when there is no email id or no
    reply text: an example without his words teaches nothing."""
    if not email_id:
        raise ValueError("an example needs his email's id (the dedupe key)")
    reply = _text(reply_text)
    if not reply:
        raise ValueError("an example needs the text of his reply")
    if source not in SOURCES:
        raise ValueError("source must be one of %s" % (SOURCES,))
    camp = settings.CAMPAIGN_BY_ID.get(str(campaign_id or ""), {}) if campaign_id else {}
    return {
        "email_id": str(email_id),
        "date": _iso(sent_at),
        "lead_email": str(lead_email or "").strip().lower() or None,
        "thread_id": str(thread_id) if thread_id else None,
        "campaign_id": str(campaign_id) if campaign_id else None,
        "campaign_key": camp.get("key"),
        "offer": camp.get("offer"),
        "niche": camp.get("niche"),
        "category": str(category) if category else None,
        "lead_message": _text(lead_message),
        "lead_message_id": str(lead_message_id) if lead_message_id else None,
        "lead_message_at": _iso(lead_message_at),
        "reply": reply,
        "subject": str(subject) if subject else None,
        "eaccount": str(eaccount).strip().lower() if eaccount else None,
        "sent_by": "lorenzo",
        "source": source,
        "recorded_at": slots.to_tz(now or datetime.now(slots.TZ)).isoformat(),
    }


def exists(store, email_id: Any) -> bool:
    return store.get(key_for(email_id)) is not None


def record(store, example: Dict[str, Any]) -> bool:
    """Keep ``example`` (from build()). True when it was new, False when an
    example for the same email id is already stored (dedupe: set_if_absent,
    atomic against another worker)."""
    return bool(store.set_if_absent(key_for(example["email_id"]), dict(example)))


def all_examples(store) -> List[Dict[str, Any]]:
    out = []  # type: List[Dict[str, Any]]
    for key in store.keys(PREFIX):
        raw = store.get(key)
        if isinstance(raw, dict):
            out.append(raw)
    return out


def recent(category: Optional[str] = None, n: int = 5, store=None) -> List[Dict[str, Any]]:
    """The ``n`` newest examples (by the date he sent the reply), newest
    first; only ``category`` when given (a reply category, e.g.
    "positive_interested"). ``store`` defaults to the engine store
    (shared.store.get_store). Read only."""
    if store is None:
        from shared.store import get_store

        store = get_store()
    rows = all_examples(store)
    if category:
        rows = [r for r in rows if r.get("category") == category]
    rows.sort(key=lambda r: (str(r.get("date") or ""), str(r.get("email_id") or "")), reverse=True)
    return rows[:max(0, int(n))]


def _category_for(state: Any, card: Any) -> Optional[str]:
    """How the engine classified the lead's message the card answers: its
    history ``inbound`` entry's label, else the card's own label."""
    email_id = str(getattr(card, "email_id", None) or "")
    for entry in list(getattr(state, "history", None) or []):
        if (isinstance(entry, dict) and entry.get("event") == "inbound"
                and str(entry.get("email_id") or "") == email_id and entry.get("label")):
            return str(entry["label"])
    label = getattr(card, "label", None) or getattr(getattr(card, "draft", None), "label", None)
    return str(label) if label else None


def _our_addresses(state: Any) -> set:
    """Every address a row of ours is sent from: the active inboxes
    (config/ids.json), Lorenzo's own, and the lead's inbox (``eaccount``)."""
    from services.reply_engine.poller import own_inboxes

    ours = set(str(a).strip().lower() for a in own_inboxes() if a)
    inbox = str(getattr(state, "eaccount", None) or "").strip().lower()
    if inbox:
        ours.add(inbox)
    return ours


def _from_the_lead(row: Dict[str, Any], ours: set) -> bool:
    """A GET /emails row the lead sent, on positive evidence only: ``ue_type``
    2 (Instantly's own direction flag, pipeline_sweep.UE_TYPE_INBOUND) from
    an address not ours; with no ``ue_type``, a sender that is not ours; with
    neither, a recipient that is ours (the recorded September list's shape).
    Any other ``ue_type`` (3 ours by hand, 1 or 4 a campaign step or a
    scheduled send) is never the lead's."""
    from jobs.pipeline_sweep import UE_TYPE_INBOUND

    sender = str(row.get("from_address_email") or "").strip().lower()
    ue_type = row.get("ue_type")
    if ue_type not in (None, ""):
        try:
            return int(ue_type) == UE_TYPE_INBOUND and sender not in ours
        except (TypeError, ValueError):
            return False
    if sender:
        return sender not in ours
    to_field = str(row.get("to_address_email_list") or "")
    recipients = [x.strip().lower() for x in to_field.replace(";", ",").split(",") if x.strip()]
    return any(r in ours for r in recipients)


def lead_row_in(state: Any, card: Any, found: Dict[str, Any], rows: Any) -> Optional[Dict[str, Any]]:
    """The lead's message Lorenzo answered, among the thread rows the tick
    already read (no new read): the row whose id is the card's ``email_id``
    when it is the lead's, else the newest row of the lead's in the lead's
    ``thread_id`` sent before his reply (``found["sent_at"]``) that is not an
    auto-reply (pipeline_sweep.is_auto_reply). None when the rows hold none
    (the manual list may not carry the lead's rows at all)."""
    from jobs.pipeline_sweep import is_auto_reply, parse_ts

    rows = [r for r in list(rows or []) if isinstance(r, dict)]
    if not rows:
        return None
    ours = _our_addresses(state)
    card_id = str(getattr(card, "email_id", None) or "")
    if card_id:
        for r in rows:
            if str(r.get("id") or "") == card_id and _from_the_lead(r, ours):
                return r
    thread = str(getattr(state, "thread_id", None) or "")
    his_at = parse_ts((found or {}).get("sent_at"))
    if not thread or his_at is None:
        return None
    best = None  # type: Optional[Tuple[datetime, Dict[str, Any]]]
    for r in rows:
        if str(r.get("thread_id") or "") != thread or not _from_the_lead(r, ours) or is_auto_reply(r):
            continue
        at = parse_ts(r.get("timestamp_created") or r.get("timestamp_email"))
        if at is None or at >= his_at:
            continue
        if best is None or at > best[0]:
            best = (at, r)
    return best[1] if best else None


def capture_first_reply(store, state: Any, card: Any, found: Dict[str, Any], row: Optional[Dict[str, Any]],
                        context: Optional[Dict[str, Any]] = None, now: Optional[datetime] = None,
                        instantly: Any = None, thread_rows: Any = None) -> Dict[str, Any]:
    """Keep Lorenzo's first reply, found in the thread by
    cadence.detect_manual_first_reply after it recorded that reply on the
    lead. ``found`` is manual_first_reply_in's {"email_id", "sent_at"},
    ``row`` the GET /emails row it came from (his text; when the row has
    none, one GET /emails/{id} through ``instantly``, a single try), ``card``
    the card whose lead message he answered (its ``lead_reply``, ``label``
    and ``email_id``). A card with no ``lead_reply`` (older cards) takes the
    lead's message from ``thread_rows``, the rows the tick already read
    (lead_row_in; no new read). An email id already kept costs no read.
    Never raises: returns {"example": "recorded" | "duplicate" | "skipped" |
    "failed", "read": None | "ok" | "failed", ...}; ``read`` is what the GET
    /emails/{id} did (read_text), and a failed one is "skipped" with reason
    ``read_failed``."""
    read = None  # type: Optional[str]
    try:
        email_id = (found or {}).get("email_id")
        if not email_id:
            return {"example": "skipped", "reason": "no_email_id", "read": read}
        if exists(store, email_id):
            return {"example": "duplicate", "email_id": str(email_id), "read": read}
        text, read = read_text(instantly, dict(row or {}, id=(row or {}).get("id") or email_id), single_try=True)
        if read == "failed":
            return {"example": "skipped", "reason": "read_failed", "email_id": str(email_id), "read": read}
        if not str(text or "").strip():
            return {"example": "skipped", "reason": "no_reply_text", "email_id": str(email_id), "read": read}
        lead_message = getattr(card, "lead_reply", None)
        lead_message_id = getattr(card, "email_id", None)
        lead_message_at = (context or {}).get("reply_at")
        if not str(lead_message or "").strip():
            lead_row = lead_row_in(state, card, found, thread_rows)
            if lead_row is not None:
                from jobs.pipeline_sweep import parse_ts

                lead_message = row_text(lead_row)
                lead_message_id = lead_message_id or lead_row.get("id")
                lead_message_at = lead_message_at or parse_ts(
                    lead_row.get("timestamp_created") or lead_row.get("timestamp_email"))
        example = build(
            email_id=email_id, sent_at=(found or {}).get("sent_at"), reply_text=text,
            lead_email=getattr(state, "lead_email", None), thread_id=getattr(state, "thread_id", None),
            campaign_id=getattr(state, "campaign_id", None) or getattr(card, "campaign_id", None),
            lead_message=lead_message, lead_message_id=lead_message_id,
            lead_message_at=lead_message_at, category=_category_for(state, card),
            subject=(row or {}).get("subject"), eaccount=getattr(state, "eaccount", None),
            source="thread", now=now)
        new = record(store, example)
        return {"example": "recorded" if new else "duplicate", "email_id": str(email_id), "read": read}
    except Exception as exc:  # noqa: BLE001 - an example is context; it must never cost the tick its work
        logger.warning("could not keep the reply example for %s: %s", getattr(state, "lead_email", None), exc)
        return {"example": "failed", "error": str(exc)[:200], "read": read}


def keep_alive(store) -> int:
    """Read every example once, so Modal's 7-day idle expiry never deletes
    one (the hourly cadence tick calls this, as it reads every lead record).
    Returns how many were read; -1 when the store could not be listed.
    Never raises."""
    try:
        keys = store.keys(PREFIX)
    except Exception as exc:  # noqa: BLE001 - the tick must not fail on context
        logger.warning("could not list the reply examples: %s", exc)
        return -1
    read = 0
    for key in keys:
        try:
            store.get(key)
            read += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not read %s: %s", key, exc)
    return read


def copy_all(src, dst, write: bool = False) -> Dict[str, Any]:
    """Copy every example from ``src`` to ``dst`` (set_if_absent: an example
    already in ``dst`` is left as it is). ``write=False`` only counts."""
    copied, present = [], []  # type: List[str], List[str]
    for key in sorted(src.keys(PREFIX)):
        raw = src.get(key)
        if not isinstance(raw, dict):
            continue
        if dst.get(key) is not None:
            present.append(key)
        elif not write:
            copied.append(key)
        elif dst.set_if_absent(key, raw):
            copied.append(key)
        else:
            present.append(key)
    return {"copied": copied, "present": present, "write": write}
