"""Lorenzo's own replies, kept as examples (2026-09-25).

Lorenzo: "we'll add context every time I reply to a new one." Every time the
engine sees a reply he sent himself from an Instantly thread, it keeps one
example: what the lead wrote, what he answered, how the engine classified the
lead's message, the campaign and offer, the thread and the lead. A future
decide() step puts the most recent ones into its prompt (runbooks/reply_examples.md).

Where they come from:
  * cadence.detect_manual_first_reply, on the hourly cadence tick: his first
    reply to a lead, found in the thread and recorded as day 0
    (capture_first_reply). Only a reply found there is his: the check runs
    only for a lead with no reply of the engine's recorded, and only takes a
    manual row with ue_type 3 (sent by hand from the inbox).
  * jobs/seed_reply_examples.py, once: his replies since the poller's start
    date, read with GET /emails (dry run by default, --write to record).

Where they live: the engine store (shared.store), one key per example,
``reply_example:<his Instantly email id>``, written with set_if_absent, so the
same email is never recorded twice (the tick and the seed may both see it).
The store is the Modal Dict on Modal and .tmp/store.json on the laptop.

What they never do: change what is sent. Nothing in the send path reads
them; the only text that auto-sends is still an approved template
(template_gate, approve_templates.py). They are context for a prompt, and
recent() is the whole read API.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

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


def fetch_text(instantly: Any, row: Optional[Dict[str, Any]]) -> str:
    """The row's body, else the body of GET /emails/{id} (one read-only call):
    a list page can carry an outbound row without its text (the recorded
    September manual list has an empty ``text`` on every row we sent). ""
    when neither has any; never raises."""
    text = row_text(row or {})
    if str(text or "").strip():
        return text
    eid = (row or {}).get("id")
    getter = getattr(instantly, "get_email", None)
    if not eid or not callable(getter):
        return ""
    try:
        full = getter(str(eid))
    except Exception as exc:  # noqa: BLE001 - no text is "skipped", not a failure of the caller
        logger.warning("could not read email %s for its text: %s", eid, exc)
        return ""
    return row_text(full) if isinstance(full, dict) else ""


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


def capture_first_reply(store, state: Any, card: Any, found: Dict[str, Any], row: Optional[Dict[str, Any]],
                        context: Optional[Dict[str, Any]] = None, now: Optional[datetime] = None,
                        instantly: Any = None) -> Dict[str, Any]:
    """Keep Lorenzo's first reply, found in the thread by
    cadence.detect_manual_first_reply after it recorded that reply on the
    lead. ``found`` is manual_first_reply_in's {"email_id", "sent_at"},
    ``row`` the GET /emails row it came from (his text; when the row has
    none, one GET /emails/{id} through ``instantly``), ``card`` the card
    whose lead message he answered (its ``lead_reply``, ``label`` and
    ``email_id``). An email id already kept costs no read. Never raises:
    returns {"example": "recorded" | "duplicate" | "skipped" | "failed", ...}."""
    try:
        email_id = (found or {}).get("email_id")
        if not email_id:
            return {"example": "skipped", "reason": "no_email_id"}
        if exists(store, email_id):
            return {"example": "duplicate", "email_id": str(email_id)}
        text = fetch_text(instantly, dict(row or {}, id=(row or {}).get("id") or email_id))
        if not str(text or "").strip():
            return {"example": "skipped", "reason": "no_reply_text"}
        example = build(
            email_id=email_id, sent_at=(found or {}).get("sent_at"), reply_text=text,
            lead_email=getattr(state, "lead_email", None), thread_id=getattr(state, "thread_id", None),
            campaign_id=getattr(state, "campaign_id", None) or getattr(card, "campaign_id", None),
            lead_message=getattr(card, "lead_reply", None), lead_message_id=getattr(card, "email_id", None),
            lead_message_at=(context or {}).get("reply_at"), category=_category_for(state, card),
            subject=(row or {}).get("subject"), eaccount=getattr(state, "eaccount", None),
            source="thread", now=now)
        new = record(store, example)
        return {"example": "recorded" if new else "duplicate", "email_id": str(email_id)}
    except Exception as exc:  # noqa: BLE001 - an example is context; it must never cost the tick its work
        logger.warning("could not keep the reply example for %s: %s", getattr(state, "lead_email", None), exc)
        return {"example": "failed", "error": str(exc)[:200]}
