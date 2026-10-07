"""Pre-call brief (Blueprint S6): everything Lorenzo needs 60 minutes before a call.

One brief per (appointment id, start time), built from data that already
exists and nothing else:

* company facts from the list-factory export (`output/verified/CLEAN_all.csv`)
  and the Instantly lead record, each line carrying the source it came from.
  Nothing is inferred and nothing is invented: a fact with no source is not
  printed. Reviews and the Maps footprint are deliberately absent because the
  only way to get them tonight is a paid Apify run (see runbooks/).
* the campaign and the full reply thread, read with GETs against Instantly.
* the offer for that niche with its guarantee numbers, taken from
  config/offers.md through services.reply_engine.draft, so a figure Lorenzo
  has not approved in writing ("TO CONFIRM") can never reach the brief.
* the likely objections, ranked by what the lead actually wrote in the thread
  (prompts/precall_objections.md, SOP-008).
* the one-call-close structure (prompts/precall_call_structure.md, SOP-007).

Delivery is an ntfy card plus, when a GHL token exists, a note on the contact.
Both go through the shared library, so in MODE=shadow the note is a
``guard_write`` record and nothing reaches GHL. The full brief is also written
to ``.tmp/precall/`` so it can be read after the push has scrolled away.

The brief is INTERNAL. It is the one artefact in this engine that a prospect
never sees, which is why it may quote the thread verbatim and why the manual
Google-Calendar calls (config/ids.json google_calendar.booked_this_week) are
included here although show_rate deliberately excludes them: briefing Lorenzo
about a call he made by hand is safe, emailing that prospect is not.

Clocks are injected (``now``); nothing here reads the wall clock.
"""
import csv
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from shared import paths, settings, slots
from shared.settings import TZ

from services.reply_engine import draft as draft_mod
from services.reply_engine import show_rate

logger = logging.getLogger("reply_engine.precall")

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
CLAIM_PREFIX = "precall:"
# 60 minutes before the call, per Blueprint S6. A tick that runs every 5
# minutes fires the brief on the first tick inside the window.
DEFAULT_LEAD_MINUTES = 60
# How many thread messages to quote in full before truncating the oldest.
MAX_THREAD_MESSAGES = 12
MAX_MESSAGE_CHARS = 700
# The list-factory export is the only local source of company facts that costs
# nothing to read. Override with LEAD_FACTS_CSV.
DEFAULT_FACTS_CSV = paths.ROOT_DIR / "Coding" / "lead-scrape-2026" / "output" / "verified" / "CLEAN_all.csv"
FACTS_ENV = "LEAD_FACTS_CSV"

_FACTS_CACHE = {}  # type: Dict[str, Dict[str, Dict[str, str]]]


# --------------------------------------------------------------- models
@dataclass
class Fact(object):
    label: str
    value: str
    source: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Message(object):
    when_iso: str
    direction: str          # 'in' (the lead) | 'out' (us)
    sender: str
    subject: str
    text: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Brief(object):
    appointment_id: str
    start_iso: str
    lead_email: Optional[str] = None
    contact_id: Optional[str] = None
    first_name: str = "there"
    company: str = "their business"
    niche: str = "generic"
    offer: str = "reactivation"
    campaign_key: str = draft_mod.GENERIC_KEY
    campaign_name: Optional[str] = None
    campaign_id: Optional[str] = None
    source: str = "ghl"
    when_text: str = ""
    zoom_link: Optional[str] = None
    facts: List[Fact] = field(default_factory=list)
    thread: List[Message] = field(default_factory=list)
    thread_error: Optional[str] = None
    objections: List[Dict[str, str]] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return claim_key(self.appointment_id, self.start_iso)

    @property
    def title(self) -> str:
        return "Call in %d min: %s (%s)" % (self.meta.get("minutes_out", DEFAULT_LEAD_MINUTES),
                                            self.first_name, self.company)

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["key"] = self.key
        return out


# ------------------------------------------------------------- offer data
def offer_key(niche: Optional[str], offer: Optional[str]) -> str:
    """The config/offers.md key for a (niche, offer) pair.

    Mirrors services.reply_engine.draft._key, which does the same job for a
    ReplyEvent: recruiting's outbound offer is keyed ``recruiting_outbound``
    while the other two are ``*_trigger``.
    """
    niche = (niche or "cleaning").strip().lower()
    offer = (offer or "reactivation").strip().lower()
    if offer == "outbound":
        guess = "recruiting_outbound" if niche == "recruiting" else "%s_trigger" % niche
    else:
        guess = "%s_reactivation" % niche
    return guess if guess in draft_mod.PRICING else draft_mod.GENERIC_KEY


def offer_block(campaign_key: str) -> Dict[str, Any]:
    """Mechanism, pricing answer, minimum, guarantee and proof for one offer.

    Every value is derived from config/offers.md (through draft.py, which is
    the module that parses it), so the brief cannot drift from the offer sheet
    and cannot carry a figure marked TO CONFIRM.
    """
    key = campaign_key if campaign_key in draft_mod.PRICING else draft_mod.GENERIC_KEY
    guarantee = ""
    for row in draft_mod.offer_guarantee_rows():
        if row["key"] == key:
            guarantee = row["guarantee"]
            break
    proof = ""
    for row in draft_mod.offer_proof_rows():
        if key in row["keys"]:
            proof = row["proof"]
            break
    return {
        "key": key,
        "mechanism": draft_mod.MECHANISM.get(key, ""),
        # the call's price answer (and the proposal's), never an email's: the
        # first reply's price answer states no number (2026-09-24)
        "pricing_answer": draft_mod.CALL_PRICING.get(key, ""),
        "minimum": draft_mod.MINIMUM.get(key, ""),
        # The three trigger rows carry the guarantee AND the retainer range in
        # one cell, and the retainer is TO CONFIRM. Printing the cell verbatim
        # put $2,500-5,000/mo under "The offer for this call", two sections
        # above the block that forbids exactly those numbers, in the one line
        # labelled "verbatim" that Lorenzo is most likely to read out.
        "guarantee_cell": strip_unquotable_figures(guarantee),
        "guarantee_cell_raw": guarantee,
        "proof": proof,
        "attribution": ("A contact that comes back and signs within 6 months of the first sequence touch counts."
                        if key.endswith("_reactivation") else None),
    }


def unquotable_figures() -> List[str]:
    """Figures offers.md marks TO CONFIRM. They go in the brief's do-not-say
    list, never in a sentence Lorenzo could read out as the price."""
    return draft_mod.unconfirmed_dollar_figures()


UNQUOTABLE_PLACEHOLDER = "[figure withheld, see Do not say]"


def strip_unquotable_figures(text: Optional[str]) -> str:
    """Replace every TO CONFIRM figure in ``text`` with a visible placeholder.

    The whole line stays readable, including the "until then answer ..."
    instruction offers.md puts right after the range, so nothing is lost except
    the one thing Lorenzo may not say out loud yet.
    """
    body = text or ""
    if not body:
        return ""
    unconfirmed = set(unquotable_figures())
    if not unconfirmed:
        return body
    out = []  # type: List[str]
    index = 0
    for match in draft_mod._DOLLAR_RE.finditer(body):  # noqa: SLF001 - one dollar parser for the engine
        value = draft_mod._norm_one(match.group(0))  # noqa: SLF001
        tail = draft_mod._RANGE_TAIL_RE.match(body[match.end():])  # noqa: SLF001
        upper = draft_mod._norm_one(tail.group(1)) if tail else None  # noqa: SLF001
        if value not in unconfirmed and (upper is None or upper not in unconfirmed):
            continue
        end = match.end() + (tail.end() if tail else 0)
        out.append(body[index:match.start()])
        out.append(UNQUOTABLE_PLACEHOLDER)
        index = end
    out.append(body[index:])
    return "".join(out)


# ------------------------------------------------------------- company facts
def facts_csv_path(path: Optional[str] = None) -> Optional[Path]:
    raw = path or os.environ.get(FACTS_ENV) or str(DEFAULT_FACTS_CSV)
    candidate = Path(raw)
    return candidate if candidate.exists() else None


def _load_facts_index(path: Path) -> Dict[str, Dict[str, str]]:
    """email -> row, plus domain -> row for the first contact at a company."""
    key = str(path)
    cached = _FACTS_CACHE.get(key)
    if cached is not None:
        return cached
    index = {}  # type: Dict[str, Dict[str, str]]
    try:
        with open(str(path), "r", newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                email = (row.get("email") or "").strip().lower()
                if email:
                    index.setdefault(email, row)
                domain = (row.get("company_domain") or "").strip().lower()
                if domain:
                    index.setdefault("domain:%s" % domain, row)
    except (OSError, csv.Error) as exc:
        logger.warning("could not read the lead facts export %s: %s", path, exc)
        index = {}
    _FACTS_CACHE[key] = index
    return index


def local_facts(email: Optional[str], domain: Optional[str] = None,
                path: Optional[str] = None) -> Optional[Dict[str, str]]:
    """The list-factory row for this lead, or None. Read-only, costs nothing."""
    csv_path = facts_csv_path(path)
    if csv_path is None:
        return None
    index = _load_facts_index(csv_path)
    if email:
        row = index.get(email.strip().lower())
        if row:
            return row
    if not domain and email and "@" in email:
        domain = email.split("@", 1)[1]
    if domain:
        return index.get("domain:%s" % domain.strip().lower())
    return None


def instantly_lead(instantly, email: Optional[str]) -> Optional[Dict[str, Any]]:
    """The Instantly lead record (read-only POST /leads/list). Never raises."""
    if instantly is None or not email:
        return None
    try:
        resp = instantly.list_leads(contacts=[email], limit=5)
    except Exception as exc:  # noqa: BLE001 - a brief without the CRM row is still a brief
        logger.warning("could not read the Instantly lead for %s: %s", email, exc)
        return None
    items = resp.get("items") if isinstance(resp, dict) else resp
    for item in items or []:
        if str(item.get("email") or "").strip().lower() == email.strip().lower():
            return item
    return (items or [None])[0]


_SIZE_LABEL = {"1": "1 person on record", "0": "size unknown"}


def company_facts(appointment: Dict[str, Any], row: Optional[Dict[str, str]] = None,
                  lead: Optional[Dict[str, Any]] = None) -> List[Fact]:
    """Sourced company facts. A value with no source is never printed."""
    out = []  # type: List[Fact]

    def add(label, value, source):
        if value is None:
            return
        text = str(value).strip()
        if not text:
            return
        out.append(Fact(label=label, value=text, source=source))

    row = row or {}
    payload = (lead or {}).get("payload") or {}
    csv_src = "list factory export"
    # The value and its source are chosen together. Deciding the label by
    # re-testing only the FIRST candidate printed "(instantly lead)" next to a
    # company name that came off the hand-made calendar row, which is the one
    # thing this section promises not to do.
    add(*_sourced("Company",
                  (row.get("company_name"), csv_src),
                  ((lead or {}).get("company_name"), "instantly lead"),
                  (payload.get("companyName"), "instantly lead"),
                  (appointment.get("company"), "the booking")))
    add("Contact", " ".join(x for x in [row.get("first_name"), row.get("last_name")] if x) or None, csv_src)
    add("Title", row.get("job_title") or row.get("headline"), csv_src)
    add(*_sourced("Website",
                  (row.get("company_website"), csv_src),
                  (payload.get("website"), "instantly lead"),
                  (("https://%s" % (lead or {}).get("company_domain")) if (lead or {}).get("company_domain") else None,
                   "instantly lead (domain)")))
    add("Where", row.get("company_full_address") or ", ".join(x for x in [row.get("city"), row.get("state")] if x), csv_src)
    add("Industry", row.get("industry"), csv_src)
    size = (row.get("company_size") or "").strip()
    if size:
        add("Headcount on record", _SIZE_LABEL.get(size, "%s on record" % size), csv_src)
    add("Founded", row.get("company_founded_year"), csv_src)
    add("Revenue on record", row.get("company_annual_revenue_clean"), csv_src)
    add("What they say they do", _shorten(row.get("company_description"), 400), csv_src)
    add("Services listed", _shorten(row.get("keywords"), 240), csv_src)
    add("LinkedIn", row.get("linkedin"), csv_src)
    add(*_sourced("Phone",
                  (row.get("company_phone"), csv_src),
                  (row.get("mobile_number"), csv_src),
                  (appointment.get("phone"), "the booking")))
    if lead:
        add("Opener we sent", _shorten(lead.get("personalization") or payload.get("personalization"), 300),
            "instantly lead (what the cold email already claimed we noticed)")
        add("Replies from them", lead.get("email_reply_count"), "instantly lead")
        add("First contacted", _date_only(lead.get("timestamp_created")), "instantly lead")
        add("Last reply", _date_only(lead.get("timestamp_last_reply")), "instantly lead")
        add("Inbox that owns the thread", lead.get("last_contacted_from"), "instantly lead")
    return out


def _sourced(label: str, *candidates: Tuple[Any, str]) -> Tuple[str, Optional[str], Optional[str]]:
    """(label, value, source) for the first candidate that actually has a value."""
    for value, source in candidates:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return label, text, source
    return label, None, None


def _shorten(text: Optional[str], limit: int) -> Optional[str]:
    if not text:
        return None
    flat = re.sub(r"\s+", " ", str(text)).strip()
    return flat if len(flat) <= limit else flat[: limit - 3].rstrip() + "..."


def _date_only(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return slots.to_tz(slots.parse_iso(str(value)), TZ).strftime("%b %d")
    except (ValueError, TypeError):
        return str(value)[:10]


# ------------------------------------------------------------------ thread
def fetch_thread(instantly, lead_email: Optional[str], limit: int = 50) -> Tuple[List[Message], Optional[str]]:
    """The whole thread with one lead, oldest first. Read-only GET /emails.

    ``lead=<email>`` filters by the Instantly lead record, so a thread the
    prospect answers from a different address (info@ rather than ilmi@) still
    comes back whole - which is exactly the case on the live cleaning booking.
    """
    if instantly is None or not lead_email:
        return [], "no_instantly_client" if instantly is None else "no_lead_email"
    items = []  # type: List[Dict[str, Any]]
    error = None
    for email_type in ("received", "sent"):
        try:
            resp = instantly.list_emails(email_type=email_type, limit=limit, lead=lead_email)
        except Exception as exc:  # noqa: BLE001 - half a thread beats no brief
            logger.warning("thread read (%s) failed for %s: %s", email_type, lead_email, exc)
            error = str(exc)[:200]
            continue
        page = resp.get("items") if isinstance(resp, dict) else resp
        items.extend(page or [])
    return [normalise_message(i) for i in _sorted_items(items)], error


def _sorted_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(items, key=lambda i: str(i.get("timestamp_created") or i.get("timestamp_email") or ""))


def normalise_message(item: Dict[str, Any]) -> Message:
    """One GET /emails row -> one thread line.

    Direction is read off the inbox that owns the row: Instantly sets
    ``eaccount`` to our own inbox on both sides of the thread, so a row whose
    ``from_address_email`` IS the eaccount is ours and everything else is
    theirs.
    """
    from services.reply_engine import models

    sender = str(item.get("from_address_email") or "").strip().lower()
    eaccount = str(item.get("eaccount") or "").strip().lower()
    direction = "out" if sender and sender == eaccount else "in"
    raw = models.reply_body_text(item)
    # display only: strip_quoted returns "" when the reply is bottom-posted,
    # and for a brief the raw text is better than a blank line. Nothing here
    # feeds the time parser, which is where that fallback would be unsafe.
    text = slots.strip_quoted(raw) or raw
    when = item.get("timestamp_created") or item.get("timestamp_email")
    try:
        when_iso = slots.to_tz(slots.parse_iso(str(when)), TZ).isoformat()
    except (ValueError, TypeError):
        when_iso = str(when or "")
    return Message(
        when_iso=when_iso,
        direction=direction,
        sender=sender or "unknown",
        subject=str(item.get("subject") or ""),
        text=_shorten(text, MAX_MESSAGE_CHARS) or "",
    )


# -------------------------------------------------------------- objections
# thread language -> objection block in prompts/precall_objections.md.
OBJECTION_PATTERNS = (
    # A plain price question ("What is your percentage?") matched NOTHING before
    # this entry: too_expensive wants the word "expensive" and cant_afford wants
    # "afford" or "budget". The one live bookkeeping call asked exactly that and
    # the brief told Lorenzo the thread gave no signal.
    ("price_question", re.compile(
        r"(what (?:is|are|s) (?:your|the) (?:percentage|percent|rate|rates|fee|fees|price|pricing|cut|commission|charge)"
        r"|what(?:'s|’s|s| is)? the (?:price|cost|pricing|damage)"
        r"|how much (?:do|does|would|will|is|are|will it)"
        r"|what (?:does|would|will) (?:it|this|that) cost"
        r"|your (?:pricing|prices|rates|fee structure)"
        r"|send (?:me )?(?:your |a |the )?(?:price list|price|pricing|quote))", re.I)),
    ("too_expensive", re.compile(r"\b(expensive|too much|pricey|cost too|out of (?:our|my) (?:budget|range))\b", re.I)),
    ("cant_afford", re.compile(r"\b(afford|budget|tight right now|no money)\b", re.I)),
    ("think_about_it", re.compile(r"\b(think (?:about|it over)|mull|consider it|get back to you)\b", re.I)),
    ("talk_to_partner", re.compile(r"\b(partner|my wife|my husband|the owner|my boss|board|co-?founder)\b", re.I)),
    ("timing", re.compile(r"\b(busy season|next (?:quarter|month|year)|timing|slammed|after the holidays|not right now)\b", re.I)),
    ("how_does_it_work", re.compile(r"\b(how (?:does|do|would) (?:it|this|you)|what (?:exactly )?do you do|send (?:me )?(?:more )?info|walk me through)\b", re.I)),
    ("who_are_you", re.compile(r"\b(who are you|have you done|case study|references?|worked with)\b", re.I)),
    ("results_guarantee", re.compile(r"\b(guarantee|what if it does ?n[o']t work|results?|roi)\b", re.I)),
    ("data_or_list", re.compile(r"\b(list|our data|contacts?|database|crm|spreadsheet|do ?n[o']t have)\b", re.I)),
    ("already_tried", re.compile(r"\b(tried|agency|burned|last (?:guy|company|vendor)|did ?n[o']t work)\b", re.I)),
    # The live cleaning booking is exactly this case: "i don't have any accounts
    # that i will like them back because i didn't loose any of them", followed
    # by "prospect accounts that we sent the proposals and never had back".
    # Without it the brief would have offered her the lost-account mechanism she
    # had already refused.
    ("nothing_to_reactivate", re.compile(
        r"(do ?n[o']?t (?:have|lose|loose)|did ?n[o']?t (?:lose|loose)|never (?:lost|lose)|no (?:lost|cancelled|canceled|dormant) )", re.I)),
)
# Curly quotes are the norm in real replies ("i don’t have"), and a pattern
# written with a straight apostrophe silently misses every one of them.
_SMART_QUOTES = {0x2018: "'", 0x2019: "'", 0x201c: '"', 0x201d: '"', 0x2032: "'"}


def normalise_for_match(text: str) -> str:
    return (text or "").translate(_SMART_QUOTES)


# How specific each pattern is. Two patterns regularly match the same sentence
# and the tuple order above is declaration order, not likelihood: the live
# cleaning thread ("i don't have any accounts that i will like them back")
# matches the broad data_or_list keyword list AND nothing_to_reactivate, and the
# brief used to lead with the wrong read of the sentence. The more specific
# pattern wins the sentence and the broader one is suppressed for it.
OBJECTION_WEIGHT = {
    "price_question": 5,
    "nothing_to_reactivate": 5,
    "too_expensive": 4,
    "already_tried": 4,
    "cant_afford": 3,
    "talk_to_partner": 3,
    "timing": 3,
    "results_guarantee": 3,
    "who_are_you": 3,
    "how_does_it_work": 2,
    "think_about_it": 2,
    "data_or_list": 1,
}
DEFAULT_WEIGHT = 2
# What to show when the thread gives no signal: the three that come up on
# essentially every one-call close.
DEFAULT_OBJECTIONS = ("how_does_it_work", "who_are_you", "think_about_it")
_BLOCK_RE = re.compile(r"^##\s+(\S+)\s*$")


def load_objection_blocks() -> Dict[str, str]:
    """Parse prompts/precall_objections.md into {id: body}."""
    out = {}  # type: Dict[str, str]
    try:
        text = (PROMPTS_DIR / "precall_objections.md").read_text(encoding="utf-8")
    except OSError as exc:  # noqa: BLE001
        logger.warning("could not read precall_objections.md: %s", exc)
        return out
    current = None
    buf = []  # type: List[str]
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


_SENTENCE_SPLIT_RE = re.compile(r"[.!?\n]+")


def _sentence_spans(text: str) -> List[Tuple[int, int]]:
    """(start, end) of every sentence in one message, in order."""
    spans = []  # type: List[Tuple[int, int]]
    start = 0
    for match in _SENTENCE_SPLIT_RE.finditer(text or ""):
        spans.append((start, match.end()))
        start = match.end()
    if start < len(text or ""):
        spans.append((start, len(text)))
    return spans or [(0, len(text or ""))]


def _sentence_index(spans: List[Tuple[int, int]], index: int) -> int:
    for position, (start, end) in enumerate(spans):
        if start <= index < end:
            return position
    return max(0, len(spans) - 1)


def rank_objections(thread: List[Message], campaign_key: str) -> List[Dict[str, str]]:
    """The objections this lead is most likely to raise, most likely first.

    Ranked by what they actually wrote, not by a model: every match points at
    the exact sentence it came from, so Lorenzo can tell a real signal from a
    keyword that happened to appear.

    Ranking is by pattern specificity first, then by recency. Two patterns that
    match the same sentence never both appear: the broader one is suppressed for
    that sentence, so the brief can never show two blocks quoting one sentence
    and giving contradictory advice.
    """
    blocks = load_objection_blocks()
    best = {}  # type: Dict[str, Dict[str, Any]]
    for order, message in enumerate(thread):
        if message.direction != "in":
            continue
        matched = normalise_for_match(message.text)
        spans = _sentence_spans(matched)
        per_sentence = {}  # type: Dict[int, List[Tuple[int, str, int]]]
        for oid, pattern in OBJECTION_PATTERNS:
            found = pattern.search(matched)
            if not found:
                continue
            sentence = _sentence_index(spans, found.start())
            per_sentence.setdefault(sentence, []).append(
                (OBJECTION_WEIGHT.get(oid, DEFAULT_WEIGHT), oid, found.start()))
        for sentence, found_here in per_sentence.items():
            top = max(w for w, _oid, _at in found_here)
            for weight, oid, at in found_here:
                if weight < top:
                    continue  # a more specific pattern owns this sentence
                candidate = {"id": oid, "weight": weight, "order": order,
                             "why": "they wrote: %s" % _sentence_around(message.text, at),
                             "respond": blocks.get(oid, "")}
                current = best.get(oid)
                if current is None or (candidate["weight"], candidate["order"]) > (current["weight"],
                                                                                   current["order"]):
                    best[oid] = candidate
    hits = sorted(best.values(), key=lambda h: (-h["weight"], -h["order"]))
    hits = [{"id": h["id"], "why": h["why"], "respond": h["respond"]} for h in hits]
    seen = set(h["id"] for h in hits)
    for oid in DEFAULT_OBJECTIONS:
        if oid in seen:
            continue
        seen.add(oid)
        hits.append({"id": oid, "why": "standard on a first call", "respond": blocks.get(oid, "")})
    framework = blocks.get("framework")
    if framework:
        hits.append({"id": "framework", "why": "SOP-008, in this order every time", "respond": framework})
    return hits


def _sentence_around(text: str, index: int, width: int = 90) -> str:
    flat = re.sub(r"\s+", " ", text or "")
    start = max(0, index - width // 2)
    end = min(len(flat), index + width // 2)
    return ("..." if start else "") + flat[start:end].strip() + ("..." if end < len(flat) else "")


_HTML_COMMENT_RE = re.compile(r"(?s)<!--.*?-->")


class _SafeDict(dict):
    """Leave an unknown placeholder visible rather than raising or blanking it."""

    def __missing__(self, key):
        return "{%s}" % key


def call_structure(first_name: Optional[str] = None, company: Optional[str] = None) -> str:
    """The SOP-007 skeleton, without the editor note at the top of the file.

    ``{first_name}`` and ``{company}`` are filled from the brief; the discovery
    placeholders ({size}, {source}, {value}, {count}, {math}) are left visible
    because they are genuinely unknown until Lorenzo asks the questions.
    """
    try:
        raw = (PROMPTS_DIR / "precall_call_structure.md").read_text(encoding="utf-8")
        text = _HTML_COMMENT_RE.sub("", raw).strip()
    except OSError as exc:  # noqa: BLE001
        logger.warning("could not read precall_call_structure.md: %s", exc)
        return "SOP-007: open, discovery, diagnosis, solution, close. Price on the call, ask for the decision."
    if first_name is None and company is None:
        return text
    try:
        return text.format_map(_SafeDict(first_name=first_name or "there", company=company or "their business"))
    except (ValueError, IndexError) as exc:  # noqa: BLE001 - a stray brace must not lose the section
        logger.warning("could not fill the call structure placeholders: %s", exc)
        return text


# ------------------------------------------------------- appointment sources
def manual_calls(now: datetime) -> List[Dict[str, Any]]:
    """Calls Lorenzo booked by hand on his own Google Calendar.

    jobs/appointments_tick deliberately keeps these OUT of the show-rate
    ladder, because S4 would email a prospect who already agreed the time with
    him directly. A brief is the opposite case: it is internal, nobody but
    Lorenzo reads it, and today both real calls on the books are of this kind.
    Leaving them out would mean the brief generator covers zero live calls.

    Contact ids are resolved from ``ghl.opportunities_observed_2026-09-21`` in
    config/ids.json so the GHL note has somewhere to land once a token exists.
    """
    out = []  # type: List[Dict[str, Any]]
    by_email = {}
    for opp in (settings.IDS.get("ghl") or {}).get("opportunities_observed_2026-09-21") or []:
        email = str(opp.get("email") or "").strip().lower()
        if email:
            by_email[email] = opp
    for row in (settings.IDS.get("google_calendar") or {}).get("booked_this_week") or []:
        try:
            start = slots.to_tz(slots.parse_iso(row.get("start")), TZ)
        except (ValueError, TypeError):
            logger.warning("unreadable manual calendar row %r", row)
            continue
        who = str(row.get("who") or "")
        person, _, company = who.partition(" / ")
        email = str(row.get("email") or "").strip().lower()
        opp = by_email.get(email) or {}
        out.append({
            "id": row.get("event_id") or ("manual:%s" % email),
            "contact_id": opp.get("contact_id"),
            "opportunity_id": opp.get("id"),
            "start_iso": start.isoformat(),
            "end_iso": (start + timedelta(minutes=15)).isoformat(),
            "email": email,
            "first_name": (person.strip().split(" ") or [""])[0] or None,
            "contact_name": person.strip() or None,
            "company": company.strip() or None,
            "zoom_link": row.get("location"),
            "title": who,
            "source": "google_calendar (hand made, not a GHL booking)",
            "note": row.get("note"),
            # Sopio's row is "needsAction": the invite has not been accepted.
            # Dropping it meant due() could not filter a declined call and the
            # brief said nothing, so an unconfirmed meeting was prepped for and
            # then proposed on as though it had happened.
            "response_status": str(row.get("response_status") or "").strip() or None,
        })
    return out


ACCEPTED_STATUSES = ("accepted",)
REFUSED_STATUSES = ("declined", "cancelled", "canceled")


def stale_manual_calls(now: datetime) -> List[Dict[str, Any]]:
    """Hand-made rows in config/ids.json whose start is already in the past.

    ``google_calendar.booked_this_week`` is a hand-maintained snapshot, not a
    calendar read: if a call is rescheduled and only the calendar is updated,
    this job briefs a time that no longer exists and never briefs the new one.
    Nothing here can fix that, but the tick can say out loud that the file is
    behind. See runbooks/precall_and_proposal.md, failure modes.
    """
    now = slots.to_tz(slots.ensure_aware(now, TZ), TZ)
    out = []  # type: List[Dict[str, Any]]
    for row in manual_calls(now):
        try:
            start = slots.to_tz(slots.parse_iso(row["start_iso"]), TZ)
        except (ValueError, TypeError, KeyError):
            continue
        if start < now:
            out.append(row)
    return out


def due(appointment: Dict[str, Any], now: datetime, lead_minutes: int = DEFAULT_LEAD_MINUTES) -> bool:
    """Is this call inside the brief window and not yet started?

    Late is fine on purpose. A brief is internal, so one produced 12 minutes
    before the call because the tick was down is still worth having, unlike
    every prospect-facing touch in S4 which is dropped when it goes stale.
    """
    try:
        start = slots.to_tz(slots.parse_iso(appointment["start_iso"]), TZ)
    except (ValueError, TypeError, KeyError):
        return False
    now = slots.to_tz(slots.ensure_aware(now, TZ), TZ)
    if str(appointment.get("ghl_status") or "").lower() in ("cancelled", "canceled") or appointment.get("cancelled"):
        return False
    if str(appointment.get("response_status") or "").strip().lower() in REFUSED_STATUSES:
        return False
    return (start - timedelta(minutes=lead_minutes)) <= now < start


def claim_key(appointment_id: Any, start_iso: str) -> str:
    return "%s%s:%s" % (CLAIM_PREFIX, appointment_id, _normalise_start(start_iso))


def _normalise_start(start_iso: Optional[str]) -> str:
    try:
        return slots.to_tz(slots.parse_iso(str(start_iso)), TZ).isoformat()
    except (ValueError, TypeError):
        return str(start_iso or "")


# ------------------------------------------------------------------ build
NOT_READ = "not_read"


def resolve_offer(appointment: Dict[str, Any], lead: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """(niche, offer, campaign key, campaign) for one booking, one lookup order.

    The campaign the thread really came from beats any guess from tags or the
    company name: a bookkeeping prospect booked through a cleaning campaign must
    be briefed AND proposed on the offer she was actually sold. proposal.py used
    to read only ``appointment['campaign_id']``, which ``normalise_ghl_event``
    never sets, so the brief and the proposal for one call could quote two
    different offers' pricing. Both now call this.
    """
    niche = show_rate.niche_of(appointment)
    offer = show_rate.offer_of(appointment)
    key = offer_key(niche, offer)
    campaign_id = appointment.get("campaign_id") or (lead or {}).get("campaign")
    campaign = settings.CAMPAIGN_BY_ID.get(campaign_id or "") or settings.CAMPAIGNS.get(
        appointment.get("campaign_key") or "") or {}
    matched = bool(campaign.get("niche") and campaign.get("offer"))
    if matched:
        niche, offer = campaign["niche"], campaign["offer"]
        key = offer_key(niche, offer)
    return {"niche": niche, "offer": offer, "key": key, "campaign": campaign,
            "campaign_id": campaign_id, "campaign_matched": matched,
            "offer_block_missing": offer_block_missing(offer)}


# The campaign offers config/offers.md has a call pricing and proposal block
# for. An AI agents campaign (offer "ai_agents", 2026-10-06) has none yet: its
# brief and proposal fall back to the GENERIC_KEY block and must say so.
PROPOSAL_OFFERS = ("reactivation", "outbound", "trigger")


def offer_block_missing(offer: Optional[str]) -> Optional[str]:
    """Why the brief and the proposal for this offer cannot be trusted, or
    None when offers.md has a pricing and proposal block for it."""
    name = (offer or "reactivation").strip().lower()
    if name in PROPOSAL_OFFERS:
        return None
    return ("the campaign's offer (%s) has no pricing or proposal block in config/offers.md; the offer block is "
            "the %s default, which is the wrong offer. Check it before you quote anything"
            % (name, draft_mod.GENERIC_KEY))


def build_brief(
    appointment: Dict[str, Any],
    now: datetime,
    instantly=None,
    ghl=None,
    facts_path: Optional[str] = None,
    read_thread: bool = True,
    offline_reason: Optional[str] = None,
) -> Brief:
    """Everything S6 asks for, for one appointment. Read-only end to end."""
    now = slots.to_tz(slots.ensure_aware(now, TZ), TZ)
    start = slots.to_tz(slots.parse_iso(appointment["start_iso"]), TZ)
    lead_email = (appointment.get("email") or appointment.get("lead_email") or "").strip().lower() or None
    lead = instantly_lead(instantly, lead_email) if read_thread else None
    row = local_facts(lead_email, (lead or {}).get("company_domain"), facts_path)
    thread, thread_error = fetch_thread(instantly, lead_email) if read_thread else ([], NOT_READ)
    resolved = resolve_offer(appointment, lead)
    niche, offer, key = resolved["niche"], resolved["offer"], resolved["key"]
    campaign, campaign_id = resolved["campaign"], resolved["campaign_id"]
    problems = []  # type: List[str]
    if resolved["offer_block_missing"]:
        problems.append(resolved["offer_block_missing"])
    elif niche == "generic":
        problems.append("niche could not be determined from the booking or the campaign; the offer block below is "
                        "the %s default, check it before you quote anything" % draft_mod.GENERIC_KEY)
    if thread_error == NOT_READ:
        # A chosen offline run is not a failure. Saying "could not be read" for
        # --no-read made a deliberate offline brief look like a broken key.
        problems.append("thread not read on this run (%s); the objections below are the defaults"
                        % (offline_reason or "offline mode"))
    elif thread_error:
        problems.append("reply thread could not be read (%s)" % thread_error)
    if not lead_email:
        problems.append("no email on the booking, so no CRM record and no thread")
    status = str(appointment.get("response_status") or "").strip()
    if status and status.lower() not in ACCEPTED_STATUSES:
        problems.append("the invite has not been accepted (response_status=%s); confirm the call is really "
                        "happening before you prep for it" % status)
    brief = Brief(
        appointment_id=str(appointment.get("id")),
        start_iso=start.isoformat(),
        lead_email=lead_email,
        contact_id=appointment.get("contact_id"),
        first_name=show_rate.first_name_of(appointment),
        # the booking's own company name wins: it is the one a human typed or
        # GHL holds, and the export carries the scraper's version
        # ("Shiningarmorcleaningnj Llc"). proposal.py reads the same field, so
        # the brief and the proposal cannot disagree about who this is.
        company=appointment.get("company") or (row or {}).get("company_name") or show_rate.company_of(appointment),
        niche=niche,
        offer=offer,
        campaign_key=key,
        campaign_name=campaign.get("name"),
        campaign_id=campaign_id,
        source=str(appointment.get("source") or "ghl"),
        when_text=when_text_for(start, show_rate.lead_tz_of(appointment)),
        zoom_link=appointment.get("zoom_link") or appointment.get("meeting_link"),
        facts=company_facts(appointment, row, lead),
        thread=thread[-MAX_THREAD_MESSAGES:],
        thread_error=thread_error,
        objections=rank_objections(thread, key),
        problems=problems,
        meta={
            "minutes_out": max(0, int((start - now).total_seconds() // 60)),
            "built_at": now.isoformat(),
            "facts_csv": str(facts_csv_path(facts_path) or ""),
            "thread_messages": len(thread),
            "instantly_lead": bool(lead),
            "note": appointment.get("note"),
        },
    )
    return brief


# ----------------------------------------------------------------- render
def markdown(brief: Brief) -> str:
    """The full brief. This is what lands in the GHL note and in .tmp/precall/."""
    block = offer_block(brief.campaign_key)
    lines = [
        "# Pre-call brief: %s, %s" % (brief.first_name, brief.company),
        "",
        "%s, 15 minutes. %s" % (brief.when_text, brief.zoom_link or "Zoom link on the calendar invite"),
        "Booking source: %s. Campaign: %s." % (brief.source, brief.campaign_name or "not matched to a campaign"),
        "Offer on the table: %s." % brief.campaign_key,
    ]
    if brief.meta.get("note"):
        lines.append("Note on the booking: %s" % brief.meta["note"])
    if brief.problems:
        lines.append("")
        lines.append("## Read this first")
        for problem in brief.problems:
            lines.append("- %s" % problem)
    lines += ["", "## Company facts"]
    if brief.facts:
        for fact in brief.facts:
            lines.append("- %s: %s  _(%s)_" % (fact.label, fact.value, fact.source))
    else:
        lines.append("- Nothing on file. Ask the discovery questions and take notes.")
    lines.append("- Reviews and Maps footprint: not pulled. The only source tonight is a paid Google Maps run, "
                 "so nothing here claims a rating or a review count.")
    total = int(brief.meta.get("thread_messages") or len(brief.thread))
    dropped = max(0, total - len(brief.thread))
    lines += ["", "## The thread (%d messages)" % len(brief.thread)]
    if dropped:
        # The heading used to print the untruncated count and show 12, so a
        # sentence Lorenzo remembered and could not find read as "they never
        # wrote it".
        lines.append("_%d older message(s) are not shown here. The full thread is in the Instantly inbox._" % dropped)
    if brief.thread:
        for message in brief.thread:
            who = "THEM" if message.direction == "in" else "US"
            lines.append("")
            lines.append("**%s, %s** (%s)" % (who, _stamp(message.when_iso), message.sender))
            lines.append("> %s" % (message.text or "").replace("\n", "\n> "))
    else:
        lines.append("- No thread on file.")
    lines += [
        "",
        "## The offer for this call (config/offers.md, %s)" % brief.campaign_key,
        "- What we build: %s" % block["mechanism"],
        "- What it costs, said out loud: %s" % block["pricing_answer"],
        "- Guarantee cell from offers.md, with any TO CONFIRM figure withheld: %s" % (
            block["guarantee_cell"] or "none"),
        "- Minimum to start: %s" % block["minimum"],
    ]
    if block["attribution"]:
        lines.append("- Attribution: %s" % block["attribution"])
    lines += [
        "- The one proof point allowed on this call: %s" % (block["proof"] or "none on file"),
        "",
        "## Do not say",
        "- Any figure marked TO CONFIRM in the offer sheet: %s. Say \"setup plus a monthly retainer, sized to your "
        "service area, and the guarantee covers it\" instead." % (
            ", ".join("$%s" % f for f in unquotable_figures()) or "none today"),
        "- The other offer type's proof point or guarantee. One per offer, never mixed.",
        "- Anything about how the emails get written. No tools, no software, no systems that are not theirs.",
        "",
        "## Likely objections, most likely first (SOP-008)",
    ]
    for item in brief.objections:
        lines.append("")
        lines.append("### %s" % item["id"].replace("_", " "))
        lines.append("_%s_" % item["why"])
        if item.get("respond"):
            lines.append(item["respond"])
    lines += ["", call_structure(brief.first_name, brief.company), ""]
    return "\n".join(lines).strip() + "\n"


DO_NOT_SAY_HEADING = "## Do not say"
_DO_NOT_SAY_RE = re.compile(r"(?ms)^## Do not say\n.*?(?=^## )")


def quotable_text(brief: Brief) -> str:
    """The brief minus the do-not-say block.

    The do-not-say block exists to name the figures Lorenzo must NOT say out
    loud, so it necessarily contains the retainer range that offers.md marks
    TO CONFIRM and that belongs to another offer. Every other line of the brief
    is something he could read to the prospect, so that part has to pass the
    same cross-offer checks a cold reply does. Tested in
    tests/test_precall_brief.py::test_everything_outside_the_do_not_say_block_is_safe_to_read_aloud.
    """
    return _DO_NOT_SAY_RE.sub("", markdown(brief))


def when_text_for(start: datetime, lead_tz=None) -> str:
    """'Wed, Sep 23 at 3:00pm CT'.

    show_rate.fmt_when renders the same header without am/pm, so a 15:00 call
    read as "3:00 CT" and a prospect who agreed "Thursday 4pm Eastern" could not
    be checked against it at a glance. That helper is another component's file
    and is used in prospect-facing copy, so the brief formats its own header and
    the fix there is a cross-cutting request.
    """
    ct = slots.to_tz(start, TZ)
    text = "%s, %s %d at %d:%02d%s CT" % (ct.strftime("%a"), ct.strftime("%b"), ct.day,
                                          ct.hour % 12 or 12, ct.minute, "am" if ct.hour < 12 else "pm")
    if lead_tz is not None and getattr(lead_tz, "zone", "") not in ("", "America/Chicago"):
        local = ct.astimezone(lead_tz)
        text += " (%d:%02d%s %s)" % (local.hour % 12 or 12, local.minute,
                                     "am" if local.hour < 12 else "pm",
                                     slots._tz_label(local, lead_tz))  # noqa: SLF001
    return text


def _stamp(when_iso: str) -> str:
    """'Sep 21, 6:17pm CT'.

    The am/pm is not optional, for the same reason slots.format_slot says so:
    without it 02:00 and 14:00 both render '2:00 CT', a thread sorted correctly
    reads as though it runs backwards, and a SOP-009 due time of 7:00 could be
    morning or evening.
    """
    try:
        dt = slots.to_tz(slots.parse_iso(when_iso), TZ)
    except (ValueError, TypeError):
        return when_iso
    return "%s %d, %d:%02d%s CT" % (dt.strftime("%b"), dt.day, dt.hour % 12 or 12, dt.minute,
                                    "am" if dt.hour < 12 else "pm")


def topic_is_protected() -> bool:
    """Is the ntfy topic safe for a named prospect and their own words?

    ntfy.sh topics are world readable by anyone who knows the name, and
    ``notify.redact()`` strips only email addresses and URLs. Without a token
    (NTFY_TOKEN) or an explicit accept (NTFY_ALLOW_SENSITIVE) the card must not
    carry the company name or a quote of a private reply, and there is no email
    leg in this .env to carry the withheld detail either.
    """
    try:
        from shared import notify as notify_mod

        return bool(notify_mod.topic_is_protected())
    except Exception as exc:  # noqa: BLE001 - assume the worst, which is the safe direction
        logger.warning("could not read the ntfy topic protection: %s", exc)
        return False


def card_title(brief: Brief, protected: Optional[bool] = None) -> str:
    """The push title. Carries the company only on a protected topic."""
    if protected is None:
        protected = topic_is_protected()
    if protected:
        return brief.title
    return "Call in %d min: %s" % (brief.meta.get("minutes_out", DEFAULT_LEAD_MINUTES), brief.first_name)


def card_text(brief: Brief, protected: Optional[bool] = None) -> str:
    """The push. Short, and still useful after notify.redact() has removed
    every email address and URL from an unprotected ntfy topic.

    On an unprotected topic the company name and the verbatim quote of their
    last email are withheld. Both are in the file and in the GHL note, which is
    where a private sentence belongs.
    """
    if protected is None:
        protected = topic_is_protected()
    block = offer_block(brief.campaign_key)
    said = next((m for m in reversed(brief.thread) if m.direction == "in"), None)
    lines = [
        ("%s at %s, %s." % (brief.first_name, brief.when_text, brief.company) if protected
         else "%s at %s." % (brief.first_name, brief.when_text)),
        "Offer: %s." % brief.campaign_key,
        "Price answer: %s" % _shorten(block["pricing_answer"], 220),
        "Proof: %s" % _shorten(block["proof"], 180),
    ]
    if said and protected:
        lines.append("They last said: %s" % _shorten(said.text, 180))
    top = [o["id"].replace("_", " ") for o in brief.objections if o["id"] != "framework"][:3]
    if top:
        lines.append("Expect: %s." % ", ".join(top))
    if brief.problems:
        lines.append("Check: %s" % brief.problems[0])
    if not protected:
        lines.append("Company and their own words are in the note and the file: the ntfy topic has no token.")
    lines.append("Full brief in the note and in .tmp/precall.")
    return "\n".join(lines)


def write_file(brief: Brief, directory: Optional[Path] = None) -> Optional[str]:
    """Persist the full brief next to the other intermediate files."""
    try:
        target = Path(directory) if directory is not None else (paths.tmp_dir() / "precall")
        target.mkdir(parents=True, exist_ok=True)
        stamp = _normalise_start(brief.start_iso)[:16].replace(":", "").replace("-", "")
        slug = re.sub(r"[^a-z0-9]+", "_", (brief.company or "lead").lower()).strip("_")[:40]
        path = target / ("%s_%s_%s.md" % (stamp, slug, brief.appointment_id[:12]))
        path.write_text(markdown(brief), encoding="utf-8")
        return str(path)
    except OSError as exc:  # noqa: BLE001 - a brief that cannot be filed is still delivered
        logger.warning("could not write the brief file: %s", exc)
        return None


# ---------------------------------------------------------------- deliver
def _leg_ok(result: Any) -> bool:
    """Did this delivery leg actually get the brief somewhere Lorenzo will see?

    ``shared.notify.notify`` never raises: it returns
    ``{"sent": False, "errors": [...]}`` when ntfy is unreachable. A shadow
    record or a NOTIFY=off record counts as delivered, because in both cases
    the run did what the mode allows.
    """
    if result is None:
        return False
    if isinstance(result, dict):
        if result.get("error") or result.get("errors"):
            return bool(result.get("sent"))
        if result.get("skipped"):
            return False
        return bool(result.get("sent") or result.get("test") or result.get("shadow")
                    or result.get("id") or result.get("would_do"))
    return True


def deliver(brief: Brief, store, ghl=None, now: Optional[datetime] = None,
            notify_fn=None, write: bool = True) -> Dict[str, Any]:
    """Claim the brief, push the card, write the note. Exactly once.

    The claim is taken with ``set_if_absent`` before anything is sent, so two
    overlapping ticks cannot both brief the same call. **It is released again
    when every delivery leg failed.** For a prospect-facing touch,
    claim-before-send is right (a duplicate email is worse than a missed one,
    which is why show_rate and no_show keep the claim). A brief is internal, so
    at-least-once beats at-most-once: a failed ntfy push used to leave Lorenzo
    walking into the call with no brief and no warning, because the digest goes
    out over the same ntfy leg.
    """
    if now is not None:
        now = slots.to_tz(slots.ensure_aware(now, TZ), TZ)
    else:
        try:
            now = slots.to_tz(slots.parse_iso(brief.meta.get("built_at")), TZ)
        except (ValueError, TypeError):
            now = datetime.now(TZ)
    out = {"appointment_id": brief.appointment_id, "key": brief.key, "claimed": False,
           "notified": None, "note": None, "file": None, "delivered": False}  # type: Dict[str, Any]
    if store is not None and not store.set_if_absent(brief.key, {"at": now.isoformat(),
                                                                "company": brief.company}):
        out["skipped"] = "already_briefed"
        return out
    out["claimed"] = True
    if write:
        out["file"] = write_file(brief)
    if notify_fn is None:
        from shared import notify as notify_mod

        notify_fn = notify_mod.notify
    protected = topic_is_protected()
    try:
        out["notified"] = notify_fn(card_title(brief, protected), card_text(brief, protected), priority="high",
                                    tags=["calendar"])
    except Exception as exc:  # noqa: BLE001 - never lose the note over the push
        logger.warning("precall notify failed: %s", exc)
        out["notified"] = {"error": str(exc)}
    if ghl is not None and brief.contact_id:
        try:
            out["note"] = ghl.create_note(brief.contact_id, markdown(brief))
        except Exception as exc:  # noqa: BLE001
            logger.warning("precall note failed: %s", exc)
            out["note"] = {"error": str(exc)}
    elif ghl is not None:
        out["note"] = {"skipped": "no_contact_id"}
    # The file on disk deliberately does NOT count as a delivery leg: it is the
    # archive, not the thing Lorenzo sees 60 minutes before a call.
    out["delivered"] = bool(_leg_ok(out["notified"]) or _leg_ok(out["note"]))
    if store is not None and not out["delivered"]:
        try:
            store.delete(brief.key)
            out["claim_released"] = True
            logger.warning("every delivery leg failed for %s; the claim was released so the next tick retries",
                           brief.key)
        except Exception as exc:  # noqa: BLE001 - a stuck claim is bad, a crashed tick is worse
            logger.warning("could not release the brief claim %s: %s", brief.key, exc)
    return out


def already_briefed(store, appointment_id: Any, start_iso: str) -> bool:
    if store is None:
        return False
    return bool(store.get(claim_key(appointment_id, start_iso)))
