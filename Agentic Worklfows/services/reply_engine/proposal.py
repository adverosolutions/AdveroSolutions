"""Proposal generator and the SOP-009 verbal-commit path (Blueprint S7).

Same day as the call, from whatever record of the call exists:

1. a Fireflies transcript, when one is handed in (there is no Fireflies API
   key in any .env today, so this is a file path Lorenzo passes, never a live
   pull);
2. Lorenzo's own notes;
3. the reply thread, read with GETs against Instantly.

The proposal is assembled from config/offers.md, never from memory: the
mechanism, the pricing answer, the guarantee, the minimum to start and the one
allowed proof point all come through services.reply_engine.draft, which is the
module that parses the offer sheet. A figure the sheet marks TO CONFIRM (today
the $2,500 to $5,000 monthly retainer) can never appear: ``copy_problems``
rejects the whole document if it does.

**Nothing here sends anything.** ``build_proposal`` returns a draft,
``write_draft`` files it under ``.tmp/proposals/``, and ``deliver`` pushes a
card to Lorenzo and writes a GHL note through the guarded client. GHL
Documents and PandaDoc both need a human paste (no public create-document
endpoint exists in shared/ghl.py, and there is no PandaDoc account), so the
result says ``manual`` for that step rather than pretending it happened.

The verbal-commit path is three drafts, not three sends: the payment link
within the hour, then SOP-009's day 1 and day 3 nudges, each with the moment
it becomes due and each validated against the same copy rules as a cold reply.
"""
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from shared import llm, paths, settings, slots
from shared.settings import TZ

from services.reply_engine import draft as draft_mod
from services.reply_engine import precall

logger = logging.getLogger("reply_engine.proposal")

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
CLAIM_PREFIX = "proposal:"
PAYMENT_LINK_ENV = "PAYMENT_LINK_URL"
FIREFLIES_ENV = "FIREFLIES_API_KEY"
# A proposal is longer than a reply, so draft.validate_draft's 1500 character
# cap does not apply; everything else it checks does.
MAX_PROPOSAL_CHARS = 6000
# SOP-009 verbal commit: link within the hour, nudges on day 1 and day 3.
VERBAL_COMMIT_OFFSETS = (("immediate", timedelta(minutes=30)),
                         ("day1", timedelta(days=1)),
                         ("day3", timedelta(days=3)))
_BLOCK_RE = re.compile(r"^##\s+(\S+)\s*$")
_HTML_COMMENT_RE = re.compile(r"(?s)<!--.*?-->")
_SUBJECT_RE = re.compile(r"^Subject:\s*(.+)$", re.M)


# --------------------------------------------------------------- models
@dataclass
class CallInputs(object):
    source: str = "none"              # fireflies | notes | thread | none
    transcript: Optional[str] = None
    notes: Optional[str] = None
    thread: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["transcript"] = bool(self.transcript)
        return out


@dataclass
class EmailDraft(object):
    key: str
    subject: str
    body: str
    due_iso: str
    problems: List[str] = field(default_factory=list)

    @property
    def sendable(self) -> bool:
        return not self.problems

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["sendable"] = self.sendable
        return out


@dataclass
class Proposal(object):
    lead_email: Optional[str]
    company: str
    first_name: str
    campaign_key: str
    call_date: str
    text: str
    contact_id: Optional[str] = None
    appointment_id: Optional[str] = None
    opportunity_id: Optional[str] = None
    source: str = "none"
    model: str = "template"
    rationale: str = ""
    problems: List[str] = field(default_factory=list)
    held_evidence: str = "unknown"
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def sendable(self) -> bool:
        return not self.problems

    @property
    def key(self) -> str:
        return claim_key(self.appointment_id or self.lead_email, self.call_date)

    @property
    def title(self) -> str:
        return "Proposal draft ready: %s (%s)" % (self.company, self.campaign_key)

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["key"] = self.key
        out["sendable"] = self.sendable
        return out


# ------------------------------------------------------------ validation
def copy_problems(text: str, campaign_key: Optional[str] = None,
                  allow_terms: Optional[List[str]] = None,
                  max_chars: int = MAX_PROPOSAL_CHARS,
                  quoted: Optional[List[str]] = None) -> List[str]:
    """Every check draft.validate_draft runs, minus its reply-length cap.

    Using the same validator is the point: the banned vocabulary, the
    offers.md figure list, the TO CONFIRM refusal, the never-mix-the-offers
    rules and the signature line stay identical to the ones a cold reply obeys,
    and they cannot drift apart.

    ``quoted`` are spans the engine did not write: the verbatim recap of what
    the prospect said, and Lorenzo's own call notes. They are blanked before
    every check, because validating them marks the document BLOCKED for the
    prospect's punctuation and the prospect's numbers. A sampled read of 50 real
    inbound replies found 14 with an exclamation mark and 7 with an em or en
    dash, so at least a quarter of real proposals were stamped BLOCKED with a
    reason that pointed Lorenzo at the wrong text. Anything found inside a quote
    comes back through ``quote_notes`` as a check, not as a block.
    """
    scanned = draft_mod._blank_out(text or "", quoted) if quoted else (text or "")  # noqa: SLF001
    problems = [p for p in draft_mod.validate_draft(scanned, campaign_key=campaign_key, allow_terms=allow_terms)
                if not p.startswith("too long")]
    if len(text or "") > max_chars:
        problems.append("too long (%d chars, limit %d)" % (len(text or ""), max_chars))
    return problems


def quote_notes(quoted: Optional[List[str]], campaign_key: Optional[str] = None,
                allow_terms: Optional[List[str]] = None) -> List[str]:
    """Checks raised by the prospect's own words, phrased as their words.

    Their sentence is not our copy, so it never blocks. It is still worth
    Lorenzo's eyes: a prospect who wrote "our last agency charged us $2,500 a
    month" has put a TO CONFIRM figure into a document he is about to send back
    to them.
    """
    text = "\n".join(q for q in (quoted or []) if (q or "").strip()).strip()
    if not text:
        return []
    raised = [p for p in draft_mod.validate_draft(text + "\n\nLorenzo", campaign_key=campaign_key,
                                                  allow_terms=allow_terms)
              if not p.startswith("too long") and "signature" not in p]
    return ["the recap quotes them verbatim and the quote contains %s. Those are their words, not our copy, so it "
            "is not blocking. Read it once before you send." % p for p in raised]


def payment_link() -> Optional[str]:
    link = (os.environ.get(PAYMENT_LINK_ENV) or "").strip()
    return link or None


def fireflies_status() -> Dict[str, Any]:
    """There is no Fireflies key in any .env, so the transcript is a file
    Lorenzo hands in. Stated explicitly so a missing transcript is never read
    as "the call produced nothing"."""
    key = (os.environ.get(FIREFLIES_ENV) or "").strip()
    if key:
        return {"available": True, "reason": "api_key_present", "pull": "not implemented; pass --transcript"}
    return {"available": False, "reason": "no_fireflies_api_key", "pull": "pass --transcript <file>"}


# --------------------------------------------------------------- inputs
def gather_inputs(lead_email: Optional[str], instantly=None, transcript_path: Optional[str] = None,
                  notes: Optional[str] = None, thread: Optional[List[Any]] = None) -> CallInputs:
    """The best record of the call that exists, and what is missing."""
    out = CallInputs()
    if transcript_path:
        try:
            out.transcript = Path(transcript_path).read_text(encoding="utf-8")
            out.source = "fireflies"
        except OSError as exc:  # noqa: BLE001
            out.warnings.append("transcript %s could not be read (%s)" % (transcript_path, exc))
    if not out.transcript and notes:
        out.source = "notes"
    out.notes = notes
    if thread is not None:
        rows = thread
    elif instantly is not None and lead_email:
        rows, error = precall.fetch_thread(instantly, lead_email)
        if error:
            out.warnings.append("thread read failed (%s)" % error)
    else:
        rows = []
    out.thread = [r.to_dict() if hasattr(r, "to_dict") else dict(r) for r in rows or []]
    if out.source == "none" and out.thread:
        out.source = "thread"
    if out.source == "none":
        out.warnings.append("no transcript, no notes and no thread: the recap section will be empty on purpose")
    if not out.transcript:
        out.warnings.append("no Fireflies transcript (%s); the recap is built from %s"
                            % (fireflies_status()["reason"], out.source))
    return out


# Scheduling and acknowledgement language. A message that is only this is
# booking chatter, not discovery, and it has no business in a client-facing
# "What you told me" section.
_SCHEDULING_RE = re.compile(
    r"(works? for me|work for me|reschedul|re-?schedul|availabilit|available|let me know|"
    r"talk (?:to|with) you then|see you (?:then|on|at)|sounds good|no problem|thank you|thanks|"
    r"best ?regards|regards|sincerely|looking forward|calendar (?:invite|link)|zoom link|"
    r"get together|my (?:cell|number|phone))", re.I)
# One business noun is enough to keep a short message: it is then about their
# operation, not about what time to meet.
_BUSINESS_NOUN_RE = re.compile(
    r"(accounts?\b|client|customer|proposal|contract|revenue|leads?\b|list\b|database|crm|"
    r"placement|candidate|hiring|bookkeep|tax return|cleaning|janitorial|facilit|invoice|"
    r"renew|cancel|churn|dormant|bid\b|tender|inquir|enquir|follow ?up|pipeline|quote[ds]?\b|"
    r"walkthrough|square (?:feet|foot)|jobs?\b|staff|payroll|turnover)", re.I)
_SIGNOFF_RE = re.compile(
    r"^(thanks|thank you(?: so much)?|best|best ?regards|kind regards|warm regards|regards|"
    r"sincerely|cheers|talk soon|br)[,.\s]*$", re.I)
_PHONE_ONLY_RE = re.compile(r"^[\s()+\-./\d]{7,}$")
# A sign-off does not have to be on its own line. The live cleaning thread ends
# "... that works for me . Best reagrds ; Ilmi Curovic ShinigArmorCleaningNJ,
# LLC" all on one line, and the company name inside that signature was enough to
# make the chatter filter read the message as being about their business.
_SIGNOFF_STRONG_RE = re.compile(
    # "Best reagrds" is what the live cleaning thread actually says, so the
    # word after "best" is matched loosely rather than spelled out.
    r"(\bbest\s+r\w{3,9}\b|\b(?:kind|warm)\s+r\w{3,9}\b|\bregards\b|\bsincerely\b|\bcheers\b|"
    r"\btalk soon\b|\ball the best\b)", re.I)
# "thanks" and "thank you" appear mid-sentence far too often ("thank you for
# you're email , right know i don't have any accounts...") to cut on blindly, so
# they only end a message when they start a new sentence.
_SIGNOFF_WEAK_RE = re.compile(r"(?:(?<=[.!?\n])|^)\s*\b(thanks|thank you)\b", re.I)
# How much may follow a sign-off and still be a signature rather than content.
MAX_SIGNATURE_TAIL = 80
# Under this many words a message has to carry a business noun to survive.
MIN_RECAP_WORDS = 40


def _cut_signature(flat: str) -> str:
    """Drop the sign-off and everything after it, when that tail is short."""
    body = flat or ""
    cut = None
    for pattern in (_SIGNOFF_STRONG_RE, _SIGNOFF_WEAK_RE):
        for match in pattern.finditer(body):
            if len(body) - match.start() <= MAX_SIGNATURE_TAIL:
                cut = match.start() if cut is None else min(cut, match.start())
                break
    if cut is None:
        return body
    return body[:cut].rstrip(" ,;.:-–—")


def is_scheduling_chatter(text: str) -> bool:
    """True when this inbound message says nothing about their business.

    The live threads are the case this exists for. Taxfo's proposal opened with
    three bullets: a price question, "Thursday 4pm Eastern time. works for me
    237-791-5700", and "I am available every day 3pm-6pm Estern time. let me
    know what wirks." Zero discovery content, her phone number and her typos, in
    a document Lorenzo is told to paste into GHL Documents and send her.
    """
    body = (text or "").strip()
    if not body:
        return True
    if _BUSINESS_NOUN_RE.search(body):
        return False
    if len(body.split()) >= MIN_RECAP_WORDS:
        return False
    return True


def clean_quote(text: Optional[str]) -> str:
    """One inbound message, ready to be quoted back to them.

    Phone numbers are blanked (``slots.strip_phone_numbers``) and the sign-off
    is dropped, so a recap bullet never reproduces a private number or ends in
    "Best reagrds".
    """
    lines = []  # type: List[str]
    for raw in (text or "").splitlines():
        blanked = slots.strip_phone_numbers(raw)
        if blanked != raw and len(blanked.split()) < 6:
            # the line was a phone number with a couple of words around it
            # ("Call me on 237-791-5700"); blanking it leaves a fragment
            continue
        lines.append(blanked.rstrip())
    while lines:
        last = lines[-1].strip()
        if not last or _SIGNOFF_RE.match(last) or _PHONE_ONLY_RE.match(last):
            lines.pop()
            continue
        break
    flat = re.sub(r"\s+", " ", " ".join(l.strip() for l in lines if l.strip())).strip()
    return _cut_signature(flat).strip()


def _recap(inputs: CallInputs, limit: int = 4) -> Tuple[List[str], List[str]]:
    """(display bullets, the raw spans the engine did not write).

    The second list is what ``copy_problems`` blanks: those spans are the
    prospect's own words or Lorenzo's own notes, and validating them as if they
    were our copy is how a normal reply containing "!" blocked a whole proposal.
    """
    out = []  # type: List[str]
    quotes = []  # type: List[str]
    if inputs.notes:
        for line in inputs.notes.splitlines():
            line = line.strip().lstrip("-* ").strip()
            if line:
                out.append(line)
                quotes.append(line)
            if len(out) >= limit:
                break
        if out:
            # Lorenzo's own notes are the call. Quoting pre-call emails
            # underneath them invites a recap that contradicts what was
            # actually agreed, so the notes are exclusive.
            return out, quotes
    if inputs.transcript and len(out) < limit:
        out.append("From the call transcript on file (%d characters), see the transcript for the full record."
                   % len(inputs.transcript))
    if len(out) < limit:
        # Longest first, then back into date order for display. Reverse
        # chronological put "please reschedule for Wednesday" at the top of the
        # live proposal and pushed the sentence that actually defines the deal
        # ("i don't have any accounts... prospect accounts that we sent the
        # proposals") to the bottom, truncated.
        inbound = []
        for row in inputs.thread or []:
            if row.get("direction") != "in":
                continue
            cleaned = clean_quote(row.get("text"))
            if not cleaned or is_scheduling_chatter(cleaned):
                continue
            inbound.append((row, cleaned))
        chosen = sorted(sorted(inbound, key=lambda pair: len(pair[1]), reverse=True)[: limit - len(out)],
                        key=lambda pair: str(pair[0].get("when_iso") or ""))
        for row, cleaned in chosen:
            text = precall._shorten(cleaned, 300)  # noqa: SLF001 - one shortener for the engine
            if not text:
                continue
            out.append("You wrote on %s: %s" % (precall._stamp(row.get("when_iso", "")), text))  # noqa: SLF001
            quotes.append(text)
    return out, quotes


def recap_lines(inputs: CallInputs, limit: int = 4) -> List[str]:
    """What the call record actually shows, with its source. Never invented.

    A proposal that opens with three bullets nobody said is worse than one that
    opens with the prospect's own sentence, so every bullet here is either
    Lorenzo's own note or a verbatim quote from the thread. Booking chatter is
    not a bullet: when nothing substantive survives, the section is a hole with
    an instruction in it rather than three lines about what time to meet.
    """
    return _recap(inputs, limit)[0]


def mechanism_warnings(inputs: CallInputs, campaign_key: str) -> List[str]:
    """Where the call record contradicts the offer sheet's mechanism line.

    The live cleaning booking is the case this exists for: she replied that she
    had lost no accounts, and the reactivation mechanism in offers.md opens
    with "every account that cancelled". Sending that sentence back to her
    unedited is how a proposal loses a deal it had already won on the call.
    """
    from services.reply_engine.precall import rank_objections

    rows = []
    for row in inputs.thread or []:
        rows.append(precall.Message(when_iso=row.get("when_iso", ""), direction=row.get("direction", "in"),
                                    sender=row.get("sender", ""), subject=row.get("subject", ""),
                                    text=row.get("text", "")))
    hits = {h["id"] for h in rank_objections(rows, campaign_key) if h["why"].startswith("they wrote")}
    out = []  # type: List[str]
    if "nothing_to_reactivate" in hits and campaign_key.endswith("_reactivation"):
        out.append("the thread says they did not lose accounts. The mechanism line below is the lost-account "
                   "version from offers.md. Reframe it to the list they do have (unanswered proposals, old "
                   "inquiries) before you send this.")
    if "already_tried" in hits:
        out.append("they mentioned a previous attempt. Say what is different in one line before the pricing "
                   "section, or the proposal answers a question they did not ask.")
    return out


# ------------------------------------------------------------- the offer
def deposit_terms(campaign_key: str) -> Tuple[str, List[str]]:
    """The 50 percent deposit line, or the reason there is none.

    Blueprint S7 says "50% deposit". config/offers.md says the three
    reactivation offers are $0 up front and commission only. Both cannot be
    true in the same document, and the offer sheet wins (CLAUDE.md: pricing and
    proof only from config/offers.md). So a retainer offer carries the deposit
    and a commission offer says out loud that there is nothing to deposit, with
    a note back to Lorenzo that the blueprint line needs updating.
    """
    if campaign_key.endswith("_reactivation"):
        return ("There is no deposit and no setup fee. You pay nothing until an account comes back, and nothing at "
                "all if none of them do.",
                ["deposit: offers.md says $0 up front for %s, so the blueprint's 50 percent deposit does not apply. "
                 "Confirm which one is right." % campaign_key])
    return ("Half of the setup fee starts the work and the balance is due when the first sequences go live. The "
            "monthly retainer starts in the same week.",
            ["deposit: the retainer figure is marked TO CONFIRM in offers.md, so this proposal states the deposit "
             "structure without a number. Give me the number and it goes in."])


def attribution_line(campaign_key: str) -> Optional[str]:
    if campaign_key.endswith("_reactivation"):
        return ("An account counts as mine when it signs within 6 months of the first message in the sequence. "
                "Anything that signs after that window is yours, free.")
    return None


# ------------------------------------------------------------- skeleton
def skeleton(company: str, first_name: str, campaign_key: str, call_date: str,
             inputs: CallInputs) -> Tuple[str, List[str]]:
    return skeleton_with_quotes(company, first_name, campaign_key, call_date, inputs)[:2]


def skeleton_with_quotes(company: str, first_name: str, campaign_key: str, call_date: str,
                         inputs: CallInputs) -> Tuple[str, List[str], List[str]]:
    """(document, notes for Lorenzo, the spans the engine did not write)."""
    block = precall.offer_block(campaign_key)
    deposit, notes = deposit_terms(campaign_key)
    recap, quotes = _recap(inputs)
    lines = [
        "# Proposal for %s" % company,
        "",
        "Prepared by Lorenzo Villarreal, AdveroSolutions. %s." % call_date,
        "",
        "## What you told me",
    ]
    if recap:
        lines.extend("- %s" % r for r in recap)
    else:
        lines.append("- (Nothing on file from the call. Write two lines here before you send this.)")
    lines += [
        "",
        "## What I will build",
        block["mechanism"],
        "",
        "## What it costs",
        block["pricing_answer"],
        "",
        deposit,
    ]
    attribution = attribution_line(campaign_key)
    if attribution:
        lines += ["", "## How we count a win", attribution,
                  "I invoice monthly against a scorecard that shows every account the sequences touched and what "
                  "came back."]
    lines += [
        "",
        "## What I need from you to start",
        block["minimum"],
        "",
        "## Why me",
        block["proof"] or "",
        "",
        "## Next step",
        "Say yes and I will send the link today. The first sequences are ready to look at this week, and you approve "
        "every message before it goes anywhere.",
        "",
        "Lorenzo",
    ]
    return "\n".join(l for l in lines if l is not None).strip() + "\n", notes, quotes


def _system_prompt(skel: str, campaign_key: str) -> str:
    try:
        template = (PROMPTS_DIR / "proposal_system.md").read_text(encoding="utf-8")
    except OSError:
        template = "Return only the proposal. Change no number."
    template = _HTML_COMMENT_RE.sub("", template).strip()
    return "%s\n\n--- OFFER SHEET (%s) ---\n%s\n\n--- SKELETON ---\n%s" % (
        template, campaign_key, settings.OFFERS_MD or "", skel)


# ------------------------------------------------------------------ build
def call_date_for(appointment: Dict[str, Any], now: datetime) -> str:
    """The call's OWN date in Central, as ``YYYY-MM-DD``.

    ``jobs.precall_tick.proposal_due`` keeps the window open until the end of
    the call's day plus a three hour floor, which crosses midnight for any call
    starting after about 20:40 CT. A claim keyed on ``now.date()`` therefore let
    a 22:30 call be drafted twice, once before midnight and once after, and the
    second document was dated the wrong day for the client.
    """
    try:
        return slots.to_tz(slots.parse_iso(appointment["start_iso"]), TZ).date().isoformat()
    except (ValueError, TypeError, KeyError):
        return slots.to_tz(slots.ensure_aware(now, TZ), TZ).date().isoformat()


def claim_key(appointment_id: Any, call_date: str) -> str:
    return "%s%s:%s" % (CLAIM_PREFIX, appointment_id, call_date)


def already_drafted(store, appointment_id: Any, call_date: str) -> bool:
    """Has this call already produced its proposal today?

    Checked by the caller BEFORE the model is invoked. The claim used to be
    taken inside ``deliver()``, after ``gather_inputs`` (two Instantly GETs) and
    ``build_proposal`` (a billed claude-opus-5 turn) had already run, so the
    5-minute tick paid for a proposal on every pass of the whole proposal window
    and threw all but the first away.
    """
    if store is None:
        return False
    return bool(store.get(claim_key(appointment_id, call_date)))


def _niche_offer_of_key(key: str) -> Tuple[str, str]:
    niche, _, kind = (key or "").partition("_")
    return niche, ("reactivation" if kind == "reactivation" else "outbound")


def build_proposal(
    lead: Dict[str, Any],
    now: datetime,
    inputs: Optional[CallInputs] = None,
    instantly=None,
    use_llm: Optional[bool] = None,
    held_evidence: str = "unknown",
    campaign_key: Optional[str] = None,
    call_date: Optional[str] = None,
) -> Proposal:
    """One proposal draft. ``lead`` is the appointment/contact dict.

    Keys read: id, contact_id, opportunity_id, email, first_name, company,
    niche, offer, campaign_id, campaign_key, start_iso.

    ``campaign_key`` is the offer the brief for this same call resolved. Pass it
    whenever it is known: the brief recovers the campaign from the Instantly
    lead record and this used to read only ``lead['campaign_id']``, which
    ``appointments_tick.normalise_ghl_event`` never sets, so one call could be
    briefed on cleaning_trigger and proposed on cleaning_reactivation, with a
    different price, different deposit terms and the other offer type's proof.
    """
    now = slots.to_tz(slots.ensure_aware(now, TZ), TZ)
    email = (lead.get("email") or lead.get("lead_email") or "").strip().lower() or None
    if inputs is None:
        inputs = gather_inputs(email, instantly=instantly)
    from services.reply_engine import show_rate

    resolved = precall.resolve_offer(lead)
    if not resolved["campaign_matched"] and instantly is not None and email:
        # Same lookup order as precall.build_brief: the campaign the thread
        # really came from beats a guess from tags or the company name.
        crm = precall.instantly_lead(instantly, email)
        if crm:
            resolved = precall.resolve_offer(lead, crm)
    if campaign_key and campaign_key in draft_mod.PRICING:
        key = campaign_key
        niche, offer = _niche_offer_of_key(key)
        if resolved["niche"] != "generic":
            niche = resolved["niche"]
    else:
        key, niche, offer = resolved["key"], resolved["niche"], resolved["offer"]
    company = show_rate.company_of(lead)
    first_name = show_rate.first_name_of(lead)
    call_day = call_date or call_date_for(lead, now)
    prepared_on = _prepared_on(call_day, now)
    skel, notes, quotes = skeleton_with_quotes(company, first_name, key, prepared_on, inputs)
    notes = notes + mechanism_warnings(inputs, key)
    terms = [t for t in (company, first_name, lead.get("contact_name")) if t]
    text, model, rationale = skel, "template", "skeleton from config/offers.md (%s)" % key

    call_llm = (not llm.is_fake()) if use_llm is None else use_llm
    if call_llm:
        record = inputs.transcript or inputs.notes or "\n".join(
            "%s %s: %s" % (r.get("direction"), r.get("when_iso"), r.get("text")) for r in inputs.thread)
        user = "Prospect: %s at %s\nCall record source: %s\n<<<\n%s\n>>>" % (
            first_name, company, inputs.source, (record or "")[:8000])
        try:
            polished = llm.complete("proposal", _system_prompt(skel, key), user, max_tokens=1600)
            polished = polished.strip() if isinstance(polished, str) else ""
            probs = copy_problems(polished, campaign_key=key, allow_terms=terms, quoted=quotes)
            if polished and not probs:
                text, model = polished, llm.model_for("proposal")
                rationale += "; polished by %s" % model
            else:
                logger.warning("LLM proposal rejected (%s); using the skeleton", probs or "empty")
                rationale += "; LLM proposal rejected (%s)" % ("; ".join(probs) or "empty")
        except Exception as exc:  # noqa: BLE001 - a model hiccup must not lose the proposal
            logger.warning("proposal LLM failed: %s", exc)
            rationale += "; LLM failed (%s)" % exc

    problems = copy_problems(text, campaign_key=key, allow_terms=terms, quoted=quotes)
    notes = notes + quote_notes(quotes, campaign_key=key, allow_terms=terms)
    if niche == "generic":
        # The brief for this same call prints "check it before you quote
        # anything". A clean-looking document that silently commits to the
        # default offer is far more likely to go out unedited than one carrying
        # the same warning, so this one carries it as a BLOCKED line.
        problems = problems + ["niche could not be determined from the booking or the campaign; this document is the "
                               "%s default offer. Confirm the offer, the pricing and the proof point against "
                               "config/offers.md before you send it" % draft_mod.GENERIC_KEY]
        notes = notes + ["the niche could not be matched to a campaign, so the whole offer block is the %s default"
                         % draft_mod.GENERIC_KEY]
    return Proposal(
        lead_email=email,
        company=company,
        first_name=first_name,
        campaign_key=key,
        call_date=call_day,
        text=text,
        contact_id=lead.get("contact_id"),
        appointment_id=str(lead.get("id")) if lead.get("id") is not None else None,
        opportunity_id=lead.get("opportunity_id"),
        source=inputs.source,
        model=model,
        rationale=rationale,
        problems=problems,
        held_evidence=held_evidence,
        meta={
            "built_at": now.isoformat(),
            "niche": niche,
            "offer": offer,
            "campaign_matched": resolved["campaign_matched"] or bool(campaign_key),
            "campaign_id": resolved["campaign_id"],
            "notes_for_lorenzo": notes + list(inputs.warnings),
            "fireflies": fireflies_status(),
            "stage_hint": "proposal_sent",
            "quoted_spans": quotes,
            "inputs": inputs.to_dict(),
        },
    )


def _prepared_on(call_day: str, now: datetime) -> str:
    """'September 23, 2026' for the call's own date, not the clock's."""
    try:
        return datetime.strptime(call_day, "%Y-%m-%d").strftime("%B %d, %Y")
    except (ValueError, TypeError):
        return slots.to_tz(slots.ensure_aware(now, TZ), TZ).strftime("%B %d, %Y")


# ------------------------------------------------- SOP-009 verbal commit
class _SafeDict(dict):
    def __missing__(self, key):
        return "{%s}" % key


def load_verbal_blocks() -> Dict[str, str]:
    try:
        text = (PROMPTS_DIR / "proposal_verbal_commit.md").read_text(encoding="utf-8")
    except OSError as exc:  # noqa: BLE001
        logger.warning("could not read proposal_verbal_commit.md: %s", exc)
        return {}
    out = {}  # type: Dict[str, str]
    current, buf = None, []  # type: Optional[str], List[str]
    for line in text.splitlines():
        match = _BLOCK_RE.match(line.strip())
        if match:
            if current:
                out[current] = "\n".join(buf).strip()
            current, buf = match.group(1), []
            continue
        if current:
            buf.append(line)
    if current:
        out[current] = "\n".join(buf).strip()
    return out


def verbal_commit_drafts(proposal: Proposal, now: datetime, link: Optional[str] = None) -> List[EmailDraft]:
    """The SOP-009 payment path as three drafts with the moment each is due.

    Every one is validated like a cold reply. With no payment link configured
    the first draft keeps the visible ``{payment_link}`` placeholder and is
    marked unsendable, because a proposal email with a silently missing link is
    worse than one that obviously needs a paste.
    """
    now = slots.to_tz(slots.ensure_aware(now, TZ), TZ)
    link = link or payment_link()
    blocks = load_verbal_blocks()
    deposit_line, _ = deposit_terms(proposal.campaign_key)
    out = []  # type: List[EmailDraft]
    for key, offset in VERBAL_COMMIT_OFFSETS:
        raw = blocks.get(key)
        if not raw:
            continue
        body = raw.format_map(_SafeDict(
            first_name=proposal.first_name,
            company=proposal.company,
            payment_link=link or "{payment_link}",
            deposit_line=deposit_line,
        ))
        subject_match = _SUBJECT_RE.search(body)
        subject = subject_match.group(1).strip() if subject_match else "Next steps for %s" % proposal.company
        body = _SUBJECT_RE.sub("", body, count=1).strip()
        due = _due_at(now + offset, key)
        problems = draft_mod.validate_draft(body, campaign_key=proposal.campaign_key,
                                            allow_terms=[proposal.company, proposal.first_name])
        if "{payment_link}" in body:
            problems.append("no payment link configured (set %s); paste Lorenzo's link before sending"
                            % PAYMENT_LINK_ENV)
        out.append(EmailDraft(key=key, subject=subject, body=body, due_iso=due.isoformat(), problems=problems))
    return out


def _due_at(when: datetime, key: str) -> datetime:
    """Inside the 07:00 to 19:00 CT send window, on a business day.

    The immediate draft is the exception SOP-009 asks for (within the hour),
    so it only moves when the hour itself is outside the window.
    """
    when = slots.to_tz(when, TZ)
    if key == "immediate":
        return when if slots.within_send_window(when) else _next_window_open(when)
    for _ in range(10):
        if slots.is_send_time(when):
            return when
        when = _next_window_open(when)
    return when


def _next_window_open(when: datetime) -> datetime:
    hour = settings.SEND_WINDOW[0]
    if when.hour >= settings.SEND_WINDOW[1]:
        when = when + timedelta(days=1)
    day = when.date()
    naive = datetime(day.year, day.month, day.day, hour, 0)
    try:
        opened = TZ.localize(naive)
    except Exception:  # noqa: BLE001 - DST edge
        opened = TZ.localize(naive, is_dst=False)
    while opened.weekday() >= 5:
        opened = opened + timedelta(days=1)
    return opened


# ---------------------------------------------------------------- output
def _discriminator(proposal: Proposal) -> str:
    raw = proposal.appointment_id or proposal.lead_email or "lead"
    return re.sub(r"[^a-z0-9]+", "", str(raw).lower())[:12] or "lead"


def write_draft(proposal: Proposal, directory: Optional[Path] = None,
                verbal: Optional[List[EmailDraft]] = None,
                suffix: Optional[str] = None) -> Optional[str]:
    """File the draft under .tmp/proposals/. Returns the path, or None.

    The filename carries the appointment id, the same shape
    ``precall.write_file`` uses. Without it two calls on one day that slug to
    the same company name (a rescheduled call and its original, the same
    prospect arriving from both appointment sources, two prospects with the
    same company name) silently overwrote each other while the digest reported
    both as filed.
    """
    try:
        target = Path(directory) if directory is not None else (paths.tmp_dir() / "proposals")
        target.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "_", (proposal.company or "lead").lower()).strip("_")[:40]
        stem = "%s_%s_%s" % (proposal.call_date.replace("-", ""), slug, _discriminator(proposal))
        path = target / ("%s.md" % stem)
        if suffix:
            # A forced re-draft never replaces the scheduled one on disk: both
            # are evidence of what was produced and when.
            path = target / ("%s_%s.md" % (stem, suffix))
            counter = 2
            while path.exists():
                path = target / ("%s_%s%d.md" % (stem, suffix, counter))
                counter += 1
        path.write_text(document(proposal, verbal), encoding="utf-8")
        return str(path)
    except OSError as exc:  # noqa: BLE001
        logger.warning("could not write the proposal draft: %s", exc)
        return None


INTERNAL_BANNER = "=== INTERNAL. NOTES FOR LORENZO. DO NOT PASTE ANYTHING ABOVE THE NEXT BANNER. ==="
CLIENT_BANNER = "=== CLIENT-FACING PROPOSAL STARTS HERE. PASTE FROM THE NEXT LINE DOWN. ==="


def client_body(document_text: str) -> str:
    """Everything below the client banner: what actually goes to the prospect.

    "Paste into GHL Documents" invites a select-all, and the review header is
    ordinary markdown blockquotes. Without a banner the eye cannot miss, a
    select-all put "nothing proves this call happened" and "offers.md says $0 up
    front ... Confirm which one is right" in front of the prospect.
    """
    marker = "%s\n" % CLIENT_BANNER
    index = (document_text or "").find(marker)
    if index < 0:
        return document_text or ""
    body = (document_text or "")[index + len(marker):]
    cut = body.find(INTERNAL_BANNER)
    if cut >= 0:
        body = body[:cut]
    return body.strip().rstrip("-").strip() + "\n"


def document(proposal: Proposal, verbal: Optional[List[EmailDraft]] = None) -> str:
    """The proposal plus the header Lorenzo needs to review it."""
    head = [
        "<!-- DRAFT. Nothing in this file has been sent. Review, edit, then paste the CLIENT-FACING section into "
        "GHL Documents or PandaDoc and send it yourself. -->",
        "",
        INTERNAL_BANNER,
        "",
        "> Draft for %s (%s), built %s from %s. Held evidence: %s." % (
            proposal.company, proposal.campaign_key, proposal.meta.get("built_at"), proposal.source,
            proposal.held_evidence),
    ]
    if proposal.held_evidence == "unknown":
        head.append("> No Zoom telemetry: nothing proves this call happened. Confirm it did before you send this.")
    for note in proposal.meta.get("notes_for_lorenzo") or []:
        head.append("> Check: %s" % note)
    for problem in proposal.problems:
        head.append("> BLOCKED: %s" % problem)
    head += ["", CLIENT_BANNER, ""]
    body = ["\n".join(head), proposal.text]
    if verbal:
        body.append("\n---\n\n%s\n\n# Verbal commit path (SOP-009), drafts only\n" % INTERNAL_BANNER)
        for item in verbal:
            body.append("## %s, due %s\n\nSubject: %s\n\n%s\n" % (
                item.key, precall._stamp(item.due_iso), item.subject, item.body))  # noqa: SLF001
            if item.problems:
                body.append("> BLOCKED: %s\n" % "; ".join(item.problems))
    return "\n".join(body).strip() + "\n"


def card_title(proposal: Proposal, protected: Optional[bool] = None) -> str:
    if protected is None:
        protected = precall.topic_is_protected()
    return proposal.title if protected else "Proposal draft ready (%s)" % proposal.campaign_key


def card_text(proposal: Proposal, verbal: Optional[List[EmailDraft]] = None, path: Optional[str] = None,
              protected: Optional[bool] = None) -> str:
    """The push. The company name is withheld on an unprotected ntfy topic, the
    same rule the pre-call card follows: the topic is world readable and naming
    a prospect on it is the leak, whatever else the card says."""
    if protected is None:
        protected = precall.topic_is_protected()
    lines = [
        ("%s, %s. Call %s." % (proposal.company, proposal.campaign_key, proposal.call_date) if protected
         else "%s. Call %s. The company is named in the file and the note." % (proposal.campaign_key,
                                                                               proposal.call_date)),
        "Built from: %s." % proposal.source,
    ]
    if proposal.held_evidence == "unknown":
        lines.append("No Zoom telemetry, so confirm the call happened first.")
    if proposal.problems:
        lines.append("BLOCKED: %s" % "; ".join(proposal.problems[:2]))
    else:
        lines.append("Clean against the offer sheet. Review, then send it yourself.")
    if verbal:
        blocked = [v.key for v in verbal if not v.sendable]
        lines.append("Verbal commit drafts: %d ready, %d need you (%s)."
                     % (len(verbal) - len(blocked), len(blocked), ", ".join(blocked) or "none"))
    lines.append("Draft file: %s" % (path or ".tmp/proposals"))
    return "\n".join(lines)


def deliver(proposal: Proposal, store=None, ghl=None, now: Optional[datetime] = None,
            notify_fn=None, verbal: Optional[List[EmailDraft]] = None, write: bool = True,
            replace: bool = False) -> Dict[str, Any]:
    """File the draft, tell Lorenzo, put a note on the contact. Exactly once.

    Nothing is sent to the prospect here and nothing can be: the only outbound
    call is ``ghl.create_note``, which is guarded, and the document itself
    never leaves the laptop until Lorenzo pastes it.

    ``replace=True`` is the forced path (``--proposal-for`` with a Fireflies
    transcript). Without it the documented workflow was silently swallowed by
    the claim the scheduled tick had already taken that day: the better,
    transcript-based proposal was built and then dropped, and the digest
    reported it as if it had been filed.
    """
    now = slots.to_tz(slots.ensure_aware(now, TZ), TZ) if now is not None else datetime.now(TZ)
    out = {"key": proposal.key, "claimed": False, "replaced": False, "file": None, "notified": None, "note": None,
           "document": {"status": "manual",
                        "reason": "GHL Documents and PandaDoc have no create-draft endpoint in shared/ghl.py; "
                                  "paste the file by hand"}}  # type: Dict[str, Any]
    if store is not None and not store.set_if_absent(proposal.key, {"at": now.isoformat(),
                                                                    "company": proposal.company}):
        if not replace:
            out["skipped"] = "already_drafted"
            return out
        out["replaced"] = True
        store.set(proposal.key, {"at": now.isoformat(), "company": proposal.company, "replaced": True,
                                 "source": proposal.source})
    out["claimed"] = True
    if write:
        out["file"] = write_draft(proposal, verbal=verbal, suffix="forced" if out["replaced"] else None)
    if notify_fn is None:
        from shared import notify as notify_mod

        notify_fn = notify_mod.notify
    try:
        protected = precall.topic_is_protected()
        out["notified"] = notify_fn(card_title(proposal, protected),
                                    card_text(proposal, verbal, out["file"], protected), priority="high",
                                    tags=["memo"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("proposal notify failed: %s", exc)
        out["notified"] = {"error": str(exc)}
    if ghl is not None and proposal.contact_id:
        note = "Proposal drafted %s for %s (%s). Draft only, not sent. File: %s" % (
            proposal.call_date, proposal.company, proposal.campaign_key, out["file"] or ".tmp/proposals")
        try:
            out["note"] = ghl.create_note(proposal.contact_id, note)
        except Exception as exc:  # noqa: BLE001
            logger.warning("proposal note failed: %s", exc)
            out["note"] = {"error": str(exc)}
    elif ghl is not None:
        out["note"] = {"skipped": "no_contact_id"}
    return out
