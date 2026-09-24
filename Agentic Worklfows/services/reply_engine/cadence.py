"""Daily follow-up cadence for positive replies (Blueprint S2, Eric's framework
extended to 7 days, then D14 / D30 re-touches, then Follow Up Later).

Owns the ``cadence`` dict on LeadState:

    {
      "armed_at": ISO,            # when Lorenzo approved the first reply
      "armed_for_email_id": str,  # the inbound that approved reply answered (set under
                                  # the lead row's lock by approval._arm_under_lock)
      "day": int,                 # last cadence day completed (0 = none yet)
      "next_send_at": ISO|None,   # next 10:00 CT send instant
      "touches": [ {...}, ... ],  # one record per touch (or would_do in shadow)
      "stopped_reason": str|None, # booked | inbound_reply | unsubscribe | hostile |
                                  # follow_up_later | opt_out | vetoed | exhausted |
                                  # nurture (enrolled in the 90-day nurture, nurture.py)
      "veto_notified_at": ISO|None,
      "d6_notified_at": ISO|None,
      "stall_notified_at": ISO|None,          # "waiting on your fresh draft" said once
      "resumed_after_auto_reply_at": ISO|None, # the auto-reply's own received time: the
                                  # inbound baseline stop_reason reads after a pause
      "auto_reply_seen_through": ISO|None,    # when the engine processed the newest inbound
                                  # that pause took stock of (inbounds_since_baseline)
      "auto_reply_seen_email_id": str|None,   # and that inbound's email id (its history entry)
      "needs_fresh_draft": bool,  # set when an inbound reply stopped the cadence
      "last_blocked": {...}|None, # copy check refused a touch
      "booking": {...}|None       # written by booking.book()
    }

Every touch pulls fresh slots via shared.slots.candidate_slots, excluding the
lead's own ``offered_slots`` and every slot still outstanding for any lead in
the rolling registry ``offered_slots`` (the same key approval.py writes). The
reservation is keyed on the slot, never on the day the offer was made, so two
leads touched on consecutive days cannot be sent the same Thursday 12:00.
``offered:<YYYY-MM-DD>`` is kept as a per-day audit trail.

Shadow contract: every send goes through Instantly.reply_to_email which calls
shared.settings.guard_write first, so in MODE=shadow a touch is a would_do
record and no HTTP request is made. Every send passes ``to=recipient_for(state)``
- the address that actually wrote the thread, which is not always the CRM
``lead_email`` - so Instantly validates the recipient against the thread. D1
auto-sends only in live mode after a 30-minute veto window, and only when that
veto link was actually delivered and points at a usable BASE_URL
(``veto_undeliverable`` otherwise); a live touch goes out only when the thread
re-read CONFIRMS the recipient (decision R6: a read error holds it); D6's
calendar hold needs Lorenzo's OK and, in live, the CADENCE_D6_HOLD opt-in. A
touch whose copy fails copy_problems() is never sent (action ``blocked_copy``),
and a send that did not happen never advances the day (action ``send_failed``).

Idempotency: the touch marker is claimed with ``store.set_if_absent`` before the
POST, so two overlapping ticks cannot both send a day. It is deleted only for
refusals decided before the request was issued (see PRE_SEND_REFUSALS); an
exception or an HTTP failure leaves it in place, because a write that never got
an answer may still have been accepted. Slots are reserved before the marker is
confirmed and replayed by _repair_from_marker, so a crash can never hand two
prospects the same 15 minutes.

All functions take ``now`` explicitly. No wall-clock reads.
"""
import dataclasses
import hashlib
import hmac
import json
import logging
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import quote, urlencode

from shared import llm, settings
from shared import slots as slot_rules
from shared.notify import notify
from shared.settings import CADENCE_HOUR, TZ, guard_write, is_live

try:  # the shared copy validator (draft.validate_draft) is the gate the human-approved
    # first reply already clears; the unattended cadence clears the same one.
    from services.reply_engine import draft as draft_mod  # type: ignore
except Exception:  # noqa: BLE001 - see copy_problems(): a missing validator BLOCKS, it never opens the gate
    draft_mod = None  # type: ignore

try:  # core (A1) owns models.py; fall back to a minimal local shape so this module tests standalone
    from services.reply_engine.models import Draft, LeadState  # type: ignore
except Exception:  # noqa: BLE001 - any import problem means "run standalone"

    class LeadState(object):  # type: ignore
        """Minimal stand-in with the fields the cadence relies on."""

        def __init__(self, lead_email, campaign_id=None, status="new", cadence=None, offered_slots=None,
                     ghl_contact_id=None, ghl_opportunity_id=None, last_inbound_at=None, last_outbound_at=None,
                     first_name=None, company=None, eaccount=None, thread_id=None, last_email_id=None,
                     last_subject=None, history=None, **extra):
            self.lead_email = lead_email
            self.campaign_id = campaign_id
            self.status = status
            self.cadence = cadence if cadence is not None else {}
            self.offered_slots = offered_slots if offered_slots is not None else []
            self.ghl_contact_id = ghl_contact_id
            self.ghl_opportunity_id = ghl_opportunity_id
            self.last_inbound_at = last_inbound_at
            self.last_outbound_at = last_outbound_at
            self.first_name = first_name
            self.company = company
            self.eaccount = eaccount
            self.thread_id = thread_id
            self.last_email_id = last_email_id
            self.last_subject = last_subject
            self.history = history if history is not None else []
            for k, v in extra.items():
                setattr(self, k, v)

        @property
        def key(self):
            return "lead:%s:%s" % (self.campaign_id or "unknown", self.lead_email)

        def to_store(self):
            return dict(self.__dict__)

        @classmethod
        def from_store(cls, data, event=None):
            return cls(**dict(data or {}))

    @dataclasses.dataclass
    class Draft(object):  # type: ignore
        subject: str
        body_text: str
        offered_slots: List[str] = dataclasses.field(default_factory=list)
        booking_link: Optional[str] = None
        rationale: str = ""
        model: str = "template"
        label: Optional[str] = None
        problems: List[str] = dataclasses.field(default_factory=list)
        # CT3 (template_gate): which approved template this text was rendered
        # from, and the catalogue hashes at render time.
        template_id: Optional[str] = None
        template_hash: Optional[str] = None
        template_parts: Dict[str, Optional[str]] = dataclasses.field(default_factory=dict)


logger = logging.getLogger("reply_engine.cadence")

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# Day sequence: seven daily touches, then two re-touches from Follow Up Later.
DAY_SEQUENCE = (1, 2, 3, 4, 5, 6, 7, 14, 30)
INTENTS = {
    1: "lost_times",
    2: "research",
    3: "times_went",
    4: "case_study",
    5: "free_work",
    6: "calendar_invite",
    7: "yes_no_close",
    14: "retouch",
    30: "retouch_final",
}
SLOTLESS_DAYS = (7,)
VETO_WINDOW_MINUTES = 30
# CT3: where day 2's research line comes from. "fallback" (the default) is the
# fixed line fallback_research_line() writes, which Lorenzo can approve
# (cadence.d2.research_fallback.<offer>), and shared.llm role "research" is
# never called. "llm" asks the model first; a line it writes is covered by no
# approval (cadence.d2.research_line), so that day 2 is always held.
D2_RESEARCH_MODE = "fallback"
# CT3: a day held because its template is not approved (or its text is not an
# auto-sendable form of it) is reported once a day. The stall counts the
# business days on which the day was held for a cause that is not gate-wide
# (see below), whatever order the causes come in, and they add up: a gate-wide
# hold in between neither counts nor resets the count, so an approval hold
# after a kill-switch pause continues the count it had before the pause. On
# the tick that finds the day held for such a cause with this many earlier
# held days counted, the ladder is stopped as ``template_unapproved``
# (resumable); never on a tick whose hold is gate-wide (_hold_for_template).
TEMPLATE_HOLD_STALL_DAYS = 3
# CT3: the daily Resume reminder of a ``template_unapproved`` stop ends after this many pushes, or this many days
# after ``stopped_at``, whichever comes first (_template_stop_reminder); the ladder itself stays stopped.
TEMPLATE_STOP_REMINDER_MAX_PUSHES = 8
TEMPLATE_STOP_REMINDER_MAX_DAYS = 14
# CT3: why a day is held, by what fixes it (hold_cause). A gate-wide hold (the
# kill switch, a parity failure, a catalogue or approvals file the gate could
# not read, the catalogue not built yet) holds every ladder at once and clears
# by itself when the cause is fixed: it is never counted toward the stall and
# never stops a ladder, so the day goes out late instead. A reason the gate
# does not list is treated the same way (it holds, it never stops).
SYSTEM_HOLD_REASONS = ("kill_switch", "parity_failed", "registry_error", "not_ready")
APPROVE_HOLD_REASONS = ("unapproved", "changed_since_approval")
LEAD_DATA_HOLD_REASONS = ("nonconforming", "copy_gate")
CODE_HOLD_REASONS = ("no_template", "not_template_render", "unknown_id", "not_approvable", "stale_render",
                     "classification", "requested_override")
D6_FALLBACK_HOUR = 18  # if Lorenzo has not answered the invite request by then, send the no-invite variant
SLOT_MINUTES = slot_rules.SLOT_MINUTES
GRID_STEP_MINUTES = 30

# Cross-lead slot reservations. The same rolling registry approval.py writes
# ([{"slot", "lead", "at", ...}]), so a slot offered by the day-0 draft or by
# any lead's touch on ANY day is never offered again while it is still ahead of
# us. ``offered:<date>`` is kept as a per-day audit trail only.
OFFERED_REGISTRY_KEY = "offered_slots"

# Signed one-tap decision URLs (mirrors approval.make_token). Without
# REPLY_ENGINE_SECRET nothing can be verified, so a decision recorded with no
# token is accepted (token_ok=None). Once the secret IS set, every card URL
# carries a token and an unsigned decision is refused (token_ok=False).
DECISION_SECRET_ENV = "REPLY_ENGINE_SECRET"
DECISION_TTL_HOURS = 48

# Labels/statuses that mean "a machine replied, not the human": these pause the
# cadence instead of ending it (Blueprint S1: only a human reply needs a draft).
AUTO_REPLY_STATUSES = ("ooo", "auto_reply", "auto_reply_unmonitored")

# Statuses / labels that end the cadence (core's models.LABELS vocabulary plus stage-ish statuses)
BOOKED_STATUSES = ("booked", "call_booked", "meeting_booked", "meeting_completed", "won", "closed")
UNSUBSCRIBE_STATUSES = ("unsubscribe", "unsubscribed", "blocklisted")
HOSTILE_STATUSES = ("negative_hostile", "hostile", "lost", "negative_notfit", "wrong_person")
NOT_NOW_STATUSES = ("negative_notnow", "not_now", "follow_up_later")

DEFAULT_BOOKING_URL = settings.BOOKING_URL or "https://api.leadconnectorhq.com/widget/booking/GDugwLmZNdsD13RBDnRu"

# Fallback proof lines (offers.md is the source of truth; these are only used if the table cannot be parsed)
_FALLBACK_PROOF = {
    "reactivation": "I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.",
    "outbound": "I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.",
}


# ------------------------------------------------------------------ models
@dataclasses.dataclass
class Touch(object):
    day: int
    intent: str
    subject: str
    body_text: str
    slots: List[str] = dataclasses.field(default_factory=list)  # ISO strings, CT
    requires_approval: bool = False
    channel_note: Optional[str] = None
    slots_source: str = "provided"
    meta: Dict[str, Any] = dataclasses.field(default_factory=dict)
    # Values that came from the lead's own record (company, first name). They are
    # quoted back verbatim, so a prospect called "Automation Depot" must not trip
    # the AI gate on its own name; only the prose around it is judged.
    allow_terms: List[str] = dataclasses.field(default_factory=list)
    # The offers.md key this lead was pitched under. Without it the copy gate
    # cannot tell whose guarantee a number is, so cleaning's "$24,000 a year in
    # new contracts within 90 days" sailed through inside a bookkeeping thread.
    campaign_key: Optional[str] = None
    # CT3: the catalogue id this body was rendered from and the ids of the
    # lines spliced into it (day 2, 4 and 5). build_touch sets the ids only;
    # tick_lead stamps the hashes (template_gate.stamp) right before the gate.
    template_id: Optional[str] = None
    template_hash: Optional[str] = None
    template_parts: Dict[str, Optional[str]] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @property
    def problems(self) -> List[str]:
        return copy_problems(self.body_text, allow=self.allow_terms, campaign_key=self.campaign_key)


_MONEY_RE = re.compile(r"\$\s?\d[\d,\.]*\s?(?:[KkMmBb]\b|thousand|million|billion)?")
# Percentages are pricing too: offers.md quotes 20-30% for every reactivation
# deal, so "45% of first-year fees" in an unattended touch is an invented price.
_PERCENT_RE = re.compile(r"\d[\d,\.]*\s?(?:-\s?\d[\d,\.]*\s?)?%")
# "AI", "A.I.", "bots", "chatbot": offers.md rule 8 forbids signalling that a
# system wrote the mail, and \bAI\b alone missed the dotted and plural forms.
_AI_RE = re.compile(
    r"(\bAI\b|\bA\.\s?I\.?|\bartificial intelligence\b|\bautomation\b|\bautomated\b|\bautomating\b|"
    r"\bautomate[sd]?\b|\bbots?\b|\bchat\s?bots?\b|\bGPT\b|\bChatGPT\b|\bClaude\b|\bLLM\b)", re.I)
# No cadence template promises a guarantee; only an invented line can, and the
# guarantees in offers.md belong to the outbound rows, never to a follow-up.
_GUARANTEE_RE = re.compile(r"\bguarantee[sd]?\b|\bguaranteeing\b", re.I)


def _offers_text() -> str:
    """The offer sheet, or a loud error. Pricing and proof come from it and
    nowhere else, so an unreadable sheet must not quietly open the money gate
    (draft.py already fails loudly here; the cadence used to return [])."""
    return settings.require_offers()


def _flat(text: str) -> str:
    """Whitespace-free, dash-normalised, for verbatim comparison against the sheet."""
    return re.sub(r"\s+", "", (text or "").replace("\u2014", "-").replace("\u2013", "-"))


def _redact(text: str, allow: Optional[List[str]] = None) -> str:
    """Blank out values that came from the lead's own record before judging the
    prose, so a company name cannot trip a copy rule the writer did not break."""
    out = text or ""
    for term in allow or []:
        term = str(term or "").strip()
        if len(term) >= 3:
            out = re.sub(re.escape(term), " ", out, flags=re.I)
    return out


def _unverified_money(text: str) -> List[str]:
    """Dollar figures that do not appear verbatim in config/offers.md.

    The only numbers a customer-facing touch may contain are the proof points
    in the offer sheet ("$6M", "$180,000"). An LLM research line that invents
    "$50,000 in recovered contracts" is caught here."""
    flat = _flat(_offers_text())
    bad = []
    for m in _MONEY_RE.findall(text):
        token = _flat(m).rstrip(".,")
        if token and token not in flat:
            bad.append(token)
    return bad


def _unverified_percent(text: str) -> List[str]:
    """Percentages that do not appear verbatim in config/offers.md."""
    flat = _flat(_offers_text())
    bad = []
    for m in _PERCENT_RE.findall(text):
        token = _flat(m).rstrip(".,")
        if token and token not in flat:
            bad.append(token)
    return bad


# draft.validate_draft is the gate the human-approved first reply clears. Its
# problems are sentences; the cadence's are short codes, and both vocabularies
# are asserted by tests and read off blocked_copy cards. This is the join, so
# the two gates cannot drift: every rule draft.py gains arrives here with it.
_SHARED_PROBLEM_CODES = (
    ("em or en dash", "dash"),
    ("exclamation mark", "exclamation"),
    ("mentions AI", "mentions_ai_or_automation"),
    ("mentions automation", "mentions_ai_or_automation"),
    ("mentions machine learning", "mentions_ai_or_automation"),
    ("mentions an algorithm", "mentions_ai_or_automation"),
    ("mentions a bot", "mentions_ai_or_automation"),
    ("must end with the signature line", "unsigned"),
    ("empty body", "empty_body"),
    ("is marked TO CONFIRM", "money_marked_to_confirm"),
    # Percentages (Defect 8) come before the dollar needle: "percentage 25% not
    # in offers.md" also contains "not in offers.md". The flat one shares its
    # code with the cadence's own verbatim check below, as the dollar one does;
    # "percentage 20% is the pricing of X" / "is the figure of the 'X' proof"
    # is the cross-offer one (SAL-11), which used to arrive as copy_rule:<sentence>.
    ("% not in offers.md", "percentage_not_in_offer_sheet"),
    ("% is the ", "percentage_from_another_offer"),
    ("not in offers.md", "money_not_in_offer_sheet"),
    ("guarantee, not", "guarantee_from_another_offer"),
    ("proof line for", "proof_from_another_offer"),
    ("belongs to the", "proof_from_another_offer"),
)
# draft.validate_draft's reply-length cap is a first-reply rule, not a copy-safety
# one, and the cadence has never had one. Carried across it would block a day for
# a reason that is not about what the prospect is told.
_SHARED_PROBLEMS_IGNORED = ("too long", "missing booking link")
# The shared validator could not be imported. That is not "no problems": it is
# the copy gate missing, so the touch is blocked and Lorenzo is told which gate.
VALIDATOR_UNAVAILABLE = "copy_validator_unavailable"


def _shared_code(problem: str) -> str:
    """One draft.validate_draft sentence -> the cadence's short code."""
    for needle, code in _SHARED_PROBLEM_CODES:
        if needle in problem:
            return code
    # A rule draft.py grows that nothing here maps yet still blocks the touch,
    # carrying its own sentence, rather than being silently dropped.
    return "copy_rule:%s" % problem


def shared_problems(text: str, allow: Optional[List[str]] = None,
                    campaign_key: Optional[str] = None) -> List[str]:
    """draft.validate_draft's verdict, in the cadence's vocabulary.

    Raises nothing: a missing validator comes back as VALIDATOR_UNAVAILABLE so
    the caller blocks instead of sending unchecked copy.
    """
    if draft_mod is None:
        logger.error("services.reply_engine.draft could not be imported; every cadence touch is blocked")
        return [VALIDATOR_UNAVAILABLE]
    try:
        raw = draft_mod.validate_draft(text or "", campaign_key=campaign_key, allow_terms=list(allow or []))
    except Exception as exc:  # noqa: BLE001 - a validator that raised has not approved anything
        logger.error("draft.validate_draft raised on a cadence touch: %s", exc)
        return [VALIDATOR_UNAVAILABLE]
    out = []  # type: List[str]
    for problem in raw:
        if any(problem.startswith(prefix) for prefix in _SHARED_PROBLEMS_IGNORED):
            continue
        code = _shared_code(problem)
        if code not in out:
            out.append(code)
    return out


def copy_problems(text: str, allow: Optional[List[str]] = None,
                  campaign_key: Optional[str] = None) -> List[str]:
    """Customer-facing copy rules for an UNATTENDED touch.

    Two halves, and both have to pass:

    1. ``draft.validate_draft`` - the same validator that gates the first reply
       Lorenzo approves by hand. It knows which offer this lead was pitched, so
       a figure that belongs to another vertical's guarantee is refused, and it
       refuses outright anything offers.md marks TO CONFIRM (today the
       $2,500-5,000/mo retainer). ``campaign_key`` is what makes both of those
       answerable; without it the cross-offer half is silent, which is how
       cleaning's $24,000 guarantee passed inside a bookkeeping thread.
    2. The cadence's own extra rules, which are stricter still and stay:
       verbatim-substring money and percentage checks against the sheet, no
       unfilled ``{placeholder}``, and no "guarantee" at all - offers.md keeps
       guarantees for the outbound pitch, never for a follow-up.

    This runs on the only path that reaches a prospect with nobody reading it
    first, so it must never be the weaker of the two gates.

    ``allow`` holds values that came from the lead's own record (company, first
    name). They are quoted back verbatim, so they are removed before the prose
    is judged: a prospect called "Automation Depot" is not a copy failure."""
    out = shared_problems(text, allow=allow, campaign_key=campaign_key)

    def add(code):
        if code not in out:
            out.append(code)

    if "\u2014" in text or "\u2013" in text:
        add("dash")
    if "!" in text:
        add("exclamation")
    judged = _redact(text, allow)
    if _AI_RE.search(judged):
        add("mentions_ai_or_automation")
    if not text.rstrip().endswith("Lorenzo"):
        add("unsigned")
    if re.search(r"\{[a-z_0-9]+\}", text):
        add("unfilled_placeholder")
    if _unverified_money(judged):
        add("money_not_in_offer_sheet")
    if _unverified_percent(judged):
        add("percentage_not_in_offer_sheet")
    if _GUARANTEE_RE.search(judged):
        add("unverified_guarantee")
    return out


# --------------------------------------------------------------- helpers
def _field(state: Any, *names: str, default: Any = None) -> Any:
    for n in names:
        v = getattr(state, n, None)
        if v not in (None, ""):
            return v
    return default


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return slot_rules.to_tz(dt).isoformat() if dt is not None else None


def _parse(value: Union[str, datetime, None]) -> Optional[datetime]:
    if value in (None, ""):
        return None
    try:
        return slot_rules.to_tz(slot_rules.parse_iso(value))
    except (ValueError, TypeError):
        return None


def campaign_meta(state: Any) -> Dict[str, Any]:
    meta = dict(settings.CAMPAIGN_BY_ID.get(_field(state, "campaign_id") or "", {}))
    key = _field(state, "campaign_key")
    if not meta and key:
        meta = dict(settings.CAMPAIGNS.get(key, {}), key=key)
    return meta


def niche_and_offer(state: Any) -> Tuple[str, str]:
    meta = campaign_meta(state)
    niche = (_field(state, "niche") or meta.get("niche") or "").lower()
    offer = (_field(state, "offer") or meta.get("offer") or "").lower()
    if offer in ("trigger", "outbound"):
        offer = "outbound"
    return niche, offer or "reactivation"


def campaign_key_of(state: Any) -> Optional[str]:
    """The config/offers.md key this lead's copy is judged against.

    ``Approval.campaign_key`` stores the same thing for the first reply, for the
    same reason: the cross-offer guards in draft.validate_draft return [] when
    no key is supplied, so a touch built without one is judged as if every
    guarantee in the sheet belonged to it.
    """
    key = _field(state, "campaign_key") or campaign_meta(state).get("key")
    if key:
        return str(key)
    niche, offer = niche_and_offer(state)
    if not niche:
        return None
    if offer == "outbound":
        guess = "%s_outbound" % niche if niche == "recruiting" else "%s_trigger" % niche
    else:
        guess = "%s_reactivation" % niche
    return guess if guess in settings.CAMPAIGNS else None


def first_name_of(state: Any) -> str:
    return str(_field(state, "first_name", default="there")).strip().split(" ")[0]


def company_of(state: Any) -> str:
    return str(_field(state, "company", "company_name", default="your team")).strip()


# Reply prefixes a mail client stacks up, and the auto-responder prefixes a
# robot stacks on top of them. app.py records ``last_subject`` on EVERY inbound,
# including out-of-office mail, so without this the touch after a resumed
# auto-reply goes out as "Re: Automatic reply: Tiffany, question" - which tells
# the prospect in the subject line that a machine is answering their machine.
_REPLY_PREFIX_RE = re.compile(r"^\s*(?:re|fw|fwd|aw|ext)\s*:\s*", re.I)
_AUTO_PREFIX_RE = re.compile(
    r"^\s*(?:automatic reply|automated (?:reply|response)|automatic response|auto[- ]?reply|autoreply|"
    r"out of (?:the )?office|ooo|away from (?:the |my )?office|"
    r"thank you for (?:your e-?mail|your message|contacting[^:]{0,60}|reaching out)|"
    r"this (?:e-?mail|mailbox|inbox)(?: address)? is no longer monitored|"
    r"undeliverable|delivery (?:status|failure))\s*[:.\-]*\s*", re.I)
# The same signals anywhere in the subject: "I'm currently out of the office."
# carries no usable thread subject at all, so the cadence falls back instead of
# quoting a robot.
_AUTO_ANYWHERE_RE = re.compile(
    r"(automatic reply|automated (?:reply|response)|auto[- ]?reply|autoreply|out of (?:the )?office|"
    r"no longer monitored|not monitored|undeliverable|delivery (?:status|failure))", re.I)


def normalize_subject(raw: Optional[str]) -> str:
    """Strip stacked Re:/Fwd:/EXT: and auto-responder prefixes down to the
    thread's own subject. Mirrors draft.reply_subject's normaliser (so the
    approved first reply and every cadence touch stay on one subject) and
    extends it to the auto-responder prefixes draft never sees."""
    subj = str(raw or "").strip()
    for _ in range(8):
        stripped = _AUTO_PREFIX_RE.sub("", _REPLY_PREFIX_RE.sub("", subj)).strip()
        if stripped == subj:
            break
        subj = stripped
    return subj


def subject_for(state: Any) -> str:
    """'Re: <thread subject>'. Without a usable thread subject it rebuilds the
    cold email's own '<First>, question'; without a real first name either it
    says 'Re: your reply' (draft.reply_subject's fallback), never
    'Re: there, question'."""
    core = normalize_subject(_field(state, "last_subject", "subject", "thread_subject"))
    if not core or _AUTO_ANYWHERE_RE.search(core):
        first = first_name_of(state)
        if not first or first.lower() == "there":
            return "Re: your reply"
        return "Re: %s, question" % first
    return "Re: %s" % core


# ------------------------------------------------------------- day math
def cadence_send_time(d: date, tz=TZ) -> datetime:
    """10:00 CT on the given date."""
    return tz.localize(datetime(d.year, d.month, d.day, CADENCE_HOUR, 0))


def roll_to_business_day(d: date) -> date:
    while d.weekday() >= 5:
        d = d + timedelta(days=1)
    return d


def next_business_day_send(after: datetime, tz=TZ) -> datetime:
    """The next business day after ``after`` (date-wise) at 10:00 CT.
    Friday 16:00 -> Monday 10:00; Monday 21:10 -> Tuesday 10:00."""
    ct = slot_rules.to_tz(after, tz)
    return cadence_send_time(roll_to_business_day(ct.date() + timedelta(days=1)), tz)


def next_day_number(day_done: int) -> Optional[int]:
    for d in DAY_SEQUENCE:
        if d > day_done:
            return d
    return None


def schedule_after(day_done: int, sent_at: datetime, tz=TZ) -> Optional[datetime]:
    """When the touch after ``day_done`` should go out."""
    ct = slot_rules.to_tz(sent_at, tz)
    if day_done < 7:
        return next_business_day_send(ct, tz)
    if day_done == 7:  # D14 = one week later
        return cadence_send_time(roll_to_business_day(ct.date() + timedelta(days=7)), tz)
    if day_done == 14:  # D30 = ~16 days after D14
        return cadence_send_time(roll_to_business_day(ct.date() + timedelta(days=16)), tz)
    return None


# -------------------------------------------------------------- lifecycle
def arm(state: Any, now: datetime, store: Any = None, restart: bool = False) -> Any:
    """Arm (or re-arm) the cadence right after Lorenzo approves a reply.

    A lead who replies mid-cadence and gets a fresh approved answer **resumes**:
    the completed day is kept, so a lead stopped at D4 comes back at D5 instead
    of hearing "I lost both of those times" a second time. ``restart=True``
    starts the ladder again from D1.

    Any veto / D6 decision from the previous run is dropped: decisions are
    stamped with the ``armed_at`` they belong to (and deleted outright when a
    store is passed), so a two-week-old tap can never govern this run."""
    now = slot_rules.to_tz(now)
    cad = dict(state.cadence or {})
    touches = list(cad.get("touches") or [])
    day_done = 0 if restart else int(cad.get("day") or 0)
    cad.update({
        "armed_at": now.isoformat(),
        "day": day_done,
        "next_send_at": next_business_day_send(now).isoformat(),
        "touches": touches,
        "stopped_reason": None,
        "stopped_at": None,
        "veto_notified_at": None,
        "d6_notified_at": None,
        "needs_fresh_draft": False,
        "stall_notified_at": None,
        "resumed": bool(day_done) or bool(cad.get("resumed")),
    })
    cad.pop("paused", None)
    cad.pop("resume_at", None)
    cad.pop("last_blocked", None)
    cad.pop("last_skipped", None)
    cad.pop("veto_undeliverable_at", None)
    cad.pop("d1_held_no_base_url_at", None)
    cad.pop("recipient_hold", None)
    cad.pop("template_hold", None)
    cad.pop("d1_gate_hold", None)
    # The thread counterparty, kept on the cadence's own record so every touch
    # answers whoever actually wrote (see recipient_for).
    thread_from = _field(state, "reply_from", "reply_to_address")
    if thread_from:
        cad["reply_from"] = str(thread_from).strip()
    if cad.get("reason") in AUTO_REPLY_STATUSES:
        cad.pop("reason", None)
    state.cadence = cad
    if getattr(state, "offered_slots", None) is None:
        state.offered_slots = []
    if store is not None:
        for key in (veto_key(state), approval_key(state, "d6")):
            try:
                store.delete(key)
            except Exception as exc:  # noqa: BLE001 - a store without delete must not break arming
                logger.warning("could not clear %s: %s", key, exc)
    return state


def resume(state: Any, now: datetime, store: Any = None) -> Any:
    """Explicit alias for the resume path (arm keeps the completed day).
    Refuses (returns the state untouched) while the lead is enrolled in the
    90-day nurture: that lead gets no more follow-up touches."""
    if in_nurture(state, store):
        return state
    return arm(state, now, store=store, restart=False)


def in_nurture(state: Any, store: Any = None) -> bool:
    """True while the lead has an active 90-day nurture record
    (nurture.enroll). Read from the record's own key, in the shared store when
    none is passed. A store that cannot be read raises; callers hold."""
    from services.reply_engine import nurture as nurture_mod

    return nurture_mod.is_enrolled(_field(state, "lead_email"), store)


RESUMABLE_STOPS = ("recipient_unconfirmed", "template_unapproved")


def resume_after_recipient_hold(state: Any, now: datetime) -> Dict[str, Any]:
    """Lorenzo tapped Resume on a ladder that was stopped by a hold: R6's
    recipient hold (the thread re-read kept failing) or CT3's template hold
    (the day's template stayed unapproved for TEMPLATE_HOLD_STALL_DAYS
    business days). Un-stops it with a fresh attempt budget and makes the held
    day due now; the next tick re-reads the thread and re-runs the template
    gate before it sends anything, exactly as before. Only those two stops are
    resumable: ``recipient_mismatch`` means the thread is somebody else's, and
    that needs the lead re-pointed, not a retry.

    The remembered D1 refusal (``d1_gate_hold``) goes too, so a held D1 gets
    a fresh full check on the next tick rather than being held again because
    nothing it looked at changed: a gate rule relaxed by a deploy that did not
    bump template_gate.GATE_RULES_VERSION leaves the fingerprint as it was. A
    pass opens one fresh 30-minute Veto window; a refusal (at the pre-check
    or at send time) is recorded again, so the window does not re-open on
    every tick."""
    ct = slot_rules.to_tz(now)
    cad = dict(getattr(state, "cadence", None) or {})
    reason = cad.get("stopped_reason")
    if not cad.get("armed_at") or reason not in RESUMABLE_STOPS:
        return {"resumed": False, "reason": reason or "not_stopped"}
    cad.pop("stopped_reason", None)
    cad.pop("stopped_at", None)
    cad.pop("d1_gate_hold", None)
    held = cad.pop("recipient_hold", None) or {}
    template_held = cad.pop("template_hold", None) or {}
    if not held and template_held:
        held = template_held
    cad["needs_fresh_draft"] = False
    cad["next_send_at"] = ct.isoformat()
    cad["resumed_after_recipient_hold_at"] = ct.isoformat()
    # The held day's send moved: a D1 re-opens its 30-minute Veto window with
    # a fresh link instead of going out behind yesterday's push.
    cad["veto_notified_at"] = None
    state.cadence = cad
    _log_job("template_hold_resumed" if reason == "template_unapproved" else "recipient_hold_resumed",
             {"lead": _field(state, "lead_email"), "day": held.get("day")})
    return {"resumed": True, "day": held.get("day"), "next_send_at": ct.isoformat()}


def is_armed(state: Any) -> bool:
    cad = getattr(state, "cadence", None) or {}
    return bool(cad.get("armed_at")) and not cad.get("stopped_reason") and cad.get("next_send_at") is not None


def stop(state: Any, reason: str, now: datetime) -> Any:
    cad = dict(state.cadence or {})
    cad["stopped_reason"] = reason
    cad["stopped_at"] = slot_rules.to_tz(now).isoformat()
    cad["next_send_at"] = None
    cad["needs_fresh_draft"] = reason == "inbound_reply"
    state.cadence = cad
    return state


def opted_out(state: Any) -> bool:
    """True when the lead row carries an opt-out marker (LeadState.opt_out).
    Any value counts, a malformed one included: it holds."""
    return bool(getattr(state, "opt_out", None))


def stop_reason(state: Any, now: datetime) -> Optional[str]:
    """Why the cadence must not continue, or None. Does not mutate."""
    cad = getattr(state, "cadence", None) or {}
    if cad.get("stopped_reason"):
        return cad["stopped_reason"]
    if not cad.get("armed_at"):
        return "not_armed"
    ended = terminal_reason(state)
    if ended:
        return ended
    # The baseline moves forward when an auto-responder pause is resumed, to that
    # auto-reply's own received time (resume_after_auto_reply), so the same
    # out-of-office mail does not stop the cadence again on the next tick while
    # a reply received after it still does.
    armed = _parse(cad.get("armed_at"))
    resumed = _parse(cad.get("resumed_after_auto_reply_at"))
    if resumed and (armed is None or resumed > armed):
        armed = resumed
    last_in = _parse(_field(state, "last_inbound_at"))
    if armed and last_in and last_in > armed:
        return "inbound_reply"
    return None


def terminal_reason(state: Any) -> Optional[str]:
    """Why this lead is done with the ladder whatever the ladder's own record
    says, or None: a booked call, an unsubscribe (a blocklisted lead
    included), a hostile, lost or wrong-person answer, a "not now", or the
    sticky opt-out marker. stop_reason's lead-side answers, in its order,
    without a newer reply (an approved answer to it re-arms the ladder, and an
    auto-reply pause resumes it). A stopped ladder offers no Resume to a lead
    this answers for (tick_lead). Does not mutate."""
    cad = getattr(state, "cadence", None) or {}
    if cad.get("booking"):
        return "booked"
    status = str(_field(state, "status", default="")).lower()
    label = str(_field(state, "last_label", "label", default="")).lower()
    cls = getattr(state, "classification", None)
    if cls is not None and getattr(cls, "label", None):
        label = label or str(cls.label).lower()
    for candidate in (status, label):
        if candidate in BOOKED_STATUSES:
            return "booked"
        if candidate in UNSUBSCRIBE_STATUSES:
            return "unsubscribe"
        if candidate in HOSTILE_STATUSES:
            return "hostile"
        if candidate in NOT_NOW_STATUSES:
            return "follow_up_later"
    # The sticky opt-out marker (LeadState.opt_out): the lead opted out or gave
    # a final no, and no later reply of their own took it back. It stops the
    # ladder whatever the status says, so the order replies were processed in
    # can never let a touch reach an opted-out lead.
    if opted_out(state):
        return "opt_out"
    return None


def _is_machine(label: Any) -> bool:
    """A history label that means a machine answered (an out-of-office, an
    unmonitored mailbox), not the lead. Anything else, a missing label
    included, is the lead's own reply."""
    return str(label or "").strip().lower() in AUTO_REPLY_STATUSES


def _last_stock_take(state: Any) -> Tuple[Optional[datetime], Optional[str], str]:
    """When the ladder last took stock of the thread, on the engine's own clock;
    the email id whose history entry marks what it had seen by then; and how:
    ``"armed"`` (an approved answer armed or re-armed it: armed_at, and the
    email that answer covered) or ``"resumed"`` (an auto-reply pause was
    resumed: auto_reply_seen_through, and the newest inbound it saw). A row
    resumed before auto_reply_seen_through existed has only
    resumed_after_auto_reply_at, which was the tick's own clock then."""
    cad = getattr(state, "cadence", None) or {}
    armed = _parse(cad.get("armed_at"))
    seen = _parse(cad.get("auto_reply_seen_through"))
    if seen is None and not cad.get("auto_reply_seen_through"):
        seen = _parse(cad.get("resumed_after_auto_reply_at"))
    if seen is not None and (armed is None or seen > armed):
        return seen, cad.get("auto_reply_seen_email_id"), "resumed"
    return armed, cad.get("armed_for_email_id"), "armed"


def _inbound_entries(state: Any) -> List[Dict[str, Any]]:
    """The lead's inbound history entries, without the stale ones: a reply the
    lead sent before their opt-out, or before a newer reply of theirs, was
    recorded only (router.stale_reason, app._record_stale_reply). It stops
    nothing and is no reply the ladder has to take stock of: the opt-out
    marker already holds the ladder (stop_reason), and the newer reply was
    taken stock of when it was processed."""
    return [e for e in list(getattr(state, "history", None) or [])
            if isinstance(e, dict) and e.get("event") == "inbound" and not e.get("stale")]


def inbounds_since_baseline(state: Any) -> List[Dict[str, Any]]:
    """Every inbound the ladder has not taken stock of, from the lead's history
    (oldest first; the history is in the order the engine finished processing
    them, since every writer only appends to it).

    That is everything processed after the last stock-take, by either measure:
    at or after its time (armed_at; for an auto-reply resume, after the newest
    inbound it saw), or written after the entry it marks (the email the
    approved answer covered; the newest inbound the resume saw). The second
    catches a reply whose pipeline started before the stock-take and wrote
    after it: its entry is stamped with the pipeline's start, yet nobody took
    stock of it. An entry without a readable time counts: it cannot be shown
    to be old. The email the approved answer covered never counts, even when
    a retry processed it again after the arm: that answer is its answer."""
    base, marker, how = _last_stock_take(state)
    entries = _inbound_entries(state)
    after_marker = set()  # type: set
    if marker:
        hits = [i for i, e in enumerate(entries) if str(e.get("email_id")) == str(marker)]
        if hits:
            # The FIRST entry for the marker: a retry that processed the same
            # email again appends a second entry for it, and measuring from
            # that one would skip a reply written between the two.
            after_marker = set(range(hits[0] + 1, len(entries)))
    out = []  # type: List[Dict[str, Any]]
    for i, entry in enumerate(entries):
        if how == "armed" and marker and str(entry.get("email_id")) == str(marker):
            continue
        at = _parse(entry.get("at"))
        if base is None or at is None or i in after_marker:
            out.append(entry)
        elif at > base or (how == "armed" and at == base):
            out.append(entry)
    return out


def human_reply_since_baseline(state: Any) -> Optional[str]:
    """The email id of a reply since the ladder's baseline that a machine did
    not write (by its history label), or None. That reply is the lead's, and
    nothing may go out on top of it until Lorenzo answers it."""
    for entry in inbounds_since_baseline(state):
        if not _is_machine(entry.get("label")):
            return str(entry.get("email_id") or "") or "unknown"
    return None


def is_auto_reply_pause(state: Any) -> bool:
    """True when the ladder is stopped for an inbound and every inbound since it
    last took stock of the thread was a machine's (an out-of-office, an
    unmonitored mailbox), by the label each one's history entry carries. Those
    produce no draft and no approval, so nothing would ever re-arm the lead:
    the cadence pauses and resumes itself instead of dying on a positive lead.
    An auto-responder answers EVERY message in a thread, so a second robot
    reply is as much a pause as the first.

    Never decided from the auto-reply's leftover ``cadence.reason``, the lead's
    status or only the newest label. Those said "robot" while the lead's own
    reply, sent after the robot's or just before it, waited on a pending card:
    the tick resumed the ladder over it and D2 and D3 went out. A human reply
    anywhere since the baseline keeps the ladder stopped (awaiting the fresh
    draft), and so does a stop nothing on the row explains."""
    cad = getattr(state, "cadence", None) or {}
    if cad.get("stopped_reason") != "inbound_reply":
        return False
    if opted_out(state):
        return False  # an opted-out lead's stop is never a pause to resume
    since = inbounds_since_baseline(state)
    return bool(since) and all(_is_machine(e.get("label")) for e in since)


def resume_after_auto_reply(state: Any, now: datetime) -> datetime:
    """Un-stop a cadence paused by an auto-responder and schedule the next touch
    for the business day after the stated return date (next business day when
    the auto-reply named none). The completed day is kept.

    The baseline moves to what the pause took stock of, never to the tick's own
    clock. ``resumed_after_auto_reply_at`` becomes the newest inbound's own
    received time (the auto-reply's: every inbound since the baseline was a
    machine's, or this would not be a pause), which stop_reason compares
    ``last_inbound_at`` with. ``auto_reply_seen_through`` and
    ``auto_reply_seen_email_id`` record the newest inbound it took stock of
    (when the engine processed it, and its entry in the history), which is
    what inbounds_since_baseline measures from. Stamped with the tick's clock,
    the baseline passed a reply the lead sent before the tick ran, and nothing
    ever stopped the ladder for it. The auto-reply's leftover ``reason`` goes
    with the pause."""
    ct = slot_rules.to_tz(now)
    cad = dict(state.cadence or {})
    resume_at = cad.get("resume_at") or _field(state, "resume_at", "ooo_until")
    target = None
    if resume_at:
        try:
            target = slot_rules.to_tz(slot_rules.parse_iso(str(resume_at)))
        except (ValueError, TypeError):
            target = None
    nxt = next_business_day_send(ct)
    if target is not None:
        from_return = cadence_send_time(roll_to_business_day(target.date()))
        if from_return > nxt:
            nxt = from_return
    entries = _inbound_entries(state)
    seen_times = [t for t in (_parse(e.get("at")) for e in entries) if t is not None]
    seen_through = max(seen_times) if seen_times else None
    received = _parse(_field(state, "last_inbound_at")) or seen_through or ct
    cad.update({
        "stopped_reason": None,
        "stopped_at": None,
        "needs_fresh_draft": False,
        "next_send_at": nxt.isoformat(),
        "resumed_after_auto_reply_at": received.isoformat(),
        "auto_reply_seen_through": (seen_through or received).isoformat(),
        "auto_reply_seen_email_id": (entries[-1].get("email_id") if entries else None),
        "stall_notified_at": None,
        # The held day's send moved to the return date: a D1 re-opens its
        # 30-minute Veto window with a fresh push instead of going out behind
        # the one sent before the auto-reply (resume_after_recipient_hold does
        # the same).
        "veto_notified_at": None,
    })
    cad.pop("paused", None)
    if str(cad.get("reason") or "").strip().lower() in AUTO_REPLY_STATUSES:
        cad.pop("reason", None)
    state.cadence = cad
    return nxt


def pending_day(state: Any) -> Optional[int]:
    cad = getattr(state, "cadence", None) or {}
    return next_day_number(int(cad.get("day") or 0))


def touched_today(state: Any, now: datetime) -> bool:
    today = slot_rules.to_tz(now).date()
    for t in (getattr(state, "cadence", None) or {}).get("touches") or []:
        sent = _parse(t.get("sent_at"))
        if sent and sent.date() == today:
            return True
    return False


def due(state: Any, now: datetime) -> bool:
    """True when a touch should go out now: armed, not stopped, next_send_at
    reached, business day, 10:00 <= CT hour < 19:00, no touch yet today."""
    if not is_armed(state) or stop_reason(state, now):
        return False
    ct = slot_rules.to_tz(now)
    if ct.weekday() >= 5 or not slot_rules.within_send_window(ct) or ct.hour < CADENCE_HOUR:
        return False
    nxt = _parse(state.cadence.get("next_send_at"))
    if nxt is None or nxt > ct:
        return False
    return not touched_today(state, ct)


def veto_notify_due(state: Any, now: datetime) -> bool:
    """D1 only: 30 minutes before the send, ping Lorenzo with a Veto action (live mode)."""
    if not is_armed(state) or stop_reason(state, now) or pending_day(state) != 1:
        return False
    cad = state.cadence
    if cad.get("veto_notified_at"):
        return False
    ct = slot_rules.to_tz(now)
    nxt = _parse(cad.get("next_send_at"))
    if nxt is None or ct.weekday() >= 5 or not slot_rules.within_send_window(ct):
        return False
    # 30 minutes before the send can REALLY happen: an overdue next_send_at
    # (a Resume on Friday at 18:45, a weekend) used to open the window at the
    # 07:00 tick, three hours before the 10:00 send.
    real = projected_send_time(max(slot_rules.to_tz(nxt), ct.replace(second=0, microsecond=0)))
    return ct >= real - timedelta(minutes=VETO_WINDOW_MINUTES)


# ------------------------------------------------------------- decisions
def veto_key(state: Any) -> str:
    return "veto:%s:%s" % (_field(state, "campaign_id", default="unknown"), _field(state, "lead_email"))


def approval_key(state: Any, item: str = "d6") -> str:
    return "approval:%s:%s:%s" % (_field(state, "campaign_id", default="unknown"), _field(state, "lead_email"), item)


def _decision_secret() -> str:
    return os.environ.get(DECISION_SECRET_ENV, "").strip()


def _decision_message(kind: str, state: Any, expires_at: str) -> bytes:
    cad = getattr(state, "cadence", None) or {}
    return "|".join([
        kind,
        str(_field(state, "campaign_id", default="unknown")),
        str(_field(state, "lead_email") or ""),
        str(cad.get("armed_at") or ""),
        expires_at,
    ]).encode("utf-8")


def make_decision_token(kind: str, state: Any, now: datetime, ttl_hours: int = DECISION_TTL_HOURS) -> str:
    """``<expires_at>.<hmac>`` bound to this kind, campaign, lead and armed_at.

    The card URL carries it so a third party who sees one notification cannot
    swap the email in the path and flip another lead's cadence. Empty when
    REPLY_ENGINE_SECRET is unset (nothing to sign with)."""
    secret = _decision_secret()
    if not secret:
        return ""
    expires_at = (slot_rules.to_tz(now) + timedelta(hours=ttl_hours)).isoformat()
    sig = hmac.new(secret.encode("utf-8"), _decision_message(kind, state, expires_at), hashlib.sha256).hexdigest()[:32]
    return "%s.%s" % (expires_at, sig)


def verify_decision_token(kind: str, state: Any, token: Optional[str], now: datetime) -> Optional[bool]:
    """True (valid), False (forged, expired, wrong lead, or missing once a
    secret exists), None (cannot tell: no secret is configured).

    "No secret configured" and "no token supplied" are different answers. Once
    REPLY_ENGINE_SECRET is set every card URL carries a token, so a request
    without one is not Lorenzo's tap: app.py already promises that such a
    decision "is recorded as unsigned and the tick will not act on it", and
    returning None here let a bare GET to /cadence/veto/<campaign>/<email> stop
    a positive lead's whole ladder. Those URLs are broadcast on a public ntfy
    topic, so the path is not a secret."""
    secret = _decision_secret()
    if not secret:
        return None
    if token is None or not str(token).strip():
        return False
    token = str(token)
    if "." not in token:
        return False
    expires_at, sig = token.rsplit(".", 1)
    expected = hmac.new(secret.encode("utf-8"), _decision_message(kind, state, expires_at), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(expected, sig):
        return False
    exp = _parse(expires_at)
    return bool(exp is not None and exp > slot_rules.to_tz(now))


def _decision_record(kind: str, state: Any, now: datetime, token: Optional[str], **extra: Any) -> Dict[str, Any]:
    cad = getattr(state, "cadence", None) or {}
    rec = {
        "ts": slot_rules.to_tz(now).isoformat(),
        "armed_at": cad.get("armed_at"),
        "day": pending_day(state),
        "token_ok": verify_decision_token(kind, state, token, now),
    }
    rec.update(extra)
    return rec


def record_veto(store: Any, state: Any, now: datetime, token: Optional[str] = None) -> Dict[str, Any]:
    """Called by the approval endpoint when Lorenzo taps Veto on the D1 card.
    Stamped with the run it belongs to: a veto never survives a re-arm."""
    rec = _decision_record("veto", state, now, token)
    store.set(veto_key(state), rec)
    return rec


def record_invite_decision(store: Any, state: Any, decision: str, now: datetime, token: Optional[str] = None) -> Dict[str, Any]:
    """Called by the approval endpoint for the D6 calendar invite: 'approve' | 'veto'."""
    kind = "approve" if decision == "approve" else "veto-invite"
    rec = _decision_record(kind, state, now, token, decision=decision)
    store.set(approval_key(state, "d6"), rec)
    return rec


def decision_is_current(record: Any, state: Any) -> bool:
    """A recorded decision governs this run only when its token verified (or
    could not be checked) and it was taken for the current armed_at."""
    if not isinstance(record, dict):
        return False
    if record.get("token_ok") is False:
        return False
    armed = (getattr(state, "cadence", None) or {}).get("armed_at")
    stamped = record.get("armed_at")
    if stamped and armed and stamped != armed:
        return False
    return True


def _log_job(status: str, detail: Dict[str, Any]) -> None:
    """A Job_Log row for a hold; never raises (the tick must not fail on it)."""
    try:
        from shared import job_log

        job_log.log_run("reply_engine.cadence", status, detail)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not write the %s job-log row: %s", status, exc)


def links_base_url() -> Optional[str]:
    """approval.base_url(), the one resolver every card link uses, or None
    when it has nothing a phone can reach and the process is live.

    This module used to read REPLY_ENGINE_BASE_URL alone and default to
    http://localhost:8000, while the deployment runbook sets BASE_URL: the D1
    auto-send would have gone out behind a Veto button that could not work.
    In shadow approval.base_url() logs the problem and answers the dev URL,
    and the cadence carries on exactly as before.
    """
    from services.reply_engine import approval as approval_mod

    try:
        return approval_mod.base_url()
    except approval_mod.ApprovalUndeliverable as exc:
        logger.error("no usable base URL for the cadence decision links: %s", exc)
        return None


def _decision_url(kind: str, state: Any, now: Optional[datetime] = None) -> str:
    """Raises approval.ApprovalUndeliverable in live when there is no usable
    base URL: callers check links_base_url() first and hold instead."""
    from services.reply_engine import approval as approval_mod

    base = approval_mod.base_url()
    url = "%s/cadence/%s/%s/%s" % (base, kind, quote(str(_field(state, "campaign_id", default="unknown"))),
                                   quote(str(_field(state, "lead_email"))))
    token = make_decision_token(kind, state, now) if now is not None else ""
    return "%s?%s" % (url, urlencode({"t": token})) if token else url


# ----------------------------------------------------------------- slots
def default_slot_grid(now: datetime, days: int = slot_rules.MAX_BUSINESS_DAYS + 1, step_minutes: int = GRID_STEP_MINUTES) -> List[str]:
    """Calendar-shaped fallback when GHL free-slots are unavailable (no token /
    shadow): every ``step_minutes`` between 12:00 and 18:00 CT from today
    onwards. candidate_slots applies the 4-hour rule, so today's late-afternoon
    times are offered when they still qualify. Marked slots_source='default_grid'
    on the touch so a live run can refuse to send unverified times."""
    ct = slot_rules.to_tz(now)
    out = []
    d = ct.date() - timedelta(days=1)
    made = 0
    while made < days:
        d = d + timedelta(days=1)
        if d.weekday() >= 5:
            continue
        made += 1
        minute = slot_rules.SLOT_WINDOW[0] * 60
        while minute + SLOT_MINUTES <= slot_rules.SLOT_WINDOW[1] * 60:
            out.append(TZ.localize(datetime(d.year, d.month, d.day, minute // 60, minute % 60)).isoformat())
            minute += step_minutes
    return out


def parse_free_slots(resp: Any) -> List[str]:
    """Flatten a GHL free-slots response ({date: {slots: [...]}} or {_dates_: {...}}) to ISO strings."""
    if not resp:
        return []
    if isinstance(resp, list):
        return [str(x) for x in resp]
    if not isinstance(resp, dict):
        return []
    body = resp.get("_dates_") if isinstance(resp.get("_dates_"), dict) else resp
    out = []
    for key, val in body.items():
        if key in ("traceId", "_dates_"):
            continue
        if isinstance(val, dict) and isinstance(val.get("slots"), list):
            out.extend(str(s) for s in val["slots"])
        elif isinstance(val, list):
            out.extend(str(s) for s in val)
    return out


def resolve_free_slots(ghl: Any, now: datetime) -> Tuple[List[str], str]:
    """GHL Discovery Call free slots for the next horizon, else the default grid."""
    if ghl is None or not getattr(ghl, "has_token", False):
        return default_slot_grid(now), "default_grid"
    ct = slot_rules.to_tz(now)
    end = slot_rules.business_days_ahead(ct, slot_rules.MAX_BUSINESS_DAYS + 1)
    try:
        resp = ghl.get_free_slots(getattr(ghl, "calendar_id", None), int(ct.timestamp() * 1000), int(end.timestamp() * 1000))
    except Exception as exc:  # noqa: BLE001 - never let a calendar hiccup crash the tick
        logger.warning("get_free_slots failed: %s", exc)
        resp = None
    parsed = parse_free_slots(resp)
    if not parsed:
        return default_slot_grid(now), "default_grid"
    return parsed, "ghl"


def offered_key(now: datetime) -> str:
    """Per-day audit trail of what went out that day (not the reservation)."""
    return "offered:%s" % slot_rules.to_tz(now).date().isoformat()


def outstanding_offers(store: Any, now: datetime, lead_email: Optional[str] = None) -> List[str]:
    """Every slot still ahead of us that has been offered to anyone, whichever
    day the offer was made. Reads the same registry approval.py writes, so the
    day-0 draft's two slots are covered too.

    Keyed on the slot, not on the offer date: lead A's Monday touch and lead B's
    Tuesday touch can no longer land on the same Thursday 12:00."""
    if store is None:
        return []
    try:
        rows = store.get(OFFERED_REGISTRY_KEY, []) or []
    except Exception as exc:  # noqa: BLE001 - a store hiccup must not double-book the calendar
        logger.warning("could not read %s: %s", OFFERED_REGISTRY_KEY, exc)
        return []
    ct = slot_rules.to_tz(now)
    out = []
    for row in rows:
        iso = row.get("slot") if isinstance(row, dict) else row
        if not iso:
            continue
        if lead_email and isinstance(row, dict) and str(row.get("lead") or "").lower() == str(lead_email).lower():
            continue
        dt = _parse(iso)
        if dt is None or dt < ct:  # expired: the slot is in the past, it can be reused
            continue
        out.append(dt.isoformat())
    return out


def fresh_slots(state: Any, now: datetime, free_slots: List[Any], store: Any = None, count: int = 2) -> List[datetime]:
    """Compliant slots not yet offered to this lead nor outstanding for anyone else."""
    exclude = list(getattr(state, "offered_slots", None) or [])
    if store is not None:
        exclude.extend(outstanding_offers(store, now))
        exclude.extend(store.get(offered_key(now), []) or [])
    cands = slot_rules.candidate_slots(free_slots, now, already_offered=exclude)
    two = slot_rules.pick_two(cands)
    return two[:count]


def reserve_slots(state: Any, two: List[Any], now: datetime, store: Any = None, day: Optional[int] = None) -> List[str]:
    """Hold these slots against every lead until they are in the past.

    Idempotent on (slot, lead, day): the recovery path replays the slots a dead
    tick already offered, and a replay must not append the same reservation
    twice or inflate the per-day audit trail."""
    isos = [_iso(s if isinstance(s, datetime) else slot_rules.parse_iso(s)) for s in (two or [])]
    offered = list(getattr(state, "offered_slots", None) or [])
    state.offered_slots = offered + [s for s in isos if s not in offered]
    if store is not None:
        ct = slot_rules.to_tz(now)
        lead = _field(state, "lead_email")
        try:
            rows = store.get(OFFERED_REGISTRY_KEY, []) or []
        except Exception as exc:  # noqa: BLE001 - a store hiccup must not lose the reservation
            logger.warning("could not read %s: %s", OFFERED_REGISTRY_KEY, exc)
            rows = []
        held = set()
        for r in rows:
            if isinstance(r, dict):
                held.add((r.get("slot"), r.get("lead"), r.get("day")))
        for s in isos:
            # Already held: the pre-send claim (tick_lead, SAL-10) or a replay
            # wrote the registry row. The audit trail below is still recorded.
            if (s, lead, day) not in held:
                store.append(OFFERED_REGISTRY_KEY, {"slot": s, "lead": lead, "at": ct.isoformat(),
                                                    "source": "cadence", "day": day})
            # add_once, not append: the audit trail is a list of iso strings, so
            # a replayed day would otherwise record the same slot twice.
            try:
                store.add_once(offered_key(now), s)
            except AttributeError:
                store.append(offered_key(now), s)
    return isos


# ------------------------------------------------------------------ copy
def _load_template(name: str) -> str:
    path = PROMPTS_DIR / ("cadence_%s.md" % name)
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"^\s*<!--.*?-->\s*", "", text, count=1, flags=re.S)
    return text.strip() + "\n"


class _Safe(dict):
    """A missing value leaves the placeholder in place instead of silently
    rendering an empty sentence ("here are two new ones: ."), so
    copy_problems() flags it as unfilled_placeholder and the touch is blocked."""

    def __missing__(self, key):
        return "{%s}" % key


def render(template_name: str, **values: Any) -> str:
    return _load_template(template_name).format_map(_Safe(values)).rstrip() + "\n"


# The body a slot day takes when there is no free slot to offer. tick_lead
# never sends one (it skips a touch with fewer than two slots), but
# build_touch renders it and the catalogue shows it as the day's no_slots
# variant, which Lorenzo approves word for word. So each one reads as its own
# email and names no open time: it points at the booking link only. Splicing a
# stand-in phrase into {slots} gave "any afternoon this week open this week".
NO_SLOTS_BODIES = {
    "d1": "Hey {first_name},\n\n"
          "In case the first times did not suit, grab any open time that works for you here: {booking_url}\n\n"
          "Lorenzo\n",
    "d2": "Hey {first_name},\n\n"
          "{research_line}\n\n"
          "Fifteen minutes is enough for me to show you how this would run for {company}. "
          "Grab any open time here: {booking_url}\n\n"
          "Lorenzo\n",
    "d3": "Hey {first_name},\n\n"
          "If none of those times worked, pick whatever suits you here: {booking_url}\n\n"
          "Lorenzo\n",
    "d4": "Hey {first_name},\n\n"
          "Quick bit of context on why I keep nudging. {case_study}\n\n"
          "Happy to walk through what that would look like for {company}. Grab any open time here: {booking_url}\n\n"
          "Lorenzo\n",
    "d5": "Hey {first_name},\n\n"
          "{free_work}\n\n"
          "Happy to walk through it together. Grab any open time here: {booking_url}\n\n"
          "Lorenzo\n",
    "d6_noinvite": "Hey {first_name},\n\n"
                   "If a 15-minute walkthrough would help, grab any open time here: {booking_url}\n\n"
                   "Lorenzo\n",
    "d14": "Hey {first_name},\n\n"
           "Circling back in case the timing is better now. Grab any open time here: {booking_url}\n\n"
           "Lorenzo\n",
    "d30": "Hey {first_name},\n\n"
           "Last one from me for a while. If {company} still wants a look, grab any open time here: {booking_url}\n\n"
           "If not, I will leave it here and check back in a few months.\n\n"
           "Lorenzo\n",
}  # type: Dict[str, str]


def render_day(template_name: str, has_slots: bool, **values: Any) -> str:
    """render() for a day with two slots, NO_SLOTS_BODIES without one."""
    if has_slots or template_name not in NO_SLOTS_BODIES:
        return render(template_name, **values)
    return NO_SLOTS_BODIES[template_name].format_map(_Safe(values)).rstrip() + "\n"


def sanitize_line(text: str) -> str:
    text = (text or "").strip().strip('"').strip()
    text = text.replace("\u2014", ",").replace("\u2013", ",").replace("!", ".")
    text = re.sub(r"\s+", " ", text)
    return text


def case_study_line(offer: str) -> str:
    """Verbatim proof line for the offer type, parsed from config/offers.md."""
    want = "Outbound / trigger" if offer == "outbound" else "Reactivation"
    for line in (settings.OFFERS_MD or "").splitlines():
        if line.startswith("| %s |" % want):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2:
                return cells[1].strip().strip('"')
    return _FALLBACK_PROOF["outbound" if offer == "outbound" else "reactivation"]


def free_work_line(niche: str, company: str, specialty: Optional[str] = None, offer: str = "outbound") -> str:
    """The D5 sample of work. It must match the mechanism the lead was pitched
    (config/offers.md): a reactivation prospect is working their own dormant
    list, so offering them brand-new business formations or fresh job posts
    mixes two offers and reads like a different pitch."""
    niche = (niche or "").lower()
    offer = (offer or "outbound").lower()
    # Outbound lines offer to pull a list; they never say one was pulled. The
    # touch goes out on a timer, and nobody built a list for this lead.
    if offer == "reactivation":
        if niche == "bookkeeping":
            return ("I can draft the first two emails for the clients %s lost or quoted and never closed. "
                    "Want to see them?" % company)
        if niche == "recruiting":
            return ("I can draft the first two emails for the clients %s made one placement for and never heard "
                    "from again. Want to see them?" % company)
        return ("I can draft the first two emails for the accounts %s lost or bid on and never closed. "
                "Want to see them?" % company)
    if niche == "bookkeeping":
        return ("I can pull the businesses in your area that just formed or posted a part-time bookkeeper role "
                "this month. Want the list?")
    if niche == "recruiting":
        what = "%s roles" % specialty if specialty else "roles in your specialty"
        return ("I can pull the %s that opened this week in your market, with the hiring manager for each. "
                "Want the list?" % what)
    if niche in ("cleaning", "commercial_cleaning", "janitorial"):
        # offers.md defines cleaning_trigger as "new leases, office expansions, PM
        # changes, new construction". Lost bids are the *reactivation* mechanism,
        # and the sheet says the two sets are never mixed. They also cannot be
        # derived from a prospect's reviews and Maps listing.
        return ("I can pull the buildings in your area that just signed a new lease, expanded, or changed "
                "property managers this month. Want the list?")
    # Unknown niche: say nothing about a mechanism we have not defined for it.
    return "I can put together a short sample of the first two emails I would send for %s. Want to see it?" % company


def generate_research_line(state: Any, facts: Optional[Dict[str, Any]] = None) -> str:
    """One researched sentence via shared.llm role 'research' (faked with LLM_FAKE=1)."""
    niche, offer = niche_and_offer(state)
    company = company_of(state)
    payload = {
        "company": company,
        "website": _field(state, "website"),
        "niche": niche,
        "offer": offer,
        "first_name": first_name_of(state),
    }
    payload.update(facts or {})
    system = _load_template("research")
    try:
        out = llm.complete("research", system, json.dumps(payload, ensure_ascii=False), max_tokens=120)
    except Exception as exc:  # noqa: BLE001 - a research hiccup must not block the day-2 touch
        logger.warning("research line failed: %s", exc)
        out = ""
    out = out if isinstance(out, str) else ""
    if not out or out.startswith("FAKE[") or len(out) > 240:
        out = fallback_research_line(company, offer)
    return sanitize_line(out)


def fallback_research_line(company: str, offer: str) -> str:
    """What D2 says when the model gave nothing.

    It must not open "I had a look at {company}": the whole point of the D2
    prompt is a line that shows Lorenzo looked at their business, and the
    fallback fires on every LLM error and in every LLM_FAKE dry run, so that
    sentence asserted research nobody did in exactly the preview Lorenzo
    reviews. It also has to match the offer: "the quiet accounts on your list"
    is the reactivation pitch and lands on an outbound prospect who has no
    dormant list.

    It stops at one clause: the D2 body goes straight on to "Fifteen minutes
    is enough for me to show you how this would run for {company}", so a
    second "fifteen minutes" clause here said it twice. ``company`` is kept in
    the signature for callers; the line no longer names it (the body does)."""
    if (offer or "").lower() == "reactivation":
        return "The quickest place to start is usually the accounts that already know you and went quiet."
    return "The quickest place to start is usually the prospects who are in market right now."


research_line_for = generate_research_line


# ------------------------------------------------------ template ids (CT3)
# Builders return pure id strings and never touch the catalogue: the catalogue
# is itself rendered through build_touch, so a hash lookup here would recurse.
# tick_lead stamps the hashes (template_gate.stamp) outside builder code.
FREE_WORK_CLEANING_NICHES = ("cleaning", "commercial_cleaning", "janitorial")


def _offer_branch(offer: Optional[str]) -> str:
    """The two offer branches every cadence line is written for (case_study_line
    and free_work_line treat anything that is not reactivation as outbound)."""
    return "reactivation" if (offer or "").strip().lower() == "reactivation" else "outbound"


def free_work_template_id(niche: Optional[str], offer: Optional[str], specialty: Optional[str] = None) -> str:
    """cadence.d5.free_work.<niche>_<offer>[_specialty], following the branches
    of free_work_line (an unnamed niche is 'generic')."""
    niche = (niche or "").strip().lower()
    branch = _offer_branch(offer)
    if niche in ("bookkeeping", "recruiting"):
        key = niche
    elif niche in FREE_WORK_CLEANING_NICHES:
        key = "cleaning"
    else:
        key = "generic"
    suffix = "_specialty" if (key == "recruiting" and branch == "outbound" and specialty) else ""
    return "cadence.d5.free_work.%s_%s%s" % (key, branch, suffix)


def touch_template_ids(day: int, state: Any, invite_created: bool = True, research_source: str = "fallback",
                       has_slots: bool = True) -> Tuple[str, List[str]]:
    """(main id, part ids) of the cadence touch build_touch renders for
    ``day``. ``research_source`` is "fallback" when day 2 carries the fixed
    fallback line, anything else for a line the model wrote (that part,
    cadence.d2.research_line, can never be approved). Day 6 is the no-invite
    body whenever there is no invite or no slot to hold (flag 11)."""
    niche, offer = niche_and_offer(state)
    parts = []  # type: List[str]
    if day == 6:
        main = "cadence.d6" if (invite_created and has_slots) else "cadence.d6_noinvite"
    else:
        main = "cadence.d%d" % day
    if day == 2:
        if research_source == "fallback":
            parts.append("cadence.d2.research_fallback.%s" % _offer_branch(offer))
        else:
            parts.append("cadence.d2.research_line")
    elif day == 4:
        parts.append("cadence.d4.case_study.%s" % _offer_branch(offer))
    elif day == 5:
        parts.append(free_work_template_id(niche, offer, _field(state, "specialty")))
    return main, parts


def build_touch(state: Any, day: int, slots: List[Any], research_line: Optional[str] = None,
                invite_created: bool = True, slots_source: str = "provided",
                research_mode: Optional[str] = None) -> Touch:
    """Subject 'Re: ...' + body for cadence day 1..7, 14, 30.

    ``slots`` are the two fresh slots (datetime or ISO, CT). ``research_line``
    overrides day 2's line. Without it, ``research_mode`` (default
    D2_RESEARCH_MODE, "fallback") picks the fixed fallback line, or "llm" asks
    shared.llm role "research" first. For day 6 ``invite_created=False`` (or
    no slot) renders the no-invite fallback body. The touch carries the
    template ids it was rendered from (touch_template_ids), unstamped."""
    if day not in INTENTS:
        raise ValueError("cadence day must be one of %s, got %r" % (DAY_SEQUENCE, day))
    two = [slot_rules.to_tz(slot_rules.parse_iso(s)) for s in (slots or [])][:2]
    isos = [s.isoformat() for s in two]
    niche, offer = niche_and_offer(state)
    first = first_name_of(state)
    company = company_of(state)
    booking_url = DEFAULT_BOOKING_URL
    has_slots = bool(two)
    # Without a slot the day renders its NO_SLOTS_BODIES text, which has no
    # {slots}; if one ever did, _Safe leaves "{slots}" and the copy gate blocks it.
    slot_values = {"slots": slot_rules.format_slots(two)} if two else {}  # type: Dict[str, Any]
    slot1 = slot_rules.format_slots(two[:1]) if two else "an afternoon this week"
    # d6 with one slot: "If another time is better, say the word and I will
    # move it." It names no afternoon Lorenzo has not checked.
    slot2 = slot_rules.format_slots(two[1:2]) if len(two) > 1 else "another time"
    meta = {"niche": niche, "offer": offer}  # type: Dict[str, Any]
    requires_approval = False
    channel_note = None
    line = research_line
    research_source = "fallback"

    if day == 2:
        mode = research_mode or D2_RESEARCH_MODE
        fallback = fallback_research_line(company, offer)
        if line:
            line = sanitize_line(line)
        elif mode == "llm":
            line = generate_research_line(state)
        else:
            line = fallback
        research_source = "fallback" if line in (fallback, sanitize_line(fallback)) else "llm"
        meta["research_line"] = line
        meta["research_source"] = research_source
        body = render_day("d2", has_slots, first_name=first, company=company, research_line=line,
                          booking_url=booking_url, **slot_values)
    elif day == 4:
        case = case_study_line(offer)
        meta["case_study"] = case
        body = render_day("d4", has_slots, first_name=first, company=company, case_study=case,
                          booking_url=booking_url, **slot_values)
    elif day == 5:
        fw = free_work_line(niche, company, _field(state, "specialty"), offer=offer)
        meta["free_work"] = fw
        body = render_day("d5", has_slots, first_name=first, free_work=fw, booking_url=booking_url, **slot_values)
    elif day == 6:
        requires_approval = True
        if invite_created and two:
            body = render("d6", first_name=first, slot1=slot1, slot2=slot2, booking_url=booking_url)
            meta["invite_slot"] = isos[0]
        else:
            body = render_day("d6_noinvite", has_slots, first_name=first, booking_url=booking_url, **slot_values)
            meta["invite_slot"] = None
        phone = _field(state, "phone")
        if phone:
            channel_note = ("Second channel (manual until A2P clears): text %s: 'Hey %s, Lorenzo here. Put a hold on your calendar for %s, "
                            "shout if another day is better.'" % (phone, first, slot1))
        else:
            channel_note = "Second channel: no phone on file; a LinkedIn note is optional."
    elif day == 7:
        body = render("d7", first_name=first)
        isos = []
    elif day == 14:
        body = render_day("d14", has_slots, first_name=first, booking_url=booking_url, **slot_values)
    elif day == 30:
        body = render_day("d30", has_slots, first_name=first, company=company, booking_url=booking_url,
                          **slot_values)
    else:  # 1 and 3
        body = render_day("d%d" % day, has_slots, first_name=first, booking_url=booking_url, **slot_values)

    template_id, parts = touch_template_ids(day, state, invite_created=invite_created,
                                            research_source=research_source, has_slots=bool(two))
    return Touch(
        day=day,
        intent=INTENTS[day],
        subject=subject_for(state),
        body_text=body,
        slots=isos,
        requires_approval=requires_approval,
        channel_note=channel_note,
        slots_source=slots_source,
        meta=meta,
        # Only the prose is judged by the copy gate: "Automation Depot" is the
        # prospect's own name, not a copy failure, and blocking on it used to lose
        # that lead every day from D2 onwards.
        allow_terms=[company, first],
        # ... and the copy gate needs to know whose offer sheet row this is, or
        # another vertical's guarantee reads as a number that "exists in offers.md".
        campaign_key=campaign_key_of(state),
        template_id=template_id,
        template_parts=dict((p, None) for p in parts),
    )


def touch_bindings(state: Any, touch: Touch) -> Dict[str, str]:
    """What build_touch actually put into each placeholder of ``touch``, for
    template_gate's conformance check (flag 13): the captured value must
    equal it. The slot placeholders are bound to the slots the touch offers,
    so a body naming other times never conforms. Only values that were
    rendered are bound (no slots, no binding for them)."""
    out = {
        "first_name": first_name_of(state),
        "company": company_of(state),
        "booking_url": DEFAULT_BOOKING_URL,
    }  # type: Dict[str, Any]
    specialty = _field(state, "specialty")
    if specialty:
        out["specialty"] = str(specialty)
    core = normalize_subject(_field(state, "last_subject", "subject", "thread_subject"))
    if core and not _AUTO_ANYWHERE_RE.search(core):
        out["original_subject"] = core
    two = []  # type: List[datetime]
    for iso in touch.slots or []:
        try:
            two.append(slot_rules.to_tz(slot_rules.parse_iso(iso)))
        except (ValueError, TypeError):
            continue
    two = two[:2]
    if two:
        out["slots"] = slot_rules.format_slots(two)
        out["slot1"] = slot_rules.format_slots(two[:1])
        if len(two) > 1:
            out["slot2"] = slot_rules.format_slots(two[1:2])
    return dict((k, str(v)) for k, v in out.items() if v not in (None, ""))


# ------------------------------------------------------ template gate (CT3)
class _GateUnavailable(object):
    """A failed verdict for when template_gate itself could not be asked."""

    def __init__(self, template_id: Optional[str], parts: Any, error: str) -> None:
        self.allowed = False
        self.reason = "registry_error"
        self.template_id = template_id
        self.ids = ([template_id] if template_id else []) + [p for p in (parts or []) if p]
        self.statuses = {}  # type: Dict[str, str]
        self.detail = error

    def to_record(self) -> Dict[str, Any]:
        return {"allowed": False, "reason": self.reason, "template_id": self.template_id,
                "ids": list(self.ids), "statuses": {}}


def _template_ids_verdict(template_id: Optional[str], parts: Any = ()) -> Any:
    """template_gate.ids_verdict, failing closed on any error."""
    try:
        from services.reply_engine import template_gate

        return template_gate.ids_verdict(template_id, list(parts or ()))
    except Exception as exc:  # noqa: BLE001 - a gate that cannot answer holds the day
        logger.warning("template pre-check failed closed for %s: %s", template_id, type(exc).__name__)
        return _GateUnavailable(template_id, parts, type(exc).__name__)


def _template_touch_verdict(state: Any, touch: Touch) -> Any:
    """Stamp ``touch`` with the catalogue hashes of its ids, then the full
    template_gate.touch_verdict on its exact subject and body, with the
    placeholders bound to what was rendered. Fails closed."""
    parts = list((touch.template_parts or {}).keys())
    try:
        from services.reply_engine import template_gate

        template_gate.stamp(touch, touch.template_id, parts)
        return template_gate.touch_verdict(touch, bindings=touch_bindings(state, touch))
    except Exception as exc:  # noqa: BLE001 - a gate that cannot answer holds the day
        logger.warning("template gate failed closed for %s: %s", touch.template_id, type(exc).__name__)
        return _GateUnavailable(touch.template_id, parts, type(exc).__name__)


def business_days_between(start: date, end: date) -> int:
    """Weekdays d with start < d <= end."""
    n = 0
    d = start
    while d < end:
        d = d + timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


# -------------------------------------------------------------- sending
def recipient_for(state: Any) -> Optional[str]:
    """The address that actually wrote the thread, which is not always the CRM
    address the state is keyed on.

    models.ReplyEvent already carries it (``reply_from`` /
    ``reply_to_address``: "what instantly.reply_to_email must use as `to`"), and
    approval.py sends the first reply to it. A positive lead whose reply came
    from a shared or assistant mailbox used to get the first reply and then none
    of the nine touches, because every touch was addressed to ``lead_email``.
    ``cadence['reply_from']`` is the cadence's own copy, seeded at arm time, so
    the ladder keeps working on a state written before LeadState carried the
    field. ``lead_email`` stays the store key either way."""
    cad = getattr(state, "cadence", None) or {}
    for value in (_field(state, "reply_from", "reply_to_address"), cad.get("reply_from")):
        if value:
            return str(value).strip()
    return _field(state, "lead_email")


def thread_recipient_ok(state: Any, instantly: Any) -> Optional[bool]:
    """Does the thread we are about to reply into actually belong to this lead?

    True / False / None (cannot tell). This is the compensating control
    config/instantly_api_contract.md asks for: re-read the email by id and
    compare ``from_address_email`` with the lead we mean to answer. It is a
    read, so it is safe against live data, and it holds even if Instantly ever
    ignores the ``to`` validation field."""
    reply_to = _field(state, "last_email_id", "reply_to_uuid", "email_id")
    recipient = recipient_for(state)
    if instantly is None or not reply_to or not recipient or not hasattr(instantly, "get_email"):
        return None
    try:
        email = instantly.get_email(reply_to)
    except Exception as exc:  # noqa: BLE001 - a read hiccup must not block the touch
        logger.warning("could not re-read %s: %s", reply_to, exc)
        return None
    sender = (email or {}).get("from_address_email") if isinstance(email, dict) else None
    if not sender:
        return None
    return str(sender).strip().lower() == str(recipient).strip().lower()


def _send(state: Any, touch: Touch, instantly: Any, now: datetime) -> Dict[str, Any]:
    """Reply in the original thread through Instantly (guarded).

    ``to`` is the recipient guard: Instantly validates it against the thread and
    refuses the send if ``reply_to_uuid`` points at a message from somebody else
    (a colleague or assistant who replied on the thread, a replayed state that
    carries another thread's id). Nine unattended touches ride this path, so it
    is never omitted and ``skip_validation`` stays off."""
    reply_to = _field(state, "last_email_id", "reply_to_uuid", "email_id")
    eaccount = _field(state, "eaccount")
    lead_email = _field(state, "lead_email")
    recipient = recipient_for(state)
    payload = {
        "reply_to_uuid": reply_to,
        "eaccount": eaccount,
        "to": recipient,
        "subject": touch.subject,
        "body": {"text": touch.body_text},
        "cadence_day": touch.day,
        "lead_email": lead_email,
    }
    if instantly is None or not reply_to or not eaccount or not recipient:
        rec = guard_write("instantly", "reply_to_email", payload)
        if not reply_to or not eaccount:
            rec["skipped"] = "missing_thread_ids"
        elif not recipient:
            rec["skipped"] = "missing_recipient"
        else:
            rec["skipped"] = "no_instantly_client"
        # A state that cannot address a reply is broken in either mode; having no
        # client at all is normal in shadow (the record is the deliverable) and a
        # failure in live.
        if rec["skipped"] != "no_instantly_client" or not rec.get("shadow"):
            rec["error"] = rec["skipped"]
        return rec
    if is_live():
        # Decision R6: a live touch goes out only on a CONFIRMED match. A read
        # error, a timeout or a thread with no readable sender used to count
        # as "cannot tell" and let the send through, which disarmed the
        # second recipient belt exactly when it could not look.
        verdict = thread_recipient_ok(state, instantly)
        if verdict is False:
            logger.error("refusing D%d to %s: the thread's last inbound is from somebody else", touch.day, recipient)
            return {"shadow": False, "error": "recipient_mismatch", "payload": payload}
        if verdict is not True:
            logger.error("holding D%d to %s: the thread could not be re-read to confirm the recipient",
                         touch.day, recipient)
            return {"shadow": False, "error": "recipient_unconfirmed", "payload": payload}
    try:
        result = instantly.reply_to_email(reply_to, eaccount, touch.subject, touch.body_text, to=recipient)
    except Exception as exc:  # noqa: BLE001 - a send failure must never look like a send
        logger.warning("reply_to_email failed for %s: %s", recipient, exc)
        return {"shadow": False, "error": "send_failed: %s" % exc, "payload": payload}
    if isinstance(result, dict) and "shadow" in result:
        return result  # guard record (shadow)
    if result is None:
        return {"shadow": False, "error": "no_response_from_instantly", "payload": payload}
    live = {"shadow": False, "result": result}
    if isinstance(result, dict) and result.get("id"):
        live["id"] = result["id"]
    return live


def send_failed(result: Any) -> Optional[str]:
    """The reason a send did not happen, or None when it did.

    A shadow guard record is a success (the intent is recorded). In live a
    record carrying error/skipped, or no response at all, is a failure: the day
    must not advance and the digest must say so, otherwise a lead whose state
    lost its eaccount burns the whole nine-touch ladder in silence."""
    if not isinstance(result, dict):
        return "unknown_response"
    if result.get("error"):
        return str(result["error"])
    if result.get("shadow"):
        return None  # would_do: the intent is the deliverable in shadow
    if result.get("skipped"):
        return str(result["skipped"])
    if result.get("shadow") is None and "result" not in result:
        return "unknown_response"
    if result.get("result") in (None, False):
        return "empty_response"
    return None


# Refusals decided *before* the POST is issued: nothing left the process, so the
# idempotency marker can be dropped and the day retried. Everything else (an
# exception, an HTTP failure) means the request WAS issued, and
# shared/instantly.py deliberately does not retry a write that never got an
# answer because "a write that never got an answer may still have been
# accepted". Deleting the marker for those re-sent the identical body into the
# same thread on the next hourly tick.
PRE_SEND_REFUSALS = ("missing_thread_ids", "missing_recipient", "no_instantly_client", "recipient_mismatch",
                     "recipient_unconfirmed")
# A touch held because the recipient re-read could not confirm the lead is
# retried on the next ticks (the marker is dropped: nothing left the process).
# After this many consecutive holds of the same day it escalates and the
# ladder stays stopped until Lorenzo re-arms it.
RECIPIENT_HOLD_MAX_ATTEMPTS = 3


def nothing_left_the_process(reason: Optional[str]) -> bool:
    """True when the refusal proves no request was issued."""
    if not reason:
        return True
    return str(reason).split(":")[0].strip() in PRE_SEND_REFUSALS


def _record_touch(state: Any, touch: Touch, now: datetime, result: Dict[str, Any], kind: str) -> Dict[str, Any]:
    ct = slot_rules.to_tz(now)
    cad = dict(state.cadence or {})
    rec = {
        "day": touch.day,
        "intent": touch.intent,
        "sent_at": ct.isoformat(),
        "kind": kind,  # would_do | done | skipped
        "subject": touch.subject,
        "slots": list(touch.slots),
        "slots_source": touch.slots_source,
        "requires_approval": touch.requires_approval,
        "channel_note": touch.channel_note,
        "shadow": bool(result.get("shadow", True)),
        "result_id": (result.get("id") if isinstance(result, dict) else None),
        "problems": touch.problems,
    }
    touches = list(cad.get("touches") or [])
    touches.append(rec)
    cad["touches"] = touches
    cad["day"] = touch.day
    nxt = schedule_after(touch.day, ct)
    cad["next_send_at"] = nxt.isoformat() if nxt else None
    state.cadence = cad
    state.last_outbound_at = ct.isoformat()
    if nxt is None:
        stop(state, "exhausted", ct)
    return rec


def touch_marker_key(state: Any, day: int) -> str:
    """Idempotency marker, written *before* the send and scoped to this run.

    If the process dies between Instantly accepting the POST and the store
    write, the next tick finds the marker and repairs the state instead of
    sending the same day a second time."""
    cad = getattr(state, "cadence", None) or {}
    return "touch:%s:%s:%s:%s" % (_field(state, "campaign_id", default="unknown"), _field(state, "lead_email"),
                                  cad.get("armed_at") or "unarmed", day)


def _repair_from_marker(state: Any, day: int, marker: Dict[str, Any], now: datetime, store: Any = None) -> Dict[str, Any]:
    """The touch went out on an earlier tick but the state never got written.

    The slots in the marker were emailed to the lead, so they are re-reserved
    here: a repaired state has to be indistinguishable from a clean one. Without
    it the registry stayed empty, the same Thursday 12:00 was offered to a
    second prospect, and the next day's body said "those times went" while
    re-offering one of them."""
    ct = slot_rules.to_tz(now)
    sent_at = _parse(marker.get("ts")) or ct
    cad = dict(state.cadence or {})
    touches = list(cad.get("touches") or [])
    rec = {
        "day": day,
        "intent": INTENTS.get(day, "unknown"),
        "sent_at": sent_at.isoformat(),
        "kind": marker.get("kind") or "done",
        "subject": marker.get("subject"),
        "slots": list(marker.get("slots") or []),
        "slots_source": marker.get("slots_source"),
        "requires_approval": bool(marker.get("requires_approval")),
        "channel_note": None,
        "shadow": bool(marker.get("shadow", False)),
        "result_id": marker.get("result_id"),
        "problems": [],
        "recovered_from_marker": True,
    }
    touches.append(rec)
    cad["touches"] = touches
    cad["day"] = day
    nxt = schedule_after(day, sent_at)
    cad["next_send_at"] = nxt.isoformat() if nxt else None
    state.cadence = cad
    try:
        reserve_slots(state, list(marker.get("slots") or []), sent_at, store, day=day)
    except Exception as exc:  # noqa: BLE001 - a registry hiccup must not lose the repair
        logger.warning("could not re-reserve the repaired slots for D%d: %s", day, exc)
    if nxt is None:
        stop(state, "exhausted", ct)
    return rec


def move_to_follow_up_later(state: Any, ghl: Any, now: datetime, reason: str = "follow_up_later") -> Dict[str, Any]:
    """Stop the cadence, then move the GHL stage to Follow Up Later (guarded).

    The stop comes first on purpose. With no GHL Private Integration token the
    write raises, and when stop() sat after it the lead was left un-stopped:
    every daily tick hit the same GHLError, recorded action='error' with
    stopped_reason still None, and the digest carried the identical failure for
    ever. The pipeline move is the part that may fail; halting the cadence is
    not. The GHL error is returned on the record so the caller can surface it."""
    stop(state, reason, now)
    stage = settings.GHL_STAGES.get("follow_up_later")
    opp = _field(state, "ghl_opportunity_id")
    try:
        if ghl is not None and opp and stage:
            rec = ghl.update_opportunity_stage(opp, stage) or {}
        else:
            rec = guard_write("ghl", "update_opportunity_stage",
                              {"opportunity_id": opp, "stage_id": stage, "note": "no ghl client or opportunity id"})
    except Exception as exc:  # noqa: BLE001 - the cadence is already stopped; surface, never loop
        logger.warning("Follow Up Later move failed for %s: %s", _field(state, "lead_email"), exc)
        return {"error": "follow_up_later: %s" % exc, "opportunity_id": opp, "stage_id": stage}
    return rec if isinstance(rec, dict) else {"result": rec}


# How many consecutive days a slot-bearing touch may be skipped (no slots, or an
# unverifiable slot source) before the ladder is stopped rather than left to
# look like it is still running.
SKIP_STALL_DAYS = 2
# How many days in a row the copy gate may refuse the same day before it is
# parked. The gate itself never sends; the failure mode is a silent stall plus a
# high-priority push on every hourly tick.
BLOCKED_COPY_STALL_DAYS = 3


def actions_delivered(result: Any) -> Optional[bool]:
    """Did that notification actually carry its action links?
    True / False / None (cannot tell).

    shared.notify withholds action buttons (and the Click URL) from an
    unauthenticated ntfy topic, because a button on a public topic is a one-tap
    live send for anyone subscribed. It says "(details in the email)", but the
    email leg only renders ``message`` and ``click``. Passing the same URL as
    ``click`` is what puts it in the email; this reads the result back to check
    one of the two legs really carried it."""
    if not isinstance(result, dict):
        return None
    if result.get("test") or result.get("shadow"):
        return None  # nothing left the process: not a live control either way
    ntfy = result.get("ntfy") if isinstance(result.get("ntfy"), dict) else {}
    headers = ntfy.get("headers") if isinstance(ntfy.get("headers"), dict) else {}
    if ntfy.get("ok") and headers.get("Actions"):
        return True
    if result.get("email"):
        return True  # the email leg carries the link, because it is passed as click=
    return False


def _cancel_hold(appointment_id: Optional[str], ghl: Any) -> Dict[str, Any]:
    """Take back a D6 hold whose email never went out (guarded).

    ``to_notify=False``, as on every cancel the engine starts (SAL-9): the
    prospect was never told about the hold, and GHL's default notification
    setting must not decide whether they hear about its cancel."""
    if not appointment_id:
        return {"skipped": "no_appointment_id"}
    try:
        if ghl is not None:
            rec = ghl.update_appointment_status(appointment_id, "cancelled", to_notify=False)
        else:
            rec = guard_write("ghl", "update_appointment_status", {"appointment_id": appointment_id, "status": "cancelled",
                                                                   "toNotify": False})
    except Exception as exc:  # noqa: BLE001 - surface the orphan, never raise out of the tick
        logger.warning("could not cancel hold %s: %s", appointment_id, exc)
        return {"error": str(exc), "appointment_id": appointment_id}
    return rec if isinstance(rec, dict) else {"result": rec}


def _hold_appointment_id(rec: Any) -> Optional[str]:
    if not isinstance(rec, dict) or rec.get("shadow"):
        return None
    for path in ("id", "appointment.id", "event.id"):
        cur = rec  # type: Any
        for part in path.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
            if cur is None:
                break
        if cur:
            return str(cur)
    return None


def _note_skip(state: Any, day: int, kind: str, now: datetime) -> Tuple[bool, int]:
    """Record that a slot-bearing day was skipped. Returns (quiet, days).

    ``quiet`` is True when this same day/kind was already reported today, so the
    digest says it once instead of once per hourly tick; ``days`` counts the
    consecutive days it has been skipped, which is what escalates a silent stall
    into a stop."""
    ct = slot_rules.to_tz(now)
    cad = dict(getattr(state, "cadence", None) or {})
    prev = cad.get("last_skipped") or {}
    prev_at = _parse(prev.get("at"))
    same = prev.get("day") == day and prev.get("kind") == kind
    if same and prev_at is not None and prev_at.date() == ct.date():
        cad["last_skipped"] = dict(prev, at=ct.isoformat())
        state.cadence = cad
        return True, int(prev.get("days") or 1)
    days = (int(prev.get("days") or 0) + 1) if same else 1
    cad["last_skipped"] = {"day": day, "kind": kind, "at": ct.isoformat(), "days": days}
    state.cadence = cad
    return False, days


def _clear_skip(state: Any) -> None:
    cad = getattr(state, "cadence", None) or {}
    if cad.get("last_skipped") or cad.get("last_blocked"):
        cad = dict(cad)
        cad.pop("last_skipped", None)
        cad.pop("last_blocked", None)
        state.cadence = cad


def _recipient_hold(state: Any, day: int, now: datetime, email: Any, notify_fn: Any) -> Dict[str, Any]:
    """Count one held attempt at ``day`` and decide: retry, or escalate.

    Nothing was sent (recipient_unconfirmed is a pre-send refusal, so the
    marker is already gone and the next tick retries the day). The first hold
    alerts Lorenzo; the RECIPIENT_HOLD_MAX_ATTEMPTS-th consecutive hold of the
    same day escalates and stops the ladder, so it stays held until he re-arms
    it instead of retrying for ever."""
    ct = slot_rules.to_tz(now)
    cad = dict(getattr(state, "cadence", None) or {})
    prev = cad.get("recipient_hold") or {}
    attempts = (int(prev.get("attempts") or 0) + 1) if prev.get("day") == day else 1
    cad["recipient_hold"] = {"day": day, "attempts": attempts, "last_at": ct.isoformat(),
                             "first_at": prev.get("first_at") if prev.get("day") == day else ct.isoformat()}
    state.cadence = cad
    recipient = recipient_for(state)
    _log_job("recipient_held", {"lead": email, "day": day, "attempts": attempts, "to": recipient})
    if attempts >= RECIPIENT_HOLD_MAX_ATTEMPTS:
        stop(state, "recipient_unconfirmed", ct)
        # A stopped ladder is never re-armed by anything else (no new reply is
        # coming - the thread read is what failed), so the alert carries a
        # signed Resume link. Without a usable base URL or a signing secret
        # there is no link, and the text says so instead of promising one.
        resume_url = None
        if links_base_url() is not None and make_decision_token("resume", state, ct):
            resume_url = _decision_url("resume", state, ct)
        if resume_url:
            how = ("Check the thread in the Instantly inbox, then tap Resume: the next tick re-reads the thread and "
                   "sends D%d only if it is confirmed as %s's." % (day, recipient))
        else:
            how = ("Check the thread in the Instantly inbox. No Resume link could be signed (BASE_URL or "
                   "REPLY_ENGINE_SECRET is missing), so fix that and re-arm the lead by hand.")
        kwargs = {"priority": "urgent", "tags": ["warning"]}  # type: Dict[str, Any]
        if resume_url:
            kwargs.update(actions=[("Resume", resume_url)], click=resume_url)
        notify_fn(
            "Cadence HELD for %s: recipient could not be confirmed" % email,
            "D%d was not sent. Before every touch the engine re-reads the thread and checks it was %s who wrote it; "
            "that re-read failed %d times in a row, so the ladder is stopped and stays held. %s"
            % (day, recipient, attempts, how),
            **kwargs
        )
        return {"held": True, "attempts": attempts, "escalated": True, "stopped": True,
                "resume_link": bool(resume_url)}
    if attempts == 1:
        notify_fn(
            "Cadence D%d to %s held: recipient not confirmed" % (day, email),
            "Nothing was sent. The thread re-read failed, so the engine could not confirm it belongs to %s. "
            "It retries on the next ticks (up to %d attempts), then escalates." % (recipient, RECIPIENT_HOLD_MAX_ATTEMPTS),
            priority="high",
            tags=["warning"],
        )
    return {"held": True, "attempts": attempts, "escalated": False}


# jobs: modal_app SCHEDULES["cadence_tick"] runs hourly on the hour (07-19 CT),
# plus the 09:30 veto ping. A send due at 14:30 therefore goes at 15:00, and
# the push must say so.
CADENCE_TICK_MINUTES = 60


def projected_send_time(at: datetime) -> datetime:
    """The first cadence tick at or after ``at`` on which due() may send:
    on the hour, a business day, inside the send window, from CADENCE_HOUR."""
    t = slot_rules.to_tz(at).replace(second=0, microsecond=0)
    if t.minute % CADENCE_TICK_MINUTES:
        t = t.replace(minute=0) + timedelta(minutes=CADENCE_TICK_MINUTES)
    for _ in range(24 * 21):
        if t.weekday() < 5 and slot_rules.within_send_window(t) and t.hour >= CADENCE_HOUR:
            return t
        if t.weekday() >= 5 or t.hour >= CADENCE_HOUR:
            t = cadence_send_time(roll_to_business_day(t.date() + timedelta(days=1)))
        else:
            t = cadence_send_time(t.date())
    return t


def veto_send_time(planned: Optional[datetime], now: datetime) -> datetime:
    """When a D1 whose Veto window opens at ``now`` really sends: no earlier
    than the plan, a full 30 minutes after the push, on the first tick that
    may send. ``now`` is taken to the minute: a push at 09:30:05 must not move
    a 10:00:00 send to 10:00:05, which the 10:00:03 tick would then skip."""
    earliest = slot_rules.to_tz(now).replace(second=0, microsecond=0) + timedelta(minutes=VETO_WINDOW_MINUTES)
    if planned is not None and slot_rules.to_tz(planned) > earliest:
        earliest = slot_rules.to_tz(planned)
    return projected_send_time(earliest)


def _defer_d1_window(state: Any, now: datetime, send_at: datetime, base: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """None when the send lands today; else move the send to that day and
    open no window now (the link would sit overnight, or expire over a
    weekend). veto_notify_due re-opens it 30 minutes before, with a fresh link."""
    ct = slot_rules.to_tz(now)
    if send_at.date() == ct.date():
        return None
    state.cadence = dict(state.cadence, next_send_at=send_at.isoformat(), veto_notified_at=None)
    _log_job("d1_veto_window_deferred", {"lead": _field(state, "lead_email"), "send_at": send_at.isoformat()})
    return dict(base, action="not_due", day=1, reason="veto_window_deferred", next_send_at=send_at.isoformat())


def _lead_push(state: Any, public: str) -> Tuple[str, str, Dict[str, Any]]:
    """(who, message, notify kwargs) for a push to Lorenzo about one lead
    whose lead-free text is ``public``, split the way _resume_push splits a
    template_unapproved push (runbooks/reply_engine_alerts.md: a public topic
    carries no lead names; shared.notify.redact hides only emails and URLs):

    - a protected topic (shared.notify.topic_is_protected): ``who`` is the
      lead's email for the title, and the message ends with "Lead: <email>
      (<company>).";
    - a public topic: ``who`` is "a lead" and ``public`` goes on ntfy alone;
      the lead line goes on the email leg only (``email_message``).

    A setting that cannot be read counts as a public topic."""
    from shared import notify as notify_mod

    email = _field(state, "lead_email")
    lead = "Lead: %s (%s)." % (email, company_of(state))
    try:
        protected = notify_mod.topic_is_protected()
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not read the ntfy config: %s", type(exc).__name__)
        protected = False
    if protected:
        return str(email), "%s %s" % (public, lead), {}
    return "a lead", public, {"email_message": "%s %s" % (public, lead)}


def _hold_d1_without_base_url(state: Any, now: datetime, base: Dict[str, Any], notify_fn: Any) -> Optional[Dict[str, Any]]:
    """None when the D1 Veto link can work; else the hold result.

    No usable base URL in live (unset, or localhost / 127.0.0.1 / 0.0.0.0 /
    ::1) means the Veto link is dead on Lorenzo's phone, so the D1 auto-send
    would go out behind a button that cannot stop it. The D1 arm is held - no
    veto window, no send - Lorenzo is alerted once and it is logged, and every
    tick re-checks, so the day proceeds as soon as BASE_URL is set.

    Reported as ``veto_undeliverable`` (reason ``no_base_url``): it is the same
    condition as a Veto link the push stripped, and jobs/cadence_tick already
    lists that action as one that needs Lorenzo. Unlike that case it is not
    stamped ``veto_undeliverable_at``, so it does not wait for a re-arm."""
    if links_base_url() is not None:
        (getattr(state, "cadence", None) or {}).pop("d1_held_no_base_url_at", None)
        return None
    ct = slot_rules.to_tz(now)
    email = _field(state, "lead_email")
    since = (state.cadence or {}).get("d1_held_no_base_url_at")
    reason = "no_base_url"
    if not since:
        state.cadence = dict(state.cadence or {}, d1_held_no_base_url_at=ct.isoformat())
        logger.error("holding D1 to %s: BASE_URL is unset or local-only, so the Veto link could not work", email)
        _log_job("d1_held_no_base_url", {"lead": email, "campaign_id": _field(state, "campaign_id")})
        who, message, private = _lead_push(
            state,
            "The D1 follow-up auto-sends after a 30-minute Veto window, and the Veto link needs BASE_URL "
            "(it is unset or points at localhost). Nothing was sent and no window was opened. Set BASE_URL "
            "in the Modal secret; the next tick opens the window.")
        notify_fn(
            "D1 follow-up to %s is HELD: no BASE_URL" % who,
            message,
            priority="high",
            tags=["warning"],
            **private
        )
    return dict(base, action="veto_undeliverable", day=1, reason=reason, quiet=bool(since),
                since=since or ct.isoformat(), held=True)


def open_cards(state: Any, store: Any, now: datetime) -> List[str]:
    """The ids of this lead's cards still waiting on Lorenzo (pending or queued,
    inside their TTL; approval.open_card_ids). Each one is a reply of the
    lead's that nobody has answered yet, so nothing of the ladder's goes out
    while one is open. Empty without a store; a store that cannot be read
    raises, and the caller holds."""
    tokens = list(getattr(state, "approvals", None) or [])
    if store is None or not tokens:
        return []
    from services.reply_engine import approval as approval_mod

    return approval_mod.open_card_ids(store, tokens, now)


def changed_in_store(state: Any, store: Any, now: Optional[datetime] = None) -> Optional[str]:
    """Why the stored lead row no longer lets this tick send, or None.

    The tick works on the copy it read at the start. A reply pipeline, a
    booking, or an approval that re-armed the ladder writes the row without
    the tick's lock, so the row is read again just before a send: an opt-out
    marker, a stop, a booking, a new ``armed_at``, a newer inbound or (given
    ``now``) a card still waiting on Lorenzo in the store holds the day. A row
    that cannot be read holds it too (``row_unreadable``), as
    approval.send_approved puts its card back when its re-read fails; cards
    that cannot be read hold it. No store, or no row stored for the lead
    (nothing written it since), proceeds: the thread re-read and the touch
    marker still guard the send."""
    key = getattr(state, "key", None)
    if store is None or not isinstance(key, str):
        return None
    try:
        row = store.get(key)
    except Exception as exc:  # noqa: BLE001 - an unreadable row may hide a stop or an opt-out
        logger.warning("could not re-read %s before the send, holding the day: %s", key, exc)
        return "row_unreadable"
    if not isinstance(row, dict):
        return None
    if row.get("opt_out"):
        return "opt_out"
    stored = row.get("cadence") or {}
    mine = getattr(state, "cadence", None) or {}
    if stored.get("stopped_reason") and not mine.get("stopped_reason"):
        return str(stored["stopped_reason"])
    if stored.get("booking") and not mine.get("booking"):
        return "booked"
    if stored.get("armed_at") and mine.get("armed_at") and stored["armed_at"] != mine["armed_at"]:
        return "rearmed"
    stored_in = _parse(row.get("last_inbound_at"))
    mine_in = _parse(_field(state, "last_inbound_at"))
    if stored_in is not None and (mine_in is None or stored_in > mine_in):
        return "inbound_reply"
    if now is not None and row.get("approvals"):
        try:
            from services.reply_engine import approval as approval_mod

            if approval_mod.open_card_ids(store, list(row.get("approvals") or []), slot_rules.to_tz(now)):
                return "open_card"
        except Exception as exc:  # noqa: BLE001 - a card that cannot be read holds the day
            logger.warning("could not read the cards of %s before the send: %s", key, exc)
            return "open_card_unreadable"
    return None


def hold_cause(reason: Optional[str]) -> str:
    """What fixes a template hold (CT3):

    - ``system``: a gate-wide hold (SYSTEM_HOLD_REASONS: the kill switch,
      parity, a catalogue or approvals file the gate could not read). It holds
      every ladder at once, clears by itself once that is fixed, and never
      counts toward the stall. A reason the gate does not list is ``system``
      too: it holds and never stops a ladder.
    - ``approve``: approve the ids (jobs/approve_templates.py).
    - ``lead_data``: approving changes nothing; a value of the lead's (first
      name, company, thread subject) does not fit the template, or the copy
      check refused it.
    - ``code``: the id cannot be auto-sent as it stands.
    """
    if reason in APPROVE_HOLD_REASONS:
        return "approve"
    if reason in LEAD_DATA_HOLD_REASONS:
        return "lead_data"
    if reason in CODE_HOLD_REASONS:
        return "code"
    return "system"


def hold_advice(reason: Optional[str]) -> str:
    """What Lorenzo does about a template hold, in one or two sentences.
    Ids, reasons and file names only: it goes on the public ntfy topic."""
    cause = hold_cause(reason)
    if reason == "kill_switch":
        return ("Nothing to approve: template auto-send is switched off (the kill switch is on, or the approvals "
                "file cannot be read). Turn the kill switch off (runbooks/template_approvals.md) and the day goes "
                "out on the next tick.")
    if reason == "parity_failed":
        return ("Nothing to approve: the deployed template catalogue does not match its parity reference. Fix "
                "parity (changesets/deploy/template_parity.py --check, then redeploy) and the day goes out on the "
                "next tick.")
    if cause == "system":
        return ("Nothing to approve: the template gate could not read its catalogue or approvals (%s). Fix that "
                "(see /health) and the day goes out on the next tick." % (reason or "registry_error"))
    if cause == "approve":
        return "Approve the ids with jobs/approve_templates.py."
    if reason == "copy_gate":
        return ("Approving changes nothing: the copy check refused the text, most likely a banned word or a "
                "figure in the lead's company or name. Fix the lead's record, or answer the lead by hand.")
    if cause == "lead_data":
        return ("Approving changes nothing: the lead's first name, company or thread subject does not fit the "
                "template's placeholder rules. Fix the lead's record, or answer the lead by hand.")
    return ("Approving changes nothing: the id cannot be auto-sent as it stands (%s). The code or the catalogue "
            "needs a fix." % reason)


def _resume_url(state: Any, now: datetime) -> Optional[str]:
    """A signed /cadence/resume link, or None when none can be signed (no
    usable BASE_URL, or no REPLY_ENGINE_SECRET)."""
    if links_base_url() is None or not make_decision_token("resume", state, now):
        return None
    try:
        return _decision_url("resume", state, now)
    except Exception as exc:  # noqa: BLE001 - no link is said as such, it never fails the tick
        logger.warning("could not sign a resume link: %s", type(exc).__name__)
        return None


# Where a template_unapproved push can put its signed Resume link
# (resume_link_channel).
RESUME_LINK_VIA_NTFY = "ntfy"
RESUME_LINK_VIA_EMAIL = "email"
# What the push says when no leg can carry the link. It goes on the public
# topic: key names only, no lead and no link.
NO_RESUME_CHANNEL = ("No channel can carry the Resume link: the ntfy topic is public (no NTFY_TOKEN, and "
                     "NTFY_ALLOW_SENSITIVE is not 1) and no email leg is set (NOTIFY_EMAIL, GMAIL_SENDER_EMAIL, "
                     "GMAIL_APP_PASSWORD). Set NTFY_TOKEN (or NTFY_ALLOW_SENSITIVE=1), or those three, in .env and "
                     "redeploy (runbooks/deployment.md, step 2a); the next tick then sends a signed Resume link.")


def resume_link_channel() -> Optional[str]:
    """Which leg of a push can carry a signed Resume link, by the notify
    configuration (runbooks/deployment.md step 2a accepts either one):

    - "ntfy": the topic is protected (shared.notify.topic_is_protected:
      NTFY_TOKEN, or NTFY_ALLOW_SENSITIVE=1), so the push itself may name the
      lead and carry the link; the email leg, when set, gets the same text;
    - "email": the topic is public and the email leg is set (NOTIFY_EMAIL,
      GMAIL_SENDER_EMAIL, GMAIL_APP_PASSWORD): ids and counts on ntfy, the
      lead and the link on the email leg only;
    - None: neither, so no leg can carry it.

    Read from the configuration, not from NOTIFY=off, so a test or dry-run
    record shows what a live push would carry. Never raises: a setting that
    cannot be read counts as not set."""
    from shared import notify as notify_mod

    try:
        if notify_mod.topic_is_protected():
            return RESUME_LINK_VIA_NTFY
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not read the ntfy config: %s", type(exc).__name__)
    try:
        if notify_mod._email_config() is not None:  # noqa: SLF001 - the only accessor there is
            return RESUME_LINK_VIA_EMAIL
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not read the email config: %s", type(exc).__name__)
    return None


def _resume_line(via: Optional[str], url: Optional[str]) -> str:
    """The sentence of a template_unapproved push that says where its Resume
    link is, or why there is none. No lead and no link: it is on the topic."""
    if via is None:
        return NO_RESUME_CHANNEL + ("" if url else " A link also needs BASE_URL and REPLY_ENGINE_SECRET.")
    if not url:
        return ("No Resume link could be signed (BASE_URL or REPLY_ENGINE_SECRET is missing). Set them and a "
                "signed link is sent on the next tick.")
    return "Then open the Resume link %s." % ("below" if via == RESUME_LINK_VIA_NTFY else "in the email for this stop")


def _template_stop_private(state: Any, day: Any, url: Optional[str]) -> str:
    """The lead and the signed Resume link of a template_unapproved push. It
    goes only on a leg resume_link_channel() says may carry them: the push
    itself on a protected topic, else the email leg; never a public topic."""
    lead = "Lead: %s (%s), day %s." % (_field(state, "lead_email"), _field(state, "campaign_id"), day)
    if not url:
        return lead
    return ("%s\n\nResume: %s\n\nThe link is valid for %d hours. A fresh one is sent each morning for up to 2 "
            "weeks while the ladder stays stopped, and as soon as the held ids are approved. Nothing is sent from "
            "the page: the next tick runs the template gate again and sends the day only if it is auto-sendable by "
            "then and every send check passes; otherwise it is held again." % (lead, url, DECISION_TTL_HOURS))


def _resume_push(state: Any, day: Any, public: str, url: Optional[str],
                 via: Optional[str]) -> Tuple[str, Dict[str, Any]]:
    """(message, notify kwargs) for a template_unapproved push whose ids and
    counts text is ``public``, by the leg that can carry the Resume link
    (``via``, resume_link_channel()), the way approval._failed_card_push and
    poller._send_stuck_push split theirs:

    - "ntfy" (a protected topic): the push itself names the lead and carries
      the link, as text and as a Resume button (a view action: it opens the
      confirm page, which resumes nothing without its POST). No click, so a
      tap on the push opens nothing;
    - "email": ``public`` on ntfy; the lead and the link on the email leg
      only (``email_message``);
    - None: ``public`` alone (it already says what to set); no link
      anywhere."""
    if via == RESUME_LINK_VIA_NTFY:
        kwargs = {"actions": [("Resume", url)]} if url else {}  # type: Dict[str, Any]
        return "%s\n\n%s" % (public, _template_stop_private(state, day, url)), kwargs
    if via == RESUME_LINK_VIA_EMAIL:
        return public, {"email_message": "%s\n\n%s" % (public, _template_stop_private(state, day, url))}
    return public, {}


def _hold_for_template(state: Any, day: int, verdict: Any, now: datetime, store: Any, base: Dict[str, Any],
                       notify_fn: Any, dry_run: bool = False) -> Dict[str, Any]:
    """CT3: this day's email is not an approved template (or not an
    auto-sendable form of one), so it is held: never a card, never a send.

    Recorded as ``cadence["template_hold"]`` = {day, template_id, ids,
    reason, cause, since, held_days, counted_on, first_at, reported_on}.
    Reported once a day per reason (``quiet`` after that) and counted once for
    the FYI (template_gate.note_held). A D1 hold also drops
    ``veto_notified_at``, so a fix opens a fresh 30-minute Veto window instead
    of sending behind a ping for text that was not going out.

    The stall: ``held_days`` counts the business days (CT dates) on which this
    day was held for a cause that is not gate-wide, once per date, whatever
    order the causes come in, and the count carries across a gate-wide hold:
    one neither counts nor resets it. ``since`` is the first such hold (for
    the record; the count decides). ``days`` in the result is how many such
    days came before today.

    A gate-wide hold (hold_cause "system": the kill switch, parity, an
    unreadable catalogue or approvals file) only holds and never stops the
    ladder, whatever the count says, so the day goes out late, under the
    usual send-window and D1 Veto rules, once it clears. A tick held for any
    other cause, with TEMPLATE_HOLD_STALL_DAYS held days before today, stops
    the ladder as ``template_unapproved``: one push, worded for that cause,
    which carries a signed Resume link on whichever leg can carry one
    (_resume_push; resume_after_recipient_hold; _template_stop_reminder
    re-signs it while the ladder stays stopped)."""
    ct = slot_rules.to_tz(now)
    template_id = getattr(verdict, "template_id", None)
    ids = [i for i in (getattr(verdict, "ids", None) or []) if i]
    reason = getattr(verdict, "reason", None) or "registry_error"
    cause = hold_cause(reason)
    out = dict(base, action="held_template", day=day, template_id=template_id, ids=ids, reason=reason, cause=cause)
    if dry_run:
        return dict(out, dry_run=True)
    cad = dict(getattr(state, "cadence", None) or {})
    prev = cad.get("template_hold") or {}
    today = ct.date().isoformat()
    same = prev.get("day") == day
    since, held_days, counted_on = None, 0, None
    if same:
        since = prev.get("since")
        held_days = _count_of(prev.get("held_days"))
        counted_on = prev.get("counted_on")
        if not held_days and since:
            # A hold recorded before held_days existed: its first day counts.
            held_days, counted_on = 1, (_parse(since) or ct).date().isoformat()
    if cause != "system":
        since = since or ct.isoformat()
        if counted_on != today:
            held_days += 1
            counted_on = today
    days = max(held_days - 1, 0)
    quiet = bool(same and prev.get("reported_on") == today and prev.get("reason") == reason)
    cad["template_hold"] = {"day": day, "template_id": template_id, "ids": ids, "reason": reason, "cause": cause,
                            "since": since or None, "held_days": held_days, "counted_on": counted_on,
                            "first_at": prev.get("first_at") if (same and prev.get("first_at")) else ct.isoformat(),
                            "reported_on": today}
    if day == 1:
        cad["veto_notified_at"] = None
    state.cadence = cad
    if not quiet:
        if store is not None:
            try:
                from services.reply_engine import template_gate

                template_gate.note_held(store, kind="cadence", template_id=template_id, reason=reason, now=ct)
            except Exception as exc:  # noqa: BLE001 - the FYI count must not fail the tick
                logger.warning("could not count the held D%d: %s", day, type(exc).__name__)
        _log_job("template_held", {"lead": _field(state, "lead_email"), "day": day, "template_id": template_id,
                                   "ids": ids, "reason": reason, "cause": cause})
    # Never stopped on a gate-wide hold: that tick's cause clears by itself,
    # and the advice for it ("the day goes out on the next tick") would be
    # false for a stopped ladder.
    if cause == "system" or days < TEMPLATE_HOLD_STALL_DAYS:
        return dict(out, quiet=quiet, since=since or None, days=days)
    stop(state, "template_unapproved", ct)
    _log_job("template_unapproved_stop", {"lead": _field(state, "lead_email"), "day": day,
                                          "template_id": template_id, "reason": reason, "cause": cause,
                                          "days": days})
    url = _resume_url(state, ct)
    via = resume_link_channel()
    linked = bool(url and via)
    if linked:
        state.cadence = dict(state.cadence, template_hold=dict(state.cadence["template_hold"], link_on=today,
                                                               link_at=ct.isoformat(), link_via=via))
    # Ids and counts on a public topic; the lead and the link only on a leg
    # that may carry them (_resume_push).
    public = ("A cadence D%d was held %d business days (reason: %s; ids: %s), so its ladder is stopped as "
              "template_unapproved. %s %s" % (day, days, reason, ", ".join(ids) or "-", hold_advice(reason),
                                              _resume_line(via, url)))
    message, kwargs = _resume_push(state, day, public, url, via)
    notify_fn(
        "Cadence stopped: template %s not auto-sendable" % (template_id or "(none)"),
        message,
        priority="high",
        tags=["warning"],
        **kwargs
    )
    stopped = dict(out, action="stopped", reason="template_unapproved", held_reason=reason, days=days,
                   since=since, stopped=True, resume_link=linked, resume_link_via=via if linked else None)
    if not linked:
        stopped["resume_link_missing"] = "no_channel" if via is None else "unsigned"
    return stopped


def _count_of(value: Any) -> int:
    """A stored count as a non-negative int; anything unreadable is 0."""
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _reminder_cap_reached(cad: Dict[str, Any], ct: datetime) -> bool:
    """The daily Resume reminder's cap: TEMPLATE_STOP_REMINDER_MAX_PUSHES
    reminders sent (``template_hold.link_count``, 0 when absent or unreadable)
    or TEMPLATE_STOP_REMINDER_MAX_DAYS since ``stopped_at`` (no limit by days
    when that is missing). The one rule _template_stop_reminder and
    template_reminders_ended both apply."""
    hold = cad.get("template_hold") or {}
    if _count_of(hold.get("link_count")) >= TEMPLATE_STOP_REMINDER_MAX_PUSHES:
        return True
    stopped_at = _parse(cad.get("stopped_at"))
    return stopped_at is not None and ct - stopped_at >= timedelta(days=TEMPLATE_STOP_REMINDER_MAX_DAYS)


def template_reminders_ended(state: Any, now: datetime) -> bool:
    """True when the ladder is stopped as ``template_unapproved`` and its daily
    Resume reminder has reached its cap (_reminder_cap_reached), so nothing
    reminds Lorenzo of it any more. Pure: it reads the row only, never the
    store; the caller leaves out a lead in the 90-day nurture or one the
    ladder is over for."""
    cad = getattr(state, "cadence", None) or {}
    if cad.get("stopped_reason") != "template_unapproved":
        return False
    return _reminder_cap_reached(cad, slot_rules.to_tz(now))


def _template_stop_reminder(state: Any, now: datetime, notify_fn: Any) -> Optional[Dict[str, Any]]:
    """A ladder stopped as ``template_unapproved`` stays resumable: the Resume
    link is signed for DECISION_TTL_HOURS, so it is re-signed and sent on the
    first tick of every CT day the ladder stays stopped, and at once when the
    held ids pass the gate's pre-check again (an "approve" hold Lorenzo has
    since approved), on the leg that can carry it (_resume_push): the push
    itself on a protected topic, else the email leg, with ids and counts
    only on a public topic. None when there is nothing to send (the row is
    not changed): the link went out today already, or no link can be signed,
    or no leg can carry one (the stop push said what to set; the first tick
    after that sends the link). Otherwise the result, and ``template_hold``
    records the day the link went out and on which leg. The caller withholds
    it for a lead the ladder is over for (terminal_reason) or enrolled in the
    90-day nurture. ``link_count`` (beside ``link_on``; 0 when absent) counts
    the daily reminders: none goes out once TEMPLATE_STOP_REMINDER_MAX_PUSHES
    have, or TEMPLATE_STOP_REMINDER_MAX_DAYS after ``stopped_at``. The
    one-time "ready to resume" push is not counted and not capped. The ladder
    stays stopped either way."""
    ct = slot_rules.to_tz(now)
    cad = getattr(state, "cadence", None) or {}
    hold = dict(cad.get("template_hold") or {})
    today = ct.date().isoformat()
    template_id = hold.get("template_id")
    ids = [i for i in (hold.get("ids") or []) if i]
    reason = hold.get("reason")
    day = hold.get("day")
    ready = False
    if template_id and hold_cause(reason) == "approve":
        ready = bool(getattr(_template_ids_verdict(template_id, [i for i in ids if i != template_id]),
                             "allowed", False))
    announce = ready and not hold.get("ready_announced")
    if not announce and hold.get("link_on") == today:
        return None
    sent_count = _count_of(hold.get("link_count"))
    if not announce:
        if _reminder_cap_reached(cad, ct):
            return None
        sent_count += 1
    url = _resume_url(state, ct)
    via = resume_link_channel()
    if url is None or via is None:
        return None
    where = "below" if via == RESUME_LINK_VIA_NTFY else "in the email"
    if announce:
        title = "Cadence ready to resume: template %s is approved" % (template_id or "(none)")
        public = ("A ladder stopped at D%s (it was held for: %s; ids: %s) can go again: the held ids pass the "
                  "template gate now. Open the Resume link %s." % (day, reason, ", ".join(ids) or "-", where))
        priority = "high"
    else:
        title = "Cadence still stopped: template %s" % (template_id or "(none)")
        public = ("A ladder is still stopped at D%s (reason: %s; ids: %s). %s A fresh Resume link is %s."
                  % (day, reason, ", ".join(ids) or "-", hold_advice(reason), where))
        priority = "low"
    message, kwargs = _resume_push(state, day, public, url, via)
    notify_fn(title, message, priority=priority, tags=["warning"], **kwargs)
    hold.update(link_on=today, link_at=ct.isoformat(), link_via=via, link_count=sent_count,
                ready_announced=bool(hold.get("ready_announced") or ready))
    # No Job_Log row of its own: the tick's row counts resume_link_sent.
    state.cadence = dict(cad, template_hold=hold)
    return {"action": "resume_link_sent", "reason": "template_unapproved", "day": day, "template_id": template_id,
            "ids": ids, "held_reason": reason, "ready": ready, "resume_link_via": via}


class _HeldVerdict(object):
    """A D1 hold repeated without a change (see _d1_gate_hold)."""

    allowed = False

    def __init__(self, template_id: Optional[str], ids: List[str], reason: str) -> None:
        self.template_id = template_id
        self.ids = list(ids)
        self.reason = reason
        self.statuses = {}  # type: Dict[str, str]
        self.detail = "unchanged since the last full check refused it"


def _d1_gate_fingerprint(state: Any, touch: Touch, verdict: Any) -> str:
    """What a D1 verdict depended on, the slots aside: the lead's bound values,
    the subject, the ids' catalogue hashes and their approval statuses, and
    the gate itself: the version of its rules (template_gate.
    GATE_RULES_VERSION: a relaxed value rule changes no hash) and the
    catalogue digest (template_gate.catalogue_digest_cached, computed once
    per catalogue build). A D1 the full check refused re-opens its Veto
    window only once this changes, or after a Resume (which drops the
    refusal). Raises when the catalogue cannot be built."""
    from services.reply_engine import template_gate

    bound = dict((k, v) for k, v in touch_bindings(state, touch).items() if k not in ("slots", "slot1", "slot2"))
    record = {"template_id": touch.template_id, "template_hash": touch.template_hash,
              "parts": dict(touch.template_parts or {}), "subject": touch.subject, "bindings": bound,
              "statuses": dict(getattr(verdict, "statuses", None) or {}),
              "gate_rules": template_gate.GATE_RULES_VERSION,
              "catalogue": template_gate.catalogue_digest_cached()}
    return hashlib.sha256(json.dumps(record, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _note_d1_gate_hold(state: Any, touch: Touch, verdict: Any, now: datetime) -> None:
    """Remember what the refused D1 full check looked at (_d1_gate_fingerprint)."""
    try:
        fp = _d1_gate_fingerprint(state, touch, verdict)
    except Exception as exc:  # noqa: BLE001 - without a fingerprint the next check simply runs again
        logger.warning("could not fingerprint the refused D1: %s", type(exc).__name__)
        return
    state.cadence = dict(state.cadence or {}, d1_gate_hold={
        "fp": fp, "reason": getattr(verdict, "reason", None) or "registry_error",
        "at": slot_rules.to_tz(now).isoformat()})


def _d1_precheck_slots(state: Any, now: datetime, store: Any, free_slots: Optional[List[Any]]) -> List[datetime]:
    """Two slots to render the D1 pre-check with: the tick's own free slots
    when it has two, else two from the default grid. No GHL read. The gate
    binds the slots to whichever are offered, so they do not change its answer
    on the subject, the name or the company."""
    two = fresh_slots(state, now, free_slots, store) if free_slots is not None else []
    if len(two) < 2:
        two = fresh_slots(state, now, default_slot_grid(now), None)
    return two


def _d1_gate_hold(state: Any, now: datetime, store: Any,
                  free_slots: Optional[List[Any]]) -> Tuple[Optional[Any], bool]:
    """Live D1, before its Veto window opens: the full template check on the
    exact subject and body D1 would send, placeholders bound, so Lorenzo is
    never pinged "sends at 10:00" about a D1 the send-time check refuses.

    Returns (verdict to hold on, copy_blocked). A refused check is remembered
    (_note_d1_gate_hold); a later check that passes but looked at the very same
    inputs (the send-time check refused what this one let through) holds too,
    so the window re-opens only once something changed that could make it pass
    (an approval, the lead's data, the template, the gate's rules or the
    catalogue after a deploy), or once Lorenzo resumes the stopped ladder
    (resume_after_recipient_hold drops the refusal, so this check runs
    fresh). ``copy_blocked``: the copy check refuses the body, which the send
    path reports as ``blocked_copy``; no window is opened for it either.
    Fails closed (registry_error)."""
    ct = slot_rules.to_tz(now)
    try:
        touch = build_touch(state, 1, _d1_precheck_slots(state, ct, store, free_slots))
        if touch.problems:
            return None, True
    except Exception as exc:  # noqa: BLE001 - a D1 that cannot be rendered is held, never pinged
        logger.warning("D1 pre-check failed closed: %s", type(exc).__name__)
        return _GateUnavailable("cadence.d1", (), type(exc).__name__), False
    verdict = _template_touch_verdict(state, touch)
    if not verdict.allowed:
        _note_d1_gate_hold(state, touch, verdict, ct)
        return verdict, False
    refused = (getattr(state, "cadence", None) or {}).get("d1_gate_hold") or {}
    try:
        unchanged = bool(refused.get("fp")) and refused["fp"] == _d1_gate_fingerprint(state, touch, verdict)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not fingerprint the D1 pre-check: %s", type(exc).__name__)
        return _GateUnavailable("cadence.d1", (), type(exc).__name__), False
    if unchanged:
        reason = str(refused.get("reason") or "nonconforming")
        return _HeldVerdict(verdict.template_id, list(verdict.ids), reason), False
    return None, False


def tick_lead(state: Any, now: datetime, store: Any = None, instantly: Any = None, ghl: Any = None,
              free_slots: Optional[List[Any]] = None, dry_run: bool = False, notify_fn: Any = notify,
              research_mode: Optional[str] = None) -> Dict[str, Any]:
    """Evaluate one lead at ``now`` and act. Returns a result dict with
    ``action`` in: not_armed | already_stopped | awaiting_fresh_draft |
    resumed_after_auto_reply | stopped | follow_up_later | not_due |
    veto_window_opened | vetoed | awaiting_invite_ok | skipped_no_slots |
    skipped_unverified_slots | already_sent | blocked_copy | held_template |
    send_failed | slot_taken | would_send | sent | resume_link_sent.

    CT3: a touch goes out only when its text is an approved template
    (template_gate), in shadow as in live, so the shadow preview is the live
    run. Anything else is ``held_template`` (see _hold_for_template). A ladder
    stopped as ``template_unapproved`` answers ``resume_link_sent`` on the
    tick that re-signs its Resume link (_template_stop_reminder).

    ``dry_run=True`` plans the touch and mutates nothing (no store, no send).
    ``research_mode`` is passed to build_touch (default D2_RESEARCH_MODE)."""
    ct = slot_rules.to_tz(now)
    email = _field(state, "lead_email")
    base = {"lead_email": email, "campaign_id": _field(state, "campaign_id"), "now": ct.isoformat()}

    cad = getattr(state, "cadence", None) or {}
    if not cad.get("armed_at"):
        return dict(base, action="not_armed")

    pause = is_auto_reply_pause(state)
    # A lead enrolled in the 90-day nurture (nurture.enroll) gets no more
    # follow-up touches: a running ladder is stopped for it before anything
    # else is looked at, and an auto-reply pause is not resumed past it. A
    # nurture record that cannot be read holds the lead this tick.
    if pause or not cad.get("stopped_reason"):
        try:
            enrolled = in_nurture(state, store)
        except Exception as exc:  # noqa: BLE001 - never let an unreadable nurture record through
            logger.warning("could not read the nurture record of %s: %s", email, exc)
            return dict(base, action="error", error="could not read this lead's nurture record: %s" % exc)
        if enrolled:
            if not dry_run:
                stop(state, "nurture", ct)
            return dict(base, action="stopped", reason="nurture", needs_fresh_draft=False)

    # A card waiting on Lorenzo is a reply of the lead's that nobody has
    # answered yet. Nothing of the ladder's goes out on top of it, whatever the
    # ladder's own fields say (a pause resumed on a copy read before the reply
    # landed, a stop another writer lost): a running ladder is stopped for it
    # exactly as the reply's own pipeline stops one, and a stopped ladder is
    # not resumed past it. Cards that cannot be read hold the lead this tick.
    # (A ladder that stays stopped either way costs no card reads.) The
    # ladder's own stop reasons keep their meaning: a booked, unsubscribed,
    # hostile or not-now lead, or a newer inbound, is stopped for that below,
    # and nothing goes out either way; the open card stops a ladder that
    # nothing else would.
    waiting = []  # type: List[str]
    if pause or not cad.get("stopped_reason"):
        try:
            waiting = open_cards(state, store, ct)
        except Exception as exc:  # noqa: BLE001 - never let an unreadable card through
            logger.warning("could not read the open cards of %s: %s", email, exc)
            return dict(base, action="error", error="could not read this lead's cards: %s" % exc)
    if waiting and not cad.get("stopped_reason") and not stop_reason(state, ct):
        if not dry_run:
            stop(state, "inbound_reply", ct)
        return dict(base, action="stopped", reason="open_card", cards=waiting, needs_fresh_draft=True)

    # An out-of-office / unmonitored auto-responder stopped the cadence at
    # webhook time, but it produces no draft and no approval, so nothing would
    # ever re-arm this lead. Resume instead of losing the sequence.
    if pause and not waiting:
        if dry_run:
            return dict(base, action="resumed_after_auto_reply", dry_run=True, day=pending_day(state))
        nxt = resume_after_auto_reply(state, ct)
        return dict(base, action="resumed_after_auto_reply", day=pending_day(state), next_send_at=nxt.isoformat())

    if cad.get("stopped_reason"):
        if cad.get("stopped_reason") == "inbound_reply" and cad.get("needs_fresh_draft") and not cad.get("stall_notified_at"):
            # Say it once: a human replied, the cadence is parked until Lorenzo
            # approves the fresh answer. Silence here loses positive leads.
            # Only a reply that raised a card has an answer waiting on him. An
            # unsubscribe, a short no or a "not now" raises none, and the line
            # must not say one is coming (card_open False; None when the cards
            # could not be read).
            try:
                card_open = bool(waiting) or bool(open_cards(state, store, ct))
            except Exception as exc:  # noqa: BLE001 - the wording falls back to the neutral line
                logger.warning("could not read the open cards of %s: %s", email, exc)
                card_open = None
            if not dry_run:
                state.cadence = dict(cad, stall_notified_at=ct.isoformat())
            return dict(base, action="awaiting_fresh_draft", reason="inbound_reply", day=pending_day(state),
                        card_open=card_open)
        if cad.get("stopped_reason") == "template_unapproved" and not dry_run:
            # Keeps a live, signed Resume link in Lorenzo's hands while the
            # ladder stays stopped (daily, and at once when the ids pass),
            # unless the lead is done with the ladder anyway: opted out,
            # blocklisted, booked, hostile or not now (terminal_reason). A
            # Resume would stop it again at once, so no reminder and no
            # "ready to resume" push.
            ended = terminal_reason(state)
            if ended:
                return dict(base, action="already_stopped", reason=cad["stopped_reason"], resume_withheld=ended)
            # A lead in the 90-day nurture is done with the ladder too. A
            # nurture record that cannot be read still reminds: the push only
            # reaches Lorenzo, and the send path holds on that error anyway.
            try:
                nurtured = in_nurture(state, store)
            except Exception as exc:  # noqa: BLE001 - an unreadable record keeps the reminder
                logger.warning("could not read the nurture record of %s: %s", email, exc)
                nurtured = False
            if nurtured:
                return dict(base, action="already_stopped", reason=cad["stopped_reason"], resume_withheld="nurture")
            reminded = _template_stop_reminder(state, ct, notify_fn)
            if reminded is not None:
                return dict(base, **reminded)
        return dict(base, action="already_stopped", reason=cad["stopped_reason"])

    reason = stop_reason(state, ct)
    if reason:
        if reason == "follow_up_later":
            post_errors = []  # type: List[str]
            if not dry_run:
                # The cadence is halted inside move_to_follow_up_later before the
                # GHL write, so a pipeline failure surfaces once instead of
                # erroring on this lead on every daily tick for ever.
                try:
                    rec = move_to_follow_up_later(state, ghl, ct)
                except Exception as exc:  # noqa: BLE001 - belt and braces around another brief's client
                    logger.warning("move_to_follow_up_later failed for %s: %s", email, exc)
                    stop(state, reason, ct)
                    rec = {"error": "follow_up_later: %s" % exc}
                if isinstance(rec, dict) and rec.get("error"):
                    post_errors.append(str(rec["error"]))
            out = dict(base, action="follow_up_later", reason=reason)
            if post_errors:
                out["post_errors"] = post_errors
            return out
        if not dry_run:
            stop(state, reason, ct)
        return dict(base, action="stopped", reason=reason, needs_fresh_draft=(reason == "inbound_reply"))

    day = pending_day(state)
    if day is None:
        if not dry_run:
            stop(state, "exhausted", ct)
        return dict(base, action="stopped", reason="exhausted")

    # The one human hold on the live D1 auto-send could not be delivered. An
    # unattended send whose only control was dropped escalates, it does not
    # proceed; said once, then quiet.
    if day == 1 and is_live() and (state.cadence or {}).get("veto_undeliverable_at"):
        return dict(base, action="veto_undeliverable", day=1, quiet=True,
                    reason="the Veto link was withheld from the push and no email leg carried it",
                    since=(state.cadence or {}).get("veto_undeliverable_at"))

    # A Veto link that has expired (or is about to) cannot stop the send it
    # was pushed for: re-open the window with a fresh link. A send the engine
    # moves to another day never keeps its old window in the first place
    # (_defer_d1_window opens none; resume_after_recipient_hold drops it).
    # Before the CT3 pre-check below, so a re-opened window is checked too.
    if day == 1 and is_live() and not dry_run and (state.cadence or {}).get("veto_notified_at"):
        pinged = _parse(state.cadence.get("veto_notified_at"))
        if pinged is not None and ct - slot_rules.to_tz(pinged) >= timedelta(hours=DECISION_TTL_HOURS - 1):
            state.cadence = dict(state.cadence, veto_notified_at=None, veto_reopened_from=pinged.isoformat())

    # CT3: D1 auto-sends only as an approved template. Checked before the
    # Veto window opens, so Lorenzo is never pinged about text that is not
    # going out: the ids first, then (live, before a window opens) the full
    # check on the exact subject and body with its placeholders bound
    # (_d1_gate_hold). A hold drops veto_notified_at, so a fix opens a fresh
    # 30-minute window (approving never shortens it), and after a refused full
    # check the window re-opens only once something changed that could make
    # it pass. A body the copy check refuses opens no window either: it is
    # reported as blocked_copy when it falls due.
    d1_copy_blocked = False
    if day == 1 and not dry_run and ((is_live() and veto_notify_due(state, ct)) or due(state, ct)):
        pre = _template_ids_verdict("cadence.d1")
        if not pre.allowed:
            return _hold_for_template(state, 1, pre, ct, store, base, notify_fn)
        if is_live() and not (state.cadence or {}).get("veto_notified_at"):
            refused, d1_copy_blocked = _d1_gate_hold(state, ct, store, free_slots)
            if refused is not None:
                return _hold_for_template(state, 1, refused, ct, store, base, notify_fn)
            if d1_copy_blocked and not due(state, ct):
                return dict(base, action="not_due", day=1, reason="d1_copy_blocked",
                            next_send_at=(state.cadence or {}).get("next_send_at"))

    # D1 veto window (live only; shadow records the intent inside the would_do)
    if day == 1 and is_live() and veto_notify_due(state, ct) and not dry_run and not d1_copy_blocked:
        held = _hold_d1_without_base_url(state, ct, base, notify_fn)
        if held is not None:
            return held
        # The window always lasts the full 30 minutes, and the push names the
        # time the send will really happen (the first cadence tick that may
        # send). Opened late - a D1 held for hours by a missing BASE_URL - it
        # used to leave the send overdue, so the next tick sent it a minute
        # after the push. When that time falls on another day the window is not
        # opened now; it re-opens on that day with a fresh link.
        send_at = veto_send_time(_parse(state.cadence.get("next_send_at")), ct)
        deferred = _defer_d1_window(state, ct, send_at, base)
        if deferred is not None:
            return deferred
        veto_url = _decision_url("veto", state, ct)
        state.cadence = dict(state.cadence, veto_notified_at=ct.isoformat(), next_send_at=send_at.isoformat())
        who, message, private = _lead_push(
            state, "Tap Veto, then confirm on the page it opens, within 30 minutes to hold it.")
        sent = notify_fn(
            "D1 follow-up to %s sends at %s CT" % (who, slot_rules.format_slot(send_at)),
            message,
            priority="high",
            actions=[("Veto", veto_url)],
            # Passed as click= as well: shared.notify strips action buttons from an
            # unauthenticated topic and only renders message + click into the email
            # fallback, so this is the leg that actually reaches Lorenzo.
            click=veto_url,
            tags=["calendar"],
            **private
        )
        if actions_delivered(sent) is False:
            state.cadence = dict(state.cadence, veto_notified_at=None, veto_undeliverable_at=ct.isoformat())
            return dict(base, action="veto_undeliverable", day=1,
                        reason="the Veto link was withheld from the push and no email leg carried it")
        return dict(base, action="veto_window_opened", day=1)

    if not due(state, ct):
        return dict(base, action="not_due", day=day, next_send_at=(state.cadence or {}).get("next_send_at"))

    if day == 1 and store is not None and decision_is_current(store.get(veto_key(state)), state):
        if not dry_run:
            stop(state, "vetoed", ct)
        return dict(base, action="vetoed", day=1)

    if (day == 1 and is_live() and not (state.cadence or {}).get("veto_notified_at") and not dry_run
            and not d1_copy_blocked):
        # Never auto-send D1 live without the veto window having been opened
        # first, and (CT3, the pre-check above) never open it for a template
        # that is not approved.
        held = _hold_d1_without_base_url(state, ct, base, notify_fn)
        if held is not None:
            return held
        send_at = veto_send_time(None, ct)
        deferred = _defer_d1_window(state, ct, send_at, base)
        if deferred is not None:
            return deferred
        veto_url = _decision_url("veto", state, ct)
        state.cadence = dict(state.cadence, veto_notified_at=ct.isoformat(), next_send_at=send_at.isoformat())
        who, message, private = _lead_push(state, "Tap Veto, then confirm on the page it opens, to hold it.")
        sent = notify_fn(
            "D1 follow-up to %s sends at %s CT" % (who, slot_rules.format_slot(send_at)),
            message,
            priority="high",
            actions=[("Veto", veto_url)],
            click=veto_url,
            tags=["calendar"],
            **private
        )
        if actions_delivered(sent) is False:
            state.cadence = dict(state.cadence, veto_notified_at=None, veto_undeliverable_at=ct.isoformat())
            return dict(base, action="veto_undeliverable", day=1,
                        reason="the Veto link was withheld from the push and no email leg carried it")
        return dict(base, action="veto_window_opened", day=1)

    # A previous tick already sent this day but died before the state was
    # written: repair the state, never send twice.
    marker = store.get(touch_marker_key(state, day)) if store is not None else None
    if isinstance(marker, dict) and marker.get("sent"):
        if dry_run:
            return dict(base, action="already_sent", day=day, dry_run=True)
        rec = _repair_from_marker(state, day, marker, ct, store)
        return dict(base, action="already_sent", day=day, record=rec)
    if isinstance(marker, dict) and not marker.get("sent"):
        # An attempt from earlier today never confirmed: either the process died
        # with the POST in flight, or Instantly failed the write without ever
        # answering it. Either way the body may already be in the thread, so the
        # day is held and Lorenzo confirms it by hand; tomorrow it retries.
        started = _parse(marker.get("ts"))
        if started is not None and started.date() == ct.date():
            return dict(base, action="send_failed", day=day, reason="previous_attempt_unconfirmed",
                        started_at=marker.get("ts"), needs_manual_check=True)

    # Fresh slots (skip for the slotless yes/no close)
    two = []  # type: List[datetime]
    source = "provided"
    if day not in SLOTLESS_DAYS:
        if free_slots is None:
            free_slots, source = resolve_free_slots(ghl, ct)
        two = fresh_slots(state, ct, free_slots, store)
        skip = None
        if len(two) < 2:
            # Every slot-bearing body offers two times ("here are two new ones");
            # one slot would render a sentence Lorenzo did not write.
            skip = "skipped_no_slots"
        elif is_live() and source == "default_grid":
            skip = "skipped_unverified_slots"
        if skip:
            # Eight of the nine cadence days carry slots, so a skip that never
            # advances, never stops and never stamps anything is a lead getting
            # zero follow-ups while the digest repeats the same line every hour.
            # Say it once a day, and after SKIP_STALL_DAYS stop the ladder with a
            # reason of its own so a stall cannot pass for a running cadence.
            if dry_run:
                return dict(base, action=skip, day=day, slots_found=len(two), dry_run=True)
            quiet, days = _note_skip(state, day, skip, ct)
            if days >= SKIP_STALL_DAYS:
                stop(state, "slots_unavailable", ct)
                if not quiet:
                    who, message, private = _lead_push(
                        state,
                        "D%d could not be sent on %d days running (%s). The ladder is stopped so it does not "
                        "look like it is still running." % (day, days, skip))
                    notify_fn(
                        "Cadence stopped for %s: no bookable times" % who,
                        message,
                        priority="high",
                        tags=["warning"],
                        **private
                    )
                return dict(base, action="stopped", reason="slots_unavailable", day=day, skipped=skip, days=days)
            return dict(base, action=skip, day=day, slots_found=len(two), quiet=quiet, days=days)

    # D6: the calendar invite needs Lorenzo's OK
    invite_created = False
    if day == 6:
        raw_decision = store.get(approval_key(state, "d6")) if store is not None else None
        decision = raw_decision if decision_is_current(raw_decision, state) else None
        if not hold_enabled():
            # Default: no hold, in shadow and live alike, so the shadow run is a
            # true preview, and D6 renders the no-invite wording.
            #
            # The dependency this used to wait on is DONE: jobs/appointments_tick
            # .is_cadence_hold() drops events whose title starts with "HOLD: ",
            # so a hold is no longer read as a booked call, confirmed to the
            # prospect and then chased as a no-show. _create_hold also writes
            # to_notify=False, so GHL sends no booking notice.
            #
            # It stays off anyway, because the blueprint's D6 is "a calendar
            # invite for one of the slots, marked free so it does not block
            # their day" and this is not that: a GHL appointment carries no
            # transparency flag and the prospect receives nothing at all. What
            # ships today is a private hold on Lorenzo's own calendar. The real
            # touch needs an ICS attachment with TRANSP:TRANSPARENT sent from
            # the Instantly reply, which is a design change, recorded as out of
            # scope for Phase 1 in runbooks/PHASE1_SHADOW_REPORT.md.
            # CADENCE_D6_HOLD=1 turns the private hold on; it does not make the
            # blueprint's touch exist.
            invite_created = False
        elif is_live() and not decision:
            if not (state.cadence or {}).get("d6_notified_at"):
                if not dry_run and links_base_url() is None:
                    # "Send hold" / "Email only" would be dead links. Say so once
                    # and fall through to the no-hold wording at 18:00, exactly
                    # like an undeliverable card: it costs the hold, never the touch.
                    state.cadence = dict(state.cadence, d6_notified_at=ct.isoformat())
                    logger.error("D6 hold card for %s not sent: BASE_URL is unset or local-only", email)
                    _log_job("d6_card_no_base_url", {"lead": email, "campaign_id": _field(state, "campaign_id")})
                    who, message, private = _lead_push(
                        state,
                        "The 'Send hold' / 'Email only' links need BASE_URL (unset or localhost). No hold will be "
                        "booked; the no-hold follow-up goes out at %d:00 CT." % D6_FALLBACK_HOUR)
                    notify_fn(
                        "D6 hold card for %s could not be sent: no BASE_URL" % who,
                        message,
                        priority="high",
                        tags=["warning"],
                        **private
                    )
                    return dict(base, action="awaiting_invite_ok", day=6, slot=_iso(two[0]),
                                card_undeliverable=True, reason="no_base_url")
                if not dry_run:
                    approve_url = _decision_url("approve", state, ct)
                    state.cadence = dict(state.cadence, d6_notified_at=ct.isoformat())
                    who, message, private = _lead_push(
                        state,
                        "Day 6. The follow-up email goes out either way: 'Send hold' also books the %s CT "
                        "hold on the Discovery Call calendar, 'Email only' sends the no-hold wording."
                        % slot_rules.format_slot(two[0]))
                    sent = notify_fn(
                        "OK to put a calendar hold on %s?" % who,
                        message,
                        priority="high",
                        actions=[("Send hold", approve_url),
                                 ("Email only", _decision_url("veto-invite", state, ct))],
                        # See the D1 card: this is the leg that survives an
                        # unauthenticated topic. Without an answer the day falls
                        # through to the no-hold wording at 18:00 anyway, so an
                        # undeliverable card costs the hold, never the touch.
                        click=approve_url,
                        tags=["calendar"],
                        **private
                    )
                    if actions_delivered(sent) is False:
                        logger.warning("D6 hold card for %s carried no buttons; the no-hold body will be sent", email)
                        return dict(base, action="awaiting_invite_ok", day=6, slot=_iso(two[0]),
                                    card_undeliverable=True)
                return dict(base, action="awaiting_invite_ok", day=6, slot=_iso(two[0]))
            if ct.hour < D6_FALLBACK_HOUR:
                return dict(base, action="awaiting_invite_ok", day=6, slot=_iso(two[0]))
            invite_created = False  # no answer by 18:00 CT: send the no-invite variant
        elif is_live():
            invite_created = decision.get("decision") == "approve"
        else:
            invite_created = True  # shadow: record the intent; requires_approval stays on the record

    # CT3 pre-check: the day's template (and every line spliced into it that
    # is known before the body is built) is approved, before a D6 hold is
    # put on the calendar or a research line is paid for.
    mode = research_mode or D2_RESEARCH_MODE
    pre_main, pre_parts = touch_template_ids(day, state, invite_created=invite_created,
                                             research_source="fallback", has_slots=bool(two))
    if day == 2 and mode == "llm":
        pre_parts = []  # the line is not written yet; the full verdict below judges it
    pre = _template_ids_verdict(pre_main, pre_parts)
    if not pre.allowed:
        return _hold_for_template(state, day, pre, ct, store, base, notify_fn, dry_run=dry_run)

    if dry_run:
        touch = build_touch(state, day, two, invite_created=invite_created, slots_source=source,
                            research_mode=research_mode)
        # Touch.problems is a property, so it is not in to_dict(): a --dry-run
        # preview that hid the copy verdict is the one Lorenzo signs off on.
        if touch.problems:
            return dict(base, action="blocked_copy", day=day, problems=list(touch.problems),
                        touch=touch.to_dict(), dry_run=True)
        verdict = _template_touch_verdict(state, touch)
        if not verdict.allowed:
            return dict(_hold_for_template(state, day, verdict, ct, store, base, notify_fn, dry_run=True),
                        touch=touch.to_dict())
        return dict(base, action="would_send", day=day, touch=touch.to_dict(), dry_run=True)

    # The copy gate refused this day already today: nothing about the lead has
    # changed since, so do not rebuild the touch (D2 rebuilds it with a fresh
    # paid research line), do not notify again, and do not re-create the D6 hold.
    prev_blocked = (getattr(state, "cadence", None) or {}).get("last_blocked") or {}
    prev_blocked_at = _parse(prev_blocked.get("at"))
    if prev_blocked.get("day") == day and prev_blocked_at is not None and prev_blocked_at.date() == ct.date():
        return dict(base, action="blocked_copy", day=day, quiet=True,
                    problems=list(prev_blocked.get("problems") or []),
                    days=int(prev_blocked.get("days") or 1), reason="already_reported_today")

    # The D6 body claims a hold exists, so the hold is attempted first; if it
    # cannot be created the day falls through to the no-hold wording instead of
    # being lost (and the lead is never told about a hold that is not there).
    records = []  # type: List[Dict[str, Any]]
    hold_error = None
    hold_appointment_id = None
    if day == 6 and invite_created and two:
        try:
            appt = _create_hold(state, two[0], ghl, ct)
        except Exception as exc:  # noqa: BLE001 - a calendar failure must not sit between the OK and the email
            logger.warning("D6 hold failed for %s: %s", email, exc)
            appt = {"error": str(exc)}
        if isinstance(appt, dict) and not appt.get("error") and not appt.get("skipped"):
            records.append(appt)
            hold_appointment_id = _hold_appointment_id(appt)
        else:
            hold_error = (appt or {}).get("error") or (appt or {}).get("skipped") or "hold_failed"
            invite_created = False

    touch = build_touch(state, day, two, invite_created=invite_created, slots_source=source,
                        research_mode=research_mode)

    # The copy gate: approval.send_approved refuses a draft with problems, and an
    # unattended touch must clear the same bar before it reaches a customer.
    if touch.problems:
        days = (int(prev_blocked.get("days") or 0) + 1) if prev_blocked.get("day") == day else 1
        state.cadence = dict(state.cadence or {},
                             last_blocked={"day": day, "at": ct.isoformat(), "problems": list(touch.problems),
                                           "days": days})
        # The hold was created before the copy check; the email is not going out,
        # so the afternoon goes back on the calendar instead of leaving one orphan
        # HOLD per retry.
        if hold_appointment_id:
            records.append(_cancel_hold(hold_appointment_id, ghl))
        stalled = days >= BLOCKED_COPY_STALL_DAYS
        if stalled:
            stop(state, "blocked_copy", ct)
        # The blocked body names the lead ("Hey Dana", the company), so on a
        # public topic it goes on the email leg only, with the lead line.
        who, message, private = _lead_push(
            state,
            "Copy check failed (%s). The day was not sent%s."
            % (", ".join(touch.problems),
               ", and after %d days the ladder is stopped so it does not stall in silence" % days if stalled
               else " and will be retried tomorrow once the wording is fixed"))
        if "email_message" in private:
            private["email_message"] = "%s\n\n%s" % (private["email_message"], touch.body_text)
        else:
            message = "%s\n\n%s" % (message, touch.body_text)
        notify_fn(
            "Cadence D%d to %s was blocked%s" % (day, who, " (%d days running)" % days if days > 1 else ""),
            message,
            priority="high",
            tags=["warning"],
            **private
        )
        return dict(base, action=("blocked_copy_stalled" if stalled else "blocked_copy"), day=day,
                    problems=list(touch.problems), touch=touch.to_dict(), days=days, records=records)

    # CT3: the exact subject and body are an approved template with only its
    # placeholders filled (the slots bound to the ones offered). Before the
    # base-URL hold, the marker claim, the slot claim and the send.
    verdict = _template_touch_verdict(state, touch)
    if not verdict.allowed:
        if hold_appointment_id:
            records.append(_cancel_hold(hold_appointment_id, ghl))
        if day == 1:
            # The next Veto window waits for a change that could make it pass.
            _note_d1_gate_hold(state, touch, verdict, ct)
        held = _hold_for_template(state, day, verdict, ct, store, base, notify_fn)
        held["records"] = records
        return held

    # Belt and braces: a live D1 never goes out without its Veto window. Only
    # a D1 the pre-check found copy-blocked gets here without one, and only
    # the copy block above was meant to report it.
    if day == 1 and is_live() and not (state.cadence or {}).get("veto_notified_at"):
        return dict(base, action="not_due", day=1, reason="veto_window_not_open",
                    next_send_at=(state.cadence or {}).get("next_send_at"))

    # The D1 auto-send only ever goes out behind a working Veto link. The
    # window was opened with one, but if BASE_URL has gone since, hold.
    if day == 1 and is_live():
        held = _hold_d1_without_base_url(state, ct, base, notify_fn)
        if held is not None:
            if hold_appointment_id:
                held["records"] = records + [_cancel_hold(hold_appointment_id, ghl)]
            return held

    # Claim the day. set_if_absent is the atomic half of what used to be a
    # get-then-set: two overlapping ticks both read "no marker" and both POSTed
    # the same body into the same thread.
    if store is not None:
        pre = {"ts": ct.isoformat(), "day": day, "sent": False,
               "subject": touch.subject, "slots": list(touch.slots),
               "slots_source": touch.slots_source,
               "requires_approval": touch.requires_approval}
        try:
            claimed = store.set_if_absent(touch_marker_key(state, day), pre)
            if not claimed:
                # Either another worker is mid-send right now, or an unconfirmed
                # attempt from an earlier day is still sitting there (the
                # same-day case was already held above). Take that one over, but
                # only if nobody else has touched it since we read it.
                held = store.get(touch_marker_key(state, day))
                held_at = _parse((held or {}).get("ts")) if isinstance(held, dict) else None
                if (isinstance(held, dict) and not held.get("sent")
                        and held_at is not None and held_at.date() < ct.date()):
                    claimed = bool(store.compare_and_set(touch_marker_key(state, day), held, pre))
        except Exception as exc:  # noqa: BLE001 - a store without the primitive must not stop the tick
            logger.warning("could not claim the touch marker for D%d: %s", day, exc)
            store.set(touch_marker_key(state, day), pre)
            claimed = True
        if not claimed:
            if hold_appointment_id:
                records.append(_cancel_hold(hold_appointment_id, ghl))
            return dict(base, action="locked", day=day, quiet=True,
                        reason="another worker owns this cadence day", records=records)
    # Last look before the POST. A reply (or a booking, or a fresh approval)
    # that landed after this tick read the row is not in ``state``; the store
    # has it. Sending the day on top of it is SAL-4's D2 going out anyway.
    changed = changed_in_store(state, store, ct)
    if changed:
        try:
            store.delete(touch_marker_key(state, day))  # nothing was sent: the day stays unspent
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not clear touch marker: %s", exc)
        if hold_appointment_id:
            records.append(_cancel_hold(hold_appointment_id, ghl))
        return dict(base, action="stopped", day=day, reason="changed_while_ticking:%s" % changed,
                    records=records)
    # The two times were picked from a registry read made at the top of this
    # tick. Claimed atomically before the POST: a time another lead's card,
    # touch or call took in the meantime is never offered twice (SAL-10). The
    # day is not spent; the next tick picks two times that are still free.
    claim_fields = {"source": "cadence", "day": day}
    claimed_isos = [_iso(s) for s in two]
    if store is not None and claimed_isos:
        try:
            from services.reply_engine import approval as approval_mod

            taken = approval_mod.claim_slots(store, _field(state, "lead_email"), claimed_isos, ct, fields=claim_fields)
        except Exception as exc:  # noqa: BLE001 - an unreadable registry holds the day rather than double-offer
            logger.warning("could not claim the D%d slots for %s: %s", day, email, exc)
            taken = list(claimed_isos)
        if taken:
            try:
                store.delete(touch_marker_key(state, day))  # nothing was sent: the day stays unspent
            except Exception as exc:  # noqa: BLE001
                logger.warning("could not clear touch marker: %s", exc)
            if hold_appointment_id:
                records.append(_cancel_hold(hold_appointment_id, ghl))
            return dict(base, action="slot_taken", day=day, slots=taken, quiet=True, records=records,
                        reason="another lead took %s while this tick ran; retried next tick" % ", ".join(taken))
    result = _send(state, touch, instantly, ct)
    records.append(result)
    failure = send_failed(result)
    if failure:
        if store is not None:
            if nothing_left_the_process(failure):
                try:
                    store.delete(touch_marker_key(state, day))  # decided before the POST: the day may be retried
                except Exception as exc:  # noqa: BLE001
                    logger.warning("could not clear touch marker: %s", exc)
                if claimed_isos:  # the times never reached the lead: back in the pool
                    try:
                        from services.reply_engine import approval as approval_mod

                        approval_mod.release_claimed(store, _field(state, "lead_email"), claimed_isos,
                                                     fields=claim_fields)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("could not release the D%d slots: %s", day, exc)
            else:
                # The request WAS issued and never got a clean answer, so it may
                # already have been accepted. Leaving the {sent: False} marker is
                # what holds the day for the rest of today instead of re-sending
                # the identical body on the next hourly tick.
                logger.warning("D%d to %s failed after the request was issued (%s): holding the day",
                               day, recipient_for(state), failure)
        if hold_appointment_id:
            records.append(_cancel_hold(hold_appointment_id, ghl))
        out = dict(base, action="send_failed", day=day, reason=failure, records=records, touch=touch.to_dict())
        if not nothing_left_the_process(failure):
            out["needs_manual_check"] = True
        if failure == "recipient_mismatch":
            # Nothing re-arms this by itself and every tick would refuse it again.
            # Stop once, say so once, and let Lorenzo point the thread at the
            # right address.
            stop(state, "recipient_mismatch", ct)
            notify_fn(
                "Cadence stopped for %s: the thread belongs to somebody else" % email,
                "D%d was not sent: the last inbound on this thread is not from %s, so the follow-up would answer "
                "the wrong person. Point the lead at the address that actually replied, then re-arm."
                % (day, recipient_for(state)),
                priority="high",
                tags=["warning"],
            )
            out["stopped"] = True
        elif failure == "recipient_unconfirmed":
            out.update(_recipient_hold(state, day, ct, email, notify_fn))
        return out

    (state.cadence or {}).pop("recipient_hold", None)
    (state.cadence or {}).pop("template_hold", None)
    (state.cadence or {}).pop("d1_gate_hold", None)
    if store is not None:
        # The slots were in the body that just went out, so they are reserved
        # before the marker is confirmed: a crash in between used to leave two
        # emailed times with no row in the registry, free for the next lead and
        # free to be re-offered to this one on the very next day.
        reserve_slots(state, two, ct, store, day=day)
        # Confirm the marker before touching the state: from here on the day is
        # spent, whatever fails next.
        store.set(touch_marker_key(state, day), {"ts": ct.isoformat(), "day": day, "sent": True,
                                                 "kind": "would_do" if result.get("shadow", True) else "done",
                                                 "subject": touch.subject, "slots": list(touch.slots),
                                                 "slots_source": touch.slots_source,
                                                 "requires_approval": touch.requires_approval,
                                                 "shadow": bool(result.get("shadow", True)),
                                                 "result_id": result.get("id")})
    else:
        reserve_slots(state, two, ct, store, day=day)

    # Persist the touch before anything else can fail: a crash after this point
    # must never re-send the day.
    kind = "would_do" if result.get("shadow", True) else "done"
    _clear_skip(state)
    rec = _record_touch(state, touch, ct, result, kind)
    post_errors = []  # type: List[str]
    if touch.day == 30:
        # D30 done: the lead stays in Follow Up Later. A GHL hiccup here must not
        # discard the touch we just sent.
        try:
            moved = move_to_follow_up_later(state, ghl, ct, reason="exhausted")
            if isinstance(moved, dict) and moved.get("error"):
                post_errors.append(str(moved["error"]))
        except Exception as exc:  # noqa: BLE001
            logger.warning("move_to_follow_up_later failed for %s: %s", email, exc)
            post_errors.append("follow_up_later: %s" % exc)
    out = dict(base, action=("would_send" if kind == "would_do" else "sent"), day=day, touch=touch.to_dict(),
               records=records, record=rec)
    if hold_error:
        out["hold_error"] = hold_error
    if post_errors:
        out["post_errors"] = post_errors
    return out


HOLD_TITLE_PREFIX = "HOLD: "


def hold_enabled() -> bool:
    """Whether D6 may write a calendar hold in live mode (runbook open item 7).

    Off by default, and safe to turn on: jobs/appointments_tick.is_cadence_hold
    drops events whose TITLE starts with ``HOLD: `` (the title is the
    discriminating half; appointmentStatus "new" alone is not, because a real
    Discovery Call booking is "new" whenever the calendar's auto-confirm is
    off), so a hold is no longer read as a booked call and confirmed to the
    prospect, and _create_hold writes ``to_notify=False`` so GHL does not email
    them a booking notice for a call they never agreed to.

    What it does NOT do is send the prospect anything. The blueprint's D6 is a
    transparent invite in THEIR calendar; this is a private block in Lorenzo's.
    Set CADENCE_D6_HOLD=1 for the private block; see PHASE1_SHADOW_REPORT
    "not built yet" for the real touch."""
    return str(os.environ.get("CADENCE_D6_HOLD", "")).strip().lower() in ("1", "true", "yes", "on")


def _create_hold(state: Any, slot: datetime, ghl: Any, now: datetime) -> Dict[str, Any]:
    """D6 calendar hold on the Discovery Call calendar (guarded). GHL has no
    'free' transparency flag on appointments; the title is prefixed HOLD: so the
    show-rate job and Lorenzo can tell it from a booked call.

    Returns a record carrying ``skipped``/``error`` when no hold was created, so
    the caller falls back to the no-hold body instead of telling the lead about
    a hold that does not exist."""
    start = slot_rules.to_tz(slot)
    end = start + timedelta(minutes=SLOT_MINUTES)
    title = "%sLorenzo <> %s: 15-min %s plan" % (HOLD_TITLE_PREFIX, company_of(state),
                                                 "reactivation" if niche_and_offer(state)[1] == "reactivation" else "outbound")
    contact_id = _field(state, "ghl_contact_id")
    payload = {
        "calendarId": settings.GHL_CALENDAR_ID,
        "contactId": contact_id,
        "startTime": start.isoformat(),
        "endTime": end.isoformat(),
        "title": title,
        "appointmentStatus": "new",
        # the prospect never agreed to this time; GHL must not email them about it
        "toNotify": False,
    }
    if not contact_id:
        # GHL rejects a contactId of "pending" (422) and the whole day used to be
        # lost to that; fall through to the no-hold body instead.
        logger.info("D6 hold skipped for %s: no ghl_contact_id", _field(state, "lead_email"))
        return {"skipped": "no_ghl_contact_id", "payload": payload}
    if ghl is None:
        # shadow: record the intent (that is the deliverable). live: nothing was
        # created, so say so and let the caller fall back to the no-hold body.
        rec = guard_write("ghl", "create_appointment", payload)
        if not rec.get("shadow"):
            rec["skipped"] = "no_ghl_client"
        return rec
    try:
        rec = ghl.create_appointment(settings.GHL_CALENDAR_ID, contact_id, start.isoformat(), end.isoformat(), title,
                                     appointment_status="new", to_notify=False)
    except TypeError:  # older shared.ghl without to_notify
        logger.warning("shared.ghl.create_appointment has no to_notify; the hold would email the prospect")
        return {"skipped": "ghl_cannot_suppress_notification", "payload": payload}
    if rec is None:  # live without a Private Integration token: nothing was created
        return {"skipped": "ghl_write_returned_nothing", "payload": payload}
    return rec if isinstance(rec, dict) else {"result": rec}


def confirm_calendar_invite(state: Any, slot: Union[str, datetime], ghl: Any, now: datetime) -> Dict[str, Any]:
    """For the approval endpoint: Lorenzo tapped Approve on the D6 card before
    the tick ran; create the hold right away (guarded)."""
    return _create_hold(state, slot_rules.parse_iso(slot), ghl, now)


# ---------------------------------------------------------- serialization
def state_to_dict(state: Any) -> Dict[str, Any]:
    if hasattr(state, "to_store"):
        return state.to_store()
    if hasattr(state, "model_dump"):
        return state.model_dump(mode="json")
    if dataclasses.is_dataclass(state):
        return dataclasses.asdict(state)
    return dict(vars(state))


def state_from_dict(data: Dict[str, Any]) -> Any:
    if hasattr(LeadState, "from_store"):
        try:
            return LeadState.from_store(data)
        except Exception as exc:  # noqa: BLE001 - fall through to the tolerant path
            logger.warning("LeadState.from_store failed (%s); using tolerant loader", exc)
    if hasattr(LeadState, "model_validate"):
        return LeadState.model_validate(data)
    return LeadState(**data)


def _resume_leg(via: Optional[str]) -> str:
    """Where a Resume link went, for a digest line (never the link)."""
    return "in the push" if via == RESUME_LINK_VIA_NTFY else "in the email"


def _resume_digest(result: Dict[str, Any]) -> str:
    """The digest's word on a template_unapproved stop's Resume link: where it
    went, or why none went and what to set (never the link itself)."""
    if result.get("resume_link"):
        return "Then open the Resume link %s (a fresh one comes each morning for up to 2 weeks)" % _resume_leg(
            result.get("resume_link_via"))
    if result.get("resume_link_missing") == "no_channel":
        return ("No Resume link was sent: no channel can carry one (set NTFY_TOKEN, or NOTIFY_EMAIL, "
                "GMAIL_SENDER_EMAIL and GMAIL_APP_PASSWORD; the next tick then sends it)")
    return ("No Resume link was sent: none could be signed (set BASE_URL and REPLY_ENGINE_SECRET; the next tick "
            "then sends it)")


def summarize_touch(result: Dict[str, Any]) -> str:
    """One digest line per lead for Lorenzo's notification."""
    action = result.get("action")
    email = result.get("lead_email")
    day = result.get("day")
    touch = result.get("touch") or {}
    slots = touch.get("slots") or []
    when = ""
    if slots:
        try:
            when = slot_rules.format_slots([slot_rules.parse_iso(s) for s in slots])
        except (ValueError, TypeError):
            when = ", ".join(slots)
    template_id = result.get("template_id") or touch.get("template_id")
    if action in ("would_send", "sent"):
        flag = " (needs your OK for the invite)" if touch.get("requires_approval") else ""
        tid = ", %s" % template_id if template_id else ""
        return "D%s -> %s: %s%s [%s%s]" % (day, email, when or "no times (yes/no close)", flag, action, tid)
    if action == "held_template":
        # the template id, the gate's reason and what fixes it, never the body
        reason = result.get("reason")
        if hold_cause(reason) == "system":
            return ("D%s -> %s: HELD, not sent: template auto-send is off for every ladder (%s). %s Nothing is "
                    "stopped, the day is retried every tick" % (day, email, reason, hold_advice(reason)))
        return ("D%s -> %s: HELD, not sent: template %s is not auto-sendable (%s). %s The day is retried every "
                "tick; after %d business days held the ladder stops" % (
                    day, email, template_id or "(none)", reason, hold_advice(reason), TEMPLATE_HOLD_STALL_DAYS))
    if action == "stopped" and result.get("reason") == "template_unapproved":
        return ("D%s -> %s: cadence stopped, template %s was held %s business days (%s). %s %s" % (
                    day, email, template_id or "(none)", result.get("days"), result.get("held_reason"),
                    hold_advice(result.get("held_reason")), _resume_digest(result)))
    if action == "resume_link_sent":
        return ("D%s -> %s: cadence still stopped on template %s (%s), %s %s" % (
            day, email, template_id or "(none)", result.get("held_reason"),
            "its ids are approved now, a Resume link was sent" if result.get("ready")
            else "a fresh Resume link was sent", _resume_leg(result.get("resume_link_via"))))
    if action == "stopped" and result.get("reason") == "open_card":
        return "%s: cadence stopped, a reply of theirs is waiting on your approval" % email
    if action in ("stopped", "follow_up_later"):
        return "%s: cadence stopped (%s)" % (email, result.get("reason"))
    if action == "awaiting_invite_ok":
        return "D6 -> %s: waiting on your OK for the %s CT hold" % (email, when or result.get("slot"))
    if action == "veto_window_opened":
        return "D1 -> %s: veto window open, sends in 30 minutes" % email
    if action == "blocked_copy":
        return "D%s -> %s: BLOCKED, copy check failed (%s)" % (day, email, ", ".join(result.get("problems") or []))
    if action == "blocked_copy_stalled":
        return "D%s -> %s: BLOCKED %s days running (%s), cadence stopped" % (
            day, email, result.get("days"), ", ".join(result.get("problems") or []))
    if action == "veto_undeliverable" and result.get("reason") == "no_base_url":
        return ("D1 -> %s: NOT SENT, held because BASE_URL is unset or local-only (the Veto link could not "
                "work). Set BASE_URL; the next tick opens the veto window." % email)
    if action == "send_failed" and result.get("reason") == "recipient_unconfirmed":
        if result.get("escalated"):
            return ("D%s -> %s: NOT SENT, recipient could not be confirmed %s times, cadence held. Check the "
                    "thread, then re-arm." % (day, email, result.get("attempts")))
        return ("D%s -> %s: NOT SENT, recipient could not be confirmed (attempt %s of %d), retrying next tick"
                % (day, email, result.get("attempts"), RECIPIENT_HOLD_MAX_ATTEMPTS))
    if action == "veto_undeliverable":
        return ("D1 -> %s: NOT SENT, the Veto link could not be delivered, so the auto-send is held. "
                "Set NTFY_TOKEN or a NOTIFY_EMAIL leg, then re-arm." % email)
    if action == "send_failed" and result.get("reason") == "previous_attempt_unconfirmed":
        return ("D%s -> %s: an earlier attempt today was never confirmed, day held. Confirm by hand in the "
                "Instantly inbox before tomorrow's tick." % (day, email))
    if action == "send_failed":
        extra = ", confirm by hand in the Instantly inbox" if result.get("needs_manual_check") else ""
        return "D%s -> %s: NOT SENT (%s), day not advanced%s" % (day, email, result.get("reason"), extra)
    if action == "error":
        return "%s: cadence tick errored (%s), nothing sent, day not advanced" % (email, result.get("error"))
    if action == "already_sent":
        return "D%s -> %s: already sent on an earlier tick, state repaired" % (day, email)
    if action == "awaiting_fresh_draft":
        if result.get("card_open") is False:
            return ("%s: replied mid-cadence and raised no card (nothing to approve), cadence stays stopped. "
                    "Read the reply in the Instantly inbox" % email)
        if "card_open" in result and result.get("card_open") is None:
            return "%s: replied mid-cadence, cadence stopped (its cards could not be read)" % email
        return "%s: replied mid-cadence, waiting on your approved answer to resume" % email
    if action == "resumed_after_auto_reply":
        return "%s: auto-responder paused the cadence, resuming %s" % (email, result.get("next_send_at") or "next business day")
    if action in ("skipped_no_slots", "skipped_unverified_slots", "vetoed"):
        return "D%s -> %s: %s" % (day, email, action)
    return "%s: %s" % (email, action)


# --------------------------------------------------------- scheduled entrypoint
def tick(now: Optional[datetime] = None, store: Any = None, dry_run: bool = False) -> Dict[str, Any]:
    """Zero-argument entrypoint for the Modal ``cadence_tick`` schedule.

    ``services/reply_engine/modal_app.py`` looks for ``cadence.tick`` and logged
    ``entrypoint_missing`` because the run body lives in ``jobs/cadence_tick.py``.
    This is the one wrapper that joins them: it builds the same clients the CLI
    builds, uses the one shared store (``shared.store.get_store``) and writes the
    same Job_Log row, so the scheduled tick and ``python3 -m jobs.cadence_tick``
    are the same run.
    """
    from shared.store import get_store

    from jobs import cadence_tick as job

    # llm.is_fake(), not == "1": LLM_FAKE=true would otherwise skip the fake
    # registry here and make real, billed model calls inside a dry run.
    if llm.is_fake():
        from services.reply_engine.classify import ensure_offline_fakes

        ensure_offline_fakes()
    ts = slot_rules.to_tz(slot_rules.ensure_aware(now)) if now is not None else datetime.now(TZ)
    store = store if store is not None else get_store()
    instantly, ghl = job._clients(dry_run)
    try:
        return job.run(ts, store, instantly, ghl, dry_run=dry_run)
    finally:
        for client in (instantly, ghl):
            try:
                if client is not None:
                    client.close()
            except Exception:  # noqa: BLE001 - closing a client must not fail the tick
                logger.warning("could not close %r", client)
