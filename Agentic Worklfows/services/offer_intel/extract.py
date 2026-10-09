"""Step 2 of analysis: pull the offer out of a win, facts only.

Sonnet (role ``research``) returns every field as {"value", "quote"} or null.
Then ``verify`` checks each one in code, because a model asked for quotes
still paraphrases and still guesses:

* the quote must appear in the post or the author's replies (whitespace,
  case and curly quotes ignored; "..." may join two pieces of the text);
* a number must appear in its own quote ("$3k/mo" supports 3000);
* an industry, mechanism, place or buyer must share a word with its quote;
* an enum must be one of its allowed values;
* a tool must be named somewhere in the text.

A field that fails is dropped to null and listed under ``dropped`` with the
reason, so the hand check shows what the model tried to invent.
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from shared import llm

from services.offer_intel.gate import source_text

logger = logging.getLogger("offer_intel.extract")

MAX_TOKENS = 1200
TYPICAL_OUT_TOKENS = 450

TEXT_FIELDS = ("offer_one_line", "mechanism", "industry", "buyer_role", "geo", "guarantee",
               "list_source", "copy_angle", "time_to_result", "experience")
NUMBER_FIELDS = ("setup_usd", "monthly_usd", "deal_usd", "emails_sent", "reply_rate_pct",
                 "positive_replies", "calls_booked")
PRICING_MODELS = ("setup_plus_retainer", "retainer", "rev_share", "pay_per_meeting", "pay_per_lead",
                  "performance", "one_off_build", "other")
ENUM_FIELDS = {"pricing_model": PRICING_MODELS}
LIST_FIELDS = ("tools",)
ALL_FIELDS = TEXT_FIELDS + NUMBER_FIELDS + tuple(ENUM_FIELDS) + LIST_FIELDS
TEXT_VALUE_LIMIT = 160

SYSTEM = """You extract facts from one member's win post in a community for people who sell AI and automation services to businesses. The text is the post plus the author's own replies in the comments.

Return one JSON object with exactly these keys. Each value is either null or {"value": ..., "quote": "..."}.
- "quote" is copied WORD FOR WORD from the text, the shortest span that states the fact. If you cannot copy a span that states it, the field is null.
- Only what the author states about THIS win. Never infer, never fill a field from general knowledge, never use the community's typical offers. Most posts leave most fields null; that is the right answer.

Keys:
- offer_one_line: what the author sells to this client, in at most 15 words of your own (the quote is the span it rests on).
- mechanism: what they build or run for the client (for example "database reactivation campaign", "AI voice receptionist", "cold email appointment setting").
- industry: the CLIENT's industry, as stated (for example "dental practices", "commercial roofing"). Not the author's industry.
- buyer_role: who bought (owner, office manager, marketing director).
- geo: the client's country, state or city.
- pricing_model: one of these, as stated for this client:
  setup_plus_retainer = a one-time setup fee AND a fixed monthly fee, both stated.
  retainer = a fixed monthly fee with no setup fee stated.
  rev_share = a percentage of the client's revenue or profit.
  pay_per_meeting = paid per booked or attended call or appointment.
  pay_per_lead = paid per lead delivered to the client, never a flat price for a job.
  performance = paid per closed deal, sale or other result that is not a meeting or a lead (commission).
  one_off_build = one fixed price for one job or build, whatever its size (a $5 flat job is one_off_build).
  other = hourly, salary, equity or anything else stated.
  A fixed fee combined with pay per result (for example a monthly fee plus pay per closed call) takes the per-result model, never setup_plus_retainer or retainer; setup_plus_retainer needs a stated setup fee.
- setup_usd, monthly_usd, deal_usd: numbers in US dollars as stated (3000, not "$3k").
- setup_usd: one client's one-time setup fee.
- monthly_usd: one client's recurring monthly fee. Null for the author's total monthly revenue or MRR across clients ("first $10k month", "hit $20k MRR") and for projected fees.
- deal_usd: the price ONE client agreed to pay for this deal (signed or paid): a one-off build price or that client's total contract. Null for month or lifetime revenue totals ("First $10k month", "Contracted Revenue = $34,348"), projected or possible scope ("$10k+ scope"), lifetime value projections, prices quoted on a call or in a proposal the client has not accepted, and sums across several clients.
- emails_sent, reply_rate_pct, positive_replies, calls_booked: numbers from the cold email result, if stated.
- guarantee: the guarantee offered, as stated.
- list_source: where the lead list came from (Apollo, Google Maps, LinkedIn Sales Navigator, job boards, Clay).
- tools: a list of tool names the author names (Instantly, Smartlead, n8n, Make, GoHighLevel). The quote covers them.
- copy_angle: the hook or opening line of the cold email, if the author shares it.
- time_to_result: how long it took, as stated.
- experience: the author's stage, as stated (first client, months in the program).
"""

# The sentence shared/llm.py appends in json_mode. extract() asks for JSON
# itself and parses locally (parse_json), so the billed prompt is unchanged
# but a model that copies Skool's markdown escapes ("\\(") is repaired
# instead of failing the post.
JSON_ONLY = "\n\nRespond with a single JSON object and nothing else. No prose, no code fences."


# ----------------------------------------------------------------- matching
# curly quotes, en/em dashes and a non-breaking space, written as chr() so the
# file stays plain ASCII
_QUOTES = {chr(0x2018): "'", chr(0x2019): "'", chr(0x201C): '"', chr(0x201D): '"', chr(0x2013): "-",
           chr(0x2014): "-", chr(0xA0): " "}
_ELLIPSIS = r"\.\.\.|" + chr(0x2026)


def _norm(text: Any) -> str:
    text = str(text or "")
    for bad, good in _QUOTES.items():
        text = text.replace(bad, good)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text.strip(" .,;:!?\"'")


def quote_in_source(quote: Any, source: str) -> bool:
    """Word-for-word, modulo whitespace, case, curly quotes and edge punctuation.
    An ellipsis may join pieces; each piece of 3+ characters must be present."""
    haystack = _norm(source)
    pieces = [p for p in (_norm(x) for x in re.split(_ELLIPSIS, str(quote or ""))) if p]
    if not pieces or sum(len(p) for p in pieces) < 3:
        return False
    return all(len(p) < 3 or p in haystack for p in pieces) and any(len(p) >= 3 for p in pieces)


_NUMBER = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(k|m|mm|million|thousand|grand)?\b", re.I)
_SCALE = {"k": 1e3, "thousand": 1e3, "grand": 1e3, "m": 1e6, "mm": 1e6, "million": 1e6}


def numbers_in(text: str) -> List[float]:
    out = []
    for digits, unit in _NUMBER.findall(str(text or "")):
        try:
            value = float(digits.replace(",", ""))
        except ValueError:
            continue
        out.append(value * _SCALE.get((unit or "").lower(), 1.0))
    return out


def _as_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    found = numbers_in(str(value or ""))
    return found[0] if len(found) == 1 else None


def number_in_quote(value: float, quote: str) -> bool:
    return any(abs(n - value) <= 0.01 * max(1.0, abs(value)) for n in numbers_in(quote))


# Fields whose VALUE is counted (the taxonomy reads it), so the value itself
# must rest on its quote, not just the quote on the post: "dental" backed by
# "Signed a new client!" is a real quote and an invented industry.
VALUE_MUST_MATCH = ("industry", "mechanism", "geo", "buyer_role")
_STOP = frozenset("that with their them they this from for and the who what have into your our".split())


def value_in_quote(value: Any, quote: Any) -> bool:
    """Some word of 4+ letters in the value shares its first 4 letters with a
    word in the quote ("dentists" / "dental", "reactivation" / "reactivating").
    A value with no such word ("IT", "UK") passes."""
    words = [w for w in re.findall(r"[a-z0-9]+", _norm(value)) if len(w) >= 4 and w not in _STOP]
    if not words:
        return True
    stems = set(w[:4] for w in re.findall(r"[a-z0-9]+", _norm(quote)) if len(w) >= 4)
    return any(w[:4] in stems for w in words)


# ------------------------------------------------------------------ verify
def _check(field: str, item: Any, source: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if item is None:
        return None, None
    if not isinstance(item, dict) or "value" not in item:
        return None, "not_value_quote"
    value, quote = item.get("value"), item.get("quote")
    if value in (None, "", []):
        return None, None
    if not quote_in_source(quote, source):
        return None, "quote_not_in_post"
    if field in NUMBER_FIELDS:
        number = _as_number(value)
        if number is None:
            return None, "not_a_number"
        if not number_in_quote(number, str(quote)):
            return None, "number_not_in_quote"
        return {"value": number, "quote": str(quote)}, None
    if field in ENUM_FIELDS:
        choice = str(value).strip().lower().replace(" ", "_")
        if choice not in ENUM_FIELDS[field]:
            return None, "not_allowed"
        return {"value": choice, "quote": str(quote)}, None
    if field in LIST_FIELDS:
        names = value if isinstance(value, list) else [value]
        haystack = _norm(source)
        kept = [str(n).strip() for n in names if str(n).strip() and _norm(n) in haystack]
        if not kept:
            return None, "not_named_in_post"
        return {"value": kept, "quote": str(quote)}, None
    text = str(value).strip()
    if field in VALUE_MUST_MATCH and not value_in_quote(text, quote):
        return None, "value_not_in_quote"
    if len(text) > TEXT_VALUE_LIMIT:
        text = text[:TEXT_VALUE_LIMIT].rstrip() + "..."
    return {"value": text, "quote": str(quote)}, None


def verify(raw: Any, source: str, has_media: bool = False) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    fields = {}  # type: Dict[str, Any]
    dropped = {}  # type: Dict[str, str]
    for field in ALL_FIELDS:
        kept, why = _check(field, raw.get(field), source)
        fields[field] = kept
        if why:
            dropped[field] = why
    extra = sorted(k for k in raw if k not in ALL_FIELDS)
    if any(fields[f] for f in NUMBER_FIELDS):
        strength = "numbers"
    elif has_media:
        strength = "screenshot_only"
    else:
        strength = "vague"
    return {"fields": fields, "dropped": dropped, "unknown_keys": extra, "evidence_strength": strength,
            "filled": sum(1 for f in ALL_FIELDS if fields[f])}


# --------------------------------------------------------------- parse JSON
_VALID_ESCAPE = re.compile(r'\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4})')


def repair_escapes(text: str) -> str:
    """Double every backslash that does not start a valid JSON escape, left to
    right, so an existing valid pair (such as a double backslash) stays a pair."""
    out = []
    i = 0
    while i < len(text):
        if text[i] != "\\":
            out.append(text[i])
            i += 1
            continue
        match = _VALID_ESCAPE.match(text, i)
        if match:
            out.append(match.group(0))
            i = match.end()
        else:
            out.append("\\\\")
            i += 1
    return "".join(out)


def parse_json(raw: Any) -> Dict[str, Any]:
    """The model's reply as a dict. Repairs invalid backslash escapes (Skool's
    markdown "\\(" copied into a quote) and falls back to the outermost {...}.
    Anything else raises llm.LLMError, which analyze.run counts as an error."""
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    candidates = [text, repair_escapes(text)]
    span = re.search(r"\{.*\}", text, re.S)
    if span:
        candidates += [span.group(0), repair_escapes(span.group(0))]
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
        raise llm.LLMError("model did not return a JSON object: %s" % text[:300])
    raise llm.LLMError("model did not return valid JSON: %s" % text[:300])


def extract(record: Dict[str, Any]) -> Dict[str, Any]:
    source = source_text(record)
    raw = parse_json(llm.complete("research", SYSTEM + JSON_ONLY, source, max_tokens=MAX_TOKENS,
                                  json_mode=False))
    result = verify(raw, source, has_media=bool(record.get("has_media")))
    result["model_role"] = "research"
    return result


def value(result: Optional[Dict[str, Any]], field: str) -> Any:
    """The verified value of one field, or None."""
    item = ((result or {}).get("fields") or {}).get(field)
    return item.get("value") if isinstance(item, dict) else None
