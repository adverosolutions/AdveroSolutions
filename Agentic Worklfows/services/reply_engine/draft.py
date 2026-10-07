"""First-reply drafts per config/offers.md.

Order inside every draft: answer -> two afternoon slots -> "Lorenzo".
No booking link in any email (Lorenzo, 2026-09-23): the lead picks one of
the two offered times and Lorenzo sends the invite. The one exception is the
AI agents booking_link reply (Lorenzo, 2026-10-06), which adds his calendar
after the two times. AI agents first replies are his approved text of
2026-10-06 (_ai_agents_skeleton), not the answer -> slots structure.
Slots come from the GHL Discovery Call calendar (free-slots) or, when GHL
returns None (no token), from a fallback generator that assumes the
calendar's open hours (Mon-Fri 12:00-18:00 CT, 30-minute grid) minus any
busy blocks handed in. shared.slots enforces the 4 h lead, 5 business day
horizon and the never-double-offer rule.

In LLM_FAKE mode the template alone produces a sendable draft; with a real
model the template is the skeleton Sonnet may only polish, and the result is
validated (validate_draft) before it replaces the template.
"""
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from shared import llm, settings, slots

from services.reply_engine.models import Classification, Draft, LeadState, ReplyEvent

logger = logging.getLogger("reply_engine.draft")

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
NO_SLOTS_ASK = "Could you send me a couple of times that work for %s next week?"
FALLBACK_STEP_MINUTES = 30
FALLBACK_DAYS = 9  # calendar days scanned; slots.candidate_slots trims to 5 business days
BUFFER_MINUTES = 15  # calendar buffer (config/ids.json discovery_call.buffer_minutes)

# ------------------------------------------------------------ offer copy
# Every sentence here is derived from config/offers.md. Dollar figures and percentages must
# exist in offers.md or validate_draft() rejects the draft.
MECHANISM = {
    "cleaning_reactivation": "I build email and text sequences to every account that cancelled, stopped renewing, or never closed, and the ones ready to come back land on your calendar.",
    "bookkeeping_reactivation": "I build sequences to lost inquiries and former clients, timed to tax season, quarterly estimates and year-end cleanup, and the ones ready to come back get booked onto your calendar.",
    "recruiting_reactivation": "I build sequences to your dormant and near-miss client accounts, and the ones ready to work with you again land on your calendar.",
    "cleaning_trigger": "I watch for triggers like new leases, office expansions, property management changes and new construction, run the outreach under your name, and land the walkthroughs on your calendar.",
    "bookkeeping_trigger": "I watch for triggers like new business formations, part-time bookkeeper job posts and second locations, run the outreach under your name, and land the discovery calls on your calendar.",
    "recruiting_outbound": "I watch job boards for your specialty roles as they open, reach the hiring managers under your agency's name, and land the intro calls on your calendar.",
}


# "We never talk numbers over email" (Lorenzo, 2026-09-24): a first reply to a
# price question states no price, percentage, dollar amount or guarantee
# figure. It gives the same answer as any other question for that offer (the
# "other" branch below) and the price is covered on the call. PRICING keeps its
# keys, so the pricing template id and its variants stay as they are.
OTHER_ANSWER = "Good question. The short version is that %s The rest is easier to cover on a quick call."


def _as_clause(sentence: str) -> str:
    """A MECHANISM sentence continuing "The short version is that ...": its
    first letter lower-cased unless the sentence opens with "I"."""
    if not sentence or sentence.startswith("I ") or sentence.startswith("I'"):
        return sentence
    return sentence[0].lower() + sentence[1:]


PRICING = dict((k, OTHER_ANSWER % _as_clause(v)) for k, v in MECHANISM.items())
# The price said out loud on the call (precall brief) and written in the
# proposal after it: call only, never in an email. No email draft reads these.
CALL_PRICING = {
    "cleaning_reactivation": "Nothing up front. I take 20 to 30 percent of first-year contract value on the accounts that come back, a smaller cut on a bigger list, and $0 if nothing closes.",
    "bookkeeping_reactivation": "Nothing up front. I take 20 to 30 percent of first-year fees from the clients who come back, and $0 if nothing closes.",
    "recruiting_reactivation": "Nothing up front. I take 20 to 30 percent of the first placement fee on the accounts that come back, and $0 if nothing closes.",
    "cleaning_trigger": "Setup plus a monthly retainer, sized to your service area, and the guarantee covers it: $24,000 a year in new cleaning contracts signed within 90 days or your money back plus a $200 steakhouse gift card.",
    "bookkeeping_trigger": "Setup plus a monthly retainer, sized to your target client profile, and the guarantee covers it: $15,000 in new annual client fees within 90 days or your money back plus a $200 gift card.",
    "recruiting_outbound": "Setup plus a monthly retainer, sized to your specialty and geography, and the guarantee covers it: $40,000 in new placement fees within 180 days or your money back plus a $200 gift card.",
}

MINIMUM = {
    "cleaning_reactivation": "All I need to start is a list of 60 or more lost or dormant accounts or lost proposals.",
    "bookkeeping_reactivation": "All I need to start is a list of 60 or more former clients or lost inquiries.",
    "recruiting_reactivation": "All I need to start is a list of 60 or more dormant client accounts.",
    "cleaning_trigger": "All I need to start is your service area and the building types you want.",
    "bookkeeping_trigger": "All I need to start is the client profile you want more of.",
    "recruiting_outbound": "All I need to start is your specialty and geography.",
}
GENERIC_KEY = "cleaning_reactivation"

# ------------------------------------------------------- AI agents offer
# One offer key for the eight "2026 ... - AI Agents" campaigns (config/ids.json
# instantly.reply_offer_campaigns). Its first replies are Lorenzo's approved
# text of 2026-10-06, word for word, so they do not use the six offers'
# answer paragraph + "15-minute call" paragraph above: _ai_agents_skeleton
# builds them. The six offers' dicts (PRICING, MECHANISM, MINIMUM,
# CALL_PRICING) stay six keys; FIRST_REPLY_OFFERS is every key a first reply
# can be written for.
AI_AGENTS_KEY = "ai_agents"
# The only link a first reply may carry, and only in the booking_link reply
# (validate_draft allowed_url).
AI_AGENTS_BOOKING_URL = "https://api.leadconnectorhq.com/widget/booking/GDugwLmZNdsD13RBDnRu"
AI_AGENTS_TIME_ASK = "Would %s work for a 15 minute call?"
AI_AGENTS_DEFAULT_LEAD = "Glad to hear it."
_AI_AGENTS_MECHANISM = ("Glad you asked. Quick overview: I look at how %s runs day to day, find the tasks AI agents "
                        "can take over, and put that in a plan with what each one is worth in time and money. If "
                        "you like it, I build them. If not, the plan is yours to keep.")
# Answer paragraphs, %s = the company. "other" is held (a card Lorenzo edits)
# and starts from the mechanism answer.
AI_AGENTS_ANSWERS = {
    "mechanism": _AI_AGENTS_MECHANISM,
    "other": _AI_AGENTS_MECHANISM,
    "send_info": ("Most of what I'd send depends on how %s runs, so it's quicker to cover on a call. Short "
                  "version: I find the tasks AI agents can take over and show you what each one is worth in time "
                  "and money. The plan is free and yours to keep."),
    # The one email that carries a price figure (offers.md, PRICING REPLY ONLY).
    "pricing": ("The plan itself is free and yours to keep. Builds after that usually land between $400 and "
                "$5,300, depending on how many agents make sense for %s."),
}
# Said after the time ask, in the same paragraph.
AI_AGENTS_TAILS = {
    "pricing": "I'll have the exact number for you by the end of it.",
    "booking_link": "If neither fits, here's my calendar: %s" % AI_AGENTS_BOOKING_URL,
}
# The booking_link reply when there are no two times to offer.
AI_AGENTS_NO_SLOTS_LINK = "Here's my calendar: %s" % AI_AGENTS_BOOKING_URL
AI_AGENTS_REFERRAL = "Thanks for pointing me to %s. Would you mind looping %s in on this thread?"
FIRST_REPLY_OFFERS = tuple(MECHANISM) + (AI_AGENTS_KEY,)


def campaign_key_for(event: ReplyEvent) -> str:
    """The offers.md key this reply belongs to (public name for _key)."""
    return _key(event)


def _guess_key(niche: str, offer: str) -> str:
    return "%s_%s" % (niche, "outbound" if (offer == "outbound" and niche == "recruiting") else ("trigger" if offer == "outbound" else "reactivation"))


# The campaign offers a niche/offer pair can name (config/ids.json campaigns).
MAPPED_OFFERS = ("reactivation", "outbound")


def _key(event: ReplyEvent) -> str:
    if event.campaign_key in PRICING or event.campaign_key == AI_AGENTS_KEY:
        return event.campaign_key
    guess = _guess_key(event.niche or "cleaning", event.offer or "reactivation")
    return guess if guess in PRICING else GENERIC_KEY


# ---------------------------------------------------------------- slots
def fallback_free_slots(
    now: datetime,
    busy_blocks: Optional[Iterable[Tuple[Any, Any]]] = None,
    tz=slots.TZ,
    window: Tuple[int, int] = slots.SLOT_WINDOW,
    step_minutes: int = FALLBACK_STEP_MINUTES,
    days: int = FALLBACK_DAYS,
) -> List[str]:
    """Assume the Discovery Call open hours and remove busy blocks (with buffer)."""
    now_ct = slots.to_tz(slots.ensure_aware(now, tz), tz)
    blocks = []
    for start, end in busy_blocks or ():
        try:
            s = slots.to_tz(slots.parse_iso(start, tz), tz) - timedelta(minutes=BUFFER_MINUTES)
            e = slots.to_tz(slots.parse_iso(end, tz), tz) + timedelta(minutes=BUFFER_MINUTES)
            blocks.append((s, e))
        except (ValueError, TypeError):
            continue
    out = []  # type: List[str]
    for day_offset in range(0, days + 1):
        day = (now_ct + timedelta(days=day_offset)).date()
        if day.weekday() >= 5:
            continue
        minute = window[0] * 60
        while minute + slots.SLOT_MINUTES <= window[1] * 60:
            naive = datetime(day.year, day.month, day.day, minute // 60, minute % 60)
            try:
                dt = tz.localize(naive, is_dst=None)
            except Exception:  # noqa: BLE001 - DST edge
                dt = tz.localize(naive, is_dst=False)
            # the call we would book also needs its own trailing buffer, so a
            # candidate occupies slot + buffer and the busy block is already
            # padded by the same buffer on both sides
            dt_end = dt + timedelta(minutes=slots.SLOT_MINUTES + BUFFER_MINUTES)
            if not any(dt < e and dt_end > s for s, e in blocks):
                out.append(dt.isoformat())
            minute += step_minutes
    return out


def parse_ghl_free_slots(payload: Any) -> List[str]:
    """GHL free-slots returns {"2026-09-22": {"slots": [iso, ...]}, ..., "traceId": ...}."""
    out = []  # type: List[str]
    if payload is None:
        return out
    if isinstance(payload, list):
        return [str(x) for x in payload]
    if isinstance(payload, dict):
        if isinstance(payload.get("slots"), list):
            return [str(x) for x in payload["slots"]]
        for key, val in payload.items():
            if isinstance(val, dict) and isinstance(val.get("slots"), list):
                out.extend(str(x) for x in val["slots"])
            elif isinstance(val, list) and re.match(r"\d{4}-\d{2}-\d{2}", str(key)):
                out.extend(str(x) for x in val)
    return out


def free_slots_from_ghl(ghl, now: datetime) -> Optional[List[str]]:
    if ghl is None or not getattr(ghl, "has_token", False):
        return None
    start = slots.ensure_aware(now)
    end = slots.business_days_ahead(start, slots.MAX_BUSINESS_DAYS + 1)
    try:
        payload = ghl.get_free_slots(ghl.calendar_id, int(start.timestamp() * 1000), int(end.timestamp() * 1000), timezone="America/Chicago", user_id=ghl.user_id)
    except Exception as exc:  # noqa: BLE001 - never let the calendar break a draft
        logger.warning("GHL free-slots failed: %s", exc)
        return None
    if payload is None:
        return None
    parsed = parse_ghl_free_slots(payload)
    return parsed if parsed else None


def _within_availability(dt: datetime, window: Optional[Dict[str, Any]]) -> bool:
    if not window:
        return True
    try:
        import pytz

        tz = pytz.timezone(window.get("tz") or "America/Chicago")
        local = dt.astimezone(tz)
        start_h = int(window.get("start_hour", 0))
        end_h = int(window.get("end_hour", 24))
        minute = local.hour * 60 + local.minute
        return start_h * 60 <= minute and minute + slots.SLOT_MINUTES <= end_h * 60
    except Exception:  # noqa: BLE001
        return True


def proposed_time_ok(proposed_iso: Optional[str], now: datetime, already_offered: Optional[Iterable[Any]] = None) -> Optional[datetime]:
    """The lead's proposed time if it obeys the slot rules, else None."""
    if not proposed_iso:
        return None
    try:
        dt = slots.to_tz(slots.parse_iso(proposed_iso), slots.TZ)
    except (ValueError, TypeError):
        return None
    ok = slots.candidate_slots([dt], now, already_offered=already_offered)
    return ok[0] if ok else None


def choose_slots(
    event: ReplyEvent,
    classification: Classification,
    now: datetime,
    ghl=None,
    already_offered: Optional[Iterable[Any]] = None,
    busy_blocks: Optional[Iterable[Tuple[Any, Any]]] = None,
) -> Tuple[List[datetime], str]:
    """Two offerable slots (CT) and the source used ('ghl' | 'fallback')."""
    raw = free_slots_from_ghl(ghl, now)
    source = "ghl"
    if raw is None:
        raw = fallback_free_slots(now, busy_blocks=busy_blocks)
        source = "fallback"
    cands = slots.candidate_slots(raw, now, already_offered=already_offered)
    window = classification.extracted.availability_window
    if window:
        narrowed = [c for c in cands if _within_availability(c, window)]
        if narrowed:
            cands = narrowed
    return pick_two_varied(cands), source


# Preferred start hours for offered calls (mid-afternoon first); ties broken by the minute.
HOUR_PREFERENCE = [14, 15, 13, 16, 12, 17]


def _rank(dt: datetime) -> Tuple[int, int]:
    try:
        r = HOUR_PREFERENCE.index(dt.hour)
    except ValueError:
        r = len(HOUR_PREFERENCE)
    return (r, dt.minute)


def pick_two_varied(cands: List[datetime]) -> List[datetime]:
    """Two slots on different days, mid-afternoon preferred, different clock times when possible.
    Falls back to shared.slots.pick_two when fewer than two days are available."""
    if len(cands) < 2:
        return slots.pick_two(cands)
    by_day = {}  # type: Dict[Any, List[datetime]]
    for c in cands:
        by_day.setdefault(c.date(), []).append(c)
    days = sorted(by_day)
    if len(days) < 2:
        ordered = sorted(cands, key=_rank)
        return slots.pick_two(ordered)
    first_day = sorted(by_day[days[0]], key=_rank)
    first = first_day[0]
    second_day = sorted(by_day[days[1]], key=_rank)
    second = next((c for c in second_day if (c.hour, c.minute) != (first.hour, first.minute)), second_day[0])
    return [first, second]


# --------------------------------------------------------------- copy
def reply_subject(original: Optional[str]) -> str:
    subj = (original or "").strip()
    subj = re.sub(r"^\s*((re|fw|fwd|aw|ext)\s*:\s*)+", "", subj, flags=re.I).strip()
    return "Re: %s" % (subj or "your reply")


def greeting(event: ReplyEvent) -> str:
    return "Hey %s," % event.first_name if event.first_name else "Hey there,"


def _first_word(name: Optional[str]) -> str:
    parts = str(name or "").strip().split()
    return parts[0] if parts else ""


def _looks_like_a_person(name: str) -> bool:
    """True when ``name`` reads as a person's name the reply can address:
    the template gate's own name rule (letters, at most 3 words, no role
    word such as "The" or "Manager" first). Anything else, or any error,
    is False, so the draft falls back to the no-name wording."""
    try:
        from services.reply_engine import template_gate

        first = name.split(" ", 1)[0].lower().rstrip(".")
        return bool(template_gate._name_ok(name)) and first not in template_gate.ROLE_WORDS
    except Exception as exc:  # noqa: BLE001 - the no-name wording is always safe
        logger.warning("referral name check failed: %s", type(exc).__name__)
        return False


def referral_person(classification: Classification) -> Optional[str]:
    """The referral name to write in the reply, or None for the no-name
    wording ("the right person" ... "looping them in"). A role phrase ("talk
    to The Manager") is not a name: it used to render "looping The in"."""
    if classification.label != "positive_referral":
        return None
    name = " ".join(str(classification.extracted.referral_name or "").split())
    return name if name and _looks_like_a_person(name) else None


# The answer branches, in the order first_reply_branch checks them. The same
# names are template_approvals.FIRST_REPLY_BRANCHES (catalogue order).
FIRST_REPLY_BRANCH_ORDER = ("referral", "pricing", "send_info", "mechanism", "booking_link", "other", "default")
# booking_link (the lead asked for a Calendly or booking link) is an AI agents
# branch only; for the six offers it reads as if no question type were given.
BOOKING_LINK_OFFERS = (AI_AGENTS_KEY,)


def first_reply_branch(classification: Classification, offer: Optional[str] = None) -> str:
    """Which answer the first reply gives: referral, pricing, send_info,
    mechanism, booking_link (``offer`` in BOOKING_LINK_OFFERS only), other
    (also every neutral_question that is none of those) or default. The one
    branch order answer_paragraph renders from."""
    qt = classification.extracted.question_type
    if classification.label == "positive_referral":
        return "referral"
    if qt in ("pricing", "send_info", "mechanism"):
        return qt
    if qt == "booking_link":
        if offer in BOOKING_LINK_OFFERS:
            return "booking_link"
        # what it was before booking_link existed: a question is "other", a yes is "default"
        qt = None if classification.label == "positive_interested" else "other"
    if qt == "other" or classification.label == "neutral_question":
        return "other"
    return "default"


def first_reply_offer_key(event: ReplyEvent, campaign_key: Optional[str] = None) -> Optional[str]:
    """The offers.md key when the campaign is actually mapped, else None.

    _key falls back to cleaning_reactivation (and fills a missing niche or
    offer with a default) so a draft always has copy; that fallback must never
    choose a template id, or an unmapped campaign would auto-send the
    cleaning offer. Mapped means: the campaign key is an offers.md key, or
    (no campaign key) both niche and offer are set and name one."""
    key = campaign_key if campaign_key is not None else event.campaign_key
    if not key:
        if not event.niche or event.offer not in MAPPED_OFFERS:
            return None
        key = _guess_key(event.niche, event.offer)
    # the text build_draft renders is _key's; any disagreement is no id
    return key if key in FIRST_REPLY_OFFERS and key == _key(event) else None


def first_reply_template_id(event: ReplyEvent, classification: Classification,
                            campaign_key: Optional[str] = None) -> Optional[str]:
    """``first_reply.<offer>.<branch>.full``, the catalogue id of the template
    build_draft renders for this reply, or None when the campaign or offer is
    unmapped (see first_reply_offer_key). An id string only: the catalogue
    is never read here."""
    offer = first_reply_offer_key(event, campaign_key)
    if offer is None:
        return None
    return "first_reply.%s.%s.full" % (offer, first_reply_branch(classification, offer))


def _ai_agents_answer(event: ReplyEvent, classification: Classification, branch: str) -> Optional[str]:
    """The AI agents answer paragraph for ``branch``, or None for the
    branches whose time ask is the whole reply (default, booking_link)."""
    if branch == "referral":
        who = referral_person(classification)
        return AI_AGENTS_REFERRAL % (who or "the right person", _first_word(who) or "them")
    if branch in AI_AGENTS_ANSWERS:
        return AI_AGENTS_ANSWERS[branch] % (event.company or "your business")
    return None


def answer_paragraph(event: ReplyEvent, classification: Classification) -> str:
    key = _key(event)
    branch = first_reply_branch(classification, key)
    if key == AI_AGENTS_KEY:
        return _ai_agents_answer(event, classification, branch) or AI_AGENTS_DEFAULT_LEAD
    if branch == "referral":
        who = referral_person(classification)
        # Second mention is the first name only: "looping Dustin Landeis in"
        # twice in one sentence reads like a form letter.
        return "Appreciate you pointing me to %s. Would you mind looping %s in on this thread so I can send the details over?" % (
            who or "the right person", _first_word(who) or "them")
    if branch == "pricing":
        return PRICING[key]
    if branch == "send_info":
        return "%s Instead of sending a deck, I would rather walk you through it in 15 minutes and show you what it would look like for %s." % (
            MECHANISM[key], event.company or "your business")
    if branch == "mechanism":
        return "%s %s" % (MECHANISM[key], MINIMUM[key])
    if branch == "other":
        return OTHER_ANSWER % _as_clause(MECHANISM[key])
    return "Glad to hear it. %s" % MINIMUM[key]


def slot_paragraph(two: List[datetime], booking_link: Optional[str] = None, confirmed: Optional[datetime] = None,
                   early_note: Optional[str] = None, for_person: Optional[str] = None) -> str:
    """``for_person`` is the referral case (offers.md rule 5): the two slots are
    offered for the named third party, not for the person who just said "not
    me". Asking the replier "would Tue 2:00pm work for a 15-minute call?" after
    they declined to be the contact reads as if we did not listen.

    ``booking_link`` is ignored: no email carries a booking link (2026-09-23)."""
    if confirmed is not None:
        # Referral: the person replying is not the one taking the call, so the
        # invite waits until the named person is on the thread; sent now it
        # would land in the referrer's calendar.
        if for_person:
            who = "they are" if for_person == "them" else "%s is" % for_person
            return "%s CT works on my end. Once %s on the thread, I will send the invite over." % (
                slots.format_slot(confirmed), who)
        return "%s CT works on my end. I will send the invite over." % slots.format_slot(confirmed)
    if for_person:
        if not two:
            return "Would %s have 15 minutes for a quick call? %s" % (for_person, NO_SLOTS_ASK % for_person)
        return "Would %s work for %s?" % (slots.format_slots(two), for_person)
    if not two:
        return "Do you have 15 minutes for a quick call? %s" % (NO_SLOTS_ASK % "you")
    lead_in = early_note + " " if early_note else ""
    return "%sWould %s work for a 15-minute call?" % (lead_in, slots.format_slots(two))


def referral_pronoun(classification: Classification) -> Optional[str]:
    """"him"/"her" is a guess we have no right to make, so the slots are offered
    for the named person by first name, or for "them" when no name was given."""
    if classification.label != "positive_referral":
        return None
    return _first_word(referral_person(classification)) or "them"


def _ai_agents_skeleton(event: ReplyEvent, classification: Classification, two: List[datetime],
                        confirmed: Optional[datetime] = None, early_note: Optional[str] = None) -> str:
    """An AI agents first reply: Lorenzo's approved text (2026-10-06). The
    time ask is "Would {slots} work for a 15 minute call?"; default puts
    "Glad to hear it." in front of it, pricing and booking_link add their
    line after it, and the answer branches put their paragraph above it. A
    referral keeps the six offers' time paragraph for the named person. The
    no-slots, confirmed-time and refused-time wordings reuse the engine's
    own sentences."""
    branch = first_reply_branch(classification, AI_AGENTS_KEY)
    answer = _ai_agents_answer(event, classification, branch)
    if branch == "referral":
        ask = slot_paragraph(two, None, confirmed, early_note, for_person=referral_pronoun(classification))
    elif confirmed is not None:
        ask = "%s CT works on my end. I will send the invite over." % slots.format_slot(confirmed)
        if branch == "pricing":
            ask += " " + AI_AGENTS_TAILS["pricing"]
    elif not two:
        ask = "Do you have 15 minutes for a quick call? %s" % (
            AI_AGENTS_NO_SLOTS_LINK if branch == "booking_link" else NO_SLOTS_ASK % "you")
    else:
        ask = (early_note + " " if early_note else "") + AI_AGENTS_TIME_ASK % slots.format_slots(two)
        if branch in AI_AGENTS_TAILS:
            ask += " " + AI_AGENTS_TAILS[branch]
    if branch == "default":
        ask = "%s %s" % (AI_AGENTS_DEFAULT_LEAD, ask)
    parts = [greeting(event), ""] + ([answer, ""] if answer else []) + [ask, "", "Lorenzo"]
    return "\n".join(parts)


def skeleton(event: ReplyEvent, classification: Classification, two: List[datetime], booking_link: Optional[str],
             confirmed: Optional[datetime] = None, early_note: Optional[str] = None) -> str:
    if _key(event) == AI_AGENTS_KEY:
        return _ai_agents_skeleton(event, classification, two, confirmed=confirmed, early_note=early_note)
    parts = [greeting(event), "", answer_paragraph(event, classification), "",
             slot_paragraph(two, booking_link, confirmed, early_note, for_person=referral_pronoun(classification)), "", "Lorenzo"]
    return "\n".join(parts)


# ----------------------------------------------------------- validation
_DOLLAR_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?\s?(?:[kKmM]\b)?")
# "$2,500-5,000/mo" and "$1,500 to 2,500": the upper end of a range carries no
# second dollar sign, so it has to be read off the end of the first one.
_RANGE_TAIL_RE = re.compile(r"\A\s*(?:[-‐-―]|to\b)\s*(\d[\d,]*(?:\.\d+)?\s?(?:[kKmM]\b)?)")
# Percentages (Defect 8). Spelled-out numbers are turned into digits first
# (_spell_to_digits), then _PERCENT_CHAIN_RE reads a run of numbers joined by
# range/list words: "20-30%", "20–30%", "20 to 30 percent", "20% to 30%",
# "20 and 30 percent", "20, 25 or 30 percent", "25-percent", "25.5 %". In a run,
# a number counts when it or a LATER number in the run carries the % sign or
# the word percent ("20 and 30 percent" is both); numbers after the last one do
# not ("20% to 30 accounts" is 20 only). A number right after "$" or ":" is a
# price or a clock time, never the start of a percentage.
_PCT_NUM = r"\d+(?:,\d{3})*(?:\.\d+)?"
_PCT_WORD = r"(?:\s*%|[\s‐-―-]*\bper[\s-]?cents?(?:age)?\b|\s*\bpct\b)"
_PCT_SEP = r"(?:\s*,\s*(?:(?:and|or)\s+)?|\s+(?:and|or|to|through|thru)\s+(?:about\s+)?|\s*[‐-―-]\s*)"
_PERCENT_CHAIN_RE = re.compile(
    r"(?<![\d.$:,])(%s)(%s)?((?:%s%s(?:%s)?)*)" % (_PCT_NUM, _PCT_WORD, _PCT_SEP, _PCT_NUM, _PCT_WORD), re.I)
_PERCENT_LINK_RE = re.compile(r"%s(%s)(%s)?" % (_PCT_SEP, _PCT_NUM, _PCT_WORD), re.I)
_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
          "nine": 9}
_TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
          "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
         "eighty": 80, "ninety": 90}
_U = "|".join(sorted(_UNITS, key=len, reverse=True))
_TE = "|".join(sorted(_TEENS, key=len, reverse=True))
_TN = "|".join(sorted(_TENS, key=len, reverse=True))
_BELOW_100 = r"(?:(?:%s)(?:[\s-]+(?:%s))?|%s|%s)" % (_TN, _U, _TE, _U)
# "a hundred", "one hundred and twenty", "twenty-five", "thirty", "fifteen".
_SPELLED_RE = re.compile(
    r"\b(?:(?:a|%s)[\s-]+hundred(?:[\s-]+(?:and[\s-]+)?%s)?|%s)\b" % (_U, _BELOW_100, _BELOW_100), re.I)
# Percent phrasing that states no price, proof or guarantee term. Only the
# 100-percent idiom of certainty ("100% sure", "a hundred percent agree"); a
# "100% of the calls" or "100% of your money back" stays a claim and is refused.
_PERCENT_IDIOM_RE = re.compile(
    r"\b100\s*(?:%|[\s-]*per[\s-]?cent)\s+(?:sure|certain|honest|agree|agreed)\b", re.I)
# A figure offers.md marks "TO CONFIRM" must never be quoted in writing.
_TO_CONFIRM_RE = re.compile(r"TO CONFIRM", re.I)
_SENTENCE_CUT_RE = re.compile(r"(?s)^.*(?:[.;!?]\s|\n)")
# offers.md rule 8: never tell or imply that a bot wrote the email; no
# exclamation marks, no em dashes. "AI" and "automation" are allowed since the
# AI agents offer (Lorenzo, 2026-10-06): the offer is AI agents. Only U+2014
# used to count as a dash, while cadence.copy_problems already rejected U+2013
# too. The two validators share the same vocabulary.
_BANNED = [
    (re.compile("[\u2014\u2013\u2015]"), "em or en dash"),
    (re.compile(r"!"), "exclamation mark"),
    (re.compile(r"\bmachine learning\b", re.I), "mentions machine learning"),
    (re.compile(r"\balgorithms?\b", re.I), "mentions an algorithm"),
    (re.compile(r"\b(bot|bots|chatbot|large language model|LLM|GPT|Claude)\b", re.I), "mentions a bot"),
]


def _norm_one(raw: str) -> Optional[str]:
    raw = raw.replace("$", "").replace(",", "").replace(" ", "")
    mult = 1
    if raw[-1:].lower() == "k":
        mult, raw = 1000, raw[:-1]
    elif raw[-1:].lower() == "m":
        mult, raw = 1000000, raw[:-1]
    try:
        val = float(raw) * mult
    except ValueError:
        return None
    return ("%.2f" % val).rstrip("0").rstrip(".")


def _norm_dollars(text: str) -> List[str]:
    """Every dollar figure in ``text``, normalised. '$2,500-5,000' yields both ends."""
    body = text or ""
    out = []  # type: List[str]
    for m in _DOLLAR_RE.finditer(body):
        val = _norm_one(m.group(0))
        if val is not None:
            out.append(val)
        tail = _RANGE_TAIL_RE.match(body[m.end():])
        if tail:
            upper = _norm_one(tail.group(1))
            if upper is not None:
                out.append(upper)
    return out


def _norm_percent(raw: str) -> Optional[str]:
    try:
        return ("%.2f" % float((raw or "").replace(",", ""))).rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return None


def _spelled_value(words: str) -> Optional[int]:
    total, cur = 0, 0
    for w in re.split(r"[\s-]+", words.lower()):
        if not w or w == "and":
            continue
        if w == "hundred":
            total += (cur or 1) * 100
            cur = 0
        elif w == "a":
            cur = 1
        elif w in _UNITS:
            cur += _UNITS[w]
        elif w in _TEENS:
            cur += _TEENS[w]
        elif w in _TENS:
            cur += _TENS[w]
        else:
            return None
    return total + cur


def _spell_to_digits(text: str) -> str:
    """'twenty to thirty percent' -> '20 to 30 percent'. Every spelled number is
    converted; only the ones a percent word follows are read afterwards."""
    def repl(m):
        val = _spelled_value(m.group(0))
        return m.group(0) if val is None else str(val)
    return _SPELLED_RE.sub(repl, text or "")


def _norm_percents(text: str) -> List[str]:
    """Every percentage in ``text``, normalised ('20', '30', '35'), digits or
    spelled out. A range or list ('20-30%', '20 to 30 percent', '20 and 30
    percent', 'twenty to thirty percent') yields every number in it."""
    out = []  # type: List[str]
    for m in _PERCENT_CHAIN_RE.finditer(_spell_to_digits(text)):
        run = [(m.group(1), bool(m.group(2)))]
        for link in _PERCENT_LINK_RE.finditer(m.group(3) or ""):
            run.append((link.group(1), bool(link.group(2))))
        last = max((i for i, (_, has) in enumerate(run) if has), default=-1)
        for raw, _ in run[: last + 1]:
            val = _norm_percent(raw)
            if val is not None:
                out.append(val)
    return out


def allowed_percent_figures(offers_md: Optional[str] = None) -> List[str]:
    """Every percentage config/offers.md contains, for any offer (today 20, 30
    and the +35% reply-rate P.S. proof)."""
    return sorted(set(_norm_percents(offers_md if offers_md is not None else settings.OFFERS_MD)), key=float)


def unlisted_percent_figures(text: str, offers_md: Optional[str] = None,
                             allow_terms: Optional[Iterable[str]] = None) -> List[str]:
    """Percentages in ``text`` that config/offers.md does not state anywhere
    (Defect 8), in order of first appearance.

    The flat twin of the dollar check: "I take 25% of first-year contract value"
    is an invented price whichever offer the thread is on. The cross-offer
    check (_wrong_offer_percents) still decides whose 20-30% it is.

    Two things are not read: the lead's own name (``allow_terms``: a prospect
    called "110 Percent Cleaning" is not us quoting 110%) and the certainty
    idiom in _PERCENT_IDIOM_RE ("100% sure"), which states no term.
    """
    scanned = _blank_out(text, allow_terms) if allow_terms else (text or "")
    scanned = _PERCENT_IDIOM_RE.sub(" ", _spell_to_digits(scanned))
    allowed = set(allowed_percent_figures(offers_md))
    out = []  # type: List[str]
    for fig in _norm_percents(scanned):
        if fig not in allowed and fig not in out:
            out.append(fig)
    return out


def allowed_dollar_figures(offers_md: Optional[str] = None) -> List[str]:
    """Every figure config/offers.md actually contains (both ends of a range)."""
    return sorted(set(_norm_dollars(offers_md if offers_md is not None else settings.OFFERS_MD)))


def unconfirmed_dollar_figures(offers_md: Optional[str] = None) -> List[str]:
    """Figures offers.md marks 'TO CONFIRM'. They exist in the offer sheet but
    Lorenzo has not approved quoting them in writing, so a draft may not carry
    one (today: the $2,500-5,000/mo retainer). Only the clause the marker sits
    in is scanned, so the guarantee numbers in the same row stay quotable."""
    text = offers_md if offers_md is not None else settings.OFFERS_MD
    out = set()  # type: set
    for m in _TO_CONFIRM_RE.finditer(text or ""):
        before = (text or "")[: m.start()]
        clause = _SENTENCE_CUT_RE.sub("", before)
        out.update(_norm_dollars(clause))
    return sorted(out)


# A figure offers.md marks "PRICING REPLY ONLY" may appear in the approved
# pricing reply (first_reply.ai_agents.pricing.full) and in no other email.
_PRICING_REPLY_ONLY_RE = re.compile(r"PRICING REPLY ONLY", re.I)
PRICING_REPLY_ONLY_PROBLEM = "dollar figure $%s is only for the approved pricing reply"


def pricing_reply_only_dollar_figures(offers_md: Optional[str] = None) -> List[str]:
    """Figures offers.md marks 'PRICING REPLY ONLY' (today the AI agents
    $400 to $5,300 band). Read like unconfirmed_dollar_figures: only the
    clause the marker sits in."""
    text = offers_md if offers_md is not None else settings.OFFERS_MD
    out = set()  # type: set
    for m in _PRICING_REPLY_ONLY_RE.finditer(text or ""):
        clause = _SENTENCE_CUT_RE.sub("", (text or "")[: m.start()])
        out.update(_norm_dollars(clause))
    return sorted(out)


_QUOTED_PROOF_RE = re.compile(r'"([^"]{20,})"')
_WS = re.compile(r"\s+")


def offer_proof_rows(offers_md: Optional[str] = None) -> List[Dict[str, Any]]:
    """The offers.md proof table, one row per offer type.

    The table is headed "one per offer type, never mixed": the reactivation
    proof ($6M recovered) and the outbound proof ($180,000 in 90 days) are not
    interchangeable, and Lorenzo's own sent mail observes that split exactly.
    """
    text = offers_md if offers_md is not None else settings.OFFERS_MD
    rows = []  # type: List[Dict[str, Any]]
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 3:
            continue
        quoted = _QUOTED_PROOF_RE.search(cells[1])
        if not quoted:
            continue
        keys = [k.strip() for k in cells[2].split(",") if "_" in k]
        if not keys:
            continue
        proof = quoted.group(1)
        rows.append({"offer_type": cells[0], "proof": proof, "keys": keys, "figures": set(_norm_dollars(proof)),
                     "percents": set(_norm_percents(proof))})
    return rows


_OFFER_KEY_RE = re.compile(r"^[a-z][a-z0-9]*_[a-z0-9_]+$")


def offer_guarantee_rows(offers_md: Optional[str] = None) -> List[Dict[str, Any]]:
    """The offers.md 'six offers' table: one row per campaign key.

    ``| Key | Mechanism | Guarantee / pricing answer | Minimum to start |``.
    Only the guarantee/pricing cell is read, because that is the cell whose
    numbers a draft may put in front of a prospect.
    """
    text = offers_md if offers_md is not None else settings.OFFERS_MD
    rows = []  # type: List[Dict[str, Any]]
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 3:
            continue
        key = cells[0].strip().strip("`*")
        if not _OFFER_KEY_RE.match(key):
            continue
        rows.append({"key": key, "guarantee": cells[2], "figures": set(_norm_dollars(cells[2])),
                     "percents": set(_norm_percents(cells[2]))})
    return rows


def wrong_offer_guarantee_problems(text: str, campaign_key: Optional[str], offers_md: Optional[str] = None) -> List[str]:
    """Problems raised by promising another offer's guarantee in writing.

    validate_draft only cross-checked the proof table, so a Sonnet polish that
    swapped one guarantee for another passed clean: every figure in the six
    offers exists somewhere in offers.md, so allowed_dollar_figures,
    unconfirmed_dollar_figures and wrong_offer_proof_problems all accept it. A
    commercial-cleaning prospect could be promised "$15,000 in new annual client
    fees within 90 days or your money back", which is the bookkeeping
    guarantee.
    """
    if not campaign_key:
        return []
    rows = offer_guarantee_rows(offers_md)
    mine = [r for r in rows if r["key"] == campaign_key]
    if not mine:
        return []
    my_figures = set()  # type: set
    for r in mine:
        my_figures |= r["figures"]
    in_body = set(_norm_dollars(text))
    problems = []  # type: List[str]
    for row in rows:
        if row["key"] == campaign_key:
            continue
        for fig in sorted(row["figures"] - my_figures):
            if fig in in_body:
                problems.append("dollar figure $%s is the '%s' guarantee, not %s's; offers.md gives one guarantee per offer"
                                % (fig, row["key"], campaign_key))
    problems.extend(_wrong_offer_percents(text, campaign_key, mine, [r for r in rows if r["key"] != campaign_key],
                                          lambda r: r["key"], "pricing"))
    return problems


def _wrong_offer_percents(text: str, campaign_key: str, mine: List[Dict[str, Any]], others: List[Dict[str, Any]],
                          name_of: Any, what: str) -> List[str]:
    """Percentages in ``text`` that offers.md gives to OTHER offers and not to
    this one (SAL-11): a trigger offer is a retainer, so "20 to 30 percent" in
    a cleaning_trigger draft is the reactivation commission. One problem per
    figure. A percentage no offer row carries (the "+35% reply rate" P.S.
    proof) is not an offer's, and is left to the other checks."""
    in_body = set(_norm_percents(text))
    if not in_body:
        return []
    my_percents = set()  # type: set
    for r in mine:
        my_percents |= r.get("percents") or set()
    owners = {}  # type: Dict[str, List[str]]
    for row in others:
        for fig in (row.get("percents") or set()) - my_percents:
            if fig in in_body:
                owners.setdefault(fig, [])
                if name_of(row) not in owners[fig]:
                    owners[fig].append(name_of(row))
    return ["percentage %s%% is the %s of %s, not %s's; offers.md gives one per offer"
            % (fig, what, ", ".join(owners[fig]), campaign_key) for fig in sorted(owners, key=float)]


def _blank_out(text: str, terms: Optional[Iterable[str]]) -> str:
    """Replace lead-supplied spans with spaces before the banned-word scan.

    draft.answer_paragraph interpolates event.company, so an ordinary
    commercial-cleaning name like "Automated Building Services" made every draft
    for that prospect permanently unsendable ("mentions automation") with no
    path back except /edit. The prospect's own name is not our copy.
    """
    out = text or ""
    for term in terms or ():
        term = (term or "").strip()
        if len(term) < 3:
            continue
        idx = out.lower().find(term.lower())
        while idx >= 0:
            out = out[:idx] + (" " * len(term)) + out[idx + len(term):]
            idx = out.lower().find(term.lower(), idx + len(term))
    return out


def lead_terms(event: Optional[ReplyEvent], state: Optional[LeadState] = None) -> List[str]:
    """The lead-supplied strings a draft interpolates verbatim."""
    out = []  # type: List[str]
    for source in (event, state):
        if source is None:
            continue
        for attr in ("company", "first_name", "last_name"):
            value = getattr(source, attr, None)
            if value and str(value).strip() and str(value).strip() not in out:
                out.append(str(value).strip())
    return out


def _proof_fingerprint(proof: str) -> str:
    return _WS.sub(" ", (proof or "")).strip().lower()[:48]


def wrong_offer_proof_problems(text: str, campaign_key: Optional[str], offers_md: Optional[str] = None) -> List[str]:
    """Problems raised by quoting the OTHER offer type's proof.

    validate_draft used to check dollar figures against offers.md as one flat
    set, so the reactivation proof line inside an outbound draft (and the
    reverse) passed clean: every figure in it exists somewhere in the file.
    """
    if not campaign_key:
        return []
    rows = offer_proof_rows(offers_md)
    mine = [r for r in rows if campaign_key in r["keys"]]
    if not mine:
        return []
    my_figures = set()
    for r in mine:
        my_figures |= r["figures"]
    body = _WS.sub(" ", text or "").lower()
    problems = []  # type: List[str]
    for row in rows:
        if campaign_key in row["keys"]:
            continue
        if _proof_fingerprint(row["proof"]) in body:
            problems.append("proof line for '%s' used in a %s draft; offers.md allows one per offer type, never mixed"
                            % (row["offer_type"], campaign_key))
            continue
        for fig in sorted(row["figures"] - my_figures):
            if fig in _norm_dollars(text):
                problems.append("dollar figure $%s belongs to the '%s' proof, not to %s" % (fig, row["offer_type"], campaign_key))
    problems.extend(_wrong_offer_percents(text, campaign_key, mine, [r for r in rows if campaign_key not in r["keys"]],
                                          lambda r: "the '%s' proof" % r["offer_type"], "figure"))
    return problems


def validate_draft(body: str, offers_md: Optional[str] = None, booking_link: Optional[str] = None,
                   campaign_key: Optional[str] = None, allow_terms: Optional[Iterable[str]] = None,
                   first_reply: bool = False, allowed_url: Optional[str] = None,
                   pricing_reply: bool = False) -> List[str]:
    """Return a list of problems (empty == sendable).

    ``first_reply``: the body is a first reply, which must not carry a link of
    any kind (the passed ``booking_link``, settings.BOOKING_URL, any URL, a link
    placeholder or booking wording such as "grab a time"; see _has_booking_link).
    ``allowed_url`` is the one exception: the booking_link reply
    (first_reply.<offer>.booking_link.full) passes AI_AGENTS_BOOKING_URL, and
    exactly that URL is not read as a link; any other link still is.

    ``pricing_reply``: the body is the approved pricing reply
    (first_reply.ai_agents.pricing.full), the only email that may carry a
    figure offers.md marks PRICING REPLY ONLY.

    ``allow_terms`` are lead-supplied strings the draft interpolates (company,
    first name). They are blanked out before the banned-word scan only: a
    prospect called "Automated Building Services" is not the draft mentioning
    automation. Every other check still reads the full body.
    """
    problems = []  # type: List[str]
    text = body or ""
    if not text.strip():
        return ["empty body"]
    scanned = _blank_out(text, allow_terms) if allow_terms else text
    for rx, why in _BANNED:
        if rx.search(scanned):
            problems.append(why)
    allowed = set(allowed_dollar_figures(offers_md))
    unconfirmed = set(unconfirmed_dollar_figures(offers_md))
    reply_only = set() if pricing_reply else set(pricing_reply_only_dollar_figures(offers_md))
    for fig in _norm_dollars(text):
        if fig not in allowed:
            problems.append("dollar figure $%s not in offers.md" % fig)
        elif fig in unconfirmed:
            problems.append("dollar figure $%s is marked TO CONFIRM in offers.md; do not quote it in writing" % fig)
        elif fig in reply_only:
            problems.append(PRICING_REPLY_ONLY_PROBLEM % fig)
    # Defect 8: the flat percentage twin of the dollar check above. The problem
    # text ends "% not in offers.md"; cadence._SHARED_PROBLEM_CODES keys on that.
    for fig in unlisted_percent_figures(text, offers_md, allow_terms):
        problems.append("percentage %s%% not in offers.md" % fig)
    problems.extend(wrong_offer_proof_problems(text, campaign_key, offers_md))
    problems.extend(wrong_offer_guarantee_problems(text, campaign_key, offers_md))
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if not lines or lines[-1] != "Lorenzo":
        problems.append("must end with the signature line 'Lorenzo'")
    # ``scanned``: a lead whose company is "Acme.io" is not the draft adding a link.
    if first_reply and _has_booking_link(_blank_out(scanned, [allowed_url]) if allowed_url else scanned,
                                         booking_link):
        problems.append("contains a booking link")
    if len(text) > 1500:
        problems.append("too long (%d chars)" % len(text))
    return problems


# First replies carry no link of any kind (2026-09-23), so any URL counts:
# a scheme or www., a bare domain followed by a path, or a bare domain on a
# common TLD. No first-reply template contains one except the booking_link
# reply's AI_AGENTS_BOOKING_URL, which validate_draft's allowed_url blanks out
# for that template only, so this cannot block a legitimate draft.
_URL_RE = re.compile(
    r"(?:https?://|\bwww\.)"
    r"|\b[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.[a-z]{2,24}/"
    r"|\b[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.(?:com|net|org|io|ai|co|app|ly|link|biz|info|xyz|me|us)\b",
    re.IGNORECASE)
# Link placeholders and booking wording: "[link]", "<booking_link>",
# "{booking_url}", "calendar link", "book a time", "pick a slot" ...
_LINK_PLACEHOLDER_RE = re.compile(r"[\[{<][^\]}>\n]{0,40}(?:link|url)[^\]}>\n]{0,40}[\]}>]", re.IGNORECASE)
_LINK_PHRASES = ("grab a time", "booking link", "booking page", "calendar link", "scheduling link", "book a time",
                 "pick a slot", "use my calendar", "calendly")


def _has_booking_link(text: str, booking_link: Optional[str] = None) -> bool:
    """No email carries a booking link (2026-09-23); this keeps one from
    sneaking back in through the template or the LLM polish: the passed or
    configured link, any URL, a link placeholder or booking-link wording."""
    low = text.lower()
    if any(p in low for p in _LINK_PHRASES):
        return True
    for url in (booking_link, getattr(settings, "BOOKING_URL", None)):
        if url and url.strip() and url.strip().lower() in low:
            return True
    return bool(_URL_RE.search(text) or _LINK_PLACEHOLDER_RE.search(text))


# ----------------------------------------------------------------- main
def _draft_system(skel: str) -> str:
    try:
        template = (PROMPTS_DIR / "draft_system.md").read_text(encoding="utf-8")
    except OSError:
        template = "Return only the email body.\n\n{{OFFERS_MD}}\n\n{{SKELETON}}"
    return template.replace("{{OFFERS_MD}}", settings.OFFERS_MD or "").replace("{{SKELETON}}", skel)


def template_gate_flags(template_id: Optional[str]) -> Dict[str, Any]:
    """validate_draft's exceptions for a first reply's template id: the
    booking URL in first_reply.ai_agents.booking_link.full, the PRICING
    REPLY ONLY band in first_reply.ai_agents.pricing.full. Every other id
    gets neither (template_gate passes the same flags)."""
    parts = str(template_id or "").split(".")
    if len(parts) != 4 or parts[0] != "first_reply" or parts[3] != "full" or parts[1] not in BOOKING_LINK_OFFERS:
        return {}
    if parts[2] == "booking_link":
        return {"allowed_url": AI_AGENTS_BOOKING_URL}
    if parts[2] == "pricing" and parts[1] == AI_AGENTS_KEY:
        return {"pricing_reply": True}
    return {}


def first_reply_gate_flags(event: ReplyEvent, classification: Classification) -> Dict[str, Any]:
    """template_gate_flags for the first reply build_draft renders."""
    key = _key(event)
    return template_gate_flags("first_reply.%s.%s.full" % (key, first_reply_branch(classification, key)))


def build_draft(
    event: ReplyEvent,
    classification: Classification,
    state: Optional[LeadState] = None,
    ghl=None,
    now: Optional[datetime] = None,
    already_offered: Optional[Iterable[Any]] = None,
    busy_blocks: Optional[Iterable[Tuple[Any, Any]]] = None,
    booking_link: Optional[str] = None,
    core_text: Optional[str] = None,
    use_llm: Optional[bool] = None,
    others_offered: Optional[Iterable[Any]] = None,
) -> Draft:
    """already_offered: every slot to avoid for NEW picks (other leads' and this lead's earlier offers).
    others_offered: slots held by OTHER leads only; a time this lead proposes may match one we offered them."""
    now = slots.ensure_aware(now) if now is not None else event.received_at
    # booking_link is still accepted (app.py passes it) but never written into
    # the draft; validate_draft uses it only to reject a draft that contains it.
    offered = list(already_offered or [])
    if state is not None:
        offered.extend(state.offered_slots)
    blocked_for_confirm = list(others_offered) if others_offered is not None else offered

    confirmed = proposed_time_ok(classification.extracted.proposed_time, now, already_offered=blocked_for_confirm)
    early_note = None
    two = []  # type: List[datetime]
    source = "confirmed"
    if confirmed is None:
        two, source = choose_slots(event, classification, now, ghl=ghl, already_offered=offered, busy_blocks=busy_blocks)
        asked_text = asked_time_text(event, classification)
        if asked_text:
            early_note = "%s is tough on my end." % asked_text

    skel = skeleton(event, classification, two, booking_link, confirmed=confirmed, early_note=early_note)
    body = skel
    model = "template"
    rationale = "template per offers.md (%s, %s, slots from %s)" % (classification.label, _key(event), source)

    terms = lead_terms(event, state)
    gate_flags = first_reply_gate_flags(event, classification)
    call_llm = (not llm.is_fake()) if use_llm is None else use_llm
    if call_llm:
        user = "Lead: %s at %s\nLabel: %s\nTheir words:\n<<<\n%s\n>>>" % (
            event.first_name or "unknown", event.company or "unknown", classification.label, (core_text or event.text or "")[:2000])
        try:
            polished = llm.complete("draft", _draft_system(skel), user, max_tokens=500)
            polished = polished.strip() if isinstance(polished, str) else ""
            probs = validate_draft(polished, booking_link=booking_link, campaign_key=_key(event), allow_terms=terms,
                                   first_reply=True, **gate_flags)
            keeps_slots = (not two) or slots.format_slots(two) in polished
            # No numbers over email (2026-09-24): a polish may not add a price,
            # percentage or guarantee figure the template does not carry.
            added = sorted(set("$" + f for f in _norm_dollars(polished)) - set("$" + f for f in _norm_dollars(skel))
                           | set(f + "%" for f in _norm_percents(polished)) - set(f + "%" for f in _norm_percents(skel)))
            if added:
                probs = list(probs) + ["states a price, percentage or guarantee figure (%s); never in an email"
                                       % ", ".join(added)]
            if polished and not probs and keeps_slots:
                body, model = polished, llm.model_for("draft")
                rationale += "; polished by %s" % model
            else:
                logger.warning("LLM draft rejected (%s); using template", probs or "slots changed")
                rationale += "; LLM draft rejected (%s)" % ("; ".join(probs) or "slots changed")
        except Exception as exc:  # noqa: BLE001
            logger.warning("draft LLM failed: %s", exc)
            rationale += "; LLM failed (%s)" % exc

    problems = validate_draft(body, booking_link=booking_link, campaign_key=_key(event), allow_terms=terms,
                              first_reply=True, **gate_flags)
    offered_slots = [confirmed.isoformat()] if confirmed is not None else [d.isoformat() for d in two]
    # CT3: the template id only for the template render. A polished body is
    # other text, so it carries no id and is always a card. The hash is
    # stamped by the pipeline (template_gate.stamp), never here.
    template_id = first_reply_template_id(event, classification) if model == "template" else None
    return Draft(
        subject=reply_subject(event.subject),
        body_text=body,
        offered_slots=offered_slots,
        booking_link=None,
        rationale=rationale,
        model=model,
        label=classification.label,
        problems=problems,
        template_id=template_id,
    )


def first_reply_bindings(event: ReplyEvent, classification: Classification, d: Draft,
                         state: Optional[LeadState] = None) -> Dict[str, str]:
    """{placeholder: value} for what build_draft rendered into ``d`` from this
    reply: the lead's first name and company, the referral name when one was
    written, the offered slots and the refused time (no booking link: a first
    reply carries none, 2026-09-23). Only
    placeholders that got a value (not their fallback wording); the template
    gate pins each placeholder to its value (CT3 bindings).

    The name and the company are bound to the stored lead record (``state``,
    as read before this reply) when it has them, not to the event that
    rendered them: a reply whose sender name or company differs from the
    record is refused by the gate (a card), never sent under the approval."""
    out = {}  # type: Dict[str, str]
    if event.first_name:
        out["first_name"] = (getattr(state, "first_name", None) or event.first_name)
    if event.company:
        out["company"] = (getattr(state, "company", None) or event.company)
    who = referral_person(classification)
    if who:
        out["referral_name"] = who
        out["referral_first_name"] = _first_word(who)
    try:
        offered = [slots.to_tz(slots.parse_iso(s), slots.TZ) for s in (d.offered_slots or [])]
        if offered:
            out["slots"] = slots.format_slots(offered)
    except (ValueError, TypeError):
        pass
    asked_text = asked_time_text(event, classification)
    if asked_text:
        out["asked_time"] = asked_text
    return out


def lead_zone_of(event: ReplyEvent) -> Optional[Any]:
    """The zone the lead named in their own words ("Thursday 11am ET"), or
    None when they named none. Read the way classify read the proposed time:
    classify.core_text of the reply, then slots.parse_proposed_time's own
    zone detection (quotes and phone numbers stripped), so the zone is the
    one the time was parsed in. Taken from the event alone, so build_draft
    and first_reply_bindings always agree."""
    text = event.text or ""
    try:
        from services.reply_engine.classify import core_text

        text = core_text(text)
    except Exception as exc:  # noqa: BLE001 - the plain text still names the zone
        logger.warning("core_text unavailable for the lead zone: %s", type(exc).__name__)
    try:
        return slots.detect_tz(slots.strip_phone_numbers(slots.strip_quoted(text)))
    except Exception as exc:  # noqa: BLE001 - no zone reads as Central, labelled CT
        logger.warning("lead zone detection failed: %s", type(exc).__name__)
        return None


def asked_time_text(event: ReplyEvent, classification: Classification) -> Optional[str]:
    """{asked_time}: the time the lead proposed, in the zone they wrote it in
    and with its label ("Thu 11:00am ET"); "Thu 11:00am CT" when they named
    Central or no zone. None when there is no readable proposed time."""
    proposed = classification.extracted.proposed_time
    if not proposed:
        return None
    try:
        asked = slots.to_tz(slots.parse_iso(proposed), slots.TZ)
    except (ValueError, TypeError):
        return None
    return slots.format_asked_time(asked, lead_zone_of(event))


def busy_blocks_from_ids(exclude_email: Optional[str] = None) -> List[Tuple[str, str]]:
    """Known bookings recorded in config/ids.json (google_calendar.booked_this_week).

    ``exclude_email`` drops the blocks that ARE this lead's own call. Without
    it, Sopio writing "Thursday 4pm Eastern works for me" collides with her own
    15:00 CT Discovery Call and gets counter-proposed around it, and Ilmi asking
    to move her 11:30 is offered 12:30/13:00 because 12:00 runs into the buffer
    around the very appointment she is trying to move.
    """
    out = []  # type: List[Tuple[str, str]]
    wanted = (exclude_email or "").strip().lower()
    for ev in settings.IDS.get("google_calendar", {}).get("booked_this_week", []) or []:
        start = ev.get("start")
        if not start:
            continue
        if wanted and str(ev.get("email") or "").strip().lower() == wanted:
            continue
        try:
            s = slots.parse_iso(start)
        except (ValueError, TypeError):
            continue
        out.append((s.isoformat(), (s + timedelta(minutes=30)).isoformat()))
    return out
