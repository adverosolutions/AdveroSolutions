"""The E2 research line validator (section 1): may this model-written line go
into E2 without a per-email Approve?

E2 is "Hey {first_name},\\n\\n{research_line}\\n\\nFifteen minutes is enough
for me to show you how this would run for {company}. ..." and
``{research_line}`` is written per lead by a model from the lead's own
website, reviews or listing. Lorenzo approves the frame plus RULES_TEXT once;
after that E2 auto-sends only when ``validate`` passes the line (the template
gate re-runs it and pins ``rules_sha``). Anything that fails falls back to the
fixed approved line for the offer. So the validator is strict: when in doubt,
it fails.

    RULES_VERSION                       # bump by hand when a check changes
    RULES_TEXT                          # the rules as Lorenzo reads and approves them
    rules_sha() -> str                  # sha256(RULES_TEXT + "\\n" + str(RULES_VERSION))
    validate(line, evidence, context) -> ResearchVerdict

``evidence`` is what the research step stores:

    {"facts": [{"text": str, "source_url": str, "excerpt": str}, ...],   # 1 to 3
     "identity": {"source_url": str, "matched_on": "city" | "phone"}}

``context``:

    {"company": str, "company_spoken": str,
     "offer_branch": "reactivation" | "outbound",
     "niche": "cleaning" | "bookkeeping" | "recruiting",
     "website_domain": str, "city": Optional[str]}

Every check is deterministic and each failing one adds its reason code (in
check order, no repeats); ``ok`` only when none fail. The word lists are the
module-level tuples below so the rules can be audited; RULES_TEXT states the
rules only, not the lists.

What this cannot catch, by design:

- Names that are really on the page. A capitalised word must appear in an
  excerpt, which stops invented names, but a real owner, staff member,
  reviewer or client named on the page passes (rule 7 still forbids them;
  the prompt carries that rule). The first word of each sentence is exempt
  from the name check, so a sentence that opens with a name is not caught
  either.
- Whether a number is used for what the excerpt uses it for ("over 200
  reviews" passes when the excerpt says "213 Main St").
- Whether the tie-back is a new claim about the business, whether the facts
  are praise only, and whether a fact is generic. The tie-back and branch
  word checks are lexical.

Versioning: the hash Lorenzo approves (``rules_sha``) covers only RULES_TEXT
and RULES_VERSION, not this code. So RULES_VERSION must be bumped whenever
``validate``'s logic changes (a check, a word list, a limit), even when
RULES_TEXT does not; otherwise a changed validator would still match the old
approval.

The raw line is checked before it is normalised: a line break
(``line_break``), a control character (``control_char``), leading or trailing
whitespace (``surrounding_space``) or more than 300 characters
(``too_long_chars``) fail it. The other checks run on the normalised line
(stripped, internal whitespace collapsed), which is what ``line`` returns.

Pure: no network, no model, no clock, no environment reads, no randomness.
Never raises: malformed input gives ``ok=False`` with a reason code, and any
unexpected error inside a check gives ``validator_error``.
"""
import hashlib
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlsplit

# Bump by hand whenever validate()'s logic changes: the approved hash covers
# only RULES_TEXT and RULES_VERSION, not the checks below.
RULES_VERSION = 1

RULES_TEXT = (
    "E2 research line rules\n"
    "\n"
    "The research line is written for one lead from that lead's own pages. It sits "
    "right after \"Hey {first_name},\" and right before \"Fifteen minutes is enough "
    "for me to show you how this would run for {company}.\" E2 goes out on its own "
    "only when the line passes every rule below. Otherwise the approved fallback "
    "line for the offer is used instead.\n"
    "\n"
    "1. One or two sentences, 35 words or fewer. One to three facts about their "
    "business, then what that means we could do for them under this offer. Stop there.\n"
    "2. It must tie back into the offer. Reactivation: the facts point to past or lost "
    "clients we could win back. Outbound: the facts point to the triggers we'd watch "
    "turning into work for them. The tie-back may state the obvious conclusion of a "
    "fact, never a new claim about their business.\n"
    "3. Lorenzo's first person, plain and spoken, normal capitalization. Don't start "
    "with \"I think\", don't open with \"I saw\" or \"I noticed\", don't mention times, "
    "calls or booking, and don't ask a question.\n"
    "4. No Claudeisms: nothing after the tie-back that restates, sums up or sells the "
    "point just made.\n"
    "5. Facts only from their own website, their reviews or their listing (Google, "
    "Yelp, BBB), after confirming the business by its city or phone number. Every fact "
    "has the page it came from.\n"
    "6. Numbers exactly as found or rounded down (\"over 200\"), never up. Years quoted "
    "as found, no date math. Review counts, not star ratings.\n"
    "7. Never: guesses (\"must be\", \"probably\", \"I bet\", \"looks like you\"); "
    "market facts that are not on their own pages; a line that is only praise; "
    "anything negative; pricing, fees, percentages, guarantees or results; names of "
    "competitors, owners, staff, reviewers or their clients; quoted reviews; dates "
    "that could be wrong on the day it sends; any mention of research, tools, AI or "
    "automation; URLs, placeholders, em or en dashes, exclamation marks, emojis.\n"
    "8. The company name the way a person says it: no LLC, Inc. or taglines.\n"
    "9. NONE when unsure: when the business can't be confirmed, the facts are generic, "
    "nothing connects to the offer or the line would need a guess, the answer is NONE "
    "and the fallback line is used. NONE always beats a stretch.\n"
)

MAX_WORDS = 35
MAX_SENTENCES = 2
MAX_FACTS = 3
MAX_CHARS = 300   # on the raw line, before normalising
# What str.splitlines() breaks on.
LINE_BREAKS = ("\n", "\r", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85",
               "\u2028", "\u2029")

OFFER_BRANCHES = ("reactivation", "outbound")
NICHES = ("cleaning", "bookkeeping", "recruiting")
MATCHED_ON = ("city", "phone")

# Listing hosts a fact or the identity match may come from (any subdomain).
LISTING_HOSTS = ("google.com", "maps.google.com", "g.co", "g.page",
                 "business.google.com", "yelp.com", "bbb.org")
# A platform name may be named in the line when a fact comes from its host
# ("180 Google reviews"), even if the excerpt does not spell it out.
PLATFORM_NAMES = (
    ("Google", ("google.com", "g.co", "g.page")),
    ("Yelp", ("yelp.com",)),
    ("BBB", ("bbb.org",)),
)

# Word lists. Single words and phrases are matched whole-word on the
# lowercased line (curly apostrophes read as straight ones).
OPENERS = ("i think", "i saw", "i noticed", "i've noticed", "i have noticed",
           "i've seen", "i see", "i came across", "i was looking", "i found")
BOOKING_WORDS = ("call", "calls", "calling", "phone call", "book", "booking",
                 "booked", "calendar", "calendars", "schedule", "scheduled",
                 "scheduling", "minute", "minutes", "meeting", "meetings",
                 "appointment", "appointments", "zoom", "chat", "today",
                 "tomorrow", "o'clock", "monday", "tuesday", "wednesday",
                 "thursday", "friday", "saturday", "sunday")
GUESS_WORDS = ("must be", "must have", "probably", "i bet", "looks like you",
               "seems like", "i assume", "i imagine", "i'd imagine", "i'm guessing",
               "i guess", "i'd guess", "i suspect", "maybe", "might be", "likely",
               "chances are", "presumably", "surely", "i'm sure")
MONEY_WORDS = ("percent", "percentage", "guarantee", "guarantees", "guaranteed",
               "price", "prices", "priced", "pricing", "fee", "fees", "cost",
               "costs", "roi", "revenue", "profit", "profits", "money", "dollars",
               "discount", "discounts", "free", "cheap", "affordable", "rate",
               "rates", "results", "income")
MONEY_CHARS = ("$", "%", "\u00a3", "\u20ac")
RESEARCH_WORDS = ("research", "researched", "researching", "googled", "googling",
                  "looked you up", "looked up", "found online", "ai", "a.i.",
                  "automation", "automations", "automated", "automate", "tool",
                  "tools", "software", "bot", "bots", "chatgpt", "gpt",
                  "algorithm", "website", "websites", "web site")
STAR_WORDS = ("star", "stars", "rated", "rating", "ratings")
STALE_PHRASES = ("this year", "last year", "this month", "last month", "this week",
                 "last week", "this season", "recently", "just opened",
                 "just launched", "just added", "new this", "newly", "latest",
                 "currently", "right now", "now")
# Month names are matched case-sensitively (capitalised), so "may" and
# "march" as ordinary words pass.
MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December",
          "Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug", "Sep", "Sept",
          "Oct", "Nov", "Dec")
NEGATIVE_WORDS = ("bad", "worst", "worse", "complaint", "complaints", "struggling",
                  "struggle", "struggles", "slow", "lost money", "problem",
                  "problems", "poor", "terrible", "awful", "unhappy", "failing",
                  "failed", "declining", "issue", "issues")
CLAUDEISMS = ("which means", "that way", "no more", "the whole point",
              "simple as that", "it just works", "that's a real opportunity",
              "that's huge", "game changer", "game-changer", "win-win",
              "no-brainer", "no brainer", "on autopilot", "at the end of the day",
              "bottom line", "in other words", "the best part",
              "without lifting a finger", "so you can focus")
# A clause that starts after the tie-back ("... we could win back, which ...").
TAIL_KICKER = re.compile(
    r"(?:[,;:]\s*(?:which|so|and|meaning|giving|plus|that|without|all|because)\b)"
    r"|\b(?:so that|so you|which|without|meaning)\b")
# "one" is left out on purpose: it is mostly a pronoun ("one of those roles").
SPELLED_NUMBERS = ("two", "three", "four", "five", "six", "seven", "eight", "nine",
                   "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
                   "sixteen", "seventeen", "eighteen", "nineteen", "twenty",
                   "thirty", "forty", "fifty", "sixty", "seventy", "eighty",
                   "ninety", "hundred", "hundreds", "thousand", "thousands",
                   "million", "millions", "dozen", "dozens")
TIE_BACK = re.compile(r"\b(?:we could|we'd|i could|i'd|we can)\b", re.IGNORECASE)
BRANCH_WORDS = {
    "reactivation": ("back", "past", "former", "before", "again", "lost", "quiet",
                     "returning"),
    "outbound": ("new", "every", "each", "next", "in front of", "watch", "when"),
}
OVER_WORDS = ("over", "more than")
DASH_CHARS = ("\u2012", "\u2013", "\u2014", "\u2015", "\u2212")
QUOTE_CHARS = ("\"", "\u201c", "\u201d", "\u201e", "\u201f", "\u00ab", "\u00bb")
PLACEHOLDER_CHARS = ("{", "}", "<", ">", "[", "]")
# A period after these is not the end of a sentence ("St. Louis").
ABBREVIATIONS = ("St", "Mt", "Ft", "Mr", "Mrs", "Ms", "Dr", "Jr", "Sr", "Inc",
                 "Co", "Corp", "Ltd", "No", "vs", "etc")

_LEGAL_SUFFIX = re.compile(r"(?<![A-Za-z])(?:LLC|L\.L\.C|Inc|Corp|Ltd|LLP|PLLC)(?![A-Za-z])",
                           re.IGNORECASE)
_LEGAL_CO = re.compile(r"(?<![A-Za-z])Co\.")
_URL = re.compile(r"(?:https?://|www\.|@)|\b[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.[a-z]{2,}\b")
_NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
_DECIMAL_RATING = re.compile(r"\b[1-5]\.\d\b")
_OUT_OF_FIVE = re.compile(r"/\s*5\b")
_CLOCK_TIME = re.compile(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)", re.IGNORECASE)
_WORD = re.compile(r"[^\W\d_][\w'\-]*")
_I_FORMS = re.compile(r"^I(?:'(?:d|m|ve|ll))?$")
_SENTENCE_END = re.compile(r"[.!?]+[\"')\]]*(?=\s|$)")


@dataclass(frozen=True)
class ResearchVerdict:
    ok: bool
    line: str          # the normalised line that was checked ("" for NONE)
    reasons: tuple     # reason codes in check order; empty when ok
    rules_sha: str     # rules_sha(): the same for every call


def rules_sha() -> str:
    """sha256 hex of RULES_TEXT + "\\n" + str(RULES_VERSION), read at call time."""
    blob = RULES_TEXT + "\n" + str(RULES_VERSION)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def _plain(text: str) -> str:
    """Lowercased, curly apostrophes as straight ones: the text word lists match on."""
    return text.replace("\u2019", "'").replace("\u2018", "'").lower()


def _has_phrase(low: str, phrase: str) -> bool:
    pattern = r"(?<![a-z0-9'])" + re.escape(phrase) + r"(?![a-z0-9])"
    return re.search(pattern, low) is not None


def _any_phrase(low: str, phrases) -> bool:
    return any(_has_phrase(low, p) for p in phrases)


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _to_decimal(token: str) -> Optional[Decimal]:
    try:
        return Decimal(token.replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _host_of(url: Any) -> Optional[str]:
    """Lowercased host of an http(s) URL without "www." or a trailing dot, or None."""
    if not _nonempty_str(url):
        return None
    try:
        parts = urlsplit(url.strip())
        if parts.scheme.lower() not in ("http", "https"):
            return None
        host = parts.hostname
    except ValueError:
        return None
    if not host:
        return None
    host = host.lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _normalise_domain(domain: Any) -> Optional[str]:
    """"https://www.Example.com/about" -> "example.com"; None when unusable."""
    if not _nonempty_str(domain):
        return None
    text = domain.strip().lower()
    if "://" not in text:
        text = "https://" + text
    host = _host_of(text)
    if not host or "." not in host:
        return None
    return host


def _under(host: str, base: str) -> bool:
    return host == base or host.endswith("." + base)


def _source_allowed(url: Any, domain: Optional[str]) -> bool:
    host = _host_of(url)
    if host is None:
        return False
    if domain and _under(host, domain):
        return True
    return any(_under(host, listing) for listing in LISTING_HOSTS)


def _split_sentences(line: str) -> List[str]:
    """Sentences, ending at . ! or ? followed by a space or the end of the line.
    A period after an abbreviation (ABBREVIATIONS) or a single capital
    (an initial) does not end a sentence."""
    sentences = []
    start = 0
    for match in _SENTENCE_END.finditer(line):
        before = line[start:match.start()].split()
        last = before[-1] if before else ""
        if match.group().startswith(".") and (
                last in ABBREVIATIONS or (len(last) == 1 and last.isupper())):
            continue
        piece = line[start:match.end()].strip()
        if piece:
            sentences.append(piece)
        start = match.end()
    rest = line[start:].strip()
    if rest:
        sentences.append(rest)
    return sentences


def _words(text: str) -> List[str]:
    """Word tokens with a trailing possessive or stray apostrophe/hyphen removed."""
    out = []
    for token in _WORD.findall(text.replace("\u2019", "'")):
        if token.endswith("'s"):
            token = token[:-2]
        token = token.rstrip("'-")
        if token:
            out.append(token)
    return out


def _in_excerpt(word: str, excerpts: List[str]) -> bool:
    pattern = r"(?<![\w])" + re.escape(word) + r"(?![\w])"
    return any(re.search(pattern, ex.replace("\u2019", "'")) for ex in excerpts)


# --------------------------------------------------------------------------
# input shape
# --------------------------------------------------------------------------

def _read_context(context: Any) -> Tuple[Dict[str, Any], bool]:
    """(usable fields, ok). Unusable fields come back as None."""
    out = {"company": None, "company_spoken": None, "offer_branch": None,
           "niche": None, "domain": None, "city": None}
    if not isinstance(context, dict):
        return out, False
    ok = True
    for key in ("company", "company_spoken"):
        if _nonempty_str(context.get(key)):
            out[key] = " ".join(context[key].split())
        else:
            ok = False
    if context.get("offer_branch") in OFFER_BRANCHES:
        out["offer_branch"] = context["offer_branch"]
    else:
        ok = False
    if context.get("niche") in NICHES:
        out["niche"] = context["niche"]
    else:
        ok = False
    out["domain"] = _normalise_domain(context.get("website_domain"))
    if out["domain"] is None:
        ok = False
    city = context.get("city")
    if city is None:
        pass
    elif _nonempty_str(city):
        out["city"] = " ".join(city.split())
    else:
        ok = False
    return out, ok


def _check_evidence(evidence: Any, domain: Optional[str]) -> Tuple[List[str], List[Dict[str, str]]]:
    """(reason codes, well-formed facts)."""
    reasons = []
    facts = []
    if not isinstance(evidence, dict):
        return ["evidence_malformed", "identity_unconfirmed"], facts
    raw = evidence.get("facts")
    if not isinstance(raw, list):
        reasons.append("evidence_malformed")
        raw = []
    elif not raw:
        reasons.append("no_facts")
    elif len(raw) > MAX_FACTS:
        reasons.append("too_many_facts")
    for item in raw:
        if (isinstance(item, dict) and _nonempty_str(item.get("text"))
                and _nonempty_str(item.get("source_url"))
                and _nonempty_str(item.get("excerpt"))):
            facts.append({"text": item["text"], "source_url": item["source_url"],
                          "excerpt": item["excerpt"]})
        elif "evidence_malformed" not in reasons:
            reasons.append("evidence_malformed")
    if any(not _source_allowed(f["source_url"], domain) for f in facts):
        reasons.append("source_not_allowed")
    identity = evidence.get("identity")
    if not (isinstance(identity, dict)
            and _source_allowed(identity.get("source_url"), domain)
            and identity.get("matched_on") in MATCHED_ON):
        reasons.append("identity_unconfirmed")
    return reasons, facts


# --------------------------------------------------------------------------
# line checks
# --------------------------------------------------------------------------

def _shape(line: str, low: str, sentences: List[str]) -> List[str]:
    reasons = []
    if len(line.split()) > MAX_WORDS:
        reasons.append("too_long")
    if len(sentences) > MAX_SENTENCES:
        reasons.append("too_many_sentences")
    if "?" in line:
        reasons.append("question")
    if "!" in line:
        reasons.append("exclamation")
    if any(c in line for c in DASH_CHARS) or " - " in line or "--" in line \
            or line.startswith("- ") or line.endswith(" -"):
        reasons.append("dash")
    if any(ord(c) > 0xFFFF or unicodedata.category(c) in ("So", "Me")
           or 0xFE00 <= ord(c) <= 0xFE0F for c in line):
        reasons.append("emoji")
    if any(unicodedata.category(c) in ("Cf", "Co", "Cn", "Cs", "Zl", "Zp")
           for c in line):
        reasons.append("bad_character")
    if _URL.search(low):
        reasons.append("url")
    if any(c in line for c in PLACEHOLDER_CHARS):
        reasons.append("placeholder")
    letters = [c for c in line if c.isalpha()]
    starts_ok = all(_first_letter_upper(s) for s in sentences)
    if (not starts_ok or (len(letters) > 1 and all(c.isupper() for c in letters))
            or re.search(r"(?<![\w'])i(?![\w])", line.replace("\u2019", "'"))):
        reasons.append("capitalization")
    return reasons


def _first_letter_upper(sentence: str) -> bool:
    """The sentence starts with a capital letter (nothing before it)."""
    return bool(sentence) and sentence[0].isalpha() and sentence[0].isupper()


def _lexical(line: str, low: str, sentences: List[str]) -> List[str]:
    reasons = []
    if any(re.match(re.escape(p) + r"(?![a-z0-9])", _plain(s))
           for s in sentences for p in OPENERS):
        reasons.append("opener")
    if _any_phrase(low, BOOKING_WORDS) or _CLOCK_TIME.search(line):
        reasons.append("mentions_booking")
    if _any_phrase(low, GUESS_WORDS):
        reasons.append("guess")
    if any(c in line for c in MONEY_CHARS) or _any_phrase(low, MONEY_WORDS):
        reasons.append("money_or_results")
    if _any_phrase(low, RESEARCH_WORDS):
        reasons.append("mentions_research")
    if (_any_phrase(low, STAR_WORDS) or _OUT_OF_FIVE.search(line)
            or _DECIMAL_RATING.search(line)):
        reasons.append("star_rating")
    if _any_phrase(low, STALE_PHRASES) or any(
            re.search(r"(?<![A-Za-z])" + m + r"(?![A-Za-z])", line) for m in MONTHS):
        reasons.append("stale_date")
    if _LEGAL_SUFFIX.search(line) or _LEGAL_CO.search(line):
        reasons.append("legal_suffix")
    if any(c in line for c in QUOTE_CHARS):
        reasons.append("quoted_text")
    if _any_phrase(low, NEGATIVE_WORDS):
        reasons.append("negative")
    return reasons


def _supported_name(word: str, excerpts: List[str], allowed: Set[str]) -> bool:
    return word in allowed or _in_excerpt(word, excerpts)


def _allowed_names(ctx: Dict[str, Any], facts: List[Dict[str, str]]) -> Set[str]:
    allowed = set()
    for key in ("company_spoken", "city"):
        if ctx.get(key):
            allowed.update(_words(ctx[key]))
    hosts = [_host_of(f["source_url"]) for f in facts]
    for name, bases in PLATFORM_NAMES:
        if any(h and any(_under(h, b) for b in bases) for h in hosts):
            allowed.add(name)
    return allowed


def _claudeism(low: str, sentences: List[str], excerpts: List[str],
               allowed: Set[str]) -> bool:
    if _any_phrase(low, CLAUDEISMS):
        return True
    # Anything after the last tie-back: a further sentence, or a further
    # clause in the tie-back's own sentence.
    tied = [i for i, s in enumerate(sentences) if TIE_BACK.search(_plain(s))]
    if tied:
        last = tied[-1]
        if last < len(sentences) - 1:
            return True
        sentence = _plain(sentences[last])
        tail = sentence[list(TIE_BACK.finditer(sentence))[-1].end():]
        if TAIL_KICKER.search(tail):
            return True
    # A later sentence with no number, no name from the evidence and no tie-back.
    for sentence in sentences[1:]:
        words = _words(sentence)
        has_number = bool(re.search(r"\d", sentence))
        has_name = any(
            w[0].isupper() and (w in allowed or (i > 0 and _in_excerpt(w, excerpts)))
            and not _I_FORMS.match(w)
            for i, w in enumerate(words))
        has_tie = bool(TIE_BACK.search(_plain(sentence)))
        if not (has_number or has_name or has_tie):
            return True
    return False


def _after_over(text_low: str, start: int, text: str, end: int) -> bool:
    """The number at text[start:end] reads "over N", "more than N" or "N+"."""
    before = text_low[:start].rstrip()
    return any(re.search(r"(?<![a-z])" + w + r"$", before) for w in OVER_WORDS) \
        or text[end:end + 1] == "+"


def _year_like(token: str, value: Decimal) -> bool:
    """A bare four-digit 1900-2099 ("2011"), not a count written "2,011"."""
    return "," not in token and "." not in token and 1900 <= value <= 2099


def _int_digits(value: Decimal) -> int:
    return len(str(int(value)))


def _numbers(line: str, low: str, excerpts: List[str]) -> List[str]:
    """Numbers as found, or "over N" rounded down.

    A plain number must appear in an excerpt (same value; "1,200" and "1200"
    are the same). "over N" / "more than N" / "N+" passes when an excerpt
    says over N itself, or has a number above N with the same count of
    digits that is not a bare year: "over 200" is backed by 213, not by
    "since 2011" or by 1,500 of something else. A bare N on the page does not
    back "over N".
    """
    reasons = []
    found = set()
    over_found = set()
    above_candidates = []
    for ex in excerpts:
        ex_low = _plain(ex)
        for m in _NUMBER.finditer(ex):
            value = _to_decimal(m.group())
            if value is None:
                continue
            found.add(value)
            if _after_over(ex_low, m.start(), ex, m.end()):
                over_found.add(value)
            if not _year_like(m.group(), value):
                above_candidates.append(value)
    for m in _NUMBER.finditer(line):
        value = _to_decimal(m.group())
        if value is None:
            reasons.append("number_not_in_evidence")
            continue
        if _after_over(low, m.start(), line, m.end()):
            ok = value in over_found or any(
                v > value and _int_digits(v) == _int_digits(value) for v in above_candidates)
        else:
            ok = value in found
        if not ok:
            reasons.append("number_not_in_evidence")
    if _any_phrase(low, SPELLED_NUMBERS):
        reasons.append("spelled_number")
    return reasons


def _names(sentences: List[str], excerpts: List[str], allowed: Set[str]) -> bool:
    """True when every capitalised word past the first of its sentence is backed."""
    for sentence in sentences:
        for i, word in enumerate(_words(sentence)):
            if i == 0 or not word[0].isupper() or _I_FORMS.match(word):
                continue
            if not _supported_name(word, excerpts, allowed):
                return False
    return True


def _company_form(line: str, ctx: Dict[str, Any]) -> List[str]:
    reasons = []
    company, spoken = ctx.get("company"), ctx.get("company_spoken")
    if not company or not spoken:
        return reasons
    if company.casefold() in line.casefold() and (
            _LEGAL_SUFFIX.search(company) or _LEGAL_CO.search(company)):
        reasons.append("legal_suffix")
    if company.casefold() == spoken.casefold():
        return reasons
    if company.casefold() in line.casefold():
        reasons.append("company_form")
        return reasons
    # The spoken name followed by a capitalised word from the long form
    # ("Brightline Cleaning Services" when the spoken form is "Brightline").
    extra = {w.casefold() for w in _words(company)} - {w.casefold() for w in _words(spoken)}
    for m in re.finditer(re.escape(spoken), line, re.IGNORECASE):
        following = _words(line[m.end():])
        if following and following[0][0].isupper() and following[0].casefold() in extra \
                and line[m.end():m.end() + 1] == " ":
            reasons.append("company_form")
            break
    return reasons


# --------------------------------------------------------------------------
# public entry point
# --------------------------------------------------------------------------

def validate(line: str, evidence: dict, context: dict) -> ResearchVerdict:
    """Check one research line against the rules. Never raises."""
    sha = rules_sha()
    if line is None:
        line = ""
    if not isinstance(line, str):
        return ResearchVerdict(ok=False, line="", reasons=("line_malformed",), rules_sha=sha)
    norm = " ".join(line.split())
    if norm == "" or re.fullmatch(r"none\W*", norm, re.IGNORECASE):
        return ResearchVerdict(ok=False, line="", reasons=("none",), rules_sha=sha)
    try:
        reasons = _raw_checks(line) + _run_checks(norm, evidence, context)
    except Exception:  # fail closed: a bug in a check is a failed line
        reasons = ["validator_error"]
    ordered = tuple(dict.fromkeys(reasons))
    return ResearchVerdict(ok=not ordered, line=norm, reasons=ordered, rules_sha=sha)


def _raw_checks(raw: str) -> List[str]:
    """Checks on the line as given, before normalising. A line break is also a
    control character, so "\n" gives both codes."""
    reasons = []
    if any(c in raw for c in LINE_BREAKS):
        reasons.append("line_break")
    if any(unicodedata.category(c) == "Cc" for c in raw):
        reasons.append("control_char")
    if raw != raw.strip():
        reasons.append("surrounding_space")
    if len(raw) > MAX_CHARS:
        reasons.append("too_long_chars")
    return reasons


def _run_checks(line: str, evidence: Any, context: Any) -> List[str]:
    reasons = []
    ctx, ctx_ok = _read_context(context)
    if not ctx_ok:
        reasons.append("context_malformed")
    low = _plain(line)
    sentences = _split_sentences(line)

    reasons += _shape(line, low, sentences)
    reasons += _lexical(line, low, sentences)

    ev_reasons, facts = _check_evidence(evidence, ctx["domain"])
    excerpts = [f["excerpt"] for f in facts]
    allowed = _allowed_names(ctx, facts)

    if _claudeism(low, sentences, excerpts, allowed):
        reasons.append("claudeism")
    if not TIE_BACK.search(low):
        reasons.append("no_tie_back")
    branch = ctx["offer_branch"]
    if branch is None or not _any_phrase(low, BRANCH_WORDS[branch]):
        reasons.append("no_offer_link")
    reasons += ev_reasons
    reasons += _numbers(line, low, excerpts)
    if not _names(sentences, excerpts, allowed):
        reasons.append("unsupported_name")
    reasons += _company_form(line, ctx)
    return reasons
