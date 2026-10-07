"""Reply classification: deterministic rules first, Haiku for the rest,
Sonnet ('escalate') when Haiku is unsure (< 0.8).

Rule layer (documented, regex, no LLM call):
  R1  auto-responders  -> ooo | auto_reply_unmonitored   (subject + body markers, return date extracted)
  R2  hostility        -> negative_hostile                (insults / spam accusations / "leave me alone")
  R3  removal          -> unsubscribe                     ("remove", "stop", "don't email me again", ...)
  R4  short plain no   -> negative_notfit | negative_notnow (only when the lead's own words are short,
                          unambiguous and carry no positive cue; anything else goes to the LLM)
Everything else: shared.llm.complete('classify', ...) on the lead's own words only; the
quoted cold email is stripped and never sent to a model.
"""
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from shared import llm, slots

from services.reply_engine.models import LABELS, QUESTION_TYPES, Classification, Extracted, ReplyEvent

logger = logging.getLogger("reply_engine.classify")

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
CONFIDENCE_FLOOR = 0.8

# ------------------------------------------------------------ quote strip
_QUOTE_LINE_RE = re.compile(r"^\s*>")


def strip_quoted(text: str) -> str:
    """Return only the lead's own words.

    One implementation, shared with ``shared.slots.strip_quoted``. The local
    copy this replaced made the colon optional in ``On ... wrote`` and matched
    under re.S, so the attribution could span the lead's own sentences: "On your
    site I saw what you wrote about commercial accounts.\\nWhat does this
    cost?" was cut to nothing, classify() took the empty-body branch
    (neutral_question, confidence 0.0) and the pricing question never reached
    question_type_for. shared.slots requires the colon (or Zoho's
    ``---- ... wrote ----``), anchors "On" to the start of a line and still
    handles the wrapped Gmail attribution.

    Lines starting with '>' are dropped here as well, which the shared cutter
    only does when the quote begins at one.
    """
    raw = (text or "").replace("\r\n", "\n").replace("﻿", "")
    out = slots.strip_quoted(raw)
    lines = [ln for ln in out.split("\n") if not _QUOTE_LINE_RE.match(ln)]
    return "\n".join(lines).strip()


_SIGNOFF_RE = re.compile(
    r"^\s*(kind(est)? regards|best regards|warm regards|regards|best|thanks|thank you|thx|cheers|sincerely|"
    r"respectfully|with kind regards|talk soon|speak soon|all the best|many thanks)\b[,!.:;\s]*(?P<rest>[^\n]*)$",
    re.I,
)
_IMG_RE = re.compile(r"\[(?:cid:|https?://)[^\]]*\]")
# A sign-off line that carries a question, a day or a clock time is a sentence,
# not the top of a signature block.
_TIME_HINT_RE = re.compile(
    r"\b\d{1,2}\s?(?:am|pm)\b|\b\d{1,2}:\d{2}\b|\b(mon|tues?|wed(nes)?|thur?s?|fri|sat(ur)?|sun)(day)?\b|"
    r"\b(today|tomorrow|morning|afternoon|noon|week)\b",
    re.I,
)
# Lines that are signature furniture rather than the lead's message.
_SIGNATURE_LINE_RE = re.compile(
    r"@|\bllc\b|\binc\b|\bcorp\b|\bltd\b|www\.|https?://|"
    r"\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}|^sent from|^--|^\|",
    re.I,
)
_GREETING_ONLY_RE = re.compile(r"^(hi|hello|hey|good (morning|afternoon|evening))\b[^\n]{0,24}$", re.I)


def _signature_starts_here(line: str, following) -> bool:
    """True only when ``line`` really is the top of a signature block.

    'Thanks,' on its own above a name and a phone number is a sign-off.
    'Thanks, Tuesday at 2pm works for me.' is the whole answer, and cutting
    there used to delete the lead's chosen time before classification ever saw
    it.
    """
    m = _SIGNOFF_RE.match(line)
    if not m:
        return False
    rest = (m.group("rest") or "").strip()
    if rest:
        if "?" in rest or _TIME_HINT_RE.search(rest) or len(rest.split()) > 2:
            return False
    for ln in following:
        text = ln.strip()
        if not text:
            continue
        if "?" in text:
            return False
        if _SIGNATURE_LINE_RE.search(text):
            continue
        if len(text.split()) > 4:
            return False
    return True


def core_text(text: str) -> str:
    """strip_quoted + cut the signature block + drop inline image markers."""
    top = strip_quoted(text)
    top = _IMG_RE.sub("", top)
    lines = top.split("\n")
    kept = []
    for i, ln in enumerate(lines):
        if kept and _signature_starts_here(ln, lines[i + 1:]):
            break
        kept.append(ln)
    core = "\n".join(kept).strip()
    if not core:
        return top
    # A cut that leaves nothing but the greeting has eaten the message.
    body_lines = [l.strip() for l in core.split("\n") if l.strip()]
    if len(body_lines) == 1 and _GREETING_ONLY_RE.match(body_lines[0]):
        return top
    return core


# --------------------------------------------------------- R1 auto reply
AUTO_SUBJECT_RE = re.compile(
    r"^\s*(?:re:\s*)?(automatic reply|auto[- ]?reply|autoreply|automated (reply|response)|out of (the )?office|"
    r"i'?m currently out of the office|thank you for (contacting|reaching out|your e-?mail|your message)|"
    r"this (email|mailbox|inbox) is no longer monitored|undeliverable|delivery (status|failure))",
    re.I,
)
UNMONITORED_RE = re.compile(
    r"no longer (monitored|in use|active|valid)|not monitored|unmonitored|do not respond to e-?mails?|"
    r"does not accept (incoming )?(e-?mail|messages)|this (inbox|mailbox|e-?mail( address)?) is (not|no longer)|"
    r"e-?mail (address )?has changed|will be disabled|not my primary channel|this is an automated (message|response)|"
    r"has been filtered|identified as unsolicited|automatically detect and filter|no longer with|"
    r"is no longer (employed|working)",
    re.I,
)
OOO_STRONG_RE = re.compile(
    r"(i am|i'm|i will be|will be|currently) (currently )?(out of (the |my )?office|on vacation|on leave|away from (the |my )?office|"
    r"traveling|travelling)|out of (the |my )?office (with|and|until|from|through|until|speaking|without)|in and out of meetings|"
    r"returning on|will return|back (in|on) the office|limited access to e-?mail",
    re.I,
)

# Generic auto-responder boilerplate. It is deliberately wider than
# UNMONITORED_RE/OOO_STRONG_RE: it only has to recognise "this text was written
# by a mail rule", so a real human reply is never mistaken for one.
AUTO_BODY_RE = re.compile(
    r"as soon as (possible|i can|we can|we are able)|thank you for (contacting|reaching out|your (e-?mail|message|inquiry|enquiry))|"
    r"(your|the) (e-?mail|message|correspondence|inquiry) (has been |is |was )?receiv|"
    r"will (be )?(respond|reply|get back|return)|responses? to e-?mails?|within \d+ (business )?(hours?|days?)|"
    r"this is an automat|do not reply|no-?reply|out of (the )?office|please allow (up to )?\d+|client portal|"
    r"if you (need|have an|require) (immediate|urgent)|all messages will be|currently away",
    re.I,
)
# A first-person buying signal, much narrower than POSITIVE_CUE_RE, which an
# auto-responder's own boilerplate ("call our office", "send a detailed email",
# "let us know if you have any questions") trips all the time.
HUMAN_REPLY_RE = re.compile(
    r"\b(yes|yeah|yep|sure thing|sounds good|i'?m interested|we'?re interested|interested in|"
    r"tell me more|how much|what (is|are|would be) (your|the|it)|what'?s (your|the)|your (price|pricing|fee|rate)|"
    r"how does (it|this) work|works for me|let'?s (talk|chat|meet|set|do)|send me (the|your|a|more)|"
    r"book a|schedule a|set up a call|call me|does (this|that) cost|much does)\b",
    re.I,
)

_MONTHS = "jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
_MONTH_NUM = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
_DATE_RE = re.compile(
    r"\b(?:(%s)\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?"      # September 22nd, 2026 / Sep 22
    r"|(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?)\b" % _MONTHS,               # 9/21 / 09/21/2026 / 10/05/26
    re.I,
)
_RETURN_KEY_RE = re.compile(r"\b(return|returning|back|until|till|through|resume|resuming)\b", re.I)


def extract_return_date(text: str, received_at: datetime) -> Optional[str]:
    """First calendar date preceded (within 45 chars) by return/back/until/through."""
    body = (text or "").replace("\n", " ")
    for m in _DATE_RE.finditer(body):
        window = body[max(0, m.start() - 45): m.start()]
        if not _RETURN_KEY_RE.search(window):
            continue
        try:
            if m.group(1):
                month = _MONTH_NUM[m.group(1)[:3].lower()]
                day = int(m.group(2))
                year = int(m.group(3)) if m.group(3) else received_at.year
            else:
                month = int(m.group(4))
                day = int(m.group(5))
                year = m.group(6)
                if year is None:
                    year = received_at.year
                else:
                    year = int(year)
                    if year < 100:
                        year += 2000
            d = datetime(year, month, day).date()
        except (ValueError, KeyError):
            continue
        # An auto reply that names a date months in the past means last year's template; ignore it.
        if (received_at.date() - d).days > 45:
            continue
        return d.isoformat()
    return None


def rule_auto_reply(event: ReplyEvent, top: str) -> Optional[Classification]:
    subject = event.subject or ""
    auto_subject = bool(AUTO_SUBJECT_RE.match(subject))
    unmonitored = bool(UNMONITORED_RE.search(top))
    ooo_body = bool(OOO_STRONG_RE.search(top))
    # A human whose mail client titles the thread "Thank you for reaching out"
    # is not an auto-responder. The subject alone may only decide when the body
    # carries no buying signal; otherwise router.route() would file the reply
    # under the deliverability monitor and drop it with no draft and no card.
    if auto_subject and not (unmonitored or ooo_body) and HUMAN_REPLY_RE.search(top) and not AUTO_BODY_RE.search(top):
        return None
    if not (auto_subject or unmonitored or (ooo_body and len(top) < 900 and not _has_positive_cue(top))):
        return None
    return_date = extract_return_date(top, event.received_at)
    if unmonitored and not return_date:
        return Classification(label="auto_reply_unmonitored", confidence=0.99, reason="R1: unmonitored/filtered mailbox marker", method="rule",
                              extracted=Extracted())
    if auto_subject and re.match(r"^\s*(?:re:\s*)?(automatic reply|auto[- ]?reply|autoreply|automated|out of|i'?m currently out)", subject, re.I):
        return Classification(label="ooo", confidence=0.98, reason="R1: out-of-office subject", method="rule",
                              extracted=Extracted(return_date=return_date))
    if ooo_body or return_date:
        return Classification(label="ooo", confidence=0.95, reason="R1: out-of-office body", method="rule",
                              extracted=Extracted(return_date=return_date))
    return Classification(label="auto_reply_unmonitored", confidence=0.95, reason="R1: generic auto-responder subject", method="rule",
                          extracted=Extracted())


# ----------------------------------------------------------- R2 hostile
# The bare alternatives `bot`, `damn`, `scam`, `stupid` and `lazy` used to live
# here. They fire on ordinary curiosity and buying signals ("am I talking to a
# bot?", "Damn, that is a good pitch, send pricing"), and R2 blocklists the
# address workspace-wide, which the lead cannot undo. They are gone; an insult
# now has to be an insult (second person, or an unambiguous word).
#
# `absolutely not` and `never work with` were left behind by that pass and are
# the same class of bug: both are polite refusals. "Absolutely not at this time,
# budget is frozen until January." and "We would never work with a vendor we
# have not met. Come by the office sometime." are a timing objection and an
# invitation, and R2 answered both with a workspace-wide blocklist plus GHL
# DND/Lost. They are gone too, and `_is_timing_objection` below is the second
# belt for anything else in this regex that a "not now" reply might trip.
HOSTILE_RE = re.compile(
    r"\b(shit\w*|fuck\w*|bullshit|worthless|garbage|idiot\w*|laughing at|"
    r"leave (me|us) alone|for the love of god|get lost|piss off|go away|harass\w*|terrible reviews|"
    r"marked (this |it |you )?as spam|is spam|spam(ming)? (me|us)|report(ed|ing)? (you|this|it)( as spam)?|"
    r"hallucinat\w*|slop)\b"
    r"|(?:you(?:'?re| are)|this is|that is|it'?s|what a)\s+(?:a\s+|an\s+|just\s+a\s+|some\s+|so\s+|really\s+|such a\s+)*"
    r"(?:scam|fraud|stupid|lazy|pathetic|ridiculous|waste of (?:my |our )?time)\b",
    re.I,
)

# ---------------------------------------------------------- R3 removal
UNSUB_START_RE = re.compile(r"^\W*(remove|stop|unsubscribe|opt[- ]?out|no more e-?mails?|delete (me|us))\b", re.I)
UNSUB_RE = re.compile(
    r"remove (me|us|my (e-?mail|address)|our (e-?mail|address))|take (me|us) off|unsubscribe|opt[- ]?out|"
    r"(do not|don'?t|never|stop) (e-?mail(ing)?|contact(ing)?|message|messaging|write to|writing to) (me|us|this)|"
    r"(do not|don'?t) contact us again|please stop(?!\s+(by|in|over|around|at|on)\b)|stop (e-?mailing|contacting|sending)|no (further|more) (e-?mails?|contact|messages)|"
    r"leave (me|us) alone|remove us from all lists",
    re.I,
)

# ------------------------------------------------------ R4 short negatives
NOTNOW_RE = re.compile(
    r"not (interested )?at this time|at this time|not (right )?now\b|bad timing|not a good time|not the right time|"
    r"(touch base|check back|circle back|reach (back )?out|follow up|revisit|reconnect|try (me|us) again)\s+(with (me|us)\s+)?(in|next|after|later|early|toward)|"
    r"next (month|quarter|year)|in (a few|a couple( of)?|\d+|two|three|four|six) (weeks|months)|later this year|"
    r"after (tax season|the (new )?year|q[1-4]|the holidays|busy season)|maybe later|down the road",
    re.I,
)
NOTFIT_RE = re.compile(
    r"^\W*(no|nope|no,? thank(s| you)|not interested|we'?re not interested|i'?m not interested|(hard )?pass|no not really)\b|"
    r"\bnot (something|anything) (that |which )?(would be |we'?d be |i'?d be |i would be |we would be )?(of interest|interested in)|"
    r"\bnot (a good |the right |a )?fit\b|\b(we|i) (don'?t|do not) (need|want|have (a|any) (need|interest))\b|\bno need\b|"
    r"\bnot for (us|me)\b|\b(we|i)('?re| am| are) (all )?(set|good)( here| for now)?\b|\bnot interested\b|\bno thank(s| you)\b",
    re.I,
)
POSITIVE_CUE_RE = re.compile(
    r"\b(yes|yeah|sure|sounds good|tell me more|more info|call|chat|zoom|works for me|open to|how much|what is|what'?s|"
    r"percentage|cost|price|pricing|send|schedule|meet|talk|interested in|curious|question)\b",
    re.I,
)


def has_positive_cue(text: str) -> bool:
    """Public name for the buying-signal check the rules gate on."""
    return _has_positive_cue(text or "")


def _has_positive_cue(top: str) -> bool:
    scrub = NOTFIT_RE.sub(" ", top)
    scrub = NOTNOW_RE.sub(" ", scrub)
    return bool(POSITIVE_CUE_RE.search(scrub))


def _is_timing_objection(core: str) -> bool:
    """A "not now" that asks for nothing to be removed.

    R2/R3 run before R4, so without this a timing objection that happens to
    carry a word from HOSTILE_RE is graded hostile and fires the irreversible
    workspace-wide blocklist before rule_short_negative ever runs.
    """
    if not core:
        return False
    return bool(NOTNOW_RE.search(core)) and not explicit_removal(core)


def rule_short_negative(core: str) -> Optional[Classification]:
    if len(core) > 260 or not core:
        return None
    notnow = NOTNOW_RE.search(core)
    notfit = NOTFIT_RE.search(core)
    if not (notnow or notfit):
        return None
    if _has_positive_cue(core):
        return None
    if notnow:
        return Classification(label="negative_notnow", confidence=0.92, reason="R4: timing objection (%s)" % notnow.group(0).strip(), method="rule")
    return Classification(label="negative_notfit", confidence=0.92, reason="R4: plain no (%s)" % notfit.group(0).strip(), method="rule")


# ------------------------------------------------------------ extraction
PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)")
PRICING_RE = re.compile(r"percentage|percent|\d\s?%|\bcost|\bprice|pricing|how much|\bfees?\b|up ?front|charge|\brates?\b|commission|budget|expensive", re.I)
SEND_INFO_RE = re.compile(r"send (me |us |over |it )?(some |more |the |your )?(info|information|details|deck|brochure|proposal|material|literature|a (link|one[- ]pager))|more info(rmation)?\b|(do you have|got) (a |any )?(deck|website|case stud)", re.I)
MECHANISM_RE = re.compile(r"how (does|would|do|will) (it|this|that|you)|how it works|tell me more|what (exactly )?(is|are|do|does|would) (this|it|that|you)|walk me through|more about|what do you (mean|do)|explain", re.I)
# "do you have a Calendly?", "send me your booking link", "a link to book a
# time": the lead wants to pick a time themselves (question type booking_link).
BOOKING_LINK_RE = re.compile(
    r"\bcalendly\b|\b(?:booking|scheduling|calendar|meeting) (?:link|page)\b|\blink to (?:book|schedule|grab|pick)\b"
    r"|\b(?:send|share) (?:me |us |over )?(?:your|a) calendar\b", re.I)
REFERRAL_RE = re.compile(
    r"(?:talk to|reach out to|contact|speak (?:with|to)|e-?mail|get in touch with|forward(?:ed)? (?:this )?to|handles? this is|person (?:to|you want) (?:talk to|contact) is)\s+"
    r"(?:my |our )?(?:colleague |partner |manager |director |owner )?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
)
_FOLLOW_UP_UNITS = {"week": 7, "weeks": 7, "month": 30, "months": 30, "quarter": 90, "year": 365}
_WORD_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "couple": 2, "few": 3, "several": 3}


def question_type_for(core: str) -> str:
    if PRICING_RE.search(core):
        return "pricing"
    if BOOKING_LINK_RE.search(core):
        return "booking_link"
    if SEND_INFO_RE.search(core):
        return "send_info"
    if MECHANISM_RE.search(core):
        return "mechanism"
    return "other"


def parse_follow_up_date(core: str, received_at: datetime) -> str:
    """'touch base next month' -> +30 days; 'in 2 weeks' -> +14; 'next quarter' -> +90; default +30."""
    base = received_at.date()
    low = (core or "").lower()
    m = re.search(r"in (a|an|one|two|three|four|five|six|couple( of)?|few|several|\d+) (weeks?|months?)", low)
    if m:
        raw = m.group(1).split()[0]
        n = int(raw) if raw.isdigit() else _WORD_NUM.get(raw, 1)
        unit = m.group(3).rstrip("s") + ("s" if m.group(3).endswith("s") else "")
        days = n * _FOLLOW_UP_UNITS.get(unit, 30)
        return (base + timedelta(days=days)).isoformat()
    if re.search(r"next (month)", low):
        return (base + timedelta(days=30)).isoformat()
    if re.search(r"next quarter|in q[1-4]|after q[1-4]", low):
        return (base + timedelta(days=90)).isoformat()
    if re.search(r"next year|after the (new )?year|in january", low):
        target = datetime(base.year + 1, 1, 15).date()
        return target.isoformat()
    if re.search(r"after tax season|after april|busy season", low):
        target = datetime(base.year if base.month < 4 else base.year + 1, 4, 20).date()
        return target.isoformat()
    if re.search(r"end of (the )?year|q4|holidays", low):
        return datetime(base.year, 12, 1).date().isoformat() if base.month < 12 else (base + timedelta(days=45)).isoformat()
    return (base + timedelta(days=30)).isoformat()


def extract(event: ReplyEvent, core: str, label: str) -> Extracted:
    ex = Extracted()
    if not core:
        return ex
    if label in ("positive_question", "neutral_question"):
        ex.question_type = question_type_for(core)
    elif label in ("positive_interested", "positive_referral") and PRICING_RE.search(core):
        ex.question_type = "pricing"
    elif label == "positive_interested" and BOOKING_LINK_RE.search(core):
        ex.question_type = "booking_link"
    if label.startswith("positive") or label == "neutral_question":
        pm = PHONE_RE.search(core)
        if pm:
            ex.phone = pm.group(0).strip()
        try:
            pt = slots.parse_proposed_time(core, event.received_at)
        except Exception:  # noqa: BLE001 - parsing must never break classification
            pt = None
        if pt is not None:
            ex.proposed_time = pt.isoformat()
        try:
            win = slots.parse_availability_window(core)
        except Exception:  # noqa: BLE001
            win = None
        if win is not None:
            ex.availability_window = {"start_hour": win[0], "end_hour": win[1], "tz": getattr(win[2], "zone", str(win[2]))}
    if label in ("positive_referral", "wrong_person"):
        rm = REFERRAL_RE.search(core)
        if rm:
            ex.referral_name = rm.group(1)
    if label == "negative_notnow":
        ex.follow_up_date = parse_follow_up_date(core, event.received_at)
    if label in ("negative_hostile", "unsubscribe"):
        ex.remove_request = bool(UNSUB_RE.search(core) or UNSUB_START_RE.match(core))
    return ex


# -------------------------------------------------------------- LLM tier
def _prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("prompt %s missing", path)
        return ""


def build_user_message(event: ReplyEvent, core: str) -> str:
    return (
        "Subject: %s\nCampaign: %s (niche=%s, offer=%s)\nInstantly AI interest value: %s\n"
        "Lead's reply (quoted text removed):\n<<<\n%s\n>>>"
        % (event.subject or "", event.campaign_key or event.campaign_id or "?", event.niche or "?", event.offer or "?",
           event.ai_interest_value if event.ai_interest_value is not None else "n/a", core)
    )


def _coerce(raw: Any, method: str, model: str) -> Optional[Classification]:
    if not isinstance(raw, dict):
        return None
    label = str(raw.get("label", "")).strip().lower()
    if label not in LABELS:
        return None
    try:
        conf = float(raw.get("confidence", 0.5))
    except (TypeError, ValueError):
        conf = 0.5
    conf = max(0.0, min(1.0, conf))
    ex = Extracted()
    qt = raw.get("question_type")
    if isinstance(qt, str) and qt in QUESTION_TYPES:
        ex.question_type = qt
    return Classification(label=label, confidence=conf, reason=str(raw.get("reason", ""))[:300], method=method, model=model, extracted=ex)


def llm_classify(event: ReplyEvent, core: str) -> Classification:
    ensure_offline_fakes()
    user = build_user_message(event, core)
    result = None
    try:
        raw = llm.complete("classify", _prompt("classify_system.md"), user, max_tokens=300, json_mode=True)
        result = _coerce(raw, "llm", llm.model_for("classify"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("classify LLM failed: %s", exc)
    if result is None or result.confidence < CONFIDENCE_FLOOR:
        try:
            raw = llm.complete("escalate", _prompt("escalate_system.md"), user, max_tokens=300, json_mode=True)
            esc = _coerce(raw, "escalate", llm.model_for("escalate"))
            if esc is not None:
                if result is not None:
                    esc.reason = (esc.reason or "") + " (first pass: %s %.2f)" % (result.label, result.confidence)
                result = esc
        except Exception as exc:  # noqa: BLE001
            logger.warning("escalate LLM failed: %s", exc)
    if result is None:
        result = Classification(label="neutral_question", confidence=0.0, reason="LLM unavailable; routed to Lorenzo for review", method="fallback")
    return result


def explicit_removal(core: str) -> bool:
    """An unmistakable opt-out in the lead's own words."""
    return bool(UNSUB_START_RE.match(core) or UNSUB_RE.search(core))


# ------------------------------------------------------------------ main
def classify(event: ReplyEvent) -> Classification:
    top = strip_quoted(event.text)
    core = core_text(event.text)

    result = rule_auto_reply(event, top)
    if result is None:
        # R2/R3 read `core` (signature stripped), not `top`: a lead whose
        # signature block happens to contain a trigger word - "Pat Miller |
        # BotCo | bot@example.com" - must not be blocklisted for it. Both rules
        # carry the same positive-cue escape hatch R4 has, so a reply that also
        # asks about pricing or a time can never be destroyed by a keyword.
        positive = _has_positive_cue(core)
        # A timing objection is never hostile. R2 runs before R4, so "Absolutely
        # not at this time, budget is frozen until January." used to be graded
        # negative_hostile 0.97 and blocklisted workspace-wide.
        timing = _is_timing_objection(core)
        if HOSTILE_RE.search(core) and not positive and not timing:
            result = Classification(label="negative_hostile", confidence=0.97, reason="R2: hostile language", method="rule")
        elif explicit_removal(core) and not positive:
            result = Classification(label="unsubscribe", confidence=0.98, reason="R3: removal request", method="rule")
    if result is None:
        result = rule_short_negative(core)
    if result is None:
        if not core.strip():
            result = Classification(label="neutral_question", confidence=0.0, reason="empty reply body; needs a human look", method="fallback")
        else:
            result = llm_classify(event, core)
            # Same protection one tier up: a model that answers "hostile" or
            # "unsubscribe" to a reply carrying a buying signal and no opt-out
            # in words is routed to Lorenzo instead of the blocklist.
            if result.label in ("negative_hostile", "unsubscribe") and _has_positive_cue(core) and not explicit_removal(core):
                result = Classification(
                    label="neutral_question", confidence=0.5, method=result.method, model=result.model,
                    reason="%s downgraded: buying signal present and no removal request in the lead's words (%s)" % (
                        result.label, (result.reason or "")[:120]))

    merged = extract(event, core, result.label)
    if result.extracted.question_type and not merged.question_type:
        merged.question_type = result.extracted.question_type
    if result.extracted.return_date and not merged.return_date:
        merged.return_date = result.extracted.return_date
    result.extracted = merged
    return result


# --------------------------------------------- offline heuristic (tests/replay)
def offline_classify(system: str, user: str, json_mode: bool) -> Dict[str, Any]:
    """Keyword stand-in for Haiku used when LLM_FAKE=1 (tests and shadow replay).
    It only ever sees the lead's own words, exactly like the real model."""
    m = re.search(r"<<<\n(.*)\n>>>", user or "", re.S)
    core = (m.group(1) if m else user or "").strip()
    low = core.lower()
    qt = question_type_for(core)
    ref = REFERRAL_RE.search(core)
    if NOTNOW_RE.search(core) and not re.search(r"\?", core):
        return {"label": "negative_notnow", "confidence": 0.9, "reason": "offline: timing objection", "question_type": None}
    if re.search(r"no longer (here|with|works?|employed|at)|wrong (person|contact)|not the right (person|contact)|i (don'?t|do not) handle|left the company|retired", low):
        return {"label": "wrong_person", "confidence": 0.9, "reason": "offline: wrong person", "question_type": None}
    if ref and re.search(r"talk to|reach out to|contact|speak (with|to)|handles", low) and not re.search(r"\b(how|what|cost|price)\b", low):
        return {"label": "positive_referral", "confidence": 0.85, "reason": "offline: referral to %s" % ref.group(1), "question_type": None}
    if PRICING_RE.search(core) or SEND_INFO_RE.search(core) or MECHANISM_RE.search(core) or re.search(r"tell me more|more\?", low):
        conf = 0.9 if "?" in core or re.search(r"tell me more", low) else 0.7
        return {"label": "positive_question", "confidence": conf, "reason": "offline: question (%s)" % qt, "question_type": qt}
    if re.search(r"\b(yes|sure|works for me|let'?s (chat|talk|do it|get together|meet)|open (to|for) (a )?(discussion|chat|call)|sounds good|call me|"
                 r"i'?m (in|available|free)|available|works|how'?s \d|\d ?(am|pm)|monday|tuesday|wednesday|thursday|friday|reschedule)\b", low):
        return {"label": "positive_interested", "confidence": 0.9, "reason": "offline: proposes a time / says yes", "question_type": None}
    if NOTFIT_RE.search(core):
        return {"label": "negative_notfit", "confidence": 0.88, "reason": "offline: plain no", "question_type": None}
    if "?" in core:
        return {"label": "neutral_question", "confidence": 0.6, "reason": "offline: unclear question", "question_type": qt}
    return {"label": "neutral_question", "confidence": 0.4, "reason": "offline: unclear", "question_type": None}


def offline_escalate(system: str, user: str, json_mode: bool) -> Dict[str, Any]:
    out = offline_classify(system, user, json_mode)
    out["confidence"] = max(out["confidence"], 0.85)
    out["reason"] = out["reason"].replace("offline:", "offline-escalate:")
    return out


def install_offline_fakes() -> None:
    """Register the keyword heuristics as the LLM_FAKE responders for classify/escalate."""
    llm.register_fake("classify", offline_classify)
    llm.register_fake("escalate", offline_escalate)


def offline_fakes_wanted() -> bool:
    """Follow shared.llm's own truthiness rule, not an exact match on "1".

    ``llm.is_fake()`` accepts 1/true/yes/on/y/t. Comparing LLM_FAKE to "1" here
    meant LLM_FAKE=true turned fake mode on but left these stand-ins
    uninstalled, so shared.llm's generic default answered
    {"label": "positive_interested", "confidence": 0.95} to every reply - a
    fabricated positive that is indistinguishable from a real Haiku answer.
    """
    return llm.is_fake() and os.environ.get("REPLY_ENGINE_OFFLINE_FAKES", "1") == "1"


def ensure_offline_fakes() -> None:
    """Re-install the offline stand-ins if the registry was cleared.

    Registering at import time is a one-shot side effect: anything that calls
    shared.llm.clear_fakes() afterwards (another test module, a CLI that swaps
    fakes) would silently drop this module back to the library's generic
    default, which answers 'positive_interested' to everything. A role that has
    a fake registered on purpose is left alone.
    """
    if not offline_fakes_wanted():
        return
    if llm.fake_for("classify") is None:
        llm.register_fake("classify", offline_classify)
    if llm.fake_for("escalate") is None:
        llm.register_fake("escalate", offline_escalate)


if offline_fakes_wanted():
    install_offline_fakes()
