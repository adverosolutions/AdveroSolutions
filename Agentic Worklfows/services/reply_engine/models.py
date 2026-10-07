"""Pydantic v2 models for the reply engine (Python 3.9 compatible)."""
import hashlib
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pytz
from pydantic import BaseModel, Field, field_validator

from shared import settings, slots

# ---------------------------------------------------------------- taxonomy
LABELS = (
    "positive_interested",
    "positive_question",
    "positive_referral",
    "neutral_question",
    "negative_notnow",
    "negative_notfit",
    "negative_hostile",
    "unsubscribe",
    "ooo",
    "wrong_person",
    "auto_reply_unmonitored",
)
POSITIVE_LABELS = ("positive_interested", "positive_question", "positive_referral")
# Labels that get a drafted answer. It goes to Lorenzo as an approval card,
# unless it is exactly a template he approved with jobs/approve_templates.py
# and unchanged since, the template kill switch is off and every send check
# passes (CT3, services/reply_engine/template_gate.py): then it is sent
# automatically. neutral_question is always a card.
DRAFT_LABELS = POSITIVE_LABELS + ("neutral_question",)
# Labels the rule layer must decide without an LLM call.
RULE_ONLY_LABELS = ("unsubscribe", "negative_hostile", "ooo", "auto_reply_unmonitored")
BLOCKLIST_LABELS = ("negative_hostile", "unsubscribe")
# booking_link: a yes plus an ask for a Calendly or booking link (the AI agents
# offer answers it with its booking_link reply, 2026-10-06).
QUESTION_TYPES = ("pricing", "mechanism", "send_info", "other", "booking_link")

# Instantly interest values (config/ids.json interest_status_codes)
INTEREST_FOR_LABEL = {
    "positive_interested": 1,
    "positive_question": 1,
    "positive_referral": 1,
    "neutral_question": None,
    "negative_notnow": -1,
    "negative_notfit": -1,
    "negative_hostile": -1,
    "unsubscribe": -1,
    "ooo": 0,
    "wrong_person": -2,
    "auto_reply_unmonitored": None,
}  # type: Dict[str, Optional[int]]

# GHL Sales pipeline stage key (resolved to an id via settings.GHL_STAGES)
STAGE_FOR_LABEL = {
    "positive_interested": "new_reply",
    "positive_question": "new_reply",
    "positive_referral": "new_reply",
    "neutral_question": "new_reply",
    "negative_notnow": "follow_up_later",
    "negative_notfit": "lost",
    "negative_hostile": "lost",
    "unsubscribe": "lost",
    "wrong_person": "lost",
    "ooo": None,
    "auto_reply_unmonitored": None,
}  # type: Dict[str, Optional[str]]


def _first(d: Dict[str, Any], *keys, default=None):
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return default


def _campaign_meta(campaign_id: Optional[str]) -> Dict[str, Any]:
    return settings.CAMPAIGN_BY_ID.get(campaign_id or "", {})


_SUBJECT_NAME_RE = re.compile(r"^\s*(?:(?:re|fw|fwd|ext|aw)\s*:\s*)*([A-Z][a-zA-Z'\-]+),\s", re.I)


def _first_name_from_subject(subject: Optional[str]) -> Optional[str]:
    """Cold-email subjects are '<First>, question'; recover the first name from a reply subject."""
    m = _SUBJECT_NAME_RE.match(subject or "")
    if not m:
        return None
    name = m.group(1)
    if name.lower() in ("automatic", "auto", "out", "thank", "this", "re", "fw", "fwd"):
        return None
    return name[:1].upper() + name[1:]


_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"(?i)<\s*(br|/p|/div|/tr)\s*/?>")
_WS_RE = re.compile(r"\s+")


def html_to_text(html: Optional[str]) -> str:
    """Crude HTML -> text for the rare Instantly row that carries body.html only."""
    if not html:
        return ""
    import html as html_mod

    text = _BR_RE.sub("\n", str(html))
    text = _TAG_RE.sub(" ", text)
    text = html_mod.unescape(text)
    lines = [ln.strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln).strip()


def reply_body_text(item: Dict[str, Any]) -> str:
    """The lead's reply body out of one live GET /emails row.

    The live API nests the full body under ``body.text`` (with ``body.html``
    beside it) and carries ``content_preview``, a ~60 character truncation.
    Reading content_preview first threw away everything past the first line -
    times, phone numbers, "remove me", the actual question - so it is only ever
    the last resort. ``text`` / ``body_text`` keep the flattened shapes some
    fixtures and webhook payloads use.
    """
    body = item.get("body")
    if isinstance(body, dict):
        text = body.get("text")
        if isinstance(text, str) and text.strip():
            return text
        converted = html_to_text(body.get("html"))
        if converted:
            return converted
    elif isinstance(body, str) and body.strip():
        return body
    return _first(item, "text", "body_text", "content_preview", default="") or ""


CONTENT_KEY_PREFIX = "c:"
SYNTHETIC_ID_PREFIX = "wh:"


def is_content_key(key: str) -> bool:
    """True for a content fingerprint, as opposed to a provider/message id.

    A fingerprint is deliberately time-independent so the same reply matches
    across ingestion paths, which also means a genuinely repeated body ("Any
    update on this?", "Sounds good") collapses onto the key of the first one.
    app.process_event therefore honours a fingerprint match only inside
    DEDUPE_WINDOW_HOURS; provider ids and message ids stay permanent.
    """
    return str(key or "").startswith(CONTENT_KEY_PREFIX)


def is_synthetic_email_id(email_id: Optional[str]) -> bool:
    """'wh:<email>:<ts>' - a webhook payload that carried no email id at all.

    It is an idempotency key, never a thread handle: passing it to
    instantly.reply_to_email as reply_to_uuid is a guaranteed 4xx.
    """
    return str(email_id or "").startswith(SYNTHETIC_ID_PREFIX)


def content_fingerprint(lead_email: str, thread_id: Optional[str], text: str) -> Optional[str]:
    """Stable identity for one reply, independent of which ingestion path saw it.

    The provider email id is not enough: the same reply arriving as an id-less
    webhook ('wh:<email>:<ts>') and again from the poller with Instantly's real
    id would otherwise be processed twice.

    No time component on purpose: the webhook's delivery timestamp and the
    poller's timestamp_created are not always the same value, and bucketing
    would split the two views of one reply across a bucket boundary. The
    freshness window lives in app.process_event instead.
    """
    normalised = _WS_RE.sub(" ", (text or "")).strip().lower()
    if len(normalised) < 8:
        return None
    basis = "|".join([(lead_email or "").strip().lower(), (thread_id or "").strip(), normalised[:400]])
    return "%s%s" % (CONTENT_KEY_PREFIX, hashlib.sha1(basis.encode("utf-8")).hexdigest()[:24])


def _split_name(name: Optional[str]):
    if not name:
        return None, None
    parts = str(name).strip().split()
    if not parts:
        return None, None
    return parts[0], (" ".join(parts[1:]) or None)


# ------------------------------------------------- when the lead sent a reply
# Where a reply's received time came from, on ReplyEvent.received_at_source and
# on the inbound history entry ("received_at_source"):
#   "email"      the email's own time as Instantly reports it (the poller's
#                timestamp_created, else timestamp_email; a webhook's timestamp).
#   "processing" the payload carried no time, so the time is only when the
#                engine saw the reply. That is an upper bound, never proof that
#                the lead sent it after anything else.
RECEIVED_AT_EMAIL = "email"
RECEIVED_AT_PROCESSING = "processing"


def iso_utc(dt: datetime) -> str:
    """An aware instant as ISO 8601 in UTC (the inbound entry's received_at)."""
    return slots.ensure_aware(dt).astimezone(pytz.utc).isoformat()


def parse_time(value: Any) -> Optional[datetime]:
    """A stored ISO time as an aware datetime, or None when it cannot be read."""
    if value in (None, ""):
        return None
    try:
        return slots.parse_iso(value)
    except (ValueError, TypeError, OverflowError):
        return None


def reply_received_at(event: Any, processed_at: datetime) -> Tuple[datetime, str]:
    """When the lead sent ``event``, and where that time came from.

    The email's own time (ReplyEvent.received_at) when the payload carried one;
    otherwise ``processed_at``, with source "processing" (the contract's
    fallback: the inbound entry then records its processing time)."""
    received = getattr(event, "received_at", None)
    source = getattr(event, "received_at_source", None) or RECEIVED_AT_EMAIL
    if received is None or source == RECEIVED_AT_PROCESSING:
        return slots.ensure_aware(processed_at), RECEIVED_AT_PROCESSING
    return slots.ensure_aware(received), RECEIVED_AT_EMAIL


def entry_received_at(entry: Any) -> Optional[datetime]:
    """When the lead sent the reply an inbound history entry records: its
    ``received_at``; an entry written before that field existed falls back to
    ``at`` (when the engine processed it)."""
    if not isinstance(entry, dict):
        return None
    return parse_time(entry.get("received_at")) or parse_time(entry.get("at"))


def entry_email_time(entry: Any) -> Optional[datetime]:
    """The entry's received_at only when it is the email's own time: None for
    an entry with no received_at (written before it existed, so only ``at``,
    an upper bound) and for a processing-time stand-in. Only this can prove
    that one reply was sent after another."""
    if not isinstance(entry, dict) or not entry.get("received_at"):
        return None
    if str(entry.get("received_at_source") or RECEIVED_AT_EMAIL) == RECEIVED_AT_PROCESSING:
        return None
    return parse_time(entry.get("received_at"))


def opt_out_marker(state_or_row: Any) -> Optional[Dict[str, Any]]:
    """The lead's sticky opt-out marker (LeadState.opt_out, or a stored row's
    "opt_out"), or None. A malformed value is kept as a marker (it holds)."""
    if isinstance(state_or_row, dict):
        marker = state_or_row.get("opt_out")
    else:
        marker = getattr(state_or_row, "opt_out", None)
    if not marker:
        return None
    return marker if isinstance(marker, dict) else {"malformed": str(marker)}


def opt_out_received_at(marker: Any) -> Optional[datetime]:
    """When the lead sent the opt-out a marker records, or None (unreadable)."""
    return parse_time(marker.get("received_at")) if isinstance(marker, dict) else None


# ------------------------------------------------------------------ models
class ReplyEvent(BaseModel):
    email_id: str
    thread_id: Optional[str] = None
    campaign_id: Optional[str] = None
    campaign_key: Optional[str] = None
    niche: Optional[str] = None
    offer: Optional[str] = None
    eaccount: Optional[str] = None
    lead_email: str
    # The address that actually wrote the thread (item['from_address_email']).
    # It is NOT always the CRM address in item['lead']; Instantly validates the
    # reply `to` against the thread, so this is what a reply must be addressed to.
    reply_from: Optional[str] = None
    message_id: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company: Optional[str] = None
    subject: Optional[str] = ""
    text: str = ""
    # When the lead sent it: the email's own time as Instantly reports it
    # (from_poller_item: timestamp_created, else timestamp_email; from_webhook:
    # timestamp / timestamp_created / reply_timestamp / event_timestamp).
    received_at: datetime
    # RECEIVED_AT_EMAIL, or RECEIVED_AT_PROCESSING when the payload carried no
    # time and received_at is only the moment the engine saw the reply.
    received_at_source: str = RECEIVED_AT_EMAIL
    i_status: Optional[int] = None
    ai_interest_value: Optional[int] = None
    source: str = "poller"  # 'webhook' | 'poller' | 'replay'
    event_type: Optional[str] = None
    step: Optional[str] = None

    @field_validator("lead_email")
    @classmethod
    def _lower_email(cls, v: str) -> str:
        return (v or "").strip().lower()

    @field_validator("received_at", mode="before")
    @classmethod
    def _parse_received(cls, v):
        if isinstance(v, datetime):
            return slots.ensure_aware(v)
        return slots.parse_iso(v)

    @field_validator("reply_from")
    @classmethod
    def _lower_reply_from(cls, v):
        return (v or "").strip().lower() or None

    @property
    def state_key(self) -> str:
        return "lead:%s:%s" % (self.campaign_id or "unknown", self.lead_email)

    @property
    def reply_to_address(self) -> str:
        """Who a reply on this thread must be addressed to."""
        return self.reply_from or self.lead_email

    @property
    def dedupe_keys(self) -> List[str]:
        """Every identity this reply is known by, strongest first.

        A synthesised webhook id ('wh:<email>:<ts>') is deliberately excluded:
        two id-less webhooks in the same second would otherwise collapse onto
        one key and the second reply would be dropped as a duplicate.
        """
        keys = []  # type: List[str]
        if self.message_id:
            keys.append("mid:%s" % str(self.message_id).strip())
        fingerprint = content_fingerprint(self.lead_email, self.thread_id, self.text)
        if fingerprint:
            keys.append(fingerprint)
        if self.email_id and not is_synthetic_email_id(self.email_id):
            keys.append(str(self.email_id))
        return keys

    @classmethod
    def from_poller_item(cls, item: Dict[str, Any], lead: Optional[Dict[str, Any]] = None, source: str = "poller") -> "ReplyEvent":
        """Normalise one GET /emails item (email_type=received)."""
        lead = lead or {}
        meta = _campaign_meta(item.get("campaign_id"))
        first = _first(lead, "first_name", "firstName")
        last = _first(lead, "last_name", "lastName")
        if not first:
            first, last2 = _split_name(_first(item, "from_address_name", "from_name"))
            last = last or last2
        if not first:
            first = _first_name_from_subject(item.get("subject"))
        return cls(
            email_id=str(item.get("id")),
            thread_id=item.get("thread_id"),
            campaign_id=item.get("campaign_id"),
            campaign_key=meta.get("key"),
            niche=meta.get("niche"),
            offer=meta.get("offer"),
            eaccount=item.get("eaccount") or item.get("to_address_email_list"),
            lead_email=_first(item, "lead", "from_address_email", default=""),
            reply_from=_first(item, "from_address_email", "lead"),
            message_id=item.get("message_id"),
            first_name=first,
            last_name=last,
            company=_first(lead, "company_name", "companyName"),
            subject=item.get("subject") or "",
            text=reply_body_text(item),
            received_at=item.get("timestamp_created") or item.get("timestamp_email"),
            i_status=item.get("i_status"),
            ai_interest_value=item.get("ai_interest_value"),
            source=source,
            step=item.get("step"),
        )

    @classmethod
    def from_webhook(cls, payload: Dict[str, Any]) -> "ReplyEvent":
        """Normalise an Instantly webhook payload (reply_received, lead_interested, ...)."""
        campaign_id = _first(payload, "campaign_id", "campaign")
        meta = _campaign_meta(campaign_id)
        lead_obj = payload.get("lead") if isinstance(payload.get("lead"), dict) else {}
        first = _first(payload, "firstName", "first_name") or _first(lead_obj, "first_name", "firstName")
        last = _first(payload, "lastName", "last_name") or _first(lead_obj, "last_name", "lastName")
        email_id = _first(payload, "email_id", "reply_email_id", "id", "message_id")
        ts = _first(payload, "timestamp", "timestamp_created", "reply_timestamp", "event_timestamp")
        if not email_id:
            # Fall back to a deterministic id so idempotency still works.
            email_id = "wh:%s:%s" % (_first(payload, "lead_email", "email", default=""), ts or "")
        return cls(
            email_id=str(email_id),
            thread_id=_first(payload, "thread_id", "reply_thread_id"),
            campaign_id=campaign_id,
            campaign_key=meta.get("key"),
            niche=meta.get("niche"),
            offer=meta.get("offer"),
            eaccount=_first(payload, "email_account", "eaccount", "from_email"),
            lead_email=_first(payload, "lead_email", "email", default="") or _first(lead_obj, "email", default=""),
            reply_from=_first(payload, "from_address_email", "reply_from", "lead_email", "email"),
            message_id=_first(payload, "message_id", "reply_message_id"),
            first_name=first,
            last_name=last,
            company=_first(payload, "companyName", "company_name", "company") or _first(lead_obj, "company_name", "companyName"),
            subject=_first(payload, "reply_subject", "subject", default="") or "",
            text=_first(payload, "reply_text", "text", "reply_text_snippet", default="") or "",
            received_at=ts or datetime.now(slots.TZ),
            received_at_source=RECEIVED_AT_EMAIL if ts else RECEIVED_AT_PROCESSING,
            i_status=payload.get("interest_status") if isinstance(payload.get("interest_status"), int) else None,
            ai_interest_value=payload.get("ai_interest_value"),
            source="webhook",
            event_type=payload.get("event_type"),
            step=payload.get("step"),
        )


class Extracted(BaseModel):
    proposed_time: Optional[str] = None          # ISO, America/Chicago
    availability_window: Optional[Dict[str, Any]] = None  # {"start_hour","end_hour","tz"}
    phone: Optional[str] = None
    return_date: Optional[str] = None            # YYYY-MM-DD
    referral_name: Optional[str] = None
    question_type: Optional[str] = None          # pricing | mechanism | send_info | other | booking_link
    remove_request: bool = False
    follow_up_date: Optional[str] = None         # YYYY-MM-DD (negative_notnow)


class Classification(BaseModel):
    label: str
    confidence: float = 1.0
    reason: str = ""
    extracted: Extracted = Field(default_factory=Extracted)
    method: str = "rule"  # rule | llm | escalate | fallback
    model: Optional[str] = None

    @field_validator("label")
    @classmethod
    def _valid_label(cls, v: str) -> str:
        if v not in LABELS:
            raise ValueError("unknown label %r" % v)
        return v

    @property
    def is_positive(self) -> bool:
        return self.label in POSITIVE_LABELS

    @property
    def needs_draft(self) -> bool:
        return self.label in DRAFT_LABELS


class Draft(BaseModel):
    subject: str
    body_text: str
    offered_slots: List[str] = Field(default_factory=list)  # ISO CT
    booking_link: Optional[str] = None
    rationale: str = ""
    model: str = "template"
    label: Optional[str] = None
    problems: List[str] = Field(default_factory=list)
    # CT3: the catalogue template this body was rendered from, the hash of
    # that template when it was rendered (template_gate.stamp), and each part
    # id's hash. None / empty for a polished, edited or hand-written body,
    # which is always a card.
    template_id: Optional[str] = None
    template_hash: Optional[str] = None
    template_parts: Dict[str, Optional[str]] = Field(default_factory=dict)

    @property
    def sendable(self) -> bool:
        return not self.problems and bool(self.body_text.strip())


class Action(BaseModel):
    system: str            # instantly | ghl | store | none
    action: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    kind: str = "would_do"  # would_do (shadow) | done (live) | skipped
    note: str = ""


class Approval(BaseModel):
    token: str
    state_key: str
    lead_email: str
    campaign_id: Optional[str] = None
    # The offers.md key this card belongs to. Stored at create time so every
    # later validate_draft (notably approval.edit, where a human rewrites the
    # body by hand) can run the cross-offer proof guard, which returns [] when
    # no campaign key is supplied.
    campaign_key: Optional[str] = None
    email_id: str
    eaccount: Optional[str] = None
    # The thread's real counterparty: what instantly.reply_to_email must use as
    # `to`. lead_email stays the CRM/state key.
    reply_to: Optional[str] = None
    draft: Draft
    # pending | approved_queued | sending | sent | sent_manually | vetoed | expired | blocked |
    # superseded | stale_slots | send_failed. sent_manually: a card stuck at send_failed, or at
    # sending once its send claim is approval.SEND_CLAIM_LEASE_MINUTES old, whose reply
    # Lorenzo confirmed did go out (approval.mark_sent_manually, MARK_SENT_FROM). It is done
    # exactly like sent; Mark sent itself sends nothing through Instantly.
    status: str = "pending"
    # Write-ahead send claim: set before the Instantly call, so a crash between
    # the send and the save can never be replayed as a fresh send.
    send_attempt: Optional[str] = None
    created_at: str
    expires_at: str
    decided_at: Optional[str] = None
    send_after: Optional[str] = None
    label: Optional[str] = None
    notify_result: Optional[Dict[str, Any]] = None
    # The 5-minute reply SLA, enforced rather than measured once a day: how many
    # rungs of approval.ESCALATION_LADDER this card has already been chased up,
    # and when it was last chased. Both only ever move while the card is still
    # `pending` inside sending hours; a chase is a push, never a send.
    escalations: int = 0
    last_escalated_at: Optional[str] = None
    # Set when the lead asked for a specific time that only Lorenzo's own slot
    # rule blocks (before 12:00, a weekend, under 4 h out, past the 5-business-day
    # horizon). The draft counter-proposes; these fields let the approval card
    # also offer "book it as asked" instead.
    requested_slot: Optional[str] = None      # ISO CT
    requested_status: Optional[str] = None    # booking.BookingMatch.status
    requested_lead_tz: Optional[str] = None
    # CT3: who approved the send: "lorenzo" (a tap on Approve, Retry or Book
    # as asked) or "template" (approval.auto_send_approved, for a draft that is
    # exactly an approved template). None until approved.
    approved_by: Optional[str] = None
    # CT3: the template gate's verdict when the card was raised
    # (template_gate.Verdict.to_record(): ids, statuses and the reason, never
    # text), plus the classification it was judged on ({"label",
    # "confidence", "method"}). None for a card raised without a verdict.
    auto_send: Optional[Dict[str, Any]] = None
    # What the lead wrote (the reply this card answers), quoted history cut
    # and capped (approval.lead_reply_excerpt), shown above the draft on the
    # email leg and a protected topic only. None on a card stored before it.
    lead_reply: Optional[str] = None


class LeadState(BaseModel):
    lead_email: str
    campaign_id: Optional[str] = None
    campaign_key: Optional[str] = None
    status: str = "new"
    classification: Optional[Classification] = None
    drafts: List[Draft] = Field(default_factory=list)
    approvals: List[str] = Field(default_factory=list)  # approval tokens
    cadence: Dict[str, Any] = Field(default_factory=dict)
    ghl_contact_id: Optional[str] = None
    ghl_opportunity_id: Optional[str] = None
    last_inbound_at: Optional[str] = None
    last_outbound_at: Optional[str] = None
    offered_slots: List[str] = Field(default_factory=list)
    processed_email_ids: List[str] = Field(default_factory=list)
    # every dedupe identity (message id, content fingerprint, provider id) that
    # has been claimed for this lead; processed_email_ids stays one-per-reply
    processed_keys: List[str] = Field(default_factory=list)
    first_name: Optional[str] = None
    company: Optional[str] = None
    phone: Optional[str] = None
    eaccount: Optional[str] = None
    thread_id: Optional[str] = None
    last_email_id: Optional[str] = None
    last_subject: Optional[str] = None
    history: List[Dict[str, Any]] = Field(default_factory=list)
    # The sticky opt-out marker: None, or {"label", "email_id", "received_at",
    # "set_at"} ("received_at_source": "processing" when the opt-out's payload
    # carried no time). Set when a reply with a router.OPT_OUT_LABELS label is
    # processed, unless the marker already records a later one; cleared only by
    # a human reply (not a machine's, not an opt-out) sent strictly after it.
    # Written only under the row's lock (app._inbound_stop_hook), never through
    # the three-way merge. Rows stored before it existed load with None.
    opt_out: Optional[Dict[str, Any]] = None

    @field_validator("opt_out", mode="before")
    @classmethod
    def _tolerant_opt_out(cls, v):
        # A value that is not a dict must not make the whole row unreadable
        # (every reply for the lead would then fail); kept truthy, it still holds.
        if not v:
            return None
        return v if isinstance(v, dict) else {"malformed": str(v)}

    @property
    def key(self) -> str:
        return "lead:%s:%s" % (self.campaign_id or "unknown", self.lead_email)

    def to_store(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_store(cls, data: Optional[Dict[str, Any]], event: Optional[ReplyEvent] = None) -> "LeadState":
        if data:
            return cls.model_validate(data)
        if event is None:
            raise ValueError("need data or event")
        return cls(
            lead_email=event.lead_email,
            campaign_id=event.campaign_id,
            campaign_key=event.campaign_key,
            first_name=event.first_name,
            company=event.company,
            eaccount=event.eaccount,
            thread_id=event.thread_id,
        )
